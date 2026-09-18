"""Synthetic geometry regressions; these do not certify a real SCC machine."""

from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO

from gw_imposition import Job, calculate, load_profile
from gw_imposition.cli import main
from gw_imposition.models import Margins, Stock
from gw_imposition.profiles import BUNDLED_PROFILES, DEMO_PROFILE
from gw_imposition.units import to_um


def machine(**changes):
    defaults = dict(stocks=(Stock("test", 100, 200),),
                    press_margins=Margins(0, 0, 0, 0),
                    finisher_margins=Margins(0, 0, 0, 0),
                    feed_edges=("short",), allow_rotation=False,
                    minimum_gutter_um=0, maximum_gutter_um=100,
                    gutter_increment_um=1, max_columns=3, max_rows=100,
                    allow_shared_cut=True)
    defaults.update(changes)
    return replace(load_profile(DEMO_PROFILE), **defaults)


class GeometryTests(unittest.TestCase):
    def test_centering_and_full_sheet_lines(self):
        result = calculate(Job(19, 31, bleed_um=2, bleed_y_um=4, gutter_um=8),
                           machine(allow_rotation=True))
        for c in result.candidates:
            first, last = c.bleed_regions[0], c.bleed_regions[-1]
            self.assertLessEqual(abs(first.x_um - (c.sheet_width_um - last.x_um - last.width_um)), 1)
            self.assertEqual(last.y_um + last.height_um, c.usable.y_um + c.usable.height_um)
            for line in c.slitters:
                self.assertEqual((line.x1_um, line.y1_um, line.y2_um),
                                 (line.x2_um, 0, c.sheet_height_um))
            for line in c.cuts:
                self.assertEqual((line.y1_um, line.x1_um, line.x2_um),
                                 (line.y2_um, 0, c.sheet_width_um))
            self.assertEqual(len(c.slitters), len(set(c.slitter_x_um)))
            bx, by = (2, 4) if c.rotation == 0 else (4, 2)
            self.assertEqual(c.placements[0].x_um - first.x_um, bx)
            self.assertEqual(c.placements[0].y_um - first.y_um, by)

    def test_centering_rejects_asymmetric_margin_violation(self):
        result = calculate(Job(80, 100, gutter_um=1),
                           machine(finisher_margins=Margins(15, 0, 0, 0)))
        self.assertIsNone(result.recommended)
        self.assertIn("centered_margins", {r.code for r in result.rejections})

    def test_ranking_uses_stock_before_waste(self):
        profile = machine(stocks=(Stock("wide", 110, 110), Stock("narrow", 100, 200)))
        result = calculate(Job(60, 100, gutter_um=1), profile)
        self.assertEqual(result.recommended.stock_id, "narrow")
        keys = [(-c.yield_per_sheet, c.sheet_width_um, c.sheet_height_um, c.stock_id)
                for c in result.candidates]
        self.assertEqual(keys, sorted(keys))

    def test_all_specification_machines_limit_columns(self):
        self.assertEqual(len(BUNDLED_PROFILES), 6)
        for machine_id, path in BUNDLED_PROFILES.items():
            profile = load_profile(path)
            self.assertEqual(profile.id, machine_id)
            self.assertEqual(profile.approval_state, "unverified")
            result = calculate(Job(to_um("2"), to_um("2"), gutter_um=to_um(".25")), profile)
            if profile.capabilities.max_side_trim_um is not None:
                self.assertIsNone(result.recommended)
                self.assertIn("side_trim_margin_conflict", {r.code for r in result.rejections})
            else:
                self.assertEqual(result.recommended.columns, 3)
            self.assertTrue(all(c.columns <= 3 for c in result.candidates))
        with self.assertRaisesRegex(ValueError, "maximum of 3 columns"):
            machine(max_columns=4)

    def test_exact_fit_and_one_micrometre_over(self):
        profile = machine()
        exact = calculate(Job(50, 50, shared_cut=True), profile).recommended
        self.assertEqual((exact.columns, exact.rows), (2, 4))
        over = calculate(Job(51, 50, shared_cut=True), profile).recommended
        self.assertEqual((over.columns, over.rows), (1, 4))

    def test_bleed_and_gutter_not_double_counted(self):
        result = calculate(Job(40, 40, bleed_um=5, gutter_um=10), machine())
        best = result.recommended
        self.assertEqual((best.columns, best.rows), (2, 4))
        self.assertEqual(best.placements[0].x_um, 5)
        self.assertEqual(best.bleed_regions[-1].x_um + best.bleed_regions[-1].width_um, 100)
        self.assertEqual(best.slitter_x_um, (5, 45, 55, 95))

    def test_margins_intersect_and_are_asymmetric(self):
        profile = machine(press_margins=Margins(10, 2, 4, 1),
                          finisher_margins=Margins(5, 6, 3, 8))
        best = calculate(Job(20, 20, gutter_um=2), profile).recommended
        self.assertEqual((best.usable.x_um, best.usable.y_um,
                          best.usable.width_um, best.usable.height_um), (10, 4, 84, 188))

    def test_rotation_can_rescue_layout(self):
        job = Job(150, 80, gutter_um=1)
        self.assertIsNone(calculate(job, machine()).recommended)
        self.assertEqual(calculate(job, machine(allow_rotation=True)).recommended.rotation, 90)

    def test_long_edge_feed_is_rejected(self):
        for edges in (("long",), ("short", "long")):
            with self.assertRaisesRegex(ValueError, "Only short-edge feeding"):
                machine(feed_edges=edges)

    def test_standard_sheets_always_feed_on_12_or_13_inch_edge(self):
        result = calculate(Job(to_um("3.5"), to_um("2"), gutter_um=to_um(".25")),
                           load_profile())
        expected = {"12x18": (to_um("12"), to_um("18")),
                    "13x19": (to_um("13"), to_um("19"))}
        self.assertEqual({c.rotation for c in result.candidates}, {0, 90})
        self.assertEqual({c.stock_id for c in result.candidates}, set(expected))
        for candidate in result.candidates:
            self.assertEqual(candidate.feed_edge, "short")
            self.assertEqual((candidate.sheet_width_um, candidate.sheet_height_um),
                             expected[candidate.stock_id])

    def test_limits_and_single_sheet_yield(self):
        result = calculate(Job(20, 20, gutter_um=1),
                           machine(max_columns=2, max_rows=3))
        self.assertEqual(len(result.candidates), 6)
        best = result.recommended
        self.assertEqual(best.yield_per_sheet, 6)
        self.assertEqual(best.yield_per_sheet, len(best.placements))
        self.assertIn("grid_limit", [r.code for r in result.rejections])

    def test_no_fit_and_unavailable_reasons(self):
        result = calculate(Job(300, 300, gutter_um=1), machine())
        self.assertEqual(result.rejections[0].code, "item_does_not_fit")
        result = calculate(Job(20, 20, gutter_um=1), machine(stocks=(Stock("x", 100, 200, False),)))
        self.assertEqual(result.rejections[0].code, "stock_unavailable")

    def test_shared_cut_requires_explicit_support(self):
        for job, profile in ((Job(20, 20), machine()),
                             (Job(20, 20, shared_cut=True), machine(allow_shared_cut=False)),
                             (Job(20, 20, bleed_um=1, shared_cut=True), machine())):
            with self.assertRaises(ValueError):
                calculate(job, profile)

    def test_gutter_limits_increments_and_bleed(self):
        for gap in (2, 4, 12):
            with self.assertRaises(ValueError):
                calculate(Job(20, 20, gutter_um=gap),
                          machine(minimum_gutter_um=3, maximum_gutter_um=9, gutter_increment_um=3))
        with self.assertRaises(ValueError):
            calculate(Job(20, 20, bleed_um=5, gutter_um=9), machine())

    def test_placements_within_usable_area_and_nonoverlapping(self):
        for width in (13, 29, 49, 101):
            result = calculate(Job(width, 31, bleed_um=2, gutter_um=5),
                               machine(allow_rotation=True))
            for candidate in result.candidates:
                u = candidate.usable
                boxes = candidate.bleed_regions
                for i, a in enumerate(boxes):
                    self.assertGreaterEqual(a.x_um, u.x_um)
                    self.assertGreaterEqual(a.y_um, u.y_um)
                    self.assertLessEqual(a.x_um + a.width_um, u.x_um + u.width_um)
                    self.assertLessEqual(a.y_um + a.height_um, u.y_um + u.height_um)
                    for b in boxes[i+1:]:
                        self.assertTrue(a.x_um + a.width_um <= b.x_um or
                                        b.x_um + b.width_um <= a.x_um or
                                        a.y_um + a.height_um <= b.y_um or
                                        b.y_um + b.height_um <= a.y_um)

    def test_larger_margins_never_improve_yield(self):
        yields = []
        for margin in range(0, 51, 5):
            result = calculate(Job(19, 29, gutter_um=2),
                               machine(finisher_margins=Margins(margin, margin, margin, margin)))
            yields.append(result.recommended.yield_per_sheet if result.recommended else 0)
        self.assertEqual(yields, sorted(yields, reverse=True))

    def test_ranking_is_deterministic_and_prefers_less_waste(self):
        profile = machine(stocks=(Stock("larger", 101, 201), Stock("smaller", 100, 200)))
        job = Job(50, 50, shared_cut=True)
        self.assertEqual(calculate(job, profile), calculate(job, profile))
        self.assertEqual(calculate(job, profile).recommended.stock_id, "smaller")

    def test_demo_regression(self):
        result = calculate(Job(to_um("3.5"), to_um("2"), to_um(".125"),
                               to_um(".25")), load_profile())
        best = result.recommended
        self.assertEqual((best.stock_id, best.columns, best.rows, best.yield_per_sheet),
                         ("13x19", 3, 8, 24))
        self.assertIn("UNVERIFIED", result.warnings[0])


