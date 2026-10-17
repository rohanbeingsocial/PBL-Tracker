import { useState } from "react";
import { api, type Closest, type Project } from "../api";
import { BigScore, Failed, Loading, Meter, PageHead, Resources, Tags } from "../components/ui";
import { eyebrow, useApp } from "../context";
import { formatDay } from "../format";
import { useLoad } from "../hooks";

type Waiting = Project & Closest & { sent_at: string };

function Proposal({ p, onDecided }: { p: Waiting; onDecided: (status: string) => void }) {
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function decide(status: "approved" | "rejected") {
    setBusy(true);
    setError(null);
    try {
      await api(`/projects/${p.project_id}/decision`, { body: { status, note } });
      onDecided(status);
    } catch (e) {
      // The database's own refusal, e.g. a near duplicate approved without a note.
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ borderRadius: 12, overflow: "hidden" }}>
      <div style={{ padding: "18px 20px 14px" }}>
        <div className="strong" style={{ fontSize: 16, letterSpacing: "-0.01em" }}>{p.title}</div>
        <div className="meta" style={{ marginTop: 3 }}>{p.subject} · sent {formatDay(p.sent_at)} · team {p.members}</div>
        <div className="stack-sm" style={{ marginTop: 10, gap: 6 }}><Tags tags={p.tags} type={p.project_type} /><Resources links={p.links} files={p.files} /></div>
      </div>
      <div className="compare" style={{ borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)" }}>
        <div style={{ padding: "14px 20px" }}>
          <div className="label-sm" style={{ marginBottom: 6 }}>This proposal</div>
          <div className="small soft pretty">{p.abstract}</div>
        </div>
        {p.closest_title && p.similarity !== null ? (
          <>
            <div className="mid" style={{ padding: "14px 18px" }}>
              <BigScore score={p.similarity} size={30} />
              <Meter score={p.similarity} large />
            </div>
            <div style={{ padding: "14px 20px" }}>
              <div className="label-sm" style={{ marginBottom: 6 }}>Closest existing · {p.closest_year}</div>
              <div className="strong" style={{ fontSize: 13.5, marginBottom: 4 }}>{p.closest_title}</div>
              <div className="small soft pretty">{p.closest_abstract}</div>
            </div>
          </>
        ) : (
          <div className="mid small muted" style={{ padding: "14px 18px" }}>No embedding yet, so it hasn't been compared with past projects.</div>
        )}
      </div>
      <div className="stack" style={{ padding: "14px 20px", gap: 10 }}>
        <textarea className={`textarea${error ? " bad" : ""}`} rows={2} value={note} maxLength={1000} aria-label="Review note"
                  onChange={(e) => { setNote(e.target.value); setError(null); }}
                  placeholder="Needed when approving a near duplicate: what is different about this one?" />
        <div className="row" style={{ gap: 8 }}>
          <button className="btn primary" disabled={busy} onClick={() => decide("approved")}>✓ Approve</button>
          <button className="btn danger" disabled={busy} onClick={() => decide("rejected")}>Reject</button>
          {error && <span className="error-text" role="alert">{error}</span>}
        </div>
      </div>
    </div>
  );
}

export default function Review() {
  const { me, toast, refreshCounts } = useApp();
  const { data, error, loading, reload } = useLoad<{ waiting: Waiting[]; running: Project[] }>("/review");

  const decided = (status: string) => {
    toast(`Marked as ${status}.`);
    reload();
    refreshCounts();
  };
  async function complete(p: Project) {
    try {
      await api(`/projects/${p.project_id}/decision`, { body: { status: "completed", note: p.review_note ?? "" } });
      decided("completed");
    } catch (e) {
      toast((e as Error).message);
    }
  }

  const head = <PageHead eyebrow={eyebrow(me)} title="Review proposals"
                         sub="Proposals sent to you. You can only decide on projects assigned to you, and the database asks for a note before a near duplicate is approved." />;
  if (loading && !data) return <>{head}<Loading /></>;
  if (error || !data) return <>{head}<Failed message={error ?? ""} retry={reload} /></>;
  return (
    <>
      {head}
      <div className="stack" style={{ gap: 14 }}>
        <div className="label">Waiting for your decision · {data.waiting.length}</div>
        {data.waiting.map((p) => <Proposal key={p.project_id} p={p} onDecided={decided} />)}
        {data.waiting.length === 0 && <div className="empty" style={{ borderRadius: 12, padding: 28 }}>Nothing waiting. New proposals from your students will show up here.</div>}
        <div className="label" style={{ marginTop: 16 }}>Running projects · {data.running.length}</div>
        <div className="card divided" style={{ overflow: "hidden" }}>
          {data.running.map((p) => (
            <div key={p.project_id} className="row" style={{ gap: 16, padding: "12px 18px" }}>
              <div className="grow">
                <div className="strong" style={{ fontSize: 13.5 }}>{p.title}</div>
                <div className="meta">{p.academic_year} · {p.subject} · {p.members}</div>
              </div>
              <button className="btn good" style={{ height: 30, fontSize: 12.5 }} onClick={() => complete(p)}>Mark completed</button>
            </div>
          ))}
          {data.running.length === 0 && <div className="small muted" style={{ padding: "16px 18px" }}>No approved projects are running right now.</div>}
        </div>
      </div>
    </>
  );
}
