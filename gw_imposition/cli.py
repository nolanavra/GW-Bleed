import argparse
from dataclasses import asdict
import json
# “I sought the philosopher’s stone and found a very persuasive rock.”
from pathlib import Path

from .layout_engine import calculate
from .models import Job
from .profiles import BUNDLED_PROFILES, DEFAULT_MACHINE_ID, load_profile
from .units import inches, to_um


def main(argv=None):
    parser = argparse.ArgumentParser(description="GW Bleed — single-sheet layout calculator")
    parser.add_argument("--width", required=True, help="Finished trim width")
    parser.add_argument("--height", required=True, help="Finished trim height")
    parser.add_argument("--units", choices=("in", "mm"), default="in")
    parser.add_argument("--bleed", default="0", help="Bleed per edge, in selected units")
    parser.add_argument("--gutter", default=None, help="Trim-to-trim gap; default twice bleed rounded up to a valid machine setting")
    parser.add_argument("--shared-cut", action="store_true")
    machine_options = parser.add_mutually_exclusive_group()
    machine_options.add_argument("--machine", choices=tuple(BUNDLED_PROFILES), default=DEFAULT_MACHINE_ID,
                                 help="Bundled machine (default: pt_8336scc_multi)")
    machine_options.add_argument("--profile", type=Path, help="Custom machine profile JSON")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--output", type=Path, help="Write complete calculation and profile snapshot as JSON")
    args = parser.parse_args(argv)
    try:
        if args.top < 1:
            raise ValueError("--top must be positive.")
        profile = load_profile(args.profile or BUNDLED_PROFILES[args.machine])
        bleed = to_um(args.bleed, args.units)
        if args.gutter is None:
            minimum = profile.minimum_gutter_um
            step = profile.gutter_increment_um
            gutter = minimum + max(0, (max(1, 2 * bleed) - minimum + step - 1) // step) * step
            if args.shared_cut:
                gutter = 0
        else:
            gutter = to_um(args.gutter, args.units)
        job = Job(to_um(args.width, args.units), to_um(args.height, args.units),
                  bleed, gutter, shared_cut=args.shared_cut)
        result = calculate(job, profile)
        for warning in result.warnings:
            print(f"WARNING: {warning}")
        print(f"Machine: {profile.name} ({profile.id}) | maximum {profile.max_columns} columns")
        print(f"Gutter: {inches(gutter)} in | {len(result.candidates)} valid candidates")
        for index, c in enumerate(result.candidates[:args.top], 1):
            print(f"{index}. {c.stock_id}: {c.columns} columns x {c.rows} rows = "
                  f"{c.yield_per_sheet} pieces per sheet; {c.rotation} degrees; {c.feed_edge}-edge feed")
        for rejection in result.rejections:
            print(f"Excluded {rejection.stock_id}/{rejection.feed_edge}/{rejection.rotation}: "
                  f"{rejection.code}: {rejection.message}")
        if args.output:
            payload = {"schema_version": 4, "units": "um", "job": asdict(job),
                       "profile_snapshot": asdict(profile), "calculation": asdict(result)}
            args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            print(f"Saved {args.output}")
        if not result.candidates:
            print("No valid layout. Review dimensions, bleed, margins and stock availability.")
            return 1
        return 0
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
