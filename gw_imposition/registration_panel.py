"""Registration controls are export settings, independent of preview visibility."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFormLayout, QCheckBox, QGroupBox, QLineEdit, QComboBox, QScrollArea, QLayout
from .finishing_editor import distance_input
from .registration import RegistrationSettings
from .units import to_um
from .barcodes import BarcodeSettings, has_barcode_reader


class RegistrationPanel(QScrollArea):
    changed = Signal()
    visibility_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False
        self.reader_available = False
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("registrationBody")
        self.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        title = QLabel("Registration marks")
        title.setStyleSheet("font-size: 17px; font-weight: 600;")
        layout.addWidget(title)
        self.enabled = QCheckBox("Include registration marks in exported PDFs")
        self.enabled.setChecked(True)
        layout.addWidget(self.enabled)
        self.show_preview = QCheckBox("Show registration marks in sheet preview")
        self.show_preview.setChecked(True)
        self.show_preview.toggled.connect(self.visibility_changed)
        layout.addWidget(self.show_preview)
        note = QLabel("Small solid-black rectangles outside the artwork grid. Each starts at a cut or slitter coordinate, "
            "with its thickness extending into waste or a gutter. Marks follow the selected machine's printable margins and layout.")
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.thickness = distance_input(508)
        self.length = distance_input(3175)
        self.gap = distance_input(0)
        for label, field in (("Thickness (in)", self.thickness), ("Length (in)", self.length), ("Gap from artwork (in)", self.gap)):
            field.setMaximum(10)
            if field is not self.gap:
                field.setMinimum(.00004)
            form.addRow(label, field)
            field.valueChanged.connect(self.settings_changed)
        layout.addLayout(form)
        self.enabled.toggled.connect(self.settings_changed)
        self.machine = QLabel("Select a layout to generate marks.")
        self.machine.setWordWrap(True)
        layout.addWidget(self.machine)
        self.counts = QLabel()
        self.counts.setWordWrap(True)
        layout.addWidget(self.counts)
        self.warnings = QLabel()
        self.warnings.setWordWrap(True)
        layout.addWidget(self.warnings)
        export_note = QLabel("Settings update immediately. Marks are included in all three export modes when enabled. "
            "Hiding the preview marks does not change export. The PDF page remains the exact selected stock size.")
        export_note.setWordWrap(True)
        layout.addWidget(export_note)
        self.barcode_group = QGroupBox("Barcode")
        barcode_layout = QVBoxLayout(self.barcode_group)
        self.barcode_enabled = QCheckBox("Generate barcode in preview and exported PDF")
        barcode_layout.addWidget(self.barcode_enabled)
        barcode_form = QFormLayout()
        self.barcode_value = QLineEdit()
        self.barcode_value.setMaxLength(64)
        self.barcode_value.setPlaceholderText("Value / saved machine job number")
        self.barcode_format = QComboBox()
        self.barcode_format.addItem("Code 128", "code128")
        self.barcode_format.addItem("Code 39 (no optional checksum)", "code39")
        self.barcode_module = distance_input(254)
        self.barcode_module.setRange(100/25400, 2000/25400)
        self.barcode_height = distance_input(3175)
        self.barcode_height.setRange(1000/25400, 100000/25400)
        self.barcode_auto = QCheckBox("Automatic position above artwork")
        self.barcode_auto.setChecked(True)
        self.barcode_x = distance_input()
        self.barcode_y = distance_input()
        for field in (self.barcode_x, self.barcode_y):
            field.setMaximum(2000000/25400)
        for label, field in (("Value", self.barcode_value), ("Format", self.barcode_format),
                ("Narrow bar width (in)", self.barcode_module), ("Bar height (in)", self.barcode_height)):
            barcode_form.addRow(label, field)
        barcode_form.addRow(self.barcode_auto)
        barcode_form.addRow("Left position (in)", self.barcode_x)
        barcode_form.addRow("Top position (in)", self.barcode_y)
        barcode_layout.addLayout(barcode_form)
        help_text = QLabel("Position includes the white quiet zone. Ten narrow-bar widths are reserved on each side. "
            "Confirm the reader's format, job value and scan position; the spreadsheet specifies reader availability only.")
        help_text.setWordWrap(True)
        barcode_layout.addWidget(help_text)
        self.barcode_status = QLabel()
        self.barcode_status.setWordWrap(True)
        barcode_layout.addWidget(self.barcode_status)
        layout.addWidget(self.barcode_group)
        self.barcode_group.hide()
        self.barcode_value.textChanged.connect(self.settings_changed)
        self.barcode_format.currentIndexChanged.connect(self.settings_changed)
        for field in (self.barcode_module, self.barcode_height, self.barcode_x, self.barcode_y):
            field.valueChanged.connect(self.settings_changed)
        self.barcode_enabled.toggled.connect(self.settings_changed)
        self.barcode_auto.toggled.connect(self.settings_changed)
        layout.addStretch()

    def settings(self):
        return RegistrationSettings(self.enabled.isChecked(), to_um(str(self.thickness.value())),
                                    to_um(str(self.length.value())), to_um(str(self.gap.value())),
                                    BarcodeSettings(self.reader_available and self.barcode_enabled.isChecked(),
                                        self.barcode_value.text(), self.barcode_format.currentData(),
                                        to_um(str(self.barcode_module.value())), to_um(str(self.barcode_height.value())),
                                        self.barcode_auto.isChecked(), to_um(str(self.barcode_x.value())), to_um(str(self.barcode_y.value()))))

    def set_settings(self, settings):
        self._updating = True
        self.enabled.setChecked(settings.enabled)
        self.thickness.setValue(settings.thickness_um/25400)
        self.length.setValue(settings.length_um/25400)
        self.gap.setValue(settings.gap_um/25400)
        b = settings.barcode
        self.barcode_enabled.setChecked(self.reader_available and b.enabled)
        self.barcode_value.setText(b.value)
        self.barcode_format.setCurrentIndex(self.barcode_format.findData(b.symbology))
        self.barcode_module.setValue(b.module_um/25400)
        self.barcode_height.setValue(b.height_um/25400)
        self.barcode_auto.setChecked(b.automatic)
        self.barcode_x.setValue(b.x_um/25400)
        self.barcode_y.setValue(b.y_um/25400)
        self._updating = False
        self.settings_changed()

    def settings_changed(self, *_):
        for field in (self.thickness, self.length, self.gap):
            field.setEnabled(self.enabled.isChecked())
        barcode_enabled = self.reader_available and self.barcode_enabled.isChecked()
        for field in (self.barcode_value, self.barcode_format, self.barcode_module, self.barcode_height, self.barcode_auto):
            field.setEnabled(barcode_enabled)
        for field in (self.barcode_x, self.barcode_y):
            field.setEnabled(barcode_enabled and not self.barcode_auto.isChecked())
        if not self._updating:
            self.changed.emit()

    def set_profile(self, profile):
        self.reader_available = has_barcode_reader(profile)
        self.barcode_group.setVisible(self.reader_available)
        if not self.reader_available:
            self.barcode_enabled.setChecked(False)
            self.barcode_status.clear()
        self.settings_changed()

    def show_result(self, candidate=None, profile=None, result=None):
        if candidate is None:
            self.machine.setText("Select a layout to generate marks.")
            self.counts.clear()
            self.warnings.clear()
            return
        self.machine.setText(f"{profile.name}\n{candidate.stock_id} | {candidate.columns} × {candidate.rows} | {candidate.rotation}°")
        if not self.enabled.isChecked():
            self.counts.setText("Registration marks are disabled for preview and export.")
        else:
            counts = {side: sum(mark.side == side for mark in result.marks) for side in ("top", "bottom", "left", "right")}
            self.counts.setText(f"{len(result.marks)} marks — " + " | ".join(f"{side.title()}: {count}" for side, count in counts.items()))
        self.warnings.setText("\n".join(result.warnings))
