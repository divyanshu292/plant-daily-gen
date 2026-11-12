"""analytics.py: per-day figures, trends, progress and the watch list.

Synthetic entries pin down each rule and edge case. One test runs the real
workbook and checks the per-day figures against calc.performance_report, and
the API tests go through FastAPI with an in-memory database.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

import analytics
import calc
import main
from helpers import requires_workbook

ON = date(2026, 11, 10)
TOMORROW = ON + timedelta(days=1)  # the normal "today": D's report is printed on D+1

# 7 MU a day; sp. coal 0.714 kg/kWh, sp. oil 0.2 ml/kWh, APC 10 %, make-up 1 %.
BASE = {
    "u1Gen": 3.5, "u2Gen": 3.5, "u1Coal": 2500.0, "u2Coal": 2500.0, "u1Oil": 0.7, "u2Oil": 0.7,
    "apc": 0.7, "gcv": 3500.0, "u1Dm": 100.0, "u2Dm": 117.0, "coalReceipt": 5000.0,
    "u1Fo": 0.0, "u2Fo": 0.0, "u1Po": 0.0, "u2Po": 0.0, "u1Bd": 0.0, "u2Bd": 0.0,
    "u1Trip": 0.0, "u2Trip": 0.0, "u1Btl": 0.0, "u2Btl": 0.0,
}


def series(first: date, last: date = ON, skip: tuple[str, ...] = (), **fields) -> list[dict]:
    """One BASE entry per day from first to last, with `fields` on top."""
    out = []
    d = first
    while d <= last:
        if d.isoformat() not in skip:
            out.append({"date": d.isoformat(), **BASE, **fields})
        d += timedelta(days=1)
    return out


def with_recent(entries: list[dict], days: int = 7, **fields) -> list[dict]:
    """The last `days` entries changed by `fields` (the trends' recent window)."""
    for e in entries[-days:]:
        e.update(fields)
    return entries


def config(targets: dict | None = None, anchors: list | None = None) -> dict:
    return {"fy": 2026, "unitMw": 210, "monthlyTargets": targets or {},
            "coalStockAnchors": anchors or [], "oilStockAnchors": []}


def run(entries: list[dict], cfg: dict | None = None, on: date = ON, today: date | None = None) -> dict:
    return analytics.analytics(entries, cfg or config(), on, today or on + timedelta(days=1))


def watch(out: dict, key: str) -> dict | None:
    return next((w for w in out["watch"] if w["key"] == key), None)


def trend(out: dict, key: str) -> dict:
    return next(t for t in out["trends"] if t["key"] == key)


def day(out: dict, iso: str) -> dict:
    return next(d for d in out["days"] if d["date"] == iso)


# --- shape and per-day figures ------------------------------------------------------------------

def test_empty():
    assert analytics.empty(date(2027, 2, 3)) == {
        "date": None, "today": "2027-02-03", "fy": 2026, "unitMw": 210,
        "days": [], "progress": None, "trends": [], "watch": [],
    }


def test_shape():
    out = run(series(date(2026, 7, 1)))
    assert (out["date"], out["today"], out["fy"]) == ("2026-11-10", "2026-11-11", 2026)
    assert len(out["days"]) == analytics.DAYS_SHOWN
    assert (out["days"][0]["date"], out["days"][-1]["date"]) == ("2026-08-13", "2026-11-10")
    assert set(out["days"][0]) == {"date", "hasData", *analytics.DAY_METRICS, "coalStock"}
    assert [t["key"] for t in out["trends"]] == ["plf", "availability", "spCoal", "heatRate", "apcPct", "spOil", "dmPct"]
    assert [t["better"] for t in out["trends"]] == ["up", "up", "down", "down", "down", "down", "down"]
    assert set(out["progress"]) == {"month", "year"}
    assert set(out["progress"]["month"]) == {"label", "gen", "target", "expected", "askingRate", "recentRate",
                                             "plf", "targetPlf", "daysElapsed", "daysTotal", "daysMissing"}
    assert all(set(w) == {"key", "level", "title", "detail"} for w in out["watch"])


def test_day_figures():
    entries = series(date(2026, 11, 1))
    entries[-1].update(u1Gen=3.0, u2Gen=4.0, u1Coal=2000.0, u2Coal=3000.0, u1Oil=1.0, u2Oil=0.4, apc=0.77,
                       u1Dm=150.0, u2Dm=67.0, u1Fo=2.0, u2Po=4.0, u1Bd=0.1, u2Bd=0.2, u1Trip=1.0, u2Btl=1.0,
                       gcv=9999.0)  # the day's own GCV is not used for its heat rate
    d = day(run(entries), "2026-11-10")
    assert d["hasData"] is True
    assert (d["gen"], d["u1Gen"], d["u2Gen"]) == (7.0, 3.0, 4.0)
    assert d["plf"] == pytest.approx(7.0 / 10.08 * 100)
    assert d["u1Plf"] == pytest.approx(3.0 / 5.04 * 100) and d["u2Plf"] == pytest.approx(4.0 / 5.04 * 100)
    assert d["availability"] == pytest.approx(100 - 6.0 / 48 * 100)
    assert d["forcedOutage"] == 2.0
    assert d["spCoal"] == pytest.approx(5000 / 7000)
    assert d["spOil"] == pytest.approx(1.4 / 7)
    assert d["apcPct"] == pytest.approx(11.0)
    assert d["dmPct"] == pytest.approx(217 * 100 / (7000 * 3.1))
    assert d["heatRate"] == pytest.approx(calc.heat_rate(5000.0, 1.4, 7.0, 3500.0))
    assert d["backingDown"] == pytest.approx(0.3)
    assert (d["trips"], d["btl"]) == (1.0, 1.0)


def test_heat_rate_uses_the_latest_earlier_gcv():
    entries = series(date(2026, 11, 1), gcv=None)
    entries[1]["gcv"] = 3000.0  # 2 Nov
    entries[5]["gcv"] = 3600.0  # 6 Nov
    out = run(entries)
    assert day(out, "2026-11-01")["heatRate"] is None and day(out, "2026-11-02")["heatRate"] is None
    for iso in ("2026-11-03", "2026-11-06"):
        assert day(out, iso)["heatRate"] == pytest.approx(calc.heat_rate(5000.0, 1.4, 7.0, 3000.0))
    assert day(out, "2026-11-07")["heatRate"] == pytest.approx(calc.heat_rate(5000.0, 1.4, 7.0, 3600.0))


def test_no_gcv_at_all():
    out = run(series(date(2026, 9, 1), gcv=None))
    assert all(d["heatRate"] is None for d in out["days"])
    hr = trend(out, "heatRate")
    assert (hr["recent"], hr["baseline"], hr["change"], hr["changePct"], hr["status"]) == (None, None, None, None, "steady")
    assert trend(out, "spCoal")["recent"] == pytest.approx(5000 / 7000)


def test_zero_generation_day():
    entries = series(date(2026, 11, 1))
    entries[-1].update(u1Gen=0.0, u2Gen=0.0, u1Coal=0.0, u2Coal=0.0, u1Oil=3.0, u2Oil=0.0, u1Fo=24.0, u2Fo=24.0)
    d = day(run(entries), "2026-11-10")
    assert d["hasData"] is True and d["gen"] == 0.0 and d["plf"] == 0.0 and d["availability"] == 0.0
    assert all(d[k] is None for k in ("spCoal", "spOil", "apcPct", "heatRate", "dmPct"))


def test_blank_apc_is_left_out():
    entries = series(date(2026, 9, 1))
    entries[-1]["apc"] = None
    out = run(entries)
    assert day(out, "2026-11-10")["apcPct"] is None
    assert trend(out, "apcPct")["recent"] == pytest.approx(10.0)  # the other six days only


def test_days_without_data():
    entries = series(date(2026, 9, 1), skip=("2026-11-08", "2026-11-09"),
                     coalReceipt=0.0, u1Coal=1000.0, u2Coal=1000.0)
    entries.append({"date": "2026-11-09", "u1Remark": "no generation figures"})  # not a data day
    out = run(entries, config(anchors=[{"date": "2026-11-01", "stock": 50000.0}]))
    for iso in ("2026-11-08", "2026-11-09"):
        d = day(out, iso)
        assert d["hasData"] is False
        assert all(d[k] is None for k in analytics.DAY_METRICS)
    # Stock is still known on those days: nothing was burnt on them.
    assert [day(out, f"2026-11-{n:02d}")["coalStock"] for n in (7, 8, 9, 10)] == [38000.0, 38000.0, 38000.0, 36000.0]
    assert day(out, "2026-10-31")["coalStock"] is None  # before the opening balance
    # The recent window skips the gap: 7 days with data back from 10 Nov is 2..7 Nov and 10 Nov.
    assert trend(out, "plf")["recentDays"] == 7 and trend(out, "plf")["baselineDays"] == 30
    assert out["progress"]["month"]["recentRate"] == pytest.approx(7.0)


def test_sparse_history_gives_short_windows():
    entries = series(date(2026, 11, 6))  # five days
    out = run(entries)
    plf = trend(out, "plf")
    assert (plf["recentDays"], plf["baselineDays"]) == (5, 0)
    assert plf["recent"] == pytest.approx(7 / 10.08 * 100)
    assert (plf["baseline"], plf["change"], plf["changePct"], plf["status"]) == (None, None, None, "steady")


def test_no_data_in_range():
    out = run([], on=ON)
    assert all(d["hasData"] is False for d in out["days"])
    assert all(t["recent"] is None and t["status"] == "steady" for t in out["trends"])
    assert out["progress"]["month"]["gen"] == 0.0 and out["progress"]["month"]["recentRate"] is None
    assert watch(out, "coalStock") is None and watch(out, "staleData") is None


def test_coal_stock_series_matches_calc():
    entries = series(date(2026, 6, 1))
    for i, e in enumerate(entries):
        e["coalReceipt"] = 3000.0 + 500 * (i % 5)
    entries[100]["coalStock"] = 123456.0  # a printed figure re-bases the roll-forward
    anchors = [{"date": "2026-04-01", "stock": 500000.0}, {"date": "2026-07-20", "stock": 250000.0}]
    out = run(entries, config(anchors=anchors))
    by_date = {e["date"]: e for e in entries}
    for d in out["days"]:
        expected = calc._stock(by_date, anchors, date.fromisoformat(d["date"]),
                               "coalStock", "coalReceipt", ("u1Coal", "u2Coal"))
        assert d["coalStock"] == expected["value"]


# --- trends -------------------------------------------------------------------------------------------

def test_trend_is_ratio_of_sums():
    entries = series(date(2026, 9, 1))
    # Recent week: one big day and six small ones, at different sp. coal.
    for e in entries[-7:-1]:
        e.update(u1Gen=1.0, u2Gen=1.0, u1Coal=800.0, u2Coal=800.0)
    entries[-1].update(u1Gen=4.0, u2Gen=4.0, u1Coal=2800.0, u2Coal=2800.0)
    sp = trend(run(entries), "spCoal")
    assert sp["recent"] == pytest.approx((6 * 1600 + 5600) / (1000 * (6 * 2 + 8)))
    assert sp["baseline"] == pytest.approx(5000 / 7000)
    assert sp["change"] == pytest.approx(sp["recent"] - sp["baseline"])
    assert sp["changePct"] == pytest.approx(sp["change"] / sp["baseline"] * 100)


@pytest.mark.parametrize("coal, status", [(2540.0, "steady"), (2560.0, "worse"), (2440.0, "better")])
def test_trend_status_relative_threshold(coal, status):
    # sp. coal: steady within 2 %. 2540 is +1.6 %, 2560 is +2.4 %.
    out = run(with_recent(series(date(2026, 9, 1)), u1Coal=coal, u2Coal=coal))
    assert trend(out, "spCoal")["status"] == status


@pytest.mark.parametrize("gen, status", [(3.46, "steady"), (3.4, "worse"), (3.6, "better")])
def test_trend_status_points_threshold(gen, status):
    # PLF: steady within 1 point. 3.46 MU a unit is -0.8 pt, 3.4 is -2 pt.
    out = run(with_recent(series(date(2026, 9, 1)), u1Gen=gen, u2Gen=gen))
    assert trend(out, "plf")["status"] == status


def test_trend_from_a_zero_baseline():
    entries = with_recent(series(date(2026, 9, 1), u1Oil=0.0, u2Oil=0.0), days=1, u1Oil=2.0)
    oil = trend(run(entries), "spOil")
    assert oil["baseline"] == 0.0 and oil["changePct"] is None
    assert oil["status"] == "worse"


# --- progress -----------------------------------------------------------------------------------------

NOV_TARGET = {"2026-11": {"u1": 108.0, "u2": 115.2}}  # 223.2 MU
FULL_YEAR = {f"{2026 + (m < 4)}-{m:02d}": {"u1": 100.0, "u2": 100.0} for m in range(1, 13)}


def test_progress_matches_calc():
    entries = series(date(2026, 4, 1))
    cfg = config(targets=FULL_YEAR)
    out = run(entries, cfg)
    rows = {r["key"]: r for r in calc.performance_report(entries, cfg, ON)["rows"]}
    for scope, elapsed, total, label in (("month", 10, 30, "November 2026"), ("year", 224, 365, "FY 2026-27")):
        p = out["progress"][scope]
        assert (p["label"], p["daysElapsed"], p["daysTotal"]) == (label, elapsed, total)
        for key in ("gen", "target", "askingRate", "plf", "targetPlf"):
            assert p[key] == rows[key]["stn"][scope], key
        assert p["expected"] == pytest.approx(p["target"] * elapsed / total)
        assert p["recentRate"] == pytest.approx(7.0)


def test_progress_without_targets():
    out = run(series(date(2026, 11, 1)))
    for scope in ("month", "year"):
        p = out["progress"][scope]
        assert p["target"] is None and p["expected"] is None and p["askingRate"] is None and p["targetPlf"] is None
    assert watch(out, "monthTarget") is None and watch(out, "yearTarget") is None


# --- watch list ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("today, level, title", [
    (date(2026, 11, 11), None, None),
    (date(2026, 11, 12), "info", "Yesterday's report not uploaded yet"),
    (date(2026, 11, 14), "warn", "Latest data is 4 days old"),
])
def test_stale_data(today, level, title):
    item = watch(run(series(date(2026, 11, 1)), today=today), "staleData")
    if level is None:
        assert item is None
    else:
        assert (item["level"], item["title"]) == (level, title)
        assert "Latest data is for 10 Nov." in item["detail"]


