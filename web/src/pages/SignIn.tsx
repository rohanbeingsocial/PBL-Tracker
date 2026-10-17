import { useState, type FormEvent } from "react";
import { api, type Account, type DemoAccount } from "../api";
import { Logo } from "../components/Shell";
import { Notice } from "../components/ui";

const refusal = (e: unknown) => (e as Error).message;

export default function SignIn({ notice, demo, onSignedIn }: {
  notice: string | null; demo: DemoAccount[]; onSignedIn: (account: Account) => void;
}) {
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!login.trim() || !password) {
      setError("Enter your PRN or email and your password.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onSignedIn(await api<Account>("/sign-in", { body: { login, password } }));
    } catch (err) {
      setError(refusal(err));
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  async function quick(account: DemoAccount) {
    setBusy(true);
    setError(null);
    try {
      onSignedIn(await api<Account>("/demo/sign-in", { body: { login: account.login } }));
    } catch (err) {
      setError(refusal(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="signin">
      <div className="signin-box">
        <div className="row" style={{ gap: 10 }}>
          <Logo />
          <div className="wordmark">pbl<span>/</span>tracker</div>
        </div>
        <div>
          <h1>Sign in</h1>
          <p className="muted" style={{ margin: "6px 0 0" }}>PBL projects, proposals, reports and marks for the department.</p>
        </div>
        {notice && <Notice tone="info" kind="Signed out">{notice}</Notice>}
        <form className="card pad-lg stack" style={{ gap: 14 }} onSubmit={submit}>
          <label className="field">
            <span>PRN or college email</span>
            <input className="input" value={login} onChange={(e) => setLogin(e.target.value)} maxLength={120}
                   autoComplete="username" placeholder="1032240101 or name@example.edu" autoFocus />
          </label>
          <label className="field">
            <span>Password</span>
            <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                   maxLength={72} autoComplete="current-password" />
          </label>
          {error && <div className="error-text" role="alert">{error}</div>}
          <button className="btn primary full" style={{ height: 38 }} disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
        <div className="small muted">Forgot your password? The PBL coordinator can give you a temporary one.</div>
        {demo.length > 0 && (
          <div className="stack" style={{ gap: 8 }}>
            <div className="label">Sample accounts · demo</div>
            <div className="card demo-list" style={{ overflow: "hidden" }}>
              {demo.map((a) => (
                <button key={a.login} className="demo-item" onClick={() => quick(a)} disabled={busy}>
                  <span className="who">{a.name}</span>
                  <span className="role">{a.role}</span>
                  <span className="what">{a.shows}</span>
                </button>
              ))}
            </div>
            <div className="small muted" style={{ fontSize: 12 }}>
              Signs in with SEED_PASSWORD from .env. Set DEMO_SWITCHER=off before anyone else can open this app.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
