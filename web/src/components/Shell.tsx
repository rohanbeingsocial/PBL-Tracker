import type { ReactNode } from "react";
import type { Account, DemoAccount } from "../api";
import { initials } from "../format";
import type { Path } from "../hooks";

interface NavItem {
  path: Path;
  label: string;
  group: string;
  count?: number;
}

export function navFor(me: Account, waiting: number): NavItem[] {
  const items: NavItem[] = [
    { path: "/", label: "Home", group: "" },
    { path: "/search", label: "Search projects", group: "Projects" },
    { path: "/check", label: "Check an idea", group: "Projects" },
    { path: "/trends", label: "Trends", group: "Projects" },
  ];
  if (me.role === "faculty") {
    items.push({ path: "/review", label: "Review proposals", group: "Faculty", count: waiting });
    items.push({ path: "/marks", label: "Enter marks", group: "Faculty" });
  }
  if (me.is_admin) {
    items.push({ path: "/people", label: "People", group: "Admin" });
    items.push({ path: "/subjects", label: "Subjects", group: "Admin" });
  }
  return items;
}

export function Logo() {
  return (
    <svg width="24" height="24" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="var(--accent)" />
      <circle cx="14.5" cy="14.5" r="6.25" fill="none" stroke="var(--accent-fg)" strokeWidth="2.5" />
      <path d="M19.4 19.4 24.5 24.5" stroke="var(--accent-fg)" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

const ROLE_ORDER = ["student", "faculty", "admin"] as const;
const ROLE_GROUP = { student: "Students", faculty: "Faculty", admin: "Admin" };

// Demo only (DEMO_SWITCHER in .env): sign in as another sample account in one step.
function DemoSwitcher({ me, accounts, onSwitch, error }: {
  me: Account; accounts: DemoAccount[]; onSwitch: (login: string) => void; error: string | null;
}) {
  const current = accounts.find((a) => a.login === me.login);
  return (
    <div className="side-block">
      <label className="label-sm" htmlFor="demo-switch">Switch account · demo</label>
      <select id="demo-switch" className="select" style={{ height: 32, fontSize: 13 }}
              value={current?.login ?? ""} onChange={(e) => onSwitch(e.target.value)}>
        {!current && <option value="" disabled>Choose a sample account</option>}
        {ROLE_ORDER.map((role) => (
          <optgroup key={role} label={ROLE_GROUP[role]}>
            {accounts.filter((a) => a.role === role).map((a) => <option key={a.login} value={a.login}>{a.name}</option>)}
          </optgroup>
        ))}
      </select>
      {current && <div className="small muted pretty" style={{ fontSize: 12 }}>{current.shows}</div>}
      {error && <div className="error-text">{error}</div>}
    </div>
  );
}

export function Shell({ me, path, go, waiting, demo, onSwitch, switchError, onSignOut, crumb, year, children }: {
  me: Account; path: string; go: (to: Path) => void; waiting: number; demo: DemoAccount[];
  onSwitch: (login: string) => void; switchError: string | null; onSignOut: () => void;
  crumb: [string, string]; year: string; children: ReactNode;
}) {
  let lastGroup = "";
  return (
    <div className="app">
      <aside className="side">
        <div className="brand">
          <Logo />
          <div className="wordmark">pbl<span>/</span>tracker</div>
        </div>
        <nav className="nav" aria-label="Pages">
          {navFor(me, waiting).map((item, i) => {
            const heading = item.group && item.group !== lastGroup ? item.group : null;
            lastGroup = item.group;
            return (
              <div key={item.path} style={{ display: "flex", flexDirection: "column" }}>
                {heading && <div className="nav-group">{heading}</div>}
                <button className={`nav-item${path === item.path ? " active" : ""}`}
                        aria-current={path === item.path ? "page" : undefined} onClick={() => go(item.path)}>
                  <span className="nav-num">{String(i + 1).padStart(2, "0")}</span>
                  <span>{item.label}</span>
                  {!!item.count && <span className="nav-count">{item.count}</span>}
                </button>
              </div>
            );
          })}
        </nav>
        <div style={{ flex: 1 }} />
        {demo.length > 0 && <DemoSwitcher me={me} accounts={demo} onSwitch={onSwitch} error={switchError} />}
        <div className="side-block">
          <div className="me">
            <div className="avatar">{initials(me.name)}</div>
            <div className="me-text">
              <div className="me-name">{me.name}</div>
              <div className="me-sub">{me.role === "student" ? "Student" : me.is_admin ? "Faculty, admin" : "Faculty"} · {me.login}</div>
            </div>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <button className="btn" style={{ height: 30, flex: 1, justifyContent: "center" }} onClick={() => go("/account")}>Account</button>
            <button className="btn danger" style={{ height: 30, flex: 1, justifyContent: "center" }} onClick={onSignOut}>Sign out</button>
          </div>
        </div>
      </aside>
      <main className="main">
        <div className="top">
          <div className="crumb">{crumb[0]}<i>/</i><b>{crumb[1]}</b></div>
          <div className="year"><span className="dot" />Academic year<b>{year}</b></div>
        </div>
        <div className="page">{children}</div>
      </main>
    </div>
  );
}
