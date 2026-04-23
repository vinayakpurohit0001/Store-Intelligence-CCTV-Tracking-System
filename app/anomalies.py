from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import EventORM
from datetime import datetime, timezone, timedelta

router = APIRouter()

@router.get("/stores/{store_id}/anomalies")
def get_anomalies(store_id: str, db: Session = Depends(get_db)):
    anomalies = []
    now = datetime.now(timezone.utc)

    # 1. BILLING_QUEUE_SPIKE — queue depth > 5 in last 10 min
    recent_billing = db.query(EventORM).filter(
        EventORM.store_id == store_id,
        EventORM.event_type == "BILLING_QUEUE_JOIN",
        EventORM.meta_queue_depth != None,
        EventORM.timestamp >= now - timedelta(minutes=10)
    ).order_by(EventORM.timestamp.desc()).first()

    if recent_billing and recent_billing.meta_queue_depth > 5:
        anomalies.append({
            "type": "BILLING_QUEUE_SPIKE",
            "severity": "CRITICAL" if recent_billing.meta_queue_depth > 10 else "WARN",
            "detail": f"Queue depth {recent_billing.meta_queue_depth} in last 10 min",
            "suggested_action": "Open additional checkout lane immediately"
        })

    # 2. DEAD_ZONE — no ZONE_ENTER events in any zone in last 30 min
    recent_zone = db.query(EventORM).filter(
        EventORM.store_id == store_id,
        EventORM.event_type == "ZONE_ENTER",
        EventORM.timestamp >= now - timedelta(minutes=30)
    ).first()

    if not recent_zone:
        anomalies.append({
            "type": "DEAD_ZONE",
            "severity": "INFO",
            "detail": "No zone visits recorded in last 30 minutes",
            "suggested_action": "Check camera feed and detection pipeline"
        })

    # 3. CONVERSION_DROP — today conversion < 50% of 7-day average
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start  = today_start - timedelta(days=7)

    def conversion_for_window(start, end):
        visitors = db.query(func.count(func.distinct(EventORM.visitor_id))).filter(
            EventORM.store_id == store_id,
            EventORM.is_staff == False,
            EventORM.event_type == "ENTRY",
            EventORM.timestamp >= start,
            EventORM.timestamp < end
        ).scalar() or 0
        converted = db.query(func.count(func.distinct(EventORM.visitor_id))).filter(
            EventORM.store_id == store_id,
            EventORM.is_staff == False,
            EventORM.event_type == "BILLING_QUEUE_JOIN",
            EventORM.timestamp >= start,
            EventORM.timestamp < end
        ).scalar() or 0
        return converted / visitors if visitors > 0 else None

    today_cr  = conversion_for_window(today_start, now)
    week_cr   = conversion_for_window(week_start, today_start)

    if today_cr is not None and week_cr and week_cr > 0:
        if today_cr < week_cr * 0.5:
            anomalies.append({
                "type": "CONVERSION_DROP",
                "severity": "WARN",
                "detail": f"Today CR {today_cr:.1%} vs 7-day avg {week_cr:.1%}",
                "suggested_action": "Review staffing levels and product availability"
            })

    return {
        "store_id": store_id,
        "anomalies": anomalies,
        "checked_at": now.isoformat()
    }
