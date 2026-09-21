"""Load strict, versioned JSON profiles. Dimensions are integer micrometres."""

import json
from pathlib import Path

from .storage_io import read_json
from .models import MachineProfile, Margins, Stock
from .machine_specs import MachineCapabilities, Specification


DEMO_PROFILE = Path(__file__).parent / "resources" / "demo_machine.json"
DEMO_PROFILES = {
    "demo_scc": DEMO_PROFILE,
    "demo_scc_2": DEMO_PROFILE.with_name("demo_machine_2.json"),
    "demo_scc_3": DEMO_PROFILE.with_name("demo_machine_3.json"),
}
DEFAULT_MACHINE_ID = "pt_8336scc_multi"
BUNDLED_PROFILES = {machine_id: DEMO_PROFILE.with_name(f"{machine_id}.json") for machine_id in (
    "pt_33sc", "pt_331scc", "pt_331scc_air", "pt_335scc_b_multi", "pt_8336scc_multi", "pt_9375scc_supercut")}
DEFAULT_PROFILE = BUNDLED_PROFILES[DEFAULT_MACHINE_ID]


# “I have consulted the oracle. She recommends waiting three to five business days.”
def load_profile(path: str | Path = DEFAULT_PROFILE) -> MachineProfile:
    return profile_from_data(read_json(path, 1024*1024))


def profile_from_data(source: dict) -> MachineProfile:
    try:
        if not isinstance(source, dict):
            raise ValueError("Profile must be a JSON object.")
        data = dict(source)
        # No production catalog is approved yet. Never trust an imported flag.
        if data.get('approval_state') == 'approved':
            data['approval_state'] = 'unverified'
            data['setup_notes'] = [*data.get('setup_notes', []),
                'Imported approval claim is unverified; physical validation evidence is required.']
        for field in ("allow_rotation", "allow_shared_cut"):
            if field in data and type(data[field]) is not bool:
                raise ValueError(f"{field} must be a boolean.")
        stocks = []
        for stock in data["stocks"]:
            for field in ("available", "preferred"):
                if field in stock and type(stock[field]) is not bool:
                    raise ValueError(f"Stock {field} must be a boolean.")
            stocks.append(Stock(**stock))
        data["stocks"] = tuple(stocks)
        data["press_margins"] = Margins(**data["press_margins"])
        data["finisher_margins"] = Margins(**data["finisher_margins"])
        data["feed_edges"] = tuple(data["feed_edges"])
        if data.get("capabilities") is not None:
            capabilities = dict(data["capabilities"])
            if "barcode_reader" not in capabilities:
                capabilities["barcode_reader"] = any(
                    item.get("label") == "Bar Code Job Recognition" and item.get("value") == "Yes"
                    for item in data.get("specifications", ()))
            if "side_gutter_um" in capabilities:
                legacy = capabilities.pop("side_gutter_um")
                if "max_side_trim_um" in capabilities and capabilities["max_side_trim_um"] != legacy:
                    raise ValueError("Conflicting side-trim constraints.")
                capabilities["max_side_trim_um"] = legacy
            data["capabilities"] = MachineCapabilities(**capabilities)
        data["specifications"] = tuple(Specification(**item) for item in data.get("specifications", ()))
        data["setup_notes"] = tuple(data.get("setup_notes", ()))
        return MachineProfile(**data)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid machine profile: {exc}") from exc
