"""Pasted WhatsApp messages -> a day's readings under a fixed set of keys.

Staff send the routine readings (mills, fans, ESP, turbine side, chemistry, ash,
fuel oil, DG sets...) as WhatsApp messages typed by hand, each in its own
layout. logbook_forms.py holds the fixed set: the forms and their fields. A
person pastes a day's messages; a model call files every value under its
field, and the code here does what must not be left to a model:

- the model copies every value and date as written; dates and numbers are
  parsed here, so a day/month mix-up or a "repaired" digit cannot happen;
- every value must be found, as written, on the line the model says it came
  from, or it is marked for a person to check;
- numbers left unused on a line that was read are reported, so a dropped value
  does not pass unnoticed;
- only keys of the fixed set are accepted. Anything else is kept as an "extra",
  never dropped and never forced into a field.

compare() then sets a day's values beside another day's. main.py holds the
routes and the database; nothing here touches either.
"""

from __future__ import annotations

import asyncio
import math
import re
from datetime import date, timedelta
from typing import Literal, Optional

from pydantic import BaseModel, Field

import extract
import logbook_forms as forms

# A day's messages are 3,000 to 5,000 characters. The limit leaves room for a
# few days at once while keeping the answer inside the model's output limit.
MAX_CHARS = 24_000
MAX_OUTPUT_TOKENS = 32_768
# The wait is the answer being written: about a second for every seven values,
# so a day's messages take 10 to 20 seconds and two days in one request 45.
# Messages copied together from WhatsApp each start with its stamp, which is a
# sure place to cut, so such a paste is read in parts of about PART_LINES lines
# of text, all at once. A paste without stamps cannot be cut safely (a mill's
# block may depend on the heading three blocks above it) and is read in one
# request, which MAX_LINES keeps inside the reader's time limit.
PART_LINES = 60
MAX_PARTS = 6
MAX_LINES = 300
# Sizes kept sane whatever the model answers or a person types.
LABEL_MAX, VALUE_MAX = 80, 200

FORM_KEYS = tuple(form.key for form in forms.FORMS) + (forms.OTHER,)
FIELD_KEYS = tuple(dict.fromkeys(f.key for form in forms.FORMS for f in form.fields))


# --- what the model returns ------------------------------------------------------------
#
# The descriptions are sent as part of the JSON schema, so they double as
# instructions. Everything read from the text is a string, copied as written.
# `key` is an enum of the fixed set, so the model cannot return any other key.
# (A shorter answer, one "line|key|value" string per value, was tried: it came
# back a third faster but dropped fields, where this shape dropped none.)

class Value(BaseModel):
    key: Literal[FIELD_KEYS] = Field(description="A field of the section's own form.")  # type: ignore[valid-type]
    value: str = Field(description=(
        "The value exactly as written, digit for digit, without its unit: '2.3', '04.80', '00', '42×100', "
        "'1:9', '17 to 18', 'Main', 'Ext', '----'."))
    line: int = Field(description="Number of the line the value is written on.")


class Extra(BaseModel):
    label: str = Field(description="What the reading is, in a few plain words.")
    value: str = Field(description="The value exactly as written.")
    line: int = Field(description="Number of the line the value is written on.")


class Section(BaseModel):
    form: Literal[FORM_KEYS] = Field(description="The form this section fills in.")  # type: ignore[valid-type]
    tag: str = Field(description=(
        "What the form says its tag is: '2A' for Mill 2A or ID Fan 2 A, '2' for Unit 2 or E.S.P - 2, '1' for "
        "DG-01. Empty for a form without a tag."))
    first_line: int = Field(description="Number of the first line of this section alone, its heading included.")
    last_line: int = Field(description="Number of the last line of this section alone.")
    date_written: str = Field(description=(
        "The date in the heading of the message this section is part of, exactly as written ('12.11.2026', "
        "'12 - 11- 2026'). Empty when the message has no date."))
    values: list[Value]
    extra: list[Extra] = Field(description="Readings in this section that its form has no field for. Usually empty.")


class Paste(BaseModel):
    sections: list[Section]


SCHEMA = extract.response_schema(Paste)

