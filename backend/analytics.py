"""Trends and "things to look at" for the Home screen.

Built from the daily entries alone, with no database access:

- per-day figures for the 90 days ending at the analysed day,
- month and year progress against target (one calc.performance_report call),
- the last 7 days with data against the 30 days with data before them,
- a short, sorted list of findings in plain words.

Everything is compared with the plant's own history, never with outside norms.
The response shape is a contract with the frontend (GET /api/analytics).
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import calc
from calc import HOURS_PER_DAY, STEAM_T_PER_MWH, _has_data, _stock, _val

DAYS_SHOWN = 90      # days[] covers this many calendar days, ending at the analysed day
RECENT_DAYS = 7      # "recent": the last 7 days that have data
BASELINE_DAYS = 30   # "baseline": the 30 days with data before those
# How far back the trend windows may reach. The API loads at least this much
# history, so a few weeks without data still leave a baseline.
LOOKBACK_DAYS = 130

# A trend is "steady" while its change is under its threshold: points (pt)
# for percentages, relative % for the specific figures.
STEADY_PLF_PT = 1.0
STEADY_AVAILABILITY_PT = 1.0
STEADY_SP_COAL_PCT = 2.0
STEADY_HEAT_RATE_PCT = 1.5
STEADY_APC_PT = 0.3
STEADY_SP_OIL_PCT = 20.0  # oil use is small and lumpy (start-ups), so only big swings count
STEADY_DM_PCT = 15.0

# Watch-list thresholds.
MAX_WATCH = 6
STALE_INFO_DAYS = 2   # today - latest data date. 1 is normal: day D is printed on D+1's report.
STALE_WARN_DAYS = 3
COAL_ALERT_DAYS = 7   # days of coal cover
COAL_WARN_DAYS = 15
EFFICIENCY_WARN_PCT = 3.0  # sp. coal or heat rate up by this much
APC_WARN_PT = 0.5
DM_WARN_PCT = 25.0
OIL_WARN_RATIO = 1.5  # recent sp. oil against the baseline
OIL_WARN_MIN = 0.5    # ml/kWh; below this, oil use is too small to matter
UNIT_GAP_PCT = 5.0    # one unit's sp. coal above the other's
TRIP_REASON_CHARS = 80

LEVELS = ("alert", "warn", "info", "good")  # most urgent first
TARGET_KEYS = {"monthTarget", "yearTarget"}
ALWAYS_LISTED = {"staleData", "missingDays"}

# key, label, unit, decimals, better, steady threshold, threshold kind ("pt" or "pct")
TRENDS = (
    ("plf", "PLF", "%", 1, "up", STEADY_PLF_PT, "pt"),
    ("availability", "Availability", "%", 1, "up", STEADY_AVAILABILITY_PT, "pt"),
    ("spCoal", "Sp. coal", "kg/kWh", 3, "down", STEADY_SP_COAL_PCT, "pct"),
    ("heatRate", "Heat rate", "kcal/kWh", 0, "down", STEADY_HEAT_RATE_PCT, "pct"),
    ("apcPct", "Aux. power", "%", 2, "down", STEADY_APC_PT, "pt"),
    ("spOil", "Sp. oil", "ml/kWh", 2, "down", STEADY_SP_OIL_PCT, "pct"),
    ("dmPct", "DM make-up", "%", 2, "down", STEADY_DM_PCT, "pct"),
)
DAY_METRICS = ("gen", "u1Gen", "u2Gen", "plf", "u1Plf", "u2Plf", "availability", "forcedOutage",
               "spCoal", "spOil", "apcPct", "heatRate", "dmPct", "backingDown", "trips", "btl")


def empty(today: date) -> dict:
    """The response when the database has no generation data at all."""
    return {"date": None, "today": today.isoformat(), "fy": calc.fiscal_year(today), "unitMw": 210,
            "days": [], "progress": None, "trends": [], "watch": []}


def analytics(entries: list[dict], config: dict, on: date, today: date,
              latest: date | None = None) -> dict:
    """Home-screen analysis of `on`.

    `entries` must reach back to the start of on's fiscal year (for the
    month/year progress and the stock roll-forward) and LOOKBACK_DAYS before
    `on` (for the trends). `latest` is the latest day with data in the whole
    database, for the "not uploaded yet" check; it defaults to the latest in
    `entries`.
    """
    by_date = {e["date"]: e for e in entries if e["date"] <= on.isoformat()}
    unit_cap = config.get("unitMw", 210) * HOURS_PER_DAY / 1000  # MU per unit per day at full load
    station_cap = 2 * unit_cap
    first = on - timedelta(days=LOOKBACK_DAYS)
    span = [first + timedelta(days=i) for i in range(LOOKBACK_DAYS + 1)]
    stocks = _coal_stock_series(by_date, config.get("coalStockAnchors") or [], first, on)

    sums: dict[date, dict] = {}
    for d in span:
        e = by_date.get(d.isoformat())
        if _has_data(e):
            # Same GCV rule as calc: never reaches back past the fiscal year's start.
            gcv = calc.latest_gcv(by_date, d, date(calc.fiscal_year(d), 4, 1))
            sums[d] = _day_sums(e, gcv["value"] if gcv else None)
    data_days = list(sums)  # oldest first
    recent = [sums[d] for d in data_days[-RECENT_DAYS:]]
    baseline = [sums[d] for d in data_days[-RECENT_DAYS - BASELINE_DAYS:-RECENT_DAYS]]

    days = [_public_day(d, sums.get(d), stocks[d], unit_cap, station_cap) for d in span[-DAYS_SHOWN:]]
    report = calc.performance_report(entries, config, on)
    recent_rate = sum(s["gen"] for s in recent) / len(recent) if recent else None
    progress = _progress(report, on, recent_rate)
    trends = _trends(recent, baseline, station_cap)

    if latest is None:
        latest = max((date.fromisoformat(iso) for iso, e in by_date.items() if _has_data(e)), default=None)
    # Within a level this order decides what survives the cut to MAX_WATCH:
    # things to act on this week before the slow-moving year target.
    found = [
        _stale(latest, today),
        _coal(stocks, on, recent),
        _target("monthTarget", progress["month"], f"{on:%B}", station_cap),
        _trips(report, by_date, on),
        _efficiency(trends),
        _oil(trends),
        _dm(trends),
        _apc(trends),
        _target("yearTarget", progress["year"], progress["year"]["label"], station_cap),
        _unit_gap(recent),
        _missing(report, on),
        _backing_down(report, on),
    ]
    # The Home screen shows target progress in full beside this list, so a
    # target is repeated here only when it is out of reach.
    found = [w for w in found if w and (w["key"] not in TARGET_KEYS or w["level"] == "alert")]
    ranked = sorted(found, key=lambda w: LEVELS.index(w["level"]))
    # Late or missing reports explain gaps in every other figure, so they are
    # always listed and do not take one of the MAX_WATCH places.
    kept = {id(w) for w in ranked if w["key"] in ALWAYS_LISTED}
    kept |= {id(w) for w in [w for w in ranked if w["key"] not in ALWAYS_LISTED][:MAX_WATCH]}
    watch = [w for w in ranked if id(w) in kept]

    return {
        "date": on.isoformat(),
        "today": today.isoformat(),
        "fy": calc.fiscal_year(on),
        "unitMw": config.get("unitMw", 210),
        "days": days,
        "progress": progress,
        "trends": trends,
        "watch": watch,
    }


# --- per-day figures -------------------------------------------------------------------

def _coal_stock_series(by_date: dict[str, dict], anchors: list[dict], first: date,
                       last: date) -> dict[date, float | None]:
    """calc._stock's closing coal stock for every day from `first` to `last`.

    Rolled forward one day at a time instead of from the anchor for each day.
    A day with its own figure (an opening balance or a printed stock) is taken
    from calc._stock, so every value is exactly the one calc gives.
    """
    seeds = {a["date"] for a in anchors} | {iso for iso, e in by_date.items() if e.get("coalStock") is not None}
    out: dict[date, float | None] = {}
    value: float | None = None
    d = first
    while d <= last:
        iso = d.isoformat()
        if d == first or iso in seeds:
            s = _stock(by_date, anchors, d, "coalStock", "coalReceipt", ("u1Coal", "u2Coal"))
            value = s["value"] if s else None
        elif value is not None:
            e = by_date.get(iso)
            value += _val(e, "coalReceipt") - _val(e, "u1Coal") - _val(e, "u2Coal")
        out[d] = value
        d += timedelta(days=1)
    return out


def _day_sums(e: dict, gcv: float | None) -> dict:
    """A day's station totals: the building blocks of every ratio. Blank counts
    as zero, as in calc, except APC, which is left out of the ratio when blank."""
    coal = _val(e, "u1Coal") + _val(e, "u2Coal")
    oil = _val(e, "u1Oil") + _val(e, "u2Oil")
    return {
        "u1Gen": _val(e, "u1Gen"), "u2Gen": _val(e, "u2Gen"),
        "gen": _val(e, "u1Gen") + _val(e, "u2Gen"),
        "u1Coal": _val(e, "u1Coal"), "u2Coal": _val(e, "u2Coal"),
        "coal": coal,
        "oil": oil,
        "dm": _val(e, "u1Dm") + _val(e, "u2Dm"),
        "apc": None if e.get("apc") is None else float(e["apc"]),
        "fo": _val(e, "u1Fo") + _val(e, "u2Fo"),
        "outage": _val(e, "u1Fo") + _val(e, "u2Fo") + _val(e, "u1Po") + _val(e, "u2Po"),
        "bd": _val(e, "u1Bd") + _val(e, "u2Bd"),
        "trips": _val(e, "u1Trip") + _val(e, "u2Trip"),
        "btl": _val(e, "u1Btl") + _val(e, "u2Btl"),
        # None without a known GCV, so the day drops out of heat-rate sums.
        "heat": None if gcv is None else calc.heat_input(coal, oil, gcv),
    }


def _ratio(num: float, den: float, scale: float = 1.0) -> float | None:
    return None if den == 0 else num / den * scale


def _metrics(days: list[dict], station_cap: float) -> dict[str, float | None]:
    """The trend figures over a run of days, as ratio-of-sums, so a 7 MU day
    weighs more than a 2 MU day. For a single day these are that day's figures,
    with calc's formulas."""
    if not days:
        return {key: None for key, *_ in TRENDS}
    gen = sum(s["gen"] for s in days)
    with_apc = [s for s in days if s["apc"] is not None]
    with_gcv = [s for s in days if s["heat"] is not None]
    return {
        "plf": gen / (station_cap * len(days)) * 100,
        "availability": 100 - sum(s["outage"] for s in days) / (2 * HOURS_PER_DAY * len(days)) * 100,
        "spCoal": _ratio(sum(s["coal"] for s in days), 1000 * gen),
        "heatRate": _ratio(sum(s["heat"] for s in with_gcv), 10 * sum(s["gen"] for s in with_gcv)),
        "apcPct": _ratio(sum(s["apc"] for s in with_apc), sum(s["gen"] for s in with_apc), 100),
        "spOil": _ratio(sum(s["oil"] for s in days), gen),
        "dmPct": _ratio(sum(s["dm"] for s in days) * 100, gen * 1000 * STEAM_T_PER_MWH),
    }


