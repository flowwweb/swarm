const state = { token: "", overview: null, proof: [], proofCollections: new Map(), proofStatuses: new Map(), proofStatus: "idle", proofSequence: 0, usageHistory: null, usageWindowHours: 1, usageScopeKey: "", usageStatus: "idle", usageError: "", projectProgress: null, projectProgressProjectId: "", projectProgressStatus: "idle", projectProgressError: "", projectProgressFeed: null, projectProgressFeedProjectId: "", projectProgressFeedStatus: "idle", projectProgressFeedError: "", projectTab: "overview", projectUiMode: "screens", projectUiGroupId: "", runLogs: new Map(), runLogRequestGenerations: new Map(), runLogSurfaceStates: new Map(), runLogAgent: null, agentUpdatesFilter: "all", agentUpdatesPaused: false, agentDetailTrigger: null, diagnostics: null, diagnosticsHistory: null, diagnosticsHistoryStatus: "idle", diagnosticsError: "", diagnosticsSelectedChecks: new Set(), diagnosticsSelectionInitialized: false, diagnosticsRepairPreview: null, diagnosticsRepairPending: false, diagnosticsRepairError: "", diagnosticsRepairTrigger: null, health: null, storage: null, profile: null, profileStatus: "idle", profileError: "", profileUpload: null, profilePreviewUrl: "", profileSaving: false, profileTrigger: null, messageOpen: false, messageTrigger: null, messageDraft: "", messageRecipientId: "", messageStatus: "unavailable", messageError: "", messageReceipt: null, config: null, configStatus: "idle", configError: "", configResetPending: null, configResetRetry: null, chatRelaySaving: false, settingsDraft: new Map(), settingsSaving: false, settingsSaveError: "", settingsSaveMessage: "", configEditorTrigger: null, ctrlSettings: null, auto: null, autoBindingKey: "", autoStatus: "idle", autoError: "", autoSaving: false, skills: null, skillsError: "", roleManifests: null, roleManifestStatus: "unavailable", roleManifestError: "", roleManifestMessage: "", roleManifestSaving: false, roleManifestRetry: null, roleEditorMode: "", roleEditorTrigger: null, roleSearch: "", roleTypes: new Set(["builtin", "custom"]), roleSearchFields: new Set(["profession", "specialization", "alias", "skills", "purpose"]), selectedRoleId: "", assets: null, assetBindingKey: "", assetStatus: "idle", assetError: "", assetProjection: "active", assetView: "grid", assetRequestGeneration: 0, assetEventCursors: new Map(), assetMutationPending: null, assetConfirm: null, assetUndo: null, selectedAssetIdentity: "", assetTrigger: null, onboardingStep: 0, onboardingShown: false, onboardingTrigger: null, onboardingFlowZoom: 1, onboardingConfigPending: new Map(), onboardingConfigFailures: new Map(), notifications: null, notificationBindingKey: "", notificationStatus: "idle", notificationError: "", notificationAckFlight: null, notificationRequestGenerations: new Map(), notificationPresentedIds: new Set(), notificationToast: null, notificationToastTimer: null, notificationTrigger: null, connectionStatus: "reconnecting", view: "overview", projectId: "all", ctrlId: "", scopeNotice: "", scopeNoticeVisible: false, settingsCtrlId: "", settingsScopeType: "", settingsScopeId: "", evidenceImages: [], evidenceIndex: 0, evidenceTrigger: null };
const PROFILE_API_CONTRACT = Object.freeze({ read: "/api/profile", write: "/api/profile", schemaVersion: 1, avatarField: "avatar", profileField: "profile" });
const DIAGNOSTICS_HISTORY_HOURS = 1;
const MESSAGE_CONNECTOR_UNAVAILABLE = "Messaging is unavailable until SWARM exposes the authenticated HQ connector.";
let configMutationTail = Promise.resolve();
let configAuthorityGeneration = 0;
let lastAppliedHistoryRoute = "";
const EVIDENCE_THUMBNAIL_PAGE_SIZE = 24;
const RUN_LOG_CLIENT_LIMIT = 200;
const ONBOARDING_PRESENTATION_KEY = "swarm.onboarding.v2.seen";
const ONBOARDING_STEPS = [
  { name: "Welcome", primary: "Start guided tour" },
  { name: "Coordinated roles", primary: "Continue" },
  { name: "Role variety", primary: "Continue" },
  { name: "Project views", primary: "Continue" },
  { name: "Configuration", primary: "Start using SWARM" },
];
const ONBOARDING_COORDINATION_GROUPS = [
  { id: "coo", label: "COO", accent: "#4da8ff", leads: [
    { id: "operations", label: "Operations", roleId: "operator", icon: "settings" },
    { id: "delivery", label: "Delivery", roleId: "strategist", icon: "git-branch" },
    { id: "support", label: "Support", roleId: "support", icon: "message-square" },
  ] },
  { id: "cto", label: "CTO", accent: "#9b7cff", leads: [
    { id: "engineering", label: "Engineering", roleId: "developer", icon: "git-branch" },
    { id: "architecture", label: "Architecture", roleId: "architect", icon: "list-tree" },
    { id: "security", label: "Security", roleId: "security", icon: "shield-check" },
  ] },
  { id: "cfo", label: "CFO", accent: "#55d59a", leads: [
    { id: "finance", label: "Finance", roleId: "accountant", icon: "list" },
    { id: "analytics", label: "Analytics", roleId: "analyst", icon: "layout-dashboard" },
    { id: "compliance", label: "Compliance", roleId: "auditor", icon: "check" },
  ] },
  { id: "cmo", label: "CMO", accent: "#ff6fae", leads: [
    { id: "design", label: "Design", roleId: "designer", icon: "pencil" },
    { id: "content", label: "Content", roleId: "producer", icon: "file-clock" },
    { id: "growth", label: "Growth", roleId: "marketer", icon: "sparkles" },
  ] },
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

function observedTimestampMs(value) {
  if (value == null || value === "") return 0;
  const numeric = Number(value);
  const parsed = Number.isFinite(numeric) && numeric > 0 ? (numeric < 1e12 ? numeric * 1000 : numeric) : new Date(value).getTime();
  return Number.isFinite(parsed) && parsed >= Date.UTC(2000, 0, 1) ? parsed : 0;
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

function showConnectionState() {
  clearError();
  setDataStatus("unavailable", state.overview?.generated_at);
  setNotificationsOpen(false);
  dismissNotificationToast(false);
  if (state.messageOpen) closeMessageComposer(false);
  $(".app-shell").classList.add("is-disconnected");
  $(".workspace").classList.add("is-disconnected");
  $("#connection-state").hidden = false;
}

function clearConnectionState() {
  $(".app-shell").classList.remove("is-disconnected");
  $(".workspace").classList.remove("is-disconnected");
  $("#connection-state").hidden = true;
}

function onboardingConfigBlocked() {
  return state.onboardingConfigPending.size > 0 || state.onboardingConfigFailures.size > 0;
}

function onboardingConfigDraft(key, fallback) {
  return state.onboardingConfigPending.get(key)?.value ?? state.onboardingConfigFailures.get(key)?.value ?? fallback;
}

function onboardingControlIdentity(element) {
  if (!(element instanceof HTMLElement)) return "";
  const summaryOwner = element.matches("summary") ? element.closest("details[data-onboarding-control]") : null;
  if (summaryOwner) return "summary:" + summaryOwner.dataset.onboardingControl;
  const control = element.matches("[data-config-key],[data-onboarding-control]") ? element : element.closest("[data-config-key],[data-onboarding-control]");
  if (!control) return "";
  if (control.dataset.configKey) return "config:" + control.dataset.configKey;
  return control.dataset.onboardingControl ? "control:" + control.dataset.onboardingControl : "";
}

function onboardingControlForIdentity(root, identity) {
  if (!root || !identity) return null;
  const [kind, ...parts] = identity.split(":");
  const value = parts.join(":");
  if (kind === "summary") return $$('details[data-onboarding-control]', root).find((details) => details.dataset.onboardingControl === value)?.querySelector("summary") || null;
  const attribute = kind === "config" ? "configKey" : "onboardingControl";
  return $$('[data-' + attribute.replace(/[A-Z]/g, (letter) => "-" + letter.toLowerCase()) + ']', root).find((element) => element.dataset[attribute] === value) || null;
}

function onboardingConfigToggle(key, value, label) {
  const editable = configEditable(key) && !state.onboardingConfigPending.has(key);
  const draft = onboardingConfigDraft(key, value);
  return '<label class="toggle-row"><input data-config-key="' + escapeHTML(key) + '" type="checkbox"' + (draft === true ? ' checked' : '') + (editable ? '' : ' disabled') + '><span>' + escapeHTML(label) + '</span></label>' + (editable ? '' : '<small>Managed by the current configuration.</small>');
}

function onboardingConfigModeToggle(key, value, enabledValue, disabledValue, label) {
  const editable = configEditable(key) && !state.onboardingConfigPending.has(key);
  const draft = onboardingConfigDraft(key, value);
  return '<label class="toggle-row"><input data-config-key="' + escapeHTML(key) + '" data-true-value="' + escapeHTML(enabledValue) + '" data-false-value="' + escapeHTML(disabledValue) + '" type="checkbox"' + (draft === enabledValue ? ' checked' : '') + (editable ? '' : ' disabled') + '><span>' + escapeHTML(label) + '</span></label>' + (editable ? '' : '<small>Managed by the current configuration.</small>');
}

function onboardingSpeedControl(value) {
  const key = "execution.fast_mode";
  const editable = configEditable(key) && !state.onboardingConfigPending.has(key);
  const draft = onboardingConfigDraft(key, value) === true;
  const choice = (id, label, selected, configValue, disabled = false) => '<label title="' + escapeHTML(disabled ? label + ' requires server support.' : label + ' mode') + '"><input type="radio" name="onboarding-speed" data-config-key="' + key + '" data-config-value="' + String(configValue) + '" data-onboarding-control="speed-' + id + '"' + (selected ? ' checked' : '') + ((!editable || disabled) ? ' disabled' : '') + '><span>' + escapeHTML(label) + '</span></label>';
  return '<fieldset class="onboarding-segmented"><legend>Speed</legend><div>' + choice("default", "Default", !draft, false) + choice("fast", "Fast", draft, true) + choice("ultrafast", "Ultrafast", false, true, true) + '</div></fieldset><small>Ultrafast is unavailable until the server exposes an accepted mode.</small>';
}

const ONBOARDING_TASK_LIFE_DETENTS = [
  { hours: 1, valueText: "Short — 1 hour" },
  { hours: 2, valueText: "Between Short and Balanced — 2 hours" },
  { hours: 4, valueText: "Balanced — 4 hours" },
  { hours: 24, valueText: "Between Balanced and Long — 24 hours" },
  { hours: 720, valueText: "Long — 30 days" },
];

function onboardingTaskLifeControl(value) {
  const key = "lifecycle.task_lifetime_hours";
  const current = Number.isInteger(value) ? value : 4;
  const draft = onboardingConfigDraft(key, current);
  const exactIndex = ONBOARDING_TASK_LIFE_DETENTS.findIndex((detent) => detent.hours === draft);
  const index = exactIndex >= 0 ? exactIndex : ONBOARDING_TASK_LIFE_DETENTS.reduce((best, detent, position) => Math.abs(detent.hours - draft) < Math.abs(ONBOARDING_TASK_LIFE_DETENTS[best].hours - draft) ? position : best, 0);
  const editable = Number.isInteger(value) && configEditable(key) && !state.onboardingConfigPending.has(key);
  const values = ONBOARDING_TASK_LIFE_DETENTS.map((detent) => detent.hours).join(",");
  const tooltip = "Short clears context sooner to keep work efficient, with more handovers. Balanced hands over when task efficiency begins to drop. Long reduces scheduled handovers, while a larger context can become less efficient over time.";
  return '<section class="onboarding-task-life"><div class="onboarding-task-life-head"><label for="onboarding-task-life">Task life</label><details class="onboarding-task-life-info" data-onboarding-control="task-life-info"><summary class="icon-button" aria-label="About task life"><span aria-hidden="true">i</span></summary><div class="onboarding-task-life-tooltip" role="tooltip">' + escapeHTML(tooltip) + '</div></details></div>' +
    '<input id="onboarding-task-life" data-config-key="' + key + '" data-config-values="' + values + '" type="range" min="0" max="4" step="1" value="' + index + '" aria-valuetext="' + escapeHTML(ONBOARDING_TASK_LIFE_DETENTS[index].valueText) + '"' + (editable ? '' : ' disabled') + '>' +
    '<div class="onboarding-task-life-labels" aria-hidden="true"><span>Short</span><span>Balanced</span><span>Long</span></div>' + (editable ? '' : '<small>Managed by the current configuration.</small>') + '</section>';
}

function onboardingConfigurationMarkup() {
  const settings = state.config?.settings || {};
  const execution = settings.execution || {};
  const automation = settings.automation || {};
  const lifecycle = settings.lifecycle || {};
  const pending = state.onboardingConfigPending.size;
  const failures = [...state.onboardingConfigFailures.values()];
  const status = pending ? 'Saving ' + pending + ' setting' + (pending === 1 ? '' : 's') + '…' : failures.length ? (failures[0].error || 'A setting was not saved.') : 'Changes are saved when acknowledged by SWARM.';
  return '<section class="onboarding-config-essentials"><header><div><p class="eyebrow">Essentials</p><h3>How SWARM runs your work</h3></div><div>' + onboardingConfigModeToggle("automation.mode", automation.mode || "standard", "standard", "manual", "Auto mode") + '<small>SWARM keeps eligible work moving until it needs you.</small></div></header><div class="onboarding-essentials-controls">' +
    onboardingSpeedControl(execution.fast_mode) + onboardingTaskLifeControl(lifecycle.task_lifetime_hours) + '</div></section>' +
    '<button class="onboarding-advanced-link" id="onboarding-advanced-settings" data-onboarding-control="advanced-settings-link" type="button">Advanced settings</button>' +
    '<div class="onboarding-config-save ' + (failures.length ? 'is-error' : '') + '" id="onboarding-config-status" data-onboarding-control="config-status" role="status" tabindex="-1"><span>' + escapeHTML(status) + '</span>' + (failures.length ? '<button class="quiet-button" type="button" data-onboarding-control="retry-config">Retry</button>' : '') + '</div>';
}

function onboardingRoleAvatar(roleId, label) {
  return roleAvatar(roleRecord(roleId) || { id: roleId, name: label });
}

function onboardingCoordinationSignature() {
  const ids = ["manager", ...ONBOARDING_COORDINATION_GROUPS.flatMap((group) => group.leads.map((lead) => lead.roleId))];
  return ids.map((id) => {
    const role = roleRecord(id);
    return [id, role?.version || "", role?.avatar_asset_digest || ""].join(":");
  }).join("|");
}

function onboardingCoordinationMarkup() {
  let entranceIndex = 1;
  const paths = [];
  const connections = [];
  const groups = ONBOARDING_COORDINATION_GROUPS.map((group) => {
    const executiveId = "executive-" + group.id;
    paths.push('<path data-onboarding-edge="ctrl-' + escapeHTML(group.id) + '" data-source="ctrl" data-target="' + escapeHTML(executiveId) + '"></path>');
    connections.push("CTRL to " + group.label);
    const executiveIndex = entranceIndex++;
    const leads = group.leads.map((lead) => {
      const nodeId = group.id + "-" + lead.id;
      const leadIndex = entranceIndex++;
      paths.push('<path data-onboarding-edge="' + escapeHTML(nodeId) + '" data-source="' + escapeHTML(executiveId) + '" data-target="' + escapeHTML(nodeId) + '"></path>');
      connections.push(group.label + " to " + lead.label);
      return '<div class="onboarding-lead-node" role="treeitem" aria-level="3" tabindex="-1" data-onboarding-node="lead" data-onboarding-node-id="' + escapeHTML(nodeId) + '" data-onboarding-lead="' + escapeHTML(lead.id) + '" data-role-id="' + escapeHTML(lead.roleId) + '" style="--org-index:' + leadIndex + '">' +
        onboardingRoleAvatar(lead.roleId, lead.label) +
        '<span class="onboarding-role-icon" aria-hidden="true"><svg class="lucide"><use href="#lucide-' + escapeHTML(lead.icon) + '"></use></svg></span>' +
        '<strong>' + escapeHTML(lead.label) + '</strong></div>';
    }).join("");
    return '<section class="onboarding-executive-branch" role="group" aria-label="' + escapeHTML(group.label + " team") + '" style="--executive-accent:' + escapeHTML(group.accent) + '">' +
      '<div class="onboarding-executive-node" role="treeitem" aria-level="2" tabindex="-1" data-onboarding-node="executive" data-onboarding-node-id="' + escapeHTML(executiveId) + '" data-onboarding-executive="' + escapeHTML(group.id) + '" data-role-id="manager" style="--org-index:' + executiveIndex + '">' +
      onboardingRoleAvatar("manager", "Manager") + '<span><strong>' + escapeHTML(group.label) + '</strong><small>Manager</small></span><i class="onboarding-jack is-input" aria-hidden="true"></i></div>' +
      '<div class="onboarding-lead-group" role="group" aria-label="' + escapeHTML(group.label + " profession leads") + '">' + leads + '</div></section>';
  }).join("");
  return '<div class="onboarding-flow-toolbar" aria-label="Flowchart zoom"><button class="icon-button" type="button" data-onboarding-flow-zoom="out" aria-label="Zoom out">−</button><button class="quiet-button" type="button" data-onboarding-flow-zoom="fit">Fit</button><button class="icon-button" type="button" data-onboarding-flow-zoom="in" aria-label="Zoom in">+</button></div>' +
    '<div class="onboarding-coordination-stage"><svg class="onboarding-coordination-connectors" aria-hidden="true" focusable="false">' + paths.join("") + '</svg>' +
    '<div class="onboarding-coordination-content"><div class="onboarding-ctrl-node" role="treeitem" aria-level="1" tabindex="0" data-onboarding-node="ctrl" data-onboarding-node-id="ctrl" style="--org-index:0"><i class="onboarding-jack is-input" aria-hidden="true"></i><img src="/assets/swarm-mascot-512.png" alt="" aria-hidden="true" width="512" height="512"><span class="onboarding-console-face"><strong>CTRL</strong><i class="onboarding-console-dial" aria-hidden="true"></i><span class="onboarding-console-switches" aria-hidden="true"><i></i><i></i></span></span><span class="onboarding-output-jacks" aria-hidden="true"><i></i><i></i><i></i><i></i></span></div>' +
    '<div class="onboarding-executive-grid" role="group" aria-label="Executive managers and profession leads">' + groups + '</div></div>' +
    '<ul class="sr-only" aria-label="Coordination connections">' + connections.map((connection) => '<li>' + escapeHTML(connection) + '</li>').join("") + '</ul></div>';
}

function renderOnboardingCoordination() {
  const tree = $("#onboarding-coordination-tree");
  if (!tree) return;
  const signature = onboardingCoordinationSignature();
  if (tree.dataset.roleSignature !== signature || !tree.firstElementChild) {
    const focusedId = document.activeElement?.dataset?.onboardingNodeId || "";
    tree.innerHTML = onboardingCoordinationMarkup();
    tree.dataset.roleSignature = signature;
    if (focusedId) $$('[data-onboarding-node-id]', tree).find((item) => item.dataset.onboardingNodeId === focusedId)?.focus({ preventScroll: true });
  }
  tree.style.setProperty("--flow-zoom", String(state.onboardingFlowZoom));
  $('[data-onboarding-flow-zoom="out"]', tree).disabled = state.onboardingFlowZoom <= .9;
  $('[data-onboarding-flow-zoom="in"]', tree).disabled = state.onboardingFlowZoom >= 1.1;
  scheduleProjectViewConnectors();
}

function drawOnboardingCoordinationConnectors() {
  const stage = $(".onboarding-coordination-stage", $("#onboarding-coordination-tree"));
  const svg = stage && $(".onboarding-coordination-connectors", stage);
  if (!stage || !svg) return;
  const stageRect = stage.getBoundingClientRect();
  if (!stageRect.width || !stageRect.height) return;
  svg.setAttribute("viewBox", "0 0 " + stage.clientWidth + " " + stage.clientHeight);
  svg.setAttribute("width", String(stage.clientWidth));
  svg.setAttribute("height", String(stage.clientHeight));
  const nodeById = new Map($$("[data-onboarding-node-id]", stage).map((node) => [node.dataset.onboardingNodeId, node]));
  $$('[data-onboarding-edge]', svg).forEach((path) => {
    const source = nodeById.get(path.dataset.source);
    const target = nodeById.get(path.dataset.target);
    if (!source || !target) { path.removeAttribute("d"); return; }
    const from = source.getBoundingClientRect();
    const to = target.getBoundingClientRect();
    const x1 = from.left + from.width / 2 - stageRect.left;
    const y1 = from.bottom - stageRect.top;
    const x2 = to.left + to.width / 2 - stageRect.left;
    const y2 = to.top - stageRect.top;
    const bend = Math.max(12, (y2 - y1) / 2);
    path.setAttribute("d", "M " + x1 + " " + y1 + " C " + x1 + " " + (y1 + bend) + ", " + x2 + " " + (y2 - bend) + ", " + x2 + " " + y2);
  });
}

function moveOnboardingTreeFocus(event) {
  if (!["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp", "Home", "End"].includes(event.key)) return;
  const items = $$("[data-onboarding-node-id]", event.currentTarget);
  const current = items.indexOf(document.activeElement);
  if (current < 0) return;
  const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (current + (["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1) + items.length) % items.length;
  event.preventDefault();
  items.forEach((item, index) => { item.tabIndex = index === next ? 0 : -1; });
  items[next].focus({ preventScroll: false });
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
  const finalStep = step === ONBOARDING_STEPS.length - 1;
  const blocked = finalStep && onboardingConfigBlocked();
  const laterStep = step > 0;
  $("#onboarding-body-nav").hidden = !laterStep;
  $("#onboarding-back").disabled = blocked;
  $("#onboarding-close").disabled = blocked;
  $("#onboarding-skip").hidden = laterStep;
  $("#onboarding-skip").disabled = blocked;
  $$('[data-onboarding-step]').forEach((dot) => { dot.disabled = blocked; });
  $("#onboarding-primary").textContent = current.primary;
  $("#onboarding-primary").disabled = blocked;
  $("#onboarding-primary").toggleAttribute("aria-busy", finalStep && state.onboardingConfigPending.size > 0);
  if (step === 1) renderOnboardingCoordination();
  if (finalStep) {
    const root = $("#onboarding-configuration");
    const focusIdentity = onboardingControlIdentity(document.activeElement);
    const scrollOwner = root.closest(".dialog-body");
    const scrollTop = scrollOwner?.scrollTop || 0;
    const openControls = new Set($$("details[open][data-onboarding-control]", root).map((details) => details.dataset.onboardingControl));
    root.innerHTML = onboardingConfigurationMarkup();
    $$("details[data-onboarding-control]", root).forEach((details) => { details.open = openControls.has(details.dataset.onboardingControl); });
    if (scrollOwner) scrollOwner.scrollTop = scrollTop;
    const restored = onboardingControlForIdentity(root, focusIdentity);
    const focusTarget = restored && !restored.disabled
      ? restored
      : (focusIdentity ? $("#onboarding-config-status", root) : null);
    if (focusTarget) requestAnimationFrame(() => focusTarget.focus({ preventScroll: true }));
    const advancedSettings = $("#onboarding-advanced-settings", root);
    if (advancedSettings) advancedSettings.disabled = blocked;
  }
  updateOnboardingEntrance(step);
}

function updateOnboardingEntrance(step) {
  const dialog = $("#onboarding-dialog");
  const motionStep = String(step);
  if (!dialog || dialog.dataset.motionStep === motionStep) return;
  dialog.dataset.motionStep = motionStep;
  dialog.classList.remove("is-step-entering");
  void dialog.offsetWidth;
  dialog.classList.add("is-step-entering");
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
  $(".dialog-body", dialog).scrollTop = 0;
  if (!dialog.open) dialog.showModal();
  requestAnimationFrame(() => $("#onboarding-primary").focus({ preventScroll: true }));
}

function closeOnboarding(openProjects = false) {
  if (state.onboardingStep === ONBOARDING_STEPS.length - 1 && onboardingConfigBlocked()) return false;
  markOnboardingSeen();
  const dialog = $("#onboarding-dialog");
  if (dialog.open) dialog.close();
  if (openProjects) setView("overview", false);
  return true;
}

function onboardingCanDismiss() {
  return state.onboardingStep !== ONBOARDING_STEPS.length - 1 || !onboardingConfigBlocked();
}

function openAdvancedSettingsFromOnboarding() {
  if (!onboardingCanDismiss()) return false;
  state.onboardingTrigger = null;
  if (!closeOnboarding()) return false;
  setView('settings', false, false);
  writeRoute('push', 'settings-advanced');
  renderSettings();
  requestAnimationFrame(() => {
    const entry = $('#settings-advanced');
    if (!entry) return;
    entry.scrollIntoView({ block: 'start' });
    $('#settings-edit-config')?.focus({ preventScroll: true });
  });
  return true;
}

function setOnboardingStep(step, focusDot = false, focusNavigation = "") {
  const nextStep = Math.min(Math.max(0, Number(step) || 0), ONBOARDING_STEPS.length - 1);
  const changed = nextStep !== state.onboardingStep;
  state.onboardingStep = nextStep;
  renderOnboarding();
  if (changed) $(".dialog-body", $("#onboarding-dialog")).scrollTop = 0;
  if (focusDot) $('[data-onboarding-step="' + state.onboardingStep + '"]')?.focus({ preventScroll: true });
  else if (focusNavigation) requestAnimationFrame(() => (focusNavigation === "back" && state.onboardingStep > 0 ? $("#onboarding-back") : $("#onboarding-primary")).focus({ preventScroll: true }));
}

async function saveConfigMutation(changes) {
  configAuthorityGeneration += 1;
  const operation = configMutationTail.then(async () => {
    const config = await api('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ changes }) });
    state.config = config;
    state.configStatus = "current";
    return config;
  });
  configMutationTail = operation.then(() => undefined, () => undefined);
  return operation;
}

function configResetOperationId(kind) {
  const values = new Uint32Array(4);
  window.crypto.getRandomValues(values);
  return "console-config-reset-" + kind + "-" + [...values].map((value) => value.toString(16).padStart(8, "0")).join("");
}

function configResetRequest(kind) {
  if (kind === "ctrl") {
    const setting = state.ctrlSettings;
    if (!setting?.ctrl_id || !Number.isInteger(setting.revision)) return null;
    return {
      kind,
      endpoint: "/api/ctrl-settings/reset",
      binding: { type: "ctrl", id: String(setting.ctrl_id) },
      payload: { ctrl_id: String(setting.ctrl_id), expected_revision: setting.revision, acknowledge: true },
    };
  }
  const projection = state.config;
  const scope = projection?.scope;
  if (!projection || projection.state !== "KNOWN" || projection.write_contract?.available !== true || projection.revision == null) return null;
  if (kind === "global" && scope?.type === "global") {
    return { kind, endpoint: "/api/settings/restore", binding: { type: "global", id: "global" }, payload: { scope: { type: "global" }, expected_revision: projection.revision, acknowledge: true } };
  }
  if (kind === "project" && scope?.type === "project" && scope.project_id && scope.accepted_cursor) {
    return {
      kind,
      endpoint: "/api/config/reset",
      binding: { type: "project", id: String(scope.project_id) },
      payload: { scope: { type: "project", project_id: String(scope.project_id), accepted_cursor: structuredClone(scope.accepted_cursor) }, expected_revision: projection.revision, acknowledge: true },
    };
  }
  return null;
}

function configResetRequestKey(request) {
  return request ? request.endpoint + "|" + JSON.stringify(request.payload) : "";
}

function configResetBindingIsCurrent(request) {
  const scope = currentSettingsScope();
  return Boolean(request) && scope.type === request.binding.type && String(scope.id) === request.binding.id;
}

async function resetSettingsScope(kind) {
  const base = configResetRequest(kind);
  if (!base || state.configResetPending) throw new Error("This settings scope cannot be reset from the current accepted projection.");
  const key = configResetRequestKey(base);
  const retainedRetry = state.configResetRetry?.key === key ? state.configResetRetry : null;
  const operationId = retainedRetry?.operationId || configResetOperationId(kind);
  const request = { ...base, key, operationId, payload: { ...base.payload, operation_id: operationId } };
  state.configResetPending = request;
  configAuthorityGeneration += 1;
  const operation = configMutationTail.then(() => api(request.endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request.payload) }));
  configMutationTail = operation.then(() => undefined, () => undefined);
  try {
    const result = await operation;
    state.configResetRetry = null;
    if (!configResetBindingIsCurrent(request)) return { applied: false, result };
    if (kind === "ctrl") state.ctrlSettings = result;
    else {
      state.config = result;
      state.configStatus = "current";
      state.settingsDraft.clear();
    }
    return { applied: true, result };
  } catch (error) {
    state.configResetRetry = error?.connectionFailure === true || !Number.isInteger(error?.status) ? { key, operationId } : null;
    throw error;
  } finally {
    if (state.configResetPending?.operationId === operationId) state.configResetPending = null;
  }
}

async function readConfigState(previousConfig = state.config, saveError = "") {
  let pendingWrites = configMutationTail;
  await pendingWrites;
  while (pendingWrites !== configMutationTail) {
    pendingWrites = configMutationTail;
    await pendingWrites;
  }
  const generation = configAuthorityGeneration;
  try {
    const config = await api('/api/config');
    if (generation !== configAuthorityGeneration) {
      if (saveError) state.configError = saveError + " Current settings changed before the reload completed.";
      return false;
    }
    if (saveError) Object.assign(state, chatRelayFailureState(previousConfig, config, saveError));
    else {
      state.config = config;
      state.configStatus = "current";
      state.configError = "";
    }
    return true;
  } catch (error) {
    if (generation !== configAuthorityGeneration) {
      if (saveError) state.configError = saveError + " Current settings changed before the reload completed.";
      return false;
    }
    if (saveError) Object.assign(state, chatRelayFailureState(previousConfig, null, saveError));
    else {
      state.config = previousConfig;
      state.configStatus = previousConfig ? "stale" : "unavailable";
      state.configError = error.message || "Settings could not be loaded.";
    }
    throw error;
  }
}

async function saveOnboardingConfig(key, value) {
  if (!configEditable(key) || state.onboardingConfigPending.has(key)) return false;
  const focusIdentity = onboardingControlIdentity(document.activeElement);
  state.onboardingConfigFailures.delete(key);
  state.onboardingConfigPending.set(key, { value, focusIdentity });
  renderAllViews();
  try {
    await saveConfigMutation({ [key]: value });
    if (key === 'console.project_progress_feed_enabled' || key === 'console.project_progress_feed_lines') await refreshProjectProgressFeed();
    return true;
  } catch (error) {
    state.onboardingConfigFailures.set(key, { value, error: error.message || "This setting could not be saved." });
    return false;
  } finally {
    state.onboardingConfigPending.delete(key);
    renderAllViews();
    const root = $("#onboarding-configuration");
    const target = onboardingControlForIdentity(root, focusIdentity)
      || (focusIdentity === "control:retry-config" ? $("#onboarding-config-status", root) : null);
    requestAnimationFrame(() => target?.focus({ preventScroll: true }));
  }
}

async function retryOnboardingConfig() {
  const failures = [...state.onboardingConfigFailures.entries()];
  for (const [key, failure] of failures) await saveOnboardingConfig(key, failure.value);
  const target = state.onboardingConfigFailures.size
    ? $('[data-onboarding-control="retry-config"]', $("#onboarding-configuration"))
    : $("#onboarding-config-status", $("#onboarding-configuration"));
  requestAnimationFrame(() => target?.focus({ preventScroll: true }));
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
  renderDiagnosticsSummary(presentation);
}

function openSystemHealth() {
  setView("diagnostics");
  requestAnimationFrame(() => $("#diagnostics-heading")?.focus({ preventScroll: true }));
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

const TOP_LEVEL_VIEWS = ["overview", "agents", "roles", "review", "assets", "diagnostics", "settings"];

function routeView() {
  const view = location.hash.slice(1);
  if (view === "settings-advanced") return "settings";
  return TOP_LEVEL_VIEWS.includes(view) ? view : "overview";
}

function routeProjectId() {
  const projectId = new URL(location.href).searchParams.get("project");
  return projectId && projectId.trim() ? projectId.trim() : "all";
}

function routeURL(view = state.view, projectId = state.projectId, hashOverride = "") {
  const url = new URL(location.href);
  if (projectId && projectId !== "all") url.searchParams.set("project", projectId);
  else url.searchParams.delete("project");
  url.hash = "#" + (hashOverride || view);
  return url.pathname + url.search + url.hash;
}

function writeRoute(mode = "replace", hashOverride = "") {
  const method = mode === "push" ? "pushState" : "replaceState";
  const next = routeURL(state.view, state.projectId, hashOverride);
  const current = location.pathname + location.search + location.hash;
  if (next !== current) history[method]({ view: state.view, projectId: state.projectId }, "", next);
  lastAppliedHistoryRoute = next;
}

function setView(view, focus = false, syncRoute = true, historyMode = "push") {
  const selectedView = TOP_LEVEL_VIEWS.includes(view) ? view : "overview";
  state.view = selectedView;
  const titles = {
    overview: ["Overview", "Portfolio progress and project scope."],
    agents: ["Agents", "Active ownership and current work."],
    roles: ["Roles", "Profession manifests and role defaults."],
    review: ["Review", "Proof, decisions, and handoff acknowledgements."],
    assets: ["Assets", "Approved project and role assets."],
    diagnostics: ["Diagnostics", "Live local health checks and recovery preparation."],
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
  if (selectedView === 'diagnostics' && state.token && state.diagnosticsHistoryStatus === "idle") refreshDiagnostics().then(renderDiagnostics);
  if (syncRoute) writeRoute(historyMode);
  renderMessageComposer();
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

const PROJECT_NAVIGATION_STATUS_RANK = { active: 0, recent: 1, stalled: 1, inactive: 2, unknown: 3 };

function projectStatusLabel(status) {
  return { active: "Active", recent: "Recently active", stalled: "Needs attention", inactive: "Inactive", unknown: "Status unknown" }[status] || "Status unknown";
}

function admittedProjectLogo(project) {
  const logo = project?.logo || project?.identity?.logo;
  const artifact = logo?.artifact;
  const url = typeof artifact?.url === "string" ? artifact.url : "";
  const digest = String(artifact?.digest || "").replace(/^sha256:/i, "");
  const safePath = /^\/(?!\/)(?!.*(?:^|\/)\.\.(?:\/|$))[a-z0-9._~!$&'()*+,;=:@%/-]+$/i.test(url);
  return logo?.status === "ADMITTED"
    && /^image\/(?:png|webp|jpeg|svg\+xml)$/i.test(String(artifact?.media_type || ""))
    && /^[a-f0-9]{64}$/i.test(digest)
    && safePath
    ? { url, alt: String(artifact?.alt || "") }
    : null;
}

function projectScopeMark(project) {
  const logo = admittedProjectLogo(project);
  return logo
    ? '<img class="project-scope-logo" src="' + escapeHTML(logo.url) + '" alt="" loading="lazy" decoding="async">'
    : '<span class="scope-dot is-' + escapeHTML(project?.status || "unknown") + '"></span>';
}

function savedProjectRoster() {
  const navigation = state.overview?.navigation;
  const inventory = navigation?.project_inventory;
  if (inventory?.state !== "KNOWN" || inventory.available !== true || !Array.isArray(navigation?.projects)) return { state: "UNKNOWN", projects: [] };
  const projects = navigation.projects.map((project) => {
    const activityStatus = String(project?.activity_status || "").toLowerCase();
    const activityFacts = project?.activity_facts;
    const legacyStatus = String(project?.status || "").toLowerCase();
    const legacyFacts = project?.status_facts;
    const ctrlIds = project?.ctrl_ids;
    const activityKey = activityStatus === "recently_active" ? "recently_active" : activityStatus === "active" ? "active_now" : activityStatus;
    const validActivity = ["active", "recently_active", "inactive", "unknown"].includes(activityStatus)
      && activityFacts && activityFacts[activityKey] === true
      && ["active_now", "recently_active", "inactive", "unknown"].filter((name) => activityFacts[name] === true).length === 1;
    const validLegacy = ["active", "stalled", "inactive"].includes(legacyStatus)
      && legacyFacts && legacyFacts[legacyStatus] === true
      && ["active", "stalled", "inactive"].filter((name) => legacyFacts[name] === true).length === 1;
    const status = validActivity ? (activityStatus === "recently_active" ? "recent" : activityStatus) : legacyStatus;
    const validStatus = validActivity || validLegacy;
    if (!project || typeof project.id !== "string" || !project.id || project.archived !== false || project.visibility !== "visible" || !Array.isArray(ctrlIds) || !validStatus) return null;
    return {
      id: project.id,
      label: publicLabel(project.goal_label || project.name || project.id, "Untitled project"),
      status,
      lastActivityAt: Number.isInteger(project.last_activity_at) && project.last_activity_at >= 0 ? project.last_activity_at : null,
      ctrlIds: [...ctrlIds],
      activeCtrlId: typeof project.active_ctrl_id === "string" ? project.active_ctrl_id : "",
      taskCount: Number.isInteger(project.task_count) && project.task_count >= 0 ? project.task_count : null,
      eligibility: project.project_eligibility === "swarm_ctrl" ? "swarm_ctrl" : "no_ctrl",
      logo: project.logo || project.identity?.logo || null,
    };
  });
  if (projects.some((project) => !project)) return { state: "UNKNOWN", projects: [] };
  return {
    state: "KNOWN",
    projects: projects.sort((a, b) => PROJECT_NAVIGATION_STATUS_RANK[a.status] - PROJECT_NAVIGATION_STATUS_RANK[b.status]
      || (b.lastActivityAt ?? -1) - (a.lastActivityAt ?? -1)
      || a.label.localeCompare(b.label)
      || a.id.localeCompare(b.id)),
  };
}

function scopeLabel() {
  if (state.projectId === "all") return "All projects";
  const project = savedProjectRoster().projects.find((item) => item.id === state.projectId);
  const ctrl = historicalControllers().find((item) => item.id === state.ctrlId);
  return ctrl && state.ctrlId ? ctrlLabel(ctrl) : (project?.label || "All projects");
}

function setProjectSelection(projectId, ctrlId = "") {
  const nextProjectId = String(projectId || "all");
  const nextCtrlId = String(ctrlId || "");
  const changed = state.projectId !== nextProjectId || state.ctrlId !== nextCtrlId;
  if (changed) {
    state.projectUiGroupId = "";
    const selectedAgent = state.runLogAgent;
    if (selectedAgent && nextProjectId !== "all" && selectedAgent.projectId !== nextProjectId) {
      state.runLogAgent = null;
      if (state.agentUpdatesFilter === "selected") state.agentUpdatesFilter = "all";
      if ($("#agent-detail-dialog")?.open) closeAgentDetail(false);
    }
  }
  state.projectId = nextProjectId;
  state.ctrlId = nextCtrlId;
}

function renderScopeNotice() {
  const notice = $("#scope-change-status");
  if (!notice) return;
  notice.textContent = state.scopeNotice;
  notice.classList.toggle("sr-only", !state.scopeNoticeVisible);
  notice.hidden = !state.scopeNotice;
}

function renderProjectNavigation() {
  const roster = savedProjectRoster();
  const projects = roster.projects;
  const selector = $("#project-scope-filter");
  if (roster.state !== "KNOWN") {
    $("#project-navigation").innerHTML = '<p class="project-roster-state" role="status">Saved projects unavailable</p>';
    if (selector) {
      selector.setAttribute("aria-disabled", "true");
      selector.setAttribute("aria-label", "Project scope unavailable");
      $("#project-scope-selector").open = false;
      $("#project-scope-selected-mark").innerHTML = '<span class="scope-dot is-unknown"></span>';
      $("#project-scope-selected-label").textContent = "Projects unavailable";
      $("#project-scope-options").innerHTML = '<p class="project-roster-state" role="status">Saved projects unavailable</p>';
    }
    return;
  }
  if (state.projectId !== "all" && !projects.some((project) => project.id === state.projectId)) {
    const unavailableId = state.projectId;
    setProjectSelection("all");
    state.scopeNotice = "Project " + unavailableId + " is unavailable. Showing All projects.";
    state.scopeNoticeVisible = true;
    writeRoute("replace");
  }
  const entries = [];
  projects.forEach((project) => {
    const current = state.projectId === project.id && !state.ctrlId;
    const statusLabel = projectStatusLabel(project.status);
    entries.push('<button class="project-scope-button ' + (current ? "is-selected" : "") + '" data-project-id="' + escapeHTML(project.id) + '" type="button" aria-label="' + escapeHTML(project.label + ", " + statusLabel) + '" aria-pressed="' + current + '"><span class="scope-dot is-' + project.status + '" aria-hidden="true"></span><span class="project-scope-label" title="' + escapeHTML(project.label) + '">' + escapeHTML(project.label) + '</span></button>');
  });
  $("#project-navigation").innerHTML = entries.length ? entries.join("") : '<p class="project-roster-state" role="status">No saved projects</p>';
  if (selector) {
    const selectedProject = projects.find((project) => project.id === state.projectId);
    const selectedStatus = selectedProject?.status || "unknown";
    selector.removeAttribute("aria-disabled");
    selector.setAttribute("aria-label", "Project scope");
    $("#project-scope-selected-mark").innerHTML = projectScopeMark(selectedProject || { status: selectedStatus });
    $("#project-scope-selected-label").textContent = selectedProject?.label || "All projects";
    $("#project-scope-options").innerHTML = '<button class="polished-select-option' + (state.projectId === "all" ? ' is-selected' : '') + '" type="button" role="option" data-project-scope-id="all" aria-selected="' + String(state.projectId === "all") + '"><span class="project-scope-mark" aria-hidden="true"><span class="scope-dot is-unknown"></span></span><span>All projects</span><small>Portfolio</small></button>' + projects.map((project) => '<button class="polished-select-option' + (state.projectId === project.id ? ' is-selected' : '') + '" type="button" role="option" data-project-scope-id="' + escapeHTML(project.id) + '" aria-selected="' + String(state.projectId === project.id) + '" aria-label="' + escapeHTML(project.label + ", " + projectStatusLabel(project.status)) + '"><span class="project-scope-mark" aria-hidden="true">' + projectScopeMark(project) + '</span><span>' + escapeHTML(project.label) + '</span><small>' + escapeHTML(projectStatusLabel(project.status)) + '</small></button>').join("");
  }
  renderScopeNotice();
}

async function selectProjectScope(projectId, trigger = null, historyMode = "push") {
  const roster = savedProjectRoster();
  const selectedId = String(projectId || "all");
  if (selectedId !== "all" && (roster.state !== "KNOWN" || !roster.projects.some((project) => project.id === selectedId))) {
    state.scopeNotice = "That project is unavailable. The current project scope was not changed.";
    state.scopeNoticeVisible = true;
    renderScopeNotice();
    return false;
  }
  setProjectSelection(selectedId);
  state.settingsCtrlId = "";
  state.settingsScopeType = selectedId === "all" ? "global" : "project";
  state.settingsScopeId = selectedId === "all" ? "global" : selectedId;
  state.scopeNotice = (selectedId === "all" ? "All projects" : scopeLabel()) + " selected. " + (state.view === "overview" ? "Overview" : $("#view-title")?.textContent || "Current page") + " refreshed.";
  state.scopeNoticeVisible = false;
  writeRoute(historyMode);
  renderProjectNavigation();
  if (mobileDrawerQuery.matches) setMobileDrawer(false, true);
  renderAllViews();
  await refreshOverview(false);
  requestAnimationFrame(() => {
    if (trigger?.id === "project-scope-filter") $("#project-scope-filter")?.focus({ preventScroll: true });
    else if (trigger) $('[data-project-id="' + CSS.escape(state.projectId) + '"]')?.focus({ preventScroll: true });
  });
  return true;
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
  const record = activeAgentRecords().find((item) => item.binding?.projectId === selection.projectId && item.binding?.ctrlId === selection.ctrlId && item.binding?.agentId === selection.agentId);
  return record ? { ...selection, ...record.binding, label: record.presentationName } : null;
}

function agentRunLogPlan() {
  if (state.view !== "agents") return null;
  if (state.agentUpdatesFilter === "selected") {
    const selected = currentRunLogAgent();
    return { title: "Live updates", bindings: selected ? [selected] : [], bindingUnavailable: !selected, filter: "selected" };
  }
  const bindings = new Map();
  activeAgentRecords().forEach((record) => {
    if (!record.binding) return;
    const binding = { projectId: record.binding.projectId, ctrlId: record.binding.ctrlId, agentId: "" };
    bindings.set(runLogBindingKey(binding), binding);
  });
  return { title: "Live updates", bindings: [...bindings.values()], bindingUnavailable: !bindings.size, filter: state.agentUpdatesFilter };
}

function runLogSurfacePlans() {
  const plans = new Map();
  const overviewBinding = state.ctrlId ? runLogBindingForCtrl(state.ctrlId) : null;
  if (overviewBinding) plans.set("overview", { title: "Current CTRL", bindings: [overviewBinding] });
  const projectId = selectedProgressProjectId();
  const projectBindings = projectId && state.projectTab === "logs" ? runLogBindingsForProject(projectId) : [];
  if (projectId && state.projectTab === "logs") plans.set("project", { title: projectBindings.length <= 1 ? "Project run log" : "Project run log · " + projectBindings.length + " CTRLs", bindings: projectBindings, bindingUnavailable: !projectBindings.length });
  const agentPlan = agentRunLogPlan();
  if (agentPlan) plans.set("agent", agentPlan);
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
  const items = [...byIdentity.values()]
    .sort((left, right) => Number(left.event_seq) - Number(right.event_seq) || runLogItemIdentity(left).localeCompare(runLogItemIdentity(right)))
    .slice(-RUN_LOG_CLIENT_LIMIT);
  if (plan.filter !== "material") return items;
  const materialKinds = new Set([
    "BLOCK_CREATED", "SCOPE_REVISED", "PROOF_ADMITTED", "PROOF_INVALIDATED",
    "REWORK_REQUESTED", "USER_STEERING_ACCEPTED", "LIVENESS_STALE", "LIVENESS_RECOVERED",
    "RETRY_STARTED", "TAKEOVER_STARTED", "ACCEPTED",
  ]);
  return items.filter((item) => materialKinds.has(String(item.kind || item.event_kind || "").toUpperCase()));
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

function runLogEntryMarkup(item, surface = "") {
  const observed = Number(item.observed_at_ms);
  const datetime = Number.isFinite(observed) && observed > 0 ? new Date(observed).toISOString() : "";
  if (surface === "agent") {
    const record = activeAgentRecords().find((candidate) => candidate.node.id === item.task_id || candidate.binding?.agentId === item.agent_id);
    const agent = record?.presentationName || "Agent";
    const kind = humanize(item.kind || item.status || "Material update");
    return '<li class="agent-live-entry" data-run-log-entry="' + escapeHTML(runLogItemIdentity(item)) + '"><span class="agent-live-dot" aria-hidden="true"></span><div><p><strong>' + escapeHTML(agent) + '</strong><time datetime="' + escapeHTML(datetime) + '">' + escapeHTML(formatRelative(observed)) + '</time></p><span>' + escapeHTML(item.summary) + '</span><small>' + escapeHTML(kind) + '</small></div></li>';
  }
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
    if (surface === "agent" && state.agentUpdatesPaused) {
      status.textContent = "Paused · received updates remain available when resumed.";
      status.classList.remove("is-stale");
      if (!sameBinding) list.innerHTML = '<li class="empty-state">Live updates paused for this scope.</li>';
      return;
    }
    status.textContent = presentation.message;
    status.classList.toggle("is-stale", presentation.stale);
    list.innerHTML = presentation.items.length ? presentation.items.map((item) => runLogEntryMarkup(item, surface)).join("") : '<li class="empty-state">' + escapeHTML(presentation.message) + '</li>';
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
  if (!svg) return;
  if (!values.length) {
    svg.replaceChildren();
    return;
  }
  const box = svg.viewBox?.baseVal;
  const width = box?.width || 320;
  const height = box?.height || 138;
  const bottom = height - 10;
  const middle = Math.round(height / 2);
  const top = Math.min(28, Math.max(8, Math.round(height * .2)));
  const series = values;
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
  $("#evidence-lightbox-caption").textContent = String(state.evidenceIndex + 1) + " of " + String(items.length)
    + (item.project_requirement_summary ? " · " + item.project_requirement_summary : "");
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

function usageHistorySeries() {
  if (state.usageScopeKey !== usageRequestKey() || state.usageHistory?.ok !== true) return [];
  return (Array.isArray(state.usageHistory.history) ? state.usageHistory.history : [])
    .map((sample) => ({ bucket: Number(sample?.bucket_ms), tokens: Number(sample?.delta_tokens) }))
    .filter((sample) => Number.isFinite(sample.bucket) && sample.bucket >= 0 && Number.isFinite(sample.tokens) && sample.tokens >= 0)
    .sort((a, b) => a.bucket - b.bucket)
    .map((sample) => sample.tokens);
}

function usageRangeLabel(hours = state.usageWindowHours) {
  return hours === 1 ? "last hour" : hours === 24 ? "last 24 hours" : "last 7 days";
}

function usageChartMarkup(surface, svgId) {
  return '<div class="usage-chart" data-usage-chart="' + surface + '"><div class="usage-range" role="group" aria-label="Usage range"><button type="button" data-usage-range="1" aria-pressed="' + String(state.usageWindowHours === 1) + '">1h</button><button type="button" data-usage-range="24" aria-pressed="' + String(state.usageWindowHours === 24) + '">24h</button><button type="button" data-usage-range="168" aria-pressed="' + String(state.usageWindowHours === 168) + '">7d</button></div><svg id="' + svgId + '" viewBox="0 0 160 28" preserveAspectRatio="none" aria-label="Usage history unavailable"></svg></div>';
}

function renderUsageCharts() {
  const values = usageHistorySeries();
  const current = state.usageStatus === "current";
  const label = values.length && current
    ? "Usage during the " + usageRangeLabel() + " from " + values.length + " timestamped sample" + (values.length === 1 ? "" : "s")
    : state.usageStatus === "stale" ? "Usage history stale" : "Usage history unavailable";
  $$('[data-usage-range]').forEach((button) => button.setAttribute("aria-pressed", String(Number(button.dataset.usageRange) === state.usageWindowHours)));
  [$("#metric-usage-trend"), $("#diagnostics-usage-trend")].filter(Boolean).forEach((svg) => {
    drawLine(svg, current ? values : [], "#ff6a3d");
    svg.setAttribute("aria-label", label);
  });
}

function diagnosticChecks() {
  return Array.isArray(state.diagnostics?.health?.checks) ? state.diagnostics.health.checks : [];
}

function diagnosticStatusClass(status) {
  const value = String(status || "UNKNOWN").toUpperCase();
  return value === "PASS" ? "is-pass" : value === "WARN" ? "is-warn" : value === "FAIL" ? "is-fail" : "is-unknown";
}

function diagnosticCheckFor(...needles) {
  return diagnosticChecks().find((check) => needles.some((needle) => String(check?.id || "").toLowerCase().includes(needle))) || null;
}

function diagnosticSummaryItems() {
  return [
    ["Endpoint", diagnosticCheckFor("endpoint_response", "api.health")],
    ["Package", diagnosticCheckFor("package", "source_mirror")],
    ["Project roots", diagnosticCheckFor("project.root", "root_binding", "canonical_project")],
    ["CTRL", diagnosticCheckFor("ctrl", "controller")],
    ["Ledger", diagnosticCheckFor("ledger", "event_cursor")],
    ["Assets", diagnosticCheckFor("asset", "evidence_store", "proof_store")],
    ["Config", diagnosticCheckFor("config")],
    ["Refresh", diagnosticCheckFor("refresh.last_success")],
  ];
}

function diagnosticHistorySeries() {
  const cutoff = Date.now() - DIAGNOSTICS_HISTORY_HOURS * 60 * 60 * 1000;
  const score = { PASS: 100, HEALTHY: 100, OK: 100, WARN: 68, DEGRADED: 68, UNKNOWN: 38, FAIL: 12, CRITICAL: 12 };
  return (Array.isArray(state.diagnosticsHistory?.items) ? state.diagnosticsHistory.items : [])
    .filter((item) => Number(item?.sampled_at_ms) >= cutoff)
    .sort((left, right) => Number(left.sampled_at_ms) - Number(right.sampled_at_ms))
    .map((item) => score[String(item?.health_state || item?.payload?.health_state || "UNKNOWN").toUpperCase()] ?? score.UNKNOWN);
}

function renderDiagnosticsSummary(presentation = systemHealthPresentation()) {
  const root = $("#diagnostics-summary-grid");
  if (!root) return;
  const observed = state.diagnostics?.health?.observed_at_ms;
  root.innerHTML = diagnosticSummaryItems().map(([label, check]) => {
    const status = String(check?.status || "UNKNOWN").toUpperCase();
    const note = check?.summary || check?.reason || "No deterministic receipt is available.";
    return '<article class="panel diagnostics-summary-card ' + diagnosticStatusClass(status) + '"><header><span>' + escapeHTML(label) + '</span><strong>' + escapeHTML(status) + '</strong></header><p>' + escapeHTML(note) + '</p></article>';
  }).join("");
  root.setAttribute("aria-label", presentation.label + " · " + (observed ? "checked " + formatRelative(observed) : "check time unavailable"));
}

function renderDiagnostics() {
  if (!$("#view-diagnostics")) return;
  const presentation = systemHealthPresentation();
  renderDiagnosticsSummary(presentation);
  const checks = diagnosticChecks();
  const validIds = new Set(checks.map((check) => String(check.id)));
  state.diagnosticsSelectedChecks = new Set([...state.diagnosticsSelectedChecks].filter((id) => validIds.has(id)));
  if (!state.diagnosticsSelectionInitialized && checks.length) {
    state.diagnosticsSelectedChecks = new Set(checks.filter((check) => String(check.status).toUpperCase() !== "PASS").map((check) => String(check.id)));
    state.diagnosticsSelectionInitialized = true;
  }
  const list = $("#diagnostics-check-list");
  list.innerHTML = checks.length ? checks.map((check) => {
    const id = String(check.id || "");
    const status = String(check.status || "UNKNOWN").toUpperCase();
    const selected = state.diagnosticsSelectedChecks.has(id);
    const disabled = status === "PASS";
    return '<label class="diagnostics-check ' + diagnosticStatusClass(status) + '"><input type="checkbox" data-diagnostic-check="' + escapeHTML(id) + '"' + (selected ? ' checked' : '') + (disabled ? ' disabled' : '') + '><span class="diagnostics-check-state">' + escapeHTML(status) + '</span><span><strong>' + escapeHTML(humanize(id)) + '</strong><small>' + escapeHTML(check.summary || "No check summary available.") + '</small></span></label>';
  }).join("") : '<p class="empty-state">Deterministic health checks are unavailable. Refresh to try again.</p>';
  const selected = state.diagnosticsSelectedChecks.size;
  $("#diagnostics-selection-status").textContent = selected ? selected + " recommended check" + (selected === 1 ? "" : "s") + " selected." : "No repair checks selected.";
  $("#diagnostics-repair").disabled = !selected || state.diagnosticsRepairPending;
  $("#diagnostics-select-recommended").disabled = !checks.some((check) => String(check.status).toUpperCase() !== "PASS");
  const signals = checks.filter((check) => String(check.status).toUpperCase() !== "PASS");
  $("#diagnostics-log-list").innerHTML = signals.length ? signals.slice(0, 8).map((check) => '<li><span class="diagnostics-signal ' + diagnosticStatusClass(check.status) + '">' + escapeHTML(String(check.status || "UNKNOWN").toUpperCase()) + '</span><div><strong>' + escapeHTML(humanize(check.id)) + '</strong><p>' + escapeHTML(check.recommended_action || check.summary || "Review this local signal.") + '</p></div></li>').join("") : '<li class="is-clear"><strong>No current errors</strong><p>All available deterministic checks pass.</p></li>';
  const autoPolicy = state.diagnostics?.health?.repair_policy || state.health?.auto_repair || {};
  $("#diagnostics-auto-fix-state").textContent = autoPolicy.status || (autoPolicy.enabled === true ? "ON" : autoPolicy.enabled === false ? "OFF" : "UNKNOWN");
  $("#diagnostics-auto-fix-note").textContent = autoPolicy.reason || "Health checks remain active even when Auto fix is off.";
  const healthValues = diagnosticHistorySeries();
  const healthSvg = $("#diagnostics-health-trend");
  drawLine(healthSvg, healthValues, "#ff6a3d");
  healthSvg.setAttribute("aria-label", healthValues.length ? "Health during the last hour from " + healthValues.length + " deterministic sample" + (healthValues.length === 1 ? "" : "s") : "Health history unavailable for the last hour");
  $("#diagnostics-health-chart-state").textContent = state.diagnosticsHistoryStatus === "current" ? (healthValues.length ? presentation.label : "No samples") : state.diagnosticsHistoryStatus === "stale" ? "Stale" : "Unavailable";
  $("#diagnostics-usage-state").textContent = state.usageStatus === "current" ? "Live" : state.usageStatus === "stale" ? "Stale" : "Unavailable";
  renderUsageCharts();
}

async function refreshDiagnostics(render = true) {
  const hasHistory = Array.isArray(state.diagnosticsHistory?.items);
  state.diagnosticsHistoryStatus = hasHistory ? "refreshing" : "loading";
  state.diagnosticsError = "";
  const results = await Promise.allSettled([
    api("/api/diagnostics"),
    api("/api/diagnostics/history?limit=120"),
    api("/api/health/settings"),
  ]);
  if (results[0].status === "fulfilled") state.diagnostics = results[0].value;
  else state.diagnosticsError = results[0].reason?.message || "Diagnostics unavailable";
  if (results[1].status === "fulfilled") {
    state.diagnosticsHistory = results[1].value;
    state.diagnosticsHistoryStatus = "current";
  } else {
    state.diagnosticsHistoryStatus = hasHistory ? "stale" : "unavailable";
    state.diagnosticsError ||= results[1].reason?.message || "Diagnostic history unavailable";
  }
  if (results[2].status === "fulfilled") state.health = results[2].value;
  if (render) {
    renderSystemHealth();
    renderDiagnostics();
  }
}

function selectRecommendedDiagnostics() {
  state.diagnosticsSelectedChecks = new Set(diagnosticChecks().filter((check) => String(check.status).toUpperCase() !== "PASS").map((check) => String(check.id)));
  state.diagnosticsSelectionInitialized = true;
  renderDiagnostics();
  $("#diagnostics-repair")?.focus({ preventScroll: true });
}

function repairDispatchPresentation() {
  const policy = state.diagnosticsRepairPreview?.repair_policy || state.diagnostics?.health?.repair_policy || {};
  return policy.dispatch === "disabled"
    ? "Dispatch is unavailable from this server. SWARM can prepare an audited request, but it will not start Codex or change your system."
    : String(policy.claim_limit || "The server did not provide a repair dispatch claim.");
}

function renderRepairDialog() {
  const preview = $("#repair-preview");
  const selected = diagnosticChecks().filter((check) => state.diagnosticsSelectedChecks.has(String(check.id)));
  preview.innerHTML = '<section class="repair-preview-summary"><strong>' + selected.length + ' check' + (selected.length === 1 ? "" : "s") + '</strong><span>Scope: ' + escapeHTML(state.projectId === "all" ? "All projects" : state.projectId) + '</span></section><ul>' + selected.map((check) => '<li><span class="diagnostics-signal ' + diagnosticStatusClass(check.status) + '">' + escapeHTML(String(check.status).toUpperCase()) + '</span><div><strong>' + escapeHTML(humanize(check.id)) + '</strong><p>' + escapeHTML(check.recommended_action || check.summary || "Review this check.") + '</p></div></li>').join("") + '</ul>';
  $("#repair-dispatch-note").textContent = repairDispatchPresentation();
  $("#repair-status").textContent = state.diagnosticsRepairError || (state.diagnosticsRepairPending ? "Preparing preview…" : state.diagnosticsRepairPreview ? "Preview ready. Acknowledgement is required before preparation." : "Preview the selected checks before preparing a request.");
  $("#repair-acknowledge").disabled = state.diagnosticsRepairPending || !state.diagnosticsRepairPreview;
  $("#repair-confirm").disabled = state.diagnosticsRepairPending || !state.diagnosticsRepairPreview || !$("#repair-acknowledge").checked;
}

async function openRepairPreview(trigger) {
  if (!state.diagnosticsSelectedChecks.size) return;
  state.diagnosticsRepairTrigger = trigger;
  state.diagnosticsRepairPreview = null;
  state.diagnosticsRepairError = "";
  state.diagnosticsRepairPending = true;
  $("#repair-acknowledge").checked = false;
  const dialog = $("#repair-dialog");
  if (!dialog.open) dialog.showModal();
  renderRepairDialog();
  requestAnimationFrame(() => $("#repair-close")?.focus({ preventScroll: true }));
  try {
    state.diagnosticsRepairPreview = await api("/api/health/repair", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ check_ids: [...state.diagnosticsSelectedChecks], scope: state.projectId, acknowledge: false, dry_run: true }) });
  } catch (error) {
    state.diagnosticsRepairError = error.message || "Repair preview unavailable.";
  } finally {
    state.diagnosticsRepairPending = false;
    renderRepairDialog();
  }
}

function closeRepairDialog(restoreFocus = true) {
  const dialog = $("#repair-dialog");
  if (dialog.open) dialog.close();
  if (restoreFocus) state.diagnosticsRepairTrigger?.focus({ preventScroll: true });
  state.diagnosticsRepairTrigger = null;
}

async function confirmRepairPreparation() {
  if (!state.diagnosticsRepairPreview || !$("#repair-acknowledge").checked || state.diagnosticsRepairPending) return;
  state.diagnosticsRepairPending = true;
  state.diagnosticsRepairError = "";
  renderRepairDialog();
  try {
    const result = await api("/api/health/repair", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ check_ids: [...state.diagnosticsSelectedChecks], scope: state.projectId, acknowledge: true, dry_run: false }) });
    state.diagnosticsRepairPreview = result;
    $("#repair-status").textContent = "Repair request prepared. " + repairDispatchPresentation();
    $("#repair-acknowledge").checked = false;
  } catch (error) {
    state.diagnosticsRepairError = error.message || "Repair request could not be prepared.";
  } finally {
    state.diagnosticsRepairPending = false;
    renderRepairDialog();
  }
}

function safeProfileAvatarURL(value) {
  const url = String(value || "");
  return /^\/(?:swarm-icon-64\.png|assets\/[a-z0-9_/-]+\.(?:png|jpe?g|webp))$/i.test(url) && !url.includes("..") ? url : "";
}

function renderProfile() {
  const profile = state.profile?.profile || {};
  const avatar = safeProfileAvatarURL(profile?.avatar?.url);
  const preview = $("#profile-avatar-preview");
  const previewURL = state.profilePreviewUrl || avatar;
  preview.hidden = !previewURL;
  preview.src = previewURL || "";
  preview.alt = previewURL ? "Profile avatar preview" : "";
  $("#profile-avatar-placeholder").hidden = Boolean(previewURL);
  $("#profile-display-name").value = profile.display_name || "";
  $("#profile-compact-updates").checked = profile.preferences?.compact_updates === true;
  $("#profile-reduced-motion").checked = profile.preferences?.reduced_motion === true;
  $("#profile-claim-limit").textContent = state.profile?.claim_limit || "This is a local presentation profile, not an account or provider identity.";
  const unavailable = state.profileStatus === "unavailable";
  $("#profile-status").textContent = state.profileError || (state.profileStatus === "loading" ? "Loading profile…" : unavailable ? "Profile editing is unavailable from this server. Your current presentation remains readable." : "Local presentation profile loaded.");
  $("#profile-save").disabled = state.profileStatus !== "current" || state.profileSaving;
  [$("#profile-display-name"), $("#profile-avatar-input"), $("#profile-compact-updates"), $("#profile-reduced-motion")].forEach((control) => control.disabled = state.profileStatus !== "current" || state.profileSaving);
}

async function openProfile(trigger) {
  state.profileTrigger = trigger;
  state.profileStatus = "loading";
  state.profileError = "";
  state.profileUpload = null;
  if (state.profilePreviewUrl) URL.revokeObjectURL(state.profilePreviewUrl);
  state.profilePreviewUrl = "";
  const dialog = $("#profile-dialog");
  if (!dialog.open) dialog.showModal();
  renderProfile();
  requestAnimationFrame(() => $("#profile-close")?.focus({ preventScroll: true }));
  try {
    state.profile = await api(PROFILE_API_CONTRACT.read);
    state.profileStatus = "current";
  } catch (error) {
    state.profile = null;
    state.profileStatus = "unavailable";
    state.profileError = error.message || "Profile unavailable.";
  }
  renderProfile();
}

function closeProfile(restoreFocus = true) {
  const dialog = $("#profile-dialog");
  if (dialog.open) dialog.close();
  if (state.profilePreviewUrl) URL.revokeObjectURL(state.profilePreviewUrl);
  state.profilePreviewUrl = "";
  state.profileUpload = null;
  if (restoreFocus) state.profileTrigger?.focus({ preventScroll: true });
  state.profileTrigger = null;
}

function selectProfileAvatar(file) {
  if (!file) return;
  if (!new Set(["image/png", "image/jpeg", "image/webp"]).has(file.type) || file.size > 5 * 1024 * 1024) {
    state.profileError = "Choose a PNG, JPEG, or WebP image up to 5 MB.";
    renderProfile();
    return;
  }
  if (state.profilePreviewUrl) URL.revokeObjectURL(state.profilePreviewUrl);
  state.profileUpload = file;
  state.profilePreviewUrl = URL.createObjectURL(file);
  state.profileError = "";
  renderProfile();
}

async function saveProfile(event) {
  event.preventDefault();
  if (state.profileStatus !== "current" || state.profileSaving) return;
  const displayName = $("#profile-display-name").value.trim();
  if (!displayName) {
    state.profileError = "Enter a display name.";
    renderProfile();
    $("#profile-display-name").focus();
    return;
  }
  const payload = { schema_version: PROFILE_API_CONTRACT.schemaVersion, display_name: displayName, preferences: { compact_updates: $("#profile-compact-updates").checked, reduced_motion: $("#profile-reduced-motion").checked } };
  const options = state.profileUpload ? (() => { const body = new FormData(); body.append(PROFILE_API_CONTRACT.profileField, JSON.stringify(payload)); body.append(PROFILE_API_CONTRACT.avatarField, state.profileUpload, state.profileUpload.name); return { method: "POST", body }; })() : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) };
  state.profileSaving = true;
  state.profileError = "";
  renderProfile();
  try {
    const result = await api(PROFILE_API_CONTRACT.write, options);
    state.profile = result;
    state.profileStatus = "current";
    state.profileUpload = null;
    if (state.profilePreviewUrl) URL.revokeObjectURL(state.profilePreviewUrl);
    state.profilePreviewUrl = "";
    $("#profile-status").textContent = "Profile saved.";
  } catch (error) {
    state.profileError = error.status === 404 || error.status === 405 ? "Profile saving is unavailable from this server. No changes were applied." : (error.message || "Profile could not be saved. No changes were applied.");
  } finally {
    state.profileSaving = false;
    renderProfile();
  }
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
  $("#metric-progress-trend").setAttribute("aria-label", presentation.progress.series?.length ? "Accepted verified progress trend" : "Verified progress trend unavailable");
  renderUsageCharts();
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
const NOTIFICATION_SAFE_VIEWS = Object.freeze({ projects: "overview", review: "review", assets: "assets", roles: "roles" });

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
  return { view, projectId, ctrlId };
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
  setProjectSelection(target.projectId, target.ctrlId);
  state.projectTab = "overview";
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

function currentProjectView() {
  const projection = state.overview?.project_view;
  const projectId = selectedProgressProjectId();
  return projection && projection.project_id === projectId && projection.tab?.id === "ui" ? projection : null;
}

function projectViewEvidence(screenKey) {
  const screen = currentProjectView()?.screens?.find((item) => item.id === screenKey);
  return Array.isArray(screen?.evidence) ? screen.evidence : [];
}

function projectViewRequirementGroup(nodeIds) {
  const identifiers = new Set((Array.isArray(nodeIds) ? nodeIds : [nodeIds]).filter(Boolean));
  return currentProjectView()?.requirements?.groups?.find((group) => (group.node_ids || []).some((id) => identifiers.has(id))) || null;
}

function projectViewRequirementText(nodeIds) {
  const group = projectViewRequirementGroup(nodeIds);
  if (!group) return "";
  const counts = group.counts_by_state || {};
  const parts = [
    [counts.KNOWN_SATISFIED, "satisfied"], [counts.PARTIAL, "partial"],
    [counts.MISSING, "missing"], [counts.UNKNOWN, "unknown"],
  ].filter(([count]) => Number(count) > 0).map(([count, label]) => String(count) + " " + label);
  return group.label + (parts.length ? " · " + parts.join(" · ") : "");
}

function openProjectViewEvidence(screenKey, trigger) {
  const evidence = projectViewEvidence(screenKey);
  if (!evidence.length) return;
  const screen = currentProjectView()?.screens?.find((item) => item.id === screenKey);
  const requirementSummary = projectViewRequirementText([screen?.screen_id, screen?.state_id, screen?.id]);
  state.evidenceImages = evidence.map((item) => ({ ...item, project_requirement_summary: requirementSummary }));
  openEvidenceLightbox(0, trigger);
}

function projectViewScreenMarkup(screen) {
  const evidence = Array.isArray(screen.evidence) ? screen.evidence : [];
  const preview = evidence[0];
  const devices = Array.isArray(screen.devices) ? screen.devices : [];
  const label = screen.label || screen.id;
  const previewMarkup = preview
    ? '<button class="project-ui-preview" type="button" data-project-view-evidence="' + escapeHTML(screen.id) + '" aria-label="Open evidence for ' + escapeHTML(label) + '"><img loading="lazy" decoding="async" src="' + proofMediaURL(preview) + '" alt=""></button>'
    : '<div class="project-ui-preview is-empty" aria-label="No bound image evidence"><svg class="lucide" aria-hidden="true"><use href="#lucide-image"></use></svg><span>Evidence unavailable</span></div>';
  const deviceMarkup = devices.length
    ? '<ul class="project-ui-devices" aria-label="Bound devices">' + devices.map((device) => '<li>' + escapeHTML(humanize(device)) + '</li>').join("") + '</ul>'
    : "";
  const alternatives = Number(screen.alternative_count) > 1
    ? '<span class="project-ui-alternatives">' + escapeHTML(String(screen.alternative_count)) + ' alternatives</span>'
    : "";
  const requirements = projectViewRequirementText([screen.screen_id, screen.state_id, screen.id]);
  return '<article class="project-ui-card" data-project-view-screen="' + escapeHTML(screen.id) + '">' + previewMarkup + '<div class="project-ui-card-copy"><p class="eyebrow">' + escapeHTML(screen.screen_id + " · " + screen.state_id) + '</p><h3>' + escapeHTML(label) + '</h3><div><span class="project-ui-status">' + escapeHTML(humanize(screen.status || "UNKNOWN")) + '</span>' + alternatives + '</div>' + deviceMarkup + (requirements ? '<small class="project-ui-requirements">' + escapeHTML(requirements) + '</small>' : '') + '</div></article>';
}

function projectViewMapModel(projection, selectedGroupId = "") {
  const graph = projection?.map;
  if (!graph || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges) || !graph.nodes.length || graph.nodes.length > 200 || graph.edges.length > 500) return null;
  const nodes = [];
  const nodesById = new Map();
  for (const raw of graph.nodes) {
    const id = typeof raw?.id === "string" ? raw.id.trim() : "";
    const label = typeof raw?.label === "string" ? raw.label.trim() : "";
    const visibility = String(raw?.visibility || "visible").toLowerCase();
    const type = String(raw?.type || "screen").toLowerCase();
    const groupId = String(raw?.group_id || raw?.parent_id || "").trim();
    if (!id || !label || nodesById.has(id) || !["visible", "conditional", "hidden"].includes(visibility)) return null;
    const node = { ...raw, id, label, type, visibility, groupId, order: Number.isFinite(Number(raw.order)) ? Number(raw.order) : 0 };
    nodes.push(node);
    nodesById.set(id, node);
  }
  if (nodes.some((node) => node.groupId && !nodesById.has(node.groupId))) return null;
  const edges = [];
  const edgeIds = new Set();
  for (let index = 0; index < graph.edges.length; index += 1) {
    const raw = graph.edges[index];
    const source = typeof raw?.source === "string" ? raw.source.trim() : "";
    const target = typeof raw?.target === "string" ? raw.target.trim() : "";
    const id = typeof raw?.id === "string" && raw.id.trim() ? raw.id.trim() : source + "--" + target + "--" + index;
    if (!source || !target || source === target || !nodesById.has(source) || !nodesById.has(target) || edgeIds.has(id)) return null;
    edgeIds.add(id);
    edges.push({ ...raw, id, source, target });
  }
  const presentable = (node) => node.visibility !== "hidden" && !["runtime", "data", "state"].includes(node.type);
  const selectedGroup = selectedGroupId ? nodesById.get(selectedGroupId) : null;
  if (selectedGroupId && (!selectedGroup || !presentable(selectedGroup))) return null;
  const visibleNodes = nodes.filter((node) => presentable(node) && (selectedGroup ? node.groupId === selectedGroup.id : !node.groupId));
  if (!visibleNodes.length) return null;
  const visibleIds = new Set(visibleNodes.map((node) => node.id));
  const visibleEdges = edges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target));
  const outgoing = new Map(visibleNodes.map((node) => [node.id, []]));
  const indegree = new Map(visibleNodes.map((node) => [node.id, 0]));
  visibleEdges.forEach((edge) => {
    outgoing.get(edge.source).push(edge.target);
    indegree.set(edge.target, indegree.get(edge.target) + 1);
  });
  const stable = (left, right) => left.order - right.order || left.id.localeCompare(right.id);
  const pending = visibleNodes.filter((node) => indegree.get(node.id) === 0).sort(stable);
  const depths = new Map(pending.map((node) => [node.id, 0]));
  const visited = new Set();
  while (pending.length) {
    const node = pending.shift();
    if (visited.has(node.id)) continue;
    visited.add(node.id);
    for (const targetId of outgoing.get(node.id)) {
      depths.set(targetId, Math.max(depths.get(targetId) || 0, (depths.get(node.id) || 0) + 1));
      indegree.set(targetId, indegree.get(targetId) - 1);
      if (indegree.get(targetId) === 0) pending.push(nodesById.get(targetId));
    }
    pending.sort(stable);
  }
  const cycleDepth = depths.size ? Math.max(...depths.values()) + 1 : 0;
  visibleNodes.filter((node) => !visited.has(node.id)).sort(stable).forEach((node) => depths.set(node.id, cycleDepth));
  const layers = [];
  visibleNodes.sort(stable).forEach((node) => {
    const depth = depths.get(node.id) || 0;
    (layers[depth] ||= []).push(node);
  });
  return { nodes, nodesById, edges: visibleEdges, layers: layers.filter(Boolean), selectedGroup };
}

