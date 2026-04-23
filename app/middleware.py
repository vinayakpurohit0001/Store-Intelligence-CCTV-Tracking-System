import time, uuid, logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger('store_intelligence')

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id  = str(uuid.uuid4())[:8]
        start     = time.perf_counter()

        # Extract store_id from path if present
        parts    = request.url.path.split('/')
        store_id = parts[2] if len(parts) > 2 and parts[1] == 'stores' else '-'

        response = await call_next(request)

        latency_ms = round((time.perf_counter() - start) * 1000, 1)

        # Count events for ingest endpoint
        event_count = '-'

        logger.info(
            f'trace_id={trace_id} store_id={store_id} '
            f'method={request.method} endpoint={request.url.path} '
            f'status={response.status_code} latency_ms={latency_ms} '
            f'event_count={event_count}'
        )
        response.headers['X-Trace-Id'] = trace_id
        return response
