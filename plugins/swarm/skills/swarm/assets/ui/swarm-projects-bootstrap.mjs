import {mountSettings} from './swarm-settings.js';
import {configTextWithChanges} from '@swarm/config-editor';
import settingsCSS from './swarm-settings.css';
import {App,applyDocumentTheme,applyHostStyleVariables} from '@swarm/sdk';
import {usageView,readProjectUsage,latestRequest} from './swarm-usage.mjs';
import {rosterView,projectDetail,metricView} from './swarm-projects.mjs';
// Flowwweb consumer-contract-v3: local route preparation only, not deployed.
export function supportCheckoutURL(amount){
 if(typeof amount!=='string'||!/^\d+(?:\.\d{1,2})?$/.test(amount))return null;
 const cents=Math.round(Number(amount)*100);if(!Number.isSafeInteger(cents)||cents<100||cents>1000000)return null;
 return 'https://flowwweb.com/1M?source=swarm&amount='+encodeURIComponent((cents/100).toFixed(2))+'&checkout=1#support';
}
export async function mountProjects() {
const app=new App({name:'SWARM HQ',version:'1.0.0'},{availableDisplayModes:['fullscreen']},{autoResize:false});
const $=s=>document.querySelector(s), root=document.documentElement;
const text=(selector,value)=>{$(selector).textContent=value;};
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const label={active:'Active',inactive:'Inactive',recently_active:'Recently active',unknown:'Unknown'};
const number=value=>value===null?'\u2014':value.toLocaleString();
let roster=null,metrics=null,filter='',view='list',generation=0,usageGeneration=0,detailGeneration=0,hours=24,lastUsage=null,dialogOpener=null,selectedProject=null,refreshPending=false;
function theme(ctx){if(ctx?.theme)applyDocumentTheme(ctx.theme);if(ctx?.styles?.variables)applyHostStyleVariables(ctx.styles.variables);}
app.onhostcontextchanged=theme;
async function call(name,args={}){const result=await app.callServerTool({name,arguments:args},undefined,{timeout:20000});if(result.isError)throw Error('Unavailable');return result.structuredContent||JSON.parse(result.content.find(c=>c.type==='text').text);}
document.querySelectorAll('.brand-links img,.support-portrait').forEach(image=>{
 const fallback=image.nextElementSibling;const hasFallback=fallback?.hasAttribute('data-brand-fallback');
 if(!hasFallback&&!image.matches('.support-portrait'))return;
 const failed=()=>{image.hidden=true;if(hasFallback)fallback.hidden=false;};
 image.addEventListener('error',failed);if(image.complete&&!image.naturalWidth)failed();
});
const amount=$('#support-custom'),checkout=$('.support-checkout');
function supportAmount(){const choice=document.querySelector('[name="support-amount"]:checked').value;amount.hidden=choice!=='custom';const url=supportCheckoutURL(choice==='custom'?amount.value:choice);amount.setCustomValidity(choice==='custom'&&!url?'Enter $1 to $10,000 with up to two decimal places.':'');checkout.dataset.preparedUrl=url||'';}
document.querySelector('.support-amounts').addEventListener('change',supportAmount);amount.addEventListener('input',supportAmount);supportAmount();
const externalLinks=new Set(['https://x.com/PeikGabriel','https://github.com/peikgabriel','https://flowwweb.com','https://flowwweb.com/1M','https://flowwweb.com/1M#support']);
document.addEventListener('click',async event=>{
 const link=event.target.closest('a[data-external]');if(!link)return;
 event.preventDefault();if(link===checkout){if(!amount.hidden&&!amount.checkValidity())amount.reportValidity();else text('#support-link-status','Checkout is not available yet.');return;}const url=link.getAttribute('href');if(!externalLinks.has(url))return;
 try{const result=await app.openLink({url});if(result?.isError)throw Error('Unavailable');text('#support-link-status','');}
 catch{text('#support-link-status','Could not open this link. Try again.');}
});
function projectHref(id){return '#project='+encodeURIComponent(id);}
function busy(button,on){button.disabled=on;button.setAttribute('aria-busy',String(on));}
function icon(p){return `<span class="project-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M3 7V5h7l2 2h9v13H3Z"/></svg></span>`;}
function status(p){return `<span class="status ${p.status}"><span class="status-dot" aria-hidden="true"></span>${label[p.status]}</span>`;}
function openButton(p){return `<button data-project="${escape(p.id)}" aria-label="Open ${escape(p.name)}">Open <span aria-hidden="true">\u2192</span></button>`;}
function filtered(){const query=$('#project-search').value.trim().toLocaleLowerCase();return (roster?.projects||[]).filter(p=>(!filter||p.status===filter)&&(!query||p.name.toLocaleLowerCase().includes(query)));}
function render(){
 const query=$('#project-search').value.trim().toLocaleLowerCase();const rows=filtered();
 $('#project-nav').innerHTML=(roster?.projects||[]).filter(p=>!query||p.name.toLocaleLowerCase().includes(query)).map(p=>`<a class="project-link ${p.status}" href="${projectHref(p.id)}" data-project="${escape(p.id)}">${icon(p)}<span class="name">${escape(p.name)}</span><span class="status-dot" aria-label="${label[p.status]}"></span></a>`).join('')||'<p class="quiet">No matching projects.</p>';
 $('#clear-filter').hidden=!filter&&!query;
 document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===view)));
 if(!rows.length){$('#project-content').innerHTML='<p class="empty">'+(roster?'No matching projects.':'Project inventory unavailable. Use Refresh to try again.')+'</p>';return;}
 if(view==='list')$('#project-content').innerHTML=`<div class="table-scroll"><table><thead><tr><th scope="col">Project</th><th scope="col">Activity</th><th scope="col">Next milestone</th><th scope="col">Next action</th><th scope="col">Updated</th><th scope="col"><span class="quiet">Details</span></th></tr></thead><tbody>${rows.map(p=>`<tr><td class="project-name"><a href="${projectHref(p.id)}" data-project="${escape(p.id)}">${icon(p)}${escape(p.name)}</a></td><td>${status(p)}</td><td class="cell-unknown" aria-label="Milestone unavailable" title="Milestone unavailable">\u2014</td><td class="cell-unknown" aria-label="Next action unavailable" title="Next action unavailable">\u2014</td><td class="updated" aria-label="Update time unavailable" title="Open project details for its last task update">\u2014</td><td>${openButton(p)}</td></tr>`).join('')}</tbody></table></div>`;
 if(view==='constellation')$('#project-content').innerHTML=`<div class="constellation"><p class="view-note">Registered projects. No project relationships are supplied.</p>${rows.map(p=>`<button data-project="${escape(p.id)}" aria-label="Open ${escape(p.name)}">${icon(p)}<span>${escape(p.name)}</span>${status(p)}</button>`).join('')}</div>`;
 if(view==='flow')$('#project-content').innerHTML=`<div class="flow"><p class="view-note">Grouped by observed activity, not task sequence or dependency.</p>${Object.keys(label).map(s=>`<section><h3>${label[s]}</h3>${rows.filter(p=>p.status===s).map(p=>`<button data-project="${escape(p.id)}">${escape(p.name)}</button>`).join('')||'<p class="quiet small">No projects in this group.</p>'}</section>`).join('')}</div>`;
}
function showDialog(title,html){detailGeneration++;dialogOpener=document.activeElement;text('#inspector-title',title);$('#inspector-body').innerHTML=html;if(!$('#inspector').open)$('#inspector').showModal();$('#close-inspector').focus();}
$('#close-inspector').onclick=()=>$('#inspector').close();
$('#inspector').addEventListener('close',()=>{detailGeneration++;if(dialogOpener?.isConnected)dialogOpener.focus();});
const projectPage=document.createElement('main');projectPage.id='project-page';projectPage.hidden=true;$('.hq-footer').before(projectPage);
function projectShell(p,body){const restoreFocus=projectPage.contains(document.activeElement);projectPage.innerHTML=`<header class="page-header"><div><a href="#projects" class="project-back">&larr; Projects</a><h1 tabindex="-1">${escape(p.name)}</h1></div></header>${body}`;if(restoreFocus)projectPage.querySelector('h1').focus();}
const projectUsageRequests=latestRequest();
const projectUsagePeriod=value=>value===24?'Last 24 hours':value===168?'Last 7 days':'Last 30 days';
async function loadProjectUsage(id,value){
 const section=projectPage.querySelector('#project-usage');if(!section||projectPage.hidden||selectedProject!==id)return;
 const token=projectUsageRequests.next(),detail=detailGeneration,field=name=>section.querySelector(`[data-project-usage="${name}"]`);
 const current=()=>projectUsageRequests.isLatest(token)&&detail===detailGeneration&&selectedProject===id&&section.isConnected&&!projectPage.hidden;
 section.querySelectorAll('[data-project-hours]').forEach(b=>b.setAttribute('aria-pressed',String(+b.dataset.projectHours===value)));
 field('period').textContent=projectUsagePeriod(value);field('total').textContent='\u2014';field('window').textContent='';field('status').textContent='Loading local observations\u2026';
 const result=await readProjectUsage(call,id,value,current);
 if(result.state==='stale'||!current())return;
 if(result.state!=='ready'){field('status').textContent='Usage for this project is unavailable for this period. Select a period to retry.';return;}
 const data=result.view;field('total').textContent=number(data.total);
 field('window').textContent=`Observed window: ${new Date(data.window.after_ms).toLocaleString()} to ${new Date(data.window.before_ms).toLocaleString()}.`;
 field('status').textContent=data.total===null?'No retained observations for this project in this period.':`${data.status==='partial'?'Partial coverage':'Observed coverage'} \u00b7 gaps are not zero.`;
}
projectPage.addEventListener('click',e=>{const button=e.target.closest('[data-project-hours]');if(button&&selectedProject)loadProjectUsage(selectedProject,+button.dataset.projectHours);});
async function openProject(id){
 const p=roster?.projects.find(p=>p.id===id);if(!p)return;
 selectedProject=id;const request=++detailGeneration;$('#main').hidden=true;settingsPage.hidden=true;projectPage.hidden=false;
 $('#settings').classList.remove('selected');$('#settings').removeAttribute('aria-current');$('#all-projects').classList.remove('selected');
 projectShell(p,'<p role="status">Loading project...</p>');projectPage.querySelector('h1').focus();
 try{const data=projectDetail(await call('swarm_status',{project_id:id}),id);if(request!==detailGeneration||selectedProject!==id)return;
 projectShell(p,`<section class="project-section"><h2>Overview</h2><dl><dt>Activity</dt><dd>${status(p)}</dd><dt>Current milestone</dt><dd>${escape(data.milestone||'Current milestone unavailable')}</dd><dt>Measured progress</dt><dd>${data.progress===null?'Unknown':escape(String(data.progress))}</dd><dt>Last task update</dt><dd>${data.updated?escape(new Date(data.updated).toLocaleString()):'Unknown'}</dd></dl></section><section class="project-section"><h2>Tasks</h2>${data.taskRows.length?`<ul>${data.taskRows.map(t=>`<li><strong>${escape(t.name)}</strong><span>${escape(t.status)}</span></li>`).join('')}</ul>`:`<p>${data.tasksAvailable?'No retained tasks.':'Task details unavailable.'}</p>`}${data.tasksTruncated?'<p>More tasks unavailable.</p>':''}</section><section class="project-section" id="project-usage" aria-labelledby="project-usage-title"><div class="section-heading"><h2 id="project-usage-title">Usage</h2><div class="period-switch" role="group" aria-label="Project usage period"><button data-project-hours="24" aria-pressed="true">24h</button><button data-project-hours="168" aria-pressed="false">7d</button><button data-project-hours="720" aria-pressed="false">30d</button></div></div><p><strong data-project-usage="total">\u2014</strong> <span class="quiet small" data-project-usage="period">Last 24 hours</span></p><p class="quiet small" data-project-usage="window"></p><p role="status" data-project-usage="status">Loading local observations\u2026</p><p class="quiet small">Locally observed token deltas for this project. Not billing; gaps are not zero.</p></section><details><summary>Diagnostics</summary><code>${escape(id)}</code><p><code>${escape(JSON.stringify(data.cursor||'Cursor unavailable'))}</code></p></details>`);void loadProjectUsage(id,24);
 }catch{if(request===detailGeneration&&selectedProject===id)projectShell(p,'<p role="status">Project details unavailable. Return to Projects and try again.</p>');}
}
// One scoped editor; drafts stay in the mounted form, never in a second store.
function libraryEditor(library,lens){
 const epoch=detailGeneration,active=()=>epoch===detailGeneration&&!projectPage.hidden;
 let snapshot=null,uncertain=null,pending=false;
 projectShell({name:library==='roles'?'Roles':'Units'},`<nav aria-label="Library views"><a class="project-back" href="#${library}">${library==='roles'?'Roles':'Units'}</a> <a class="project-back" href="#${library}/flows">Flows</a> <a class="project-back" href="#${library}/loops">Loops</a></nav><label>Project <select data-library-project>${(roster?.projects||[]).map(p=>`<option value="${escape(p.id)}">${escape(p.name)}</option>`).join('')}</select></label>${library==='units'?'<label>Unit type <select data-library-kind><option value="LAB">Labs</option><option value="FACTORY">Factories</option></select></label>':''}<button data-library-load>Load</button><p role="status" data-library-status></p><div data-library-body></div>`);
 const q=sel=>projectPage.querySelector(sel),body=q('[data-library-body]'),status=q('[data-library-status]'),picker=q('[data-library-project]');
 const kind=()=>library==='roles'?'ROLE':q('[data-library-kind]').value;
 let serial=0;
 const valid=(v,id,k)=>v?.ok===true&&v.project_id===id&&typeof v.source_digest==='string'&&Array.isArray(v.definitions)&&Array.isArray(v.assignments)&&(!k||v.kind===k);
 async function read(id,k){const v=await call('swarm_library_read',{project_id:id,kind:k});if(!valid(v,id,k))throw Error('Library could not be confirmed.');return v;}
 function form(v){
  const rows=kind()==='ROLE'?v.inventory?.roles:v.inventory?.instances;
  if(!Array.isArray(rows))throw Error('Inventory unavailable.');
  const subjects=rows.filter(r=>kind()==='ROLE'?typeof r.id==='string'&&r.active_version:r.project_id===picker.value&&r.subject_version&&r.ctrl_id);
  const subjectKey=r=>JSON.stringify([v.project_id,kind(),r.id||r.task_id,kind()==='ROLE'?r.active_version:r.subject_version,kind()==='ROLE'?null:r.ctrl_id]);
  const flowKey=f=>JSON.stringify([v.project_id,f.id,f.version,f.digest]);
  body.innerHTML=`<p>${subjects.length} ${kind()==='ROLE'?'roles':'instances'}</p><form data-assignment><label>${kind()==='ROLE'?'Role':'Instance'} <select name="subject" required>${subjects.map(r=>`<option value="${escape(subjectKey(r))}">${escape(r.name||r.task_id)}</option>`).join('')}</select></label><label>Flow <select name="flow" required>${v.definitions.map(r=>`<option value="${escape(flowKey(r))}">${escape(r.id)} \u00b7 v${r.version}</option>`).join('')}</select></label><label>Label <input name="label" maxlength="160"></label><label>Notes <textarea name="notes" maxlength="2048"></textarea></label><label>Repeat count <input name="repeat" type="number" min="1" max="9007199254740991" step="1" value="1" required></label><button ${!subjects.length||!v.definitions.length?'disabled':''}>Save assignment</button></form><details ${lens==='flows'?'open':''}><summary>Edit Flow definition</summary><form data-flow><label>Flow <select name="existing"><option value="">New Flow</option>${v.definitions.map(f=>`<option value="${escape(flowKey(f))}">${escape(f.id)} \u00b7 v${f.version}</option>`).join('')}</select></label><label>Definition <textarea name="definition" rows="12" required></textarea></label><button>Save Flow</button></form></details>`;
  const assignment=q('[data-assignment]'),flow=q('[data-flow]');
  const selectSubject=()=>{if(assignment.dataset.keepDraft)return;const r=subjects.find(r=>subjectKey(r)===assignment.elements.subject.value);if(!r)return;const previous=v.assignments.filter(a=>a.subject_kind===kind()&&a.subject_id===(r.id||r.task_id)&&a.ctrl_id===(kind()==='ROLE'?null:r.ctrl_id)).sort((a,b)=>b.version-a.version)[0];assignment.elements.label.value=previous?.label||'';assignment.elements.notes.value=previous?.notes||'';assignment.elements.repeat.value=previous?.repeat_count||1;const index=v.definitions.findIndex(f=>f.id===previous?.flow_id&&f.version===previous?.flow_version&&f.digest===previous?.flow_digest);if(index>=0)assignment.elements.flow.value=flowKey(v.definitions[index]);};
  body.onchange=e=>{if(e.target.tagName==='SELECT')e.target.setCustomValidity('');};
  assignment.elements.subject.onchange=selectSubject;selectSubject();
  flow.elements.definition.value=JSON.stringify(v.starter,null,2);flow.elements.existing.onchange=()=>{if(flow.dataset.keepDraft)return;const f=v.definitions.find(f=>flowKey(f)===flow.elements.existing.value);flow.elements.definition.value=JSON.stringify(flow.elements.existing.value===''?v.starter:{id:f.id,version:Math.max(...v.definitions.filter(d=>d.id===f.id).map(d=>d.version))+1,objective:f.objective,nodes:f.nodes},null,2);};
  assignment.onsubmit=e=>{e.preventDefault();const r=subjects.find(r=>subjectKey(r)===assignment.elements.subject.value),f=v.definitions.find(f=>flowKey(f)===assignment.elements.flow.value),repeat=Number(assignment.elements.repeat.value);if(!r||!f||!Number.isSafeInteger(repeat)||repeat<1)return;const ctrl=kind()==='ROLE'?null:r.ctrl_id,versions=v.assignments.filter(a=>a.subject_kind===kind()&&a.subject_id===(r.id||r.task_id)&&a.ctrl_id===ctrl).map(a=>a.version);save('swarm_flow_assign',{assignment:{version:Math.max(0,...versions)+1,subject_kind:kind(),subject_id:r.id||r.task_id,subject_version:kind()==='ROLE'?r.active_version:r.subject_version,ctrl_id:ctrl,flow_id:f.id,flow_version:f.version,flow_digest:f.digest,label:assignment.elements.label.value,notes:assignment.elements.notes.value,repeat_count:repeat}});};
  flow.onsubmit=e=>{e.preventDefault();if(!flow.checkValidity())return;try{save('swarm_flow_save',{definition:JSON.parse(flow.elements.definition.value)});}catch{status.textContent='Enter valid JSON. Your draft is preserved.';}};
 }
 async function load(){if(pending)return;const id=picker.value,k=kind(),token=++serial;if(!id){status.textContent='Choose a saved project.';return;}status.textContent='Loading\u2026';try{const v=await read(id,k);if(!active()||token!==serial)return;snapshot=v;form(v);status.textContent='';}catch(e){if(active()&&token===serial)status.textContent=e.message;}}
 const sameRecord=(r,d)=>Object.keys(d).every(k=>JSON.stringify(r[k])===JSON.stringify(d[k]));
 async function save(tool,part){
  if(pending||uncertain||!snapshot)return;
  const id=picker.value,k=kind(),token=serial,request={project_id:id,expected_digest:snapshot.source_digest,...part,acknowledge:true};pending=true;status.textContent='Saving\u2026';const controls=[...projectPage.querySelectorAll('input,select,textarea,button')];const disabled=controls.map(c=>c.disabled);controls.forEach(c=>c.disabled=true);
  try{const result=await call(tool,request);if(!valid(result,id))throw Error('Save was not confirmed.');const key=part.assignment?'assignments':'definitions',draft=part.assignment||part.definition,record=result[key].find(r=>sameRecord(r,draft));if(!record?.digest)throw Error('Save receipt did not match.');const fresh=await read(id,k);if(!active()||token!==serial)return;if(fresh.source_digest!==result.source_digest||!fresh[key].some(r=>r.digest===record.digest&&sameRecord(r,draft)))throw Error('Readback changed.');snapshot=fresh;form(fresh);q(part.assignment?'[data-assignment] button':'[data-flow] button')?.focus();status.textContent='Saved';}
  catch{if(active()&&token===serial){uncertain={tool,part,id,k};status.textContent='Save not confirmed. Draft preserved. Reload to reconcile.';}}
  finally{pending=false;if(active()){controls.forEach((c,i)=>{if(c.isConnected)c.disabled=disabled[i];});}}
 }
 q('[data-library-load]').onclick=async()=>{if(!uncertain){load();return;}const u=uncertain,token=serial;status.textContent='Checking saved data\u2026';try{const fresh=await read(u.id,u.k);if(!active()||token!==serial||picker.value!==u.id||kind()!==u.k)return;const key=u.part.assignment?'assignments':'definitions',draft=u.part.assignment||u.part.definition;if(fresh[key].some(r=>r.digest&&sameRecord(r,draft))){uncertain=null;snapshot=fresh;form(fresh);q(u.part.assignment?'[data-assignment] button':'[data-flow] button')?.focus();status.textContent='Saved';}else{const draftValues=[...body.querySelectorAll('input,textarea,select')].map(c=>[c.name,c.value]);uncertain=null;snapshot=fresh;form(fresh);let changed=false;for(const [name,value] of draftValues){const control=[...body.querySelectorAll('input,textarea,select')].find(c=>c.name===name);if(!control)continue;if(control.tagName==='SELECT'&&![...control.options].some(o=>o.value===value)){const option=new Option('Previous selection unavailable. Choose again.',value,true,true);option.disabled=true;control.add(option);control.setCustomValidity('Choose a current selection.');if(name==='subject'||name==='existing')control.form.dataset.keepDraft='true';changed=true;}control.value=value;}status.textContent=changed?'A selected object changed or is unavailable. Choose a current selection; your draft is preserved.':'Source reloaded. Review your preserved draft before saving again.';}}catch{if(active())status.textContent='Could not reconcile. Draft preserved.';}};
 picker.onchange=()=>{uncertain=null;snapshot=null;body.replaceChildren();load();};if(q('[data-library-kind]'))q('[data-library-kind]').onchange=picker.onchange;load();
}
function hideSupport(){ $('#support-page').hidden=true;$('#support').classList.remove('selected');$('#support').removeAttribute('aria-current'); }
function restoreRoute(){
 hideSupport();
 if(location.hash==='#support'){
  detailGeneration++;selectedProject=null;projectPage.hidden=true;settingsPage.hidden=true;$('#main').hidden=true;$('#support-page').hidden=false;
  $('#all-projects').classList.remove('selected');$('#settings').classList.remove('selected');$('#settings').removeAttribute('aria-current');$('#support').classList.add('selected');$('#support').setAttribute('aria-current','page');$('#support-title').focus();return;
 }

 const [library,lens]=location.hash.slice(1).split('/');const section=['units','roles'].includes(library)&&(!lens||['flows','loops'].includes(lens))?{units:'Units',roles:'Roles'}[library]:null;
 if(section){detailGeneration++;selectedProject=null;$('#main').hidden=true;settingsPage.hidden=true;projectPage.hidden=false;
 $('#settings').classList.remove('selected');$('#settings').removeAttribute('aria-current');$('#all-projects').classList.remove('selected');
 libraryEditor(library,lens);projectPage.querySelector('h1').focus();return;}
 const match=location.hash.match(/^#project=(.+)$/);let id=null;try{id=match?decodeURIComponent(match[1]):null;}catch{}
 if(id&&roster?.projects.some(p=>p.id===id)){openProject(id);return;}
 detailGeneration++;selectedProject=null;projectPage.hidden=true;settingsPage.hidden=true;$('#main').hidden=false;
 $('#settings').classList.remove('selected');$('#settings').removeAttribute('aria-current');$('#all-projects').classList.add('selected');
 if(match)text('#roster-status','This project is unavailable. Showing Projects.');
 $('#main h1').tabIndex=-1;$('#main h1').focus();
}
window.addEventListener('hashchange',restoreRoute);
document.addEventListener('click',e=>{const target=e.target.closest('[data-project]');if(!target||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey||e.button)return;
 if(target.tagName==='A'){if(location.hash===target.getAttribute('href')){e.preventDefault();restoreRoute();}return;}
 const next=projectHref(target.dataset.project);if(location.hash===next)restoreRoute();else location.hash=next;
});
$('#search-toggle').onclick=()=>{const input=$('#project-search'),open=input.hidden;input.hidden=!open;$('.wordmark').hidden=open;$('#search-toggle').setAttribute('aria-expanded',String(open));if(open)input.focus();else{input.value='';render();}};
$('#project-search').addEventListener('input',render);
$('#project-search').addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();$('#search-toggle').click();$('#search-toggle').focus();}});
function reset(){filter='';$('#project-search').value='';render();}
$('#clear-filter').onclick=reset;$('#all-projects').onclick=()=>{reset();$('#main').scrollIntoView({block:'start'});};
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{view=b.dataset.view;render();});
function coverage(){showDialog('Observation coverage',`<p>Registered project identities and activity come from the host\u2019s saved-project inventory. Activity does not grant a role, execution permission or completion credit.</p><p>Milestones, next actions, favorites and updated timestamps are not included in this roster. Open a project for its separately scoped details.</p><p>Decision counts, agent lanes and completed tasks are shown only when the accepted metrics fields are known. Partial counts are marked.</p><code>${escape(JSON.stringify(metrics?.cursor||roster?.cursor||'Unavailable'))}</code>`);}
$('#attention-details').onclick=coverage;
const settingsStyle=document.createElement('style');settingsStyle.textContent=settingsCSS;document.head.append(settingsStyle);
const settingsPage=document.createElement('main');settingsPage.id='settings-page';settingsPage.hidden=true;
const closeSettings=document.createElement('button');closeSettings.textContent='\u00d7';closeSettings.className='icon-action';closeSettings.setAttribute('aria-label','Close settings');closeSettings.title='Close settings';
const settingsPanel=document.createElement('section');settingsPage.append(closeSettings,settingsPanel);
$('.hq-footer').before(settingsPage);
let settingsMounted=false;
function leaveSettings(){hideSupport();projectPage.hidden=true;selectedProject=null;detailGeneration++;settingsPage.hidden=true;$('#main').hidden=false;$('#settings').classList.remove('selected');$('#settings').removeAttribute('aria-current');$('#all-projects').classList.add('selected');$('#settings').focus();}
closeSettings.onclick=leaveSettings;
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!settingsPage.hidden){event.preventDefault();leaveSettings();}});
const projectsHome=$('#all-projects').onclick;$('#all-projects').onclick=()=>{leaveSettings();projectsHome();if(location.hash!=='#projects')location.hash='projects';};
$('#settings').disabled=true;
$('#settings').onclick=async()=>{
 hideSupport();
 detailGeneration++;selectedProject=null;projectPage.hidden=true;$('#main').hidden=true;settingsPage.hidden=false;$('#all-projects').classList.remove('selected');$('#settings').classList.add('selected');$('#settings').setAttribute('aria-current','page');closeSettings.focus();
 if(settingsMounted)return;settingsMounted=true;
 let scopes=[];
 try{const data=await call('swarm_projects');if(data.available===true&&data.cursor&&typeof data.cursor==='object'&&!Array.isArray(data.cursor))
 scopes=(data.projects||[]).filter(p=>typeof p.id==='string').map(p=>({label:p.name||p.id,scope:{type:'project',project_id:p.id,accepted_cursor:data.cursor}}));}catch{}
 mountSettings(settingsPanel,{app,scopes,editText:configTextWithChanges});
};
const metric=x=>x&&!x.partial?number(x.value):'\u2014';
async function refresh(){if(refreshPending)return;refreshPending=true;const request=++generation;busy($('#refresh'),true);text('#roster-status','Loading projects...');
 const rosterRead=(async()=>{try{const next=rosterView(await call('swarm_projects'));if(request!==generation)return;roster=next;render();text('#project-count',number(next.projects.length));text('#roster-status',`${next.projects.length} projects${next.truncated?' (more unavailable)':''}`);if(location.hash.startsWith('#project=')&&!selectedProject)restoreRoute();}
 catch{if(request===generation){text('#roster-status',roster?'Refresh unavailable. Last observation may be stale.':'Projects unavailable. Refresh to retry.');if(!roster)render();}}})();
 const metricsRead=(async()=>{let next=null;try{next=metricView(await call('swarm_status'));}catch{}if(request!==generation)return;metrics=next;text('#attention-copy',metrics?.attention&&!metrics.attention.partial?(metrics.attention.value===0?'Nothing needs your attention.':`${number(metrics.attention.value)} items need your attention.`):'Attention items are unavailable.');text('#lane-count',metric(metrics?.lanes));text('#completed-count',metric(metrics?.completed));})();
 try{await Promise.all([rosterRead,metricsRead]);}finally{if(request===generation){refreshPending=false;busy($('#refresh'),false);}}
}
function usageDetails(){showDialog('Token observations',`<p>Input plus output from retained local token deltas, not billing. Cached input and reasoning are subsets, not added again.</p><p>${lastUsage?`Observed window: ${escape(new Date(lastUsage.window.after_ms).toLocaleString())} to ${escape(new Date(lastUsage.window.before_ms).toLocaleString())}.`:'No valid observation is available for this period.'}</p><p>Points show observation time. Gaps are not zero and are not connected. Account limits, reset times, forecasts, per-project allocations and API-price equivalents are not supplied by this view.</p>`);}
$('#usage-details').onclick=usageDetails;
async function loadUsage(value){hours=value;const request=++usageGeneration;lastUsage=null;document.querySelectorAll('[data-hours]').forEach(b=>b.setAttribute('aria-pressed',String(+b.dataset.hours===value)));text('.usage-period',value===24?'Last 24 hours':value===168?'Last 7 days':'Last 30 days');text('.usage-total','\u2014');text('.usage-coverage','Loading local observations\u2026');$('.usage-chart').replaceChildren();
 try{const data=usageView(await call('swarm_usage',{hours:value}),value);if(request!==usageGeneration)return;const span=data.window.before_ms-data.window.after_ms;if(span<=0)throw Error('Invalid window');lastUsage=data;text('.usage-total',number(data.total));text('.usage-coverage',data.total===null?'No retained observations for this period.':`${data.status==='partial'?'Partial coverage':'Observed coverage'} \u00b7 gaps are not zero.`);const max=Math.max(1,...data.points.map(p=>p.tokens));
 const svg=$('.usage-chart');svg.hidden=data.total===null;$('.chart-wrap').classList.toggle('empty-chart',data.total===null);const node=(name,attrs,content)=>{const n=document.createElementNS(svg.namespaceURI,name);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);if(content)n.textContent=content;svg.append(n);return n;};
 for(let i=0;i<4;i++){const y=12+i*38;node('line',{x1:50,y1:y,x2:895,y2:y});if(data.total!==null)node('text',{x:0,y:y+4},Intl.NumberFormat(undefined,{notation:'compact',maximumFractionDigits:1}).format(max*(1-i/3)));}
 if(data.total!==null)for(const p of data.points){const dot=node('circle',{cx:50+(p.at-data.window.after_ms)/span*845,cy:126-p.tokens/max*114,r:2.5});const title=document.createElementNS(svg.namespaceURI,'title');title.textContent=`${new Date(p.at).toLocaleString()}: ${p.tokens.toLocaleString()} tokens`;dot.append(title);}
 }catch{if(request!==usageGeneration)return;text('.usage-total','\u2014');$('.usage-chart').replaceChildren();$('.usage-chart').hidden=true;$('.chart-wrap').classList.add('empty-chart');text('.usage-coverage','Usage unavailable. Select a period to retry.');}}
document.querySelectorAll('[data-hours]').forEach(b=>b.onclick=()=>loadUsage(+b.dataset.hours));
$('#refresh').onclick=()=>{if(refreshPending)return;refresh();loadUsage(hours);};
app.onteardown=async()=>{generation++;usageGeneration++;detailGeneration++;root.dataset.swarmHost='closed';selectedProject=null;projectPage.hidden=true;$('#settings').disabled=true;settingsPage.hidden=true;$('#main').hidden=false;return {};};
try{await app.connect(undefined,{timeout:5000});theme(app.getHostContext());root.dataset.swarmHost='initialized';$('#settings').disabled=!app.getHostCapabilities()?.serverTools;await Promise.all([refresh(),loadUsage(hours)]);if(/^#(?:roles|units)(?:\/(?:flows|loops))?$|^#support$/.test(location.hash))restoreRoute();}catch{root.dataset.swarmHost='unavailable';text('#roster-status','Host connection unavailable. Reopen SWARM to reconnect.');text('.usage-coverage','Usage unavailable while disconnected.');text('#attention-copy','Attention items are unavailable.');}
}