SYSTEM_PROMPT = """\
You file the routine readings that staff of Tenughat Thermal Power Station (two \
210 MW coal-fired units, Unit 1 and Unit 2) send on WhatsApp into a fixed set \
of fields. Each message is typed on a phone by a different person, so there is \
no fixed layout: labels are abbreviated, separators change from line to line, \
and several values often share one line. What is reported is the same every \
day; only the way it is written changes.

You receive a paste of one or more such messages, one after another. Every line \
starts with its line number and a "|". The values you return are stored as they \
are and compared with other days, so a wrong digit or a value under the wrong \
field does real harm. Work as a careful clerk, not an analyst.

Sections
- The forms listed at the end are the fixed set. A form is one kind of message, \
or one piece of equipment in a message. Return one section for every form you \
find filled in: one per mill, one per fan, one per ESP, one per DG set, one per \
report.
- A message normally opens with a heading that names the unit, the area and the \
date. A line such as "[12/11/26, 7:05 AM] Name:" is WhatsApp's own stamp at the \
start of a message. Lines of only dashes, quotes or other punctuation are \
separators.
- date_written is the date of the message the section is part of. Every section \
of one message carries that message's date: Mill 2C, written under Mill 2A in \
the same message, has the date in the heading above Mill 2A. When the heading \
has no date, use the date in the WhatsApp stamp. A date written beside a single \
reading (the day a lab sample was taken) is not the message's date.
- A message that fits none of the forms is one section with the form "other" \
and all of its readings in extra.

Values
- Give each value the key of the field it belongs to, from the section's own \
form. The text after each field shows how staff write it. Never use a key from \
another form.
- Go through the message line by line so that no number is passed over. Every \
number is a reading unless it is part of a heading, a date, a time or size \
named in a label, or the number of a piece of equipment.
- Copy the value exactly as written, without its unit. Never calculate, \
convert, round, correct or complete a value, and never supply one that is not \
written.
- A dash, colon, equals sign, dot or underscore between a label and its value \
is only a separator: "DE --50 C" is 50, "NDE.-37 C" is 37, "SOT Vacuum - 230" \
is 230, "Hz-49.82" is 49.82. A value is negative only when a minus sign follows \
the separator: "Vacuum:- -640" is -640, "U#2= -9.3" is -9.3.
- A value written as a dash or as dashes ("U#1= -", "26/----") was not taken: \
return the dashes as the value.
- A field with nothing written for it is left out.
- A reading the form has no field for goes in extra, with a short label in \
plain words. Never put it in a field that means something else. Greetings, \
sign-offs, shift and group names (M/S, Gr-c) are not readings.

Abbreviations used at this plant: LPD, HPD = LP, HP discharge pressure; HPS = HP \
suction pressure; LOP = lube oil pump; Brg = bearing; DE, NDE = drive end, \
non-drive end; PA fan = primary air fan; ID, FD fan = induced, forced draught \
fan; ESP = electrostatic precipitator; U/V = under voltage; EOP = emergency oil \
pump; SOP = starting oil pump; BFP = boiler feed pump; CEP = condensate \
extraction pump; SOT = seal oil tank; MOT = main oil tank; S.O. = seal oil; TE, \
EE = turbine end, exciter end; CW = circulating water; ACW = auxiliary cooling \
water; I/L, O/L = inlet, outlet; DOT = day oil tank; HFO = heavy fuel oil; DG = \
diesel generator; U/C = unburnt carbon; GCV = gross calorific value; TSS = total \
suspended solids; MCG, YCG = month, year cumulative generation; PLF = plant load \
factor; U#1, U#2 = Unit 1, Unit 2; M/S, E/S, N/S = morning, evening, night \
shift; U/M = under maintenance.

The forms. Each line is: key = what it is [unit]; how it is written.

""" + forms.catalogue()

USER_PROMPT = "File every reading in these messages under its field."


# Tabs, no-break spaces and the other widths of space a phone may put in a message.
ODD_SPACE_RE = re.compile("[\t\u00a0\u2000-\u200b\u202f]")


def number_lines(text: str) -> list[str]:
    """The paste as lines, tabs and odd spaces made plain. Line n is lines[n - 1]."""
    return [ODD_SPACE_RE.sub(" ", line).rstrip() for line in text.replace("\r\n", "\n").split("\n")]


def _written(lines: list[str], first: int, last: int) -> int:
    return sum(1 for line in lines[first - 1:last] if line.strip())


