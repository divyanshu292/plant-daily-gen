// What each stored entry field means, and how the printed Daily System Report
// maps onto those fields.

// kind: 'number' (decimal), 'count' (whole number), 'hours' (decimal hours, shown h:mm), 'text'
export const FIELDS = {
  u1Gen: { label: 'Unit 1 generation', unit: 'MU' },
  u2Gen: { label: 'Unit 2 generation', unit: 'MU' },
  u1Bd: { label: 'Unit 1 grid backing down', unit: 'MU' },
  u2Bd: { label: 'Unit 2 grid backing down', unit: 'MU' },
  u1Coal: { label: 'Unit 1 coal', unit: 'MT' },
  u2Coal: { label: 'Unit 2 coal', unit: 'MT' },
  u1Oil: { label: 'Unit 1 oil', unit: 'KL' },
  u2Oil: { label: 'Unit 2 oil', unit: 'KL' },
  gcv: { label: 'Coal GCV', unit: 'kcal/kg' },
  apcPlant: { label: 'Aux. power, plant', unit: 'MU' },
  apcSub: { label: 'Aux. power, sub-station', unit: 'MU' },
  apc: { label: 'Aux. power, station', unit: 'MU' },
  u1Dm: { label: 'Unit 1 DM water', unit: 'm³' },
  u2Dm: { label: 'Unit 2 DM water', unit: 'm³' },
  u1H2: { label: 'Unit 1 H₂', unit: 'cylinders', kind: 'count' },
  u2H2: { label: 'Unit 2 H₂', unit: 'cylinders', kind: 'count' },
  u1Fo: { label: 'Unit 1 forced outage', unit: 'h:mm', kind: 'hours' },
  u2Fo: { label: 'Unit 2 forced outage', unit: 'h:mm', kind: 'hours' },
  u1Po: { label: 'Unit 1 planned outage', unit: 'h:mm', kind: 'hours' },
  u2Po: { label: 'Unit 2 planned outage', unit: 'h:mm', kind: 'hours' },
  u1Trip: { label: 'Unit 1 trips', unit: 'nos.', kind: 'count' },
  u2Trip: { label: 'Unit 2 trips', unit: 'nos.', kind: 'count' },
  u1Btl: { label: 'Unit 1 boiler tube leaks', unit: 'nos.', kind: 'count' },
  u2Btl: { label: 'Unit 2 boiler tube leaks', unit: 'nos.', kind: 'count' },
  u1TripReason: { label: 'Unit 1 trip reason', kind: 'text' },
  u2TripReason: { label: 'Unit 2 trip reason', kind: 'text' },
  coalReceiptRoad: { label: 'Coal receipt by road', unit: 'MT' },
  coalReceiptRail: { label: 'Coal receipt by rail', unit: 'MT' },
  coalReceipt: { label: 'Coal receipt, total', unit: 'MT' },
  oilReceipt: { label: 'Oil receipt', unit: 'KL' },
  coalStock: { label: 'Usable coal stock', unit: 'MT' },
  oilStock: { label: 'Usable oil stock', unit: 'KL' },
  oilPipeline: { label: 'Oil in pipeline', unit: 'KL' },
  u1Remark: { label: 'Unit 1 remarks', kind: 'text' },
  u2Remark: { label: 'Unit 2 remarks', kind: 'text' },
};

export function fieldKind(key) {
  return FIELDS[key]?.kind || 'number';
}

export function fieldLabel(key) {
  const f = FIELDS[key];
  if (!f) return key;
  return f.unit ? `${f.label} (${f.unit})` : f.label;
}