def test_stale_data_uses_the_latest_day_in_the_database():
    out = analytics.analytics(series(date(2026, 11, 1), date(2026, 11, 5)), config(), date(2026, 11, 5),
                              TOMORROW, latest=ON)
    assert watch(out, "staleData") is None


@pytest.mark.parametrize("skip, listed", [
    (("2026-11-05", "2026-11-06"), "5, 6 Nov"),
    (("2026-11-02", "2026-11-03", "2026-11-04", "2026-11-06"), "2-4, 6 Nov"),
])
def test_missing_days(skip, listed):
    item = watch(run(series(date(2026, 10, 1), skip=skip)), "missingDays")
    assert item["level"] == "info"
    assert item["title"] == f"{len(skip)} days missing in November"
    assert item["detail"] == f"No data for {listed}. Month totals count them as zero."


def test_no_missing_days():
    assert watch(run(series(date(2026, 10, 1), skip=("2026-10-30",))), "missingDays") is None


@pytest.fixture
def all_targets(monkeypatch):
    """Keep every target item in the watch list (normally only an unreachable
    one is), so its wording can be checked."""
    monkeypatch.setattr(analytics, "TARGET_KEYS", set())


@pytest.mark.parametrize("u1, u2, level, title", [
    (108.0, 115.2, "warn", "November: 4.40 MU behind target pace"),  # 223.2: 74.4 due, 70 made
    (100.0, 100.0, "good", "November: 3.33 MU ahead of target pace"),  # 200: 66.67 due
    (200.0, 200.0, "alert", "November target out of reach"),  # needs 16.5 MU/day
    (30.0, 30.0, "good", "November target met"),
])
def test_month_target(u1, u2, level, title, all_targets):
    out = run(series(date(2026, 11, 1)), config(targets={"2026-11": {"u1": u1, "u2": u2}}))
    item = watch(out, "monthTarget")
    assert (item["level"], item["title"]) == (level, title)
    assert watch(out, "yearTarget") is None  # only one month has a target


