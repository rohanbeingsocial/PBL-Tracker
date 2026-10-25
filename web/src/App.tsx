import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api, whenSignedOut, type Account, type DemoAccount, type Reference } from "./api";
import { navFor, Shell } from "./components/Shell";
import { Failed, Loading } from "./components/ui";
import { AppContext } from "./context";
import { usePath, type Page } from "./hooks";
import AccountPage from "./pages/Account";
import Home from "./pages/Home";
import LinkPage from "./pages/LinkPage";
import Links from "./pages/Links";
import OpenLink from "./pages/OpenLink";
import People from "./pages/People";
import ProjectPage from "./pages/Project";
import Search from "./pages/Search";
import SignIn from "./pages/SignIn";
import Subjects from "./pages/Subjects";
import Submit from "./pages/Submit";
import Trends from "./pages/Trends";

const PAGES: Record<Page, () => ReactNode> = {
  "/": () => <Home />,
  "/search": () => <Search />,
  "/submit": () => <Submit />,
  "/trends": () => <Trends />,
  "/links": () => <Links />,
  "/people": () => <People />,
  "/subjects": () => <Subjects />,
  "/account": () => <AccountPage />,
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
    // A submission link opened before signing in: the same page opens right after.
    const forLink = path.startsWith("/s/") ? "Sign in with your college account to open the submission link." : null;
    return <SignIn notice={notice ?? forLink} demo={demo} onSignedIn={(account) => { setNotice(null); setMe(account); }} />;
  }
  if (me.must_change_password) {
    return <AccountPage forced me={me} onChanged={setMe} onSignOut={signOut} />;
  }
  if (!ref) return <div className="page"><Loading /></div>;

  // A project's own page, a submission link (a faculty member's own, or one sent to a
  // class), or one of the pages this account has. Anything else (after switching
  // accounts, or a typed URL) opens Home.
  const projectId = /^\/projects\/(\d+)$/.exec(path)?.[1];
  const linkId = me.role === "faculty" ? /^\/links\/(\d+)$/.exec(path)?.[1] : undefined;
  const code = /^\/s\/([a-z0-9]{6,16})$/.exec(path)?.[1];
  const allowed: string[] = navFor(me, 0).map((n) => n.path).concat("/account");
  const current = projectId || linkId || code ? path : allowed.includes(path) ? path : "/";
  if (current !== path) window.history.replaceState(null, "", current);
  const page = projectId ? <ProjectPage id={Number(projectId)} />
    : linkId ? <LinkPage id={Number(linkId)} />
    : code ? <OpenLink code={code} />
    : PAGES[current as Page]();

  return (
    <AppContext.Provider value={{ me, ref, go, toast, refreshCounts }}>
      <Shell me={me} path={current} go={go} waiting={waiting} demo={demo} onSwitch={switchTo}
             switchError={switchError} onSignOut={signOut} wide={!!projectId}>
        {/* The key makes every page start fresh for each account. */}
        <div key={`${me.login}${current}`}>{page}</div>
      </Shell>
      {toastText && <div className="toast" role="status">{toastText}</div>}
    </AppContext.Provider>
  );
}
