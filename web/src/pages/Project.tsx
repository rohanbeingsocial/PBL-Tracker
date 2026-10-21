import { useState } from "react";
import { api, type ProjectDetail } from "../api";
import { Attachments } from "../components/Attachments";
import { ReportViewer } from "../components/ReportViewer";
import { AppLink, Closeness, Failed, FILE_KIND, Loading, PageHead, StatusTag, TYPE_LABEL, Toggle } from "../components/ui";
import { useApp } from "../context";
import { formatDay } from "../format";
import { useLoad } from "../hooks";

// The faculty member's part: approve or reject a submission (marks can go in at the
// same time), or change the marks of an approved one.
function FacultyPanel({ p, onDone }: { p: ProjectDetail; onDone: (message: string) => void }) {
  const [note, setNote] = useState(p.review_note ?? "");
  const [marks, setMarks] = useState(p.marks === null ? "" : String(p.marks));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onDone(message);
    } catch (e) {
      setError((e as Error).message);    // the database's own refusal, e.g. marks above the maximum
    } finally {
      setBusy(false);
    }
  }
  const value = marks.trim() === "" ? null : Number(marks);
  const marksField = (
    <label className="field"><span>Marks (out of {p.max_marks})</span>
      <input className="input" type="number" min={0} max={p.max_marks} step={0.5} value={marks} style={{ maxWidth: 140 }}
             onChange={(e) => { setMarks(e.target.value); setError(null); }} />
    </label>
  );

  if (p.status === "submitted") {
    return (
      <div className="card pad stack">
        <div className="strong">Your review</div>
        {p.closest?.closest_title && (p.closest.band === "near duplicate" || p.closest.band === "similar") && (
          <div className="small">
            Closest earlier project: {p.closest.closest_id
              ? <AppLink to={`/projects/${p.closest.closest_id}`}>{p.closest.closest_title}</AppLink>
              : p.closest.closest_title} ({p.closest.closest_year}){" "}
            <Closeness band={p.closest.band} score={p.closest.similarity} />
          </div>
        )}
        <label className="field"><span>Note to the team</span>
          <textarea className="textarea" rows={3} value={note} maxLength={1000} onChange={(e) => { setNote(e.target.value); setError(null); }}
                    placeholder="Needed when it is very close to an earlier project: what is different about this one?" />
        </label>
        {marksField}
        <div className="row" style={{ gap: 8 }}>
          <button className="btn primary" disabled={busy}
                  onClick={() => run(() => api(`/projects/${p.project_id}/decision`, { body: { status: "approved", note, marks: value } }), "Approved.")}>
            Approve
          </button>
          <button className="btn danger" disabled={busy}
                  onClick={() => run(() => api(`/projects/${p.project_id}/decision`, { body: { status: "rejected", note } }), "Rejected.")}>
            Reject
          </button>
        </div>
        {error && <div className="error-text" role="alert">{error}</div>}
      </div>
    );
  }
  if (p.status !== "approved") return null;
  return (
    <div className="card pad stack">
      <div className="strong">Marks</div>
      {marksField}
      <div className="row" style={{ gap: 8 }}>
        <button className="btn primary" disabled={busy}
                onClick={() => run(() => api(`/marks/${p.project_id}`, { method: "PUT", body: { marks: value } }), "Marks saved.")}>
          Save marks
        </button>
      </div>
      {error && <div className="error-text" role="alert">{error}</div>}
    </div>
  );
}

