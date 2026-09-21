"""Source-backed machine capabilities; unknown setup settings stay explicit."""
from dataclasses import dataclass


@dataclass(frozen=True)
class MachineCapabilities:
    min_sheet_width_um: int
    min_sheet_height_um: int
    max_sheet_width_um: int
    max_sheet_height_um: int
    min_finished_width_um: int
    min_finished_height_um: int
    max_slitters: int
    crease: bool
    cross_perf: bool
    rotary_perf: bool
    strike_perf: bool
    gutter_mode: str
    fixed_gutters_um: tuple[int, ...] = ()
    strike_optional: bool = False
    max_side_trim_um: int | None = None
    barcode_reader: bool = False
    min_paper_thickness_um: int | None = None
    max_paper_thickness_um: int | None = None

    def __post_init__(self):
        for name in ("min_sheet_width_um", "min_sheet_height_um", "max_sheet_width_um", "max_sheet_height_um",
                     "min_finished_width_um", "min_finished_height_um", "max_slitters"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"Machine capability {name} must be a positive integer.")
        if self.min_sheet_width_um > self.max_sheet_width_um or self.min_sheet_height_um > self.max_sheet_height_um:
            raise ValueError("Machine sheet-size limits are reversed.")
        for name in ("crease", "cross_perf", "rotary_perf", "strike_perf", "strike_optional", "barcode_reader"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"Machine capability {name} must be a boolean.")
        if self.gutter_mode not in ("fixed", "variable"):
            raise ValueError("Machine gutter mode must be fixed or variable.")
        if any(type(g) is not int or g <= 0 for g in self.fixed_gutters_um):
            raise ValueError("Fixed gutters must be positive integer micrometres.")
        object.__setattr__(self, "fixed_gutters_um", tuple(self.fixed_gutters_um))
        if self.max_side_trim_um is not None and (type(self.max_side_trim_um) is not int or self.max_side_trim_um < 0):
            raise ValueError("Maximum side trim must be a nonnegative integer micrometre dimension.")
        limits = (self.min_paper_thickness_um, self.max_paper_thickness_um)
        if limits != (None,None):
            if any(type(v) is not int or v <= 0 for v in limits) or limits[0] >= limits[1]:
                raise ValueError('Paper thickness limits must be positive integers with minimum below maximum.')


@dataclass(frozen=True)
class Specification:
    label: str
    value: str
    source_cell: str


def validate_machine_finishing(operations, profile):
    if not profile or not profile.capabilities:
        return
    from .finishing import KINDS
    for kind in sorted({op.kind for op in operations}):
        if not getattr(profile.capabilities, kind):
            raise ValueError(f"{profile.name} does not support {KINDS[kind].lower()} according to the supplied specifications.")
