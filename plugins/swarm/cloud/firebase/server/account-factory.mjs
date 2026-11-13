import { createAccountApi } from "./account-api.mjs";
import { createAccountService } from "./account-service.mjs";
import { createDeviceService } from "./device-service.mjs";

// Only a server-owned Firebase Admin app and SDK functions may be supplied.
// Nothing in this module registers or exposes an HTTP route.
export function createSwarmAccountHandler({ app, getAuth, getFirestore }) {
  if (process.env.SWARM_SHARED_SYNC_ENABLED !== "true" ||
      app?.options?.projectId !== "swarm-sync-20261105-fw" ||
      process.env.FIREBASE_AUTH_EMULATOR_HOST || process.env.FIRESTORE_EMULATOR_HOST ||
      typeof getAuth !== "function" || typeof getFirestore !== "function") {
    throw new Error("SWARM_FIREBASE_PROJECT_UNVERIFIED");
  }
  let db;
  try {
    db = getFirestore(app);
    if (db?.projectId !== "swarm-sync-20261105-fw") throw new Error();
  } catch {
    throw new Error("SWARM_FIREBASE_PROJECT_UNVERIFIED");
  }
  const auth = getAuth(app);
  return createAccountApi({ accountService: createAccountService({ auth, db }), deviceService: createDeviceService({ auth, db }) });
}