function projectViewMapNodeMarkup(node, model) {
  const hasChildren = model.nodes.some((candidate) => candidate.groupId === node.id && candidate.visibility !== "hidden" && !["runtime", "data", "state"].includes(candidate.type));
  const hasEvidence = Boolean(node.screen_key && projectViewEvidence(node.screen_key).length);
  const requirementSummary = projectViewRequirementText([node.id, node.screen_key]);
  const action = hasChildren ? ' data-project-map-group="' + escapeHTML(node.id) + '"' : hasEvidence ? ' data-project-view-evidence="' + escapeHTML(node.screen_key) + '"' : ' aria-disabled="true"';
  const actionLabel = hasChildren ? "Open " + node.label + " group" : hasEvidence ? "Open evidence for " + node.label : node.label + ", evidence unavailable";
  const kind = hasChildren ? '<span class="project-ui-node-kind">Group</span>' : node.visibility === "conditional" ? '<span class="project-ui-node-kind">Conditional</span>' : "";
  return '<button class="project-ui-flowchart-node' + (hasChildren ? " is-group" : "") + '" type="button" data-project-map-node="' + escapeHTML(node.id) + '"' + action + ' aria-label="' + escapeHTML(actionLabel) + '"><span>' + escapeHTML(node.label) + '</span><small>' + escapeHTML(node.id) + '</small>' + kind + (requirementSummary ? '<small class="project-ui-requirements">' + escapeHTML(requirementSummary) + '</small>' : '') + '</button>';
}

