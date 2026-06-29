import os
import json
import shutil
from omegaconf import DictConfig
from iphumi.demonstration_processing.utils.generic_util import (
    demonstration_to_display_string,
    get_demonstration_sides_present,
    get_demonstration_type,
)


def validate_iphone_data(demonstration_iterator_fn, cfg: DictConfig):
    """Check that every grouped demo has all sides listed in sidesPresent.

    Demos with a missing side are deleted so that all downstream stages skip
    them.  Demos without a sidesPresent field (recorded before this feature
    was added) are left untouched.
    """
    counts = {
        'demo_valid': 0,
        'demo_invalid': 0,
        'demo_no_sides_present': 0,
        'demo_no_side_data': 0,
        'calibration_valid': 0,
        'calibration_invalid': 0,
        'other_skipped': 0,
    }

    for demonstration_dir in demonstration_iterator_fn():
        try:
            demo_type = get_demonstration_type(demonstration_dir)

            if demo_type == 'grippercalibration':
                # Calibrations are self-contained per side — no sidesPresent completeness check needed
                sides_present = get_demonstration_sides_present(demonstration_dir)
                if not sides_present:
                    reason = 'no side data found after grouping'
                    print(f'{demonstration_to_display_string(demonstration_dir)} Invalid: {reason}')
                    shutil.rmtree(demonstration_dir)
                    counts['calibration_invalid'] += 1
                else:
                    counts['calibration_valid'] += 1
                continue

            if demo_type != 'demonstration':
                counts['other_skipped'] += 1
                continue

            sides_present = get_demonstration_sides_present(demonstration_dir)

            if not sides_present:
                reason = 'no side data found after grouping'
                print(f'{demonstration_to_display_string(demonstration_dir)} Invalid: {reason}')
                shutil.rmtree(demonstration_dir)
                counts['demo_invalid'] += 1
                continue

            # Read sidesPresent from any available side JSON
            expected_sides = None
            for side in sides_present:
                json_path = os.path.join(demonstration_dir, f'{side}.json')
                if not os.path.exists(json_path):
                    continue
                with open(json_path) as f:
                    data = json.load(f)
                sp = data.get('sidesPresent')
                if sp:
                    expected_sides = sp
                    break

            if expected_sides is None:
                # Recorded before sidesPresent was added — skip completeness check
                counts['demo_no_sides_present'] += 1
                continue

            missing = [s for s in expected_sides if s not in sides_present]
            if missing:
                reason = f'missing sides: {", ".join(sorted(missing))}'
                print(f'{demonstration_to_display_string(demonstration_dir)} Invalid: {reason}')
                shutil.rmtree(demonstration_dir)
                counts['demo_invalid'] += 1
            else:
                counts['demo_valid'] += 1
        except Exception as e:
            raise RuntimeError(f"Failed during validation of demonstration: {demonstration_dir}") from e

    print(f'\nValidation complete:')
    print(f'  Demonstrations:  {counts["demo_valid"]} valid, {counts["demo_invalid"]} invalid'
          + (f', {counts["demo_no_sides_present"]} skipped (no sidesPresent field, recorded before feature was added)' if counts['demo_no_sides_present'] else '')
          + (f', {counts["demo_no_side_data"]} skipped (no side data)' if counts['demo_no_side_data'] else ''))
    print(f'  Calibrations:    {counts["calibration_valid"]} valid, {counts["calibration_invalid"]} invalid')
    if counts['other_skipped']:
        print(f'  Other:           {counts["other_skipped"]} skipped')
