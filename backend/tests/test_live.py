"""The live feed: parsing, a day's figures (live.py) and the API that records them."""

from __future__ import annotations

import asyncio
import io
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient
from PIL import Image
from pymongo.errors import ServerSelectionTimeoutError

import extract
import live
import main
from helpers import PAGE_1, load_report

IST = live.IST
NOW = datetime(2026, 11, 12, 21, 0, tzinfo=IST)
DAY = date(2026, 11, 12)


def feed(u1=146.41, u2=156.56, stamp="12-Nov-2026 20:55", stamp2=None) -> list[dict]:
    """The portal's reply, as in the contract."""
    return [
        {"station": "Power generation Unit-1", "readings": {"power": u1}, "units": {"power": "MW"},
         "timestamp": stamp},
        {"station": "Power Generation Unit-2", "readings": {"power": u2}, "units": {"power": "MW"},
         "timestamp": stamp2 or stamp},
    ]


def reading(at: str, u1: float | None, u2: float | None) -> dict:
    """A reading as parse_feed() gives it, for the minute `at` (IST)."""
    return {"at": at, "ts": live.key_time(at).astimezone(timezone.utc), "u1": u1, "u2": u2, "u1At": at, "u2At": at}


def series(start: str, end: str, u1, u2, step_min: int = 2) -> list[dict]:
    """Readings every `step_min` from `start` to `end` inclusive (IST minutes).
    u1 and u2 are numbers or functions of the reading's time."""
    t, stop = live.key_time(start), live.key_time(end)
    out = []
    while t <= stop:
        out.append(reading(live.minute_key(t), u1(t) if callable(u1) else u1, u2(t) if callable(u2) else u2))
        t += timedelta(minutes=step_min)
    return out


# --- parsing the feed ---------------------------------------------------------------------------

def test_parse_feed():
    r = live.parse_feed(feed())
    assert r == {"at": "2026-11-12T20:55", "ts": datetime(2026, 11, 12, 15, 25, tzinfo=timezone.utc),
                 "u1": 146.41, "u2": 156.56, "u1At": "2026-11-12T20:55", "u2At": "2026-11-12T20:55"}


def test_units_are_matched_by_name_not_position():
    items = feed(u1=100.0, u2=200.0)
    items.reverse()
    items[0]["station"] = "POWER GENERATION UNIT - 2"
    r = live.parse_feed([{"station": "Station total", "readings": {"power": 300.0}}, *items])
    assert (r["u1"], r["u2"]) == (100.0, 200.0)


def test_units_with_different_stamps_key_on_the_later():
    r = live.parse_feed(feed(stamp="12-Nov-2026 20:53", stamp2="12-nov-2026 20:55"))
    assert r["at"] == "2026-11-12T20:55" and r["ts"] == datetime(2026, 11, 12, 15, 25, tzinfo=timezone.utc)
    assert (r["u1At"], r["u2At"]) == ("2026-11-12T20:53", "2026-11-12T20:55")


def test_parse_feed_tolerates_odd_values():
    items = feed()
    items[0]["readings"]["power"] = "146.41"
    items[1]["readings"] = {}
    r = live.parse_feed(items)
    assert (r["u1"], r["u2"]) == (146.41, None)

    # A unit without a readable stamp keeps its value; the other unit keys the reading.
    r = live.parse_feed(feed(stamp="soon", stamp2="12-Nov-2026 20:55"))
    assert (r["at"], r["u1"], r["u1At"]) == ("2026-11-12T20:55", 146.41, None)

    # A missing unit is None.
    r = live.parse_feed(feed()[:1])
    assert (r["u1"], r["u2"], r["u2At"]) == (146.41, None, None)

    for bad in (None, {}, "<html>", [], [{"station": "Unit-1", "timestamp": "31-Feb-2026 10:00"}],
                feed(stamp="12-Nvm-2026 20:55"), [{"station": "Unit-3", "timestamp": "12-Nov-2026 20:55"}]):
        assert live.parse_feed(bad) is None
    assert live.parse_feed(feed(u1=float("nan"), u2=True))["u1"] is None
    assert live.parse_feed(feed(u2=True))["u2"] is None


