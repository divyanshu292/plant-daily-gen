import math
import os
import re
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import certifi
import httpx
from bson.binary import Binary
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError

# Sibling modules are imported by bare name; make that work however the app is launched.
sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(ROOT_ENV_PATH)

import analytics  # noqa: E402
import calc  # noqa: E402
import extract  # noqa: E402
import workbook_import  # noqa: E402
from validate import cross_checks, validate  # noqa: E402

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB = os.getenv("MONGODB_DB", "ttps")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
IST = ZoneInfo("Asia/Kolkata")

# Daily values, per unit (u1/u2) unless noted. Units follow the plant workbook.
NUMERIC_FIELDS = {
    "u1Gen", "u2Gen",                    # generation, MU
    "u1Coal", "u2Coal",                  # coal consumption, MT
    "u1Oil", "u2Oil",                    # oil consumption, KL
    "u1Bd", "u2Bd",                      # grid backing down, MU
    "apc", "apcPlant", "apcSub",         # auxiliary power (station total, plant, sub-station), MU
    "gcv",                               # coal gross calorific value, kcal/kg (lab figure, arrives later)
    "coalReceipt", "coalReceiptRoad", "coalReceiptRail",  # MT
    "oilReceipt",                        # KL
    "u1Dm", "u2Dm",                      # DM make-up water, m3
    "u1Trip", "u2Trip",                  # number of trips
    "u1Btl", "u2Btl",                    # number of boiler tube leaks
    "u1Fo", "u2Fo",                      # forced outage, hours
    "u1Po", "u2Po",                      # planned outage, hours
    "u1H2", "u2H2",                      # hydrogen cylinders
    "coalStock", "oilStock", "oilPipeline",  # as printed on the day's report
}
TEXT_FIELDS = {"u1TripReason", "u2TripReason", "u1Remark", "u2Remark"}

# Uploaded page images are deleted this long after upload by a MongoDB TTL
# index (the database's own background job, so it works on serverless hosts).
IMAGE_RETENTION_DAYS = 15
IMAGE_TTL_INDEX = "createdAt_ttl"

LIVE_URL = "https://tpro.telsys.in/tpportal/power_generation?param=ajax_call&status_check=true"
LIVE_CACHE_TTL_S = 3

client: Optional[AsyncIOMotorClient] = None
# Opened on first use. dev_server.py and the tests put an in-memory database here.
db = None

http_client: Optional[httpx.AsyncClient] = None
live_cache: dict = {"data": None, "fetched_at": 0.0}


def _mongo_client(uri: str) -> AsyncIOMotorClient:
    options: dict = {"serverSelectionTimeoutMS": 8000}
    if uri.startswith("mongodb+srv://") or re.search(r"[?&](tls|ssl)=true", uri, re.IGNORECASE):
        # Use certifi's root certificates: some Python builds (python.org on
        # macOS, slim containers) have no CA store, and Atlas TLS then fails.
        options["tlsCAFile"] = certifi.where()
    return AsyncIOMotorClient(uri, **options)


def _db():
    global client, db
    if db is None:
        if not MONGODB_URI:
            raise HTTPException(503, "Database is not configured. Set MONGODB_URI in the project's .env file.")
        try:
            # An SRV address is resolved here, so a wrong or deleted cluster fails at this line.
            client = _mongo_client(MONGODB_URI)
        except PyMongoError as exc:
            raise HTTPException(503, f"Could not reach the database: {exc}")
        db = client[MONGODB_DB]
    return db


_indexed_db = None


async def _ensure_indexes() -> None:
    """Create the indexes once per database handle. Idempotent; also run before
    the first upload in case the host skipped the startup hook."""
    global _indexed_db
    database = _db()
    if _indexed_db is database:
        return
    await database["entries"].create_index("date", unique=True)
    await database["reports"].create_index([("dataDate", 1), ("createdAt", -1)])
    images = database["report_images"]
    ttl = IMAGE_RETENTION_DAYS * 24 * 3600
    current = (await images.index_information()).get(IMAGE_TTL_INDEX)
    if current is None:
        await images.create_index("createdAt", name=IMAGE_TTL_INDEX, expireAfterSeconds=ttl)
    elif current.get("expireAfterSeconds") != ttl:
        # Retention changed: update the existing index in place.
        await database.command("collMod", "report_images",
                               index={"name": IMAGE_TTL_INDEX, "expireAfterSeconds": ttl})
    _indexed_db = database


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(
        timeout=10.0,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (TTPS-dashboard)"},
    )
    try:
        await _ensure_indexes()
    except (HTTPException, PyMongoError) as exc:
        # Start anyway so /api/health can say what is wrong.
        print(f"Database not ready at startup: {getattr(exc, 'detail', exc)}")
    yield
    if client is not None:
        client.close()
    await http_client.aclose()


