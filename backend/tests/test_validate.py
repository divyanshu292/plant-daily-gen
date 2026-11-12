"""validate.py: parsing printed cells, the page's own arithmetic, and the
comparisons with what the database already holds."""

from __future__ import annotations

from datetime import date

import pytest

from helpers import PAGE_1, PAGE_2, get_cell, load_report, requires_workbook, set_cell
from validate import cross_checks, hours, num, parse_report_date, validate

TODAY = date(2026, 11, 12)

EXPECTED = {
    PAGE_1: {
        "report_date": date(2026, 11, 4),
        "data_date": date(2026, 11, 3),
        "entry": {
            "u1Gen": 3.48, "u2Gen": 3.68, "u1Coal": 2656.0, "u2Coal": 3011.0, "u1Oil": 0.0, "u2Oil": 9.0,
            "u1Dm": 111.0, "u2Dm": 256.0, "apc": 0.7931, "apcPlant": 0.76514, "apcSub": 0.028,
            "u1Fo": 0.0, "u2Fo": 0.0, "u1H2": 8.0, "u2H2": 6.0, "u1Bd": 0.0, "u2Bd": 0.0,
            "coalReceipt": 3617.7, "coalReceiptRoad": 0.0, "coalReceiptRail": 3617.7, "oilReceipt": 0.0,
            "coalStock": 12246.51, "oilStock": 349.286, "oilPipeline": 100.0,
            "u1Remark": "On Load", "u2Remark": "On Load",
        },
    },
    PAGE_2: {
        "report_date": date(2026, 11, 11),
        "data_date": date(2026, 11, 10),
        "entry": {
            "u1Gen": 3.53, "u2Gen": 3.79, "u1Coal": 2496.0, "u2Coal": 2770.4, "u1Oil": 0.0, "u2Oil": 0.0,
            "u1Dm": 113.0, "u2Dm": 268.0, "apc": 0.802, "apcPlant": 0.77397, "apcSub": 0.028,
            "u1Fo": 0.0, "u2Fo": 0.0, "u1H2": 8.0, "u2H2": 9.0, "u1Bd": 0.046, "u2Bd": 0.084,
            "coalReceipt": 3852.4, "coalReceiptRoad": 0.0, "coalReceiptRail": 3852.4, "oilReceipt": 0.0,
            "coalStock": 13007.25, "oilStock": 436.286, "oilPipeline": 13.0,
            "u1Remark": "On Load", "u2Remark": "On Load",
        },
    },
}

# Every arithmetic check the page supports. If one of these goes missing, a
# misread in its cells would no longer be caught.
ALL_CHECKS = {
    "gen_total", "coal_total", "oil_total", "dm_total", "h2_total", "bd_total", "receipt_total",
    "apc_total", "outage_total", "apc_pct",
    *(f"{c}_{k}" for c in ("plf", "sp_coal", "sp_oil") for k in ("unit1", "unit2", "station")),
    *(f"{c}_{k}" for c in ("paf", "dm_pct") for k in ("unit1", "unit2")),
}


# --- the two real pages --------------------------------------------------------------

@pytest.mark.parametrize("page", [PAGE_1, PAGE_2])
def test_real_page_passes_every_check(page):
    result = validate(load_report(page), today=TODAY)
    assert {c.id for c in result.checks} == ALL_CHECKS
    assert [c for c in result.checks if not c.ok] == []
    assert result.ok
    assert result.recheck_hints() == []


@pytest.mark.parametrize("page", [PAGE_1, PAGE_2])
def test_real_page_gives_expected_entry(page):
    result = validate(load_report(page), today=TODAY)
    expected = EXPECTED[page]
    assert result.report_date == expected["report_date"]
    # The page is published the morning after: its figures belong to the day before.
    assert result.data_date == expected["data_date"]
    assert result.entry == expected["entry"]


# Fields the printed page and the workbook's DAILY DATA sheet both carry.
SHARED_FIELDS = ("u1Gen", "u2Gen", "u1Coal", "u2Coal", "u1Oil", "u2Oil", "u1Bd", "u2Bd", "apc",
                 "coalReceipt", "oilReceipt", "u1Dm", "u2Dm", "u1Fo", "u2Fo")


