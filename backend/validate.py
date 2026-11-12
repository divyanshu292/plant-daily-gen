"""Turn a transcribed Daily System Report into a database entry, and prove it.

The printed form is heavily redundant: every unit pair has a station total, and
rows 5, 6, 12 and 13 are ratios of other rows. Recomputing those from the
transcribed cells catches a misread digit without anyone looking at the page.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from report_schema import DailySystemReport

UNIT_MW = 210
UNIT_MU_PER_DAY = UNIT_MW * 24 / 1000  # 5.04 MU at full load for 24 h
STATION_MU_PER_DAY = 2 * UNIT_MU_PER_DAY
# The form expresses DM make-up as a share of boiler steam flow at full load:
# 690 t/h for 24 h (1 m3 of water = 1 t).
DM_BASE_M3_PER_DAY = 690 * 24

_BLANK = {"", "-", "--", "---", "----", "-----", "na", "n/a"}
_ZERO_WORDS = {"nil", "nill", "zero"}


def num(text: str | None) -> float | None:
    """Parse a printed number. Blank or dashed cells are None."""
    if text is None:
        return None
    s = text.strip().replace(",", "").replace("%", "").replace(" ", "")
    low = s.lower()
    if low in _BLANK:
        return None
    if low in _ZERO_WORDS:
        return 0.0
    try:
        value = float(s)
    except ValueError:
        return None
    # float() also accepts 'nan' and 'inf'; neither is a printed figure, and a
    # NaN that reached the database would break every JSON response showing it.
    return value if math.isfinite(value) else None


def hours(text: str | None) -> float | None:
    """Parse a printed duration ('0:35:00' or '0:35') into hours."""
    if text is None:
        return None
    s = text.strip()
    if s.lower() in _BLANK:
        return None
    if s.lower() in _ZERO_WORDS:
        return 0.0
    parts = s.split(":")
    if not 2 <= len(parts) <= 3 or not all(p.strip().isdigit() for p in parts):
        return None
    h, m = int(parts[0]), int(parts[1])
    sec = int(parts[2]) if len(parts) == 3 else 0
    if m >= 60 or sec >= 60:
        return None  # '0:85:00' is a misread, not 1 h 25 min
    # Whole seconds / 3600, so the same duration read from the page and from the
    # workbook (workbook_import._hours) is the same float.
    return (h * 3600 + m * 60 + sec) / 3600


def parse_report_date(text: str | None) -> date | None:
    """Dates on the form are day/month/year, e.g. '4/11/26' or '04.11.2026'."""
    if not text:
        return None
    m = re.search(r"(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{2,4})", text)
    if not m:
        return None
    d, mo, y = (int(g) for g in m.groups())
    if y < 100:
        y += 2000
    try:
        return date(y, mo, d)
    except ValueError:
        return None


@dataclass
class Check:
    id: str
    label: str
    ok: bool
    severity: str  # "error" blocks auto-save, "warn" is shown but does not block
    detail: str
    cells: list[str] = field(default_factory=list)


@dataclass
class Validation:
    report_date: date | None
    data_date: date | None
    entry: dict
    checks: list[Check]

    @property
    def errors(self) -> list[Check]:
        return [c for c in self.checks if not c.ok and c.severity == "error"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def recheck_hints(self) -> list[str]:
        return [f"{c.label}: {c.detail} (cells: {', '.join(c.cells)})" for c in self.errors]

    def checks_json(self) -> list[dict]:
        return [asdict(c) for c in self.checks]


def _fmt(v: float | None, dp: int) -> str:
    return "blank" if v is None else f"{v:.{dp}f}"


class _Checker:
    def __init__(self) -> None:
        self.checks: list[Check] = []

    def add(self, id: str, label: str, ok: bool, detail: str, cells: list[str], severity: str = "error") -> None:
        self.checks.append(Check(id, label, ok, severity, detail, cells))

    def required(self, label: str, cells: dict[str, float | None]) -> bool:
        missing = [path for path, v in cells.items() if v is None]
        if missing:
            self.add(
                f"read_{missing[0].split('.')[0]}",
                f"{label} could not be read",
                False,
                "No number found in " + ", ".join(missing),
                missing,
            )
        return not missing

    def total(self, id: str, label: str, row: str, parts: tuple[str, str], dp: int,
              a: float | None, b: float | None, tot: float | None, severity: str = "error",
              rounded: bool = False) -> None:
        """Station (or total) cell must equal the sum of its two parts.

        `rounded` rows are recorded to more decimals than the page prints, so the
        printed total may be one unit off the sum of the printed parts. Every other
        row is recorded at the printed precision (the plant workbook confirms it),
        so its total is an exact sum and a one-unit difference is a misread.
        """
        if a is None or b is None or tot is None:
            return
        tol = (1.1 if rounded else 0.5) * 10 ** -dp
        self.add(
            id, label, abs(a + b - tot) <= tol,
            f"{_fmt(a, dp)} + {_fmt(b, dp)} = {_fmt(a + b, dp)}, page shows {_fmt(tot, dp)}",
            [f"{row}.{parts[0]}", f"{row}.{parts[1]}", f"{row}.{'total' if 'road' in parts else 'station'}"],
            severity,
        )

    def ratio(self, id: str, label: str, expected: float | None, printed: float | None, dp: int,
              tol: float, cells: list[str], severity: str = "error") -> None:
        """A printed ratio must match the one recomputed from other cells."""
        if expected is None or printed is None:
            return
        self.add(
            id, label, abs(expected - printed) <= tol,
            f"works out to {_fmt(expected, dp)}, page shows {_fmt(printed, dp)}",
            cells, severity,
        )


def _div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def validate(report: DailySystemReport, today: date | None = None) -> Validation:
    c = _Checker()

    # --- date ---------------------------------------------------------------
    report_date = parse_report_date(report.report_date)
    data_date = report_date - timedelta(days=1) if report_date else None
    if report_date is None:
        c.add("date", "Report date could not be read", False,
              f"Printed date reads {report.report_date!r}", ["report_date"])
    elif today is not None:
        if report_date > today + timedelta(days=1):
            c.add("date", "Report date is in the future", False,
                  f"Page is dated {report_date:%d-%b-%Y}, today is {today:%d-%b-%Y}", ["report_date"])
        elif (today - report_date).days > 400:
            c.add("date", "Report date is more than a year old", False,
                  f"Page is dated {report_date:%d-%b-%Y}", ["report_date"], "warn")

    # --- parse the cells that feed the database --------------------------------
    gen = (num(report.r04_gen.unit1), num(report.r04_gen.unit2), num(report.r04_gen.station))
    plf = (num(report.r05_plf.unit1), num(report.r05_plf.unit2), num(report.r05_plf.station))
    paf = (num(report.r06_paf.unit1), num(report.r06_paf.unit2), num(report.r06_paf.station))
    coal = (num(report.r07_coal.unit1), num(report.r07_coal.unit2), num(report.r07_coal.station))
    oil = (num(report.r08_oil.unit1), num(report.r08_oil.unit2), num(report.r08_oil.station))
    dm = (num(report.r09_dm_water.unit1), num(report.r09_dm_water.unit2), num(report.r09_dm_water.station))
    dm_pct = (num(report.r09_dm_water.unit1_pct), num(report.r09_dm_water.unit2_pct))
    apc_plant = num(report.r10_aux_power.plant)
    apc_pct = num(report.r10_aux_power.plant_pct)
    apc_sub = num(report.r10_aux_power.substation)
    apc_stn = num(report.r10_aux_power.station)
    out = (hours(report.r11_outage.unit1), hours(report.r11_outage.unit2), hours(report.r11_outage.station))
    sp_coal = (num(report.r12_sp_coal.unit1), num(report.r12_sp_coal.unit2), num(report.r12_sp_coal.station))
    sp_oil = (num(report.r13_sp_oil.unit1), num(report.r13_sp_oil.unit2), num(report.r13_sp_oil.station))
    h2 = (num(report.r14_h2.unit1), num(report.r14_h2.unit2), num(report.r14_h2.station))
    bd = (num(report.r15_backing_down.unit1), num(report.r15_backing_down.unit2),
          num(report.r15_backing_down.station))
    rcpt_road = num(report.r28_coal_transported.road)
    rcpt_rail = num(report.r28_coal_transported.rail)
    rcpt_total = num(report.r28_coal_transported.total)
    oil_rcpt = num(report.r31_oil_transported)

    # --- every value we store must have been read --------------------------------
    c.required("Generation (row 4)", {"r04_gen.unit1": gen[0], "r04_gen.unit2": gen[1]})
    c.required("Coal consumption (row 7)", {"r07_coal.unit1": coal[0], "r07_coal.unit2": coal[1]})
    c.required("Oil consumption (row 8)", {"r08_oil.unit1": oil[0], "r08_oil.unit2": oil[1]})
    c.required("DM water (row 9)", {"r09_dm_water.unit1": dm[0], "r09_dm_water.unit2": dm[1]})
    c.required("Auxiliary power (row 10)", {"r10_aux_power.station": apc_stn})
    c.required("Period of outage (row 11)", {"r11_outage.unit1": out[0], "r11_outage.unit2": out[1]})
    c.required("H2 consumption (row 14)", {"r14_h2.unit1": h2[0], "r14_h2.unit2": h2[1]})
    c.required("Grid backing down (row 15)",
               {"r15_backing_down.unit1": bd[0], "r15_backing_down.unit2": bd[1]})
    c.required("Coal transported (row 28)", {"r28_coal_transported.total": rcpt_total})
    c.required("Oil transported (row 31)", {"r31_oil_transported": oil_rcpt})

    # --- station totals ---------------------------------------------------------
    u = ("unit1", "unit2")
    # Generation is metered to a few more decimals than the page prints; the other
    # rows are whole m3 / cylinders, or tonnes and MU at most at the printed decimals.
    c.total("gen_total", "Generation: Unit 1 + Unit 2 = Station", "r04_gen", u, 2, *gen, rounded=True)
    c.total("coal_total", "Coal: Unit 1 + Unit 2 = Station", "r07_coal", u, 2, *coal)
    c.total("oil_total", "Oil: Unit 1 + Unit 2 = Station", "r08_oil", u, 2, *oil)
    c.total("dm_total", "DM water: Unit 1 + Unit 2 = Station", "r09_dm_water", u, 0, *dm)
    c.total("h2_total", "H2 cylinders: Unit 1 + Unit 2 = Station", "r14_h2", u, 0, *h2)
    c.total("bd_total", "Backing down: Unit 1 + Unit 2 = Station", "r15_backing_down", u, 3, *bd)
    c.total("receipt_total", "Coal receipt: Road + Rail = Total", "r28_coal_transported",
            ("road", "rail"), 2, rcpt_road, rcpt_rail, rcpt_total)
    if apc_plant is not None and apc_sub is not None and apc_stn is not None:
        # Station is plant (5 decimals) + sub-station (a flat 0.028) rounded to 4
        # decimals, so it can differ from the sum by half a unit of the 4th decimal
        # plus the plant figure's own rounding, and no more.
        c.add("apc_total", "Aux. power: Plant + Sub-Station = Station",
              abs(apc_plant + apc_sub - apc_stn) <= 0.5e-4 + 0.5e-5 + 1e-9,
              f"{apc_plant:.5f} + {apc_sub:.3f} = {apc_plant + apc_sub:.4f}, page shows {apc_stn:.4f}",
              ["r10_aux_power.plant", "r10_aux_power.substation", "r10_aux_power.station"])
    if None not in out:
        c.add("outage_total", "Outage: Unit 1 + Unit 2 = Station",
              abs(out[0] + out[1] - out[2]) <= 0.02,
              f"{out[0]:.2f} h + {out[1]:.2f} h, page shows {out[2]:.2f} h",
              ["r11_outage.unit1", "r11_outage.unit2", "r11_outage.station"], "warn")

    # --- ratios printed on the form, recomputed -------------------------------
    caps = (UNIT_MU_PER_DAY, UNIT_MU_PER_DAY, STATION_MU_PER_DAY)
    names = ("Unit 1", "Unit 2", "Station")
    keys = ("unit1", "unit2", "station")
    for i in range(3):
        k, n = keys[i], names[i]
        c.ratio(f"plf_{k}", f"PLF {n} = generation / {caps[i]:.2f} MU",
                None if gen[i] is None else gen[i] / caps[i] * 100, plf[i], 2, 0.02,
                [f"r04_gen.{k}", f"r05_plf.{k}"])
        sc = _div(coal[i], None if gen[i] is None else gen[i] * 1000)
        c.ratio(f"sp_coal_{k}", f"Sp. coal {n} = coal / generation", sc, sp_coal[i], 3, 0.0011,
                [f"r07_coal.{k}", f"r04_gen.{k}", f"r12_sp_coal.{k}"])
        c.ratio(f"sp_oil_{k}", f"Sp. oil {n} = oil / generation", _div(oil[i], gen[i]), sp_oil[i], 3, 0.0011,
                [f"r08_oil.{k}", f"r04_gen.{k}", f"r13_sp_oil.{k}"])
    for i in range(2):
        k, n = keys[i], names[i]
        c.ratio(f"paf_{k}", f"Availability {n} = (24 h - outage) / 24 h",
                None if out[i] is None else (24 - out[i]) / 24 * 100, paf[i], 2, 0.011,
                [f"r11_outage.{k}", f"r06_paf.{k}"])
        c.ratio(f"dm_pct_{k}", f"DM water % {n} = quantity / {DM_BASE_M3_PER_DAY} m3",
                None if dm[i] is None else dm[i] / DM_BASE_M3_PER_DAY * 100, dm_pct[i], 2, 0.011,
                [f"r09_dm_water.{k}", f"r09_dm_water.{k}_pct"])
    c.ratio("apc_pct", "Aux. power % = plant consumption / station generation",
            None if _div(apc_plant, gen[2]) is None else apc_plant / gen[2] * 100, apc_pct, 2, 0.02,
            ["r10_aux_power.plant", "r04_gen.station", "r10_aux_power.plant_pct"])

    # --- the database entry -----------------------------------------------------
    entry = {
        "u1Gen": gen[0], "u2Gen": gen[1],
        "u1Coal": coal[0], "u2Coal": coal[1],
        "u1Oil": oil[0], "u2Oil": oil[1],
        "u1Dm": dm[0], "u2Dm": dm[1],
        "apc": apc_stn, "apcPlant": apc_plant, "apcSub": apc_sub,
        # The form has one outage figure per unit; the workbook files it as forced outage.
        "u1Fo": out[0], "u2Fo": out[1],
        "u1H2": h2[0], "u2H2": h2[1],
        "u1Bd": bd[0], "u2Bd": bd[1],
        "coalReceipt": rcpt_total, "coalReceiptRoad": rcpt_road, "coalReceiptRail": rcpt_rail,
        "oilReceipt": oil_rcpt,
        "coalStock": num(report.r30_usable_coal_stock),
        "oilStock": num(report.r32_usable_oil_stock),
        "oilPipeline": num(report.r31_oil_in_pipeline),
        "u1Remark": report.r38_remarks_unit1.strip() or None,
        "u2Remark": report.r39_remarks_unit2.strip() or None,
    }

    for path in report.unclear_cells:
        c.add("unclear", "Cell flagged as hard to read", False, path, [path], "warn")

    return Validation(report_date=report_date, data_date=data_date, entry=entry, checks=c.checks)


# Month-to-date rows on the form, matched to the entry fields they accumulate.
# (check id, label, entry fields summed, getter for the printed value, decimals)
_PROGRESSIVE = (
    ("prog_gen_u1", "Prog. generation Unit 1", ("u1Gen",), lambda r: r.r16_prog_gen.unit1, 2),
    ("prog_gen_u2", "Prog. generation Unit 2", ("u2Gen",), lambda r: r.r16_prog_gen.unit2, 2),
    ("prog_coal_u1", "Prog. coal Unit 1", ("u1Coal",), lambda r: r.r18_prog_coal.unit1, 2),
    ("prog_coal_u2", "Prog. coal Unit 2", ("u2Coal",), lambda r: r.r18_prog_coal.unit2, 2),
    ("prog_oil", "Prog. oil Station", ("u1Oil", "u2Oil"), lambda r: r.r19_prog_oil.station, 2),
    ("prog_dm", "Prog. DM water Station", ("u1Dm", "u2Dm"), lambda r: r.r20_prog_dm_water.station, 0),
    ("prog_apc", "Prog. aux. power Station", ("apc",), lambda r: r.r21_prog_aux_power.station, 3),
    ("prog_bd", "Prog. backing down Station", ("u1Bd", "u2Bd"), lambda r: r.r26_prog_backing_down.station, 3),
    ("prog_receipt", "Prog. coal receipt", ("coalReceipt",), lambda r: r.r29_prog_coal_receipt.total, 2),
)


def cross_checks(report: DailySystemReport, entry: dict, data_date: date,
                 month_entries: dict[str, dict]) -> tuple[list[Check], list[str]]:
    """Compare the page with what the database already holds.

    `month_entries` maps ISO date -> entry for the same month, excluding the
    day being uploaded. Returns warn-level checks plus the ISO dates of earlier
    days in the month that have no generation data yet.
    """
    checks: list[Check] = []
    earlier = [date(data_date.year, data_date.month, d).isoformat() for d in range(1, data_date.day)]
    missing = [iso for iso in earlier
               if month_entries.get(iso, {}).get("u1Gen") is None
               and month_entries.get(iso, {}).get("u2Gen") is None]

    # Month-to-date totals only mean something once every earlier day is in.
    if not missing:
        for id, label, fields, getter, dp in _PROGRESSIVE:
            printed = num(getter(report))
            today_vals = [entry.get(f) for f in fields]
            if printed is None or any(v is None for v in today_vals):
                continue
            total = sum(today_vals)
            complete = True
            for iso in earlier:
                vals = [month_entries[iso].get(f) for f in fields]
                if any(v is None for v in vals):
                    complete = False
                    break
                total += sum(vals)
            if not complete:
                continue
            # APC is stored to 4 decimals but its running total is printed to 3.
            tol = 1.1 * 10 ** -dp + (0.0001 * len(earlier) if id == "prog_apc" else 0)
            checks.append(Check(
                id, f"{label} matches the days already in the database", abs(total - printed) <= tol, "warn",
                f"database adds up to {total:.{dp}f}, page shows {printed:.{dp}f}", [],
            ))

    # Stock should roll forward: yesterday + receipt - consumption.
    prev = month_entries.get((data_date - timedelta(days=1)).isoformat())
    if prev is None and data_date.day == 1:
        prev = None  # previous day is in another month; the caller may add it to month_entries
    if prev:
        coal_used = _sum(entry.get("u1Coal"), entry.get("u2Coal"))
        oil_used = _sum(entry.get("u1Oil"), entry.get("u2Oil"))
        for id, label, stock_key, receipt, used, dp in (
            ("coal_stock", "Coal stock", "coalStock", entry.get("coalReceipt"), coal_used, 2),
            ("oil_stock", "Oil stock", "oilStock", entry.get("oilReceipt"), oil_used, 3),
        ):
            before, after = prev.get(stock_key), entry.get(stock_key)
            if None in (before, after, receipt, used):
                continue
            expected = before + receipt - used
            checks.append(Check(
                id, f"{label} = previous day + receipt - consumption",
                abs(expected - after) <= 2.1 * 10 ** -dp, "warn",
                f"{before:.{dp}f} + {receipt:.{dp}f} - {used:.{dp}f} = {expected:.{dp}f}, "
                f"page shows {after:.{dp}f}", [],
            ))
    return checks, missing


def _sum(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else a + b
