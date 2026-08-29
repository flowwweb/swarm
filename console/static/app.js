const state = { token: "", overview: null, proof: [], proofCollections: new Map(), proofStatuses: new Map(), proofStatus: "idle", proofSequence: 0, usageHistory: null, usageWindowHours: 24, usageScopeKey: "", usageStatus: "idle", usageError: "", projectProgress: null, projectProgressProjectId: "", projectProgressStatus: "idle", projectProgressError: "", projectProgressFeed: null, projectProgressFeedProjectId: "", projectProgressFeedStatus: "idle", projectProgressFeedError: "", projectTab: "overview", runLogs: new Map(), runLogRequestGenerations: new Map(), runLogSurfaceStates: new Map(), runLogAgent: null, diagnostics: null, health: null, storage: null, config: null, configStatus: "idle", configError: "", chatRelaySaving: false, ctrlSettings: null, auto: null, autoBindingKey: "", autoStatus: "idle", autoError: "", autoSaving: false, skills: null, skillsError: "", roleManifests: null, roleManifestStatus: "unavailable", roleManifestError: "", roleManifestMessage: "", roleManifestSaving: false, roleManifestRetry: null, roleEditorMode: "", agentsTab: "active", roleEditorTrigger: null, roleSearch: "", roleTypes: new Set(["builtin", "custom"]), roleSearchFields: new Set(["profession", "specialization", "alias", "skills", "purpose"]), selectedRoleId: "", assetView: "grid", selectedAssetIdentity: "", onboardingStep: 0, onboardingShown: false, onboardingTrigger: null, notifications: null, notificationBindingKey: "", notificationStatus: "idle", notificationError: "", notificationAckFlight: null, notificationRequestGenerations: new Map(), notificationPresentedIds: new Set(), notificationToast: null, notificationToastTimer: null, notificationTrigger: null, connectionStatus: "reconnecting", view: "overview", projectId: "all", ctrlId: "", settingsCtrlId: "", settingsScopeType: "", settingsScopeId: "", evidenceImages: [], evidenceIndex: 0, evidenceTrigger: null };
const EVIDENCE_THUMBNAIL_PAGE_SIZE = 24;
const USAGE_WINDOW_LABELS = { 1: "1h", 24: "1d" };
const RUN_LOG_CLIENT_LIMIT = 200;
const ONBOARDING_PRESENTATION_KEY = "swarm.onboarding.v1.seen";
const ONBOARDING_STEPS = [
  { name: "Welcome", primary: "Start guided tour" },
  { name: "Owned lanes", primary: "Continue" },
  { name: "Proof gates", primary: "Open Projects" },
];
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function runLogBindingKey(binding) {
  return binding ? [binding.projectId, binding.ctrlId, binding.agentId || ""].join("|") : "";
}

function runLogPlanBindingKey(plan) {
  return JSON.stringify((plan?.bindings || []).map(runLogBindingKey).filter(Boolean).sort());
}

function runLogSurfaceStateKey(surface, bindingKey) {
  return String(surface || "") + "|" + String(bindingKey || "");
}

function runLogItemIdentity(item) {
  const eventId = String(item?.event_id || "").trim();
  const digest = String(item?.event_digest || "").trim();
  return eventId && digest ? eventId + "|" + digest : "";
}

function runLogResponseMatches(result, binding) {
  const scope = result?.scope;
  return result?.ok === true
    && scope?.project_id === binding?.projectId
    && scope?.ctrl_id === binding?.ctrlId
    && String(scope?.agent_id || "") === String(binding?.agentId || "")
    && Array.isArray(result.items);
}

function mergeRunLogItems(previous, incoming, replace = false, limit = RUN_LOG_CLIENT_LIMIT) {
  const prior = Array.isArray(previous) ? previous : [];
  const existing = replace ? [] : prior;
  const knownIdentities = new Set(prior.map(runLogItemIdentity).filter(Boolean));
  const byIdentity = new Map();
  existing.forEach((item) => {
    const identity = runLogItemIdentity(item);
    if (identity) byIdentity.set(identity, item);
  });
  const addedItems = [];
  (Array.isArray(incoming) ? incoming : []).forEach((item) => {
    const identity = runLogItemIdentity(item);
    const sequence = Number(item?.event_seq);
    if (!identity || !Number.isInteger(sequence) || sequence <= 0 || !String(item?.summary || "").trim()) return;
    if (!knownIdentities.has(identity)) {
      addedItems.push(item);
      knownIdentities.add(identity);
    }
    byIdentity.set(identity, item);
  });
  const items = [...byIdentity.values()]
    .sort((left, right) => Number(left.event_seq) - Number(right.event_seq) || runLogItemIdentity(left).localeCompare(runLogItemIdentity(right)))
    .slice(-Math.max(1, Number(limit) || RUN_LOG_CLIENT_LIMIT));
  const retainedIdentities = new Set(items.map(runLogItemIdentity));
  const retainedAddedItems = addedItems.filter((item) => retainedIdentities.has(runLogItemIdentity(item)));
  return { items, added: retainedAddedItems.length, addedItems: retainedAddedItems };
}

function runLogNearBottom(scrollHeight, scrollTop, clientHeight, threshold = 48) {
  return Number(scrollHeight) - Number(scrollTop) - Number(clientHeight) <= threshold;
}

function runLogAnnouncement(items) {
  const appended = (Array.isArray(items) ? items : [])
    .filter((item) => runLogItemIdentity(item) && String(item?.summary || "").trim())
    .sort((left, right) => Number(left.event_seq) - Number(right.event_seq));
  if (!appended.length) return "";
  const latest = appended[appended.length - 1];
  if (appended.length === 1) return "New run log entry " + String(latest.event_seq) + ": " + String(latest.summary).trim();
  return String(appended.length) + " new run log entries. Latest, " + String(latest.event_seq) + ": " + String(latest.summary).trim();
}

function runLogReplaceSnapshot(previous, retention) {
  return previous?.initialized !== true || retention?.stale_cursor === true;
}

function runLogCanAnnounce(previous, replace) {
  return previous?.initialized === true && !replace;
}

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
  setDataStatus("unavailable", state.overview?.generated_at);
  setNotificationsOpen(false);
  dismissNotificationToast(false);
  $(".app-shell").classList.add("is-disconnected");
  $(".workspace").classList.add("is-disconnected");
  $("#connection-state").hidden = false;
}

function clearConnectionState() {
  $(".app-shell").classList.remove("is-disconnected");
  $(".workspace").classList.remove("is-disconnected");
  $("#connection-state").hidden = true;
}

function renderOnboarding() {
  const step = Math.min(Math.max(0, state.onboardingStep), ONBOARDING_STEPS.length - 1);
  state.onboardingStep = step;
  $$('[data-onboarding-step]').forEach((dot, index) => {
    const selected = index === step;
    dot.classList.toggle("is-current", selected);
    dot.setAttribute("aria-selected", String(selected));
    dot.toggleAttribute("aria-current", selected);
    if (selected) dot.setAttribute("aria-current", "step");
    dot.tabIndex = selected ? 0 : -1;
  });
  $$('[data-onboarding-panel]').forEach((panel, index) => {
    const selected = index === step;
    panel.hidden = !selected;
    panel.classList.toggle("is-active", selected);
  });
  const current = ONBOARDING_STEPS[step];
  $("#onboarding-step-status").textContent = current.name + ". Step " + String(step + 1) + " of " + String(ONBOARDING_STEPS.length) + ".";
  $("#onboarding-back").hidden = step === 0;
  $("#onboarding-primary").textContent = current.primary;
}

function onboardingSeen(storage = window.localStorage) {
  try { return storage.getItem(ONBOARDING_PRESENTATION_KEY) === "1"; }
  catch { return false; }
}

function markOnboardingSeen(storage = window.localStorage) {
  try { storage.setItem(ONBOARDING_PRESENTATION_KEY, "1"); }
  catch { /* Presentation state remains safely ephemeral when storage is unavailable. */ }
}

function openOnboarding(force = false, trigger = null) {
  if ((!force && (state.onboardingShown || onboardingSeen())) || !state.overview || $(".workspace").classList.contains("is-disconnected")) return;
  state.onboardingShown = true;
  state.onboardingStep = 0;
  state.onboardingTrigger = trigger || (document.activeElement instanceof HTMLElement && document.activeElement !== document.body ? document.activeElement : $("#tab-overview"));
  renderOnboarding();
  const dialog = $("#onboarding-dialog");
  if (!dialog.open) dialog.showModal();
  requestAnimationFrame(() => $("#onboarding-primary").focus({ preventScroll: true }));
}

function closeOnboarding(openProjects = false) {
  markOnboardingSeen();
  const dialog = $("#onboarding-dialog");
  if (dialog.open) dialog.close();
  if (openProjects) setView("overview", false);
}

function setOnboardingStep(step, focusDot = false) {
  state.onboardingStep = Math.min(Math.max(0, Number(step) || 0), ONBOARDING_STEPS.length - 1);
  renderOnboarding();
  if (focusDot) $('[data-onboarding-step="' + state.onboardingStep + '"]')?.focus({ preventScroll: true });
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
    if (!response.ok) {
      const requestError = new Error(data.error || "Request failed (" + response.status + ")");
      requestError.status = response.status;
      throw requestError;
    }
    return data;
  } catch (error) {
    if (error?.name === "AbortError") throw connectionFailure("Project data request timed out");
    if (error instanceof TypeError) throw connectionFailure("SWARM cannot reach its local console");
    throw error;
  } finally {
    if (timeout) window.clearTimeout(timeout);
  }
}

function systemHealthPresentation() {
  if (state.connectionStatus === "offline") return { label: "Offline", className: "is-offline", note: "The local console is unavailable." };
  if (state.connectionStatus === "reconnecting") return { label: "Reconnecting", className: "is-reconnecting", note: "Waiting for a fresh console response." };
  const diagnostics = state.diagnostics;
  if (!diagnostics?.ok) return { label: "Unknown", className: "", note: "Diagnostics are unavailable." };
  const incidents = Array.isArray(diagnostics.health?.incidents) ? diagnostics.health.incidents.length : 0;
  const requests = Array.isArray(diagnostics.health?.open_requests) ? diagnostics.health.open_requests.length : 0;
  const reported = String(diagnostics.latest?.payload?.health_state || "").trim().toUpperCase();
  if (diagnostics.config_valid === false || incidents || requests || (reported && !["HEALTHY", "OK"].includes(reported))) {
    const count = incidents + requests;
    return { label: "Needs attention", className: "is-attention", note: count ? count + " open health signal" + (count === 1 ? "" : "s") + "." : "The latest diagnostic state needs attention." };
  }
  if (["HEALTHY", "OK"].includes(reported)) return { label: "Healthy", className: "is-live", note: "The latest diagnostic receipt reports healthy." };
  return { label: "Unknown", className: "", note: "No current health receipt is available." };
}

function renderSystemHealth() {
  const presentation = systemHealthPresentation();
  const control = $("#system-health-control");
  if (control) {
    control.classList.remove("is-live", "is-reconnecting", "is-offline", "is-attention");
    if (presentation.className) control.classList.add(presentation.className);
    control.setAttribute("aria-label", "System health: " + presentation.label);
    control.title = "System health: " + presentation.label;
  }
  const chromeDot = $("#snapshot-status-dot");
  if (chromeDot) chromeDot.className = "status-dot" + (presentation.className ? " " + presentation.className : "");
  const panel = $("#system-health-panel");
  if (panel) {
    $("#system-health-state").textContent = presentation.label;
    $("#system-health-note").textContent = presentation.note;
    const dot = $("#system-health-panel-dot");
    dot.className = "status-dot" + (presentation.className ? " " + presentation.className : "");
  }
}

function openSystemHealth() {
  setView("settings");
  requestAnimationFrame(() => {
    const panel = $("#system-health-panel");
    panel?.scrollIntoView({ block: "nearest" });
    panel?.focus({ preventScroll: true });
  });
}