@requires_workbook
def test_page_matches_workbook_row(book):
    page = validate(load_report(PAGE_1), today=TODAY)
    row = next(e for e in book["entries"] if e["date"] == "2026-11-03")
    assert page.data_date.isoformat() == row["date"]
    assert {f: page.entry[f] for f in SHARED_FIELDS} == pytest.approx({f: row[f] for f in SHARED_FIELDS}, abs=1e-9)


# --- a misread digit in any stored cell must block auto-save ---------------------------

STORED_CELLS = (
    "r04_gen.unit1", "r04_gen.unit2",
    "r07_coal.unit1", "r07_coal.unit2",
    "r08_oil.unit1", "r08_oil.unit2",
    "r09_dm_water.unit1", "r09_dm_water.unit2",
    "r10_aux_power.station", "r10_aux_power.plant", "r10_aux_power.substation",
    "r15_backing_down.unit1", "r15_backing_down.unit2",
    "r28_coal_transported.road", "r28_coal_transported.rail", "r28_coal_transported.total",
    "r11_outage.unit1", "r11_outage.unit2",
    "r14_h2.unit1", "r14_h2.unit2",
)

# Changes the page itself cannot reveal, because every cell that depends on
# them is printed more coarsely. Each entry: cell -> (reason, test on the index
# of the changed character in the printed text).
BELOW_PAGE_RESOLUTION = {
    # Station aux. power is printed to 4 decimals and plant % to 2, so the plant
    # figure's 5th decimal is invisible to both. (apcPlant is stored for
    # reference only; calc uses the station figure, which is fully checked.)
    "r10_aux_power.plant": ("5th decimal of the plant figure", lambda text, i: i == len(text) - 1),
    # Availability is printed to 2 decimals (0.01 % of 24 h = 8.6 s), so a few
    # seconds of outage do not show anywhere else on the page.
    "r11_outage.unit1": ("seconds of outage", lambda text, i: i >= len(text) - 2),
    "r11_outage.unit2": ("seconds of outage", lambda text, i: i >= len(text) - 2),
}


def _misreads(text: str):
    """Every way of reading one printed digit as another."""
    for i, ch in enumerate(text):
        if ch.isdigit():
            for d in "0123456789":
                if d != ch:
                    yield i, text[:i] + d + text[i + 1:]


@pytest.mark.parametrize("page", [PAGE_1, PAGE_2])
@pytest.mark.parametrize("cell", STORED_CELLS)
def test_every_misread_digit_is_caught(page, cell):
    original = get_cell(load_report(page), cell)
    allowed = BELOW_PAGE_RESOLUTION.get(cell)
    slipped, tried = [], 0
    for i, misread in _misreads(original):
        if allowed and allowed[1](original, i):
            continue
        tried += 1
        report = load_report(page)
        set_cell(report, cell, misread)
        result = validate(report, today=TODAY)
        if result.ok:
            slipped.append(misread)
        else:
            # The retry prompt names the cells of the failed checks, so the
            # misread cell must be among them.
            assert any(cell in c.cells for c in result.errors), (misread, result.recheck_hints())
    assert tried > 0
    assert slipped == [], f"{cell} printed {original!r}: these misreads pass every check"


@pytest.mark.parametrize("cell, misread", [
    ("r10_aux_power.plant", "0.76515"),  # printed 0.76514
    ("r11_outage.unit1", "0:00:05"),     # printed 0:00:00
])
def test_misreads_below_page_resolution_pass(cell, misread):
    """Pins down the gaps listed in BELOW_PAGE_RESOLUTION, so closing or widening one is deliberate."""
    report = load_report(PAGE_1)
    set_cell(report, cell, misread)
    assert validate(report, today=TODAY).ok


def test_unchecked_stored_cells():
    """Stocks, oil receipt and oil in pipeline have no arithmetic on the page.

    A misread there is saved as read; only the stock roll-forward in
    cross_checks (a warning) can notice it. This test pins that fact down so a
    change in either direction is deliberate.
    """
    for cell, misread in (("r30_usable_coal_stock", "12846.51"), ("r32_usable_oil_stock", "348.286"),
                          ("r31_oil_transported", "8.000"), ("r31_oil_in_pipeline", "180")):
        report = load_report(PAGE_1)
        set_cell(report, cell, misread)
        assert validate(report, today=TODAY).ok, cell


