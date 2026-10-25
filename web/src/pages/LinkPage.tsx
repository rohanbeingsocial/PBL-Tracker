import { useState } from "react";
import { api, linkUrl, type Band, type Status, type SubmissionLink } from "../api";
import { Icon } from "../components/charts";
import { AppLink, Closeness, Failed, Loading, Metrics, PageHead, StatusTag } from "../components/ui";
import { useApp } from "../context";
import { formatDay } from "../format";
import { useLoad } from "../hooks";
import { CopyLink, OpenTag } from "./Links";

interface LinkStudent {
  user_id: number;
  prn: string;
  name: string;
  is_leader: boolean;
  marks: number | null;
}

interface LinkProject {
  project_id: number;
  title: string;
  status: Status;
  created_at: string;
  team_score: number | null;
  closest: { closest_title: string | null; similarity: number | null; band: Band | null } | null;
  students: LinkStudent[];
}

type LinkData = SubmissionLink & { projects: LinkProject[] };

function EditLink({ link, onSaved, onCancel }: { link: LinkData; onSaved: () => void; onCancel: () => void }) {
  const [className, setClassName] = useState(link.class_name);
  const [purpose, setPurpose] = useState(link.purpose);
  const [max, setMax] = useState(String(link.max_marks));
  const [error, setError] = useState<string | null>(null);

  async function save() {
    if (!(Number(max) > 0)) return setError("Marks out of has to be more than 0.");
    try {
      await api(`/links/${link.submission_link_id}`, {
        method: "PUT",
        body: { class_name: className.trim(), purpose: purpose.trim(), max_marks: Number(max), is_open: link.is_open },
      });
      onSaved();
    } catch (e) {
      setError((e as Error).message);    // e.g. a student already has more marks than the new maximum
    }
  }
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="row wrap" style={{ gap: 8 }}>
        <input className="input grow" style={{ minWidth: 160 }} value={className} maxLength={80} aria-label="Class"
               onChange={(e) => setClassName(e.target.value)} />
        <input className="input grow" style={{ minWidth: 160 }} value={purpose} maxLength={100} aria-label="What it is for"
               onChange={(e) => setPurpose(e.target.value)} />
        <input className="input mono" style={{ width: 100 }} type="number" min={0.5} step={0.5} value={max}
               aria-label="Each student out of" onChange={(e) => setMax(e.target.value)} />
        <button className="btn primary" disabled={className.trim().length < 2 || purpose.trim().length < 2} onClick={save}>Save</button>
        <button className="btn" onClick={onCancel}>Cancel</button>
      </div>
      {error && <div className="error-text" role="alert">{error}</div>}
    </div>
  );
}

function ProjectRow({ p, max }: { p: LinkProject; max: number }) {
  const graded = p.students.filter((s) => s.marks !== null).length;
  return (
    <div className="row-top" style={{ padding: "14px 18px", gap: 16 }}>
      <div className="grow stack-sm" style={{ minWidth: 0, gap: 6 }}>
        <div className="row wrap" style={{ gap: 10 }}>
          <AppLink to={`/projects/${p.project_id}`} className="strong title">{p.title}</AppLink>
          <StatusTag status={p.status} />
          {p.status === "submitted" && p.closest && (p.closest.band === "near duplicate" || p.closest.band === "similar") && (
            <Closeness band={p.closest.band} score={p.closest.similarity} />
          )}
        </div>
        <div className="row wrap small" style={{ gap: "4px 14px" }}>
          {p.students.map((s) => (
            <span key={s.user_id}>
              {s.name}{s.is_leader ? " (lead)" : ""} <span className="muted mono">{s.prn}</span>
              {p.status === "approved" && <b style={{ marginLeft: 6 }}>{s.marks ?? "–"}</b>}
            </span>
          ))}
        </div>
        <div className="meta">Submitted {formatDay(p.created_at)}</div>
      </div>
      {p.status === "approved" && (
        <div style={{ textAlign: "right", whiteSpace: "nowrap" }}>
          {p.team_score !== null
            ? <><div className="strong">{p.team_score} / {max}</div><div className="meta">team score</div></>
            : <><div className="small" style={{ color: "var(--warn)" }}>{graded} of {p.students.length} graded</div>
                <AppLink to={`/projects/${p.project_id}`} className="small">Grade</AppLink></>}
        </div>
      )}
    </div>
  );
}

export default function LinkPage({ id }: { id: number }) {
  const { toast } = useApp();
  const { data: link, error, loading, reload } = useLoad<LinkData>(`/links/${id}`);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const back = { to: "/links" as const, label: "Submission links" };
  if (loading && !link) return <><PageHead title="Submission link" back={back} /><Loading /></>;
  if (error || !link) return <><PageHead title="Submission link" back={back} /><Failed message={error ?? ""} retry={reload} /></>;

  async function setOpen(open: boolean) {
    setBusy(true);
    try {
      await api(`/links/${id}`, {
        method: "PUT",
        body: { class_name: link!.class_name, purpose: link!.purpose, max_marks: link!.max_marks, is_open: open },
      });
      toast(open ? "The link takes projects again." : "Link closed. It takes no new projects.");
      reload();
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const waiting = link.projects.filter((p) => p.status === "submitted");
  const approved = link.projects.filter((p) => p.status === "approved");
  const rejected = link.projects.filter((p) => p.status === "rejected");
  const groups = [
    { name: "Waiting for review", rows: waiting },
    { name: "Approved", rows: approved },
    { name: "Rejected", rows: rejected },
  ].filter((g) => g.rows.length);
  return (
    <>
      <PageHead title={`${link.subject} · ${link.class_name}`} back={back}
                sub={`${link.purpose} · ${link.academic_year} · each student out of ${link.max_marks}`} />
      <div className="stack" style={{ gap: 16 }}>
        <div className="card pad stack" style={{ gap: 12 }}>
          <div className="row wrap" style={{ gap: 10 }}>
            <OpenTag open={link.is_open} />
            <span className="mono small grow" style={{ userSelect: "all", wordBreak: "break-all" }}>{linkUrl(link.code)}</span>
            <CopyLink code={link.code} />
            <a className="btn" href={`/api/links/${id}/marks.csv`}><Icon name="download" size={15} />Download marks</a>
          </div>
          {editing
            ? <EditLink link={link} onCancel={() => setEditing(false)}
                        onSaved={() => { toast("Saved."); setEditing(false); reload(); }} />
            : <div className="row wrap" style={{ gap: 14 }}>
                <button className="link" onClick={() => setEditing(true)}>Change class, purpose or marks</button>
                <button className="link" disabled={busy} onClick={() => setOpen(!link.is_open)}>
                  {link.is_open ? "Close the link" : "Open it again"}
                </button>
              </div>}
        </div>

        <Metrics items={[
          { label: "Waiting for review", value: link.waiting },
          { label: "Approved", value: link.approved },
          { label: "Graded", value: `${link.graded} of ${link.approved}` },
          { label: "Students", value: link.students, tone: "accent" },
        ]} />

        {groups.map((g) => (
          <div key={g.name} className="stack" style={{ gap: 10 }}>
            <div className="label section">{g.name} ({g.rows.length})</div>
            <div className="card divided" style={{ overflow: "hidden" }}>
              {g.rows.map((p) => <ProjectRow key={p.project_id} p={p} max={link.max_marks} />)}
            </div>
          </div>
        ))}
        {link.projects.length === 0 && (
          <div className="empty">Nothing submitted yet. Copy the link and send it to {link.class_name}.</div>
        )}
      </div>
    </>
  );
}
