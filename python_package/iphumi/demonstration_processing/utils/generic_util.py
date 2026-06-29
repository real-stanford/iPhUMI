import os
import copy
from datetime import datetime
import csv
import json
import yaml
from glob import glob
from omegaconf import DictConfig
import re
from iphumi.demonstration_processing.utils.color_util import red, green, yellow
from iphumi.common.timecode_util import datetime_fromisoformat
from iphumi.common.transform_util import pos_quat_xyzw_to_4x4
from pathlib import Path
import cv2
import numpy as np

DEMONSTRATION_SIDES = ("left", "right", "head")

# In single/single_and_head mode, left and right are interchangeable; normalise
# to this canonical name so all episodes end up under the same replay-buffer key.
SINGLE_CANONICAL_SIDE = "right"
SINGLE_MODES = frozenset({"single", "single_and_head"})


def normalize_side_for_session_mode(side: str, sides_mode: str) -> str:
    """Return the canonical side name used for plan/replay-buffer keys.

    In single/single_and_head mode, 'left' and 'right' are the same physical
    gripper so they are both mapped to SINGLE_CANONICAL_SIDE.  'head' and all
    sides in non-single modes are returned unchanged.
    """
    if sides_mode in SINGLE_MODES and side in ("left", "right"):
        return SINGLE_CANONICAL_SIDE
    return side


# Maps each sides mode to the canonical whitelist used to filter a demo's sides.
# For single/single_and_head both 'left' and 'right' are listed so downstream
# code keeps whichever gripper the individual demo actually has.
SIDES_MODES = {
    'left':            ['left'],
    'right':           ['right'],
    'head':            ['head'],
    'single':          ['left', 'right'],
    'bimanual':        ['left', 'right'],
    'left_and_head':   ['left', 'head'],
    'right_and_head':  ['right', 'head'],
    'single_and_head': ['left', 'right', 'head'],
    'bimanual_and_head':   ['left', 'right', 'head'],
}


def infer_sides_mode(demo_sides) -> str:
    """Return the most general sides mode that covers the given set of sides."""
    s = frozenset(demo_sides)
    has_left  = 'left'  in s
    has_right = 'right' in s
    has_head  = 'head'  in s
    both = has_left and has_right
    one  = has_left ^ has_right
    if both and has_head: return 'bimanual_and_head'
    if both:              return 'bimanual'
    if one  and has_head: return 'single_and_head'
    if one:               return 'single'
    if has_head:          return 'head'
    raise ValueError(f"Cannot infer sides mode from {sorted(s)}")


def get_demonstration_video_frame_count(demonstration_dir, side):
    video_path = get_demonstration_main_video_path(demonstration_dir, side)
    assert os.path.exists(video_path)
    cap = cv2.VideoCapture(video_path)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return frame_count

def get_demonstration_video_fps(demonstration_dir, side):
    video_path = get_demonstration_main_video_path(demonstration_dir, side)
    assert os.path.exists(video_path)
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    return fps

def get_demonstration_json_data(demonstration_dir, side):
    json_path = os.path.join(demonstration_dir, f'{side}.json')
    assert os.path.exists(json_path)
    with open(json_path, 'r') as f:
        return json.load(f)

def build_demonstration_iphone_calibration(demonstration_dir, side, calibration_dict):
    json_data = get_demonstration_json_data(demonstration_dir, side)

    system_name = json_data.get("deviceIdentifier", "iPhone16,1")
    gripper_id = json_data.get("gripperID", "default")
    has_gripper_mount = side != "head" and gripper_id not in (None, "")

    result = {}
    if has_gripper_mount:
        assert (
            gripper_id in calibration_dict
        ), f"Missing gripper ID '{gripper_id}' in iphone_calibration.yaml. Available gripper IDs: {list(calibration_dict.keys())}"
        assert (
            system_name in calibration_dict[gripper_id]
        ), f"Missing device identifier '{system_name}' under gripper ID '{gripper_id}' in iphone_calibration.yaml. Available devices: {list(calibration_dict[gripper_id].keys())}"
        result = copy.deepcopy(calibration_dict[gripper_id][system_name])

    if 'camera_calibration' not in result:
        result['camera_calibration'] = {}

    if 'mainCameraIntrinsics' in json_data:
        if 'main' not in result['camera_calibration']:
            result['camera_calibration']['main'] = {}
        result['camera_calibration']['main']['intrinsics'] = json_data['mainCameraIntrinsics']
    if 'ultrawideCameraIntrinsics' in json_data:
        if 'ultrawide' not in result['camera_calibration']:
            result['camera_calibration']['ultrawide'] = {}
        result['camera_calibration']['ultrawide']['intrinsics'] = json_data['ultrawideCameraIntrinsics']

    return result