def test_stamps_round_trip():
    assert live.parse_stamp("2-Nov-2026 7:05") == datetime(2026, 11, 2, 7, 5, tzinfo=IST)
    assert live.parse_stamp("12-Nov-2026 20:55:41") == datetime(2026, 11, 12, 20, 55, tzinfo=IST)
    assert live.feed_stamp("2026-11-02T07:05") == "02-Nov-2026 07:05"
    assert live.parse_stamp(live.feed_stamp("2026-11-12T20:55")) == live.key_time("2026-11-12T20:55")


def test_stale_feed_has_the_portal_shape():
    stored = {"at": "2026-11-12T20:55", "u1": 146.41, "u2": None, "u1At": "2026-11-12T20:53", "u2At": None}
    items = live.stale_feed(stored)
    assert items == [
        {"station": "Power Generation Unit-1", "readings": {"power": 146.41}, "units": {"power": "MW"},
         "timestamp": "12-Nov-2026 20:53", "stale": True},
        {"station": "Power Generation Unit-2", "readings": {"power": None}, "units": {"power": "MW"},
         "timestamp": "12-Nov-2026 20:55", "stale": True},
    ]
    assert live.parse_feed(items)["at"] == "2026-11-12T20:55"


# --- energy and hours ------------------------------------------------------------------------------

def summarize(readings, day=DAY, now=NOW, **kw):
    return live.summarize(readings, day, now, **kw)


def test_constant_load_for_a_day_is_its_mw_times_24_hours():
    # 00:00 to the next 00:00: the reading at midnight closes the last stretch.
    readings = series("2026-11-11T00:00", "2026-11-12T00:00", 150.0, 150.0)
    s = summarize(readings, day=date(2026, 11, 11))
    assert s["energy"] == {"u1": 3.6, "u2": 3.6, "stn": 7.2}
    assert s["hours"] == {"elapsed": 24.0, "covered": 24.0}
    assert s["complete"] is True and s["isToday"] is False and s["projected"] is None
    assert s["plf"] == {"u1": 71.4, "u2": 71.4, "stn": 71.4}  # 150 / 210
    # Only the day's own readings are listed.
    assert len(s["points"]) == 720 and s["points"][0] == {"at": "2026-11-11T00:00", "u1": 150.0, "u2": 150.0}
    assert s["lastAt"] == "2026-11-11T23:58"


def test_a_ramp_is_integrated_as_a_trapezoid():
    energy, covered = live.integrate(
        [(live.key_time(r["at"]), r) for r in (reading("2026-11-12T10:00", 0.0, 100.0),
                                                reading("2026-11-12T10:10", 120.0, 100.0))],
        *live.day_bounds(DAY))
    assert covered == pytest.approx(10 / 60)
    assert energy[1] == pytest.approx(60 * 10 / 60 / 1000) and energy[2] == pytest.approx(100 * 10 / 60 / 1000)


def test_gaps_over_fifteen_minutes_are_not_integrated():
    readings = [
        *series("2026-11-12T00:00", "2026-11-12T06:00", 150.0, 150.0),
        # 15 minutes later still counts...
        *series("2026-11-12T06:15", "2026-11-12T08:15", 150.0, 150.0, step_min=15),
        # ...16 minutes later does not.
        *series("2026-11-12T08:31", "2026-11-12T10:31", 150.0, 150.0),
    ]
    s = summarize(readings)
    assert s["hours"]["covered"] == pytest.approx(6 + 0.25 + 2 + 2)
    assert s["energy"]["u1"] == pytest.approx(150 * 10.25 / 1000, abs=1e-3)  # rounded to 3 decimals
    assert s["plf"]["u1"] == 71.4  # over the covered hours, not the elapsed 21
    assert s["complete"] is False


