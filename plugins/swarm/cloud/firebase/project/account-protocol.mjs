import { createHash, randomUUID } from "node:crypto";

// This is a transaction decision function, not an authentication or storage boundary.
// A trusted server must verify the subject and read the device and project in the
// same durable transaction before calling it. Do not expose it directly to clients.
export const newProjectId = () => randomUUID();

function authorize(project, identity, minimumRole) {
  const role = Object.hasOwn(project.members, identity.subject) ? project.members[identity.subject] : undefined;
  const ranks = { viewer: 1, editor: 2, owner: 3 };
  if (identity.verified !== true || typeof identity.subject !== "string" || !identity.subject ||
      typeof identity.device?.id !== "string" || !identity.device.id || identity.device.subject !== identity.subject ||
      identity.device?.revoked !== false || !Object.hasOwn(ranks, role) ||
      ranks[role] < ranks[minimumRole]) throw new Error("FORBIDDEN");
}

export function readProject(project, identity) {
  authorize(project, identity, "viewer");
  return { id: project.id, revision: project.revision, value: project.value, deleted: project.deleted,
    ...(!project.deleted && typeof project.ticketValue === "string" ? { ticketValue: project.ticketValue } : {}) };
}

export function applyMutation(project, identity, operation) {
  authorize(project, identity, "editor");
  if (operation.projectId !== project.id || operation.deviceId !== identity.device.id ||
      typeof operation.id !== "string" || !operation.id || operation.id.length > 128 ||
      !Number.isSafeInteger(operation.expectedRevision) || operation.expectedRevision < 0 ||
      !["put", "ticket-put", "delete"].includes(operation.kind) ||
      (["put", "ticket-put"].includes(operation.kind) && typeof operation.value !== "string") ||
      (operation.kind === "delete" && operation.value !== undefined)) throw new Error("INVALID_OPERATION");

  const key = JSON.stringify([identity.subject, identity.device.id, operation.id]);
  const fingerprint = createHash("sha256").update(JSON.stringify([operation.projectId, operation.deviceId, operation.expectedRevision, operation.kind, operation.value ?? null])).digest("hex");
  const previous = project.receipts.find((receipt) => receipt.key === key);
  if (previous) {
    if (previous.fingerprint !== fingerprint) throw new Error("OPERATION_ID_REUSED");
    if (previous.conflict) return { project, conflict: previous.conflict, replay: true };
    if (previous.error) return { project, error: previous.error, replay: true };
    return { project, receipt: previous, replay: true };
  }
  if (operation.expectedRevision !== project.revision) {
    const conflict = { revision: project.revision, value: operation.kind === "ticket-put" ? (project.ticketValue ?? null) : project.value, deleted: project.deleted };
    const receipt = { key, fingerprint, conflict };
    return { project: { ...project, receipts: [...project.receipts, receipt] }, conflict, replay: false };
  }
  if (project.deleted) {
    const receipt = { key, fingerprint, error: "PROJECT_DELETED" };
    return { project: { ...project, receipts: [...project.receipts, receipt] }, error: receipt.error, replay: false };
  }
  const receipt = { key, fingerprint, revision: project.revision + 1 };
  const receipts = operation.kind === "delete"
    ? project.receipts.map((item) => item.conflict
      ? { ...item, conflict: { revision: receipt.revision, value: null, deleted: true } }
      : item)
    : project.receipts;
  return {
    project: { ...project, revision: receipt.revision,
      ...(operation.kind === "ticket-put" ? { ticketValue: operation.value } : { value: operation.kind === "put" ? operation.value : null }),
      ...(operation.kind === "delete" ? { ticketValue: null } : {}),
      deleted: operation.kind === "delete", receipts: [...receipts, receipt] },
    receipt,
    replay: false,
  };
}

export function changeMembership(project, identity, subject, role) {
  authorize(project, identity, "owner");
  if (typeof subject !== "string" || !subject || !["owner", "editor", "viewer", null].includes(role)) {
    throw new Error("INVALID_MEMBERSHIP");
  }
  const members = { ...project.members };
  if (role === null) delete members[subject];
  else Object.defineProperty(members, subject, { value: role, enumerable: true, configurable: true, writable: true });
  if (!Object.values(members).includes("owner")) throw new Error("LAST_OWNER");
  return { ...project, members };
}
