import { useRef, useState } from 'react';
import { FileSpreadsheet, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Notice } from '@/components/common/Notice';
import { MicroLabel } from '@/components/common/Text';
import { api } from '@/lib/api';
import { fmtDate, fyLabel } from '@/lib/format';

/** One-time load of history from the plant's "TTPS DAILY GEN DATA" workbook. */
export function ImportWorkbook({ onImported }) {
  const inputRef = useRef(null);
  const [state, setState] = useState({ status: 'idle' });

  const upload = async (file) => {
    if (!file) return;
    setState({ status: 'working', name: file.name });
    const form = new FormData();
    form.append('file', file, file.name);
    try {
      const result = await api('/import/workbook', { method: 'POST', body: form });
      setState({ status: 'done', name: file.name, result });
      onImported?.(result);
    } catch (err) {
      setState({ status: 'error', name: file.name, error: err.message });
    }
  };

  const r = state.result;

  return (
    <Card className="space-y-4 p-4 md:p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <MicroLabel>Import workbook</MicroLabel>
          <p className="max-w-xl text-sm text-muted-foreground">
            One-time load of earlier days from the plant&apos;s Excel workbook (the DAILY DATA sheet, .xlsx). Days already
            read from a report page keep their values; the workbook only fills in what is missing, such as GCV and trips.
          </p>
        </div>
        <Button
          variant="outline"
          className="shrink-0"
          disabled={state.status === 'working'}
          onClick={() => inputRef.current?.click()}
        >
          {state.status === 'working' ? <Loader2 className="animate-spin" /> : <FileSpreadsheet />}
          {state.status === 'working' ? 'Importing' : 'Choose .xlsx file'}
        </Button>
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          className="hidden"
          onChange={(e) => {
            upload(e.target.files?.[0]);
            e.target.value = '';
          }}
        />
      </div>

      {state.status === 'working' && (
        <p className="text-sm text-muted-foreground">Reading {state.name}…</p>
      )}
      {state.status === 'error' && (
        <Notice tone="error" title={`${state.name} was not imported`}>
          {state.error}
        </Notice>
      )}
      {state.status === 'done' && r && (
        <Notice tone="success" title={`Imported ${fyLabel(r.fy)} from ${state.name}`}>
          The workbook has {r.days} day{r.days === 1 ? '' : 's'}
          {r.from && r.to && (
            <>
              {' '}
              ({fmtDate(r.from, 'medium')} to {fmtDate(r.to, 'medium')})
            </>
          )}
          . <strong>{r.added}</strong> new day{r.added === 1 ? ' was' : 's were'} added and <strong>{r.updated}</strong>{' '}
          existing day{r.updated === 1 ? ' was' : 's were'} filled in
          {r.days - r.added - r.updated > 0 && <>; {r.days - r.added - r.updated} already had every value the workbook carries</>}.
        </Notice>
      )}
    </Card>
  );
}