function setDataStatus(status, observedAt = null) {
  const title = $("#data-status-title");
  const note = $("#data-status-note");
  const dot = $("#data-status-dot");
  const snapshotDot = $("#snapshot-status-dot");
  const snapshot = $("#sync-time");
  if (!title || !note || !dot || !snapshotDot || !snapshot) return;
  const connection = status === "current" ? "live" : status === "unavailable" ? "offline" : "reconnecting";
  state.connectionStatus = connection;
  [dot, snapshotDot].forEach((item) => {
    item.classList.toggle("is-live", connection === "live");
    item.classList.toggle("is-reconnecting", connection === "reconnecting");
    item.classList.toggle("is-offline", connection === "offline");
  });
  if (connection === "live") {
    title.textContent = "Live";
    note.textContent = observedAt ? "Updated " + formatRelative(observedAt) : "Snapshot received";
    snapshot.textContent = observedAt ? "Live · " + formatRelative(observedAt) : "Live";
  } else if (connection === "reconnecting") {
    title.textContent = "Reconnecting";
    note.textContent = observedAt ? "Last update " + formatRelative(observedAt) : "Waiting for data";
    snapshot.textContent = "Reconnecting";
  } else {
    title.textContent = "Offline";
    note.textContent = observedAt ? "Last update " + formatRelative(observedAt) : "Console unavailable";
    snapshot.textContent = "Offline";
  }
  renderSystemHealth();
  renderNotifications();
  renderRunLogSurfaces();
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

const mobileDrawerQuery = window.matchMedia("(max-width: 620px)");

function mobileDrawerFocusable() {
  return Array.from($("#console-drawer").querySelectorAll('a[href], button:not([disabled]):not([tabindex="-1"]), [tabindex]:not([tabindex="-1"])'))
    .filter((element) => !element.hidden && !element.closest("[hidden]") && !element.inert && element.getClientRects().length);
}

function setMobileDrawer(open, restoreFocus = false) {
  const shell = $(".app-shell");
  const drawer = $("#console-drawer");
  const trigger = $("#mobile-menu-button");
  const backdrop = $("#drawer-backdrop");
  const workspace = $(".workspace");
  const expanded = Boolean(open && mobileDrawerQuery.matches);
  shell.classList.toggle("is-drawer-open", expanded);
  trigger.setAttribute("aria-expanded", String(expanded));
  trigger.setAttribute("aria-label", expanded ? "Close navigation" : "Open navigation");
  backdrop.hidden = !expanded;
  document.body.classList.toggle("drawer-open", expanded);
  workspace.inert = expanded;
  if (mobileDrawerQuery.matches) {
    drawer.setAttribute("aria-hidden", String(!expanded));
    drawer.inert = !expanded;
  } else {
    drawer.setAttribute("aria-hidden", "false");
    drawer.inert = false;
  }
  if (expanded) requestAnimationFrame(() => ($(".nav-item.is-active") || mobileDrawerFocusable()[0])?.focus());
  else if (restoreFocus && mobileDrawerQuery.matches) trigger.focus({ preventScroll: true });
}

function syncMobileDrawer() {
  setMobileDrawer(false);
}

function routeView() {
  const view = location.hash.slice(1);
  return ["overview", "agents", "review", "assets", "settings"].includes(view) ? view : "overview";
}

function setView(view, focus, syncRoute = true) {
  const allowed = ["overview", "agents", "review", "assets", "settings"];
  const selectedView = allowed.includes(view) ? view : "overview";
  state.view = selectedView;
  const titles = {
    overview: ["Overview", "Portfolio progress and project scope."],
    agents: ["Agents", "Active ownership and the role library."],
    review: ["Review", "Proof, decisions, and handoff acknowledgements."],
    assets: ["Assets", "Approved project and role assets."],
    settings: ["Settings", "Defaults and optional per-CTRL overrides."],
  };
  $(".app-shell").dataset.currentView = selectedView;
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
  const project = state.projectId !== "all" && !state.ctrlId ? projectGroups().find((item) => item.id === state.projectId) : null;
  $("#view-title").textContent = selectedView === "overview" && project ? project.label : titles[selectedView][0];
  $("#view-subtitle").textContent = selectedView === "overview" && project ? "Project progress, proof, ownership, and ledger." : titles[selectedView][1];
  if (selectedView === 'settings' && (!state.skills || state.skillsError)) refreshSkills().then(renderSettings);
  if (selectedView === 'settings' && state.token) refreshAutoStatus().then(renderSettings);
  if (syncRoute && location.hash !== '#' + selectedView) history.replaceState(null, '', '#' + selectedView);
  if (focus) $("#tab-" + selectedView)?.focus({ preventScroll: true });
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

const PROJECT_NAVIGATION_STATUS_RANK = { active: 0, stalled: 1, inactive: 2 };

function projectNavigationStatus(project) {
  const projectStatus = String(project.status || "").toLowerCase();
  const controllerStatuses = (state.overview?.navigation?.controllers || [])
    .filter((controller) => controller.visibility === "visible" && controller.archived === false && controller.project_id === project.id && project.ctrl_ids.includes(controller.id))
    .map((controller) => String(controller.status || "").toLowerCase());
  if (project.active_ctrl === true) return "active";
  if (projectStatus === "stalled" || controllerStatuses.includes("stalled")) return "stalled";
  if (project.active_ctrl === false) return "inactive";
  return [projectStatus, ...controllerStatuses].some((status) => ["active", "running", "in_progress"].includes(status)) ? "active" : "inactive";
}

function projectNavigationEntries() {
  const summaries = new Map((state.overview?.projects || []).map((project) => [project.id, project]));
  return currentWorkProjects()
    .map((project) => {
      const summary = summaries.get(project.id) || {};
      return {
        id: project.id,
        label: publicLabel(project.goal_label || project.name || summary.goal_label || summary.name, "Untitled project"),
        status: projectNavigationStatus(project),
      };
    })
    .sort((a, b) => PROJECT_NAVIGATION_STATUS_RANK[a.status] - PROJECT_NAVIGATION_STATUS_RANK[b.status] || a.label.localeCompare(b.label) || a.id.localeCompare(b.id));
}

function scopeLabel() {
  if (state.projectId === "all") return "All projects";
  const group = projectGroups().find((item) => item.id === state.projectId);
  const ctrl = historicalControllers().find((item) => item.id === state.ctrlId);
  return ctrl && state.ctrlId ? ctrlLabel(ctrl) : (group?.label || "All projects");
}

function renderProjectNavigation() {
  const projects = projectNavigationEntries();
  if (state.projectId !== "all" && !projects.some((project) => project.id === state.projectId)) {
    state.projectId = "all";
    state.ctrlId = "";
  }
  const entries = ['<button class="project-scope-button ' + (state.projectId === "all" ? "is-selected" : "") + '" data-project-id="all" type="button" aria-pressed="' + (state.projectId === "all") + '"><span aria-hidden="true">◇</span>All projects</button>'];
  projects.forEach((project) => {
    const current = state.projectId === project.id && !state.ctrlId;
    const statusLabel = project.status[0].toUpperCase() + project.status.slice(1);
    entries.push('<button class="project-scope-button ' + (current ? "is-selected" : "") + '" data-project-id="' + escapeHTML(project.id) + '" type="button" aria-label="' + escapeHTML(project.label + ", " + statusLabel) + '" aria-pressed="' + current + '"><span class="scope-dot is-' + project.status + '" aria-hidden="true"></span><span class="project-scope-label" title="' + escapeHTML(project.label) + '">' + escapeHTML(project.label) + '</span></button>');
  });
  $("#project-navigation").innerHTML = entries.join("");
  const selector = $("#project-scope-filter");
  if (selector) {
    selector.innerHTML = ['<option value="all">All projects</option>'].concat(projects.map((project) => '<option value="' + escapeHTML(project.id) + '">' + escapeHTML(project.label) + '</option>')).join("");
    selector.value = state.projectId === "all" || projects.some((project) => project.id === state.projectId) ? state.projectId : "all";
  }
}

function runLogBindingForCtrl(ctrlId, agentId = "") {
  const ctrl = currentWorkControllers().find((item) => item.id === ctrlId);
  const project = currentWorkProjects().find((item) => item.id === ctrl?.project_id && item.ctrl_ids.includes(ctrlId));
  return project && ctrl ? { projectId: project.id, ctrlId, agentId: String(agentId || "") } : null;
}

function runLogBindingsForProject(projectId) {
  const project = currentWorkProjects().find((item) => item.id === projectId);
  if (!project) return [];
  return project.ctrl_ids.map((ctrlId) => runLogBindingForCtrl(ctrlId)).filter(Boolean);
}

function currentRunLogAgent() {
  const selection = state.runLogAgent;
  if (!selection || (state.projectId !== "all" && state.projectId !== selection.projectId)) return null;
  const binding = runLogBindingForCtrl(selection.ctrlId, selection.agentId);
  if (!binding || binding.projectId !== selection.projectId) return null;
  const eligible = (state.overview?.nodes || []).some((node) => {
    const inCtrl = node.id === binding.ctrlId || (node.controller_ids || []).includes(binding.ctrlId);
    const agentId = String(node.owner_id || node.id || "");
    return node.project_id === binding.projectId && inCtrl && agentId === binding.agentId;
  });
  return eligible ? { ...selection, ...binding } : null;
}

function runLogSurfacePlans() {
  const plans = new Map();
  const overviewBinding = state.ctrlId ? runLogBindingForCtrl(state.ctrlId) : null;
  if (overviewBinding) plans.set("overview", { title: "Current CTRL", bindings: [overviewBinding] });
  const projectId = selectedProgressProjectId();
  const projectBindings = projectId && state.projectTab === "logs" ? runLogBindingsForProject(projectId) : [];
  if (projectId && state.projectTab === "logs") plans.set("project", { title: projectBindings.length <= 1 ? "Project run log" : "Project run log · " + projectBindings.length + " CTRLs", bindings: projectBindings, bindingUnavailable: !projectBindings.length });
  const agent = state.view === "agents" && state.agentsTab === "active" ? currentRunLogAgent() : null;
  if (agent) plans.set("agent", { title: agent.label || "Selected agent", bindings: [agent] });
  return plans;
}

function runLogSurfaceState(surface, bindingKey) {
  const key = runLogSurfaceStateKey(surface, bindingKey);
  const prefix = String(surface || "") + "|";
  if (!state.runLogSurfaceStates.has(key)) {
    [...state.runLogSurfaceStates.keys()].filter((candidate) => candidate.startsWith(prefix)).forEach((candidate) => state.runLogSurfaceStates.delete(candidate));
    state.runLogSurfaceStates.set(key, { nearBottom: true, newEntries: 0, pendingAnnouncements: [], announcement: "", announcementRevision: 0 });
  }
  return state.runLogSurfaceStates.get(key);
}

function runLogEntries(plan) {
  const byIdentity = new Map();
  plan.bindings.forEach((binding) => {
    const record = state.runLogs.get(runLogBindingKey(binding));
    (record?.items || []).forEach((item) => byIdentity.set(runLogItemIdentity(item), item));
  });
  return [...byIdentity.values()]
    .sort((left, right) => Number(left.event_seq) - Number(right.event_seq) || runLogItemIdentity(left).localeCompare(runLogItemIdentity(right)))
    .slice(-RUN_LOG_CLIENT_LIMIT);
}

function runLogPresentation(plan) {
  const records = plan.bindings.map((binding) => state.runLogs.get(runLogBindingKey(binding))).filter(Boolean);
  const items = runLogEntries(plan);
  const loading = records.some((record) => ["loading", "refreshing"].includes(record.status));
  const failed = records.some((record) => ["stale", "unavailable"].includes(record.status));
  const offline = state.connectionStatus !== "live";
  const retention = records.map((record) => record.retention || {}).filter(Boolean);
  let message = items.length ? String(items.length) + " retained material entr" + (items.length === 1 ? "y" : "ies") : "No retained material events in this scope.";
  if (plan.bindingUnavailable) message = "Run log needs a current host-confirmed CTRL binding.";
  else if (loading && !items.length) message = "Loading retained material events.";
  else if (offline && items.length) message = "Offline · showing the last received entries.";
  else if (offline) message = "Run log unavailable while the console reconnects.";
  else if (failed && items.length) message = "Showing the last received entries · refresh unavailable.";
  else if (failed) message = "Run log unavailable. Refresh to try again.";
  else if (loading) message = "Refreshing · last received entries remain visible.";
  const notices = [];
  if (retention.some((item) => item.stale_cursor)) notices.push("Cursor reset to the retained range");
  if (retention.some((item) => item.page_truncated || item.source_scan_truncated)) notices.push("Showing a bounded retained window");
  return { items, message, notices, stale: offline || failed, loading };
}

function runLogEntryMarkup(item) {
  const observed = Number(item.observed_at_ms);
  const datetime = Number.isFinite(observed) && observed > 0 ? new Date(observed).toISOString() : "";
  const owner = item.owner_id || item.task_id || "Unknown owner";
  const detail = [humanize(item.structural_role || item.profession || "Agent"), humanize(item.kind || item.status || "Material event")].filter(Boolean).join(" · ");
  return '<li data-run-log-entry="' + escapeHTML(runLogItemIdentity(item)) + '"><time datetime="' + escapeHTML(datetime) + '">' + escapeHTML(formatRelative(observed)) + '</time><div><strong>' + escapeHTML(owner) + '</strong><span>' + escapeHTML(detail) + '</span></div><p>' + escapeHTML(item.summary) + '</p></li>';
}

function captureRunLogViewport(mount) {
  const scroller = $(".run-log-list", mount);
  if (!scroller) return null;
  const nearBottom = runLogNearBottom(scroller.scrollHeight, scroller.scrollTop, scroller.clientHeight);
  const top = scroller.getBoundingClientRect().top;
  const anchor = $$("[data-run-log-entry]", scroller).find((row) => row.getBoundingClientRect().bottom > top + 1);
  return { nearBottom, scrollTop: scroller.scrollTop, anchorIdentity: anchor?.dataset.runLogEntry || "", anchorOffset: anchor ? anchor.getBoundingClientRect().top - top : 0 };
}

function restoreRunLogViewport(mount, viewport) {
  const scroller = $(".run-log-list", mount);
  if (!scroller) return;
  if (!viewport || viewport.nearBottom) {
    scroller.scrollTop = scroller.scrollHeight;
    return;
  }
  const anchor = $$("[data-run-log-entry]", scroller).find((row) => row.dataset.runLogEntry === viewport.anchorIdentity);
  if (anchor) scroller.scrollTop += anchor.getBoundingClientRect().top - scroller.getBoundingClientRect().top - viewport.anchorOffset;
  else scroller.scrollTop = Math.min(viewport.scrollTop, Math.max(0, scroller.scrollHeight - scroller.clientHeight));
}

function ensureRunLogShell(mount, surface) {
  if ($(".run-log-list", mount)) return;
  const headingId = "run-log-" + surface + "-heading";
  const statusId = "run-log-" + surface + "-status";
  mount.innerHTML = '<header class="run-log-head"><div><p class="eyebrow">Run log</p><h2 id="' + headingId + '"></h2></div><p id="' + statusId + '"></p></header><div class="run-log-frame"><ol class="run-log-list" role="log" aria-labelledby="' + headingId + '" aria-describedby="' + statusId + '" tabindex="0"></ol><button class="run-log-new quiet-button" type="button" data-run-log-latest="' + escapeHTML(surface) + '" hidden></button></div><p class="run-log-announcer sr-only" role="status" aria-live="polite" aria-atomic="true"></p><p class="run-log-notice" hidden></p>';
}

function renderRunLogSurfaces() {
  const plans = runLogSurfacePlans();
  $$('[data-run-log-surface]').forEach((mount) => {
    const surface = mount.dataset.runLogSurface;
    const plan = plans.get(surface);
    if (!plan) {
      mount.hidden = true;
      return;
    }
    ensureRunLogShell(mount, surface);
    const bindingKey = runLogPlanBindingKey(plan);
    const sameBinding = mount.dataset.runLogBindingKey === bindingKey;
    const surfaceState = runLogSurfaceState(surface, bindingKey);
    const viewport = sameBinding ? captureRunLogViewport(mount) : null;
    if (viewport) surfaceState.nearBottom = viewport.nearBottom;
    mount.dataset.runLogBindingKey = bindingKey;
    const presentation = runLogPresentation(plan);
    const heading = $(".run-log-head h2", mount);
    const status = $(".run-log-head > p", mount);
    const list = $(".run-log-list", mount);
    const latest = $("[data-run-log-latest]", mount);
    const announcer = $(".run-log-announcer", mount);
    const notice = $(".run-log-notice", mount);
    mount.hidden = false;
    heading.textContent = plan.title;
    status.textContent = presentation.message;
    status.classList.toggle("is-stale", presentation.stale);
    list.innerHTML = presentation.items.length ? presentation.items.map(runLogEntryMarkup).join("") : '<li class="empty-state">' + escapeHTML(presentation.message) + '</li>';
    latest.textContent = String(surfaceState.newEntries) + " new " + (surfaceState.newEntries === 1 ? "entry" : "entries");
    latest.hidden = !surfaceState.newEntries;
    notice.textContent = presentation.notices.join(" · ");
    notice.hidden = !presentation.notices.length;
    if (surfaceState.pendingAnnouncements.length) {
      const byIdentity = new Map(surfaceState.pendingAnnouncements.map((item) => [runLogItemIdentity(item), item]));
      surfaceState.announcement = runLogAnnouncement([...byIdentity.values()]);
      surfaceState.announcementRevision += 1;
      surfaceState.pendingAnnouncements = [];
    }
    if (announcer.dataset.revision !== String(surfaceState.announcementRevision)) {
      announcer.textContent = surfaceState.announcement;
      announcer.dataset.revision = String(surfaceState.announcementRevision);
    }
    restoreRunLogViewport(mount, viewport);
  });
}

function markRunLogNewEntries(bindingKey, items) {
  if (!items?.length) return;
  runLogSurfacePlans().forEach((plan, surface) => {
    if (!plan.bindings.some((binding) => runLogBindingKey(binding) === bindingKey)) return;
    const view = runLogSurfaceState(surface, runLogPlanBindingKey(plan));
    view.pendingAnnouncements.push(...items);
    if (!view.nearBottom) view.newEntries += items.length;
  });
}

async function refreshRunLogBinding(binding) {
  const key = runLogBindingKey(binding);
  const previous = state.runLogs.get(key) || { initialized: false, items: [], cursor: 0, retention: null, status: "idle", error: "" };
  const generation = (state.runLogRequestGenerations.get(key) || 0) + 1;
  state.runLogRequestGenerations.set(key, generation);
  state.runLogs.set(key, { ...previous, status: previous.items.length ? "refreshing" : "loading", error: "" });
  const params = new URLSearchParams({ ctrl_id: binding.ctrlId, project_id: binding.projectId, after_cursor: String(previous.cursor || 0) });
  if (binding.agentId) params.set("agent_id", binding.agentId);
  try {
    const result = await api("/api/run-log?" + params.toString());
    if (state.runLogRequestGenerations.get(key) !== generation) return;
    if (!runLogResponseMatches(result, binding)) throw new Error("Run log scope did not match the selected surface.");
    if (!result.items.every((item) => item.project_id === binding.projectId && item.ctrl_id === binding.ctrlId)) throw new Error("Run log entry escaped the selected CTRL scope.");
    const nextCursor = Number(result.cursor?.next_event_seq);
    if (!Number.isInteger(nextCursor) || nextCursor < 0) throw new Error("Run log cursor was invalid.");
    const replace = runLogReplaceSnapshot(previous, result.retention);
    const merged = mergeRunLogItems(previous.items, result.items, replace);
    state.runLogs.set(key, { initialized: true, items: merged.items, cursor: nextCursor, retention: result.retention || null, status: "current", error: "" });
    if (runLogCanAnnounce(previous, replace)) markRunLogNewEntries(key, merged.addedItems);
  } catch (error) {
    if (state.runLogRequestGenerations.get(key) !== generation) return;
    state.runLogs.set(key, { ...previous, status: previous.items.length ? "stale" : "unavailable", error: error.message || "Run log unavailable" });
  }
}

async function refreshRunLogs() {
  const bindings = new Map();
  runLogSurfacePlans().forEach((plan) => plan.bindings.forEach((binding) => bindings.set(runLogBindingKey(binding), binding)));
  if (!bindings.size) {
    renderRunLogSurfaces();
    return;
  }
  const requests = [...bindings.values()].map(refreshRunLogBinding);
  renderRunLogSurfaces();
  await Promise.all(requests);
  renderRunLogSurfaces();
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

function scopedProofItems(nodes = scopedNodes()) {
  const items = dedupeProofItems(currentProofItems());
  if (state.ctrlId) {
    const allowed = new Set(nodes.map((node) => node.id));
    return items.filter((item) => allowed.has(item.task_id));
  }
  if (state.projectId !== "all" && !state.projectId.startsWith("ctrl:")) {
    return items.filter((item) => !item.project_id || item.project_id === state.projectId);
  }
  return items;
}

function evidenceImagesFor(nodes) {
  return scopedProofItems(nodes).filter((item) => String(item.media_type || "").startsWith("image/"));
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
  $("#usage-note").textContent = !scopeMatches || state.usageStatus === "loading" ? "Loading usage history" : state.usageStatus === "stale" ? "Last received usage · refresh failed" : state.usageStatus === "error" ? (state.usageError || "Usage history unavailable") : source.status === 'no_data' ? 'No persisted usage in this scope' : source.status === 'partial' ? ('Partial coverage' + (coverage ? ' · ' + coverage : '')) : source.status === 'ok' ? ('Complete coverage' + (coverage ? ' · ' + coverage : '')) : (series.length ? 'Usage status unavailable' : 'No recent history');
  $$('[data-usage-hours]').forEach((button) => {
    const selected = Number(button.dataset.usageHours) === state.usageWindowHours;
    button.classList.toggle('is-selected', selected);
    button.setAttribute('aria-pressed', String(selected));
  });
  drawLine($("#usage-sparkline"), downsampleSeries(values), "#ff9c3d");
  drawLine($("#usage-rate-sparkline"), downsampleSeries(rates), "#46dfd0");
}

function verifiedYieldProjection() {
  return state.usageHistory?.verified_yield && state.usageScopeKey === usageRequestKey()
    ? state.usageHistory.verified_yield
    : null;
}

function verifiedYieldItem(type, id = "") {
  const projection = verifiedYieldProjection();
  if (!projection) return null;
  if (type === "portfolio") return projection.portfolio || null;
  const collection = type === "project" ? projection.projects : type === "task" ? projection.tasks : projection.owners;
  return (collection || []).find((item) => item.scope?.id === id) || null;
}

function yieldValue(item) {
  const value = Number(item?.yield_per_100k);
  return item?.measurement_state === "MEASURED" && Number.isFinite(value)
    ? new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value)
    : "—";
}

function yieldSeries(item) {
  return (item?.series || []).map((sample) => Number(sample.yield_per_100k)).filter(Number.isFinite);
}

function miniSparkline(values, label) {
  const series = values.length ? values : [0, 0];
  const high = Math.max(1, ...series);
  const points = series.map((value, index) => ((index / Math.max(1, series.length - 1)) * 88).toFixed(1) + "," + (24 - (value / high) * 20).toFixed(1)).join(" ");
  return '<svg class="mini-sparkline" viewBox="0 0 88 28" preserveAspectRatio="none" role="img" aria-label="' + escapeHTML(label) + '"><polyline points="' + points + '"></polyline></svg>';
}

function yieldHealth(item) {
  if (!item || item.measurement_state !== "MEASURED") return "Unmeasured";
  const confidence = item.confidence === "HIGH" ? "Complete receipts" : item.confidence === "PARTIAL" ? "Partial receipts" : "Confidence unknown";
  const rework = Number(item.rework_drag);
  return confidence + (Number.isFinite(rework) && rework > 0 ? " · rework " + rework.toFixed(1) + "%" : "");
}

function yieldWarnings(item) {
  const warnings = [];
  if (item?.confidence === "PARTIAL") warnings.push('<span class="yield-warning" title="Partial token or ledger coverage" aria-label="Partial measurement coverage">◐</span>');
  if (Number(item?.rework_drag) > 0) warnings.push('<span class="yield-warning" title="Receipt-backed rework drag" aria-label="Rework drag observed">↶</span>');
  if (item?.measurement_state === "MEASURED" && Number(item?.observed_tokens) > 0 && Number(item?.net_scope_points) === 0) warnings.push('<span class="yield-warning" title="Tokens observed without admitted scope" aria-label="Token burn without admitted scope">↑</span>');
  return warnings.join("");
}

const OVERVIEW_METRIC_FIELDS = [
  "active_projects", "active_lanes", "actionable_items", "oldest_wait",
  "admitted_milestones", "admitted_proof", "completed", "total", "percent", "trend",
  "window", "used_tokens", "remaining_tokens", "burn_rate_series", "coverage",
];
const OVERVIEW_METRIC_STATES = new Set(["KNOWN", "PARTIAL", "UNKNOWN"]);

function overviewMetricsProjectionValue(value, expectedScopeId = "") {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  if (!String(value.accepted_scope_id || "").trim() || value.accepted_cursor == null) return null;
  if (expectedScopeId && String(value.accepted_scope_id) !== String(expectedScopeId)) return null;
  if (!value.active_work || !value.needs_attention || !value.verified_progress || !value.usage || !value.field_state) return null;
  if (!OVERVIEW_METRIC_FIELDS.every((field) => OVERVIEW_METRIC_STATES.has(value.field_state[field]))) return null;
  const numericFields = {
    active_projects: value.active_work.active_projects, active_lanes: value.active_work.active_lanes,
    actionable_items: value.needs_attention.actionable_items,
    admitted_milestones: value.verified_progress.admitted_milestones, admitted_proof: value.verified_progress.admitted_proof,
    completed: value.verified_progress.completed, total: value.verified_progress.total, percent: value.verified_progress.percent,
    used_tokens: value.usage.used_tokens, remaining_tokens: value.usage.remaining_tokens,
  };
  if (Object.entries(numericFields).some(([field, number]) => value.field_state[field] !== "UNKNOWN" && (typeof number !== "number" || !Number.isFinite(number) || number < 0))) return null;
  if (["active_projects", "active_lanes", "actionable_items", "admitted_milestones", "admitted_proof", "completed", "total"].some((field) => value.field_state[field] !== "UNKNOWN" && !Number.isInteger(numericFields[field]))) return null;
  if (value.field_state.percent !== "UNKNOWN" && value.verified_progress.percent > 100) return null;
  if (value.field_state.trend !== "UNKNOWN" && !Array.isArray(value.verified_progress.trend)) return null;
  if (value.field_state.burn_rate_series !== "UNKNOWN" && !Array.isArray(value.usage.burn_rate_series)) return null;
  return value;
}

function overviewMetricsScopeId() {
  return state.ctrlId || (state.projectId !== "all" ? state.projectId : "all");
}

function overviewMetricCombinedState(record, fields) {
  if (!record) return "UNKNOWN";
  const states = fields.map((field) => record.field_state[field]);
  if (states.every((status) => status === "KNOWN")) return "KNOWN";
  if (states.every((status) => status === "UNKNOWN")) return "UNKNOWN";
  return "PARTIAL";
}

function overviewMetricNumber(record, field, value) {
  return record && record.field_state[field] !== "UNKNOWN" && typeof value === "number" && Number.isFinite(value) ? value : null;
}

function compactMetricNumber(value) {
  if (value == null) return "—";
  if (Math.abs(value) >= 1_000_000) return (value / 1_000_000).toFixed(value >= 10_000_000 ? 0 : 1).replace(/\.0$/, "") + "m";
  if (Math.abs(value) >= 1_000) return (value / 1_000).toFixed(value >= 100_000 ? 0 : 1).replace(/\.0$/, "") + "k";
  return String(value);
}

function overviewMetricSeries(record, field, value, keys) {
  if (!record || record.field_state[field] === "UNKNOWN" || !Array.isArray(value)) return [];
  return value.map((item) => {
    if (typeof item === "number" && Number.isFinite(item)) return item;
    if (!item || typeof item !== "object") return null;
    const key = keys.find((candidate) => typeof item[candidate] === "number" && Number.isFinite(item[candidate]));
    return key ? item[key] : null;
  }).filter((item) => item != null);
}

function overviewMetricWaitLabel(record) {
  if (!record || record.field_state.oldest_wait === "UNKNOWN") return "Oldest wait —";
  const wait = record.needs_attention.oldest_wait;
  if (wait == null) return "No accepted wait";
  if (typeof wait === "string") return "Oldest wait · " + wait;
  const reason = wait.reason || wait.label || wait.state || "Waiting";
  const release = wait.release_condition ? " · " + wait.release_condition : "";
  return "Oldest wait · " + reason + release;
}

function overviewMetricPresentation(record) {
  const activeProjects = overviewMetricNumber(record, "active_projects", record?.active_work?.active_projects);
  const activeLanes = overviewMetricNumber(record, "active_lanes", record?.active_work?.active_lanes);
  const actionable = overviewMetricNumber(record, "actionable_items", record?.needs_attention?.actionable_items);
  const milestones = overviewMetricNumber(record, "admitted_milestones", record?.verified_progress?.admitted_milestones);
  const proof = overviewMetricNumber(record, "admitted_proof", record?.verified_progress?.admitted_proof);
  const completed = overviewMetricNumber(record, "completed", record?.verified_progress?.completed);
  const total = overviewMetricNumber(record, "total", record?.verified_progress?.total);
  const percent = overviewMetricNumber(record, "percent", record?.verified_progress?.percent);
  const used = overviewMetricNumber(record, "used_tokens", record?.usage?.used_tokens);
  const remaining = overviewMetricNumber(record, "remaining_tokens", record?.usage?.remaining_tokens);
  const window = record?.field_state.window === "UNKNOWN" ? null : String(record?.usage?.window || "").trim();
  const coverage = record?.field_state.coverage === "UNKNOWN" ? null : String(record?.usage?.coverage || "").trim();
  return {
    binding: record ? "Scope " + record.accepted_scope_id + " · cursor " + (typeof record.accepted_cursor === "object" ? JSON.stringify(record.accepted_cursor) : record.accepted_cursor) : "Metrics unavailable · UNKNOWN",
    active: { state: overviewMetricCombinedState(record, ["active_projects", "active_lanes"]), value: activeProjects == null && activeLanes == null ? "—" : compactMetricNumber(activeProjects) + " / " + compactMetricNumber(activeLanes), note: compactMetricNumber(activeProjects) + " projects · " + compactMetricNumber(activeLanes) + " lanes" },
    attention: { state: overviewMetricCombinedState(record, ["actionable_items", "oldest_wait"]), value: compactMetricNumber(actionable), note: overviewMetricWaitLabel(record) },
    progress: { state: overviewMetricCombinedState(record, ["admitted_milestones", "admitted_proof", "completed", "total", "percent", "trend"]), value: percent != null ? compactMetricNumber(percent) + "%" : completed != null || total != null ? compactMetricNumber(completed) + " / " + compactMetricNumber(total) : "—", note: compactMetricNumber(milestones) + " milestones · " + compactMetricNumber(proof) + " proof", series: overviewMetricSeries(record, "trend", record?.verified_progress?.trend, ["value", "percent", "admitted_scope", "completed"]) },
    usage: { state: overviewMetricCombinedState(record, ["window", "used_tokens", "remaining_tokens", "burn_rate_series", "coverage"]), value: used == null ? "—" : compactMetricNumber(used) + " used", note: compactMetricNumber(remaining) + " remaining" + (window ? " · " + window : "") + (coverage ? " · " + coverage : ""), series: overviewMetricSeries(record, "burn_rate_series", record?.usage?.burn_rate_series, ["value", "tokens_per_minute", "burn_rate", "tokens"]) },
  };
}

function renderOverviewMetric(name, presentation) {
  const value = $("#metric-" + name + "-value");
  const status = $("#metric-" + name + "-state");
  value.textContent = presentation.value;
  value.setAttribute("aria-label", presentation.value === "—" ? "UNKNOWN" : presentation.value);
  status.textContent = presentation.state;
  status.className = "is-" + presentation.state.toLowerCase();
  $("#metric-" + name + "-note").textContent = presentation.note;
}

function renderOverviewMetrics() {
  const record = overviewMetricsProjectionValue(state.overview?.overview_metrics, overviewMetricsScopeId());
  const presentation = overviewMetricPresentation(record);
  $("#overview-metrics-binding").textContent = presentation.binding;
  renderOverviewMetric("active", presentation.active);
  renderOverviewMetric("attention", presentation.attention);
  renderOverviewMetric("progress", presentation.progress);
  renderOverviewMetric("usage", presentation.usage);
  drawLine($("#metric-progress-trend"), presentation.progress.series || [], "#4cda85");
  drawLine($("#metric-usage-trend"), presentation.usage.series || [], "#4da8ff");
  $("#metric-progress-trend").setAttribute("aria-label", presentation.progress.series?.length ? "Accepted verified progress trend" : "Verified progress trend unavailable");
  $("#metric-usage-trend").setAttribute("aria-label", presentation.usage.series?.length ? "Accepted usage burn rate" : "Usage burn rate unavailable");
}

function yieldChartMarkup(item) {
  const samples = item?.series || [];
  if (!samples.length) return '<div class="project-yield-empty"><strong>—</strong><span>Verified yield is unmeasured</span></div>';
  let cumulativeTokens = 0;
  let cumulativeScope = 0;
  const points = samples.map((sample) => {
    cumulativeTokens += Math.max(0, Number(sample.observed_tokens) || 0);
    cumulativeScope += Number(sample.net_scope_points) || 0;
    return { tokens: cumulativeTokens, scope: cumulativeScope, scopeVersion: sample.scope_version };
  });
  const maximumTokens = Math.max(1, ...points.map((point) => point.tokens));
  const scopes = points.map((point) => point.scope);
  const minimumScope = Math.min(0, ...scopes);
  const maximumScope = Math.max(1, ...scopes);
  const scopeRange = Math.max(1, maximumScope - minimumScope);
  const mapX = (tokens) => 34 + (tokens / maximumTokens) * 562;
  const mapY = (scope) => 154 - ((scope - minimumScope) / scopeRange) * 128;
  const line = points.map((point) => mapX(point.tokens).toFixed(1) + "," + mapY(point.scope).toFixed(1)).join(" ");
  const dividers = points.slice(1).filter((point, index) => point.scopeVersion !== points[index].scopeVersion).map((point) => '<line class="yield-scope-divider" x1="' + mapX(point.tokens).toFixed(1) + '" x2="' + mapX(point.tokens).toFixed(1) + '" y1="18" y2="158"><title>Scope version changed</title></line>').join("");
  const observedTokens = Number(item?.observed_tokens);
  return '<div class="project-yield-chart"><header><div><p class="eyebrow">Verified yield</p><h2>' + escapeHTML(yieldValue(item)) + '</h2></div><span>' + escapeHTML(yieldHealth(item)) + '</span></header><svg viewBox="0 0 620 186" role="img" aria-label="Observed tokens against cumulative admitted scope"><path class="yield-axis" d="M34 18v140h562"></path><text x="315" y="181">Observed tokens</text><text class="yield-y-label" x="8" y="91">Admitted scope</text>' + dividers + '<polyline class="yield-primary-line" points="' + line + '"></polyline></svg><footer><span>Token burn ' + (Number.isFinite(observedTokens) ? compactNumber(observedTokens) : '—') + '</span><span>Rework ' + (Number.isFinite(Number(item.rework_drag)) ? Number(item.rework_drag).toFixed(1) + '%' : '—') + '</span><span>' + escapeHTML(item.confidence === "HIGH" ? "High confidence" : item.confidence === "PARTIAL" ? "Partial confidence" : "Confidence unknown") + '</span></footer></div>';
}

const NOTIFICATION_PANEL_UNREAD_LIMIT = 8;
const NOTIFICATION_SAFE_VIEWS = Object.freeze({ projects: "overview", review: "review", assets: "assets", roles: "agents" });

function dedupeNotificationItems(items) {
  const seen = new Set();
  return (Array.isArray(items) ? items : []).filter((item) => {
    const identity = typeof item?.id === "string" ? item.id : "";
    if (!identity || seen.has(identity)) return false;
    seen.add(identity);
    return true;
  });
}

function notificationToastPlan(unread, presentedIds) {
  const priority = { critical: 3, warning: 2, info: 1 };
  const candidates = dedupeNotificationItems(unread).filter((item) => !presentedIds.has(item.id));
  const ordered = [...candidates].sort((left, right) =>
    (priority[String(right.severity)] || 0) - (priority[String(left.severity)] || 0)
      || Number(right.material_sequence || 0) - Number(left.material_sequence || 0)
      || String(right.id).localeCompare(String(left.id)));
  return { item: ordered[0] || null, additionalCount: Math.max(0, ordered.length - 1), presentedIds: candidates.map((item) => item.id) };
}

function notificationAcknowledgePayload(binding, notificationIds) {
  return { ctrl_id: binding.ctrlId, project_id: binding.projectId, notification_ids: [...notificationIds] };
}

function notificationDismissIds(toast, interacted) {
  return interacted && typeof toast?.item?.id === "string" ? [toast.item.id] : [];
}

function notificationPanelMessage(status, hasLastGood, connectionStatus, error = "") {
  if (connectionStatus !== "live") return hasLastGood ? "Offline · last received notifications are read-only." : "Notifications are unavailable while the console reconnects.";
  if (status === "loading") return "Loading notifications.";
  if (status === "refreshing") return "Refreshing notifications.";
  if (status === "acknowledging") return "Saving read status.";
  if (status === "stale") return "Last received notifications are read-only. " + (error || "Refresh failed.");
  if (status === "unavailable") return error || "Notifications could not be loaded.";
  if (status === "idle") return "Choose a project to see notifications.";
  return "Up to date.";
}

function notificationNextGeneration(generations, bindingKey) {
  const generation = Number(generations.get(bindingKey) || 0) + 1;
  generations.set(bindingKey, generation);
  return generation;
}

function notificationGenerationIsCurrent(generations, bindingKey, generation, currentBindingKey) {
  return bindingKey === currentBindingKey && generations.get(bindingKey) === generation;
}

function notificationFeedMatchesBinding(feed, binding) {
  return feed?.ok === true && feed.project_id === binding?.projectId && feed.ctrl_id === binding?.ctrlId
    && Array.isArray(feed.unread) && Array.isArray(feed.recent_seen);
}

async function notificationFeedResult(generations, bindingKey, generation, currentBindingKey, request) {
  const result = await request();
  return notificationGenerationIsCurrent(generations, bindingKey, generation, currentBindingKey()) ? result : null;
}

async function notificationActionAfterAcknowledgement(item, acknowledge, navigate) {
  if (!item?.id || !await acknowledge(item.id)) return false;
  navigate(item);
  return true;
}

function notificationActionEntry(data, notificationId) {
  const unread = dedupeNotificationItems(data?.unread).find((item) => item.id === notificationId);
  if (unread) return { item: unread, requiresAcknowledgement: true };
  const seen = dedupeNotificationItems(data?.recent_seen).find((item) => item.id === notificationId);
  return seen ? { item: seen, requiresAcknowledgement: false } : null;
}

async function notificationNavigateEntry(entry, acknowledge, navigate) {
  if (!entry) return false;
  if (entry.requiresAcknowledgement) return notificationActionAfterAcknowledgement(entry.item, acknowledge, navigate);
  navigate(entry.item);
  return true;
}

function notificationAcknowledgementFlight(currentFlight, bindingKey, notificationIds, start) {
  const identities = [...new Set(notificationIds)];
  if (currentFlight) {
    const activeIds = new Set(currentFlight.notificationIds);
    return currentFlight.bindingKey === bindingKey && identities.every((identity) => activeIds.has(identity))
      ? { flight: currentFlight, started: false }
      : { flight: null, started: false };
  }
  const flight = { bindingKey, notificationIds: identities, promise: start() };
  return { flight, started: true };
}

function notificationSafeTarget(item, binding) {
  const target = item?.action_target;
  const allowedFields = new Set(["view", "project_id", "ctrl_id", "task_id", "subject_id"]);
  if (!target || Object.keys(target).some((field) => !allowedFields.has(field))) return null;
  const view = NOTIFICATION_SAFE_VIEWS[String(target?.view || "")];
  const projectId = typeof target?.project_id === "string" ? target.project_id : "";
  const ctrlId = typeof target?.ctrl_id === "string" ? target.ctrl_id : "";
  if (
    !view || !projectId || !ctrlId || !binding
    || item.project_id !== projectId || item.ctrl_id !== ctrlId
    || binding.projectId !== projectId || binding.ctrlId !== ctrlId
  ) return null;
  return { view, projectId, ctrlId, roleLibrary: String(target.view) === "roles" };
}

function notificationBinding() {
  if (state.ctrlId) {
    const ctrl = historicalControllers().find((item) => item.id === state.ctrlId);
    const project = ctrl?.project_id ? currentWorkProjects().find((item) => item.id === ctrl.project_id) : null;
    if (project?.ctrl_ids?.includes(ctrl.id)) return { projectId: project.id, ctrlId: ctrl.id };
  }
  if (state.projectId === "all" || state.projectId.startsWith("ctrl:")) return null;
  const project = currentWorkProjects().find((item) => item.id === state.projectId);
  if (!project) return null;
  const ctrlIds = [...new Set(project.ctrl_ids || [])];
  const ctrlId = ctrlIds.includes(project.active_ctrl_id) ? project.active_ctrl_id : "";
  return ctrlId ? { projectId: project.id, ctrlId } : null;
}

function notificationBindingIdentity(binding = notificationBinding()) {
  return binding ? binding.projectId + "|" + binding.ctrlId : "";
}

function notificationData() {
  const key = notificationBindingIdentity();
  return key && key === state.notificationBindingKey && state.notifications?.ok === true ? state.notifications : null;
}

function notificationActionTarget(item) {
  const binding = notificationBinding();
  if (!binding || notificationBindingIdentity(binding) !== state.notificationBindingKey) return null;
  return notificationSafeTarget(item, binding);
}

function notificationIcon(item) {
  if (item.kind === "MILESTONE_COMPLETED") return "check";
  if (item.kind === "REVIEW_REQUESTED" || item.kind === "REVIEW_COMPLETED") return "shield-check";
  return "triangle-alert";
}

function notificationItemMarkup(item, seen = false) {
  const target = notificationActionTarget(item);
  const tag = target ? "button" : "article";
  const action = target ? ' type="button" data-notification-action="navigate"' : ' aria-disabled="true"';
  const severity = ["critical", "warning", "info"].includes(item.severity) ? item.severity : "info";
  const context = [item.project_id, item.task_id, item.owner_id].filter(Boolean).join(" · ") || "Project";
  const timestamp = seen ? item.seen_at_ms || item.observed_at_ms : item.observed_at_ms;
  return '<' + tag + ' class="notification-item is-' + severity + (seen ? ' is-seen' : '') + '"' + action + ' data-notification-id="' + escapeHTML(item.id) + '"><svg class="lucide" aria-hidden="true"><use href="#lucide-' + notificationIcon(item) + '"></use></svg><span><strong>' + escapeHTML(item.sentence || humanize(item.kind)) + '</strong><small>' + escapeHTML(context) + '</small></span><time>' + escapeHTML((seen ? "Seen " : "") + formatRelative(timestamp)) + '</time></' + tag + '>';
}

function renderedNotificationUnreadIds() {
  return $$("#notifications-unread-list [data-notification-id]").filter((item) => !item.hidden).map((item) => item.dataset.notificationId);
}

function renderNotificationToast() {
  const host = $("#notification-toast-region");
  const toast = state.notificationToast;
  if (!toast?.item) { host.innerHTML = ""; return; }
  const target = notificationActionTarget(toast.item);
  const mainTag = target ? "button" : "div";
  const mainAction = target ? ' type="button" data-notification-toast-action="open"' : "";
  const more = toast.additionalCount ? '<small>' + String(toast.additionalCount) + ' more notification' + (toast.additionalCount === 1 ? '' : 's') + '</small>' : "";
  const error = state.notificationStatus === "stale" && state.notificationError ? '<small>' + escapeHTML(state.notificationError) + '</small>' : "";
  host.innerHTML = '<aside class="notification-toast panel is-' + escapeHTML(toast.item.severity || "info") + '" data-notification-toast-id="' + escapeHTML(toast.item.id) + '" role="status"><' + mainTag + ' class="notification-toast-main"' + mainAction + '><svg class="lucide" aria-hidden="true"><use href="#lucide-' + notificationIcon(toast.item) + '"></use></svg><span><strong>' + escapeHTML(toast.item.sentence || humanize(toast.item.kind)) + '</strong>' + more + error + '</span></' + mainTag + '><button class="icon-button" type="button" data-notification-toast-action="dismiss" aria-label="Dismiss notification"><svg class="lucide" aria-hidden="true"><use href="#lucide-x"></use></svg></button></aside>';
}

function renderNotifications() {
  const data = notificationData();
  const unread = dedupeNotificationItems(data?.unread);
  const recentSeen = dedupeNotificationItems(data?.recent_seen);
  const badge = $("#notification-unread");
  badge.hidden = unread.length === 0;
  badge.textContent = unread.length > 9 ? "9+" : String(unread.length);
  $("#notifications").setAttribute("aria-label", unread.length ? "Notifications, " + String(unread.length) + " unread" : "Notifications");
  $("#notifications-panel").setAttribute("aria-busy", String(["loading", "refreshing", "acknowledging"].includes(state.notificationStatus)));
  $("#notifications-status").textContent = notificationPanelMessage(state.notificationStatus, Boolean(data), state.connectionStatus, state.notificationError);
  $("#notifications-retry").hidden = !notificationBinding() || !["stale", "unavailable"].includes(state.notificationStatus) || state.connectionStatus !== "live";
  $("#notifications-unread-list").innerHTML = unread.length
    ? unread.slice(0, NOTIFICATION_PANEL_UNREAD_LIMIT).map((item) => notificationItemMarkup(item)).join("")
    : '<p class="notifications-empty">' + (state.notificationStatus === "current" ? "All tentacles moving." : "No current notification list.") + '</p>';
  $("#notifications-recent-list").innerHTML = recentSeen.length
    ? recentSeen.map((item) => notificationItemMarkup(item, true)).join("")
    : '<p class="notifications-empty">No recent history.</p>';
  renderNotificationToast();
}

function clearNotificationToast() {
  if (state.notificationToastTimer) window.clearTimeout(state.notificationToastTimer);
  state.notificationToastTimer = null;
  state.notificationToast = null;
  renderNotificationToast();
}

async function dismissNotificationToast(interacted) {
  const toast = state.notificationToast;
  const ids = notificationDismissIds(toast, interacted);
  if (!ids.length) { clearNotificationToast(); return true; }
  const acknowledged = await acknowledgeNotifications(ids);
  if (acknowledged) clearNotificationToast();
  else renderNotificationToast();
  return acknowledged;
}

function presentNotificationToast(unread) {
  if (document.visibilityState !== "visible" || !$("#notifications-panel").hidden) return;
  const plan = notificationToastPlan(unread, state.notificationPresentedIds);
  if (!plan.item) return;
  plan.presentedIds.forEach((identity) => state.notificationPresentedIds.add(identity));
  if (state.notificationToastTimer) window.clearTimeout(state.notificationToastTimer);
  state.notificationToast = { item: plan.item, additionalCount: plan.additionalCount };
  renderNotificationToast();
  state.notificationToastTimer = window.setTimeout(() => dismissNotificationToast(false), 8_000);
}

async function performNotificationAcknowledgement(binding, bindingKey, exactIds) {
  notificationNextGeneration(state.notificationRequestGenerations, bindingKey);
  state.notificationStatus = "acknowledging";
  state.notificationError = "";
  renderNotifications();
  try {
    const result = await api("/api/notifications/seen", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(notificationAcknowledgePayload(binding, exactIds)) });
    if (!notificationFeedMatchesBinding(result?.feed, binding)) throw new Error("Notification acknowledgement returned an invalid feed");
    notificationNextGeneration(state.notificationRequestGenerations, bindingKey);
    if (notificationBindingIdentity() !== bindingKey || state.notificationBindingKey !== bindingKey) return false;
    state.notifications = result.feed;
    state.notificationStatus = "current";
    state.notificationError = "";
    return true;
  } catch (error) {
    notificationNextGeneration(state.notificationRequestGenerations, bindingKey);
    if (state.notificationBindingKey === bindingKey) {
      state.notificationStatus = "stale";
      state.notificationError = (error.message || "Read status could not be saved") + " Try again.";
    }
    return false;
  } finally {
    renderNotifications();
  }
}

async function acknowledgeNotifications(notificationIds) {
  const binding = notificationBinding();
  const bindingKey = notificationBindingIdentity(binding);
  const data = notificationData();
  const currentIds = new Set(dedupeNotificationItems(data?.unread).map((item) => item.id));
  const exactIds = [...new Set(notificationIds)].filter((identity) => currentIds.has(identity));
  if (!binding || !data || !exactIds.length || state.connectionStatus !== "live") return false;
  const selection = notificationAcknowledgementFlight(
    state.notificationAckFlight,
    bindingKey,
    exactIds,
    () => performNotificationAcknowledgement(binding, bindingKey, exactIds),
  );
  if (!selection.flight) return false;
  if (selection.started) state.notificationAckFlight = selection.flight;
  try {
    return await selection.flight.promise;
  } finally {
    if (selection.started && state.notificationAckFlight === selection.flight) state.notificationAckFlight = null;
  }
}

async function refreshNotifications() {
  const binding = notificationBinding();
  const bindingKey = notificationBindingIdentity(binding);
  if (state.notificationBindingKey !== bindingKey) dismissNotificationToast(false);
  if (!binding) {
    state.notifications = null;
    state.notificationBindingKey = "";
    state.notificationStatus = "idle";
    state.notificationError = "";
    renderNotifications();
    return;
  }
  const hasLastGood = state.notificationBindingKey === bindingKey && state.notifications?.ok === true;
  const generation = notificationNextGeneration(state.notificationRequestGenerations, bindingKey);
  if (!hasLastGood) state.notifications = null;
  state.notificationBindingKey = bindingKey;
  state.notificationStatus = hasLastGood ? "refreshing" : "loading";
  state.notificationError = "";
  renderNotifications();
  try {
    const params = new URLSearchParams({ ctrl_id: binding.ctrlId, project_id: binding.projectId });
    const result = await notificationFeedResult(
      state.notificationRequestGenerations,
      bindingKey,
      generation,
      notificationBindingIdentity,
      () => api("/api/notifications?" + params.toString()),
    );
    if (!result) return;
    if (!notificationFeedMatchesBinding(result, binding)) throw new Error("Notification feed returned an invalid response");
    state.notifications = result;
    state.notificationStatus = "current";
    state.notificationError = "";
    renderNotifications();
    presentNotificationToast(result.unread);
  } catch (error) {
    if (!notificationGenerationIsCurrent(state.notificationRequestGenerations, bindingKey, generation, notificationBindingIdentity())) return;
    state.notificationStatus = hasLastGood ? "stale" : "unavailable";
    state.notificationError = error.message || "Notifications could not be loaded.";
    renderNotifications();
  }
}

function setNotificationsOpen(open, returnFocus = false) {
  const panel = $("#notifications-panel");
  const trigger = $("#notifications");
  panel.hidden = !open;
  trigger.setAttribute("aria-expanded", String(open));
  if (open) {
    state.notificationTrigger = trigger;
    dismissNotificationToast(false);
    renderNotifications();
    requestAnimationFrame(() => {
      panel.focus({ preventScroll: true });
      if (state.notificationStatus === "current" && state.connectionStatus === "live") acknowledgeNotifications(renderedNotificationUnreadIds());
    });
  } else if (returnFocus) {
    state.notificationTrigger?.focus({ preventScroll: true });
  }
}

function navigateNotification(item) {
  const target = notificationActionTarget(item);
  if (!target) return false;
  state.projectId = target.projectId;
  state.ctrlId = target.ctrlId;
  state.projectTab = "overview";
  if (target.roleLibrary) state.agentsTab = "library";
  setNotificationsOpen(false);
  renderProjectNavigation();
  setView(target.view, false);
  renderAllViews();
  Promise.all([refreshProof(), refreshUsageHistory(), refreshProjectProgress(), refreshProjectProgressFeed(), refreshNotifications()]).then(renderAllViews);
  return true;
}

function selectedProjectProgress() {
  return state.projectProgressProjectId === selectedProgressProjectId() && state.projectProgress?.ok === true ? state.projectProgress : null;
}

function blockProgress(block) {
  const committed = Number(block?.committed_weight);
  const admitted = Number(block?.admitted_proof_weight);
  if (!Number.isFinite(committed) || committed <= 0 || !Number.isFinite(admitted)) return { percent: null, display: "Unmeasured" };
  const percent = Math.max(0, Math.min(100, admitted * 100 / committed));
  return { percent, display: new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(percent) + "%" };
}

function projectFeedMarkup(limit = 4) {
  const items = progressFeedItems().slice(0, limit);
  return '<ol class="project-progress-feed project-detail-feed">' + (items.length ? items.map((item) => {
    const [icon, label] = progressFeedFlag(item);
    return '<li><time>' + escapeHTML(formatRelative(item.observed_at_ms)) + '</time><strong>' + escapeHTML(item.owner_id || item.task_id || "Project") + '</strong><span>' + escapeHTML(item.material_update_sentence) + '</span>' + (icon ? '<i role="img" aria-label="' + escapeHTML(label) + '">' + escapeHTML(icon) + '</i>' : '') + '</li>';
  }).join("") : '<li class="empty-state">No material updates yet.</li>') + '</ol>';
}

function projectMilestones(blocks) {
  const groups = new Map();
  blocks.forEach((block) => {
    const id = block.milestone_id || "Unassigned milestone";
    const list = groups.get(id) || [];
    list.push(block);
    groups.set(id, list);
  });
  return [...groups.entries()];
}

function milestoneSummary(blocks) {
  if (!blocks.length || blocks.some((block) => !Number.isFinite(Number(block.committed_weight)))) return { percent: null, admitted: "—", committed: "—" };
  const committed = blocks.reduce((sum, block) => sum + Number(block.committed_weight), 0);
  const admitted = blocks.reduce((sum, block) => sum + Number(block.admitted_proof_weight || 0), 0);
  return { percent: committed > 0 ? Math.max(0, Math.min(100, admitted * 100 / committed)) : null, admitted, committed };
}

function projectEta(nodes) {
  const active = nodes.map((node) => node.eta?.current || node.eta || {}).filter((eta) => eta.status !== "complete" && Number(eta.eta_end_ms));
  if (!active.length) return "—";
  const starts = active.map((eta) => Number(eta.eta_start_ms)).filter(Number.isFinite);
  const ends = active.map((eta) => Number(eta.eta_end_ms)).filter(Number.isFinite);
  const start = starts.length ? Math.max(0, Math.min(...starts) - Date.now()) : Math.max(0, Math.min(...ends) - Date.now());
  const end = Math.max(0, Math.max(...ends) - Date.now());
  return formatDuration(start) + "–" + formatDuration(end);
}

function projectBlockRow(block) {
  const progress = blockProgress(block);
  const report = progressFeedItems().find((item) => item.task_id === block.task_id)?.material_update_sentence || "No material update yet.";
  const complete = progress.percent === 100 && ["VERIFIED", "ACCEPTED"].includes(block.lifecycle_state);
  return '<article class="project-block"><div class="project-block-state ' + (complete ? "is-complete" : "") + '">' + (complete ? '<svg class="lucide" aria-label="Proof admitted"><use href="#lucide-check"></use></svg>' : '<span aria-hidden="true"></span>') + '</div><div><header><strong>' + escapeHTML(block.block_id) + '</strong><span>' + escapeHTML(block.owner_id || "Unassigned") + '</span></header><p>' + escapeHTML(report) + '</p><div class="project-block-meter"><i style="width:' + (progress.percent == null ? 0 : progress.percent) + '%"></i></div><small>' + escapeHTML(progress.display + " · " + humanize(block.lifecycle_state || "Unknown") + " · ETA " + (block.eta?.end_ms ? formatDuration(Math.max(0, Number(block.eta.end_ms) - Date.now())) : "—")) + '</small></div></article>';
}

function projectTabMarkup(tab, progress, nodes) {
  const blocks = progress?.blocks || [];
  const milestones = projectMilestones(blocks);
  if (tab === "overview") {
    const efficiency = verifiedYieldItem("project", selectedProgressProjectId());
    return '<section class="project-overview-grid"><div class="milestone-rings">' + (milestones.length ? milestones.slice(0, 4).map(([id, items]) => { const summary = milestoneSummary(items); return '<article><div class="milestone-ring ' + (summary.percent === 100 ? "is-complete" : "") + '" style="--progress:' + (summary.percent ?? 0) + '%"><strong>' + escapeHTML(summary.percent == null ? "—" : Math.round(summary.percent) + "%") + '</strong></div><h3>' + escapeHTML(id) + '</h3><small>' + escapeHTML(summary.admitted + " / " + summary.committed + " admitted") + '</small></article>'; }).join("") : '<p class="empty-state">No measured milestones yet.</p>') + '</div>' + yieldChartMarkup(efficiency) + '<section class="panel project-updates"><header class="overview-section-head"><div><p class="eyebrow">Material events</p><h2>Latest updates</h2></div><p>Newest first</p></header>' + projectFeedMarkup(4) + '</section></section>';
  }
  if (tab === "roadmap") return '<section class="project-roadmap">' + (milestones.length ? milestones.map(([id, items], index) => '<article><span>' + String(index + 1) + '</span><div><h3>' + escapeHTML(id) + '</h3><p>' + escapeHTML(items.length + " block" + (items.length === 1 ? "" : "s") + " · " + milestoneSummary(items).admitted + " admitted") + '</p></div></article>').join("") : '<p class="empty-state">No roadmap receipts yet.</p>') + '</section>';
  if (tab === "lanes") { const owners = new Map(); blocks.forEach((block) => { const id = block.owner_id || "Unassigned"; owners.set(id, [...(owners.get(id) || []), block]); }); return '<section class="project-lanes">' + ([...owners.entries()].map(([owner, items]) => '<section class="panel"><header><h3>' + escapeHTML(owner) + '</h3><span>' + items.length + '</span></header>' + items.map(projectBlockRow).join("") + '</section>').join("") || '<p class="empty-state">No owner lanes yet.</p>') + '</section>'; }
  if (tab === "hierarchy") return '<section class="project-hierarchy">' + (nodes.length ? nodes.filter((node) => !isSubagent(node)).map((node) => '<article><svg class="lucide" aria-hidden="true"><use href="#lucide-git-branch"></use></svg><div><strong>' + escapeHTML(node.worker || node.owner || node.role_label || "Unassigned") + '</strong><span>' + escapeHTML(node.artifact || node.title || node.id) + '</span></div><small>' + escapeHTML(observedAgentRole(node) || "TASK") + '</small></article>').join("") : '<p class="empty-state">No hierarchy is observed for this project.</p>') + '</section>';
  if (tab === "proof") { const images = evidenceImagesFor(nodes); state.evidenceImages = images; return '<section class="project-proof-grid">' + (images.length ? images.map((item, index) => '<button class="asset-tile" type="button" data-evidence-open="' + index + '" aria-label="Open proof image"><img loading="lazy" src="' + proofMediaURL(item) + '" alt=""><span>' + escapeHTML(item.caption || item.kind || "Proof") + '</span></button>').join("") : '<p class="empty-state">No image proof is available for this project.</p>') + '</section>'; }
  if (tab === "ledger") return '<section class="panel project-ledger"><header class="overview-section-head"><div><p class="eyebrow">Canonical events</p><h2>Ledger</h2></div><p>' + escapeHTML(progress?.cursor?.event_seq == null ? "No cursor" : "Through " + progress.cursor.event_seq) + '</p></header>' + projectFeedMarkup(10) + '</section>';
  return '<section class="panel run-log" data-run-log-surface="project" aria-label="Project run log"></section>';
}

function renderProjectDetail() {
  const projectId = selectedProgressProjectId();
  const active = Boolean(projectId);
  $("#projects-portfolio").hidden = active;
  $("#project-detail").hidden = !active;
  const group = projectGroups().find((item) => item.id === projectId);
  if (state.view === "overview") {
    $("#view-title").textContent = active ? (group?.label || "Project") : "Overview";
    $("#view-subtitle").textContent = active ? "Project progress, proof, ownership, and ledger." : "Portfolio progress and project scope.";
  }
  if (!active) return;
  const progress = selectedProjectProgress();
  const nodes = scopedNodes();
  $("#project-detail-title").textContent = group?.label || "Project";
  $("#project-detail-status").textContent = state.projectProgressStatus === "stale" ? "Last received project ledger" : state.projectProgressStatus === "unavailable" ? "Project ledger unavailable" : progress ? "Scope version " + (progress.scope_version ?? "—") : "Loading project ledger";
  const measured = progress?.status === "MEASURED" && Number.isFinite(Number(progress.percent));
  const nextGate = (progress?.blocks || []).find((block) => ["REVIEW", "WAITING_DEPENDENCY", "WAITING_EXTERNAL", "USER_PAUSED"].includes(block.lifecycle_state));
  $("#project-detail-summary").innerHTML = '<p><span>Progress</span><strong>' + escapeHTML(measured ? progress.percent + "%" : "—") + '</strong></p><p><span>Live ETA</span><strong><svg class="lucide" aria-hidden="true"><use href="#lucide-clock"></use></svg>' + escapeHTML(projectEta(nodes)) + '</strong></p><p><span>Next gate</span><strong>' + escapeHTML(nextGate ? humanize(nextGate.lifecycle_state) : "—") + '</strong></p>';
  const selectedTabId = "project-tab-" + state.projectTab;
  $$('[data-project-tab]').forEach((button) => { const selected = button.dataset.projectTab === state.projectTab; button.classList.toggle("is-active", selected); button.setAttribute("aria-selected", String(selected)); button.tabIndex = selected ? 0 : -1; });
  const tabPanel = $("#project-tab-panel");
  tabPanel.setAttribute("aria-labelledby", selectedTabId);
  const retainedRunLogMount = state.projectTab === "logs" && $('[data-run-log-surface="project"]', tabPanel);
  if (!retainedRunLogMount) tabPanel.innerHTML = projectTabMarkup(state.projectTab, progress, nodes);
}

function proofReviewState(item) {
  return humanize(item.review_status || item.disposition || item.status || "Status unavailable");
}

function renderReview() {
  const items = scopedProofItems();
  $("#review-status").textContent = currentProofStatus() === "stale" ? "Showing the last received proof" : items.length ? items.length + " proof item" + (items.length === 1 ? "" : "s") : "No proof in this scope";
  $("#review-list").innerHTML = items.length ? items.map((item) => { const image = String(item.media_type || "").startsWith("image/"); return '<article class="review-row"><div class="review-kind"><svg class="lucide" aria-hidden="true"><use href="#lucide-shield-check"></use></svg></div><div><strong>' + escapeHTML(item.caption || item.kind || item.evidence_id) + '</strong><p>' + escapeHTML([item.project_id, item.task_id, item.owner_id].filter(Boolean).join(" · ") || "Unscoped proof") + '</p><small>' + escapeHTML(proofReviewState(item) + " · " + formatRelative(item.observed_at_ms || item.updated_at)) + '</small></div><div class="review-actions"><button class="icon-button" type="button" data-review-open="' + escapeHTML(proofIdentity(item)) + '" aria-label="Open proof"' + (image ? '' : ' disabled title="No visual preview is available"') + '><svg class="lucide" aria-hidden="true"><use href="#lucide-image"></use></svg></button><button class="icon-button" type="button" aria-label="Send feedback unavailable" disabled title="Review feedback command is not available"><svg class="lucide" aria-hidden="true"><use href="#lucide-message-square"></use></svg></button><button class="icon-button" type="button" aria-label="Admit proof unavailable" disabled title="Proof admission command is not available"><svg class="lucide" aria-hidden="true"><use href="#lucide-check"></use></svg></button><details><summary aria-label="More proof details"><svg class="lucide" aria-hidden="true"><use href="#lucide-ellipsis"></use></svg></summary><p>Digest ' + escapeHTML(String(item.digest || "—").slice(0, 16)) + ' · ' + escapeHTML(item.claim_limit || "Acceptance is recorded separately.") + '</p></details></div></article>'; }).join("") : '<p class="empty-state review-empty">No proof is available in this scope.</p>';
}

function assetItems() {
  return scopedProofItems().filter((item) => String(item.media_type || "").startsWith("image/"));
}

function openProofIdentity(identity, trigger) {
  const images = assetItems();
  const index = images.findIndex((item) => proofIdentity(item) === identity);
  if (index < 0) return;
  state.evidenceImages = images;
  openEvidenceLightbox(index, trigger);
}

function assetImageMarkup(item, detail = false) {
  return '<span class="asset-image-frame' + (detail ? ' is-detail' : '') + '"><img data-asset-image loading="lazy" src="' + proofMediaURL(item) + '" alt=""><span class="asset-image-failed"' + (detail ? ' role="status"' : '') + ' hidden>Preview unavailable</span></span>';
}

function assetGridMarkup(item) {
  const identity = proofIdentity(item);
  const label = item.caption || item.kind || "Asset";
  const selected = identity === state.selectedAssetIdentity;
  return '<article class="asset-tile' + (selected ? ' is-selected' : '') + '" data-asset-card="' + escapeHTML(identity) + '"><button class="asset-image-button" type="button" data-asset-detail="' + escapeHTML(identity) + '" aria-label="Open asset details for ' + escapeHTML(label) + '" aria-current="' + String(selected) + '">' + assetImageMarkup(item) + '</button><div class="asset-quick-actions" aria-label="Quick actions for ' + escapeHTML(label) + '"><button class="icon-button" type="button" data-review-open="' + escapeHTML(identity) + '" aria-label="Open proof for ' + escapeHTML(label) + '" title="Open proof"><svg class="lucide" aria-hidden="true"><use href="#lucide-image"></use></svg></button><button class="icon-button" type="button" disabled aria-label="New revision unavailable for ' + escapeHTML(label) + '" title="Asset revision command is not available"><svg class="lucide" aria-hidden="true"><use href="#lucide-pencil"></use></svg></button><button class="icon-button" type="button" disabled aria-label="Approve digest unavailable for ' + escapeHTML(label) + '" title="Asset approval command is not available"><svg class="lucide" aria-hidden="true"><use href="#lucide-check"></use></svg></button></div></article>';
}

function assetListMarkup(item) {
  const identity = proofIdentity(item);
  const label = item.caption || item.kind || "Asset";
  const selected = identity === state.selectedAssetIdentity;
  return '<article class="asset-list-row' + (selected ? ' is-selected' : '') + '"><button class="asset-list-main" type="button" data-asset-detail="' + escapeHTML(identity) + '" aria-label="Open asset details for ' + escapeHTML(label) + '" aria-current="' + String(selected) + '">' + assetImageMarkup(item) + '<span class="asset-list-copy"><strong>' + escapeHTML(label) + '</strong><small>' + escapeHTML([item.project_id || "Unscoped", proofReviewState(item)].join(" · ")) + '</small><code>' + escapeHTML(String(item.digest || "—").slice(0, 16)) + '</code></span></button><div class="asset-list-actions"><button class="quiet-button" type="button" data-review-open="' + escapeHTML(identity) + '">Open proof</button><button class="quiet-button" type="button" disabled title="Asset revision command is not available">New revision</button><button class="quiet-button" type="button" disabled title="Asset approval command is not available">Approve digest</button></div></article>';
}

function renderAssets() {
  const items = assetItems();
  if (!items.some((item) => proofIdentity(item) === state.selectedAssetIdentity)) state.selectedAssetIdentity = proofIdentity(items[0]);
  const selected = items.find((item) => proofIdentity(item) === state.selectedAssetIdentity) || null;
  $("#assets-status").textContent = currentProofStatus() === "stale" ? "Showing the last received asset inventory" : items.length ? items.length + " digest-bound asset" + (items.length === 1 ? "" : "s") : "No retained assets";
  $$('[data-asset-view]').forEach((button) => { const selectedView = button.dataset.assetView === state.assetView; button.classList.toggle("is-selected", selectedView); button.setAttribute("aria-pressed", String(selectedView)); });
  const gallery = $("#asset-gallery");
  gallery.classList.toggle("is-list", state.assetView === "list");
  gallery.setAttribute("aria-label", state.assetView === "grid" ? "Asset image grid" : "Asset list");
  gallery.innerHTML = items.length ? items.map(state.assetView === "grid" ? assetGridMarkup : assetListMarkup).join("") : '<p class="empty-state">Assets appear after digest-bound proof is retained.</p>';
  if (!selected) { $("#asset-detail").innerHTML = '<p class="empty-state">Select an asset to inspect its immutable revision.</p>'; return; }
  const revisions = items.filter((item) => item.evidence_id === selected.evidence_id);
  const provenance = selected.source || selected.provenance?.source || selected.provenance?.kind || "Unknown";
  const revisionMarkup = revisions.map((revision) => '<li><code>' + escapeHTML(String(revision.digest || "—").slice(0, 12)) + '</code><span>' + escapeHTML(proofReviewState(revision)) + '</span><time>' + escapeHTML(formatRelative(revision.observed_at_ms || revision.updated_at)) + '</time></li>').join("");
  $("#asset-detail").innerHTML = assetImageMarkup(selected, true) + '<p class="eyebrow">' + escapeHTML(proofReviewState(selected)) + '</p><h2>' + escapeHTML(selected.caption || selected.kind || "Asset") + '</h2><dl><div><dt>Digest</dt><dd>' + escapeHTML(selected.digest || "—") + '</dd></div><div><dt>Revision history</dt><dd>' + revisions.length + '</dd></div><div><dt>Provenance</dt><dd>' + escapeHTML(provenance) + '</dd></div></dl><ol class="asset-revisions" aria-label="Retained asset revisions">' + revisionMarkup + '</ol><div class="asset-actions"><button class="quiet-button" type="button" data-review-open="' + escapeHTML(proofIdentity(selected)) + '">Open proof</button><button class="quiet-button" type="button" disabled title="Asset revision command is not available">New revision</button><button class="quiet-button" type="button" disabled title="Asset approval command is not available">Approve digest</button></div><small>Revision and approval actions remain unavailable until their server commands are accepted.</small>';
}

function selectedProgressProjectId() {
  if (state.ctrlId) return "";
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
  const hasCurrentFeed = state.projectProgressFeed?.ok === true
    && state.projectProgressFeed?.project_id === projectId
    && Array.isArray(state.projectProgressFeed?.items);
  if (!projectId || state.projectProgressFeedProjectId !== projectId || !hasCurrentFeed || state.projectProgressFeed.enabled === false) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  const items = progressFeedItems();
  const status = $("#project-progress-status");
  status.textContent = state.projectProgressFeedStatus === "stale" ? "Last received · reconnect to refresh" : state.projectProgressFeedStatus === "unavailable" ? "Updates unavailable" : items.length ? String(items.length) + " latest update" + (items.length === 1 ? "" : "s") : "No material updates yet";
  $("#project-progress-feed").innerHTML = items.length ? items.map((item) => {
    const [icon, label] = progressFeedFlag(item);
    const owner = item.owner_id || item.task_id || item.block_id || "Project";
    return '<li data-progress-event-id="' + escapeHTML(item.event_id || progressEventIdentity(item)) + '"><time datetime="' + escapeHTML(new Date(Number(item.observed_at_ms) || 0).toISOString()) + '">' + escapeHTML(formatRelative(item.observed_at_ms)) + '</time><strong>' + escapeHTML(owner) + '</strong><span>' + escapeHTML(item.material_update_sentence) + '</span>' + (icon ? '<i role="img" aria-label="' + escapeHTML(label) + '" title="' + escapeHTML(label) + '">' + escapeHTML(icon) + '</i>' : '') + '</li>';
  }).join("") : '<li class="empty-state">No material project updates yet.</li>';
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
    const efficiency = verifiedYieldItem(current?.id ? "task" : "project", current?.id || card.projectId) || verifiedYieldItem("project", card.projectId);
    const stateLabel = primary ? statusLabel(primary)[0] : "No task state";
    const ringClass = needsAttention(primary) ? "is-attention" : (statusLabel(primary || {})[1] || "is-pending");
    const subagents = card.ctrlId ? subagentDescendants(card.ctrlId, tree) : [];
    const subagentDisclosure = subagents.length ? '<details class="overview-subagents" data-overview-subagents="' + escapeHTML(card.ctrlId) + '"><summary>Subagents <span>' + subagents.length + '</span></summary><ul>' + subagents.map((node) => '<li><strong>' + escapeHTML(node.artifact || node.title || node.id) + '</strong><span>' + escapeHTML(statusLabel(node)[0]) + '</span></li>').join('') + '</ul></details>' : '<span class="overview-subagent-empty">No subagents</span>';
    const progressDisplay = progress.display === "Unmeasured" ? "—" : progress.display;
    const progressFreshness = progress.freshness === "Unmeasured" ? "UNKNOWN" : progress.freshness;
    const efficiencyHealth = yieldHealth(efficiency) === "Unmeasured" ? "UNKNOWN" : yieldHealth(efficiency);
    return '<article class="overview-project-card panel"><div class="overview-progress-ring ' + ringClass + '" style="--progress:' + (progress.percent == null ? 0 : progress.percent) + '%" aria-label="' + escapeHTML(progressDisplay + ' receipt-backed progress · ' + progressFreshness) + '"><strong>' + escapeHTML(progressDisplay) + '</strong><span>' + escapeHTML(progressFreshness) + '</span></div><div class="overview-project-main"><p class="eyebrow">' + escapeHTML(stateLabel) + '</p><h3>' + escapeHTML(card.label) + '</h3><p>' + escapeHTML(current?.artifact || "No current task observed") + '</p></div><dl class="overview-project-facts"><div><dt>Current work</dt><dd>' + escapeHTML(current?.artifact || "None observed") + '</dd></div><div><dt>Latest receipt</dt><dd>' + escapeHTML(receipt?.caption || receipt?.kind || "None received") + '</dd></div><div><dt>Blocker</dt><dd class="' + (blocker ? 'risk-text' : '') + '">' + escapeHTML(blocker?.artifact || "None observed") + '</dd></div></dl><div class="overview-yield"><span>Verified yield ' + yieldWarnings(efficiency) + '</span><strong>' + escapeHTML(yieldValue(efficiency)) + '</strong>' + miniSparkline(yieldSeries(efficiency), "Verified yield trend for " + card.label) + '<small>' + escapeHTML(efficiencyHealth) + '</small></div><div class="overview-project-subagents">' + subagentDisclosure + '</div></article>';
  };
  $("#overview-summary").textContent = allProjects
    ? (scopedCards.length ? String(scopedCards.length) + " project scope" + (scopedCards.length === 1 ? "" : "s") : "No classified Current Work")
    : (scopedCards.length ? "Current scope" : "No classified Current Work");
  const empty = !scopeAvailable
    ? '<p class="empty-state overview-empty">Current Work needs host-reported CTRL classification. Task history remains available in project views.</p>'
    : allProjects
      ? '<p class="empty-state overview-empty">No classified Current Work is available.</p>'
      : '<p class="empty-state overview-empty">No classified Current Work is available in ' + escapeHTML(scopeLabel()) + '.</p>';
  $("#overview-project-cards").innerHTML = visibleCards.length
    ? visibleCards.map(renderCard).join("") + (moreCards.length ? '<details class="overview-more"><summary>' + String(moreCards.length) + ' more project scope' + (moreCards.length === 1 ? '' : 's') + '</summary><div>' + moreCards.map(renderCard).join("") + '</div></details>' : '')
    : empty;
}

