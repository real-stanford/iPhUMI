"""Given a folder of processed demonstrations, generates a session folder containing the demonstrations you want to use to train a policy."""

import json
import os
import shutil
import re
from glob import glob
import hydra
from omegaconf import DictConfig

from iphumi.common.generic_util import symlink_absolute
from iphumi.demonstration_processing.utils.generic_util import get_demonstration_sides_present, get_demonstration_json_data
from iphumi.demonstration_processing.utils.generic_util import (
    get_demonstration_path,
    validate_demonstration_tracking_artifacts,
    SIDES_MODES,
    infer_sides_mode,
)

def _demo_qualifies(demo_sides, mode: str, strict: bool = False) -> bool:
    s = frozenset(demo_sides)
    has_left  = 'left'  in s
    has_right = 'right' in s
    has_head  = 'head'  in s
    one_gripper  = has_left ^ has_right
    both_grippers = has_left and has_right
    if mode == 'left':
        return has_left and (not strict or (not has_right and not has_head))
    if mode == 'right':
        return has_right and (not strict or (not has_left and not has_head))
    if mode == 'head':
        return has_head and (not strict or (not has_left and not has_right))
    if mode == 'single':
        return one_gripper and (not strict or not has_head)
    if mode == 'bimanual':
        return both_grippers and (not strict or not has_head)
    if mode == 'left_and_head':
        return has_left and has_head and (not strict or not has_right)
    if mode == 'right_and_head':
        return has_right and has_head and (not strict or not has_left)
    if mode == 'single_and_head':
        return one_gripper and has_head
    if mode == 'bimanual_and_head':
        return both_grippers and has_head
    raise ValueError(f"Unknown sides mode {mode!r}. Valid: {sorted(SIDES_MODES)}")


