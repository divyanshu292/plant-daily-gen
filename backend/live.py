"""The plant portal's live MW feed: parse it, store it, and sum up a day of it.

The portal shows each unit's load to the minute and keeps no history, so every
reading is stored as it arrives (main.py records it when the Home screen polls
and when an outside scheduler calls /api/live/record). From those readings:

- the day's load curve and its energy, integrated over the spans with no long
  gap between readings,
- PLF over the hours covered, and a projection for the rest of today,
- trips, stops and returns to service,
- an independent check of the generation printed on an uploaded report.

Everything here except the small storage helpers at the end is pure, and the
response shape is a contract with the frontend (GET /api/live/day).
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from pymongo.errors import DuplicateKeyError

from validate import Check

IST = ZoneInfo("Asia/Kolkata")
UNITS = (1, 2)
UNIT_MW = 210  # used when the fiscal year's config does not say otherwise
HOURS_PER_DAY = 24

# Readings arrive about every 2 minutes. Across a longer gap the load is not
# known, so that stretch is neither integrated nor counted as covered.
MAX_GAP_MIN = 15
# Below this a unit is offline: a stopped unit's feed shows a small non-zero value.
OFFLINE_MW = 5
# A trip is a sudden fall to offline from real load, seen between two readings
# close together. Any other fall to offline (a ramp down, or across a gap in the
# readings) is a stop.
TRIP_FROM_MW = 50
TRIP_WITHIN_MIN = 10
# A day is "complete" once readings cover this share of its hours.
COMPLETE_SHARE = 0.95
# Upload cross-check: the page's unit generation may differ from the feed's by this much.
CHECK_TOLERANCE_PCT = 3.0
CHECK_TOLERANCE_MU = 0.1

MAX_GAP = timedelta(minutes=MAX_GAP_MIN)
TRIP_WITHIN = timedelta(minutes=TRIP_WITHIN_MIN)

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_MONTH_NUMBER = {m.lower(): i for i, m in enumerate(_MONTHS, 1)}
# "12-Nov-2026 20:55", IST. Seconds, if the portal ever sends them, are dropped.
_STAMP_RE = re.compile(r"^\s*(\d{1,2})-([A-Za-z]{3})-(\d{4})\s+(\d{1,2}):(\d{2})")
# "Power generation Unit-1" / "Power Generation Unit-2": the portal's own
# capitalisation varies, and the array order is not promised.
_UNIT_RE = re.compile(r"unit[\s-]*([12])\b", re.IGNORECASE)


# --- the feed ----------------------------------------------------------------------------

def parse_stamp(text) -> datetime | None:
    """A feed timestamp ('12-Nov-2026 20:55', IST) as an aware datetime, or None."""
    m = _STAMP_RE.match(str(text or ""))
    if not m:
        return None
    day, mon, year, hour, minute = m.groups()
    month = _MONTH_NUMBER.get(mon.lower())
    if month is None:
        return None
    try:
        return datetime(int(year), month, int(day), int(hour), int(minute), tzinfo=IST)
    except ValueError:
        return None


def minute_key(moment: datetime) -> str:
    """The IST minute of `moment` as '2026-11-12T21:54': a reading's _id."""
    return moment.astimezone(IST).strftime("%Y-%m-%dT%H:%M")


def key_time(key: str) -> datetime:
    """Inverse of minute_key."""
    return datetime.fromisoformat(key).replace(tzinfo=IST)


def feed_stamp(key: str) -> str:
    """'2026-11-12T20:55' in the portal's own form, '12-Nov-2026 20:55'."""
    t = datetime.fromisoformat(key)
    return f"{t.day:02d}-{_MONTHS[t.month - 1]}-{t.year} {t:%H:%M}"


def _power(item: dict) -> float | None:
    value = (item.get("readings") or {}).get("power")
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_feed(data) -> dict | None:
    """The portal's array as one reading, or None if no unit carries a readable stamp.

    {"at": "2026-11-12T20:55", "ts": <UTC datetime>, "u1": 146.41, "u2": 156.56,
     "u1At": "2026-11-12T20:55", "u2At": "2026-11-12T20:55"}

    Units are matched by station name. If their stamps differ, the reading is
    keyed on the later one and each unit keeps its own stamp.
    """
    if not isinstance(data, list):
        return None
    units: dict[int, tuple[float | None, datetime | None]] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        m = _UNIT_RE.search(str(item.get("station") or ""))
        if m and int(m.group(1)) not in units:
            units[int(m.group(1))] = (_power(item), parse_stamp(item.get("timestamp")))
    stamps = [stamp for _, stamp in units.values() if stamp is not None]
    if not stamps:
        return None
    latest = max(stamps)
    reading: dict = {"at": minute_key(latest), "ts": latest.astimezone(timezone.utc)}
    for n in UNITS:
        mw, stamp = units.get(n, (None, None))
        reading[f"u{n}"] = mw
        reading[f"u{n}At"] = minute_key(stamp) if stamp else None
    return reading


