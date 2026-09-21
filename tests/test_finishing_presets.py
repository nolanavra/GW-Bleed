import unittest
from gw_imposition.finishing_presets import preset_operations
from gw_imposition.finishing import build_finishing
from gw_imposition.models import Rect


class PresetTests(unittest.TestCase):
    def test_fold_positions(self):
        self.assertEqual([o.position_um for o in preset_operations("half", 60000, 120000)], [60000])
        self.assertEqual([o.position_um for o in preset_operations("accordion", 60000, 120000)], [40000, 80000])
        self.assertEqual([o.position_um for o in preset_operations("gate", 60000, 120000)], [30000, 90000])
        for edge in ("top", "bottom"):
            ops = preset_operations("letter", 60000, 120000, allowance=3000, tuck=edge)
            a, b = (o.position_um for o in ops)
            lengths = [a, b-a, 120000-b]
            self.assertEqual(lengths, [38000, 41000, 41000] if edge == "top" else [41000, 41000, 38000])
        with self.assertRaises(ValueError):
            preset_operations("letter", 60000, 120000, allowance=60000)

    def test_stub_edge_and_two_by_three_coupons(self):
        for edge, kind, expected in (("right", "strike_perf", 150000-50800), ("bottom", "cross_perf", 120000-50800)):
            op, = preset_operations("ticket", 150000, 120000, edge=edge)
            self.assertEqual((op.kind, op.position_um), (kind, expected))
        with self.assertRaisesRegex(ValueError, "Stub size"):
            preset_operations("ticket", 40000, 40000)
        ops = preset_operations("coupons", 60000, 120000)
        self.assertEqual([(o.kind, o.position_um) for o in ops],
                         [("strike_perf", 30000), ("cross_perf", 40000), ("cross_perf", 80000)])
        with self.assertRaises(ValueError):
            preset_operations("coupons", 60000, 120000, columns=1, rows=1)

    def test_tent_three_creases_and_half_flap_strikes(self):
        ops = preset_operations("tent", 60000, 120000, flap=20000)
        self.assertEqual([(o.kind, o.position_um, o.start_um, o.end_um) for o in ops],
                         [("crease", 20000, 0, 0), ("crease", 60000, 0, 0), ("crease", 100000, 0, 0),
                          ("strike_perf", 30000, 0, 10000), ("strike_perf", 30000, 110000, 120000)])
        marks, warnings = build_finishing(ops, (Rect(5000, 5000, 60000, 120000),), 0, 70000, 130000)
        self.assertEqual(len({m.x1_um for m in marks if m.kind == "strike_perf"}), 1)
        self.assertFalse(warnings)

    def test_presets_validate_tiny_and_invalid_cards(self):
        for name in ("half", "accordion", "letter", "gate", "ticket", "coupons", "tent"):
            with self.subTest(preset=name):
                with self.assertRaises(ValueError):
                    preset_operations(name, 0, 120000)
                with self.assertRaises(ValueError):
                    preset_operations(name, 1, 1)
