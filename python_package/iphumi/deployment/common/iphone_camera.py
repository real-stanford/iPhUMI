"""
iPhone camera streams over USB or Ethernet.

Usage:
    from iphumi.deployment.iphone_camera import (
        IPhoneCameraFeed,
        create_iphone_ethernet_threaded_feed,
        visualize_single_stream,
    )

    # Ethernet: single background thread feed for a named stream ("main", "ultrawide", "depth")
    feed = create_iphone_ethernet_threaded_feed(host="192.168.123.18", stream_name="main")
    frame, is_depth = feed.get_blocking()

    # USB: single main thread feed for a named stream ("main", "ultrawide", "depth")
    iphone_usb_receive_loop(stream_name="main")

    # USB: single background thread feed for a named stream ("main", "ultrawide", "depth")
    feed = create_iphone_usb_theaded_feed(stream_name="main")
    frame, is_depth = feed.get_blocking()
"""

from __future__ import annotations

import base64
import logging
import threading
import time
from datetime import datetime
from io import BytesIO
from threading import Event
from typing import Callable, Optional

import cv2
import numpy as np
from PIL import Image

from flask import Flask
from flask_socketio import SocketIO

from iphumi.common.cv_util import get_image_transform_with_border
from iphumi.deployment.common.qr_code_util import read_qr_code
import pypeertalk

# Optional: Flask for Ethernet, pypeertalk for USB (imported where used)
_MAIN_PORT = 5555
_ULTRAWIDE_PORT = 5556
_DEPTH_PORT = 5557
_DEPTH_SHAPE: tuple[int, int] = (240, 320)
TARGET_VIS_FPS = 60.0

# Canonical stream names for known ports (iOS app: 5555=main, 5556=ultrawide, 5557=depth)
_PORT_STREAM_NAMES: dict[int, str] = {
    _MAIN_PORT: "main",
    _ULTRAWIDE_PORT: "ultrawide",
    _DEPTH_PORT: "depth",
}


def _stream_name_for_port(port: int) -> str:
    return _PORT_STREAM_NAMES.get(port, f"port_{port}")


def stream_name_to_port(name: str) -> int:
    """Map a common stream name ('main', 'ultrawide', 'depth') to its port."""
    normalized = name.strip().lower()
    if normalized == "main":
        return _MAIN_PORT
    if normalized == "ultrawide":
        return _ULTRAWIDE_PORT
    if normalized == "depth":
        return _DEPTH_PORT
    raise KeyError(f"Unknown stream name: {name!r}")


# -----------------------------------------------------------------------------
# Shared feed type and visualization
# -----------------------------------------------------------------------------


