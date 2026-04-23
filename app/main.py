from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.health import router as health_router
from app.database import engine, Base
import app.models

from app.middleware import RequestLoggingMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Store Intelligence API", version="1.0.0")

app.add_middleware(RequestLoggingMiddleware)

@app.exception_handler(OperationalError)
async def db_error_handler(request, exc):
    return JSONResponse(
        status_code=503,
        content={
            "error": "database_unavailable",
            "message": "Database is temporarily unavailable. Please retry.",
            "trace": str(exc)[:120]
        }
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(health_router)
from app.ingestion import router as ingestion_router
from app.metrics   import router as metrics_router
from app.funnel    import router as funnel_router
from app.heatmap   import router as heatmap_router
from app.anomalies import router as anomalies_router

from app.reid_router import router as reid_router

app.include_router(ingestion_router)
app.include_router(metrics_router)
app.include_router(funnel_router)
app.include_router(heatmap_router)
app.include_router(anomalies_router)
app.include_router(reid_router)

from fastapi.staticfiles import StaticFiles
from app.dashboard import router as dashboard_router

app.include_router(dashboard_router)
app.mount('/static', StaticFiles(directory='app/static'), name='static')

@app.get("/")
async def root():
    return {"message": "Store Intelligence API — use /health to check status"}
