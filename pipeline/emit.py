import uuid, json, requests
from datetime import datetime, timezone
from pathlib import Path

API_URL = 'http://127.0.0.1:8000/events/ingest'
JSONL_PATH = Path('data/events_output.jsonl')

def make_event(store_id, camera_id, visitor_id, event_type,
               timestamp_offset_sec, clip_start_utc,
               zone_id=None, dwell_ms=0, is_staff=False,
               confidence=0.9, queue_depth=None, session_seq=1):
    ts = clip_start_utc + __import__('datetime').timedelta(seconds=timestamp_offset_sec)
    return {
        'event_id':   str(uuid.uuid4()),
        'store_id':   store_id,
        'camera_id':  camera_id,
        'visitor_id': visitor_id,
        'event_type': event_type,
        'timestamp':  ts.isoformat().replace('+00:00','Z'),
        'zone_id':    zone_id,
        'dwell_ms':   dwell_ms,
        'is_staff':   is_staff,
        'confidence': round(float(confidence), 4),
        'metadata': {
            'queue_depth':  queue_depth,
            'sku_zone':     zone_id,
            'session_seq':  session_seq
        }
    }

def write_jsonl(events: list):
    JSONL_PATH.parent.mkdir(exist_ok=True)
    with open(JSONL_PATH, 'a') as f:
        for e in events:
            f.write(json.dumps(e) + '\n')

def post_to_api(events: list) -> dict:
    try:
        r = requests.post(API_URL, json={'events': events}, timeout=10)
        return r.json()
    except Exception as ex:
        print(f'[emit] API post failed: {ex}')
        return {}
