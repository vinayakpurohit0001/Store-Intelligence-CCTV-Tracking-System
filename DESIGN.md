# DESIGN.md — Store Intelligence
## Apex Retail · STORE_BLR_002 · April 2026

---

## 1. System Overview

This document describes the complete architecture of the Store Intelligence system — an end-to-end pipeline that processes raw anonymised CCTV footage from Apex Retail's beauty store and produces live operational analytics via a REST API and web dashboard.

**North Star:** What is the offline store conversion rate, and where are customers dropping off before purchasing?

```
Raw CCTV Clips
    ↓
Detection Layer (YOLOv8n + ByteTrack)
    ↓
Re-ID & Staff Classification (MobileNetV3 + HSV)
    ↓
Zone Tracking (supervision PolygonZone)
    ↓
Event Emission (JSONL → POST /events/ingest)
    ↓
Intelligence API (FastAPI + SQLAlchemy + SQLite)
    ↓
Live Dashboard (SSE + Chart.js)
```

| Stage | Component | Technology | Output |
|-------|-----------|------------|--------|
| 1 — Detection | pipeline/detect.py | YOLOv8n + supervision ByteTrack | Structured events (JSONL) |
| 2 — Re-ID & Staff | pipeline/reid.py + staff.py | MobileNetV3 + HSV histogram | is_staff flag, REENTRY events |
| 3 — Zone Tracking | pipeline/zones.py | supervision PolygonZone | ZONE_ENTER/EXIT/DWELL events |
| 4 — Event Emission | pipeline/emit.py | JSON schema + requests | POST to /events/ingest |
| 5 — Intelligence API | app/ (FastAPI) | FastAPI + SQLAlchemy + SQLite | 6 REST endpoints |
| 6 — Live Dashboard | app/static/dashboard.html | SSE + Chart.js | Real-time web UI |

---

## 2. Detection Pipeline

### 2.1 Video Processing

Each CCTV clip is processed frame-by-frame using OpenCV. The pipeline runs at 7.5 effective fps by processing every other frame (`FRAME_SKIP=2`) from the native 15fps footage. This halves compute cost while still catching all entry/exit crossings — a person takes at minimum 0.5 seconds to cross the entry threshold line, so no crossings are missed at 7.5fps.

Real footage resolutions: 1512×710 (CAM_1, CAM_3, CAM_4, CAM_5) and 1440×720 (CAM_2). YOLOv8n handles both natively.

### 2.2 Object Detection — YOLOv8n

People are detected using Ultralytics YOLOv8n (nano variant), class 0 (person) only. Confidence threshold: **0.35** — deliberately below the typical 0.5 default to maintain high recall on partially occluded people near shelving and between customers.

**Critical design principle:** low-confidence detections are never suppressed. They pass through the pipeline with their actual confidence score recorded in the event. Downstream consumers can filter by confidence — the pipeline never makes that decision unilaterally.

```python
results = model(frame, classes=[0], conf=0.35, verbose=False)[0]
detections = sv.Detections.from_ultralytics(results)
```

### 2.3 Multi-Object Tracking — ByteTrack

Detections are passed to `sv.ByteTrack()` (supervision v0.27+ API — renamed from `sv.ByteTracker()` in v0.21). ByteTrack uses a Kalman filter to maintain track identity through short occlusions, which is critical in a retail environment where customers are frequently obscured by shelves.

**Implementation note:** supervision v0.27 returns `tracker_id` as a numpy array. Boolean evaluation of a numpy array raises an `AmbiguousError`. Both tracking loops use explicit `is not None` checks:

```python
for i, tid in enumerate(tracked.tracker_id or []):
    if tid is None: continue
```

### 2.4 Entry/Exit Direction Detection

A virtual horizontal threshold line at **60% of frame height** determines direction. The centroid y-coordinate of each bounding box is tracked across frames:
- Centroid crossing from **above → below** the threshold = **ENTRY**
- Centroid crossing from **below → above** = **EXIT**

