"""Performance figures derived from the daily entries.

This is the plant workbook's GEN-PLF, COAL OIL, TRIP BTL, APC and DAILY REPORT
sheets as code: daily, month-to-date and fiscal-year-to-date figures for Unit 1,
Unit 2 and the station. tests/test_calc.py checks it against the workbook's own
cached values.

Where the workbook is plainly wrong, this module computes what was meant and
says so in a comment next to the formula.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

HOURS_PER_DAY = 24
# Heat value of light diesel oil used by the workbook: 10,140 kcal per litre.
OIL_KCAL_PER_LITRE = 10140
# Steam consumed per MWh generated, the base the workbook uses for make-up %.
STEAM_T_PER_MWH = 3.1
# The workbook's yearly asking rate assumes 12 % of the remaining days are lost
# to forced outage, after setting aside 2 days per unit (0.8 for the station).
ASKING_FORCED_OUTAGE = 0.12
ASKING_RESERVED_DAYS = {"u1": 2, "u2": 2, "stn": 0.8}

CONFIG_KEYS = {"unitMw", "monthlyTargets", "coalStockAnchors", "oilStockAnchors"}

# Constants typed into the FY 2026-27 workbook (TARGET sheet, COAL OIL!BD3/BD75/BE3).
_FY2026 = {
    "monthlyTargets": {
        "2026-04": {"u1": 100.0, "u2": 115.2}, "2026-05": {"u1": 105.0, "u2": 111.6},
        "2026-06": {"u1": 102.0, "u2": 108.0}, "2026-07": {"u1": 0.0, "u2": 115.2},
        "2026-08": {"u1": 111.6, "u2": 122.76}, "2026-09": {"u1": 108.0, "u2": 118.8},
        "2026-10": {"u1": 111.6, "u2": 122.76}, "2026-11": {"u1": 108.0, "u2": 115.2},
        "2026-12": {"u1": 111.6, "u2": 122.76}, "2027-01": {"u1": 111.6, "u2": 122.76},
        "2027-02": {"u1": 100.8, "u2": 110.88}, "2027-03": {"u1": 111.6, "u2": 122.76},
    },
    # Closing stock at the end of the given day.
    "coalStockAnchors": [
        {"date": "2026-04-01", "stock": 518696.75},
        {"date": "2026-06-11", "stock": 297377.915},  # stock re-based by the plant on 12 June
    ],
    "oilStockAnchors": [{"date": "2026-04-01", "stock": 528.286}],
}


def fiscal_year(d: date) -> int:
    """Indian fiscal year: 2026 means 1 Apr 2026 to 31 Mar 2027."""
    return d.year if d.month >= 4 else d.year - 1


def default_config(fy: int) -> dict:
    base = {"fy": fy, "unitMw": 210, "monthlyTargets": {}, "coalStockAnchors": [], "oilStockAnchors": []}
    if fy == 2026:
        base.update(_FY2026)
    return base


def merge_config(base: dict, stored: dict) -> dict:
    return {**base, **{k: v for k, v in stored.items() if k in CONFIG_KEYS and v is not None}}


def _val(entry: dict | None, key: str) -> float:
    """Blank counts as zero, as it does in the workbook."""
    if not entry:
        return 0.0
    v = entry.get(key)
    return 0.0 if v is None else float(v)


def _has_data(entry: dict | None) -> bool:
    return bool(entry) and (entry.get("u1Gen") is not None or entry.get("u2Gen") is not None)


def _stock(by_date: dict[str, dict], anchors: list[dict], on: date,
           stock_key: str, receipt_key: str, used_keys: tuple[str, str]) -> dict | None:
    """Stock at the end of `on`: the latest known figure rolled forward by
    receipts minus consumption. A figure printed on a day's report beats the
    workbook's opening balance, because it is the plant's official number."""
    best: tuple[str, float, str] | None = None
    for a in anchors:
        if a["date"] <= on.isoformat() and (best is None or a["date"] > best[0]):
            best = (a["date"], float(a["stock"]), "opening")
    for iso, e in by_date.items():
        if e.get(stock_key) is not None and iso <= on.isoformat() and (best is None or iso >= best[0]):
            best = (iso, float(e[stock_key]), "report")
    if best is None:
        return None
    anchor_date, value, kind = best
    d = date.fromisoformat(anchor_date) + timedelta(days=1)
    while d <= on:
        e = by_date.get(d.isoformat())
        value += _val(e, receipt_key) - _val(e, used_keys[0]) - _val(e, used_keys[1])
        d += timedelta(days=1)
    printed_today = kind == "report" and anchor_date == on.isoformat()
    return {"value": value, "asOf": anchor_date, "source": "report" if printed_today else "computed"}


def latest_gcv(by_date: dict[str, dict], on: date, since: date) -> dict | None:
    """Coal GCV for the heat rate of `on`: the day before's, like the workbook.
    The lab figure arrives late, so fall back to the most recent one known,
    looking no further back than `since`."""
    d = on - timedelta(days=1)
    while d >= since:
        e = by_date.get(d.isoformat())
        if e and e.get("gcv"):
            return {"value": float(e["gcv"]), "date": d.isoformat()}
        d -= timedelta(days=1)
    return None


def heat_input(coal: float, oil: float, gcv: float) -> float:
    """Heat fired, scaled so that heat_input / (10 * gen in MU) is kcal/kWh.
    Coal in MT at `gcv` kcal/kg, oil in KL. The 0.01 * coal term is the
    workbook's own and is kept as is."""
    return (coal * gcv / 100) + (oil * OIL_KCAL_PER_LITRE / 100) - (0.01 * coal / 100)


