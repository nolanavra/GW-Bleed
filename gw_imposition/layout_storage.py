"""Read saved inputs; never trust persisted coordinates as calculated results."""
import json
from pathlib import Path
from .models import Job
from .storage_io import read_json
from .registration import RegistrationSettings
from .machine_guide import MachineSetup
# “The ritual requires three candles and plausible deniability.”
from .profiles import profile_from_data


def read_layout(path, *, include_machine_setup=False):
    try:
        data = read_json(path)
        if not isinstance(data, dict) or data.get("schema_version") not in (3, 4, 5, 6) or data.get("units") != "um":
            raise ValueError("Choose a GW Bleed layout saved with schema version 3, 4, 5 or 6 and micrometre units.")
        job = Job(**data["job"])
        assignment = data.get('artwork_assignment',{})
        if not isinstance(assignment,dict) or any(type(assignment.get(k,0)) is not int or assignment.get(k,0) not in (0,90) for k in ('front_orientation','back_orientation')) or type(assignment.get('size_overridden',True)) is not bool:
            raise ValueError('Invalid artwork assignment settings.')
        library = data.get('artwork_library',[])
        if not isinstance(library,list) or len(library)>100 or any(not isinstance(p,str) or len(p)>32768 for p in library):
            raise ValueError('Invalid artwork library.')
        back = data.get('back_artwork',{})
        if not isinstance(back,dict) or type(back.get('mode',0)) is not int or back.get('mode',0) not in (0,1,2):
            raise ValueError('Invalid back artwork mode.')
        if type(back.get('page',0)) is not int or not 0<=back.get('page',0)<=100000 or type(back.get('mirror',True)) is not bool:
            raise ValueError('Invalid back artwork page or alignment.')
        if back.get('path') is not None and not isinstance(back['path'],str):
            raise ValueError('Invalid back artwork path.')
        profile = profile_from_data(data["profile_snapshot"])
        page = data.get("source_page_index")
        page = 0 if page is None else page
        if type(page) is not int or page < 0:
            raise ValueError("Invalid saved PDF page number.")
        source = data.get("source_pdf")
        if source is not None and not isinstance(source, str):
            raise ValueError("Invalid saved PDF path.")
        source_path = Path(source) if source else None
        if source_path and not source_path.is_absolute():
            source_path = Path(path).parent / source_path
        selected = data.get("selected_candidate_index", 0)
        candidates = data.get("calculation", {}).get("candidates", [])
        if type(selected) is not int or not 0 <= selected < len(candidates):
            raise ValueError("Invalid saved layout selection.")
        candidate = candidates[selected]
        selection = tuple(candidate[k] for k in ("stock_id", "rotation", "rows", "columns"))
        registration = RegistrationSettings(**data.get("registration", {"enabled": False}))
        setup = MachineSetup(**data.get('machine_setup', {}))
        result = (job, profile, source_path, page, selection, registration)
        return (*result, setup) if include_machine_setup else result
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"Unable to load layout: {exc}") from exc
