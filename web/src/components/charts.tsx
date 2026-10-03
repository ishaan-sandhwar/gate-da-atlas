/**
 * Small SVG charts following the project's data-viz rules: bars at most 24px thick with a 4px rounded
 * data end and a square baseline, hairline solid grid, a hover tooltip on every mark, text in ink tokens.
 * Below NARROW px the row labels move above their marks so long section names never clip.
 */
import { useState, type ReactNode } from 'react';
import { barPath, ticks, useWidth } from './chartMath';

const NARROW = 520;
const LABEL_ROW = 17;

export interface Tip {
  x: number;
  y: number;
  content: ReactNode;
}

export function ChartTip({ tip }: { tip: Tip | null }) {
  if (!tip) return null;
  return (
    <div className="chart-tip" role="presentation" style={{ left: Math.min(tip.x + 14, window.innerWidth - 240), top: tip.y + 14 }}>
      {tip.content}
    </div>
  );
}

/** Row label: right-aligned beside the mark on wide charts, left-aligned above it on narrow ones. */
function RowLabel({ narrow, labelWidth, y, children }: { narrow: boolean; labelWidth: number; y: number; children: string }) {
  return (
    <text className="chart__label" x={narrow ? 0 : labelWidth - 10} y={y} textAnchor={narrow ? 'start' : 'end'}>
      {children}
    </text>
  );
}

export interface GroupedRow {
  label: string;
  values: number[];
}

/** Grouped horizontal bars: one group per row, one bar per series (series share an ordinal ramp). */
export function GroupedBars({ rows, series, colors, unit }: { rows: GroupedRow[]; series: string[]; colors: string[]; unit: string }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const narrow = width < NARROW;
  const labelWidth = narrow ? 0 : Math.min(210, width * 0.38);
  const bar = 9;
  const gap = 2;
  const groupHeight = series.length * bar + (series.length - 1) * gap;
  const rowHeight = groupHeight + 18 + (narrow ? LABEL_ROW : 0);
  const top = 6;
  const bottom = 26;
  const height = top + rows.length * rowHeight + bottom;
  const max = Math.max(...rows.flatMap((r) => r.values)) * 1.08;
  const plotWidth = width - labelWidth - 34;
  const x = (v: number) => labelWidth + (v / max) * plotWidth;
  const tickValues = ticks(max, 4);

  return (
    <div ref={ref} onMouseLeave={() => setTip(null)}>
      <div className="split-legend" style={{ marginBottom: 6 }}>
        {series.map((name, s) => (
          <span key={name}>
            <span className="dot" style={{ background: colors[s] }} />
            {name}
          </span>
        ))}
      </div>
      <svg className="chart" width={width} height={height} role="img" aria-label={`Bar chart: ${unit} by ${series.join(', ')}`}>
        <g className="grid">
          {tickValues.map((t) => (
            <line key={t} x1={x(t)} x2={x(t)} y1={top} y2={height - bottom} />
          ))}
        </g>
        {tickValues.map((t) => (
          <text key={t} x={x(t)} y={height - 8} textAnchor="middle" className="num">
            {t}
          </text>
        ))}
        {rows.map((row, r) => {
          const y0 = top + r * rowHeight + 9 + (narrow ? LABEL_ROW : 0);
          const last = row.values[row.values.length - 1];
          return (
            <g key={row.label}>
              <RowLabel narrow={narrow} labelWidth={labelWidth} y={narrow ? y0 - 6 : y0 + groupHeight / 2 + 4}>
                {row.label}
              </RowLabel>
              {row.values.map((value, s) => (
                <path
                  key={series[s]}
                  d={barPath(x(0), x(value), y0 + s * (bar + gap), bar)}
                  fill={colors[s]}
                  onMouseMove={(event) => setTip({ x: event.clientX, y: event.clientY, content: `${row.label}, ${series[s]}: ${value} ${unit}` })}
                />
              ))}
              <text x={x(last) + 6} y={y0 + (series.length - 1) * (bar + gap) + bar - 1} className="num">
                {last}
              </text>
            </g>
          );
        })}
        <line x1={x(0)} x2={x(0)} y1={top} y2={height - bottom} stroke="var(--rule-strong)" />
      </svg>
      <ChartTip tip={tip} />
    </div>
  );
}

