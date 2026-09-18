"""Vector barcode geometry with protected quiet zones and machine capability checks."""
from dataclasses import dataclass
from itertools import groupby
from .models import Rect


@dataclass(frozen=True)
class BarcodeSettings:
    enabled: bool = False
    value: str = ""
    symbology: str = "code128"
    module_um: int = 254
    height_um: int = 3175
    automatic: bool = True
    x_um: int = 0
    y_um: int = 0

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
    if not value or any(ord(c) < 32 or ord(c) > 126 for c in value):
        raise ValueError("Enter 1–64 printable ASCII characters for the barcode.")
    if settings.symbology == "code39" and any(c not in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-. $/+%" for c in value):
        raise ValueError("Code 39 accepts uppercase letters, digits, spaces and - . $ / + %. Input is not changed automatically.")
    try:
        from barcode.codex import Code128, Code39
    except ImportError as exc:
        raise ValueError("Install the desktop dependencies to generate barcodes (python-barcode is missing).") from exc
    # Code 128 includes its checksum. Code 39 uses no optional Mod-43 checksum.
    return (Code128(value) if settings.symbology == "code128" else Code39(value, add_checksum=False)).build()[0]


def overlaps(a, b):
    return min(a.x_um+a.width_um, b.x_um+b.width_um) > max(a.x_um, b.x_um) and min(a.y_um+a.height_um, b.y_um+b.height_um) > max(a.y_um, b.y_um)


def build_barcode(candidate, profile, settings, registration_marks=()):
    if not settings.enabled:
        return None
    if not has_barcode_reader(profile):
        raise ValueError("The selected machine has no barcode reader; barcode export is unavailable.")
    pattern = encode_bars(settings)
    quiet = 10*settings.module_um
    width = len(pattern)*settings.module_um + 2*quiet
    height = settings.height_um+2*settings.module_um
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
        xs = {(left+right-width)//2, left, right-width}
        ys = {top, artwork_top-height}
        for obstacle in obstacles:
            xs.update((obstacle.x_um-width, obstacle.x_um+obstacle.width_um))
            ys.update((obstacle.y_um-height, obstacle.y_um+obstacle.height_um))
        boxes = (Rect(x, y, width, height) for y in sorted(ys) if top <= y and y+height <= artwork_top
                 for x in sorted(xs, key=lambda x: abs((2*x+width)-(left+right))))
        bounds = next((box for box in boxes if valid(box)), None)
        if bounds is None:
            raise ValueError("No clear printable space above the artwork for this barcode. Choose a smaller valid size, another layout, or a manual position.")
    else:
        bounds = Rect(settings.x_um, settings.y_um, width, height)
        if not valid(bounds):
            raise ValueError("Barcode or quiet zone overlaps artwork, registration/finishing lines, or printable margins. Adjust its position or size.")
    bars = []
    x = bounds.x_um+quiet
    for digit, group in groupby(pattern):
        length = sum(1 for _ in group)*settings.module_um
        if digit == "1":
            bars.append(Rect(x, bounds.y_um+settings.module_um, length, settings.height_um))
        x += length
    return BarcodeGeometry(bounds, tuple(bars))
