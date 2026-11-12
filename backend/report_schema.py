"""Shape of the printed TVNL "Daily System Report", as transcribed from an image.

Every cell is a string holding exactly what is printed. Numbers are parsed later
in validate.py, so a misread never gets silently "repaired" by the model and a
blank cell is simply an empty string. The field descriptions are sent to the
model as part of the JSON schema, so they double as transcription instructions.
"""

from pydantic import BaseModel, Field


class UnitCells(BaseModel):
    """One printed row with a Unit 1 cell, a Unit 2 cell and a Station cell."""

    unit1: str = Field(description="Cell under 'Unit 1 (210 MW)'")
    unit2: str = Field(description="Cell under 'Unit 2 (210 MW)'")
    station: str = Field(description="Cell under 'Station'")


class UnitValueTimes(BaseModel):
    unit1_value: str = Field(description="Unit 1 load in MW")
    unit1_time: str = Field(description="Unit 1 time of occurrence, e.g. '2:00'")
    unit2_value: str = Field(description="Unit 2 load in MW")
    unit2_time: str = Field(description="Unit 2 time of occurrence, e.g. '22:00'")


class ValueTime(BaseModel):
    value: str
    time: str = Field(description="Time of occurrence, e.g. '22:00'")


class DmWater(BaseModel):
    unit1: str = Field(description="Unit 1 quantity in m3, the number before the bracket, e.g. '111'")
    unit1_pct: str = Field(description="Unit 1 percentage inside the bracket, without the % sign, e.g. '0.67'")
    unit2: str = Field(description="Unit 2 quantity in m3, e.g. '256'")
    unit2_pct: str = Field(description="Unit 2 percentage inside the bracket, e.g. '1.55'")
    station: str = Field(description="Station total in m3, e.g. '367'")


class AuxPower(BaseModel):
    plant: str = Field(description="Number after 'Plant:', e.g. '0.76514'")
    plant_pct: str = Field(description="Percentage in the bracket after the plant figure, without %, e.g. '10.69'")
    substation: str = Field(description="Number after 'Sub-Station:', e.g. '0.028'")
    station: str = Field(description="Station cell, e.g. '0.7931'")


class Hydrogen(BaseModel):
    unit1: str = Field(description="Unit 1 cylinders, the number before the bracket, e.g. '8'")
    unit1_split: str = Field(description="Unit 1 bracket contents, e.g. '4+4'")
    unit2: str = Field(description="Unit 2 cylinders, e.g. '6'")
    unit2_split: str = Field(description="Unit 2 bracket contents, e.g. '6+0'")
    station: str = Field(description="Station total, e.g. '14'")


class CoalTrips(BaseModel):
    road: str = Field(description="Cell under 'By Road Dumpers'")
    rail: str = Field(description="Cell under 'By Railways', exactly as printed, e.g. '1 (03)'")


class RoadRailTotal(BaseModel):
    road: str = Field(description="Cell under 'By Road Dumpers'")
    rail: str = Field(description="Cell under 'By Railways'")
    total: str = Field(description="Cell under 'Total Coal Receipt'")


class LineFlow(BaseModel):
    max: str = Field(description="Max. load in MW, or '----' if dashes are printed")
    max_time: str
    min: str
    min_time: str


class LoadFlow(BaseModel):
    pvunl: LineFlow = Field(description="PVUNL (400 KV Tr. Line)")
    biharsarif: LineFlow = Field(description="Biharsarif (220 KV Tr. Line)")
    govindpur: LineFlow = Field(description="Govindpur (220 KV Tr. Line)")


class EnergyFlow(BaseModel):
    exported: str = Field(description="Energy Export (MU)")
    imported: str = Field(description="Energy Import (MU)")
    net_export: str = Field(description="Net Energy Export (MU)")
    prog_export: str = Field(description="Prog. Energy Export (MU)")
    prog_import: str = Field(description="Prog. Energy Import (MU)")
    prog_net_export: str = Field(description="Prog. Net Energy Exp. (MU)")


