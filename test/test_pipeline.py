# PROMPT: Write pytest unit tests for a computer vision pipeline module. Cover: emit schema, staff classifier colour detection, Re-ID embedding similarity and timeline timeouts.
import uuid, json, numpy as np
from datetime import datetime, timezone
from pipeline.emit  import make_event
from pipeline.staff import is_staff
from pipeline.reid  import ReIDGallery

REQUIRED_FIELDS = {
    'event_id','store_id','camera_id','visitor_id',
    'event_type','timestamp','dwell_ms','is_staff','confidence','metadata'
}

def test_make_event_has_all_required_fields():
    e = make_event(
        store_id='STORE_TEST', camera_id='CAM_01',
        visitor_id='VIS_001', event_type='ENTRY',
        timestamp_offset_sec=10.0,
        clip_start_utc=datetime(2026,4,19,9,0,0,tzinfo=timezone.utc)
    )
    assert REQUIRED_FIELDS.issubset(set(e.keys()))

def test_make_event_timestamp_is_iso8601():
    e = make_event(
        store_id='S', camera_id='C', visitor_id='V',
        event_type='EXIT', timestamp_offset_sec=0,
        clip_start_utc=datetime(2026,4,19,9,0,0,tzinfo=timezone.utc)
    )
    # Must parse without error
    datetime.fromisoformat(e['timestamp'].replace('Z','+00:00'))

def test_staff_classifier_black_is_staff():
    import cv2
    frame = np.zeros((200,100,3), dtype=np.uint8)
    assert is_staff(frame, np.array([0,0,100,200])) == True

def test_staff_classifier_customer_not_staff():
    frame = np.full((200,100,3), 180, dtype=np.uint8)  # mid-grey
    assert is_staff(frame, np.array([0,0,100,200])) == False

def test_reid_gallery_identical_crop_matches():
    gallery = ReIDGallery(threshold=0.5)
    crop = np.random.randint(0, 255, (128,64,3), dtype=np.uint8)
    gallery.add('VIS_001', crop)
    gallery.mark_exit('VIS_001', 0.0)
    matched, sim = gallery.match(crop, 30.0)
    assert matched == 'VIS_001'
    assert sim > 0.99

def test_reid_gallery_no_match_below_threshold():
    gallery = ReIDGallery(threshold=0.99)  # very high threshold
    crop1 = np.random.randint(0, 255, (128,64,3), dtype=np.uint8)
    crop2 = np.random.randint(0, 255, (128,64,3), dtype=np.uint8)
    gallery.add('VIS_001', crop1)
    gallery.mark_exit('VIS_001', 0.0)
    matched, sim = gallery.match(crop2, 30.0)
    assert matched is None

def test_reid_gallery_no_match_outside_reentry_window():
    gallery = ReIDGallery(threshold=0.5, reentry_window_sec=60)
    crop = np.random.randint(0, 255, (128,64,3), dtype=np.uint8)
    gallery.add('VIS_001', crop)
    gallery.mark_exit('VIS_001', 0.0)
    # Query at 120 sec — outside 60-sec window
    matched, sim = gallery.match(crop, 120.0)
    assert matched is None
