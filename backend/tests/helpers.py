"""Helpers shared by the test modules (fixtures live in conftest.py)."""

from __future__ import annotations

import io
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from report_schema import DailySystemReport

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
# The plant workbook is not committed; tests that need it skip without it.
# TTPS_WORKBOOK points them at a copy elsewhere.
WORKBOOK = Path(os.getenv("TTPS_WORKBOOK") or ROOT / "TTPS DAILY GEN DATA 2026-27.xlsx")

PAGE_1 = "report_2026-11-04.json"  # printed 4/11/26, data for 3 Nov 2026
PAGE_2 = "report_2026-11-11.json"  # printed 11/11/26, data for 10 Nov 2026

SKIP_REASON = f"no plant workbook at {WORKBOOK} (it is not committed to git)"
requires_workbook = pytest.mark.skipif(not WORKBOOK.exists(), reason=SKIP_REASON)


def load_report(name: str) -> DailySystemReport:
    return DailySystemReport.model_validate(json.loads((FIXTURES / name).read_text()))


def get_cell(report: DailySystemReport, path: str):
    obj = report
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj


def set_cell(report: DailySystemReport, path: str, value: str) -> None:
    *parents, last = path.split(".")
    obj = report
    for part in parents:
        obj = getattr(obj, part)
    setattr(obj, last, value)


def build_workbook(days: dict[str, dict], fy: int = 2026, targets: dict | None = None,
                   coal_opening: float | None = None, oil_opening: float | None = None,
                   coal_rebase: tuple[str, float] | None = None) -> bytes:
    """A small workbook laid out like the plant's 'TTPS DAILY GEN DATA'.

    `days` maps ISO date -> entry fields (named as in the database). Durations
    (u1Fo...) are given in hours and written as Excel durations. `coal_rebase`
    is (closing date, stock): the next day's COAL OIL formula starts from that
    number instead of the previous row, the way the plant re-based in June 2026.
    """
    import openpyxl

    import workbook_import as wi

    start = date(fy, 4, 1)
    wb = openpyxl.Workbook()
    daily = wb.active
    daily.title = "DAILY DATA"
    daily["A2"] = f"{fy}-{(fy + 1) % 100:02d}"
    daily["A3"] = datetime(fy, 4, 1)
    columns = {field: col for col, field in {**wi.NUMBER_COLUMNS, **wi.DURATION_COLUMNS, **wi.TEXT_COLUMNS}.items()}
    for iso, fields in days.items():
        row = wi.FIRST_ROW + (date.fromisoformat(iso) - start).days
        for field, value in fields.items():
            cell = daily[f"{columns[field]}{row}"]
            if field in wi.DURATION_COLUMNS.values():
                cell.value = timedelta(hours=value)
                cell.number_format = "[h]:mm"
            else:
                cell.value = value

    target = wb.create_sheet("TARGET")
    for month, t in (targets or {}).items():
        row = wi.FIRST_ROW + (date.fromisoformat(f"{month}-01") - start).days
        target[f"B{row}"], target[f"C{row}"] = t["u1"], t["u2"]

    coal_oil = wb.create_sheet("COAL OIL")
    if coal_opening is not None:
        coal_oil["BD3"] = coal_opening
    if oil_opening is not None:
        coal_oil["BE3"] = oil_opening
    for offset in range(1, (date(fy + 1, 4, 1) - start).days):
        r = wi.FIRST_ROW + offset
        coal_oil[f"BD{r}"] = f"=(BD{r - 1}+'DAILY DATA'!P{r})-('DAILY DATA'!G{r})"
        coal_oil[f"BE{r}"] = f"=BE{r - 1}+('DAILY DATA'!Q{r})-('DAILY DATA'!J{r})"
    if coal_rebase:
        r = wi.FIRST_ROW + (date.fromisoformat(coal_rebase[0]) - start).days + 1
        coal_oil[f"BD{r}"] = f"=({coal_rebase[1]}+'DAILY DATA'!P{r})-('DAILY DATA'!G{r})"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
