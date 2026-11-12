import { useMemo, useState } from 'react';
import { Check, Loader2, Save, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/common/Notice';
import { ValueInput } from '@/components/common/ValueInput';
import { InlinePageImage } from '@/components/common/ImageViewer';
import { CheckRow } from '@/components/upload/ChecksList';
import { api, apiUrl } from '@/lib/api';
import { cn } from '@/lib/utils';
import { REVIEW_ROWS, fieldKind, flaggedCells, rawCell } from '@/lib/fields';
import { addDays, fmtDate, fmtHours, fmtNum, isIsoDate, printedDecimals, printedNumber, toInputText } from '@/lib/format';

const COLUMNS = ['Unit 1', 'Unit 2', 'Station'];

/** Does part 1 + part 2 = total, with the values as they stand in the form? */
function sumStatus(row, values, raw) {
  if (!row.sum) return null;
  const [a, b, t] = row.slots;
  const va = values[a.field];
  const vb = values[b.field];
  const totalText = rawCell(raw, t.cell);
  const vt = t.field ? values[t.field] : printedNumber(totalText);
  if (va == null || vb == null || vt == null) return null;
  const hours = row.kind === 'hours';
  const dp = hours ? 0 : printedDecimals(totalText);
  const tol = hours ? 1 / 60 + 1e-9 : 1.1 * 10 ** -dp;
  const ok = Math.abs(va + vb - vt) <= tol;
  const f = (v) => (hours ? fmtHours(v) : fmtNum(v, dp).replace(/,/g, ''));
  return { ok, text: `${f(va)} + ${f(vb)} = ${f(va + vb)}, ${t.field ? 'total' : 'page shows'} ${f(vt)}` };
}

function SlotLabel({ children, always }) {
  return (
    <div className={cn('mb-1 truncate text-[10px] uppercase tracking-wider text-muted-foreground', !always && 'sm:hidden')}>
      {children}
    </div>
  );
}

function ReviewRow({ row, values, original, setValue, raw, flagged, flaggedPrinted }) {
  const slots = row.slots;
  const used = slots.filter(Boolean);
  const status = sumStatus(row, values, raw);
  const single = used.length === 1;
  const text = row.kind === 'text';

  const renderSlot = (slot, i) => {
    if (!slot) return <div key={i} className="hidden sm:block" />;
    const label = slot.sub || (single ? null : COLUMNS[i]);
    if (!slot.field) {
      const printed = rawCell(raw, slot.cell);
      return (
        <div key={i} className="min-w-0">
          {label && <SlotLabel always={!!slot.sub}>{label}, on page</SlotLabel>}
          <div
            className={cn(
              'flex h-10 items-center justify-end rounded-md border border-dashed border-border px-3 text-sm text-muted-foreground tabular',
              flaggedPrinted.has(slot.cell) && 'border-attention/70 text-foreground'
            )}
            title="Printed on the page; not stored"
          >
            {printed || '—'}
          </div>
        </div>
      );
    }
    const kind = text ? 'text' : fieldKind(slot.field);
    const edited =
      (values[slot.field] ?? null) !== (original[slot.field] ?? null) &&
      !(typeof values[slot.field] === 'number' && typeof original[slot.field] === 'number' && Math.abs(values[slot.field] - original[slot.field]) < 1e-9);
    return (
      <div key={i} className="min-w-0">
        {label && <SlotLabel always={!!slot.sub || text}>{label}</SlotLabel>}
        <ValueInput
          value={values[slot.field]}
          kind={kind}
          flagged={flagged.has(slot.field) && !edited}
          onCommit={(v) => setValue(slot.field, v)}
          aria-label={`${row.label}${label ? `, ${label}` : ''}`}
        />
        {edited && (
          <div className="mt-1 truncate text-[10px] text-muted-foreground">
            read as <span className="line-through">{toInputText(original[slot.field], kind) || 'blank'}</span>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="py-3">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <div className="text-sm font-medium">
          {row.label}
          {row.unit && <span className="ml-1.5 text-xs font-normal text-muted-foreground">{row.unit}</span>}
        </div>
        {status && (
          <div className={cn('flex items-center gap-1 text-[11px] tabular', status.ok ? 'text-muted-foreground' : 'text-attention')}>
            {status.ok ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
            {status.ok ? 'Adds up' : status.text}
          </div>
        )}
      </div>
      {single ? (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <div className="hidden sm:block" />
          <div className="hidden sm:block" />
          <div className="col-span-2 sm:col-span-1">{renderSlot(used[0], 2)}</div>
        </div>
      ) : (
        <div className={cn('grid gap-2', text ? 'grid-cols-1 sm:grid-cols-2' : 'grid-cols-3')}>
          {(text ? used : slots).map((s, i) => renderSlot(s, i))}
        </div>
      )}
    </div>
  );
}

/**
 * A page whose sums did not agree. Shows why, the page itself, and the values
 * read, with the suspect ones highlighted. Saving sends the corrected values.
 */
export function ReviewForm({ report, onConfirmed }) {
  const original = report.entry || {};
  const [values, setValues] = useState(() => ({ ...original }));
  const [dataDate, setDataDate] = useState(report.dataDate || '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const checks = report.checks || [];
  const failed = checks.filter((c) => !c.ok);
  const failedErrors = failed.filter((c) => c.severity === 'error');
  const failedWarnings = failed.filter((c) => c.severity !== 'error');
  const { fields: flagged, cells: flaggedPrinted } = useMemo(
    () => flaggedCells(failed, report.raw?.unclear_cells),
    [report]
  );
  const editedCount = Object.keys(values).filter((k) => {
    const a = values[k] ?? null;
    const b = original[k] ?? null;
    return typeof a === 'number' && typeof b === 'number' ? Math.abs(a - b) > 1e-9 : a !== b;
  }).length;

  const setValue = (field, v) => setValues((s) => ({ ...s, [field]: v }));

  const save = async () => {
    if (!isIsoDate(dataDate)) {
      setError('Enter the date the figures are for. That is the day before the date printed on the page.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await api(`/reports/${report.id}/confirm`, {
        method: 'POST',
        json: { dataDate, entry: values },
      });
      onConfirmed(saved);
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <Notice tone="attention" title="This page did not add up, so nothing has been saved yet.">
        Compare the highlighted values with the page, correct any that were misread, then save.
        {report.replaced && dataDate && <> {fmtDate(dataDate, 'short')} already has data; saving replaces it.</>}
      </Notice>

      {failedErrors.length > 0 && (
        <div className="rounded-lg border border-attention/40">
          <div className="border-b border-attention/30 px-4 py-2 text-[11px] font-medium uppercase tracking-widest text-attention">
            {failedErrors.length === 1 ? 'Check that failed' : `${failedErrors.length} checks that failed`}
          </div>
          <ul className="divide-y divide-border/60 px-4">
            {failedErrors.map((c, i) => (
              <CheckRow key={`${c.id}-${i}`} check={c} />
            ))}
          </ul>
          {failedWarnings.length > 0 && (
            <ul className="divide-y divide-border/60 border-t border-border/60 px-4">
              {failedWarnings.map((c, i) => (
                <CheckRow key={`${c.id}-${i}`} check={c} />
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="lg:sticky lg:top-20 lg:self-start">
          <InlinePageImage
            src={apiUrl(`/reports/${report.id}/image`)}
            title={report.reportDate ? `Page dated ${fmtDate(report.reportDate, 'medium')}` : report.fileName || 'Uploaded page'}
          />
        </div>

        <div className="min-w-0">
          <div className="rounded-lg border border-border bg-muted/30 p-3">
            <label className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <span className="text-sm">
                <span className="font-medium">Figures are for</span>
                <span className="block text-xs text-muted-foreground">
                  {report.reportDate
                    ? `Page dated ${fmtDate(report.reportDate, 'medium')}, so normally ${fmtDate(addDays(report.reportDate, -1), 'medium')}.`
                    : 'The date on the page could not be read. Enter the day the figures belong to (the day before the page date).'}
                </span>
              </span>
              <input
                type="date"
                value={dataDate}
                onChange={(e) => setDataDate(e.target.value)}
                className={cn(
                  'h-10 rounded-md border border-input bg-background px-3 text-sm tabular [color-scheme:light] dark:[color-scheme:dark] sm:w-44',
                  !dataDate && 'border-attention ring-1 ring-attention'
                )}
              />
            </label>
          </div>

          <div className="mt-2 hidden grid-cols-3 gap-2 px-0 pt-2 text-[10px] font-medium uppercase tracking-widest text-muted-foreground sm:grid">
            {COLUMNS.map((c) => (
              <div key={c} className="text-right">
                {c}
              </div>
            ))}
          </div>
          <div className="divide-y divide-border/60">
            {REVIEW_ROWS.map((row) => (
              <ReviewRow
                key={row.label}
                row={row}
                values={values}
                original={original}
                setValue={setValue}
                raw={report.raw}
                flagged={flagged}
                flaggedPrinted={flaggedPrinted}
              />
            ))}
          </div>

          <div className="sticky bottom-0 -mx-1 mt-4 border-t border-border bg-card/95 px-1 pb-1 pt-4 backdrop-blur">
            {error && (
              <Notice tone="error" className="mb-3" title="Not saved">
                {error}
              </Notice>
            )}
            <div className="flex flex-wrap items-center gap-3">
              <Button size="lg" onClick={save} disabled={saving}>
                {saving ? <Loader2 className="animate-spin" /> : <Save />}
                {saving ? 'Saving' : dataDate ? `Save figures for ${fmtDate(dataDate, 'short')}` : 'Save'}
              </Button>
              <span className="hidden text-xs text-muted-foreground sm:inline">
                {editedCount === 0
                  ? 'No values changed yet. Save as read only if the page itself is wrong.'
                  : `${editedCount} value${editedCount === 1 ? '' : 's'} corrected.`}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
