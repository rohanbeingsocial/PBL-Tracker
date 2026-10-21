import { useState } from "react";
import { api, type Closest, type Project, type Status } from "../api";
import { Bars, Columns, Donut, Icon, Legend, Panel, Ring, StatTile, type Slice } from "../components/charts";
import { AppLink, Closeness, Failed, Loading, Notice, PageHead, StatusTag } from "../components/ui";
import { useApp } from "../context";
import { formatDay } from "../format";
import { useLoad } from "../hooks";

type MyProject = Project & { is_leader: boolean; marks: number | null; max_marks: number };

const percent = (marks: number, max: number) => Math.round((100 * marks) / max);

// Where a project is: submitted, then decided, then graded.
function Steps({ p }: { p: MyProject }) {
  const decided = p.status !== "submitted";
  const graded = p.marks !== null;
  const steps = [
    { name: "Submitted", done: true, bad: false },
    { name: p.status === "rejected" ? "Rejected" : "Approved", done: decided, bad: p.status === "rejected" },
    { name: "Graded", done: graded, bad: false },
  ];
  if (p.status === "rejected") steps.pop();
  return (
    <div className="steps">
      {steps.map((s) => (
        <div key={s.name} className={`step${s.done ? " done" : ""}${s.bad ? " bad" : ""}`}>
          <span className="step-dot">{s.done && <Icon name={s.bad ? "cross" : "check"} size={11} />}</span>
          {s.name}
        </div>
      ))}
    </div>
  );
}

function MyProjectTile({ p }: { p: MyProject }) {
  return (
    <AppLink to={`/projects/${p.project_id}`} className="card pad row-link project-tile">
      <div className="row-top" style={{ gap: 14 }}>
        <div className="grow">
          <div className="strong title" style={{ fontSize: 15 }}>{p.title}</div>
          <div className="meta">{p.subject} · {p.faculty}{p.is_leader ? " · you lead" : ""}</div>
        </div>
        {p.marks !== null
          ? <div className="stack-sm" style={{ alignItems: "center", gap: 2 }}>
              <Ring value={p.marks} max={p.max_marks} />
              <span className="small strong">{p.marks} / {p.max_marks}</span>
            </div>
          : <StatusTag status={p.status} />}
      </div>
      <Steps p={p} />
    </AppLink>
  );
}

interface StudentData {
  projects: MyProject[];
  popular: { tag: string; projects: number }[];
  approved: { project_id: number; title: string; subject: string; academic_year: string; faculty: string; members: string; decided_at: string }[];
}

