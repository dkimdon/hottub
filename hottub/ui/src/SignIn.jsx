import { useState } from "react";
import { chooseNewPassword, finishReset, sendResetCode, signIn } from "./auth";

const PASSWORD_RULES = "At least 8 characters, with an upper-case letter, a lower-case letter and a number.";

// Turn Cognito's errors into something a person can act on.
function explain(error) {
  switch (error?.name) {
    case "NotAuthorizedException":
    case "UserNotFoundException":
      return "That email address and password do not match. If you were sent a temporary password more than 7 days ago, ask an admin to send a new one.";
    case "InvalidPasswordException":
      return `That password is not strong enough. ${PASSWORD_RULES}`;
    case "CodeMismatchException":
      return "That code is not right. Check the most recent email.";
    case "ExpiredCodeException":
      return "That code has expired. Go back and request a new one.";
    case "LimitExceededException":
    case "TooManyRequestsException":
      return "Too many attempts. Wait a few minutes and try again.";
    case "UserAlreadyAuthenticatedException":
      return "You are already signed in. Reload the page.";
    default:
      return error?.message || "Something went wrong. Please try again.";
  }
}

export default function SignIn({ onSignedIn }) {
  // "sign-in" | "new-password" | "forgot" | "reset"
  const [step, setStep] = useState("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  // Run one step of signing in, then move to whatever comes next.
  async function attempt(action) {
    setBusy(true);
    setError(null);
    try {
      const next = await action();
      if (next === "done") {
        await onSignedIn();
      } else {
        setStep(next);
      }
    } catch (e) {
      setError(explain(e));
    } finally {
      setBusy(false);
    }
  }

  const submit = (action) => (event) => {
    event.preventDefault();
    attempt(action);
  };

  const goTo = (next) => {
    setError(null);
    setStep(next);
  };

  const emailField = (
    <label>
      Email address
      <input
        type="email"
        autoComplete="username"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
    </label>
  );

  const newPasswordField = (
    <label>
      New password
      <input
        type="password"
        autoComplete="new-password"
        required
        minLength={8}
        value={newPassword}
        onChange={(e) => setNewPassword(e.target.value)}
      />
      <span className="hint">{PASSWORD_RULES}</span>
    </label>
  );

  return (
    <main className="card signin">
      <h1>CoHo Hot Tub</h1>

      {step === "sign-in" && (
        <form onSubmit={submit(() => signIn(email, password))}>
          {emailField}
          <label>
            Password
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <button className="primary" disabled={busy}>Sign in</button>
          <button type="button" className="link" onClick={() => goTo("forgot")}>
            Forgot your password?
          </button>
        </form>
      )}

      {step === "new-password" && (
        <form onSubmit={submit(() => chooseNewPassword(newPassword))}>
          <p>Welcome. Choose a password of your own to replace the temporary one.</p>
          {newPasswordField}
          <button className="primary" disabled={busy}>Save password and sign in</button>
        </form>
      )}

      {step === "forgot" && (
        <form onSubmit={submit(() => sendResetCode(email))}>
          <p>Enter your email address and we will send you a code to reset your password.</p>
          {emailField}
          <button className="primary" disabled={busy}>Send code</button>
          <button type="button" className="link" onClick={() => goTo("sign-in")}>
            Back to sign in
          </button>
        </form>
      )}

      {step === "reset" && (
        <form onSubmit={submit(() => finishReset(email, code, newPassword))}>
          <p>
            If {email || "that address"} has an account, a code has been emailed to it. Enter the
            code and choose a new password.
          </p>
          <label>
            Code from the email
            <input
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
          </label>
          {newPasswordField}
          <button className="primary" disabled={busy}>Set password and sign in</button>
          <button type="button" className="link" onClick={() => goTo("sign-in")}>
            Back to sign in
          </button>
        </form>
      )}

      {error && <p className="error" role="alert">{error}</p>}
    </main>
  );
}