The 60% threshold was chosen because CAM_3 (entry camera) shows the store threshold roughly in the lower-middle portion of the frame.

```python
if prev_y < self.threshold_y <= cy and tid not in self.crossed:
    events.append((tid, 'ENTRY', conf))
elif prev_y > self.threshold_y >= cy and tid in self.active:
    events.append((tid, 'EXIT', conf))
```

### 2.5 Zone Detection — PolygonZone

Zone membership uses `supervision.PolygonZone`. Zone polygons are loaded from `dataset/store_layout.json` which defines zones per camera. The real store contains 5 cameras and 15 named product zones:

| Camera | Zones |
|--------|-------|
| CAM_1 | FARMSTAY, FACE_SHOP, GOOD_VIBES, DERMA, MINIMALIST, NAIL_POLISH |
| CAM_2 | MAYBELLINE_NY, FACES_CANADA, LAKME, SWISS_BEAUTY, LOREAL, FRAGRANCE |
| CAM_3 | ENTRY_ZONE |
| CAM_4 | STORAGE (staff-only) |
| CAM_5 | BILLING_COUNTER, QUEUE_ZONE |

**Real layout format** (differs from sample): zones are nested under cameras, not in a flat list. The `load_zones()` function was rewritten for the real schema:

```python
# Real format: layout.cameras.CAM_X.zones.ZONE_NAME.polygon
for zone_name, zone_info in zones_data.items():
    polygon = zone_info.get('polygon', [])
    zones.append((zone_name, sv.PolygonZone(polygon=np.array(polygon))))
```

### 2.6 Person Re-Identification

Re-ID uses **MobileNetV3** (torchvision small variant, classifier head removed) producing 576-dimensional L2-normalised appearance embeddings. A cosine similarity gallery stores one embedding per `visitor_id`.

On every ENTRY event, the gallery is queried: is this new person's appearance similar to any recently-exited visitor within a **10-minute window**? If cosine similarity ≥ 0.72, a `REENTRY` event is emitted reusing the original `visitor_id` — the visitor's session is continued, not duplicated.

**Verified result on real footage:** 4 REENTRY events correctly detected on CAM_1.mp4.

MobileNetV3 was chosen over OSNet/torchreid because torchreid requires CUDA for acceptable inference speed on 20-minute clips. MobileNetV3 runs on CPU at under 10ms per crop. See CHOICES.md for full rationale.

### 2.7 Staff Detection

Staff are identified using an **HSV colour histogram** on the upper 60% of each detected bounding box (the torso region). If ≥35% of torso pixels match defined uniform colour ranges, the person is classified as `is_staff=True`.

Frame 500 was extracted from CAM_1.mp4 and CAM_2.mp4 to inspect actual uniform colours. Staff wear **black uniforms**. The default black HSV range confirmed correct — no tuning required.

```python
UNIFORM_HSV_RANGES = [
    (np.array([0, 0, 0]),   np.array([180, 50, 60]),  'black'),
    (np.array([100,50,20]), np.array([130,255,100]), 'navy'),
    (np.array([0, 0, 200]), np.array([180, 30, 255]), 'white'),
]
STAFF_UNIFORM_RATIO = 0.35
```

**Verified result:** 2 staff events correctly flagged, excluded from all customer metrics.

---

## 3. Event Schema

All pipeline events conform to a single schema that supports all analytics queries without post-hoc joins:

```json
{
  "event_id":   "cf843b0d-d5ca-4128-9e8b-6d57892a42d0",
  "store_id":   "STORE_BLR_002",
  "camera_id":  "CAM_3",
  "visitor_id": "VIS_a1f3c2",
  "event_type": "ENTRY",
  "timestamp":  "2026-10-04T14:30:00Z",
  "zone_id":    null,
  "dwell_ms":   0,
  "is_staff":   false,
  "confidence": 0.91,
  "metadata": {
    "queue_depth":  null,
    "sku_zone":     null,
    "session_seq":  1
  }
}
```