def test_month_target_detail(all_targets):
    item = watch(run(series(date(2026, 11, 1)), config(targets=NOV_TARGET)), "monthTarget")
    assert item["detail"] == ("70.0 of 223.2 MU so far, 74.4 due by now. "
                              "Needs 7.66 MU/day from here; the last 7 days averaged 7.00.")


def test_target_detail_says_when_days_are_missing(all_targets):
    out = run(series(date(2026, 4, 1), skip=("2026-11-05", "2026-11-06")), config(targets=NOV_TARGET))
    assert (out["progress"]["month"]["daysMissing"], out["progress"]["year"]["daysMissing"]) == (2, 2)
    item = watch(out, "monthTarget")
    assert item["detail"].startswith("56.0 of 223.2 MU so far (2 days with no data), 74.4 due by now.")


def test_month_target_out_of_reach_detail():
    item = watch(run(series(date(2026, 11, 1)), config(targets={"2026-11": {"u1": 200.0, "u2": 200.0}})),
                 "monthTarget")
    assert item["detail"] == ("It needs 16.50 MU/day from here, above the station's full load of "
                              "10.08 MU/day. 70.0 of 400.0 MU so far.")


def test_month_target_missed_on_the_last_day(all_targets):
    on = date(2026, 11, 30)
    item = watch(run(series(date(2026, 11, 1), on), config(targets=NOV_TARGET), on=on), "monthTarget")
    assert (item["level"], item["title"]) == ("warn", "November target missed by 13.2 MU")
    assert item["detail"] == "210.0 MU against a target of 223.2 MU."