function renderOverview() {
  const nodes = scopedNodes();
  renderOverviewMetrics();
  renderOverviewProjectCards(nodes);
  renderEvidenceGallery(nodes, "#overview-evidence-gallery", "#overview-evidence-note", 4);
  renderUsage();
  renderProjectProgressFeed();
  renderProjectDetail();
  renderNotifications();
  if (state.connectionStatus === "live") $("#sync-time").textContent = state.overview?.generated_at ? "Live · " + formatRelative(state.overview.generated_at) : "Live";
}

function observedAgentRole(node) {
  const role = String(node?.role || node?.worker_role || "").trim().toUpperCase();
  return ["CTRL", "LEAD", "DOER"].includes(role) ? role : "";
}

function runLogAgentId(node) {
  return String(node?.owner_id || node?.id || "");
}

function agentRow(node, role, binding = null) {
  const status = statusLabel(node || {});
  const title = node?.artifact || node?.title || "Unknown task";
  const owner = node?.worker || node?.owner || node?.id || "Unknown";
  const updated = node?.updated_at || node?.generated_at;
  const efficiency = verifiedYieldItem("owner", node?.owner_id || node?.worker || node?.owner || node?.id || "");
  const selected = binding && currentRunLogAgent()?.projectId === binding.projectId && currentRunLogAgent()?.ctrlId === binding.ctrlId && currentRunLogAgent()?.agentId === binding.agentId;
  const identity = binding
    ? '<button class="agent-identity" type="button" data-run-log-agent="' + escapeHTML(binding.agentId) + '" data-project-id="' + escapeHTML(binding.projectId) + '" data-ctrl-id="' + escapeHTML(binding.ctrlId) + '" data-agent-label="' + escapeHTML(owner) + '" aria-pressed="' + String(Boolean(selected)) + '" aria-label="Show run log for ' + escapeHTML(owner) + '"><strong>' + escapeHTML(owner) + '</strong><small>' + escapeHTML(title) + '</small></button>'
    : '<div><strong>' + escapeHTML(owner) + '</strong><small>' + escapeHTML(title) + '</small></div>';
  return '<div class="agent-row' + (selected ? ' is-selected' : '') + '" data-agent-role="' + escapeHTML(role) + '"><span class="agent-role-mark" aria-hidden="true">' + escapeHTML(role.slice(0, 1)) + '</span>' + identity + '<div class="agent-yield"><strong>' + escapeHTML(yieldValue(efficiency)) + '</strong>' + miniSparkline(yieldSeries(efficiency), "Verified yield trend for " + owner) + '<small>Verified yield</small></div><span class="state-pill ' + status[1] + '">' + escapeHTML(status[0] || "Unknown") + '</span><time datetime="' + escapeHTML(updated || "") + '">' + escapeHTML(formatRelative(updated)) + '</time></div>';
}

