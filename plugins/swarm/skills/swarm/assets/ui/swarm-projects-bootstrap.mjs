import {mountSettings} from './swarm-settings.js';
import {configTextWithChanges} from '@swarm/config-editor';
import {App,applyDocumentTheme,applyHostStyleVariables} from '@swarm/sdk';
import {usageView,readProjectUsage,latestRequest} from './swarm-usage.mjs';
import {rosterView,projectDetail,metricView} from './swarm-projects.mjs';
// Accepted Flowwweb v2 public-page route; checkout API and payment remain website-owned.
export function supportCheckoutURL(amount){
 if(typeof amount!=='string'||!/^\d+(?:\.\d{1,2})?$/.test(amount))return null;
 const cents=Math.round(Number(amount)*100);if(!Number.isSafeInteger(cents)||cents<100||cents>1000000)return null;
 return 'https://flowwweb.com/1M?source=swarm&amount='+encodeURIComponent((cents/100).toFixed(2))+'&checkout=1#support';
}
export function validSupportCheckoutURL(value){
 if(typeof value!=='string')return false;
 try{const u=new URL(value),keys=[...u.searchParams.keys()],amount=u.searchParams.get('amount');return value===u.href&&u.origin==='https://flowwweb.com'&&!u.username&&!u.password&&u.pathname==='/1M'&&u.hash==='#support'&&keys.length===3&&new Set(keys).size===3&&keys.every(k=>['source','amount','checkout'].includes(k))&&u.searchParams.get('source')==='swarm'&&u.searchParams.get('checkout')==='1'&&/^(?:[1-9]\d{0,3}|10000)\.\d{2}$/.test(amount)&&supportCheckoutURL(amount)!==null;}catch{return false;}
}
export function activeFirstProjects(projects){return [...projects].sort((a,b)=>Number(b.status==='active')-Number(a.status==='active'));}
// Geometry is derived from the retained dependency DAG, never saved into the definition.
export function flowLayout(definition,vertical=false){
 const rows=definition?.nodes;if(!Array.isArray(rows)||!rows.length||rows.length>64)return null;
 const byId=new Map(),depth=new Map(),visiting=new Set();
 for(const n of rows){if(!n||typeof n.id!=='string'||!n.id||byId.has(n.id)||typeof n.objective!=='string'||!Array.isArray(n.dependencies)||n.dependencies.length>64||new Set(n.dependencies).size!==n.dependencies.length)return null;byId.set(n.id,n);}
 function level(id){if(depth.has(id))return depth.get(id);if(!byId.has(id)||visiting.has(id))throw Error('Unbound or cyclic Flow');visiting.add(id);const d=byId.get(id).dependencies.reduce((max,p)=>Math.max(max,level(p)+1),0);visiting.delete(id);depth.set(id,d);return d;}
 try{rows.forEach(n=>level(n.id));}catch{return null;}
 const links=rows.flatMap(n=>n.dependencies.map(parent=>({source:parent,target:n.id}))),margin=24+links.length*5,counts=new Map();
 const nodes=rows.map(n=>{const d=depth.get(n.id),row=counts.get(d)||0;counts.set(d,row+1);return {id:n.id,label:n.objective,x:vertical?margin+row*224:24+d*224,y:vertical?24+d*128:margin+row*128,width:180,height:88};});
 const placed=new Map(nodes.map(n=>[n.id,n])),edges=links.map((e,i)=>{const a=placed.get(e.source),b=placed.get(e.target),track=12+i*5;
  const adjacent=depth.get(e.target)===depth.get(e.source)+1,points=adjacent?(vertical?[[a.x+90,a.y+88],[a.x+90,(a.y+88+b.y)/2],[b.x+90,(a.y+88+b.y)/2],[b.x+90,b.y]]:[[a.x+180,a.y+44],[(a.x+180+b.x)/2,a.y+44],[(a.x+180+b.x)/2,b.y+44],[b.x,b.y+44]]):vertical?[[a.x+90,a.y+88],[a.x+90,a.y+100],[track,a.y+100],[track,b.y-12],[b.x+90,b.y-12],[b.x+90,b.y]]:[[a.x+180,a.y+44],[a.x+192,a.y+44],[a.x+192,track],[b.x-12,track],[b.x-12,b.y+44],[b.x,b.y+44]];
  return {...e,points,path:points.map(([x,y],j)=>`${j?'L':'M'}${x} ${y}`).join(' ')};});
 return {nodes,edges,width:Math.max(...nodes.map(n=>n.x+n.width))+24,height:Math.max(...nodes.map(n=>n.y+n.height))+24,vertical};
}
// A Hive is an existing project/CTRL projection, never a new grouping or role roster.
export function hiveProjection(raw,projectId){
 const v=raw?.hives,fail=()=>{throw Error('Hive bindings unavailable.');};
 if(!v||!['KNOWN','PARTIAL'].includes(v.state)||!v.cursor||Array.isArray(v.cursor)||typeof v.cursor!=='object'||!Object.keys(v.cursor).length||v.read_only!==true||v.execution_authority!==false||!Array.isArray(v.items)||v.items.length>256)fail();
 const scopes=new Set();
 for(const h of v.items){
  if(h?.project_id!==projectId||typeof h.ctrl_id!=='string'||!h.ctrl_id||scopes.has(h.ctrl_id)||!Array.isArray(h.agents)||!Array.isArray(h.units)||!Array.isArray(h.agent_edges)||h.agents.length>256||h.agent_edges.length>512)fail();scopes.add(h.ctrl_id);
  const ids=new Set(),parents=new Map();
  for(const a of h.agents){if(typeof a?.id!=='string'||!a.id||ids.has(a.id)||a.project_id!==projectId||a.ctrl_id!==h.ctrl_id||!['CTRL','LEAD','DOER'].includes(a.structural_role))fail();ids.add(a.id);}
  if(!h.agents.some(a=>a.id===h.ctrl_id&&a.structural_role==='CTRL'&&a.parent_relation?.state==='ROOT'))fail();
  const edgeIds=new Set();for(const e of h.agent_edges){if(typeof e?.id!=='string'||!e.id||edgeIds.has(e.id)||!ids.has(e.source)||!ids.has(e.target)||e.target===h.ctrl_id||parents.has(e.target))fail();edgeIds.add(e.id);parents.set(e.target,e.source);}
  for(const id of ids){const seen=new Set();let at=id;while(at!==h.ctrl_id){if(seen.has(at)||!parents.has(at))fail();seen.add(at);at=parents.get(at);}}
  const units=new Set();for(const u of h.units){const a=h.agents.find(a=>a.id===u?.task_id);if(!a||units.has(u.task_id)||u.project_id!==projectId||u.ctrl_id!==h.ctrl_id||!['LAB','FACTORY'].includes(u.work_unit?.kind)||!a.manifest_identity?.manifest_digest||a.manifest_identity.manifest_digest!==u.manifest_identity?.manifest_digest||JSON.stringify(a.work_unit)!==JSON.stringify(u.work_unit))fail();units.add(u.task_id);}
 }
 return v;
}
export async function nativeRoleDetail(value,id){
 if(value?.ok!==true||value.scope!=='global-definitions'||value.roles?.length!==1||value.roles[0]?.id!==id)throw Error('Selected role could not be confirmed.');
 const role=value.roles[0],cursor=value.cursor,hex=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v),bound=a=>a?.role_id===id&&a.manifest_version===role.active_version&&hex(a.digest);
 if(!cursor||!Number.isSafeInteger(cursor.event_seq)||cursor.event_seq<0||cursor.event_seq>0&&(!cursor.event_id||!hex(cursor.event_digest)))throw Error('Role cursor unavailable.');
 const choices=Array.isArray(role.avatar_choices)&&role.avatar_choices.length<=1?role.avatar_choices.filter(a=>bound(a)&&a.id==='canonical'&&typeof a.label==='string'):[];
 let avatar=role.avatar;
 if(avatar?.url?.startsWith('data:')){
  try{if(!bound(avatar)||avatar.state!=='AVAILABLE'||avatar.digest!==role.avatar_asset_digest||avatar.media_type!=='image/webp'||avatar.width!==256||avatar.height!==256||!hex(avatar.render_digest)||!/^data:image\/webp;base64,[A-Za-z0-9+/]+={0,2}$/.test(avatar.url)||avatar.url.length>43715)throw Error();
   const bytes=Uint8Array.from(atob(avatar.url.slice(23)),c=>c.charCodeAt(0)),digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');if(digest!==avatar.render_digest)throw Error();
  }catch{avatar=null;}
 }
 return {...role,avatar,avatar_choices:choices};
}