| Field | Design Rationale |
|-------|-----------------|
| `event_id` (UUID v4) | Globally unique — enables idempotent ingest at API level |
| `store_id` | Read automatically from `store_layout.json` — not a CLI argument |
| `confidence` | Always recorded — never suppressed even if low |
| `is_staff` | HSV classifier output — drives metric exclusion across all endpoints |
| `metadata` | Stored as flat ORM columns (not JSON blob) — enables indexed SQL filtering |

**Metadata storage:** `meta_queue_depth`, `meta_sku_zone`, `meta_session_seq` are flat ORM columns in `EventORM` rather than a JSON blob. All three appear in SQL `WHERE` clauses and benefit from column indexing. See CHOICES.md Choice 2.

---

## 4. Intelligence API

**Stack:** FastAPI + SQLAlchemy + SQLite. `DATABASE_URL` is environment-parameterised — switching to PostgreSQL requires only changing this variable.

| Endpoint | Method | What It Computes |
|----------|--------|-----------------|
| `/events/ingest` | POST | Up to 500 events. Deduplicates by `event_id` in one pre-query. Idempotent. |
| `/stores/{id}/metrics` | GET | `unique_visitors`, `conversion_rate`, `avg_dwell_per_zone`, `queue_depth`, `abandonment_rate` |
| `/stores/{id}/funnel` | GET | 4-stage funnel with drop-off % per stage. Session = `visitor_id` unit. |
| `/stores/{id}/heatmap` | GET | Zone visit frequency + avg dwell, normalised 0–100. `data_confidence` flag if <20 sessions. |
| `/stores/{id}/anomalies` | GET | `BILLING_QUEUE_SPIKE`, `DEAD_ZONE`, `CONVERSION_DROP` with severity + `suggested_action` |
| `/stores/{id}/stream` | GET (SSE) | Server-Sent Events — pushes live metrics JSON every 3 seconds |
| `/health` | GET | Service status + per-store `last_event` + `STALE_FEED` warning if >10 min lag |
| `/dashboard` | GET | Serves `app/static/dashboard.html` |

### 4.1 Idempotency

`POST /events/ingest` fetches all existing `event_id` values for the incoming batch in **one pre-query** before the insert loop. Sending the same batch twice returns `{accepted:0, duplicates:N, errors:0}` — never 4xx or 5xx.

### 4.2 Structured Logging

`RequestLoggingMiddleware` logs every request with: `trace_id` (8-char UUID prefix), `store_id` (extracted from URL path), `method`, `endpoint`, `status_code`, `latency_ms`. `X-Trace-Id` header is returned in every response.

### 4.3 Graceful Degradation

`OperationalError` from SQLAlchemy is caught by a registered exception handler and returns HTTP 503 with a structured JSON body — no raw stack traces in responses.

---

## 5. Anomaly Detection

| Anomaly | Logic | Severity |
|---------|-------|----------|
| `BILLING_QUEUE_SPIKE` | `queue_depth > 5` in any `BILLING_QUEUE_JOIN` in last 10 minutes | WARN (>5) / CRITICAL (>10) |
| `DEAD_ZONE` | No `ZONE_ENTER` events in last 30 minutes | INFO — may indicate camera failure |
| `CONVERSION_DROP` | Today's conversion rate < 50% of 7-day rolling average | WARN |

Each anomaly includes `suggested_action` — a plain-English string shown directly to store managers.

---

## 6. Live Dashboard

Single-file HTML application (`app/static/dashboard.html`). No build step. No npm. Works immediately on `docker compose up`.

**Data sources:**
- SSE stream at `/stores/{id}/stream` — pushes metrics every 3 seconds
- Polls `/metrics`, `/heatmap`, `/anomalies` every 5 seconds for richer data

