import unittest
from dataclasses import asdict, replace
from gw_imposition import Job, calculate, load_profile
from gw_imposition.profiles import BUNDLED_PROFILES
from gw_imposition.accessories import MachineAccessories, default_accessories, validate_accessories
from gw_imposition.finishing import FinishingOperation as Op
from gw_imposition.finishing_presets import preset_operations
from gw_imposition.machine_guide import build_guide


class AccessoryTests(unittest.TestCase):
    def test_defaults_and_unsupported_tools(self):
        for machine, path in BUNDLED_PROFILES.items():
            profile = load_profile(path)
            settings = default_accessories(profile)
            self.assertEqual(settings.total_strikes, 4 if profile.capabilities.strike_perf else 0)
            self.assertEqual(settings.auto_strike_perfs, 2 if machine == 'pt_9375scc_supercut' else 0)
            self.assertEqual(settings.rotary_perfs, 0)
            validate_accessories(settings, profile)
        with self.assertRaises(ValueError):
            MachineAccessories(4, 1)
        with self.assertRaises(ValueError):
            validate_accessories(MachineAccessories(0, 1), load_profile())
        with self.assertRaises(ValueError):
            validate_accessories(MachineAccessories(1), load_profile(BUNDLED_PROFILES['pt_33sc']))

    def test_repeated_tools_respect_installed_count(self):
        job = Job(88900, 50800, 3175, 6350, finishing=(Op('strike_perf', 25400, 0, 12700),),
                  accessories=MachineAccessories(1))
        result = calculate(job, load_profile())
        self.assertTrue(result.candidates)
        self.assertTrue(all(c.columns == 1 for c in result.candidates))
        self.assertTrue(any('installed' in r.message for r in result.rejections))
        rotary = replace(job, finishing=(Op('rotary_perf', 25400),))
        self.assertFalse(calculate(rotary, load_profile()).candidates)
        self.assertTrue(calculate(replace(rotary, accessories=MachineAccessories(1, 0, 1)), load_profile()).candidates)

    def test_rotated_pattern_uses_swapped_card_dimensions_and_machine_axes(self):
        job = Job(88900, 50800, 3175, 6350, finishing_rotation=90,
                  finishing=(Op('crease', 60000), Op('strike_perf', 20000, 0, 15000)),
                  accessories=MachineAccessories(4))
        self.assertEqual(Job(**asdict(job)), job)
        result = calculate(job, load_profile())
        self.assertTrue(result.candidates)
        for c in result.candidates:
            self.assertEqual(c.rotation, 90)
            self.assertEqual(c.placements[0].height_um, job.width_um)
            self.assertTrue(any(m.y1_um == c.placements[0].y_um+60000 for m in c.finishing if m.kind == 'crease'))
            self.assertTrue(all(m.x1_um == 0 and m.x2_um == c.sheet_width_um for m in c.finishing if m.kind == 'crease'))
        with self.assertRaises(ValueError):
            replace(job, finishing_rotation=0)

    def test_supercut_guide_uses_installed_automatic_tools(self):
        profile = load_profile(BUNDLED_PROFILES['pt_9375scc_supercut'])
        job = Job(88900, 50800, 3175, 6350, finishing=(Op('strike_perf', 25400, 0, 12700),),
                  accessories=MachineAccessories(2, 1))
        candidate = calculate(job, profile).recommended
        guide = build_guide(job, profile, candidate)
        self.assertEqual([t.automatic for t in guide.strikes], [True, False, False])

    def test_tent_requires_flap_and_rotary_is_explicit(self):
        for flap in (0, 60000, -1):
            with self.assertRaises(ValueError):
                preset_operations('tent', 60000, 120000, flap=flap)
        strikes = preset_operations('coupons', 60000, 120000)
        self.assertEqual(strikes[0], Op('strike_perf', 30000, 0, 120000))
        self.assertEqual(preset_operations('coupons', 60000, 120000, vertical_tool='rotary_perf')[0], Op('rotary_perf', 30000))
