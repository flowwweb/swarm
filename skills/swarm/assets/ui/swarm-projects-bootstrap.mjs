import {mountSettings} from './swarm-settings.js';
import {configTextWithChanges} from '@swarm/config-editor';
import settingsCSS from './swarm-settings.css';
import {App,applyDocumentTheme,applyHostStyleVariables} from '@swarm/sdk';
import {usageView} from './swarm-usage.mjs';
import {rosterView,projectDetail,metricView} from './swarm-projects.mjs';
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
const projectPage=document.createElement('main');projectPage.id='project-page';projectPage.hidden=true;$('.workspace').append(projectPage);
function projectShell(p,body){const restoreFocus=projectPage.contains(document.activeElement);projectPage.innerHTML=`<header class="page-header"><div><a href="#projects" class="project-back">&larr; Projects</a><h1 tabindex="-1">${escape(p.name)}</h1></div></header>${body}`;if(restoreFocus)projectPage.querySelector('h1').focus();}
async function openProject(id){
 const p=roster?.projects.find(p=>p.id===id);if(!p)return;
 selectedProject=id;const request=++detailGeneration;$('#main').hidden=true;settingsPage.hidden=true;projectPage.hidden=false;
 $('#settings').classList.remove('selected');$('#settings').removeAttribute('aria-current');$('#all-projects').classList.remove('selected');
 projectShell(p,'<p role="status">Loading project...</p>');projectPage.querySelector('h1').focus();
 try{const data=projectDetail(await call('swarm_status',{project_id:id}),id);if(request!==detailGeneration||selectedProject!==id)return;
 projectShell(p,`<section class="project-section"><h2>Overview</h2><dl><dt>Activity</dt><dd>${status(p)}</dd><dt>Current milestone</dt><dd>${escape(data.milestone||'Current milestone unavailable')}</dd><dt>Measured progress</dt><dd>${data.progress===null?'Unknown':escape(String(data.progress))}</dd><dt>Last task update</dt><dd>${data.updated?escape(new Date(data.updated).toLocaleString()):'Unknown'}</dd></dl></section><section class="project-section"><h2>Tasks</h2>${data.taskRows.length?`<ul>${data.taskRows.map(t=>`<li><strong>${escape(t.name)}</strong><span>${escape(t.status)}</span></li>`).join('')}</ul>`:`<p>${data.tasksAvailable?'No retained tasks.':'Task details unavailable.'}</p>`}${data.tasksTruncated?'<p>More tasks unavailable.</p>':''}</section><section class="project-section"><h2>Usage</h2><p>Project-scoped usage is not available from this connection.</p></section><details><summary>Diagnostics</summary><code>${escape(id)}</code><p><code>${escape(JSON.stringify(data.cursor||'Cursor unavailable'))}</code></p></details>`);
 }catch{if(request===detailGeneration&&selectedProject===id)projectShell(p,'<p role="status">Project details unavailable. Return to Projects and try again.</p>');}
}
function restoreRoute(){
 const section={roles:'Roles',flows:'Flows',loops:'Loops',units:'Units'}[location.hash.slice(1)];
 if(section){detailGeneration++;selectedProject=null;$('#main').hidden=true;settingsPage.hidden=true;projectPage.hidden=false;
 $('#settings').classList.remove('selected');$('#settings').removeAttribute('aria-current');$('#all-projects').classList.remove('selected');
 projectShell({name:section},`<p role="status">${section} are unavailable from this connection.</p>${section==='Units'?'<p>Units contain Labs and Factories. Their records are not available yet.</p>':''}`);projectPage.querySelector('h1').focus();return;}
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
$('.workspace').append(settingsPage);
let settingsMounted=false;
function leaveSettings(){projectPage.hidden=true;selectedProject=null;detailGeneration++;settingsPage.hidden=true;$('#main').hidden=false;$('#settings').classList.remove('selected');$('#settings').removeAttribute('aria-current');$('#all-projects').classList.add('selected');$('#settings').focus();}
closeSettings.onclick=leaveSettings;
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!settingsPage.hidden){event.preventDefault();leaveSettings();}});
const projectsHome=$('#all-projects').onclick;$('#all-projects').onclick=()=>{leaveSettings();projectsHome();if(location.hash!=='#projects')location.hash='projects';};
$('#settings').disabled=true;
$('#settings').onclick=async()=>{
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
try{await app.connect(undefined,{timeout:5000});theme(app.getHostContext());root.dataset.swarmHost='initialized';$('#settings').disabled=!app.getHostCapabilities()?.serverTools;if(['#roles','#flows','#loops','#units'].includes(location.hash))restoreRoute();await Promise.all([refresh(),loadUsage(hours)]);}catch{root.dataset.swarmHost='unavailable';text('#roster-status','Host connection unavailable. Reopen SWARM to reconnect.');text('.usage-coverage','Usage unavailable while disconnected.');text('#attention-copy','Attention items are unavailable.');}
}