def test_the_edges_of_the_day_are_clipped_at_midnight():
    # 23:55 the day before and 00:05: the 5 minutes after midnight belong to the day,
    # along the straight line between the two readings (100 -> 200 MW).
    readings = [reading("2026-11-11T23:55", 100.0, 100.0), reading("2026-11-12T00:05", 200.0, 100.0),
                reading("2026-11-12T23:55", 100.0, 100.0), reading("2026-11-13T00:05", 100.0, 100.0)]
    s = summarize(readings)
    assert s["hours"]["covered"] == pytest.approx(10 / 60, abs=0.005)
    assert s["energy"]["u1"] == pytest.approx((150 + 200) / 2 * (5 / 60) / 1000 + 100 * (5 / 60) / 1000, abs=5e-4)
    assert [p["at"] for p in s["points"]] == ["2026-11-12T00:05", "2026-11-12T23:55"]
    # Readings further away than MAX_GAP do not reach into the day.
    far = [reading("2026-11-11T23:44", 100.0, 100.0), reading("2026-11-12T00:00", 100.0, 100.0)]
    assert summarize(far)["hours"]["covered"] == 0.0


def test_a_missing_unit_value_adds_no_energy_for_that_unit():
    readings = [reading("2026-11-12T10:00", 150.0, 150.0), reading("2026-11-12T10:02", 150.0, None),
                reading("2026-11-12T10:04", 150.0, 150.0)]
    s = summarize(readings)
    assert s["hours"]["covered"] == pytest.approx(4 / 60, abs=0.005)
    assert s["energy"]["u1"] == pytest.approx(0.01) and s["energy"]["u2"] == 0.0


def test_sample_is_keyed_on_the_minute_it_was_taken():
    r = live.sample(live.parse_feed(feed()), datetime(2026, 11, 12, 21, 3, 41, tzinfo=IST))
    assert (r["at"], r["feedAt"], r["u1At"]) == ("2026-11-12T21:03", "2026-11-12T20:55", "2026-11-12T20:55")
    assert r["ts"] == datetime(2026, 11, 12, 15, 33, tzinfo=timezone.utc)


def test_samples_of_a_stuck_portal_are_a_gap():
    # Samples every minute 00:00-24:00 at 150 MW, but from 06:00 to 08:00 the
    # portal kept showing its 05:58 reading.
    samples = []
    t, end = live.key_time("2026-11-12T00:00"), live.key_time("2026-11-13T00:00")
    while t <= end:
        r = reading(live.minute_key(t), 150.0, 150.0)
        stuck = live.key_time("2026-11-12T06:00") <= t < live.key_time("2026-11-12T08:00")
        r["feedAt"] = "2026-11-12T05:58" if stuck else live.minute_key(t - timedelta(minutes=2))
        samples.append(r)
        t += timedelta(minutes=1)
    s = summarize(samples, now=NOW + timedelta(days=2))
    # 06:00-06:13 still counts (the reading is at most 15 minutes old); the rest
    # of the stuck stretch, up to the first fresh sample at 08:00, does not.
    assert s["hours"]["covered"] == pytest.approx(24 - (8 - (6 + 13 / 60)), abs=0.02)
    assert s["energy"]["u1"] == pytest.approx(0.15 * s["hours"]["covered"], abs=0.001)
    assert not s["complete"]
    assert all(live.fresh(r) for r in samples[:360])


def test_no_readings():
    s = summarize([])
    assert s["points"] == [] and s["lastAt"] is None
    assert s["energy"] == {"u1": 0.0, "u2": 0.0, "stn": 0.0}
    assert s["plf"] == {"u1": None, "u2": None, "stn": None}
    assert s["hours"] == {"elapsed": 21.0, "covered": 0.0}
    assert s["projected"] is None and s["events"] == [] and s["offline"] == [] and s["complete"] is False
    assert summarize([reading("2026-11-12T10:00", 150.0, 150.0)])["plf"]["stn"] is None  # one reading spans nothing


