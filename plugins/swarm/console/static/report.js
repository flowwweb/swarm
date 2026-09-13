const $ = (selector) => document.querySelector(selector);
const escapeHTML = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
const attentionStates = new Set(["stalled", "blocked", "waiting", "needs_attention", "failed", "rejected"]);
const inactiveTaskStates = new Set(["quiet", "idle", "archived", "completed", "accepted", "verified"]);

function visibleProject(project) {
  return project && project.archived !== true && project.visibility !== "archived";
}

function reportableProject(project) {
  return visibleProject(project) && project.activity_facts?.inactive !== true && project.activity_status !== "inactive";
}

function projectLogo(project) {
  const artifact = project?.logo?.artifact;
  return project?.logo?.status === "ADMITTED" && typeof artifact?.url === "string" ? artifact.url : "/assets/swarm-wordmark.png";
}

function nodeTitle(node) {
  return node?.artifact || node?.title || node?.presentation?.display_name || "Recorded work";
}

function nodeTime(node) {
  const timestamp = Date.parse(node?.updated_at || "");
  return Number.isFinite(timestamp) ? new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "Time unavailable";
}

function projectMarkup(project, nodes) {
  const work = nodes.filter((node) => node.project_id === project.id && String(node.role || "").toLowerCase() !== "ctrl" && !inactiveTaskStates.has(String(node.status || "").toLowerCase()));
  const shown = work.slice(0, 6);
  const remainder = work.length - shown.length;
  return '<article class="project"><header class="project-head"><div class="project-meta"><img class="project-logo" src="' + escapeHTML(projectLogo(project)) + '" alt="" /><div><h2>' + escapeHTML(project.name || project.display_name || "Project") + '</h2><p>' + work.length + ' current work item' + (work.length === 1 ? "" : "s") + '</p></div></div><span class="status">' + escapeHTML(project.activity_status || "observed") + '</span></header><div class="work-list">' + (shown.length ? shown.map((node) => '<div class="work-row"><div><strong>' + escapeHTML(nodeTitle(node)) + '</strong><small>' + escapeHTML(node.presentation?.display_name || node.role_label || node.role || "Agent") + ' · ' + escapeHTML(node.status || "observed") + '</small></div><time>' + escapeHTML(nodeTime(node)) + '</time></div>').join("") + (remainder ? '<p class="empty">+' + remainder + ' more current item' + (remainder === 1 ? "" : "s") + '</p>' : "") : '<p class="empty">No current task updates were observed for this project.</p>') + '</div></article>';
}

function metric(label, value) {
  return '<article class="metric"><strong>' + escapeHTML(value) + '</strong><span>' + escapeHTML(label) + '</span></article>';
}

async function load() {
  const requested = new URLSearchParams(location.search).get("project_id") || "all";
  const [rosterResponse, overviewResponse] = await Promise.all([
    fetch("/api/projects"),
    fetch("/api/overview" + (requested === "all" ? "" : "?project_id=" + encodeURIComponent(requested))),
  ]);
  if (!rosterResponse.ok || !overviewResponse.ok) throw new Error("Current SWARM data could not be loaded.");
  const roster = await rosterResponse.json();
  const overview = await overviewResponse.json();
  if (!Array.isArray(roster.projects) || !Array.isArray(overview.nodes)) throw new Error("Current SWARM data is incomplete.");

  const allProjects = roster.projects.filter(visibleProject);
  $("#report-scope").innerHTML = '<option value="all">Portfolio</option>' + allProjects.map((project) => '<option value="' + escapeHTML(project.id) + '">' + escapeHTML(project.name || project.display_name) + '</option>').join("");
  $("#report-scope").value = allProjects.some((project) => project.id === requested) ? requested : "all";
  const selected = requested === "all" ? null : allProjects.find((project) => project.id === requested);
  const projects = selected ? (reportableProject(selected) ? [selected] : []) : allProjects.filter(reportableProject);
  const projectIds = new Set(projects.map((project) => project.id));
  const nodes = overview.nodes.filter((node) => projectIds.has(node.project_id));
  const tasks = nodes.filter((node) => String(node.role || "").toLowerCase() !== "ctrl" && !inactiveTaskStates.has(String(node.status || "").toLowerCase()));
  const attention = tasks.filter((node) => attentionStates.has(String(node.status || "").toLowerCase()));
  const tokens = nodes.reduce((total, node) => total + (Number.isFinite(Number(node.tokens)) ? Number(node.tokens) : 0), 0);

  $("#report-title").textContent = selected?.name || selected?.display_name || "Portfolio";
  $("#report-subtitle").textContent = selected ? "Current work and attention items for this project." : "Current work across active and recently active projects.";
  $("#report-time").textContent = new Date().toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  $("#report-metrics").innerHTML = metric("Projects included", projects.length) + metric("Current work", tasks.length) + metric("Needs attention", attention.length) + metric("Observed tokens", tokens ? new Intl.NumberFormat().format(tokens) : "—");
  $("#report-projects").innerHTML = projects.length ? projects.map((project) => projectMarkup(project, nodes)).join("") : '<article class="project"><p class="empty">No active project updates to include today.</p></article>';
  $("#report-status").textContent = roster.state === "KNOWN" ? "" : "Project inventory is partial. This report includes only observed records.";
}

$("#report-scope").addEventListener("change", (event) => {
  const projectId = event.target.value;
  location.href = "/report.html" + (projectId === "all" ? "" : "?project_id=" + encodeURIComponent(projectId));
});
$("#print-report").addEventListener("click", () => window.print());
load().catch((error) => { $("#report-status").textContent = error.message; $("#report-projects").innerHTML = '<article class="project"><p class="empty">Open SWARM HQ and refresh this report.</p></article>'; });