function agentBranch(node, role, binding = null, children = []) {
  const label = node?.artifact || node?.title || node?.id || "Unknown task";
  const body = agentRow(node, role, binding) + children.join("");
  return '<details class="agent-branch agent-level-' + role.toLowerCase() + '" open><summary><svg class="lucide" aria-hidden="true"><use href="#lucide-chevron-right"></use></svg><span>' + escapeHTML(label) + '</span><small>' + escapeHTML(role) + '</small></summary><div class="agent-branch-body">' + body + '</div></details>';
}

function activeSwarmProjects() {
  const projects = historicalProjects().filter((project) => project.visibility !== "archived" && project.archived !== true);
  const selected = state.projectId === "all" ? projects : projects.filter((project) => project.id === state.projectId);
  const nodes = state.overview?.nodes || [];
  return selected.map((project) => ({ project, nodes: nodes.filter((node) => node.project_id === project.id && observedAgentRole(node)) })).filter((entry) => entry.nodes.length);
}

function renderAgentHierarchy() {
  const projects = activeSwarmProjects();
  const observed = projects.flatMap((entry) => entry.nodes);
  const roleCounts = ["CTRL", "LEAD", "DOER"].map((role) => [role, observed.filter((node) => observedAgentRole(node) === role).length]);
  $("#agents-summary").innerHTML = roleCounts.map(([role, count]) => '<p><strong>' + escapeHTML(count) + '</strong><span>' + escapeHTML(role) + '</span></p>').join("") + '<p><strong>' + escapeHTML(projects.length) + '</strong><span>Projects</span></p>';
  $("#agent-hierarchy").innerHTML = projects.length ? projects.map(({ project, nodes }) => {
    const ctrlIds = new Set((state.overview?.navigation?.controllers || []).filter((ctrl) => ctrl.project_id === project.id && ctrl.archived !== true && ctrl.visibility !== "archived").map((ctrl) => ctrl.id));
    const ctrls = nodes.filter((node) => observedAgentRole(node) === "CTRL" && (!ctrlIds.size || ctrlIds.has(node.id)));
    const orphanLeads = nodes.filter((node) => observedAgentRole(node) === "LEAD" && !(node.controller_ids || []).some((id) => ctrls.some((ctrl) => ctrl.id === id)));
    const orphanDoers = nodes.filter((node) => observedAgentRole(node) === "DOER" && !(node.controller_ids || []).some((id) => ctrls.some((ctrl) => ctrl.id === id)));
    const ctrlBranches = ctrls.map((ctrl) => {
      const ctrlNodes = nodes.filter((node) => node.id !== ctrl.id && (node.controller_ids || []).includes(ctrl.id));
      const leads = ctrlNodes.filter((node) => observedAgentRole(node) === "LEAD");
      const leadIds = new Set(leads.map((lead) => lead.id));
      const exactCtrlBinding = runLogBindingForCtrl(ctrl.id);
      const bindingFor = (node) => exactCtrlBinding ? { projectId: exactCtrlBinding.projectId, ctrlId: exactCtrlBinding.ctrlId, agentId: runLogAgentId(node) } : null;
      const leadBranches = leads.map((lead) => agentBranch(lead, "LEAD", bindingFor(lead), ctrlNodes.filter((node) => observedAgentRole(node) === "DOER" && node.parent_id === lead.id).map((node) => agentRow(node, "DOER", bindingFor(node)))));
      const directDoers = ctrlNodes.filter((node) => observedAgentRole(node) === "DOER" && !leadIds.has(node.parent_id));
      return agentBranch(ctrl, "CTRL", bindingFor(ctrl), leadBranches.concat(directDoers.map((node) => agentRow(node, "DOER", bindingFor(node)))));
    });
    const unresolved = orphanLeads.map((node) => agentBranch(node, "LEAD")).concat(orphanDoers.map((node) => agentRow(node, "DOER")));
    return '<details class="agent-project" open><summary><svg class="lucide" aria-hidden="true"><use href="#lucide-chevron-right"></use></svg><span>' + escapeHTML(publicLabel(project.goal_label || project.name, "Untitled project")) + '</span><small>' + escapeHTML(nodes.length) + ' observed</small></summary><div class="agent-project-body">' + (ctrlBranches.length || unresolved.length ? ctrlBranches.concat(unresolved).join("") : '<p class="empty-state">No CTRL, LEAD, or DOER authority was observed.</p>') + '</div></details>';
  }).join("") : '<p class="empty-state agents-empty">No CTRL, LEAD, or DOER authority is available in this project scope.</p>';
}

