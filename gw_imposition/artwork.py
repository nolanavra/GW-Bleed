"""Shared artwork clipping and duplex positioning; no independent layout search."""
from dataclasses import replace
from .models import Rect


def bleed_clips(candidate, mode):
    if mode == 'crop': return candidate.placements
    if mode != 'trim':
        return candidate.bleed_regions
    positions = candidate.placements
    xs = sorted({(p.x_um, p.x_um+p.width_um) for p in positions})
    ys = sorted({(p.y_um, p.y_um+p.height_um) for p in positions})
    def limits(intervals, interval, length):
        i = intervals.index(interval)
        return ((intervals[i-1][1]+interval[0])//2 if i else 0,
                (interval[1]+intervals[i+1][0])//2 if i+1<len(intervals) else length)
    clips = []
    for p,b in zip(positions,candidate.bleed_regions):
        left,right = limits(xs,(p.x_um,p.x_um+p.width_um),candidate.sheet_width_um)
        top,bottom = limits(ys,(p.y_um,p.y_um+p.height_um),candidate.sheet_height_um)
        left,top = max(left,b.x_um),max(top,b.y_um)
        right,bottom = min(right,b.x_um+b.width_um),min(bottom,b.y_um+b.height_um)
        clips.append(Rect(left,top,right-left,bottom-top))
    return tuple(clips)


def back_candidate(candidate, mirror):
    if not mirror:
        return candidate
    sw = candidate.sheet_width_um
    def rect(r): return replace(r,x_um=sw-r.x_um-r.width_um)
    def line(l): return replace(l,x1_um=sw-l.x2_um,x2_um=sw-l.x1_um)
    return replace(candidate,placements=tuple(map(rect,candidate.placements)),
        bleed_regions=tuple(map(rect,candidate.bleed_regions)),usable=rect(candidate.usable),
        slitter_x_um=tuple(sorted(sw-x for x in candidate.slitter_x_um)),
        slitters=tuple(map(line,candidate.slitters)),cuts=tuple(map(line,candidate.cuts)),
        finishing=tuple(map(line,candidate.finishing)))
