"""Desktop integration checks; skip when optional desktop dependencies are absent."""

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

AVAILABLE = all(importlib.util.find_spec(name) for name in ("PySide6", "pymupdf"))
if AVAILABLE:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import pymupdf
    from PySide6.QtWidgets import QApplication
    from gw_imposition.gui import MainWindow
    from gw_imposition.pdf_service import inspect_pdf


@unittest.skipUnless(AVAILABLE, "Install desktop dependencies to test the GUI")
class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name) / "artwork.pdf"
        with pymupdf.open() as doc:
            doc.new_page(width=270, height=162)
            doc.save(path)
        self.window.load_pdf(path)
        self.wait_pdf()

    def wait_pdf(self):
        deadline = time.monotonic() + 10
        while self.window.pdf_busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertFalse(self.window.pdf_busy)

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.temp.cleanup()

    def calculate(self):
        self.window.calculate_layout()
        deadline = time.monotonic() + 10
        while not self.window.calculate_button.isEnabled() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertTrue(self.window.calculate_button.isEnabled())

    def test_calculate_select_alternative_and_invalidate(self):
        w = self.window
        self.assertEqual(w.machine.count(), 6)
        self.calculate()
        self.assertEqual(w.result.recommended.yield_per_sheet, 24)
        self.assertTrue(all(c.columns <= 3 and c.feed_edge == "short" for c in w.result.candidates))
        w.table.selectRow(1)
        self.assertEqual(w.preview.candidate, w.result.candidates[1])
        self.assertIn("Alternative", w.summary.text())
        w.width.setText("4")
        self.assertIsNone(w.result)
        self.assertIsNone(w.preview.candidate)
        self.assertFalse(w.export_button.isEnabled())

    def test_invalid_input_and_no_fit_clear_results(self):
        self.calculate()
        self.window.width.setText("abc")
        self.calculate()
        self.assertIn("Invalid dimension", self.window.messages.toPlainText())
        self.assertIsNone(self.window.result)
        self.window.width.setText("100")
        self.calculate()
        self.assertIn("exceed", self.window.messages.toPlainText())
        self.assertFalse(self.window.export_button.isEnabled())

    def test_stale_worker_result_is_discarded(self):
        w = self.window
        w.calculate_layout()
        w.height.setText("3")
        w.pool.waitForDone()
        self.app.processEvents()
        self.assertIsNone(w.result)
        self.assertFalse(w.export_button.isEnabled())

    def test_pdf_page_selection_does_not_change_trim(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.pdf"
            with pymupdf.open() as doc:
                doc.new_page(width=270, height=162)
                doc.new_page(width=144, height=252).set_rotation(90)
                doc.save(path)
            self.assertTrue(self.window.load_pdf(path))
            self.wait_pdf()
            self.assertEqual(self.window.width.text(), "3.5")
            self.assertEqual(self.window.page_choice.count(), 2)
            self.window.page_choice.setCurrentIndex(1)
            self.wait_pdf()
            self.assertIn("3.500 × 2.000", self.window.page_info.text())
            path.write_bytes(b"invalid pdf")
            self.window.load_pdf(path)
            self.wait_pdf()
            self.assertFalse(self.window.pdf_pages)

    def test_password_pdf_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "locked.pdf"
            with pymupdf.open() as doc:
                doc.new_page()
                doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                         owner_pw="owner", user_pw="test")
            with self.assertRaisesRegex(ValueError, "Password-protected"):
                inspect_pdf(path)

    def test_save_selected_layout(self):
        self.calculate()
        self.window.table.selectRow(1)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "result.json"
            with patch("gw_imposition.gui.QFileDialog.getSaveFileName", return_value=(str(path), "")):
                self.window.save_json()
            data = json.loads(path.read_text())
            self.assertEqual(data["selected_candidate_index"], 1)
            self.assertNotIn("quantity", data["job"])
            self.assertEqual(data["calculation"]["candidates"][1]["columns"],
                             self.window.preview.candidate.columns)

    def test_pdf_bleed_axes_and_page_changes(self):
        from gw_imposition.pdf_service import PdfPageInfo
        from gw_imposition.units import to_um
        info = PdfPageInfo(270, 180, 0)
        self.assertEqual(info.derive_bleed(to_um("3.5"), to_um("2")),
                         (to_um(".125"), to_um(".25")))
        self.assertEqual(info.derive_bleed(to_um("3.75"), to_um("2.5")), (0, 0))
        self.assertFalse(hasattr(self.window, "bleed"))
        self.calculate()
        self.assertEqual(self.window.job.bleed_um, 3175)
        self.assertEqual(self.window.job.vertical_bleed_um, 3175)
        self.window.height.setText("1.75")
        self.assertIn("0.2500", self.window.bleed_info.text())
        self.assertIsNone(self.window.result)

    def test_pdf_required(self):
        self.window.pdf_pages = ()
        self.calculate()
        self.assertIsNone(self.window.result)
        self.assertIn("Select a PDF", self.window.messages.toPlainText())

    def test_pdf_preview_toggle_and_rotated_placement_bounds(self):
        from PySide6.QtWidgets import QGraphicsPixmapItem
        self.calculate()
        w = self.window
        row = next(i for i, c in enumerate(w.result.candidates) if c.rotation == 90)
        w.table.selectRow(row)
        c = w.preview.candidate
        items = [item for item in w.preview.scene().items() if isinstance(item, QGraphicsPixmapItem)]
        self.assertEqual(len(items), c.yield_per_sheet)
        bounds = sorted((round(item.sceneBoundingRect().x() * 1000),
                         round(item.sceneBoundingRect().y() * 1000),
                         round(item.sceneBoundingRect().width() * 1000),
                         round(item.sceneBoundingRect().height() * 1000)) for item in items)
        self.assertEqual(bounds, sorted((r.x_um, r.y_um, r.width_um, r.height_um) for r in c.bleed_regions))
        w.show_pdf_checkbox.setChecked(False)
        self.assertFalse(any(isinstance(item, QGraphicsPixmapItem) for item in w.preview.scene().items()))
        self.assertEqual(w.preview.candidate, c)
        w.show_pdf_checkbox.setChecked(True)
        self.assertEqual(sum(isinstance(item, QGraphicsPixmapItem) for item in w.preview.scene().items()), c.yield_per_sheet)

    def test_render_uses_selected_page_rotation(self):
        from gw_imposition.pdf_service import render_pdf_page
        from PySide6.QtGui import QImage
        path = Path(self.temp.name) / "two-pages.pdf"
        with pymupdf.open() as doc:
            page = doc.new_page(width=270, height=162)
            page.draw_rect(page.rect, fill=(1, 0, 0), color=None)
            page = doc.new_page(width=270, height=162)
            page.draw_rect(page.rect, fill=(0, 0, 1), color=None)
            page.set_rotation(90)
            doc.save(path)
        first = QImage.fromData(render_pdf_page(path, 0))
        second = QImage.fromData(render_pdf_page(path, 1))
        self.assertGreater(first.width(), first.height())
        self.assertLess(second.width(), second.height())
        self.assertGreater(first.pixelColor(20, 20).red(), 240)
        self.assertGreater(second.pixelColor(20, 20).blue(), 240)

    def test_card_matches_rotated_sheet_and_details(self):
        self.window.height.setText("1.98")
        self.calculate()
        w = self.window
        row = next(i for i, c in enumerate(w.result.candidates) if c.rotation == 90)
        w.table.selectRow(row)
        c = w.preview.candidate
        w.view_mode.setCurrentText("Card")
        artwork = [item for item in w.preview.scene().items() if item.data(0) == "artwork"]
        self.assertEqual(len(artwork), 1)
        self.assertAlmostEqual(artwork[0].sceneBoundingRect().width()*1000, c.bleed_regions[0].width_um)
        self.assertAlmostEqual(artwork[0].sceneBoundingRect().height()*1000, c.bleed_regions[0].height_um)
        cuts = sorted(item.line().y1()*1000 for item in w.preview.scene().items() if item.data(0) == "cuts")
        offset = c.placements[0].y_um-c.bleed_regions[0].y_um
        self.assertEqual(cuts, [offset, offset+c.placements[0].height_um])
        self.assertIn("Artwork rotation: 90°", w.details.text())
        self.assertIn("Bottom: 0.2500 in", w.details.text())

    def test_layers_preserve_zoom_pan_and_selection(self):
        w = self.window
        w.show()
        self.app.processEvents()
        self.calculate()
        w.preview.zoom(4)
        w.preview.horizontalScrollBar().setValue(120)
        w.preview.verticalScrollBar().setValue(170)
        transform = w.preview.transform()
        scroll = (w.preview.horizontalScrollBar().value(), w.preview.verticalScrollBar().value())
        candidate, row = w.preview.candidate, w.table.currentRow()
        for key, checkbox in w.layer_checkboxes.items():
            checkbox.setChecked(False)
            self.assertFalse(any(item.data(0) == key for item in w.preview.scene().items()))
            self.assertEqual(w.preview.transform(), transform)
            self.assertEqual((w.preview.horizontalScrollBar().value(), w.preview.verticalScrollBar().value()), scroll)
            self.assertEqual(w.table.currentRow(), row)
            self.assertEqual(w.preview.candidate, candidate)
            checkbox.setChecked(True)
        w.show_pdf_checkbox.setChecked(False)
        self.assertEqual((w.preview.horizontalScrollBar().value(), w.preview.verticalScrollBar().value()), scroll)
        w.view_mode.setCurrentText("Card")
        self.assertTrue(w.preview.auto_fit)

    def make_colored_pages(self):
        path = Path(self.temp.name) / "colors.pdf"
        with pymupdf.open() as doc:
            for color in ((1, 0, 0), (0, 0, 1)):
                page = doc.new_page(width=270, height=162)
                page.draw_rect(page.rect, fill=color, color=None)
            doc.save(path)
        return path

    def test_cache_reuses_pages_and_ignores_obsolete_results(self):
        w = self.window
        path = self.make_colored_pages()
        w.load_pdf(path)
        obsolete_token = w.pdf_token
        w.load_pdf(path, 1)
        self.wait_pdf()
        self.assertEqual(w.page_choice.currentIndex(), 1)
        self.assertGreater(w.preview.artwork.toImage().pixelColor(10, 10).blue(), 240)
        w.pdf_failed(obsolete_token, "obsolete error")
        self.assertNotIn("obsolete", w.messages.toPlainText())
        w.page_choice.setCurrentIndex(0)
        # Supersede an in-flight page request with a cached page, then load page 0.
        w.page_choice.setCurrentIndex(1)
        self.wait_pdf()
        self.assertEqual(w.page_choice.currentIndex(), 1)
        w.page_choice.setCurrentIndex(0)
        self.wait_pdf()
        self.assertEqual(len(w.loader.cache), 2)
        w.page_choice.setCurrentIndex(1)
        self.assertIsNone(w.loader.process)  # Cache hit starts no subprocess.
        self.wait_pdf()
        self.assertGreater(w.preview.artwork.toImage().pixelColor(10, 10).blue(), 240)
        self.calculate()
        token = w.loader.token
        w.table.selectRow(1)
        w.show_pdf_checkbox.setChecked(False)
        w.show_pdf_checkbox.setChecked(True)
        self.assertEqual(w.loader.token, token)

    def test_changed_missing_and_encrypted_files_preserve_inputs(self):
        w = self.window
        path = self.make_colored_pages()
        w.load_pdf(path)
        self.wait_pdf()
        old_signature = w.pdf_signature
        with pymupdf.open() as doc:
            page = doc.new_page(width=288, height=180)
            page.insert_text((20, 40), "Changed source")
            doc.save(path)
        w.check_source()
        self.assertTrue(w.pdf_busy)
        self.wait_pdf()
        self.assertNotEqual(w.pdf_signature, old_signature)
        self.assertEqual(len(w.loader.cache), 1)
        self.assertEqual(w.pdf_pages[0].width_points, 288)
        path.unlink()
        w.check_source()
        self.wait_pdf()
        self.assertFalse(w.pdf_pages)
        self.assertEqual(w.width.text(), "3.5")
        self.assertIsNone(w.result)
        with pymupdf.open() as doc:
            doc.new_page()
            doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="secret")
        w.load_pdf(path)
        self.wait_pdf()
        self.assertIn("Password-protected", w.messages.toPlainText())
        self.assertEqual(w.width.text(), "3.5")

    def test_loading_is_async_and_card_works_before_calculation(self):
        from PySide6.QtCore import QTimer
        w = self.window
        w.load_pdf(self.make_colored_pages())
        self.assertTrue(w.pdf_busy)
        self.assertFalse(w.calculate_button.isEnabled())
        ticks = []
        QTimer.singleShot(0, lambda: ticks.append(True))
        self.wait_pdf()
        self.assertTrue(ticks)
        w.view_mode.setCurrentText("Card")
        self.assertIsNone(w.result)
        self.assertEqual(sum(item.data(0) == "artwork" for item in w.preview.scene().items()), 1)

    def test_load_layout_round_trip_recalculates_and_restores_selection(self):
        self.calculate()
        w = self.window
        w.table.selectRow(2)
        selected = w.preview.candidate
        path = Path(self.temp.name) / "saved.json"
        with patch("gw_imposition.gui.QFileDialog.getSaveFileName", return_value=(str(path), "")):
            w.save_json()
        data = json.loads(path.read_text())
        data["calculation"]["candidates"][2]["placements"][0]["x_um"] = -999999
        path.write_text(json.dumps(data))
        w.width.setText("1")
        self.assertTrue(w.load_layout(path))
        self.wait_pdf()
        w.pool.waitForDone()
        self.app.processEvents()
        self.assertEqual(w.preview.candidate, selected)
        self.assertEqual(w.job.width_um, 88900)
        self.assertEqual(w.machine.currentData(), "saved_profile")
        self.assertIn("recalculated", w.messages.toPlainText())

    def test_finishing_editor_preview_and_saved_layout(self):
        from gw_imposition.finishing import FinishingOperation
        from gw_imposition.units import to_um
        ops = (FinishingOperation("crease", to_um("1")),
               FinishingOperation("strike_perf", to_um("1.5"), 0, to_um("2")),
               FinishingOperation("rotary_perf", to_um("2.5")))
        w = self.window
        panel = w.finishing_panel
        panel.set_operations(ops)
        self.assertEqual(panel.advanced.operations(), ops)
        panel.set_operations((ops[0], FinishingOperation("cross_perf", to_um(".5"))))
        panel.apply()
        self.assertIn("same interchangeable tool", panel.status.text())
        self.assertFalse(panel.apply_button.isEnabled())
        self.assertEqual(w.finishing_operations, ())
        panel.set_operations(ops)
        panel.apply()
        w.pool.waitForDone()
        self.app.processEvents()
        selected = w.preview.candidate
        self.assertIn("solenoids", w.messages.toPlainText())
        marks = lambda: [i for i in w.preview.scene().items() if i.data(0) == "finishing"]
        self.assertEqual(len(marks()), len(selected.finishing))
        w.preview.zoom(1.5)
        transform = w.preview.transform()
        w.finishing_checkbox.setChecked(False)
        self.assertFalse(marks())
        self.assertEqual(w.preview.transform(), transform)
        self.assertEqual(w.preview.candidate, selected)
        w.finishing_checkbox.setChecked(True)
        w.view_mode.setCurrentText("Card")
        self.assertEqual({i.data(1) for i in marks()}, {op.kind for op in ops})
        self.assertEqual(len(marks()), 3)
        path = Path(self.temp.name) / "finishing.json"
        with patch("gw_imposition.gui.QFileDialog.getSaveFileName", return_value=(str(path), "")):
            w.save_json()
        self.assertEqual(json.loads(path.read_text())["schema_version"], 4)
        w.finishing_operations = ()
        self.assertTrue(w.load_layout(path))
        self.wait_pdf()
        w.pool.waitForDone()
        self.app.processEvents()
        self.assertEqual(w.job.finishing, ops)
        self.assertEqual(w.preview.candidate.finishing, selected.finishing)
        self.assertEqual(panel.advanced.operations(), ops)

    def test_load_invalid_layout_preserves_current_state(self):
        self.calculate()
        result = self.window.result
        path = Path(self.temp.name) / "invalid.json"
        path.write_text('{"schema_version": 1}')
        self.assertFalse(self.window.load_layout(path))
        self.assertEqual(self.window.result, result)
        self.assertIn("Unable to load layout", self.window.messages.toPlainText())

    def test_finishing_tab_presets_drafts_and_advanced(self):
        w = self.window
        panel = w.finishing_panel
        self.assertEqual(w.results_tabs.tabText(1), "Finishing")
        self.assertFalse(panel.isWindow())
        self.calculate()
        original = w.preview.candidate
        panel.preset.setCurrentIndex(panel.preset.findData("half"))
        self.assertEqual(w.finishing_operations, ())
        self.assertEqual(w.preview.candidate, original)
        self.assertIn("Not applied", panel.status.text())
        panel.apply()
        w.pool.waitForDone()
        self.app.processEvents()
        self.assertEqual(w.job.finishing[0].position_um, 25400)
        panel.preset.setCurrentIndex(panel.preset.findData("advanced"))
        self.assertEqual(panel.advanced.operations(), w.job.finishing)
        panel.advanced.table.cellWidget(0, 1).setValue(.75)
        self.assertEqual(w.job.finishing[0].position_um, 25400)
        panel.apply()
        w.pool.waitForDone()
        self.app.processEvents()
        self.assertEqual(w.job.finishing[0].position_um, 19050)
        panel.preset.setCurrentIndex(panel.preset.findData("tent"))
        panel.apply()
        w.pool.waitForDone()
        self.app.processEvents()
        self.assertEqual(len(w.job.finishing), 3)
        self.assertIn("solenoids", panel.sheet_status.text())
        panel.preset.setCurrentIndex(panel.preset.findData("ticket"))
        panel.edge.setCurrentIndex(panel.edge.findData("bottom"))
        self.assertFalse(panel.apply_button.isEnabled())
        self.assertIn("Stub size", panel.status.text())
        panel.apply()
        self.assertEqual(len(w.job.finishing), 3)
        panel.preset.setCurrentIndex(panel.preset.findData("none"))
        panel.apply()
        w.pool.waitForDone()
        self.app.processEvents()
        self.assertEqual(w.job.finishing, ())

    def test_preset_updates_dimensions_and_advanced_can_produce_no_fit(self):
        w = self.window
        panel = w.finishing_panel
        panel.preset.setCurrentIndex(panel.preset.findData("half"))
        w.height.setText("1")
        self.assertEqual(panel.draft_operations[0].position_um, 12700)
        w.height.setText("2")
        from gw_imposition.finishing import FinishingOperation
        panel.set_operations(tuple(FinishingOperation("strike_perf", x, 0, 10000)
                                   for x in (10000, 20000, 30000, 40000, 50000)))
        panel.apply()
        w.pool.waitForDone()
        self.app.processEvents()
        self.assertFalse(w.result.candidates)
        self.assertIn("maximum of 4", panel.sheet_status.text())

    def test_load_missing_source_can_relink(self):
        self.calculate()
        w = self.window
        source = str(w.pdf_path)
        path = Path(self.temp.name) / "saved.json"
        with patch("gw_imposition.gui.QFileDialog.getSaveFileName", return_value=(str(path), "")):
            w.save_json()
        data = json.loads(path.read_text())
        data["source_pdf"] = "missing.pdf"
        path.write_text(json.dumps(data))
        previous = w.result
        with patch("gw_imposition.gui.QFileDialog.getOpenFileName", return_value=("", "")):
            self.assertFalse(w.load_layout(path))
        self.assertEqual(w.result, previous)
        with patch("gw_imposition.gui.QFileDialog.getOpenFileName", return_value=(source, "")):
            self.assertTrue(w.load_layout(path))
        self.wait_pdf()
        w.pool.waitForDone()
        self.app.processEvents()
        self.assertIsNotNone(w.result)

    def test_logo_and_load_button_are_available(self):
        self.assertTrue(self.window.logo.renderer().isValid())
        self.assertEqual(self.window.load_button.text(), "Load layout…")

    def test_theme_switch_preserves_layout_and_preview(self):
        self.calculate()
        w = self.window
        w.show()
        self.app.processEvents()
        w.preview.zoom(3)
        transform = w.preview.transform()
        result, candidate = w.result, w.preview.candidate
        w.layer_checkboxes["bleed"].setChecked(False)
        for theme, background in (("Light", "#e8edf2"), ("Dark", "#0d151d")):
            w.theme_choice.setCurrentText(theme)
            self.assertEqual(w.preview.backgroundBrush().color().name(), background)
            self.assertEqual(w.result, result)
            self.assertEqual(w.preview.candidate, candidate)
            self.assertEqual(w.preview.transform(), transform)
            self.assertFalse(w.preview.layers["bleed"])
            self.assertTrue(w.logo.renderer().isValid())

    def wait_export(self):
        deadline = time.monotonic() + 10
        while self.window.exporter.process and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertIsNone(self.window.exporter.process)
        self.app.processEvents()

    def test_pdf_export_selected_alternative_ignores_preview_toggles(self):
        self.calculate()
        w = self.window
        w.table.selectRow(2)
        c = w.preview.candidate
        w.show_pdf_checkbox.setChecked(False)
        w.registration_panel.show_preview.setChecked(False)
        w.view_mode.setCurrentText("Card")
        for checkbox in w.layer_checkboxes.values():
            checkbox.setChecked(False)
        destination = Path(self.temp.name) / "export.pdf"
        self.assertTrue(w.start_pdf_export(destination, "lines"))
        self.assertFalse(w.centralWidget().isEnabled())
        self.wait_export()
        self.assertTrue(w.centralWidget().isEnabled())
        with pymupdf.open(destination) as pdf:
            self.assertEqual(len(pdf[0].get_drawings()), len(c.cuts)+len(c.slitters)+len(w.preview.registration_marks))
        self.assertIn(str(destination), w.statusBar().currentMessage())

    def test_registration_tab_preview_settings_and_saved_layout(self):
        self.calculate()
        w = self.window
        panel = w.registration_panel
        self.assertEqual(w.results_tabs.tabText(2), "Registration marks")
        candidate = w.preview.candidate
        marks = lambda: [i for i in w.preview.scene().items() if i.data(0) == "registration"]
        self.assertTrue(marks())
        w.preview.zoom(2)
        transform = w.preview.transform()
        panel.show_preview.setChecked(False)
        self.assertFalse(marks())

        self.assertEqual(w.preview.transform(), transform)
        self.assertEqual(w.preview.candidate, candidate)
        self.assertTrue(panel.settings().enabled)
        panel.show_preview.setChecked(True)
        panel.length.setValue(.2)
        panel.thickness.setValue(.03)
        self.assertEqual(w.preview.candidate, candidate)
        self.assertEqual(w.preview.transform(), transform)
        path = Path(self.temp.name) / "registration-layout.json"
        with patch("gw_imposition.gui.QFileDialog.getSaveFileName", return_value=(str(path), "")):
            w.save_json()
        expected = panel.settings()
        panel.enabled.setChecked(False)
        self.assertFalse(marks())
        self.assertTrue(w.load_layout(path))
        self.wait_pdf()
        w.pool.waitForDone()
        self.app.processEvents()
        self.assertEqual(panel.settings(), expected)
        self.assertTrue(marks())
        data = json.loads(path.read_text())
        del data["registration"]
        path.write_text(json.dumps(data))
        self.assertTrue(w.load_layout(path))
        self.wait_pdf()
        w.pool.waitForDone()
        self.app.processEvents()
        self.assertFalse(panel.settings().enabled)
        self.assertFalse(marks())

    def test_machine_capabilities_and_zero_gutter_load(self):
        from gw_imposition.finishing import FinishingOperation
        w = self.window
        w.machine.setCurrentIndex(w.machine.findData("pt_33sc"))
        self.assertIn("PT 33SC", w.machine_panel.title.text())
        half = w.finishing_panel.preset.findData("half")
        self.assertFalse(w.finishing_panel.preset.model().item(half).isEnabled())
        w.finishing_operations = (FinishingOperation("crease", 25400),)
        self.calculate()
        self.assertFalse(w.result.candidates)
        self.assertIn("does not support crease", w.messages.toPlainText())
        w.finishing_operations = ()
        from dataclasses import replace
        from gw_imposition.models import Margins
        # A synthetic borderless press setup permits the confirmed zero-trim boundary.
        profile = replace(w.current_machine_profile(), press_margins=Margins(0, 0, 0, 0))
        w.loaded_profiles["test_borderless"] = profile
        w.machine.addItem("Test borderless", "test_borderless")
        w.machine.setCurrentIndex(w.machine.findData("test_borderless"))
        source = Path(self.temp.name) / "four-inch.pdf"
        with pymupdf.open() as pdf:
            pdf.new_page(width=288, height=162)
            pdf.save(source)
        w.load_pdf(source)
        self.wait_pdf()
        w.width.setText("4")
        w.height.setText("2.25")
        w.gutter.setText("0")
        self.calculate()
        self.assertTrue(w.job.shared_cut)
        self.assertTrue(w.result.candidates)
        path = Path(self.temp.name) / "zero-gutter.json"
        with patch("gw_imposition.gui.QFileDialog.getSaveFileName", return_value=(str(path), "")):
            w.save_json()
        self.assertTrue(w.load_layout(path))
        self.wait_pdf()
        w.pool.waitForDone()
        self.app.processEvents()
        self.assertTrue(w.job.shared_cut)
        self.assertEqual(w.profile.capabilities.max_side_trim_um, 3000)

    def test_cancel_export_and_worker_failure_preserve_destination(self):
        self.calculate()
        w = self.window
        destination = Path(self.temp.name) / "existing.pdf"
        destination.write_bytes(b"original destination")
        w.start_pdf_export(destination, "combined")
        w.exporter.cancel()
        self.wait_export()
        self.assertEqual(destination.read_bytes(), b"original destination")
        self.assertFalse(list(Path(self.temp.name).glob(".gw-export-*")))
        self.assertIsNotNone(w.result)
        w.start_pdf_export(destination, "invalid-mode")
        self.wait_export()
        self.assertEqual(destination.read_bytes(), b"original destination")
        self.assertTrue(w.centralWidget().isEnabled())
        self.assertIn("Unknown PDF export", w.messages.toPlainText())

    def test_export_save_dialog_cancel_does_not_start_worker(self):
        from PySide6.QtWidgets import QDialog
        self.calculate()
        with patch("gw_imposition.gui.QDialog.exec", return_value=QDialog.DialogCode.Accepted), \
             patch("gw_imposition.gui.QFileDialog.getSaveFileName", return_value=("", "")):
            self.window.choose_pdf_export()
        self.assertIsNone(self.window.exporter.process)

    def test_barcode_reader_visibility_and_preview_validation(self):
        w = self.window
        panel = w.registration_panel
        for index in range(w.machine.count()):
            w.machine.setCurrentIndex(index)
            self.assertEqual(not panel.barcode_group.isHidden(), w.machine.currentData() in ('pt_8336scc_multi', 'pt_9375scc_supercut'))
        w.machine.setCurrentIndex(w.machine.findData('pt_8336scc_multi'))
        self.calculate()
        panel.barcode_enabled.setChecked(True)
        self.assertFalse(w.pdf_export_button.isEnabled())
        panel.barcode_value.setText('000123')
        self.assertTrue(w.pdf_export_button.isEnabled())
        self.assertIsNotNone(w.preview.barcode)
        self.assertTrue(any(item.data(0) == 'barcode' for item in w.preview.scene().items()))
        w.preview.scale(2, 2)
        transform = w.preview.transform()
        panel.show_preview.setChecked(False)
        self.assertEqual(w.preview.transform(), transform)
        self.assertIsNotNone(w.preview.barcode)
        w.machine.setCurrentIndex(w.machine.findData('pt_335scc_b_multi'))
        self.assertFalse(panel.settings().barcode.enabled)
        self.assertIsNone(w.preview.barcode)
