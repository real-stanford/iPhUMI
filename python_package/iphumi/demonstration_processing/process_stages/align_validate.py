import os
import numpy as np
from omegaconf import DictConfig

from iphumi.demonstration_processing.utils.generic_util import (
    demonstration_to_display_string,
    get_demonstration_sides_present,
    read_aligned_csv,
)
from iphumi.demonstration_processing.utils.color_util import red

INVALID_FILENAME = "invalid.txt"
VALID_FILENAME = "valid.txt"

_CONDITION_OPS = {
    '>=': lambda a, b: a >= b,
    '<=': lambda a, b: a <= b,
    '>':  lambda a, b: a > b,
    '<':  lambda a, b: a < b,
    '==': lambda a, b: a == b,
    '!=': lambda a, b: a != b,
}

def _check_conditions(value, conditions, label, failure_reasons):
    """Evaluate one or more condition strings against value and append failures."""
    if conditions is None:
        return
    if isinstance(conditions, str):
        conditions = [conditions]
    for cond in conditions:
        cond = cond.strip()
        for op_str, op_fn in sorted(_CONDITION_OPS.items(), key=lambda x: -len(x[0])):
            if cond.startswith(op_str):
                threshold = float(cond[len(op_str):].strip())
                if not op_fn(value, threshold):
                    failure_reasons.append(f"{label} {value:.4f}m failed condition {cond}m")
                break
        else:
            raise ValueError(f"Cannot parse condition string: '{cond}'")


