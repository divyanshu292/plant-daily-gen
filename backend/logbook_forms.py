"""The fixed set of readings taken from the WhatsApp messages, form by form.

Staff of each area send the same readings every day, each in their own layout.
A form is one such message, or one piece of equipment in it: its fields are the
keys everything is stored and compared under, so they do not change from day
to day whatever the layout of the message. logbook.py sends this list to the
model with every paste and accepts no key that is not in it; a reading with no
field here comes back as an "extra" and is shown as such, which is the sign
that a field should be added.

`hint` is how the reading is written in the messages. It is for the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    unit: str = ""
    hint: str = ""
    text: bool = False   # a word or a list ("Main", "1A&2A"), never compared as a number
    group: str = ""      # sub-heading inside the form


@dataclass(frozen=True)
class Form:
    key: str
    name: str            # "Mill"
    title: str           # the section's name, with {tag} for the equipment or unit
    about: str           # how to recognise the message, for the model
    fields: tuple
    tag: str = ""        # what tells two of these apart ("" when there is one a day)
    tag_re: str = ""     # what a tag looks like once tidied (upper case, no spaces or leading zeros)

    def field(self, key: str):
        return next((f for f in self.fields if f.key == key), None)

    def clean_tag(self, raw: str):
        """The tag as stored ('2 a' -> '2A', '01' -> '1'), or None when it is not one."""
        if not self.tag:
            return ""
        tag = re.sub(r"[^A-Za-z0-9]", "", raw or "").upper().lstrip("0")
        return tag if re.fullmatch(self.tag_re, tag) else None


def F(key, label, unit="", hint="", text=False, group=""):
    return Field(key, label, unit, hint, text, group)


def _pair(key, label, unit, hint, group="", ends=("nde", "de")):
    """The same reading at two ends of a shaft."""
    return tuple(F(f"{key}_{end}", f"{label} {end.upper()}", unit, hint, group=group) for end in ends)


MILL = Form(
    "mill", "Mill", "Mill {tag}",
    "Mill readings, one block per mill, headed 'Mill- 2A' or 'Mill-1B'. Unit 1 and Unit 2 staff lay the "
    "same readings out differently.",
    tag="the mill's number: unit digit and letter, e.g. 2A", tag_re=r"[12][A-F]",
    fields=(
        F("lp_pump", "LP pump in service", hint="the word after LPD: 'LPD-Main-2.3' is Main, 'LPD-Standby-3.1' is Standby",
          text=True, group="Lube oil"),
        F("lp_discharge", "LP discharge pressure", "kg/cm²", "'LPD-Main-2.3' is 2.3; 'L P discharge : 5.7'", group="Lube oil"),
        F("hp_pump", "HP pump in service", hint="the word after HPS: 'HPS-Main-1.6' is Main", text=True, group="Lube oil"),
        F("hp_suction", "HP suction pressure", "kg/cm²", "'HPS-Main-1.6' is 1.6; 'HP suction :- 1.4'", group="Lube oil"),
        *(F(f"hp_discharge_{n}", f"HP discharge pressure {n}", "kg/cm²",
            "'HPD- 30,41,45,41' or 'HP discharge :-42, 36, 33, 41': four values, 1 to 4 in the order written",
            group="Lube oil") for n in (1, 2, 3, 4)),
        *(F(f"bs_{n}", f"B&S {n}", "", "'B.S-19,26' or 'B&S:- 24/16': two values, 1 and 2 in the order written",
            group="Lube oil") for n in (1, 2)),
        F("lube_oil_temp", "Lube oil temperature", "°C", "'Temp-40' at the end of the LPD/HPD line; 'Lub oil tem. : 45'",
          group="Lube oil"),
        *_pair("flow", "Bearing oil flow", "", "'Flow-NDE-7×4/DE-7×4'; a bare 'Flow :-26/29' is NDE then DE", "Lube oil"),
        F("pa_lop", "PA fan lube oil pump in service", hint="the letter after LOP: 'PA FAN LOP -A-Press=1.1' is A",
          text=True, group="PA fan"),
        F("pa_lop_pressure", "PA fan lube oil pressure", "kg/cm²", "'PA FAN LOP -A-Press=1.1' is 1.1; 'Lop:-A - 1.18'",
          group="PA fan"),
        F("pa_lop_temp", "PA fan lube oil temperature", "°C",
          "'Temp=33' on the line under the PA fan LOP line; 'Tem. :- 34' on the PA fan line", group="PA fan"),
        *_pair("pa_motor", "PA fan motor bearing temperature", "°C",
               "'P.A FAN Motor= NDE- 50/DE-49'; 'PA fan motor brg.'; a 'Motor brg.tem.' line directly under the PA fan line",
               "PA fan"),
        *_pair("pa_fan", "PA fan bearing temperature", "°C", "'FAN Brg.Temp= DE-48/NDE-35'; 'Fan brg.tem.'; 'PA fan brg. Tem.'",
               "PA fan"),
        *_pair("motor", "Main motor bearing temperature", "°C",
               "'Mill Main motor= DE-63/NDE-34'; 'Main motor brg.tem.'; 'Main motor tem.'", "Main motor"),
        *_pair("cooler", "Motor cooler temperature", "°C", "'Motor cooler tem.NDE.:-32 DE:-44'", "Main motor"),
        F("grease_pressure", "Grease pump pressure", "kg",
          "'Grease press=8.0 kg'; the first value of 'Grease pump pr.: 10.0/6.0'", group="Grease and reducer"),
        F("atomising_air", "Atomising air pressure", "kg",
          "'Automising air pr.-6.8'; the second value of 'Grease pump pr.: 10.0/6.0'", group="Grease and reducer"),
        F("reducer_pressure", "Reducer oil pressure", "kg/cm²",
          "'Press-2.0' on the line under Reducer Flow; the first value of 'Reducer oil pressure :- 1.5/4000'",
          group="Grease and reducer"),
        F("reducer_flow", "Reducer oil flow", "",
          "'Reducer Flow- 42×100' is 42×100; the second value of 'Reducer oil pressure :- 1.5/4000'",
          group="Grease and reducer"),
        F("reducer_temp", "Reducer oil temperature", "°C", "'Temp.-70' after the reducer pressure; 'Reducer oil tem.:- 71'",
          group="Grease and reducer"),
        F("noise", "Noise level", "%", "'Noise level Mill 1A:- 17 to 18 %' is 17 to 18", text=True, group="Grease and reducer"),
    ),
)

ESP = Form(
    "esp", "ESP", "ESP {tag}",
    "Electrostatic precipitator readings, headed 'E.S.P - 2'. A table: each field (1A to 7D) has a current "
    "in mA and then a voltage in kV, two fields to a line: '4A.140 34  4C30  27' is 4A 140 mA 34 kV and "
    "4C 30 mA 27 kV; '6D240 20' is 6D 240 mA 20 kV.",
    tag="the unit's number, 1 or 2", tag_re=r"[12]",
    fields=(
        *(f for p in "ABCD" for n in range(1, 8) for f in (
            F(f"{n}{p.lower()}_ma", f"Field {n}{p} current", "mA", group=f"Pass {p}"),
            F(f"{n}{p.lower()}_kv", f"Field {n}{p} voltage", "kV", group=f"Pass {p}"),
        )),
        F("under_voltage", "Fields under voltage", hint="'U/V-1A, 7A,1B,3B' is 1A, 7A,1B,3B", text=True, group="Remarks"),
        F("remarks", "Rapping motors and hopper heaters",
          hint="the sentence about E.E.R.M, C.E.R.M and hopper heaters, whole", text=True, group="Remarks"),
    ),
)

ID_FAN = Form(
    "id_fan", "ID fan", "ID fan {tag}",
    "Induced draught fan readings, one block per fan, headed 'ID Fan- 2 A'. They come in one message with "
    "the FD fans.",
    tag="the fan's number: unit digit and letter, e.g. 2A", tag_re=r"[12][A-C]",
    fields=(
        *_pair("motor", "Motor bearing temperature", "°C", "under 'Motor bearing temp': 'DE.__47 C', 'NDE__42 C'",
               ends=("de", "nde")),
        F("coupling_pressure", "Hydro coupling pressure", "kg", "the first value of 'HYDRO COUPLING PR. /TEMP.__ 0.70kg/46 C'"),
        F("coupling_temp", "Hydro coupling temperature", "°C", "the second value of the same line"),
        *_pair("fan", "Fan bearing temperature", "°C", "under 'FAN BEARING TEMP': 'DE.__35 C', 'NDE__46 C'",
               ends=("de", "nde")),
        F("scoop", "Scoop", "%", "'SCOOP_ 100'"),
    ),
)

FD_FAN = Form(
    "fd_fan", "FD fan", "FD fan {tag}",
    "Forced draught fan readings, one block per fan, headed 'FD FAN 2 A'.",
    tag="the fan's number: unit digit and letter, e.g. 2A", tag_re=r"[12][A-C]",
    fields=(
        *_pair("motor", "Motor bearing temperature", "°C", "under 'MOTOR BEARING TEMP': 'DE --33 C', 'NDE.-37 C'",
               ends=("de", "nde")),
        *_pair("fan", "Fan bearing temperature", "°C", "under 'FAN BEARING TEMP'", ends=("de", "nde")),
        F("control_oil_pressure", "Control oil pressure", "kg", "'CONTROL OIL PR. --10.1KG'"),
        F("lube_oil_pressure", "Lube oil pressure", "kg", "the first value of 'LUBE OIL PR./TEMP -- 1.4 Kg/ 38 C'"),
        F("lube_oil_temp", "Lube oil temperature", "°C", "the second value of the same line"),
    ),
)

STATOR_CW = Form(
    "stator_cw", "Stator water and CW", "Stator water and CW, Unit {tag}",
    "A short message headed with the unit and the date, giving stator water and CW (circulating water) "
    "pressures and temperatures, each as two values with a slash: 'Stator Water Pressure = 2.8/1.0'.",
    tag="the unit's number, 1 or 2", tag_re=r"[12]",
    fields=tuple(
        F(f"{key}_{n}", f"{label} {n}", unit, f"'{hint}': two values, 1 and 2 in the order written", group=group)
        for key, label, unit, hint, group in (
            ("stator_pressure", "Stator water pressure", "kg/cm²", "Stator Water Pressure = 2.8/1.0", "Stator water"),
            ("stator_temp", "Stator water temperature", "°C", "Stator Water Temp. = 36/41", "Stator water"),
            ("cw_in_pressure", "CW inlet pressure", "kg/cm²", "CW Pressure I/L= 1.2/1.4", "Circulating water"),
            ("cw_in_temp", "CW inlet temperature", "°C", "CW Temp. I/L = 26/----", "Circulating water"),
            ("cw_out_pressure", "CW outlet pressure", "kg/cm²", "CW Pressure O/L=0.3/0", "Circulating water"),
            ("cw_out_temp", "CW outlet temperature", "°C", "CW Temp. O/L= 40/37", "Circulating water"),
        )
        for n in (1, 2)
    ),
)

TURBINE = Form(
    "turbine", "Turbine side", "Turbine side, Unit {tag}",
    "The turbine side report, headed 'Unit-No - 02 Report': oil pumps, feed pumps, seal oil. The pump's "
    "letter picks the field: BFP 2A is BFP A of Unit 2.",
    tag="the unit's number, 1 or 2", tag_re=r"[12]",
    fields=(
        F("eop_current", "EOP current", "A", "the first value of 'EOP - 32A/5.2kg'", group="Oil pumps"),
        F("eop_pressure", "EOP pressure", "kg", "the second value of the same line", group="Oil pumps"),
        F("sop_current", "SOP current", "A", "the first value of 'SOP DC 18.5A/10.3kg'", group="Oil pumps"),
        F("sop_pressure", "SOP pressure", "kg", "the second value of the same line", group="Oil pumps"),
        *(f for p in "ABC" for f in (
            F(f"bfp_{p.lower()}_oil_temp", f"BFP {p} working oil temperature", "°C",
              f"'Working Oil Temp of BFP 2{p}=82°C'", group="Feed and condensate pumps"),
            F(f"bfp_{p.lower()}_lube_pressure", f"BFP {p} lube oil pressure", "kg/cm²",
              f"'Lube Oil Pr 2{p} = 2.8'", group="Feed and condensate pumps"),
        )),
        *(F(f"cep_{p.lower()}_thrust_temp", f"CEP {p} thrust bearing temperature", "°C",
            f"'Thrust Bearing Temp of CEP 2{p} :- 59°C'", group="Feed and condensate pumps") for p in "ABC"),
        F("sot_vacuum", "SOT vacuum", "", "'SOT Vacuum - 230' is 230", group="Oil system"),
        F("mot_filter_choking", "MOT thrust bearing filter choking", "%", "'MOT Thrust brg filter chocking - 50%'",
          group="Oil system"),
        F("expansion_tank_vacuum", "Expansion tank vacuum", "", "'Expansion Tank Vacuum:- -640' is -640", group="Oil system"),
        F("seal_oil_flow_te", "Seal oil flow TE", "", "the first value of 'S. O. Flow TE/EE - 38/26'", group="Oil system"),
        F("seal_oil_flow_ee", "Seal oil flow EE", "", "the second value of the same line", group="Oil system"),
        F("seal_oil_temp", "Seal oil temperature after cooler", "°C", "'S.O.Temp. after Cooler- 46°C'", group="Oil system"),
        F("seal_oil_exhaust_fan", "Seal oil exhaust fan in service", hint="'S. O. Exhaust fan in service -B' is B",
          text=True, group="Oil system"),
        F("control_oil_pressure", "Control oil pressure", "kg/cm²", "'Control Oil Pr= 8.4'", group="Oil system"),
    ),
)

GENERATION = Form(
    "generation", "Generation report", "Generation report",
    "The morning generation report, 'Tenughat TPS Generation Report on 12.11.2026', with one value for "
    "each unit (U#1, U#2).",
    fields=(
        *(F(f"load_u{u}", f"Load at 06:00, Unit {u}", "MW", f"under 'Load at 6:00Hrs': 'U# {u}: 154MW'", group="Load and generation")
          for u in (1, 2)),
        *(F(f"gen_u{u}", f"Generation, Unit {u}", "MU", f"'Gen.U#{u}=3.47MU'", group="Load and generation") for u in (1, 2)),
        *(F(f"plf_u{u}", f"PLF, Unit {u}", "%", f"'PLF (U#{u}) =68.85%'", group="PLF") for u in (1, 2)),
        F("plf_station", "PLF, station", "%", "'Stn.PLF = 70.63%'", group="PLF"),
        F("mcg", "Month cumulative generation", "MU", "the first value of 'MCG/PLF=79.97MU/72.12%'", group="PLF"),
        F("month_plf", "Month PLF", "%", "the second value of the MCG/PLF line", group="PLF"),
        F("ycg", "Year cumulative generation", "MU", "the first value of 'YCG/PLF=1521.54MU/67.09%'", group="PLF"),
        F("year_plf", "Year PLF", "%", "the second value of the YCG/PLF line", group="PLF"),
        *(F(f"h2_u{u}", f"H2 consumption, Unit {u}", "", f"'H2 Consu. U#{u}=4'", group="Hydrogen") for u in (1, 2)),
        *(F(f"purging_u{u}", f"Purging, Unit {u}", "", f"'Purging: U#{u} =0'", group="Hydrogen") for u in (1, 2)),
    ),
)

SILO = Form(
    "silo", "Silo system", "Silo system",
    "The ash silo report, headed '(Silo System)': running hours of each path, bulkers and hywas loaded, "
    "silo levels.",
    fields=(
        *(F(f"run_u{u}_{p.lower()}", f"Unit {u} path {p} running hours", "Hrs",
            f"under 'System Running Hours', 'Unit#0{u}': 'Path-{p} =24:00 Hrs' is 24:00", text=True, group="Running hours")
          for u in (1, 2) for p in "AB"),
        *(F(f"bulkers_s{s}_{mt}", f"Silo {s} bulkers, {mt} MT", "Nos",
            f"under 'Silo#{s}(Bulkers)': '60 MT= 06 Nos and 40 MT= 10 Nos' is 06 for 60 MT and 10 for 40 MT",
            group="Dry fly ash") for s in (1, 2) for mt in (60, 40)),
        F("bulkers_total", "Bulkers loaded, total", "Nos", "'Total Bulkers loaded:- 16 Nos'", group="Dry fly ash"),
        *(F(f"hywa_s{s}", f"Silo {s} hywas", "Nos", f"'Silo#{s} (Hywa): - 33 Nos'", group="Conditioned ash") for s in (1, 2)),
        F("hywa_total", "Hywas loaded, total", "Nos", "'Total Hywa loaded: - 38 Nos'", group="Conditioned ash"),
        *(F(f"level_s{s}", f"Silo {s} level at 06:00", "M", f"under 'Level at 06:00 Hrs': 'Silo-{s} = 04.80 M'", group="Level")
          for s in (1, 2)),
    ),
)

CHEMICAL = Form(
    "chemical", "Chemical report", "Chemical report",
    "The chemistry lab's report, headed 'Chemical Report': a numbered list, most items with one value "
    "for each unit (U#1, U#2).",
    fields=(
        *(F(f"silica_u{u}", f"Boiler silica, Unit {u}", "", f"under 'Boiler Silica': 'U#{u}=0.27'", group="Water and steam")
          for u in (1, 2)),
        *(F(f"cation_u{u}", f"Cation conductivity, Unit {u}", "", "under 'Cation Conductivity'; may be a word such as Ext",
            group="Water and steam") for u in (1, 2)),
        *(F(f"dew_point_u{u}", f"Hydrogen dew point, Unit {u}", "", "under 'Hydrogen Dew point': 'U#2= -9.3' is -9.3",
            group="Water and steam") for u in (1, 2)),
        *(F(f"mot_u{u}", f"MOT, Unit {u}", "", f"under 'MOT': 'U#{u}= 81'", group="Water and steam") for u in (1, 2)),
        *(F(f"o2_u{u}_{p.lower()}_{side}", f"Flue gas O2, Unit {u} path {p} {name}", "%",
            f"under 'Flue Gas', 'U#{u}(O2)': 'Path {p} I/L=4.8, O/L=5.4' is 4.8 inlet and 5.4 outlet", group="Flue gas")
          for u in (1, 2) for p in "AB" for side, name in (("in", "inlet"), ("out", "outlet"))),
        *(f for kind, name in (("fly", "fly ash"), ("bottom", "bottom ash")) for u in (1, 2) for f in (
            F(f"uc_{kind}_u{u}", f"Unburnt carbon in {name}, Unit {u}", "%",
              f"under 'U/C in {name.title()}': 'U#{u}=5.08(S.Blackish)' is 5.08", group="Ash and coal"),
            F(f"{kind}_colour_u{u}", f"Colour of {name}, Unit {u}",
              hint="the word in brackets after the unburnt carbon value: S.Blackish", text=True, group="Ash and coal"),
        )),
        F("gcv", "GCV of coal", "kcal/kg", "'GCV of coal= 3597'", group="Ash and coal"),
        F("gcv_date", "GCV sample date", hint="the date written under the GCV, as written: 10.11.2026", text=True,
          group="Ash and coal"),
        F("ash_water_ratio", "Ash water ratio", hint="'Ash Water Ratio= 1:9' is 1:9", text=True, group="Ash and coal"),
        F("tss", "TSS", "ppm", "'TSS = 53 ppm'", group="Ash and coal"),
    ),
)

FUEL_OIL = Form(
    "fuel_oil", "Fuel oil", "Fuel oil",
    "The fuel oil pump house message: 'D.O.T Level', H.F.O pumps in service and available, with the "
    "pressure and current of each pump in service (pumps 1A, 1B, 2A, 2B).",
    fields=(
        F("dot_level", "DOT level", "M", "'D.O.T Level-2.98M'"),
        F("hfo_service", "HFO pumps in service", hint="'H.F.O Pump Service-1A&2A' is 1A&2A", text=True),
        F("hfo_available", "HFO pumps available", hint="'H.F.O Pump Available-1B&2B' is 1B&2B", text=True),
        *(F(f"hfo_pressure_{p.lower()}", f"HFO pump {p} pressure", "kg/cm²", "'Pressure-1A-12Kg/Cm2&2A-12.5Kg/Cm2' is 12 for 1A, 12.5 for 2A")
          for p in ("1A", "1B", "2A", "2B")),
        *(F(f"hfo_current_{p.lower()}", f"HFO pump {p} current", "A", "'Current-1A-18Amp&2A-23Amp' is 18 for 1A, 23 for 2A")
          for p in ("1A", "1B", "2A", "2B")),
    ),
)

DG = Form(
    "dg", "DG set", "DG {tag}",
    "The diesel generator message, one block per set, headed 'DG-01', 'DG-02'.",
    tag="the set's number, 1 or 2", tag_re=r"[1-4]",
    fields=(
        F("status", "Status", hint="what the set did: 'U/M' (under maintenance), 'Trial run taken from.C.R.'", text=True),
        F("oil_level", "Diesel oil level", "Ltr", "'oil level - 530 Ltr'"),
        F("run_time", "Run time", "Hrs", "'Time- 06-30 to 06-34' is 06-30 to 06-34", text=True),
        F("voltage", "Voltage", "V", "'Volt- 417.0'"),
        F("frequency", "Frequency", "Hz", "'Hz-49.82'"),
    ),
)

ACW = Form(
    "acw", "ACW", "ACW and CW valves",
    "The auxiliary cooling water message, headed 'A C W': for each unit the ACW pump and booster pump in "
    "service with their current in brackets, and how far CW valves 34 and 56 are open.",
    fields=(
        *(f for u in (1, 2) for f in (
            F(f"acw_pump_u{u}", f"Unit {u} ACW pump in service", hint=f"'Acw pump {u}B service (29..A)' is {u}B", text=True,
              group=f"Unit {u}"),
            F(f"acw_current_u{u}", f"Unit {u} ACW pump current", "A", f"'Acw pump {u}B service (29..A)' is 29", group=f"Unit {u}"),
            F(f"booster_pump_u{u}", f"Unit {u} booster pump in service", hint=f"'Booster pump {u}A service (248A)' is {u}A",
              text=True, group=f"Unit {u}"),
            F(f"booster_current_u{u}", f"Unit {u} booster pump current", "A", f"'Booster pump {u}A service (248A)' is 248",
              group=f"Unit {u}"),
            F(f"cw34_u{u}", f"Unit {u} CW valve 34 open", "%", f"'Unit# 0{u} CW 34-100 % Open' is 100", group=f"Unit {u}"),
            F(f"cw56_u{u}", f"Unit {u} CW valve 56 open", "%", "'56-100 %' on the line under CW 34 is 100", group=f"Unit {u}"),
        )),
        F("ash_water_pumps", "Ash water pumps in service", hint="'Ash water pump 01 & 02 in service' is 01 & 02", text=True,
          group="Ash water"),
    ),
)

# In the order the app shows them.
FORMS = (GENERATION, MILL, ID_FAN, FD_FAN, ESP, TURBINE, STATOR_CW, CHEMICAL, SILO, FUEL_OIL, DG, ACW)
BY_KEY = {form.key: form for form in FORMS}
# Readings that belong to no form are kept under this section, so nothing pasted is lost.
OTHER = "other"
OTHER_TITLE = "Not in the fixed set"


def section_id(form: Form, tag: str) -> str:
    """'mill' + '2A' -> 'mill_2a'; a form with one section a day is its own id."""
    return f"{form.key}_{tag.lower()}" if tag else form.key


def catalogue() -> str:
    """Every form and field, as the block of the prompt that defines the keys."""
    blocks = []
    for form in FORMS:
        head = f"FORM {form.key}: {form.about}"
        head += f"\n  tag: {form.tag}" if form.tag else "\n  tag: empty (one for the whole station)"
        rows = [f"  {f.key} = {f.label}" + (f" [{f.unit}]" if f.unit else "") + (f"; {f.hint}" if f.hint else "")
                for f in form.fields]
        blocks.append("\n".join([head, *rows]))
    return "\n\n".join(blocks)
