"""Registration rectangles in printable waste outside the artwork grid."""
from dataclasses import dataclass, field
from .models import Rect
from .barcodes import BarcodeSettings


@dataclass(frozen=True)
class RegistrationSettings:
    enabled: bool = True
    thickness_um: int = 508
    length_um: int = 3175
    gap_um: int = 0
    barcode: BarcodeSettings = field(default_factory=BarcodeSettings)

    def __post_init__(self):
        if isinstance(self.barcode, dict):
            object.__setattr__(self, "barcode", BarcodeSettings(**self.barcode))
        if not isinstance(self.barcode, BarcodeSettings):
            raise ValueError("Invalid barcode settings.")
        if type(self.enabled) is not bool:
            raise ValueError("Registration marks enabled must be a boolean.")
        for name in ("thickness_um", "length_um", "gap_um"):
            value = getattr(self, name)
            if type(value) is not int or not (0 if name == "gap_um" else 1) <= value <= 254000:
                raise ValueError("Registration dimensions must be whole micrometres, positive (gap may be zero), and no more than 10 inches.")


@dataclass(frozen=True)
class RegistrationMark:
    side: str
    axis: str
    coordinate_um: int
    rect: Rect


@dataclass(frozen=True)
class RegistrationResult:
    marks: tuple[RegistrationMark, ...] = ()
    warnings: tuple[str, ...] = ()


def _waste_bands(intervals, sheet_end, thickness):
    """Return coordinate -> waste-side strip. Shared cuts without waste get no strip."""
    intervals = sorted(set(intervals))
    bands = {}
    previous = 0
    for index, (start, end) in enumerate(intervals):
        available = start-previous
        # Interior gutter has two distinct boundaries: keep their marks separate.
        size = min(thickness, available if index == 0 else available//2)
        if size > 0:
            bands[start] = (start-size, start)
            if index:
                bands[previous] = (previous, previous+size)
        previous = end
    size = min(thickness, sheet_end-previous)
    if size > 0:
        bands[previous] = (previous, previous+size)
    return bands


def build_registration(candidate, profile, settings):
    if not settings.enabled:
        return RegistrationResult()
    c = candidate
    m = profile.press_margins
    printable = (m.left_um, m.lead_um, c.sheet_width_um-m.right_um, c.sheet_height_um-m.trail_um)
    left = min(b.x_um for b in c.bleed_regions)
    top = min(b.y_um for b in c.bleed_regions)
    right = max(b.x_um+b.width_um for b in c.bleed_regions)
    bottom = max(b.y_um+b.height_um for b in c.bleed_regions)
    xb = _waste_bands(((p.x_um, p.x_um+p.width_um) for p in c.placements), c.sheet_width_um, settings.thickness_um)
    yb = _waste_bands(((p.y_um, p.y_um+p.height_um) for p in c.placements), c.sheet_height_um, settings.thickness_um)
    proposed = []
    gap, length = settings.gap_um, settings.length_um
    missing = dict(left=0, right=0, top=0, bottom=0)
    for y in c.cut_y_um:
        if y not in yb:
            missing["left"] += 1; missing["right"] += 1
            continue
        y1, y2 = yb[y]
        proposed.extend((("left", "cut", y, (left-gap-length, y1, left-gap, y2)),
                         ("right", "cut", y, (right+gap, y1, right+gap+length, y2))))
    for x in c.slitter_x_um:
        if x not in xb:
            missing["top"] += 1; missing["bottom"] += 1
            continue
        x1, x2 = xb[x]
        proposed.extend((("top", "slitter", x, (x1, top-gap-length, x2, top-gap)),
                         ("bottom", "slitter", x, (x1, bottom+gap, x2, bottom+gap+length))))
    marks, seen = [], set()
    shortened = 0
    for side, axis, coordinate, raw in proposed:
        x1, y1 = max(raw[0], printable[0]), max(raw[1], printable[1])
        x2, y2 = min(raw[2], printable[2]), min(raw[3], printable[3])
        if x1 >= x2 or y1 >= y2:
            missing[side] += 1
            continue
        rect = Rect(x1, y1, x2-x1, y2-y1)
        if rect in seen:
            continue
        seen.add(rect)
        shortened += (x2-x1 != (length if axis == "cut" else settings.thickness_um) or
                      y2-y1 != (settings.thickness_um if axis == "cut" else length))
        marks.append(RegistrationMark(side, axis, coordinate, rect))
    warnings = [f"{side.title()}: {count} marks omitted; no printable space or gutter outside the artwork."
                for side, count in missing.items() if count]
    if shortened:
        warnings.append(f"{shortened} marks shortened to fit printable margins or narrow gutters.")
    return RegistrationResult(tuple(marks), tuple(warnings))
