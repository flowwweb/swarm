const state = { token: "", overview: null, proof: [], proofSequence: 0, usageHistory: null, diagnostics: null, diagnosticHistory: [], health: null, storage: null, config: null, ctrlSettings: null, view: "overview", projectId: "all", ctrlId: "" };
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

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { ...(state.token ? { "X-Swarm-Token": state.token } : {}), ...(options.headers || {}) } });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed (" + response.status + ")");
  return data;
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

function setView(view, focus) {
  state.view = view;
  const titles = {
    overview: ["Overview", "Project progress, risks, and proof at a glance."],
    hierarchy: ["Hierarchy", "See who owns the work, what is active, and where attention is needed."],
    kanban: ["Kanban", "Task state for the selected project or CTRL."],
    diagnostics: ["Diagnostics", "Device health, capacity, and maintenance."],
    settings: ["Settings", "Defaults and optional per-CTRL overrides."],
  };
  $$(".nav-item").forEach((tab) => {
    const selected = tab.dataset.view === view;
    tab.classList.toggle("is-active", selected);
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
  });
  $$("[data-view-panel]").forEach((panel) => {
    const selected = panel.dataset.viewPanel === view;
    panel.classList.toggle("is-active", selected);
    panel.hidden = !selected;
  });
  $("#view-title").textContent = titles[view][0];
  $("#view-subtitle").textContent = titles[view][1];
  if (focus) $("#tab-" + view).focus({ preventScroll: true });
}

function activeControllers() {
  return (state.overview?.nodes || []).filter((node) => String(node.role || "").toLowerCase() === "ctrl" && ["active", "in_progress"].includes(String(node.status || "").toLowerCase()));
}

function ctrlLabel(ctrl) {
  const label = ctrl.artifact || ctrl.title || ctrl.id;
  return String(label).replace(/^[^A-Za-z0-9]*CTRL\s*-\s*/i, "").trim() || "Untitled goal";
}

function projectGroups() {
  const projects = new Map((state.overview?.projects || []).map((project) => [project.id, project.name]));
  const groups = new Map((state.overview?.projects || [])
    .filter((project) => !/^https?[-_:]/i.test(String(project.name || "")))
    .map((project) => [project.id, { id: project.id, label: project.name, controllers: [], standalone: false }]));
  activeControllers().forEach((ctrl) => {
    const id = ctrl.project_id || "ctrl:" + ctrl.id;
    const label = ctrl.project_id ? (projects.get(ctrl.project_id) || ctrl.project || "Untitled project") : ctrlLabel(ctrl);
    const group = groups.get(id) || { id, label, controllers: [], standalone: !ctrl.project_id };
    group.controllers.push(ctrl);
    groups.set(id, group);
  });
  return [...groups.values()].sort((a, b) => a.label.localeCompare(b.label));
}

function scopeLabel() {
  if (state.projectId === "all") return "All projects";
  const group = projectGroups().find((item) => item.id === state.projectId);
  const ctrl = activeControllers().find((item) => item.id === state.ctrlId);
  return ctrl && state.ctrlId ? ctrlLabel(ctrl) : (group?.label || "All projects");
}

