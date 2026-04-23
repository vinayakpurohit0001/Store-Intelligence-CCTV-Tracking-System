from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import EventORM
from datetime import datetime, timezone, timedelta

router = APIRouter()

@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    store_status = {}

    try:
        rows = db.query(
            EventORM.store_id,
            func.max(EventORM.timestamp).label('last_event')
        ).group_by(EventORM.store_id).all()

        for row in rows:
            last = row.last_event
            if last and last.tzinfo is None:
                from datetime import timezone as tz
                last = last.replace(tzinfo=tz.utc)
            lag_min = (now - last).total_seconds() / 60 if last else None
            store_status[row.store_id] = {
                "last_event": last.isoformat() if last else None,
                "status": "STALE_FEED" if lag_min and lag_min > 10 else "OK"
            }
        db_status = 'ok'
    except Exception as e:
        db_status = f'error: {str(e)}'

    return {
        "status": "ok",
        "timestamp": now.isoformat(),
        "version": "1.0.0",
        "service": "store-intelligence-api",
        "database": db_status,
        "stores": store_status
    }