def stale_feed(reading: dict) -> list[dict]:
    """A stored reading in the portal's own array shape, marked stale: served
    when the portal cannot be reached."""
    return [{
        "station": f"Power Generation Unit-{n}",
        "readings": {"power": reading.get(f"u{n}")},
        "units": {"power": "MW"},
        "timestamp": feed_stamp(reading.get(f"u{n}At") or reading["at"]),
        "stale": True,
    } for n in UNITS]


# --- a day of readings -------------------------------------------------------------------

def day_bounds(day: date) -> tuple[datetime, datetime]:
    """00:00 to 24:00 IST."""
    start = datetime.combine(day, time(0), IST)
    return start, start + timedelta(days=1)


def day_window(day: date) -> tuple[datetime, datetime]:
    """The readings summarize() needs for `day`: the day itself plus MAX_GAP
    either side, so the minutes around midnight are integrated (and a trip
    just after midnight is seen) from the neighbouring readings."""
    start, end = day_bounds(day)
    return start - MAX_GAP, end + MAX_GAP


def integrate(series: list[tuple[datetime, dict]], start: datetime, end: datetime) -> tuple[dict[int, float], float]:
    """Energy per unit (MU) and hours covered between `start` and `end`.

    `series` is (time, reading) oldest first. Each pair of consecutive readings
    at most MAX_GAP apart contributes a trapezoid, clipped to [start, end]
    along the straight line between the two. A unit missing from either end of
    a pair adds nothing for that stretch.
    """
    energy = {n: 0.0 for n in UNITS}
    covered = timedelta(0)  # summed exactly, so a day at the COMPLETE_SHARE boundary is not a float's whim
    for (t0, r0), (t1, r1) in zip(series, series[1:]):
        if t1 - t0 > MAX_GAP:
            continue
        a, b = max(t0, start), min(t1, end)
        if b <= a:
            continue
        covered += b - a
        hours = (b - a).total_seconds() / 3600
        span = (t1 - t0).total_seconds()
        for n in UNITS:
            v0, v1 = r0.get(f"u{n}"), r1.get(f"u{n}")
            if v0 is None or v1 is None:
                continue
            va = v0 + (v1 - v0) * (a - t0).total_seconds() / span
            vb = v0 + (v1 - v0) * (b - t0).total_seconds() / span
            energy[n] += (va + vb) / 2 * hours / 1000  # MW x h = MWh; / 1000 = MU
    return energy, covered.total_seconds() / 3600


def events(series: list[tuple[datetime, dict]], start: datetime, end: datetime) -> list[dict]:
    """Trips, stops and returns to service between `start` and `end`, oldest first.

    `series` may begin with a reading before `start`: it sets each unit's state
    without producing an event of its own.
    """
    out: list[dict] = []
    for n in UNITS:
        prev: tuple[datetime, float] | None = None
        for t, r in series:
            mw = r.get(f"u{n}")
            if mw is None:
                continue
            if prev is not None and start <= t < end:
                pt, pmw = prev
                if pmw >= OFFLINE_MW > mw:
                    tripped = pmw >= TRIP_FROM_MW and t - pt <= TRIP_WITHIN
                    out.append({"unit": n, "kind": "trip" if tripped else "stop", "at": r["at"], "fromMw": pmw})
                elif pmw < OFFLINE_MW <= mw:
                    out.append({"unit": n, "kind": "back", "at": r["at"]})
            prev = (t, mw)
    return sorted(out, key=lambda e: (e["at"], e["unit"]))


def _round(value: float | None, dp: int) -> float | None:
    return None if value is None else round(value, dp)