function StudentHome() {
  const { me, ref, go } = useApp();
  const { data, error, loading, reload } = useLoad<StudentData>("/home");
  const head = <PageHead title={`Hello, ${me.name.split(" ")[0]}`} sub={`PRN ${me.prn} · ${ref.current_year}`} />;
  if (loading && !data) return <>{head}<Loading /></>;
  if (error || !data) return <>{head}<Failed message={error ?? ""} retry={reload} /></>;

  const all = data.projects;
  const current = all.filter((p) => p.academic_year === ref.current_year);
  const earlier = all.filter((p) => p.academic_year !== ref.current_year);
  const graded = all.filter((p) => p.marks !== null);
  const average = graded.length
    ? Math.round(graded.reduce((a, p) => a + percent(p.marks!, p.max_marks), 0) / graded.length) : null;
  const count = (s: Status) => all.filter((p) => p.status === s).length;
  const slices: Slice[] = [
    { label: "Approved", value: count("approved"), tone: "up" },
    { label: "Waiting for review", value: count("submitted"), tone: "warn" },
    { label: "Rejected", value: count("rejected"), tone: "down" },
  ];
  return (
    <>
      <div className="row head-row">
        {head}
        <button className="btn primary" onClick={() => go("/submit")}><Icon name="upload" size={16} />Submit a project</button>
      </div>
      <div className="tiles">
        <StatTile icon="folder" label="Your projects" value={all.length} hint={`${current.length} this year`} />
        <StatTile icon="check" label="Approved" value={count("approved")} tone="up" />
        <StatTile icon="clock" label="Waiting for review" value={count("submitted")} tone="warn" />
        <StatTile icon="star" label="Average marks" value={average === null ? "–" : `${average}%`}
                  hint={graded.length ? `over ${graded.length} graded` : "nothing graded yet"} />
      </div>

      <div className="dash">
        <div className="dash-main">
          <Panel title={`This year · ${ref.current_year}`} sub="Where each of your projects is">
            <div className="stack">
              {current.map((p) => <MyProjectTile key={p.project_id} p={p} />)}
              {current.length === 0 && (
                <div className="empty row">
                  <span className="grow">You haven't submitted a project for {ref.current_year} yet.</span>
                  <button className="btn" onClick={() => go("/submit")}>Submit one</button>
                </div>
              )}
            </div>
          </Panel>
          {graded.length > 0 && (
            <Panel title="Your marks" sub="Each graded project, as a share of its subject's maximum">
              <Columns suffix="%" columns={graded.slice().reverse().map((p) => ({
                label: `${p.subject} ${p.academic_year.slice(2)}`,
                parts: [{ name: p.title, value: percent(p.marks!, p.max_marks), tone: "accent" }],
              }))} />
            </Panel>
          )}
          <Panel title="Recently approved" sub="New in the department" flush
                 action={<button className="link" onClick={() => go("/search")}>Search all</button>}>
            <div className="divided">
              {data.approved.map((p) => (
                <AppLink key={p.project_id} to={`/projects/${p.project_id}`} className="row-link">
                  <div className="row" style={{ gap: 12, padding: "11px 18px" }}>
                    <div className="tile-icon small-icon"><Icon name="file" size={16} /></div>
                    <div className="grow" style={{ minWidth: 0 }}>
                      <div className="strong ellipsis title">{p.title}</div>
                      <div className="meta ellipsis">{p.subject} · {p.faculty}{p.members ? ` · ${p.members}` : ""}</div>
                    </div>
                    <span className="small muted" style={{ whiteSpace: "nowrap" }}>{formatDay(p.decided_at)}</span>
                  </div>
                </AppLink>
              ))}
              {data.approved.length === 0 && <div className="small muted" style={{ padding: "12px 18px" }}>Nothing approved yet.</div>}
            </div>
          </Panel>
          {earlier.length > 0 && (
            <Panel title="Earlier years" flush>
              <div className="divided">
                {earlier.map((p) => (
                  <AppLink key={p.project_id} to={`/projects/${p.project_id}`} className="row-link">
                    <div className="row" style={{ padding: "12px 18px", gap: 12 }}>
                      <div className="grow"><div className="strong title">{p.title}</div>
                        <div className="meta">{p.academic_year} · {p.subject} · {p.faculty}</div></div>
                      {p.marks !== null ? <Ring value={p.marks} max={p.max_marks} size={40} /> : <StatusTag status={p.status} />}
                    </div>
                  </AppLink>
                ))}
              </div>
            </Panel>
          )}
        </div>
        <div className="dash-side">
          <Panel title="Your projects by status">
            <div className="donut-row">
              <Donut slices={slices} size={120}>
                <div className="donut-total">{all.length}</div><div className="small muted">projects</div>
              </Donut>
              <Legend slices={slices} />
            </div>
          </Panel>
          <Panel title="Popular stacks" sub="Approved projects, last two years">
            {data.popular.length
              ? <Bars rows={data.popular.map((t) => ({ label: t.tag, value: t.projects }))} />
              : <div className="small muted">No approved projects yet.</div>}
          </Panel>
        </div>
      </div>
    </>
  );
}

interface FacultyData {
  waiting: (Closest & { project_id: number; title: string; subject: string; created_at: string })[];
  approved: number;
  rejected: number;
  graded: number;
  to_grade: { project_id: number; title: string; academic_year: string; subject: string; max_marks: number }[];
  by_subject: { subject: string; approved: number; waiting: number; average_percent: number | null }[];
  percents: number[];
}

const BUCKETS = [[0, 50, "<50"], [50, 60, "50s"], [60, 70, "60s"], [70, 80, "70s"], [80, 90, "80s"], [90, 101, "90+"]] as const;