def test_complete_from_95_percent_of_the_day():
    full = series("2026-11-11T00:00", "2026-11-12T00:00", 150.0, 150.0)  # 720 two-minute stretches
    on = date(2026, 11, 11)
    assert summarize(full[:685], day=on)["hours"]["covered"] == 22.8
    assert summarize(full[:685], day=on)["complete"] is True
    assert summarize(full[:684], day=on)["complete"] is False  # 22.77 h
    # Wherever the hours are missing.
    assert summarize(full[:300] + full[335:], day=on)["complete"] is True    # 09:58 to 11:10: 72 minutes
    assert summarize(full[:300] + full[336:], day=on)["complete"] is False   # 74 minutes


def test_elapsed_and_projection_for_today():
    readings = series("2026-11-12T00:00", "2026-11-12T12:00", 150.0, 140.0)
    s = summarize(readings, now=datetime(2026, 11, 12, 12, 30, tzinfo=IST))
    assert s["isToday"] is True and s["hours"] == {"elapsed": 12.5, "covered": 12.0}
    assert s["energy"]["stn"] == pytest.approx(3.48)
    # The rest of the day at the latest station load: 290 MW for 11.5 h.
    assert s["projected"] == {"stn": pytest.approx(3.48 + 290 * 11.5 / 1000)}
    # A day still to come has no hours yet; a past day has all 24.
    assert summarize([], day=date(2026, 11, 13))["hours"]["elapsed"] == 0.0
    assert summarize(readings, now=datetime(2026, 11, 13, 1, 0, tzinfo=IST))["projected"] is None


def test_unit_mw_comes_from_the_caller():
    s = summarize(series("2026-11-12T00:00", "2026-11-12T01:00", 150.0, 150.0), unit_mw=200)
    assert s["unitMw"] == 200 and s["plf"]["u1"] == 75.0


# --- trips, stops, back ---------------------------------------------------------------------------

def kinds(s) -> list[tuple]:
    return [(e["unit"], e["kind"], e["at"], e.get("fromMw")) for e in s["events"]]


def test_trip_and_back():
    u2 = {"2026-11-12T10:00": 150.2, "2026-11-12T10:02": 0.4, "2026-11-12T10:04": 1.8, "2026-11-12T10:06": 0.0,
          "2026-11-12T10:08": 22.0, "2026-11-12T10:10": 60.0}
    s = summarize([reading(at, 150.0, mw) for at, mw in u2.items()])
    assert kinds(s) == [(2, "trip", "2026-11-12T10:02", 150.2), (2, "back", "2026-11-12T10:08", None)]
    assert s["offline"] == []


def test_ramp_down_and_slow_drops_are_stops():
    # Ramped down: the last reading before offline was under 50 MW.
    ramp = [reading(f"2026-11-12T10:{m:02d}", mw, 150.0) for m, mw in ((0, 150.0), (2, 90.0), (4, 30.1), (6, 2.0))]
    assert kinds(summarize(ramp)) == [(1, "stop", "2026-11-12T10:06", 30.1)]
    # A sudden fall, but seen across 12 minutes without readings.
    gap = [reading("2026-11-12T10:00", 150.0, 150.0), reading("2026-11-12T10:12", 150.0, 0.5)]
    assert kinds(summarize(gap)) == [(2, "stop", "2026-11-12T10:12", 150.0)]
    # 10 minutes apart is still a trip.
    near = [reading("2026-11-12T10:00", 150.0, 150.0), reading("2026-11-12T10:10", 150.0, 0.5)]
    assert kinds(summarize(near)) == [(2, "trip", "2026-11-12T10:10", 150.0)]
    # Exactly 50 MW counts as load; 5 MW is online.
    edge = [reading("2026-11-12T10:00", 50.0, 5.0), reading("2026-11-12T10:02", 4.99, 5.0)]
    assert kinds(summarize(edge)) == [(1, "trip", "2026-11-12T10:02", 50.0)]


