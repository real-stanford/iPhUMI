import faulthandler
import os
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from iphumi.common.trajectory_util import vis_video_aligned_trajectories, vis_trajectories, SIDE_TRAJECTORY_COLORS
from iphumi.demonstration_processing.utils.generic_util import (
    demonstration_to_display_string,
    get_aligned_trajectory_path,
    get_aligned_frame_times,
    get_demonstration_calibration,
    get_demonstration_sides_present,
    get_gripper_calibration_run_dir,
    read_aligned_csv,
)
from iphumi.demonstration_processing.utils.gripper_util import get_demo_gripper_width, iphone_to_tcp_poses
from iphumi.common.plot_util import plot_gripper_width, plot_multi_gripper_width, plot_inter_gripper_distances, SIDE_LINE_COLORS
from iphumi.demonstration_processing.utils.depth_util import load_depth, depth_array_to_color_video
import numpy as np
import cv2
from tqdm import tqdm
from multiprocessing import get_context
import imageio.v3 as iio


def _write_blank_video(path, width, height, num_frames, fps):
    blank = np.full((height, width, 3), 255, dtype=np.uint8)
    with iio.imopen(path, "w", plugin="pyav") as out:
        out.init_video_stream("libx264", fps=fps)
        for _ in range(num_frames):
            out.write(blank, is_batch=False)


def _assert_min_frames(video_path: str, min_frames: int = 5) -> None:
    cap = cv2.VideoCapture(video_path)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    if frame_count < min_frames:
        os.remove(video_path)
        raise RuntimeError(
            f"Video was not written correctly and has been deleted: {video_path} had {frame_count} frame(s), "
            f"expected at least {min_frames}."
        )


def visualize_aligned_iphone_data(demonstration_iterator, cfg):
    num_processed = 0
    num_already_processed = 0

    for demonstration_dir in demonstration_iterator('demonstration'):
        side_trajectories = []
        side_names = []
        min_len = None

        for side in get_demonstration_sides_present(demonstration_dir):
            trajectory_path = get_aligned_trajectory_path(demonstration_dir, side)
            if not os.path.exists(trajectory_path):
                continue
            poses = read_aligned_csv(demonstration_dir, side)["poses"]
            side_names.append(side)
            side_trajectories.append(poses)
            min_len = poses.shape[0] if min_len is None else min(min_len, poses.shape[0])

        if len(side_trajectories) < 2:
            continue

        out_path = os.path.join(demonstration_dir, 'multi_iphone_aligned_trajectory.mp4')
        if os.path.exists(out_path) and not cfg.overwrite:
            num_already_processed += 1
            continue

        print(
            f"{demonstration_to_display_string(demonstration_dir)} visualizing aligned "
            f"trajectories for sides: {side_names}"
        )
        poses_all_sides = [poses[:min_len] for poses in side_trajectories]
        vis_trajectories(
            out_path,
            poses_all_sides,
            fps=60,
            colors=[SIDE_TRAJECTORY_COLORS.get(s) for s in side_names],
        )
        print(f"{demonstration_to_display_string(demonstration_dir)} Wrote combined trajectory to {out_path}")
        num_processed += 1

    print(f'\nVisualized {num_processed} aligned multi-phone demonstrations')
    print(f'Previously processed {num_already_processed} aligned multi-phone demonstrations')

def _subprocess_target(fn, suppress_output, *args, **kwargs):
    faulthandler.enable()
    if suppress_output:
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        saved_out, saved_err = os.dup(1), os.dup(2)
        os.dup2(devnull_fd, 1)
        os.dup2(devnull_fd, 2)
        os.close(devnull_fd)
    try:
        fn(*args, **kwargs)
    except Exception:
        if suppress_output:
            os.dup2(saved_out, 1)
            os.dup2(saved_err, 2)
        traceback.print_exc()
        raise
    finally:
        if suppress_output:
            os.dup2(saved_out, 1)
            os.dup2(saved_err, 2)
            os.close(saved_out)
            os.close(saved_err)


