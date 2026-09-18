"""Inline advanced finishing editor; distances are inches on the finished card."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QComboBox, QPushButton, QHeaderView, QDoubleSpinBox)
from .finishing import KINDS, FinishingOperation
from .units import to_um


class DistanceInput(QDoubleSpinBox):
    def textFromValue(self, value):
        return self.locale().toString(value, "f", self.decimals()).rstrip("0").rstrip(self.locale().decimalPoint())


def distance_input(value=0):
    field = DistanceInput()
    field.setRange(0, 1000)
    field.setDecimals(6)
    field.setSingleStep(.0625)
    field.setValue(value / 25400)
    field.setMinimumWidth(65)
    field.setKeyboardTracking(False)
    return field


class AdvancedFinishingEditor(QWidget):
    changed = Signal()

    def __init__(self, dimensions, parent=None):
        super().__init__(parent)
        self.dimensions = dimensions
        self.setMinimumHeight(390)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        help_text = QLabel("All distances are in inches on the finished card.\n"
            "Crease / cross perf position: from TOP.\n"
            "Strike / rotary position: from LEFT. Strike start/end: from TOP.")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Operation", "Position", "Start", "End"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumHeight(210)
        self.table.setMaximumHeight(300)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        self.add_button = QPushButton("Add operation")
        self.add_button.clicked.connect(lambda: self.add_operation())
        self.remove_button = QPushButton("Remove selected")
        self.remove_button.clicked.connect(self.remove_selected)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        layout.addLayout(buttons)
        rules = QLabel("Creases OR cross perfs (one interchangeable tool). Rotary perfs run the full sheet. "
                       "Up to 4 strike-tool positions across the sheet; coverage above 60% per tool warns of solenoid burnout.")
        rules.setWordWrap(True)
        layout.addWidget(rules)

    def set_operations(self, operations):
        self.table.setRowCount(0)
        for operation in operations:
            self.add_operation(operation, notify=False)

    def add_operation(self, operation=None, notify=True):
        if operation is None:
            try:
                _, height = self.dimensions()
            except ValueError:
                height = 50800
            operation = FinishingOperation("crease", max(1, height // 2))
        row = self.table.rowCount()
        self.table.insertRow(row)
        kind = QComboBox()
        for key, label in KINDS.items():
            kind.addItem(label, key)
        kind.setCurrentIndex(kind.findData(operation.kind))
        self.table.setCellWidget(row, 0, kind)
        for col, value in enumerate((operation.position_um, operation.start_um, operation.end_um), 1):
            field = distance_input(value)
            self.table.setCellWidget(row, col, field)
            field.valueChanged.connect(self.changed)
        kind.currentIndexChanged.connect(lambda *_: self.update_fields())
        kind.currentIndexChanged.connect(self.changed)
        self.update_fields()
        self.table.selectRow(row)
        if notify:
            self.changed.emit()

    def remove_selected(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
            self.changed.emit()

    def update_fields(self):
        for row in range(self.table.rowCount()):
            strike = self.table.cellWidget(row, 0).currentData() == "strike_perf"
            for col in (2, 3):
                field = self.table.cellWidget(row, col)
                field.setEnabled(strike)
                field.setToolTip("Distance from card top" if strike else "Only strike perfs use start/end distances")
            kind = self.table.cellWidget(row, 0).currentData()
            self.table.cellWidget(row, 1).setToolTip("Distance from card top" if kind in ("crease", "cross_perf") else "Distance from card left")

    def operations(self):
        operations = []
        for row in range(self.table.rowCount()):
            kind = self.table.cellWidget(row, 0).currentData()
            position = to_um(str(self.table.cellWidget(row, 1).value()))
            start, end = (to_um(str(self.table.cellWidget(row, c).value())) for c in (2, 3)) if kind == "strike_perf" else (0, 0)
            operations.append(FinishingOperation(kind, position, start, end))
        return tuple(operations)
