const state = { token: "", overview: null, proof: [], proofCollections: new Map(), proofStatuses: new Map(), proofStatus: "idle", proofSequence: 0, usageHistory: null, usageWindowHours: 24, usageScopeKey: "", usageStatus: "idle", usageError: "", projectProgressFeed: null, projectProgressProjectId: "", projectProgressStatus: "idle", projectProgressError: "", diagnostics: null, diagnosticHistory: [], health: null, storage: null, config: null, ctrlSettings: null, skills: null, skillsError: "", view: "overview", projectId: "all", ctrlId: "", settingsCtrlId: "", settingsScopeType: "", settingsScopeId: "", evidenceImages: [], evidenceIndex: 0, evidenceTrigger: null };
const EVIDENCE_THUMBNAIL_PAGE_SIZE = 24;
const USAGE_WINDOW_LABELS = { 1: "1h", 24: "1d" };
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function escapeHTML(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
}

function compactNumber(value) {
  return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(Number(value) || 0);
}

function formatBytes(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "Unavailable";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const unit = Math.min(Math.max(0, Math.floor(Math.log(Math.max(amount, 1)) / Math.log(1024))), units.length - 1);
  const scaled = amount / (1024 ** unit);
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: scaled >= 10 || unit === 0 ? 0 : 1 }).format(scaled) + units[unit];
}

function formatRelative(value) {
  const timestamp = new Date(value || 0).getTime();
  if (!timestamp || Number.isNaN(timestamp)) return "Unknown";
  const minutes = Math.max(0, Math.round((Date.now() - timestamp) / 60000));
  if (minutes < 1) return "Just now";
  if (minutes < 60) return String(minutes) + "m ago";
  if (minutes < 2880) return String(Math.round(minutes / 60)) + "h ago";
  return String(Math.round(minutes / 1440)) + "d ago";
}

function formatEta(value) {
  const date = new Date(Number(value));
  if (!value || Number.isNaN(date.getTime())) return "Unforecast";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(date);
}

function statusLabel(node) {
  const status = String(node.status || "quiet").toLowerCase();
  if (status === "done" || status === "archived") return ["Done", "is-done"];
  if (status === "active" || status === "in_progress") return ["In progress", "is-active"];
  if (status === "blocked") return ["Blocked", "is-blocked"];
  return ["Pending", "is-pending"];
}

const attentionStates = ["blocked", "at_risk", "stalled", "critical"];

function attentionStatus(node) {
  return [node?.status, node?.eta?.status]
    .map((status) => String(status || "").toLowerCase())
    .find((status) => attentionStates.includes(status)) || "";
}

function needsAttention(node) {
  return Boolean(attentionStatus(node));
}

function humanize(value) {
  return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function showError(message) {
  $("#error-message").textContent = message;
  $("#error-surface").hidden = false;
}

function clearError() {
  $("#error-surface").hidden = true;
}

function showConnectionState() {
  clearError();
  $(".workspace").classList.add("is-disconnected");
  $("#connection-state").hidden = false;
}

function clearConnectionState() {
  $(".workspace").classList.remove("is-disconnected");
  $("#connection-state").hidden = true;
}

function connectionFailure(message) {
  const error = new Error(message);
  error.connectionFailure = true;
  return error;
}

async function api(path, options = {}) {
  const { timeoutMs = 0, ...fetchOptions } = options;
  const controller = timeoutMs > 0 ? new AbortController() : null;
  const timeout = controller ? window.setTimeout(() => controller.abort(), timeoutMs) : null;
  try {
    const response = await fetch(path, { ...fetchOptions, ...(controller ? { signal: controller.signal } : {}), headers: { ...(state.token ? { "X-Swarm-Token": state.token } : {}), ...(fetchOptions.headers || {}) } });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Request failed (" + response.status + ")");
    return data;
  } catch (error) {
    if (error?.name === "AbortError") throw connectionFailure("Project data request timed out");
    if (error instanceof TypeError) throw connectionFailure("SWARM cannot reach its local console");
    throw error;
  } finally {
    if (timeout) window.clearTimeout(timeout);
  }
}

function setDataStatus(status, observedAt = null) {
  const title = $("#data-status-title");
  const note = $("#data-status-note");
  const dot = $("#data-status-dot");
  if (!title || !note || !dot) return;
  dot.classList.toggle("is-live", status === "current");
  if (status === "current") {
    title.textContent = "Current";
    note.textContent = observedAt ? "Updated " + formatRelative(observedAt) : "Snapshot received";
  } else if (status === "stale") {
    title.textContent = "Stale";
    note.textContent = observedAt ? "Last update " + formatRelative(observedAt) : "Refresh failed";
  } else if (status === "unavailable") {
    title.textContent = "Data unavailable";
    note.textContent = "Waiting for a project snapshot";
  } else {
    title.textContent = "Connecting";
    note.textContent = "Waiting for data";
  }
}

function scopedNodes() {
  const nodes = state.overview?.nodes || [];
  const projectNodes = state.projectId === "all" || state.projectId.startsWith("ctrl:")
    ? nodes
    : nodes.filter((node) => node.project_id === state.projectId);
  return state.ctrlId ? projectNodes.filter((node) => node.id === state.ctrlId || (node.controller_ids || []).includes(state.ctrlId)) : projectNodes;
}

function setLoading(loading) {
  $("#overview-loading").hidden = !loading;
  $("#overview-content").hidden = loading;
}

function routeView() {
  const view = location.hash.slice(1);
  return ["overview", "dashboard", "hierarchy", "kanban", "diagnostics", "settings"].includes(view) ? view : "overview";
}

function setView(view, focus, syncRoute = true) {
  const selectedView = view === 'dashboard' || view === 'hierarchy' || view === 'kanban' || view === 'diagnostics' || view === 'settings' ? view : 'overview';
  state.view = selectedView;
  const titles = {
    overview: ["Overview", "Project progress, risks, and proof at a glance."],
    dashboard: ["Dashboard", "Project progress, risks, and proof at a glance."],
    hierarchy: ["Hierarchy", "See who owns the work, what is active, and where attention is needed."],
    kanban: ["Kanban", "Task state for the selected project or CTRL."],
    diagnostics: ["Diagnostics", "Device health, capacity, and maintenance."],
    settings: ["Settings", "Defaults and optional per-CTRL overrides."],
  };
  $$(".nav-item").forEach((tab) => {
    const selected = tab.dataset.view === selectedView;
    tab.classList.toggle("is-active", selected);
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
  });
  $$("[data-view-panel]").forEach((panel) => {
    const selected = panel.dataset.viewPanel === selectedView;
    panel.classList.toggle("is-active", selected);
    panel.hidden = !selected;
  });
  $("#view-title").textContent = titles[selectedView][0];
  $("#view-subtitle").textContent = titles[selectedView][1];
  if (selectedView === 'settings' && (!state.skills || state.skillsError)) refreshSkills().then(renderSettings);
  if (syncRoute && location.hash !== '#' + selectedView) history.replaceState(null, '', '#' + selectedView);
  if (focus) $("#tab-" + selectedView).focus({ preventScroll: true });
}

function hasCurrentWorkScopeContract() {
  const navigation = state.overview?.navigation;
  if (!Array.isArray(navigation?.projects) || !Array.isArray(navigation?.controllers)) return false;
  return navigation.projects.every((project) => typeof project.id === "string" && typeof project.archived === "boolean" && typeof project.visibility === "string" && typeof project.project_eligibility === "string" && Array.isArray(project.ctrl_ids))
    && navigation.controllers.every((controller) => typeof controller.id === "string" && typeof controller.project_id === "string" && typeof controller.archived === "boolean" && typeof controller.visibility === "string");
}

function currentWorkProjects() {
  const navigation = state.overview?.navigation;
  if (!hasCurrentWorkScopeContract()) return [];
  return navigation.projects.filter((project) => project.visibility === "visible" && project.archived === false && project.project_eligibility === "swarm_ctrl" && Array.isArray(project.ctrl_ids) && project.ctrl_ids.length);
}

function currentWorkControllers() {
  const navigation = state.overview?.navigation;
  if (!hasCurrentWorkScopeContract()) return [];
  const allowedControllerProjects = new Map(currentWorkProjects().flatMap((project) => project.ctrl_ids.map((ctrlId) => [ctrlId, project.id])));
  const nodeById = new Map((state.overview?.nodes || []).map((node) => [node.id, node]));
  return navigation.controllers
    .filter((controller) => controller.visibility === "visible" && controller.archived === false && allowedControllerProjects.get(controller.id) === controller.project_id)
    .map((controller) => nodeById.get(controller.id))
    .filter(Boolean);
}

function currentWorkScopeUnavailable() {
  if (!hasCurrentWorkScopeContract()) return true;
  const expectedControllerIds = currentWorkProjects().flatMap((project) => project.ctrl_ids);
  const resolvedControllerIds = new Set(currentWorkControllers().map((controller) => controller.id));
  return new Set(expectedControllerIds).size !== expectedControllerIds.length || expectedControllerIds.some((ctrlId) => !resolvedControllerIds.has(ctrlId));
}

function publicLabel(value, fallback = "Untitled") {
  const label = String(value || "")
    .replace(/\blocalhost\b/gi, "console")
    .replace(/\bconsole(?:\s+console)+\b/gi, "console")
    .replace(/\s+/g, " ")
    .trim();
  return label || fallback;
}

function ctrlLabel(ctrl) {
  const label = ctrl.artifact || ctrl.title || ctrl.id;
  return publicLabel(String(label).replace(/^[^A-Za-z0-9]*CTRL\s*-\s*/i, ""), "Untitled goal");
}

function historicalProjects() {
  const summaries = new Map((state.overview?.projects || []).map((project) => [project.id, project]));
  const source = Array.isArray(state.overview?.navigation?.projects) ? state.overview.navigation.projects : (state.overview?.projects || []);
  return source.map((project) => ({ ...(summaries.get(project.id) || {}), ...project }));
}

function historicalControllers() {
  const summaries = new Map((state.overview?.controllers || []).map((controller) => [controller.id, controller]));
  const nodes = new Map((state.overview?.nodes || []).map((node) => [node.id, node]));
  const source = Array.isArray(state.overview?.navigation?.controllers) ? state.overview.navigation.controllers : (state.overview?.controllers || []);
  return source.map((controller) => ({ ...(summaries.get(controller.id) || {}), ...(nodes.get(controller.id) || {}), ...controller }));
}

function projectGroups() {
  const projects = historicalProjects().filter((project) => !/^https?[-_:]/i.test(String(project.name || "")));
  const labels = new Map(projects.map((project) => [project.id, publicLabel(project.goal_label || project.name, "Untitled project")]));
  const groups = new Map(projects.map((project) => [project.id, { id: project.id, label: labels.get(project.id), controllers: [], standalone: false }]));
  historicalControllers().forEach((ctrl) => {
    const id = ctrl.project_id || "ctrl:" + ctrl.id;
    const group = groups.get(id) || { id, label: ctrl.project_id ? (labels.get(ctrl.project_id) || publicLabel(ctrl.project, "Untitled project")) : ctrlLabel(ctrl), controllers: [], standalone: !ctrl.project_id };
    group.controllers.push(ctrl);
    groups.set(id, group);
  });
  return [...groups.values()].sort((a, b) => a.label.localeCompare(b.label));
}

function scopeLabel() {
  if (state.projectId === "all") return "All projects";
  const group = projectGroups().find((item) => item.id === state.projectId);
  const ctrl = historicalControllers().find((item) => item.id === state.ctrlId);
  return ctrl && state.ctrlId ? ctrlLabel(ctrl) : (group?.label || "All projects");
}

function renderProjectNavigation() {
  const groups = projectGroups().filter((group) => !group.standalone);
  if (state.projectId !== "all" && !groups.some((group) => group.id === state.projectId)) {
    state.projectId = "all";
    state.ctrlId = "";
  }
  const entries = ['<button class="project-scope-button ' + (state.projectId === "all" ? "is-selected" : "") + '" data-project-id="all" type="button" aria-pressed="' + (state.projectId === "all") + '"><span aria-hidden="true">◇</span>All projects</button>'];
  groups.forEach((group) => {
    const current = state.projectId === group.id && !state.ctrlId;
    entries.push('<button class="project-scope-button ' + (current ? "is-selected" : "") + '" data-project-id="' + escapeHTML(group.id) + '" type="button" aria-pressed="' + current + '"><span class="scope-dot is-live" aria-hidden="true"></span>' + escapeHTML(group.label) + '</button>');
  });
  $("#project-navigation").innerHTML = entries.join("");
  $("#scope-context strong").textContent = scopeLabel();
}

function drawLine(svg, values, color) {
  const box = svg.viewBox?.baseVal;
  const width = box?.width || 320;
  const height = box?.height || 138;
  const bottom = height - 10;
  const middle = Math.round(height / 2);
  const top = Math.min(28, Math.max(8, Math.round(height * .2)));
  const series = values.length ? values : [0, 0];
  const high = Math.max(1, ...series);
  const points = series.map((value, index) => {
    const x = series.length === 1 ? width / 2 : (index / (series.length - 1)) * width;
    const y = bottom - ((Number(value) || 0) / high) * Math.max(12, height - top - 10);
    return x.toFixed(1) + "," + y.toFixed(1);
  }).join(" ");
  svg.innerHTML = '<path class="chart-grid" d="M0 ' + bottom + 'H' + width + ' M0 ' + middle + 'H' + width + ' M0 ' + top + 'H' + width + '"/><polyline class="chart-area" points="0,' + height + ' ' + points + ' ' + width + ',' + height + '"/><polyline class="chart-line" stroke="' + color + '" points="' + points + '"/>';
}

function renderMetrics(nodes) {
  const total = nodes.length;
  const complete = nodes.filter((node) => ["done", "archived"].includes(String(node.status).toLowerCase())).length;
  const percent = total ? Math.round((complete / total) * 100) : 0;
  $("#progress-value").textContent = total ? String(percent) + "%" : "—";
  $("#progress-note").textContent = total ? String(complete) + " of " + String(total) + " tasks complete" : "Waiting for tasks";
  $("#progress-detail").textContent = total ? String(Math.max(0, total - complete)) + " remaining" : "No tasks yet";
  $("#progress-bar").style.width = String(percent) + "%";

  const activeForecasts = nodes.map((node) => node.eta || {}).filter((eta) => eta.status !== "complete" && eta.eta_end_ms);
  const forecast = activeForecasts.sort((a, b) => Number(a.eta_end_ms) - Number(b.eta_end_ms))[0];
  const confidence = Math.max(0, Math.min(100, Number(forecast?.confidence) || 0));
  $("#forecast-value").textContent = forecast ? formatEta(forecast.eta_end_ms) : "—";
  $("#forecast-note").textContent = forecast?.status ? humanize(forecast.status) : "No active forecast";
  $("#confidence-bar").style.width = String(confidence) + "%";
  $("#confidence-detail").textContent = forecast ? String(confidence) + "% confidence · updated " + formatRelative(forecast.last_calculated_at_ms) : "Confidence unavailable";

  const risks = nodes.filter(needsAttention);
  $("#drift-value").textContent = risks.length ? String(risks.length) + " at risk" : "On track";
  $("#drift-value").className = risks.length ? "risk-text" : "healthy-text";
  $("#drift-note").textContent = risks.length ? String(risks.length) + " need attention" : "No forecast drift detected";
  $("#drift-detail").textContent = total ? String(total - risks.length) + " without a risk signal" : "No drift signal yet";

  const risk = risks[0];
  $("#risk-value").textContent = risk?.artifact || "No active risk";
  $("#risk-note").textContent = risk ? humanize(attentionStatus(risk)) + " · active " + formatRelative(risk.updated_at) : "Everything looks clear";
  const action = $("#risk-action");
  action.hidden = !risk;
  action.dataset.taskId = risk?.id || "";
}

function isSubagent(node) {
  if (node?.is_subagent === true) return true;
  const surface = String(node?.surface ?? node?.thread_source ?? "").trim().toLowerCase();
  return ["subagent", "internal_subagent"].includes(surface);
}

function taskTree(nodes) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const parent = new Map();
  const children = new Map();
  const linkedParent = new Map((state.overview?.links || []).map((link) => [link.target, link.source]));
  nodes.forEach((node) => {
    const candidate = node.parent_id || linkedParent.get(node.id);
    if (!candidate || candidate === node.id || !byId.has(candidate)) return;
    parent.set(node.id, candidate);
    const list = children.get(candidate) || [];
    list.push(node);
    children.set(candidate, list);
  });
  return { byId, parent, children };
}