def _public_day(d: date, sums: dict | None, coal_stock: float | None, unit_cap: float,
                station_cap: float) -> dict:
    if sums is None:
        return {"date": d.isoformat(), "hasData": False, **dict.fromkeys(DAY_METRICS), "coalStock": coal_stock}
    m = _metrics([sums], station_cap)
    return {
        "date": d.isoformat(),
        "hasData": True,
        "gen": sums["gen"], "u1Gen": sums["u1Gen"], "u2Gen": sums["u2Gen"],
        "plf": m["plf"], "u1Plf": sums["u1Gen"] / unit_cap * 100, "u2Plf": sums["u2Gen"] / unit_cap * 100,
        "availability": m["availability"],
        "forcedOutage": sums["fo"],
        "spCoal": m["spCoal"], "spOil": m["spOil"], "apcPct": m["apcPct"],
        "heatRate": m["heatRate"], "dmPct": m["dmPct"],
        "backingDown": sums["bd"],
        "trips": sums["trips"], "btl": sums["btl"],
        "coalStock": coal_stock,
    }


# --- progress and trends ---------------------------------------------------------------

def _progress(report: dict, on: date, recent_rate: float | None) -> dict:
    rows = {r["key"]: r for r in report["rows"]}
    n, fy = report["days"], report["fy"]

    def scope(s: str, label: str, elapsed: int, total: int, missing: int) -> dict:
        target = rows["target"]["stn"][s]
        return {
            "label": label,
            "gen": rows["gen"]["stn"][s],
            "target": target,
            "expected": None if target is None else target * elapsed / total,
            "askingRate": rows["askingRate"]["stn"][s],
            "recentRate": recent_rate,
            "plf": rows["plf"]["stn"][s],
            "targetPlf": rows["targetPlf"]["stn"][s],
            "daysElapsed": elapsed,
            "daysTotal": total,
            # Days so far without data. calc counts them as zero, so gen and
            # the pace against target read low until they are uploaded.
            "daysMissing": missing,
        }

    return {
        "month": scope("month", f"{on:%B %Y}", n["month"], n["monthLength"], len(report["missing"]["month"])),
        "year": scope("year", f"FY {fy}-{(fy + 1) % 100:02d}", n["year"], n["yearLength"],
                      report["missing"]["year"]),
    }