def _run_in_subprocess(fn, args, kwargs, max_attempts=3, suppress_output=False):
    # Use spawn (not fork) so child gets a fresh Python interpreter with no inherited
    # EGL state — fork leaves EGL mutexes/fds in an inconsistent state after eglInitialize.
    ctx = get_context('spawn')
    last_exitcode = None
    for attempt in range(max_attempts):
        p = ctx.Process(target=_subprocess_target, args=(fn, suppress_output) + args, kwargs=kwargs)
        p.start()
        p.join()
        if p.exitcode == 0:
            return
        last_exitcode = p.exitcode
        print(f"Subprocess {fn.__name__} failed with exit code {last_exitcode} (attempt {attempt + 1}/{max_attempts})")
    raise RuntimeError(f"Subprocess {fn.__name__} failed with exit code {last_exitcode} after {max_attempts} attempts")


def _render_aligned_video(src_video_path: str, frame_indices: np.ndarray, out_path: str, fps: float) -> None:
    """Write a video where output frame i is the src frame at frame_indices[i]."""
    cap = cv2.VideoCapture(src_video_path)
    cur = 0
    last_frame = None
    with iio.imopen(out_path, "w", plugin="pyav") as out:
        out.init_video_stream("libx264", fps=fps)
        for tgt in frame_indices:
            tgt = int(tgt)
            while cur <= tgt:
                r, f = cap.read()
                if r:
                    last_frame = f
                cur += 1
            if last_frame is not None:
                out.write(last_frame[..., ::-1], is_batch=False)
    cap.release()


