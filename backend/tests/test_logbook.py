"""Pasted WhatsApp messages -> a day's readings under the fixed set of keys.

The two fixtures are real days of messages (tests/fixtures/logs_*.txt) with the
reading model's answer for each (logs_*.json), checked by hand against the
text. No request leaves the machine: the reader is replaced by one that hands
back a prepared answer.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import date, datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

import extract
import logbook
import logbook_forms as forms
import main
from helpers import FIXTURES, sign_in
from logbook import Extra, Paste, Section, Value

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=main.IST)
TODAY = NOW.date()
DAY_1, DAY_2 = "logs_2026-11-11", "logs_2026-11-12"


def fixture(name: str) -> tuple[str, Paste]:
    return (FIXTURES / f"{name}.txt").read_text(), Paste.model_validate_json((FIXTURES / f"{name}.json").read_text())


def stored(name: str, fallback: date = TODAY) -> dict[str, dict]:
    """A fixture day as records(), by section."""
    text, paste = fixture(name)
    records, notes = logbook.records(paste, logbook.number_lines(text), fallback, TODAY)
    assert notes == []
    return {r["section"]: r for r in records}


def one(lines: list[str], values=(), extra=(), form="mill", tag="2A", written="12.11.2026",
        fallback: date = TODAY) -> tuple[list[dict], list[str]]:
    """records() for a single section covering all of `lines`. values: (key, value, line)."""
    section = Section(form=form, tag=tag, first_line=1, last_line=len(lines), date_written=written,
                      values=[Value(key=k, value=v, line=n) for k, v, n in values],
                      extra=[Extra(label=k, value=v, line=n) for k, v, n in extra])
    return logbook.records(Paste(sections=[section]), lines, fallback, TODAY)


# --- the fixed set ---------------------------------------------------------------------------------

def test_every_key_can_be_a_database_field_and_is_named_once_per_form():
    assert [f.key for f in forms.FORMS] == ["generation", "mill", "id_fan", "fd_fan", "esp", "turbine",
                                            "stator_cw", "chemical", "silo", "fuel_oil", "dg", "acw"]
    for form in forms.FORMS:
        keys = [f.key for f in form.fields]
        labels = [f.label for f in form.fields]
        assert len(set(keys)) == len(keys), form.key
        assert len(set(labels)) == len(labels), form.key
        assert all(re.fullmatch(r"[a-z0-9_]+", k) for k in keys), form.key
        assert bool(form.tag) == bool(form.tag_re) == ("{tag}" in form.title), form.key
    assert sum(len(form.fields) for form in forms.FORMS) == 221
    assert len(forms.ESP.fields) == 4 * 7 * 2 + 2


def test_tags_are_tidied_or_refused():
    assert forms.MILL.clean_tag("2 a") == "2A"
    assert forms.MILL.clean_tag("Mill-2A") is None
    assert forms.MILL.clean_tag("") is None
    assert forms.DG.clean_tag("01") == "1"
    assert forms.ESP.clean_tag("2") == "2"
    assert forms.ESP.clean_tag("3") is None
    assert forms.CHEMICAL.clean_tag("whatever") == ""
    assert forms.section_id(forms.MILL, "2A") == "mill_2a"
    assert forms.section_id(forms.SILO, "") == "silo"


def test_the_model_is_given_every_key_and_can_return_no_other():
    catalogue = forms.catalogue()
    for form in forms.FORMS:
        assert f"FORM {form.key}:" in catalogue
        for field in form.fields:
            assert f"  {field.key} = {field.label}" in catalogue
    assert catalogue in logbook.SYSTEM_PROMPT

    schema = logbook.SCHEMA
    flat = json.dumps(schema)
    assert "$ref" not in flat and "$defs" not in flat
    section = schema["properties"]["sections"]["items"]
    assert section["properties"]["form"]["enum"] == [f.key for f in forms.FORMS] + ["other"]
    value = section["properties"]["values"]["items"]
    assert set(value["properties"]["key"]["enum"]) == {f.key for form in forms.FORMS for f in form.fields}
    assert value["propertyOrdering"] == ["key", "value", "line"]


# --- dates and numbers are read by the code ---------------------------------------------------------

@pytest.mark.parametrize("written, expected", [
    ("12.11.2026", date(2026, 11, 12)),
    ("12 - 11- 2026", date(2026, 11, 12)),
    ("12. 11.2026", date(2026, 11, 12)),
    ("Date-12/11/2026", date(2026, 11, 12)),
    ("4/11/26", date(2026, 11, 4)),
    ("[03/11/26, 7:05 AM] Name:", date(2026, 11, 3)),   # day first, as the plant's phones write it
    ("31.02.2026", None),
    ("no date here", None),
    ("", None),
])
def test_dates_are_read_day_first(written, expected):
    assert logbook.parse_date(written) == expected


@pytest.mark.parametrize("value, expected", [
    ("2.3", 2.3), ("04.80", 4.8), ("00", 0.0), ("-640", -640.0), (".38", 0.38), ("1,521.54", 1521.54),
    ("42×100", None), ("17 to 18", None), ("Main", None), ("-", None), ("1:9", None), ("24:00", None), (None, None),
])
def test_only_a_plain_number_is_a_number(value, expected):
    assert logbook.parse_number(value) == expected


@pytest.mark.parametrize("value, expected", [
    ("154MW", "154"), ("72.12%", "72.12"), ("40.", "40"), ("12Kg/Cm2", "12"), ("46 C", "46"), ("29..A", "29"),
    ("245-A", "245"), ("04.80", "04.80"), ("-640", "-640"),
    ("42×100", "42×100"), ("17 to 18", "17 to 18"), ("06-30", "06-30"), ("1.5/4000", "1.5/4000"),
])
def test_a_unit_stuck_to_a_number_is_taken_off(value, expected):
    assert logbook._tidy(value) == expected


@pytest.mark.parametrize("value, line, expected", [
    ("-43", "Lub oil tem. :-43", "43"),                       # ':-' is how they write a colon
    ("-50", "PA fan motor brg. NDE:- 36   DE:--50", "50"),
    ("-50", "DE --50 C", "50"),
    ("-37", "NDE.-37  C", "37"),
    ("-49.82", "Volt- 417.0  Hz-49.82", "49.82"),
    ("-1.20", "LUBE OIL PR./TEMP. -1.20KG/34C", "1.20"),
    ("640", "Expansion Tank Vacuum:- -640", "-640"),          # a minus of its own after the separator
    ("9.3", "           U#2= -9.3", "-9.3"),
    ("-12", "Dew point: -12", "-12"),
    ("33", "Silo#1 (Hywa): - 33 Nos", "33"),
    ("Main", "LPD-Main-2.3", "Main"),
])
def test_the_sign_comes_from_the_line_not_from_the_model(value, line, expected):
    assert logbook._signed(value, line) == expected


# --- a real day, end to end ---------------------------------------------------------------------------

def test_day_one_is_filed_under_the_fixed_keys():
    day = stored(DAY_1)
    assert list(day) == ["mill_2a", "mill_2c", "esp_2", "id_fan_2a", "id_fan_2b", "fd_fan_2a", "fd_fan_2b",
                         "stator_cw_2", "turbine_2"]
    assert {r["date"] for r in day.values()} == {"2026-11-11"}
    assert all(r["dated"] for r in day.values())
    assert sum(len(r["values"]) for r in day.values()) == 169
    # Nothing to check, nothing passed over, nothing outside the set.
    assert [(s, r["checks"], r["missed"], r["extra"]) for s, r in day.items() if logbook.to_check(r) or r["extra"]] == []

    mill = day["mill_2a"]["values"]
    assert (mill["lp_pump"], mill["lp_discharge"], mill["hp_pump"], mill["hp_suction"]) == ("Main", "2.3", "Main", "1.6")
    assert [mill[f"hp_discharge_{n}"] for n in (1, 2, 3, 4)] == ["30", "41", "45", "41"]
    assert (mill["pa_fan_de"], mill["pa_fan_nde"], mill["motor_de"], mill["motor_nde"]) == ("48", "35", "63", "34")
    assert (mill["reducer_flow"], mill["flow_nde"], mill["flow_de"]) == ("42×100", "7×4", "7×4")
    assert day["mill_2c"]["values"]["lp_pump"] == "Standby"
    # Mill 2C has no date of its own: it is in Mill 2A's message.
    assert day["mill_2c"]["pieces"][0].lstrip().startswith("Mill-2C")

    esp = day["esp_2"]["values"]
    assert len(esp) == 58
    assert (esp["4a_ma"], esp["4a_kv"], esp["4c_ma"], esp["4c_kv"]) == ("140", "34", "30", "27")
    assert (esp["6d_ma"], esp["6d_kv"], esp["2c_ma"], esp["2c_kv"]) == ("240", "20", "40", "03")
    assert esp["under_voltage"] == "1A, 7A,1B,3B,5B,2C,2D,5D"

    assert day["fd_fan_2a"]["values"] == {"motor_de": "33", "motor_nde": "37", "fan_de": "49", "fan_nde": "37",
                                           "control_oil_pressure": "10.1", "lube_oil_pressure": "1.4",
                                           "lube_oil_temp": "38"}
    turbine = day["turbine_2"]["values"]
    assert (turbine["sot_vacuum"], turbine["expansion_tank_vacuum"], turbine["seal_oil_exhaust_fan"]) == ("230", "-640", "B")
    assert (turbine["bfp_a_oil_temp"], turbine["bfp_b_lube_pressure"], turbine["cep_b_thrust_temp"]) == ("82", "3.1", "59")
    assert "bfp_c_oil_temp" not in turbine
    # A reading written as dashes was not taken.
    assert day["stator_cw_2"]["values"]["cw_in_temp_2"] == "-"


def test_day_two_is_filed_under_the_fixed_keys():
    day = stored(DAY_2)
    assert list(day) == ["generation", "silo", "chemical", "fuel_oil", "mill_1a", "mill_1b", "dg_1", "dg_2", "acw"]
    assert {r["date"] for r in day.values()} == {"2026-11-12"}
    assert sum(len(r["values"]) for r in day.values()) == 143
    assert [(s, r["checks"], r["missed"], r["extra"]) for s, r in day.items() if logbook.to_check(r) or r["extra"]] == []

    generation = day["generation"]["values"]
    assert (generation["load_u1"], generation["gen_u2"], generation["mcg"], generation["month_plf"]) == \
        ("154", "3.65", "79.97", "72.12")
    # Unit 1 lays the mill out differently; the same keys come out.
    mill = day["mill_1a"]["values"]
    assert (mill["lp_discharge"], mill["hp_suction"], mill["flow_nde"], mill["flow_de"]) == ("5.7", "1.4", "26", "29")
    assert (mill["grease_pressure"], mill["atomising_air"]) == ("10.0", "6.0")
    assert (mill["reducer_pressure"], mill["reducer_flow"], mill["noise"]) == ("1.5", "4000", "17 to 18")
    assert set(stored(DAY_1)["mill_2a"]["values"]) - set(mill) == {"lp_pump", "hp_pump"}
    assert day["mill_1b"]["values"]["pa_motor_de"] == "50"       # written 'DE:--50'

    chemical = day["chemical"]["values"]
    assert (chemical["dew_point_u1"], chemical["dew_point_u2"], chemical["cation_u2"]) == ("-", "-9.3", "Ext")
    assert (chemical["uc_fly_u1"], chemical["fly_colour_u1"]) == ("5.08", "S.Blackish")
    # The date beside the GCV is the sample's, not the message's.
    assert (chemical["gcv"], chemical["gcv_date"]) == ("3597", "10.11.2026")
    silo = day["silo"]["values"]
    assert (silo["run_u1_b"], silo["bulkers_s1_60"], silo["bulkers_s1_40"], silo["level_s1"]) == ("24:00", "06", "10", "04.80")
    assert day["fuel_oil"]["values"]["hfo_pressure_2a"] == "12.5"
    assert day["dg_1"]["values"]["status"] == "U/M"
    assert day["dg_2"]["values"] == {"status": "Trial run taken from.C.R.", "oil_level": "625",
                                      "run_time": "06-30 to 06-34", "voltage": "417.0", "frequency": "49.82"}
    acw = day["acw"]["values"]
    assert (acw["acw_pump_u1"], acw["acw_current_u1"], acw["cw56_u2"], acw["ash_water_pumps"]) == ("1B", "29", "100", "01 & 02")


def test_each_value_remembers_the_line_it_came_from():
    record = stored(DAY_1)["mill_2a"]
    view = logbook.compare(record, None)
    rows = {r["key"]: r for r in view["rows"]}
    assert rows["pa_motor_nde"]["src"] == "P.A FAN Motor= NDE- 50/DE-49"
    assert rows["hp_discharge_3"]["src"].startswith("LPD-Main-2.3/B.S-19,26/HPD- 30,41,45,41")
    assert all(r["src"] for r in view["rows"])


# --- what the code catches --------------------------------------------------------------------------

def test_a_unit_or_a_separator_dash_from_the_model_is_put_right():
    records, _ = one(["Mill-1B  12.11.2026", "Lub oil tem. :-43", "L P discharge : 5.7"],
                     values=[("lube_oil_temp", "-43", 2), ("lp_discharge", "5.7kg", 3)], tag="1B")
    assert records[0]["values"] == {"lube_oil_temp": "43", "lp_discharge": "5.7"}
    assert records[0]["checks"] == {}


def test_a_value_that_is_not_in_the_message_is_marked():
    records, _ = one(["Mill- 2A  12.11.2026", "PA FAN LOP -A-Press=1.1"],
                     values=[("pa_lop", "A", 2), ("pa_lop_pressure", "1.7", 2)])
    assert records[0]["values"]["pa_lop_pressure"] == "1.7"
    assert records[0]["checks"] == {"pa_lop_pressure": logbook.NOT_FOUND}
    # ...and the number that is there was not used, which says what it should have been.
    assert records[0]["missed"] == [{"line": "PA FAN LOP -A-Press=1.1", "numbers": ["1.1"]}]
    assert logbook.to_check(records[0]) == 2
    assert logbook.compare(records[0], None)["rows"][-1]["check"] == logbook.NOT_FOUND


def test_a_wrong_line_number_is_corrected_from_the_text():
    records, _ = one(["Mill- 2A  12.11.2026", "Temp=33", "Grease press=8.0 kg."],
                     values=[("pa_lop_temp", "33", 3), ("grease_pressure", "8.0", 99)])
    assert records[0]["checks"] == {}
    assert records[0]["src"] == {"pa_lop_temp": "Temp=33", "grease_pressure": "Grease press=8.0 kg."}


def test_a_number_passed_over_on_a_line_is_reported():
    lines = ["Mill- 2A  12.11.2026", "LPD-Main-2.3/B.S-19,26/HPD- 30,41,45,41/HPS-Main-1.6/Temp-40"]
    values = [("lp_pump", "Main", 2), ("lp_discharge", "2.3", 2), ("bs_1", "19", 2), ("bs_2", "26", 2),
              ("hp_discharge_1", "30", 2), ("hp_discharge_2", "41", 2), ("hp_discharge_3", "41", 2),
              ("hp_suction", "1.6", 2), ("lube_oil_temp", "40", 2)]
    records, _ = one(lines, values=values)
    assert records[0]["missed"] == [{"line": lines[1], "numbers": ["45"]}]


def test_equipment_numbers_dates_and_list_numbers_are_not_missed_readings():
    assert logbook._unused_numbers("PA fan 1A Lop:-A -  1.18  Tem. :- 34", ["A", "PA fan lube oil pump in service",
                                   "1.18", "PA fan lube oil pressure", "34", "PA fan lube oil temperature", "1A"]) == []
    assert logbook._unused_numbers("8.GCV of coal= 3597", ["3597", "GCV of coal", ""]) == []
    assert logbook._unused_numbers("M/S. Gr-c  12 - 11- 2026  oil level - 530  Ltr", ["530", "Diesel oil level", "1"]) == []
    assert logbook._unused_numbers("*Pressure-1A-12Kg/Cm2&2A-12.5Kg/Cm2", ["12", "HFO pump 1A pressure", "12.5",
                                                                           "HFO pump 2A pressure", ""]) == []
    assert logbook._unused_numbers("H2 Consu. U#1=4", ["4", "H2 consumption, Unit 1", ""]) == []
    assert logbook._unused_numbers("Volt- 417.0  Hz-49.82", ["417.0", "Voltage", "1"]) == ["49.82"]


def test_a_key_of_another_form_or_a_second_value_is_kept_as_an_extra():
    records, _ = one(["Mill- 2A  12.11.2026", "Temp=33", "Temp=35", "SCOOP_ 100"],
                     values=[("pa_lop_temp", "33", 2), ("pa_lop_temp", "35", 3), ("scoop", "100", 4)])
    record = records[0]
    assert record["values"] == {"pa_lop_temp": "33"}
    assert record["extra"] == [{"label": "PA fan lube oil temperature", "value": "35", "src": "Temp=35"},
                               {"label": "scoop", "value": "100", "src": "SCOOP_ 100"}]


def test_an_extra_that_names_a_field_becomes_that_field():
    records, _ = one(["E.S.P - 2   12.11.2026", "All E.E.R.M charged."], form="esp", tag="2",
                     extra=[("Remarks", "All E.E.R.M charged.", 2)])
    assert records[0]["values"] == {"remarks": "All E.E.R.M charged."}
    assert records[0]["extra"] == []


def test_readings_outside_the_fixed_set_are_kept():
    records, _ = one(["Boiler  12.11.2026", "Drum level - 12"], form="other", tag="",
                     extra=[("Drum level", "12", 2)])
    assert records[0]["section"] == records[0]["form"] == "other"
    assert records[0]["extra"] == [{"label": "Drum level", "value": "12", "src": "Drum level - 12"}]
    assert logbook.compare(records[0], None)["name"] == "Not in the fixed set"


def test_a_section_that_does_not_say_which_one_it_is_goes_under_other():
    records, notes = one(["Mill  12.11.2026", "Temp=33"], values=[("pa_lop_temp", "33", 2)], tag="")
    assert [r["section"] for r in records] == ["other"]
    assert records[0]["extra"] == [{"label": "pa lop temp", "value": "33", "src": "Temp=33"}]
    assert len(notes) == 1 and "does not say which one" in notes[0]


def test_an_undated_message_goes_under_the_chosen_day():
    records, notes = one(["Mill- 2A", "Temp=33"], values=[("pa_lop_temp", "33", 2)], written="",
                         fallback=date(2026, 11, 10))
    assert (records[0]["date"], records[0]["dated"], notes) == ("2026-11-10", False, [])


def test_a_date_the_message_does_not_carry_is_not_believed():
    records, _ = one(["Mill- 2A", "Temp=33"], values=[("pa_lop_temp", "33", 2)], written="09.11.2026")
    assert (records[0]["date"], records[0]["dated"]) == (TODAY.isoformat(), False)


@pytest.mark.parametrize("stamp", ["[12/11/26, 7:02:55 AM] Operator DG: ", "[7:02 am, 12/11/2026] Operator DG: "])
def test_a_message_with_no_date_in_its_heading_takes_whatsapps_stamp(stamp):
    lines = ["[11/11/26, 9:40:01 PM] Someone: Mill- 2A", "Temp=33", f"{stamp}DG-01  U/M  oil level - 530  Ltr",
             "Volt- 00  Hz 00"]
    section = Section(form="dg", tag="01", first_line=3, last_line=4, date_written="", extra=[],
                      values=[Value(key="status", value="U/M", line=3), Value(key="oil_level", value="530", line=3),
                              Value(key="voltage", value="00", line=4), Value(key="frequency", value="00", line=4)])
    records, notes = logbook.records(Paste(sections=[section]), lines, date(2026, 11, 9), TODAY)
    # Its own stamp, not the one of the message above, and not the day on screen.
    assert (records[0]["date"], records[0]["dated"], notes) == ("2026-11-12", True, [])
    # The stamp's clock is not a reading that was passed over.
    assert records[0]["missed"] == []


def test_a_date_in_the_heading_wins_over_the_stamp():
    lines = ["[13/11/26, 6:10:00 AM] Someone: M/S  Date-12/11/2026", "*D.O.T  Level-2.98M"]
    records, _ = one(lines, values=[("dot_level", "2.98", 2)], form="fuel_oil", tag="", written="12/11/2026")
    assert records[0]["date"] == "2026-11-12"


def test_a_message_the_model_skipped_is_reported():
    text, paste = fixture(DAY_1)
    lines = logbook.number_lines(text)
    paste.sections = [s for s in paste.sections if s.form != "esp"]
    records, notes = logbook.records(paste, lines, TODAY, TODAY)
    assert "esp_2" not in {r["section"] for r in records}
    assert len(notes) == 1
    assert notes[0].startswith('17 lines with numbers were not read into any section, from "E.S.P - 2 11-11-2026".')
    # A heading or a greeting outside every section is not a skipped message.
    assert logbook.records(fixture(DAY_1)[1], lines, TODAY, TODAY)[1] == []


@pytest.mark.parametrize("written", ["12.12.2026", "12.11.2024"])
def test_a_date_it_cannot_have_been_sent_on_is_refused(written):
    records, notes = one([f"Mill- 2A  {written}", "Temp=33"], values=[("pa_lop_temp", "33", 2)], written=written)
    assert records[0]["date"] == TODAY.isoformat() and not records[0]["dated"]
    assert len(notes) == 1 and "not a day it can have been sent" in notes[0]


def test_two_blocks_for_one_section_are_one_record():
    lines = ["Mill- 2A  12.11.2026", "Temp=33", "ID Fan 2A", "SCOOP_ 100", "Mill-2A again", "Grease press=8.0 kg."]
    paste = Paste(sections=[
        Section(form="mill", tag="2A", first_line=1, last_line=2, date_written="12.11.2026",
                values=[Value(key="pa_lop_temp", value="33", line=2)], extra=[]),
        Section(form="mill", tag="2a", first_line=5, last_line=6, date_written="12.11.2026",
                values=[Value(key="grease_pressure", value="8.0", line=6)], extra=[]),
    ])
    records, _ = logbook.records(paste, lines, TODAY, TODAY)
    assert len(records) == 1
    view = logbook.compare(records[0], None)
    assert {r["key"]: r["src"] for r in view["rows"]} == {"pa_lop_temp": "Temp=33", "grease_pressure": "Grease press=8.0 kg."}


# --- one day beside another -----------------------------------------------------------------------

def test_compare_sets_each_value_beside_the_other_days():
    today = {"date": "2026-11-12", "section": "mill_2a", "form": "mill", "tag": "2A", "raw": "",
             "values": {"lp_pump": "Standby", "lp_discharge": "2.5", "lube_oil_temp": "40", "reducer_flow": "42×100",
                        "motor_de": "61.50", "noise": "17 to 18"}}
    before = {"date": "2026-11-11", "section": "mill_2a", "form": "mill", "tag": "2A",
              "values": {"lp_pump": "Main", "lp_discharge": "2.3", "lube_oil_temp": "40.0", "reducer_flow": "42 × 100",
                         "motor_de": "63", "hp_suction": "1.6"}}
    view = logbook.compare(today, before)
    assert (view["name"], view["previousDate"]) == ("Mill 2A", "2026-11-11")
    rows = {r["key"]: r for r in view["rows"]}
    # In the form's order, fields with a value on either day.
    assert list(rows) == ["lp_pump", "lp_discharge", "hp_suction", "lube_oil_temp", "motor_de", "reducer_flow", "noise"]
    assert (rows["lp_discharge"]["prev"], rows["lp_discharge"]["delta"], rows["lp_discharge"]["changed"]) == ("2.3", 0.2, True)
    assert (rows["motor_de"]["delta"], rows["motor_de"]["changed"]) == (-1.5, True)
    assert (rows["lube_oil_temp"]["delta"], rows["lube_oil_temp"]["changed"]) == (0.0, False)   # 40 and 40.0
    assert (rows["lp_pump"]["delta"], rows["lp_pump"]["changed"]) == (None, True)               # Main -> Standby
    assert rows["reducer_flow"]["changed"] is False                                             # spacing only
    assert (rows["hp_suction"]["value"], rows["hp_suction"]["prev"], rows["hp_suction"]["changed"]) == (None, "1.6", True)
    assert (rows["noise"]["prev"], rows["noise"]["changed"]) == (None, True)
    assert view["counts"] == {"values": 6, "changed": 5, "toCheck": 0}


def test_nothing_is_changed_when_there_is_no_other_day():
    view = logbook.compare(stored(DAY_1)["id_fan_2a"], None)
    assert view["previousDate"] is None
    assert view["counts"] == {"values": 7, "changed": 0, "toCheck": 0}
    assert all(r["prev"] is None and r["delta"] is None and not r["changed"] for r in view["rows"])
    assert view["rows"][0] == {"key": "motor_de", "label": "Motor bearing temperature DE", "unit": "°C", "group": "",
                               "text": False, "value": "47", "num": 47.0, "prev": None, "delta": None,
                               "changed": False, "check": None, "edited": False, "src": "DE.__47 C"}


# --- the call to the model -----------------------------------------------------------------------

def stamped(messages: list[int]) -> list[str]:
    """A paste of stamped messages, each with this many lines of text."""
    lines = []
    for i, size in enumerate(messages):
        lines.append(f"[12/11/26, 7:{10 + i}:00 AM] Desk {i}: Mill- 1{'ABCDEF'[i % 6]}  12.11.2026")
        lines += [f"Temp={30 + n}" for n in range(size - 1)] + [""]
    return lines


def test_a_paste_is_one_request_unless_it_is_long_and_stamped():
    text, _ = fixture(DAY_2)
    lines = logbook.number_lines(text)
    assert logbook.parts(lines) == [(1, len(lines))]                 # 128 lines of text, no stamps: no safe place to cut
    assert logbook.parts(stamped([20, 20])) == [(1, 42)]             # short: not worth cutting
    # Whole messages, grouped to about PART_LINES lines of text each.
    assert logbook.parts(stamped([30, 30, 30, 30])) == [(1, 62), (63, 124)]
    assert logbook.parts(stamped([50, 40, 15, 10])) == [(1, 51), (52, 108), (109, 119)]
    # Lines above the first stamp go with the first message.
    assert logbook.parts(["Mill- 2A", "Temp=33"] + stamped([40, 40]))[0] == (1, 43)
    # Never more than MAX_PARTS requests at once: the parts grow instead.
    assert len(logbook.parts(stamped([40] * 12))) == logbook.MAX_PARTS

    assert not logbook.too_long(lines)
    assert logbook.too_long(["Temp=33"] * (logbook.MAX_LINES + 1))
    assert not logbook.too_long(stamped([logbook.MAX_LINES] * 2))
    assert logbook.too_long(stamped([40, logbook.MAX_LINES + 1]))


def test_a_long_stamped_paste_is_read_in_parts_at_once(monkeypatch):
    lines = stamped([50, 50])
    seen = []

    async def ask(body, parse, what, model=None):
        prompt = body["contents"][0]["parts"][0]["text"]
        numbers = [int(n) for n in re.findall(r"^(\d+)\| ", prompt, re.M)]
        seen.append((numbers[0], numbers[-1]))
        first = numbers[0]
        answer = Paste(sections=[Section(form="mill", tag="1A" if first == 1 else "1B", first_line=first,
                                         last_line=numbers[-1], date_written="12.11.2026", extra=[],
                                         values=[Value(key="pa_lop_temp", value="30", line=first + 1)])])
        return parse(answer.model_dump_json()), f"model-{first}", {"inputTokens": 10, "outputTokens": 5, "thinkingTokens": None}

    monkeypatch.setattr(extract, "ask", ask)
    answer, model, usage = asyncio.run(logbook.read(lines))
    # Each part is sent with the paste's own line numbers, so the answers go together as they are.
    assert sorted(seen) == [(1, 51), (52, 102)]
    assert [(s.tag, s.first_line) for s in answer.sections] == [("1A", 1), ("1B", 52)]
    assert (model, usage) == ("model-1", {"inputTokens": 20, "outputTokens": 10, "thinkingTokens": None})
    records, notes = logbook.records(answer, lines, TODAY, TODAY)
    assert [(r["section"], r["date"], r["values"]) for r in records] == [
        ("mill_1a", "2026-11-12", {"pa_lop_temp": "30"}), ("mill_1b", "2026-11-12", {"pa_lop_temp": "30"})]


def test_one_part_that_cannot_be_read_fails_the_whole_paste(monkeypatch):
    async def ask(body, parse, what, model=None):
        if "\n52| " in body["contents"][0]["parts"][0]["text"]:
            raise extract.ExtractionError("The reading service failed. Try again in a minute.", status=502)
        return Paste(sections=[]), "model", {}

    monkeypatch.setattr(extract, "ask", ask)
    with pytest.raises(extract.ExtractionError):
        asyncio.run(logbook.read(stamped([50, 50])))


def test_request_carries_the_numbered_lines_the_fixed_set_and_the_schema(monkeypatch):
    text, paste = fixture(DAY_2)
    calls = []

    class Stub:
        async def post(self, url, headers=None, json=None):
            calls.append({"url": url, "body": json})
            return httpx.Response(200, json={
                "candidates": [{"content": {"parts": [{"text": paste.model_dump_json()}]}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 11556, "candidatesTokenCount": 5903}, "modelVersion": "served"})

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(extract, "MODELS", ["model-a"])
    monkeypatch.setattr(extract, "_client", lambda: Stub())
    answer, model, usage = asyncio.run(logbook.read(logbook.number_lines(text)))
    assert (answer, model, usage["outputTokens"]) == (paste, "served", 5903)

    body = calls[0]["body"]
    assert "models/model-a:generateContent" in calls[0]["url"]
    assert body["generationConfig"]["responseSchema"] == logbook.SCHEMA
    assert "FORM mill:" in body["systemInstruction"]["parts"][0]["text"]
    prompt = body["contents"][0]["parts"][0]["text"]
    assert "\n2| Tenughat TPS Generation Report on 12.11.2026\n" in prompt
    assert "\n141| Ash water pump  01 & 02  in service" in prompt


# --- the API -------------------------------------------------------------------------------------

class Reader:
    """Stands in for logbook.read: hands back the answer prepared for the text pasted."""

    def __init__(self):
        self.answers: dict[str, Paste] = {}
        self.error: extract.ExtractionError | None = None
        self.calls = 0

    def knows(self, text: str, paste: Paste) -> str:
        self.answers["\n".join(logbook.number_lines(text))] = paste
        return text

    async def read(self, lines, model=None):
        self.calls += 1
        if self.error:
            raise self.error
        return self.answers["\n".join(lines)], "test-model", {"inputTokens": 1, "outputTokens": 1, "thinkingTokens": None}


@pytest.fixture
def reader(monkeypatch) -> Reader:
    fake = Reader()
    monkeypatch.setattr(logbook, "read", fake.read)
    return fake


@pytest.fixture
def api(monkeypatch, reader):
    monkeypatch.setattr(main, "db", AsyncMongoMockClient()["ttps_test"])
    monkeypatch.setattr(main, "_ist_now", lambda: NOW)
    with TestClient(main.app) as c:
        c.user = sign_in(c, "admin")
        yield c


def paste(api, reader, name: str = DAY_1, **body):
    text, answer = fixture(name)
    return api.post("/api/logs", json={"text": reader.knows(text, answer), **body})


def next_day(reader, changes: dict[str, tuple[str, str]], new_date: str = "12") -> str:
    """Day 1's messages again, dated the next day, with some values changed.
    changes: text to replace -> (replacement, the section.key it is the value of)."""
    text, answer = fixture(DAY_1)
    text = text.replace("11-11-2026", f"{new_date}-11-2026").replace("11/11/2026", f"{new_date}/11/2026")
    for section in answer.sections:
        section.date_written = section.date_written.replace("11-11", f"{new_date}-11").replace("11/11", f"{new_date}/11")
    for old, (new, where) in changes.items():
        assert text.count(old) == 1, old
        text = text.replace(old, new)
        form, tag, key = where.split(".")
        section = next(s for s in answer.sections if (s.form, s.tag) == (form, tag))
        value = next(v for v in section.values if v.key == key)
        value.value = re.search(r"[\d.]+$", new).group()
    return reader.knows(text, answer)


def sections(response) -> dict[str, dict]:
    assert response.status_code == 200, response.text
    return {s["id"]: s for s in response.json()["sections"]}


def test_paste_files_each_message_under_its_own_date(api, reader):
    response = paste(api, reader)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "days": [{"date": "2026-11-11", "sections": 9, "values": 169, "toCheck": 0, "undated": 0}],
        "notes": [], "model": "test-model", "usage": {"inputTokens": 1, "outputTokens": 1, "thinkingTokens": None}}

    day = api.get("/api/logs?date=2026-11-11").json()
    assert (day["date"], day["latest"], day["earlier"], day["later"], day["absent"]) == ("2026-11-11", "2026-11-11", None, None, [])
    # In the order of the forms, then by tag.
    assert [s["name"] for s in day["sections"]] == [
        "Mill 2A", "Mill 2C", "ID fan 2A", "ID fan 2B", "FD fan 2A", "FD fan 2B", "ESP 2", "Turbine side, Unit 2",
        "Stator water and CW, Unit 2"]
    mill = day["sections"][0]
    assert mill["counts"] == {"values": 27, "changed": 0, "toCheck": 0}
    assert mill["updatedBy"] == {"id": api.user["id"], "name": "Admin"}
    assert mill["raw"].startswith("Mill- 2A")
    assert {r["key"]: r["value"] for r in mill["rows"]}["hp_discharge_3"] == "45"


def test_with_no_date_the_latest_day_with_readings_is_shown(api, reader):
    empty = api.get("/api/logs").json()
    assert (empty["date"], empty["latest"], empty["sections"]) == ("2026-11-13", None, [])
    paste(api, reader, DAY_1)
    paste(api, reader, DAY_2)
    latest = api.get("/api/logs").json()
    assert (latest["date"], latest["latest"], latest["earlier"], latest["later"]) == ("2026-11-12", "2026-11-12", "2026-11-11", None)
    first = api.get("/api/logs?date=2026-11-11").json()
    assert (first["earlier"], first["later"]) == (None, "2026-11-12")
    assert api.get("/api/logs?date=12-11-2026").status_code == 400


def test_a_paste_is_compared_with_the_last_day_each_section_was_reported(api, reader):
    paste(api, reader, DAY_1)
    text = next_day(reader, {"Temp=33": ("Temp=36", "mill.2A.pa_lop_temp"),
                             "CONTROL OIL PR. --10.1KG": ("CONTROL OIL PR. --9.8", "fd_fan.2A.control_oil_pressure"),
                             "*SOT Vacuum - 230*": ("*SOT Vacuum - 230.0", "turbine.2.sot_vacuum")})
    assert api.post("/api/logs", json={"text": text}).json()["days"][0]["date"] == "2026-11-12"

    day = api.get("/api/logs?date=2026-11-12")
    today = sections(day)
    assert all(s["previousDate"] == "2026-11-11" for s in today.values())
    assert {s: v["counts"]["changed"] for s, v in today.items() if v["counts"]["changed"]} == {"mill_2a": 1, "fd_fan_2a": 1}
    rows = {r["key"]: r for r in today["mill_2a"]["rows"]}
    assert (rows["pa_lop_temp"]["value"], rows["pa_lop_temp"]["prev"], rows["pa_lop_temp"]["delta"]) == ("36", "33", 3.0)
    assert (rows["lp_discharge"]["prev"], rows["lp_discharge"]["delta"], rows["lp_discharge"]["changed"]) == ("2.3", 0.0, False)
    oil = {r["key"]: r for r in today["fd_fan_2a"]["rows"]}["control_oil_pressure"]
    assert (oil["value"], oil["prev"], oil["delta"]) == ("9.8", "10.1", -0.3)
    # 230 and 230.0 are the same reading.
    assert {r["key"]: r for r in today["turbine_2"]["rows"]}["sot_vacuum"]["changed"] is False
    # The earlier day is still compared with nothing.
    assert all(s["previousDate"] is None for s in sections(api.get("/api/logs?date=2026-11-11")).values())


def test_the_other_day_can_be_chosen_and_missing_messages_are_named(api, reader):
    paste(api, reader, DAY_1)                                     # 11 Nov: Unit 2 mills, fans, ESP, turbine...
    api.post("/api/logs", json={"text": next_day(reader, {"Temp=33": ("Temp=36", "mill.2A.pa_lop_temp")}, "10")})
    paste(api, reader, DAY_2)                                     # 12 Nov: other messages altogether

    day = api.get("/api/logs?date=2026-11-12").json()
    assert day["with"] is None
    assert all(s["previousDate"] is None for s in day["sections"])
    # Reported the day before and not today.
    assert [a["name"] for a in day["absent"]] == ["Mill 2A", "Mill 2C", "ID fan 2A", "ID fan 2B", "FD fan 2A",
                                                  "FD fan 2B", "ESP 2", "Turbine side, Unit 2",
                                                  "Stator water and CW, Unit 2"]
    assert {a["date"] for a in day["absent"]} == {"2026-11-11"}

    # 10 Nov compared with a later day of one's choosing.
    chosen = api.get("/api/logs?date=2026-11-10&with=2026-11-11").json()
    assert chosen["with"] == "2026-11-11" and chosen["absent"] == []
    mill = next(s for s in chosen["sections"] if s["id"] == "mill_2a")
    assert mill["previousDate"] == "2026-11-11"
    assert {r["key"]: r for r in mill["rows"]}["pa_lop_temp"]["delta"] == 3.0   # 36 on the 10th, 33 on the 11th
    assert api.get("/api/logs?date=2026-11-10&with=nonsense").status_code == 400


def piece(reader, lines: list[str], values: list[tuple[str, str, int]], form="mill", tag="2A", written="") -> str:
    """One piece of a message, with the answer the reader gives for it."""
    text = "\n".join(lines)
    return reader.knows(text, Paste(sections=[Section(
        form=form, tag=tag, first_line=1, last_line=len(lines), date_written=written, extra=[],
        values=[Value(key=k, value=v, line=n) for k, v, n in values])]))


def test_a_day_pasted_in_pieces_adds_up(api, reader):
    # The morning's first piece: the generation report and half of a mill's block.
    first = piece(reader, ["Mill- 2A    11-11-2026", "LPD-Main-2.3/B.S-19,26", "Temp=33"],
                  [("lp_pump", "Main", 2), ("lp_discharge", "2.3", 2), ("bs_1", "19", 2), ("bs_2", "26", 2),
                   ("pa_lop_temp", "33", 3)], written="11-11-2026")
    assert api.post("/api/logs", json={"text": first, "date": "2026-11-13"}).json()["days"] == [
        {"date": "2026-11-11", "sections": 1, "values": 5, "toCheck": 0, "undated": 0}]
    # The rest of the block arrives later, without the heading: filed under the day chosen for undated pieces.
    rest = piece(reader, ["Mill Main motor= DE-63/NDE-34", "Grease press=8.0 kg."],
                 [("motor_de", "63", 1), ("motor_nde", "34", 1), ("grease_pressure", "8.0", 2)])
    assert api.post("/api/logs", json={"text": rest, "date": "2026-11-11"}).json()["days"][0]["undated"] == 1

    mill = sections(api.get("/api/logs?date=2026-11-11"))["mill_2a"]
    assert {r["key"]: r["value"] for r in mill["rows"]} == {
        "lp_pump": "Main", "lp_discharge": "2.3", "bs_1": "19", "bs_2": "26", "pa_lop_temp": "33",
        "motor_nde": "34", "motor_de": "63", "grease_pressure": "8.0"}
    assert mill["dated"] is True                                  # an undated piece does not undo that
    assert mill["messages"] == 2 and mill["raw"].startswith("Mill- 2A") and mill["raw"].endswith("8.0 kg.")
    assert {r["key"]: r["src"] for r in mill["rows"]}["motor_de"] == "Mill Main motor= DE-63/NDE-34"

    # The same piece pasted again changes nothing.
    api.post("/api/logs", json={"text": rest, "date": "2026-11-11"})
    again = sections(api.get("/api/logs?date=2026-11-11"))["mill_2a"]
    assert (again["rows"], again["messages"], again["missed"]) == (mill["rows"], 2, [])
    assert asyncio.run(main.db["logs"].count_documents({})) == 1


def test_a_reading_pasted_again_later_wins(api, reader):
    paste(api, reader, DAY_1)
    api.put("/api/logs/2026-11-11/mill_2a", json={"key": "lp_discharge", "value": "2.5"})
    # The sender corrects a value and sends the line again.
    fix = piece(reader, ["Mill- 2A    11-11-2026", "LPD-Main-2.4"], [("lp_pump", "Main", 2), ("lp_discharge", "2.4", 2)],
                written="11-11-2026")
    api.post("/api/logs", json={"text": fix})
    day = sections(api.get("/api/logs?date=2026-11-11"))
    rows = {r["key"]: r for r in day["mill_2a"]["rows"]}
    assert (rows["lp_discharge"]["value"], rows["lp_discharge"]["edited"], rows["lp_discharge"]["src"]) == \
        ("2.4", False, "LPD-Main-2.4")
    assert rows["hp_discharge_3"]["value"] == "45"                 # the rest of the section is untouched
    assert len(day) == 9 and day["mill_2a"]["counts"]["values"] == 27


def test_a_value_found_later_clears_its_check(api, reader):
    wrong = piece(reader, ["Mill- 2A    11-11-2026", "Temp=33"], [("pa_lop_temp", "38", 2)], written="11-11-2026")
    api.post("/api/logs", json={"text": wrong})
    row = {r["key"]: r for r in sections(api.get("/api/logs?date=2026-11-11"))["mill_2a"]["rows"]}["pa_lop_temp"]
    assert (row["check"], row["src"]) == (logbook.NOT_FOUND, "")
    right = piece(reader, ["Mill- 2A    11-11-2026", "Temp=33", ""], [("pa_lop_temp", "33", 2)], written="11-11-2026")
    api.post("/api/logs", json={"text": right})
    row = {r["key"]: r for r in sections(api.get("/api/logs?date=2026-11-11"))["mill_2a"]["rows"]}["pa_lop_temp"]
    assert (row["value"], row["check"], row["src"]) == ("33", None, "Temp=33")


def test_two_pastes_for_one_section_at_once_lose_nothing(api, reader):
    a = piece(reader, ["Mill- 2A    11-11-2026", "Temp=33"], [("pa_lop_temp", "33", 2)], written="11-11-2026")
    b = piece(reader, ["Mill- 2A    11-11-2026", "Grease press=8.0 kg."], [("grease_pressure", "8.0", 2)],
              written="11-11-2026")

    async def both():
        records = []
        for text in (a, b):
            lines = logbook.number_lines(text)
            records += logbook.records(reader.answers["\n".join(lines)], lines, TODAY, TODAY)[0]
        stamp = {"updatedAt": "now", "updatedBy": None, "model": "m"}
        await asyncio.gather(*(main.db["logs"].update_one({"date": r["date"], "section": r["section"]},
                                                          logbook.update(r, stamp), upsert=True) for r in records))

    asyncio.run(both())
    record = asyncio.run(main.db["logs"].find_one({}, {"_id": 0}))
    assert record["values"] == {"pa_lop_temp": "33", "grease_pressure": "8.0"}
    assert len(record["pieces"]) == 2


def test_readings_outside_the_set_add_up_over_the_day(api, reader):
    def other(line: str, label: str, value: str) -> str:
        text = f"Boiler 13.11.2026\n{line}"
        return reader.knows(text, Paste(sections=[Section(
            form="other", tag="", first_line=1, last_line=2, date_written="13.11.2026", values=[],
            extra=[Extra(label=label, value=value, line=2)])]))

    api.post("/api/logs", json={"text": other("Drum level - 12", "Drum level", "12")})
    api.post("/api/logs", json={"text": other("Furnace draft - 5", "Furnace draft", "5")})
    api.post("/api/logs", json={"text": other("Furnace draft - 5", "Furnace draft", "5")})
    section = sections(api.get("/api/logs?date=2026-11-13"))["other"]
    assert (section["name"], section["rows"]) == ("Not in the fixed set", [])
    assert [(e["label"], e["value"]) for e in section["extra"]] == [("Drum level", "12"), ("Furnace draft", "5")]


def test_an_undated_message_is_filed_under_the_day_given(api, reader):
    text = reader.knows("Mill- 2A\nTemp=33", Paste(sections=[Section(
        form="mill", tag="2A", first_line=1, last_line=2, date_written="",
        values=[Value(key="pa_lop_temp", value="33", line=2)], extra=[])]))
    assert api.post("/api/logs", json={"text": text, "date": "2026-11-09"}).json()["days"] == [
        {"date": "2026-11-09", "sections": 1, "values": 1, "toCheck": 0, "undated": 1}]
    assert api.post("/api/logs", json={"text": text}).json()["days"][0]["date"] == "2026-11-13"
    assert api.post("/api/logs", json={"text": text, "date": "2026-11-20"}).status_code == 400
    assert sections(api.get("/api/logs?date=2026-11-09"))["mill_2a"]["dated"] is False


def test_what_cannot_be_read_is_refused_without_storing_anything(api, reader):
    assert api.post("/api/logs", json={}).status_code == 400
    assert api.post("/api/logs", json={"text": "   \n "}).status_code == 400
    long = api.post("/api/logs", json={"text": "x" * (logbook.MAX_CHARS + 1)})
    assert long.status_code == 413 and "a few at a time" in long.json()["detail"]
    lines = api.post("/api/logs", json={"text": "Temp=33\n" * (logbook.MAX_LINES + 1)})
    assert lines.status_code == 413 and "more than can be read in one go" in lines.json()["detail"]
    assert reader.calls == 0

    nothing = api.post("/api/logs", json={"text": reader.knows("Good morning", Paste(sections=[]))})
    assert (nothing.status_code, nothing.json()["detail"]) == (422, "No readings were found in what was pasted.")
    reader.error = extract.ExtractionError("GEMINI_API_KEY is not set on the server.", status=503)
    assert paste(api, reader).status_code == 503
    assert asyncio.run(main.db["logs"].count_documents({})) == 0


def test_a_value_can_be_corrected_or_removed_by_hand(api, reader):
    text, answer = fixture(DAY_1)
    answer.sections[0].values[1].value = "9.9"                    # the model misread Mill 2A's LP discharge
    api.post("/api/logs", json={"text": reader.knows(text, answer)})
    mill = sections(api.get("/api/logs?date=2026-11-11"))["mill_2a"]
    # 9.9 is not in the message, and the 2.3 that is there went unused.
    assert mill["counts"]["toCheck"] == 2
    assert {r["key"]: r["check"] for r in mill["rows"]}["lp_discharge"] == logbook.NOT_FOUND
    assert [m["numbers"] for m in mill["missed"]] == [["2.3"]]

    fixed = sections(api.put("/api/logs/2026-11-11/mill_2a", json={"key": "lp_discharge", "value": " 2.3 "}))["mill_2a"]
    row = {r["key"]: r for r in fixed["rows"]}["lp_discharge"]
    assert (row["value"], row["num"], row["check"], row["edited"], row["src"]) == ("2.3", 2.3, None, True, "")
    assert fixed["counts"] == {"values": 27, "changed": 0, "toCheck": 0} and fixed["missed"] == []

    removed = sections(api.put("/api/logs/2026-11-11/mill_2a", json={"key": "lp_pump", "value": ""}))["mill_2a"]
    assert "lp_pump" not in {r["key"] for r in removed["rows"]} and removed["counts"]["values"] == 26

    assert api.put("/api/logs/2026-11-11/mill_2a", json={"key": "scoop", "value": "1"}).status_code == 400
    assert api.put("/api/logs/2026-11-11/mill_2a", json={"value": "1"}).status_code == 400
    assert api.put("/api/logs/2026-11-11/mill_9z", json={"key": "noise", "value": "1"}).status_code == 404
    assert api.put("/api/logs/2026-11-10/mill_2a", json={"key": "noise", "value": "1"}).status_code == 404


def test_a_section_that_has_been_looked_at_can_be_marked_checked(api, reader):
    text, answer = fixture(DAY_1)
    answer.sections[0].values[1].value = "9.9"
    api.post("/api/logs", json={"text": reader.knows(text, answer)})
    checked = sections(api.put("/api/logs/2026-11-11/mill_2a", json={"checked": True}))["mill_2a"]
    assert checked["counts"]["toCheck"] == 0 and checked["missed"] == []
    row = {r["key"]: r for r in checked["rows"]}["lp_discharge"]
    assert (row["value"], row["check"], row["edited"]) == ("9.9", None, False)     # the value itself is left alone


def test_without_number_takes_a_typed_number_off_the_passed_over_ones():
    missed = [{"line": "a", "numbers": ["45", "2.30"]}, {"line": "b", "numbers": ["2.3"]}]
    assert logbook.without_number(missed, "2.3") == [{"line": "a", "numbers": ["45"]}, {"line": "b", "numbers": ["2.3"]}]
    assert logbook.without_number(missed, "Main") == missed
    assert logbook.without_number([{"line": "b", "numbers": ["2.3"]}], "2.3") == []


def test_a_section_pasted_by_mistake_can_be_removed(api, reader):
    paste(api, reader)
    left = sections(api.delete("/api/logs/2026-11-11/esp_2"))
    assert "esp_2" not in left and len(left) == 8
    assert api.delete("/api/logs/2026-11-11/esp_2").status_code == 404
    assert asyncio.run(main.db["logs"].count_documents({})) == 8


def test_only_an_editor_changes_readings_and_anyone_signed_in_reads_them(api, reader):
    paste(api, reader)
    with TestClient(main.app) as viewer:
        assert viewer.get("/api/logs").status_code == 401
        sign_in(viewer, "viewer")
        assert len(viewer.get("/api/logs?date=2026-11-11").json()["sections"]) == 9
        text, answer = fixture(DAY_2)
        for response in (
            viewer.post("/api/logs", json={"text": reader.knows(text, answer)}),
            viewer.put("/api/logs/2026-11-11/mill_2a", json={"key": "noise", "value": "1"}),
            viewer.delete("/api/logs/2026-11-11/mill_2a"),
        ):
            assert (response.status_code, response.json()) == (403, {"detail": "Your access is view only"})
    assert reader.calls == 1
    assert asyncio.run(main.db["logs"].count_documents({})) == 9


def test_pastes_edits_and_removals_are_in_the_activity_log(api, reader):
    paste(api, reader)
    api.put("/api/logs/2026-11-11/mill_2a", json={"key": "lp_discharge", "value": "2.4"})
    api.put("/api/logs/2026-11-11/mill_2a", json={"key": "lp_discharge", "value": "2.4"})   # no change, no line
    api.delete("/api/logs/2026-11-11/dummy")
    api.delete("/api/logs/2026-11-11/fd_fan_2b")
    activity = [(a["action"], a["text"]) for a in api.get("/api/auth/activity").json()]
    assert activity[:3] == [
        ("logs_removed", "Removed FD fan 2B readings for 11 Nov 2026"),
        ("logs_edited", "Edited Mill 2A readings for 11 Nov 2026: LP discharge pressure"),
        ("logs_pasted", "Pasted readings for 11 Nov 2026: 169 values"),
    ]


def test_the_collection_has_one_record_per_day_and_section(api, reader):
    paste(api, reader)
    info = asyncio.run(main.db["logs"].index_information())
    assert any(list(i["key"]) == [("date", 1), ("section", 1)] and i.get("unique") for i in info.values())
    record = asyncio.run(main.db["logs"].find_one({"date": "2026-11-11", "section": "id_fan_2a"}, {"_id": 0}))
    assert record["values"] == {"motor_de": "47", "motor_nde": "42", "coupling_pressure": "0.70", "coupling_temp": "46",
                                "fan_de": "35", "fan_nde": "46", "scoop": "100"}
    assert (record["form"], record["tag"], record["model"], record["updatedBy"]["name"]) == ("id_fan", "2A", "test-model", "Admin")
    assert record["src"]["coupling_temp"] == "HYDRO COUPLING PR. /TEMP.__  0.70kg/46 C"
    # The piece of message it came from, with the heading that dates it.
    assert record["pieces"] == ["*UNIT-#02                  11-11-2026\n_ID Fan- 2 A_\nMotor bearing temp\nDE.__47 C\n"
                                "NDE__42 C\nHYDRO COUPLING PR. /TEMP.__  0.70kg/46 C\n\nFAN BEARING TEMP.\nDE.__35 C\n"
                                "NDE__46 C\nSCOOP_ 100"]
    # Nothing of the daily entries or the report pages is touched.
    assert asyncio.run(main.db["entries"].count_documents({})) == 0
    assert asyncio.run(main.db["reports"].count_documents({})) == 0