def get_demonstration_calibration(demonstration_dir: str, side: str):
    """
    Load the per-demonstration, per-side calibration saved as {side}_calibration.yaml.
    """
    side_calib_path = Path(demonstration_dir).joinpath(f"{side}_calibration.yaml")
    assert side_calib_path.exists(), f"Missing calibration file: {side_calib_path}"
    with open(side_calib_path, "r") as f:
        return yaml.safe_load(f)

def get_demonstration_main_video_path(demonstration_dir, side):
    return os.path.join(demonstration_dir, f'{side}_rgb.mp4')

def get_demonstration_frame_times(demonstration_dir, side):
    demonstration_json = get_demonstration_json_data(demonstration_dir, side)
    return demonstration_json['rgbTimes']


def get_aligned_trajectory_path(demonstration_dir, side):
    return os.path.join(demonstration_dir, f"{side}_aligned.csv")


def read_aligned_csv(demonstration_dir: str, side: str) -> dict:
    """Read {side}_aligned.csv and return poses and per-modality frame index arrays."""
    csv_path = get_aligned_trajectory_path(demonstration_dir, side)
    pos_quat_rows, rgb_indices, depth_indices, ultrawide_indices = [], [], [], []
    with open(csv_path, "r", newline="") as f:
        for row in csv.DictReader(f):
            pos_quat_rows.append([
                float(row["x"]), float(row["y"]), float(row["z"]),
                float(row["q_x"]), float(row["q_y"]), float(row["q_z"]), float(row["q_w"]),
            ])
            rgb_indices.append(int(row["rgb_frame_idx"]))
            depth_indices.append(int(row["depth_frame_idx"]))
            ultrawide_indices.append(int(row["ultrawide_frame_idx"]))
    return {
        "poses": pos_quat_xyzw_to_4x4(np.asarray(pos_quat_rows, dtype=np.float64)),
        "rgb_frame_idx": np.asarray(rgb_indices, dtype=np.int64),
        "depth_frame_idx": np.asarray(depth_indices, dtype=np.int64),
        "ultrawide_frame_idx": np.asarray(ultrawide_indices, dtype=np.int64),
    }


def get_aligned_frame_times(demonstration_dir):
    metadata = read_demonstration_metadata(demonstration_dir)
    if "aligned_frame_times" not in metadata or metadata["aligned_frame_times"] is None:
        raise FileNotFoundError(
            f"Missing aligned_frame_times metadata for {demonstration_dir}. "
            "Run the align stage first."
        )
    return metadata["aligned_frame_times"]


