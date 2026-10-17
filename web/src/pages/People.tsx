import { useState } from "react";
import { api, type Role } from "../api";
import { Failed, Loading, Metrics, Notice, PageHead, Segmented } from "../components/ui";
import { eyebrow, useApp } from "../context";
import { useLoad } from "../hooks";

interface Person {
  user_id: number;
  name: string;
  login: string;
  email: string;
  role: Role;
  is_admin: boolean;
  is_active: boolean;
  must_change_password: boolean;
  projects: number;
}

const FILTERS = ["All", "Students", "Faculty", "Admins"] as const;

function statusOf(p: Person): string {
  if (!p.is_active) return "Switched off";
  if (p.must_change_password) return "Temporary password";
  return "Active";
}

const STATUS_COLOR: Record<string, string> = { "Switched off": "var(--down)", "Temporary password": "var(--accent)", Active: "var(--muted)" };

function AddPerson({ onAdded }: { onAdded: (who: string, password: string) => void }) {
  const [role, setRole] = useState<Role>("student");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [prn, setPrn] = useState("");
  const [admin, setAdmin] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add() {
    if (role === "student" && !/^[0-9]{10}$/.test(prn.trim())) return setError("A student needs a 10-digit PRN.");
    setError(null);
    try {
      const result = await api<{ temporary: string }>("/people", {
        body: { name, email, prn: role === "student" ? prn.trim() : "", role, is_admin: role === "faculty" && admin },
      });
      onAdded(name, result.temporary);
      setName("");
      setEmail("");
      setPrn("");
      setAdmin(false);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="card pad stack" style={{ gap: 10 }}>
      <div className="strong">Add a person</div>
      <Segmented options={["student", "faculty"] as const} value={role} onChange={setRole} label="Role" />
      <input className="input" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} placeholder="Full name" aria-label="Name" />
      <input className="input" value={email} maxLength={120} onChange={(e) => setEmail(e.target.value)} placeholder="College email" aria-label="Email" />
      {role === "student"
        ? <input className="input mono" value={prn} maxLength={10} onChange={(e) => setPrn(e.target.value)} placeholder="PRN" aria-label="PRN" />
        : <label className="row small" style={{ gap: 8 }}><input type="checkbox" checked={admin} onChange={(e) => setAdmin(e.target.checked)} />PBL coordinator (admin)</label>}
      <button className="btn primary full" disabled={name.trim().length < 2 || !email.trim()} onClick={add}>Add and make a temporary password</button>
      {error && <div className="error-text" role="alert">{error}</div>}
    </div>
  );
}

