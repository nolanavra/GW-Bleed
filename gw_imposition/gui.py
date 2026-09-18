"""Phase-three operator desktop. Run with python -m gw_imposition.gui."""

# “All magic has a price, though some of it accepts store credit.”
from dataclasses import asdict
from decimal import Decimal
import json
from pathlib import Path
import sys

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Qt, QTimer
from PySide6.QtGui import QFont, QPalette
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget, QHeaderView,
    QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QProgressDialog, QGridLayout, QTabWidget,
)

from .layout_engine import calculate
from .layout_storage import read_layout
from .finishing_panel import FinishingPanel
from .registration_panel import RegistrationPanel
from .registration import build_registration
from .barcodes import build_barcode
from .machine_panel import MachinePanel
from .finishing import KINDS
from .pdf_export import MODES
from .export_controller import ExportController
from .theme import STYLE, LIGHT_STYLE, dark_palette
from .models import Job
from .pdf_loader import PdfLoader, source_signature
from .preview import SheetPreview
from .profiles import BUNDLED_PROFILES, DEFAULT_MACHINE_ID, load_profile
from .units import to_um, inches


class WorkerSignals(QObject):
    finished = Signal(int, object, str)


class CalculationWorker(QRunnable):
    def __init__(self, revision, job, profile):
        super().__init__()
        self.revision, self.job, self.profile = revision, job, profile
        self.signals = WorkerSignals()

    def run(self):
        try:
            result = calculate(self.job, self.profile)
            self.signals.finished.emit(self.revision, result, "")
        except Exception as exc:
            self.signals.finished.emit(self.revision, None, str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GW Bleed")
        self.light_palette = QPalette(self.palette())
        self.setStyleSheet(STYLE)
        self.setPalette(dark_palette())
        self.resize(1480, 900)
        self.revision = 0
        self.result = self.job = self.profile = None
        self.pdf_path = None
        self.pdf_pages = ()
        self.pdf_busy = False
        self.pdf_token = 0
        self.pdf_signature = None
        self.loader = PdfLoader(self)
        self.loader.ready.connect(self.pdf_ready)
        self.loader.failed.connect(self.pdf_failed)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.worker = None
        self.loaded_profiles = {}
        self.pending_layout = None
        self.restore_selection = None
        self.finishing_operations = ()
        self.exporter = ExportController(self)
        self.exporter.finished.connect(self.pdf_export_finished)
        self.export_progress = None

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        header = QHBoxLayout()
        self.logo = QSvgWidget(str(Path(__file__).parent / "resources" / "graphic_whizard_logo.svg"))
        self.logo.setFixedSize(156, 100)
        self.logo.setAccessibleName("Graphic Whizard logo")
        self.logo.setAutoFillBackground(False)
        self.logo.setStyleSheet("background: transparent;")
        header.addWidget(self.logo)
        heading = QVBoxLayout()
        title = QLabel("GW Bleed")
        self.title_label = title
        title.setStyleSheet("font-size: 26px; font-weight: 600; color: #B3D485;")
        heading.addWidget(title)
        heading.addWidget(QLabel("Single-sheet layouts  •  Maximum 3 columns  •  12 / 13-inch feed edge"))
        header.addLayout(heading)
        header.addStretch()
        header.addWidget(QLabel("Theme"))
        self.theme_choice = QComboBox()
        self.theme_choice.addItems(["Dark", "Light"])
        self.theme_choice.setAccessibleName("Color theme")
        self.theme_choice.currentTextChanged.connect(self.apply_theme)
        header.addWidget(self.theme_choice)
        outer.addLayout(header)
        splitter = QSplitter()
        outer.addWidget(splitter, 1)
        inputs = QWidget()
        inputs.setMinimumWidth(280)
        inputs.setMaximumWidth(380)
        left = QVBoxLayout(inputs)
        splitter.addWidget(inputs)

        artwork = QGroupBox("Artwork")
        a = QVBoxLayout(artwork)
        choose = QPushButton("Select PDF…")
        choose.clicked.connect(self.select_pdf)
        a.addWidget(choose)
        self.pdf_label = QLabel("Select a PDF to calculate bleed and layout.")
        self.pdf_label.setWordWrap(True)
        a.addWidget(self.pdf_label)
        self.page_choice = QComboBox()
        self.page_choice.setEnabled(False)
        self.page_choice.currentIndexChanged.connect(self.page_changed)
        a.addWidget(self.page_choice)
        self.page_info = QLabel("Bleed is calculated from PDF page size minus finished card size, with centered trim.")
        self.page_info.setWordWrap(True)
        a.addWidget(self.page_info)
        left.addWidget(artwork)

        settings = QGroupBox("Layout settings")
        form = QFormLayout(settings)
        self.width = QLineEdit("3.5")
        self.height = QLineEdit("2")
        self.gutter = QLineEdit()
        self.gutter.setPlaceholderText("Auto: allow both bleeds")
        for label, field in (("Finished width (in)", self.width),
                             ("Finished height (in)", self.height),
                             ("Gutter (in)", self.gutter)):
            form.addRow(label, field)
            field.textChanged.connect(self.invalidate)
        self.bleed_info = QLabel("Select a PDF to calculate bleed.")
        self.bleed_info.setWordWrap(True)
        form.addRow("Calculated bleed", self.bleed_info)
        self.machine = QComboBox()
        for machine_id, path in BUNDLED_PROFILES.items():
            self.machine.addItem(load_profile(path).name.split(" - ")[0], machine_id)
        self.machine.setCurrentIndex(self.machine.findData(DEFAULT_MACHINE_ID))
        self.machine.currentIndexChanged.connect(self.machine_changed)
        form.addRow("Machine", self.machine)
        left.addWidget(settings)
        self.calculate_button = QPushButton("Calculate layout")
        self.calculate_button.setObjectName("calculate")
        self.calculate_button.clicked.connect(self.calculate_layout)
        left.addWidget(self.calculate_button)
        self.export_button = QPushButton("Save layout JSON…")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.save_json)
        left.addWidget(self.export_button)
        self.load_button = QPushButton("Load layout…")
        self.load_button.clicked.connect(self.choose_layout)
        left.addWidget(self.load_button)
        self.pdf_export_button = QPushButton("Export PDF…")
        self.pdf_export_button.setEnabled(False)
        self.pdf_export_button.clicked.connect(self.choose_pdf_export)
        left.addWidget(self.pdf_export_button)
        note = QLabel("Machine capabilities come from the supplied spreadsheet. Setup margins remain provisional; see Machine specs.\n\nLayout sits at the bottom usable boundary, centered horizontally.")
        note.setWordWrap(True)
        left.addWidget(note)
        left.addStretch()

        output = QWidget()
        right = QVBoxLayout(output)
        self.summary = QLabel("Enter finished dimensions and calculate a layout.")
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("font-size: 17px; font-weight: 600;")
        right.addWidget(self.summary)
        self.preview = SheetPreview()
        navigation = QHBoxLayout()
        self.view_mode = QComboBox()
        self.view_mode.addItems(["Sheet", "Card"])
        self.view_mode.currentTextChanged.connect(self.preview.set_mode)
        navigation.addWidget(self.view_mode)
        navigation.addStretch()
        for label, action in (("Zoom +", lambda: self.preview.zoom(1.25)),
                              ("Zoom −", lambda: self.preview.zoom(.8)),
                              ("Fit", self.preview.fit_sheet)):
            button = QPushButton(label)
            button.clicked.connect(action)
            navigation.addWidget(button)
        right.addLayout(navigation)
        right.addWidget(self.preview, 3)
        self.show_pdf_checkbox = QCheckBox("Show PDF in preview")
        self.show_pdf_checkbox.setChecked(True)
        self.show_pdf_checkbox.toggled.connect(self.preview.set_show_pdf)
        overlays = QGridLayout()
        overlays.addWidget(self.show_pdf_checkbox, 0, 0, 1, 2)
        self.layer_checkboxes = {}
        for index, (key, label) in enumerate((("cuts", "Cuts"), ("slitters", "Slitters"),
                           ("bleed", "Bleed"), ("bounds", "Machine bounds"))):
            checkbox = QCheckBox(label)
            checkbox.setChecked(True)
            checkbox.toggled.connect(lambda checked, name=key: self.preview.set_layer(name, checked))
            self.layer_checkboxes[key] = checkbox
            overlays.addWidget(checkbox, 1, index)
        right.addLayout(overlays)
        self.finishing_checkbox = QCheckBox("Show creases and perforations")
        self.finishing_checkbox.setChecked(True)
        self.finishing_checkbox.toggled.connect(lambda checked: self.preview.set_layer("finishing", checked))
        overlays.addWidget(self.finishing_checkbox, 0, 2, 1, 2)
        tools = QHBoxLayout()
        legend = QLabel("Red: cuts  •  Purple: slitters  •  Blue dashed: bleed\nOrange: creases  •  Green: cross perfs  •  Cyan: strike perfs  •  Pink: rotary perfs")
        tools.addWidget(legend)
        right.addLayout(tools)
        self.details = QLabel("Select a layout to see placement distances.")
        self.details.setWordWrap(True)
        self.details.setMinimumHeight(self.details.fontMetrics().lineSpacing() * 4)
        right.addWidget(self.details)
        results_panel = QWidget()
        results_panel.setMinimumWidth(380)
        results = QVBoxLayout(results_panel)
        results_title = QLabel("Stock layouts")
        results_title.setStyleSheet("font-size: 17px; font-weight: 600;")
        results.addWidget(results_title)
        results.addWidget(QLabel("Ordered by pieces per sheet, then stock"))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Stock", "Columns\n× rows", "Pieces /\nsheet", "Rotation", "Trim\nwaste"])
        self.table.setMinimumHeight(350)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.select_candidate)
        results.addWidget(self.table, 1)
        results.addWidget(QLabel("Cuts from leading edge"))
        self.cut_distances = QTableWidget(0, 2)
        self.cut_distances.setHorizontalHeaderLabels(["Cut", "Distance from leading edge (in)"])
        self.cut_distances.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.cut_distances.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.cut_distances.verticalHeader().hide()
        self.cut_distances.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.cut_distances.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.cut_distances.setMinimumHeight(130)
        self.cut_distances.setMaximumHeight(180)
        self.cut_distances.setToolTip("Horizontal cuts measured from the paper's leading edge (y = 0), including trim and gutter cuts.")
        results.addWidget(self.cut_distances)
        self.messages = QTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setMaximumHeight(150)
        results.addWidget(QLabel("Layout notes"))
        results.addWidget(self.messages)
        self.results_tabs = QTabWidget()
        self.results_tabs.setMinimumWidth(400)
        self.results_tabs.addTab(results_panel, "Stock layouts")
        self.finishing_panel = FinishingPanel(self.finished_dimensions)
        self.finishing_panel.applied.connect(self.apply_finishing)
        self.results_tabs.addTab(self.finishing_panel, "Finishing")
        self.registration_panel = RegistrationPanel()
        self.registration_panel.changed.connect(self.update_registration)
        self.registration_panel.visibility_changed.connect(self.preview.set_show_registration)
        self.results_tabs.addTab(self.registration_panel, "Registration marks")
        self.machine_panel = MachinePanel()
        self.results_tabs.addTab(self.machine_panel, "Machine specs")
        self.width.textChanged.connect(self.finishing_panel.refresh)
        self.height.textChanged.connect(self.finishing_panel.refresh)
        splitter.addWidget(output)
        splitter.addWidget(self.results_tabs)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 2)
        splitter.setSizes([330, 650, 480])
        self.statusBar().showMessage("Ready")
        self.source_timer = QTimer(self)
        self.source_timer.setInterval(1000)
        self.source_timer.timeout.connect(self.check_source)
        self.source_timer.start()
        self.machine_changed()

    def current_machine_profile(self):
        machine_id = self.machine.currentData()
        return (self.loaded_profiles[machine_id] if machine_id in self.loaded_profiles
                else load_profile(BUNDLED_PROFILES[machine_id]))

    def machine_changed(self, *_):
        self.invalidate()
        profile = self.current_machine_profile()
        self.machine_panel.set_profile(profile)
        self.registration_panel.set_profile(profile)
        self.finishing_panel.set_profile(profile)
        self.gutter.setToolTip("Zero gutter requires zero PDF bleed. Fixed middle gutter: 0 or 5–15 mm; side trim: 0–3 mm per paper edge."
                              if profile.capabilities and profile.capabilities.gutter_mode == "fixed" else
                              "Trim-to-trim gap; leave blank to accommodate both bleeds. See Machine specs for provisional limits.")

    def apply_theme(self, name):
        dark = name == "Dark"
        self.setPalette(dark_palette() if dark else self.light_palette)
        self.setStyleSheet(STYLE if dark else LIGHT_STYLE)
        color = "#B3D485" if dark else "#004B7F"
        self.title_label.setStyleSheet(f"font-size: 26px; font-weight: 600; color: {color};")
        self.preview.set_dark_mode(dark)

    def invalidate(self, *_):
        self.revision += 1
        self.result = None
        self.export_button.setEnabled(False)
        self.pdf_export_button.setEnabled(False)
        self.table.setRowCount(0)
        self.cut_distances.setRowCount(0)
        self.preview.show_candidate(None)
        self.preview.set_registration(())
        self.preview.set_barcode(None)
        self.registration_panel.barcode_status.clear()
        self.registration_panel.show_result()
        self.summary.setText("Inputs changed — calculate to update the layout.")
        self.details.setText("Select a layout to see placement distances.")
        self.messages.clear()
        self.finishing_panel.sheet_status.setText("Calculate a sheet to check repeated tool positions and strike coverage.")
        self.update_bleed()

    def get_bleed(self):
        index = self.page_choice.currentIndex()
        if not 0 <= index < len(self.pdf_pages):
            raise ValueError("Select a PDF to calculate bleed and layout.")
        return self.pdf_pages[index].derive_bleed(to_um(self.width.text()), to_um(self.height.text()))

    def update_bleed(self):
        try:
            bx, by = self.get_bleed()
            self.bleed_info.setText(f"Left / right: {inches(bx)} in\nTop / bottom: {inches(by)} in")
            width, height = to_um(self.width.text()), to_um(self.height.text())
            self.preview.set_card(width, height, bx, by) if width and height else self.preview.set_card()
        except ValueError as exc:
            self.bleed_info.setText(str(exc))
            self.preview.set_card()

    def select_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select artwork", "", "PDF files (*.pdf)")
        if path:
            self.load_pdf(path)

    def load_pdf(self, path, index=0):
        self.pdf_path, self.pdf_pages = Path(path), ()
        self.pdf_label.setText(self.pdf_path.name)
        self.pdf_label.setToolTip(str(self.pdf_path))
        self.page_choice.blockSignals(True)
        self.page_choice.clear()
        self.page_choice.setEnabled(False)
        self.page_choice.blockSignals(False)
        self.request_pdf(index)
        return True

    def page_changed(self, *_):
        if self.pdf_path and self.page_choice.currentIndex() >= 0:
            self.request_pdf(self.page_choice.currentIndex())

    def request_pdf(self, index):
        self.pdf_busy = True
        self.pdf_pages = ()
        self.invalidate()
        self.preview.set_artwork(None)
        self.calculate_button.setEnabled(False)
        self.page_info.setText("Loading PDF preview…")
        self.statusBar().showMessage("Loading PDF preview…")
        self.pdf_token = self.loader.request(self.pdf_path, index)

    def pdf_ready(self, token, pages, index, png):
        if token != self.pdf_token:
            return
        self.pdf_busy = False
        self.pdf_signature = self.loader.signature
        self.pdf_pages = pages
        self.page_choice.blockSignals(True)
        self.page_choice.clear()
        self.page_choice.addItems([f"Page {n + 1}" for n in range(len(pages))])
        self.page_choice.setCurrentIndex(index)
        self.page_choice.setEnabled(True)
        self.page_choice.blockSignals(False)
        self.preview.set_artwork(png)
        self.update_bleed()
        p = pages[index]
        self.page_info.setText(f"Displayed page: {p.width_points/72:.3f} × {p.height_points/72:.3f} in.\n"
                               "CropBox dimensions; centered trim. Artwork coverage is not verified.")
        self.calculate_button.setEnabled(True)
        self.statusBar().showMessage("PDF preview ready")
        pending = self.pending_layout
        self.pending_layout = None
        if pending and pending[0] == token and pending[1] == self.revision:
            if pending[2] != index:
                self.messages.setPlainText("The saved PDF page is no longer available. Choose a page and recalculate.")
                return
            self.calculate_layout()
            self.restore_selection = (self.revision, pending[3])

    def pdf_failed(self, token, error):
        if token != self.pdf_token:
            return
        self.pdf_busy = False
        self.pending_layout = None
        self.pdf_signature = None
        self.pdf_pages = ()
        self.preview.set_artwork(None)
        self.invalidate()
        self.page_info.setText("PDF preview unavailable. Select the file again to retry.")
        self.messages.setPlainText(error)
        self.calculate_button.setEnabled(True)
        self.statusBar().showMessage("PDF load failed")

    def check_source(self):
        if self.exporter.process:
            return
        if self.pdf_path is None or self.pdf_signature is None or self.pdf_busy:
            return
        try:
            changed = source_signature(self.pdf_path) != self.pdf_signature
        except OSError:
            changed = True
        if changed:
            self.load_pdf(self.pdf_path, max(0, self.page_choice.currentIndex()))

    def finished_dimensions(self):
        return to_um(self.width.text()), to_um(self.height.text())

    def update_registration(self):
        row = self.table.currentRow()
        if self.result is None or not 0 <= row < len(self.result.candidates):
            self.preview.set_registration(())
            self.registration_panel.show_result()
            self.preview.set_barcode(None)
            return
        candidate = self.result.candidates[row]
        registration = build_registration(candidate, self.profile, self.registration_panel.settings())
        self.preview.set_registration(registration.marks)
        self.registration_panel.show_result(candidate, self.profile, registration)
        try:
            barcode = build_barcode(candidate, self.profile, self.registration_panel.settings().barcode, registration.marks)
        except ValueError as exc:
            self.preview.set_barcode(None)
            self.registration_panel.barcode_status.setText(str(exc))
            self.pdf_export_button.setEnabled(False)
            return
        self.preview.set_barcode(barcode)
        self.registration_panel.barcode_status.setText(
            f"Barcode ready: left {barcode.bounds.x_um/25400:.3f} in, top {barcode.bounds.y_um/25400:.3f} in (including quiet zone)."
            if barcode else "Barcode generation is off.")
        self.pdf_export_button.setEnabled(not self.pdf_busy)

    def apply_finishing(self, operations):
        self.finishing_operations = tuple(operations)
        self.invalidate()
        if self.pdf_pages and not self.pdf_busy:
            self.calculate_layout()

    def calculate_layout(self):
        self.check_source()
        if self.pdf_busy:
            return
        self.invalidate()
        try:
            self.profile = self.current_machine_profile()
            bleed_x, bleed_y = self.get_bleed()
            if self.gutter.text().strip():
                gutter = to_um(self.gutter.text())
            else:
                minimum, step = self.profile.minimum_gutter_um, self.profile.gutter_increment_um
                gutter = minimum + max(0, (max(1, 2*max(bleed_x, bleed_y)) - minimum + step - 1) // step) * step
            self.job = Job(to_um(self.width.text()), to_um(self.height.text()), bleed_x, gutter,
                           bleed_y_um=bleed_y, finishing=self.finishing_operations, shared_cut=gutter == 0)
        except (ValueError, OSError) as exc:
            self.messages.setPlainText(str(exc))
            return
        self.calculate_button.setEnabled(False)
        self.statusBar().showMessage("Calculating…")
        self.worker = CalculationWorker(self.revision, self.job, self.profile)
        self.worker.signals.finished.connect(self.calculation_finished)
        self.pool.start(self.worker)

    def calculation_finished(self, revision, result, error):
        self.calculate_button.setEnabled(not self.pdf_busy)
        if revision != self.revision:
            return
        self.statusBar().showMessage("Ready")
        if error:
            self.messages.setPlainText(error)
            self.finishing_panel.sheet_status.setText(error)
            return
        self.result = result
        self.messages.setPlainText("\n".join(result.warnings) + "\n" + "\n".join(
            f"{r.stock_id}, {r.rotation}°: {r.message}" for r in result.rejections))
        self.table.setRowCount(len(result.candidates))
        for row, c in enumerate(result.candidates):
            waste = 100 * c.waste_area_um2 / (c.sheet_width_um * c.sheet_height_um)
            for col, value in enumerate((c.stock_id, f"{c.columns} × {c.rows}",
                                         str(c.yield_per_sheet), f"{c.rotation}°", f"{waste:.1f}%")):
                self.table.setItem(row, col, QTableWidgetItem(value))
        if result.candidates:
            row = 0
            restore = self.restore_selection
            self.restore_selection = None
            restored_messages = []
            if restore and restore[0] == revision:
                selected = next((i for i, c in enumerate(result.candidates)
                                 if (c.stock_id, c.rotation, c.rows, c.columns) == restore[1]), None)
                if selected is None:
                    restored_messages.append("Saved arrangement is no longer valid; showing the current recommendation.")
                else:
                    row = selected
                restored_messages.append("Layout loaded and recalculated using the saved machine profile and current PDF.")
            self.table.selectRow(row)
            for message in restored_messages:
                self.messages.append(message)
            self.export_button.setEnabled(True)
            self.update_registration()
        else:
            self.summary.setText("No valid layout. Review dimensions, bleed, gutter and machine settings.")
            side_reasons = list(dict.fromkeys(r.message for r in result.rejections
                                if r.code in ("side_trim_margin_conflict", "side_trim_limit")))
            if side_reasons:
                self.summary.setText("No valid layout: side trim exceeds the machine limit. See layout notes.")
                self.messages.setPlainText("\n".join(side_reasons) + "\n\n" + self.messages.toPlainText())
            reasons = list(dict.fromkeys(r.message for r in result.rejections if r.code in ("finishing_rule", "machine_finishing")))
            self.finishing_panel.sheet_status.setText("No valid sheet layout. " + (reasons[0] if reasons else "Review card dimensions and machine settings."))

    def select_candidate(self):
        row = self.table.currentRow()
        if self.result is None or not 0 <= row < len(self.result.candidates):
            return
        c = self.result.candidates[row]
        self.finishing_panel.sheet_status.setText("\n".join(c.finishing_warnings) if c.finishing_warnings else
            f"Selected sheet: {c.stock_id}, {c.yield_per_sheet} pieces. Finishing geometry is valid.")
        self.messages.setPlainText("\n".join((*self.result.warnings, *c.finishing_warnings)) + "\n" +
            "\n".join(f"{r.stock_id}, {r.rotation}°: {r.message}" for r in self.result.rejections))
        for mark in c.finishing:
            if mark.kind in ("crease", "cross_perf"):
                text = f"{KINDS[mark.kind]}: {inches(mark.y1_um)} in from leading edge"
            else:
                text = (f"{KINDS[mark.kind]}: x={inches(mark.x1_um)} in from left; "
                        f"start/end={inches(mark.y1_um)} / {inches(mark.y2_um)} in from leading edge")
            self.messages.append(text)
        self.cut_distances.setRowCount(len(c.cut_y_um))
        for index, distance in enumerate(c.cut_y_um):
            self.cut_distances.setItem(index, 0, QTableWidgetItem(str(index + 1)))
            self.cut_distances.setItem(index, 1, QTableWidgetItem(inches(distance)))
        self.preview.show_candidate(c)
        self.update_registration()
        self.summary.setText(f"{'Recommended' if row == 0 else 'Alternative'}: {c.stock_id}  •  "
                             f"{c.columns} × {c.rows}  •  {c.yield_per_sheet} pieces per sheet\n"
                             f"Feed edge: {inches(c.sheet_width_um)} in  •  Gutter: {inches(self.job.gutter_um)} in")
        first, last = c.bleed_regions[0], c.bleed_regions[-1]
        p = c.placements[0]
        self.details.setText(
            f"Artwork rotation: {c.rotation}° | Bleed L/R: {inches(p.x_um-first.x_um)} in, "
            f"T/B: {inches(p.y_um-first.y_um)} in\n"
            f"Outer bleed to sheet edge — Left: {inches(first.x_um)} in | "
            f"Right: {inches(c.sheet_width_um-last.x_um-last.width_um)} in | "
            f"Top: {inches(first.y_um)} in | Bottom: {inches(c.sheet_height_um-last.y_um-last.height_um)} in")

    def choose_layout(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load layout", "", "GW Bleed layouts (*.json)")
        if path:
            self.load_layout(path)

    def load_layout(self, path):
        try:
            job, profile, source, page, selection, registration = read_layout(path)
            if source is None or not source.is_file():
                replacement, _ = QFileDialog.getOpenFileName(
                    self, "Locate PDF for saved layout", str(Path(path).parent), "PDF files (*.pdf)")
                if not replacement:
                    return False
                source = Path(replacement)
            key = "saved_profile"
            self.loaded_profiles[key] = profile
            index = self.machine.findData(key)
            label = f"{profile.name.split(' - ')[0]} (saved v{profile.version})"
            if index < 0:
                self.machine.addItem(label, key)
                index = self.machine.count() - 1
            else:
                self.machine.setItemText(index, label)
            self.machine.setCurrentIndex(index)
            self.machine_changed()
            self.finishing_operations = job.finishing
            self.width.setText(str(Decimal(job.width_um) / 25400))
            self.height.setText(str(Decimal(job.height_um) / 25400))
            self.finishing_panel.set_operations(job.finishing)
            self.registration_panel.set_settings(registration)
            self.gutter.setText(str(Decimal(job.gutter_um) / 25400))
            self.restore_selection = None
            self.load_pdf(source, page)
            self.pending_layout = (self.pdf_token, self.revision, page, selection)
            return True
        except (ValueError, OSError) as exc:
            self.messages.setPlainText(str(exc))
            return False

    def choose_pdf_export(self):
        self.check_source()
        if self.result is None or self.pdf_busy:
            return
        row = self.table.currentRow()
        if row < 0:
            return
        candidate = self.result.candidates[row]
        dialog = QDialog(self)
        dialog.setWindowTitle("Export PDF")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"{candidate.stock_id} | {candidate.columns} × {candidate.rows} | "
                                f"{candidate.yield_per_sheet} pieces per sheet"))
        modes = QComboBox()
        for key, label in MODES.items():
            modes.addItem(label, key)
        layout.addWidget(modes)
        layout.addWidget(QLabel("Black 0.25-point finishing guides: solid cuts/slitters, dash-dot creases, dashed perfs.\nPreview toggles do not affect export."))
        registration = build_registration(candidate, self.profile, self.registration_panel.settings())
        layout.addWidget(QLabel(f"Registration marks: {len(registration.marks)}. Page cropped to {candidate.stock_id} stock."))
        layout.addWidget(QLabel("Enabled registration marks are added to all export modes, including artwork only."))
        barcode_settings = self.registration_panel.settings().barcode
        if barcode_settings.enabled:
            note = QLabel(f"Barcode: {barcode_settings.symbology.upper()} — {barcode_settings.value}")
            note.setTextFormat(Qt.TextFormat.PlainText)
            note.setWordWrap(True)
            layout.addWidget(note)
        if registration.warnings:
            notice = QLabel("\n".join(registration.warnings))
            notice.setWordWrap(True)
            layout.addWidget(notice)
        if candidate.finishing_warnings:
            warning = QLabel("\n".join(candidate.finishing_warnings))
            warning.setWordWrap(True)
            layout.addWidget(warning)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        mode = modes.currentData()
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF",
            f"{self.pdf_path.stem}_{candidate.stock_id}_{mode}.pdf", "PDF files (*.pdf)")
        if path:
            self.start_pdf_export(path, mode)

    def start_pdf_export(self, path, mode):
        self.check_source()
        if self.result is None or self.pdf_busy or self.exporter.process:
            return False
        row = self.table.currentRow()
        if row < 0:
            return False
        request = dict(source=str(self.pdf_path.resolve()), page=self.page_choice.currentIndex(),
                       destination=str(Path(path).resolve()), mode=mode,
                       signature=self.pdf_signature, job=asdict(self.job), profile=asdict(self.profile),
                       candidate=asdict(self.result.candidates[row]),
                       registration=asdict(self.registration_panel.settings()))
        try:
            self.exporter.start(request)
        except (ValueError, OSError) as exc:
            self.messages.setPlainText(str(exc))
            return False
        self.centralWidget().setEnabled(False)
        self.export_progress = QProgressDialog("Exporting and verifying PDF…", "Cancel", 0, 0, self)
        self.export_progress.setWindowTitle("GW Bleed — PDF export")
        self.export_progress.setMinimumDuration(0)
        self.export_progress.canceled.connect(self.exporter.cancel)
        self.export_progress.show()
        self.statusBar().showMessage("Exporting PDF…")
        return True

    def pdf_export_finished(self, destination, error):
        self.centralWidget().setEnabled(True)
        if self.export_progress:
            self.export_progress.close()
            self.export_progress.deleteLater()
            self.export_progress = None
        message = f"Saved PDF: {destination}" if destination else error
        self.statusBar().showMessage(message)
        self.messages.append(message)

    def save_json(self):
        self.check_source()
        if self.result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save layout", "layout.json", "JSON files (*.json)")
        if not path:
            return
        try:
            payload = {"schema_version": 4, "units": "um", "job": asdict(self.job),
                       "profile_snapshot": asdict(self.profile), "calculation": asdict(self.result),
                       "selected_candidate_index": self.table.currentRow(),
                       "source_pdf": str(self.pdf_path) if self.pdf_path else None,
                       "source_page_index": self.page_choice.currentIndex() if self.pdf_path else None}
            payload["registration"] = asdict(self.registration_panel.settings())
            Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            self.statusBar().showMessage(f"Saved {path}")
        except OSError as exc:
            self.messages.setPlainText(f"Unable to save layout: {exc}")

    def closeEvent(self, event):
        self.exporter.close()
        self.source_timer.stop()
        self.loader.close()
        self.pool.waitForDone()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("GW Bleed")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
