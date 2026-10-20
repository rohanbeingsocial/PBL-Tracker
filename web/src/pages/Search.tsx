import { useState } from "react";
import { query, type Project, type ProjectType, type Scored } from "../api";
import { Closeness, Failed, Loading, PageHead, ProjectCard, Segmented } from "../components/ui";
import { useApp } from "../context";
import { useDebounced, useLoad } from "../hooks";

const MODES = ["Both", "Meaning", "Keywords"] as const;
const PAGE = 20;
const TYPES: { value: ProjectType; label: string }[] = [
  { value: "software", label: "Software" }, { value: "hardware", label: "Hardware" }, { value: "both", label: "Both" },
];
type Row = Project & Scored & { snippet: string | null };

export default function Search() {
  const { ref } = useApp();
  const [q, setQ] = useState("");
  const [mode, setMode] = useState<(typeof MODES)[number]>("Both");
  const [subjects, setSubjects] = useState<string[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [kinds, setKinds] = useState<string[]>([]);
  const [from, setFrom] = useState(ref.years[0]);
  const [to, setTo] = useState(ref.years[ref.years.length - 1]);
  const [shown, setShown] = useState(PAGE);

  const settled = useDebounced(q.trim(), 350);
  const params = query({ q: settled, mode, subject: subjects, tag: tags, kind: kinds, year_from: from, year_to: to });
  const { data, error, loading, reload } = useLoad<{ rows: Row[]; ranked: boolean }>(`/search?${params}`);

  const toggle = (list: string[], set: (v: string[]) => void, value: string) => {
    set(list.includes(value) ? list.filter((x) => x !== value) : [...list, value]);
    setShown(PAGE);
  };
  const clear = () => {
    setSubjects([]);
    setTags([]);
    setKinds([]);
    setFrom(ref.years[0]);
    setTo(ref.years[ref.years.length - 1]);
  };

  const rows = data?.rows ?? [];
  const visible = data?.ranked ? rows : rows.slice(0, shown);
  return (
    <>
      <PageHead title="Search projects"
                sub="Every approved project, from every year. Search by name or by what the project does." />
      <div className="split">
        <div className="wide stack">
          <div className="row wrap" style={{ gap: 10 }}>
            <input className="input" style={{ flex: "1 1 300px", height: 42 }} value={q} maxLength={200} aria-label="Search"
                   onChange={(e) => { setQ(e.target.value); setShown(PAGE); }}
                   placeholder="Project name or idea, e.g. heart attack risk from patient data" />
            <Segmented options={MODES} value={mode} onChange={setMode} label="Match by"
                       names={{ Both: "Name and idea", Meaning: "Idea only", Keywords: "Exact words" }} />
          </div>
          {loading && (data ? <div className="loading-bar" style={{ margin: 0 }}><div /></div> : <Loading />)}
          {error && <Failed message={error} retry={reload} />}
          {data && (
            <>
              <div className="meta" style={{ padding: "4px 2px" }}>
                {data.ranked ? `${rows.length} best matches` : `${rows.length} projects, newest first`}
              </div>
              {visible.map((r) => <ProjectCard key={r.project_id} p={r} snippet={r.snippet} extra={<Closeness band={r.band} score={r.similarity} />} />)}
              {rows.length === 0 && (
                <div className="empty">No projects match. {mode === "Keywords" ? "Try searching by idea, or fewer filters." : "Try fewer filters."}</div>
              )}
              {!data.ranked && shown < rows.length && (
                <button className="btn" style={{ alignSelf: "flex-start" }} onClick={() => setShown(shown + PAGE)}>
                  Show {Math.min(PAGE, rows.length - shown)} more
                </button>
              )}
            </>
          )}
        </div>
        <div className="narrow card sticky" style={{ overflow: "hidden" }}>
          <div className="row strong" style={{ padding: "14px 16px", borderBottom: "1px solid var(--border)", justifyContent: "space-between" }}>
            Filters<button className="link" style={{ fontSize: 12, padding: 0 }} onClick={clear}>Clear</button>
          </div>
          <div className="stack-sm" style={{ padding: "14px 16px", borderBottom: "1px solid var(--border)", gap: 8 }}>
            <div className="label-sm">Subject</div>
            <div className="chips">
              {ref.subjects.map((s) => (
                <button key={s.subject_id} className={`chip square${subjects.includes(s.code) ? " on" : ""}`} aria-pressed={subjects.includes(s.code)}
                        title={s.name} onClick={() => toggle(subjects, setSubjects, s.code)}>{s.code}</button>
              ))}
            </div>
          </div>
          <div className="stack-sm" style={{ padding: "14px 16px", borderBottom: "1px solid var(--border)", gap: 8 }}>
            <div className="label-sm">Type</div>
            <div className="chips">
              {TYPES.map((k) => (
                <button key={k.value} className={`chip${kinds.includes(k.value) ? " on" : ""}`} aria-pressed={kinds.includes(k.value)}
                        onClick={() => toggle(kinds, setKinds, k.value)}>{k.label}</button>
              ))}
            </div>
          </div>
          <div className="stack-sm" style={{ padding: "14px 16px", borderBottom: "1px solid var(--border)", gap: 8 }}>
            <div className="label-sm">Technologies</div>
            <div className="chips">
              {ref.tags.map((tg) => (
                <button key={tg.tag_id} className={`chip square${tags.includes(tg.name) ? " on" : ""}`} aria-pressed={tags.includes(tg.name)}
                        onClick={() => toggle(tags, setTags, tg.name)}>{tg.name}</button>
              ))}
            </div>
          </div>
          <div className="stack-sm" style={{ padding: "14px 16px", gap: 8 }}>
            <div className="label-sm">Academic year</div>
            <div className="row" style={{ gap: 8 }}>
              <select className="select grow" style={{ height: 32, fontSize: 13 }} aria-label="From year" value={from}
                      onChange={(e) => { setFrom(e.target.value); if (e.target.value > to) setTo(e.target.value); }}>
                {ref.years.map((y) => <option key={y}>{y}</option>)}
              </select>
              <span className="muted small">to</span>
              <select className="select grow" style={{ height: 32, fontSize: 13 }} aria-label="To year" value={to}
                      onChange={(e) => { setTo(e.target.value); if (e.target.value < from) setFrom(e.target.value); }}>
                {ref.years.map((y) => <option key={y}>{y}</option>)}
              </select>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
