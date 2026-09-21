"""Immutable, Qt-free translation of sheet geometry into operator instructions."""
from dataclasses import dataclass, asdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json


@dataclass(frozen=True)
class GuideAdapter:
    machine_id: str
    automatic_strike_tools: int = 0


ADAPTERS = {name: GuideAdapter(name, 2 if name == 'pt_9375scc_supercut' else 0)
            for name in ('pt_331scc_air', 'pt_335scc_b_multi', 'pt_8336scc_multi', 'pt_9375scc_supercut')}


def machine_inches(um):
    return str((Decimal(um) / 25400).quantize(Decimal('.001'), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class MachineSetup:
    thickness_inches: str = ''
    crease_depth: int | None = None
    job_name: str = ''
    job_number: int | None = None

    def __post_init__(self):
        if self.job_number is not None and (type(self.job_number) is not int or not 0<=self.job_number<=999):
            raise ValueError('Machine job number must be 000–999.')
        if not isinstance(self.thickness_inches, str) or len(self.thickness_inches) > 40:
            raise ValueError('Invalid stock thickness.')
        if self.thickness_inches:
            try:
                value = Decimal(self.thickness_inches)
                if not value.is_finite() or value <= 0 or value.adjusted() > 6 or value.adjusted() < -20:
                    raise ValueError('Thickness must be a positive, finite inch measurement within numeric input limits.')
            except InvalidOperation as exc:
                raise ValueError('Enter stock thickness in inches.') from exc
        if self.crease_depth is not None and (type(self.crease_depth) is not int or not 0 <= self.crease_depth <= 10):
            raise ValueError('Crease depth must be an integer from 0 to 10.')
        if not isinstance(self.job_name, str) or len(self.job_name) > 200:
            raise ValueError('Job name must contain at most 200 characters.')

    @property
    def complete(self):
        return bool(self.thickness_inches) and self.crease_depth is not None


@dataclass(frozen=True)
class StrikeTool:
    number: int
    right_um: int
    automatic: bool
    segments: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class GuideData:
    identity: str
    candidate: object
    machine_name: str
    slits: tuple[int, ...]
    cuts: tuple[int, ...]
    creases: tuple[int, ...]
    cross_perf: bool
    strikes: tuple[StrikeTool, ...]
    physical: tuple[str, ...]
    conflicts: tuple[str, ...]
    warnings: tuple[str, ...]
    steps: tuple[str, ...]
    machine_id: str = ''


def build_guide(job, profile, candidate, source_identity=None):
    from .accessories import validate_accessories
    validate_accessories(job.accessories, profile, candidate.finishing)
    adapter = ADAPTERS.get(profile.id)
    if adapter is None:
        raise ValueError('Machine screen workflow has not been supplied for this model.')
    # Snapshot identity includes the selected alternative, never the recommendation by assumption.
    identity = hashlib.sha256(json.dumps([asdict(job), asdict(profile), asdict(candidate), source_identity],
                                       sort_keys=True, default=str).encode()).hexdigest()
    slits = tuple(sorted({candidate.sheet_width_um - x for x in candidate.slitter_x_um}))
    cuts = tuple(sorted(set(candidate.cut_y_um)))
    kinds = {m.kind for m in candidate.finishing}
    if {'crease', 'cross_perf'} <= kinds:
        raise ValueError('Creases and cross perfs cannot share the installed tool.')
    creases = tuple(sorted({m.y1_um for m in candidate.finishing if m.kind in ('crease', 'cross_perf')}))
    cap = profile.capabilities
    for kind in kinds:
        if cap is not None and not getattr(cap, kind, False):
            raise ValueError(f'The selected machine does not support {kind}.')
    positions = sorted({candidate.sheet_width_um-m.x1_um for m in candidate.finishing if m.kind == 'strike_perf'})
    if len(positions) > 4:
        raise ValueError('At most four strike-tool positions are supported.')
    automatic = job.accessories.auto_strike_perfs if job.accessories is not None else adapter.automatic_strike_tools
    strikes = tuple(StrikeTool(i+1, x, i < automatic,
                    tuple(sorted((m.y1_um, m.y2_um) for m in candidate.finishing
                                 if m.kind == 'strike_perf' and candidate.sheet_width_um-m.x1_um == x)))
                    for i, x in enumerate(positions))
    physical = []
    if 'cross_perf' in kinds:
        physical.append('Install the cross-perf tool in place of the crease tool; use the crease-position entries.')
    elif creases:
        physical.append('Confirm the crease tool is installed.')
    for tool in strikes:
        if not tool.automatic:
            physical.append(f'Strike tool {tool.number}: physically position {machine_inches(tool.right_um)} in from the right paper edge.')
    rotary = sorted({candidate.sheet_width_um-m.x1_um for m in candidate.finishing if m.kind == 'rotary_perf'})
    physical.extend(f'Rotary perf: physically install {machine_inches(x)} in from the right paper edge; must perforate the full sheet length. No program entry.' for x in rotary)
    conflicts = []
    def collisions(label, values):
        seen = {}
        for value in sorted(set(values)):
            rounded = machine_inches(value)
            if rounded in seen:
                conflicts.append(f'{label}: distinct positions {seen[rounded]} and {value} µm both display {rounded} in.')
            seen[rounded] = value
    for label, values in [('Slitters', slits), ('Cuts', cuts), ('Crease/cross perf', creases), ('Strike sideways', positions), ('Rotary sideways', rotary)]:
        collisions(label, values)
    for tool in strikes:
        collisions(f'Strike tool {tool.number}', [v for pair in tool.segments for v in pair])
        for start, end in tool.segments:
            if machine_inches(start) == machine_inches(end):
                conflicts.append(f'Strike tool {tool.number}: segment collapses at machine precision.')
    warnings = list(candidate.finishing_warnings)
    warnings.append('Workflow unverified: confirm on the real machine. Entry capacities, firmware pagination, adjustment controls, Test and Run behavior are unverified.')
    steps = ['Sheet', 'Slitters', 'Cuts']
    if creases:
        steps.append('Cross perf' if 'cross_perf' in kinds else 'Crease')
    if strikes:
        steps.append('Strike perfs')
    steps.extend(['Physical tooling', 'Review'])
    return GuideData(identity, candidate, profile.name, slits, cuts, creases, 'cross_perf' in kinds,
                     strikes, tuple(physical), tuple(conflicts), tuple(warnings), tuple(steps), profile.id)
