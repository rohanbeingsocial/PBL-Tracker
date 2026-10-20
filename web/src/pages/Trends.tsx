import type { Band } from "../api";
import { Closeness, Failed, Loading, Metrics, PageHead } from "../components/ui";
import { useLoad } from "../hooks";

interface TrendsData {
  year: string;
  totals: { projects: number; years: number; waiting: number };
  pairs: { first_title: string; first_year: string; second_title: string; second_year: string; similarity: number; band: Band }[];
  types: { project_type: string; projects: number }[];
  tags: { tag: string; academic_year: string; project_count: number }[];
  load: { faculty: string; projects: number; waiting: number }[];
}

function Heatmap({ rows, years }: { rows: TrendsData["tags"]; years: string[] }) {
  const counts = new Map<string, Map<string, number>>();
  for (const r of rows) {
    if (!counts.has(r.tag)) counts.set(r.tag, new Map());
    counts.get(r.tag)!.set(r.academic_year, r.project_count);
  }
  const max = Math.max(1, ...rows.map((r) => r.project_count));
  const total = (d: string) => [...counts.get(d)!.values()].reduce((a, b) => a + b, 0);
  const tags = [...counts.keys()].sort((a, b) => total(b) - total(a) || a.localeCompare(b));
  const grid = { display: "grid", gridTemplateColumns: `140px repeat(${years.length}, minmax(0, 1fr)) 44px`, gap: 3, alignItems: "center" };
  return (
    <div role="table" aria-label="Projects per stack tag per year">
      <div style={grid} role="row">
        <span />
        {years.map((y) => <span key={y} className="muted" style={{ fontSize: 12, textAlign: "center", paddingBottom: 4 }}>{y}</span>)}
        <span className="muted" style={{ fontSize: 12, textAlign: "right", paddingBottom: 4 }}>Total</span>
      </div>
      {tags.map((d) => (
        <div key={d} style={{ ...grid, marginTop: 3 }} role="row">
          <span className="soft ellipsis" style={{ fontSize: 12.5 }}>{d}</span>
          {years.map((y) => {
            const n = counts.get(d)!.get(y) ?? 0;
            const share = n / max;
            return (
              <div key={y} title={`${d} · ${y} · ${n}`} role="cell"
                   style={{ height: 26, borderRadius: 3, display: "flex", alignItems: "center", justifyContent: "center",
                            fontSize: 12, fontWeight: 600,
                            background: n ? `color-mix(in oklab, var(--accent) ${Math.round(22 + 78 * share)}%, var(--surface-2))` : "var(--surface-2)",
                            color: share > 0.55 ? "var(--accent-fg)" : "var(--fg-soft)" }}>
                {n || ""}
              </div>
            );
          })}
          <span style={{ fontSize: 12.5, textAlign: "right" }}>{total(d)}</span>
        </div>
      ))}
    </div>
  );
}

export default function Trends() {
  const { data, error, loading, reload } = useLoad<TrendsData>("/trends");
  const head = <PageHead title="Trends" sub="Which ideas and stacks come up again and again, and how many projects each faculty member has." />;
  if (loading) return <>{head}<Loading /></>;
  if (error || !data) return <>{head}<Failed message={error ?? ""} retry={reload} /></>;

  const years = [...new Set(data.tags.map((d) => d.academic_year))].sort();
  const totals = new Map<string, number>();
  for (const r of data.tags) totals.set(r.tag, (totals.get(r.tag) ?? 0) + r.project_count);
  const top = [...totals.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 8);
  const topCount = Math.max(1, ...top.map(([, n]) => n));
  const typeCount = (k: string) => data.types.find((x) => x.project_type === k)?.projects ?? 0;
  return (
    <>
      {head}
      <Metrics items={[
        { label: "Approved projects", value: data.totals.projects },
        { label: "Academic years", value: data.totals.years },
        { label: "Very close pairs", value: data.pairs.filter((p) => p.band === "near duplicate").length },
        { label: "Hardware projects", value: typeCount("hardware") + typeCount("both") },
      ]} />
      <div className="stack" style={{ gap: 20 }}>
        <div className="card pad-lg">
          <div className="row" style={{ alignItems: "baseline", marginBottom: 16 }}>
            <div className="strong grow">Most used stacks per year</div>
            <span className="muted" style={{ fontSize: 12 }}>fewer</span>
            <div className="row" style={{ gap: 2 }}>
              {[20, 45, 70, 100].map((p) => <span key={p} style={{ width: 14, height: 10, borderRadius: 2, background: `color-mix(in oklab, var(--accent) ${p}%, var(--surface-2))` }} />)}
            </div>
            <span className="muted" style={{ fontSize: 12 }}>more</span>
          </div>
          {data.tags.length ? <Heatmap rows={data.tags} years={years} /> : <div className="small muted">No projects yet.</div>}
        </div>
        <div className="card" style={{ overflow: "hidden" }}>
          <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)" }}>
            <div className="strong">Ideas that keep coming back</div>
            <div className="small muted" style={{ marginTop: 2 }}>Pairs of projects whose titles and abstracts mean nearly the same thing.</div>
          </div>
          <table className="table">
            <thead><tr><th>Project</th><th>Similar project</th><th style={{ width: 150 }}>How close</th></tr></thead>
            <tbody>
              {data.pairs.map((p) => (
                <tr key={`${p.first_title}|${p.second_title}`}>
                  <td>{p.first_title} <span className="muted">({p.first_year})</span></td>
                  <td>{p.second_title} <span className="muted">({p.second_year})</span></td>
                  <td><Closeness band={p.band} score={p.similarity} /></td>
                </tr>
              ))}
              {data.pairs.length === 0 && <tr><td colSpan={3} className="muted">No similar pairs found.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="cols-2" style={{ gap: 20 }}>
          <div className="card" style={{ overflow: "hidden" }}>
            <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)" }}>
              <div className="strong">Faculty load in {data.year}</div>
              <div className="small muted" style={{ marginTop: 2 }}>Projects this year, and how many still wait for a decision.</div>
            </div>
            <table className="table">
              <thead><tr><th>Faculty</th><th className="num">Projects</th><th className="num">Waiting</th></tr></thead>
              <tbody>
                {data.load.map((g) => (
                  <tr key={g.faculty}>
                    <td>{g.faculty}</td>
                    <td className="num">{g.projects}</td>
                    <td className="num" style={{ color: g.waiting ? "var(--accent)" : "var(--faint)" }}>{g.waiting}</td>
                  </tr>
                ))}
                {data.load.length === 0 && <tr><td colSpan={3} className="muted">No projects this year yet.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="card" style={{ overflow: "hidden" }}>
            <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)" }}>
              <div className="strong">Most used stack</div>
              <div className="small muted" style={{ marginTop: 2 }}>Projects that used each one, all years.</div>
            </div>
            <div className="stack-sm" style={{ padding: "14px 20px", gap: 9 }}>
              {top.map(([name, count]) => (
                <div key={name} style={{ display: "grid", gridTemplateColumns: "110px minmax(0, 1fr) 28px", gap: 12, alignItems: "center" }}>
                  <span className="soft" style={{ fontSize: 13 }}>{name}</span>
                  <div style={{ height: 14, background: "var(--surface-2)", borderRadius: 2 }}>
                    <div style={{ height: "100%", width: `${(count / topCount) * 100}%`, background: "var(--accent)", borderRadius: 2 }} />
                  </div>
                  <span style={{ fontSize: 13, textAlign: "right" }}>{count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
