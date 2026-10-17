import { useState } from "react";
import { query, type Project, type ProjectType, type Scored } from "../api";
import { Failed, Loading, PageHead, ProjectCard, Segmented, Toggle } from "../components/ui";
import { eyebrow, useApp } from "../context";
import { useDebounced, useLoad } from "../hooks";

const MODES = ["Both", "Meaning", "Keywords"] as const;
const PAGE = 20;
const TYPES: { value: ProjectType; label: string }[] = [
  { value: "software", label: "Software" }, { value: "hardware", label: "Hardware" }, { value: "both", label: "Both" },
];
type Row = Project & Scored & { snippet: string | null };

export default function Search() {
  const { me, ref } = useApp();
  const [q, setQ] = useState("");
  const [mode, setMode] = useState<(typeof MODES)[number]>("Both");
  const [subjects, setSubjects] = useState<string[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [kinds, setKinds] = useState<string[]>([]);
  const [from, setFrom] = useState(ref.years[0]);
  const [to, setTo] = useState(ref.years[ref.years.length - 1]);
  const [includeAll, setIncludeAll] = useState(false);
  const [shown, setShown] = useState(PAGE);

  const settled = useDebounced(q.trim(), 350);
  const params = query({ q: settled, mode, subject: subjects, tag: tags, kind: kinds, year_from: from, year_to: to, include_all: includeAll });
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
    setIncludeAll(false);
  };

  const rows = data?.rows ?? [];
  const visible = data?.ranked ? rows : rows.slice(0, shown);
  return (
    <>
      <PageHead eyebrow={eyebrow(me)} title="Search projects"
                sub="Keyword search matches words. Meaning search matches ideas, so it also finds projects that describe the same thing in other words." />
      <div className="split">
        <div className="wide stack">
          <div className="row wrap" style={{ gap: 10 }}>
            <label className="row" style={{ flex: "1 1 300px", height: 42, padding: "0 14px", border: "1px solid var(--border-2)", borderRadius: 8, background: "var(--surface)", gap: 10 }}>
              <span className="mono" style={{ color: "var(--faint)" }} aria-hidden="true">⌕</span>
              <input value={q} onChange={(e) => { setQ(e.target.value); setShown(PAGE); }} maxLength={200} aria-label="Search"
                     placeholder="Describe the idea, e.g. predict heart attack risk from patient data"
                     style={{ flex: 1, border: 0, background: "transparent", fontSize: 14, outline: "none" }} />
            </label>
            <Segmented options={MODES} value={mode} onChange={setMode} label="Match by" />
          </div>
          {loading && (data ? <div className="loading-bar" style={{ margin: 0 }}><div /></div> : <Loading />)}
          {error && <Failed message={error} retry={reload} />}
          {data && (
            <>
              <div className="meta" style={{ padding: "4px 2px" }}>
                {data.ranked ? `${rows.length} best matches` : `${rows.length} projects, newest first`}
              </div>
              {visible.map((r) => <ProjectCard key={r.project_id} p={r} score={r.similarity} snippet={r.snippet} />)}
              {rows.length === 0 && (
                <div className="empty">No projects match. {mode === "Keywords" ? "Try Meaning search, or fewer filters." : "Try fewer filters."}</div>
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
            <div className="label-sm">Stack</div>
            <div className="chips">
              {ref.tags.map((tg) => (
                <button key={tg.tag_id} className={`chip square${tags.includes(tg.name) ? " on" : ""}`} aria-pressed={tags.includes(tg.name)}
                        onClick={() => toggle(tags, setTags, tg.name)}>{tg.name}</button>
              ))}
            </div>
          </div>
          <div className="stack-sm" style={{ padding: "14px 16px", borderBottom: "1px solid var(--border)", gap: 8 }}>
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
          <div style={{ padding: "14px 16px" }}>
            <Toggle on={includeAll} onChange={setIncludeAll}>Include proposals and rejected ideas</Toggle>
          </div>
        </div>
      </div>
    </>
  );
}
