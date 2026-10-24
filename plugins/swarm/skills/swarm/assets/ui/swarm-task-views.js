// SWARM task views: Task Inspector and Milestone Groups renderers.
//
// Renders the existing explicit-refresh canonical snapshot only. No network,
// storage, polling, model/provider calls, or writes. Project text reaches the
// DOM through textContent / setAttribute only. No progress graphics: the
// snapshot carries no measured progress, and undeclared value keys are ignored.
//
// records.tasks === null means task records are not declared in the source
// (UNKNOWN). It is never rendered as an observed empty collection.
//
// source_record_digest covers the full original source record, while value is
// an allowlisted display projection. The digest is treated as an opaque
// identity: it is never recomputed here. Contradictions are detected against
// the retained normalized model when the same identity is reused.

export const TASK_VIEW_LIMITS = Object.freeze({
  maxMilestones: 128,
  maxTasks: 512,
  pageSize: 40,
  narrowQuery: "(max-width: 720px)",
});

const { maxMilestones: MAX_MILESTONES, maxTasks: MAX_TASKS, pageSize: PAGE_SIZE } = TASK_VIEW_LIMITS;
const LAYOUTS = new Set(["inspector", "milestones"]);
const SHA256_HEX = /^[0-9a-f]{64}$/;
const DIGEST = /^(?:sha256:)?[0-9a-f]{64}$/;
const POINTER = /^\/(milestones|tasks)\/(0|[1-9][0-9]*)$/;
const TEXT_FIELDS = ["title", "state", "planning_status", "execution_status"];
const FOCUSABLE =
  'button:not([disabled]), summary, [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
const ROVING = "\u0000roving";
const SHEET_CLOSE = "\u0000sheet-close";
let mountSeq = 0;

class SnapshotError extends Error {}
const fail = (message) => {
  throw new SnapshotError(message);
};
const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const isText = (v) => typeof v === "string" && v.length > 0;
const isAbsent = (v) => v === undefined || v === null;
const fk = (...parts) => JSON.stringify(parts);

// ---------------------------------------------------------------- validation

function readIdList(value, key, where) {
  if (isAbsent(value[key])) return null;
  const list = value[key];
  if (!Array.isArray(list) || !list.every(isText)) fail(`${where}.${key} must be an array of non-empty strings`);
  if (new Set(list).size !== list.length) fail(`${where}.${key} repeats an id`);
  return Object.freeze(list.slice());
}

// Pointers are exactly /<collection>/<original array index>. An exact index
// match also excludes duplicates within a collection.
function checkPointer(pointer, kind, index, where) {
  if (typeof pointer !== "string") fail(`${where}.source_pointer must be a string`);
  const match = POINTER.exec(pointer);
  if (!match) fail(`${where}.source_pointer is not a canonical /${kind}/<index> pointer`);
  if (match[1] !== kind) fail(`${where}.source_pointer names the ${match[1]} collection`);
  if (Number(match[2]) !== index) fail(`${where}.source_pointer names index ${match[2]} (duplicate or wrong index)`);
}

function readRecord(raw, kind, index) {
  const where = `records.${kind}[${index}]`;
  if (!isObject(raw)) fail(`${where} must be an object`);
  checkPointer(raw.source_pointer, kind, index, where);
  if (typeof raw.source_record_digest !== "string" || !DIGEST.test(raw.source_record_digest)) {
    fail(`${where}.source_record_digest must be a sha256 digest`);
  }
  const v = raw.value;
  if (!isObject(v)) fail(`${where}.value must be an object`);
  if (!isText(v.id)) fail(`${where}.value.id must be a non-empty string`);

  const rec = { kind, index, id: v.id, pointer: raw.source_pointer, digest: raw.source_record_digest };
  for (const key of TEXT_FIELDS) {
    if (isAbsent(v[key])) rec[key] = null;
    else if (typeof v[key] === "string") rec[key] = v[key];
    else fail(`${where}.value.${key} must be a string`);
  }
  if (isAbsent(v.milestone_id)) rec.milestone_id = null;
  else if (isText(v.milestone_id)) rec.milestone_id = v.milestone_id;
  else fail(`${where}.value.milestone_id must be a non-empty string`);
  if (isAbsent(v.roadmap_order)) rec.roadmap_order = null;
  else if (Number.isFinite(v.roadmap_order)) rec.roadmap_order = v.roadmap_order;
  else fail(`${where}.value.roadmap_order must be a finite number`);
  rec.task_ids = readIdList(v, "task_ids", where);
  rec.dependency_ids = readIdList(v, "dependency_ids", where);
  rec.signature = JSON.stringify([
    rec.id,
    rec.title,
    rec.state,
    rec.planning_status,
    rec.execution_status,
    rec.milestone_id,
    rec.roadmap_order,
    rec.task_ids,
    rec.dependency_ids,
  ]);
  return Object.freeze(rec);
}

