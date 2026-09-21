"""Operator-selected installed tooling, separate from machine capabilities."""
from dataclasses import dataclass


@dataclass(frozen=True)
class MachineAccessories:
    strike_perfs: int = 0
    auto_strike_perfs: int = 0
    rotary_perfs: int = 0

    def __post_init__(self):
        for name, limit in (('strike_perfs', 4), ('auto_strike_perfs', 2), ('rotary_perfs', 300)):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= limit:
                raise ValueError(f'Invalid installed {name.replace("_", " ")} count.')
        if self.strike_perfs + self.auto_strike_perfs > 4:
            raise ValueError('Manual and automatic strike perfs share a maximum of four positions.')

    @property
    def total_strikes(self):
        return self.strike_perfs + self.auto_strike_perfs


def default_accessories(profile):
    strike = bool(profile.capabilities and profile.capabilities.strike_perf)
    automatic = 2 if strike and profile.id == 'pt_9375scc_supercut' else 0
    return MachineAccessories(4-automatic if strike else 0, automatic, 0)


def validate_accessories(settings, profile, marks=()):
    if settings is None:  # Legacy engine requests retain their previous behavior.
        return
    cap = profile.capabilities
    if settings.total_strikes and (not cap or not cap.strike_perf):
        raise ValueError('This machine does not support strike perfs.')
    if settings.auto_strike_perfs and profile.id != 'pt_9375scc_supercut':
        raise ValueError('This machine does not support automatically positioned strike perfs.')
    if settings.rotary_perfs and (not cap or not cap.rotary_perf):
        raise ValueError('This machine does not support rotary perfs.')
    for kind, available in (('strike_perf', settings.total_strikes), ('rotary_perf', settings.rotary_perfs)):
        required = len({m.x1_um for m in marks if m.kind == kind})
        if required > available:
            raise ValueError(f'Layout needs {required} {kind.replace("_", " ")} tools; {available} installed. Review Machine Accessory Settings.')
