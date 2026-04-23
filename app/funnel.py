from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import EventORM

router = APIRouter()

@router.get("/stores/{store_id}/funnel")
def get_funnel(store_id: str, db: Session = Depends(get_db)):
    def visitors_with(event_type):
        return set(r[0] for r in db.query(EventORM.visitor_id).filter(
            EventORM.store_id == store_id,
            EventORM.is_staff == False,
            EventORM.event_type == event_type
        ).distinct().all())

    entered       = visitors_with('ENTRY')
    visited_zone  = visitors_with('ZONE_ENTER')
    joined_billing= visitors_with('BILLING_QUEUE_JOIN')
    abandoned     = visitors_with('BILLING_QUEUE_ABANDON')
    purchased     = joined_billing - abandoned

    def pct(num, den):
        return round(num / den * 100, 1) if den > 0 else 0.0

    n_entry   = len(entered)
    n_zone    = len(entered & visited_zone)
    n_billing = len(entered & joined_billing)
    n_purchase= len(entered & purchased)

    return {
        "store_id": store_id,
        "funnel": [
            {"stage": "Entry",        "visitors": n_entry,    "drop_off_pct": 0.0},
            {"stage": "Zone visit",   "visitors": n_zone,     "drop_off_pct": pct(n_entry - n_zone, n_entry)},
            {"stage": "Billing queue","visitors": n_billing,  "drop_off_pct": pct(n_zone - n_billing, n_zone)},
            {"stage": "Purchase",     "visitors": n_purchase, "drop_off_pct": pct(n_billing - n_purchase, n_billing)},
        ]
    }
