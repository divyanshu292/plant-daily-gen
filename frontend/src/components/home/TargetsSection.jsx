import { useState } from 'react';
import { MicroLabel } from '@/components/common/Text';
import { DailyBars } from '@/components/home/charts';
import { UNIT_MW } from '@/components/home/LivePanel';
import { fmtDate, fmtNum } from '@/lib/format';
import { cn } from '@/lib/utils';

// Station at full load for a whole day: 2 units x 210 MW x 24 h.
const FULL_LOAD_MU = (UNIT_MW * 2 * 24) / 1000;

function mu(value) {
  if (value == null) return '—';
  return fmtNum(value, Math.abs(value) >= 1000 ? 0 : 1);
}

export function TargetsSection({ progress, days }) {
  const month = progress?.month;
  const year = progress?.year;
  return (
    <section aria-labelledby="targets-heading" className="space-y-4">
      <MicroLabel as="h2" id="targets-heading">
        Targets
      </MicroLabel>
      <div className="space-y-5">
        {month && <TargetProgress p={month} />}
        {year && <TargetProgress p={year} />}
      </div>
      <GenerationBars days={days.slice(-30)} asking={month?.askingRate ?? null} />
    </section>
  );
}

function TargetProgress({ p }) {
  const hasTarget = p.target != null && p.target > 0;
  const share = hasTarget ? Math.min(1, Math.max(0, p.gen / p.target)) : 0;
  const pace = hasTarget && p.expected != null ? Math.min(1, Math.max(0, p.expected / p.target)) : null;
  const behind = hasTarget && p.askingRate != null && p.recentRate != null && p.askingRate > p.recentRate;
  const outOfReach = p.askingRate != null && p.askingRate > FULL_LOAD_MU;

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <span className="truncate text-sm font-medium">{p.label}</span>
        <span className="shrink-0 text-sm tabular">
          {mu(p.gen)}
          <span className="text-muted-foreground">{hasTarget ? ` / ${mu(p.target)} MU` : ' MU'}</span>
        </span>
      </div>

      {hasTarget ? (
        <div
          className="relative h-1.5 rounded-full bg-muted"
          role="meter"
          aria-label={`${p.label}: ${mu(p.gen)} of ${mu(p.target)} MU${pace != null ? `, expected by now ${mu(p.expected)} MU` : ''}`}
          aria-valuemin={0}
          aria-valuemax={p.target}
          aria-valuenow={p.gen}
        >
          <div className="h-full rounded-full bg-foreground" style={{ width: `${share * 100}%` }} />
          {pace != null && (
            <div
              className="absolute -top-1 h-3.5 w-0.5 -translate-x-1/2 rounded-full bg-foreground shadow-[0_0_0_2px_hsl(var(--background))]"
              style={{ left: `${pace * 100}%` }}
              title={`Expected by now: ${mu(p.expected)} MU`}
            />
          )}
        </div>
      ) : (
        <div className="text-xs text-muted-foreground">No target set for this period.</div>
      )}

      {hasTarget && (
        <div className="flex items-baseline justify-between gap-3 text-xs text-muted-foreground tabular">
          <span className="min-w-0">
            {p.askingRate != null ? (
              <>
                Needs <span className={cn('font-medium', behind ? 'text-attention' : 'text-foreground')}>{fmtNum(p.askingRate, 2)}</span> MU/day
                {outOfReach ? ', above full load' : ''}
                {p.recentRate != null && (
                  <>
                    {' · '}running <span className="text-foreground">{fmtNum(p.recentRate, 2)}</span>
                  </>
                )}
              </>
            ) : p.gen >= p.target ? (
              'Target met'
            ) : (
              'Period over'
            )}
          </span>
          <span className="shrink-0">
            {pace != null && (p.gen >= p.expected ? `${mu(p.gen - p.expected)} MU ahead` : `${mu(p.expected - p.gen)} MU behind`)}
          </span>
        </div>
      )}
    </div>
  );
}

function GenerationBars({ days, asking }) {
  const [selected, setSelected] = useState(null);
  if (!days.length) return null;
  const last = days.length - 1;
  const day = days[selected ?? last];

  return (
    <div className="space-y-1.5 pt-1">
      <div className="flex items-baseline justify-between gap-3 text-[11px] text-muted-foreground tabular">
        <span className="min-w-0 truncate">
          {fmtDate(day.date, 'weekday')} ·{' '}
          {day.hasData && day.gen != null ? (
            <span className="font-medium text-foreground">{fmtNum(day.gen, 2)} MU</span>
          ) : (
            <span className="text-attention">no data</span>
          )}
        </span>
        {asking != null && (
          <span className="inline-flex shrink-0 items-center gap-1.5">
            <svg width="14" height="2" aria-hidden="true">
              <line x1="0" x2="14" y1="1" y2="1" strokeWidth="1" strokeDasharray="3 2" className="stroke-foreground" />
            </svg>
            needs {fmtNum(asking, 2)}/day
          </span>
        )}
      </div>
      <DailyBars days={days} reference={asking} selected={selected ?? last} onSelect={setSelected} />
      <div className="flex justify-between text-[10px] text-muted-foreground">
        <span>{fmtDate(days[0].date, 'short')}</span>
        <span>Daily generation, MU</span>
        <span>{fmtDate(days[last].date, 'short')}</span>
      </div>
    </div>
  );
}
