"""Run the API locally without MongoDB or a Gemini key.

    cd backend && .venv/bin/python dev_server.py

- The database lives in memory and is seeded from the plant workbook in the
  project root, so month and year figures are realistic.
- If GEMINI_API_KEY is not set, report images are not really read: the two
  sample pages in the project root return their hand-checked transcriptions
  (recognised by image shape). Any other portrait image returns a page with one
  wrong digit, to exercise the needs-review path, and a landscape image is
  rejected as not being a report.
- Live readings start empty. DEV_SEED_LIVE=1 fills today from 00:00 to now with
  a synthetic day (every 2 minutes, 140-165 MW, one Unit 2 trip and return),
  so the Home screen's load curve has something to draw.
- Three users are created, one per role, all with the password DEV_PASSWORD,
  and printed at startup.
- The Logs screen starts with three sample days (10 to 12 Nov 2026) made from
  the two days of WhatsApp messages in tests/fixtures, so there is something to
  compare. Without GEMINI_API_KEY only those two sample pastes can be read.

Nothing here is used in production; main.py is the real entry point.
"""

import asyncio
import json
import math
import os
import random
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import uvicorn
from mongomock_motor import AsyncMongoMockClient

os.environ.setdefault("MONGODB_URI", "")
import main  # noqa: E402
import auth  # noqa: E402
import extract  # noqa: E402
import live  # noqa: E402
import logbook  # noqa: E402
import workbook_import  # noqa: E402
from report_schema import DailySystemReport  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "tests" / "fixtures"

main.db = AsyncMongoMockClient()["ttps_dev"]


def _fixture(name: str) -> DailySystemReport:
    return DailySystemReport.model_validate(json.loads((FIXTURES / name).read_text()))


async def fake_extract(image, recheck=None):
    """Stand-in for the vision call, chosen by the shape of the uploaded image."""
    ratio = image.width / image.height
    await asyncio.sleep(1.5)  # a real read takes a while; keep the UI honest
    if ratio > 1.2:  # landscape: not a report page
        report = _fixture("report_2026-11-04.json")
        report.is_daily_system_report = False
    elif 0.76 <= ratio <= 0.80:  # the sample screenshot (1414 x 1810)
        report = _fixture("report_2026-11-04.json")
    elif 0.68 <= ratio <= 0.72:  # the sample phone photo (1119 x 1599)
        report = _fixture("report_2026-11-11.json")
    else:  # any other portrait image: a page with one misread digit
        report = _fixture("report_2026-11-04.json")
        report.r04_gen.unit1 = "3.43"  # totals and PLF no longer agree
    return extract.Extraction(report=report, model="dev-fixture", usage={"inputTokens": 0, "outputTokens": 0})


def _log_fixtures() -> list[tuple[list[str], logbook.Paste]]:
    """The sample days of messages with the answers checked for them."""
    return [(logbook.number_lines(path.read_text()),
             logbook.Paste.model_validate_json(path.with_suffix(".json").read_text()))
            for path in sorted(FIXTURES.glob("logs_*.txt"))]


async def fake_read_logs(lines, model=None):
    """Stand-in for the model call that reads pasted messages: the sample
    pastes return their checked answers, anything else cannot be read."""
    await asyncio.sleep(1.5)
    pasted = "\n".join(lines).strip()
    for sample, answer in _log_fixtures():
        if "\n".join(sample).strip() == pasted:
            return answer, "dev-fixture", {"inputTokens": 0, "outputTokens": 0, "thinkingTokens": None}
    raise extract.ExtractionError(
        "GEMINI_API_KEY is not set, so this development server can only read the sample messages in "
        "backend/tests/fixtures (logs_*.txt).", status=503)


if not extract.is_configured():
    main.extract.extract_report = fake_extract
    logbook.read = fake_read_logs


async def seed() -> None:
    books = sorted(ROOT.glob("TTPS DAILY GEN DATA*.xlsx"))
    if not books:
        print("dev: no workbook found in the project root, starting empty")
        return
    book = workbook_import.read_workbook(books[-1].read_bytes())
    for row in book["entries"]:
        await main.db["entries"].insert_one({**row, "source": "workbook"})
    if book["config"]:
        await main.db["config"].insert_one({"fy": book["fy"], **book["config"]})
    print(f"dev: seeded {len(book['entries'])} days from {books[-1].name}")


