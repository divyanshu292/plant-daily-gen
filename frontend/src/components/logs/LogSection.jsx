import { useState } from 'react';
import {
  ArrowDownIcon,
  ArrowUpIcon,
  CaretDownIcon,
  ChatTextIcon,
  CheckIcon,
  CircleNotchIcon,
  TrashIcon,
  WarningIcon,
} from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { MicroLabel } from '@/components/common/Text';
import { DASH, fmtDate, fmtDateTime, printedDecimals } from '@/lib/format';
import { cn } from '@/lib/utils';

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

/** A value as written. A dash in the message means the reading was not taken. */
function shown(value) {
  return value == null || value === '-' ? DASH : value;
}

function valueTitle(value) {
  if (value == null) return 'Not reported';
  return value === '-' ? 'Written as a dash: not taken' : undefined;
}

/** "▲ 0.2" with as many decimals as the values were written with. */
function Change({ row, className }) {
  if (row.delta == null) return null;
  if (row.delta === 0) return null;
  const places = Math.max(printedDecimals(row.value), printedDecimals(row.prev));
  const Icon = row.delta > 0 ? ArrowUpIcon : ArrowDownIcon;
  return (
    <span className={cn('inline-flex items-center gap-0.5 whitespace-nowrap font-medium tabular', className)}>
      <Icon weight="bold" className="h-3 w-3" aria-hidden />
      <span className="sr-only">{row.delta > 0 ? 'up' : 'down'}</span>
      {Math.abs(row.delta).toFixed(places)}
    </span>
  );
}

/** Columns from md up: reading, this day, the other day, change. On a phone the last two sit under the value. */
const COLS = 'md:grid-cols-[minmax(0,1fr)_9rem_9rem_6rem]';

function Row({ row, compared, canEdit, onSave }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(row.value ?? '');
  const [state, setState] = useState({ status: 'idle' }); // idle | saving | error
  const saving = state.status === 'saving';
  const unit = row.unit && row.value != null && row.value !== '-' ? row.unit : '';

  const toggle = () => {
    if (!open) {
      setDraft(row.value ?? '');
      setState({ status: 'idle' });
    }
    setOpen(!open);
  };

  const save = async (e) => {
    e.preventDefault();
    if (saving) return;
    setState({ status: 'saving' });
    try {
      await onSave(row.key, draft.trim());
      setState({ status: 'idle' });
      setOpen(false);
    } catch (err) {
      setState({ status: 'error', error: err.message });
    }
  };

  return (
    <li>
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className={cn(
          'grid min-h-11 w-full grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-3 px-4 py-2.5 text-left transition-colors',
          'hover:bg-accent/50 focus-visible:bg-accent/50 focus-visible:outline-none',
          compared && COLS,
          open && 'bg-accent/40'
        )}
      >
        <span className="min-w-0 text-sm leading-snug">
          {row.label}
          {row.check && (
            <>
              <span aria-hidden className="ml-2 inline-block h-1.5 w-1.5 -translate-y-px rounded-full bg-attention align-middle" />
              <span className="sr-only"> (to check)</span>
            </>
          )}
        </span>

        <span className="text-right" title={valueTitle(row.value)}>
          <span className={cn('text-[15px] font-semibold tabular', row.value == null && 'font-normal text-muted-foreground')}>
            {shown(row.value)}
          </span>
          {unit && <span className="ml-1 text-xs text-muted-foreground">{unit}</span>}
        </span>

        {compared && (
          <>
            {/* Phone: one line under the row, only when something differs. */}
            {row.changed && (
              <span className="col-span-2 mt-0.5 flex items-baseline justify-end gap-2 text-xs text-muted-foreground md:hidden">
                <span className="tabular">{row.prev == null ? 'not reported then' : `was ${shown(row.prev)}`}</span>
                <Change row={row} className="text-foreground" />
              </span>
            )}
            {/* md and up: columns of their own. */}
            <span className="hidden text-right text-sm text-muted-foreground tabular md:block" title={valueTitle(row.prev)}>
              {shown(row.prev)}
            </span>
            <span className="hidden text-right text-sm md:block">
              {row.delta ? (
                <Change row={row} />
              ) : (
                <span className="text-muted-foreground">{row.changed ? 'changed' : ''}</span>
              )}
            </span>
          </>
        )}
      </button>

      {open && (
        <div className="space-y-3 bg-muted/40 px-4 py-3">
          {row.check && (
            <p className="flex gap-2 text-sm leading-snug text-attention">
              <WarningIcon weight="fill" className="mt-0.5 h-4 w-4 shrink-0" />
              {row.check}
            </p>
          )}
          {row.src ? (
            <div className="space-y-1">
              <MicroLabel className="text-[10px]">In the message</MicroLabel>
              <p className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">{row.src}</p>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">{row.edited ? 'Typed in by hand.' : 'The line it came from was not kept.'}</p>
          )}
          {row.edited && row.src && <p className="text-xs text-muted-foreground">Corrected by hand.</p>}

          {canEdit && (
            <form onSubmit={save} className="space-y-2">
              <label htmlFor={`log-${row.key}`} className="block text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
                Correct the value{row.unit ? ` (${row.unit})` : ''}
              </label>
              <div className="flex gap-2">
                <input
                  id={`log-${row.key}`}
                  type="text"
                  inputMode={row.text ? 'text' : 'decimal'}
                  enterKeyHint="done"
                  autoComplete="off"
                  autoCapitalize="off"
                  value={draft}
                  disabled={saving}
                  onChange={(e) => {
                    setDraft(e.target.value);
                    if (state.status === 'error') setState({ status: 'idle' });
                  }}
                  className={cn(
                    // 16 px text below md: iOS zooms the page into any smaller input.
                    'h-11 min-w-0 flex-1 rounded-md border border-input bg-background px-3 text-base tabular md:h-9 md:text-sm',
                    'hover:border-foreground/30 focus:border-foreground/60 focus:outline-none focus:ring-1 focus:ring-ring'
                  )}
                />
                <Button type="submit" size="touch" disabled={saving || draft.trim() === (row.value ?? '')}>
                  {saving ? <CircleNotchIcon weight="bold" className="animate-spin" /> : <CheckIcon weight="bold" />}
                  Save
                </Button>
              </div>
              {state.status === 'error' ? (
                <p role="alert" className="text-xs text-attention">
                  {state.error}
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">Leave it blank to remove the value.</p>
              )}
            </form>
          )}
        </div>
      )}
    </li>
  );
}

