import unittest
from dataclasses import replace
from gw_imposition import Job, calculate, load_profile
from gw_imposition.models import Margins
from gw_imposition.profiles import BUNDLED_PROFILES
from gw_imposition.registration import RegistrationSettings, build_registration
from gw_imposition.units import to_um


def overlap(a, b):
    return (min(a.x_um+a.width_um, b.x_um+b.width_um) > max(a.x_um, b.x_um) and
            min(a.y_um+a.height_um, b.y_um+b.height_um) > max(a.y_um, b.y_um))


class RegistrationTests(unittest.TestCase):
    def test_dedicated_l_mark_corner_region_and_reader(self):
        profile=load_profile()
        c=calculate(Job(88900,50800,3175,6350),profile).recommended
        settings=RegistrationSettings(machine_mark_enabled=True)
        result=build_registration(c,profile,settings)
        arms=[m.rect for m in result.marks if m.axis.startswith('machine')]
        self.assertEqual(len(arms),2)
        horizontal,vertical=arms
        self.assertEqual((horizontal.width_um,horizontal.height_um),(5000,1000))
        self.assertEqual((vertical.width_um,vertical.height_um),(1000,5000))
        self.assertEqual(horizontal.y_um,vertical.y_um)
        self.assertEqual(horizontal.x_um+horizontal.width_um,vertical.x_um+vertical.width_um)
        for rect in arms:
            self.assertGreaterEqual(rect.y_um,3000)
            self.assertLessEqual(rect.y_um+rect.height_um,20000)
            self.assertGreaterEqual(c.sheet_width_um-rect.x_um-rect.width_um,3000)
            self.assertLessEqual(c.sheet_width_um-rect.x_um,20000)
            self.assertFalse(any(overlap(rect,b) for b in c.bleed_regions))
        no_reader=replace(profile,capabilities=replace(profile.capabilities,barcode_reader=False))
        self.assertFalse(any(m.axis.startswith('machine') for m in build_registration(c,no_reader,settings).marks))
        no_room=replace(profile,press_margins=Margins(0,0,21000,0))
        result=build_registration(c,no_room,settings)
        self.assertFalse(any(m.axis.startswith('machine') for m in result.marks))
        self.assertIn('omitted',' '.join(result.warnings))

    def test_dedicated_mark_minimum_dimensions(self):
        for values in ({'machine_mark_thickness_um':399},{'machine_mark_length_um':4999},
                       {'machine_mark_thickness_um':5000,'machine_mark_length_um':5000}):
            with self.assertRaises(ValueError):RegistrationSettings(**values)

    def test_all_machines_stocks_rotations_marks_are_outside_artwork_and_in_waste(self):
        job = Job(to_um("3.5"), to_um("2"), to_um(".125"), to_um(".25"))
        settings = RegistrationSettings()
        for path in BUNDLED_PROFILES.values():
            profile = load_profile(path)
            result = calculate(job, profile)
            candidates = result.candidates
            if not candidates:
                self.assertIn("side_trim_margin_conflict", {r.code for r in result.rejections})
                continue
            for stock in ("12x18", "13x19"):
                for rotation in (0, 90):
                    c = next(c for c in candidates if c.stock_id == stock and c.rotation == rotation)
                    result = build_registration(c, profile, settings)
                    self.assertTrue(result.marks)
                    self.assertEqual(len(result.marks), len({m.rect for m in result.marks}))
                    self.assertIn("Bottom:", " ".join(result.warnings))
                    pm = profile.press_margins
                    for mark in result.marks:
                        r = mark.rect
                        self.assertGreaterEqual(r.x_um, pm.left_um)
                        self.assertGreaterEqual(r.y_um, pm.lead_um)
                        self.assertLessEqual(r.x_um+r.width_um, c.sheet_width_um-pm.right_um)
                        self.assertLessEqual(r.y_um+r.height_um, c.sheet_height_um-pm.trail_um)
                        self.assertFalse(any(overlap(r, b) for b in c.bleed_regions))
                        if mark.axis == "cut":
                            self.assertIn(mark.coordinate_um, c.cut_y_um)
                            self.assertIn(mark.coordinate_um, (r.y_um, r.y_um+r.height_um))
                            self.assertLessEqual(r.height_um, settings.thickness_um)
                            for p in c.placements:
                                self.assertFalse(min(r.y_um+r.height_um, p.y_um+p.height_um) > max(r.y_um, p.y_um))
                        else:
                            self.assertIn(mark.coordinate_um, c.slitter_x_um)
                            self.assertIn(mark.coordinate_um, (r.x_um, r.x_um+r.width_um))
                            self.assertLessEqual(r.width_um, settings.thickness_um)
                            for p in c.placements:
                                self.assertFalse(min(r.x_um+r.width_um, p.x_um+p.width_um) > max(r.x_um, p.x_um))

    def test_all_sides_when_machine_has_room_and_clipping_when_space_is_tight(self):
        profile = replace(load_profile(), press_margins=Margins(0, 0, 0, 0))
        c = calculate(Job(to_um("3.5"), to_um("2"), to_um(".125"), to_um(".25")), replace(profile, press_margins=Margins(6350,6350,6350,6350))).recommended
        result = build_registration(c, profile, RegistrationSettings())
        self.assertEqual({m.side for m in result.marks}, {"top", "bottom", "left", "right"})
        tight = replace(profile, press_margins=Margins(0, 0, 0, 6000))
        result = build_registration(c, tight, RegistrationSettings(length_um=10000, thickness_um=10000))
        self.assertIn("shortened", " ".join(result.warnings))
        for a in result.marks:
            for b in result.marks:
                if a != b and a.axis == b.axis:
                    self.assertFalse(overlap(a.rect, b.rect))
        self.assertEqual(build_registration(c, profile, RegistrationSettings(enabled=False)).marks, ())
        no_room = build_registration(c, profile, RegistrationSettings(gap_um=254000))
        self.assertFalse(no_room.marks)
        self.assertTrue(no_room.warnings)

    def test_shared_cuts_have_no_mark_in_zero_width_gutter(self):
        profile = replace(load_profile(), allow_shared_cut=True)
        c = calculate(Job(to_um("3"), to_um("2"), shared_cut=True), profile).recommended
        result = build_registration(c, profile, RegistrationSettings())
        outer_x = (min(c.slitter_x_um), max(c.slitter_x_um))
        outer_y = (min(c.cut_y_um), max(c.cut_y_um))
        for mark in result.marks:
            self.assertIn(mark.coordinate_um, outer_x if mark.axis == "slitter" else outer_y)

    def test_settings_validation(self):
        for fields in ({"enabled": 1}, {"length_um": 0}, {"thickness_um": -1}, {"gap_um": -1}, {"length_um": 254001}):
            with self.assertRaises(ValueError):
                RegistrationSettings(**fields)
