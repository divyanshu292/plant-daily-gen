"""calc.py against the plant workbook's own cached values.

The workbook-backed tests build entries with workbook_import.read_workbook()
and compare calc.performance_report() with what Excel last calculated. Where
calc deliberately departs from a workbook formula, the test proves that the
workbook's figure is exactly what its formula gives, so the difference is the
formula and nothing else.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest
from openpyxl.utils import get_column_letter
from openpyxl.utils.datetime import to_excel

import calc
from helpers import requires_workbook

REL = 1e-7
FY_START = date(2026, 4, 1)
FIRST_ROW, LAST_ROW = 3, 220  # 1 Apr 2026 .. 4 Nov 2026, row = 3 + days since 1 Apr
SCOPES = ("day", "month", "year")
COLS = ("u1", "u2", "stn")


def excel_number(value):
    """Durations come back from openpyxl as time, timedelta or a 1900 datetime."""
    if isinstance(value, (datetime, time, timedelta)):
        return to_excel(value)
    return value


def close(a: float, b: float) -> bool:
    return abs(a - b) <= REL * max(1.0, abs(b))


def report_for(book: dict, on: date) -> dict:
    config = calc.merge_config(calc.default_config(book["fy"]), book["config"])
    return calc.performance_report([e for e in book["entries"] if e["date"] <= on.isoformat()], config, on)


def rows_of(report: dict) -> dict:
    return {r["key"]: r for r in report["rows"]}


# --- DAILY REPORT sheet --------------------------------------------------------------------

REPORT_COLUMNS = {
    "B": ("u1", "day"), "C": ("u1", "month"), "D": ("u1", "year"),
    "E": ("u2", "day"), "F": ("u2", "month"), "G": ("u2", "year"),
    "H": ("stn", "day"), "I": ("stn", "month"), "J": ("stn", "year"),
}
ALL, UNITS, STATION = "BCDEFGHIJ", "BCDEFG", "HIJ"

# sheet row -> (row key, factor to turn the sheet value into ours, columns compared)
DAILY_REPORT_ROWS = {
    9: ("target", 1, "CDFGIJ"),
    10: ("targetPlf", 1, "CDFGIJ"),
    11: ("askingRate", 1, "DGJ"),  # C/F/I hold the text '?'
    13: ("gen", 1, ALL),
    14: ("plf", 100, ALL),
    15: ("loadingFactor", 100, UNITS),
    16: ("avgLoad", 1, ALL),
    17: ("runningHours", 24, UNITS),  # the sheet holds days
    18: ("availability", 100, UNITS),
    19: ("apc", 1, STATION),
    20: ("apcPct", 1, STATION),
    21: ("coal", 1, ALL),
    22: ("spCoal", 1, ALL),
    23: ("oil", 1, ALL),
    24: ("spOil", 1, ALL),
    25: ("dm", 1, ALL),
    26: ("dmPct", 1, ALL),
    27: ("heatRate", 1, ALL),
    32: ("backingDown", 1, ALL),
    33: ("deemedGen", 1, ALL),
    34: ("deemedPlf", 1, ALL),
    36: ("forcedOutage", 24, ALL),
    37: ("forcedOutagePct", 100, UNITS),
    38: ("plannedOutage", 24, ALL),
    39: ("plannedOutagePct", 100, UNITS),
    40: ("totalOutage", 24, ALL),
    41: ("totalOutagePct", 100, UNITS),
    42: ("trips", 1, ALL),
    43: ("btl", 1, ALL),
    44: ("btlShare", 100, ALL),  # B44 is '-' (no trips or leaks), where calc gives None
    46: ("oilReceipt", 1, STATION),
    47: ("coalReceipt", 1, STATION),
}


@pytest.fixture(scope="module")
def daily_report(book, cached):
    sheet = cached["DAILY REPORT"]
    on = sheet["C5"].value.date()
    return sheet, on, report_for(book, on)


@requires_workbook
def test_daily_report_is_for_30_october(daily_report):
    sheet, on, report = daily_report
    assert on == date(2026, 10, 30)
    assert report["days"] == {"month": 30, "monthLength": 31, "year": 213, "yearLength": 365}
    assert sheet["L3"].value == report["days"]["year"]  # 'No. of days in a Year'


@requires_workbook
@pytest.mark.parametrize("sheet_row", sorted(DAILY_REPORT_ROWS))
def test_daily_report_row(daily_report, sheet_row):
    sheet, _, report = daily_report
    key, factor, columns = DAILY_REPORT_ROWS[sheet_row]
    row = rows_of(report)[key]
    wrong = []
    for col in columns:
        unit, scope = REPORT_COLUMNS[col]
        theirs = excel_number(sheet[f"{col}{sheet_row}"].value)
        ours = None if row[unit] is None else row[unit][scope]
        if isinstance(theirs, (int, float)):
            ok = ours is not None and close(ours, theirs * factor)
        else:  # text such as '-' means 'not applicable'
            ok = ours is None
        if not ok:
            wrong.append(f"{col}{sheet_row}: workbook {theirs!r} x {factor}, calc {ours!r}")
    assert wrong == []


@requires_workbook
@pytest.mark.parametrize("cell, kind", [("B47", "coal"), ("B46", "oil")])
def test_daily_report_stock(daily_report, cell, kind):
    sheet, _, report = daily_report
    assert close(report["stocks"][kind]["value"], sheet[cell].value)


@requires_workbook
def test_asking_rate_month_cells_are_not_numbers(daily_report):
    """The sheet prints '?' for the monthly asking rate; calc computes it. Not compared."""
    sheet, _, report = daily_report
    assert [sheet[f"{c}11"].value for c in "CFI"] == ["?", "?", "?"]
    assert all(rows_of(report)["askingRate"][u]["month"] is not None for u in COLS)


# --- deliberate differences from the workbook ----------------------------------------------

@requires_workbook
def test_station_outage_figures_use_two_units_of_hours(daily_report):
    """The workbook divides the station's summed outage hours (both units) by one
    unit's 24 h a day; calc divides by 48 unit-hours. This affects station
    availability, outage %, loading factor and running hours (none in calc)."""
    sheet, _, report = daily_report
    rows = rows_of(report)
    days = {"day": 1, "month": report["days"]["month"], "year": report["days"]["year"]}
    for col in STATION:
        _, scope = REPORT_COLUMNS[col]
        outage_h = rows["totalOutage"]["stn"][scope]
        forced_h = rows["forcedOutage"]["stn"][scope]
        assert outage_h > 0  # otherwise the two definitions agree and this proves nothing

        one_unit_hours = 24 * days[scope]
        wb_availability = 1 - outage_h / one_unit_hours
        assert close(sheet[f"{col}18"].value, wb_availability)
        assert close(sheet[f"{col}37"].value, forced_h / one_unit_hours)
        assert close(sheet[f"{col}41"].value, outage_h / one_unit_hours)
        assert close(excel_number(sheet[f"{col}17"].value) * 24, one_unit_hours - outage_h)
        assert close(sheet[f"{col}15"].value, rows["plf"]["stn"][scope] / 100 / wb_availability)

        two_unit_hours = 48 * days[scope]
        assert close(rows["availability"]["stn"][scope], 100 - outage_h / two_unit_hours * 100)
        assert close(rows["forcedOutagePct"]["stn"][scope], forced_h / two_unit_hours * 100)
        assert close(rows["totalOutagePct"]["stn"][scope], outage_h / two_unit_hours * 100)
        assert close(rows["loadingFactor"]["stn"][scope],
                     rows["plf"]["stn"][scope] / rows["availability"]["stn"][scope] * 100)
        assert rows["runningHours"]["stn"] is None
        assert not close(rows["availability"]["stn"][scope], wb_availability * 100)


@requires_workbook
def test_partial_loading_uses_percentages(daily_report):
    """Rows 29-31: the workbook computes 100 - PLF - outage with PLF and outage
    as fractions (so it always shows about 99 %); calc uses percentages."""
    sheet, _, report = daily_report
    rows = rows_of(report)
    days = {"day": 1, "month": report["days"]["month"], "year": report["days"]["year"]}
    for col in ALL:
        unit, scope = REPORT_COLUMNS[col]
        if unit == "stn":  # the workbook's own station outage fractions (see above)
            fo = rows["forcedOutage"]["stn"][scope] / (24 * days[scope])
            po = rows["plannedOutage"]["stn"][scope] / (24 * days[scope])
        else:
            fo = rows["forcedOutagePct"][unit][scope] / 100
            po = rows["plannedOutagePct"][unit][scope] / 100
        wb_pct = 100 - rows["plf"][unit][scope] / 100 - fo - po
        wb_mu = wb_pct * 5.04 * (2 if unit == "stn" else 1) * days[scope] / 100
        assert close(sheet[f"{col}29"].value, wb_pct)
        assert close(sheet[f"{col}30"].value, wb_mu)
        assert close(sheet[f"{col}31"].value, wb_mu - rows["backingDown"][unit][scope])

        ours = rows["partialLoadingPct"][unit][scope]
        if unit != "stn":
            assert close(ours, 100 - rows["plf"][unit][scope] - rows["forcedOutagePct"][unit][scope]
                         - rows["plannedOutagePct"][unit][scope])
        assert ours < 50 < sheet[f"{col}29"].value


# --- every filled day against the cumulative sheets ------------------------------------------

def _groups(first_col: int, key: str, factor: float = 1):
    """Nine columns: daily U1/U2/Stn, then monthly, then yearly."""
    return [(first_col + 3 * s + u, key, COLS[u], SCOPES[s], factor) for s in range(3) for u in range(3)]


CUMULATIVE_SHEETS = {
    "GEN-PLF": _groups(2, "gen") + _groups(11, "plf"),
    "COAL OIL": (_groups(2, "coal") + _groups(11, "oil") + _groups(20, "dm") + _groups(29, "backingDown")
                 + _groups(38, "forcedOutage", 24) + _groups(47, "plannedOutage", 24)),
    "APC": [(2 + i, "apc", "stn", s, 1) for i, s in enumerate(SCOPES)]
           + [(6 + i, "coalReceipt", "stn", s, 1) for i, s in enumerate(SCOPES)]
           + [(9 + i, "oilReceipt", "stn", s, 1) for i, s in enumerate(SCOPES)],
    "TRIP BTL": _groups(2, "trips") + _groups(11, "btl"),
}

# TRIP BTL's monthly columns carry the previous month on into the 1st of these
# months and reset on the 2nd; calc resets on the 1st.
TRIP_BTL_LATE_RESET_ROWS = {33, 94, 125, 186}  # 1 May, 1 Jul, 1 Aug, 1 Oct 2026


@pytest.fixture(scope="module")
def every_day(book):
    """Sheet row -> calc rows, for every day the workbook has data."""
    out = {}
    for row in range(FIRST_ROW, LAST_ROW + 1):
        out[row] = report_for(book, FY_START + timedelta(days=row - FIRST_ROW))
    return out


@requires_workbook
def test_workbook_is_filled_to_4_november(book):
    assert book["entries"][0]["date"] == "2026-04-01"
    assert book["entries"][-1]["date"] == "2026-11-04"
    assert len(book["entries"]) == LAST_ROW - FIRST_ROW + 1


@requires_workbook
@pytest.mark.parametrize("sheet_name", sorted(CUMULATIVE_SHEETS))
def test_cumulative_sheet(cached, every_day, sheet_name):
    sheet = cached[sheet_name]
    wrong = []
    for row, report in every_day.items():
        assert sheet.cell(row, 1).value.date().isoformat() == report["date"]
        rows = rows_of(report)
        for col, key, unit, scope, factor in CUMULATIVE_SHEETS[sheet_name]:
            theirs = excel_number(sheet.cell(row, col).value) or 0
            if not close(rows[key][unit][scope], theirs * factor):
                wrong.append((row, get_column_letter(col), key, unit, scope))

    if sheet_name != "TRIP BTL":
        assert wrong == []
        return
    # The only differences are the workbook's late monthly reset, and there its
    # figure is yesterday's month-to-date plus today's daily count.
    assert {w[0] for w in wrong} == TRIP_BTL_LATE_RESET_ROWS
    assert {w[4] for w in wrong} == {"month"}
    for row in TRIP_BTL_LATE_RESET_ROWS:
        today, yesterday = rows_of(every_day[row]), rows_of(every_day[row - 1])
        for col, key, unit, scope, _ in CUMULATIVE_SHEETS["TRIP BTL"]:
            if scope == "month":
                carried = yesterday[key][unit]["month"] + today[key][unit]["day"]
                assert sheet.cell(row, col).value == carried
                assert today[key][unit]["month"] == today[key][unit]["day"]


COAL_REBASE_ROW = 74  # 11 Jun 2026


@requires_workbook
@pytest.mark.parametrize("col, kind", [(56, "coal"), (57, "oil")])
def test_stock_columns(cached, every_day, col, kind):
    sheet = cached["COAL OIL"]
    wrong = [row for row, report in every_day.items()
             if not close(report["stocks"][kind]["value"], sheet.cell(row, col).value)]
    if kind == "oil":
        assert wrong == []
        return
    # The plant re-based coal stock to 297,377.915 MT by typing that figure into
    # 12 June's formula as the previous closing balance. calc files it as the
    # closing stock of 11 June, so on that one day calc shows the re-based figure
    # while the workbook still shows the old balance rolled forward.
    assert wrong == [COAL_REBASE_ROW]
    rebased = every_day[COAL_REBASE_ROW]["stocks"]["coal"]
    assert rebased == {"value": 297377.915, "asOf": "2026-06-11", "source": "computed"}
    day = rows_of(every_day[COAL_REBASE_ROW])
    old_balance = sheet.cell(COAL_REBASE_ROW - 1, col).value + day["coalReceipt"]["stn"]["day"] - day["coal"]["stn"]["day"]
    assert close(sheet.cell(COAL_REBASE_ROW, col).value, old_balance)


@requires_workbook
def test_workbook_constants_match_calc_defaults(book):
    """calc carries the FY 2026-27 targets and stock anchors for when no workbook was imported."""
    defaults = calc.default_config(2026)
    for key in ("monthlyTargets", "coalStockAnchors", "oilStockAnchors"):
        assert book["config"][key] == defaults[key]


# --- calc on its own (no workbook needed) ----------------------------------------------------

def test_fiscal_year():
    assert calc.fiscal_year(date(2026, 4, 1)) == 2026
    assert calc.fiscal_year(date(2027, 3, 31)) == 2026
    assert calc.fiscal_year(date(2027, 4, 1)) == 2027


def test_config_defaults_and_merge():
    assert len(calc.default_config(2026)["monthlyTargets"]) == 12
    assert calc.default_config(2030)["monthlyTargets"] == {}
    merged = calc.merge_config(calc.default_config(2030), {"unitMw": 200, "bogus": 1, "monthlyTargets": None})
    assert merged["unitMw"] == 200 and "bogus" not in merged and merged["monthlyTargets"] == {}


def _entry(iso: str, **fields) -> dict:
    base = {"u1Gen": 0.0, "u2Gen": 0.0, "u1Fo": 0.0, "u2Fo": 0.0, "u1Po": 0.0, "u2Po": 0.0}
    return {"date": iso, **base, **fields}


def test_small_month_by_hand():
    entries = [
        _entry("2027-05-01", u1Gen=5.04, u2Gen=2.52, u1Coal=3000.0, u2Coal=1500.0, u1Trip=1.0, u1Btl=1.0,
               coalReceipt=1000.0, apc=0.8),
        _entry("2027-05-02", u1Gen=2.52, u2Gen=0.0, u2Fo=24.0, u1Coal=1500.0, u2Btl=1.0, gcv=3500.0, apc=0.4),
    ]
    report = calc.performance_report(entries, calc.default_config(2027), date(2027, 5, 2))
    rows = rows_of(report)
    assert report["fy"] == 2027 and report["hasData"]
    assert rows["gen"]["stn"] == {"day": 2.52, "month": 10.08, "year": 10.08}
    assert rows["plf"]["u1"]["month"] == pytest.approx(75.0)
    # Unit 2 was out all day on the 2nd: availability 0, half the month; the station
    # lost 24 of 48 unit-hours that day.
    assert rows["availability"]["u2"]["day"] == 0
    assert rows["availability"]["u2"]["month"] == pytest.approx(50.0)
    assert rows["availability"]["stn"]["day"] == pytest.approx(50.0)
    assert rows["loadingFactor"]["u2"]["day"] == 0
    # Days without data count as zero outage, as blanks do in the workbook (and the
    # report says so in its notes): April's 30 days add 720 h to the year.
    assert rows["runningHours"]["u2"] == {"day": 0.0, "month": 24.0, "year": 744.0}
    assert rows["runningHours"]["stn"] is None
    assert rows["apc"]["u1"] is None and rows["apc"]["stn"]["month"] == pytest.approx(1.2)
    assert rows["apcPct"]["stn"]["month"] == pytest.approx(1.2 / 10.08 * 100)
    assert rows["spCoal"]["u1"]["day"] == pytest.approx(1500 / 2520)
    assert rows["btlShare"]["u1"]["month"] == pytest.approx(50.0)
    assert rows["btlShare"]["u2"]["month"] == pytest.approx(100.0)
    assert rows["btlShare"]["u2"]["day"] == pytest.approx(100.0)
    assert rows["btlShare"]["u1"]["day"] is None  # no trips and no leaks: not applicable
    # No GCV before the 2nd (the workbook uses the day before's GCV).
    assert report["gcv"] is None and rows["heatRate"]["u1"]["day"] is None
    # No targets configured for FY 2027.
    assert rows["target"]["stn"]["month"] is None and rows["askingRate"]["stn"]["year"] is None
    # April had no data at all.
    assert report["missing"] == {"month": [], "year": 30}
    assert any("30 day(s)" in n for n in report["notes"])


def test_heat_rate_uses_previous_days_gcv():
    entries = [_entry("2026-04-01", u1Gen=3.0, gcv=3400.0), _entry("2026-04-02", u1Gen=3.0, u1Coal=2400.0, gcv=9999.0)]
    report = calc.performance_report(entries, calc.default_config(2026), date(2026, 4, 2))
    assert report["gcv"] == {"value": 3400.0, "date": "2026-04-01"}
    assert rows_of(report)["heatRate"]["u1"]["day"] == pytest.approx(
        (2400 * 3400 / 100 - 0.01 * 2400 / 100) / (3.0 * 10))


def test_stock_prefers_printed_figure_over_opening_balance():
    config = {**calc.default_config(2030), "coalStockAnchors": [{"date": "2030-04-01", "stock": 1000.0}]}
    entries = [
        _entry("2030-04-01", u1Gen=1.0),
        _entry("2030-04-02", u1Gen=1.0, u1Coal=100.0, coalReceipt=50.0),
        _entry("2030-04-03", u1Gen=1.0, u1Coal=100.0, coalStock=777.0),
        _entry("2030-04-04", u1Gen=1.0, u1Coal=10.0, coalReceipt=20.0),
    ]
    stock = lambda d: calc.performance_report(entries, config, d)["stocks"]["coal"]  # noqa: E731
    assert stock(date(2030, 4, 2)) == {"value": 950.0, "asOf": "2030-04-01", "source": "computed"}
    assert stock(date(2030, 4, 3)) == {"value": 777.0, "asOf": "2030-04-03", "source": "report"}
    assert stock(date(2030, 4, 4)) == {"value": 787.0, "asOf": "2030-04-03", "source": "computed"}
    assert calc.performance_report(entries, config, date(2030, 4, 4))["stocks"]["oil"] is None


def test_asking_rate_notes_unreachable_target():
    config = {**calc.default_config(2030), "monthlyTargets": {"2030-04": {"u1": 150.0, "u2": 4.0}}}
    report = calc.performance_report([_entry("2030-04-29", u1Gen=1.0)], config, date(2030, 4, 29))
    rows = rows_of(report)
    assert rows["askingRate"]["u1"]["month"] == pytest.approx((150 - 1) / 1)
    assert rows["askingRate"]["u1"]["year"] is None  # the other eleven months have no target
    assert any(n.startswith("Unit 1 month target is out of reach") for n in report["notes"])
    assert not any(n.startswith("Unit 2") for n in report["notes"])