/** Day editor layout. A row has a unit pair (u1/u2) or a single station-level field. */
export const DETAIL_GROUPS = [
  {
    title: 'Generation',
    rows: [
      { label: 'Generation', unit: 'MU', u1: 'u1Gen', u2: 'u2Gen', dp: 2 },
      { label: 'Grid backing down', unit: 'MU', u1: 'u1Bd', u2: 'u2Bd', dp: 3 },
    ],
  },
  {
    title: 'Fuel consumption',
    rows: [
      { label: 'Coal', unit: 'MT', u1: 'u1Coal', u2: 'u2Coal' },
      { label: 'Oil', unit: 'KL', u1: 'u1Oil', u2: 'u2Oil' },
      { label: 'Coal GCV', unit: 'kcal/kg', field: 'gcv', extra: true },
    ],
  },
  {
    title: 'Auxiliary power',
    rows: [
      { label: 'Plant', unit: 'MU', field: 'apcPlant' },
      { label: 'Sub-station', unit: 'MU', field: 'apcSub' },
      { label: 'Station total', unit: 'MU', field: 'apc' },
    ],
  },
  {
    title: 'Water and hydrogen',
    rows: [
      { label: 'DM water', unit: 'm³', u1: 'u1Dm', u2: 'u2Dm', dp: 0 },
      { label: 'H₂', unit: 'cylinders', u1: 'u1H2', u2: 'u2H2' },
    ],
  },
  {
    title: 'Outages and trips',
    rows: [
      { label: 'Forced outage', unit: 'h:mm', u1: 'u1Fo', u2: 'u2Fo' },
      { label: 'Planned outage', unit: 'h:mm', u1: 'u1Po', u2: 'u2Po', extra: true },
      { label: 'Trips', unit: 'nos.', u1: 'u1Trip', u2: 'u2Trip', extra: true },
      { label: 'Boiler tube leaks', unit: 'nos.', u1: 'u1Btl', u2: 'u2Btl', extra: true },
      { label: 'Trip reason', u1: 'u1TripReason', u2: 'u2TripReason', extra: true },
    ],
  },
  {
    title: 'Fuel receipt and stock',
    rows: [
      { label: 'Coal receipt by road', unit: 'MT', field: 'coalReceiptRoad' },
      { label: 'Coal receipt by rail', unit: 'MT', field: 'coalReceiptRail' },
      { label: 'Coal receipt, total', unit: 'MT', field: 'coalReceipt' },
      { label: 'Oil receipt', unit: 'KL', field: 'oilReceipt' },
      { label: 'Usable coal stock', unit: 'MT', field: 'coalStock' },
      { label: 'Usable oil stock', unit: 'KL', field: 'oilStock' },
      { label: 'Oil in pipeline', unit: 'KL', field: 'oilPipeline' },
    ],
  },
  {
    title: 'Remarks',
    rows: [{ label: 'Remarks', u1: 'u1Remark', u2: 'u2Remark' }],
  },
];

// ---- the printed page ------------------------------------------------------------------

/**
 * Rows 4 to 15, 28 and 31 of the Daily System Report. Each row has three column
 * slots (Unit 1, Unit 2, Station on the page). A slot names the raw cell, the
 * entry field it is stored in (if any), and optional extras printed beside it.
 */
const unitSlots = (key, u1, u2, extra = {}) => [
  { cell: `${key}.unit1`, field: u1, ...(extra.unit1 || {}) },
  { cell: `${key}.unit2`, field: u2, ...(extra.unit2 || {}) },
  { cell: `${key}.station` },
];