@hydra.main(version_base="1.2", config_path="config", config_name="create_session_iphone")
def main(cfg: DictConfig):
    # Make sure demonstration dir exists
    demonstrations_dir = cfg.demonstrations_dir
    assert os.path.isdir(demonstrations_dir)

    # Create a session folder
    session_dir = os.path.join(cfg.sessions_dir, cfg.output_session_name)
    if os.path.exists(session_dir):
        if cfg.overwrite:
            print(f'Overwriting existing session at {session_dir}')
            shutil.rmtree(session_dir)
        else:
            print(f'Session already exists at {session_dir}')
            exit()
    os.makedirs(session_dir, exist_ok=True)

    # demos
    demos_dir = os.path.join(session_dir, 'demos')
    os.makedirs(demos_dir, exist_ok=True)

    # process demonstrations
    gripper_calibrations_dirs = set()
    num_demonstrations, num_gripper_calibrations, num_skipped = 0, 0, 0
    num_error_correction_episodes, num_non_error_correction_episodes = 0, 0
    task_counts = {}
    session_counts = {}
    error_correction_task_counts = {}
    non_error_correction_task_counts = {}
    session_stats = {}
    def process_demonstration_dir(demonstration_dir, include_gripper_calibrations=False):
        nonlocal num_demonstrations, num_gripper_calibrations, num_skipped, num_error_correction_episodes, num_non_error_correction_episodes
        if os.path.isdir(demonstration_dir):
            base_demo_dir_name = os.path.basename(demonstration_dir)
            session_demo_dir = os.path.join(demos_dir, base_demo_dir_name)
            if os.path.exists(session_demo_dir):
                return


            is_demonstration = base_demo_dir_name.endswith('_demonstration')
            is_gripper_calibration = base_demo_dir_name.endswith('_grippercalibration')

            if is_demonstration:
                if num_demonstrations >= cfg.max_demos and cfg.max_demos >= 0:
                    return

                invalid_path = os.path.join(demonstration_dir, 'invalid.txt')
                valid_path = os.path.join(demonstration_dir, 'valid.txt')
                manual_invalid_path = os.path.join(demonstration_dir, 'manual_invalid.txt')
                manual_valid_path = os.path.join(demonstration_dir, 'manual_valid.txt')
                has_manual_invalid = os.path.exists(manual_invalid_path)
                has_manual_valid = os.path.exists(manual_valid_path)
                has_invalid = os.path.exists(invalid_path)
                has_valid = os.path.exists(valid_path)

                if has_manual_invalid and has_manual_valid:
                    print(f'Skipping {base_demo_dir_name} (error: both manual_invalid.txt and manual_valid.txt present)')
                    num_skipped += 1
                    return
                if has_invalid and has_valid:
                    print(f'Skipping {base_demo_dir_name} (error: both invalid.txt and valid.txt present)')
                    num_skipped += 1
                    return
                if has_manual_invalid:
                    print(f'Skipping {base_demo_dir_name} (manual_invalid.txt present)')
                    num_skipped += 1
                    return
                if has_manual_valid:
                    pass  # manual_valid overrides invalid.txt — include unconditionally
                else:
                    if not has_invalid and not has_valid:
                        shutil.rmtree(session_dir)
                        raise RuntimeError(
                            f"Demonstration {base_demo_dir_name} has neither valid.txt nor invalid.txt. "
                            f"Run the align_validate stage first. Session directory {session_dir} has been deleted."
                        )
                    if not cfg.get('include_invalid', False) and has_invalid:
                        print(f'Skipping {base_demo_dir_name} (invalid.txt present)')
                        num_skipped += 1
                        return

                validate_demonstration_tracking_artifacts(demonstration_dir)
                num_demonstrations += 1

                # Track session name counts
                demo_session_name = None
                split = base_demo_dir_name.split('_')
                if len(split) == 4:
                    demo_session_name = split[2]
                    session_counts[demo_session_name] = session_counts.get(demo_session_name, 0) + 1
                    if demo_session_name not in session_stats:
                        session_stats[demo_session_name] = {
                            'total_episodes': 0,
                            'error_correction_episodes': 0,
                            'non_error_correction_episodes': 0,
                            'demos_by_task': {},
                            'error_correction_by_task': {},
                            'non_error_correction_by_task': {},
                        }
                    session_stats[demo_session_name]['total_episodes'] += 1

                # make sure we add the gripper calibration to the session
                for side_present in get_demonstration_sides_present(demonstration_dir):
                    json_data = get_demonstration_json_data(demonstration_dir, side_present)
                    gripper_calibration_run_name = json_data.get('gripperCalibrationRunName', '')
                    if side_present == 'head' or not gripper_calibration_run_name:
                        continue
                    gripper_calibrations_dirs.add(
                        get_demonstration_path(demonstrations_dir, gripper_calibration_run_name)
                    )

                # Count task names and error correction status from the first available side's JSON
                for side_present in get_demonstration_sides_present(demonstration_dir):
                    try:
                        json_data = get_demonstration_json_data(demonstration_dir, side_present)
                        is_error_correction = bool(json_data.get('isErrorCorrection'))
                        if is_error_correction:
                            num_error_correction_episodes += 1
                        else:
                            num_non_error_correction_episodes += 1
                        if demo_session_name:
                            s = session_stats[demo_session_name]
                            if is_error_correction:
                                s['error_correction_episodes'] += 1
                            else:
                                s['non_error_correction_episodes'] += 1
                        for task_name in json_data.get('taskNames', []):
                            task_counts[task_name] = task_counts.get(task_name, 0) + 1
                            if is_error_correction:
                                error_correction_task_counts[task_name] = error_correction_task_counts.get(task_name, 0) + 1
                            else:
                                non_error_correction_task_counts[task_name] = non_error_correction_task_counts.get(task_name, 0) + 1
                            if demo_session_name:
                                s = session_stats[demo_session_name]
                                s['demos_by_task'][task_name] = s['demos_by_task'].get(task_name, 0) + 1
                                if is_error_correction:
                                    s['error_correction_by_task'][task_name] = s['error_correction_by_task'].get(task_name, 0) + 1
                                else:
                                    s['non_error_correction_by_task'][task_name] = s['non_error_correction_by_task'].get(task_name, 0) + 1
                        break
                    except Exception:
                        continue

            elif is_gripper_calibration:
                if not include_gripper_calibrations:
                    return

                num_gripper_calibrations += 1
            else:
                raise NotImplementedError

            # Symlink the demonstration into the session
            symlink_absolute(demonstration_dir, session_demo_dir, target_is_directory=True)

            print(f'Added {base_demo_dir_name} to session')

    input_name_filtered_demonstrations = set()
    # Copy the processed demonstrations by name filter
    for filter in cfg.input_name_filters:
        for demonstration_dir in glob(demonstrations_dir + "/*/" + filter):
            input_name_filtered_demonstrations.add(demonstration_dir)

    session_name_filtered_demonstrations = set()
    # Copy the processed demonstrations by session name filter
    for filter in cfg.input_session_filters:
        for demonstration_dir in glob(demonstrations_dir + "/*/*"):
            demonstration_name = os.path.basename(demonstration_dir)
            split = demonstration_name.split('_')
            if len(split) != 4:
                continue
            demonstration_time_str, demonstration_randomizer, demonstration_session_name, recording_type = split

            if re.fullmatch(filter, demonstration_session_name):
                session_name_filtered_demonstrations.add(demonstration_dir)

    input_task_filtered_demonstrations = set()
    # Filter processed demonstrations by task name filter
    for filter in cfg.input_task_filters:
        for demonstration_dir in glob(demonstrations_dir + "/*/*"):
            demonstration_name = os.path.basename(demonstration_dir)
            split = demonstration_name.split('_')
            if len(split) != 4:
                continue
            demonstration_time_str, demonstration_randomizer, demonstration_session_name, recording_type = split

            # Try to load the demonstration JSON to get the task name
            for side_present in get_demonstration_sides_present(demonstration_dir):
                try:
                    json_data = get_demonstration_json_data(demonstration_dir, side_present)
                    task_names = json_data.get("taskNames", None)
                    # will add demonstraiton to filtered set if it contains ANY task name that is passed through input_task_name (not just exact matches)
                    if task_names and any(re.match(filter, task_name, re.IGNORECASE) for task_name in task_names):
                        input_task_filtered_demonstrations.add(demonstration_dir)
                        break  # Only need to process once per demonstration
                except Exception as e:
                    # If JSON is missing or malformed, skip this demonstration
                    continue

    # take the intersection of all non-emtpy filters
    filtered_sets = []
    if len(cfg.input_name_filters) > 0:
        filtered_sets.append(input_name_filtered_demonstrations)
    if len(cfg.input_session_filters) > 0:
        filtered_sets.append(session_name_filtered_demonstrations)
    if len(cfg.input_task_filters) > 0:
        filtered_sets.append(input_task_filtered_demonstrations)

    if filtered_sets:
        filtered_demonstration_intersection = set.intersection(*filtered_sets)
    else:
        filtered_demonstration_intersection = set()

    sides_mode = (getattr(cfg, 'sides', None) or '').strip()

    if sides_mode:
        if sides_mode not in SIDES_MODES:
            shutil.rmtree(session_dir)
            raise ValueError(f"Unknown sides mode {sides_mode!r}. Valid: {sorted(SIDES_MODES)}")
        side_filtered = set()
        for demonstration_dir in filtered_demonstration_intersection:
            demo_name = os.path.basename(demonstration_dir)
            if not demo_name.endswith('_demonstration'):
                side_filtered.add(demonstration_dir)
                continue
            demo_sides = get_demonstration_sides_present(demonstration_dir)
            strict = getattr(cfg, 'strict_side_matching', True)
            if _demo_qualifies(demo_sides, sides_mode, strict=strict):
                side_filtered.add(demonstration_dir)
        filtered_demonstration_intersection = side_filtered
        active_mode = sides_mode
    else:
        # Without a sides mode, all demos must have the same side combination.
        side_sets = {}
        for demonstration_dir in filtered_demonstration_intersection:
            demo_name = os.path.basename(demonstration_dir)
            if not demo_name.endswith('_demonstration'):
                continue
            demo_sides = sorted(get_demonstration_sides_present(demonstration_dir))
            side_sets[demonstration_dir] = demo_sides

        if side_sets:
            expected = next(iter(side_sets.values()))
            mismatched = {d: sides for d, sides in side_sets.items() if sides != expected}
            if mismatched:
                lines = '\n'.join(f'  {os.path.basename(d)}: {sides}' for d, sides in mismatched.items())
                shutil.rmtree(session_dir)
                raise ValueError(
                    f"Inconsistent sides across demonstrations. Expected {expected}, but found mismatches:\n{lines}\n"
                    f"Use sides=<mode> to filter (e.g. sides=single, sides=bimanual).\n"
                    f"Session directory {session_dir} has been deleted."
                )

        active_mode = None
        if filtered_demonstration_intersection:
            for d in filtered_demonstration_intersection:
                if os.path.basename(d).endswith('_demonstration'):
                    active_mode = infer_sides_mode(get_demonstration_sides_present(d))
                    break

    # process demonstrations that satisfy all non-empty filters
    for demonstration_dir in filtered_demonstration_intersection:
        process_demonstration_dir(demonstration_dir)

    # Copy all the associated gripper calibrations (it's possible that the gripper calibration is under a different session name or demonstration title filter that doesn't match the specified filters) so we want to manually include them
    for demonstration_dir in gripper_calibrations_dirs:
        process_demonstration_dir(demonstration_dir, include_gripper_calibrations=True)

    for stats in session_stats.values():
        stats['total_task_demos'] = sum(stats['demos_by_task'].values())

    session_info = {
        'sides': active_mode,
        'unique_tasks': len(task_counts),
        'total_task_demos': sum(task_counts.values()),
        'total_episodes': num_demonstrations,
        'error_correction_episodes': num_error_correction_episodes,
        'non_error_correction_episodes': num_non_error_correction_episodes,
        'demos_by_task': task_counts,
        'error_correction_by_task': error_correction_task_counts,
        'non_error_correction_by_task': non_error_correction_task_counts,
        'demos_by_session': session_counts,
        'stats_by_session': session_stats,
    }
    with open(os.path.join(session_dir, 'session_info.json'), 'w') as f:
        json.dump(session_info, f, indent=2)

    print(f'Finished creating session at {os.path.abspath(session_dir)} with {num_demonstrations} demonstrations ({num_skipped} skipped) and {num_gripper_calibrations} gripper calibrations')

if __name__ == '__main__':
    main()