function roleManifestProjectionValue(value) {
  if (!value || value.ok !== true || value.schema_version !== 1 || value.built_in_count !== 24 || !Array.isArray(value.roles) || !Array.isArray(value.assignments)) return null;
  const ids = value.roles.map((role) => String(role?.id || ""));
  const builtIns = value.roles.filter((role) => role?.built_in === true);
  if (ids.some((id) => !id) || new Set(ids).size !== ids.length || builtIns.length !== 24 || !builtIns.some((role) => role.id === "assistant") || builtIns.some((role) => role.id === "critic")) return null;
  const validSpecializations = value.roles.every((role) => Array.isArray(role.specializations) && role.specializations.length <= 4 && (!role.built_in || role.specializations.length === 4));
  return validSpecializations ? value : null;
}

function roleManifestProjection() {
  return roleManifestProjectionValue(state.roleManifests);
}

function roleCurrentRecords(projection = roleManifestProjection()) {
  return (projection?.roles || []).filter((role) => role.id !== "critic");
}

function roleRecord(roleId) {
  return roleCurrentRecords().find((role) => role.id === roleId) || null;
}

function roleCommandContract() {
  const contract = roleManifestProjection()?.command_contract;
  const commands = ["ROLE_MANIFEST_CREATE", "ROLE_MANIFEST_REVISE", "ROLE_MANIFEST_RESET"];
  return contract?.endpoint === "/api/role-manifests/commands"
    && contract.optimistic_concurrency_field === "expected_active_version"
    && commands.every((command) => contract.commands?.includes(command))
    && contract.avatar?.selection_field === "avatar_asset_digest"
    && contract.avatar?.requires_retained_immutable_asset === true
    && contract.avatar?.generation_command == null ? contract : null;
}

