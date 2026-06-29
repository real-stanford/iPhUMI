import numpy as np


def compute_center_lookat_from_pointmap(pointmap: np.ndarray, top_k: int = 50) -> np.ndarray:
    """Approximate a center look-at target from the closest valid rays in the pointmap."""
    if pointmap is None:
        raise ValueError("pointmap cannot be None")

    points = np.asarray(pointmap)
    dtype = points.dtype if np.issubdtype(points.dtype, np.floating) else np.float16
    if points.size == 0:
        return np.zeros(3, dtype=dtype)

    flat = points.reshape(-1, 3)
    valid_mask = (flat[:, 2] > 0) & np.isfinite(flat).all(axis=1)
    if not np.any(valid_mask):
        return np.zeros(3, dtype=dtype)

    valid_points = flat[valid_mask]
    radial_distance = (valid_points[:, 0] ** 2) + (valid_points[:, 1] ** 2)
    k = min(top_k, len(valid_points))
    closest_idx = np.argpartition(radial_distance, k - 1)[:k]
    median_z = np.median(valid_points[closest_idx, 2])

    result = np.zeros(3, dtype=np.float16)
    result[2] = float(median_z)
    return result.astype(dtype)
