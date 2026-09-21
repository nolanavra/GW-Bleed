"""Right-column finishing presets, card diagram and inline advanced settings."""
from PySide6.QtCore import Signal, Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QComboBox, QFormLayout,
    QSpinBox, QPushButton, QScrollArea, QLayout)
from .finishing import KINDS, validate_operations
from .finishing_presets import PRESETS, preset_operations
from .finishing_editor import AdvancedFinishingEditor, distance_input
from .units import to_um, inches
from .machine_specs import validate_machine_finishing


class CardDiagram(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(140)
        self.setMaximumHeight(175)
        self.card = None

    def set_card(self, width, height, operations):
        self.card = width, height, operations
        self.update()

    def paintEvent(self, event):
        if not self.card:
            return
        width, height, operations = self.card
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = min((self.width()-48)/width, (self.height()-38)/height)
        rect = QRectF((self.width()-width*scale)/2, 24, width*scale, height*scale)
        painter.setPen(self.palette().windowText().color())
        painter.drawText(QRectF(0, 0, self.width(), 22), Qt.AlignmentFlag.AlignCenter, "Finished card • top edge")
        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(QPen(QColor("#71899A"), 1))
        painter.drawRect(rect)
        for op in operations:
            pen = QPen(QColor("#B66500" if op.kind == "crease" else "#00668C"), 2)
            pen.setStyle(Qt.PenStyle.DashDotLine if op.kind == "crease" else Qt.PenStyle.DashLine)
            painter.setPen(pen)
            if op.kind in ("crease", "cross_perf"):
                y = rect.top()+op.position_um*scale
                painter.drawLine(rect.left(), y, rect.right(), y)
            else:
                x = rect.left()+op.position_um*scale
                start, end = (op.start_um, op.end_um) if op.kind == "strike_perf" else (0, height)
                painter.drawLine(x, rect.top()+start*scale, x, rect.top()+end*scale)


class FinishingPanel(QScrollArea):
    applied = Signal(object)

    def __init__(self, dimensions, parent=None):
        super().__init__(parent)
        self.dimensions = dimensions
        self.profile = None
        self.operations = ()
        self.applied_rotation = 0
        self.draft_operations = ()
        self._updating = False
        self._last_preset = "none"
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("finishingBody")
        self.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        heading = QLabel("Creases and perforations")
        heading.setStyleSheet("font-size: 17px; font-weight: 600;")
        layout.addWidget(heading)
        self._rotation = 0
        self.flip_orientation = QPushButton('Flip orientation (0°)')
        self.flip_orientation.setToolTip('Rotate finishing relative to artwork; machine tool directions remain unchanged.')
        self.flip_orientation.clicked.connect(self.flip)
        self.preset = QComboBox()
        for key, label in PRESETS:
            self.preset.addItem(label, key)
        layout.addWidget(self.preset)
        self.description = QLabel()
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        self.options = QWidget()
        form = QFormLayout(self.options)
        form.setContentsMargins(0, 0, 0, 0)
        self.allowance = distance_input(1588)
        self.allowance.setValue(.0625)
        self.tuck = QComboBox(); self.tuck.addItem("Bottom panel", "bottom"); self.tuck.addItem("Top panel", "top")
        self.stub = distance_input(50800)
        self.edge = QComboBox(); self.edge.addItem("Right", "right"); self.edge.addItem("Bottom — cross perf", "bottom")
        self.columns = QSpinBox(); self.columns.setRange(1, 10); self.columns.setValue(2)
        self.rows = QSpinBox(); self.rows.setRange(1, 10); self.rows.setValue(3)
        self.flap = distance_input(0)
        self.flap.setMinimum(0)
        self.flap.setSpecialValueText('Enter flap size')
        self.vertical_tool = QComboBox()
        self.vertical_tool.addItem('Strike perf', 'strike_perf')
        self.vertical_tool.addItem('Rotary perf', 'rotary_perf')
        self.fields = {}
        for key, label, field in (("allowance", "Tuck allowance (in)", self.allowance),
                ("tuck", "Shorter tuck panel", self.tuck), ("stub", "Stub size (in)", self.stub),
                ("edge", "Detachable edge", self.edge), ("columns", "Coupon columns", self.columns),
                ("rows", "Coupon rows", self.rows), ("flap", "End-flap size (in)", self.flap),
                ("vertical_tool", "Vertical perforation", self.vertical_tool)):
            form.addRow(label, field)
            self.fields[key] = field
            signal = field.currentIndexChanged if isinstance(field, QComboBox) else field.valueChanged
            signal.connect(self.refresh)
        self.form = form
        layout.addWidget(self.options)
        self.advanced = AdvancedFinishingEditor(self.oriented_dimensions)
        self.advanced.changed.connect(self.refresh)
        layout.addWidget(self.advanced)
        self.diagram = CardDiagram()
        layout.addWidget(self.diagram)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.summary)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addWidget(self.flip_orientation)
        self.apply_button = QPushButton("Apply finishing")
        self.apply_button.clicked.connect(self.apply)
        layout.addWidget(self.apply_button)
        layout.addStretch()
        self.preset.currentIndexChanged.connect(self.preset_changed)
        self.refresh()

    def preset_changed(self):
        if self._updating:
            return
        key = self.preset.currentData()
        if key == "advanced" and self._last_preset != "advanced":
            self._updating = True
            self.advanced.set_operations(self.draft_operations if self.draft_operations is not None else self.operations)
            self._updating = False
        self._last_preset = key
        self.refresh()

    def flip(self):
        self._rotation = 90 if self._rotation == 0 else 0
        self.flip_orientation.setText(f'Flip orientation ({self._rotation}°)')
        self.refresh()

    @property
    def rotation(self):
        return self._rotation

    def oriented_dimensions(self):
        width, height = self.dimensions()
        return (height, width) if self.rotation == 90 else (width, height)

    def set_operations(self, operations, rotation=0):
        self._updating = True
        self.operations = tuple(operations)
        self.applied_rotation = rotation
        self._rotation = rotation
        self.flip_orientation.setText(f'Flip orientation ({rotation}°)')
        self.advanced.set_operations(operations)
        key = "advanced" if operations else "none"
        self.preset.setCurrentIndex(self.preset.findData(key))
        self._last_preset = key
        self._updating = False
        self.refresh()

    def set_profile(self, profile):
        self.profile = profile
        requirements = {"half": ("crease",), "accordion": ("crease",), "letter": ("crease",),
            "gate": ("crease",), "tent": ("crease", "strike_perf")}
        for index, (key, _) in enumerate(PRESETS):
            required = requirements.get(key, ())
            available = not profile.capabilities or all(getattr(profile.capabilities, kind) for kind in required)
            self.preset.model().item(index).setEnabled(available)
        self.refresh()

    def refresh(self, *_):
        if self._updating:
            return
        key = self.preset.currentData()
        self.advanced.setVisible(key == "advanced")
        visible = {"letter": ("allowance", "tuck"), "ticket": ("stub", "edge", "vertical_tool"),
                   "coupons": ("columns", "rows", "vertical_tool"), "tent": ("flap",)}.get(key, ())
        for name, field in self.fields.items():
            self.form.setRowVisible(field, name in visible)
        self.options.setVisible(bool(visible))
        descriptions = {
            "none": "Remove all creases and perforations.",
            "half": "One crease at half the card height. Two equal panels.",
            "accordion": "Two creases at one-third and two-thirds of the card height. Three equal panels.",
            "letter": "Two creases for a letter fold. The tuck panel is shorter by the allowance; the other two panels are equal.",
            "gate": "Creases at one-quarter and three-quarters of the card height. The two outer panels meet at the center.",
            "ticket": "One detachable strip. The stub size is measured inward from the selected card edge.",
            "coupons": "Equal coupons within each finished card: cross perfs between rows and the selected vertical tool between columns.",
            "tent": "End flap / side A / side B / end flap, with three creases. Each centerline strike perf runs from the outer cut edge halfway into its flap.",
            "advanced": "Add or edit each tool position below. Disabled start/end fields do not apply to that tool."}
        self.description.setText(descriptions[key])
        try:
            width, height = self.oriented_dimensions()
            if width <= 0 or height <= 0:
                raise ValueError("Enter positive finished card dimensions first.")
            ops = self.advanced.operations() if key == "advanced" else preset_operations(key, width, height,
                allowance=to_um(str(self.allowance.value())), tuck=self.tuck.currentData(),
                stub=to_um(str(self.stub.value())), edge=self.edge.currentData(),
                columns=self.columns.value(), rows=self.rows.value(), flap=to_um(str(self.flap.value())),
                vertical_tool=self.vertical_tool.currentData())
            validate_operations(ops, width, height)
            validate_machine_finishing(ops, self.profile)
            self.draft_operations = ops
            self.diagram.set_card(width, height, ops)
            self.diagram.show()
            lines = []
            for op in ops:
                axis = "top" if op.kind in ("crease", "cross_perf") else "left"
                text = f"{KINDS[op.kind]}: {inches(op.position_um)} in from {axis}"
                if op.kind == "strike_perf":
                    text += f"; {inches(op.start_um)}–{inches(op.end_um)} in from top"
                lines.append(text)
            self.summary.setText("\n".join(lines) if lines else "No finishing operations.")
            self.status.setText("" if ops == self.operations and self.rotation == self.applied_rotation else "Not applied")
            self.apply_button.setEnabled(True)
        except ValueError as exc:
            self.draft_operations = None
            self.diagram.hide()
            self.summary.clear()
            self.status.setText(str(exc))
            self.apply_button.setEnabled(False)

    def apply(self):
        self.refresh()
        if self.draft_operations is None:
            return
        self.operations = self.draft_operations
        self.applied_rotation = self.rotation
        self.applied.emit(self.operations)
        self.refresh()
