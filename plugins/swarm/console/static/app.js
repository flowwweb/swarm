const state = {
  token: "",
  overview: null,
  config: null,
  changes: {},
  view: "swarm",
  readOnly: false,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const RAIL_STATE_KEY = "swarm.console.rail-collapsed";
const MOBILE_RAIL = window.matchMedia("(max-width: 720px)");
const REQUESTED_CONTROLLER = new URLSearchParams(location.search).get("ctrl") || "";

const settingGroups = [
  {
    title: "Portfolio",
    fields: [
      ["portfolio.max_active_tasks", "Active task ceiling", "number", "Producing, integrating, or reviewing tasks"],
      ["portfolio.default_parallel_tasks", "Preferred parallel wave", "number", "A ceiling, never a creation quota"],
      ["portfolio.reuse_existing_tasks", "Reuse matching owners", "boolean", "Avoid duplicate task startup"],
      ["coordination.preferred_lane_width", "Preferred lane width", "number", "Soft shape after delegation is justified"],
      ["coordination.allow_coordinators", "Allow coordinators", "boolean", "Permit LEAD coordination when useful"],
    ],
  },
  {
    title: "Execution",
    fields: [
      ["execution.usage_profile", "Usage profile", "select", "Relative model and effort policy", ["high", "medium", "low"]],
      ["execution.service_tier", "Service tier", "text", "Empty keeps the host default"],
      ["execution.usage_saver", "Usage Saver", "boolean", "Reduce avoidable coordination churn"],
      ["console.open_on_start", "Open portal on start", "boolean", "Reuse an open portal tab; closed tabs expire after a short grace period"],
      ["subagents.enabled", "Internal subagents", "boolean", "Bounded work inside an owning task"],
      ["subagents.max_per_task", "Subagent ceiling", "number", "Separate safety ceiling, not a target"],
      ["monitoring.heartbeat_minutes", "Freshness minutes", "number", "Optional alert-only sensor; ordinary alerts return to the watched owner"],
    ],
  },
  {
    title: "Review & recovery",
    fields: [
      ["review.task_enabled", "Dedicated REVIEW tasks", "boolean", "QC remains required when disabled"],
      ["review.max_parallel_tasks", "Review ceiling", "number", "Concurrent independent review surfaces"],
      ["review.scale_when_queue_reaches", "Scale review at queue", "number", "Ready artifacts before another reviewer"],
      ["recovery.stall_after_updates", "Stall after updates", "number", "Material owner updates, not heartbeat reads"],
    ],
  },
  {
    title: "Closeout",
    fields: [
      ["boost.enabled", "Boost available", "boolean", "Still requires direct run authorization"],
      ["lifecycle.pin_created_tasks", "Pin new tasks", "boolean", "Keep new SWARM owners visible"],
      ["lifecycle.archive_completed_tasks", "Archive accepted tasks", "boolean", "Terminal acceptance; ambiguity stays open"],
      ["feedback.enabled", "Feedback workflow", "boolean", "On-demand, never automatic submission"],
      ["feedback.prompt_on_close", "Offer feedback on close", "boolean", "One optional prompt after acceptance"],
    ],
  },
  {
    title: "Hierarchy names",
    fields: [
      ["labels.lead", "LEAD label", "text", "Bounded domain coordinator"],
      ["labels.review", "REVIEW label", "text", "Independent evidence verdict"],
      ["labels.doer", "Fallback DOER label", "text", "Used only when no clearer role exists"],
    ],
  },
  {
    title: "Role signals",
    fields: [
      ["role_icons.enabled", "Task title icons", "boolean", "Disable only when all SWARM title emojis should disappear"],
      ["role_icons.ctrl", "CTRL icon", "text", "Default octopus control signal"],
      ["role_icons.lead", "LEAD icon", "text", "Domain direction signal"],
      ["role_icons.review", "REVIEW icon", "text", "Independent inspection signal"],
      ["role_icons.fallback", "Fallback icon", "text", "Only when no literal DOER metaphor fits"],
    ],
  },
];

function escapeHTML(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
}

function getPath(object, path) {
  return path.split(".").reduce((value, key) => value?.[key], object);
}

function formatDuration(ms) {
  if (ms == null) return "unknown";
  const minutes = Math.floor(ms / 60000);
  if (minutes < 60) return `${Math.max(1, minutes)}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function showError(message) {
  $("#error-message").textContent = message;
  $("#error-surface").hidden = false;
}

function clearError() {
  $("#error-surface").hidden = true;
}

const railState = { pinned: false, preview: false, suppressFocusPreview: false, suppressPointerPreview: false };

function renderRail(persist = false) {
  const shell = $(".app-shell");
  const button = $("#rail-toggle");
  const collapseButton = $("#panel-collapse");
  const panel = $("#console-sidepanel");
  const expanded = !MOBILE_RAIL.matches && (railState.pinned || railState.preview);
  shell.classList.toggle("rail-expanded", expanded);
  button.setAttribute("aria-expanded", String(expanded));
  button.setAttribute("aria-label", expanded ? "Collapse sidepanel" : "Expand sidepanel");
  button.title = expanded ? "Collapse sidepanel" : "Expand sidepanel";
  collapseButton.setAttribute("aria-expanded", String(expanded));
  collapseButton.setAttribute("aria-label", railState.pinned ? "Collapse sidepanel" : "Keep sidepanel open");
  collapseButton.title = railState.pinned ? "Collapse sidepanel" : "Keep sidepanel open";
  panel.toggleAttribute("inert", !expanded && !MOBILE_RAIL.matches);
  panel.setAttribute("aria-hidden", String(!expanded && !MOBILE_RAIL.matches));
  if (persist) {
    try { localStorage.setItem(RAIL_STATE_KEY, railState.pinned ? "0" : "1"); } catch {}
  }
}

function closeRail() {
  railState.pinned = false;
  railState.preview = false;
  renderRail(true);
}

try { railState.pinned = localStorage.getItem(RAIL_STATE_KEY) === "0"; } catch {}
renderRail();

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(state.token ? { "X-Swarm-Token": state.token } : {}),
      ...(options.headers || {}),
    },
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function setView(view) {
  state.view = view;
  $$(".nav-item").forEach((button) => button.classList.toggle("is-active", button.dataset.view === view));
  $$("[data-view-panel]").forEach((panel) => panel.classList.toggle("is-active", panel.dataset.viewPanel === view));
  const titles = { swarm: "Graph", settings: "Settings" };
  $("#view-title").textContent = titles[view];
  if (view === "swarm") {
    $("#swarm-canvas").dataset.project = "";
    requestAnimationFrame(renderSwarm);
  }
}

function renderProjectFilter() {
  const select = $("#project-filter");
  const current = select.value;
  select.innerHTML = `<option value="all">All projects</option>${state.overview.projects.map((project) => `<option value="${escapeHTML(project.id)}">${escapeHTML(project.name)}</option>`).join("")}`;
  select.value = [...select.options].some((option) => option.value === current) ? current : "all";
}

function renderControllerFilter() {
  const select = $("#controller-filter");
  const current = select.value;
  const controllers = state.overview.controllers || [];
  select.innerHTML = controllers.length
    ? controllers.map((controller) => `<option value="${escapeHTML(controller.id)}">${escapeHTML(controller.artifact)} · ${controller.nodes} nodes</option>`).join("")
    : `<option value="all">No observed CTRL</option>`;
  select.value = [...select.options].some((option) => option.value === current)
    ? current
    : ([...select.options].some((option) => option.value === REQUESTED_CONTROLLER)
      ? REQUESTED_CONTROLLER
      : (controllers[0]?.id || "all"));
}

function roleColor(role) {
  return { ctrl: "#f15936", specialist: "#8cb6ff", lead: "#60daff", review: "#8cb6ff", doer: "#84c2da" }[role] || "#84c2da";
}

function hierarchyStatus(status) {
  const active = status === "active";
  return `<span class="node-status${active ? " is-processing" : ""}" role="status" aria-label="Status: ${escapeHTML(status)}"><i aria-hidden="true"></i><span>${escapeHTML(status)}</span></span>`;
}

function renderSwarm() {
  if (!state.overview) return;
  const project = $("#project-filter").value || "all";
  const controller = $("#controller-filter").value || "all";
  const allNodes = state.overview.nodes.filter((node) =>
    (project === "all" || node.project_id === project) &&
    (controller === "all" || (node.controller_ids || []).includes(controller)),
  );
  const ids = new Set(allNodes.map((node) => node.id));
  const allLinks = state.overview.links.filter((link) => ids.has(link.source) && ids.has(link.target));
  const displayNodes = allNodes;
  const links = allLinks;
  const incoming = new Map(links.map((link) => [link.target, link.source]));
  const children = new Map();
  links.forEach((link) => children.set(link.source, [...(children.get(link.source) || []), link.target]));
  const roots = displayNodes.filter((node) => !incoming.has(node.id));
  const depth = new Map();
  const queue = roots.map((node) => [node.id, 0]);
  while (queue.length) {
    const [id, level] = queue.shift();
    if (depth.has(id) && depth.get(id) <= level) continue;
    depth.set(id, level);
    (children.get(id) || []).forEach((child) => queue.push([child, level + 1]));
  }
  displayNodes.forEach((node) => { if (!depth.has(node.id)) depth.set(node.id, 0); });
  const levels = new Map();
  displayNodes.forEach((node) => levels.set(depth.get(node.id), [...(levels.get(depth.get(node.id)) || []), node]));
  const scroller = $(".swarm-scroll");
  const maxWidth = Math.max(1, ...[...levels.values()].map((items) => items.length));
  const levelStride = 150;
  const widestNode = 188;
  const stage = scroller.getBoundingClientRect();
  const requiredWidth = maxWidth * widestNode + Math.max(0, maxWidth - 1) * 24 + (maxWidth > 1 ? 32 : 0);
  const requiredHeight = levels.size * levelStride + 70;
  const overflowX = requiredWidth > Math.floor(stage.width);
  const overflowY = requiredHeight > Math.floor(stage.height);
  const width = overflowX ? requiredWidth : Math.floor(stage.width);
  const height = overflowY ? requiredHeight : Math.floor(stage.height);
  const positions = new Map();
  const firstLevelY = Math.max(72, (height - Math.max(0, levels.size - 1) * levelStride) / 2);
  [...levels.entries()].sort(([a], [b]) => a - b).forEach(([level, items]) => {
    items.sort((a, b) => a.project.localeCompare(b.project) || a.created_at - b.created_at);
    const gap = width / (items.length + 1);
    items.forEach((node, index) => positions.set(node.id, { x: gap * (index + 1), y: firstLevelY + level * levelStride }));
  });
  const canvas = $("#swarm-canvas");
  scroller.style.overflowX = overflowX ? "auto" : "hidden";
  scroller.style.overflowY = overflowY ? "auto" : "hidden";
  canvas.style.width = overflowX ? `${width}px` : "100%";
  canvas.style.height = overflowY ? `${height}px` : "100%";
  $("#swarm-links").setAttribute("viewBox", `0 0 ${width} ${height}`);
  $("#swarm-links").innerHTML = links.map((link) => {
    const a = positions.get(link.source), b = positions.get(link.target);
    if (!a || !b) return "";
    const bend = Math.max(36, (b.y - a.y) * .5);
    const active = allNodes.find((node) => node.id === link.target)?.status === "active";
    return `<path class="swarm-link${active ? " is-active" : ""}" d="M ${a.x} ${a.y + 52} C ${a.x} ${a.y + bend}, ${b.x} ${b.y - bend}, ${b.x} ${b.y - 52}"/>`;
  }).join("");
  $("#swarm-nodes").innerHTML = displayNodes.map((node) => {
    const p = positions.get(node.id);
    const worker = node.worker || node.worker_role
      ? `<span class="node-worker">${node.worker_role ? `<b>${escapeHTML(node.worker_role)}</b>` : ""}<span aria-hidden="true">●</span>${escapeHTML(node.worker || "unassigned")}</span>`
      : "";
    const workerDetail = node.worker ? `. Worker: ${node.worker}${node.worker_role ? ` (${node.worker_role})` : ""}` : "";
    return `<article class="swarm-node role-${escapeHTML(node.role)} is-${escapeHTML(node.status)}" style="left:${p.x}px;top:${p.y}px;--node-color:${roleColor(node.role)}" aria-label="${escapeHTML(`${node.role_label} - ${node.artifact}${workerDetail}. Model: ${node.model || "unknown"}. Status: ${node.status}`)}"><div class="node-top"><span class="node-icon" aria-hidden="true">${escapeHTML(node.icon)}</span><span class="node-role">${escapeHTML(node.role_label)}</span><span class="node-model">${escapeHTML(node.model || "unknown")}</span></div><strong>${escapeHTML(node.artifact)}</strong><div class="node-meta">${worker}${hierarchyStatus(node.status)}</div></article>`;
  }).join("");
  if (!displayNodes.length) $("#swarm-nodes").innerHTML = `<div class="empty-state">Host has not exposed a CTRL.</div>`;
  const scopeKey = `${project}:${controller}`;
  if (canvas.dataset.project !== scopeKey) {
    const first = positions.get(roots[0]?.id);
    scroller.scrollLeft = first ? Math.max(0, first.x - scroller.clientWidth / 2) : 0;
    scroller.scrollTop = 0;
    canvas.dataset.project = scopeKey;
  }
  renderScopeCopy(allNodes, controller);
  renderScopeActivity(allNodes);
}

function renderScopeCopy(nodes, controllerId) {
  const controller = (state.overview.controllers || []).find((item) => item.id === controllerId);
  const performance = state.overview.performance;
  const scope = controller
    ? (nodes.length > 1 ? `${nodes.length} nodes` : "1 node · host has not exposed child lanes")
    : "No CTRL";
  const refresh = performance ? `${performance.refresh_seconds}s refresh · ${performance.data_bytes} B snapshot` : "30s refresh";
  const omitted = controller?.older_lanes_omitted ? ` · ${controller.older_lanes_omitted} older lanes omitted` : "";
  $("#scope-copy").textContent = `${scope}${omitted} · ${refresh}`;
}

function renderScopeActivity(nodes) {
  const recent = nodes.filter((node) => !node.virtual && node.status === "active")
    .sort((a, b) => b.updated_at - a.updated_at).slice(0, 6);
  $("#scope-activity").innerHTML = recent.length
    ? recent.map((node) => `<div class="pulse-row"><i class="pulse-dot"></i><span><strong>${escapeHTML(node.artifact)}</strong><small>${node.worker ? `${escapeHTML(node.worker)} · ` : ""}${escapeHTML(node.project)} · updated ${formatDuration(node.quiet_ms)} ago</small></span></div>`).join("")
    : `<div class="empty-state">No recent host activity.</div>`;
}

function renderSettings() {
  if (!state.config) return;
  $("#config-path").textContent = state.config.path;
  $("#settings-grid").innerHTML = settingGroups.map((group) => `<section class="settings-card"><h3>${group.title}</h3><div class="field-list">${group.fields.map(renderField).join("")}</div></section>`).join("");
  $("#save-settings").disabled = Object.keys(state.changes).length === 0;
  if (state.readOnly) $("#settings-status").textContent = "Remote view is read-only. Open the console on this computer to change settings.";
}

function renderField([path, label, type, hint, options]) {
  const value = getPath(state.config.settings, path);
  const disabled = state.readOnly ? " disabled" : "";
  let control;
  if (type === "boolean") {
    control = `<label class="switch"><input data-setting="${path}" type="checkbox" ${value ? "checked" : ""}${disabled} aria-label="${escapeHTML(label)}"><span aria-hidden="true"></span></label>`;
  } else if (type === "select") {
    control = `<select data-setting="${path}"${disabled} aria-label="${escapeHTML(label)}">${options.map((option) => `<option value="${option}" ${option === value ? "selected" : ""}>${option}</option>`).join("")}</select>`;
  } else {
    control = `<input data-setting="${path}" type="${type}" value="${escapeHTML(value ?? "")}"${disabled} aria-label="${escapeHTML(label)}">`;
  }
  return `<div class="field"><div><label>${escapeHTML(label)}</label><small>${escapeHTML(hint)}</small></div>${control}</div>`;
}

function normalizeInput(input) {
  if (input.type === "checkbox") return input.checked;
  if (input.type === "number") return Number(input.value);
  return input.value;
}

async function saveSettings() {
  if (state.readOnly || !Object.keys(state.changes).length) return;
  const button = $("#save-settings");
  button.disabled = true;
  $("#settings-status").textContent = "Validating…";
  try {
    const result = await api("/api/config", { method: "POST", body: JSON.stringify({ changes: state.changes }) });
    state.config = result;
    state.changes = {};
    $("#settings-status").textContent = "Saved. New scheduling waves will use this config.";
    renderSettings();
    await refreshOverview();
  } catch (error) {
    $("#settings-status").textContent = error.message;
    button.disabled = false;
  }
}

async function refreshOverview() {
  clearError();
  try {
    state.overview = await api("/api/overview");
    renderProjectFilter(); renderControllerFilter(); renderSwarm();
    $("#sync-time").textContent = new Date(state.overview.generated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch (error) {
    showError(error.message);
  }
}

async function initialize() {
  try {
    const bootstrap = await api("/api/bootstrap");
    state.token = bootstrap.token;
    state.readOnly = Boolean(bootstrap.read_only);
    state.config = await api("/api/config");
    renderSettings();
    await refreshOverview();
  } catch (error) {
    showError(error.message);
  }
}

document.addEventListener("click", (event) => {
  const nav = event.target.closest("[data-view]");
  if (nav) setView(nav.dataset.view);
});
$("#refresh").addEventListener("click", refreshOverview);
const sidepanelRegion = $(".sidepanel-region");
const railToggle = $("#rail-toggle");
const panelCollapse = $("#panel-collapse");
railToggle.addEventListener("pointerenter", (event) => { if (!railState.pinned && !railState.suppressPointerPreview && event.pointerType !== "touch") { railState.preview = true; renderRail(); } });
railToggle.addEventListener("focus", (event) => {
  if (railState.pinned || railState.suppressFocusPreview || !event.currentTarget.matches(":focus-visible")) return;
  railState.preview = true;
  renderRail();
  panelCollapse.focus();
});
$("#rail-toggle").addEventListener("click", (event) => {
  railState.pinned = !railState.pinned;
  railState.preview = false;
  renderRail(true);
  if (!event.detail && railState.pinned) panelCollapse.focus();
});
panelCollapse.addEventListener("click", (event) => {
  if (!railState.pinned && railState.preview) {
    railState.pinned = true;
    railState.preview = false;
    renderRail(true);
    return;
  }
  railState.suppressPointerPreview = Boolean(event.detail);
  closeRail();
  if (!event.detail) {
    railState.suppressFocusPreview = true;
    railToggle.focus();
    railState.suppressFocusPreview = false;
  }
});
sidepanelRegion.addEventListener("pointerleave", () => { railState.suppressPointerPreview = false; if (!railState.pinned && !sidepanelRegion.contains(document.activeElement)) { railState.preview = false; renderRail(); } });
sidepanelRegion.addEventListener("focusout", (event) => { if (!railState.pinned && !sidepanelRegion.contains(event.relatedTarget)) { railState.preview = false; renderRail(); } });
MOBILE_RAIL.addEventListener("change", () => renderRail());
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || MOBILE_RAIL.matches || (!railState.pinned && !railState.preview)) return;
  closeRail();
  railState.suppressFocusPreview = true;
  railToggle.focus();
  railState.suppressFocusPreview = false;
});
$("#project-filter").addEventListener("change", renderSwarm);
$("#controller-filter").addEventListener("change", renderSwarm);
$("#save-settings").addEventListener("click", saveSettings);
$("#settings-form").addEventListener("input", (event) => {
  if (state.readOnly) return;
  const input = event.target.closest("[data-setting]");
  if (!input) return;
  state.changes[input.dataset.setting] = normalizeInput(input);
  $("#save-settings").disabled = false;
  $("#settings-status").textContent = `${Object.keys(state.changes).length} unsaved change${Object.keys(state.changes).length === 1 ? "" : "s"}`;
});
window.addEventListener("resize", () => { if (state.view === "swarm") renderSwarm(); });

initialize();
setInterval(() => {
  if (document.visibilityState === "visible") refreshOverview();
}, 30_000);
setInterval(() => {
  if (document.visibilityState === "hidden" && state.token && !state.readOnly) {
    api("/api/presence", { method: "POST" }).catch(() => {});
  }
}, 60_000);
