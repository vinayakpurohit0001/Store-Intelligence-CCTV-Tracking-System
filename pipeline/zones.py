import json, numpy as np
import supervision as sv
from pathlib import Path

def load_zones(layout_path: str, camera_id: str):
    '''Load PolygonZone objects from real store_layout.json for a specific camera.
    New format: layout.cameras.CAM_X.zones.ZONE_NAME.polygon
    Returns list of (zone_id, sv.PolygonZone).
    '''
    with open(layout_path) as f:
        layout = json.load(f)

    cameras = layout.get('cameras', {})
    cam_data = cameras.get(camera_id, {})
    zones_data = cam_data.get('zones', {})

    zones = []
    for zone_name, zone_info in zones_data.items():
        polygon = zone_info.get('polygon', [])
        if len(polygon) < 3:
            continue   # skip degenerate polygons
        np_poly = np.array(polygon, dtype=np.int32)
        zones.append((zone_name, sv.PolygonZone(polygon=np_poly)))

    return zones

def get_visitor_zone(cx: float, cy: float, zones: list):
    '''Return zone_id if centroid (cx,cy) is inside any zone polygon.
    Unchanged — still works the same way.
    '''
    for zone_id, pzone in zones:
        det = sv.Detections(xyxy=np.array([[cx-1, cy-1, cx+1, cy+1]])  )
        if pzone.trigger(det):
            return zone_id
    return None

def get_store_id(layout_path: str) -> str:
    '''Helper: read store_id from the layout file.'''
    with open(layout_path) as f:
        return json.load(f).get('store_id', 'STORE_UNKNOWN')

def get_camera_resolution(layout_path: str, camera_id: str):
    '''Helper: return (width, height) for a camera.'''
    with open(layout_path) as f:
        layout = json.load(f)
    cam = layout.get('cameras', {}).get(camera_id, {})
    res = cam.get('frame_resolution', [1920, 1080])
    return res[0], res[1]
