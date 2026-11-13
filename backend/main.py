import asyncio
import hmac
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
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, IndexModel, ReturnDocument
from pymongo.errors import DuplicateKeyError, OperationFailure, PyMongoError

# Sibling modules are imported by bare name; make that work however the app is launched.
sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(ROOT_ENV_PATH)

import analytics  # noqa: E402
import auth  # noqa: E402
import calc  # noqa: E402
import extract  # noqa: E402
import live  # noqa: E402
import logbook  # noqa: E402
import logbook_forms  # noqa: E402
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
# Live feed readings (live.py) are deleted the same way, this long after their stamp.
LIVE_RETENTION_DAYS = 90
LIVE_TTL_INDEX = "ts_ttl"

LIVE_URL = "https://tpro.telsys.in/tpportal/power_generation?param=ajax_call&status_check=true"
LIVE_CACHE_TTL_S = 3
LIVE_COLLECTION = "live_readings"
# Readings from pasted WhatsApp messages (logbook.py): one record per day and section.
LOGS_COLLECTION = "logs"
# How far back to look for "the last day this section was reported" to compare with.
LOGS_LOOKBACK_DAYS = 45

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

# Every query the API makes is served by one of these, or by a TTL index
# (_ensure_indexes; report_images is otherwise read by _id):
#   entries        one day, or a date range sorted by date; latest day with
#                  generation (walks the date index backwards)        -> date
#   reports        one report by id (open, confirm, image check)      -> id
#                  newest first (Recent uploads)                       -> createdAt
#                  one day or one month, newest first (Daily report)   -> dataDate, createdAt
#   config         one fiscal year                                     -> fy
#   live_readings  one IST day by time; the latest reading             -> ts (its TTL index)
#   logs           one day's sections; one section on earlier days;
#                  the latest, next and previous day with readings     -> date, section
#   users          one user by id (user management)                    -> id
#                  by email (sign-in; unique, so no duplicate accounts) -> email
#                  by session (every signed-in request)                -> sessions.hash
#                  The user list and the "is there a super admin" check
#                  read the whole collection: a handful of people.
INDEXES = {
    "entries": [IndexModel([("date", ASCENDING)], unique=True)],
    "reports": [
        IndexModel([("id", ASCENDING)], unique=True),
        IndexModel([("createdAt", DESCENDING)]),
        IndexModel([("dataDate", ASCENDING), ("createdAt", DESCENDING)]),
    ],
    "config": [IndexModel([("fy", ASCENDING)], unique=True)],
    LOGS_COLLECTION: [IndexModel([("date", ASCENDING), ("section", ASCENDING)], unique=True)],
    "users": [
        IndexModel([("id", ASCENDING)], unique=True),
        IndexModel([("email", ASCENDING)], unique=True),
        IndexModel([("sessions.hash", ASCENDING)]),
    ],
}


async def _ensure_ttl(database, collection: str, field: str, name: str, days: int) -> None:
    """A TTL index deleting documents `days` after their `field` date."""
    ttl = days * 24 * 3600
    current = (await database[collection].index_information()).get(name)
    if current is None:
        await database[collection].create_index(field, name=name, expireAfterSeconds=ttl)
    elif current.get("expireAfterSeconds") != ttl:
        # Retention changed: update the existing index in place.
        await database.command("collMod", collection, index={"name": name, "expireAfterSeconds": ttl})


async def _ensure_indexes() -> None:
    """Create the indexes once per database handle. Idempotent; also run before
    the first upload or live recording in case the host skipped the startup
    hook. The collections are done in parallel, so a cold start pays about one
    round trip, not one per collection."""
    global _indexed_db
    database = _db()
    if _indexed_db is database:
        return
    ttls = (
        ("report_images", "createdAt", IMAGE_TTL_INDEX, IMAGE_RETENTION_DAYS),
        (LIVE_COLLECTION, "ts", LIVE_TTL_INDEX, LIVE_RETENTION_DAYS),
    )

    async def build(name: str, models: list) -> None:
        try:
            await database[name].create_indexes(models)
        except OperationFailure as exc:
            # e.g. duplicate values blocking a unique index: queries still work,
            # just slower, so report it rather than failing every request.
            print(f"Could not create indexes on {name}: {exc}")

    await asyncio.gather(*(_ensure_ttl(database, *ttl) for ttl in ttls),
                         *(build(n, m) for n, m in INDEXES.items()))
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
        await _seed_super_admin()
    except (HTTPException, PyMongoError) as exc:
        # Start anyway so /api/health can say what is wrong.
        print(f"Database not ready at startup: {getattr(exc, 'detail', exc)}")
    yield
    if client is not None:
        client.close()
    await http_client.aclose()


app = FastAPI(title="TTPS API", lifespan=lifespan)


class JsonGZipMiddleware:
    """gzip the JSON responses, which shrink about tenfold (a year of entries
    is ~200 kB raw), but pass page images through: JPEG does not compress."""

    def __init__(self, app):
        self.app = app
        self.gzip = GZipMiddleware(app, minimum_size=1024, compresslevel=6)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].endswith("/image"):
            await self.app(scope, receive, send)
        else:
            await self.gzip(scope, receive, send)