function FacultyHome() {
  const { me, ref, go } = useApp();
  const { data, error, loading, reload } = useLoad<FacultyData>("/home");
  const head = <PageHead title={`Hello, ${me.name}`} sub={`Projects submitted to you · ${ref.current_year}`} />;
  if (loading) return <>{head}<Loading /></>;
  if (error || !data) return <>{head}<Failed message={error ?? ""} retry={reload} /></>;

  const slices: Slice[] = [
    { label: "Waiting for review", value: data.waiting.length, tone: "warn" },
    { label: "Approved, graded", value: data.graded, tone: "up" },
    { label: "Approved, not graded", value: data.to_grade.length, tone: "accent" },
    { label: "Rejected", value: data.rejected, tone: "down" },
  ];
  const total = slices.reduce((a, s) => a + s.value, 0);
  const average = data.percents.length
    ? Math.round(data.percents.reduce((a, b) => a + b, 0) / data.percents.length) : null;
  return (
    <>
      {head}
      <div className="tiles">
        <StatTile icon="clock" label="Waiting for review" value={data.waiting.length} tone="warn" />
        <StatTile icon="check" label="Approved" value={data.approved} tone="up" />
        <StatTile icon="review" label="Not graded yet" value={data.to_grade.length} />
        <StatTile icon="star" label="Average marks given" value={average === null ? "–" : `${average}%`}
                  hint={`${data.graded} graded`} />
      </div>

      <div className="dash">
        <div className="dash-main">
          <Panel title="Waiting for your review" sub="Oldest first, with the closest past project" flush
                 action={<button className="link" onClick={() => go("/review")}>All projects</button>}>
            <div className="divided">
              {data.waiting.map((p) => (
                <AppLink key={p.project_id} to={`/projects/${p.project_id}`} className="row-link">
                  <div className="row" style={{ padding: "12px 18px", gap: 14 }}>
                    <div className="grow">
                      <div className="strong title">{p.title}</div>
                      <div className="meta">{p.subject} · submitted {formatDay(p.created_at)}
                        {p.closest_title ? ` · closest: ${p.closest_title} (${p.closest_year})` : ""}</div>
                    </div>
                    {p.similarity !== null && (
                      <div className="stack-sm" style={{ width: 120, gap: 4, alignItems: "flex-end" }}>
                        <div className="meter"><div style={{
                          width: `${Math.round(p.similarity * 100)}%`,
                          background: p.band === "near duplicate" ? "var(--down-fill)" : p.band === "similar" ? "var(--warn-fill)" : "var(--accent-fill)",
                        }} /></div>
                        <Closeness band={p.band} score={p.similarity} />
                      </div>
                    )}
                  </div>
                </AppLink>
              ))}
              {data.waiting.length === 0 && <div className="small muted" style={{ padding: "14px 18px" }}>Nothing waiting.</div>}
            </div>
          </Panel>
          <div className="cols-2" style={{ gap: 20 }}>
            <Panel title="Projects by subject" sub="Approved and waiting">
              <Columns height={150} columns={data.by_subject.map((s) => ({
                label: s.subject,
                parts: [{ name: "Approved", value: s.approved, tone: "up" }, { name: "Waiting", value: s.waiting, tone: "warn" }],
              }))} />
            </Panel>
            <Panel title="Marks you gave" sub="Graded projects by share of the maximum">
              {data.percents.length
                ? <Columns height={150} columns={BUCKETS.map(([lo, hi, label]) => ({
                    label, parts: [{ name: "Projects", value: data.percents.filter((x) => x >= lo && x < hi).length, tone: "accent" }],
                  }))} />
                : <div className="small muted">Nothing graded yet.</div>}
            </Panel>
          </div>
        </div>
        <div className="dash-side">
          <Panel title="All your projects">
            <div className="donut-row">
              <Donut slices={slices} size={120}>
                <div className="donut-total">{total}</div><div className="small muted">projects</div>
              </Donut>
              <Legend slices={slices} />
            </div>
          </Panel>
          <Panel title="Approved, not graded yet" flush>
            <div className="divided">
              {data.to_grade.map((p) => (
                <AppLink key={p.project_id} to={`/projects/${p.project_id}`} className="row-link">
                  <div style={{ padding: "10px 18px" }}>
                    <div className="strong title">{p.title}</div>
                    <div className="meta">{p.academic_year} · {p.subject} · out of {p.max_marks}</div>
                  </div>
                </AppLink>
              ))}
              {data.to_grade.length === 0 && <div className="small muted" style={{ padding: "14px 18px" }}>Every approved project of yours has marks.</div>}
            </div>
          </Panel>
          {data.by_subject.some((s) => s.average_percent !== null) && (
            <Panel title="Average marks by subject">
              <Bars suffix="%" rows={data.by_subject.filter((s) => s.average_percent !== null)
                .map((s) => ({ label: s.subject, value: s.average_percent! }))} />
            </Panel>
          )}
        </div>
      </div>
    </>
  );
}