function roleCanMutate(command) {
  return state.roleManifestStatus === "current" && roleCommandContract()?.commands.includes(command) === true && !state.roleManifestSaving;
}

function roleDisplayName(role) {
  return ["dev", "developer"].includes(String(role?.id || "").toLowerCase()) ? "Developer" : (role?.name || role?.id || "Unknown role");
}

function roleAvatar(role) {
  const accent = /^#[0-9a-f]{6}$/i.test(role?.accent || "") ? role.accent : "#8f9db0";
  const retained = assetItems().find((item) => String(item.digest || "").toLowerCase() === String(role?.avatar_asset_digest || "").toLowerCase());
  const visual = retained ? '<img loading="lazy" decoding="async" src="' + proofMediaURL(retained) + '" alt="">' : '<svg class="lucide"><use href="#lucide-circle-user-round"></use></svg><b>' + escapeHTML(roleDisplayName(role).slice(0, 1) || "?") + '</b>';
  return '<span class="role-avatar" style="--role-accent:' + escapeHTML(accent) + '" aria-hidden="true">' + visual + '</span>';
}

function roleHasRetainedAvatar(role) {
  const digest = String(role?.avatar_asset_digest || "").toLowerCase();
  return /^[0-9a-f]{64}$/.test(digest) && assetItems().some((item) => String(item.digest || "").toLowerCase() === digest);
}

function roleSourceLabel(role) {
  return role?.source === "builtin" ? "Built in" : role?.source === "user_override" ? "Custom version" : role?.source === "custom" ? "Custom role" : "Unknown";
}

function roleSpecializations(role) {
  if (!Array.isArray(role?.specializations)) return [];
  return role.specializations.map((item) => String(typeof item === "string" ? item : item?.name || item?.label || item?.id || "").trim()).filter(Boolean).slice(0, 4);
}

function roleSpecializationsMarkup(role) {
  const items = roleSpecializations(role);
  return items.length ? '<ul class="role-specializations">' + items.map((item) => '<li>' + escapeHTML(item) + '</li>').join("") + '</ul>' : '<p class="role-specializations-empty">No specializations.</p>';
}

function roleSearchBuckets(role) {
  const texts = (value) => Array.isArray(value) ? value.map((item) => String(item || "").trim()).filter(Boolean) : [];
  return [
    { field: "profession", label: "profession", values: [role?.name, role?.id].map((item) => String(item || "").trim()).filter(Boolean) },
    { field: "specialization", label: "specialization", values: roleSpecializations(role) },
    { field: "alias", label: "alias or tag", values: [...texts(role?.aliases), ...texts(role?.tags)] },
    { field: "skills", label: "skill", values: texts(role?.default_skills) },
    { field: "purpose", label: "purpose", values: [role?.purpose].map((item) => String(item || "").trim()).filter(Boolean) },
  ];
}

function roleSearchMatch(role, query, fields) {
  const needle = String(query || "").trim().toLocaleLowerCase();
  if (!needle) return { matched: true, label: "" };
  for (const bucket of roleSearchBuckets(role)) {
    if (!fields.has(bucket.field)) continue;
    const value = bucket.values.find((item) => item.toLocaleLowerCase().includes(needle));
    if (value) return { matched: true, label: "Matched: " + value + " · " + bucket.label };
  }
  return { matched: false, label: "" };
}

function roleFilterRecords(roles, query, types, fields) {
  return roles.map((role) => ({ role, match: roleSearchMatch(role, query, fields) }))
    .filter(({ role, match }) => types.has(role.built_in ? "builtin" : "custom") && match.matched);
}

function roleFilterChipsMarkup(types) {
  const chips = [];
  if (types.size === 1 && types.has("builtin")) chips.push('<button type="button" data-role-filter-clear="type">Built-in <span aria-hidden="true">×</span><span class="sr-only">Remove Built-in filter</span></button>');
  if (types.size === 1 && types.has("custom")) chips.push('<button type="button" data-role-filter-clear="type">Custom <span aria-hidden="true">×</span><span class="sr-only">Remove Custom filter</span></button>');
  return chips.join("");
}

function roleAssignments(roleId) {
  return (roleManifestProjection()?.assignments || []).filter((item) => item.role_id === roleId);
}

function roleAssignmentsMarkup(roleId) {
  const nodes = new Map((state.overview?.nodes || []).map((node) => [node.id, node]));
  const assignments = roleAssignments(roleId);
  if (!assignments.length) return '<p class="role-specializations-empty">No current owners.</p>';
  return '<ul class="role-bindings">' + assignments.map((assignment) => {
    const node = nodes.get(assignment.task_id);
    const owner = node?.owner_id || node?.worker || node?.owner || "Unassigned";
    return '<li><strong>' + escapeHTML(owner) + '</strong><span>' + escapeHTML(assignment.task_id + " · " + (assignment.manifest_version || "Unknown version")) + '</span></li>';
  }).join("") + '</ul>';
}

function reviewerStancesMarkup(role) {
  if (role?.id !== "reviewer") return "";
  return '<section class="reviewer-stances" aria-label="Reviewer stances"><h4>Reviewer stances</h4><dl><div><dt>Friendly</dt><dd>Collaborative strengths, gaps, and clear repairs.</dd></div><div><dt>Hostile</dt><dd>Red-team the artifact with counterexamples, hidden assumptions, edge cases, and failure tests.</dd></div></dl><small>Stance changes neither authority nor the verdict evidence bar.</small></section>';
}

function roleTextList(items, empty) {
  return Array.isArray(items) && items.length ? '<ul>' + items.map((item) => '<li>' + escapeHTML(item) + '</li>').join("") + '</ul>' : '<p class="role-specializations-empty">' + escapeHTML(empty) + '</p>';
}

function roleChooserMarkup(role, match, selected) {
  const displayName = roleDisplayName(role);
  return '<button class="role-choice' + (selected ? ' is-selected' : '') + '" data-role-select="' + escapeHTML(role.id) + '" id="role-choice-' + escapeHTML(role.id) + '" role="option" aria-selected="' + String(selected) + '" aria-controls="role-library-detail" type="button">' + roleAvatar(role) + '<span><strong>' + escapeHTML(displayName) + '</strong><small>' + escapeHTML(roleSourceLabel(role)) + '</small>' + (match.label ? '<em>' + escapeHTML(match.label) + '</em>' : '') + '</span><svg class="lucide" aria-hidden="true"><use href="#lucide-chevron-right"></use></svg></button>';
}

function roleDetailMarkup(role, match = { label: "" }) {
  if (!role) return '<p class="empty-state">Choose a role to inspect its server-owned manifest.</p>';
  const displayName = roleDisplayName(role);
  const editAllowed = roleCanMutate("ROLE_MANIFEST_REVISE");
  return '<header class="role-detail-head">' + roleAvatar(role) + '<div><p class="eyebrow">' + escapeHTML(roleSourceLabel(role)) + '</p><h3 id="role-detail-title">' + escapeHTML(displayName) + '</h3><p>' + escapeHTML(role.purpose || "Purpose unavailable.") + '</p></div><div class="role-detail-actions"><button class="icon-button" data-role-action="generate-avatar" type="button" disabled aria-label="Generate avatar" title="Generate avatar unavailable"><svg class="lucide" aria-hidden="true"><use href="#lucide-sparkles"></use></svg></button><button class="icon-button" data-role-action="edit" data-role-id="' + escapeHTML(role.id) + '" type="button" aria-label="Edit ' + escapeHTML(displayName) + '" title="Edit role"' + (editAllowed ? "" : ' disabled') + '><svg class="lucide" aria-hidden="true"><use href="#lucide-pencil"></use></svg></button></div></header>' + (match.label ? '<p class="role-match">' + escapeHTML(match.label) + '</p>' : '') + '<div class="role-detail-sections"><section><h4>Owns</h4>' + roleTextList(role.owns, "No owned surface declared.") + '</section><section><h4>Default skills</h4>' + roleTextList(role.default_skills, "No default skills.") + '</section><section><h4>Instructions</h4>' + roleTextList(role.instructions, "No instructions.") + '</section><section><h4>Boundaries</h4>' + roleTextList(role.boundaries, "No boundaries declared.") + '</section><section><h4>Current owners</h4>' + roleAssignmentsMarkup(role.id) + '</section><section><h4>Specializations</h4>' + roleSpecializationsMarkup(role) + '<small>Metadata only · no authority transfer.</small></section></div>' + reviewerStancesMarkup(role) + '<footer><span>' + escapeHTML(roleHasRetainedAvatar(role) ? "Retained avatar" : "Accent fallback") + '</span><span>Active tasks retain their accepted role version.</span></footer>';
}

function renderRoleLibrary() {
  const projection = roleManifestProjection();
  const roles = roleCurrentRecords(projection);
  const filtered = roleFilterRecords(roles, state.roleSearch, state.roleTypes, state.roleSearchFields);
  const create = $("#role-create");
  const active = state.agentsTab === "active";
  create.hidden = active;
  create.disabled = !roleCanMutate("ROLE_MANIFEST_CREATE");
  create.setAttribute("aria-disabled", String(create.disabled));
  let status = state.roleManifestStatus === "loading" || state.roleManifestStatus === "refreshing"
    ? "Loading server-owned role manifests"
    : state.roleManifestStatus === "stale"
      ? "Showing the last received role manifests · refresh failed"
      : state.roleManifestStatus === "current" && projection
        ? (filtered.length === roles.length ? roles.length : filtered.length + " of " + roles.length) + " server-owned role manifest" + (roles.length === 1 ? "" : "s")
        : state.roleManifestStatus === "current"
          ? "Role manifest response was invalid"
          : (state.roleManifestError || "Role manifests unavailable");
  if (state.roleManifestMessage) status += " · " + state.roleManifestMessage;
  $("#role-library-status").textContent = status;
  $("#role-filter-chips").innerHTML = roleFilterChipsMarkup(state.roleTypes);
  if (!filtered.some(({ role }) => role.id === state.selectedRoleId)) state.selectedRoleId = filtered[0]?.role.id || "";
  const selected = filtered.find(({ role }) => role.id === state.selectedRoleId) || null;
  $("#role-library-grid").innerHTML = filtered.length ? filtered.map(({ role, match }) => roleChooserMarkup(role, match, role.id === state.selectedRoleId)).join("") : '<p class="empty-state">No roles match these filters. Clear the search or filters to see the server roster.</p>';
  $("#role-library-detail").innerHTML = roleDetailMarkup(selected?.role, selected?.match);
}

function renderAgents() {
  const active = state.agentsTab === "active";
  $$('[data-agents-tab]').forEach((tab) => { const selected = tab.dataset.agentsTab === state.agentsTab; tab.classList.toggle("is-active", selected); tab.setAttribute("aria-selected", String(selected)); tab.tabIndex = selected ? 0 : -1; });
  $$('[data-agents-panel]').forEach((panel) => { panel.hidden = panel.dataset.agentsPanel !== state.agentsTab; });
  renderAgentHierarchy();
  renderRoleLibrary();
}

function roleFieldValue(id, value) {
  const field = $(id);
  if (field) field.value = value == null ? "" : String(value);
}

function roleLines(value) {
  return String(value || "").split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
}

function roleAvatarDigestAllowed(value, manifestRoles, retainedAssets) {
  const digest = String(value || "").trim().toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(digest)) return false;
  return manifestRoles.some((role) => String(role.avatar_asset_digest || "").toLowerCase() === digest)
    || retainedAssets.some((item) => String(item.digest || "").toLowerCase() === digest);
}

function roleAvatarDigestValid(value) {
  return roleAvatarDigestAllowed(value, roleCurrentRecords(), assetItems());
}

function roleAvatarOptions(role) {
  const options = new Map();
  if (/^[0-9a-f]{64}$/i.test(role?.avatar_asset_digest || "")) options.set(role.avatar_asset_digest.toLowerCase(), "Current avatar");
  assetItems().forEach((item) => {
    const digest = String(item.digest || "").toLowerCase();
    if (/^[0-9a-f]{64}$/.test(digest)) options.set(digest, item.caption || item.kind || "Retained asset");
  });
  return [...options].map(([digest, label]) => '<option value="' + digest + '">' + escapeHTML(label + " · " + digest.slice(0, 12)) + '</option>').join("");
}

function updateRoleEditorAuthority(message = "") {
  const roleId = $("#role-field-id").value.trim();
  const role = roleRecord(roleId);
  const editing = state.roleEditorMode === "edit";
  const command = editing ? "ROLE_MANIFEST_REVISE" : "ROLE_MANIFEST_CREATE";
  const allowed = roleCanMutate(command);
  $$("#role-editor input, #role-editor textarea, #role-editor select").forEach((field) => { field.disabled = !allowed; });
  $("#role-field-id").readOnly = editing;
  $("#role-save").disabled = !allowed || !roleAvatarDigestValid($("#role-field-avatar").value);
  $("#role-reset").disabled = !(editing && role?.built_in && role.override_active && roleCanMutate("ROLE_MANIFEST_RESET"));
  const generate = $('#role-editor [data-role-action="generate-avatar"]');
  generate.disabled = true;
  generate.title = "Generate avatar is unavailable because the server exposes no generation command";
  $("#role-editor-status").textContent = message || (allowed ? "Saving creates a new server-owned version." : "Role changes are unavailable until current server authority is available.");
}

function openRoleEditor(roleId = "", trigger = null) {
  const role = roleId ? roleRecord(roleId) : { id: "", name: "", purpose: "", owns: [], instructions: [], boundaries: [], default_skills: [], specializations: [], avatar_asset_digest: "", accent: "#4da8ff", active_version: null, source: "custom" };
  if (!role) return;
  const editing = Boolean(roleId);
  state.roleEditorMode = editing ? "edit" : "create";
  state.roleManifestRetry = null;
  state.roleEditorTrigger = trigger;
  $("#role-editor-title").textContent = editing ? roleDisplayName(role) + " manifest" : "Create role";
  roleFieldValue("#role-field-id", role.id);
  roleFieldValue("#role-field-name", role.name);
  roleFieldValue("#role-field-purpose", role.purpose);
  roleFieldValue("#role-field-owns", (role.owns || []).join("\n"));
  roleFieldValue("#role-field-instructions", (role.instructions || []).join("\n"));
  roleFieldValue("#role-field-boundaries", (role.boundaries || []).join("\n"));
  roleFieldValue("#role-field-skills", (role.default_skills || []).join("\n"));
  $("#role-field-avatar").innerHTML = roleAvatarOptions(role);
  roleFieldValue("#role-field-avatar", role.avatar_asset_digest);
  roleFieldValue("#role-field-accent", role.accent || "#4da8ff");
  roleFieldValue("#role-field-specializations", roleSpecializations(role).join("\n"));
  $("#role-field-version").textContent = role.active_version || role.version || "New role";
  $("#role-field-source").textContent = roleSourceLabel(role);
  updateRoleEditorAuthority(!$("#role-field-avatar").value ? "Choose a retained image asset before saving." : "");
  $("#role-editor").showModal();
  requestAnimationFrame(() => (editing ? $("#role-field-name") : $("#role-field-id")).focus());
}

function closeRoleEditor() {
  if ($("#role-editor").open) $("#role-editor").close();
}

function roleEditorDraft() {
  const specializations = roleLines($("#role-field-specializations").value);
  if (specializations.length > 4) throw new Error("Choose no more than four specializations.");
  if (roleRecord($("#role-field-id").value.trim())?.built_in && specializations.length !== 4) throw new Error("Built-in professions require exactly four specializations.");
  const avatar = $("#role-field-avatar").value.trim().toLowerCase();
  if (!roleAvatarDigestValid(avatar)) throw new Error("Choose a retained avatar asset.");
  return {
    name: $("#role-field-name").value.trim(), purpose: $("#role-field-purpose").value.trim(),
    owns: roleLines($("#role-field-owns").value), instructions: roleLines($("#role-field-instructions").value),
    boundaries: roleLines($("#role-field-boundaries").value), default_skills: roleLines($("#role-field-skills").value),
    specializations, avatar_asset_digest: avatar, accent: $("#role-field-accent").value.toLowerCase(),
  };
}

function roleCommandPayload(command, roleId, expectedVersion, manifest, eventId, dedupeKey, observedAtMs) {
  const payload = { command, role_id: roleId, event_id: eventId, dedupe_key: dedupeKey, expected_active_version: expectedVersion, provenance: "console:role-library", observed_at_ms: observedAtMs };
  if (command !== "ROLE_MANIFEST_RESET") payload.manifest = manifest;
  return payload;
}

function roleCommandFingerprint(payload) {
  return JSON.stringify({ command: payload.command, role_id: payload.role_id, expected_active_version: payload.expected_active_version, manifest: payload.manifest || null });
}

function roleCommandReceiptMatches(result, payload) {
  return result?.ok === true && result.receipt?.command === payload.command && result.receipt?.role_id === payload.role_id && result.receipt?.event_id === payload.event_id;
}

function roleCommandObserved(projection, payload) {
  return projection?.roles?.find((role) => role.id === payload.role_id)?.source_event_ids?.includes(payload.event_id) === true;
}

function roleCommandResolution(result, failure, reloaded, observed) {
  if (observed) return "observed";
  if (failure?.status === 409) return "conflict";
  if (Number(failure?.status) >= 400 && Number(failure?.status) < 500) return "rejected";
  if (result && !reloaded) return "accepted-unreadable";
  return "ambiguous";
}

function roleCurrentIdAllowed(value) {
  const roleId = String(value || "").trim();
  return /^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/.test(roleId) && roleId.toLowerCase() !== "critic";
}

