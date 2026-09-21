"""Offline Trimposer INI exchange. Binary transfer is deliberately not implemented."""
from decimal import Decimal
import configparser
import os
from pathlib import Path
import tempfile
from .layout_engine import calculate
from .machine_guide import build_guide


def mm(um):
    return format(Decimal(um)/1000, '.4f')


def trimposer_ini(job, profile, candidate, setup, *, job_number, speed_grade=4,
                  crease_level=None, registration_position=None):
    """Encode the observed INI schema; caller must review in Trimposer before use."""
    from .paper_stocks import automatic_crease_depth
    derived = automatic_crease_depth(setup.thickness_inches,profile.capabilities)
    if crease_level is not None and crease_level!=derived:
        raise ValueError('Crease level must match the automatic thickness mapping.')
    crease_level=derived
    for label,value,low,high in (('Job number',job_number,0,999),
                               ('Speed grade',speed_grade,4,4),
                               ('Crease level',crease_level,1,5)):
        if type(value) is not int or not low<=value<=high:
            raise ValueError(f'{label} must be an integer from {low} to {high}.')
    if not setup.thickness_inches:
        raise ValueError('Select a paper profile with measured thickness before saving a Trimposer job.')
    name = setup.job_name or f'JOB{job_number}'
    if not name.isascii() or len(name)>31 or any(ord(c)<32 or c in '=;[]' for c in name):
        raise ValueError('Trimposer job names currently support at most 31 plain ASCII characters without = ; [ ].')
    if candidate not in calculate(job,profile).candidates:
        raise ValueError('The selected layout is no longer valid for this job and machine.')
    g = build_guide(job,profile,candidate)
    if g.conflicts:
        raise ValueError('Resolve guide precision conflicts before export: '+' '.join(g.conflicts))
    if any(m.kind in ('cross_perf','rotary_perf') for m in candidate.finishing):
        raise ValueError('Cross/rotary perf INI position fields are not established by the supplied examples; export is blocked rather than omitting those operations.')
    if len(g.slits)>6 or len(g.cuts)>32 or len(g.creases)>32 or any(len(t.segments)>25 for t in g.strikes):
        raise ValueError('Layout exceeds the observed Trimposer INI operation-array limits.')
    d = dict(m_JobNO=job_number,m_JobNameStr=name,m_UnitType=1,
             m_Paper_Width=mm(candidate.sheet_width_um),m_Paper_Height=mm(candidate.sheet_height_um),
             m_Paper_Thickness=format(Decimal(setup.thickness_inches)*Decimal('25.4'),'.4f'),
             m_Paper_Num=1,m_Paper_Batch=1,m_IsLocatorUsed=int(registration_position is not None),
             m_IsBarcodeUsed=0,m_IsSniperUsed=0,m_Is_Crease_Enable=int(bool(g.creases)),
             m_Is_Crease_Inv_Enable=0,m_Is_Perforator_Hor_Enable=0,m_Is_Perforator_Ver_Enable=0,
             m_Is_Perforator_Hor_Part_Enable=0,m_Is_Perforator_Ver_Part_Enable=int(bool(g.strikes)),
             m_Is_Fold_Enable=0,m_ProcessSpeed_Grade=speed_grade,m_Crease_Level=crease_level,
             m_Crease_Level2=1,m_Is_twoSide=0,m_Page_Num=1,m_pic_num=0)
    if registration_position is not None:
        lead,right = registration_position
        if any(type(v) is not int or v<0 for v in (lead,right)) or lead>candidate.sheet_height_um or right>candidate.sheet_width_um:
            raise ValueError('Invalid registration mark position.')
        d['m_Locator_Offset_Hor']=mm(right)
        d['m_Locator_Offset_Ver']=mm(lead)
    def array(prefix,values):
        for i,value in enumerate(values):
            d[f'{prefix}[{i}]']=mm(value)
    d['m_CutNum']=len(g.cuts)
    array('m_p_CutPos_Arry',g.cuts)
    # Supplied examples retain outer trim slots at indices 0 and 5, padding
    # unused middle slots rather than moving the final edge into an inner slot.
    slits = list(g.slits)
    slots = [slits[0],*slits[1:-1],*([0]*(6-len(slits))),slits[-1]] if len(slits)>=2 else slits+[0]*(6-len(slits))
    d['m_SlitNum']=6
    array('m_p_SlitPos_Arry',slots)
    d['m_CreaseNum']=len(g.creases)
    array('m_p_CreasePos_Arry',g.creases)
    if g.strikes:
        d['m_PerforatorVerPartTotalNum']=len(g.strikes)
        array('m_p_PerforatorVerPartTotalPos_Arry',[t.right_um for t in g.strikes])
        for tool in g.strikes:
            d[f'm_p_PerforatorVerPartNum[{tool.number-1}]']=len(tool.segments)
            for i,value in enumerate(v for segment in tool.segments for v in segment):
                d[f'm_p_PerforatorVerPartPos_Arry[{50*(tool.number-1)+i}]']=mm(value)
    return ('[MANULE_JOB_PARA]\r\n'+''.join(f'{key}={value}\r\n' for key,value in d.items())).encode('ascii')


def save_trimposer_ini(path, content):
    path=Path(path)
    if path.suffix.lower()!='.ini':
        raise ValueError('Trimposer job output must use .ini. Binary transfer is reserved for a future feature.')
    parsed=configparser.ConfigParser(interpolation=None)
    parsed.read_string(content.decode('ascii'))
    if 'MANULE_JOB_PARA' not in parsed:
        raise ValueError('Invalid Trimposer job data.')
    handle, staging=tempfile.mkstemp(prefix='.gw-trimposer-',suffix='.ini',dir=path.parent)
    try:
        with os.fdopen(handle,'wb') as stream:
            stream.write(content);stream.flush();os.fsync(stream.fileno())
        if Path(staging).read_bytes()!=content:
            raise ValueError('Staged Trimposer job verification failed.')
        os.replace(staging,path)
    finally:
        Path(staging).unlink(missing_ok=True)