/**
 * One section of a day (Mill 2A, Chemical report...): its values in the fixed
 * order, each beside the other day's. `mode` picks the rows: all | changed | check.
 * actions: { edit(key, value), checked(), remove() }, each returning a promise.
 */
export function LogSection({ section, mode, startOpen, canEdit, actions }) {
  const [open, setOpen] = useState(startOpen);
  const [showRaw, setShowRaw] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(null); // 'checked' | 'remove' | null
  const [error, setError] = useState(null);

  const { counts } = section;
  const compared = !!section.previousDate;
  const rows = section.rows.filter((r) => (mode === 'changed' ? r.changed : mode === 'check' ? r.check : true));

  const run = async (name, fn) => {
    setBusy(name);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  const bits = [plural(counts.values + section.extra.length, 'value')];
  if (compared) bits.push(counts.changed ? `${counts.changed} changed since ${fmtDate(section.previousDate, 'short')}` : `same as ${fmtDate(section.previousDate, 'short')}`);

  let lastGroup = null;

  return (
    <Card className="overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex min-h-[56px] w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-accent/50 focus-visible:bg-accent/50 focus-visible:outline-none"
      >
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[15px] font-semibold leading-snug">{section.name}</span>
          <span className="block truncate text-xs text-muted-foreground tabular">{bits.join(' · ')}</span>
        </span>
        {counts.toCheck > 0 && (
          <span className="shrink-0 whitespace-nowrap rounded-md bg-attention px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest text-attention-foreground">
            {counts.toCheck} to check
          </span>
        )}
        <CaretDownIcon weight="bold" className={cn('h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="border-t border-border">
          {rows.length > 0 && compared && (
            <div className={cn('hidden gap-x-3 border-b border-border px-4 py-2 md:grid', COLS)}>
              <MicroLabel className="text-[10px]">Reading</MicroLabel>
              <MicroLabel className="text-right text-[10px]">{fmtDate(section.date, 'short')}</MicroLabel>
              <MicroLabel className="text-right text-[10px]">{fmtDate(section.previousDate, 'short')}</MicroLabel>
              <MicroLabel className="text-right text-[10px]">Change</MicroLabel>
            </div>
          )}

          {rows.length > 0 && (
            <ul className="divide-y divide-border/60">
              {rows.map((row) => {
                const heading = row.group && row.group !== lastGroup ? row.group : null;
                lastGroup = row.group;
                return (
                  <FragmentWithHeading key={row.key} heading={heading}>
                    <Row row={row} compared={compared} canEdit={canEdit} onSave={actions.edit} />
                  </FragmentWithHeading>
                );
              })}
            </ul>
          )}

          {mode !== 'changed' && section.missed.length > 0 && (
            <div className="space-y-2 border-t border-border bg-attention/[0.08] px-4 py-3">
              <p className="flex gap-2 text-sm font-medium leading-snug">
                <WarningIcon weight="fill" className="mt-0.5 h-4 w-4 shrink-0 text-attention" />
                {section.missed.length === 1 ? 'A number in the message was not used' : 'Numbers in the message were not used'}
              </p>
              <ul className="space-y-2 pl-6">
                {section.missed.map((m) => (
                  <li key={m.line} className="text-xs leading-relaxed">
                    <span className="font-semibold tabular">{m.numbers.join(', ')}</span>
                    <span className="text-muted-foreground"> in </span>
                    <span className="break-words font-mono">{m.line}</span>
                  </li>
                ))}
              </ul>
              <p className="pl-6 text-xs text-muted-foreground">
                If it is a reading, open the value it belongs to and correct it.
              </p>
            </div>
          )}

          {mode !== 'changed' && section.extra.length > 0 && (
            <div className="space-y-2 border-t border-border px-4 py-3">
              <MicroLabel className="text-[10px]">{section.rows.length > 0 ? 'Written in the message, with no field in the fixed set' : 'Readings with no field in the fixed set'}</MicroLabel>
              <ul className="divide-y divide-border/60">
                {section.extra.map((e) => (
                  <li key={`${e.label}-${e.value}`} className="flex items-baseline justify-between gap-3 py-2 text-sm">
                    <span className="min-w-0 break-words">{e.label}</span>
                    <span className="shrink-0 font-semibold tabular">{e.value}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="space-y-3 border-t border-border px-4 py-3">
            {showRaw && section.raw && (
              <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/60 px-3 py-2.5 font-mono text-xs leading-relaxed">
                {section.raw}
              </pre>
            )}
            {error && (
              <p role="alert" className="text-xs text-attention">
                {error}
              </p>
            )}

            {confirming ? (
              <div className="space-y-3 rounded-lg bg-attention/[0.08] px-4 py-3">
                <div className="flex gap-3">
                  <WarningIcon weight="fill" className="mt-0.5 h-4 w-4 shrink-0 text-attention" />
                  <p className="text-sm font-medium leading-snug">
                    Remove the {section.name} readings for {fmtDate(section.date, 'medium')}? Paste the message again to bring them back.
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-2 sm:flex sm:justify-end">
                  <Button type="button" variant="outline" size="touch" className="bg-transparent" autoFocus onClick={() => setConfirming(false)} disabled={busy === 'remove'}>
                    Cancel
                  </Button>
                  <Button
                    type="button"
                    size="touch"
                    className="bg-attention text-attention-foreground hover:bg-attention/90"
                    onClick={() => run('remove', actions.remove)}
                    disabled={busy === 'remove'}
                  >
                    {busy === 'remove' && <CircleNotchIcon weight="bold" className="animate-spin" />}
                    Remove
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-x-1 gap-y-2">
                {section.raw && (
                  <Button type="button" variant="ghost" size="touch" className="-ml-3" onClick={() => setShowRaw(!showRaw)} aria-expanded={showRaw}>
                    <ChatTextIcon weight="bold" />
                    {showRaw ? 'Hide the message' : 'Show the message'}
                  </Button>
                )}
                {canEdit && counts.toCheck > 0 && (
                  <Button type="button" variant="ghost" size="touch" onClick={() => run('checked', actions.checked)} disabled={busy === 'checked'}>
                    {busy === 'checked' ? <CircleNotchIcon weight="bold" className="animate-spin" /> : <CheckIcon weight="bold" />}
                    Mark as checked
                  </Button>
                )}
                {canEdit && (
                  <Button type="button" variant="ghost" size="touch" className="text-muted-foreground" onClick={() => setConfirming(true)}>
                    <TrashIcon weight="bold" />
                    Remove
                  </Button>
                )}
                {section.updatedAt && (
                  <span className="ml-auto text-xs text-muted-foreground tabular">
                    {section.updatedBy?.name ? `${section.updatedBy.name} · ` : ''}
                    {fmtDateTime(section.updatedAt)}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

/** A row, with its group's sub-heading above it when the group starts here. */
function FragmentWithHeading({ heading, children }) {
  if (!heading) return children;
  return (
    <>
      <li className="bg-muted/40 px-4 pb-1.5 pt-2.5">
        <MicroLabel className="text-[10px]">{heading}</MicroLabel>
      </li>
      {children}
    </>
  );
}
