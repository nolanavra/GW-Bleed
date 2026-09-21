from dataclasses import asdict, replace
import unittest
from gw_imposition import Job, calculate, load_profile
from gw_imposition.models import Stock, Margins
from gw_imposition.finishing import FinishingOperation
from gw_imposition.profiles import BUNDLED_PROFILES, DEMO_PROFILES, profile_from_data
from gw_imposition.units import to_um


class MachineSpecificationTests(unittest.TestCase):
    def test_six_profiles_match_workbook_and_round_trip(self):
        expected = (("pt_33sc", "2", "1.8", False, False, False),
                    ("pt_331scc", "1.96", "1.77", True, False, False),
                    ("pt_331scc_air", "1.96", "1.77", True, False, False),
                    ("pt_335scc_b_multi", "1.96", "1.89", True, True, False),
                    ("pt_8336scc_multi", "1.96", "1.89", True, True, True),
                    ("pt_9375scc_supercut", "1.96", "1.89", True, True, True))
        self.assertEqual(len(BUNDLED_PROFILES), 6)
        for key, w, h, crease, rotary, strike in expected:
            p = load_profile(BUNDLED_PROFILES[key]); c = p.capabilities
            self.assertEqual(p.schema_version, 2)
            self.assertEqual(p.approval_state, "unverified")
            self.assertEqual((c.min_finished_width_um, c.min_finished_height_um), (to_um(w), to_um(h)))
            self.assertEqual((c.crease, c.cross_perf, c.rotary_perf, c.strike_perf), (crease, crease, rotary, strike))
            self.assertEqual(c.max_slitters, 6)
            self.assertEqual(len(p.specifications), 22)
            self.assertEqual(profile_from_data(asdict(p)), p)
            self.assertIn("SCC Comparison!", p.source_document)
            self.assertEqual(len(p.source_sha256), 64)

    def test_unsupported_finishing_rejected_for_each_machine(self):
        for path in BUNDLED_PROFILES.values():
            p = load_profile(path)
            p = replace(p, capabilities=replace(p.capabilities, max_side_trim_um=None))  # Isolate tool support.
            for kind in ("crease", "cross_perf", "rotary_perf", "strike_perf"):
                op = FinishingOperation(kind, 25400, 0, 25400) if kind == "strike_perf" else FinishingOperation(kind, 25400)
                result = calculate(Job(88900, 50800, gutter_um=6350, finishing=(op,)), p)
                self.assertEqual(bool(result.candidates), getattr(p.capabilities, kind), (p.id, kind))
                if not getattr(p.capabilities, kind):
                    self.assertIn("machine_finishing", {r.code for r in result.rejections})

    def test_minimum_finished_size_in_feed_coordinates_and_rotations(self):
        p = load_profile(BUNDLED_PROFILES["pt_33sc"])
        p = replace(p, capabilities=replace(p.capabilities, max_side_trim_um=None))  # Isolate dimensional limits.
        for width, height, valid in ((50800, 45720, True), (50799, 45720, False), (50800, 45719, False)):
            result = calculate(Job(width, height, gutter_um=5000), replace(p, allow_rotation=False))
            self.assertEqual(bool(result.candidates), valid)
        result = calculate(Job(45720, 50800, gutter_um=5000), p)
        self.assertEqual({c.rotation for c in result.candidates}, {90})

    def test_input_size_limits_are_enforced(self):
        p = load_profile(BUNDLED_PROFILES["pt_33sc"])
        p = replace(p, capabilities=replace(p.capabilities, max_side_trim_um=None))  # Isolate dimensional limits.
        for width, height, valid in (("8.2", "8.2", True), ("8.199", "8.2", False), ("13", "26", True), ("13", "26.001", False), ("13.001", "26", False)):
            profile = replace(p, stocks=(Stock("test", to_um(width), to_um(height)),))
            result = calculate(Job(50800, 50800, gutter_um=5000), profile)
            self.assertEqual(bool(result.candidates), valid)
            if not valid:
                self.assertIn("machine_sheet_size", {r.code for r in result.rejections})

    def test_interchangeable_fixed_middle_gutters(self):
        for path in list(BUNDLED_PROFILES.values())[:3]:
            p = load_profile(path)
            self.assertIsNone(p.capabilities.max_side_trim_um)
            p = replace(p, capabilities=replace(p.capabilities, max_side_trim_um=None))  # Isolate middle gutter settings.
            for gap in (5000, 6001, 15000):
                self.assertTrue(calculate(Job(88900, 50800, gutter_um=gap), p).candidates)
            for gap in (1, 3000, 4999, 15001):
                with self.assertRaises(ValueError):
                    calculate(Job(88900, 50800, gutter_um=gap), p)
            self.assertTrue(calculate(Job(88900, 50800, shared_cut=True), p).candidates)
            with self.assertRaises(ValueError):
                calculate(Job(88900, 50800, bleed_um=1, shared_cut=True), p)

    def test_slitter_limit_and_legacy_profiles(self):
        p = load_profile()
        p = replace(p, capabilities=replace(p.capabilities, max_slitters=4))
        result = calculate(Job(88900, 50800, gutter_um=6350), p)
        self.assertTrue(all(c.columns <= 2 for c in result.candidates))
        self.assertIn("slitter_limit", {r.code for r in result.rejections})
        for path in DEMO_PROFILES.values():
            old = load_profile(path)
            self.assertEqual(old.schema_version, 1)
            self.assertIsNone(old.capabilities)
            self.assertEqual(profile_from_data(asdict(old)), old)

    def side_profile(self, width, **changes):
        p = load_profile(BUNDLED_PROFILES["pt_33sc"])
        defaults = dict(capabilities=replace(p.capabilities, max_side_trim_um=3000), stocks=(Stock("side-test", width, 457200),),
                        press_margins=Margins(0, 0, 0, 0), finisher_margins=Margins(0, 0, 0, 0))
        defaults.update(changes)
        return replace(p, **defaults)

    def test_side_trim_inclusive_limit_and_one_micrometre_over(self):
        for sheet_width, valid in ((310000, True), (315999, True), (316000, True), (316001, False), (316002, False)):
            result = calculate(Job(100000, 50800, gutter_um=5000), self.side_profile(sheet_width))
            self.assertEqual(bool(result.candidates), valid, sheet_width)
            for c in result.candidates:
                self.assertLessEqual(c.slitter_x_um[0], 3000)
                self.assertLessEqual(c.sheet_width_um-c.slitter_x_um[-1], 3000)
            if not valid:
                self.assertIn("side_trim_limit", {r.code for r in result.rejections})
        zero = calculate(Job(100000, 50800, shared_cut=True), self.side_profile(300000)).recommended
        self.assertEqual((zero.slitter_x_um[0], zero.sheet_width_um-zero.slitter_x_um[-1]), (0, 0))

    def test_side_trim_measures_trim_not_bleed_boundary_and_respects_rotation(self):
        p = self.side_profile(316000)
        result = calculate(Job(100000, 50800, bleed_um=2000, gutter_um=5000), p)
        c = result.recommended
        self.assertEqual(c.bleed_regions[0].x_um, 1000)
        self.assertEqual(c.slitter_x_um[0], 3000)
        invalid = calculate(Job(100000, 50800, bleed_um=2000, gutter_um=5000), self.side_profile(318000))
        self.assertFalse(invalid.candidates)
        rotated = calculate(Job(50800, 100000, gutter_um=5000), p)
        self.assertEqual({c.rotation for c in rotated.candidates}, {90})

    def test_provisional_margins_conflict_is_explicit_and_not_relaxed(self):
        for path in list(BUNDLED_PROFILES.values())[:3]:
            p = load_profile(path)
            p = replace(p, capabilities=replace(p.capabilities, max_side_trim_um=3000))
            result = calculate(Job(100000, 50800, gutter_um=5000), p)
            self.assertFalse(result.candidates)
            self.assertIn("side_trim_margin_conflict", {r.code for r in result.rejections})
            self.assertEqual(p.press_margins.left_um, 6350)
        p = self.side_profile(316000, press_margins=Margins(0, 3001, 0, 0))
        self.assertFalse(calculate(Job(100000, 50800, gutter_um=5000), p).candidates)

    def test_legacy_side_field_migration_and_validation(self):
        p = load_profile(BUNDLED_PROFILES["pt_33sc"])
        data = asdict(p)
        data["capabilities"].pop("max_side_trim_um")
        data["capabilities"]["side_gutter_um"] = 3000
        self.assertEqual(profile_from_data(data).capabilities.max_side_trim_um, 3000)
        for invalid in (-1, True, 1.5):
            with self.assertRaises(ValueError):
                replace(p.capabilities, max_side_trim_um=invalid)