function roleEditorCommand(action) {
  const roleId = $("#role-field-id").value.trim();
  if (!roleCurrentIdAllowed(roleId)) throw new Error("Choose a safe role ID. Critic is retained as history, not available as a current role.");
  const current = roleRecord(roleId);
  const command = action === "reset" ? "ROLE_MANIFEST_RESET" : state.roleEditorMode === "create" ? "ROLE_MANIFEST_CREATE" : "ROLE_MANIFEST_REVISE";
  if (!roleCanMutate(command)) throw new Error("Current server authority is unavailable.");
  const manifest = command === "ROLE_MANIFEST_RESET" ? null : roleEditorDraft();
  const expected = command === "ROLE_MANIFEST_CREATE" ? null : current?.active_version;
  const draft = roleCommandPayload(command, roleId, expected, manifest, "", "", 0);
  const fingerprint = roleCommandFingerprint(draft);
  if (state.roleManifestRetry?.fingerprint === fingerprint) return state.roleManifestRetry.payload;
  if (!globalThis.crypto?.randomUUID) throw new Error("Secure command identity is unavailable.");
  const payload = roleCommandPayload(command, roleId, expected, manifest, crypto.randomUUID(), crypto.randomUUID(), Date.now());
  state.roleManifestRetry = { fingerprint, payload };
  return payload;
}

async function submitRoleCommand(action = "save") {
  if (state.roleManifestSaving) return;
  let payload;
  try { payload = roleEditorCommand(action); }
  catch (error) { updateRoleEditorAuthority(error.message); return; }
  state.roleManifestMessage = "";
  state.roleManifestSaving = true;
  updateRoleEditorAuthority("Saving role manifest…");
  let result = null;
  let failure = null;
  try {
    result = await api("/api/role-manifests/commands", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!roleCommandReceiptMatches(result, payload)) throw new Error("Role command receipt did not match the submitted operation.");
  } catch (error) { failure = error; }
  const reloaded = await refreshRoleManifests();
  const observed = reloaded && roleCommandObserved(roleManifestProjection(), payload);
  const resolution = roleCommandResolution(result, failure, reloaded, observed);
  state.roleManifestSaving = false;
  if (resolution === "observed") {
    state.roleManifestRetry = null;
    state.roleManifestMessage = failure ? "Role change reconciled from the server" : "Role change saved";
    closeRoleEditor();
    renderRoleLibrary();
    return;
  }
  if (resolution === "conflict") {
    state.roleManifestRetry = null;
    state.roleManifestMessage = "Role changed elsewhere";
    $("#role-field-version").textContent = roleRecord(payload.role_id)?.active_version || "Unknown";
    updateRoleEditorAuthority("Role changed elsewhere. Latest server version loaded; review your draft and save again.");
  } else if (resolution === "rejected") {
    state.roleManifestRetry = null;
    updateRoleEditorAuthority("Role change rejected: " + (failure?.message || "The server rejected this request."));
  } else if (resolution === "accepted-unreadable") {
    updateRoleEditorAuthority("Command was accepted, but the current server version could not be reloaded. Refresh before continuing.");
  } else {
    updateRoleEditorAuthority("Save outcome is unverified. Retry reuses the same operation identity.");
  }
  renderRoleLibrary();
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

function autoBinding() {
  const ctrl = selectedSettingsCtrl();
  if (!ctrl?.id || !ctrl?.project_id) return null;
  return { ctrlId: String(ctrl.id), projectId: String(ctrl.project_id) };
}

function autoBindingKey(binding) {
  return binding ? binding.projectId + "|" + binding.ctrlId : "";
}

function autoRequestId(command) {
  const values = new Uint32Array(4);
  window.crypto.getRandomValues(values);
  return "console-auto-" + command.toLowerCase() + "-" + [...values].map((value) => value.toString(16).padStart(8, "0")).join("");
}

function autoPresentation(auto) {
  const attention = auto?.attention;
  if (attention?.kind === "WAIT_USER") return ["Waiting for user", attention.reason || "A user decision is required before Auto can continue."];
  if (auto?.in_flight === true) return ["Active", "One accepted continuation is in flight."];
  if (attention) return ["Attention", attention.reason || "Auto needs review before it can continue."];
  if (auto?.enabled === true) return ["Enabled", "Eligible work may continue when the server admits it."];
  return ["Off", "Auto continuation is off for this CTRL."];
}

function autoSettingsMarkup() {
  const binding = autoBinding();
  if (!binding) return "";
  const matches = state.auto && state.autoBindingKey === autoBindingKey(binding);
  const current = matches && state.autoStatus === "current";
  const presentation = matches ? autoPresentation(state.auto) : ["Unavailable", "Auto status has not been loaded for this CTRL."];
  let note = presentation[1];
  if (state.autoStatus === "loading") note = "Loading the server-owned Auto status.";
  if (state.autoStatus === "refreshing") note = "Refreshing the server-owned Auto status.";
  if (state.autoStatus === "stale") note = "Auto status could not be refreshed. The last known value is shown read-only.";
  if (state.autoStatus === "unavailable") note = "Auto status is unavailable for this CTRL.";
  if (state.autoSaving) note = "Saving the explicit Auto setting.";
  if (state.autoError) note += " " + state.autoError;
  return '<h4>Auto</h4><label class="toggle-row"><input id="auto-continuation" type="checkbox" aria-label="Continue eligible work automatically" aria-describedby="auto-continuation-status"' + (matches && state.auto.enabled === true ? ' checked' : '') + (!current || state.autoSaving ? ' disabled' : '') + '><span>Continue eligible work automatically</span></label><p class="scope-setting-status" id="auto-continuation-status" aria-live="polite"><strong>' + escapeHTML(matches ? presentation[0] : state.autoStatus === "loading" ? "Loading" : "Unavailable") + '</strong><span>' + escapeHTML(note) + '</span></p>';
}

function chatRelayPresentation(config, configStatus, saving, error) {
  const serverValue = config?.settings?.chat_relay?.enabled;
  const editable = Array.isArray(config?.editable) && config.editable.includes("chat_relay.enabled");
  const hasServerValue = typeof serverValue === "boolean";
  const current = configStatus === "current" && hasServerValue;
  let title = current ? (serverValue ? "Enabled" : "Off") : "Unavailable";
  let note = current
    ? "Eligible work can be offloaded while SWARM still verifies results."
    : hasServerValue
      ? "The current server value could not be reloaded. The last known value is shown read-only."
      : "Chat relay is unavailable from the current server configuration.";
  if (saving) {
    title = "Saving";
    note = "Saving the explicit Chat relay setting.";
  }
  if (error) note += " " + error;
  return { checked: serverValue === true, disabled: !current || !editable || saving, title, note };
}

function chatRelayMutation(enabled) {
  return { changes: { "chat_relay.enabled": enabled === true } };
}

function chatRelayFailureState(previousConfig, reloadedConfig, saveError) {
  const reloaded = Boolean(reloadedConfig);
  return {
    config: reloaded ? reloadedConfig : previousConfig,
    configStatus: reloaded ? "current" : previousConfig ? "stale" : "unavailable",
    configError: saveError + (reloaded ? " The current server value was reloaded." : " The current server value could not be reloaded."),
  };
}

function chatRelaySettingsMarkup() {
  const presentation = chatRelayPresentation(state.config, state.configStatus, state.chatRelaySaving, state.configError);
  return '<section class="advanced-setting-group"><h4>Chat relay</h4><label class="toggle-row"><input id="chat-relay-enabled" type="checkbox" aria-label="Use ChatGPT for eligible work" aria-describedby="chat-relay-status"' + (presentation.checked ? ' checked' : '') + (presentation.disabled ? ' disabled' : '') + '><span>Use ChatGPT for eligible work</span></label><p class="scope-setting-status" id="chat-relay-status" aria-live="polite"><strong>' + escapeHTML(presentation.title) + '</strong><span>' + escapeHTML(presentation.note) + '</span></p></section>';
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
  const systemHealth = systemHealthPresentation();
  const ctrlAdvanced = selectedCtrl ? '<section class="advanced-setting-group"><h4>CTRL override</h4><p><strong>' + escapeHTML(publicLabel(selectedCtrl.project, "Project") + " / " + ctrlLabel(selectedCtrl)) + '</strong><br><span>' + escapeHTML(setting?.customized ? "Custom settings" : "Inherits global defaults") + '</span></p><label class="toggle-row"><input id="ctrl-customize" type="checkbox"' + (setting?.customized ? ' checked' : '') + '><span>Customize this CTRL separately</span></label>' + (setting?.customized ? '<div class="ctrl-fields"><label>Model<input id="ctrl-model" value="' + escapeHTML(effective.model || '') + '" autocomplete="off"></label><label>Reasoning<select id="ctrl-reasoning">' + reasoningOptions.map((option) => '<option value="' + option + '"' + (option === effective.reasoning ? ' selected' : '') + '>' + option + '</option>').join('') + '</select></label></div><button class="quiet-button" data-setting-action="save-ctrl" type="button">Save CTRL settings</button>' : '') + '<button class="quiet-button" data-setting-action="reset" type="button"' + (!setting?.customized ? ' disabled' : '') + '>Use global defaults</button></section>' : '';
  $("#settings-grid").innerHTML =
    '<section class="panel settings-card system-health-card" id="system-health-panel" tabindex="-1" aria-labelledby="system-health-heading"><p class="eyebrow">Diagnostics</p><h3 id="system-health-heading">System health</h3><p class="system-health-summary"><span class="status-dot' + (systemHealth.className ? ' ' + systemHealth.className : '') + '" id="system-health-panel-dot" aria-hidden="true"></span><strong id="system-health-state">' + escapeHTML(systemHealth.label) + '</strong></p><p id="system-health-note">' + escapeHTML(systemHealth.note) + '</p></section>' +
    '<section class="panel settings-card"><p class="eyebrow">Settings scope</p><h3>Where changes apply</h3><label class="setting-field">Scope<select id="settings-scope">' + settingsScopeOptions() + '</select></label><p class="scope-setting-status"><strong>' + escapeHTML(selectedCtrl ? publicLabel(selectedCtrl.project, "Project") + " / " + ctrlLabel(selectedCtrl) : scope.type === "project" ? scopeLabel() : "Global defaults") + '</strong><span>' + escapeHTML(selectedCtrl ? (setting?.customized ? "Custom settings" : "Inherits global defaults") : "Uses the current server-owned settings") + '</span></p><small>Per-CTRL overrides are in Advanced settings.</small></section>' +
    '<section class="panel settings-card"><p class="eyebrow">Work routing</p><h3>How work is handled</h3>' +
      settingSelect('execution.max_reasoning', execution.max_reasoning || 'medium', reasoningOptions, 'Default reasoning') +
      settingToggle('execution.fast_mode', execution.fast_mode, 'Fast mode') + '<small>Requests faster service for new assignments. SWARM reports it active only from a host receipt.</small>' +
      settingToggle('execution.usage_saver', execution.usage_saver, 'Use less usage when possible') +
      settingToggle('boost.spark_enabled', boost.spark_enabled, 'Use Spark for safe small tasks') + '<small>Spark stays bounded to quick, low-risk work.</small>' + autoSettingsMarkup() + '<h4>Skills</h4>' + skillsSummary(scope) + '</section>' +
    '<section class="panel settings-card"><p class="eyebrow">Console and data</p><h3>Keep the workspace predictable</h3>' +
      settingToggle('console.project_progress_feed_enabled', consoleSettings.project_progress_feed_enabled, 'Progress feed') +
      '<label class="setting-field">Updates shown<input data-config-key="console.project_progress_feed_lines" type="number" min="1" max="10" value="' + escapeHTML(consoleSettings.project_progress_feed_lines ?? 4) + '"' + (!configEditable('console.project_progress_feed_lines') ? ' disabled' : '') + '></label>' +
      settingToggle('console.open_on_start', consoleSettings.open_on_start, 'Open SWARM when Codex starts') +
      '<label class="toggle-row"><input id="auto-health" type="checkbox"' + (state.health?.enabled ? ' checked' : '') + '><span>Request health review when needed</span></label><small>Passive monitoring does not run models.</small><div class="guided-tour-setting"><span><strong>Guided tour</strong><small>Replay the current console introduction.</small></span><button class="quiet-button" data-setting-action="replay-tour" type="button">Replay tour</button></div></section>' +
      '<details class="panel settings-advanced settings-wide" id="settings-advanced"><summary>Advanced settings</summary><div class="settings-advanced-grid">' + ctrlAdvanced + chatRelaySettingsMarkup() + '<section class="advanced-setting-group"><h4>Spark and monitoring</h4>' + settingSelect('boost.spark_reasoning', boost.spark_reasoning || 'xhigh', reasoningOptions, 'Spark reasoning') + '<label class="setting-field">Spark model<input id="spark-model" value="' + escapeHTML(boost.spark_model || '') + '" autocomplete="off"' + (!configEditable('boost.spark_model') ? ' disabled' : '') + '></label><label class="setting-field">Heartbeat minutes<input id="heartbeat-minutes" data-config-key="monitoring.heartbeat_minutes" type="number" min="1" value="' + escapeHTML(monitoring.heartbeat_minutes || '') + '"' + (!configEditable('monitoring.heartbeat_minutes') ? ' disabled' : '') + '></label><button class="quiet-button" data-setting-action="save-spark" type="button"' + (!configEditable('boost.spark_model') ? ' disabled' : '') + '>Save Spark model</button>' + settingToggle('role_icons.enabled', roleIcons.enabled, 'Show role icons') + '</section><section class="advanced-setting-group"><h4>' + escapeHTML(storage?.bytes == null ? 'Saved history unavailable' : formatBytes(storage.bytes) + ' saved history' + retention) + '</h4><p>Progress, forecasts, proof, and token history stay available between sessions' + (proofFiles ? ' · ' + proofFiles + ' proof file' + (proofFiles === 1 ? '' : 's') : '') + '.</p><div class="settings-actions-inline"><button class="quiet-button" data-setting-action="clear" type="button">Clear history</button><button class="quiet-button" data-setting-action="restore" type="button">Restore defaults</button></div><small>Clearing history leaves tasks unchanged. Restoring defaults keeps history.</small>' + skillsAdvanced(scope) + '</section></div></details>';
  renderSystemHealth();
}

function renderAllViews() { renderOverview(); renderAgents(); renderReview(); renderAssets(); renderSettings(); renderRunLogSurfaces(); }

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
  const hasLastGood = state.usageScopeKey === requestKey && state.usageHistory?.ok === true;
  state.usageStatus = hasLastGood ? "refreshing" : "loading";
  try {
    const result = await api('/api/usage-history?' + params.toString());
    if (request.projectId !== state.projectId || request.ctrlId !== state.ctrlId || request.hours !== state.usageWindowHours) return;
    state.usageHistory = result;
    state.usageScopeKey = requestKey;
    state.usageStatus = "current";
    state.usageError = "";
  } catch (error) {
    if (request.projectId !== state.projectId || request.ctrlId !== state.ctrlId || request.hours !== state.usageWindowHours) return;
    if (!hasLastGood) state.usageHistory = null;
    state.usageScopeKey = requestKey;
    state.usageStatus = hasLastGood ? "stale" : "error";
    state.usageError = error.message || "Usage history unavailable";
  }
}

async function refreshProjectProgress() {
  const projectId = selectedProgressProjectId();
  if (!projectId) {
    state.projectProgress = null;
    state.projectProgressProjectId = "";
    state.projectProgressStatus = "idle";
    state.projectProgressError = "";
    return;
  }
  const hasLastGood = state.projectProgressProjectId === projectId && state.projectProgress?.ok === true;
  if (!hasLastGood) state.projectProgress = null;
  state.projectProgressProjectId = projectId;
  state.projectProgressStatus = hasLastGood ? "refreshing" : "loading";
  try {
    const result = await api('/api/project-progress?project_id=' + encodeURIComponent(projectId));
    if (projectId !== selectedProgressProjectId()) return;
    state.projectProgress = result;
    state.projectProgressStatus = "current";
    state.projectProgressError = "";
  } catch (error) {
    if (projectId !== selectedProgressProjectId()) return;
    if (!hasLastGood) state.projectProgress = null;
    state.projectProgressStatus = hasLastGood ? "stale" : "unavailable";
    state.projectProgressError = error.message || "Project ledger unavailable";
  }
}

async function refreshProjectProgressFeed() {
  const projectId = selectedProgressProjectId();
  if (!projectId) {
    state.projectProgressFeed = null;
    state.projectProgressFeedProjectId = "";
    state.projectProgressFeedStatus = "idle";
    state.projectProgressFeedError = "";
    return;
  }
  const hasLastGood = state.projectProgressFeedProjectId === projectId && Array.isArray(state.projectProgressFeed?.items);
  if (!hasLastGood) {
    state.projectProgressFeed = null;
    state.projectProgressFeedProjectId = projectId;
  }
  state.projectProgressFeedStatus = hasLastGood ? "refreshing" : "loading";
  try {
    const params = new URLSearchParams({ project_id: projectId, after_cursor: "0" });
    const result = await api('/api/project-progress-feed?' + params.toString());
    if (projectId !== selectedProgressProjectId()) return;
    state.projectProgressFeed = result;
    state.projectProgressFeedProjectId = projectId;
    state.projectProgressFeedStatus = "current";
    state.projectProgressFeedError = "";
  } catch (error) {
    if (projectId !== selectedProgressProjectId()) return;
    if (!hasLastGood) state.projectProgressFeed = null;
    state.projectProgressFeedProjectId = projectId;
    state.projectProgressFeedStatus = hasLastGood ? "stale" : "unavailable";
    state.projectProgressFeedError = error.message || "Project updates unavailable";
  }
}