def _status(change: float | None, change_pct: float | None, better: str, threshold: float, kind: str) -> str:
    if not change:  # unknown or no change
        return "steady"
    # A relative change from a zero baseline is unbounded, so it always counts.
    size = abs(change) if kind == "pt" else (math.inf if change_pct is None else abs(change_pct))
    if size < threshold:
        return "steady"
    return "better" if (change > 0) == (better == "up") else "worse"


def _trends(recent: list[dict], baseline: list[dict], station_cap: float) -> list[dict]:
    now, before = _metrics(recent, station_cap), _metrics(baseline, station_cap)
    out = []
    for key, label, unit, decimals, better, threshold, kind in TRENDS:
        r, b = now[key], before[key]
        change = None if r is None or b is None else r - b
        change_pct = None if change is None or b == 0 else change / b * 100
        out.append({
            "key": key, "label": label, "unit": unit, "decimals": decimals, "better": better,
            "recent": r, "baseline": b, "change": change, "changePct": change_pct,
            "status": _status(change, change_pct, better, threshold, kind),
            # Days with data behind each figure, so the screen can say when a baseline is thin.
            "recentDays": len(recent), "baselineDays": len(baseline),
        })
    return out


# --- watch list ------------------------------------------------------------------------

def _item(key: str, level: str, title: str, detail: str) -> dict:
    return {"key": key, "level": level, "title": title, "detail": detail}