class DailySystemReport(BaseModel):
    is_daily_system_report: bool = Field(
        description="True only if the image shows the Tenughat Vidyut Nigam Limited 'Daily System Report' form."
    )
    report_date: str = Field(
        description="The date printed after 'Date:' at the top right, exactly as printed, e.g. '4/11/26' (day/month/year)."
    )

    # Daily section -----------------------------------------------------------
    r01_load_0600: UnitCells = Field(description="S.No 1, 'Load At 06.00 Hr' (MW)")
    r01_load_0900: UnitCells = Field(description="S.No 1, 'At 09:00 Hr' (MW)")
    r02_load_max: UnitValueTimes = Field(description="S.No 2, Previous Day Load, Max. (MW / Hrs)")
    r02_load_min: UnitValueTimes = Field(description="S.No 2, Previous Day Load, Min. (MW / Hrs)")
    r03_freq_max: ValueTime = Field(description="S.No 3, Frequency Max. (Hz / Hrs)")
    r03_freq_min: ValueTime = Field(description="S.No 3, Frequency Min. (Hz / Hrs)")
    r04_gen: UnitCells = Field(description="S.No 4, Previous Day Gen. (MU)")
    r05_plf: UnitCells = Field(description="S.No 5, Plant Load Factor (%)")
    r06_paf: UnitCells = Field(description="S.No 6, Plant Availability Factor (%)")
    r07_coal: UnitCells = Field(description="S.No 7, Coal Consumption (MT)")
    r08_oil: UnitCells = Field(description="S.No 8, Oil Consumption (KL)")
    r09_dm_water: DmWater = Field(description="S.No 9, DM Water consumption (m3)")
    r10_aux_power: AuxPower = Field(description="S.No 10, Auxl. Power Consumption (MU)")
    r11_outage: UnitCells = Field(description="S.No 11, Period of Outage, as printed, e.g. '0:00:00'")
    r12_sp_coal: UnitCells = Field(description="S.No 12, Sp. Coal consumption (Kg/Kwh)")
    r13_sp_oil: UnitCells = Field(description="S.No 13, Sp. Oil consumption (ml/Kwh)")
    r14_h2: Hydrogen = Field(description="S.No 14, H2 Consumption (Nos. of Cylinder)")
    r15_backing_down: UnitCells = Field(description="S.No 15, Grid Backing Down (MU)")

    # Monthly progressive section ---------------------------------------------
    r16_prog_gen: UnitCells = Field(description="S.No 16, Prog. Generation (MU)")
    r17_prog_plf: UnitCells = Field(description="S.No 17, Prog. PLF (%)")
    r18_prog_coal: UnitCells = Field(description="S.No 18, Prog. Coal consumption (MT)")
    r19_prog_oil: UnitCells = Field(description="S.No 19, Prog. Oil consumption (KL)")
    r20_prog_dm_water: UnitCells = Field(description="S.No 20, Prog. DM water cons. (m3)")
    r21_prog_aux_power: AuxPower = Field(description="S.No 21, Prog. Auxl. Power Cons. (MU)")
    r22_prog_outage: UnitCells = Field(description="S.No 22, Prog. Period of Outage, as printed, e.g. '0:35:00'")
    r23_prog_sp_coal: UnitCells = Field(description="S.No 23, Prog. Sp. Coal cons. (Kg/Kwh)")
    r24_prog_sp_oil: UnitCells = Field(description="S.No 24, Prog. Sp. Oil consumption (ml/Kwh)")
    r25_prog_h2: UnitCells = Field(description="S.No 25, Prog. H2 Consumption (Nos. of Cylinder)")
    r26_prog_backing_down: UnitCells = Field(description="S.No 26, Prog. Grid Backing Down (MU)")

    # Status of fuel -----------------------------------------------------------
    r27_coal_trips: CoalTrips = Field(description="S.No 27, Trip (Nos.)")
    r28_coal_transported: RoadRailTotal = Field(description="S.No 28, Coal Transported at site (MT)")
    r29_prog_coal_receipt: RoadRailTotal = Field(description="S.No 29, Prog. Coal Receipt (MT)")
    r30_usable_coal_stock: str = Field(description="S.No 30, Usable Coal Stock (MT)")
    r31_oil_transported: str = Field(description="S.No 31, Oil Transported at Site (KL), the first value cell")
    r31_oil_in_pipeline: str = Field(description="S.No 31, value after 'Oil in Pipeline in KL'")
    r32_usable_oil_stock: str = Field(description="S.No 32, Usable stock of oil (KL)")
    r32_prog_oil_receipt: str = Field(description="S.No 32, value after 'Prog. oil receipt KL'")

    # Electrical system ---------------------------------------------------------
    r33_load_flow: LoadFlow = Field(description="S.No 33, Load Flow in MW per transmission line")
    r34_pvunl: EnergyFlow = Field(description="S.No 34, Energy flow, PVUNL")
    r35_biharsarif: EnergyFlow = Field(description="S.No 35, Energy flow, Biharsarif")
    r36_govindpur: EnergyFlow = Field(description="S.No 36, Energy flow, Govindpur (1+2)")
    r37_total: EnergyFlow = Field(description="S.No 37, Energy flow, Total")
    r38_remarks_unit1: str = Field(description="(38) Remarks: Unit 1, the text after the label, e.g. 'On Load'")
    r39_remarks_unit2: str = Field(description="(39) Remarks: Unit 2, the text after the label")

    unclear_cells: list[str] = Field(
        description=(
            "Field paths of any cells you could not read with confidence (smudged, cut off, overwritten by "
            "pen or a stamp), e.g. 'r07_coal.unit2'. Empty list when everything is legible."
        )
    )
