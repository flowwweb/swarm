// Portable task-view contracts. Synthetic fixtures only, not host or live acceptance.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const testDir=path.dirname(fileURLToPath(import.meta.url));
const repoRoot=path.resolve(testDir,'../../..');
const assets=path.join(repoRoot,'skills/swarm/assets/ui');
const require=createRequire(path.join(repoRoot,'console/package.json'));
const {chromium}=require('playwright');
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const js=fs.readFileSync(path.join(assets,'swarm-task-views.js'));
const css=fs.readFileSync(path.join(assets,'swarm-task-views.css'));
const html=fs.readFileSync(path.join(testDir,'fixtures/task-views.html'));
for(const name of ['swarm-task-views.js','swarm-task-views.css']){
  assert.deepEqual(fs.readFileSync(path.join(assets,name)),
    fs.readFileSync(path.join(repoRoot,'plugins/swarm/skills/swarm/assets/ui',name)),
    name+' generated mirror must match canonical bytes');
}
for(const [name,source] of [['component',js],['fixture',html.toString('utf8').match(/<script type="module">([\s\S]*?)<\/script>/)[1]]]){
  const parsed=spawnSync(process.execPath,['--input-type=module','--check'],{input:source,encoding:'utf8'});
  assert.equal(parsed.status,0,name+' syntax: '+parsed.stderr);
}
const executablePath=[process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe'].find(p=>p&&fs.existsSync(p));
const browser=await chromium.launch({headless:true,...(executablePath?{executablePath}:{})});
async function apiContracts(){
  const code=js;
let results;
const context=await browser.newContext({viewport:{width:1440,height:900}});
try {
  await context.route('**/*',route=>route.abort());
  const page=await context.newPage();
  const runtimeErrors=[]; page.on('pageerror',error=>runtimeErrors.push(String(error)));
  await page.setContent('<!doctype html><main id="fixture"></main>');
  results=await page.evaluate(async url=>{
    const {mountTaskViews}=await import(url);
    const rows=[];
    const snapshot=()=>({project_id:'fixture',source_version:'v1',source_file_sha256:'c'.repeat(64),
      canonical_digest:'sha256:'+'a'.repeat(64),binding_digest:'sha256:'+'b'.repeat(64),cursor:null,
      records:{milestones:[{source_pointer:'/milestones/0',source_record_digest:'sha256:'+'d'.repeat(64),
        value:{id:'m1',title:'First milestone',state:'accepted',task_ids:['t1','t2']}}],
        tasks:['t1','t2'].map((id,i)=>({source_pointer:`/tasks/${i}`,source_record_digest:'sha256:'+String(i+1).repeat(64),
          value:{id,title:`Task ${i+1}`,state:i?'completed':'active',milestone_id:'m1'}}))}});
    function probe(name,expected,body){
      const host=document.createElement('div');document.querySelector('#fixture').append(host);
      let actual;try{actual=body(host);}catch(error){actual={exception:String(error)};}
      rows.push({name,expected,actual,pass:JSON.stringify(expected)===JSON.stringify(actual)});host.remove();
    }
    probe('inspector exposes selected task and no invented progress',true,host=>{
      const view=mountTaskViews(host,{snapshot:snapshot(),layout:'inspector'});
      const good=host.querySelector('.stv').dataset.stvState==='ready'&&host.querySelector('[role="option"][aria-selected="true"]')?.textContent.includes('Task 1')&&host.querySelectorAll('progress,[role="progressbar"]').length===0;
      view.destroy();return good;
    });
    probe('milestone group and task details execute',true,host=>{
      const view=mountTaskViews(host,{snapshot:snapshot(),layout:'milestones'});
      host.querySelector('.stv-group-toggle').click();host.querySelector('.stv-row-toggle').click();
      const good=host.querySelector('.stv-row-detail:not([hidden])')?.textContent.includes('t1')&&host.querySelector('.stv-row[data-state="completed"] .stv-state')?.textContent==='Completed';
      view.destroy();return Boolean(good);
    });
    probe('undeclared production tasks null stays UNKNOWN, not invalid',true,host=>{
      const next=snapshot();next.records.tasks=null;
      const view=mountTaskViews(host,{snapshot:next,layout:'milestones'});
      const good=host.querySelector('.stv').dataset.stvState!=='error';view.destroy();return good;
    });
    probe('human state labels retain exact raw source in details',true,host=>{
      const next=snapshot();next.records.tasks[0].value.state='in_progress';
      next.records.tasks[1].value.state='waiting_for_external_review_of_the_entire_second_draft';
      const view=mountTaskViews(host,{snapshot:next,layout:'inspector'});
      const first=host.querySelector('.stv-state[data-state="in_progress"]')?.textContent==='In progress'&&
        host.querySelector('[data-field="state"] dd')?.textContent==='in_progress';
      host.querySelectorAll('[role="option"]')[1].click();
      const second=host.querySelector('.stv-task-detail > .stv-state')?.textContent==='Waiting for external review of the entire second draft'&&
        host.querySelector('[data-field="state"] dd')?.textContent==='waiting_for_external_review_of_the_entire_second_draft';
      view.destroy();return first&&second;
    });
    probe('task pointer from another collection is rejected',true,host=>{
      const next=snapshot();next.records.tasks[0].source_pointer='/artifacts/0';
      const view=mountTaskViews(host,{snapshot:next,layout:'inspector'});
      const good=host.querySelector('.stv').dataset.stvState==='error';view.destroy();return good;
    });
    probe('changed visible value cannot reuse identical record/source identities',true,host=>{
      const first=snapshot();const view=mountTaskViews(host,{snapshot:first,layout:'inspector'});
      const next=structuredClone(first);next.records.tasks[0].value.title='Different content with identical receipts';
      const result=view.update(next);const good=result.ok===false&&!host.textContent.includes('Different content with identical receipts');
      view.destroy();return good;
    });
    probe('malformed update preserves previous valid rows as stale',true,host=>{
      const view=mountTaskViews(host,{snapshot:snapshot(),layout:'inspector'});const result=view.update({});
      const good=result.ok===false&&result.state==='stale'&&host.textContent.includes('Task 1');view.destroy();return good;
    });
    probe('duplicate task identity rejected',true,host=>{
      const next=snapshot();next.records.tasks[1].value.id='t1';
      const view=mountTaskViews(host,{snapshot:next,layout:'inspector'});const good=host.querySelector('.stv').dataset.stvState==='error';view.destroy();return good;
    });
    probe('same-binding selection continuity and destroy',true,host=>{
      const first=snapshot();const view=mountTaskViews(host,{snapshot:first,layout:'inspector'});
      host.querySelectorAll('[role="option"]')[1].click();view.update(first);
      const kept=host.querySelector('[role="option"][aria-selected="true"]')?.textContent.includes('Task 2');
      view.destroy();return Boolean(kept)&&host.childElementCount===0&&view.update(first).state==='destroyed';
    });

    probe('UNKNOWN task records do not become empty or zero',true,host=>{
      const next=snapshot();next.records.tasks=null;next.records.milestones[0].value.task_ids=undefined;
      const view=mountTaskViews(host,{snapshot:next,layout:'milestones'});
      const good=host.querySelector('.stv').dataset.stvState!=='empty'&&host.textContent.includes('Tasks not declared')&&!host.textContent.includes('0 tasks');
      view.destroy();return good;
    });
    for(const pointer of ['/tasks/00','/tasks/1']){
      probe('noncanonical or wrong original index rejected '+pointer,true,host=>{
        const next=snapshot();next.records.tasks[0].source_pointer=pointer;
        const view=mountTaskViews(host,{snapshot:next,layout:'inspector'});
        const good=host.querySelector('.stv').dataset.stvState==='error';view.destroy();return good;
      });
    }
    probe('byte formatting and cohort binding change with same semantics accepted',true,host=>{
      const first=snapshot();const view=mountTaskViews(host,{snapshot:first,layout:'inspector'});
      const next=structuredClone(first);next.source_file_sha256='e'.repeat(64);next.binding_digest='sha256:'+'f'.repeat(64);
      const good=view.update(next).ok;view.destroy();return good;
    });
    probe('cohort binding change cannot bypass same-canonical content identity',true,host=>{
      const first=snapshot();const view=mountTaskViews(host,{snapshot:first,layout:'inspector'});
      const next=structuredClone(first);next.binding_digest='sha256:'+'f'.repeat(64);next.records.tasks[0].value.title='Changed under same canonical digest';
      const result=view.update(next);const good=result.ok===false&&!host.textContent.includes('Changed under same canonical digest');
      view.destroy();return good;
    });
    probe('cohort binding change cannot bypass retained record digest identity',true,host=>{
      const first=snapshot();const view=mountTaskViews(host,{snapshot:first,layout:'inspector'});
      const next=structuredClone(first);next.binding_digest='sha256:'+'f'.repeat(64);next.canonical_digest='sha256:'+'e'.repeat(64);
      next.records.tasks[0].value.title='Changed under retained record digest';
      const result=view.update(next);const good=result.ok===false&&!host.textContent.includes('Changed under retained record digest');
      view.destroy();return good;
    });

    probe('source_version cannot change under identical source identities',true,host=>{
      const first=snapshot();const view=mountTaskViews(host,{snapshot:first,layout:'inspector'});
      const next=structuredClone(first);next.source_version='v2';
      const result=view.update(next);const good=result.ok===false&&result.state==='stale'&&host.textContent.includes('source version v1');
      view.destroy();return good;
    });
    probe('project change cannot reuse the canonical brief digest',true,host=>{
      const first=snapshot();const view=mountTaskViews(host,{snapshot:first,layout:'inspector'});
      const next=structuredClone(first);next.project_id='different-project';next.binding_digest='sha256:'+'9'.repeat(64);
      const result=view.update(next);const good=result.ok===false&&result.state==='stale'&&!host.textContent.includes('Project different-project');
      view.destroy();return good;
    });
    probe('genuine new version and changed record with new identities accepted',true,host=>{
      const first=snapshot();const view=mountTaskViews(host,{snapshot:first,layout:'inspector'});
      const next=structuredClone(first);next.source_version='v2';next.source_file_sha256='e'.repeat(64);
      next.canonical_digest='sha256:'+'f'.repeat(64);next.binding_digest='sha256:'+'9'.repeat(64);
      next.records.tasks[0].value.title='Genuine updated task';next.records.tasks[0].source_record_digest='sha256:'+'8'.repeat(64);
      const good=view.update(next).ok&&host.textContent.includes('Genuine updated task');view.destroy();return Boolean(good);
    });
    probe('genuine reorder with new source and canonical identities accepted',true,host=>{
      const first=snapshot();const view=mountTaskViews(host,{snapshot:first,layout:'inspector'});
      const next=structuredClone(first);next.source_version='v2';next.source_file_sha256='e'.repeat(64);
      next.canonical_digest='sha256:'+'f'.repeat(64);next.binding_digest='sha256:'+'9'.repeat(64);
      next.records.tasks.reverse().forEach((row,index)=>row.source_pointer='/tasks/'+index);
      const good=view.update(next).ok&&host.querySelector('[role="option"]')?.textContent.includes('Task 2');
      view.destroy();return Boolean(good);
    });
    probe('milestone title opens shared record inspector without expanding',true,host=>{
      const view=mountTaskViews(host,{snapshot:snapshot(),layout:'milestones'});
      host.querySelector('.stv-group-title').click();
      const good=host.querySelector('.stv-detail').dataset.recordKind==='milestones'&&
        host.querySelector('.stv-detail-title').textContent==='First milestone';
      host.querySelector('.stv-sheet-close').click();
      const back=host.querySelector('.stv-group-toggle').getAttribute('aria-expanded')==='false'&&
        document.activeElement===host.querySelector('.stv-group-title');
      view.destroy();return good&&back;
    });
    probe('task title and Back preserve group and row expansion',true,host=>{
      const view=mountTaskViews(host,{snapshot:snapshot(),layout:'milestones'});
      host.querySelector('.stv-group-toggle').click();host.querySelector('.stv-row-toggle').click();
      host.querySelector('.stv-row-title').click();
      const good=host.querySelector('.stv-detail').dataset.recordKind==='tasks'&&
        host.querySelector('.stv-detail').dataset.recordId==='t1';
      host.querySelector('.stv-sheet-close').click();
      const back=host.querySelector('.stv-group-toggle').getAttribute('aria-expanded')==='true'&&
        host.querySelector('.stv-row-toggle').getAttribute('aria-expanded')==='true'&&
        document.activeElement===host.querySelector('.stv-row-title');
      view.destroy();return good&&back;
    });
    probe('provenance is retained behind closed technical disclosure',true,host=>{
      const view=mountTaskViews(host,{snapshot:snapshot(),layout:'inspector'});
      const details=host.querySelector('.stv-technical');
      const good=!details.open&&!host.innerText.includes('/tasks/0')&&!host.innerText.includes('Source record digest');
      details.open=true;
      const available=host.innerText.includes('/tasks/0')&&host.innerText.includes('Source record digest');
      view.destroy();return good&&available;
    });
    probe('title filter is local and new binding resets it',true,host=>{
      const first=snapshot();const before=JSON.stringify(first);
      const view=mountTaskViews(host,{snapshot:first,layout:'inspector'});
      const search=host.querySelector('.stv-filter');search.value='Task 2';search.dispatchEvent(new Event('input'));
      const filtered=host.querySelectorAll('[role="option"]').length===1&&host.querySelector('[role="option"]').textContent.includes('Task 2');
      const next=structuredClone(first);next.binding_digest='sha256:'+'e'.repeat(64);view.update(next);
      const reset=search.value===''&&host.querySelectorAll('[role="option"]').length===2;
      view.destroy();return filtered&&reset&&JSON.stringify(first)===before;
    });
    probe('milestone dependencies resolve canonical milestone identities',true,host=>{
      const source=snapshot();source.records.milestones.push({source_pointer:'/milestones/1',source_record_digest:'sha256:'+'7'.repeat(64),
        value:{id:'m-review',title:'Review milestone',dependency_ids:['m1']}});
      const view=mountTaskViews(host,{snapshot:source,layout:'milestones'});
      host.querySelectorAll('.stv-group-title')[1].click();
      const primary=host.querySelector('.stv-dependencies li').textContent;
      const technical=host.querySelector('[data-field="dependencies"] li');
      const good=primary==='First milestone'&&technical.dataset.record==='present'&&technical.textContent==='First milestone (m1)';
      view.destroy();return good;
    });
    probe('task dependencies still resolve task identities',true,host=>{
      const source=snapshot();source.records.tasks[0].value.dependency_ids=['t2'];
      const view=mountTaskViews(host,{snapshot:source,layout:'inspector'});
      const good=host.querySelector('.stv-dependencies li').textContent==='Task 2'&&
        host.querySelector('[data-field="dependencies"] li').dataset.record==='present';
      view.destroy();return good;
    });
    probe('truly missing dependencies use the exact record-kind label',true,host=>{
      const source=snapshot();source.records.milestones[0].value.dependency_ids=['missing-milestone'];
      source.records.tasks[0].value.dependency_ids=['missing-task'];
      let view=mountTaskViews(host,{snapshot:source,layout:'milestones'});host.querySelector('.stv-group-title').click();
      const missingMilestone=host.querySelector('.stv-dependencies li').textContent==='Referenced milestone not available'&&
        host.querySelector('[data-field="dependencies"] li').textContent.includes('no milestone record');
      view.destroy();view=mountTaskViews(host,{snapshot:source,layout:'inspector'});
      const missingTask=host.querySelector('.stv-dependencies li').textContent==='Referenced task not available'&&
        host.querySelector('[data-field="dependencies"] li').dataset.record==='missing';
      view.destroy();return missingMilestone&&missingTask;
    });
    return rows;
  },'data:text/javascript;base64,'+code.toString('base64'));
  results.push({name:'no browser runtime exceptions',pass:runtimeErrors.length===0,actual:runtimeErrors,expected:[]});
} finally {await context.close();}

  return results;
}
async function referenceContinuityContracts(){
  const rows=[];
  for(const width of [1440,768,390]){
    const context=await browser.newContext({viewport:{width,height:900}});
    try{
      await context.route('**/*',route=>route.abort());
      const page=await context.newPage();await page.setContent('<!doctype html><main></main>');
      await page.addStyleTag({content:css.toString('utf8')});
      const observed=await page.evaluate(async url=>{
        const {mountTaskViews}=await import(url);
        const rows=[];
        for(const mode of ['identical','current-source','unrelated-record','closed','changed-record','changed-reference','changed-binding','removed-record','milestone-identical']){
          const host=document.createElement('div');document.querySelector('main').append(host);
          const first={project_id:'reference-fixture',source_version:1,source_file_sha256:'c'.repeat(64),
            canonical_digest:'a'.repeat(64),binding_digest:'b'.repeat(64),cursor:null,records:{
              milestones:[{source_pointer:'/milestones/0',source_record_digest:'3'.repeat(64),value:{id:'m1',title:'Long milestone reference '.repeat(20),task_ids:['t1','t2']}}],
              tasks:['t1','t2'].map((id,i)=>({source_pointer:'/tasks/'+i,source_record_digest:String(i+1).repeat(64),value:{id,title:'Task '+(i+1),milestone_id:'m1'}}))}};
          const view=mountTaskViews(host,{snapshot:first,layout:mode==='milestone-identical'?'milestones':'inspector'});
          if(mode==='milestone-identical'){
            host.querySelector('.stv-group-toggle').click();host.querySelector('.stv-row-toggle').click();host.querySelector('.stv-row-title').click();
          }else if(innerWidth<=720)host.querySelector('[role="option"]').click();
          const selector='.stv-detail:not([hidden]) .stv-secondary summary';
          const summary=host.querySelector(selector);summary.click();summary.focus();
          if(mode==='closed')summary.click();
          const before={open:summary.parentElement.open,focus:document.activeElement===summary};
          const next=structuredClone(first);
          if(mode==='current-source')next.source_file_sha256='f'.repeat(64);
          if(mode==='changed-record'){
            next.source_file_sha256='6'.repeat(64);next.canonical_digest='5'.repeat(64);
            next.records.tasks[0].source_record_digest='4'.repeat(64);next.records.tasks[0].value.title='Changed task';
          }
          if(mode==='unrelated-record'){
            next.source_file_sha256='6'.repeat(64);next.canonical_digest='5'.repeat(64);
            next.records.tasks[1].source_record_digest='4'.repeat(64);next.records.tasks[1].value.title='Other task changed';
          }
          if(mode==='changed-reference'){
            next.source_file_sha256='9'.repeat(64);next.canonical_digest='8'.repeat(64);
            next.records.milestones[0].source_record_digest='7'.repeat(64);next.records.milestones[0].value.title+='changed';
          }
          if(mode==='changed-binding')next.binding_digest='e'.repeat(64);
          if(mode==='removed-record'){
            next.source_file_sha256='6'.repeat(64);next.canonical_digest='5'.repeat(64);
            next.records.tasks.shift();next.records.tasks[0].source_pointer='/tasks/0';
          }
          const result=view.update(next);const current=host.querySelector(selector);
          const after={ok:result.ok,open:current?.parentElement.open??false,focus:current?document.activeElement===current:false,oldConnected:summary.isConnected};
          const preserve=['identical','current-source','unrelated-record','milestone-identical'].includes(mode);
          const pass=before.focus&&before.open===(mode!=='closed')&&after.ok&&!after.oldConnected&&
            after.open===preserve&&after.focus===(preserve||mode==='closed');
          rows.push({mode,before,after,pass});view.destroy();host.remove();
        }
        return rows;
      },'data:text/javascript;base64,'+js.toString('base64'));
      rows.push(...observed.map(row=>({name:width+'px secondary refresh '+row.mode,...row})));
    }finally{await context.close();}
  }
  return rows;
}
let apiResults,continuityResults;
try {apiResults=await apiContracts();}
catch(error){await browser.close();throw error;}
try {continuityResults=await referenceContinuityContracts();}
catch(error){await browser.close();throw error;}
const origin='https://swarm-task-fixture.invalid';
const fixture='/skills/swarm/tests/fixtures/task-views.html';
const files=new Map([[fixture,['text/html',html]],['/skills/swarm/assets/ui/swarm-task-views.js',['text/javascript',js]],
  ['/skills/swarm/assets/ui/swarm-task-views.css',['text/css',css]]]);
const checks=[],metrics=[],screenshots=[];
const evidenceDir=process.env.SWARM_TASK_VIEWS_EVIDENCE_DIR;
if(evidenceDir)fs.mkdirSync(evidenceDir,{recursive:true});
async function capture(page,name){
  if(!evidenceDir)return;
  const destination=path.join(evidenceDir,name+'.png');
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:destination,fullPage:false});
  screenshots.push({path:destination,sha256:hash(fs.readFileSync(destination)),limit:'WIP synthetic fixture, not approved-design parity or live proof'});
}
async function check(name,fn){try{const observed=await fn();checks.push({name,pass:true,observed});}catch(error){checks.push({name,pass:false,error:String(error)});}}
async function ready(page){await page.waitForFunction(()=>document.querySelector('[data-fixture]')?.dataset.fixtureReady==='true');}
async function scenario(page,name){
  await page.locator('[data-fixture-debug]').evaluate(node=>node.open=true);
  await page.locator(`input[name="stv-fixture-scenario"][value="${name}"]`).check();
  await page.waitForFunction(name=>{
    try{return !document.querySelector('[data-fixture]').hasAttribute('data-fixture-busy')&&
      JSON.parse(document.querySelector('[data-fixture-result]').textContent).action==='scenario:'+name;}
    catch{return false;}
  },name);
  const result=await page.locator('[data-fixture-result]').getAttribute('data-ok');assert.equal(result,'true');
  await page.locator('[data-fixture-debug]').evaluate(node=>node.open=false);
}
async function layout(page,name){
  await page.locator('[data-fixture-debug]').evaluate(node=>node.open=true);
  await page.locator(`input[name="stv-fixture-layout"][value="${name}"]`).check();
  await page.locator('[data-fixture-debug]').evaluate(node=>node.open=false);
}
async function secondaryReferenceCheck(page,device){
  await check(device.name+' long secondary reference clamps and expands without losing source',async()=>{
    const reference=page.locator('.stv-detail .stv-secondary').first();
    const preview=reference.locator('.stv-secondary-preview');
    const fullText=await preview.textContent();assert.ok(fullText.length>160);
    const before=await preview.evaluate(n=>({height:n.getBoundingClientRect().height,line:parseFloat(getComputedStyle(n).lineHeight),clamp:getComputedStyle(n).webkitLineClamp}));
    assert.equal(before.clamp,'3');assert.ok(before.height<=before.line*3+1);
    const summary=reference.locator('summary');await summary.focus();await page.keyboard.press('Enter');
    assert.ok(await reference.locator('details').evaluate(n=>n.open));assert.ok(!await preview.isVisible());
    assert.equal(await reference.locator('.stv-secondary-full').textContent(),fullText);
    assert.ok(await reference.getByText('Show less',{exact:true}).isVisible());
    await page.keyboard.press('Enter');assert.ok(await preview.isVisible());
    assert.ok(await reference.getByText('Show more',{exact:true}).isVisible());
    assert.ok(await summary.evaluate(n=>n===document.activeElement));return before;
  });
}
try{
  for(const device of [{name:'desktop',width:1440,height:900},{name:'tablet',width:768,height:1024},{name:'phone',width:390,height:844}]){
    const context=await browser.newContext({viewport:{width:device.width,height:device.height}});
    context.setDefaultTimeout(5000);
    const blocked=[],requests=[],errors=[];
    await context.route('**/*',async route=>{
      const url=new URL(route.request().url());requests.push(url.href);
      if(url.origin===origin&&files.has(url.pathname)){const[type,body]=files.get(url.pathname);await route.fulfill({status:200,contentType:type,body,headers:{'cache-control':'no-store'}});}
      else if(url.origin===origin&&url.pathname==='/favicon.ico'){await route.fulfill({status:204,body:''});}
      else{blocked.push(url.href);await route.abort();}
    });
    const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
    page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
    const started=Date.now();await page.goto(origin+fixture);await ready(page);
    metrics.push({device:device.name,kind:'fixture_navigation_to_ready',wall_ms:Date.now()-started,
      nodes:await page.locator('.stv *').count(),limit:'Fixture/automation observation only; no installed or field performance claim.'});
    await check(device.name+' coherent initial snapshot',async()=>{
      assert.equal(await page.locator('.stv').getAttribute('data-stv-state'),'ready');
      assert.equal(await page.locator('.stv [role="option"]').count(),6);
      assert.equal(await page.locator('.stv progress,.stv [role="progressbar"]').count(),0);
      assert.equal(await page.locator('[data-fixture-debug]').getAttribute('open'),null);
      assert.equal(await page.locator('#stv-fixture-controls').isVisible(),false);
      return '6 source rows, no measured progress invented';
    });
    await check(device.name+' horizontal containment and 44px targets',async()=>{
      const result=await page.locator('.stv').evaluate(root=>({overflow:document.documentElement.scrollWidth-innerWidth,
        targets:[...root.querySelectorAll('.stv-task-option,.stv-page-button,.stv-group-toggle')].filter(n=>n.getClientRects().length).map(n=>n.getBoundingClientRect().height)}));
      assert.ok(result.overflow<=1,JSON.stringify(result));assert.ok(result.targets.every(h=>h>=44));return result;
    });
    await check(device.name+' enclosing panel and truthful empty-center state marks',async()=>{
      const result=await page.locator('.stv').evaluate(root=>({
        panel:getComputedStyle(root.querySelector('.stv-inspector-list')).borderTopWidth,
        toolbar:getComputedStyle(root.querySelector('.stv-toolbar')).borderBottomWidth,
        marks:[...root.querySelectorAll('.stv-task-option > .stv-state-mark')].map(n=>({
          state:n.dataset.state,width:n.getBoundingClientRect().width,height:n.getBoundingClientRect().height,
          fill:getComputedStyle(n).backgroundColor,border:getComputedStyle(n).borderTopStyle,text:n.textContent,hidden:n.getAttribute('aria-hidden')})),
        unknown:root.querySelector('.stv-task-option:last-child .stv-state').textContent,
        navigation:[...root.querySelectorAll('.stv-option-chevron svg')].map(n=>n.getBoundingClientRect().width)}));
      assert.equal(result.panel,'1px');assert.equal(result.toolbar,'1px');assert.equal(result.marks.length,6);
      assert.ok(result.marks.every(n=>n.width===16&&n.height===16&&n.text===''&&n.hidden==='true'&&n.fill==='rgba(0, 0, 0, 0)'));
      assert.equal(result.marks.at(-1).state,'unknown');assert.equal(result.marks.at(-1).border,'dashed');assert.equal(result.unknown,'Unknown');
      assert.ok(result.navigation.every(w=>w===16));return result;
    });
    await check(device.name+' keyboard selection and focus',async()=>{
      await page.locator('.stv [role="option"]').first().focus();await page.keyboard.press('ArrowDown');
      const result=await page.evaluate(()=>({selected:document.querySelector('.stv [aria-selected="true"]').dataset.taskId,
        focused:document.activeElement.dataset.taskId,outline:getComputedStyle(document.activeElement).outlineStyle}));
      assert.equal(result.selected,'t-chapters');assert.equal(result.focused,'t-chapters');assert.notEqual(result.outline,'none');return result;
    });
    if(device.width>720){
      await check(device.name+' inspector list left and detail right',async()=>{
        const a=await page.locator('.stv-inspector-list').boundingBox();const b=await page.locator('.stv-detail').boundingBox();
        assert.ok(a&&b&&a.x+a.width<=b.x+1);return {list:a,detail:b};
      });
      if(device.name==='desktop')await capture(page,'desktop-inspector-1440x900');
    }
    await layout(page,'milestones');
    await page.locator('.stv-group-toggle').first().click();await page.locator('.stv-row-toggle').first().click();
    await check(device.name+' milestone disclosure and row detail',async()=>{
      assert.equal(await page.locator('.stv-group-toggle').first().getAttribute('aria-expanded'),'true');
      assert.equal(await page.locator('.stv-row-toggle').first().getAttribute('aria-expanded'),'true');
      assert.ok(await page.locator('.stv-row-detail').first().isVisible());return 'source rows expanded without write';
    });
    await check(device.name+' compact right-edge disclosures keep full touch targets',async()=>{
      const result=await page.locator('.stv-group').first().evaluate(root=>{
        const title=root.querySelector('.stv-group-title').getBoundingClientRect();
        return [...root.querySelectorAll('.stv-group-toggle,.stv-row-toggle')].map(n=>({
          width:n.getBoundingClientRect().width,height:n.getBoundingClientRect().height,
          icon:n.querySelector('svg').getBoundingClientRect().width,border:getComputedStyle(n).borderTopWidth,
          rightOfTitle:n.classList.contains('stv-group-toggle')?n.getBoundingClientRect().left>=title.right-1:true}));});
      assert.ok(result.every(n=>n.width>=44&&n.height>=44&&n.icon<=17&&n.border==='0px'&&n.rightOfTitle));
      const frames=await page.locator('.stv-milestones').evaluate(root=>{
        const groups=[...root.querySelectorAll(':scope > .stv-group')];const a=groups[0].getBoundingClientRect(),b=groups[1].getBoundingClientRect();
        const selected=root.querySelector('.stv-row.is-expanded > .stv-row-head');return {
          gap:b.top-a.bottom,radius:getComputedStyle(groups[0]).borderTopLeftRadius,border:getComputedStyle(groups[0]).borderTopWidth,
          selectedWidth:getComputedStyle(selected).outlineWidth,selectedColor:getComputedStyle(selected).outlineColor};});
      assert.ok(frames.gap>=8);assert.equal(frames.radius,'12px');assert.equal(frames.border,'1px');
      assert.equal(frames.selectedWidth,'1px');assert.equal(frames.selectedColor,'rgb(134, 184, 255)');return {targets:result,frames};
    });
    if(device.name==='tablet')await capture(page,'tablet-milestones-768x1024');
    await check(device.name+' shared inspector title, chevron and Back continuity',async()=>{
      await page.locator('.stv-group-title').first().click();
      assert.equal(await page.locator('.stv-detail').getAttribute('data-record-kind'),'milestones');
      if(device.name==='phone'){
        const origin=page.locator('.stv-origin');assert.ok(await origin.isVisible());assert.equal(await origin.getAttribute('inert'),'');
        const row=await origin.locator('.stv-group-heading').first().boundingBox();const sheet=await page.locator('.stv-detail').boundingBox();
        assert.ok(row&&sheet&&row.y+row.height<=sheet.y,'short sheet must leave its originating list visible');
        assert.equal(await page.locator('.stv [role="dialog"]').count(),1);
      }
      if(device.name==='phone')await capture(page,'phone-milestone-inspector-390x844');
      await page.locator('.stv-sheet-close').click();
      assert.equal(await page.locator('.stv-group-toggle').first().getAttribute('aria-expanded'),'true');
      await page.locator('.stv-group-title').nth(1).click();
      assert.equal(await page.locator('.stv-dependencies li').first().innerText(),'Complete first draft');
      if(device.name==='phone')await capture(page,'phone-milestone-dependency-390x844');
      await page.locator('.stv-sheet-close').click();
      await page.locator('.stv-row-title').first().click();
      assert.equal(await page.locator('.stv-detail').getAttribute('data-record-kind'),'tasks');
      if(device.name==='phone')await capture(page,'phone-task-inspector-390x844');
      await page.locator('.stv-sheet-close').click();
      assert.equal(await page.locator('.stv-row-toggle').first().getAttribute('aria-expanded'),'true');
      assert.ok(await page.locator('.stv-row-title').first().evaluate(node=>node===document.activeElement));
      return 'canonical record maps, independent expansion, same origin and focus restored';
    });
    await scenario(page,'undeclared');
    await check(device.name+' UNKNOWN is not observed zero',async()=>{
      assert.equal(await page.locator('.stv').getAttribute('data-stv-tasks'),'undeclared');
      assert.equal(await page.locator('.stv').getAttribute('data-stv-state'),'ready');
      const text=await page.locator('.stv').innerText();assert.ok(!text.includes('0 tasks'));
      assert.ok(text.includes('listed task ids')||text.includes('Tasks not declared'));return text.slice(0,350);
    });
    await check(device.name+' unknown membership keeps badge and count aligned',async()=>{
      const rows=await page.locator('.stv-group-meta').evaluateAll(nodes=>nodes.map(n=>{
        const badge=n.querySelector('.stv-state').getBoundingClientRect();const count=n.querySelector('.stv-group-count').getBoundingClientRect();
        return {difference:Math.abs(badge.y+badge.height/2-count.y-count.height/2),text:n.textContent,right:n.getBoundingClientRect().right};}));
      assert.ok(rows.length>0&&rows.every(n=>n.difference<=1&&n.right<=device.width+1));return rows;
    });
    if(device.name==='phone'){
      await page.locator('.stv').scrollIntoViewIfNeeded();
      await capture(page,'phone-unknown-390x844');
    }
    await scenario(page,'empty');
    await check(device.name+' observed empty',async()=>{assert.equal(await page.locator('.stv').getAttribute('data-stv-state'),'empty');return 'observed empty, not unknown';});
    await scenario(page,'normal');await layout(page,'inspector');
    await page.locator('[data-fixture-debug]').evaluate(node=>node.open=true);
    await page.locator('[data-fixture-test="malformed-update"]').click();
    await page.locator('[data-fixture-debug]').evaluate(node=>node.open=false);
    await check(device.name+' rejected input keeps last valid rows stale',async()=>{
      assert.equal(await page.locator('.stv').getAttribute('data-stv-state'),'stale');
      assert.ok((await page.locator('.stv').innerText()).includes('Outline chapters'));return 'last valid retained';
    });
    await scenario(page,'long');
    await check(device.name+' long text no horizontal overflow',async()=>{
      const result=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth-innerWidth,
        outside:[...document.querySelectorAll('body *')].filter(n=>n.getBoundingClientRect().right>innerWidth+1||n.scrollWidth>n.clientWidth+2).map(n=>({tag:n.tagName,class:n.className,right:n.getBoundingClientRect().right,width:n.clientWidth,scroll:n.scrollWidth}))}));
      assert.ok(result.overflow<=1,JSON.stringify(result));return result;
    });
    if(device.name!=='phone')await secondaryReferenceCheck(page,device);
    if(device.name==='phone'){
      const originalOverflow=await page.evaluate(()=>getComputedStyle(document.documentElement).overflowY);
      await page.evaluate(()=>{const spacer=document.createElement('div');spacer.id='scroll-proof-spacer';spacer.style.height='200vh';document.body.append(spacer);});
      await page.locator('.stv [role="option"]').first().click();
      await secondaryReferenceCheck(page,device);
      await check('phone sheet viewport, single body scroller and fixed close',async()=>{
        const dialog=page.locator('.stv [role="dialog"]');assert.ok(await dialog.isVisible());
        assert.equal(await page.evaluate(()=>getComputedStyle(document.documentElement).overflowY),'hidden');
        await dialog.locator('.stv-technical').evaluate(node=>node.open=true);
        const result=await dialog.evaluate(root=>{const rect=root.getBoundingClientRect();return {top:rect.top,bottom:rect.bottom,right:rect.right,
          scrollers:[...root.querySelectorAll('*')].filter(n=>n.scrollHeight>n.clientHeight+1&&['auto','scroll'].includes(getComputedStyle(n).overflowY)).map(n=>n.className)};});
        assert.ok(result.top>=0&&result.bottom<=device.height+1&&result.right<=device.width+1);
        assert.deepEqual(result.scrollers,['stv-task-detail']);
        const close=await page.locator('.stv-sheet-close').boundingBox();
        const title=await page.locator('.stv-sheet-title').boundingBox();
        await page.locator('.stv-detail--sheet > .stv-task-detail').evaluate(n=>n.scrollTop=n.scrollHeight);
        const after=await page.locator('.stv-sheet-close').boundingBox();assert.ok(close&&after&&Math.abs(close.y-after.y)<=1);
        const titleAfter=await page.locator('.stv-sheet-title').boundingBox();assert.ok(title&&titleAfter&&Math.abs(title.y-titleAfter.y)<=1);
        await dialog.locator('.stv-technical').evaluate(node=>node.open=false);
        await dialog.locator('.stv-task-detail').evaluate(node=>node.scrollTop=0);
        return result;
      });
      await check('phone background wheel blocked only while sheet mounted',async()=>{
        const before=await page.evaluate(()=>scrollY);
        await page.mouse.move(5,5);await page.mouse.wheel(0,300);
        await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
        assert.equal(await page.evaluate(()=>scrollY),before);
        return 'outside wheel leaves background position unchanged; host inline styles untouched';
      });
      await capture(page,'phone-sheet-long-390x844');
      await check('phone sheet Tab confinement and Escape return',async()=>{
        await page.locator('.stv-sheet-close').focus();await page.keyboard.press('Shift+Tab');
        assert.ok(await page.locator('.stv [role="dialog"]').evaluate(n=>n.contains(document.activeElement)));
        await page.keyboard.press('Tab');assert.ok(await page.locator('.stv-sheet-close').evaluate(n=>n===document.activeElement));
        await page.keyboard.press('Escape');assert.ok(!await page.locator('.stv [role="dialog"]').isVisible());
        assert.equal(await page.evaluate(()=>getComputedStyle(document.documentElement).overflowY),originalOverflow);
        const result=await page.evaluate(()=>({role:document.activeElement.getAttribute('role'),selected:document.activeElement.getAttribute('aria-selected')}));
        assert.deepEqual(result,{role:'option',selected:'true'});
        const scroll=await page.evaluate(()=>scrollY);await page.mouse.move(5,5);await page.mouse.wheel(0,200);
        await page.waitForFunction(before=>scrollY>before,scroll);
        return result;
      });
      await page.evaluate(()=>document.getElementById('scroll-proof-spacer').remove());
    }
    await scenario(page,'large');
    await check(device.name+' large list bounded rendering and next page',async()=>{
      assert.equal(await page.locator('.stv [role="option"]').count(),40);
      assert.equal(await page.locator('.stv-task-detail').count(),1);
      await page.locator('.stv-page-button').filter({hasText:'Next'}).click();
      assert.ok((await page.locator('.stv [role="option"]').first().innerText()).includes('Synthetic task 41'));
      return {visibleRows:await page.locator('.stv [role="option"]').count(),nodes:await page.locator('.stv *').count()};
    });
    await page.emulateMedia({reducedMotion:'reduce'});
    await check(device.name+' reduced motion',async()=>{
      const durations=await page.locator('.stv-page-button').evaluateAll(nodes=>nodes.map(n=>getComputedStyle(n).transitionDuration));assert.ok(durations.every(d=>d==='0s'));return durations;
    });
    await check(device.name+' verified kit fallback tokens',async()=>{
      const result=await page.locator('.stv').evaluate(n=>({background:getComputedStyle(n).backgroundColor,color:getComputedStyle(n).color,
        blue:getComputedStyle(n).getPropertyValue('--stv-blue').trim()}));
      assert.equal(result.background,'rgb(9, 19, 33)');assert.equal(result.color,'rgb(244, 248, 255)');assert.equal(result.blue.toLowerCase(),'#86b8ff');return result;
    });
    await check(device.name+' no console/runtime or external requests',async()=>{assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);return {requests,errors};});
    await context.close();
  }
}finally{await browser.close();}

const results=[...apiResults,...continuityResults,...checks];
const receipt={status:results.every(row=>row.pass)?'PASS_SOURCE_FIXTURE':'FAIL_SOURCE_FIXTURE',
  inputs:{js:hash(js),css:hash(css),html:hash(html)},
  passed:results.filter(row=>row.pass).length,total:results.length,
  failures:results.filter(row=>!row.pass),metrics,screenshots,
  referenceContinuity:continuityResults,
  limits:['Synthetic isolated browser only','Scroll lock is scoped CSS on mounted narrow sheets; transformed host ancestors unverified',
    'Shared inspector and presentation correction require fresh independent source/visual review',
    'No selected-reference pixel fidelity, package, live, or real-project admission']};
console.log(JSON.stringify(receipt,null,2));
process.exitCode=receipt.passed===receipt.total?0:1;