function projectViewMapMarkup(projection) {
  const model = projectViewMapModel(projection, state.projectUiGroupId);
  if (!model) return '<section class="project-ui-map is-unavailable" aria-label="App Map"><p class="empty-state" role="status">Flowchart unavailable. The accepted map projection could not be rendered safely.</p></section>';
  const parentGroupId = model.selectedGroup?.groupId || "";
  const heading = model.selectedGroup
    ? '<header class="project-ui-map-heading"><button class="icon-button" type="button" data-project-map-back data-project-map-parent="' + escapeHTML(parentGroupId) + '" aria-label="Back to ' + escapeHTML(parentGroupId ? (model.nodesById.get(parentGroupId)?.label || "parent group") : "App Map") + '"><svg class="lucide" aria-hidden="true"><use href="#lucide-chevron-left"></use></svg></button><div><p class="eyebrow">App Map group</p><h3>' + escapeHTML(model.selectedGroup.label) + '</h3></div></header>'
    : "";
  const connectionList = model.edges.length
    ? model.edges.map((edge) => '<li>' + escapeHTML((model.nodesById.get(edge.source)?.label || edge.source) + " to " + (model.nodesById.get(edge.target)?.label || edge.target) + (edge.label ? ": " + edge.label : "")) + '</li>').join("")
    : '<li>No graph connections</li>';
  const paths = model.edges.map((edge) => '<path data-project-map-edge="' + escapeHTML(edge.id) + '" data-source="' + escapeHTML(edge.source) + '" data-target="' + escapeHTML(edge.target) + '" marker-end="url(#project-map-arrow)"></path>').join("");
  const layers = model.layers.map((layer, index) => '<div class="project-ui-flowchart-layer" data-flow-layer="' + index + '">' + layer.map((node) => projectViewMapNodeMarkup(node, model)).join("") + '</div>').join("");
  return '<section class="project-ui-map" aria-label="App Map">' + heading + '<div class="project-ui-flowchart"><svg class="project-ui-flowchart-connectors" aria-hidden="true" focusable="false"><defs><marker id="project-map-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z"></path></marker></defs>' + paths + '</svg><div class="project-ui-flowchart-layers">' + layers + '</div><ul class="sr-only" aria-label="Map connections">' + connectionList + '</ul></div></section>';
}

