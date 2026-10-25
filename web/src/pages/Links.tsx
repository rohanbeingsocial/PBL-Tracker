import { useState, type FormEvent } from "react";
import { api, linkUrl, type SubmissionLink } from "../api";
import { Icon } from "../components/charts";
import { Failed, Loading, PageHead } from "../components/ui";
import { useApp } from "../context";
import { useLoad } from "../hooks";

export function CopyLink({ code }: { code: string }) {
  const { toast } = useApp();
  async function copy() {
    try {
      await navigator.clipboard.writeText(linkUrl(code));
      toast("Link copied. Send it to the class.");
    } catch {
      toast(linkUrl(code));    // the browser refused the clipboard: show it so it can be copied by hand
    }
  }
  return <button className="btn" onClick={copy}><Icon name="link" size={15} />Copy link</button>;
}

export function OpenTag({ open }: { open: boolean }) {
  return <span className={`status ${open ? "approved" : "rejected"}`}>{open ? "Open" : "Closed"}</span>;
}

function NewLink({ onMade }: { onMade: (id: number) => void }) {
  const { ref } = useApp();
  const [subject, setSubject] = useState(0);
  const [className, setClassName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [max, setMax] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const chosen = ref.subjects.find((s) => s.subject_id === subject);

  async function make(e: FormEvent) {
    e.preventDefault();
    const maxMarks = max.trim() === "" ? null : Number(max);
    if (!subject) return setError("Choose the subject.");
    if (className.trim().length < 2) return setError("Write which class it is for, for example TY ECE Div A.");
    if (purpose.trim().length < 2) return setError("Write what the submission is for, for example Semester PBL.");
    if (maxMarks !== null && !(maxMarks > 0)) return setError("Marks out of has to be more than 0.");
    setBusy(true);
    setError(null);
    try {
      const made = await api<{ submission_link_id: number }>("/links", {
        body: { subject_id: subject, class_name: className.trim(), purpose: purpose.trim(), max_marks: maxMarks },
      });
      onMade(made.submission_link_id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const req = <span className="required"> *</span>;
  return (
    <form className="stack" style={{ gap: 14 }} onSubmit={make}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 14 }}>
        <label className="field"><span>Subject{req}</span>
          <select className="select" value={subject} onChange={(e) => setSubject(Number(e.target.value))}>
            <option value={0} disabled>Choose a subject</option>
            {ref.subjects.map((s) => <option key={s.subject_id} value={s.subject_id}>{s.code} - {s.name}</option>)}
          </select>
        </label>
        <label className="field"><span>Class{req}</span>
          <input className="input" value={className} maxLength={80} placeholder="TY ECE Div A"
                 onChange={(e) => setClassName(e.target.value)} />
        </label>
        <label className="field"><span>What it is for{req}</span>
          <input className="input" value={purpose} maxLength={100} placeholder="Semester PBL, LCA 1, Mini project"
                 onChange={(e) => setPurpose(e.target.value)} />
        </label>
        <label className="field"><span>Each student out of</span>
          <input className="input" type="number" min={0.5} step={0.5} value={max} placeholder={chosen ? String(chosen.max_marks) : ""}
                 onChange={(e) => setMax(e.target.value)} />
          <small>{chosen ? `Leave it empty for the subject's usual ${chosen.max_marks}.` : "Leave it empty for the subject's usual total."}</small>
        </label>
      </div>
      <div className="row" style={{ gap: 12 }}>
        <button className="btn primary" disabled={busy}>{busy ? "Making…" : "Make the link"}</button>
        {error && <span className="error-text" role="alert">{error}</span>}
      </div>
    </form>
  );
}

function LinkTable({ links, years }: { links: SubmissionLink[]; years?: boolean }) {
  const { go } = useApp();
  return (
    <div className="card" style={{ overflow: "hidden" }}>
      <table className="table">
        <thead>
          <tr><th>Subject</th><th>Class</th><th>For</th><th className="num">Out of</th><th className="num">Waiting</th>
            <th className="num">Approved</th><th className="num">Graded</th><th className="num">Students</th><th /></tr>
        </thead>
        <tbody>
          {links.map((l) => (
            <tr key={l.submission_link_id} className="click" onClick={() => go(`/links/${l.submission_link_id}`)}>
              <td className="mono strong">{l.subject}</td>
              <td>{l.class_name}</td>
              <td>{l.purpose}{years && <span className="muted"> · {l.academic_year}</span>}</td>
              <td className="num">{l.max_marks}</td>
              <td className="num" style={l.waiting ? { color: "var(--warn)", fontWeight: 600 } : undefined}>{l.waiting}</td>
              <td className="num">{l.approved}</td>
              <td className="num">{l.graded}</td>
              <td className="num">{l.students}</td>
              <td className="num"><OpenTag open={l.is_open} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Links() {
  const { ref, go, toast } = useApp();
  const { data, error, loading, reload } = useLoad<{ links: SubmissionLink[] }>("/links");
  const head = <PageHead title="Submission links"
                         sub="One link for each class and submission. Send it to the class: every project submitted through it lands here, ready to review and grade." />;
  if (loading && !data) return <>{head}<Loading /></>;
  if (error || !data) return <>{head}<Failed message={error ?? ""} retry={reload} /></>;

  const now = data.links.filter((l) => l.academic_year === ref.current_year);
  const earlier = data.links.filter((l) => l.academic_year !== ref.current_year);
  return (
    <>
      {head}
      <div className="stack" style={{ gap: 14 }}>
        <div className="label">This year · {ref.current_year}</div>
        {now.length ? <LinkTable links={now} /> : <div className="empty">No links for {ref.current_year} yet. Make one below.</div>}

        <div className="card pad stack section" style={{ gap: 12 }}>
          <div className="strong">Make a new link</div>
          <NewLink onMade={(id) => { toast("Link made. Copy it and send it to the class."); go(`/links/${id}`); }} />
        </div>

        {earlier.length > 0 && (
          <>
            <div className="label section">Earlier years</div>
            <LinkTable links={earlier} years />
          </>
        )}
      </div>
    </>
  );
}