def test_zero_target_is_skipped():
    out = run(series(date(2026, 11, 1)), config(targets={"2026-11": {"u1": 0.0, "u2": 0.0}}))
    assert watch(out, "monthTarget") is None


def test_year_target(all_targets):
    out = run(series(date(2026, 4, 1)), config(targets=FULL_YEAR))
    item = watch(out, "yearTarget")
    # 2400 MU a year; 224 days at 7 MU is 1568, against 1472.9 due by now.
    assert (item["level"], item["title"]) == ("good", "FY 2026-27: 95.1 MU ahead of target pace")
    assert item["detail"].startswith("1,568.0 of 2,400.0 MU so far, 1,472.9 due by now. Needs ")


@pytest.mark.parametrize("stock, level, title", [
    (3000.0, "alert", "Coal stock covers under a day"),
    (29850.0, "alert", "Coal stock covers 5 days"),
    (60000.0, "warn", "Coal stock covers 12 days"),
    (100000.0, "info", "Coal stock covers 20 days"),
])
def test_coal_stock(stock, level, title):
    entries = series(date(2026, 10, 1))
    entries[-1]["coalStock"] = stock  # printed on the 10 Nov report
    out = run(entries, config(anchors=[{"date": "2026-10-01", "stock": 100000.0}]))
    item = watch(out, "coalStock")
    assert (item["level"], item["title"]) == (level, title)
    assert item["detail"].startswith(f"{stock:,.0f} MT left at 5,000 MT/day (7-day average).")


