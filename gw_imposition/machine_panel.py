"""Readable specifications and explicit provisional settings for the selected machine."""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit
from .units import inches


class MachinePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setWordWrap(True)
        self.title.setStyleSheet("font-size: 17px; font-weight: 600;")
        layout.addWidget(self.title)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        layout.addWidget(self.details)

    def set_profile(self, profile):
        self.title.setText(profile.name)
        lines = [f"Profile status: {profile.approval_state}"]
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
            lines.extend(["", "WORKBOOK SPECIFICATIONS", profile.source_document])
            for item in profile.specifications:
                lines.extend(["", item.label + ": " + item.value, "Source: " + item.source_cell])
        else:
            lines.extend(["", "Legacy/custom profile; additional workbook capabilities are unavailable."])
        self.details.setPlainText("\n".join(lines))
