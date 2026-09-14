const $ = (selector) => document.querySelector(selector);
const escapeHTML = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
const attentionStates = new Set(["stalled", "blocked", "waiting", "needs_attention", "failed", "rejected"]);
const inactiveTaskStates = new Set(["quiet", "idle", "archived", "completed", "accepted", "verified"]);

function visibleProject(project) {
  return project && project.archived !== true && project.visibility !== "archived";
}

function reportableProject(project, skipInactive) {
  return visibleProject(project) && (!skipInactive || (project.activity_facts?.inactive !== true && project.activity_status !== "inactive"));
}

function nodeTitle(node) {
  return node?.artifact || node?.title || node?.presentation?.display_name || "Recorded work";
}

function nodeTime(node) {
  const timestamp = Date.parse(node?.updated_at || "");
  return Number.isFinite(timestamp) ? new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—";
}

function projectMarkup(project, nodes) {
  const work = nodes.filter((node) => node.project_id === project.id && String(node.role || "").toLowerCase() !== "ctrl" && !inactiveTaskStates.has(String(node.status || "").toLowerCase()));
  const shown = work.slice(0, 6);
  const remainder = work.length - shown.length;
  const activity = project.activity_status === "active" ? "active" : "inactive";
  return '<article class="project"><header class="project-head"><div class="project-meta"><span class="project-mark is-' + activity + '" aria-hidden="true"></span><div><h2>' + escapeHTML(project.name || project.display_name || "Project") + '</h2><p>' + work.length + ' current</p></div></div><span class="status">' + escapeHTML(project.activity_status || "observed") + '</span></header><div class="work-list">' + (shown.length ? shown.map((node) => '<div class="work-row"><div><strong>' + escapeHTML(nodeTitle(node)) + '</strong><small>' + escapeHTML(node.presentation?.display_name || node.role_label || node.role || "Agent") + ' · ' + escapeHTML(node.status || "observed") + '</small></div><time>' + escapeHTML(nodeTime(node)) + '</time></div>').join("") + (remainder ? '<p class="empty">+' + remainder + ' more</p>' : "") : '<p class="empty">No current updates.</p>') + '</div></article>';
}

function metric(label, value) {
  return '<article class="metric"><strong>' + escapeHTML(value) + '</strong><span>' + escapeHTML(label) + '</span></article>';
}

async function load() {
  const requested = new URLSearchParams(location.search).get("project_id") || "all";
  const response = await fetch("/api/daily-report");
  if (!response.ok) throw new Error("Report unavailable");
  const report = await response.json();
  if (!Array.isArray(report.projects) || !Array.isArray(report.nodes)) throw new Error("Report unavailable");
  const skipInactive = report.settings?.skip_inactive === true;

  const allProjects = report.projects.filter(visibleProject);
  $("#report-scope").innerHTML = '<option value="all">Portfolio</option>' + allProjects.map((project) => '<option value="' + escapeHTML(project.id) + '">' + escapeHTML(project.name || project.display_name) + '</option>').join("");
  $("#report-scope").value = allProjects.some((project) => project.id === requested) ? requested : "all";
  const selected = requested === "all" ? null : allProjects.find((project) => project.id === requested);
  const projects = selected ? (reportableProject(selected, skipInactive) ? [selected] : []) : allProjects.filter((project) => reportableProject(project, skipInactive));
  const projectIds = new Set(projects.map((project) => project.id));
  const nodes = report.nodes.filter((node) => projectIds.has(node.project_id));
  const tasks = nodes.filter((node) => String(node.role || "").toLowerCase() !== "ctrl" && !inactiveTaskStates.has(String(node.status || "").toLowerCase()));
  const attention = tasks.filter((node) => attentionStates.has(String(node.status || "").toLowerCase()));
  const tokens = nodes.reduce((total, node) => total + (Number.isFinite(Number(node.tokens)) ? Number(node.tokens) : 0), 0);

  $("#report-title").textContent = selected?.name || selected?.display_name || "Portfolio";
  $("#report-time").textContent = new Date().toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  $("#report-metrics").innerHTML = metric("Projects", projects.length) + metric("Current work", tasks.length) + metric("Needs attention", attention.length) + metric("Tokens", tokens ? new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(tokens) : "—");
  $("#report-projects").innerHTML = projects.length ? projects.map((project) => projectMarkup(project, nodes)).join("") : '<article class="project"><p class="empty">No current updates.</p></article>';
  $("#report-status").textContent = report.state === "KNOWN" ? "" : "Partial data";
}

$("#report-scope").addEventListener("change", (event) => {
  const projectId = event.target.value;
  location.href = "/report.html" + (projectId === "all" ? "" : "?project_id=" + encodeURIComponent(projectId));
});
$("#print-report").addEventListener("click", () => window.print());
load().catch(() => {
  $("#report-status").innerHTML = 'Couldn\'t load report.<button class="retry-report" type="button">Retry</button>';
  $("#report-status .retry-report").addEventListener("click", () => location.reload());
});
