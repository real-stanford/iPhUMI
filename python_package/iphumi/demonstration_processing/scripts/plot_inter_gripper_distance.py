#!/usr/bin/env python3
"""Plot inter-gripper distance over time for a demonstration directory."""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from iphumi.demonstration_processing.utils.generic_util import read_aligned_csv
from iphumi.demonstration_processing.utils.gripper_util import iphone_to_tcp_poses


def main():
    parser = argparse.ArgumentParser(description="Plot distance between left and right grippers over time.")
    parser.add_argument("demo_dir", type=Path, help="Path to demonstration directory")
    args = parser.parse_args()

    demo_dir = args.demo_dir
    if not demo_dir.is_dir():
        print(f"Error: {demo_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    left_data = read_aligned_csv(str(demo_dir), "left")
    right_data = read_aligned_csv(str(demo_dir), "right")

    left_tcp = iphone_to_tcp_poses(str(demo_dir), "left", left_data["poses"])
    right_tcp = iphone_to_tcp_poses(str(demo_dir), "right", right_data["poses"])

    n = min(len(left_tcp), len(right_tcp))
    left_pos = left_tcp[:n, :3, 3]
    right_pos = right_tcp[:n, :3, 3]

    distance_cm = np.linalg.norm(left_pos - right_pos, axis=1) * 100.0

    left_csv = pd.read_csv(demo_dir / "left_aligned.csv")
    time_s = left_csv["relative_aligned_timestamp"].values[:n]

    # Find the index closest to each integer second
    tick_seconds = np.arange(int(time_s[0]), int(time_s[-1]) + 1)
    tick_indices = [np.argmin(np.abs(time_s - t)) for t in tick_seconds]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(time_s, distance_cm, linewidth=1.5)
    ax.scatter(time_s[tick_indices], distance_cm[tick_indices], color="C0", zorder=5)
    for idx in tick_indices:
        ax.annotate(
            f"{distance_cm[idx]:.1f}",
            xy=(time_s[idx], distance_cm[idx]),
            xytext=(0, 6),
            textcoords="offset points",
            ha="center",
            fontsize=7,
        )
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Distance (cm)")
    ax.set_title(f"Inter-Gripper Distance\n{demo_dir.name}")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    out_path = demo_dir / "inter_gripper_distance.png"
    fig.savefig(out_path, dpi=150)
    print(f"Saved plot to {out_path}")


if __name__ == "__main__":
    main()
