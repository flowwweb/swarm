import { createProjectApi } from "./project-api.mjs";
import { createProjectService } from "./project-service.mjs";

// Server-owned adapters only; this module does not expose an HTTP route.
export function createSwarmProjectHandler({ app, getAuth, getFirestore }) {
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
  return createProjectApi({ projectService: createProjectService({ auth: getAuth(app), db }) });
}
