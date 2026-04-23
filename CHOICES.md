# CHOICES.md — Store Intelligence
## Apex Retail · STORE_BLR_002 · April 2026

This document records three architectural decisions made during the build: the options that were considered, what the AI suggested, what was chosen, and why. One entry documents a point where I disagreed with the AI's recommendation.

---

## Choice 1 — Detection Model: YOLOv8n + ByteTrack

### Options Considered

**Detection models:**

| Model | CPU Speed | Reason for Accept/Reject |
|-------|-----------|--------------------------|
| YOLOv8n | ~40ms/frame | **Chosen** — fastest variant, sufficient accuracy for 1080p 15fps footage |
| YOLOv8s | ~120ms/frame | Considered — better accuracy, too slow for real-time processing on CPU |
| YOLOv8m | ~300ms/frame | Rejected — far too slow for 20-minute clip batch processing on CPU |
| RT-DETR | ~180ms/frame | Rejected — transformer architecture overhead not justified for single-class (person) detection |
| MediaPipe | ~15ms/frame | Rejected — optimised for faces/hands, poor full-body person detection accuracy |

**Tracking algorithms:**

| Tracker | Assessment |
|---------|------------|
| ByteTrack | **Chosen** — best speed/accuracy balance. Kalman filter maintains track identity through occlusions. Maintained in supervision library with clean Python API. |
| DeepSORT | Considered — uses appearance features at every track step but requires a separate Re-ID model embedded in the tracker. More complex with overlapping concerns. |
| StrongSORT | Rejected — higher accuracy ceiling but significantly more complex; overkill for single-camera retail tracking. |

### What the AI Suggested

AI suggested starting with YOLOv8n + ByteTrack via supervision, combined with `FRAME_SKIP=2` to make CPU inference feasible on 15fps footage without missing any entry/exit crossings.

### What I Chose and Why

**YOLOv8n + supervision ByteTrack + FRAME_SKIP=2.** Agreed with the AI's reasoning on all three decisions.

**On FRAME_SKIP=2:** a person walking through the entry threshold takes at minimum 0.5 seconds, typically 1–2 seconds. At 7.5 effective fps (every other frame), that is 4–15 frames to detect the threshold crossing. The direction detection logic checks centroid trajectory across frames rather than a single-frame snapshot — the lower frame rate does not affect accuracy.

**On confidence threshold 0.35:** the typical YOLO default is 0.5. The footage includes partial occlusions near shelving and between customers. At 0.5, partially-visible people are discarded entirely. At 0.35, they are captured with their actual confidence score in the event's `confidence` field. The key design principle: the pipeline never silently discards a detection. Downstream consumers decide what confidence level to trust.

**On supervision v0.27 compatibility:** the ByteTrack class was renamed from `sv.ByteTracker()` to `sv.ByteTrack()` in supervision v0.21. Additionally, `tracked.tracker_id` returns a numpy array — boolean evaluation raises an `AmbiguousError`. Fixed with explicit `is not None` checks in both tracking loops.

**Verified on real footage (CAM_1.mp4):** 14 ENTRY events, 15 EXIT events, 4 REENTRY events, 2 staff events correctly flagged. Unique customer visitors: 13 (staff excluded from 7 total visitor sessions).

---

## Choice 2 — Event Schema: Flat ORM Columns over JSON Blob

### Options Considered

| Option | Description | Trade-off |
|--------|-------------|-----------|
| **(a) JSON blob** | Single `metadata` column storing arbitrary JSON | Flexible schema, but no SQL indexing on metadata fields |
| **(b) Flat ORM columns** | Separate columns per field: `meta_queue_depth`, `meta_sku_zone`, `meta_session_seq` | Fixed schema, but all fields are indexable and directly queryable |
| **(c) Separate FK table** | `EventMetadata` table with foreign key to `Events` | Normalised and flexible, but adds a JOIN to every analytics query |

### What the AI Suggested

AI suggested option **(b)** — flat ORM columns — because all three metadata fields appear in SQL `WHERE` clauses. AI also suggested option **(c)** as a "more scalable" approach for future metadata evolution.

### What I Chose and Why

**Option (b): flat ORM columns.** Agreed with AI on **(b)**. **Disagreed and rejected (c).**

**Why flat columns over JSON blob:**

All three metadata fields are used in filtering and aggregation:
- `meta_queue_depth` appears in every anomaly detection query (`BILLING_QUEUE_SPIKE` checks `queue_depth > 5` in recent events)
- `meta_session_seq` is available for funnel ordering
- `meta_sku_zone` maps to zone labels from `store_layout.json`

A JSON blob would require SQLite's `JSON_EXTRACT` in every anomaly query — not indexable, and slower:

```python
# With JSON blob — not indexable
.filter(text("JSON_EXTRACT(metadata, '$.queue_depth') > 5"))

# With flat column — uses standard index
.filter(EventORM.meta_queue_depth > 5)
```

**Why I rejected the separate FK table (overriding AI):**

The anomaly detection endpoint (`/stores/{id}/anomalies`) is called on every dashboard poll cycle. Adding a JOIN to the `BILLING_QUEUE_JOIN` filter query adds latency on every request with no benefit. The three metadata fields are fixed in the challenge specification — they will not change during this project. A separate table solves a schema flexibility problem that does not exist here.