def align_validate_iphone_data(demonstration_iterator, cfg: DictConfig):
    max_gripper_to_gripper = cfg.get("max_initial_gripper_to_gripper_distance", None)
    max_gripper_to_gripper_x = cfg.get("max_initial_gripper_to_gripper_x_distance", None)
    max_gripper_to_gripper_y = cfg.get("max_initial_gripper_to_gripper_y_distance", None)
    max_gripper_to_gripper_z = cfg.get("max_initial_gripper_to_gripper_z_distance", None)
    max_gripper_angle_apart = cfg.get("max_initial_gripper_angle_apart", None)
    max_gripper_to_head = cfg.get("max_initial_gripper_to_head_distance", None)
    enable_gripper_to_gripper_check = cfg.get("enable_initial_gripper_to_gripper_distance_check", True)
    detect_flipped_grippers = cfg.get("detect_flipped_grippers", True)
    max_pose_delta_m_per_s = cfg.get("max_pose_delta_m_per_s", None)
    fps = float(cfg.get("fps", 60))
    max_pose_delta = max_pose_delta_m_per_s / fps if max_pose_delta_m_per_s is not None else None
    print_stats = cfg.get("print_stats", False)
    clear_invalid = cfg.get("clear_invalid", False)
    overwrite = cfg.get("overwrite", False)
    traj_conditions = {
        ("left",  "right"): (cfg.get("left_right_min_distance", None), cfg.get("left_right_max_distance", None)),
        ("left",  "head"):  (cfg.get("left_head_min_distance",  None), cfg.get("left_head_max_distance",  None)),
        ("right", "head"):  (cfg.get("right_head_min_distance", None), cfg.get("right_head_max_distance", None)),
    }

    if clear_invalid:
        num_cleared = 0
        for demonstration_dir in demonstration_iterator("demonstration"):
            for filename in (INVALID_FILENAME, VALID_FILENAME):
                path = os.path.join(demonstration_dir, filename)
                if os.path.exists(path):
                    os.remove(path)
                    num_cleared += 1
        print(f"Cleared {num_cleared} validation file(s).")
        return

    num_passed = 0
    num_failed = 0
    num_skipped = 0

    for demonstration_dir in demonstration_iterator("demonstration"):
        demo_str = demonstration_to_display_string(demonstration_dir)

        invalid_path = os.path.join(demonstration_dir, INVALID_FILENAME)
        valid_path = os.path.join(demonstration_dir, VALID_FILENAME)
        already_validated = os.path.exists(invalid_path) or os.path.exists(valid_path)
        if already_validated and not overwrite:
            num_skipped += 1
            continue

        sides = get_demonstration_sides_present(demonstration_dir)
        aligned_sides = [s for s in sides if os.path.exists(os.path.join(demonstration_dir, f"{s}_aligned.csv"))]
        if not aligned_sides:
            continue

        all_poses = {}
        for side in aligned_sides:
            all_poses[side] = read_aligned_csv(demonstration_dir, side)["poses"]

        initial_poses = {side: poses[0] for side, poses in all_poses.items()}
        initial_positions = {side: pose[:3, 3] for side, pose in initial_poses.items()}

        failure_reasons = []
        stat_lines = []

        def _fmt(val, max_val, unit):
            thresh = f"{max_val}{unit}" if max_val is not None else "none"
            return f"{val:.4f}{unit} [max: {thresh}]"

        # Check gripper-to-gripper distances
        if "left" in initial_positions and "right" in initial_positions:
            R_left = initial_poses["left"][:3, :3]
            R_right = initial_poses["right"][:3, :3]
            offset_world = initial_positions["right"] - initial_positions["left"]
            offset_left_frame = R_left.T @ offset_world

            if enable_gripper_to_gripper_check:
                dist = float(np.linalg.norm(offset_world))
                R_rel = R_left.T @ R_right
                angle_deg = float(np.degrees(np.arccos(np.clip((np.trace(R_rel) - 1) / 2, -1, 1))))

                if print_stats:
                    flipped_str = f"  flipped-check x={offset_left_frame[0]:.4f}m ({'FAIL' if detect_flipped_grippers and offset_left_frame[0] < 0 else 'ok'})"
                    stat_lines.append(
                        f"initial left-right distance: {_fmt(dist, max_gripper_to_gripper, 'm')}"
                        f"  offset in left ARKit frame"
                        f" (x={_fmt(offset_left_frame[0], max_gripper_to_gripper_x, 'm')},"
                        f" y={_fmt(offset_left_frame[1], max_gripper_to_gripper_y, 'm')},"
                        f" z={_fmt(offset_left_frame[2], max_gripper_to_gripper_z, 'm')})"
                        f"  angle apart: {_fmt(angle_deg, max_gripper_angle_apart, 'deg')}"
                        + flipped_str
                    )

                if max_gripper_to_gripper is not None and dist > max_gripper_to_gripper:
                    failure_reasons.append(f"left-right distance {dist:.4f}m exceeds max {max_gripper_to_gripper}m")

                for axis, idx, max_val in (
                    ("x", 0, max_gripper_to_gripper_x),
                    ("y", 1, max_gripper_to_gripper_y),
                    ("z", 2, max_gripper_to_gripper_z),
                ):
                    if max_val is not None and abs(offset_left_frame[idx]) > max_val:
                        failure_reasons.append(
                            f"left-right offset {axis} in left ARKit frame {offset_left_frame[idx]:.4f}m"
                            f" (abs) exceeds max {max_val}m"
                        )

                if max_gripper_angle_apart is not None and angle_deg > max_gripper_angle_apart:
                    failure_reasons.append(f"left-right angle apart {angle_deg:.2f}deg exceeds max {max_gripper_angle_apart}deg")

            if detect_flipped_grippers and offset_left_frame[0] < 0:
                failure_reasons.append(
                    f"right gripper is to the left of left gripper in left ARKit frame"
                    f" (x={offset_left_frame[0]:.4f}m) — grippers likely held flipped"
                )

        # Check gripper-to-head distance
        if "head" in initial_positions:
            for side in ("left", "right"):
                if side not in initial_positions:
                    continue
                dist = float(np.linalg.norm(initial_positions[side] - initial_positions["head"]))
                if print_stats:
                    thresh = f"{max_gripper_to_head}m" if max_gripper_to_head is not None else "none"
                    stat_lines.append(f"initial {side}-head distance: {dist:.4f}m [max: {thresh}]")
                if max_gripper_to_head is not None and dist > max_gripper_to_head:
                    failure_reasons.append(f"{side}-head distance {dist:.4f}m exceeds max {max_gripper_to_head}m")

        # Check trajectory-wide ARKit distance conditions (min/max over all frames)
        min_traj_len = min(p.shape[0] for p in all_poses.values())
        for (side_a, side_b), (min_cond, max_cond) in traj_conditions.items():
            if min_cond is None and max_cond is None:
                continue
            if side_a not in all_poses or side_b not in all_poses:
                continue
            dists = np.linalg.norm(
                all_poses[side_a][:min_traj_len, :3, 3] - all_poses[side_b][:min_traj_len, :3, 3],
                axis=1,
            )
            _check_conditions(float(dists.min()), min_cond, f"{side_a}-{side_b} trajectory min distance", failure_reasons)
            _check_conditions(float(dists.max()), max_cond, f"{side_a}-{side_b} trajectory max distance", failure_reasons)

        # Check per-step pose delta per side
        for side, poses in all_poses.items():
            if len(poses) < 2:
                continue
            deltas = np.linalg.norm(np.diff(poses[:, :3, 3], axis=0), axis=1)
            if print_stats:
                thresh = f"{max_pose_delta_m_per_s}m/s" if max_pose_delta_m_per_s is not None else "none"
                deltas_m_per_s = deltas * fps
                stat_lines.append(
                    f"{side} pose deltas:"
                    f" min={deltas_m_per_s.min():.4f}m/s"
                    f" median={np.median(deltas_m_per_s):.4f}m/s"
                    f" max={deltas_m_per_s.max():.4f}m/s [max: {thresh}]"
                )
            if max_pose_delta is not None and deltas.max() > max_pose_delta:
                failure_reasons.append(
                    f"{side} max pose delta {float(deltas.max()) * fps:.4f}m/s exceeds max {max_pose_delta_m_per_s}m/s"
                )

        if print_stats and stat_lines:
            stats_str = "\n".join(f"  - {s}" for s in stat_lines)
            print(f"{demo_str} stats:\n{stats_str}")

        if failure_reasons:
            num_failed += 1
            reasons_str = "\n".join(f"  - {r}" for r in failure_reasons)
            print(f"{red('FAILURE')} {demo_str}:\n{reasons_str}")
            with open(invalid_path, "w") as f:
                f.write("\n".join(failure_reasons) + "\n")
            if os.path.exists(valid_path):
                os.remove(valid_path)
        else:
            num_passed += 1
            open(valid_path, "w").close()
            if os.path.exists(invalid_path):
                os.remove(invalid_path)

    print(f"\nAlign validation complete: {num_passed} passed, {num_failed} failed, {num_skipped} skipped.")