app.add_middleware(JsonGZipMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _now() -> str:
    return auth.iso(_utcnow())


def _ist_now() -> datetime:
    return datetime.now(IST)


def _today() -> date:
    return _ist_now().date()


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


# A fiscal year of entries in one batch: the driver's default first batch is
# 101 documents, and every further batch costs another round trip to the database.
ENTRIES_BATCH = 1000


def _month_range(month: str) -> dict:
    """A YYYY-MM month as a range on YYYY-MM-DD strings: a plain index range
    (a regex prefix works too, but the planner bounds a range more tightly)."""
    return {"$gte": f"{month}-01", "$lte": f"{month}-31"}


async def _entries_between(start: date, end: date) -> list[dict]:
    cursor = _db()["entries"].find(
        {"date": {"$gte": start.isoformat(), "$lte": end.isoformat()}}, {"_id": 0}
    ).sort("date", 1).batch_size(ENTRIES_BATCH)
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


# --- who is signed in ----------------------------------------------------------------
#
# Every /api route needs a session except /api/health, /api/live/record (it has
# its own key) and sign-in and sign-out. Each route names what it needs with one
# of the three dependencies below; tests/test_auth.py fails if one has none.

async def require_user(request: Request) -> dict:
    """The signed-in user, from the session cookie. Looked up on every request,
    with no cache, so a role change or a removal takes effect at once."""
    database = _db()  # without a database, say so (503) rather than "sign in"
    token = request.cookies.get(auth.COOKIE)
    if token:
        hashed = auth.token_hash(token)
        user = await database["users"].find_one({"sessions.hash": hashed}, {"_id": 0, "activity": 0})
        if user and auth.session_live(user, hashed, _utcnow()):
            request.state.session_hash = hashed  # the session a password change keeps
            return user
    raise HTTPException(401, "Sign in to continue")


async def require_editor(user: dict = Depends(require_user)) -> dict:
    """Admins and the super admin change plant data; a viewer only reads it."""
    if user["role"] not in auth.EDITOR_ROLES:
        raise HTTPException(403, "Your access is view only")
    return user


async def require_super_admin(user: dict = Depends(require_user)) -> dict:
    if user["role"] != auth.SUPER_ADMIN:
        raise HTTPException(403, "Only the super admin can manage users")
    return user


async def _log(user_id: str, action: str, text: str) -> None:
    """Add a line to someone's activity (the newest ACTIVITY_KEPT are kept).
    A failure is printed, never passed on: the change itself has been made."""
    try:
        entry = auth.activity_entry(action, text, _utcnow())
        await _db()["users"].update_one(
            {"id": user_id}, {"$push": {"activity": {"$each": [entry], "$slice": -auth.ACTIVITY_KEPT}}})
    except Exception as exc:  # noqa: BLE001
        print(f"Could not record activity {action}: {exc}")


def _day_label(iso_date: str) -> str:
    """2026-11-03 -> 3 Nov 2026, for activity lines."""
    d = date.fromisoformat(iso_date)
    return f"{d.day} {d:%b %Y}"


def _fy_label(fy: int) -> str:
    return f"{fy}-{(fy + 1) % 100:02d}"


def _new_user(email: str, name: str, role: str, password_hash: str, created_by: Optional[dict] = None) -> dict:
    """A user document. `created_by` is the super admin who onboarded them, or
    None for a user seeded from the server's settings."""
    now = _now()
    activity = []
    if created_by:
        activity.append(auth.activity_entry("account_created", f"Account created by {created_by['name']}", _utcnow()))
    return {
        "id": uuid.uuid4().hex, "email": email, "name": name, "role": role, "passwordHash": password_hash,
        "createdAt": now, "createdBy": created_by["id"] if created_by else None, "updatedAt": now,
        "lastLoginAt": None, "failedLogins": 0, "lockedUntil": None, "sessions": [], "activity": activity,
    }


async def _seed_super_admin() -> None:
    """Create the super admin from SUPERADMIN_EMAIL and SUPERADMIN_PASSWORD
    (SUPERADMIN_NAME optional) when there is none yet. Run at startup and before
    every sign-in, since a serverless host may skip startup. Never changes an
    existing user. The settings' values are never printed."""
    users = _db()["users"]
    if await users.find_one({"role": auth.SUPER_ADMIN}, {"_id": 1}):
        return
    email, password = os.getenv("SUPERADMIN_EMAIL"), os.getenv("SUPERADMIN_PASSWORD")
    if not email or not password:
        print("No super admin yet: set SUPERADMIN_EMAIL and SUPERADMIN_PASSWORD "
              "(and optionally SUPERADMIN_NAME), then restart or sign in.")
        return
    try:
        email, name = auth.check_email(email), auth.check_name(os.getenv("SUPERADMIN_NAME") or "Super admin")
        auth.check_password(password)
    except auth.Invalid as exc:
        print(f"Super admin not created, check the SUPERADMIN_* settings: {exc}")
        return
    if await users.find_one({"email": email}, {"_id": 1}):
        print("Super admin not created: a user with SUPERADMIN_EMAIL already exists and is left as is.")
        return
    password_hash = await asyncio.to_thread(auth.hash_password, password)
    try:
        await users.insert_one(_new_user(email, name, auth.SUPER_ADMIN, password_hash))
        print("Created the super admin from SUPERADMIN_EMAIL.")
    except DuplicateKeyError:
        pass  # another instance created it at the same moment


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

@app.get("/api/entries", dependencies=[Depends(require_user)])
async def list_entries(month: Optional[str] = None, fy: Optional[int] = None):
    """Entries for one month (YYYY-MM) or one fiscal year (fy=2026 means Apr 2026 - Mar 2027)."""
    query: dict = {}
    if month:
        if not MONTH_RE.match(month):
            raise HTTPException(400, "Invalid month format (YYYY-MM)")
        query["date"] = _month_range(month)
    elif fy:
        query["date"] = {"$gte": f"{fy}-04-01", "$lte": f"{fy + 1}-03-31"}
    cursor = _db()["entries"].find(query, {"_id": 0}).sort("date", 1).batch_size(ENTRIES_BATCH)
    return await cursor.to_list(length=None)


@app.put("/api/entries/{date_str}")
async def upsert_entry(date_str: str, payload: dict, user: dict = Depends(require_editor)):
    """Manual correction of a day's values."""
    _check_date(date_str)
    clean = _clean_fields(payload)
    if clean:
        clean["updatedAt"] = _now()
    # The day as it was, to say in the activity log which values changed.
    before = await _db()["entries"].find_one_and_update(
        {"date": date_str},
        {"$set": clean, "$setOnInsert": {"date": date_str, "source": "manual"}},
        projection={"_id": 0},
        upsert=True,
        return_document=ReturnDocument.BEFORE,
    ) or {}
    changed = [k for k, v in clean.items() if k != "updatedAt" and before.get(k) != v]
    if changed:
        await _log(user["id"], "entry_edited", f"Edited {_day_label(date_str)}: {', '.join(changed)}")
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
async def upload_report(file: UploadFile = File(...), user: dict = Depends(require_editor)):
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
        # The recorded live feed's own figure for the day, when it covers the day.
        # Warnings only: `status` was settled above from the page's own checks.
        extra += live.generation_checks(await _live_day(check.data_date), check.entry)
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
    outcome = "saved" if status == "saved" else "needs review"
    what = f"the report for {_day_label(doc['dataDate'])}" if doc["dataDate"] else "a report with an unreadable date"
    await _log(user["id"], "report_uploaded", f"Uploaded {what} ({outcome})")
    return doc


@app.get("/api/reports", dependencies=[Depends(require_user)])
async def list_reports(month: Optional[str] = None, day: Optional[str] = Query(None, alias="date"),
                       limit: int = 60):
    """Uploaded reports, newest first, without the full transcription. `date`
    (YYYY-MM-DD) or `month` (YYYY-MM) picks the reports whose data is for that day or month."""
    query: dict = {}
    if day:
        query["dataDate"] = _check_date(day).isoformat()
    elif month:
        if not MONTH_RE.match(month):
            raise HTTPException(400, "Invalid month format (YYYY-MM)")
        query["dataDate"] = _month_range(month)
    cursor = _db()["reports"].find(query, {"_id": 0, "raw": 0, "usage": 0}).sort("createdAt", -1)
    return await cursor.to_list(length=max(1, min(limit, 400)))


async def _report_or_404(report_id: str) -> dict:
    doc = await _db()["reports"].find_one({"id": report_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Report not found")
    return doc


@app.get("/api/reports/{report_id}", dependencies=[Depends(require_user)])
async def get_report(report_id: str):
    return await _report_or_404(report_id)


@app.get("/api/reports/{report_id}/image", dependencies=[Depends(require_user)])
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
async def confirm_report(report_id: str, payload: dict, user: dict = Depends(require_editor)):
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
    await _log(user["id"], "report_confirmed", f"Confirmed the report for {_day_label(update['dataDate'])}")
    return {**doc, **update}


# --- derived figures ------------------------------------------------------------------

@app.get("/api/performance/{date_str}", dependencies=[Depends(require_user)])
async def performance(date_str: str):
    """Daily / month-to-date / year-to-date performance report for one date."""
    on = _check_date(date_str)
    fy = calc.fiscal_year(on)
    entries, config = await asyncio.gather(_entries_between(date(fy, 4, 1), on), _config(fy))
    return calc.performance_report(entries, config, on)


@app.get("/api/analytics", dependencies=[Depends(require_user)])
async def get_analytics(on: Optional[str] = None):
    """Trends and things to look at for the Home screen (analytics.py), for
    `on` or by default the latest day with generation data."""
    today = _today()

    def window(day: date) -> tuple[date, date]:
        # The trend windows need LOOKBACK_DAYS of history; month and year
        # progress and the stock roll-forward need the whole fiscal year so far.
        return min(day - timedelta(days=analytics.LOOKBACK_DAYS), date(calc.fiscal_year(day), 4, 1)), day

    if on:
        # The day is known, so all three reads go out at once.
        day = _check_date(on)
        latest, entries, config = await asyncio.gather(
            _latest_data_date(), _entries_between(*window(day)), _config(calc.fiscal_year(day)))
        if latest is None:
            return analytics.empty(today)
    else:
        # The day is the latest with data. Its fiscal year is nearly always
        # today's, so that year's config is read alongside.
        latest, config = await asyncio.gather(_latest_data_date(), _config(calc.fiscal_year(today)))
        if latest is None:
            return analytics.empty(today)
        day = latest
        if calc.fiscal_year(day) != config["fy"]:
            config = await _config(calc.fiscal_year(day))
        entries = await _entries_between(*window(day))
    return analytics.analytics(entries, config, day, today, latest=latest)


@app.get("/api/config/{fy}", dependencies=[Depends(require_user)])
async def get_config(fy: int):
    return await _config(fy)


# What each config key is called in activity lines.
CONFIG_LABELS = {"unitMw": "unit MW", "monthlyTargets": "targets",
                 "coalStockAnchors": "opening coal stock", "oilStockAnchors": "opening oil stock"}


@app.put("/api/config/{fy}")
async def put_config(fy: int, payload: dict, user: dict = Depends(require_editor)):
    """Override targets or opening stocks for a fiscal year."""
    allowed = {k: v for k, v in payload.items() if k in calc.CONFIG_KEYS}
    await _db()["config"].update_one({"fy": fy}, {"$set": allowed, "$setOnInsert": {"fy": fy}}, upsert=True)
    if allowed:
        what = ", ".join(CONFIG_LABELS.get(k, k) for k in allowed)
        await _log(user["id"], "config_changed", f"Changed FY {_fy_label(fy)} {what}")
    return await _config(fy)


@app.post("/api/import/workbook")
async def import_workbook(file: UploadFile = File(...), overwrite: bool = False,
                          user: dict = Depends(require_editor)):
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
    await _log(user["id"], "workbook_imported",
               f"Imported FY {_fy_label(book['fy'])} workbook: {added} added, {updated} updated")
    return {
        "fy": book["fy"],
        "days": len(days),
        "from": min(days) if days else None,
        "to": max(days) if days else None,
        "added": added,
        "updated": updated,
    }


# --- live feed --------------------------------------------------------------------------

async def _fetch_live():
    """The portal's current feed. Cached briefly, so however many screens poll,
    the portal is asked about once every LIVE_CACHE_TTL_S per process."""
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


async def _live_day(day: date) -> dict:
    """live.summarize() of one IST day, from the stored readings."""
    start, end = live.day_window(day)
    readings, config = await asyncio.gather(
        live.readings_between(_db()[LIVE_COLLECTION], start, end), _config(calc.fiscal_year(day)))
    return live.summarize(readings, day, _ist_now(), unit_mw=config["unitMw"])


@app.get("/api/live-generation", dependencies=[Depends(require_user)])
async def live_generation():
    """Proxy the upstream TTPS portal feed (bypasses browser CORS). It never
    writes: the history is recorded by the scheduler alone (/api/live/record).
    If the portal cannot be reached, the last recorded reading is returned in
    the same shape with "stale": true on each item."""
    try:
        data = await _fetch_live()
    except HTTPException as exc:
        last = None
        try:
            last = await live.last_reading(_db()[LIVE_COLLECTION])
        except (HTTPException, PyMongoError) as db_exc:
            print(f"No stored live reading to fall back on: {getattr(db_exc, 'detail', db_exc)}")
        if last is None:
            raise exc
        return live.stale_feed(last)
    return data


@app.api_route("/api/live/record", methods=["GET", "POST"])
async def live_record(key: Optional[str] = None, x_record_key: Optional[str] = Header(None)):
    """Store this minute's sample of the portal's reading. Called every minute
    by an outside scheduler, and the only thing that writes the history. Each
    call stores one document for its minute, even when the portal has not
    published anything new since the last one (feedAt says how old it is).
    The key (LIVE_RECORD_KEY) comes as ?key= or an X-Record-Key header; the
    scheduler has no session, so this route needs none."""
    expected = os.getenv("LIVE_RECORD_KEY")  # read per request, not at import
    if not expected:
        raise HTTPException(503, "Recording is not configured. Set LIVE_RECORD_KEY on the server.")
    given = key or x_record_key or ""
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(401, "Wrong or missing record key")
    reading = live.parse_feed(await _fetch_live())
    if reading is None:
        raise HTTPException(502, "The portal's reply has no readable reading")
    sample = live.sample(reading, _ist_now())
    await _ensure_indexes()
    recorded = await live.record(_db()[LIVE_COLLECTION], sample)
    return {"recorded": recorded, "at": sample["at"], "feedAt": reading["at"], "u1": reading["u1"], "u2": reading["u2"]}


@app.get("/api/live/day", dependencies=[Depends(require_user)])
async def live_day(day: Optional[str] = Query(None, alias="date")):
    """One IST day of recorded readings (default today): load curve, energy,
    PLF, projection, trips. Shape: live.summarize()."""
    return await _live_day(_check_date(day) if day else _today())


# --- readings from pasted WhatsApp messages ------------------------------------------------
#
# A feature of its own: its own collection (logs) and nothing shared with the
# daily entries or the report pages. logbook_forms.py is the fixed set of keys,
# logbook.py reads a paste into it and sets one day beside another.

async def _logs_day(on: str, other: Optional[str] = None) -> dict:
    """One day's sections, each beside the same section on another day: `other`
    when given, else the last earlier day that section was reported."""
    logs = _db()[LOGS_COLLECTION]
    one_date = {"_id": 0, "date": 1}
    records, latest, earlier, later = await asyncio.gather(
        logs.find({"date": on}, {"_id": 0}).to_list(length=None),
        logs.find_one({}, one_date, sort=[("date", -1)]),
        logs.find_one({"date": {"$lt": on}}, one_date, sort=[("date", -1)]),
        logs.find_one({"date": {"$gt": on}}, one_date, sort=[("date", 1)]),
    )
    present = [r["section"] for r in records]
    before = other or (earlier or {}).get("date")
    previous: dict[str, dict] = {}
    absent: list[dict] = []
    if before:
        if other:
            span = {"date": other}
        else:
            start = date.fromisoformat(on) - timedelta(days=LOGS_LOOKBACK_DAYS)
            span = {"date": {"$lt": on, "$gte": start.isoformat()}}
        slim = {"_id": 0, "date": 1, "section": 1, "form": 1, "tag": 1, "values": 1}
        async for doc in logs.find({**span, "section": {"$in": present}}, slim).sort("date", -1):
            previous.setdefault(doc["section"], doc)
        # Reported on the day before this one (or on `other`) and not today: a message that has not come.
        slim.pop("values")
        missing = await logs.find({"date": before, "section": {"$nin": present}}, slim).to_list(length=None)
        absent = [{"id": m["section"], "name": logbook.title(m), "date": m["date"]}
                  for m in sorted(missing, key=logbook.order) if m.get("form") != logbook_forms.OTHER]
    return {
        "date": on,
        "with": other,
        "latest": (latest or {}).get("date"),
        "earlier": (earlier or {}).get("date"),
        "later": (later or {}).get("date"),
        "sections": [logbook.compare(r, previous.get(r["section"])) for r in sorted(records, key=logbook.order)],
        "absent": absent,
    }


@app.get("/api/logs", dependencies=[Depends(require_user)])
async def get_logs(day: Optional[str] = Query(None, alias="date"), other: Optional[str] = Query(None, alias="with")):
    """A day's readings (default: the latest day that has any), compared with
    `with` (YYYY-MM-DD) or else with the last earlier day each section was reported."""
    if day:
        on = _check_date(day).isoformat()
    else:
        latest = await _db()[LOGS_COLLECTION].find_one({}, {"_id": 0, "date": 1}, sort=[("date", -1)])
        on = latest["date"] if latest else _today().isoformat()
    return await _logs_day(on, _check_date(other).isoformat() if other else None)


@app.post("/api/logs")
async def paste_logs(payload: dict, user: dict = Depends(require_editor)):
    """Read pasted WhatsApp messages into the fixed set of keys and store them.

    A day comes in several pastes, in pieces. Each message is filed under the
    date written in it (or its WhatsApp stamp); `date` (default today) is only
    for a piece that carries neither. What a paste brings is added to what the
    day already has for each section: see logbook.update."""
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(400, "Paste the messages first")
    if len(text) > logbook.MAX_CHARS:
        raise HTTPException(413, f"That is {len(text):,} characters; the limit is {logbook.MAX_CHARS:,}. "
                                 "Paste the messages a few at a time: they are put together by their dates.")
    today = _today()
    fallback = _check_date(payload["date"]) if payload.get("date") else today
    if fallback > today + timedelta(days=1):
        raise HTTPException(400, "That day has not come yet")

    lines = logbook.number_lines(text)
    if logbook.too_long(lines):
        raise HTTPException(413, "That is more than can be read in one go. Paste the messages a few at a time: "
                                 "they are put together by their dates.")
    try:
        paste, model, usage = await logbook.read(lines)
    except extract.ExtractionError as exc:
        raise HTTPException(exc.status, str(exc))
    records, notes = logbook.records(paste, lines, fallback, today)
    if not records:
        raise HTTPException(422, "No readings were found in what was pasted.")

    await _ensure_indexes()
    logs = _db()[LOGS_COLLECTION]
    stamp = {"updatedAt": _now(), "updatedBy": {"id": user["id"], "name": user["name"]}, "model": model}
    days: dict[str, dict] = {}
    for record in records:
        # Added to what the day already has for the section: see logbook.update.
        await logs.update_one({"date": record["date"], "section": record["section"]},
                              logbook.update(record, stamp), upsert=True)
        day = days.setdefault(record["date"], {"date": record["date"], "sections": 0, "values": 0, "toCheck": 0,
                                               "undated": 0})
        day["sections"] += 1
        day["values"] += len(record["values"]) + len(record["extra"])
        day["toCheck"] += logbook.to_check(record)
        day["undated"] += not record["dated"]
    summary = sorted(days.values(), key=lambda d: d["date"])
    values = sum(d["values"] for d in summary)
    await _log(user["id"], "logs_pasted",
               f"Pasted readings for {' and '.join(_day_label(d['date']) for d in summary)}: {values} values")
    return {"days": summary, "notes": notes, "model": model, "usage": usage}


async def _log_section(date_str: str, section: str) -> dict:
    record = await _db()[LOGS_COLLECTION].find_one({"date": _check_date(date_str).isoformat(), "section": section},
                                                   {"_id": 0})
    if not record:
        raise HTTPException(404, "No readings are stored for that section on that day")
    return record


@app.put("/api/logs/{date_str}/{section}")
async def edit_log(date_str: str, section: str, payload: dict, user: dict = Depends(require_editor)):
    """Correct one value by hand, {"key": ..., "value": ...} (a blank value
    removes it), or say the section has been looked at, {"checked": true},
    which clears what was marked for checking."""
    record = await _log_section(date_str, section)
    where = {"date": record["date"], "section": section}
    stamp = {"updatedAt": _now(), "updatedBy": {"id": user["id"], "name": user["name"]}}
    name, day = logbook.title(record), _day_label(record["date"])
    if payload.get("checked") is True:
        if logbook.to_check(record):
            await _db()[LOGS_COLLECTION].update_one(where, {"$set": {**stamp, "checks": {}, "missed": []}})
            await _log(user["id"], "logs_edited", f"Checked {name} readings for {day}")
    else:
        form = logbook_forms.BY_KEY.get(record.get("form"))
        field = form.field(payload.get("key")) if form and isinstance(payload.get("key"), str) else None
        if field is None:
            raise HTTPException(400, "That is not one of this section's fields")
        value = logbook.clip(payload.get("value"), logbook.VALUE_MAX)
        if (record.get("values") or {}).get(field.key) != (value or None):
            change: dict = {
                # The number typed is no longer one the reading passed over.
                "$set": {**stamp, "missed": logbook.without_number(record.get("missed") or [], value)},
                "$unset": {f"checks.{field.key}": "", f"src.{field.key}": ""},
                "$addToSet": {"edited": field.key},
            }
            change["$set" if value else "$unset"][f"values.{field.key}"] = value
            await _db()[LOGS_COLLECTION].update_one(where, change)
            await _log(user["id"], "logs_edited", f"Edited {name} readings for {day}: {field.label}")
    return await _logs_day(record["date"], _check_date(payload["with"]).isoformat() if payload.get("with") else None)


@app.delete("/api/logs/{date_str}/{section}")
async def delete_log(date_str: str, section: str, other: Optional[str] = Query(None, alias="with"),
                     user: dict = Depends(require_editor)):
    """Remove a section's readings for a day (a message pasted by mistake)."""
    record = await _log_section(date_str, section)
    await _db()[LOGS_COLLECTION].delete_one({"date": record["date"], "section": section})
    await _log(user["id"], "logs_removed", f"Removed {logbook.title(record)} readings for {_day_label(record['date'])}")
    return await _logs_day(record["date"], _check_date(other).isoformat() if other else None)


# --- sign-in and your own account --------------------------------------------------------

def _https(request: Request) -> bool:
    """Behind Vercel or nginx the app sees plain http; the proxy says what the browser used."""
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return forwarded == "https" or request.url.scheme == "https"


def _cookie_options(request: Request) -> dict:
    # HttpOnly: page scripts never see the token. Lax: other sites cannot post with it.
    return {"path": "/", "httponly": True, "samesite": "lax", "secure": _https(request)}


def _valid(check, value):
    """Run one of auth's input checks; a bad value is a 400 saying what is wrong."""
    try:
        return check(value)
    except auth.Invalid as exc:
        raise HTTPException(400, str(exc))


async def _failed_login(user: dict) -> None:
    """Count a wrong password. The MAX_FAILED_LOGINS-th in a row locks the
    account for LOCK_MINUTES and starts the count again."""
    users = _db()["users"]
    doc = await users.find_one_and_update({"id": user["id"]}, {"$inc": {"failedLogins": 1}},
                                          projection={"failedLogins": 1}, return_document=ReturnDocument.AFTER)
    if doc and doc.get("failedLogins", 0) >= auth.MAX_FAILED_LOGINS:
        until = _utcnow() + timedelta(minutes=auth.LOCK_MINUTES)
        await users.update_one({"id": user["id"]}, {"$set": {"failedLogins": 0, "lockedUntil": auth.iso(until)}})
        raise HTTPException(429, f"Too many attempts. Try again in {auth.LOCK_MINUTES} min.")


@app.post("/api/auth/login")
async def login(payload: dict, request: Request, response: Response):
    """Check the email and password and start a session (an HttpOnly cookie).
    An unknown email and a wrong password get the same answer."""
    email, password = auth.normalize_email(payload.get("email")), payload.get("password")
    if not email or not isinstance(password, str) or not password:
        raise HTTPException(400, "Enter your email and password")
    # A serverless host may have skipped startup: make sure of the unique
    # email index and the super admin before anything else.
    await _ensure_indexes()
    await _seed_super_admin()
    users = _db()["users"]
    user = await users.find_one({"email": email}, {"_id": 0, "activity": 0})
    now = _utcnow()
    if user and (minutes := auth.locked_minutes(user, now)):
        raise HTTPException(429, f"Too many attempts. Try again in {minutes} min.")
    ok = await asyncio.to_thread(auth.verify_password, password, user.get("passwordHash") if user else None)
    if not ok:
        if user:
            await _failed_login(user)
        raise HTTPException(401, "Wrong email or password")

    token = auth.new_token()
    # Expired sessions go first: one update cannot both pull from and push to a list.
    await users.update_one({"id": user["id"]}, {"$pull": {"sessions": {"expiresAt": {"$lte": auth.iso(now)}}}})
    session = auth.new_session(auth.token_hash(token), now, request.headers.get("user-agent"))
    await users.update_one({"id": user["id"]}, {
        "$push": {"sessions": {"$each": [session], "$slice": -auth.SESSIONS_KEPT}},
        "$set": {"lastLoginAt": auth.iso(now), "failedLogins": 0, "lockedUntil": None},
    })
    await _log(user["id"], "login", "Signed in")
    response.set_cookie(auth.COOKIE, token, max_age=auth.SESSION_DAYS * 24 * 3600, **_cookie_options(request))
    return {"user": auth.public_user({**user, "lastLoginAt": auth.iso(now)})}


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    """End this session if the cookie names one. The cookie is cleared whatever happens."""
    token = request.cookies.get(auth.COOKIE)
    if token:
        hashed = auth.token_hash(token)
        try:
            user = await _db()["users"].find_one_and_update(
                {"sessions.hash": hashed}, {"$pull": {"sessions": {"hash": hashed}}}, projection={"id": 1})
            if user:
                await _log(user["id"], "logout", "Signed out")
        except (HTTPException, PyMongoError) as exc:
            print(f"Could not end the session: {getattr(exc, 'detail', exc)}")
    response.delete_cookie(auth.COOKIE, **_cookie_options(request))
    return {"ok": True}


@app.get("/api/auth/me")
async def me(user: dict = Depends(require_user)):
    return {"user": auth.public_user(user)}


@app.patch("/api/auth/me")
async def update_me(payload: dict, user: dict = Depends(require_user)):
    """Change your own name. The email never changes."""
    name = _valid(auth.check_name, payload.get("name"))
    if name != user["name"]:
        await _db()["users"].update_one({"id": user["id"]}, {"$set": {"name": name, "updatedAt": _now()}})
        await _log(user["id"], "name_changed", f"Changed name to {name}")
    return {"user": auth.public_user({**user, "name": name})}


@app.post("/api/auth/password")
async def change_password(payload: dict, request: Request, user: dict = Depends(require_user)):
    """Change your own password. Every other session of yours ends; this one
    stays. A wrong current password is a 400, not a 401, so the app does not
    take it as being signed out."""
    new = _valid(auth.check_password, payload.get("newPassword"))
    current = payload.get("currentPassword")
    if not isinstance(current, str) or not await asyncio.to_thread(
            auth.verify_password, current, user.get("passwordHash")):
        raise HTTPException(400, "Current password is wrong")
    password_hash = await asyncio.to_thread(auth.hash_password, new)
    await _db()["users"].update_one({"id": user["id"]}, {
        "$set": {"passwordHash": password_hash, "updatedAt": _now()},
        "$pull": {"sessions": {"hash": {"$ne": request.state.session_hash}}},
    })
    await _log(user["id"], "password_changed", "Changed password")
    return {"ok": True}


async def _activity(user_id: str, limit: int) -> list[dict]:
    doc = await _db()["users"].find_one({"id": user_id}, {"_id": 0, "activity": 1})
    if doc is None:
        raise HTTPException(404, "User not found")
    return auth.newest_first(doc.get("activity"), limit)


@app.get("/api/auth/activity")
async def my_activity(limit: int = 100, user: dict = Depends(require_user)):
    """Your own activity, newest first (limit 1 to 200)."""
    return await _activity(user["id"], limit)


# --- managing users (super admin only) -------------------------------------------------------

# A user without what the API never sends (the hash, sessions, activity).
USER_FIELDS = {"_id": 0, "passwordHash": 0, "sessions": 0, "activity": 0}


async def _user_or_404(user_id: str) -> dict:
    doc = await _db()["users"].find_one({"id": user_id}, USER_FIELDS)
    if not doc:
        raise HTTPException(404, "User not found")
    return doc


def _role_phrase(role: str) -> str:
    return "an admin" if role == auth.ADMIN else "a viewer"


@app.get("/api/users", dependencies=[Depends(require_super_admin)])
async def list_users():
    """Everyone, the super admin first, then by name."""
    users = await _db()["users"].find({}, USER_FIELDS).to_list(length=None)
    users.sort(key=lambda u: (u.get("role") != auth.SUPER_ADMIN, (u.get("name") or "").lower()))
    return [auth.public_user(u) for u in users]


@app.post("/api/users", status_code=201)
async def create_user(payload: dict, actor: dict = Depends(require_super_admin)):
    """Onboard someone as admin or viewer. The super admin hands them the first password."""
    email = _valid(auth.check_email, payload.get("email"))
    name = _valid(auth.check_name, payload.get("name"))
    password = _valid(auth.check_password, payload.get("password"))
    role = _valid(auth.check_role, payload.get("role"))
    users = _db()["users"]
    taken = HTTPException(409, "Someone with this email already exists")
    if await users.find_one({"email": email}, {"_id": 1}):
        raise taken
    doc = _new_user(email, name, role, await asyncio.to_thread(auth.hash_password, password), created_by=actor)
    await _ensure_indexes()  # the unique email index settles two onboardings at once
    try:
        await users.insert_one(doc)
    except DuplicateKeyError:
        raise taken
    await _log(actor["id"], "user_created", f"Onboarded {name} ({email}) as {role}")
    return {"user": auth.public_user(doc)}


@app.patch("/api/users/{user_id}")
async def update_user(user_id: str, payload: dict, actor: dict = Depends(require_super_admin)):
    """Rename someone or switch them between admin and viewer. The email never changes."""
    target = await _user_or_404(user_id)
    if target["role"] == auth.SUPER_ADMIN or target["id"] == actor["id"]:
        raise HTTPException(400, "The super admin's access cannot change" if "role" in payload
                            else "Use Account to change your own name")
    changes = {}
    if payload.get("name") is not None:
        changes["name"] = _valid(auth.check_name, payload["name"])
    if payload.get("role") is not None:
        changes["role"] = _valid(auth.check_role, payload["role"])
    changes = {k: v for k, v in changes.items() if v != target.get(k)}
    if not changes:
        return {"user": auth.public_user(target)}
    await _db()["users"].update_one({"id": user_id}, {"$set": {**changes, "updatedAt": _now()}})
    old_name = target["name"]
    target.update(changes)
    logs = []
    if "name" in changes:
        logs += [_log(actor["id"], "user_updated", f"Renamed {old_name} to {target['name']}"),
                 _log(user_id, "name_changed", f"Name changed to {target['name']} by {actor['name']}")]
    if "role" in changes:
        logs += [_log(actor["id"], "user_updated", f"Made {target['name']} {_role_phrase(target['role'])}"),
                 _log(user_id, "role_changed", f"Access changed to {target['role']} by {actor['name']}")]
    await asyncio.gather(*logs)
    return {"user": auth.public_user(target)}


@app.post("/api/users/{user_id}/password")
async def set_user_password(user_id: str, payload: dict, actor: dict = Depends(require_super_admin)):
    """Set a new password for someone who forgot theirs. All their sessions end
    and any lockout is lifted."""
    target = await _user_or_404(user_id)
    if target["id"] == actor["id"] or target["role"] == auth.SUPER_ADMIN:
        raise HTTPException(400, "Use Account to change your own password")
    password = _valid(auth.check_password, payload.get("password"))
    password_hash = await asyncio.to_thread(auth.hash_password, password)
    await _db()["users"].update_one({"id": user_id}, {"$set": {
        "passwordHash": password_hash, "sessions": [], "failedLogins": 0, "lockedUntil": None, "updatedAt": _now(),
    }})
    await asyncio.gather(_log(actor["id"], "user_password_set", f"Set a new password for {target['name']}"),
                         _log(user_id, "password_set", f"Password set by {actor['name']}"))
    return {"ok": True}


@app.delete("/api/users/{user_id}")
async def delete_user(user_id: str, actor: dict = Depends(require_super_admin)):
    """Remove someone. Their sessions go with them, so they are signed out at once."""
    target = await _user_or_404(user_id)
    if target["id"] == actor["id"]:
        raise HTTPException(400, "You cannot remove yourself")
    if target["role"] == auth.SUPER_ADMIN:
        raise HTTPException(400, "The super admin cannot be removed")
    await _db()["users"].delete_one({"id": user_id})
    await _log(actor["id"], "user_deleted", f"Removed {target['name']} ({target['email']})")
    return {"ok": True}


@app.get("/api/users/{user_id}/activity", dependencies=[Depends(require_super_admin)])
async def user_activity(user_id: str, limit: int = 100):
    """Someone's activity, newest first (limit 1 to 200)."""
    return await _activity(user_id, limit)
