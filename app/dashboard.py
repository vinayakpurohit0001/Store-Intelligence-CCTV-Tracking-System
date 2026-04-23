import asyncio, json
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import EventORM
from datetime import datetime, timezone, timedelta

router = APIRouter()

def _get_live_metrics(store_id: str, db: Session) -> dict:
    # Get all non-staff events for this store
    base = db.query(EventORM).filter(
        EventORM.store_id == store_id,
        EventORM.is_staff == False
    )

    # Calculate Unique Visitors (Non-Staff)
    # We use ENTRY events to count unique visitors
    unique_visitors = db.query(EventORM.visitor_id).filter(
        EventORM.store_id == store_id,
        EventORM.is_staff == False,
        EventORM.event_type == 'ENTRY'
    ).distinct().count()

    # Calculate Staff Count (Currently on floor)
    # Anyone with a staff flag seen in the last 15 minutes
    now = datetime.now(timezone.utc)
    staff_on_floor = db.query(EventORM.visitor_id).filter(
        EventORM.store_id == store_id,
        EventORM.is_staff == True,
        EventORM.timestamp >= now - timedelta(minutes=15)
    ).distinct().count()

    def vset(etype):
        return set(r[0] for r in db.query(EventORM.visitor_id).filter(
            EventORM.store_id == store_id,
            EventORM.is_staff == False,
            EventORM.event_type == etype
        ).distinct().all())

    entered  = vset('ENTRY')
    zoned    = vset('ZONE_ENTER')
    billed   = vset('BILLING_QUEUE_JOIN')
    abandons = vset('BILLING_QUEUE_ABANDON')
    purchased= billed - abandons

    valid_abandons = entered & abandons
    valid_purchased = entered & purchased
    converted = len(valid_purchased)

    last_billing = base.filter(
        EventORM.event_type == 'BILLING_QUEUE_JOIN',
        EventORM.meta_queue_depth != None
    ).order_by(EventORM.timestamp.desc()).first()
    queue_depth = last_billing.meta_queue_depth if last_billing else 0

    # Recent anomalies count
    recent_anomaly = db.query(EventORM).filter(
        EventORM.store_id == store_id,
        EventORM.event_type == 'BILLING_QUEUE_JOIN',
        EventORM.meta_queue_depth > 5,
        EventORM.timestamp >= now - timedelta(minutes=10)
    ).first()

    return {
        'store_id':         store_id,
        'unique_visitors':  unique_visitors,
        'staff_count':      staff_on_floor,
        'conversion_rate':  round(converted/unique_visitors,4) if unique_visitors>0 else 0.0,
        'abandonment_rate': round(len(valid_abandons)/unique_visitors, 4) if unique_visitors>0 else 0.0,
        'converted_visitors': converted,
        'queue_depth':      queue_depth,
        'alert':            bool(recent_anomaly),
        'funnel': [
            {'stage':'Entry',        'count': len(entered)},
            {'stage':'Zone visit',   'count': len(entered & zoned)},
            {'stage':'Billing queue','count': len(entered & billed)},
            {'stage':'Purchase',     'count': len(entered & purchased)},
        ],
        'as_of': now.isoformat()
    }

@router.get('/stores/{store_id}/stream')
async def stream_metrics(store_id: str, db: Session = Depends(get_db)):
    async def generator():
        while True:
            data = _get_live_metrics(store_id, db)
            yield {'data': json.dumps(data)}
            await asyncio.sleep(3)
    return EventSourceResponse(generator())

@router.get('/dashboard')
async def serve_dashboard():
    return FileResponse('app/static/dashboard.html', headers={'Cache-Control': 'no-cache, no-store, must-revalidate'})
