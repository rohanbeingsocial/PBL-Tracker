import { useEffect, useState, type ReactNode } from "react";
import type { Link, Project, ProjectFile, ProjectType, Status } from "../api";
import { BAND_CLASS, BAND_COLOR, bandOf } from "../format";

export function PageHead({ eyebrow, title, sub }: { eyebrow: string; title: string; sub?: string }) {
  return (
    <div className="head">
      <div className="eyebrow">{eyebrow}</div>
      <h1>{title}</h1>
      {sub && <p>{sub}</p>}
    </div>
  );
}

export function StatusTag({ status }: { status: Status }) {
  return <span className={`status ${status}`}>{status}</span>;
}

// A bar from 0 to 1 with marks at the 0.35 / 0.50 / 0.70 band edges. It fills in
// after mounting so a new score visibly slides into place.
export function Meter({ score, large, hideLabel }: { score: number; large?: boolean; hideLabel?: boolean }) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    const timer = setTimeout(() => setShown(score), 40);
    return () => clearTimeout(timer);
  }, [score]);
  const band = bandOf(score);
  return (
    <div className={`meter${large ? " lg" : ""}`}>
      {!hideLabel && (
        <div className="meter-label">
          <span className={`meter-band ${BAND_CLASS[band]}`}>{band}</span>
          <span className="meter-score">{score.toFixed(2)}</span>
        </div>
      )}
      <div className="meter-bar" role="img" aria-label={`Similarity ${score.toFixed(2)}, ${band}`}>
        <div className="meter-fill" style={{ width: `${Math.round(shown * 100)}%`, background: BAND_COLOR[band] }} />
        {[35, 50, 70].map((at) => <div key={at} className="meter-tick" style={{ left: `${at}%` }} />)}
      </div>
    </div>
  );
}

export function BigScore({ score, size }: { score: number | null; size: number }) {
  if (score === null) return <div className="big-score muted" style={{ fontSize: size }}>–</div>;
  return <div className={`big-score ${BAND_CLASS[bandOf(score)]}`} style={{ fontSize: size }}>{score.toFixed(2)}</div>;
}

export interface MetricItem {
  label: string;
  value: ReactNode;
  note?: string;
  tone?: "accent" | "down";
}

export function Metrics({ items }: { items: MetricItem[] }) {
  return (
    <div className="metrics">
      {items.map((m) => (
        <div className="metric" key={m.label}>
          <div className="metric-label">{m.label}</div>
          <div className={`metric-value ${m.tone ?? ""}`}>{m.value}</div>
          {m.note && <div className="metric-note">{m.note}</div>}
        </div>
      ))}
    </div>
  );
}

const TYPE_LABEL = { software: "Software", hardware: "Hardware", both: "Hardware + software" } as const;

export function Tags({ tags, type }: { tags: string[]; type?: ProjectType }) {
  if (!tags.length && !type) return null;
  return (
    <div className="row wrap" style={{ gap: 6 }}>
      {type && <span className="tag">{TYPE_LABEL[type]}</span>}
      {tags.length > 0 && <span className="techs">{tags.join(" · ")}</span>}
    </div>
  );
}

// keyword_search() marks the matched words with « »; show them highlighted.
export function Highlighted({ text }: { text: string }) {
  const parts = text.split(/[«»]/);
  return <>{parts.map((part, i) => (i % 2 && part ? <mark key={i}>{part}</mark> : <span key={i}>{part}</span>))}</>;
}

export const FILE_KIND = { report: "Report", ppt: "Presentation" } as const;

// Links and files as plain links. Files download through /api/files, which checks
// the session; the browser sends the cookie along.
export function Resources({ links, files }: { links: Link[]; files: ProjectFile[] }) {
  if (!links.length && !files.length) return null;
  return (
    <div className="row wrap small" style={{ gap: "4px 14px" }}>
      {links.map((l) => <a key={l.link_id} className="link" href={l.url} target="_blank" rel="noopener noreferrer">{l.label} ↗</a>)}
      {files.map((f) => <a key={f.file_id} className="link" href={`/api/files/${f.file_id}`}>{FILE_KIND[f.kind]}: {f.file_name}</a>)}
    </div>
  );
}

export function ProjectCard({ p, score, snippet, showTeam = true }: {
  p: Project; score?: number | null; snippet?: string | null; showTeam?: boolean;
}) {
  return (
    <div className="card pad stack" style={{ gap: 8 }}>
      <div className="row-top" style={{ gap: 16 }}>
        <div className="grow">
          <div className="strong" style={{ fontSize: 14.5 }}>{p.title}</div>
          <div className="meta" style={{ marginTop: 2 }}>{p.academic_year} · {p.subject} · {p.faculty}</div>
        </div>
        {p.status !== "completed" && <StatusTag status={p.status} />}
        {score != null && <div style={{ width: 150, flex: "none" }}><Meter score={score} /></div>}
      </div>
      <div className="small soft pretty">{snippet ? <Highlighted text={snippet} /> : p.abstract}</div>
      <Tags tags={p.tags} type={p.project_type} />
      {showTeam && p.members && <div className="small muted">Team: <span className="soft">{p.members}</span></div>}
      <Resources links={p.links} files={p.files} />
      {p.review_note && <div className="small muted">Faculty note: <span className="soft">{p.review_note}</span></div>}
    </div>
  );
}

export function Notice({ tone, kind, children }: { tone: "down" | "warn" | "up" | "info"; kind?: string; children: ReactNode }) {
  return <div className={`notice ${tone}`}>{kind && <b className="kind">{kind}</b>}{children}</div>;
}

export function Loading() {
  return (
    <div className="stack">
      <div className="loading-bar"><div /></div>
      <div className="skeleton" />
      <div className="skeleton" />
    </div>
  );
}

export function Failed({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <Notice tone="down" kind="Error">
      {message} {retry && <button className="link" onClick={retry}>Try again</button>}
    </Notice>
  );
}

export function Segmented<T extends string>({ options, value, onChange, label }: {
  options: readonly T[]; value: T; onChange: (v: T) => void; label: string;
}) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={o} role="radio" aria-checked={o === value} className={o === value ? "on" : ""} onClick={() => onChange(o)}>
          {o}
        </button>
      ))}
    </div>
  );
}

export function Toggle({ on, onChange, children }: { on: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  return (
    <button className={`toggle${on ? " on" : ""}`} role="switch" aria-checked={on} onClick={() => onChange(!on)}>
      <span className="track"><span className="knob" /></span>
      {children}
    </button>
  );
}
