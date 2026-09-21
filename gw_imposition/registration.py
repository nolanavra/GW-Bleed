"""Registration rectangles in printable waste outside the artwork grid."""
from dataclasses import dataclass, field
from .models import Rect
from .barcodes import BarcodeSettings, has_barcode_reader, overlaps


@dataclass(frozen=True)
class RegistrationSettings:
    enabled: bool = True
    thickness_um: int = 508
    length_um: int = 5080
    gap_um: int = 0
    barcode: BarcodeSettings = field(default_factory=BarcodeSettings)
    machine_mark_enabled: bool = False
    machine_mark_thickness_um: int = 1000
    machine_mark_length_um: int = 5000

    def __post_init__(self):
        if isinstance(self.barcode, dict):
            object.__setattr__(self, "barcode", BarcodeSettings(**self.barcode))
        if not isinstance(self.barcode, BarcodeSettings):
            raise ValueError("Invalid barcode settings.")
        if type(self.enabled) is not bool:
            raise ValueError("Registration marks enabled must be a boolean.")
        if type(self.machine_mark_enabled) is not bool:
            raise ValueError('Machine registration mark enabled must be a boolean.')
        if type(self.machine_mark_length_um) is not int or not 5000<=self.machine_mark_length_um<=17000:
            raise ValueError('Dedicated mark arm length must be 5–17 mm to fit the corner region.')
        if type(self.machine_mark_thickness_um) is not int or not 400<=self.machine_mark_thickness_um<self.machine_mark_length_um:
            raise ValueError('Dedicated mark thickness must be at least 0.4 mm and less than its arm length.')
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
    if settings.machine_mark_enabled:
        arm,thick = settings.machine_mark_length_um,settings.machine_mark_thickness_um
        # A top/right corner (┐): the horizontal arm extends left and vertical
        # arm down. Both complete rectangles must fit within the 3–20 mm band.
        zone_left=max(c.sheet_width_um-20000,printable[0])
        zone_right=min(c.sheet_width_um-3000,printable[2])
        zone_top=max(3000,printable[1])
        zone_bottom=min(20000,printable[3])
        obstacles=[*c.bleed_regions,*(mark.rect for mark in marks)]
        for line in (*c.cuts,*c.slitters,*c.finishing):
            obstacles.append(Rect(line.x1_um-100,line.y1_um-100,line.x2_um-line.x1_um+200,line.y2_um-line.y1_um+200))
        xs={zone_right-arm,zone_left}
        ys={zone_top,zone_bottom-arm}
        for box in obstacles:
            xs.update((box.x_um-arm,box.x_um+box.width_um,box.x_um-thick))
            ys.update((box.y_um-arm,box.y_um+box.height_um,box.y_um-thick))
        chosen=None
        if has_barcode_reader(profile):
            for y in sorted(ys):
                for x in sorted(xs,reverse=True):
                    if not(zone_left<=x and x+arm<=zone_right and zone_top<=y and y+arm<=zone_bottom):
                        continue
                    pair=(Rect(x,y,arm,thick),Rect(x+arm-thick,y,thick,arm))
                    if not any(overlaps(rect,box) for rect in pair for box in obstacles):
                        chosen=pair;break
                if chosen:break
        if chosen:
            marks.append(RegistrationMark('top','machine',chosen[0].y_um,chosen[0]))
            marks.append(RegistrationMark('right','machine_vertical',chosen[1].x_um,chosen[1]))
        else:
            warnings.append('Dedicated L-shaped machine registration mark omitted: machine has no barcode reader or no clear printable space inside the 3–20 mm top-right corner region. Guide registration positions are unavailable.')
    return RegistrationResult(tuple(marks), tuple(warnings))
