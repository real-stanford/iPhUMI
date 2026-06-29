import cv2
import numpy as np


def get_image_transform_with_border(in_res, out_res, mode="rgb", bgr_to_rgb: bool = False):
    """Pad to a square canvas and resize while preserving the image center."""
    iw, ih = in_res
    interp_method = cv2.INTER_AREA
    if mode in {"depth", "pointmap"}:
        # Avoid interpolating invalid depth or 3-D points across empty regions.
        interp_method = cv2.INTER_NEAREST

    size = max(iw, ih)
    top = (size - ih) // 2
    bottom = size - ih - top
    left = (size - iw) // 2
    right = size - iw - left

    def transform(img: np.ndarray):
        if mode == "rgb":
            assert img.shape == (ih, iw, 3)
            resized = cv2.copyMakeBorder(
                img,
                top,
                bottom,
                left,
                right,
                cv2.BORDER_CONSTANT,
                value=[0, 0, 0],
            )
            resized = cv2.resize(resized, out_res, interpolation=interp_method)
            if bgr_to_rgb:
                resized = resized[:, :, ::-1]
            return resized

        if mode == "depth":
            assert img.shape == (ih, iw)
            padded = cv2.copyMakeBorder(
                img.astype(np.float32, copy=False),
                top,
                bottom,
                left,
                right,
                cv2.BORDER_CONSTANT,
                value=0,
            )
            return cv2.resize(padded, out_res, interpolation=interp_method).astype(np.float16)

        if mode == "pointmap":
            assert img.shape == (ih, iw, 3)
            padded = cv2.copyMakeBorder(
                img.astype(np.float32, copy=False),
                top,
                bottom,
                left,
                right,
                cv2.BORDER_CONSTANT,
                value=[0, 0, 0],
            )
            return cv2.resize(padded, out_res, interpolation=interp_method).astype(np.float16)

        raise ValueError(f"Unsupported transform mode: {mode}")

    return transform


def depth2xyzmap(depth: np.ndarray, intrinsic: np.ndarray, uvs: np.ndarray = None) -> np.ndarray:
    """Project a depth image into an xyz map in the camera frame."""
    height, width = depth.shape[:2]
    if uvs is None:
        vs, us = np.meshgrid(
            np.arange(height, dtype=np.int32),
            np.arange(width, dtype=np.int32),
            indexing="ij",
        )
        us = us.reshape(-1)
        vs = vs.reshape(-1)
    else:
        uvs = np.asarray(uvs).round().astype(np.int32)
        us = uvs[:, 0]
        vs = uvs[:, 1]

    depth_values = depth[vs, us].astype(np.float32, copy=False)
    xs = (us - intrinsic[0, 2]) * depth_values / intrinsic[0, 0]
    ys = (vs - intrinsic[1, 2]) * depth_values / intrinsic[1, 1]
    xyz = np.stack((xs, ys, depth_values), axis=-1)

    xyz_map = np.zeros((height, width, 3), dtype=np.float16)
    xyz_map[vs, us] = xyz.astype(np.float16)
    return xyz_map
