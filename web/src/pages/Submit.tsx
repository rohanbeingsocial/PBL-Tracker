import { useEffect, useState, type FormEvent } from "react";
import { api, postForm, type Band, type ProjectType } from "../api";
import { AppLink, Closeness, PageHead, Segmented } from "../components/ui";
import { useApp } from "../context";
import { useDebounced } from "../hooks";

const TYPES = ["software", "hardware", "both"] as const;
const TYPE_NAMES = { software: "Software", hardware: "Hardware", both: "Both" };
const MAX_BYTES = 20 * 1024 * 1024;

interface Match {
  project_id: number;
  title: string;
  academic_year: string;
  subject: string;
  similarity: number;
  band: Band;
}

// Past projects close to what is being typed, so a team sees them before submitting.
function SimilarPast({ title, abstract }: { title: string; abstract: string }) {
  const settled = useDebounced(`${title}\n${abstract}`, 700);
  const [matches, setMatches] = useState<Match[] | null>(null);
  useEffect(() => {
    const [t, a] = settled.split("\n");
    if (t.trim().length < 5 || a.trim().length < 30) {
      setMatches(null);
      return;
    }
    let live = true;
    api<{ matches: Match[] }>("/check", { body: { title: t, abstract: a } })
      .then((r) => live && setMatches(r.matches))
      .catch(() => live && setMatches(null));
    return () => {
      live = false;
    };
  }, [settled]);

  return (
    <div className="card pad stack sticky" style={{ gap: 10 }}>
      <div className="strong">Similar past projects</div>
      {matches === null && <div className="small muted">Fill in the title and abstract to see past projects that are about the same thing.</div>}
      {matches?.length === 0 && <div className="small muted">Nothing close. Looks like a new idea.</div>}
      {matches?.map((m) => (
        <div key={m.project_id} className="stack-sm" style={{ gap: 2 }}>
          <AppLink to={`/projects/${m.project_id}`}>{m.title}</AppLink>
          <div className="row meta" style={{ gap: 8 }}><span className="grow">{m.subject} · {m.academic_year}</span><Closeness band={m.band} score={m.similarity} /></div>
        </div>
      ))}
      {matches?.some((m) => m.band === "near duplicate") && (
        <div className="small" style={{ color: "var(--down)" }}>
          Very close to an earlier project. Your faculty member can still approve it, but has to write down what is different about yours.
        </div>
      )}
    </div>
  );
}

