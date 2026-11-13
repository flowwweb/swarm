import { createHash, randomBytes } from "node:crypto";
import { verifiedAccountUser } from "./account-service.mjs";

const digest = (value) => createHash("sha256").update(value).digest("hex");
const idPattern = /^[A-Za-z0-9_-]{22,128}$/;

// Server only. Auth and db are trusted Admin instances, never request data.
export function createDeviceService({ auth, db }) {
  async function recentUser(token) {
    const user = await verifiedAccountUser(auth, token);
    const now = Math.floor(Date.now() / 1000);
    if (!Number.isSafeInteger(user.authTime) || user.authTime > now || now - user.authTime > 300) throw new Error("REAUTH_REQUIRED");
    return user;
  }

  async function enroll(token, operationId) {
    if (typeof operationId !== "string" || !idPattern.test(operationId)) throw new Error("INVALID_REQUEST");
    const user = await recentUser(token);
    const accountId = digest(user.uid);
    const deviceId = randomBytes(24).toString("base64url");
    const deviceSecret = randomBytes(32).toString("base64url");
    const receiptId = digest(JSON.stringify([user.uid, operationId]));
    return db.runTransaction(async (tx) => {
      const accountRef = db.doc(`swrmAccounts/${accountId}`);
      const receiptRef = db.doc(`swrmDeviceEnrollments/${receiptId}`);
      const [account, receipt] = await Promise.all([tx.get(accountRef), tx.get(receiptRef)]);
      if (!account.exists || account.data()?.subject !== user.uid) throw new Error("FORBIDDEN");
      if (receipt.exists) {
        const previousId = receipt.data()?.deviceId;
        if (typeof previousId !== "string" || !idPattern.test(previousId)) throw new Error("FORBIDDEN");
        const previous = await tx.get(db.doc(`swrmDeviceAccounts/${accountId}/devices/${previousId}`));
        if (!previous.exists || previous.data()?.subject !== user.uid || previous.data()?.revoked !== false) throw new Error("FORBIDDEN");
        return { deviceId: previousId, status: "DELIVERY_UNCONFIRMED" };
      }
      const deviceRef = db.doc(`swrmDeviceAccounts/${accountId}/devices/${deviceId}`);
      if ((await tx.get(deviceRef)).exists) throw new Error("ID_COLLISION");
      tx.create(deviceRef, { subject: user.uid, secretDigest: digest(deviceSecret), revoked: false });
      tx.create(receiptRef, { deviceId });
      return { deviceId, deviceSecret, status: "ISSUED" };
    });
  }

  async function revoke(token, deviceId) {
    if (typeof deviceId !== "string" || !idPattern.test(deviceId)) throw new Error("INVALID_REQUEST");
    const user = await recentUser(token);
    const accountId = digest(user.uid);
    return db.runTransaction(async (tx) => {
      const accountRef = db.doc(`swrmAccounts/${accountId}`);
      const deviceRef = db.doc(`swrmDeviceAccounts/${accountId}/devices/${deviceId}`);
      const [account, device] = await Promise.all([tx.get(accountRef), tx.get(deviceRef)]);
      if (!account.exists || account.data()?.subject !== user.uid || !device.exists || device.data()?.subject !== user.uid) throw new Error("FORBIDDEN");
      if (device.data().revoked === true) return { deviceId, replay: true };
      tx.set(deviceRef, { ...device.data(), revoked: true });
      return { deviceId, replay: false };
    });
  }

  async function list(token, cursor) {
    if (cursor !== undefined && (typeof cursor !== "string" || !idPattern.test(cursor))) throw new Error("INVALID_REQUEST");
    const user = await recentUser(token);
    const accountId = digest(user.uid);
    return db.runTransaction(async (tx) => {
      const account = await tx.get(db.doc(`swrmAccounts/${accountId}`));
      if (!account.exists || account.data()?.subject !== user.uid) throw new Error("FORBIDDEN");
      let query = db.collection(`swrmDeviceAccounts/${accountId}/devices`).orderBy("__name__");
      if (cursor !== undefined) query = query.startAfter(cursor);
      const snapshot = await tx.get(query.limit(51));
      const page = snapshot.docs.slice(0, 50);
      const devices = page.map((doc) => {
        const device = doc.data();
        if (!idPattern.test(doc.id) || device?.subject !== user.uid || typeof device.revoked !== "boolean") throw new Error("FORBIDDEN");
        return { deviceId: doc.id, revoked: device.revoked };
      });
      return { devices, nextCursor: snapshot.docs.length > 50 ? page[page.length - 1].id : null };
    });
  }
  return { enroll, revoke, list };
}