function subagentDescendants(nodeId, tree) {
  const descendants = [];
  const pending = [...(tree.children.get(nodeId) || [])];
  while (pending.length) {
    const node = pending.shift();
    if (isSubagent(node)) descendants.push(node);
    pending.unshift(...(tree.children.get(node.id) || []));
  }
  return descendants;
}

function subagentToggle(node, count) {
  if (!count) return "";
  const label = count + " subagent" + (count === 1 ? "" : "s");
  return '<button class="subagent-toggle" data-subagent-toggle="' + escapeHTML(node.id) + '" type="button" aria-expanded="false">＋ <span>Show ' + label + '</span></button>';
}

function renderTaskRow(node, tree, { subagent = false, depth = 0, hidden = false } = {}) {
  const eta = node.eta || {};
  const proof = node.proof_snapshot || {};
  const status = statusLabel(node);
  const etaLabel = eta.status === "complete" ? "Complete" : (eta.eta_end_ms ? formatEta(eta.eta_end_ms) : "Unforecast");
  const descendants = subagentDescendants(node.id, tree);
  const rowClass = subagent ? "task-row subagent-row" : "task-row";
  const parentAttribute = subagent && tree.parent.has(node.id) ? ' data-subagent-parent="' + escapeHTML(tree.parent.get(node.id)) + '"' : "";
  const indent = subagent ? '<span class="subagent-indent" aria-hidden="true" style="--subagent-depth:' + depth + '">↳</span>' : "";
  const label = escapeHTML(node.artifact || node.title || node.id);
  const worker = escapeHTML(node.worker || node.worker_role || node.role_label || "Unassigned");
  const rowId = subagent ? ' id="subagents-' + escapeHTML(node.id) + '"' : "";
  return '<tr class="' + rowClass + '" data-task-id="' + escapeHTML(node.id) + '" data-subagent-depth="' + depth + '"' + parentAttribute + rowId + (hidden ? " hidden" : "") + '><td>' + indent + '<strong>' + label + '</strong><small>' + (subagent ? "Subagent · " : "") + escapeHTML(node.project || "Task") + '</small>' + subagentToggle(node, descendants.length) + '</td><td>' + worker + '</td><td><span class="state-pill ' + status[1] + '">' + status[0] + '</span></td><td><strong>' + escapeHTML(etaLabel) + '</strong><small>' + escapeHTML(eta.status ? humanize(eta.status) : "No forecast") + '</small></td><td>' + (eta.confidence == null ? "—" : escapeHTML(eta.confidence) + "%") + '</td><td><span class="activity-dot ' + status[1] + '" aria-hidden="true"></span>' + escapeHTML(formatRelative(node.updated_at || node.generated_at)) + '</td><td><span class="proof-state ' + (proof.available ? "" : "is-muted") + '">' + (proof.available ? "Available" : "—") + "</span></td></tr>";
}

function renderSubagentRows(node, tree, depth = 1) {
  return (tree.children.get(node.id) || []).filter(isSubagent).map((child) => renderTaskRow(child, tree, { subagent: true, depth, hidden: true }) + renderSubagentRows(child, tree, depth + 1)).join("");
}

function renderTable(nodes) {
  $("#plan-count").textContent = String(nodes.length) + " task" + (nodes.length === 1 ? "" : "s");
  $("#task-empty").hidden = nodes.length > 0;
  const tree = taskTree(nodes);
  const roots = nodes.filter((node) => !isSubagent(node) || !tree.parent.has(node.id));
  $("#task-table").innerHTML = roots.map((node) => renderTaskRow(node, tree) + (isSubagent(node) ? "" : renderSubagentRows(node, tree))).join("");
}

function setSubagentVisibility(parentId, visible, visited = new Set()) {
  if (visited.has(parentId)) return;
  visited.add(parentId);
  const rows = $$('[data-subagent-parent="' + CSS.escape(parentId) + '"]', $("#task-table"));
  rows.forEach((row) => {
    row.hidden = !visible;
    if (!visible) {
      row.querySelectorAll("[data-subagent-toggle]").forEach((button) => {
        button.setAttribute("aria-expanded", "false");
        const text = button.querySelector("span");
        if (text) text.textContent = text.textContent.replace(/^Hide /, "Show ");
      });
      setSubagentVisibility(row.dataset.taskId, false, visited);
    }
  });
}

function proofMediaURL(item) {
  return "/api/proof-media/" + encodeURIComponent(item.evidence_id) + "?digest=" + encodeURIComponent(item.digest);
}

function proofIdentity(item) {
  const evidenceId = String(item?.evidence_id || "").trim();
  const digest = String(item?.digest || "").trim().toLowerCase();
  return evidenceId && digest ? evidenceId + "|" + digest : "";
}