def parts(lines: list[str]) -> list[tuple[int, int]]:
    """The paste as the (first, last) lines of each request. One part, the whole
    paste, unless it is long and its messages carry WhatsApp's stamps: then whole
    messages are grouped into parts of about PART_LINES lines of text."""
    whole = [(1, len(lines))]
    starts = [n for n, line in enumerate(lines, start=1) if STAMP_RE.match(line)]
    total = _written(lines, 1, len(lines))
    if len(starts) < 2 or total <= PART_LINES:
        return whole
    # Each message runs to the line before the next stamp; lines above the first stamp go with it.
    messages = [(1 if i == 0 else start, starts[i + 1] - 1 if i + 1 < len(starts) else len(lines))
                for i, start in enumerate(starts)]
    size = max(PART_LINES, math.ceil(total / MAX_PARTS))
    out: list[tuple[int, int]] = []
    for first, last in messages:
        if out and _written(lines, out[-1][0], last) <= size:
            out[-1] = (out[-1][0], last)
        else:
            out.append((first, last))
    return out


def too_long(lines: list[str]) -> bool:
    """Whether some part of the paste is more than one request can read in time."""
    return any(_written(lines, first, last) > MAX_LINES for first, last in parts(lines))


def request_body(lines: list[str], part: Optional[tuple[int, int]] = None) -> dict:
    first, last = part or (1, len(lines))
    # A part keeps the paste's own line numbers, so the answers go together as they are.
    numbered = "\n".join(f"{n}| {lines[n - 1]}" for n in range(first, last + 1))
    return {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": f"{USER_PROMPT}\n\nThe messages:\n{numbered}"}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA,
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
        },
    }


async def read(lines: list[str], model: str | None = None) -> tuple[Paste, str, dict]:
    """The paste as sections of values, with the model and the token usage: one
    request per part (see parts), all running at once. If any part cannot be
    read the whole paste fails, so a day is never half filed without notice."""
    answers = await asyncio.gather(*(
        extract.ask(request_body(lines, part), Paste.model_validate_json, "these messages", model)
        for part in parts(lines)))
    sections = [section for answer, _, _ in answers for section in answer.sections]
    usage = {key: sum(u.get(key) or 0 for _, _, u in answers) or None
             for key in ("inputTokens", "outputTokens", "thinkingTokens")}
    return Paste(sections=sections), answers[0][1], usage


# --- from the model's answer to records ----------------------------------------------------

DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[-./]\s*(\d{1,2})\s*[-./]\s*(\d{4}|\d{2})(?!\d)")
NUMBER_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)$")
# A number in a line of a message: "0.70" in "0.70kg", the "2" of "BFP 2A". Not
# the digit of a word (H2, Cm2), of U#1, or the decimals of another number.
LOOSE_NUMBER_RE = re.compile(r"(?<![A-Za-z#\d])(?<!\d\.)\d+(?:\.\d+)?(?!\.?\d)")
LIST_NUMBER_RE = re.compile(r"^\s*\d{1,2}\s*[.)]\s*(?=[A-Za-z])")
# WhatsApp's own stamp at the start of each message copied along with others:
# "[12/11/26, 7:05:12 AM] Name: " on an iPhone, "[7:05 am, 12/11/2026] Name: " on
# Android and on the web. Group 1 holds its time and date.
STAMP_RE = re.compile(r"^\s*\[(?=[^\]]*\d{1,2}:\d{2})(?=[^\]]*\d{1,2}/\d{1,2}/\d{2,4})([^\]]{8,40})\][^:]{1,60}:\s?")


def parse_date(written: str) -> Optional[date]:
    """A date as people here write it, day first: '12.11.2026', '12 - 11- 2026', '4/11/26'."""
    match = DATE_RE.search(written or "")
    if not match:
        return None
    day, month, year = (int(g) for g in match.groups())
    try:
        return date(year + 2000 if year < 100 else year, month, day)
    except ValueError:
        return None


def parse_number(value: Optional[str]) -> Optional[float]:
    """The value as a number when it is plainly one ('04.80', '-640', '00'); None
    for anything else ('42×100', '17 to 18', 'Main', '----')."""
    text = (value or "").strip().replace(",", "")
    return float(text) if NUMBER_RE.match(text) else None


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text).casefold()


