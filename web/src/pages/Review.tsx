import type { ReactNode } from "react";
import type { Band, Status } from "../api";
import { AppLink, Closeness, Failed, Loading, PageHead } from "../components/ui";
import { formatDay } from "../format";
import { useLoad } from "../hooks";

interface Waiting {
  project_id: number;
  title: string;
  subject: string;
  members: string | null;
  created_at: string;
  closest_title: string | null;
  similarity: number | null;
  band: Band | null;
}

interface Decided {
  project_id: number;
  title: string;
  subject: string;
  academic_year: string;
  members: string | null;
  status: Status;
  decided_at: string;
  marks: number | null;
  max_marks: number;
}

function Row({ to, title, meta, right }: { to: number; title: string; meta: string; right?: ReactNode }) {
  return (
    <AppLink to={`/projects/${to}`} className="row-link">
      <div className="row" style={{ padding: "12px 18px", gap: 12 }}>
        <div className="grow" style={{ minWidth: 0 }}>
          <div className="strong title">{title}</div>
          <div className="meta">{meta}</div>
        </div>
        {right}
      </div>
    </AppLink>
  );
}

export default function Review() {
  const { data, error, loading, reload } = useLoad<{ waiting: Waiting[]; decided: Decided[] }>("/review");
  const head = <PageHead title="Review and marks"
                         sub="Projects submitted to you. Open one to read the report, approve or reject it, and give marks." />;
  if (loading && !data) return <>{head}<Loading /></>;
  if (error || !data) return <>{head}<Failed message={error ?? ""} retry={reload} /></>;

  const approved = data.decided.filter((p) => p.status === "approved");
  const rejected = data.decided.filter((p) => p.status === "rejected");
  return (
    <>
      {head}
      <div className="stack" style={{ gap: 14 }}>
        <div className="label">Waiting for review ({data.waiting.length})</div>
        <div className="card divided" style={{ overflow: "hidden" }}>
          {data.waiting.map((p) => (
            <Row key={p.project_id} to={p.project_id} title={p.title}
                 meta={`${p.subject} · ${p.members ?? ""} · submitted ${formatDay(p.created_at)}`}
                 right={<Closeness band={p.band === "near duplicate" || p.band === "similar" ? p.band : null} score={p.similarity} />} />
          ))}
          {data.waiting.length === 0 && <div className="small muted" style={{ padding: "14px 18px" }}>Nothing waiting.</div>}
        </div>

        <div className="label section">Approved ({approved.length})</div>
        <div className="card divided" style={{ overflow: "hidden" }}>
          {approved.map((p) => (
            <Row key={p.project_id} to={p.project_id} title={p.title} meta={`${p.academic_year} · ${p.subject} · ${p.members ?? ""}`}
                 right={p.marks === null
                   ? <span className="small" style={{ color: "var(--warn)", whiteSpace: "nowrap" }}>Not graded</span>
                   : <span className="strong" style={{ whiteSpace: "nowrap" }}>{p.marks} / {p.max_marks}</span>} />
          ))}
          {approved.length === 0 && <div className="small muted" style={{ padding: "14px 18px" }}>None yet.</div>}
        </div>

        {rejected.length > 0 && (
          <>
            <div className="label section">Rejected ({rejected.length})</div>
            <div className="card divided" style={{ overflow: "hidden" }}>
              {rejected.map((p) => (
                <Row key={p.project_id} to={p.project_id} title={p.title}
                     meta={`${p.academic_year} · ${p.subject} · rejected ${formatDay(p.decided_at)}`} />
              ))}
            </div>
          </>
        )}
      </div>
    </>
  );
}
