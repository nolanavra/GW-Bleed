"""Repeat grids in feed coordinates: origin top-left, lead edge y=0.

Gutter means trim-to-trim gap. Independent bleed requires gap >= 2*bleed.
Artwork uses printing margins; finisher exclusions do not define printable area.
Cut positions are setup geometry, not a claim of a valid machine tool sequence.
"""

from .models import Calculation, Candidate, Job, Line, MachineProfile, Rect, Rejection
from .finishing import build_finishing
from .machine_specs import validate_machine_finishing
from .accessories import validate_accessories


MAX_CANDIDATES = 50_000
MAX_PLACEMENTS = 1_000_000


def calculate(job: Job, profile: MachineProfile) -> Calculation:
    if job.trimposer_ini is not None:
        from .trimposer_import import calculate_imported
        return calculate_imported(job, profile)
    capability = profile.capabilities
    finishing_error = ""
    try:
        validate_machine_finishing(job.finishing, profile)
        validate_accessories(job.accessories, profile)
    except ValueError as exc:
        finishing_error = str(exc)
    gap = job.gutter_um
    maximum_bleed = max(job.bleed_um, job.vertical_bleed_um)
    if job.bleed_handling == 'crop': maximum_bleed = 0
    if job.shared_cut:
        if not profile.allow_shared_cut or gap or (maximum_bleed and job.bleed_handling == 'keep'):
            raise ValueError("Shared cuts require profile support, zero gutter and zero bleed.")
    elif gap < 2 * maximum_bleed and job.bleed_handling == 'keep':
        raise ValueError("Gutter must accommodate both adjacent bleeds (at least 2 x bleed).")
    elif gap == 0:
        raise ValueError("Zero gutter requires explicit shared-cut mode and profile support.")
    if not job.shared_cut:
        if not profile.minimum_gutter_um <= gap <= profile.maximum_gutter_um:
            raise ValueError("Gutter is outside the machine profile range.")
        if (gap - profile.minimum_gutter_um) % profile.gutter_increment_um:
            raise ValueError("Gutter must equal minimum gutter plus a whole number of increments.")

    press = profile.press_margins
    left, right, lead, trail = (
        getattr(press, k)
        for k in ("left_um", "right_um", "lead_um", "trail_um"))
    candidates, rejected = [], []
    placement_count = 0
    for stock in profile.stocks:
        for feed in profile.feed_edges:
            # Only the short edge enters the machine: 12 or 13 inches on standard stock.
            sw, sh = sorted((stock.width_um, stock.height_um))
            usable = Rect(left, lead, sw - left - right, sh - lead - trail)
            for rotation in ((0, 90) if profile.allow_rotation else (0,)):
                def reject(code, message):
                    rejected.append(Rejection(stock.id, feed, rotation, code, message))

                if not stock.available:
                    reject("stock_unavailable", "Stock is not available.")
                    continue
                if capability and not (capability.min_sheet_width_um <= sw <= capability.max_sheet_width_um and
                                       capability.min_sheet_height_um <= sh <= capability.max_sheet_height_um):
                    reject("machine_sheet_size", "Stock is outside this machine's input paper-size limits.")
                    continue
                if finishing_error:
                    reject("machine_finishing", finishing_error)
                    continue
                w, h = ((job.width_um, job.height_um) if rotation == 0
                        else (job.height_um, job.width_um))
                bx, by = ((job.bleed_um, job.vertical_bleed_um) if rotation == 0
                          else (job.vertical_bleed_um, job.bleed_um))
                if job.bleed_handling == 'crop': bx,by = 0,0
                side_limit = capability.max_side_trim_um if capability else None
                if side_limit is not None and (left + bx > side_limit or right + bx > side_limit):
                    reject("side_trim_margin_conflict", f"Side trim must be 0–{side_limit/1000:g} mm per paper edge, "
                           f"but margins plus bleed require at least {(left+bx)/1000:g} mm left and {(right+bx)/1000:g} mm right. "
                           "Review printing margins and bleed against this machine's side-trim capability.")
                    continue
                if capability and (w < capability.min_finished_width_um or h < capability.min_finished_height_um):
                    reject("minimum_finished_size", "Finished card is below this machine's minimum across-feed width or feed length.")
                    continue
                if usable.width_um <= 0 or usable.height_um <= 0:
                    reject("no_usable_area", "Margins consume the entire sheet.")
                    continue
                cols = (usable.width_um - 2 * bx + gap) // (w + gap)
                rows = (usable.height_um - 2 * by + gap) // (h + gap)
                if cols < 1 or rows < 1:
                    reject("item_does_not_fit", "Trim and outer bleed do not fit the usable area.")
                    continue
                max_cols, max_rows = min(cols, profile.max_columns), min(rows, profile.max_rows)
                if cols > max_cols or rows > max_rows:
                    reject("grid_limit", "Larger geometric grids excluded by row/column limits.")
                for nr in range(1, max_rows + 1):
                    for nc in range(1, max_cols + 1):
                        grid_width = nc * w + (nc - 1) * gap + 2 * bx
                        grid_height = nr * h + (nr - 1) * gap + 2 * by
                        origin_x = (sw - grid_width) // 2
                        # Bottom-align the outer bleed to the trailing usable boundary.
                        origin_y = sh - trail - grid_height
                        left_trim = origin_x + bx
                        right_trim = sw - (left_trim + nc*w + (nc-1)*gap)
                        if side_limit is not None and not (0 <= left_trim <= side_limit and 0 <= right_trim <= side_limit):
                            reject("side_trim_limit", f"{nc} columns x {nr} rows: left trim {left_trim/1000:g} mm, "
                                   f"right trim {right_trim/1000:g} mm; each must be 0–{side_limit/1000:g} mm from the paper edge.")
                            continue
                        if (origin_x < left or origin_y < lead or
                                origin_x + grid_width > sw - right or
                                origin_y + grid_height > sh - trail):
                            reject("centered_margins", f"{nc} columns x {nr} rows: bottom-aligned, horizontally centered layout crosses a printing margin.")
                            continue
                        count = nr * nc
                        placement_count += count
                        if len(candidates) >= MAX_CANDIDATES or placement_count > MAX_PLACEMENTS:
                            raise ValueError("Search exceeds prototype limits; narrow stocks or grid limits.")
                        placements = tuple(Rect(origin_x + bx + c * (w + gap),
                                                origin_y + by + r * (h + gap), w, h)
                                           for r in range(nr) for c in range(nc))
                        bleeds = tuple(Rect(p.x_um - bx, p.y_um - by, w + 2*bx, h + 2*by)
                                       for p in placements)
                        cuts_x = tuple(sorted({x for p in placements for x in (p.x_um, p.x_um + w)}))
                        cuts_y = tuple(sorted({y for p in placements for y in (p.y_um, p.y_um + h)}))
                        if capability and len(cuts_x) > capability.max_slitters:
                            reject("slitter_limit", f"Layout needs {len(cuts_x)} slitters; machine supports {capability.max_slitters}.")
                            continue
                        waste = sw * sh - count * w * h
                        slitters = tuple(Line(x, 0, x, sh) for x in cuts_x)
                        cuts = tuple(Line(0, y, sw, y) for y in cuts_y)
                        try:
                            finishing, finishing_warnings = build_finishing(job.finishing, placements, rotation, sw, sh, job.finishing_rotation)
                            validate_accessories(job.accessories, profile, finishing)
                        except ValueError as exc:
                            reject("finishing_rule", f"{nc} columns x {nr} rows: {exc}")
                            continue
                        # Pieces per sheet descending, then stock dimensions ascending.
                        rank = (-count, sw, sh, stock.id, rotation, nr, nc)
                        candidates.append(Candidate(
                            stock.id, feed, rotation, sw, sh, usable, nr, nc, count,
                            waste,
                            placements, bleeds, cuts_x, cuts_y, slitters, cuts, rank,
                            finishing, finishing_warnings))
    warnings = ["Prototype checks layout and basic finishing geometry; tool sequencing, folds, duplex and PDF preflight are not implemented."]
    if profile.approval_state != "approved":
        warnings.insert(0, "UNVERIFIED PROFILE: results are for development, not production setup.")
    warnings.extend(profile.setup_notes)
    return Calculation(profile.id, profile.version, profile.approval_state,
                       tuple(warnings), tuple(sorted(candidates, key=lambda c: c.rank_key)),
                       tuple(rejected))
