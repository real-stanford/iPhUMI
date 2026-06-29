from omegaconf import DictConfig
import os
import multiprocessing
import pathlib
from tqdm import tqdm
from typing import List, Dict, Any

from iphumi.demonstration_processing.utils.generic_util import (
    demonstration_to_display_string,
    get_demonstration_json_data,
    get_demonstration_sides_present,
    get_demonstration_calibration,
)
from iphumi.demonstration_processing.scripts.detect_aruco_iphone import (
    run_detection as run_aruco_detection,
)


def _detect_worker(job: Dict[str, Any]) -> None:
    """Process entrypoint for AR tag detection on a single video."""
    run_aruco_detection(
        input=job["input"],
        output=job["output"],
        ultrawideIntrinsics=job["ultrawideIntrinsics"],
        aruco_yaml=job["aruco_yaml"],
        num_workers=job["num_workers"],
        time_offset=job["time_offset"],
    )


def detect_ar_tag_iphone(demonstration_iterator, cfg: DictConfig):
    """Run AR tag detection for iPhone ultrawide videos using multiprocessing."""
    processed_demos = set()
    processed_calibrations = set()
    skipped_demos = set()
    skipped_calibrations = set()

    # Build jobs for all demonstration videos that need processing
    jobs: List[Dict[str, Any]] = []
    for demonstration_dir in demonstration_iterator(['demonstration', 'grippercalibration']):
        demo_type = os.path.basename(demonstration_dir).split('_')[-1]
        is_calibration = demo_type == 'grippercalibration'
        processed_set = processed_calibrations if is_calibration else processed_demos
        skipped_set = skipped_calibrations if is_calibration else skipped_demos

        for side in get_demonstration_sides_present(demonstration_dir):
            video_path = pathlib.Path(demonstration_dir).joinpath(f'{side}_ultrawidergb.mp4').absolute()
            json_path = pathlib.Path(demonstration_dir).joinpath(f'{side}_tag_detection.json')

            if not json_path.exists() or cfg.overwrite:
                print(f'Going to detect AR tag for {demonstration_to_display_string(demonstration_dir, side)}')
                processed_set.add(demonstration_dir)
            elif demonstration_dir not in processed_set:
                skipped_set.add(demonstration_dir)
                continue

            # since the ultrawide records at 10Hz, the first frame of the ultrawide may not necessarily be the
            # first frame of the main camera video. Thus we need to offset the timestamps put into the tag
            # detection results so that they correspond to the actual beginning of the recording.
            demonstration_json = get_demonstration_json_data(demonstration_dir, side)
            ultrawideIntrinsics = demonstration_json.get("ultrawideCameraIntrinsics", None)
            if ultrawideIntrinsics is None:
                camera_calibration = get_demonstration_calibration(demonstration_dir, side)
                ultrawideIntrinsics = camera_calibration["camera_calibration"]["ultrawide"]["intrinsics"]
            video_times = demonstration_json['ultrawideRGBTimes']
            i = 0
            while video_times[i] == "":  # empty time indicates no ultrawide frame captured
                i += 1
            time_offset = 1 / 60 * i  # main camera records at 60Hz

            jobs.append(
                {
                    "input": str(video_path),
                    "output": str(json_path),
                    "ultrawideIntrinsics": ultrawideIntrinsics,
                    "aruco_yaml": os.path.abspath(cfg.aruco_config),
                    "num_workers": 1,
                    "time_offset": time_offset,
                }
            )

    # Validate shared paths once
    if jobs:
        aruco_yaml = jobs[0]["aruco_yaml"]
        assert os.path.isfile(aruco_yaml)

    # Launch multiprocessing pool to process videos in parallel
    num_workers = cfg.num_workers or multiprocessing.cpu_count()

    if jobs:
        with multiprocessing.Pool(processes=num_workers) as pool:
            for _ in tqdm(
                pool.imap_unordered(_detect_worker, jobs),
                total=len(jobs),
                desc="Detecting AR tags",
            ):
                pass

    print(f'\nProcessed {len(processed_demos)} demonstrations, {len(processed_calibrations)} gripper calibrations')
    print(f'Previously processed {len(skipped_demos)} demonstrations, {len(skipped_calibrations)} gripper calibrations')
