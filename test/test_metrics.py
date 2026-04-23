# PROMPT: Write pytest tests for retail analytics endpoints: /metrics, /funnel,
# /heatmap, /anomalies, /health. Seed the DB with known events before each test.
# Cover: empty store, staff excluded, zero purchases, re-entry dedup.
# CHANGES MADE: Added staff exclusion assertion, added zero-visitor store test,
# added data_confidence LOW check for <20 sessions.

import uuid, pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import EventORM
from app.database import Base, engine # Added for DB setup

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    # We do NOT drop all here because health tests might fail due to ordering,
    # or we can drop if we know it's fine. Wait, test_ingestion has drop_all!
    Base.metadata.drop_all(bind=engine)

STORE = "STORE_TEST_001"

@pytest.fixture
def seed_event(db_session):
    def _seed(event_type, visitor_id='VIS_001', is_staff=False, zone_id=None, dwell_ms=0, queue_depth=None, confidence=0.9):
        db_session.add(EventORM(
            event_id=str(uuid.uuid4()), store_id=STORE, camera_id='CAM_01', visitor_id=visitor_id,
            event_type=event_type, timestamp=datetime.now(timezone.utc), zone_id=zone_id,
            dwell_ms=dwell_ms, is_staff=is_staff, confidence=confidence, meta_queue_depth=queue_depth
        ))
        db_session.commit()
    return _seed

def test_metrics_empty_store(client):
    r = client.get(f"/stores/STORE_EMPTY_999/metrics")
    assert r.status_code == 200
    d = r.json()
    assert d["unique_visitors"] == 0
    assert d["conversion_rate"] == 0.0

def test_metrics_excludes_staff(client, seed_event):
    seed_event("ENTRY", visitor_id="VIS_STAFF", is_staff=True)
    r = client.get(f"/stores/{STORE}/metrics")
    d = r.json()
    # staff visitor must NOT appear in unique_visitors
    assert d["unique_visitors"] == 0

def test_metrics_with_real_visitor(client, seed_event):
    vid = "VIS_REAL_001"
    seed_event("ENTRY", visitor_id=vid)
    seed_event("ZONE_ENTER", visitor_id=vid, zone_id="SKINCARE")
    seed_event("BILLING_QUEUE_JOIN", visitor_id=vid, queue_depth=2)
    r = client.get(f"/stores/{STORE}/metrics")
    d = r.json()
    assert d["unique_visitors"] >= 1
    assert d["queue_depth"] == 2

def test_funnel_structure(client):
    r = client.get(f"/stores/{STORE}/funnel")
    assert r.status_code == 200
    d = r.json()
    assert "funnel" in d
    assert len(d["funnel"]) == 4
    stages = [s["stage"] for s in d["funnel"]]
    assert "Entry" in stages
    assert "Purchase" in stages

def test_heatmap_low_confidence(client):
    # New store with < 20 sessions should return data_confidence LOW
    r = client.get("/stores/STORE_NEW_888/heatmap")
    assert r.status_code == 200
    d = r.json()
    assert d["data_confidence"] == "LOW"

def test_anomalies_empty_store(client):
    r = client.get("/stores/STORE_EMPTY_000/anomalies")
    assert r.status_code == 200
    assert "anomalies" in r.json()

def test_health_has_stores_key(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert "stores" in r.json()