def clip(text, limit: int) -> str:
    return re.sub(r"\s+", " ", text if isinstance(text, str) else "").strip()[:limit]


def _numbers(text: str) -> list[float]:
    return [float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)]


def _unused_numbers(line: str, used: list[str]) -> list[str]:
    """Numbers on a line that nothing taken from it accounts for. `used` is the
    values read from the line, their fields' labels and the section's tag."""
    spoken = [n for chunk in used for n in _numbers(chunk)]
    left = []
    for found in LOOSE_NUMBER_RE.findall(LIST_NUMBER_RE.sub("", DATE_RE.sub(" ", STAMP_RE.sub("", line)))):
        if float(found) in spoken:
            spoken.remove(float(found))
        else:
            left.append(found)
    return left


# A number with what the model may leave stuck to it: '154MW', '40.', '12Kg/Cm2', '29..A'.
PLAIN_RE = re.compile(r"^([+-]?)\s*(\d+(?:\.\d+)?|\.\d+)[.\s\-]*(?:[A-Za-z%°]+(?:/[A-Za-z]+\d?)?\.?)?$")
# What stands before a number that is really negative: a separator, then a minus of its own.
MINUS_RE = re.compile(r"(?:[:=\-]\s+|=)-$")


def _tidy(value: str) -> str:
    """A number without the unit or full stop written against it; anything else as it is."""
    match = PLAIN_RE.match(value)
    return f"{match.group(1)}{match.group(2)}" if match else value


def _signed(value: str, line: str) -> str:
    """A number with the sign it has on its line. Staff put ':-', '--' or '.-'
    between a label and its value, so a dash before a number is a minus only
    when it follows such a separator: ':- -640', '= -9.3'. Decided here, from
    the line, because a model reads ':-43' as -43 often enough to matter."""
    if not NUMBER_RE.match(value):
        return value
    bare = value.lstrip("+-")
    signs = {"-" if MINUS_RE.search(line[:found.start()]) else ""
             for found in re.finditer(rf"(?<![\d.]){re.escape(bare)}(?!\d|\.\d)", line)}
    return f"{signs.pop()}{bare}" if len(signs) == 1 else value


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _locate(value: str, named: int, first: int, last: int, lines: list[str]) -> Optional[int]:
    """The line of the section that carries the value as written: the one the
    model named, else the nearest one that has it, else None."""
    needle = _squash(value)
    if first <= named <= last and needle in _squash(lines[named - 1]):
        return named
    near = [n for n in range(first, last + 1) if needle in _squash(lines[n - 1])]
    return min(near, key=lambda n: abs(n - named)) if near else None


NOT_FOUND = "This value is not in the message as written."
# This many lines with numbers outside every section means a message was skipped
# (a heading or a greeting accounts for one or two).
UNREAD_LINES = 4


