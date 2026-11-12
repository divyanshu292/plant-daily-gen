// Small inline-SVG charts for the Home screen. Monochrome: marks use the
// foreground / muted-foreground tokens, `attention` only for what needs a look.
import { useLayoutEffect, useRef, useState } from 'react';
import { fmtDate, fmtNum } from '@/lib/format';
import { cn } from '@/lib/utils';

/** Width of an element in CSS px, kept up to date with a ResizeObserver. */
export function useWidth() {
  const ref = useRef(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    setWidth(Math.floor(el.getBoundingClientRect().width));
    const ro = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}

function extent(values, extra = []) {
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of [...values, ...extra]) {
    if (v == null || !Number.isFinite(v)) continue;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (lo === Infinity) return [0, 1];
  if (lo === hi) {
    const pad = Math.abs(lo) * 0.05 || 1;
    return [lo - pad, hi + pad];
  }
  return [lo, hi];
}

/** SVG path through the values, lifting the pen over nulls; lone points come back separately. */
function linePath(values, x, y, from = 0) {
  let d = '';
  const singles = [];
  for (let i = from; i < values.length; i++) {
    const v = values[i];
    if (v == null) continue;
    const prev = i > from ? values[i - 1] : null;
    const next = i + 1 < values.length ? values[i + 1] : null;
    if (prev == null && next == null) singles.push(i);
    d += `${prev == null ? 'M' : 'L'}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
  }
  return { d, singles };
}

function lastIndex(values) {
  for (let i = values.length - 1; i >= 0; i--) if (values[i] != null) return i;
  return -1;
}

/** Column with a rounded data end and a square foot on the baseline. */
function barPath(x, top, w, h, r) {
  const rr = Math.max(0, Math.min(r, w / 2, h));
  return `M${x},${top + h}V${top + rr}Q${x},${top} ${x + rr},${top}H${x + w - rr}Q${x + w},${top} ${x + w},${top + rr}V${top + h}Z`;
}

const toneStroke = { attention: 'stroke-attention', default: 'stroke-foreground' };
const toneFill = { attention: 'fill-attention', default: 'fill-foreground' };

/**
 * Tiny line: the whole series in a quiet grey, the stretch from `recentFrom`
 * drawn stronger (in `attention` when tone says so), and a dot on the last value.
 */
export function Sparkline({ values, recentFrom = values.length, tone = 'default', height = 28, className }) {
  const [ref, width] = useWidth();
  const pad = 4;
  const [lo, hi] = extent(values);
  const x = (i) => pad + (i * (width - pad * 2)) / Math.max(1, values.length - 1);
  const y = (v) => pad + (1 - (v - lo) / (hi - lo)) * (height - pad * 2);
  const base = width ? linePath(values, x, y) : null;
  const recent = width ? linePath(values, x, y, Math.max(0, recentFrom)) : null;
  const end = lastIndex(values);

  return (
    <div ref={ref} className={cn('w-full', className)} style={{ height }}>
      {width > 0 && (
        <svg width={width} height={height} aria-hidden="true" className="block overflow-visible">
          {recentFrom < values.length && (
            <rect x={x(recentFrom) - 2} y={0} width={width - x(recentFrom) + 2} height={height} rx={2} className="fill-foreground" fillOpacity={0.06} />
          )}
          <path d={base.d} fill="none" strokeWidth={1.25} strokeLinejoin="round" strokeLinecap="round" className="stroke-muted-foreground" strokeOpacity={0.45} />
          {base.singles.map((i) => (
            <circle key={i} cx={x(i)} cy={y(values[i])} r={1.25} className="fill-muted-foreground" fillOpacity={0.6} />
          ))}
          <path d={recent.d} fill="none" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" className={toneStroke[tone]} />
          {end >= 0 && <circle cx={x(end)} cy={y(values[end])} r={2.75} className={toneFill[tone]} />}
        </svg>
      )}
    </div>
  );
}

/** Nearest index under the pointer, for scrubbing a chart by touch or mouse. */
function indexAt(event, count, left, plotWidth) {
  const rect = event.currentTarget.getBoundingClientRect();
  const px = event.clientX - rect.left - left;
  const i = Math.round((px / plotWidth) * (count - 1));
  return Math.max(0, Math.min(count - 1, i));
}

/**
 * Larger trend chart: max/min on the right, dashed baseline, last-7-day stretch
 * emphasised, first/last date below, and a crosshair readout while scrubbing.
 */
export function TrendChart({ days, metric, baseline, recentFrom, tone = 'default', decimals = 2, unit }) {
  const [ref, width] = useWidth();
  const [active, setActive] = useState(null);
  const values = days.map((d) => (d.hasData ? d[metric] ?? null : null));
  const height = 148;
  const top = 10;
  const bottom = 22;
  const gutter = 52;
  const plotW = Math.max(10, width - gutter);
  const plotH = height - top - bottom;
  const [lo, hi] = extent(values);
  const x = (i) => (i * plotW) / Math.max(1, values.length - 1);
  const y = (v) => top + (1 - (v - lo) / (hi - lo)) * plotH;
  const base = width ? linePath(values, x, y) : null;
  const recent = width ? linePath(values, x, y, Math.max(0, recentFrom)) : null;
  const end = lastIndex(values);
  const inRange = baseline != null && baseline >= lo && baseline <= hi;
  const shown = active ?? null;

  const onMove = (e) => setActive(indexAt(e, values.length, 0, plotW));

  return (
    <div className="relative">
      <div className="mb-1 flex h-4 items-baseline justify-between text-[11px] text-muted-foreground tabular">
        {shown != null ? (
          <span>
            {fmtDate(days[shown].date, 'weekday')} ·{' '}
            {values[shown] != null ? (
              <span className="font-medium text-foreground">
                {fmtNum(values[shown], decimals)} {unit}
              </span>
            ) : (
              'no data'
            )}
          </span>
        ) : (
          <span>{days.length} days · slide across the chart to read a day</span>
        )}
      </div>
      <div ref={ref} style={{ height }} className="touch-pan-y select-none">
        {width > 0 && (
          <svg
            width={width}
            height={height}
            className="block"
            role="img"
            aria-label={`${values.filter((v) => v != null).length} daily values from ${fmtDate(days[0].date, 'short')} to ${fmtDate(days[days.length - 1].date, 'short')}, between ${fmtNum(lo, decimals)} and ${fmtNum(hi, decimals)} ${unit}`}
            onPointerMove={onMove}
            onPointerDown={onMove}
            onPointerLeave={() => setActive(null)}
          >
            {recentFrom < values.length && (
              <rect x={x(recentFrom) - 3} y={top} width={plotW - x(recentFrom) + 3} height={plotH} className="fill-foreground" fillOpacity={0.05} />
            )}
            <line x1={0} x2={plotW} y1={y(hi)} y2={y(hi)} className="stroke-border" strokeWidth={1} />
            <line x1={0} x2={plotW} y1={y(lo)} y2={y(lo)} className="stroke-border" strokeWidth={1} />
            <text x={width} y={y(hi) + 3.5} textAnchor="end" className="fill-muted-foreground text-[10px] tabular">
              {fmtNum(hi, decimals)}
            </text>
            <text x={width} y={y(lo) + 3.5} textAnchor="end" className="fill-muted-foreground text-[10px] tabular">
              {fmtNum(lo, decimals)}
            </text>
            {inRange && (
              <line x1={0} x2={plotW} y1={y(baseline)} y2={y(baseline)} className="stroke-foreground" strokeOpacity={0.55} strokeWidth={1} strokeDasharray="3 3" />
            )}
            <path d={base.d} fill="none" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" className="stroke-muted-foreground" strokeOpacity={0.6} />
            {base.singles.map((i) => (
              <circle key={i} cx={x(i)} cy={y(values[i])} r={1.5} className="fill-muted-foreground" />
            ))}
            <path d={recent.d} fill="none" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" className={toneStroke[tone]} />
            {end >= 0 && shown == null && (
              <circle cx={x(end)} cy={y(values[end])} r={4} strokeWidth={2} className={cn(toneFill[tone], 'stroke-background')} />
            )}
            {shown != null && (
              <g>
                <line x1={x(shown)} x2={x(shown)} y1={top} y2={top + plotH} className="stroke-muted-foreground" strokeWidth={1} />
                {values[shown] != null && (
                  <circle cx={x(shown)} cy={y(values[shown])} r={4} strokeWidth={2} className="fill-foreground stroke-background" />
                )}
              </g>
            )}
            <text x={0} y={height - 6} className="fill-muted-foreground text-[10px]">
              {fmtDate(days[0].date, 'short')}
            </text>
            <text x={plotW} y={height - 6} textAnchor="end" className="fill-muted-foreground text-[10px]">
              {fmtDate(days[days.length - 1].date, 'short')}
            </text>
          </svg>
        )}
      </div>
    </div>
  );
}

/**
 * Daily station generation as thin columns with a dashed reference line
 * (the asking rate). Days without data get a short attention stub.
 * `selected` / `onSelect` let the caller show a readout for the scrubbed day.
 */
export function DailyBars({ days, reference, selected, onSelect, height = 72 }) {
  const [ref, width] = useWidth();
  const count = days.length;
  const top = 4;
  const plotH = height - top;
  const max = Math.max(1, reference ?? 0, ...days.map((d) => d.gen ?? 0)) * 1.06;
  const slot = width / Math.max(1, count);
  const barW = Math.min(24, Math.max(2, slot - Math.max(2, slot * 0.3)));
  const y = (v) => top + (1 - v / max) * plotH;
  const pick = (e) => onSelect?.(indexAt(e, count, slot / 2, width - slot));

  return (
    <div ref={ref} style={{ height }} className="touch-pan-y select-none">
      {width > 0 && (
        <svg
          width={width}
          height={height}
          className="block"
          aria-hidden="true"
          onPointerMove={pick}
          onPointerDown={pick}
          onPointerLeave={() => onSelect?.(null)}
        >
          <line x1={0} x2={width} y1={height - 0.5} y2={height - 0.5} className="stroke-border" strokeWidth={1} />
          {days.map((d, i) => {
            const x = i * slot + (slot - barW) / 2;
            if (!d.hasData || d.gen == null) {
              return <rect key={d.date} x={x} y={height - 2} width={barW} height={2} className="fill-attention" />;
            }
            const h = Math.max(1, height - y(d.gen));
            const on = selected === i;
            return (
              <path
                key={d.date}
                d={barPath(x, height - h, barW, h, 2)}
                className={on ? 'fill-foreground' : 'fill-muted-foreground'}
                fillOpacity={on ? 1 : 0.55}
              />
            );
          })}
          {reference != null && (
            <line x1={0} x2={width} y1={y(reference)} y2={y(reference)} className="stroke-foreground" strokeWidth={1} strokeDasharray="3 3" />
          )}
        </svg>
      )}
    </div>
  );
}