function drawProjectViewConnectors() {
  const stage = $(".project-ui-flowchart");
  if (!stage) return;
  const svg = $(".project-ui-flowchart-connectors", stage);
  if (!svg) return;
  const stageRect = stage.getBoundingClientRect();
  if (!stageRect.width || !stageRect.height) return;
  svg.setAttribute("viewBox", "0 0 " + stage.clientWidth + " " + stage.clientHeight);
  svg.setAttribute("width", String(stage.clientWidth));
  svg.setAttribute("height", String(stage.clientHeight));
  const nodeById = new Map($$("[data-project-map-node]", stage).map((node) => [node.dataset.projectMapNode, node]));
  $$("[data-project-map-edge]", svg).forEach((path) => {
    const source = nodeById.get(path.dataset.source);
    const target = nodeById.get(path.dataset.target);
    if (!source || !target) { path.removeAttribute("d"); return; }
    const from = source.getBoundingClientRect();
    const to = target.getBoundingClientRect();
    const x1 = from.left + from.width / 2 - stageRect.left;
    const y1 = from.bottom - stageRect.top;
    const x2 = to.left + to.width / 2 - stageRect.left;
    const y2 = to.top - stageRect.top;
    const bend = Math.max(24, Math.abs(y2 - y1) / 2);
    path.setAttribute("d", "M " + x1 + " " + y1 + " C " + x1 + " " + (y1 + bend) + ", " + x2 + " " + (y2 - bend) + ", " + x2 + " " + y2);
  });
}

function scheduleProjectViewConnectors() {
  if (state.projectTab === "ui" && state.projectUiMode === "map") requestAnimationFrame(drawProjectViewConnectors);
  if ($("#onboarding-dialog")?.open && state.onboardingStep === 1) requestAnimationFrame(drawOnboardingCoordinationConnectors);
}

function projectViewMarkup() {
  const projection = currentProjectView();
  if (!projection) return '<p class="empty-state">UI evidence is unavailable for this project.</p>';
  const mode = state.projectUiMode === "map" ? "map" : "screens";
  const content = mode === "map"
    ? projectViewMapMarkup(projection)
    : '<section class="project-ui-screens" aria-label="Project screens">' + ((projection.screens || []).map(projectViewScreenMarkup).join("") || '<p class="empty-state">No accepted screen states are available.</p>') + '</section>';
  return '<section class="project-ui"><header class="project-ui-toolbar"><div><p class="eyebrow">Digest-bound project view</p><h2>' + escapeHTML(projection.tab.label || "UI") + '</h2></div><div class="segmented-control" aria-label="UI view mode">' + (projection.modes || []).map((item) => {
    const selected = item.id === mode;
    return '<button type="button" data-project-ui-mode="' + escapeHTML(item.id) + '" aria-pressed="' + String(selected) + '" class="' + (selected ? "is-selected" : "") + '">' + escapeHTML(item.label) + '</button>';
  }).join("") + '</div></header>' + content + '<p class="project-ui-claim">' + escapeHTML(projection.claim_limit || "Project UI is read-only.") + '</p></section>';
}

function projectProgressQueueProjection(progress) {
  const projection = progress?.progress_queue;
  const cursor = progress?.cursor;
  if (!projection || projection.view_id !== "view.project.progress" || projection.renderer !== "table") return null;
  const projectId = selectedProgressProjectId();
  const scope = projection.scope_binding;
  if (projection.project_id !== projectId || scope?.project_id !== projectId || !Array.isArray(scope?.ctrl_ids)) return null;
  if (!Array.isArray(projection.segments)) return null;
  const expected = ["segment.project.progress.active", "segment.project.progress.queue"];
  if (projection.segments.length !== expected.length || projection.segments.some((segment, index) => segment?.segment_id !== expected[index] || !Array.isArray(segment.rows))) return null;
  if (projection.status !== "CURRENT") {
    if (progress?.status !== "UNKNOWN" || projection.available !== false || !["UNKNOWN", "RESYNC_REQUIRED"].includes(projection.status)) return null;
    return projection;
  }
  if (!cursor || !projection.accepted_cursor || progress?.status === "UNKNOWN") return null;
  if (["event_seq", "event_id", "event_digest"].some((field) => projection.accepted_cursor[field] !== cursor[field] || scope.cursor?.[field] !== cursor[field])) return null;
  return projection;
}

function progressQueueRowPresentation(row, stale = false) {
  const forceUnknown = stale || row?.freshness?.state === "STALE";
  return {
    ...row,
    progress: forceUnknown ? { state: "UNKNOWN", completed_milestones: null, total_milestones: null, percent: null } : row?.progress,
    eta: forceUnknown ? { state: "UNKNOWN", start_ms: null, end_ms: null, confidence: null, basis_receipt_ids: [] } : row?.eta,
    elapsed: forceUnknown ? { state: "UNKNOWN", elapsed_ms: null } : row?.elapsed,
    queue_state: forceUnknown ? "UNKNOWN" : row?.queue_state,
    runnable: forceUnknown ? false : row?.runnable,
    blocked_recovery: forceUnknown ? null : row?.blocked_recovery,
  };
}

function projectProgressQueueSegments(projection, stale = false) {
  if (!projection || !Array.isArray(projection.segments)) return [];
  return projection.segments.map((segment) => ({
    ...segment,
    rows: segment.rows.map((row) => progressQueueRowPresentation(row, stale)),
  }));
}

function progressQueueStateLabel(row, segmentId) {
  if (segmentId === "segment.project.progress.active" && row.queue_state == null) return humanize(row.lifecycle || "Active");
  const labels = {
    QUEUED_NOT_STARTED: "Queued",
    WAITING_FOR_DEPENDENCY: "Waiting for dependency",
    WAITING_FOR_CAPACITY: "Waiting for capacity",
    REVIEW_GATED: "Waiting for review",
    SCOPED_BLOCKED: "Blocked",
    FAILED: "Failed",
    UNKNOWN: "Unknown",
  };
  return labels[row.queue_state] || "Unknown";
}

function progressQueueProgressMarkup(row) {
  const progress = row?.progress;
  if (progress?.state !== "KNOWN" || !Number.isFinite(Number(progress.percent))) {
    return '<span class="project-progress-unknown" aria-label="Progress unavailable">— <small>UNKNOWN</small></span>';
  }
  const label = String(progress.completed_milestones) + " of " + String(progress.total_milestones) + " accepted milestones";
  return '<div class="project-progress-cell"><div class="project-progress-meter" role="progressbar" aria-label="' + escapeHTML(row.task_name + " milestone progress") + '" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + escapeHTML(progress.percent) + '" aria-valuetext="' + escapeHTML(label) + '"><i style="width:' + escapeHTML(progress.percent) + '%"></i></div><small>' + escapeHTML(label) + '</small></div>';
}

function progressQueueEtaMarkup(row) {
  const eta = row?.eta;
  if (eta?.state !== "KNOWN") return '<span aria-label="ETA unavailable">— <small>UNKNOWN</small></span>';
  const start = new Date(Number(eta.start_ms));
  const end = new Date(Number(eta.end_ms));
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return '<span aria-label="ETA unavailable">— <small>UNKNOWN</small></span>';
  return '<span class="project-progress-eta"><time datetime="' + escapeHTML(start.toISOString()) + '">' + escapeHTML(formatEta(eta.start_ms)) + '</time><span aria-hidden="true">–</span><time datetime="' + escapeHTML(end.toISOString()) + '">' + escapeHTML(formatEta(eta.end_ms)) + '</time><small>' + escapeHTML(String(eta.confidence)) + ' confidence</small></span>';
}

function progressQueueRecoveryMarkup(row) {
  const recovery = row?.blocked_recovery;
  if (!recovery) return "";
  const release = recovery.blocked_release_condition;
  const suggested = recovery.blocked_suggested_recovery;
  const evidence = Array.isArray(suggested?.evidence_receipt_refs) ? suggested.evidence_receipt_refs : [];
  if (!release?.condition || !release?.release_event_id || !release?.release_event_digest || !suggested?.action || !suggested?.route_id || !suggested?.responsible_authority || !Number.isInteger(recovery.blocked_attempts) || typeof recovery.blocked_critical_path !== "boolean" || !evidence.length || evidence.some((receipt) => !receipt?.event_id || !receipt?.event_digest)) return "";
  const evidenceMarkup = evidence.map((receipt) => '<li><span>' + escapeHTML(receipt.event_id) + '</span><code>' + escapeHTML(receipt.event_digest) + '</code></li>').join("");
  return '<details class="project-progress-recovery"><summary>Recovery details</summary><dl><div><dt>Release</dt><dd>' + escapeHTML(release.condition) + '</dd></div><div><dt>Route</dt><dd>' + escapeHTML(suggested.route_id) + '</dd></div><div><dt>Critical path</dt><dd>' + escapeHTML(recovery.blocked_critical_path ? "Yes" : "No") + '</dd></div><div><dt>Release event</dt><dd><span>' + escapeHTML(release.release_event_id) + '</span><code>' + escapeHTML(release.release_event_digest) + '</code></dd></div><div><dt>Recovery</dt><dd>' + escapeHTML(suggested.action) + '</dd></div><div><dt>Authority</dt><dd>' + escapeHTML(suggested.responsible_authority) + '</dd></div><div><dt>Attempts</dt><dd>' + escapeHTML(recovery.blocked_attempts) + '</dd></div><div><dt>Evidence</dt><dd><ul>' + evidenceMarkup + '</ul></dd></div></dl></details>';
}

function projectProgressQueueRowMarkup(row, segmentId) {
  const stateLabel = progressQueueStateLabel(row, segmentId);
  const signal = row?.last_accepted_signal?.summary;
  const elapsed = row?.elapsed?.state === "KNOWN" ? formatDuration(row.elapsed.elapsed_ms) : "—";
  const ctrlId = row?.scope_binding?.ctrl_id || "UNKNOWN";
  const taskContext = ["CTRL " + ctrlId, row.role, row.owner_id].filter(Boolean).join(" · ");
  return '<tr data-progress-task="' + escapeHTML(row.task_id) + '" data-progress-ctrl="' + escapeHTML(ctrlId) + '"><th scope="row" data-label="Task"><strong>' + escapeHTML(row.task_name || row.task_id) + '</strong><small>' + escapeHTML(taskContext) + '</small></th><td data-label="State"><span class="project-progress-state" data-state="' + escapeHTML(row.queue_state || row.lifecycle || "UNKNOWN") + '">' + escapeHTML(stateLabel) + '</span>' + progressQueueRecoveryMarkup(row) + '</td><td data-label="Progress">' + progressQueueProgressMarkup(row) + '</td><td data-label="Last accepted signal"><span>' + escapeHTML(signal || "—") + '</span><small>' + escapeHTML(row?.freshness?.state || "UNKNOWN") + '</small></td><td data-label="Elapsed"><span aria-label="' + escapeHTML(elapsed === "—" ? "Elapsed unavailable" : "Elapsed " + elapsed) + '">' + escapeHTML(elapsed) + '</span>' + (elapsed === "—" ? '<small>UNKNOWN</small>' : '') + '</td><td data-label="ETA">' + progressQueueEtaMarkup(row) + '</td></tr>';
}

function projectProgressQueueMarkup(progress) {
  const projection = projectProgressQueueProjection(progress);
  if (!projection || projection.status !== "CURRENT" || projection.available === false) {
    return '<section class="panel project-progress-view is-unavailable" aria-labelledby="project-progress-view-title"><header class="overview-section-head"><div><p class="eyebrow">Accepted project scope</p><h2 id="project-progress-view-title">Project Progress</h2></div><p>— <span class="sr-only">UNKNOWN</span><small aria-hidden="true">UNKNOWN</small></p></header><p class="empty-state" role="status">Active and queue are unavailable until a fresh accepted scope is restored.</p></section>';
  }
  const stale = ["stale", "unavailable"].includes(state.projectProgressStatus) || projection.status !== "CURRENT";
  const segments = projectProgressQueueSegments(projection, stale);
  const tables = segments.map((segment) => '<section class="project-progress-segment" aria-labelledby="' + escapeHTML(segment.segment_id) + '"><header><h3 id="' + escapeHTML(segment.segment_id) + '">' + escapeHTML(segment.label) + '</h3><span>' + escapeHTML(segment.rows.length) + '</span></header>' + (segment.rows.length ? '<div class="project-progress-table-wrap"><table class="project-progress-table"><thead><tr><th scope="col">Task</th><th scope="col">State</th><th scope="col">Progress</th><th scope="col">Last accepted signal</th><th scope="col">Elapsed</th><th scope="col">ETA</th></tr></thead><tbody>' + segment.rows.map((row) => projectProgressQueueRowMarkup(row, segment.segment_id)).join("") + '</tbody></table></div>' : '<p class="empty-state">No ' + escapeHTML(segment.label.toLowerCase()) + ' work at this cursor.</p>') + '</section>').join("");
  return '<section class="panel project-progress-view" aria-labelledby="project-progress-view-title"><header class="overview-section-head"><div><p class="eyebrow">Accepted project scope</p><h2 id="project-progress-view-title">Project Progress</h2></div><p>' + (stale ? 'Last accepted identity · live fields unavailable' : 'Through event ' + escapeHTML(projection.accepted_cursor.event_seq)) + '</p></header>' + tables + '</section>';
}

