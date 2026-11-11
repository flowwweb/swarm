import { onRequest } from "firebase-functions/v2/https";
import { getApps, initializeApp } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";
import { getFirestore } from "firebase-admin/firestore";
import { createAccountHttp, createProjectHttp } from "./server/account-http.mjs";
import { createWebConfigHttp } from "./server/web-config-http.mjs";

const adapters = {
  initialize() {
    const projectId = process.env.GCLOUD_PROJECT;
    if (projectId !== "swarm-sync-20261105-fw" || (process.env.GOOGLE_CLOUD_PROJECT && process.env.GOOGLE_CLOUD_PROJECT !== projectId) || process.env.FIREBASE_AUTH_EMULATOR_HOST || process.env.FIRESTORE_EMULATOR_HOST) throw new Error("UNAVAILABLE");
    const app = getApps().find((candidate) => candidate.name === "[DEFAULT]") ?? initializeApp({ projectId });
    return { app, getAuth, getFirestore };
  },
};

export const account = onRequest({ region: "europe-west4", cors: false }, createAccountHttp(adapters));
export const project = onRequest({ region: "europe-west4", cors: false }, createProjectHttp(adapters));
export const webConfig = onRequest({ region: "europe-west4", cors: false }, createWebConfigHttp(adapters));