app = FastAPI(title="TTPS API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today() -> date:
    return datetime.now(IST).date()


def _check_date(value: str) -> date:
    if not DATE_RE.match(value):
        raise HTTPException(400, "Invalid date format (YYYY-MM-DD)")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, "Invalid date")


def _clean_fields(payload: dict) -> dict:
    """Keep known fields only; numbers as floats, blank as None."""
    clean: dict = {}
    for key, value in payload.items():
        if key in NUMERIC_FIELDS:
            if value is None or value == "":
                clean[key] = None
                continue
            try:
                # true/false would otherwise pass as 1/0.
                number = None if isinstance(value, bool) else float(value)
            except (TypeError, ValueError):
                number = None
            # NaN and infinity cannot be sent back as JSON, so once stored they
            # would break every response that includes the day.
            if number is None or not math.isfinite(number):
                raise HTTPException(400, f"Field {key} must be a number or null")
            clean[key] = number
        elif key in TEXT_FIELDS:
            clean[key] = (str(value).strip() or None) if value is not None else None
    return clean


async def _entries_between(start: date, end: date) -> list[dict]:
    cursor = _db()["entries"].find(
        {"date": {"$gte": start.isoformat(), "$lte": end.isoformat()}}, {"_id": 0}
    ).sort("date", 1)
    return await cursor.to_list(length=None)


async def _config(fy: int) -> dict:
    stored = await _db()["config"].find_one({"fy": fy}, {"_id": 0})
    return calc.merge_config(calc.default_config(fy), stored or {})


async def _latest_data_date() -> Optional[date]:
    """The latest day with generation data, or None if there is none."""
    doc = await _db()["entries"].find_one(
        {"$or": [{"u1Gen": {"$ne": None}}, {"u2Gen": {"$ne": None}}]}, {"date": 1}, sort=[("date", -1)]
    )
    return date.fromisoformat(doc["date"]) if doc else None


@app.get("/")
async def root():
    return {"name": "TTPS API", "docs": "/docs"}


@app.get("/api/health")
async def health():
    latest, database = None, True
    try:
        day = await _latest_data_date()
        latest = day.isoformat() if day else None
    except (HTTPException, PyMongoError):
        database = False
    return {
        "ok": True,
        "database": database,
        "extraction": {
            "configured": extract.is_configured(),
            "model": extract.MODEL,
        },
        "latestDate": latest,
        "today": _today().isoformat(),
    }


# --- daily entries -----------------------------------------------------------------

@app.get("/api/entries")
async def list_entries(month: Optional[str] = None, fy: Optional[int] = None):
    """Entries for one month (YYYY-MM) or one fiscal year (fy=2026 means Apr 2026 - Mar 2027)."""
    query: dict = {}
    if month:
        if not MONTH_RE.match(month):
            raise HTTPException(400, "Invalid month format (YYYY-MM)")
        query["date"] = {"$regex": f"^{month}"}
    elif fy:
        query["date"] = {"$gte": f"{fy}-04-01", "$lte": f"{fy + 1}-03-31"}
    cursor = _db()["entries"].find(query, {"_id": 0}).sort("date", 1)
    return await cursor.to_list(length=None)


@app.put("/api/entries/{date_str}")
async def upsert_entry(date_str: str, payload: dict):
    """Manual correction of a day's values."""
    _check_date(date_str)
    clean = _clean_fields(payload)
    if clean:
        clean["updatedAt"] = _now()
    await _db()["entries"].update_one(
        {"date": date_str},
        {"$set": clean, "$setOnInsert": {"date": date_str, "source": "manual"}},
        upsert=True,
    )
    return await _db()["entries"].find_one({"date": date_str}, {"_id": 0})


# --- report image -> data -------------------------------------------------------------

def _changes(existing: dict | None, new: dict) -> list[dict]:
    """Fields whose stored value differs from the newly read one."""
    if not existing:
        return []
    out = []
    for key, after in new.items():
        before = existing.get(key)
        if after is None or before is None:
            continue
        differs = abs(before - after) > 1e-9 if key in NUMERIC_FIELDS else before != after
        if differs:
            out.append({"field": key, "before": before, "after": after})
    return out