def _mu(x: float) -> str:
    return f"{x:,.1f}" if abs(x) >= 10 else f"{x:.2f}"


def _plural(n: float, word: str) -> str:
    return f"{n:g} {word}{'' if n == 1 else 's'}"


def _day_label(d: date) -> str:
    return f"{d.day} {d:%b}"


def _days_list(days: list[date]) -> str:
    """Days of one month as '5, 6 Nov' or '2-5, 9 Nov'."""
    runs: list[list[date]] = []
    for d in days:
        if runs and (d - runs[-1][-1]).days == 1:
            runs[-1].append(d)
        else:
            runs.append([d])
    parts = [f"{r[0].day}-{r[-1].day}" if len(r) >= 3 else ", ".join(str(x.day) for x in r) for r in runs]
    return f"{', '.join(parts)} {days[0]:%b}"


def _compare(t: dict, recent: str, baseline: str) -> str:
    return (f"{recent} in the last {t['recentDays']} days with data, "
            f"against {baseline} in the {t['baselineDays']} before")


def _stale(latest: date | None, today: date) -> dict | None:
    if latest is None:
        return None
    age = (today - latest).days
    if age < STALE_INFO_DAYS:
        return None
    if age < STALE_WARN_DAYS:
        return _item("staleData", "info", "Yesterday's report not uploaded yet",
                     f"Latest data is for {_day_label(latest)}. "
                     f"The report printed today carries {_day_label(today - timedelta(days=1))}.")
    return _item("staleData", "warn", f"Latest data is {age} days old",
                 f"Latest data is for {_day_label(latest)}. "
                 f"The {age - 1} days since have not been uploaded.")


