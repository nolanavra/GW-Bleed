from dataclasses import dataclass
from .finishing import FinishingOperation, FinishingMark, validate_operations
from .machine_specs import MachineCapabilities, Specification


def positive(value: int, name: str, *, zero: bool = False) -> None:
    if type(value) is not int or value < (0 if zero else 1):
        raise ValueError(f"{name} must be a {'nonnegative' if zero else 'positive'} integer.")


@dataclass(frozen=True)
# “A watched crucible never transmutes.”
class Rect:
    x_um: int
    y_um: int
    width_um: int
    height_um: int


@dataclass(frozen=True)
class Margins:
    left_um: int
    right_um: int
    lead_um: int
    trail_um: int

    def __post_init__(self):
        for name, value in vars(self).items():
            positive(value, name, zero=True)


@dataclass(frozen=True)
class Stock:
    id: str
    width_um: int
    height_um: int
    available: bool = True
    preferred: bool = False

    def __post_init__(self):
        positive(self.width_um, "Stock width")
        positive(self.height_um, "Stock height")


@dataclass(frozen=True)
class MachineProfile:
    schema_version: int
    id: str
    version: str
    name: str
    approval_state: str
    stocks: tuple[Stock, ...]
    press_margins: Margins
    finisher_margins: Margins
    feed_edges: tuple[str, ...]
    allow_rotation: bool
    minimum_gutter_um: int
    maximum_gutter_um: int
    gutter_increment_um: int
    max_columns: int
    max_rows: int
    allow_shared_cut: bool = False
    capabilities: MachineCapabilities | None = None
    specifications: tuple[Specification, ...] = ()
    source_document: str = ""
    source_sha256: str = ""
    setup_notes: tuple[str, ...] = ()

    def __post_init__(self):
        if self.schema_version not in (1, 2):
            raise ValueError("Unsupported profile schema version.")
        if self.capabilities is not None and not isinstance(self.capabilities, MachineCapabilities):
            raise ValueError("Invalid machine capabilities.")
        if any(not isinstance(s, Specification) for s in self.specifications):
            raise ValueError("Invalid machine specification metadata.")
        if any(not isinstance(s, str) for s in self.setup_notes):
            raise ValueError("Invalid machine setup notes.")
        if not self.id or not self.version or not self.name:
            raise ValueError("Profile identity, version and name are required.")
        if self.approval_state not in ("demonstration", "unverified", "approved"):
            raise ValueError("Invalid profile approval state.")
        if not self.stocks or len({s.id for s in self.stocks}) != len(self.stocks):
            raise ValueError("Provide stocks with unique IDs.")
        if self.feed_edges != ("short",):
            raise ValueError("Only short-edge feeding is supported: feed_edges must be ['short'] (12-inch or 13-inch edge for standard stock).")
        for name in ("minimum_gutter_um", "maximum_gutter_um"):
            positive(getattr(self, name), name, zero=True)
        for name in ("gutter_increment_um", "max_columns", "max_rows"):
            positive(getattr(self, name), name)
        if self.max_columns > 3:
            raise ValueError("Machines support a maximum of 3 columns.")
        if self.maximum_gutter_um < self.minimum_gutter_um:
            raise ValueError("Maximum gutter cannot be smaller than minimum gutter.")


@dataclass(frozen=True)
class Job:
    width_um: int
    height_um: int
    bleed_um: int = 0
    gutter_um: int = 0
    shared_cut: bool = False
    bleed_y_um: int | None = None
    finishing: tuple[FinishingOperation, ...] = ()

    def __post_init__(self):
        for name in ("width_um", "height_um"):
            positive(getattr(self, name), name)
        for name in ("bleed_um", "gutter_um"):
            positive(getattr(self, name), name, zero=True)
        if self.bleed_y_um is not None:
            positive(self.bleed_y_um, "bleed_y_um", zero=True)
        operations = tuple(FinishingOperation(**op) if isinstance(op, dict) else op for op in self.finishing)
        if any(not isinstance(op, FinishingOperation) for op in operations):
            raise ValueError("Invalid finishing operation.")
        object.__setattr__(self, "finishing", operations)
        validate_operations(operations, self.width_um, self.height_um)

    @property
    def vertical_bleed_um(self):
        return self.bleed_um if self.bleed_y_um is None else self.bleed_y_um


@dataclass(frozen=True)
class Line:
    x1_um: int
    y1_um: int
    x2_um: int
    y2_um: int


@dataclass(frozen=True)
class Candidate:
    stock_id: str
    feed_edge: str
    rotation: int
    sheet_width_um: int
    sheet_height_um: int
    usable: Rect
    rows: int
    columns: int
    yield_per_sheet: int
    waste_area_um2: int
    placements: tuple[Rect, ...]
    bleed_regions: tuple[Rect, ...]
    slitter_x_um: tuple[int, ...]
    cut_y_um: tuple[int, ...]
    slitters: tuple[Line, ...]
    cuts: tuple[Line, ...]
    rank_key: tuple
    finishing: tuple[FinishingMark, ...] = ()
    finishing_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Rejection:
    stock_id: str
    feed_edge: str
    rotation: int
    code: str
    message: str


@dataclass(frozen=True)
class Calculation:
    profile_id: str
    profile_version: str
    profile_approval_state: str
    warnings: tuple[str, ...]
    candidates: tuple[Candidate, ...]
    rejections: tuple[Rejection, ...]

    @property
    def recommended(self) -> Candidate | None:
        return self.candidates[0] if self.candidates else None