def test_station_total_tolerances():
    # Generation is metered to more decimals than printed, so the station figure
    # may be one unit off the printed parts (with its ratios printed to match)...
    report = load_report(PAGE_1)
    report.r04_gen.station, report.r05_plf.station = "7.17", "71.13"
    report.r12_sp_coal.station, report.r13_sp_oil.station = "0.790", "1.255"
    report.r10_aux_power.plant_pct = "10.67"
    assert validate(report, today=TODAY).ok
    # ...but not two.
    report.r04_gen.station = "7.18"
    assert [c.id for c in validate(report, today=TODAY).errors][0] == "gen_total"
    # Whole cylinders and whole m3 add up exactly.
    for path, value in (("r14_h2.station", "15"), ("r09_dm_water.station", "368"), ("r07_coal.station", "5667.01")):
        report = load_report(PAGE_1)
        set_cell(report, path, value)
        assert not validate(report, today=TODAY).ok, path


def test_unreadable_required_cell_blocks_and_is_named():
    report = load_report(PAGE_1)
    report.r07_coal.unit2 = ""
    result = validate(report, today=TODAY)
    assert not result.ok
    assert result.entry["u2Coal"] is None
    assert any("r07_coal.unit2" in c.cells and c.id.startswith("read_") for c in result.errors)


def test_unclear_cells_warn_but_do_not_block():
    report = load_report(PAGE_1)
    report.unclear_cells = ["r07_coal.unit2"]
    result = validate(report, today=TODAY)
    assert result.ok
    warn = [c for c in result.checks if c.id == "unclear"]
    assert len(warn) == 1 and warn[0].severity == "warn" and warn[0].cells == ["r07_coal.unit2"]


# --- dates -------------------------------------------------------------------------------

def test_future_dated_page_is_blocked():
    report = load_report(PAGE_1)
    report.report_date = "14/11/26"  # two days after TODAY
    result = validate(report, today=TODAY)
    assert not result.ok
    assert [c.id for c in result.errors] == ["date"]
    # Tomorrow's date is tolerated (the page may be read just after midnight elsewhere).
    report.report_date = "13/11/26"
    assert validate(report, today=TODAY).ok


def test_old_page_only_warns():
    report = load_report(PAGE_1)
    result = validate(report, today=date(2028, 1, 1))
    assert result.ok
    assert [c.severity for c in result.checks if c.id == "date"] == ["warn"]


@pytest.mark.parametrize("printed", ["", "smudged", "4/11", "31/11/26"])
def test_unreadable_date_blocks(printed):
    report = load_report(PAGE_1)
    report.report_date = printed
    result = validate(report, today=TODAY)
    assert not result.ok
    assert result.report_date is None and result.data_date is None
    assert any(c.id == "date" and c.cells == ["report_date"] for c in result.errors)
    # The figures are still read, so a reviewer only has to supply the date.
    assert result.entry["u1Gen"] == 3.48


def test_data_date_crosses_month_and_year():
    report = load_report(PAGE_1)
    report.report_date = "1/1/27"
    result = validate(report)
    assert result.data_date == date(2026, 12, 31)


@pytest.mark.parametrize("text, expected", [
    ("4/11/26", date(2026, 11, 4)),
    ("04.11.2026", date(2026, 11, 4)),
    ("4-11-2026", date(2026, 11, 4)),
    (" 04 / 11 / 26 ", date(2026, 11, 4)),
    ("Date: 11/11/26", date(2026, 11, 11)),
    ("29/02/28", date(2028, 2, 29)),
    ("", None),
    (None, None),
    ("garbage", None),
    ("4/11", None),
    ("31/11/26", None),   # no 31 November
    ("29/02/27", None),   # 2027 is not a leap year
    ("4/13/26", None),    # day/month order: there is no month 13
    ("00/11/26", None),
])
def test_parse_report_date(text, expected):
    assert parse_report_date(text) == expected


