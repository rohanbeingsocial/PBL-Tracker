import type { ReactNode } from "react";

// Small SVG charts for the dashboards. No chart library: these few shapes are all the
// pages need, and they pick up the theme colours from CSS variables.

export type Tone = "accent" | "up" | "warn" | "down" | "muted";
// Fills for bars, slices and dots; TEXT for icons and numbers, which need more contrast.
export const TONE: Record<Tone, string> = {
  accent: "var(--accent-fill)", up: "var(--up-fill)", warn: "var(--warn-fill)", down: "var(--down-fill)", muted: "var(--border-2)",
};
const TEXT: Record<Tone, string> = {
  accent: "var(--accent)", up: "var(--up)", warn: "var(--warn)", down: "var(--down)", muted: "var(--muted)",
};

const ICONS = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z",
  search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zm9 16-4.3-4.3",
  upload: "M12 16V4m0 0-5 5m5-5 5 5M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2",
  chart: "M4 20V10m6 10V4m6 16v-7m4 7H2",
  review: "M9 11l3 3 8-8M20 12v7a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h11",
  people: "M16 19v-1a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v1M9 10a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zm13 9v-1a4 4 0 0 0-3-3.9M16 3.1a3.5 3.5 0 0 1 0 6.8",
  book: "M4 19.5V5a2 2 0 0 1 2-2h14v16H6.5A2.5 2.5 0 0 0 4 21.5zm0 0A2.5 2.5 0 0 1 6.5 17H20",
  folder: "M3 6a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z",
  check: "M20 6 9 17l-5-5",
  clock: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm0 4v5l3 2",
  cross: "M18 6 6 18M6 6l12 12",
  star: "m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z",
  user: "M20 21v-1a5 5 0 0 0-5-5H9a5 5 0 0 0-5 5v1M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  file: "M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8zm0 0v5h5",
} as const;
export type IconName = keyof typeof ICONS;

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}
         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={ICONS[name]} />
    </svg>
  );
}

export function StatTile({ icon, label, value, hint, tone = "accent" }: {
  icon: IconName; label: string; value: ReactNode; hint?: ReactNode; tone?: Tone;
}) {
  return (
    <div className="tile">
      <div className="tile-icon" style={{ color: TEXT[tone], background: `color-mix(in oklab, ${TONE[tone]} 16%, transparent)` }}>
        <Icon name={icon} size={20} />
      </div>
      <div style={{ minWidth: 0 }}>
        <div className="tile-label">{label}</div>
        <div className="tile-value">{value}</div>
        {hint && <div className="tile-hint">{hint}</div>}
      </div>
    </div>
  );
}

export interface Slice {
  label: string;
  value: number;
  tone: Tone;
}

export function Donut({ slices, size = 150, children }: { slices: Slice[]; size?: number; children?: ReactNode }) {
  const total = slices.reduce((a, s) => a + s.value, 0);
  const r = 15.9155;   // circumference 100, so dash lengths are percentages
  let offset = 25;     // start at 12 o'clock
  return (
    <div className="donut" style={{ width: size, height: size }}>
      <svg viewBox="0 0 42 42" width={size} height={size} role="img"
           aria-label={slices.map((s) => `${s.label} ${s.value}`).join(", ")}>
        <circle cx="21" cy="21" r={r} fill="none" stroke="var(--surface-3)" strokeWidth="5" />
        {total > 0 && slices.filter((s) => s.value > 0).map((s) => {
          const share = (s.value / total) * 100;
          const el = (
            <circle key={s.label} cx="21" cy="21" r={r} fill="none" stroke={TONE[s.tone]} strokeWidth="5"
                    strokeDasharray={`${share} ${100 - share}`} strokeDashoffset={offset}>
              <title>{`${s.label}: ${s.value}`}</title>
            </circle>
          );
          offset -= share;
          return el;
        })}
      </svg>
      {children && <div className="donut-center">{children}</div>}
    </div>
  );
}

// A legend with counts, or (inline) just the colour keys in one line above a chart.
export function Legend({ slices, inline }: { slices: Slice[]; inline?: boolean }) {
  return (
    <div className={inline ? "legend inline" : "legend"}>
      {slices.map((s) => (
        <div key={s.label} className="legend-row">
          <span className="dot" style={{ background: TONE[s.tone] }} />
          <span className="grow soft">{s.label}</span>
          {!inline && <span className="strong">{s.value}</span>}
        </div>
      ))}
    </div>
  );
}