async function refreshMonitoring(proofSequence) {
  try {
    state.overview = await api("/api/overview", { timeoutMs: 15_000 });
    clearConnectionState();
    setDataStatus("current", state.overview?.generated_at);
    renderProjectNavigation();
    await Promise.all([refreshUsageHistory(), refreshNotifications(), refreshRunLogs()]);
    if (Number(proofSequence) !== state.proofSequence) await refreshProof();
    renderOverview();
    renderAgents();
    renderReview();
    renderAssets();
    renderRunLogSurfaces();
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

async function refreshAutoStatus() {
  const binding = autoBinding();
  if (!binding) {
    state.auto = null;
    state.autoBindingKey = "";
    state.autoStatus = "idle";
    state.autoError = "";
    return;
  }
  const bindingKey = autoBindingKey(binding);
  const hasLastGood = state.auto && state.autoBindingKey === bindingKey;
  state.autoStatus = hasLastGood ? "refreshing" : "loading";
  state.autoError = "";
  try {
    const params = new URLSearchParams({ ctrl_id: binding.ctrlId, project_id: binding.projectId });
    const result = await api('/api/auto?' + params.toString());
    if (autoBindingKey(autoBinding()) !== bindingKey) return;
    state.auto = result;
    state.autoBindingKey = bindingKey;
    state.autoStatus = "current";
  } catch (error) {
    if (autoBindingKey(autoBinding()) !== bindingKey) return;
    if (!hasLastGood) state.auto = null;
    state.autoBindingKey = bindingKey;
    state.autoStatus = hasLastGood ? "stale" : "unavailable";
    state.autoError = error.message || "Auto status could not be loaded.";
  }
}

async function refreshRoleManifests() {
  const lastGood = roleManifestProjectionValue(state.roleManifests);
  const hasLastGood = Boolean(lastGood);
  state.roleManifestStatus = hasLastGood ? "refreshing" : "loading";
  try {
    const result = await api('/api/role-manifests');
    if (!roleManifestProjectionValue(result)) throw new Error("Role manifest response was invalid.");
    state.roleManifests = result;
    state.roleManifestStatus = "current";
    state.roleManifestError = "";
    return true;
  } catch (error) {
    state.roleManifests = lastGood;
    state.roleManifestStatus = hasLastGood ? "stale" : "unavailable";
    state.roleManifestError = error.message || "Role library unavailable";
    return false;
  }
}

async function refreshOverview(showLoading = true) {
  if (showLoading) setLoading(true);
  clearError();
  setDataStatus("connecting", state.overview?.generated_at);
  try {
    state.overview = await api("/api/overview", { timeoutMs: 15_000 });
    clearConnectionState();
    setDataStatus("current", state.overview?.generated_at);
    renderProjectNavigation();
    await Promise.all([refreshProof(), refreshUsageHistory(), refreshProjectProgress(), refreshProjectProgressFeed(), refreshRoleManifests(), refreshNotifications(), refreshRunLogs()]);
    const selectedCtrl = state.ctrlId || historicalControllers()[0]?.id || '';
    const previousConfig = state.config;
    const results = await Promise.allSettled([api('/api/diagnostics'), api('/api/health/settings'), api('/api/storage'), selectedCtrl ? api('/api/ctrl-settings?ctrl_id=' + encodeURIComponent(selectedCtrl)) : Promise.resolve(null), api('/api/config')]);
    [state.diagnostics, state.health, state.storage, state.ctrlSettings, state.config] = results.map((result) => result.status === 'fulfilled' ? result.value : null);
    if (results[4].status === 'fulfilled') {
      state.configStatus = "current";
      state.configError = "";
    } else {
      state.config = previousConfig;
      state.configStatus = previousConfig ? "stale" : "unavailable";
      state.configError = results[4].reason?.message || "Settings could not be loaded.";
    }
    await Promise.all([refreshSkills(), refreshAutoStatus()]);
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
  setDataStatus("connecting", state.overview?.generated_at);
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
  openOnboarding();
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

document.addEventListener("click", async (event) => {
  if (!$("#notifications-panel").hidden && !event.target.closest("#notifications-panel, #notifications")) {
    setNotificationsOpen(false);
  }
  const onboardingDot = event.target.closest("[data-onboarding-step]");
  if (onboardingDot) {
    setOnboardingStep(onboardingDot.dataset.onboardingStep, true);
    return;
  }
  const assetView = event.target.closest("[data-asset-view]");
  if (assetView) {
    state.assetView = assetView.dataset.assetView === "list" ? "list" : "grid";
    renderAssets();
    $('[data-asset-view="' + state.assetView + '"]')?.focus({ preventScroll: true });
    return;
  }
  const projectTab = event.target.closest("[data-project-tab]");
  if (projectTab) {
    state.projectTab = projectTab.dataset.projectTab;
    renderProjectDetail();
    renderRunLogSurfaces();
    if (state.projectTab === "logs") refreshRunLogs();
    projectTab.focus({ preventScroll: true });
    return;
  }
  const runLogAgent = event.target.closest("[data-run-log-agent]");
  if (runLogAgent) {
    state.runLogAgent = {
      projectId: runLogAgent.dataset.projectId,
      ctrlId: runLogAgent.dataset.ctrlId,
      agentId: runLogAgent.dataset.runLogAgent,
      label: runLogAgent.dataset.agentLabel,
    };
    renderAgents();
    renderRunLogSurfaces();
    refreshRunLogs();
    return;
  }
  const runLogLatest = event.target.closest("[data-run-log-latest]");
  if (runLogLatest) {
    const surface = runLogLatest.dataset.runLogLatest;
    const mount = $('[data-run-log-surface="' + CSS.escape(surface) + '"]');
    const scroller = mount ? $(".run-log-list", mount) : null;
    if (!scroller) return;
    const view = runLogSurfaceState(surface, mount.dataset.runLogBindingKey || "");
    view.nearBottom = true;
    view.newEntries = 0;
    runLogLatest.hidden = true;
    scroller.scrollTop = scroller.scrollHeight;
    scroller.focus({ preventScroll: true });
    return;
  }
  const notificationAction = event.target.closest('[data-notification-action="navigate"][data-notification-id]');
  if (notificationAction) {
    const id = notificationAction.dataset.notificationId;
    const entry = notificationActionEntry(notificationData(), id);
    await notificationNavigateEntry(entry, (identity) => acknowledgeNotifications([identity]), navigateNotification);
    return;
  }
  const toastAction = event.target.closest("[data-notification-toast-action]");
  if (toastAction) {
    const item = state.notificationToast?.item || null;
    const action = toastAction.dataset.notificationToastAction;
    if (action === "dismiss") await dismissNotificationToast(true);
    if (action === "open" && item) {
      await notificationActionAfterAcknowledgement(item, (identity) => acknowledgeNotifications([identity]), (notification) => {
        clearNotificationToast();
        navigateNotification(notification);
      });
    }
    return;
  }
  const reviewOpen = event.target.closest("[data-review-open]");
  if (reviewOpen && !reviewOpen.disabled) {
    openProofIdentity(reviewOpen.dataset.reviewOpen, reviewOpen);
    return;
  }
  const asset = event.target.closest("[data-asset-detail]");
  if (asset) {
    state.selectedAssetIdentity = asset.dataset.assetDetail;
    renderAssets();
    $("#asset-detail")?.focus({ preventScroll: true });
    return;
  }
  const agentsTab = event.target.closest("[data-agents-tab]");
  if (agentsTab) {
    state.agentsTab = agentsTab.dataset.agentsTab === "library" ? "library" : "active";
    renderAgents();
    $("#agents-tab-" + state.agentsTab)?.focus({ preventScroll: true });
    return;
  }
  const roleFilterClear = event.target.closest("[data-role-filter-clear]");
  if (roleFilterClear) {
    state.roleTypes = new Set(["builtin", "custom"]);
    $$('[data-role-type]').forEach((input) => { input.checked = true; });
    renderRoleLibrary();
    $("#role-search").focus({ preventScroll: true });
    return;
  }
  const roleSelect = event.target.closest("[data-role-select]");
  if (roleSelect) {
    state.selectedRoleId = roleSelect.dataset.roleSelect;
    renderRoleLibrary();
    $('[data-role-select="' + CSS.escape(state.selectedRoleId) + '"]')?.focus({ preventScroll: true });
    return;
  }
  const roleAction = event.target.closest("[data-role-action]");
  if (roleAction) {
    if (roleAction.dataset.roleAction === "edit") openRoleEditor(roleAction.dataset.roleId, roleAction);
    if (roleAction.dataset.roleAction === "create" && !roleAction.disabled) openRoleEditor("", roleAction);
    if (roleAction.dataset.roleAction === "reset" && !roleAction.disabled) await submitRoleCommand("reset");
    return;
  }
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
    renderAllViews();
    refreshUsageHistory().then(renderAllViews);
    return;
  }
  const tab = event.target.closest("[data-view]");
  if (tab) {
    setView(tab.dataset.view);
    if (mobileDrawerQuery.matches) setMobileDrawer(false, true);
  }
});

$("#onboarding-close").addEventListener("click", () => closeOnboarding());
$("#onboarding-skip").addEventListener("click", () => closeOnboarding());
$("#onboarding-back").addEventListener("click", () => setOnboardingStep(state.onboardingStep - 1));
$("#onboarding-primary").addEventListener("click", () => {
  if (state.onboardingStep === ONBOARDING_STEPS.length - 1) closeOnboarding(true);
  else setOnboardingStep(state.onboardingStep + 1);
});
$(".onboarding-progress").addEventListener("keydown", (event) => {
  if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
  const next = event.key === "Home" ? 0 : event.key === "End" ? ONBOARDING_STEPS.length - 1 : (state.onboardingStep + (event.key === "ArrowRight" ? 1 : -1) + ONBOARDING_STEPS.length) % ONBOARDING_STEPS.length;
  event.preventDefault();
  setOnboardingStep(next, true);
});
$("#onboarding-dialog").addEventListener("close", () => {
  markOnboardingSeen();
  state.onboardingTrigger?.focus({ preventScroll: true });
  state.onboardingTrigger = null;
});

$("#evidence-lightbox").addEventListener("close", () => {
  state.evidenceTrigger?.focus();
  state.evidenceTrigger = null;
});
$("#evidence-lightbox-image").addEventListener("error", () => {
  $("#evidence-lightbox-image").hidden = true;
  $("#evidence-lightbox-failed").hidden = false;
});
document.addEventListener("error", (event) => {
  const image = event.target.closest?.("[data-asset-image]");
  if (!image) return;
  image.hidden = true;
  const failed = image.parentElement?.querySelector(".asset-image-failed");
  if (failed) failed.hidden = false;
}, true);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("#notifications-panel").hidden) {
    event.preventDefault();
    setNotificationsOpen(false, true);
    return;
  }
  if (event.key === "Escape" && $(".app-shell").classList.contains("is-drawer-open")) {
    event.preventDefault();
    setMobileDrawer(false, true);
    return;
  }
  if (event.key === "Tab" && $(".app-shell").classList.contains("is-drawer-open")) {
    const drawer = $("#console-drawer");
    const focusable = mobileDrawerFocusable();
    const first = focusable[0];
    const last = focusable.at(-1);
    if (!first) {
      event.preventDefault();
      return;
    }
    if (event.shiftKey && (document.activeElement === first || !drawer.contains(document.activeElement))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || !drawer.contains(document.activeElement))) {
      event.preventDefault();
      first.focus();
    }
    return;
  }
  if (!$("#evidence-lightbox").open || !["ArrowLeft", "ArrowRight"].includes(event.key)) return;
  const nextIndex = state.evidenceIndex + (event.key === "ArrowLeft" ? -1 : 1);
  if (nextIndex < 0 || nextIndex >= state.evidenceImages.length) return;
  event.preventDefault();
  state.evidenceIndex = nextIndex;
  renderEvidenceLightbox();
});
document.addEventListener("scroll", (event) => {
  const scroller = event.target.closest?.(".run-log-list");
  if (!scroller) return;
  const surface = scroller.closest("[data-run-log-surface]")?.dataset.runLogSurface;
  if (!surface) return;
  const mount = scroller.closest("[data-run-log-surface]");
  const view = runLogSurfaceState(surface, mount?.dataset.runLogBindingKey || "");
  view.nearBottom = runLogNearBottom(scroller.scrollHeight, scroller.scrollTop, scroller.clientHeight);
  if (view.nearBottom) {
    view.newEntries = 0;
    const affordance = $('[data-run-log-latest="' + CSS.escape(surface) + '"]');
    if (affordance) affordance.hidden = true;
  }
}, true);

$("#project-navigation").addEventListener("click", (event) => {
  const scope = event.target.closest("[data-project-id]");
  if (!scope) return;
  event.preventDefault();
  state.projectId = scope.dataset.projectId;
  state.ctrlId = scope.dataset.ctrlId || "";
  state.settingsCtrlId = state.ctrlId;
  state.settingsScopeType = state.ctrlId ? 'ctrl' : (state.projectId === 'all' ? 'global' : 'project');
  state.settingsScopeId = state.ctrlId || (state.projectId === 'all' ? 'global' : state.projectId);
  state.projectTab = "overview";
  renderProjectNavigation();
  setView("overview", false);
  renderAllViews();
  Promise.all([refreshProof(), refreshCtrlSettings(), refreshUsageHistory(), refreshProjectProgress(), refreshProjectProgressFeed(), refreshSkills(), refreshNotifications(), refreshRunLogs()]).then(renderAllViews);
});
$("#refresh").addEventListener("click", refreshOverview);
$("#system-health-control").addEventListener("click", openSystemHealth);
$("#retry").addEventListener("click", refreshOverview);
$("#connection-retry").addEventListener("click", initialize);
$("#notifications").addEventListener("click", () => setNotificationsOpen($("#notifications-panel").hidden));
$("#notifications-close").addEventListener("click", () => setNotificationsOpen(false, true));
$("#notifications-retry").addEventListener("click", async () => {
  const ids = renderedNotificationUnreadIds();
  if (ids.length && notificationData()) await acknowledgeNotifications(ids);
  else await refreshNotifications();
});
$("#role-editor-close").addEventListener("click", closeRoleEditor);
$("#role-editor-cancel").addEventListener("click", closeRoleEditor);
$("#role-editor").addEventListener("close", () => { state.roleEditorTrigger?.focus({ preventScroll: true }); state.roleEditorTrigger = null; });
$("#role-editor-form").addEventListener("input", () => {
  state.roleManifestRetry = null;
  updateRoleEditorAuthority(!$("#role-field-avatar").value ? "Choose a retained image asset before saving." : "");
});
$("#role-editor-form").addEventListener("submit", async (event) => { event.preventDefault(); await submitRoleCommand("save"); });
$("#role-search").addEventListener("input", (event) => {
  state.roleSearch = event.target.value;
  renderRoleLibrary();
});
$("#role-filter-reset").addEventListener("click", () => {
  state.roleSearch = "";
  state.roleTypes = new Set(["builtin", "custom"]);
  state.roleSearchFields = new Set(["profession", "specialization", "alias", "skills", "purpose"]);
  $("#role-search").value = "";
  $$('[data-role-type],[data-role-search-field]').forEach((input) => { input.checked = true; });
  renderRoleLibrary();
  $("#role-search").focus({ preventScroll: true });
});
$("#mobile-menu-button").addEventListener("click", () => setMobileDrawer(!$(".app-shell").classList.contains("is-drawer-open"), true));
$("#drawer-backdrop").addEventListener("click", () => setMobileDrawer(false, true));
mobileDrawerQuery.addEventListener("change", syncMobileDrawer);
document.addEventListener('change', async (event) => {
  if (event.target.matches('[data-role-type]')) {
    const type = event.target.dataset.roleType;
    if (event.target.checked) state.roleTypes.add(type);
    else state.roleTypes.delete(type);
    renderRoleLibrary();
    return;
  }
  if (event.target.matches('[data-role-search-field]')) {
    const field = event.target.dataset.roleSearchField;
    if (event.target.checked) state.roleSearchFields.add(field);
    else state.roleSearchFields.delete(field);
    renderRoleLibrary();
    return;
  }
  if (event.target.id === 'project-scope-filter') {
    state.projectId = event.target.value || 'all';
    state.ctrlId = '';
    state.projectTab = 'overview';
    state.settingsCtrlId = '';
    state.settingsScopeType = state.projectId === 'all' ? 'global' : 'project';
    state.settingsScopeId = state.projectId === 'all' ? 'global' : state.projectId;
    renderProjectNavigation();
    renderAllViews();
    try {
      await Promise.all([refreshProof(), refreshUsageHistory(), refreshProjectProgress(), refreshProjectProgressFeed(), refreshCtrlSettings(), refreshSkills(), refreshNotifications(), refreshRunLogs()]);
      await refreshAutoStatus();
    }
    finally { renderAllViews(); }
    return;
  }
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
      await Promise.all([refreshProof(), refreshUsageHistory(), refreshProjectProgress(), refreshProjectProgressFeed(), refreshCtrlSettings(), refreshSkills(), refreshNotifications(), refreshRunLogs()]);
      await refreshAutoStatus();
    } finally { renderAllViews(); }
    return;
  }
  if (event.target.id === 'auto-continuation') {
    const binding = autoBinding();
    if (!binding || state.autoStatus !== "current" || state.autoSaving) { renderSettings(); return; }
    const command = event.target.checked ? "ENABLE" : "DISABLE";
    state.autoSaving = true;
    state.autoError = "";
    renderSettings();
    try {
      state.auto = await api('/api/auto', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command, ctrl_id: binding.ctrlId, project_id: binding.projectId, request_id: autoRequestId(command) }) });
      state.autoBindingKey = autoBindingKey(binding);
      state.autoStatus = "current";
    } catch (error) {
      state.autoError = error.message || "Auto setting could not be saved.";
      await refreshAutoStatus();
      if (state.autoStatus === "current") state.autoError = error.message || "Auto setting could not be saved.";
    } finally {
      state.autoSaving = false;
      renderSettings();
    }
    return;
  }
  if (event.target.id === 'chat-relay-enabled') {
    if (state.configStatus !== "current" || !configEditable("chat_relay.enabled") || state.chatRelaySaving) { renderSettings(); return; }
    const requestedValue = event.target.checked;
    const previousConfig = state.config;
    state.chatRelaySaving = true;
    state.configError = "";
    renderSettings();
    try {
      state.config = await api('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(chatRelayMutation(requestedValue)) });
      state.configStatus = "current";
    } catch (error) {
      const saveError = error.message || "Chat relay setting could not be saved.";
      try {
        Object.assign(state, chatRelayFailureState(previousConfig, await api('/api/config'), saveError));
      } catch (reloadError) {
        Object.assign(state, chatRelayFailureState(previousConfig, null, saveError));
      }
    } finally {
      state.chatRelaySaving = false;
      renderSettings();
    }
    return;
  }
  if (event.target.id === 'auto-health') {
    try { state.health = await api('/api/health/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: event.target.checked }) }); renderSettings(); } catch (error) { showError(error.message); renderSettings(); }
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
  if (action === 'replay-tour') {
    openOnboarding(true, event.target.closest('[data-setting-action]'));
    return;
  }
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
$(".drawer-navigation").addEventListener("keydown", (event) => {
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
  const tabs = $$(".nav-item");
  const index = tabs.indexOf(document.activeElement);
  const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + tabs.length) % tabs.length;
  event.preventDefault();
  tabs[next].focus();
  setView(tabs[next].dataset.view, true);
});

$(".agents-tabs").addEventListener("keydown", (event) => {
  if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
  const tabs = $$('[data-agents-tab]');
  const index = tabs.indexOf(document.activeElement);
  const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
  event.preventDefault();
  state.agentsTab = tabs[next].dataset.agentsTab;
  renderAgents();
  tabs[next].focus();
});

$(".project-tabs").addEventListener("keydown", (event) => {
  if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
  const tabs = $$('[data-project-tab]');
  const index = tabs.indexOf(document.activeElement);
  const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
  event.preventDefault();
  state.projectTab = tabs[next].dataset.projectTab;
  renderProjectDetail();
  renderRunLogSurfaces();
  if (state.projectTab === "logs") refreshRunLogs();
  tabs[next].focus();
});

document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") reportPresence(); });
window.addEventListener("pagehide", () => { if (presenceTimer) clearInterval(presenceTimer); });

syncMobileDrawer();
setView(routeView(), false, routeView() === 'overview' && location.hash !== '#overview');
window.addEventListener('hashchange', () => setView(routeView(), false, routeView() === 'overview' && location.hash !== '#overview'));
initialize().then(startPresence);
