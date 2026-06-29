import json
import os
import pickle

import numpy as np
from tqdm import tqdm

from iphumi.common.pose_util import mat_to_pose
from iphumi.demonstration_processing.utils.generic_util import (
    get_aligned_trajectory_path,
    get_demonstration_json_data,
    get_demonstration_sides_present,
    get_demonstration_type,
    read_aligned_csv,
    read_demonstration_metadata,
    normalize_side_for_session_mode,
    SIDES_MODES,
)
from iphumi.demonstration_processing.utils.gripper_util import (
    get_demo_gripper_width,
    iphone_to_tcp_poses,
)


def gen_dataset_plan(
    session_dir: str,
    out_plan_path: str,
    task_filters=None,
):
    all_plans = []
    demos_dir = os.path.join(session_dir, "demos")
    demo_names = sorted(os.listdir(demos_dir))
    for demo_name in tqdm(demo_names, desc="gen_dataset_plan"):
        demo_dir = os.path.join(demos_dir, demo_name)
        demonstration_type = get_demonstration_type(demo_dir)

        if demonstration_type == "grippercalibration":
            continue
        assert demonstration_type == "demonstration"

        labels_path = os.path.join(demo_dir, "labels_aligned.json")
        with open(labels_path, "r") as f:
            labels_data = json.load(f)
        tasks = labels_data["tasks"]
        for task in tasks:
            task["start_idx"] = task.pop("relative_aligned_start_frame_idx")
            task["end_idx"] = task.pop("relative_aligned_end_frame_idx")

        if task_filters:
            task_set = set(task_filters)
            tasks = [task for task in tasks if task["name"] in task_set]

        sides_for_demo = get_demonstration_sides_present(demo_dir)
        demo_json = get_demonstration_json_data(demo_dir, sides_for_demo[0])
        is_error_correction = demo_json.get("isErrorCorrection", False)

        plan = {
            "tasks": tasks,
            "episode_name": demo_name,
            "is_error_correction": is_error_correction,
        }

        sides_present = get_demonstration_sides_present(demo_dir)

        # Respect the sides recorded in session_info.json (set by create_session_iphone.py).
        sides_mode = None
        session_info_path = os.path.join(session_dir, 'session_info.json')
        if os.path.exists(session_info_path):
            with open(session_info_path) as f:
                sides_mode = json.load(f).get('sides')
            if sides_mode is not None:
                allowed = SIDES_MODES[sides_mode]
                sides_present = [s for s in sides_present if s in allowed]

        aligned_metadata = read_demonstration_metadata(demo_dir)
        aligned_times = aligned_metadata.get("aligned_frame_times")
        if aligned_times is None:
            raise FileNotFoundError(
                f"Missing aligned_frame_times metadata for {demo_dir}. "
                "Run process_demos_iphone align first."
            )

        for side in sides_present:
            # canonical_side is the key used in the plan (and downstream in the
            # replay buffer). In single/single_and_head mode 'left' and 'right'
            # are the same physical gripper so both normalise to SINGLE_CANONICAL_SIDE.
            # All file/calibration lookups below still use the original `side`.
            canonical_side = normalize_side_for_session_mode(side, sides_mode)

            trajectory_path = get_aligned_trajectory_path(demo_dir, side)
            if not os.path.exists(trajectory_path):
                raise FileNotFoundError(
                    f"Missing aligned trajectory for {demo_dir} side={side}: {trajectory_path}"
                )

            aligned_data = read_aligned_csv(demo_dir, side)
            arkit_poses = aligned_data["poses"]

            if len(aligned_times) != arkit_poses.shape[0]:
                raise ValueError(
                    f"Aligned frame time count mismatch for {demo_dir} side={side}: "
                    f"{len(aligned_times)} metadata times vs {arkit_poses.shape[0]} poses"
                )

            tcp_pose = mat_to_pose(iphone_to_tcp_poses(demo_dir, side, arkit_poses))
            horizon = tcp_pose.shape[0]

            try:
                gripper_width = get_demo_gripper_width(
                    demo_dir,
                    side,
                    include_detection_types=False,
                    aligned_video_times=aligned_times,
                )
            except (AssertionError, IndexError, ValueError, FileNotFoundError) as e:
                print(f"[{side}] Skipping gripper width extraction for {demo_name}: {e}")
                gripper_width = None

            demo_start_pose = np.tile(tcp_pose[0], (horizon, 1))
            demo_end_pose = np.tile(tcp_pose[-1], (horizon, 1))
            plan[f"grippers_{canonical_side}"] = [
                {
                    "tcp_pose": tcp_pose,
                    "gripper_width": gripper_width,
                    "demo_start_pose": demo_start_pose,
                    "demo_end_pose": demo_end_pose,
                }
            ]

            if os.path.exists(os.path.join(demo_dir, f"{side}_rgb_masked.mp4")):
                main_video_path = os.path.join(demo_name, f"{side}_rgb_masked.mp4")
            else:
                main_video_path = os.path.join(demo_name, f"{side}_rgb.mp4")

            plan[f"cameras_{canonical_side}"] = [
                {
                    "main_video_path": main_video_path,
                    "depth_video_path": os.path.join(demo_name, f"{side}_depth.raw"),
                    "ultrawide_video_path": os.path.join(demo_name, f"{side}_ultrawidergb.mp4"),
                    "pose_idx_to_main_idx": aligned_data["rgb_frame_idx"],
                    "pose_idx_to_depth_idx": aligned_data["depth_frame_idx"],
                    "pose_idx_to_ultrawide_idx": aligned_data["ultrawide_frame_idx"],
                }
            ]

        all_plans.append(plan)

    with open(out_plan_path, "wb") as f:
        pickle.dump(all_plans, f)
    print(f"Wrote dataset plan to {out_plan_path}")