def _coal(stocks: dict[date, float | None], on: date, recent: list[dict]) -> dict | None:
    stock = stocks.get(on)
    if stock is None:
        return None
    week_ago = stocks.get(on - timedelta(days=7))
    change = ""
    if week_ago:  # unknown or zero gives no percentage
        pct = (stock - week_ago) / week_ago * 100
        change = (" About the same as a week ago." if abs(pct) < 1
                  else f" {'Down' if pct < 0 else 'Up'} {abs(pct):.0f}% in a week.")
    burn = sum(s["coal"] for s in recent) / len(recent) if recent else 0.0
    if burn <= 0:
        return _item("coalStock", "info", f"Coal stock {stock:,.0f} MT",
                     "No coal burnt in the recent days with data, so days of cover cannot be worked out." + change)
    cover = stock / burn
    level = "alert" if cover < COAL_ALERT_DAYS else "warn" if cover < COAL_WARN_DAYS else "info"
    # Rounded down, so the title never reads 7 days while the level says under 7.
    whole = math.floor(cover)
    title = "Coal stock covers under a day" if whole < 1 else f"Coal stock covers {_plural(whole, 'day')}"
    return _item("coalStock", level, title,
                 f"{stock:,.0f} MT left at {burn:,.0f} MT/day ({len(recent)}-day average).{change}")


def _target(key: str, p: dict, period: str, station_full: float) -> dict | None:
    target, gen = p["target"], p["gen"]
    if not target:  # none configured, or zero: nothing to measure against
        return None
    against = f"{_mu(gen)} MU against a target of {_mu(target)} MU."
    if gen >= target:
        return _item(key, "good", f"{period} target met", against)
    if p["daysElapsed"] >= p["daysTotal"]:  # last day: there is no pace left to keep
        return _item(key, "warn", f"{period} target missed by {_mu(target - gen)} MU", against)
    so_far = f"{_mu(gen)} of {_mu(target)} MU so far"
    if p["daysMissing"]:
        so_far += f" ({_plural(p['daysMissing'], 'day')} with no data)"
    asking, recent = p["askingRate"], p["recentRate"]
    if asking is not None and asking > station_full:
        return _item(key, "alert", f"{period} target out of reach",
                     f"It needs {asking:.2f} MU/day from here, above the station's full load of "
                     f"{station_full:.2f} MU/day. {so_far}.")
    pace = []
    if asking is not None:
        pace.append(f"needs {asking:.2f} MU/day from here")
    if recent is not None:
        pace.append(f"the last {RECENT_DAYS} days averaged {recent:.2f}")
    pace_text = "; ".join(pace)
    pace_text = f" {pace_text[:1].upper()}{pace_text[1:]}." if pace else ""
    gap = p["expected"] - gen
    detail = f"{so_far}, {_mu(p['expected'])} due by now.{pace_text}"
    if gap > 0:
        return _item(key, "warn", f"{period}: {_mu(gap)} MU behind target pace", detail)
    return _item(key, "good", f"{period}: {_mu(-gap)} MU ahead of target pace", detail)


def _trips(report: dict, by_date: dict[str, dict], on: date) -> dict | None:
    rows = {r["key"]: r for r in report["rows"]}
    trips = {u: rows["trips"][u]["month"] for u in ("u1", "u2")}
    btl = {u: rows["btl"][u]["month"] for u in ("u1", "u2")}
    total_trips, total_btl = sum(trips.values()), sum(btl.values())
    if not total_trips and not total_btl:
        return None
    counts = []
    if total_trips:
        counts.append(_plural(total_trips, "trip"))
    if total_btl:
        counts.append(_plural(total_btl, "tube leak"))
    lines = []
    for n, u in ((1, "u1"), (2, "u2")):
        bits = ([_plural(trips[u], "trip")] if trips[u] else []) + \
               ([_plural(btl[u], "boiler tube leak")] if btl[u] else [])
        if bits:
            lines.append(f"Unit {n}: {', '.join(bits)}.")
    reason = _latest_reason(by_date, on)
    if reason:
        lines.append(f"Latest reason ({reason[0]}): {reason[1]}")
    return _item("trips", "warn", f"{' and '.join(counts)} this month", " ".join(lines))


def _latest_reason(by_date: dict[str, dict], on: date) -> tuple[str, str] | None:
    """The most recent trip reason typed this month, as (where, text)."""
    d = on
    while d.month == on.month:
        e = by_date.get(d.isoformat()) or {}
        for n in (1, 2):
            text = (e.get(f"u{n}TripReason") or "").strip()
            if text:
                if len(text) > TRIP_REASON_CHARS:
                    text = text[:TRIP_REASON_CHARS - 1].rstrip() + "…"
                return f"Unit {n}, {_day_label(d)}", text
        d -= timedelta(days=1)
    return None


def _figure(t: dict, key: str, unit: bool = False) -> str:
    text = f"{t[key]:,.{t['decimals']}f}"
    return f"{text} {t['unit']}" if unit else text


