from dataclasses import replace
import unittest
from gw_imposition.finishing import FinishingOperation as Op, FinishingMark as Mark, build_finishing, validate_marks
from gw_imposition import Job, calculate, load_profile
from gw_imposition.models import Rect, Margins, Stock
from gw_imposition.profiles import DEMO_PROFILE


class FinishingTests(unittest.TestCase):
    def profile(self):
        return replace(load_profile(DEMO_PROFILE), stocks=(Stock("sheet", 1000, 2000),),
                       press_margins=Margins(0, 0, 0, 0), finisher_margins=Margins(0, 0, 0, 0),
                       minimum_gutter_um=0, maximum_gutter_um=100, gutter_increment_um=1)

    def test_exclusive_horizontal_tool_and_valid_card_positions(self):
        with self.assertRaisesRegex(ValueError, "OR"):
            Job(300, 400, finishing=(Op("crease", 100), Op("cross_perf", 200)))
        for op in (Op("crease", 400), Op("rotary_perf", 300), Op("strike_perf", 100, 200, 100)):
            with self.assertRaises(ValueError):
                Job(300, 400, finishing=(op,))

    def test_repetition_deduplication_and_rotation_rejection(self):
        result = calculate(Job(250, 350, gutter_um=10, finishing=(Op("crease", 100), Op("rotary_perf", 80))), self.profile())
        self.assertTrue(result.candidates)
        for c in result.candidates:
            self.assertEqual(c.rotation, 0)
            creases = [m for m in c.finishing if m.kind == "crease"]
            rotary = [m for m in c.finishing if m.kind == "rotary_perf"]
            self.assertEqual(len(creases), c.rows)
            self.assertEqual(len(rotary), c.columns)
            self.assertTrue(all(m.x1_um == 0 and m.x2_um == 1000 and m.y1_um == m.y2_um for m in creases))
            self.assertTrue(all(m.y1_um == 0 and m.y2_um == 2000 and m.x1_um == m.x2_um for m in rotary))
        self.assertTrue(any(r.code == "finishing_rule" and r.rotation == 90 for r in result.rejections))

    def test_max_four_strike_tools_after_repetition(self):
        result = calculate(Job(250, 350, gutter_um=10,
            finishing=(Op("strike_perf", 50, 10, 200), Op("strike_perf", 150, 10, 200))), self.profile())
        self.assertEqual(result.recommended.columns, 2)
        for c in result.candidates:
            self.assertLessEqual(len({m.x1_um for m in c.finishing}), 4)

    def test_sixty_percent_boundary_cumulative_and_overlap(self):
        placements = (Rect(0, 0, 100, 700),)
        for length, warns in ((599, False), (600, False), (601, True)):
            marks, warnings = build_finishing((Op("strike_perf", 50, 0, length),), placements, 0, 100, 1000)
            self.assertEqual(bool(warnings), warns)
        _, warnings = build_finishing((Op("strike_perf", 50, 0, 350),),
                                      (Rect(0, 0, 100, 400), Rect(0, 500, 100, 400)), 0, 100, 1000)
        self.assertIn("70.0%", warnings[0])
        self.assertIn("solenoids may burn out", warnings[0])
        coverage = validate_marks((Mark("strike_perf", 50, 0, 50, 400),
                                   Mark("strike_perf", 50, 200, 50, 600)), 100, 1000)
        self.assertEqual(coverage[50], 600)

    def test_sheet_rules_block_full_strike_partial_rotary_and_wrong_direction(self):
        invalid = (Mark("strike_perf", 50, 0, 50, 1000),
                   Mark("rotary_perf", 50, 100, 50, 900),
                   Mark("crease", 50, 0, 50, 1000),
                   Mark("cross_perf", 0, 10, 100, 20))
        for mark in invalid:
            with self.assertRaises(ValueError):
                validate_marks((mark,), 100, 1000)
        with self.assertRaises(ValueError):
            validate_marks(tuple(Mark("strike_perf", x, 10, x, 300) for x in (10, 20, 30, 40, 50)), 100, 1000)

    def test_json_operations_normalize_into_immutable_model(self):
        job = Job(300, 400, finishing=[{"kind": "cross_perf", "position_um": 100}])
        self.assertEqual(job.finishing, (Op("cross_perf", 100),))


if __name__ == "__main__":
    unittest.main()