function indexById(list, kind) {
  const map = new Map();
  for (const rec of list) {
    if (map.has(rec.id)) fail(`duplicate ${kind} id at records.${kind}s[${rec.index}]`);
    map.set(rec.id, rec);
  }
  return map;
}

function byRoadmap(a, b) {
  if (a.roadmap_order !== b.roadmap_order) {
    if (a.roadmap_order === null) return 1;
    if (b.roadmap_order === null) return -1;
    return a.roadmap_order - b.roadmap_order;
  }
  return a.index - b.index;
}

function normalizeSnapshot(snapshot) {
  if (!isObject(snapshot)) fail("snapshot must be an object");
  if (!isText(snapshot.project_id)) fail("project_id must be a non-empty string");
  const version = snapshot.source_version;
  if (!isText(version) && !(Number.isSafeInteger(version) && version >= 0)) {
    fail("source_version must be a non-empty string or non-negative integer");
  }
  if (typeof snapshot.source_file_sha256 !== "string" || !SHA256_HEX.test(snapshot.source_file_sha256)) {
    fail("source_file_sha256 must be 64 lowercase hex characters");
  }
  for (const key of ["canonical_digest", "binding_digest"]) {
    if (typeof snapshot[key] !== "string" || !DIGEST.test(snapshot[key])) fail(`${key} must be a sha256 digest`);
  }
  if (!("cursor" in snapshot)) fail("cursor must be present (null for a source snapshot)");
  const cursor = snapshot.cursor;
  if (cursor !== null && !isText(cursor) && !(Number.isSafeInteger(cursor) && cursor >= 0)) {
    fail("cursor must be null, a non-empty string, or a non-negative integer");
  }
  const records = snapshot.records;
  if (!isObject(records)) fail("records must be an object");
  if (!Array.isArray(records.milestones)) fail("records.milestones must be an array");
  const tasksKnown = records.tasks !== null;
  if (tasksKnown && !Array.isArray(records.tasks)) fail("records.tasks must be an array, or null when undeclared");
  if (records.milestones.length > MAX_MILESTONES) fail(`more than ${MAX_MILESTONES} milestones exceeds this view's bound`);
  if (tasksKnown && records.tasks.length > MAX_TASKS) fail(`more than ${MAX_TASKS} tasks exceeds this view's bound`);

  const rawMilestones = records.milestones.map((r, i) => readRecord(r, "milestones", i));
  const rawTasks = tasksKnown ? records.tasks.map((r, i) => readRecord(r, "tasks", i)) : [];
  const milestones = [...rawMilestones].sort(byRoadmap);
  const tasks = [...rawTasks].sort(byRoadmap);
  const milestoneById = indexById(milestones, "milestone");
  const taskById = indexById(tasks, "task");

  const byDigest = new Map();
  for (const rec of [...rawMilestones, ...rawTasks]) {
    const key = `${rec.kind}\u0000${rec.digest}`;
    const other = byDigest.get(key);
    if (other && other.signature !== rec.signature) {
      fail(`${rec.pointer} and ${other.pointer} share source_record_digest with different values`);
    }
    byDigest.set(key, rec);
  }
  const listedIn = new Map();
  for (const ms of milestones) {
    for (const id of ms.task_ids ?? []) {
      if (!listedIn.has(id)) listedIn.set(id, []);
      listedIn.get(id).push(ms.id);
    }
  }
  return Object.freeze({
    projectId: snapshot.project_id,
    sourceVersion: version,
    sourceFileSha256: snapshot.source_file_sha256,
    canonicalDigest: snapshot.canonical_digest,
    bindingDigest: snapshot.binding_digest,
    cursor,
    tasksKnown,
    milestones,
    tasks,
    milestoneById,
    taskById,
    taskOrder: new Map(tasks.map((t, i) => [t.id, i])),
    listedIn,
    byDigest,
    // Semantic identity only. Excludes source_file_sha256, so a byte-only
    // source edit with an unchanged canonical digest is accepted.
    semantic: JSON.stringify([
      tasksKnown,
      rawMilestones.map((r) => [r.pointer, r.digest, r.signature]),
      rawTasks.map((r) => [r.pointer, r.digest, r.signature]),
    ]),
  });
}

// Compares the next model with the retained last valid model. Nothing else is
// stored.
function contradiction(prev, next) {
  if (!prev) return null;
  if (
    (prev.canonicalDigest === next.canonicalDigest || prev.sourceFileSha256 === next.sourceFileSha256) &&
    (prev.projectId !== next.projectId || prev.sourceVersion !== next.sourceVersion || prev.semantic !== next.semantic)
  ) {
    return "source identity is unchanged but project_id, source_version, or record projection differs";
  }
  if (prev.bindingDigest === next.bindingDigest && prev.projectId !== next.projectId) {
    return "binding_digest is unchanged but project_id differs";
  }
  if (prev.projectId !== next.projectId) return null;
  for (const [key, rec] of next.byDigest) {
    const old = prev.byDigest.get(key);
    if (old && old.signature !== rec.signature) {
      return `${rec.pointer} reuses the source_record_digest of retained ${old.pointer} with different values`;
    }
  }
  return null;
}