async def _save_entry(data_date: date, fields: dict, report_id: str) -> None:
    values = {k: v for k, v in fields.items() if v is not None}
    values.update({"source": "report", "reportId": report_id, "updatedAt": _now()})
    await _db()["entries"].update_one(
        {"date": data_date.isoformat()},
        {"$set": values, "$setOnInsert": {"date": data_date.isoformat()}},
        upsert=True,
    )


async def _month_context(data_date: date) -> dict[str, dict]:
    """Entries of the month, plus the previous day when that falls in the month before."""
    start = min(data_date.replace(day=1), data_date - timedelta(days=1))
    rows = await _entries_between(start, data_date + timedelta(days=31))
    return {r["date"]: r for r in rows if r["date"] != data_date.isoformat()}


@app.post("/api/reports")
async def upload_report(file: UploadFile = File(...)):
    """Read a Daily System Report image and store the previous day's data from it.

    The page is transcribed, its own arithmetic is re-checked, and only a page
    that adds up is saved automatically. Anything else is kept as 'needs_review'.
    """
    raw = await file.read()
    try:
        image = extract.load_image(raw)
        result = await extract.extract_report(image)
        if not result.report.is_daily_system_report:
            raise HTTPException(422, "This image does not look like the TVNL Daily System Report.")
        check = validate(result.report, today=_today())
        attempts = 1
        if not check.ok:
            # One more look, pointing at the cells that did not add up. If that
            # look fails outright, keep the first reading for review.
            attempts = 2
            try:
                retry = await extract.extract_report(image, recheck=check.recheck_hints())
            except extract.ExtractionError:
                retry = None
            if retry is not None and retry.report.is_daily_system_report:
                retry_check = validate(retry.report, today=_today())
                if len(retry_check.errors) <= len(check.errors):
                    result, check = retry, retry_check
    except extract.ExtractionError as exc:
        raise HTTPException(exc.status, str(exc))

    report_id = uuid.uuid4().hex
    uploaded_at = datetime.now(timezone.utc).replace(microsecond=0)
    checks = check.checks_json()
    missing_days: list[str] = []
    replaced = False
    changes: list[dict] = []
    status = "saved" if check.ok and check.data_date else "needs_review"

    if check.data_date:
        context = await _month_context(check.data_date)
        extra, missing_days = cross_checks(result.report, check.entry, check.data_date, context)
        checks += [c.__dict__ for c in extra]
        existing = await _db()["entries"].find_one({"date": check.data_date.isoformat()}, {"_id": 0})
        replaced = bool(existing and (existing.get("u1Gen") is not None or existing.get("u2Gen") is not None))
        changes = _changes(existing, check.entry)

    doc = {
        "id": report_id,
        "status": status,
        "reportDate": check.report_date.isoformat() if check.report_date else None,
        "dataDate": check.data_date.isoformat() if check.data_date else None,
        "raw": result.report.model_dump(),
        "entry": check.entry,
        "checks": checks,
        "missingDays": missing_days,
        "replaced": replaced,
        "changes": changes,
        "attempts": attempts,
        "model": result.model,
        "usage": result.usage,
        "fileName": file.filename,
        "createdAt": uploaded_at.isoformat(),
        "confirmedAt": None,
        "imageUntil": (uploaded_at + timedelta(days=IMAGE_RETENTION_DAYS)).isoformat(),
    }
    await _ensure_indexes()
    # createdAt must be a BSON date for the TTL index to delete the image.
    await _db()["report_images"].insert_one(
        {"_id": report_id, "data": Binary(extract.stored_image(image)), "createdAt": uploaded_at}
    )
    await _db()["reports"].insert_one(dict(doc))
    if status == "saved":
        await _save_entry(check.data_date, check.entry, report_id)
    return doc


@app.get("/api/reports")
async def list_reports(month: Optional[str] = None, limit: int = 60):
    """Uploaded reports, newest first, without the full transcription."""
    query: dict = {}
    if month:
        if not MONTH_RE.match(month):
            raise HTTPException(400, "Invalid month format (YYYY-MM)")
        query["dataDate"] = {"$regex": f"^{month}"}
    cursor = _db()["reports"].find(query, {"_id": 0, "raw": 0, "usage": 0}).sort("createdAt", -1)
    return await cursor.to_list(length=max(1, min(limit, 400)))


