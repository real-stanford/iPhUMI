import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import yaml

from iphumi.demonstration_processing.utils.generic_util import (
    get_gripper_calibration_run_dir,
    get_demonstration_json_data,
    get_demonstration_calibration,
)
from iphumi.common.timecode_util import datetime_fromisoformat
from iphumi.demonstration_processing.utils.interpolation_util import (
    get_gripper_calibration_interpolator,
    get_interp1d,
)

def get_demo_gripper_width(
    demonstration_dir: str,
    side: str,
    include_detection_types: bool = False,
    aligned_video_times=None,
):
    """Returns a list of gripper widths for each frame in the demonstration. Adapted from 06_generate_dataset_plan.py from UMI.
    Note that since the iphone records ultrawide at 10Hz (and ultrawide is used to detect AR tags), but since we want to have gripper width for every frame of the main camera video (which is at 60Hz)

    Returns:
    - gripper_widths: list of gripper widths for each frame in the demonstration
    - gripper_detection_types: list of integers indicating the presence of the gripper in each frame. 0: not present, 1: both fingers present, 2: left finger only, 3: right finger only
    """

    if side == "head":
        if include_detection_types:
            return None, None
        return None

    calibration = get_demonstration_calibration(demonstration_dir, side)
    if "gripper_transform" not in calibration:
        if include_detection_types:
            return None, None
        return None

    # find the associated gripper calibration
    gripper_cal_run_dir = get_gripper_calibration_run_dir(demonstration_dir, side)

    # get the gripper calibration interpolator
    with open(Path(gripper_cal_run_dir).joinpath(f'{side}_gripper_range.json'), 'r') as f:
        gripper_range_data = json.load(f)
    max_width = gripper_range_data['max_width']
    min_width = gripper_range_data['min_width']
    left_to_right = gripper_range_data['left_to_right']
    right_to_left = gripper_range_data['right_to_left']
    x_basis = gripper_range_data.get('x_basis', 'tvec0')
    if x_basis != 'tvec0':
        raise ValueError(f"Unsupported gripper_range.json x_basis={x_basis!r}; expected 'tvec0'.")
    gripper_cal_data = {
        'aruco_measured_width': [min_width, max_width],
        'aruco_actual_width': [min_width, max_width]
    }
    gripper_cal_interp = get_gripper_calibration_interpolator(**gripper_cal_data)

    # load the tag detection results for the demonstration
    pkl_path = Path(demonstration_dir).joinpath(f'{side}_tag_detection.json')
    with open(pkl_path, 'r') as f:
        tag_detection_results = json.load(f)
    for frame in tag_detection_results:
        frame['tag_dict'] = {int(k): v for k, v in frame['tag_dict'].items()}

    # identify the gripper id
    left_id = gripper_range_data['left_finger_tag_id']
    right_id = gripper_range_data['right_finger_tag_id']

    # extract the gripper width from the tag detection results
    detected_gripper_timestamps = list()
    detected_gripper_widths = list()
    detected_gripper_left_present = list()
    detected_gripper_right_present = list()
    for td in tag_detection_results:
        width, left_present, right_present = get_gripper_width_offset(
            td["tag_dict"],
            left_id=left_id,
            right_id=right_id,
            nominal_z=calibration["gripper_transform"]["artag_z_distance_from_ultrawide"],
            left_to_right=left_to_right,
            right_to_left=right_to_left,
            min_width=min_width,
            max_width=max_width,
        )
        if width is not None:
            detected_gripper_timestamps.append(td['time'])
            detected_gripper_widths.append(gripper_cal_interp(width))
            detected_gripper_left_present.append(left_present)
            detected_gripper_right_present.append(right_present)
    
    # some frames may not have had detections, so we interpolate to fill gaps
    gripper_interp = get_interp1d(detected_gripper_timestamps, detected_gripper_widths)

    # use the main RGB to get the timestamps. This is becuase the ultrawide records the tag detections at 10Hz, but we want to have gripper width for every frame of the main camera video (which is at 60Hz)
    demonstration_json = get_demonstration_json_data(demonstration_dir, side)
    if aligned_video_times is not None:
        video_times = aligned_video_times
    else:
        video_times = demonstration_json['rgbTimes']
    video_times = [datetime_fromisoformat(t) for t in video_times]
    video_times = [(t - video_times[0]).total_seconds() for t in video_times]
    all_gripper_widths = gripper_interp(video_times)

    # compute the frame indices in the main camera video that correspond to the timestamps of gripper detections
    gripper_detection_types = np.zeros(len(video_times), dtype=np.int8)
    for detection_i in range(len(detected_gripper_timestamps)):
        detected_timestamp = detected_gripper_timestamps[detection_i]
        left_present = detected_gripper_left_present[detection_i]
        right_present = detected_gripper_right_present[detection_i]
        main_camera_frame_idx = np.argmin(np.abs(np.array(video_times) - detected_timestamp))
        if left_present and right_present:
            gripper_detection_types[main_camera_frame_idx] = 1
        elif left_present:
            gripper_detection_types[main_camera_frame_idx] = 2
        else:
            gripper_detection_types[main_camera_frame_idx] = 3

    if include_detection_types:
        return all_gripper_widths, gripper_detection_types
    else:
        return all_gripper_widths

