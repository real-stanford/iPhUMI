"""Test iPhone camera stream over Ethernet."""

from argparse import ArgumentParser
from multiprocessing import Process

from iphumi.deployment.common.iphone_camera import create_rgb_latency_callback, create_iphone_ethernet_threaded_feed, visualize_single_stream
from iphumi.deployment.common.qr_code_util import dynamic_qr_timecode


def _run_single_stream_process(
    host: str,
    stream_name: str,
    policy_obs: bool,
    max_depth: float,
    log_fps: bool,
    eval_latency: bool,
    window_name: str | None = None,
) -> None:
    """Run a single Ethernet stream (server + visualization) in its own process."""
    feed = create_iphone_ethernet_threaded_feed(
        host=host,
        stream_name=stream_name,
        log_fps=log_fps,
    )
    if eval_latency:
        feed.set_on_frame(create_rgb_latency_callback(stream_name))

    if window_name is None:
        window_name = f"Ethernet Feed ({stream_name})"
    visualize_single_stream(
        feed,
        policy_obs=policy_obs,
        max_depth=max_depth,
        log_fps=log_fps,
        window_name=window_name,
    )


def main():
    parser = ArgumentParser(description="Test iPhone camera stream over Ethernet.")
    parser.add_argument(
        "--hosts",
        nargs="+",
        default=["192.168.123.18"],
        help="Host IP(s) to bind, one per device.",
    )
    parser.add_argument(
        "--streams",
        default=["main", "ultrawide", "depth"],
        nargs="+",
        type=str,
        help="Stream names to visualize (main, ultrawide, depth)",
    )
    parser.add_argument("--eval_latency", action="store_true")
    parser.add_argument(
        "--policy_obs",
        action="store_true",
        help="Resize to policy observation format",
    )
    parser.add_argument("--max_depth", type=float, default=1.0, help="Max depth in meters (for display only)")
    parser.add_argument("--log_fps", type=bool, default=True, help="Log frame rate")
    args = parser.parse_args()

    if args.eval_latency:
        qr_process = Process(target=dynamic_qr_timecode, daemon=False)
        qr_process.start()

        if "depth" in args.streams:
            print("WARNING: eval_latency is not supported for depth streams. Removing depth from streams.")
            args.streams.remove("depth")

    multi_host = len(args.hosts) > 1

    # One process per (host, stream) combination.
    processes: list[Process] = []
    for host_idx, host in enumerate(args.hosts):
        device_label = f"device{host_idx + 1}" if multi_host else None
        for name in args.streams:
            window_name = (
                f"Ethernet Feed ({name}, {device_label})" if device_label else f"Ethernet Feed ({name})"
            )
            p = Process(
                target=_run_single_stream_process,
                args=(
                    host,
                    name,
                    args.policy_obs,
                    args.max_depth,
                    args.log_fps,
                    args.eval_latency,
                    window_name,
                ),
                daemon=False,
            )
            p.start()
            processes.append(p)

    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        for p in processes:
            p.terminate()
        for p in processes:
            p.join()

        if args.eval_latency:
            qr_process.terminate()
            qr_process.join()


if __name__ == "__main__":
    main()
