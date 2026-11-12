"""workbook_import.py on a generated workbook, plus the real one when present."""

from __future__ import annotations

import io
from datetime import datetime, time, timedelta

import openpyxl
import pytest

import workbook_import
from helpers import WORKBOOK, build_workbook, requires_workbook
from workbook_import import WorkbookError, read_workbook


@pytest.mark.parametrize("value, expected", [
    (None, None),
    ("", None),
    ("abc", None),
    (True, None),
    (time(0, 0), 0.0),
    (time(0, 47), 47 / 60),
    (time(18, 56, 30), 18 + 56 / 60 + 30 / 3600),
    (timedelta(hours=24), 24.0),
    (timedelta(days=2, minutes=35), 48 + 35 / 60),
    # 24 h and more come back as 1900 datetimes. Serial 1 = 1900-01-01.
    (datetime(1900, 1, 1, 0, 0), 24.0),
    (datetime(1900, 1, 2, 5, 26), 48 + 5 + 26 / 60),
    # Past serial 60 Excel's phantom 29 Feb 1900 counts: 1900-03-01 is serial 61.
    # Subtracting an epoch by hand gives 60 days here.
    (datetime(1900, 3, 1, 0, 0), 61 * 24.0),
    (0.5, 12.0),
    (1, 24.0),
])
def test_hours(value, expected):
    result = workbook_import._hours(value)
    assert result == (pytest.approx(expected, abs=1e-9) if expected is not None else None)


def _sample() -> bytes:
    return build_workbook(
        {
            "2026-04-01": {"u1Gen": 3.65, "u2Gen": 4.18, "u1Coal": 2756, "u2Coal": 3120.8, "apc": 0.7223,
                           "gcv": 3417, "coalReceipt": 6712.4, "u1Dm": 156, "u2Dm": 234},
            "2026-04-02": {"u1Gen": 0, "u2Gen": 4.26, "u1Fo": 24, "u2Fo": 0.5, "u1Trip": 1,
                           "u1TripReason": "  Boiler tube leakage  ", "u2TripReason": "   "},
            "2026-04-04": {"u2Gen": 4.0},
            "2026-04-05": {"gcv": 3500},  # no generation: not a filled day
        },
        targets={"2026-04": {"u1": 100, "u2": 115.2}, "2026-05": {"u1": 105, "u2": 111.6}},
        coal_opening=518696.75, oil_opening=528.286, coal_rebase=("2026-06-11", 297377.915),
    )


def test_reads_filled_days_only():
    book = read_workbook(_sample())
    assert book["fy"] == 2026
    assert [e["date"] for e in book["entries"]] == ["2026-04-01", "2026-04-02", "2026-04-04"]
    first, second, fourth = book["entries"]
    assert first["u1Gen"] == 3.65 and first["u2Coal"] == 3120.8 and first["gcv"] == 3417.0
    assert first["u1Oil"] is None  # blank stays unknown...
    assert first["u1Trip"] == 0.0 and first["u1Fo"] == 0.0  # ...except counts and outages
    assert second["u1Gen"] == 0.0 and second["u1Fo"] == 24.0 and second["u2Fo"] == 0.5
    assert second["u1Trip"] == 1.0
    assert second["u1TripReason"] == "Boiler tube leakage" and second["u2TripReason"] is None
    assert fourth["u1Gen"] is None and fourth["u2Gen"] == 4.0


def test_reads_targets_and_stock_anchors():
    config = read_workbook(_sample())["config"]
    assert config["monthlyTargets"] == {"2026-04": {"u1": 100.0, "u2": 115.2}, "2026-05": {"u1": 105.0, "u2": 111.6}}
    # The re-based figure sits in 12 June's formula as the previous day's closing stock.
    assert config["coalStockAnchors"] == [{"date": "2026-04-01", "stock": 518696.75},
                                         {"date": "2026-06-11", "stock": 297377.915}]
    assert config["oilStockAnchors"] == [{"date": "2026-04-01", "stock": 528.286}]


def test_bytes_and_path_agree(tmp_path):
    data = _sample()
    path = tmp_path / "book.xlsx"
    path.write_bytes(data)
    assert read_workbook(str(path)) == read_workbook(data)


def test_rejects_a_file_that_is_not_a_workbook():
    with pytest.raises(WorkbookError, match="not a readable .xlsx"):
        read_workbook(b"this is not a spreadsheet")


def test_rejects_a_workbook_without_daily_data():
    wb = openpyxl.Workbook()
    wb.active.title = "Sheet1"
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(WorkbookError, match="DAILY DATA"):
        read_workbook(buf.getvalue())


def test_rejects_a_year_that_does_not_start_on_1_april():
    wb = openpyxl.load_workbook(io.BytesIO(_sample()))
    wb["DAILY DATA"]["A3"] = datetime(2026, 1, 1)
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(WorkbookError, match="1 April"):
        read_workbook(buf.getvalue())


def test_year_from_label_when_first_date_is_missing():
    wb = openpyxl.load_workbook(io.BytesIO(_sample()))
    wb["DAILY DATA"]["A3"] = None
    buf = io.BytesIO()
    wb.save(buf)
    assert read_workbook(buf.getvalue())["fy"] == 2026


@requires_workbook
def test_real_workbook(book):
    assert book["fy"] == 2026
    assert len(book["entries"]) == 218
    assert (book["entries"][0]["date"], book["entries"][-1]["date"]) == ("2026-04-01", "2026-11-04")
    assert set(book["config"]) == {"monthlyTargets", "coalStockAnchors", "oilStockAnchors"}
    assert read_workbook(WORKBOOK.read_bytes()) == book
