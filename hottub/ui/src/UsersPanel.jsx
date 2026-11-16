import { useEffect, useState } from "react";
import { createUser, deleteUser, listUsers, resetPassword, setAdmin } from "./api";

const STATUS_LABELS = {
  FORCE_CHANGE_PASSWORD: "Invited — has not signed in yet",
  RESET_REQUIRED: "Password reset sent",
};

export default function UsersPanel({ me }) {
  const [users, setUsers] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [makeAdmin, setMakeAdmin] = useState(false);

  async function load() {
    try {
      setUsers(await listUsers());
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  // Run a change, say what happened, and show the list as it now is.
  async function change(action, done) {
    setBusy(true);
    setError(null);
    setNotice(null);
    let ok = false;
    try {
      await action();
      setNotice(done);
      ok = true;
      await load();
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
    return ok;
  }

  function add(event) {
    event.preventDefault();
    const address = email.trim();
    change(
      () => createUser(address, makeAdmin),
      `${address} has been added and emailed a temporary password, valid for 7 days.`
    ).then((ok) => {
      if (!ok) return;
      setEmail("");
      setMakeAdmin(false);
    });
  }

  function remove(user) {
    if (!window.confirm(`Remove ${user.email}? They will no longer be able to sign in.`)) return;
    change(() => deleteUser(user.username), `${user.email} has been removed.`);
  }

  function reset(user) {
    change(
      () => resetPassword(user.username),
      user.status === "FORCE_CHANGE_PASSWORD"
        ? `${user.email} has been emailed a new temporary password.`
        : `${user.email} has been emailed a code. They should choose "Forgot your password?" on the sign-in page, or simply sign in, and enter it.`
    );
  }

  function toggleAdmin(user) {
    change(
      () => setAdmin(user.username, !user.admin),
      user.admin ? `${user.email} is no longer an admin.` : `${user.email} is now an admin.`
    );
  }

  return (
    <>
      <h2>Users</h2>
      <p className="hint">
        Everyone listed here can control the tub. Admins can also add and remove users.
      </p>

      {error && <p className="error" role="alert">{error}</p>}
      {notice && <p className="notice" role="status">{notice}</p>}

      {users === null ? (
        !error && <p className="muted">Loading…</p>
      ) : (
        <ul className="users">
          {users.map((user) => {
            const isMe = user.username === me.username;
            return (
              <li key={user.username}>
                <div className="user-name">
                  <strong>{user.email}</strong>
                  {isMe && <span className="badge">you</span>}
                  {STATUS_LABELS[user.status] && (
                    <span className="hint">{STATUS_LABELS[user.status]}</span>
                  )}
                </div>
                <div className="user-actions">
                  <label title={isMe ? "You cannot remove your own admin rights" : undefined}>
                    <input
                      type="checkbox"
                      checked={user.admin}
                      disabled={busy || isMe}
                      onChange={() => toggleAdmin(user)}
                    />
                    Admin
                  </label>
                  <button disabled={busy} onClick={() => reset(user)}>
                    Reset password
                  </button>
                  <button className="danger" disabled={busy || isMe} onClick={() => remove(user)}>
                    Remove
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <form className="add-user" onSubmit={add}>
        <h3>Add a user</h3>
        <label>
          Email address
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="inline">
          <input
            type="checkbox"
            checked={makeAdmin}
            onChange={(e) => setMakeAdmin(e.target.checked)}
          />
          Make them an admin
        </label>
        <button className="primary" disabled={busy}>Add user</button>
      </form>
    </>
  );
}