interface AdminData {
  approved: number;
  waiting: number;
  rejected: number;
  unembedded: number;
  students: number;
  faculty: number;
  per_year: { academic_year: string; approved: number; submitted: number; rejected: number }[];
  by_subject: { subject: string; projects: number }[];
  load: { faculty: string; waiting: number; approved: number }[];
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

  const slices: Slice[] = [
    { label: "Approved", value: data.approved, tone: "up" },
    { label: "Waiting for review", value: data.waiting, tone: "warn" },
    { label: "Rejected", value: data.rejected, tone: "down" },
  ];
  const thisYear = data.per_year.find((y) => y.academic_year === ref.current_year);
  return (
    <>
      {head}
      <div className="tiles">
        <StatTile icon="check" label="Approved projects" value={data.approved} tone="up"
                  hint={`${data.per_year.length} academic years`} />
        <StatTile icon="clock" label="Waiting for review" value={data.waiting} tone="warn"
                  hint={thisYear ? `${thisYear.submitted + thisYear.approved} submitted this year` : undefined} />
        <StatTile icon="people" label="Students" value={data.students} />
        <StatTile icon="user" label="Faculty" value={data.faculty} />
      </div>
      {data.unembedded > 0 && (
        <div style={{ marginBottom: 20 }}>
          <Notice tone="warn">
            {data.unembedded} projects can't be found by meaning search yet.{" "}
            <button className="link" disabled={embedding} onClick={makeEmbeddings}>{embedding ? "Working…" : "Fix it now"}</button>
          </Notice>
        </div>
      )}

      <div className="dash">
        <div className="dash-main">
          <Panel title="Projects per academic year"
                 action={<Legend slices={slices} inline />}>
            <Columns columns={data.per_year.map((y) => ({
              label: y.academic_year,
              parts: [
                { name: "Approved", value: y.approved, tone: "up" },
                { name: "Waiting", value: y.submitted, tone: "warn" },
                { name: "Rejected", value: y.rejected, tone: "down" },
              ],
            }))} />
          </Panel>
          <Panel title="Latest submissions" flush>
            <div className="divided">
              {data.recent.map((p) => (
                <AppLink key={p.project_id} to={`/projects/${p.project_id}`} className="row-link">
                  <div className="row" style={{ gap: 12, padding: "11px 18px" }}>
                    <div className="tile-icon small-icon"><Icon name="file" size={16} /></div>
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
          </Panel>
        </div>
        <div className="dash-side">
          <Panel title="All projects">
            <div className="donut-row">
              <Donut slices={slices} size={120}>
                <div className="donut-total">{data.approved + data.waiting + data.rejected}</div><div className="small muted">projects</div>
              </Donut>
              <Legend slices={slices} />
            </div>
          </Panel>
          <Panel title="By subject" sub="Approved and waiting, all years">
            <Bars rows={data.by_subject.map((s) => ({ label: s.subject, value: s.projects }))} />
          </Panel>
          <Panel title={`Faculty load · ${ref.current_year}`} sub="Projects still waiting for each faculty member">
            {data.load.length
              ? <Bars tone="warn" rows={data.load.map((f) => ({ label: f.faculty, value: f.waiting, note: `${f.approved} approved` }))} />
              : <div className="small muted">No projects this year yet.</div>}
          </Panel>
        </div>
      </div>
    </>
  );
}

export default function Home() {
  const { me } = useApp();
  return me.is_admin ? <AdminHome /> : me.role === "student" ? <StudentHome /> : <FacultyHome />;
}
