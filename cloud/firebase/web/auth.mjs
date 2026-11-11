const expected = { projectId: "swarm-sync-20261105-fw", appId: "1:765846931749:web:0cc27254c87721b613b2cc", authDomain: "swarm-sync-20261105-fw.firebaseapp.com" };

export function createAuthFlow({ appSdk, authSdk, fetcher, render }) {
  let auth, revision = 0;
  let state;
  const update = (next) => { state = next; render(next, Boolean(auth)); };
  async function start() {
    auth = undefined;
    update("loading");
    try {
      const response = await fetcher("/api/config", { cache: "no-store", redirect: "error" });
      if (!response.ok) throw new Error();
      const config = await response.json();
      if (!config || Object.entries(expected).some(([key, value]) => config[key] !== value) || typeof config.apiKey !== "string" || !config.apiKey) throw new Error();
      const candidate = authSdk.getAuth(appSdk.initializeApp(config));
      await authSdk.setPersistence(candidate, authSdk.browserLocalPersistence);
      let observationFailed = false;
      authSdk.onAuthStateChanged(candidate, async (user) => {
        const current = ++revision;
        if (!user) { update("signed-out"); return; }
        update("loading");
        try {
          const token = await user.getIdToken();
          const result = await fetcher("/api/account", { method: "POST", cache: "no-store", redirect: "error", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: JSON.stringify({ action: "bootstrap" }) });
          if (!result.ok) throw new Error();
          const account = await result.json();
          if (!account || typeof account.subject !== "string" || !account.subject || typeof account.email !== "string" || typeof account.created !== "boolean") throw new Error();
          if (current === revision) update("signed-in");
        } catch { if (current === revision) update("unavailable"); }
      }, () => { observationFailed = true; revision++; auth = undefined; update("unavailable"); });
      if (observationFailed) throw new Error();
      auth = candidate;
      update(state);
    } catch { auth = undefined; revision++; update("unavailable"); }
  }
  async function signIn() {
    if (!auth) { update("unavailable"); return; }
    try { await authSdk.signInWithPopup(auth, new authSdk.GoogleAuthProvider()); }
    catch { update("unavailable"); }
  }
  return { start, signIn };
}

if (typeof document !== "undefined") {
  const status = document.querySelector("[role=status]"), button = document.querySelector("#sign-in");
  const messages = { loading: "Connecting…", "signed-out": "Sign in to continue.", "signed-in": "Signed in.", unavailable: "Sign-in is unavailable. Try again later." };
  const render = (state, ready = false) => { status.textContent = messages[state]; button.disabled = !ready; button.hidden = !ready || (state !== "signed-out" && state !== "unavailable"); };
  try {
    const [appSdk, authSdk] = await Promise.all([import("./vendor/firebase-app.js"), import("./vendor/firebase-auth.js")]);
    const flow = createAuthFlow({ appSdk, authSdk, fetcher: fetch, render });
    button.addEventListener("click", () => void flow.signIn());
    await flow.start();
  } catch { render("unavailable"); }
}