def test_offline_at_the_start_of_the_day_and_the_latest_reading():
    # Offline all night (no event for that), back in the morning, then tripped again.
    u1 = [(f"2026-11-12T0{h}:00", mw) for h, mw in ((0, 0.3), (1, 0.0), (2, 0.2))]
    readings = [reading(at, mw, 150.0) for at, mw in u1]
    readings += [reading("2026-11-12T02:10", 25.0, 150.0), reading("2026-11-12T02:20", 120.0, 150.0),
                 reading("2026-11-12T02:22", 3.0, 150.0)]
    s = summarize(readings)
    assert kinds(s) == [(1, "back", "2026-11-12T02:10", None), (1, "trip", "2026-11-12T02:22", 120.0)]
    assert s["offline"] == [1]


def test_the_reading_before_midnight_sets_the_state():
    readings = [reading("2026-11-11T23:58", 150.0, 0.5), reading("2026-11-12T00:00", 0.2, 0.4),
                reading("2026-11-12T00:02", 0.1, 30.0)]
    assert kinds(summarize(readings)) == [(1, "trip", "2026-11-12T00:00", 150.0),
                                          (2, "back", "2026-11-12T00:02", None)]
    # Events of the day before are not the day's.
    readings = [reading("2026-11-11T23:56", 150.0, 150.0), reading("2026-11-11T23:58", 0.5, 150.0),
                reading("2026-11-12T00:00", 0.5, 150.0)]
    assert summarize(readings)["events"] == []


def test_events_of_both_units_are_in_time_order():
    readings = [reading("2026-11-12T10:00", 150.0, 150.0), reading("2026-11-12T10:02", 150.0, 0.0),
                reading("2026-11-12T10:04", 0.0, 0.0), reading("2026-11-12T10:06", 0.0, 10.0)]
    assert [(e["unit"], e["kind"]) for e in summarize(readings)["events"]] == [(2, "trip"), (1, "trip"), (2, "back")]
    assert summarize(readings)["offline"] == [1]


# --- report cross-check ------------------------------------------------------------------------------

def day_at(u1: float, u2: float, hours: float = 24.0) -> dict:
    """A summary of 3 Nov at constant load over the first `hours`."""
    end = datetime(2026, 11, 3, tzinfo=IST) + timedelta(hours=hours)
    return summarize(series("2026-11-03T00:00", live.minute_key(end), u1, u2), day=date(2026, 11, 3))


def test_generation_checks():
    s = day_at(145.0, 153.0)  # 3.48 and 3.672 MU
    c1, c2 = live.generation_checks(s, {"u1Gen": 3.48, "u2Gen": 3.53})
    assert (c1.id, c1.ok, c1.severity, c1.cells) == ("live_gen_u1", True, "warn", ["r04_gen.unit1"])
    assert c1.label == "Generation Unit 1 matches the live feed"
    assert c1.detail == "Unit 1: page 3.48 MU, live feed 3.48 MU"
    # 0.142 MU apart: more than 3 % of 3.672 (0.110).
    assert (c2.id, c2.ok, c2.cells) == ("live_gen_u2", False, ["r04_gen.unit2"])
    assert c2.detail == "Unit 2: page 3.53 MU, live feed 3.67 MU"


def test_generation_check_tolerance_is_at_least_a_tenth_of_a_mu():
    s = day_at(20.0, 0.0)  # 0.48 MU and nothing
    c1, c2 = live.generation_checks(s, {"u1Gen": 0.57, "u2Gen": 0.1})
    assert c1.ok is True and c2.ok is True
    c1, c2 = live.generation_checks(s, {"u1Gen": 0.59, "u2Gen": 0.11})
    assert c1.ok is False and c2.ok is False


def test_generation_checks_fill_the_uncovered_minutes():
    s = day_at(150.0, 150.0, hours=23.0)  # complete, 23 h covered: 3.45 MU recorded
    assert s["complete"] is True and s["energy"]["u1"] == pytest.approx(3.45)
    [c1, _] = live.generation_checks(s, {"u1Gen": 3.6, "u2Gen": 3.6})
    assert c1.ok and c1.detail == "Unit 1: page 3.60 MU, live feed 3.60 MU"


