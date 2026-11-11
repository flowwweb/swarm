import { createHash, randomUUID, timingSafeEqual } from "node:crypto";
import { applyMutation, changeMembership, readProject } from "./account-protocol.mjs";
import { verifiedAccountUser } from "../server/account-service.mjs";

const opaqueId = /^[A-Za-z0-9_-]{1,128}$/;
const projectIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const digest = (value) => createHash("sha256").update(value).digest("hex");

// Server-only factory: callers must inject the verified project's Firebase Admin
// Auth and Firestore instances, never client-provided adapters or identity data.
export function createProjectService({ auth, db }) {
  async function session(token, deviceId, deviceSecret) {
    if (typeof token !== "string" || !token || !opaqueId.test(deviceId ?? "") ||
        typeof deviceSecret !== "string" || !/^[A-Za-z0-9_-]{43,128}$/.test(deviceSecret)) throw new Error("FORBIDDEN");
    const user = await verifiedAccountUser(auth, token);
    return { uid: user.uid, deviceId, secretDigest: digest(deviceSecret) };
  }

  async function authorize(tx, current, workspaceId) {
    const deviceRef = db.doc(`swrmDeviceAccounts/${digest(current.uid)}/devices/${current.deviceId}`);
    const workspaceRef = db.doc(`swrmWorkspaces/${workspaceId}`);
    const [deviceSnap, workspaceSnap] = await Promise.all([tx.get(deviceRef), tx.get(workspaceRef)]);
    const device = deviceSnap.data();
    const workspace = workspaceSnap.data();
    const stored = device?.secretDigest;
    const goodSecret = typeof stored === "string" && /^[a-f0-9]{64}$/.test(stored) &&
      timingSafeEqual(Buffer.from(stored, "hex"), Buffer.from(current.secretDigest, "hex"));
    const role = workspace?.members && Object.hasOwn(workspace.members, current.uid) ? workspace.members[current.uid] : undefined;
    const billing = workspace?.billing;
    const validRoles = workspace?.members && Object.values(workspace.members).every((item) => ["owner", "editor", "viewer"].includes(item));
    const activeHumans = validRoles ? Object.keys(workspace.members).length : Infinity;
    if (!deviceSnap.exists || device?.subject !== current.uid || device?.revoked !== false || !goodSecret ||
        !workspaceSnap.exists || workspace.id !== workspaceId || !["owner", "editor", "viewer"].includes(role) ||
        !Number.isSafeInteger(workspace.billingRevision) || workspace.billingRevision < 0 ||
        billing?.verified !== true || billing.revision !== workspace.billingRevision || billing.plan !== "team" ||
        billing.status !== "active" || billing.paymentStatus !== "paid" ||
        !Number.isSafeInteger(billing.paidSeats) || billing.paidSeats < activeHumans ||
        !Number.isSafeInteger(billing.validUntil) || Date.now() >= billing.validUntil) throw new Error("FORBIDDEN");
    return { role, workspace, identity: { verified: true, subject: current.uid, device: { id: current.deviceId, subject: current.uid, revoked: false } } };
  }

  function validateWorkspace(workspaceId) {
    if (typeof workspaceId !== "string" || !opaqueId.test(workspaceId)) throw new Error("INVALID_REQUEST");
  }

  async function create(token, deviceId, deviceSecret, workspaceId, operationId) {
    validateWorkspace(workspaceId);
    if (typeof operationId !== "string" || !opaqueId.test(operationId)) throw new Error("INVALID_REQUEST");
    const current = await session(token, deviceId, deviceSecret);
    const id = randomUUID();
    const receiptRef = db.doc(`swrmProjectCreates/${digest(JSON.stringify([current.uid, deviceId, operationId]))}`);
    return db.runTransaction(async (tx) => {
      const access = await authorize(tx, current, workspaceId);
      if (!["owner", "editor"].includes(access.role)) throw new Error("FORBIDDEN");
      const receiptSnap = await tx.get(receiptRef);
      if (receiptSnap.exists) {
        const receipt = receiptSnap.data();
        if (receipt.workspaceId !== workspaceId || !projectIdPattern.test(receipt.projectId)) throw new Error("OPERATION_ID_REUSED");
        const old = await tx.get(db.doc(`swrmSharedProjects/${receipt.projectId}`));
        if (!old.exists || old.data().workspaceId !== workspaceId) throw new Error("FORBIDDEN");
        readProject(old.data(), access.identity);
        return { projectId: receipt.projectId, replay: true };
      }
      const projectRef = db.doc(`swrmSharedProjects/${id}`);
      if ((await tx.get(projectRef)).exists) throw new Error("ID_COLLISION");
      const members = Object.fromEntries([[current.uid, "owner"]]);
      tx.create(projectRef, { id, workspaceId, revision: 0, value: null, deleted: false, members, receipts: [] });
      tx.create(receiptRef, { workspaceId, projectId: id });
      return { projectId: id, replay: false };
    });
  }

  async function transact(token, deviceId, deviceSecret, workspaceId, projectId, operation) {
    validateWorkspace(workspaceId);
    if (typeof projectId !== "string" || !projectIdPattern.test(projectId)) throw new Error("INVALID_REQUEST");
    if (operation && (typeof operation !== "object" ||
        (typeof operation.value === "string" && Buffer.byteLength(operation.value, "utf8") > 32000))) throw new Error("INVALID_REQUEST");
    const current = await session(token, deviceId, deviceSecret);
    return db.runTransaction(async (tx) => {
      const access = await authorize(tx, current, workspaceId);
      const ref = db.doc(`swrmSharedProjects/${projectId}`);
      const snapshot = await tx.get(ref);
      if (!snapshot.exists || snapshot.data().workspaceId !== workspaceId || snapshot.data().id !== projectId) throw new Error("FORBIDDEN");
      const project = snapshot.data();
      if (operation === undefined) return readProject(project, access.identity);
      if (!["owner", "editor"].includes(access.role)) throw new Error("FORBIDDEN");
      const result = applyMutation(project, access.identity, operation);
      // A terminal project admits no new operations. Existing receipts still
      // replay or reject altered IDs through applyMutation before this check.
      if (project.deleted && result.project !== project) return { error: "PROJECT_DELETED", recorded: false };
      if (result.project !== project) {
        // Reserve 100 KB for a tombstone and its receipt; never evict receipts.
        const deletesProject = operation.kind === "delete" && !project.deleted && result.project.deleted;
        const limit = deletesProject ? 700000 : 600000;
        if (Buffer.byteLength(JSON.stringify(result.project), "utf8") > limit) throw new Error("PROJECT_CAPACITY_REACHED");
        tx.set(ref, result.project);
      }
      if (result.conflict) return { conflict: result.conflict, replay: result.replay };
      if (result.error) return { error: result.error, replay: result.replay };
      return { revision: result.receipt.revision, replay: result.replay };
    });
  }

  async function membershipAccess(tx, current, workspaceId, projectId) {
    const access = await authorize(tx, current, workspaceId);
    if (!["owner", "editor"].includes(access.role)) throw new Error("FORBIDDEN");
    const ref = db.doc(`swrmSharedProjects/${projectId}`);
    const snapshot = await tx.get(ref);
    const project = snapshot.data();
    if (!snapshot.exists || project?.id !== projectId || project.workspaceId !== workspaceId ||
        !project.members || !Object.hasOwn(project.members, current.uid) || project.members[current.uid] !== "owner") throw new Error("FORBIDDEN");
    if (project.deleted) throw new Error("PROJECT_DELETED");
    const revision = project.membersRevision ?? 0;
    if (!Number.isSafeInteger(revision) || revision < 0 || revision >= Number.MAX_SAFE_INTEGER) throw new Error("INVALID_MEMBERSHIP_STATE");
    return { access, ref, project, revision };
  }

  async function readMembers(token, deviceId, deviceSecret, workspaceId, projectId) {
    validateWorkspace(workspaceId);
    if (typeof projectId !== "string" || !projectIdPattern.test(projectId)) throw new Error("INVALID_REQUEST");
    const current = await session(token, deviceId, deviceSecret);
    return db.runTransaction(async (tx) => {
      const { project, revision } = await membershipAccess(tx, current, workspaceId, projectId);
      return { members: { ...project.members }, membersRevision: revision };
    });
  }

  async function setMember(token, deviceId, deviceSecret, workspaceId, projectId, subject, role, expectedRevision) {
    validateWorkspace(workspaceId);
    if (typeof projectId !== "string" || !projectIdPattern.test(projectId) ||
        typeof subject !== "string" || !subject || subject.length > 128 ||
        !["owner", "editor", "viewer", null].includes(role) ||
        !Number.isSafeInteger(expectedRevision) || expectedRevision < 0) throw new Error("INVALID_REQUEST");
    const current = await session(token, deviceId, deviceSecret);
    return db.runTransaction(async (tx) => {
      const { access, ref, project, revision } = await membershipAccess(tx, current, workspaceId, projectId);
      if (revision !== expectedRevision) return { conflict: true, membersRevision: revision };
      const updated = changeMembership(project, access.identity, subject, role);
      const targetRole = Object.hasOwn(access.workspace.members, subject) ? access.workspace.members[subject] : undefined;
      if (role !== null && (!targetRole || (role !== "viewer" && targetRole === "viewer"))) throw new Error("FORBIDDEN");
      if ((Object.hasOwn(project.members, subject) ? project.members[subject] : null) === role) return { membersRevision: revision };
      const next = { ...updated, membersRevision: revision + 1 };
      if (Buffer.byteLength(JSON.stringify(next), "utf8") > 600000) throw new Error("PROJECT_CAPACITY_REACHED");
      tx.set(ref, next);
      return { membersRevision: next.membersRevision };
    });
  }

  return { create, setMember, readMembers, read: (token, deviceId, secret, workspaceId, projectId) => transact(token, deviceId, secret, workspaceId, projectId),
    mutate: transact };
}
