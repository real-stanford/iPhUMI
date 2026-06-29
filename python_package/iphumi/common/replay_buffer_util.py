"""Utility to print out the contents of a replay buffer for debugging."""

import os
from typing import Optional

import cv2
import imageio.v3 as iio
import numpy as np
import zarr
from tqdm import tqdm

from iphumi.common.replay_buffer import ReplayBuffer

PREFERRED_SIDES = ("head", "left", "right")


def _side_priority(side: str):
    if side in PREFERRED_SIDES:
        return (PREFERRED_SIDES.index(side), side)
    return (len(PREFERRED_SIDES), side)


def _select_camera_prefixes(replay_buffer: ReplayBuffer) -> list[str]:
    """Return all camera prefixes sorted by side priority (head, left, right, others)."""
    data_keys = set(replay_buffer.keys())
    prefixes = []
    for key in data_keys:
        if key.startswith("camera_") and key.endswith("_main_rgb"):
            prefix = key[: -len("_main_rgb")]
            side = prefix.split("_", 1)[1]
            prefixes.append((side, prefix))

    if prefixes:
        prefixes.sort(key=lambda item: _side_priority(item[0]))
        return [p for _, p in prefixes]

    if "camera0_main_rgb" in data_keys:
        return ["camera0"]

    raise KeyError("Could not find a main camera stream in the replay buffer.")


def _camera_key(prefix: str, suffix: str) -> str:
    return f"{prefix}_{suffix}"


def _select_depth_key(replay_buffer: ReplayBuffer, camera_prefix: str) -> Optional[str]:
    data_keys = set(replay_buffer.keys())
    for candidate in (f"{camera_prefix}_depth", f"{camera_prefix}_main_depth"):
        if candidate in data_keys:
            return candidate
    depth_candidates = sorted(k for k in data_keys if k.endswith("_depth") or k.endswith("_main_depth"))
    return depth_candidates[0] if depth_candidates else None


def _depth_to_color(depth_frame: np.ndarray, max_distance: float) -> np.ndarray:
    depth_frame = depth_frame.astype(np.float32)
    if max_distance <= 0.0 or not np.isfinite(max_distance):
        gray = np.zeros_like(depth_frame, dtype=np.uint8)
    else:
        gray = (np.clip(depth_frame, 0.0, max_distance) / max_distance * 255.0).astype(np.uint8)
    return cv2.applyColorMap(gray, cv2.COLORMAP_RAINBOW)[..., ::-1]


def _map_main_indices_to_ultrawide(
    replay_buffer: ReplayBuffer, ultrawide_key: str, main_indices
) -> list[int]:
    if replay_buffer.is_key_upsampled(ultrawide_key):
        return [int(replay_buffer.map_upsample_index(ultrawide_key, idx)) for idx in main_indices]
    return [int(idx) for idx in main_indices]


def print_replay_buffer_summary(replay_buffer):
    print(replay_buffer)
    if hasattr(replay_buffer, "task_names"):
        task_names = replay_buffer.task_names[:]
        unique_tasks, counts = np.unique(task_names, return_counts=True)
        sorted_indices = np.argsort(unique_tasks)
        unique_tasks = unique_tasks[sorted_indices]
        counts = counts[sorted_indices]

        task_ec = replay_buffer.is_task_error_correction
        task_ec_arr = np.asarray(task_ec[:]).flatten() if task_ec is not None else None

        print("\nTask names:")
        for task_name, count in zip(unique_tasks, counts):
            if task_ec_arr is not None:
                mask = task_names == task_name
                n_ec = int(task_ec_arr[mask].sum())
                print(f"  {task_name}: {count} ({n_ec} error correction, {count - n_ec} regular)")
            else:
                print(f"  {task_name}: {count}")

    ec = replay_buffer.is_episode_error_correction
    if ec is not None:
        ec = np.asarray(ec[:])
        n_total = len(ec)
        n_ec = int(ec.sum())
        print(f"\nEpisodes: {n_total} total ({n_ec} error correction, {n_total - n_ec} regular)")

    def _print_group_details(group_name, group):
        if group is None or not hasattr(group, "items"):
            return
        items = list(group.items())
        if not items:
            return
        print(f"\n{'─' * 60}")
        print(f"  {group_name.upper()}")
        print(f"{'─' * 60}")
        for key, array in items:
            shape = getattr(array, "shape", None)
            chunks = getattr(array, "chunks", None)
            compressor = getattr(array, "compressor", None)
            print(f"  {key}")
            print(f"    shape={shape}  chunks={chunks}  compressor={compressor}")

    _print_group_details("data", getattr(replay_buffer, "data", None))
    _print_group_details("labels", getattr(replay_buffer, "labels", None))
    _print_group_details("meta", getattr(replay_buffer, "meta", None))
    print()


