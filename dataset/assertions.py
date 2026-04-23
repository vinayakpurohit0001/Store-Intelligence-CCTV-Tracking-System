import httpx
import time

API_URL = "http://localhost:8000"

def test_health():
    resp = httpx.get(f"{API_URL}/health")
    assert resp.status_code == 200
    assert "status" in resp.json()

def test_ingest_duplicate():
    event = {
        "event_id": "test-uuid-dup",
        "store_id": "STORE_BLR_002",
        "camera_id": "CAM_3",
        "visitor_id": "VIS_TEST",
        "event_type": "ENTRY",
        "timestamp": "2026-03-03T14:22:10Z",
        "zone_id": None,
        "dwell_ms": 0,
        "is_staff": False,
        "confidence": 0.99,
        "metadata": {}
    }
    
    # First ingest
    r1 = httpx.post(f"{API_URL}/events/ingest", json={"events": [event]})
    assert r1.status_code == 200
    
    # Second ingest should be idempotent (200 but maybe dropped or skipped)
    r2 = httpx.post(f"{API_URL}/events/ingest", json={"events": [event]})
    assert r2.status_code == 200

if __name__ == "__main__":
    test_health()
    test_ingest_duplicate()
    print("Dummy assertions passed!")
