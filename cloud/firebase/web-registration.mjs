const projectId = "swarm-sync-20261105-fw";
const appId = "1:765846931749:web:0cc27254c87721b613b2cc";
const authDomain = `${projectId}.firebaseapp.com`;
const keys = ["projectId", "appId", "authDomain", "apiKey"];

// The registration must come from a trusted server-side Firebase metadata read,
// never from the browser or another caller-provided source.
export function matchesSwarmWebRegistration(registration, configured) {
  if (!registration || !configured || registration.projectId !== projectId ||
      registration.appId !== appId || registration.authDomain !== authDomain) return false;
  return keys.every((key) => typeof registration[key] === "string" && registration[key].length > 0 &&
    typeof configured[key] === "string" && configured[key] === registration[key]);
}

// The caller is a trusted server adapter; neither endpoint nor app is client-selected.
export async function resolveSwarmWebRegistration(app, configured, fetcher = fetch) {
  if (app?.options?.projectId !== projectId || typeof app?.options?.credential?.getAccessToken !== "function") throw new Error("UNAVAILABLE");
  if (!configured || !matchesSwarmWebRegistration(configured, configured)) throw new Error("UNAVAILABLE");
  try {
    const token = await app.options.credential.getAccessToken();
    if (!token || typeof token.access_token !== "string" || !token.access_token) throw new Error();
    const response = await fetcher(`https://firebase.googleapis.com/v1beta1/projects/-/webApps/${appId}/config`, {
      headers: { Authorization: `Bearer ${token.access_token}` }, redirect: "error", signal: AbortSignal.timeout(5000),
    });
    if (!response.ok || !response.body) throw new Error();
    const reader = response.body.getReader(), decoder = new TextDecoder("utf-8", { fatal: true });
    let size = 0, body = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 65536) { await reader.cancel(); throw new Error(); }
      body += decoder.decode(value, { stream: true });
    }
    const registration = JSON.parse(body + decoder.decode());
    if (!matchesSwarmWebRegistration(registration, configured)) throw new Error();
    return Object.fromEntries(keys.map((key) => [key, registration[key]]));
  } catch {
    throw new Error("UNAVAILABLE");
  }
}
