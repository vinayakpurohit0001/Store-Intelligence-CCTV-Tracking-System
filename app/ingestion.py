import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from app.database import get_db
from app.models import IngestRequest, IngestResponse, EventORM

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/events/ingest", response_model=IngestResponse)
def ingest_events(payload: IngestRequest, db: Session = Depends(get_db)):
    accepted = duplicates = errors = 0
    error_details = []

    try:
        # Fetch all existing event_ids in this batch for dedup check
        incoming_ids = [e.event_id for e in payload.events]
        existing_ids = set(
            row[0] for row in
            db.query(EventORM.event_id)
              .filter(EventORM.event_id.in_(incoming_ids)).all()
        )

        for event in payload.events:
            try:
                if event.event_id in existing_ids:
                    duplicates += 1
                    continue

                orm = EventORM(
                    event_id   = event.event_id,
                    store_id   = event.store_id,
                    camera_id  = event.camera_id,
                    visitor_id = event.visitor_id,
                    event_type = event.event_type.value,
                    timestamp  = event.timestamp,
                    zone_id    = event.zone_id,
                    dwell_ms   = event.dwell_ms,
                    is_staff   = event.is_staff,
                    confidence = event.confidence,
                    meta_queue_depth = event.metadata.queue_depth,
                    meta_sku_zone    = event.metadata.sku_zone,
                    meta_session_seq = event.metadata.session_seq,
                )
                db.add(orm)
                existing_ids.add(event.event_id)
                accepted += 1

            except Exception as e:
                errors += 1
                error_details.append({"event_id": event.event_id, "error": str(e)})
                logger.error(f'Event {event.event_id} failed: {e}')

        db.commit()

    except OperationalError as e:
        db.rollback()
        raise HTTPException(status_code=503, detail={"error": "database_unavailable", "message": str(e)})

    return IngestResponse(
        accepted=accepted,
        duplicates=duplicates,
        errors=errors,
        error_details=error_details
    )
