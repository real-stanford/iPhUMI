# adapted from 07_generate_replay_buffer.py from UMI

import concurrent.futures
import multiprocessing
import pickle
import shutil
import tempfile
from pathlib import Path

import av
import numcodecs
import numpy as np
import yaml
import zarr
from omegaconf import DictConfig, ListConfig
from tqdm import tqdm

from iphumi.common.cv_util import depth2xyzmap, get_image_transform_with_border
from iphumi.common.imagecodecs_numcodecs import JpegXl, register_codecs
from iphumi.common.replay_buffer import ReplayBuffer, get_optimal_chunks, rechunk_recompress_array
from iphumi.demonstration_processing.utils.depth_util import load_depth
from iphumi.demonstration_processing.utils.lookat_util import (
    compute_center_lookat_from_pointmap,
)

register_codecs()

SIDE_ORDER = ("left", "right", "head")


def _ordered_sides(side_dict):
    return [side for side in SIDE_ORDER if side in side_dict]


def _resolve_episode_keep_ratio(cfg: DictConfig, episode_name: str, n_frames_full: int) -> int:
    episode_keep_ratio = float(cfg.get("episode_keep_ratio", 1.0))
    if not (0.0 < episode_keep_ratio <= 1.0):
        raise ValueError(f"episode_keep_ratio must be in (0, 1], got {episode_keep_ratio}")

    name_filter = cfg.get("episode_keep_ratio_name_filter", None)
    if isinstance(name_filter, str) and not name_filter:
        name_filter = None
    if isinstance(name_filter, ListConfig):
        name_filter = list(name_filter)
    if isinstance(name_filter, list):
        name_filter = [str(token) for token in name_filter]

    use_ratio = episode_keep_ratio
    if name_filter is not None:
        if isinstance(name_filter, str):
            match = name_filter in episode_name
        else:
            match = any(token in episode_name for token in name_filter)
        if not match:
            use_ratio = 1.0

    n_frames = max(1, int(np.floor(n_frames_full * use_ratio)))
    return min(n_frames, n_frames_full)


def _resolve_local_path(path_str: str) -> Path:
    candidate_paths = [
        Path(path_str).expanduser(),
        Path.cwd().joinpath(path_str),
        Path(__file__).resolve().parent.parent.joinpath(path_str),
    ]
    for candidate in candidate_paths:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"Could not resolve path: {path_str}")


def _camera_output_res(
    side: str,
    save_pointmap: bool,
    save_pointmap_side: str,
    out_res_rgb,
    out_res_pointmap,
):
    if save_pointmap and side == save_pointmap_side:
        return out_res_pointmap
    return out_res_rgb