export function Ring({ value, max, size = 56 }: { value: number; max: number; size?: number }) {
  const share = Math.max(0, Math.min(100, (value / max) * 100));
  const tone = share >= 75 ? "up" : share >= 50 ? "accent" : "warn";
  return (
    <div className="donut" style={{ width: size, height: size }}>
      <svg viewBox="0 0 42 42" width={size} height={size} role="img" aria-label={`${value} out of ${max}`}>
        <circle cx="21" cy="21" r="15.9155" fill="none" stroke="var(--surface-3)" strokeWidth="4" />
        <circle cx="21" cy="21" r="15.9155" fill="none" stroke={TONE[tone]} strokeWidth="4" strokeLinecap="round"
                strokeDasharray={`${share} ${100 - share}`} strokeDashoffset="25" />
      </svg>
      <div className="donut-center" style={{ fontSize: size > 50 ? 13 : 11, fontWeight: 650 }}>{Math.round(share)}%</div>
    </div>
  );
}

export interface Column {
  label: string;
  parts: { name: string; value: number; tone: Tone }[];
}

// Vertical bars, stacked when a column has several parts.
export function Columns({ columns, height = 180, suffix = "" }: { columns: Column[]; height?: number; suffix?: string }) {
  const max = Math.max(1, ...columns.map((c) => c.parts.reduce((a, p) => a + p.value, 0)));
  const step = niceStep(max);
  const top = Math.ceil(max / step) * step;
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
  return (
    <div className="columns" style={{ height: height + 28 }}>
      <div className="columns-axis" style={{ height }}>
        {ticks.map((t) => <span key={t} style={{ bottom: `${(t / top) * 100}%` }}>{t}{suffix}</span>)}
      </div>
      <div className="columns-plot">
        <div className="columns-grid" style={{ height }}>
          {ticks.map((t) => <span key={t} style={{ bottom: `${(t / top) * 100}%` }} />)}
        </div>
        <div className="columns-bars" style={{ height }}>
          {columns.map((c) => {
            const sum = c.parts.reduce((a, p) => a + p.value, 0);
            return (
              <div key={c.label} className="column" title={`${c.label}: ${c.parts.map((p) => `${p.name} ${p.value}${suffix}`).join(", ")}`}>
                <div className="column-value">{sum ? `${sum}${suffix}` : ""}</div>
                <div className="column-stack" style={{ height: `${(sum / top) * 100}%` }}>
                  {c.parts.filter((p) => p.value > 0).map((p) => (
                    <div key={p.name} style={{ flex: p.value, background: TONE[p.tone] }} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
        <div className="columns-labels">
          {columns.map((c) => <span key={c.label}>{c.label}</span>)}
        </div>
      </div>
    </div>
  );
}

function niceStep(max: number): number {
  const rough = max / 4;
  const pow = 10 ** Math.floor(Math.log10(rough));
  return [1, 2, 5, 10].map((m) => m * pow).find((s) => s >= rough) ?? pow * 10;
}

// Horizontal bars with the label on the left and the number on the right.
export function Bars({ rows, tone = "accent", suffix = "" }: {
  rows: { label: string; value: number; note?: string }[]; tone?: Tone; suffix?: string;
}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div className="bars">
      {rows.map((r) => (
        <div key={r.label} className="bar-row" title={r.note}>
          <span className="soft ellipsis">{r.label}</span>
          <div className="bar-track"><div style={{ width: `${(r.value / max) * 100}%`, background: TONE[tone] }} /></div>
          <span className="strong num">{r.value}{suffix}</span>
        </div>
      ))}
    </div>
  );
}

export function Panel({ title, sub, action, children, flush }: {
  title: string; sub?: string; action?: ReactNode; children: ReactNode; flush?: boolean;
}) {
  return (
    <section className="card panel">
      <div className="panel-head">
        <div className="grow">
          <div className="strong">{title}</div>
          {sub && <div className="small muted">{sub}</div>}
        </div>
        {action}
      </div>
      <div className={flush ? "" : "panel-body"}>{children}</div>
    </section>
  );
}
