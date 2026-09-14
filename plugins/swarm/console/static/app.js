const state = { token: "", overview: null, proof: [], proofCollections: new Map(), proofStatuses: new Map(), proofStatus: "idle", proofSequence: 0, usageHistory: null, usageRequestGeneration: 0, usageWindowHours: 1, usageScopeKey: "", usageStatus: "idle", usageError: "", projectProgress: null, projectProgressProjectId: "", projectProgressStatus: "idle", projectProgressError: "", projectProgressFeed: null, projectProgressFeedProjectId: "", projectProgressFeedStatus: "idle", projectProgressFeedError: "", projectTab: "overview", projectUiMode: "screens", projectUiGroupId: "", projectArtifactPage: 0, runLogs: new Map(), runLogRequestGenerations: new Map(), runLogSurfaceStates: new Map(), runLogAgent: null, agentUpdatesFilter: "all", agentUpdatesPaused: false, agentDetailTrigger: null, diagnostics: null, diagnosticsHistory: null, diagnosticsHistoryStatus: "idle", diagnosticsError: "", diagnosticsSelectedChecks: new Set(), diagnosticsSelectionInitialized: false, diagnosticsRepairPreview: null, diagnosticsRepairPending: false, diagnosticsRepairError: "", diagnosticsRepairTrigger: null, health: null, storage: null, profile: null, profileStatus: "idle", profileError: "", profileUpload: null, profilePreviewUrl: "", profileSaving: false, profileTrigger: null, supportTrigger: null, messageOpen: false, messageTrigger: null, messageDraft: "", messageRecipientId: "", messageStatus: "unavailable", messageError: "", messageReceipt: null, messageConnector: null, messageAttachments: [], messagePendingAction: null, config: null, configStatus: "idle", configError: "", configResetPending: null, configResetRetry: null, chatRelaySaving: false, settingsDraft: new Map(), settingsSaving: false, settingsSaveError: "", settingsSaveMessage: "", configEditorTrigger: null, ctrlSettings: null, auto: null, autoBindingKey: "", autoStatus: "idle", autoError: "", autoSaving: false, skills: null, skillsError: "", roleManifests: null, roleManifestStatus: "unavailable", roleManifestError: "", roleManifestMessage: "", roleManifestSaving: false, roleManifestRetry: null, roleEditorMode: "", roleEditorTrigger: null, roleSearch: "", roleTypes: new Set(["builtin", "custom"]), roleSearchFields: new Set(["profession", "specialization", "alias", "skills", "purpose"]), selectedRoleId: "", roleDetailOpen: false, roleDetailTriggerId: "", assets: null, assetBindingKey: "", assetStatus: "idle", assetError: "", assetProjection: "active", assetView: "grid", assetPage: 0, assetRequestGeneration: 0, assetEventCursors: new Map(), assetMutationPending: null, assetConfirm: null, assetUndo: null, selectedAssetIdentity: "", assetTrigger: null, onboardingStep: 0, onboardingShown: false, onboardingTrigger: null, onboardingConfigPending: new Map(), onboardingConfigFailures: new Map(), notifications: null, notificationBindingKey: "", notificationStatus: "idle", notificationError: "", notificationAckFlight: null, notificationRequestGenerations: new Map(), notificationPresentedIds: new Set(), notificationToast: null, notificationToastTimer: null, notificationTrigger: null, connectionStatus: "reconnecting", view: "overview", projectId: "all", ctrlId: "", scopeNotice: "", scopeNoticeVisible: false, settingsCtrlId: "", settingsScopeType: "", settingsScopeId: "", evidenceImages: [], evidenceIndex: 0, evidenceTrigger: null, labs: null, labsStatus: "idle", labsError: "" };
const THEME_STORAGE_KEY = "swarm.theme.v1";
const THEME_OPTIONS = Object.freeze({ midnight: "Midnight", black: "Black", graphite: "Graphite", pearl: "Pearl" });

function currentTheme() {
  return Object.hasOwn(THEME_OPTIONS, document.documentElement.dataset.theme) ? document.documentElement.dataset.theme : "midnight";
}

function setTheme(theme, storage = window.localStorage) {
  const selected = Object.hasOwn(THEME_OPTIONS, theme) ? theme : "midnight";
  document.documentElement.dataset.theme = selected;
  try { storage.setItem(THEME_STORAGE_KEY, selected); } catch { /* Presentation remains applied when storage is unavailable. */ }
  return selected;
}

