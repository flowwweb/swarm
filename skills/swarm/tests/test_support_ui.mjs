import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
const root=new URL('../assets/ui/',import.meta.url),read=name=>readFileSync(new URL(name,root));
const assets={ROADTO1M_COMPACT:['brand/road-to-1m-square-transparent.png','image/png','d22259dd1524a1bcec13ce13ff117bf098a493d77d653231658583689aba2155'],FLOWWWEB_LOGO:['brand/flowwweb-lockup-v2-light.svg','image/svg+xml','57253bfef4d4f26c399dbb1d5fb2f258d663b52d31dd1414ab7c9cfef808d7b3']};
const hash=b=>createHash('sha256').update(b).digest('hex');
// Review fixture only: production resource admission belongs to MCP integration.
function resource(bytes,digest,mime){assert.ok(bytes,'missing asset');assert.equal(hash(bytes),digest,'asset digest');return `data:${mime};base64,${bytes.toString('base64')}`;}
let html=read('swarm-hq-projects.html').toString(),source=read('swarm-projects-bootstrap.mjs').toString();
for(const [key,[file,mime,digest]] of Object.entries(assets)){
 assert.ok(html.includes(`__${key}__`));const bytes=read(file);assert.throws(()=>resource(null,digest,mime));assert.throws(()=>resource(Buffer.from('bad'),digest,mime));html=html.replaceAll(`__${key}__`,resource(bytes,digest,mime));
}
for(const [key,file,mime] of [['SUPPORT_PORTRAIT','brand/support-caricature-light.webp','image/webp'],['WORDMARK','../swarm-wordmark.png','image/png']])html=html.replaceAll(`__${key}__`,resource(read(file),hash(read(file)),mime));
assert.equal((html.match(/aria-label="Visit Flowwweb"/g)||[]).length,1);
assert.equal((html.match(/aria-label="Visit Road to \$1M"/g)||[]).length,1);
assert.ok(html.indexOf('id="support"')<html.indexOf('id="settings"'));
assert.match(html,/aria-disabled="true" title="Checkout is not available yet"/);
assert.doesNotMatch(source,/api\/1m\/checkout|amountCents/);
assert.match(source,/app.openLink\(\{url\}\)/);assert.match(source,/externalLinks.has\(url\)/);
assert.doesNotMatch(source,/setInterval|setTimeout/);
assert.doesNotMatch(html,/\u00c2|\u00e2[\u20ac\u2122]/,'no mojibake');
assert.doesNotMatch(html,/Continue on Flowwweb|\$1,000,000 goal|__ROADTO1M_LOGO__|road-to-million-wide/);
assert.doesNotMatch(html,/href="#(?:flows|loops)"|Workflows/);assert.match(html,/data-source="human-reported"/);assert.doesNotMatch(html,/support-goals|Choose your amount on Flowwweb/);
const helper=source.slice(source.indexOf("export function supportCheckoutURL"),source.indexOf("export async function mountProjects"));const {supportCheckoutURL}=await import("data:text/javascript;base64,"+Buffer.from(helper).toString("base64"));
for(const amount of ["5","10","20","1","12.34","10000"]){const u=new URL(supportCheckoutURL(amount));assert.equal(u.searchParams.get("amount"),Number(amount).toFixed(2));assert.equal(u.searchParams.getAll("amount").length,1);assert.equal(u.searchParams.get("checkout"),"1");}
for(const amount of [null,5,""," 5","0","10000.01","1.234","1e2","5&checkout=1","-5","custom"])assert.equal(supportCheckoutURL(amount),null);
const sizes={html:read('swarm-hq-projects.html').length,css:read('swarm-hq-host.css').length,fixtureHtmlWithImages:Buffer.byteLength(html)};
console.log('PASS exact assets, placeholders, missing/hash rejection fixture, links, fallback authority',sizes);
if(process.argv.includes('--browser')){
 const require=createRequire(import.meta.url),{chromium}=require(process.env.SWARM_PLAYWRIGHT_PATH||'playwright');
 const stub=`const mountSettings=el=>{el.innerHTML='<h1>Settings fixture</h1>'};const configTextWithChanges=()=>{};const settingsCSS='';const applyDocumentTheme=()=>{},applyHostStyleVariables=()=>{};class App{async connect(){} getHostContext(){return {}} getHostCapabilities(){return {serverTools:true}} async callServerTool({name,arguments:a}){if(name.startsWith('swarm_flow_')){window.writes=(window.writes||0)+1;if(window.conflict)return {isError:true};const key=name==='swarm_flow_assign'?'assignments':'definitions',draft=a.assignment||a.definition;window.lib[key].push({...draft,id:draft.id||'assignment-fixture',digest:'record-'+window.writes});window.lib.source_digest='source-'+window.writes;if(window.uncertain){window.uncertain=false;throw Error('transport');}return {structuredContent:{...structuredClone(window.lib),project_id:window.badReceipt?'wrong-project':a.project_id}};}if(name==='swarm_library_read'){const response={structuredContent:{...structuredClone(window.lib),project_id:a.project_id,kind:a.kind,inventory:a.kind==='ROLE'?{roles:[{id:'designer',name:'Designer',active_version:'role-v1'}],scope:'global-definitions'}:{instances:[{task_id:'unit-1',name:'Example Lab',project_id:a.project_id,ctrl_id:'ctrl-1',subject_version:'manifest-v1'}]}}};if(window.deferLibrary){window.deferLibrary=false;return new Promise(resolve=>window.releaseLibrary=()=>resolve(response));}return response;}return name==='swarm_projects'?{structuredContent:{ok:true,available:true,state:'KNOWN',cursor:{digest:'fixture'},projects:[{id:'example',name:'Example project',activity_status:'unknown'}]}}:{isError:true}} async openLink({url}){window.opened.push(url);if(window.failLink)return {isError:true};return {}}}window.opened=[];window.lib={ok:true,source_digest:'source-0',definitions:[{id:'create',version:1,digest:'flow-v1',objective:'Example',nodes:[]}],assignments:[],starter:{id:'new-flow',version:1,objective:'Example',nodes:[]}};`;
 source=source.replace(/^import .*;\r?\n/gm,'');
 // Keep module lexical scopes isolated, preserving the production readers.
 const dataModule=name=>'data:text/javascript;base64,'+read(name).toString('base64');
 const imports=`import {usageView,readProjectUsage,latestRequest} from '${dataModule('swarm-usage.mjs')}';import {rosterView,projectDetail,metricView} from '${dataModule('swarm-projects.mjs')}';`;
 html=html.replace('__CSS__',read('swarm-hq-host.css').toString()).replace('__SCRIPT__',imports+stub+source+'\nmountProjects();');
 const out=process.env.SWARM_SUPPORT_EVIDENCE;assert.ok(out,'evidence path required');mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,channel:'chrome'});const results=[];
 for(const [width,height] of [[1440,1000],[834,1112],[390,844]]){
  const page=await browser.newPage({viewport:{width,height},colorScheme:'dark'}),errors=[],requests=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(r.url()));
  await page.setContent(html);await page.locator('#support').click();await page.locator('#support-page').waitFor({state:'visible'});
  assert.equal(await page.locator('.support-checkout').textContent(),'Support');assert.equal(await page.locator('[role=progressbar]').getAttribute('aria-valuenow'),'5');
  assert.equal(await page.locator('#support').getAttribute('aria-current'),'page');assert.ok(!await page.locator('#all-projects').evaluate(e=>e.classList.contains('selected')));
  await page.locator('#support-page img').evaluateAll(async imgs=>{await Promise.all(imgs.map(i=>i.decode()));});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  for(const loc of ['.hq-footer [aria-label="Visit Flowwweb"]','.hq-footer [aria-label="Visit Road to $1M"]'])await page.locator(loc).click();
  assert.deepEqual(await page.evaluate(()=>window.opened),['https://flowwweb.com','https://flowwweb.com/1M']);
  for(const value of ['5','10','20']){await page.locator(`[name="support-amount"][value="${value}"]`).check({force:true});assert.equal(await page.locator('.support-checkout').getAttribute('data-prepared-url'),supportCheckoutURL(value));}
  await page.locator('[name="support-amount"][value="custom"]').check({force:true});await page.getByRole('textbox',{name:'Custom support amount in USD'}).fill('12.34');assert.equal(await page.locator('.support-checkout').getAttribute('data-prepared-url'),supportCheckoutURL('12.34'));
  await page.locator('#support-custom').fill('0');assert.equal(await page.locator('.support-checkout').getAttribute('data-prepared-url'),'');assert.ok(!await page.locator('#support-custom').evaluate(e=>e.checkValidity()));
  await page.locator('[name="support-amount"][value="10"]').check({force:true});const before=await page.evaluate(()=>window.opened.length);await page.locator('.support-checkout').focus();await page.keyboard.press('Enter');assert.equal(await page.evaluate(()=>window.opened.length),before);await page.getByText('Checkout is not available yet.').waitFor();
  await page.evaluate(()=>window.failLink=true);await page.locator('.hq-footer [aria-label="Visit Flowwweb"]').click();await page.getByText('Could not open this link. Try again.').waitFor();await page.evaluate(()=>window.failLink=false);await page.locator('.hq-footer [aria-label="Visit Flowwweb"]').click();assert.equal(await page.locator('#support-link-status').textContent(),'');
  await page.locator('#support-page .project-back').click();assert.ok(await page.locator('#support-page').isHidden());await page.locator('#support').focus();await page.keyboard.press('Enter');await page.locator('#support-page').waitFor({state:'visible'});
  await page.locator('#support').click();assert.equal(await page.locator('#support-title').evaluate(e=>getComputedStyle(e).outlineStyle),'none');
  await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:`${out}/support-${width}.png`,fullPage:true});
  for(const route of ['projects','project=example','units','units/flows','roles','roles/loops','settings']){
   if(route==='settings')await page.locator('#settings').click();else await page.evaluate(r=>location.hash=r,route);
   const active=route==='settings'?'#settings-page':route==='projects'?'#main':'#project-page';await page.locator(active).waitFor({state:'visible'});
   if(route==='roles'){
    const form=page.locator('[data-assignment]');await form.waitFor();await form.locator('[name=repeat]').fill('101');await form.locator('[name=label]').fill('My project role');await form.getByRole('button',{name:'Save assignment'}).click();await page.locator('[data-library-status]').filter({hasText:/^Saved$/}).waitFor();assert.equal(await page.evaluate(()=>window.lib.assignments.at(-1).repeat_count),101);
    await page.evaluate(()=>window.conflict=true);await form.locator('[name=notes]').fill('Preserve my draft');await form.getByRole('button',{name:'Save assignment'}).click();await page.getByText('Save not confirmed. Draft preserved. Reload to reconcile.').waitFor();assert.equal(await form.locator('[name=notes]').inputValue(),'Preserve my draft');await page.evaluate(()=>window.conflict=false);await page.locator('[data-library-load]').click();await page.getByText('Source reloaded. Review your preserved draft before saving again.').waitFor();assert.equal(await form.locator('[name=notes]').inputValue(),'Preserve my draft');
    await page.evaluate(()=>window.uncertain=true);const writes=await page.evaluate(()=>window.writes);await form.getByRole('button',{name:'Save assignment'}).click();await page.getByText('Save not confirmed. Draft preserved. Reload to reconcile.').waitFor();await page.locator('[data-library-load]').click();await page.locator('[data-library-status]').filter({hasText:/^Saved$/}).waitFor();assert.equal(await page.evaluate(()=>window.writes),writes+1);
    await page.evaluate(()=>window.badReceipt=true);await form.locator('[name=label]').fill('Receipt mismatch draft');await form.getByRole('button',{name:'Save assignment'}).click();await page.getByText('Save not confirmed. Draft preserved. Reload to reconcile.').waitFor();assert.equal(await form.locator('[name=label]').inputValue(),'Receipt mismatch draft');await page.evaluate(()=>window.badReceipt=false);await page.locator('[data-library-load]').click();await page.locator('[data-library-status]').filter({hasText:/^Saved$/}).waitFor();
    assert.ok(await form.getByRole('button',{name:'Save assignment'}).evaluate(e=>e===document.activeElement));await page.getByText('Edit Flow definition',{exact:true}).click();const flow=page.locator('[data-flow]');await flow.getByRole('button',{name:'Save Flow'}).click();await page.locator('[data-library-status]').filter({hasText:/^Saved$/}).waitFor();assert.ok(await page.evaluate(()=>window.lib.definitions.some(f=>f.id==='new-flow'&&f.digest)));

   }
   assert.equal(await page.locator('.library-nav h2').count(),0);assert.equal(await page.locator('.hq-footer').count(),1);assert.equal(await page.locator('.support-social').count(),0);
   assert.ok(await page.evaluate(sel=>document.querySelector(sel).getBoundingClientRect().bottom<=document.querySelector('.hq-footer').getBoundingClientRect().top+1,active),'footer follows active content');
   for(const label of ['Follow Peik Gabriel on X','Follow Peik Gabriel on GitHub']){const link=page.getByRole('link',{name:label,exact:true});const box=await link.boundingBox();assert.ok(box.width>=44&&box.height>=44);assert.equal(await link.getAttribute('title'),label);await page.keyboard.press('Tab');await link.focus();assert.notEqual(await link.evaluate(e=>getComputedStyle(e).outlineStyle),'none');}
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:`${out}/${route.replace(/[=/]/g,'-')}-${width}.png`,fullPage:true});
  }
  await page.evaluate(()=>location.hash='roles');await page.locator('[data-assignment]').waitFor();await page.evaluate(()=>window.deferLibrary=true);await page.locator('[data-library-load]').click();await page.waitForFunction(()=>typeof window.releaseLibrary==='function');await page.locator('#support').click();await page.evaluate(()=>window.releaseLibrary());assert.ok(await page.locator('#support-page').isVisible());assert.ok(await page.locator('#project-page').isHidden());
  await page.locator('.compact-brand').dispatchEvent('error');assert.ok(await page.locator('[data-brand-fallback]').isVisible());assert.ok(await page.locator('.compact-brand').isHidden());await page.locator('.hq-footer [aria-label="Visit Road to $1M"]').click();assert.equal((await page.evaluate(()=>window.opened)).at(-1),'https://flowwweb.com/1M');
  await page.locator('#support').click();
  await page.locator('.support-portrait').evaluate(img=>{img.src='data:image/webp;base64,broken';});
  await page.waitForFunction(()=>document.querySelector('.support-portrait').hidden);
  assert.ok(await page.locator('.support-portrait').isHidden());
  assert.ok(await page.locator('.support-checkout').isVisible());
  assert.equal(await page.locator('.support-layout').evaluate(el=>getComputedStyle(el).gridTemplateColumns.trim().split(/\s+/).length),1);
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:`${out}/support-portrait-failed-${width}.png`,fullPage:true});
  assert.deepEqual(errors,[]);assert.ok(!requests.some(x=>x.startsWith('http')));results.push({width,height,errors,networkRequests:requests.filter(x=>x.startsWith('http')),scrollWidth:await page.evaluate(()=>document.documentElement.scrollWidth)});await page.close();
 }
 await browser.close();writeFileSync(`${out}/BROWSER-PROOF.json`,JSON.stringify({class:'mock-browser',settings:'stub; not exercised',host:'fixture openLink; no native navigation/payment',sizes,results},null,2));console.log('PASS browser 1440/834/390, named links, keyboard, retry, route, image decode, containment, zero console/network');
}
