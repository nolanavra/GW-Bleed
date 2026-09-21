"""Common finishing recipes, expressed in the existing per-card geometry model."""
from .finishing import FinishingOperation as Operation, validate_operations

PRESETS = (("none", "No finishing"), ("half", "Half fold"),
           ("accordion", "Accordion fold"), ("letter", "Letter fold"),
           ("gate", "Gate fold"), ("ticket", "Ticket stub"),
           ("coupons", "Coupons — grid"), ("tent", "Tent fold + strike perf"),
           ("advanced", "Advanced — custom settings"))


def preset_operations(preset, width, height, *, allowance=1588, tuck="bottom",
                      stub=50800, edge="right", columns=2, rows=3, flap=0, vertical_tool="strike_perf"):
    if width <= 0 or height <= 0:
        raise ValueError("Enter positive finished card dimensions first.")
    if vertical_tool not in ('strike_perf', 'rotary_perf'):
        raise ValueError('Choose strike or rotary perfs for vertical perforations.')
    def vertical(position):
        return Operation(vertical_tool, position, 0, height) if vertical_tool == 'strike_perf' else Operation(vertical_tool, position)
    if preset == "none":
        ops = ()
    elif preset == "half":
        ops = (Operation("crease", height // 2),)
    elif preset == "accordion":
        ops = tuple(Operation("crease", round(height * n / 3)) for n in (1, 2))
    elif preset == "letter":
        if not 0 <= allowance < height / 2:
            raise ValueError("Tuck-in allowance must be less than half the card height.")
        panel = (height + allowance) / 3
        positions = (panel, 2 * panel) if tuck == "bottom" else (panel-allowance, 2*panel-allowance)
        ops = tuple(Operation("crease", round(position)) for position in positions)
    elif preset == "gate":
        ops = tuple(Operation("crease", round(height * n / 4)) for n in (1, 3))
    elif preset == "ticket":
        limit = height if edge == "bottom" else width
        if not 0 < stub < limit:
            raise ValueError("Stub size must be smaller than the card dimension along the selected edge.")
        ops = (Operation("cross_perf", limit-stub) if edge == "bottom" else vertical(limit-stub),)
    elif preset == "coupons":
        if type(columns) is not int or type(rows) is not int or not (1 <= columns <= 10 and 1 <= rows <= 10) or columns*rows < 2:
            raise ValueError("Choose 1–10 columns and rows, with at least two coupons.")
        ops = tuple(vertical(round(width * n / columns)) for n in range(1, columns))
        ops += tuple(Operation("cross_perf", round(height * n / rows)) for n in range(1, rows))
    elif preset == "tent":
        if type(flap) is not int or not 1 < flap < height // 2:
            raise ValueError('Enter an end-flap size greater than zero and less than half the card length.')
        ops = tuple(Operation('crease', y) for y in (flap, height // 2, height-flap))
        ops += (Operation('strike_perf', width // 2, 0, flap // 2),
                Operation('strike_perf', width // 2, height-flap // 2, height))
    else:
        raise ValueError("Unknown finishing preset.")
    validate_operations(ops, width, height)
    return ops