function dedupeProofItems(items) {
  const seen = new Set();
  return (Array.isArray(items) ? items : []).filter((item) => {
    const identity = proofIdentity(item);
    if (!identity || seen.has(identity)) return false;
    seen.add(identity);
    return true;
  });
}

function proofCollectionKey(projectId = state.projectId) {
  return projectId !== "all" && !projectId.startsWith("ctrl:") ? projectId : "all";
}

function currentProofItems() {
  return state.proofCollections.get(proofCollectionKey()) || [];
}

function currentProofStatus() {
  return state.proofStatuses.get(proofCollectionKey()) || "idle";
}

function evidenceImagesFor(nodes) {
  const images = dedupeProofItems(currentProofItems()).filter((item) => String(item.media_type || "").startsWith("image/"));
  if (state.projectId !== "all" && !state.projectId.startsWith("ctrl:")) {
    return images.filter((item) => !item.project_id || item.project_id === state.projectId);
  }
  if (state.ctrlId) {
    const allowed = new Set(nodes.map((node) => node.id));
    return images.filter((item) => allowed.has(item.task_id));
  }
  return images;
}

function renderEvidenceLightbox() {
  const items = state.evidenceImages;
  const image = $("#evidence-lightbox-image");
  const empty = $("#evidence-lightbox-empty");
  const failed = $("#evidence-lightbox-failed");
  const previous = $("#evidence-lightbox-previous");
  const next = $("#evidence-lightbox-next");
  const pagePrevious = $("#evidence-page-previous");
  const pageNext = $("#evidence-page-next");
  const pageStatus = $("#evidence-page-status");
  if (!items.length) {
    image.hidden = true;
    empty.hidden = false;
    failed.hidden = true;
    $("#evidence-lightbox-caption").textContent = "No image selected";
    $("#evidence-lightbox-thumbnails").innerHTML = "";
    pageStatus.textContent = "No thumbnails";
    previous.disabled = true;
    next.disabled = true;
    pagePrevious.disabled = true;
    pageNext.disabled = true;
    return;
  }
  state.evidenceIndex = Math.min(Math.max(0, state.evidenceIndex), items.length - 1);
  const item = items[state.evidenceIndex];
  image.hidden = false;
  empty.hidden = true;
  failed.hidden = true;
  image.src = proofMediaURL(item);
  image.alt = item.caption || "Evidence image";
  $("#evidence-lightbox-caption").textContent = String(state.evidenceIndex + 1) + " of " + String(items.length);
  previous.disabled = state.evidenceIndex === 0;
  next.disabled = state.evidenceIndex === items.length - 1;
  const page = Math.floor(state.evidenceIndex / EVIDENCE_THUMBNAIL_PAGE_SIZE);
  const start = page * EVIDENCE_THUMBNAIL_PAGE_SIZE;
  const end = Math.min(items.length, start + EVIDENCE_THUMBNAIL_PAGE_SIZE);
  $("#evidence-lightbox-thumbnails").innerHTML = items.slice(start, end).map((entry, offset) => {
    const index = start + offset;
    return (
    '<button class="evidence-lightbox-thumbnail' + (index === state.evidenceIndex ? " is-selected" : "") +
    '" type="button" data-evidence-thumbnail="' + String(index) + '" data-evidence-id="' + escapeHTML(entry.evidence_id) +
    '" data-evidence-digest="' + escapeHTML(entry.digest) + '" aria-current="' + String(index === state.evidenceIndex) +
    '" aria-label="Show image ' + String(index + 1) + ': ' + escapeHTML(entry.caption || "Evidence image") +
    '"><img loading="lazy" decoding="async" src="' + proofMediaURL(entry) + '" alt=""></button>'
    );
  }).join("");
  pageStatus.textContent = "Images " + String(start + 1) + "–" + String(end) + " of " + String(items.length);
  pagePrevious.disabled = start === 0;
  pageNext.disabled = end >= items.length;
  const dialog = $("#evidence-lightbox");
  if (!dialog.open) dialog.showModal();
}

function openEvidenceLightbox(index, trigger) {
  state.evidenceIndex = Number.isFinite(index) ? index : 0;
  state.evidenceTrigger = trigger || null;
  renderEvidenceLightbox();
}

function closeEvidenceLightbox() {
  const dialog = $("#evidence-lightbox");
  if (dialog.open) dialog.close();
}

function renderProof(nodes) {
  const images = evidenceImagesFor(nodes);
  state.evidenceImages = images;
  if ($("#evidence-lightbox").open) renderEvidenceLightbox();
  $("#proof-count").textContent = String(images.length);
  $("#proof-count").title = currentProofStatus() === "stale" ? "Showing the last received evidence" : "";
  const previews = images.slice(0, 4);
  const remaining = Math.max(0, images.length - previews.length);
  const tiles = previews.map((item, index) =>
    '<button class="proof-tile" type="button" data-evidence-open="' + String(index) +
    '" data-evidence-id="' + escapeHTML(item.evidence_id) + '" data-evidence-digest="' + escapeHTML(item.digest) +
    '" aria-label="Open evidence image: ' + escapeHTML(item.caption || "Image evidence") +
    '"><img loading="lazy" decoding="async" src="' + proofMediaURL(item) + '" alt=""></button>'
  ).join("");
  const more = remaining ? '<button class="proof-tile proof-more" type="button" data-evidence-open="4" aria-label="Open ' + String(remaining) + ' more images; ' + String(images.length) + ' images in this gallery">+' + String(remaining) + '</button>' : '';
  $("#proof-feed").innerHTML = images.length ? tiles + more : '<p class="empty-state">No image proof yet.</p>';
}

function renderBurnRate() {
  const burn = state.overview?.analytics?.burn_rate || {};
  const history = burn.history || state.overview?.token_history || [];
  const values = history.map((item) => Number(item.delta_tokens) || 0);
  const current = Number(burn.tokens_per_minute ?? values.at(-1) ?? 0);
  const allProjects = state.projectId === "all" && !state.ctrlId;
  $("#burn-current").textContent = allProjects && history.length ? compactNumber(current) + " / min" : "—";
  $("#burn-note").textContent = allProjects ? (history.length ? "Live across all projects" : "Waiting for activity") : "Select all projects to see the live rate";
  drawLine($("#burn-chart"), values, "#46dfd0");
}

function observedTasks(nodes) {
  return nodes.filter((node) => !isSubagent(node) && String(node.role || "").toLowerCase() !== "ctrl");
}

function authoritativeProgress(projectId, ctrlId = "") {
  const summaries = state.overview?.progress || {};
  if (ctrlId) return summaries.controllers?.[ctrlId] ?? null;
  if (projectId) return summaries.projects?.[projectId] ?? null;
  return null;
}

function progressPresentation(summary) {
  const measured = summary?.progress;
  const percent = typeof measured?.percent === "number" ? measured.percent : Number.NaN;
  const validPercent = Number.isFinite(percent) ? Math.max(0, Math.min(100, percent)) : null;
  const freshness = summary?.freshness || {};
  const freshnessLabel = freshness.state === "fresh" ? "Fresh" : freshness.state === "stale" ? "Stale" : "Unmeasured";
  const observed = freshness.observed_at_ms ? formatRelative(freshness.observed_at_ms) : "No receipt time";
  return {
    percent: validPercent,
    display: validPercent == null ? "Unmeasured" : String(validPercent) + "%",
    freshness: freshnessLabel + (freshness.observed_at_ms ? " · " + observed : ""),
  };
}

function overviewCards(nodes) {
  if (currentWorkScopeUnavailable()) return [];
  const projects = currentWorkProjects();
  const controllers = currentWorkControllers();
  const cardForController = (project, ctrl, multiple) => ({
    label: publicLabel(project.goal_label || project.name, "Untitled project") + (multiple ? " · " + ctrlLabel(ctrl) : ""),
    projectId: project.id,
    ctrlId: ctrl.id,
    nodes: nodes.filter((node) => node.id === ctrl.id || (node.controller_ids || []).includes(ctrl.id)),
  });
  const cardsForProject = (project) => {
    const projectControllers = controllers.filter((ctrl) => project.ctrl_ids.includes(ctrl.id));
    return projectControllers.map((ctrl) => cardForController(project, ctrl, projectControllers.length > 1));
  };
  if (state.ctrlId) {
    const project = projects.find((item) => item.id === state.projectId && item.ctrl_ids.includes(state.ctrlId));
    const ctrl = controllers.find((item) => item.id === state.ctrlId);
    return project && ctrl ? [cardForController(project, ctrl, false)] : [];
  }
  if (state.projectId !== "all") {
    const project = projects.find((item) => item.id === state.projectId);
    return project ? cardsForProject(project) : [];
  }
  return projects.flatMap(cardsForProject);
}

function latestReceipt(nodes) {
  const allowed = new Set(nodes.map((node) => node.id));
  return currentProofItems().find((item) => allowed.has(item.task_id)) || null;
}

function formatDuration(value) {
  const minutes = Math.max(0, Math.round(Number(value) / 60000));
  if (minutes < 60) return String(minutes) + "m";
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return String(hours) + "h" + (remainder ? " " + String(remainder) + "m" : "");
}

function forecastSummary(node) {
  const eta = node?.eta || {};
  const current = eta.current || eta;
  const end = Number(current.eta_end_ms);
  if (!Number.isFinite(end) || !end) return '';
  const remaining = current.status === 'complete' ? 'Complete' : formatDuration(Math.max(0, end - Date.now())) + ' remaining';
  const baseline = Number(eta.baseline_eta_end_ms);
  const drift = Number(eta.delta_from_baseline_ms);
  const revised = Number(eta.revision) > 1 && Number.isFinite(drift) && drift !== 0;
  const previous = eta.previous && typeof eta.previous === 'object' ? eta.previous : null;
  const details = baseline || previous || eta.last_material_heartbeat_at_ms || eta.short_reason || eta.claim_limit
    ? '<details class="forecast-details"><summary>Forecast details</summary><dl>' +
      (baseline ? '<div><dt>Original forecast</dt><dd>' + escapeHTML(formatEta(baseline)) + '</dd></div>' : '') +
      (previous?.eta_end_ms ? '<div><dt>Previous revision</dt><dd>' + escapeHTML(formatEta(previous.eta_end_ms)) + '</dd></div>' : '') +
      (eta.short_reason ? '<div><dt>Reason</dt><dd>' + escapeHTML(eta.short_reason) + '</dd></div>' : '') +
      (eta.last_material_heartbeat_at_ms ? '<div><dt>Last material update</dt><dd>' + escapeHTML(formatRelative(eta.last_material_heartbeat_at_ms)) + '</dd></div>' : '') +
      (eta.claim_limit ? '<div><dt>Claim limit</dt><dd>' + escapeHTML(eta.claim_limit) + '</dd></div>' : '') +
      '</dl></details>' : '';
  return '<div class="forecast-summary"><strong>' + escapeHTML(remaining) + (revised ? ' <span>Changed</span>' : '') + '</strong><small>' + escapeHTML(String(current.confidence ?? eta.confidence ?? '—') + '% confidence' + (current.eta_start_ms ? ' · range ' + formatEta(current.eta_start_ms) + '–' + formatEta(end) : '')) + (revised ? ' · ' + (drift > 0 ? '+' : '−') + formatDuration(Math.abs(drift)) + ' from original' : '') + '</small>' + details + '</div>';
}