def print_replay_buffer_umi(
    path,
    vis_frame: bool = False,
    vis_video: bool = False,
    vis_tasks: bool = False,
    load_buffer_into_memory: bool = False,
    task_for_video: Optional[str] = None,
    depth_max_distance: float = 0.5,
):
    if load_buffer_into_memory:
        replay_buffer = ReplayBuffer.copy_from_path(path, store=zarr.MemoryStore())
    else:
        replay_buffer = ReplayBuffer.create_from_path(path)

    print_replay_buffer_summary(replay_buffer)

    out_dir = os.path.dirname(path)
    camera_prefixes = _select_camera_prefixes(replay_buffer)
    main_keys = [_camera_key(p, "main_rgb") for p in camera_prefixes]
    ultrawide_keys = [_camera_key(p, "ultrawide_rgb") for p in camera_prefixes]

    def _hstack_frames(arrays):
        """Horizontally stack frames, resizing to match height of the first."""
        if len(arrays) == 1:
            return arrays[0]
        h = arrays[0].shape[0]
        resized = []
        for a in arrays:
            if a.shape[0] != h:
                scale = h / a.shape[0]
                a = cv2.resize(a, (int(a.shape[1] * scale), h))
            resized.append(a)
        return np.concatenate(resized, axis=1)

    if vis_frame:
        sample_index = np.random.randint(0, replay_buffer[main_keys[0]].shape[0])
        main_rgb = _hstack_frames([replay_buffer[k][sample_index] for k in main_keys])[..., ::-1]
        out_path = os.path.join(out_dir, "tmp_main_rgb.png")
        cv2.imwrite(out_path, main_rgb)
        print(f"Saved main RGB image to {out_path}")

        uw_frames = []
        for p, uk in zip(camera_prefixes, ultrawide_keys):
            uw_idx = _map_main_indices_to_ultrawide(replay_buffer, uk, [sample_index])[0]
            uw_frames.append(replay_buffer[uk][uw_idx])
        ultrawide_rgb = _hstack_frames(uw_frames)[..., ::-1]
        out_path = os.path.join(out_dir, "tmp_ultrawide_rgb.png")
        cv2.imwrite(out_path, ultrawide_rgb)
        print(f"Saved ultrawide RGB image to {out_path}")

    if vis_video:
        main_frame_indices = None
        ultrawide_frame_indices = None
        if task_for_video is not None:
            task_names = replay_buffer.task_names[:]
            matching_task_indices = np.where(task_names == task_for_video)[0]
            if len(matching_task_indices) == 0:
                print(f'Warning: No tasks found with name "{task_for_video}". Creating empty videos.')
                main_frame_indices = []
                ultrawide_frame_indices = []
            else:
                main_frame_indices_list = []
                for task_idx in matching_task_indices:
                    end_frame_idx = replay_buffer.task_data_ends[task_idx]
                    start_frame_idx = end_frame_idx - replay_buffer.task_lengths[task_idx]
                    main_frame_indices_list.extend(range(start_frame_idx, end_frame_idx))

                main_frame_indices = sorted(set(main_frame_indices_list))
                ultrawide_frame_indices = sorted(
                    set(_map_main_indices_to_ultrawide(replay_buffer, ultrawide_keys[0], main_frame_indices))
                )
                print(f'Found {len(matching_task_indices)} task(s) with name "{task_for_video}"')
                print(
                    f"Including {len(main_frame_indices)} main camera frames and "
                    f"{len(ultrawide_frame_indices)} ultrawide camera frames in videos"
                )

        video_path = os.path.join(out_dir, "tmp_main_video.mp4")
        frame_range = (
            main_frame_indices if main_frame_indices is not None else range(replay_buffer[main_keys[0]].shape[0])
        )
        with iio.imopen(video_path, "w", plugin="pyav") as out:
            out.init_video_stream("libx264", fps=60)
            for idx in tqdm(frame_range, desc="Writing main video"):
                out.write(_hstack_frames([replay_buffer[k][idx] for k in main_keys]), is_batch=False)
        print(f"Saved main video to {video_path}")

        video_path = os.path.join(out_dir, "tmp_ultrawide_video.mp4")
        ultrawide_fps = 10 if replay_buffer.is_key_upsampled(ultrawide_keys[0]) else 60
        frame_range = (
            ultrawide_frame_indices
            if ultrawide_frame_indices is not None
            else range(replay_buffer[ultrawide_keys[0]].shape[0])
        )
        with iio.imopen(video_path, "w", plugin="pyav") as out:
            out.init_video_stream("libx264", fps=ultrawide_fps)
            for idx in tqdm(frame_range, desc="Writing ultrawide video"):
                out.write(_hstack_frames([replay_buffer[k][idx] for k in ultrawide_keys]), is_batch=False)
        print(f"Saved ultrawide video to {video_path}")

        depth_keys = [_select_depth_key(replay_buffer, p) for p in camera_prefixes]
        depth_keys = [k for k in depth_keys if k is not None]
        if depth_keys:
            depths = []
            for dk in depth_keys:
                d = replay_buffer[dk]
                if d.ndim == 4 and d.shape[-1] == 1:
                    d = d[..., 0]
                depths.append(d)
            frame_range = (
                main_frame_indices if main_frame_indices is not None else range(depths[0].shape[0])
            )
            auto_max = float(max(np.max(d) for d in depths)) if depths[0].size > 0 else 0.0

            for suffix, dist in (("full", auto_max), ("clipped", depth_max_distance)):
                video_path = os.path.join(out_dir, f"tmp_depth_{suffix}_video.mp4")
                with iio.imopen(video_path, "w", plugin="pyav") as out:
                    out.init_video_stream("libx264", fps=60)
                    for idx in tqdm(frame_range, desc=f"Writing depth {suffix} video"):
                        frames = [_depth_to_color(d[idx], max_distance=dist) for d in depths]
                        out.write(_hstack_frames(frames), is_batch=False)
                print(f"Saved depth {suffix} video to {video_path}")

    if vis_tasks:
        if not hasattr(replay_buffer, "task_names"):
            print("Warning: No task names found in replay buffer. Skipping --vis-tasks.")
        else:
            lr_prefixes = [p for p in camera_prefixes if p.split("_", 1)[1] in ("left", "right")]
            if not lr_prefixes:
                lr_prefixes = camera_prefixes
            lr_main_keys = [_camera_key(p, "main_rgb") for p in lr_prefixes]

            task_names_arr = replay_buffer.task_names[:]
            for task_name in np.unique(task_names_arr):
                matching_task_indices = np.where(task_names_arr == task_name)[0]
                safe_name = task_name.replace(" ", "_")
                for task_idx in matching_task_indices:
                    end_frame_idx = replay_buffer.task_data_ends[task_idx]
                    start_frame_idx = end_frame_idx - replay_buffer.task_lengths[task_idx]
                    frame_indices = range(start_frame_idx, end_frame_idx)

                    video_path = os.path.join(out_dir, f"{safe_name}_{task_idx}.mp4")
                    with iio.imopen(video_path, "w", plugin="pyav") as out:
                        out.init_video_stream("libx264", fps=60)
                        for idx in tqdm(frame_indices, desc=f"Writing task video: {task_name} [{task_idx}]"):
                            out.write(_hstack_frames([replay_buffer[k][idx] for k in lr_main_keys]), is_batch=False)
                    print(f"Saved task video to {video_path}")
