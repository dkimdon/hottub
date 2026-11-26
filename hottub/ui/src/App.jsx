import { useEffect, useState } from "react";
import { configureApi } from "./api";
import { configureAuth, currentUser, signOut } from "./auth";
import Help from "./Help";
import HistoryPanel from "./HistoryPanel";
import SignIn from "./SignIn";
import TubPanel from "./TubPanel";
import UsersPanel from "./UsersPanel";

// config.json is written at deploy time and says which backend to use, so
// the same build works for both the test and live environments.
async function loadConfig() {
  const response = await fetch("/config.json", { cache: "no-store" });
  if (!response.ok) throw new Error("config.json is missing");
  return response.json();
}

export default function App() {
  // undefined = still starting up, null = signed out
  const [user, setUser] = useState(undefined);
  const [config, setConfig] = useState(null);
  const [startupError, setStartupError] = useState(null);
  const [page, setPage] = useState("tub");
  // The tub panel's latest state, shared with the history graph's forecast.
  const [tub, setTub] = useState(null);

  useEffect(() => {
    let cancelled = false;
    loadConfig()
      .then(async (loaded) => {
        configureAuth(loaded);
        configureApi(loaded, { sessionExpired: () => setUser(null) });
        const signedIn = await currentUser({ forceRefresh: true });
        if (!cancelled) {
          setConfig(loaded);
          setUser(signedIn);
        }
      })
      .catch(() => {
        if (!cancelled) setStartupError("The app could not start. Please try again later.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (startupError) return <main className="card"><p className="error">{startupError}</p></main>;
  if (user === undefined) return <main className="card"><p className="muted">Loading…</p></main>;
  if (user === null) return <SignIn onSignedIn={async () => setUser(await currentUser())} />;

  const current = page === "users" && !user.isAdmin ? "tub" : page;
  const tabs = [["tub", "Tub"], ["help", "Help"], ...(user.isAdmin ? [["users", "Users"]] : [])];
  async function leave() {
    await signOut();
    setUser(null);
    setPage("tub");
  }

  return (
    <>
      <nav className="tabs" aria-label="Sections">
        {tabs.map(([id, label]) => (
          <button key={id} aria-current={current === id ? "page" : undefined} onClick={() => setPage(id)}>
            {label}
          </button>
        ))}
        {config.environment !== "live" && <span className="badge">{config.environment}</span>}
      </nav>

      {current === "tub" && (
        <>
          <main className="card wooden">
            <TubPanel onTub={setTub} />
          </main>
          <section className="card wooden">
            <HistoryPanel tub={tub} />
          </section>
        </>
      )}
      {current === "help" && (
        <main className="card">
          <Help onSignOut={leave} />
        </main>
      )}
      {current === "users" && (
        <main className="card">
          <UsersPanel me={user} onSignOut={leave} />
        </main>
      )}
    </>
  );
}
