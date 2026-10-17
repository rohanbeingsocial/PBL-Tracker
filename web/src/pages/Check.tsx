import { useState, type FormEvent } from "react";
import { api, type Project, type ProjectType, type Scored } from "../api";
import { Meter, Notice, PageHead, Segmented, Tags } from "../components/ui";
import { eyebrow, useApp } from "../context";

type Match = Project & Scored & { similarity: number };

function Legend() {
  return (
    <div className="narrow card pad sticky stack" style={{ gap: 14 }}>
      <div className="strong">How to read the score</div>
      <div style={{ display: "flex", height: 8, borderRadius: 2, overflow: "hidden", gap: 1 }}>
        <div style={{ width: "35%", background: "var(--surface-3)" }} />
        <div style={{ width: "15%", background: "var(--accent)" }} />
        <div style={{ width: "20%", background: "var(--warn)" }} />
        <div style={{ width: "30%", background: "var(--down)" }} />
      </div>
      <div className="stack-sm mono" style={{ fontSize: 12, gap: 8 }}>
        <div className="row" style={{ justifyContent: "space-between" }}><span className="band-near">near duplicate</span><span className="muted">0.70 and above</span></div>
        <div className="row" style={{ justifyContent: "space-between" }}><span className="band-similar">similar</span><span className="muted">0.50 to 0.70</span></div>
        <div className="row" style={{ justifyContent: "space-between" }}><span className="band-related">related</span><span className="muted">0.35 to 0.50</span></div>
      </div>
      <div className="muted pretty" style={{ fontSize: 12.5, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
        A high score means: read that project and talk to your faculty member. It is a warning, not proof of copying.
        Approving a near duplicate needs a note from the faculty member.
      </div>
    </div>
  );
}

function Verdict({ top }: { top: Match }) {
  const closest = <><strong>{top.title}</strong> ({top.academic_year}), similarity {top.similarity.toFixed(2)}</>;
  if (top.band === "near duplicate") {
    return <Notice tone="down" kind="Near duplicate">Very close to {closest}. Talk to your faculty member before submitting. If it is approved, they have to write down what is different about yours.</Notice>;
  }
  if (top.band === "similar") {
    return <Notice tone="warn" kind="Similar">Similar to {closest}. Read it first. You might build on it instead of starting over.</Notice>;
  }
  return <Notice tone="up" kind="Clear">No close matches. The nearest project is {closest}.</Notice>;
}

const TYPES = ["software", "hardware", "both"] as const;

function Submit({ title, abstract, onSent }: { title: string; abstract: string; onSent: () => void }) {
  const { me, ref, toast, go } = useApp();
  const [subject, setSubject] = useState(ref.subjects[0]?.subject_id ?? 0);
  const [faculty, setFaculty] = useState(ref.faculty[0]?.user_id ?? 0);
  const [mates, setMates] = useState("");
  const [type, setType] = useState<ProjectType>("software");
  const [tags, setTags] = useState<string[]>([]);
  const [newTag, setNewTag] = useState("");
  const [links, setLinks] = useState([{ label: "GitHub", url: "" }]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const toggleTag = (name: string) =>
    setTags(tags.includes(name) ? tags.filter((x) => x !== name) : tags.length < 12 ? [...tags, name] : tags);
  function addTag() {
    const name = newTag.trim();
    if (name && !tags.some((x) => x.toLowerCase() === name.toLowerCase()) && tags.length < 12) setTags([...tags, name]);
    setNewTag("");
  }
  const setLink = (i: number, field: "label" | "url", value: string) =>
    setLinks(links.map((l, j) => (j === i ? { ...l, [field]: value } : l)));

  async function send() {
    const teammates = mates.split(/[,\s]+/).filter(Boolean);
    const filled = links.filter((l) => l.url.trim());
    if (abstract.trim().length < 30) return setError("A proposal needs an abstract of at least 30 characters. Add one above and check again.");
    if (!teammates.every((m) => /^[0-9]{10}$/.test(m))) return setError("Enter each teammate's 10-digit PRN, separated by commas.");
    if (filled.some((l) => !/^https?:\/\/\S+$/.test(l.url.trim()))) return setError("A link has to start with https:// or http://.");
    setBusy(true);
    setError(null);
    try {
      const sent = await api<{ id: number; faculty: string }>("/proposals", {
        body: { title, abstract, subject_id: subject, faculty_id: faculty, teammates, project_type: type, tags,
                links: filled.map((l) => ({ label: l.label.trim() || "Link", url: l.url.trim() })) },
      });
      toast(`Proposal #${sent.id} sent to ${sent.faculty}. You can follow it on Home.`);
      onSent();
      go("/");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // Tags typed in that aren't in the list yet still show as chips, so they can be taken off again.
  const custom = tags.filter((name) => !ref.tags.some((tg) => tg.name.toLowerCase() === name.toLowerCase()));
  return (
    <div className="card section" style={{ overflow: "hidden", maxWidth: 920 }}>
      <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)" }}>
        <div className="strong">Submit as a proposal</div>
        <div className="small muted" style={{ marginTop: 2 }}>For {ref.current_year}, with you ({me.name}) as team leader. To change the title or abstract, edit them above and check again.</div>
      </div>
      <div style={{ padding: "18px 20px", display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 16 }}>
        <label className="field"><span>Subject</span>
          <select className="select" value={subject} onChange={(e) => setSubject(Number(e.target.value))}>
            {ref.subjects.map((s) => <option key={s.subject_id} value={s.subject_id}>{s.code} · {s.name}</option>)}
          </select>
        </label>
        <label className="field"><span>Faculty</span>
          <select className="select" value={faculty} onChange={(e) => setFaculty(Number(e.target.value))}>
            {ref.faculty.map((f) => <option key={f.user_id} value={f.user_id}>{f.name}</option>)}
          </select>
        </label>
        <label className="field" style={{ gridColumn: "1 / -1" }}><span>Teammates' PRNs</span>
          <input className="input mono" style={{ fontSize: 13 }} value={mates} maxLength={200} onChange={(e) => setMates(e.target.value)} placeholder="1032240102, 1032240103" />
          <small>Any team size. Leave it empty if you are working alone.</small>
        </label>
        <div className="field" style={{ gridColumn: "1 / -1" }}><span>Type</span>
          <Segmented options={TYPES} value={type} onChange={setType} label="Project type" />
        </div>
        <div className="field" style={{ gridColumn: "1 / -1" }}><span>Stack <span className="muted" style={{ fontWeight: 400 }}>· up to 12</span></span>
          <div className="chips">
            {[...ref.tags.map((tg) => tg.name), ...custom].map((name) => (
              <button key={name} className={`chip square${tags.includes(name) ? " on" : ""}`} aria-pressed={tags.includes(name)}
                      disabled={!tags.includes(name) && tags.length >= 12} onClick={() => toggleTag(name)}>{name}</button>
            ))}
          </div>
          <div className="row" style={{ gap: 8, marginTop: 6 }}>
            <input className="input" style={{ maxWidth: 240 }} value={newTag} maxLength={60} placeholder="Not in the list? Type it"
                   aria-label="New stack tag" onChange={(e) => setNewTag(e.target.value)}
                   onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addTag(); } }} />
            <button className="btn" onClick={addTag} disabled={!newTag.trim()}>Add</button>
          </div>
        </div>
        <div className="field" style={{ gridColumn: "1 / -1" }}><span>Links <span className="muted" style={{ fontWeight: 400 }}>· optional, more can be added later</span></span>
          {links.map((l, i) => (
            <div key={i} className="row" style={{ gap: 8, marginBottom: 6 }}>
              <input className="input" style={{ width: 130 }} value={l.label} maxLength={40} aria-label="Link label"
                     onChange={(e) => setLink(i, "label", e.target.value)} />
              <input className="input grow" value={l.url} maxLength={300} aria-label="Link URL" placeholder="https://github.com/team/project"
                     onChange={(e) => setLink(i, "url", e.target.value)} />
            </div>
          ))}
          {links.length < 6 && (
            <button className="link" style={{ alignSelf: "flex-start", padding: 0 }} onClick={() => setLinks([...links, { label: "", url: "" }])}>
              Add another link
            </button>
          )}
        </div>
      </div>
      <div className="row" style={{ padding: "14px 20px", borderTop: "1px solid var(--border)" }}>
        <button className="btn primary" style={{ height: 36 }} onClick={send} disabled={busy}>{busy ? "Sending…" : "Submit proposal"}</button>
        {error && <span className="error-text" role="alert">{error}</span>}
      </div>
    </div>
  );
}

export default function Check() {
  const { me } = useApp();
  const [title, setTitle] = useState("");
  const [abstract, setAbstract] = useState("");
  const [checked, setChecked] = useState<{ title: string; abstract: string; matches: Match[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(e: FormEvent) {
    e.preventDefault();
    if (title.trim().length < 5) return setError("Give the project a title of at least five characters.");
    setBusy(true);
    setError(null);
    try {
      const result = await api<{ matches: Match[] }>("/check", { body: { title, abstract } });
      setChecked({ title: title.trim(), abstract: abstract.trim(), matches: result.matches });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHead eyebrow={eyebrow(me)} title="Check an idea"
                sub="Your title and abstract are compared with every past project by meaning, so a match shows up even when the words are different." />
      <div className="split">
        <div className="wide stack" style={{ gap: 20 }}>
          <form className="card pad-lg stack" style={{ gap: 14 }} onSubmit={run}>
            <label className="field"><span>Project title</span>
              <input className="input" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
            </label>
            <label className="field"><span>Short abstract</span>
              <textarea className="textarea" rows={4} value={abstract} maxLength={1500} onChange={(e) => setAbstract(e.target.value)}
                        placeholder="Three or four lines: what it does, for whom, and how." />
            </label>
            <div className="row">
              <button className="btn primary" style={{ height: 36 }} disabled={busy}>
                {busy ? "Comparing…" : checked ? "Check again" : "Find similar projects"}
              </button>
              <span className="mono" style={{ fontSize: 11, color: "var(--faint)" }}>{abstract.length} / 1500</span>
              {error && <span className="error-text" role="alert">{error}</span>}
            </div>
          </form>
          {busy && <div className="loading-bar"><div /></div>}
          {checked && checked.matches.length === 0 && (
            <div className="empty">No project has an embedding yet, so there is nothing to compare with.</div>
          )}
          {checked && checked.matches.length > 0 && (
            <div className="stack">
              <Verdict top={checked.matches[0]} />
              <div className="label" style={{ marginTop: 8 }}>Closest past projects</div>
              {checked.matches.map((m) => (
                <div key={m.project_id} className="card pad" style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 180px", gap: 24 }}>
                  <div className="stack-sm">
                    <div className="strong">{m.title}</div>
                    <div className="meta">{m.academic_year} · {m.subject} · {m.faculty}</div>
                    <div className="small soft pretty">{m.abstract}</div>
                    <Tags tags={m.tags} type={m.project_type} />
                  </div>
                  <Meter score={m.similarity} />
                </div>
              ))}
            </div>
          )}
        </div>
        <Legend />
      </div>
      {checked && checked.matches.length > 0 && (me.role === "student"
        ? <Submit title={checked.title} abstract={checked.abstract} onSent={() => setChecked(null)} />
        : <div className="small muted section">Only students submit proposals.</div>)}
    </>
  );
}