function renderEvidenceGallery(nodes, gallerySelector, noteSelector, limit = 6) {
  const images = evidenceImagesFor(nodes);
  state.evidenceImages = images;
  if ($("#evidence-lightbox").open) renderEvidenceLightbox();
  const proofStatus = currentProofStatus();
  const retained = proofStatus === "stale" ? " · last received" : "";
  $(noteSelector).textContent = images.length ? String(images.length) + " recent image" + (images.length === 1 ? "" : "s") + retained : (proofStatus === "unavailable" ? "Evidence unavailable" : "No images received");
  const previews = images.slice(0, limit);
  const remaining = Math.max(0, images.length - previews.length);
  const previewTiles = previews.map((item, index) =>
    '<button class="evidence-gallery-item" type="button" data-evidence-open="' + String(index) +
    '" data-evidence-id="' + escapeHTML(item.evidence_id) + '" data-evidence-digest="' + escapeHTML(item.digest) +
    '" aria-label="Open evidence image: ' + escapeHTML(item.caption || "Image evidence") +
    '"><img loading="lazy" decoding="async" src="' + proofMediaURL(item) + '" alt=""></button>'
  ).join("");
  const moreTile = remaining
    ? '<button class="evidence-gallery-more" type="button" data-evidence-open="' + String(previews.length) +
      '" data-evidence-more="' + String(remaining) + '" aria-label="Open ' + String(remaining) + ' more images; ' + String(images.length) +
      ' images in this gallery">+' + String(remaining) + " more</button>"
    : "";
  $(gallerySelector).innerHTML = images.length ? previewTiles + moreTile : '<p class="empty-state">Images appear here when they are received.</p>';
}

function usageRequestKey(projectId = state.projectId, ctrlId = state.ctrlId, hours = state.usageWindowHours) {
  return projectId + "|" + ctrlId + "|" + String(hours);
}

function usageSeries(source = state.usageHistory || {}) {
  return source.history || source.items || [];
}

function downsampleSeries(values, maximum = 96) {
  if (values.length <= maximum) return values;
  const step = (values.length - 1) / (maximum - 1);
  return Array.from({ length: maximum }, (_, index) => values[Math.round(index * step)]);
}

function usageRateSeries(series) {
  const rates = [];
  for (let index = 1; index < series.length; index += 1) {
    const previousAt = Number(series[index - 1]?.bucket_ms ?? series[index - 1]?.observed_at_ms);
    const currentAt = Number(series[index]?.bucket_ms ?? series[index]?.observed_at_ms);
    const elapsedMinutes = (currentAt - previousAt) / 60000;
    const tokens = Number(series[index]?.delta_tokens ?? series[index]?.tokens ?? series[index]?.value);
    if (Number.isFinite(elapsedMinutes) && elapsedMinutes > 0 && Number.isFinite(tokens)) rates.push(Math.max(0, tokens / elapsedMinutes));
  }
  return rates;
}

function renderUsage() {
  const scopeMatches = state.usageScopeKey === usageRequestKey();
  const source = scopeMatches ? (state.usageHistory || {}) : {};
  const series = usageSeries(source);
  const total = Number(source.total_tokens ?? source.tokens ?? source.total ?? source.analytics?.tokens);
  const observed = Number(source.coverage?.observed_threads);
  const expected = Number(source.coverage?.expected_threads);
  const coverage = Number.isFinite(observed) && Number.isFinite(expected) ? String(observed) + ' of ' + String(expected) + ' observed' : '';
  const values = series.map((item) => Number(item.delta_tokens ?? item.tokens ?? item.value) || 0);
  const rates = usageRateSeries(series);
  const reportedRate = Number(source.tokens_per_minute ?? source.usage_now?.tokens_per_minute ?? source.usage_now?.rate);
  const currentRate = Number.isFinite(reportedRate) ? Math.max(0, reportedRate) : rates.at(-1);
  const windowLabel = USAGE_WINDOW_LABELS[state.usageWindowHours] || String(state.usageWindowHours) + "h";
  $("#usage-heading").textContent = "Tokens · " + windowLabel;
  $("#usage-total").textContent = Number.isFinite(total) ? compactNumber(total) : "—";
  $("#usage-rate").textContent = Number.isFinite(currentRate) ? compactNumber(currentRate) + " / min" : "—";
  $("#usage-range").textContent = values.length ? 'Range ' + compactNumber(Math.min(...values)) + '–' + compactNumber(Math.max(...values)) + ' per sample' : 'No historical range';
  $("#usage-note").textContent = !scopeMatches || state.usageStatus === "loading" ? "Loading usage history" : state.usageStatus === "error" ? (state.usageError || "Usage history unavailable") : source.status === 'no_data' ? 'No persisted usage in this scope' : source.status === 'partial' ? ('Partial coverage' + (coverage ? ' · ' + coverage : '')) : source.status === 'ok' ? ('Complete coverage' + (coverage ? ' · ' + coverage : '')) : (series.length ? 'Usage status unavailable' : 'No recent history');
  $$('[data-usage-hours]').forEach((button) => {
    const selected = Number(button.dataset.usageHours) === state.usageWindowHours;
    button.classList.toggle('is-selected', selected);
    button.setAttribute('aria-pressed', String(selected));
  });
  drawLine($("#usage-sparkline"), downsampleSeries(values), "#ff9c3d");
  drawLine($("#usage-rate-sparkline"), downsampleSeries(rates), "#46dfd0");
}

function selectedProgressProjectId() {
  return state.projectId !== "all" && !state.projectId.startsWith("ctrl:") ? state.projectId : "";
}

function progressEventIdentity(item) {
  const eventId = String(item?.event_id || "").trim();
  const digest = String(item?.event_digest || item?.digest || "").trim();
  return eventId && digest ? eventId + "|" + digest : eventId || (String(item?.event_seq || "") + "|" + String(item?.observed_at_ms || ""));
}

function progressFeedItems() {
  const seen = new Set();
  return (state.projectProgressFeed?.items || []).filter((item) => {
    const identity = progressEventIdentity(item);
    const sentence = String(item?.material_update_sentence || "").trim();
    if (!identity || !sentence || seen.has(identity)) return false;
    seen.add(identity);
    return true;
  }).sort((a, b) => Number(b.event_seq || b.observed_at_ms || 0) - Number(a.event_seq || a.observed_at_ms || 0));
}

function progressFeedFlag(item) {
  const flags = Array.isArray(item?.flags) ? item.flags.map((flag) => String(flag).toLowerCase()) : [];
  if (flags.some((flag) => flag.includes("scope"))) return ["△", "Scope changed"];
  if (flags.some((flag) => flag.includes("eta") || flag.includes("stale"))) return ["!", "ETA or freshness needs attention"];
  if (flags.some((flag) => flag.includes("token"))) return ["↑", "Token use needs attention"];
  return ["", ""];
}

function renderProjectProgressFeed() {
  const section = $("#project-progress-section");
  const projectId = selectedProgressProjectId();
  if (!projectId || state.projectProgressProjectId !== projectId || state.projectProgressFeed?.enabled === false) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  const items = progressFeedItems();
  const status = $("#project-progress-status");
  status.textContent = state.projectProgressStatus === "stale" ? "Last received · reconnect to refresh" : state.projectProgressStatus === "unavailable" ? "Updates unavailable" : items.length ? String(items.length) + " latest update" + (items.length === 1 ? "" : "s") : "No material updates yet";
  $("#project-progress-feed").innerHTML = items.length ? items.map((item) => {
    const [icon, label] = progressFeedFlag(item);
    const owner = item.owner_id || item.task_id || item.block_id || "Project";
    return '<li data-progress-event-id="' + escapeHTML(item.event_id || progressEventIdentity(item)) + '"><time datetime="' + escapeHTML(new Date(Number(item.observed_at_ms) || 0).toISOString()) + '">' + escapeHTML(formatRelative(item.observed_at_ms)) + '</time><strong>' + escapeHTML(owner) + '</strong><span>' + escapeHTML(item.material_update_sentence) + '</span>' + (icon ? '<i role="img" aria-label="' + escapeHTML(label) + '" title="' + escapeHTML(label) + '">' + escapeHTML(icon) + '</i>' : '') + '</li>';
  }).join("") : '<li class="empty-state">No material project updates yet.</li>';
}

function renderHealth(nodes, stateSelector, noteSelector) {
  const lanes = nodes.filter((node) => !isSubagent(node));
  const attention = lanes.filter(needsAttention);
  $(stateSelector).textContent = attention.length ? 'Needs attention' : (lanes.length ? 'On track' : 'Waiting for work');
  $(stateSelector).className = attention.length ? 'risk-text' : 'healthy-text';
  $(noteSelector).textContent = attention.length ? String(attention.length) + ' visible lane' + (attention.length === 1 ? ' needs attention' : 's need attention') : (lanes.length ? String(lanes.length) + ' visible lanes without an attention signal' : 'No visible lanes');
}

function renderOverviewHealth(nodes) {
  renderHealth(nodes, "#overview-monitoring-health-state", "#overview-monitoring-health-note");
}

