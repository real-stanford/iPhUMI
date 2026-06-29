"""Interactive Open3D viewer for aligned trajectories.

Usage:
    python interactive_trajectory_viewer.py path/to/left.json
    python interactive_trajectory_viewer.py path/to/left_aligned.csv
    python interactive_trajectory_viewer.py path/to/demo_dir/
    python interactive_trajectory_viewer.py path/to/demo_dir/ --sides left right
    python interactive_trajectory_viewer.py path/to/demo_dir/ --no-tcp
    python interactive_trajectory_viewer.py path/to/demo_dir/ --step-through
    python interactive_trajectory_viewer.py path/to/demo_dir/ --step-through --fps 60
    python interactive_trajectory_viewer.py path/to/demo_dir/ --world-frame
"""

import argparse
import csv
import json
import os
import sys
import time

import numpy as np
import open3d as o3d

from iphumi.common.trajectory_util import (
    get_open3d_geo_trajectories,
    _step_time_aligned_trajectories_incremental,
)
from iphumi.common.transform_util import pos_quat_xyzw_to_4x4
from iphumi.demonstration_processing.utils.generic_util import (
    get_demonstration_sides_present,
    read_aligned_csv,
)

SIDE_COLORS = {
    'left':  [1.0, 0.2, 0.2],
    'right': [0.2, 0.5, 1.0],
    'head':  [0.2, 0.8, 0.2],
}
_FALLBACK_COLORS = [[0.6, 0.0, 0.6], [1.0, 0.6, 0.0], [0.0, 0.8, 0.8]]


def _color_for(side, idx):
    return SIDE_COLORS.get(side, _FALLBACK_COLORS[idx % len(_FALLBACK_COLORS)])


def _load_json(json_path):
    with open(json_path) as f:
        data = json.load(f)
    return np.array(data['poseTransforms'], dtype=np.float64)  # (T, 4, 4)


def _load_csv(csv_path):
    rows = []
    with open(csv_path, newline='') as f:
        for row in csv.DictReader(f):
            rows.append([
                float(row['x']), float(row['y']), float(row['z']),
                float(row['q_x']), float(row['q_y']), float(row['q_z']), float(row['q_w']),
            ])
    return pos_quat_xyzw_to_4x4(np.array(rows, dtype=np.float64))  # (T, 4, 4)


def main():
    parser = argparse.ArgumentParser(description='View aligned trajectories interactively in Open3D.')
    parser.add_argument('path', help='A .json file, a _aligned.csv file, or a demonstration directory')
    parser.add_argument('--sides', nargs='+', metavar='SIDE',
                        help='Sides to show when path is a demo dir (default: all present)')
    parser.add_argument('--no-tcp', action='store_true',
                        help='Show raw iPhone camera poses instead of TCP poses (head applies a rotation even without --no-tcp)')
    parser.add_argument('--world-frame', action='store_true',
                        help='Show the world coordinate frame at the origin')
    parser.add_argument('--step-through', action='store_true',
                        help='Continuously loop through the trajectory frame by frame')
    parser.add_argument('--fps', type=float, default=30.0,
                        help='Playback speed for --step-through (default: 30)')
    args = parser.parse_args()

    path = args.path
    trajectories = []
    labels = []

    if os.path.isfile(path):
        if path.endswith('.json'):
            poses = _load_json(path)
            side = os.path.splitext(os.path.basename(path))[0]
        elif path.endswith('.csv'):
            poses = _load_csv(path)
            side = os.path.basename(path).replace('_aligned.csv', '')
        else:
            print(f"Unsupported file: {path}. Expected .json or .csv", file=sys.stderr)
            sys.exit(1)
        if not args.no_tcp:
            from iphumi.demonstration_processing.utils.gripper_util import iphone_to_tcp_poses
            poses = iphone_to_tcp_poses(os.path.dirname(path), side, poses)
        trajectories.append(poses)
        labels.append(side)

    elif os.path.isdir(path):
        demo_dir = path
        sides_present = get_demonstration_sides_present(demo_dir)
        sides = args.sides or sides_present

        for side in sides:
            if side not in sides_present:
                print(f"Warning: side '{side}' not present in demonstration, skipping")
                continue

            csv_path = os.path.join(demo_dir, f'{side}_aligned.csv')
            json_path = os.path.join(demo_dir, f'{side}.json')

            if os.path.exists(csv_path):
                poses = read_aligned_csv(demo_dir, side)['poses']
            elif os.path.exists(json_path):
                poses = _load_json(json_path)
            else:
                print(f"Warning: no aligned CSV or JSON found for side '{side}', skipping")
                continue

            if not args.no_tcp:
                from iphumi.demonstration_processing.utils.gripper_util import iphone_to_tcp_poses
                poses = iphone_to_tcp_poses(demo_dir, side, poses)

            trajectories.append(poses)
            labels.append(side)

    else:
        print(f"Path does not exist: {path}", file=sys.stderr)
        sys.exit(1)

    if not trajectories:
        print("No trajectories to display.", file=sys.stderr)
        sys.exit(1)

    print("Trajectories to display:")
    for label, traj in zip(labels, trajectories):
        print(f"  {label}: {traj.shape[0]} frames")

    colors = [_color_for(label, i) for i, label in enumerate(labels)]

    if args.step_through:
        # Truncate all trajectories to the same length for the incremental stepper
        min_T = min(t.shape[0] for t in trajectories)
        if len(set(t.shape[0] for t in trajectories)) > 1:
            print(f"Note: trajectories have different lengths, truncating to {min_T} frames")
        trajectories = [t[:min_T] for t in trajectories]

        material = o3d.visualization.rendering.MaterialRecord()
        material.shader = "defaultUnlit"

        vis = o3d.visualization.Visualizer()
        vis.create_window(window_name='Trajectory Viewer')
        if args.world_frame:
            vis.add_geometry(o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.08))

        frame_dt = 1.0 / args.fps

        while vis.poll_events():
            vis.clear_geometries()
            if args.world_frame:
                vis.add_geometry(o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.08), reset_bounding_box=False)

            stepper = _step_time_aligned_trajectories_incremental(
                False, vis, trajectories, material,
                include_base_frame=False, colors=colors,
            )
            next(stepper)  # initialise

            loop_running = True
            while loop_running:
                t0 = time.monotonic()
                try:
                    next(stepper)
                except StopIteration:
                    loop_running = False
                    break
                vis.update_renderer()
                if not vis.poll_events():
                    sys.exit(0)
                elapsed = time.monotonic() - t0
                remaining = frame_dt - elapsed
                if remaining > 0:
                    time.sleep(remaining)

        vis.destroy_window()

    else:
        # Static view — show full trajectory at once
        all_geometries = []
        if args.world_frame:
            all_geometries.append(o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.08))
        for i, (traj, label) in enumerate(zip(trajectories, labels)):
            geos = get_open3d_geo_trajectories([traj], colors=[colors[i]], include_base_frame=False)
            all_geometries.extend(geos)

        o3d.visualization.draw_geometries(all_geometries, window_name='Trajectory Viewer')


if __name__ == '__main__':
    main()
