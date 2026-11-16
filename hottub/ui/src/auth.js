// Sign-in with AWS Cognito.  This is the only file that talks to Amplify.

import { Amplify } from "aws-amplify";
import {
  confirmResetPassword,
  confirmSignIn,
  fetchAuthSession,
  resetPassword,
  signIn as amplifySignIn,
  signOut as amplifySignOut,
} from "aws-amplify/auth";

export function configureAuth(config) {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: config.userPoolId,
        userPoolClientId: config.userPoolClientId,
      },
    },
  });
}

// Returns { email, isAdmin, username } for the signed-in user, or null.
// Refreshing on page load picks up admin rights granted since the last visit.
export async function currentUser({ forceRefresh = false } = {}) {
  try {
    const { tokens } = await fetchAuthSession({ forceRefresh });
    if (!tokens?.idToken) return null;
    const claims = tokens.idToken.payload;
    return {
      username: claims["cognito:username"],
      email: claims.email,
      isAdmin: (claims["cognito:groups"] || []).includes("admin"),
    };
  } catch {
    return null;
  }
}

// The token to send to the API; null if the session has ended.
export async function idToken() {
  try {
    const { tokens } = await fetchAuthSession();
    return tokens?.idToken?.toString() ?? null;
  } catch {
    return null;
  }
}

// Each of the functions below resolves to the next step of signing in:
//   "done"          signed in
//   "new-password"  first sign-in with a temporary password: choose your own
//   "reset"         a reset code has been emailed: enter it with a new password

export async function signIn(email, password) {
  const { nextStep } = await amplifySignIn({ username: email.trim(), password });
  switch (nextStep.signInStep) {
    case "DONE":
      return "done";
    case "CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED":
      return "new-password";
    case "RESET_PASSWORD":
      // An admin reset this password; Cognito has already emailed a code.
      return "reset";
    default:
      throw new Error(`Unsupported sign-in step: ${nextStep.signInStep}`);
  }
}

export async function chooseNewPassword(newPassword) {
  const { nextStep } = await confirmSignIn({ challengeResponse: newPassword });
  if (nextStep.signInStep !== "DONE") {
    throw new Error(`Unsupported sign-in step: ${nextStep.signInStep}`);
  }
  return "done";
}

export async function sendResetCode(email) {
  await resetPassword({ username: email.trim() });
  return "reset";
}

export async function finishReset(email, code, newPassword) {
  await confirmResetPassword({
    username: email.trim(),
    confirmationCode: code.trim(),
    newPassword,
  });
  return signIn(email, newPassword);
}

export async function signOut() {
  await amplifySignOut();
}