# --- number and duration cells -------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("3.48", 3.48),
    (" 2656.00 ", 2656.0),
    ("0.000", 0.0),
    ("1,234.50", 1234.5),
    ("12,246.51", 12246.51),
    ("10.69%", 10.69),
    ("-0.5", -0.5),
    ("Nil", 0.0),
    ("NIL", 0.0),
    ("nill", 0.0),
    ("", None),
    ("   ", None),
    (None, None),
    ("-", None),
    ("--", None),
    ("----", None),
    ("NA", None),
    ("n/a", None),
    ("abc", None),
    ("1 (03)", None),
    ("3.4.8", None),
    ("nan", None),
    ("inf", None),
])
def test_num(text, expected):
    assert num(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("0:00:00", 0.0),
    ("0:35:00", 35 / 60),
    ("0:35", 35 / 60),
    ("18:56:00", 18 + 56 / 60),
    ("24:00:00", 24.0),
    ("120:35", 120 + 35 / 60),
    ("1:00:30", 1 + 30 / 3600),
    (" 2:15 ", 2.25),
    ("Nil", 0.0),
    ("----", None),
    ("", None),
    (None, None),
    ("garbage", None),
    ("1.5", None),
    ("1:2:3:4", None),
    ("-1:00", None),
    ("1:xx", None),
    ("0:75:00", None),   # 75 minutes is a misread, not 1 h 15 min
    ("0:35:60", None),
])
def test_hours(text, expected):
    assert hours(text) == (pytest.approx(expected, abs=1e-12) if expected is not None else None)


def test_hours_matches_workbook_import_exactly():
    """A duration read from a page and from the workbook must be the same float,
    otherwise re-uploading a page reports a phantom change against imported data."""
    from datetime import time

    import workbook_import

    assert hours("0:47:00") == workbook_import._hours(time(0, 47))
    assert hours("18:56:00") == workbook_import._hours(time(18, 56))


# --- comparisons with the database ------------------------------------------------------------

# The workbook's DAILY DATA rows for 1 and 2 Nov 2026 (test_month_constants_match_workbook
# confirms them when the workbook is present).
NOV_1 = {"date": "2026-11-01", "u1Gen": 3.48, "u2Gen": 3.45, "u1Coal": 2600.0, "u2Coal": 2899.4,
         "u1Oil": 0.0, "u2Oil": 10.0, "u1Bd": 0.053, "u2Bd": 0.089, "apc": 0.8152, "coalReceipt": 3599.7,
         "oilReceipt": 0.0, "u1Dm": 111.0, "u2Dm": 1027.0}
NOV_2 = {"date": "2026-11-02", "u1Gen": 3.56, "u2Gen": 3.72, "u1Coal": 2618.0, "u2Coal": 2997.6,
         "u1Oil": 0.0, "u2Oil": 0.0, "u1Bd": 0.0, "u2Bd": 0.0, "apc": 0.7859, "coalReceipt": 3678.6,
         "oilReceipt": 0.0, "u1Dm": 112.0, "u2Dm": 245.0}
PROGRESSIVE = {"prog_gen_u1", "prog_gen_u2", "prog_coal_u1", "prog_coal_u2", "prog_oil", "prog_dm",
               "prog_apc", "prog_bd", "prog_receipt"}


def _page_1():
    report = load_report(PAGE_1)
    result = validate(report, today=TODAY)
    return report, result.entry, result.data_date


@requires_workbook
def test_month_constants_match_workbook(book):
    rows = {e["date"]: e for e in book["entries"]}
    for const in (NOV_1, NOV_2):
        assert {k: rows[const["date"]][k] for k in const} == const


def test_progressive_totals_checked_when_month_is_complete():
    report, entry, day = _page_1()
    checks, missing = cross_checks(report, entry, day, {"2026-11-01": NOV_1, "2026-11-02": NOV_2})
    assert missing == []
    assert {c.id for c in checks} == PROGRESSIVE
    assert all(c.ok and c.severity == "warn" for c in checks), [c.detail for c in checks if not c.ok]


