// Read projections only. Host activity is never promoted to role or progress authority.
export function rosterView(raw) {
  if (raw?.ok !== true || raw.available !== true || raw.state !== 'KNOWN' || !raw.cursor?.digest || !Array.isArray(raw.projects)) throw Error('Project inventory unavailable');
  const seen = new Set();
  const observationCursor=raw.observation_cursor?.type==='project_roster_observation_v1'&&typeof raw.observation_cursor.digest==='string'&&/^[a-f0-9]{64}$/.test(raw.observation_cursor.digest)?raw.observation_cursor:null;
  const projects = raw.projects.map(p => {
    if (typeof p.id !== 'string' || !p.id || seen.has(p.id) || typeof p.name !== 'string' || !p.name) throw Error('Invalid project identity');
    seen.add(p.id);
    const binding=observationCursor&&p.root_binding?.source==='codex.project_roots'?p.root_binding:{};
    return {id:p.id,name:p.name,status:['active','inactive','recently_active'].includes(p.activity_status)?p.activity_status:'unknown',tasks:Number.isSafeInteger(p.task_count)&&p.task_count>=0?p.task_count:null,
      root_binding:{status:['KNOWN','UNKNOWN','INVALID','AMBIGUOUS'].includes(binding.status)?binding.status:'UNKNOWN',availability:binding.status==='KNOWN'&&['AVAILABLE','MISSING','INVALID','UNKNOWN'].includes(binding.availability)?binding.availability:'UNKNOWN',source:binding.source||null},
      provenance:{source:p.provenance?.source==='codex.projects+codex.project_roots'?p.provenance.source:null,machine_ownership:'UNKNOWN',archive_state:'UNKNOWN'},
      logo:{status:'UNKNOWN',artifact:null}};
  });
  return {projects,cursor:raw.cursor,observationCursor,truncated:raw.truncated===true};
}
export function projectDetail(raw,id) {
  const p=raw?.projects?.find(p=>p.id===id);
  if (!p || raw.projects.some(p=>p.id!==id)) throw Error('Project scope mismatch');
  const scope=raw.progress?.projects?.[id];
  const bound=scope?.scope?.project_id===id;
  const m=bound?scope.current_milestone:null;
  if(raw?.overview_metrics?.accepted_scope_id!==id||raw.overview_metrics.accepted_cursor?.scope_id!==id||!raw.overview_metrics.accepted_cursor?.digest)throw Error('Project cursor mismatch');
  const seenTasks=new Set();
  const tasksAvailable=bound&&Array.isArray(scope.tasks)&&scope.tasks.every(t=>{
    if(!t||t.project_id!==id||typeof t.id!=='string'||!t.id.trim()||seenTasks.has(t.id))return false;
    seenTasks.add(t.id);return true;
  });
  const taskText=(value,max)=>typeof value==='string'&&value.trim()&&Array.from(value).length<=max&&!/[\u0000-\u001f\u007f-\u009f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]/u.test(value)?value.trim():null;
  const taskRows=tasksAvailable?[...scope.tasks].sort((a,b)=>Number(b.state==='ACTIVE')-Number(a.state==='ACTIVE')).map(t=>{
    const candidateId=taskText(t.display_id,64);
    const displayId=candidateId&&/^[A-Z]{1,4}-[1-9][0-9]*$/.test(candidateId)?candidateId:null,label=taskText(t.label,160);
    const lifecycle=t.durable_lifecycle,identity=raw.progress?.task_identity,cursor=identity?.ledger_cursor;
    const lifecycleBound=identity?.state==='KNOWN'&&lifecycle?.source==='ledger:bound-task-acceptance'&&
      /^sha256:[a-f0-9]{64}$/.test(lifecycle.manifest_digest||'')&&Number.isSafeInteger(cursor?.event_seq)&&
      typeof cursor?.event_id==='string'&&typeof cursor?.event_digest==='string'&&cursor.event_digest.length>0&&
      ['event_seq','event_id','event_digest'].every(key=>lifecycle.ledger_cursor?.[key]===cursor[key])&&
      ['OPEN','COMPLETED'].includes(lifecycle.state);
    return {id:t.id,name:[displayId,label].filter(Boolean).join(' \u00b7 ')||'Task '+t.id,
      status:lifecycle!==undefined?(lifecycleBound?lifecycle.state:'Unknown'):typeof t.state==='string'&&t.state.trim()?t.state:'Unknown'};
  }):[];
  return {taskRows,tasksAvailable,tasksTruncated:tasksAvailable&&scope.truncated===true,updated:Number.isSafeInteger(p.updated_at)&&p.updated_at>0?p.updated_at:null,
    milestone:m?.state==='KNOWN'&&typeof m.name==='string'?m.name:null,
    tasks:bound&&Number.isSafeInteger(scope.counts?.tasks)?scope.counts.tasks:null,
    progress:bound&&scope.measurement_status==='measured'&&Number.isFinite(scope.progress)?scope.progress:null,
    cursor:raw.overview_metrics?.accepted_scope_id===id?raw.overview_metrics.accepted_cursor:null};
}
export function metricView(raw) {
  const m=raw?.overview_metrics;
  if(m?.accepted_scope_id!=='all'||m.accepted_cursor?.scope_id!=='all'||!m.accepted_cursor?.digest) return null;
  const field=(name,value)=>['KNOWN','PARTIAL'].includes(m.field_state?.[name])&&Number.isSafeInteger(value)&&value>=0?{value,partial:m.field_state[name]==='PARTIAL'}:null;
  return {active:field('active_projects',m.active_work?.active_projects),lanes:field('active_lanes',m.active_work?.active_lanes),attention:field('actionable_items',m.needs_attention?.actionable_items),completed:field('completed',m.verified_progress?.completed),cursor:m.accepted_cursor};
}
