"""Readable specifications and explicit provisional settings for the selected machine."""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QComboBox, QPushButton, QMessageBox
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from .units import inches
from .machine_manuals import catalog, documents_for, machine_context, manual_path


class MachinePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setWordWrap(True)
        self.title.setStyleSheet("font-size: 17px; font-weight: 600;")
        layout.addWidget(self.title)
        self.manuals = QComboBox()
        self.manuals.setAccessibleName('Bundled machine manuals')
        self.manuals.setToolTip('Original supplied manuals. PDF page numbers in descriptions include covers and contents. Pending mappings are not machine compatibility claims.')
        layout.addWidget(self.manuals)
        self.manual_summary = QTextEdit()
        self.manual_summary.setReadOnly(True)
        self.manual_summary.setAccessibleName('Selected manual provenance and review notes')
        self.manual_summary.setMaximumHeight(120)
        layout.addWidget(self.manual_summary)
        self.manuals.currentIndexChanged.connect(self.show_manual_summary)
        self.open_manual_button = QPushButton('Open manual PDF…')
        self.open_manual_button.clicked.connect(self.open_manual)
        layout.addWidget(self.open_manual_button)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        layout.addWidget(self.details)

    def show_manual_summary(self):
        doc = next((d for d in catalog()['documents'] if d['id'] == self.manuals.currentData()), None)
        if doc is None:
            self.manual_summary.clear()
            return
        notes = '\n'.join(f"PDF p. {', '.join(map(str, n['pages']))}: {n['text']}" for n in doc['notes'])
        self.manual_summary.setPlainText(f"{doc['pages']} pages | {doc['mapping_status']}\n" +
                                   (notes or 'Reference archived; model applicability and settings review pending.'))
        self.manual_summary.setToolTip('SHA-256: ' + doc['sha256'])

    def open_manual(self):
        try:
            path = manual_path(self.manuals.currentData(), verify=True)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
                raise ValueError('No PDF viewer opened the manual. Install or select a default PDF viewer.')
        except (ValueError, OSError, StopIteration) as exc:
            QMessageBox.warning(self, 'Cannot open manual', str(exc))

    def set_profile(self, profile):
        self.title.setText(profile.name)
        matched = {d['id'] for d in documents_for(profile.id)}
        self.manuals.clear()
        for doc in sorted(catalog()['documents'], key=lambda d: d['id'] not in matched):
            label = 'This model' if doc['id'] in matched else doc['mapping_status']
            self.manuals.addItem(f"{doc['filename']} — {label}", doc['id'])
        lines = [f"Profile status: {profile.approval_state}", '', 'MANUAL SOURCES',
                 machine_context(profile.id),
                 'Manuals take precedence once model and revision applicability are confirmed. Technical service procedures are not operator programming steps. Physical validation remains separate.',
                 'Current profile limits below remain provisional wherever reconciliation is pending.']
        cap = profile.capabilities
        if cap:
            lines.extend(["", "ENFORCED LAYOUT LIMITS",
                f"Input width: {inches(cap.min_sheet_width_um)}–{inches(cap.max_sheet_width_um)} in",
                f"Input feed length: {inches(cap.min_sheet_height_um)}–{inches(cap.max_sheet_height_um)} in",
                f"Minimum finished width × feed length: {inches(cap.min_finished_width_um)} × {inches(cap.min_finished_height_um)} in",
                f"Slitters: {cap.max_slitters}; maximum columns: {profile.max_columns}",
                f"Gutter: {profile.minimum_gutter_um/1000:g}–{profile.maximum_gutter_um/1000:g} mm" + (" or 0 mm with zero bleed" if profile.allow_shared_cut else ""),
                "Finishing: " + (", ".join(kind.replace("_", " ") for kind in ("crease", "cross_perf", "rotary_perf", "strike_perf") if getattr(cap, kind)) or "None (slit/cut only)")])
            if cap.max_side_trim_um is not None:
                lines.append(f"Side trim: 0–{cap.max_side_trim_um/1000:g} mm per paper edge to outer finished-card edge (includes bleed)")
        if profile.setup_notes:
            lines.extend(["", "SETUP NOTES", *profile.setup_notes])
        if profile.specifications:
            lines.extend(["", "LEGACY WORKBOOK REFERENCE — SUBJECT TO MANUAL RECONCILIATION", profile.source_document])
            for item in profile.specifications:
                lines.extend(["", item.label + ": " + item.value, "Source: " + item.source_cell])
        else:
            lines.extend(["", "Legacy/custom profile; additional workbook capabilities are unavailable."])
        self.details.setPlainText("\n".join(lines))