class IPhoneCameraFeed:
    """Unified feed interface: get_blocking() returns (frame, is_depth).

    Optionally accepts an `on_frame` callback that is invoked whenever a new
    frame is set via `set_frame`. This keeps latency / side-effect logic
    outside of the feed itself.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        on_frame: Optional[Callable[[np.ndarray, bool], None]] = None,
    ):
        self.frame: np.ndarray | None = None
        self.event = Event()
        self.is_depth: bool | None = None
        self.name = name
        self._on_frame = on_frame

    def set_on_frame(self, on_frame: Callable[[np.ndarray, bool], None]):
        self._on_frame = on_frame

    def set_frame(self, frame: np.ndarray, is_depth: bool):
        self.frame = frame
        self.is_depth = is_depth
        self.event.set()
        if self._on_frame is not None:
            try:
                self._on_frame(frame, is_depth)
            except Exception as exc:  # pragma: no cover - defensive
                print(f"IPhoneCameraFeed on_frame callback error: {exc}")

    def get_blocking(self) -> tuple[np.ndarray, bool]:
        """Block until a new frame is available; return (frame, is_depth)."""
        self.event.wait()
        self.event.clear()
        return self.frame, self.is_depth

    def get_latest(self) -> tuple[np.ndarray | None, bool | None]:
        """Return (frame, is_depth) if a new frame is available, else (None, False). Non-blocking."""
        if not self.event.is_set():
            return None, False
        self.event.clear()
        return self.frame, self.is_depth


def _compute_rgb_latency(frame: np.ndarray, frame_received_time: datetime) -> float | None:
    """Compute latency using QR timecode in the image, if present."""
    qr_data = read_qr_code(frame)
    if qr_data:
        try:
            qr_time = datetime.fromisoformat(qr_data)
            return (frame_received_time - qr_time).total_seconds()
        except (ValueError, TypeError):
            return None
    return None


def create_rgb_latency_callback(
    name: Optional[str] = None,
) -> Callable[[np.ndarray, bool], None]:
    """Factory for a per-frame callback that logs RGB latency based on QR code."""

    def _callback(frame: np.ndarray, is_depth: bool) -> None:
        if is_depth:
            return
        received_time = datetime.now()
        latency_seconds = _compute_rgb_latency(frame, received_time)
        if latency_seconds is None:
            return
        prefix = f"[{name}] " if name is not None else ""
        print(f"{prefix}Frame latency: {latency_seconds:.3f} seconds")

    return _callback


def _depth_to_display_single_channel(depth: np.ndarray, max_depth: float) -> np.ndarray:
    """Convert raw float32 depth to uint8 single-channel for display."""
    depth = np.clip(depth, 0, max_depth)
    return (depth / max_depth * 255).astype(np.uint8)


def visualize_single_stream(
    feed: IPhoneCameraFeed,
    *,
    policy_obs: bool = False,
    max_depth: float = 1.0,
    log_fps: bool = True,
    window_name: str = "Camera Feed",
) -> None:
    """Simplified visualization loop for a single stream in one window.

    Press 'q' to quit. Capped at TARGET_VIS_FPS.
    """
    policy_obs_in_res = (320, 240)
    policy_obs_transform = get_image_transform_with_border(
        in_res=policy_obs_in_res, out_res=(224, 224), bgr_to_rgb=False
    )
    frame_period = 1.0 / TARGET_VIS_FPS

    # Show an initial black frame so the window appears even before data arrives.
    placeholder_black = np.zeros((240, 320, 3), dtype=np.uint8)
    cv2.imshow(window_name, placeholder_black)
    cv2.waitKey(1)

    if log_fps:
        display_count = 0
        last_fps_time = time.perf_counter()

    while True:
        frame_start = time.perf_counter()

        im, is_depth = feed.get_latest()
        if im is not None:
            if is_depth:
                # For depth, keep it single-channel for cheaper display.
                im = _depth_to_display_single_channel(im, max_depth)
                cv2.imshow(window_name, im)
            else:
                if policy_obs:
                    if im.shape[:2] != (policy_obs_in_res[1], policy_obs_in_res[0]):
                        im = cv2.resize(im, policy_obs_in_res)
                    im = policy_obs_transform(im)
                if im.ndim == 3 and im.shape[2] == 3:
                    im = im[:, :, ::-1]  # RGB -> BGR for cv2.imshow
                cv2.imshow(window_name, im)

        if log_fps:
            display_count += 1
            now = time.perf_counter()
            elapsed = now - last_fps_time
            if elapsed >= 1.0:
                fps = display_count / elapsed
                print(f"{window_name} visualization frame rate: {fps:.1f} FPS")
                display_count = 0
                last_fps_time = now

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

        elapsed = time.perf_counter() - frame_start
        sleep_time = frame_period - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    cv2.destroyWindow(window_name)

# -----------------------------------------------------------------------------
# Ethernet (Flask-SocketIO server)
# -----------------------------------------------------------------------------


def _decode_rgb_base64_to_numpy(base64_string: str) -> np.ndarray:
    image_data = base64.b64decode(base64_string)
    image = Image.open(BytesIO(image_data))
    return np.array(image)


def _decode_depth_base64_to_float32(base64_string: str, shape: tuple[int, int] = (240, 320)) -> np.ndarray:
    """Decode base64 depth to raw float32 array (no scaling)."""
    depth_bytes = base64.b64decode(base64_string)
    depth_array = np.frombuffer(depth_bytes, dtype=np.float32)
    return depth_array.reshape(shape)


def create_iphone_ethernet_threaded_feed(
    stream_name: str,
    *,
    host: str = "192.168.123.18",
    log_fps: bool = False,
) -> IPhoneCameraFeed:
    """Start a single Ethernet server for the given named stream on a background thread; returns the feed."""
    socket_port = stream_name_to_port(stream_name)
    server_state = IPhoneCameraFeed(name=stream_name)
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)
    app = Flask(__name__)
    # Allow large frames (e.g. high-res JPEG); default 1MB is too small and drops packets.
    socketio = SocketIO(app, max_http_buffer_size=10 * 1024 * 1024, max_decode_packets=500)

    fps_state: list[int | float] = [0, time.perf_counter()]  # [frame_count, last_fps_time]

    def maybe_log_fps():
        if not log_fps:
            return
        fps_state[0] += 1
        now = time.perf_counter()
        elapsed = now - fps_state[1]
        if elapsed >= 1.0:
            fps = fps_state[0] / elapsed
            print(f"Ethernet {stream_name} (port {socket_port}) input frame rate: {fps:.1f} FPS")
            fps_state[0] = 0
            fps_state[1] = now

    @socketio.on("connect")
    def handle_connect():
        print("Client connected")

    @socketio.on("disconnect")
    def handle_disconnect():
        print("Client disconnected")

    @socketio.on("rgb")
    def handle_rgb_message(data):
        image_np = _decode_rgb_base64_to_numpy(data)
        server_state.set_frame(image_np, is_depth=False)
        maybe_log_fps()

    @socketio.on("depth")
    def handle_depth_message(data):
        depth_np = _decode_depth_base64_to_float32(data, shape=_DEPTH_SHAPE)
        server_state.set_frame(depth_np, is_depth=True)
        maybe_log_fps()

    @socketio.on("validate")
    def handle_validate_message(data):
        return "server got it!"

    @socketio.on("kill")
    def handle_kill_message(data):
        socketio.stop()

    def run_server():
        socketio.run(app, host=host, port=socket_port, allow_unsafe_werkzeug=True)

    server_thread = threading.Thread(target=run_server, daemon=False)
    server_thread.start()
    return server_state


# -----------------------------------------------------------------------------
# USB (pypeertalk client)
# -----------------------------------------------------------------------------


def _decode_usb_message(
    data: bytes,
    is_depth: bool,
) -> np.ndarray | None:
    if is_depth:
        depth_array = np.frombuffer(data, dtype=np.float32)
        try:
            return depth_array.reshape(_DEPTH_SHAPE)
        except ValueError:
            return None
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is not None:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return img


def iphone_usb_receive_loop(
    stream_name: str,
    device_udid: str | None,
    output_feed: IPhoneCameraFeed | None,
    log_fps: bool = False,
    visualize: bool = False,
    visualize_window_name: str | None = None,
    visualize_max_depth: float = 1.0,
):
    """Receive loop that reconnects when the device disconnects or errors. Use this if you want to block the current thread.

    If visualize is True, frames are shown directly in an OpenCV window from
    this loop. If feed is not None, frames are also pushed into the feed.
    """
    port = stream_name_to_port(stream_name)
    is_depth = stream_name.strip().lower() == "depth"

    while True:
        devices = pypeertalk.get_connected_devices()
        if not devices:
            continue

        # Select device either by UDID (if provided) or default to first device.
        if device_udid is not None:
            device = next((d for d in devices if getattr(d, "udid", None) == device_udid), None)
            if device is None:
                continue
        else:
            device = devices[0]
        if visualize and visualize_window_name is None:
            visualize_window_name = f"USB {stream_name} (port {port})"
        try:
            client = pypeertalk.PeerTalkClient(device, port, 1)
        except Exception as e:
            print(f"Error creating PeerTalkClient: {e}")
            time.sleep(1)
            continue
        if log_fps:
            frame_count = 0
            last_fps_time = time.perf_counter()
        while True:
            try:
                message = client.get_latest_message(1000)
                if message is None or len(message) == 0:
                    break
                frame = _decode_usb_message(message, is_depth)
                if frame is not None:
                    if output_feed is not None:
                        output_feed.set_frame(frame, is_depth=is_depth)

                    if visualize and visualize_window_name is not None:
                        if is_depth:
                            disp = _depth_to_display_single_channel(frame, visualize_max_depth)
                            cv2.imshow(visualize_window_name, disp)
                        else:
                            disp = frame
                            if disp.ndim == 3 and disp.shape[2] == 3:
                                disp = disp[:, :, ::-1]  # RGB -> BGR
                            cv2.imshow(visualize_window_name, disp)
                        if cv2.waitKey(1) & 0xFF == ord("q"):
                            cv2.destroyWindow(visualize_window_name)
                            return

                    if log_fps:
                        frame_count += 1
                        now = time.perf_counter()
                        elapsed = now - last_fps_time
                        if elapsed >= 1.0:
                            fps = frame_count / elapsed
                            if frame is not None and frame.ndim >= 2:
                                height, width = frame.shape[:2]
                                print(
                                    f"USB {stream_name} (port {port}) frame rate: {fps:.1f} FPS, resolution: {width}x{height}"
                                )
                            else:
                                print(f"USB {stream_name} (port {port}) frame rate: {fps:.1f} FPS")
                            frame_count = 0
                            last_fps_time = now
            except Exception:
                break


def create_iphone_usb_theaded_feed(
    stream_name: str,
    *,
    device_udid: str | None = None,
    log_fps: bool = False,
) -> IPhoneCameraFeed:
    """Create a single USB feed for one stream on a separate thread. Use this if you don't want to block the main thread.
    Note that this does not support the visualization features of iphone_usb_receive_loop because
    it's running on a separate thread and we can only do UI updates on the main thread.
    """
    feed = IPhoneCameraFeed(name=stream_name)
    thread = threading.Thread(
        target=iphone_usb_receive_loop,
        args=(stream_name, device_udid, feed, log_fps),
        daemon=True,
    )
    thread.start()
    return feed