function projectTabMarkup(tab, progress, nodes) {
  const blocks = progress?.blocks || [];
  const milestones = projectMilestones(blocks);
  if (tab === "overview") {
    const efficiency = verifiedYieldItem("project", selectedProgressProjectId());
    return '<section class="project-overview-grid">' + projectProgressQueueMarkup(progress) + '<div class="milestone-rings">' + (milestones.length ? milestones.slice(0, 4).map(([id, items]) => { const summary = milestoneSummary(items); return '<article><div class="milestone-ring ' + (summary.percent === 100 ? "is-complete" : "") + '" style="--progress:' + (summary.percent ?? 0) + '%"><strong>' + escapeHTML(summary.percent == null ? "—" : Math.round(summary.percent) + "%") + '</strong></div><h3>' + escapeHTML(id) + '</h3><small>' + escapeHTML(summary.admitted + " / " + summary.committed + " admitted") + '</small></article>'; }).join("") : '<p class="empty-state">No measured milestones yet.</p>') + '</div>' + yieldChartMarkup(efficiency) + '<section class="panel project-updates"><header class="overview-section-head"><div><p class="eyebrow">Material events</p><h2>Latest updates</h2></div><p>Newest first</p></header>' + projectFeedMarkup(4) + '</section></section>';
  }
  if (tab === "roadmap") return '<section class="project-roadmap">' + (milestones.length ? milestones.map(([id, items], index) => '<article><span>' + String(index + 1) + '</span><div><h3>' + escapeHTML(id) + '</h3><p>' + escapeHTML(items.length + " block" + (items.length === 1 ? "" : "s") + " · " + milestoneSummary(items).admitted + " admitted") + '</p></div></article>').join("") : '<p class="empty-state">No roadmap receipts yet.</p>') + '</section>';
  if (tab === "lanes") { const owners = new Map(); blocks.forEach((block) => { const id = block.owner_id || "Unassigned"; owners.set(id, [...(owners.get(id) || []), block]); }); return '<section class="project-lanes">' + ([...owners.entries()].map(([owner, items]) => '<section class="panel"><header><h3>' + escapeHTML(owner) + '</h3><span>' + items.length + '</span></header>' + items.map(projectBlockRow).join("") + '</section>').join("") || '<p class="empty-state">No owner lanes yet.</p>') + '</section>'; }
  if (tab === "hierarchy") return '<section class="project-hierarchy">' + (nodes.length ? nodes.filter((node) => !isSubagent(node)).map((node) => '<article><svg class="lucide" aria-hidden="true"><use href="#lucide-git-branch"></use></svg><div><strong>' + escapeHTML(node.worker || node.owner || node.role_label || "Unassigned") + '</strong><span>' + escapeHTML(node.artifact || node.title || node.id) + '</span></div><small>' + escapeHTML(observedAgentRole(node) || "TASK") + '</small></article>').join("") : '<p class="empty-state">No hierarchy is observed for this project.</p>') + '</section>';
  if (tab === "proof") { const images = evidenceImagesFor(nodes); state.evidenceImages = images; return '<section class="project-proof-grid">' + (images.length ? images.map((item, index) => '<button class="asset-tile" type="button" data-evidence-open="' + index + '" aria-label="Open proof image"><img loading="lazy" src="' + proofMediaURL(item) + '" alt=""><span>' + escapeHTML(item.caption || item.kind || "Proof") + '</span></button>').join("") : '<p class="empty-state">No image proof is available for this project.</p>') + '</section>'; }
  if (tab === "ledger") return '<section class="panel project-ledger"><header class="overview-section-head"><div><p class="eyebrow">Canonical events</p><h2>Ledger</h2></div><p>' + escapeHTML(progress?.cursor?.event_seq == null ? "No cursor" : "Through " + progress.cursor.event_seq) + '</p></header>' + projectFeedMarkup(10) + '</section>';
  if (tab === "ui") return projectViewMarkup();
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
  const projectView = currentProjectView();
  const uiTab = $("#project-tab-ui");
  uiTab.hidden = !projectView;
  uiTab.textContent = projectView?.tab?.label || "UI";
  if (state.projectTab === "ui" && !projectView) state.projectTab = "overview";
  const selectedTabId = "project-tab-" + state.projectTab;
  $$('[data-project-tab]').forEach((button) => { const selected = !button.hidden && button.dataset.projectTab === state.projectTab; button.classList.toggle("is-active", selected); button.setAttribute("aria-selected", String(selected)); button.tabIndex = selected ? 0 : -1; });
  const tabPanel = $("#project-tab-panel");
  tabPanel.setAttribute("aria-labelledby", selectedTabId);
  const retainedRunLogMount = state.projectTab === "logs" && $('[data-run-log-surface="project"]', tabPanel);
  if (!retainedRunLogMount) tabPanel.innerHTML = projectTabMarkup(state.projectTab, progress, nodes);
  scheduleProjectViewConnectors();
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
  return state.assets && state.assetBindingKey === assetBindingKey() && Array.isArray(state.assets.items) ? state.assets.items : [];
}

function openProofIdentity(identity, trigger) {
  const images = scopedProofItems().filter((item) => String(item.media_type || "").startsWith("image/"));
  const index = images.findIndex((item) => proofIdentity(item) === identity);
  if (index < 0) return;
  state.evidenceImages = images;
  openEvidenceLightbox(index, trigger);
}

function assetScopeProjectId() {
  return state.projectId === "all" ? "" : String(state.projectId || "");
}

function assetBindingKey(projection = state.assetProjection, projectId = assetScopeProjectId()) {
  return String(projectId || "all") + "|" + (projection === "trash" ? "trash" : "active");
}

function assetIdentity(item) {
  return String(item?.asset_id || "").trim();
}

function assetPresentation(item) {
  return item?.presentation && typeof item.presentation === "object" ? item.presentation : {};
}

function assetTechnical(item) {
  return item?.technical && typeof item.technical === "object" ? item.technical : {};
}

function assetProjectionValue(result, binding, projectId, projection) {
  if (!result || result.ok !== true || result.status !== "available" || result.projection !== projection || !Array.isArray(result.items)) return null;
  const responseProject = String(result.project_id || "");
  if (responseProject !== projectId) return null;
  const seen = new Set();
  for (const item of result.items) {
    const identity = assetIdentity(item);
    if (!identity || seen.has(identity) || (projectId && String(item?.project_id || "") !== projectId)) return null;
    seen.add(identity);
  }
  return { ...result, items: result.items.slice(), binding };
}

function assetEventsValue(result, projectId) {
  if (!result || result.ok !== true || result.status !== "available" || !Array.isArray(result.items)) return null;
  if (String(result.project_id || "") !== projectId) return null;
  const sequence = Number(result.cursor?.sequence);
  return Number.isSafeInteger(sequence) && sequence >= 0 ? sequence : null;
}

async function refreshAssets() {
  const projectId = assetScopeProjectId();
  const projection = state.assetProjection === "trash" ? "trash" : "active";
  const binding = assetBindingKey(projection, projectId);
  const generation = ++state.assetRequestGeneration;
  const hasLastGood = Boolean(state.assets && state.assetBindingKey === binding);
  state.assetStatus = hasLastGood ? "refreshing" : "loading";
  state.assetError = "";
  const inventoryParams = new URLSearchParams({ projection });
  const eventParams = new URLSearchParams({ after_sequence: String(state.assetEventCursors.get(binding) || 0), limit: "64" });
  if (projectId) {
    inventoryParams.set("project_id", projectId);
    eventParams.set("project_id", projectId);
  }
  try {
    const [inventoryResult, eventResult] = await Promise.all([
      api("/api/assets?" + inventoryParams.toString()),
      api("/api/assets/events?" + eventParams.toString()),
    ]);
    if (generation !== state.assetRequestGeneration || binding !== assetBindingKey()) return false;
    const inventory = assetProjectionValue(inventoryResult, binding, projectId, projection);
    const eventSequence = assetEventsValue(eventResult, projectId);
    if (!inventory || eventSequence === null) throw new Error("Asset inventory response was invalid.");
    state.assets = inventory;
    state.assetBindingKey = binding;
    state.assetEventCursors.set(binding, eventSequence);
    state.assetStatus = "current";
    state.assetError = "";
    return true;
  } catch (error) {
    if (generation !== state.assetRequestGeneration || binding !== assetBindingKey()) return false;
    if (!hasLastGood) state.assets = null;
    state.assetBindingKey = binding;
    state.assetStatus = hasLastGood ? "stale" : "unavailable";
    state.assetError = error.message || "Assets could not be loaded.";
    return false;
  }
}

function assetImageMarkup(item, detail = false) {
  const stage = assetStage(item);
  if (stage) return '<span class="asset-image-frame asset-generation-placeholder' + (detail ? ' is-detail' : '') + '" role="status" aria-label="' + escapeHTML(stage.label) + '"><span class="asset-generation-shimmer" aria-hidden="true"></span><strong>' + escapeHTML(stage.label) + '</strong>' + (stage.measured ? '<small>' + escapeHTML(stage.percent + "%") + '</small>' : '') + '</span>';
  const preview = item?.preview && typeof item.preview === "object" ? item.preview : {};
  const url = preview.state === "AVAILABLE" && String(preview.url || "").startsWith("/") ? String(preview.url) : "";
  if (!url) return '<span class="asset-image-frame asset-image-unavailable' + (detail ? ' is-detail' : '') + '" role="status">Preview unavailable</span>';
  return '<span class="asset-image-frame' + (detail ? ' is-detail' : '') + '"><img data-asset-image loading="' + (detail ? "eager" : "lazy") + '" decoding="async" src="' + escapeHTML(url) + '" alt="' + (detail ? escapeHTML("Preview of " + assetLabel(item)) : "") + '"><span class="asset-image-failed"' + (detail ? ' role="status"' : '') + ' hidden>Preview unavailable</span></span>';
}

function assetStage(item) {
  const technical = assetTechnical(item);
  const value = String(assetPresentation(item).status || technical.status || "").trim().toUpperCase();
  const labels = { RESERVED: "Queued", QUEUED: "Queued", GENERATING: "Generating", VALIDATING: "Validating" };
  if (!labels[value]) return null;
  const percent = Number(technical.measured_progress);
  return { value, label: labels[value], measured: technical.measured_progress_provenance === "MEASURED" && Number.isFinite(percent) && percent >= 0 && percent <= 100, percent: Math.round(percent) };
}

function assetLabel(item) {
  const presentation = assetPresentation(item);
  return String(presentation.display_name || "Asset").trim() || "Asset";
}

function assetTypeLabel(item) {
  const kind = String(assetPresentation(item).kind || "").trim();
  if (kind) return humanize(kind);
  const mime = String(assetTechnical(item).media_type || "").trim();
  return mime.startsWith("image/") ? humanize(mime.slice(6)) + " image" : "Asset";
}

function assetProjectLabel(item) {
  const projectId = String(item?.project_id || "");
  return savedProjectRoster().projects.find((project) => project.id === projectId)?.label || projectId || "Unscoped";
}

function assetDate(item, field = "updated") {
  const presentation = assetPresentation(item);
  const technical = assetTechnical(item);
  const value = field === "created" ? (presentation.created_at || technical.created_at_ms) : (presentation.updated_at || technical.updated_at_ms);
  const date = new Date(typeof value === "number" ? value : String(value || ""));
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function assetSize(item) {
  const bytes = Number(assetTechnical(item).size_bytes);
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return Math.round(bytes) + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0) + " KB";
  return (bytes / (1024 * 1024)).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0) + " MB";
}

function assetRevisionItems(selected, items = assetItems()) {
  const selectedTechnical = assetTechnical(selected);
  const logicalId = String(selectedTechnical.logical_asset_id || "").trim();
  if (!logicalId) return [selected];
  const revisions = items.filter((item) => String(assetTechnical(item).logical_asset_id || "").trim() === logicalId);
  if (revisions.length < 2 || !revisions.some((item) => String(assetTechnical(item).parent_revision_id || "").trim())) return [selected];
  return revisions.sort((left, right) => Number(assetTechnical(right).revision || 0) - Number(assetTechnical(left).revision || 0));
}

function assetStateLabel(item) {
  return assetStage(item)?.label || String(assetPresentation(item).status_label || humanize(assetPresentation(item).status || assetTechnical(item).status || "Unknown"));
}

function assetTrashEligible(item) {
  return state.assetProjection === "active" && !assetStage(item) && Number.isSafeInteger(Number(assetTechnical(item).revision)) && Number(assetTechnical(item).revision) > 0;
}

function assetRetryEligible(item) {
  const status = String(assetTechnical(item).status || assetPresentation(item).status || "").toUpperCase();
  return ["FAILED", "CANCELLED"].includes(status) && assetTechnical(item).retry_eligible === true;
}

function assetOperationId(prefix) {
  const suffix = globalThis.crypto?.randomUUID?.() || (Date.now().toString(36) + "-" + Math.random().toString(36).slice(2));
  return prefix + "-" + suffix;
}

function replaceAssetItem(item) {
  const identity = assetIdentity(item);
  const items = assetItems().filter((candidate) => assetIdentity(candidate) !== identity);
  state.assets = { ...(state.assets || {}), items: [item, ...items] };
}

function assetMutationRequest(action, item) {
  const technical = assetTechnical(item);
  const operationId = assetOperationId("asset-" + action);
  const payload = {
    project_id: String(item.project_id || ""),
    asset_id: assetIdentity(item),
    expected_revision: Number(technical.revision),
    operation_id: operationId,
  };
  let path = "/api/assets/" + action;
  if (action === "retry") {
    path = "/api/assets/generation/retry";
    payload.generation_job_id = assetOperationId("generation");
  }
  return { action, path, payload, bindingProjectId: assetScopeProjectId(), pending: true, error: "" };
}

function assetMutationMatches(request) {
  return Boolean(request?.payload?.operation_id)
    && state.assetMutationPending?.payload?.operation_id === request.payload.operation_id;
}

function assetMutationBindingCurrent(request) {
  return String(request?.bindingProjectId || "") === assetScopeProjectId();
}

async function runAssetMutation(request) {
  if (!request || state.assetMutationPending?.pending) return false;
  state.assetMutationPending = { ...request, pending: true, error: "" };
  renderAssets();
  try {
    const result = await api(request.path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request.payload) });
    if (!assetMutationBindingCurrent(request)) {
      if (assetMutationMatches(request)) state.assetMutationPending = null;
      return false;
    }
    const item = result?.asset;
    if (result?.ok !== true || result?.mutation?.accepted !== true || assetIdentity(item) !== request.payload.asset_id || String(item?.project_id || "") !== request.payload.project_id) throw new Error("Asset acknowledgement was invalid.");
    ++state.assetRequestGeneration;
    state.assetMutationPending = null;
    state.assetConfirm = null;
    state.assetError = "";
    if (request.action === "trash") {
      state.assetProjection = "trash";
      state.assetBindingKey = assetBindingKey("trash", request.bindingProjectId);
      state.assets = { ok: true, status: "available", projection: "trash", project_id: request.bindingProjectId || null, items: [item] };
      state.assetStatus = "current";
      state.selectedAssetIdentity = assetIdentity(item);
      state.assetUndo = { item, expectedRevision: Number(assetTechnical(item).revision) };
    } else if (request.action === "restore") {
      state.assetProjection = "active";
      state.assetBindingKey = assetBindingKey("active", request.bindingProjectId);
      state.assets = { ok: true, status: "available", projection: "active", project_id: request.bindingProjectId || null, items: [item] };
      state.assetStatus = "current";
      state.selectedAssetIdentity = assetIdentity(item);
      state.assetUndo = null;
    } else {
      replaceAssetItem(item);
      state.selectedAssetIdentity = assetIdentity(item);
    }
    renderAssets();
    if (request.action === "trash") closeAssetDialog();
    await refreshAssets();
    renderAssets();
    return true;
  } catch (error) {
    if (!assetMutationBindingCurrent(request)) {
      if (assetMutationMatches(request)) state.assetMutationPending = null;
      return false;
    }
    state.assetMutationPending = { ...request, pending: false, error: error.message || "Asset update failed." };
    state.assetError = state.assetMutationPending.error;
    renderAssets();
    return false;
  }
}

async function mutateAsset(action, item) {
  if (!item) return false;
  return runAssetMutation(assetMutationRequest(action, item));
}

function assetGridMarkup(item) {
  const identity = assetIdentity(item);
  const label = assetLabel(item);
  const selected = identity === state.selectedAssetIdentity;
  const contextAction = state.assetProjection === "trash"
    ? '<button class="icon-button" type="button" data-asset-action="restore" data-asset-id="' + escapeHTML(identity) + '" aria-label="Restore ' + escapeHTML(label) + '" title="Restore"><svg class="lucide" aria-hidden="true"><use href="#lucide-rotate-ccw"></use></svg></button>'
    : assetRetryEligible(item)
      ? '<button class="icon-button" type="button" data-asset-action="retry" data-asset-id="' + escapeHTML(identity) + '" aria-label="Retry generation for ' + escapeHTML(label) + '" title="Retry generation"><svg class="lucide" aria-hidden="true"><use href="#lucide-refresh-cw"></use></svg></button>'
      : '<button class="icon-button" type="button" data-asset-action="trash" data-asset-id="' + escapeHTML(identity) + '" aria-label="Move ' + escapeHTML(label) + ' to trash" title="' + (assetTrashEligible(item) ? "Move to trash" : "Trash unavailable for this asset") + '"' + (assetTrashEligible(item) ? "" : " disabled") + '><svg class="lucide" aria-hidden="true"><use href="#lucide-trash-2"></use></svg></button>';
  return '<article class="asset-tile' + (selected ? ' is-selected' : '') + '" data-asset-card="' + escapeHTML(identity) + '"><button class="asset-image-button" type="button" data-asset-detail="' + escapeHTML(identity) + '" aria-label="Open asset details for ' + escapeHTML(label) + '" aria-current="' + String(selected) + '">' + assetImageMarkup(item) + '</button><div class="asset-quick-actions" aria-label="Quick actions for ' + escapeHTML(label) + '"><button class="icon-button" type="button" data-asset-detail="' + escapeHTML(identity) + '" aria-label="View details for ' + escapeHTML(label) + '" title="View details"><svg class="lucide" aria-hidden="true"><use href="#lucide-eye"></use></svg></button>' + contextAction + '</div></article>';
}

function assetListMarkup(item) {
  const identity = assetIdentity(item);
  const label = assetLabel(item);
  const selected = identity === state.selectedAssetIdentity;
  const project = state.projectId === "all" && item.project_id ? '<span><small>Project</small>' + escapeHTML(assetProjectLabel(item)) + '</span>' : '';
  const presentation = assetPresentation(item);
  const action = state.assetProjection === "trash" ? "restore" : assetRetryEligible(item) ? "retry" : "trash";
  const enabled = action !== "trash" || assetTrashEligible(item);
  const actionLabel = action === "restore" ? "Restore " + label : action === "retry" ? "Retry generation for " + label : "Move " + label + " to trash";
  const icon = action === "restore" ? "rotate-ccw" : action === "retry" ? "refresh-cw" : "trash-2";
  return '<article class="asset-list-row' + (selected ? ' is-selected' : '') + '" data-asset-card="' + escapeHTML(identity) + '"><button class="asset-list-main" type="button" data-asset-detail="' + escapeHTML(identity) + '" aria-label="Open asset details for ' + escapeHTML(label) + '" aria-current="' + String(selected) + '">' + assetImageMarkup(item) + '<span class="asset-list-copy"><strong>' + escapeHTML(label) + '</strong>' + (presentation.description ? '<small>' + escapeHTML(presentation.description) + '</small>' : '') + '</span><span class="asset-list-facts"><span><small>Type</small>' + escapeHTML(assetTypeLabel(item)) + '</span>' + project + '<span><small>Updated</small>' + escapeHTML(assetDate(item)) + '</span><span><small>Status</small>' + escapeHTML(assetStateLabel(item)) + '</span></span></button><div class="asset-list-actions"><button class="icon-button" type="button" data-asset-detail="' + escapeHTML(identity) + '" aria-label="View details for ' + escapeHTML(label) + '" title="View details"><svg class="lucide" aria-hidden="true"><use href="#lucide-eye"></use></svg></button><button class="icon-button" type="button" data-asset-action="' + action + '" data-asset-id="' + escapeHTML(identity) + '" aria-label="' + escapeHTML(actionLabel) + '" title="' + escapeHTML(enabled ? actionLabel : "Trash unavailable for this asset") + '"' + (enabled ? "" : " disabled") + '><svg class="lucide" aria-hidden="true"><use href="#lucide-' + icon + '"></use></svg></button></div></article>';
}

function renderAssetDialog(item) {
  const dialog = $("#asset-dialog");
  if (!item) {
    if (dialog.open) dialog.close();
    return;
  }
  const focusedIdentity = dialog.contains(document.activeElement) ? String(document.activeElement?.dataset?.assetFocus || document.activeElement?.id || "") : "";
  const label = assetLabel(item);
  const stage = assetStage(item);
  const revisions = assetRevisionItems(item);
  const presentation = assetPresentation(item);
  const technical = assetTechnical(item);
  const provenance = technical.provenance && typeof technical.provenance === "object" ? technical.provenance : {};
  const creator = String(provenance.creator_label || provenance.source_label || technical.job_metadata?.creator_label || "—");
  const dimensions = Number(provenance.width) > 0 && Number(provenance.height) > 0 ? String(provenance.width) + " × " + String(provenance.height) : "—";
  const revisionMarkup = revisions.length > 1 ? '<section><h3>Revision history</h3><ol class="asset-revisions" aria-label="Revision history">' + revisions.map((revision) => '<li><strong>Revision ' + escapeHTML(assetTechnical(revision).revision || "—") + '</strong><span>' + escapeHTML(assetStateLabel(revision)) + '</span><time>' + escapeHTML(assetDate(revision)) + '</time></li>').join("") + '</ol></section>' : '';
  const requestMarkup = stage && technical.request_summary ? '<section class="asset-request"><h3>Request</h3><p>' + escapeHTML(technical.request_summary) + '</p><small>' + escapeHTML(stage.label + (stage.measured ? " · " + stage.percent + "% measured" : "")) + '</small></section>' : '';
  $("#asset-dialog-kind").textContent = assetTypeLabel(item);
  $("#asset-dialog-title").textContent = label;
  $("#asset-dialog-content").innerHTML = '<div class="asset-dialog-preview">' + assetImageMarkup(item, true) + '</div>' + (presentation.description ? '<p class="asset-description">' + escapeHTML(presentation.description) + '</p>' : '') + requestMarkup + '<dl class="asset-human-meta"><div><dt>Project</dt><dd>' + escapeHTML(assetProjectLabel(item)) + '</dd></div><div><dt>Status</dt><dd>' + escapeHTML(assetStateLabel(item)) + '</dd></div><div><dt>Created</dt><dd>' + escapeHTML(assetDate(item, "created")) + '</dd></div><div><dt>Updated</dt><dd>' + escapeHTML(assetDate(item)) + '</dd></div><div><dt>File size</dt><dd>' + escapeHTML(assetSize(item)) + '</dd></div><div><dt>Creator</dt><dd>' + escapeHTML(creator) + '</dd></div></dl>' + revisionMarkup + '<details class="asset-advanced"><summary>Advanced</summary><dl class="asset-advanced-meta"><div><dt>Immutable ID</dt><dd>' + escapeHTML(assetIdentity(item)) + '</dd></div><div><dt>Logical asset</dt><dd>' + escapeHTML(technical.logical_asset_id || "—") + '</dd></div><div><dt>MIME type</dt><dd>' + escapeHTML(technical.media_type || "—") + '</dd></div><div><dt>Dimensions</dt><dd>' + escapeHTML(dimensions) + '</dd></div><div><dt>Digest</dt><dd>' + escapeHTML(technical.digest || "—") + '</dd></div><div><dt>Revision</dt><dd>' + escapeHTML(technical.revision ?? "—") + '</dd></div><div><dt>Parent revision</dt><dd>' + escapeHTML(technical.parent_revision_id || "—") + '</dd></div><div><dt>Operation</dt><dd>' + escapeHTML(technical.operation_id || "—") + '</dd></div></dl></details>';
  const pending = state.assetMutationPending;
  const sameMutation = pending?.payload?.asset_id === assetIdentity(item);
  let note = state.assetProjection === "trash" ? "Purge unavailable · no retention policy is configured." : "Move eligible, revision-bound assets to recoverable Trash.";
  let controls = "";
  if (sameMutation && pending.pending) {
    note = "Saving this asset change…";
    controls = '<button class="quiet-button" type="button" disabled>Saving…</button>';
  } else if (sameMutation && pending.error) {
    note = pending.error;
    controls = '<button class="quiet-button" type="button" data-asset-mutation-retry data-asset-focus="mutation-retry">Retry</button>';
  } else if (state.assetConfirm?.assetId === assetIdentity(item)) {
    note = "Move this revision to Trash? You can restore it afterward.";
    controls = '<button class="quiet-button" type="button" data-asset-confirm-cancel data-asset-focus="confirm-cancel">Cancel</button><button class="danger-button" type="button" data-asset-confirm data-asset-focus="confirm-trash">Move to Trash</button>';
  } else if (state.assetProjection === "trash") {
    controls = '<button class="quiet-button" type="button" data-asset-action="restore" data-asset-id="' + escapeHTML(assetIdentity(item)) + '" data-asset-focus="restore">Restore</button><button class="quiet-button" type="button" disabled title="Purge is unavailable because no retention policy is configured">Purge unavailable</button>';
  } else {
    if (assetRetryEligible(item)) controls += '<button class="quiet-button" type="button" data-asset-action="retry" data-asset-id="' + escapeHTML(assetIdentity(item)) + '" data-asset-focus="retry">Retry generation</button>';
    controls += '<button class="quiet-button" type="button" data-asset-action="trash" data-asset-id="' + escapeHTML(assetIdentity(item)) + '" data-asset-focus="trash"' + (assetTrashEligible(item) ? "" : ' disabled title="Only admitted revision-bound assets can move to Trash"') + '>Move to Trash</button>';
  }
  $("#asset-dialog-footer").innerHTML = '<p class="asset-dialog-note" role="status">' + escapeHTML(note) + '</p><div class="asset-actions">' + controls + '<button class="primary-action" id="asset-dialog-done" type="button" data-asset-focus="done">Done</button></div>';
  if (focusedIdentity) requestAnimationFrame(() => {
    const target = focusedIdentity === "asset-dialog-done" ? $("#asset-dialog-done") : $('[data-asset-focus="' + CSS.escape(focusedIdentity) + '"]', dialog);
    (target || $("#asset-dialog-close"))?.focus({ preventScroll: true });
  });
}