export default function People() {
  const { me, toast } = useApp();
  const { data, error, loading, reload } = useLoad<{ people: Person[]; me: number }>("/people");
  const [find, setFind] = useState("");
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("All");
  const [picked, setPicked] = useState<number | null>(null);
  const [temporary, setTemporary] = useState<{ who: string; password: string } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const head = <PageHead eyebrow={eyebrow(me)} title="People"
                         sub="Everyone who can sign in. Passwords are never shown or stored in readable form; to help someone who forgot theirs, give them a temporary one." />;
  if (loading && !data) return <>{head}<Loading /></>;
  if (error || !data) return <>{head}<Failed message={error ?? ""} retry={reload} /></>;

  const needle = find.trim().toLowerCase();
  const matches = (p: Person) =>
    filter === "All" || (filter === "Students" && p.role === "student") || (filter === "Faculty" && p.role === "faculty") || (filter === "Admins" && p.is_admin);
  const shown = data.people.filter((p) => matches(p) &&
    (!needle || p.name.toLowerCase().includes(needle) || p.login.toLowerCase().includes(needle) || p.email.includes(needle)));
  const person = data.people.find((p) => p.user_id === picked) ?? null;
  const isMe = person?.user_id === data.me;

  async function act(action: string, done: string) {
    if (!person) return;
    setActionError(null);
    try {
      const result = await api<{ temporary: string | null }>(`/people/${person.user_id}`, { body: { action } });
      if (result.temporary) setTemporary({ who: person.name, password: result.temporary });
      else toast(done);
      reload();
    } catch (e) {
      setActionError((e as Error).message);
    }
  }

  return (
    <>
      {head}
      <Metrics items={[
        { label: "Students", value: data.people.filter((p) => p.role === "student").length },
        { label: "Faculty", value: data.people.filter((p) => p.role === "faculty").length },
        { label: "Admins", value: data.people.filter((p) => p.is_admin).length },
        { label: "Switched off", value: data.people.filter((p) => !p.is_active).length },
      ]} />
      {temporary && (
        <div className="card pad-lg stack" style={{ marginBottom: 24, borderColor: "var(--up)" }}>
          <div className="strong">Temporary password for {temporary.who}</div>
          <code className="secret">{temporary.password}</code>
          <div className="small muted">Copy it now: it is shown only once. It works for one sign-in, after which they have to choose their own password.</div>
          <button className="link" onClick={() => setTemporary(null)}>Done</button>
        </div>
      )}
      <div className="split">
        <div className="wide stack">
          <div className="row wrap" style={{ gap: 10 }}>
            <input className="input grow" style={{ minWidth: 220 }} value={find} onChange={(e) => setFind(e.target.value)} placeholder="Name, PRN or email" aria-label="Find a person" />
            <Segmented options={FILTERS} value={filter} onChange={setFilter} label="Role" />
          </div>
          <div className="meta">{shown.length} people. Pick one to change them.</div>
          <div className="card" style={{ overflow: "hidden" }}>
            <div style={{ maxHeight: 560, overflowY: "auto" }}>
              <table className="table">
                <thead><tr><th>Name</th><th>Signs in with</th><th>Role</th><th className="num">Projects</th><th>Status</th></tr></thead>
                <tbody>
                  {shown.map((p) => (
                    <tr key={p.user_id} className={`click${p.user_id === picked ? " picked" : ""}`} tabIndex={0}
                        onClick={() => { setPicked(p.user_id); setActionError(null); }}
                        onKeyDown={(e) => e.key === "Enter" && setPicked(p.user_id)}>
                      <td className="strong">{p.name}</td>
                      <td className="mono soft" style={{ fontSize: 12 }}>{p.login}</td>
                      <td className="muted">{p.role}{p.is_admin ? ", admin" : ""}</td>
                      <td className="num">{p.projects}</td>
                      <td style={{ color: STATUS_COLOR[statusOf(p)] }}>{statusOf(p)}</td>
                    </tr>
                  ))}
                  {shown.length === 0 && <tr><td colSpan={5} className="muted">Nobody matches.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </div>
        <div className="narrow stack sticky">
          {actionError && <Notice tone="down" kind="Refused">{actionError}</Notice>}
          <div className="card pad stack" style={{ gap: 10 }}>
            {!person ? (
              <>
                <div className="strong">Nobody selected</div>
                <div className="small muted">Pick a row to give a temporary password, switch someone off or on, or make a faculty member an admin.</div>
              </>
            ) : (
              <>
                <div>
                  <div className="strong">{person.name}</div>
                  <div className="meta">{person.role}{person.is_admin ? ", admin" : ""} · {person.login} · {statusOf(person)}</div>
                </div>
                <button className="btn full" onClick={() => act("reset", "")}>Give a temporary password</button>
                <div className="small muted" style={{ fontSize: 12 }}>Their current password stops working at once, and they are signed out wherever they are signed in.</div>
                {person.is_active
                  ? <button className="btn danger full" disabled={isMe} title={isMe ? "You can't switch off your own account." : undefined}
                            onClick={() => act("switch_off", `Switched off ${person.name}`)}>Switch off</button>
                  : <button className="btn good full" onClick={() => act("switch_on", `Switched on ${person.name}`)}>Switch on</button>}
                {person.role === "faculty" && !isMe && (
                  <button className="btn full" onClick={() => act(person.is_admin ? "remove_admin" : "make_admin",
                                                                  person.is_admin ? `${person.name} is no longer an admin` : `${person.name} is now an admin`)}>
                    {person.is_admin ? "Remove admin rights" : "Make admin"}
                  </button>
                )}
              </>
            )}
          </div>
          <AddPerson onAdded={(who, password) => { setTemporary({ who, password }); reload(); }} />
        </div>
      </div>
    </>
  );
}
