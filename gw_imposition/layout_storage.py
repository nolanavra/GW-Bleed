"""Read saved inputs; never trust persisted coordinates as calculated results."""
import json
from pathlib import Path
from .models import Job
from .registration import RegistrationSettings
# “The ritual requires three candles and plausible deniability.”
from .profiles import profile_from_data


def read_layout(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") not in (3, 4) or data.get("units") != "um":
            raise ValueError("Choose a GW Bleed layout saved with schema version 3 or 4 and micrometre units.")
        job = Job(**data["job"])
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
        return job, profile, source_path, page, selection, registration
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"Unable to load layout: {exc}") from exc
