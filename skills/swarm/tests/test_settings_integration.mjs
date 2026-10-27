// Actual official SDK -> MCP stdio -> App -> temporary config/SQLite authority.
// Only the outer host message relay and host roster are local test fixtures.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {spawn, execFileSync} from 'node:child_process';
import {createInterface} from 'node:readline';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const require = createRequire(path.join(repo, 'console/package.json'));
const {chromium} = require('playwright');
const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'swarm-settings-integration-'));
const python = process.env.PYTHON || 'python';
const fixture = JSON.parse(execFileSync(python, ['-B', 'skills/swarm/tests/settings_integration_fixture.py', scratch], {cwd:repo,encoding:'utf8'}));
let child, sequence = 0, pending = new Map(), drop = false, calls = [], reads = [], checks = 0;
function start() {
  child = spawn(python, ['-B', 'skills/swarm/scripts/swarm_mcp.py', '--stdio'], {cwd:repo,env:{...process.env,
    SWARM_CONFIG_PATH:path.join(scratch,'fixtures/swarm/config.toml'), CODEX_HOME:path.join(scratch,'fixtures/codex'),
    SWARM_MCP_TELEMETRY_PATH:path.join(scratch,'telemetry.jsonl')},stdio:['pipe','pipe','pipe']});
  child.stderr.on('data', data=>process.stderr.write(data));
  createInterface({input:child.stdout}).on('line', line=>{const value=JSON.parse(line);const resolve=pending.get(value.id);if(resolve){pending.delete(value.id);resolve(value);}});
}
async function stop(){if(!child||child.exitCode!==null)return; const exited=new Promise(resolve=>child.once('exit',resolve));child.stdin.end();await exited;}
function rpc(params) {return new Promise(resolve=>{const id=++sequence;pending.set(id,resolve);child.stdin.write(JSON.stringify({jsonrpc:'2.0',id,method:'tools/call',params})+'\n');});}
start();
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
try {
  const page=await browser.newPage({viewport:{width:1200,height:960}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});page.on('requestfailed',request=>errors.push(request.url()));
  await page.exposeFunction('backend',async params=>{
    const response=await rpc(params);
    if(params.name==='swarm_settings_read')reads.push(response.result);
    if(params.name==='swarm_settings_save'){calls.push({params,result:response.result});if(drop)return {isError:true,content:[{type:'text',text:'Fixture: applied acknowledgement lost'}]};}
    return response.result;
  });
  if (process.argv.includes('--source-settings-only')) {
    // Current leased module + retained production shell, real MCP/App/config.
    // No compiled bundle replacement, SDK/native host placement or user settings claim.
    const roster=(await rpc({name:'swarm_projects',arguments:{}})).result.structuredContent;
    assert.equal(roster.available,true);assert.ok(roster.cursor);checks++;
    const project=roster.projects.find(p=>p.id==='project:alpha');assert.ok(project);
    const projectScope={type:'project',project_id:project.id,accepted_cursor:roster.cursor};
    const source=fs.readFileSync(path.join(repo,'skills/swarm/assets/ui/swarm-settings.js'),'utf8');
    const css=fs.readFileSync(path.join(repo,'skills/swarm/assets/ui/swarm-settings.css'),'utf8');
    const legacy=fs.readFileSync(path.join(repo,'console/static/app.js'),'utf8');
    const editor=legacy.slice(legacy.indexOf('function configTomlLiteral('),legacy.indexOf('function configWriteRequest('));
    const shell=fs.readFileSync(path.join(scratch,'rendered.html'),'utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'');
    const hostState=()=>execFileSync(python,['-B','-c',`import sqlite3,json,sys;from pathlib import Path;p=next(Path(sys.argv[1]).rglob('state_*.sqlite'));c=sqlite3.connect(p);print(json.dumps(c.execute('select * from threads order by id').fetchall()))`,scratch],{cwd:repo,encoding:'utf8'});
    const beforeHost=hostState();
    await page.route('https://swarm-integration.invalid/**',route=>route.fulfill({contentType:'text/html',body:shell}));
    await page.goto('https://swarm-integration.invalid/');
    await page.addStyleTag({content:css});
    await page.addScriptTag({content:editor});
    await page.addScriptTag({type:'module',content:source+`
      document.querySelector('#main').hidden=true;
      const page=document.createElement('main');page.id='settings-page';
      const close=document.createElement('button');close.textContent='×';close.className='icon-action';close.setAttribute('aria-label','Close settings');
      const root=document.createElement('section');page.append(close,root);document.querySelector('.hq-footer').before(page);
      document.querySelector('#settings').classList.add('selected');document.querySelector('#all-projects').classList.remove('selected');
      const roster=${JSON.stringify(roster)};const nav=document.querySelector('#project-nav');nav.replaceChildren();
      for(const p of roster.projects){const row=document.createElement('p');row.textContent=p.name;nav.append(row);}
      window.settings=mountSettings(root,{app:{callServerTool:window.backend},scopes:[{label:${JSON.stringify(project.name)},scope:${JSON.stringify(projectScope)}}],editText:configTextWithChanges});
      await window.settings.ready;window.ready=true;
    `});
    await page.waitForFunction(()=>window.ready);
    const root=page.locator('.swarm-settings'),status=root.getByRole('status');
    await root.getByRole('button',{name:'Advanced',exact:true}).click();
    const template=root.getByLabel('Controllers Title template',{exact:true});
    assert.equal(await template.inputValue(),'{project}');checks++;
    for(const category of ['Controllers','Units','Leads','Workers']) {
      assert.equal(await root.getByLabel(`${category} Auto-pin`,{exact:true}).isChecked(),false);
      assert.equal(await root.getByLabel(`${category} Show emoji`,{exact:true}).isChecked(),true);checks++;
    }
    const evidence=process.env.SWARM_SETTINGS_EVIDENCE;
    for(const [name,width,height] of [['desktop',1440,1000],['tablet',834,1112],['mobile',390,844]]) {
      await page.setViewportSize({width,height});await page.emulateMedia({colorScheme:'dark'});
      assert.equal(await page.locator('html').evaluate(el=>el.scrollWidth<=innerWidth),true);checks++;
      assert.match(await root.evaluate(el=>getComputedStyle(el).fontFamily),/system-ui|sans-serif/);checks++;
      assert.equal(await root.locator('h1').evaluate(el=>getComputedStyle(el).fontFamily.includes('Times')),false);checks++;
      const geometry=await root.evaluate(el=>{const content=el.getBoundingClientRect(),footer=document.querySelector('.hq-footer').getBoundingClientRect();return {bottom:content.bottom,footerTop:footer.top,font:getComputedStyle(el.querySelector('h1')).fontFamily};});
      assert.ok(geometry.bottom<=geometry.footerTop+1,JSON.stringify(geometry));checks++;
      for(const input of await root.locator('[data-naming] input').all())assert.ok((await input.boundingBox()).height>=44);checks++;
      if(evidence){fs.mkdirSync(evidence,{recursive:true});await page.locator('body').evaluate(el=>el.scrollTop=0);await page.screenshot({path:path.join(evidence,`naming-source-backend-${name}.png`)});await page.screenshot({path:path.join(evidence,`naming-source-backend-${name}-full.png`),fullPage:true});if(name==='mobile'){await root.getByLabel('Units Title template',{exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:path.join(evidence,'naming-source-backend-mobile-controls.png')});}}
    }
    assert.match(await root.locator('#naming-availability').textContent(),/unavailable until host support is verified/);checks++;
    for(const category of ['Controllers','Units','Leads','Workers'])for(const label of ['Title template','Show emoji','Auto-pin'])assert.equal(await root.getByLabel(`${category} ${label}`,{exact:true}).isDisabled(),true);checks++;
    assert.equal(calls.length,0);checks++;
    await root.getByRole('button',{name:'Essentials',exact:true}).click();
    const fast=root.getByLabel('Fast',{exact:true});const fastValue=await fast.isChecked();await fast.setChecked(!fastValue);
    await root.getByRole('button',{name:'Save changes',exact:true}).click();await status.filter({hasText:'Saved.'}).waitFor();
    assert.equal(await status.textContent(),'Saved.');checks++;
    const saved=calls.at(-1);assert.deepEqual(Object.keys(saved.params.arguments).sort(),['acknowledge','expected_revision','operation_id','scope','text']);checks++;
    assert.equal(saved.result.structuredContent.effective_settings.execution.fast_mode,!fastValue);checks++;
    await stop();start();await root.getByRole('button',{name:'Reload',exact:true}).click();await status.filter({hasText:'Preferences loaded'}).waitFor();
    assert.equal(await fast.isChecked(),!fastValue);checks++;
    await root.getByLabel('Settings scope').selectOption('1');await status.filter({hasText:'Preferences loaded'}).waitFor();
    assert.deepEqual(reads.at(-1).structuredContent.scope,projectScope);checks++;
    const saver=root.getByLabel('Usage Saver',{exact:true});const saverValue=await saver.isChecked();await saver.setChecked(!saverValue);
    drop=true;await root.getByRole('button',{name:'Save changes',exact:true}).click();await root.getByRole('button',{name:'Retry save',exact:true}).waitFor();
    assert.equal(await saver.isChecked(),!saverValue);checks++;
    await stop();start();drop=false;
    await root.getByRole('button',{name:'Retry save',exact:true}).click();await status.filter({hasText:'Saved.'}).waitFor();
    assert.deepEqual(calls.at(-1).params.arguments,calls.at(-2).params.arguments);assert.equal(calls.at(-1).result.structuredContent.mutation_receipt.replayed,true);checks++;
    await stop();start();await root.getByRole('button',{name:'Reload',exact:true}).click();await status.filter({hasText:'Preferences loaded'}).waitFor();
    assert.equal(await saver.isChecked(),!saverValue);checks++;
    const snapshot=reads.at(-1).structuredContent;
    const changed=await page.evaluate(text=>configTextWithChanges(text,{'lifecycle.pin_created_workers':true}),snapshot.editable_text);
    const external=await rpc({name:'swarm_settings_save',arguments:{scope:projectScope,expected_revision:snapshot.revision,acknowledge:true,text:changed,operation_id:'fixture-external-writer'}});
    assert.equal(external.result.structuredContent.mutation_receipt.accepted,true);checks++;
    await saver.setChecked(saverValue);await root.getByRole('button',{name:'Save changes',exact:true}).click();await status.filter({hasText:'preserved'}).waitFor();
    assert.equal(await saver.isChecked(),saverValue);assert.doesNotMatch(await status.textContent(),/Saved\./);checks++;
    const invalidText=await page.evaluate(text=>configTextWithChanges(text,{'task_titles.unit_template':'{private.path}'}),changed);
    const invalid=await rpc({name:'swarm_settings_save',arguments:{scope:projectScope,expected_revision:external.result.structuredContent.revision,acknowledge:true,text:invalidText,operation_id:'fixture-invalid-naming'}});
    assert.equal(invalid.result.isError,true);checks++;
    assert.equal(hostState(),beforeHost);checks++;
    assert.deepEqual(errors,[]);checks++;
    console.log(JSON.stringify({status:'PASS_SOURCE_MODULE_REAL_MCP_CONFIG',checks,limits:['Retained shell with source module mounted by test; not composed SDK/native placement','Temporary config/SQLite only; no user titles or pins mutated','Full compiled SDK regression still required after Source bundle integration']}));
  } else {
  await page.route('https://swarm-integration.invalid/**',route=>route.fulfill({contentType:'text/html',body:route.request().url().endsWith('/app')?fs.readFileSync(path.join(scratch,'rendered.html'),'utf8'):`<!doctype html><style>body{margin:0}iframe{display:block;border:0;width:100%;height:100dvh}</style><iframe title="HQ" src="/app"></iframe><script>
    window.handshakes=0;addEventListener('message',async event=>{const request=event.data;if(!request?.id && request?.id!==0)return;let result;
    if(request.method==='ui/initialize'){window.handshakes++;result={protocolVersion:request.params.protocolVersion,hostInfo:{name:'isolated-test-host',version:'1'},hostCapabilities:{serverTools:{}},hostContext:{theme:'dark'}};}
    else if(request.method==='tools/call')result=await window.backend(request.params);else return;
    event.source.postMessage({jsonrpc:'2.0',id:request.id,result},event.origin);
    });</script>`}));
  await page.goto('https://swarm-integration.invalid/');
  const frame=page.frameLocator('iframe');
  await frame.getByRole('button',{name:'Settings',exact:true}).click();
  await frame.getByRole('status').filter({hasText:'Preferences loaded'}).waitFor();
  assert.equal(await page.evaluate(()=>window.handshakes),1);checks++;
  assert.equal(reads.at(-1).structuredContent.state,'KNOWN');checks++;
  assert.equal(await frame.getByRole('navigation',{name:'Saved projects'}).isVisible(),true);checks++;
  assert.equal(await frame.locator('dialog').count(),1); // Existing closed project inspector only; Settings is a page.
  assert.equal(await frame.locator('#settings-page').isVisible(),true);checks++;
  assert.equal(await frame.locator('#settings').getAttribute('aria-current'),'page');
  assert.equal(await frame.locator('#all-projects').evaluate(el=>el.classList.contains('selected')),false);checks++;
  await frame.getByLabel('Model order',{exact:true}).fill('gpt-6-luna, gpt-6-sol, gpt-6-astra');
  await frame.getByLabel('Model order',{exact:true}).blur();
  await frame.getByLabel('Minimum model',{exact:true}).selectOption('gpt-6-astra');
  await frame.getByLabel('Default model',{exact:true}).selectOption('gpt-6-sol');
  await frame.getByLabel('Maximum model',{exact:true}).selectOption('gpt-6-astra');
  await frame.getByRole('button',{name:'Save changes',exact:true}).click();
  await frame.getByRole('status').filter({hasText:'within the supported minimum'}).waitFor();
  assert.equal(calls.length,0);checks++;
  await frame.getByLabel('Minimum model',{exact:true}).selectOption('gpt-6-luna');
  await frame.getByLabel('Reasoning',{exact:true}).selectOption('high');
  await frame.getByRole('button',{name:'Save changes',exact:true}).click();
  await frame.getByRole('status').filter({hasText:'Saved.'}).waitFor();
  const effective=calls.at(-1).result.structuredContent.effective_settings;
  const routed=JSON.parse(execFileSync(python,['-B','-c',`import sys,json;from pathlib import Path;sys.path.insert(0,'skills/swarm/scripts');import swarm_config as c;print(json.dumps(c.resolve_model_assignment(c.load(Path(sys.argv[1]))[0],'lead',surface='codex_task')))`,path.join(scratch,'fixtures/swarm/config.toml')],{cwd:repo,encoding:'utf8'}));
  // The real fixture template explicitly selects Sol/Medium for LEAD. The
  // newly saved automatic High default must not overwrite that explicit pair.
  assert.match(fs.readFileSync(path.join(scratch,'fixtures/swarm/config.toml'),'utf8'),/lead_reasoning = "medium"/);
  assert.equal(routed.model,'gpt-6-sol');assert.equal(routed.reasoning_effort,'medium');checks++;
  assert.equal(routed.actual_model_verification,'UNVERIFIED');checks++;
  await stop();start();
  await frame.getByRole('button',{name:'Reload',exact:true}).click();
  await frame.getByRole('status').filter({hasText:'Preferences loaded'}).waitFor();
  assert.equal(await frame.getByLabel('Default model',{exact:true}).inputValue(),'gpt-6-sol');
  assert.equal(await frame.getByLabel('Minimum model',{exact:true}).inputValue(),'gpt-6-luna');
  assert.equal(await frame.getByLabel('Maximum model',{exact:true}).inputValue(),'gpt-6-astra');
  assert.equal(await frame.getByLabel('Reasoning',{exact:true}).inputValue(),'high');checks++;
  const fast=frame.getByLabel('Fast',{exact:true});const original=await fast.isChecked();
  await fast.setChecked(!original);
  await frame.getByRole('button',{name:'Save changes',exact:true}).click();
  await frame.getByRole('status').filter({hasText:'Saved.'}).waitFor();
  assert.equal(calls.at(-1).result.structuredContent.mutation_receipt.accepted,true);checks++;
  await stop();start();
  await frame.getByRole('button',{name:'Reload',exact:true}).click();
  await frame.getByRole('status').filter({hasText:'Preferences loaded'}).waitFor();
  assert.equal(await fast.isChecked(),!original);checks++;
  const scope=frame.getByLabel('Settings scope');
  assert.ok(await scope.locator('option').count()>1);checks++;
  await scope.selectOption('1');
  await frame.getByRole('status').filter({hasText:'Preferences loaded'}).waitFor();
  assert.equal(reads.at(-1).structuredContent.scope.type,'project');checks++;
  await frame.getByLabel('Default model',{exact:true}).selectOption('gpt-6-astra');
  await frame.getByRole('button',{name:'Save changes',exact:true}).click();
  await frame.getByRole('status').filter({hasText:'Saved.'}).waitFor();
  await stop();start();
  await frame.getByRole('button',{name:'Reload',exact:true}).click();
  await frame.getByRole('status').filter({hasText:'Preferences loaded'}).waitFor();
  assert.equal(await frame.getByLabel('Default model',{exact:true}).inputValue(),'gpt-6-astra');checks++;
  await scope.selectOption('0');
  await frame.getByRole('status').filter({hasText:'Preferences loaded'}).waitFor();
  assert.equal(await frame.getByLabel('Default model',{exact:true}).inputValue(),'gpt-6-sol');checks++;
  await scope.selectOption('1');
  await frame.getByRole('status').filter({hasText:'Preferences loaded'}).waitFor();
  const saver=frame.getByLabel('Usage Saver',{exact:true});await saver.setChecked(!(await saver.isChecked()));
  drop=true;
  await frame.getByRole('button',{name:'Save changes',exact:true}).click();
  await frame.getByRole('button',{name:'Retry save',exact:true}).waitFor();
  await stop();start();
  await frame.getByRole('button',{name:'Retry save',exact:true}).click();
  await frame.getByRole('status').filter({hasText:'Reload to reconcile'}).waitFor();
  // SDK progressToken identifies the transport call, not the immutable config operation.
  assert.equal(calls.at(-1).params.name,calls.at(-2).params.name);
  assert.deepEqual(calls.at(-1).params.arguments,calls.at(-2).params.arguments);checks++;
  assert.equal(calls.at(-1).result.structuredContent.mutation_receipt.replayed,true);checks++;
  const count=calls.length;drop=false;
  await frame.getByRole('button',{name:'Reload',exact:true}).click();
  await frame.getByRole('status').filter({hasText:'Current settings match'}).waitFor();
  assert.equal(calls.length,count);checks++;
  assert.equal(await scope.isEnabled(),true);checks++;
  if(process.env.SWARM_SETTINGS_EVIDENCE) {
    fs.mkdirSync(process.env.SWARM_SETTINGS_EVIDENCE,{recursive:true});
    for(const [name,width,height] of [['desktop',1200,960],['mobile',390,844]]) {
      await page.setViewportSize({width,height});
      assert.equal(await frame.locator('html').evaluate(el=>el.scrollWidth<=innerWidth),true);checks++;
      await frame.locator('.swarm-settings').evaluate(el=>{el.scrollTop=0});
      assert.equal(await frame.getByRole('button',{name:'Close settings',exact:true}).evaluate(el=>{
        const r=el.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight;
      }),true);checks++;
      const screenshot=path.join(process.env.SWARM_SETTINGS_EVIDENCE,`integrated-settings-${name}.png`);
      await frame.locator('body').screenshot({path:screenshot});
      const identity=createHash('sha256').update(fs.readFileSync(screenshot)).digest('hex').slice(0,16);
      execFileSync(python,['-B','skills/swarm/scripts/swarm_proof.py',screenshot,'--evidence-id',`settings-integrated-${name}-${identity}`,'--task-id','01a02240-41f5-7f30-aac9-358b4e8d2813','--kind','screenshot','--caption','Local official SDK/MCP/backend integration fixture, not native host placement'],{cwd:repo});
      if(name==='mobile') {
        await frame.getByLabel('Default model',{exact:true}).scrollIntoViewIfNeeded();
        await frame.locator('.swarm-settings').evaluate(el=>{el.scrollTop=el.querySelector('[data-key="execution.default_model"]').closest('.settings-row').offsetTop-el.offsetTop});
        const detail=path.join(process.env.SWARM_SETTINGS_EVIDENCE,'integrated-settings-models-mobile.png');
        await frame.locator('body').screenshot({path:detail});
        const digest=createHash('sha256').update(fs.readFileSync(detail)).digest('hex').slice(0,16);
        execFileSync(python,['-B','skills/swarm/scripts/swarm_proof.py',detail,'--evidence-id',`settings-models-mobile-${digest}`,'--task-id','01a02240-41f5-7f30-aac9-358b4e8d2813','--kind','screenshot','--caption','Composed Settings model controls, local SDK/backend proof with isolated roster'],{cwd:repo});
      }
    }
  }
  await frame.getByRole('button',{name:'Close settings',exact:true}).click();
  assert.equal(await frame.getByRole('button',{name:'Settings',exact:true}).evaluate(el=>el===document.activeElement),true);checks++;
  await frame.getByRole('button',{name:'Settings',exact:true}).click();
  await page.keyboard.press('Escape');
  assert.equal(await frame.getByRole('button',{name:'Settings',exact:true}).evaluate(el=>el===document.activeElement),true);checks++;
  assert.deepEqual(errors,[]);checks++;
  console.log(JSON.stringify({status:'PASS_LOCAL_INTEGRATED',checks,...fixture,limits:['Outer host simulated; no native placement, user-config mutation or model-policy acceptance']}));
  }
} finally {await browser.close();await stop();fs.rmSync(scratch,{recursive:true,force:true});}
