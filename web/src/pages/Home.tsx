import { useState } from "react";
import { api, type Closest, type Project, type Status } from "../api";
import { Attachments } from "../components/Attachments";
import { BigScore, Failed, Loading, Meter, Metrics, Notice, PageHead, Resources, StatusTag, Tags } from "../components/ui";
import { eyebrow, useApp } from "../context";
import { formatDay, shortName } from "../format";
import { useLoad, type Path } from "../hooks";

type MyProject = Project & Closest & { is_leader: boolean; marks: number | null; max_marks: number };

function Tiles() {
  const { go } = useApp();
  const tiles: { kicker: string; label: string; body: string; to: Path }[] = [
    { kicker: "Check", label: "Check an idea before submitting", body: "Top 5 closest past projects, scored by meaning.", to: "/check" },
    { kicker: "Search", label: "Search past projects", body: "Keyword, meaning or both, with subject and stack filters.", to: "/search" },
    { kicker: "Trends", label: "See which ideas repeat", body: "Stacks per year and ideas that keep coming back.", to: "/trends" },
  ];
  return (
    <>
      {tiles.map((t) => (
        <button key={t.to} className="card pad stack tile" style={{ gap: 8, textAlign: "left", cursor: "pointer", whiteSpace: "normal" }}
                onClick={() => go(t.to)}>
          <span className="label" style={{ color: "var(--accent)" }}>{t.kicker} →</span>
          <span className="strong">{t.label}</span>
          <span className="small muted">{t.body}</span>
        </button>
      ))}
    </>
  );
}

function Marks({ p }: { p: MyProject }) {
  if (p.status !== "approved" && p.status !== "completed") return null;
  return p.marks === null
    ? <span className="small muted">Not marked yet</span>
    : <span className="mono strong">{p.marks} / {p.max_marks}</span>;
}

const STEPS = ["Checked against past work", "Submitted", "Faculty decides"];

function Focus({ p, onChanged }: { p: MyProject; onChanged: () => void }) {
  // Steps 1 and 2 are done for anything that exists; 3 is done once the faculty decided.
  const done = [true, true, p.status !== "proposed", p.status === "approved" || p.status === "completed"];
  const now = done.indexOf(false);
  const labels = [...STEPS, p.status === "rejected" ? "Rejected" : "Approved"];
  return (
    <div className="card big">
      <div className="row-top pad-lg" style={{ borderBottom: "1px solid var(--border)", gap: 16 }}>
        <div className="grow">
          <div className="label">Proposal #{p.project_id} · {p.subject}</div>
          <div style={{ fontSize: 22, fontWeight: 650, letterSpacing: "-0.02em", marginTop: 6 }}>{p.title}</div>
          <div className="meta" style={{ marginTop: 4 }}>{p.faculty} · team {p.members}</div>
        </div>
        <StatusTag status={p.status} />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", borderBottom: "1px solid var(--border)" }}>
        {labels.map((label, i) => {
          const isDone = done[i] && !(i === 3 && p.status === "rejected");
          const isNow = i === now;
          return (
            <div key={label} style={{ padding: "14px 18px", borderLeft: i ? "1px solid var(--border)" : 0, display: "flex", flexDirection: "column", gap: 8,
                                      background: isNow ? "var(--accent-soft)" : "transparent" }}>
              <div style={{ height: 3, borderRadius: 2, background: p.status === "rejected" && i >= 2 ? "var(--down)" : isDone ? "var(--up)" : isNow ? "var(--accent)" : "var(--surface-3)" }} />
              <div className="row" style={{ gap: 8, alignItems: "baseline" }}>
                <span className="mono" style={{ fontSize: 11, color: isDone ? "var(--up)" : isNow ? "var(--accent)" : "var(--faint)" }}>
                  {isDone ? "✓" : String(i + 1).padStart(2, "0")}
                </span>
                <span style={{ fontSize: 13, fontWeight: 500, color: isDone || isNow ? "var(--fg)" : "var(--muted)" }}>{label}</span>
              </div>
            </div>
          );
        })}
      </div>
      {p.closest_title && p.similarity !== null ? (
        <div className="compare">
          <div className="pad-lg">
            <div className="label-sm" style={{ marginBottom: 8 }}>Your proposal</div>
            <div className="soft pretty" style={{ fontSize: 13.5 }}>{p.abstract}</div>
          </div>
          <div className="mid pad-lg">
            <BigScore score={p.similarity} size={40} />
            <Meter score={p.similarity} large hideLabel />
            <div className="muted" style={{ fontSize: 12 }}>Similarity by meaning, 0 to 1</div>
          </div>
          <div className="pad-lg">
            <div className="label-sm" style={{ marginBottom: 8 }}>Closest past project · {p.closest_year}</div>
            <div className="strong" style={{ marginBottom: 4 }}>{p.closest_title}</div>
            <div className="soft pretty" style={{ fontSize: 13.5 }}>{p.closest_abstract}</div>
          </div>
        </div>
      ) : (
        <div className="pad-lg soft pretty" style={{ fontSize: 13.5 }}>{p.abstract}</div>
      )}
      {p.band === "near duplicate" && p.status === "proposed" && (
        <div style={{ padding: "12px 24px", borderTop: "1px solid var(--border)", background: "var(--warn-soft)", fontSize: 13 }}>
          <span className="mono" style={{ color: "var(--warn)", marginRight: 8 }}>NOTE</span>
          Your faculty member can only approve it with a note on what is different about yours.
        </div>
      )}
      <div className="pad-lg" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="label-sm" style={{ marginBottom: 8 }}>Links and files</div>
        <Attachments p={p} onChanged={onChanged} />
      </div>
    </div>
  );
}