function renderOverviewProjectCards(nodes) {
  const scopeAvailable = !currentWorkScopeUnavailable();
  const cards = overviewCards(nodes);
  const tree = taskTree(nodes);
  const allProjects = state.projectId === "all" && !state.ctrlId;
  const scopedCards = cards.filter((card) => card.nodes.length);
  const visibleCards = allProjects ? scopedCards.slice(0, 5) : scopedCards;
  const moreCards = allProjects ? scopedCards.slice(5) : [];
  const renderCard = (card) => {
    const tasks = observedTasks(card.nodes);
    const progress = progressPresentation(authoritativeProgress(card.projectId, card.ctrlId));
    const blocker = tasks.find(needsAttention);
    const receipt = latestReceipt(card.nodes);
    const primary = card.nodes.find((node) => node.id === card.ctrlId) || tasks[0];
    const current = tasks.find((task) => !["done", "archived"].includes(String(task.status).toLowerCase())) || primary;
    const stateLabel = primary ? statusLabel(primary)[0] : "No task state";
    const ringClass = needsAttention(primary) ? "is-attention" : (statusLabel(primary || {})[1] || "is-pending");
    const subagents = card.ctrlId ? subagentDescendants(card.ctrlId, tree) : [];
    const subagentDisclosure = subagents.length ? '<details class="overview-subagents" data-overview-subagents="' + escapeHTML(card.ctrlId) + '"><summary>Subagents <span>' + subagents.length + '</span></summary><ul>' + subagents.map((node) => '<li><strong>' + escapeHTML(node.artifact || node.title || node.id) + '</strong><span>' + escapeHTML(statusLabel(node)[0]) + '</span></li>').join('') + '</ul></details>' : '<span class="overview-subagent-empty">No subagents</span>';
    return '<article class="overview-project-card panel"><div class="overview-progress-ring ' + ringClass + '" style="--progress:' + (progress.percent == null ? 0 : progress.percent) + '%" aria-label="' + escapeHTML(progress.display + ' receipt-backed progress · ' + progress.freshness) + '"><strong>' + escapeHTML(progress.display) + '</strong><span>' + escapeHTML(progress.freshness) + '</span></div><div class="overview-project-main"><p class="eyebrow">' + escapeHTML(stateLabel) + '</p><h3>' + escapeHTML(card.label) + '</h3><p>' + escapeHTML(current?.artifact || "No current task observed") + '</p></div><dl class="overview-project-facts"><div><dt>Current work</dt><dd>' + escapeHTML(current?.artifact || "None observed") + '</dd></div><div><dt>Latest receipt</dt><dd>' + escapeHTML(receipt?.caption || receipt?.kind || "None received") + '</dd></div><div><dt>Blocker</dt><dd class="' + (blocker ? 'risk-text' : '') + '">' + escapeHTML(blocker?.artifact || "None observed") + '</dd></div></dl><div class="overview-project-subagents">' + subagentDisclosure + '</div></article>';
  };
  $("#overview-summary").textContent = allProjects
    ? (scopedCards.length ? String(scopedCards.length) + " project scope" + (scopedCards.length === 1 ? "" : "s") : "No classified Current Work")
    : (scopedCards.length ? "Current scope" : "No classified Current Work");
  const empty = !scopeAvailable
    ? '<p class="empty-state overview-empty">Current Work needs host-reported CTRL classification. Dashboard still shows task history.</p>'
    : allProjects
      ? '<p class="empty-state overview-empty">No classified Current Work is available.</p>'
      : '<p class="empty-state overview-empty">No classified Current Work is available in ' + escapeHTML(scopeLabel()) + '.</p>';
  $("#overview-project-cards").innerHTML = visibleCards.length
    ? visibleCards.map(renderCard).join("") + (moreCards.length ? '<details class="overview-more"><summary>' + String(moreCards.length) + ' more project scope' + (moreCards.length === 1 ? '' : 's') + '</summary><div>' + moreCards.map(renderCard).join("") + '</div></details>' : '')
    : empty;
}

function renderOverview() {
  const nodes = scopedNodes();
  renderOverviewProjectCards(nodes);
  renderEvidenceGallery(nodes, "#overview-evidence-gallery", "#overview-evidence-note", 4);
  renderUsage();
  renderProjectProgressFeed();
  renderOverviewHealth(nodes);
  $("#sync-time").textContent = state.overview?.generated_at ? "Updated " + formatRelative(state.overview.generated_at) : "Ready";
}

function renderDashboard() {
  const nodes = scopedNodes();
  renderMetrics(nodes);
  renderTable(nodes);
  renderProof(nodes);
  renderBurnRate();
  renderOverviewDiagnostics();
}

function renderHierarchy() {
  const nodes = scopedNodes();
  const tree = taskTree(nodes);
  const groups = new Map();
  nodes.filter((node) => !isSubagent(node)).forEach((node) => {
    const owner = node.controller_ids?.[0] || node.worker || node.worker_role || node.role_label || "Unassigned";
    const list = groups.get(owner) || [];
    list.push(node); groups.set(owner, list);
  });
  $("#hierarchy-list").innerHTML = groups.size ? [...groups.entries()].map(([owner, tasks]) => {
    const current = tasks.find((task) => !["done", "archived"].includes(String(task.status).toLowerCase())) || tasks[0];
    const extra = tasks.filter((task) => task.id !== current.id);
    const stalled = needsAttention(current);
    const status = statusLabel(current);
    const subagents = subagentDescendants(current.id, tree);
    const subagentMeta = subagents.length ? '<span class="subagent-count">' + subagents.length + ' subagent' + (subagents.length === 1 ? '' : 's') + '</span>' : '';
    const progress = progressPresentation(authoritativeProgress(current.project_id, state.overview?.progress?.controllers?.[owner] ? owner : ""));
    return '<article class="hierarchy-card"><div class="health-ring ' + status[1] + '"><i></i><span>' + escapeHTML(progress.display) + '</span></div><div class="hierarchy-main"><div class="hierarchy-title"><strong>' + escapeHTML(current.artifact || current.title || owner) + '</strong><span>' + escapeHTML(current.role_label || current.role || "TASK") + subagentMeta + '</span></div><p><i class="activity-dot ' + status[1] + '" aria-hidden="true"></i>' + escapeHTML(progress.freshness) + (stalled ? ' <b class="stalled-cue">Paused attention</b>' : '') + '</p><div class="task-progress"><i style="width:' + (progress.percent == null ? 0 : progress.percent) + '%"></i></div>' + (extra.length ? '<details><summary>' + extra.length + ' more task' + (extra.length === 1 ? '' : 's') + '</summary><ul>' + extra.map((task) => '<li>' + escapeHTML(task.artifact || task.title || task.id) + '</li>').join('') + '</ul></details>' : '') + '</div></article>';
  }).join('') : '<p class="empty-state">No owners in this view.</p>';
}

function kanbanState(node) {
  const taskStatus = String(node.status || "pending").toLowerCase();
  const forecastStatus = String(node.eta?.status || "").toLowerCase();
  if (["done", "complete", "archived"].includes(taskStatus)) return "Completed";
  if (["blocked", "at_risk"].includes(taskStatus) || ["blocked", "at_risk"].includes(forecastStatus)) return "Attention";
  if (["active", "in_progress"].includes(taskStatus)) return "In progress";
  return "Planned";
}

function renderKanban() {
  const columns = ["Planned", "In progress", "Attention", "Completed"];
  const nodes = scopedNodes().filter((node) => !isSubagent(node));
  $("#kanban-summary").textContent = nodes.length ? String(nodes.length) + " task" + (nodes.length === 1 ? '' : 's') : 'No tasks';
  $("#kanban-board").innerHTML = columns.map((column) => {
    const tasks = nodes.filter((node) => kanbanState(node) === column);
    return '<section class="kanban-column"><header><strong>' + column + '</strong><span>' + tasks.length + '</span></header><div>' + (tasks.length ? tasks.map((task) => {
      const label = column === "Attention" ? ["At risk", "is-blocked"] : statusLabel(task);
      return '<article class="kanban-card"><strong>' + escapeHTML(task.artifact || task.title || task.id) + '</strong><small>' + escapeHTML(task.eta?.eta_end_ms ? 'Forecast ' + formatEta(task.eta.eta_end_ms) : 'No forecast') + '</small><span class="state-pill ' + label[1] + '">' + escapeHTML(label[0]) + '</span></article>';
    }).join('') : '<p>None observed</p>') + '</div></section>';
  }).join('');
}

function renderDiagnostics() {
  const latest = state.diagnostics?.latest || {};
  const payload = latest.payload || {};
  const health = state.diagnostics?.health || {};
  const disk = (payload.disks || []).find((item) => item?.available) || {};
  const freshness = latest.freshness || state.diagnostics?.freshness || {};
  const availability = latest.availability || state.diagnostics?.availability || {};
  const unavailable = Array.isArray(availability.unavailable) ? availability.unavailable : [];
  const freshnessLabel = freshness.state === 'fresh' ? 'Fresh' : freshness.state === 'stale' ? 'Stale' : 'No diagnostic sample';
  const freshnessNote = Number.isFinite(Number(freshness.age_seconds)) ? formatDuration(Number(freshness.age_seconds) * 1000) + ' ago' : 'Waiting for a source sample';
  const metricNote = (metric, fallback) => [metric?.source ? humanize(metric.source) : fallback, metric?.observed_at_ms ? formatRelative(metric.observed_at_ms) : ''].filter(Boolean).join(' · ');
  const cards = [];
  if (payload.cpu?.available) cards.push(['CPU', Math.round(Number(payload.cpu.percent) || 0) + '%', metricNote(payload.cpu, 'Current load')]);
  if (payload.memory?.available) cards.push(['Memory', formatBytes(payload.memory.used_bytes) + ' in use', metricNote(payload.memory, 'Current memory')]);
  if (disk.available) cards.push(['Disk', formatBytes(disk.free_bytes) + ' free', metricNote(disk, Math.round(Number(disk.percent) || 0) + '% used')]);
  if (payload.docker?.available) cards.push(['Containers', String(payload.docker.container_count || 0), metricNote(payload.docker, humanize(payload.docker.status || 'Available'))]);
  if (payload.network?.available) cards.push(['Network', formatBytes((Number(payload.network.rx_bytes) || 0) + (Number(payload.network.tx_bytes) || 0)), metricNote(payload.network, 'Observed total')]);
  const unavailableState = unavailable.length ? '<article class="panel diagnostic-unavailable"><p class="eyebrow">Source availability</p><h3>' + escapeHTML(unavailable.map((item) => item.label || item.group).join(', ') + ' unavailable') + '</h3><p>' + escapeHTML(unavailable[0].reason || 'No observed value was returned.') + '</p><small>' + escapeHTML(unavailable[0].action || 'Keep this source unavailable until it returns a readable value.') + '</small></article>' : '';
  const noMetrics = cards.length ? '' : '<article class="panel diagnostic-unavailable"><p class="eyebrow">Source availability</p><h3>No independent metrics available</h3><p>Diagnostics will show values when a source reports them.</p></article>';
  $("#diagnostic-grid").innerHTML = '<article class="panel diagnostic-freshness"><p class="eyebrow">Diagnostics</p><h3>' + escapeHTML(freshnessLabel) + '</h3><small>' + escapeHTML(freshnessNote) + '</small></article>' + cards.map(([label, value, note]) => '<article class="metric-card diagnostic-card"><p>' + escapeHTML(label) + '</p><strong>' + escapeHTML(value) + '</strong><span>' + escapeHTML(note) + '</span></article>').join('') + unavailableState + noMetrics + '<article class="panel auto-health"><p class="eyebrow">Automatic care</p><h3>Keep this device healthy</h3><label class="toggle-row"><input id="auto-health" type="checkbox"' + (state.health?.enabled ? ' checked' : '') + '><span>Create maintenance tasks automatically</span></label><small>Starts with a review. SWARM will not delete files or stop work on its own.</small></article>';
  const incidents = health.incidents || [];
  $("#attention-count").textContent = String(incidents.length);
  $("#attention-list").innerHTML = incidents.length ? incidents.slice(0, 6).map((item) => {
    const guidance = { disk: "Storage is running low.", cpu: "CPU load has stayed high.", memory: "Memory use has stayed high." };
    return '<article class="attention-item"><strong>' + escapeHTML((item.scope || "Device") + " " + (item.kind || "health")) + '</strong><small>' + escapeHTML(humanize(item.severity || item.state || 'Active') + " · " + (guidance[item.kind] || "Needs attention.")) + '</small></article>';
  }).join('') : '<p class="empty-state">No current health attention.</p>';
}