def _validate_training_schema(
    replay_buffer: ReplayBuffer,
    expected_sides,
    buffer_length: int,
    uw_buffer_lengths: dict,
    save_pointmap: bool,
    save_pointmap_side: str,
    save_look_at_point: bool,
    include_demo_start_end_pose: bool,
    out_res_rgb,
    out_res_pointmap,
):
    if expected_sides is None:
        return

    data_group = replay_buffer.data

    for side in expected_sides["grippers"]:
        required_keys = [
            f"gripper_{side}_eef_pos",
            f"gripper_{side}_eef_rot_axis_angle",
        ]
        if include_demo_start_end_pose:
            required_keys += [
                f"gripper_{side}_demo_start_pose",
                f"gripper_{side}_demo_end_pose",
            ]
        missing = [key for key in required_keys if key not in data_group]
        if missing:
            raise ValueError(f"Replay buffer missing gripper keys for side '{side}': {missing}")

    for side in expected_sides["cameras"]:
        expected_res = _camera_output_res(
            side,
            save_pointmap=save_pointmap,
            save_pointmap_side=save_pointmap_side,
            out_res_rgb=out_res_rgb,
            out_res_pointmap=out_res_pointmap,
        )
        uw_length = buffer_length if not uw_buffer_lengths else uw_buffer_lengths.get(side, 0)
        for suffix, expected_length in (
            ("main_rgb", buffer_length),
            ("ultrawide_rgb", uw_length),
        ):
            key = f"camera_{side}_{suffix}"
            if key not in data_group:
                raise ValueError(f"Replay buffer missing camera key '{key}'")
            shape = data_group[key].shape
            if shape[0] != expected_length or tuple(shape[1:3]) != expected_res or shape[-1] != 3:
                raise ValueError(
                    f"Replay buffer dataset '{key}' has incompatible shape {shape}; "
                    f"expected ({expected_length}, {expected_res[0]}, {expected_res[1]}, 3)"
                )

    if not save_pointmap:
        return

    if save_pointmap_side not in expected_sides["cameras"]:
        print(
            f"[gen_replay_buffer] Warning: configured pointmap side '{save_pointmap_side}' "
            "is not present in this session; skipping xm_dev pointmap validation."
        )
        return

    pointmap_key = f"camera_{save_pointmap_side}_pointmap"
    if pointmap_key not in data_group:
        raise ValueError(f"Replay buffer missing pointmap key '{pointmap_key}'")
    pointmap_shape = data_group[pointmap_key].shape
    if pointmap_shape[0] != buffer_length or tuple(pointmap_shape[1:3]) != out_res_pointmap or pointmap_shape[-1] != 3:
        raise ValueError(
            f"Replay buffer dataset '{pointmap_key}' has incompatible shape {pointmap_shape}; "
            f"expected ({buffer_length}, {out_res_pointmap[0]}, {out_res_pointmap[1]}, 3)"
        )

    head_rgb_key = f"camera_{save_pointmap_side}_main_rgb"
    if tuple(data_group[head_rgb_key].shape[1:3]) != out_res_pointmap:
        raise ValueError(
            f"Replay buffer dataset '{head_rgb_key}' must match pointmap resolution "
            f"{out_res_pointmap}, got {data_group[head_rgb_key].shape[1:3]}"
        )

    if save_look_at_point:
        lookat_key = f"camera_{save_pointmap_side}_lookatpoint"
        if lookat_key not in data_group:
            raise ValueError(f"Replay buffer missing look-at key '{lookat_key}'")
        lookat_shape = data_group[lookat_key].shape
        if lookat_shape != (buffer_length, 3):
            raise ValueError(
                f"Replay buffer dataset '{lookat_key}' has incompatible shape {lookat_shape}; "
                f"expected ({buffer_length}, 3)"
            )


