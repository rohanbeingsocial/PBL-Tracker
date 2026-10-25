import { useState, type ReactNode } from "react";
import type { Account, DemoAccount } from "../api";
import type { Page, Path } from "../hooks";
import { applyTheme, savedTheme, type Theme } from "../theme";
import { Icon, type IconName } from "./charts";
import { Segmented } from "./ui";

interface NavItem {
  path: Page;
  label: string;
  icon: IconName;
  group: string;
  count?: number;
}

export function navFor(me: Account, waiting: number): NavItem[] {
  const items: NavItem[] = [
    { path: "/", label: "Dashboard", icon: "home", group: "" },
    { path: "/search", label: "Search projects", icon: "search", group: "" },
  ];
  if (me.role === "student") items.push({ path: "/submit", label: "Submit a project", icon: "upload", group: "" });
  items.push({ path: "/trends", label: "Trends", icon: "chart", group: "" });
  if (me.role === "faculty") items.push({ path: "/links", label: "Submission links", icon: "link", group: "Faculty", count: waiting });
  if (me.is_admin) {
    items.push({ path: "/people", label: "People", icon: "people", group: "Admin" });
    items.push({ path: "/subjects", label: "Subjects", icon: "book", group: "Admin" });
  }
  return items;
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
      <label className="label-sm" htmlFor="demo-switch">Switch account (demo)</label>
      <select id="demo-switch" className="select" style={{ height: 32, fontSize: 13 }}
              value={current?.login ?? ""} onChange={(e) => onSwitch(e.target.value)}>
        {!current && <option value="" disabled>Choose a sample account</option>}
        {ROLE_ORDER.map((role) => (
          <optgroup key={role} label={ROLE_GROUP[role]}>
            {accounts.filter((a) => a.role === role).map((a) => <option key={a.login} value={a.login}>{a.name}</option>)}
          </optgroup>
        ))}
      </select>
      {current && <div className="small muted pretty" style={{ fontSize: 12.5 }}>{current.shows}</div>}
      {error && <div className="error-text">{error}</div>}
    </div>
  );
}

export function ThemeSwitch() {
  const [theme, setTheme] = useState<Theme>(savedTheme);
  const pick = (t: Theme) => {
    setTheme(t);
    applyTheme(t, true);
  };
  return <Segmented options={["light", "dark"] as const} value={theme} onChange={pick} label="Theme"
                    names={{ light: "Light", dark: "Dark" }} />;
}

export function Shell({ me, path, go, waiting, demo, onSwitch, switchError, onSignOut, wide, children }: {
  me: Account; path: string; go: (to: Path) => void; waiting: number; demo: DemoAccount[];
  onSwitch: (login: string) => void; switchError: string | null; onSignOut: () => void; wide?: boolean; children: ReactNode;
}) {
  let lastGroup = "";
  return (
    <div className="app">
      <aside className="side">
        <div className="brand">
          <div className="wordmark">PBL Tracker</div>
        </div>
        <nav className="nav" aria-label="Pages">
          {navFor(me, waiting).map((item) => {
            const heading = item.group && item.group !== lastGroup ? item.group : null;
            lastGroup = item.group;
            const active = path === item.path || (item.path !== "/" && path.startsWith(`${item.path}/`));
            return (
              <div key={item.path} style={{ display: "flex", flexDirection: "column" }}>
                {heading && <div className="nav-group">{heading}</div>}
                <button className={`nav-item${active ? " active" : ""}`}
                        aria-current={active ? "page" : undefined} onClick={() => go(item.path)}>
                  <Icon name={item.icon} size={17} />
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
          <div>
            <div className="me-name">{me.name}</div>
            <div className="me-sub">{me.role === "student" ? "Student" : me.is_admin ? "Faculty, PBL coordinator" : "Faculty"} · {me.login}</div>
          </div>
          <ThemeSwitch />
          <div className="row" style={{ gap: 8 }}>
            <button className="btn" style={{ height: 30, flex: 1, justifyContent: "center" }} onClick={() => go("/account")}>Account</button>
            <button className="btn danger" style={{ height: 30, flex: 1, justifyContent: "center" }} onClick={onSignOut}>Sign out</button>
          </div>
        </div>
      </aside>
      <main className="main">
        <div className={`page${wide ? " wide-page" : ""}`}>{children}</div>
      </main>
    </div>
  );
}
