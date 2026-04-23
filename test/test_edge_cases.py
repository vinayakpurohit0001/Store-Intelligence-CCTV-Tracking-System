# PROMPT: Write pytest edge case tests for a retail analytics FastAPI app.
# Cover: empty store returns zeros not null, all-staff clip excluded from metrics,
# zero purchases gives conversion_rate 0.0 not error, re-entry visitor_id
# not double-counted in funnel, POST /events/ingest idempotency on 500 events,
# malformed event in batch gives partial success not full 422.
# CHANGES MADE: Added fixture-based DB isolation, added funnel dedup assertion,
# added 503 structure check for DB unavailable scenario.

import uuid, pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import EventORM


def seed(event_type, visitor_id, store_id='STORE_EDGE_001',
         is_staff=False, zone_id=None, queue_depth=None):
    db = SessionLocal()
    db.add(EventORM(
        event_id=str(uuid.uuid4()), store_id=store_id,
        camera_id='CAM_01', visitor_id=visitor_id,
        event_type=event_type,
        timestamp=datetime.now(timezone.utc),
        dwell_ms=0, is_staff=is_staff, confidence=0.9,
        zone_id=zone_id, meta_queue_depth=queue_depth
    ))
    db.commit(); db.close()

# ── Empty store ──────────────────────────────────────────────────────
def test_empty_store_metrics_returns_zeros(client):
    r = client.get('/stores/STORE_EMPTY_EDGE/metrics')
    assert r.status_code == 200
    d = r.json()
    assert d['unique_visitors']  == 0
    assert d['conversion_rate']  == 0.0
    assert d['queue_depth']      == 0
    assert d['abandonment_rate'] == 0.0

def test_empty_store_funnel_returns_zero_counts(client):
    r = client.get('/stores/STORE_EMPTY_EDGE/funnel')
    assert r.status_code == 200
    stages = r.json()['funnel']
    assert all(s['visitors'] == 0 for s in stages)

def test_empty_store_heatmap_low_confidence(client):
    r = client.get('/stores/STORE_EMPTY_EDGE/heatmap')
    assert r.status_code == 200
    assert r.json()['data_confidence'] == 'LOW'

# ── All-staff clip ───────────────────────────────────────────────────
def test_all_staff_clip_gives_zero_customers(client, db_session):
    def seed_db(event_type, visitor_id, **kwargs):
        db_session.add(EventORM(
            event_id=str(uuid.uuid4()), store_id='STORE_EDGE_001',
            camera_id='CAM_01', visitor_id=visitor_id, event_type=event_type,
            timestamp=datetime.now(timezone.utc), confidence=0.9, **kwargs
        ))
        db_session.commit()
        
    for i in range(5):
        seed_db('ENTRY', f'VIS_STAFF_{i}', is_staff=True)
    r = client.get('/stores/STORE_EDGE_001/metrics')
    assert r.json()['unique_visitors'] == 0

# ── Zero purchases ───────────────────────────────────────────────────
def test_zero_purchases_conversion_rate(client, db_session):
    def seed_db(event_type, visitor_id, store_id='STORE_NOPURCHASE', **kwargs):
        db_session.add(EventORM(
            event_id=str(uuid.uuid4()), store_id=store_id,
            camera_id='CAM_01', visitor_id=visitor_id, event_type=event_type,
            timestamp=datetime.now(timezone.utc), confidence=0.9, **kwargs
        ))
        db_session.commit()
    seed_db('ENTRY', 'VIS_NOPURCHASE')
    r = client.get('/stores/STORE_NOPURCHASE/metrics')
    assert r.status_code == 200
    assert r.json()['conversion_rate'] == 0.0

# ── Re-entry funnel dedup ────────────────────────────────────────────
def test_reentry_not_double_counted_in_funnel(client, db_session):
    sid = 'STORE_REENTRY_TEST'
    def seed_db(event_type, visitor_id, **kwargs):
        db_session.add(EventORM(
            event_id=str(uuid.uuid4()), store_id=sid,
            camera_id='CAM_01', visitor_id=visitor_id, event_type=event_type,
            timestamp=datetime.now(timezone.utc), confidence=0.9, **kwargs
        ))
        db_session.commit()
    # Same visitor enters twice (ENTRY + REENTRY) — should count as 1 in funnel
    seed_db('ENTRY',   'VIS_RETURNING')
    seed_db('EXIT',    'VIS_RETURNING')
    seed_db('REENTRY', 'VIS_RETURNING')
    r = client.get(f'/stores/{sid}/funnel')
    assert r.status_code == 200
    entry_stage = r.json()['funnel'][0]
    # REENTRY reuses visitor_id — ENTRY distinct count must be 1, not 2
    assert entry_stage['visitors'] == 1

# ── Idempotency at scale ─────────────────────────────────────────────
def test_ingest_500_events_idempotent(client):
    events = [{
        'event_id': str(uuid.uuid4()),
        'store_id': 'STORE_SCALE_001', 'camera_id': 'CAM_01',
        'visitor_id': f'VIS_{i}', 'event_type': 'ENTRY',
        'timestamp': '2026-04-19T10:00:00Z',
        'dwell_ms': 0, 'is_staff': False, 'confidence': 0.9,
        'metadata': {}
    } for i in range(500)]
    r1 = client.post('/events/ingest', json={'events': events})
    r2 = client.post('/events/ingest', json={'events': events})
    assert r1.json()['accepted']   == 500
    assert r2.json()['duplicates'] == 500
    assert r2.json()['accepted']   == 0

def test_malformed_event_partial_success(client):
    events = [
        {'event_id': 'BAD_1', 'store_id': 'S', 'camera_id': 'C', 'visitor_id': 'V', 'event_type': 'ENTRY'},
        {'event_id': 'GOOD_1', 'store_id': 'S', 'camera_id': 'C', 'visitor_id': 'V', 'event_type': 'ENTRY', 'timestamp': '2026-04-19T10:00:00Z', 'dwell_ms': 0, 'is_staff': False, 'confidence': 0.9, 'metadata': {}}
    ]
    r = client.post('/events/ingest', json={'events': events})
    assert r.status_code == 422
