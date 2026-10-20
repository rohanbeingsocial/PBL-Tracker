import { useState } from "react";
import { api, type Closest, type Project, type Status } from "../api";
import { AppLink, Closeness, Failed, Loading, Metrics, Notice, PageHead, ProjectCard, StatusTag } from "../components/ui";
import { useApp } from "../context";
import { formatDay } from "../format";
import { useLoad } from "../hooks";

type MyProject = Project & { is_leader: boolean; marks: number | null; max_marks: number };

function Marks({ p }: { p: MyProject }) {
  if (p.status !== "approved") return null;
  return p.marks === null
    ? <span className="small muted" style={{ whiteSpace: "nowrap" }}>Not graded yet</span>
    : <span className="strong" style={{ whiteSpace: "nowrap" }}>{p.marks} / {p.max_marks}</span>;
}

function StudentHome() {
  const { me, ref, go } = useApp();
  const { data, error, loading, reload } = useLoad<{ projects: MyProject[] }>("/home");
  const head = <PageHead title={`Hello, ${me.name.split(" ")[0]}`} sub={`PRN ${me.prn} · ${ref.current_year}`} />;
  if (loading && !data) return <>{head}<Loading /></>;
  if (error || !data) return <>{head}<Failed message={error ?? ""} retry={reload} /></>;

  const current = data.projects.filter((p) => p.academic_year === ref.current_year);
  const earlier = data.projects.filter((p) => p.academic_year !== ref.current_year);
  return (
    <>
      {head}
      <div className="stack" style={{ gap: 14 }}>
        <div className="row">
          <div className="label grow">Your projects this year</div>
          <button className="btn primary" onClick={() => go("/submit")}>Submit a project</button>
        </div>
        {current.map((p) => <ProjectCard key={p.project_id} p={p} extra={<Marks p={p} />} />)}
        {current.length === 0 && <div className="empty">You haven't submitted a project for {ref.current_year} yet.</div>}
        {earlier.length > 0 && (
          <div className="stack section">
            <div className="label">Earlier years</div>
            <div className="card divided" style={{ overflow: "hidden" }}>
              {earlier.map((p) => (
                <AppLink key={p.project_id} to={`/projects/${p.project_id}`} className="row-link">
                  <div className="row" style={{ padding: "12px 18px", gap: 12 }}>
                    <div className="grow"><div className="strong title">{p.title}</div>
                      <div className="meta">{p.academic_year} · {p.subject} · {p.faculty}</div></div>
                    <Marks p={p} />
                    {p.status !== "approved" && <StatusTag status={p.status} />}
                  </div>
                </AppLink>
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
  approved: number;
  graded: number;
  to_grade: { project_id: number; title: string; academic_year: string; subject: string; max_marks: number }[];
}

function FacultyHome() {
  const { me, ref, go } = useApp();
  const { data, error, loading, reload } = useLoad<FacultyData>("/home");
  const head = <PageHead title={`Hello, ${me.name}`} sub={`Projects submitted to you · ${ref.current_year}`} />;
  if (loading) return <>{head}<Loading /></>;
  if (error || !data) return <>{head}<Failed message={error ?? ""} retry={reload} /></>;
  return (
    <>
      {head}
      <Metrics items={[
        { label: "Waiting for review", value: data.waiting.length, tone: data.waiting.length ? "accent" : undefined },
        { label: "Approved", value: data.approved },
        { label: "Graded", value: data.graded },
        { label: "Not graded yet", value: data.to_grade.length },
      ]} />
      <div className="cols-2">
        <div className="stack">
          <div className="label">Waiting for your review</div>
          <div className="card divided" style={{ overflow: "hidden" }}>
            {data.waiting.map((p) => (
              <AppLink key={p.project_id} to={`/projects/${p.project_id}`} className="row-link">
                <div style={{ padding: "12px 18px" }}>
                  <div className="strong title">{p.title}</div>
                  <div className="row meta" style={{ gap: 8 }}>
                    <span className="grow">{p.subject} · submitted {formatDay(p.created_at)}</span>
                    <Closeness band={p.band === "near duplicate" || p.band === "similar" ? p.band : null} score={p.similarity} />
                  </div>
                </div>
              </AppLink>
            ))}
            {data.waiting.length === 0 && <div className="small muted" style={{ padding: "14px 18px" }}>Nothing waiting.</div>}
          </div>
        </div>
        <div className="stack">
          <div className="label">Approved, not graded yet</div>
          <div className="card divided" style={{ overflow: "hidden" }}>
            {data.to_grade.map((p) => (
              <AppLink key={p.project_id} to={`/projects/${p.project_id}`} className="row-link">
                <div style={{ padding: "12px 18px" }}>
                  <div className="strong title">{p.title}</div>
                  <div className="meta">{p.academic_year} · {p.subject} · out of {p.max_marks}</div>
                </div>
              </AppLink>
            ))}
            {data.to_grade.length === 0 && <div className="small muted" style={{ padding: "14px 18px" }}>Every approved project of yours has marks.</div>}
          </div>
          <button className="link" onClick={() => go("/review")}>All your projects</button>
        </div>
      </div>
    </>
  );
}

interface AdminData {
  approved: number;
  waiting: number;
  unembedded: number;
  students: number;
  faculty: number;
  per_year: { academic_year: string; approved: number; submitted: number }[];
  recent: { project_id: number; title: string; subject: string; faculty: string; status: Status; created_at: string }[];
}

function AdminHome() {
  const { ref, toast } = useApp();
  const { data, error, loading, reload } = useLoad<AdminData>("/home");
  const [embedding, setEmbedding] = useState(false);
  const head = <PageHead title="Overview" sub={`Whole department · ${ref.current_year}`} />;
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

  const max = Math.max(1, ...data.per_year.map((y) => y.approved + y.submitted));
  return (
    <>
      {head}
      <Metrics items={[
        { label: "Approved projects", value: data.approved },
        { label: "Waiting for review", value: data.waiting, tone: "accent" },
        { label: "Students", value: data.students },
        { label: "Faculty", value: data.faculty },
      ]} />
      {data.unembedded > 0 && (
        <div style={{ marginBottom: 24 }}>
          <Notice tone="warn">
            {data.unembedded} projects can't be found by meaning search yet.{" "}
            <button className="link" disabled={embedding} onClick={makeEmbeddings}>{embedding ? "Working…" : "Fix it now"}</button>
          </Notice>
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))", gap: 24, alignItems: "start" }}>
        <div className="card pad-lg">
          <div className="strong" style={{ marginBottom: 16 }}>Projects per academic year</div>
          <table className="table">
            <thead><tr><th>Year</th><th className="num">Approved</th><th className="num">Waiting</th><th style={{ width: "45%" }} /></tr></thead>
            <tbody>
              {data.per_year.map((y) => (
                <tr key={y.academic_year}>
                  <td>{y.academic_year}</td>
                  <td className="num">{y.approved}</td>
                  <td className="num">{y.submitted}</td>
                  <td><div style={{ height: 8, width: `${((y.approved + y.submitted) / max) * 100}%`, background: "var(--accent)", borderRadius: 2 }} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card" style={{ overflow: "hidden" }}>
          <div className="strong" style={{ padding: "16px 18px", borderBottom: "1px solid var(--border)" }}>Latest submissions</div>
          <div className="divided">
            {data.recent.map((p) => (
              <AppLink key={p.project_id} to={`/projects/${p.project_id}`} className="row-link">
                <div className="row" style={{ gap: 12, padding: "12px 18px" }}>
                  <div className="grow" style={{ minWidth: 0 }}>
                    <div className="strong ellipsis title">{p.title}</div>
                    <div className="meta">{p.subject} · {p.faculty} · {formatDay(p.created_at)}</div>
                  </div>
                  <StatusTag status={p.status} />
                </div>
              </AppLink>
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