function renderOverviewDiagnostics() {
  const latest = state.diagnostics?.latest || {};
  const payload = latest.payload || {};
  const disk = (payload.disks || []).find((item) => item.available) || {};
  const network = payload.network || {};
  const value = (available, amount, suffix = "%") => available && Number.isFinite(Number(amount)) ? Math.round(Number(amount)) + suffix : "Unavailable";
  $("#overview-health-state").textContent = humanize(latest.health_state || "Unavailable");
  $("#overview-cpu").textContent = value(payload.cpu?.available, payload.cpu?.percent);
  $("#overview-memory").textContent = value(payload.memory?.available, payload.memory?.percent);
  $("#overview-disk").textContent = value(disk.available, disk.percent);
  $("#overview-network").textContent = network.available ? compactNumber((Number(network.rx_bytes) || 0) + (Number(network.tx_bytes) || 0)) + "B" : "Unavailable";
}

function configEditable(key) {
  return (state.config?.editable || []).includes(key);
}

function settingToggle(key, value, label) {
  const editable = configEditable(key);
  return '<label class="toggle-row"><input data-config-key="' + escapeHTML(key) + '" type="checkbox"' + (value ? ' checked' : '') + (!editable ? ' disabled' : '') + '><span>' + escapeHTML(label) + '</span></label>' + (!editable ? '<small>Managed by the current configuration.</small>' : '');
}

function settingSelect(key, value, options, label) {
  const editable = configEditable(key);
  return '<label class="setting-field">' + escapeHTML(label) + '<select data-config-key="' + escapeHTML(key) + '"' + (!editable ? ' disabled' : '') + '>' + options.map((option) => '<option value="' + escapeHTML(option) + '"' + (option === value ? ' selected' : '') + '>' + escapeHTML(option) + '</option>').join('') + '</select></label>' + (!editable ? '<small>Managed by the current configuration.</small>' : '');
}

function currentSettingsScope() {
  if (state.settingsScopeType && state.settingsScopeId) return { type: state.settingsScopeType, id: state.settingsScopeId };
  if (state.ctrlId) return { type: 'ctrl', id: state.ctrlId };
  if (state.projectId !== 'all' && !state.projectId.startsWith('ctrl:')) return { type: 'project', id: state.projectId };
  return { type: 'global', id: 'global' };
}

function settingsScopeOptions() {
  const groups = projectGroups();
  const scope = currentSettingsScope();
  const selected = scope.type + '|' + scope.id;
  const options = ['<option value="global|global"' + (selected === 'global|global' ? ' selected' : '') + '>Global defaults</option>'];
  groups.forEach((group) => {
    const controllers = [...(group.controllers || [])].sort((a, b) => Number(b.updated_at || 0) - Number(a.updated_at || 0));
    if (!group.standalone) options.push('<option value="project|' + escapeHTML(group.id) + '"' + (selected === 'project|' + group.id ? ' selected' : '') + '>' + escapeHTML(group.label) + ' / project</option>');
    if (controllers.length) options.push('<optgroup label="' + escapeHTML(group.label) + '">' + controllers.map((ctrl, index) => {
      const rawLabel = ctrlLabel(ctrl);
      const label = rawLabel.localeCompare(group.label, undefined, { sensitivity: "base" }) === 0 ? "CTRL" + (controllers.length > 1 ? " " + String(index + 1) : "") : rawLabel;
      return '<option value="ctrl|' + escapeHTML(ctrl.id) + '"' + (selected === 'ctrl|' + ctrl.id ? ' selected' : '') + '>' + escapeHTML(group.label + ' / ' + label) + '</option>';
    }).join('') + '</optgroup>');
  });
  return options.join('');
}

function selectedSettingsCtrl() {
  const scope = currentSettingsScope();
  return scope.type === 'ctrl' ? historicalControllers().find((ctrl) => ctrl.id === scope.id) || null : null;
}

function skillStatus(skill) {
  if (skill.builtin) return 'Built in';
  return ({ inherited: 'Inherited', available_to_install: 'Available', blocked_unreviewed: 'Needs review', blocked_authority: 'Blocked' })[skill.status] || (skill.relevant ? 'Available' : 'Not matched');
}

function skillPurpose(skill) {
  return skill.task_purpose || skill.purpose || (skill.relevant ? 'Matches the selected role and task.' : 'Not matched for the selected role and task.');
}

function skillOverlay(scope) {
  return state.skills?.overlays?.[scope.type] || null;
}

function skillsSummary(scope) {
  if (state.skillsError) return '<div class="skills-row"><div><strong>Skills</strong><small>Skills are unavailable right now. Try again to refresh this scope.</small></div><button class="quiet-button" data-setting-action="retry-skills" type="button">Try again</button></div>';
  if (!state.skills) return '<div class="skills-row"><div><strong>Skills</strong><small>Loading the approved skills for this scope.</small></div></div>';
  const skills = state.skills.skills || [];
  const inherited = skills.filter((skill) => skill.status === 'inherited').length;
  const preferred = skills.filter((skill) => skill.preferred).length;
  const available = skills.filter((skill) => skill.status === 'available_to_install').length;
  const enabled = state.skills.settings?.inheritance_enabled === true;
  const overlay = skillOverlay(scope);
  return '<div class="skills-row"><div><strong>Skills</strong><small>' + escapeHTML(scope.type === 'global' ? 'Global defaults' : (enabled ? 'Inherited for this scope' : 'Inheritance off for this scope')) + '</small></div><button class="quiet-button" data-setting-action="manage-skills" type="button" aria-controls="skills-details">Manage</button></div><label class="toggle-row"><input id="skills-inheritance" type="checkbox"' + (enabled ? ' checked' : '') + '><span>Inherit approved skills</span></label><small>' + inherited + ' inherited · ' + preferred + ' preferred · ' + available + ' available</small>' + (overlay ? '<button class="quiet-button" data-setting-action="reset-skills" type="button">Use inherited settings</button>' : '');
}

function skillsAdvanced(scope) {
  if (!state.skills) return '<section class="skills-panel" id="skills-details"><p>Approved skill details are loading.</p></section>';
  const shortlist = (state.skills.skills || []).filter((skill) => skill.relevant || skill.builtin || skill.preferred).sort((a, b) => Number(b.status === 'inherited') - Number(a.status === 'inherited') || Number(b.preferred) - Number(a.preferred) || Number(b.builtin) - Number(a.builtin));
  const entries = shortlist.length ? shortlist.map((skill) => {
    const metadata = [];
    if (skill.source?.repo) metadata.push(skill.source.repo + (skill.source.version ? ' · ' + skill.source.version : ''));
    if (skill.audit?.value && skill.audit.value !== 'unknown') metadata.push('Audit ' + skill.audit.value);
    if (skill.popularity?.value && skill.popularity.value !== 'unknown') metadata.push('Popularity ' + skill.popularity.value);
    return '<li><div><strong>' + escapeHTML(humanize(skill.skill_id)) + '</strong><small>' + escapeHTML(skillPurpose(skill)) + '</small></div><span class="skill-status">' + escapeHTML(skillStatus(skill)) + '</span>' + (metadata.length ? '<em>' + escapeHTML(metadata.join(' · ')) + '</em>' : '') + '</li>';
  }).join('') : '<p>No approved skills match this scope yet.</p>';
  return '<section class="skills-panel" id="skills-details"><div><strong>Approved skills</strong><small>Read-only catalog projection for ' + escapeHTML(scope.type === 'global' ? 'global defaults' : scope.type + ' scope') + '.</small></div><ul class="skills-list">' + entries + '</ul><p>This console cannot install or update skills.</p></section>';
}