def test_no_generation_checks_for_an_incomplete_day_or_a_blank_cell():
    assert live.generation_checks(day_at(150.0, 150.0, hours=22.0), {"u1Gen": 3.6, "u2Gen": 3.6}) == []
    assert [c.id for c in live.generation_checks(day_at(150.0, 150.0), {"u1Gen": None, "u2Gen": 3.6})] == \
        ["live_gen_u2"]


# --- the API ---------------------------------------------------------------------------------------

class Portal:
    """Stands in for the plant portal behind main.http_client."""

    def __init__(self):
        self.feed = feed()
        self.down = False
        self.calls = 0

    def answer(self, request: httpx.Request) -> httpx.Response:
        assert str(request.url) == main.LIVE_URL
        self.calls += 1
        if self.down:
            raise httpx.ConnectError("portal down", request=request)
        return httpx.Response(200, json=self.feed, request=request)


@pytest.fixture
def portal(monkeypatch) -> Portal:
    """Replaces conftest's network block for the portal's URL only."""
    fake = Portal()

    async def send(client, request, *args, **kwargs):
        return fake.answer(request)

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    return fake


@pytest.fixture
def api(monkeypatch, portal):
    monkeypatch.setattr(main, "db", AsyncMongoMockClient()["ttps_test"])
    monkeypatch.setattr(main, "_ist_now", lambda: NOW)
    # mongomock applies TTL indexes against the real clock, which would delete
    # these fixed 2026 readings once they are 90 days old. The index itself is
    # checked in test_readings_expire_after_ninety_days.
    monkeypatch.setattr(main, "LIVE_RETENTION_DAYS", 365 * 100)
    # Every request asks the portal; nothing carries over between tests.
    monkeypatch.setattr(main, "LIVE_CACHE_TTL_S", 0)
    monkeypatch.setattr(main, "live_cache", {"data": None, "fetched_at": 0.0})
    monkeypatch.delenv("LIVE_RECORD_KEY", raising=False)
    with TestClient(main.app) as c:
        yield c


def run(coro):
    return asyncio.run(coro)


def stored() -> list[dict]:
    return run(main.db["live_readings"].find({}).sort("ts", 1).to_list(None))


def store(readings: list[dict]) -> None:
    async def insert():
        await main.db["live_readings"].insert_many([live.to_doc(r) for r in readings])
    run(insert())


def test_polling_never_writes(api, portal):
    """Opening the app must not change the history: only the scheduler records."""
    for _ in range(3):
        response = api.get("/api/live-generation")
        assert response.status_code == 200 and response.json() == portal.feed  # passed through unchanged
    assert portal.calls == 3 and stored() == []
    # An unreadable feed is passed through as well.
    portal.feed = {"error": "maintenance"}
    assert api.get("/api/live-generation").json() == {"error": "maintenance"}


def test_portal_down_serves_the_last_reading_marked_stale(api, portal):
    portal.down = True
    response = api.get("/api/live-generation")
    assert response.status_code == 502 and "portal down" in response.json()["detail"]

    store([reading("2026-11-12T20:51", 140.0, 150.0), reading("2026-11-12T20:53", 141.5, 0.4)])
    response = api.get("/api/live-generation")
    assert response.status_code == 200
    items = response.json()
    assert [(i["station"], i["readings"]["power"], i["timestamp"], i["stale"]) for i in items] == [
        ("Power Generation Unit-1", 141.5, "12-Nov-2026 20:53", True),
        ("Power Generation Unit-2", 0.4, "12-Nov-2026 20:53", True),
    ]
    assert all(i["units"] == {"power": "MW"} for i in items)

    portal.down = False
    assert "stale" not in api.get("/api/live-generation").json()[0]


