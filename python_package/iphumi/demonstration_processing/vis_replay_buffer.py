"""
Visualize the trajectory from the replay buffer for UMI.

This script loads a UMI replay buffer and creates a visualization video showing:
- Main camera video with trajectory overlay
- Ultrawide camera video
- Combined output similar to the original visualization pipeline
"""

import os
import argparse
import tempfile
import shutil
from pathlib import Path

import numpy as np
import cv2
import imageio.v3 as iio
import zarr
import scipy.spatial.transform as st
from tqdm import tqdm

from iphumi.common.replay_buffer import ReplayBuffer
from iphumi.common.transform_util import pose_6d_to_4x4
from iphumi.common.trajectory_util import vis_trajectories
from iphumi.common.imagecodecs_numcodecs import register_codecs
register_codecs()

PREFERRED_SIDES = ("head", "left", "right")


def _resize_to_width(frame: np.ndarray, cell_w: int) -> np.ndarray:
    """Resize frame to cell_w preserving aspect ratio."""
    h, w = frame.shape[:2]
    new_h = int(round(h * cell_w / w))
    return cv2.resize(frame, (cell_w, new_h))


def _side_priority(side: str):
    if side in PREFERRED_SIDES:
        return (PREFERRED_SIDES.index(side), side)
    return (len(PREFERRED_SIDES), side)


def _key(prefix: str, suffix: str) -> str:
    return f"{prefix}_{suffix}"


def _select_gripper_prefix(data) -> str:
    data_keys = set(data.keys())
    prefixes = []
    for key in data_keys:
        if key.startswith("gripper_") and key.endswith("_eef_pos"):
            prefix = key[: -len("_eef_pos")]
            side = prefix.split("_", 1)[1]
            if _key(prefix, "eef_rot_axis_angle") in data_keys:
                prefixes.append((side, prefix))

    if prefixes:
        prefixes.sort(key=lambda item: _side_priority(item[0]))
        return prefixes[0][1]

    if "robot0_eef_pos" in data_keys and "robot0_eef_rot_axis_angle" in data_keys:
        return "robot0"

    raise KeyError("Could not find a gripper pose stream in the replay buffer episode.")



def _select_all_camera_prefixes(data) -> list:
    data_keys = set(data.keys())
    prefixes = []
    for key in data_keys:
        if key.startswith("camera_") and key.endswith("_main_rgb"):
            prefix = key[: -len("_main_rgb")]
            side = prefix.split("_", 1)[1]
            prefixes.append((side, prefix))
    prefixes.sort(key=lambda item: _side_priority(item[0]))
    return [prefix for _, prefix in prefixes] or (["camera0"] if "camera0_main_rgb" in data_keys else [])


def _select_all_gripper_prefixes(data) -> list:
    data_keys = set(data.keys())
    prefixes = []
    for key in data_keys:
        if key.startswith("gripper_") and key.endswith("_eef_pos"):
            prefix = key[: -len("_eef_pos")]
            side = prefix.split("_", 1)[1]
            if _key(prefix, "eef_rot_axis_angle") in data_keys:
                prefixes.append((side, prefix))
    prefixes.sort(key=lambda item: _side_priority(item[0]))
    return [prefix for _, prefix in prefixes]


def _select_depth_key(data, camera_prefix: str):
    preferred_keys = (_key(camera_prefix, "depth"), _key(camera_prefix, "main_depth"))
    for preferred_key in preferred_keys:
        if preferred_key in data:
            return preferred_key

    depth_candidates = sorted(
        key for key in data.keys() if key.endswith("_depth") or key.endswith("_main_depth")
    )
    if depth_candidates:
        return depth_candidates[0]
    return None


def _episode_start_idx(replay_buffer, episode_idx: int) -> int:
    if episode_idx <= 0:
        return 0
    return int(replay_buffer.episode_ends[episode_idx - 1])


def _upsampled_episode_start_idx(replay_buffer, key: str, episode_idx: int) -> int:
    episode_ends_key = f"episode_ends_{key}"
    if episode_idx <= 0 or episode_ends_key not in replay_buffer.meta:
        return 0
    return int(replay_buffer.meta[episode_ends_key][episode_idx - 1])


