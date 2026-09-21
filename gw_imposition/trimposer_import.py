"""Bounded offline INI import; fixed coordinates are never re-optimized."""
import configparser
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


def read_trimposer(path):
    if Path(path).suffix.lower() != '.ini':
        raise ValueError('Choose a Trimposer .ini job; binary transfer is not supported.')
    with Path(path).open('rb') as stream:
        raw = stream.read(131073)
    if len(raw) > 131072:
        raise ValueError('Trimposer job exceeds the import size limit.')
    try:
        return raw.decode('utf-8-sig')
    except UnicodeError as exc:
        raise ValueError('Trimposer job must be UTF-8 or ASCII text.') from exc


def parse(text):
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    try:
        parser.read_string(text)
        data = parser['MANULE_JOB_PARA']
        def number(key, default=None):
            value = Decimal(data[key] if default is None else data.get(key, str(default)))
            if not value.is_finite() or not 0 <= value <= 100000:
                raise ValueError(f'Invalid Trimposer value: {key}.')
            return value
        def count(key, maximum, default=None):
            value = number(key, default)
            if value != int(value) or value > maximum:
                raise ValueError(f'Invalid Trimposer count: {key}.')
            return int(value)
        def distance(key):
            return int((number(key)*1000).to_integral_value(rounding=ROUND_HALF_UP))
        for flag in ('m_Is_Crease_Inv_Enable', 'm_Is_Perforator_Hor_Enable',
                     'm_Is_Perforator_Ver_Enable', 'm_Is_Perforator_Hor_Part_Enable',
                     'm_Is_Fold_Enable', 'm_Is_twoSide', 'm_IsSniperUsed'):
            if count(flag, 1, 0):
                raise ValueError(f'Unsupported Trimposer operation {flag}; import would omit machine instructions.')
        if count('m_Page_Num', 100, 1) != 1:
            raise ValueError('Only single-page Trimposer jobs are supported.')
        def array(prefix, n):
            return tuple(distance(f'{prefix}[{i}]') for i in range(n))
        sw, sh = distance('m_Paper_Width'), distance('m_Paper_Height')
        cuts = array('m_p_CutPos_Arry', count('m_CutNum', 32))
        slots = array('m_p_SlitPos_Arry', count('m_SlitNum', 6))
        if len(slots) != 6:
            raise ValueError('Only the established six-slot Trimposer slitter format is supported.')
        # Outer slots are active even at zero; middle zero entries are unused.
        slits = (slots[0], *(x for x in slots[1:-1] if x), slots[-1])
        creases = array('m_p_CreasePos_Arry', count('m_CreaseNum', 32, 0)) if count('m_Is_Crease_Enable', 1, 0) else ()
        strikes = []
        if count('m_Is_Perforator_Ver_Part_Enable', 1, 0):
            for tool in range(count('m_PerforatorVerPartTotalNum', 4)):
                x = sw-distance(f'm_p_PerforatorVerPartTotalPos_Arry[{tool}]')
                for pair in range(count(f'm_p_PerforatorVerPartNum[{tool}]', 25)):
                    start = distance(f'm_p_PerforatorVerPartPos_Arry[{50*tool+2*pair}]')
                    end = distance(f'm_p_PerforatorVerPartPos_Arry[{50*tool+2*pair+1}]')
                    if (start, end) != (0, 0):
                        strikes.append((x, start, end))
        return sw, sh, tuple(sorted(set(sw-x for x in slits))), tuple(sorted(set(cuts))), creases, strikes
    except (configparser.Error, KeyError, InvalidOperation, OverflowError) as exc:
        raise ValueError(f'Invalid Trimposer INI: {exc}') from exc