def test_record_endpoint_needs_the_key(api, portal, monkeypatch):
    assert api.get("/api/live/record", params={"key": "anything"}).status_code == 503
    assert portal.calls == 0

    monkeypatch.setenv("LIVE_RECORD_KEY", "s3cret")
    assert api.get("/api/live/record").status_code == 401
    assert api.get("/api/live/record", params={"key": "s3cre"}).status_code == 401
    assert api.post("/api/live/record", headers={"X-Record-Key": "wrong"}).status_code == 401
    assert api.get("/api/live/record", params={"key": "s3crét"}).status_code == 401  # non-ASCII is just wrong
    assert portal.calls == 0 and stored() == []

    response = api.get("/api/live/record", params={"key": "s3cret"})
    assert response.status_code == 200
    assert response.json() == {"recorded": True, "at": "2026-11-12T21:00", "feedAt": "2026-11-12T20:55",
                               "u1": 146.41, "u2": 156.56}
    # A second call in the same minute keeps the first sample.
    again = api.post("/api/live/record", headers={"X-Record-Key": "s3cret"})
    assert again.status_code == 200 and again.json()["recorded"] is False
    assert len(stored()) == 1

    portal.down = True
    assert api.get("/api/live/record", params={"key": "s3cret"}).status_code == 502
    portal.down, portal.feed = False, []
    assert api.get("/api/live/record", params={"key": "s3cret"}).status_code == 502


def test_every_scheduled_minute_is_stored_even_if_the_portal_has_not_moved(api, portal, monkeypatch):
    monkeypatch.setenv("LIVE_RECORD_KEY", "s3cret")
    for minute in range(3):  # 21:00, 21:01, 21:02; the portal still shows its 20:55 reading
        monkeypatch.setattr(main, "_ist_now", lambda m=minute: NOW + timedelta(minutes=m, seconds=40))
        assert api.get("/api/live/record", params={"key": "s3cret"}).json()["recorded"] is True
    portal.feed = feed(u1=150.0, u2=0.4, stamp="12-Nov-2026 21:01")
    monkeypatch.setattr(main, "_ist_now", lambda: NOW + timedelta(minutes=3))
    api.get("/api/live/record", params={"key": "s3cret"})
    assert [(d["_id"], d["feedAt"], d["u1"], d["u2"]) for d in stored()] == [
        ("2026-11-12T21:00", "2026-11-12T20:55", 146.41, 156.56),
        ("2026-11-12T21:01", "2026-11-12T20:55", 146.41, 156.56),
        ("2026-11-12T21:02", "2026-11-12T20:55", 146.41, 156.56),
        ("2026-11-12T21:03", "2026-11-12T21:01", 150.0, 0.4),
    ]
    assert stored()[0]["ts"] == datetime(2026, 11, 12, 15, 30)  # the sample's minute, UTC
    # The stale fallback shows the portal's own stamp, not the sample's minute.
    portal.down = True
    assert [i["timestamp"] for i in api.get("/api/live-generation").json()] == ["12-Nov-2026 21:01"] * 2


def test_day_endpoint(api):
    def u2(t: datetime) -> float:
        # Unit 2 trips at 10:00 and is back at 12:00.
        return 1.0 if live.key_time("2026-11-12T10:00") <= t < live.key_time("2026-11-12T12:00") else 160.0

    store([*series("2026-11-11T23:30", "2026-11-11T23:58", 99.0, 99.0),
           *series("2026-11-12T00:00", "2026-11-12T21:00", 150.0, u2)])
    response = api.get("/api/live/day")
    assert response.status_code == 200, response.text
    day = response.json()
    assert (day["date"], day["isToday"], day["unitMw"], day["lastAt"]) == ("2026-11-12", True, 210, "2026-11-12T21:00")
    assert len(day["points"]) == 631 and day["points"][0] == {"at": "2026-11-12T00:00", "u1": 150.0, "u2": 160.0}
    assert day["hours"] == {"elapsed": 21.0, "covered": 21.0}
    assert day["energy"]["u1"] == 3.15 and day["plf"]["u1"] == 71.4
    assert day["projected"]["stn"] == pytest.approx(day["energy"]["stn"] + 310 * 3 / 1000, abs=1e-3)
    assert day["complete"] is False and day["offline"] == []
    assert day["events"] == [{"unit": 2, "kind": "trip", "at": "2026-11-12T10:00", "fromMw": 160.0},
                             {"unit": 2, "kind": "back", "at": "2026-11-12T12:00"}]

    before = api.get("/api/live/day", params={"date": "2026-11-11"}).json()
    assert before["isToday"] is False and before["projected"] is None and len(before["points"]) == 15
    assert before["hours"] == {"elapsed": 24.0, "covered": 0.5}

    api.put("/api/config/2026", json={"unitMw": 200})
    assert api.get("/api/live/day").json()["plf"]["u1"] == 75.0
    assert api.get("/api/live/day", params={"date": "2026-11-31"}).status_code == 400
    assert api.get("/api/live/day", params={"date": "2026-10-01"}).json()["points"] == []