export default function Submit() {
  const { me, ref, toast, go } = useApp();
  const [title, setTitle] = useState("");
  const [abstract, setAbstract] = useState("");
  const [subject, setSubject] = useState(0);
  const [faculty, setFaculty] = useState(0);
  const [type, setType] = useState<ProjectType>("software");
  const [mates, setMates] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [newTag, setNewTag] = useState("");
  const [report, setReport] = useState<File | null>(null);
  const [ppt, setPpt] = useState<File | null>(null);
  const [github, setGithub] = useState("");
  const [demo, setDemo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const toggleTag = (name: string) =>
    setTags(tags.includes(name) ? tags.filter((x) => x !== name) : tags.length < 12 ? [...tags, name] : tags);
  function addTag() {
    const name = newTag.trim();
    if (name && !tags.some((x) => x.toLowerCase() === name.toLowerCase()) && tags.length < 12) setTags([...tags, name]);
    setNewTag("");
  }

  function problem(): string | null {
    if (title.trim().length < 5) return "Give the project a title of at least five characters.";
    if (abstract.trim().length < 30) return "The abstract needs at least 30 characters.";
    if (!subject) return "Choose the subject it is for.";
    if (!faculty) return "Choose the faculty member it goes to.";
    if (!mates.split(/[,\s]+/).filter(Boolean).every((m) => /^[0-9]{10}$/.test(m))) return "Enter each teammate's 10-digit PRN, separated by commas.";
    if (!report) return "Attach the project report (PDF).";
    if (!report.name.toLowerCase().endsWith(".pdf")) return "The report has to be a PDF.";
    if (ppt && !/\.(pptx|pdf)$/i.test(ppt.name)) return "The presentation has to be a .pptx or .pdf file.";
    if ([report, ppt].some((f) => f && f.size > MAX_BYTES)) return "Files can be at most 20 MB.";
    if ([github, demo].some((u) => u.trim() && !/^https?:\/\/\S+$/.test(u.trim()))) return "A link has to start with https:// or http://.";
    return null;
  }

  async function send(e: FormEvent) {
    e.preventDefault();
    const wrong = problem();
    if (wrong) return setError(wrong);
    const form = new FormData();
    form.append("title", title.trim());
    form.append("abstract", abstract.trim());
    form.append("subject_id", String(subject));
    form.append("faculty_id", String(faculty));
    form.append("project_type", type);
    form.append("teammates", mates);
    tags.forEach((t) => form.append("tags", t));
    form.append("github", github.trim());
    form.append("demo", demo.trim());
    form.append("report", report!);
    if (ppt) form.append("ppt", ppt);
    setBusy(true);
    setError(null);
    try {
      const sent = await postForm<{ id: number; faculty: string }>("/submissions", form);
      toast(`Submitted to ${sent.faculty}.`);
      go(`/projects/${sent.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const custom = tags.filter((name) => !ref.tags.some((tg) => tg.name.toLowerCase() === name.toLowerCase()));
  const req = <span className="required"> *</span>;
  return (
    <>
      <PageHead title="Submit a project"
                sub={`For ${ref.current_year}, with you (${me.name}) as team leader. The faculty member you choose reviews it and gives the marks.`} />
      <div className="split">
        <form className="wide card pad-lg stack" style={{ gap: 18 }} onSubmit={send}>
          <label className="field"><span>Project title{req}</span>
            <input className="input" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label className="field"><span>Abstract{req}</span>
            <textarea className="textarea" rows={5} value={abstract} maxLength={3000} onChange={(e) => setAbstract(e.target.value)}
                      placeholder="What it does, who it is for, and how it works." />
          </label>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16 }}>
            <label className="field"><span>Subject{req}</span>
              <select className="select" value={subject} onChange={(e) => setSubject(Number(e.target.value))}>
                <option value={0} disabled>Choose a subject</option>
                {ref.subjects.map((s) => <option key={s.subject_id} value={s.subject_id}>{s.code} - {s.name}</option>)}
              </select>
            </label>
            <label className="field"><span>Submit to (faculty){req}</span>
              <select className="select" value={faculty} onChange={(e) => setFaculty(Number(e.target.value))}>
                <option value={0} disabled>Choose a faculty member</option>
                {ref.faculty.map((f) => <option key={f.user_id} value={f.user_id}>{f.name}</option>)}
              </select>
            </label>
          </div>
          <label className="field"><span>Teammates' PRNs</span>
            <input className="input" value={mates} maxLength={300} onChange={(e) => setMates(e.target.value)} placeholder="1032240102, 1032240103" />
            <small>Separate them with commas. Leave it empty if you worked alone.</small>
          </label>
          <div className="field"><span>Type</span>
            <div><Segmented options={TYPES} value={type} onChange={setType} label="Project type" names={TYPE_NAMES} /></div>
          </div>
          <div className="field"><span>Technologies used</span>
            <div className="chips">
              {[...ref.tags.map((tg) => tg.name), ...custom].map((name) => (
                <button key={name} type="button" className={`chip${tags.includes(name) ? " on" : ""}`} aria-pressed={tags.includes(name)}
                        disabled={!tags.includes(name) && tags.length >= 12} onClick={() => toggleTag(name)}>{name}</button>
              ))}
            </div>
            <div className="row" style={{ gap: 8, marginTop: 4 }}>
              <input className="input" style={{ maxWidth: 240 }} value={newTag} maxLength={60} placeholder="Not in the list? Type it"
                     aria-label="New technology" onChange={(e) => setNewTag(e.target.value)}
                     onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addTag(); } }} />
              <button type="button" className="btn" onClick={addTag} disabled={!newTag.trim()}>Add</button>
            </div>
          </div>
          <label className="field"><span>Report (PDF){req}</span>
            <input type="file" accept=".pdf,application/pdf" onChange={(e) => setReport(e.target.files?.[0] ?? null)} />
            <small>Up to 20 MB. This is what people see first when they open the project.</small>
          </label>
          <label className="field"><span>Presentation</span>
            <input type="file" accept=".pptx,.pdf" onChange={(e) => setPpt(e.target.files?.[0] ?? null)} />
            <small>Optional. PowerPoint (.pptx) or PDF, up to 20 MB.</small>
          </label>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16 }}>
            <label className="field"><span>GitHub link</span>
              <input className="input" value={github} maxLength={300} onChange={(e) => setGithub(e.target.value)} placeholder="https://github.com/team/project" />
            </label>
            <label className="field"><span>Working demo link</span>
              <input className="input" value={demo} maxLength={300} onChange={(e) => setDemo(e.target.value)} placeholder="https://..." />
            </label>
          </div>
          <div className="row" style={{ gap: 12 }}>
            <button className="btn primary" style={{ height: 38 }} disabled={busy}>{busy ? "Uploading…" : "Submit project"}</button>
            {error && <span className="error-text" role="alert">{error}</span>}
          </div>
        </form>
        <div className="narrow"><SimilarPast title={title} abstract={abstract} /></div>
      </div>
    </>
  );
}
