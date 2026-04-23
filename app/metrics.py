from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import EventORM
from datetime import datetime, timezone, timedelta
from typing import Optional

router = APIRouter()

@router.get("/stores/{store_id}/metrics")
def get_metrics(store_id: str, db: Session = Depends(get_db)):
    base = db.query(EventORM).filter(
        EventORM.store_id == store_id,
        EventORM.is_staff == False
    )

    # Unique visitors — count distinct visitor_ids from ENTRY events
    unique_visitors = base.filter(
        EventORM.event_type == "ENTRY"
    ).with_entities(func.count(func.distinct(EventORM.visitor_id))).scalar() or 0

    # Conversions — visitors who had a BILLING_QUEUE_JOIN and NOT BILLING_QUEUE_ABANDON
    billing_joins = set(
        r[0] for r in base.filter(
            EventORM.event_type == "BILLING_QUEUE_JOIN"
        ).with_entities(EventORM.visitor_id).all()
    )
    billing_abandons = set(
        r[0] for r in base.filter(
            EventORM.event_type == "BILLING_QUEUE_ABANDON"
        ).with_entities(EventORM.visitor_id).all()
    )
    converted = len(billing_joins - billing_abandons)
    conversion_rate = round(converted / unique_visitors, 4) if unique_visitors > 0 else 0.0

    # Avg dwell per zone
    zone_dwell = db.query(
        EventORM.zone_id,
        func.avg(EventORM.dwell_ms).label('avg_dwell')
    ).filter(
        EventORM.store_id == store_id,
        EventORM.is_staff == False,
        EventORM.zone_id != None,
        EventORM.event_type.in_(["ZONE_DWELL","ZONE_EXIT"])
    ).group_by(EventORM.zone_id).all()

    # Current queue depth — latest queue_depth value from billing events
    last_billing = base.filter(
        EventORM.event_type == "BILLING_QUEUE_JOIN",
        EventORM.meta_queue_depth != None
    ).order_by(EventORM.timestamp.desc()).first()
    queue_depth = last_billing.meta_queue_depth if last_billing else 0

    # Abandonment rate
    abandonment_rate = round(
        len(billing_joins & billing_abandons) / len(billing_joins), 4
    ) if billing_joins else 0.0

    return {
        "store_id": store_id,
        "unique_visitors": unique_visitors,
        "conversion_rate": conversion_rate,
        "converted_visitors": converted,
        "queue_depth": queue_depth,
        "abandonment_rate": abandonment_rate,
        "avg_dwell_per_zone": {
            row.zone_id: round(row.avg_dwell or 0, 1)
            for row in zone_dwell
        },
        "as_of": datetime.now(timezone.utc).isoformat()
    }