def summarize(readings: list[dict], day: date, now: datetime, unit_mw: float = UNIT_MW) -> dict:
    """The GET /api/live/day response for `day` (IST), as seen at `now`.

    `readings` are stored readings ({"at", "u1", "u2", ...}) in any order; those
    outside the day are used only at its edges (see day_window).
    """
    start, end = day_bounds(day)
    timed = sorted(((key_time(r["at"]), r) for r in readings), key=lambda tr: tr[0])
    inside = [(t, r) for t, r in timed if start <= t < end]
    before = [(t, r) for t, r in timed if t < start][-1:]
    after = [(t, r) for t, r in timed if t >= end][:1]

    energy, covered = integrate(before + inside + after, start, end)
    stn = sum(energy.values())

    today = now.astimezone(IST).date()
    is_today = day == today
    if day < today:
        elapsed = float(HOURS_PER_DAY)
    elif day > today:
        elapsed = 0.0
    else:
        elapsed = min(max((now - start).total_seconds() / 3600, 0.0), HOURS_PER_DAY)

    def plf(mu: float, units: int) -> float | None:
        return None if covered <= 0 else _round(mu / (unit_mw * units * covered / 1000) * 100, 1)

    # Each unit's latest value of the day.
    latest: dict[int, float] = {}
    for _, r in inside:
        for n in UNITS:
            if r.get(f"u{n}") is not None:
                latest[n] = r[f"u{n}"]

    projected = None
    if is_today and latest:
        # The rest of the day at the station's present load.
        projected = {"stn": _round(stn + sum(latest.values()) * (HOURS_PER_DAY - elapsed) / 1000, 3)}

    return {
        "date": day.isoformat(),
        "isToday": is_today,
        "unitMw": unit_mw,
        "points": [{"at": r["at"], "u1": r.get("u1"), "u2": r.get("u2")} for _, r in inside],
        "lastAt": inside[-1][1]["at"] if inside else None,
        "hours": {"elapsed": _round(elapsed, 2), "covered": _round(covered, 2)},
        "energy": {"u1": _round(energy[1], 3), "u2": _round(energy[2], 3), "stn": _round(stn, 3)},
        "plf": {"u1": plf(energy[1], 1), "u2": plf(energy[2], 1), "stn": plf(stn, 2)},
        "projected": projected,
        "complete": covered >= COMPLETE_SHARE * HOURS_PER_DAY,
        "events": events(before + inside, start, end),
        "offline": [n for n in UNITS if n in latest and latest[n] < OFFLINE_MW],
    }


def generation_checks(summary: dict, entry: dict) -> list[Check]:
    """Warnings comparing a report's unit generation with the feed's, for a day
    the feed covers (`summary` from summarize); none for a day it does not.

    The few uncovered minutes of a complete day are filled at the unit's average
    load over the covered hours.
    """
    covered = summary["hours"]["covered"]
    if not summary["complete"] or not covered:
        return []
    checks: list[Check] = []
    for n in UNITS:
        page = entry.get(f"u{n}Gen")
        if page is None:
            continue
        feed = summary["energy"][f"u{n}"] * HOURS_PER_DAY / covered
        tolerance = max(CHECK_TOLERANCE_PCT / 100 * feed, CHECK_TOLERANCE_MU)
        checks.append(Check(
            f"live_gen_u{n}", f"Generation Unit {n} matches the live feed", abs(page - feed) <= tolerance, "warn",
            f"Unit {n}: page {page:.2f} MU, live feed {feed:.2f} MU", [f"r04_gen.unit{n}"],
        ))
    return checks


# --- storage -----------------------------------------------------------------------------
# One document per feed minute in the live_readings collection:
#   {_id: "2026-11-12T21:54" (IST), ts: <BSON date, UTC>, u1, u2, u1At, u2At}
# ts carries the TTL index (main.py), which also serves the range reads below.

def to_doc(reading: dict) -> dict:
    return {"_id": reading["at"], **{k: reading.get(k) for k in ("ts", "u1", "u2", "u1At", "u2At")}}


def from_doc(doc: dict) -> dict:
    return {"at": doc["_id"], **{k: doc.get(k) for k in ("u1", "u2", "u1At", "u2At")}}


async def record(collection, reading: dict) -> bool:
    """Store a reading unless its minute is already stored. True if it was new.

    Keyed on the feed minute with $setOnInsert, so every poller and the
    scheduler can record the same reading and it is stored once, as first seen.
    """
    doc = to_doc(reading)
    del doc["_id"]  # the filter supplies it
    try:
        result = await collection.update_one({"_id": reading["at"]}, {"$setOnInsert": doc}, upsert=True)
    except DuplicateKeyError:
        return False  # another recorder inserted the same minute at the same moment
    return result.upserted_id is not None


async def last_reading(collection) -> dict | None:
    doc = await collection.find_one({}, sort=[("ts", -1)])
    return from_doc(doc) if doc else None


async def readings_between(collection, start: datetime, end: datetime) -> list[dict]:
    # A day is about 720 readings: fetch them in one batch.
    cursor = collection.find({"ts": {"$gte": start, "$lte": end}}).sort("ts", 1).batch_size(2000)
    return [from_doc(doc) for doc in await cursor.to_list(length=None)]