// Declared membership only: milestone.task_ids order first, then tasks whose
// milestone_id names the milestone. With known tasks, everything else goes to
// "unbound". With undeclared tasks, only task_ids membership exists.
function buildGroups(m) {
  const membership = new Map();
  const groups = m.milestones.map((ms) => {
    const ids = [...(ms.task_ids ?? [])];
    const seen = new Set(ids);
    for (const t of m.tasks) if (t.milestone_id === ms.id && !seen.has(t.id)) ids.push(t.id);
    const key = fk("milestone", ms.id);
    for (const id of ids) {
      if (!membership.has(id)) membership.set(id, new Set());
      membership.get(id).add(key);
    }
    return { key, milestone: ms, ids };
  });
  if (m.tasksKnown) {
    const unbound = m.tasks.filter((t) => !membership.has(t.id)).map((t) => t.id);
    if (unbound.length) groups.push({ key: fk("unbound"), milestone: null, ids: unbound });
  }
  for (const g of groups) {
    g.rows = g.ids.map((id) => ({
      key: fk(g.key, id),
      id,
      task: m.taskById.get(id) ?? null,
      conflict: (membership.get(id)?.size ?? 0) > 1,
    }));
  }
  return groups;
}

// ----------------------------------------------------------------------- DOM

function h(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "data") {
      for (const [dk, dv] of Object.entries(value)) if (dv !== null && dv !== undefined) node.dataset[dk] = String(dv);
    } else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of [children].flat(Infinity)) if (child !== null && child !== undefined && child !== false) node.append(child);
  return node;
}

function field(name, label, value) {
  const missing = value === null || value === undefined || value === "";
  return h("div", { class: missing ? "stv-field is-unavailable" : "stv-field", data: { field: name } }, [
    h("dt", { text: label }),
    missing ? h("dd", { text: "Not declared" }) : h("dd", {}, [value]),
  ]);
}

function chevron() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "stv-chevron");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(svg.namespaceURI, "path");
  path.setAttribute("d", "m9 6 6 6-6 6");
  svg.append(path);
  return svg;
}

// State only, never a measured fraction. Missing source state stays unknown.
function stateMark(state) {
  return h("span", { class: "stv-state-mark", "aria-hidden": "true", data: { state: state || "unknown" } });
}

function stateLabel(state) {
  const label = state ? state.replace(/_+/g, " ").trim() || state : "Unknown";
  return h("span", { class: "stv-state", text: label[0].toUpperCase() + label.slice(1), data: { state: state || "unknown" } });
}

function secondaryReference(text, key, tag = "div", className = "stv-record-context") {
  if (text.length <= 160) return h(tag, { class: className, text });
  return h(tag, { class: `${className} stv-secondary` }, [
    h("span", { class: "stv-secondary-preview", text }),
    h("details", { data: { stvReference: key } }, [
      h("summary", { data: { stvFocus: key } }, [h("span", { class: "stv-secondary-more", text: "Show more" }), h("span", { class: "stv-secondary-less", text: "Show less" })]),
      h("p", { class: "stv-secondary-full", text }),
    ]),
  ]);
}

function milestoneLabel(m, id) {
  const ms = m.milestoneById.get(id);
  return ms ? `${ms.title || "Untitled milestone"} (${id})` : `${id} (no milestone record in this snapshot)`;
}

function dependencyRecords(m, record) {
  return record.kind === "milestones" ? m.milestoneById : m.taskById;
}

function dependencyLabel(m, record, id, technical = false) {
  const target = dependencyRecords(m, record).get(id);
  const kind = record.kind === "milestones" ? "milestone" : "task";
  if (!target) return technical ? `${id} (no ${kind} record in this snapshot)` : `Referenced ${kind} not available`;
  const title = target.title || `Untitled ${kind}`;
  return technical ? `${title} (${id})` : title;
}

