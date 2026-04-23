from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import EventORM

router = APIRouter()

@router.get("/stores/{store_id}/heatmap")
def get_heatmap(store_id: str, db: Session = Depends(get_db)):
    rows = db.query(
        EventORM.zone_id,
        func.count(EventORM.event_id).label('visits'),
        func.avg(EventORM.dwell_ms).label('avg_dwell')
    ).filter(
        EventORM.store_id == store_id,
        EventORM.is_staff == False,
        EventORM.zone_id != None,
        EventORM.event_type == "ZONE_ENTER"
    ).group_by(EventORM.zone_id).all()

    if not rows:
        return {"store_id": store_id, "zones": [], "data_confidence": "LOW"}

    max_visits = max(r.visits for r in rows) or 1
    max_dwell  = max(r.avg_dwell or 0 for r in rows) or 1

    total_sessions = db.query(func.count(func.distinct(EventORM.visitor_id))).filter(
        EventORM.store_id == store_id,
        EventORM.is_staff == False,
        EventORM.event_type == "ENTRY"
    ).scalar() or 0

    return {
        "store_id": store_id,
        "data_confidence": "LOW" if total_sessions < 20 else "OK",
        "zones": [
            {
                "zone_id": r.zone_id,
                "visit_score": round(r.visits / max_visits * 100, 1),
                "dwell_score": round((r.avg_dwell or 0) / max_dwell * 100, 1),
                "raw_visits": r.visits,
                "avg_dwell_ms": round(r.avg_dwell or 0, 1)
            }
            for r in rows
        ]
    }