def records(paste: Paste, lines: list[str], fallback: date, today: date) -> tuple[list[dict], list[str]]:
    """The model's answer as records ready to store, one per (date, section), and
    notes for the person who pasted. Everything is checked against `lines`."""
    out: dict[tuple, dict] = {}
    notes: list[str] = []
    count = len(lines)
    pasted = _squash("\n".join(lines))

    for section in paste.sections:
        form = forms.BY_KEY.get(section.form)
        tag = form.clean_tag(section.tag) if form else ""
        if form and tag is None:
            notes.append(f"A {form.name} message does not say which one it is (\"{clip(section.tag, 20)}\"), so its "
                         f"readings are under \"{forms.OTHER_TITLE}\".")
            form, tag = None, ""
        first = min(max(section.first_line, 1), count)
        last = min(max(section.last_line, first), count)
        title = form.title.format(tag=tag) if form else forms.OTHER_TITLE

        # The date: as written in the message, read day first. Never the model's arithmetic.
        # A message with no date in its heading has the date of WhatsApp's stamp above it.
        day = parse_date(section.date_written) if _squash(section.date_written) in pasted else None
        if day is None:
            stamp = next(filter(None, (STAMP_RE.match(lines[n - 1]) for n in range(first, 0, -1))), None)
            day = parse_date(stamp.group(1)) if stamp else None
        if day is not None and (day > today + timedelta(days=1) or day < today - timedelta(days=366)):
            notes.append(f"{title} is dated {day:%d.%m.%Y}, which is not a day it can have been sent, so it was "
                         f"filed under {fallback:%d.%m.%Y}.")
            day = None
        dated = day is not None
        day = day or fallback

        sid = forms.section_id(form, tag) if form else forms.OTHER
        record = out.setdefault((day.isoformat(), sid), {
            "date": day.isoformat(), "section": sid, "form": form.key if form else forms.OTHER, "tag": tag,
            "dated": dated, "values": {}, "src": {}, "checks": {}, "extra": [], "missed": [], "pieces": [],
        })
        record["dated"] = record["dated"] or dated
        # The text of the message, as pasted; a second block for the same section is a second piece.
        piece = "\n".join(lines[first - 1:last]).strip("\n")
        if piece and piece not in record["pieces"]:
            record["pieces"].append(piece)

        cited: dict[int, list[str]] = {}
        rows = [(v.line, v.key, v.value) for v in section.values]
        extras = []
        for e in section.extra:
            # An "extra" that names a field of the form after all is that field's value.
            named = _slug(e.label)
            match = next((f for f in (form.fields if form else ()) if named in (f.key, _slug(f.label))), None)
            if match:
                rows.append((e.line, match.key, e.value))
            else:
                extras.append((clip(e.label, LABEL_MAX), clip(e.value, VALUE_MAX), e.line))
        for named, key, value in rows:
            field = form.field(key) if form else None
            value = clip(value, VALUE_MAX)
            if not value:
                continue
            if set(value) <= set("-–—_ "):
                value = "-"  # not taken, however many dashes were typed
            elif field is not None and not field.text:
                value = _tidy(value)
            if field is None or key in record["values"]:
                # Not a key of this form, or a second value for a field: kept, but not as that field.
                extras.append((field.label if field else clip(key.replace("_", " "), LABEL_MAX), value, named))
                continue
            at = _locate(value.lstrip("+-") or value, named, first, last, lines)
            if at is not None and not field.text:
                value = _signed(value, lines[at - 1])
            record["values"][key] = value
            if at is None:
                record["checks"][key] = NOT_FOUND
            else:
                record["src"][key] = lines[at - 1].strip()
                cited.setdefault(at, []).extend([value, field.label])
        for label, value, named in extras:
            if not label or not value:
                continue
            at = _locate(value, named, first, last, lines)
            row = {"label": label, "value": value, "src": lines[at - 1].strip() if at else ""}
            if row not in record["extra"]:
                record["extra"].append(row)
            if at:
                cited.setdefault(at, []).extend([value, label])

        # Numbers the model passed over on a line it took other values from.
        for at, used in sorted(cited.items()):
            left = _unused_numbers(lines[at - 1], used + [tag])
            entry = {"line": lines[at - 1].strip(), "numbers": left}
            if left and entry not in record["missed"]:
                record["missed"].append(entry)

    # A whole message the model passed over: lines with numbers that are in no section.
    inside = {n for section in paste.sections
              for n in range(max(section.first_line, 1), min(max(section.last_line, section.first_line), count) + 1)}
    outside = [n for n in range(1, count + 1)
               if n not in inside and _unused_numbers(lines[n - 1], [])]
    if len(outside) >= UNREAD_LINES:
        # Name the longest stretch of them by the line it starts under (its heading, as a rule).
        runs: list[list[int]] = []
        for n in outside:
            if runs and n - runs[-1][-1] <= 3:
                runs[-1].append(n)
            else:
                runs.append([n])
        start = max(runs, key=len)[0]
        while start > 1 and start - 1 not in inside and lines[start - 2].strip():
            start -= 1
        notes.append(f"{len(outside)} lines with numbers were not read into any section, from "
                     f"\"{clip(lines[start - 1], 60)}\". Paste that message again by itself.")

    kept = [r for r in out.values() if r["values"] or r["extra"]]
    return kept, notes