def validate_tracking_artifacts(demonstration_dir, side):
    trajectory_path = get_aligned_trajectory_path(demonstration_dir, side)
    if not os.path.exists(trajectory_path):
        raise FileNotFoundError(
            f"Missing aligned trajectory for {demonstration_dir} side={side}: {trajectory_path}"
        )

    frame_times = get_aligned_frame_times(demonstration_dir)
    if len(frame_times) == 0:
        raise ValueError(f"Aligned frame-time metadata is empty for {demonstration_dir} side={side}")

    csv_rows = []
    with open(trajectory_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            csv_rows.append(row)

    if len(csv_rows) == 0:
        raise ValueError(f"Aligned trajectory CSV is empty for {demonstration_dir} side={side}")

    if len(csv_rows) != len(frame_times):
        raise ValueError(
            f"Aligned trajectory / metadata length mismatch for {demonstration_dir} side={side}: "
            f"{len(csv_rows)} csv rows vs {len(frame_times)} frame times"
        )

    timestamps = np.asarray([float(row["relative_aligned_timestamp"]) for row in csv_rows], dtype=np.float64)
    if np.any(np.diff(timestamps) < 0):
        raise ValueError(
            f"Aligned trajectory timestamps are not monotonic for {demonstration_dir} side={side}"
        )


def validate_demonstration_tracking_artifacts(demonstration_dir):
    for side in get_demonstration_sides_present(demonstration_dir):
        validate_tracking_artifacts(demonstration_dir, side)

def get_demonstration_sides_present(demonstration_dir):
    sides = []
    for side in DEMONSTRATION_SIDES:
        json_path = os.path.join(demonstration_dir, f'{side}.json')
        if os.path.exists(json_path):
            sides.append(side)
    return sides

def get_demonstration_property(demonstration_dir, side, property_name):
    demonstration_json = get_demonstration_json_data(demonstration_dir, side)
    return demonstration_json[property_name]

def get_gripper_calibration_run_dir(demonstration_dir, side):
    """Given a specific demonstration, returns the gripper calibration run directory. First look into the demonstration folder structure which has folders for each day, if if not present, then check in the same directory as the given demonstration"""
    # TODO: there are other places where this function can be used to simplify logic
    demonstration_json = get_demonstration_json_data(demonstration_dir, side)
    gripper_cal_run_name = demonstration_json['gripperCalibrationRunName']
    gripper_cal_run_dir = get_demonstration_path(get_demonstrations_dir_from_specific_dir(demonstration_dir), gripper_cal_run_name)

    # attempt search in same directory as given demonstration if previous search failed
    if not os.path.exists(gripper_cal_run_dir):
        gripper_cal_run_dir = os.path.join(
            os.path.dirname(demonstration_dir),
            gripper_cal_run_name.replace('_right', '').replace('_left', '').replace('_head', '')
        )
    
    assert os.path.exists(gripper_cal_run_dir), f"Gripper calibration run directory not found: {gripper_cal_run_dir}"

    return gripper_cal_run_dir


def get_demonstrations_dir_from_specific_dir(demonstrations_dir):
    """Given a specific demonstration directory, return the parent demonstrations directory containing the rest of the demonstrations"""
    return Path(demonstrations_dir).parent.parent.as_posix()


def get_demonstration_path(demonstrations_dir, demonstration_name):
    demonstration_name = (
        demonstration_name
        .replace('_right', '')
        .replace('_left', '')
        .replace('_head', '')
    )
    demonstration_time_str_iso8601 = demonstration_name[:demonstration_name.index('T')]
    demonstration_time = datetime_fromisoformat(demonstration_time_str_iso8601)
    demonstration_ymd = demonstration_time.strftime('%Y-%m-%d')
    path = os.path.join(demonstrations_dir, demonstration_ymd, demonstration_name)
    return path


def get_reference_side(sides_present):
    if "head" in sides_present:
        return "head"
    return sides_present[0]


def demonstration_to_display_string(demonstration_dir, side=None):
    colored_demonstration_dir = green(demonstration_dir)
    if side is None:
        return f'[{colored_demonstration_dir}]'
    else:
        json_path = os.path.join(demonstration_dir, f'{side}.json')
        if not os.path.exists(json_path):
            return f'[{colored_demonstration_dir} {side}]'

        demonstration_json = get_demonstration_json_data(demonstration_dir, side)
        note = (f" \"{demonstration_json['note']}\"") if 'note' in demonstration_json and demonstration_json['note'] else ''
        return f'[{yellow(demonstration_json["sessionName"])} {colored_demonstration_dir} {side}{red(note)}]'

"""Demonstration metadata"""

def write_demonstration_metadata(demonstration_dir, metadata_dict, overwrite_all=False):
    if not overwrite_all:
        metadata_dict = {**read_demonstration_metadata(demonstration_dir), **metadata_dict}

    metadata_path = os.path.join(demonstration_dir, 'metadata.yaml')
    with open(metadata_path, 'w') as f:
        yaml.safe_dump(metadata_dict, f)


def read_demonstration_metadata(demonstration_dir):
    metadata_path = os.path.join(demonstration_dir, 'metadata.yaml')
    if not os.path.exists(metadata_path):
        with open(metadata_path, 'w') as f:
            yaml.safe_dump({}, f)
    
    with open(metadata_path, 'r') as f:
        metadata_dict = yaml.safe_load(f)
    return metadata_dict



"""Filtering demonstrations"""

def get_demonstration_type(demonstration_dir):
    demonstration_name = os.path.basename(demonstration_dir)
    return demonstration_name.split('_')[-1]

def calculate_max_position_delta(file_path: str) -> float:
    """Calculate the maximum position delta between consecutive timestamps in a json file with poseTimes and poseTransforms keys"""
    with open(file_path, 'r') as f:
        data = json.load(f)
    
    pose_times = data['poseTimes']
    pose_transforms = data['poseTransforms']
    
    if len(pose_times) < 2 or len(pose_transforms) < 2:
        return 0.0
        
    # Extract positions from transforms
    positions = [np.array(transform)[:3, 3] for transform in pose_transforms]
    positions = np.array(positions)
    
    # Calculate position deltas between consecutive timestamps
    max_delta = 0.0
    for i in range(1, len(positions)):
        # Calculate Euclidean distance between consecutive positions
        delta = np.linalg.norm(positions[i] - positions[i-1])
        max_delta = max(max_delta, delta)

    return max_delta

def keep_demonstration(demonstration_title, demonstration_json_path, filters: DictConfig, demo_type=None):
    if type(demo_type) == str:
        demo_type = [demo_type]
    if demo_type is not None and not any([demonstration_title.endswith(f'_{type}') for type in demo_type]):
        return False

    if filters.demonstration_names is not None and demonstration_title not in filters.demonstration_names:
        return False
    
    if filters.demonstration_regex is not None and not re.search(filters.demonstration_regex, demonstration_title):
        return False
    
    if filters.task_names is not None:
        if 'gripper' not in demonstration_title:
            with open(demonstration_json_path, 'r') as f:
                    demonstration_json = json.load(f)
                    if 'taskNames' not in demonstration_json:
                        return False  
                    # Convert both to strings for comparison (taskNames in JSON are strings, but filter might be ints)
                    demo_task_names = set(str(t) for t in demonstration_json['taskNames'])
                    filter_task_names = set(str(t) for t in filters.task_names)
                    # if there is no intersection between the task names in the demo and the
                    # task names we are filtering for, we throw out the demo     
                    if not (bool(demo_task_names & filter_task_names)):
                        return False
                
    if filters.session_name:
        # Support both single string and list of strings
        # Handle OmegaConf ListConfig which is used by Hydra
        if hasattr(filters.session_name, '__iter__') and not isinstance(filters.session_name, str):
            session_names = list(filters.session_name)
        else:
            session_names = [filters.session_name]
        
        split = demonstration_title.split('_')
        if len(split) == 4:
            demonstration_time_str, demonstration_randomizer, demonstration_session_name, recording_type = split
            if demonstration_session_name not in session_names:
                return False
        else:
            # TODO: eventually remove this legacy format
            with open(demonstration_json_path, 'r') as f:
                demonstration_json = json.load(f)
                if 'sessionName' not in demonstration_json:
                    return False
                else:
                    if demonstration_json['sessionName'] not in session_names:
                        return False
    # filter out demos that have position changes greater than a certain threshold between consecutive frames
    if filters.get('max_position_delta', None):
        max_position_delta = calculate_max_position_delta(demonstration_json_path)
        if max_position_delta > filters.max_position_delta:
            return False
    
    return True


def iterate_demonstrations(demonstrations_dir, filters: DictConfig, demo_type=None):
    num_processed = 0
    for demonstration_dir in sorted(list(glob(demonstrations_dir + '/*/*'))):
        if not os.path.isdir(demonstration_dir):
            continue

        demonstration_json_path = None
        for side in DEMONSTRATION_SIDES:
            candidate_path = os.path.join(demonstration_dir, f'{side}.json')
            if os.path.exists(candidate_path):
                demonstration_json_path = candidate_path
                break
        assert demonstration_json_path is not None, f"No side JSON found in {demonstration_dir}"
        if not keep_demonstration(os.path.basename(demonstration_dir), demonstration_json_path, filters, demo_type):
            continue

        if num_processed == filters.max_demos:
            break

        yield demonstration_dir
        num_processed += 1


def demonstration_has_data_for_side(demonstration_dir, side):
    video_path = os.path.join(demonstration_dir, f'{side}.mp4')
    return os.path.exists(video_path)
