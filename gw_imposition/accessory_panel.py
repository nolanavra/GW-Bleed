from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QFormLayout, QSpinBox, QLabel
from .accessories import MachineAccessories, default_accessories, validate_accessories


class AccessoryPanel(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.profile = None
        self._updating = False
        self._by_machine = {}
        self.form = QFormLayout(self)
        self.machine_name = QLabel()
        self.machine_name.setWordWrap(True)
        self.form.addRow(self.machine_name)
        self.strikes = QSpinBox(); self.strikes.setRange(0, 4)
        self.automatic = QSpinBox(); self.automatic.setRange(0, 2)
        self.automatic.setToolTip('Automatic tools occupy the first strike positions and share the four-tool total with manual strike perfs.')
        self.rotary = QSpinBox(); self.rotary.setRange(0, 300)
        self.rotary.setToolTip('Installed tool count, not a verified machine capacity. Confirm physical spacing and tooling with the machine specification.')
        for label, field in (('Strike perfs', self.strikes), ('Auto strike perfs', self.automatic), ('Rotary perfs', self.rotary)):
            self.form.addRow(label, field)
            field.valueChanged.connect(self.edited)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.form.addRow(self.note)

    def settings(self):
        return MachineAccessories(self.strikes.value(), self.automatic.value(), self.rotary.value())

    def set_profile(self, profile):
        if self.profile is not None:
            self._by_machine[self.profile.id] = self.settings()
        self.profile = profile
        self.machine_name.setText(profile.name)
        self.set_settings(self._by_machine.get(profile.id, default_accessories(profile)))

    def set_settings(self, settings, inferred=False):
        validate_accessories(settings, self.profile)
        self._updating = True
        self.automatic.setValue(settings.auto_strike_perfs)
        self.strikes.setMaximum(4-settings.auto_strike_perfs)
        self.strikes.setValue(settings.strike_perfs)
        self.rotary.setValue(settings.rotary_perfs)
        cap = self.profile.capabilities
        self.form.setRowVisible(self.strikes, bool(cap and cap.strike_perf))
        self.form.setRowVisible(self.automatic, self.profile.id == 'pt_9375scc_supercut')
        self.form.setRowVisible(self.rotary, bool(cap and cap.rotary_perf))
        self.note.setText('Legacy job: tooling inferred from its operations. Confirm installed tools.' if inferred else '')
        self._updating = False

    def edited(self):
        if self._updating:
            return
        self._updating = True
        self.strikes.setMaximum(4-self.automatic.value())
        self._updating = False
        self.note.clear()
        self.changed.emit()