function renderSettings() {
  const scope = currentSettingsScope();
  const selectedCtrl = selectedSettingsCtrl();
  const setting = state.ctrlSettings;
  const storage = state.storage;
  const boost = state.config?.settings?.boost || {};
  const execution = state.config?.settings?.execution || {};
  const consoleSettings = state.config?.settings?.console || {};
  const monitoring = state.config?.settings?.monitoring || {};
  const roleIcons = state.config?.settings?.role_icons || {};
  const effective = setting?.effective || setting?.global_defaults || {};
  const reasoningOptions = ["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"];
  const retention = storage?.retention_days == null ? "" : " · retain " + storage.retention_days + " days";
  const proofFiles = Number(storage?.proof_files) || 0;
  $("#settings-grid").innerHTML =
    '<section class="panel settings-card"><p class="eyebrow">Settings scope</p><h3>Where changes apply</h3><label class="setting-field">Scope<select id="settings-scope">' + settingsScopeOptions() + '</select></label><p class="scope-setting-status"><strong>' + escapeHTML(selectedCtrl ? publicLabel(selectedCtrl.project, "Project") + " / " + ctrlLabel(selectedCtrl) : "Global defaults") + '</strong><span>' + escapeHTML(selectedCtrl ? (setting?.customized ? "Custom settings" : "Inherits global defaults") : "Applies to every CTRL unless it has custom settings") + '</span></p>' +
      (selectedCtrl ? '<div class="ctrl-assignment"><small>Current assignment</small><strong>' + escapeHTML((effective.model || "Model unavailable") + ' · ' + (effective.reasoning || "Reasoning unavailable")) + '</strong></div><label class="toggle-row"><input id="ctrl-customize" type="checkbox"' + (setting?.customized ? ' checked' : '') + '><span>Customize this CTRL separately</span></label>' + (setting?.customized ? '<div class="ctrl-fields"><label>Model<input id="ctrl-model" value="' + escapeHTML(effective.model || '') + '" autocomplete="off"></label><label>Reasoning<select id="ctrl-reasoning">' + reasoningOptions.map((option) => '<option value="' + option + '"' + (option === effective.reasoning ? ' selected' : '') + '>' + option + '</option>').join('') + '</select></label></div><button class="quiet-button" data-setting-action="save-ctrl" type="button">Save CTRL settings</button>' : '') + '<button class="quiet-button" data-setting-action="reset" type="button"' + (!setting?.customized ? ' disabled' : '') + '>Use global defaults</button>' : '<small>Select a Project / CTRL above to create a permitted per-CTRL override.</small>') + '</section>' +
    '<section class="panel settings-card"><p class="eyebrow">Work routing</p><h3>How work is handled</h3>' +
      settingSelect('execution.max_reasoning', execution.max_reasoning || 'medium', reasoningOptions, 'Default reasoning') +
      settingToggle('execution.fast_mode', execution.fast_mode, 'Fast mode') + '<small>Requests faster service for new assignments. SWARM reports it active only from a host receipt.</small>' +
      settingToggle('execution.usage_saver', execution.usage_saver, 'Use less usage when possible') +
      settingToggle('boost.spark_enabled', boost.spark_enabled, 'Use Spark for safe small tasks') + '<small>Spark handles quick, low-risk work. Larger or external tasks stay with full agents.</small>' +
      settingSelect('boost.spark_reasoning', boost.spark_reasoning || 'xhigh', reasoningOptions, 'Spark default reasoning') +
      '<details class="settings-advanced" id="settings-advanced"><summary>Advanced settings</summary><div class="ctrl-fields"><label>Spark model<input id="spark-model" value="' + escapeHTML(boost.spark_model || '') + '" autocomplete="off"' + (!configEditable('boost.spark_model') ? ' disabled' : '') + '></label><label>Heartbeat minutes<input id="heartbeat-minutes" data-config-key="monitoring.heartbeat_minutes" type="number" min="1" value="' + escapeHTML(monitoring.heartbeat_minutes || '') + '"' + (!configEditable('monitoring.heartbeat_minutes') ? ' disabled' : '') + '></label></div><button class="quiet-button" data-setting-action="save-spark" type="button"' + (!configEditable('boost.spark_model') ? ' disabled' : '') + '>Save Spark model</button>' + skillsAdvanced(scope) + '</details></section>' +
    '<section class="panel settings-card"><p class="eyebrow">Console and data</p><h3>Keep the workspace predictable</h3>' +
      settingToggle('console.project_progress_feed_enabled', consoleSettings.project_progress_feed_enabled, 'Progress feed') +
      '<label class="setting-field">Updates shown<input data-config-key="console.project_progress_feed_lines" type="number" min="1" max="10" value="' + escapeHTML(consoleSettings.project_progress_feed_lines ?? 4) + '"' + (!configEditable('console.project_progress_feed_lines') ? ' disabled' : '') + '></label>' +
      settingToggle('console.open_on_start', consoleSettings.open_on_start, 'Open SWARM when Codex starts') +
      settingToggle('role_icons.enabled', roleIcons.enabled, 'Show role icons') +
      '<label class="toggle-row"><input id="auto-health" type="checkbox"' + (state.health?.enabled ? ' checked' : '') + '><span>Ask for maintenance review when health needs attention</span></label><small>Review requests do not run a model or change the device by themselves.</small><h4>Skills</h4>' + skillsSummary(scope) + '<h4>' + escapeHTML(storage?.bytes == null ? 'Saved history unavailable' : formatBytes(storage.bytes) + ' saved history' + retention) + '</h4><p>Progress, forecasts, proof, and token history stay available between sessions' + (proofFiles ? ' · ' + proofFiles + ' proof file' + (proofFiles === 1 ? '' : 's') : '') + '.</p><div class="settings-actions-inline"><button class="quiet-button" data-setting-action="clear" type="button">Clear history</button><button class="quiet-button" data-setting-action="restore" type="button">Restore defaults</button></div><small>Clearing history leaves tasks unchanged. Restoring defaults keeps history.</small></section>';
}

function renderAllViews() { renderOverview(); renderDashboard(); renderHierarchy(); renderKanban(); renderDiagnostics(); renderSettings(); }

async function refreshProof() {
  const projectId = state.projectId;
  const collectionKey = proofCollectionKey(projectId);
  const params = new URLSearchParams();
  if (projectId !== "all" && !projectId.startsWith("ctrl:")) params.set("project_id", projectId);
  try {
    const result = await api('/api/proof-feed' + (params.size ? '?' + params.toString() : ''));
    if (collectionKey !== proofCollectionKey()) return;
    state.proof = dedupeProofItems(result.items);
    state.proofCollections.set(collectionKey, state.proof);
    state.proofStatus = "current";
    state.proofStatuses.set(collectionKey, "current");
    state.proofSequence = Number(result.sequence) || 0;
  } catch {
    if (collectionKey !== proofCollectionKey()) return;
    state.proof = state.proofCollections.get(collectionKey) || [];
    state.proofStatus = state.proof.length ? "stale" : "unavailable";
    state.proofStatuses.set(collectionKey, state.proofStatus);
  }
}

async function refreshUsageHistory() {
  const request = { projectId: state.projectId, ctrlId: state.ctrlId, hours: state.usageWindowHours };
  const requestKey = usageRequestKey(request.projectId, request.ctrlId, request.hours);
  const params = new URLSearchParams({ project_id: request.projectId, ctrl_id: request.ctrlId, hours: String(request.hours) });
  state.usageStatus = "loading";
  try {
    const result = await api('/api/usage-history?' + params.toString());
    if (request.projectId !== state.projectId || request.ctrlId !== state.ctrlId || request.hours !== state.usageWindowHours) return;
    state.usageHistory = result;
    state.usageScopeKey = requestKey;
    state.usageStatus = "current";
    state.usageError = "";
  } catch (error) {
    if (request.projectId !== state.projectId || request.ctrlId !== state.ctrlId || request.hours !== state.usageWindowHours) return;
    state.usageHistory = null;
    state.usageScopeKey = requestKey;
    state.usageStatus = "error";
    state.usageError = error.message || "Usage history unavailable";
  }
}

async function refreshProjectProgressFeed() {
  const projectId = selectedProgressProjectId();
  if (!projectId) {
    state.projectProgressFeed = null;
    state.projectProgressProjectId = "";
    state.projectProgressStatus = "idle";
    state.projectProgressError = "";
    return;
  }
  const hasLastGood = state.projectProgressProjectId === projectId && Array.isArray(state.projectProgressFeed?.items);
  if (!hasLastGood) {
    state.projectProgressFeed = null;
    state.projectProgressProjectId = projectId;
  }
  state.projectProgressStatus = hasLastGood ? "refreshing" : "loading";
  try {
    const params = new URLSearchParams({ project_id: projectId, after_cursor: "0" });
    const result = await api('/api/project-progress-feed?' + params.toString());
    if (projectId !== selectedProgressProjectId()) return;
    state.projectProgressFeed = result;
    state.projectProgressProjectId = projectId;
    state.projectProgressStatus = "current";
    state.projectProgressError = "";
  } catch (error) {
    if (projectId !== selectedProgressProjectId()) return;
    if (!hasLastGood) state.projectProgressFeed = null;
    state.projectProgressProjectId = projectId;
    state.projectProgressStatus = hasLastGood ? "stale" : "unavailable";
    state.projectProgressError = error.message || "Project updates unavailable";
  }
}

async function refreshMonitoring(proofSequence) {
  try {
    state.overview = await api("/api/overview", { timeoutMs: 15_000 });
    clearConnectionState();
    setDataStatus("current", state.overview?.generated_at);
    renderProjectNavigation();
    await refreshUsageHistory();
    if (Number(proofSequence) !== state.proofSequence) await refreshProof();
    renderOverview();
    renderDashboard();
    renderHierarchy();
  } catch {
    setDataStatus(state.overview ? "stale" : "unavailable", state.overview?.generated_at);
    /* The next manual refresh can recover the complete screen. */
  }
}

async function refreshCtrlSettings() {
  const scope = currentSettingsScope();
  const selectedCtrl = scope.type === 'ctrl' ? scope.id : '';
  if (!selectedCtrl) { state.ctrlSettings = null; return; }
  try { state.ctrlSettings = await api('/api/ctrl-settings?ctrl_id=' + encodeURIComponent(selectedCtrl)); }
  catch { state.ctrlSettings = null; }
}

async function refreshSkills() {
  const scope = currentSettingsScope();
  const params = new URLSearchParams();
  if (scope.type === 'project') params.set('project_id', scope.id);
  if (scope.type === 'ctrl') params.set('ctrl_id', scope.id);
  try { state.skills = await api('/api/skills' + (params.size ? '?' + params.toString() : '')); state.skillsError = ''; }
  catch (error) { state.skills = null; state.skillsError = error.message || 'Skills could not be loaded.'; }
}

async function refreshOverview(showLoading = true) {
  if (showLoading) setLoading(true);
  clearError();
  try {
    state.overview = await api("/api/overview", { timeoutMs: 15_000 });
    clearConnectionState();
    setDataStatus("current", state.overview?.generated_at);
    renderProjectNavigation();
    await Promise.all([refreshProof(), refreshUsageHistory(), refreshProjectProgressFeed()]);
    const selectedCtrl = state.ctrlId || historicalControllers()[0]?.id || '';
    const results = await Promise.allSettled([api('/api/diagnostics'), api('/api/diagnostics/history?limit=24'), api('/api/health/settings'), api('/api/storage'), selectedCtrl ? api('/api/ctrl-settings?ctrl_id=' + encodeURIComponent(selectedCtrl)) : Promise.resolve(null), api('/api/config')]);
    [state.diagnostics, state.diagnosticHistory, state.health, state.storage, state.ctrlSettings, state.config] = results.map((result) => result.status === 'fulfilled' ? result.value : null);
    state.diagnosticHistory = state.diagnosticHistory?.items || [];
    await refreshSkills();
    renderAllViews();
  } catch (error) {
    setDataStatus(state.overview ? "stale" : "unavailable", state.overview?.generated_at);
    if (error.connectionFailure && !state.overview) showConnectionState();
    else showError(error.message);
  } finally {
    if (showLoading) setLoading(false);
  }
}

async function initialize() {
  try {
    const bootstrap = await api("/api/bootstrap");
    state.token = bootstrap.token || "";
  } catch (error) {
    if (error.connectionFailure) showConnectionState();
    else showError(error.message);
    setLoading(false);
    return;
  }
  await refreshOverview();
}

let presenceTimer = null;
async function reportPresence() {
  if (document.visibilityState === "hidden") return;
  try {
    const receipt = await api("/api/presence", { method: "POST" });
    const sequence = Number(receipt.proof_sequence) || 0;
    await refreshMonitoring(sequence);
  } catch { /* Presence is advisory. */ }
}