async def _report_or_404(report_id: str) -> dict:
    doc = await _db()["reports"].find_one({"id": report_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Report not found")
    return doc


@app.get("/api/reports/{report_id}")
async def get_report(report_id: str):
    return await _report_or_404(report_id)


@app.get("/api/reports/{report_id}/image")
async def get_report_image(report_id: str):
    doc = await _db()["report_images"].find_one({"_id": report_id})
    if not doc:
        if await _db()["reports"].find_one({"id": report_id}, {"_id": 1}):
            raise HTTPException(404, f"Page images are kept for {IMAGE_RETENTION_DAYS} days after upload; "
                                     "this one has been deleted.")
        raise HTTPException(404, "Image not found")
    return Response(bytes(doc["data"]), media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400"})


@app.post("/api/reports/{report_id}/confirm")
async def confirm_report(report_id: str, payload: dict):
    """Save a report that needed review, with any corrections made by the user."""
    doc = await _report_or_404(report_id)
    data_date_str = payload.get("dataDate") or doc.get("dataDate")
    if not data_date_str:
        raise HTTPException(400, "The report date could not be read. Provide dataDate (YYYY-MM-DD).")
    data_date = _check_date(data_date_str)
    entry = {**doc["entry"], **_clean_fields(payload.get("entry") or {})}
    await _save_entry(data_date, entry, report_id)
    update = {"status": "saved", "dataDate": data_date.isoformat(), "entry": entry, "confirmedAt": _now()}
    await _db()["reports"].update_one({"id": report_id}, {"$set": update})
    return {**doc, **update}


# --- derived figures ------------------------------------------------------------------

@app.get("/api/performance/{date_str}")
async def performance(date_str: str):
    """Daily / month-to-date / year-to-date performance report for one date."""
    on = _check_date(date_str)
    fy = calc.fiscal_year(on)
    entries = await _entries_between(date(fy, 4, 1), on)
    return calc.performance_report(entries, await _config(fy), on)


@app.get("/api/analytics")
async def get_analytics(on: Optional[str] = None):
    """Trends and things to look at for the Home screen (analytics.py), for
    `on` or by default the latest day with generation data."""
    day = _check_date(on) if on else None
    today = _today()
    latest = await _latest_data_date()
    if latest is None:
        return analytics.empty(today)
    day = day or latest
    fy = calc.fiscal_year(day)
    # The trend windows need LOOKBACK_DAYS of history; month and year progress
    # and the stock roll-forward need the whole fiscal year so far.
    start = min(day - timedelta(days=analytics.LOOKBACK_DAYS), date(fy, 4, 1))
    entries = await _entries_between(start, day)
    return analytics.analytics(entries, await _config(fy), day, today, latest=latest)


@app.get("/api/config/{fy}")
async def get_config(fy: int):
    return await _config(fy)


@app.put("/api/config/{fy}")
async def put_config(fy: int, payload: dict):
    """Override targets or opening stocks for a fiscal year."""
    allowed = {k: v for k, v in payload.items() if k in calc.CONFIG_KEYS}
    await _db()["config"].update_one({"fy": fy}, {"$set": allowed, "$setOnInsert": {"fy": fy}}, upsert=True)
    return await _config(fy)


@app.post("/api/import/workbook")
async def import_workbook(file: UploadFile = File(...), overwrite: bool = False):
    """Load history from the plant's 'TTPS DAILY GEN DATA' workbook (DAILY DATA sheet).

    Days already filled from a report image keep their values unless overwrite
    is set; the workbook only adds what the image does not carry (GCV, trips...).
    """
    raw = await file.read()
    try:
        book = workbook_import.read_workbook(raw)
    except workbook_import.WorkbookError as exc:
        raise HTTPException(422, str(exc))

    existing = {e["date"]: e for e in await _entries_between(date(book["fy"], 4, 1), date(book["fy"] + 1, 3, 31))}
    added = updated = 0
    for row in book["entries"]:
        current = existing.get(row["date"])
        fields = {k: v for k, v in row.items() if k != "date" and v is not None}
        if current and not overwrite:
            fields = {k: v for k, v in fields.items() if current.get(k) is None}
        if not fields:
            continue
        fields["updatedAt"] = _now()
        await _db()["entries"].update_one(
            {"date": row["date"]},
            {"$set": fields, "$setOnInsert": {"date": row["date"], "source": "workbook"}},
            upsert=True,
        )
        if current:
            updated += 1
        else:
            added += 1
    if book.get("config"):
        await _db()["config"].update_one(
            {"fy": book["fy"]}, {"$set": book["config"], "$setOnInsert": {"fy": book["fy"]}}, upsert=True
        )
    days = [r["date"] for r in book["entries"]]
    return {
        "fy": book["fy"],
        "days": len(days),
        "from": min(days) if days else None,
        "to": max(days) if days else None,
        "added": added,
        "updated": updated,
    }


# --- live feed --------------------------------------------------------------------------

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
