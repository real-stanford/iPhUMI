import shutil
import tempfile
import zipfile
from pathlib import Path
import hydra
from omegaconf import DictConfig
from tqdm import tqdm


def _find_demo_folders(root: Path) -> list[tuple[str, Path]]:
    """Return (date_folder, demo_path) pairs from a shared data root."""
    pairs = []
    for date_dir in sorted(root.iterdir()):
        if not date_dir.is_dir():
            continue
        for demo_dir in sorted(date_dir.iterdir()):
            if demo_dir.is_dir():
                pairs.append((date_dir.name, demo_dir))
    return pairs


@hydra.main(version_base="1.2", config_name="link_shared_iphumi_data", config_path="./config")
def main(cfg: DictConfig):
    assert cfg.shared_path, "shared_path must be set"

    shared = Path(cfg.shared_path)
    dest_base = Path(cfg.demonstrations_dir).resolve()

    tmp_dir = None
    try:
        if shared.suffix == '.zip':
            tmp_dir = tempfile.mkdtemp()
            print(f"Extracting {shared} ...")
            with zipfile.ZipFile(shared, 'r') as zf:
                zf.extractall(tmp_dir)
            extracted = [p for p in Path(tmp_dir).iterdir() if p.is_dir()]
            assert len(extracted) == 1, f"Expected one top-level folder in zip, found: {extracted}"
            root = extracted[0]
        else:
            assert shared.is_dir(), f"shared_path must be a zip file or directory: {shared}"
            root = shared

        pairs = _find_demo_folders(root)
        if not pairs:
            print("No demonstration folders found in shared data.")
            return

        print(f"Found {len(pairs)} folders to import from {shared}\n")

        total_files = sum(
            sum(1 for f in demo_dir.iterdir() if f.is_file())
            for _, demo_dir in pairs
        )

        skipped = []
        with tqdm(total=total_files, unit='file') as pbar:
            for date_folder, demo_dir in pairs:
                dest_dir = dest_base / date_folder / demo_dir.name

                if dest_dir.exists():
                    if not cfg.overwrite:
                        files = [f for f in demo_dir.iterdir() if f.is_file()]
                        pbar.update(len(files))
                        skipped.append(demo_dir.name)
                        continue
                    shutil.rmtree(dest_dir)

                dest_dir.mkdir(parents=True)
                for src in sorted(f for f in demo_dir.iterdir() if f.is_file()):
                    shutil.copy2(src, dest_dir / src.name)
                    pbar.update(1)

        if skipped:
            print(f"\nSkipped {len(skipped)} existing folders (overwrite=false):")
            for name in skipped:
                print(f"  {name}")

        print(f"\nDone. Data imported to {dest_base}")

    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir)


if __name__ == '__main__':
    main()