def test_coal_stock_weekly_change():
    entries = series(date(2026, 10, 1))
    entries[-1]["coalStock"] = 29850.0
    item = watch(run(entries, config(anchors=[{"date": "2026-10-01", "stock": 100000.0}])), "coalStock")
    assert item["detail"] == "29,850 MT left at 5,000 MT/day (7-day average). Down 70% in a week."
    steady = watch(run(series(date(2026, 10, 1)), config(anchors=[{"date": "2026-10-01", "stock": 100000.0}])),
                   "coalStock")
    assert steady["detail"].endswith("About the same as a week ago.")


def test_coal_stock_unknown_or_not_burnt():
    assert watch(run(series(date(2026, 10, 1))), "coalStock") is None
    idle = series(date(2026, 10, 1), u1Coal=0.0, u2Coal=0.0, coalReceipt=0.0)
    item = watch(run(idle, config(anchors=[{"date": "2026-10-01", "stock": 80000.0}])), "coalStock")
    assert (item["level"], item["title"]) == ("info", "Coal stock 80,000 MT")


def test_trips():
    entries = series(date(2026, 10, 1))
    by = {e["date"]: e for e in entries}
    by["2026-10-30"].update(u1Trip=1.0, u1TripReason="Last month's trip")
    by["2026-11-03"].update(u1Trip=1.0, u1TripReason="Drum level low")
    long_reason = "Boiler tube leakage in the economiser zone, unit hand-tripped and boxed up for repair work"
    by["2026-11-07"].update(u2Btl=1.0, u2TripReason=long_reason)
    item = watch(run(entries), "trips")
    assert (item["level"], item["title"]) == ("warn", "1 trip and 1 tube leak this month")
    reason = long_reason[:79].rstrip() + "…"
    assert item["detail"] == f"Unit 1: 1 trip. Unit 2: 1 boiler tube leak. Latest reason (Unit 2, 7 Nov): {reason}"
    assert len(reason) <= analytics.TRIP_REASON_CHARS