export async function mountProjects() {
const app=new App({name:'SWARM HQ',version:'1.0.0'},{availableDisplayModes:['fullscreen']},{autoResize:false});
const $=s=>document.querySelector(s), root=document.documentElement;
const text=(selector,value)=>{$(selector).textContent=value;};
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const label={active:'Active',inactive:'Inactive',recently_active:'Recently active',unknown:'Unknown'};
const number=value=>value===null?'\u2014':value.toLocaleString();
text('#attention-copy','\u2014');$('#attention-copy').setAttribute('aria-label','Attention is not yet known');$('#project-nav').firstElementChild?.classList.add('loading-announcement');
let roster=null,metrics=null,view='list',generation=0,usageGeneration=0,detailGeneration=0,hours=24,lastUsage=null,dialogOpener=null,selectedProject=null,refreshPending=false;
function theme(ctx){
 if(ctx?.theme)applyDocumentTheme(ctx.theme);
 if(['light','dark'].includes(ctx?.theme)){root.style.setProperty('--brand-image-opacity',ctx.theme==='light'?'0':'1');root.style.setProperty('--brand-label-display',ctx.theme==='light'?'flex':'none');}
 if(ctx?.styles?.variables)applyHostStyleVariables(ctx.styles.variables);
 // Host notifications are partial; omitted dimensions/insets retain their last value.
 if(ctx?.containerDimensions)for(const dimension of ['width','height']){const dimensions=ctx.containerDimensions,max='max'+dimension[0].toUpperCase()+dimension.slice(1);if(!(dimension in dimensions||max in dimensions))continue;const value=dimensions[dimension]??dimensions[max];if(Number.isFinite(value)&&value>0)root.style.setProperty('--hq-host-'+dimension,value+'px');else root.style.removeProperty('--hq-host-'+dimension);}
 for(const side of ['top','right','bottom','left']){const inset=ctx?.safeAreaInsets?.[side];if(Number.isFinite(inset)&&inset>=0)root.style.setProperty('--hq-safe-'+side,inset+'px');}
}
app.onhostcontextchanged=theme;
// Reuse the same navigation DOM as a native drawer in narrow host containers.
const navigation=$('#workspace-navigation'),compactHeader=$('#compact-header'),navigationToggle=$('#navigation-toggle'),brandRow=$('.brand-row'),headerActions=$('.header-actions'),desktopHeader=$('#desktop-header'),headerSearch=$('.header-search'),searchToggle=$('#search-toggle'),projectSearch=$('#project-search');
function closeNavigation(){if(navigation.matches(':popover-open'))navigation.hidePopover();}
function fitNavigation(){
 const style=getComputedStyle(document.body),compact=document.body.clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight)<=700;
 if(compact===!compactHeader.hidden&&(compact?brandRow.parentElement===compactHeader:headerActions.parentElement===desktopHeader))return;
 const focused=document.activeElement;
 closeNavigation();compactHeader.hidden=!compact;desktopHeader.hidden=compact;
 if(compact){navigation.setAttribute('popover','auto');brandRow.append(searchToggle,projectSearch);compactHeader.append(brandRow,headerActions);projectSearch.hidden=focused!==projectSearch;$('.wordmark-wrap').hidden=!projectSearch.hidden;searchToggle.setAttribute('aria-expanded',String(!projectSearch.hidden));}
 else{navigation.removeAttribute('popover');navigation.prepend(brandRow);headerSearch.append(searchToggle,projectSearch);desktopHeader.append(headerActions);projectSearch.hidden=false;$('.wordmark-wrap').hidden=false;searchToggle.setAttribute('aria-expanded','true');}

 if(focused&&focused!==document.body&&focused.isConnected){
  if(navigation.contains(focused)&&compact)navigationToggle.focus({preventScroll:true});
  else focused.focus({preventScroll:true});
 }
}
function fitNavigationEdge(){if(!compactHeader.hidden)root.style.setProperty('--navigation-top',compactHeader.getBoundingClientRect().bottom+'px');}
new ResizeObserver(()=>{fitNavigation();fitNavigationEdge();drawUsage();fitFlow();}).observe(document.body);new ResizeObserver(fitNavigationEdge).observe(compactHeader);fitNavigation();fitNavigationEdge();
navigation.addEventListener('beforetoggle',event=>{if(event.newState==='open')fitNavigationEdge();});
navigation.addEventListener('toggle',event=>{navigationToggle.setAttribute('aria-expanded',String(event.newState==='open'));});
navigation.addEventListener('click',event=>{if(event.target.closest('a,button:not(:disabled):not([data-keep-navigation])'))closeNavigation();});
window.addEventListener('hashchange',closeNavigation);
// Acknowledged writers answer REJECTED/CONFLICT as typed structured content; only transport failures throw.
const typedOutcomes=new Set(['swarm_project_tickets','swarm_role_save','swarm_unit_prepare','swarm_unit_create']);
async function call(name,args={}){const result=await app.callServerTool({name,arguments:args},undefined,{timeout:20000});if(result.isError&&!(typedOutcomes.has(name)&&result.structuredContent?.ok===false))throw Error('Unavailable');return result.structuredContent||JSON.parse(result.content.find(c=>c.type==='text').text);}
document.querySelectorAll('.wordmark,.brand-links img,.support-portrait').forEach(image=>{
 const fallback=image.nextElementSibling;const hasFallback=fallback?.hasAttribute('data-brand-fallback');
 if(!hasFallback&&!image.matches('.wordmark,.support-portrait,.brand-light-variant'))return;
 const failed=()=>{image.hidden=true;if(hasFallback)fallback.hidden=false;};
 image.addEventListener('error',failed);image.addEventListener('load',()=>{image.hidden=false;if(hasFallback)fallback.hidden=true;});if(image.complete&&!image.naturalWidth)failed();
});
const amount=$('#support-custom'),checkout=$('.support-checkout');
function supportAmount(){text('#support-link-status','');const choice=document.querySelector('[name="support-amount"]:checked').value;amount.hidden=choice!=='custom';const url=supportCheckoutURL(choice==='custom'?amount.value:choice);amount.setCustomValidity(choice==='custom'&&!url?'Enter $1 to $10,000 with up to two decimal places.':'');checkout.dataset.preparedUrl=url||'';checkout.setAttribute('aria-disabled',String(!url));checkout.title=url?'Open support checkout':'Choose a valid support amount';checkout.href=url||'https://flowwweb.com/1M#support';}
document.querySelector('.support-amounts').addEventListener('change',supportAmount);amount.addEventListener('input',supportAmount);supportAmount();
const externalLinks=new Set(['https://github.com/flowwweb/swarm','https://x.com/PeikGabriel','https://github.com/peikgabriel','https://flowwweb.com','https://flowwweb.com/1M','https://flowwweb.com/1M#support']);
document.addEventListener('click',async event=>{
 const link=event.target.closest('a[data-external]');if(!link)return;
 event.preventDefault();if(link.getAttribute('aria-busy')==='true')return;const url=link===checkout?checkout.dataset.preparedUrl:link.getAttribute('href');if(link===checkout&&!validSupportCheckoutURL(url)){if(!amount.hidden)amount.reportValidity();text('#support-link-status','Choose an amount from $1 to $10,000.');return;}if(!externalLinks.has(url)&&!validSupportCheckoutURL(url))return;link.setAttribute('aria-busy','true');
 try{const result=await app.openLink({url});if(result?.isError)throw Error('Unavailable');text('#support-link-status','');}
 catch{text('#support-link-status','Could not open this link. Try again.');}finally{link.removeAttribute('aria-busy');}
});
const tasksNav=document.createElement('a');tasksNav.className='nav-home';tasksNav.href='#tasks';tasksNav.id='all-tasks';tasksNav.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6h12M9 12h12M9 18h12M3 6h1M3 12h1M3 18h1"/></svg>Tickets';$('#all-projects').after(tasksNav);
const primaryNav=document.createElement('nav');primaryNav.className='primary-nav';primaryNav.setAttribute('aria-label','Main navigation');$('#all-projects').before(primaryNav);primaryNav.append($('#all-projects'),tasksNav,$('.library-nav'));
// Flows and Loops are primary sections beside Units and Roles; the catalog pages never write Flow preferences.
for(const [hash,label,path] of [['hives','Hives','M12 3l8 5v8l-8 5-8-5V8Z'],['flows','Flows','M4 6h10a4 4 0 0 1 0 8H8a4 4 0 0 0 0 8h12M16 3l4 3-4 3'],['loops','Loops','M20 12a8 8 0 1 1-2.3-5.6M20 4v5h-5']]){const link=document.createElement('a');link.className='nav-home';link.href='#'+hash;link.innerHTML=`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>${label}`;$('.library-nav').append(link);}
$('.library-nav').prepend(document.querySelector('.library-nav a[href="#hives"]'));
const feedback=document.createElement('div');feedback.className='feedback-toast';feedback.hidden=true;feedback.innerHTML='<span role="status"></span><button aria-label="Dismiss notification">×</button>';document.body.append(feedback);feedback.querySelector('button').onclick=()=>{feedback.hidden=true;};
function notify(message){const content=feedback.querySelector('[role=status]');if(content.textContent===message)return;content.textContent=message;feedback.hidden=false;}
function projectHref(id,tab='overview'){return '#project='+encodeURIComponent(id)+(tab==='tasks'?'&tab=tasks':'');}
function projectRoute(){const params=new URLSearchParams(location.hash.slice(1));return {id:params.getAll('project').length===1?params.get('project'):null,tab:params.get('tab')==='tasks'?'tasks':'overview'};}
function busy(button,on){button.disabled=on;button.setAttribute('aria-busy',String(on));}
function skeleton(kind='rows'){
 if(kind==='detail')return '<div class="loading-shell loading-detail" aria-hidden="true">'+Array.from({length:4},()=>'<span class="skeleton-line"></span>').join('')+'</div>';
 return `<div class="table-scroll loading-shell" aria-hidden="true"><table class="${kind==='tickets'?'ticket-table':''}"><tbody>${Array.from({length:3},()=>'<tr>'+Array.from({length:kind==='tickets'?5:6},()=>'<td><span class="skeleton-line"></span></td>').join('')+'</tr>').join('')}</tbody></table></div>`;
}
function loading(element,on,initial=false,kind='rows'){
 element.setAttribute('aria-busy',String(on));element.classList.toggle('is-initial-loading',on&&initial);element.classList.toggle('is-refreshing',on&&!initial);
 if(on&&initial&&kind!=='chart')element.innerHTML=skeleton(kind);
}
function icon(p){return `<span class="project-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M3 7V5h7l2 2h9v13H3Z"/></svg></span>`;}
function status(p){return `<span class="status ${p.status}"><span class="status-dot" aria-hidden="true"></span>${label[p.status]}</span>`;}
function openButton(p){return `<button data-project="${escape(p.id)}" aria-label="Open ${escape(p.name)}">Open <span aria-hidden="true">\u2192</span></button>`;}
function projectRows(rows){
 if(!rows.length)return '<p class="empty">No available active projects.</p>';
 if(view==='list')return `<div class="table-scroll"><table class="project-table"><thead><tr><th scope="col">Project</th><th scope="col">Activity</th><th scope="col">Next milestone</th><th scope="col">Next action</th><th scope="col">Updated</th><th scope="col"><span class="quiet">Details</span></th></tr></thead><tbody>${rows.map(p=>`<tr><td class="project-name"><a href="${projectHref(p.id)}" data-project="${escape(p.id)}">${icon(p)}${escape(p.name)}</a></td><td>${status(p)}</td><td class="cell-unknown" aria-label="Milestone unavailable" title="Milestone unavailable">\u2014</td><td class="cell-unknown" aria-label="Next action unavailable" title="Next action unavailable">\u2014</td><td class="updated" aria-label="Update time unavailable" title="Open project details for its last task update">\u2014</td><td>${openButton(p)}</td></tr>`).join('')}</tbody></table></div>`;
 if(view==='constellation')return `<div class="constellation"><p class="view-note">Registered projects. No project relationships are supplied.</p>${rows.map(p=>`<button data-project="${escape(p.id)}" aria-label="Open ${escape(p.name)}">${icon(p)}<span>${escape(p.name)}</span>${status(p)}</button>`).join('')}</div>`;
 if(view==='flow')return `<div class="flow"><p class="view-note">Grouped by observed activity, not task sequence or dependency.</p>${Object.keys(label).map(s=>`<section><h3>${label[s]}</h3>${rows.filter(p=>p.status===s).map(p=>`<button data-project="${escape(p.id)}">${escape(p.name)}</button>`).join('')||'<p class="quiet small">No projects in this group.</p>'}</section>`).join('')}</div>`;
}
function otherProjects(rows,content,open){return rows.length?`<details class="other-projects" data-other-projects${open?' open':''}><summary aria-expanded="${String(open)}">Other projects (${rows.length})</summary>${content}</details>`:'';}
function render(){
 const query=$('#project-search').value.trim().toLocaleLowerCase(),selected=projectRoute().id,all=(roster?.projects||[]).filter(p=>!query||p.id===selected||p.name.toLocaleLowerCase().includes(query));
 const primary=p=>p.root_binding?.availability==='AVAILABLE'&&p.status==='active',rows=all.filter(primary),other=all.filter(p=>!primary(p));
 const navQuery=$('#sidebar-project-search').value.trim().toLocaleLowerCase(),navAll=(roster?.projects||[]).filter(p=>!navQuery||p.id===selected||p.name.toLocaleLowerCase().includes(navQuery)),navRows=navAll.filter(primary),navOther=navAll.filter(p=>!primary(p));
 const nav=$('#project-nav'),content=$('#project-content'),selectedOther=other.some(p=>p.id===selected),navOpen=!!nav.querySelector('[data-other-projects]')?.open||navOther.some(p=>p.id===selected),contentOpen=!!content.querySelector('[data-other-projects]')?.open||selectedOther;
 const links=items=>items.map(p=>`<a class="project-link ${p.status}" href="${projectHref(p.id)}" data-project="${escape(p.id)}"${p.id===selected?' aria-current="page"':''}>${icon(p)}<span class="name">${escape(p.name)}</span><span class="status-dot" aria-label="${label[p.status]}"></span></a>`).join('');
 nav.innerHTML=roster?`<div data-project-group="active">${links(navRows)||'<p class="quiet">No active projects.</p>'}</div>${otherProjects(navOther,links(navOther),navOpen)}`:'<span class="loading-announcement">Project inventory unavailable.</span>';
 $('#clear-filter').hidden=!query;document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===view)));
 content.innerHTML=roster?`<section data-project-group="active" aria-label="Active projects">${projectRows(rows)}</section>${otherProjects(other,projectRows(other),contentOpen)}`:'<p class="empty">Projects unavailable.</p>';
}
for(const surface of [$('#project-nav'),$('#project-content')])surface.addEventListener('toggle',e=>{if(e.target.matches('[data-other-projects]'))e.target.querySelector('summary').setAttribute('aria-expanded',String(e.target.open));},true);
function showDialog(title,html,headerPanel=false){$('#inspector').classList.toggle('header-panel',headerPanel);if(headerPanel)$('#inspector').style.setProperty('--header-panel-top',(compactHeader.hidden?desktopHeader:compactHeader).getBoundingClientRect().bottom+'px');detailGeneration++;dialogOpener=document.activeElement;text('#inspector-title',title);$('#inspector-body').innerHTML=html;if(!$('#inspector').open)$('#inspector').showModal();$('#close-inspector').focus();}
// Identity and notification items are not exposed by the current host contract.
$('#notifications-toggle').onclick=()=>showDialog('Notifications','<p role="status">Notifications are unavailable in this view.</p>',true);
$('#profile-toggle').onclick=()=>showDialog('Profile','<p role="status">Profile information is unavailable in this view.</p>',true);
$('#sidebar-create-project').onclick=()=>showDialog('Create project','<p role="status">Project creation is unavailable in this view.</p>');
$('#close-inspector').onclick=()=>$('#inspector').close();
$('#inspector').addEventListener('close',()=>{detailGeneration++;if(dialogOpener?.isConnected){if(!compactHeader.hidden&&navigation.contains(dialogOpener)&&!navigation.matches(':popover-open'))navigation.showPopover();dialogOpener.focus();}});
const projectPage=document.createElement('main');projectPage.id='project-page';projectPage.hidden=true;$('.hq-footer').before(projectPage);
function projectShell(p,body){const restoreFocus=projectPage.contains(document.activeElement);projectPage.innerHTML=`<header class="page-header"><div><nav class="breadcrumbs" aria-label="Breadcrumb"><a href="#projects" class="project-back">Projects</a><span aria-hidden="true">&rsaquo;</span><span aria-current="page">${escape(p.name)}</span></nav><h1 tabindex="-1">${escape(p.name)}</h1></div></header>${p.id?`<nav class="project-tabs" aria-label="Project views">${['overview','tasks'].map(tab=>`<a href="${projectHref(p.id,tab)}"${projectRoute().tab===tab?' aria-current="page"':''}>${tab==='tasks'?'Tickets':'Overview'}</a>`).join('')}</nav>`:''}${body}`;if(restoreFocus)projectPage.querySelector('h1').focus();}
const projectUsageRequests=latestRequest();
function projectRecoveryMarkup(loading=false){if(loading)return `<section class="project-section project-recovery" aria-busy="true"><div class="project-recovery-content">${skeleton('detail')}<button class="icon-action" disabled aria-label="Loading project details" title="Loading project details" aria-busy="true"><span class="busy-spinner" aria-hidden="true"></span></button></div></section>`;return `<section class="project-section project-recovery" aria-busy="${loading}"><div class="project-recovery-content"><svg class="project-recovery-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3l18 18M5 6a6 6 0 0 0-1 11h11M9 4a6 6 0 0 1 9 5h1a4 4 0 0 1 2 7"/></svg><h2 role="status">${loading?'Loading project details':'Project details unavailable'}</h2><button class="icon-action" ${loading?'disabled aria-label="Loading project details"':'data-project-retry aria-label="Retry project details"'} title="${loading?'Loading project details':'Retry project details'}" aria-busy="${loading}"><svg class="idle-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 7v5h-5M20 12a8 8 0 1 0-2 5"/></svg><span class="busy-spinner" aria-hidden="true"></span></button></div></section>`;}
const projectUsagePeriod=value=>value===24?'Last 24 hours':value===168?'Last 7 days':'Last 30 days';
async function loadProjectUsage(id,value){
 const section=projectPage.querySelector('#project-usage');if(!section||projectPage.hidden||selectedProject!==id)return;
 const token=projectUsageRequests.next(),detail=detailGeneration,field=name=>section.querySelector(`[data-project-usage="${name}"]`);
 const current=()=>projectUsageRequests.isLatest(token)&&detail===detailGeneration&&selectedProject===id&&section.isConnected&&!projectPage.hidden;
 section.querySelectorAll('[data-project-hours]').forEach(b=>b.setAttribute('aria-pressed',String(+b.dataset.projectHours===value)));
 const retained=section.dataset.loadedPeriod===String(value);loading(section,true,!retained,'chart');field('period').textContent=projectUsagePeriod(value);if(!retained){field('total').textContent='\u2014';field('window').textContent='';field('status').textContent='Loading local observations\u2026';}
 const result=await readProjectUsage(call,id,value,current);
 if(result.state==='stale'||!current())return;
 loading(section,false);if(result.state!=='ready'){field('status').textContent='Usage unavailable.';return;}
 const data=result.view;section.dataset.loadedPeriod=String(value);field('total').textContent=number(data.total);
 field('window').textContent=`Observed window: ${new Date(data.window.after_ms).toLocaleString()} to ${new Date(data.window.before_ms).toLocaleString()}.`;
 field('status').textContent=data.total===null?'No observations in this period.':`${data.status==='partial'?'Partial coverage':'Observed coverage'} \u00b7 gaps are not zero.${data.omitted?` Chart omits ${data.omitted.observations.toLocaleString()} earlier observations (${data.omitted.tokens.toLocaleString()} tokens); total includes them.`:''}`;
}
projectPage.addEventListener('click',e=>{if(e.target.closest('[data-project-retry]')&&selectedProject){void openProject(selectedProject);return;}const button=e.target.closest('[data-project-hours]');if(button&&selectedProject)loadProjectUsage(selectedProject,+button.dataset.projectHours);});
async function openProject(id){
 const p=roster?.projects.find(p=>p.id===id);if(!p)return;const tab=projectRoute().tab;
 selectedProject=id;render();const request=++detailGeneration;$('#main').hidden=true;settingsPage.hidden=true;projectPage.hidden=false;
 $('#settings').classList.remove('selected');$('#settings').removeAttribute('aria-current');$('#all-projects').classList.remove('selected');
 projectShell(p,projectRecoveryMarkup(true));projectPage.querySelector('h1').focus();
 try{const data=projectDetail(await call('swarm_status',{project_id:id}),id);if(request!==detailGeneration||selectedProject!==id)return;
 projectShell(p,tab==='tasks'?`<section class="project-section"><h2>Execution</h2>${data.taskRows.length?`<ul>${data.taskRows.map(t=>`<li><strong>${escape(t.name)}</strong><span>${escape(t.status)}</span></li>`).join('')}</ul>`:`<p>${data.tasksAvailable?'No retained tasks.':'Task details unavailable.'}</p>`}${data.tasksTruncated?'<p>More tasks unavailable.</p>':''}</section>`:`<section class="project-section"><h2>Overview</h2><dl><dt>Activity</dt><dd>${status(p)}</dd><dt>Current milestone</dt><dd>${escape(data.milestone||'Current milestone unavailable')}</dd><dt>Measured progress</dt><dd>${data.progress===null?'Unknown':escape(String(data.progress))}</dd><dt>Last task update</dt><dd>${data.updated?escape(new Date(data.updated).toLocaleString()):'Unknown'}</dd></dl></section><section class="project-section" id="project-usage" aria-labelledby="project-usage-title"><div class="section-heading"><h2 id="project-usage-title">Usage</h2><div class="period-switch" role="group" aria-label="Project usage period"><button data-project-hours="24" aria-pressed="true">24h</button><button data-project-hours="168" aria-pressed="false">7d</button><button data-project-hours="720" aria-pressed="false">30d</button></div></div><p><strong data-project-usage="total">\u2014</strong> <span class="quiet small" data-project-usage="period">Last 24 hours</span></p><p class="quiet small" data-project-usage="window"></p><p role="status" data-project-usage="status">Loading local observations\u2026</p><p class="quiet small">Locally observed token deltas for this project. Not billing; gaps are not zero.</p></section><details><summary>Diagnostics</summary><code>${escape(id)}</code><p><code>${escape(JSON.stringify(data.cursor||'Cursor unavailable'))}</code></p></details>`);if(tab==='tasks'){const planning=document.createElement('section');planning.className='project-section';projectPage.append(planning);void openTasks(id,true,planning);}else void loadProjectUsage(id,24);
 }catch{if(request===detailGeneration&&selectedProject===id)projectShell(p,projectRecoveryMarkup());}
}
// One scoped editor; drafts stay in the mounted form, never in a second store.
function fitFlow(){
 const viewport=projectPage.querySelector('[data-flow-viewport]'),canvas=viewport?.querySelector('[data-flow-map]'),space=canvas?.querySelector('.flow-space'),stage=canvas?.querySelector('.flow-stage');if(!stage)return;
 if(canvas.dataset.vertical!==String(compact()||canvas.dataset.direction==='vertical')){viewport.dispatchEvent(new Event('flowlayout'));return;}
 const w=Number(canvas.dataset.width),h=Number(canvas.dataset.height),scale=viewport.dataset.zoom==='fit'?Math.min(1,Math.max(.5,(viewport.clientWidth-24)/w),Math.max(.5,(viewport.clientHeight-84)/h)):Number(viewport.dataset.zoom);viewport.dataset.scale=String(scale);
 space.style.width=w*scale+'px';space.style.height=h*scale+'px';space.style.marginBlockStart=Math.max(0,(viewport.clientHeight-84-h*scale)/2)+'px';stage.style.transform=`scale(${scale})`;stage.style.setProperty('--flow-scale',String(scale));
}
function libraryEditor(library,lens){
 const epoch=detailGeneration,active=()=>epoch===detailGeneration&&!projectPage.hidden;
 let snapshot=null,uncertain=null,pending=false;
 const disabledControls=new Map();
 function syncPending(){
  if(pending){for(const c of projectPage.querySelectorAll('input,select,textarea,button')){if(!disabledControls.has(c))disabledControls.set(c,c.disabled);c.disabled=true;}}
  else{for(const [c,disabled] of disabledControls){if(c.isConnected)c.disabled=disabled;}disabledControls.clear();}
 }
 // Primary Flows/Loops sections offer every subject kind; Units/Roles-scoped links keep their own kinds.
 const kinds=library==='roles'?['ROLE']:library==='units'?['LAB','FACTORY']:['ROLE','LAB','FACTORY'],title=library==='roles'?'Roles':library==='units'?'Units':lens==='loops'?'Loops':'Flows';
 projectShell({name:title},`<div class="flow-context"><label>Project <select data-library-project>${(roster?.projects||[]).map(p=>`<option value="${escape(p.id)}">${escape(p.name)}</option>`).join('')}</select></label>${kinds.length>1?`<label>Assign to <select data-library-kind>${kinds.map(k=>`<option value="${k}">${k==='ROLE'?'Roles':k==='LAB'?'Labs':'Factories'}</option>`).join('')}</select></label>`:''}<button data-library-load>Load</button></div><p role="status" data-library-status></p><div data-library-body></div>`);
 const q=sel=>projectPage.querySelector(sel),body=q('[data-library-body]'),status=q('[data-library-status]'),picker=q('[data-library-project]');
 const kind=()=>kinds.length===1?kinds[0]:q('[data-library-kind]').value;
 let serial=0;
 const valid=(v,id,k)=>v?.ok===true&&v.project_id===id&&typeof v.source_digest==='string'&&Array.isArray(v.definitions)&&Array.isArray(v.assignments)&&(!k||v.kind===k);
 async function read(id,k){const v=await call('swarm_library_read',{project_id:id,kind:k});if(!valid(v,id,k))throw Error('Library could not be confirmed.');return v;}
 function form(v,savedDefinition=null){
  const rows=kind()==='ROLE'?v.inventory?.roles:v.inventory?.instances;
  if(!Array.isArray(rows))throw Error('Inventory unavailable.');
  const subjects=rows.filter(r=>kind()==='ROLE'?typeof r.id==='string'&&r.active_version:r.project_id===picker.value&&r.subject_version&&r.ctrl_id);
  const subjectKey=r=>JSON.stringify([v.project_id,kind(),r.id||r.task_id,kind()==='ROLE'?r.active_version:r.subject_version,kind()==='ROLE'?null:r.ctrl_id]);
  const flowKey=f=>JSON.stringify([v.project_id,f.id,f.version,f.digest]);
  const previousNode=body.querySelector('[data-flow-map]')?.dataset.selected;
  body.className='flow-library';
  body.innerHTML=`<form data-flow><header class="flow-toolbar"><label>Flow <select name="existing"><option value="">New Flow</option>${v.definitions.map(f=>`<option value="${escape(flowKey(f))}">${escape(f.id)} \u00b7 v${f.version}</option>`).join('')}</select></label><label class="flow-outcome">Outcome<input name="flow_objective" maxlength="2048"></label><button type="submit" class="cta">Save Flow</button>${lens==='loops'?'<button type="button" data-flow-repeat>Repeat preference</button>':''}</header><div class="flow-workspace"><section class="flow-main"><div class="flow-canvas"><div class="flow-map-controls" role="group" aria-label="Flow map controls"><button type="button" data-flow-zoom="out" aria-label="Zoom out">\u2212</button><button type="button" data-flow-zoom="fit" aria-label="Fit Flow">Fit</button><button type="button" data-flow-zoom="in" aria-label="Zoom in">+</button></div><div class="flow-viewport" data-flow-viewport tabindex="0" aria-label="Flow dependency map"><div data-flow-map></div></div></div><p class="quiet small" data-flow-map-status role="status"></p></section><section class="flow-node-editor" aria-label="Selected step"><h2>Selected step</h2><div data-flow-node-fields><p class="quiet">Select a step to edit its instructions.</p></div></section></div><details class="flow-source"><summary>Definition details</summary><label>Definition <textarea name="definition" rows="12" required></textarea></label></details></form><section class="flow-assignment"><h2>${lens==='loops'?'Repeat preference':'Assign Flow'}</h2>${lens==='loops'?'<p class="quiet small">Saved preference. Automatic runs are not available.</p>':''}<form data-assignment><label>${kind()==='ROLE'?'Role':'Instance'} <select name="subject" required>${subjects.map(r=>`<option value="${escape(subjectKey(r))}">${escape(r.name||r.task_id)}</option>`).join('')}</select></label><label>Flow <select name="flow" required>${v.definitions.map(r=>`<option value="${escape(flowKey(r))}">${escape(r.id)} \u00b7 v${r.version}</option>`).join('')}</select></label><label>Label <input name="label" maxlength="160"></label><label>Notes <textarea name="notes" maxlength="2048"></textarea></label><label>Planned repeats <input name="repeat" type="number" min="1" max="9007199254740991" step="1" value="1" required></label><button ${!subjects.length||!v.definitions.length?'disabled':''}>Save assignment</button></form></section>`;
  const assignment=q('[data-assignment]'),flow=q('[data-flow]');
  const selectSubject=()=>{if(assignment.dataset.keepDraft)return;const r=subjects.find(r=>subjectKey(r)===assignment.elements.subject.value);if(!r)return;const previous=v.assignments.filter(a=>a.subject_kind===kind()&&a.subject_id===(r.id||r.task_id)&&a.ctrl_id===(kind()==='ROLE'?null:r.ctrl_id)).sort((a,b)=>b.version-a.version)[0];assignment.elements.label.value=previous?.label||'';assignment.elements.notes.value=previous?.notes||'';assignment.elements.repeat.value=previous?.repeat_count||1;const index=v.definitions.findIndex(f=>f.id===previous?.flow_id&&f.version===previous?.flow_version&&f.digest===previous?.flow_digest);if(index>=0)assignment.elements.flow.value=flowKey(v.definitions[index]);};
  body.onchange=e=>{if(e.target.tagName==='SELECT')e.target.setCustomValidity('');};
  assignment.elements.subject.onchange=selectSubject;selectSubject();
  flow.elements.definition.value=JSON.stringify(v.starter,null,2);flow.elements.existing.onchange=()=>{if(flow.dataset.keepDraft)return;const f=v.definitions.find(f=>flowKey(f)===flow.elements.existing.value);flow.elements.definition.value=JSON.stringify(flow.elements.existing.value===''?v.starter:{id:f.id,version:Math.max(...v.definitions.filter(d=>d.id===f.id).map(d=>d.version))+1,objective:f.objective,nodes:f.nodes},null,2);paintFlow();};
  const canvas=q('[data-flow-map]'),viewport=q('[data-flow-viewport]'),nodeFields=q('[data-flow-node-fields]');
  canvas.dataset.direction=lens==='loops'?'vertical':'responsive';
  canvas.dataset.selected=previousNode||'';
  q('[data-flow-repeat]')?.addEventListener('click',()=>assignment.elements.repeat.focus());
  const draft=()=>JSON.parse(flow.elements.definition.value),store=d=>{flow.elements.definition.value=JSON.stringify(d,null,2);};
  function selectNode(id){const d=draft(),n=d.nodes.find(n=>n.id===id);if(!n)return;canvas.dataset.selected=id;
   canvas.querySelectorAll('[data-flow-node]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.flowNode===id)));
   nodeFields.innerHTML=`<label>Instructions<textarea name="node_objective" maxlength="2048" rows="3">${escape(n.objective)}</textarea></label><label>Owner<input name="node_owner_id" value="${escape(n.owner_id||'')}" maxlength="128"></label><label>Completion<textarea name="node_completion" maxlength="2048" rows="4">${escape(n.completion||'')}</textarea></label><p class="quiet small">Changes stay in this draft until you save.</p>`;
   syncPending();
   nodeFields.oninput=e=>{if(pending)return;const key=e.target.name?.replace(/^node_/,'');if(!['objective','owner_id','completion'].includes(key))return;const next=draft(),node=next.nodes.find(n=>n.id===canvas.dataset.selected);if(!node)return;node[key]=e.target.value;store(next);const button=[...canvas.querySelectorAll('[data-flow-node]')].find(b=>b.dataset.flowNode===node.id);if(button&&key==='objective')button.querySelector('span').textContent=node.objective;};
  }
  function paintFlow(){const focused=document.activeElement,focusNode=canvas.contains(focused)?focused.dataset.flowNode:null,focusField=nodeFields.contains(focused)?focused.name:null;let d,layout;try{d=draft();layout=flowLayout(d,compact()||lens==='loops');}catch{}
   canvas.replaceChildren();flow.querySelector('button[type=submit]').disabled=!layout;q('[data-flow-map-status]').textContent=layout?'':'This definition has no valid dependency map. Review Definition details.';
   if(!layout){nodeFields.innerHTML='<p class="quiet">No valid step is selected.</p>';syncPending();return;}
   flow.elements.flow_objective.value=d.objective||'';canvas.dataset.width=layout.width;canvas.dataset.height=layout.height;canvas.dataset.vertical=String(layout.vertical);
   canvas.innerHTML=`<div class="flow-space"><div class="flow-stage" style="width:${layout.width}px;height:${layout.height}px"><svg viewBox="0 0 ${layout.width} ${layout.height}" aria-hidden="true">${layout.edges.map(e=>`<path data-flow-edge="${escape(JSON.stringify([e.source,e.target]))}" d="${e.path}"/>`).join('')}</svg><div role="group" aria-label="Flow steps">${layout.nodes.map(n=>`<button type="button" data-flow-node="${escape(n.id)}" aria-pressed="false" style="left:${n.x}px;top:${n.y}px;width:${n.width}px;height:${n.height}px">${layout.edges.some(e=>e.target===n.id)?'<i class="flow-port input" aria-hidden="true"></i>':''}<span>${escape(n.label)}</span>${layout.edges.some(e=>e.source===n.id)?'<i class="flow-port output" aria-hidden="true"></i>':''}</button>`).join('')}</div></div></div>`;
   viewport.dataset.zoom='fit';fitFlow();selectNode(layout.nodes.some(n=>n.id===canvas.dataset.selected)?canvas.dataset.selected:layout.nodes[0].id);
   if(!pending){const target=focusField?flow.elements.namedItem(focusField):[...canvas.querySelectorAll('[data-flow-node]')].find(n=>n.dataset.flowNode===focusNode);target?.focus({preventScroll:true});}
  }
  canvas.onclick=e=>{const n=e.target.closest('[data-flow-node]');if(n)selectNode(n.dataset.flowNode);};
  canvas.onkeydown=e=>{const nodes=[...canvas.querySelectorAll('[data-flow-node]')],i=nodes.indexOf(e.target);if(i<0)return;let next;if(e.key==='Home')next=0;else if(e.key==='End')next=nodes.length-1;else if(['ArrowRight','ArrowDown'].includes(e.key))next=Math.min(i+1,nodes.length-1);else if(['ArrowLeft','ArrowUp'].includes(e.key))next=Math.max(i-1,0);else return;e.preventDefault();nodes[next].focus();selectNode(nodes[next].dataset.flowNode);};
  viewport.addEventListener('flowlayout',paintFlow);
  flow.elements.definition.oninput=paintFlow;flow.elements.flow_objective.oninput=e=>{try{const d=draft();d.objective=e.target.value;store(d);}catch{}};
  flow.querySelectorAll('[data-flow-zoom]').forEach(b=>b.onclick=()=>{viewport.dataset.zoom=b.dataset.flowZoom==='fit'?'fit':String(Math.max(.5,Math.min(2,Number(viewport.dataset.scale||1)+(b.dataset.flowZoom==='in'?.15:-.15))));fitFlow();});
  if(savedDefinition){flow.elements.existing.value=flowKey(savedDefinition);flow.elements.existing.onchange();}else paintFlow();
  assignment.onsubmit=e=>{e.preventDefault();const r=subjects.find(r=>subjectKey(r)===assignment.elements.subject.value),f=v.definitions.find(f=>flowKey(f)===assignment.elements.flow.value),repeat=Number(assignment.elements.repeat.value);if(!r||!f||!Number.isSafeInteger(repeat)||repeat<1)return;const ctrl=kind()==='ROLE'?null:r.ctrl_id,versions=v.assignments.filter(a=>a.subject_kind===kind()&&a.subject_id===(r.id||r.task_id)&&a.ctrl_id===ctrl).map(a=>a.version);save('swarm_flow_assign',{assignment:{version:Math.max(0,...versions)+1,subject_kind:kind(),subject_id:r.id||r.task_id,subject_version:kind()==='ROLE'?r.active_version:r.subject_version,ctrl_id:ctrl,flow_id:f.id,flow_version:f.version,flow_digest:f.digest,label:assignment.elements.label.value,notes:assignment.elements.notes.value,repeat_count:repeat}});};
  flow.onsubmit=e=>{e.preventDefault();if(!flow.checkValidity())return;try{save('swarm_flow_save',{definition:JSON.parse(flow.elements.definition.value)});}catch{status.textContent='Enter valid JSON. Your draft is preserved.';}};
 }
 async function load(){if(pending)return;const id=picker.value,k=kind(),token=++serial;if(!id){status.textContent='Choose a saved project.';return;}loading(body,true,!snapshot,'detail');busy(q('[data-library-load]'),true);status.textContent='Loading\u2026';try{const v=await read(id,k);if(!active()||token!==serial)return;snapshot=v;form(v);status.textContent='';}catch(e){if(active()&&token===serial){if(!snapshot)body.replaceChildren();status.textContent=e.message;}}finally{if(active()&&token===serial){loading(body,false);busy(q('[data-library-load]'),false);}}}
 const sameRecord=(r,d)=>Object.keys(d).every(k=>JSON.stringify(r[k])===JSON.stringify(d[k]));
 async function save(tool,part){
  if(pending||uncertain||!snapshot)return;
  const id=picker.value,k=kind(),token=serial,request={project_id:id,expected_digest:snapshot.source_digest,...part,acknowledge:true};pending=true;status.textContent='Saving\u2026';syncPending();
  try{const result=await call(tool,request);if(!valid(result,id))throw Error('Save was not confirmed.');const key=part.assignment?'assignments':'definitions',draft=part.assignment||part.definition,record=result[key].find(r=>sameRecord(r,draft));if(!record?.digest)throw Error('Save receipt did not match.');const fresh=await read(id,k);if(!active()||token!==serial)return;if(fresh.source_digest!==result.source_digest||!fresh[key].some(r=>r.digest===record.digest&&sameRecord(r,draft)))throw Error('Readback changed.');snapshot=fresh;form(fresh,part.definition?record:null);status.textContent='Saved';}
  catch{if(active()&&token===serial){uncertain={tool,part,id,k};status.textContent='Save not confirmed. Draft preserved. Reload to reconcile.';}}
  finally{pending=false;syncPending();if(active()&&token===serial&&!uncertain)q(part.assignment?'[data-assignment] button':'[data-flow] button')?.focus();}
 }
 q('[data-library-load]').onclick=async()=>{if(!uncertain){load();return;}const u=uncertain,token=serial;status.textContent='Checking saved data\u2026';try{const fresh=await read(u.id,u.k);if(!active()||token!==serial||picker.value!==u.id||kind()!==u.k)return;const key=u.part.assignment?'assignments':'definitions',draft=u.part.assignment||u.part.definition;if(fresh[key].some(r=>r.digest&&sameRecord(r,draft))){uncertain=null;snapshot=fresh;form(fresh,u.part.definition?fresh.definitions.find(r=>r.digest&&sameRecord(r,draft)):null);q(u.part.assignment?'[data-assignment] button':'[data-flow] button')?.focus();status.textContent='Saved';}else{const draftValues=[...body.querySelectorAll('input,textarea,select')].map(c=>[c.name,c.value]);uncertain=null;snapshot=fresh;form(fresh);let changed=false;for(const [name,value] of draftValues){const control=[...body.querySelectorAll('input,textarea,select')].find(c=>c.name===name);if(!control)continue;if(control.tagName==='SELECT'&&![...control.options].some(o=>o.value===value)){const option=new Option('Previous selection unavailable. Choose again.',value,true,true);option.disabled=true;control.add(option);control.setCustomValidity('Choose a current selection.');if(name==='subject'||name==='existing')control.form.dataset.keepDraft='true';changed=true;}control.value=value;}q('[data-flow] [name=definition]')?.dispatchEvent(new Event('input'));status.textContent=changed?'A selected object changed or is unavailable. Choose a current selection; your draft is preserved.':'Source reloaded. Review your preserved draft before saving again.';}}catch{if(active())status.textContent='Could not reconcile. Draft preserved.';}};
 picker.onchange=()=>{uncertain=null;snapshot=null;body.replaceChildren();load();};if(q('[data-library-kind]'))q('[data-library-kind]').onchange=picker.onchange;load();
}
// Units and Roles catalog/editor. Reads use the exact server projections; writes go through the acknowledged
// MCP bridges and show "Saved" only after a matching fresh readback. Drafts live in the mounted form only.
const compact=()=>!compactHeader.hidden;
const newIdentity=prefix=>prefix+Array.from(crypto.getRandomValues(new Uint8Array(8)),b=>b.toString(16).padStart(2,'0')).join('');
function mountEditor(title,html,panel,opener){
 // One title per surface: the dialog header owns it in compact hosts; the form's own editor-head owns it in the panel.
 if(compact()){showDialog(title,html);dialogOpener=opener;const dialog=$('#inspector'),form=dialog.querySelector('form'),footer=dialog.querySelector('footer'),before=footer.innerHTML;dialog.classList.add('ticket-dialog');footer.hidden=false;form.querySelector('.editor-head h2')?.remove();const actions=form.querySelector('.editor-actions');footer.replaceChildren(actions);form.id='library-editor-form';actions.querySelector('[type=submit]').setAttribute('form',form.id);
  dialog.addEventListener('close',()=>{footer.innerHTML=before;dialog.classList.remove('ticket-dialog');},{once:true});
  return {form,actions,close:()=>{if(dialog.open)dialog.close();},open:()=>dialog.open&&form.isConnected};}
 panel.hidden=false;panel.innerHTML=(html.includes('class="editor-head"')?'':`<div class="section-heading"><h2>${escape(title)}</h2></div>`)+html;const form=panel.querySelector('form');
 return {form,actions:form.querySelector('.editor-actions'),close:()=>{panel.hidden=true;panel.replaceChildren();if(opener?.isConnected)opener.focus();},open:()=>form.isConnected&&!panel.hidden};
}
const reloadIcon='<svg class="idle-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 7v5h-5M20 12a8 8 0 1 0-2 5"/></svg><span class="busy-spinner" aria-hidden="true"></span>';
// Only the server-projected admitted avatar is ever shown; anything else is a neutral icon with a truthful label.
// Icon-name registry only; role identity and selection come from the admitted manifest.
const roleIconPaths={"palette":"M12 3a9 9 0 1 0 0 18h1a2 2 0 0 0 1-3.7A1.5 1.5 0 0 1 15.5 15H17a4 4 0 0 0 4-4c0-4.4-4-8-9-8ZM7.5 9h.01M10 6h.01M15 6.5h.01M17 10h.01","briefcase-business":"M9 6V4h6v2M3 6h18v14H3ZM3 11a20 20 0 0 0 18 0M12 11v3","compass":"M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm4 5-3 5-5 3 3-5Z","search":"M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14Zm5 12 6 6","chart-no-axes-combined":"M3 20v-4M7 20v-8M11 20v-4M15 20v-8M19 20V8M3 10l5-5 5 3 8-6","badge-info":"M12 3l3 2 4 1 1 4 1 3-3 3-1 4-5 1-4-2-4-2V9l3-4Zm0 7v6M12 7h.01","lightbulb":"M9 18h6M10 21h4M8 15a6 6 0 1 1 8 0v3H8Z","landmark":"M3 10h18M4 10V7l8-4 8 4v3M6 10v9M10 10v9M14 10v9M18 10v9M3 21h18","brush":"m14 6 4-4 4 4-8 8-4-4ZM10 14c-5-2-3 7-8 6 5 3 10 1 10-4","pen-line":"m15 3 6 6-12 12H3v-6Zm-12 18h18","code-xml":"m8 5-6 7 6 7M16 5l6 7-6 7M14 3l-4 18","clapperboard":"M3 8h18v13H3ZM3 8l-1-5 19-2 1 5ZM7 3l4 4M14 2l4 4","flask-conical":"M9 3h6M10 3v6L3 20h18L14 9V3M7 15h10","clipboard-list":"M9 3h6v4H9ZM9 5H5v16h14V5h-4M8 11h1M12 11h4M8 16h1M12 16h4","shield-check":"M12 3 3 7v6c0 5 9 9 9 9s9-4 9-9V7Zm-5 9 3 3 6-6","file-search":"M14 2H4v20h16V8ZM14 2v6h6M10 10a3 3 0 1 0 0 6 3 3 0 0 0 0-6Zm2 5 4 4","scale":"M12 3v18M6 21h12M3 7h18M6 7l-4 8h8ZM18 7l-4 8h8Z","scan-search":"M3 7V3h4M17 3h4v4M21 17v4h-4M7 21H3v-4M11 7a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm3 7 4 4","settings":"M9 3h6l1 4 4 2v6l-4 2-1 4H9l-1-4-4-2V9l4-2ZM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z","megaphone":"M3 9h5l12-5v16L8 15H3ZM8 15l2 6H6l-1-6","headset":"M4 14v-3a8 8 0 0 1 16 0v7l-4 3h-4M4 12H2v6h5v-6ZM20 12h2v6h-5v-6Z","calculator":"M5 3h14v18H5ZM8 6h8v3H8ZM8 13h.01M12 13h.01M16 13h.01M8 17h.01M12 17h.01M16 17h.01","user-search":"M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM2 21v-2a7 7 0 0 1 9-7M17 12a3 3 0 1 0 0 6 3 3 0 0 0 0-6Zm2 5 3 3","graduation-cap":"m2 9 10-6 10 6-10 6ZM6 12v6l6 3 6-3v-6M22 9v8","circle-user-round":"M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM12 6a3 3 0 1 0 0 6 3 3 0 0 0 0-6ZM6 19a6 6 0 0 1 12 0"};
function roleIcon(role){const name=Object.hasOwn(roleIconPaths,role.lucide_icon)?role.lucide_icon:'circle-user-round';return `<span class="role-avatar role-manifest-icon" aria-hidden="true"><svg viewBox="0 0 24 24" data-role-icon="${name}"><path d="${roleIconPaths[name]}"/></svg></span>`;}
function roleAvatar(role,label){const available=role.avatar?.state==='AVAILABLE'&&role.avatar.digest===role.avatar_asset_digest&&typeof role.avatar.url==='string'&&(/^\/assets\/role-avatars\/[a-z0-9_]+\.png$/.test(role.avatar.url)||role.avatar.url.startsWith('data:image/webp;base64,'));return `<span class="role-avatar" data-role-avatar-state="${available?'available':'unavailable'}">${available?`<img src="${escape(role.avatar.url)}" alt="${escape(label)} avatar" width="52" height="52">`:''}<svg class="role-avatar-fallback" viewBox="0 0 24 24" role="img" aria-label="${escape(label)} avatar unavailable"${available?' hidden':''}><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg></span>`;}
const chevron='<svg class="row-chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>';
const unitIcon=kind=>libraryMarkup(kind==='LAB'?'unit-icon-lab':'unit-icon-factory',{});
for(const surface of [projectPage,$('#inspector')])surface.addEventListener('error',e=>{const img=e.target;if(!(img instanceof HTMLImageElement)||!img.closest('.role-avatar'))return;img.hidden=true;const fallback=img.nextElementSibling;if(fallback)fallback.removeAttribute('hidden');img.closest('.role-avatar').dataset.roleAvatarState='unavailable';},true);
// Flows/Loops are project routes, not unit fields. While a draft is dirty the routes stay focusable but are
// marked aria-disabled="true", described by one short note, and never navigate; no confirmation dialog or store.
function guardRoutes(form){let dirty=false;const note=form.querySelector('[data-dirty-note]');if(note&&!note.id)note.id=newIdentity('dirty-note-');
 const apply=()=>{for(const link of form.querySelectorAll('.row-action')){link.setAttribute('aria-disabled',String(dirty));if(note){if(dirty)link.setAttribute('aria-describedby',note.id);else link.removeAttribute('aria-describedby');}}if(note)note.hidden=!dirty;};
 const mark=()=>{if(!dirty){dirty=true;apply();}};form.addEventListener('input',mark);form.addEventListener('change',mark);
 form.addEventListener('click',e=>{const link=e.target.closest('.row-action');if(link?.getAttribute('aria-disabled')==='true'){e.preventDefault();note?.focus();}});apply();}
// Inert canonical HTML; only escaped data and the existing icon primitive fill named slots.
function libraryMarkup(id,slots){return $('#'+id).innerHTML.replace(/__(\w+)__/g,(_,key)=>slots[key]||'');}
function catalogPage(library){
 const route=location.hash;let surface;
 // Dialog opens/closes do not end the catalog lifetime; replacing its mounted page does.
 const active=()=>surface===projectPage.firstElementChild&&!projectPage.hidden&&location.hash===route;
 if(library==='roles')rolesPage(active);else unitsPage(active);
 surface=projectPage.firstElementChild;
}
function rolesPage(active){
 // 04 v2: one compact header row (title, one-line scope, search, Create) above the list and the editor.
 projectShell({name:'Roles'},libraryMarkup('role-page',{reload:reloadIcon}));
 const q=sel=>projectPage.querySelector(sel),body=q('[data-library-body]'),status=q('[data-library-status]'),search=q('[data-role-search]'),create=q('[data-role-create]'),reload=q('[data-library-load]'),panel=q('[data-library-editor]');
 const header=q('.page-header');header.classList.add('library-header');header.firstElementChild.insertAdjacentHTML('beforeend','<p class="quiet">Global roles shared by every project.</p>');header.append(q('.library-toolbar'));
 let snapshot=null,serial=0,selected=null,editor=null;
 const digest=v=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
 const valid=v=>v?.ok===true&&v.scope==='global-definitions'&&Array.isArray(v.roles)&&v.roles.every(r=>typeof r.id==='string'&&r.id&&typeof r.name==='string'&&typeof r.active_version==='string'&&r.active_version&&digest(r.avatar_asset_digest)&&typeof r.purpose==='string'&&['instructions','owns','boundaries','default_skills','specializations'].every(k=>Array.isArray(r[k])));
 async function read(id){const v=await call('swarm_role_read',id?{role_id:id}:{});if(!valid(v))throw Error('Roles could not be confirmed.');if(id)v.roles=[await nativeRoleDetail(v,id)];return v;}
 async function readSelected(id){const token=++serial;try{const v=await read(id);return active()&&token===serial?v.roles[0]:null;}catch(e){if(active()&&token===serial)throw e;return null;}}
 function draw(){
  if(!snapshot){body.innerHTML=serial?'<p class="empty">Roles unavailable. Reload to retry.</p>':'';create.disabled=true;return;}
  const query=search.value.trim().toLocaleLowerCase(),rows=snapshot.roles.filter(r=>!query||[r.name,r.id,r.purpose,...r.default_skills,...r.specializations].some(value=>typeof value==='string'&&value.toLocaleLowerCase().includes(query)));create.disabled=false;
  q('[data-role-count]').textContent=`Roles (${rows.length}${query?' of '+snapshot.roles.length:''})`;
  body.innerHTML=rows.length?`<ul class="role-list">${rows.map(r=>`<li><button class="library-card role-row" data-role-open="${escape(r.id)}" aria-pressed="${String(selected===r.id)}">${roleIcon(r)}<span class="role-row-text"><strong>${escape(r.name)}</strong><span class="quiet small role-purpose" title="${escape(r.purpose)}">${escape(r.purpose)}</span></span>${chevron}</button></li>`).join('')}</ul>`:'<p class="empty">No roles match this search.</p>';
 }
 async function load(){const token=++serial;loading(body,true,!snapshot,'detail');busy(reload,true);status.textContent='Loading roles…';try{const v=await read();if(!active()||token!==serial)return;snapshot=v;draw();status.textContent='';}catch(e){if(active()&&token===serial){draw();status.textContent=e.message;}}finally{if(active()&&token===serial){loading(body,false);busy(reload,false);}}}
 search.oninput=draw;reload.onclick=load;
 body.onclick=e=>{const b=e.target.closest('[data-role-open]');if(!b||!snapshot)return;const role=snapshot.roles.find(r=>r.id===b.dataset.roleOpen);if(role)openEditor(role,null,b);};
 create.onclick=()=>{if(snapshot)openEditor(null,snapshot.roles[0],create);};
 async function openEditor(role,template,opener){editor?.close();editor=null;selected=role?.id||null;draw();status.textContent='Loading role…';try{const original=role||template,current=await readSelected(original.id);if(!current)return;if(current.active_version!==original.active_version)throw Error('Role changed. Reload roles before editing.');if(role)role=current;else template=current;status.textContent='';opener=role?body.querySelector(`[data-role-open="${CSS.escape(role.id)}"]`):create;editor=roleEditor({role,template,roles:snapshot.roles,panel,opener,active,status,read,readSelected,async refresh(){const fresh=await read();if(!active())return null;snapshot=fresh;draw();return fresh;},done(id){selected=id;draw();editor=null;(id?body.querySelector(`[data-role-open="${CSS.escape(id)}"]`):create)?.focus();}});}catch(e){if(active())status.textContent=e.message;}}
 load();
}
function roleEditor(options){
 let {role}=options;const {template,roles,panel,opener,active,status,read,readSelected,refresh,done}=options,creating=!role;
 let source=role||template,avatarDigest=source.avatar_asset_digest,draftKey=null,lastRequest=null,uncertain=false,pending=false,expected=role?.active_version||null;
 const lines=v=>(v||[]).join('\n');
 // Anatomy follows the approved Roles composition: main column Name/Purpose/Instructions, large avatar at right,
 // Boundaries collapsed, Skills as chips, Flows/Loops rows, Cancel/Create footer. Custody stays in a disclosure.
 const html=libraryMarkup('role-form',{role0:creating?'New role':escape(role.name),role1:creating?'Custom role':'Global definition',role2:escape(source.name),role3:escape(source.purpose),role4:escape(lines(source.instructions)),role5:creating?libraryMarkup('role-artwork-source',{options:roles.map(r=>`<option value="${escape(r.id)}"${r.id===template.id?' selected':''}>${escape(r.name)}</option>`).join('')}): '',role6:escape(lines(source.owns)),role7:escape(lines(source.boundaries)),role8:creating?libraryMarkup('role-id-field'):'',role9:escape(lines(source.specializations)),role10:escape(source.accent||'#ff7a18'),role11:escape(source.lucide_icon||''),role12:creating?'The avatar is the admitted retained artwork of the selected role; nothing is uploaded or linked.':'Saving appends a new version; it never changes who may run work.',role13:chevron,role14:chevron,role15:!creating&&role.source==='user_override'?'<button type="button" data-role-reset>Reset to built-in</button>':'',role16:creating?'Create role':'Save role'});
 const mounted=mountEditor(creating?'New role':'Edit '+role.name,html,panel,opener),form=mounted.form,field=n=>form.elements.namedItem(n),note=form.querySelector('[data-editor-status]'),submit=mounted.actions.querySelector('[type=submit]'),reloadButton=mounted.actions.querySelector('[data-editor-reload]'),resetButton=mounted.actions.querySelector('[data-role-reset]');
 const preview=()=>{form.querySelector('[data-role-avatar]').innerHTML=roleAvatar(source,field('name').value.trim()||source.name);const choice=source.avatar_choices?.find(c=>c.id==='canonical'),button=form.querySelector('[data-role-canonical]');button.hidden=!choice||choice.digest===source.avatar_asset_digest;button.disabled=pending||choice?.digest===avatarDigest;form.querySelector('[data-role-avatar-note]').textContent=avatarDigest!==source.avatar_asset_digest?'Canonical artwork selected. Save to apply.':'Image uploads are unavailable. Current artwork stays active until you save.';};
 // Skills are chips over the role's default_skills list; the same safe-identifier rule as the server applies.
 let skills=[...(source.default_skills||[])];const skillToken=/^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/;
 const chips=()=>{form.querySelector('[data-skill-chips]').innerHTML=skills.map(s=>`<span class="chip" data-skill-chip="${escape(s)}">${escape(s)}<button type="button" data-chip-remove="${escape(s)}" aria-label="Remove skill ${escape(s)}">×</button></span>`).join('')+'<span class="chip chip-add"><input data-skill-input placeholder="+ Add skill" aria-label="Add skill" maxlength="256" autocomplete="off"></span>';};
 // The consumed value is cleared before the chips re-render: removing the focused field fires focusout, which
 // re-enters here and must find nothing to add. Blur commits quietly; only Enter and submit report or refocus.
 const addSkill=(input,explicit=true)=>{const value=input.value.trim();if(!value)return;if(!skillToken.test(value)){input.setCustomValidity('Use letters, digits and . _ : -');if(explicit)input.reportValidity();return;}input.setCustomValidity('');input.value='';if(!skills.includes(value))skills.push(value);chips();if(explicit)form.querySelector('[data-skill-input]').focus();};
 form.addEventListener('click',e=>{const remove=e.target.closest('[data-chip-remove]');if(!remove)return;skills=skills.filter(s=>s!==remove.dataset.chipRemove);chips();form.querySelector('[data-skill-input]').focus();});
 form.addEventListener('keydown',e=>{if(e.target.matches('[data-skill-input]')&&e.key==='Enter'){e.preventDefault();addSkill(e.target);}});
 form.addEventListener('focusout',e=>{if(e.target.matches?.('[data-skill-input]'))addSkill(e.target,false);});
 // The ID is derived from the name until the user edits it under More; the native pattern still guards it.
 const slug=text=>text.normalize('NFKD').replace(/[̀-ͯ]/g,'').toLowerCase().replace(/[^a-z0-9._:-]+/g,'-').replace(/^[^a-z0-9]+/,'').replace(/-+$/,'').slice(0,128);
 let idTouched=false;const deriveId=()=>{if(!creating||idTouched)return;field('role_id').value=slug(field('name').value);};
 form.addEventListener('input',e=>{if(e.target.name==='name'||e.target.name==='lucide_icon')preview();if(e.target.name==='name')deriveId();if(e.target.name==='role_id')idTouched=true;});
 guardRoutes(form);
 // Switching the starting role repopulates every field from it, including empty lists; a typed ID stays.
 const populate=r=>{avatarDigest=r.avatar_asset_digest;field('name').value=r.name;field('purpose').value=r.purpose;for(const key of ['instructions','owns','boundaries','specializations'])field(key).value=lines(r[key]);skills=[...(r.default_skills||[])];chips();field('accent').value=r.accent||'#ff7a18';field('lucide_icon').value=r.lucide_icon||'';deriveId();preview();};
 if(creating)field('template').onchange=()=>{const chosen=roles.find(r=>r.id===field('template').value);if(!chosen)return;source=chosen;populate(chosen);readSelected(chosen.id).then(current=>{if(mounted.open()&&current&&current.id===source.id&&current.active_version===source.active_version){source={...source,avatar:current.avatar,avatar_choices:current.avatar_choices};preview();}}).catch(()=>{if(mounted.open())note.textContent='Artwork could not be loaded. Your draft is preserved.';});};
 form.querySelector('[data-role-canonical]').onclick=()=>{if(pending)return;const choice=source.avatar_choices?.find(c=>c.id==='canonical');if(choice){avatarDigest=choice.digest;preview();}};
 chips();deriveId();preview();
 const open=()=>mounted.open()&&active(),split=n=>field(n).value.split('\n').map(s=>s.trim()).filter(Boolean);
 const manifest=()=>{const m={name:field('name').value.trim(),purpose:field('purpose').value.trim(),owns:split('owns'),instructions:split('instructions'),boundaries:split('boundaries'),default_skills:[...skills],specializations:split('specializations'),avatar_asset_digest:avatarDigest,accent:field('accent').value.toLowerCase()};if(!creating&&Array.isArray(source.avatar_variants))m.avatar_variants=source.avatar_variants;const icon=field('lucide_icon').value.trim();if(icon)m.lucide_icon=icon;return m;};
 const same=(a,b)=>{if(a===b)return true;if(!a||!b||typeof a!=='object'||typeof b!=='object'||Array.isArray(a)!==Array.isArray(b))return false;const keys=Object.keys(a);return keys.length===Object.keys(b).length&&keys.every(k=>Object.hasOwn(b,k)&&same(a[k],b[k]));};
 const matches=(r,m)=>Object.keys(m).every(k=>same(r[k],m[k]))&&same(r.lucide_icon??null,m.lucide_icon??null)&&same(r.avatar_variants??[],m.avatar_variants??[]);
 const controls=()=>[...form.querySelectorAll('input,textarea,select,button'),...mounted.actions.querySelectorAll('button')];
 const roleId=()=>creating?field('role_id').value.trim():role.id;
 async function run(command,m){
  if(pending)return;const id=roleId(),key=JSON.stringify([command,id,expected,m]);
  // An unchanged ambiguous retry resends the identical original command (same event, dedupe key and
  // observed_at_ms); any change or a settled outcome mints a new identity.
  let request=uncertain&&key===draftKey?lastRequest:null;
  if(!request){const eventId=newIdentity('role-edit-');request={command,role_id:id,event_id:eventId,dedupe_key:eventId,provenance:'hq-roles-editor',observed_at_ms:Date.now(),acknowledge:true};if(m)request.manifest=m;if(!creating)request.expected_active_version=expected;}
  draftKey=key;lastRequest=request;
  pending=true;uncertain=false;const all=controls(),disabled=all.map(c=>c.disabled);all.forEach(c=>c.disabled=true);note.textContent='Saving…';
  try{const raw=await call('swarm_role_save',request);if(!open())return;
   if(raw?.ok===false){reloadButton.hidden=false;note.textContent=raw.state==='CONFLICT'?'This role changed elsewhere. Reload current roles; your draft is preserved.':'Not saved: check the fields and the admitted avatar source. Your draft is preserved.';return;}
   if(raw?.ok!==true||raw.receipt?.role_id!==id||raw.receipt.command!==request.command||raw.receipt.event_id!==request.event_id||!['appended','unchanged'].includes(raw.receipt.status)||typeof raw.receipt.active_version!=='string'||!raw.receipt.active_version)throw Error('receipt');
   const fresh=await read(id);if(!open())return;const saved=fresh.roles.find(r=>r.id===id&&r.active_version===raw.receipt.active_version);if(!saved||(m?!matches(saved,m):saved.source!=='builtin'))throw Error('readback');
   await refresh();if(!open())return;mounted.close();done(id);status.textContent='Saved';}
  catch{if(open()){uncertain=true;reloadButton.hidden=false;note.textContent='Save not confirmed. Your draft is preserved. Save again unchanged to retry the same request, or reload current roles.';}}
  finally{pending=false;if(open())all.forEach((c,i)=>{if(c.isConnected)c.disabled=disabled[i];});}
 }
 form.onsubmit=e=>{e.preventDefault();if(!form.reportValidity())return;run(creating?'ROLE_MANIFEST_CREATE':'ROLE_MANIFEST_REVISE',manifest());};
 if(resetButton)resetButton.onclick=()=>run('ROLE_MANIFEST_RESET',null);
 mounted.actions.querySelector('[data-editor-cancel]').onclick=()=>{mounted.close();done(role?.id||null);};
 reloadButton.onclick=async()=>{if(pending)return;pending=true;reloadButton.disabled=true;const id=roleId();try{const fresh=await refresh();if(!open()||!fresh)return;const current=fresh.roles.find(r=>r.id===id);
  // Native reads have no command-history binding: a changed version cannot confirm this request.
  if(current&&!creating){role=current;expected=current.active_version;preview();}uncertain=false;
  note.textContent=creating&&current?'A role with this ID already exists. Choose another ID; your draft is preserved.':'Current roles loaded. Review your preserved draft, then save.';}
  catch{if(open())note.textContent='Could not reconcile. Your draft is preserved.';}finally{pending=false;if(open())reloadButton.disabled=false;}};
 form.onsubmit=((submitHandler)=>e=>{const pendingInput=form.querySelector('[data-skill-input]');if(pendingInput?.value.trim()){e.preventDefault();addSkill(pendingInput);if(pendingInput.isConnected&&!pendingInput.checkValidity())return;}submitHandler(e);})(form.onsubmit);
 field('name').focus();
 return mounted;
}
function unitCommandMatches(p,d,result){
 const matches=(o,fields)=>!!o&&Object.entries(fields).every(([k,v])=>o[k]===v),hex=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v),e=p?.submission?.envelope,c=e?.task_creation,m=c?.task_manifest_draft,r=c?.role_manifest;
 if(!matches(p,{ok:true,status:'PREPARED',kind:d.kind})||!hex(p.command_digest)||!matches(p.submission,{acknowledge:true})||typeof p.submission.instruction!=='string'||!p.submission.instruction||!matches(e,{command_id:d.request_id,idempotency_key:d.request_id,project_id:d.project_id,ctrl_id:d.ctrl_id,action:'MANUAL_AGENT',target_intent:'NEW_THREAD',target_thread_id:''})||!hex(e.root_digest)||!hex(e.payload_digest)||!Number.isSafeInteger(e.expected_ledger_revision)||e.expected_ledger_revision<0||!matches(c,{parent_task_id:d.ctrl_id,independent_host_task:false})||!matches(r,d.coordinator_role)||!matches(m,{project_id:d.project_id,ctrl_id:d.ctrl_id,task_name:d.name,manifest_id:'unit:'+d.request_id,role_scope:'LEAD_SINGLE'})||m.work_unit?.kind!==d.kind)return false;
 if(arguments.length===2)return true;const b=result?.readback,u=b?.unit,event=b?.creation_event,cursor=b?.cursor;
 return matches(result,{ok:true,work_completed:false,command_digest:p.command_digest,observed_root_digest:e.root_digest})&&['RESULT','REPLAY'].includes(result.status)&&typeof result.thread_id==='string'&&!!result.thread_id&&b?.state==='KNOWN'&&matches(u,{task_id:result.thread_id,coordinator_id:result.thread_id,project_id:d.project_id,ctrl_id:d.ctrl_id,name:d.name,role_scope:'LEAD_SINGLE'})&&u.work_unit?.kind===d.kind&&/^sha256:[a-f0-9]{64}$/.test(u.subject_version||'')&&matches(b.role_manifest_ref,{manifest_id:r.id,manifest_version:r.version,manifest_digest:'sha256:'+r.version.split(':').at(-1)})&&ticketCursorValid(cursor)&&ticketCursorValid(event)&&event.event_id===d.request_id&&cursor.event_seq>=event.event_seq&&(cursor.event_seq!==event.event_seq||cursor.event_digest===event.event_digest&&cursor.event_id===event.event_id);
}
function unitsPage(active){
 projectShell({name:'Units'},libraryMarkup('unit-page',{projects:(roster?.projects||[]).map(p=>`<option value="${escape(p.id)}"${p.id===selectedProject?' selected':''}>${escape(p.name)}</option>`).join(''),reload:reloadIcon}));
 const q=s=>projectPage.querySelector(s),picker=q('[data-unit-project]'),body=q('[data-unit-catalog]'),panel=q('[data-unit-editor]'),status=q('[data-library-status]'),create=q('[data-unit-draft]');let serial=0,hives=[],roles=[],editor=null;
 const key=(h,u)=>JSON.stringify([h.ctrl_id,u.task_id]),name=a=>a.display_name||a.title||'Unnamed unit';
 async function load(){const token=++serial,id=picker.value;create.disabled=true;body.replaceChildren();panel.hidden=true;editor?.close();hives=[];roles=[];if(!id){status.textContent='Choose a saved project.';return;}loading(body,true,true,'detail');status.textContent='Loading Units…';try{const [raw,r]=await Promise.all([call('swarm_status',{project_id:id}),call('swarm_role_read')]);const v=hiveProjection(raw,id);if(!active()||token!==serial)return;hives=v.items;if(r?.ok===true&&r.scope==='global-definitions'&&Array.isArray(r.roles))roles=r.roles.filter(x=>typeof x.id==='string'&&typeof x.name==='string'&&typeof x.active_version==='string');body.innerHTML=hives.some(h=>h.units.length)?`<ul class="library-cards">${hives.flatMap(h=>h.units.map(u=>{const a=h.agents.find(a=>a.id===u.task_id);return `<li class="unit-card"><button class="unit-card-head" data-unit-open="${escape(key(h,u))}"><span class="unit-tile unit-tile-${u.work_unit.kind.toLowerCase()}">${unitIcon(u.work_unit.kind)}</span><span class="unit-card-text"><strong>${escape(name(a))}</strong><span class="quiet small">${u.work_unit.kind==='LAB'?'Lab':'Factory'} · ${escape(h.label||'Hive')}</span></span>${chevron}</button></li>`;})).join('')}</ul>`:'<p class="empty">No retained Units in this project.</p>';create.disabled=!hives.length;status.textContent=v.state==='PARTIAL'?'Some Hive bindings are unavailable.':'';return true;}catch{if(active()&&token===serial)status.textContent='Units unavailable. Reload to retry.';}finally{if(active()&&token===serial)loading(body,false);}}
 body.onclick=e=>{const button=e.target.closest('[data-unit-open]');if(!button)return;for(const h of hives){const u=h.units.find(u=>key(h,u)===button.dataset.unitOpen);if(!u)continue;const a=h.agents.find(a=>a.id===u.task_id);showDialog(name(a),`<dl><dt>Type</dt><dd>${u.work_unit.kind==='LAB'?'Lab':'Factory'}</dd><dt>Hive</dt><dd>${escape(h.label||'Hive')}</dd><dt>Profession</dt><dd>${escape(a.profession_label||'Unavailable')}</dd></dl><p class="quiet">Read-only retained Unit.</p><details><summary>Source bindings</summary><p>CTRL <code>${escape(h.ctrl_id)}</code></p><p>Unit <code>${escape(u.task_id)}</code></p><code>${escape(u.manifest_identity.manifest_digest)}</code></details>`);return;}};
 create.onclick=()=>{if(!hives.length)return;editor?.close();editor=mountEditor('New unit',libraryMarkup('unit-form',{hives:hives.map(h=>`<option value="${escape(h.ctrl_id)}">${escape(h.label||'Hive')}</option>`).join(''),roles:roles.map(r=>`<option value="${escape(r.id)}">${escape(r.name)}</option>`).join(''),disabled:roles.length?'':' disabled'}),panel,create);
 const mounted=editor,{form,actions}=mounted,field=n=>form.elements[n],note=form.querySelector('[data-unit-status]'),submit=actions.querySelector('[type=submit]'),cancel=actions.querySelector('[data-editor-cancel]'),locks=[picker,q('[data-unit-reload]'),create,...body.querySelectorAll('button')],id=picker.value,token=serial,open=()=>active()&&token===serial&&picker.value===id&&mounted.open();let pending=false,prepared=null,request=null;form.oninput=form.onchange=()=>{if(!pending&&!prepared)request=null;};
 const unlock=()=>{locks.forEach(c=>c.disabled=false);$('#close-inspector').disabled=false;if(active()&&create.isConnected)create.focus();},controls=()=>{form.querySelectorAll('input,select,textarea').forEach(c=>c.disabled=pending||!!prepared);cancel.disabled=pending||!!prepared;submit.disabled=pending||!roles.length;if(compact())$('#close-inspector').disabled=cancel.disabled;};locks.forEach(c=>c.disabled=true);cancel.onclick=()=>{mounted.close();unlock();};
 if(compact()){const dialog=$('#inspector'),hold=e=>{if(pending||prepared)e.preventDefault();};dialog.addEventListener('cancel',hold);dialog.addEventListener('close',()=>{dialog.removeEventListener('cancel',hold);unlock();},{once:true});}
 form.onsubmit=async e=>{e.preventDefault();if(pending||!open()||!form.reportValidity())return;const role=roles.find(r=>r.id===field('role').value);if(!role)return;pending=true;controls();note.textContent=prepared?'Checking the same request…':'Preparing Unit…';
 try{if(!prepared){request={kind:field('kind').value,template_id:'custom',name:field('name').value.trim(),objective:field('purpose').value.trim(),project_id:id,ctrl_id:field('hive').value,request_id:request?.request_id||newIdentity('unit-'),coordinator_role:{id:role.id,version:role.active_version}};const p=await call('swarm_unit_prepare',request);if(!open())return;if(!unitCommandMatches(p,request))throw Error('receipt');prepared=p;}
 note.textContent='Creating Unit…';const result=await call('swarm_unit_create',prepared.submission);if(!open())return;
 if(result?.command_digest===prepared.command_digest&&result.status==='NOT_DISPATCHED'&&result.definitive_non_dispatch===true){prepared=null;request=null;submit.textContent='Prepare again';note.textContent='Nothing was dispatched. Review this draft, then prepare again.';return;}
 if(!unitCommandMatches(prepared,request,result))throw Error('receipt');const name=request.name;prepared=null;unlock();if(await load()&&active()&&picker.value===id){status.textContent=`Created ${name}.`;create.focus();}
 }catch(error){if(open()){note.textContent=prepared?'Creation is unconfirmed. Keep this draft and check the same request.':'Unit preparation is unavailable or changed. Your draft is preserved.';submit.textContent=prepared?'Check same request':'Retry preparation';}}finally{pending=false;if(open())controls();else if(mounted.open()){prepared=null;mounted.close();unlock();}}};field('name').focus();};
 picker.onchange=load;q('[data-unit-reload]').onclick=load;load();
}
const ticketKinds=['goal','milestone','task','block'];
const ticketCollection={goal:'goals',milestone:'milestones',task:'tasks',block:'blocks'};
const ticketKindLabel=k=>k.charAt(0).toUpperCase()+k.slice(1);
function ticketKindMarkup(k,compact=false){const paths={goal:'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10M12 11v2',milestone:'m12 3 9 9-9 9-9-9Z',task:'M8 6h12M8 12h12M8 18h12M3 6h1M3 12h1M3 18h1',block:'m12 3 9 5v8l-9 5-9-5V8Zm-9 5 9 5 9-5M12 13v8'};return `<span class="ticket-kind ticket-kind-${k}"${compact?` role="img" aria-label="${ticketKindLabel(k)}" title="${ticketKindLabel(k)}"`:""}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[k]}"/></svg>${compact?"":ticketKindLabel(k)}</span>`;}
const ticketTitle=r=>r.display_id?`${r.display_id} \u00b7 ${r.label}`:r.label;
function ticketStatus(r){
 if(!r.display_id)return 'Unknown';
 if(r.read_only===true){const d=r.durable_lifecycle;if(r.source!=='ledger:task-creation-binding'||typeof r.binding_event_digest!=='string'||!/^[a-f0-9]{64}$/.test(r.binding_event_digest)||typeof d?.manifest_digest!=='string'||!/^sha256:[a-f0-9]{64}$/.test(d.manifest_digest)||!ticketCursorValid(d?.ledger_cursor)||d?.source!=='ledger:bound-task-acceptance'||!Number.isInteger(d.total_blocks)||d.total_blocks<1||!Number.isInteger(d.accepted_blocks)||d.accepted_blocks<0||d.accepted_blocks>d.total_blocks)return 'Unknown';return d.state==='COMPLETED'&&d.accepted_blocks===d.total_blocks?'Completed':d.state==='OPEN'&&d.accepted_blocks<d.total_blocks?'Open':'Unknown';}
 const e=r.execution;if(typeof r.id!=='string'||!r.id||e?.record_id!==r.id||!Number.isInteger(e.required_count)||e.required_count<0||!Number.isInteger(e.accepted_required_count)||e.accepted_required_count<0||e.accepted_required_count>e.required_count)return 'Unknown';
 if(e.required_count===0)return e.completed===false?'Not linked':'Unknown';
 return e.completed===true&&e.accepted_required_count===e.required_count?'Completed':e.completed===false&&e.accepted_required_count<e.required_count?'Open':'Unknown';
}
function ticketCursorValid(c){return !!c&&!Array.isArray(c)&&Number.isSafeInteger(c.event_seq)&&c.event_seq>0&&typeof c.event_id==='string'&&!!c.event_id.trim()&&typeof c.event_digest==='string'&&/^[a-f0-9]{64}$/.test(c.event_digest);}
function ticketProjection(raw,id,operation='read'){
 if(raw?.ok!==true||raw.project_id!==id||raw.operation!==operation||!/^sha256:[a-f0-9]{64}$/.test(raw.source_digest||'')||JSON.stringify(raw.hierarchy)!==JSON.stringify(ticketKinds)||!Array.isArray(raw.records))throw Error('Ticket response was not confirmed.');
 const ids=new Set();for(const r of raw.records){if(!r||typeof r.id!=='string'||!r.id||ids.has(r.id)||!ticketKinds.includes(r.kind)||typeof r.label!=='string'||!['ROOT','BOUND','CONFLICT','DANGLING'].includes(r.parent_status))throw Error('Ticket identities are unavailable.');if(r.source==='ledger:task-creation-binding'&&(r.read_only!==true||r.parent!==null||r.parent_status!=='ROOT'||r.declared_state!==null))throw Error('Retained ticket identity is unavailable.');if(r.read_only===true&&(!ticketCursorValid(raw.ledger_cursor)||!ticketCursorValid(r.durable_lifecycle?.ledger_cursor)||['event_seq','event_id','event_digest'].some(k=>r.durable_lifecycle.ledger_cursor[k]!==raw.ledger_cursor[k])))throw Error('Retained ticket cursor is unavailable.');ids.add(r.id);}
 return raw;
}
async function readTickets(id){return ticketProjection(await call('swarm_project_tickets',{operation:'read',project_id:id}),id);}
function ticketRows(records){
 const ordered=[],seen=new Set(),byId=new Map(records.map(r=>[r.id,r]));
 function append(r,depth){if(seen.has(r.id))return;seen.add(r.id);ordered.push({r,depth});records.filter(c=>c.parent_status==='BOUND'&&c.parent?.id===r.id&&ticketKinds.indexOf(c.kind)===ticketKinds.indexOf(r.kind)+1).forEach(c=>append(c,depth+1));}
 records.filter(r=>r.parent_status!=='BOUND'||!byId.has(r.parent?.id)).forEach(r=>append(r,0));records.forEach(r=>append(r,0));return ordered;
}
async function openTasks(projectId='',withinProject=false,target=null){
 const request=++detailGeneration,route=location.hash;if(!target){selectedProject=withinProject?projectId:null;$('#main').hidden=true;settingsPage.hidden=true;projectPage.hidden=false;
 $('#settings').classList.remove('selected');$('#settings').removeAttribute('aria-current');$('#all-projects').classList.remove('selected');tasksNav.classList.toggle('selected',!withinProject);if(!withinProject)tasksNav.setAttribute('aria-current','page');}
 const projects=(roster?.projects||[]).filter(p=>!projectId||p.id===projectId),results=new Map();let reading=false,pendingProjects=0;
 const markup=`${withinProject?'<h2>Tickets</h2>':''}<div class="ticket-toolbar">${withinProject?'':`<label>Project <select data-tasks-project><option value="">All projects</option>${(roster?.projects||[]).map(p=>`<option value="${escape(p.id)}"${p.id===projectId?' selected':''}>${escape(p.name)}</option>`).join('')}</select></label>`}<label>Search <input data-ticket-search type="search" placeholder="Search tickets"></label><button data-ticket-create disabled>+ New ticket</button></div><section data-tasks-results></section>`;if(target)target.innerHTML=markup;else projectShell({name:'Tickets'},markup);const surface=target||projectPage;
 const active=()=>request===detailGeneration&&location.hash===route,body=surface.querySelector('[data-tasks-results]'),search=surface.querySelector('[data-ticket-search]'),create=surface.querySelector('[data-ticket-create]');
 const picker=surface.querySelector('[data-tasks-project]');if(picker)picker.onchange=e=>openTasks(e.target.value);
 function draw(){
  if(!active())return;const focused=body.contains(document.activeElement)?document.activeElement:null,focusData=focused?{...focused.dataset}:null,logsOpen=!!body.querySelector('.activity-logs[open]');const successful=[...results.values()].filter(x=>x.data),pending=pendingProjects,failed=[...results.values()].filter(x=>!x.data||x.stale),query=search.value.trim().toLocaleLowerCase();create.disabled=!successful.length;
  const rows=projects.flatMap(project=>ticketRows(results.get(project.id)?.data?.records||[]).filter(({r})=>ticketTitle(r).toLocaleLowerCase().includes(query)).map(({r,depth})=>({project,r,depth})));
  loading(body,pending>0);body.classList.toggle('is-refreshing',pending>0&&rows.length>0);body.innerHTML=`${pending&&!rows.length?skeleton('tickets'):''}${pending?`<span class="loading-announcement" role="status">Loading ${pending} project${pending===1?'':'s'}\u2026</span>`:''}${failed.length?`<div class="ticket-recovery"><span>${rows.length?'Some tickets may be out of date.':'Tickets unavailable.'}</span><button data-ticket-reload ${pending?'disabled aria-busy="true"':''}>Retry</button></div>`:''}${!roster?'<p>Project inventory unavailable. Refresh Projects to try again.</p>':rows.length?`<div class="table-scroll"><table class="ticket-table"><thead><tr><th scope="col">Ticket</th>${withinProject?'':'<th scope="col">Project</th>'}<th scope="col">Priority</th><th scope="col">Execution</th><th scope="col">Actions</th></tr></thead><tbody>${rows.map(({project,r,depth})=>`<tr><td style="--ticket-depth:${depth}"><div class="ticket-row">${ticketKindMarkup(r.kind,true)}<button data-ticket-open="${escape(r.id)}" data-ticket-project="${escape(project.id)}" aria-label="${escape(ticketTitle(r))}" aria-haspopup="dialog">${r.display_id?`<span class="ticket-id">${escape(r.display_id)}</span>`:""}<span class="ticket-title">${escape(r.label)}</span></button></div>${['CONFLICT','DANGLING'].includes(r.parent_status)?'<small>Parent needs attention</small>':''}</td>${withinProject?'':`<td data-ticket-column="Project">${escape(project.name)}</td>`}<td data-ticket-column="Priority">${r.priority?escape(ticketKindLabel(r.priority)):'\u2014'}</td><td data-ticket-column="Execution">${ticketStatus(r)}</td><td>${r.read_only!==true&&r.kind!=='block'?`<button data-ticket-child="${escape(r.id)}" data-ticket-project="${escape(project.id)}" aria-label="Add ${ticketKinds[ticketKinds.indexOf(r.kind)+1]} to ${escape(ticketTitle(r))}" title="Add ${ticketKinds[ticketKinds.indexOf(r.kind)+1]}">+</button><button data-ticket-attach="${escape(r.id)}" data-ticket-project="${escape(project.id)}" aria-label="Attach existing child to ${escape(ticketTitle(r))}" title="Attach existing"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 15 6-6M7 14l-2 2a3 3 0 0 0 4 4l4-4M11 8l4-4a3 3 0 0 1 4 4l-2 2"/></svg></button>`:''}</td></tr>`).join('')}</tbody></table></div>`:pending?'':failed.length?'':'<p>No planning tickets.</p>'}`;
  if(failed.length)body.insertAdjacentHTML('beforeend',`<details class="activity-logs"><summary>Activity logs (${failed.length})</summary><ul>${failed.map(r=>`<li>${escape(r.project.name)}: ticket read unavailable${r.stale?' \u00b7 retained observation may be stale':''}.</li>`).join('')}</ul></details>`);
  if(!pending&&!failed.length)feedback.hidden=true;
  if(!pending&&failed.length)notify(`${failed.length} project${failed.length===1?'':'s'} could not refresh tickets.`);
  if(logsOpen&&body.querySelector('.activity-logs'))body.querySelector('.activity-logs').open=true;
  if(focusData)Array.from(body.querySelectorAll('button')).find(b=>Object.keys(focusData).length&&Object.entries(focusData).every(([k,v])=>b.dataset[k]===v))?.focus({preventScroll:true});
 }
 function edit(project,snapshot,record=null,parent=null){ticketEditor(project,snapshot,record,parent,()=>withinProject?openProject(projectId):openTasks(projectId));}
 create.onclick=()=>{const first=projects.find(p=>results.get(p.id)?.data);if(first)edit(first,results.get(first.id).data);};
 body.onclick=e=>{if(e.target.closest('[data-ticket-reload]')){void load();return;}const b=e.target.closest('[data-ticket-open],[data-ticket-child],[data-ticket-attach]');if(!b)return;const project=projects.find(p=>p.id===b.dataset.ticketProject),snapshot=results.get(project?.id)?.data,r=snapshot?.records.find(r=>r.id===(b.dataset.ticketOpen||b.dataset.ticketChild||b.dataset.ticketAttach));if(!r)return;if(b.dataset.ticketOpen){ticketDetail(project,snapshot,r,()=>withinProject?openProject(projectId):openTasks(projectId));return;}if(r.read_only===true)return;if(b.dataset.ticketAttach){const candidates=snapshot.records.filter(c=>c.read_only!==true&&ticketKinds.indexOf(c.kind)===ticketKinds.indexOf(r.kind)+1&&c.parent?.id!==r.id);showDialog('Attach existing ticket',candidates.length?`<label>Ticket<select data-ticket-attach-choice>${candidates.map(c=>`<option value="${escape(c.id)}">${escape(ticketTitle(c))}</option>`).join('')}</select></label><button data-ticket-attach-continue>Continue</button>`:'<p>No eligible tickets.</p>');const next=$('#inspector-body [data-ticket-attach-continue]');if(next)next.onclick=()=>{const chosen=snapshot.records.find(c=>c.id===$('#inspector-body [data-ticket-attach-choice]').value);edit(project,snapshot,chosen,r);};}else edit(project,snapshot,b.dataset.ticketOpen?r:null,b.dataset.ticketChild?r:null);};search.oninput=draw;
 async function load(){if(reading)return;reading=true;pendingProjects=projects.length;draw();let cursor=0;try{await Promise.all(Array.from({length:Math.min(4,projects.length)},async()=>{while(active()&&cursor<projects.length){const project=projects[cursor++];try{results.set(project.id,{project,data:await readTickets(project.id)});}catch{const previous=results.get(project.id);results.set(project.id,{project,data:previous?.data||null,stale:!!previous?.data});}pendingProjects--;draw();}}));}finally{reading=false;}}await load();
}
function ticketDetail(project,snapshot,record,reload){
 const status=ticketStatus(record),execution=record.read_only===true?record.durable_lifecycle:record.execution;
 const accepted=record.read_only===true?execution?.accepted_blocks:execution?.accepted_required_count,total=record.read_only===true?execution?.total_blocks:execution?.required_count;
 const count=status!=='Unknown'&&Number.isInteger(total)&&total>0?`${accepted} of ${total}`:'Unknown';
 const assignment=record.assignment,assignee=typeof assignment?.assignee_id==='string'&&assignment.assignee_id.trim()?assignment.assignee_id:'Unassigned';
 showDialog(ticketTitle(record),`<div class="ticket-detail"><dl><dt>Project</dt><dd>${escape(project.name)}</dd><dt>Type</dt><dd>${ticketKindLabel(record.kind)}</dd><dt>${record.read_only===true?'Task status':'Execution link'}</dt><dd>${status}</dd><dt>Planned assignee</dt><dd>${assignee==='Unassigned'?'Unassigned':'Assigned'}</dd><dt>Accepted blocks</dt><dd>${count}</dd><dt>Processing chat</dt><dd>Unavailable</dd></dl>${record.description?`<details><summary>Recorded description</summary><p>${escape(record.description)}</p></details>`:''}<details><summary>Observation</summary>${assignee!=='Unassigned'?`<p>Planned assignee ID: <code>${escape(assignee)}</code></p>`:''}<p>${ticketCursorValid(snapshot.ledger_cursor)?`Ledger event ${snapshot.ledger_cursor.event_seq}`:'Ledger observation unavailable'}. Live freshness is unavailable.</p><p>Planning assignment does not confirm who is currently processing this ticket.</p></details></div>`);
 const footer=$('#inspector footer'),previous=footer.innerHTML;footer.innerHTML=record.read_only===true?'Read-only':'<button data-ticket-edit>Edit ticket</button>';
 const edit=footer.querySelector('[data-ticket-edit]');if(edit)edit.onclick=()=>{const opener=dialogOpener;footer.innerHTML=previous;ticketEditor(project,snapshot,record,null,reload);dialogOpener=opener;};
 $('#inspector').addEventListener('close',()=>{footer.innerHTML=previous;},{once:true});
}
function ticketEditor(project,snapshot,record,parent,reload){
 if(record?.read_only===true)return;
 if(parent?.read_only===true)return;
 const newId=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join(''),route=location.hash,kind=record?.kind||(parent?ticketKinds[ticketKinds.indexOf(parent.kind)+1]:'goal');let id=record?.id||newId(),pending=false,uncertain=false,reserved=false;
 showDialog(record?'Edit ticket':'New ticket',`<form class="ticket-editor"><p>${escape(project.name)}${record?' \u00b7 '+escape(record.display_id||id):''}</p><label data-ticket-code hidden>Project code<input name="project_code" pattern="[A-Za-z]{1,4}" maxlength="4" placeholder="1\u20134 letters"></label><input type="hidden" name="kind" value="${kind}">${record||parent?ticketKindMarkup(kind):`<fieldset class="ticket-types"><legend class="sr-only">Ticket type</legend>${ticketKinds.map(k=>`<label><input type="radio" name="ticket-type" value="${k}"${k===kind?' checked':''}>${ticketKindMarkup(k)}</label>`).join('')}</fieldset>`}<label>Title<input name="label" required maxlength="160" value="${escape(record?.label||'')}"></label><label>Description<textarea name="description" rows="3">${escape(record?.description||'')}</textarea></label><label>Parent<select name="parent_id"></select></label><label>Priority<select name="priority"><option value="">Not set</option>${['critical','high','medium','low'].map(v=>`<option value="${v}"${record?.priority===v?' selected':''}>${ticketKindLabel(v)}</option>`).join('')}</select></label><details><summary>Assignment</summary><label>Assignee ID<input name="assignee_id" value="${escape(record?.assignment?.assignee_id||'')}"></label><label>Role ID<input name="role_id" value="${escape(record?.assignment?.role_id||'')}"></label></details><p role="status" data-ticket-save-status></p><div class="ticket-actions"><button type="button" data-ticket-cancel>Cancel</button><button type="button" data-ticket-reconcile hidden>Reload current tickets</button><button type="submit">${record?'Save changes':'Create ticket'}</button></div></form>`);
 const dialog=$('#inspector'),form=dialog.querySelector('form'),footer=dialog.querySelector('footer');dialog.classList.add('ticket-dialog');footer.hidden=false;const footerBefore=footer.innerHTML;const actions=form.querySelector('.ticket-actions');footer.replaceChildren(actions);form.id='ticket-editor-form';actions.querySelector('[type=submit]').setAttribute('form',form.id);
 dialog.addEventListener('close',()=>{footer.innerHTML=footerBefore;dialog.classList.remove('ticket-dialog');},{once:true});const field=n=>form.elements.namedItem(n),status=form.querySelector('[data-ticket-save-status]'),submit=footer.querySelector('[type=submit]'),reconcile=footer.querySelector('[data-ticket-reconcile]');
 const active=()=>form.isConnected&&dialog.open&&location.hash===route;
 function parents(selected){const expected=ticketKinds[ticketKinds.indexOf(field('kind').value)-1];field('parent_id').innerHTML='<option value="">No parent</option>'+snapshot.records.filter(r=>r.read_only!==true&&r.kind===expected&&r.id!==id).map(r=>`<option value="${escape(r.id)}"${r.id===selected?' selected':''}>${escape(ticketTitle(r))}</option>`).join('');field('parent_id').disabled=!expected;if(selected&&field('parent_id').value!==selected){field('parent_id').add(new Option('Previous parent unavailable',selected,true,true));}}
 parents(parent?.id||record?.parent?.id);form.querySelectorAll('[name="ticket-type"]').forEach(r=>r.onchange=()=>{field('kind').value=r.value;parents(null);});footer.querySelector('[data-ticket-cancel]').onclick=()=>dialog.close();
 const changes=()=>({label:field('label').value.trim(),description:field('description').value,parent_id:field('kind').value==='goal'?null:field('parent_id').value||null,priority:field('priority').value||null,assignment:field('assignee_id').value||field('role_id').value?Object.fromEntries(['assignee_id','role_id'].filter(k=>field(k).value).map(k=>[k,field(k).value])):null});
 function matches(r,d){return r?.id===id&&r.kind===field('kind').value&&r.label===d.label&&r.description===d.description&&(r.parent?.id||null)===d.parent_id&&r.priority===d.priority&&JSON.stringify(r.assignment)===JSON.stringify(d.assignment);}
 form.onsubmit=async e=>{e.preventDefault();if(pending||uncertain||!form.reportValidity())return;const draft=changes(),operation=record?'update':'create',request={operation,project_id:project.id,expected_digest:snapshot.source_digest,acknowledge:true,collection:ticketCollection[field('kind').value],record_id:id,changes:draft};if(!record&&!form.querySelector('[data-ticket-code]').hidden)request.project_code=field('project_code').value.toUpperCase();pending=true;const controls=[...form.querySelectorAll('input,textarea,select,button'),submit,reconcile],disabled=controls.map(c=>c.disabled);controls.forEach(c=>c.disabled=true);status.textContent='Saving\u2026';
 try{const raw=await call('swarm_project_tickets',request);if(!active())return;if(!record&&raw?.ok===false&&raw.project_id===project.id&&raw.state==='REJECTED'&&raw.code==='RECORD_ID_RESERVED'){reserved=true;uncertain=true;reconcile.hidden=false;reconcile.textContent='Start new draft';status.textContent='This draft identity is reserved for an earlier request. Start a new draft to keep your content and save it separately.';return;}if(!record&&raw?.ok===false&&raw.project_id===project.id&&raw.state==='REJECTED'&&['PROJECT_CODE_REQUIRED','PROJECT_CODE_INVALID','PROJECT_CODE_CONFLICT'].includes(raw.code)){form.querySelector('[data-ticket-code]').hidden=false;field('project_code').required=true;status.textContent=raw.code==='PROJECT_CODE_CONFLICT'?'That code is already assigned. Choose another.':'Choose a project code of 1\u20134 letters.';return;}const result=ticketProjection(raw,project.id,operation);if(!result.records.some(r=>matches(r,draft)))throw Error('Save receipt did not match.');const fresh=await readTickets(project.id);if(!active())return;if(fresh.source_digest!==result.source_digest||!fresh.records.some(r=>matches(r,draft)))throw Error('Saved ticket changed before verification.');dialog.close();reload();}
 catch{if(active()){uncertain=true;reconcile.hidden=false;status.textContent='Save not confirmed. Your draft is preserved. Reload current tickets before trying again.';}}
 finally{pending=false;if(active()){controls.forEach((c,i)=>c.disabled=disabled[i]);submit.disabled=uncertain;}}};
 reconcile.onclick=async()=>{if(pending)return;pending=true;reconcile.disabled=true;const draft=changes();try{const fresh=await readTickets(project.id);if(!active())return;if(!reserved&&fresh.records.some(r=>matches(r,draft))){dialog.close();reload();return;}snapshot=fresh;if(reserved){id=newId();reserved=false;reconcile.hidden=true;reconcile.textContent='Reload current tickets';field('label').focus();}const selected=field('parent_id').value;parents(selected);if(!record&&fresh.records.some(r=>r.id===id))throw Error('Identity conflict');uncertain=false;submit.disabled=false;status.textContent='Current tickets loaded. Review your preserved draft, then save.';}catch{if(active())status.textContent='Could not reconcile this draft. Your input is preserved.';}finally{pending=false;if(active())reconcile.disabled=false;}};field('label').focus();
}
function hiveHref(project,ctrl=''){return '#hives?project='+encodeURIComponent(project)+(ctrl?'&ctrl='+encodeURIComponent(ctrl):'');}
async function openHives(){
 const params=new URLSearchParams(location.hash.split('?')[1]||''),id=params.get('project')||selectedProject||roster?.projects[0]?.id,chosen=params.get('ctrl');
 const request=++detailGeneration;selectedProject=id||null;$('#main').hidden=true;settingsPage.hidden=true;projectPage.hidden=false;$('#all-projects').classList.remove('selected');$('#settings').classList.remove('selected');$('#settings').removeAttribute('aria-current');
 const nav=document.querySelector('.library-nav a[href="#hives"]');nav.classList.add('selected');nav.setAttribute('aria-current','page');
 projectShell({name:'Hives'},`<div class="section-heading"><p class="quiet">The Units and agents working together on your project.</p><button disabled title="Hive creation is not available through this connection">Create hive</button></div><label class="hive-project">Project <select data-hive-project aria-label="Hive project">${(roster?.projects||[]).map(p=>`<option value="${escape(p.id)}"${p.id===id?' selected':''}>${escape(p.name)}</option>`).join('')}</select></label><div data-hive-content aria-live="polite"></div>`);
 projectPage.querySelector('h1').focus();const content=projectPage.querySelector('[data-hive-content]'),picker=projectPage.querySelector('[data-hive-project]');picker.onchange=()=>{location.hash=hiveHref(picker.value);};
 const current=()=>request===detailGeneration&&content.isConnected&&!projectPage.hidden&&selectedProject===id;
 if(!id||!roster?.projects.some(p=>p.id===id)){content.innerHTML='<p role="status">Choose an available project to see its Hives.</p>';return;}
 loading(content,true,true,'detail');
 try{const v=hiveProjection(await call('swarm_status',{project_id:id}),id);if(!current())return;
  const selected=chosen?v.items.find(h=>h.ctrl_id===chosen):null,name=a=>a.display_name||a.title||'Unnamed agent';
  const rows=(items,type)=>items.length?`<ul class="hive-rows">${items.map(a=>`<li><span class="hive-kind" aria-hidden="true">${type==='unit'?(a.work_unit.kind==='LAB'?'L':'F'):'◇'}</span><div><strong>${escape(name(a))}</strong><span class="quiet small">${escape(type==='unit'?(a.work_unit.kind==='LAB'?'Lab':'Factory'):(a.profession_label||'Profession unavailable'))}</span></div><button data-hive-agent="${escape(a.id)}" aria-label="View ${escape(name(a))}">View</button></li>`).join('')}</ul>`:`<p class="quiet">${type==='unit'?'No retained Units in this Hive.':'No bound agents.'}</p>`;
  const overview=h=>`<section class="hive-overview"><div class="section-heading"><div><p class="quiet small">${escape(roster.projects.find(p=>p.id===id).name)}</p><h2>${escape(h.label||'Hive')}</h2></div><a href="#hives" data-hive-back>All Hives</a></div><div class="hive-columns"><section><h3>Units</h3>${rows(h.units.map(u=>h.agents.find(a=>a.id===u.task_id)),'unit')}</section><section><h3>Agents</h3>${rows(h.agents,'agent')}</section></div><p class="quiet small">Read-only. Unit creation and Hive customization are not available through this connection.</p><details><summary>Source bindings</summary><p>CTRL <code>${escape(h.ctrl_id)}</code></p><code>${escape(JSON.stringify(v.cursor))}</code></details></section>`;
  content.innerHTML=(v.state==='PARTIAL'?'<p role="status">Some Hive bindings are unavailable.</p>':'')+(chosen&&!selected?'<p role="status">This Hive is no longer available. Choose another Hive.</p>':'')+(selected?overview(selected):v.items.length?`<div class="hive-catalog">${v.items.map(h=>`<article class="hive-card"><div class="hive-emblem" aria-hidden="true">⬡</div><div><h2>${escape(h.label||'Hive')}</h2><p class="quiet">${escape(roster.projects.find(p=>p.id===id).name)}</p><dl><div><dt>Units</dt><dd>${h.units.length}</dd></div><div><dt>Bound agents</dt><dd>${h.agents.length}</dd></div></dl><a class="hive-open" href="${hiveHref(id,h.ctrl_id)}">Open ${escape(h.label||'Hive')} <span aria-hidden="true">→</span></a></div></article>`).join('')}</div>`:'<p role="status">No bound Hives in this project yet.</p>');
  const back=content.querySelector('[data-hive-back]');if(back)back.href=hiveHref(id);
  content.querySelectorAll('[data-hive-agent]').forEach(button=>button.onclick=()=>{const a=selected?.agents.find(a=>a.id===button.dataset.hiveAgent);if(!a)return;showDialog(name(a),`<dl><dt>Profession</dt><dd>${escape(a.profession_label||'Unavailable')}</dd><dt>Responsibility</dt><dd>${escape(a.structural_role)}</dd><dt>Project</dt><dd>${escape(roster.projects.find(p=>p.id===id).name)}</dd>${a.work_unit?`<dt>Unit</dt><dd>${a.work_unit.kind==='LAB'?'Lab':'Factory'}</dd>`:''}</dl><details><summary>Source bindings</summary><code>${escape(JSON.stringify({id:a.id,project_id:a.project_id,ctrl_id:a.ctrl_id,manifest_identity:a.manifest_identity,parent_relation:a.parent_relation,cursor:v.cursor}))}</code></details>`,button);});
 }catch{if(current()){content.innerHTML='<p role="status">Hive bindings unavailable.</p><button data-hive-retry>Retry</button>';content.querySelector('button').onclick=()=>openHives();}}finally{if(current())loading(content,false);}
}
function hideSupport(){tasksNav.classList.remove('selected');tasksNav.removeAttribute('aria-current');document.querySelectorAll('.library-nav a').forEach(a=>{a.classList.remove('selected');a.removeAttribute('aria-current');}); $('#support-page').hidden=true;$('#support').classList.remove('selected');$('#support').removeAttribute('aria-current'); }
function restoreRoute(){
 if($('#inspector').open&&$('#inspector').classList.contains('ticket-dialog'))$('#inspector').close();
 hideSupport();
 if(location.hash==='#hives'||location.hash.startsWith('#hives?')){void openHives();return;}
 if(location.hash==='#tasks'){void openTasks();return;}
 if(location.hash==='#support'){
  detailGeneration++;selectedProject=null;projectPage.hidden=true;settingsPage.hidden=true;$('#main').hidden=true;$('#support-page').hidden=false;
  $('#all-projects').classList.remove('selected');$('#settings').classList.remove('selected');$('#settings').removeAttribute('aria-current');$('#support').classList.add('selected');$('#support').setAttribute('aria-current','page');$('#support-title').focus();return;
 }

 const [library,lens]=location.hash.slice(1).split('/');
 const catalogRoute=['units','roles'].includes(library)&&!lens,flowRoute=['flows','loops'].includes(library)&&!lens,scopedRoute=['units','roles'].includes(library)&&['flows','loops'].includes(lens);
 if(catalogRoute||flowRoute||scopedRoute){detailGeneration++;selectedProject=null;$('#main').hidden=true;settingsPage.hidden=true;projectPage.hidden=false;
 $('#settings').classList.remove('selected');$('#settings').removeAttribute('aria-current');$('#all-projects').classList.remove('selected');
 const nav=document.querySelector(`.library-nav a[href="#${flowRoute?library:lens||library}"]`);nav.classList.add('selected');nav.setAttribute('aria-current','page');
 if(catalogRoute)catalogPage(library);else libraryEditor(flowRoute?'all':library,flowRoute?library:lens);projectPage.querySelector('h1').focus();return;}
 const match=location.hash.startsWith('#project=');const {id}=projectRoute();
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
$('#search-toggle').onclick=()=>{const input=$('#project-search');if(compactHeader.hidden){input.focus();return;}const open=input.hidden;input.hidden=!open;$('.wordmark-wrap').hidden=open;$('#search-toggle').setAttribute('aria-expanded',String(open));if(open)input.focus();else{input.value='';render();}};
$('#project-search').addEventListener('input',render);
$('#project-search').addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();if(compactHeader.hidden){projectSearch.value='';render();}else $('#search-toggle').click();$('#search-toggle').focus();}});
$('#sidebar-search-toggle').onclick=()=>{const input=$('#sidebar-project-search');input.hidden=!input.hidden;$('#sidebar-search-toggle').setAttribute('aria-expanded',String(!input.hidden));if(!input.hidden)input.focus();else{input.value='';render();}};
$('#sidebar-project-search').addEventListener('input',render);
$('#sidebar-project-search').addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();$('#sidebar-search-toggle').click();$('#sidebar-search-toggle').focus();}});
function reset(){$('#project-search').value='';render();}
$('#clear-filter').onclick=reset;$('#all-projects').onclick=()=>{reset();$('#main').scrollIntoView({block:'start'});};
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{view=b.dataset.view;render();});
function coverage(){showDialog('Observation coverage',`<p>Registered project identities and activity come from the host\u2019s saved-project inventory. Activity does not grant a role, execution permission or completion credit.</p><p>Milestones, next actions, favorites and updated timestamps are not included in this roster. Open a project for its separately scoped details.</p><p>The human action inbox is not available here. Observed waits do not include every approval or review.</p><code>${escape(JSON.stringify(metrics?.cursor||roster?.cursor||'Unavailable'))}</code>`);}
$('#attention-details').onclick=coverage;
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
async function refresh(){if(refreshPending)return;refreshPending=true;const request=++generation;busy($('#refresh'),true);text('#roster-status','Loading projects...');$('#roster-status').classList.remove('is-stale');loading($('#project-content'),true,!roster);
 const rosterRead=(async()=>{try{const next=rosterView(await call('swarm_projects'));if(request!==generation)return;next.projects=activeFirstProjects(next.projects);roster=next;render();text('#project-count',number(next.projects.length));text('#roster-status',`${next.projects.length} projects${next.truncated?' (more unavailable)':''}`);if((location.hash.startsWith('#project=')&&!selectedProject)||location.hash==='#tasks'||location.hash.startsWith('#hives'))restoreRoute();}
 catch{if(request===generation){text('#roster-status',roster?'May be out of date.':'Projects unavailable. Refresh to retry.');$('#roster-status').classList.toggle('is-stale',!!roster);if(!roster)render();}}finally{if(request===generation)loading($('#project-content'),false);}})();
 const metricsRead=(async()=>{let next=null;try{next=metricView(await call('swarm_status'));}catch{}if(request!==generation)return;metrics=next;text('#attention-copy','Attention coverage unavailable.');$('#attention-copy').setAttribute('aria-label','Attention coverage unavailable: observed waits do not cover every approval or review.');text('#lane-count',metric(metrics?.lanes));text('#completed-count',metric(metrics?.completed));})();
 try{await Promise.all([rosterRead,metricsRead]);}finally{if(request===generation){refreshPending=false;busy($('#refresh'),false);}}
}
function usageDetails(){showDialog('Token observations',`<p>Input plus output from retained local token deltas, not billing. Cached input and reasoning are subsets, not added again.</p><p>${lastUsage?`Observed window: ${escape(new Date(lastUsage.window.after_ms).toLocaleString())} to ${escape(new Date(lastUsage.window.before_ms).toLocaleString())}.`:'No valid observation is available for this period.'}</p><p>${lastUsage?.status==='partial'?'Partial observation coverage. ':''}${lastUsage?.omitted?`The chart omits ${lastUsage.omitted.observations.toLocaleString()} earlier observations (${lastUsage.omitted.tokens.toLocaleString()} tokens); the total includes them.`:''}</p><p>The line joins recorded observations in time order; it does not estimate usage between them. Account limits, reset times, forecasts, per-project allocations and API-price equivalents are not supplied by this view.</p>`);}
$('#usage-details').onclick=usageDetails;
// One reserved readout line for the focused or hovered sample; cleared on every new range, failure, pointer
// leave and focus loss so no stale value survives. Values are observed samples only, never interpolated.
const usageReadout=document.createElement('p');usageReadout.className='usage-readout quiet small';usageReadout.setAttribute('aria-live','polite');$('.chart-wrap').append(usageReadout);
{const show=e=>{if(e.target.classList?.contains('usage-hit'))usageReadout.textContent=e.target.getAttribute('aria-label');};const chart=$('.usage-chart');chart.addEventListener('focusin',show);chart.addEventListener('mouseover',show);
 chart.addEventListener('mouseout',()=>{if(!document.activeElement?.classList?.contains('usage-hit'))usageReadout.textContent='';});chart.addEventListener('focusout',e=>{if(!e.relatedTarget?.classList?.contains('usage-hit'))usageReadout.textContent='';});}