function taskDetail(m, t, headingId) {
  const listedBy = m.listedIn.get(t.id) ?? [];
  const deps = t.dependency_ids;
  const referenceKey = (field, target) => fk("reference", m.projectId, m.bindingDigest, t.kind, t.id, t.digest, field, target?.id, target?.digest);
  return h("div", { class: "stv-task-detail", data: { taskId: t.id, state: t.state } }, [
    h("p", { class: "stv-record-kind", text: t.kind === "milestones" ? "Milestone" : "Task" }),
    headingId ? h("h2", { class: "stv-detail-title", id: headingId, text: t.title || "Untitled task" }) : null,
    stateLabel(t.state),
    t.milestone_id && m.milestoneById.has(t.milestone_id)
      ? secondaryReference(m.milestoneById.get(t.milestone_id).title || "Untitled milestone", referenceKey("milestone", m.milestoneById.get(t.milestone_id))) : null,
    h("p", { class: "stv-record-context", text: "Owner, review evidence and estimates are not declared in this snapshot." }),
    deps?.length ? h("section", { class: "stv-dependencies" }, [
      h("h3", { text: "Depends on" }),
      h("ul", {}, deps.map(id => secondaryReference(dependencyLabel(m, t, id), referenceKey("dependency", dependencyRecords(m, t).get(id)), "li", ""))),
    ]) : null,
    h("details", { class: "stv-technical" }, [
      h("summary", { text: "Source details" }),
      h("dl", { class: "stv-fields" }, [
      field("id", t.kind === "milestones" ? "Milestone ID" : "Task ID", t.id),
      field("title", "Full title", t.title),
      field("state", "State", t.state),
      field("planning-status", "Planning status", t.planning_status),
      field("execution-status", "Execution status", t.execution_status),
      field("milestone", "Declared milestone", t.milestone_id && milestoneLabel(m, t.milestone_id)),
      field("listed-by", "Listed by milestone", listedBy.length ? listedBy.map((id) => milestoneLabel(m, id)).join("; ") : null),
      field(
        "dependencies",
        "Dependencies",
        deps &&
          (deps.length
            ? h(
                "ul",
                { class: "stv-dependency-list" },
                deps.map((id) =>
                  h("li", { data: { recordId: id, record: dependencyRecords(m, t).has(id) ? "present" : "missing" }, text: dependencyLabel(m, t, id, true) }),
                ),
              )
            : "None declared"),
      ),
      field("roadmap-order", "Roadmap order", t.roadmap_order === null ? null : String(t.roadmap_order)),
      field("source-pointer", "Source pointer", t.pointer),
      field("record-digest", "Source record digest", t.digest),
      ]),
    ]),
  ]);
}

function pager(scope, page, total, label) {
  const pageCount = Math.ceil(total / PAGE_SIZE);
  if (pageCount <= 1) return null;
  const first = page * PAGE_SIZE + 1;
  const last = Math.min(total, first + PAGE_SIZE - 1);
  const button = (text, target) =>
    h("button", {
      type: "button",
      class: "stv-page-button",
      disabled: target < 0 || target >= pageCount,
      text,
      data: { stvAction: "page", stvScope: scope, stvPage: target },
    });
  return h("nav", { class: "stv-pager", "aria-label": label }, [
    button("Previous", page - 1),
    h("span", { class: "stv-page-range", text: `${first}–${last} of ${total}` }),
    button("Next", page + 1),
  ]);
}

// --------------------------------------------------------------------- mount

