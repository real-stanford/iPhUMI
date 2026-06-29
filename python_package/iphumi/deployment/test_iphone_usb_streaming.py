"""Test iPhone camera stream over USB."""

import time
from argparse import ArgumentParser
from multiprocessing import Process

import pypeertalk

from iphumi.deployment.common.iphone_camera import IPhoneCameraFeed, create_rgb_latency_callback, iphone_usb_receive_loop
from iphumi.deployment.common.qr_code_util import dynamic_qr_timecode


def _run_single_stream_process(
    stream_name: str,
    max_depth: float,
    log_fps: bool,
    eval_latency: bool,
    device_udid: str | None = None,
    window_name: str | None = None,
) -> None:
    """Run USB receive loop and visualization for a single stream in its own process."""
    if window_name is None:
        window_name = f"Camera Feed ({stream_name})"

    feed: IPhoneCameraFeed | None = None
    if eval_latency:
        feed = IPhoneCameraFeed(name=stream_name)
        feed.set_on_frame(create_rgb_latency_callback(stream_name))

    iphone_usb_receive_loop(
        stream_name=stream_name,
        device_udid=device_udid,
        output_feed=feed,
        log_fps=log_fps,
        visualize=True,
        visualize_window_name=window_name,
        visualize_max_depth=max_depth,
    )


def _wait_for_devices(n: int) -> list[str]:
    """Poll until at least n devices are connected; return their UDIDs."""
    print(f"Waiting for {n} device(s) to connect...")
    while True:
        devices = pypeertalk.get_connected_devices()
        udids = [getattr(d, "udid", None) for d in devices]
        udids = [u for u in udids if u is not None]
        if len(udids) >= n:
            found = udids[:n]
            print(f"Found {n} device(s): {found}")
            return found
        print(f"  {len(udids)}/{n} device(s) connected, retrying...")
        time.sleep(1)


def main():
    parser = ArgumentParser(description="Test iPhone camera stream over USB.")
    parser.add_argument(
        "--streams",
        default=["main", "ultrawide", "depth"],
        nargs="+",
        type=str,
        help="Stream names to visualize (main, ultrawide, depth)",
    )
    parser.add_argument(
        "--devices",
        type=int,
        default=1,
        help="Number of iPhones to stream from. When >1, waits for that many devices before starting. Cannot be used with --ids.",
    )
    parser.add_argument(
        "--ids",
        nargs="+",
        type=str,
        default=None,
        help="Explicit device UDIDs to stream from. Infers device count; cannot be used with --devices.",
    )
    parser.add_argument(
        "--get-ids",
        action="store_true",
        help="Print all currently connected device UDIDs and exit.",
    )
    parser.add_argument("--eval_latency", action="store_true")
    parser.add_argument("--max_depth", type=float, default=1.0, help="Max depth in meters (for display only)")
    parser.add_argument("--log_fps", type=bool, default=True, help="Log frame rate")
    args = parser.parse_args()

    if args.get_ids:
        devices = pypeertalk.get_connected_devices()
        udids = [getattr(d, "udid", None) for d in devices]
        udids = [u for u in udids if u is not None]
        if udids:
            for u in udids:
                print(u)
        else:
            print("No devices connected.")
        return

    if args.ids is not None and args.devices != 1:
        parser.error("--ids and --devices are mutually exclusive.")

    if args.eval_latency:
        qr_process = Process(target=dynamic_qr_timecode, daemon=False)
        qr_process.start()

        if "depth" in args.streams:
            print("WARNING: eval_latency is not supported for depth streams. Removing depth from streams.")
            args.streams.remove("depth")

    # Resolve device UDIDs.
    if args.ids is not None:
        device_udids: list[str | None] = list(args.ids)
    elif args.devices > 1:
        device_udids = _wait_for_devices(args.devices)
    else:
        device_udids = [None]

    # One process per (device, stream) combination.
    processes: list[Process] = []
    for device_idx, udid in enumerate(device_udids):
        device_label = f"device{device_idx + 1}" if len(device_udids) > 1 else None
        for name in args.streams:
            window_name = (
                f"Camera Feed ({name}, {device_label})" if device_label else f"Camera Feed ({name})"
            )
            p = Process(
                target=_run_single_stream_process,
                args=(
                    name,
                    args.max_depth,
                    args.log_fps,
                    args.eval_latency,
                    udid,
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
