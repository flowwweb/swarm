import { createHash } from "node:crypto";

// Server-only: adapters must be the verified project's Admin Auth and Firestore.
export async function verifiedAccountUser(auth, token) {
  if (typeof token !== "string" || !token) throw new Error("FORBIDDEN");
  const denied = new Set(["auth/id-token-expired", "auth/id-token-revoked", "auth/invalid-id-token",
    "auth/argument-error", "auth/user-disabled", "auth/user-not-found"]);
  async function checked(call) {
    try { return await call(); }
    catch (error) { throw new Error(denied.has(error?.code) ? "FORBIDDEN" : "IDENTITY_UNAVAILABLE"); }
  }
  const decoded = await checked(() => auth.verifyIdToken(token, true));
  if (typeof decoded?.uid !== "string" || !decoded.uid || decoded.uid.length > 128) throw new Error("FORBIDDEN");
  const user = await checked(() => auth.getUser(decoded.uid));
  if (!user || user.uid !== decoded.uid || user.disabled || user.emailVerified !== true || typeof user.email !== "string" || !user.email) throw new Error("FORBIDDEN");
  return { uid: decoded.uid, email: user.email, authTime: decoded.auth_time };
}

export function createAccountService({ auth, db }) {

  async function bootstrap(token) {
    const user = await verifiedAccountUser(auth, token);
    const id = createHash("sha256").update(user.uid).digest("hex");
    return db.runTransaction(async (tx) => {
      const ref = db.doc(`swrmAccounts/${id}`);
      const snapshot = await tx.get(ref);
      if (snapshot.exists && snapshot.data()?.subject !== user.uid) throw new Error("FORBIDDEN");
      if (!snapshot.exists) tx.create(ref, { subject: user.uid });
      return { subject: user.uid, email: user.email, created: !snapshot.exists };
    });
  }

  return { bootstrap };
}