def test_no_trips_this_month():
    entries = series(date(2026, 10, 1))
    entries[-11].update(u1Trip=2.0)  # 31 Oct
    assert watch(run(entries), "trips") is None


def test_efficiency():
    out = run(with_recent(series(date(2026, 9, 1)), u1Coal=2600.0, u2Coal=2600.0))
    item = watch(out, "efficiency")
    assert (item["level"], item["title"]) == ("warn", "Sp. coal up 4% this week")
    assert item["detail"].startswith("Sp. coal 0.743 kg/kWh in the last 7 days with data, against 0.714 in the 30 before.")
    assert " Heat rate " in item["detail"]  # up too, by a little less (oil is unchanged)


def test_efficiency_small_rise_is_not_listed():
    out = run(with_recent(series(date(2026, 9, 1)), u1Coal=2560.0, u2Coal=2560.0))  # +2.4 %
    assert trend(out, "spCoal")["status"] == "worse"
    assert watch(out, "efficiency") is None


@pytest.mark.parametrize("apc, listed", [(0.75, True), (0.73, False)])
def test_apc(apc, listed):
    item = watch(run(with_recent(series(date(2026, 9, 1)), apc=apc)), "apc")
    if not listed:  # +0.43 pt: worse, but under the watch threshold
        assert item is None
        return
    assert (item["level"], item["title"]) == ("warn", "Aux. power up 0.7 pt this week")
    assert item["detail"] == "10.71% of generation in the last 7 days with data, against 10.00% in the 30 before."


@pytest.mark.parametrize("dm, listed", [(200.0, True), (160.0, False)])  # +38 % and +20 %
def test_dm(dm, listed):
    item = watch(run(with_recent(series(date(2026, 9, 1)), u2Dm=dm)), "dm")
    if not listed:
        assert item is None
        return
    assert (item["level"], item["title"]) == ("warn", "DM make-up up 38% this week")
    assert "steam or water leaks" in item["detail"]