function startPresence() {
  if (presenceTimer) clearInterval(presenceTimer);
  reportPresence();
  presenceTimer = setInterval(reportPresence, 60_000);
}

document.addEventListener("click", (event) => {
  const evidenceOpen = event.target.closest("[data-evidence-open]");
  if (evidenceOpen) {
    event.preventDefault();
    openEvidenceLightbox(Number(evidenceOpen.dataset.evidenceOpen), evidenceOpen);
    return;
  }
  const evidenceThumbnail = event.target.closest("[data-evidence-thumbnail]");
  if (evidenceThumbnail) {
    state.evidenceIndex = Number(evidenceThumbnail.dataset.evidenceThumbnail);
    renderEvidenceLightbox();
    return;
  }
  if (event.target.closest("#evidence-lightbox-close")) {
    closeEvidenceLightbox();
    return;
  }
  if (event.target.closest("#evidence-lightbox-previous")) {
    state.evidenceIndex -= 1;
    renderEvidenceLightbox();
    return;
  }
  if (event.target.closest("#evidence-lightbox-next")) {
    state.evidenceIndex += 1;
    renderEvidenceLightbox();
    return;
  }
  if (event.target.closest("#evidence-page-previous")) {
    const page = Math.floor(state.evidenceIndex / EVIDENCE_THUMBNAIL_PAGE_SIZE);
    state.evidenceIndex = Math.max(0, (page - 1) * EVIDENCE_THUMBNAIL_PAGE_SIZE);
    renderEvidenceLightbox();
    return;
  }
  if (event.target.closest("#evidence-page-next")) {
    const page = Math.floor(state.evidenceIndex / EVIDENCE_THUMBNAIL_PAGE_SIZE);
    state.evidenceIndex = Math.min(state.evidenceImages.length - 1, (page + 1) * EVIDENCE_THUMBNAIL_PAGE_SIZE);
    renderEvidenceLightbox();
    return;
  }
  const usageWindow = event.target.closest("[data-usage-hours]");
  if (usageWindow) {
    const hours = Number(usageWindow.dataset.usageHours);
    if (!Object.hasOwn(USAGE_WINDOW_LABELS, hours) || hours === state.usageWindowHours) return;
    state.usageWindowHours = hours;
    renderUsage();
    refreshUsageHistory().then(renderUsage);
    return;
  }
  const subagentToggleButton = event.target.closest("[data-subagent-toggle]");
  if (subagentToggleButton) {
    const expanded = subagentToggleButton.getAttribute("aria-expanded") === "true";
    const parentId = subagentToggleButton.dataset.subagentToggle;
    setSubagentVisibility(parentId, !expanded);
    subagentToggleButton.setAttribute("aria-expanded", String(!expanded));
    const text = subagentToggleButton.querySelector("span");
    if (text) text.textContent = text.textContent.replace(expanded ? /^Show / : /^Hide /, expanded ? "Show " : "Hide ");
    event.stopPropagation();
    return;
  }
  const tab = event.target.closest("[data-view]");
  if (tab) setView(tab.dataset.view);
  const risk = event.target.closest("#risk-action");
  if (risk?.dataset.taskId) document.querySelector("tr[data-task-id='" + CSS.escape(risk.dataset.taskId) + "']")?.scrollIntoView({ block: "center", behavior: "smooth" });
});

$("#evidence-lightbox").addEventListener("close", () => {
  state.evidenceTrigger?.focus();
  state.evidenceTrigger = null;
});
$("#evidence-lightbox-image").addEventListener("error", () => {
  $("#evidence-lightbox-image").hidden = true;
  $("#evidence-lightbox-failed").hidden = false;
});
document.addEventListener("keydown", (event) => {
  if (!$("#evidence-lightbox").open || !["ArrowLeft", "ArrowRight"].includes(event.key)) return;
  const nextIndex = state.evidenceIndex + (event.key === "ArrowLeft" ? -1 : 1);
  if (nextIndex < 0 || nextIndex >= state.evidenceImages.length) return;
  event.preventDefault();
  state.evidenceIndex = nextIndex;
  renderEvidenceLightbox();
});

$("#project-navigation").addEventListener("click", (event) => {
  const scope = event.target.closest("[data-project-id]");
  if (!scope) return;
  event.preventDefault();
  state.projectId = scope.dataset.projectId;
  state.ctrlId = scope.dataset.ctrlId || "";
  state.settingsCtrlId = state.ctrlId;
  state.settingsScopeType = state.ctrlId ? 'ctrl' : (state.projectId === 'all' ? 'global' : 'project');
  state.settingsScopeId = state.ctrlId || (state.projectId === 'all' ? 'global' : state.projectId);
  renderProjectNavigation();
  renderAllViews();
  Promise.all([refreshProof(), refreshCtrlSettings(), refreshUsageHistory(), refreshProjectProgressFeed(), refreshSkills()]).then(renderAllViews);
});
$("#refresh").addEventListener("click", refreshOverview);
$("#retry").addEventListener("click", refreshOverview);
$("#connection-retry").addEventListener("click", initialize);
document.addEventListener('change', async (event) => {
  if (event.target.id === 'settings-scope') {
    const [scopeType, scopeId] = event.target.value.split('|');
    const ctrl = scopeType === 'ctrl' ? historicalControllers().find((item) => item.id === scopeId) : null;
    state.settingsScopeType = ['global', 'project', 'ctrl'].includes(scopeType) ? scopeType : 'global';
    state.settingsScopeId = scopeId || 'global';
    state.settingsCtrlId = ctrl ? ctrl.id : '';
    state.ctrlId = ctrl ? ctrl.id : '';
    state.projectId = scopeType === 'project' ? scopeId : ctrl ? (ctrl.project_id || 'ctrl:' + ctrl.id) : 'all';
    renderProjectNavigation();
    renderAllViews();
    try {
      await Promise.all([refreshProof(), refreshUsageHistory(), refreshProjectProgressFeed(), refreshCtrlSettings(), refreshSkills()]);
    } finally { renderAllViews(); }
    return;
  }
  if (event.target.id === 'auto-health') {
    try { state.health = await api('/api/health/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: event.target.checked }) }); renderDiagnostics(); renderSettings(); } catch (error) { showError(error.message); renderDiagnostics(); renderSettings(); }
    return;
  }
  if (event.target.id === 'skills-inheritance') {
    const scope = currentSettingsScope();
    const overlay = skillOverlay(scope);
    try {
      await api('/api/skills/inheritance', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scope_type: scope.type, scope_id: scope.id, expected_revision: overlay?.revision || 0, changes: { inheritance_enabled: event.target.checked } }) });
      await refreshSkills();
      renderSettings();
    } catch (error) { showError(error.message); await refreshSkills(); renderSettings(); }
    return;
  }
  if (event.target.dataset.configKey) {
    const key = event.target.dataset.configKey;
    if (!configEditable(key)) return;
    const value = event.target.type === 'checkbox' ? event.target.checked : event.target.type === 'number' ? Number(event.target.value) : event.target.value;
    try {
      state.config = await api('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ changes: { [key]: value } }) });
      if (key === 'console.project_progress_feed_enabled' || key === 'console.project_progress_feed_lines') await refreshProjectProgressFeed();
      renderAllViews();
    } catch (error) { showError(error.message); renderSettings(); }
    return;
  }
  if (event.target.id === 'ctrl-customize') {
    if (!state.ctrlSettings) return;
    try {
      if (event.target.checked) {
        const defaults = state.ctrlSettings.global_defaults || {};
        state.ctrlSettings = await api('/api/ctrl-settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ctrl_id: state.ctrlSettings.ctrl_id, expected_revision: state.ctrlSettings.revision, changes: { model: defaults.model, reasoning: defaults.reasoning } }) });
      } else {
        state.ctrlSettings = await api('/api/ctrl-settings/reset', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ctrl_id: state.ctrlSettings.ctrl_id, expected_revision: state.ctrlSettings.revision }) });
      }
      renderSettings();
    } catch (error) { showError(error.message); await refreshCtrlSettings(); renderSettings(); }
  }
});
document.addEventListener('click', async (event) => {
  const action = event.target.closest('[data-setting-action]')?.dataset.settingAction;
  if (!action) return;
  const messages = { clear: 'Clear saved SWARM history? Your tasks will stay unchanged.', restore: 'Restore default settings? Your history will stay unchanged.', reset: 'Use global defaults for this CTRL?', 'reset-skills': 'Restore inherited skill settings for this scope?' };
  if (messages[action] && !confirm(messages[action])) return;
  try {
    if (action === 'clear') await api('/api/storage/clear', { method: 'POST' });
    if (action === 'restore') await api('/api/settings/restore', { method: 'POST' });
    if (action === 'reset' && state.ctrlSettings) await api('/api/ctrl-settings/reset', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ctrl_id: state.ctrlSettings.ctrl_id, expected_revision: state.ctrlSettings.revision }) });
    if (action === 'manage-skills') {
      const details = $('#settings-advanced');
      if (details) { details.open = true; details.scrollIntoView({ block: 'nearest' }); }
      return;
    }
    if (action === 'retry-skills') { await refreshSkills(); renderSettings(); return; }
    if (action === 'reset-skills') {
      const scope = currentSettingsScope();
      const overlay = skillOverlay(scope);
      if (!overlay) return;
      await api('/api/skills/inheritance/reset', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scope_type: scope.type, scope_id: scope.id, expected_revision: overlay.revision }) });
      await refreshSkills();
      renderSettings();
      return;
    }
    if (action === 'save-ctrl' && state.ctrlSettings) state.ctrlSettings = await api('/api/ctrl-settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ctrl_id: state.ctrlSettings.ctrl_id, expected_revision: state.ctrlSettings.revision, changes: { model: $('#ctrl-model').value.trim(), reasoning: $('#ctrl-reasoning').value } }) });
    if (action === 'save-spark' && configEditable('boost.spark_model')) state.config = await api('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ changes: { 'boost.spark_model': $('#spark-model').value.trim() } }) });
    await refreshOverview();
  } catch (error) { showError(error.message); }
});
$(".nav-list").addEventListener("keydown", (event) => {
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
  const tabs = $$(".nav-item");
  const index = tabs.indexOf(document.activeElement);
  const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + tabs.length) % tabs.length;
  event.preventDefault();
  tabs[next].focus();
  setView(tabs[next].dataset.view, true);
});

document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") reportPresence(); });
window.addEventListener("pagehide", () => { if (presenceTimer) clearInterval(presenceTimer); });

setView(routeView(), false, routeView() === 'overview' && location.hash !== '#overview');
window.addEventListener('hashchange', () => setView(routeView(), false, routeView() === 'overview' && location.hash !== '#overview'));
initialize().then(startPresence);
