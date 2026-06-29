from omegaconf import DictConfig
import os
from glob import glob
import shutil
import yaml

from iphumi.common.generic_util import symlink_absolute
from iphumi.demonstration_processing.utils.color_util import red
from iphumi.demonstration_processing.utils.generic_util import (
    keep_demonstration,
    get_demonstration_path,
    build_demonstration_iphone_calibration,
)

def group_iphone_data(cfg: DictConfig):
    """Given data from iPhone (potentially paired left right data or just one side), group them together into folders by demonstration."""
    new_demonstrations = set()
    existing_demonstrations = set()
    demonstration_title_to_type = {}
    num_processed = 0

    # Load demonstrations from iPhone
    assert os.path.exists(cfg.iphone_dir), f'Did not find iphone directory: {cfg.iphone_dir}'
    demonstration_files = list(glob(os.path.join(cfg.iphone_dir, "**/*.json"), recursive=True))
    demonstration_files.sort()

    # Load global iPhone calibration (if provided) so we can persist per-demonstration copies
    calib_path = os.path.abspath(cfg.gripper_calibration)
    with open(calib_path, "r") as f:
        calibration_dict = yaml.safe_load(f)

    for demonstration_json_path in demonstration_files:
        demonstration_name = os.path.basename(demonstration_json_path).replace('.json', '')

        # get demonstration properties
        split = demonstration_name.split('_')
        if len(split) == 5:
            demonstration_time_str, demonstration_randomizer, demonstration_session_name, recording_type, side = split
            demonstration_title = f'{demonstration_time_str}_{demonstration_randomizer}_{demonstration_session_name}_{recording_type}'
        else:
            print(red(f"Skipping demonstration with unknown or old name format: {demonstration_name}"))
            continue

        # skip this demonstration under certain conditions
        if not keep_demonstration(demonstration_title, demonstration_json_path, cfg.filters):
            continue

        demonstration_title_to_type[demonstration_title] = recording_type

        if num_processed == cfg.filters.max_demos:
            break
        num_processed += 1

        demonstration_in_dir = os.path.dirname(demonstration_json_path)
        demonstration_out_dir = get_demonstration_path(cfg.demonstrations_dir, demonstration_title)

        if os.path.exists(demonstration_out_dir) and cfg.overwrite and demonstration_title not in new_demonstrations:
            shutil.rmtree(demonstration_out_dir)

        if not os.path.exists(demonstration_out_dir):
            new_demonstrations.add(demonstration_title)
            os.makedirs(demonstration_out_dir)
        elif demonstration_title not in new_demonstrations:
            existing_demonstrations.add(demonstration_title)
            continue

        # copy all the corresponding files to the output directory
        demonstration_in_files = glob(f'{demonstration_in_dir}/{demonstration_title}*')
        for in_file in demonstration_in_files:
            out_name = os.path.basename(in_file).replace(f'{demonstration_title}_', '') # looks like `right_depth.mp4` for example
            out_path = os.path.join(demonstration_out_dir, out_name)

            if cfg.symlink:
                symlink_absolute(in_file, out_path)
            else:
                shutil.copyfile(in_file, out_path)

        # After grouping files, persist calibration for this side into the demonstration directory
        try:
            calib = build_demonstration_iphone_calibration(demonstration_out_dir, side, calibration_dict)
            side_calib_path = os.path.join(demonstration_out_dir, f"{side}_calibration.yaml")
            with open(side_calib_path, "w") as f:
                yaml.safe_dump(calib, f)
        except Exception as e:
            raise RuntimeError(
                f"Failed during grouping of demonstration: {demonstration_out_dir} "
                f"(side={side}, source={demonstration_in_dir})"
            ) from e

        print(f'Processed: {demonstration_name}')

    def count_demonstrations_of_type(demonstrations_set, type):
        count = 0
        for demonstration in demonstrations_set:
            if type == demonstration_title_to_type[demonstration]:
                count += 1
        return count

    print(f'\nNew: {count_demonstrations_of_type(new_demonstrations, "demonstration")} demonstrations and {count_demonstrations_of_type(new_demonstrations, "grippercalibration")} gripper calibrations to {cfg.demonstrations_dir}')
    print(f'Previously processed: {count_demonstrations_of_type(existing_demonstrations, "demonstration")} demonstrations and {count_demonstrations_of_type(existing_demonstrations, "grippercalibration")} gripper calibrations')