function drawUsage(){const data=lastUsage;if(!data)return;const max=Math.max(1,...data.points.map(p=>p.tokens)),span=data.window.before_ms-data.window.after_ms;
 const svg=$('.usage-chart');if(!svg)return;svg.toggleAttribute('hidden',data.total===null);const width=Math.max(240,svg.clientWidth),height=180,focused=[...svg.querySelectorAll('.usage-hit')].indexOf(document.activeElement);svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.replaceChildren();$('.chart-wrap').classList.toggle('empty-chart',data.total===null);const node=(name,attrs,content)=>{const n=document.createElementNS(svg.namespaceURI,name);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);if(content)n.textContent=content;svg.append(n);return n;};
 for(let i=0;i<4;i++){const y=18+i*45;node('line',{x1:50,y1:y,x2:width-5,y2:y});if(data.total!==null)node('text',{x:0,y:y+4},Intl.NumberFormat(undefined,{notation:'compact',maximumFractionDigits:1}).format(max*(1-i/3)));}
 if(data.total!==null){const x=p=>50+(p.at-data.window.after_ms)/span*(width-55),y=p=>153-p.tokens/max*135,label=p=>`${p.start!==undefined&&p.start<p.at?new Date(p.start).toLocaleString()+' to ':''}${new Date(p.at).toLocaleString()}: ${p.tokens.toLocaleString()} tokens${p.start!==undefined&&p.start<p.at?' (observed sum)':''}`;
  if(data.points.length)node('path',{class:'usage-line',d:data.points.map((p,i)=>`${i?'L':'M'}${x(p)} ${y(p)}`).join(' ')});
  // Recorded samples remain individually accessible without drawing separate dots or synthetic points.
  data.points.forEach(p=>{const hit=node('rect',{class:'usage-hit',x:x(p)-8,y:y(p)-8,width:16,height:16,tabindex:'0',role:'img','aria-label':label(p)});const title=document.createElementNS(svg.namespaceURI,'title');title.textContent=label(p);hit.append(title);});}
 if(focused>=0)svg.querySelectorAll('.usage-hit')[focused]?.focus({preventScroll:true});
}
async function loadUsage(value){const retained=lastUsage&&hours===value;hours=value;usageReadout.textContent='';const request=++usageGeneration;$('.usage-total').setAttribute('aria-busy','true');loading($('.chart-wrap'),true,!retained,'chart');if(!retained){lastUsage=null;text('.usage-refreshed','');$('.usage-refreshed').removeAttribute('datetime');}document.querySelectorAll('[data-hours]').forEach(b=>b.setAttribute('aria-pressed',String(+b.dataset.hours===value)));text('.usage-period',value===24?'Last 24 hours':value===168?'Last 7 days':'Last 30 days');if(!retained){$('.usage-total').innerHTML='<span class="skeleton-line" aria-hidden="true"></span>';$('.usage-total').title='Loading token observations';text('.usage-coverage','Loading local observations\u2026');$('.usage-chart').replaceChildren();$('.chart-wrap').classList.remove('empty-chart');}
 try{const raw=await call('swarm_usage',{hours:value}),data=usageView(raw,value);if(request!==usageGeneration)return;
 if(data.window.before_ms<=data.window.after_ms)throw Error('Invalid window');lastUsage=data;text('.usage-total',number(data.total));$('.usage-total').title=data.total===null?'No token observation available':'Observed tokens';text('.usage-coverage',data.total===null?'No observations in this period.':'');
 const refreshed=new Date(),stamp=$('.usage-refreshed');stamp.dateTime=refreshed.toISOString();stamp.textContent=`Refreshed ${refreshed.toLocaleTimeString()}`;drawUsage();
 }catch{if(request!==usageGeneration)return;if(!retained){text('.usage-total','\u2014');$('.usage-chart').replaceChildren();$('.usage-chart').setAttribute('hidden','');$('.chart-wrap').classList.add('empty-chart');}$('.usage-total').title=retained?'May be out of date':'Usage unavailable';text('.usage-coverage',retained?'May be out of date.':'Usage unavailable.');$('.usage-coverage').title='Select a period to retry the usage read.';}finally{if(request===usageGeneration){loading($('.chart-wrap'),false);$('.usage-total').setAttribute('aria-busy','false');}}}