def update(record: dict, stamp: dict) -> dict:
    """How a paste's record is added to what is stored for its day and section,
    as one MongoDB update (upserted on date and section).

    A day's messages come in several pastes, in pieces and in any order, so
    nothing is replaced wholesale: each value pasted is set (a later paste of a
    reading wins, even over a hand correction), every other stored value stays,
    and the pieces of message, extras and passed-over numbers add up, each kept
    once, so pasting the same text twice changes nothing. One update, not a read
    and a write, so two pastes for the same section at once cannot lose either."""
    values, checks = record["values"], record["checks"]
    change: dict = {
        "$set": {**stamp,
                 **{f"values.{k}": v for k, v in values.items()},
                 **{f"src.{k}": v for k, v in record["src"].items()},
                 **{f"checks.{k}": v for k, v in checks.items()}},
        "$setOnInsert": {"form": record["form"], "tag": record["tag"]},
        "$addToSet": {name: {"$each": record[name]} for name in ("pieces", "extra", "missed")},
    }
    # A value found in this paste clears an old "not found"; one not found has no source line.
    unset = {**{f"checks.{k}": "" for k in values if k not in checks}, **{f"src.{k}": "" for k in checks}}
    if unset:
        change["$unset"] = unset
    if values:
        change["$pull"] = {"edited": {"$in": list(values)}}
    # Dated once a dated piece has come; an undated piece never undoes that.
    if record["dated"]:
        change["$set"]["dated"] = True
    else:
        change["$setOnInsert"]["dated"] = False
    return change


def without_number(missed: list[dict], value: str) -> list[dict]:
    """The passed-over numbers, less the one a person has just typed in as a value."""
    number = parse_number(value)
    if number is None:
        return missed
    out = []
    for entry in missed:
        left = list(entry["numbers"])
        match = next((n for n in left if float(n) == number), None)
        if match is not None:
            left.remove(match)
            number = None  # only once
        if left:
            out.append({**entry, "numbers": left})
    return out


def to_check(record: dict) -> int:
    return len(record.get("checks") or {}) + len(record.get("missed") or [])


# --- a day beside another day ----------------------------------------------------------------

def _decimals(value: Optional[str]) -> int:
    match = re.search(r"\.(\d+)", value or "")
    return len(match.group(1)) if match else 0


def title(record: dict) -> str:
    form = forms.BY_KEY.get(record.get("form"))
    return form.title.format(tag=record.get("tag") or "") if form else forms.OTHER_TITLE


def compare(record: dict, previous: Optional[dict]) -> dict:
    """A stored section as the app shows it: every field with a value on either
    day, in the form's order, with the other day's value and the change."""
    form = forms.BY_KEY.get(record.get("form"))
    values, before = record.get("values") or {}, (previous or {}).get("values") or {}
    source = record.get("src") or {}
    rows, changed = [], 0
    for field in (form.fields if form else ()):
        value, prev = values.get(field.key), before.get(field.key)
        if value is None and prev is None:
            continue
        num = None if field.text else parse_number(value)
        prev_num = None if field.text else parse_number(prev)
        delta = None
        if num is not None and prev_num is not None:
            delta = round(num - prev_num, max(_decimals(value), _decimals(prev)))
            differs = delta != 0
        else:
            differs = previous is not None and _squash(value or "") != _squash(prev or "")
        changed += differs
        rows.append({
            "key": field.key, "label": field.label, "unit": field.unit, "group": field.group, "text": field.text,
            "value": value, "num": num, "prev": prev, "delta": delta, "changed": bool(differs),
            "check": (record.get("checks") or {}).get(field.key),
            "edited": field.key in (record.get("edited") or []),
            "src": source.get(field.key) or "",
        })
    return {
        "id": record["section"], "form": record.get("form"), "name": title(record), "tag": record.get("tag") or "",
        "date": record["date"], "dated": record.get("dated", True),
        "rows": rows, "extra": record.get("extra") or [], "missed": record.get("missed") or [],
        "raw": "\n\n".join(record.get("pieces") or []), "messages": len(record.get("pieces") or []),
        "updatedAt": record.get("updatedAt"), "updatedBy": record.get("updatedBy"),
        "previousDate": previous["date"] if previous else None,
        "counts": {"values": len(values), "changed": changed if previous else 0, "toCheck": to_check(record)},
    }


def order(record: dict) -> tuple:
    """Sections in the order of the forms, then by tag; readings outside the set last."""
    form = record.get("form")
    return (FORM_KEYS.index(form) if form in FORM_KEYS else len(FORM_KEYS), record.get("tag") or "")