function ProjectPanel({ p, onChanged }: { p: MyProject; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="card pad stack" style={{ gap: 10 }}>
      <div className="row-top" style={{ gap: 12 }}>
        <div className="grow">
          <div className="strong">{p.title}</div>
          <div className="meta" style={{ marginTop: 2 }}>{p.subject} · {p.faculty} · team {p.members}</div>
        </div>
        <Marks p={p} />
        <StatusTag status={p.status} />
      </div>
      <Tags tags={p.tags} type={p.project_type} />
      {p.review_note && <div className="small muted">Faculty note: {p.review_note}</div>}
      {open ? <Attachments p={p} onChanged={onChanged} /> : <Resources links={p.links} files={p.files} />}
      <button className="link" style={{ alignSelf: "flex-start", padding: 0 }} onClick={() => setOpen(!open)}>
        {open ? "Done" : "Add links, report or presentation"}
      </button>
    </div>
  );
}

function StudentHome() {
  const { me, ref } = useApp();
  const { data, error, loading, reload } = useLoad<{ projects: MyProject[] }>("/home");
  const head = <PageHead eyebrow={eyebrow(me)} title={`Welcome, ${shortName(me.name, "student")}`} sub={`PRN ${me.prn} · ${ref.current_year}`} />;
  if (loading && !data) return <>{head}<Loading /></>;
  if (error || !data) return <>{head}<Failed message={error ?? ""} retry={reload} /></>;

  const current = data.projects.filter((p) => p.academic_year === ref.current_year);
  const earlier = data.projects.filter((p) => p.academic_year !== ref.current_year);
  // A proposal still waiting for a decision goes first; it is the one to watch.
  const focus = current.find((p) => p.status === "proposed");
  const others = current.filter((p) => p !== focus);
  return (
    <>
      {head}
      <div className="stack" style={{ gap: 20 }}>
        {focus && <Focus p={focus} onChanged={reload} />}
        {current.length === 0 && (
          <div className="card pad-lg stack" style={{ gap: 6 }}>
            <div className="strong">You are not in a project for {ref.current_year} yet.</div>
            <div className="small muted">Check your idea against past projects first, then submit it as a proposal from the same page.</div>
          </div>
        )}
        {others.length > 0 && <div className="label">Your projects this year · {others.length}</div>}
        {others.map((p) => <ProjectPanel key={p.project_id} p={p} onChanged={reload} />)}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16 }}>
          <Tiles />
        </div>
        {earlier.length > 0 && (
          <div className="stack section">
            <div className="label">Earlier projects</div>
            <div className="card divided">
              {earlier.map((p) => (
                <div key={p.project_id} className="row" style={{ padding: "12px 18px", gap: 12 }}>
                  <div className="grow"><div className="strong" style={{ fontSize: 13.5 }}>{p.title}</div>
                    <div className="meta">{p.academic_year} · {p.subject} · {p.faculty}</div></div>
                  <Marks p={p} />
                  <StatusTag status={p.status} />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  );
}

interface FacultyData {
  waiting: (Closest & { project_id: number; title: string; subject: string; created_at: string })[];
  running: number;
  guided: number;
  to_mark: { project_id: number; title: string; academic_year: string; subject: string; max_marks: number }[];
}

function FacultyHome() {
  const { me, ref, go } = useApp();
  const { data, error, loading, reload } = useLoad<FacultyData>("/home");
  const head = <PageHead eyebrow={eyebrow(me)} title={`Welcome, ${me.name}`} sub={`Your projects · ${ref.current_year}`} />;
  if (loading) return <>{head}<Loading /></>;
  if (error || !data) return <>{head}<Failed message={error ?? ""} retry={reload} /></>;
  return (
    <>
      {head}
      <Metrics items={[
        { label: "Waiting for you", value: data.waiting.length, tone: data.waiting.length ? "accent" : undefined },
        { label: "Running projects", value: data.running },
        { label: "Not marked yet", value: data.to_mark.length },
        { label: "Projects so far", value: data.guided, note: "all years, rejected left out" },
      ]} />
      <div className="cols-2">
        <div className="stack">
          <div className="label">Waiting for your decision</div>
          {data.waiting.map((p) => (
            <div key={p.project_id} className="card pad stack" style={{ gap: 10 }}>
              <div>
                <div className="strong">{p.title}</div>
                <div className="meta" style={{ marginTop: 2 }}>{p.subject} · sent {formatDay(p.created_at)}</div>
              </div>
              {p.closest_title && p.similarity !== null ? (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: "10px 16px", alignItems: "end" }}>
                  <div className="muted" style={{ fontSize: 12.5 }}>Closest: <span className="soft">{p.closest_title} ({p.closest_year})</span></div>
                  <Meter score={p.similarity} />
                </div>
              ) : <div className="small muted">No embedding yet, so it hasn't been compared with past projects.</div>}
            </div>
          ))}
          {data.waiting.length === 0
            ? <div className="empty">Nothing waiting. New proposals from your students show up here.</div>
            : <button className="link" onClick={() => go("/review")}>Open the review queue →</button>}
        </div>
        <div className="stack">
          <div className="label">Not marked yet</div>
          {data.to_mark.map((p) => (
            <div key={p.project_id} className="card pad stack" style={{ gap: 4 }}>
              <div className="strong">{p.title}</div>
              <div className="meta">{p.academic_year} · {p.subject} · out of {p.max_marks}</div>
            </div>
          ))}
          {data.to_mark.length === 0
            ? <div className="empty"><span style={{ color: "var(--up)" }} className="mono">✓ </span>Every approved and completed project of yours has marks.</div>
            : <button className="link" onClick={() => go("/marks")}>Enter marks →</button>}
        </div>
      </div>
    </>
  );
}

interface AdminData {
  on_record: number;
  waiting: number;
  unembedded: number;
  students: number;
  faculty: number;
  per_year: { academic_year: string; completed: number; approved: number; proposed: number }[];
  recent: { project_id: number; title: string; subject: string; faculty: string; status: Status; created_at: string }[];
}

function AdminHome() {
  const { me, ref, toast } = useApp();
  const { data, error, loading, reload } = useLoad<AdminData>("/home");
  const [embedding, setEmbedding] = useState(false);
  const head = <PageHead eyebrow={eyebrow(me)} title="Overview" sub={`Whole department · ${ref.current_year}`} />;
  if (loading && !data) return <>{head}<Loading /></>;
  if (error || !data) return <>{head}<Failed message={error ?? ""} retry={reload} /></>;

  async function makeEmbeddings() {
    setEmbedding(true);
    try {
      const result = await api<{ created: number }>("/embeddings", { method: "POST" });
      toast(`Made ${result.created} embeddings.`);
      reload();
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setEmbedding(false);
    }
  }

  const max = Math.max(1, ...data.per_year.map((y) => y.completed + y.approved + y.proposed));
  const legend = [["completed", "var(--accent)"], ["approved", "var(--up)"], ["proposed", "color-mix(in oklab, var(--accent) 55%, transparent)"]];
  return (
    <>
      {head}
      <Metrics items={[
        { label: "Projects on record", value: data.on_record, note: "rejected left out" },
        { label: "Waiting for review", value: data.waiting, note: "all faculty", tone: "accent" },
        { label: "Students", value: data.students, note: "switched on" },
        { label: "Faculty", value: data.faculty, note: "switched on" },
      ]} />
      {data.unembedded > 0 && (
        <div style={{ marginBottom: 24 }}>
          <Notice tone="warn" kind="Embeddings">
            {data.unembedded} projects can't be found by meaning search yet.{" "}
            <button className="link" disabled={embedding} onClick={makeEmbeddings}>{embedding ? "Making them…" : "Make them now"}</button>
          </Notice>
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))", gap: 24, alignItems: "start" }}>
        <div className="card pad-lg">
          <div className="row wrap" style={{ alignItems: "baseline", marginBottom: 18 }}>
            <div className="strong grow">Projects per academic year</div>
            {legend.map(([label, color]) => (
              <span key={label} className="row mono" style={{ gap: 6, fontSize: 11, color: "var(--muted)" }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: color }} />{label}
              </span>
            ))}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: `repeat(${data.per_year.length}, minmax(0, 1fr))`, gap: 14, alignItems: "end", height: 220, borderBottom: "1px solid rgba(148,163,184,0.25)", padding: "0 4px" }}>
            {data.per_year.map((y) => {
              const h = (n: number) => `${Math.round((n / max) * 170)}px`;
              return (
                <div key={y.academic_year} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, height: "100%", justifyContent: "flex-end" }}
                     title={`${y.academic_year}: ${y.completed} completed, ${y.approved} approved, ${y.proposed} proposed`}>
                  <span className="mono soft" style={{ fontSize: 12 }}>{y.completed + y.approved + y.proposed}</span>
                  <div style={{ width: "100%", maxWidth: 44, display: "flex", flexDirection: "column", gap: 2 }}>
                    {y.proposed > 0 && <div style={{ height: h(y.proposed), background: "var(--accent)", opacity: 0.55, borderRadius: "3px 3px 0 0" }} />}
                    {y.approved > 0 && <div style={{ height: h(y.approved), background: "var(--up)", borderRadius: y.proposed ? 0 : "3px 3px 0 0" }} />}
                    {y.completed > 0 && <div style={{ height: h(y.completed), background: "var(--accent)", borderRadius: y.proposed || y.approved ? 0 : "3px 3px 0 0" }} />}
                  </div>
                </div>
              );
            })}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: `repeat(${data.per_year.length}, minmax(0, 1fr))`, gap: 14, padding: "8px 4px 0" }}>
            {data.per_year.map((y) => <span key={y.academic_year} className="mono muted" style={{ textAlign: "center", fontSize: 11 }}>{y.academic_year}</span>)}
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 14 }}>Rejected proposals are left out. {ref.current_year} is still running.</div>
        </div>
        <div className="card" style={{ overflow: "hidden" }}>
          <div className="strong" style={{ padding: "16px 18px", borderBottom: "1px solid var(--border)" }}>Newest projects</div>
          <div className="divided">
            {data.recent.map((p) => (
              <div key={p.project_id} className="row" style={{ gap: 12, padding: "12px 18px" }}>
                <div className="grow" style={{ minWidth: 0 }}>
                  <div className="strong ellipsis" style={{ fontSize: 13 }}>{p.title}</div>
                  <div className="meta">{p.subject} · {p.faculty} · {formatDay(p.created_at)}</div>
                </div>
                <StatusTag status={p.status} />
              </div>
            ))}
            {data.recent.length === 0 && <div className="small muted" style={{ padding: "12px 18px" }}>No projects yet.</div>}
          </div>
        </div>
      </div>
    </>
  );
}

export default function Home() {
  const { me } = useApp();
  return me.is_admin ? <AdminHome /> : me.role === "student" ? <StudentHome /> : <FacultyHome />;
}