def test_progressive_totals_skipped_while_a_day_is_missing():
    report, entry, day = _page_1()
    checks, missing = cross_checks(report, entry, day, {"2026-11-02": NOV_2})
    assert missing == ["2026-11-01"]
    assert not {c.id for c in checks} & PROGRESSIVE
    # A day that exists but has no generation counts as missing too.
    checks, missing = cross_checks(report, entry, day, {"2026-11-01": {"date": "2026-11-01", "gcv": 3500.0},
                                                         "2026-11-02": NOV_2})
    assert missing == ["2026-11-01"]
    assert not {c.id for c in checks} & PROGRESSIVE


def test_missing_days_listed_for_second_page():
    report = load_report(PAGE_2)
    result = validate(report, today=TODAY)
    month = {"2026-11-01": NOV_1, "2026-11-02": NOV_2, "2026-11-03": {**NOV_2, "date": "2026-11-03"}}
    checks, missing = cross_checks(report, result.entry, result.data_date, month)
    assert missing == ["2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07", "2026-11-08", "2026-11-09"]
    assert not {c.id for c in checks} & PROGRESSIVE


def test_progressive_total_skips_a_field_an_earlier_day_lacks():
    report, entry, day = _page_1()
    checks, _ = cross_checks(report, entry, day, {"2026-11-01": {**NOV_1, "u1Coal": None}, "2026-11-02": NOV_2})
    assert {c.id for c in checks} == PROGRESSIVE - {"prog_coal_u1"}


def test_progressive_total_mismatch_is_a_warning():
    report, entry, day = _page_1()
    checks, _ = cross_checks(report, entry, day, {"2026-11-01": NOV_1, "2026-11-02": {**NOV_2, "u1Gen": 3.66}})
    failed = [c for c in checks if not c.ok]
    assert [c.id for c in failed] == ["prog_gen_u1"]
    assert failed[0].severity == "warn"
    assert "10.62" in failed[0].detail and "10.52" in failed[0].detail


def test_first_of_month_has_no_earlier_days():
    report = load_report(PAGE_1)
    report.report_date = "2/11/26"
    result = validate(report, today=TODAY)
    checks, missing = cross_checks(report, result.entry, result.data_date, {})
    assert result.data_date == date(2026, 11, 1)
    assert missing == []
    # The month-to-date figure is just the day's own figure; this page's are not.
    assert {c.id for c in checks} == PROGRESSIVE


def test_stock_rolls_forward_from_previous_day():
    report, entry, day = _page_1()
    # Previous closing + receipt - consumption = 12246.51 and 349.286 as printed.
    prev = {**NOV_2, "coalStock": 12246.51 - 3617.7 + 5667.0, "oilStock": 349.286 - 0.0 + 9.0}
    checks, _ = cross_checks(report, entry, day, {"2026-11-01": NOV_1, "2026-11-02": prev})
    stock = {c.id: c for c in checks if c.id in ("coal_stock", "oil_stock")}
    assert set(stock) == {"coal_stock", "oil_stock"}
    assert all(c.ok and c.severity == "warn" for c in stock.values())

    prev["coalStock"] += 50
    checks, _ = cross_checks(report, entry, day, {"2026-11-01": NOV_1, "2026-11-02": prev})
    stock = {c.id: c for c in checks if c.id in ("coal_stock", "oil_stock")}
    assert not stock["coal_stock"].ok and stock["oil_stock"].ok


def test_stock_check_needs_previous_stock():
    report, entry, day = _page_1()
    checks, _ = cross_checks(report, entry, day, {"2026-11-01": NOV_1, "2026-11-02": NOV_2})
    assert not {c.id for c in checks} & {"coal_stock", "oil_stock"}


def test_stock_check_on_the_first_uses_previous_month():
    report = load_report(PAGE_1)
    report.report_date = "2/11/26"
    result = validate(report, today=TODAY)
    prev = {"date": "2026-10-31", "u1Gen": 3.5, "coalStock": 12246.51 - 3617.7 + 5667.0, "oilStock": 358.286}
    checks, _ = cross_checks(report, result.entry, result.data_date, {"2026-10-31": prev})
    stock = {c.id: c.ok for c in checks if c.id in ("coal_stock", "oil_stock")}
    assert stock == {"coal_stock": True, "oil_stock": True}