def gen_zarr_replay_buffer(session_dir: str, dataset_plan_path: str, out_replay_buffer_path: str, cfg: DictConfig):
    save_depth = bool(cfg.get("save_depth", cfg.get("include_depth", False)))
    save_pointmap = bool(cfg.get("save_pointmap", False))
    save_pointmap_side = str(cfg.get("save_pointmap_side", "head"))
    save_look_at_point = bool(cfg.get("save_look_at_point", False))
    upsample_ultrawide = bool(cfg.get("upsample_ultrawide_to_full_frequency", False))
    include_demo_start_end_pose = bool(cfg.get("include_demo_start_end_pose", False))
    if save_look_at_point and not save_pointmap:
        raise ValueError("save_look_at_point requires save_pointmap to also be enabled")

    if cfg.num_workers == -1:
        num_workers = multiprocessing.cpu_count()
    else:
        num_workers = cfg.num_workers

    _temp_dir = tempfile.mkdtemp(prefix="iphumi_replay_buffer_")
    out_replay_buffer = ReplayBuffer.create_empty_zarr(storage=zarr.DirectoryStore(_temp_dir))

    buffer_start = 0
    uw_buffer_starts = {}  # side → cumulative ultrawide frame count
    vid_args = []
    demos_path = Path(session_dir).joinpath("demos")
    depth_shape = (192, 256)
    depth_dtype = np.float16

    with open(dataset_plan_path, "rb") as f:
        plan = pickle.load(f)

    max_episodes = cfg.get("max_episodes", None)
    if max_episodes is not None:
        plan = plan[:int(max_episodes)]

    expected_sides = None
    for plan_episode in plan:
        grippers_by_side = {
            key.split("grippers_")[1]: value
            for key, value in plan_episode.items()
            if key.startswith("grippers_")
        }
        cameras_by_side = {
            key.split("cameras_")[1]: value
            for key, value in plan_episode.items()
            if key.startswith("cameras_")
        }

        if expected_sides is None:
            expected_sides = {
                "grippers": _ordered_sides(grippers_by_side),
                "cameras": _ordered_sides(cameras_by_side),
            }
        else:
            assert _ordered_sides(grippers_by_side) == expected_sides["grippers"], (
                f"Inconsistent gripper sides in episode {plan_episode['episode_name']}"
            )
            assert _ordered_sides(cameras_by_side) == expected_sides["cameras"], (
                f"Inconsistent camera sides in episode {plan_episode['episode_name']}"
            )

        pose_lengths = [grippers_by_side[side][0]["tcp_pose"].shape[0] for side in expected_sides["grippers"]]
        if not pose_lengths:
            raise ValueError(f"No gripper data found for episode {plan_episode['episode_name']}")
        if len(set(pose_lengths)) != 1:
            raise ValueError(
                f"Inconsistent aligned pose horizon in episode {plan_episode['episode_name']}: {pose_lengths}"
            )

        n_frames_full = pose_lengths[0]
        episode_name = plan_episode["episode_name"]
        n_frames = _resolve_episode_keep_ratio(cfg, episode_name, n_frames_full)
        if n_frames < n_frames_full:
            print(
                f"[gen_replay_buffer] Truncating episode {episode_name} "
                f"from {n_frames_full} to {n_frames} frames"
            )

        episode_data = {}
        for side in expected_sides["grippers"]:
            gripper = grippers_by_side[side][0]
            prefix = f"gripper_{side}"

            eef_pose = gripper["tcp_pose"][:n_frames]
            episode_data[f"{prefix}_eef_pos"] = eef_pose[..., :3].astype(np.float32)
            episode_data[f"{prefix}_eef_rot_axis_angle"] = eef_pose[..., 3:].astype(np.float32)
            if include_demo_start_end_pose:
                episode_data[f"{prefix}_demo_start_pose"] = gripper["demo_start_pose"][:n_frames].astype(
                    np.float32
                )
                episode_data[f"{prefix}_demo_end_pose"] = gripper["demo_end_pose"][:n_frames].astype(
                    np.float32
                )

            gripper_width = gripper["gripper_width"]
            if gripper_width is not None:
                episode_data[f"{prefix}_gripper_width"] = np.expand_dims(
                    np.asarray(gripper_width[:n_frames], dtype=np.float32), axis=-1
                )

        uw_data_by_side = {}
        for side in expected_sides["cameras"]:
            camera = cameras_by_side[side][0]
            camera_prefix = f"camera_{side}"

            main_video_path = demos_path.joinpath(camera["main_video_path"]).absolute()
            ultrawide_video_path = demos_path.joinpath(camera["ultrawide_video_path"]).absolute()
            assert main_video_path.is_file(), f"Main video not found: {main_video_path}"
            assert ultrawide_video_path.is_file(), f"Ultrawide video not found: {ultrawide_video_path}"

            vid_args.append(
                {
                    "video_path": str(main_video_path),
                    "camera_prefix": camera_prefix,
                    "camera_side": side,
                    "buffer_start": buffer_start,
                    "frame_indices": np.asarray(camera["pose_idx_to_main_idx"][:n_frames], dtype=np.int64),
                    "type": "main_rgb",
                }
            )

            uw_idx = np.asarray(camera["pose_idx_to_ultrawide_idx"][:n_frames], dtype=np.int64)
            if upsample_ultrawide:
                # Store one ultrawide frame per aligned (60 Hz) step, repeating frames as needed.
                uw_start = uw_buffer_starts.get(side, 0)
                vid_args.append(
                    {
                        "video_path": str(ultrawide_video_path),
                        "camera_prefix": camera_prefix,
                        "camera_side": side,
                        "buffer_start": uw_start,
                        "frame_indices": uw_idx,
                        "type": "ultrawide_rgb",
                    }
                )
                uw_data_by_side[side] = None
                uw_buffer_starts[side] = uw_start + n_frames
            else:
                # Store ultrawide at its native ~10 Hz: decode only the unique frames.
                # The 60 Hz → 10 Hz mapping is registered as upsample/downsample metadata.
                n_uw = int(uw_idx[-1]) + 1
                # For each unique ultrawide frame, the first 60 Hz aligned frame that uses it
                downsample_mapping = np.searchsorted(uw_idx, np.arange(n_uw, dtype=np.int64), side="left")

                uw_start = uw_buffer_starts.get(side, 0)
                vid_args.append(
                    {
                        "video_path": str(ultrawide_video_path),
                        "camera_prefix": camera_prefix,
                        "camera_side": side,
                        "buffer_start": uw_start,
                        "frame_indices": np.arange(n_uw, dtype=np.int64),
                        "type": "ultrawide_rgb",
                    }
                )
                uw_data_by_side[side] = (uw_idx, n_uw, downsample_mapping)
                uw_buffer_starts[side] = uw_start + n_uw

            needs_depth_processing = save_depth or (save_pointmap and side == save_pointmap_side)
            if needs_depth_processing:
                depth_video_path = demos_path.joinpath(camera["depth_video_path"]).absolute()
                assert depth_video_path.is_file(), f"Depth raw file not found: {depth_video_path}"
                vid_args.append(
                    {
                        "video_path": str(depth_video_path),
                        "camera_prefix": camera_prefix,
                        "camera_side": side,
                        "buffer_start": buffer_start,
                        "frame_indices": np.asarray(
                            camera["pose_idx_to_depth_idx"][:n_frames], dtype=np.int64
                        ),
                        "type": "depth",
                    }
                )

        out_replay_buffer.add_episode(
            data=episode_data,
            tasks=plan_episode["tasks"],
            compressors=None,
            episode_name=episode_name,
            is_error_correction=plan_episode.get("is_error_correction", False),
        )
        buffer_start += n_frames

        # Register ultrawide upsample/downsample index metadata (only in native-Hz mode).
        # Done after add_episode so episode_ends already contains the current episode's end.
        if not upsample_ultrawide:
            meta = out_replay_buffer.meta
            ep_ends = meta["episode_ends"]
            prev_main_end = int(np.asarray(ep_ends)[-2]) if len(np.asarray(ep_ends)) >= 2 else 0
            for side, uw_data in uw_data_by_side.items():
                uw_idx, n_uw, downsample_mapping = uw_data
                uw_key = f"camera_{side}_ultrawide_rgb"
                upsample_meta_key = f"upsample_index_{uw_key}"
                episode_ends_uw_key = f"episode_ends_{uw_key}"
                downsample_meta_key = f"downsample_index_{uw_key}"

                if upsample_meta_key in meta:
                    prev_uw_end = int(np.asarray(meta[episode_ends_uw_key])[-1])
                else:
                    prev_uw_end = 0

                out_replay_buffer.append_attribute(meta, upsample_meta_key, uw_idx + prev_uw_end)
                out_replay_buffer.append_attribute(meta, episode_ends_uw_key, prev_uw_end + n_uw)
                out_replay_buffer.append_attribute(meta, downsample_meta_key, downsample_mapping + prev_main_end)

    if not vid_args:
        raise ValueError(f"No demonstrations available to build replay buffer from {dataset_plan_path}")

    out_res_rgb_value = cfg.get("out_res_rgb", None)
    out_res_rgb = (out_res_rgb_value, out_res_rgb_value) if out_res_rgb_value is not None else (224, 224)
    out_res_pointmap_value = cfg.get("out_res_pointmap", None)
    out_res_pointmap = (
        (out_res_pointmap_value, out_res_pointmap_value)
        if out_res_pointmap_value is not None
        else (512, 512)
    )
    pad_depth_to_square = bool(cfg.get("pad_depth_to_square", False))
    out_res_depth_value = cfg.get("out_res_depth", None)
    if pad_depth_to_square:
        square_size = out_res_depth_value if out_res_depth_value is not None else max(depth_shape)
        out_res_depth = (square_size, square_size)
    else:
        out_res_depth = depth_shape  # native (192, 256) — no padding
    num_episodes = len(plan)
    print(f"{num_episodes} episodes used in total ({len(vid_args)} streams)!")  # noqa: T201

    main_rgb_meta = next(v for v in vid_args if v["type"] == "main_rgb")
    with av.open(main_rgb_meta["video_path"]) as container:
        in_stream = container.streams.video[0]
        main_ih, main_iw = in_stream.height, in_stream.width

    ultrawide_rgb_meta = next(v for v in vid_args if v["type"] == "ultrawide_rgb")
    with av.open(ultrawide_rgb_meta["video_path"]) as container:
        in_stream = container.streams.video[0]
        ultrawide_ih, ultrawide_iw = in_stream.height, in_stream.width

    pointmap_enabled = (
        save_pointmap
        and expected_sides is not None
        and save_pointmap_side in expected_sides["cameras"]
    )
    if save_pointmap and not pointmap_enabled:
        print(
            f"[gen_replay_buffer] Warning: pointmap side '{save_pointmap_side}' not found; "
            "building an xm_dev-compatible RGB/gripper buffer without pointmaps."
        )

    depth_intrinsic = None
    if pointmap_enabled:
        calibration_path = _resolve_local_path(str(cfg.get("iphone_calibration")))
        with open(calibration_path, "r") as f:
            calibration = yaml.safe_load(f)
        depth_intrinsic = np.asarray(calibration["depth"]["intrinsicMatrix"], dtype=np.float32)

    img_compressor = JpegXl(level=99, numthreads=1)
    float_compressor = numcodecs.Blosc(
        cname="zstd",
        clevel=5,
        shuffle=numcodecs.Blosc.BITSHUFFLE,
    )

    for side in expected_sides["cameras"]:
        camera_prefix = f"camera_{side}"
        side_out_res = _camera_output_res(
            side,
            save_pointmap=pointmap_enabled,
            save_pointmap_side=save_pointmap_side,
            out_res_rgb=out_res_rgb,
            out_res_pointmap=out_res_pointmap,
        )
        _ = out_replay_buffer.data.require_dataset(
            name=f"{camera_prefix}_main_rgb",
            shape=(buffer_start,) + side_out_res + (3,),
            chunks=(1,) + side_out_res + (3,),
            compressor=img_compressor,
            dtype=np.uint8,
        )
        uw_total = buffer_start if upsample_ultrawide else uw_buffer_starts.get(side, 0)
        _ = out_replay_buffer.data.require_dataset(
            name=f"{camera_prefix}_ultrawide_rgb",
            shape=(uw_total,) + side_out_res + (3,),
            chunks=(1,) + side_out_res + (3,),
            compressor=img_compressor,
            dtype=np.uint8,
        )

        if save_depth:
            _ = out_replay_buffer.data.require_dataset(
                name=f"{camera_prefix}_depth",
                shape=(buffer_start,) + out_res_depth + (1,),
                chunks=(1,) + out_res_depth + (1,),
                compressor=float_compressor,
                dtype=depth_dtype,
            )

        if pointmap_enabled and side == save_pointmap_side:
            _ = out_replay_buffer.data.require_dataset(
                name=f"{camera_prefix}_pointmap",
                shape=(buffer_start,) + out_res_pointmap + (3,),
                chunks=(1,) + out_res_pointmap + (3,),
                compressor=float_compressor,
                dtype=depth_dtype,
            )
            if save_look_at_point:
                _ = out_replay_buffer.data.require_dataset(
                    name=f"{camera_prefix}_lookatpoint",
                    shape=(buffer_start, 3),
                    chunks=(1, 3),
                    compressor=float_compressor,
                    dtype=depth_dtype,
                )

    def video_to_zarr(replay_buffer, vid_metadata):
        vid_type = vid_metadata["type"]
        camera_prefix = vid_metadata["camera_prefix"]
        camera_side = vid_metadata["camera_side"]
        frame_indices = np.asarray(vid_metadata["frame_indices"], dtype=np.int64)
        buffer_offset = int(vid_metadata["buffer_start"])

        if vid_type == "depth":
            depth_array = load_depth(
                vid_metadata["video_path"], depth_shape=depth_shape, dtype=depth_dtype
            )
            depth_out = replay_buffer.data[f"{camera_prefix}_depth"] if save_depth else None
            pointmap_out = None
            lookatpoint_out = None
            if pointmap_enabled and camera_side == save_pointmap_side:
                pointmap_out = replay_buffer.data[f"{camera_prefix}_pointmap"]
                if save_look_at_point:
                    lookatpoint_out = replay_buffer.data[f"{camera_prefix}_lookatpoint"]

            resize_tf_depth = (
                get_image_transform_with_border(
                    in_res=(depth_shape[1], depth_shape[0]),
                    out_res=out_res_depth,
                    mode="depth",
                )
                if (save_depth and pad_depth_to_square)
                else None
            )
            resize_tf_pointmap = (
                get_image_transform_with_border(
                    in_res=(depth_shape[1], depth_shape[0]),
                    out_res=out_res_pointmap,
                    mode="pointmap",
                )
                if pointmap_out is not None
                else None
            )

            invalid_before = 0
            invalid_after = 0
            invalid_samples = []
            n_depth_frames = len(depth_array)
            for local_idx, frame_idx in enumerate(frame_indices):
                if frame_idx < 0:
                    invalid_before += 1
                    if len(invalid_samples) < 5:
                        invalid_samples.append((local_idx, int(frame_idx), "before"))
                    continue
                if frame_idx >= n_depth_frames:
                    invalid_after += 1
                    if len(invalid_samples) < 5:
                        invalid_samples.append((local_idx, int(frame_idx), "after"))
                    continue

                depth_frame = depth_array[frame_idx].copy()
                if depth_out is not None:
                    if resize_tf_depth is not None:
                        depth_frame_out = resize_tf_depth(depth_frame)
                    else:
                        depth_frame_out = depth_frame.astype(np.float16)
                    depth_out[buffer_offset + local_idx] = depth_frame_out[..., np.newaxis]

                if pointmap_out is not None:
                    pointmap = depth2xyzmap(depth_frame, depth_intrinsic)
                    pointmap_resized = resize_tf_pointmap(pointmap)
                    pointmap_out[buffer_offset + local_idx] = pointmap_resized
                    if lookatpoint_out is not None:
                        lookatpoint_out[buffer_offset + local_idx] = compute_center_lookat_from_pointmap(
                            pointmap_resized
                        )

            if invalid_before or invalid_after:
                print(
                    f"[gen_replay_buffer] Depth stream '{camera_prefix}' skipped "
                    f"{invalid_before} frames before start and {invalid_after} after end "
                    f"(depth frames: {n_depth_frames}). Examples: {invalid_samples}"
                )
            return

        if vid_type == "main_rgb":
            iw, ih = main_iw, main_ih
        else:
            iw, ih = ultrawide_iw, ultrawide_ih

        side_out_res = _camera_output_res(
            camera_side,
            save_pointmap=pointmap_enabled,
            save_pointmap_side=save_pointmap_side,
            out_res_rgb=out_res_rgb,
            out_res_pointmap=out_res_pointmap,
        )
        resize_tf = get_image_transform_with_border(
            in_res=(iw, ih),
            out_res=side_out_res,
            mode="rgb",
        )
        arr = replay_buffer.data[f"{camera_prefix}_{vid_type}"]
        with av.open(vid_metadata["video_path"]) as container:
            in_stream = container.streams.video[0]
            in_stream.thread_count = 1
            n_source_frames = in_stream.frames
            decoded_iter = container.decode(in_stream)
            decoded_idx = -1
            last_img = None
            for local_idx, frame_idx in enumerate(frame_indices):
                frame_idx = int(frame_idx)
                if not (0 <= frame_idx < n_source_frames):
                    continue
                while decoded_idx < frame_idx:
                    try:
                        raw = next(decoded_iter)
                        last_img = raw.to_ndarray(format="rgb24")
                        decoded_idx += 1
                    except StopIteration:
                        break
                if last_img is not None:
                    arr[buffer_offset + local_idx] = resize_tf(last_img)

    with tqdm(total=len(vid_args), smoothing=0) as pbar:
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = set()
            for vid_metadata in vid_args:
                if len(futures) >= num_workers:
                    completed, futures = concurrent.futures.wait(
                        futures, return_when=concurrent.futures.FIRST_COMPLETED
                    )
                    for future in completed:
                        future.result()
                    pbar.update(len(completed))

                futures.add(executor.submit(video_to_zarr, out_replay_buffer, vid_metadata))

            completed, _ = concurrent.futures.wait(futures)
            for future in completed:
                future.result()
            pbar.update(len(completed))

    _validate_training_schema(
        out_replay_buffer,
        expected_sides=expected_sides,
        buffer_length=buffer_start,
        uw_buffer_lengths={} if upsample_ultrawide else uw_buffer_starts,
        save_pointmap=pointmap_enabled,
        save_pointmap_side=save_pointmap_side,
        save_look_at_point=save_look_at_point,
        include_demo_start_end_pose=include_demo_start_end_pose,
        out_res_rgb=out_res_rgb,
        out_res_pointmap=out_res_pointmap,
    )

    # we rechunk the arrays so they have reasonable chunk sizes for training (we assume random sampling during training). This means we want fairly small chunks (8KB) so if we load just a single entry we aren't loading a huge amount of unnecessary data. The images and depth always use chunk size 1 which is not impacted by this logic below.

    _META_TARGET_CHUNK_BYTES = 8 * 1024
    for key in list(out_replay_buffer.meta.array_keys()):
        arr = out_replay_buffer.meta[key]
        optimal = get_optimal_chunks(shape=arr.shape, dtype=arr.dtype, target_chunk_bytes=_META_TARGET_CHUNK_BYTES)
        if optimal != arr.chunks:
            rechunk_recompress_array(out_replay_buffer.meta, key, chunks=optimal)

    _DATA_TARGET_CHUNK_BYTES = 8 * 1024
    for key in list(out_replay_buffer.data.array_keys()):
        arr = out_replay_buffer.data[key]
        if arr.chunks[0] == 1:
            continue  # images, depth, pointmaps — already frame-chunked
        optimal = get_optimal_chunks(shape=arr.shape, dtype=arr.dtype, target_chunk_bytes=_DATA_TARGET_CHUNK_BYTES)
        if optimal != arr.chunks:
            rechunk_recompress_array(out_replay_buffer.data, key, chunks=optimal)

    print(f"Saving ReplayBuffer to {out_replay_buffer_path}")
    try:
        with zarr.ZipStore(out_replay_buffer_path, mode="w") as zip_store:
            out_replay_buffer.save_to_store(store=zip_store)
    finally:
        shutil.rmtree(_temp_dir, ignore_errors=True)
    print(f"Done! {num_episodes} episodes used in total!")
