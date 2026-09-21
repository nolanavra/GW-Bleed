"""Phase-three operator desktop. Run with python -m gw_imposition.gui."""

# “All magic has a price, though some of it accepts store credit.”
from dataclasses import asdict, replace
from decimal import Decimal
import json
from pathlib import Path
import sys

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Qt, QTimer, QStandardPaths
from PySide6.QtGui import QFont, QPalette, QPixmap, QTransform
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget, QHeaderView,
    QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QProgressDialog, QGridLayout, QTabWidget, QStackedWidget, QMessageBox, QScrollArea,
)

from .layout_engine import calculate
from .layout_storage import read_layout
from .machine_guide import ADAPTERS, MachineSetup, build_guide
from .machine_guide_ui import MachineGuideDialog
from .finishing_panel import FinishingPanel
from .accessory_panel import AccessoryPanel
from .accessories import default_accessories
from .registration_panel import RegistrationPanel
from .registration import build_registration
from .storage_io import atomic_json, read_json
from .paper_stocks import PaperStock, automatic_crease_depth, crease_depth_is_placeholder, standard_paper_stocks, stock_fits_machine
from .trimposer_export import trimposer_ini, save_trimposer_ini
from .barcodes import build_barcode, BarcodePlacementError
from .machine_panel import MachinePanel
from .finishing import KINDS
from .pdf_export import MODES
from .back_artwork import BackArtwork
from .artwork import back_candidate
from .artwork_library import ArtworkLibrary
from .export_controller import ExportController
from .theme import STYLE, LIGHT_STYLE, dark_palette
from .models import Job, Margins
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
        self.machine_setup = MachineSetup()
        self.guide = None
        self.result = self.job = self.profile = None
        self.pdf_path = None
        self.pdf_pages = ()
        self.pdf_busy = False
        self.pdf_token = 0
        self._barcode_warning_key = None
        self.pdf_signature = None
        self.front_png = None
        self.front_orientation = self.back_orientation = 0
        self.size_overridden = False
        self.suggestion_applied = False
        self.assignment_history = []
        self.source_review_required = False
        self.review_sources = set()
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
        self.finishing_rotation = 0
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
        self.bleed_logo = QLabel()
        self.bleed_logo.setAccessibleName('GW Bleed logo')
        self.bleed_logo.setPixmap(QPixmap(str(Path(__file__).parent/'resources'/'GW BLEED LOGO WIDE.png')).scaled(330,100,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        header.addWidget(self.bleed_logo)
        header.addStretch()
        self.back_to_layout = QPushButton('← Back to layout view')
        self.back_to_layout.setVisible(False)
        self.back_to_layout.clicked.connect(lambda: self.layout_views.setCurrentIndex(0))
        header.addWidget(self.back_to_layout)
        header.addWidget(QLabel("Theme"))
        self.theme_choice = QComboBox()
        self.theme_choice.addItems(["Dark", "Light"])
        self.theme_choice.setAccessibleName("Color theme")
        self.theme_choice.currentTextChanged.connect(self.apply_theme)
        header.addWidget(self.theme_choice)
        header.addWidget(self.logo)
        outer.addLayout(header)
        splitter = QSplitter()
        self.layout_views = QStackedWidget()
        self.layout_views.addWidget(splitter)
        self.layout_views.currentChanged.connect(lambda index: self.back_to_layout.setVisible(index > 0))
        outer.addWidget(self.layout_views, 1)
        inputs = QWidget()
        inputs.setObjectName('inputBody')
        inputs.setMinimumWidth(330)
        inputs.setMaximumWidth(380)
        left = QVBoxLayout(inputs)
        input_scroll = QScrollArea()
        input_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        input_scroll.setWidgetResizable(True)
        input_scroll.setMinimumWidth(350)
        input_scroll.setMaximumWidth(400)
        input_scroll.setWidget(inputs)
        splitter.addWidget(input_scroll)

        artwork = QGroupBox("Artwork")
        a = QVBoxLayout(artwork)
        self.artwork_library = ArtworkLibrary()
        a.addWidget(self.artwork_library)
        self.pdf_label = QLabel()
        self.pdf_label.setWordWrap(True)
        self.page_choice = QComboBox()
        self.page_choice.setEnabled(False)
        self.page_choice.currentIndexChanged.connect(self.page_changed)
        self.page_info = QLabel()
        self.page_info.setWordWrap(True)
        a.addWidget(self.page_info)
        self.size_suggestion = QLabel()
        self.size_suggestion.setWordWrap(True)
        a.addWidget(self.size_suggestion)
        self.use_suggestion = QPushButton('Use suggested size')
        self.use_suggestion.clicked.connect(self.apply_suggested_size)
        a.addWidget(self.use_suggestion)
        self.bleed_mode = QComboBox()
        for label,mode in (('Keep bleed separated','keep'),('Overlap bleed','overlap'),('Trim bleed at gutter midpoint','trim'),('Crop all bleed','crop')):
            self.bleed_mode.addItem(label,mode)
        self.bleed_mode.setToolTip('Overlap keeps full bleed; later placements paint over earlier ones. Trim clips excess bleed halfway through each gutter. Artwork is never scaled.')
        a.addWidget(self.bleed_mode)
        self.back_panel = BackArtwork()
        self.back_panel.setParent(self)
        self.back_panel.hide()
        a.addWidget(self.back_panel.alignment)
        left.addWidget(artwork)

        settings = QWidget()
        form = QFormLayout(settings)
        self.setup_job_name = QLineEdit()
        self.setup_job_name.setMaxLength(200)
        form.addRow('Job name', self.setup_job_name)
        self.setup_job_number = QLineEdit()
        self.setup_job_number.setMaxLength(3)
        self.setup_job_number.setPlaceholderText('000–999')
        form.addRow('Machine job number', self.setup_job_number)
        self.card_quantity = QLineEdit()
        self.card_quantity.setMaxLength(9)
        self.card_quantity.setPlaceholderText('Total cards')
        form.addRow('Card quantity', self.card_quantity)
        self.sheet_quantity = QLabel()
        form.addRow('Sheets required', self.sheet_quantity)
        self.width = QLineEdit("3.5")
        self.height = QLineEdit("2")
        self.gutter = QLineEdit()
        self.gutter.setPlaceholderText("Auto: allow both bleeds")
        for label, field in (("Finished width (in)", self.width),
                             ("Finished height (in)", self.height),
                             ("Gutter (in)", self.gutter)):
            form.addRow(label, field)
            field.textChanged.connect(self.invalidate)
        self.width.textEdited.connect(self.finished_size_edited)
        self.height.textEdited.connect(self.finished_size_edited)
        self.bleed_info = QLabel()
        self.bleed_info.setWordWrap(False)
        form.addRow("Calculated bleed", self.bleed_info)
        self.machine = QComboBox()
        for machine_id, path in BUNDLED_PROFILES.items():
            self.machine.addItem(load_profile(path).name.split(" - ")[0], machine_id)
        self.machine.setCurrentIndex(self.machine.findData(DEFAULT_MACHINE_ID))
        self.machine.currentIndexChanged.connect(self.machine_changed)
        form.addRow("Machine", self.machine)
        self.input_tabs = QTabWidget()
        self.input_tabs.addTab(settings, 'Layout settings')
        self.accessory_panel = AccessoryPanel()
        self.accessory_panel.setAccessibleName('Machine Accessory Settings')
        self.accessory_panel.changed.connect(self.invalidate)
        self.input_tabs.addTab(self.accessory_panel, 'Machine accessories')
        left.addWidget(self.input_tabs)
        self.calculate_button = QPushButton("Calculate layout")
        self.calculate_button.setObjectName("calculate")
        self.calculate_button.clicked.connect(self.calculate_layout)
        left.addWidget(self.calculate_button)
        self.export_button = QPushButton("Save GW Bleed project…")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.save_json)
        left.addWidget(self.export_button)
        self.trimposer_button = QPushButton('Save Trimposer job (.ini)…')
        self.trimposer_button.setEnabled(False)
        self.trimposer_button.clicked.connect(self.choose_trimposer_save)
        left.addWidget(self.trimposer_button)
        self.load_button = QPushButton("Load layout…")
        self.load_button.clicked.connect(self.choose_layout)
        left.addWidget(self.load_button)
        self.imported_trimposer = None
        self.import_trimposer_button = QPushButton('Load Trimposer job (.ini)…')
        self.import_trimposer_button.clicked.connect(self.choose_trimposer)
        left.addWidget(self.import_trimposer_button)
        self.clear_trimposer_button = QPushButton('Use automatic layout')
        self.clear_trimposer_button.clicked.connect(self.clear_trimposer)
        self.clear_trimposer_button.hide()
        left.addWidget(self.clear_trimposer_button)
        self.pdf_export_button = QPushButton("Export PDF…")
        self.pdf_export_button.setEnabled(False)
        self.pdf_export_button.clicked.connect(self.choose_pdf_export)
        left.addWidget(self.pdf_export_button)
        self.guide_button = QPushButton('Machine setup guide…')
        self.guide_button.setEnabled(False)
        self.guide_button.setToolTip('Prefilled operator reference for supported machine screens; no equipment control.')
        self.guide_button.clicked.connect(self.open_machine_guide)
        left.addWidget(self.guide_button)
        from .build_info import about_text
        about = QPushButton('About / build information…')
        about.clicked.connect(lambda: QMessageBox.information(self, 'About GW Bleed', about_text()))
        left.addWidget(about)
        left.addStretch()

        output = QWidget()
        right = QVBoxLayout(output)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("font-size: 17px; font-weight: 600;")
        right.addWidget(self.summary)
        self.preview = SheetPreview()
        navigation = QHBoxLayout()
        self.view_mode = QComboBox()
        self.view_mode.addItems(["Sheet", "Card"])
        self.view_mode.currentTextChanged.connect(self.preview.set_mode)
        navigation.addWidget(self.view_mode)
        self.artwork_side = QComboBox()
        self.artwork_side.addItems(['Front','Back'])
        self.artwork_side.model().item(1).setEnabled(False)
        self.artwork_side.currentIndexChanged.connect(self.refresh_artwork_preview)
        navigation.addWidget(self.artwork_side)
        self.rotate_preview = QPushButton('Rotate view')
        self.rotate_preview.setToolTip('Rotate the displayed card or sheet 90°. Does not change layout or export.')
        self.rotate_preview.clicked.connect(self.preview.rotate_view)
        navigation.addWidget(self.rotate_preview)
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
                           ("bleed", "Bleed"), ("bounds", "Printing bounds"))):
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
        legend.setWordWrap(True)
        tools.addWidget(legend)
        right.addLayout(tools)
        self.details = QLabel()
        self.details.setWordWrap(True)
        right.addWidget(self.details)
        results_panel = QWidget()
        results_panel.setMinimumWidth(380)
        results = QVBoxLayout(results_panel)
        results_title = QLabel("Paper stock profiles")
        results_title.setStyleSheet("font-size: 17px; font-weight: 600;")
        results.addWidget(results_title)
        self.paper_catalog_path = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))/'GW Bleed'/'paper-stocks.json'
        self.paper_profiles = standard_paper_stocks()
        self.paper_profile = QComboBox()
        results.addWidget(self.paper_profile)
        self.paper_details = QLabel()
        self.paper_details.setWordWrap(True)
        results.addWidget(self.paper_details)
        paper_buttons = QHBoxLayout()
        for label, edit in (('New profile…',False),('Edit profile…',True)):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False,edit=edit:self.edit_paper_profile(edit))
            paper_buttons.addWidget(button)
        results.addLayout(paper_buttons)
        self.advanced_layouts = QCheckBox('Advanced view')
        results.addWidget(self.advanced_layouts)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Stock", "Columns\n× rows", "Pieces /\nsheet", "Rotation", "Trim\nwaste"])
        self.table.setMinimumHeight(350)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.select_candidate)
        results.addWidget(self.table, 1)
        self.table.hide()
        self.advanced_layouts.toggled.connect(self.table.setVisible)
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
        self.results_tabs.addTab(results_panel, "Paper stock")
        self.finishing_panel = FinishingPanel(self.finished_dimensions)
        self.finishing_panel.applied.connect(self.apply_finishing)
        self.results_tabs.addTab(self.finishing_panel, "Finishing")
        self.registration_panel = RegistrationPanel()
        self.registration_panel.changed.connect(self.update_registration)
        self.registration_panel.visibility_changed.connect(self.preview.set_show_registration)
        self.results_tabs.addTab(self.registration_panel, "Registration marks")
        self.machine_panel = MachinePanel()
        self.results_tabs.addTab(self.machine_panel, "Machine specs")
        self.setup_status = QLabel()
        self.setup_status.setWordWrap(True)
        results.insertWidget(3,self.setup_status)
        self.paper_profile.currentIndexChanged.connect(self.paper_profile_changed)
        self.load_paper_profiles()
        self.setup_job_name.textChanged.connect(self.machine_setup_changed)
        self.setup_job_number.textChanged.connect(self.machine_setup_changed)
        self.setup_job_number.textChanged.connect(self.update_registration)
        self.card_quantity.textChanged.connect(self.update_registration)
        self.bleed_mode.currentIndexChanged.connect(self.invalidate)
        self.back_panel.changed.connect(self.back_changed)
        self.back_panel.ready.connect(self.back_ready)
        self.artwork_library.assign_front.connect(self.assign_front_page)
        self.artwork_library.assign_back.connect(self.assign_back_page)
        self.artwork_library.clear_back.connect(self.clear_back_assignment)
        self.artwork_library.swap.connect(self.swap_artwork)
        self.artwork_library.undo.connect(self.undo_assignment)
        self.artwork_library.rotate_front.connect(lambda:self.rotate_source(False))
        self.artwork_library.rotate_back.connect(lambda:self.rotate_source(True))
        self.artwork_library.relinked.connect(self.relink_artwork)
        self.artwork_library.compare.connect(self.compare_artwork)
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
        self.refresh_paper_profiles(self.paper_profile.currentData())
        self.accessory_panel.set_profile(profile)
        self.machine_panel.set_profile(profile)
        self.registration_panel.set_profile(profile)
        self.finishing_panel.set_profile(profile)
        self.machine_setup_changed()
        cap = profile.capabilities
        if cap and cap.gutter_mode == "fixed":
            side = (f"Side trim maximum: {cap.max_side_trim_um/1000:g} mm per paper edge."
                    if cap.max_side_trim_um is not None else "No side-trim maximum configured; profile remains unverified.")
            self.gutter.setToolTip("Zero gutter requires zero PDF bleed. Fixed middle gutter: 0 or 5–15 mm. " + side)
        else:
            self.gutter.setToolTip("Trim-to-trim gap; leave blank to accommodate both bleeds. See Machine specs for provisional limits.")


    def apply_theme(self, name):
        dark = name == "Dark"
        self.setPalette(dark_palette() if dark else self.light_palette)
        self.setStyleSheet(STYLE if dark else LIGHT_STYLE)
        self.preview.set_dark_mode(dark)

    def invalidate(self, *_):
        self.invalidate_guide()
        self.guide_button.setEnabled(False)
        self.revision += 1
        self.result = None
        self.export_button.setEnabled(False)
        self.trimposer_button.setEnabled(False)
        self.pdf_export_button.setEnabled(False)
        self.table.setRowCount(0)
        self.cut_distances.setRowCount(0)
        self.preview.show_candidate(None)
        self.preview.set_registration(())
        self.preview.set_barcode(None)
        self.registration_panel.barcode_status.clear()
        self.registration_panel.show_result()
        self.summary.clear()
        self.details.clear()
        self.messages.setPlainText("Inputs changed — calculate to update the layout.")
        self.update_bleed()

    def get_bleed(self):
        index = self.page_choice.currentIndex()
        if not 0 <= index < len(self.pdf_pages):
            raise ValueError("Select a PDF to calculate bleed and layout.")
        dimensions = (to_um(self.width.text()),to_um(self.height.text()))
        front = self.pdf_pages[index].oriented(self.front_orientation).derive_bleed(*dimensions)
        if self.back_panel.enabled:
            self.back_panel.validate()
            back = self.back_panel.pages[self.back_panel.page.currentIndex()].oriented(self.back_orientation).derive_bleed(*dimensions)
            return tuple(max(a,b) for a,b in zip(front,back))
        return front

    @staticmethod
    def page_extent(page):
        return tuple(to_um(Decimal(str(v))/72) for v in (page.width_points,page.height_points))

    def finished_size_edited(self,*_):
        self.size_overridden = True

    def update_size_suggestion(self):
        index = self.page_choice.currentIndex()
        if not 0<=index<len(self.pdf_pages):
            self.size_suggestion.clear();return
        info = self.pdf_pages[index].oriented(self.front_orientation)
        w,h,reason = info.suggested_size()
        text = f'Suggested {inches(w)} × {inches(h)} in — {reason}'
        if info.trim_warning: text += '\n'+info.trim_warning
        try:
            if max(info.derive_bleed(*self.finished_dimensions()))>6350:
                text += '\nLarge available bleed; check the finished dimensions.'
        except ValueError: pass
        self.size_suggestion.setText(text)

    def apply_suggested_size(self):
        index = self.page_choice.currentIndex()
        if not 0<=index<len(self.pdf_pages):return
        w,h,_ = self.pdf_pages[index].oriented(self.front_orientation).suggested_size()
        self.suggestion_applied = True
        self.size_overridden = False
        self.width.setText(str(Decimal(w)/25400))
        self.height.setText(str(Decimal(h)/25400))
        self.update_bleed()
        self.update_size_suggestion()
        self.refresh_artwork_preview()

    def assignment_snapshot(self):
        return dict(front=(str(self.pdf_path),max(0,self.page_choice.currentIndex())) if self.pdf_path else None,
                    back=(str(self.back_panel.path),max(0,self.back_panel.page.currentIndex())) if self.back_panel.enabled and self.back_panel.path else None,
                    front_angle=self.front_orientation,back_angle=self.back_orientation)

    def remember_assignment(self):
        self.assignment_history.append(self.assignment_snapshot())
        self.assignment_history = self.assignment_history[-20:]

    def update_assignments(self):
        state = self.assignment_snapshot()
        self.artwork_library.set_assignments(state['front'],state['back'],self.front_orientation,self.back_orientation)

    def assign_front_page(self,path,index):
        self.remember_assignment()
        self.front_orientation = 0
        self.load_pdf(path,index)
        self.update_assignments()

    def assign_back_page(self,path,index):
        self.remember_assignment()
        self.review_sources.discard(str(Path(path).resolve()))
        self.source_review_required = bool(self.review_sources)
        self.back_orientation = 0
        self.back_panel.mode.setCurrentIndex(2)
        self.back_panel.load(path,index)
        self.update_assignments()

    def clear_back_assignment(self):
        self.remember_assignment()
        self.back_panel.mode.setCurrentIndex(0)
        self.update_assignments()

    def restore_assignments(self,state):
        self.front_orientation,self.back_orientation = state['front_angle'],state['back_angle']
        if state['front']: self.load_pdf(*state['front'])
        else:
            self.loader.close();self.pdf_token=-1;self.pdf_path=None;self.pdf_pages=();self.pdf_busy=False;self.front_png=None
            self.page_choice.clear();self.pdf_label.clear();self.page_info.clear();self.size_suggestion.clear();self.invalidate()
        if state['back']:
            self.back_panel.mode.setCurrentIndex(2);self.back_panel.load(*state['back'])
        else:self.back_panel.mode.setCurrentIndex(0)
        self.update_assignments()

    def undo_assignment(self):
        if self.assignment_history:self.restore_assignments(self.assignment_history.pop())

    def swap_artwork(self):
        state = self.assignment_snapshot()
        if not state['front'] or not state['back']:
            self.artwork_library.status.setText('Assign both sides before swapping.');return
        self.remember_assignment()
        self.restore_assignments(dict(front=state['back'],back=state['front'],front_angle=state['back_angle'],back_angle=state['front_angle']))

    def rotate_source(self,back):
        self.remember_assignment()
        if back:self.back_orientation=90-self.back_orientation
        else:self.front_orientation=90-self.front_orientation
        self.invalidate();self.update_size_suggestion();self.update_assignments();self.refresh_artwork_preview()

    def relink_artwork(self,old,new):
        state = self.assignment_snapshot()
        self.remember_assignment()
        for side in ('front','back'):
            if state[side] and Path(state[side][0]).resolve()==Path(old).resolve():state[side]=(new,state[side][1])
        self.restore_assignments(state)

    def compare_artwork(self):
        row = self.table.currentRow()
        if not self.result or row<0 or not self.back_panel.enabled or not self.back_panel.pages:
            self.artwork_library.status.setText('Assign both sides and calculate a layout to compare them.');return
        dialog = QDialog(self)
        dialog.setWindowTitle('Front and back review')
        dialog.resize(1100,700)
        layout = QVBoxLayout(dialog)
        mode = QComboBox();mode.addItems(['Card','Sheet']);layout.addWidget(mode)
        columns = QHBoxLayout();layout.addLayout(columns,1)
        c = self.result.candidates[row]
        for back in (False,True):
            box = QVBoxLayout();columns.addLayout(box,1)
            box.addWidget(QLabel('Back' if back else 'Front'))
            preview = SheetPreview();box.addWidget(preview,1)
            preview.set_dark_mode(self.preview.dark_mode)
            angle = self.back_orientation if back else self.front_orientation
            info = (self.back_panel.pages[self.back_panel.page.currentIndex()] if back else self.pdf_pages[self.page_choice.currentIndex()]).oriented(angle)
            preview.source_extent = info.extent_um
            preview.source_trim = info.trim_for(*self.finished_dimensions())
            preview.bleed_handling = self.job.bleed_handling
            preview.set_card(*self.finished_dimensions(),self.job.bleed_um,self.job.vertical_bleed_um)
            preview.set_artwork(self.back_panel.png if back else self.front_png)
            if angle:preview.artwork=preview.artwork.transformed(QTransform().rotate(angle),Qt.TransformationMode.SmoothTransformation)
            preview.show_candidate(back_candidate(c,back and self.back_panel.alignment.currentIndex()==0))
            preview.set_mode('Card')
            mode.currentTextChanged.connect(preview.set_mode)
        dialog.exec()

    def back_changed(self):
        self.artwork_side.model().item(1).setEnabled(self.back_panel.enabled)
        if not self.back_panel.enabled:
            self.artwork_side.setCurrentIndex(0)
        self.invalidate()
        self.calculate_button.setEnabled(not self.pdf_busy and not self.back_panel.busy)
        self.statusBar().showMessage('Loading back PDF…' if self.back_panel.busy else 'Ready')
        self.refresh_artwork_preview()

    def back_ready(self):
        self.back_changed()
        self.update_bleed()
        if self.back_panel.pages:
            self.artwork_library.add_document(self.back_panel.path,self.back_panel.pages,self.back_panel.signature)
        self.update_assignments()
        if self.back_panel.error:
            self.messages.setPlainText('Back PDF: '+self.back_panel.error)
        pending = getattr(self,'pending_duplex_recalculate',False)
        if pending and not self.pdf_busy and self.back_panel.pages:
            self.pending_duplex_recalculate = False
            self.calculate_layout()
            if getattr(self,'duplex_selection',None):
                self.restore_selection = (self.revision,self.duplex_selection)

    def refresh_artwork_preview(self):
        back = self.artwork_side.currentText() == 'Back'
        pages = self.back_panel.pages if back else self.pdf_pages
        index = self.back_panel.page.currentIndex() if back else self.page_choice.currentIndex()
        angle = self.back_orientation if back else self.front_orientation
        info = pages[index].oriented(angle) if 0<=index<len(pages) else None
        self.preview.source_extent = self.page_extent(info) if info else None
        try: self.preview.source_trim = info.trim_for(*self.finished_dimensions()) if info else None
        except ValueError: self.preview.source_trim = None
        self.preview.bleed_handling = self.bleed_mode.currentData()
        png = self.back_panel.png if back and self.back_panel.enabled else self.front_png if not back else None
        self.preview.set_artwork(png)
        if angle and png:
            self.preview.artwork = self.preview.artwork.transformed(QTransform().rotate(angle),Qt.TransformationMode.SmoothTransformation)
            self.preview.redraw(False)
        row = self.table.currentRow()
        if self.result and 0<=row<len(self.result.candidates):
            c = self.result.candidates[row]
            self.preview.show_candidate(back_candidate(c,back and self.back_panel.alignment.currentIndex()==0))
            self.update_registration()

    def update_bleed(self):
        if not self.pdf_pages:
            self.bleed_info.clear()
            self.preview.set_card()
            return
        try:
            bx, by = self.get_bleed()
            self.registration_panel.set_artwork_bleed(bx, by)
            self.bleed_info.setText(f"Left / right: {inches(bx)} in\nTop / bottom: {inches(by)} in")
            width, height = to_um(self.width.text()), to_um(self.height.text())
            self.preview.set_card(width, height, bx, by) if width and height else self.preview.set_card()
            if self.bleed_mode.currentData() == 'crop' and width and height:
                self.preview.set_card(width,height,0,0)
        except (ValueError, OSError) as exc:
            self.bleed_info.setText(str(exc))
            self.preview.set_card()

    def select_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select artwork", "", "PDF files (*.pdf)")
        if path:
            self.load_pdf(path)

    def load_pdf(self, path, index=0):
        self.review_sources.discard(str(Path(path).resolve()))
        self.source_review_required = bool(self.review_sources)
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
        self.front_png = None
        self.invalidate()
        self.preview.set_artwork(None)
        self.calculate_button.setEnabled(False)
        self.page_info.clear()
        self.size_suggestion.clear()
        self.statusBar().showMessage("Loading PDF preview…")
        self.pdf_token = self.loader.request(self.pdf_path, index)

    def pdf_ready(self, token, pages, index, png):
        if token != self.pdf_token:
            return
        self.pdf_busy = False
        self.pdf_signature = self.loader.signature
        self.pdf_pages = pages
        self.front_png = png
        self.page_choice.blockSignals(True)
        self.page_choice.clear()
        self.page_choice.addItems([f"Page {n + 1}" for n in range(len(pages))])
        self.page_choice.setCurrentIndex(index)
        self.page_choice.setEnabled(True)
        self.page_choice.blockSignals(False)
        self.artwork_library.add_document(self.pdf_path,pages,self.pdf_signature)
        self.update_assignments()
        self.update_size_suggestion()
        if not self.suggestion_applied and not self.size_overridden:
            self.apply_suggested_size()
        self.preview.set_artwork(png)
        self.back_panel.sync_front(self.pdf_path)
        self.update_bleed()
        p = pages[index]
        self.page_info.setText(f"{p.width_points/72:.3f} × {p.height_points/72:.3f} in")
        self.calculate_button.setEnabled(not self.back_panel.busy)
        self.statusBar().showMessage("PDF preview ready")
        pending = self.pending_layout
        self.pending_layout = None
        if pending and pending[0] == token and pending[1] == self.revision:
            if pending[2] != index:
                self.messages.setPlainText("The saved PDF page is no longer available. Choose a page and recalculate.")
                return
            if self.back_panel.busy:
                self.pending_duplex_recalculate = True
                return
            self.calculate_layout()
            self.restore_selection = (self.revision, pending[3])
        self.refresh_artwork_preview()
        if getattr(self,'pending_duplex_recalculate',False) and not self.back_panel.busy and self.back_panel.pages:
            self.back_ready()

    def pdf_failed(self, token, error):
        if token != self.pdf_token:
            return
        self.pdf_busy = False
        self.pending_layout = None
        self.pdf_signature = None
        self.front_png = None
        self.pdf_pages = ()
        self.preview.set_artwork(None)
        self.invalidate()
        self.page_info.clear()
        self.messages.setPlainText(error)
        self.calculate_button.setEnabled(True)
        self.statusBar().showMessage("PDF load failed")

    def check_source(self):
        if self.exporter.process:
            return
        if self.back_panel.enabled and self.back_panel.path and self.back_panel.signature and not self.back_panel.busy:
            try: back_changed = source_signature(self.back_panel.path) != self.back_panel.signature
            except OSError: back_changed = True
            if back_changed:
                self.back_panel.load(self.back_panel.path,max(0,self.back_panel.page.currentIndex()))
                self.review_sources.add(str(self.back_panel.path.resolve()))
                self.source_review_required = True
        if self.pdf_path is None or self.pdf_signature is None or self.pdf_busy:
            return
        try:
            changed = source_signature(self.pdf_path) != self.pdf_signature
        except OSError:
            changed = True
        if changed:
            self.load_pdf(self.pdf_path, max(0, self.page_choice.currentIndex()))
            self.review_sources.add(str(self.pdf_path.resolve()))
            self.source_review_required = True

    def finished_dimensions(self):
        return to_um(self.width.text()), to_um(self.height.text())

    def update_registration(self):
        self.invalidate_guide()
        row = self.table.currentRow()
        if self.result is None or not 0 <= row < len(self.result.candidates):
            self.sheet_quantity.clear()
            self.registration_panel.barcode_value.blockSignals(True)
            self.registration_panel.barcode_value.clear()
            self.registration_panel.barcode_value.blockSignals(False)
            self.preview.set_registration(())
            self.registration_panel.show_result()
            self.preview.set_barcode(None)
            return
        candidate = self.result.candidates[row]
        if self.artwork_side.currentText() == 'Back' and self.back_panel.enabled:
            candidate = back_candidate(candidate,self.back_panel.alignment.currentIndex()==0)
        quantity_error = ''
        count = self.card_quantity.text().strip()
        number = self.setup_job_number.text().strip()
        payload = ''
        if not count.isascii() or not count.isdigit() or int(count) < 1:
            quantity_error = 'Enter a positive card quantity in Layout settings.'
            self.sheet_quantity.clear()
        else:
            sheets = (int(count)+candidate.yield_per_sheet-1)//candidate.yield_per_sheet
            self.sheet_quantity.setText(str(sheets))
            if sheets > 99:
                quantity_error = 'Barcode supports at most 99 sheets. Reduce the card quantity or disable barcode.'
            elif not number.isascii() or not number.isdigit() or not 0 <= int(number) <= 999:
                quantity_error = 'Enter a machine job number from 000 to 999 in Layout settings.'
            else:
                payload = f'{int(number):03d}{sheets:02d}'
        self.registration_panel.barcode_value.blockSignals(True)
        self.registration_panel.barcode_value.setText(payload)
        self.registration_panel.barcode_value.blockSignals(False)
        registration = build_registration(candidate, self.profile, self.registration_panel.settings())
        self.preview.set_registration(registration.marks)
        self.registration_panel.show_result(candidate, self.profile, registration)
        try:
            if quantity_error and self.registration_panel.settings().barcode.enabled:
                raise ValueError(quantity_error)
            barcode = build_barcode(candidate, self.profile, self.registration_panel.settings().barcode, registration.marks)
        except ValueError as exc:
            self.preview.set_barcode(None)
            self.registration_panel.barcode_status.setText(str(exc))
            self.pdf_export_button.setEnabled(False)
            if isinstance(exc, BarcodePlacementError):
                key = (self.revision, row, repr(self.registration_panel.settings()))
                if key != self._barcode_warning_key:
                    self._barcode_warning_key = key
                    QMessageBox.warning(self, 'Barcode cannot be placed', str(exc))
            else:
                self._barcode_warning_key = None
            return
        self._barcode_warning_key = None
        self.preview.set_barcode(barcode)
        self.registration_panel.barcode_status.setText(
            f"Code 39: job {self.registration_panel.settings().barcode.value[:3]}, quantity {self.registration_panel.settings().barcode.value[3:]} | 45 × 6.5 mm bars, leading edge {barcode.bars[0].y_um/1000:.3f} mm, right edge 52 mm."
            if barcode else "Barcode generation is off.")
        self.pdf_export_button.setEnabled(not self.pdf_busy)

    def apply_finishing(self, operations):
        if self.imported_trimposer is not None:
            QMessageBox.warning(self, 'Imported Trimposer layout', 'Finishing positions come from the imported job. Choose Use automatic layout before applying card finishing.')
            self.finishing_panel.set_operations(())
            return
        self.finishing_operations = tuple(operations)
        self.finishing_rotation = self.finishing_panel.rotation
        self.view_mode.setCurrentText("Card")
        self.invalidate()
        if self.pdf_pages and not self.pdf_busy:
            self.calculate_layout()

    def calculate_layout(self):
        self.check_source()
        if self.pdf_busy or self.back_panel.busy:
            return
        self.invalidate()
        try:
            if self.source_review_required:
                raise ValueError('Artwork changed. Review and reassign the affected pages from the artwork list before calculating.')
            self.profile = self.current_machine_profile()
            paper = self.paper_profile.currentData()
            if paper is not None:
                self.profile = replace(self.profile, stocks=(paper.stock(),), press_margins=paper.printing_margins, approval_state='unverified')
            else:
                self.profile = replace(self.profile, press_margins=Margins(3175,3175,3175,3175))
            bleed_x, bleed_y = self.get_bleed()
            if self.gutter.text().strip():
                gutter = to_um(self.gutter.text())
            else:
                minimum, step = self.profile.minimum_gutter_um, self.profile.gutter_increment_um
                needed = 2*max(bleed_x,bleed_y) if self.bleed_mode.currentData() == 'keep' else 0
                gutter = minimum + max(0, (max(1, needed) - minimum + step - 1) // step) * step
            self.job = Job(to_um(self.width.text()), to_um(self.height.text()), bleed_x, gutter,
                           bleed_y_um=bleed_y, finishing=self.finishing_operations, shared_cut=gutter == 0,
                           finishing_rotation=self.finishing_rotation, accessories=self.accessory_panel.settings(),
                           trimposer_ini=self.imported_trimposer,bleed_handling=self.bleed_mode.currentData())
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

    def select_candidate(self):
        self.invalidate_guide()
        row = self.table.currentRow()
        if self.result is None or not 0 <= row < len(self.result.candidates):
            return
        c = self.result.candidates[row]
        self.trimposer_button.setEnabled(self.profile.id in ADAPTERS and not self.pdf_busy)
        self.guide_button.setEnabled(self.profile.id in ADAPTERS and not self.pdf_busy)
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
        self.refresh_artwork_preview()
        self.update_registration()
        self.summary.setText(f"{'Recommended' if row == 0 else 'Alternative'}: {c.stock_id}  •  "
                             f"{c.columns} × {c.rows}  •  {c.yield_per_sheet} pieces per sheet\n"
                             f"Feed edge: {inches(c.sheet_width_um)} in  •  Gutter: {inches(self.job.gutter_um)} in")
        if self.job.trimposer_ini is not None:
            self.summary.setText(f'Imported Trimposer: {inches(c.sheet_width_um)} × {inches(c.sheet_height_um)} in • {c.columns} × {c.rows} • {c.yield_per_sheet} pieces per sheet')
        first, last = c.bleed_regions[0], c.bleed_regions[-1]
        self.details.setText(
            f"Artwork rotation: {c.rotation}°\n"
            f"Outer bleed to sheet edge — Left: {inches(first.x_um)} in | "
            f"Right: {inches(c.sheet_width_um-last.x_um-last.width_um)} in | "
            f"Top: {inches(first.y_um)} in | Bottom: {inches(c.sheet_height_um-last.y_um-last.height_um)} in")

    def choose_layout(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load layout", "", "GW Bleed layouts (*.json)")
        if path:
            self.load_layout(path)

    def choose_trimposer(self):
        if self.pdf_busy or not self.pdf_pages or not self.calculate_button.isEnabled():
            QMessageBox.warning(self, 'Load Trimposer job', 'Load artwork and wait for PDF loading and calculation to finish first.')
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Load Trimposer job', '', 'Trimposer jobs (*.ini)')
        if path:
            self.load_trimposer(path)

    def load_trimposer(self, path):
        from .trimposer_import import read_trimposer
        try:
            if self.source_review_required:
                raise ValueError('Artwork changed. Relink/reload and review the assigned pages before calculating.')
            if self.pdf_busy or not self.pdf_pages:
                raise ValueError('Load artwork and wait for it to finish first.')
            text = read_trimposer(path)
            profile = self.current_machine_profile()
            paper = self.paper_profile.currentData()
            profile = replace(profile, press_margins=paper.printing_margins if paper else Margins(3175,3175,3175,3175))
            bx, by = self.get_bleed()
            job = Job(to_um(self.width.text()), to_um(self.height.text()), bx, bleed_y_um=by,
                      accessories=self.accessory_panel.settings(), trimposer_ini=text,bleed_handling=self.bleed_mode.currentData())
            result = calculate(job, profile)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, 'Cannot load Trimposer job', str(exc))
            return False
        self.invalidate()
        self.imported_trimposer = text
        self.clear_trimposer_button.show()
        self.finishing_operations = ()
        self.finishing_panel.set_operations(())
        self.job, self.profile = job, profile
        self.calculation_finished(self.revision, result, '')
        self.view_mode.setCurrentText('Sheet')
        return True

    def clear_trimposer(self):
        self.imported_trimposer = None
        self.clear_trimposer_button.hide()
        self.invalidate()

    def load_layout(self, path):
        try:
            job, profile, source, page, selection, registration, setup = read_layout(path, include_machine_setup=True)
            saved_artwork = read_json(path).get('artwork_assignment',{})
            self.front_orientation = saved_artwork.get('front_orientation',0)
            self.back_orientation = saved_artwork.get('back_orientation',0)
            self.size_overridden = saved_artwork.get('size_overridden',True)
            self.suggestion_applied = True
            self.assignment_history.clear()
            library = read_json(path).get('artwork_library',[])
            self.artwork_library.import_files([str(Path(p) if Path(p).is_absolute() else Path(path).parent/p) for p in library])
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
            self.machine_setup = setup
            saved_paper = read_json(path).get('paper_stock')
            if saved_paper is not None:
                paper = PaperStock(**saved_paper)
                if paper not in self.paper_profiles:
                    self.paper_profiles.append(paper)
                self.refresh_paper_profiles(paper)
            else:
                self.paper_profile.setCurrentIndex(0)
            self.setup_job_name.setText(setup.job_name)
            self.setup_job_number.setText('' if setup.job_number is None else f'{setup.job_number:03d}')
            self.card_quantity.setText(str(read_json(path).get('card_quantity', '')))
            self.machine_setup_changed()
            self.finishing_operations = job.finishing
            self.bleed_mode.setCurrentIndex(self.bleed_mode.findData(job.bleed_handling))
            back_data = read_json(path).get('back_artwork',{})
            self.back_panel.mode.setCurrentIndex(back_data.get('mode',0))
            self.back_panel.alignment.setCurrentIndex(0 if back_data.get('mirror',True) else 1)
            if back_data.get('mode') and back_data.get('path'):
                back_path = Path(back_data['path'])
                if not back_path.is_absolute(): back_path = Path(path).parent/back_path
                self.back_panel.load(back_path,back_data.get('page',0))
            self.imported_trimposer = job.trimposer_ini
            self.clear_trimposer_button.setVisible(job.trimposer_ini is not None)
            self.finishing_rotation = job.finishing_rotation
            accessories = job.accessories
            if accessories is None:
                # Preserve legacy rotary jobs; previous files had no installed-tool inventory.
                accessories = replace(default_accessories(profile), rotary_perfs=len({op.position_um for op in job.finishing if op.kind == 'rotary_perf'}) * profile.max_columns)
            self.accessory_panel.set_settings(accessories, inferred=job.accessories is None)
            self.width.setText(str(Decimal(job.width_um) / 25400))
            self.height.setText(str(Decimal(job.height_um) / 25400))
            self.finishing_panel.set_operations(job.finishing, job.finishing_rotation)
            self.registration_panel.set_settings(registration)
            self.gutter.setText(str(Decimal(job.gutter_um) / 25400))
            self.restore_selection = None
            self.load_pdf(source, page)
            self.pending_layout = (self.pdf_token, self.revision, page, selection)
            self.pending_duplex_recalculate = self.back_panel.enabled
            self.duplex_selection = selection
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
        if self.back_panel.enabled:
            layout.addWidget(QLabel('Two pages: front, then back. '+self.back_panel.alignment.currentText()))
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
        if self.result is None or self.pdf_busy or self.back_panel.busy or self.exporter.process:
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
            self.back_panel.validate()
            front_info = self.pdf_pages[self.page_choice.currentIndex()].oriented(self.front_orientation)
            request['source_dimensions'] = self.page_extent(front_info)
            request['source_trim'] = front_info.trim_for(*self.finished_dimensions())
            request['source_orientation'] = self.front_orientation
            if self.back_panel.enabled:
                back_info = self.back_panel.pages[self.back_panel.page.currentIndex()].oriented(self.back_orientation)
                request['back'] = dict(source=str(self.back_panel.path.resolve()),signature=self.back_panel.signature,
                    page=self.back_panel.page.currentIndex(),source_dimensions=self.page_extent(back_info),source_trim=back_info.trim_for(*self.finished_dimensions()),source_orientation=self.back_orientation,
                    mirror=self.back_panel.alignment.currentIndex()==0)
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
            payload = {"schema_version": 6, "units": "um", "job": asdict(self.job), "card_quantity": self.card_quantity.text().strip(), "back_artwork":self.back_panel.snapshot(),
                       "artwork_library":self.artwork_library.snapshot(),"artwork_assignment":dict(front_orientation=self.front_orientation,back_orientation=self.back_orientation,size_overridden=self.size_overridden),
                       "profile_snapshot": asdict(self.profile), "calculation": asdict(self.result),
                       "selected_candidate_index": self.table.currentRow(),
                       "source_pdf": str(self.pdf_path) if self.pdf_path else None,
                       "source_page_index": self.page_choice.currentIndex() if self.pdf_path else None}
            payload["registration"] = asdict(self.registration_panel.settings())
            payload['machine_setup'] = asdict(self.read_machine_setup())
            paper = self.paper_profile.currentData()
            payload['paper_stock'] = asdict(paper) if paper else None
            atomic_json(path, payload)
            self.statusBar().showMessage(f"Saved {path}")
        except (OSError, ValueError) as exc:
            self.messages.setPlainText(f"Unable to save layout: {exc}")

    def invalidate_guide(self):
        if self.guide is not None:
            self.guide.invalidate()

    def choose_trimposer_save(self):
        self.check_source()
        row = self.table.currentRow()
        if self.result is None or self.pdf_busy or not 0<=row<len(self.result.candidates):
            return
        candidate = self.result.candidates[row]
        export_job, export_profile, export_revision = self.job, self.profile, self.revision
        try:
            setup = self.read_machine_setup()
            if not setup.thickness_inches:
                raise ValueError('Select a paper profile with measured thickness first.')
            if setup.job_number is None:
                raise ValueError('Enter a machine job number in Layout settings first.')
            registration = self.registration_panel.settings()
            if registration.barcode.enabled:
                raise ValueError('Barcode job-selection semantics are not verified for Trimposer INI export. Disable barcode for this exchange job.')
            marks = build_registration(candidate,self.profile,registration).marks
            mark = next((m for m in marks if m.axis=='machine'),None)
            if registration.machine_mark_enabled and mark is None:
                raise ValueError('The requested dedicated registration mark cannot be generated.')
            position = ((mark.rect.y_um,candidate.sheet_width_um-mark.rect.x_um-mark.rect.width_um) if mark else None)
        except ValueError as exc:
            self.messages.setPlainText(str(exc))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Save Trimposer INI job')
        form = QFormLayout(dialog)
        note = QLabel('Offline exchange format based on supplied Trimposer examples. Review tool slots, units and operations in Trimposer before use. This file contains job settings, not PDF artwork or the full GW Bleed project. Binary (.bin) transfer is reserved for a future feature.')
        note.setWordWrap(True)
        note.setMaximumWidth(520)
        form.addRow(note)
        form.addRow('Machine job number',QLabel(f'{setup.job_number:03d}'))
        form.addRow('Speed grade',QLabel('4'))
        placeholder = crease_depth_is_placeholder(setup.thickness_inches,export_profile.capabilities)
        form.addRow('Crease level',QLabel(f'{setup.crease_depth} / 5'+(' — placeholder (mapping unavailable)' if placeholder else ' — calculated')))
        error = QLabel()
        error.setWordWrap(True)
        error.setMaximumWidth(520)
        form.addRow(error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        form.addRow(buttons)
        buttons.rejected.connect(dialog.reject)
        def save():
            try:
                self.check_source()
                if self.revision != export_revision or self.result is None:
                    raise ValueError('The source or layout changed; recalculate before saving a Trimposer job.')
                data=trimposer_ini(export_job,export_profile,candidate,setup,job_number=setup.job_number,
                                   registration_position=position)
                path,_=QFileDialog.getSaveFileName(dialog,'Save Trimposer job',f'MachineParameterFile_{setup.job_number}.ini','Trimposer INI jobs (*.ini)')
                if not path:
                    return
                if not Path(path).suffix:
                    path += '.ini'
                save_trimposer_ini(path,data)
                self.statusBar().showMessage(f'Saved Trimposer INI: {path} — review in Trimposer before use.')
                dialog.accept()
            except (ValueError,OSError) as exc:
                error.setText(str(exc))
        buttons.accepted.connect(save)
        dialog.exec()

    def read_machine_setup(self):
        paper = self.paper_profile.currentData()
        thickness = paper.thickness_inches if paper else ''
        depth = automatic_crease_depth(thickness,self.current_machine_profile().capabilities)
        number = self.setup_job_number.text().strip()
        if number and (not number.isascii() or not number.isdigit()):
            raise ValueError('Machine job number must be 000–999.')
        return MachineSetup(thickness, depth, self.setup_job_name.text(),int(number) if number else None)

    def refresh_paper_profiles(self, selected=None):
        self.paper_profile.blockSignals(True)
        self.paper_profile.clear()
        self.paper_profile.addItem('Automatic — available machine stock sizes', None)
        for paper in self.paper_profiles:
            if stock_fits_machine(paper,self.current_machine_profile()):
                label = paper.name if paper.gsm is None or f'{paper.gsm} gsm' in paper.name else f'{paper.name} — {paper.gsm} gsm'
                self.paper_profile.addItem(label,paper)
        self.paper_profile.setCurrentIndex(next((i for i in range(self.paper_profile.count()) if self.paper_profile.itemData(i)==selected),0))
        self.paper_profile.blockSignals(False)
        self.update_paper_details()

    def load_paper_profiles(self):
        try:
            if self.paper_catalog_path.exists():
                records = read_json(self.paper_catalog_path,1024*1024)
                if not isinstance(records,list) or len(records)>200:
                    raise ValueError('Invalid paper profile catalog.')
                self.paper_profiles = [PaperStock(**record) for record in records]
                for standard in standard_paper_stocks():
                    if len(self.paper_profiles)<200 and not any(p.name == standard.name for p in self.paper_profiles):
                        self.paper_profiles.append(standard)
        except (ValueError,TypeError,OSError) as exc:
            self.messages.setPlainText(f'Unable to load paper profiles: {exc}')
        self.refresh_paper_profiles()

    def update_paper_details(self):
        paper = self.paper_profile.currentData()
        m = paper.printing_margins if paper else Margins(3175,3175,3175,3175)
        self.paper_details.setText(((f'{inches(paper.width_um)} × {inches(paper.height_um)} in | Weight: {str(paper.gsm)+" gsm" if paper.gsm else "not set"} | Thickness: {paper.thickness_inches or "not measured"} in\n') if paper else '')+
            f'Printing margins (in): left {inches(m.left_um)}, right {inches(m.right_um)}, lead {inches(m.lead_um)}, trail {inches(m.trail_um)}')

    def paper_profile_changed(self, *_):
        self.update_paper_details()
        self.machine_setup_changed()
        self.invalidate()
        if self.pdf_pages and not self.pdf_busy:
            self.calculate_layout()

    def edit_paper_profile(self, edit=False):
        existing = self.paper_profile.currentData() if edit else None
        dialog = QDialog(self)
        dialog.setWindowTitle('Edit paper stock profile' if existing else 'New paper stock profile')
        form = QFormLayout(dialog)
        fields = [QLineEdit(value) for value in ((existing.name if existing else ''),
                  str(Decimal(existing.width_um)/25400) if existing else '',
                  str(Decimal(existing.height_um)/25400) if existing else '',
                  existing.thickness_inches if existing else '')]
        for label,field in zip(('Profile name','Width (in)','Length (in)','Thickness (in)'),fields):
            form.addRow(label,field)
        fields[3].setPlaceholderText('Optional — measured caliper, not derived from gsm')
        gsm_field = QLineEdit(str(existing.gsm) if existing and existing.gsm else '')
        form.addRow('Paper weight (gsm)',gsm_field)
        margins = existing.printing_margins if existing else Margins(3175,3175,3175,3175)
        margin_fields = {}
        for edge in ('left','right','lead','trail'):
            field = QLineEdit(str(Decimal(getattr(margins,edge+'_um'))/25400))
            field.setToolTip('Printing margin measured inward from this paper edge in feed orientation. Applies to artwork and registration marks.')
            margin_fields[edge+'_um'] = field
            form.addRow(f'Printing margin — {edge} (in)',field)
        error = QLabel()
        error.setWordWrap(True)
        form.addRow(error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        form.addRow(buttons)
        buttons.rejected.connect(dialog.reject)
        def save():
            try:
                paper = PaperStock(fields[0].text().strip(),to_um(fields[1].text()),to_um(fields[2].text()),fields[3].text().strip(),
                    Margins(**{key:to_um(value.text()) for key,value in margin_fields.items()}),int(gsm_field.text()) if gsm_field.text().strip() else None)
                if not stock_fits_machine(paper,self.current_machine_profile()):
                    raise ValueError('Paper dimensions are outside the selected machine’s sheet-size limits.')
                if any(p.name == paper.name and p != existing for p in self.paper_profiles):
                    raise ValueError('A paper profile with that name already exists.')
                profiles = list(self.paper_profiles)
                if existing:
                    profiles[profiles.index(existing)] = paper
                else:
                    if len(profiles)>=200:
                        raise ValueError('At most 200 paper profiles are supported.')
                    profiles.append(paper)
                self.paper_catalog_path.parent.mkdir(parents=True,exist_ok=True)
                atomic_json(self.paper_catalog_path,[asdict(p) for p in profiles])
                self.paper_profiles = profiles
                self.refresh_paper_profiles(paper)
                self.paper_profile_changed()
                dialog.accept()
            except (ValueError,OSError) as exc:
                error.setText(str(exc))
        buttons.accepted.connect(save)
        dialog.exec()

    def machine_setup_changed(self, *_):
        self.invalidate_guide()
        try:
            self.machine_setup = self.read_machine_setup()
            placeholder = crease_depth_is_placeholder(self.machine_setup.thickness_inches,self.current_machine_profile().capabilities)
            self.setup_status.setText('Crease depth: 2 / 5 — placeholder (mapping unavailable).'+(' Select a paper profile with measured thickness.' if not self.machine_setup.thickness_inches else '') if placeholder else f'Automatic crease depth: {self.machine_setup.crease_depth} / 5')
        except ValueError as exc:
            self.setup_status.setText(str(exc))

    def open_machine_guide(self):
        self.check_source()
        row = self.table.currentRow()
        if self.result is None or self.pdf_busy or not self.calculate_button.isEnabled() or not 0 <= row < len(self.result.candidates):
            return
        try:
            self.machine_setup = self.read_machine_setup()
            data = build_guide(self.job, self.profile, self.result.candidates[row],
                               (str(self.pdf_path), self.pdf_signature, self.page_choice.currentIndex(), asdict(self.registration_panel.settings())))
            if crease_depth_is_placeholder(self.machine_setup.thickness_inches,self.current_machine_profile().capabilities):
                data = replace(data,warnings=(*data.warnings,'Crease depth 2 is a placeholder because the thickness mapping is unavailable.'))
            candidate = self.result.candidates[row]
            marks = build_registration(candidate, self.profile, self.registration_panel.settings()).marks
            mark = next((m for m in marks if m.axis == 'machine'), None)
            registration_position = ((mark.rect.y_um, candidate.sheet_width_um-mark.rect.x_um-mark.rect.width_um) if mark else None)
            if self.guide is not None:
                self.layout_views.removeWidget(self.guide)
                self.guide.close()
                self.guide.deleteLater()
            self.guide = MachineGuideDialog(data, self.machine_setup, self, registration_position=registration_position, show_setup_inputs=False)
            self.guide.setWindowFlags(Qt.WindowType.Widget)
            self.layout_views.addWidget(self.guide)
            self.layout_views.setCurrentWidget(self.guide)
        except ValueError as exc:
            self.messages.setPlainText(str(exc))

    def closeEvent(self, event):
        self.artwork_library.close()
        self.back_panel.loader.close()
        if self.guide is not None:
            self.guide.close()
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