const PROFILE_API_CONTRACT = Object.freeze({ read: "/api/profile", write: "/api/profile", schemaVersion: 1, avatarField: "avatar", profileField: "profile" });
const DIAGNOSTICS_HISTORY_HOURS = 1;
const MESSAGE_CONNECTOR_UNAVAILABLE = "Messaging is unavailable until SWARM exposes the authenticated HQ connector.";
let configMutationTail = Promise.resolve();
let configAuthorityGeneration = 0;
let configWriteRetry = null;
let lastAppliedHistoryRoute = "";
const RUN_LOG_CLIENT_LIMIT = 200;
const ONBOARDING_PRESENTATION_KEY = "swarm.onboarding.v2.seen";
const ONBOARDING_STEPS = [
  { name: "Welcome", primary: "Start guided tour" },
  { name: "Coordinated roles", primary: "Continue" },
  { name: "Role variety", primary: "Continue" },
  { name: "Project views", primary: "Continue" },
  { name: "Configuration", primary: "Start using SWARM" },
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

const COLLECTION_PAGE_SIZE = 12;

function boundedCollectionWindow(items, step) {
  const total = items.length;
  const index = Math.max(0, Number.isInteger(step) ? step : 0);
  const end = Math.min(total, COLLECTION_PAGE_SIZE * (index + 1));
  return { items: items.slice(0, end), index, total, end, hasMore: end < total };
}

function collectionLoadMoreMarkup(kind, collection, label) {
  if (!collection.hasMore) return '<p class="collection-status" data-collection-status="' + kind + '" role="status" aria-live="polite" tabindex="-1">Showing all ' + collection.total + ' ' + escapeHTML(label.toLowerCase()) + '.</p>';
  return '<div class="collection-more"><button class="quiet-button" type="button" data-collection-more="' + kind + '">Load more</button><p class="collection-status" data-collection-status="' + kind + '" role="status" aria-live="polite" tabindex="-1">Showing ' + collection.end + ' of ' + collection.total + ' ' + escapeHTML(label.toLowerCase()) + '.</p></div>';
}

function loadingSkeletonMarkup(count = 8) {
  return '<div class="loading-skeleton" aria-hidden="true">' + Array.from({ length: count }, () => "<i></i>").join("") + '</div>';
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

const STATE_ILLUSTRATIONS = Object.freeze({
  offline: Object.freeze({ asset: "/assets/swarm-offline-disconnected.png", webp: "/assets/swarm-offline-disconnected.webp", width: 1024, height: 640, prop: "" }),
  failed: Object.freeze({ asset: "/assets/swarm-state-mascot-concerned.png", webp: "/assets/swarm-state-mascot-concerned.webp", width: 512, height: 512, prop: "!" }),
  empty: Object.freeze({ asset: "/assets/swarm-state-mascot-concerned.png", webp: "/assets/swarm-state-mascot-concerned.webp", width: 512, height: 512, prop: "—" }),
  recovery: Object.freeze({ asset: "/assets/swarm-state-mascot-concerned.png", webp: "/assets/swarm-state-mascot-concerned.webp", width: 512, height: 512, prop: "↻" }),
});

function stateIllustrationMarkup(variant = "empty", { compact = false } = {}) {
  const resolvedVariant = Object.hasOwn(STATE_ILLUSTRATIONS, variant) ? variant : "empty";
  const illustration = STATE_ILLUSTRATIONS[resolvedVariant];
  const prop = illustration.prop ? '<span class="state-illustration-prop">' + illustration.prop + "</span>" : "";
  return '<div class="state-illustration state-illustration--' + resolvedVariant + (compact ? " state-illustration--compact" : "") + '" data-state-variant="' + resolvedVariant + '" aria-hidden="true"><picture><source type="image/webp" srcset="' + illustration.webp + '"><img src="' + illustration.asset + '" width="' + illustration.width + '" height="' + illustration.height + '" loading="lazy" decoding="async" alt=""></picture>' + prop + "</div>";
}

function stateMessageMarkup(variant, title, detail, className = "") {
  return '<section class="empty-state state-message ' + escapeHTML(className) + '" role="status">' + stateIllustrationMarkup(variant, { compact: true }) + '<div><strong>' + escapeHTML(title) + "</strong><p>" + escapeHTML(detail) + "</p></div></section>";
}

function showError(message) {
  $("#error-message").textContent = message;
  $("#error-surface").hidden = false;
}

function clearError(restoreFocus = true) {
  const surface = $("#error-surface");
  const restore = restoreFocus && surface.contains(document.activeElement);
  surface.hidden = true;
  if (restore) requestAnimationFrame(() => $("#notifications")?.focus({ preventScroll: true }));
}

function showConnectionState() {
  clearError(false);
  setDataStatus("unavailable", state.overview?.generated_at);
  setNotificationsOpen(false);
  dismissNotificationToast(false);
  if (state.messageOpen) closeMessageComposer(false, true);
  $(".app-shell").classList.add("is-disconnected");
  $(".workspace").classList.add("is-disconnected");
  $("#connection-state").hidden = false;
  updateDocumentTitle();
}

function clearConnectionState() {
  const surface = $("#connection-state");
  const restore = surface.contains(document.activeElement);
  $(".app-shell").classList.remove("is-disconnected");
  $(".workspace").classList.remove("is-disconnected");
  surface.hidden = true;
  updateDocumentTitle();
  if (restore) requestAnimationFrame(() => $("#notifications")?.focus({ preventScroll: true }));
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

const ONBOARDING_TASK_LIFE_DETENTS = [
  { hours: 1, valueText: "Short — 1 hour" },
  { hours: 2, valueText: "Between Short and Balanced — 2 hours" },
  { hours: 4, valueText: "Balanced — 4 hours" },
  { hours: 24, valueText: "Between Balanced and Long — 24 hours" },
  { hours: 720, valueText: "Long — 30 days" },
];

function onboardingConfigurationMarkup() {
  const settings = state.config?.settings || {};
  const execution = settings.execution || {};
  const automation = settings.automation || {};
  const lifecycle = settings.lifecycle || {};
  const pending = state.onboardingConfigPending.size;
  const failures = [...state.onboardingConfigFailures.values()];
  const status = pending ? 'Saving ' + pending + ' setting' + (pending === 1 ? '' : 's') + '…' : failures.length ? (failures[0].error || 'A setting was not saved.') : 'Changes are saved when acknowledged by SWARM.';
  const binding = { attribute: "data-config-key", control: true };
  const mode = onboardingConfigDraft("automation.mode", automation.mode || "standard");
  const fast = onboardingConfigDraft("execution.fast_mode", execution.fast_mode === true);
  const life = onboardingConfigDraft("lifecycle.task_lifetime_hours", lifecycle.task_lifetime_hours);
  return '<section class="settings-essentials onboarding-config-essentials"><header class="settings-essentials-head"><div><p class="eyebrow">Essentials</p><h3>How SWARM runs your work</h3><p>Execution-first defaults, shared with Settings.</p></div></header><div class="settings-toggle-grid">' + settingsSwitch("automation.mode", mode, "Auto mode", "SWARM keeps eligible work moving until it needs you.", { trueValue: "standard", falseValue: "manual", editable: configEditable("automation.mode") && !state.onboardingConfigPending.has("automation.mode"), binding }) + '</div><div class="settings-run-controls">' +
    settingsSpeedMarkup({ value: fast, editable: configEditable("execution.fast_mode") && !state.onboardingConfigPending.has("execution.fast_mode"), binding, name: "onboarding-speed" }) + settingsTaskLifeMarkup({ value: life, editable: Number.isInteger(lifecycle.task_lifetime_hours) && configEditable("lifecycle.task_lifetime_hours") && !state.onboardingConfigPending.has("lifecycle.task_lifetime_hours"), binding, id: "onboarding-task-life" }) + '</div></section>' +
    '<button class="onboarding-advanced-link" id="onboarding-advanced-settings" data-onboarding-control="advanced-settings-link" type="button">Advanced settings</button>' +
    '<div class="onboarding-config-save ' + (failures.length ? 'is-error' : '') + '" id="onboarding-config-status" data-onboarding-control="config-status" role="status" tabindex="-1"><span>' + escapeHTML(status) + '</span>' + (failures.length ? '<button class="quiet-button" type="button" data-onboarding-control="retry-config">Retry</button>' : '') + '</div>';
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
  if (!force && (state.messageOpen || $("dialog[open]"))) return;
  if ((!force && (state.onboardingShown || onboardingSeen())) || !state.overview || $(".workspace").classList.contains("is-disconnected")) return;
  state.onboardingShown = true;
  state.onboardingStep = 0;
  state.onboardingTrigger = trigger || (document.activeElement instanceof HTMLElement && document.activeElement !== document.body ? document.activeElement : $("#tab-overview"));
  renderOnboarding();
  const dialog = $("#onboarding-dialog");
  $(".dialog-body", dialog).scrollTop = 0;
  if (!dialog.open) dialog.showModal();
  updateDocumentTitle();
  requestAnimationFrame(() => $("#onboarding-primary").focus({ preventScroll: true }));
}

function closeOnboarding(openProjects = false) {
  if (state.onboardingStep === ONBOARDING_STEPS.length - 1 && onboardingConfigBlocked()) return false;
  markOnboardingSeen();
  const dialog = $("#onboarding-dialog");
  if (dialog.open) dialog.close();
  updateDocumentTitle();
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
    entry.open = true;
    entry.scrollIntoView({ block: 'start' });
    const editConfig = $('#settings-edit-config');
    editConfig?.focus();
    editConfig?.scrollIntoView({ block: 'nearest' });
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

function configWriteOperationId() {
  const values = new Uint32Array(4);
  window.crypto.getRandomValues(values);
  return "console-config-write-" + [...values].map((value) => value.toString(16).padStart(8, "0")).join("");
}

function configWriteScope(projection = state.config) {
  const scope = projection?.scope;
  if (scope?.type === "global") return { type: "global" };
  if (scope?.type === "project" && scope.project_id && scope.accepted_cursor) {
    return { type: "project", project_id: String(scope.project_id), accepted_cursor: structuredClone(scope.accepted_cursor) };
  }
  return null;
}

function configTomlLiteral(value) {
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) return "[" + value.map(configTomlLiteral).join(", ") + "]";
  throw new Error("This setting cannot be represented in the canonical config text.");
}

function configTextWithChanges(source, changes) {
  if (typeof source !== "string") throw new Error("Exact config text is unavailable. Reload Settings before saving.");
  const newline = source.includes("\r\n") ? "\r\n" : "\n";
  const lines = source.split(/\r?\n/);
  for (const [path, value] of Object.entries(changes || {})) {
    const parts = String(path).split(".").filter(Boolean);
    if (parts.length < 2 || !parts.every((part) => /^[A-Za-z0-9_-]+$/.test(part))) throw new Error("This setting has an invalid config path.");
    const key = parts.pop();
    const section = parts.join(".");
    let sectionStart = -1;
    let sectionEnd = lines.length;
    for (let index = 0; index < lines.length; index += 1) {
      const match = lines[index].match(/^\s*\[([^\]]+)\]\s*(?:#.*)?$/);
      if (!match) continue;
      if (sectionStart >= 0) { sectionEnd = index; break; }
      if (match[1].trim() === section) sectionStart = index;
    }
    const assignment = key + " = " + configTomlLiteral(value);
    if (sectionStart < 0) {
      if (lines.length && lines.at(-1).trim()) lines.push("");
      lines.push("[" + section + "]", assignment);
      continue;
    }
    const keyPattern = new RegExp("^\\s*" + key.replace(/[.*+?^${}()|[\\]\\]/g, "\\$&") + "\\s*=");
    const existing = lines.findIndex((line, index) => index > sectionStart && index < sectionEnd && keyPattern.test(line));
    if (existing >= 0) lines[existing] = assignment;
    else lines.splice(sectionEnd, 0, assignment);
  }
  return lines.join(newline);
}

function configWriteRequest(text, projection = state.config) {
  const scope = configWriteScope(projection);
  if (projection?.state !== "KNOWN" || projection?.write_contract?.available !== true || !scope || projection.revision == null || typeof text !== "string") {
    throw new Error("Settings are not writable from the current accepted config projection.");
  }
  const identity = JSON.stringify({ scope, expected_revision: projection.revision, text });
  const retry = configWriteRetry?.identity === identity ? configWriteRetry : null;
  if (retry?.exhausted) throw new Error("SWARM could not confirm this save after one retry. Reload before trying again; your unsaved changes are preserved.");
  const operationId = retry?.operationId || configWriteOperationId();
  return {
    identity,
    operationId,
    uncertainRetry: Boolean(retry),
    binding: JSON.stringify(scope),
    payload: { scope, expected_revision: projection.revision, acknowledge: true, text, operation_id: operationId },
  };
}

function configWriteReceiptMatches(result, request) {
  const receipt = result?.mutation_receipt;
  return result?.state === "KNOWN"
    && JSON.stringify(configWriteScope(result)) === request.binding
    && JSON.stringify(receipt?.scope) === request.binding
    && result.revision === receipt?.new_revision
    && receipt?.accepted === true
    && receipt?.action === (request.action || "config_update")
    && typeof receipt?.replayed === "boolean"
    && receipt?.acknowledged === true
    && receipt?.operation_id === request.operationId
    && receipt?.expected_revision === request.payload.expected_revision;
}

function configWriteBindingIsCurrent(request) {
  return JSON.stringify(configWriteScope(state.config)) === request.binding
    && state.config?.revision === request.payload.expected_revision;
}

async function saveConfigText(text) {
  configAuthorityGeneration += 1;
  let request = null;
  const operation = configMutationTail.then(async () => {
    const resolvedText = typeof text === "function" ? text() : text;
    request = configWriteRequest(resolvedText);
    const config = await api('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request.payload),
    });
    return config;
  });
  configMutationTail = operation.then(() => undefined, () => undefined);
  try {
    const config = await operation;
    if (!configWriteReceiptMatches(config, request)) {
      const error = new Error("SWARM returned an invalid config acknowledgement. Your changes are still here; retry this exact save.");
      error.invalidConfigAcknowledgement = true;
      throw error;
    }
    configWriteRetry = null;
    if (!configWriteBindingIsCurrent(request)) return { applied: false, config };
    state.config = config;
    state.configStatus = "current";
    state.configError = "";
    return { applied: true, config };
  } catch (error) {
    const uncertain = Boolean(request) && (error?.invalidConfigAcknowledgement === true || error?.connectionFailure === true || !Number.isInteger(error?.status));
    if (request) configWriteRetry = uncertain ? { identity: request.identity, operationId: request.operationId, exhausted: request.uncertainRetry } : null;
    if (error?.status === 409) error.message = "Settings changed elsewhere. Reload before retrying; your unsaved changes are preserved.";
    else if (uncertain && request?.uncertainRetry) error.message = "SWARM could not confirm this save after one retry. Reload before trying again; your unsaved changes are preserved.";
    else if (uncertain && error?.invalidConfigAcknowledgement !== true) error.message = "SWARM could not confirm the save. Retry will reuse this exact operation; your unsaved changes are preserved.";
    throw error;
  }
}

async function saveConfigMutation(changes) {
  return saveConfigText(() => configTextWithChanges(state.config?.editable_text, changes));
}

async function saveCurrentConfigMutation(changes) {
  const result = await saveConfigMutation(changes);
  if (!result.applied) throw new Error("Settings scope changed before the save was acknowledged. Your unsaved changes are preserved.");
  return result;
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
  return Boolean(request) && scope.type === request.binding.type && String(scope.id) === request.binding.id &&
    (request.kind === "ctrl" || (state.configStatus === "current" && state.config?.revision === request.payload.expected_revision && JSON.stringify(configWriteScope()) === JSON.stringify(request.payload.scope)));
}

async function resetSettingsScope(kind) {
  const base = configResetRequest(kind);
  if (!base || state.configResetPending) throw new Error("This settings scope cannot be reset from the current accepted projection.");
  const key = configResetRequestKey(base);
  const retainedRetry = state.configResetRetry?.key === key ? state.configResetRetry : null;
  if (retainedRetry?.exhausted) throw new Error("SWARM could not confirm this reset after one retry. Reload before trying again.");
  const operationId = retainedRetry?.operationId || configResetOperationId(kind);
  const request = { ...base, key, operationId, payload: { ...base.payload, operation_id: operationId } };
  state.configResetPending = request;
  configAuthorityGeneration += 1;
  const operation = configMutationTail.then(() => {
    if (!configResetBindingIsCurrent(request)) throw Object.assign(new Error("Settings changed before reset. Reload the current scope."), { status: 409 });
    return api(request.endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request.payload) });
  });
  configMutationTail = operation.then(() => undefined, () => undefined);
  try {
    const result = await operation;
    if (kind !== "ctrl" && !configWriteReceiptMatches(result, { ...request, binding: JSON.stringify(request.payload.scope), action: kind + "_config_reset" })) {
      throw new Error("SWARM returned an invalid reset acknowledgement. Retry this exact reset; current settings are preserved.");
    }
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
    state.configResetRetry = error?.connectionFailure === true || !Number.isInteger(error?.status) ? { key, operationId, exhausted: Boolean(retainedRetry) } : null;
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
    await saveCurrentConfigMutation({ [key]: value });
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
  const chromeDot = $("#snapshot-status-dot");
  if (chromeDot) chromeDot.className = "status-dot" + (presentation.className ? " " + presentation.className : "");
}

function setDataStatus(status, observedAt = null) {
  const snapshotDot = $("#snapshot-status-dot");
  const snapshot = $("#sync-time");
  if (!snapshotDot || !snapshot) return;
  const connection = status === "current" ? "live" : status === "unavailable" ? "offline" : "reconnecting";
  state.connectionStatus = connection;
  if (connection !== "live") invalidateMessageHistory();
  if (connection !== "live") clearCommandApprovals();
  if (connection !== "live" && state.view === "overview") renderProjectDetail();
  snapshotDot.classList.toggle("is-live", connection === "live");
  snapshotDot.classList.toggle("is-reconnecting", connection === "reconnecting");
  snapshotDot.classList.toggle("is-offline", connection === "offline");
  if (connection === "live") {
    snapshot.textContent = observedAt ? "Live · " + formatRelative(observedAt) : "Live";
  } else if (connection === "reconnecting") {
    snapshot.textContent = "Reconnecting";
  } else {
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
  if (expanded && $("#project-scope-selector")?.open) $("#project-scope-selector").open = false;
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

const TOP_LEVEL_VIEWS = ["overview", "agents", "labs", "roles", "review", "assets", "diagnostics", "settings"];

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

function titleSegment(value) {
  const normalized = String(value || "").replace(/[\u{1F000}-\u{1FAFF}\u2600-\u27BF]/gu, "").replace(/\s+/g, " ").trim();
  return normalized.length > 48 ? normalized.slice(0, 47).trimEnd() + "…" : normalized;
}

function composeDocumentTitle() {
  let title = "";
  if ($("#onboarding-dialog")?.open) title = "Quick Tour";
  else if ($("#config-editor-dialog")?.open) title = "Advanced Settings";
  else if ($("#agent-detail-dialog")?.open) title = titleSegment(state.runLogAgent?.label) + " — Agent";
  else if ($("#role-editor")?.open) title = titleSegment(roleDisplayName(roleRecord($("#role-field-id")?.value))) + " — Role";
  else if ($("#asset-dialog")?.open) {
    const item = assetItems().find((candidate) => assetIdentity(candidate) === state.selectedAssetIdentity);
    title = titleSegment(assetLabel(item)) + " — Asset";
  } else {
    const labels = { overview: "Overview", agents: "Agents", labs: "Labs", roles: "Roles", review: "Review", assets: "Assets", diagnostics: "Diagnostics", settings: "Settings" };
    title = labels[state.view] || "";
    const project = state.projectId !== "all" ? projectGroups().find((item) => item.id === state.projectId) : null;
    if (project) title = titleSegment(project.label) + " — " + title;
  }
  const base = (title ? title + " · " : "") + "SWARM HQ";
  return $(".app-shell")?.classList.contains("is-disconnected") ? "Offline — " + base : base;
}

function updateDocumentTitle() { document.title = composeDocumentTitle(); }

function writeRoute(mode = "replace", hashOverride = "") {
  const method = mode === "push" ? "pushState" : "replaceState";
  const next = routeURL(state.view, state.projectId, hashOverride);
  const current = location.pathname + location.search + location.hash;
  if (next !== current) history[method]({ view: state.view, projectId: state.projectId }, "", next);
  lastAppliedHistoryRoute = next;
}

function setView(view, focus = false, syncRoute = true, historyMode = "push") {
  const selectedView = TOP_LEVEL_VIEWS.includes(view) ? view : "overview";
  if (selectedView !== "roles" && state.roleDetailOpen) closeMobileRoleDetail(false);
  state.view = selectedView;
  const titles = {
    overview: ["Overview", "Portfolio progress and project scope."],
    agents: ["Agents", "Active ownership and current work."],
    labs: ["Labs", "Preconfigured teams for outcome-driven work."],
    roles: ["Roles", "Profession manifests and role defaults."],
    review: ["Review", "Proof, decisions, and handoff acknowledgements."],
    assets: ["Assets", "Approved project and role assets."],
    diagnostics: ["Diagnostics", "Live local health checks and recovery preparation."],
    settings: ["Settings", "Defaults and optional per-CTRL overrides."],
  };
  $(".app-shell").dataset.currentView = selectedView;
  $$(".nav-item[data-view]").forEach((tab) => {
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
  $$(".mobile-destination[data-view]").forEach((button) => {
    if (button.dataset.view === selectedView) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  const project = state.projectId !== "all" && !state.ctrlId ? projectGroups().find((item) => item.id === state.projectId) : null;
  $("#view-title").textContent = selectedView === "overview" && project ? project.label : titles[selectedView][0];
  $("#view-subtitle").textContent = "";
  $("#view-subtitle").hidden = true;
  if (selectedView === 'settings' && (!state.skills || state.skillsError)) refreshSkills().then(renderSettings);
  if (selectedView === 'settings' && state.token) refreshAutoStatus().then(renderSettings);
  if (selectedView === 'labs' && state.labsStatus === 'idle') refreshLabs();
  if (selectedView === 'diagnostics' && state.token && state.diagnosticsHistoryStatus === "idle") refreshDiagnostics().then(renderDiagnostics);
  if (syncRoute) writeRoute(historyMode);
  renderMessageComposer();
  updateDocumentTitle();
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
      activeNowCount: Number.isInteger(project.active_now_count) && project.active_now_count >= 0 ? project.active_now_count : null,
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
  clearCommandApprovals();
  const nextProjectId = String(projectId || "all");
  const nextCtrlId = String(ctrlId || "");
  const changed = state.projectId !== nextProjectId || state.ctrlId !== nextCtrlId;
  if (changed) {
    invalidateMessageHistory();
    state.projectUiGroupId = "";
    state.assetPage = 0;
    state.projectArtifactPage = 0;
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
  if (!items.length) {
    image.hidden = true;
    empty.hidden = false;
    failed.hidden = true;
    $("#evidence-lightbox-caption").textContent = "No image selected";
    $("#evidence-lightbox-thumbnails").innerHTML = "";
    previous.disabled = true;
    next.disabled = true;
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
  $("#evidence-lightbox-thumbnails").innerHTML = items.map((entry, index) => {
    return (
    '<button class="evidence-lightbox-thumbnail' + (index === state.evidenceIndex ? " is-selected" : "") +
    '" type="button" data-evidence-thumbnail="' + String(index) + '" data-evidence-id="' + escapeHTML(entry.evidence_id) +
    '" data-evidence-digest="' + escapeHTML(entry.digest) + '" aria-current="' + String(index === state.evidenceIndex) +
    '" aria-label="Show image ' + String(index + 1) + ': ' + escapeHTML(entry.caption || "Evidence image") +
    '"><img loading="lazy" decoding="async" src="' + proofMediaURL(entry) + '" alt=""></button>'
    );
  }).join("");
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


function usageRequestKey(projectId = state.projectId, ctrlId = state.ctrlId, hours = state.usageWindowHours, range = state.usageDateRange) {
  return projectId + "|" + ctrlId + "|" + String(hours) + (range ? '|' + range.after_ms + '|' + range.before_ms : '');
}

function usageHistorySeries() {
  if (state.usageScopeKey !== usageRequestKey() || state.usageHistory?.ok !== true) return [];
  return (Array.isArray(state.usageHistory.items) ? state.usageHistory.items : [])
    .filter((sample) => typeof sample?.bucket_ms === "number" && typeof sample?.delta_tokens === "number")
    .map((sample) => ({ bucket: Number(sample?.bucket_ms), tokens: Number(sample?.delta_tokens) }))
    .filter((sample) => Number.isFinite(sample.bucket) && sample.bucket >= 0 && Number.isFinite(sample.tokens) && sample.tokens >= 0)
    .sort((a, b) => a.bucket - b.bucket)
    .map((sample) => sample.tokens);
}

function usageRangeLabel(hours = state.usageWindowHours) {
  if (state.usageDateRange) return 'selected dates';
  return hours === 1 ? "last hour" : hours === 24 ? "last 24 hours" : hours === 720 ? "last 30 days" : "last 7 days";
}

function usageChartMarkup(surface, svgId) {
  return '<div class="usage-chart" data-usage-chart="' + surface + '"><div class="usage-range" role="group" aria-label="Usage range"><button type="button" data-usage-range="1" aria-pressed="' + String(state.usageWindowHours === 1) + '">1h</button><button type="button" data-usage-range="24" aria-pressed="' + String(state.usageWindowHours === 24) + '">24h</button><button type="button" data-usage-range="168" aria-pressed="' + String(state.usageWindowHours === 168) + '">7d</button></div><svg id="' + svgId + '" viewBox="0 0 160 28" preserveAspectRatio="none" aria-label="Usage history unavailable"></svg></div>';
}

function renderUsageCharts() {
  const detail = $("#metric-detail-dialog");
  const taskDetailOpen = detail?.open && detail.dataset.metric === "tbr";
  if (!taskDetailOpen) renderHighestUsageTasks();
  renderAccountUsage();
  renderOverviewMetric("progress", tokenBurnRatePresentation());
  if (detail?.open && ["usage", "tbr"].includes(detail.dataset.metric)) renderMetricDetail(false);
  const values = usageHistorySeries();
  const current = state.usageStatus === "current";
  const label = values.length && current
    ? "Usage during the " + usageRangeLabel() + " from " + values.length + " timestamped sample" + (values.length === 1 ? "" : "s")
    : state.usageStatus === "stale" ? "Usage history stale" : "Usage history unavailable";
  $$('[data-usage-range]').forEach((button) => button.setAttribute("aria-pressed", String(Number(button.dataset.usageRange) === state.usageWindowHours)));
  [$("#diagnostics-usage-trend"), $("#metric-detail-token-trend")].filter(Boolean).forEach((svg) => {
    drawLine(svg, current ? values : [], "#ff6a3d");
    svg.setAttribute("aria-label", label);
  });
}

function accountUsageWindows(now = Date.now()) {
  const account = state.usageHistory?.account_limits;
  if (state.usageStatus !== "current" || state.usageScopeKey !== usageRequestKey() || state.usageHistory?.ok !== true
    || account?.scope !== "account" || account.source !== "codex_app_server.account/rateLimits/read"
    || !["KNOWN", "PARTIAL"].includes(account.status) || !Number.isFinite(account.sampled_at_ms)
    || now < account.sampled_at_ms || now - account.sampled_at_ms > 300000) return [];
  return (Array.isArray(account.windows) ? account.windows : []).filter(row => row.status === "KNOWN"
    && typeof row.remaining_percent === "number" && Number.isFinite(row.remaining_percent)
    && row.remaining_percent >= 0 && row.remaining_percent <= 100
    && (row.reset_at_ms === null || Number.isFinite(row.reset_at_ms) && row.reset_at_ms > now));
}

function accountUsageDisplayWindows(now = Date.now()) {
  const current = accountUsageWindows(now);
  if (current.length || state.usageStatus !== "stale") return current;
  const account = state.usageHistory?.account_limits;
  if (state.usageScopeKey !== usageRequestKey() || state.usageHistory?.ok !== true
    || account?.scope !== "account" || account.source !== "codex_app_server.account/rateLimits/read"
    || !Number.isFinite(account.sampled_at_ms) || now < account.sampled_at_ms
    || !["KNOWN", "PARTIAL", "STALE"].includes(account.status)) return [];
  return (Array.isArray(account.windows) ? account.windows : []).filter(row => row.status === "KNOWN"
    && typeof row.remaining_percent === "number" && Number.isFinite(row.remaining_percent)
    && row.remaining_percent >= 0 && row.remaining_percent <= 100
    && (row.reset_at_ms === null || Number.isFinite(row.reset_at_ms)))
    .map(row => ({...row, status: "STALE", forecast: {status: "UNKNOWN", exhaustion_at_ms: null}, stale_sampled_at_ms: account.sampled_at_ms}));
}

function accountUsageGraph(row, includeForecast = true, window = null) {
  const points = Array.isArray(row?.history) ? row.history : [];
  if (points.length < 2 || points.some((point, index) => !Number.isFinite(point.sampled_at_ms)
    || !Number.isFinite(point.remaining_percent) || point.remaining_percent < 0 || point.remaining_percent > 100
    || index > 0 && (point.sampled_at_ms <= points[index - 1].sampled_at_ms || point.sampled_at_ms - points[index - 1].sampled_at_ms > 120000))) return '';
  const last = points.at(-1), forecast = row.forecast || {};
  const end = includeForecast && forecast.status === 'ESTIMATED' && Number.isFinite(forecast.exhaustion_at_ms) && Number.isFinite(row.reset_at_ms)
    && forecast.exhaustion_at_ms > last.sampled_at_ms && forecast.exhaustion_at_ms <= row.reset_at_ms ? forecast.exhaustion_at_ms : last.sampled_at_ms;
  const start = window?.after_ms ?? points[0].sampled_at_ms, span = Math.max(end, window?.before_ms ?? end) - start;
  const position = point => ((point.sampled_at_ms - start) / span * 160).toFixed(2) + ',' + (28 - point.remaining_percent / 100 * 28).toFixed(2);
  return '<polyline fill="none" stroke="var(--orange)" stroke-width="1.5" points="' + points.map(position).join(' ') + '"/>'
    + (end > last.sampled_at_ms ? '<path stroke="var(--orange)" stroke-dasharray="3 3" fill="none" d="M' + position(last) + ' L' + position({sampled_at_ms:end,remaining_percent:0}) + '"><title>Projected exhaustion if the recent rate continues</title></path>' : '');
}

function renderAccountUsage() {
  const rows = accountUsageDisplayWindows();
  const row = rows[0];
  renderOverviewMetric("usage", row ? {state:row.status === "STALE" ? "STALE" : state.usageHistory.account_limits.status, value:row.remaining_percent + "%", note:row.limit_id + ' · ' + row.window + (row.status === "STALE" ? ' · last observed ' + new Date(row.stale_sampled_at_ms).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : ' remaining')}
    : {state:"UNKNOWN", value:"—", note:"Remaining allowance unavailable"});
  const chart = $("#metric-usage-trend");
  chart.innerHTML = accountUsageGraph(row, false);
  chart.setAttribute('aria-label', row ? (row.status === "STALE" ? 'Last observed remaining allowance percent; refresh pending' : 'Remaining allowance percent over observed time') : 'Remaining allowance unavailable');
}

function accountUsageDetails() {
  const rows = accountUsageDisplayWindows();
  if (!rows.length) return '<p>Remaining allowance — · UNKNOWN</p><p>Quota reset —</p><p>Estimated exhaustion —</p><p>Account allowance readings are unavailable.</p>';
  return rows.map(row => {
    const forecast = row.forecast || {};
    const time = value => Number.isFinite(value) ? new Date(value).toLocaleString() : '—';
    const estimated = forecast.status === 'ESTIMATED' && Number.isFinite(forecast.exhaustion_at_ms)
      && forecast.exhaustion_at_ms > Date.now() && Number.isFinite(row.reset_at_ms) && forecast.exhaustion_at_ms <= row.reset_at_ms;
    const values = [[row.remaining_percent + '%', 'Remaining'],
      [estimated ? new Date(forecast.exhaustion_at_ms).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : '—', 'Runs out'],
      [estimated ? '~' + formatDuration(forecast.exhaustion_at_ms - Date.now()) : '—', 'At current rate']];
    const estimate = forecast.status === 'EXHAUSTED' ? 'Exhausted' : forecast.status === 'NO_MEASURABLE_BURN' ? 'No measurable burn in this interval'
      : forecast.status === 'RESET_BEFORE_EXHAUSTION' ? 'Reset occurs before projected exhaustion'
      : forecast.status === 'ESTIMATED' && Number.isFinite(forecast.exhaustion_at_ms) ? time(forecast.exhaustion_at_ms) + ' if the recent rate continues' : '—';
    const selection = state.usageHistory.window;
    const samples = state.usageHistory.account_history;
    const points = samples?.scope === 'account' && Array.isArray(samples.items) ? samples.items.filter(sample =>
      sample.account_key && sample.account_key === state.usageHistory.account_limits.account_key
      && sample.sampled_at_ms >= selection?.after_ms && sample.sampled_at_ms <= selection?.before_ms).flatMap(sample =>
      (sample.windows || []).filter(item => item.status === 'KNOWN' && item.limit_id === row.limit_id && item.window === row.window && item.reset_at_ms === row.reset_at_ms)
        .map(item => ({sampled_at_ms:sample.sampled_at_ms,remaining_percent:item.remaining_percent}))) : [];
    const chartRow = selection ? {...row,history:points,forecast:points.at(-1)?.sampled_at_ms === state.usageHistory.account_limits.sampled_at_ms ? forecast : {}} : row;
    const chart = accountUsageGraph(chartRow, true, selection);
    const graphEnd = chartRow.forecast?.status === 'ESTIMATED' && Number.isFinite(chartRow.forecast.exhaustion_at_ms) && chartRow.forecast.exhaustion_at_ms <= row.reset_at_ms ? Math.max(selection?.before_ms || 0, chartRow.forecast.exhaustion_at_ms) : selection?.before_ms;
    const axis = selection ? '<div class="metric-time-axis"><span>' + escapeHTML(time(selection.after_ms)) + '</span><span>' + escapeHTML(time(graphEnd)) + '</span></div>' : '';
    const note = row.status === 'STALE' ? 'Last observed ' + time(row.stale_sampled_at_ms) + '. Forecast withheld until the account reading recovers.' : estimated ? 'Estimate assumes the recent rate continues.' : estimate === '—' ? '' : estimate;
    return '<section><h3>' + escapeHTML(row.limit_id + ' · ' + row.window + (row.status === 'STALE' ? ' · STALE' : '')) + '</h3><div class="usage-detail-values">' + values.map(([value,label]) => '<div><strong>' + escapeHTML(value) + '</strong><span>' + label + '</span></div>').join('') + '</div><svg viewBox="0 0 160 28" role="img" aria-label="Remaining allowance percent over observed time">' + chart + '</svg>' + axis + (!chart ? '<p>Allowance history unavailable for this period.</p>' : '') + (note ? '<p>' + escapeHTML(note) + '</p>' : '') + '<p><time>' + escapeHTML(time(row.reset_at_ms)) + '</time> · Reset</p></section>';
  }).join('') + (state.usageHistory.account_limits.status === 'PARTIAL' ? '<p>Some account windows are unavailable.</p>' : '');
}

function highestUsageTaskRows() {
  if (state.usageStatus !== "current" || state.usageScopeKey !== usageRequestKey()
    || state.usageHistory?.ok !== true || !Array.isArray(state.usageHistory.task_usage)) return null;
  return state.usageHistory.task_usage.filter((row) =>
    typeof row?.thread_id === "string" && row.thread_id && (typeof row.title === "string" || row.title == null)
    && typeof row.project_id === "string" && typeof row.tokens === "number"
    && Number.isFinite(row.tokens) && row.tokens >= 0
    && (state.projectId === "all" || row.project_id === state.projectId))
    .slice().sort((left, right) => right.tokens - left.tokens || left.thread_id.localeCompare(right.thread_id)).slice(0, 10);
}

function taskUsageHistory() {
  const result = state.usageHistory, window = result?.window, history = result?.task_history;
  if (state.usageStatus !== 'current' || state.usageScopeKey !== usageRequestKey() || result?.ok !== true
    || result.hours !== state.usageWindowHours
    || !window || !Number.isFinite(window.after_ms) || !Number.isFinite(window.before_ms) || window.before_ms <= window.after_ms
    || window.before_ms > Date.now() || window.before_ms - window.after_ms > 720 * 3600000
    || !history || !Array.isArray(history.items) || !['partial','no_data'].includes(history.status)) return null;
  if (state.usageDateRange && (window.explicit !== true || window.after_ms !== state.usageDateRange.after_ms || window.before_ms !== state.usageDateRange.before_ms)) return null;
  const scope = result.scope;
  if (state.ctrlId ? scope?.type !== 'ctrl' || scope.ctrl_id !== state.ctrlId || scope.project_id !== state.projectId
    : state.projectId !== 'all' ? scope?.type !== 'project' || scope.project_id !== state.projectId : scope?.type !== 'all-projects') return null;
  const tasks = new Map((highestUsageTaskRows() || []).map(row => [row.thread_id, row]));
  const items = history.items.filter(point => tasks.get(point.thread_id)?.project_id === point.project_id
    && Number.isFinite(point.bucket_start_ms) && Number.isFinite(point.bucket_end_ms)
    && point.bucket_start_ms >= window.after_ms && point.bucket_end_ms <= window.before_ms && point.bucket_end_ms > point.bucket_start_ms
    && Number.isFinite(point.tokens) && point.tokens >= 0);
  return {...history, items, window, rateHistory:Array.isArray(result.rate_history) ? result.rate_history : []};
}

function taskUsageColor(id) {
  let hash = 0;
  for (const character of id) hash = (Math.imul(hash, 31) + character.codePointAt(0)) >>> 0;
  return 'hsl(' + ((hash * 137.508) % 360).toFixed(2) + ' 70% 65%)';
}

function taskUsageGraph(rows, history) {
  if (!history) return '<p class="empty-state" role="status">Task history unavailable.</p>';
  if (!rows.length) return '<p class="empty-state" role="status">All task series hidden. Select a task in the legend to show it.</p>';
  return usageRateGraph(rows.map(row => ({row, points:history.items.filter(point => point.thread_id === row.thread_id)})), history.window);
}

function usageRateGraph(series, window) {
  if (!window) return '<p class="empty-state" role="status">Rate history unavailable.</p>';
  const groups = series.map(group => ({...group, points:group.points.filter(point => Number.isFinite(point.tokens_per_minute)
    && (point.status === undefined || point.status === 'observed')
    && point.tokens_per_minute >= 0 && Number.isFinite(point.rate_start_ms) && Number.isFinite(point.rate_end_ms)
    && point.rate_start_ms >= window.after_ms && point.rate_end_ms <= window.before_ms && point.rate_end_ms > point.rate_start_ms)
    .sort((a,b) => a.rate_start_ms - b.rate_start_ms)}));
  const high = Math.max(1, ...groups.flatMap(group => group.points.map(point => point.tokens_per_minute)));
  const span = window.before_ms - window.after_ms;
  const paths = groups.map(({row,points}) => {
    let previous = null;
    const d = points.map(point => {
      const x = 32 + (point.rate_end_ms - window.after_ms) / span * 576;
      const y = 170 - point.tokens_per_minute / high * 145;
      const command = !previous || point.rate_start_ms > previous.rate_end_ms ? 'M' : 'L';
      const start = 32 + (point.rate_start_ms - window.after_ms) / span * 576;
      previous = point;
      return (command === 'M' ? 'M' + start.toFixed(2) + ',' + y.toFixed(2) + ' L' : 'L') + x.toFixed(2) + ',' + y.toFixed(2);
    }).join(' ');
    return d ? '<path d="' + d + '" fill="none" stroke="' + taskUsageColor(row.thread_id) + '" stroke-width="2"><title>' + escapeHTML(row.title || 'Unnamed task') + '</title></path>' : '';
  }).join('');
  if (!paths) return '<p class="empty-state" role="status">No measured rate intervals in this period.</p>';
  const date = ms => new Date(ms).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
  return '<svg class="task-usage-graph" viewBox="0 0 640 210" role="img" aria-label="Token rates over the selected period; gaps omitted"><path class="chart-grid" d="M32 25H608M32 98H608M32 170H608"/><text x="32" y="16">' + Math.ceil(high) + ' tokens/min</text>' + paths + '<text x="32" y="198">' + escapeHTML(date(window.after_ms)) + '</text><text x="608" y="198" text-anchor="end">' + escapeHTML(date(window.before_ms)) + '</text></svg>';
}

function renderHighestUsageTasks() {
  const host = $("#highest-usage-tasks");
  if (!host) return;
  const rows = highestUsageTaskRows();
  const loading = ["idle", "loading", "refreshing"].includes(state.usageStatus);
  host.setAttribute("aria-busy", String(loading));
  const message = loading ? "Loading task usage…" : state.usageStatus === "error"
    ? "Task usage could not be loaded. Try another range or refresh."
    : state.usageStatus === "stale" ? "Task usage is stale. Refresh to see current measurements."
    : rows === null ? "Task usage is unavailable." : "No measured task usage in this period.";
  const coverage = state.usageHistory?.task_usage_status === "partial" ? '<p class="usage-task-note">Some tasks have no measurements in this period.</p>' : "";
  if (!rows?.length) { host.innerHTML = '<p class="empty-state" role="status">' + message + '</p>'; return; }
  const dialog = $('#metric-detail-dialog'), history = taskUsageHistory();
  const selected = rows.find(row => row.thread_id === dialog.dataset.taskId);
  const hiddenTasks = new Set(JSON.parse(dialog.dataset.hiddenTaskIds || '[]'));
  const graph = selected || dialog.dataset.taskView === 'graph';
  const controls = selected ? '<button class="quiet-button" type="button" data-task-usage-back>← All tasks</button><h3>' + escapeHTML(selected.title || 'Unnamed task') + '</h3>'
    : '<div class="usage-range" role="group" aria-label="Task comparison view">' + ['table','graph'].map(view => '<button type="button" data-task-usage-view="' + view + '" aria-pressed="' + ((dialog.dataset.taskView || 'table') === view) + '">' + (view === 'table' ? 'Table' : 'Graph') + '</button>').join('') + '</div>';
  const legend = graph ? '<button class="quiet-button" type="button" data-task-usage-legend aria-pressed="' + (dialog.dataset.hideLegend !== 'true') + '">Legend</button>' + (dialog.dataset.hideLegend === 'true' ? '' : '<div class="task-usage-legend">' + (selected ? [selected] : rows).map(row => '<button type="button" data-task-usage-visible="' + escapeHTML(row.thread_id) + '" aria-pressed="' + !hiddenTasks.has(row.thread_id) + '" title="Toggle task series"><i style="background:' + taskUsageColor(row.thread_id) + '" aria-hidden="true"></i>' + escapeHTML(row.title || 'Unnamed task') + '</button>').join('') + '</div>') : '';
  const table = '<table class="usage-task-table"><caption class="sr-only">Top 10 tasks · selected-period tokens</caption><thead><tr><th scope="col">Task</th><th scope="col">Model</th><th scope="col">Tokens</th><th scope="col">Share</th></tr></thead><tbody>' + rows.map(row => {
    const hasHistory = history?.items.some(point => point.thread_id === row.thread_id);
    const share = history && Number.isFinite(history.total_tokens) && history.total_tokens > 0 && row.tokens <= history.total_tokens ? (100 * row.tokens / history.total_tokens).toFixed(1) + '%' : '—';
    return '<tr><th scope="row"><button type="button" data-task-usage-id="' + escapeHTML(row.thread_id) + '"' + (hasHistory ? '' : ' disabled title="Task history unavailable"') + '><span>' + escapeHTML(row.title || 'Unnamed task') + '</span><span aria-hidden="true">›</span></button></th><td aria-label="Historical model unavailable">—</td><td>' + compactNumber(row.tokens) + ' tokens</td><td><span class="task-usage-share">' + (share === '—' ? '' : '<progress max="100" value="' + parseFloat(share) + '" aria-label="Share of measured token total"></progress>') + '<span>' + share + '</span></span></td></tr>';
  }).join('') + '</tbody></table>';
  host.innerHTML = controls + coverage + (graph ? taskUsageGraph((selected ? [selected] : rows).filter(row => !hiddenTasks.has(row.thread_id)), history) + legend : table);
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

function renderDiagnostics() {
  if (!$("#view-diagnostics")) return;
  const presentation = systemHealthPresentation();
  const checks = diagnosticChecks();
  const observed = Number(state.diagnostics?.health?.observed_at_ms || state.diagnostics?.latest?.observed_at_ms || 0);
  $("#diagnostics-health-heading").textContent = presentation.label;
  $("#diagnostics-health-note").textContent = presentation.note;
  $("#diagnostics-checked-time").textContent = observed > 0 ? "Checked " + formatRelative(observed) : "Check time unavailable";
  $(".diagnostics-hero").className = "panel diagnostics-hero " + diagnosticStatusClass(presentation.label === "Healthy" ? "PASS" : presentation.label === "Needs attention" ? "WARN" : "UNKNOWN");
  const strip = $("#diagnostics-check-strip");
  strip.innerHTML = checks.length ? checks.map((check) => {
    const id = String(check.id || "");
    const status = String(check.status || "UNKNOWN").toUpperCase();
    const detail = check.summary || check.reason || "No deterministic receipt is available.";
    return '<button type="button" role="listitem" class="diagnostics-check-token ' + diagnosticStatusClass(status) + '" data-diagnostic-inspect="' + escapeHTML(id) + '" title="' + escapeHTML(humanize(id) + ": " + detail) + '"><span aria-hidden="true"></span><strong>' + escapeHTML(humanize(id)) + '</strong><small>' + escapeHTML(status) + '</small></button>';
  }).join("") : loadingSkeletonMarkup(4);
  const list = $("#diagnostics-check-list");
  list.innerHTML = checks.length ? checks.map((check) => {
    const id = String(check.id || "");
    const status = String(check.status || "UNKNOWN").toUpperCase();
    return '<article class="diagnostics-check ' + diagnosticStatusClass(status) + '" data-diagnostic-detail="' + escapeHTML(id) + '" tabindex="-1"><span class="diagnostics-check-state">' + escapeHTML(status) + '</span><span><strong>' + escapeHTML(humanize(id)) + '</strong><small>' + escapeHTML(check.summary || "No check summary available.") + '</small></span></article>';
  }).join("") : '<p class="empty-state">Deterministic health checks are unavailable. Refresh to try again.</p>';
  const signals = checks.filter((check) => String(check.status).toUpperCase() !== "PASS");
  $("#diagnostics-signal-count").textContent = signals.length ? signals.length + " open" : "Clear";
  $("#diagnostics-signal-list").innerHTML = signals.length ? signals.map((check) => '<article class="diagnostics-signal-row ' + diagnosticStatusClass(check.status) + '"><span class="diagnostics-signal">' + escapeHTML(String(check.status || "UNKNOWN").toUpperCase()) + '</span><div><strong>' + escapeHTML(humanize(check.id)) + '</strong><p>' + escapeHTML(check.recommended_action || check.summary || "Review this local signal.") + '</p></div><button class="quiet-button" type="button" data-diagnostic-review="' + escapeHTML(String(check.id || "")) + '">Review with CTRL</button></article>').join("") : '<p class="empty-state is-clear">No actionable signals. The current deterministic checks are healthy.</p>';
  const recent = [...(state.diagnostics?.health?.incidents || []), ...(state.diagnostics?.health?.open_requests || [])];
  $("#diagnostics-log-list").innerHTML = recent.length ? recent.slice(0, 8).map((item) => '<li><span class="scope-dot is-stalled" aria-hidden="true"></span><div><strong>' + escapeHTML(item.title || item.kind || item.id || "Health signal") + '</strong><p>' + escapeHTML(item.summary || item.reason || "Review the retained health signal.") + '</p></div></li>').join("") : '<li class="is-clear"><strong>Quiet right now</strong><p>No retained incidents or requests.</p></li>';
  $("#diagnostics-all-checks-state").textContent = checks.length ? checks.length + " deterministic check" + (checks.length === 1 ? "" : "s") : "Checks unavailable";
  const healthValues = diagnosticHistorySeries();
  const healthSvg = $("#diagnostics-health-trend");
  drawLine(healthSvg, healthValues, "#ff6a3d");
  healthSvg.setAttribute("aria-label", healthValues.length ? "Health during the last hour from " + healthValues.length + " deterministic sample" + (healthValues.length === 1 ? "" : "s") : "Health history unavailable for the last hour");
  $("#diagnostics-health-chart-state").textContent = state.diagnosticsHistoryStatus === "current" ? (healthValues.length ? presentation.label : "No samples") : state.diagnosticsHistoryStatus === "stale" ? "Stale" : "Unavailable";
  renderUsageCharts();
}

function inspectDiagnosticCheck(checkId) {
  const details = $(".diagnostics-all-checks");
  details.open = true;
  requestAnimationFrame(() => $('[data-diagnostic-detail="' + CSS.escape(checkId) + '"]')?.focus({ preventScroll: false }));
}

function reviewDiagnosticWithCtrl(checkId) {
  const check = diagnosticChecks().find((item) => String(item.id) === String(checkId));
  const record = activeAgentRecords().find((item) => item.identityState === "admitted" && item.structuralRole === "CTRL" && (!check?.project_id || item.project.id === check.project_id) && (!check?.ctrl_id || item.binding?.ctrlId === check.ctrl_id));
  if (!record) {
    $("#diagnostics-signal-count").textContent = "CTRL unavailable";
    return false;
  }
  setView("agents");
  requestAnimationFrame(() => {
    const trigger = $$('[data-agent-detail]').find((item) => item.dataset.agentDetail === record.node.id && item.dataset.agentProject === record.node.project_id);
    if (trigger) openAgentDetail(trigger);
  });
  return true;
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
  const status = $("#repair-status");
  status.textContent = state.diagnosticsRepairError || (state.diagnosticsRepairPending ? "Preparing preview…" : state.diagnosticsRepairPreview ? "Preview ready. Acknowledgement is required before preparation." : "Preview the selected checks before preparing a request.");
  status.classList.toggle("is-error", Boolean(state.diagnosticsRepairError));
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

function renderProfileButton() {
  const profile = state.profile?.profile || {};
  const name = String(profile.display_name || "").trim();
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
  const avatar = safeProfileAvatarURL(profile?.avatar?.url);
  const image = $("#profile-button-image");
  image.onerror = () => {
    image.hidden = true;
    image.removeAttribute("src");
    $("#profile-initials").textContent = initials;
    $("#profile-button-placeholder").toggleAttribute("hidden", Boolean(initials));
  };
  image.hidden = !avatar;
  image.src = avatar || "";
  $("#profile-initials").textContent = avatar ? "" : initials;
  $("#profile-button-placeholder").toggleAttribute("hidden", Boolean(avatar || initials));
  $("#profile").setAttribute("aria-label", name ? "Open profile for " + name : "Open profile");
}

async function refreshProfileSummary() {
  if (state.profile) { renderProfileButton(); return; }
  try { state.profile = await api(PROFILE_API_CONTRACT.read); }
  catch { state.profile = null; }
  renderProfileButton();
}

function renderProfile() {
  const profile = state.profile?.profile || {};
  const avatar = safeProfileAvatarURL(profile?.avatar?.url);
  const preview = $("#profile-avatar-preview");
  const previewURL = state.profilePreviewUrl || avatar;
  preview.onerror = () => {
    preview.hidden = true;
    preview.removeAttribute("src");
    $("#profile-avatar-placeholder").removeAttribute("hidden");
  };
  preview.hidden = !previewURL;
  preview.src = previewURL || "";
  preview.alt = previewURL ? "Profile avatar preview" : "";
  $("#profile-avatar-placeholder").toggleAttribute("hidden", Boolean(previewURL));
  $("#profile-display-name").value = profile.display_name || "";
  $("#profile-compact-updates").checked = profile.preferences?.compact_updates === true;
  $("#profile-reduced-motion").checked = profile.preferences?.reduced_motion === true;
  $("#profile-claim-limit").textContent = "Your HQ profile and preferences stay on this device.";
  const unavailable = state.profileStatus === "unavailable";
  $("#profile-status").textContent = state.profileError || (state.profileStatus === "loading" ? "Loading profile…" : unavailable ? "Profile editing is unavailable from this server. Your current presentation remains readable." : "");
  $("#profile-save").disabled = state.profileStatus !== "current" || state.profileSaving;
  [$("#profile-display-name"), $("#profile-avatar-input"), $("#profile-compact-updates"), $("#profile-reduced-motion")].forEach((control) => control.disabled = state.profileStatus !== "current" || state.profileSaving);
  renderProfileButton();
}

async function openProfile(trigger) {
  if ($("#profile-dialog").matches(":popover-open")) { closeProfile(); return; }
  state.profileTrigger = trigger;
  state.profileStatus = "loading";
  state.profileError = "";
  state.profileUpload = null;
  if (state.profilePreviewUrl) URL.revokeObjectURL(state.profilePreviewUrl);
  state.profilePreviewUrl = "";
  const dialog = $("#profile-dialog");
  dialog.showPopover();
  trigger.setAttribute("aria-expanded", "true");
  if (state.profile) {
    state.profileStatus = "current";
    renderProfile();
    requestAnimationFrame(() => $("#profile-close")?.focus({ preventScroll: true }));
    return;
  }
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
  if (dialog.matches(":popover-open")) dialog.hidePopover();
  $("#profile").setAttribute("aria-expanded", "false");
  if (state.profilePreviewUrl) URL.revokeObjectURL(state.profilePreviewUrl);
  state.profilePreviewUrl = "";
  state.profileUpload = null;
  if (restoreFocus) state.profileTrigger?.focus({ preventScroll: true });
  state.profileTrigger = null;
}

function openSupport(trigger) {
  state.supportTrigger = trigger;
  const dialog = $("#support-dialog");
  if (!dialog.open) dialog.showModal();
  requestAnimationFrame(() => $("#support-close")?.focus({ preventScroll: true }));
}

function closeSupport(restoreFocus = true) {
  const dialog = $("#support-dialog");
  if (dialog.open) dialog.close();
  if (restoreFocus) state.supportTrigger?.focus({ preventScroll: true });
  state.supportTrigger = null;
}

function openProjectCreate() {
  $("#project-create-form").reset();
  $("#project-create-status").textContent = "Choose an existing local folder.";
  const dialog = $("#project-create-dialog");
  if (!dialog.open) dialog.showModal();
  requestAnimationFrame(() => $("#project-create-name").focus({ preventScroll: true }));
}

function closeProjectCreate(restoreFocus = true) {
  const dialog = $("#project-create-dialog");
  if (dialog.open) dialog.close();
  if (restoreFocus) $("#project-create").focus({ preventScroll: true });
}

async function createProject(event) {
  event.preventDefault();
  const submit = $("#project-create-submit");
  if (submit.disabled) return;
  submit.disabled = true;
  $("#project-create-status").textContent = "Creating project…";
  try {
    const result = await api("/api/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: $("#project-create-name").value.trim(), root: $("#project-create-root").value.trim(), acknowledge: $("#project-create-acknowledge").checked }) });
    const projectId = String(result?.project?.id || "");
    closeProjectCreate(false);
    if (projectId) {
      setProjectSelection(projectId);
      state.settingsScopeType = "project";
      state.settingsScopeId = projectId;
      setView("overview", false, false);
      writeRoute("push");
    }
    await refreshOverview(false);
  } catch (error) {
    $("#project-create-status").textContent = error.message || "Project could not be created.";
  } finally {
    submit.disabled = false;
  }
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

function tokenBurnRatePresentation(now = Date.now(), historical = false) {
  const history = state.usageHistory, reading = history?.usage_now;
  const valid = state.usageStatus === "current" && state.usageScopeKey === usageRequestKey()
    && history?.ok === true && ["ok", "partial"].includes(history.status)
    && reading?.status === "observed" && reading.source === "persisted_local_token_deltas"
    && reading.rate_coverage === 'partial' && Number.isFinite(reading.rate_observed_interval_ms) && reading.rate_observed_interval_ms > 0
    && reading.window_hours === state.usageWindowHours && Number.isFinite(reading.rate_sampled_at_ms)
    && now >= reading.rate_sampled_at_ms && (historical || now - reading.rate_sampled_at_ms <= 300000)
    && Number.isFinite(reading.rate_tokens_per_minute) && reading.rate_tokens_per_minute >= 0;
  return {state:valid ? history.status === "partial" ? "PARTIAL" : "KNOWN" : "UNKNOWN",
    value:valid ? compactMetricNumber(reading.rate_tokens_per_minute) : "—",
    note:valid ? "tokens/min · " + usageRangeLabel() : "Token burn rate unavailable", series:[]};
}

function renderOverviewMetrics() {
  const record = overviewMetricsProjectionValue(state.overview?.overview_metrics, overviewMetricsScopeId());
  const presentation = overviewMetricPresentation(record);
  $("#overview-metrics-binding").textContent = presentation.binding;
  renderOverviewMetric("active", presentation.active);
  renderOverviewMetric("attention", presentation.attention);
  drawLine($("#metric-progress-trend"), [], "#4cda85");
  $("#metric-progress-trend").setAttribute("aria-label", "Token burn rate history unavailable");
  renderUsageCharts();
  if ($("#metric-detail-dialog")?.open && !["usage", "tbr"].includes($("#metric-detail-dialog").dataset.metric)) renderMetricDetail();
}

function renderMetricDetail(refreshCharts = true) {
  const dialog = $("#metric-detail-dialog");
  const focusedRange = dialog.contains(document.activeElement) ? document.activeElement.dataset.usageRange : null;
  const focusedTask = dialog.contains(document.activeElement) ? Object.entries(document.activeElement.dataset || {}).find(([name]) => name.startsWith('taskUsage')) : null;
  const body = dialog.querySelector('.dialog-body');
  const scrollTop = body?.scrollTop || 0;
  const key = dialog.dataset.metric;
  const names = { "active-work": ["active", "Active work"], "needs-attention": ["attention", "Needs attention"], "tbr": ["progress", "TBR"], usage: ["usage", "Usage"] };
  const selected = names[key];
  if (!selected) return;
  const presentation = key === "tbr" ? tokenBurnRatePresentation(Date.now(), taskUsageHistory() !== null) : overviewMetricPresentation(overviewMetricsProjectionValue(state.overview?.overview_metrics, overviewMetricsScopeId()))[selected[0]];
  $("#metric-detail-title").textContent = selected[1];
  $("#metric-detail-actions").hidden = !["usage", "tbr"].includes(key);
  const actions = $('#metric-detail-actions');
  const supported = taskUsageHistory() !== null;
  for (const button of actions.querySelectorAll?.('[data-usage-range]') || []) {
    button.setAttribute('aria-pressed', String(!state.usageDateRange && Number(button.dataset.usageRange) === state.usageWindowHours));
    if (button.dataset.usageRange === '720') { button.disabled = !supported; button.title = supported ? 'Rolling 30 days' : 'Monthly history unavailable'; }
  }
  const dateButton = actions.querySelector?.('[type="submit"]');
  if (dateButton) dateButton.disabled = !supported;
  const dateStatus = actions.querySelector?.('#metric-date-status');
  if (supported && dateStatus?.textContent === 'Custom dates are unavailable from this server.') dateStatus.textContent = 'Choose up to 30 days, in local time.';
  const history = key === 'tbr' ? taskUsageHistory() : null;
  const taskScope = state.projectId + '|' + state.ctrlId;
  if (dialog.dataset.taskScope !== taskScope) { delete dialog.dataset.taskId; delete dialog.dataset.hiddenTaskIds; dialog.dataset.taskScope = taskScope; }
  const taskPanel = dialog.dataset.tbrPanel === 'tasks';
  const tabs = '<div class="metric-tabs" role="group" aria-label="TBR view"><button type="button" data-task-usage-panel="graph" aria-pressed="' + !taskPanel + '">Graph</button><button type="button" data-task-usage-panel="tasks" aria-pressed="' + taskPanel + '">By task</button></div>';
  $("#metric-detail-content").innerHTML = key === "usage"
    ? accountUsageDetails()
    : key === 'tbr' ? tabs + (taskPanel ? '<section class="highest-usage-section"><p>Top 10 · selected-period tokens</p><div id="highest-usage-tasks" aria-busy="true"></div></section>'
      : '<div class="usage-detail-values"><div><strong>' + escapeHTML(presentation.value) + '</strong><span>tokens/min</span></div></div>' + usageRateGraph([{row:{thread_id:'aggregate',title:'Token burn rate'},points:history?.rateHistory || []}], history?.window))
    : '<strong>' + escapeHTML(presentation.value) + '</strong><p>' + escapeHTML(presentation.note) + '</p><p>' + escapeHTML(presentation.state) + '</p><svg id="metric-detail-trend" viewBox="0 0 160 28" role="img" aria-label="Accepted metric history"></svg>' + (presentation.series?.length ? '' : '<p>History unavailable.</p>');
  if (key === "tbr") renderHighestUsageTasks();
  if (key === "usage" && refreshCharts) renderUsageCharts();
  else if (!["usage", "tbr"].includes(key)) drawLine($("#metric-detail-trend"), presentation.series || [], "var(--orange)");
  if (focusedRange) Array.from(dialog.querySelectorAll('[data-usage-range]')).find(button => button.dataset.usageRange === focusedRange)?.focus({ preventScroll: true });
  if (focusedTask) Array.from(dialog.querySelectorAll('button')).find(button => button.dataset[focusedTask[0]] === focusedTask[1])?.focus({preventScroll:true});
  if (body) body.scrollTop = scrollTop;
}

function openMetricDetail(card) {
  const dialog = $("#metric-detail-dialog");
  dialog.dataset.metric = card.dataset.overviewMetric;
  const loadDay = ["usage", "tbr"].includes(dialog.dataset.metric) && state.usageWindowHours === 1;
  if (loadDay) { state.usageWindowHours = 24; state.usageStatus = "loading"; }
  renderMetricDetail();
  dialog.onclose = () => card.isConnected && card.focus({ preventScroll: true });
  dialog.showModal();
  if (loadDay) refreshUsageHistory().then(renderUsageCharts);
}

async function applyUsageDates(event) {
  event.preventDefault();
  const form = event.currentTarget, status = $('#metric-date-status');
  if (!taskUsageHistory()) { status.textContent = 'Custom dates are unavailable from this server.'; return; }
  const after = new Date(form.elements.namedItem('after').value).getTime();
  const before = new Date(form.elements.namedItem('before').value).getTime();
  if (!Number.isFinite(after) || !Number.isFinite(before) || after < 0 || before <= after || before > Date.now() || before - after > 720 * 3600000) {
    status.textContent = 'Choose a past interval of up to 30 days.'; return;
  }
  state.usageDateRange = {after_ms:after,before_ms:before};
  state.usageStatus = 'loading';
  renderUsageCharts();
  await refreshUsageHistory();
  renderUsageCharts();
  status.textContent = state.usageStatus === 'current' ? 'Date range applied.' : state.usageError;
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
  const projection = currentProjectView();
  const views = projectWorkspaceViews(projection);
  const workspaceView = state.projectTab === "ui" ? projectWorkspaceModeView(projection, state.projectUiMode, views) : views.find((view) => view.id === state.projectTab);
  if ((state.projectTab === "ui" && state.projectUiMode === "map") || (workspaceView?.renderer === "canvas" && workspaceView.mode === "network")) requestAnimationFrame(drawProjectViewConnectors);
}

const PROJECT_WORKSPACE_RENDERERS = new Set(["document/blocks", "timeline/milestones", "canvas/network", "table/records", "gallery/grid", "gallery/list"]);
const PROJECT_WORKSPACE_EMBEDDED_TABS = new Map([
  ["view.project.overview-health", "overview"],
  ["view.project.roadmap", "roadmap"],
]);
const PROJECT_WORKSPACE_TAB_ICONS = new Map([
  ["view.project.work", "list-tree"], ["view.project.agents", "users"],
  ["document/blocks", "file-clock"], ["timeline/milestones", "clock"],
  ["canvas/network", "git-branch"], ["table/records", "list"], ["gallery/list", "image"],
]);

function projectWorkspaceTabIcon(view) {
  return PROJECT_WORKSPACE_TAB_ICONS.get(view.id) || PROJECT_WORKSPACE_TAB_ICONS.get(view.renderer + "/" + view.mode) || "";
}

function projectWorkspaceViews(projection) {
  const candidates = Array.isArray(projection?.views) && projection.views.length
    ? projection.views
    : Array.isArray(projection?.tabs) ? projection.tabs : [];
  const ids = new Set();
  const views = [];
  for (const candidate of candidates) {
    const id = typeof candidate?.id === "string" ? candidate.id.trim() : "";
    const label = typeof candidate?.label === "string" ? candidate.label.trim() : "";
    const renderer = typeof candidate?.renderer === "string" ? candidate.renderer.trim() : "";
    const mode = typeof candidate?.mode === "string" ? candidate.mode.trim() : "";
    if (!id || !label || ids.has(id) || !PROJECT_WORKSPACE_RENDERERS.has(renderer + "/" + mode) || !candidate.content || typeof candidate.content !== "object" || Array.isArray(candidate.content)) return [];
    ids.add(id);
    views.push({ ...candidate, id, label, renderer, mode });
  }
  return views;
}

function projectWorkspaceModeView(projection, modeId, views = projectWorkspaceViews(projection)) {
  const mode = (Array.isArray(projection?.modes) ? projection.modes : []).find((item) => item?.id === modeId);
  const viewId = typeof mode?.view_id === "string" && mode.view_id.trim() ? mode.view_id.trim() : mode?.id;
  return views.find((view) => view.id === viewId) || null;
}

function projectWorkspaceFlowMarkup(view) {
  const graph = view?.content?.graph || (Array.isArray(view?.content?.nodes) && Array.isArray(view?.content?.edges)
    ? { nodes: view.content.nodes, edges: view.content.edges }
    : null);
  if (!graph) return '<p class="empty-state" role="status">Flow unavailable. No accepted relationship projection is bound.</p>';
  const projection = currentProjectView();
  return projectViewMapMarkup({ ...projection, map: {
    ...graph,
    nodes: (graph.nodes || []).map((node) => ({ ...node, type: node.type || node.kind || "record", visibility: node.visibility || "visible" })),
  } }).replaceAll("App Map", escapeHTML(view.label));
}

function projectWorkspaceDocumentMarkup(view) {
  const document = view?.content?.document;
  const source = Array.isArray(document?.blocks) ? document.blocks : view?.content?.blocks;
  if (!Array.isArray(source) || source.length > 128) return '<p class="empty-state" role="status">Project brief unavailable. No accepted document projection is bound.</p>';
  if (document) {
    const blocks = source.map((block) => {
      if (block?.type === "heading" && [2, 3, 4].includes(block.level) && typeof block.text === "string" && block.text.trim()) return '<article class="project-model-block" data-project-document-block><h' + block.level + '>' + escapeHTML(block.text) + '</h' + block.level + '></article>';
      if (block?.type === "paragraph" && typeof block.text === "string" && block.text.trim()) return '<article class="project-model-block" data-project-document-block><p>' + escapeHTML(block.text) + '</p></article>';
      if (block?.type === "list" && Array.isArray(block.items) && block.items.length && block.items.every((item) => typeof item === "string" && item.trim())) return '<article class="project-model-block" data-project-document-block><ul>' + block.items.map((item) => '<li>' + escapeHTML(item) + '</li>').join("") + '</ul></article>';
      return "";
    });
    if (blocks.some((block) => !block)) return '<p class="empty-state" role="status">Project brief unavailable. The accepted document projection is malformed.</p>';
    return '<section class="project-model-document" aria-label="Project brief snapshot">' + blocks.join("") + '</section>';
  }
  const ids = new Set();
  const blocks = source.map((candidate) => {
    const id = typeof candidate?.id === "string" ? candidate.id.trim() : "";
    const label = typeof candidate?.label === "string" ? candidate.label.trim() : "";
    const text = typeof candidate?.text === "string" ? candidate.text.trim() : "";
    const kind = typeof candidate?.kind === "string" ? candidate.kind.trim() : "";
    if (!id || !label || !text || !kind || ids.has(id)) return "";
    ids.add(id);
    return '<article class="project-model-block" data-project-model-block="' + escapeHTML(id) + '"><p class="eyebrow">' + escapeHTML(humanize(kind)) + '</p><h3>' + escapeHTML(label) + '</h3><p>' + escapeHTML(text) + '</p></article>';
  });
  if (blocks.some((block) => !block)) return '<p class="empty-state" role="status">Project brief unavailable. The accepted document projection is malformed.</p>';
  return '<section class="project-model-document" aria-label="Project brief snapshot">' + (blocks.join("") || '<p class="empty-state" role="status">No accepted project brief blocks are available.</p>') + '</section>';
}

function projectWorkspaceTimelineMarkup(view) {
  const timeline = view?.content?.timeline;
  const source = Array.isArray(timeline?.events) ? timeline.events : view?.content?.milestones;
  if (!Array.isArray(source) || source.length > 128) return '<p class="empty-state" role="status">Roadmap unavailable. No accepted milestone projection is bound.</p>';
  const ids = new Set();
  const milestones = source.map((candidate) => {
    const id = typeof candidate?.id === "string" ? candidate.id.trim() : "";
    const label = typeof candidate?.label === "string" ? candidate.label.trim() : "";
    const order = timeline ? candidate?.sequence : candidate?.order;
    if (!id || !label || ids.has(id) || !Number.isInteger(order) || order < 0) return "";
    ids.add(id);
    const dependencies = Array.isArray(candidate.dependency_ids) ? candidate.dependency_ids.filter((item) => typeof item === "string" && item.trim()) : [];
    const detail = timeline ? [candidate.status, candidate.summary, candidate.exit_criteria].filter((item) => typeof item === "string" && item.trim()).join(" · ") : dependencies.length ? "After " + dependencies.join(", ") : "No declared dependency";
    return '<article data-project-milestone="' + escapeHTML(id) + '"><span>' + escapeHTML(String(order + 1)) + '</span><div><h3>' + escapeHTML(label) + '</h3><p>' + escapeHTML(detail) + '</p></div></article>';
  });
  if (milestones.some((milestone) => !milestone)) return '<p class="empty-state" role="status">Roadmap unavailable. The accepted milestone projection is malformed.</p>';
  return '<section class="project-roadmap project-model-roadmap" aria-label="Project brief roadmap">' + (milestones.join("") || '<p class="empty-state" role="status">No accepted roadmap milestones are available.</p>') + '</section>';
}

function projectWorkspaceRecordsMarkup(view) {
  const source = view?.content?.records;
  if (!Array.isArray(source) || source.length > 256) return '<p class="empty-state" role="status">Records unavailable. No accepted record projection is bound.</p>';
  const ids = new Set();
  const rows = source.map((candidate) => {
    const id = typeof candidate?.id === "string" ? candidate.id.trim() : "";
    const label = typeof candidate?.label === "string" ? candidate.label.trim() : "";
    const roles = Array.isArray(candidate?.roles) ? candidate.roles.filter((item) => typeof item === "string" && item.trim()) : [];
    if (!id || !label || ids.has(id) || roles.length !== (candidate?.roles || []).length) return "";
    ids.add(id);
    return '<tr data-project-record="' + escapeHTML(id) + '"><th scope="row">' + escapeHTML(label) + '</th><td>' + escapeHTML(roles.length ? roles.map(humanize).join(", ") : "Unknown") + '</td></tr>';
  });
  if (rows.some((row) => !row)) return '<p class="empty-state" role="status">Records unavailable. The accepted record projection is malformed.</p>';
  return '<div class="project-model-records"><table><thead><tr><th scope="col">Agent</th><th scope="col">Project role</th></tr></thead><tbody>' + rows.join("") + '</tbody></table>' + (rows.length ? "" : '<p class="empty-state" role="status">No accepted records are available.</p>') + '</div>';
}

function projectWorkRows(view) {
  const source = view?.content?.rows;
  if (!Array.isArray(source) || source.length > 512) return null;
  const rows = [];
  const byId = new Map();
  const allowedKinds = new Set(["milestone", "task", "block"]);
  for (const candidate of source) {
    const id = typeof candidate?.id === "string" ? candidate.id.trim() : "";
    const kind = typeof candidate?.kind === "string" ? candidate.kind.trim().toLowerCase() : "";
    const label = typeof candidate?.label === "string" ? candidate.label.trim() : "";
    const parentId = typeof candidate?.parent_id === "string" && candidate.parent_id.trim() ? candidate.parent_id.trim() : null;
    const depth = candidate?.depth;
    const expectedDepth = kind === "milestone" ? 0 : kind === "task" ? (parentId ? 1 : 0) : (parentId ? (byId.get(parentId)?.kind === "task" ? byId.get(parentId).depth + 1 : -1) : 0);
    if (!id || !label || byId.has(id) || !allowedKinds.has(kind) || !Number.isInteger(depth) || depth < 0 || depth > 2 || depth !== expectedDepth) return null;
    if (parentId) {
      const parent = byId.get(parentId);
      if (!parent || (kind === "task" && parent.kind !== "milestone") || (kind === "block" && parent.kind !== "task")) return null;
    }
    const progress = typeof candidate.progress_percent === "number" && Number.isFinite(candidate.progress_percent) && candidate.progress_percent >= 0 && candidate.progress_percent <= 100 ? candidate.progress_percent : null;
    const row = { ...candidate, id, kind, label, parentId, depth, progress };
    rows.push(row);
    byId.set(id, row);
  }
  return rows;
}

function projectArtifactAssociations(projection) {
  const artifactView = projectWorkspaceViews(projection).find((view) => view.renderer === "gallery" && view.mode === "list");
  const artifacts = Array.isArray(artifactView?.content?.artifacts) ? artifactView.content.artifacts : [];
  const associations = new Map();
  for (const artifact of artifacts) {
    const id = typeof artifact?.id === "string" ? artifact.id.trim() : "";
    const label = typeof artifact?.label === "string" ? artifact.label.trim() : "";
    const associatedIds = Array.isArray(artifact?.associated_ids) ? artifact.associated_ids : [];
    if (!id || !label || associatedIds.some((item) => typeof item !== "string" || !item.trim())) continue;
    associatedIds.forEach((entityId) => {
      const list = associations.get(entityId) || [];
      list.push({ id, label });
      associations.set(entityId, list);
    });
  }
  return associations;
}

function projectWorkRowMarkup(row, associations, { summary = false } = {}) {
  const owner = typeof row.owner_id === "string" && row.owner_id.trim() ? row.owner_id.trim() : "Unknown";
  const progress = row.progress == null ? "" : '<span class="project-work-progress"><progress max="100" value="' + row.progress + '" aria-label="' + escapeHTML(row.label + " progress") + '"></progress><span>' + escapeHTML(String(row.progress) + "%") + '</span></span>';
  const artifacts = (associations.get(row.id) || []).map((artifact) => '<span class="project-work-artifact" data-artifact-association="' + escapeHTML(row.id) + '" aria-label="Artifact ' + escapeHTML(artifact.label) + ' associated with ' + escapeHTML(row.label) + '"><svg class="lucide" aria-hidden="true"><use href="#lucide-paperclip"></use></svg>' + escapeHTML(artifact.label) + '</span>').join("");
  const tag = summary ? "span" : "div";
  return '<' + tag + ' class="project-work-row" role="row" data-work-kind="' + row.kind + '" data-work-id="' + escapeHTML(row.id) + '"><span class="project-work-name" role="cell"><span class="project-work-kind">' + escapeHTML(humanize(row.kind)) + '</span><strong>' + escapeHTML(row.label) + '</strong><small>' + escapeHTML(row.id) + '</small>' + (artifacts ? '<span class="project-work-artifacts">' + artifacts + '</span>' : '') + '</span><span role="cell">' + escapeHTML(owner) + '</span><span role="cell">' + progress + '</span></' + tag + '>';
}

function projectWorkspaceWorkMarkup(view) {
  const rows = projectWorkRows(view);
  if (!rows) return '<p class="empty-state" role="status">Work unavailable. The accepted hierarchy projection is malformed.</p>';
  const associations = projectArtifactAssociations(currentProjectView());
  const children = new Map();
  rows.forEach((row) => { const list = children.get(row.parentId) || []; list.push(row); children.set(row.parentId, list); });
  const render = (row) => {
    const nested = children.get(row.id) || [];
    if (row.kind === "block" || !nested.length) return projectWorkRowMarkup(row, associations);
    return '<details class="project-work-group is-' + row.kind + '" open><summary>' + projectWorkRowMarkup(row, associations, { summary: true }) + '</summary><div class="project-work-children" role="rowgroup">' + nested.map(render).join("") + '</div></details>';
  };
  const blockState = view.content.blocks_state === "UNKNOWN" ? '<p class="project-work-notice" role="status">Block details are unavailable in this accepted project model.</p>' : "";
  return '<section class="project-work" role="table" aria-label="Milestones, tasks, and blocks"><header class="project-work-row" role="row"><span role="columnheader">Work</span><span role="columnheader">Owner or agent</span><span role="columnheader">Progress</span></header>' + blockState + '<div role="rowgroup">' + (children.get(null) || []).map(render).join("") + '</div></section>';
}

function projectWorkspaceArtifactsMarkup(view) {
  const artifacts = Array.isArray(view?.content?.artifacts) ? view.content.artifacts : null;
  if (!artifacts) return '<p class="empty-state" role="status">Artifacts unavailable. No accepted artifact projection is bound.</p>';
  const collection = boundedCollectionWindow(artifacts, state.projectArtifactPage);
  state.projectArtifactPage = collection.index;
  const cards = collection.items.map((artifact) => {
    const id = typeof artifact?.id === "string" ? artifact.id.trim() : "";
    const label = typeof artifact?.label === "string" ? artifact.label.trim() : "";
    if (!id || !label) return "";
    const associated = Array.isArray(artifact.associated_ids) ? artifact.associated_ids.filter((item) => typeof item === "string" && item.trim()) : [];
    return '<article class="project-workspace-artifact" data-project-artifact="' + escapeHTML(id) + '"><svg class="lucide" aria-hidden="true"><use href="#lucide-file"></use></svg><div><h3>' + escapeHTML(label) + '</h3><p>' + escapeHTML(associated.length ? "Linked to " + associated.join(", ") : "No exact work association") + '</p></div></article>';
  }).join("");
  return '<section class="project-workspace-artifacts" aria-label="Project artifacts">' + (cards || '<p class="empty-state" role="status">No accepted artifacts are bound.</p>') + '</section>' + (artifacts.length ? collectionLoadMoreMarkup("artifacts", collection, "Project artifacts") : "");
}

function projectWorkspaceViewMarkup(view) {
  if (view.renderer === "document" && view.mode === "blocks") return projectWorkspaceDocumentMarkup(view);
  if (view.renderer === "timeline" && view.mode === "milestones") return projectWorkspaceTimelineMarkup(view);
  if (view.renderer === "canvas" && view.mode === "network") return projectWorkspaceFlowMarkup(view);
  if (view.renderer === "table" && view.mode === "records") return Array.isArray(view?.content?.records) ? projectWorkspaceRecordsMarkup(view) : projectWorkspaceWorkMarkup(view);
  if (view.renderer === "gallery" && view.mode === "grid") {
    const screens = view?.content?.screens;
    return Array.isArray(screens) ? '<section class="project-ui-screens" aria-label="Project screens">' + (screens.map(projectViewScreenMarkup).join("") || '<p class="empty-state">No accepted screen states are available.</p>') + '</section>' : '<p class="empty-state" role="status">Screens unavailable. No accepted screen projection is bound.</p>';
  }
  if (view.renderer === "gallery" && view.mode === "list") return projectWorkspaceArtifactsMarkup(view);
  return '<p class="empty-state" role="status">This project view is unavailable.</p>';
}

function projectViewFreshnessMarkup(projection) {
  return projection?.status === "STALE_LAST_ACCEPTED"
    ? '<p class="project-ui-stale" role="status">Last accepted project brief snapshot</p>'
    : "";
}

function projectWorkspaceTabMarkup(view, projection = currentProjectView()) {
  return '<section class="project-ui"><header class="project-ui-toolbar"><div><p class="eyebrow">Project view</p><h2>' + escapeHTML(view.label) + '</h2></div></header>' + projectViewFreshnessMarkup(projection) + projectWorkspaceViewMarkup(view) + '<p class="project-ui-claim">' + escapeHTML(projection?.claim_limit || "Project view is read-only.") + '</p></section>';
}

function projectViewMarkup() {
  const projection = currentProjectView();
  if (!projection) return '<p class="empty-state">UI evidence is unavailable for this project.</p>';
  const workspaceViews = projectWorkspaceViews(projection);
  const declaredModes = Array.isArray(projection.modes) ? projection.modes : [];
  const modeItems = workspaceViews.length ? declaredModes.filter((item) => projectWorkspaceModeView(projection, item?.id, workspaceViews)) : declaredModes.filter((item) => ["screens", "map"].includes(item?.id));
  if (!modeItems.some((item) => item.id === state.projectUiMode)) state.projectUiMode = modeItems[0]?.id || "screens";
  const mode = state.projectUiMode;
  const workspaceView = projectWorkspaceModeView(projection, mode, workspaceViews);
  const content = workspaceView
    ? projectWorkspaceViewMarkup(workspaceView)
    : mode === "map" ? projectViewMapMarkup(projection)
      : '<section class="project-ui-screens" aria-label="Project screens">' + ((projection.screens || []).map(projectViewScreenMarkup).join("") || '<p class="empty-state">No accepted screen states are available.</p>') + '</section>';
  return '<section class="project-ui"><header class="project-ui-toolbar"><div><p class="eyebrow">Digest-bound project view</p><h2>' + escapeHTML(projection.tab.label || "UI") + '</h2></div><div class="segmented-control" aria-label="UI view mode">' + modeItems.map((item) => {
    const selected = item.id === mode;
    return '<button type="button" data-project-ui-mode="' + escapeHTML(item.id) + '" aria-pressed="' + String(selected) + '" class="' + (selected ? "is-selected" : "") + '">' + escapeHTML(item.label) + '</button>';
  }).join("") + '</div></header>' + projectViewFreshnessMarkup(projection) + content + '<p class="project-ui-claim">' + escapeHTML(projection.claim_limit || "Project UI is read-only.") + '</p></section>';
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
  const tables = segments.map((segment) => '<section class="project-progress-segment" aria-labelledby="' + escapeHTML(segment.segment_id) + '"><header><h3 id="' + escapeHTML(segment.segment_id) + '">' + escapeHTML(segment.label) + '</h3><span>' + escapeHTML(segment.rows.length) + '</span></header>' + (segment.rows.length ? '<div class="project-progress-table-wrap"><table class="project-progress-table"><thead><tr><th scope="col">Task</th><th scope="col">State</th><th scope="col">Progress</th><th scope="col">Last accepted signal</th><th scope="col">Elapsed</th><th scope="col">ETA</th></tr></thead><tbody>' + segment.rows.map((row) => projectProgressQueueRowMarkup(row, segment.segment_id)).join("") + '</tbody></table></div>' : '<p class="empty-state">No recorded ' + (segment.segment_id === "segment.project.progress.active" ? "active" : "queued") + ' work.</p>') + '</section>').join("");
  return '<section class="panel project-progress-view" aria-labelledby="project-progress-view-title"><header class="overview-section-head"><div><p class="eyebrow">Accepted project scope</p><h2 id="project-progress-view-title">Project Progress</h2></div><p>' + (stale ? 'Last accepted identity · live fields unavailable' : 'Through event ' + escapeHTML(projection.accepted_cursor.event_seq)) + '</p></header>' + tables + '</section>';
}

function projectTabMarkup(tab, progress, nodes) {
  const workspaceViews = projectWorkspaceViews(currentProjectView());
  const workspaceView = workspaceViews.find((view) => view.id === tab);
  if (workspaceView) return projectWorkspaceTabMarkup(workspaceView);
  const embeddedView = workspaceViews.find((view) => PROJECT_WORKSPACE_EMBEDDED_TABS.get(view.id) === tab);
  const blocks = progress?.blocks || [];
  const milestones = projectMilestones(blocks);
  if (tab === "overview") {
    const efficiency = verifiedYieldItem("project", selectedProgressProjectId());
    return projectHostWorkMarkup() + '<section class="project-overview-grid">' + (embeddedView ? '<section class="panel project-model-snapshot"><header class="overview-section-head"><div><p class="eyebrow">Project brief snapshot</p><h2>' + escapeHTML(embeddedView.label) + '</h2></div></header>' + projectWorkspaceViewMarkup(embeddedView) + '</section>' : "") + projectProgressQueueMarkup(progress) + '<div class="milestone-rings">' + (milestones.length ? milestones.slice(0, 4).map(([id, items]) => { const summary = milestoneSummary(items); return '<article><div class="milestone-ring ' + (summary.percent === 100 ? "is-complete" : "") + '" style="--progress:' + (summary.percent ?? 0) + '%"><strong>' + escapeHTML(summary.percent == null ? "—" : Math.round(summary.percent) + "%") + '</strong></div><h3>' + escapeHTML(id) + '</h3><small>' + escapeHTML(summary.admitted + " / " + summary.committed + " admitted") + '</small></article>'; }).join("") : '<p class="empty-state">No measured milestones yet.</p>') + '</div>' + yieldChartMarkup(efficiency) + '<section class="panel project-updates"><header class="overview-section-head"><div><p class="eyebrow">Material events</p><h2>Latest updates</h2></div><p>Newest first</p></header>' + projectFeedMarkup(4) + '</section></section>';
  }
  if (tab === "roadmap") return (embeddedView ? '<section class="project-model-snapshot"><header class="overview-section-head"><div><p class="eyebrow">Project brief snapshot</p><h2>' + escapeHTML(embeddedView.label) + '</h2></div></header>' + projectWorkspaceViewMarkup(embeddedView) + '</section>' : "") + '<section class="project-roadmap">' + (milestones.length ? milestones.map(([id, items], index) => '<article><span>' + String(index + 1) + '</span><div><h3>' + escapeHTML(id) + '</h3><p>' + escapeHTML(items.length + " block" + (items.length === 1 ? "" : "s") + " · " + milestoneSummary(items).admitted + " admitted") + '</p></div></article>').join("") : '<p class="empty-state">No roadmap receipts yet.</p>') + '</section>';
  if (tab === "lanes") { const owners = new Map(); blocks.forEach((block) => { const id = block.owner_id || "Unassigned"; owners.set(id, [...(owners.get(id) || []), block]); }); return '<section class="project-lanes">' + ([...owners.entries()].map(([owner, items]) => '<section class="panel"><header><h3>' + escapeHTML(owner) + '</h3><span>' + items.length + '</span></header>' + items.map(projectBlockRow).join("") + '</section>').join("") || '<p class="empty-state">No owner lanes yet.</p>') + '</section>'; }
  if (tab === "proof") { const images = evidenceImagesFor(nodes); state.evidenceImages = images; return '<section class="project-proof-grid">' + (images.length ? images.map((item, index) => '<button class="asset-tile" type="button" data-evidence-open="' + index + '" aria-label="Open proof image"><img loading="lazy" src="' + proofMediaURL(item) + '" alt=""><span>' + escapeHTML(item.caption || item.kind || "Proof") + '</span></button>').join("") : '<p class="empty-state">No image proof is available for this project.</p>') + '</section>'; }
  if (tab === "ledger") return '<section class="panel project-ledger"><header class="overview-section-head"><div><p class="eyebrow">Canonical events</p><h2>Ledger</h2></div><p>' + escapeHTML(progress?.cursor?.event_seq == null ? "No cursor" : "Through " + progress.cursor.event_seq) + '</p></header>' + projectFeedMarkup(10) + '</section>';
  if (tab === "ui") return projectViewMarkup();
  return '<section class="panel run-log" data-run-log-surface="project" aria-label="Project run log"></section>';
}

function projectHostWorkMarkup() {
  const projectId = selectedProgressProjectId();
  if (!projectId) return "";
  const heading = '<header class="overview-section-head"><h2>Host work</h2></header>';
  if (!Array.isArray(state.overview?.nodes) || state.connectionStatus !== "live") {
    return '<section class="panel project-progress-view">' + heading + '<p class="empty-state" role="status">Host work unavailable' + (state.overview ? ' · Last snapshot is not current' : '') + '.</p></section>';
  }
  const nodes = scopedNodes().filter((node) => node.project_id === projectId && node.id && node.virtual !== true);
  const records = activeAgentRecords();
  const active = nodes.filter((node) => ["active", "in_progress"].includes(node.status)).length;
  const rows = nodes.map((node) => {
    const record = records.find((item) => item.node.id === node.id && item.node.project_id === projectId && item.identityState === "admitted" && item.binding);
    const title = escapeHTML(node.title || "Task name unavailable");
    const name = record ? '<button class="quiet-button" type="button" data-agent-detail="' + escapeHTML(node.id) + '" data-agent-project="' + escapeHTML(projectId) + '" data-agent-ctrl="' + escapeHTML(record.binding.ctrlId) + '">' + title + '</button>' : '<strong>' + title + '</strong>';
    return '<tr data-host-work-id="' + escapeHTML(node.id) + '"><th scope="row" data-label="Task">' + name + '<small>' + escapeHTML(node.id) + '</small></th><td data-label="Host status">' + escapeHTML(node.status || "UNKNOWN") + '</td><td data-label="Block progress"><span aria-label="Block progress UNKNOWN">—</span><small>Block progress not recorded</small></td></tr>';
  }).join("");
  return '<section class="panel project-progress-view" aria-label="Host work">' + heading + '<p>' + active + ' reported active · ' + nodes.length + ' observed</p>' + (rows ? '<div class="project-progress-table-wrap"><table class="project-progress-table"><thead><tr><th scope="col">Task</th><th scope="col">Host status</th><th scope="col">Block progress</th></tr></thead><tbody>' + rows + '</tbody></table></div>' : '<p class="empty-state">No host work observed for this scope.</p>') + '</section>';
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
  const hostSnapshot = nodes.length > 0 && state.connectionStatus === "live";
  $("#project-detail-status").textContent = state.projectProgressStatus === "stale" ? "Last received project ledger" : state.projectProgressStatus === "unavailable" ? (hostSnapshot ? "Host snapshot · provider ledger unavailable" : "Project ledger unavailable") : progress ? "Scope version " + (progress.scope_version ?? "—") : "Loading project ledger";
  const measured = progress?.status === "MEASURED" && Number.isFinite(Number(progress.percent));
  const nextGate = (progress?.blocks || []).find((block) => ["REVIEW", "WAITING_DEPENDENCY", "WAITING_EXTERNAL", "USER_PAUSED"].includes(block.lifecycle_state));
  $("#project-detail-summary").innerHTML = '<p><span>Progress</span><strong>' + escapeHTML(measured ? progress.percent + "%" : "—") + '</strong></p><p><span>Live ETA</span><strong><svg class="lucide" aria-hidden="true"><use href="#lucide-clock"></use></svg>' + escapeHTML(projectEta(nodes)) + '</strong></p><p><span>Next gate</span><strong>' + escapeHTML(nextGate ? humanize(nextGate.lifecycle_state) : "—") + '</strong></p>';
  state.projectTab = "overview";
  const tabPanel = $("#project-tab-panel");
  tabPanel.innerHTML = projectTabMarkup("overview", progress, nodes);
  scheduleProjectViewConnectors();
}

function proofReviewState(item) {
  return humanize(item.review_status || item.disposition || item.status || "Status unavailable");
}

const commandApprovals = { projectId: "", generation: 0, requests: [], attempted: new Map(), pending: false, status: "Select a project to review command requests." };

function clearCommandApprovals() {
  commandApprovals.generation++;
  commandApprovals.requests = [];
  commandApprovals.status = "Command requests unavailable until a fresh connection is restored.";
  renderCommandApprovals();
}

function renderCommandApprovals() {
  const host = $("#command-approvals");
  if (!host) return;
  const requests = state.connectionStatus === "live" && commandApprovals.projectId === selectedProgressProjectId() ? commandApprovals.requests : [];
  const labels = { accept: "Allow command", decline: "Decline command", cancel: "Decline and stop turn" };
host.innerHTML = '<header class="overview-section-head"><h2>Command requests</h2></header><p role="status">' + escapeHTML(commandApprovals.status) + '</p>' + requests.map((request, index) => '<article class="panel command-approval"><pre>' + escapeHTML(request.command) + '</pre><details><summary>Request details</summary><p>' + escapeHTML(request.root) + '</p><p>Task ' + escapeHTML(request.thread_id) + ' · Turn ' + escapeHTML(request.turn_id) + '</p><p>' + escapeHTML(request.request_digest) + '</p></details><div class="review-actions">' + request.permitted_decisions.map((decision) => '<button class="quiet-button" type="button" data-command-approval="' + index + '" data-command-decision="' + decision + '">' + labels[decision] + '</button>').join("") + '</div>' + (request.permitted_decisions.length ? '<small>Your decision is sent once to this running request.</small>' : '<p>No supported decision is offered for this request.</p>') + '</article>').join("");
  for (const attempt of commandApprovals.attempted.values()) {
    if (attempt.uncertain && attempt.projectId === selectedProgressProjectId()) host.insertAdjacentHTML("beforeend", '<p role="status">Delivery is unconfirmed for task ' + escapeHTML(attempt.threadId) + '. Do not resend; check the original task in Codex.</p>');
  }
}

async function refreshCommandApprovals() {
  if (commandApprovals.pending) return;
  const projectId = selectedProgressProjectId();
  const generation = ++commandApprovals.generation;
  commandApprovals.projectId = projectId;
  commandApprovals.requests = [];
  if (!projectId || state.connectionStatus !== "live") {
    commandApprovals.status = projectId ? "Command requests unavailable." : "Select a project to review command requests.";
    renderCommandApprovals(); return;
  }
  try {
    const result = await api("/api/tasks/approvals", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project_id:projectId}),timeoutMs:15000});
    if (generation !== commandApprovals.generation || projectId !== selectedProgressProjectId()) return;
    if (result?.ok !== true || !Array.isArray(result.requests)) throw new Error("Invalid command request response.");
    commandApprovals.requests = result.requests.filter((request) => request?.project_id === projectId &&
      ["approval_id","thread_id","turn_id","root","command","item_id","request_digest"].every((key) => typeof request[key] === "string" && request[key].length > 0) &&
      /^[a-f0-9]{64}$/i.test(request.request_digest) && ["string","number"].includes(typeof request.request_id) &&
      Array.isArray(request.permitted_decisions) && request.permitted_decisions.every((choice) => ["accept","decline","cancel"].includes(choice)) &&
      !commandApprovals.attempted.has(request.approval_id));
    commandApprovals.status = commandApprovals.requests.length ? "Review the command before sending a decision." : "No supported live command requests in this project.";
  } catch {
    if (generation !== commandApprovals.generation || projectId !== selectedProgressProjectId()) return;
    commandApprovals.requests = [];
    commandApprovals.status = "Command requests unavailable.";
  }
  renderCommandApprovals();
}

async function respondCommandApproval(index, decision) {
  const request = commandApprovals.requests[index];
  if (!request || state.connectionStatus !== "live" || request.project_id !== selectedProgressProjectId() || !request.permitted_decisions.includes(decision) || commandApprovals.attempted.has(request.approval_id)) return;
  const payload = Object.fromEntries(["approval_id","project_id","thread_id","turn_id","request_digest"].map((key) => [key,request[key]]));
  const attempt = { projectId: request.project_id, threadId: request.thread_id, uncertain: true };
  commandApprovals.attempted.set(request.approval_id, attempt);
  commandApprovals.pending = true;
  commandApprovals.requests = [];
  const generation = ++commandApprovals.generation;
  commandApprovals.status = "Sending decision…";
  renderCommandApprovals();
  $("#command-approvals").focus();
  try {
    const result = await api("/api/tasks/approvals/respond", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({...payload,decision,acknowledge:true}),timeoutMs:15000});
    if (generation !== commandApprovals.generation || request.project_id !== selectedProgressProjectId()) return;
    if (result?.ok !== true || result.status !== "SUBMITTED" || result.approval_id !== request.approval_id || result.work_completed !== false) throw new Error("Unconfirmed delivery");
    attempt.uncertain = false;
    commandApprovals.status = "Decision sent. Host acceptance and work completion are not yet confirmed.";
  } catch {
    if (generation !== commandApprovals.generation || request.project_id !== selectedProgressProjectId()) return;
    commandApprovals.status = "Decision receipt unavailable.";
  } finally {
    commandApprovals.pending = false;
  }
  renderCommandApprovals();
}

function renderReview() {
  renderCommandApprovals();
  const items = scopedProofItems();
  const status = currentProofStatus();
  $("#review-status").textContent = status === "stale" ? "Showing the last received proof" : items.length ? items.length + " proof item" + (items.length === 1 ? "" : "s") : "No proof in this scope";
  const empty = status === "stale" || status === "unavailable"
    ? stateMessageMarkup("recovery", "Proof is temporarily unavailable", "Proof will appear here when SWARM receives it again.", "review-empty")
    : stateMessageMarkup("empty", "No proof yet", "Accepted proof will appear here when it reaches this scope.", "review-empty");
  $("#review-list").innerHTML = items.length ? items.map((item) => { const image = String(item.media_type || "").startsWith("image/"); const task = String(item.task_id || ""); const digest = String(item.digest || item.evidence_id || ""); return '<article class="review-row"><div class="review-kind"><svg class="lucide" aria-hidden="true"><use href="#lucide-shield-check"></use></svg></div><div><strong>' + escapeHTML(item.caption || item.kind || item.evidence_id) + '</strong><p>' + escapeHTML([item.project_id, item.task_id, item.owner_id].filter(Boolean).join(" · ") || "Unscoped proof") + '</p><small>' + escapeHTML(proofReviewState(item) + " · " + formatRelative(item.observed_at_ms || item.updated_at)) + '</small></div><div class="review-actions"><button class="icon-button" type="button" data-review-open="' + escapeHTML(proofIdentity(item)) + '" aria-label="Open proof"' + (image ? '' : ' disabled title="No visual preview is available"') + '><svg class="lucide" aria-hidden="true"><use href="#lucide-image"></use></svg></button>' + (task ? '<button class="icon-button" type="button" data-review-task="' + escapeHTML(task) + '" aria-label="Open task" title="Open task"><svg class="lucide" aria-hidden="true"><use href="#lucide-chevron-right"></use></svg></button>' : '') + '<button class="icon-button" type="button" data-review-copy="' + escapeHTML(digest) + '" aria-label="Copy proof ID" title="Copy proof ID"><svg class="lucide" aria-hidden="true"><use href="#lucide-check"></use></svg></button><details><summary aria-label="More proof details"><svg class="lucide" aria-hidden="true"><use href="#lucide-ellipsis"></use></svg></summary><p>Digest ' + escapeHTML(digest.slice(0, 16) || "—") + ' · ' + escapeHTML(item.claim_limit || "Acceptance is recorded separately.") + '</p></details></div></article>'; }).join("") : empty;
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
  renderAssets();
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
  updateDocumentTitle();
  requestAnimationFrame(() => $("#asset-dialog-close").focus({ preventScroll: true }));
}

function closeAssetDialog() {
  const dialog = $("#asset-dialog");
  if (dialog.open) dialog.close();
  updateDocumentTitle();
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
  const loading = state.assetStatus === "loading" && !items.length;
  const collection = boundedCollectionWindow(items, state.assetPage);
  state.assetPage = collection.index;
  gallery.setAttribute("aria-busy", String(loading));
  gallery.innerHTML = loading ? loadingSkeletonMarkup() : collection.items.length ? collection.items.map(state.assetView === "grid" ? assetGridMarkup : assetListMarkup).join("") : '<p class="empty-state" role="status">' + escapeHTML(state.assetStatus === "unavailable" ? state.assetError || "Asset inventory unavailable." : state.assetProjection === "trash" ? "Trash is empty." : "No assets are available in this project.") + '</p>';
  $("#asset-gallery-pager").innerHTML = loading || !items.length ? "" : collectionLoadMoreMarkup("assets", collection, "Assets");
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

function overviewTopologyProjection(value) {
  if (!value || value.schema_version !== 1 || !["KNOWN", "PARTIAL", "EMPTY"].includes(value.state)) return null;
  return ["nodes", "tasks", "agent_edges", "task_edges", "independent_nodes"].every((field) => Array.isArray(value[field])) ? value : null;
}

function renderOverviewProjectCards() {
  const host = $("#overview-project-cards");
  if (!state.overview) {
    $("#overview-summary").textContent = "Loading team";
    host.setAttribute("aria-busy", "true");
    host.innerHTML = overviewHierarchySkeletonMarkup();
    return;
  }
  const roster = savedProjectRoster();
  if (roster.state !== "KNOWN") {
    $("#overview-summary").textContent = "Team unavailable";
    host.removeAttribute("aria-busy");
    host.innerHTML = '<p class="empty-state overview-empty" role="status">Project team is unavailable. Refresh when the console can read the host project inventory.</p>';
    return;
  }
  host.removeAttribute("aria-busy");
  const topologyProjection = overviewTopologyProjection(state.overview?.topology);
  if (!topologyProjection) {
    $("#overview-summary").textContent = "Team unavailable";
    host.innerHTML = '<p class="empty-state overview-empty" role="status">Active agent topology is unavailable. The team will appear when SWARM receives an accepted topology projection.</p>';
    return;
  }
  const records = activeAgentRecords();
  const projectById = new Map(roster.projects.map((project) => [project.id, project]));
  const grouped = new Map();
  records.filter((record) => record.identityState === "admitted").forEach((record) => {
    const projectGroup = grouped.get(record.project.id) || [];
    projectGroup.push(record);
    grouped.set(record.project.id, projectGroup);
  });
  const topologyNodes = new Map(topologyProjection.nodes.map((node) => [node.agent_id, node]));
  const cards = [...grouped.entries()].map(([projectId, projectRecords]) => {
    const project = projectById.get(projectId);
    if (!project) return "";
    const admittedIds = new Set(projectRecords.map((record) => record.node.id));
    projectRecords = projectRecords.filter((record) => {
      const topology = topologyNodes.get(record.node.id);
      const relation = topology?.parent_relation;
      return topology?.project_id === projectId && (relation?.state === "ROOT" || (relation?.state === "KNOWN" && admittedIds.has(relation.parent_agent_id)));
    });
    const byId = new Map(projectRecords.map((record) => [record.node.id, record]));
    const children = new Map(projectRecords.map((record) => [record.node.id, []]));
    const parentById = new Map();
    projectRecords.forEach((record) => {
      const topology = topologyNodes.get(record.node.id);
      const relation = topology?.parent_relation;
      const acceptedParent = relation?.state === "KNOWN" && byId.has(relation.parent_agent_id) ? relation.parent_agent_id : null;
      const parentId = acceptedParent;
      parentById.set(record.node.id, parentId);
      if (parentId) children.get(parentId).push(record);
    });
    const roots = projectRecords.filter((record) => !parentById.get(record.node.id));
    const renderBranch = (record, ancestry = new Set(), depth = 0) => {
      if (ancestry.has(record.node.id)) return "";
      const next = new Set(ancestry).add(record.node.id);
      const descendants = children.get(record.node.id) || [];
      return '<div class="overview-agent-branch" data-agent-mode="' + escapeHTML(record.structuralRole.toLowerCase()) + '">' + overviewHierarchyNodeMarkup(record, descendants, depth) + (descendants.length ? '<div class="overview-hierarchy-children">' + descendants.map((child) => renderBranch(child, next, depth + 1)).join("") + '</div>' : '') + '</div>';
    };
    const edges = [...parentById.entries()].filter(([, parentId]) => parentId).map(([childId, parentId]) => '<path data-overview-hierarchy-edge data-source="' + escapeHTML(parentId) + '" data-target="' + escapeHTML(childId) + '"></path>').join("");
    const ctrlCount = projectRecords.filter((record) => record.structuralRole === "CTRL").length;
    return '<article class="overview-hierarchy-project" data-overview-hierarchy-project="' + escapeHTML(projectId) + '"><header><button type="button" data-overview-project-id="' + escapeHTML(projectId) + '"><span class="scope-dot is-' + escapeHTML(project.status) + '" aria-hidden="true"></span><span><strong>' + escapeHTML(project.label) + '</strong><small>' + escapeHTML(String(ctrlCount) + " active CTRL" + (ctrlCount === 1 ? "" : "s")) + '</small></span></button><button class="icon-button" type="button" data-overview-project-edit="' + escapeHTML(projectId) + '" aria-label="Edit ' + escapeHTML(project.label) + ' settings"><svg class="lucide" aria-hidden="true"><use href="#lucide-settings"></use></svg></button></header><div class="overview-hierarchy-stage"><svg class="overview-hierarchy-edges" aria-hidden="true" focusable="false">' + edges + '</svg><div class="overview-hierarchy-forest">' + roots.map((record) => renderBranch(record)).join("") + '</div></div></article>';
  }).join("");
  const independent = records.filter((record) => record.identityState === "independent");
  const independentNodes = state.connectionStatus === "live" ? (state.overview?.nodes || []).filter((node) => node && node.project_id === "" && ["active", "in_progress"].includes(String(node.status || "").toLowerCase())) : [];
  const independentRecordIds = new Set(independent.map((record) => record.node.id));
  const observedIndependentNodes = independentNodes.filter((node) => !independentRecordIds.has(node.id));
  const independentItems = independent.map((record) => '<article class="overview-independent-task" title="Task ID: ' + escapeHTML(record.node.id) + '"><span class="scope-dot is-active" aria-hidden="true"></span><span><strong>' + escapeHTML(agentTaskTitle(record)) + '</strong><small>' + escapeHTML(record.presentationName + " · Anonymous · Independent task") + '</small></span></article>').join("") + observedIndependentNodes.map((node) => '<article class="overview-independent-task" title="Task ID: ' + escapeHTML(node.id) + '"><span class="scope-dot is-active" aria-hidden="true"></span><span><strong>' + escapeHTML(publicLabel(node.title || node.artifact, "Codex task")) + '</strong><small>' + escapeHTML(String(node.model || "Codex") + " · " + String(node.reasoning || "unknown") + " reasoning") + '</small></span></article>').join("");
  const independentMarkup = independentItems ? '<section class="overview-independent panel"><header><span><strong>Active host tasks</strong><small>Observed locally; no accepted project hierarchy binding</small></span></header><div>' + independentItems + '</div></section>' : "";
  const malformed = records.filter((record) => record.identityState === "malformed");
  const malformedMarkup = malformed.length ? '<section class="overview-independent panel is-error" role="alert"><header><span><strong>Role binding needs attention</strong><small>Reconnect each SWARM task to one manifest role and CTRL.</small></span></header><div>' + malformed.map((record) => '<article class="overview-independent-task" title="Task ID: ' + escapeHTML(record.node.id) + '"><span class="scope-dot is-stalled" aria-hidden="true"></span><span><strong>' + escapeHTML(agentTaskTitle(record)) + '</strong><small>' + escapeHTML(record.presentationName + " · Role binding error") + '</small></span></article>').join("") + '</div></section>' : "";
  $("#overview-summary").textContent = grouped.size ? String(grouped.size) + " active project" + (grouped.size === 1 ? "" : "s") : independentNodes.length ? String(independentNodes.length) + " active host task" + (independentNodes.length === 1 ? "" : "s") : "No active project team";
  const content = cards || independentMarkup || malformedMarkup ? cards + independentMarkup + malformedMarkup : '<p class="empty-state overview-empty" role="status">No active project team is available.</p>';
  if (!cards && !independentMarkup && !malformedMarkup) { host.innerHTML = content; return; }
  host.innerHTML = '<div class="overview-hierarchy-toolbar" role="group" aria-label="Team map controls"><button class="icon-button" type="button" data-overview-zoom="out" aria-label="Zoom out"><svg class="lucide" aria-hidden="true"><use href="#lucide-minus"></use></svg></button><button class="icon-button" type="button" data-overview-zoom="fit" aria-label="Fit team"><svg class="lucide" aria-hidden="true"><use href="#lucide-scan"></use></svg></button><button class="icon-button" type="button" data-overview-zoom="in" aria-label="Zoom in"><svg class="lucide" aria-hidden="true"><use href="#lucide-plus"></use></svg></button></div><div class="overview-hierarchy-viewport edge-scroll"><div class="overview-hierarchy-canvas">' + content + '</div></div>';
  scheduleOverviewHierarchyEdges();
}

function overviewHierarchyWorkRows(record) {
  const topology = overviewTopologyProjection(state.overview?.topology);
  if (!topology || state.connectionStatus !== "live" || !record.binding) return [];
  const owner = topology.nodes.find(node => node.agent_id === record.node.id);
  if (!owner || owner.project_id !== record.binding.projectId || owner.ctrl_id !== record.binding.ctrlId) return [];
  const seen = new Set();
  const hidden = Array.isArray(topology.hidden_tasks) ? topology.hidden_tasks : [];
  return [...topology.tasks, ...hidden].filter(task => {
    const valid = task.record_type === "TASK" && task.id === task.task_id && typeof task.task_name === "string"
      && task.manifest_identity?.state === "KNOWN" && task.project_id === owner.project_id && task.ctrl_id === owner.ctrl_id
      && task.owning_agent_id === record.node.id
      && (topology.tasks.includes(task)
        ? owner.task_ids?.includes(task.task_id) && topology.task_edges.some(edge => edge.edge_kind === "AGENT_TASK_OWNERSHIP" && edge.source === record.node.id && edge.target === task.task_id)
        : hidden.includes(task))
      && !seen.has(task.task_id);
    if (valid) seen.add(task.task_id);
    return valid;
  }).sort((a,b) => a.order - b.order || a.task_id.localeCompare(b.task_id)).map(task => {
    const blocks = Array.isArray(task.blocks) && Number.isInteger(task.scope_version) && task.scope_version > 0
      && task.blocks.every(block => block.task_id === task.task_id && block.project_id === task.project_id
        && block.ctrl_id === task.ctrl_id && block.scope_version === task.scope_version && typeof block.block_id === "string"
        && block.event_cursor?.event_id && block.event_cursor?.event_digest)
      && new Set(task.blocks.map(block => block.block_id)).size === task.blocks.length ? task.blocks : [];
    const measured = blocks.length && blocks.every(block => Number.isFinite(block.committed_weight) && block.committed_weight > 0);
    const eta = task.eta;
    const retainedEta = eta?.task_id === task.task_id && eta.project_id === task.project_id
      && eta.eta_source === 'task_owner_report' && ['planned','in_progress','blocked','complete'].includes(eta.status)
      && Number.isFinite(eta.eta_start_ms) && Number.isFinite(eta.eta_end_ms) && eta.eta_start_ms > 0
      && eta.eta_end_ms >= eta.eta_start_ms && Number.isFinite(eta.eta_observed_at_ms) && eta.eta_observed_at_ms > 0;
    return { id:task.task_id, label:task.task_name, status:task.state, blocks,
      progress:measured && Number.isFinite(task.progress) && task.progress >= 0 && task.progress <= 100 ? task.progress : null,
      eta:retainedEta ? eta : null };
  });
}

function overviewHierarchyNodeMarkup(record, descendants, depth = 0) {
  const rows = overviewHierarchyWorkRows(record);
  const visible = rows.slice(0, 3);
  const hiddenTaskCount = Math.max(0, rows.length - visible.length);
  const roleAccent = /^#[0-9a-f]{6}$/i.test(String(record.role?.accent || "")) ? record.role.accent : record.accent;
  const accent = record.structuralRole === "CTRL" ? "#ff7a18" : roleAccent;
  const ports = descendants.map((child, index) => '<i class="overview-node-port is-out" data-overview-output="' + escapeHTML(child.node.id) + '" style="--port-index:' + index + ';--port-count:' + descendants.length + '" aria-hidden="true"></i>').join("");
  const workRow = (row) => {
    const progress = typeof row.progress === "number" ? Math.max(0, Math.min(100, row.progress)) : null;
    const heading = '<span class="overview-node-work"><span>' + agentWorkStatusIcon(row) + '<strong title="' + escapeHTML(row.label) + '">' + escapeHTML(row.label) + '</strong>' + (progress === null ? "" : '<small>' + progress + '%</small>') + '</span>' + (progress === null ? "" : '<i style="--task-progress:' + progress + '%" aria-hidden="true"></i>') + '</span>';
    const estimate = row.eta ? '<small class="overview-task-estimate">Retained estimate: ' + escapeHTML(new Date(row.eta.eta_start_ms).toLocaleString()) + '–' + escapeHTML(new Date(row.eta.eta_end_ms).toLocaleString()) + ' · task owner report · observed ' + escapeHTML(new Date(row.eta.eta_observed_at_ms).toLocaleString()) + '</small>' : '';
    if (!row.blocks.length) return heading + estimate;
    return '<details class="agent-work-group"><summary>' + heading + '</summary>' + estimate + '<div class="overview-work-blocks">' + row.blocks.map(block => {
      const status = String(block.lifecycle_state || 'UNKNOWN').toUpperCase();
      const tone = ['ACCEPTED','VERIFIED','COMPLETED_COMMITTED'].includes(status) ? 'complete'
        : /FAILED|REJECTED|INVALIDATED/.test(status) ? 'failed'
        : ['ACTIVE','IN_PROGRESS','PLANNED','READY','QUEUED','REVIEW_PENDING','BLOCKED','WAITING'].includes(status) ? 'active' : 'unknown';
      const label = (block.title || block.block_id) + ' · ' + humanize(status);
      return '<details class="overview-work-block is-' + tone + '"><summary aria-label="' + escapeHTML(label) + '" title="' + escapeHTML(label) + '"><span aria-hidden="true"></span></summary><p>' + escapeHTML(label) + '</p></details>';
    }).join('') + '</div></details>';
  };
  const work = visible.map(workRow).join("") || '<p class="overview-node-work-empty">No current task received</p>';
  const hiddenLabel = hiddenTaskCount + ' more work item' + (hiddenTaskCount === 1 ? "" : "s");
  const more = hiddenTaskCount ? '<details class="overview-node-more"><summary title="' + hiddenLabel + '"><span aria-hidden="true"><svg class="lucide"><use href="#lucide-chevron-down"></use></svg></span><span class="sr-only">Show ' + hiddenLabel + '</span></summary><div>' + rows.slice(3).map(workRow).join("") + '</div></details>' : "";
  const input = depth ? '<i class="overview-node-port is-in' + (depth > 1 ? ' is-side' : '') + '" data-overview-input aria-hidden="true"></i>' : "";
  return '<article class="overview-hierarchy-node is-' + escapeHTML(record.structuralRole.toLowerCase()) + '" data-overview-hierarchy-node="' + escapeHTML(record.node.id) + '" style="--node-accent:' + escapeHTML(accent) + '">' + input + '<button class="overview-node-open" type="button" data-agent-detail="' + escapeHTML(record.node.id) + '" data-agent-project="' + escapeHTML(record.node.project_id) + '" data-agent-ctrl="' + escapeHTML(record.binding.ctrlId) + '" aria-label="Open ' + escapeHTML(record.presentationName + ", " + record.profession) + '">' + agentAvatarMarkup(record) + '<span class="overview-node-identity"><strong>' + escapeHTML(record.presentationName) + '</strong><small>' + escapeHTML(record.profession) + '</small></span></button><button class="overview-node-inspect icon-button" type="button" data-agent-inspect="' + escapeHTML(record.node.id) + '" data-agent-detail="' + escapeHTML(record.node.id) + '" data-agent-project="' + escapeHTML(record.node.project_id) + '" data-agent-ctrl="' + escapeHTML(record.binding.ctrlId) + '" aria-label="View ' + escapeHTML(record.presentationName) + ' details" title="View agent details"><svg class="lucide" aria-hidden="true"><use href="#lucide-eye"></use></svg></button><span class="overview-node-work-list">' + work + more + '</span>' + ports + '</article>';
}

function overviewHierarchySkeletonMarkup() {
  const node = '<i class="overview-hierarchy-skeleton-node"><b></b><span></span><span></span><small></small></i>';
  return '<div class="overview-hierarchy-toolbar is-skeleton" aria-hidden="true"></div><div class="overview-hierarchy-viewport"><div class="overview-hierarchy-canvas is-loading" aria-hidden="true"><svg class="overview-hierarchy-skeleton-edges" viewBox="0 0 100 48"><path d="M50 12V22H20V34M50 22H80V34"></path></svg><div class="overview-hierarchy-skeleton-tree">' + node + '<div>' + node + node + node + '</div></div></div></div>';
}

function drawOverviewHierarchyEdges() {
  $$(".overview-hierarchy-project").forEach((card) => {
    const nodes = new Map($$("[data-overview-hierarchy-node]", card).map((node) => [node.dataset.overviewHierarchyNode, node]));
    $$(".overview-hierarchy-edges", card).forEach((svg) => {
      const svgRect = svg.getBoundingClientRect();
      svg.setAttribute("viewBox", "0 0 " + svg.clientWidth + " " + svg.clientHeight);
      $$('[data-overview-hierarchy-edge]', svg).forEach((path) => {
        const source = nodes.get(path.dataset.source);
        const target = nodes.get(path.dataset.target);
        const output = source && $$('[data-overview-output]', source).find((port) => port.dataset.overviewOutput === path.dataset.target);
        const input = target?.querySelector('[data-overview-input]');
        if (!output || !input) { path.removeAttribute("d"); return; }
        const from = output.getBoundingClientRect();
        const to = input.getBoundingClientRect();
        const x1 = from.left + from.width / 2 - svgRect.left;
        const y1 = from.top + from.height / 2 - svgRect.top;
        const x2 = to.left + to.width / 2 - svgRect.left;
        const y2 = to.top + to.height / 2 - svgRect.top;
        if (input.classList.contains("is-side")) {
          const trunk = x2 - 24;
          path.setAttribute("d", "M " + x1 + " " + y1 + " V " + (y1 + 14) + " H " + trunk + " V " + y2 + " H " + x2);
        } else {
          const bend = y1 + Math.max(12, (y2 - y1) / 2);
          path.setAttribute("d", "M " + x1 + " " + y1 + " V " + bend + " H " + x2 + " V " + y2);
        }
      });
    });
  });
}

function setOverviewHierarchyZoom(action) {
  const canvas = $(".overview-hierarchy-canvas");
  if (!canvas) return;
  const current = Number(canvas.dataset.zoom || 1);
  const zoom = action === "fit" ? 1 : Math.max(.7, Math.min(1.3, current + (action === "in" ? .1 : -.1)));
  canvas.dataset.zoom = String(zoom);
  canvas.style.setProperty("--overview-zoom", String(zoom));
  scheduleOverviewHierarchyEdges();
}

function scheduleOverviewHierarchyEdges() {
  if (state.view === "overview" && state.projectId === "all") requestAnimationFrame(drawOverviewHierarchyEdges);
}

function scopedActiveHostTasks() {
  const allProjects = state.projectId === "all" && !state.ctrlId;
  const binding = state.ctrlId ? runLogBindingForCtrl(state.ctrlId) : null;
  const projectId = state.ctrlId ? binding?.projectId : selectedProgressProjectId();
  const scopeValid = allProjects || (projectId && savedProjectRoster().projects.some(project => project.id === projectId) && (!state.ctrlId || state.projectId === projectId || state.projectId === "ctrl:" + state.ctrlId || state.projectId === "all"));
  if (state.connectionStatus !== "live" || !Array.isArray(state.overview?.nodes) || !scopeValid) return null;
  return state.overview.nodes.filter(node => node && typeof node.id === "string" && node.status === "active"
    && (node.node_kind === "independent_host_task" || String(node.role || node.worker_role || "").toLowerCase() === "independent"
      || (!String(node.role || node.worker_role || "").trim() && node.agent_role == null))
    && (allProjects || node.project_id === projectId));
}

function activeCodexTasksMarkup() {
  const nodes = scopedActiveHostTasks();
  if (!nodes) return '<section class="panel"><h3>Observed host tasks</h3><p role="status">Current host activity is unavailable.</p></section>';
  return '<section class="overview-independent panel"><h3>Observed host tasks</h3><p>Live host activity · SWARM role admission and reviewed progress are separate.</p>' + (nodes.length ? nodes.map(node => '<article class="overview-independent-task" data-active-codex-task="' + escapeHTML(node.id) + '"><span class="scope-dot is-active" aria-hidden="true"></span><span><strong>' + escapeHTML(publicLabel(node.title, "Codex task")) + '</strong><small>' + escapeHTML([node.model || "Codex", node.reasoning ? String(node.reasoning) + " reasoning" : "", "Observed host task"].filter(Boolean).join(" · ")) + '</small></span><span>Active</span></article>').join("") : '<p>No active host tasks in this scope.</p>') + '</section>';
}

function renderOverviewProjects() {
  const host = $("#overview-project-rows"), roster = savedProjectRoster();
  if (roster.state !== "KNOWN") { host.innerHTML = '<p role="status">Saved projects unavailable.</p>'; return; }
  host.innerHTML = roster.projects.length ? '<table class="overview-project-table"><thead><tr><th>Project</th><th>Milestone</th><th>Progress</th></tr></thead><tbody>' + roster.projects.map(project => {
    const summary = authoritativeProgress(project.id), progress = summary?.progress;
    const percent = state.connectionStatus === "live" && summary?.freshness?.state === "fresh"
      && Number.isFinite(progress?.percent) && progress.percent >= 0 && progress.percent <= 100 ? progress.percent : null;
    const milestone = summary?.current_milestone;
    const milestoneName = state.connectionStatus === "live" && summary?.freshness?.state === "fresh"
      && milestone?.state === "KNOWN" && milestone.source === "ledger_active_task_manifest"
      && milestone.project_id === project.id && typeof milestone.name === "string" ? milestone.name : null;
    const status = project.status === "recent" ? "Recently active" : humanize(project.status);
    const observedTasks = Number.isInteger(project.taskCount) ? project.taskCount : 0;
    const activeTasks = Number.isInteger(project.activeNowCount) ? project.activeNowCount : (project.status === "active" ? 1 : 0);
    const observedLabel = observedTasks ? observedTasks + " observed task" + (observedTasks === 1 ? "" : "s") : status;
    const milestoneFallback = activeTasks ? activeTasks + " active" : observedTasks ? "No active work" : "No task activity";
    const progressMarkup = percent === null
      ? '<span class="overview-observed-progress" aria-label="Observed activity, progress unavailable">' + escapeHTML(observedLabel) + '</span><small class="overview-data-note">Completion needs an accepted receipt.</small>'
      : '<span>' + percent + '%</span><progress max="100" value="' + percent + '" aria-label="' + escapeHTML(project.label) + ' progress"></progress>';
    return '<tr><th scope="row"><button type="button" data-project-id="' + escapeHTML(project.id) + '" aria-label="' + escapeHTML(project.label + ' · ' + status) + '">' + projectScopeMark(project) + '<strong>' + escapeHTML(project.label) + '</strong></button></th><td>' + (milestoneName ? escapeHTML(milestoneName) : '<span class="overview-observed-milestone" aria-label="Current milestone unavailable; observed project activity">' + escapeHTML(milestoneFallback) + '</span>') + '</td><td>' + progressMarkup + '</td></tr>';
  }).join('') + '</tbody></table>' : '<p role="status">No saved projects.</p>';
}

function renderOverview() {
  const nodes = scopedNodes();
  renderOverviewMetrics();
  renderOverviewProjects();
  renderOverviewProjectCards();
  state.evidenceImages = evidenceImagesFor(nodes);
  if ($('#evidence-lightbox').open) renderEvidenceLightbox();
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
  return projected && !["AGENT", "TASK", "CTRL", "LEAD", "DOER", "REVIEW"].includes(projected.toUpperCase()) ? humanize(projected) : "";
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
  return scopedNodes()
    .filter((node) => observedAgentRole(node) && ["active", "in_progress"].includes(String(node.status || "").toLowerCase()))
    .map((node) => {
      const assignment = agentRoleAssignment(node);
      const role = agentRoleRecord(node);
      const profession = agentProfession(node, role);
      const binding = agentExactBinding(node);
      const independent = !node.project_id;
      const projectedName = String(node?.presentation?.display_name || "").trim();
      const projectedAccent = String(node?.presentation?.accent || node?.accent || role?.accent || "").trim();
      const identityState = independent ? "independent" : assignment && role && binding && projectedName ? "admitted" : "malformed";
      const project = projects.get(node.project_id) || { id: independent ? "independent" : String(node.project_id || "unbound"), label: independent ? "Independent" : "Project unavailable" };
      return { node, role, assignment, profession, structuralRole: observedAgentRole(node), accent: /^#[0-9a-f]{6}$/i.test(projectedAccent) ? projectedAccent : "var(--faint)", presentationName: projectedName || (independent ? "Anonymous" : "Identity unavailable"), binding, project, identityState };
    })
    .sort((left, right) => left.project.label.localeCompare(right.project.label) || (roleRank[left.structuralRole] ?? 3) - (roleRank[right.structuralRole] ?? 3) || String(left.node.artifact || left.node.title || left.node.id).localeCompare(String(right.node.artifact || right.node.title || right.node.id)));
}

function agentTaskTitle(record) {
  return String(record?.node?.artifact || record?.node?.title || "Named task unavailable");
}

function agentRoleState(record) {
  if (record.identityState === "independent") return { label: "Anonymous", detail: "Independent task", error: "" };
  if (record.identityState === "admitted") return { label: record.profession, detail: record.structuralRole, error: "" };
  return { label: "Role binding error", detail: "Reconnect this SWARM task to one valid manifest role and CTRL.", error: "role-binding-error" };
}

function messageConnectorCapability(bootstrap) {
  const capability = bootstrap?.capabilities?.hq_connector;
  const endpoint = String(capability?.endpoint || "");
  const timeoutMs = Number(capability?.timeout_ms);
  if (capability?.contract !== "swarm.universal_hq_connector.action.v1" || capability?.method !== "POST" || !/^\/api\/[a-z0-9_/-]+$/i.test(endpoint)) return null;
  return { endpoint, timeoutMs: Number.isInteger(timeoutMs) && timeoutMs >= 50 && timeoutMs <= 30_000 ? timeoutMs : 15_000 };
}

function messageRecipients() {
  return activeAgentRecords()
    .filter((record) => record.identityState === "admitted" && record.binding)
    .filter((record) => record.structuralRole === "CTRL")
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
  if (state.messageRecipientId) return null;
  const preferred = recipients.find((recipient) => recipient.structuralRole === "CTRL") || recipients[0] || null;
  state.messageRecipientId = preferred?.id || "";
  return preferred;
}

let messageHistoryRequestGeneration = 0;
let messageRosterRequestGeneration = 0;
let messageInteractionGeneration = 0;
function invalidateMessageHistory() {
  messageInteractionGeneration += 1;
  messageHistoryRequestGeneration += 1;
  messageRosterRequestGeneration += 1;
  state.messageHistory = null;
  state.messageRoster = null;
  renderMessageHistory();
}

function messageRosterProjectId() {
  if (state.connectionStatus !== "live") return "";
  const projectId = state.ctrlId ? runLogBindingForCtrl(state.ctrlId)?.projectId : selectedProgressProjectId();
  if (!projectId || (state.ctrlId && !["all", projectId, "ctrl:" + state.ctrlId].includes(state.projectId))) return "";
  return savedProjectRoster().projects.some(project => project.id === projectId) ? projectId : "";
}

async function refreshMessageConversation() {
  if (!state.messageOpen) return;
  const projectId = messageRosterProjectId();
  const generation = ++messageRosterRequestGeneration;
  const scope = JSON.stringify([state.projectId, state.ctrlId, projectId]);
  if (!projectId || state.messageRoster?.project_id !== projectId || !["AVAILABLE","PARTIAL"].includes(state.messageRoster.status)) {
    state.messageRoster = {project_id:projectId, status:projectId ? "LOADING" : "UNAVAILABLE", items:[], truncated:false};
  }
  renderMessageComposer();
  if (!projectId) return;
  try {
    const result = await api("/api/tasks/history-roster", {method:"POST", timeoutMs:15_000, body:JSON.stringify({project_id:projectId})});
    if (generation !== messageRosterRequestGeneration || !state.messageOpen || scope !== JSON.stringify([state.projectId, state.ctrlId, messageRosterProjectId()])) return;
    if (result?.project_id !== projectId || !["AVAILABLE","EMPTY","PARTIAL","UNAVAILABLE"].includes(result.status)
      || typeof result.truncated !== "boolean" || result.truncated !== (result.status === "PARTIAL")
      || !Array.isArray(result.items) || result.items.length > 500
      || result.items.some(item => !item || item.project_id !== projectId || typeof item.thread_id !== "string" || !item.thread_id || typeof item.title !== "string" || [...item.title].length > 160)
      || new Set(result.items.map(item => item.thread_id)).size !== result.items.length
      || (result.status === "AVAILABLE" && !result.items.length) || (["EMPTY","UNAVAILABLE"].includes(result.status) && result.items.length)) throw new Error("Invalid conversation roster");
    state.messageRoster = result;
  } catch {
    if (generation !== messageRosterRequestGeneration || !state.messageOpen || scope !== JSON.stringify([state.projectId, state.ctrlId, messageRosterProjectId()])) return;
    state.messageRoster = {project_id:projectId,status:"UNAVAILABLE",items:[],truncated:false};
  }
  renderMessageComposer();
  await refreshMessageHistory();
}

function messageHistoryRecipients() {
  const projectId = messageRosterProjectId();
  const roster = state.messageRoster;
  if (!projectId || roster?.project_id !== projectId || !["AVAILABLE","PARTIAL"].includes(roster.status)) return [];
  const project = savedProjectRoster().projects.find(item => item.id === projectId);
  return roster.items.map(item => ({id:item.thread_id,projectId,label:publicLabel(/[<>]/.test(item.title || "") ? "" : item.title,"Task " + item.thread_id.slice(-8)),projectLabel:project?.label || "Project"}));
}

function messageHistoryBinding() {
  const recipient = messageHistoryRecipients().find(item => item.id === state.messageRecipientId);
  return recipient ? JSON.stringify([state.projectId, state.ctrlId, recipient.projectId, recipient.id]) : "";
}

async function refreshMessageHistory() {
  if (!state.messageOpen) return;
  const generation = ++messageHistoryRequestGeneration;
  const binding = messageHistoryBinding();
  const recipient = messageHistoryRecipients().find(item => item.id === state.messageRecipientId);
  if (!binding || state.messageHistory?.binding !== binding || state.messageHistory.status !== "AVAILABLE") {
    state.messageHistory = {binding, status: recipient ? "LOADING" : "UNAVAILABLE", items: []};
  }
  renderMessageHistory();
  if (!recipient) return;
  try {
    const result = await api("/api/tasks/history", {method: "POST", timeoutMs: 15_000,
      body: JSON.stringify({project_id: recipient.projectId, thread_id: recipient.id})});
    if (generation !== messageHistoryRequestGeneration || !state.messageOpen || binding !== messageHistoryBinding()) return;
    const items = result?.items;
    if (result?.project_id !== recipient.projectId || result?.thread_id !== recipient.id
      || !["AVAILABLE", "EMPTY", "UNAVAILABLE"].includes(result.status) || typeof result.truncated !== "boolean"
      || !Array.isArray(items) || items.length > 100 || new TextEncoder().encode(JSON.stringify(items)).length > 65536
      || items.some(item => !item || typeof item.id !== "string" || !item.id || typeof item.turn_id !== "string" || !item.turn_id
        || !["user", "assistant"].includes(item.role) || typeof item.text !== "string" || [...item.text].length > 4096)
      || new Set(items.map(item => item.id)).size !== items.length
      || (result.status === "AVAILABLE") !== Boolean(items.length)
      || (result.status !== "UNAVAILABLE" && !normalizedActionDigest(result.cursor))) throw new Error("Invalid conversation snapshot");
    state.messageHistory = {...result, binding};
  } catch {
    if (generation !== messageHistoryRequestGeneration || !state.messageOpen || binding !== messageHistoryBinding()) return;
    state.messageHistory = {binding, status: "UNAVAILABLE", items: []};
  }
  renderMessageHistory();
}

function renderMessageHistory() {
  const host = $("#message-conversation-items");
  if (!host) return;
  const binding = messageHistoryBinding();
  const snapshot = binding && state.messageHistory?.binding === binding ? state.messageHistory : null;
  const status = snapshot?.status || "UNAVAILABLE";
  const roster = state.messageRoster?.project_id === messageRosterProjectId() ? state.messageRoster : null;
  const rosterStatus = $("#message-roster-status");
  if (rosterStatus) rosterStatus.textContent = !messageRosterProjectId() ? "Choose a project to view its conversations."
    : roster?.status === "LOADING" ? "Loading conversations…"
    : roster?.status === "PARTIAL" ? "Showing a limited conversation list. Some tasks may be omitted."
    : roster?.status === "EMPTY" ? "No retained conversations in this project."
    : roster?.status === "UNAVAILABLE" ? "Conversation list is unavailable. Try refreshing HQ." : "";
  $("#message-conversation-state").textContent = state.connectionStatus !== "live" ? "Conversation unavailable while HQ is disconnected."
    : !binding ? "Choose a recipient to view a conversation."
    : status === "LOADING" ? "Loading conversation…"
    : status === "EMPTY" ? "No messages yet."
    : status === "AVAILABLE" ? (snapshot.truncated ? "Showing the latest available messages. Earlier content is omitted." : "")
    : "Conversation is unavailable. Try refreshing HQ.";
  host.setAttribute("aria-busy", String(status === "LOADING"));
  const markup = status === "AVAILABLE" ? snapshot.items.map(item => '<article class="message-history-item" data-message-id="' + escapeHTML(item.id) + '"><strong>'
    + (item.role === "user" ? "You" : "Assistant") + '</strong><p>' + escapeHTML(item.text) + '</p></article>').join("") : "";
  if (host.innerHTML !== markup) host.innerHTML = markup;
}

function normalizedActionDigest(value) {
  const digest = String(value || "").toLowerCase();
  const normalized = digest.startsWith("sha256:") ? digest : "sha256:" + digest;
  return /^sha256:[0-9a-f]{64}$/.test(normalized) ? normalized : "";
}

function canonicalActionValue(value) {
  if (Array.isArray(value)) return value.map(canonicalActionValue);
  if (!value || typeof value !== "object") return value;
  return Object.keys(value).sort().reduce((record, key) => {
    if (value[key] !== undefined) record[key] = canonicalActionValue(value[key]);
    return record;
  }, {});
}

async function messageActionDigest(envelope) {
  const bytes = new TextEncoder().encode(JSON.stringify(canonicalActionValue(envelope)));
  const digest = await window.crypto.subtle.digest("SHA-256", bytes);
  return "sha256:" + [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
}

function messageCurrentViewId(projection) {
  if (state.view !== "overview" || state.projectId === "all") return state.view;
  if (state.projectTab !== "ui") return state.projectTab;
  const mode = (projection?.modes || []).find((item) => item.id === state.projectUiMode);
  return mode?.view_id || mode?.id || "";
}

function messageContextIdentity(recipient = selectedMessageRecipient()) {
  const projection = state.overview?.project_view;
  const identity = projection?.identity;
  const viewId = messageCurrentViewId(projection);
  const view = (projection?.views || []).find((item) => item?.id === viewId || String(item?.id || "").endsWith("." + viewId));
  const manifestId = String(identity?.manifest_id || "").trim();
  const manifestVersion = Number(identity?.manifest_version);
  const manifestDigest = normalizedActionDigest(identity?.manifest_digest);
  const declaredViewId = String(view?.id || identity?.view_id || "").trim();
  const viewDigest = normalizedActionDigest(view?.view_digest || identity?.view_digest);
  const sourceDigests = (Array.isArray(view?.source_digests) ? view.source_digests : identity?.source_digests || []).map(normalizedActionDigest);
  const cursor = identity?.observed_cursor || projection?.observed_cursor;
  const cursorDigest = normalizedActionDigest(cursor?.event_digest);
  if (!recipient || projection?.project_id !== recipient.projectId || state.projectId !== recipient.projectId) return null;
  if (!manifestId || !Number.isInteger(manifestVersion) || manifestVersion < 1 || !manifestDigest || !declaredViewId || declaredViewId !== viewId || !viewDigest || !sourceDigests.length || sourceDigests.some((digest) => !digest)) return null;
  if (!cursor || cursor.project_id !== recipient.projectId || !String(cursor.stream_id || "").trim() || !Number.isInteger(cursor.sequence) || cursor.sequence < 0 || !String(cursor.event_id || "").trim() || !cursorDigest) return null;
  return {
    manifest_id: manifestId,
    manifest_version: manifestVersion,
    manifest_digest: manifestDigest,
    view_id: declaredViewId,
    view_digest: viewDigest,
    source_digests: sourceDigests,
    observed_cursor: { stream_id: String(cursor.stream_id), project_id: cursor.project_id, sequence: cursor.sequence, event_id: String(cursor.event_id), event_digest: cursorDigest },
  };
}

function messageAttachments() {
  if (!Array.isArray(state.messageAttachments) || state.messageAttachments.length > 8) return null;
  const attachments = state.messageAttachments.map((item) => ({ artifact_id: String(item?.artifact_id || "").trim(), digest: normalizedActionDigest(item?.digest) }));
  return attachments.every((item) => item.artifact_id && item.digest) ? attachments : null;
}

function currentMessageArtifact() {
  if ($("#asset-dialog")?.open) {
    const asset = selectedAsset();
    const digest = normalizedActionDigest(assetTechnical(asset).digest);
    if (asset?.asset_id && digest) return { artifact_id: String(asset.asset_id), artifact_digest: digest };
  }
  if ($("#evidence-lightbox")?.open) {
    const evidence = state.evidenceImages[state.evidenceIndex];
    const digest = normalizedActionDigest(evidence?.digest);
    if (evidence?.evidence_id && digest) return { artifact_id: String(evidence.evidence_id), artifact_digest: digest };
  }
  return { artifact_id: null, artifact_digest: null };
}

function messageRequestId() {
  if (typeof window.crypto?.randomUUID === "function") return window.crypto.randomUUID();
  const values = new Uint32Array(4);
  window.crypto.getRandomValues(values);
  return "message-" + [...values].map((value) => value.toString(16).padStart(8, "0")).join("");
}

function messageImplicitContext(recipient, requestId) {
  const identity = messageContextIdentity(recipient);
  const attachments = messageAttachments();
  if (!identity || !attachments || !/^[a-z0-9][a-z0-9._:-]{7,127}$/i.test(String(requestId || ""))) return null;
  const artifact = currentMessageArtifact();
  return {
    type: "swarm.project_view_action",
    schema_version: 1,
    request_id: requestId,
    project_id: recipient.projectId,
    target_ctrl_id: recipient.targetCtrlId,
    recipient_id: recipient.id,
    view_id: identity.view_id,
    screen_id: state.view,
    state_id: state.view === "overview" && state.projectId !== "all" ? state.projectTab : "default",
    action_kind: "send_feedback",
    target: artifact.artifact_id ? { kind: "artifact", artifact_id: artifact.artifact_id } : { kind: "screen_state", screen_id: state.view, state_id: state.view === "overview" && state.projectId !== "all" ? state.projectTab : "default" },
    artifact_id: artifact.artifact_id,
    artifact_digest: artifact.artifact_digest,
    attachments,
    manifest_id: identity.manifest_id,
    manifest_version: identity.manifest_version,
    manifest_digest: identity.manifest_digest,
    view_digest: identity.view_digest,
    source_digests: identity.source_digests,
    observed_cursor: identity.observed_cursor,
  };
}

function messageActionBinding(action) {
  if (!action) return "";
  return [action.project_id, action.target_ctrl_id, action.recipient_id, action.view_id, action.screen_id, action.state_id, action.manifest_id, action.manifest_version, action.manifest_digest, action.view_digest, JSON.stringify(action.source_digests || []), action.observed_cursor?.stream_id, action.observed_cursor?.sequence, action.observed_cursor?.event_id, action.observed_cursor?.event_digest, action.artifact_id || "", action.artifact_digest || "", JSON.stringify(action.attachments || [])].join("|");
}

function messageReceiptPresentation(result, request) {
  const code = String(result?.result_code || result?.status || "").toUpperCase();
  const requestMatches = Boolean(request?.request_id) && result?.request_id === request.request_id;
  const expectedDigest = normalizedActionDigest(request?.action_digest);
  const actionDigest = normalizedActionDigest(result?.action_digest);
  if (!requestMatches || !expectedDigest || !actionDigest) return { status: "failed", clearDraft: false, reason: "SWARM returned an incomplete acknowledgement. Your draft is still here." };
  if (actionDigest !== expectedDigest) return { status: "conflict", clearDraft: false, reason: "SWARM acknowledged a different command. Your draft is still here; retry this exact message." };
  if (["ACKNOWLEDGED", "REPLAYED"].includes(code) && String(result?.result_event_id || "").trim() && normalizedActionDigest(result?.result_event_digest)) {
    return { status: "sent", clearDraft: true };
  }
  if (["STALE", "CONFLICT"].includes(code)) return { status: "conflict", clearDraft: false };
  return { status: "failed", clearDraft: false };
}

function taskMessageCapability(bootstrap) {
  const value = bootstrap?.capabilities?.task_message;
  return value?.contract === "swarm.hq_task_message.v1" && value.method === "POST" && value.endpoint === "/api/tasks/message" && value.context_endpoint === "/api/tasks/message-context" ? value : null;
}

async function taskMessageDigest(text) {
  const digest = await window.crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2, "0")).join("");
}

async function sendTaskMessage(retry) {
  const generation = messageInteractionGeneration;
  const binding = messageHistoryBinding();
  const recipient = messageHistoryRecipients().find(item => item.id === state.messageRecipientId);
  const instruction = state.messageDraft;
  const capability = state.taskMessageCapability;
  if (!capability || !state.messageOpen || !binding || !recipient || !instruction.trim() || state.messageAttachments.length || state.messageStatus === "pending") return false;
  let pending = state.messagePendingAction;
  if (pending && (!retry || pending.kind !== "task" || pending.binding !== binding || pending.instruction !== instruction || pending.retried)) return false;
  state.messageStatus = "pending";
  state.messageError = "";
  renderMessageComposer();
  try {
    if (!pending) {
      const context = await api(capability.context_endpoint, {method:"POST", timeoutMs:15000, headers:{"Content-Type":"application/json"}, body:JSON.stringify({project_id:recipient.projectId,thread_id:recipient.id})});
      if (context?.ok !== true || context.project_id !== recipient.projectId || context.target_thread_id !== recipient.id
        || context.action !== "TASK" || context.target_intent !== "EXISTING_THREAD" || context.ctrl_id !== ""
        || !/^[a-f0-9]{64}$/.test(context.root_digest || "") || !Number.isSafeInteger(context.expected_ledger_revision) || context.expected_ledger_revision < 0
        || !Number.isSafeInteger(context.submitted_at_ms) || !Number.isSafeInteger(context.expires_at_ms)
        || context.expires_at_ms - context.submitted_at_ms !== 60000 || context.expires_at_ms <= Date.now()) throw new Error("Message context is unavailable or stale. Your draft is still here.");
      const envelope = {command_id:messageRequestId(),idempotency_key:messageRequestId(),action:"TASK",project_id:context.project_id,root_digest:context.root_digest,
        ctrl_id:"",target_intent:"EXISTING_THREAD",target_thread_id:context.target_thread_id,payload_digest:await taskMessageDigest(instruction),
        expected_ledger_revision:context.expected_ledger_revision,submitted_at_ms:context.submitted_at_ms,expires_at_ms:context.expires_at_ms,target_turn_id:"",acknowledgement_required:true};
      const canonical = JSON.stringify(canonicalActionValue(envelope)).replace(/[\u007f-\uffff]/g, char => "\\u" + char.charCodeAt(0).toString(16).padStart(4,"0"));
      pending = {kind:"task",binding,instruction,envelope,digest:await taskMessageDigest(canonical),retried:false};
    } else pending.retried = true;
    if (generation !== messageInteractionGeneration || !state.messageOpen || binding !== messageHistoryBinding() || instruction !== state.messageDraft || state.messageAttachments.length) throw new Error("The recipient or draft changed. Nothing new was sent.");
    state.messagePendingAction = pending;
    const result = await api(capability.endpoint, {method:"POST",timeoutMs:15000,headers:{"Content-Type":"application/json"},body:JSON.stringify({envelope:pending.envelope,instruction:pending.instruction,acknowledge:true})});
    if (generation !== messageInteractionGeneration || !state.messageOpen || binding !== messageHistoryBinding() || instruction !== state.messageDraft) throw new Error("The message scope changed. Your draft is preserved.");
    if (result?.ok === true && result.status === "NOT_DISPATCHED" && result.definitive_non_dispatch === true && result.work_completed === false
      && result.command_id === pending.envelope.command_id && result.idempotency_key === pending.envelope.idempotency_key
      && result.command_digest === pending.digest && result.project_id === pending.envelope.project_id
      && result.target_thread_id === pending.envelope.target_thread_id && result.root_digest === pending.envelope.root_digest
      && ["SUBMISSION_EXPIRED_OR_REVISION_STALE", "RETAINED_UNSUPPORTED"].includes(result.reason)) {
      state.messagePendingAction = null;
      state.messageStatus = "failed";
      state.messageError = "Message was not dispatched. Your draft is still here. When the task is ready, send again.";
      return false;
    }
    if (result?.ok !== true || result.command_digest !== pending.digest || result.thread_id !== recipient.id || result.observed_root_digest !== pending.envelope.root_digest
      || !["RESULT","REPLAY"].includes(result.status) || typeof result.turn_id !== "string" || !result.turn_id || result.work_completed !== false) {
      throw new Error("Dispatch is unconfirmed or conflicting. Your draft is preserved; do not assume the task completed.");
    }
    state.messageReceipt = result;
    state.messageStatus = "sent";
    state.messageDraft = "";
    state.messagePendingAction = null;
    state.messageError = "";
    return true;
  } catch (error) {
    state.messageStatus = "failed";
    state.messageError = error.message || "Dispatch is unconfirmed. Your draft is preserved.";
    return false;
  } finally { renderMessageComposer(); }
}

function messageStatusCopy(recipient = selectedMessageRecipient()) {
  if (state.taskMessageCapability) {
    if (state.messageStatus === "pending") return "Pending · waiting for dispatch acknowledgement.";
    if (state.messageStatus === "sent") return "Message dispatched. Task completion is not yet verified.";
    if (state.messageError) return state.messageError;
    return state.messageAttachments.length ? "Attachments are unavailable for this task message." : "";
  }
  if (!recipient) return "No authorized CTRL is available in this project scope.";
  if (!state.messageConnector) return MESSAGE_CONNECTOR_UNAVAILABLE;
  if (!messageContextIdentity(recipient) || !messageAttachments()) return "Messaging is unavailable because this screen does not have a complete digest and cursor binding.";
  if (state.messageStatus === "pending") return "Pending · waiting for SWARM acknowledgement.";
  if (state.messageStatus === "sent") return "Sent to " + recipient.label + ".";
  if (state.messageStatus === "conflict") return state.messageError || "The project context changed. Review the message and retry.";
  if (state.messageStatus === "failed") return state.messageError || "The message was not acknowledged. Your draft is still here.";
  return "";
}

function renderMessageComposer() {
  const panel = $("#message-composer");
  if (!panel) return;
  const recipients = messageRecipients();
  const historyRecipients = messageHistoryRecipients();
  if (historyRecipients.length && !historyRecipients.some(item => item.id === state.messageRecipientId)) state.messageRecipientId = historyRecipients[0].id;
  const recipient = recipients.find(item => item.id === state.messageRecipientId) || null;
  const identity = messageContextIdentity(recipient);
  const attachments = messageAttachments();
  const retryContext = state.messagePendingAction ? messageImplicitContext(recipient, state.messagePendingAction.request_id) : null;
  const canRetry = Boolean(state.messageConnector && retryContext && messageActionBinding(retryContext) === messageActionBinding(state.messagePendingAction));
  $("#message-recipient").innerHTML = historyRecipients.length
    ? historyRecipients.map(item => '<option value="' + escapeHTML(item.id) + '"' + (item.id === state.messageRecipientId ? " selected" : "") + '>' + escapeHTML(item.label + " · " + item.projectLabel) + '</option>').join("")
    : '<option value="">No observed conversations</option>';
  $("#message-recipient").disabled = !historyRecipients.length || state.messageStatus === "pending";
  const draft = $("#message-draft");
  if (draft.value !== state.messageDraft) draft.value = state.messageDraft;
  draft.disabled = state.messageStatus === "pending";
  const send = $("#message-send");
  send.disabled = state.taskMessageCapability
    ? !messageHistoryBinding() || Boolean(state.messagePendingAction) || state.messageAttachments.length > 0 || !state.messageDraft.trim() || state.messageStatus === "pending"
    : !state.messageConnector || !identity || !attachments || !state.messageDraft.trim() || state.messageStatus === "pending";
  send.setAttribute("aria-disabled", String(send.disabled));
  send.setAttribute("aria-busy", String(state.messageStatus === "pending"));
  $("#message-retry").hidden = !["failed", "conflict"].includes(state.messageStatus);
  $("#message-retry").disabled = state.taskMessageCapability
    ? state.messageStatus === "pending" || state.messagePendingAction?.kind !== "task" || state.messagePendingAction.retried || state.messagePendingAction.binding !== messageHistoryBinding() || state.messagePendingAction.instruction !== state.messageDraft
    : !canRetry || state.messageStatus === "pending";
  $("#message-status").textContent = messageStatusCopy(recipient);
  renderMessageHistory();
  $("#message-launcher").setAttribute("aria-expanded", String(state.messageOpen));
  $("#mobile-message-action").setAttribute("aria-expanded", String(state.messageOpen));
  panel.dataset.contextAvailable = String(Boolean(identity && attachments));
}

function showMessageComposerDialog() {
  const panel = $("#message-composer");
  if (panel.open) panel.close();
  panel.setAttribute("aria-modal", String(mobileDrawerQuery.matches));
  if (mobileDrawerQuery.matches) panel.showModal();
  else panel.show();
}

function openMessageComposer(trigger) {
  if (state.messageOpen) return;
  state.messageTrigger = trigger || state.messageTrigger;
  state.messageOpen = true;
  renderMessageComposer();
  showMessageComposerDialog();
  refreshMessageConversation();
  if (!history.state?.messageComposer) history.pushState({ ...(history.state || {}), messageComposer: true }, "", location.href);
  requestAnimationFrame(() => (selectedMessageRecipient() ? $("#message-draft") : $("#message-close"))?.focus({ preventScroll: true }));
}

function closeMessageComposer(restoreFocus = true, fromHistory = false) {
  if (!fromHistory && history.state?.messageComposer) {
    history.back();
    return;
  }
  state.messageOpen = false;
  invalidateMessageHistory();
  const panel = $("#message-composer");
  if (panel.open) panel.close();
  renderMessageComposer();
  if (restoreFocus) state.messageTrigger?.focus({ preventScroll: true });
  state.messageTrigger = null;
}

function syncMessageComposerMode() {
  if (!state.messageOpen) return;
  showMessageComposerDialog();
  requestAnimationFrame(() => $("#message-draft")?.focus({ preventScroll: true }));
}

async function sendMessageFromComposer(retry = false) {
  if (state.taskMessageCapability) return sendTaskMessage(retry);
  if (state.messageStatus === "pending") return false;
  const recipient = selectedMessageRecipient();
  let request = retry ? state.messagePendingAction : null;
  if (!retry) {
    const context = messageImplicitContext(recipient, messageRequestId());
    const message = state.messageDraft.trim();
    if (context && message) {
      const envelope = { ...context, payload: { message } };
      request = { ...envelope, action_digest: await messageActionDigest(envelope) };
    }
  }
  if (!state.messageConnector || !request) {
    state.messageStatus = "unavailable";
    state.messageError = state.messageConnector ? "Messaging is unavailable because this screen does not have a complete digest and cursor binding." : MESSAGE_CONNECTOR_UNAVAILABLE;
    renderMessageComposer();
    return false;
  }
  state.messagePendingAction = request;
  state.messageStatus = "pending";
  state.messageError = "";
  state.messageReceipt = null;
  renderMessageComposer();
  try {
    const result = await api(state.messageConnector.endpoint, { method: "POST", timeoutMs: state.messageConnector.timeoutMs, headers: { "Content-Type": "application/json" }, body: JSON.stringify(request) });
    const current = messageImplicitContext(selectedMessageRecipient(), request.request_id);
    if (!current || messageActionBinding(current) !== messageActionBinding(request)) {
      state.messageStatus = "conflict";
      state.messageError = "The project context changed before SWARM acknowledged this message. Your draft is still here.";
      return false;
    }
    const presentation = messageReceiptPresentation(result, request);
    state.messageReceipt = result;
    state.messageStatus = presentation.status;
    if (presentation.clearDraft) {
      state.messageDraft = "";
      state.messageAttachments = [];
      state.messagePendingAction = null;
      state.messageError = "";
      return true;
    }
    state.messageError = presentation.reason || (presentation.status === "conflict" ? "SWARM reported a stale or conflicting context. Review the message and retry." : "SWARM returned an incomplete acknowledgement. Your draft is still here.");
    return false;
  } catch (error) {
    state.messageStatus = "failed";
    state.messageError = error.connectionFailure ? error.message + ". Your draft is still here." : (error.message || "The message was not acknowledged. Your draft is still here.");
    return false;
  } finally {
    renderMessageComposer();
    requestAnimationFrame(() => (["failed", "conflict"].includes(state.messageStatus) ? $("#message-retry") : state.messageStatus === "sent" ? $("#message-close") : $("#message-draft"))?.focus({ preventScroll: true }));
  }
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
  const roleState = agentRoleState(record);
  const interactive = record.identityState === "admitted";
  return '<button class="agent-table-row' + (roleState.error ? ' is-error' : '') + '" type="button" role="row" data-agent-detail="' + escapeHTML(record.node.id) + '" data-agent-project="' + escapeHTML(record.node.project_id || "") + '" data-agent-ctrl="' + escapeHTML(record.binding?.ctrlId || "") + '" aria-label="' + escapeHTML((interactive ? "Open " : "View ") + agentTaskTitle(record) + ", " + record.presentationName) + '" title="Task ID: ' + escapeHTML(record.node.id) + '"' + (interactive ? "" : " disabled") + '><span class="agent-table-agent" role="cell" data-label="Agent">' + agentAvatarMarkup(record) + '<span><strong>' + escapeHTML(agentTaskTitle(record)) + '</strong><small>' + escapeHTML(record.presentationName) + '</small></span></span><span class="agent-table-task" role="cell" data-label="Role"><strong>' + escapeHTML(roleState.label) + '</strong><small>' + escapeHTML(roleState.error ? roleState.detail : [roleState.detail, record.profession && record.identityState === "independent" ? record.profession : ""].filter(Boolean).join(" · ")) + '</small></span><span role="cell" data-label="Project">' + escapeHTML(record.project.label) + '</span><span role="cell" data-label="Status"><span class="state-pill ' + escapeHTML(roleState.error ? "is-warning" : status[1]) + '">' + escapeHTML(roleState.error ? "Needs attention" : status[0]) + '</span></span><span role="cell" data-label="Progress">' + agentProgressMarkup(record) + '</span><time role="cell" data-label="Updated" datetime="' + escapeHTML(updated > 0 ? new Date(updated).toISOString() : "") + '"' + (updated > 0 ? "" : ' aria-label="Last update UNKNOWN"') + '>' + escapeHTML(updatedText) + '</time><span class="agent-table-chevron" role="cell" aria-hidden="true"><svg class="lucide"><use href="#lucide-chevron-right"></use></svg></span></button>';
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

function agentProgressQueueRow(record) {
  if (state.projectId !== record?.binding?.projectId) return null;
  const projection = projectProgressQueueProjection(selectedProjectProgress());
  if (!projection || projection.status !== "CURRENT") return null;
  return projectProgressQueueSegments(projection).flatMap((segment) => segment.rows).find((row) => row.task_id === record.node.id && row.scope_binding?.ctrl_id === record.binding.ctrlId) || null;
}

function agentWorkRows(record) {
  const projection = state.overview?.project_view;
  if (!record?.binding || projection?.project_id !== record.binding.projectId) return null;
  const view = projectWorkspaceViews(projection).find((candidate) => candidate.renderer === "table" && candidate.mode === "records");
  const rows = projectWorkRows(view);
  if (!rows) return null;
  const direct = rows.find((row) => row.task_id === record.node.id && (!row.ctrl_id || row.ctrl_id === record.binding.ctrlId));
  if (!direct) return [];
  const byId = new Map(rows.map((row) => [row.id, row]));
  const included = new Set([direct.id]);
  let parent = direct.parentId ? byId.get(direct.parentId) : null;
  while (parent) { included.add(parent.id); parent = parent.parentId ? byId.get(parent.parentId) : null; }
  rows.filter((row) => row.parentId === direct.id).forEach((row) => included.add(row.id));
  return rows.filter((row) => included.has(row.id));
}

function agentWorkStatusIcon(row) {
  const status = String(row.status || row.lifecycle_state || (row.progress === 100 ? "complete" : "in progress")).toLowerCase();
  const icon = /complete|accepted|verified/.test(status) ? "check" : /block|fail|error/.test(status) ? "triangle-alert" : /wait|queue|pending/.test(status) ? "clock" : "activity";
  return '<span class="agent-work-status" role="img" aria-label="' + escapeHTML(humanize(status)) + '" title="' + escapeHTML(humanize(status)) + '"><svg class="lucide" aria-hidden="true"><use href="#lucide-' + icon + '"></use></svg></span>';
}

function agentWorkMarkup(record) {
  const rows = agentWorkRows(record);
  if (rows === null) return '<p class="empty-state" role="status">Work unavailable. No accepted project hierarchy is bound.</p>';
  if (!rows.length) return '<p class="empty-state" role="status">No exact accepted work association is available for this agent.</p>';
  const children = new Map();
  rows.forEach((row) => { const list = children.get(row.parentId) || []; list.push(row); children.set(row.parentId, list); });
  const render = (row) => {
    const nested = children.get(row.id) || [];
    const heading = '<span class="agent-work-heading">' + agentWorkStatusIcon(row) + '<span><small>' + escapeHTML(humanize(row.kind)) + '</small><strong>' + escapeHTML(row.label) + '</strong></span></span>';
    if (row.kind === "block") return '<div class="agent-work-block" data-agent-work-kind="block">' + heading + '</div>';
    return '<details class="agent-work-group is-' + escapeHTML(row.kind) + '" open><summary>' + heading + '</summary><div>' + nested.map(render).join("") + '</div></details>';
  };
  const roots = rows.filter((row) => !rows.some((candidate) => candidate.id === row.parentId));
  const blocks = rows.filter((row) => row.kind === "block");
  const blockMap = '<div class="agent-block-map" role="img" aria-label="' + escapeHTML(blocks.length ? blocks.length + " accepted block" + (blocks.length === 1 ? "" : "s") + " in this work path" : "No accepted blocks in this work path") + '">' + blocks.map((row) => '<i data-block-state="' + escapeHTML(String(row.status || row.lifecycle_state || "unknown").toLowerCase()) + '"></i>').join("") + '</div>';
  return '<div class="agent-work-tree">' + roots.map(render).join("") + '</div>' + blockMap;
}

function renderAgentDetail() {
  const record = selectedAgentRecord();
  if (!record) return false;
  const dialog = $("#agent-detail-dialog");
  const updates = selectedAgentUpdates(record);
  const queueRow = agentProgressQueueRow(record);
  $("#agent-detail-title").textContent = agentTaskTitle(record);
  $("#agent-detail-content").innerHTML = '<section class="agent-detail-identity">' + agentAvatarMarkup(record) + '<div><span class="state-pill is-active">In progress</span><h3 title="Task ID: ' + escapeHTML(record.node.id) + '">' + escapeHTML(agentTaskTitle(record)) + '</h3><p>' + escapeHTML(record.presentationName + " · " + record.profession + " · " + record.structuralRole) + '</p></div></section><dl class="agent-detail-facts"><div><dt>Project</dt><dd>' + escapeHTML(record.project.label) + '</dd></div><div><dt>Role</dt><dd>' + escapeHTML(record.profession) + '</dd></div><div><dt>Identity</dt><dd>' + escapeHTML(record.presentationName) + '</dd></div><div class="agent-detail-eta"><dt>Live ETA</dt><dd>' + progressQueueEtaMarkup(queueRow) + '</dd></div></dl><section class="agent-detail-section"><h3>Work</h3>' + agentWorkMarkup(record) + '</section><section class="agent-detail-section"><h3>Log</h3>' + (updates.length ? '<ol>' + updates.map((item) => { const observed = Number(item.observed_at_ms); const datetime = Number.isFinite(observed) && observed > 0 ? new Date(observed).toISOString() : ""; return '<li><time datetime="' + escapeHTML(datetime) + '">' + escapeHTML(formatRelative(observed)) + '</time><span>' + escapeHTML(item.summary) + '</span></li>'; }).join("") + '</ol>' : '<p class="empty-state">No retained material updates are available for this agent yet.</p>') + '</section>';
  return dialog.open;
}

function openAgentDetail(trigger) {
  const record = activeAgentRecords().find((item) => item.node.id === trigger?.dataset.agentDetail && item.node.project_id === trigger?.dataset.agentProject);
  if (record?.identityState !== "admitted" || !record.binding) return;
  state.runLogAgent = { ...record.binding, label: record.presentationName };
  state.agentUpdatesFilter = "selected";
  state.agentDetailTrigger = trigger;
  renderAgents();
  const dialog = $("#agent-detail-dialog");
  renderAgentDetail();
  if (!dialog.open) dialog.showModal();
  updateDocumentTitle();
  requestAnimationFrame(() => $("#agent-detail-close")?.focus({ preventScroll: true }));
  refreshRunLogs().then(() => { renderRunLogSurfaces(); if (dialog.open) renderAgentDetail(); });
}

function agentDetailFocusTarget(trigger) {
  if (trigger?.isConnected && trigger.getClientRects().length) return trigger;
  const matches = trigger?.dataset.agentDetail
    ? $$('[data-agent-detail]').filter((candidate) => candidate.dataset.agentDetail === trigger.dataset.agentDetail && candidate.dataset.agentProject === trigger.dataset.agentProject)
    : [];
  return matches.find((candidate) => candidate.getClientRects().length) || matches[0] || $("#agents-heading");
}

function closeAgentDetail(restoreFocus = true) {
  const dialog = $("#agent-detail-dialog");
  if (dialog.open) dialog.close();
  updateDocumentTitle();
  if (!restoreFocus) return;
  const trigger = state.agentDetailTrigger;
  agentDetailFocusTarget(trigger)?.focus?.({ preventScroll: true });
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
  const hostTasks = scopedActiveHostTasks();
  const projects = new Set(records.map((record) => record.project.id));
  $("#agents-summary").textContent = hostTasks?.length && !records.length
    ? hostTasks.length + " observed host task" + (hostTasks.length === 1 ? "" : "s") + " · no admitted agents"
    : unavailable ? "Active-agent inventory unavailable" : records.length
      ? records.length + " admitted agent" + (records.length === 1 ? "" : "s") + " across " + projects.size + " project" + (projects.size === 1 ? "" : "s")
      : "No active agents";
  $("#agents-table-status").textContent = unavailable ? "Accepted project and CTRL bindings are unavailable." : state.projectId === "all" ? "All projects" : scopeLabel();
  $("#agent-table-body").innerHTML = unavailable
    ? '<p class="empty-state agents-empty" role="status">Active agents are unavailable until SWARM receives a current project and CTRL projection.</p>'
    : records.length ? records.map(agentTableRowMarkup).join("") : '<p class="empty-state agents-empty" role="status">No admitted CTRL, LEAD, or DOER is active in this project scope.</p>';
  $("#agent-table-body").insertAdjacentHTML("beforeend", activeCodexTasksMarkup());
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
  return '<span class="role-avatar is-unavailable" style="--role-accent:' + escapeHTML(accent) + '" role="img" aria-label="Mascot avatar unavailable for ' + escapeHTML(displayName) + '; admission pending"><svg class="lucide" aria-hidden="true"><use href="#lucide-circle-user-round"></use></svg></span>';
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
    const task = node?.artifact || node?.title || "Assigned task";
    return '<li title="Task ID: ' + escapeHTML(assignment.task_id) + '"><strong>' + escapeHTML(task) + '</strong><span>' + escapeHTML(owner) + '</span></li>';
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
  return '<div class="role-instruction-preview">' + roleTextList(preview, "No instructions.") + (remaining.length ? '<details><summary><span class="role-disclosure-more">Show more</span><span class="role-disclosure-less">Show less</span></summary>' + roleTextList(remaining, "") + '</details>' : '') + '</div>';
}

function rolePresentationText(value) {
  const text = String(value || "").trim();
  return text && !/\b(?:authority|provenance|server-owned|metadata only|bounded SWARM assignment|built[ -]?in)\b/i.test(text) ? text : "";
}

function rolePresentationItems(items) {
  return (Array.isArray(items) ? items : []).map(rolePresentationText).filter(Boolean);
}

function roleCardDescription(role) {
  return rolePresentationItems(Array.isArray(role?.instructions) ? role.instructions.slice(1) : [])[0] || "";
}

function roleDetailDisclosure(label, body) {
  return '<details class="role-detail-disclosure"><summary><span>' + escapeHTML(label) + '</span><svg class="lucide" aria-hidden="true"><use href="#lucide-chevron-down"></use></svg></summary><div class="role-detail-disclosure-body">' + body + '</div></details>';
}

function roleChooserMarkup(role, match, selected) {
  const displayName = roleDisplayName(role);
  const description = roleCardDescription(role);
  return '<button class="role-choice' + (selected ? ' is-selected' : '') + '" data-role-select="' + escapeHTML(role.id) + '" id="role-choice-' + escapeHTML(role.id) + '" role="option" aria-label="' + escapeHTML(displayName) + '" aria-selected="' + String(selected) + '" aria-controls="role-library-detail" tabindex="' + (selected ? '0' : '-1') + '" type="button">' + roleAvatar(role) + '<span><strong>' + escapeHTML(displayName) + '</strong>' + (description ? '<p class="role-choice-description" title="' + escapeHTML(description) + '">' + escapeHTML(description) + '</p>' : '') + (match.label ? '<em>' + escapeHTML(match.label) + '</em>' : '') + '</span></button>';
}

function roleDetailMarkup(role, match = { label: "" }) {
  if (!role) return '<p class="empty-state">Choose a role to see its details.</p>';
  const displayName = roleDisplayName(role);
  const avatarButton = '<button class="role-avatar-trigger" data-role-action="avatar" data-role-id="' + escapeHTML(role.id) + '" type="button" aria-label="Edit ' + escapeHTML(displayName) + ' avatar" title="Edit avatar">' + roleAvatar(role) + '</button>';
  const purpose = rolePresentationText(role.purpose);
  const owns = rolePresentationItems(role.owns);
  const instructions = rolePresentationItems(role.instructions);
  const skills = rolePresentationItems(role.default_skills);
  const boundaries = rolePresentationItems(role.boundaries);
  const sections = [
    purpose ? roleDetailDisclosure("Purpose", '<p class="role-detail-copy">' + escapeHTML(purpose) + '</p>') : "",
    owns.length ? roleDetailDisclosure("Owns", roleTextList(owns, "")) : "",
    instructions.length ? roleDetailDisclosure("Instructions", roleInstructionsMarkup(instructions)) : "",
    roleDetailDisclosure("Current owners", roleAssignmentsMarkup(role.id)),
    Array.isArray(role.specializations) && role.specializations.length ? roleDetailDisclosure("Specializations", roleSpecializationsMarkup(role)) : "",
    skills.length ? roleDetailDisclosure("Default skills", roleTextList(skills, "")) : "",
    boundaries.length ? roleDetailDisclosure("Boundaries", roleTextList(boundaries, "")) : "",
  ].join("");
  return '<button class="role-detail-back" type="button" data-role-detail-back aria-label="Back to roles"><svg class="lucide" aria-hidden="true"><use href="#lucide-arrow-left"></use></svg><span>Back</span></button><header class="role-detail-head">' + avatarButton + '<div><h3 id="role-detail-title">' + escapeHTML(displayName) + '</h3></div></header>' + (match.label ? '<p class="role-match">' + escapeHTML(match.label) + '</p>' : '') + '<div class="role-detail-sections">' + sections + '</div>';
}

function focusRoleChoice(roleId) {
  if (!roleId) return;
  const choice = $('[data-role-select="' + CSS.escape(roleId) + '"]');
  choice?.focus({ preventScroll: true });
  choice?.scrollIntoView({ block: "nearest", inline: "nearest" });
}

function isMobileRoleDetail() {
  return matchMedia("(max-width: 620px)").matches;
}

function roleDetailFocusable() {
  return $$('#role-library-detail button:not([disabled]),#role-library-detail summary,#role-library-detail a[href],#role-library-detail [tabindex]:not([tabindex="-1"])').filter((element) => !element.hidden);
}

function syncRoleDetailPresentation() {
  const detail = $("#role-library-detail");
  if (!detail) return;
  const mobile = isMobileRoleDetail();
  if (!mobile && state.roleDetailOpen) {
    state.roleDetailOpen = false;
    state.roleDetailTriggerId = "";
  }
  const open = mobile && state.roleDetailOpen;
  detail.hidden = mobile && !open;
  detail.classList.toggle("is-mobile-open", open);
  if (open) {
    detail.setAttribute("role", "dialog");
    detail.setAttribute("aria-modal", "true");
  } else {
    detail.removeAttribute("role");
    detail.removeAttribute("aria-modal");
  }
  document.body.classList.toggle("role-detail-open", open);
}

function closeMobileRoleDetail(restoreFocus = true) {
  if (!state.roleDetailOpen) return;
  const roleId = state.roleDetailTriggerId || state.selectedRoleId;
  state.roleDetailOpen = false;
  state.roleDetailTriggerId = "";
  syncRoleDetailPresentation();
  if (restoreFocus) requestAnimationFrame(() => focusRoleChoice(roleId));
}

function selectRoleChoice(roleId, openDetail = false) {
  state.selectedRoleId = roleId;
  if (openDetail && isMobileRoleDetail()) {
    state.roleDetailOpen = true;
    state.roleDetailTriggerId = roleId;
  }
  renderRoleLibrary(roleId);
  if (state.roleDetailOpen) requestAnimationFrame(() => $("[data-role-detail-back]")?.focus({ preventScroll: true }));
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
    ? "Loading roles"
    : state.roleManifestStatus === "stale"
      ? "Showing the last received role manifests · refresh failed"
      : state.roleManifestStatus === "current" && projection
        ? (filtered.length === roles.length ? roles.length : filtered.length + " of " + roles.length) + " role" + (roles.length === 1 ? "" : "s")
        : state.roleManifestStatus === "current"
          ? "Role manifest response was invalid"
          : (state.roleManifestError || "Role manifests unavailable");
  if (state.roleManifestMessage) status += " · " + state.roleManifestMessage;
  $("#role-library-status").textContent = status;
  $("#role-filter-chips").innerHTML = roleFilterChipsMarkup(state.roleTypes);
  const loading = ["loading", "refreshing"].includes(state.roleManifestStatus) && !roles.length;
  grid.setAttribute("aria-busy", String(loading));
  if (loading) {
    grid.innerHTML = loadingSkeletonMarkup();
    $("#role-library-detail").innerHTML = loadingSkeletonMarkup(4);
    $("#role-library-pager").innerHTML = "";
    return;
  }
  if (!filtered.some(({ role }) => role.id === state.selectedRoleId)) state.selectedRoleId = filtered[0]?.role.id || "";
  const selected = filtered.find((role) => role.role.id === state.selectedRoleId) || null;
  const unavailable = !roles.length && state.roleManifestStatus === "unavailable";
  grid.innerHTML = filtered.length ? filtered.map(({ role, match }) => roleChooserMarkup(role, match, role.id === state.selectedRoleId)).join("") : '<p class="empty-state" role="status">' + escapeHTML(unavailable ? state.roleManifestError || "Role manifests unavailable." : "No roles match these filters. Clear the search or filters to see the roster.") + '</p>';
  $("#role-library-detail").innerHTML = unavailable ? '<p class="empty-state" role="status">Role details are unavailable until the manifest roster loads.</p>' : roleDetailMarkup(selected?.role, selected?.match);
  $("#role-library-detail").setAttribute("aria-labelledby", "role-detail-title");
  $("#role-library-detail").tabIndex = -1;
  syncRoleDetailPresentation();
  $("#role-library-pager").innerHTML = "";
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
  $("#role-editor-status").textContent = message || (allowed ? "Saving creates a new server-owned version." : "Role changes are unavailable until current server authority is available.");
}

function openRoleEditor(roleId = "", trigger = null) {
  const role = roleId ? roleRecord(roleId) : { id: "", name: "", purpose: "", owns: [], instructions: [], boundaries: [], default_skills: [], specializations: [], avatar_asset_digest: "", accent: "#4da8ff", active_version: null, source: "custom" };
  if (!role) return;
  const editing = Boolean(roleId);
  state.roleEditorMode = editing ? "edit" : "create";
  state.roleManifestRetry = null;
  state.roleEditorTrigger = ["edit", "avatar"].includes(trigger?.dataset.roleAction)
    ? { action: trigger.dataset.roleAction, roleId: trigger.dataset.roleId || roleId }
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
  updateDocumentTitle();
  requestAnimationFrame(() => (editing ? $("#role-field-name") : $("#role-field-id")).focus());
}

function closeRoleEditor() {
  if ($("#role-editor").open) $("#role-editor").close();
  updateDocumentTitle();
}

function roleEditorReturnTarget(origin) {
  const trigger = ["edit", "avatar"].includes(origin?.action) && origin.roleId
    ? $('[data-role-action="' + origin.action + '"][data-role-id="' + CSS.escape(origin.roleId) + '"]')
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
  const binding = options.binding?.attribute || "data-settings-draft-key";
  const control = options.binding?.control ? ' data-onboarding-control="setting-' + escapeHTML(key) + '"' : '';
  return '<section class="settings-essential-control"><div><span class="settings-control-title"><strong>' + escapeHTML(label) + '</strong>' + badge + '</span><small>' + escapeHTML(help) + '</small></div><label class="settings-switch"><input type="checkbox" ' + binding + '="' + escapeHTML(key) + '"' + control + (options.trueValue !== undefined ? ' data-true-value="' + escapeHTML(options.trueValue) + '" data-false-value="' + escapeHTML(options.falseValue) + '"' : '') + (checked ? ' checked' : '') + (editable ? '' : ' disabled') + ' aria-label="' + escapeHTML(label) + '"><span aria-hidden="true"></span></label>' + (editable ? '' : '<em>' + escapeHTML(options.unavailable || 'Managed by the current configuration.') + '</em>') + '</section>';
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

function settingsSpeedMarkup(options = {}) {
  const key = "execution.fast_mode";
  const fast = (options.value ?? settingsDraftValue(key, false)) === true;
  const editable = options.editable ?? settingsConfigEditable(key);
  const binding = options.binding?.attribute || "data-settings-draft-key";
  const choice = (label, selected, value, disabled = false) => '<label><input type="radio" name="' + escapeHTML(options.name || "settings-speed") + '" ' + binding + '="' + key + '" data-config-value="' + String(value) + '"' + (options.binding?.control ? ' data-onboarding-control="speed-' + label.toLowerCase() + '"' : '') + (selected ? ' checked' : '') + ((!editable || disabled) ? ' disabled' : '') + ' aria-label="' + escapeHTML(label) + '"><span>' + escapeHTML(label) + '</span></label>';
  return '<fieldset class="settings-segmented"><legend>Speed</legend><div>' + choice("Default", !fast, false) + choice("Fast", fast, true) + '</div>' + (editable ? '' : '<small>Speed is read-only in this scope.</small>') + '</fieldset>';
}

function settingsTaskLifeMarkup(options = {}) {
  if (!options.binding && options.editable !== true) return "";
  const labels = ["Short", "Medium", "Balanced", "Long", "Unlimited"];
  const tooltip = "Short clears context sooner to keep work efficient, with more handovers. Balanced hands over when task efficiency begins to drop. Long reduces handovers, while a larger context can become less efficient over time.";
  const value = Number(options.value);
  const exactIndex = ONBOARDING_TASK_LIFE_DETENTS.findIndex((item) => item.hours === value);
  const index = exactIndex >= 0 ? exactIndex : 2;
  const editable = options.editable === true;
  const binding = options.binding?.attribute || "";
  const bindingMarkup = binding ? ' ' + binding + '="lifecycle.task_lifetime_hours" data-config-values="' + ONBOARDING_TASK_LIFE_DETENTS.map((item) => item.hours).join(",") + '"' : '';
  const valueText = editable ? ONBOARDING_TASK_LIFE_DETENTS[index].valueText : "Balanced — unavailable";
  return '<section class="settings-task-life"><div class="settings-task-life-head"><strong>Task life</strong><details' + (options.binding?.control ? ' data-onboarding-control="task-life-info"' : '') + '><summary class="icon-button" aria-label="About task life"><span aria-hidden="true">i</span></summary><div role="tooltip">' + escapeHTML(tooltip) + '</div></details></div><input id="' + escapeHTML(options.id || "settings-task-life") + '" type="range" min="0" max="4" step="1" value="' + index + '"' + bindingMarkup + (editable ? '' : ' disabled') + ' aria-label="Task life" aria-valuetext="' + escapeHTML(valueText) + '"><div aria-hidden="true">' + labels.map((label) => '<span>' + label + '</span>').join('') + '</div><small>' + escapeHTML(editable ? 'Balanced hands over when efficiency begins to drop.' : 'Task life is unavailable until SWARM exposes the accepted five-step setting.') + '</small></section>';
}

function settingsContextPresentation(scope, selectedCtrl, setting) {
  if (selectedCtrl) return { title: publicLabel(selectedCtrl.project, "Project") + " / " + ctrlLabel(selectedCtrl), note: setting?.customized ? "Custom CTRL values override global defaults." : "Inherits global defaults." };
  if (scope.type === "project") return { title: scopeLabel(), note: "Project values inherit global defaults until an accepted override is supplied." };
  return { title: "Global defaults", note: "Changes apply wherever a project has not overridden them." };
}

function configEditorWritable(draft = state.configEditorDraft) {
  const scope = currentSettingsScope();
  const binding = configWriteScope();
  const config = state.config;
  return Boolean(draft && draft === state.configEditorDraft && state.configStatus === "current" && config?.state === "KNOWN" && config.available === true && config.read_only === false && config.write_contract?.available === true && config.revision && typeof config.editable_text === "string" && binding?.type === scope.type && (scope.type === "global" || binding.project_id === scope.id) && JSON.stringify(scope) === draft.scope && JSON.stringify(binding) === draft.binding && config.revision === draft.revision);
}

function renderConfigEditor() {
  const dialog = $("#config-editor-dialog");
  if (!dialog) return;
  if (dialog.open && state.configEditorDraft) {
    const writable = configEditorWritable() && !state.configEditorDraft.pending;
    $("#config-editor-text").readOnly = !writable;
    $("#config-editor-save").disabled = !writable || $("#config-editor-text").value === state.configEditorDraft.text;
    $("#config-editor-reset").disabled = !writable || currentSettingsScope().type !== "project" || !configResetRequest("project");
    return;
  }
  const scope = currentSettingsScope();
  const context = settingsContextPresentation(scope, selectedSettingsCtrl(), state.ctrlSettings);
  const config = state.config;
  const binding = configWriteScope(config);
  const current = state.configStatus === "current" && config?.state === "KNOWN" && config.available === true &&
    binding?.type === scope.type && (scope.type === "global" || binding.project_id === scope.id) && Boolean(config.revision);
  const textAvailable = current && typeof config.editable_text === "string";
  $("#config-editor-context").textContent = context.title;
  $("#config-editor-source").textContent = current ? context.title : "Unavailable";
  $("#config-editor-revision").textContent = current ? String(config.revision).slice(0, 12) : "Unavailable";
  $("#config-editor-validation").textContent = current && config.validation?.state === "KNOWN" ? config.validation.status : "Validation unavailable";
  $("#config-editor-warning").hidden = scope.type === "global";
  $("#config-editor-text").value = textAvailable ? config.editable_text : "";
  $("#config-editor-text").placeholder = "Exact config text is unavailable from this server.";
  $("#config-editor-text").readOnly = true;
  $("#config-editor-status").textContent = textAvailable ? "Current configuration · Read-only preview" : "Current configuration is unavailable for this scope.";
  $("#config-editor-save").disabled = true;
  $("#config-editor-reset").disabled = true;
  $("#config-editor-reset").hidden = scope.type !== "project";
  $("#config-editor-reset").title = "Remove this project's overrides; inherited global settings remain unchanged.";
}

function openConfigEditor(trigger) {
  if ($("#config-editor-dialog").open) return;
  state.configEditorTrigger = trigger || document.activeElement;
  renderConfigEditor();
  state.configEditorDraft = { scope: JSON.stringify(currentSettingsScope()), binding: JSON.stringify(configWriteScope()), revision: state.config?.revision, text: $("#config-editor-text").value, pending: false };
  const writable = configEditorWritable();
  $("#config-editor-text").readOnly = !writable;
  $("#config-editor-reset").disabled = !writable || currentSettingsScope().type !== "project" || !configResetRequest("project");
  $("#config-editor-status").textContent = writable ? "No changes" : $("#config-editor-status").textContent;
  const dialog = $("#config-editor-dialog");
  if (!dialog.open) dialog.showModal();
  updateDocumentTitle();
  requestAnimationFrame(() => $("#config-editor-close").focus({ preventScroll: true }));
}

function closeConfigEditor() {
  const draft = state.configEditorDraft;
  if (draft?.pending) return;
  if (draft && $("#config-editor-text").value !== draft.text && !confirm("Discard unsaved configuration changes?")) return;
  const dialog = $("#config-editor-dialog");
  if (dialog.open) dialog.close();
  updateDocumentTitle();
}

async function saveConfigEditor() {
  const draft = state.configEditorDraft;
  const input = $("#config-editor-text");
  if (!configEditorWritable(draft) || draft.pending || input.readOnly || input.value === draft.text) return;
  const text = input.value;
  draft.pending = true;
  input.readOnly = true;
  $("#config-editor-save").disabled = true;
  $("#config-editor-status").textContent = "Saving…";
  $("#config-editor-reset").disabled = true;
  try {
    const result = await saveConfigText(() => {
      if (!configEditorWritable(draft)) throw new Error("Configuration changed. Your text is preserved; reopen the current scope before saving.");
      return text;
    });
    if (!result.applied || JSON.stringify(currentSettingsScope()) !== draft.scope) throw new Error("Scope changed. Your text is preserved; this view has not been saved.");
    draft.text = text;
    draft.revision = state.config.revision;
    $("#config-editor-revision").textContent = String(state.config.revision).slice(0, 12);
    $("#config-editor-validation").textContent = state.config.validation?.state === "KNOWN" ? state.config.validation.status : "Validation unavailable";
    $("#config-editor-status").textContent = "Saved";
  } catch (error) {
    $("#config-editor-status").textContent = error.message || "Could not save. Your text is preserved.";
  } finally {
    draft.pending = false;
    input.readOnly = !configEditorWritable(draft);
    $("#config-editor-save").disabled = input.value === draft.text || input.readOnly;
    $("#config-editor-reset").disabled = input.readOnly || currentSettingsScope().type !== "project" || !configResetRequest("project");
    input.focus({ preventScroll: true });
  }
}

async function resetConfigEditor() {
  const draft = state.configEditorDraft;
  if (!configEditorWritable(draft) || draft.pending || currentSettingsScope().type !== "project") return;
  if (!confirm("Remove this project's overrides and discard this editor's unsaved text? These values will follow global settings again.")) return;
  draft.pending = true;
  renderConfigEditor();
  $("#config-editor-status").textContent = "Resetting…";
  try {
    const outcome = await resetSettingsScope("project");
    if (!outcome.applied || JSON.stringify(currentSettingsScope()) !== draft.scope) throw new Error("Scope changed. Your editor text is preserved.");
    draft.revision = state.config.revision;
    draft.text = state.config.editable_text;
    $("#config-editor-text").value = draft.text;
    $("#config-editor-revision").textContent = String(draft.revision).slice(0, 12);
    $("#config-editor-validation").textContent = state.config.validation?.state === "KNOWN" ? state.config.validation.status : "Validation unavailable";
    $("#config-editor-status").textContent = "Project overrides removed";
  } catch (error) {
    $("#config-editor-status").textContent = error.message || "Could not reset. Your text is preserved.";
  } finally {
    draft.pending = false;
    renderConfigEditor();
    $("#config-editor-text").focus({ preventScroll: true });
  }
}

async function saveSettingsDraft() {
  const changes = settingsDraftChanges();
  if (!Object.keys(changes).length || state.settingsSaving) return false;
  state.settingsSaving = true;
  state.settingsSaveError = "";
  state.settingsSaveMessage = "Saving…";
  renderSettings();
  try {
    await saveCurrentConfigMutation(changes);
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

function settingsThemeMarkup() {
  const selected = currentTheme();
  const options = Object.entries(THEME_OPTIONS).map(([value, label]) => '<label><input type="radio" name="appearance-theme" data-theme-option="' + value + '" value="' + value + '"' + (value === selected ? ' checked' : '') + '><span class="theme-choice-label"><i class="theme-swatch theme-swatch-' + value + '" aria-hidden="true"></i><b>' + label + '</b></span></label>').join('');
  return '<fieldset class="panel settings-theme settings-wide"><legend>Appearance</legend><p>Choose how SWARM HQ looks on this device.</p><div>' + options + '</div></fieldset>';
}

function settingsConfigSummary() {
  const scope = currentSettingsScope();
  const config = state.config;
  const binding = configWriteScope(config);
  const label = scope.type === "global" ? "Global" : scope.type === "project" ? "Project" : "CTRL";
  const matches = binding?.type === scope.type && (scope.type === "global" || binding.project_id === scope.id);
  if (!matches || state.configStatus !== "current" || config?.state !== "KNOWN" || config.available !== true || !String(config.revision ?? "")) {
    return label + " configuration unavailable for this scope" + (state.configStatus === "stale" ? " · Last read is stale" : "");
  }
  return label + " configuration · revision " + String(config.revision).slice(0, 12) + " · Config text " +
    (typeof config.editable_text === "string" ? "available" : "unavailable") +
    (config.read_only !== false || config.write_contract?.available !== true ? " · Read-only" : "");
}

function renderSettings() {
  const scope = currentSettingsScope();
  const selectedCtrl = selectedSettingsCtrl();
  const setting = state.ctrlSettings;
  const advancedOpen = $("#settings-advanced")?.open === true;
  const automation = state.config?.settings?.automation || {};
  const context = settingsContextPresentation(scope, selectedCtrl, setting);
  const autoMode = settingsDraftValue("automation.mode", automation.mode || "manual");
  const pending = state.settingsDraft.size;
  const saveStatus = state.settingsSaveError || state.settingsSaveMessage || (pending ? pending + " unsaved change" + (pending === 1 ? "" : "s") : "All changes saved");
  $("#settings-grid").innerHTML =
    '<header class="settings-page-head"><div><p class="eyebrow">Preferences</p><p>Three defaults keep SWARM predictable. Everything else stays behind Advanced.</p></div><label class="settings-scope-control">Applies to<select id="settings-scope">' + settingsScopeOptions() + '</select></label></header>' +
    '<div class="settings-card-grid">' +
      '<section class="panel settings-card settings-card-workflow" id="settings-essentials" tabindex="-1"><div class="settings-card-icon" aria-hidden="true"><svg class="lucide"><use href="#lucide-activity"></use></svg></div><h3>Workflow</h3><p>Keep eligible work moving with automatic next steps.</p>' + settingsSwitch("automation.mode", autoMode, "Auto-advance", "Continue to the next admitted item after one completes.", { trueValue: "standard", falseValue: "manual", unavailable: scope.type === "global" ? "Managed by the current configuration." : "Edit global defaults or use an accepted override." }) + '</section>' +
      '<section class="panel settings-card settings-card-usage"><div class="settings-card-icon" aria-hidden="true"><svg class="lucide"><use href="#lucide-sparkles"></use></svg></div><h3>Usage saver</h3><p>Save resources without slowing down eligible work.</p>' + descriptorBooleanSwitch("execution.usage_saver", "Enable usage saver", "Uses lighter models and reduces background activity when possible.", { unsupported: "Unavailable until the canonical setting is exposed." }) + '</section>' +
      '<fieldset class="panel settings-card settings-card-appearance"><legend>Appearance</legend><div class="settings-card-icon" aria-hidden="true"><svg class="lucide"><use href="#lucide-settings"></use></svg></div><h3>Appearance</h3><p>Choose the look that feels right for you.</p><div class="settings-theme-choice">' + Object.entries(THEME_OPTIONS).map(([value, label]) => '<label><input type="radio" name="appearance-theme" data-theme-option="' + value + '" value="' + value + '"' + (value === currentTheme() ? ' checked' : '') + '><span class="theme-choice-label"><i class="theme-swatch theme-swatch-' + value + '" aria-hidden="true"></i><b>' + label + '</b></span></label>').join('') + '</div></fieldset>' +
    '</div>' +
    '<details class="panel settings-advanced-drawer" id="settings-advanced"' + (advancedOpen ? ' open' : '') + '><summary>Advanced settings</summary><div class="settings-advanced-grid"><section><p class="eyebrow">Scope</p><strong>' + escapeHTML(context.title) + '</strong><small>' + escapeHTML(context.note) + '</small></section><section>' + settingsSpeedMarkup() + settingsTaskLifeMarkup() + '</section><section>' + chatRelaySettingsMarkup() + autoSettingsMarkup() + '</section><section>' + skillsSummary(scope) + skillsAdvanced(scope) + '</section><section class="settings-config-entry"><p class="eyebrow">Configuration</p><h3>Edit config</h3><small>' + escapeHTML(settingsConfigSummary()) + '</small><button class="quiet-button" id="settings-edit-config" data-setting-action="edit-config" type="button">Edit config</button></section><div class="guided-tour-setting"><span><strong>Guided tour</strong><small>Replay the current SWARM introduction.</small></span><button class="quiet-button" data-setting-action="replay-tour" type="button">Replay tour</button></div></div></details>' +
    '<footer class="settings-save-bar settings-wide' + (state.settingsSaveError ? ' is-error' : '') + '" aria-live="polite"' + (!pending && !state.settingsSaving && !state.settingsSaveError ? ' hidden' : '') + '><p><strong>' + escapeHTML(saveStatus) + '</strong><span>' + escapeHTML(pending ? "Review and save these server-backed changes." : "Essentials reflect the latest acknowledged configuration.") + '</span></p><div><button class="quiet-button" data-setting-action="discard-settings" type="button"' + (!pending || state.settingsSaving ? ' disabled' : '') + '>Discard</button><button class="primary-action" id="settings-save" data-setting-action="save-settings" type="button"' + (!pending || state.settingsSaving ? ' disabled' : '') + (state.settingsSaving ? ' aria-busy="true"' : '') + '>Save changes</button></div></footer>';
}

function labCatalog() {
  return state.labs?.ok === true && Array.isArray(state.labs.labs) ? state.labs.labs : [];
}

function labRoleStack(roleIds) {
  return '<span class="lab-role-stack" aria-label="' + escapeHTML(roleIds.join(", ")) + '">' + roleIds.slice(0, 3).map((roleId) => '<img src="/assets/role-avatars/' + encodeURIComponent(roleId) + '.png" alt="" title="' + escapeHTML(roleId) + '">').join("") + (roleIds.length > 3 ? '<i aria-hidden="true">+' + (roleIds.length - 3) + '</i>' : '') + '</span>';
}

function selectedLab() {
  const labs = labCatalog();
  const id = $("#view-labs")?.dataset.selectedLabId || labs[0]?.id;
  return labs.find((lab) => lab.id === id) || labs[0] || null;
}

function renderLabs() {
  const catalog = $("#lab-catalog"), status = $("#lab-status");
  if (!catalog || !status) return;
  const labs = labCatalog();
  if (!labs.length) {
    status.textContent = state.labsStatus === "loading" ? "Loading labs" : (state.labsError || "Labs unavailable");
    catalog.innerHTML = state.labsStatus === "loading" ? '<div class="loading-skeleton lab-loading" aria-hidden="true"><i></i><i></i><i></i><i></i></div>' : '<div class="empty-inline"><strong>Labs unavailable</strong><button class="quiet-button" type="button" data-lab-retry>Retry</button></div>';
    return;
  }
  status.textContent = labs.length + " labs ready";
  const active = selectedLab();
  catalog.innerHTML = labs.map((lab) => {
    const selected = lab.id === active?.id;
    return '<article class="lab-card' + (selected ? ' is-selected' : '') + '" role="listitem">' +
      '<button class="lab-card-select" type="button" data-lab-id="' + lab.id + '" aria-expanded="' + String(selected) + '"><span class="lab-mark" aria-hidden="true"><svg class="lucide"><use href="#lucide-flask-conical"></use></svg></span><span class="lab-card-copy"><strong>' + escapeHTML(lab.name) + '</strong><small>' + escapeHTML(lab.summary) + '</small></span><span class="lab-ready"><i></i>Ready</span>' + labRoleStack(lab.role_ids) + '<svg class="lucide lab-chevron" aria-hidden="true"><use href="#lucide-chevron-down"></use></svg></button>' +
      (selected ? '<form class="lab-launch" data-lab-form="' + lab.id + '"><label for="lab-question-' + lab.id + '"><span>' + escapeHTML(lab.prompt) + '</span><textarea id="lab-question-' + lab.id + '" rows="2" maxlength="1200" placeholder="Describe the outcome…"></textarea></label><button class="primary-action" type="submit">Start</button></form>' : '') +
      '</article>';
  }).join("");
}

function startLab(lab, question = "") {
  state.messageDraft = 'Start the ' + lab.name + ' for the current project scope: ' + (question.trim() || lab.prompt) + ' Use only the roles needed. Return the selected outcome with proof.';
  renderMessageComposer();
  openMessageComposer($("[data-lab-form='" + lab.id + "'] button"));
}

async function refreshLabs() {
  const hasLastGood = labCatalog().length > 0;
  state.labsStatus = hasLastGood ? "refreshing" : "loading";
  renderLabs();
  try {
    const result = await api('/api/labs');
    if (result?.ok !== true || !Array.isArray(result.labs)) throw new Error("Lab catalog response was invalid.");
    state.labs = result;
    state.labsStatus = "current";
    state.labsError = "";
  } catch (error) {
    state.labsStatus = hasLastGood ? "stale" : "unavailable";
    state.labsError = error.message || "Labs unavailable";
  }
  renderLabs();
}

function renderAllViews() { renderOverview(); renderAgents(); renderLabs(); renderRoles(); renderReview(); renderAssets(); renderDiagnostics(); renderSettings(); renderRunLogSurfaces(); renderMessageComposer(); if ($("#onboarding-dialog")?.open) renderOnboarding(); updateDocumentTitle(); }

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
  const generation = ++state.usageRequestGeneration;
  const request = { projectId: state.projectId, ctrlId: state.ctrlId, hours: state.usageWindowHours };
  const range = state.usageDateRange ? {...state.usageDateRange} : null;
  const requestKey = usageRequestKey(request.projectId, request.ctrlId, request.hours, range);
  const params = new URLSearchParams({ project_id: request.projectId, ctrl_id: request.ctrlId, hours: String(request.hours) });
  if (range) { params.set('after_ms', String(range.after_ms)); params.set('before_ms', String(range.before_ms)); }
  const hasLastGood = state.usageScopeKey === requestKey && state.usageHistory?.ok === true;
  state.usageStatus = hasLastGood ? "refreshing" : "loading";
  try {
    const result = await api('/api/usage-history?' + params.toString());
    if (generation !== state.usageRequestGeneration || request.projectId !== state.projectId || request.ctrlId !== state.ctrlId || request.hours !== state.usageWindowHours || requestKey !== usageRequestKey()) return;
    if (result.window && (result.hours !== request.hours || (request.ctrlId
      ? result.scope?.type !== 'ctrl' || result.scope.ctrl_id !== request.ctrlId || (request.projectId !== 'all' && result.scope.project_id !== request.projectId)
      : request.projectId !== 'all' ? result.scope?.type !== 'project' || result.scope.project_id !== request.projectId : result.scope?.type !== 'all-projects'))) throw new Error('Usage response does not match the selected scope.');
    if (range && (result.window?.explicit !== true || result.window.after_ms !== range.after_ms || result.window.before_ms !== range.before_ms)) throw new Error('Usage response does not match the selected dates.');
    if (!range && result.window?.explicit === true) throw new Error('Usage response does not match the selected range.');
    state.usageHistory = result;
    state.usageScopeKey = requestKey;
    state.usageStatus = "current";
    state.usageError = "";
  } catch (error) {
    if (generation !== state.usageRequestGeneration || request.projectId !== state.projectId || request.ctrlId !== state.ctrlId || request.hours !== state.usageWindowHours || requestKey !== usageRequestKey()) return;
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
    if (state.view === "overview") renderProjectDetail();
  } catch (error) {
    if (projectId !== selectedProgressProjectId()) return;
    if (!hasLastGood) state.projectProgress = null;
    state.projectProgressStatus = hasLastGood ? "stale" : "unavailable";
    state.projectProgressError = error.message || "Project ledger unavailable";
    if (state.view === "overview") renderProjectDetail();
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
    await Promise.all([refreshUsageHistory(), refreshNotifications(), refreshRunLogs(), refreshAssets(), refreshDiagnostics(false), refreshCommandApprovals(), refreshMessageConversation()]);
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
  renderRoleLibrary();
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
    renderOverview();
    if (showLoading) setLoading(false);
    await Promise.all([refreshProof(), refreshUsageHistory(), refreshProjectProgress(), refreshProjectProgressFeed(), refreshRoleManifests(), refreshLabs(), refreshNotifications(), refreshRunLogs(), refreshAssets(), refreshProfileSummary(), refreshCommandApprovals(), refreshMessageConversation()]);
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
    state.messageConnector = messageConnectorCapability(bootstrap);
    state.taskMessageCapability = taskMessageCapability(bootstrap);
    state.messageStatus = state.messageConnector ? "idle" : "unavailable";
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
  const diagnosticInspect = event.target.closest("[data-diagnostic-inspect]");
  if (diagnosticInspect) {
    inspectDiagnosticCheck(diagnosticInspect.dataset.diagnosticInspect);
    return;
  }
  const diagnosticReview = event.target.closest("[data-diagnostic-review]");
  if (diagnosticReview) {
    reviewDiagnosticWithCtrl(diagnosticReview.dataset.diagnosticReview);
    return;
  }
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
  const metricCard = event.target.closest("[data-overview-metric]");
  if (metricCard) { openMetricDetail(metricCard); return; }
  const taskUsage = event.target.closest('[data-task-usage-id], [data-task-usage-view], [data-task-usage-back], [data-task-usage-legend], [data-task-usage-panel], [data-task-usage-visible]');
  if (taskUsage) {
    const dialog = $('#metric-detail-dialog');
    if (dialog.dataset.metric !== 'tbr') return;
    if (taskUsage.hasAttribute('data-task-usage-panel')) { dialog.dataset.tbrPanel = taskUsage.dataset.taskUsagePanel; delete dialog.dataset.taskId; }
    if (taskUsage.hasAttribute('data-task-usage-id')) dialog.dataset.taskId = taskUsage.dataset.taskUsageId;
    if (taskUsage.hasAttribute('data-task-usage-view')) { dialog.dataset.taskView = taskUsage.dataset.taskUsageView; delete dialog.dataset.taskId; }
    if (taskUsage.hasAttribute('data-task-usage-back')) delete dialog.dataset.taskId;
    if (taskUsage.hasAttribute('data-task-usage-legend')) dialog.dataset.hideLegend = String(dialog.dataset.hideLegend !== 'true');
    if (taskUsage.hasAttribute('data-task-usage-visible')) {
      const hidden = new Set(JSON.parse(dialog.dataset.hiddenTaskIds || '[]')), id = taskUsage.dataset.taskUsageVisible;
      if (hidden.has(id)) hidden.delete(id); else hidden.add(id);
      dialog.dataset.hiddenTaskIds = JSON.stringify([...hidden]);
    }
    renderMetricDetail(false);
    if (taskUsage.hasAttribute('data-task-usage-id') || taskUsage.hasAttribute('data-task-usage-back')) $('#highest-usage-tasks')?.querySelector('button:not(:disabled)')?.focus({preventScroll:true});
    return;
  }
  const usageRange = event.target.closest("[data-usage-range]");
  if (usageRange) {
    const hours = Number(usageRange.dataset.usageRange);
    if (usageRange.disabled || ![1, 24, 168, 720].includes(hours) || (hours === state.usageWindowHours && !state.usageDateRange)) return;
    state.usageDateRange = null;
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
  const collectionMore = event.target.closest("[data-collection-more]");
  if (collectionMore) {
    const kind = collectionMore.dataset.collectionMore;
    if (kind === "assets") {
      closeAssetDialog();
      state.assetPage += 1;
      renderAssets();
    } else if (kind === "artifacts") {
      state.projectArtifactPage += 1;
      renderProjectDetail();
    } else return;
    requestAnimationFrame(() => { const status = $('[data-collection-status="' + kind + '"]'); status?.scrollIntoView({ block: "nearest" }); status?.focus({ preventScroll: true }); });
    return;
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
      state.assetPage = 0;
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
    state.projectUiMode = projectUiMode.dataset.projectUiMode || "screens";
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
  const reviewTask = event.target.closest("[data-review-task]");
  if (reviewTask) {
    setView("agents");
    requestAnimationFrame(() => {
      const trigger = $('[data-agent-detail="' + CSS.escape(reviewTask.dataset.reviewTask) + '"]');
      if (trigger) openAgentDetail(trigger);
    });
    return;
  }
  const reviewCopy = event.target.closest("[data-review-copy]");
  if (reviewCopy) {
    try { await navigator.clipboard.writeText(reviewCopy.dataset.reviewCopy || ""); } catch { /* clipboard is optional */ }
    reviewCopy.setAttribute("aria-label", "Proof ID copied");
    reviewCopy.title = "Copied";
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
    selectRoleChoice(roleSelect.dataset.roleSelect, true);
    return;
  }
  if (event.target.closest("[data-role-detail-back]")) {
    closeMobileRoleDetail();
    return;
  }
  const roleAction = event.target.closest("[data-role-action]");
  if (roleAction) {
    if (roleAction.dataset.roleAction === "edit") openRoleEditor(roleAction.dataset.roleId, roleAction);
    if (roleAction.dataset.roleAction === "avatar") openRoleEditor(roleAction.dataset.roleId, roleAction);
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
  const tab = event.target.closest("[data-view]");
  if (tab) {
    setView(tab.dataset.view);
    if (mobileDrawerQuery.matches) setMobileDrawer(false, true);
  }
});

$("#message-launcher").addEventListener("click", (event) => { event.stopPropagation(); openMessageComposer(event.currentTarget); });
$("#mobile-message-action").addEventListener("click", (event) => { event.stopPropagation(); openMessageComposer(event.currentTarget); });
$("#message-composer").addEventListener("click", (event) => event.stopPropagation());
$("#message-close").addEventListener("click", (event) => { event.stopPropagation(); closeMessageComposer(); });
$("#message-draft").addEventListener("input", (event) => {
  messageInteractionGeneration += 1;
  state.messageDraft = event.target.value;
  if (state.messagePendingAction?.kind === "task" || (state.taskMessageCapability && state.messageStatus === "pending")) { renderMessageComposer(); return; }
  if (["failed", "conflict", "sent"].includes(state.messageStatus)) state.messagePendingAction = null;
  state.messageStatus = state.messageConnector ? "idle" : "unavailable";
  state.messageError = "";
  state.messageReceipt = null;
  renderMessageComposer();
});
$("#message-recipient").addEventListener("change", (event) => {
  messageInteractionGeneration += 1;
  state.messageRecipientId = event.target.value;
  if (state.messagePendingAction?.kind === "task" || (state.taskMessageCapability && state.messageStatus === "pending")) { renderMessageComposer(); refreshMessageHistory(); return; }
  state.messagePendingAction = null;
  state.messageStatus = state.messageConnector ? "idle" : "unavailable";
  state.messageError = "";
  state.messageReceipt = null;
  renderMessageComposer();
  refreshMessageHistory();
});
$("#message-send").addEventListener("click", () => sendMessageFromComposer(false));
$("#message-retry").addEventListener("click", () => sendMessageFromComposer(true));

$("#profile").addEventListener("click", (event) => openProfile(event.currentTarget));
$("#command-approvals").addEventListener("click", (event) => {
  const button = event.target.closest("[data-command-approval]");
  if (button) respondCommandApproval(Number(button.dataset.commandApproval), button.dataset.commandDecision);
});
$("#profile-close").addEventListener("click", () => closeProfile());
$("#profile-cancel").addEventListener("click", () => closeProfile());
$("#profile-form").addEventListener("submit", saveProfile);
$("#profile-avatar-input").addEventListener("change", (event) => selectProfileAvatar(event.target.files?.[0]));
$("#profile-dialog").addEventListener("toggle", (event) => {
  if (event.newState === "closed" && !event.currentTarget.matches(":popover-open")) closeProfile(false);
});
$("#profile-dialog").addEventListener("keydown", (event) => {
  if (event.key === "Escape") { event.preventDefault(); closeProfile(); }
});

$("#support-open").addEventListener("click", (event) => openSupport(event.currentTarget));
$("#support-close").addEventListener("click", () => closeSupport());
$("#support-dialog").addEventListener("click", (event) => { if (event.target === event.currentTarget) closeSupport(); });
$("#support-dialog").addEventListener("cancel", (event) => {
  event.preventDefault();
  closeSupport();
});

$("#project-create").addEventListener("click", openProjectCreate);
$("#project-create-close").addEventListener("click", () => closeProjectCreate());
$("#project-create-cancel").addEventListener("click", () => closeProjectCreate());
$("#project-create-form").addEventListener("submit", createProject);
$("#project-create-dialog").addEventListener("click", (event) => { if (event.target === event.currentTarget) closeProjectCreate(); });
$("#project-create-dialog").addEventListener("cancel", (event) => { event.preventDefault(); closeProjectCreate(); });

$("#ask-anything-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const value = $("#ask-anything").value.trim();
  if (value) state.messageDraft = value;
  $("#ask-anything").value = "";
  renderMessageComposer();
  openMessageComposer($("#ask-anything"));
});
$("#lab-catalog").addEventListener("click", (event) => {
  if (event.target.closest("[data-lab-retry]")) { refreshLabs(); return; }
  const trigger = event.target.closest("[data-lab-id]");
  if (!trigger) return;
  const panel = $("#view-labs");
  panel.dataset.selectedLabId = panel.dataset.selectedLabId === trigger.dataset.labId ? "" : trigger.dataset.labId;
  renderLabs();
  $("[data-lab-form] textarea")?.focus({ preventScroll: true });
});
$("#lab-catalog").addEventListener("submit", (event) => {
  const form = event.target.closest("[data-lab-form]");
  if (!form) return;
  event.preventDefault();
  const lab = labCatalog().find((item) => item.id === form.dataset.labForm);
  if (lab) startLab(lab, form.querySelector("textarea")?.value || "");
});
document.addEventListener("keydown", (event) => {
  if (event.ctrlKey && !event.altKey && !event.shiftKey && event.key.toLowerCase() === "k") {
    event.preventDefault();
    $("#ask-anything").focus({ preventScroll: true });
  }
});

$("#repair-close").addEventListener("click", () => closeRepairDialog());
$("#repair-cancel").addEventListener("click", () => closeRepairDialog());
$("#repair-confirm").addEventListener("click", confirmRepairPreparation);
$("#repair-acknowledge").addEventListener("change", renderRepairDialog);
$("#repair-dialog").addEventListener("cancel", (event) => {
  event.preventDefault();
  closeRepairDialog();
});

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
$("#agent-detail-dialog").addEventListener("click", (event) => { if (event.target === event.currentTarget) closeAgentDetail(); });
$("#agent-detail-dialog").addEventListener("cancel", (event) => {
  event.preventDefault();
  closeAgentDetail();
});
$("#agent-detail-dialog").addEventListener("close", () => {
  const trigger = state.agentDetailTrigger;
  agentDetailFocusTarget(trigger)?.focus?.({ preventScroll: true });
  state.agentDetailTrigger = null;
});
$("#config-editor-close").addEventListener("click", closeConfigEditor);
$("#config-editor-save").addEventListener("click", saveConfigEditor);
$("#config-editor-reset").addEventListener("click", resetConfigEditor);
$("#config-editor-text").addEventListener("input", () => {
  const draft = state.configEditorDraft;
  const dirty = draft && $("#config-editor-text").value !== draft.text;
  $("#config-editor-text").readOnly = !configEditorWritable(draft) || Boolean(draft?.pending);
  $("#config-editor-save").disabled = !dirty || $("#config-editor-text").readOnly;
  $("#config-editor-status").textContent = dirty ? "Unsaved changes" : "No changes";
  $("#config-editor-validation").textContent = dirty ? "Not yet validated" : state.config?.validation?.status || "Validation unavailable";
});
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
  if (state.roleDetailOpen && isMobileRoleDetail() && !document.querySelector("dialog[open]")) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeMobileRoleDetail();
      return;
    }
    if (event.key === "Tab") {
      const focusable = roleDetailFocusable();
      const first = focusable[0];
      const last = focusable.at(-1);
      if (!first) { event.preventDefault(); return; }
      if (event.shiftKey && (document.activeElement === first || !$("#role-library-detail").contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !$("#role-library-detail").contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
      return;
    }
  }
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
  if (event.target.closest(".overview-node-more summary")) requestAnimationFrame(scheduleOverviewHierarchyEdges);
  const zoom = event.target.closest("[data-overview-zoom]");
  if (zoom) {
    setOverviewHierarchyZoom(zoom.dataset.overviewZoom);
    zoom.focus({ preventScroll: true });
    return;
  }
  const agentInspect = event.target.closest("[data-agent-inspect]");
  if (agentInspect) {
    event.stopPropagation();
    openAgentDetail(agentInspect);
    return;
  }
  const edit = event.target.closest("[data-overview-project-edit]");
  if (edit) {
    await selectProjectScope(edit.dataset.overviewProjectEdit, edit);
    setView("settings", true);
    return;
  }
  const project = event.target.closest("[data-overview-project-id]");
  if (project) await selectProjectScope(project.dataset.overviewProjectId, project);
});
$("#overview-project-rows").addEventListener("click", async event => {
  const project = event.target.closest("[data-project-id]");
  if (project) await selectProjectScope(project.dataset.projectId, project);
});
$("#retry").addEventListener("click", refreshOverview);
$("#metric-date-form").addEventListener("submit", applyUsageDates);
$('.metric-date-picker').addEventListener('keydown', event => {
  if (event.key === 'Escape' && event.currentTarget.open) {
    event.preventDefault(); event.stopPropagation(); event.currentTarget.open = false;
    event.currentTarget.querySelector('summary').focus();
  }
});
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
$("#drawer-close").addEventListener("click", () => setMobileDrawer(false, true));
$("#drawer-backdrop").addEventListener("click", () => setMobileDrawer(false, true));
mobileDrawerQuery.addEventListener("change", syncMobileDrawer);
mobileDrawerQuery.addEventListener("change", syncMessageComposerMode);
document.addEventListener('change', async (event) => {
  if (event.target.matches('[data-theme-option]')) {
    setTheme(event.target.dataset.themeOption);
    renderSettings();
    return;
  }
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
      await saveCurrentConfigMutation(chatRelayMutation(requestedValue).changes);
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
      await saveCurrentConfigMutation({ [key]: value });
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
    await refreshOverview();
  } catch (error) { showError(error.message); }
});
$(".drawer-navigation").addEventListener("keydown", (event) => {
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
  const tabs = $$(".nav-item[data-view]").filter(tab => !tab.closest("details") || tab.closest("details").open);
  const index = tabs.indexOf(document.activeElement);
  if (index < 0) return;
  const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + tabs.length) % tabs.length;
  event.preventDefault();
  tabs[next].focus();
  setView(tabs[next].dataset.view, true);
});

$(".project-tabs")?.addEventListener("keydown", (event) => {
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
window.addEventListener("resize", () => {
  scheduleProjectViewConnectors();
  scheduleOverviewHierarchyEdges();
  syncRoleDetailPresentation();
});
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
window.addEventListener('popstate', () => { if (state.messageOpen) closeMessageComposer(true, true); });
window.addEventListener('hashchange', applyHistoryRoute);
initialize().then(startPresence);
