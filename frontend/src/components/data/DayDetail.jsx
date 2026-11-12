import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { ChevronLeft, ChevronRight, Image as ImageIcon, X } from 'lucide-react';
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

  const next = addDays(date, 1);
  const errorList = Object.entries(errors).filter(([, m]) => m);

  return createPortal(
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={`Data for ${fmtDate(date, 'long')}`}>
      <div className="absolute inset-0 bg-black/50 animate-fade-in" onClick={onClose} />
      <div className="absolute inset-y-0 right-0 flex w-full flex-col border-l border-border bg-background shadow-2xl duration-200 animate-in slide-in-from-right-8 sm:max-w-xl">
        <div className="flex items-start gap-3 border-b border-border px-4 py-3 md:px-6 md:py-4">
          <div className="min-w-0 flex-1">
            <MicroLabel>Data for the day</MicroLabel>
            <div className="mt-1 text-xl font-semibold tracking-tight md:text-2xl">{fmtDate(date, 'long')}</div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <Button variant="outline" size="icon" onClick={() => onNavigate(addDays(date, -1))} aria-label="Previous day">
              <ChevronLeft />
            </Button>
            <Button variant="outline" size="icon" onClick={() => onNavigate(next)} disabled={next > today} aria-label="Next day">
              <ChevronRight />
            </Button>
            <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close">
              <X />
            </Button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto scroll-thin">
          <div className="space-y-6 px-4 py-4 md:px-6 md:py-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm">
                <SourceMarker status={status} />
                <span>{STATUS_TEXT[status]}</span>
                {entry?.updatedAt && (
                  <span className="text-xs text-muted-foreground">· changed {fmtDateTime(entry.updatedAt)}</span>
                )}
              </div>
              {entry?.reportId && (
                <Button variant="outline" size="sm" onClick={() => setViewing(true)}>
                  <ImageIcon />
                  View uploaded page
                </Button>
              )}
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
                  <div className="mb-1 flex items-end gap-2 border-b border-border pb-2">
                    <MicroLabel className="flex-1">{group.title}</MicroLabel>
                    {hasPairs && (
                      <>
                        <span className="w-24 text-right text-[10px] font-medium uppercase tracking-widest text-muted-foreground sm:w-28">
                          Unit 1
                        </span>
                        <span className="w-24 text-right text-[10px] font-medium uppercase tracking-widest text-muted-foreground sm:w-28">
                          Unit 2
                        </span>
                      </>
                    )}
                  </div>
                  <div className="divide-y divide-border/50">
                    {group.rows.map((row) => {
                      const text = row.u1 && fieldKind(row.u1) === 'text';
                      const sum = stationSum(row, entry);
                      const labelBlock = (
                        <div className="min-w-0 flex-1">
                          <div className="text-sm leading-snug">
                            {row.label}
                            {row.unit && <span className="ml-1.5 text-xs text-muted-foreground">{row.unit}</span>}
                          </div>
                          {row.extra && (
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Not on the page</div>
                          )}
                          {sum && <div className="text-[11px] text-muted-foreground tabular">Station {sum}</div>}
                        </div>
                      );
                      if (text) {
                        return (
                          <div key={row.label} className="space-y-2 py-2.5">
                            {labelBlock}
                            <div className="grid gap-2 sm:grid-cols-2">
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
                        <div key={row.label} className="flex items-center gap-2 py-2.5">
                          {labelBlock}
                          {row.u1 ? (
                            <>
                              <Field
                                className="w-24 shrink-0 sm:w-28"
                                field={row.u1}
                                entry={entry}
                                state={states[row.u1]}
                                onSave={save}
                                label={`${row.label}, unit 1`}
                              />
                              <Field
                                className="w-24 shrink-0 sm:w-28"
                                field={row.u2}
                                entry={entry}
                                state={states[row.u2]}
                                onSave={save}
                                label={`${row.label}, unit 2`}
                              />
                            </>
                          ) : (
                            <Field
                              className="w-[12.5rem] shrink-0 sm:w-[14.5rem]"
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

        <div className="border-t border-border px-4 py-3 text-xs text-muted-foreground md:px-6">
          Each value is saved when you leave its box (or press Enter). Clear a box to remove the value. Hours as h:mm.
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