function openAssetDialog(identity, trigger) {
  const item = assetItems().find((candidate) => assetIdentity(candidate) === identity);
  if (!item) return;
  state.selectedAssetIdentity = identity;
  state.assetTrigger = { element: trigger || null, identity };
  $$('[data-asset-card]').forEach((card) => card.classList.toggle("is-selected", card.dataset.assetCard === identity));
  $$('[data-asset-detail]').forEach((control) => {
    if (control.classList.contains("asset-image-button") || control.classList.contains("asset-list-main")) control.setAttribute("aria-current", String(control.dataset.assetDetail === identity));
  });
  renderAssetDialog(item);
  const dialog = $("#asset-dialog");
  if (!dialog.open) dialog.showModal();
  requestAnimationFrame(() => $("#asset-dialog-close").focus({ preventScroll: true }));
}

function closeAssetDialog() {
  const dialog = $("#asset-dialog");
  if (dialog.open) dialog.close();
}

function renderAssets() {
  const items = assetItems();
  if (!items.some((item) => assetIdentity(item) === state.selectedAssetIdentity)) state.selectedAssetIdentity = "";
  const selected = items.find((item) => assetIdentity(item) === state.selectedAssetIdentity) || null;
  const status = state.assetStatus === "loading" ? "Loading assets" : state.assetStatus === "refreshing" ? "Refreshing assets" : state.assetStatus === "stale" ? "Showing last received assets · refresh to retry" : state.assetStatus === "unavailable" ? "Assets unavailable · refresh to retry" : items.length ? items.length + (state.assetProjection === "trash" ? " trashed asset" : " asset") + (items.length === 1 ? "" : "s") : state.assetProjection === "trash" ? "Trash is empty" : "No assets in this scope";
  $("#assets-status").textContent = status;
  $$('[data-asset-projection]').forEach((button) => { const active = button.dataset.assetProjection === state.assetProjection; button.classList.toggle("is-selected", active); button.setAttribute("aria-pressed", String(active)); });
  $$('[data-asset-view]').forEach((button) => { const selectedView = button.dataset.assetView === state.assetView; button.classList.toggle("is-selected", selectedView); button.setAttribute("aria-pressed", String(selectedView)); });
  const gallery = $("#asset-gallery");
  gallery.classList.toggle("is-list", state.assetView === "list");
  gallery.setAttribute("aria-label", state.assetProjection === "trash" ? "Trashed assets" : state.assetView === "grid" ? "Asset image grid" : "Asset list");
  gallery.innerHTML = items.length ? items.map(state.assetView === "grid" ? assetGridMarkup : assetListMarkup).join("") : '<p class="empty-state">' + escapeHTML(state.assetStatus === "unavailable" ? state.assetError || "Asset inventory unavailable." : state.assetProjection === "trash" ? "Trash is empty." : "No assets are available in this project.") + '</p>';
  const undo = $("#asset-undo-toast");
  undo.hidden = !state.assetUndo;
  undo.innerHTML = state.assetUndo ? '<span><strong>' + escapeHTML(assetLabel(state.assetUndo.item)) + '</strong> moved to Trash.</span><button class="quiet-button" type="button" data-asset-undo>Undo</button><button class="icon-button" type="button" data-asset-undo-dismiss aria-label="Dismiss undo"><svg class="lucide" aria-hidden="true"><use href="#lucide-x"></use></svg></button>' : "";
  if ($("#asset-dialog").open) renderAssetDialog(selected);
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

function renderOverviewProjectCards() {
  const roster = savedProjectRoster();
  const host = $("#overview-project-cards");
  if (roster.state !== "KNOWN") {
    $("#overview-summary").textContent = "Project inventory unavailable";
    host.innerHTML = '<p class="empty-state overview-empty" role="status">Saved projects are unavailable. Refresh when the console can read the host project inventory.</p>';
    return;
  }
  $("#overview-summary").textContent = roster.projects.length ? String(roster.projects.length) + " saved project" + (roster.projects.length === 1 ? "" : "s") : "No saved projects";
  host.innerHTML = roster.projects.length ? roster.projects.map((project) => {
    const selected = state.projectId === project.id && !state.ctrlId;
    const statusLabel = project.status[0].toUpperCase() + project.status.slice(1);
    const ctrlLabel = project.ctrlIds.length ? String(project.ctrlIds.length) + " CTRL" + (project.ctrlIds.length === 1 ? "" : "s") : "No CTRL";
    const taskLabel = project.taskCount == null ? "—" : String(project.taskCount);
    return '<article class="overview-project-card panel' + (selected ? ' is-selected' : '') + '"><button class="overview-project-main" type="button" data-overview-project-id="' + escapeHTML(project.id) + '" aria-label="Open ' + escapeHTML(project.label) + '"><span class="scope-dot is-' + project.status + '" aria-hidden="true"></span><span><strong title="' + escapeHTML(project.label) + '">' + escapeHTML(project.label) + '</strong><small>' + escapeHTML(project.eligibility === "swarm_ctrl" ? "SWARM project" : "Saved project") + '</small></span><svg class="lucide" aria-hidden="true"><use href="#lucide-chevron-right"></use></svg></button><dl class="overview-project-facts"><div><dt>Status</dt><dd>' + escapeHTML(statusLabel) + '</dd></div><div><dt>CTRLs</dt><dd>' + escapeHTML(ctrlLabel) + '</dd></div><div><dt>Tasks</dt><dd' + (project.taskCount == null ? ' aria-label="UNKNOWN"' : '') + '>' + escapeHTML(taskLabel) + '</dd></div></dl></article>';
  }).join("") : '<p class="empty-state overview-empty" role="status">No saved projects are available.</p>';
}

function renderOverview() {
  const nodes = scopedNodes();
  renderOverviewMetrics();
  renderOverviewProjectCards();
  renderEvidenceGallery(nodes, "#overview-evidence-gallery", "#overview-evidence-note", 4);
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

const AGENT_COLOR_CATALOG = "AliceBlue:#F0F8FF,AntiqueWhite:#FAEBD7,Aqua:#00FFFF,Aquamarine:#7FFFD4,Azure:#F0FFFF,Beige:#F5F5DC,Bisque:#FFE4C4,Black:#000000,BlanchedAlmond:#FFEBCD,Blue:#0000FF,BlueViolet:#8A2BE2,Brown:#A52A2A,BurlyWood:#DEB887,CadetBlue:#5F9EA0,Chartreuse:#7FFF00,Chocolate:#D2691E,Coral:#FF7F50,CornflowerBlue:#6495ED,Cornsilk:#FFF8DC,Crimson:#DC143C,Cyan:#00FFFF,DarkBlue:#00008B,DarkCyan:#008B8B,DarkGoldenRod:#B8860B,DarkGray:#A9A9A9,DarkGreen:#006400,DarkKhaki:#BDB76B,DarkMagenta:#8B008B,DarkOliveGreen:#556B2F,DarkOrange:#FF8C00,DarkOrchid:#9932CC,DarkRed:#8B0000,DarkSalmon:#E9967A,DarkSeaGreen:#8FBC8F,DarkSlateBlue:#483D8B,DarkSlateGray:#2F4F4F,DarkTurquoise:#00CED1,DarkViolet:#9400D3,DeepPink:#FF1493,DeepSkyBlue:#00BFFF,DimGray:#696969,DodgerBlue:#1E90FF,FireBrick:#B22222,FloralWhite:#FFFAF0,ForestGreen:#228B22,Fuchsia:#FF00FF,Gainsboro:#DCDCDC,GhostWhite:#F8F8FF,Gold:#FFD700,GoldenRod:#DAA520,Gray:#808080,Green:#008000,GreenYellow:#ADFF2F,HoneyDew:#F0FFF0,HotPink:#FF69B4,IndianRed:#CD5C5C,Indigo:#4B0082,Ivory:#FFFFF0,Khaki:#F0E68C,Lavender:#E6E6FA,LavenderBlush:#FFF0F5,LawnGreen:#7CFC00,LemonChiffon:#FFFACD,LightBlue:#ADD8E6,LightCoral:#F08080,LightCyan:#E0FFFF,LightGoldenRodYellow:#FAFAD2,LightGray:#D3D3D3,LightGreen:#90EE90,LightPink:#FFB6C1,LightSalmon:#FFA07A,LightSeaGreen:#20B2AA,LightSkyBlue:#87CEFA,LightSlateGray:#778899,LightSteelBlue:#B0C4DE,LightYellow:#FFFFE0,Lime:#00FF00,LimeGreen:#32CD32,Linen:#FAF0E6,Magenta:#FF00FF,Maroon:#800000,MediumAquaMarine:#66CDAA,MediumBlue:#0000CD,MediumOrchid:#BA55D3,MediumPurple:#9370DB,MediumSeaGreen:#3CB371,MediumSlateBlue:#7B68EE,MediumSpringGreen:#00FA9A,MediumTurquoise:#48D1CC,MediumVioletRed:#C71585,MidnightBlue:#191970,MintCream:#F5FFFA,MistyRose:#FFE4E1,Moccasin:#FFE4B5,Navy:#000080,OldLace:#FDF5E6,Olive:#808000,OliveDrab:#6B8E23,Orange:#FFA500,OrangeRed:#FF4500,Orchid:#DA70D6,PaleGoldenRod:#EEE8AA,PaleGreen:#98FB98,PaleTurquoise:#AFEEEE,PaleVioletRed:#DB7093,PapayaWhip:#FFEFD5,PeachPuff:#FFDAB9,Peru:#CD853F,Pink:#FFC0CB,Plum:#DDA0DD,PowderBlue:#B0E0E6,Purple:#800080,RebeccaPurple:#663399,Red:#FF0000,RosyBrown:#BC8F8F,RoyalBlue:#4169E1,SaddleBrown:#8B4513,Salmon:#FA8072,SandyBrown:#F4A460,SeaGreen:#2E8B57,SeaShell:#FFF5EE,Sienna:#A0522D,Silver:#C0C0C0,SkyBlue:#87CEEB,SlateBlue:#6A5ACD,SlateGray:#708090,Snow:#FFFAFA,SpringGreen:#00FF7F,SteelBlue:#4682B4,Tan:#D2B48C,Teal:#008080,Thistle:#D8BFD8,Tomato:#FF6347,Turquoise:#40E0D0,Violet:#EE82EE,Wheat:#F5DEB3,White:#FFFFFF,WhiteSmoke:#F5F5F5,Yellow:#FFFF00,YellowGreen:#9ACD32".split(",").map((entry) => {
  const [name, hex] = entry.split(":");
  return { name, hex };
});

function agentColorRgb(hex) {
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(String(hex || ""));
  return match ? match.slice(1).map((value) => Number.parseInt(value, 16)) : null;
}

function closestAgentColorName(accent) {
  const target = agentColorRgb(accent) || agentColorRgb("#708090");
  return AGENT_COLOR_CATALOG.reduce((best, candidate) => {
    const rgb = agentColorRgb(candidate.hex);
    const distance = rgb.reduce((sum, value, index) => sum + (value - target[index]) ** 2, 0);
    return !best || distance < best.distance || (distance === best.distance && candidate.name.localeCompare(best.name) < 0) ? { ...candidate, distance } : best;
  }, null).name;
}

function romanAgentOrdinal(value) {
  if (value <= 1) return "";
  const numerals = [[10, "X"], [9, "IX"], [5, "V"], [4, "IV"], [1, "I"]];
  let remaining = Math.min(39, value);
  let result = "";
  numerals.forEach(([number, numeral]) => { while (remaining >= number) { result += numeral; remaining -= number; } });
  return result;
}

function agentRoleAssignment(node) {
  return (roleManifestProjection()?.assignments || [])
    .filter((assignment) => assignment.task_id === node?.id)
    .sort((left, right) => Number(right.event_seq || 0) - Number(left.event_seq || 0))[0] || null;
}

function agentRoleRecord(node) {
  const assignment = agentRoleAssignment(node);
  return assignment ? roleRecord(assignment.role_id) : null;
}

function agentProfession(node, role = agentRoleRecord(node)) {
  if (role) return roleDisplayName(role);
  const projected = String(node?.worker_role || "").trim();
  return projected && !["AGENT", "TASK", "CTRL", "LEAD", "DOER", "REVIEW"].includes(projected.toUpperCase()) ? humanize(projected) : "Role pending";
}

function agentExactBinding(node) {
  const project = currentWorkProjects().find((item) => item.id === node?.project_id);
  if (!project) return null;
  const structural = observedAgentRole(node);
  const candidates = structural === "CTRL" && project.ctrl_ids.includes(node.id)
    ? [node.id]
    : [...new Set((node?.controller_ids || []).filter((ctrlId) => project.ctrl_ids.includes(ctrlId)))];
  if (candidates.length !== 1) return null;
  const ctrl = runLogBindingForCtrl(candidates[0]);
  return ctrl ? { ...ctrl, agentId: runLogAgentId(node) } : null;
}

function activeAgentRecords() {
  if (currentWorkScopeUnavailable()) return [];
  const projects = new Map(savedProjectRoster().projects.map((project) => [project.id, project]));
  const roleRank = { CTRL: 0, LEAD: 1, DOER: 2 };
  const records = scopedNodes()
    .filter((node) => observedAgentRole(node) && ["active", "in_progress"].includes(String(node.status || "").toLowerCase()) && projects.has(node.project_id))
    .map((node) => {
      const role = agentRoleRecord(node);
      const profession = agentProfession(node, role);
      const accent = /^#[0-9a-f]{6}$/i.test(role?.accent || "") ? role.accent : "#708090";
      return { node, role, assignment: agentRoleAssignment(node), profession, structuralRole: observedAgentRole(node), accent, baseColorName: closestAgentColorName(accent), binding: agentExactBinding(node), project: projects.get(node.project_id) };
    })
    .filter((record) => record.binding)
    .sort((left, right) => left.project.label.localeCompare(right.project.label) || roleRank[left.structuralRole] - roleRank[right.structuralRole] || String(left.node.id).localeCompare(String(right.node.id)));
  const ordinals = new Map();
  return records.map((record) => {
    const key = record.baseColorName + "|" + record.profession;
    const ordinal = (ordinals.get(key) || 0) + 1;
    ordinals.set(key, ordinal);
    const suffix = romanAgentOrdinal(ordinal);
    return { ...record, presentationName: record.baseColorName + (suffix ? " " + suffix : "") + " — " + record.profession };
  });
}

function messageRecipients() {
  return activeAgentRecords()
    .filter((record) => ["CTRL", "LEAD"].includes(record.structuralRole))
    .filter((record) => state.projectId === "all" || record.binding?.projectId === state.projectId)
    .map((record) => ({
      id: record.node.id,
      projectId: record.binding.projectId,
      targetCtrlId: record.binding.ctrlId,
      structuralRole: record.structuralRole,
      label: record.presentationName,
      projectLabel: record.project.label,
    }));
}

function selectedMessageRecipient(recipients = messageRecipients()) {
  const selected = recipients.find((recipient) => recipient.id === state.messageRecipientId);
  if (selected) return selected;
  const preferred = recipients.find((recipient) => recipient.structuralRole === "CTRL") || recipients[0] || null;
  state.messageRecipientId = preferred?.id || "";
  return preferred;
}

function messageImplicitContext(recipient = selectedMessageRecipient()) {
  if (!recipient) return null;
  const projectView = state.projectId !== "all" && state.view === "overview" ? state.projectTab : state.view;
  return {
    type: "swarm.project_view_action",
    schema_version: 1,
    action_kind: "send_feedback",
    project_id: recipient.projectId,
    target_ctrl_id: recipient.targetCtrlId,
    recipient_id: recipient.id,
    view_id: projectView,
    screen_id: state.view,
    state_id: state.view === "overview" && state.projectId !== "all" ? state.projectTab : "default",
  };
}

function messageReceiptPresentation(result) {
  const code = String(result?.result_code || result?.status || "").toUpperCase();
  if (["ACKNOWLEDGED", "REPLAYED"].includes(code) && result?.request_id && result?.action_digest && result?.result_event_id && result?.result_event_digest) {
    return { status: "sent", clearDraft: true };
  }
  if (["STALE", "CONFLICT"].includes(code)) return { status: "conflict", clearDraft: false };
  return { status: "failed", clearDraft: false };
}

function messageStatusCopy(recipient = selectedMessageRecipient()) {
  if (!recipient) return "No authorized CTRL or LEAD is available in this project scope.";
  if (state.messageStatus === "pending") return "Pending · waiting for SWARM acknowledgement.";
  if (state.messageStatus === "sent") return "Sent to " + recipient.label + ".";
  if (state.messageStatus === "conflict") return state.messageError || "The project context changed. Review the message and retry.";
  if (state.messageStatus === "failed") return state.messageError || "The message was not acknowledged. Your draft is still here.";
  return MESSAGE_CONNECTOR_UNAVAILABLE;
}

function renderMessageComposer() {
  const panel = $("#message-composer");
  if (!panel) return;
  const recipients = messageRecipients();
  const recipient = selectedMessageRecipient(recipients);
  panel.hidden = !state.messageOpen;
  $("#message-recipient").innerHTML = recipients.length
    ? recipients.map((item) => '<option value="' + escapeHTML(item.id) + '"' + (item.id === recipient?.id ? " selected" : "") + '>' + escapeHTML(item.label + " · " + item.structuralRole + " · " + item.projectLabel) + '</option>').join("")
    : '<option value="">No authorized recipients</option>';
  $("#message-recipient").disabled = !recipients.length || state.messageStatus === "pending";
  const draft = $("#message-draft");
  if (draft.value !== state.messageDraft) draft.value = state.messageDraft;
  draft.disabled = state.messageStatus === "pending";
  const send = $("#message-send");
  send.disabled = true;
  send.setAttribute("aria-disabled", "true");
  $("#message-retry").hidden = !["failed", "conflict"].includes(state.messageStatus);
  $("#message-retry").disabled = true;
  $("#message-status").textContent = messageStatusCopy(recipient);
  $("#message-launcher").setAttribute("aria-expanded", String(state.messageOpen));
  $("#mobile-message-action").setAttribute("aria-expanded", String(state.messageOpen));
  panel.dataset.contextAvailable = String(Boolean(messageImplicitContext(recipient)));
}

function openMessageComposer(trigger) {
  state.messageTrigger = trigger || state.messageTrigger;
  state.messageOpen = true;
  renderMessageComposer();
  requestAnimationFrame(() => (selectedMessageRecipient() ? $("#message-draft") : $("#message-close"))?.focus({ preventScroll: true }));
}

function closeMessageComposer(restoreFocus = true) {
  state.messageOpen = false;
  renderMessageComposer();
  if (restoreFocus) state.messageTrigger?.focus({ preventScroll: true });
  state.messageTrigger = null;
}

async function sendMessageFromComposer() {
  state.messageStatus = "unavailable";
  state.messageError = MESSAGE_CONNECTOR_UNAVAILABLE;
  renderMessageComposer();
}

function agentProgress(record) {
  if (!record.binding) return null;
  if (state.projectId === "all") {
    const observed = state.overview?.progress?.controllers?.[record.binding.ctrlId];
    const freshness = String(observed?.freshness?.state || "").toLowerCase();
    const progress = observed?.progress;
    const percent = progress?.percent;
    const completed = progress?.completed_units;
    const total = progress?.total_units;
    if (freshness === "fresh" && Number.isFinite(percent) && percent >= 0 && percent <= 100 && Number.isInteger(completed) && Number.isInteger(total) && completed >= 0 && total > 0 && completed <= total) {
      return { percent, label: String(completed) + " of " + String(total) + " accepted milestones" };
    }
    return null;
  }
  if (state.projectId !== record.binding.projectId || state.projectProgressStatus !== "current") return null;
  const projection = projectProgressQueueProjection(selectedProjectProgress());
  if (!projection || projection.status !== "CURRENT") return null;
  const row = projection.segments.flatMap((segment) => segment.rows).find((item) => item.task_id === record.node.id && item.scope_binding?.ctrl_id === record.binding.ctrlId);
  const progress = progressQueueRowPresentation(row)?.progress;
  const percent = Number(progress?.percent);
  return progress?.state === "KNOWN" && Number.isFinite(percent) && percent >= 0 && percent <= 100 ? { percent, label: String(progress.completed_milestones) + " of " + String(progress.total_milestones) + " accepted milestones" } : null;
}

function agentAvatarMarkup(record) {
  return '<span class="agent-avatar-token" style="--agent-accent:' + escapeHTML(record.accent) + '">' + roleAvatar(record.role) + '</span>';
}

function agentProgressMarkup(record) {
  const progress = agentProgress(record);
  if (!progress) return '<span class="agent-progress-unknown" aria-label="Progress UNKNOWN">— <small>UNKNOWN</small></span>';
  return '<div class="agent-progress"><div role="progressbar" aria-label="' + escapeHTML(record.presentationName + " progress") + '" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + escapeHTML(progress.percent) + '" aria-valuetext="' + escapeHTML(progress.label) + '"><i style="width:' + escapeHTML(progress.percent) + '%"></i></div><small>' + escapeHTML(Math.round(progress.percent) + "% · " + progress.label) + '</small></div>';
}

function agentTableRowMarkup(record) {
  const status = statusLabel(record.node);
  const updated = observedTimestampMs(record.node.updated_at || record.node.generated_at);
  const updatedText = updated > 0 ? formatRelative(updated) : "UNKNOWN";
  const bindingState = record.binding ? record.binding.ctrlId : "Binding unavailable";
  return '<button class="agent-table-row" type="button" role="row" data-agent-detail="' + escapeHTML(record.node.id) + '" data-agent-project="' + escapeHTML(record.node.project_id) + '" data-agent-ctrl="' + escapeHTML(record.binding?.ctrlId || "") + '" aria-label="Open ' + escapeHTML(record.presentationName + ", " + record.node.artifact) + '"><span class="agent-table-agent" role="cell" data-label="Agent">' + agentAvatarMarkup(record) + '<span><strong>' + escapeHTML(record.presentationName) + '</strong><small>' + escapeHTML(record.profession + " · " + record.structuralRole + " · " + bindingState) + '</small></span></span><span class="agent-table-task" role="cell" data-label="Current task"><strong>' + escapeHTML(record.node.artifact || "Named task unavailable") + '</strong><small>' + escapeHTML(record.node.id) + '</small></span><span role="cell" data-label="Project">' + escapeHTML(record.project.label) + '</span><span role="cell" data-label="Status"><span class="state-pill ' + escapeHTML(status[1]) + '">' + escapeHTML(status[0]) + '</span></span><span role="cell" data-label="Progress">' + agentProgressMarkup(record) + '</span><time role="cell" data-label="Updated" datetime="' + escapeHTML(updated > 0 ? new Date(updated).toISOString() : "") + '"' + (updated > 0 ? "" : ' aria-label="Last update UNKNOWN"') + '>' + escapeHTML(updatedText) + '</time><span class="agent-table-chevron" role="cell" aria-hidden="true"><svg class="lucide"><use href="#lucide-chevron-right"></use></svg></span></button>';
}

function selectedAgentRecord() {
  const selection = state.runLogAgent;
  return selection ? activeAgentRecords().find((record) => record.binding?.projectId === selection.projectId && record.binding?.ctrlId === selection.ctrlId && record.binding?.agentId === selection.agentId) || null : null;
}

function selectedAgentUpdates(record) {
  if (!record?.binding) return [];
  const exact = state.runLogs.get(runLogBindingKey(record.binding))?.items || [];
  const ctrl = state.runLogs.get(runLogBindingKey({ projectId: record.binding.projectId, ctrlId: record.binding.ctrlId, agentId: "" }))?.items || [];
  const items = [...exact, ...ctrl].filter((item) => item.task_id === record.node.id || item.agent_id === record.binding.agentId);
  return [...new Map(items.map((item) => [runLogItemIdentity(item), item])).values()].sort((left, right) => Number(right.event_seq) - Number(left.event_seq)).slice(0, 6);
}

function renderAgentDetail() {
  const record = selectedAgentRecord();
  if (!record) return false;
  const dialog = $("#agent-detail-dialog");
  const assignmentVersion = record.assignment?.manifest_version || record.role?.active_version || "UNKNOWN";
  const updates = selectedAgentUpdates(record);
  $("#agent-detail-title").textContent = record.presentationName;
  $("#agent-detail-content").innerHTML = '<section class="agent-detail-identity">' + agentAvatarMarkup(record) + '<div><span class="state-pill is-active">In progress</span><h3>' + escapeHTML(record.presentationName) + '</h3><p>' + escapeHTML(record.structuralRole + " structure · " + record.profession + " profession") + '</p></div></section><dl class="agent-detail-facts"><div><dt>Current task</dt><dd>' + escapeHTML(record.node.artifact || "Named task unavailable") + '</dd></div><div><dt>Project</dt><dd>' + escapeHTML(record.project.label) + '</dd></div><div><dt>CTRL binding</dt><dd>' + escapeHTML(record.binding?.ctrlId || "UNKNOWN") + '</dd></div><div><dt>Role template</dt><dd>' + escapeHTML(record.profession + " · " + assignmentVersion) + '</dd></div></dl><section class="agent-detail-section"><h3>Material updates</h3>' + (updates.length ? '<ol>' + updates.map((item) => { const observed = Number(item.observed_at_ms); const datetime = Number.isFinite(observed) && observed > 0 ? new Date(observed).toISOString() : ""; return '<li><time datetime="' + escapeHTML(datetime) + '">' + escapeHTML(formatRelative(observed)) + '</time><span>' + escapeHTML(item.summary) + '</span></li>'; }).join("") + '</ol>' : '<p class="empty-state">No retained material updates are available for this agent yet.</p>') + '</section><section class="agent-detail-section"><h3>This agent only</h3><p>No agent-specific instruction augmentation was supplied by the server projection. The role template remains read-only here.</p></section>';
  return dialog.open;
}

function openAgentDetail(trigger) {
  const record = activeAgentRecords().find((item) => item.node.id === trigger?.dataset.agentDetail && item.node.project_id === trigger?.dataset.agentProject);
  if (!record?.binding) return;
  state.runLogAgent = { ...record.binding, label: record.presentationName };
  state.agentUpdatesFilter = "selected";
  state.agentDetailTrigger = trigger;
  renderAgents();
  const dialog = $("#agent-detail-dialog");
  renderAgentDetail();
  if (!dialog.open) dialog.showModal();
  requestAnimationFrame(() => $("#agent-detail-close")?.focus({ preventScroll: true }));
  refreshRunLogs().then(() => { renderRunLogSurfaces(); if (dialog.open) renderAgentDetail(); });
}

function closeAgentDetail(restoreFocus = true) {
  const dialog = $("#agent-detail-dialog");
  if (dialog.open) dialog.close();
  if (!restoreFocus) return;
  const trigger = state.agentDetailTrigger;
  const replacement = trigger?.dataset.agentDetail
    ? $$('[data-agent-detail]').find((candidate) => candidate.dataset.agentDetail === trigger.dataset.agentDetail && candidate.dataset.agentProject === trigger.dataset.agentProject)
    : null;
  (trigger?.isConnected ? trigger : replacement || $("#agents-heading"))?.focus?.({ preventScroll: true });
}

function renderAgentUpdateControls() {
  const selectedAvailable = Boolean(currentRunLogAgent());
  $$('[data-agent-updates-filter]').forEach((button) => {
    const selected = button.dataset.agentUpdatesFilter === state.agentUpdatesFilter;
    button.classList.toggle("is-selected", selected);
    button.setAttribute("aria-pressed", String(selected));
    button.disabled = button.dataset.agentUpdatesFilter === "selected" && !selectedAvailable;
  });
  const pause = $("#agent-updates-pause");
  pause.textContent = state.agentUpdatesPaused ? "Resume" : "Pause";
  pause.setAttribute("aria-pressed", String(state.agentUpdatesPaused));
}

function renderAgentTable() {
  const unavailable = currentWorkScopeUnavailable();
  const records = unavailable ? [] : activeAgentRecords();
  const projects = new Set(records.map((record) => record.project.id));
  $("#agents-summary").textContent = unavailable ? "Active-agent inventory unavailable" : records.length + " active agent" + (records.length === 1 ? "" : "s") + " across " + projects.size + " project" + (projects.size === 1 ? "" : "s");
  $("#agents-table-status").textContent = unavailable ? "Accepted project and CTRL bindings are unavailable." : state.projectId === "all" ? "All projects" : scopeLabel();
  $("#agent-table-body").innerHTML = unavailable
    ? '<p class="empty-state agents-empty" role="status">Active agents are unavailable until SWARM receives a current project and CTRL projection.</p>'
    : records.length ? records.map(agentTableRowMarkup).join("") : '<p class="empty-state agents-empty" role="status">No active CTRL, LEAD, or DOER is available in this project scope.</p>';
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
  return role?.name || role?.id || "Unknown role";
}

function safeRoleAvatarURL(value, expectedDigest) {
  const url = String(value || "");
  const apiMatch = url.match(/^\/api\/assets\/([a-z0-9_-]+)\/preview\?digest=([0-9a-f]{64})$/i);
  if (apiMatch) return apiMatch[2].toLowerCase() === expectedDigest ? url : "";
  return /^\/assets\/role-avatars\/[a-z0-9_]+\.png$/i.test(url) ? url : "";
}

function retainedRoleAvatar(role) {
  const digest = String(role?.avatar_asset_digest || "").toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(digest)) return null;
  const embedded = role?.avatar && typeof role.avatar === "object" ? role.avatar : null;
  const embeddedDigest = String(embedded?.digest || "").toLowerCase();
  const embeddedURL = safeRoleAvatarURL(embedded?.url, digest);
  if (embeddedDigest === digest && embedded?.state === "AVAILABLE" && embeddedURL) return { digest, url: embeddedURL };
  const asset = assetItems().find((item) => String(assetTechnical(item).digest || "").toLowerCase() === digest);
  const preview = asset?.preview && typeof asset.preview === "object" ? asset.preview : null;
  const previewURL = safeRoleAvatarURL(preview?.url, digest);
  return preview?.state === "AVAILABLE" && previewURL ? { digest, url: previewURL } : null;
}

function roleAvatar(role) {
  const accent = /^#[0-9a-f]{6}$/i.test(role?.accent || "") ? role.accent : "#8f9db0";
  const displayName = roleDisplayName(role);
  const avatar = retainedRoleAvatar(role);
  if (avatar) return '<span class="role-avatar has-image" style="--role-accent:' + escapeHTML(accent) + '" role="img" aria-label="' + escapeHTML(displayName + " mascot avatar") + '"><img loading="lazy" decoding="async" src="' + escapeHTML(avatar.url) + '" alt=""></span>';
  return '<span class="role-avatar is-pending" style="--role-accent:' + escapeHTML(accent) + '" role="img" aria-label="Avatar pending for ' + escapeHTML(displayName) + '"><span>Pending</span></span>';
}

function roleHasRetainedAvatar(role) { return Boolean(retainedRoleAvatar(role)); }

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

function roleTextList(items, empty) {
  return Array.isArray(items) && items.length ? '<ul>' + items.map((item) => '<li>' + escapeHTML(item) + '</li>').join("") + '</ul>' : '<p class="role-specializations-empty">' + escapeHTML(empty) + '</p>';
}

function roleInstructionsMarkup(items) {
  const instructions = Array.isArray(items) ? items.map((item) => String(item || "").trim()).filter(Boolean) : [];
  if (!instructions.length) return '<p class="role-specializations-empty">No instructions.</p>';
  const preview = instructions.slice(0, 3);
  const remaining = instructions.slice(3);
  return '<div class="role-instruction-preview">' + roleTextList(preview, "No instructions.") + (remaining.length ? '<details><summary>Show all ' + escapeHTML(instructions.length) + ' instructions</summary>' + roleTextList(remaining, "") + '</details>' : '') + '</div>';
}

function roleChooserMarkup(role, match, selected) {
  const displayName = roleDisplayName(role);
  const sourceLabel = roleSourceLabel(role);
  return '<button class="role-choice' + (selected ? ' is-selected' : '') + '" data-role-select="' + escapeHTML(role.id) + '" id="role-choice-' + escapeHTML(role.id) + '" role="option" aria-label="' + escapeHTML(displayName + ', ' + sourceLabel) + '" aria-selected="' + String(selected) + '" aria-controls="role-library-detail" tabindex="' + (selected ? '0' : '-1') + '" type="button">' + roleAvatar(role) + '<span><strong>' + escapeHTML(displayName) + '</strong><small class="role-choice-source">' + escapeHTML(sourceLabel) + '</small>' + (match.label ? '<em>' + escapeHTML(match.label) + '</em>' : '') + '</span></button>';
}

function roleDetailMarkup(role, match = { label: "" }) {
  if (!role) return '<p class="empty-state">Choose a role to inspect its server-owned manifest.</p>';
  const displayName = roleDisplayName(role);
  const editAllowed = roleCanMutate("ROLE_MANIFEST_REVISE");
  return '<header class="role-detail-head">' + roleAvatar(role) + '<div><p class="eyebrow">' + escapeHTML(roleSourceLabel(role)) + '</p><h3 id="role-detail-title">' + escapeHTML(displayName) + '</h3><p>Profession · not authority</p></div><div class="role-detail-actions"><button class="icon-button" data-role-action="generate-avatar" type="button" disabled aria-label="Generate avatar" title="Generate avatar unavailable"><svg class="lucide" aria-hidden="true"><use href="#lucide-sparkles"></use></svg></button><button class="icon-button" data-role-action="edit" data-role-id="' + escapeHTML(role.id) + '" type="button" aria-label="Edit ' + escapeHTML(displayName) + '" title="Edit role"' + (editAllowed ? "" : ' disabled') + '><svg class="lucide" aria-hidden="true"><use href="#lucide-pencil"></use></svg></button></div></header>' + (match.label ? '<p class="role-match">' + escapeHTML(match.label) + '</p>' : '') + '<div class="role-detail-sections"><section><h4>Purpose</h4><p class="role-detail-copy">' + escapeHTML(role.purpose || "Purpose unavailable.") + '</p></section><section><h4>Owns</h4>' + roleTextList(role.owns, "No owned surface declared.") + '</section><section><h4>Instructions</h4>' + roleInstructionsMarkup(role.instructions) + '</section><section><h4>Current owners</h4>' + roleAssignmentsMarkup(role.id) + '</section><section><h4>Specializations</h4><div>' + roleSpecializationsMarkup(role) + '<small>Metadata only · no authority transfer.</small></div></section><section><h4>Default skills</h4>' + roleTextList(role.default_skills, "No default skills.") + '</section><section><h4>Boundaries</h4>' + roleTextList(role.boundaries, "No boundaries declared.") + '</section></div><footer><span>' + escapeHTML(roleHasRetainedAvatar(role) ? "Retained avatar" : "Avatar pending admission") + '</span><span>Active tasks retain their accepted role version.</span></footer>';
}

function focusRoleChoice(roleId) {
  if (!roleId) return;
  const choice = $('[data-role-select="' + CSS.escape(roleId) + '"]');
  choice?.focus({ preventScroll: true });
  choice?.scrollIntoView({ block: "nearest", inline: "nearest" });
}

function selectRoleChoice(roleId) {
  state.selectedRoleId = roleId;
  renderRoleLibrary(roleId);
}

function roleGridColumnCount(grid) {
  const columns = getComputedStyle(grid).gridTemplateColumns.trim();
  return Math.max(1, columns ? columns.split(/\s+/).length : 1);
}

function roleGridTargetIndex(key, index, count, columns) {
  if (!count || index < 0) return index;
  if (key === "Home") return 0;
  if (key === "End") return count - 1;
  if (key === "ArrowUp") return Math.max(0, index - columns);
  if (key === "ArrowDown") return Math.min(count - 1, index + columns);
  if (key === "ArrowLeft") return index % columns ? index - 1 : index;
  if (key === "ArrowRight") return index % columns < columns - 1 && index + 1 < count ? index + 1 : index;
  return index;
}

function renderRoleLibrary(focusRoleId = "") {
  const projection = roleManifestProjection();
  const roles = roleCurrentRecords(projection);
  const filtered = roleFilterRecords(roles, state.roleSearch, state.roleTypes, state.roleSearchFields);
  const grid = $("#role-library-grid");
  const focusedRoleId = grid.contains(document.activeElement) ? document.activeElement.closest("[data-role-select]")?.dataset.roleSelect || "" : "";
  const create = $("#role-create");
  create.hidden = false;
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
  grid.innerHTML = filtered.length ? filtered.map(({ role, match }) => roleChooserMarkup(role, match, role.id === state.selectedRoleId)).join("") : '<p class="empty-state">No roles match these filters. Clear the search or filters to see the server roster.</p>';
  $("#role-library-detail").innerHTML = roleDetailMarkup(selected?.role, selected?.match);
  focusRoleChoice(focusRoleId || focusedRoleId);
}

function renderAgents() {
  renderAgentTable();
  renderAgentUpdateControls();
  const dialog = $("#agent-detail-dialog");
  if (dialog?.open && !renderAgentDetail()) closeAgentDetail();
}

function renderRoles() {
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
  state.roleEditorTrigger = trigger?.dataset.roleAction === "edit"
    ? { action: "edit", roleId: trigger.dataset.roleId || roleId }
    : trigger?.dataset.roleAction === "create" ? { action: "create" } : null;
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

function roleEditorReturnTarget(origin) {
  const trigger = origin?.action === "edit" && origin.roleId
    ? $('[data-role-action="edit"][data-role-id="' + CSS.escape(origin.roleId) + '"]')
    : origin?.action === "create" ? $("#role-create") : null;
  if (trigger && !trigger.disabled && !trigger.hidden) return trigger;
  return $("#role-search") || $("#tab-roles");
}

function restoreRoleEditorFocus() {
  const origin = state.roleEditorTrigger;
  state.roleEditorTrigger = null;
  requestAnimationFrame(() => {
    const target = roleEditorReturnTarget(origin);
    target?.focus({ preventScroll: true });
    target?.scrollIntoView({ block: "nearest", inline: "nearest" });
  });
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

function configValue(key) {
  return key.split(".").reduce((value, part) => value && typeof value === "object" ? value[part] : undefined, state.config?.settings);
}

function configDescriptor(key) {
  const rows = Array.isArray(state.config?.descriptors) ? state.config.descriptors : [];
  return rows.find((row) => row?.key === key) || null;
}

function settingsConfigEditable(key) {
  return currentSettingsScope().type === "global" && state.configStatus === "current" && configEditable(key) && !state.settingsSaving;
}

function settingsDraftValue(key, fallback) {
  return state.settingsDraft.has(key) ? state.settingsDraft.get(key) : (configValue(key) ?? fallback);
}

function stageSettingsDraft(key, value) {
  if (!settingsConfigEditable(key)) return false;
  if (Object.is(configValue(key), value)) state.settingsDraft.delete(key);
  else state.settingsDraft.set(key, value);
  state.settingsSaveError = "";
  state.settingsSaveMessage = "";
  return true;
}

function settingsDraftChanges() {
  return Object.fromEntries(state.settingsDraft.entries());
}

function settingsSwitch(key, value, label, help, options = {}) {
  const editable = options.editable ?? settingsConfigEditable(key);
  const checked = value === (options.trueValue ?? true);
  const badge = options.badge ? '<span class="settings-control-badge">' + escapeHTML(options.badge) + '</span>' : '';
  return '<section class="settings-essential-control"><div><span class="settings-control-title"><strong>' + escapeHTML(label) + '</strong>' + badge + '</span><small>' + escapeHTML(help) + '</small></div><label class="settings-switch"><input type="checkbox" data-settings-draft-key="' + escapeHTML(key) + '"' + (options.trueValue !== undefined ? ' data-true-value="' + escapeHTML(options.trueValue) + '" data-false-value="' + escapeHTML(options.falseValue) + '"' : '') + (checked ? ' checked' : '') + (editable ? '' : ' disabled') + ' aria-label="' + escapeHTML(label) + '"><span aria-hidden="true"></span></label>' + (editable ? '' : '<em>' + escapeHTML(options.unavailable || 'Managed by the current configuration.') + '</em>') + '</section>';
}

function descriptorBooleanSwitch(key, label, help, options = {}) {
  const descriptor = configDescriptor(key);
  const knownBoolean = descriptor?.classification === "exposed"
    && descriptor?.type === "boolean"
    && descriptor?.value_state === "KNOWN"
    && typeof descriptor?.current === "boolean";
  const value = knownBoolean ? settingsDraftValue(key, descriptor.current) : false;
  return settingsSwitch(key, value, label, help, {
    ...options,
    editable: knownBoolean && descriptor.editable === true && settingsConfigEditable(key),
    unavailable: knownBoolean
      ? (options.unavailable || "Read-only in the current scope.")
      : (options.unsupported || "Unavailable in the current configuration."),
  });
}

function settingsSpeedMarkup() {
  const key = "execution.fast_mode";
  const fast = settingsDraftValue(key, false) === true;
  const editable = settingsConfigEditable(key);
  const choice = (label, selected, value, disabled = false) => '<label><input type="radio" name="settings-speed" data-settings-draft-key="' + key + '" data-config-value="' + String(value) + '"' + (selected ? ' checked' : '') + ((!editable || disabled) ? ' disabled' : '') + ' aria-label="' + escapeHTML(label) + '"><span>' + escapeHTML(label) + '</span></label>';
  return '<fieldset class="settings-segmented"><legend>Speed</legend><div>' + choice("Default", !fast, false) + choice("Fast", fast, true) + choice("Ultrafast", false, true, true) + '</div><small>' + escapeHTML(editable ? 'Ultrafast is unavailable until SWARM exposes an accepted mode.' : 'Speed is read-only in this scope.') + '</small></fieldset>';
}

function settingsTaskLifeMarkup() {
  const labels = ["Short", "Medium", "Balanced", "Long", "Unlimited"];
  const tooltip = "Short clears context sooner to keep work efficient, with more handovers. Balanced hands over when task efficiency begins to drop. Long reduces handovers, while a larger context can become less efficient over time.";
  return '<section class="settings-task-life"><div class="settings-task-life-head"><strong>Task life</strong><details><summary class="icon-button" aria-label="About task life"><span aria-hidden="true">i</span></summary><div role="tooltip">' + escapeHTML(tooltip) + '</div></details></div><input type="range" min="0" max="4" step="1" value="2" disabled aria-label="Task life" aria-valuetext="Balanced — unavailable"><div aria-hidden="true">' + labels.map((label) => '<span>' + label + '</span>').join('') + '</div><small>Task life is unavailable until SWARM exposes the accepted five-step setting.</small></section>';
}

function settingsContextPresentation(scope, selectedCtrl, setting) {
  if (selectedCtrl) return { title: publicLabel(selectedCtrl.project, "Project") + " / " + ctrlLabel(selectedCtrl), note: setting?.customized ? "Custom CTRL values override global defaults." : "Inherits global defaults." };
  if (scope.type === "project") return { title: scopeLabel(), note: "Project values inherit global defaults until an accepted override is supplied." };
  return { title: "Global defaults", note: "Changes apply wherever a project has not overridden them." };
}

function renderConfigEditor() {
  const dialog = $("#config-editor-dialog");
  if (!dialog) return;
  const scope = currentSettingsScope();
  const context = settingsContextPresentation(scope, selectedSettingsCtrl(), state.ctrlSettings);
  $("#config-editor-context").textContent = context.title;
  $("#config-editor-source").textContent = state.config?.exists ? "Server-owned configuration" : "Unavailable";
  $("#config-editor-revision").textContent = "Unavailable";
  $("#config-editor-validation").textContent = state.configStatus === "current" ? "Text authority unavailable" : "Configuration unavailable";
  $("#config-editor-warning").hidden = scope.type === "global";
  $("#config-editor-text").value = "";
  $("#config-editor-text").placeholder = "Exact config text is unavailable from this server.";
  $("#config-editor-text").readOnly = true;
  $("#config-editor-status").textContent = "SWARM can read individual settings, but this server does not expose validated config text or revision-safe text saves.";
  $("#config-editor-save").disabled = true;
  $("#config-editor-reset").disabled = true;
}

function openConfigEditor(trigger) {
  state.configEditorTrigger = trigger || document.activeElement;
  renderConfigEditor();
  const dialog = $("#config-editor-dialog");
  if (!dialog.open) dialog.showModal();
  requestAnimationFrame(() => $("#config-editor-close").focus({ preventScroll: true }));
}

function closeConfigEditor() {
  const dialog = $("#config-editor-dialog");
  if (dialog.open) dialog.close();
}

async function saveSettingsDraft() {
  const changes = settingsDraftChanges();
  if (!Object.keys(changes).length || state.settingsSaving) return false;
  state.settingsSaving = true;
  state.settingsSaveError = "";
  state.settingsSaveMessage = "Saving…";
  renderSettings();
  try {
    await saveConfigMutation(changes);
    state.settingsDraft.clear();
    state.settingsSaveMessage = "Saved";
    return true;
  } catch (error) {
    state.settingsSaveError = error.message || "Settings could not be saved.";
    state.settingsSaveMessage = "Changes not saved";
    return false;
  } finally {
    state.settingsSaving = false;
    renderSettings();
    requestAnimationFrame(() => $("#settings-save")?.focus({ preventScroll: true }));
  }
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
  const automation = state.config?.settings?.automation || {};
  const context = settingsContextPresentation(scope, selectedCtrl, setting);
  const autoMode = settingsDraftValue("automation.mode", automation.mode || "manual");
  const pending = state.settingsDraft.size;
  const saveStatus = state.settingsSaveError || state.settingsSaveMessage || (pending ? pending + " unsaved change" + (pending === 1 ? "" : "s") : "All changes saved");
  $("#settings-grid").innerHTML =
    '<section class="panel settings-essentials settings-wide" id="settings-essentials" tabindex="-1"><header class="settings-essentials-head"><div><p class="eyebrow">Essentials</p><h3>How SWARM runs your work</h3><p>Keep the defaults clear. Exact configuration remains server-owned.</p></div><label class="settings-scope-control">Applies to<select id="settings-scope">' + settingsScopeOptions() + '</select></label></header><div class="settings-context"><strong>' + escapeHTML(context.title) + '</strong><span>' + escapeHTML(context.note) + '</span></div><div class="settings-toggle-grid">' +
      settingsSwitch("automation.mode", autoMode, "Auto mode", "SWARM keeps eligible work moving until it needs you.", { trueValue: "standard", falseValue: "manual", unavailable: scope.type === "global" ? "Managed by the current configuration." : "Edit global defaults or use an accepted override." }) +
      descriptorBooleanSwitch("monitoring.auto_health_enabled", "Auto fix", "SWARM attempts to recover from issues automatically. This may start repair tasks and increase usage.", { unsupported: "Unavailable. Health checks remain active; no repair is started." }) +
      descriptorBooleanSwitch("execution.usage_saver", "Usage Saver", "Smart routing can reduce usage.", { badge: "Experimental", unsupported: "Unavailable until the canonical setting is exposed." }) + '</div><div class="settings-run-controls">' + settingsSpeedMarkup() + settingsTaskLifeMarkup() + '</div><div class="guided-tour-setting"><span><strong>Guided tour</strong><small>Replay the current SWARM introduction.</small></span><button class="quiet-button" data-setting-action="replay-tour" type="button">Replay tour</button></div></section>' +
    '<section class="panel settings-config-entry settings-wide" id="settings-advanced"><div><p class="eyebrow">Configuration</p><h3>Edit config</h3><p>Review the exact source, inheritance, and validation state in one place.</p><small>Server-owned source · revision unavailable · text authority unavailable</small></div><button class="quiet-button" id="settings-edit-config" data-setting-action="edit-config" type="button">Edit config</button></section>' +
    '<footer class="settings-save-bar settings-wide' + (state.settingsSaveError ? ' is-error' : '') + '" aria-live="polite"><p><strong>' + escapeHTML(saveStatus) + '</strong><span>' + escapeHTML(pending ? "Review and save these server-backed changes." : "Essentials reflect the latest acknowledged configuration.") + '</span></p><div><button class="quiet-button" data-setting-action="discard-settings" type="button"' + (!pending || state.settingsSaving ? ' disabled' : '') + '>Discard</button><button class="primary-action" id="settings-save" data-setting-action="save-settings" type="button"' + (!pending || state.settingsSaving ? ' disabled' : '') + (state.settingsSaving ? ' aria-busy="true"' : '') + '>Save changes</button></div></footer>';
}

function renderAllViews() { renderOverview(); renderAgents(); renderRoles(); renderReview(); renderAssets(); renderDiagnostics(); renderSettings(); renderRunLogSurfaces(); renderMessageComposer(); if ($("#onboarding-dialog")?.open) renderOnboarding(); }

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
    state.projectProgressStatus = result?.status === "UNKNOWN" || result?.progress_queue?.status !== "CURRENT" ? "unavailable" : "current";
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

function overviewRequestPath() {
  const projectId = selectedProgressProjectId();
  return "/api/overview" + (projectId ? "?project_id=" + encodeURIComponent(projectId) : "");
}

async function refreshMonitoring(proofSequence) {
  try {
    state.overview = await api(overviewRequestPath(), { timeoutMs: 15_000 });
    clearConnectionState();
    setDataStatus("current", state.overview?.generated_at);
    renderProjectNavigation();
    await Promise.all([refreshUsageHistory(), refreshNotifications(), refreshRunLogs(), refreshAssets(), refreshDiagnostics(false)]);
    if (Number(proofSequence) !== state.proofSequence) await refreshProof();
    renderOverview();
    renderAgents();
    renderReview();
    renderAssets();
    renderDiagnostics();
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
    state.overview = await api(overviewRequestPath(), { timeoutMs: 15_000 });
    clearConnectionState();
    setDataStatus("current", state.overview?.generated_at);
    renderProjectNavigation();
    await Promise.all([refreshProof(), refreshUsageHistory(), refreshProjectProgress(), refreshProjectProgressFeed(), refreshRoleManifests(), refreshNotifications(), refreshRunLogs(), refreshAssets()]);
    const selectedCtrl = state.ctrlId || historicalControllers()[0]?.id || '';
    const previousConfig = state.config;
    const results = await Promise.allSettled([api('/api/storage'), selectedCtrl ? api('/api/ctrl-settings?ctrl_id=' + encodeURIComponent(selectedCtrl)) : Promise.resolve(null), readConfigState(previousConfig), refreshDiagnostics(false)]);
    [state.storage, state.ctrlSettings] = results.slice(0, 2).map((result) => result.status === 'fulfilled' ? result.value : null);
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
  const scopeSelector = $("#project-scope-selector");
  if (scopeSelector?.open && !event.target.closest("#project-scope-selector")) scopeSelector.open = false;
  if (event.target.closest("#project-scope-filter")?.getAttribute("aria-disabled") === "true") {
    event.preventDefault();
    scopeSelector.open = false;
    return;
  }
  const projectScopeOption = event.target.closest("[data-project-scope-id]");
  if (projectScopeOption) {
    event.preventDefault();
    scopeSelector.open = false;
    await selectProjectScope(projectScopeOption.dataset.projectScopeId, $("#project-scope-filter"));
    return;
  }
  const usageRange = event.target.closest("[data-usage-range]");
  if (usageRange) {
    const hours = Number(usageRange.dataset.usageRange);
    if (![1, 24, 168].includes(hours) || hours === state.usageWindowHours) return;
    state.usageWindowHours = hours;
    state.usageStatus = "loading";
    renderUsageCharts();
    await refreshUsageHistory();
    renderUsageCharts();
    return;
  }
  if (!$("#notifications-panel").hidden && !event.target.closest("#notifications-panel, #notifications")) {
    setNotificationsOpen(false);
  }
  const onboardingDot = event.target.closest("[data-onboarding-step]");
  if (onboardingDot) {
    setOnboardingStep(onboardingDot.dataset.onboardingStep, true);
    return;
  }
  const assetProjection = event.target.closest("[data-asset-projection]");
  if (assetProjection) {
    const projection = assetProjection.dataset.assetProjection === "trash" ? "trash" : "active";
    if (projection !== state.assetProjection) {
      closeAssetDialog();
      state.assetProjection = projection;
      state.selectedAssetIdentity = "";
      state.assetConfirm = null;
      state.assetMutationPending = null;
      renderAssets();
      await refreshAssets();
      renderAssets();
    }
    $('[data-asset-projection="' + projection + '"]')?.focus({ preventScroll: true });
    return;
  }
  const assetView = event.target.closest("[data-asset-view]");
  if (assetView) {
    state.assetView = assetView.dataset.assetView === "list" ? "list" : "grid";
    renderAssets();
    $('[data-asset-view="' + state.assetView + '"]')?.focus({ preventScroll: true });
    return;
  }
  const projectUiMode = event.target.closest("[data-project-ui-mode]");
  if (projectUiMode) {
    state.projectUiMode = projectUiMode.dataset.projectUiMode === "map" ? "map" : "screens";
    state.projectUiGroupId = "";
    renderProjectDetail();
    $('[data-project-ui-mode="' + state.projectUiMode + '"]')?.focus({ preventScroll: true });
    return;
  }
  const projectMapBack = event.target.closest("[data-project-map-back]");
  if (projectMapBack) {
    const previousGroupId = state.projectUiGroupId;
    state.projectUiGroupId = projectMapBack.dataset.projectMapParent || "";
    renderProjectDetail();
    requestAnimationFrame(() => $$('[data-project-map-group]').find((element) => element.dataset.projectMapGroup === previousGroupId)?.focus({ preventScroll: true }));
    return;
  }
  const projectMapGroup = event.target.closest("[data-project-map-group]");
  if (projectMapGroup) {
    state.projectUiGroupId = projectMapGroup.dataset.projectMapGroup;
    renderProjectDetail();
    requestAnimationFrame(() => $("[data-project-map-node]")?.focus({ preventScroll: true }));
    return;
  }
  const projectViewEvidenceTrigger = event.target.closest("[data-project-view-evidence]");
  if (projectViewEvidenceTrigger) {
    openProjectViewEvidence(projectViewEvidenceTrigger.dataset.projectViewEvidence, projectViewEvidenceTrigger);
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
  const agentDetail = event.target.closest("[data-agent-detail]");
  if (agentDetail) {
    openAgentDetail(agentDetail);
    return;
  }
  const agentUpdatesFilter = event.target.closest("[data-agent-updates-filter]");
  if (agentUpdatesFilter) {
    state.agentUpdatesFilter = agentUpdatesFilter.dataset.agentUpdatesFilter;
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
  const assetAction = event.target.closest("[data-asset-action]");
  if (assetAction && !assetAction.disabled) {
    const item = assetItems().find((candidate) => assetIdentity(candidate) === assetAction.dataset.assetId);
    if (!item) return;
    const action = assetAction.dataset.assetAction;
    if (action === "trash") {
      openAssetDialog(assetIdentity(item), assetAction);
      state.assetConfirm = { assetId: assetIdentity(item) };
      renderAssetDialog(item);
      requestAnimationFrame(() => $('[data-asset-focus="confirm-trash"]', $("#asset-dialog"))?.focus({ preventScroll: true }));
    } else if (action === "restore" || action === "retry") {
      await mutateAsset(action, item);
    }
    return;
  }
  if (event.target.closest("[data-asset-confirm]")) {
    const item = assetItems().find((candidate) => assetIdentity(candidate) === state.assetConfirm?.assetId);
    if (item) await mutateAsset("trash", item);
    return;
  }
  if (event.target.closest("[data-asset-confirm-cancel]")) {
    state.assetConfirm = null;
    const item = assetItems().find((candidate) => assetIdentity(candidate) === state.selectedAssetIdentity);
    renderAssetDialog(item);
    requestAnimationFrame(() => $('[data-asset-focus="trash"]', $("#asset-dialog"))?.focus({ preventScroll: true }));
    return;
  }
  if (event.target.closest("[data-asset-mutation-retry]")) {
    await runAssetMutation(state.assetMutationPending);
    return;
  }
  if (event.target.closest("[data-asset-undo]")) {
    const item = state.assetUndo?.item;
    const identity = assetIdentity(item);
    if (item && await mutateAsset("restore", item)) requestAnimationFrame(() => $('[data-asset-detail="' + CSS.escape(identity) + '"]')?.focus({ preventScroll: true }));
    return;
  }
  if (event.target.closest("[data-asset-undo-dismiss]")) {
    state.assetUndo = null;
    renderAssets();
    return;
  }
  const asset = event.target.closest("[data-asset-detail]");
  if (asset) {
    openAssetDialog(asset.dataset.assetDetail, asset);
    return;
  }
  if (event.target.closest("#asset-dialog-done")) {
    closeAssetDialog();
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
    selectRoleChoice(roleSelect.dataset.roleSelect);
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
  const tab = event.target.closest("[data-view]");
  if (tab) {
    setView(tab.dataset.view);
    if (mobileDrawerQuery.matches) setMobileDrawer(false, true);
  }
});

$("#message-launcher").addEventListener("click", (event) => openMessageComposer(event.currentTarget));
$("#mobile-message-action").addEventListener("click", (event) => openMessageComposer(event.currentTarget));
$("#message-close").addEventListener("click", () => closeMessageComposer());
$("#message-draft").addEventListener("input", (event) => {
  state.messageDraft = event.target.value;
  if (["failed", "conflict", "sent"].includes(state.messageStatus)) {
    state.messageStatus = "unavailable";
    state.messageError = "";
    renderMessageComposer();
  }
});
$("#message-recipient").addEventListener("change", (event) => {
  state.messageRecipientId = event.target.value;
  state.messageStatus = "unavailable";
  state.messageError = "";
  renderMessageComposer();
});
$("#message-send").addEventListener("click", sendMessageFromComposer);
$("#message-retry").addEventListener("click", sendMessageFromComposer);

$("#onboarding-close").addEventListener("click", () => closeOnboarding());
$("#onboarding-skip").addEventListener("click", () => closeOnboarding());
$("#onboarding-back").addEventListener("click", () => setOnboardingStep(state.onboardingStep - 1, false, "back"));
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
$("#onboarding-coordination-tree").addEventListener("keydown", moveOnboardingTreeFocus);
$("#onboarding-coordination-tree").addEventListener("click", (event) => {
  const control = event.target.closest("[data-onboarding-flow-zoom]");
  if (!control) return;
  const action = control.dataset.onboardingFlowZoom;
  state.onboardingFlowZoom = action === "fit" ? 1 : Math.min(1.1, Math.max(.9, state.onboardingFlowZoom + (action === "in" ? .1 : -.1)));
  renderOnboardingCoordination();
  control.focus({ preventScroll: true });
});
$("#onboarding-dialog").addEventListener("close", () => {
  state.onboardingTrigger?.focus({ preventScroll: true });
  state.onboardingTrigger = null;
});
$("#onboarding-dialog").addEventListener("cancel", (event) => {
  event.preventDefault();
  if (onboardingCanDismiss()) closeOnboarding();
  else {
    renderOnboarding();
    requestAnimationFrame(() => ($('[data-onboarding-control="retry-config"]', $("#onboarding-configuration")) || $("#onboarding-config-status", $("#onboarding-configuration")) || $("#onboarding-primary"))?.focus({ preventScroll: true }));
  }
});

$("#evidence-lightbox").addEventListener("close", () => {
  state.evidenceTrigger?.focus();
  state.evidenceTrigger = null;
});
$("#asset-dialog-close").addEventListener("click", closeAssetDialog);
$("#asset-dialog").addEventListener("close", () => {
  const trigger = state.assetTrigger?.element;
  const replacement = state.assetTrigger?.identity ? $('[data-asset-detail="' + CSS.escape(state.assetTrigger.identity) + '"]') : null;
  (trigger?.isConnected ? trigger : replacement)?.focus({ preventScroll: true });
  state.assetTrigger = null;
});
$("#agent-updates-pause").addEventListener("click", () => {
  state.agentUpdatesPaused = !state.agentUpdatesPaused;
  renderAgentUpdateControls();
  renderRunLogSurfaces();
});
$("#agent-detail-close").addEventListener("click", () => closeAgentDetail());
$("#agent-detail-done").addEventListener("click", () => closeAgentDetail());
$("#agent-detail-dialog").addEventListener("cancel", (event) => {
  event.preventDefault();
  closeAgentDetail();
});
$("#agent-detail-dialog").addEventListener("close", () => {
  const trigger = state.agentDetailTrigger;
  const replacement = trigger?.dataset.agentDetail
    ? $$('[data-agent-detail]').find((candidate) => candidate.dataset.agentDetail === trigger.dataset.agentDetail && candidate.dataset.agentProject === trigger.dataset.agentProject)
    : null;
  (trigger?.isConnected ? trigger : replacement || $("#agents-heading"))?.focus?.({ preventScroll: true });
  state.agentDetailTrigger = null;
});
$("#config-editor-close").addEventListener("click", closeConfigEditor);
$("#config-editor-cancel").addEventListener("click", closeConfigEditor);
$("#config-editor-dialog").addEventListener("cancel", (event) => {
  event.preventDefault();
  closeConfigEditor();
});
$("#config-editor-dialog").addEventListener("close", () => {
  state.configEditorTrigger?.focus({ preventScroll: true });
  state.configEditorTrigger = null;
});
$("#project-scope-selector").addEventListener("keydown", (event) => {
  const options = $$('[data-project-scope-id]', event.currentTarget);
  if (event.target.id === "project-scope-filter" && ["ArrowDown", "Home", "End"].includes(event.key)) {
    event.preventDefault();
    event.currentTarget.open = true;
    (event.key === "End" ? options.at(-1) : options.find((option) => option.getAttribute("aria-selected") === "true") || options[0])?.focus();
    return;
  }
  const index = options.indexOf(event.target.closest("[data-project-scope-id]"));
  if (index < 0 || !["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const next = event.key === "Home" ? 0 : event.key === "End" ? options.length - 1 : Math.max(0, Math.min(options.length - 1, index + (event.key === "ArrowDown" ? 1 : -1)));
  options[next]?.focus();
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
  if (event.key === "Escape" && state.messageOpen) {
    event.preventDefault();
    closeMessageComposer();
    return;
  }
  if (event.key === "Escape" && $("#project-scope-selector")?.open) {
    event.preventDefault();
    $("#project-scope-selector").open = false;
    $("#project-scope-filter").focus({ preventScroll: true });
    return;
  }
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

$("#project-navigation").addEventListener("click", async (event) => {
  const scope = event.target.closest("[data-project-id]");
  if (!scope) return;
  event.preventDefault();
  await selectProjectScope(scope.dataset.projectId, scope);
});
$("#project-scope-selector").addEventListener("toggle", (event) => {
  $("#project-scope-filter").setAttribute("aria-expanded", String(event.currentTarget.open));
});
$("#project-navigation-heading").addEventListener("click", async (event) => {
  event.preventDefault();
  setView("overview", false, false);
  await selectProjectScope("all", event.currentTarget);
});
$("#overview-project-cards").addEventListener("click", async (event) => {
  const project = event.target.closest("[data-overview-project-id]");
  if (project) await selectProjectScope(project.dataset.overviewProjectId, project);
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
$("#role-editor").addEventListener("cancel", (event) => { event.preventDefault(); closeRoleEditor(); });
$("#role-editor").addEventListener("close", restoreRoleEditorFocus);
$("#role-editor-form").addEventListener("input", () => {
  state.roleManifestRetry = null;
  updateRoleEditorAuthority(!$("#role-field-avatar").value ? "Choose a retained image asset before saving." : "");
});
$("#role-editor-form").addEventListener("submit", async (event) => { event.preventDefault(); await submitRoleCommand("save"); });
$("#role-search").addEventListener("input", (event) => {
  state.roleSearch = event.target.value;
  renderRoleLibrary();
});
$("#role-library-grid").addEventListener("keydown", (event) => {
  if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  const current = event.target.closest("[data-role-select]");
  if (!current) return;
  const choices = $$("#role-library-grid [data-role-select]");
  const index = choices.indexOf(current);
  const nextIndex = roleGridTargetIndex(event.key, index, choices.length, roleGridColumnCount($("#role-library-grid")));
  event.preventDefault();
  if (nextIndex !== index) selectRoleChoice(choices[nextIndex].dataset.roleSelect);
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
  if (event.target.id === 'settings-scope') {
    const [scopeType, scopeId] = event.target.value.split('|');
    const ctrl = scopeType === 'ctrl' ? historicalControllers().find((item) => item.id === scopeId) : null;
    state.settingsScopeType = ['global', 'project', 'ctrl'].includes(scopeType) ? scopeType : 'global';
    state.settingsScopeId = scopeId || 'global';
    state.settingsCtrlId = ctrl ? ctrl.id : '';
    state.settingsDraft.clear();
    state.settingsSaveError = "";
    state.settingsSaveMessage = "";
    setProjectSelection(scopeType === 'project' ? scopeId : ctrl ? (ctrl.project_id || 'ctrl:' + ctrl.id) : 'all', ctrl ? ctrl.id : '');
    renderProjectNavigation();
    renderAllViews();
    try {
      await Promise.all([refreshProof(), refreshUsageHistory(), refreshProjectProgress(), refreshProjectProgressFeed(), refreshCtrlSettings(), refreshSkills(), refreshNotifications(), refreshRunLogs()]);
      await refreshAutoStatus();
    } finally { renderAllViews(); }
    return;
  }
  if (event.target.dataset.settingsDraftKey) {
    const key = event.target.dataset.settingsDraftKey;
    const value = event.target.type === "radio"
      ? event.target.dataset.configValue === "true"
      : event.target.dataset.trueValue !== undefined
        ? (event.target.checked ? event.target.dataset.trueValue : event.target.dataset.falseValue)
        : event.target.checked;
    if (stageSettingsDraft(key, value)) renderSettings();
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
      await saveConfigMutation(chatRelayMutation(requestedValue).changes);
    } catch (error) {
      const saveError = error.message || "Chat relay setting could not be saved.";
      try { await readConfigState(previousConfig, saveError); }
      catch (reloadError) { /* readConfigState retains the truthful failure state. */ }
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
    const value = event.target.type === 'range' && event.target.dataset.configValues
      ? Number(event.target.dataset.configValues.split(',')[Number(event.target.value)])
      : event.target.type === 'radio' && event.target.dataset.configValue !== undefined
      ? event.target.dataset.configValue === 'true'
      : event.target.type === 'checkbox' && event.target.dataset.trueValue !== undefined
        ? (event.target.checked ? event.target.dataset.trueValue : event.target.dataset.falseValue)
        : event.target.type === 'checkbox' ? event.target.checked : event.target.type === 'number' ? Number(event.target.value) : event.target.value;
    if (event.target.closest("#onboarding-configuration")) {
      await saveOnboardingConfig(key, value);
      return;
    }
    try {
      await saveConfigMutation({ [key]: value });
      if (key === 'console.project_progress_feed_enabled' || key === 'console.project_progress_feed_lines') await refreshProjectProgressFeed();
      renderAllViews();
    } catch (error) { showError(error.message); renderSettings(); }
    return;
  }
  if (event.target.id === 'ctrl-customize') {
    if (!state.ctrlSettings) return;
    if (!event.target.checked && !confirm('Use global defaults for this CTRL?')) { event.target.checked = true; return; }
    try {
      if (event.target.checked) {
        const defaults = state.ctrlSettings.global_defaults || {};
        state.ctrlSettings = await api('/api/ctrl-settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ctrl_id: state.ctrlSettings.ctrl_id, expected_revision: state.ctrlSettings.revision, changes: { model: defaults.model, reasoning: defaults.reasoning } }) });
      } else {
        await resetSettingsScope('ctrl');
      }
      renderSettings();
    } catch (error) { showError(error.message); await refreshCtrlSettings(); renderSettings(); }
  }
});
document.addEventListener('click', async (event) => {
  if (event.target.closest('#onboarding-advanced-settings')) {
    openAdvancedSettingsFromOnboarding();
    return;
  }
  if (event.target.closest('[data-onboarding-control="retry-config"]')) {
    await retryOnboardingConfig();
    return;
  }
  const action = event.target.closest('[data-setting-action]')?.dataset.settingAction;
  if (!action) return;
  if (action === 'replay-tour') {
    openOnboarding(true, event.target.closest('[data-setting-action]'));
    return;
  }
  if (action === 'edit-config') {
    openConfigEditor(event.target.closest('[data-setting-action]'));
    return;
  }
  if (action === 'discard-settings') {
    state.settingsDraft.clear();
    state.settingsSaveError = "";
    state.settingsSaveMessage = "Changes discarded";
    renderSettings();
    requestAnimationFrame(() => $('#settings-scope')?.focus({ preventScroll: true }));
    return;
  }
  if (action === 'save-settings') {
    await saveSettingsDraft();
    return;
  }
  const messages = { clear: 'Clear saved SWARM history? Your tasks will stay unchanged.', restore: 'Restore global defaults? Project and CTRL overrides will stay unchanged.', 'reset-project': 'Reset this project to global settings? Its project override will be removed.', reset: 'Use global defaults for this CTRL?', 'reset-skills': 'Restore inherited skill settings for this scope?' };
  if (messages[action] && !confirm(messages[action])) return;
  try {
    if (action === 'clear') await api('/api/storage/clear', { method: 'POST' });
    if (action === 'restore') await resetSettingsScope('global');
    if (action === 'reset-project') await resetSettingsScope('project');
    if (action === 'reset' && state.ctrlSettings) await resetSettingsScope('ctrl');
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
    if (action === 'save-spark' && configEditable('boost.spark_model')) await saveConfigMutation({ 'boost.spark_model': $('#spark-model').value.trim() });
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

$(".project-tabs").addEventListener("keydown", (event) => {
  if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
  const tabs = $$('[data-project-tab]').filter((tab) => !tab.hidden);
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
window.addEventListener("resize", scheduleProjectViewConnectors);
window.addEventListener("pagehide", () => { if (presenceTimer) clearInterval(presenceTimer); });

syncMobileDrawer();
setProjectSelection(routeProjectId());
setView(routeView(), false, false);
writeRoute("replace");
function applyHistoryRoute() {
  const route = location.pathname + location.search + location.hash;
  if (route === lastAppliedHistoryRoute) return;
  lastAppliedHistoryRoute = route;
  setProjectSelection(routeProjectId());
  state.scopeNotice = "Restored " + scopeLabel() + " on " + (routeView() === "overview" ? "Overview" : routeView()) + ".";
  state.scopeNoticeVisible = false;
  setView(routeView(), false, false);
  renderProjectNavigation();
  renderAllViews();
  refreshOverview(false);
}
window.addEventListener('popstate', applyHistoryRoute);
window.addEventListener('hashchange', applyHistoryRoute);
initialize().then(startPresence);
