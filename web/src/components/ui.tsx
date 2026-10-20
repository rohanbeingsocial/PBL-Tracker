import type { MouseEvent, ReactNode } from "react";
import type { Band, Project, ProjectType, Status } from "../api";
import { useApp } from "../context";
import type { Path } from "../hooks";

export function PageHead({ title, sub, back }: { title: string; sub?: ReactNode; back?: { to: Path; label: string } }) {
  return (
    <div className="head">
      {back && <AppLink to={back.to} className="back">← {back.label}</AppLink>}
      <h1>{title}</h1>
      {sub && <p>{sub}</p>}
    </div>
  );
}

// A normal link (so it can be opened in a new tab) that changes page without a reload.
export function AppLink({ to, className, children }: { to: Path; className?: string; children: ReactNode }) {
  const { go } = useApp();
  const open = (e: MouseEvent) => {
    if (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    go(to);
  };
  return <a href={to} className={className} onClick={open}>{children}</a>;
}

const STATUS_TEXT: Record<Status, string> = { submitted: "Waiting for review", approved: "Approved", rejected: "Rejected" };

export function StatusTag({ status }: { status: Status }) {
  return <span className={`status ${status}`}>{STATUS_TEXT[status]}</span>;
}

// Same cut-offs as similarity_band() in sql/03_functions.sql.
const BAND_TEXT: Record<Band, string> = {
  "near duplicate": "Very close", similar: "Similar", related: "Related", different: "Different",
};

export function Closeness({ band, score }: { band: Band | null; score: number | null }) {
  if (!band || score === null) return null;
  const tone = band === "near duplicate" ? "var(--down)" : band === "similar" ? "var(--warn)" : "var(--muted)";
  return <span className="small" style={{ color: tone, whiteSpace: "nowrap" }}>{BAND_TEXT[band]} ({score.toFixed(2)})</span>;
}

export interface MetricItem {
  label: string;
  value: ReactNode;
  tone?: "accent";
}

export function Metrics({ items }: { items: MetricItem[] }) {
  return (
    <div className="metrics">
      {items.map((m) => (
        <div className="metric" key={m.label}>
          <div className="metric-label">{m.label}</div>
          <div className={`metric-value ${m.tone ?? ""}`}>{m.value}</div>
        </div>
      ))}
    </div>
  );
}

export const TYPE_LABEL = { software: "Software", hardware: "Hardware", both: "Hardware and software" } as const;

export function Tags({ tags, type }: { tags: string[]; type?: ProjectType }) {
  if (!tags.length && !type) return null;
  return (
    <div className="row wrap" style={{ gap: 6 }}>
      {type && <span className="tag">{TYPE_LABEL[type]}</span>}
      {tags.map((t) => <span key={t} className="tag">{t}</span>)}
    </div>
  );
}

// keyword_search() marks the matched words with « »; show them highlighted.
export function Highlighted({ text }: { text: string }) {
  const parts = text.split(/[«»]/);
  return <>{parts.map((part, i) => (i % 2 && part ? <mark key={i}>{part}</mark> : <span key={i}>{part}</span>))}</>;
}

export const FILE_KIND = { report: "Report", ppt: "Presentation" } as const;

export function ProjectCard({ p, extra, snippet }: { p: Project; extra?: ReactNode; snippet?: string | null }) {
  return (
    <AppLink to={`/projects/${p.project_id}`} className="card pad stack row-link">
      <div className="row-top" style={{ gap: 16 }}>
        <div className="grow">
          <div className="strong title" style={{ fontSize: 15 }}>{p.title}</div>
          <div className="meta" style={{ marginTop: 2 }}>
            {p.subject} · {p.academic_year} · {p.faculty}{p.members ? ` · ${p.members}` : ""}
          </div>
        </div>
        {extra}
        {p.status !== "approved" && <StatusTag status={p.status} />}
      </div>
      <div className="small soft pretty">{snippet ? <Highlighted text={snippet} /> : p.abstract}</div>
      <Tags tags={p.tags} type={p.project_type} />
    </AppLink>
  );
}

export function Notice({ tone, kind, children }: { tone: "down" | "warn" | "up" | "info"; kind?: string; children: ReactNode }) {
  return <div className={`notice ${tone}`}>{kind && <b className="kind">{kind}:</b>}{children}</div>;
}

export function Loading() {
  return <div className="loading">Loading…</div>;
}

export function Failed({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <Notice tone="down">
      {message} {retry && <button className="link" onClick={retry}>Try again</button>}
    </Notice>
  );
}

export function Segmented<T extends string>({ options, value, onChange, label, names }: {
  options: readonly T[]; value: T; onChange: (v: T) => void; label: string; names?: Partial<Record<T, string>>;
}) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={o} type="button" role="radio" aria-checked={o === value} className={o === value ? "on" : ""} onClick={() => onChange(o)}>
          {names?.[o] ?? o}
        </button>
      ))}
    </div>
  );
}

export function Toggle({ on, onChange, disabled, children }: {
  on: boolean; onChange: (v: boolean) => void; disabled?: boolean; children: ReactNode;
}) {
  return (
    <button type="button" className={`toggle${on ? " on" : ""}`} role="switch" aria-checked={on} disabled={disabled}
            onClick={() => onChange(!on)}>
      <span className="track"><span className="knob" /></span>
      {children}
    </button>
  );
}
