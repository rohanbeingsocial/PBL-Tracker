import { useState } from "react";
import { api } from "../api";
import { Failed, Loading, PageHead } from "../components/ui";
import { eyebrow, useApp } from "../context";
import { useLoad } from "../hooks";

interface SubjectRow {
  subject_id: number;
  code: string;
  name: string;
  max_marks: number;
  projects: number;
  marked: number;
}

function SubjectForm({ start, onSaved, onCancel }: {
  start: SubjectRow | null; onSaved: (message: string) => void; onCancel?: () => void;
}) {
  const [code, setCode] = useState(start?.code ?? "");
  const [name, setName] = useState(start?.name ?? "");
  const [max, setMax] = useState(start ? String(start.max_marks) : "");
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const body = { code: code.trim(), name: name.trim(), max_marks: Number(max) };
    if (!(body.max_marks > 0)) return setError("The maximum marks have to be more than 0.");
    setError(null);
    try {
      if (start) await api(`/subjects/${start.subject_id}`, { method: "PUT", body });
      else await api("/subjects", { body });
      onSaved(start ? `Saved ${body.code}.` : `Added ${body.code}.`);
      if (!start) {
        setCode("");
        setName("");
        setMax("");
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="row wrap" style={{ gap: 8 }}>
        <input className="input mono" style={{ width: 130 }} value={code} maxLength={20} placeholder="DBMS-PBL" aria-label="Code"
               onChange={(e) => setCode(e.target.value.toUpperCase())} />
        <input className="input grow" style={{ minWidth: 200 }} value={name} maxLength={100} placeholder="Subject name" aria-label="Name"
               onChange={(e) => setName(e.target.value)} />
        <input className="input mono" style={{ width: 110 }} type="number" min={0.5} step={0.5} value={max} placeholder="out of"
               aria-label="Maximum marks" onChange={(e) => setMax(e.target.value)} />
        <button className="btn primary" disabled={!code.trim() || !name.trim() || !max} onClick={save}>{start ? "Save" : "Add subject"}</button>
        {onCancel && <button className="btn" onClick={onCancel}>Cancel</button>}
      </div>
      {error && <div className="error-text" role="alert">{error}</div>}
    </div>
  );
}

export default function Subjects() {
  const { me, toast } = useApp();
  const { data, error, loading, reload } = useLoad<{ subjects: SubjectRow[] }>("/subjects");
  const [editing, setEditing] = useState<number | null>(null);
  const head = <PageHead eyebrow={eyebrow(me)} title="Subjects"
                         sub="Each subject marks its projects out of its own total, for example 33 for a lab or 5 for a theory subject." />;
  if (loading && !data) return <>{head}<Loading /></>;
  if (error || !data) return <>{head}<Failed message={error ?? ""} retry={reload} /></>;

  const saved = (message: string) => {
    toast(message);
    setEditing(null);
    reload();
  };
  return (
    <>
      {head}
      <div className="stack" style={{ gap: 20, maxWidth: 920 }}>
        <div className="card" style={{ overflow: "hidden" }}>
          <table className="table">
            <thead><tr><th>Code</th><th>Name</th><th className="num">Out of</th><th className="num">Projects</th><th className="num">Marked</th><th /></tr></thead>
            <tbody>
              {data.subjects.map((s) => editing === s.subject_id ? (
                <tr key={s.subject_id}><td colSpan={6}><SubjectForm start={s} onSaved={saved} onCancel={() => setEditing(null)} /></td></tr>
              ) : (
                <tr key={s.subject_id}>
                  <td className="mono strong">{s.code}</td>
                  <td>{s.name}</td>
                  <td className="num">{s.max_marks}</td>
                  <td className="num">{s.projects}</td>
                  <td className="num">{s.marked}</td>
                  <td className="num"><button className="link" onClick={() => setEditing(s.subject_id)}>Edit</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card pad stack" style={{ gap: 10 }}>
          <div className="strong">Add a subject</div>
          <SubjectForm start={null} onSaved={saved} />
        </div>
      </div>
    </>
  );
}