/** Two-part bars: asked (solid) and never asked (hatched), with an end label. */
export function CoverageBars({ rows }: { rows: { label: string; asked: number; never: number }[] }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const narrow = width < NARROW;
  const labelWidth = narrow ? 0 : Math.min(210, width * 0.38);
  const bar = 16;
  const rowHeight = 30 + (narrow ? LABEL_ROW : 0);
  const height = rows.length * rowHeight + 8;
  const max = Math.max(...rows.map((r) => r.asked + r.never));
  const plotWidth = width - labelWidth - 130;
  const x = (v: number) => labelWidth + (v / max) * plotWidth;
  return (
    <div ref={ref} onMouseLeave={() => setTip(null)}>
      <svg className="chart" width={width} height={height} role="img" aria-label="Syllabus items asked and never asked, per section">
        <defs>
          <pattern id="hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="5" height="5" fill="var(--hatch-bg)" />
            <line x1="0" y1="0" x2="0" y2="5" stroke="var(--hatch)" strokeWidth="1.2" />
          </pattern>
        </defs>
        {rows.map((row, r) => {
          const y = 4 + r * rowHeight + (narrow ? LABEL_ROW : 0) + (30 - bar) / 2;
          const total = row.asked + row.never;
          const split = x(row.asked);
          return (
            <g key={row.label}>
              <RowLabel narrow={narrow} labelWidth={labelWidth} y={narrow ? y - 6 : y + bar - 3}>
                {row.label}
              </RowLabel>
              <path
                d={row.never ? `M${x(0)},${y}H${split - 1}V${y + bar}H${x(0)}Z` : barPath(x(0), split, y, bar)}
                fill="var(--ramp-3)"
                onMouseMove={(event) => setTip({ x: event.clientX, y: event.clientY, content: `${row.label}: ${row.asked} items asked` })}
              />
              {row.never > 0 && (
                <path
                  d={barPath(split + 1, x(total), y, bar)}
                  fill="url(#hatch)"
                  stroke="var(--hatch)"
                  strokeWidth="1"
                  onMouseMove={(event) => setTip({ x: event.clientX, y: event.clientY, content: `${row.label}: ${row.never} items never asked` })}
                />
              )}
              <text x={x(total) + 8} y={y + bar - 3} className="num">
                {row.never} of {total} never asked
              </text>
            </g>
          );
        })}
      </svg>
      <ChartTip tip={tip} />
    </div>
  );
}

/** Dot (posterior mean) with an interval line per row. */
export function DotIntervals({ rows, unit }: { rows: { label: string; value: number; low: number; high: number; note: string }[]; unit: string }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const narrow = width < NARROW;
  const labelWidth = narrow ? 0 : Math.min(250, width * 0.45);
  const rowHeight = 26 + (narrow ? LABEL_ROW - 3 : 0);
  const top = 4;
  const bottom = 26;
  const height = top + rows.length * rowHeight + bottom;
  const max = Math.max(...rows.map((r) => r.high)) * 1.06;
  const plotWidth = width - labelWidth - 16;
  const x = (v: number) => labelWidth + (v / max) * plotWidth;
  const tickValues = ticks(max, 4);
  return (
    <div ref={ref} onMouseLeave={() => setTip(null)}>
      <svg className="chart" width={width} height={height} role="img" aria-label={`Expected ${unit} with 80% intervals`}>
        <g className="grid">
          {tickValues.map((t) => (
            <line key={t} x1={x(t)} x2={x(t)} y1={top} y2={height - bottom} />
          ))}
        </g>
        {tickValues.map((t) => (
          <text key={t} x={x(t)} y={height - 8} textAnchor="middle" className="num">
            {t}
          </text>
        ))}
        {rows.map((row, r) => {
          const rowTop = top + r * rowHeight;
          const cy = narrow ? rowTop + LABEL_ROW + 5 : rowTop + rowHeight / 2;
          return (
            <g key={row.label} onMouseMove={(event) => setTip({ x: event.clientX, y: event.clientY, content: row.note })}>
              <rect x={0} y={rowTop} width={width} height={rowHeight} fill="transparent" />
              <RowLabel narrow={narrow} labelWidth={labelWidth} y={narrow ? rowTop + LABEL_ROW - 4 : cy + 4}>
                {row.label}
              </RowLabel>
              <line x1={x(row.low)} x2={x(row.high)} y1={cy} y2={cy} stroke="var(--ramp-1)" strokeWidth={3} strokeLinecap="round" />
              <circle cx={x(row.value)} cy={cy} r={5} fill="var(--ramp-4)" stroke="var(--paper)" strokeWidth={2} />
            </g>
          );
        })}
      </svg>
      <ChartTip tip={tip} />
    </div>
  );
}
