import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api, whenSignedOut, type Account, type DemoAccount, type Reference } from "./api";
import { navFor, Shell } from "./components/Shell";
import { Failed, Loading } from "./components/ui";
import { AppContext } from "./context";
import { usePath, type Path } from "./hooks";
import AccountPage from "./pages/Account";
import Check from "./pages/Check";
import Home from "./pages/Home";
import Marks from "./pages/Marks";
import People from "./pages/People";
import Review from "./pages/Review";
import Search from "./pages/Search";
import SignIn from "./pages/SignIn";
import Subjects from "./pages/Subjects";
import Trends from "./pages/Trends";

const PAGES: Record<Path, { crumb: string; title: string; page: () => ReactNode }> = {
  "/": { crumb: "Home", title: "", page: () => <Home /> },
  "/search": { crumb: "Projects", title: "Search projects", page: () => <Search /> },
  "/check": { crumb: "Projects", title: "Check an idea", page: () => <Check /> },
  "/trends": { crumb: "Projects", title: "Trends", page: () => <Trends /> },
  "/review": { crumb: "Faculty", title: "Review proposals", page: () => <Review /> },
  "/marks": { crumb: "Faculty", title: "Enter marks", page: () => <Marks /> },
  "/people": { crumb: "Admin", title: "People", page: () => <People /> },
  "/subjects": { crumb: "Admin", title: "Subjects", page: () => <Subjects /> },
  "/account": { crumb: "Account", title: "Your account", page: () => <AccountPage /> },
};

export default function App() {
  const [path, go] = usePath();
  const [me, setMe] = useState<Account | null | undefined>(undefined);   // undefined = still asking
  const [demo, setDemo] = useState<DemoAccount[]>([]);
  const [ref, setRef] = useState<Reference | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [waiting, setWaiting] = useState(0);
  const [switchError, setSwitchError] = useState<string | null>(null);
  const [toastText, setToastText] = useState<string | null>(null);
  const toastTimer = useRef<number | undefined>(undefined);

  const signedOut = useCallback((message: string | null) => {
    setMe(null);
    setRef(null);
    setNotice(message);
  }, []);

  useEffect(() => {
    whenSignedOut((message) => signedOut(message));
    Promise.all([api<{ account: Account | null }>("/me"), api<{ accounts: DemoAccount[] }>("/demo")])
      .then(([who, demoList]) => {
        setDemo(demoList.accounts);
        setMe(who.account);
      })
      .catch((e: Error) => setStartError(e.message));
  }, [signedOut]);

  const ready = !!me && !me.must_change_password;
  useEffect(() => {
    if (!ready) return;
    api<Reference>("/reference").then(setRef).catch((e: Error) => setStartError(e.message));
  }, [ready, me?.login]);

  const refreshCounts = useCallback(() => {
    if (!me || me.role !== "faculty" || me.must_change_password) return;
    api<{ waiting: unknown[] }>("/review").then((r) => setWaiting(r.waiting.length)).catch(() => {});
  }, [me]);
  useEffect(refreshCounts, [refreshCounts]);

  const toast = useCallback((message: string) => {
    setToastText(message);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToastText(null), 3600);
  }, []);

  async function switchTo(login: string) {
    setSwitchError(null);
    try {
      setMe(await api<Account>("/demo/sign-in", { body: { login } }));
    } catch (e) {
      setSwitchError((e as Error).message);
    }
  }

  async function signOut() {
    await api("/sign-out", { method: "POST" }).catch(() => {});
    signedOut(null);
  }

  if (startError && !me) return <div className="signin"><div className="signin-box"><Failed message={startError} /></div></div>;
  if (me === undefined) return null;
  if (me === null) {
    return <SignIn notice={notice} demo={demo} onSignedIn={(account) => { setNotice(null); setMe(account); }} />;
  }
  if (me.must_change_password) {
    return <AccountPage forced me={me} onChanged={setMe} onSignOut={signOut} />;
  }
  if (!ref) return <div className="page"><Loading /></div>;

  // A page the account doesn't have (after switching accounts, or a typed URL) opens Home.
  const allowed = navFor(me, 0).map((n) => n.path as string).concat("/account");
  const current = (allowed.includes(path) ? path : "/") as Path;
  if (current !== path) window.history.replaceState(null, "", current);
  const info = PAGES[current];
  const crumbPage = current === "/" ? (me.is_admin ? "Overview" : me.name) : info.title;

  return (
    <AppContext.Provider value={{ me, ref, go, toast, refreshCounts }}>
      <Shell me={me} path={current} go={go} waiting={waiting} demo={demo} onSwitch={switchTo}
             switchError={switchError} onSignOut={signOut} crumb={[info.crumb, crumbPage]} year={ref.current_year}>
        {/* The key makes every page start fresh for each account. */}
        <div key={`${me.login}${current}`}>{info.page()}</div>
      </Shell>
      {toastText && <div className="toast" role="status"><b>✓</b>{toastText}</div>}
    </AppContext.Provider>
  );
}