def test_readings_expire_after_ninety_days(monkeypatch):
    monkeypatch.setattr(main, "db", AsyncMongoMockClient()["ttps_test"])
    run(main._ensure_indexes())
    ttl = run(main.db["live_readings"].index_information())[main.LIVE_TTL_INDEX]
    assert ttl["key"] == [("ts", 1)]
    assert ttl["expireAfterSeconds"] == 90 * 24 * 3600 == main.LIVE_RETENTION_DAYS * 24 * 3600


# --- upload cross-check ------------------------------------------------------------------------------

def upload_page(api, monkeypatch) -> dict:
    """Upload the sample page (data for 3 Nov: Unit 1 3.48 MU, Unit 2 3.68 MU)."""
    async def reader(image, recheck=None):
        return extract.Extraction(report=load_report(PAGE_1), model="fake-reader", usage={})

    monkeypatch.setattr(main.extract, "extract_report", reader)
    buf = io.BytesIO()
    Image.new("RGB", (1119, 1599), "white").save(buf, format="JPEG")
    response = api.post("/api/reports", files={"file": ("page.jpg", buf.getvalue(), "image/jpeg")})
    assert response.status_code == 200, response.text
    return response.json()


def live_checks(body: dict) -> dict[str, dict]:
    return {c["id"]: c for c in body["checks"] if c["id"].startswith("live_gen")}


def test_upload_is_checked_against_a_complete_feed_day(api, monkeypatch):
    # 145 MW and 153.33 MW all day: 3.48 and 3.68 MU, as printed.
    store(series("2026-11-02T23:58", "2026-11-04T00:00", 145.0, 153.33))
    body = upload_page(api, monkeypatch)
    checks = live_checks(body)
    assert checks == {
        "live_gen_u1": {"id": "live_gen_u1", "label": "Generation Unit 1 matches the live feed", "ok": True,
                        "severity": "warn", "detail": "Unit 1: page 3.48 MU, live feed 3.48 MU",
                        "cells": ["r04_gen.unit1"]},
        "live_gen_u2": {"id": "live_gen_u2", "label": "Generation Unit 2 matches the live feed", "ok": True,
                        "severity": "warn", "detail": "Unit 2: page 3.68 MU, live feed 3.68 MU",
                        "cells": ["r04_gen.unit2"]},
    }
    # Stored with the report, like the other checks.
    assert live_checks(api.get(f"/api/reports/{body['id']}").json()) == checks


def test_a_feed_mismatch_warns_but_does_not_block_saving(api, monkeypatch):
    store(series("2026-11-02T23:58", "2026-11-04T00:00", 145.0, 140.0))  # Unit 2: 3.36 MU
    body = upload_page(api, monkeypatch)
    checks = live_checks(body)
    assert checks["live_gen_u1"]["ok"] is True
    assert checks["live_gen_u2"]["ok"] is False and checks["live_gen_u2"]["severity"] == "warn"
    assert checks["live_gen_u2"]["detail"] == "Unit 2: page 3.68 MU, live feed 3.36 MU"
    assert body["status"] == "saved"
    assert api.get("/api/entries", params={"month": "2026-11"}).json()[0]["u2Gen"] == 3.68


def test_no_feed_check_when_the_feed_day_is_incomplete(api, monkeypatch):
    store(series("2026-11-03T00:00", "2026-11-03T12:00", 145.0, 140.0))
    body = upload_page(api, monkeypatch)
    assert body["status"] == "saved" and live_checks(body) == {}
