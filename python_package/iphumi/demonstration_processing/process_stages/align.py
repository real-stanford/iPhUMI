import csv
import json
import os
from datetime import datetime, timezone

import numpy as np
from omegaconf import DictConfig

from iphumi.common.timecode_util import datetime_fromisoformat
from iphumi.common.transform_util import pose_4x4_to_6d, pose_4x4_to_quat_xyzw, pose_6d_to_4x4
from iphumi.demonstration_processing.utils.generic_util import (
    get_demonstration_sides_present,
    validate_tracking_artifacts,
    write_demonstration_metadata,
)
from iphumi.demonstration_processing.utils.interpolation_util import get_interp1d


def _sample_poses_at_times(poses: np.ndarray, pose_times, sample_times: np.ndarray) -> np.ndarray:
    pose_6d = pose_4x4_to_6d(poses)
    sampled_pose_6d = np.stack(
        [get_interp1d(pose_times, pose_6d[:, dim])(sample_times) for dim in range(pose_6d.shape[1])],
        axis=-1,
    )
    return pose_6d_to_4x4(sampled_pose_6d)


def _compute_frame_indices(time_strings: list, sample_times: np.ndarray, filter_empty: bool = False) -> np.ndarray:
    """Return the most-recent-past frame index for each sample time via searchsorted."""
    if filter_empty:
        time_strings = [t for t in time_strings if t]
    ts = np.array([datetime_fromisoformat(x).timestamp() for x in time_strings], dtype=np.float64)
    return np.clip(np.searchsorted(ts, sample_times, side="right") - 1, 0, len(ts) - 1).astype(np.int64)


def _save_trajectory_csv(
    out_csv_path: str,
    poses: np.ndarray,
    times: np.ndarray,
    rgb_indices: np.ndarray,
    depth_indices: np.ndarray,
    ultrawide_indices: np.ndarray,
) -> None:
    pos_quat_xyzw = pose_4x4_to_quat_xyzw(poses)
    fieldnames = [
        "relative_aligned_frame_idx",
        "relative_aligned_timestamp",
        "x", "y", "z", "q_x", "q_y", "q_z", "q_w",
        "rgb_frame_idx",
        "depth_frame_idx",
        "ultrawide_frame_idx",
    ]
    with open(out_csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        time_offset = times[0]
        for frame_idx, (time_value, pose_value, rgb_i, depth_i, ultra_i) in enumerate(
            zip(times, pos_quat_xyzw, rgb_indices, depth_indices, ultrawide_indices)
        ):
            writer.writerow(
                {
                    "relative_aligned_frame_idx": frame_idx,
                    "relative_aligned_timestamp": f"{time_value - time_offset:.6f}",
                    "x": f"{pose_value[0]:.9f}",
                    "y": f"{pose_value[1]:.9f}",
                    "z": f"{pose_value[2]:.9f}",
                    "q_x": f"{pose_value[3]:.9f}",
                    "q_y": f"{pose_value[4]:.9f}",
                    "q_z": f"{pose_value[5]:.9f}",
                    "q_w": f"{pose_value[6]:.9f}",
                    "rgb_frame_idx": rgb_i,
                    "depth_frame_idx": depth_i,
                    "ultrawide_frame_idx": ultra_i,
                }
            )


def align_multi_iphone_data(demonstration_iterator, cfg: DictConfig):
    num_processed = 0
    num_already_processed = 0
    fps = float(getattr(cfg, "fps", 60))
    dt = 1.0 / fps

    for demonstration_dir in demonstration_iterator("demonstration"):
        sides = get_demonstration_sides_present(demonstration_dir)

        finished = all(
            os.path.exists(os.path.join(demonstration_dir, f"{side}_aligned.csv"))
            for side in sides
        )
        if finished and not cfg.overwrite:
            num_already_processed += 1
            continue

        print(f"[{demonstration_dir}] Aligning sides: {sides}")
        num_processed += 1

        pose_data = {}
        pose_times = {}
        for side in sides:
            pose_path = os.path.join(demonstration_dir, f"{side}.json")
            with open(pose_path, "r") as f:
                side_pose_data = json.load(f)
            side_pose_times = [datetime_fromisoformat(x).timestamp() for x in side_pose_data["poseTimes"]]

            if len(side_pose_times) != len(side_pose_data["poseTransforms"]):
                raise ValueError(
                    f"Pose time count does not match pose count for {demonstration_dir} side={side}"
                )

            pose_data[side] = side_pose_data
            pose_times[side] = side_pose_times

        try:
            valid_start_time = max(times[0] for times in pose_times.values())
            valid_end_time = min(times[-1] for times in pose_times.values())
        except ValueError:
            print(f"Skipping {demonstration_dir} due to empty pose times.")
            continue

        if valid_end_time <= valid_start_time:
            print(
                f"Skipping {demonstration_dir} because overlap is empty: "
                f"start={valid_start_time}, end={valid_end_time}"
            )
            continue

        sample_times = np.arange(valid_start_time, valid_end_time, dt, dtype=np.float64)
        if sample_times.size == 0:
            print(f"Skipping {demonstration_dir} because no aligned samples were produced.")
            continue

        time_strings = [datetime.fromtimestamp(t, timezone.utc).isoformat() for t in sample_times]

        write_demonstration_metadata(demonstration_dir, {"aligned_frame_times": time_strings})
        for side in sides:
            side_data = pose_data[side]

            rgb_indices = _compute_frame_indices(side_data["rgbTimes"], sample_times)
            depth_times = side_data.get("depthTimes", side_data["rgbTimes"])
            depth_indices = _compute_frame_indices(depth_times, sample_times)
            ultrawide_indices = _compute_frame_indices(side_data["ultrawideRGBTimes"], sample_times, filter_empty=True)

            poses = np.asarray(side_data["poseTransforms"], dtype=np.float64)
            sampled_poses = _sample_poses_at_times(poses, pose_times[side], sample_times)
            out_csv_path = os.path.join(demonstration_dir, f"{side}_aligned.csv")
            _save_trajectory_csv(out_csv_path, sampled_poses, sample_times, rgb_indices, depth_indices, ultrawide_indices)
            validate_tracking_artifacts(demonstration_dir, side)

    print(f"\nAligned {num_processed} demonstrations")
    print(f"Previously processed {num_already_processed} demonstrations")