class InputTests(unittest.TestCase):
    def test_cli_selects_each_specification_machine(self):
        for machine_id in BUNDLED_PROFILES:
            with tempfile.TemporaryDirectory() as folder, redirect_stdout(StringIO()):
                path = Path(folder) / "layout.json"
                self.assertEqual(main(["--width", "3.5", "--height", "2",
                                       "--machine", machine_id, "--output", str(path)]),
                                 1 if load_profile(BUNDLED_PROFILES[machine_id]).capabilities.max_side_trim_um is not None else 0)
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(data["calculation"]["profile_id"], machine_id)
                self.assertEqual(data["profile_snapshot"]["max_columns"], 3)

    def test_units_and_rounding(self):
        self.assertEqual(to_um("1"), 25400)
        self.assertEqual(to_um("25.4", "mm"), 25400)
        self.assertEqual(to_um(Decimal("0.0005"), "mm"), 1)
        for value in ("nan", "Infinity", "-1", "abc"):
            with self.assertRaises(ValueError):
                to_um(value)

    def test_invalid_dimensions(self):
        for width in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                Job(width, 1)

    def test_invalid_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"
            path.write_text('{"schema_version": 999}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_profile(path)
        with self.assertRaises(ValueError):
            machine(gutter_increment_um=0)

    def test_cli_json_export_and_no_fit(self):
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(StringIO()):
            path = Path(folder) / "result.json"
            self.assertEqual(main(["--width", "3.5", "--height", "2", "--bleed", ".125",
                                   "--output", str(path)]), 0)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["calculation"]["candidates"][0]["yield_per_sheet"], 24)
            self.assertEqual(data["schema_version"], 4)
            self.assertNotIn("quantity", data["job"])
            self.assertNotIn("overs", data["job"])
            for candidate in data["calculation"]["candidates"]:
                self.assertEqual(candidate["yield_per_sheet"], candidate["rows"] * candidate["columns"])
                for removed in ("sheets_required", "excess_pieces", "total_stock_area_um2"):
                    self.assertNotIn(removed, candidate)
            self.assertEqual(data["profile_snapshot"]["approval_state"], "unverified")
            self.assertEqual(main(["--width", "100", "--height", "100"]), 1)

    def test_cli_invalid_input(self):
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
            main(["--width", "0", "--height", "2"])
        self.assertEqual(error.exception.code, 2)

    def test_order_quantity_arguments_are_rejected(self):
        for option in ("--quantity", "--overs"):
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
                main(["--width", "3.5", "--height", "2", option, "100"])
            self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
