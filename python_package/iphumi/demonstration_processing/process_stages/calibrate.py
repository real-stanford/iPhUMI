import os
from omegaconf import DictConfig
from pathlib import Path
import collections
import json
import numpy as np
from typing import Tuple

from iphumi.demonstration_processing.utils.generic_util import (
    demonstration_to_display_string,
    get_demonstration_sides_present,
    get_demonstration_calibration,
)
import yaml


def calibrate_gripper_range_iphone(demonstration_iterator, cfg: DictConfig):
    """Adapted from 05_run_calibrations.py from UMI"""
    skipped_calibrations = set()
    processed_calibrations = set()
    for demonstration_dir in demonstration_iterator('grippercalibration'):
        for side in get_demonstration_sides_present(demonstration_dir):
            tag_path = Path(demonstration_dir).joinpath(f'{side}_tag_detection.json').absolute()
            gripper_range_path = Path(demonstration_dir).joinpath(f'{side}_gripper_range.json').absolute()
            calibration = get_demonstration_calibration(demonstration_dir, side)
            if side == "head" or "gripper_transform" not in calibration:
                continue
            
            if gripper_range_path.exists() and not cfg.overwrite:
                if demonstration_dir not in processed_calibrations:
                    skipped_calibrations.add(demonstration_dir)
                continue

            print(f'Processing {demonstration_to_display_string(demonstration_dir, side)} ', end='')

            input = str(tag_path)
            output = str(gripper_range_path)
            tag_det_threshold = cfg.tag_det_threshold

            with open(input, 'r') as f:
                tag_detection_results = json.load(f)
            for frame in tag_detection_results:
                frame['tag_dict'] = {int(k): v for k, v in frame['tag_dict'].items()}
    
            # identify gripper hardware id
            n_frames = len(tag_detection_results)
            tag_counts = collections.defaultdict(lambda: 0)
            for frame in tag_detection_results:
                for key in frame['tag_dict'].keys():
                    tag_counts[key] += 1
            tag_stats = collections.defaultdict(lambda: 0.0)
            for k, v in tag_counts.items():
                tag_stats[k] = v / n_frames

            max_tag_id = np.max(list(tag_stats.keys()))
            tag_per_gripper = 2
            max_gripper_id = max_tag_id // tag_per_gripper

            gripper_prob_map = dict()
            for gripper_id in range(max_gripper_id+1):
                left_id = gripper_id * tag_per_gripper
                right_id = left_id + 1
                left_prob = tag_stats[left_id]
                right_prob = tag_stats[right_id]
                gripper_prob = min(left_prob, right_prob)
                if gripper_prob <= 0:
                    continue
                gripper_prob_map[gripper_id] = gripper_prob
            if len(gripper_prob_map) == 0:
                print("No grippers detected!")
                assert False

            gripper_probs = sorted(gripper_prob_map.items(), key=lambda x:x[1])
            gripper_id = gripper_probs[-1][0]
            gripper_prob = gripper_probs[-1][1]
            print(f"Detected gripper id: {gripper_id} with probability {gripper_prob}")
            if gripper_prob < tag_det_threshold:
                print(f"Detection rate {gripper_prob} < {tag_det_threshold} threshold.")
                assert False
                
            # run calibration
            left_id = gripper_id * tag_per_gripper
            right_id = left_id + 1

            nominal_z = calibration['gripper_transform']['artag_z_distance_from_ultrawide']

            z_tolerance = 0.08
            zmax = nominal_z + z_tolerance
            zmin = nominal_z - z_tolerance

            left_x_raws = []
            right_x_raws = []
            width_both_samples = []
            for dt in tag_detection_results:
                tag_dict = dt['tag_dict']

                left_x_raw = None
                if left_id in tag_dict:
                    tvec = tag_dict[left_id]['tvec']
                    if zmin < tvec[-1] < zmax:
                        left_x_raw = tvec[0]

                right_x_raw = None
                if right_id in tag_dict:
                    tvec = tag_dict[right_id]['tvec']
                    if zmin < tvec[-1] < zmax:
                        right_x_raw = tvec[0]

                if (left_x_raw is not None) and (right_x_raw is not None):
                    left_x_raws.append(left_x_raw)
                    right_x_raws.append(right_x_raw)
                    width_both_samples.append(right_x_raw - left_x_raw)

            left_x_raws = np.asarray(left_x_raws, dtype=np.float64)
            right_x_raws = np.asarray(right_x_raws, dtype=np.float64)
            width_both_samples = np.asarray(width_both_samples, dtype=np.float64)

            result = {
                'gripper_id': gripper_id,
                'left_finger_tag_id': left_id,
                'right_finger_tag_id': right_id,
            }

            # Fit linear prediction maps from both-tag frames.
            if width_both_samples.size < 3:
                raise ValueError(
                    f"Not enough valid both-tag frames for gripper {gripper_id} / side {side}: "
                    f"n_both_frames={int(width_both_samples.size)}"
                )

            # Use the raw observed extrema (no percentile clipping).
            min_width = float(np.nanmin(width_both_samples))
            max_width = float(np.nanmax(width_both_samples))

            def fit_line(x: np.ndarray, y: np.ndarray) -> Tuple[float, float, float]:
                # Fit y = a + b*x, returning (a, b, mae).
                b, a = np.polyfit(x, y, 1)
                resid = y - (b * x + a)
                med = float(np.median(resid))
                mad = float(np.median(np.abs(resid - med)))
                if mad > 0:
                    thresh = 3.0 * mad
                    mask = np.abs(resid - med) <= thresh
                    if np.sum(mask) >= 3:
                        b, a = np.polyfit(x[mask], y[mask], 1)
                        resid = y[mask] - (b * x[mask] + a)
                mae = float(np.mean(np.abs(resid)))
                return float(a), float(b), mae

            a_lr, b_lr, mae_lr = fit_line(left_x_raws, right_x_raws)
            a_rl, b_rl, mae_rl = fit_line(right_x_raws, left_x_raws)

            left_to_right = {'a': a_lr, 'b': b_lr}
            right_to_left = {'a': a_rl, 'b': b_rl}
            fit_stats = {
                'n_both_frames': int(width_both_samples.size),
                'mae_left_to_right': mae_lr,
                'mae_right_to_left': mae_rl,
            }

            result['max_width'] = max_width
            result['min_width'] = min_width
            result['x_basis'] = 'tvec0'
            result['left_to_right'] = left_to_right
            result['right_to_left'] = right_to_left
            result['fit_stats'] = fit_stats
            
            json.dump(result, open(output, 'w'), indent=2)

            processed_calibrations.add(demonstration_dir)
            if demonstration_dir in skipped_calibrations:
                skipped_calibrations.remove(demonstration_dir)
    
    print(f"\nProcessed {len(processed_calibrations)} gripper calibrations")
    print(f"Previously processed {len(skipped_calibrations)} gripper calibrations")
