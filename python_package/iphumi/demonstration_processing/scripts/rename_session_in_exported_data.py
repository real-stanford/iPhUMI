#!/usr/bin/env python3
"""Rename a session in raw iPhUMI exported data (before pipeline processing).

For all run folders between --start and --end (inclusive, sorted ascending):

  - Gripper calibration folders: COPIED to a new name with the new session,
    original left in place (so any data still under the old session keeps a
    valid reference). JSON fields updated in the copy.

  - Demonstration folders: RENAMED to the new session. JSON sessionName and
    gripperCalibrationRunName updated to point to the copied calibration.

Calibrations referenced by in-range demonstrations are always copied, even
if they fall outside the specified start/end range.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path


def collect_run_folders(data_path: Path) -> list[Path]:
    """Return all run folders across all date subdirs, sorted by folder name."""
    folders: list[Path] = []
    for date_dir in data_path.iterdir():
        if date_dir.is_dir():
            for run_dir in date_dir.iterdir():
                if run_dir.is_dir():
                    folders.append(run_dir)
    folders.sort(key=lambda p: p.name)
    return folders


KNOWN_SIDES = ("_left", "_right", "_head")


def strip_side(name: str) -> str:
    """Remove a trailing _left/_right/_head suffix, return the base run name."""
    for side in KNOWN_SIDES:
        if name.endswith(side):
            return name[: -len(side)]
    return name


def resolve_endpoint(folders: list[Path], raw_input: str, pick: str) -> tuple[int, str]:
    """
    Given a user-supplied folder name or path (possibly with a specific side),
    strip the side, find all existing side variants, and return the index and
    name of the earliest (pick='first') or latest (pick='last') variant.

    This ensures that passing a _right name as --start still includes the
    paired _left folder that sorts before it.
    """
    name = Path(raw_input).name  # tolerate full paths
    base = strip_side(name)
    names = [f.name for f in folders]

    variants = sorted(n for n in names if strip_side(n) == base)
    if not variants:
        sys.exit(f"ERROR: no folders found matching base run {base!r}")

    chosen = variants[0] if pick == "first" else variants[-1]
    return names.index(chosen), chosen


def get_folder_range(folders: list[Path], start_raw: str, end_raw: str) -> list[Path]:
    start_idx, start_name = resolve_endpoint(folders, start_raw, pick="first")
    end_idx, end_name = resolve_endpoint(folders, end_raw, pick="last")

    if start_idx > end_idx:
        sys.exit(
            f"ERROR: start folder sorts after end folder.\n"
            f"  start ({start_idx}): {start_name}\n"
            f"  end   ({end_idx}): {end_name}"
        )

    print(f"  Resolved start : {start_name}")
    print(f"  Resolved end   : {end_name}")

    return folders[start_idx : end_idx + 1]


def run_type(folder_name: str) -> str:
    if "grippercalibration" in folder_name:
        return "calibration"
    if "demonstration" in folder_name:
        return "demonstration"
    return "other"


def plan_folder_changes(folder: Path, old_session: str, new_session: str) -> dict:
    """Return a description of all changes needed for this run folder (no I/O side effects)."""
    old_token = f"_{old_session}_"
    new_token = f"_{new_session}_"

    old_folder_name = folder.name
    new_folder_name = old_folder_name.replace(old_token, new_token)
    kind = run_type(old_folder_name)

    # Calibration: copy (original stays). Demonstration: rename (move).
    folder_op = "copy" if kind == "calibration" else "rename"

    file_renames: list[tuple[str, str]] = []
    json_field_updates: list[tuple[str, str, str]] = []  # (filename, field, new_value)
    referenced_cal_names: list[str] = []  # old gripperCalibrationRunName values seen

    for file in sorted(folder.iterdir()):
        if not file.is_file():
            continue

        new_file_name = file.name.replace(old_token, new_token)
        if new_file_name != file.name:
            file_renames.append((file.name, new_file_name))

        if file.suffix == ".json":
            with open(file, encoding="utf-8") as fh:
                data = json.load(fh)

            if data.get("sessionName") == old_session:
                json_field_updates.append((file.name, "sessionName", new_session))

            cal_run = data.get("gripperCalibrationRunName", "")
            if cal_run:
                referenced_cal_names.append(cal_run)
                if old_token in cal_run:
                    new_cal_run = cal_run.replace(old_token, new_token)
                    json_field_updates.append((file.name, "gripperCalibrationRunName", new_cal_run))

    return {
        "folder": folder,
        "kind": kind,
        "folder_op": folder_op,
        "old_folder_name": old_folder_name,
        "new_folder_name": new_folder_name,
        "changed": new_folder_name != old_folder_name,
        "file_renames": file_renames,
        "json_field_updates": json_field_updates,
        "referenced_cal_names": referenced_cal_names,
    }


def find_extra_calibration_plans(
    range_plans: list[dict],
    all_folders: list[Path],
    old_session: str,
    new_session: str,
) -> list[dict]:
    """
    Find calibration folders referenced by in-range demonstrations that are NOT
    already covered by a plan in range_plans, and return copy plans for them.
    """
    already_planned = {p["old_folder_name"] for p in range_plans if p["kind"] == "calibration"}

    # Collect all unique old-session calibration run names referenced by demos.
    referenced: set[str] = set()
    for plan in range_plans:
        for cal_name in plan["referenced_cal_names"]:
            referenced.add(cal_name)

    # Map all known folders by name for lookup.
    folder_by_name = {f.name: f for f in all_folders}

    extra: list[dict] = []
    seen_bases: set[str] = set()
    for cal_name in sorted(referenced):
        if cal_name in already_planned:
            continue
        base = strip_side(cal_name)
        if base in seen_bases:
            continue
        seen_bases.add(base)

        # Find all side variants of this calibration and plan a copy for each.
        variants = sorted(n for n in folder_by_name if strip_side(n) == base)
        for variant in variants:
            if variant in folder_by_name:
                extra.append(plan_folder_changes(folder_by_name[variant], old_session, new_session))

    return extra


def apply_calibration_copy(plan: dict) -> None:
    """Copy calibration folder to new name, then update files/JSON inside the copy."""
    src: Path = plan["folder"]
    dst: Path = src.parent / plan["new_folder_name"]

    if dst.exists():
        print(f"  SKIP (already exists): {dst.name}")
        return

    shutil.copytree(src, dst)

    # Update JSON content in the copy.
    for file_name, field, new_value in plan["json_field_updates"]:
        file_path = dst / file_name
        with open(file_path, encoding="utf-8") as fh:
            data = json.load(fh)
        data[field] = new_value
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=4, ensure_ascii=False)

    # Rename files inside the copy.
    for old_name, new_name in plan["file_renames"]:
        (dst / old_name).rename(dst / new_name)


def apply_demonstration_rename(plan: dict) -> None:
    """Update JSON inside demonstration folder, rename files, then rename folder."""
    folder: Path = plan["folder"]

    # 1. Update JSON content (while paths still use old names).
    for file_name, field, new_value in plan["json_field_updates"]:
        file_path = folder / file_name
        with open(file_path, encoding="utf-8") as fh:
            data = json.load(fh)
        data[field] = new_value
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=4, ensure_ascii=False)

    # 2. Rename files inside the folder.
    for old_name, new_name in plan["file_renames"]:
        (folder / old_name).rename(folder / new_name)

    # 3. Rename the folder itself.
    if plan["changed"]:
        folder.rename(folder.parent / plan["new_folder_name"])


def print_plans_grouped(plans: list[dict], note: str = "") -> None:
    """Print one line per unique base run name, listing sides found."""
    old_token = None
    new_token = None

    # Group by base run name (strip side).
    from collections import defaultdict
    groups: dict[str, list[str]] = defaultdict(list)
    new_base_by_old: dict[str, str] = {}
    for plan in plans:
        old_name = plan["old_folder_name"]
        new_name = plan["new_folder_name"]
        side = next((s.lstrip("_") for s in KNOWN_SIDES if old_name.endswith(s)), "unknown")
        base = strip_side(old_name)
        new_base = strip_side(new_name)
        groups[base].append(side)
        new_base_by_old[base] = new_base

    suffix = f"  ({note})" if note else ""
    for base in sorted(groups):
        sides = ", ".join(sorted(groups[base]))
        new_base = new_base_by_old[base]
        if base != new_base:
            print(f"  {base}  [{sides}]")
            print(f"    → {new_base}{suffix}")
        else:
            print(f"  {base}  [{sides}]  (name unchanged)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rename a session in raw iPhUMI exported data."
    )
    parser.add_argument(
        "--data-path",
        required=True,
        help="Path to the exported iPhUMI data root (e.g. /media/auspatel/Austin/iPhUMI_export)",
    )
    parser.add_argument(
        "--old-session",
        required=True,
        help="Session name to replace (e.g. austin-053126)",
    )
    parser.add_argument(
        "--new-session",
        required=True,
        help="Replacement session name (e.g. austin-053126-recovery-wrong-task)",
    )
    parser.add_argument(
        "--start",
        required=True,
        help=(
            "Folder name (or full path) of the first run to process. "
            "The side suffix (_left/_right/_head) is stripped and all side variants "
            "are found; the alphabetically earliest is used as the true start."
        ),
    )
    parser.add_argument(
        "--end",
        required=True,
        help=(
            "Folder name (or full path) of the last run to process. "
            "The side suffix (_left/_right/_head) is stripped and all side variants "
            "are found; the alphabetically latest is used as the true end."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes without modifying anything",
    )
    args = parser.parse_args()

    data_path = Path(args.data_path)
    if not data_path.is_dir():
        sys.exit(f"ERROR: --data-path does not exist or is not a directory: {data_path}")

    all_folders = collect_run_folders(data_path)
    target_folders = get_folder_range(all_folders, args.start, args.end)

    range_plans = [
        plan_folder_changes(folder, args.old_session, args.new_session)
        for folder in target_folders
    ]

    # Auto-detect calibrations referenced by in-range demos but outside the range.
    extra_cal_plans = find_extra_calibration_plans(
        range_plans, all_folders, args.old_session, args.new_session
    )

    # ── Summary counts ──────────────────────────────────────────────────────
    all_plans = extra_cal_plans + range_plans
    n_demonstrations = sum(1 for p in range_plans if p["kind"] == "demonstration")
    n_calibrations_in_range = sum(1 for p in range_plans if p["kind"] == "calibration")
    n_calibrations_extra = len(extra_cal_plans)
    n_file_ops = sum(len(p["file_renames"]) for p in all_plans)
    n_json_updates = sum(len(p["json_field_updates"]) for p in all_plans)

    mode = "DRY RUN — no changes will be made" if args.dry_run else "APPLYING CHANGES"
    print(f"\n{'=' * 60}")
    print(f"  {mode}")
    print(f"  {args.old_session!r}  →  {args.new_session!r}")
    print(f"{'=' * 60}")
    print(f"  Demonstrations           : {n_demonstrations}  (will be RENAMED)")
    print(f"  Calibrations in range    : {n_calibrations_in_range}  (will be COPIED, original kept)")
    print(f"  Calibrations auto-added  : {n_calibrations_extra}  (referenced outside range, will be COPIED)")
    print(f"  File renames/copies      : {n_file_ops}")
    print(f"  JSON field edits         : {n_json_updates}")
    print(f"{'=' * 60}\n")

    # ── Per-folder detail ───────────────────────────────────────────────────
    if extra_cal_plans:
        print("── Calibrations auto-detected outside range (will be COPIED) ──\n")
        # Check if any destinations already exist.
        any_exists = any(
            (p["folder"].parent / p["new_folder_name"]).exists() for p in extra_cal_plans
        )
        note = "destination already exists — will skip" if any_exists else ""
        print_plans_grouped(extra_cal_plans, note)
        print()

    print("── Demonstrations in range (will be RENAMED) ─────────────────\n")
    print_plans_grouped([p for p in range_plans if p["kind"] == "demonstration"])
    if any(p["kind"] == "calibration" for p in range_plans):
        print()
        print("── Calibrations in range (will be COPIED) ────────────────────\n")
        print_plans_grouped([p for p in range_plans if p["kind"] == "calibration"])

    if args.dry_run:
        print("Dry run complete — no files were modified.")
        return

    # ── Apply ───────────────────────────────────────────────────────────────
    for plan in all_plans:
        if plan["folder_op"] == "copy":
            apply_calibration_copy(plan)
        else:
            apply_demonstration_rename(plan)

    print(
        f"Done. Copied {n_calibrations_in_range + n_calibrations_extra} calibration folder(s), "
        f"renamed {n_demonstrations} demonstration folder(s), "
        f"updated {n_json_updates} JSON fields."
    )


if __name__ == "__main__":
    main()