def _another_day(record: dict, day: str, seed: int) -> dict:
    """The same section on another day, with some of its numbers a little off, so
    the Logs screen has a day to compare with. Made up: no message says this."""
    rng = random.Random(f"{day}-{record['section']}-{seed}")
    values = {}
    for key, value in record["values"].items():
        number = logbook.parse_number(value)
        if number is not None and rng.random() < 0.3:
            places = len(value.split(".")[1]) if "." in value else 0
            step = rng.choice((-3, -2, -1, 1, 2, 3)) * 10 ** -places
            value = f"{max(number + step, 0) if number >= 0 else number + step:.{places}f}"
        values[key] = value
    return {**record, "date": day, "values": values, "src": {}, "pieces": [], "checks": {}, "missed": [], "extra": []}


async def seed_logs() -> None:
    fixtures = _log_fixtures()
    if len(fixtures) < 2:
        return
    stamp = {"updatedAt": main._now(), "updatedBy": {"id": None, "name": "Sample data"}, "model": "dev-fixture"}
    sample_today = date(2026, 11, 13)  # the fixtures' dates are read against this, whenever the server runs
    (first, _), (second, _) = (logbook.records(answer, lines, sample_today, sample_today) for lines, answer in fixtures)
    days = first + second
    days += [_another_day(r, "2026-11-10", 1) for r in first] + [_another_day(r, "2026-11-11", 2) for r in second]
    await main.db[main.LOGS_COLLECTION].insert_many([{**r, **stamp} for r in days])
    print(f"dev: seeded {len(days)} sections of sample readings for 10 to 12 Nov 2026 (Logs)")


DEV_PASSWORD = "ttps-dev-pass"
# One sign-in per role. With one here, SUPERADMIN_* from .env is not used.
DEV_USERS = (
    ("super@ttps.local", "Dev Super", auth.SUPER_ADMIN),
    ("admin@ttps.local", "Dev Admin", auth.ADMIN),
    ("viewer@ttps.local", "Dev Viewer", auth.VIEWER),
)


async def seed_users() -> None:
    for email, name, role in DEV_USERS:
        if not await main.db["users"].find_one({"email": email}):
            await main.db["users"].insert_one(main._new_user(email, name, role, auth.hash_password(DEV_PASSWORD)))
    print(f"dev: sign in with the password {DEV_PASSWORD} as")
    for email, name, role in DEV_USERS:
        print(f"dev:   {email:<18} {name} ({role})")


def synthetic_day(now: datetime) -> list[dict]:
    """Readings every 2 minutes from today 00:00 IST to `now`: both units
    around 140-165 MW, following a daily swing, with Unit 2 tripping a little
    before the middle of the day so far and coming back about two hours later."""
    start = datetime.combine(now.date(), time(0), live.IST)
    elapsed = now - start
    trip_at = start + elapsed * 0.45
    back_at = trip_at + min(timedelta(hours=2), elapsed * 0.2)
    ramp = timedelta(minutes=50)  # back on the grid at ~20 MW, then loading up
    rng = random.Random(now.date().toordinal())  # the same day each restart
    readings = []
    t = start
    while t <= now:
        hour = (t - start).total_seconds() / 3600
        # Low in the small hours, highest in the evening peak.
        swing = 152 + 9 * math.sin((hour - 13) / 24 * 2 * math.pi)
        u1 = min(max(swing + rng.uniform(-3, 3), 140), 165)
        u2 = min(max(swing + 2 + rng.uniform(-3, 3), 140), 165)
        if trip_at <= t < back_at:
            u2 = rng.uniform(0, 1.5)  # a stopped unit's feed hovers just above zero
        elif back_at <= t < back_at + ramp:
            u2 = 20 + (u2 - 20) * (t - back_at) / ramp
        at = live.minute_key(t)
        readings.append({"at": at, "ts": t.astimezone(timezone.utc), "u1": round(u1, 2), "u2": round(u2, 2),
                         "u1At": at, "u2At": at})
        t += timedelta(minutes=2)
    return readings


async def seed_live() -> None:
    readings = synthetic_day(main._ist_now())
    if readings:
        await main.db[main.LIVE_COLLECTION].insert_many([live.to_doc(r) for r in readings])
    print(f"dev: seeded {len(readings)} synthetic live readings for today")


if __name__ == "__main__":
    asyncio.run(seed())
    asyncio.run(seed_users())
    asyncio.run(seed_logs())
    if os.getenv("DEV_SEED_LIVE") == "1":
        asyncio.run(seed_live())
    uvicorn.run(main.app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
