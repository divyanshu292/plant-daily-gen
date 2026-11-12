"""Read history out of the plant's 'TTPS DAILY GEN DATA' workbook.

Only the DAILY DATA sheet holds typed-in figures; every other sheet is derived
from it. TARGET supplies the monthly generation targets and COAL OIL the
opening stock balances.
"""

from __future__ import annotations

import io
import re
from datetime import date, datetime, time, timedelta

import openpyxl
from openpyxl.utils.datetime import to_excel

FIRST_ROW = 3  # 1 April of the fiscal year

# DAILY DATA column -> entry field
NUMBER_COLUMNS = {
    "B": "u1Gen", "C": "u2Gen",
    "E": "u1Coal", "F": "u2Coal",
    "H": "u1Oil", "I": "u2Oil",
    "K": "u1Bd", "L": "u2Bd",
    "N": "apc", "O": "gcv",
    "P": "coalReceipt", "Q": "oilReceipt",
    "T": "u1Dm", "U": "u2Dm",
    "W": "u1Trip", "X": "u2Trip",
    "Z": "u1Btl", "AA": "u2Btl",
}
DURATION_COLUMNS = {"AC": "u1Fo", "AD": "u2Fo", "AF": "u1Po", "AG": "u2Po"}
TEXT_COLUMNS = {"AJ": "u1TripReason", "AL": "u2TripReason"}
# On a day that has data, a blank in these means zero, not unknown.
ZERO_WHEN_BLANK = ("u1Trip", "u2Trip", "u1Btl", "u2Btl", "u1Fo", "u2Fo", "u1Po", "u2Po")



class WorkbookError(Exception):
    pass


def _hours(value) -> float | None:
    """Excel stores durations as fractions of a day; openpyxl hands them back
    as time, timedelta or (for 24 h and more) a 1900 datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, (datetime, time, timedelta)):
        days = to_excel(value)  # handles the 1900 leap-year quirk for 60+ days
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        days = float(value)
    else:
        return None
    # Durations are typed as h:mm(:ss). Rounding to whole seconds removes the
    # float noise of a day fraction without the error a fixed number of decimal
    # hours would add, and matches validate.hours() for the same duration.
    return round(days * 86400) / 3600


def _number(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _fy_start(sheet) -> date:
    first = sheet["A3"].value
    if isinstance(first, datetime):
        return first.date()
    label = str(sheet["A2"].value or "")
    m = re.search(r"(20\d{2})\s*-\s*\d{2}", label)
    if m:
        return date(int(m.group(1)), 4, 1)
    raise WorkbookError("Could not tell which year this workbook covers (DAILY DATA!A2/A3).")


def read_workbook(source: bytes | str) -> dict:
    """-> {"fy": 2026, "entries": [{"date": "2026-04-01", ...}], "config": {...}}"""
    stream = io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else source
    try:
        values = openpyxl.load_workbook(stream, data_only=True)
    except Exception as exc:  # openpyxl raises several unrelated types for a bad file
        raise WorkbookError("That file is not a readable .xlsx workbook.") from exc
    if "DAILY DATA" not in values.sheetnames:
        raise WorkbookError("The workbook has no 'DAILY DATA' sheet.")

    sheet = values["DAILY DATA"]
    start = _fy_start(sheet)
    if (start.month, start.day) != (4, 1):
        raise WorkbookError(f"DAILY DATA should start on 1 April, found {start:%d-%b-%Y}.")
    fy = start.year
    days_in_fy = (date(fy + 1, 4, 1) - start).days

    entries = []
    for offset in range(days_in_fy):
        r = FIRST_ROW + offset
        row = {field: _number(sheet[f"{col}{r}"].value) for col, field in NUMBER_COLUMNS.items()}
        if row["u1Gen"] is None and row["u2Gen"] is None:
            continue  # day not filled in yet
        row.update({field: _hours(sheet[f"{col}{r}"].value) for col, field in DURATION_COLUMNS.items()})
        for col, field in TEXT_COLUMNS.items():
            text = sheet[f"{col}{r}"].value
            row[field] = text.strip() if isinstance(text, str) and text.strip() else None
        for field in ZERO_WHEN_BLANK:
            if row[field] is None:
                row[field] = 0.0
        entries.append({"date": (start + timedelta(days=offset)).isoformat(), **row})

    config: dict = {}
    if "TARGET" in values.sheetnames:
        target = values["TARGET"]
        monthly = {}
        for offset in range(days_in_fy):
            d = start + timedelta(days=offset)
            if d.day != 1:
                continue
            u1, u2 = _number(target[f"B{FIRST_ROW + offset}"].value), _number(target[f"C{FIRST_ROW + offset}"].value)
            if u1 is not None and u2 is not None:
                monthly[f"{d.year}-{d.month:02d}"] = {"u1": u1, "u2": u2}
        if monthly:
            config["monthlyTargets"] = monthly

    if "COAL OIL" in values.sheetnames:
        # Stock columns start from a typed balance; a re-based balance shows up
        # as a formula that begins with a number instead of the previous row.
        if isinstance(source, (bytes, bytearray)):
            stream = io.BytesIO(source)
        formulas = openpyxl.load_workbook(stream)["COAL OIL"]
        for col, key in (("BD", "coalStockAnchors"), ("BE", "oilStockAnchors")):
            anchors = []
            opening = _number(formulas[f"{col}{FIRST_ROW}"].value)
            if opening is not None:
                anchors.append({"date": start.isoformat(), "stock": opening})
            for offset in range(1, days_in_fy):
                cell = formulas[f"{col}{FIRST_ROW + offset}"].value
                m = re.match(r"^=\(?\s*(\d+(?:\.\d+)?)\s*\+", cell) if isinstance(cell, str) else None
                if m:
                    anchors.append({"date": (start + timedelta(days=offset - 1)).isoformat(),
                                    "stock": float(m.group(1))})
            if anchors:
                config[key] = anchors

    return {"fy": fy, "entries": entries, "config": config}
