import logging, os, threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import redis
from . import service
from .db import init_db, DAILY_QUOTA

log = logging.getLogger("sweeper")
r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

def sweeper(stop: threading.Event):
    while not stop.wait(2):
        try:
            if r.set("lock:sweeper", "1", nx=True, ex=5):
                service.sweep()
        except Exception as e:
            log.warning("sweep skipped: %s", e)

@asynccontextmanager
async def lifespan(app):
    init_db()
    stop = threading.Event()
    threading.Thread(target=sweeper, args=(stop,), daemon=True).start()
    yield
    stop.set()

app = FastAPI(title="Enrichment quota coordinator", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.exception_handler(service.ApiError)
async def api_error(_, e: service.ApiError):
    return JSONResponse({"detail": e.message}, status_code=e.status)

class EnrichBody(BaseModel):
    indicator: str = Field(min_length=1, max_length=255)
    analyst_id: str = Field(min_length=1, max_length=64)

@app.get("/api/quota")
def quota():
    return service.quota_snapshot()

@app.post("/api/enrichment")
def request_enrichment(body: EnrichBody, idempotency_key: str = Header(..., alias="Idempotency-Key")):
    return service.request_enrichment(body.indicator, body.analyst_id, idempotency_key)

@app.post("/api/enrichment/{lookup_id}/run")
def run(lookup_id: str):
    return service.run_lookup(lookup_id)

@app.get("/api/enrichment/{lookup_id}")
def status(lookup_id: str):
    return service.get_lookup(lookup_id)

@app.post("/api/admin/reset") 
def reset(total: int = DAILY_QUOTA):
    service.reset(total)
    return service.quota_snapshot()
