"""Registration controls are export settings, independent of preview visibility."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFormLayout, QCheckBox, QGroupBox, QLineEdit, QScrollArea, QLayout
from .registration import RegistrationSettings
from .barcodes import BarcodeSettings, has_barcode_reader


class RegistrationPanel(QScrollArea):
    changed = Signal()
    visibility_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False
        self.reader_available = False
        self._profile_id = None
        self._reader_choices = {}
        self._machine_mark_thickness_um = 1000
        self._machine_mark_length_um = 5000
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
        self._thickness_um = 508
        self._length_um = 5080
        self._gap_um = 0
        self.mark_dimensions = QLabel('Marks: .02 in thick × .2 in long')
        layout.addWidget(self.mark_dimensions)
        self.machine_mark = QCheckBox('Generate dedicated L-shaped machine registration mark')
        self.machine_mark.setToolTip('Barcode-reader machines: two perpendicular arms inside the 3–20 mm top/right edge region. The horizontal arm extends left, the vertical arm down. Guide positions measure to the outer top and right edges.')
        self.machine_mark.toggled.connect(self.settings_changed)
        layout.addWidget(self.machine_mark)
        self.machine_mark_size = QLabel('L-mark: 1 mm thick × 5 mm arms')
        layout.addWidget(self.machine_mark_size)
        self.machine_mark_status = QLabel()
        self.machine_mark_status.setWordWrap(True)
        layout.addWidget(self.machine_mark_status)
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
        self.barcode_group = QGroupBox("Barcode")
        barcode_layout = QVBoxLayout(self.barcode_group)
        self.barcode_enabled = QCheckBox("Generate barcode in preview and exported PDF")
        barcode_layout.addWidget(self.barcode_enabled)
        barcode_form = QFormLayout()
        self.barcode_value = QLineEdit()
        self.barcode_value.setMaxLength(5)
        self.barcode_value.setPlaceholderText('JJJQQ, e.g. 12305')
        self.barcode_value.setToolTip('First three digits: saved machine job number (000–999). Last two: quantity (00–99). Do not enter the Code 39 start/stop asterisks.')
        self.barcode_value.setReadOnly(True)
        barcode_form.addRow('Generated Code 39', self.barcode_value)
        barcode_form.addRow(QLabel('Black bars: 45 × 6.5 mm · Right edge: 52 mm'))
        barcode_layout.addLayout(barcode_form)
        self.barcode_status = QLabel()
        self.barcode_status.setWordWrap(True)
        barcode_layout.addWidget(self.barcode_status)
        layout.addWidget(self.barcode_group)
        self.barcode_group.hide()
        self.barcode_value.textChanged.connect(self.settings_changed)
        self.barcode_enabled.toggled.connect(self.settings_changed)
        layout.addStretch()

    def set_artwork_bleed(self, horizontal, vertical):
        self._gap_um = 1270 if horizontal == 0 and vertical == 0 else 0

    def settings(self):
        return RegistrationSettings(self.enabled.isChecked(), self._thickness_um,
                                    self._length_um, self._gap_um,
                                    BarcodeSettings(self.reader_available and self.barcode_enabled.isChecked(),
                                        self.barcode_value.text(), 'code39',
                                        254, 6500, True, 0, 4000),
                                    machine_mark_enabled=self.machine_mark.isChecked(),
                                    machine_mark_thickness_um=self._machine_mark_thickness_um,
                                    machine_mark_length_um=self._machine_mark_length_um)

    def set_settings(self, settings):
        self._updating = True
        self.enabled.setChecked(settings.enabled)
        self.machine_mark.setChecked(settings.machine_mark_enabled)
        self._machine_mark_length_um = settings.machine_mark_length_um
        self._machine_mark_thickness_um = settings.machine_mark_thickness_um
        self.machine_mark_size.setText(f'L-mark: {self._machine_mark_thickness_um/1000:g} mm thick × {self._machine_mark_length_um/1000:g} mm arms')
        b = settings.barcode
        self.barcode_enabled.setChecked(self.reader_available and b.enabled)
        valid_payload = b.symbology=='code39' and len(b.value)==5 and b.value.isascii() and b.value.isdigit()
        self.barcode_value.setText(b.value if valid_payload else '')
        self._updating = False
        self.settings_changed()

    def settings_changed(self, *_):
        self.machine_mark.setEnabled(self.enabled.isChecked() and self.reader_available)
        self.machine_mark_size.setEnabled(self.enabled.isChecked() and self.machine_mark.isChecked() and self.reader_available)
        if not self._updating:
            self.changed.emit()

    def set_profile(self, profile):
        from .machine_manuals import contextual_tooltip
        self.machine_mark.setToolTip(contextual_tooltip(profile.id,
            'L-mark: 3–20 mm from top/right edges, measured to outer arm edges. Arms ≥5 mm long and ≥0.4 mm thick. Manual/firmware applicability remains unverified.', 'registration'))
        self.barcode_value.setToolTip(contextual_tooltip(profile.id,
            'JJJQQ: machine job number and required sheet count, calculated from card quantity. Distances measure to black bars, excluding quiet zones. Confirm reader alignment on the installed machine.', 'barcode'))
        if self._profile_id != profile.id:
            if self._profile_id is not None and self.reader_available:
                self._reader_choices[self._profile_id] = (self.machine_mark.isChecked(), self.barcode_enabled.isChecked())
            self._updating = True
            self.reader_available = has_barcode_reader(profile)
            marks, barcode = self._reader_choices.get(profile.id, (self.reader_available, self.reader_available))
            self.machine_mark.setChecked(marks if self.reader_available else False)
            self.barcode_enabled.setChecked(barcode if self.reader_available else False)
            self._profile_id = profile.id
            self._updating = False
        self.reader_available = has_barcode_reader(profile)
        self.machine_mark.setVisible(self.reader_available)
        self.machine_mark_size.setVisible(self.reader_available)
        self.barcode_group.setVisible(self.reader_available)
        if not self.reader_available:
            self.machine_mark.setChecked(False)
            self.barcode_enabled.setChecked(False)
            self.barcode_status.clear()
        self.settings_changed()

    def show_result(self, candidate=None, profile=None, result=None):
        if candidate is None:
            self.machine_mark_status.clear()
            self.machine.setText("Select a layout to generate marks.")
            self.counts.clear()
            self.warnings.clear()
            return
        self.machine.setText(f"{profile.name}\n{candidate.stock_id} | {candidate.columns} × {candidate.rows} | {candidate.rotation}°")
        mark = next((m for m in result.marks if m.axis == 'machine'), None)
        self.machine_mark_status.setText(
            f'Dedicated mark: {mark.rect.y_um/25400:.3f} in from leading edge (top); '
            f'{(candidate.sheet_width_um-mark.rect.x_um-mark.rect.width_um)/25400:.3f} in from right edge. Reader placement remains unverified.'
            if mark else 'Dedicated L-shaped machine mark is disabled or unavailable.')
        if not self.enabled.isChecked():
            self.counts.setText("Registration marks are disabled for preview and export.")
        else:
            counts = {side: sum(mark.side == side for mark in result.marks) for side in ("top", "bottom", "left", "right")}
            self.counts.setText(f"{len(result.marks)} marks — " + " | ".join(f"{side.title()}: {count}" for side, count in counts.items()))
        self.warnings.setText("\n".join(result.warnings))
