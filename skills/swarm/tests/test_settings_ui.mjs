// Isolated browser + fake MCP authority. No native, provider or live-config claim.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const require = createRequire(path.join(repo, 'console/package.json'));
const {chromium} = require('playwright');
const source = fs.readFileSync(path.join(repo, 'skills/swarm/assets/ui/swarm-settings.js'), 'utf8');
const css = fs.readFileSync(path.join(repo, 'skills/swarm/assets/ui/swarm-settings.css'), 'utf8');
// Use the production host palette without importing unrelated full-page layout.
const theme = fs.readFileSync(path.join(repo, 'skills/swarm/assets/ui/swarm-hq-host.css'), 'utf8').match(/^:root\{[^}]+\}/)[0];
const legacy = fs.readFileSync(path.join(repo, 'console/static/app.js'), 'utf8');
// Reuse the production canonical-text editor without copying another TOML editor.
const editor = legacy.slice(legacy.indexOf('function configTomlLiteral('), legacy.indexOf('function configWriteRequest('));
const namingContract = JSON.parse(execFileSync(process.env.PYTHON || 'python', ['-B','-c', `
import sys,json
sys.path.insert(0,'skills/swarm/scripts')
import swarm_config as c
base=c.merge({})
values=dict(project='Example project',unit='Interface Lab',role='Designer',responsibility='UI')
templates=[*base['task_titles'].values()]
templates=[t for t in templates if isinstance(t,str)]+['{project} · {role} · {created:MMM D}','{{project}} {project}','{{{project}}}','1️⃣ {project}','#⃣ {project}','*️⃣ {project}','👩‍💻 {project}','🇹🇭 {project}','1 {project}','{project:}','{role} · {responsibility}','{private.path}','{project!r}','{project:>99}','{created}','{created:%Y}','{','}','{project}'+chr(0x2028)+'{role}','{project}'+chr(0x2029)+'{role}','x'*161,'','  ']
cases=[]
for template in templates:
 for enabled in [True,False]:
  cfg=c.merge({'task_titles':{'controller_template':template},'role_icons':{'enabled':enabled}})
  try:result=c.resolve_task_presentation(cfg,'controller',**values,created='2026-10-27',emoji='📋')['title'];error=False
  except c.ConfigError:result=None;error=True
  cases.append(dict(template=template,values=values,enabled=enabled,emoji='📋',result=result,error=error))
print(json.dumps(dict(settings={key:base[key] for key in ['task_titles','role_icons','lifecycle']},cases=cases)))
`], {cwd:repo,encoding:'utf8'}));
const browser = await chromium.launch({headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
const evidence = process.env.SWARM_SETTINGS_EVIDENCE;
let checks = 0;
try {
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}, colorScheme:'dark', hasTouch:true});
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.route('https://swarm-settings.invalid/**', route => route.fulfill({contentType:'text/html',body:'<style>body{margin:0;background:#07131d}</style><main></main>'}));
  await page.goto('https://swarm-settings.invalid/');
  await page.addStyleTag({content: theme + css});
  await page.addScriptTag({content: editor});
  await page.addScriptTag({type: 'module', content: source + `
    const base = {state:'KNOWN', available:true, scope:{type:'global'}, revision:'a'.repeat(64), editable_text:'[execution]\\nfast_mode = true\\nusage_saver = false\\n[models.medium]\\ntask_model = "observed-model"\\ntask_reasoning = "medium"\\n', write_contract:{method:'POST'}, effective_settings:{execution:{usage_profile:'medium',fast_mode:true,usage_saver:false},models:{medium:{task_model:'observed-model',task_reasoning:'medium'}}}, descriptors:['execution.fast_mode','execution.usage_saver','models.medium.task_model','models.medium.task_reasoning'].map(key=>({key,editable:true}))};
    const naming = ${JSON.stringify(namingContract.settings)};
    Object.assign(base.effective_settings, naming);
    for(const [section,values] of Object.entries(naming))for(const [key,value] of Object.entries(values))if(section==='task_titles'||key.startsWith('pin_created'))base.descriptors.push({key:section+'.'+key,type:typeof value==='string'?'string':'boolean',editable:true});
    window.namingExample=namingExample; window.base=structuredClone(base);
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
      let section='';for(const line of args.text.split('\\n')){const table=line.match(/^\\[([^\\]]+)\\]$/);if(table){section=table[1];continue;}if(!['task_titles','lifecycle','role_icons'].includes(section))continue;const pair=line.match(/^([a-z_]+) = (.*)$/);if(pair)next.effective_settings[section][pair[1]]=JSON.parse(pair[2]);}
      next.mutation_receipt={action:'config_update',accepted:true,acknowledged:true,replayed:false,scope:args.scope,operation_id:window.wrong?'wrong':args.operation_id,expected_revision:args.expected_revision,new_revision:next.revision};
      window.current=next;return {structuredContent:structuredClone(next)};
    }};
    window.mount=()=>mountSettings(document.querySelector('main'),{app,scopes:[{label:'SWARM project',scope:{type:'project',project_id:'swarm',accepted_cursor:'exact-cursor'}}],hostModels:[{id:'observed-model',reasoning:['low','medium','high']}],editText:configTextWithChanges});
    window.settings=window.mount();
    await window.settings.ready;window.ready=true;
  `});
  await page.waitForFunction(() => window.ready);
  const switchProof = [];
  const fast = page.getByLabel('Fast', {exact:true});
  for (const [name,width,height] of [['desktop',1440,1000],['tablet',834,1112],['mobile',390,844]]) {
    await page.setViewportSize({width,height});
    for (const reducedMotion of ['no-preference','reduce']) {
      await page.emulateMedia({reducedMotion});
      const geometry = await fast.evaluate(input => {
        const box=input.getBoundingClientRect(), track=getComputedStyle(input,'::after'), knob=getComputedStyle(input,'::before');
        return {width:box.width,height:box.height,track:[track.width,track.height,track.top],knob:[knob.width,knob.height,knob.top],overflow:document.documentElement.scrollWidth>innerWidth};
      });
      assert.deepEqual(geometry,{width:48,height:44,track:['48px','28px','8px'],knob:['22px','22px','11px'],overflow:false}); checks++;
      // Exercise the added top/bottom hit area, not just the old visible track.
      await fast.click({position:{x:24,y:2}});
      assert.equal(await fast.isChecked(),false); checks++;
      await fast.tap({position:{x:24,y:42}});
      assert.equal(await fast.isChecked(),true); checks++;
      await fast.focus(); await page.keyboard.press('Space');
      assert.equal(await fast.isChecked(),false); checks++;
      assert.equal(await fast.evaluate(input=>input===document.activeElement),true); checks++;
      await page.keyboard.press('Space');
      assert.equal(await fast.isChecked(),true); checks++;
      assert.equal(await page.evaluate(()=>window.calls.length),0); checks++;
      assert.equal(await page.getByRole('button',{name:'Save changes',exact:true}).isDisabled(),true); checks++;
      switchProof.push({name,reducedMotion,...geometry});
    }
    if(evidence){fs.mkdirSync(evidence,{recursive:true});await page.screenshot({path:path.join(evidence,`switch-${name}.png`),fullPage:true});}
  }
  await page.emulateMedia({forcedColors:'active'});
  assert.equal(await fast.evaluate(input=>getComputedStyle(input,'::after').display),'none');checks++;
  assert.equal(await fast.evaluate(input=>getComputedStyle(input).appearance),'auto');checks++;
  await page.emulateMedia({forcedColors:'none',reducedMotion:'no-preference'});
  if(evidence)fs.writeFileSync(path.join(evidence,'SWITCH-GEOMETRY.json'),JSON.stringify(switchProof,null,2));
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
  // Local examples must match the accepted Python authority; they cannot become a host title writer.
  for(const item of namingContract.cases) {
    const actual=await page.evaluate(item=>{try{return {result:window.namingExample(item.template,item.values,item.emoji,item.enabled),error:false}}catch{return {result:null,error:true}}},item);
    assert.deepEqual(actual,{result:item.result,error:item.error});checks++;
  }
  await page.evaluate(async()=>{window.fail=false;window.wrong=false;window.current=structuredClone(window.base);window.calls=[];await window.mount().ready;});
  await page.getByRole('button',{name:'Advanced',exact:true}).click();
  const controller=page.getByLabel('Controllers Title template',{exact:true});
  assert.equal(await controller.inputValue(),'{project}');checks++;
  for(const category of ['Controllers','Units','Leads','Workers']) {
    assert.equal(await page.getByLabel(`${category} Show emoji`,{exact:true}).isChecked(),true);checks++;
    assert.equal(await page.getByLabel(`${category} Auto-pin`,{exact:true}).isChecked(),false);checks++;
  }
  for(const [name,width,height] of [['desktop',1440,1000],['tablet',834,1112],['mobile',390,844]]) {
    await page.setViewportSize({width,height});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);checks++;
    for(const box of await page.locator('.naming-row input').evaluateAll(inputs=>inputs.map(x=>({width:x.getBoundingClientRect().width,height:x.getBoundingClientRect().height})))){assert.ok(box.width>=44&&box.height>=44);checks++;}
    if(evidence)await page.screenshot({path:path.join(evidence,`naming-${name}.png`),fullPage:true});
  }
  assert.match(await page.locator('#naming-availability').textContent(),/unavailable until host support is verified/);checks++;
  for(const category of ['Controllers','Units','Leads','Workers']) for(const label of ['Title template','Show emoji','Auto-pin']) {
    const field=page.getByLabel(`${category} ${label}`,{exact:true});
    assert.equal(await field.isDisabled(),true);assert.match(await field.getAttribute('aria-describedby'),/naming-availability/);checks++;
  }
  assert.equal(await page.getByRole('button',{name:'Save changes',exact:true}).isDisabled(),true);checks++;
  await controller.evaluate(input=>{input.value='Tampered {project}';input.dispatchEvent(new Event('input',{bubbles:true}));});
  assert.equal(await page.getByRole('button',{name:'Save changes',exact:true}).isDisabled(),true);checks++;
  assert.equal(await page.evaluate(()=>window.calls.length),0);checks++;
  assert.match(await page.locator('#example-controller').textContent(),/^Example only:/);checks++;
  await page.getByRole('button',{name:'Essentials',exact:true}).click();
  await page.getByLabel('Search settings',{exact:true}).fill('Controllers');
  assert.equal(await controller.isVisible(),true);checks++;
  assert.equal(await page.getByLabel('Workers Title template',{exact:true}).isVisible(),false);checks++;
  await page.getByLabel('Search settings',{exact:true}).fill('task_titles.worker_template');
  assert.equal(await page.getByLabel('Workers Title template',{exact:true}).isVisible(),true);checks++;
  await page.getByLabel('Search settings',{exact:true}).fill('no-such-preference');
  assert.equal(await page.locator('[data-search-empty]').isVisible(),true);checks++;
  await page.getByRole('button',{name:'Advanced',exact:true}).click();
  await page.getByLabel('Settings scope').selectOption('1');
  await page.getByRole('status').filter({hasText:'Preferences loaded'}).waitFor();
  assert.equal(await controller.isDisabled(),true);checks++;
  assert.equal(await page.getByLabel('Units Auto-pin',{exact:true}).isDisabled(),true);checks++;
  assert.equal(await page.evaluate(()=>window.calls.length),0);checks++;
  await page.evaluate(async()=>{window.fail=false;window.current=structuredClone(window.base);window.current.effective_settings.role_icons.enabled=false;await window.mount().ready;});
  await page.getByRole('button',{name:'Advanced',exact:true}).click();
  assert.equal(await page.locator('#example-controller').textContent(),'Example only: Example project');checks++;
  assert.equal(await page.getByLabel('Controllers Show emoji',{exact:true}).isChecked(),true);checks++;
  assert.match(await page.locator('[data-emoji-note]').textContent(),/off globally/);checks++;
  await page.evaluate(async()=>{window.current.descriptors=window.current.descriptors.filter(x=>!x.key.startsWith('task_titles.'));await window.mount().ready;});
  await page.getByRole('button',{name:'Advanced',exact:true}).click();
  assert.equal(await controller.isDisabled(),true);checks++;
  assert.match(await page.locator('#example-controller').textContent(),/unavailable/);checks++;
  assert.deepEqual(errors,[]);checks++;
  console.log(JSON.stringify({status:'PASS_FIXTURE_ONLY',checks,limits:['No native host, real persistence, supported model bounds or full-page integration proof']}));
} finally {await browser.close();}
