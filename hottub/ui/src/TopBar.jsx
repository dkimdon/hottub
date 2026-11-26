// The header: a wooden sign with the name, and the signed-in
// person's email, Help and Sign out.

export default function TopBar({ environment, email, helpOpen, onHelp, onSignOut }) {
  return (
    <header className="topbar">
      <h1>
        CoHo Hot Tub
        {environment !== "live" && <span className="badge">{environment}</span>}
      </h1>
      <div className="topbar-user">
        <span className="muted">{email}</span>
        <button className="link" aria-current={helpOpen ? "page" : undefined} onClick={onHelp}>
          Help
        </button>
        <button className="link" onClick={onSignOut}>
          Sign out
        </button>
      </div>
    </header>
  );
}
