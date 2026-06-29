# adapted from `detect_aruco.py` from UMI

import json
import os

from tqdm import tqdm
import yaml
import av
import numpy as np
import cv2
from typing import Dict

from iphumi.demonstration_processing.utils.cv_util import (
    parse_aruco_config,
)


def run_detection(
    input: str,
    output: str,
    ultrawideIntrinsics: np.ndarray,
    aruco_yaml: str,
    num_workers: int = 4,
    time_offset: float = 0.0,
) -> None:
    """Core AR tag detection routine, callable from Python or CLI."""
    cv2.setNumThreads(num_workers)

    # load aruco config
    aruco_config = parse_aruco_config(yaml.safe_load(open(aruco_yaml, 'r')))
    aruco_dict = aruco_config['aruco_dict']
    marker_size_map = aruco_config['marker_size_map']

    # load intrinsics
    K = np.array(ultrawideIntrinsics)

    results = list()
    with av.open(os.path.expanduser(input)) as in_container:
        in_stream = in_container.streams.video[0]
        in_stream.thread_type = "AUTO"
        in_stream.thread_count = num_workers

        in_res = np.array([in_stream.height, in_stream.width])[::-1]

        for i, frame in tqdm(enumerate(in_container.decode(in_stream)), total=in_stream.frames):
            img = frame.to_ndarray(format='rgb24')
            frame_cts_sec = frame.pts * in_stream.time_base
            tag_dict = detect_localize_aruco_tags_iphone(
                img=img,
                aruco_dict=aruco_dict,
                marker_size_map=marker_size_map,
                K=K,
                refine_subpix=True
            )
            result = {
                'frame_idx': i,
                'time': float(frame_cts_sec) + time_offset,
                'tag_dict': {
                    tag_id: {
                        'rvec': data['rvec'].tolist(),
                        'tvec': data['tvec'].tolist(),
                        'corners': data['corners'].tolist(),
                    }
                    for tag_id, data in tag_dict.items()
                }
            }
            results.append(result)

    with open(os.path.expanduser(output), 'w') as f:
        json.dump(results, f, indent=2)

def detect_localize_aruco_tags_iphone(
        img: np.ndarray, 
        aruco_dict: cv2.aruco.Dictionary, 
        marker_size_map: Dict[int, float], 
        K: np.ndarray,
        refine_subpix: bool=True):
    param = cv2.aruco.DetectorParameters()
    if refine_subpix:
        param.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector = cv2.aruco.ArucoDetector(dictionary=aruco_dict, detectorParams=param)
    corners, ids, rejectedImgPoints = detector.detectMarkers(image=img)
    if len(corners) == 0:
        return dict()

    tag_dict = dict()
    for this_id, this_corners in zip(ids, corners):
        this_id = int(this_id[0])
        if this_id not in marker_size_map:
            continue
        
        marker_size_m = marker_size_map[this_id]
        # Create 3D object points for the marker (centered at origin, in XY plane)
        # ArUco marker coordinate system: top-left, top-right, bottom-right, bottom-left
        obj_points = np.array([
            [-marker_size_m/2, marker_size_m/2, 0],  # top-left
            [marker_size_m/2, marker_size_m/2, 0],   # top-right
            [marker_size_m/2, -marker_size_m/2, 0],  # bottom-right
            [-marker_size_m/2, -marker_size_m/2, 0]  # bottom-left
        ], dtype=np.float32)
        
        # Reshape corners to (4, 2) for solvePnP
        img_points = this_corners.reshape(-1, 2).astype(np.float32)
        
        # Use solvePnP instead of estimatePoseSingleMarkers
        dist_coeffs = np.zeros((5, 1), dtype=np.float32)
        success, rvec, tvec = cv2.solvePnP(
            obj_points, img_points, K, dist_coeffs
        )
        
        if not success:
            continue
            
        tag_dict[this_id] = {
            'rvec': rvec.squeeze(),
            'tvec': tvec.squeeze(),
            'corners': this_corners.squeeze()
        }
    return tag_dict