def load_replay_buffer(path, keep_on_disk=False):
    """Load replay buffer from path."""
    if keep_on_disk:
        replay_buffer = ReplayBuffer.create_from_path(path)
    else:
        replay_buffer = ReplayBuffer.copy_from_path(path, store=zarr.MemoryStore())
    return replay_buffer


def extract_poses(replay_buffer, episode_idx=0):
    """Extract and convert poses from replay buffer."""
    episode_data = replay_buffer.get_episode(episode_idx)
    gripper_prefix = _select_gripper_prefix(episode_data["data"])
    eef_pos = episode_data["data"][_key(gripper_prefix, "eef_pos")]
    eef_rot = episode_data["data"][_key(gripper_prefix, "eef_rot_axis_angle")]

    if eef_pos.shape[0] != eef_rot.shape[0]:
        raise ValueError(f"Mismatch in pose dimensions: pos={eef_pos.shape[0]}, rot={eef_rot.shape[0]}")

    if eef_pos.shape[0] == 0:
        raise ValueError(f"Episode {episode_idx} is empty (no poses)")

    poses_6d = np.concatenate([eef_pos, eef_rot], axis=-1)
    poses_4x4 = pose_6d_to_4x4(poses_6d)
    return poses_4x4, episode_data


def extract_all_poses(replay_buffer, episode_idx=0):
    """Extract poses for all gripper sides present in the episode."""
    episode_data = replay_buffer.get_episode(episode_idx)
    gripper_prefixes = _select_all_gripper_prefixes(episode_data["data"])
    if not gripper_prefixes:
        raise KeyError(f"No gripper pose streams found in episode {episode_idx}")
    all_poses = []
    for gp in gripper_prefixes:
        eef_pos = episode_data["data"][_key(gp, "eef_pos")]
        eef_rot = episode_data["data"][_key(gp, "eef_rot_axis_angle")]
        if eef_pos.shape[0] == 0:
            raise ValueError(f"Episode {episode_idx} is empty (no poses for {gp})")
        poses_6d = np.concatenate([eef_pos, eef_rot], axis=-1)
        all_poses.append(pose_6d_to_4x4(poses_6d))
    return all_poses, episode_data


