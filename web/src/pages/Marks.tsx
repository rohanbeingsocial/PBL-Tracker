import { useState } from "react";
import { api, type Status } from "../api";
import { Failed, Loading, Metrics, PageHead, StatusTag } from "../components/ui";
import { eyebrow, useApp } from "../context";
import { useLoad } from "../hooks";

interface MarkProject {
  project_id: number;
  title: string;
  academic_year: string;
  subject: string;
  subject_name: string;
  status: Status;
  members: string | null;
  marks: number | null;
  max_marks: number;
}

function Sheet({ project, onSaved }: { project: MarkProject; onSaved: () => void }) {
  const { toast } = useApp();
  const [value, setValue] = useState(project.marks === null ? "" : String(project.marks));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save(marks: number | null) {
    if (marks !== null && (Number.isNaN(marks) || marks < 0 || marks > project.max_marks)) {
      return setError(`Enter a number from 0 to ${project.max_marks}.`);
    }
    setBusy(true);
    setError(null);
    try {
      await api(`/marks/${project.project_id}`, { method: "PUT", body: { marks } });
      toast(marks === null ? "Marks cleared." : `Saved ${marks} / ${project.max_marks}.`);
      onSaved();
    } catch (e) {
      // The database's own refusal, e.g. more than the subject's maximum.
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card pad-lg stack" style={{ gap: 14, maxWidth: 520 }}>
      <label className="field"><span>Marks for the project</span>
        <div className="row" style={{ gap: 10 }}>
          <input className="input mono" style={{ width: 140 }} type="number" min={0} max={project.max_marks} step={0.5}
                 placeholder="not marked" value={value} onChange={(e) => setValue(e.target.value)} aria-label="Marks" />
          <span className="mono muted">out of {project.max_marks}</span>
        </div>
        <small>{project.subject_name} is marked out of {project.max_marks}. Half marks are fine.</small>
      </label>
      <div className="row" style={{ gap: 8 }}>
        <button className="btn primary" disabled={busy || value.trim() === ""} onClick={() => save(Number(value))}>
          {busy ? "Saving…" : "Save marks"}
        </button>
        {project.marks !== null && <button className="btn" disabled={busy} onClick={() => save(null)}>Clear</button>}
        {error && <span className="error-text" role="alert">{error}</span>}
      </div>
    </div>
  );
}

export default function Marks() {
  const { me } = useApp();
  const { data, error, loading, reload } = useLoad<{ projects: MarkProject[] }>("/marks");
  const [picked, setPicked] = useState<number | null>(null);
  const head = <PageHead eyebrow={eyebrow(me)} title="Enter marks"
                         sub="One mark per project, out of its subject's total. The database refuses anything above that total." />;
  if (loading && !data) return <>{head}<Loading /></>;
  if (error || !data) return <>{head}<Failed message={error ?? ""} retry={reload} /></>;
  if (!data.projects.length) {
    return <>{head}<div className="empty">None of your projects are approved or completed yet, so there is nothing to mark.</div></>;
  }
  const project = data.projects.find((p) => p.project_id === picked) ?? data.projects.find((p) => p.marks === null) ?? data.projects[0];
  const unmarked = data.projects.filter((p) => p.marks === null).length;
  return (
    <>
      {head}
      <div className="split">
        <div className="narrow card" style={{ overflow: "hidden", flex: "1 1 280px" }}>
          <div className="label" style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)" }}>Your projects · {data.projects.length}</div>
          <div className="divided" style={{ maxHeight: 560, overflowY: "auto" }}>
            {data.projects.map((p) => {
              const on = p.project_id === project.project_id;
              return (
                <button key={p.project_id} onClick={() => setPicked(p.project_id)} aria-current={on || undefined}
                        style={{ display: "flex", flexDirection: "column", gap: 4, width: "100%", padding: "12px 16px", border: 0, textAlign: "left", cursor: "pointer", whiteSpace: "normal",
                                 borderLeft: `2px solid ${on ? "var(--accent)" : "transparent"}`, background: on ? "var(--surface-2)" : "transparent" }}>
                  <span className="strong" style={{ fontSize: 13.5 }}>{p.title}</span>
                  <span className="meta">{p.academic_year} · {p.subject} · {p.marks === null ? "–" : `${p.marks}/${p.max_marks}`}</span>
                  {p.marks === null && <span className="mono" style={{ fontSize: 11, color: "var(--warn)" }}>not marked yet</span>}
                </button>
              );
            })}
          </div>
        </div>
        <div className="wide" style={{ flex: "3 1 480px" }}>
          <div className="row-top" style={{ gap: 12 }}>
            <div className="grow">
              <div className="strong" style={{ fontSize: 18, letterSpacing: "-0.01em" }}>{project.title}</div>
              <div className="meta" style={{ margin: "4px 0 18px" }}>{project.academic_year} · {project.subject} · team {project.members}</div>
            </div>
            <StatusTag status={project.status} />
          </div>
          <Metrics items={[
            { label: "Marks", value: project.marks === null ? "–" : project.marks },
            { label: "Out of", value: project.max_marks },
            { label: "Your projects not marked", value: unmarked },
          ]} />
          <Sheet key={project.project_id} project={project} onSaved={reload} />
        </div>
      </div>
    </>
  );
}