export function mountTaskViews(container, { snapshot, layout } = {}) {
  if (!container || container.nodeType !== 1) throw new TypeError("mountTaskViews needs a container element");
  if (!LAYOUTS.has(layout)) throw new TypeError('layout must be "inspector" or "milestones"');

  const prefix = `stv${++mountSeq}`;
  const controller = new AbortController();
  const { signal } = controller;
  const mql = typeof window !== "undefined" && window.matchMedia ? window.matchMedia(TASK_VIEW_LIMITS.narrowQuery) : null;
  let destroyed = false;

  const st = {
    model: null,
    groups: null,
    status: "error",
    reason: "",
    selectedTaskId: null,
    page: 0,
    narrow: Boolean(mql?.matches),
    sheetOpen: false,
    sheetReturn: null,
    sheetEl: null,
    pendingFocus: null,
    expandedGroups: new Set(),
    groupPages: new Map(),
    openRecord: null,
    inspectorReturn: null,
    filter: "",
  };

  const provenanceEl = h("p", { class: "stv-provenance" });
  const noticeEl = h("p", { class: "stv-notice", role: "status", "aria-live": "polite" });
  const viewHost = h("div", { class: "stv-view", tabindex: "-1" });
  const filterInput = h("input", { type: "search", class: "stv-filter", placeholder: "Filter by title", "aria-label": "Filter by title" });
  const root = h("div", { class: `stv stv--${layout}`, data: { stvLayout: layout } }, [
    h("header", { class: "stv-toolbar" }, [
      h("div", {}, [h("nav", { class: "stv-breadcrumb", "aria-label": "Section", text: "SWARM / Tasks" }),
        h("h1", { text: layout === "inspector" ? "Tasks" : "Milestones" })]),
      filterInput,
    ]),
    h("header", { class: "stv-status" }, [
      h("details", { class: "stv-source" }, [h("summary", { text: "Snapshot details" }), provenanceEl]), noticeEl,
    ]),
    viewHost,
  ]);
  container.append(root);

  // ------------------------------------------------------------- state

  function apply(next) {
    let model;
    try {
      model = normalizeSnapshot(next);
      const reason = contradiction(st.model, model);
      if (reason) fail(reason);
    } catch (err) {
      st.status = st.model ? "stale" : "error";
      st.reason = err instanceof SnapshotError ? err.message : "snapshot could not be read";
      render();
      return { ok: false, state: st.status, reason: st.reason };
    }
    const sameBinding =
      st.model !== null && st.model.projectId === model.projectId && st.model.bindingDigest === model.bindingDigest;
    if (!sameBinding) {
      if (st.sheetOpen && root.contains(document.activeElement)) st.pendingFocus = ROVING;
      st.selectedTaskId = null;
      st.page = 0;
      st.sheetOpen = false;
      st.sheetReturn = null;
      st.openRecord = null;
      st.inspectorReturn = null;
      st.filter = "";
      filterInput.value = "";
      st.expandedGroups.clear();
      st.groupPages.clear();
    }
    st.model = model;
    if (st.openRecord && !(st.openRecord.kind === "milestones" ? model.milestoneById : model.taskById).has(st.openRecord.id)) {
      st.openRecord = null;
      st.sheetOpen = false;
      st.inspectorReturn = null;
    }
    if (layout === "inspector") {
      if (!model.taskById.has(st.selectedTaskId)) {
        if (st.sheetOpen && root.contains(document.activeElement)) st.pendingFocus = ROVING;
        st.sheetOpen = false;
        st.sheetReturn = null;
        st.selectedTaskId = model.tasks[0]?.id ?? null;
      }
    } else {
      st.groups = buildGroups(model);
      const groupKeys = new Set(st.groups.map((g) => g.key));
      for (const k of [...st.expandedGroups]) if (!groupKeys.has(k)) st.expandedGroups.delete(k);
      for (const k of [...st.groupPages.keys()]) if (!groupKeys.has(k)) st.groupPages.delete(k);
    }
    const observedEmpty = model.milestones.length === 0 && model.tasksKnown && model.tasks.length === 0;
    st.status = observedEmpty ? "empty" : "ready";
    st.reason = "";
    render();
    return { ok: true, state: st.status };
  }

  function select(id, { open = false, focus = false } = {}) {
    if (!st.model?.taskById.has(id)) return;
    st.selectedTaskId = id;
    st.page = Math.max(0, Math.floor(filteredTasks(st.model).findIndex(task => task.id === id) / PAGE_SIZE));
    if (open && st.narrow) {
      st.sheetOpen = true;
      st.sheetReturn = fk("task", id);
      st.pendingFocus = SHEET_CLOSE;
    } else if (focus) {
      st.pendingFocus = fk("task", id);
    }
    render();
  }

  function closeSheet() {
    if (!st.sheetOpen && !st.openRecord) return;
    st.sheetOpen = false;
    st.openRecord = null;
    st.pendingFocus = st.inspectorReturn ?? st.sheetReturn ?? ROVING;
    st.inspectorReturn = null;
    st.sheetReturn = null;
    render();
  }

  function openRecord(kind, id, returnKey) {
    if (!(kind === "milestones" ? st.model.milestoneById : st.model.taskById).has(id)) return;
    if (kind === "tasks") st.selectedTaskId = id;
    st.openRecord = { kind, id };
    st.inspectorReturn = returnKey;
    st.sheetOpen = st.narrow;
    st.pendingFocus = SHEET_CLOSE;
    render();
  }

  // ------------------------------------------------------------ render

  function noticeText() {
    if (st.status === "error") return `No valid snapshot to show: ${st.reason}`;
    if (st.status === "stale") return `Update rejected; showing the last valid snapshot: ${st.reason}`;
    if (st.status === "empty") return "This snapshot declares no milestones or tasks.";
    return "";
  }

  function provenanceText(m) {
    const source =
      m.cursor === null
        ? "source snapshot, not live Ledger state"
        : `Ledger cursor ${m.cursor}, freshness not verified`;
    const tasks = m.tasksKnown ? "" : " · task records not declared";
    return `Project ${m.projectId} · source version ${m.sourceVersion} · ${source}${tasks}`;
  }

  function focusByKey(key) {
    const scope = st.sheetEl ?? root;
    const node =
      key === ROVING
        ? viewHost.querySelector('.stv-task-option[tabindex="0"]')
        : [...scope.querySelectorAll("[data-stv-focus]")].find((n) => n.dataset.stvFocus === key && !n.closest("[inert], [hidden]"));
    if (!node) return false;
    node.focus();
    return true;
  }

  function render() {
    if (destroyed) return;
    const active = document.activeElement;
    const hadFocus = active !== null && root.contains(active);
    const key = st.pendingFocus ?? (hadFocus ? active.dataset?.stvFocus ?? null : null);
    const openReferences = new Set([...viewHost.querySelectorAll("details[data-stv-reference][open]")]
      .filter(node => !node.closest("[inert], [hidden]")).map(node => node.dataset.stvReference));
    st.pendingFocus = null;
    st.sheetEl = null;

    const m = st.model;
    root.dataset.stvState = st.status;
    root.dataset.stvProvenance = !m ? "none" : m.cursor === null ? "source-snapshot" : "ledger-cursor";
    if (m) root.dataset.stvTasks = m.tasksKnown ? "declared" : "undeclared";
    else delete root.dataset.stvTasks;
    if (st.reason) root.dataset.stvReason = st.reason;
    else delete root.dataset.stvReason;
    root.classList.toggle("stv--narrow", st.narrow);
    root.classList.toggle("stv--sheet-open", st.sheetOpen);
    provenanceEl.textContent = m ? provenanceText(m) : "";
    const notice = noticeText();
    if (noticeEl.textContent !== notice) noticeEl.textContent = notice;

    if (!m) viewHost.replaceChildren();
    else if (st.openRecord) {
      const record = (st.openRecord.kind === "milestones" ? m.milestoneById : m.taskById).get(st.openRecord.id);
      const origin = st.narrow ? h("div", { class: "stv-origin", inert: true }, [
        layout === "inspector" ? renderInspector(m, false) : renderMilestones(m),
      ]) : null;
      viewHost.replaceChildren(...[origin, renderDetail(m, record, true)].filter(Boolean));
    } else viewHost.replaceChildren(layout === "inspector" ? renderInspector(m) : renderMilestones(m));

    for (const node of viewHost.querySelectorAll("details[data-stv-reference]")) node.open = openReferences.has(node.dataset.stvReference);
    if (key && focusByKey(key)) return;
    if (hadFocus && !root.contains(document.activeElement)) viewHost.focus();
  }

  function filteredTasks(m) {
    return m.tasks.filter(t => !st.filter || (t.title || "").toLowerCase().includes(st.filter));
  }

  function renderInspector(m, withDetail = true) {
    const tasks = filteredTasks(m);
    const pageCount = Math.max(1, Math.ceil(tasks.length / PAGE_SIZE));
    st.page = Math.min(Math.max(st.page, 0), pageCount - 1);
    const start = st.page * PAGE_SIZE;
    const slice = tasks.slice(start, start + PAGE_SIZE);
    const rovingId = slice.some((t) => t.id === st.selectedTaskId) ? st.selectedTaskId : slice[0]?.id;

    const list = h(
      "ul",
      { class: "stv-task-list", role: "listbox", "aria-label": "Tasks" },
      slice.map((t) => {
        const selected = t.id === st.selectedTaskId;
        return h(
          "li",
          {
            class: selected ? "stv-task-option is-selected" : "stv-task-option",
            role: "option",
            "aria-selected": String(selected),
            tabindex: t.id === rovingId ? "0" : "-1",
            data: { stvAction: "select", taskId: t.id, state: t.state, stvFocus: fk("task", t.id) },
          },
          [
            stateMark(t.state),
            h("span", { class: "stv-task-title", text: t.title || "Untitled task" }),
            stateLabel(t.state),
            h("span", { class: "stv-option-chevron", "aria-hidden": "true" }, [chevron()]),
          ],
        );
      }),
    );
    const noTasks = st.filter && m.tasks.length
      ? h("p", { class: "stv-empty", text: "No matching titles." }) : m.tasksKnown
      ? h("p", { class: "stv-empty", text: "No task records in this snapshot." })
      : h("p", { class: "stv-undeclared", text: "Task records are not declared in this source snapshot." });
    const sheetActive = st.narrow && st.sheetOpen;
    const listColumn = h("div", { class: "stv-inspector-list", inert: sheetActive }, [
      tasks.length ? list : noTasks,
      pager("inspector", st.page, tasks.length, "Task pages"),
    ]);

    return h("div", { class: "stv-inspector" }, [listColumn, withDetail ? renderDetail(m, m.taskById.get(st.selectedTaskId) ?? null) : null]);
  }

  function renderDetail(m, selected, standalone = false) {
    const sheetActive = st.narrow && st.sheetOpen;
    const headingId = `${prefix}-detail-title`;
    const detail = h(
      "section",
      {
        class: `${st.narrow ? "stv-detail stv-detail--sheet" : "stv-detail"}${standalone ? " stv-detail--standalone" : ""}`,
        id: `${prefix}-detail`,
        role: st.narrow ? "dialog" : "region",
        "aria-modal": st.narrow ? "true" : null,
        "aria-labelledby": headingId,
        hidden: st.narrow && !st.sheetOpen,
        tabindex: "-1",
        data: { recordKind: selected?.kind, recordId: selected?.id },
      },
      [
        st.narrow || standalone
          ? h("button", {
              type: "button",
              class: "stv-sheet-close",
              "aria-label": layout === "milestones" ? "Back to milestones" : "Back to tasks",
              text: "Back",
              data: { stvAction: "close-sheet", stvFocus: SHEET_CLOSE },
            })
          : null,
        st.narrow && selected ? h("h2", { class: "stv-detail-title stv-sheet-title", id: headingId, text: selected.title || "Untitled record" }) : null,
        selected
          ? taskDetail(m, selected, st.narrow ? null : headingId)
          : h("p", { class: "stv-detail-placeholder", id: headingId, text: "No task selected." }),
      ],
    );
    if (sheetActive) st.sheetEl = detail;
    return detail;
  }

  function renderMilestones(m) {
    if (!st.groups.length) {
      return m.tasksKnown
        ? h("p", { class: "stv-empty", text: "No milestones or tasks in this snapshot." })
        : h("p", { class: "stv-undeclared", text: "No milestones are declared, and task records are not declared in this source snapshot." });
    }
    const groups = st.groups.filter(g => !st.filter || (g.milestone?.title || "").toLowerCase().includes(st.filter) ||
      g.rows.some(row => (row.task?.title || "").toLowerCase().includes(st.filter)));
    return groups.length ? h("div", { class: "stv-milestones" }, groups.map((g, gi) => renderGroup(m, g, gi)))
      : h("p", { class: "stv-empty", text: "No matching titles." });
  }

  function countText(m, g) {
    const n = g.rows.length;
    if (m.tasksKnown) return `${n} ${n === 1 ? "task" : "tasks"}`;
    if (g.milestone.task_ids === null) return "Tasks not declared";
    return `${n} listed task ${n === 1 ? "id" : "ids"}`;
  }

  function renderGroup(m, g, gi) {
    const ms = g.milestone;
    const expanded = st.expandedGroups.has(g.key);
    const bodyId = `${prefix}-group-${gi}`;
    const toggle = h(
      "button",
      {
        type: "button",
        class: "stv-group-toggle",
        "aria-expanded": String(expanded),
        "aria-label": `${expanded ? "Collapse" : "Expand"} ${ms?.title || "milestone tasks"}`,
        "aria-controls": bodyId,
        data: { stvAction: "toggle-group", stvGroup: g.key, stvFocus: fk("group", g.key) },
      },
      [
        chevron(),
      ],
    );
    return h(
      "section",
      {
        class: `stv-group${ms ? "" : " stv-group--unbound"}${expanded ? " is-expanded" : ""}`,
        data: { group: ms ? "milestone" : "unbound", milestoneId: ms?.id, state: ms?.state },
      },
      [
        h("div", { class: "stv-group-heading" }, [stateMark(ms?.state),
          ms ? h("button", { type: "button", class: "stv-record-title stv-group-title", text: ms.title || "Untitled milestone",
            data: { stvAction: "open-record", recordKind: "milestones", recordId: ms.id, stvFocus: fk("milestone-title", ms.id) } })
            : h("h3", { class: "stv-group-title", text: "Not bound to a milestone" }),
          h("span", { class: "stv-group-meta" }, [stateLabel(ms?.state), h("span", { class: "stv-group-count", text: countText(m, g) })]),
          toggle,
        ]),
        h("div", { class: "stv-group-body", id: bodyId, hidden: !expanded }, expanded ? renderGroupBody(m, g) : []),
      ],
    );
  }

  function noRowsText(m, ms) {
    if (m.tasksKnown) return "This milestone declares no tasks.";
    if (ms.task_ids === null) return "Task membership is not declared in this source snapshot.";
    return "This milestone lists no task ids; task records are not declared.";
  }

  function renderGroupBody(m, g) {
    const ms = g.milestone;
    const pageCount = Math.max(1, Math.ceil(g.rows.length / PAGE_SIZE));
    const page = Math.min(Math.max(st.groupPages.get(g.key) ?? 0, 0), pageCount - 1);
    const start = page * PAGE_SIZE;
    return [
      !ms ? h("p", { class: "stv-unbound-note", text: "Tasks without a declared milestone." }) : null,
      g.rows.length
        ? h(
            "ol",
            { class: "stv-rows", start: start + 1 },
            g.rows.slice(start, start + PAGE_SIZE).map((row) => renderRow(m, row)),
          )
        : h("p", { class: m.tasksKnown ? "stv-empty" : "stv-undeclared", text: noRowsText(m, ms) }),
      pager(g.key, page, g.rows.length, "Milestone task pages"),
    ];
  }

  function renderRow(m, row) {
    const t = row.task;
    const selected = t !== null && t.id === st.selectedTaskId;
    const record = t ? "present" : m.tasksKnown ? "missing" : "undeclared";
    const notes = [];
    if (record === "missing") notes.push("No task record with this id in the snapshot.");
    if (record === "undeclared") notes.push("Task records are not declared in this source snapshot.");
    if (row.conflict) notes.push("Declared in more than one milestone.");
    if (t?.milestone_id && !m.milestoneById.has(t.milestone_id)) {
      notes.push(`Declares milestone ${t.milestone_id}, which has no record in this snapshot.`);
    }
    const title = t ? t.title || "Untitled task" : record === "missing" ? "Missing task record" : "Task record not declared";
    const head = h(t ? "button" : "div", {
      class: t ? "stv-row-head stv-row-toggle" : "stv-row-head",
      ...(t ? { type: "button", "aria-current": selected ? "true" : null,
        data: { stvAction: "open-record", recordKind: "tasks", recordId: t.id, stvFocus: fk("row", row.key) } } : {}),
    }, [stateMark(t?.state), h("span", { class: "stv-row-title", text: title }), stateLabel(t?.state),
      t ? h("span", { class: "stv-option-chevron", "aria-hidden": "true" }, [chevron()]) : null]);
    return h(
      "li",
      {
        class: selected ? "stv-row is-selected" : "stv-row",
        data: { taskId: row.id, state: t?.state, record, membership: row.conflict ? "conflict" : "single" },
      },
      [
        head,
        notes.map((text) => h("p", { class: "stv-row-note", text })),
      ],
    );
  }

  // ------------------------------------------------------------ events

  function onClick(event) {
    const target = event.target instanceof Element ? event.target.closest("[data-stv-action]") : null;
    if (!target || !viewHost.contains(target) || !st.model) return;
    const d = target.dataset;
    const toggle = (set, key) => (set.has(key) ? set.delete(key) : set.add(key));
    switch (d.stvAction) {
      case "select":
        select(d.taskId, { open: true });
        break;
      case "close-sheet":
        closeSheet();
        break;
      case "open-record":
        openRecord(d.recordKind, d.recordId, d.stvFocus);
        break;
      case "page": {
        const page = Number.parseInt(d.stvPage, 10) || 0;
        if (d.stvScope === "inspector") {
          st.page = page;
          st.pendingFocus = ROVING;
        } else {
          st.groupPages.set(d.stvScope, page);
          st.pendingFocus = fk("group", d.stvScope);
        }
        render();
        break;
      }
      case "toggle-group":
        toggle(st.expandedGroups, d.stvGroup);
        render();
        break;
    }
  }

  function trapTab(event, sheet) {
    const nodes = [...sheet.querySelectorAll(FOCUSABLE)].filter((n) => !n.closest("[hidden]"));
    const active = document.activeElement;
    if (!nodes.length) {
      event.preventDefault();
      sheet.focus();
      return;
    }
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (event.shiftKey && (active === first || active === sheet)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function onKeyDown(event) {
    if (st.openRecord && event.key === "Escape") {
      event.preventDefault();
      closeSheet();
      return;
    }
    if (st.sheetOpen && st.sheetEl) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeSheet();
        return;
      }
      if (event.key === "Tab") {
        trapTab(event, st.sheetEl);
        return;
      }
    }
    if (layout !== "inspector" || !st.model) return;
    const option = event.target instanceof Element ? event.target.closest('[data-stv-action="select"]') : null;
    if (!option) return;
    const tasks = filteredTasks(st.model);
    const at = tasks.findIndex(task => task.id === option.dataset.taskId);
    const moves = {
      ArrowDown: at + 1,
      ArrowUp: at - 1,
      Home: 0,
      End: tasks.length - 1,
      PageDown: at + PAGE_SIZE,
      PageUp: at - PAGE_SIZE,
    };
    if (Object.hasOwn(moves, event.key)) {
      event.preventDefault();
      const next = tasks[Math.min(Math.max(moves[event.key], 0), tasks.length - 1)];
      if (next) select(next.id, { focus: true });
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      select(option.dataset.taskId, { open: true, focus: true });
    }
  }

  function onFocusIn(event) {
    if (st.sheetOpen && st.sheetEl && !st.sheetEl.contains(event.target)) {
      (st.sheetEl.querySelector(FOCUSABLE) ?? st.sheetEl).focus();
    }
  }

  function onMedia() {
    st.narrow = mql.matches;
    if (st.narrow && st.openRecord) st.sheetOpen = true;
    if (!st.narrow && st.sheetOpen) {
      st.sheetOpen = false;
      st.pendingFocus = st.sheetReturn;
      st.sheetReturn = null;
    }
    render();
  }

  root.addEventListener("click", onClick, { signal });
  root.addEventListener("keydown", onKeyDown, { signal });
  filterInput.addEventListener("input", () => {
    st.filter = filterInput.value.trim().toLowerCase();
    st.page = 0;
    render();
  }, { signal });
  document.addEventListener("focusin", onFocusIn, { signal });
  mql?.addEventListener("change", onMedia, { signal });

  apply(snapshot);

  return {
    update(next) {
      if (destroyed) return { ok: false, state: "destroyed", reason: "view destroyed" };
      return apply(next);
    },
    destroy() {
      if (destroyed) return;
      const active = document.activeElement;
      if (active && root.contains(active)) active.blur();
      destroyed = true;
      controller.abort();
      root.remove();
      st.model = st.groups = st.sheetEl = st.pendingFocus = st.sheetReturn = null;
      st.sheetOpen = false;
      st.openRecord = st.inspectorReturn = null;
      st.expandedGroups.clear();
      st.groupPages.clear();
    },
  };
}
