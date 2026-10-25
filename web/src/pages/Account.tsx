import { useContext, useState, type FormEvent } from "react";
import { api, type Account } from "../api";
import { PageHead } from "../components/ui";
import { AppContext } from "../context";

function PasswordForm({ forced, onChanged }: { forced: boolean; onChanged: (a: Account) => void }) {
  const [current, setCurrent] = useState("");
  const [fresh, setFresh] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setDone(false);
    if (fresh !== again) return setError("The two new passwords are different.");
    if (fresh.length < 8) return setError("Use at least 8 characters.");
    setBusy(true);
    setError(null);
    try {
      const account = await api<Account>("/password", { body: { current, new: fresh } });
      setCurrent("");
      setFresh("");
      setAgain("");
      setDone(true);
      onChanged(account);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card pad-lg stack" style={{ gap: 14, maxWidth: 520 }} onSubmit={submit}>
      <label className="field"><span>{forced ? "Temporary password" : "Current password"}</span>
        <input className="input" type="password" maxLength={72} autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
      </label>
      <label className="field"><span>New password</span>
        <input className="input" type="password" maxLength={72} autoComplete="new-password" value={fresh} onChange={(e) => setFresh(e.target.value)} />
        <small>At least 8 characters. A short sentence is easier to remember than a jumble.</small>
      </label>
      <label className="field"><span>New password again</span>
        <input className="input" type="password" maxLength={72} autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} />
      </label>
      {error && <div className="error-text" role="alert">{error}</div>}
      {done && <div className="small" style={{ color: "var(--up)" }} role="status">Password changed. Any other signed-in tabs or computers are now signed out.</div>}
      <div><button className="btn primary" disabled={busy}>{busy ? "Saving…" : "Save new password"}</button></div>
    </form>
  );
}

// Used two ways: as a normal page, and on its own (forced) right after signing in
// with a temporary password, before anything else opens.
export default function AccountPage(props: { forced?: boolean; me?: Account; onChanged?: (a: Account) => void; onSignOut?: () => void }) {
  const app = useContext(AppContext);
  if (props.forced && props.me) {
    return (
      <div className="signin">
        <div className="signin-box" style={{ maxWidth: 520 }}>
          <div className="wordmark">PBL Tracker</div>
          <div>
            <h1>Choose a new password</h1>
            <p className="muted" style={{ margin: "6px 0 0" }}>You signed in as {props.me.name} with a temporary password. Choose your own to continue.</p>
          </div>
          <PasswordForm forced onChanged={props.onChanged ?? (() => {})} />
          <button className="link" onClick={props.onSignOut}>Sign out</button>
        </div>
      </div>
    );
  }
  const me = app!.me;
  return (
    <>
      <PageHead title="Your account" />
      <div className="card pad stack-sm" style={{ maxWidth: 520, marginBottom: 24 }}>
        <div className="strong">{me.name}</div>
        <div className="meta">{me.role === "student" ? "Student" : me.is_admin ? "Faculty, PBL coordinator" : "Faculty"} · {me.login}</div>
      </div>
      <div className="label" style={{ marginBottom: 12 }}>Change password</div>
      <PasswordForm forced={false} onChanged={() => {}} />
    </>
  );
}