@pytest.mark.parametrize("base_oil, recent_oil, listed", [
    (0.7, 3.5, True),    # 0.2 -> 1.0 ml/kWh
    (0.1, 0.7, False),   # 0.03 -> 0.2: seven times, but too small to matter
    (2.8, 3.5, False),   # 0.8 -> 1.0: up a quarter only
])
def test_oil(base_oil, recent_oil, listed):
    entries = with_recent(series(date(2026, 9, 1), u1Oil=base_oil, u2Oil=base_oil), u1Oil=recent_oil, u2Oil=recent_oil)
    item = watch(run(entries), "oil")
    if not listed:
        assert item is None
        return
    assert (item["level"], item["title"]) == ("warn", "Oil support up: 1.00 ml/kWh this week")
    assert item["detail"].startswith("Against 0.20 ml/kWh in the 30 days with data before.")


def test_backing_down():
    out = run(series(date(2026, 10, 1), u1Bd=0.1))
    item = watch(out, "backingDown")
    assert (item["level"], item["title"]) == ("info", "Grid backing down: 1.00 MU this month")
    assert item["detail"] == ("1.00 MU so far in November, 1.4% of generation. "
                              "It is instructed by the grid, not a plant problem.")
    assert watch(run(series(date(2026, 10, 1))), "backingDown") is None


def test_unit_gap():
    entries = with_recent(series(date(2026, 9, 1)), u1Coal=2400.0, u2Coal=2600.0)
    item = watch(run(entries), "unitGap")
    assert (item["level"], item["title"]) == ("info", "Unit 2 sp. coal 8% above Unit 1")
    assert item["detail"].startswith("0.743 against 0.686 kg/kWh over the last 7 days")
    # Not when a unit was off on one of those days.
    entries[-3].update(u1Gen=0.0, u1Coal=0.0)
    assert watch(run(entries), "unitGap") is None
    # Nor for a small gap.
    assert watch(run(with_recent(series(date(2026, 9, 1)), u1Coal=2450.0, u2Coal=2550.0)), "unitGap") is None


def test_watch_is_sorted_and_capped():
    entries = series(date(2026, 9, 1), u1Bd=0.1, skip=("2026-11-02",))
    with_recent(entries, u1Coal=2700.0, u2Coal=2400.0, apc=0.8, u2Dm=300.0, u1Oil=3.5, u2Oil=3.5, u1Trip=1.0)
    out = run(entries, config(targets={"2026-11": {"u1": 200.0, "u2": 200.0}},
                              anchors=[{"date": "2026-09-01", "stock": 20000.0}]), today=date(2026, 11, 15))
    levels = [analytics.LEVELS.index(w["level"]) for w in out["watch"]]
    keys = [w["key"] for w in out["watch"]]
    # Late and missing reports are always listed, on top of the MAX_WATCH others.
    assert {"staleData", "missingDays"} <= set(keys)
    assert len([k for k in keys if k not in analytics.ALWAYS_LISTED]) == analytics.MAX_WATCH
    assert levels == sorted(levels)
    assert [w["key"] for w in out["watch"][:2]] == ["coalStock", "monthTarget"]  # the two alerts
    assert all(len(w["title"]) <= 45 for w in out["watch"])


def test_targets_are_listed_only_when_out_of_reach():
    behind = run(series(date(2026, 11, 1)), config(targets=NOV_TARGET))
    assert behind["progress"]["month"]["gen"] < behind["progress"]["month"]["expected"]
    assert watch(behind, "monthTarget") is None  # the Targets section already shows it
    unreachable = run(series(date(2026, 11, 1)), config(targets={"2026-11": {"u1": 200.0, "u2": 200.0}}))
    assert watch(unreachable, "monthTarget")["level"] == "alert"


# --- the real workbook --------------------------------------------------------------------------------

