import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { CaretLeftIcon, CaretRightIcon, ImageIcon, XIcon } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/common/Notice';
import { MicroLabel } from '@/components/common/Text';
import { ValueInput } from '@/components/common/ValueInput';
import { ImageViewer } from '@/components/common/ImageViewer';
import { SourceMarker } from '@/components/data/CoverageCalendar';
import { api, apiUrl } from '@/lib/api';
import { useDialog } from '@/lib/hooks';
import { DETAIL_GROUPS, fieldKind } from '@/lib/fields';
import { add, dayStatus, STATUS_TEXT } from '@/lib/entries';
import { addDays, fmtDate, fmtDateTime, fmtHours, fmtNum } from '@/lib/format';

// One box per unit; a single station-level box spans both columns so right edges line up.
const PAIR_W = 'w-[6.25rem] sm:w-28';
const SINGLE_W = 'w-[13rem] sm:w-[14.5rem]';

function Field({ field, entry, state, onSave, label, className }) {
  return (
    <ValueInput
      className={className}
      value={entry?.[field]}
      kind={fieldKind(field)}
      status={state}
      onCommit={(v) => onSave(field, v)}
      aria-label={label}
    />
  );
}

function stationSum(row, entry) {
  if (!row.u1 || fieldKind(row.u1) === 'text' || !entry) return null;
  const v = add(entry[row.u1], entry[row.u2]);
  if (v == null) return null;
  if (fieldKind(row.u1) === 'hours') return fmtHours(v);
  if (fieldKind(row.u1) === 'count') return fmtNum(v, 0);
  return fmtNum(v, row.dp ?? 2);
}