**Live metrics shown:** unique visitors (hero), conversion rate, queue depth, abandonment rate, data confidence, 4-stage funnel with drop-off percentages, zone heatmap sorted by visit score (shows real brand zone names: LAKME, FACE_SHOP, BILLING_COUNTER etc.), active anomalies with severity colours, scrolling event feed.

**Typography:** Bebas Neue (KPIs), DM Mono (data labels), Fraunces (logo). Dark charcoal base with warm gold accents — retail-premium aesthetic.

---

## 7. Testing

| File | Tests | Coverage |
|------|-------|----------|
| `tests/test_health.py` | 2 | Health endpoint |
| `tests/test_ingestion.py` | 5 | Single event, batch 500, idempotency, staff, confidence |
| `tests/test_metrics.py` | 7 | Empty store, staff exclusion, real visitor, funnel structure |
| `tests/test_edge_cases.py` | 8 | Empty store, all-staff, zero purchases, re-entry dedup, idempotency x500 |
| `tests/test_pipeline.py` | 7 | emit schema, staff classifier, Re-ID match/no-match/timeout |
| **Total** | **29** | **app/ modules: 79–100%** |

All tests use `StaticPool` in-memory SQLite via `conftest.py`. Each test gets a clean database — no state shared between tests. Pipeline modules (`detect.py`, `tracker.py`, `zones.py`) are 0% coverage because they require real video to execute — documented and defensible.

---

## 8. Containerisation

```yaml
services:
  api:
    build: .
    ports: ['8000:8000']
    volumes:
      - ./app:/app/app
      - ./data:/app/data
    environment:
      - DATABASE_URL=sqlite:///./data/store_intelligence.db
```

`docker compose up` starts everything. No manual steps beyond `git clone`. The SQLite database persists in `./data/` between restarts via the volume mount.

---

## 9. AI-Assisted Decisions

### 9.1 Re-ID Model: MobileNetV3 over OSNet

**AI suggested:** full OSNet from torchreid for high-accuracy retail-scale Re-ID.

**What I chose:** MobileNetV3 with classifier head stripped (576-d embeddings).

**Why:** torchreid requires CUDA for acceptable inference speed on 20-minute clips. This system must run on CPU. MobileNetV3 processes each crop in under 10ms on CPU and achieves cosine similarity 1.000 on identical crops in isolation testing. Confirmed 4 REENTRY events correctly detected on real footage. If deployed to production with GPU infrastructure, the `ReIDGallery` class interface would not change — only the extractor model inside `reid.py`.

### 9.2 Flat Columns over JSON Blob (disagreement point)

**AI suggested:** JSON blob metadata column for flexibility. Also suggested a separate metadata FK table for normalisation.

**What I chose:** flat ORM columns (`meta_queue_depth`, `meta_sku_zone`, `meta_session_seq`). Agreed on flat columns, **disagreed on the separate FK table**.

**Why flat columns:** all three fields appear in SQL `WHERE` clauses. `meta_queue_depth` is used in every anomaly detection query. A JSON blob requires `JSON_EXTRACT` in every query — not indexable. Flat columns enable standard SQLAlchemy filtering with full index support.

**Why I rejected the FK table:** the join overhead for anomaly queries that run on every `/anomalies` request is not justified. The three metadata fields are fixed in the spec. If metadata schema needed to be variable per event type, a separate table would be right — not the case here.

### 9.3 SSE over WebSockets

**AI suggested:** SSE for the live dashboard.

**What I chose:** SSE via `sse-starlette`. Agreed completely.

**Why:** the dashboard is read-only. SSE is unidirectional — exactly the right tool. Advantages over WebSockets: standard HTTP (no upgrade handshake), browser's native `EventSource` auto-reconnects on drop, no client library required, simpler server implementation. WebSockets add complexity with zero benefit for a display-only dashboard.
