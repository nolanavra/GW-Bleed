import importlib.util
import json
from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

AVAILABLE = importlib.util.find_spec("pymupdf") is not None
if AVAILABLE:
    import pymupdf
    from gw_imposition.pdf_export import export_to_stage, identity, points
    from gw_imposition.pdf_service import inspect_pdf
    from gw_imposition import Job, calculate, load_profile
    from gw_imposition.units import to_um


@unittest.skipUnless(AVAILABLE, "Install desktop dependencies")
class PdfExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.pdf"
        with pymupdf.open() as doc:
            doc.new_page(width=270, height=162).insert_text((20, 40), "FIRST PAGE")
            page = doc.new_page(width=320, height=220)
            page.set_cropbox(pymupdf.Rect(25, 29, 295, 191))
            page.draw_rect(pymupdf.Rect(0, 0, 135, 81), fill=(1, 0, 0), color=None)
            page.draw_rect(pymupdf.Rect(135, 0, 270, 81), fill=(0, 1, 0), color=None)
            page.draw_rect(pymupdf.Rect(0, 81, 135, 162), fill=(0, 0, 1), color=None)
            page.draw_rect(pymupdf.Rect(135, 81, 270, 162), fill=(1, 1, 0), color=None)
            page.insert_text((20, 45), "SECOND PAGE", fontsize=10)
            page.set_rotation(90)
            doc.save(self.source)

    def tearDown(self):
        self.temp.cleanup()

    def request(self, mode="artwork", stock="13x19", rotation=0, page=1):
        width, height = (to_um("2"), to_um("3.5")) if page == 1 else (to_um("3.5"), to_um("2"))
        bx, by = inspect_pdf(self.source)[page].derive_bleed(width, height)
        job = Job(width, height, bx, max(to_um(".25"), 2*max(bx, by)), bleed_y_um=by)
        profile = load_profile()
        c = next(c for c in calculate(job, profile).candidates
                 if c.stock_id == stock and c.rotation == rotation)
        return dict(source=str(self.source), destination=str(self.root / "output.pdf"),
                    signature=identity(self.source), mode=mode, page=page,
                    job=asdict(job), profile=asdict(profile), candidate=asdict(c))

    def test_modes_stocks_rotations_page_geometry_and_lines(self):
        for stock in ("12x18", "13x19"):
            for rotation in (0, 90):
                for mode in ("artwork", "lines", "combined"):
                    with self.subTest(stock=stock, rotation=rotation, mode=mode):
                        req = self.request(mode, stock, rotation)
                        stage = self.root / "stage.pdf"
                        export_to_stage(req, stage)
                        c = req["candidate"]
                        with pymupdf.open(stage) as pdf:
                            p = pdf[0]
                            self.assertEqual(len(pdf), 1)
                            self.assertEqual(p.mediabox, p.cropbox)
                            self.assertEqual(p.mediabox, p.trimbox)
                            self.assertEqual(p.mediabox, p.bleedbox)
                            self.assertEqual(p.mediabox, p.artbox)
                            self.assertAlmostEqual(p.rect.width, points(c["sheet_width_um"]), places=3)
                            self.assertAlmostEqual(p.rect.height, points(c["sheet_height_um"]), places=3)
                            self.assertEqual(p.get_text().count("SECOND PAGE"),
                                             0 if mode == "lines" else c["yield_per_sheet"])
                            self.assertNotIn("FIRST PAGE", p.get_text())
                            self.assertEqual(p.get_images(), [])
                            lines = [d for d in p.get_drawings() if d["type"] == "s"]
                            self.assertEqual(len(lines), 0 if mode == "artwork" else len(c["cuts"])+len(c["slitters"]))
                            for line in lines:
                                self.assertEqual(line["color"], (0, 0, 0))
                                self.assertAlmostEqual(line["width"], .25)
                                self.assertTrue(abs(line["rect"].width-p.rect.width) < .001 or
                                                abs(line["rect"].height-p.rect.height) < .001)

    def test_render_matches_rotated_cropped_source_at_original_scale(self):
        for rotation in (0, 90):
            req = self.request(rotation=rotation)
            stage = self.root / "stage.pdf"
            export_to_stage(req, stage)
            region = req["candidate"]["bleed_regions"][0]
            with pymupdf.open(self.source) as source, pymupdf.open(stage) as output:
                src = source[1].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
                out = output[0].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
                for fx, fy in ((.12, .12), (.88, .12), (.12, .88), (.88, .88)):
                    ox, oy = (fx, fy) if rotation == 0 else (1-fy, fx)
                    x = round(points(region["x_um"] + ox*region["width_um"])*2)
                    y = round(points(region["y_um"] + oy*region["height_um"])*2)
                    self.assertEqual(out.pixel(x, y), src.pixel(int(fx*src.width), int(fy*src.height)))

    def test_finishing_guides_match_engine_and_artwork_omits_them(self):
        from dataclasses import replace
        from gw_imposition.finishing import FinishingOperation
        for horizontal in ("crease", "cross_perf"):
            req = self.request(page=0)
            job = replace(Job(**req["job"]), finishing=(
                FinishingOperation(horizontal, to_um("1")),
                FinishingOperation("strike_perf", to_um("1.5"), to_um(".25"), to_um("1.75")),
                FinishingOperation("rotary_perf", to_um("2.5"))))
            c = calculate(job, load_profile()).recommended
            req.update(job=asdict(job), candidate=asdict(c))
            for mode in ("artwork", "lines", "combined"):
                req["mode"] = mode
                stage = self.root / "finishing.pdf"
                export_to_stage(req, stage)
                with pymupdf.open(stage) as doc:
                    lines = doc[0].get_drawings()
                    expected = () if mode == "artwork" else (*c.cuts, *c.slitters, *c.finishing)
                    self.assertEqual(len(lines), len(expected))
                    for drawing, mark in zip(lines, expected):
                        self.assertEqual(drawing["color"], (0, 0, 0))
                        self.assertEqual(drawing["width"], .25)
                        for actual, target in zip(drawing["rect"], (mark.x1_um, mark.y1_um, mark.x2_um, mark.y2_um)):
                            self.assertAlmostEqual(actual, points(target), places=3)

    def test_registration_filled_rectangles_match_geometry_in_all_export_modes(self):
        from gw_imposition.registration import RegistrationSettings, build_registration
        settings = RegistrationSettings()
        for stock in ("12x18", "13x19"):
            for rotation in (0, 90):
                for mode in ("artwork", "lines", "combined"):
                    req = self.request(mode=mode, stock=stock, rotation=rotation, page=0)
                    req["registration"] = asdict(settings)
                    candidate = next(c for c in calculate(Job(**req["job"]), load_profile()).candidates
                                     if asdict(c) == req["candidate"])
                    marks = build_registration(candidate, load_profile(), settings).marks
                    stage = self.root / "registration.pdf"
                    export_to_stage(req, stage)
                    with pymupdf.open(stage) as doc:
                        rectangles = [d for d in doc[0].get_drawings() if d["type"] == "f"]
                        self.assertEqual(len(rectangles), len(marks))
                        for drawing, mark in zip(rectangles, marks):
                            r = mark.rect
                            self.assertEqual(drawing["fill"], (0, 0, 0))
                            self.assertIsNone(drawing["color"])
                            self.assertEqual(drawing["fill_opacity"], 1)
                            for actual, expected in zip(drawing["rect"],
                                    (r.x_um, r.y_um, r.x_um+r.width_um, r.y_um+r.height_um)):
                                self.assertAlmostEqual(actual, points(expected), places=3)

    def test_stock_clip_prevents_edge_strokes_from_painting_outside_stock(self):
        req = self.request(mode="lines")
        stage = self.root / "clipped.pdf"
        export_to_stage(req, stage)
        with pymupdf.open(stage) as doc:
            page = doc[0]
            width, height = page.rect.width, page.rect.height
            stream = page.read_contents()
            self.assertIn(b"re W n", stream)
            # Inject overhanging content inside the exported clipping scope.
            # Without a real clipping path it paints the expanded surround black.
            end_scope = stream.rfind(b"\nQ")
            self.assertGreater(end_scope, 0)
            overhang = f"\n0 g -2 -2 {width+4} {height+4} re f\n".encode("ascii")
            doc.update_stream(page.get_contents()[0], stream[:end_scope] + overhang + stream[end_scope:])
            # Expose a 2-point surround to verify the physical clipping path,
            # rather than relying only on the viewer respecting CropBox.
            page.set_mediabox(pymupdf.Rect(-2, -2, width+2, height+2))
            page.set_cropbox(pymupdf.Rect(-2, 0, width+2, height+4))
            pix = page.get_pixmap(matrix=pymupdf.Matrix(8, 8), alpha=False)
            self.assertEqual(pix.pixel(pix.width//2, pix.height//2), (0, 0, 0))
            for x in (0, 7, pix.width-8, pix.width-1):
                for y in range(pix.height):
                    self.assertEqual(pix.pixel(x, y), (255, 255, 255))
            for y in (0, 7, pix.height-8, pix.height-1):
                for x in range(pix.width):
                    self.assertEqual(pix.pixel(x, y), (255, 255, 255))

    def test_reject_source_overwrite_stale_source_and_tampered_geometry(self):
        req = self.request()
        req["destination"] = str(self.source)
        with self.assertRaisesRegex(ValueError, "overwrite"):
            export_to_stage(req, self.root / "stage.pdf")
        req = self.request()
        req["signature"] = (req["signature"][0], 0, 0)
        with self.assertRaisesRegex(ValueError, "changed"):
            export_to_stage(req, self.root / "stage.pdf")
        req = self.request()
        req["candidate"]["placements"][0]["x_um"] = -1
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            export_to_stage(req, self.root / "stage.pdf")

    def test_unwritable_and_changed_during_export(self):
        req = self.request()
        with self.assertRaises(Exception):
            export_to_stage(req, self.root / "absent" / "output.pdf")
        original = identity(self.source)
        with patch("gw_imposition.pdf_export.identity", side_effect=[original, ("changed", 0, 0)]):
            with self.assertRaisesRegex(ValueError, "changed during"):
                export_to_stage(req, self.root / "stage.pdf")

    def test_fonts_images_transparency_and_unequal_bleed(self):
        with pymupdf.open() as doc:
            page = doc.new_page(width=270, height=180)
            page.insert_font(fontname="embedded", fontfile="C:/Windows/Fonts/arial.ttf")
            page.insert_text((20, 40), "EMBEDDED TEXT", fontname="embedded")
            page.draw_rect(pymupdf.Rect(10, 50, 100, 100), fill=(1, 0, 0), fill_opacity=.4)
            image = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 12, 12), False)
            image.clear_with(100)
            page.insert_image(pymupdf.Rect(110, 50, 130, 70), pixmap=image)
            doc.save(self.source)
        req = self.request(page=0)
        # Larger vertical bleed requires a larger gutter.
        req["job"]["gutter_um"] = to_um(".5")
        job = Job(**req["job"])
        req["candidate"] = asdict(calculate(job, load_profile()).recommended)
        stage = self.root / "stage.pdf"
        export_to_stage(req, stage)
        with pymupdf.open(stage) as pdf:
            page = pdf[0]
            self.assertEqual(page.get_text().replace("\u00a0", " ").count("EMBEDDED TEXT"), req["candidate"]["yield_per_sheet"])
            self.assertTrue(page.get_fonts())
            self.assertTrue(page.get_images())
            self.assertTrue(any(abs(d["fill_opacity"]-.4) < .001 for d in page.get_drawings()))

    def test_barcode_exports_decode_and_remain_vector(self):
        from gw_imposition.registration import RegistrationSettings
        from gw_imposition.barcodes import BarcodeSettings
        try:
            import zxingcpp
        except ImportError:
            self.skipTest("Install test dependencies for independent barcode decoding")
        for symbology in ('code128', 'code39'):
            for mode in ('artwork', 'lines', 'combined'):
                request = self.request(mode=mode, page=0)
                value = '000123' if symbology == 'code128' else 'JOB000123'
                request['registration'] = asdict(RegistrationSettings(barcode=BarcodeSettings(True, value, symbology)))
                stage = self.root / 'barcode.pdf'
                export_to_stage(request, stage)
                with pymupdf.open(stage) as pdf:
                    self.assertEqual(pdf[0].get_images(), [])
                    pix = pdf[0].get_pixmap(dpi=200, colorspace=pymupdf.csGRAY)
                    result = zxingcpp.read_barcode(memoryview(pix.samples).cast('B', (pix.height, pix.width)), formats=zxingcpp.BarcodeFormat.Code128 if symbology == 'code128' else zxingcpp.BarcodeFormat.Code39)
                    self.assertIsNotNone(result, (symbology, mode))
                    self.assertEqual(result.text, value)
