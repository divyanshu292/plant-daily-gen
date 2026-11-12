import { useState } from 'react';
import { ArrowRightIcon, CalendarDotsIcon, FileTextIcon, ImageIcon } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/common/Notice';
import { ImageViewer, imageKept } from '@/components/common/ImageViewer';
import { PrintedForm } from '@/components/upload/PrintedForm';
import { ChecksSummary } from '@/components/upload/ChecksList';
import { apiUrl } from '@/lib/api';
import { fieldKind, fieldLabel } from '@/lib/fields';
import { fmtDate, fmtDayList, fmtHours, fmtTrim, monthLabel } from '@/lib/format';

function fmtField(field, value) {
  if (value == null) return 'blank';
  const kind = fieldKind(field);
  if (kind === 'hours') return fmtHours(value);
  if (kind === 'text') return `“${value}”`;
  return fmtTrim(value, 5);
}

function differs(a, b) {
  if (a == null || b == null) return a !== b;
  if (typeof a === 'number' && typeof b === 'number') return Math.abs(a - b) > 1e-9;
  return a !== b;
}

/** Changes against the earlier data, using the values actually saved (after any correction). */
function savedChanges(report) {
  return (report.changes || [])
    .map((c) => ({ ...c, after: report.entry?.[c.field] ?? c.after }))
    .filter((c) => differs(c.before, c.after));
}

/** Full-width, finger-sized on a phone; compact in a row from sm up. */
const ACTION = 'h-11 justify-start px-4 text-sm sm:h-8 sm:justify-center sm:px-3 sm:text-xs';

export function SavedResult({ report, navigate }) {
  const [viewing, setViewing] = useState(false);
  const day = report.dataDate;
  const confirmed = !!report.confirmedAt;
  const changes = savedChanges(report);
  const missing = report.missingDays || [];

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <div className="text-xl font-semibold tracking-tight md:text-2xl">Saved the figures for {fmtDate(day, 'long')}</div>
        <div className="text-sm text-muted-foreground">
          {report.reportDate ? <>Read from the page dated {fmtDate(report.reportDate, 'medium')}</> : 'Read from the uploaded page'}
          {confirmed ? ', with your corrections.' : '. The page added up, so it was saved without changes.'}
        </div>
      </div>

      {report.replaced &&
        (changes.length > 0 ? (
          <Notice tone="attention" title={`${fmtDate(day, 'short')} already had data. These values changed:`}>
            <ul className="mt-1 space-y-0.5">
              {changes.map((c) => (
                <li key={c.field} className="tabular">
                  <span className="text-foreground">{fieldLabel(c.field)}:</span> {fmtField(c.field, c.before)}{' '}
                  <ArrowRightIcon weight="bold" className="inline h-3 w-3" /> <strong>{fmtField(c.field, c.after)}</strong>
                </li>
              ))}
            </ul>
          </Notice>
        ) : (
          <Notice tone="info" title={`${fmtDate(day, 'short')} already had data. The page gave the same values.`} />
        ))}

      {missing.length > 0 && (
        <Notice
          tone="attention"
          title={`${missing.length === 1 ? '1 earlier day' : `${missing.length} earlier days`} of ${monthLabel(day.slice(0, 7))} still ${missing.length === 1 ? 'has' : 'have'} no data`}
          action={
            <Button variant="outline" size="sm" onClick={() => navigate(`data/${day.slice(0, 7)}`)}>
              <CalendarDotsIcon weight="bold" />
              See the month
            </Button>
          }
        >
          Missing: {fmtDayList(missing)}. Upload those pages (they carry the previous day's figures) or enter the values in Data.
        </Notice>
      )}

      <div className="space-y-2">
        <div className="text-[11px] font-medium uppercase tracking-widest text-muted-foreground">
          {confirmed ? 'Values on the page (corrections shown)' : 'Values read from the page'}
        </div>
        <PrintedForm raw={report.raw} entry={report.entry} showCorrections={confirmed} />
      </div>

      <ChecksSummary
        checks={report.checks}
        note={confirmed ? 'Worked out on the values as first read, before your corrections.' : undefined}
      />

      <div className="grid gap-2 sm:flex sm:flex-wrap">
        <Button variant="outline" size="sm" className={ACTION} onClick={() => navigate(`daily/${day}`)}>
          <FileTextIcon weight="bold" />
          Daily report for {fmtDate(day, 'short')}
        </Button>
        <Button variant="outline" size="sm" className={ACTION} onClick={() => navigate(`data/${day}`)}>
          <CalendarDotsIcon weight="bold" />
          Edit in Data
        </Button>
        {imageKept(report) && (
          <Button variant="ghost" size="sm" className={ACTION} onClick={() => setViewing(true)}>
            <ImageIcon weight="bold" />
            View page
          </Button>
        )}
      </div>

      {viewing && (
        <ImageViewer
          src={apiUrl(`/reports/${report.id}/image`)}
          title={report.reportDate ? `Page dated ${fmtDate(report.reportDate, 'medium')}` : report.fileName || 'Uploaded page'}
          onClose={() => setViewing(false)}
        />
      )}
    </div>
  );
}