def calculate_imported(job, profile):
    from .models import Calculation, Candidate, Rect, Line
    from .finishing import FinishingMark, validate_marks
    from .accessories import validate_accessories
    sw, sh, xs, ys, creases, strikes = parse(job.trimposer_ini)
    cap = profile.capabilities
    if not 0 < sw <= sh or not sh <= 5000000:
        raise ValueError('Imported sheet must use short-edge feed and supported positive dimensions.')
    if cap and not (cap.min_sheet_width_um <= sw <= cap.max_sheet_width_um and cap.min_sheet_height_um <= sh <= cap.max_sheet_height_um):
        raise ValueError('Imported sheet exceeds selected machine size bounds.')
    if len(xs) < 2 or len(ys) < 2 or any(not 0 <= x <= sw for x in xs) or any(not 0 <= y <= sh for y in ys):
        raise ValueError('Imported cut/slitter coordinates exceed sheet bounds or do not enclose cards.')
    if cap and len(xs) > cap.max_slitters:
        raise ValueError('Imported layout exceeds machine slitter capacity.')
    marks = tuple([FinishingMark('crease', 0, y, sw, y) for y in creases] +
                  [FinishingMark('strike_perf', x, a, x, b) for x, a, b in strikes])
    coverage = validate_marks(marks, sw, sh)
    for mark in marks:
        if cap and not getattr(cap, mark.kind):
            raise ValueError(f'Selected machine does not support imported {mark.kind}.')
    validate_accessories(job.accessories, profile, marks)
    if job.finishing:
        raise ValueError('Imported jobs supply sheet finishing. Clear card finishing before importing.')
    p = profile.press_margins
    usable = Rect(p.left_um, p.lead_um, sw-p.left_um-p.right_um, sh-p.lead_um-p.trail_um)
    def intervals(coords, size):
        result = tuple((a,b) for a,b in zip(coords, coords[1:]) if b-a == size)
        if not result or {v for pair in result for v in pair} != set(coords):
            return ()
        return result
    candidates = []
    for rotation in ((0,90) if profile.allow_rotation else (0,)):
        w,h,bx,by = (job.width_um,job.height_um,job.bleed_um,job.vertical_bleed_um) if rotation == 0 else (job.height_um,job.width_um,job.vertical_bleed_um,job.bleed_um)
        if job.bleed_handling == 'crop': bx,by = 0,0
        columns, rows = intervals(xs,w), intervals(ys,h)
        if not columns or not rows or len(columns)>profile.max_columns or len(rows)>profile.max_rows:
            continue
        if cap and (w < cap.min_finished_width_um or h < cap.min_finished_height_um):
            continue
        if cap and cap.max_side_trim_um is not None and max(xs[0],sw-xs[-1])>cap.max_side_trim_um:
            continue
        gaps = [b[0]-a[1] for sequence in (columns, rows) for a,b in zip(sequence,sequence[1:])]
        if any(g == 0 and not profile.allow_shared_cut or g > 0 and (not profile.minimum_gutter_um <= g <= profile.maximum_gutter_um or (g-profile.minimum_gutter_um)%profile.gutter_increment_um) for g in gaps):
            continue
        if job.bleed_handling == 'keep' and any(b[0]-a[1]<2*bleed for seq,bleed in ((columns,bx),(rows,by)) for a,b in zip(seq,seq[1:])):
            continue
        placements = tuple(Rect(x,y,w,h) for y,_ in rows for x,_ in columns)
        bleeds = tuple(Rect(r.x_um-bx,r.y_um-by,w+2*bx,h+2*by) for r in placements)
        if any(r.x_um<p.left_um or r.y_um<p.lead_um or r.x_um+r.width_um>sw-p.right_um or r.y_um+r.height_um>sh-p.trail_um for r in bleeds):
            continue
        rank = (-len(placements),sw,sh,'Trimposer',rotation,len(rows),len(columns))
        warnings = tuple('Strike-perf coverage exceeds 60%; solenoids may burn out.' for value in coverage.values() if value*100 > 60*sh)
        candidates.append(Candidate('Trimposer', 'short', rotation, sw, sh, usable, len(rows),len(columns),len(placements),sw*sh-len(placements)*w*h,
            placements,bleeds,xs,ys,tuple(Line(x,0,x,sh) for x in xs),tuple(Line(0,y,sw,y) for y in ys),rank,marks,warnings))
    if not candidates:
        raise ValueError('Artwork does not fit the imported layout: finished dimensions must match its card slots, bleed must fit gutters and printing margins, and machine bounds must be respected. No artwork was scaled or layout positions moved.')
    return Calculation(profile.id,profile.version,profile.approval_state,
        ('Imported Trimposer coordinates — unverified machine program. Registration/barcode settings use the current GW Bleed controls; INI reader settings are not imported.',),tuple(candidates),())
