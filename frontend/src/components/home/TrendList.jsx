import { useState } from 'react';
import { ArrowDownRightIcon, ArrowRightIcon, ArrowUpRightIcon, CaretDownIcon } from '@phosphor-icons/react';
import { MicroLabel } from '@/components/common/Text';
import { Sparkline, TrendChart } from '@/components/home/charts';
import { fmtNum } from '@/lib/format';
import { cn } from '@/lib/utils';

/** What a move in each metric usually means on the plant floor. */
const HINTS = {
  plf: 'How much of the full 420 MW the station actually generated. Falling PLF means outages, backing down or units held at part load.',
  availability: 'Hours the units were ready to run. Falling availability means more forced or planned outage hours.',
  spCoal: 'Coal burnt per unit generated. Rising means efficiency is falling or the coal is poorer (lower GCV, more ash or moisture).',
  heatRate: 'Heat in per kWh out. Rising means the cycle is less efficient: check condenser vacuum, air heaters, unburnt carbon and the coal GCV.',
  apcPct: 'Auxiliary power as a share of generation. Rising means mills, fans and pumps are drawing more, or the units are running at part load.',
  spOil: 'Support oil per unit generated. Rising points to unstable firing, wet or poor coal, or more start-ups after trips.',
  dmPct: 'DM water make-up against steam raised. Rising points to steam or water leaks, passing drains and vents, or extra blowdown.',
};

const STATUS_TEXT = {
  worse: 'text-attention',
  better: 'text-foreground',
  steady: 'text-muted-foreground',
};

/** Index in `days` where the last `n` days with data begin. */
export function recentStart(days, n = 7) {
  let seen = 0;
  for (let i = days.length - 1; i >= 0; i--) {
    if (days[i].hasData) seen += 1;
    if (seen === n) return i;
  }
  return 0;
}

function Change({ trend, className }) {
  const { change, status, decimals = 2 } = trend;
  if (change == null) return <span className={cn('text-muted-foreground', className)}>—</span>;
  const zero = Math.abs(change) < 0.5 * 10 ** -decimals;
  const Icon = zero ? ArrowRightIcon : change > 0 ? ArrowUpRightIcon : ArrowDownRightIcon;
  return (
    <span className={cn('inline-flex items-center gap-0.5 tabular', STATUS_TEXT[status] || STATUS_TEXT.steady, className)}>
      <Icon weight="bold" className="h-3 w-3 shrink-0" aria-hidden="true" />
      {fmtNum(Math.abs(change), decimals)}
      <span className="sr-only">{` ${change > 0 ? 'up' : 'down'}, ${status}`}</span>
    </span>
  );
}

export function TrendList({ trends, days }) {
  const [open, setOpen] = useState(null);
  const from = recentStart(days);

  return (
    <section aria-labelledby="trends-heading" className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <MicroLabel as="h2" id="trends-heading">
          Trends
        </MicroLabel>
        <span className="text-[11px] text-muted-foreground">Last 7 days vs the 30 before</span>
      </div>
      <ul className="divide-y divide-border border-y border-border">
        {trends.map((t) => (
          <TrendRow
            key={t.key}
            trend={t}
            days={days}
            from={from}
            open={open === t.key}
            onToggle={() => setOpen((k) => (k === t.key ? null : t.key))}
          />
        ))}
      </ul>
    </section>
  );
}

function TrendRow({ trend, days, from, open, onToggle }) {
  const values = days.map((d) => (d.hasData ? d[trend.key] ?? null : null));
  const tone = trend.status === 'worse' ? 'attention' : 'default';
  const panelId = `trend-${trend.key}`;

  return (
    <li>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={panelId}
        className="grid min-h-[52px] w-full grid-cols-[5.5rem_minmax(0,1fr)_5.25rem] items-center gap-3 py-2 text-left transition-colors hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      >
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium leading-tight">{trend.label}</span>
          <span className="block truncate text-[11px] leading-tight text-muted-foreground">{trend.unit}</span>
        </span>
        <Sparkline values={values} recentFrom={from} tone={tone} height={28} />
        <span className="flex flex-col items-end leading-tight">
          <span className="text-sm font-medium tabular">{fmtNum(trend.recent, trend.decimals)}</span>
          <span className="flex items-center gap-1 text-[11px]">
            <Change trend={trend} />
            <CaretDownIcon weight="bold" className={cn('h-3 w-3 text-muted-foreground transition-transform', open && 'rotate-180')} aria-hidden="true" />
          </span>
        </span>
      </button>
      {open && (
        <div id={panelId} className="space-y-3 pb-4 pt-1 animate-fade-in">
          <TrendChart
            days={days}
            metric={trend.key}
            baseline={trend.baseline}
            recentFrom={from}
            tone={tone}
            decimals={trend.decimals}
            unit={trend.unit}
          />
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground tabular">
            <span className="inline-flex items-center gap-1.5">
              <svg width="14" height="2" aria-hidden="true">
                <line x1="0" x2="14" y1="1" y2="1" strokeWidth="2" className={tone === 'attention' ? 'stroke-attention' : 'stroke-foreground'} />
              </svg>
              Last 7 days <span className="font-medium text-foreground">{fmtNum(trend.recent, trend.decimals)}</span>
            </span>
            <span className="inline-flex items-center gap-1.5">
              <svg width="14" height="2" aria-hidden="true">
                <line x1="0" x2="14" y1="1" y2="1" strokeWidth="1" strokeDasharray="3 2" className="stroke-foreground" />
              </svg>
              30 days before <span className="font-medium text-foreground">{fmtNum(trend.baseline, trend.decimals)}</span>
            </span>
            {trend.changePct != null && (
              <span>
                {trend.changePct > 0 ? '+' : '−'}
                {fmtNum(Math.abs(trend.changePct), 1)} %
              </span>
            )}
          </div>
          {HINTS[trend.key] && <p className="text-xs leading-relaxed text-muted-foreground">{HINTS[trend.key]}</p>}
        </div>
      )}
    </li>
  );
}