def _efficiency(trends: list[dict]) -> dict | None:
    hits = [t for t in trends if t["key"] in ("spCoal", "heatRate") and t["status"] == "worse"
            and t["changePct"] is not None and t["changePct"] >= EFFICIENCY_WARN_PCT]
    if not hits:
        return None
    worst, *others = sorted(hits, key=lambda t: t["changePct"], reverse=True)
    detail = f"{worst['label']} {_compare(worst, _figure(worst, 'recent', unit=True), _figure(worst, 'baseline'))}."
    for t in others:
        detail += (f" {t['label']} {_figure(t, 'recent')} against {_figure(t, 'baseline', unit=True)}, "
                   f"up {t['changePct']:.0f}%.")
    return _item("efficiency", "warn", f"{worst['label']} up {worst['changePct']:.0f}% this week", detail)


def _trend(trends: list[dict], key: str) -> dict:
    return next(t for t in trends if t["key"] == key)


def _apc(trends: list[dict]) -> dict | None:
    t = _trend(trends, "apcPct")
    if t["status"] != "worse" or t["change"] < APC_WARN_PT:
        return None
    recent, baseline = f"{t['recent']:.2f}% of generation", f"{t['baseline']:.2f}%"
    return _item("apc", "warn", f"Aux. power up {t['change']:.1f} pt this week",
                 f"{_compare(t, recent, baseline)}.")


def _dm(trends: list[dict]) -> dict | None:
    t = _trend(trends, "dmPct")
    if t["status"] != "worse" or t["changePct"] is None or t["changePct"] < DM_WARN_PCT:
        return None
    recent, baseline = f"{t['recent']:.2f}% of steam", f"{t['baseline']:.2f}%"
    return _item("dm", "warn", f"DM make-up up {t['changePct']:.0f}% this week",
                 f"{_compare(t, recent, baseline)}. Rising make-up water often means steam or water leaks.")


def _oil(trends: list[dict]) -> dict | None:
    t = _trend(trends, "spOil")
    r, b = t["recent"], t["baseline"]
    if r is None or b is None or r <= OIL_WARN_MIN or r < OIL_WARN_RATIO * b:
        return None
    return _item("oil", "warn", f"Oil support up: {r:.2f} ml/kWh this week",
                 f"Against {b:.2f} ml/kWh in the {t['baselineDays']} days with data before. "
                 "Oil support usually means unstable firing or unit start-ups.")


def _unit_gap(recent: list[dict]) -> dict | None:
    # Only a full week with both units on load every day is a fair comparison.
    if len(recent) < RECENT_DAYS or not all(s["u1Gen"] > 0 and s["u2Gen"] > 0 for s in recent):
        return None
    sp = {n: _ratio(sum(s[f"u{n}Coal"] for s in recent), 1000 * sum(s[f"u{n}Gen"] for s in recent))
          for n in (1, 2)}
    if not sp[1] or not sp[2]:  # coal not recorded for a unit
        return None
    worse, better = (1, 2) if sp[1] > sp[2] else (2, 1)
    gap = (sp[worse] / sp[better] - 1) * 100
    if gap <= UNIT_GAP_PCT:
        return None
    return _item("unitGap", "info", f"Unit {worse} sp. coal {gap:.0f}% above Unit {better}",
                 f"{sp[worse]:.3f} against {sp[better]:.3f} kg/kWh over the last {RECENT_DAYS} days, "
                 "with both units on load every day.")


def _missing(report: dict, on: date) -> dict | None:
    missing = [date.fromisoformat(iso) for iso in report["missing"]["month"]]
    if not missing:
        return None
    return _item("missingDays", "info", f"{_plural(len(missing), 'day')} missing in {on:%B}",
                 f"No data for {_days_list(missing)}. Month totals count "
                 f"{'it' if len(missing) == 1 else 'them'} as zero.")


def _backing_down(report: dict, on: date) -> dict | None:
    rows = {r["key"]: r for r in report["rows"]}
    bd, gen = rows["backingDown"]["stn"]["month"], rows["gen"]["stn"]["month"]
    if bd <= 0:
        return None
    share = f", {bd / gen * 100:.1f}% of generation" if gen else ""
    return _item("backingDown", "info", f"Grid backing down: {_mu(bd)} MU this month",
                 f"{_mu(bd)} MU so far in {on:%B}{share}. "
                 "It is instructed by the grid, not a plant problem.")