export const PRINTED_ROWS = [
  { no: 4, label: 'Previous day gen.', unit: 'MU', slots: unitSlots('r04_gen', 'u1Gen', 'u2Gen'), sum: true },
  { no: 5, label: 'Plant load factor', unit: '%', slots: unitSlots('r05_plf') },
  { no: 6, label: 'Availability', unit: '%', slots: unitSlots('r06_paf') },
  { no: 7, label: 'Coal consumption', unit: 'MT', slots: unitSlots('r07_coal', 'u1Coal', 'u2Coal'), sum: true },
  { no: 8, label: 'Oil consumption', unit: 'KL', slots: unitSlots('r08_oil', 'u1Oil', 'u2Oil'), sum: true },
  {
    no: 9,
    label: 'DM water',
    unit: 'm³',
    slots: unitSlots('r09_dm_water', 'u1Dm', 'u2Dm', {
      unit1: { pct: 'r09_dm_water.unit1_pct' },
      unit2: { pct: 'r09_dm_water.unit2_pct' },
    }),
    sum: true,
  },
  {
    no: 10,
    label: 'Aux. power',
    unit: 'MU',
    slots: [
      { cell: 'r10_aux_power.plant', field: 'apcPlant', sub: 'Plant', pct: 'r10_aux_power.plant_pct' },
      { cell: 'r10_aux_power.substation', field: 'apcSub', sub: 'Sub-station' },
      { cell: 'r10_aux_power.station', field: 'apc' },
    ],
    sum: true,
  },
  { no: 11, label: 'Period of outage', unit: 'h:mm:ss', kind: 'hours', slots: unitSlots('r11_outage', 'u1Fo', 'u2Fo'), sum: true },
  { no: 12, label: 'Sp. coal', unit: 'kg/kWh', slots: unitSlots('r12_sp_coal') },
  { no: 13, label: 'Sp. oil', unit: 'ml/kWh', slots: unitSlots('r13_sp_oil') },
  {
    no: 14,
    label: 'H₂ consumption',
    unit: 'cylinders',
    kind: 'count',
    slots: unitSlots('r14_h2', 'u1H2', 'u2H2', {
      unit1: { split: 'r14_h2.unit1_split' },
      unit2: { split: 'r14_h2.unit2_split' },
    }),
    sum: true,
  },
  { no: 15, label: 'Grid backing down', unit: 'MU', slots: unitSlots('r15_backing_down', 'u1Bd', 'u2Bd'), sum: true },
  {
    no: 28,
    label: 'Coal transported',
    unit: 'MT',
    slots: [
      { cell: 'r28_coal_transported.road', field: 'coalReceiptRoad', sub: 'Road' },
      { cell: 'r28_coal_transported.rail', field: 'coalReceiptRail', sub: 'Rail' },
      { cell: 'r28_coal_transported.total', field: 'coalReceipt', sub: 'Total' },
    ],
    sum: true,
  },
  {
    no: 31,
    label: 'Oil transported',
    unit: 'KL',
    slots: [null, null, { cell: 'r31_oil_transported', field: 'oilReceipt' }],
  },
];

/** Rows of the review form: the printed rows that carry stored values, plus stocks and remarks. */
export const REVIEW_ROWS = [
  ...PRINTED_ROWS.filter((r) => r.slots.some((s) => s?.field)),
  { label: 'Usable coal stock', unit: 'MT', slots: [null, null, { cell: 'r30_usable_coal_stock', field: 'coalStock' }] },
  { label: 'Usable oil stock', unit: 'KL', slots: [null, null, { cell: 'r32_usable_oil_stock', field: 'oilStock' }] },
  { label: 'Oil in pipeline', unit: 'KL', slots: [null, null, { cell: 'r31_oil_in_pipeline', field: 'oilPipeline' }] },
  { label: 'Remarks', kind: 'text', slots: [{ cell: 'r38_remarks_unit1', field: 'u1Remark' }, { cell: 'r39_remarks_unit2', field: 'u2Remark' }, null] },
];

/** Raw cell path -> entry field, from the tables above. */
export const CELL_FIELD = Object.fromEntries(
  REVIEW_ROWS.flatMap((r) => r.slots.filter((s) => s?.field).map((s) => [s.cell, s.field]))
);

/** Read a cell like "r04_gen.unit1" (or "r30_usable_coal_stock") out of the raw page. */
export function rawCell(raw, path) {
  if (!raw || !path) return null;
  const v = path.split('.').reduce((obj, k) => (obj == null ? null : obj[k]), raw);
  return v == null || typeof v === 'object' ? null : String(v);
}

/**
 * From failed checks (and cells the reader marked unclear), which entry fields
 * and which printed-only cells deserve a second look.
 */
export function flaggedCells(checks, unclear = []) {
  const fields = new Map(); // field -> number of failed checks touching it
  const cells = new Set();
  for (const c of checks || []) {
    if (c.ok) continue;
    for (const cell of c.cells || []) {
      cells.add(cell);
      const f = CELL_FIELD[cell];
      if (f) fields.set(f, (fields.get(f) || 0) + 1);
    }
  }
  for (const cell of unclear || []) {
    cells.add(cell);
    const f = CELL_FIELD[cell];
    if (f && !fields.has(f)) fields.set(f, 0);
  }
  return { fields, cells };
}