def _create_visualization_video(demonstration_dir, side, aligned_data, video_out_path, cfg):
    poses = aligned_data["poses"]

    main_indices  = aligned_data["rgb_frame_idx"]
    depth_indices = aligned_data["depth_frame_idx"]
    ultra_indices = aligned_data["ultrawide_frame_idx"]
    T = len(main_indices)

    aligned_times = get_aligned_frame_times(demonstration_dir)

    # Get FPS from the source RGB video
    tasks_video_path = os.path.join(demonstration_dir, f'{side}_subtasks.mp4')
    wide_rgb_video_path = tasks_video_path if os.path.exists(tasks_video_path) else os.path.join(demonstration_dir, f'{side}_rgb.mp4')
    cap = cv2.VideoCapture(wide_rgb_video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()

    # Convert the depth data into color, or write blank placeholders if depth is unavailable
    depth_path = os.path.join(demonstration_dir, f'{side}_depth.raw')
    depth_color_video_path = os.path.join(demonstration_dir, f'{side}_depth_color.mp4')
    clipped_depth_color_video_path = os.path.join(demonstration_dir, f'{side}_depth_color_clipped.mp4')
    if os.path.exists(depth_path):
        depth_array = load_depth(depth_path, depth_shape=(192, 256), dtype=np.float16)
        depth_array_to_color_video(depth_array, depth_color_video_path, depth_shape=(192, 256), max_distance=-1)
        depth_array_to_color_video(depth_array, clipped_depth_color_video_path, depth_shape=(192, 256), max_distance=cfg.depth_max_distance)
    else:
        _write_blank_video(depth_color_video_path, width=256, height=192, num_frames=T, fps=fps)
        _write_blank_video(clipped_depth_color_video_path, width=256, height=192, num_frames=T, fps=fps)

    # Pre-render time-aligned versions of all streams so each output frame i
    # corresponds exactly to the nearest source frame for aligned timestamp i.
    ultrawide_rgb_video_path = os.path.join(demonstration_dir, f'{side}_ultrawidergb.mp4')
    aligned_main_tmp     = f'{demonstration_dir}/{side}_aligned_main_tmp.mp4'
    aligned_depth_tmp    = f'{demonstration_dir}/{side}_aligned_depth_tmp.mp4'
    aligned_clipped_tmp  = f'{demonstration_dir}/{side}_aligned_clipped_tmp.mp4'
    aligned_ultra_tmp    = f'{demonstration_dir}/{side}_aligned_ultra_tmp.mp4'

    _render_aligned_video(wide_rgb_video_path,            main_indices,  aligned_main_tmp,    fps)
    _render_aligned_video(depth_color_video_path,         depth_indices, aligned_depth_tmp,   fps)
    _render_aligned_video(clipped_depth_color_video_path, depth_indices, aligned_clipped_tmp, fps)
    _render_aligned_video(ultrawide_rgb_video_path,       ultra_indices, aligned_ultra_tmp,   fps)

    # Overlay trajectory on the aligned main video in a subprocess because sometimes there are OpenGL context issues when doing it in the main process after running a couple times. We also retry a couple times in case of failure since it seems to be somewhat flaky whether EGL always initializes correctly.
    intermediate_video_out_path = f'{demonstration_dir}/{side}_visualized_intermediate.mp4'
    tcp_poses = iphone_to_tcp_poses(demonstration_dir, side, poses)
    suppress = getattr(cfg, 'parallel', False) and getattr(cfg, 'suppress_output_if_parallel', False)
    _run_in_subprocess(
        vis_video_aligned_trajectories,
        (aligned_main_tmp, intermediate_video_out_path, tcp_poses),
        {'max_frames': cfg.visualize_til_frame, 'trajectory_render_size': cfg.trajectory_render_size, 'colors': [SIDE_TRAJECTORY_COLORS.get(side)]},
        suppress_output=suppress,
    )

    assert os.path.exists(intermediate_video_out_path), f"Intermediate video was not created at {intermediate_video_out_path}"

    ultrawide_cap     = cv2.VideoCapture(aligned_ultra_tmp)
    depth_cap         = cv2.VideoCapture(aligned_depth_tmp)
    clipped_depth_cap = cv2.VideoCapture(aligned_clipped_tmp)
    intermediate_cap  = cv2.VideoCapture(intermediate_video_out_path)

    width  = int(intermediate_cap.get(cv2.CAP_PROP_FRAME_WIDTH)) // 2
    height = int(intermediate_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    gripper_widths, gripper_detection_types = get_demo_gripper_width(
        demonstration_dir, side, include_detection_types=True, aligned_video_times=aligned_times
    )

    with iio.imopen(video_out_path, "w", plugin="pyav") as out:
        out.init_video_stream("libx264", fps=fps)
        suppress = getattr(cfg, 'parallel', False) and getattr(cfg, 'suppress_output_if_parallel', False)
        for frame_i in tqdm(range(T), total=T, leave=False, desc='combining videos', disable=suppress):
            ret1, ultrawide_frame   = ultrawide_cap.read()
            ret2, depth_frame       = depth_cap.read()
            ret3, clipped_depth_frame = clipped_depth_cap.read()
            ret4, intermediate_frame  = intermediate_cap.read()

            if not ret1 or not ret2 or not ret3 or not ret4:
                break

            depth_frame          = cv2.resize(depth_frame,          (width, height))
            clipped_depth_frame  = cv2.resize(clipped_depth_frame,  (width, height))
            ultrawide_frame      = cv2.resize(ultrawide_frame,      (width, height))

            horizontal_stack = np.hstack((ultrawide_frame, depth_frame))
            vertical_stack   = np.vstack((intermediate_frame, horizontal_stack))

            if gripper_widths is None:
                gripper_width_im = np.ones((height, width, 3), dtype=np.uint8) * 255
            else:
                gripper_width_im = plot_gripper_width(
                    gripper_widths, gripper_detection_types, frame_i, width, height,
                    line_color=SIDE_LINE_COLORS.get(side),
                )[..., ::-1]
            side_stack = np.vstack((gripper_width_im, clipped_depth_frame))

            final = np.hstack((vertical_stack, side_stack))
            out.write(final[..., ::-1], is_batch=False)

    ultrawide_cap.release()
    depth_cap.release()
    clipped_depth_cap.release()
    intermediate_cap.release()

    for tmp in [aligned_main_tmp, aligned_depth_tmp, aligned_clipped_tmp, aligned_ultra_tmp, intermediate_video_out_path]:
        if os.path.exists(tmp):
            os.remove(tmp)

def _create_combined_visualization_video(demonstration_dir, sides, all_aligned_poses, video_out_path, cfg):
    """
    Create a combined, time-aligned visualization for all sides present.

    Layout (TILE_H x TILE_W tiles):
      Row 0: [side0_main | side1_main | ... | trajectory_3d (all sides)]
      Row 1: [side0_ultrawide | side1_ultrawide | ... | combined gripper plot]
      Row 2: [side0_depth_color | side1_depth_color | ... | inter-gripper distance plot]
      Row 3: [side0_depth_color_clipped | side1_depth_color_clipped | ... | blank]

    TCP poses used for left/right sides; raw ARKit poses for head.
    All video frames are time-aligned via aligned frame-time metadata + searchsorted.
    """
    TILE_H = cfg.trajectory_render_size
    TILE_W = int(cfg.trajectory_render_size * 4 / 3)
    N = len(sides)
    T = all_aligned_poses[0].shape[0]

    # FPS from first available main video
    fps = 20.0
    for side in sides:
        for fname in [f'{side}_subtasks.mp4', f'{side}_rgb.mp4']:
            vid = os.path.join(demonstration_dir, fname)
            if os.path.exists(vid):
                cap = cv2.VideoCapture(vid)
                fps = cap.get(cv2.CAP_PROP_FPS)
                cap.release()
                break
        else:
            continue
        break

    # TCP poses for left/right; raw ARKit for head
    tcp_poses_list = []
    for i, side in enumerate(sides):
        if side == 'head':
            tcp_poses_list.append(all_aligned_poses[i])
        else:
            tcp_poses_list.append(iphone_to_tcp_poses(demonstration_dir, side, all_aligned_poses[i]))

    # Render combined trajectory video in a subprocess
    traj_tmp = os.path.join(demonstration_dir, 'combined_traj_tmp.mp4')
    suppress = getattr(cfg, 'parallel', False) and getattr(cfg, 'suppress_output_if_parallel', False)
    _run_in_subprocess(
        vis_trajectories,
        (traj_tmp, tcp_poses_list),
        {'out_width': TILE_W, 'out_height': TILE_H, 'offscreen': True, 'fps': fps, 'colors': [SIDE_TRAJECTORY_COLORS.get(s) for s in sides]},
        suppress_output=suppress,
    )
    assert os.path.exists(traj_tmp), f"Trajectory video not created at {traj_tmp}"

    aligned_times = get_aligned_frame_times(demonstration_dir)

    # Inter-gripper distances from ARKit poses
    inter_gripper_data = []
    for i in range(len(sides)):
        for j in range(i + 1, len(sides)):
            pos_a = all_aligned_poses[i][:, :3, 3]
            pos_b = all_aligned_poses[j][:, :3, 3]
            distances = np.linalg.norm(pos_a - pos_b, axis=1)
            inter_gripper_data.append((f'{sides[i]}-{sides[j]}', distances))

    # Gripper widths at the aligned rate for sides that have them
    gripper_data = []
    for side in sides:
        try:
            widths, det_types = get_demo_gripper_width(
                demonstration_dir, side, include_detection_types=True, aligned_video_times=aligned_times
            )
            if widths is not None:
                gripper_data.append((side, widths, det_types))
        except Exception:
            pass

    # Per-side: read frame indices from aligned CSV + resolve video paths
    side_info = []
    for side in sides:
        aligned_data = read_aligned_csv(demonstration_dir, side)

        for fname in [f'{side}_depth_color.mp4', f'{side}_depth_color_clipped.mp4']:
            path = os.path.join(demonstration_dir, fname)
            if not os.path.exists(path):
                raise FileNotFoundError(f"Missing {path} — run the visualize stage for side {side} first.")

        tasks_path = os.path.join(demonstration_dir, f'{side}_subtasks.mp4')
        main_video = tasks_path if os.path.exists(tasks_path) else os.path.join(demonstration_dir, f'{side}_rgb.mp4')

        side_info.append({
            'main_video': main_video,
            'ultrawide_video': os.path.join(demonstration_dir, f'{side}_ultrawidergb.mp4'),
            'depth_video': os.path.join(demonstration_dir, f'{side}_depth_color.mp4'),
            'depth_clipped_video': os.path.join(demonstration_dir, f'{side}_depth_color_clipped.mp4'),
            'main_indices': aligned_data['rgb_frame_idx'],
            'ultra_indices': aligned_data['ultrawide_frame_idx'],
            'depth_indices': aligned_data['depth_frame_idx'],
        })

    # Open all captures
    traj_cap = cv2.VideoCapture(traj_tmp)
    main_caps         = [cv2.VideoCapture(info['main_video']) for info in side_info]
    ultra_caps        = [cv2.VideoCapture(info['ultrawide_video']) for info in side_info]
    depth_caps        = [cv2.VideoCapture(info['depth_video']) for info in side_info]
    depth_clipped_caps = [cv2.VideoCapture(info['depth_clipped_video']) for info in side_info]

    # Sequential-read state
    cur_main          = [0] * N
    cur_ultra         = [0] * N
    cur_depth         = [0] * N
    cur_depth_clipped = [0] * N
    main_frames         = [np.full((TILE_H, TILE_W, 3), 255, dtype=np.uint8) for _ in range(N)]
    ultra_frames        = [np.full((TILE_H, TILE_W, 3), 255, dtype=np.uint8) for _ in range(N)]
    depth_frames        = [np.full((TILE_H, TILE_W, 3), 255, dtype=np.uint8) for _ in range(N)]
    depth_clipped_frames = [np.full((TILE_H, TILE_W, 3), 255, dtype=np.uint8) for _ in range(N)]

    with iio.imopen(video_out_path, "w", plugin="pyav") as out:
        out.init_video_stream("libx264", fps=fps)
        suppress = getattr(cfg, 'parallel', False) and getattr(cfg, 'suppress_output_if_parallel', False)
        for frame_i in tqdm(range(T), total=T, leave=False, desc='combined visualization', disable=suppress):
            ret, traj_frame = traj_cap.read()
            if not ret:
                break

            for i, info in enumerate(side_info):
                tgt = int(info['main_indices'][frame_i])
                while cur_main[i] <= tgt:
                    r, f = main_caps[i].read()
                    if r:
                        main_frames[i] = f
                    cur_main[i] += 1

                tgt = int(info['ultra_indices'][frame_i])
                while cur_ultra[i] <= tgt:
                    r, f = ultra_caps[i].read()
                    if r:
                        ultra_frames[i] = f
                    cur_ultra[i] += 1

                tgt = int(info['depth_indices'][frame_i])
                while cur_depth[i] <= tgt:
                    r, f = depth_caps[i].read()
                    if r:
                        depth_frames[i] = f
                    cur_depth[i] += 1

                while cur_depth_clipped[i] <= tgt:
                    r, f = depth_clipped_caps[i].read()
                    if r:
                        depth_clipped_frames[i] = f
                    cur_depth_clipped[i] += 1

            if gripper_data:
                gripper_tile = plot_multi_gripper_width(gripper_data, frame_i, TILE_W, TILE_H)[..., ::-1]
            else:
                gripper_tile = np.full((TILE_H, TILE_W, 3), 255, dtype=np.uint8)

            row0 = np.hstack(
                [cv2.resize(main_frames[i],  (TILE_W, TILE_H)) for i in range(N)]
                + [cv2.resize(traj_frame, (TILE_W, TILE_H))]
            )
            row1 = np.hstack(
                [cv2.resize(ultra_frames[i], (TILE_W, TILE_H)) for i in range(N)]
                + [gripper_tile]
            )
            if inter_gripper_data:
                dist_tile = plot_inter_gripper_distances(inter_gripper_data, frame_i, TILE_W, TILE_H, convention='ARKit')[..., ::-1]
            else:
                dist_tile = np.full((TILE_H, TILE_W, 3), 255, dtype=np.uint8)
            row2 = np.hstack(
                [cv2.resize(depth_frames[i], (TILE_W, TILE_H)) for i in range(N)]
                + [dist_tile]
            )
            row3 = np.hstack(
                [cv2.resize(depth_clipped_frames[i], (TILE_W, TILE_H)) for i in range(N)]
                + [np.full((TILE_H, TILE_W, 3), 255, dtype=np.uint8)]
            )
            out.write(np.vstack([row0, row1, row2, row3])[..., ::-1], is_batch=False)

    traj_cap.release()
    for cap in main_caps + ultra_caps + depth_caps + depth_clipped_caps:
        cap.release()

    os.remove(traj_tmp)


def _process_one_demonstration(demonstration_dir, cfg, quiet=False):
    """Process a single demonstration.

    Returns the path of the completed output video, or None if nothing new was written.
    For multi-side demos the combined video path is returned; for single-side the per-side path.
    """
    def log(msg):
        if not quiet:
            print(msg)

    for side in get_demonstration_sides_present(demonstration_dir):
        calibration = get_demonstration_calibration(demonstration_dir, side)
        if side == 'head' or 'gripper_transform' not in calibration:
            continue
        cal_run_dir = get_gripper_calibration_run_dir(demonstration_dir, side)
        gripper_range_path = os.path.join(cal_run_dir, f'{side}_gripper_range.json')
        if not os.path.exists(gripper_range_path):
            raise FileNotFoundError(
                f"Gripper calibration not processed for {demonstration_to_display_string(demonstration_dir, side)}. "
                f"Expected: {gripper_range_path}\n"
                f"Run the calibrate stage first (or include the calibration demo in your filter)."
            )

    completed_path = None

    for side in get_demonstration_sides_present(demonstration_dir):
        aligned_data = read_aligned_csv(demonstration_dir, side)
        video_out_path = f'{demonstration_dir}/{side}_visualized.mp4'
        if os.path.exists(video_out_path) and not cfg.overwrite:
            continue
        log(f'{demonstration_to_display_string(demonstration_dir, side)} Beginning to visualize on {side} side')
        _create_visualization_video(demonstration_dir, side, aligned_data, video_out_path, cfg)
        _assert_min_frames(video_out_path)
        log(f'{demonstration_to_display_string(demonstration_dir, side)} Wrote to {os.path.abspath(video_out_path)}')
        completed_path = os.path.abspath(video_out_path)

    sides_present = get_demonstration_sides_present(demonstration_dir)
    if len(sides_present) > 1:
        combined_out = os.path.join(demonstration_dir, 'combined_visualized.mp4')
        if not os.path.exists(combined_out) or cfg.overwrite:
            all_poses = []
            for side in sides_present:
                trajectory_path = get_aligned_trajectory_path(demonstration_dir, side)
                if not os.path.exists(trajectory_path):
                    raise FileNotFoundError(
                        f"Need to run the align stage first. "
                        f"Missing aligned trajectory for {demonstration_to_display_string(demonstration_dir, side)}: "
                        f"{trajectory_path}"
                    )
                all_poses.append(read_aligned_csv(demonstration_dir, side)["poses"])
            min_T = min(p.shape[0] for p in all_poses)
            all_poses = [p[:min_T] for p in all_poses]
            log(f'{demonstration_to_display_string(demonstration_dir)} Creating combined visualization for sides: {sides_present}')
            _create_combined_visualization_video(demonstration_dir, sides_present, all_poses, combined_out, cfg)
            _assert_min_frames(combined_out)
            log(f'{demonstration_to_display_string(demonstration_dir)} Wrote combined visualization to {os.path.abspath(combined_out)}')
            completed_path = os.path.abspath(combined_out)

    return completed_path


def visualize_iphone_data(demonstration_iterator, cfg):
    parallel = getattr(cfg, 'parallel', False)
    num_workers = getattr(cfg, 'num_workers', None)
    max_workers = getattr(cfg, 'max_workers', None)
    if max_workers is not None:
        num_workers = min(num_workers, max_workers) if num_workers is not None else max_workers

    all_demos = list(demonstration_iterator('demonstration'))
    if len(all_demos) == 1:
        parallel = False
        cfg.parallel = False
    num_processed = 0
    num_already_processed = 0

    suppress = parallel and getattr(cfg, 'suppress_output_if_parallel', False)

    if parallel:
        if suppress:
            actual_workers = num_workers if num_workers is not None else os.cpu_count()
            print(f'Visualizing {len(all_demos)} demonstrations in parallel ({actual_workers} workers, output suppressed — each may take a couple minutes, paths will print as they complete)')
        with ProcessPoolExecutor(max_workers=num_workers, mp_context=get_context('spawn')) as executor:
            futures = {executor.submit(_process_one_demonstration, d, cfg, True): d for d in all_demos}
            with tqdm(total=len(futures), desc='Visualizing demonstrations', unit='demo') as pbar:
                for future in as_completed(futures):
                    demo_dir = futures[future]
                    try:
                        completed_path = future.result()
                        if completed_path is not None:
                            tqdm.write(f'Wrote {completed_path}')
                            num_processed += 1
                        else:
                            num_already_processed += 1
                    except Exception as e:
                        tqdm.write(f'Error processing {demonstration_to_display_string(demo_dir)}: {e}')
                    pbar.update(1)
    else:
        for demonstration_dir in tqdm(all_demos, desc='Visualizing demonstrations', unit='demo'):
            completed_path = _process_one_demonstration(demonstration_dir, cfg, quiet=False)
            if completed_path is not None:
                num_processed += 1
            else:
                num_already_processed += 1

    print(f'\nVisualized {num_processed} demonstrations')
    print(f'Previously processed {num_already_processed} demonstrations')