def log_rotation_table(replay_buffer, episode_idx=0, max_rows=100):
    """Log rotation table with rotations relative to the first rotation in Euler angles (x, y, z).
    
    Args:
        replay_buffer: Replay buffer instance
        episode_idx: Episode index to process
        max_rows: Maximum number of rows to print (default 100)
    """
    episode_data = replay_buffer.get_episode(episode_idx)
    gripper_prefix = _select_gripper_prefix(episode_data["data"])
    eef_rot = episode_data["data"][_key(gripper_prefix, "eef_rot_axis_angle")]
    N = eef_rot.shape[0]
    
    if N == 0:
        raise ValueError(f"Episode {episode_idx} is empty (no rotations)")
    
    # Convert axis-angle to rotation objects
    rotations = st.Rotation.from_rotvec(eef_rot)
    
    # Get first rotation as reference
    first_rotation = rotations[0]
    
    # Compute relative rotations (first_rotation^-1 * current_rotation)
    relative_rotations = first_rotation.inv() * rotations
    
    # Convert to Euler angles (x, y, z) - using 'xyz' extrinsic convention
    euler_angles = relative_rotations.as_euler('xyz', degrees=True)  # (N, 3)
    
    # Limit number of rows to print
    num_rows = min(N, max_rows)
    step = max(1, N // num_rows) if num_rows < N else 1
    
    # Print table header
    print("\n" + "=" * 80)
    print(f"Rotation Table (Episode {episode_idx}) - Relative to First Rotation")
    print("=" * 80)
    print(f"{'Index':<8} {'X (deg)':<12} {'Y (deg)':<12} {'Z (deg)':<12}")
    print("-" * 80)
    
    # Print rows
    for i in range(0, N, step):
        x, y, z = euler_angles[i]
        print(f"{i:<8} {x:>11.2f} {y:>11.2f} {z:>11.2f}")
    
    # Print last row if not already printed
    if (N - 1) % step != 0:
        x, y, z = euler_angles[-1]
        print(f"{N-1:<8} {x:>11.2f} {y:>11.2f} {z:>11.2f}")
    
    print("=" * 80)
    print(f"Total rotations: {N}")
    if num_rows < N:
        print(f"Showing {num_rows} rows (sampled every {step} steps)")
    print()


def save_main_camera_video(replay_buffer, episode_data, output_path, camera_prefix, fps=60, max_frames=-1):
    """Save main camera frames to temporary video file."""
    main_key = _key(camera_prefix, "main_rgb")
    main_rgb = episode_data["data"][main_key]
    N = main_rgb.shape[0]
    
    if N == 0:
        raise ValueError("No main camera frames in episode")
    
    # Limit frames if max_frames is specified
    if max_frames > 0 and max_frames < N:
        N = max_frames
    
    with iio.imopen(output_path, "w", plugin="pyav") as out:
        out.init_video_stream("libx264", fps=fps)
        for i in tqdm(range(N), desc='Writing main camera video'):
            out.write(main_rgb[i], is_batch=False)
    
    return output_path


def create_trajectory_video(all_poses_list, output_path, max_frames=-1, fps=60):
    """Create trajectory video showing all gripper sides in a single plot."""
    T = all_poses_list[0].shape[0]
    is_lost = np.zeros(T, dtype=bool)

    if max_frames > 0 and max_frames < T:
        all_poses_list = [p[:max_frames] for p in all_poses_list]
        is_lost = is_lost[:max_frames]

    vis_trajectories(
        video_out_path=output_path,
        poses=all_poses_list,
        is_lost=is_lost,
        out_width=360,
        out_height=360,
        offscreen=True,
        fps=fps,
        include_base_frame=False
    )
    
    return output_path


def save_ultrawide_video(replay_buffer, episode_data, output_path, camera_prefix, episode_idx=0, fps=60, max_frames=-1):
    """Save ultrawide camera frames to a temporary video file."""
    main_key = _key(camera_prefix, "main_rgb")
    ultrawide_key = _key(camera_prefix, "ultrawide_rgb")
    ultrawide_rgb = episode_data["data"][ultrawide_key]
    M = ultrawide_rgb.shape[0]

    if M == 0:
        raise ValueError("No ultrawide camera frames in episode")

    with iio.imopen(output_path, "w", plugin="pyav") as out:
        out.init_video_stream("libx264", fps=fps)
        if replay_buffer.is_key_upsampled(ultrawide_key):
            main_length = episode_data["data"][main_key].shape[0]
            if max_frames > 0 and max_frames < main_length:
                main_length = max_frames

            episode_start_idx = _episode_start_idx(replay_buffer, episode_idx)
            ultrawide_episode_start_idx = _upsampled_episode_start_idx(
                replay_buffer, ultrawide_key, episode_idx
            )
            blank_frame = np.zeros_like(ultrawide_rgb[0])
            for frame_i in tqdm(range(main_length), desc='Writing ultrawide video'):
                global_main_idx = episode_start_idx + frame_i
                ultrawide_global_idx = replay_buffer.map_upsample_index(ultrawide_key, global_main_idx)
                ultrawide_local_idx = ultrawide_global_idx - ultrawide_episode_start_idx
                frame = ultrawide_rgb[ultrawide_local_idx] if 0 <= ultrawide_local_idx < M else blank_frame
                out.write(frame, is_batch=False)
        else:
            if max_frames > 0 and max_frames < M:
                M = max_frames
            for frame_i in tqdm(range(M), desc='Writing ultrawide video'):
                out.write(ultrawide_rgb[frame_i], is_batch=False)

    return output_path


def _depth_frame_to_color(depth_frame: np.ndarray, max_distance: float) -> np.ndarray:
    """
    Convert a single depth frame (H, W) to an RGB visualization (H, W, 3).
    """
    depth_frame = depth_frame.astype(np.float32)
    if max_distance <= 0.0 or not np.isfinite(max_distance):
        gray = np.zeros_like(depth_frame, dtype=np.uint8)
    else:
        depth_clipped = np.clip(depth_frame, 0.0, max_distance)
        gray = (depth_clipped / max_distance * 255.0).astype(np.uint8)

    color_bgr = cv2.applyColorMap(gray, cv2.COLORMAP_RAINBOW)
    color_rgb = color_bgr[..., ::-1]
    return color_rgb


def save_depth_video(replay_buffer, episode_data, output_path, depth_key: str, fps=60, max_frames=-1, max_distance=None):
    """Save depth frames to a temporary color-mapped video file.

    Args:
        max_distance: clip distance in metres. None or <=0 → auto (full range).
    """
    if depth_key not in episode_data['data']:
        raise KeyError(f"Missing {depth_key} in episode data")

    depth = episode_data['data'][depth_key]
    if depth.ndim == 4 and depth.shape[-1] == 1:
        depth = depth[..., 0]

    if depth.ndim != 3:
        raise ValueError(f"Expected depth shape (N,H,W) or (N,H,W,1); got {depth.shape}")

    N = depth.shape[0]
    if N == 0:
        raise ValueError("No depth frames in episode")

    if max_frames > 0 and max_frames < N:
        depth = depth[:max_frames]
        N = depth.shape[0]

    if max_distance is None or max_distance <= 0:
        max_distance = float(np.max(depth)) if depth.size > 0 else 0.0

    with iio.imopen(output_path, "w", plugin="pyav") as out:
        out.init_video_stream("libx264", fps=fps)
        for i in tqdm(range(N), desc=f'Writing depth video ({depth_key})'):
            out.write(_depth_frame_to_color(depth[i], max_distance=max_distance), is_batch=False)

    return output_path



def save_gripper_width_video(episode_data, output_path, gripper_prefixes, fps=60, max_frames=-1):
    """Save a progressive gripper-width plot as a video (draws up to current frame each step).

    Returns the output path, or None if no gripper_width data was found.
    """
    from iphumi.common.plot_util import plot_multi_gripper_width

    sides_gripper_data = []
    for gp in gripper_prefixes:
        side = gp.split("_", 1)[1]
        width_key = f"{gp}_gripper_width"
        if width_key in episode_data["data"]:
            w = np.asarray(episode_data["data"][width_key]).flatten().astype(np.float32)
            if max_frames > 0:
                w = w[:max_frames]
            sides_gripper_data.append((side, w, None))

    if not sides_gripper_data:
        return None

    n_frames = max(len(w) for _, w, _ in sides_gripper_data)

    with iio.imopen(output_path, "w", plugin="pyav") as out:
        out.init_video_stream("libx264", fps=fps)
        for i in tqdm(range(n_frames), desc='Writing gripper width video'):
            frame = plot_multi_gripper_width(sides_gripper_data, i + 1, out_width=512, out_height=512)
            out.write(frame, is_batch=False)

    return output_path


def process_episode(replay_buffer, episode_idx, temp_dir, max_frames=-1, depth_max_distance=0.5):
    """Process a single episode and return paths to intermediate videos.

    Returns:
        camera_video_paths: list of (main_path, ultrawide_path) per side in priority order
        trajectory_video_path: str
        gripper_width_video_path: str or None
        depth_video_path_pairs: list of (full_range_path, clipped_path) per side, or None if no depth
    """
    print(f"\nProcessing episode {episode_idx}...")

    try:
        all_poses, episode_data = extract_all_poses(replay_buffer, episode_idx=episode_idx)
        print(f"  Extracted poses for {len(all_poses)} gripper(s), {all_poses[0].shape[0]} frames each")
    except KeyError as e:
        raise KeyError(f"Missing required data in episode {episode_idx}: {e}")
    except Exception as e:
        raise RuntimeError(f"Error extracting poses for episode {episode_idx}: {e}")

    camera_prefixes = _select_all_camera_prefixes(episode_data["data"])
    gripper_prefixes = _select_all_gripper_prefixes(episode_data["data"])

    trajectory_video_path = os.path.join(temp_dir, f'trajectory_ep{episode_idx}.mp4')
    print(f"  Creating trajectory video ({len(all_poses)} gripper(s))...")
    create_trajectory_video(all_poses, trajectory_video_path, max_frames=max_frames, fps=60)

    camera_video_paths = []
    for camera_prefix in camera_prefixes:
        side = camera_prefix.split("_", 1)[1]
        main_video_path = os.path.join(temp_dir, f'main_{side}_ep{episode_idx}.mp4')
        ultrawide_video_path = os.path.join(temp_dir, f'ultrawide_{side}_ep{episode_idx}.mp4')

        print(f"  Saving {side} main camera video...")
        save_main_camera_video(replay_buffer, episode_data, main_video_path, camera_prefix=camera_prefix, fps=60, max_frames=max_frames)

        print(f"  Saving {side} ultrawide video...")
        save_ultrawide_video(replay_buffer, episode_data, ultrawide_video_path, camera_prefix=camera_prefix, episode_idx=episode_idx, fps=60, max_frames=max_frames)

        camera_video_paths.append((main_video_path, ultrawide_video_path))

    print(f"  Creating gripper width video...")
    gw_path = os.path.join(temp_dir, f'gripper_width_ep{episode_idx}.mp4')
    gripper_width_video_path = save_gripper_width_video(
        episode_data, gw_path, gripper_prefixes, fps=60, max_frames=max_frames
    )
    if gripper_width_video_path is None:
        print("  No gripper width data found; bottom-right cell will be blank.")

    # Depth videos: two per side — full range (global max) and clipped to depth_max_distance
    depth_video_path_pairs = []
    for camera_prefix in camera_prefixes:
        side = camera_prefix.split("_", 1)[1]
        depth_key = _select_depth_key(episode_data["data"], camera_prefix)
        if depth_key is not None:
            full_arr = replay_buffer[depth_key]
            global_max = float(np.max(full_arr)) if full_arr.size > 0 else 0.0

            full_path = os.path.join(temp_dir, f'depth_full_{side}_ep{episode_idx}.mp4')
            clipped_path = os.path.join(temp_dir, f'depth_clipped_{side}_ep{episode_idx}.mp4')
            print(f"  Saving {side} depth video (full range, max={global_max:.2f}m)...")
            save_depth_video(replay_buffer, episode_data, full_path, depth_key, fps=60, max_frames=max_frames, max_distance=global_max)
            print(f"  Saving {side} depth video (clipped to {depth_max_distance}m)...")
            save_depth_video(replay_buffer, episode_data, clipped_path, depth_key, fps=60, max_frames=max_frames, max_distance=depth_max_distance)
            depth_video_path_pairs.append((full_path, clipped_path))
        else:
            depth_video_path_pairs.append((None, None))

    has_depth = any(full is not None for full, _ in depth_video_path_pairs)
    if not has_depth:
        depth_video_path_pairs = None

    return camera_video_paths, trajectory_video_path, gripper_width_video_path, depth_video_path_pairs


def combine_multiple_episodes(episode_video_paths, output_path, replay_buffer, episode_indices):
    """Combine videos from multiple episodes into a single output video.

    Layout (one column per camera side, plus a trajectory/gripper-width column):
        [ side1_main         | side2_main         | ... | trajectory        ]
        [ side1_uw           | side2_uw           | ... | gripper_width_plot ]
        [ side1_depth_full   | side2_depth_full   | ... | blank             ]  (if depth present)
        [ side1_depth_clipped| side2_depth_clipped| ... | blank             ]  (if depth present)

    All cells are resized to cell_w × cell_h (512 × 512).

    Args:
        episode_video_paths: list of (camera_video_paths, trajectory_path, gripper_width_path, depth_video_path_pairs)
            camera_video_paths: [(main_path, ultrawide_path), ...] one per camera side
            depth_video_path_pairs: [(full_path, clipped_path), ...] per side, or None if no depth
        output_path: output video path
        replay_buffer: replay buffer instance
        episode_indices: list of episode indices that were processed
    """
    first_camera_paths, first_traj_path, _, first_depth_pairs = episode_video_paths[0]

    cell_w = cell_h = 512

    cap = cv2.VideoCapture(first_camera_paths[0][0])
    main_fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()

    blank = np.zeros((cell_h, cell_w, 3), dtype=np.uint8)
    has_depth = first_depth_pairs is not None

    with iio.imopen(output_path, "w", plugin="pyav") as out:
        out.init_video_stream("libx264", fps=main_fps)

        for ep_idx, (camera_paths, traj_path, gw_path, depth_pairs) in zip(episode_indices, episode_video_paths):
            main_caps  = [cv2.VideoCapture(mp) for mp, _ in camera_paths]
            uw_caps    = [cv2.VideoCapture(up) for _, up in camera_paths]
            traj_cap   = cv2.VideoCapture(traj_path)
            gw_cap     = cv2.VideoCapture(gw_path) if gw_path is not None else None

            depth_full_caps    = []
            depth_clipped_caps = []
            if has_depth and depth_pairs is not None:
                for full_p, clipped_p in depth_pairs:
                    depth_full_caps.append(cv2.VideoCapture(full_p) if full_p is not None else None)
                    depth_clipped_caps.append(cv2.VideoCapture(clipped_p) if clipped_p is not None else None)

            # Compute natural depth cell height (aspect-ratio preserving, no padding)
            first_dc = next((c for c in depth_full_caps if c is not None), None)
            if first_dc is not None:
                dw = int(first_dc.get(cv2.CAP_PROP_FRAME_WIDTH))
                dh = int(first_dc.get(cv2.CAP_PROP_FRAME_HEIGHT))
                depth_cell_h = int(round(dh * cell_w / dw)) if dw > 0 else cell_h
            else:
                depth_cell_h = cell_h
            depth_blank = np.full((depth_cell_h, cell_w, 3), 255, dtype=np.uint8)

            main_frame_count = int(main_caps[0].get(cv2.CAP_PROP_FRAME_COUNT))

            for _ in tqdm(range(main_frame_count), desc=f'Combining episode {ep_idx}'):
                top_row    = []
                bot_row    = []
                depth_full_row    = []
                depth_clipped_row = []
                all_ok = True

                for main_cap, uw_cap in zip(main_caps, uw_caps):
                    ret_m, main_frame = main_cap.read()
                    if not ret_m:
                        all_ok = False
                        break
                    top_row.append(cv2.resize(main_frame, (cell_w, cell_h)))
                    ret_u, uw_frame = uw_cap.read()
                    bot_row.append(
                        cv2.resize(uw_frame, (cell_w, cell_h)) if ret_u else blank.copy()
                    )

                if not all_ok:
                    break

                ret_t, traj_frame = traj_cap.read()
                top_row.append(
                    cv2.resize(traj_frame, (cell_w, cell_h)) if ret_t else blank.copy()
                )

                if gw_cap is not None:
                    ret_gw, gw_frame = gw_cap.read()
                    bot_row.append(
                        cv2.resize(gw_frame, (cell_w, cell_h)) if ret_gw else blank.copy()
                    )
                else:
                    bot_row.append(blank.copy())

                if has_depth:
                    for dc in depth_full_caps:
                        if dc is not None:
                            ret_d, d_frame = dc.read()
                            depth_full_row.append(_resize_to_width(d_frame, cell_w) if ret_d else depth_blank.copy())
                        else:
                            depth_full_row.append(depth_blank.copy())
                    depth_full_row.append(depth_blank.copy())  # right-column blank (white)

                    for dc in depth_clipped_caps:
                        if dc is not None:
                            ret_d, d_frame = dc.read()
                            depth_clipped_row.append(_resize_to_width(d_frame, cell_w) if ret_d else depth_blank.copy())
                        else:
                            depth_clipped_row.append(depth_blank.copy())
                    depth_clipped_row.append(depth_blank.copy())  # right-column blank (white)

                rows = [np.hstack(top_row), np.hstack(bot_row)]
                if has_depth:
                    rows.append(np.hstack(depth_full_row))
                    rows.append(np.hstack(depth_clipped_row))
                grid = np.vstack(rows)
                out.write(cv2.cvtColor(grid, cv2.COLOR_BGR2RGB), is_batch=False)

            for c in main_caps + uw_caps:
                c.release()
            traj_cap.release()
            if gw_cap is not None:
                gw_cap.release()
            for c in depth_full_caps + depth_clipped_caps:
                if c is not None:
                    c.release()

    return output_path


def main():
    parser = argparse.ArgumentParser(description='Visualize UMI trajectory from replay buffer')
    parser.add_argument('dataset_path', type=str, help='Path to replay buffer (Zarr)')
    parser.add_argument('--output', '-o', type=str, default=None, help='Output video path (default: same directory as replay buffer)')
    parser.add_argument('--episodes', '-e', type=int, nargs='+', default=None,
                       help='List of episode indices to visualize (default: first episode)')
    parser.add_argument('--vis-all', action='store_true', help='Visualize all episodes')
    parser.add_argument('--max-frames', type=int, default=-1, help='Maximum number of frames per episode to visualize (default: -1 for all)')
    parser.add_argument('--load-dataset-in-memory', action='store_true', help='Load replay buffer into memory instead of reading from disk')
    parser.add_argument('--log-rotation-table', action='store_true', help='Log rotation table with rotations relative to first rotation in Euler angles (x, y, z)')
    parser.add_argument('--depth-max-distance', type=float, default=0.5, help='Clipped depth max distance in metres for the second depth row (default: 0.5)')
    
    args = parser.parse_args()
    
    # Validate input
    if not os.path.exists(args.dataset_path):
        raise FileNotFoundError(f"Replay buffer not found: {args.dataset_path}")
    
    print(f"Loading replay buffer from: {args.dataset_path}")
    replay_buffer = load_replay_buffer(args.dataset_path, keep_on_disk=not args.load_dataset_in_memory)
    
    print(f"Number of episodes: {replay_buffer.n_episodes}")
    
    # Determine which episodes to process
    if args.episodes is not None:
        episode_indices = args.episodes
    elif args.vis_all:
        episode_indices = list(range(replay_buffer.n_episodes))
    else:
        episode_indices = [0]

    for ep_idx in episode_indices:
        if ep_idx < 0 or ep_idx >= replay_buffer.n_episodes:
            raise ValueError(f"Episode index {ep_idx} out of range [0, {replay_buffer.n_episodes})")
    
    print(f"Processing {len(episode_indices)} episode(s): {episode_indices}")
    
    # Log rotation tables if requested
    if args.log_rotation_table:
        for ep_idx in episode_indices:
            try:
                log_rotation_table(replay_buffer, episode_idx=ep_idx)
            except Exception as e:
                print(f"Warning: Could not log rotation table for episode {ep_idx}: {e}")
    
    # Determine output path
    if args.output is None:
        replay_buffer_dir = os.path.dirname(args.dataset_path)
        replay_buffer_name = os.path.basename(args.dataset_path).replace('.zarr.zip', '').replace('.zarr', '')
        if len(episode_indices) == 1:
            args.output = os.path.join(replay_buffer_dir, f'{replay_buffer_name}_episode{episode_indices[0]}_visualization.mp4')
        else:
            args.output = os.path.join(replay_buffer_dir, f'{replay_buffer_name}_all_episodes_visualization.mp4')
    
    # Create temporary directory for intermediate videos
    temp_dir = tempfile.mkdtemp()
    try:
        # Process each episode
        episode_video_paths = []
        for ep_idx in episode_indices:
            camera_paths, traj_path, gw_path, depth_pairs = process_episode(
                replay_buffer, ep_idx, temp_dir, max_frames=args.max_frames,
                depth_max_distance=args.depth_max_distance,
            )
            episode_video_paths.append((camera_paths, traj_path, gw_path, depth_pairs))
        
        # Combine all episodes into single output
        print(f"\nCombining {len(episode_indices)} episode(s) into final output...")
        combine_multiple_episodes(
            episode_video_paths,
            args.output,
            replay_buffer,
            episode_indices
        )
        
        print(f"\nVisualization saved to: {args.output}")
        print(f"  Total episodes: {len(episode_indices)}")
        
    finally:
        # Clean up temporary directory
        shutil.rmtree(temp_dir)
        print("Cleaned up temporary files")


if __name__ == '__main__':
    main()
