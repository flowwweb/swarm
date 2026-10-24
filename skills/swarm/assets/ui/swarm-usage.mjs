// The existing API owns token deltas. Cached input/reasoning are subsets, not additions.
// A project request is explicit and exact; callers never narrow global data locally.
export function projectUsageRequest(projectId, hours) {
  if (typeof projectId !== 'string' || !projectId.trim() || ![24,168,720].includes(hours)) throw Error('Invalid project usage request');
  return {project_id:projectId,hours};
}

// Monotonic request identity: only the newest started read may present.
export function latestRequest() {
  let token = 0;
  return {next:()=>++token,isLatest:value=>value===token};
}

// One exact project read. Failures become unavailable; superseded reads become stale.
export async function readProjectUsage(call, projectId, hours, isCurrent) {
  let view = null;
  try { view = usageView(await call('swarm_usage', projectUsageRequest(projectId, hours)), hours, projectId); } catch { view = null; }
  if (!isCurrent()) return {state:'stale'};
  return view ? {state:'ready',view} : {state:'unavailable'};
}

// Without projectId this is the global reader; it still refuses project-scoped data.
export function usageView(value, hours, projectId) {
  if (projectId !== undefined && (typeof projectId !== 'string' || !projectId.trim())) throw Error('Invalid usage scope request');
  if (![24,168,720].includes(hours) || !value || value.ok !== true || value.hours !== hours ||
      !['ok','partial','no_data'].includes(value.status) || !Array.isArray(value.items) ||
      !Number.isSafeInteger(value.window?.after_ms) || !Number.isSafeInteger(value.window?.before_ms)) throw Error('Invalid usage projection');
  const scope = value.scope;
  if (projectId === undefined ? scope !== undefined && scope?.type !== 'all-projects' : scope?.type !== 'project' || scope.project_id !== projectId) throw Error('Usage scope mismatch');
  const points = value.items.map(row => {
    if (!Number.isSafeInteger(row.bucket_ms) || row.bucket_ms < value.window.after_ms || row.bucket_ms > value.window.before_ms ||
        !Number.isSafeInteger(row.delta_tokens) || row.delta_tokens < 0) throw Error('Invalid token observation');
    return {at:row.bucket_ms,tokens:row.delta_tokens};
  });
  if (points.some((p,i)=>i && p.at<=points[i-1].at)) throw Error('Conflicting token observations');
  const total=points.reduce((sum,p)=>sum+p.tokens,0);
  if (!Number.isSafeInteger(total) || points.length && total!==value.total_tokens || value.status==='no_data' && points.length) throw Error('Token total mismatch');
  return {total:points.length?total:null,points,status:points.length?value.status:'no_data',coverage:value.coverage||{},window:value.window};
}