@requires_workbook
def test_real_workbook_matches_calc(book):
    cfg = calc.merge_config(calc.default_config(book["fy"]), book["config"])
    on = date(2026, 11, 4)
    out = analytics.analytics(book["entries"], cfg, on, date(2026, 11, 5))
    assert out["date"] == "2026-11-04" and len(out["days"]) == 90
    assert all(d["hasData"] for d in out["days"])

    # Every day's figures are calc's figures for that day.
    for d in out["days"]:
        report = calc.performance_report(book["entries"], cfg, date.fromisoformat(d["date"]))
        rows = {r["key"]: r for r in report["rows"]}
        for key in ("gen", "plf", "spCoal", "spOil", "apcPct", "dmPct", "heatRate", "backingDown",
                    "forcedOutage", "trips", "btl", "availability"):
            expected = rows[key]["stn"]["day"]
            assert d[key] == (None if expected is None else pytest.approx(expected)), (d["date"], key)
        assert d["u1Plf"] == pytest.approx(rows["plf"]["u1"]["day"])
        assert d["u2Plf"] == pytest.approx(rows["plf"]["u2"]["day"])
        assert d["coalStock"] == report["stocks"]["coal"]["value"]

    month = out["progress"]["month"]
    assert month["gen"] == pytest.approx(6.93 + 7.28 + 7.16 + 7.50)  # 1-4 Nov
    assert month["target"] == pytest.approx(223.2)
    assert (month["daysElapsed"], month["daysTotal"]) == (4, 30)
    assert out["progress"]["year"]["label"] == "FY 2026-27"

    # Recent sp. coal by hand: the last 7 days are 29 Oct - 4 Nov.
    week = [e for e in book["entries"] if "2026-10-29" <= e["date"] <= "2026-11-04"]
    coal = sum(e["u1Coal"] + e["u2Coal"] for e in week)
    gen = sum(e["u1Gen"] + e["u2Gen"] for e in week)
    assert trend(out, "spCoal")["recent"] == pytest.approx(coal / (1000 * gen))
    assert all(t["recent"] is not None and t["baseline"] is not None for t in out["trends"])
    assert 1 <= len(out["watch"]) <= analytics.MAX_WATCH


# --- API ----------------------------------------------------------------------------------------------

TODAY = date(2026, 11, 12)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "db", AsyncMongoMockClient()["ttps_test"])
    monkeypatch.setattr(main, "_today", lambda: TODAY)
    with TestClient(main.app) as c:
        yield c


def put_days(client, entries: list[dict]) -> None:
    for e in entries:
        fields = {k: v for k, v in e.items() if k != "date"}
        assert client.put(f"/api/entries/{e['date']}", json=fields).status_code == 200


def test_api_empty_database(client):
    expected = analytics.empty(TODAY)
    assert client.get("/api/analytics").json() == expected
    assert client.get("/api/analytics", params={"on": "2026-11-01"}).json() == expected
    assert client.get("/api/analytics", params={"on": "2026-11-31"}).status_code == 400


def test_api_default_and_explicit_day(client):
    put_days(client, [{"date": "2026-04-02", **BASE}])  # more than LOOKBACK_DAYS back, still in the year
    put_days(client, series(date(2026, 10, 25)))
    client.put("/api/entries/2026-11-11", json={"u1Remark": "figures still to come"})  # not a data day

    body = client.get("/api/analytics").json()
    assert (body["date"], body["today"], body["fy"]) == ("2026-11-10", "2026-11-12", 2026)
    assert body["days"][-1]["date"] == "2026-11-10" and len(body["days"]) == 90
    assert body["progress"]["year"]["gen"] == pytest.approx(7.0 * 18)  # 2 Apr counts toward the year
    assert body["progress"]["month"]["target"] == pytest.approx(223.2)  # the FY 2026 default targets
    assert watch(body, "staleData")["level"] == "info"

    earlier = client.get("/api/analytics", params={"on": "2026-11-05"}).json()
    assert earlier["date"] == "2026-11-05" and earlier["days"][-1]["date"] == "2026-11-05"
    assert earlier["progress"]["month"]["gen"] == pytest.approx(35.0)
    # Staleness is about the database, not the day being looked at.
    assert watch(earlier, "staleData")["level"] == "info"


@pytest.mark.parametrize("bad", ["2026-11-31", "20261105", "5-11-2026", "yesterday"])
def test_api_bad_date(client, bad):
    put_days(client, series(date(2026, 11, 1)))
    response = client.get("/api/analytics", params={"on": bad})
    assert response.status_code == 400
