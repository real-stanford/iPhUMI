import json
import shutil
from collections import defaultdict
from pathlib import Path
import hydra
from omegaconf import DictConfig
from tqdm import tqdm
from iphumi.demonstration_processing.utils.generic_util import iterate_demonstrations, DEMONSTRATION_SIDES

_RAW_SUFFIXES = ['_rgb.mp4', '_ultrawidergb.mp4', 'ultrawidergb.mp4', '_depth.raw', '_depthpreview.mp4', '_calibration.yaml']
_DEPTH_SUFFIXES = {'_depth.raw', '_depthpreview.mp4'}


def _is_raw_iphone_file(filename: str, exclude_depth: bool = False) -> bool:
    for side in DEMONSTRATION_SIDES:
        if filename == f'{side}.json':
            return True
        for suffix in _RAW_SUFFIXES:
            if exclude_depth and suffix in _DEPTH_SUFFIXES:
                continue
            if filename == f'{side}{suffix}':
                return True
    return False


def _get_session_name(demo_path: Path) -> str:
    parts = demo_path.name.split('_')
    if len(parts) == 4:
        return parts[2]
    for side in DEMONSTRATION_SIDES:
        json_path = demo_path / f'{side}.json'
        if json_path.exists():
            try:
                with open(json_path) as f:
                    return json.load(f).get('sessionName', 'unknown')
            except Exception:
                pass
    return 'unknown'


def _demo_type(name: str) -> str:
    if name.endswith('_demonstration'):
        return 'demonstration'
    if name.endswith('_grippercalibration'):
        return 'calibration'
    return 'unknown'


@hydra.main(version_base="1.2", config_name="share_iphumi_data", config_path="./config")
def main(cfg: DictConfig):
    assert cfg.output_name, "output_name must be set in the config"

    suffix = '-raw' if cfg.raw_only else '-full'
    output_base = (Path('tmp_sharing') / (cfg.output_name + suffix)).resolve()
    print(f"Output folder: {output_base}\n")

    if output_base.exists():
        if not cfg.overwrite:
            raise RuntimeError(f"Output folder already exists: {output_base}\nSet overwrite=true to delete and re-export.")
        shutil.rmtree(output_base)
    output_base.mkdir(parents=True)

    # Collect all matching entries
    entries = []
    for demonstration_dir in iterate_demonstrations(cfg.demonstrations_dir, cfg.filters):
        demo_path = Path(demonstration_dir)
        if cfg.raw_only:
            files = sorted(f for f in demo_path.iterdir() if f.is_file() and _is_raw_iphone_file(f.name, cfg.exclude_depth))
        else:
            files = sorted(f for f in demo_path.iterdir() if f.is_file())
        entries.append({
            'path': demo_path,
            'files': files,
            'type': _demo_type(demo_path.name),
            'session': _get_session_name(demo_path),
        })

    # Print plan
    print("Demonstrations to copy:")
    for e in entries:
        print(f"  {e['path'].name}  ({len(e['files'])} files)")

    # Print statistics
    n_demos = sum(1 for e in entries if e['type'] == 'demonstration')
    n_cals = sum(1 for e in entries if e['type'] == 'calibration')
    by_session = defaultdict(lambda: {'demonstrations': 0, 'calibrations': 0})
    for e in entries:
        by_session[e['session']][e['type'] + 's'] += 1

    print(f"\nTotal demonstrations: {n_demos}")
    print(f"Total calibrations:   {n_cals}")
    print("\nBy session:")
    for session, counts in sorted(by_session.items()):
        print(f"  {session}: {counts['demonstrations']} demonstrations, {counts['calibrations']} calibrations")

    # Copy
    print()
    total_files = sum(len(e['files']) for e in entries)
    total_copied = 0
    with tqdm(total=total_files, unit='file') as pbar:
        for e in entries:
            dest_dir = output_base / e['path'].parent.name / e['path'].name
            dest_dir.mkdir(parents=True)
            for src in e['files']:
                dest = dest_dir / src.name
                if cfg.exclude_depth and src.suffix == '.json':
                    with open(src) as f:
                        data = json.load(f)
                    data['hasDepth'] = False
                    with open(dest, 'w') as f:
                        json.dump(data, f)
                else:
                    shutil.copy2(src, dest)
                pbar.update(1)
            total_copied += len(e['files'])

    print(f"\nDone. {total_copied} files copied.")
    print(f"\nTotal demonstrations: {n_demos}")
    print(f"Total calibrations:   {n_cals}")
    print("\nBy session:")
    for session, counts in sorted(by_session.items()):
        print(f"  {session}: {counts['demonstrations']} demonstrations, {counts['calibrations']} calibrations")
    print(f"\nOutput folder: {output_base}")

    if cfg.zip:
        zip_path = output_base.parent / output_base.name
        print(f"\nZipping → {zip_path}.zip ...")
        shutil.make_archive(str(zip_path), 'zip', output_base.parent, output_base.name)
        print(f"Done. {zip_path}.zip")


if __name__ == '__main__':
    main()
