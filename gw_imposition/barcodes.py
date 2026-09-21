"""Vector barcode geometry with protected quiet zones and machine capability checks."""
from dataclasses import dataclass
from itertools import groupby
from .models import Rect


class BarcodePlacementError(ValueError):
    """A valid barcode cannot fit the selected layout."""


@dataclass(frozen=True)
class BarcodeSettings:
    enabled: bool = False
    value: str = ""
    symbology: str = "code39"
    module_um: int = 254
    height_um: int = 6500
    automatic: bool = True
    x_um: int = 0
    y_um: int = 4000

    def __post_init__(self):
        if type(self.enabled) is not bool or type(self.automatic) is not bool:
            raise ValueError("Barcode switches must be boolean.")
        if not isinstance(self.value, str) or len(self.value) > 64:
            raise ValueError("Barcode value must be text of at most 64 characters.")
        if self.symbology not in ("code128", "code39"):
            raise ValueError("Choose Code 128 or Code 39.")
        for name, low, high in (("module_um", 100, 2000), ("height_um", 1000, 100000), ("x_um", 0, 2000000), ("y_um", 0, 2000000)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"Barcode {name} is outside the supported range.")


@dataclass(frozen=True)
class BarcodeGeometry:
    bounds: Rect
    bars: tuple[Rect, ...]


def has_barcode_reader(profile):
    return bool(profile and profile.capabilities and profile.capabilities.barcode_reader)


def encode_bars(settings):
    value = settings.value
    if settings.symbology != 'code39':
        raise ValueError('Machine barcodes now require Code 39. Review legacy barcode settings before export.')
    if len(value)!=5 or not value.isascii() or not value.isdigit():
        raise ValueError('Code 39 payload must be exactly five digits: machine job 000–999 followed by quantity 00–99. Start/stop * characters are added automatically.')
    try:
        from barcode.codex import Code39
    except ImportError as exc:
        raise ValueError("Install the desktop dependencies to generate barcodes (python-barcode is missing).") from exc
    return Code39(value, add_checksum=False).build()[0]


def overlaps(a, b):
    return min(a.x_um+a.width_um, b.x_um+b.width_um) > max(a.x_um, b.x_um) and min(a.y_um+a.height_um, b.y_um+b.height_um) > max(a.y_um, b.y_um)


def build_barcode(candidate, profile, settings, registration_marks=()):
    if not settings.enabled:
        return None
    if not has_barcode_reader(profile):
        raise ValueError("The selected machine has no barcode reader; barcode export is unavailable.")
    pattern = encode_bars(settings)
    if settings.height_um != 6500:
        raise ValueError('Machine barcode bars must be 6.5 mm high; review legacy size settings.')
    # Round cumulative positions, not individual widths, so the vector symbol
    # spans exactly 45 mm without accumulating module-rounding drift.
    symbol_width, symbol_height = 45000,6500
    modules = len(pattern)
    position = lambda i: (i*symbol_width+modules//2)//modules
    quiet = (10*symbol_width+modules-1)//modules
    padding = (symbol_width+modules-1)//modules
    width = symbol_width+2*quiet
    height = symbol_height+2*padding
    symbol_x = candidate.sheet_width_um-52000-symbol_width
    p = profile.press_margins
    left, top, right, bottom = p.left_um, p.lead_um, candidate.sheet_width_um-p.right_um, candidate.sheet_height_um-p.trail_um
    obstacles = list(candidate.bleed_regions) + [mark.rect for mark in registration_marks]
    # Keep even line-only/combined exports clear of the barcode and quiet zones.
    for line in (*candidate.cuts, *candidate.slitters, *candidate.finishing):
        obstacles.append(Rect(line.x1_um-100, line.y1_um-100,
            line.x2_um-line.x1_um+200, line.y2_um-line.y1_um+200))

    def valid(box):
        return (box.x_um >= left and box.y_um >= top and box.x_um+width <= right and box.y_um+height <= bottom
                and not any(overlaps(box, obstacle) for obstacle in obstacles))

    if settings.automatic:
        artwork_top = min(r.y_um for r in candidate.bleed_regions)
        ys = {max(4000,top+padding), min(20000,artwork_top-symbol_height-padding)}
        for obstacle in obstacles:
            ys.update((obstacle.y_um-symbol_height-padding, obstacle.y_um+obstacle.height_um+padding))
        boxes = (Rect(symbol_x-quiet, y-padding, width, height) for y in sorted(ys)
                 if 4000<=y<=20000 and y+symbol_height+padding<=artwork_top)
        bounds = next((box for box in boxes if valid(box)), None)
        if bounds is None:
            raise BarcodePlacementError('No clear printable space for the fixed 45 × 6.5 mm barcode at 52 mm from the right and 4–20 mm from the leading edge. Choose another layout or review printable margins; barcode size and right position cannot be reduced or moved.')
    else:
        if not 4000<=settings.y_um<=20000:
            raise ValueError('Barcode leading-edge distance must be 4–20 mm, measured to the top of the black bars.')
        bounds = Rect(symbol_x-quiet, settings.y_um-padding, width, height)
        if not valid(bounds):
            raise BarcodePlacementError('Barcode or quiet zone overlaps artwork, registration/finishing lines, or printable margins. Select another valid leading-edge position or layout.')
    bars = []
    index = 0
    for digit, group in groupby(pattern):
        end = index+sum(1 for _ in group)
        if digit == "1":
            bars.append(Rect(symbol_x+position(index), bounds.y_um+padding, position(end)-position(index), symbol_height))
        index = end
    return BarcodeGeometry(bounds, tuple(bars))
