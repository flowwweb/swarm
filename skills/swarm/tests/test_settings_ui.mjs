// Isolated browser + fake MCP authority. No native, provider or live-config claim.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const require = createRequire(path.join(repo, 'console/package.json'));
const {chromium} = require('playwright');
const source = fs.readFileSync(path.join(repo, 'skills/swarm/assets/ui/swarm-settings.js'), 'utf8');
const css = fs.readFileSync(path.join(repo, 'skills/swarm/assets/ui/swarm-settings.css'), 'utf8');
const legacy = fs.readFileSync(path.join(repo, 'console/static/app.js'), 'utf8');
// Reuse the production canonical-text editor without copying another TOML editor.
const editor = legacy.slice(legacy.indexOf('function configTomlLiteral('), legacy.indexOf('function configWriteRequest('));
const browser = await chromium.launch({headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
const evidence = process.env.SWARM_SETTINGS_EVIDENCE;
let checks = 0;
try {
  const page = await browser.newPage({viewport: {width: 1200, height: 960}});
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.route('https://swarm-settings.invalid/**', route => route.fulfill({contentType:'text/html',body:'<style>body{margin:0;background:#07131d}</style><main></main>'}));
  await page.goto('https://swarm-settings.invalid/');
  await page.addStyleTag({content: css});
  await page.addScriptTag({content: editor});
  await page.addScriptTag({type: 'module', content: source + `
    const base = {state:'KNOWN', available:true, scope:{type:'global'}, revision:'a'.repeat(64), editable_text:'[execution]\\nfast_mode = true\\nusage_saver = false\\n[models.medium]\\ntask_model = "observed-model"\\ntask_reasoning = "medium"\\n', write_contract:{method:'POST'}, effective_settings:{execution:{usage_profile:'medium',fast_mode:true,usage_saver:false},models:{medium:{task_model:'observed-model',task_reasoning:'medium'}}}, descriptors:['execution.fast_mode','execution.usage_saver','models.medium.task_model','models.medium.task_reasoning'].map(key=>({key,editable:true}))};
    window.current=structuredClone(base); window.calls=[]; window.fail=false; window.wrong=false;
    const app={callServerTool:async ({name,arguments:args})=>{
      if(name==='swarm_settings_read'){
        if(window.readFailure==='transport')throw new Error('Read unavailable');
        const value={...structuredClone(window.current),scope:args.scope};
        if(window.readFailure==='unknown')value.state='UNKNOWN';
        if(window.readFailure==='scope')value.scope={type:'project',project_id:'wrong'};
        if(window.readFailure==='revision')value.revision='invalid';
        return {structuredContent:value};
      }
      window.calls.push(structuredClone(args)); if(window.fail)throw new Error('Connection interrupted. Your changes are preserved.');
      const next=structuredClone(window.current); next.scope=args.scope; next.revision='b'.repeat(64);
      next.editable_text=args.text; next.effective_settings.execution.fast_mode=/fast_mode = true/.test(args.text);
      next.effective_settings.execution.usage_saver=/usage_saver = true/.test(args.text);
      next.mutation_receipt={action:'config_update',accepted:true,acknowledged:true,replayed:false,scope:args.scope,operation_id:window.wrong?'wrong':args.operation_id,expected_revision:args.expected_revision,new_revision:next.revision};
      window.current=next;return {structuredContent:structuredClone(next)};
    }};
    window.mount=()=>mountSettings(document.querySelector('main'),{app,scopes:[{label:'SWARM project',scope:{type:'project',project_id:'swarm',accepted_cursor:'exact-cursor'}}],hostModels:[{id:'observed-model',reasoning:['low','medium','high']}],editText:configTextWithChanges});
    window.settings=window.mount();
    await window.settings.ready;window.ready=true;
  `});
  await page.waitForFunction(() => window.ready);
  assert.equal(await page.getByLabel('Fast', {exact: true}).isChecked(), true); checks++;
  assert.equal(await page.getByLabel('Minimum model', {exact:true}).isDisabled(), true); checks++;
  assert.equal(await page.getByLabel('Maximum model', {exact:true}).isDisabled(), true); checks++;
  await page.getByLabel('Fast', {exact:true}).uncheck();
  await page.getByRole('button', {name:'Revert',exact:true}).click();
  assert.equal(await page.getByLabel('Fast',{exact:true}).isChecked(),true); checks++;
  await page.getByLabel('Fast',{exact:true}).uncheck();
  await page.getByRole('button',{name:'Save changes',exact:true}).click();
  await page.getByRole('status').filter({hasText:'Saved.'}).waitFor();
  await page.getByRole('button',{name:'Reload',exact:true}).click();
  await page.getByRole('status').filter({hasText:'Preferences loaded'}).waitFor();
  assert.equal(await page.getByLabel('Fast',{exact:true}).isChecked(),false); checks++;
  await page.getByLabel('Fast',{exact:true}).check();
  for(const failure of ['transport','unknown','scope','revision']) {
    await page.evaluate(value=>{window.readFailure=value},failure);
    await page.getByRole('button',{name:'Reload',exact:true}).click();
    await page.waitForFunction(()=>!document.querySelector('[data-reload]').disabled);
    assert.equal(await page.getByRole('button',{name:'Save changes',exact:true}).isDisabled(),true);checks++;
    assert.equal(await page.getByLabel('Fast',{exact:true}).isChecked(),true);checks++;
    assert.equal((await page.evaluate(()=>window.calls)).length,1);checks++;
  }
  await page.evaluate(()=>{window.readFailure=null});
  await page.getByRole('button',{name:'Reload',exact:true}).click();
  await page.getByRole('status').filter({hasText:'unsaved changes are preserved'}).waitFor();
  assert.equal(await page.getByRole('button',{name:'Save changes',exact:true}).isEnabled(),true);checks++;
  await page.getByRole('button',{name:'Revert',exact:true}).click();
  await page.getByLabel('Settings scope').selectOption('1');
  await page.getByRole('status').filter({hasText:'Preferences loaded'}).waitFor();
  await page.getByLabel('Usage Saver',{exact:true}).check();
  await page.evaluate(()=>{window.fail=true});
  await page.getByRole('button',{name:'Save changes',exact:true}).click();
  await page.getByRole('button',{name:'Retry save',exact:true}).waitFor();
  await page.getByRole('button',{name:'Retry save',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('[type=submit]').disabled);
  const calls=await page.evaluate(()=>window.calls);
  assert.deepEqual(calls[1],calls[2]); assert.equal(calls.length,3); checks++;
  assert.equal(calls[1].scope.project_id,'swarm'); assert.equal(calls[1].scope.accepted_cursor,'exact-cursor'); checks++;
  assert.equal(await page.getByLabel('Usage Saver',{exact:true}).isChecked(),true); checks++;
  await page.getByRole('button',{name:'Reload',exact:true}).click();
  await page.getByRole('status').filter({hasText:'uncertain'}).waitFor();
  assert.equal(await page.getByRole('button',{name:'Retry save',exact:true}).isDisabled(),true); checks++;
  for(const [name,width,height] of [['desktop',1200,960],['mobile',390,844]]) {
    await page.setViewportSize({width,height});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true); checks++;
    if(evidence){fs.mkdirSync(evidence,{recursive:true});await page.screenshot({path:path.join(evidence,`settings-${name}.png`),fullPage:true});}
  }
  await page.evaluate(async()=>{window.fail=false;window.wrong=true;await window.mount().ready;});
  await page.getByLabel('Fast',{exact:true}).check();
  await page.getByRole('button',{name:'Save changes',exact:true}).click();
  await page.getByRole('status').filter({hasText:'receipt did not match'}).waitFor();
  assert.equal(await page.getByLabel('Fast',{exact:true}).isChecked(),true);checks++;
  assert.equal(await page.getByRole('button',{name:'Revert',exact:true}).isDisabled(),true);checks++;
  assert.equal(await page.getByLabel('Settings scope').isDisabled(),true);checks++;
  assert.deepEqual(errors,[]);checks++;
  console.log(JSON.stringify({status:'PASS_FIXTURE_ONLY',checks,limits:['No native host, real persistence, supported model bounds or full-page integration proof']}));
} finally {await browser.close();}
