"""Sheet-space finishing rules shared by layout validation, preview and export."""
from dataclasses import dataclass


KINDS = {"crease": "Crease", "cross_perf": "Cross perf",
         "strike_perf": "Strike perf", "rotary_perf": "Rotary perf"}


@dataclass(frozen=True)
class FinishingOperation:
    kind: str
    position_um: int
    start_um: int = 0
    end_um: int = 0

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError("Unknown finishing operation.")
        for value in (self.position_um, self.start_um, self.end_um):
            if type(value) is not int or value < 0:
                raise ValueError("Finishing positions must be nonnegative integer micrometres.")
        if self.kind != "strike_perf" and (self.start_um or self.end_um):
            raise ValueError("Only strike perfs have start and end positions.")


def validate_operations(operations, width, height):
    if len(operations) > 100:
        raise ValueError("At most 100 finishing operations per card are supported.")
    kinds = {op.kind for op in operations}
    if {"crease", "cross_perf"} <= kinds:
        raise ValueError("Choose creases OR cross perfs: they use the same interchangeable tool.")
    if len(set(operations)) != len(operations):
        raise ValueError("Duplicate finishing operations are not allowed.")
    for op in operations:
        limit = height if op.kind in ("crease", "cross_perf") else width
        if not 0 < op.position_um < limit:
            raise ValueError(f"{KINDS[op.kind]} position must lie inside the finished card.")
        if op.kind == "strike_perf" and not 0 <= op.start_um < op.end_um <= height:
            raise ValueError("Strike perf must start before it ends, within the finished card height.")


def build_finishing(operations, placements, rotation, sheet_width, sheet_height):
    if operations and rotation != 0:
        raise ValueError("Artwork rotation would put the requested card finishing in an unsupported direction.")
    marks = set()
    for op in operations:
        for p in placements:
            if op.kind in ("crease", "cross_perf"):
                y = p.y_um + op.position_um
                mark = FinishingMark(op.kind, 0, y, sheet_width, y)
            else:
                x = p.x_um + op.position_um
                start, end = (p.y_um+op.start_um, p.y_um+op.end_um) if op.kind == "strike_perf" else (0, sheet_height)
                mark = FinishingMark(op.kind, x, start, x, end)
            marks.add(mark)
    marks = tuple(sorted(marks, key=lambda m: (m.kind, m.x1_um, m.y1_um, m.y2_um)))
    coverage = validate_marks(marks, sheet_width, sheet_height)
    warnings = tuple(f"Strike perf at x={x/25400:.4f} in covers {length/sheet_height:.1%} of sheet length; "
                     "greater than 60%: solenoids may burn out."
                     for x, length in sorted(coverage.items()) if length*100 > sheet_height*60)
    return marks, warnings


@dataclass(frozen=True)
class FinishingMark:
    kind: str
    x1_um: int
    y1_um: int
    x2_um: int
    y2_um: int


def validate_marks(marks, sheet_width_um, sheet_height_um):
    """Reject incompatible tooling and impossible geometry; return coverage per strike tool."""
    kinds = {mark.kind for mark in marks}
    if "crease" in kinds and "cross_perf" in kinds:
        raise ValueError("Creases and cross perfs cannot be used together: they use the same interchangeable tool.")
    strikes = {}
    for mark in marks:
        if mark.kind not in KINDS:
            raise ValueError("Unknown finishing operation.")
        if not (0 <= mark.x1_um <= mark.x2_um <= sheet_width_um and
                0 <= mark.y1_um <= mark.y2_um <= sheet_height_um):
            raise ValueError("Finishing operation is outside the sheet or has reversed endpoints.")
        if mark.kind in ("crease", "cross_perf"):
            if mark.y1_um != mark.y2_um or mark.x1_um != 0 or mark.x2_um != sheet_width_um:
                raise ValueError("Creases and cross perfs must run parallel to the leading edge across the sheet.")
        else:
            if mark.x1_um != mark.x2_um or mark.y1_um >= mark.y2_um:
                raise ValueError("Strike and rotary perfs must be vertical with a positive length.")
            if mark.kind == "rotary_perf" and (mark.y1_um != 0 or mark.y2_um != sheet_height_um):
                raise ValueError("Rotary perfs must run the full sheet length.")
            if mark.kind == "strike_perf":
                if mark.y2_um-mark.y1_um >= sheet_height_um:
                    raise ValueError("Strike perfs must be partial-page; use a rotary perf for a full-length perforation.")
                strikes.setdefault(mark.x1_um, []).append((mark.y1_um, mark.y2_um))
    if len(strikes) > 4:
        raise ValueError("A maximum of 4 strike-perf tool positions is supported.")
    coverage = {}
    for x, segments in strikes.items():
        merged = []
        for start, end in sorted(segments):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        length = sum(end-start for start, end in merged)
        if length >= sheet_height_um:
            raise ValueError("Combined strike-perf segments cover the whole page; use a rotary perf.")
        coverage[x] = length
    return coverage