function MarksBox({ p, onChanged }: { p: ProjectDetail; onChanged: () => void }) {
  const { toast } = useApp();
  const [busy, setBusy] = useState(false);
  if (p.status !== "approved") return null;

  async function share(on: boolean) {
    setBusy(true);
    try {
      await api(`/projects/${p.project_id}/marks-public`, { method: "PUT", body: { public: on } });
      toast(on ? "Marks are now shown to everyone." : "Marks are now shown only to the team and faculty.");
      onChanged();
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="card pad stack-sm">
      <div className="label-sm">Marks</div>
      {p.marks !== null
        ? <div className="marks-big">{p.marks} <span className="muted" style={{ fontSize: 16, fontWeight: 400 }}>/ {p.max_marks}</span></div>
        : <div className="small muted">{p.marks_hidden ? "Only the team and their faculty member can see the marks." : "Not graded yet."}</div>}
      {p.is_member && (
        <Toggle on={p.marks_public} onChange={share} disabled={busy}>Show our marks to everyone</Toggle>
      )}
    </div>
  );
}

export default function ProjectPage({ id }: { id: number }) {
  const { me, toast, refreshCounts } = useApp();
  const { data: p, error, loading, reload } = useLoad<ProjectDetail>(`/projects/${id}`);
  const [managing, setManaging] = useState(false);
  if (loading && !p) return <Loading />;
  if (error || !p) return <Failed message={error ?? ""} retry={reload} />;

  const report = p.files.find((f) => f.kind === "report");
  const ppt = p.files.find((f) => f.kind === "ppt");
  const decidedLabel = p.status === "approved" ? "Approved" : "Rejected";
  return (
    <>
      <PageHead title={p.title} back={me.role === "student" && p.is_member ? { to: "/", label: "Dashboard" } : { to: "/search", label: "Search" }} />
      <div className="project">
        <div>
          {report
            ? <ReportViewer fileId={report.file_id} fileName={report.file_name} />
            : <div className="card report-missing muted">No report on file for this project.</div>}
        </div>
        <div className="details">
          <div className="card pad stack">
            <div className="row"><StatusTag status={p.status} /></div>
            <dl className="facts">
              <dt>Subject</dt><dd>{p.subject} - {p.subject_name}</dd>
              <dt>Year</dt><dd>{p.academic_year}</dd>
              <dt>Team</dt><dd>{p.members ?? "Not recorded"}</dd>
              <dt>{p.status === "approved" ? "Approved by" : "Faculty"}</dt><dd>{p.faculty}</dd>
              <dt>Submitted</dt><dd>{formatDay(p.created_at)}</dd>
              {p.decided_at && <><dt>{decidedLabel}</dt><dd>{formatDay(p.decided_at)}</dd></>}
              <dt>Type</dt><dd>{TYPE_LABEL[p.project_type]}</dd>
              {p.tags.length > 0 && <><dt>Technologies</dt><dd>{p.tags.join(", ")}</dd></>}
            </dl>
          </div>
          <MarksBox p={p} onChanged={reload} />
          {p.is_faculty && <FacultyPanel p={p} onDone={(m) => { toast(m); reload(); refreshCounts(); }} />}
          <div className="card pad stack-sm">
            <div className="label-sm">Links and files</div>
            {p.links.map((l) => <a key={l.link_id} href={l.url} target="_blank" rel="noopener noreferrer">{l.label}</a>)}
            {report && <a href={`/api/files/${report.file_id}`}>Download the report</a>}
            {ppt && <a href={`/api/files/${ppt.file_id}`}>{FILE_KIND.ppt}: {ppt.file_name}</a>}
            {!p.links.length && !ppt && !report && <div className="small muted">None yet.</div>}
            {p.can_change && (managing
              ? <div style={{ marginTop: 8 }}><Attachments p={p} onChanged={reload} /><button className="link" onClick={() => setManaging(false)}>Done</button></div>
              : <button className="link" onClick={() => setManaging(true)}>Add or change links and files</button>)}
          </div>
          {p.review_note && (
            <div className="card pad stack-sm">
              <div className="label-sm">Note from {p.faculty}</div>
              <div className="small soft pretty">{p.review_note}</div>
            </div>
          )}
          <div className="card pad stack-sm">
            <div className="label-sm">Abstract</div>
            <div className="small soft pretty">{p.abstract}</div>
          </div>
        </div>
      </div>
    </>
  );
}
