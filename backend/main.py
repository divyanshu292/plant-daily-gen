import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(ROOT_ENV_PATH)

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB = os.getenv("MONGODB_DB", "ttps")

if not MONGODB_URI:
    raise SystemExit("Missing MONGODB_URI. Copy backend/.env.example to .env in project root and fill it in.")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
ALLOWED_FIELDS = {
    "u1Gen", "u2Gen",
    "u1Trip", "u2Trip",
    "u1Btl", "u2Btl",
    "u1Fo", "u2Fo",
    "u1Po", "u2Po",
}

LIVE_URL = "https://tpro.telsys.in/tpportal/power_generation?param=ajax_call&status_check=true"
LIVE_CACHE_TTL_S = 3

client = AsyncIOMotorClient(MONGODB_URI)
db = client[MONGODB_DB]
entries = db["entries"]

http_client: Optional[httpx.AsyncClient] = None
live_cache: dict = {"data": None, "fetched_at": 0.0}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(
        timeout=10.0,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (TTPS-dashboard)"},
    )
    await entries.create_index("date", unique=True)
    yield
    client.close()
    await http_client.aclose()


app = FastAPI(title="TTPS API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "name": "TTPS API",
        "docs": "/docs",
        "endpoints": [
            "GET  /api/health",
            "GET  /api/entries?month=YYYY-MM",
            "PUT  /api/entries/{date}",
            "GET  /api/live-generation",
        ],
        "ui": "http://localhost:5173",
    }


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/entries")
async def list_entries(month: Optional[str] = None):
    query: dict = {}
    if month:
        if not MONTH_RE.match(month):
            raise HTTPException(400, "Invalid month format (YYYY-MM)")
        query["date"] = {"$regex": f"^{month}"}
    cursor = entries.find(query, {"_id": 0})
    return await cursor.to_list(length=None)


@app.put("/api/entries/{date}")
async def upsert_entry(date: str, payload: dict):
    if not DATE_RE.match(date):
        raise HTTPException(400, "Invalid date format (YYYY-MM-DD)")

    clean: dict = {}
    for key, value in payload.items():
        if key not in ALLOWED_FIELDS:
            continue
        if value is None or value == "":
            clean[key] = None
        else:
            try:
                clean[key] = float(value)
            except (TypeError, ValueError):
                raise HTTPException(400, f"Field {key} must be a number or null")

    await entries.update_one(
        {"date": date},
        {"$set": clean, "$setOnInsert": {"date": date}},
        upsert=True,
    )
    return await entries.find_one({"date": date}, {"_id": 0})


@app.get("/api/live-generation")
async def live_generation():
    """Proxy the upstream TTPS portal feed (bypasses browser CORS)."""
    now = time.time()
    if live_cache["data"] is not None and now - live_cache["fetched_at"] < LIVE_CACHE_TTL_S:
        return live_cache["data"]
    try:
        resp = await http_client.get(LIVE_URL)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, f"Upstream portal unreachable: {exc}")

    live_cache["data"] = data
    live_cache["fetched_at"] = now
    return data
