import { useEffect, useState } from "react";
import { configureApi } from "./api";
import { configureAuth, currentUser, signOut } from "./auth";
import Help from "./Help";
import HistoryPanel from "./HistoryPanel";
import SignIn from "./SignIn";
import TopBar from "./TopBar";
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

  if (startupError) return <main className={showHelp || showUsers ? "card" : "card wooden"}><p className="error">{startupError}</p></main>;
  if (user === undefined) return <main className={showHelp || showUsers ? "card" : "card wooden"}><p className="muted">Loading…</p></main>;
  if (user === null) return <SignIn onSignedIn={async () => setUser(await currentUser())} />;

  const showUsers = user.isAdmin && page === "users";
  const showHelp = page === "help";

  return (
    <>
      <TopBar
        environment={config.environment}
        email={user.email}
        helpOpen={showHelp}
        onHelp={() => setPage("help")}
        onSignOut={async () => {
          await signOut();
          setUser(null);
        }}
      />

      {user.isAdmin && (
        <nav className="tabs" aria-label="Sections">
          <button aria-current={page === "tub" ? "page" : undefined} onClick={() => setPage("tub")}>
            Tub
          </button>
          <button aria-current={showUsers ? "page" : undefined} onClick={() => setPage("users")}>
            Users
          </button>
        </nav>
      )}

      <main className={showHelp || showUsers ? "card" : "card wooden"}>
        {showHelp ? (
          <Help onBack={() => setPage("tub")} />
        ) : showUsers ? (
          <UsersPanel me={user} />
        ) : (
          <TubPanel onTub={setTub} />
        )}
      </main>
      {!showUsers && !showHelp && (
        <section className="card wooden">
          <HistoryPanel tub={tub} />
        </section>
      )}
    </>
  );
}