If this system were extended to support arbitrary per-event-type metadata (different fields per event type), a separate table would be the right call. For this implementation, flat columns win on both query performance and implementation simplicity.

**Interface compatibility:** the Pydantic inbound schema preserves the nested metadata structure for API compatibility. The API accepts JSON with nested `metadata`, stores it flat internally:

```python
class EventMetadata(BaseModel):
    queue_depth: Optional[int] = None
    sku_zone:    Optional[str] = None
    session_seq: Optional[int] = None

class EventIn(BaseModel):
    # ... other fields ...
    metadata: EventMetadata = Field(default_factory=EventMetadata)
```

---

## Choice 3 — API Architecture: FastAPI + SQLite + SSE

### Options Considered

| Dimension | Options | Choice |
|-----------|---------|--------|
| API framework | FastAPI / Flask / Django | FastAPI |
| Database | SQLite / PostgreSQL / Redis | SQLite with PostgreSQL migration path |
| Dashboard transport | WebSockets / SSE / polling | SSE via sse-starlette |
| Dashboard frontend | React / Vue / Vanilla HTML + Chart.js | Vanilla HTML + Chart.js |

### What the AI Suggested

FastAPI + SQLite for development (with PostgreSQL path), SSE over WebSockets for the dashboard, vanilla HTML over a framework. Agreed with all three.

### FastAPI — Why

FastAPI was chosen over Flask for three reasons that directly benefited this project:

1. **Pydantic validation is built in.** The `EventIn` schema validates all 10 required fields plus the `confidence` range check (0.0–1.0) at the API boundary — before any event reaches the database. Flask requires a separate validation library and more boilerplate.

2. **Dependency injection for database sessions** (`Depends(get_db)`) makes test isolation clean. `conftest.py` overrides `get_db` with an in-memory SQLite fixture per test without monkey-patching global state. All 29 tests are fully isolated.

3. **Auto-generated Swagger UI at `/docs`** was used throughout development to manually test endpoint responses without writing curl commands for every schema iteration.

### SQLite — Why (and the PostgreSQL path)

SQLite was chosen for operational simplicity — no separate container, no connection credentials, file-based persistence that survives `docker compose` restarts via the volume mount. The `DATABASE_URL` environment variable means switching to PostgreSQL requires one config change:

```bash
# Current (SQLite)
DATABASE_URL=sqlite:///./data/store_intelligence.db

# Production path (PostgreSQL)
DATABASE_URL=postgresql://user:pass@db:5432/store_intelligence
```

**At scale (40 live stores):** SQLite write contention would be the first bottleneck. SQLite allows only one writer at a time. 40 concurrent `POST /events/ingest` calls would queue on the write lock. The fix is already parameterised: switch `DATABASE_URL` to PostgreSQL and add `pool_size=10` to `create_engine`. The `SELECT` queries (`/metrics`, `/funnel`, `/heatmap`) handle concurrency fine in SQLite WAL mode — only the write path has the limitation.

### SSE over WebSockets — Why

The live dashboard is **read-only** — the server pushes metric updates to the browser, and the browser never sends data back. WebSockets provide full-duplex bidirectional communication — the wrong tool for a unidirectional display.

SSE advantages:
- **Standard HTTP** — no upgrade handshake, works through all proxies and load balancers
- **Auto-reconnect** — the browser's native `EventSource` retries automatically on connection drop; no client-side reconnection logic needed
- **No client library** — `EventSource` is built into every modern browser
- **Simpler server code** — `sse-starlette`'s `EventSourceResponse` handles the streaming loop

The one SSE limitation (unidirectional only) is irrelevant for a display-only dashboard.

### Vanilla HTML over React — Why

The dashboard (`app/static/dashboard.html`) is a single self-contained file rather than a React or Vue application. **Primary reason: no build step.** The dashboard works immediately on `docker compose up` without `npm install`, webpack, or a separate dev server. For a submission where a reviewer runs `docker compose up` on a clean machine, eliminating the build step reduces setup friction and failure surface. The entire dashboard is one file — inspectable directly, no bundler output to decode.

---

## Appendix — Edge Case Handling

| Edge Case | How Handled | Code Location |
|-----------|-------------|---------------|
| Group entry (2–4 people simultaneously) | ByteTrack assigns separate `tracker_id` per person — 3 people entering together emit 3 ENTRY events | `pipeline/tracker.py` |
| Staff movement | HSV histogram on torso region; black uniforms confirmed from footage frame 500 | `pipeline/staff.py` |
| Re-entry | MobileNetV3 cosine gallery; same person within 10-min window gets `REENTRY`, not second `ENTRY` | `pipeline/reid.py` |
| Partial occlusion | Confidence threshold 0.35; low detections passed through with actual confidence score | `pipeline/detect.py` |
| Billing queue buildup | `queue_depth` tracked in `BILLING_QUEUE_JOIN` events; `BILLING_QUEUE_SPIKE` anomaly fires at depth > 5 | `app/anomalies.py` |
| Empty store periods | All endpoints return `0` values not `null` or `500`; tested in `test_edge_cases.py` | `app/metrics.py` + tests |
| Camera angle overlap | `visitor_id` persists via Re-ID gallery across cameras — same person in CAM_1 and CAM_3 gets same `VIS_` id | `pipeline/reid.py` |