function renderProjectNavigation() {
  const groups = projectGroups();
  if (state.projectId !== "all" && !groups.some((group) => group.id === state.projectId)) {
    state.projectId = "all";
    state.ctrlId = "";
  }
  const entries = ['<button class="project-scope-button ' + (state.projectId === "all" ? "is-selected" : "") + '" data-project-id="all" type="button" aria-pressed="' + (state.projectId === "all") + '"><span aria-hidden="true">◇</span>All projects</button>'];
  groups.forEach((group) => {
    const current = state.projectId === group.id;
    if (group.controllers.length === 0) {
      entries.push('<button class="project-scope-button ' + (current && !state.ctrlId ? "is-selected" : "") + '" data-project-id="' + escapeHTML(group.id) + '" type="button" aria-pressed="' + (current && !state.ctrlId) + '"><span class="scope-dot is-live" aria-hidden="true"></span>' + escapeHTML(group.label) + '</button>');
      return;
    }
    if (group.controllers.length === 1) {
      const ctrl = group.controllers[0];
      entries.push('<button class="project-scope-button ' + (current && state.ctrlId === ctrl.id ? "is-selected" : "") + '" data-project-id="' + escapeHTML(group.id) + '" data-ctrl-id="' + escapeHTML(ctrl.id) + '" type="button" aria-pressed="' + (current && state.ctrlId === ctrl.id) + '"><span class="scope-dot is-live" aria-hidden="true"></span>' + escapeHTML(group.label) + '</button>');
      return;
    }
    const controllers = [...group.controllers].sort((a, b) => Number(b.updated_at || 0) - Number(a.updated_at || 0));
    entries.push('<section class="project-group"><div class="project-group-row"><button class="project-scope-button ' + (current && !state.ctrlId ? "is-selected" : "") + '" data-project-id="' + escapeHTML(group.id) + '" type="button" aria-pressed="' + (current && !state.ctrlId) + '"><span class="scope-dot is-live" aria-hidden="true"></span>' + escapeHTML(group.label) + '<small>' + group.controllers.length + ' CTRLs</small></button><button class="project-expand" data-project-toggle="' + escapeHTML(group.id) + '" type="button" aria-expanded="' + current + '" aria-controls="ctrl-subpages-' + escapeHTML(group.id) + '" aria-label="Show controllers for ' + escapeHTML(group.label) + '">⌄</button></div><div class="ctrl-subpages" id="ctrl-subpages-' + escapeHTML(group.id) + '"' + (current ? "" : " hidden") + '>' + controllers.map((ctrl, index) => {
      const rawLabel = ctrlLabel(ctrl);
      const label = rawLabel.localeCompare(group.label, undefined, { sensitivity: "base" }) === 0 ? "CTRL " + String(index + 1) : rawLabel;
      return '<button class="ctrl-scope-button ' + (current && state.ctrlId === ctrl.id ? "is-selected" : "") + '" data-project-id="' + escapeHTML(group.id) + '" data-ctrl-id="' + escapeHTML(ctrl.id) + '" type="button" aria-label="' + escapeHTML(group.label + " " + label) + '" aria-pressed="' + (current && state.ctrlId === ctrl.id) + '"><span>' + escapeHTML(formatRelative(ctrl.updated_at)) + '</span>' + escapeHTML(label) + '</button>';
    }).join("") + "</div></section>");
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

  const risks = nodes.filter((node) => ["blocked", "at_risk"].includes(String(node.eta?.status || node.status).toLowerCase()));
  $("#drift-value").textContent = risks.length ? String(risks.length) + " at risk" : "On track";
  $("#drift-value").className = risks.length ? "risk-text" : "healthy-text";
  $("#drift-note").textContent = risks.length ? String(risks.length) + " need attention" : "No forecast drift detected";
  $("#drift-detail").textContent = total ? String(total - risks.length) + " without a risk signal" : "No drift signal yet";

  const risk = risks[0] || nodes.find((node) => String(node.status).toLowerCase() === "blocked");
  $("#risk-value").textContent = risk?.artifact || "No active risk";
  $("#risk-note").textContent = risk ? humanize(risk.eta?.status || risk.status) + " · active " + formatRelative(risk.updated_at) : "Everything looks clear";
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

function renderProof(nodes) {
  const feed = state.proof.length ? state.proof : nodes.flatMap((node) => node.proof_snapshot?.available ? [{ task_id: node.id, caption: "Proof available", claim_limit: node.proof_snapshot.claim_limit }] : []);
  $("#proof-count").textContent = String(feed.length);
  $("#proof-feed").innerHTML = feed.length ? feed.slice(0, 5).map((item) => {
    const owner = nodes.find((node) => node.id === item.task_id);
    const media = item.evidence_id && item.digest && String(item.media_type || "").startsWith("image/")
      ? '<img class="proof-thumb" loading="lazy" decoding="async" src="/api/proof-media/' + encodeURIComponent(item.evidence_id) + '?digest=' + encodeURIComponent(item.digest) + '" alt="">'
      : '<span class="proof-icon" aria-hidden="true">▤</span>';
    const boundary = item.claim_limit || "Acceptance is recorded separately.";
    return '<article class="proof-item">' + media + '<div><span class="proof-availability">Available</span><span class="proof-boundary" role="img" aria-label="Scope: ' + escapeHTML(boundary) + '" title="Scope: ' + escapeHTML(boundary) + '">ⓘ</span><strong>' + escapeHTML(item.caption || item.kind || "Proof item") + '</strong><small>' + escapeHTML(owner?.artifact || item.task_id || "Task") + "</small></div></article>";
  }).join("") : '<p class="empty-state">No visual proof yet.</p>';
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

function overviewCards(nodes) {
  if (state.ctrlId) return [{ label: scopeLabel(), ctrlId: state.ctrlId, nodes }];
  const projectName = (projectId, projectNodes) => (state.overview?.projects || []).find((project) => project.id === projectId)?.name || projectNodes[0]?.project || "Independent work";
  const cardsForProject = (projectId, projectNodes) => {
    const projectControllers = projectNodes.filter((node) => !isSubagent(node) && String(node.role || "").toLowerCase() === "ctrl");
    if (projectControllers.length < 2) return [{ label: projectName(projectId, projectNodes), ctrlId: projectControllers[0]?.id || "", nodes: projectNodes }];
    return projectControllers.map((ctrl) => ({ label: projectName(projectId, projectNodes) + " · " + ctrlLabel(ctrl), ctrlId: ctrl.id, nodes: projectNodes.filter((node) => node.id === ctrl.id || (node.controller_ids || []).includes(ctrl.id)) }));
  };
  if (state.projectId !== "all") return cardsForProject(state.projectId, nodes);
  const projects = new Map((state.overview?.projects || []).filter((project) => !/^https?[-_:]/i.test(String(project.name || ""))).map((project) => [project.id, []]));
  nodes.forEach((node) => {
    const projectId = node.project_id || "independent";
    const list = projects.get(projectId) || [];
    list.push(node); projects.set(projectId, list);
  });
  return [...projects.entries()].flatMap(([projectId, projectNodes]) => cardsForProject(projectId, projectNodes));
}

function latestReceipt(nodes) {
  const allowed = new Set(nodes.map((node) => node.id));
  return state.proof.find((item) => allowed.has(item.task_id)) || null;
}

function renderMonitoringCards(nodes) {
  const cards = overviewCards(nodes);
  const tree = taskTree(nodes);
  $("#overview-summary").textContent = cards.length ? String(cards.length) + " active scope" + (cards.length === 1 ? "" : "s") : "No observed work yet";
  $("#monitoring-cards").innerHTML = cards.length ? cards.map((card) => {
    const tasks = observedTasks(card.nodes);
    const completed = tasks.filter((task) => ["done", "archived"].includes(String(task.status).toLowerCase())).length;
    const total = tasks.length;
    const percent = total ? Math.round((completed / total) * 100) : 0;
    const blocker = tasks.find((task) => ["blocked", "at_risk", "stalled", "critical"].includes(String(task.eta?.status || task.status).toLowerCase()));
    const receipt = latestReceipt(card.nodes);
    const primary = card.nodes.find((node) => node.id === card.ctrlId) || tasks[0];
    const stateLabel = primary ? statusLabel(primary)[0] : "No task state";
    const subagents = card.ctrlId ? subagentDescendants(card.ctrlId, tree) : [];
    const subagentDisclosure = subagents.length ? '<details class="monitoring-subagents" data-overview-subagents="' + escapeHTML(card.ctrlId) + '"><summary>' + subagents.length + ' supporting subagent' + (subagents.length === 1 ? '' : 's') + '</summary><ul>' + subagents.map((node) => '<li><strong>' + escapeHTML(node.artifact || node.title || node.id) + '</strong><span>' + escapeHTML(statusLabel(node)[0]) + '</span></li>').join('') + '</ul></details>' : '';
    return '<article class="monitoring-card panel"><header><div><p class="eyebrow">' + escapeHTML(stateLabel) + '</p><h3>' + escapeHTML(card.label) + '</h3></div><span>' + completed + ' / ' + total + '</span></header><div class="meter" aria-label="' + completed + ' of ' + total + ' observed tasks completed"><i style="width:' + percent + '%"></i></div><p class="meter-label">Completed ' + completed + ' / ' + total + ' observed tasks</p><dl><div><dt>First blocker</dt><dd>' + escapeHTML(blocker?.artifact || "None observed") + '</dd></div><div><dt>Latest receipt</dt><dd>' + escapeHTML(receipt?.caption || receipt?.kind || "None received") + '</dd></div></dl>' + subagentDisclosure + '</article>';
  }).join("") : '<p class="empty-state">No observed project or CTRL work in this scope.</p>';
}

function renderEvidenceGallery(nodes) {
  const allowed = new Set(nodes.map((node) => node.id));
  const images = state.proof.filter((item) => allowed.has(item.task_id) && item.evidence_id && item.digest && String(item.media_type || "").startsWith("image/"));
  $("#evidence-note").textContent = images.length ? String(images.length) + " recent image" + (images.length === 1 ? "" : "s") : "No images received";
  $("#evidence-gallery").innerHTML = images.length ? images.slice(0, 6).map((item) => '<figure><img loading="lazy" decoding="async" src="/api/proof-media/' + encodeURIComponent(item.evidence_id) + '?digest=' + encodeURIComponent(item.digest) + '" alt="' + escapeHTML(item.caption || "Evidence image") + '"><figcaption>' + escapeHTML(item.caption || "Image evidence") + '</figcaption></figure>').join("") : '<p class="empty-state">Images appear here when they are received.</p>';
}

function usageSeries() {
  const source = state.usageHistory || {};
  return source.history || source.items || [];
}

function renderUsage() {
  const source = state.usageHistory || {};
  const series = usageSeries();
  const total = Number(source.total_tokens ?? source.tokens ?? source.total ?? source.analytics?.tokens);
  $("#usage-total").textContent = Number.isFinite(total) ? compactNumber(total) : "—";
  $("#usage-note").textContent = series.length ? "Selected scope" : "No recent history";
  drawLine($("#usage-sparkline"), series.map((item) => Number(item.delta_tokens ?? item.tokens ?? item.value) || 0), "#46dfd0");
}

function renderOverview() {
  const nodes = scopedNodes();
  renderMonitoringCards(nodes);
  renderEvidenceGallery(nodes);
  renderUsage();
  $("#sync-time").textContent = state.overview?.generated_at ? "Updated " + formatRelative(state.overview.generated_at) : "Ready";
}

function taskProgress(node) {
  const eta = node.eta || {};
  return Math.max(0, Math.min(100, Number(eta.progress_percent ?? eta.progress ?? (eta.status === "complete" ? 100 : 0)) || 0));
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
    const stalled = ["blocked", "at_risk"].includes(String(current.eta?.status || current.status).toLowerCase());
    const status = statusLabel(current);
    const subagents = subagentDescendants(current.id, tree);
    const subagentMeta = subagents.length ? '<span class="subagent-count">' + subagents.length + ' subagent' + (subagents.length === 1 ? '' : 's') + '</span>' : '';
    return '<article class="hierarchy-card"><div class="health-ring ' + status[1] + '"><i></i><span>' + taskProgress(current) + '%</span></div><div class="hierarchy-main"><div class="hierarchy-title"><strong>' + escapeHTML(current.artifact || current.title || owner) + '</strong><span>' + escapeHTML(current.role_label || current.role || "TASK") + subagentMeta + '</span></div><p><i class="activity-dot ' + status[1] + '" aria-hidden="true"></i>' + escapeHTML(formatRelative(current.updated_at)) + (stalled ? ' <b class="stalled-cue">Paused attention</b>' : '') + '</p><div class="task-progress"><i style="width:' + taskProgress(current) + '%"></i></div>' + (extra.length ? '<details><summary>' + extra.length + ' more task' + (extra.length === 1 ? '' : 's') + '</summary><ul>' + extra.map((task) => '<li>' + escapeHTML(task.artifact || task.title || task.id) + '</li>').join('') + '</ul></details>' : '') + '</div></article>';
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
  const disk = (payload.disks || []).find((item) => item.available) || {};
  const percent = (metric) => metric?.available && Number.isFinite(Number(metric.percent)) ? Math.round(Number(metric.percent)) + "%" : "Unavailable";
  const cards = [
    ["Health", humanize(latest.health_state || "Unknown"), "Current status"],
    ["CPU", percent(payload.cpu), payload.cpu?.available ? "Current load" : "Not available"],
    ["Memory", percent(payload.memory), payload.memory?.available ? formatBytes(payload.memory.used_bytes) + " in use" : "Not available"],
    ["Disk", disk.available ? formatBytes(disk.free_bytes) + " free" : "Unavailable", disk.available ? Math.round(Number(disk.percent) || 0) + "% used · " + (disk.mount || "Device") : "No sample"],
    ["Containers", payload.docker?.available ? String(payload.docker.container_count || 0) : "Unavailable", humanize(payload.docker?.status || "Not available")],
    ["Network", payload.network?.available ? formatBytes((Number(payload.network.rx_bytes) || 0) + (Number(payload.network.tx_bytes) || 0)) : "Unavailable", payload.network?.available ? "Current total" : "Not available"],
    ["SWARM data", state.diagnostics?.storage?.bytes == null ? "Unavailable" : formatBytes(state.diagnostics.storage.bytes), "Saved history"],
  ];
  $("#diagnostic-grid").innerHTML = cards.map(([label, value, note]) => '<article class="metric-card diagnostic-card"><p>' + escapeHTML(label) + '</p><strong>' + escapeHTML(value) + '</strong><span>' + escapeHTML(note) + '</span></article>').join('') + '<article class="panel auto-health"><p class="eyebrow">Automatic care</p><h3>Keep this device healthy</h3><label class="toggle-row"><input id="auto-health" type="checkbox"' + (state.health?.enabled ? ' checked' : '') + '><span>Create maintenance tasks automatically</span></label><small>Starts with a review. SWARM will not delete files or stop work on its own.</small></article>';
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

function renderSettings() {
  const selectedCtrl = state.ctrlId || activeControllers()[0]?.id || '';
  const setting = state.ctrlSettings;
  const storage = state.storage;
  const boost = state.config?.settings?.boost || {};
  const effective = setting?.effective || setting?.global_defaults || {};
  const reasoningOptions = ["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"];
  const retention = storage?.retention_days == null ? "" : " · retain " + storage.retention_days + " days";
  const proofFiles = Number(storage?.proof_files) || 0;
  $("#settings-grid").innerHTML =
    '<section class="panel settings-card"><p class="eyebrow">Console</p><h3>' + escapeHTML(selectedCtrl ? "CTRL settings" : "Global defaults") + '</h3>' +
      '<label class="toggle-row"><input id="ctrl-customize" type="checkbox"' + (setting?.customized ? ' checked' : '') + (!selectedCtrl ? ' disabled' : '') + '><span>Customize this CTRL separately</span></label>' +
      '<small>' + escapeHTML(selectedCtrl ? (setting?.customized ? "Changes apply only to this CTRL." : "This CTRL follows global defaults.") : "Select an active CTRL to customize it.") + '</small>' +
      (setting?.customized ? '<div class="ctrl-fields"><label>Model<input id="ctrl-model" value="' + escapeHTML(effective.model || '') + '" autocomplete="off"></label><label>Reasoning<select id="ctrl-reasoning">' + reasoningOptions.map((option) => '<option value="' + option + '"' + (option === effective.reasoning ? ' selected' : '') + '>' + option + '</option>').join('') + '</select></label></div><button class="quiet-button" data-setting-action="save-ctrl" type="button">Save CTRL settings</button>' : '') +
      '<button class="quiet-button" data-setting-action="reset" type="button"' + (!selectedCtrl || !setting?.customized ? ' disabled' : '') + '>Use global defaults</button></section>' +
    '<section class="panel settings-card"><p class="eyebrow">Work routing</p><h3>Safe small tasks</h3>' +
      '<label class="toggle-row"><input id="spark-enabled" type="checkbox"' + (boost.spark_enabled ? ' checked' : '') + '><span>Use Spark for safe small tasks</span></label>' +
      '<small>Spark handles quick, low-risk work such as search, formatting, copy, documentation, and focused checks.</small>' +
      '<details><summary>Advanced routing</summary><div class="ctrl-fields"><label>Model<input id="spark-model" value="' + escapeHTML(boost.spark_model || 'gpt-5.3-codex-spark') + '" autocomplete="off"></label><label>Reasoning<select id="spark-reasoning">' + reasoningOptions.map((option) => '<option value="' + option + '"' + (option === (boost.spark_reasoning || 'xhigh') ? ' selected' : '') + '>' + option + '</option>').join('') + '</select></label></div><button class="quiet-button" data-setting-action="save-spark" type="button">Save routing</button></details></section>' +
    '<section class="panel settings-card"><p class="eyebrow">Data</p><h3>' + escapeHTML(storage?.bytes == null ? 'Storage details unavailable' : formatBytes(storage.bytes) + ' saved history' + retention) + '</h3><p>Progress, ETAs, proof, and token history stay available between sessions' + (proofFiles ? ' · ' + proofFiles + ' proof file' + (proofFiles === 1 ? '' : 's') : '') + '.</p><div class="settings-actions-inline"><button class="quiet-button" data-setting-action="clear" type="button">Clear history</button><button class="quiet-button" data-setting-action="restore" type="button">Restore defaults</button></div><small>Clearing history leaves your tasks unchanged. Restoring defaults keeps your history.</small></section>';
}

function renderAllViews() { renderOverview(); renderHierarchy(); renderKanban(); renderDiagnostics(); renderSettings(); }

async function refreshProof() {
  const params = new URLSearchParams();
  if (state.projectId !== "all" && !state.projectId.startsWith("ctrl:")) params.set("project_id", state.projectId);
  try {
    const result = await api('/api/proof-feed' + (params.size ? '?' + params.toString() : ''));
    state.proof = result.items || [];
    state.proofSequence = Number(result.sequence) || 0;
  } catch { state.proof = []; }
}

async function refreshUsageHistory() {
  const params = new URLSearchParams({ project_id: state.projectId, ctrl_id: state.ctrlId, hours: "24" });
  try { state.usageHistory = await api('/api/usage-history?' + params.toString()); }
  catch { state.usageHistory = null; }
}

async function refreshMonitoring(proofSequence) {
  try {
    state.overview = await api("/api/overview");
    renderProjectNavigation();
    await refreshUsageHistory();
    if (Number(proofSequence) !== state.proofSequence) await refreshProof();
    renderOverview();
  } catch { /* The next manual refresh can recover the complete screen. */ }
}

async function refreshCtrlSettings() {
  const selectedCtrl = state.ctrlId || activeControllers()[0]?.id || '';
  if (!selectedCtrl) { state.ctrlSettings = null; return; }
  try { state.ctrlSettings = await api('/api/ctrl-settings?ctrl_id=' + encodeURIComponent(selectedCtrl)); }
  catch { state.ctrlSettings = null; }
}

async function refreshOverview(showLoading = true) {
  if (showLoading) setLoading(true);
  clearError();
  try {
    state.overview = await api("/api/overview");
    renderProjectNavigation();
    await Promise.all([refreshProof(), refreshUsageHistory()]);
    const selectedCtrl = state.ctrlId || activeControllers()[0]?.id || '';
    const results = await Promise.allSettled([api('/api/diagnostics'), api('/api/diagnostics/history?limit=24'), api('/api/health/settings'), api('/api/storage'), selectedCtrl ? api('/api/ctrl-settings?ctrl_id=' + encodeURIComponent(selectedCtrl)) : Promise.resolve(null), api('/api/config')]);
    [state.diagnostics, state.diagnosticHistory, state.health, state.storage, state.ctrlSettings, state.config] = results.map((result) => result.status === 'fulfilled' ? result.value : null);
    state.diagnosticHistory = state.diagnosticHistory?.items || [];
    renderAllViews();
  } catch (error) {
    showError(error.message);
  } finally {
    if (showLoading) setLoading(false);
  }
}

async function initialize() {
  try {
    const bootstrap = await api("/api/bootstrap");
    state.token = bootstrap.token || "";
  } catch (error) {
    showError(error.message);
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

$("#project-navigation").addEventListener("click", (event) => {
  const toggle = event.target.closest("[data-project-toggle]");
  if (toggle) {
    const groupId = toggle.dataset.projectToggle;
    state.projectId = state.projectId === groupId ? "all" : groupId;
    state.ctrlId = "";
    renderProjectNavigation();
    renderAllViews();
    Promise.all([refreshProof(), refreshCtrlSettings(), refreshUsageHistory()]).then(renderAllViews);
    return;
  }
  const scope = event.target.closest("[data-project-id]");
  if (!scope) return;
  event.preventDefault();
  state.projectId = scope.dataset.projectId;
  state.ctrlId = scope.dataset.ctrlId || "";
  renderProjectNavigation();
  renderAllViews();
  Promise.all([refreshProof(), refreshCtrlSettings(), refreshUsageHistory()]).then(renderAllViews);
});
$("#refresh").addEventListener("click", refreshOverview);
$("#retry").addEventListener("click", refreshOverview);
document.addEventListener('change', async (event) => {
  if (event.target.id === 'auto-health') {
    try { state.health = await api('/api/health/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: event.target.checked }) }); renderDiagnostics(); } catch (error) { showError(error.message); renderDiagnostics(); }
    return;
  }
  if (event.target.id === 'spark-enabled') {
    try { state.config = await api('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ changes: { 'boost.spark_enabled': event.target.checked } }) }); renderSettings(); } catch (error) { showError(error.message); renderSettings(); }
    return;
  }
  if (event.target.id === 'ctrl-customize') {
    if (!state.ctrlSettings) return;
    try {
      if (event.target.checked) {
        const defaults = state.ctrlSettings.global_defaults || {};
        state.ctrlSettings = await api('/api/ctrl-settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ctrl_id: state.ctrlSettings.ctrl_id, expected_revision: state.ctrlSettings.revision, changes: { model: defaults.model, reasoning: defaults.reasoning, service_tier: defaults.service_tier || '' } }) });
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
  const messages = { clear: 'Clear saved SWARM history? Your tasks will stay unchanged.', restore: 'Restore default settings? Your history will stay unchanged.', reset: 'Use global defaults for this CTRL?' };
  if (messages[action] && !confirm(messages[action])) return;
  try {
    if (action === 'clear') await api('/api/storage/clear', { method: 'POST' });
    if (action === 'restore') await api('/api/settings/restore', { method: 'POST' });
    if (action === 'reset' && state.ctrlSettings) await api('/api/ctrl-settings/reset', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ctrl_id: state.ctrlSettings.ctrl_id, expected_revision: state.ctrlSettings.revision }) });
    if (action === 'save-ctrl' && state.ctrlSettings) state.ctrlSettings = await api('/api/ctrl-settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ctrl_id: state.ctrlSettings.ctrl_id, expected_revision: state.ctrlSettings.revision, changes: { model: $('#ctrl-model').value.trim(), reasoning: $('#ctrl-reasoning').value } }) });
    if (action === 'save-spark') state.config = await api('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ changes: { 'boost.spark_model': $('#spark-model').value.trim(), 'boost.spark_reasoning': $('#spark-reasoning').value } }) });
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

initialize().then(startPresence);