document.querySelectorAll('[data-hours]').forEach(b=>b.onclick=()=>loadUsage(+b.dataset.hours));
$('#refresh').onclick=()=>{if(refreshPending)return;refresh();loadUsage(hours);};
app.onteardown=async()=>{generation++;usageGeneration++;detailGeneration++;root.dataset.swarmHost='closed';selectedProject=null;projectPage.hidden=true;$('#settings').disabled=true;settingsPage.hidden=true;$('#main').hidden=false;return {};};
loading($('#project-content'),true,true);loading($('.chart-wrap'),true,true,'chart');
try{await app.connect(undefined,{timeout:5000});theme(app.getHostContext());root.dataset.swarmHost='initialized';$('#settings').disabled=!app.getHostCapabilities()?.serverTools;await Promise.all([refresh(),loadUsage(hours)]);if(/^#(?:roles|units)(?:\/(?:flows|loops))?$|^#(?:flows|loops)$|^#support$|^#tasks$|^#hives(?:\?|$)/.test(location.hash))restoreRoute();}catch{loading($('#project-content'),false);loading($('.chart-wrap'),false);render();root.dataset.swarmHost='unavailable';text('#roster-status','Host connection unavailable. Reopen SWARM to reconnect.');text('.usage-coverage','Usage unavailable while disconnected.');text('#attention-copy','\u2014');$('#attention-copy').setAttribute('aria-label','Attention unavailable while disconnected');}
}