/** One day's stored values, every field editable. Each change is saved when the box loses focus. */
export function DayDetail({ date, entry, loaded = true, today, onClose, onSaved, onNavigate }) {
  useDialog(onClose);
  const [states, setStates] = useState({});
  const [errors, setErrors] = useState({});
  const [viewing, setViewing] = useState(false);

  useEffect(() => {
    setStates({});
    setErrors({});
    setViewing(false);
  }, [date]);
  const status = dayStatus(entry, date, today);

  const save = async (field, value) => {
    setStates((s) => ({ ...s, [field]: 'saving' }));
    setErrors((e) => ({ ...e, [field]: null }));
    try {
      const updated = await api(`/entries/${date}`, { method: 'PUT', json: { [field]: value } });
      onSaved(date, field, updated);
      setStates((s) => ({ ...s, [field]: 'saved' }));
    } catch (err) {
      setStates((s) => ({ ...s, [field]: 'error' }));
      setErrors((e) => ({ ...e, [field]: err.message }));
    }
  };

  const prev = addDays(date, -1);
  const next = addDays(date, 1);
  const errorList = Object.entries(errors).filter(([, m]) => m);

  return createPortal(
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={`Data for ${fmtDate(date, 'long')}`}>
      <div className="absolute inset-0 bg-black/60 animate-fade-in" onClick={onClose} />
      <div className="absolute inset-y-0 right-0 flex w-full flex-col bg-background shadow-2xl duration-200 animate-in slide-in-from-right-8 sm:max-w-xl sm:border-l sm:border-border">
        <div className="flex items-center gap-2 border-b border-border pb-2 pl-4 pr-1.5 pt-[calc(0.5rem_+_env(safe-area-inset-top))] md:pl-6 md:pr-3">
          <div className="min-w-0 flex-1">
            <MicroLabel>Data for the day</MicroLabel>
            <h2 className="mt-0.5 truncate text-xl font-semibold tracking-tight md:text-2xl">
              <span className="sm:hidden">{fmtDate(date, 'weekdayYear')}</span>
              <span className="hidden sm:inline">{fmtDate(date, 'long')}</span>
            </h2>
          </div>
          <Button variant="ghost" size="icon" className="h-11 w-11 shrink-0 rounded-full" onClick={onClose} aria-label="Close">
            <XIcon weight="bold" />
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto overscroll-contain scroll-thin">
          <div className="space-y-8 px-4 pb-8 pt-4 md:px-6 md:pt-5">
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
                <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-sm">
                  <SourceMarker status={status} />
                  <span>{STATUS_TEXT[status]}</span>
                  {entry?.updatedAt && (
                    <span className="text-xs text-muted-foreground">· changed {fmtDateTime(entry.updatedAt)}</span>
                  )}
                </div>
                {entry?.reportId && (
                  <Button variant="outline" size="touch" className="w-full sm:w-auto" onClick={() => setViewing(true)}>
                    <ImageIcon weight="bold" />
                    View uploaded page
                  </Button>
                )}
              </div>
              <p className="text-xs leading-relaxed text-muted-foreground">
                Each value is saved when you leave its box (or press Enter). Clear a box to remove the value. Hours as h:mm.
              </p>
            </div>

            {!entry && loaded && (
              <Notice tone="attention" title="Nothing is stored for this day yet.">
                Values typed here are saved as entered by hand. To read them from the report instead, upload the page dated{' '}
                {fmtDate(next, 'short')}.
              </Notice>
            )}

            {errorList.length > 0 && (
              <Notice tone="error" title="Some changes were not saved">
                {errorList.map(([f, m]) => (
                  <div key={f}>{m}</div>
                ))}
              </Notice>
            )}

            {DETAIL_GROUPS.map((group) => {
              const hasPairs = group.rows.some((r) => r.u1 && fieldKind(r.u1) !== 'text');
              return (
                <section key={group.title}>
                  <div className="mb-1 flex items-end gap-2">
                    <MicroLabel as="h3" className="flex-1">
                      {group.title}
                    </MicroLabel>
                    {hasPairs && (
                      <>
                        <span className={`${PAIR_W} text-right text-[10px] font-medium uppercase tracking-widest text-muted-foreground`}>
                          Unit 1
                        </span>
                        <span className={`${PAIR_W} text-right text-[10px] font-medium uppercase tracking-widest text-muted-foreground`}>
                          Unit 2
                        </span>
                      </>
                    )}
                  </div>
                  <div>
                    {group.rows.map((row) => {
                      const text = row.u1 && fieldKind(row.u1) === 'text';
                      const sum = stationSum(row, entry);
                      const labelBlock = (
                        <div className="min-w-0 flex-1">
                          <div className="text-sm leading-snug">
                            {row.label}
                            {row.unit && ' '}
                            {row.unit && <span className="ml-0.5 whitespace-nowrap text-[11px] text-muted-foreground">{row.unit}</span>}
                          </div>
                          {row.extra && (
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Not on the page</div>
                          )}
                          {sum && <div className="text-[11px] text-muted-foreground tabular">Station {sum}</div>}
                        </div>
                      );
                      if (text) {
                        return (
                          <div key={row.label} className="space-y-2 py-2">
                            {labelBlock}
                            <div className="grid gap-3 sm:grid-cols-2 sm:gap-2">
                              {[row.u1, row.u2].map((f, i) => (
                                <div key={f}>
                                  <div className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">
                                    Unit {i + 1}
                                  </div>
                                  <Field field={f} entry={entry} state={states[f]} onSave={save} label={`${row.label}, unit ${i + 1}`} />
                                </div>
                              ))}
                            </div>
                          </div>
                        );
                      }
                      return (
                        <div key={row.label} className="flex items-center gap-2 py-1.5">
                          {labelBlock}
                          {row.u1 ? (
                            <>
                              <Field
                                className={`${PAIR_W} shrink-0`}
                                field={row.u1}
                                entry={entry}
                                state={states[row.u1]}
                                onSave={save}
                                label={`${row.label}, unit 1`}
                              />
                              <Field
                                className={`${PAIR_W} shrink-0`}
                                field={row.u2}
                                entry={entry}
                                state={states[row.u2]}
                                onSave={save}
                                label={`${row.label}, unit 2`}
                              />
                            </>
                          ) : (
                            <Field
                              className={`${SINGLE_W} shrink-0`}
                              field={row.field}
                              entry={entry}
                              state={states[row.field]}
                              onSave={save}
                              label={row.label}
                            />
                          )}
                        </div>
                      );
                    })}
                  </div>
                </section>
              );
            })}
          </div>
        </div>

        {/* Day to day at the bottom, where a thumb reaches. */}
        <div className="grid grid-cols-2 gap-2 border-t border-border px-4 pb-[calc(0.75rem_+_env(safe-area-inset-bottom))] pt-3 md:px-6">
          <Button variant="outline" size="touch" className="justify-start" onClick={() => onNavigate(prev)} aria-label={`Previous day, ${fmtDate(prev, 'weekday')}`}>
            <CaretLeftIcon weight="bold" />
            {fmtDate(prev, 'weekday')}
          </Button>
          <Button
            variant="outline"
            size="touch"
            className="justify-end"
            onClick={() => onNavigate(next)}
            disabled={next > today}
            aria-label={`Next day, ${fmtDate(next, 'weekday')}`}
          >
            {fmtDate(next, 'weekday')}
            <CaretRightIcon weight="bold" />
          </Button>
        </div>
      </div>

      {viewing && entry?.reportId && (
        <ImageViewer
          src={apiUrl(`/reports/${entry.reportId}/image`)}
          title={`Uploaded page with the data for ${fmtDate(date, 'medium')}`}
          onClose={() => setViewing(false)}
        />
      )}
    </div>,
    document.body
  );
}