def heat_rate(coal: float, oil: float, gen: float, gcv: float | None) -> float | None:
    """Heat rate in kcal/kWh; None without a GCV or without generation."""
    if gcv is None or gen == 0:
        return None
    return heat_input(coal, oil, gcv) / (gen * 10)


def performance_report(entries: list[dict], config: dict, on: date) -> dict:
    """Daily, month-to-date and year-to-date figures for `on`.

    `entries` are the daily records of the fiscal year up to `on` (others are
    ignored). Each cell is {"day", "month", "year"}; None means not applicable.
    """
    fy = fiscal_year(on)
    fy_start = date(fy, 4, 1)
    fy_days = (date(fy + 1, 4, 1) - fy_start).days
    month_start = on.replace(day=1)
    month_len = monthrange(on.year, on.month)[1]
    by_date = {e["date"]: e for e in entries if fy_start.isoformat() <= e["date"] <= on.isoformat()}

    span = [fy_start + timedelta(days=i) for i in range((on - fy_start).days + 1)]
    n_days = {"day": 1, "month": on.day, "year": len(span)}
    unit_mw = config.get("unitMw", 210)
    unit_cap = unit_mw * HOURS_PER_DAY / 1000  # MU per unit per day at full load (5.04)
    units = {"u1": 1, "u2": 1, "stn": 2}
    scopes = ("day", "month", "year")
    cols = ("u1", "u2", "stn")

    def total(key: str) -> dict:
        """Sum of one entry field for the day, the month so far and the year so far."""
        day = _val(by_date.get(on.isoformat()), key)
        month = year = 0.0
        for d in span:
            v = _val(by_date.get(d.isoformat()), key)
            year += v
            if d >= month_start:
                month += v
        return {"day": day, "month": month, "year": year}

    def per_unit(suffix: str) -> dict:
        u1, u2 = total(f"u1{suffix}"), total(f"u2{suffix}")
        return {"u1": u1, "u2": u2, "stn": {s: u1[s] + u2[s] for s in scopes}}

    def cells(fn) -> dict:
        return {c: {s: fn(c, s) for s in scopes} for c in cols}

    def station_only(values: dict) -> dict:
        return {"u1": None, "u2": None, "stn": values}

    gen, coal, oil, dm = per_unit("Gen"), per_unit("Coal"), per_unit("Oil"), per_unit("Dm")
    bd, fo, po = per_unit("Bd"), per_unit("Fo"), per_unit("Po")
    trips, btl, h2 = per_unit("Trip"), per_unit("Btl"), per_unit("H2")
    apc, coal_rcpt, oil_rcpt = total("apc"), total("coalReceipt"), total("oilReceipt")

    def cap_mu(c: str, s: str) -> float:
        return unit_cap * units[c] * n_days[s]

    def hours_base(c: str, s: str) -> float:
        # The workbook divides the station's summed outage hours by one unit's
        # 24 h, which understates station availability. Two units have 48 h a day.
        return HOURS_PER_DAY * units[c] * n_days[s]

    def ratio(num: float, den: float, scale: float = 1.0) -> float | None:
        return None if den == 0 else num / den * scale

    plf = cells(lambda c, s: gen[c][s] / cap_mu(c, s) * 100)
    fo_pct = cells(lambda c, s: fo[c][s] / hours_base(c, s) * 100)
    po_pct = cells(lambda c, s: po[c][s] / hours_base(c, s) * 100)
    availability = cells(lambda c, s: 100 - fo_pct[c][s] - po_pct[c][s])
    loading = cells(lambda c, s: 0.0 if availability[c][s] == 0 else plf[c][s] / availability[c][s] * 100)
    avg_load = {c: {s: loading[c][s] / 100 * unit_mw for s in scopes} for c in ("u1", "u2")}
    avg_load["stn"] = {s: avg_load["u1"][s] + avg_load["u2"][s] for s in scopes}
    running = {c: {s: hours_base(c, s) - fo[c][s] - po[c][s] for s in scopes} for c in ("u1", "u2")}
    running["stn"] = None  # hours of two units do not add up to a meaningful station figure

    gcv = latest_gcv(by_date, on, fy_start)

    def heat_rate_cell(c: str, s: str) -> float | None:
        return heat_rate(coal[c][s], oil[c][s], gen[c][s], gcv["value"] if gcv else None)

    # Capacity not used while the unit was available. The workbook subtracts
    # fractions from 100 here (always giving about 99); this is the intended
    # 100 % - PLF % - outage %.
    partial_pct = cells(lambda c, s: 100 - plf[c][s] - fo_pct[c][s] - po_pct[c][s])
    partial_mu = cells(lambda c, s: partial_pct[c][s] * cap_mu(c, s) / 100)
    deemed = cells(lambda c, s: gen[c][s] + bd[c][s])

    # Targets ----------------------------------------------------------------
    targets = config.get("monthlyTargets") or {}
    month_target = targets.get(f"{on.year}-{on.month:02d}")
    year_keys = [f"{fy + (m < 4)}-{m:02d}" for m in (4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3)]
    have_year = all(k in targets for k in year_keys)

    def target(c: str, s: str) -> float | None:
        def of(t: dict) -> float:
            return t["u1"] + t["u2"] if c == "stn" else t[c]
        if s == "month":
            return of(month_target) if month_target else None
        if s == "year":
            return sum(of(targets[k]) for k in year_keys) if have_year else None
        return None

    def target_plf(c: str, s: str) -> float | None:
        t = target(c, s)
        if t is None:
            return None
        return t * 100 / (unit_cap * units[c] * (month_len if s == "month" else fy_days))

    notes: list[str] = []

    def asking_rate(c: str, s: str) -> float | None:
        t = target(c, s)
        if t is None:
            return None
        if s == "month":
            left = month_len - on.day
        else:
            left = fy_days - n_days["year"] - ASKING_RESERVED_DAYS[c]
            left -= left * ASKING_FORCED_OUTAGE
        if left <= 0:
            return None
        rate = (t - gen[c][s]) / left
        if rate > unit_cap * units[c]:
            label = {"u1": "Unit 1", "u2": "Unit 2", "stn": "Station"}[c]
            notes.append(f"{label} {s} target is out of reach: it needs {rate:.2f} MU/day, "
                         f"above the full-load {unit_cap * units[c]:.2f} MU/day.")
        return rate

    def row(key, label, unit, kind, decimals, values):
        return {"key": key, "label": label, "unit": unit, "kind": kind, "decimals": decimals, **values}

    rows = [
        row("target", "Target", "MU", "number", 2, cells(target)),
        row("targetPlf", "Target PLF", "%", "percent", 2, cells(target_plf)),
        row("askingRate", "Asking rate", "MU/day", "number", 2, cells(asking_rate)),
        row("gen", "Generation", "MU", "number", 2, gen),
        row("plf", "PLF", "%", "percent", 2, plf),
        row("loadingFactor", "Loading factor", "%", "percent", 2, loading),
        row("avgLoad", "Average load", "MW", "number", 2, avg_load),
        row("runningHours", "Running hours", "h:mm", "hours", 0, running),
        row("availability", "Availability", "%", "percent", 2, availability),
        row("apc", "Aux. power consumption", "MU", "number", 3, station_only(apc)),
        row("apcPct", "Aux. power consumption", "%", "percent", 2,
            station_only({s: ratio(apc[s], gen["stn"][s], 100) for s in scopes})),
        row("coal", "Coal consumption", "MT", "number", 2, coal),
        row("spCoal", "Sp. coal consumption", "kg/kWh", "number", 3,
            cells(lambda c, s: ratio(coal[c][s], 1000 * gen[c][s]))),
        row("oil", "Oil consumption", "KL", "number", 2, oil),
        row("spOil", "Sp. oil consumption", "ml/kWh", "number", 3,
            cells(lambda c, s: ratio(oil[c][s], gen[c][s]))),
        row("dm", "DM make-up water", "m³", "number", 0, dm),
        row("dmPct", "Make-up", "%", "percent", 2,
            cells(lambda c, s: ratio(dm[c][s] * 100, gen[c][s] * 1000 * STEAM_T_PER_MWH))),
        row("heatRate", "Heat rate", "kcal/kWh", "number", 0, cells(heat_rate_cell)),
        row("partialLoadingPct", "Partial loading", "%", "percent", 2, partial_pct),
        row("partialLoading", "Partial loading", "MU", "number", 3, partial_mu),
        row("stationLoss", "- due to station problems", "MU", "number", 3,
            cells(lambda c, s: partial_mu[c][s] - bd[c][s])),
        row("backingDown", "- due to grid backing down", "MU", "number", 3, bd),
        row("deemedGen", "Deemed generation", "MU", "number", 3, deemed),
        row("deemedPlf", "Deemed PLF", "%", "percent", 2,
            cells(lambda c, s: deemed[c][s] * 100 / cap_mu(c, s))),
        row("forcedOutage", "Forced outage", "h:mm", "hours", 0, fo),
        row("forcedOutagePct", "Forced outage", "%", "percent", 2, fo_pct),
        row("plannedOutage", "Planned outage", "h:mm", "hours", 0, po),
        row("plannedOutagePct", "Planned outage", "%", "percent", 2, po_pct),
        row("totalOutage", "Total outage", "h:mm", "hours", 0,
            cells(lambda c, s: fo[c][s] + po[c][s])),
        row("totalOutagePct", "Total outage", "%", "percent", 2,
            cells(lambda c, s: fo_pct[c][s] + po_pct[c][s])),
        row("trips", "Trips", "nos.", "count", 0, trips),
        row("btl", "Boiler tube leaks", "nos.", "count", 0, btl),
        row("btlShare", "BTL share of outages", "%", "percent", 2,
            cells(lambda c, s: ratio(btl[c][s], trips[c][s] + btl[c][s], 100))),
        row("h2", "H₂ consumption", "cylinders", "count", 0, h2),
        row("coalReceipt", "Coal receipt", "MT", "number", 2, station_only(coal_rcpt)),
        row("oilReceipt", "Oil receipt", "KL", "number", 3, station_only(oil_rcpt)),
    ]

    missing_month = [d.isoformat() for d in span if d >= month_start and not _has_data(by_date.get(d.isoformat()))]
    missing_year = sum(1 for d in span if not _has_data(by_date.get(d.isoformat())))
    if missing_year:
        notes.append(
            f"{missing_year} day(s) since 1 April have no data, {len(missing_month)} of them this month. "
            "Month and year figures count those days as zero."
        )

    return {
        "date": on.isoformat(),
        "fy": fy,
        "hasData": _has_data(by_date.get(on.isoformat())),
        "days": {"month": on.day, "monthLength": month_len, "year": len(span), "yearLength": fy_days},
        "missing": {"month": missing_month, "year": missing_year},
        "gcv": gcv,
        "stocks": {
            "coal": _stock(by_date, config.get("coalStockAnchors") or [], on,
                           "coalStock", "coalReceipt", ("u1Coal", "u2Coal")),
            "oil": _stock(by_date, config.get("oilStockAnchors") or [], on,
                          "oilStock", "oilReceipt", ("u1Oil", "u2Oil")),
        },
        "rows": rows,
        "notes": notes,
    }
