# Adapted from `cv_util.py` from UMI
import cv2
import numpy as np

# ================= ArUcO tag =====================
def parse_aruco_config(aruco_config_dict: dict):
    """
    example:
    aruco_dict:
        predefined: DICT_4X4_50
    marker_size_map: # all unit in meters
        default: 0.15
        12: 0.2
    """
    aruco_dict = get_aruco_dict(**aruco_config_dict['aruco_dict'])

    n_markers = len(aruco_dict.bytesList)
    marker_size_map = aruco_config_dict['marker_size_map']
    default_size = marker_size_map.get('default', None)
    
    out_marker_size_map = dict()
    for marker_id in range(n_markers):
        size = default_size
        if marker_id in marker_size_map:
            size = marker_size_map[marker_id]
        out_marker_size_map[marker_id] = size
    
    result = {
        'aruco_dict': aruco_dict,
        'marker_size_map': out_marker_size_map
    }
    return result

def get_aruco_dict(predefined:str
                   ) -> cv2.aruco.Dictionary:
    return cv2.aruco.getPredefinedDictionary(
        getattr(cv2.aruco, predefined))