def get_gripper_width_offset(
    tag_dict: Dict[int, Any],
    left_id: int,
    right_id: int,
    nominal_z: float,
    z_tolerance: float = 0.08,
    only_side: Optional[str] = None,
    *,
    left_to_right: Dict[str, float],
    right_to_left: Dict[str, float],
    min_width: Optional[float] = None,
    max_width: Optional[float] = None,
):
    """Compute gripper width from AR tag x translations.

    Uses the new linear-map calibration mode to predict the missing finger position when only one tag is visible.
    """
    zmax = nominal_z + z_tolerance
    zmin = nominal_z - z_tolerance

    use_left = only_side == 'left' or only_side is None
    use_right = only_side == 'right' or only_side is None

    left_x = None
    if left_id in tag_dict and use_left:
        tvec = tag_dict[left_id]['tvec']
        # check if depth is reasonable (to filter outliers)
        if zmin < tvec[-1] < zmax:
            left_x = tvec[0]

    right_x = None
    if right_id in tag_dict and use_right:
        tvec = tag_dict[right_id]['tvec']
        if zmin < tvec[-1] < zmax:
            right_x = tvec[0]

    width = None
    if (left_x is not None) and (right_x is not None):
        width = right_x - left_x
    elif left_x is not None:
        a_lr = float(left_to_right['a'])
        b_lr = float(left_to_right['b'])
        right_x_pred = a_lr + b_lr * left_x
        width = right_x_pred - left_x
    elif right_x is not None:
        a_rl = float(right_to_left['a'])
        b_rl = float(right_to_left['b'])
        left_x_pred = a_rl + b_rl * right_x
        width = right_x - left_x_pred

    if width is not None and min_width is not None and max_width is not None:
        width = float(np.clip(width, min_width, max_width))
    
    return width, left_x is not None, right_x is not None

"""Transformations"""

def iphone_to_tcp_poses(
    demonstration_dir: str,
    side: str,
    iphone_poses: np.ndarray,
) -> np.ndarray:
    """
    Convert a sequence of iPhone (ARKit main camera) poses to TCP poses using
    the per-demonstration calibration saved as {side}_calibration.yaml.

    Args:
        demonstration_dir: Path to the demonstration directory.
        side: 'left', 'right', or 'head'.
        iphone_poses: Array of shape (T, 4, 4) with world-to-iPhone transforms (W_T_I).

    Returns:
        tcp_poses: Array of shape (T, 4, 4) with world-to-TCP transforms (W_T_TCP).
    """
    calibration = get_demonstration_calibration(demonstration_dir, side)

    if "gripper_transform" in calibration:
        assert side in ['left', 'right'], f"Gripper transform calibration should only be present for left and right sides, but got side={side!r}"
        i_t_tcp = np.array(
            calibration["gripper_transform"]["tcp_pose_in_arkit_frame"], dtype=np.float32
        )
        assert i_t_tcp.shape == (4, 4)
    else:
        # for the head we just rotate to match the TCP orientation, but do not apply any translation offset since there is no gripper
        assert side == 'head', f"Expected head side for calibration without gripper transform, but got side={side!r}"
        i_t_tcp = np.eye(4, dtype=np.float32)
        arkit_tcp_rot = np.array(
            [[1, 0, 0], [0, -1, 0], [0, 0, -1]], dtype=np.float32
        )
        i_t_tcp[:3, :3] = arkit_tcp_rot

    tcp_poses = np.array([W_T_I @ i_t_tcp for W_T_I in iphone_poses], dtype=np.float32)
    return tcp_poses
