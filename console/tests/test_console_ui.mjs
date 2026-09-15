import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const testsRoot = path.dirname(fileURLToPath(import.meta.url));
const consoleRoot = path.resolve(testsRoot, "..");
const repositoryRoot = path.resolve(consoleRoot, "..");
const staticRoot = path.join(consoleRoot, "static");
const pluginConsoleRoot = path.join(repositoryRoot, "plugins", "swarm", "console");
const pluginStaticRoot = path.join(pluginConsoleRoot, "static");
const fixture = JSON.parse(fs.readFileSync(path.join(testsRoot, "fixtures", "console-ui.json"), "utf8"));
const labCatalogFixture = JSON.parse(fs.readFileSync(path.join(repositoryRoot, "skills", "swarm", "labs", "catalog.json"), "utf8"));
fixture.usageHistory.items = fixture.usageHistory.history;
delete fixture.usageHistory.history;
const css = fs.readFileSync(path.join(staticRoot, "styles.css"), "utf8");
const app = fs.readFileSync(path.join(staticRoot, "app.js"), "utf8").replace(/\r\n/g, "\n");
const html = fs.readFileSync(path.join(staticRoot, "index.html"), "utf8");
assert.match(html, /data-view="labs"[\s\S]*id="view-labs"/);
assert.match(app, /api\('\/api\/labs'\)/);
assert.match(app, /\/assets\/role-avatars\//);
assert.match(app, /function labManifestMarkup[\s\S]*Block progress/);
assert.doesNotMatch(app, /function startLab|data-lab-form|data-custom-lab-form/);
assert.doesNotMatch(app, /LAB_CATALOG|\/api\/labs\/commands/);
assert.match(css, /\.lab-catalog[\s\S]*grid-template-columns:repeat\(3/);
{
  for (const mode of ['cancel','success','failure','stale']) {
    const elements=new Map(); let calls=0;
    const state={configEditorDraft:{pending:false,scope:'{"type":"project","id":"p"}',text:'original',revision:'r1'},config:{revision:'r1'}};
    const sandbox={state,$:id=>{if(!elements.has(id)) elements.set(id,{value:'unsaved',focus(){}});return elements.get(id);},configEditorWritable:()=>true,currentSettingsScope:()=>({type:'project',id:'p'}),confirm:()=>mode!=='cancel',renderConfigEditor(){},resetSettingsScope:async()=>{calls++;if(mode==='failure')throw new Error('Rejected');if(mode==='stale')return{applied:false};state.config={revision:'r2',editable_text:'inherited',validation:{state:'KNOWN',status:'VALID'}};return{applied:true};}};
    vm.createContext(sandbox);
    vm.runInContext(app.slice(app.indexOf('async function resetConfigEditor('),app.indexOf('async function saveSettingsDraft(')),sandbox);
    await sandbox.resetConfigEditor();
    assert.equal(calls,mode==='cancel'?0:1);
    assert.equal(sandbox.$('#config-editor-text').value,mode==='success'?'inherited':'unsaved');
    assert.equal(state.configEditorDraft.pending,false);
    if(mode==='success') assert.equal(state.configEditorDraft.revision,'r2');
  }
}
{
  for (const mode of ['fresh','replay','operation','scope','revision','cursor','stale','transport']) {
    const scope={type:'project',project_id:'p',accepted_cursor:{sequence:4}};
    const original={state:'KNOWN',scope,revision:'r1',write_contract:{available:true}};
    const state={config:original,configStatus:'current',settingsDraft:new Map([['draft',1]])};
    const requests=[];
    const sandbox={state,structuredClone,configMutationTail:Promise.resolve(),configAuthorityGeneration:0,currentSettingsScope:()=>({type:'project',id:'p'}),configResetOperationId:()=>`reset-${requests.length}`,api:async(url,options)=>{
      assert.equal(url,'/api/config/reset'); const payload=JSON.parse(options.body); requests.push(payload);
      assert.deepEqual(Object.keys(payload).sort(),['acknowledge','expected_revision','operation_id','scope']);
      if(mode==='transport') throw Object.assign(new Error('offline'),{connectionFailure:true});
      const result={...original,revision:'r2',mutation_receipt:{accepted:true,action:'project_config_reset',scope:structuredClone(scope),expected_revision:'r1',new_revision:'r2',replayed:mode==='replay',acknowledged:true,operation_id:payload.operation_id}};
      if(mode==='operation') result.mutation_receipt.operation_id='other';
      if(mode==='scope') result.scope={type:'global'};
      if(mode==='revision') result.mutation_receipt.new_revision='other';
      if(mode==='cursor') result.mutation_receipt.scope.accepted_cursor.sequence=99;
      if(mode==='stale') state.config={...original,revision:'newer'};
      return result;
    }};
    vm.createContext(sandbox);
    vm.runInContext(app.slice(app.indexOf('function configWriteScope('),app.indexOf('function configTomlLiteral('))+app.slice(app.indexOf('function configWriteReceiptMatches('),app.indexOf('function configWriteBindingIsCurrent('))+app.slice(app.indexOf('function configResetRequest('),app.indexOf('async function readConfigState(')),sandbox);
    if(mode==='fresh'||mode==='replay') {
      assert.equal((await sandbox.resetSettingsScope('project')).applied,true); assert.equal(state.config.revision,'r2'); assert.equal(state.settingsDraft.size,0);
    } else if(mode==='stale') {
      assert.equal((await sandbox.resetSettingsScope('project')).applied,false); assert.equal(state.config.revision,'newer'); assert.equal(state.settingsDraft.size,1);
    } else {
      await assert.rejects(sandbox.resetSettingsScope('project')); assert.equal(state.config,original); assert.equal(state.settingsDraft.size,1);
      await assert.rejects(sandbox.resetSettingsScope('project')); assert.equal(requests[0].operation_id,requests[1].operation_id);
      await assert.rejects(sandbox.resetSettingsScope('project'),/after one retry/); assert.equal(requests.length,2);
    }
  }
}
{
  for (const mode of ['fresh','replay','transport','conflict','mismatch']) {
    const elements=new Map(), requests=[];
    const state={configStatus:'current',config:{scope:{type:'global'},state:'KNOWN',available:true,read_only:false,write_contract:{available:true},revision:'r1',editable_text:'original'}};
    const sandbox={state,structuredClone,configMutationTail:Promise.resolve(),configAuthorityGeneration:0,configWriteRetry:null,configWriteOperationId:()=>`op-${requests.length}`,
      currentSettingsScope:()=>({type:'global'}),$:id=>{if(!elements.has(id)) elements.set(id,{value:'',focus(){}}); return elements.get(id);},
      api:async(url,options)=>{
        assert.equal(url,'/api/config'); const request=JSON.parse(options.body); requests.push(request);
        assert.deepEqual(Object.keys(request).sort(),['acknowledge','expected_revision','operation_id','scope','text']);
        assert.equal(request.text,'  exact draft\n'); assert.equal(request.acknowledge,true);
        if(mode==='transport') throw Object.assign(new Error('disconnected'),{connectionFailure:true});
        if(mode==='conflict') throw Object.assign(new Error('conflict'),{status:409});
        return {...state.config,revision:'r2',editable_text:request.text,mutation_receipt:{scope:request.scope,new_revision:'r2',expected_revision:request.expected_revision,operation_id:mode==='mismatch'?'foreign':request.operation_id,accepted:true,acknowledged:true,action:'config_update',replayed:mode==='replay'}};
      }};
    vm.createContext(sandbox);
    vm.runInContext(app.slice(app.indexOf('function configWriteScope('),app.indexOf('function configTomlLiteral('))+app.slice(app.indexOf('function configWriteRequest('),app.indexOf('async function saveConfigMutation('))+app.slice(app.indexOf('function configEditorWritable('),app.indexOf('function renderConfigEditor('))+app.slice(app.indexOf('async function saveConfigEditor('),app.indexOf('async function saveSettingsDraft(')),sandbox);
    state.configEditorDraft={scope:'{"type":"global"}',binding:'{"type":"global"}',revision:'r1',text:'original',pending:false};
    const input=sandbox.$('#config-editor-text'); input.value='  exact draft\n'; input.readOnly=false;
    await sandbox.saveConfigEditor();
    if(mode==='fresh'||mode==='replay') {
      assert.equal(state.configEditorDraft.revision,'r2'); assert.equal(sandbox.$('#config-editor-status').textContent,'Saved');
      assert.equal(sandbox.$('#config-editor-save').disabled,true);
    } else {
      assert.equal(input.value,'  exact draft\n'); assert.equal(state.configEditorDraft.text,'original');
      assert.doesNotMatch(sandbox.$('#config-editor-status').textContent,/^Saved$/);
      await sandbox.saveConfigEditor();
      if(mode==='conflict') assert.notEqual(requests[0].operation_id,requests[1].operation_id);
      else {
        assert.equal(requests[0].operation_id,requests[1].operation_id);
        await sandbox.saveConfigEditor(); assert.equal(requests.length,2);
        assert.match(sandbox.$('#config-editor-status').textContent,/after one retry/);
      }
    }
  }
}
{
  const elements = new Map(); let release; let calls = 0;
  const scope = {type:'global'};
  const state = {configStatus:'current',config:{state:'KNOWN',available:true,read_only:false,write_contract:{available:true},revision:'r1',editable_text:'original'}};
  const sandbox = {state,$:id=>{if(!elements.has(id)) elements.set(id,{value:'',focus(){}}); return elements.get(id);},currentSettingsScope:()=>scope,configWriteScope:()=>({type:'global'}),saveConfigText:async getText=>{calls++; getText(); return await new Promise(resolve=>{release=resolve;});}};
  vm.createContext(sandbox);
  vm.runInContext(app.slice(app.indexOf('function configEditorWritable('),app.indexOf('function openConfigEditor(')) + app.slice(app.indexOf('async function saveConfigEditor('),app.indexOf('async function saveSettingsDraft(')),sandbox);
  state.configEditorDraft={scope:JSON.stringify(scope),binding:JSON.stringify(scope),revision:'r1',text:'original',pending:false};
  const input=sandbox.$('#config-editor-text'); input.value='unsaved'; input.readOnly=false;
  const pending=sandbox.saveConfigEditor();
  assert.equal(calls,1); assert.equal(input.readOnly,true);
  state.config.revision='r2'; release({applied:false}); await pending;
  assert.equal(input.value,'unsaved'); assert.equal(input.readOnly,true);
  assert.equal(sandbox.$('#config-editor-save').disabled,true);
  assert.doesNotMatch(sandbox.$('#config-editor-status').textContent,/^Saved$/);
  sandbox.$('#config-editor-dialog').open=true;
  sandbox.renderConfigEditor(); assert.equal(input.value,'unsaved');
  input.value='typed after drift'; await sandbox.saveConfigEditor(); assert.equal(calls,1);
  state.config.revision='r1'; assert.equal(sandbox.configEditorWritable(),true);
  for (const change of [()=>state.configStatus='stale',()=>state.config.read_only=true,()=>scope.type='project']) {
    change(); assert.equal(sandbox.configEditorWritable(),false);
    sandbox.renderConfigEditor(); assert.equal(input.value,'typed after drift'); assert.equal(input.readOnly,true);
    state.configStatus='current'; state.config.read_only=false; scope.type='global';
  }
}
{
  const elements = new Map();
  const state = {configStatus:'current',config:{state:'KNOWN',available:true,revision:'abcdef123456789',editable_text:'[execution]\nusage_saver = false\n',validation:{state:'KNOWN',status:'VALID'}}};
  let scope = {type:'global'};
  const sandbox = {state,$:id => {if (!elements.has(id)) elements.set(id,{}); return elements.get(id);},currentSettingsScope:()=>scope,selectedSettingsCtrl:()=>null,settingsContextPresentation:()=>({title:'Global defaults'}),configWriteScope:()=>({type:'global'})};
  vm.createContext(sandbox);
  vm.runInContext(app.slice(app.indexOf('function renderConfigEditor('),app.indexOf('function openConfigEditor(')),sandbox);
  sandbox.renderConfigEditor();
  assert.equal(elements.get('#config-editor-text').value,state.config.editable_text);
  assert.equal(elements.get('#config-editor-revision').textContent,'abcdef123456');
  assert.equal(elements.get('#config-editor-validation').textContent,'VALID');
  for (const status of ['stale','unavailable']) {
    state.configStatus=status; sandbox.renderConfigEditor();
    assert.equal(elements.get('#config-editor-text').value,'');
    assert.equal(elements.get('#config-editor-save').disabled,true);
  }
  state.configStatus='current'; scope={type:'project',id:'other'};
  sandbox.renderConfigEditor(); assert.equal(elements.get('#config-editor-revision').textContent,'Unavailable');
}
{
  const host = {innerHTML:''};
  const summary = {freshness:{state:'fresh'},current_milestone:{state:'KNOWN',source:'ledger_active_task_manifest',project_id:'p',name:'Ship <V1>'}};
  const sandbox = {state:{connectionStatus:'live'},$:()=>host,savedProjectRoster:()=>({state:'KNOWN',projects:[{id:'p',label:'Swarm',status:'recent'}]}),authoritativeProgress:()=>summary,projectScopeMark:()=>'',humanize:String};
  vm.createContext(sandbox);
  vm.runInContext(app.slice(app.indexOf('function escapeHTML('),app.indexOf('const COLLECTION_PAGE_SIZE')) + app.slice(app.indexOf('function renderOverviewProjects('),app.indexOf('function renderOverview()')),sandbox);
  sandbox.renderOverviewProjects(); assert.match(host.innerHTML,/Ship &lt;V1&gt;/);
  for (const change of [{project_id:'foreign'},{state:'UNKNOWN'},{source:'snapshot'}]) {
    const saved = {...summary.current_milestone}; Object.assign(summary.current_milestone,change);
    sandbox.renderOverviewProjects(); assert.match(host.innerHTML,/Current milestone unavailable/);
    summary.current_milestone=saved;
  }
  summary.freshness.state='stale'; sandbox.renderOverviewProjects(); assert.match(host.innerHTML,/Current milestone unavailable/);
}
{
  const state = {messageOpen:true,messageDraft:"  Reply exactly Ω.  ",messageAttachments:[],messageRecipientId:"task",messageStatus:"idle"};
  const handlers={}; let releaseContext;
  let binding="project/task", calls=[], mode="RESULT", ids=0, rejectionOverride={};
  const context={ok:true,project_id:"project",target_thread_id:"task",root_digest:"a".repeat(64),expected_ledger_revision:4,submitted_at_ms:Date.now(),expires_at_ms:Date.now()+60000,action:"TASK",target_intent:"EXISTING_THREAD",ctrl_id:""};
  context.expires_at_ms=context.submitted_at_ms+60000;
  const sandbox={state,Date,TextEncoder,Uint8Array,window:{crypto:crypto.webcrypto},messageInteractionGeneration:0,messageHistoryRequestGeneration:0,messageRosterRequestGeneration:0,messageRequestId:()=>"id"+(++ids),renderMessageComposer(){},renderMessageHistory(){},refreshMessageHistory(){},
    $:selector=>({addEventListener:(event,handler)=>{handlers[selector+event]=handler;}}),
    messageHistoryBinding:()=>binding,messageHistoryRecipients:()=>[{id:"task",projectId:"project"}],
    api:async(url,options)=>{const body=JSON.parse(options.body);calls.push({url,body});if(url.endsWith('-context'))return mode==='deferred'?await new Promise(resolve=>{releaseContext=()=>resolve(context);}):context;
      if(mode==='timeout')throw Error('transport timeout');
      const digest=crypto.createHash('sha256').update(JSON.stringify(Object.fromEntries(Object.entries(body.envelope).sort()))).digest('hex');
      if(mode==='NOT_DISPATCHED') return {ok:true,status:mode,definitive_non_dispatch:true,command_id:body.envelope.command_id,idempotency_key:body.envelope.idempotency_key,command_digest:digest,project_id:body.envelope.project_id,target_thread_id:body.envelope.target_thread_id,root_digest:body.envelope.root_digest,reason:'SUBMISSION_EXPIRED_OR_REVISION_STALE',work_completed:false,...rejectionOverride};
      if(mode==='scope-change')binding='other/task';
      return {ok:true,status:mode==='scope-change'?'RESULT':mode,command_digest:mode==='mismatch'?'b'.repeat(64):digest,thread_id:'task',turn_id:'turn',observed_root_digest:'a'.repeat(64),work_completed:false};}};
  vm.createContext(sandbox);
  vm.runInContext(app.slice(app.indexOf('function canonicalActionValue('),app.indexOf('async function messageActionDigest(')) + app.slice(app.indexOf('function taskMessageCapability('),app.indexOf('function messageStatusCopy(')),sandbox);
  vm.runInContext(app.slice(app.indexOf('$("#message-draft").addEventListener("input"'),app.indexOf('$("#message-send").addEventListener')) + app.slice(app.indexOf('function invalidateMessageHistory()'),app.indexOf('function messageRosterProjectId()')),sandbox);
  vm.runInContext(app.slice(app.indexOf('async function sendMessageFromComposer('),app.indexOf('function agentProgress(')) + app.slice(app.indexOf('$("#message-send").addEventListener'),app.indexOf('$("#profile").addEventListener')),sandbox);
  const capability={contract:'swarm.hq_task_message.v1',method:'POST',endpoint:'/api/tasks/message',context_endpoint:'/api/tasks/message-context'};
  assert.equal(sandbox.taskMessageCapability({hq_connector:capability}),null);
  state.taskMessageCapability=sandbox.taskMessageCapability({capabilities:{task_message:capability}});
  assert.equal(await sandbox.sendTaskMessage(false),true);
  assert.equal(calls[1].body.instruction,'  Reply exactly Ω.  ');
  assert.equal(calls[1].body.envelope.payload_digest,crypto.createHash('sha256').update('  Reply exactly Ω.  ').digest('hex'));
  assert.equal(calls[1].body.acknowledge,true);assert.equal(state.messageDraft,'');
  state.messageDraft='retry';mode='timeout';calls=[];
  assert.equal(await sandbox.sendTaskMessage(false),false);const original=calls[1].body;
  const pendingIdentity=state.messagePendingAction;
  for(const value of ['edited','retry'])handlers['#message-draftinput']({target:{value}});
  for(const value of ['other','task'])handlers['#message-recipientchange']({target:{value}});
  assert.equal(state.messagePendingAction,pendingIdentity,'actual input and recipient handlers retain uncertain identity');
  assert.equal(await sandbox.sendTaskMessage(false),false,'edit/restore cannot create another command');
  mode='REPLAY';assert.equal(await sandbox.sendTaskMessage(true),true);assert.deepEqual(calls[2].body,original);
  state.messageDraft='keep';mode='mismatch';assert.equal(await sandbox.sendTaskMessage(false),false);assert.equal(state.messageDraft,'keep');
  const count=calls.length;binding='other/task';assert.equal(await sandbox.sendTaskMessage(true),false);assert.equal(calls.length,count);
  binding='project/task';state.messagePendingAction=null;mode='PENDING';assert.equal(await sandbox.sendTaskMessage(false),false);assert.equal(state.messageDraft,'keep');
  assert.equal(await sandbox.sendTaskMessage(true),false);const after=calls.length;assert.equal(await sandbox.sendTaskMessage(true),false);assert.equal(calls.length,after);
  state.messagePendingAction=null;context.project_id='foreign';const beforeBad=calls.length;
  assert.equal(await sandbox.sendTaskMessage(false),false);assert.equal(calls.length,beforeBad+1,'bad context never dispatches');assert.equal(state.messageDraft,'keep');
  context.project_id='project';mode='scope-change';assert.equal(await sandbox.sendTaskMessage(false),false);assert.equal(state.messageDraft,'keep');
  for(const interaction of ['draft','recipient','close']) {
    binding='project/task';state.messagePendingAction=null;state.messageStatus='idle';mode='deferred';
    const before=calls.length, flight=sandbox.sendTaskMessage(false);
    if(interaction==='draft')for(const value of ['changed','keep'])handlers['#message-draftinput']({target:{value}});
    if(interaction==='recipient')for(const value of ['other','task'])handlers['#message-recipientchange']({target:{value}});
    if(interaction==='close'){state.messageOpen=false;sandbox.invalidateMessageHistory();state.messageOpen=true;}
    releaseContext();assert.equal(await flight,false);assert.equal(calls.length,before+1,'context ABA must not dispatch');
    assert.equal(state.messageDraft,'keep');
  }
  for(const reason of ['SUBMISSION_EXPIRED_OR_REVISION_STALE','RETAINED_UNSUPPORTED']) {
    mode='NOT_DISPATCHED';rejectionOverride={reason};state.messagePendingAction=null;state.messageStatus='idle';
    handlers['#message-draftinput']({target:{value:'correct me'}});
    assert.equal(await handlers['#message-sendclick'](),false);const rejectedId=calls.at(-1).body.envelope.command_id;
    assert.equal(state.messagePendingAction,null);assert.equal(state.messageDraft,'correct me');
    handlers['#message-draftinput']({target:{value:'corrected'}});context.expected_ledger_revision++;mode='RESULT';
    assert.equal(await handlers['#message-sendclick'](),true);assert.notEqual(calls.at(-1).body.envelope.command_id,rejectedId);
  }
  for(const mismatch of [{command_id:'wrong'},{idempotency_key:'wrong'},{command_digest:'b'.repeat(64)},{project_id:'other'},{target_thread_id:'other'},{root_digest:'b'.repeat(64)},{definitive_non_dispatch:false},{work_completed:true},{reason:'UNKNOWN'}]) {
    state.messageDraft='retain';state.messagePendingAction=null;state.messageStatus='idle';mode='NOT_DISPATCHED';rejectionOverride=mismatch;
    assert.equal(await handlers['#message-sendclick'](),false);assert.equal(state.messagePendingAction.kind,'task');assert.equal(state.messageDraft,'retain');
  }
}
const indexHtml = fs.readFileSync(path.join(staticRoot, "index.html"), "utf8");
const pluginCss = fs.readFileSync(path.join(pluginStaticRoot, "styles.css"), "utf8");
const pluginApp = fs.readFileSync(path.join(pluginStaticRoot, "app.js"), "utf8");
const pluginIndexHtml = fs.readFileSync(path.join(pluginStaticRoot, "index.html"), "utf8");
const server = fs.readFileSync(path.join(consoleRoot, "server.py"), "utf8");
const pluginServer = fs.readFileSync(path.join(pluginConsoleRoot, "server.py"), "utf8");
const agentsSourceOnly = process.argv.includes("--agents-source-only");
const skipServerParity = process.argv.includes("--skip-server-parity");
const offlineAsset = fs.readFileSync(path.join(staticRoot, "swarm-offline-disconnected.png"));
const pluginOfflineAsset = fs.readFileSync(path.join(pluginStaticRoot, "swarm-offline-disconnected.png"));
const concernedAsset = fs.readFileSync(path.join(staticRoot, "swarm-state-mascot-concerned.png"));
const pluginConcernedAsset = fs.readFileSync(path.join(pluginStaticRoot, "swarm-state-mascot-concerned.png"));
const offlineWebpAsset = fs.readFileSync(path.join(staticRoot, "swarm-offline-disconnected.webp"));
const pluginOfflineWebpAsset = fs.readFileSync(path.join(pluginStaticRoot, "swarm-offline-disconnected.webp"));
const reportHtml = fs.readFileSync(path.join(staticRoot, "report.html"), "utf8");
const reportJs = fs.readFileSync(path.join(staticRoot, "report.js"), "utf8");
const reportCss = fs.readFileSync(path.join(staticRoot, "report.css"), "utf8");
const concernedWebpAsset = fs.readFileSync(path.join(staticRoot, "swarm-state-mascot-concerned.webp"));
const pluginConcernedWebpAsset = fs.readFileSync(path.join(pluginStaticRoot, "swarm-state-mascot-concerned.webp"));
const supportCaricatureAsset = fs.readFileSync(path.join(staticRoot, "support-caricature-light.webp"));
const pluginSupportCaricatureAsset = fs.readFileSync(path.join(pluginStaticRoot, "support-caricature-light.webp"));
const stateMascotProvenance = JSON.parse(fs.readFileSync(path.join(staticRoot, "swarm-state-mascot-provenance.json"), "utf8"));
const pluginStateMascotProvenance = JSON.parse(fs.readFileSync(path.join(pluginStaticRoot, "swarm-state-mascot-provenance.json"), "utf8"));
const mascotAsset = fs.readFileSync(path.join(staticRoot, "swarm-mascot-512.png"));
const pluginMascotAsset = fs.readFileSync(path.join(pluginStaticRoot, "swarm-mascot-512.png"));
const onboardingSlide1Asset = fs.readFileSync(path.join(staticRoot, "swarm-guided-tour-slide1.png"));
const pluginOnboardingSlide1Asset = fs.readFileSync(path.join(pluginStaticRoot, "swarm-guided-tour-slide1.png"));
const onboardingRoleGroupAsset = fs.readFileSync(path.join(staticRoot, "swarm-guided-tour-role-group.png"));
const pluginOnboardingRoleGroupAsset = fs.readFileSync(path.join(pluginStaticRoot, "swarm-guided-tour-role-group.png"));
const onboardingProjectToolAsset = fs.readFileSync(path.join(staticRoot, "swarm-guided-tour-project-tool.png"));
const pluginOnboardingProjectToolAsset = fs.readFileSync(path.join(pluginStaticRoot, "swarm-guided-tour-project-tool.png"));
const iconAsset = fs.readFileSync(path.join(staticRoot, "swarm-icon-64.png"));
const pluginIconAsset = fs.readFileSync(path.join(pluginStaticRoot, "swarm-icon-64.png"));
const wordmarkAsset = fs.readFileSync(path.join(repositoryRoot, "skills", "swarm", "assets", "swarm-wordmark.png"));
const documentHtml = indexHtml
  .replace("<head>", '<head><base href="http://swarm.test/">');

function pngIdentity(buffer) {
  return { signature: buffer.subarray(1, 4).toString("ascii"), width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20), colorType: buffer[25] };
}

const offlineAssetDigest = crypto.createHash("sha256").update(offlineAsset).digest("hex");
assert.equal(offlineAssetDigest, "586dc9a24384bf0d86eef402f69172c7bfd30e18ae8b58a48fd41eb89450da1e");
assert.deepEqual(pluginOfflineAsset, offlineAsset);
assert.equal(crypto.createHash("sha256").update(concernedAsset).digest("hex"), "6b4cd07fddac1c791eadfd4a63c346eab7a6708531c8141321d968d74111654d");
assert.deepEqual(pluginConcernedAsset, concernedAsset);
assert.equal(crypto.createHash("sha256").update(offlineWebpAsset).digest("hex"), "983253ceb56061bec64fdd52ad7b6338986d0916c786fd356ede78349ec18ed3");
assert.equal(crypto.createHash("sha256").update(concernedWebpAsset).digest("hex"), "f1f3e41bdf3175afe228d3be8b3c39d0748b98a7c4e4d24aa83133d84526d276");
assert.deepEqual(pluginOfflineWebpAsset, offlineWebpAsset);
assert.deepEqual(pluginConcernedWebpAsset, concernedWebpAsset);
assert.deepEqual(pluginSupportCaricatureAsset, supportCaricatureAsset);
assert.equal(supportCaricatureAsset.subarray(0, 4).toString("ascii"), "RIFF");
assert.deepEqual(pluginStateMascotProvenance, stateMascotProvenance);
assert.equal(stateMascotProvenance.schema_version, 1);
assert.equal(stateMascotProvenance.source.sha256, "247fc2a02b5505c13815d78c4cce8765b893f51b70cf9167d1e2d43350209666");
assert.equal(stateMascotProvenance.transformation.alpha_channel_identical_to_source, true);
assert.equal(stateMascotProvenance.transformation.webp_transparent_rgb_normalized, true);
assert.equal(stateMascotProvenance.transformation.webp_nontransparent_pixels_identical_to_png, true);
assert.equal(stateMascotProvenance.assets[0].primary.sha256, "f1f3e41bdf3175afe228d3be8b3c39d0748b98a7c4e4d24aa83133d84526d276");
assert.equal(stateMascotProvenance.assets[0].fallback.sha256, "6b4cd07fddac1c791eadfd4a63c346eab7a6708531c8141321d968d74111654d");
assert.equal(stateMascotProvenance.assets[1].primary.sha256, "983253ceb56061bec64fdd52ad7b6338986d0916c786fd356ede78349ec18ed3");
assert.equal(stateMascotProvenance.assets[1].fallback.sha256, "586dc9a24384bf0d86eef402f69172c7bfd30e18ae8b58a48fd41eb89450da1e");
assert.equal(stateMascotProvenance.rejected_format.media_type, "image/avif");
assert.deepEqual(pngIdentity(offlineAsset), { signature: "PNG", width: 1024, height: 640, colorType: 6 });
assert.deepEqual(pngIdentity(concernedAsset), { signature: "PNG", width: 512, height: 512, colorType: 6 });
assert.equal(crypto.createHash("sha256").update(mascotAsset).digest("hex"), "247fc2a02b5505c13815d78c4cce8765b893f51b70cf9167d1e2d43350209666");
assert.equal(crypto.createHash("sha256").update(onboardingSlide1Asset).digest("hex"), "7f97baeee650e3e5e0c024b52da0dac9d4f69ad691050630cb90f0237ca9a3ed");
assert.equal(crypto.createHash("sha256").update(onboardingRoleGroupAsset).digest("hex"), "dc9ed5015aff55402e9f266cfbb59676d2deaa1465a16b634e4064bdf490d48e");
assert.equal(crypto.createHash("sha256").update(onboardingProjectToolAsset).digest("hex"), "6c8331de54dac15c83d889374c58cda9034dae1a86d64a1c94c3b1a90f9a3551");
assert.deepEqual(pngIdentity(onboardingSlide1Asset), { signature: "PNG", width: 1920, height: 1080, colorType: 6 });
assert.deepEqual(pngIdentity(onboardingRoleGroupAsset), { signature: "PNG", width: 1920, height: 1080, colorType: 6 });
assert.deepEqual(pngIdentity(onboardingProjectToolAsset), { signature: "PNG", width: 1536, height: 1024, colorType: 6 });
assert.equal(crypto.createHash("sha256").update(iconAsset).digest("hex"), "fbc528b1b7233105a5ddb5a32b1dfed9dbfe1a0db26e0bdb45a4c2d54f3c0bf4");
assert.deepEqual(pluginMascotAsset, mascotAsset);
assert.deepEqual(pluginOnboardingSlide1Asset, onboardingSlide1Asset);
assert.deepEqual(pluginOnboardingRoleGroupAsset, onboardingRoleGroupAsset);
assert.deepEqual(pluginOnboardingProjectToolAsset, onboardingProjectToolAsset);
assert.deepEqual(pluginIconAsset, iconAsset);
const normalizedText = (value) => value.replace(/\r\n/g, "\n");
assert.equal(normalizedText(pluginCss), normalizedText(css));
assert.equal(normalizedText(pluginApp), normalizedText(app));
assert.match(app, /compactNumber\(row\.tokens\)/, 'Task token totals use compact notation');
assert.equal(normalizedText(pluginIndexHtml), normalizedText(indexHtml));
if (!agentsSourceOnly && !skipServerParity) assert.equal(normalizedText(pluginServer), normalizedText(server));
assert.match(server, /"\/assets\/swarm-offline-disconnected\.png": \("swarm-offline-disconnected\.png", "image\/png"\)/);
assert.match(server, /"\/assets\/swarm-state-mascot-concerned\.png": \("swarm-state-mascot-concerned\.png", "image\/png"\)/);
assert.match(server, /"\/assets\/swarm-offline-disconnected\.webp": \("swarm-offline-disconnected\.webp", "image\/webp"\)/);
assert.match(server, /"\/report\.html": \("report\.html", "text\/html; charset=utf-8"\)/);
assert.match(indexHtml, /id="daily-report-link" href="\/report\.html">Daily report<\/a>/);
assert.match(app, /const reportProjectId = selectedProgressProjectId\(\);[\s\S]*#daily-report-link[\s\S]*\/report\.html\?project_id=/);
assert.match(reportHtml, /\/assets\/swarm-wordmark\.png[\s\S]*id="report-scope"[\s\S]*Save PDF/);
assert.match(reportJs, /report\.settings\?\.skip_inactive === true/);
assert.match(reportJs, /project-mark/);
assert.doesNotMatch(reportJs, /projectLogo|project-logo/);
assert.match(reportJs, /activity_facts\?\.inactive !== true[\s\S]*project\.activity_status !== "inactive"/);
assert.match(reportJs, /inactiveTaskStates[\s\S]*work\.slice\(0, 6\)[\s\S]*remainder[\s\S]* more<\/p>/);
assert.doesNotMatch(reportJs, /role \|\| ""\)\.toLowerCase\(\) !== "ctrl"/);
assert.match(reportJs, /typeof node\?\.updated_at === "number" \? node\.updated_at : Date\.parse/);
assert.match(reportJs, /selected \? \(reportableProject\(selected, skipInactive\)[\s\S]*allProjects\.filter\(\(project\) => reportableProject\(project, skipInactive\)\)/);
assert.match(reportCss, /\.project-mark \{[^}]*border-radius:50%/);
assert.match(reportCss, /@media \(max-width:420px\)[\s\S]*@media print/);
assert.match(server, /"\/assets\/swarm-state-mascot-concerned\.webp": \("swarm-state-mascot-concerned\.webp", "image\/webp"\)/);
assert.match(server, /"\/assets\/support-caricature-light\.webp": \("support-caricature-light\.webp", "image\/webp"\)/);
assert.match(pluginServer, /"\/assets\/support-caricature-light\.webp": \("support-caricature-light\.webp", "image\/webp"\)/);
assert.match(server, /"\/assets\/swarm-mascot-512\.png": \("swarm-mascot-512\.png", "image\/png"\)/);
assert.match(server, /"\/assets\/swarm-guided-tour-slide1\.png": \("swarm-guided-tour-slide1\.png", "image\/png"\)/);
assert.match(server, /"\/assets\/swarm-guided-tour-role-group\.png": \("swarm-guided-tour-role-group\.png", "image\/png"\)/);
assert.match(server, /"\/assets\/swarm-guided-tour-project-tool\.png": \("swarm-guided-tour-project-tool\.png", "image\/png"\)/);
assert.match(pluginServer, /"\/assets\/swarm-guided-tour-slide1\.png": \("swarm-guided-tour-slide1\.png", "image\/png"\)/);
assert.match(pluginServer, /"\/assets\/swarm-guided-tour-role-group\.png": \("swarm-guided-tour-role-group\.png", "image\/png"\)/);
assert.match(pluginServer, /"\/assets\/swarm-guided-tour-project-tool\.png": \("swarm-guided-tour-project-tool\.png", "image\/png"\)/);
assert.match(server, /"\/swarm-icon-64\.png": \("swarm-icon-64\.png", "image\/png"\)/);
assert.match(indexHtml, /id="connection-state" hidden role="alert" aria-labelledby="connection-state-title" aria-describedby="connection-state-detail"/);
assert.match(indexHtml, /data-state-variant="offline" aria-hidden="true"><picture><source type="image\/webp" srcset="\/assets\/swarm-offline-disconnected\.webp"><img src="\/assets\/swarm-offline-disconnected\.png" width="1024" height="640"[^>]*alt=""/);
assert.match(indexHtml, /id="connection-state-title">Connection lost<\/h2><p id="connection-state-detail">Your work is safe\. SWARM will reconnect when the console is available\.<\/p>/);
assert.match(indexHtml, /id="connection-retry"[^>]*>Retry connection<\/button>/);
assert.match(indexHtml, /id="error-surface" hidden role="alert" aria-labelledby="error-title" aria-describedby="error-message"/);
assert.match(indexHtml, /data-state-variant="failed" aria-hidden="true"><picture><source type="image\/webp" srcset="\/assets\/swarm-state-mascot-concerned\.webp"><img src="\/assets\/swarm-state-mascot-concerned\.png" width="512" height="512"[^>]*alt=""/);
assert.match(indexHtml, /id="error-title">SWARM couldn't finish that<\/strong>[^]*?id="retry"[^>]*>Refresh SWARM<\/button>/);
assert.match(app, /const STATE_ILLUSTRATIONS = Object\.freeze\([\s\S]*?offline:[\s\S]*?failed:[\s\S]*?empty:[\s\S]*?recovery:/);
assert.match(app, /function stateIllustrationMarkup\(variant = "empty"/);
assert.match(app, /<picture><source type="image\/webp" srcset=/);
assert.match(app, /stateMessageMarkup\("empty", "No proof yet"/);
assert.match(app, /stateMessageMarkup\("recovery", "Proof is temporarily unavailable", "Proof will appear here when SWARM receives it again\."/);
assert.match(css, /\.state-illustration \{[^}]*aspect-ratio:1;[^}]*isolation:isolate;/);
assert.match(css, /\.state-illustration picture \{[^}]*width:100%;[^}]*height:100%;/);
assert.match(css, /\.state-message \{[^}]*min-height:260px;/);
assert.match(app, /if \(error instanceof TypeError\) throw connectionFailure/);
assert.match(app, /if \(error\.connectionFailure && !state\.overview\) showConnectionState\(\)/);
assert.match(app, /\$\("#connection-retry"\)\.addEventListener\("click", initialize\)/);
assert.match(app, /\$\("\.app-shell"\)\.classList\.add\("is-disconnected"\)/);
assert.match(app, /\$\("\.app-shell"\)\.classList\.remove\("is-disconnected"\)/);
assert.match(css, /\.app-shell\.is-disconnected > \.mobile-app-bar,[\s\S]*?\.app-shell\.is-disconnected > \.drawer,[\s\S]*?\.app-shell\.is-disconnected > \.drawer-backdrop,[\s\S]*?\.app-shell\.is-disconnected > \.message-launcher,[\s\S]*?\.app-shell\.is-disconnected > \.mobile-message-footer \{ display:none; \}/);
assert.match(css, /\.app-shell\.is-disconnected \.workspace > :not\(#connection-state\) \{ display:none; \}/);
assert.doesNotMatch(indexHtml, /id="system-health-control"/);
assert.match(indexHtml, /id="view-diagnostics"[^>]*aria-labelledby="tab-diagnostics"[\s\S]*?System health[\s\S]*?Diagnostics/);
assert.match(indexHtml, /id="snapshot-status-dot"[^>]*class="status-dot is-reconnecting"|class="status-dot is-reconnecting" id="snapshot-status-dot"/);
assert.doesNotMatch(indexHtml, /class="snapshot-status"|>System healthy</);
for (const status of ["Live", "Reconnecting", "Offline"]) assert.match(app, new RegExp(`(?:title|snapshot)\\.textContent = [^;\\n]*"${status}`));
assert.match(css, /\.status-dot\.is-reconnecting/);
assert.match(css, /\.status-dot\.is-offline/);

for (const [tab, icon] of [["overview", "layout-dashboard"], ["agents", "users"], ["labs", "flask-conical"], ["roles", "list-tree"], ["review", "shield-check"], ["assets", "image"], ["diagnostics", "activity"], ["settings", "settings"]]) {
  assert.match(indexHtml, new RegExp(`id="tab-${tab}"[\\s\\S]*?<use href="#lucide-${icon}"></use>`));
  assert.match(indexHtml, new RegExp(`id="lucide-${icon}" viewBox="0 0 24 24"`));
}
for (const retiredTab of ["dashboard", "hierarchy", "kanban"]) assert.doesNotMatch(indexHtml, new RegExp(`id="tab-${retiredTab}"`));
assert.doesNotMatch(indexHtml, />Graph<\/b>|data-view="graph"/);
assert.doesNotMatch(indexHtml, /[⌂▦⑂▥⊙⚙]/);
assert.match(indexHtml, /id="mobile-menu-button"[^>]*aria-label="Open navigation"[^>]*aria-expanded="false"[^>]*aria-controls="console-drawer"/);
assert.match(indexHtml, /class="mobile-app-bar"[\s\S]*?<img src="\/assets\/swarm-wordmark\.png" alt="SWARM"/);
assert.match(indexHtml, /class="drawer-head"[\s\S]*?class="brand-wordmark"[^>]*alt="SWARM"[\s\S]*?id="drawer-close"[^>]*aria-label="Close navigation"/);
assert.doesNotMatch(indexHtml, /id="refresh"|Refresh overview/);
assert.doesNotMatch(app, /\$\("#refresh"\)/);
assert.match(app, /\$\("#drawer-close"\)\.addEventListener\("click", \(\) => setMobileDrawer\(false, true\)\)/);
assert.match(indexHtml, /<title>SWARM HQ<\/title>/);
assert.match(indexHtml, /id="overview-monitoring-heading">Swarm<\/h2>[\s\S]*?id="overview-summary">Loading swarm<\/p>/);
assert.match(app, /function composeDocumentTitle\(\)/);
assert.doesNotMatch(app, /navigator\.onLine/);
assert.doesNotMatch(indexHtml + app, /Control Console/i);
assert.doesNotMatch(indexHtml + css, /brand-hq/);
assert.match(css, /--coral: #FF3D32;/);
assert.equal((indexHtml.match(/class="nav-list"/g) || []).length, 1);
assert.match(indexHtml, /class="nav-footer"[\s\S]*?id="tab-settings"/);
assert.match(indexHtml, /class="top-actions"[\s\S]*?id="notifications"[\s\S]*?class="profile-button topbar-profile circle-frame" id="profile"/);
assert.match(indexHtml, /class="topbar"[\s\S]*?class="header-toolbar"[\s\S]*?id="ask-anything-form"[\s\S]*?class="top-actions"[\s\S]*?id="view-title"/);
assert.doesNotMatch(indexHtml, /<span>Project scope<\/span>/);
assert.doesNotMatch(indexHtml + app + css, /quick-help/);
assert.equal((indexHtml.match(/id="lucide-heart"/g) || []).length, 1);
assert.equal((indexHtml.match(/id="lucide-chevron-down"/g) || []).length, 1);
assert.doesNotMatch(indexHtml, /swarm-octopus-outline/);
assert.match(indexHtml, /id="project-scope-filter"[\s\S]*?<use href="#lucide-chevron-down"><\/use>/);
assert.doesNotMatch(indexHtml.slice(indexHtml.indexOf('<aside class="drawer"'), indexHtml.indexOf('<main class="workspace">')), /drawer-status|data-status-(?:dot|title|note)|>Live</);
assert.match(indexHtml, /id="tab-overview"[\s\S]*?<b>Overview<\/b>/);
assert.equal((indexHtml.match(/id="project-navigation-heading"/g) || []).length, 1);
assert.match(indexHtml, /<a id="project-navigation-heading" href="\.\/#overview" aria-label="All projects">Projects<\/a>[\s\S]*?id="project-create"[^>]*aria-label="Create project"[\s\S]*?id="project-navigation"/);
assert.match(css, /\.project-navigation-header > a \{[^}]*min-height:44px;[^}]*color:var\(--faint\);[^}]*text-decoration:none;[^}]*text-transform:uppercase;/);
assert.match(css, /\.project-navigation-header > a:focus-visible \{ outline:2px solid #fff;/);
assert.match(indexHtml, /<details class="polished-select scope-selector" id="project-scope-selector">[\s\S]*?id="project-scope-filter" aria-label="Project scope"[^>]*aria-haspopup="listbox"[\s\S]*?id="project-scope-options" role="listbox"/);
assert.doesNotMatch(indexHtml, /<select[^>]*id="project-scope-filter"/);
assert.match(indexHtml, /id="notifications"[^>]*aria-label="Notifications"/);
assert.match(indexHtml, /id="profile"[^>]*aria-label="Open profile"[^>]*title="Profile"/);
assert.match(indexHtml, /id="notifications"[^>]*class="[^"]*circle-frame[^"]*"|class="[^"]*circle-frame[^"]*"[^>]*id="notifications"/);
assert.match(indexHtml, /id="profile"[^>]*>[\s\S]*?id="profile-initials"[\s\S]*?id="profile-button-placeholder"[\s\S]*?<use href="#lucide-user-round"><\/use>/);
assert.match(indexHtml, /id="profile-avatar-placeholder"[^>]*>[\s\S]*?<use href="#lucide-user-round"><\/use>/);
assert.doesNotMatch(indexHtml, /id="profile"[^>]*>[\s\S]*?<span>Profile<\/span>/);
assert.match(indexHtml, /class="profile-button topbar-profile circle-frame"[^>]*id="profile"/);
assert.match(css, /\.topbar-profile \{[^}]*font-size:10px;/);
assert.match(indexHtml, /id="support-open"[^>]*aria-haspopup="dialog"[^>]*aria-controls="support-dialog"[\s\S]*?<use href="#lucide-heart"><\/use>[\s\S]*?Support SWARM/);
assert.match(indexHtml, /id="support-dialog"[^>]*aria-labelledby="support-dialog-title"[^>]*aria-describedby="support-dialog-description support-status"/);
assert.match(indexHtml, /src="\/assets\/support-caricature-light\.webp"[^>]*width="800"[^>]*height="800"/);
assert.doesNotMatch(indexHtml, /Buy me a coffee|Continue with Stripe|USD (?:5|10|20)|Address not configured|support-amount/);
assert.match(indexHtml, /href="https:\/\/x\.com\/PeikGabriel"[^>]*target="_blank"[^>]*rel="noopener noreferrer"[^>]*aria-label="X, @PeikGabriel"[\s\S]*?class="support-brand-icon"/);
assert.match(indexHtml, /href="https:\/\/github\.com\/peikgabriel"[^>]*target="_blank"[^>]*rel="noopener noreferrer"[^>]*aria-label="GitHub, @peikgabriel"[\s\S]*?class="support-brand-icon"/);
assert.equal((indexHtml.match(/class="support-brand-icon"/g) || []).length, 2);
assert.match(css, /\.support-brand-icon \{[^}]*width:18px; height:18px;[^}]*fill:currentColor/);
assert.match(indexHtml, /id="support-status"[^>]*>Stripe checkout is not available yet\./);
assert.match(css, /\.support-dialog \{[^}]*width:min\(760px,calc\(100vw - 32px\)\);[^}]*height:min\(520px,calc\(100dvh - 32px\)\)/);
assert.match(css, /\.support-dialog-content \{[^}]*grid-template-columns:minmax\(240px,\.9fr\) minmax\(280px,1\.1fr\)/);
assert.match(css, /@media \(max-width:620px\)[\s\S]*?\.support-dialog \{ width:100vw; height:100dvh; border:0; border-radius:0; \}/);
assert.match(app, /function openSupport\(trigger\)[\s\S]*?dialog\.showModal\(\)[\s\S]*?function closeSupport\(restoreFocus = true\)/);
assert.match(app, /\$\("#support-dialog"\)\.addEventListener\("click", \(event\) => \{ if \(event\.target === event\.currentTarget\) closeSupport\(\); \}\)/);
assert.doesNotMatch(css, /\.drawer-status/);
assert.match(indexHtml, /id="message-launcher"[^>]*aria-label="Message"[^>]*aria-controls="message-composer"[^>]*aria-expanded="false"/);
assert.match(indexHtml, /id="mobile-message-action"[^>]*aria-label="Message"[^>]*aria-controls="message-composer"/);
assert.match(indexHtml, /class="mobile-message-footer" aria-label="Primary navigation"[\s\S]*?data-view="overview"[\s\S]*?data-view="agents"[\s\S]*?id="mobile-message-action"[\s\S]*?message-mascot-silhouette[\s\S]*?data-view="assets"[\s\S]*?data-view="roles"/);
assert.match(indexHtml, /<dialog class="message-composer" id="message-composer" aria-modal="false"[^>]*aria-labelledby="message-title"/);
assert.match(app, /function showMessageComposerDialog\(\)[\s\S]*?panel\.showModal\(\)[\s\S]*?panel\.show\(\)/);
assert.match(app, /history\.pushState\(\{ \.\.\.\(history\.state \|\| \{\}\), messageComposer: true \}/);
assert.match(indexHtml, /<h2 id="message-title">Message<\/h2>/);
assert.match(indexHtml, /<header class="message-composer-header">[\s\S]*?id="message-recipient"[\s\S]*?<\/header>/);
assert.match(indexHtml, /class="message-composer-body edge-scroll">[\s\S]*?id="message-conversation-state" role="status"[\s\S]*?id="message-conversation-items" role="log" aria-label="Messages"/);
assert.doesNotMatch(indexHtml, /HQ does not expose a conversation-history feed|Messages will appear here when conversation access is available/);
assert.match(indexHtml, /<footer class="message-composer-footer">[\s\S]*?id="message-draft"[^>]*maxlength="4000"[\s\S]*?id="message-status"/);
assert.match(indexHtml, /id="message-send"[^>]*aria-label="Send message"[^>]*disabled[^>]*aria-disabled="true"/);
assert.match(indexHtml, /Messaging is unavailable until SWARM exposes the authenticated HQ connector\./);
assert.match(css, /\.message-launcher \{[^}]*position:fixed;[^}]*width:64px; height:64px;[^}]*border-radius:50%;[^}]*linear-gradient\(135deg,var\(--orange\),var\(--coral\)\)/);
assert.match(css, /\.message-mascot-silhouette \{[^}]*mask:url\("\/assets\/swarm-mascot-512\.png"\)/);
assert.match(css, /\.message-composer \{[^}]*grid-template-rows:auto minmax\(0,1fr\) auto;[^}]*overflow:hidden/);
assert.match(css, /\.message-composer:not\(\[open\]\) \{ display:none; \}/);
assert.match(css, /\.message-composer-body \{[^}]*min-height:0;[^}]*overflow-x:hidden; overflow-y:auto;/);
assert.match(css, /\.message-composer-header \{[^}]*grid-template-columns:auto minmax\(130px,1fr\) 44px/);
assert.match(css, /\.message-composer-footer \{[^}]*display:grid;[^}]*border-top:1px solid var\(--line\)/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*?\.message-launcher \{ display:none; \}[\s\S]*?\.mobile-message-footer \{[^}]*display:grid;/);
const messageSource = app.match(/function messageRecipients\(\)[\s\S]*?async function sendMessageFromComposer\([^)]*\)[\s\S]*?\n\}/)?.[0] || "";
assert.match(messageSource, /record\.structuralRole === "CTRL"/);
assert.doesNotMatch(messageSource, /"LEAD"/);
assert.match(messageSource, /record\.identityState === "admitted" && record\.binding/);
assert.match(messageSource, /action_kind: "send_feedback"/);
assert.match(messageSource, /MESSAGE_CONNECTOR_UNAVAILABLE/);
assert.match(messageSource, /manifest_id:[\s\S]*?manifest_digest:[\s\S]*?view_digest:[\s\S]*?source_digests:[\s\S]*?observed_cursor:/);
assert.match(messageSource, /request_id: requestId[\s\S]*?attachments,/);
assert.match(messageSource, /await api\(state\.messageConnector\.endpoint/);
assert.doesNotMatch(messageSource, /fetch\(|localStorage|sessionStorage|setInterval|WebSocket/);
assert.match(app, /function messageConnectorCapability\(bootstrap\)[\s\S]*?swarm\.universal_hq_connector\.action\.v1/);
assert.match(app, /function canonicalActionValue\(value\)[\s\S]*?Object\.keys\(value\)\.sort\(\)/);
assert.match(app, /function messageActionDigest\(envelope\)[\s\S]*?window\.crypto\.subtle\.digest\("SHA-256", bytes\)/);
assert.match(app, /function messageReceiptPresentation\(result, request\)[\s\S]*?actionDigest !== expectedDigest[\s\S]*?\["ACKNOWLEDGED", "REPLAYED"\][\s\S]*?\["STALE", "CONFLICT"\]/);
assert.match(app, /request = \{ \.\.\.envelope, action_digest: await messageActionDigest\(envelope\) \}/);
assert.match(app, /\$\("#profile"\)\.addEventListener\("click", \(event\) => openProfile\(event\.currentTarget\)\)/);
assert.match(app, /\$\("#profile-form"\)\.addEventListener\("submit", saveProfile\)/);
assert.match(app, /\$\("#profile-dialog"\)\.addEventListener\("toggle", \(event\) => \{[\s\S]*?closeProfile\(false\)/);
assert.match(app, /function reviewDiagnosticWithCtrl\(checkId\)/);
assert.match(app, /data-diagnostic-review/);
assert.doesNotMatch(indexHtml, /Choose recommended|diagnostics-auto-fix|id="diagnostics-repair"/);
assert.doesNotMatch(indexHtml, /data-diagnostic-check|type="checkbox"[^>]*diagnostic/);
for (const id of ["diagnostics-health-heading", "diagnostics-check-strip", "diagnostics-signal-list", "diagnostics-health-trend", "diagnostics-log-list", "diagnostics-check-list"]) assert.match(indexHtml, new RegExp(`id="${id}"`));
assert.match(app, /\$\("#repair-dialog"\)\.addEventListener\("cancel", \(event\) => \{[\s\S]*?closeRepairDialog\(\)/);
for (const icon of ["eye", "trash-2"]) assert.match(indexHtml, new RegExp(`id="lucide-${icon}" viewBox="0 0 24 24"`));
assert.match(indexHtml, /id="onboarding-dialog"[^>]*aria-labelledby="onboarding-dialog-title"[^>]*aria-describedby="onboarding-step-status"/);
assert.equal((indexHtml.match(/<dialog\b/g) || []).length, 11);
assert.match(indexHtml, /<div popover="auto" role="dialog" class="profile-dialog"/);
for (const shell of ["agent-detail-shell", "evidence-lightbox-shell", "asset-dialog-shell", "profile-dialog-shell", "support-dialog-shell", "project-create-shell", "repair-dialog-shell", "config-editor-shell", "role-editor-shell", "onboarding-shell"]) {
  assert.match(indexHtml, new RegExp(`class="dialog-shell ${shell}"`));
}
assert.equal((indexHtml.match(/class="dialog-body(?: |")/g) || []).length, 11);
assert.equal((indexHtml.match(/class="dialog-body-content/g) || []).length, 11);
assert.equal((indexHtml.match(/class="dialog-footer(?: |")/g) || []).length, 11);
assert.match(css, /\.dialog-shell \{[^}]*grid-template-rows:auto minmax\(0,1fr\) auto;[^}]*overflow:hidden;[^}]*padding:0;/);
assert.match(css, /\.dialog-body \{[^}]*width:100%;[^}]*min-height:0;[^}]*overflow-x:hidden; overflow-y:auto;[^}]*scrollbar-gutter:stable;[^}]*padding:0;/);
assert.match(css, /\.dialog-body-content \{ width:100%; min-width:0; \}/);
assert.match(css, /\.repair-dialog \{[^}]*width:min\(760px,calc\(100vw - 32px\)\);[^}]*height:min\(650px,calc\(100dvh - 32px\)\);[^}]*overflow:hidden/);
assert.match(css, /\.repair-dialog-content \{[^}]*display:grid;[^}]*gap:18px;[^}]*padding:20px 24px/);
assert.match(css, /\.repair-acknowledgement \{[^}]*min-height:44px/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*?\.repair-dialog \{ width:100vw; height:100dvh; border:0; border-radius:0; \}/);
assert.match(css, /\.evidence-lightbox-thumbnails \{ overflow-x:auto; overflow-y:hidden; \}/);
assert.match(css, /\.role-editor-fields \{ overflow:visible; \}/);
assert.match(css, /\.onboarding-panels \{ place-items:initial; overflow-x:hidden; overflow-y:auto; \}/);
assert.match(css, /\.onboarding-configuration \{ overflow:visible;[^}]*scrollbar-gutter:auto;/);
assert.match(indexHtml, /id="onboarding-step-status" aria-live="polite">Welcome\. Step 1 of 5\.<\/p>/);
const onboardingWithoutNonvisualStatus = indexHtml.replace(/<p class="sr-only" id="onboarding-step-status"[\s\S]*?<\/p>/, "");
assert.doesNotMatch(onboardingWithoutNonvisualStatus, /Step [1-5] of 5/i);
assert.equal((indexHtml.match(/data-onboarding-step=/g) || []).length, 5);
assert.match(indexHtml, /data-onboarding-step="0"[^>]*aria-label="Show welcome"[^>]*aria-controls="onboarding-panel-1"[^>]*aria-selected="true"[^>]*aria-current="step"/);
for (const control of ["onboarding-close", "onboarding-back", "onboarding-skip", "onboarding-primary"]) assert.match(indexHtml, new RegExp(`id="${control}"[^>]*type="button"`));
assert.match(indexHtml, /SWARM coordinates focused roles, clear ownership, and proof you can review\./);
assert.match(css, /\.onboarding-dialog \{ position:fixed; inset:0; width:min\(1040px,calc\(100vw - 48px\)\); height:min\(720px,calc\(100dvh - 48px\)\);/);
assert.match(css, /\.onboarding-shell \{ padding:0; \}/);
assert.match(css, /\.onboarding-header \{ padding:clamp\(16px,2\.2vw,28px\) clamp\(16px,2\.2vw,28px\) 8px; \}/);
assert.match(css, /\.onboarding-panels-content \{[^}]*padding:10px clamp\(16px,2\.2vw,28px\);/);
assert.match(css, /\.onboarding-slide1-guide \{[^}]*width:min\(680px,100%\);[^}]*object-fit:contain;/);
assert.match(indexHtml, /class="onboarding-body-nav" id="onboarding-body-nav" hidden>[\s\S]*?id="onboarding-back"[^>]*aria-label="Back"[\s\S]*?#lucide-chevron-right/);
assert.doesNotMatch(indexHtml.match(/<footer class="dialog-footer onboarding-actions">[\s\S]*?<\/footer>/)?.[0] || "", /id="onboarding-back"|>Back</);
assert.doesNotMatch(indexHtml.replace(/aria-label="Back"/g, ""), />\s*Back\s*</);
assert.match(css, /\.onboarding-body-nav \{[^}]*position:sticky;[^}]*top:0;[^}]*height:0;[^}]*pointer-events:none;/);
assert.match(css, /\.onboarding-body-back \{ width:44px; height:44px; pointer-events:auto; \}/);
assert.match(css, /\.onboarding-body-back \.lucide \{ transform:rotate\(180deg\); \}/);
assert.match(css, /\.onboarding-actions \{[^}]*display:grid;[^}]*grid-template-columns:minmax\(44px,1fr\) minmax\(220px,auto\) minmax\(44px,1fr\);/);
assert.match(css, /\.onboarding-actions \.onboarding-skip \{ grid-column:2; grid-row:2;[^}]*\}/);
assert.match(css, /\.onboarding-actions \.primary-action \{ grid-column:2; grid-row:1;[^}]*\}/);
assert.match(indexHtml, /id="onboarding-close"[^>]*aria-label="Close onboarding"/);
assert.match(indexHtml, /class="onboarding-slide1-guide onboarding-artwork" src="\/assets\/swarm-guided-tour-slide1\.png" width="1920" height="1080" alt="" aria-hidden="true" loading="eager" fetchpriority="high" decoding="sync"/);
assert.match(indexHtml, /<link rel="icon" type="image\/png" sizes="64x64" href="\/swarm-icon-64\.png"/);
assert.doesNotMatch(indexHtml, /swarm-favicon\.svg|<div class="onboarding-mascot"/);
 assert.match(indexHtml, /<h2>One goal\. A coordinated team\.<\/h2>/);
 assert.match(indexHtml, /<p>SWARM turns a clear request into owned work, handoffs, and review\.<\/p>/);
assert.match(indexHtml, /class="onboarding-flow-scene onboarding-artwork" aria-label="A prompt goes to CTRL, which coordinates Designer, Developer, and Reviewer roles\."/);
assert.match(indexHtml, /class="onboarding-flow-node is-prompt">Prompt<[\s\S]*?class="onboarding-flow-node is-ctrl">CTRL<[\s\S]*?<b>Designer<\/b><b>Developer<\/b><b>Reviewer<\/b>/);
assert.doesNotMatch(indexHtml + app + css, /onboarding-coordination|ONBOARDING_COORDINATION|data-onboarding-edge|data-onboarding-node|onboardingFlowZoom|onboarding-flow-toolbar/);
assert.doesNotMatch(indexHtml, /role="tree"|Flowchart zoom|Zoom in|Zoom out/);
assert.match(indexHtml, /<h2>A role for every kind of work\.<\/h2>/);
assert.match(indexHtml, /24 curated roles, ready to work—from development and design to security and content\./);
const onboardingRolePanel = indexHtml.match(/id="onboarding-panel-3"[\s\S]*?<\/section>/)?.[0] || "";
assert.match(onboardingRolePanel, /class="onboarding-role-group onboarding-artwork" src="\/assets\/swarm-guided-tour-role-group\.png" width="1920" height="1080" alt="Developer, Designer, Architect, and Reviewer SWARM roles"/);
assert.equal((onboardingRolePanel.match(/<img\b/g) || []).length, 1);
assert.doesNotMatch(onboardingRolePanel, /onboarding-role-assets-blocker|data-role-media|role="list"|<article/);
assert.doesNotMatch(css, /onboarding-role-assets-blocker/);
assert.doesNotMatch(app, /ONBOARDING_ROLE_IDS|onboardingRoleExamplesMarkup|renderOnboardingRoleExamples/);
assert.doesNotMatch(css, /onboarding-role-examples|onboarding-role-media/);
assert.match(indexHtml, /class="onboarding-panel onboarding-panel-role-group"/);
assert.match(css, /\.onboarding-role-group \{ display:block; width:min\(700px,100%\);/);
assert.match(css, /--motion-enter-duration: 220ms;[\s\S]*?--motion-enter-distance: 8px;[\s\S]*?--motion-stagger: 55ms;/);
assert.match(css, /@keyframes swarm-enter \{ from \{ opacity:0; transform:translateY\(var\(--motion-enter-distance\)\); \} to \{ opacity:1; transform:translateY\(0\); \} \}/);
assert.match(css, /\.view\.is-active:not\(\[hidden\]\) \{ animation:swarm-enter var\(--motion-enter-duration\) var\(--motion-ease\) both; \}/);
assert.match(css, /#onboarding-primary \{ --motion-enter-delay:calc\(var\(--motion-stagger\) \* 4\); \}[\s\S]*?#onboarding-skip \{ --motion-enter-delay:calc\(var\(--motion-stagger\) \* 5\); \}/);
assert.match(css, /@media \(prefers-reduced-motion: reduce\)[\s\S]*?animation:none!important; opacity:1!important; transform:none!important;/);
const onboardingMotionSource = app.match(/function updateOnboardingEntrance\(step\) \{[\s\S]*?\n\}/)?.[0] || "";
assert.match(onboardingMotionSource, /dialog\.dataset\.motionStep === motionStep/);
assert.match(onboardingMotionSource, /dialog\.classList\.remove\("is-step-entering"\)[\s\S]*?void dialog\.offsetWidth;[\s\S]*?dialog\.classList\.add\("is-step-entering"\)/);
assert.doesNotMatch(onboardingMotionSource, /setTimeout|setInterval|requestAnimationFrame/);
 assert.match(indexHtml, /<h2>Choose how SWARM works\.<\/h2>/);
 assert.match(indexHtml, /Set the few defaults that keep work moving, then change them any time in Settings\./);
const projectViewsPanel = indexHtml.match(/id="onboarding-panel-4"[\s\S]*?<\/section>/)?.[0] || "";
assert.match(projectViewsPanel, /<img class="onboarding-project-tool onboarding-supporting-visual" src="\/assets\/swarm-guided-tour-project-tool\.png" width="1536" height="1024" alt="The orange SWARM mascot controls connected flowchart, timeline, asset-library, and table views\." loading="eager" decoding="sync" \/>/);
assert.equal((projectViewsPanel.match(/<img\b/g) || []).length, 1);
assert.doesNotMatch(projectViewsPanel, /onboarding-project-views|Your project finds its shape|App map|Shared data/);
assert.doesNotMatch(projectViewsPanel, /manifest|schema|digest|source of truth/i);
assert.match(indexHtml, /id="onboarding-panel-5"[\s\S]*?<h2>Choose how SWARM works\.<\/h2>[\s\S]*?id="onboarding-configuration"/);
assert.doesNotMatch(indexHtml, /class="onboarding-(topology|evidence)"/);
assert.equal((indexHtml.match(/swarm-mascot-512\.png/g) || []).length, 1);
assert.match(app, /const ONBOARDING_STEPS = \[/);
assert.match(app, /function renderOnboarding\(\)/);
assert.match(app, /dot\.toggleAttribute\("aria-current", selected\)/);
assert.match(app, /if \(selected\) dot\.setAttribute\("aria-current", "step"\)/);
assert.match(app, /panel\.hidden = !selected/);
assert.match(app, /function setOnboardingStep\(step, focusDot = false, focusNavigation = ""\)/);
assert.match(app, /const changed = nextStep !== state\.onboardingStep[\s\S]*?if \(changed\) \$\("\.dialog-body", \$\("#onboarding-dialog"\)\)\.scrollTop = 0/);
assert.match(app, /state\.onboardingStep === ONBOARDING_STEPS\.length - 1/);
assert.match(app, /state\.onboardingTrigger\?\.focus/);
assert.match(app, /const ONBOARDING_PRESENTATION_KEY = "swarm\.onboarding\.v2\.seen"/);
assert.match(app, /\{ name: "Configuration", primary: "Start using SWARM" \}/);
assert.match(app, /function onboardingConfigurationMarkup\(\)/);
assert.match(app, /function onboardingControlIdentity\(element\)/);
assert.match(app, /function onboardingControlForIdentity\(root, identity\)/);
assert.match(app, /element\.matches\("summary"\)[\s\S]*?return "summary:" \+ summaryOwner\.dataset\.onboardingControl/);
assert.match(app, /kind === "summary"[\s\S]*?querySelector\("summary"\)/);
assert.match(app, /function saveOnboardingConfig\(key, value\)/);
assert.match(app, /let configMutationTail = Promise\.resolve\(\)/);
assert.match(app, /let configAuthorityGeneration = 0/);
assert.match(app, /function configWriteRequest\(text, projection = state\.config\)[\s\S]*?payload: \{ scope, expected_revision: projection\.revision, acknowledge: true, text, operation_id: operationId \}/);
assert.match(app, /function saveConfigText\(text\)[\s\S]*?configAuthorityGeneration \+= 1[\s\S]*?configMutationTail = operation\.then/);
assert.match(app, /function saveConfigMutation\(changes\) \{\s*return saveConfigText\(\(\) => configTextWithChanges\(state\.config\?\.editable_text, changes\)\);\s*\}/);
assert.match(app, /function configWriteReceiptMatches\(result, request\)[\s\S]*?JSON\.stringify\(receipt\?\.scope\) === request\.binding[\s\S]*?receipt\?\.acknowledged === true[\s\S]*?receipt\?\.operation_id === request\.operationId[\s\S]*?receipt\?\.expected_revision === request\.payload\.expected_revision/);
assert.match(app, /receipt\?\.action === \(request\.action \|\| "config_update"\)[\s\S]*?typeof receipt\?\.replayed === "boolean"/);
assert.match(app, /retry\?\.exhausted[\s\S]*?const operationId = retry\?\.operationId \|\| configWriteOperationId\(\)/);
assert.match(app, /if \(request\) configWriteRetry = uncertain \? \{ identity: request\.identity, operationId: request\.operationId, exhausted: request\.uncertainRetry \} : null/);
assert.match(app, /function saveCurrentConfigMutation\(changes\)[\s\S]*?if \(!result\.applied\) throw new Error\("Settings scope changed before the save was acknowledged\. Your unsaved changes are preserved\."\)/);
assert.match(app, /error\?\.status === 409[\s\S]*?unsaved changes are preserved[\s\S]*?Retry will reuse this exact operation/);
assert.doesNotMatch(app, /body: JSON\.stringify\(\{ changes \}\)/);
assert.match(app, /function readConfigState\(previousConfig = state\.config, saveError = ""\)[\s\S]*?let pendingWrites = configMutationTail[\s\S]*?while \(pendingWrites !== configMutationTail\)[\s\S]*?const generation = configAuthorityGeneration[\s\S]*?generation !== configAuthorityGeneration/);
assert.match(app, /function configResetRequest\(kind\)[\s\S]*?endpoint: "\/api\/settings\/restore"[\s\S]*?scope: \{ type: "global" \}[\s\S]*?expected_revision: projection\.revision[\s\S]*?acknowledge: true/);
assert.match(app, /function configResetRequest\(kind\)[\s\S]*?endpoint: "\/api\/config\/reset"[\s\S]*?accepted_cursor: structuredClone\(scope\.accepted_cursor\)[\s\S]*?expected_revision: projection\.revision/);
assert.match(app, /function configResetRequest\(kind\)[\s\S]*?endpoint: "\/api\/ctrl-settings\/reset"[\s\S]*?ctrl_id: String\(setting\.ctrl_id\)[\s\S]*?expected_revision: setting\.revision[\s\S]*?acknowledge: true/);
assert.match(app, /function resetSettingsScope\(kind\)[\s\S]*?configResetRetry\?\.key === key[\s\S]*?operation_id: operationId[\s\S]*?configMutationTail\.then[\s\S]*?configResetBindingIsCurrent\(request\)/);
assert.match(app, /state\.configResetRetry = error\?\.connectionFailure === true \|\| !Number\.isInteger\(error\?\.status\) \? \{ key, operationId, exhausted: Boolean\(retainedRetry\) \} : null/);
assert.doesNotMatch(app, /api\('\/api\/settings\/restore', \{ method: 'POST' \}\)|JSON\.stringify\(\{ ctrl_id: state\.ctrlSettings\.ctrl_id, expected_revision: state\.ctrlSettings\.revision \}\)/);
assert.match(app, /function observedTimestampMs\(value\)[\s\S]*?numeric < 1e12 \? numeric \* 1000 : numeric[\s\S]*?Date\.UTC\(2000, 0, 1\)/);
assert.match(app, /state\.onboardingConfigPending\.set\(key, \{ value, focusIdentity \}\)/);
assert.match(app, /state\.onboardingConfigFailures\.set\(key, \{ value, error:/);
assert.match(app, /configEditable\("automation\.mode"\) && !state\.onboardingConfigPending\.has\("automation\.mode"\)/);
assert.match(app, /if \(state\.onboardingStep === ONBOARDING_STEPS\.length - 1 && onboardingConfigBlocked\(\)\) return false/);
assert.match(app, /\$\("#onboarding-primary"\)\.disabled = blocked/);
assert.match(app, /const laterStep = step > 0;[\s\S]*?\$\("#onboarding-body-nav"\)\.hidden = !laterStep;[\s\S]*?\$\("#onboarding-skip"\)\.hidden = laterStep;/);
assert.match(app, /setOnboardingStep\(state\.onboardingStep - 1, false, "back"\)/);
assert.match(app, /data-onboarding-control="retry-config">Retry/);
const onboardingCloseSource = app.slice(app.indexOf('$("#onboarding-dialog").addEventListener("close"'), app.indexOf('$("#evidence-lightbox").addEventListener("close"'));
assert.doesNotMatch(onboardingCloseSource, /markOnboardingSeen/);
assert.match(onboardingCloseSource, /addEventListener\("cancel"[\s\S]*?event\.preventDefault\(\)[\s\S]*?onboardingCanDismiss\(\)/);
assert.match(app, /function settingsSpeedMarkup\(options = \{\}\)/);
assert.match(app, /choice\("Default"[\s\S]*?choice\("Fast"/);
assert.doesNotMatch(app, /choice\("Ultrafast"/);
assert.match(app, /function settingsTaskLifeMarkup\(options = \{\}\)/);
assert.match(app, /ONBOARDING_TASK_LIFE_DETENTS = \[[\s\S]*?hours: 1[\s\S]*?hours: 2[\s\S]*?hours: 4[\s\S]*?hours: 24[\s\S]*?hours: 720/);
assert.match(app, /data-config-values="["'] \+ ONBOARDING_TASK_LIFE_DETENTS/);
assert.match(app, /type="range" min="0" max="4" step="1"/);
assert.match(app, /aria-valuetext=/);
assert.match(app, /Short clears context sooner to keep work efficient, with more handovers\.[\s\S]*?Balanced hands over when task efficiency begins to drop\.[\s\S]*?Long reduces handovers, while a larger context can become less efficient over time\./);
assert.match(app, /data-onboarding-control="task-life-info"[\s\S]*?aria-label="About task life"[\s\S]*?role="tooltip"/);
assert.match(app, /const labels = \["Short", "Medium", "Balanced", "Long", "Unlimited"\]/);
assert.match(app, /settingsTaskLifeMarkup\(\{ value: life, editable:/);
const onboardingConfigSource = app.slice(app.indexOf("function onboardingConfigurationMarkup"), app.indexOf("\nfunction renderOnboarding", app.indexOf("function onboardingConfigurationMarkup")));
assert.match(onboardingConfigSource, /class="settings-essentials onboarding-config-essentials"/);
assert.match(onboardingConfigSource, /id="onboarding-advanced-settings"[\s\S]*?data-onboarding-control="advanced-settings-link"[\s\S]*?>Advanced settings<\/button>/);
assert.doesNotMatch(onboardingConfigSource, /onboarding-config-advanced|onboarding-advanced-content|Minimum model|Maximum model|Usage Saver|Use ChatGPT|Automatic health checks|Parallel lanes/);
assert.doesNotMatch(app, /data-onboarding-control="usage-policy"|onboarding-config-group|onboarding-config-wide/);
assert.doesNotMatch(app, /artifact-13|config-usage-first/i);
assert.match(app, /function openAdvancedSettingsFromOnboarding\(\)[\s\S]*?setView\('settings', false, false\)[\s\S]*?writeRoute\('push', 'settings-advanced'\)[\s\S]*?const editConfig = \$\('#settings-edit-config'\)[\s\S]*?editConfig\?\.focus/);
assert.match(app, /if \(view === "settings-advanced"\) return "settings"/);
 assert.match(app, /class="panel settings-advanced-drawer" id="settings-advanced"/);
assert.match(app, /function openOnboarding\(force = false, trigger = null\)/);
assert.match(app, /\(!force && \(state\.onboardingShown \|\| onboardingSeen\(\)\)\)/);
assert.match(app, /data-setting-action="replay-tour" type="button">Replay tour<\/button>/);
assert.match(app, /if \(action === 'replay-tour'\)[\s\S]*openOnboarding\(true, event\.target\.closest\('\[data-setting-action\]'\)\)/);
const onboardingPersistenceStart = app.indexOf("function onboardingSeen");
const onboardingPersistenceEnd = app.indexOf("\nfunction openOnboarding", onboardingPersistenceStart);
{
  let finishRefresh, opened = 0, seen = false, otherDialog = false;
  const tourState = { overview: {}, messageOpen: false, onboardingShown: false };
  const dialog = { open: false, showModal() { this.open = true; opened++; }, close() { this.open = false; } };
  const sandbox = { state: tourState, HTMLElement: class {}, document: { activeElement: null, body: {} },
    $: selector => selector === '.workspace' ? {classList:{contains:()=>false}} : selector === 'dialog[open]' ? (otherDialog ? {} : null) : selector === '.dialog-body' ? {} : dialog,
    onboardingSeen: () => seen, markOnboardingSeen: () => { seen = true; }, ONBOARDING_STEPS: [1,2,3,4,5], onboardingConfigBlocked:()=>false,
    renderOnboarding(){}, updateDocumentTitle(){}, requestAnimationFrame(){}, setDataStatus(){},
    api: async()=>({}), messageConnectorCapability:()=>null, taskMessageCapability:()=>null, refreshOverview:()=>new Promise(resolve=>{finishRefresh=resolve;}) };
  vm.createContext(sandbox);
  vm.runInContext(app.slice(app.indexOf('function openOnboarding('),app.indexOf('function onboardingCanDismiss(')) + app.slice(app.indexOf('async function initialize()'),app.indexOf('let presenceTimer')),sandbox);
  const initialized = sandbox.initialize();
  await new Promise(resolve => setImmediate(resolve));
  tourState.messageOpen = true;
  finishRefresh(); await initialized;
  assert.equal(opened,0,'late initialization must not cover active Message');
  tourState.messageOpen = false; otherDialog = true; sandbox.openOnboarding();
  assert.equal(opened,0,'automatic tour must not cover another dialog');
  otherDialog = false; sandbox.openOnboarding(); assert.equal(opened,1,'first visit still opens');
  sandbox.closeOnboarding(); tourState.onboardingShown=false; sandbox.openOnboarding();
  assert.equal(opened,1,'explicit dismissal stays seen');
  sandbox.openOnboarding(true); assert.equal(opened,2,'manual replay stays available');
}
const onboardingPersistence = vm.runInNewContext(`(() => { const ONBOARDING_PRESENTATION_KEY = "swarm.onboarding.v2.seen"; ${app.slice(onboardingPersistenceStart, onboardingPersistenceEnd)}; return { onboardingSeen, markOnboardingSeen }; })()`);
const presentationValues = new Map([["unrelated.presentation", "preserve"]]);
const presentationStorage = { getItem: (key) => presentationValues.get(key) ?? null, setItem: (key, value) => presentationValues.set(key, value) };
assert.equal(onboardingPersistence.onboardingSeen(presentationStorage), false);
onboardingPersistence.markOnboardingSeen(presentationStorage);
assert.equal(onboardingPersistence.onboardingSeen(presentationStorage), true);
assert.equal(presentationValues.get("unrelated.presentation"), "preserve");
assert.equal(onboardingPersistence.onboardingSeen({ getItem() { throw new Error("unavailable"); } }), false);
assert.doesNotThrow(() => onboardingPersistence.markOnboardingSeen({ setItem() { throw new Error("unavailable"); } }));
assert.match(css, /\.onboarding-progress button \{[^}]*width:44px; height:44px/);
assert.match(css, /\.onboarding-panel-config \{ height:auto; min-height:100%; align-self:start; overflow:visible;/);
assert.match(css, /\.onboarding-config-essentials \{[^}]*padding:14px 16px/);
assert.match(css, /\.onboarding-advanced-link \{[^}]*min-height:44px/);
assert.doesNotMatch(css, /\.onboarding-config-advanced|\.onboarding-advanced-content|\.onboarding-advanced-group|\.onboarding-model-grid|\.onboarding-readonly/);
assert.match(css, /\.settings-config-entry \{[^}]*scroll-margin-top:72px/);
assert.match(css, /\.settings-task-life > input \{[^}]*height:44px;[^}]*accent-color:var\(--orange\)/);
assert.match(css, /\.settings-task-life-head summary \{[^}]*width:44px; height:44px/);
assert.doesNotMatch(css, /onboarding-segmented\.is-readonly/);
assert.doesNotMatch(css.match(/\.onboarding-panel-config[\s\S]*?\.onboarding-actions/)?.[0] || "", /accent-color:var\(--(?:cyan|blue)\)|box-shadow:inset 0 -2px var\(--(?:cyan|blue)\)/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.onboarding-dialog \{ width:100vw; height:100dvh;/);
assert.match(css, /--base: #091321;/);
assert.match(css, /--surface: rgba\(16, 29, 47, \.9\);/);
assert.match(css, /--muted: #c2cedd;/);
assert.match(css, /--shell-top: clamp\(20px, 2\.5vw, 32px\)/);
assert.match(css, /padding: max\(var\(--shell-top\), env\(safe-area-inset-top\)\)/);
assert.match(css, /body\.drawer-open,body\.role-detail-open \{ overflow:hidden; \}/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.mobile-app-bar \{ position:sticky;/);
assert.match(css, /\.app-shell\.is-drawer-open \.drawer \{ transform:translateX\(0\); \}/);
assert.match(app, /function setMobileDrawer\(open, restoreFocus = false\)/);
assert.match(app, /workspace\.inert = expanded/);
assert.match(app, /function mobileDrawerFocusable\(\)/);
assert.match(app, /event\.key === "Tab" && \$\("\.app-shell"\)\.classList\.contains\("is-drawer-open"\)/);
assert.match(app, /drawer\.inert = !expanded/);
assert.match(app, /event\.key === "Escape" && \$\("\.app-shell"\)\.classList\.contains\("is-drawer-open"\)/);

for (const label of ["Projects", "Latest updates", "Applies to", "Replay tour"]) {
  assert.match(indexHtml + app, new RegExp(label));
}
assert.match(app, /\/api\/usage-history\?/);
assert.match(app, /usageWindowHours: 1/);
assert.doesNotMatch(indexHtml, /usage-strip|usage-heading|usage-sparkline|usage-rate-sparkline|data-usage-hours/);
assert.doesNotMatch(css, /\.usage-strip|\.usage-chart-pair|\.usage-window-button/);
assert.doesNotMatch(app, /function renderUsage\(|function usageRateSeries\(|function downsampleSeries\(/);
assert.match(app, /function usageHistorySeries\(\)[\s\S]*?bucket_ms[\s\S]*?delta_tokens[\s\S]*?sort\(\(a, b\) => a\.bucket - b\.bucket\)/);
assert.match(app, /function renderUsageCharts\(\)[\s\S]*?diagnostics-usage-trend[\s\S]*?metric-detail-token-trend/);
assert.match(app, /\[1, 24, 168, 720\]\.includes\(hours\)[\s\S]*?await refreshUsageHistory\(\)/);
assert.doesNotMatch(app.slice(app.indexOf("function drawLine"), app.indexOf("function isSubagent")), /\[0, 0\]/);
assert.doesNotMatch(app, /setInterval\([^)]*usageHistory|setInterval\([^)]*refreshUsage/);
assert.match(indexHtml, /id="project-progress-section"/);
assert.match(app, /\/api\/project-progress-feed\?/);
assert.match(app, /\/api\/project-progress\?/);
assert.match(app, /function renderProjectProgressFeed\(\)/);
assert.doesNotMatch(app, /setInterval\([^)]*projectProgress|setInterval\([^)]*progressFeed/);
assert.doesNotMatch(indexHtml, /data-project-tab=/);
assert.doesNotMatch(indexHtml, /class="project-tabs"/);
assert.match(indexHtml, /id="project-detail" hidden aria-labelledby="project-detail-title"/);
assert.match(indexHtml, /id="project-tab-panel" role="region" aria-label="Project overview"/);
assert.match(app, /function renderProjectDetail\(\)/);
assert.match(app, /state\.projectTab = "overview";[\s\S]*?tabPanel\.innerHTML = projectTabMarkup\("overview", progress, nodes\)/);
assert.match(app, /const PROJECT_WORKSPACE_TAB_ICONS = new Map\(/);
assert.match(app, /function projectWorkspaceTabIcon\(view\)/);
assert.match(app, /function projectTabMarkup\(tab, progress, nodes\)/);
assert.match(app, /function currentProjectView\(\)/);
assert.match(app, /projection && projection\.project_id === projectId && projection\.tab\?\.id === "ui"/);
assert.match(app, /const workspaceViews = projectWorkspaceViews\(currentProjectView\(\)\);[\s\S]*?const workspaceView = workspaceViews\.find\(\(view\) => view\.id === tab\);[\s\S]*?projectWorkspaceTabMarkup\(workspaceView\)[\s\S]*?PROJECT_WORKSPACE_EMBEDDED_TABS\.get\(view\.id\) === tab/);
assert.match(app, /function openProjectViewEvidence\(screenKey, trigger\)/);
assert.match(app, /function projectViewRequirementGroup\(nodeIds\)/);
assert.match(app, /state\.evidenceImages = evidence\.map\(\(item\) => \(\{ \.\.\.item, project_requirement_summary: requirementSummary \}\)\)/);
assert.match(app, /item\.project_requirement_summary \? " · " \+ item\.project_requirement_summary/);
assert.match(app, /data-project-ui-mode=/);
assert.match(app, /data-project-view-evidence=/);
assert.match(app, /function projectViewMapModel\(projection, selectedGroupId = ""\)/);
assert.match(app, /class="project-ui-flowchart-connectors" aria-hidden="true"/);
assert.match(app, /data-project-map-group=/);
assert.match(app, /function drawProjectViewConnectors\(\)/);
assert.match(app, /const PROJECT_WORKSPACE_RENDERERS = new Set\(\["document\/blocks", "timeline\/milestones", "canvas\/network", "table\/records", "gallery\/grid", "gallery\/list"\]\)/);
assert.match(app, /function projectWorkspaceViews\(projection\)/);
assert.match(app, /function projectWorkspaceModeView\(projection, modeId,[\s\S]*?mode\?\.view_id[\s\S]*?view\.id === viewId/);
assert.doesNotMatch(app, /const manifestWorkspace =|uiTab\.hidden/);
assert.match(app, /projection\?\.status === "STALE_LAST_ACCEPTED"[\s\S]*Last accepted project brief snapshot/);
assert.match(app, /view\?\.content\?\.document[\s\S]*?document\?\.blocks/);
assert.match(app, /view\?\.content\?\.timeline[\s\S]*?timeline\?\.events/);
assert.match(app, /view\.renderer === "gallery" && view\.mode === "grid"[\s\S]*?Array\.isArray\(screens\)/);
assert.match(app, /function projectWorkspaceDocumentMarkup\(view\)/);
assert.match(app, /function projectWorkspaceTimelineMarkup\(view\)/);
assert.match(app, /function projectWorkspaceRecordsMarkup\(view\)/);
assert.match(app, /PROJECT_WORKSPACE_EMBEDDED_TABS[\s\S]*?view\.project\.overview-health[\s\S]*?view\.project\.roadmap/);
assert.match(app, /function projectWorkspaceWorkMarkup\(view\)/);
assert.match(app, /function projectWorkspaceArtifactsMarkup\(view\)/);
assert.match(app, /typeof candidate\.progress_percent === "number"/);
assert.match(app, /data-artifact-association=/);
assert.doesNotMatch(app, /projectId\s*===\s*["'](?:nemo|swarm|sanguine)["']/i);
assert.match(app, /function setProjectSelection\(projectId, ctrlId = ""\)[\s\S]*?state\.projectUiGroupId = ""/);
assert.match(app, /\$\$\('\[data-project-map-group\]'\)\.find\(\(element\) => element\.dataset\.projectMapGroup === previousGroupId\)/);
assert.doesNotMatch(app, /data-project-map-group=\\?"['"]?\s*\+\s*previousGroupId/);
assert.match(app, /\["runtime", "data", "state"\]\.includes\(node\.type\)/);
assert.match(app, /Flowchart unavailable\. The accepted map projection could not be rendered safely\./);
assert.doesNotMatch(app, /Sanguine|D&D|Dungeon|project:\/\/swarm/i);
assert.doesNotMatch(app, /setInterval\([^)]*projectView|localStorage[^\n]*projectView|sessionStorage[^\n]*projectView/i);
const projectWorkspaceSource = app.slice(app.indexOf("const PROJECT_WORKSPACE_RENDERERS"), app.indexOf("\nfunction projectWorkspaceFlowMarkup"));
const projectWorkspaceSandbox = {};
vm.runInNewContext(projectWorkspaceSource + "\nthis.projectWorkspaceViews = projectWorkspaceViews; this.projectWorkspaceModeView = projectWorkspaceModeView;", projectWorkspaceSandbox);
const projectedWorkspaceViews = [
  ["view.project.plan.master", "Master plan", "document", "blocks"],
  ["view.project.plan.roadmap", "Roadmap", "timeline", "milestones"],
  ["view.project.plan.flow", "Flowchart", "canvas", "network"],
  ["view.project.ui.screens", "Screens", "gallery", "grid"],
  ["view.project.ui.map", "Map", "canvas", "network"],
].map(([id, label, renderer, mode]) => ({ id, label, renderer, mode, content: {} }));
const projectedWorkspace = {
  modes: projectedWorkspaceViews.map((view) => ({ id: view.id.split(".").at(-1), view_id: view.id, label: view.label, renderer: view.renderer, mode: view.mode })),
  views: projectedWorkspaceViews,
};
assert.equal(projectWorkspaceSandbox.projectWorkspaceViews(projectedWorkspace).length, 5);
assert.equal(projectWorkspaceSandbox.projectWorkspaceModeView(projectedWorkspace, "master")?.id, "view.project.plan.master");
assert.equal(projectWorkspaceSandbox.projectWorkspaceModeView(projectedWorkspace, "screens")?.id, "view.project.ui.screens");
assert.equal(projectWorkspaceSandbox.projectWorkspaceModeView(projectedWorkspace, "missing"), null);
assert.equal(projectWorkspaceSandbox.projectWorkspaceViews({ ...projectedWorkspace, views: [...projectedWorkspace.views, { id: "unsafe", label: "Unsafe", renderer: "script", mode: "execute", content: {} }] }).length, 0);
const projectDocumentRenderer = vm.runInNewContext(`(() => { function escapeHTML(value) { return String(value); } function humanize(value) { return String(value); } ${app.slice(app.indexOf("function projectWorkspaceDocumentMarkup"), app.indexOf("\nfunction projectWorkspaceTimelineMarkup"))}; return projectWorkspaceDocumentMarkup; })()`);
const projectTimelineRenderer = vm.runInNewContext(`(() => { function escapeHTML(value) { return String(value); } ${app.slice(app.indexOf("function projectWorkspaceTimelineMarkup"), app.indexOf("\nfunction projectWorkspaceRecordsMarkup"))}; return projectWorkspaceTimelineMarkup; })()`);
const masterPlanMarkup = projectDocumentRenderer({ content: { document: { blocks: [{ type: "heading", level: 2, text: "Master plan" }, { type: "paragraph", text: "Coordinate accepted work." }, { type: "list", items: ["Now", "Next"] }] } } });
assert.equal((masterPlanMarkup.match(/data-project-document-block/g) || []).length, 3);
assert.match(masterPlanMarkup, /Master plan[\s\S]*Coordinate accepted work\.[\s\S]*Now[\s\S]*Next/);
const roadmapMarkup = projectTimelineRenderer({ content: { timeline: { events: [{ id: "now", label: "Now", sequence: 0, status: "active", summary: "Current work", exit_criteria: "Accepted" }] } } });
assert.match(roadmapMarkup, /data-project-milestone="now"[\s\S]*Now[\s\S]*active · Current work · Accepted/);
assert.match(css, /\.project-ui-screens \{[^}]*grid-template-columns:repeat\(3,minmax\(0,1fr\)\)/);
assert.match(css, /\.project-ui-flowchart-connectors \{[^}]*position:absolute;[^}]*z-index:0/);
assert.match(css, /\.project-ui-flowchart-layers \{[^}]*position:relative;[^}]*z-index:1/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.project-ui-flowchart-layer \{[^}]*flex-direction:column/);
assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
assert.match(indexHtml, /id="run-log-overview"[^>]*data-run-log-surface="overview"[^>]*hidden/);
assert.match(indexHtml, /id="run-log-agent"[^>]*data-run-log-surface="agent"[^>]*hidden/);
assert.match(app, /data-run-log-surface="project" aria-label="Project run log"/);
assert.match(app, /api\("\/api\/run-log\?" \+ params\.toString\(\)\)/);
assert.match(app, /new URLSearchParams\(\{ ctrl_id: binding\.ctrlId, project_id: binding\.projectId, after_cursor: String\(previous\.cursor \|\| 0\) \}\)/);
assert.match(app, /if \(binding\.agentId\) params\.set\("agent_id", binding\.agentId\)/);
assert.match(app, /function runLogBindingsForProject\(projectId\)/);
assert.match(app, /project\.ctrl_ids\.map\(\(ctrlId\) => runLogBindingForCtrl\(ctrlId\)\)/);
assert.match(app, /function refreshRunLogs\(\)/);
assert.match(app, /refreshMonitoring[\s\S]*refreshRunLogs\(\)/);
assert.doesNotMatch(app, /setInterval\([^)]*runLog|setTimeout\([^)]*runLog|WebSocket[^\n]*runLog|localStorage[^\n]*runLog|sessionStorage[^\n]*runLog/i);
assert.match(app, /class="run-log-list" role="log" aria-labelledby=/);
assert.doesNotMatch(app, /class="run-log-list" role="log"[^>]*aria-live=/);
assert.match(app, /class="run-log-announcer sr-only" role="status" aria-live="polite" aria-atomic="true"/);
assert.match(app, /data-run-log-latest=/);
assert.match(app, /runLogNearBottom\(scroller\.scrollHeight, scroller\.scrollTop, scroller\.clientHeight\)/);
assert.match(app, /anchorIdentity/);
assert.match(app, /Cursor reset to the retained range/);
assert.match(app, /Showing a bounded retained window/);
assert.match(app, /Offline · showing the last received entries/);
assert.match(app, /Run log unavailable\. Refresh to try again\./);
assert.match(app, /Run log needs a current host-confirmed CTRL binding\./);
assert.match(app, /setDataStatus[\s\S]*renderRunLogSurfaces\(\)/);
assert.match(indexHtml, /id="agent-table"[^>]*role="table"[^>]*aria-label="Active agents"/);
assert.match(indexHtml, /id="run-log-agent"[^>]*aria-label="Agent live updates"/);
assert.match(app, /function agentRunLogPlan\(\)/);
assert.match(app, /state\.agentUpdatesPaused/);
assert.match(app, /filter: state\.agentUpdatesFilter/);
assert.match(css, /\.run-log-list \{[^}]*max-height:312px;[^}]*overflow-y:auto/);
assert.match(css, /\.run-log-list:focus-visible/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.run-log-new \{ min-height:44px; \}/);
const runLogHelperStart = app.indexOf("function runLogBindingKey");
const runLogHelperEnd = app.indexOf("\nfunction escapeHTML", runLogHelperStart);
assert.ok(runLogHelperStart >= 0 && runLogHelperEnd > runLogHelperStart);
const runLogHelpers = vm.runInNewContext(`(() => { const RUN_LOG_CLIENT_LIMIT = 200; ${app.slice(runLogHelperStart, runLogHelperEnd)}; return { runLogBindingKey, runLogPlanBindingKey, runLogSurfaceStateKey, runLogItemIdentity, runLogResponseMatches, mergeRunLogItems, runLogNearBottom, runLogAnnouncement, runLogReplaceSnapshot, runLogCanAnnounce }; })()`);
const runLogBinding = { projectId: "project:one", ctrlId: "ctrl:one", agentId: "owner:one" };
assert.equal(runLogHelpers.runLogBindingKey(runLogBinding), "project:one|ctrl:one|owner:one");
assert.equal(runLogHelpers.runLogPlanBindingKey({ bindings: [{ projectId: "project:one", ctrlId: "ctrl:two" }, { projectId: "project:one", ctrlId: "ctrl:one" }] }), '["project:one|ctrl:one|","project:one|ctrl:two|"]');
assert.notEqual(runLogHelpers.runLogSurfaceStateKey("project", "project:one|ctrl:one|"), runLogHelpers.runLogSurfaceStateKey("project", "project:one|ctrl:two|"));
assert.equal(runLogHelpers.runLogResponseMatches({ ok: true, scope: { project_id: "project:one", ctrl_id: "ctrl:one", agent_id: "owner:one" }, items: [] }, runLogBinding), true);
assert.equal(runLogHelpers.runLogResponseMatches({ ok: true, scope: { project_id: "project:other", ctrl_id: "ctrl:one", agent_id: "owner:one" }, items: [] }, runLogBinding), false);
const runLogA = { event_id: "event-a", event_digest: "digest-a", event_seq: 4, summary: "Proof was admitted." };
const runLogB = { event_id: "event-b", event_digest: "digest-b", event_seq: 5, summary: "Review was requested." };
const mergedRunLog = runLogHelpers.mergeRunLogItems([runLogA], [runLogA, runLogB], false, 200);
assert.deepEqual(Array.from(mergedRunLog.items, (item) => item.event_id), ["event-a", "event-b"]);
assert.equal(mergedRunLog.added, 1);
assert.deepEqual(Array.from(mergedRunLog.addedItems, (item) => item.event_id), ["event-b"]);
assert.deepEqual(Array.from(runLogHelpers.mergeRunLogItems([runLogA], [runLogB], true, 200).items, (item) => item.event_id), ["event-b"]);
assert.equal(runLogHelpers.mergeRunLogItems([runLogA], [runLogA], true, 200).added, 0);
assert.deepEqual(Array.from(runLogHelpers.mergeRunLogItems([runLogA], [runLogB], false, 1).items, (item) => item.event_id), ["event-b"]);
assert.equal(runLogHelpers.mergeRunLogItems([], [{ ...runLogA, summary: "" }], false, 200).items.length, 0);
assert.equal(runLogHelpers.runLogNearBottom(1000, 660, 300), true);
assert.equal(runLogHelpers.runLogNearBottom(1000, 400, 300), false);
assert.equal(runLogHelpers.runLogAnnouncement([runLogB]), "New run log entry 5: Review was requested.");
assert.equal(runLogHelpers.runLogAnnouncement([runLogA, runLogB]), "2 new run log entries. Latest, 5: Review was requested.");
assert.equal(runLogHelpers.runLogReplaceSnapshot({ initialized: false, items: [], cursor: 0 }, {}), true);
assert.equal(runLogHelpers.runLogCanAnnounce({ initialized: false, items: [], cursor: 0 }, true), false);
assert.equal(runLogHelpers.runLogReplaceSnapshot({ initialized: true, items: [], cursor: 0 }, {}), false);
assert.equal(runLogHelpers.runLogCanAnnounce({ initialized: true, items: [], cursor: 0 }, false), true);
assert.equal(runLogHelpers.runLogReplaceSnapshot({ initialized: true, items: [runLogA], cursor: 4 }, { stale_cursor: true }), true);
assert.equal(runLogHelpers.runLogCanAnnounce({ initialized: true, items: [runLogA], cursor: 4 }, true), false);
const runLogStateStart = app.indexOf("function runLogSurfaceState(surface, bindingKey)");
const runLogStateEnd = app.indexOf("\nfunction runLogEntries", runLogStateStart);
const runLogStateKeyStart = app.indexOf("function runLogSurfaceStateKey");
const runLogStateKeyEnd = app.indexOf("\nfunction runLogItemIdentity", runLogStateKeyStart);
const runLogStateHelpers = vm.runInNewContext(`(() => { const state = { runLogSurfaceStates: new Map() }; ${app.slice(runLogStateKeyStart, runLogStateKeyEnd)} ${app.slice(runLogStateStart, runLogStateEnd)}; return { take: runLogSurfaceState, size: () => state.runLogSurfaceStates.size }; })()`);
runLogStateHelpers.take("project", '["project:one|ctrl:one|"]').newEntries = 4;
assert.equal(runLogStateHelpers.take("project", '["project:one|ctrl:one|"]').newEntries, 4);
assert.equal(runLogStateHelpers.take("project", '["project:one|ctrl:two|"]').newEntries, 0);
assert.equal(runLogStateHelpers.size(), 1);
const runLogSource = app.slice(app.indexOf("function runLogBindingKey"), app.indexOf("function drawLine"));
assert.doesNotMatch(runLogSource, /evidence_refs|raw prompt|terminal output|hidden path/i);
assert.match(runLogSource, /function ensureRunLogShell\(mount, surface\) \{\s*if \(\$\("\.run-log-list", mount\)\) return;/);
const runLogRenderSource = app.slice(app.indexOf("function renderRunLogSurfaces"), app.indexOf("function markRunLogNewEntries"));
assert.doesNotMatch(runLogRenderSource, /mount\.innerHTML/);
assert.match(runLogRenderSource, /const sameBinding = mount\.dataset\.runLogBindingKey === bindingKey/);
assert.match(runLogRenderSource, /const viewport = sameBinding \? captureRunLogViewport\(mount\) : null/);
assert.match(runLogRenderSource, /announcer\.dataset\.revision !== String\(surfaceState\.announcementRevision\)/);
assert.match(runLogSource, /runLogSurfaceState\(surface, runLogPlanBindingKey\(plan\)\)/);
assert.match(runLogSource, /if \(runLogCanAnnounce\(previous, replace\)\) markRunLogNewEntries\(key, merged\.addedItems\)/);
const projectDetailSource = app.slice(app.indexOf("function renderProjectDetail"), app.indexOf("function proofReviewState"));
assert.match(projectDetailSource, /state\.projectTab = "overview";[\s\S]*?tabPanel\.innerHTML = projectTabMarkup\("overview", progress, nodes\)/);
const refreshRunLogBindingSource = app.slice(app.indexOf("async function refreshRunLogBinding"), app.indexOf("async function refreshRunLogs"));
const runLogEmptyBaselineHarness = vm.runInNewContext(`(() => {
  const RUN_LOG_CLIENT_LIMIT = 200;
  ${app.slice(runLogHelperStart, runLogHelperEnd)}
  const binding = { projectId: "project:one", ctrlId: "ctrl:one", agentId: "" };
  const appended = { event_id: "event:first", event_digest: "digest:first", event_seq: 1, project_id: "project:one", ctrl_id: "ctrl:one", summary: "First material event." };
  const responses = [
    { ok: true, scope: { project_id: "project:one", ctrl_id: "ctrl:one", agent_id: "" }, items: [], cursor: { next_event_seq: 0 }, retention: {} },
    { ok: true, scope: { project_id: "project:one", ctrl_id: "ctrl:one", agent_id: "" }, items: [appended], cursor: { next_event_seq: 1 }, retention: {} },
    { ok: true, scope: { project_id: "project:one", ctrl_id: "ctrl:one", agent_id: "" }, items: [appended], cursor: { next_event_seq: 1 }, retention: { stale_cursor: true } },
  ];
  const state = { runLogs: new Map(), runLogRequestGenerations: new Map() };
  const announced = [];
  async function api() { return responses.shift(); }
  function markRunLogNewEntries(key, items) { announced.push(...items); }
  ${refreshRunLogBindingSource}
  return { run: async () => { await refreshRunLogBinding(binding); await refreshRunLogBinding(binding); await refreshRunLogBinding(binding); return { announced, record: state.runLogs.get(runLogBindingKey(binding)) }; } };
})()`, { URLSearchParams });
const emptyBaselineResult = await runLogEmptyBaselineHarness.run();
assert.deepEqual(Array.from(emptyBaselineResult.announced, (item) => item.event_id), ["event:first"]);
assert.equal(emptyBaselineResult.record.initialized, true);
const progressQueueHelperStart = app.indexOf("function projectProgressQueueProjection");
const progressQueueHelperEnd = app.indexOf("\nfunction projectTabMarkup", progressQueueHelperStart);
assert.ok(progressQueueHelperStart >= 0 && progressQueueHelperEnd > progressQueueHelperStart);
const progressQueueHelpers = vm.runInNewContext(`(() => {
  const state = { projectProgressStatus: "current" };
  function selectedProgressProjectId() { return "project:alpha"; }
  function escapeHTML(value) { return String(value ?? ""); }
  function humanize(value) { return String(value ?? ""); }
  function formatDuration(value) { return String(value) + " ms"; }
  function formatEta(value) { return String(value); }
  ${app.slice(progressQueueHelperStart, progressQueueHelperEnd)}
  return { projectProgressQueueProjection, progressQueueRowPresentation, projectProgressQueueSegments, projectProgressQueueRowMarkup, projectProgressQueueMarkup };
})()`);
const progressCursor = { event_seq: 8, event_id: "event-8", event_digest: "digest-8" };
const progressRow = {
  scope_binding: { ctrl_id: "ctrl-a", project_id: "project:alpha", cursor: progressCursor },
  task_id: "task-a", task_name: "Task A", lifecycle: "ACTIVE", queue_state: null, runnable: null,
  progress: { state: "KNOWN", completed_milestones: 1, total_milestones: 2, percent: 50 },
  eta: { state: "KNOWN", start_ms: 10, end_ms: 20, confidence: 80, basis_receipt_ids: ["eta-1"] },
  elapsed: { state: "KNOWN", elapsed_ms: 10 }, freshness: { state: "UNKNOWN", observed_at_ms: 10 },
};
const progressQueueFixture = {
  view_id: "view.project.progress", renderer: "table", project_id: "project:alpha",
  scope_binding: { project_id: "project:alpha", ctrl_ids: ["ctrl-a"], cursor: progressCursor },
  accepted_cursor: progressCursor, status: "CURRENT", available: true,
  segments: [
    { segment_id: "segment.project.progress.active", label: "Active", rows: [progressRow] },
    { segment_id: "segment.project.progress.queue", label: "Queue", rows: [] },
  ],
};
assert.equal(progressQueueHelpers.projectProgressQueueProjection({ status: "MEASURED", cursor: progressCursor, progress_queue: progressQueueFixture }).status, "CURRENT");
const emptyRecordedWork = progressQueueHelpers.projectProgressQueueMarkup({ status: "UNMEASURED", cursor: progressCursor,
  progress_queue: { ...progressQueueFixture, segments: progressQueueFixture.segments.map((segment) => ({ ...segment, rows: [] })) } });
assert.match(emptyRecordedWork, /No recorded active work/);
assert.match(emptyRecordedWork, /No recorded queued work/);
assert.doesNotMatch(emptyRecordedWork, /role="progressbar"|is-unavailable/);
assert.equal(progressQueueHelpers.projectProgressQueueProjection({ cursor: { ...progressCursor, event_seq: 7 }, progress_queue: progressQueueFixture }), null);
assert.equal(progressQueueHelpers.projectProgressQueueProjection({ cursor: progressCursor, progress_queue: { ...progressQueueFixture, segments: [...progressQueueFixture.segments].reverse() } }), null);
const unavailableQueue = {
  ...progressQueueFixture,
  scope_binding: { project_id: "project:alpha", ctrl_ids: ["ctrl-a"], cursor: null },
  accepted_cursor: null,
  status: "RESYNC_REQUIRED",
  reason: "MIXED_SCOPE_REJECTED",
  available: false,
  segments: progressQueueFixture.segments.map((segment) => ({ ...segment, rows: [] })),
};
const unavailableProgress = { status: "UNKNOWN", cursor: { event_seq: null, event_id: null, event_digest: null }, progress_queue: unavailableQueue };
assert.equal(progressQueueHelpers.projectProgressQueueProjection(unavailableProgress).status, "RESYNC_REQUIRED");
assert.match(progressQueueHelpers.projectProgressQueueMarkup(unavailableProgress), /—[\s\S]*UNKNOWN[\s\S]*Progress needs resync · mixed_scope_rejected/);
assert.doesNotMatch(progressQueueHelpers.projectProgressQueueMarkup(unavailableProgress), /<table/);
const staleProgressRow = progressQueueHelpers.progressQueueRowPresentation(progressRow, true);
assert.deepEqual(
  { progress: staleProgressRow.progress.state, eta: staleProgressRow.eta.state, elapsed: staleProgressRow.elapsed.state, queue: staleProgressRow.queue_state, runnable: staleProgressRow.runnable },
  { progress: "UNKNOWN", eta: "UNKNOWN", elapsed: "UNKNOWN", queue: "UNKNOWN", runnable: false },
);
assert.equal(progressQueueHelpers.projectProgressQueueSegments(progressQueueFixture, false)[0].rows[0].progress.percent, 50);
const blockedRow = {
  ...progressRow,
  lifecycle: "ACTIVE", queue_state: "SCOPED_BLOCKED", runnable: false,
  blocked_recovery: {
    blocked_attempts: 3,
    blocked_critical_path: true,
    blocked_release_condition: { release_event_id: "release-1", release_event_digest: "release-digest", condition: "Owner releases the lane." },
    blocked_suggested_recovery: {
      action: "request_authority", route_id: "route-a", responsible_authority: "owner-lead",
      evidence_receipt_refs: [{ event_id: "receipt-1", event_digest: "receipt-digest" }],
    },
  },
};
const blockedMarkup = progressQueueHelpers.projectProgressQueueRowMarkup(blockedRow, "segment.project.progress.queue");
for (const visible of ["CTRL ctrl-a", "Owner releases the lane.", "route-a", "Critical path", "Yes", "release-1", "release-digest", "request_authority", "owner-lead", "3", "receipt-1", "receipt-digest"]) assert.match(blockedMarkup, new RegExp(visible));
assert.match(blockedMarkup, /<details class="project-progress-recovery"><summary>Recovery details<\/summary>/);
assert.doesNotMatch(progressQueueHelpers.projectProgressQueueRowMarkup({ ...blockedRow, blocked_recovery: { ...blockedRow.blocked_recovery, blocked_suggested_recovery: { ...blockedRow.blocked_recovery.blocked_suggested_recovery, route_id: "" } } }, "segment.project.progress.queue"), /Recovery details/);
const progressQueueSource = app.slice(progressQueueHelperStart, progressQueueHelperEnd);
assert.match(progressQueueSource, /role="progressbar"[^>]*aria-valuetext=/);
assert.match(progressQueueSource, /<table class="project-progress-table">/);
assert.match(progressQueueSource, /segment\.project\.progress\.active/);
assert.match(progressQueueSource, /segment\.project\.progress\.queue/);
assert.doesNotMatch(progressQueueSource, /localStorage|sessionStorage|setInterval|setTimeout|WebSocket|fetch\(/);
assert.match(css, /\.project-progress-table-wrap \{[^}]*overflow-x:auto;/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.project-progress-table tr \{[^}]*display:grid;/);
assert.match(app, /function yieldChartMarkup\(item\)/);
assert.match(app, /Observed tokens/);
assert.match(app, /Admitted scope/);
assert.match(app, /yield-scope-divider/);
assert.match(indexHtml, /id="overview-metrics" aria-label="Overview diagnostics"/);
assert.deepEqual([...indexHtml.matchAll(/data-overview-metric="([^"]+)"/g)].map((match) => match[1]), ["active-work", "needs-attention", "tbr", "usage"]);
{
  const now=1789000000000;
  const state={usageStatus:'current',usageScopeKey:'scope',usageWindowHours:1,usageHistory:{ok:true,status:'ok',usage_now:{status:'observed',source:'persisted_local_token_deltas',window_hours:1,sampled_at_ms:now,rate_sampled_at_ms:now,rate_tokens_per_minute:1234,rate_coverage:'partial',rate_observed_interval_ms:60000}}};
  const sandbox={state,usageRequestKey:()=> 'scope',usageRangeLabel:()=> 'last hour',compactMetricNumber:String};
  vm.createContext(sandbox);
  vm.runInContext(app.slice(app.indexOf('function tokenBurnRatePresentation('),app.indexOf('function renderOverviewMetrics(')),sandbox);
  assert.equal(sandbox.tokenBurnRatePresentation(now).value,'1234');
  state.usageHistory.status='partial'; assert.equal(sandbox.tokenBurnRatePresentation(now).state,'PARTIAL');
  state.usageScopeKey='other'; assert.equal(sandbox.tokenBurnRatePresentation(now).state,'UNKNOWN');
  state.usageScopeKey='scope'; assert.equal(sandbox.tokenBurnRatePresentation(now+300001).state,'UNKNOWN');
  assert.equal(sandbox.tokenBurnRatePresentation(now+300001,true).value,'1234','Historical interval is not made stale by its selected date');
  state.usageHistory.usage_now.sampled_at_ms=now+300001;
  assert.equal(sandbox.tokenBurnRatePresentation(now+300001).state,'UNKNOWN','New unqualified token observation cannot refresh old rate');
  state.usageHistory.usage_now.rate_tokens_per_minute=null; state.usageHistory.tokens=9000;
  assert.equal(sandbox.tokenBurnRatePresentation(now).value,'—');
}
assert.doesNotMatch(indexHtml, /verified-yield-summary|verified-yield-rows|overview-monitoring-health-state|>Unmeasured</);
assert.match(css, /\.overview-metrics \{[^}]*grid-template-columns:repeat\(4,minmax\(0,1fr\)\)/);
assert.match(css, /\.overview-metric-card \{[^}]*min-height:108px/);
assert.match(app, /function overviewMetricsProjectionValue\(value, expectedScopeId = ""\)/);
assert.match(app, /overviewMetricsProjectionValue\(state\.overview\?\.overview_metrics, overviewMetricsScopeId\(\)\)/);
const overviewMetricsStart = app.indexOf("const OVERVIEW_METRIC_FIELDS");
const overviewMetricsEnd = app.indexOf("\nfunction renderOverviewMetric", overviewMetricsStart);
const overviewMetricHelpers = vm.runInNewContext(`(() => { ${app.slice(overviewMetricsStart, overviewMetricsEnd)}; return { overviewMetricsProjectionValue, overviewMetricPresentation }; })()`);
const knownMetricState = Object.fromEntries(["active_projects", "active_lanes", "actionable_items", "oldest_wait", "admitted_milestones", "admitted_proof", "completed", "total", "percent", "trend", "window", "used_tokens", "remaining_tokens", "burn_rate_series", "coverage"].map((field) => [field, "KNOWN"]));
const overviewMetricFixture = {
  accepted_scope_id: "all", accepted_cursor: { event_seq: 12 },
  active_work: { active_projects: 3, active_lanes: 5 },
  needs_attention: { actionable_items: 2, oldest_wait: { reason: "Waiting for capacity", release_condition: "Capacity returns" } },
  verified_progress: { admitted_milestones: 4, admitted_proof: 7, completed: 6, total: 8, percent: 75, trend: [40, 60, 75] },
  usage: { window: "24h", used_tokens: 125000, remaining_tokens: 75000, burn_rate_series: [1000, 1200, 900], coverage: "complete" },
  field_state: knownMetricState,
};
const acceptedOverviewMetrics = overviewMetricHelpers.overviewMetricsProjectionValue(overviewMetricFixture, "all");
assert.equal(acceptedOverviewMetrics.accepted_scope_id, "all");
assert.equal(overviewMetricHelpers.overviewMetricsProjectionValue(overviewMetricFixture, "project:other"), null);
assert.equal(overviewMetricHelpers.overviewMetricsProjectionValue({ ...overviewMetricFixture, accepted_cursor: null }, "all"), null);
assert.equal(overviewMetricHelpers.overviewMetricsProjectionValue({ ...overviewMetricFixture, field_state: { ...knownMetricState, active_lanes: "STALE" } }, "all"), null);
assert.equal(overviewMetricHelpers.overviewMetricsProjectionValue({ ...overviewMetricFixture, active_work: { ...overviewMetricFixture.active_work, active_projects: null } }, "all"), null);
const metricPresentation = overviewMetricHelpers.overviewMetricPresentation(acceptedOverviewMetrics);
assert.deepEqual([metricPresentation.active.value, metricPresentation.attention.value, metricPresentation.progress.value, metricPresentation.usage.value], ["3 / 5", "2", "75%", "125k used"]);
assert.match(metricPresentation.attention.note, /Waiting for capacity · Capacity returns/);
const unknownMetricPresentation = overviewMetricHelpers.overviewMetricPresentation(null);
assert.deepEqual([unknownMetricPresentation.active.value, unknownMetricPresentation.attention.value, unknownMetricPresentation.progress.value, unknownMetricPresentation.usage.value], ["—", "—", "—", "—"]);
assert.ok(Object.values(unknownMetricPresentation).filter((item) => item && typeof item === "object").every((item) => item.state === "UNKNOWN"));
assert.doesNotMatch(indexHtml + app, /lines of code|productivity score|leaderboard/i);
assert.match(app, /node\?\.owner_id \|\| node\?\.worker/);
assert.match(indexHtml, /id="view-review"[\s\S]*id="review-list"/);
assert.match(indexHtml, /id="view-assets"[\s\S]*id="asset-gallery"/);
assert.doesNotMatch(indexHtml, /id="asset-detail"/);
assert.match(indexHtml, /id="asset-dialog"[^>]*aria-labelledby="asset-dialog-title"/);
assert.match(indexHtml, /id="asset-dialog-content"/);
assert.match(indexHtml, /id="asset-dialog-footer"/);
assert.match(indexHtml, /class="asset-view-toggle" role="group" aria-label="Asset view"/);
assert.match(indexHtml, /class="asset-projection-toggle" role="group" aria-label="Asset collection"/);
assert.match(indexHtml, /data-asset-projection="active" aria-pressed="true">Library/);
assert.match(indexHtml, /data-asset-projection="trash" aria-pressed="false"/);
assert.match(indexHtml, /id="asset-undo-toast" role="status" aria-live="polite" hidden/);
assert.match(indexHtml, /data-asset-view="grid" aria-pressed="true"/);
assert.match(indexHtml, /data-asset-view="list" aria-pressed="false"/);
assert.match(app, /function renderReview\(\)/);
assert.match(app, /function renderAssets\(\)/);
assert.match(app, /async function refreshAssets\(\)/);
assert.match(app, /api\("\/api\/assets\?" \+ inventoryParams\.toString\(\)\)/);
assert.match(app, /api\("\/api\/assets\/events\?" \+ eventParams\.toString\(\)\)/);
assert.match(app, /generation !== state\.assetRequestGeneration \|\| binding !== assetBindingKey\(\)/);
assert.match(app, /function assetMutationBindingCurrent\(request\)[\s\S]*?request\?\.bindingProjectId[\s\S]*?assetScopeProjectId\(\)/);
const assetMutationSource = app.slice(app.indexOf("async function runAssetMutation"), app.indexOf("async function mutateAsset"));
assert.match(assetMutationSource, /const result = await api[\s\S]*?if \(!assetMutationBindingCurrent\(request\)\)/);
assert.match(assetMutationSource, /catch \(error\) \{[\s\S]*?if \(!assetMutationBindingCurrent\(request\)\)/);
const assetRefreshSource = app.slice(app.indexOf("async function refreshAssets"), app.indexOf("function assetImageMarkup"));
assert.doesNotMatch(assetRefreshSource, /setInterval|setTimeout|WebSocket|EventSource|model|provider/i);
assert.match(app, /assetView: "grid"/);
assert.match(app, /function assetGridMarkup\(item\)/);
assert.match(app, /function assetListMarkup\(item\)/);
const assetGridSource = app.slice(app.indexOf("function assetGridMarkup"), app.indexOf("function assetListMarkup"));
assert.match(assetGridSource, /class="asset-image-button"/);
assert.match(assetGridSource, /class="asset-quick-actions"/);
assert.match(assetGridSource, /aria-label="Open asset details for/);
assert.doesNotMatch(assetGridSource, /<strong>|<small>|asset-list-copy|proofReviewState/);
const assetListSource = app.slice(app.indexOf("function assetListMarkup"), app.indexOf("function renderAssetDialog"));
assert.match(assetListSource, /asset-list-copy/);
assert.match(assetListSource, /assetStateLabel\(item\)/);
assert.match(assetListSource, /Type<\/small>/);
assert.match(assetListSource, /Updated<\/small>/);
assert.match(assetListSource, /Status<\/small>/);
assert.doesNotMatch(assetListSource, /Digest<\/small>|MIME<\/small>|Immutable ID<\/small>|Source<\/small>/);
assert.match(app, /data-asset-detail/);
assert.match(app, /state\.assetView = assetView\.dataset\.assetView === "list" \? "list" : "grid"/);
assert.match(app, /data-asset-image loading="/);
assert.match(app, /Preview unavailable/);
assert.match(css, /\.asset-image-frame img \{[^}]*object-fit:contain/);
assert.match(css, /\.asset-tile:hover \.asset-quick-actions,\.asset-tile:focus-within \.asset-quick-actions \{ opacity:1; \}/);
assert.match(css, /\.asset-quick-actions \.icon-button \{ width:44px; height:44px; pointer-events:auto; \}/);
assert.match(css, /@media \(hover: none\) \{[\s\S]*\.asset-quick-actions \{ opacity:1; \}/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.asset-quick-actions \.icon-button \{ width:44px; height:44px; \}/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.asset-gallery \{ grid-template-columns:1fr;/);
assert.match(app, /class="asset-revisions" aria-label="Revision history"/);
assert.match(app, /function assetRevisionItems\(selected, items = assetItems\(\)\)/);
assert.match(app, /Purge unavailable · no retention policy is configured\./);
assert.match(app, /expected_revision: Number\(technical\.revision\)/);
assert.match(app, /operation_id: operationId/);
assert.match(app, /data-asset-confirm/);
assert.match(app, /data-asset-undo/);
assert.match(app, /\/api\/assets\/generation\/retry/);
assert.doesNotMatch(app.slice(app.indexOf("function assetItems"), app.indexOf("function selectedProgressProjectId")), /\/api\/proof-feed|proofMediaURL\(item\)|ASSET_PURGE|model|provider/i);
assert.match(app, /<summary>Advanced<\/summary>/);
assert.match(app, /function openAssetDialog\(identity, trigger\)/);
const openAssetDialogSource = app.slice(app.indexOf("function openAssetDialog"), app.indexOf("function closeAssetDialog"));
assert.doesNotMatch(openAssetDialogSource, /renderAssets\(\)/);
assert.match(openAssetDialogSource, /card\.classList\.toggle\("is-selected"/);
assert.match(app, /trigger\?\.isConnected \? trigger : replacement/);
assert.doesNotMatch(app, /REVIEW_FEEDBACK_SUBMIT|["']PROOF_ADMIT["']|ASSET_REVISION_CREATE|ASSET_APPROVE/);
const assetHelperStart = app.indexOf("function assetIdentity");
const assetHelperEnd = app.indexOf("\nfunction assetGridMarkup", assetHelperStart);
const assetHelpers = vm.runInNewContext(`(() => { const state = { assetProjection: "active", projectId: "project:one" }; function humanize(value) { return String(value || ""); } ${app.slice(assetHelperStart, assetHelperEnd)}; return { assetStage, assetRevisionItems, assetProjectionValue }; })()`);
assert.deepEqual({ ...assetHelpers.assetStage({ presentation: { status: "GENERATING" }, technical: { status: "GENERATING", measured_progress: 42.4, measured_progress_provenance: "MEASURED" } }) }, { value: "GENERATING", label: "Generating", measured: true, percent: 42 });
assert.deepEqual({ ...assetHelpers.assetStage({ presentation: { status: "VALIDATING" }, technical: { status: "VALIDATING", measured_progress: 77, measured_progress_provenance: "UNMEASURED" } }) }, { value: "VALIDATING", label: "Validating", measured: false, percent: 77 });
assert.equal(assetHelpers.assetStage({ presentation: { status: "UNKNOWN" }, technical: {} }), null);
const revisionRoot = { asset_id: "root", project_id: "project:one", technical: { logical_asset_id: "asset:one", revision: 1 } };
const revisionTwo = { asset_id: "second", project_id: "project:one", technical: { logical_asset_id: "asset:one", parent_revision_id: "root", revision: 2 } };
const separateOption = { asset_id: "option", project_id: "project:one", technical: { logical_asset_id: "asset:two", revision: 9 } };
assert.deepEqual(Array.from(assetHelpers.assetRevisionItems(revisionRoot, [revisionRoot, separateOption, revisionTwo]), (item) => item.asset_id), ["second", "root"]);
assert.deepEqual(Array.from(assetHelpers.assetRevisionItems({ asset_id: "standalone", technical: {} }, [revisionRoot]), (item) => item.asset_id), ["standalone"]);
const acceptedAssets = { ok: true, status: "available", project_id: "project:one", projection: "active", items: [revisionRoot] };
assert.equal(assetHelpers.assetProjectionValue(acceptedAssets, "project:one|active", "project:one", "active").items.length, 1);
assert.equal(assetHelpers.assetProjectionValue({ ...acceptedAssets, project_id: "project:other" }, "project:one|active", "project:one", "active"), null);
assert.match(indexHtml, /id="notifications"[^>]*aria-expanded="false"[^>]*aria-controls="notifications-panel"/);
assert.match(indexHtml, /id="notifications-panel" role="dialog"[^>]*aria-labelledby="notifications-heading"[^>]*aria-describedby="notifications-status"[^>]*hidden tabindex="-1"/);
assert.match(indexHtml, /id="notifications-unread-list"/);
assert.match(indexHtml, /id="notifications-recent-list"/);
assert.match(indexHtml, /id="notifications-retry"[^>]*hidden>Try again<\/button>/);
assert.match(app, /All tentacles moving\./);
assert.match(app, /await api\("\/api\/notifications\/seen", \{ method: "POST"/);
assert.match(app, /api\("\/api\/notifications\?" \+ params\.toString\(\)\)/);
assert.doesNotMatch(app, /notificationLastSeen|overview\?\.attention_items|sessionStorage/);
const notificationHelperStart = app.indexOf("const NOTIFICATION_PANEL_UNREAD_LIMIT");
const notificationHelperEnd = app.indexOf("\nfunction notificationBinding", notificationHelperStart);
assert.ok(notificationHelperStart >= 0 && notificationHelperEnd > notificationHelperStart);
const notificationHelpers = vm.runInNewContext(`(() => {${app.slice(notificationHelperStart, notificationHelperEnd)}; return { dedupeNotificationItems, notificationToastPlan, notificationAcknowledgePayload, notificationDismissIds, notificationPanelMessage, notificationNextGeneration, notificationGenerationIsCurrent, notificationFeedMatchesBinding, notificationFeedResult, notificationActionAfterAcknowledgement, notificationActionEntry, notificationNavigateEntry, notificationAcknowledgementFlight, notificationSafeTarget }; })()`);
const unreadA = { id: "a".repeat(64), severity: "warning", material_sequence: 4 };
const unreadB = { id: "b".repeat(64), severity: "critical", material_sequence: 3 };
const notificationBindingFixture = { projectId: "project:one", ctrlId: "ctrl:one" };
const exactActionItem = { ...unreadA, project_id: "project:one", ctrl_id: "ctrl:one", action_target: { view: "review", project_id: "project:one", ctrl_id: "ctrl:one", task_id: "task", subject_id: "proof" } };
assert.deepEqual(Array.from(notificationHelpers.dedupeNotificationItems([unreadA, unreadA, unreadB]), (item) => item.id), [unreadA.id, unreadB.id]);
const burst = notificationHelpers.notificationToastPlan([unreadA, unreadB], new Set());
assert.equal(burst.item.id, unreadB.id);
assert.equal(burst.additionalCount, 1);
assert.deepEqual(Array.from(burst.presentedIds), [unreadA.id, unreadB.id]);
assert.equal(notificationHelpers.notificationToastPlan([unreadB, unreadA], new Set(burst.presentedIds)).item, null);
assert.equal(notificationHelpers.notificationToastPlan([{ ...unreadA, id: "c".repeat(64) }], new Set(burst.presentedIds)).item.id, "c".repeat(64));
assert.deepEqual(JSON.parse(JSON.stringify(notificationHelpers.notificationAcknowledgePayload({ ctrlId: "ctrl", projectId: "project:one" }, [unreadA.id]))), { ctrl_id: "ctrl", project_id: "project:one", notification_ids: [unreadA.id] });
assert.deepEqual(Array.from(notificationHelpers.notificationDismissIds({ item: unreadA }, false)), []);
assert.deepEqual(Array.from(notificationHelpers.notificationDismissIds({ item: unreadA }, true)), [unreadA.id]);
assert.equal(notificationHelpers.notificationSafeTarget(exactActionItem, notificationBindingFixture).view, "review");
assert.equal(notificationHelpers.notificationSafeTarget({ ...exactActionItem, action_target: { ...exactActionItem.action_target, view: "settings" } }, notificationBindingFixture), null);
assert.equal(notificationHelpers.notificationSafeTarget({ ...exactActionItem, project_id: "project:other", action_target: { ...exactActionItem.action_target, project_id: "project:other" } }, notificationBindingFixture), null);
assert.equal(notificationHelpers.notificationSafeTarget({ ...exactActionItem, ctrl_id: "ctrl:other", action_target: { ...exactActionItem.action_target, ctrl_id: "ctrl:other" } }, notificationBindingFixture), null);
assert.equal(notificationHelpers.notificationSafeTarget({ ...exactActionItem, action_target: { ...exactActionItem.action_target, route: "https://example.invalid" } }, notificationBindingFixture), null);
assert.equal(notificationHelpers.notificationFeedMatchesBinding({ ok: true, project_id: "project:one", ctrl_id: "ctrl:one", unread: [], recent_seen: [] }, notificationBindingFixture), true);
assert.equal(notificationHelpers.notificationFeedMatchesBinding({ ok: true, project_id: "project:one", ctrl_id: "ctrl:other", unread: [], recent_seen: [] }, notificationBindingFixture), false);
assert.equal(notificationHelpers.notificationActionEntry({ unread: [exactActionItem], recent_seen: [] }, exactActionItem.id).requiresAcknowledgement, true);
assert.equal(notificationHelpers.notificationActionEntry({ unread: [], recent_seen: [exactActionItem] }, exactActionItem.id).requiresAcknowledgement, false);
assert.equal(notificationHelpers.notificationActionEntry({ unread: [], recent_seen: [] }, exactActionItem.id), null);
let attemptedNavigation = 0;
assert.equal(await notificationHelpers.notificationActionAfterAcknowledgement(exactActionItem, async () => false, () => { attemptedNavigation += 1; }), false);
assert.equal(attemptedNavigation, 0);
let acknowledgementPosts = 0;
let resolvePanelAcknowledgement;
const panelAcknowledgementResult = new Promise((resolve) => { resolvePanelAcknowledgement = resolve; });
const panelAcknowledgement = notificationHelpers.notificationAcknowledgementFlight(null, "project:one|ctrl:one", [unreadA.id, unreadB.id], () => {
  acknowledgementPosts += 1;
  return panelAcknowledgementResult;
});
const concurrentUnreadAction = notificationHelpers.notificationAcknowledgementFlight(panelAcknowledgement.flight, "project:one|ctrl:one", [unreadA.id], () => {
  acknowledgementPosts += 1;
  return Promise.resolve(true);
});
assert.equal(panelAcknowledgement.started, true);
assert.equal(concurrentUnreadAction.started, false);
assert.equal(concurrentUnreadAction.flight, panelAcknowledgement.flight);
assert.equal(acknowledgementPosts, 1);
let concurrentSuccessNavigations = 0;
const concurrentSuccessAction = notificationHelpers.notificationNavigateEntry(
  notificationHelpers.notificationActionEntry({ unread: [exactActionItem], recent_seen: [] }, exactActionItem.id),
  async () => concurrentUnreadAction.flight.promise,
  () => { concurrentSuccessNavigations += 1; },
);
resolvePanelAcknowledgement(true);
assert.equal(await concurrentSuccessAction, true);
assert.equal(concurrentSuccessNavigations, 1);
assert.equal(acknowledgementPosts, 1);
const reconciledSeenEntry = notificationHelpers.notificationActionEntry({ unread: [], recent_seen: [exactActionItem] }, exactActionItem.id);
assert.equal(reconciledSeenEntry.requiresAcknowledgement, false);
let recentSeenNavigations = 0;
assert.equal(await notificationHelpers.notificationNavigateEntry(
  reconciledSeenEntry,
  async () => { acknowledgementPosts += 1; return true; },
  () => { recentSeenNavigations += 1; },
), true);
assert.equal(recentSeenNavigations, 1);
assert.equal(acknowledgementPosts, 1);
let resolveFailedPanelAcknowledgement;
const failedPanelAcknowledgementResult = new Promise((resolve) => { resolveFailedPanelAcknowledgement = resolve; });
const failedPanelAcknowledgement = notificationHelpers.notificationAcknowledgementFlight(null, "project:one|ctrl:one", [unreadA.id], () => {
  acknowledgementPosts += 1;
  return failedPanelAcknowledgementResult;
});
const concurrentFailedAction = notificationHelpers.notificationAcknowledgementFlight(failedPanelAcknowledgement.flight, "project:one|ctrl:one", [unreadA.id], () => {
  acknowledgementPosts += 1;
  return Promise.resolve(true);
});
let concurrentFailureNavigations = 0;
const failedActionResult = notificationHelpers.notificationNavigateEntry(
  notificationHelpers.notificationActionEntry({ unread: [exactActionItem], recent_seen: [] }, exactActionItem.id),
  async () => concurrentFailedAction.flight.promise,
  () => { concurrentFailureNavigations += 1; },
);
resolveFailedPanelAcknowledgement(false);
assert.equal(await failedActionResult, false);
assert.equal(concurrentFailureNavigations, 0);
assert.equal(acknowledgementPosts, 2);
assert.equal(notificationHelpers.notificationAcknowledgementFlight(failedPanelAcknowledgement.flight, "project:other|ctrl:other", [unreadA.id], () => Promise.resolve(true)).flight, null);
assert.match(notificationHelpers.notificationPanelMessage("stale", true, "live", "Read status failed. Try again."), /read-only.*Try again/i);
assert.match(notificationHelpers.notificationPanelMessage("current", true, "offline"), /Offline.*read-only/i);
const raceGenerations = new Map();
const raceBinding = "project:one|ctrl:one";
let resolveOldFeed;
const oldFeed = new Promise((resolve) => { resolveOldFeed = resolve; });
const oldGeneration = notificationHelpers.notificationNextGeneration(raceGenerations, raceBinding);
const lateOldResult = notificationHelpers.notificationFeedResult(raceGenerations, raceBinding, oldGeneration, () => raceBinding, () => oldFeed);
const freshGeneration = notificationHelpers.notificationNextGeneration(raceGenerations, raceBinding);
const freshResult = await notificationHelpers.notificationFeedResult(raceGenerations, raceBinding, freshGeneration, () => raceBinding, async () => ({ id: "fresh" }));
resolveOldFeed({ id: "old" });
assert.equal(freshResult.id, "fresh");
assert.equal(await lateOldResult, null);
let resolvePreAckFeed;
const preAckFeed = new Promise((resolve) => { resolvePreAckFeed = resolve; });
const preAckGeneration = notificationHelpers.notificationNextGeneration(raceGenerations, raceBinding);
const invalidatedByAck = notificationHelpers.notificationFeedResult(raceGenerations, raceBinding, preAckGeneration, () => raceBinding, () => preAckFeed);
notificationHelpers.notificationNextGeneration(raceGenerations, raceBinding);
notificationHelpers.notificationNextGeneration(raceGenerations, raceBinding);
resolvePreAckFeed({ id: "pre-ack" });
assert.equal(await invalidatedByAck, null);
const postAckGeneration = notificationHelpers.notificationNextGeneration(raceGenerations, raceBinding);
assert.equal((await notificationHelpers.notificationFeedResult(raceGenerations, raceBinding, postAckGeneration, () => raceBinding, async () => ({ id: "post-ack" }))).id, "post-ack");
const notificationSource = app.slice(notificationHelperStart, app.indexOf("\nfunction selectedProjectProgress", notificationHelperStart));
assert.doesNotMatch(notificationSource, /localStorage|sessionStorage|attention_items|setInterval|new Worker|new WebSocket/);
assert.match(notificationSource, /window\.setTimeout\(\(\) => dismissNotificationToast\(false\), 8_000\)/);
const notificationAckSource = app.slice(app.indexOf("async function performNotificationAcknowledgement"), app.indexOf("async function refreshNotifications"));
assert.equal((notificationAckSource.match(/notificationNextGeneration\(state\.notificationRequestGenerations, bindingKey\)/g) || []).length, 3);
assert.match(notificationAckSource, /notificationAcknowledgementFlight\([\s\S]*state\.notificationAckFlight/);
assert.doesNotMatch(notificationAckSource, /notificationAckPending/);
assert.match(app, /await notificationNavigateEntry\(entry, \(identity\) => acknowledgeNotifications\(\[identity\]\), navigateNotification\)/);
assert.match(app, /const ctrlId = ctrlIds\.includes\(project\.active_ctrl_id\) \? project\.active_ctrl_id : ""/);
assert.match(app, /if \(!\$\("#notifications-panel"\)\.hidden && !event\.target\.closest\("#notifications-panel, #notifications"\)\)/);
assert.match(app, /event\.key === "Escape" && !\$\("#notifications-panel"\)\.hidden/);
assert.match(app, /panel\.focus\(\{ preventScroll: true \}\)/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.notification-toast-region \{ top:auto;[^}]*bottom:max\(82px,calc\(env\(safe-area-inset-bottom\) \+ 72px\)\)/);
assert.doesNotMatch(indexHtml, /id="overview-monitoring-health-state"/);
assert.doesNotMatch(app, /function renderOverviewHealth\(nodes\)/);
const healthPresentationStart = app.indexOf("function systemHealthPresentation");
const healthPresentationEnd = app.indexOf("\nfunction renderSystemHealth", healthPresentationStart);
const healthPresentationHarness = vm.runInNewContext(`(() => {
  const state = { connectionStatus: "live", diagnostics: null };
  ${app.slice(healthPresentationStart, healthPresentationEnd)}
  return {
    run(connectionStatus, diagnostics) {
      state.connectionStatus = connectionStatus;
      state.diagnostics = diagnostics;
      return systemHealthPresentation();
    },
  };
})()`);
assert.equal(healthPresentationHarness.run("reconnecting", null).label, "Reconnecting");
assert.equal(healthPresentationHarness.run("offline", null).label, "Offline");
assert.equal(healthPresentationHarness.run("live", null).label, "Unknown");
assert.equal(healthPresentationHarness.run("live", { ok: true, config_valid: true, latest: { payload: { health_state: "HEALTHY" } }, health: { incidents: [], open_requests: [] } }).label, "Healthy");
assert.equal(healthPresentationHarness.run("live", { ok: true, config_valid: true, latest: { payload: { health_state: "HEALTHY" } }, health: { incidents: [{}], open_requests: [] } }).label, "Needs attention");
assert.match(app, /chromeDot\.className = "status-dot" \+ \(presentation\.className \? " " \+ presentation\.className : ""\)/);
assert.match(app, /function overviewRequestPath\(\)[\s\S]*?project_id=" \+ encodeURIComponent\(projectId\)/);
assert.match(app, /\$\("#project-navigation"\)\.addEventListener\("click", async \(event\) =>[\s\S]*?await selectProjectScope\(scope\.dataset\.projectId, scope\)/);
assert.match(app, /async function selectProjectScope\(projectId, trigger = null, historyMode = "push"\)[\s\S]*?await refreshOverview\(false\)/);
assert.match(app, /\$\("#project-navigation-heading"\)\.addEventListener\("click", async \(event\) =>[\s\S]*?setView\("overview", false, false\)[\s\S]*?await selectProjectScope\("all", event\.currentTarget\)/);
assert.match(indexHtml, /id="view-diagnostics"[\s\S]*?id="diagnostics-check-strip"[\s\S]*?id="diagnostics-signal-list"[\s\S]*?id="diagnostics-health-trend"[\s\S]*?class="panel diagnostics-log-panel"[\s\S]*?class="panel diagnostics-all-checks"/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*?\.icon-button \{ flex: 0 0 46px; height: 46px; \}/);
assert.match(app, /function routeView\(\)/);
assert.doesNotMatch(indexHtml, /id="highest-usage-tasks"/, "Task usage belongs in TBR, not the Overview page body");
assert.doesNotMatch(indexHtml, /id="nav-more"/);
assert.equal((indexHtml.match(/<button type="button" aria-haspopup="dialog" aria-controls="metric-detail-dialog"/g) || []).length, 4);
assert.match(indexHtml, /<dialog class="metric-detail-dialog" id="metric-detail-dialog"/);
assert.match(css, /\.metric-detail-dialog \{ width:calc\(100vw - 32px\); height:min\(720px,calc\(100dvh - 32px\)\); margin:auto; border-radius:12px;/, 'Mobile metric dialog retains margins on every side');
assert.doesNotMatch(css, /\.metric-detail-dialog \{[^}]*margin:auto 0 0/, 'Metric details are not a bottom sheet or inline panel');
assert.match(css, /#metric-detail-content svg:empty\s*\{\s*display:none;/);
assert.match(indexHtml, /id="overview-monitoring-heading">Swarm<\/h2>/);
assert.ok(indexHtml.indexOf('id="overview-metrics"') < indexHtml.indexOf('id="overview-monitoring-heading"'));
assert.doesNotMatch(indexHtml.match(/data-overview-metric="usage"[\s\S]*?<\/button>/)?.[0] || '', /data-usage-range/);
assert.match(app, /Remaining allowance unavailable/);
assert.match(app, /dialog\.onclose = \(\) => card\.isConnected && card\.focus/);
{
  let opened = 0, focused = 0;
  let rangeFocus = 0;
  const body = {scrollTop:37};
  const range = {dataset:{usageRange:'24'},focus(){rangeFocus++;}};
  const dialog = { dataset: {}, contains:() => true, querySelector:() => body, querySelectorAll:() => [range], showModal() { opened++; } };
  const title = {}, content = {};
  const sandbox = { $: id => id === '#metric-detail-dialog' ? dialog : id === '#metric-detail-title' ? title : content,
    document:{activeElement:range}, state: { overview: {} }, overviewMetricsScopeId: () => '', overviewMetricsProjectionValue: () => null,
    overviewMetricPresentation: () => ({ active: {value:'—',note:'Unavailable',state:'UNKNOWN'}, usage:{} }),
    escapeHTML: String, drawLine: () => {}, taskUsageHistory:()=>null, usageChartMarkup: () => '<svg></svg>', renderUsageCharts: () => {}, accountUsageDetails: () => '<p>Quota reset —</p><p>Estimated exhaustion —</p>' };
  vm.createContext(sandbox);
  vm.runInContext(app.slice(app.indexOf('function renderMetricDetail('), app.indexOf('function yieldChartMarkup(')), sandbox);
  for (const metric of ['active-work', 'usage']) {
    sandbox.openMetricDetail({ dataset:{overviewMetric:metric}, isConnected:true, focus(){ focused++; } });
    assert.ok(content.innerHTML.includes(metric === 'usage' ? 'Quota reset —' : 'UNKNOWN'));
    dialog.onclose();
  }
  assert.equal(opened,2); assert.equal(focused,2);
  sandbox.renderMetricDetail();
  assert.equal(rangeFocus,3); assert.equal(body.scrollTop,37);
  assert.match(content.innerHTML,/Estimated exhaustion —/);
  assert.doesNotMatch(content.innerHTML,/Task token usage|By task|metric-detail-token-trend/, 'Usage owns allowance only, not task token views');
  // Exercise the range refresh owner with an open detail, not only presentation helpers.
  dialog.open=true; dialog.dataset.metric='usage';
  const svg = {setAttribute(){}};
  sandbox.$ = id => id === '#metric-detail-dialog' ? dialog : id === '#metric-detail-title' ? title : id === '#metric-detail-content' ? content : svg;
  sandbox.$$ = () => [];
  Object.assign(sandbox, {URLSearchParams, renderHighestUsageTasks(){},renderAccountUsage(){},renderOverviewMetric(){},tokenBurnRatePresentation:()=>({state:'UNKNOWN'}),usageHistorySeries:()=>[],usageRangeLabel:()=>'',usageRequestKey:()=> 'scope'});
  Object.assign(sandbox.state,{projectId:'all',ctrlId:'',usageWindowHours:1,usageRequestGeneration:0,usageScopeKey:'scope',usageStatus:'current',usageHistory:{ok:true}});
  sandbox.accountUsageDetails=()=>sandbox.state.usageStatus==='current' ? '<p>Quota '+sandbox.state.usageHistory.quota+'</p><p>ETA supplied</p>' : '<p>UNKNOWN</p>';
  vm.runInContext(app.slice(app.indexOf('function renderUsageCharts()'),app.indexOf('function accountUsageWindows(')) + app.slice(app.indexOf('async function refreshUsageHistory()'),app.indexOf('async function refreshProjectProgress()')),sandbox);
  sandbox.api=async()=>({ok:true,quota:42});
  await sandbox.refreshUsageHistory(); sandbox.renderUsageCharts();
  assert.match(content.innerHTML,/Quota 42/);
  sandbox.api=async()=>{throw new Error('Disconnected');};
  await sandbox.refreshUsageHistory(); sandbox.renderUsageCharts();
  assert.match(content.innerHTML,/UNKNOWN/);
  assert.doesNotMatch(content.innerHTML,/Quota 42|ETA supplied/);
  assert.equal(body.scrollTop,37);
}
assert.doesNotMatch(app.slice(app.indexOf('function renderUsageCharts()'), app.indexOf('function accountUsageWindows(')), /#metric-usage-trend/);
{
  const now = 2000000;
  const state = {usageStatus:'current',usageScopeKey:'scope',usageHistory:{ok:true, account_limits:{status:'KNOWN',scope:'account',source:'codex_app_server.account/rateLimits/read',sampled_at_ms:now, windows:[{status:'KNOWN',limit_id:'main',window:'primary',remaining_percent:60,reset_at_ms:now+3600000,history:[{sampled_at_ms:now-60000,remaining_percent:70},{sampled_at_ms:now,remaining_percent:60}]}]}}};
  const sandbox = {state,usageRequestKey:()=> 'scope'};
  vm.createContext(sandbox);
  vm.runInContext(app.slice(app.indexOf('function accountUsageWindows('),app.indexOf('function renderAccountUsage(')),sandbox);
  assert.equal(sandbox.accountUsageWindows(now)[0].remaining_percent,60);
  assert.match(sandbox.accountUsageGraph(state.usageHistory.account_limits.windows[0]),/0.00,8.40 160.00,11.20/);
  const window = state.usageHistory.account_limits.windows[0];
  window.forecast = {status:'ESTIMATED',exhaustion_at_ms:now+60000};
  assert.match(sandbox.accountUsageGraph(window),/stroke-dasharray="3 3"/);
  assert.doesNotMatch(sandbox.accountUsageGraph(window, false), /stroke-dasharray/);
  assert.match(sandbox.accountUsageGraph(window, false), /160.00,11.20/);
  window.forecast.exhaustion_at_ms=window.reset_at_ms+1;
  assert.doesNotMatch(sandbox.accountUsageGraph(window),/stroke-dasharray/);
  for (const status of ['UNKNOWN','EXHAUSTED','NO_MEASURABLE_BURN','RESET_BEFORE_EXHAUSTION']) {
    window.forecast={status,exhaustion_at_ms:now+60000};
    assert.doesNotMatch(sandbox.accountUsageGraph(window),/stroke-dasharray/);
  }
  for (const remaining of [null,NaN,Infinity,-1,101]) {
    state.usageHistory.account_limits.windows[0].remaining_percent=remaining;
    assert.equal(sandbox.accountUsageWindows(now).length,0);
  }
  for (const remaining of [0,100]) {
    state.usageHistory.account_limits.windows[0].remaining_percent=remaining;
    assert.equal(sandbox.accountUsageWindows(now).length,1);
  }
  assert.equal(sandbox.accountUsageWindows(now+300001).length,0);
  state.usageScopeKey='old'; assert.equal(sandbox.accountUsageWindows(now).length,0);
  assert.equal(sandbox.accountUsageGraph({history:[{sampled_at_ms:now,remaining_percent:60}]}),'');
  assert.equal(sandbox.accountUsageGraph({history:[{sampled_at_ms:0,remaining_percent:70},{sampled_at_ms:now,remaining_percent:60}]}),'');
  let card;
  Object.assign(sandbox,{Date:class extends Date {static now(){return now;}},escapeHTML:String,
    $:()=>({setAttribute(){}}),renderOverviewMetric:(_,value)=>{card=value;}});
  vm.runInContext(app.slice(app.indexOf('function formatDuration('),app.indexOf('function forecastSummary(')) + app.slice(app.indexOf('function accountUsageDisplayWindows('),app.indexOf('function highestUsageTaskRows(')),sandbox);
  state.usageScopeKey='scope'; window.remaining_percent=40; window.reset_at_ms=now+86400000;
  window.forecast={status:'ESTIMATED',exhaustion_at_ms:now+14400000,rate_percentage_points_per_hour:10};
  sandbox.renderAccountUsage();
  assert.equal(card.value,'40%'); assert.match(card.note,/^main/); assert.doesNotMatch(card.note,/left|ETA|projected/i);
  assert.match(sandbox.accountUsageDetails(),/Estimate assumes the recent rate continues/);
  assert.match(sandbox.accountUsageDetails(), /<strong>40%<\/strong><span>Remaining<\/span>/);
  assert.match(sandbox.accountUsageDetails(), /<strong>~4h<\/strong><span>At current rate<\/span>/);
  assert.doesNotMatch(sandbox.accountUsageDetails(), /By task|TBR|Task token usage/);
  for (const [status,copy] of [['EXHAUSTED','Exhausted'],['NO_MEASURABLE_BURN','No measurable burn'],['RESET_BEFORE_EXHAUSTION','Reset occurs before projected exhaustion'],['UNKNOWN','<strong>—</strong><span>Runs out</span>']]) {
    window.forecast={status,exhaustion_at_ms:null,rate_percentage_points_per_hour:null};
    sandbox.renderAccountUsage(); assert.doesNotMatch(card.note,/left/);
    assert.ok(sandbox.accountUsageDetails().includes(copy));
  }
  state.usageHistory.account_limits.status='PARTIAL'; window.limit_id='spark';
  sandbox.renderAccountUsage(); assert.equal(card.state,'PARTIAL'); assert.match(card.note,/spark/);
  assert.match(sandbox.accountUsageDetails(),/Some account windows are unavailable/);
  state.usageStatus='stale'; sandbox.renderAccountUsage(); assert.equal(card.value,'40%');
  assert.match(sandbox.accountUsageDetails(),/STALE/);
  assert.match(sandbox.accountUsageDetails(),/Forecast withheld/);
}
assert.doesNotMatch(indexHtml, /<summary[^>]*>More/);
assert.ok(css.includes('.settings-save-bar[hidden] { display:none; }'));
assert.ok(css.includes('@media (min-width:901px) and (pointer:fine)'));
assert.ok(css.includes('.project-scope-button { min-height:32px; }'));
assert.ok(app.includes('filter(tab => !tab.closest("details") || tab.closest("details").open)'));
assert.match(app, /\["overview", "agents", "labs", "roles", "review", "assets", "diagnostics", "settings"\]/);
assert.doesNotMatch(app.slice(app.indexOf("function routeView"), app.indexOf("function setView")), /dashboard|hierarchy|kanban/);
for (const retiredView of ["dashboard", "hierarchy", "kanban"]) {
  assert.doesNotMatch(indexHtml, new RegExp(`id="view-${retiredView}"`));
}
for (const retiredRenderer of ["renderDashboard", "renderHierarchy", "renderKanban", "renderMetrics", "renderTable", "renderProof", "renderBurnRate", "renderOverviewDiagnostics"]) {
  assert.doesNotMatch(app, new RegExp(`function ${retiredRenderer}\\(`));
}
assert.match(app, /renderOverviewProjectCards\(\)/);
{
  const task={record_type:'TASK',id:'task',task_id:'task',task_name:'Actual task',project_id:'project',ctrl_id:'ctrl',owning_agent_id:'agent',state:'ACTIVE',manifest_identity:{state:'KNOWN'},order:0,progress:80};
  const topology={nodes:[{agent_id:'agent',project_id:'project',ctrl_id:'ctrl',task_ids:['task']}],tasks:[task,{...task}],task_edges:[{edge_kind:'AGENT_TASK_OWNERSHIP',source:'agent',target:'task'}]};
  const state={connectionStatus:'live',overview:{topology}};
  const sandbox={state,overviewTopologyProjection:value=>value}; vm.createContext(sandbox);
  vm.runInContext(app.slice(app.indexOf('function overviewHierarchyWorkRows('),app.indexOf('function overviewHierarchyNodeMarkup(')),sandbox);
  const record={node:{id:'agent'},binding:{projectId:'project',ctrlId:'ctrl'}};
  assert.equal(sandbox.overviewHierarchyWorkRows(record).length,1);
  assert.equal(sandbox.overviewHierarchyWorkRows(record)[0].label,'Actual task');
  assert.equal(sandbox.overviewHierarchyWorkRows(record)[0].progress,null,'Unqualified current-subset percent cannot become full task completion');
  task.scope_version=1;
  task.blocks=[{block_id:'block',title:'Actual block',task_id:'task',project_id:'project',ctrl_id:'ctrl',scope_version:1,committed_weight:10,event_cursor:{event_id:'event',event_digest:'a'.repeat(64)}}];
  assert.equal(sandbox.overviewHierarchyWorkRows(record)[0].progress,80);
  assert.equal(sandbox.overviewHierarchyWorkRows(record)[0].blocks[0].title,'Actual block');
  task.eta={task_id:'task',project_id:'project',status:'in_progress',eta_source:'task_owner_report',eta_start_ms:1000,eta_end_ms:2000,eta_observed_at_ms:500};
  assert.equal(sandbox.overviewHierarchyWorkRows(record)[0].eta.eta_end_ms,2000,'Exact retained task estimate remains available without claiming freshness');
  for(const change of [{task_id:'agent'},{project_id:'foreign'},{status:'UNKNOWN'},{eta_source:'controller'},{eta_observed_at_ms:null},{eta_end_ms:1}]) {
    const exact=task.eta; task.eta={...exact,...change};
    assert.equal(sandbox.overviewHierarchyWorkRows(record)[0].eta,null); task.eta=exact;
  }
  Object.assign(sandbox,{escapeHTML:String,humanize:String,agentWorkStatusIcon:()=>'',agentAvatarMarkup:()=>''});
  vm.runInContext(app.slice(app.indexOf('function overviewHierarchyNodeMarkup('),app.indexOf('function overviewHierarchySkeletonMarkup(')),sandbox);
  const markup=()=>sandbox.overviewHierarchyNodeMarkup({...record,structuralRole:'DOER',accent:'#123456'},[]);
  task.blocks[0].lifecycle_state='ACTIVE'; assert.match(markup(),/overview-work-block is-active/);
  task.blocks[0].lifecycle_state='ACCEPTED'; assert.match(markup(),/overview-work-block is-complete/);
  task.blocks[0].lifecycle_state='INVALIDATED_REWORK'; assert.match(markup(),/overview-work-block is-failed/);
  task.blocks[0].lifecycle_state='UNKNOWN'; assert.match(markup(),/overview-work-block is-unknown/);
  assert.match(markup(),/Retained estimate:[\s\S]*task owner report · observed/);
  assert.match(markup(),/aria-label="Actual block · UNKNOWN"/);
  assert.doesNotMatch(markup(),/countdown|Live ETA/);
  task.blocks[0].scope_version=2;
  assert.equal(sandbox.overviewHierarchyWorkRows(record)[0].progress,null,'Mismatched block scope withholds whole-task percentage');
  assert.equal(sandbox.overviewHierarchyWorkRows(record)[0].blocks.length,0);
  task.blocks[0].scope_version=1; task.blocks[0].committed_weight=null;
  assert.equal(sandbox.overviewHierarchyWorkRows(record)[0].progress,null,'Unmeasured block cannot become zero or measured completion');
  topology.hidden_tasks=[{...task,id:'hidden',task_id:'hidden',task_name:'Overflow task',order:4,blocks:[]},{...task,id:'foreign',task_id:'foreign',project_id:'other'}];
  assert.equal(sandbox.overviewHierarchyWorkRows(record).length,2,'Only same-scope overflow payload is disclosed');
  assert.equal(sandbox.overviewHierarchyWorkRows(record)[1].label,'Overflow task');
  topology.hidden_tasks=[];
  assert.equal(sandbox.overviewHierarchyWorkRows({...record,binding:{projectId:'other',ctrlId:'ctrl'}}).length,0);
  topology.task_edges=[]; assert.equal(sandbox.overviewHierarchyWorkRows(record).length,0);
  state.connectionStatus='offline'; assert.equal(sandbox.overviewHierarchyWorkRows(record).length,0);
}
const overviewProjectCardsSource = app.slice(app.indexOf("function renderOverviewProjectCards"), app.indexOf("function renderOverview()"));
assert.match(app, /function overviewTopologyProjection\(value\)[\s\S]*?value\.schema_version !== 1[\s\S]*?\["KNOWN", "PARTIAL", "EMPTY"\][\s\S]*?"independent_nodes"/);
assert.doesNotMatch(app, /recursive_host_topology/);
const evaluateOverviewTopology = vm.runInNewContext("(" + app.slice(app.indexOf("function overviewTopologyProjection"), app.indexOf("\nfunction renderOverviewProjectCards")) + ")");
const actualTopologyShape = { schema_version: 1, state: "KNOWN", nodes: [], tasks: [], agent_edges: [], task_edges: [], independent_nodes: [{ id: "host-task", record_type: "INDEPENDENT" }] };
assert.equal(evaluateOverviewTopology(actualTopologyShape), actualTopologyShape);
assert.equal(evaluateOverviewTopology({ ...actualTopologyShape, state: "UNKNOWN" }), null);
assert.equal(evaluateOverviewTopology({ ...actualTopologyShape, nodes: undefined }), null);
assert.match(overviewProjectCardsSource, /const roster = savedProjectRoster\(\)/);
assert.match(overviewProjectCardsSource, /Project team is unavailable/);
assert.match(overviewProjectCardsSource, /activeAgentRecords\(\)/);
assert.match(overviewProjectCardsSource, /topology\?\.parent_relation/);
assert.match(overviewProjectCardsSource, /relation\?\.state === "KNOWN"/);
assert.match(overviewProjectCardsSource, /if \(!topologyProjection\)[\s\S]*?Active agent topology is unavailable/);
assert.doesNotMatch(overviewProjectCardsSource, /fallbackParent|!topology && record\.structuralRole/);
assert.match(overviewProjectCardsSource, /rows\.slice\(0, 3\)/);
assert.match(overviewProjectCardsSource, /hiddenTaskCount \?/);
assert.match(overviewProjectCardsSource, /overview-node-more/);
assert.match(overviewProjectCardsSource, /overviewHierarchySkeletonMarkup\(\)/);
assert.match(overviewProjectCardsSource, /data-overview-output/);
assert.match(overviewProjectCardsSource, /data-overview-input/);
assert.match(overviewProjectCardsSource, /depth > 1 \? ' is-side'/);
assert.match(overviewProjectCardsSource, /input\.classList\.contains\("is-side"\)/);
assert.match(overviewProjectCardsSource, /data-agent-inspect/);
assert.match(overviewProjectCardsSource, /#lucide-eye/);
assert.doesNotMatch(overviewProjectCardsSource, /#lucide-pencil/);
assert.match(overviewProjectCardsSource, /Team map controls/);
assert.match(overviewProjectCardsSource, /Active host tasks/);
assert.doesNotMatch(overviewProjectCardsSource, /overviewCards\(|scopedCards|slice\(0, 5\)|Unmeasured|overview-controller-group|overview-hierarchy-tasks/);
assert.match(css, /\.overview-node-more summary \{[^}]*height:18px/);
assert.match(css, /\.overview-node-more summary::before \{[^}]*inset:-13px 0/);
assert.match(css, /\.overview-hierarchy-edges \{[^}]*z-index:0/);
assert.match(css, /\.overview-hierarchy-canvas \{[^}]*min-width:720px/);
assert.match(css, /\.overview-hierarchy-forest > \.overview-agent-branch > \.overview-hierarchy-node \{[^}]*width:min\(440px,100%\)/);
assert.match(css, /\.overview-hierarchy-node\.is-ctrl \.agent-avatar-token \{[^}]*width:64px;[^}]*height:64px/);
assert.match(css, /\.overview-hierarchy-node\.is-lead \.agent-avatar-token \{[^}]*width:48px;[^}]*height:48px/);
assert.match(css, /\.overview-hierarchy-node \.agent-avatar-token \{[^}]*width:32px;[^}]*height:32px;[^}]*border-radius:50%/);
assert.match(css, /\.overview-hierarchy-node \.agent-avatar-token \.role-avatar \{[^}]*border-radius:50%/);
assert.match(css, /\.overview-hierarchy-node\.is-ctrl \.overview-node-work-list \{[^}]*margin-left:82px/);
assert.match(css, /\.overview-node-port\.is-in\.is-side \{[^}]*left:-6px/);
assert.doesNotMatch(css, /\.overview-hierarchy-edges\s*\{\s*display:none/);
assert.match(app, /function authoritativeProgress\(projectId, ctrlId = ""\)/);
assert.match(app, /function progressPresentation\(summary\)/);
assert.match(app, /if \(ctrlId\) return summaries\.controllers\?\.\[ctrlId\] \?\? null/);
assert.match(app, /if \(projectId\) return summaries\.projects\?\.\[projectId\] \?\? null/);
assert.match(app, /validPercent == null \? "Unmeasured"/);
assert.match(app, /freshness\.state === "fresh" \? "Fresh" : freshness\.state === "stale" \? "Stale" : "Unmeasured"/);
assert.doesNotMatch(app, /completed \/ total/);
const authoritativeProgressSource = app.slice(app.indexOf("function authoritativeProgress"), app.indexOf("function hasCurrentWorkScopeContract"));
assert.doesNotMatch(authoritativeProgressSource, /progress_basis\?\.percent|progress_percent/);
assert.match(app, /function hasCurrentWorkScopeContract\(\)/);
assert.match(app, /function currentWorkProjects\(\)/);
assert.match(app, /function currentWorkControllers\(\)/);
assert.match(app, /function currentWorkScopeUnavailable\(\)/);
assert.match(app, /function historicalProjects\(\)/);
assert.match(app, /function historicalControllers\(\)/);
assert.match(app, /function savedProjectRoster\(\)/);
assert.match(app, /project\.visibility === "visible" && project\.archived === false && project\.project_eligibility === "swarm_ctrl"/);
assert.match(app, /controller\.visibility === "visible" && controller\.archived === false && allowedControllerProjects\.get\(controller\.id\) === controller\.project_id/);
assert.match(app, /project\.ctrl_ids\.includes\(ctrl\.id\)/);
assert.doesNotMatch(app, /function activeControllers\(\)/);
assert.doesNotMatch(app, /function hasCurrentOverviewWork\(card\)/);
assert.match(app, /expectedControllerIds\.some\(\(ctrlId\) => !resolvedControllerIds\.has\(ctrlId\)\)/);
assert.match(app, /if \(currentWorkScopeUnavailable\(\)\) return \[\]/);
const currentWorkProjectsSource = app.slice(app.indexOf("function currentWorkProjects"), app.indexOf("function currentWorkControllers"));
const currentWorkControllersSource = app.slice(app.indexOf("function currentWorkControllers"), app.indexOf("function publicLabel"));
const projectGroupsSource = app.slice(app.indexOf("function projectGroups"), app.indexOf("const PROJECT_NAVIGATION_STATUS_RANK"));
const savedProjectRosterSource = app.slice(app.indexOf("const PROJECT_NAVIGATION_STATUS_RANK"), app.indexOf("function scopeLabel"));
const projectNavigationSource = app.slice(app.indexOf("function renderProjectNavigation"), app.indexOf("function runLogBindingForCtrl"));
const overviewCardsSource = app.slice(app.indexOf("function overviewCards"), app.indexOf("function latestReceipt"));
assert.doesNotMatch(currentWorkProjectsSource, /project\.status|active_ctrl/);
assert.doesNotMatch(currentWorkControllersSource, /controller\.status/);
assert.match(projectGroupsSource, /historicalProjects\(\)|historicalControllers\(\)/);
assert.doesNotMatch(projectGroupsSource, /currentWorkProjects\(\)|currentWorkControllers\(\)/);
assert.match(savedProjectRosterSource, /navigation\?\.project_inventory/);
assert.match(savedProjectRosterSource, /inventory\?\.state !== "KNOWN"/);
assert.match(savedProjectRosterSource, /PROJECT_NAVIGATION_STATUS_RANK\[a\.status\] - PROJECT_NAVIGATION_STATUS_RANK\[b\.status\]/);
assert.doesNotMatch(savedProjectRosterSource, /currentWorkProjects\(\)|historicalProjects\(\)|historicalControllers\(\)|projectGroups\(\)/);
assert.match(projectNavigationSource, /const roster = savedProjectRoster\(\)/);
assert.match(projectNavigationSource, /scope-dot is-' \+ project\.status/);
assert.match(projectNavigationSource, /Saved projects unavailable/);
assert.doesNotMatch(projectNavigationSource, /data-project-id="all"|scope-dot is-live|projectGroups\(\)|currentWorkProjects\(\)/);
assert.doesNotMatch(projectNavigationSource, /data-ctrl-id|data-project-toggle|ctrl-subpages/);
assert.doesNotMatch(overviewCardsSource, /node\.role|node\.title/);
const savedProjectRosterHarness = vm.runInNewContext(`((overview) => {
  const state = { overview };
  const publicLabel = (value, fallback) => String(value || fallback);
  ${savedProjectRosterSource}
  return savedProjectRoster();
})`);
const rosterFixture = {
  navigation: {
    project_inventory: { state: "KNOWN", available: true },
    projects: [
      { id: "inactive", name: "Zulu", archived: false, visibility: "visible", project_eligibility: "no_ctrl", ctrl_ids: [], active_ctrl_id: null, task_count: 0, last_activity_at: 10, activity_status: "inactive", activity_facts: { active_now: false, recently_active: false, inactive: true, unknown: false } },
      { id: "recent", name: "Beta", archived: false, visibility: "visible", project_eligibility: "swarm_ctrl", ctrl_ids: ["ctrl-b"], active_ctrl_id: null, task_count: 2, last_activity_at: 20, activity_status: "recently_active", activity_facts: { active_now: false, recently_active: true, inactive: false, unknown: false } },
      { id: "active-b", name: "Charlie", archived: false, visibility: "visible", project_eligibility: "swarm_ctrl", ctrl_ids: ["ctrl-c"], active_ctrl_id: "ctrl-c", task_count: 3, last_activity_at: 200, activity_status: "active", activity_facts: { active_now: true, recently_active: false, inactive: false, unknown: false } },
      { id: "active-a", name: "Alpha", archived: false, visibility: "visible", project_eligibility: "no_ctrl", ctrl_ids: [], active_ctrl_id: null, task_count: 0, last_activity_at: 100, activity_status: "active", activity_facts: { active_now: true, recently_active: false, inactive: false, unknown: false } },
      { id: "unknown", name: "Unknown", archived: false, visibility: "visible", project_eligibility: "no_ctrl", ctrl_ids: [], active_ctrl_id: null, task_count: 0, activity_status: "unknown", activity_facts: { active_now: false, recently_active: false, inactive: false, unknown: true } },
    ],
  },
};
assert.deepEqual(Array.from(savedProjectRosterHarness(rosterFixture).projects, (project) => project.id), ["active-b", "active-a", "recent", "inactive", "unknown"]);
assert.equal(savedProjectRosterHarness({ navigation: { project_inventory: { state: "UNKNOWN", available: false }, projects: [] } }).state, "UNKNOWN");
const conflictedRoster = structuredClone(rosterFixture);
conflictedRoster.navigation.projects[0].activity_facts.active_now = true;
assert.equal(savedProjectRosterHarness(conflictedRoster).state, "UNKNOWN");
assert.equal(fixture.overview.progress.controllers.ctrl.progress.percent, 80);
assert.equal(fixture.overview.progress.controllers.ctrl.progress.completed_units, 4);
assert.equal(fixture.overview.progress.controllers.ctrl.progress.total_units, 5);
assert.equal(fixture.overview.progress.controllers.ctrl.progress.source, "material_receipts");
const agentProgressStart = app.indexOf("function agentProgress(record)");
const agentProgressEnd = app.indexOf("\nfunction agentAvatarMarkup", agentProgressStart);
const agentProgressHelpers = vm.runInNewContext(`(() => {
  const state = { projectId: "all", overview: null, projectProgressStatus: "unknown" };
  function projectProgressQueueProjection() { return null; }
  function selectedProjectProgress() { return null; }
  function progressQueueRowPresentation() { return null; }
  ${app.slice(agentProgressStart, agentProgressEnd)}
  return { run(record, overview) { state.overview = overview; return agentProgress(record); } };
})()`);
const measuredAgentRecord = { binding: { ctrlId: "ctrl", projectId: "project:fixture" }, node: { id: "ctrl" } };
assert.equal(agentProgressHelpers.run(measuredAgentRecord, fixture.overview).percent, 80);
const staleAgentOverview = structuredClone(fixture.overview);
staleAgentOverview.progress.controllers.ctrl.freshness.state = "stale";
assert.equal(agentProgressHelpers.run(measuredAgentRecord, staleAgentOverview), null);
const unmeasuredAgentOverview = structuredClone(fixture.overview);
unmeasuredAgentOverview.progress.controllers.ctrl.progress = { completed: 4, total: 5, percent: 80 };
assert.equal(agentProgressHelpers.run(measuredAgentRecord, unmeasuredAgentOverview), null);
const invalidMeasuredAgentOverview = structuredClone(fixture.overview);
invalidMeasuredAgentOverview.progress.controllers.ctrl.progress.completed_units = 6;
assert.equal(agentProgressHelpers.run(measuredAgentRecord, invalidMeasuredAgentOverview), null);
for (const invalid of [null, "", false, true, "4"]) {
  const invalidTypeOverview = structuredClone(fixture.overview);
  invalidTypeOverview.progress.controllers.ctrl.progress.completed_units = invalid;
  assert.equal(agentProgressHelpers.run(measuredAgentRecord, invalidTypeOverview), null);
}
for (const invalid of [null, "", false, true, "80"]) {
  const invalidTypeOverview = structuredClone(fixture.overview);
  invalidTypeOverview.progress.controllers.ctrl.progress.percent = invalid;
  assert.equal(agentProgressHelpers.run(measuredAgentRecord, invalidTypeOverview), null);
}
assert.equal(fixture.overview.navigation.projects[0].project_eligibility, "swarm_ctrl");
assert.match(css, /\.overview-hierarchy-project/);
assert.match(css, /\.overview-hierarchy-node/);
assert.match(app, /function drawOverviewHierarchyEdges\(\)/);
assert.match(app, /function agentWorkRows\(record\)/);
assert.match(app, /function agentWorkMarkup\(record\)/);
assert.match(app, /<h3>Work<\/h3>/);
assert.match(app, /<h3>Log<\/h3>/);
assert.match(app, /<dt>Live ETA<\/dt>/);
assert.doesNotMatch(indexHtml, /id="project-tab-hierarchy"/);
assert.doesNotMatch(app, /tab === "hierarchy"/);
assert.match(css, /\.project-navigation \{ display:flex; min-height:0; flex:1; flex-direction:column;[^}]*overflow:hidden; \}/);
assert.match(css, /#project-navigation \{[^}]*min-height:0;[^}]*overflow-y:auto;[^}]*overscroll-behavior:contain;/);
assert.match(css, /\.nav-footer \{[^}]*flex:0 0 auto;[^}]*margin-top:auto;/);
assert.match(css, /\.project-scope-button \{[^}]*min-height: 44px;/);
assert.doesNotMatch(indexHtml, /id="project-tab-(?:logs|ui)"/);
for (const status of ["active", "recent", "inactive", "unknown"]) assert.match(css, new RegExp(`\\.scope-dot\\.is-${status}`));
assert.doesNotMatch(indexHtml, /id="(?:task-table|proof-feed|burn-chart|overview-diagnostics-heading)"/);
assert.match(app, /Needs attention/);
assert.match(app, /project_id: request\.projectId/);
assert.match(app, /ctrl_id: request\.ctrlId/);
assert.match(app, /setInterval\(reportPresence, 60_000\)/);
assert.match(app, /async function refreshMonitoring/);
assert.match(app, /function renderAllViews\(\) \{ renderOverview\(\); renderAgents\(\); renderLabs\(\); renderRoles\(\); renderReview\(\); renderAssets\(\); renderDiagnostics\(\); renderSettings\(\); renderRunLogSurfaces\(\); renderMessageComposer\(\); if \(\$\("#onboarding-dialog"\)\?\.open\) renderOnboarding\(\); updateDocumentTitle\(\); \}/);
assert.match(app, /\/api\/diagnostics\/history\?limit=120/);
assert.match(app, /api\(overviewRequestPath\(\), \{ timeoutMs: 15_000 \}\)/);
assert.match(indexHtml, /id="connection-state-title">Connection lost</);
assert.match(indexHtml, /id="connection-state-detail">Your work is safe\. SWARM will reconnect when the console is available\.</);
assert.doesNotMatch(indexHtml, /Projects are up to date|<strong>Connected<\/strong>/);
assert.match(app, /active \? \(group\?\.label \|\| "Project"\) : "Overview"/);
assert.match(app, /setDataStatus\("current", state\.overview\?\.generated_at\)/);
assert.match(app, /setDataStatus\(state\.overview \? "stale" : "unavailable"/);
assert.match(app, /Project data request timed out/);
assert.doesNotMatch(indexHtml + app, /overview-evidence-gallery|overview-evidence-heading/, 'Overview stays stats, Projects and Swarm; proof remains in project Proof');
assert.match(indexHtml, /id="evidence-lightbox"/);
assert.match(indexHtml, /id="evidence-lightbox-thumbnails"/);
assert.doesNotMatch(indexHtml, /id="evidence-page-next"/);
assert.match(indexHtml, /Close evidence gallery/);
assert.match(indexHtml, /This image could not be loaded/);
assert.match(app, /function renderEvidenceLightbox\(\)/);
assert.match(app, /function openEvidenceLightbox\(index, trigger\)/);
assert.match(app, /data-evidence-open/);
assert.match(app, /data-evidence-thumbnail/);
assert.match(app, /if \(tab === "proof"\)[\s\S]*?data-evidence-open/);
assert.match(app, /dialog\.showModal\(\)/);
assert.match(app, /ArrowLeft/);
assert.match(app, /ArrowRight/);
assert.doesNotMatch(app, /function renderEvidenceGallery\(/);
assert.doesNotMatch(app, /EVIDENCE_THUMBNAIL_PAGE_SIZE|evidenceThumbnailPage/);
assert.match(app, /proofCollections: new Map\(\)/);
assert.match(app, /state\.proof = state\.proofCollections\.get\(collectionKey\) \|\| \[\]/);
assert.match(app, /return items\.filter\(\(item\) => !item\.project_id \|\| item\.project_id === state\.projectId\)/);
const evidenceScopeSource = app.slice(app.indexOf("function scopedProofItems"), app.indexOf("function renderEvidenceLightbox"));
assert.ok(evidenceScopeSource.indexOf("if (state.ctrlId)") < evidenceScopeSource.indexOf('if (state.projectId !== "all"'));
assert.match(app, /function selectedProgressProjectId\(\) \{\s*if \(state\.ctrlId\) return "";/);
assert.doesNotMatch(app, /catch \{ state\.proof = \[\]; \}/);
assert.match(app, /state\.evidenceImages = evidenceImagesFor\(nodes\)/);
assert.doesNotMatch(app, /figcaption/);
assert.match(css, /\.evidence-lightbox/);
assert.match(css, /\.evidence-lightbox-thumbnail:focus-visible/);
assert.match(app, /params\.set\("project_id", projectId\)/);
assert.doesNotMatch(app, /params\.set\("task_id", state\.ctrlId\)/);
const overviewMetricsRenderSource = app.slice(app.indexOf("function renderOverviewMetrics"), app.indexOf("function yieldChartMarkup"));
assert.doesNotMatch(overviewMetricsRenderSource, /scopedNodes|projectGroups|usageHistory|verifiedYieldProjection|attentionStatus/);
assert.doesNotMatch(app, /Number\(project\.active_threads \?\? project\.active\) > 0/);
assert.match(app, /function configEditable\(key\)/);
assert.match(app, /id="settings-scope"/);
assert.match(app, /Custom CTRL values override global defaults/);
assert.match(app, /Inherits global defaults/);
const settingsSource = app.slice(app.indexOf("function renderSettings"), app.indexOf("function renderLabs"));
 assert.match(settingsSource, /class="panel settings-card settings-card-workflow"/);
 assert.match(settingsSource, /class="settings-theme-choice"/);
assert.match(app, /const THEME_STORAGE_KEY = "swarm\.theme\.v1"/);
assert.match(app, /THEME_OPTIONS = Object\.freeze\(\{ midnight: "Midnight", black: "Black", graphite: "Graphite", pearl: "Pearl" \}\)/);
assert.match(app, /function setTheme\(theme, storage = window\.localStorage\)[\s\S]*?document\.documentElement\.dataset\.theme = selected[\s\S]*?storage\.setItem\(THEME_STORAGE_KEY, selected\)/);
assert.match(app, /event\.target\.matches\('\[data-theme-option\]'\)[\s\S]*?setTheme\(event\.target\.dataset\.themeOption\)[\s\S]*?renderSettings\(\)/);
assert.match(indexHtml, /localStorage\.getItem\("swarm\.theme\.v1"\)[\s\S]*?\^\(midnight\|black\|graphite\|pearl\)\$[\s\S]*?dataset\.theme="midnight"/);
assert.ok(indexHtml.indexOf('swarm.theme.v1') < indexHtml.indexOf('rel="stylesheet"'));
assert.doesNotMatch(indexHtml + app + css, /data-theme="slate"|\bSlate\b/);
for (const theme of ["black", "graphite", "pearl"]) assert.match(css, new RegExp(`html\\[data-theme="${theme}"\\]`));
assert.match(css, /html\[data-theme="black"\][\s\S]*?--base:#050607; --base-deep:#010203/);
assert.match(css, /html\[data-theme="graphite"\][\s\S]*?--base:#202123; --base-deep:#17181a/);
assert.match(css, /html\[data-theme="pearl"\][\s\S]*?color-scheme: light/);
 assert.match(settingsSource, /settingsSwitch\("automation\.mode"[\s\S]*?"Auto-advance"/);
 assert.match(settingsSource, /descriptorBooleanSwitch\("execution\.usage_saver"[\s\S]*?"Enable usage saver"[\s\S]*?Uses lighter models and reduces background activity when possible\./);
assert.match(settingsSource, /settingsSpeedMarkup\(\)[\s\S]*?settingsTaskLifeMarkup\(\)/);
 assert.match(settingsSource, /class="settings-config-entry"[\s\S]*?data-setting-action="edit-config"/);
 assert.match(settingsSource, /class="settings-save-bar settings-wide/);
 assert.match(settingsSource, /<details class="panel settings-advanced-drawer" id="settings-advanced"/);
assert.doesNotMatch(settingsSource, /Spark and monitoring|Use ChatGPT for eligible work|Heartbeat minutes|Show role icons|Use less usage when possible/);
assert.ok(settingsSource.includes('!pending && !state.settingsSaving && !state.settingsSaveError'));
assert.ok(css.includes('.message-composer-actions > div { grid-column:2; grid-row:1; }'));
assert.match(app, /function stageSettingsDraft\(key, value\)[\s\S]*?state\.settingsDraft\.set\(key, value\)/);
assert.match(app, /function saveSettingsDraft\(\)[\s\S]*?await saveCurrentConfigMutation\(changes\)[\s\S]*?state\.settingsDraft\.clear\(\)/);
assert.match(app, /function settingsConfigEditable\(key\)[\s\S]*?currentSettingsScope\(\)\.type === "global"/);
assert.match(app, /Short[\s\S]*?Medium[\s\S]*?Balanced[\s\S]*?Long[\s\S]*?Unlimited/);
assert.match(app, /function settingsTaskLifeMarkup\(options = \{\}\)[\s\S]*?aria-label="Task life" aria-valuetext="' \+ escapeHTML\(valueText\)/);
assert.match(indexHtml, /Project overrides take priority\. Overridden values stop following global changes; all other values continue to inherit\./);
assert.match(indexHtml, /id="config-editor-dialog"[\s\S]*?class="dialog-shell config-editor-shell"[\s\S]*?id="config-editor-text"[\s\S]*?readonly/);
assert.match(indexHtml, /id="config-editor-save"[^>]*disabled/);
assert.match(app, /Current configuration is unavailable for this scope/);
assert.doesNotMatch(settingsSource, /api\('/);
const autoReadSource = app.slice(app.indexOf("async function refreshAutoStatus"), app.indexOf("async function refreshRoleManifests"));
assert.match(autoReadSource, /await api\('\/api\/auto\?' \+ params\.toString\(\)\)/);
assert.doesNotMatch(autoReadSource, /method:|'POST'|"POST"/);
assert.doesNotMatch(settingsSource, /api\('\/api\/auto/);
assert.match(app, /const command = event\.target\.checked \? "ENABLE" : "DISABLE"/);
assert.match(app, /body: JSON\.stringify\(\{ command, ctrl_id: binding\.ctrlId, project_id: binding\.projectId, request_id: autoRequestId\(command\) \}\)/);
assert.doesNotMatch(app, /RELEASE_UNREACHABLE/);
assert.match(app, /aria-label="Continue eligible work automatically" aria-describedby="auto-continuation-status"/);
assert.match(app, /id="auto-continuation-status" aria-live="polite"/);
const autoPresentationStart = app.indexOf("function autoPresentation");
const autoPresentationEnd = app.indexOf("\n}\n\nfunction autoSettingsMarkup", autoPresentationStart) + 2;
assert.ok(autoPresentationStart >= 0 && autoPresentationEnd > autoPresentationStart, "autoPresentation source is extractable");
const evaluateAutoPresentation = vm.runInNewContext("(" + app.slice(autoPresentationStart, autoPresentationEnd) + ")");
assert.equal(evaluateAutoPresentation({ enabled: true, in_flight: true, attention: { kind: "IN_FLIGHT_OUTCOME_UNVERIFIED", reason: "reconcile retained turn" } })[0], "Active");
assert.equal(evaluateAutoPresentation({ enabled: true, in_flight: false, attention: { kind: "WAIT_USER", reason: "user decision required" } })[0], "Waiting for user");
assert.equal(evaluateAutoPresentation({ enabled: true, in_flight: false, attention: { kind: "TERMINAL_BLOCKED", reason: "release required" } })[0], "Attention");
assert.equal(evaluateAutoPresentation({ enabled: false, in_flight: false, attention: null })[0], "Off");
assert.equal(evaluateAutoPresentation({ enabled: true, in_flight: false, attention: null })[0], "Enabled");
assert.match(app, /state\.autoStatus === "stale"[\s\S]*?last known value is shown read-only/);
assert.match(app, /!current \|\| state\.autoSaving \? ' disabled' : ''/);
assert.match(app, /aria-label="Use ChatGPT for eligible work" aria-describedby="chat-relay-status"/);
assert.match(app, /id="chat-relay-status" aria-live="polite"/);
const chatRelayPresentationStart = app.indexOf("function chatRelayPresentation");
const chatRelayPresentationEnd = app.indexOf("\n}\n\nfunction chatRelayMutation", chatRelayPresentationStart) + 2;
assert.ok(chatRelayPresentationStart >= 0 && chatRelayPresentationEnd > chatRelayPresentationStart, "chatRelayPresentation source is extractable");
const evaluateChatRelayPresentation = vm.runInNewContext("(" + app.slice(chatRelayPresentationStart, chatRelayPresentationEnd) + ")");
const relayOff = { editable: ["chat_relay.enabled"], settings: { chat_relay: { enabled: false } } };
const relayOn = { editable: ["chat_relay.enabled"], settings: { chat_relay: { enabled: true } } };
assert.deepEqual(
  [evaluateChatRelayPresentation(relayOff, "current", false, "").checked, evaluateChatRelayPresentation(relayOff, "current", false, "").disabled, evaluateChatRelayPresentation(relayOff, "current", false, "").title],
  [false, false, "Off"],
);
assert.deepEqual(
  [evaluateChatRelayPresentation(relayOn, "current", false, "").checked, evaluateChatRelayPresentation(relayOn, "current", false, "").disabled, evaluateChatRelayPresentation(relayOn, "current", false, "").title],
  [true, false, "Enabled"],
);
const relayMissing = evaluateChatRelayPresentation({ editable: ["chat_relay.enabled"], settings: {} }, "current", false, "");
assert.deepEqual([relayMissing.checked, relayMissing.disabled, relayMissing.title], [false, true, "Unavailable"]);
const relayManaged = evaluateChatRelayPresentation({ editable: [], settings: { chat_relay: { enabled: false } } }, "current", false, "");
assert.deepEqual([relayManaged.checked, relayManaged.disabled, relayManaged.title], [false, true, "Off"]);
const relayStale = evaluateChatRelayPresentation(relayOn, "stale", false, "Settings could not be loaded.");
assert.deepEqual([relayStale.checked, relayStale.disabled, relayStale.title], [true, true, "Unavailable"]);
assert.match(relayStale.note, /last known value is shown read-only[.] Settings could not be loaded[.]/);
const relaySaving = evaluateChatRelayPresentation(relayOff, "current", true, "");
assert.deepEqual([relaySaving.checked, relaySaving.disabled, relaySaving.title], [false, true, "Saving"]);
const chatRelayMutationStart = app.indexOf("function chatRelayMutation");
const chatRelayMutationEnd = app.indexOf("\n}\n\nfunction chatRelayFailureState", chatRelayMutationStart) + 2;
const evaluateChatRelayMutation = vm.runInNewContext("(" + app.slice(chatRelayMutationStart, chatRelayMutationEnd) + ")");
assert.equal(JSON.stringify(evaluateChatRelayMutation(true)), '{"changes":{"chat_relay.enabled":true}}');
assert.equal(JSON.stringify(evaluateChatRelayMutation(false)), '{"changes":{"chat_relay.enabled":false}}');
const chatRelayFailureStart = app.indexOf("function chatRelayFailureState");
const chatRelayFailureEnd = app.indexOf("\n}\n\nfunction chatRelaySettingsMarkup", chatRelayFailureStart) + 2;
const evaluateChatRelayFailure = vm.runInNewContext("(" + app.slice(chatRelayFailureStart, chatRelayFailureEnd) + ")");
const relayReloaded = evaluateChatRelayFailure(relayOff, relayOn, "Save failed.");
assert.deepEqual([relayReloaded.config.settings.chat_relay.enabled, relayReloaded.configStatus], [true, "current"]);
assert.match(relayReloaded.configError, /Save failed[.] The current server value was reloaded[.]/);
const relayReadbackFailed = evaluateChatRelayFailure(relayOn, null, "Save failed.");
assert.deepEqual([relayReadbackFailed.config.settings.chat_relay.enabled, relayReadbackFailed.configStatus], [true, "stale"]);
assert.match(relayReadbackFailed.configError, /current server value could not be reloaded/);
assert.equal(evaluateChatRelayFailure(null, null, "Save failed.").configStatus, "unavailable");
assert.match(app, /await saveCurrentConfigMutation\(chatRelayMutation\(requestedValue\)\.changes\)/);
assert.match(app, /await readConfigState\(previousConfig, saveError\)/);
assert.match(app, /readConfigState\(previousConfig\)/);
assert.equal((app.match(/api\('\/api\/config'\)/g) || []).length, 1, "all config GET readbacks use the guarded authority seam");
assert.doesNotMatch(settingsSource, /api\('\/api\/config'/);
assert.doesNotMatch(app, /\/api\/(?:chat-relay|relay)|CodexAppServerAdapter|chat_relay\.(?:provider|surface|mode)/);
assert.match(app, /function forecastSummary\(node\)/);
assert.match(app, /baseline_eta_end_ms/);
assert.match(app, /delta_from_baseline_ms/);
assert.match(app, /last_material_heartbeat_at_ms/);
assert.match(app, /skillsError/);
assert.match(app, /Try again to refresh this scope/);
assert.match(app, /\$\("#project-navigation"\)\.addEventListener\("click", async \(event\) =>[\s\S]*?await selectProjectScope\(scope\.dataset\.projectId, scope\)/);
assert.doesNotMatch(app, /Raw host logs|terminal output|hidden paths/);
assert.match(app, /\.replace\(\/\\blocalhost\\b\/gi, "console"\)/);
assert.match(indexHtml, /id="view-agents"[^>]*aria-labelledby="tab-agents"[\s\S]*?id="agent-table"[\s\S]*?id="run-log-agent"/);
assert.match(indexHtml, /id="view-roles"[^>]*aria-labelledby="tab-roles"[\s\S]*?id="role-search"[\s\S]*?class="role-library-control-actions"[\s\S]*?id="role-create"[\s\S]*?id="role-library-grid"/);
 assert.match(indexHtml, /<p class="eyebrow">Role library<\/p><h2 id="roles-heading"[^>]*>Roles<\/h2>/);
 assert.doesNotMatch(indexHtml, />Server-owned manifests</);
assert.doesNotMatch(indexHtml + app, /data-agents-tab|agents-tab-library|state\.agentsTab/);
assert.match(indexHtml, /id="role-library-status" role="status"/);
assert.match(app, /function activeAgentRecords\(\)/);
assert.match(app, /\["active", "in_progress"\]\.includes\(String\(node\.status \|\| ""\)\.toLowerCase\(\)\)/);
assert.match(app, /identityState = independent \? "independent" : assignment && role && binding && projectedName \? "admitted" : "malformed"/);
assert.match(app, /Reconnect this SWARM task to one valid manifest role and CTRL/);
assert.match(app, /Anonymous[\s\S]*Independent task/);
assert.match(app, /function agentTableRowMarkup\(record\)/);
assert.match(app, /function agentProgressMarkup\(record\)/);
assert.match(app, /role="progressbar"[^\n]*aria-valuenow=/);
assert.match(app, /aria-label="Progress UNKNOWN"/);
assert.match(app, /function openAgentDetail\(trigger\)/);
assert.match(app, /\$\("#agent-detail-dialog"\)\.addEventListener\("click", \(event\) => \{ if \(event\.target === event\.currentTarget\) closeAgentDetail\(\); \}\)/);
assert.match(app, /No exact accepted work association is available for this agent/);
assert.match(app, /node\?\.presentation\?\.display_name/);
assert.match(app, /projectedName \? "admitted" : "malformed"/);
const taskColorSource = app.slice(app.indexOf('function taskUsageColor('), app.indexOf('function taskUsageGraph('));
assert.doesNotMatch(taskColorSource, /state\.|agent|manifest|role/i, 'Task chart colors cannot become agent identity');
assert.doesNotMatch(app.replace(taskColorSource, ''), /AGENT_COLOR_CATALOG|agentColorRegistry|agentColorIdentity|Math\.imul\(hash/);
assert.doesNotMatch(app.match(/function activeAgentRecords\(\)[\s\S]*?\n\}/)?.[0] || "", /Math\.random\(|hash/i);
assert.doesNotMatch(app, /romanAgentOrdinal|#708090|Role pending/);
assert.doesNotMatch(app + css, /class="agent-hierarchy|class="agent-project|class="agent-branch|\.agent-hierarchy|\.agent-project|\.agent-branch|\.agent-role-mark/);
const expectedProfessions = ["Accountant", "Analyst", "Architect", "Artist", "Auditor", "Assistant", "Designer", "Developer", "Educator", "Inventor", "Legal", "Manager", "Marketer", "Operator", "Producer", "Recruiter", "Researcher", "Reviewer", "Security", "Specialist", "Strategist", "Support", "Tester", "Writer"];
const roleAvatarFixtures = new Map(expectedProfessions.map((name) => name.toLowerCase()).map((roleId) => {
  return [roleId, fs.readFileSync(path.join(repositoryRoot, "skills", "swarm", "assets", "role-avatars", "source", roleId + ".png"))];
}));
function roleManifestFixture() {
  return {
    ok: true,
    schema_version: 1,
    built_in_count: 24,
    roles: expectedProfessions.map((name) => {
      const id = name.toLowerCase();
      const digest = crypto.createHash("sha256").update(roleAvatarFixtures.get(id)).digest("hex");
      const specializations = id === "developer"
        ? ["Game Development", "Developer two", "Developer three", "Developer four"]
        : id === "designer"
          ? ["Game Design", "Designer two", "Designer three", "Designer four"]
          : [`${name} one`, `${name} two`, `${name} three`, `${name} four`];
      return {
        id, name, purpose: `Apply the ${name} bounded SWARM assignment`, owns: [`${name} surface`], instructions: ["Apply the bounded SWARM assignment", `Use ${name} judgment to produce profession-specific evidence`], boundaries: ["No authority transfer"],
        default_skills: [`${id}-skill`], specializations,
        avatar_asset_digest: digest, avatar: { digest, state: "AVAILABLE", url: `/assets/role-avatars/${id}.png` }, accent: "#ff6948", version: `${id}-v1`, source: "builtin", provenance: ["fixture"],
        built_in: true, active_version: `${id}-v1`, canonical_version: `${id}-v1`, override_active: false,
        versions: [], source_event_ids: [],
      };
    }),
    assignments: [
      ["nested-ctrl", "manager"], ["nested-task", "developer"], ["branch-ctrl", "manager"], ["branch-task", "reviewer"],
      ["arc-ctrl", "manager"], ["arc-task", "writer"], ["atlas-ctrl", "manager"], ["atlas-task", "analyst"],
    ].map(([task_id, role_id], index) => ({ task_id, role_id, manifest_version: `${role_id}-v1`, event_id: `assignment-${index + 1}`, event_seq: index + 1 })),
    agent_color_registry: { schema_version: 1, colors: [{ name: "Tomato", hex: "#FF6347" }, { name: "Aqua", hex: "#00FFFF" }, { name: "Gold", hex: "#FFD700" }, { name: "Violet", hex: "#EE82EE" }] },
    cursor: { event_seq: 1 },
    hierarchy_binding: { project_field: "project_id", ctrl_membership_field: "controller_ids", task_identity_field: "id", assignment_task_field: "task_id", levels: ["PROJECT", "CTRL", "LEAD", "DOER"] },
    command_contract: {
      endpoint: "/api/role-manifests/commands",
      commands: ["ROLE_MANIFEST_CREATE", "ROLE_MANIFEST_REVISE", "ROLE_MANIFEST_RESET"],
      optimistic_concurrency_field: "expected_active_version",
      avatar: { selection_field: "avatar_asset_digest", selection_commands: ["ROLE_MANIFEST_CREATE", "ROLE_MANIFEST_REVISE"], requires_retained_immutable_asset: true, generation_command: null },
    },
    claim_limit: "Server-owned role manifests are projected without transferring task authority.",
  };
}
assert.doesNotMatch(app, /ROLE_PROFESSIONS|\["accountant", "Accountant"\]|\["critic", "Critic"\]/);
assert.match(app, /function roleManifestProjection\(\)/);
assert.match(app, /filtered\.map\(\(\{ role, match \}\) => roleChooserMarkup\(role, match, role\.id === state\.selectedRoleId\)\)\.join\(""\)/);
const roleProjectionStart = app.indexOf("function roleManifestProjectionValue");
const roleProjectionEnd = app.indexOf("\nfunction roleManifestProjection()", roleProjectionStart);
const evaluateRoleProjection = vm.runInNewContext(`(() => { ${app.slice(roleProjectionStart, roleProjectionEnd)}; return roleManifestProjectionValue; })()`);
const validRoleProjection = roleManifestFixture();
assert.equal(roleAvatarFixtures.size, 24);
assert.equal(validRoleProjection.roles.every((role) => roleAvatarFixtures.has(role.id) && role.avatar?.state === "AVAILABLE" && role.avatar.digest === crypto.createHash("sha256").update(roleAvatarFixtures.get(role.id)).digest("hex")), true);
assert.equal(evaluateRoleProjection(validRoleProjection).roles.length, 24);
assert.equal(evaluateRoleProjection({ ...validRoleProjection, roles: validRoleProjection.roles.filter((role) => role.id !== "assistant") }), null);
const historicalCriticProjection = { ...validRoleProjection, roles: [...validRoleProjection.roles, { ...validRoleProjection.roles[0], id: "critic", name: "Critic", built_in: false }] };
assert.equal(evaluateRoleProjection(historicalCriticProjection).roles.length, 25);
const roleCurrentStart = app.indexOf("function roleCurrentRecords");
const roleCurrentEnd = app.indexOf("\nfunction roleRecord", roleCurrentStart);
const evaluateRoleCurrentRecords = vm.runInNewContext(`(() => { ${app.slice(roleCurrentStart, roleCurrentEnd)}; return roleCurrentRecords; })()`);
assert.equal(evaluateRoleCurrentRecords(historicalCriticProjection).some((role) => role.id === "critic"), false);
assert.equal(evaluateRoleCurrentRecords(historicalCriticProjection).length, 24);
const roleDisplayStart = app.indexOf("function roleDisplayName");
const roleDisplayEnd = app.indexOf("\nfunction roleAvatar", roleDisplayStart);
const evaluateRoleDisplayName = vm.runInNewContext(`(() => { ${app.slice(roleDisplayStart, roleDisplayEnd)}; return roleDisplayName; })()`);
assert.equal(evaluateRoleDisplayName({ id: "dev", name: "Dev" }), "Dev");
assert.equal(evaluateRoleDisplayName({ id: "developer", name: "Software builder" }), "Software builder");
assert.equal(evaluateRoleDisplayName({ id: "designer", name: "Designer" }), "Designer");
const roleSearchStart = app.indexOf("function roleSearchBuckets");
const roleSearchEnd = app.indexOf("\nfunction roleFilterChipsMarkup", roleSearchStart);
const roleSearchHelpers = vm.runInNewContext(`(() => { function roleSpecializations(role) { return role.specializations || []; } ${app.slice(roleSearchStart, roleSearchEnd)}; return { roleSearchMatch, roleFilterRecords }; })()`);
const searchableRole = { id: "developer", name: "Developer", built_in: true, specializations: ["Game Development"], aliases: ["Coder"], tags: ["Software"], default_skills: ["javascript"], purpose: "Build reliable products" };
for (const [query, label] of [["developer", "profession"], ["game", "specialization"], ["coder", "alias or tag"], ["javascript", "skill"], ["reliable", "purpose"]]) {
  const result = roleSearchHelpers.roleSearchMatch(searchableRole, query, new Set(["profession", "specialization", "alias", "skills", "purpose"]));
  assert.equal(result.matched, true);
  assert.match(result.label, new RegExp(label));
}
assert.equal(roleSearchHelpers.roleSearchMatch(searchableRole, "coder", new Set(["profession"])).matched, false);
assert.equal(roleSearchHelpers.roleFilterRecords([searchableRole], "game", new Set(["builtin"]), new Set(["specialization"])).length, 1);
assert.equal(roleSearchHelpers.roleFilterRecords([searchableRole], "game", new Set(["custom"]), new Set(["specialization"])).length, 0);
assert.equal(evaluateRoleProjection({ ...validRoleProjection, roles: validRoleProjection.roles.map((role) => role.id === "developer" ? { ...role, specializations: role.specializations.slice(0, 3) } : role) }), null);
const customRoleProjection = { ...validRoleProjection, roles: [...validRoleProjection.roles, { ...validRoleProjection.roles[0], id: "custom-helper", name: "Custom helper", source: "custom", built_in: false, specializations: [] }] };
assert.equal(evaluateRoleProjection(customRoleProjection).roles.length, 25);
assert.equal(evaluateRoleProjection({ ...customRoleProjection, roles: customRoleProjection.roles.map((role) => role.id === "custom-helper" ? { ...role, specializations: ["1", "2", "3", "4", "5"] } : role) }), null);
const roleCommandStart = app.indexOf("function roleCommandPayload");
const roleCommandEnd = app.indexOf("\nfunction roleEditorCommand", roleCommandStart);
const roleCommandHelpers = vm.runInNewContext(`(() => { ${app.slice(roleCommandStart, roleCommandEnd)}; return { roleCommandPayload, roleCommandFingerprint, roleCommandReceiptMatches, roleCommandObserved, roleCommandResolution, roleCurrentIdAllowed }; })()`);
const manifestDraft = { name: "Custom helper", purpose: "Help", owns: [], instructions: [], boundaries: [], default_skills: [], specializations: [], avatar_asset_digest: "f".repeat(64), accent: "#ff6948" };
const createPayload = roleCommandHelpers.roleCommandPayload("ROLE_MANIFEST_CREATE", "custom-helper", null, manifestDraft, "event-create", "dedupe-create", 100);
assert.deepEqual(JSON.parse(JSON.stringify(createPayload)), { command: "ROLE_MANIFEST_CREATE", role_id: "custom-helper", event_id: "event-create", dedupe_key: "dedupe-create", expected_active_version: null, provenance: "console:role-library", observed_at_ms: 100, manifest: manifestDraft });
const revisePayload = roleCommandHelpers.roleCommandPayload("ROLE_MANIFEST_REVISE", "developer", "developer-v1", manifestDraft, "event-revise", "dedupe-revise", 101);
assert.equal(revisePayload.expected_active_version, "developer-v1");
const resetPayload = roleCommandHelpers.roleCommandPayload("ROLE_MANIFEST_RESET", "developer", "developer-v2", null, "event-reset", "dedupe-reset", 102);
assert.equal(Object.hasOwn(resetPayload, "manifest"), false);
assert.equal(roleCommandHelpers.roleCommandReceiptMatches({ ok: true, receipt: { command: "ROLE_MANIFEST_REVISE", role_id: "developer", event_id: "event-revise" } }, revisePayload), true);
assert.equal(roleCommandHelpers.roleCommandObserved({ roles: [{ id: "developer", source_event_ids: ["event-revise"] }] }, revisePayload), true);
assert.equal(roleCommandHelpers.roleCommandResolution(null, { status: 409 }, true, false), "conflict");
assert.equal(roleCommandHelpers.roleCommandResolution(null, { status: 400 }, true, false), "rejected");
assert.equal(roleCommandHelpers.roleCommandResolution(null, { status: 403 }, true, false), "rejected");
assert.equal(roleCommandHelpers.roleCommandResolution(null, { status: 500 }, true, false), "ambiguous");
assert.equal(roleCommandHelpers.roleCommandResolution(null, { connectionFailure: true }, true, false), "ambiguous");
assert.equal(roleCommandHelpers.roleCommandResolution({ ok: true }, null, false, false), "accepted-unreadable");
assert.equal(roleCommandHelpers.roleCommandResolution(null, null, true, false), "ambiguous");
assert.equal(roleCommandHelpers.roleCommandResolution(null, { status: 409 }, true, true), "observed");
assert.equal(roleCommandHelpers.roleCurrentIdAllowed("assistant"), true);
assert.equal(roleCommandHelpers.roleCurrentIdAllowed("custom-helper"), true);
assert.equal(roleCommandHelpers.roleCurrentIdAllowed("critic"), false);
assert.equal(roleCommandHelpers.roleCurrentIdAllowed("Critic"), false);
assert.equal(roleCommandHelpers.roleCurrentIdAllowed("unsafe role"), false);
const roleAvatarStart = app.indexOf("function roleAvatarDigestAllowed");
const roleAvatarEnd = app.indexOf("\nfunction roleAvatarDigestValid", roleAvatarStart);
const evaluateRoleAvatarDigest = vm.runInNewContext(`(() => { ${app.slice(roleAvatarStart, roleAvatarEnd)}; return roleAvatarDigestAllowed; })()`);
assert.equal(evaluateRoleAvatarDigest("a".repeat(64), [{ avatar_asset_digest: "a".repeat(64) }], []), true);
assert.equal(evaluateRoleAvatarDigest("b".repeat(64), [], [{ digest: "b".repeat(64) }]), true);
assert.equal(evaluateRoleAvatarDigest("c".repeat(64), [], []), false);
assert.equal((app.match(/window\.localStorage/g) || []).length, 3);
assert.doesNotMatch(app, /sessionStorage/);
assert.match(indexHtml, /id="role-editor" aria-labelledby="role-editor-title"/);
assert.match(indexHtml, /id="role-search" type="search" autocomplete="off" placeholder="Search roles"/);
assert.match(indexHtml, /class="role-filter"[\s\S]*class="quiet-button role-filter-trigger"[\s\S]*>Filter<[\s\S]*data-role-search-field="profession"[\s\S]*data-role-search-field="specialization"[\s\S]*data-role-search-field="alias"[\s\S]*data-role-search-field="skills"[\s\S]*data-role-search-field="purpose"/);
assert.match(indexHtml, /class="role-library-control-actions"[\s\S]*class="primary-action role-create-action"[^>]*>[\s\S]*>Add</);
assert.doesNotMatch(indexHtml, /data-role-type="builtin"|data-role-type="custom"/);
assert.match(app, /roleSearchFields: new Set\(\["profession", "specialization", "alias", "skills", "purpose"\]\)/);
assert.match(app, /filtered\.map\(\(\{ role, match \}\) => roleChooserMarkup\(role, match, role\.id === state\.selectedRoleId\)\)/);
assert.match(indexHtml, /id="role-library-grid" role="listbox" aria-label="Roles"/);
assert.match(indexHtml, /id="role-library-detail" aria-live="polite"/);
assert.doesNotMatch(app, /Game Development|Game Design/);
for (const field of ["role-field-id", "role-field-name", "role-field-purpose", "role-field-owns", "role-field-instructions", "role-field-boundaries", "role-field-skills", "role-field-avatar", "role-field-accent", "role-field-specializations", "role-field-version", "role-field-source"]) assert.match(indexHtml, new RegExp(`id="${field}"`));
assert.match(indexHtml, /Tasks already in progress keep the version they started with/);
assert.match(indexHtml, /Choose a retained immutable image asset/);
assert.doesNotMatch(indexHtml, /Choose in Assets/);
assert.doesNotMatch(indexHtml + app, /data-role-action="generate-avatar"|aria-label="Generate avatar"/);
assert.match(app, /function roleSpecializations\(role\)/);
assert.match(app, /role\.specializations[\s\S]*?\.slice\(0, 4\)/);
assert.match(app, /roleDetailDisclosure\("Specializations", roleSpecializationsMarkup\(role\)\)/);
assert.doesNotMatch(indexHtml + app, /Game Development|Game Design/);
assert.match(indexHtml, /id="role-save" type="submit" disabled/);
assert.match(indexHtml, /id="role-reset" data-role-action="reset" type="button" disabled/);
assert.match(app, /state\.roleEditorTrigger = \["edit", "avatar"\]\.includes\(trigger\?\.dataset\.roleAction\)/);
assert.match(app, /\.showModal\(\)/);
assert.match(app, /await api\('\/api\/role-manifests'\)/);
assert.match(server, /if path == "\/api\/role-manifests":[\s\S]*?role_manifest_projection\(\)/);
assert.doesNotMatch(server.slice(server.indexOf('if path == "/api/role-manifests":'), server.indexOf("role_avatar_match", server.indexOf('if path == "/api/role-manifests":'))), /limit|cursor|page/);
assert.match(server, /asset listing accepts only project_id and projection/);
assert.doesNotMatch(app.slice(app.indexOf("async function refreshAssets"), app.indexOf("function assetImageMarkup")), /inventoryParams\.set\("(?:limit|cursor|page)/);
assert.match(app, /await api\("\/api\/role-manifests\/commands"/);
assert.match(app, /const reloaded = await refreshRoleManifests\(\)/);
assert.match(app, /roleCommandResolution\(result, failure, reloaded, observed\)/);
assert.match(app, /Role change rejected:/);
assert.match(app, /if \(!roleCurrentIdAllowed\(roleId\)\) throw new Error\("Choose a safe role ID/);
assert.doesNotMatch(app, /assignment\.task_id \+ " · " \+ \(assignment\.manifest_version/);
assert.doesNotMatch(app.slice(app.indexOf("function roleChooserMarkup"), app.indexOf("function renderRoleLibrary")), /Metadata only|server-owned|Profession · not authority|No authority transfer|Active tasks retain/);
assert.match(css, /\.role-avatar/);
assert.match(css, /\.role-library-grid/);
assert.match(css, /\.role-editor::backdrop/);
assert.match(app, /function safeRoleAvatarURL\(value, expectedDigest\)[\s\S]*?apiMatch\[2\]\.toLowerCase\(\) === expectedDigest[\s\S]*?role-avatars/);
assert.match(app, /function retainedRoleAvatar\(role\)[\s\S]*?avatar_asset_digest[\s\S]*?assetItems\(\)[\s\S]*?preview\?\.state === "AVAILABLE"/);
assert.match(app, /function roleAvatar\(role\)[\s\S]*?class="role-avatar is-mini"[\s\S]*?class="role-avatar has-image"[\s\S]*?<img loading="lazy"/);
assert.match(app, /function roleHasRetainedAvatar\(role\) \{ return Boolean\(retainedRoleAvatar\(role\)\); \}/);
assert.match(css, /\.role-avatar\.is-unavailable \{[^}]*border-style:dashed/);
assert.doesNotMatch(css, /\.role-avatar i::before|\.role-avatar i::after/);
const roleAvatarHelperStart = app.indexOf("function safeRoleAvatarURL");
const roleAvatarHelperEnd = app.indexOf("\nfunction roleAvatar", roleAvatarHelperStart);
const roleAvatarHelpers = vm.runInNewContext(`(() => {
  let items = [];
  function assetItems() { return items; }
  function assetTechnical(item) { return item.technical || {}; }
  ${app.slice(roleAvatarHelperStart, roleAvatarHelperEnd)}
  return { retainedRoleAvatar, setItems(next) { items = next; } };
})()`);
const avatarDigest = "8".repeat(64);
assert.equal(roleAvatarHelpers.retainedRoleAvatar({ avatar_asset_digest: avatarDigest, avatar: { digest: avatarDigest, state: "AVAILABLE", url: "//evil.example/avatar.png" } }), null);
assert.equal(roleAvatarHelpers.retainedRoleAvatar({ avatar_asset_digest: avatarDigest, avatar: { digest: avatarDigest, state: "AVAILABLE", url: "/api/assets/../preview?digest=" + avatarDigest } }), null);
assert.equal(roleAvatarHelpers.retainedRoleAvatar({ avatar_asset_digest: avatarDigest, avatar: { digest: avatarDigest, state: "AVAILABLE", url: "/api/assets/%2e%2e/preview?digest=" + avatarDigest } }), null);
assert.equal(roleAvatarHelpers.retainedRoleAvatar({ avatar_asset_digest: avatarDigest, avatar: { digest: "7".repeat(64), state: "AVAILABLE", url: "/assets/role-avatars/developer.png" } }), null);
assert.equal(roleAvatarHelpers.retainedRoleAvatar({ avatar_asset_digest: avatarDigest, avatar: { digest: avatarDigest, state: "PENDING", url: "/assets/role-avatars/developer.png" } }), null);
assert.equal(roleAvatarHelpers.retainedRoleAvatar({ avatar_asset_digest: avatarDigest, avatar: { digest: avatarDigest, state: "AVAILABLE", url: "/assets/role-avatars/developer.png" } }).url, "/assets/role-avatars/developer.png");
roleAvatarHelpers.setItems([{ technical: { digest: avatarDigest }, preview: { state: "AVAILABLE", url: "/api/assets/role-avatar-developer/preview?digest=" + avatarDigest } }]);
assert.equal(roleAvatarHelpers.retainedRoleAvatar({ avatar_asset_digest: avatarDigest }).url, "/api/assets/role-avatar-developer/preview?digest=" + avatarDigest);
roleAvatarHelpers.setItems([{ technical: { digest: avatarDigest }, preview: { state: "AVAILABLE", url: "/api/assets/role-avatar-developer/preview?digest=" + "7".repeat(64) } }]);
assert.equal(roleAvatarHelpers.retainedRoleAvatar({ avatar_asset_digest: avatarDigest }), null);
roleAvatarHelpers.setItems([{ technical: { digest: avatarDigest }, preview: { state: "UNAVAILABLE", url: "/api/assets/role-avatar-developer/preview?digest=" + avatarDigest } }]);
assert.equal(roleAvatarHelpers.retainedRoleAvatar({ avatar_asset_digest: avatarDigest }), null);
assert.match(app, /<button class="role-choice/);
assert.match(app, /role="option" aria-label=/);
assert.match(app, /aria-controls="role-library-detail"/);
assert.match(app, /tabindex="' \+ \(selected \? '0' : '-1'\) \+ '"/);
assert.doesNotMatch(app.slice(app.indexOf("function roleChooserMarkup"), app.indexOf("function renderRoleLibrary")), /role-choice-source|Built in|Built-in/);
assert.match(app, /function roleDetailMarkup\(role/);
assert.match(app, /function roleInstructionsMarkup\(items\)/);
assert.match(app, /instructions\.slice\(0, 3\)/);
assert.match(app, /<summary><span class="role-disclosure-more">Show more<\/span><span class="role-disclosure-less">Show less<\/span><\/summary>/);
assert.doesNotMatch(app, /Show all .* instructions/);
assert.match(app, /aria-label="Edit ' \+ escapeHTML\(displayName\)/);
assert.doesNotMatch(app.slice(app.indexOf("function roleChooserMarkup"), app.indexOf("function renderRoleLibrary")), /active_version|avatar_asset_digest|<code>/);
assert.doesNotMatch(app, /reviewerStancesMarkup|Collaborative strengths, gaps, and clear repairs|Red-team the artifact/);
const roleContentStart = app.indexOf("function roleTextList");
const roleContentEnd = app.indexOf("\nfunction renderRoleLibrary", roleContentStart);
const roleContentRenderers = vm.runInNewContext(`(() => {
  const escapeHTML = (value) => String(value ?? "");
  const roleDisplayName = (role) => role?.name || role?.id || "Unknown role";
  const roleAvatar = () => "";
  const roleSourceLabel = (role) => role?.source === "builtin" ? "Built in" : "Custom role";
  const roleCanMutate = () => true;
  const roleAssignmentsMarkup = () => '<p>No current owners.</p>';
  const roleSpecializationsMarkup = (role) => '<ul>' + role.specializations.map((item) => '<li>' + escapeHTML(item) + '</li>').join("") + '</ul>';
  const roleHasRetainedAvatar = () => false;
  ${app.slice(roleContentStart, roleContentEnd)}
  return { roleChooserMarkup, roleDetailMarkup };
})()`);
const manifestDrivenReviewer = {
  id: "reviewer", name: "Fixture review lead", source: "builtin", purpose: "Fixture purpose", owns: ["Fixture surface"],
  instructions: ["Apply the bounded SWARM assignment", "Review evidence against the profession contract", "Fixture instruction three", "Fixture instruction four", "Fixture instruction five"],
  specializations: ["Careful", "Adversarial", "Evidence", "Repair"], default_skills: ["fixture-skill"], boundaries: ["Fixture boundary"],
};
const manifestCard = roleContentRenderers.roleChooserMarkup(manifestDrivenReviewer, { label: "Matched: Fixture review lead · profession" }, true);
const manifestDetail = roleContentRenderers.roleDetailMarkup(manifestDrivenReviewer);
const shortManifestDetail = roleContentRenderers.roleDetailMarkup({ ...manifestDrivenReviewer, instructions: manifestDrivenReviewer.instructions.slice(0, 3) });
for (const value of ["Fixture review lead", "Fixture purpose", "Fixture surface", "Review evidence against the profession contract", "Fixture instruction four", "Careful", "Adversarial", "fixture-skill", "Fixture boundary"]) assert.match(manifestCard + manifestDetail, new RegExp(value));
assert.match(manifestCard, /role-choice-description[\s\S]*Review evidence against the profession contract/);
assert.doesNotMatch(manifestCard, /Apply the bounded SWARM assignment|Fixture purpose/);
assert.match(manifestDetail, /Show more[\s\S]*Show less/);
assert.doesNotMatch(manifestDetail, /Show all|4 instructions/);
assert.doesNotMatch(shortManifestDetail, /<details>|Show more|Show less/);
assert.doesNotMatch(manifestCard + manifestDetail, /Friendly|Hostile/);
const fixtureStances = roleContentRenderers.roleDetailMarkup({ ...manifestDrivenReviewer, specializations: ["Friendly", "Hostile", "Evidence", "Repair"] });
assert.match(fixtureStances, /Friendly[\s\S]*Hostile/);
assert.doesNotMatch(app, /data-role-action="generate-avatar"|Generate matching avatar/);
assert.match(indexHtml, /class="primary-action role-create-action" id="role-create"[\s\S]*?<svg[\s\S]*?<\/svg><span>Add<\/span><\/button>/);
assert.doesNotMatch(indexHtml, /id="role-create"[^>]*>[\s\S]*?Create role<\/button>/);
assert.doesNotMatch(app, /verifiedYieldProjection\(\)\?\.attention_items/);
assert.doesNotMatch(indexHtml + app + css, /--legacy-browser|mockup|prototype reference/i);
assert.doesNotMatch(css, /\.agents-tabs/);
assert.match(css, /\.role-library-layout \{[^}]*grid-template-columns:minmax\(600px,1\.55fr\) minmax\(340px,\.75fr\)/);
assert.match(css, /\.role-library-grid \{[^}]*grid-template-columns:repeat\(4,minmax\(0,1fr\)\)[^}]*overflow:visible/);
assert.match(css, /\.role-choice \{[^}]*min-height:154px[^}]*grid-template-rows:96px auto/);
assert.match(css, /\.role-choice \.role-avatar \{ width:96px; height:96px; \}/);
assert.match(css, /\.role-choice-description \{[^}]*-webkit-line-clamp:2[^}]*white-space:normal/);
assert.match(css, /\.notification-trigger \{ --circle-size:44px;[^}]*position:relative/);
assert.match(css, /\.loading-skeleton \{[^}]*grid-column:1 \/ -1/);
assert.match(css, /\.collection-more \.quiet-button \{[^}]*min-height:44px/);
assert.match(css, /@media \(prefers-reduced-motion: reduce\)[\s\S]*\.loading-skeleton i \{ animation:none!important; \}/);
assert.match(app, /function boundedCollectionWindow\(items, step\)/);
assert.doesNotMatch(app, /boundedCollectionPage|collectionPagerMarkup/);
assert.match(app, /function loadingSkeletonMarkup\(count = 8\)/);
assert.match(app, /loading \? loadingSkeletonMarkup\(\)/);
assert.doesNotMatch(app, /collectionLoadMoreMarkup\("roles"/);
assert.match(app, /collectionLoadMoreMarkup\("assets", collection, "Assets"\)/);
assert.match(app, /collectionLoadMoreMarkup\("artifacts", collection, "Project artifacts"\)/);
assert.doesNotMatch(app, /IntersectionObserver|setInterval\([^)]*(?:asset|role|artifact)|setTimeout\([^)]*(?:asset|role|artifact)/i);
assert.match(app, /choice\?\.scrollIntoView\(\{ block: "nearest", inline: "nearest" \}\)/);
assert.match(css, /\.role-detail-sections section,\.reviewer-stances \{[^}]*grid-template-columns:128px minmax\(0,1fr\)/);
assert.match(css, /\.role-library-detail \{[^}]*position:sticky[^}]*overflow-y:auto; scrollbar-gutter:stable/);
assert.match(css, /\.role-library-detail \{ min-width:0; overflow-x:hidden; overflow-y:auto; overflow-wrap:anywhere; \}/);
assert.match(css, /@media \(max-width: 1220px\)[\s\S]*\.role-detail-head \{ grid-template-columns:72px minmax\(0,1fr\);[^}]*\}[\s\S]*\.role-detail-actions \{ grid-column:1 \/ -1; justify-content:flex-end; \}/);
assert.match(css, /@media \(max-width: 860px\)[\s\S]*\.role-detail-actions \.icon-button,\.role-editor-head \.icon-button \{ width:44px; height:44px; flex-basis:44px; \}/);
assert.match(css, /@media \(max-width: 860px\)[\s\S]*\.role-editor-actions \.quiet-button,\.role-editor-actions \.primary-action \{ min-height:44px; \}/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.role-library-layout \{ display:block; \}[\s\S]*\.role-library-grid \{[^}]*grid-template-columns:repeat\(2,minmax\(0,1fr\)\)[^}]*overflow:visible[\s\S]*\.role-choice \{ min-height:60px/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.role-filter > summary \{ width:44px; height:44px; \}/);
assert.match(css, /:is\(\.circle-frame,\.support-mark,\.scope-dot,\.status-dot,\.agent-avatar-token,\.agent-live-dot,\.agent-work-status,\.activity-dot,\.state-illustration-prop,\.message-launcher,\.mobile-message-action,\.milestone-ring,\.project-roadmap article > span,\.project-block-state,\.diagnostics-hero-icon,\.diagnostics-check-token > span,#role-field-accent\) \{[^}]*aspect-ratio:1 \/ 1; flex-shrink:0; border-radius:50%/);
assert.match(css, /\.circle-frame \{ --circle-size:40px;[^}]*inline-size:var\(--circle-size\); block-size:var\(--circle-size\); flex:0 0 var\(--circle-size\);[^}]*overflow:visible/);
assert.match(css, /\.circle-frame img \{[^}]*width:100%; height:100%; object-fit:cover/);
assert.match(css, /\.scope-dot \{ --circle-size:7px;[^}]*inline-size:var\(--circle-size\); block-size:var\(--circle-size\); flex:0 0 var\(--circle-size\)/);
assert.match(css, /\.status-dot \{ --circle-size:8px;[^}]*inline-size:var\(--circle-size\); block-size:var\(--circle-size\); flex:0 0 var\(--circle-size\)/);
assert.match(css, /#role-field-accent \{ inline-size:44px; block-size:44px; min-inline-size:44px;/);
assert.match(css, /\* \{ scrollbar-width:thin; scrollbar-color:rgba\(91,112,140,\.72\) var\(--base-deep\)/);
assert.match(css, /\.message-composer \{ top:0; right:0; bottom:0;[^}]*height:100dvh;[^}]*border-radius:0;/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*?\.mobile-message-footer \{ grid-auto-flow:column; grid-auto-columns:minmax\(48px,1fr\); grid-template-columns:none;[\s\S]*?overflow-x:auto;[\s\S]*?\.message-composer \{ inset:0; width:100vw; height:100dvh;/);
assert.match(css, /\.settings-toggle-grid \{ grid-template-columns:repeat\(3,minmax\(0,1fr\)\); \}/);
assert.match(css, /\.settings-switch input:checked \+ span \{[^}]*background:linear-gradient\(120deg,var\(--orange\),var\(--coral\)\)/);
assert.match(css, /--orange:\s*#FF7A18;/);
assert.match(css, /--coral:\s*#FF3D32;/);
assert.doesNotMatch(app + css + indexHtml, /onboarding-ctrl-node|onboarding-executive-node|onboarding-coordination-stage|data-onboarding-edge|onboardingFlowZoom/);
assert.doesNotMatch(css, /#ff7449|#ff526f|#ff784c|#ff8b25|#ff4937/i);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.circle-frame \{ --circle-size:44px; \}/);
assert.doesNotMatch(css, /\.profile-button[^}]*width:\s*\d+px;|\.profile-button[^}]*height:\s*\d+px;/);
assert.match(css, /\.role-editor-fields input,.role-editor-fields textarea,.role-editor-fields select[\s\S]*?\.role-editor-fields input,.role-editor-fields select \{ min-height:44px; \}/);
assert.doesNotMatch(indexHtml, /class="project-tabs"/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.review-actions \.icon-button,\.review-actions summary \{ width:44px; height:44px; \}/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.settings-save-bar button,\.config-editor-footer button \{ flex:1; \}/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.error-surface \{ top:calc\(64px \+ env\(safe-area-inset-top\) \+ 8px\);/);
assert.match(css, /\.error-surface button \{[^}]*min-height:44px;/);
assert.match(css, /\.assets-layout/);
assert.match(css, /\.asset-dialog \{[^}]*margin:auto;[^}]*padding:0;/);
assert.match(css, /\.asset-dialog-header \{[^}]*display:flex;[^}]*justify-content:space-between/);
assert.match(css, /\.asset-dialog-footer \{[^}]*display:flex;[^}]*border-top:1px solid var\(--line\)/);
assert.match(css, /\.asset-dialog-content \{[^}]*padding:18px 20px/);
assert.match(css, /\.asset-quick-actions \.icon-button \{ width:44px; height:44px/);
assert.match(css, /\.asset-list-actions \.icon-button \{ width:44px; height:44px/);
assert.match(css, /\.project-overview-grid/);
assert.match(css, /\.notifications-panel/);
const roleGridTargetStart = app.indexOf("function roleGridTargetIndex");
const roleGridTargetEnd = app.indexOf("\nfunction renderRoleLibrary", roleGridTargetStart);
const roleGridTargetIndex = vm.runInNewContext(`(() => { ${app.slice(roleGridTargetStart, roleGridTargetEnd)}; return roleGridTargetIndex; })()`);
assert.equal(roleGridTargetIndex("ArrowRight", 0, 24, 4), 1);
assert.equal(roleGridTargetIndex("ArrowRight", 3, 24, 4), 3);
assert.equal(roleGridTargetIndex("ArrowDown", 1, 24, 3), 4);
assert.equal(roleGridTargetIndex("ArrowDown", 22, 24, 3), 23);
assert.equal(roleGridTargetIndex("ArrowLeft", 3, 24, 3), 3);
assert.equal(roleGridTargetIndex("Home", 17, 24, 2), 0);
assert.equal(roleGridTargetIndex("End", 0, 24, 2), 23);
assert.match(app, /roleEditorTrigger = \["edit", "avatar"\]\.includes\(trigger\?\.dataset\.roleAction\)[\s\S]*\{ action: trigger\.dataset\.roleAction, roleId:/);
assert.match(app, /function roleEditorReturnTarget\(origin\)/);
assert.match(app, /if \(trigger && !trigger\.disabled && !trigger\.hidden\) return trigger;/);
assert.match(app, /requestAnimationFrame\(\(\) => \{[\s\S]*roleEditorReturnTarget\(origin\)/);
assert.match(app, /addEventListener\("cancel", \(event\) => \{ event\.preventDefault\(\); closeRoleEditor\(\); \}\)/);
assert.match(app, /addEventListener\("close", restoreRoleEditorFocus\)/);
 assert.match(app, /class="panel settings-advanced-drawer" id="settings-advanced"/);
for (const forbidden of ["hidden usage", "developer instructions", "prompts", "tools", "credentials"]) {
  assert.equal((indexHtml + app).toLowerCase().includes(forbidden), false, `forbidden copy: ${forbidden}`);
}

{
  const window={after_ms:1000000,before_ms:1600000};
  const point={thread_id:'a',project_id:'p',bucket_start_ms:1000000,bucket_end_ms:1300000,rate_start_ms:1000000,rate_end_ms:1300000,tokens:100,tokens_per_minute:20,model:null};
  const state={projectId:'all',ctrlId:'',usageWindowHours:24,usageStatus:'current',usageScopeKey:'key',usageHistory:{ok:true,hours:24,scope:{type:'all-projects'},window,task_usage:[{thread_id:'a',project_id:'p',title:'Alpha',tokens:100},{thread_id:'b',project_id:'p',title:'Beta',tokens:50}],task_history:{status:'partial',items:[point,{...point,bucket_start_ms:1300000,bucket_end_ms:1600000,rate_start_ms:1300000,rate_end_ms:1600000}],total_tokens:200}}};
  const host={setAttribute(){},innerHTML:''}, dialog={dataset:{}};
  const sandbox={state,Map,Set,Date,escapeHTML:String,usageRequestKey:()=> 'key',usageRangeLabel:()=> 'last 24 hours',$:selector=>selector==='#metric-detail-dialog'?dialog:host};
  vm.createContext(sandbox);
  vm.runInContext(app.slice(app.indexOf('function compactNumber('),app.indexOf('function formatBytes(')),sandbox);
  assert.equal(sandbox.compactNumber(2200000000), '2.2B');
  vm.runInContext(app.slice(app.indexOf('function highestUsageTaskRows('),app.indexOf('function diagnosticChecks(')),sandbox);
  sandbox.renderHighestUsageTasks();
  assert.match(host.innerHTML, /<th scope="col">Task<\/th><th scope="col">Model<\/th><th scope="col">Tokens<\/th><th scope="col">Share/);
  assert.match(host.innerHTML,/50.0%/,'Share uses all measured tokens, not top ten sum');
  assert.match(host.innerHTML,/Historical model unavailable/);
  assert.match(host.innerHTML,/data-task-usage-id="b" disabled/,'No fabricated history for aggregate-only task');
  const history=sandbox.taskUsageHistory();
  const graph=sandbox.taskUsageGraph([state.usageHistory.task_usage[0]],history);
  assert.match(graph,/M32.00,25.00 L320.00,25.00 L608.00,25.00/,'Steady measured rate is flat, not declining allowance');
  assert.doesNotMatch(graph,/<circle/);
  assert.equal(sandbox.taskUsageColor('a'),sandbox.taskUsageColor('a'));
  assert.notEqual(sandbox.taskUsageColor('a'),sandbox.taskUsageColor('b'));
  dialog.dataset.taskView='graph'; sandbox.renderHighestUsageTasks();
  assert.match(host.innerHTML,/Task comparison view/); assert.match(host.innerHTML,/Legend/);
  dialog.dataset.hiddenTaskIds='["a"]'; sandbox.renderHighestUsageTasks();
  assert.match(host.innerHTML,/data-task-usage-visible="a" aria-pressed="false"/);
  assert.doesNotMatch(host.innerHTML,/<title>Alpha<\/title>/);
  sandbox.renderHighestUsageTasks(); assert.match(host.innerHTML,/data-task-usage-visible="a" aria-pressed="false"/,'Refresh retains task visibility');
  dialog.dataset.hiddenTaskIds='[]'; sandbox.renderHighestUsageTasks(); assert.match(host.innerHTML,/<title>Alpha<\/title>/);
  dialog.dataset.taskId='a'; sandbox.renderHighestUsageTasks();
  assert.match(host.innerHTML,/All tasks/); assert.match(host.innerHTML,/<h3>Alpha/);
  dialog.dataset.hideLegend='true'; sandbox.renderHighestUsageTasks();
  assert.doesNotMatch(host.innerHTML,/class="task-usage-legend"/);
  state.usageHistory.task_history.items[1].rate_start_ms=1400000;
  assert.match(sandbox.taskUsageGraph([state.usageHistory.task_usage[0]],sandbox.taskUsageHistory()),/M416.00/,'Missing interval remains a gap');
  state.usageHistory.scope={type:'project',project_id:'foreign'};
  assert.equal(sandbox.taskUsageHistory(),null);
  state.usageHistory.scope={type:'all-projects'};state.usageStatus='stale';
  assert.equal(sandbox.taskUsageHistory(),null);
}
{
  const state={projectId:'all',ctrlId:'',usageWindowHours:24,usageRequestGeneration:0,usageStatus:'current'};
  const requests=[];
  const sandbox={state,URLSearchParams,api:url=>new Promise((resolve,reject)=>requests.push({url,resolve,reject}))};
  vm.createContext(sandbox);
  vm.runInContext(app.slice(app.indexOf('function usageRequestKey('),app.indexOf('function usageHistorySeries(')) + app.slice(app.indexOf('async function refreshUsageHistory('),app.indexOf('async function refreshProjectProgress(')),sandbox);
  state.usageDateRange={after_ms:1000,before_ms:2000};
  const old=sandbox.refreshUsageHistory();
  state.usageDateRange={after_ms:3000,before_ms:4000};
  const latest=sandbox.refreshUsageHistory();
  assert.match(requests[1].url,/after_ms=3000&before_ms=4000/);
  const result={ok:true,hours:24,scope:{type:'all-projects'},window:{explicit:true,after_ms:3000,before_ms:4000}};
  requests[1].resolve(result); await latest;
  requests[0].reject(new Error('Old dates failed')); await old;
  assert.equal(state.usageHistory,result); assert.equal(state.usageStatus,'current');
  const mismatch=sandbox.refreshUsageHistory(); requests[2].resolve({...result,window:{...result.window,before_ms:5000}}); await mismatch;
  assert.equal(state.usageStatus,'stale'); assert.match(state.usageError,/selected dates/);
  assert.equal(state.usageHistory,result);
  const wrongScope=sandbox.refreshUsageHistory(); requests[3].resolve({...result,scope:{type:'project',project_id:'foreign'}}); await wrongScope;
  assert.equal(state.usageStatus,'stale'); assert.match(state.usageError,/selected scope/);
}
{
  const usageState = { projectId: "all", ctrlId: "", usageWindowHours: 1, usageScopeKey: "all||1", usageStatus: "current", usageHistory: { ok: true, items: [{ bucket_ms: 2, delta_tokens: 9 }], task_usage: [
    { thread_id: "small", title: "Small", project_id: "p", tokens: 2 },
    { thread_id: "large", title: "Large", project_id: "p", tokens: 80 },
    { thread_id: "missing", title: "Missing", project_id: "p", tokens: null },
    { thread_id: "minutes", title: "Minutes", project_id: "p", active_minutes: 100 },
  ] } };
  const usageContext = vm.createContext({ state: usageState });
  vm.runInContext(app.slice(app.indexOf("function usageRequestKey"), app.indexOf("function usageRangeLabel")) +
    app.slice(app.indexOf("function highestUsageTaskRows"), app.indexOf("function renderHighestUsageTasks")), usageContext);
  assert.equal(JSON.stringify(vm.runInContext("highestUsageTaskRows().map(row => row.thread_id)", usageContext)), '["large","small"]');
  assert.equal(JSON.stringify(vm.runInContext("usageHistorySeries()", usageContext)), "[9]");
  usageState.usageHistory.items.push({ bucket_ms: 3, delta_tokens: null });
  assert.equal(JSON.stringify(vm.runInContext("usageHistorySeries()", usageContext)), "[9]");
  usageState.usageWindowHours = 168;
  assert.equal(vm.runInContext("highestUsageTaskRows()", usageContext), null);
  usageState.usageScopeKey = "all||168";
  usageState.usageHistory.task_usage = Array.from({ length: 15 }, (_, index) => ({ thread_id: String(index), title: "Task", project_id: "p", tokens: index }));
  assert.equal(vm.runInContext("highestUsageTaskRows().length", usageContext), 10);
  usageState.projectId = "another";
  assert.equal(vm.runInContext("highestUsageTaskRows()", usageContext), null);
  usageState.usageScopeKey = "another||168";
  assert.equal(vm.runInContext("highestUsageTaskRows().length", usageContext), 0);
  usageState.usageRequestGeneration = 0;
  let releaseUsage;
  const requestContext = vm.createContext({ state: usageState, URLSearchParams, api: () => new Promise((resolve) => { releaseUsage = resolve; }) });
  vm.runInContext(app.slice(app.indexOf("function usageRequestKey"), app.indexOf("function usageHistorySeries")) +
    app.slice(app.indexOf("async function refreshUsageHistory"), app.indexOf("async function refreshProjectProgress")), requestContext);
  const pendingUsage = vm.runInContext("refreshUsageHistory()", requestContext);
  const retainedUsage = usageState.usageHistory;
  usageState.projectId = "switched";
  usageState.ctrlId = "other-ctrl";
  releaseUsage({ ok: true, task_usage: [{ thread_id: "old", title: "Old scope", project_id: "another", tokens: 900 }] });
  await pendingUsage;
  assert.equal(usageState.usageHistory, retainedUsage, "old project/CTRL response cannot replace current scope");
  for (const staleOutcome of ["success", "error"]) {
    const deferred = [];
    requestContext.api = () => new Promise((resolve, reject) => deferred.push({ resolve, reject }));
    usageState.usageWindowHours = 1;
    const oldHour = vm.runInContext("refreshUsageHistory()", requestContext);
    usageState.usageWindowHours = 24;
    const day = vm.runInContext("refreshUsageHistory()", requestContext);
    usageState.usageWindowHours = 1;
    const newHour = vm.runInContext("refreshUsageHistory()", requestContext);
    const current = { ok: true, items: [{ bucket_ms: 4, delta_tokens: 12 }], task_usage: [] };
    deferred[2].resolve(current);
    await newHour;
    const accepted = [usageState.usageHistory, usageState.usageScopeKey, usageState.usageStatus, usageState.usageError];
    deferred[1].resolve({ ok: true, items: [], task_usage: [] });
    await day;
    if (staleOutcome === "error") deferred[0].reject(new Error("obsolete hour failed"));
    else deferred[0].resolve({ ok: true, items: [{ bucket_ms: 1, delta_tokens: 900 }], task_usage: [] });
    await oldHour;
    assert.deepEqual([usageState.usageHistory, usageState.usageScopeKey, usageState.usageStatus, usageState.usageError], accepted,
      `1h → 1d → 1h: obsolete ${staleOutcome} cannot replace the latest request`);
  }
}
{
  const hostState = { projectId: "p1", ctrlId: "", connectionStatus: "live", projectProgressStatus: "current", overview: { nodes: [
    ...["active", "in_progress", "blocked", "done", "waiting"].map((status, index) => ({ id: "host-" + index, title: "Observed " + index, project_id: "p1", status, controller_ids: ["c1"] })),
    { id: "foreign", title: "Other project", project_id: "p2", status: "active" },
    { id: "virtual", project_id: "p1", status: "active", virtual: true },
  ] } };
  const context = vm.createContext({ state: hostState, selectedProgressProjectId: () => hostState.projectId,
    activeAgentRecords: () => [], escapeHTML: (value) => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll('"', "&quot;") });
  vm.runInContext(app.slice(app.indexOf("function scopedNodes("), app.indexOf("function setLoading(")), context);
  vm.runInContext(app.slice(app.indexOf("function projectHostWorkMarkup("), app.indexOf("function renderProjectDetail(")), context);
  const render = () => vm.runInContext("projectHostWorkMarkup()", context);
  const current = render();
  assert.equal((current.match(/data-host-work-id=/g) || []).length, 5);
  assert.match(current, /2 reported active · 5 observed/);
  for (const status of ["active", "in_progress", "blocked", "done", "waiting"]) assert.ok(current.includes('data-label="Host status">' + status + '</td>'));
  assert.doesNotMatch(current, /foreign|virtual|role="progressbar"|aria-valuenow|data-agent-detail=/);
  assert.equal((current.match(/Block progress not recorded/g) || []).length, 5);
  context.activeAgentRecords = () => [{node:hostState.overview.nodes[0],identityState:"admitted",binding:{ctrlId:"c1"}}];
  assert.equal((render().match(/data-agent-detail=/g) || []).length, 1, "only existing admitted detail authority gets a link");
  context.activeAgentRecords = () => [];
  hostState.projectProgressStatus = "stale";
  assert.equal(render(), current, "stale Ledger must not erase current host work");
  hostState.ctrlId = "other";
  assert.match(render(), /No host work observed/);
  hostState.ctrlId = "";
  hostState.projectId = "p2";
  assert.equal((render().match(/data-host-work-id=/g) || []).length, 1);
  assert.doesNotMatch(render(), /Observed 0/);
  hostState.connectionStatus = "offline";
  assert.match(render(), /Host work unavailable/);
  assert.doesNotMatch(render(), /reported active|data-host-work-id=/);
  hostState.overview = null;
  assert.match(render(), /Host work unavailable/);
  assert.match(app, /No recorded ' \+ \(segment.segment_id === "segment.project.progress.active" \? "active" : "queued"\)/);
}
{
  const source = app.slice(app.indexOf("function selectedMessageRecipient"), app.indexOf("function canonicalActionValue"));
  const h = vm.runInNewContext(`(() => {
    const state = {messageOpen:true, messageRecipientId:"a", projectId:"p1", ctrlId:"", connectionStatus:"live",
      overview:{nodes:[]},messageRoster:{project_id:"p1",status:"AVAILABLE",truncated:false,items:[{thread_id:"a",project_id:"p1",title:"Retained A"}]}};
    const elements = new Map();
    function $(key) { if(!elements.has(key)) elements.set(key,{innerHTML:"",textContent:"",setAttribute(){},classList:{toggle(){}}}); return elements.get(key); }
    const calls=[];
    function api(url, options) { return new Promise((resolve,reject)=>calls.push({url,body:JSON.parse(options.body),resolve,reject})); }
    function savedProjectRoster(){return {projects:[{id:"p1",label:"One"},{id:"p2",label:"Two"}]};}
    function selectedProgressProjectId(){return state.projectId === "all" ? "" : state.projectId;}
    function runLogBindingForCtrl(){return state.binding || null;}
    function publicLabel(value){return value;}
    function messageRecipients(){return [];}
    function clearCommandApprovals(){} function renderProjectDetail(){} function renderSystemHealth(){} function renderNotifications(){} function renderRunLogSurfaces(){} function formatRelative(){return "now";}
    function renderMessageComposer(){renderMessageHistory();}
    function escapeHTML(value){return String(value).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
    ${source}
    ${app.slice(app.indexOf("function setProjectSelection("),app.indexOf("function renderScopeNotice("))}
    ${app.slice(app.indexOf("function setDataStatus("),app.indexOf("function scopedNodes("))}
    return {state,calls,read:refreshMessageHistory,roster:refreshMessageConversation,select:setProjectSelection,connection:setDataStatus,render:renderMessageHistory,recipients:messageHistoryRecipients,sendRecipient:selectedMessageRecipient,
      rosterText:()=>$("#message-roster-status").textContent,text:()=>$("#message-conversation-state").textContent,html:()=>$("#message-conversation-items").innerHTML};
  })()`, {TextEncoder});
  const snapshot = (thread_id="a", project_id="p1", text="hello") => ({thread_id,project_id,status:"AVAILABLE",truncated:false,cursor:"a".repeat(64),items:[{id:"m1",turn_id:"t1",role:"assistant",text}]});
  const roster = (project_id="p1",thread_id="a") => ({project_id,status:"AVAILABLE",truncated:false,items:[{thread_id,project_id,title:"Retained task"}]});
  assert.deepEqual(Array.from(h.recipients(), x=>x.id),["a"],"read chooser excludes foreign project");
  h.state.ctrlId="ctrl";h.state.binding={projectId:"p2"};
  assert.equal(h.recipients().length,0,"conflicting project/CTRL selection fails closed");
  h.state.binding=null;assert.equal(h.recipients().length,0,"unresolved CTRL is not all projects");h.state.ctrlId="";
  assert.equal(h.sendRecipient(),null,"observed read access grants no send authority");
  let flight=h.read();
  assert.match(h.text(),/Loading/);
  assert.equal(h.calls[0].url,"/api/tasks/history");
  assert.deepEqual({...h.calls[0].body},{project_id:"p1",thread_id:"a"});
  h.calls[0].resolve(snapshot("a","p1",'<img src=x onerror=alert(1)>\nsecond line')); await flight;
  assert.equal(h.state.messageHistory.status,"AVAILABLE");
  assert.match(h.html(),/&lt;img/); assert.doesNotMatch(h.html(),/<img/);
  // A -> B -> A: an older same-key success or failure must not overwrite the latest read.
  const old=h.read();
  h.state.projectId="p2";h.state.messageRecipientId="b";h.state.messageRoster=roster("p2","b"); const foreign=h.read();
  h.state.projectId="p1";h.state.messageRecipientId="a";h.state.messageRoster=roster(); const latest=h.read();
  h.calls[3].resolve(snapshot("a","p1","newest")); await latest;
  h.calls[1].resolve(snapshot("a","p1","old"));await old;
  h.calls[2].reject(new Error("stale transport"));await foreign;
  assert.match(h.html(),/newest/);assert.doesNotMatch(h.html(),/>old</);
  const oldError=h.read();const newest=h.read();
  h.calls[5].resolve(snapshot());await newest;h.calls[4].reject(new Error("old error"));await oldError;
  assert.equal(h.state.messageHistory.status,"AVAILABLE");
  for (const [result,status,copy] of [
    [{...snapshot(),status:"EMPTY",items:[]},"EMPTY",/No messages yet/],
    [{...snapshot(),status:"UNAVAILABLE",items:[],cursor:null},"UNAVAILABLE",/unavailable/],
    [snapshot("b","p2"),"UNAVAILABLE",/unavailable/],
    [{...snapshot(),cursor:null},"UNAVAILABLE",/unavailable/],
    [{...snapshot(),items:[...snapshot().items,...snapshot().items]},"UNAVAILABLE",/unavailable/],
    [{...snapshot(),truncated:true},"AVAILABLE",/Earlier content is omitted/],
  ]) {
    const run=h.read();h.calls.at(-1).resolve(result);await run;
    assert.equal(h.state.messageHistory.status,status);assert.match(h.text(),copy);
  }
  const pending=h.read();h.state.projectId="p2";h.state.messageRecipientId="b";
  h.calls.at(-1).resolve(snapshot());await pending;h.render();
  assert.equal(h.html(),"","scope change hides old transcript even without replacement request");
  h.state.connectionStatus="reconnecting";h.render();assert.match(h.text(),/disconnected/);assert.equal(h.html(),"");
  h.state.messageOpen=false;const count=h.calls.length;await h.read();assert.equal(h.calls.length,count,"closed composer does not read");
  h.state.messageOpen=true;h.state.messageRecipientId="a";h.select("p1");h.connection("current");
  for (const reject of [false,true]) {
    h.state.messageRoster=roster();const run=h.read();const call=h.calls.at(-1);
    h.select("p2");h.select("p1");
    reject ? call.reject(new Error("old")) : call.resolve(snapshot());await run;
    assert.equal(h.state.messageHistory,null,"actual scope setters invalidate ABA with no replacement read");
    h.state.messageRoster=roster();const reconnect=h.read();const response=h.calls.at(-1);
    h.connection("stale");h.connection("current");
    reject ? response.reject(new Error("old")) : response.resolve(snapshot());await reconnect;
    assert.equal(h.state.messageHistory,null,"actual connection setters invalidate reconnect response");
  }
  for (const result of [{...roster(),status:"PARTIAL",truncated:true,items:[]},{...roster(),status:"EMPTY",items:[]},{...roster(),status:"UNAVAILABLE",items:[]},roster("p2","b")]) {
    const run=h.roster();h.calls.at(-1).resolve(result);await run;
    assert.equal(h.recipients().length,0);
    assert.match(h.rosterText(),result.status==="PARTIAL" ? /limited.*omitted/ : result.status==="EMPTY" ? /No retained/ : /unavailable/);
  }
  const retained=h.roster();h.calls.at(-1).resolve(roster());await Promise.resolve();await Promise.resolve();
  assert.deepEqual(Array.from(h.recipients(),x=>x.id),["a"],"inactive target absent Overview remains selectable");
  h.calls.at(-1).resolve(snapshot());await retained;
  assert.equal(h.state.messageHistory.status,"AVAILABLE");
  for (const reject of [false,true]) {
    const oldRoster=h.roster();const call=h.calls.at(-1);h.select("p2");h.select("p1");
    reject ? call.reject(new Error("old roster")) : call.resolve(roster());await oldRoster;
    assert.equal(h.state.messageRoster,null,"roster success/error cannot survive setter ABA");
  }
  assert.match(app,/refreshCommandApprovals\(\), refreshMessageConversation\(\)/,"history uses existing refresh owner");
}
{
  const source=app.slice(app.indexOf("async function refreshOverview("),app.indexOf("async function initialize("));
  for(const delayed of ["refreshUsageHistory","refreshMessageConversation","readConfigState"]) {
    const state={overview:null,config:null};const rendered=[];let loading=false,release;
    const pending=new Promise(resolve=>release=resolve);
    const context={state,Promise,setLoading:value=>loading=value,renderOverview:()=>rendered.push(state.overview),renderAllViews:()=>{},
      api:async()=>({generated_at:123,nodes:[{id:"actual"}]}),overviewRequestPath:()=>"/api/overview",historicalControllers:()=>[],
      clearError(){},clearConnectionState(){},setDataStatus(){},renderProjectNavigation(){},showError(){},showConnectionState(){}};
    for(const name of ["refreshProof","refreshUsageHistory","refreshProjectProgress","refreshProjectProgressFeed","refreshRoleManifests","refreshNotifications","refreshRunLogs","refreshAssets","refreshProfileSummary","refreshCommandApprovals","refreshMessageConversation","readConfigState","refreshDiagnostics","refreshSkills","refreshAutoStatus"]) context[name]=name===delayed?()=>pending:async()=>null;
    const run=vm.runInNewContext(source+";refreshOverview()",context);
    for(let i=0;i<8;i++)await Promise.resolve();
    assert.equal(loading,false,delayed+" must not hold the project skeleton");
    assert.equal(rendered[0],state.overview,"render actual overview before auxiliary completion");
    release(null);await run;
  }
}
if (process.argv.includes("--source-only") || agentsSourceOnly) {
  console.log("SWARM console source UI contract passed");
  process.exit(0);
}

const { chromium } = require("playwright");

function response(body) {
  return { status: 200, contentType: "application/json", body: JSON.stringify(body) };
}

function applyConfigChanges(config, changes) {
  const next = structuredClone(config);
  for (const [key, value] of Object.entries(changes || {})) {
    const parts = key.split(".");
    let cursor = next.settings;
    parts.slice(0, -1).forEach((part) => { cursor = cursor[part] ||= {}; });
    cursor[parts.at(-1)] = value;
    const descriptor = Array.isArray(next.descriptors) ? next.descriptors.find((item) => item?.key === key) : null;
    if (descriptor) descriptor.current = value;
  }
  return next;
}

function configEditableText(config) {
  const lines = [];
  const sections = new Map();
  for (const key of config.editable || []) {
    const [section, name] = String(key).split(".");
    if (!section || !name) continue;
    const value = config.settings?.[section]?.[name];
    if (value === undefined) continue;
    if (!sections.has(section)) sections.set(section, []);
    const literal = typeof value === "string" ? JSON.stringify(value) : String(value);
    sections.get(section).push(`${name} = ${literal}`);
  }
  for (const [section, entries] of sections) {
    if (lines.length) lines.push("");
    lines.push(`[${section}]`, ...entries);
  }
  return `${lines.join("\n")}\n`;
}

function applyConfigText(config, text) {
  const changes = {};
  let section = "";
  for (const rawLine of String(text).split(/\r?\n/)) {
    const line = rawLine.trim();
    const sectionMatch = line.match(/^\[([A-Za-z0-9_-]+)\]$/);
    if (sectionMatch) {
      section = sectionMatch[1];
      continue;
    }
    const valueMatch = line.match(/^([A-Za-z0-9_-]+)\s*=\s*(.+)$/);
    if (!section || !valueMatch) continue;
    const literal = valueMatch[2].trim();
    let value;
    if (literal === "true" || literal === "false") value = literal === "true";
    else if (/^-?\d+(?:\.\d+)?$/.test(literal)) value = Number(literal);
    else {
      try { value = JSON.parse(literal); } catch { continue; }
    }
    changes[`${section}.${valueMatch[1]}`] = value;
  }
  const next = applyConfigChanges(config, changes);
  next.editable_text = String(text);
  return next;
}

function configRequestValue(payload, key) {
  const parsed = applyConfigText({ settings: {}, descriptors: [], editable: [] }, payload?.text || "");
  return key.split(".").reduce((value, part) => value?.[part], parsed.settings);
}

function assertConfigWriteEnvelope(payload, expected = {}) {
  assert.deepEqual(Object.keys(payload).sort(), ["acknowledge", "expected_revision", "operation_id", "scope", "text"]);
  assert.equal(payload.acknowledge, true);
  assert.equal(typeof payload.text, "string");
  assert.ok(payload.text.length > 0);
  assert.match(payload.operation_id, /^console-config-write-[a-f0-9]{32}$/);
  if (expected.scope) assert.deepEqual(payload.scope, expected.scope);
  if (expected.expectedRevision) assert.equal(payload.expected_revision, expected.expectedRevision);
  for (const [key, value] of Object.entries(expected.values || {})) assert.deepEqual(configRequestValue(payload, key), value);
}

function configDescriptorFixture(config = fixture.config) {
  const next = structuredClone(config);
  next.state = "KNOWN";
  next.scope = { type: "global" };
  next.revision = "global-revision-1";
  next.write_contract = { available: true };
  next.settings.monitoring ||= {};
  next.settings.monitoring.auto_health_enabled = false;
  next.editable = [...new Set([...(next.editable || []), "monitoring.auto_health_enabled", "execution.usage_saver"])];
  next.descriptors = [
    { key: "monitoring.auto_health_enabled", type: "boolean", classification: "exposed", value_state: "KNOWN", current: false, default: false, editable: true },
    { key: "execution.usage_saver", type: "boolean", classification: "exposed", value_state: "KNOWN", current: false, default: false, editable: true },
  ];
  next.editable_text = configEditableText(next);
  return next;
}

function projectViewFixture() {
  return {
    schema_version: 1,
    project_id: "project:fixture",
    tab: { id: "ui", label: "UI" },
    modes: [{ id: "screens", label: "Screens" }, { id: "map", label: "Map" }],
    screens: [
      {
        id: "overview/default", screen_id: "overview", state_id: "default", label: "Projects overview",
        status: "DESIGNED", devices: ["desktop", "tablet", "mobile"], alternative_count: 3,
        evidence: [
          { evidence_id: "fixture-image-1", digest: "1".padStart(64, "0"), media_type: "image/png", caption: "Overview desktop", device: "desktop", alternative_id: "overview-default" },
          { evidence_id: "fixture-image-2", digest: "2".padStart(64, "0"), media_type: "image/png", caption: "Overview tablet", device: "tablet", alternative_id: "overview-tablet" },
          { evidence_id: "fixture-image-3", digest: "3".padStart(64, "0"), media_type: "image/png", caption: "Overview mobile", device: "mobile", alternative_id: "overview-mobile" },
        ],
      },
      { id: "assets/empty", screen_id: "assets", state_id: "empty", label: "Assets empty", status: "MISSING_DESIGN", devices: [], alternative_count: 0, evidence: [] },
    ],
    map: {
      schema_version: 1,
      flowchart_id: "fixture-app-map",
      version: 1,
      nodes: [
        { id: "workspace", label: "Workspace", type: "group", visibility: "visible", order: 0 },
        { id: "overview", label: "Overview", type: "screen", visibility: "visible", group_id: "workspace", order: 0, screen_key: "overview/default" },
        { id: "assets", label: "Assets", type: "screen", visibility: "conditional", group_id: "workspace", order: 1, screen_key: "assets/empty" },
        { id: "runtime-state", label: "Runtime state", type: "runtime", visibility: "visible", order: 2 },
      ],
      edges: [{ id: "overview-assets", source: "overview", target: "assets", label: "Open assets" }],
    },
    requirements: {
      contract_id: "screen.groups.requirements.v1",
      version: "1.0.0",
      requirement_count: 31,
      counts_by_state: { KNOWN_SATISFIED: 8, PARTIAL: 8, MISSING: 7, UNKNOWN: 8 },
      groups: [
        {
          group_id: "group.overview", label: "Overview", node_ids: ["overview"],
          counts_by_state: { KNOWN_SATISFIED: 1, PARTIAL: 1, MISSING: 2, UNKNOWN: 1 },
        },
        {
          group_id: "group.assets", label: "Assets", node_ids: ["assets"],
          counts_by_state: { KNOWN_SATISFIED: 0, PARTIAL: 0, MISSING: 4, UNKNOWN: 1 },
        },
      ],
    },
    identity: {
      manifest_id: "fixture-views", manifest_version: 1, manifest_digest: "sha256:" + "a".repeat(64),
      view_id: "overview", view_digest: "sha256:" + "d".repeat(64),
      source_digests: ["sha256:" + "b".repeat(64), "sha256:" + "c".repeat(64)],
      observed_cursor: { stream_id: "project-ledger", project_id: "project:fixture", sequence: 42, event_id: "fixture-event-42", event_digest: "sha256:" + "e".repeat(64) },
    },
    claim_limit: "Project UI is a read-only digest-bound projection; actions and acceptance remain separate authority.",
  };
}

function projectModelViewFixture() {
  const overview = {
    id: "view.project.overview-health", label: "Overview", renderer: "document", mode: "blocks",
    content: { blocks: [
      { id: "overview.objective", kind: "objective", label: "Objective", text: "Make project truth easy to inspect." },
      { id: "risk-device", kind: "risk", label: "Device proof", text: "A qualified device capture is still required." },
      { id: "overview.proof-acceptance", kind: "proof_acceptance", label: "Proof and acceptance", text: "Source and browser proof remain separate." },
    ] },
  };
  const roadmap = {
    id: "view.project.roadmap", label: "Roadmap", renderer: "timeline", mode: "milestones",
    content: { milestones: [
      { id: "m-model", label: "Normalize the project model", order: 0, rank: 1, dependency_ids: [] },
      { id: "m-render", label: "Render accepted views", order: 1, rank: 2, dependency_ids: ["m-model"] },
    ] },
  };
  const flow = {
    id: "view.project.flow", label: "Flow", renderer: "canvas", mode: "network",
    content: {
      nodes: [
        { id: "m-route", kind: "milestone", label: "Routing proof", order: 0 },
        { id: "t-device", kind: "task", label: "Capture device proof", order: 1 },
        { id: "b-apk", kind: "block", label: "APK unavailable", order: 2 },
        { id: "a-source", kind: "artifact", label: "Normalizer source", order: 3 },
      ],
      edges: [
        { id: "contains", source: "m-route", target: "t-device", type: "contains" },
        { id: "blocked", source: "b-apk", target: "t-device", type: "blocks" },
        { id: "proof", source: "t-device", target: "a-source", type: "depends_on" },
      ],
    },
  };
  const work = {
    id: "view.project.work", label: "Work", renderer: "table", mode: "records",
    content: {
      blocks_state: "KNOWN", progress_state: "KNOWN",
      rows: [
        { id: "m-route", kind: "milestone", label: "Routing proof", depth: 0, parent_id: null, owner_id: "Release CTRL", progress_percent: null },
        { id: "t-device", kind: "task", label: "Capture device proof", depth: 1, parent_id: "m-route", owner_id: "Device reviewer", task_id: "nested-task", ctrl_id: "nested-ctrl", status: "active", progress_percent: 60 },
        { id: "b-apk", kind: "block", label: "Bind the qualified APK", depth: 2, parent_id: "t-device", owner_id: "Release owner", lifecycle_state: "blocked", progress_percent: null },
      ],
    },
  };
  const artifacts = {
    id: "view.project.artifacts", label: "Artifacts", renderer: "gallery", mode: "list",
    content: { artifacts: [
      { id: "a-source", label: "Normalizer source", revision: "3d23f5bd", proof_class: "SOURCE_STATIC", associated_ids: ["t-device"] },
      { id: "a-unbound", label: "Unbound note", revision: "1", proof_class: "UNKNOWN", associated_ids: [] },
    ] },
  };
  const agents = {
    id: "view.project.agents", label: "Agents", renderer: "table", mode: "records",
    content: { records: [
      { id: "release-ctrl", label: "Release CTRL", roles: ["active_ctrl"] },
      { id: "device-reviewer", label: "Device reviewer", roles: ["active_lead", "reviewer"] },
    ] },
  };
  return [overview, roadmap, work, flow, artifacts, agents];
}

function scopedFixture() {
  const overview = structuredClone(fixture.overview);
  overview.nodes.push(
    { id: "nested-ctrl", role: "ctrl", artifact: "Evidence review", project_id: "project:fixture", project: "swarm", status: "active", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["nested-ctrl"] },
    { id: "nested-task", role: "doer", role_label: "TASK", artifact: "Review screenshots", project_id: "project:fixture", project: "swarm", status: "active", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["nested-ctrl"] },
    { id: "malformed-task", role: "doer", role_label: "TASK", artifact: "Reconnect role manifest", project_id: "project:fixture", project: "swarm", status: "active", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["nested-ctrl"] },
    { id: "branch-ctrl", role: "ctrl", artifact: "Ship integrations", project_id: "project:branch", project: "Flowwweb", status: "active", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["branch-ctrl"] },
    { id: "branch-task", role: "doer", role_label: "TASK", artifact: "Confirm webhooks", project_id: "project:branch", project: "Flowwweb", status: "active", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["branch-ctrl"] },
    { id: "standalone-ctrl", role: "ctrl", artifact: "Resolve customer export", status: "active", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["standalone-ctrl"] },
    { id: "standalone-task", role: "doer", role_label: "TASK", artifact: "Inspect export evidence", status: "active", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["standalone-ctrl"] },
    { id: "arc-ctrl", role: "ctrl", artifact: "Review release notes", project_id: "project:arc", project: "Arc", status: "active", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["arc-ctrl"] },
    { id: "arc-task", role: "doer", role_label: "TASK", artifact: "Verify changelog", project_id: "project:arc", project: "Arc", status: "active", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["arc-ctrl"] },
    { id: "atlas-ctrl", role: "ctrl", artifact: "Prepare customer brief", project_id: "project:atlas", project: "Atlas", status: "active", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["atlas-ctrl"] },
    { id: "atlas-task", role: "doer", role_label: "TASK", artifact: "Summarize account status", project_id: "project:atlas", project: "Atlas", status: "active", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["atlas-ctrl"] },
    { id: "idle-ctrl", role: "ctrl", artifact: "Await customer decision", project_id: "project:idle", project: "Idle project", status: "idle", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["idle-ctrl"] },
    { id: "idle-task", role: "doer", role_label: "TASK", artifact: "Prepare decision options", project_id: "project:idle", project: "Idle project", status: "idle", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["idle-ctrl"] },
    { id: "stalled-ctrl", role: "ctrl", artifact: "Resolve dependency", project_id: "project:stalled", project: "Stalled project", status: "stalled", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["stalled-ctrl"] },
    { id: "stalled-task", role: "doer", role_label: "TASK", artifact: "Trace dependency", project_id: "project:stalled", project: "Stalled project", status: "stalled", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["stalled-ctrl"] },
    { id: "archived-ctrl", role: "ctrl", artifact: "Archived release", project_id: "project:archived", project: "Archived project", status: "quiet", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["archived-ctrl"] },
  );
  const projectedAgentIdentity = new Map([
    ["nested-ctrl", ["CTRL", "#FF6347"]], ["nested-task", ["Violet", "#EE82EE"]],
    ["branch-ctrl", ["Flowwweb CTRL", "#00FFFF"]], ["branch-task", ["Rose", "#FF69B4"]],
    ["arc-ctrl", ["Arc CTRL", "#FFD700"]], ["arc-task", ["Azure", "#00FFFF"]],
    ["atlas-ctrl", ["Atlas CTRL", "#EE82EE"]], ["atlas-task", ["Gold", "#FFD700"]],
  ]);
  overview.nodes.forEach((node) => {
    const identity = projectedAgentIdentity.get(node.id);
    if (identity) node.presentation = { display_name: identity[0], accent: identity[1] };
  });
  overview.projects.push({ id: "project:branch", name: "Flowwweb", nodes: 2, tokens: 0, active: 2 });
  overview.projects.push({ id: "project:arc", name: "Arc", nodes: 2, tokens: 0, active: 2 });
  overview.projects.push({ id: "project:atlas", name: "Atlas", nodes: 2, tokens: 0, active: 2 });
  overview.projects.push({ id: "project:idle", name: "Idle project", nodes: 2, tokens: 0, active: 0 });
  overview.projects.push({ id: "project:stalled", name: "Stalled project", nodes: 2, tokens: 0, active: 0 });
  overview.projects.push({ id: "project:archived", name: "Archived project", nodes: 1, tokens: 0, active: 0 });
  overview.projects.push({ id: "project:waiting", name: "Unassigned planning", nodes: 0, tokens: 0, active: 0 });
  overview.projects.push({ id: "project:browser", name: "https-mail-google-com-mail-u", nodes: 0, tokens: 0, active: 1 });
  overview.navigation.projects[0].ctrl_ids.push("nested-ctrl");
  overview.navigation.projects.push(
    { id: "project:branch", name: "Flowwweb", archived: false, visibility: "visible", project_eligibility: "swarm_ctrl", ctrl_ids: ["branch-ctrl"], active_ctrl_id: "branch-ctrl", active_ctrl: true },
    { id: "project:arc", name: "Arc", archived: false, visibility: "visible", project_eligibility: "swarm_ctrl", ctrl_ids: ["arc-ctrl"], active_ctrl_id: "arc-ctrl", active_ctrl: true },
    { id: "project:atlas", name: "Atlas", archived: false, visibility: "visible", project_eligibility: "swarm_ctrl", ctrl_ids: ["atlas-ctrl"], active_ctrl_id: "atlas-ctrl", active_ctrl: true },
    { id: "project:idle", name: "Idle project", archived: false, visibility: "visible", project_eligibility: "swarm_ctrl", ctrl_ids: ["idle-ctrl"], active_ctrl_id: null, active_ctrl: false },
    { id: "project:stalled", name: "Stalled project", archived: false, visibility: "visible", project_eligibility: "swarm_ctrl", ctrl_ids: ["stalled-ctrl"], active_ctrl_id: null, active_ctrl: false },
    { id: "project:waiting", name: "Unassigned planning", archived: false, visibility: "visible", project_eligibility: "no_ctrl", ctrl_ids: [], active_ctrl_id: null, active_ctrl: false }
  );
  const projectStatuses = new Map([
    ["project:fixture", "active"], ["project:branch", "active"], ["project:arc", "active"], ["project:atlas", "active"],
    ["project:stalled", "recently_active"], ["project:idle", "inactive"], ["project:waiting", "inactive"],
  ]);
  overview.navigation.project_inventory = { state: "KNOWN", available: true, source: "host_projects", claim_limit: "Fixture saved-project inventory" };
  overview.project_inventory = structuredClone(overview.navigation.project_inventory);
  overview.navigation.projects = overview.navigation.projects.map((project, position) => {
    const status = projectStatuses.get(project.id);
    return {
      ...project,
      ordering: { position, normalized_name: project.name.toLowerCase(), project_id: project.id },
      activity_status: status,
      activity_facts: { active_now: status === "active", recently_active: status === "recently_active", inactive: status === "inactive", unknown: status === "unknown", source: "fixture" },
      activity_source: "fixture",
      last_activity_at: 1788076800000,
      logo: project.id === "project:fixture" ? { status: "ADMITTED", artifact: { url: "/assets/project-fixture.svg", media_type: "image/svg+xml", digest: "f".repeat(64), alt: "" } } : null,
      task_count: overview.nodes.filter((node) => node.project_id === project.id).length,
    };
  });
  overview.navigation.controllers.push(
    { id: "nested-ctrl", project_id: "project:fixture", status: "active", archived: false, visibility: "visible" },
    { id: "branch-ctrl", project_id: "project:branch", status: "active", archived: false, visibility: "visible" },
    { id: "arc-ctrl", project_id: "project:arc", status: "active", archived: false, visibility: "visible" },
    { id: "atlas-ctrl", project_id: "project:atlas", status: "active", archived: false, visibility: "visible" },
    { id: "idle-ctrl", project_id: "project:idle", status: "idle", archived: false, visibility: "visible" },
    { id: "stalled-ctrl", project_id: "project:stalled", status: "stalled", archived: false, visibility: "visible" },
    { id: "archived-ctrl", project_id: "project:archived", status: "quiet", archived: true, visibility: "archived" }
  );
  for (const id of ["nested-ctrl", "branch-ctrl", "arc-ctrl", "atlas-ctrl", "idle-ctrl", "stalled-ctrl"]) {
    overview.progress.controllers[id] = { progress: null, freshness: { state: "unavailable", observed_at_ms: null } };
  }
  overview.project_view = projectViewFixture();
  overview.overview_metrics = structuredClone(overviewMetricFixture);
  overview.topology = {
    schema_version: 1,
    state: "KNOWN",
    nodes: overview.nodes.filter((node) => node.project_id && ["ctrl", "lead", "doer"].includes(String(node.role).toLowerCase())).map((node) => {
      const parentId = String(node.role).toLowerCase() === "ctrl" ? null : node.controller_ids?.[node.controller_ids.length - 1] || null;
      return {
        record_type: "AGENT",
        agent_id: node.id,
        project_id: node.project_id,
        parent_relation: parentId
          ? { state: "KNOWN", parent_agent_id: parentId, source: "host_thread_spawn_edges" }
          : { state: "ROOT", parent_agent_id: null, source: "host_thread_spawn_edges" },
      };
    }),
    tasks: [],
    agent_edges: [],
    task_edges: [],
    independent_nodes: [],
  };
  return overview;
}

function overflowingProjectFixture(count = 24) {
  const overview = scopedFixture();
  for (let index = 1; index <= count; index += 1) {
    const id = "project:overflow-" + String(index).padStart(2, "0");
    overview.navigation.projects.push({
      id,
      name: "Saved project " + String(index).padStart(2, "0"),
      archived: false,
      visibility: "visible",
      project_eligibility: "no_ctrl",
      ctrl_ids: [],
      active_ctrl_id: null,
      active_ctrl: false,
      ordering: { position: overview.navigation.projects.length, normalized_name: id, project_id: id },
      activity_status: "inactive",
      activity_facts: { active_now: false, recently_active: false, inactive: true, unknown: false, source: "fixture" },
      activity_source: "fixture",
      task_count: 0,
    });
  }
  return overview;
}

function assetFixtureItem(id, status = "READY", options = {}) {
  const revision = options.revision || 1;
  const projectId = options.projectId || "project:fixture";
  const ready = !["RESERVED", "QUEUED", "GENERATING", "VALIDATING"].includes(status);
  const digest = String(options.digest || id).padEnd(64, "0").slice(0, 64);
  return {
    asset_id: id,
    project_id: projectId,
    presentation: {
      display_name: options.name || id.replaceAll("-", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()),
      kind: options.kind || "illustration",
      description: options.description || "A retained project visual.",
      status,
      status_label: status.replaceAll("_", " ").toLowerCase().replace(/^./, (letter) => letter.toUpperCase()),
      created_at: "2026-08-28T10:00:00Z",
      updated_at: "2026-08-29T12:00:00Z",
    },
    technical: {
      advanced_debug: true,
      asset_id: id,
      logical_asset_id: options.logicalId || "logical:" + id,
      parent_revision_id: options.parentRevisionId || null,
      revision,
      status,
      created_at_ms: 1787892000000,
      updated_at_ms: 1787985600000,
      generation_job_id: options.generationJobId || null,
      operation_id: options.operationId || null,
      request_summary: options.requestSummary || null,
      job_metadata: { creator_label: options.creator || "SWARM" },
      provenance: { creator_label: options.creator || "SWARM", source_label: "Project asset" },
      digest,
      media_type: "image/png",
      size_bytes: options.sizeBytes || 184320,
      storage: { state: ready ? "ADMITTED" : "RESERVED", path: null, path_redacted: true },
      measured_progress: options.progress ?? null,
      measured_progress_provenance: options.measured ? "MEASURED" : "UNMEASURED",
      error_class: options.errorClass || null,
      retry_eligible: options.retryEligible === true,
      idempotency_key: options.idempotencyKey || null,
    },
    preview: ready && !["FAILED", "CANCELLED"].includes(status)
      ? { state: "AVAILABLE", url: "/api/assets/" + encodeURIComponent(id) + "/preview?digest=" + digest, media_type: "image/png", size_bytes: options.sizeBytes || 184320 }
      : { state: "NOT_READY", url: null, reason: "Preview is admitted only after validation." },
    trash: { trashed: status === "TRASHED", trashed_at: status === "TRASHED" ? "2026-08-29T13:00:00Z" : null, trashed_at_ms: status === "TRASHED" ? 1787989200000 : null, trashed_by: status === "TRASHED" ? "local-user" : null },
    retention_policy: "manual_unconfigured",
  };
}

function assetLibraryFixture() {
  const root = assetFixtureItem("asset-overview-r1", "READY", { name: "Overview direction", logicalId: "logical:overview", revision: 1 });
  const revision = assetFixtureItem("asset-overview-r2", "READY", { name: "Overview direction", logicalId: "logical:overview", revision: 2, parentRevisionId: root.asset_id });
  const developerAvatar = assetFixtureItem("role-avatar-developer", "READY", { name: "Developer role avatar", kind: "role_avatar", digest: String(8).padStart(64, "0") });
  return {
    active: [
      developerAvatar,
      revision,
      root,
      assetFixtureItem("asset-roadmap", "READY", { name: "Roadmap" }),
      assetFixtureItem("asset-generating", "GENERATING", { name: "Onboarding illustration", generationJobId: "generation:one", requestSummary: "Create the onboarding illustration", progress: 42, measured: true }),
      assetFixtureItem("asset-validating", "VALIDATING", { name: "Role catalog", generationJobId: "generation:two", requestSummary: "Validate the role catalog" }),
      assetFixtureItem("asset-failed", "FAILED", { name: "Settings option", generationJobId: "generation:failed", retryEligible: true, errorClass: "RENDER_FAILED" }),
      assetFixtureItem("asset-cancelled", "CANCELLED", { name: "Cancelled option", generationJobId: "generation:cancelled", retryEligible: true, errorClass: "CANCELLED" }),
    ],
    trash: [assetFixtureItem("asset-trashed", "TRASHED", { name: "Retired visual", revision: 3 })],
    sequence: 8,
  };
}

function imageProofFixture(count) {
  return {
    ok: true,
    items: Array.from({ length: count }, (_, index) => ({
      task_id: "ctrl",
      evidence_id: "fixture-image-" + String(index + 1),
      digest: String(index + 1).padStart(64, "0"),
      media_type: "image/png",
      caption: "Evidence image " + String(index + 1),
    })),
  };
}

function sameProjectCtrlProofFixture() {
  return {
    ok: true,
    sequence: 2,
    items: [
      { task_id: "ctrl", project_id: "project:fixture", evidence_id: "ctrl-image", digest: "a".repeat(64), media_type: "image/png", caption: "CTRL evidence" },
      { task_id: "nested-ctrl", project_id: "project:fixture", evidence_id: "nested-ctrl-image", digest: "b".repeat(64), media_type: "image/png", caption: "Other CTRL evidence" },
    ],
  };
}

function notificationFixture() {
  return {
    ok: true,
    schema_version: 1,
    ctrl_id: "ctrl",
    project_id: "project:fixture",
    unread: [{
      id: "a".repeat(64), kind: "REVIEW_REQUESTED", severity: "warning", requires_action: true,
      project_id: "project:fixture", ctrl_id: "ctrl", task_id: "ctrl", subject_id: "proof-1", owner_id: "CTRL",
      material_sequence: 3, observed_at_ms: 1712550180000, sentence: "Independent review is required for this artifact.",
      action_target: { view: "review", project_id: "project:fixture", ctrl_id: "ctrl", task_id: "ctrl", subject_id: "proof-1" },
    }],
    recent_seen: [],
  };
}

function runLogFixture() {
  const rows = [
    ["project:fixture", "nested-ctrl", "nested-task", "nested-task", "Developer", "DOER", "Designer started onboarding settings"],
    ["project:fixture", "nested-ctrl", "nested-task", "nested-task", "Developer", "DOER", "3 of 5 checks passed"],
    ["project:branch", "branch-ctrl", "branch-task", "branch-task", "Reviewer", "DOER", "Waiting for review"],
    ["project:arc", "arc-ctrl", "arc-task", "arc-task", "Writer", "DOER", "Release notes verified"],
    ["project:atlas", "atlas-ctrl", "atlas-task", "atlas-task", "Analyst", "DOER", "Account status synchronized"],
  ];
  return rows.map(([projectId, ctrlId, taskId, agentId, profession, structuralRole, summary], index) => ({
    event_id: "run-event-" + String(index + 1), event_digest: String(index + 41).padStart(64, "a"), event_seq: index + 1,
    observed_at_ms: 1788076800000 + index * 1000, kind: index % 2 ? "PROOF_ADMITTED" : "CURRENT_ACTION_CHANGED", status: "ACTIVE",
    project_id: projectId, ctrl_id: ctrlId, task_id: taskId, owner_id: agentId, agent_id: agentId,
    structural_role: structuralRole, profession, summary,
  }));
}

async function assertMetricDetailContainment(page) {
  assert.equal(await page.locator('#metric-detail-dialog').evaluate(dialog => {
    const box = dialog.getBoundingClientRect();
    const header = dialog.querySelector('.dialog-header').getBoundingClientRect();
    const range = dialog.querySelector('.usage-range');
    const bounds = range.getBoundingClientRect();
    const close = dialog.querySelector('[aria-label="Close metric details"]').getBoundingClientRect();
    const controlsOverlap = bounds.left < close.right && bounds.right > close.left && bounds.top < close.bottom && bounds.bottom > close.top;
    return getComputedStyle(range).position === 'static' && bounds.top >= header.top && bounds.bottom <= header.bottom
      && bounds.left >= box.left && bounds.right <= box.right
      && !controlsOverlap && box.left >= 8 && box.right <= innerWidth - 8
      && dialog.scrollWidth <= dialog.clientWidth
      && (innerWidth <= 600 || Math.abs(box.left + box.width / 2 - document.documentElement.clientWidth / 2) < 2)
      && box.height <= innerHeight - 16
      && close.left > header.left + header.width / 2
      && [...dialog.querySelectorAll('svg:empty')].every(svg => getComputedStyle(svg).display === 'none');
  }), true);
}

async function openPrimaryView(page, view) {
  await page.locator('.nav-item[data-view="' + view + '"]').click();
}

async function mount(page, overview, overrides = {}) {
  const testOrigin = overrides.testOrigin || "http://swarm.test";
  const runtimeErrors = [];
  const failedRequests = [];
  const requests = [];
  const notificationSeenRequests = [];
  const configRequests = [];
  const assetRequests = [];
  const messageRequests = [];
  const profileRequests = [];
  const projectRequests = [];
  const repairRequests = [];
  const proofFeed = overrides.proofFeed || fixture.proofFeed;
  const proofControl = overrides.proofControl || { fail: false, feed: proofFeed };
  const notificationControl = overrides.notificationControl || { failGet: false, failSeen: false, feed: structuredClone(overrides.notifications || notificationFixture()) };
  const configControl = overrides.configControl || { failPost: false, deferredPost: null, feed: configDescriptorFixture() };
  if (configControl.feed?.state !== "KNOWN" || !configControl.feed?.scope || configControl.feed?.revision == null || configControl.feed?.write_contract?.available !== true) {
    configControl.feed = configDescriptorFixture(configControl.feed);
  }
  if (typeof configControl.feed?.editable_text !== "string") configControl.feed.editable_text = configEditableText(configControl.feed);
  configControl.resetRequests ||= [];
  configControl.resetOperations ||= new Map();
  configControl.writeOperations ||= new Map();
  configControl.receipts ||= [];
  configControl.ctrlFeed ||= structuredClone(fixture.ctrlSettings);
  const assetControl = overrides.assetControl || { library: assetLibraryFixture(), failGet: false, failMutation: false, deferredGets: [], deferredMutations: [], operations: new Map() };
  const runLogControl = overrides.runLogControl || { items: runLogFixture(), failGet: false, deferredGets: [] };
  const messageControl = overrides.messageControl || null;
  const profileControl = overrides.profileControl || { feed: { ok: true, profile: { display_name: "Peik Gabriel", avatar: { url: null }, preferences: {} } } };
  const diagnosticsControl = overrides.diagnosticsControl || { feed: fixture.diagnostics, history: fixture.diagnosticHistory, repairResponses: [] };
  if (messageControl) {
    messageControl.endpoint ||= "/api/hq/actions";
    messageControl.timeoutMs ||= 100;
    messageControl.responses ||= [];
    messageControl.deferredResponses ||= [];
  }
  assetControl.operations ||= new Map();
  if (!overrides.preserveOnboardingPresentation) {
    await page.addInitScript(() => {
      if (sessionStorage.getItem("swarm-test-onboarding-initialized") === "1") return;
      localStorage.removeItem("swarm.onboarding.v2.seen");
      sessionStorage.setItem("swarm-test-onboarding-initialized", "1");
    });
  }
  page.on("console", (message) => { if (message.type() === "error") runtimeErrors.push(message.text()); });
  page.on("pageerror", (error) => runtimeErrors.push(error.message));
  page.on("requestfailed", (request) => failedRequests.push(request.url()));
  const routeConsoleRequest = async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    requests.push(url.pathname + url.search);
    if (url.pathname === "/") {
      const body = testOrigin === "http://swarm.test" ? documentHtml : documentHtml.replace('<base href="http://swarm.test/">', '<base href="' + testOrigin + '/">');
      return route.fulfill({ status: 200, contentType: "text/html", body });
    }
    if (url.pathname === "/styles.css") return route.fulfill({ status: 200, contentType: "text/css", body: css });
    if (url.pathname === "/app.js") return route.fulfill({ status: 200, contentType: "text/javascript", body: app });
    if (url.pathname === "/assets/swarm-offline-disconnected.webp") return route.fulfill({ status: 200, contentType: "image/webp", body: offlineWebpAsset });
    if (url.pathname === "/assets/swarm-state-mascot-concerned.webp") return route.fulfill({ status: 200, contentType: "image/webp", body: concernedWebpAsset });
    if (url.pathname === "/assets/support-caricature-light.webp") return route.fulfill({ status: 200, contentType: "image/webp", body: supportCaricatureAsset });
    if (url.pathname === "/assets/swarm-offline-disconnected.png") return route.fulfill({ status: 200, contentType: "image/png", body: offlineAsset });
    if (url.pathname === "/assets/swarm-state-mascot-concerned.png") return route.fulfill({ status: 200, contentType: "image/png", body: concernedAsset });
    if (overrides.connection?.offline && url.pathname.startsWith("/api/")) return route.abort();
    if (url.pathname === "/api/bootstrap") {
      const bootstrap = structuredClone(fixture.bootstrap);
      if (messageControl) bootstrap.capabilities = { ...(bootstrap.capabilities || {}), hq_connector: { contract: "swarm.universal_hq_connector.action.v1", method: "POST", endpoint: messageControl.endpoint, timeout_ms: messageControl.timeoutMs } };
      return route.fulfill(response(bootstrap));
    }
    if (url.pathname === "/api/overview") return route.fulfill(response(overview));
    if (url.pathname === "/api/tasks/approvals") return route.fulfill(response({ok:true,requests:[]}));
    if (url.pathname === "/api/assets" && request.method() === "GET") {
      const projection = url.searchParams.get("projection") === "trash" ? "trash" : "active";
      const projectId = url.searchParams.get("project_id") || "";
      const snapshot = structuredClone((assetControl.library?.[projection] || []).filter((item) => !projectId || item.project_id === projectId));
      const deferred = Array.isArray(assetControl.deferredGets) ? assetControl.deferredGets.shift() : null;
      if (deferred) await deferred;
      if (assetControl.failGet) return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ ok: false, error: "asset inventory unavailable" }) });
      return route.fulfill(response({ ok: true, status: "available", project_id: projectId || null, projection, items: snapshot, event_cursor: { sequence: assetControl.library?.sequence || 0, identity: "asset-cursor" }, event_count: snapshot.length, retention_policy: "manual_unconfigured" }));
    }
    if (url.pathname === "/api/assets/events" && request.method() === "GET") {
      const projectId = url.searchParams.get("project_id") || "";
      return route.fulfill(response({ ok: true, status: "available", project_id: projectId || null, after_sequence: Number(url.searchParams.get("after_sequence") || 0), cursor: { sequence: assetControl.library?.sequence || 0, identity: "asset-cursor" }, items: [], retention_policy: "manual_unconfigured" }));
    }
    if (/^\/api\/assets\/[^/]+\/preview$/.test(url.pathname) && request.method() === "GET") return route.fulfill({ status: 200, contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="200"><rect width="320" height="200" fill="#101d30"/><circle cx="160" cy="100" r="56" fill="#ff6948"/></svg>' });
    if (["/api/assets/trash", "/api/assets/restore", "/api/assets/generation/retry"].includes(url.pathname) && request.method() === "POST") {
      const payload = request.postDataJSON();
      assetRequests.push({ path: url.pathname, payload });
      if (assetControl.failMutation) return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ ok: false, error: "asset update unavailable" }) });
      if (assetControl.operations.has(payload.operation_id)) return route.fulfill(response(assetControl.operations.get(payload.operation_id)));
      const action = url.pathname.endsWith("/trash") ? "trash" : url.pathname.endsWith("/restore") ? "restore" : "retry";
      const sourceName = action === "restore" ? "trash" : "active";
      const source = assetControl.library?.[sourceName] || [];
      const index = source.findIndex((item) => item.asset_id === payload.asset_id && item.project_id === payload.project_id);
      if (index < 0 || Number(source[index].technical.revision) !== Number(payload.expected_revision)) return route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ ok: false, error: "asset revision conflict" }) });
      const item = structuredClone(source[index]);
      item.technical.revision += 1;
      item.technical.operation_id = payload.operation_id;
      item.technical.updated_at_ms += 1000;
      item.presentation.updated_at = "2026-08-29T12:00:01Z";
      if (action === "trash") {
        item.presentation.status = "TRASHED";
        item.presentation.status_label = "Trashed";
        item.technical.status = "TRASHED";
        item.trash = { trashed: true, trashed_at: "2026-08-29T13:00:00Z", trashed_at_ms: 1787989200000, trashed_by: "local-user" };
        source.splice(index, 1);
        assetControl.library.trash.unshift(item);
      } else if (action === "restore") {
        item.presentation.status = "READY";
        item.presentation.status_label = "Ready";
        item.technical.status = "READY";
        item.trash = { trashed: false, trashed_at: null, trashed_at_ms: null, trashed_by: null };
        item.preview = { state: "AVAILABLE", url: "/api/assets/" + encodeURIComponent(item.asset_id) + "/preview?digest=" + item.technical.digest, media_type: "image/png", size_bytes: item.technical.size_bytes };
        source.splice(index, 1);
        assetControl.library.active.unshift(item);
      } else {
        item.presentation.status = "QUEUED";
        item.presentation.status_label = "Queued";
        item.technical.status = "QUEUED";
        item.technical.generation_job_id = payload.generation_job_id;
        item.technical.retry_eligible = false;
        item.preview = { state: "NOT_READY", url: null, reason: "Preview is admitted only after validation." };
        source[index] = item;
      }
      assetControl.library.sequence += 1;
      const result = { ok: true, asset: item, mutation: { accepted: true, action, status: item.presentation.status.toLowerCase(), event_cursor: { sequence: assetControl.library.sequence, identity: "asset-cursor" }, retention_policy: "manual_unconfigured" } };
      assetControl.operations.set(payload.operation_id, result);
      const deferredMutation = Array.isArray(assetControl.deferredMutations) ? assetControl.deferredMutations.shift() : null;
      if (deferredMutation) await deferredMutation;
      return route.fulfill(response(result));
    }
    if (url.pathname === "/api/proof-feed") return proofControl.fail ? route.fulfill({ status: 200, contentType: "application/json", body: "{" }) : route.fulfill(response(proofControl.feed || proofFeed));
    if (url.pathname === "/api/usage-history") {
      const hours = url.searchParams.get("hours");
      if (!["1", "12", "24", "168", "720"].includes(hours)) return route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ ok: false, error: "unsupported usage window" }) });
      if (overrides.usageResponse) return route.fulfill(await overrides.usageResponse(url));
      return route.fulfill(response(overrides.usageByHours?.[hours] || fixture.usageHistory));
    }
    if (url.pathname === "/api/project-progress-feed") return route.fulfill(response(overrides.projectProgressFeed || fixture.projectProgressFeed));
    if (url.pathname === "/api/project-progress") return route.fulfill(response(overrides.projectProgress || { ok: true, project_id: url.searchParams.get("project_id"), scope_version: 1, status: "UNMEASURED", percent: null, blocks: [], cursor: { event_seq: 0 } }));
    if (url.pathname === "/api/role-manifests") return route.fulfill(response(overrides.roleManifests || roleManifestFixture()));
    if (url.pathname === "/api/run-log" && request.method() === "GET") {
      const projectId = url.searchParams.get("project_id") || "";
      const ctrlId = url.searchParams.get("ctrl_id") || "";
      const agentId = url.searchParams.get("agent_id") || "";
      const after = Number(url.searchParams.get("after_cursor") || 0);
      const snapshot = structuredClone(runLogControl.items.filter((item) => item.project_id === projectId && item.ctrl_id === ctrlId && (!agentId || item.agent_id === agentId) && item.event_seq > after));
      const deferred = Array.isArray(runLogControl.deferredGets) ? runLogControl.deferredGets.shift() : null;
      if (deferred) await deferred;
      if (runLogControl.failGet) return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ ok: false, error: "run log unavailable" }) });
      const cursor = Math.max(after, ...runLogControl.items.filter((item) => item.project_id === projectId && item.ctrl_id === ctrlId).map((item) => item.event_seq), 0);
      return route.fulfill(response({ ok: true, scope: { project_id: projectId, ctrl_id: ctrlId, agent_id: agentId }, items: snapshot, cursor: { next_event_seq: cursor }, retention: { page_truncated: false, source_scan_truncated: false, stale_cursor: false } }));
    }
    if (url.pathname === "/api/notifications" && request.method() === "GET") return notificationControl.failGet ? route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ ok: false, error: "notification feed unavailable" }) }) : route.fulfill(response(notificationControl.feed));
    if (url.pathname === "/api/notifications/seen" && request.method() === "POST") {
      const payload = request.postDataJSON();
      notificationSeenRequests.push(payload);
      if (notificationControl.failSeen) return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ ok: false, error: "notification acknowledgement unavailable" }) });
      const acknowledged = new Set(payload.notification_ids || []);
      const newlySeen = notificationControl.feed.unread.filter((item) => acknowledged.has(item.id)).map((item) => ({ ...item, seen_at_ms: Date.now() }));
      notificationControl.feed.unread = notificationControl.feed.unread.filter((item) => !acknowledged.has(item.id));
      notificationControl.feed.recent_seen = [...newlySeen, ...notificationControl.feed.recent_seen];
      return route.fulfill(response({ ok: true, acknowledged: acknowledged.size, newly_seen: newlySeen.length, pruned: 0, feed: notificationControl.feed }));
    }
    if (url.pathname === "/api/presence") return route.fulfill(response({ ok: true, proof_sequence: proofFeed.sequence || 0 }));
    if (["/api/settings/restore", "/api/config/reset", "/api/ctrl-settings/reset"].includes(url.pathname) && request.method() === "POST") {
      const payload = request.postDataJSON();
      configControl.resetRequests.push({ path: url.pathname, payload });
      const deferredReset = Array.isArray(configControl.deferredResets) ? configControl.deferredResets.shift() : configControl.deferredReset;
      if (deferredReset) await deferredReset;
      if (configControl.failReset === "connection") return route.abort();
      if (configControl.failReset === "conflict") return route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ ok: false, error: "config revision conflict" }) });
      if (configControl.resetOperations.has(payload.operation_id)) return route.fulfill(response(configControl.resetOperations.get(payload.operation_id)));
      let result;
      if (url.pathname === "/api/ctrl-settings/reset") {
        configControl.ctrlFeed = { ...configControl.ctrlFeed, revision: Number(configControl.ctrlFeed.revision || 0) + 1, customized: false, override: {}, mutation_receipt: { acknowledged: true, operation_id: payload.operation_id } };
        result = structuredClone(configControl.ctrlFeed);
      } else {
        const revision = String(configControl.feed.revision) + "-reset";
        configControl.feed = { ...configControl.feed, revision, mutation_receipt: { accepted: true, action: payload.scope.type + "_config_reset", scope: structuredClone(payload.scope), expected_revision: payload.expected_revision, new_revision: revision, replayed: false, acknowledged: true, operation_id: payload.operation_id } };
        result = structuredClone(configControl.feed);
      }
      configControl.resetOperations.set(payload.operation_id, result);
      return route.fulfill(response(result));
    }
    if (url.pathname === "/api/config") {
      if (request.method() === "GET") {
        const snapshot = structuredClone(configControl.feed);
        if (Array.isArray(configControl.getSnapshots)) configControl.getSnapshots.push(snapshot);
        const deferredGet = Array.isArray(configControl.deferredGets) ? configControl.deferredGets.shift() : configControl.deferredGet;
        if (deferredGet) await deferredGet;
        if (configControl.failGet) return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ ok: false, error: "settings readback unavailable" }) });
        return route.fulfill(response(snapshot));
      }
      const payload = request.postDataJSON();
      configRequests.push(payload);
      const deferredPost = Array.isArray(configControl.deferredPosts) ? configControl.deferredPosts.shift() : configControl.deferredPost;
      if (deferredPost) await deferredPost;
      assert.deepEqual(Object.keys(payload).sort(), ["acknowledge", "expected_revision", "operation_id", "scope", "text"]);
      assert.equal(payload.acknowledge, true);
      const replay = configControl.writeOperations.get(payload.operation_id);
      if (replay) {
        const replayResult = { ...structuredClone(replay), mutation_receipt: { ...replay.mutation_receipt, replayed: true } };
        configControl.receipts.push(structuredClone(replayResult.mutation_receipt));
        return route.fulfill(response(replayResult));
      }
      if (configControl.failPost === "connection") return route.abort();
      if (configControl.failPost === "conflict") return route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ ok: false, error: "settings revision conflict" }) });
      if (configControl.failPost) return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ ok: false, error: "setting acknowledgement unavailable" }) });
      assert.deepEqual(payload.scope, configControl.feed.scope);
      assert.equal(payload.expected_revision, configControl.feed.revision);
      const priorRevision = configControl.feed.revision;
      configControl.feed = applyConfigText(configControl.feed, payload.text);
      configControl.feed.revision = `${priorRevision}-write-${configControl.writeOperations.size + 1}`;
      configControl.feed.mutation_receipt = {
        accepted: true,
        acknowledged: true,
        action: "config_update",
        operation_id: payload.operation_id,
        replayed: false,
        scope: structuredClone(payload.scope),
        expected_revision: payload.expected_revision,
        new_revision: configControl.feed.revision,
        changed_paths: [],
      };
      configControl.writeOperations.set(payload.operation_id, structuredClone(configControl.feed));
      if (configControl.ambiguousAfterApply) {
        configControl.ambiguousAfterApply = false;
        if (configControl.restartAfterAmbiguous) {
          configControl.writeOperations = new Map([...configControl.writeOperations].map(([key, value]) => [key, structuredClone(value)]));
          configControl.restartCount = Number(configControl.restartCount || 0) + 1;
        }
        return route.abort();
      }
      const responseMutation = Array.isArray(configControl.responseMutations) ? configControl.responseMutations.shift() : null;
      const result = responseMutation ? responseMutation(structuredClone(configControl.feed), payload) : configControl.feed;
      configControl.receipts.push(structuredClone(result.mutation_receipt));
      return route.fulfill(response(result));
    }
    if (messageControl && url.pathname === messageControl.endpoint && request.method() === "POST") {
      const payload = request.postDataJSON();
      messageRequests.push(structuredClone(payload));
      const deferred = messageControl.deferredResponses.shift();
      if (deferred) await deferred;
      const outcome = messageControl.responses.shift() || { result_code: "ACKNOWLEDGED" };
      if (outcome.type === "abort") return route.abort();
      if (outcome.type === "timeout") {
        await new Promise((resolve) => setTimeout(resolve, messageControl.timeoutMs + 80));
      }
      if (outcome.status && outcome.status >= 400) return route.fulfill({ status: outcome.status, contentType: "application/json", body: JSON.stringify({ ok: false, error: outcome.error || "message action failed" }) });
      const alternateDigest = payload.action_digest === "sha256:" + "0".repeat(64) ? "sha256:" + "1".repeat(64) : "sha256:" + "0".repeat(64);
      const body = outcome.body || {
        ok: true,
        result_code: outcome.result_code || "ACKNOWLEDGED",
        request_id: payload.request_id,
        action_digest: outcome.action_digest === "different" ? alternateDigest : (outcome.action_digest || payload.action_digest),
        result_event_id: outcome.result_event_id === null ? null : (outcome.result_event_id || "message-result-event"),
        result_event_digest: outcome.result_event_digest === null ? null : (outcome.result_event_digest || "sha256:" + "9".repeat(64)),
      };
      return route.fulfill(response(body));
    }
    if (url.pathname === "/api/projects" && request.method() === "POST") {
      const payload = request.postDataJSON();
      projectRequests.push(payload);
      return route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ ok: false, error: "project creation is unavailable until Codex provides a host-owned capability; create the project in Codex, then refresh SWARM HQ" }) });
    }
    if (profileControl && url.pathname === "/api/profile") {
      profileRequests.push({ method: request.method(), body: request.postData() });
      if (profileControl.unavailable) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ ok: false, error: "profile authority unavailable" }) });
      return route.fulfill(response(profileControl.feed));
    }
    if (url.pathname === "/api/diagnostics") {
      diagnosticsControl.getCount = Number(diagnosticsControl.getCount || 0) + 1;
      return route.fulfill(response(diagnosticsControl.feed));
    }
    if (url.pathname === "/api/diagnostics/history") return route.fulfill(response(diagnosticsControl.history));
    if (url.pathname === "/api/health/repair" && request.method() === "POST") {
      const payload = request.postDataJSON();
      repairRequests.push(payload);
      const result = diagnosticsControl.repairResponses.shift() || { ok: true, repair_policy: { dispatch: "disabled", claim_limit: "Preview only." }, selected_check_ids: payload.check_ids };
      if (result.status && result.status >= 400) return route.fulfill({ status: result.status, contentType: "application/json", body: JSON.stringify({ ok: false, error: result.error || "repair preview unavailable" }) });
      return route.fulfill(response(result));
    }
    if (url.pathname === "/api/health/settings") return route.fulfill(response(fixture.healthSettings));
    if (url.pathname === "/api/storage") return route.fulfill(response(fixture.storage));
    if (url.pathname === "/api/ctrl-settings") return route.fulfill(response(configControl.ctrlFeed));
    if (url.pathname === "/api/skills") return route.fulfill(response({ ok: true, settings: { inheritance_enabled: true }, skills: [], overlays: { global: null, project: null, ctrl: null } }));
    if (url.pathname === "/api/labs") return route.fulfill(response({ ok: true, labs: labCatalogFixture.labs, manifest_contract: labCatalogFixture.manifest_contract }));
    if (url.pathname.startsWith("/api/proof-media/")) return route.fulfill({ status: 200, contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="100"><rect width="160" height="100" fill="#0f1726"/></svg>' });
    if (/^\/api\/assets\/[a-z0-9_-]+\/preview$/i.test(url.pathname)) return route.fulfill({ status: 200, contentType: "image/png", body: mascotAsset });
    if (url.pathname === "/assets/swarm-wordmark.png") return route.fulfill({ status: 200, contentType: "image/png", body: wordmarkAsset });
    if (url.pathname === "/assets/project-fixture.svg") return route.fulfill({ status: 200, contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48"><rect width="48" height="48" rx="10" fill="#ff6948"/></svg>' });
    if (url.pathname === "/assets/swarm-mascot-512.png") return route.fulfill({ status: 200, contentType: "image/png", body: mascotAsset });
    if (url.pathname === "/assets/swarm-guided-tour-slide1.png") return route.fulfill({ status: 200, contentType: "image/png", body: onboardingSlide1Asset });
    if (url.pathname === "/assets/swarm-guided-tour-role-group.png") return route.fulfill({ status: 200, contentType: "image/png", body: onboardingRoleGroupAsset });
    if (url.pathname === "/assets/swarm-guided-tour-project-tool.png") return route.fulfill({ status: 200, contentType: "image/png", body: onboardingProjectToolAsset });
    if (url.pathname.startsWith("/assets/role-avatars/")) {
      const roleId = path.basename(url.pathname, ".png");
      return roleAvatarFixtures.has(roleId)
        ? route.fulfill({ status: 200, contentType: "image/png", body: roleAvatarFixtures.get(roleId) })
        : route.fulfill({ status: 404, contentType: "text/plain", body: "Avatar unavailable" });
    }
    if (url.pathname === "/swarm-icon-64.png") return route.fulfill({ status: 200, contentType: "image/png", body: iconAsset });
    return route.abort();
  };
  await page.route(testOrigin + "/**", routeConsoleRequest);
  if (testOrigin !== "http://swarm.test") await page.route("http://swarm.test/**", routeConsoleRequest);
  await page.goto(overrides.initialURL || testOrigin + "/", { waitUntil: "domcontentloaded" });
  if (overrides.waitForConnectionState) {
    await page.locator("#connection-state").waitFor({ state: "visible" });
    return { runtimeErrors, failedRequests, requests, notificationSeenRequests, configRequests, assetRequests, messageRequests, profileRequests, projectRequests, repairRequests, assetControl, configControl, runLogControl, messageControl, profileControl, diagnosticsControl };
  }
  try {
    const initialView = new URL(overrides.initialURL || testOrigin + "/").hash.replace(/^#/, "") || "overview";
    if (initialView === "overview") await page.locator("#overview-content").waitFor({ state: "visible" });
    else await page.waitForFunction((view) => Boolean(state.overview) && !document.querySelector('[data-view-panel="' + view + '"]')?.hidden, initialView);
  } catch (error) {
    const message = await page.locator("#error-message").textContent().catch(() => "");
    throw new Error(`${error.message}; console=${runtimeErrors.join(" | ")}; surface=${message}`);
  }
  await page.locator("#onboarding-dialog").waitFor({ state: "visible" });
  if (!overrides.keepOnboarding) await page.getByRole("button", { name: "Skip for now" }).click();
  return { runtimeErrors, failedRequests, requests, notificationSeenRequests, configRequests, assetRequests, messageRequests, profileRequests, projectRequests, repairRequests, assetControl, configControl, runLogControl, messageControl, profileControl, diagnosticsControl };
}

async function assertOnboardingRoleGroup(page, viewportWidth) {
  const group = page.locator("#onboarding-panel-3 .onboarding-role-group");
  await group.waitFor({ state: "visible" });
  assert.equal(await page.locator("#onboarding-panel-3 #onboarding-role-assets-blocker").count(), 0);
  assert.equal(await group.getAttribute("src"), "/assets/swarm-guided-tour-role-group.png");
  const geometry = await group.evaluate((node) => {
    const rect = node.getBoundingClientRect();
    const panel = node.closest(".onboarding-panel").getBoundingClientRect();
    return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom, panelLeft: panel.left, panelRight: panel.right, documentWidth: document.documentElement.scrollWidth };
  });
  assert.ok(geometry.left >= geometry.panelLeft - 1 && geometry.right <= geometry.panelRight + 1);
  assert.ok(geometry.documentWidth <= viewportWidth);
}

async function assertOnboardingCoordination(page, viewportWidth) {
  const flow = page.locator("#onboarding-panel-2 .onboarding-flow-scene");
  await flow.waitFor({ state: "visible" });
  assert.equal(await flow.locator(".is-prompt").textContent(), "Prompt");
  assert.equal(await flow.locator(".is-ctrl").textContent(), "CTRL");
  assert.deepEqual(await flow.locator(".onboarding-flow-roles b").allTextContents(), ["Designer", "Developer", "Reviewer"]);
  assert.equal(await page.locator("#onboarding-dialog [role=tree], #onboarding-dialog [data-onboarding-edge]").count(), 0);
  const geometry = await flow.evaluate((node) => ({ rect: node.getBoundingClientRect().toJSON(), documentWidth: document.documentElement.scrollWidth }));
  assert.ok(geometry.rect.width > 0 && geometry.rect.height > 0, JSON.stringify(geometry));
  assert.ok(geometry.documentWidth <= viewportWidth);
}

async function assertDialogFrame(page, selector) {
  const result = await page.locator(selector).evaluate(async (dialog) => {
    const shell = dialog.querySelector(":scope > .dialog-shell");
    const header = shell?.querySelector(":scope > .dialog-header");
    const body = shell?.querySelector(":scope > .dialog-body");
    const content = body?.querySelector(":scope > .dialog-body-content");
    const footer = shell?.querySelector(":scope > .dialog-footer");
    if (!shell || !header || !body || !content || !footer) return { missing: true };
    const box = (element) => {
      const value = element.getBoundingClientRect();
      return { left: value.left, top: value.top, right: value.right, bottom: value.bottom, width: value.width, height: value.height };
    };
    const originalMinHeight = content.style.minHeight;
    content.style.minHeight = Math.max(content.scrollHeight, body.clientHeight + 320) + "px";
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const before = { header: box(header), footer: box(footer), body: box(body), shell: box(shell) };
    body.scrollTop = body.scrollHeight;
    await new Promise((resolve) => requestAnimationFrame(resolve));
    const after = { header: box(header), footer: box(footer), body: box(body) };
    const verticalOwners = [...shell.querySelectorAll("*")].filter((element) => {
      if (element.matches("textarea,input,select")) return false;
      return ["auto", "scroll"].includes(getComputedStyle(element).overflowY);
    }).map((element) => element.className || element.id || element.tagName);
    const visibleButtons = [...footer.querySelectorAll("button")].filter((button) => !button.hidden && getComputedStyle(button).display !== "none");
    const computedBody = getComputedStyle(body);
    const result = {
      missing: false,
      before,
      after,
      verticalOwners,
      bodyScrolls: body.scrollHeight > body.clientHeight && body.scrollTop > 0,
      bodyPadding: [computedBody.paddingLeft, computedBody.paddingRight],
      footerVisible: before.footer.top >= before.shell.top && before.footer.bottom <= before.shell.bottom + 1,
      footerTargets: visibleButtons.map((button) => box(button)),
      dialogOverflowX: dialog.scrollWidth - dialog.clientWidth,
      shellOverflowX: shell.scrollWidth - shell.clientWidth,
      documentOverflowX: document.documentElement.scrollWidth - innerWidth,
    };
    content.style.minHeight = originalMinHeight;
    body.scrollTop = 0;
    return result;
  });
  assert.equal(result.missing, false);
  assert.equal(result.verticalOwners.length, 1, `${selector} must have one vertical layout scroll owner`);
  assert.match(String(result.verticalOwners[0]), /\bdialog-body\b/);
  assert.equal(result.bodyScrolls, true);
  assert.deepEqual(result.bodyPadding, ["0px", "0px"]);
  assert.ok(Math.abs(result.before.body.left - result.before.shell.left) <= 1);
  assert.ok(Math.abs(result.before.body.right - result.before.shell.right) <= 1);
  assert.ok(Math.abs(result.before.header.top - result.after.header.top) <= 1);
  assert.ok(Math.abs(result.before.header.bottom - result.after.header.bottom) <= 1);
  assert.ok(Math.abs(result.before.footer.top - result.after.footer.top) <= 1);
  assert.ok(Math.abs(result.before.footer.bottom - result.after.footer.bottom) <= 1);
  assert.equal(result.footerVisible, true);
  assert.ok(result.footerTargets.every((target) => target.width >= 44 && target.height >= 44), JSON.stringify({ selector, targets: result.footerTargets }));
  assert.ok(result.dialogOverflowX <= 1);
  assert.ok(result.shellOverflowX <= 1);
  assert.ok(result.documentOverflowX <= 1);
}

async function assertCircleFrame(page, selector, minimum = 40) {
  const result = await page.locator(selector).evaluate((element) => {
    const box = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return { width: box.width, height: box.height, aspectRatio: style.aspectRatio, borderRadius: style.borderRadius, flex: style.flex, overflow: style.overflow };
  });
  assert.ok(result.width >= minimum && result.height >= minimum, JSON.stringify({ selector, result }));
  assert.ok(Math.abs(result.width - result.height) <= 0.5, JSON.stringify({ selector, result }));
  assert.equal(result.aspectRatio, "1 / 1");
  assert.match(result.borderRadius, /50%/);
  assert.match(result.flex, /0 0/);
  assert.equal(result.overflow, "visible");
}

async function assertSharedCircleGeometry(page, selectors) {
  for (const selector of selectors) {
    const result = await page.locator(selector).evaluateAll((elements) => {
      const values = elements.map((element) => {
        const box = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return { width: box.width, height: box.height, aspectRatio: style.aspectRatio, borderRadius: style.borderRadius, flexShrink: style.flexShrink };
      });
      return values.find((value) => value.width > 0 && value.height > 0) || values[0];
    });
    assert.ok(result.width > 0 && Math.abs(result.width - result.height) <= 0.5, JSON.stringify({ selector, result }));
    assert.equal(result.aspectRatio, "1 / 1");
    assert.ok(result.borderRadius.includes("50%") || Math.abs(Number.parseFloat(result.borderRadius) - result.width / 2) <= 0.5, JSON.stringify({ selector, result }));
    assert.equal(result.flexShrink, "0");
  }
}

async function chooseProjectScope(page, projectId) {
  await page.locator("#project-scope-filter").click();
  await page.locator('[data-project-scope-id="' + projectId + '"]').click();
}

async function assertLaterStepNavigation(page, expectedPrimary) {
  const result = await page.locator("#onboarding-dialog").evaluate((dialog) => {
    const rect = (element) => {
      const value = element.getBoundingClientRect();
      return { left: value.left, top: value.top, right: value.right, bottom: value.bottom, width: value.width, height: value.height };
    };
    const body = dialog.querySelector(".dialog-body");
    const back = dialog.querySelector("#onboarding-back");
    const icon = back.querySelector(".lucide");
    const backRect = rect(back);
    const iconRect = rect(icon);
    const hit = document.elementFromPoint(backRect.left + backRect.width / 2, backRect.top + backRect.height / 2);
    const footerButtons = [...dialog.querySelectorAll(".dialog-footer button")]
      .filter((button) => !button.hidden && getComputedStyle(button).display !== "none")
      .map((button) => ({ id: button.id, text: button.textContent.trim() }));
    return {
      body: rect(body),
      back: backRect,
      icon: iconRect,
      backVisible: !back.hidden && getComputedStyle(back).display !== "none" && getComputedStyle(back).visibility !== "hidden",
      backUnobscured: hit === back || Boolean(hit && back.contains(hit)),
      footerButtons,
      skipHidden: dialog.querySelector("#onboarding-skip").hidden,
      bodyOverflowY: getComputedStyle(body).overflowY,
      documentOverflowX: document.documentElement.scrollWidth - innerWidth,
    };
  });
  assert.equal(result.backVisible, true);
  assert.ok(result.back.width >= 44 && result.back.height >= 44, JSON.stringify(result));
  assert.ok(Math.abs(result.back.left + result.back.width / 2 - (result.icon.left + result.icon.width / 2)) <= 1);
  assert.ok(Math.abs(result.back.top + result.back.height / 2 - (result.icon.top + result.icon.height / 2)) <= 1);
  assert.ok(result.back.top >= result.body.top && result.back.top <= result.body.top + 12, JSON.stringify(result));
  assert.equal(result.backUnobscured, true);
  assert.deepEqual(result.footerButtons, [{ id: "onboarding-primary", text: expectedPrimary }]);
  assert.equal(result.skipHidden, true);
  assert.equal(result.bodyOverflowY, "auto");
  assert.ok(result.documentOverflowX <= 1);
  return result;
}

const browserCandidates = [
  process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean);
const executablePath = browserCandidates.find((candidate) => fs.existsSync(candidate));
const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
const evidenceDir = process.env.SWARM_UI_EVIDENCE_DIR || "";
if (evidenceDir) fs.mkdirSync(evidenceDir, { recursive: true });
async function settleOnboardingImage(image) {
  await image.waitFor({ state: "visible" });
  await image.evaluate(async (node) => {
    if (!node.complete) {
      await new Promise((resolve, reject) => {
        node.addEventListener("load", resolve, { once: true });
        node.addEventListener("error", () => reject(new Error(`Failed to load ${node.currentSrc || node.src}`)), { once: true });
      });
    }
    await node.decode();
    await Promise.all(node.getAnimations().map((animation) => animation.finished.catch(() => undefined)));
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  });
}

async function settleCurrentOnboardingImages(page) {
  const images = page.locator(".onboarding-panel.is-active img");
  for (let index = 0; index < await images.count(); index += 1) await settleOnboardingImage(images.nth(index));
}

async function assertDecodedVisibleOnboardingImage(page, selector, expectedWidth, expectedHeight) {
  const image = page.locator(selector);
  await settleOnboardingImage(image);
  const proof = await image.evaluate((node, expected) => {
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    const hit = document.elementFromPoint(centerX, centerY);
    const canvas = document.createElement("canvas");
    canvas.width = 96;
    canvas.height = 96;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    context.drawImage(node, 0, 0, canvas.width, canvas.height);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let paintedPixels = 0;
    let chromaticPixels = 0;
    for (let index = 0; index < pixels.length; index += 4) {
      const red = pixels[index];
      const green = pixels[index + 1];
      const blue = pixels[index + 2];
      const alpha = pixels[index + 3];
      if (alpha > 8) paintedPixels += 1;
      if (alpha > 8 && Math.max(red, green, blue) - Math.min(red, green, blue) > 24) chromaticPixels += 1;
    }
    return {
      complete: node.complete,
      naturalWidth: node.naturalWidth,
      naturalHeight: node.naturalHeight,
      rect: { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom, width: rect.width, height: rect.height },
      display: style.display,
      visibility: style.visibility,
      opacity: Number(style.opacity),
      inViewport: rect.right > 0 && rect.bottom > 0 && rect.left < innerWidth && rect.top < innerHeight,
      centerNotOccluded: hit === node || Boolean(hit && node.contains(hit)),
      paintedPixels,
      chromaticPixels,
      expected,
    };
  }, { width: expectedWidth, height: expectedHeight });
  assert.equal(proof.complete, true);
  assert.equal(proof.naturalWidth, expectedWidth);
  assert.equal(proof.naturalHeight, expectedHeight);
  assert.ok(proof.rect.width >= 180 && proof.rect.height >= 100, JSON.stringify(proof));
  assert.notEqual(proof.display, "none");
  assert.notEqual(proof.visibility, "hidden");
  assert.ok(proof.opacity >= 0.99, JSON.stringify(proof));
  assert.equal(proof.inViewport, true);
  assert.equal(proof.centerNotOccluded, true);
  assert.ok(proof.paintedPixels >= 120 && proof.chromaticPixels >= 40, JSON.stringify(proof));
  const clippedScreenshot = await image.screenshot({ animations: "disabled" });
  assert.ok(clippedScreenshot.byteLength >= 4000, `Expected pixel-bearing screenshot region for ${selector}`);
  return proof;
}

async function captureOnboardingEvidence(page, name) {
  if (!evidenceDir) return;
  await settleCurrentOnboardingImages(page);
  const chrome = await page.locator("#onboarding-dialog").evaluate(async (dialog) => {
    await Promise.all(dialog.getAnimations({ subtree: true }).map((animation) => animation.finished.catch(() => undefined)));
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const visibleRect = (selector) => {
      const node = dialog.querySelector(selector);
      const rect = node.getBoundingClientRect();
      const style = getComputedStyle(node);
      const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
      return { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom, width: rect.width, height: rect.height, display: style.display, visibility: style.visibility, opacity: Number(style.opacity), unobscured: hit === node || Boolean(hit && node.contains(hit)), hit: hit?.id || hit?.className || hit?.tagName || "none" };
    };
    return {
      header: visibleRect(":scope > .dialog-shell > .dialog-header"),
      footer: visibleRect(":scope > .dialog-shell > .dialog-footer"),
      wordmark: visibleRect(".onboarding-header > .brand-lockup img"),
    };
  });
  for (const [part, proof] of Object.entries(chrome)) {
    assert.ok(proof.width > 0 && proof.height > 0, `${name}: ${part} must have visible geometry`);
    assert.notEqual(proof.display, "none", `${name}: ${part} must render`);
    assert.notEqual(proof.visibility, "hidden", `${name}: ${part} must remain visible`);
    assert.ok(proof.opacity >= 0.99, `${name}: ${part} must be fully visible`);
    assert.ok(proof.left >= 0 && proof.top >= 0 && proof.right <= page.viewportSize().width && proof.bottom <= page.viewportSize().height, `${name}: ${part} left the viewport: ${JSON.stringify(proof)}`);
    assert.equal(proof.unobscured, true, `${name}: ${part} is obscured by ${proof.hit}`);
  }
  await page.screenshot({ path: path.join(evidenceDir, name + ".png"), fullPage: false, animations: "disabled" });
}
async function assertHostWorkPage() {
  for (const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
    const page = await browser.newPage({viewport});
    const overview = scopedFixture();
    overview.nodes = ["active", "in_progress", "blocked", "done", "waiting"].map((status, index) => ({id:"host-" + index,title:"Observed host task " + index,project_id:"project:fixture",status}));
    const cursor = {event_seq:0,event_id:"",event_digest:""};
    const projectProgress = {ok:true,status:"UNMEASURED",project_id:"project:fixture",cursor,blocks:[],progress_queue:{
      ...progressQueueFixture,project_id:"project:fixture",accepted_cursor:cursor,
      scope_binding:{project_id:"project:fixture",ctrl_ids:[],cursor},
      segments:progressQueueFixture.segments.map((segment) => ({...segment,rows:[]})),
    }};
    const runtime = await mount(page, overview, {projectProgress});
    await page.evaluate(() => selectProjectScope("project:fixture"));
    const section = page.getByRole("region", {name:"Host work"});
    await section.scrollIntoViewIfNeeded();
    assert.equal(await section.locator("[data-host-work-id]").count(), 5);
    assert.match(await section.textContent(), /2 reported active · 5 observed/);
    assert.equal(await section.getByRole("progressbar").count(), 0);
    assert.match(await page.locator("#project-tab-panel").textContent(), /No recorded active work[\s\S]*No recorded queued work/);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
    if (evidenceDir) await page.screenshot({path:path.join(evidenceDir,"host-work-"+viewport.width+".png"),animations:"disabled"});
    await page.evaluate(() => {state.projectProgressStatus="stale";renderProjectDetail();});
    assert.equal(await section.locator("[data-host-work-id]").count(), 5);
    assert.deepEqual(runtime.runtimeErrors, []);
    assert.deepEqual(runtime.failedRequests, []);
    for (const caller of ["refreshMonitoring", "refreshOverview"]) {
      assert.equal(await section.locator("[data-host-work-id]").count(), 5);
      await page.route("**/api/overview*", (route) => route.abort("failed"));
      await page.evaluate(async (name) => { if (name === "refreshMonitoring") await refreshMonitoring(state.proofSequence); else await refreshOverview(false); }, caller);
      assert.equal(await page.locator("[data-host-work-id]").count(), 0, caller + " must invalidate rendered host work");
      assert.match(await page.locator("#project-tab-panel").textContent(), /Host work unavailable · Last snapshot is not current/);
      assert.doesNotMatch(await page.locator("#project-tab-panel").textContent(), /reported active/);
      await page.unroute("**/api/overview*");
      await page.evaluate(() => refreshOverview(false));
      assert.equal(await section.locator("[data-host-work-id]").count(), 5, "successful refresh restores current host rows");
    }
    assert.equal(runtime.failedRequests.length, 2);
    assert.ok(runtime.failedRequests.every((request) => String(request).includes("/api/overview")));
    assert.ok(runtime.runtimeErrors.every((error) => /net::ERR_FAILED/.test(error)), runtime.runtimeErrors.join(" | "));
    await page.close();
  }
}
async function assertCommandApprovalPage() {
  for (const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
    const page = await browser.newPage({viewport});
    const runtime = await mount(page,scopedFixture());
    const request = {approval_id:"approval-"+viewport.width,project_id:"project:fixture",thread_id:"host-thread",turn_id:"host-turn",request_id:7,item_id:"item-1",root:"C:/project",request_digest:"a".repeat(64),command:'echo "<img src=x onerror=alert(1)>"',permitted_decisions:["decline"]};
    let requests = [request];
    const sent = [];
    let fail = false;
    let listFail = false;
    await page.route("**/api/tasks/approvals",route => {assert.deepEqual(route.request().postDataJSON(),{project_id:"project:fixture"});return listFail ? route.abort("failed") : route.fulfill(response({ok:true,requests}));});
    await page.route("**/api/tasks/approvals/respond",route => {sent.push(route.request().postDataJSON());return fail ? route.abort("timedout") : route.fulfill(response({ok:true,status:"SUBMITTED",approval_id:request.approval_id,work_completed:false}));});
    await page.evaluate(async () => { await selectProjectScope("project:fixture");setView("review"); });
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const section = page.locator("#command-approvals");
    assert.equal(await section.locator("pre").textContent(),request.command);
    assert.equal(await section.locator("img").count(),0);
    assert.equal(await section.getByRole("button").count(),1);
    assert.equal(await section.getByRole("button",{name:"Allow command"}).count(),0);
    if(evidenceDir) await page.screenshot({path:path.join(evidenceDir,"command-approval-"+viewport.width+".png"),animations:"disabled"});
    await section.getByRole("button",{name:"Decline command"}).focus();
    await page.keyboard.press("Enter");
    await page.waitForFunction(() => document.querySelector("#command-approvals").textContent.includes("Decision sent."));
    assert.equal(await section.evaluate(el => el === document.activeElement),true,await page.evaluate(() => document.activeElement.outerHTML.slice(0,300)));
    assert.deepEqual(sent,[{approval_id:request.approval_id,project_id:request.project_id,thread_id:request.thread_id,turn_id:request.turn_id,request_digest:request.request_digest,decision:"decline",acknowledge:true}]);
    await page.evaluate(() => refreshCommandApprovals());
    assert.equal(await section.getByRole("button").count(),0,"submitted request must not reappear from stale listing");
    requests=[{...request,approval_id:"empty",permitted_decisions:[]}];
    await page.evaluate(() => refreshCommandApprovals());
    assert.equal(await section.getByRole("button").count(),0);
    assert.match(await section.textContent(),/No supported decision/);
    requests=[{...request,approval_id:"uncertain",permitted_decisions:["cancel"]}];fail=true;
    await page.evaluate(() => refreshCommandApprovals());
    await section.getByRole("button",{name:"Decline and stop turn"}).click();
    await page.waitForFunction(() => !commandApprovals.pending);
    await page.waitForFunction(() => document.querySelector("#command-approvals").textContent.includes("Delivery is unconfirmed"));
    await page.evaluate(() => refreshCommandApprovals());
    assert.equal(sent.length,2);
    assert.equal(await section.getByRole("button").count(),0);
    assert.match(await section.textContent(),/Delivery is unconfirmed/);
    listFail=true;
    await page.evaluate(() => refreshCommandApprovals());
    assert.match(await section.textContent(),/Delivery is unconfirmed/);
    assert.doesNotMatch(await section.textContent(),/No decision was sent/);
    await page.evaluate(() => setDataStatus("stale"));
    assert.match(await section.textContent(),/Delivery is unconfirmed/);
    await page.evaluate(() => {setProjectSelection("all");renderCommandApprovals();});
    assert.doesNotMatch(await section.textContent(),/Delivery is unconfirmed/,"uncertainty must not leak into another scope");
    await page.evaluate(() => {setProjectSelection("project:fixture");setDataStatus("current");});
    listFail=false;
    await page.evaluate(() => refreshCommandApprovals());
    assert.match(await section.textContent(),/Delivery is unconfirmed/);
    assert.equal(await section.getByRole("button").count(),0,"reconnect cannot reoffer an attempted request");
    assert.equal(sent.length,2,"timeout, list failure and reconnect never resend");
    requests=[{...request,approval_id:"wrong-project",project_id:"foreign"},{...request,approval_id:"bad-digest",request_digest:"invalid"},{...request,approval_id:"bad-decision",permitted_decisions:["approve"]}];
    await page.evaluate(() => refreshCommandApprovals());
    assert.equal(await section.getByRole("button").count(),0,"malformed and foreign requests fail closed");
    requests=[{...request,approval_id:"fresh"}];fail=false;
    await page.evaluate(() => refreshCommandApprovals());
    await page.evaluate(() => setDataStatus("stale"));
    assert.equal(await section.getByRole("button").count(),0);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1),true);
    assert.ok(runtime.runtimeErrors.every(error => /net::ERR_FAILED|net::ERR_TIMED_OUT/.test(error)),runtime.runtimeErrors.join(" | "));
    await page.close();
  }
}
const proofFeed = imageProofFixture(6);
async function assertConversationHistoryBrowser() {
  for (const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
    const page=await browser.newPage({viewport});
    const errors=[];page.on("pageerror",error=>errors.push(error.message));
    await mount(page,scopedFixture());
    const calls=[];
    let history={project_id:"project:fixture",thread_id:"observed",status:"AVAILABLE",truncated:false,cursor:"b".repeat(64),
      items:[{id:"msg",turn_id:"turn",role:"assistant",text:'Literal <img src=x onerror="alert(1)">\n'+"Long message ".repeat(80)}]};
    await page.route("**/api/tasks/history-roster",async route=>{
      assert.deepEqual(route.request().postDataJSON(),{project_id:"project:fixture"});
      await route.fulfill(response({project_id:"project:fixture",status:"PARTIAL",truncated:true,items:[{thread_id:"observed",project_id:"project:fixture",title:"Retained conversation"}]}));
    });
    await page.route("**/api/tasks/history", async route=>{
      calls.push(route.request().postDataJSON());await route.fulfill(response(history));
    });
    await page.evaluate(()=>{
      state.projectId="project:fixture";state.ctrlId="";state.connectionStatus="live";
      state.overview.nodes=[];
      state.messageRecipientId="observed";openMessageComposer();
    });
    await page.locator('[data-message-id="msg"]').waitFor();
    assert.match(await page.locator("#message-roster-status").textContent(),/limited.*omitted/);
    assert.match(await page.locator("#message-conversation-items").textContent(),/Literal <img/);
    assert.equal(await page.locator("#message-conversation-items img").count(),0);
    assert.equal(await page.locator("#message-send").isDisabled(),true);
    assert.deepEqual(calls,[{project_id:"project:fixture",thread_id:"observed"}]);
    assert.equal(await page.locator("#message-composer").evaluate(el=>{
      const body=el.querySelector(".message-composer-body"),footer=el.querySelector("footer").getBoundingClientRect();
      return getComputedStyle(body).overflowY==="auto" && body.scrollWidth<=body.clientWidth+1 && footer.bottom<=innerHeight+1 && document.documentElement.scrollWidth<=innerWidth+1;
    }),true);
    history={...history,status:"EMPTY",items:[]};await page.evaluate(()=>refreshMessageHistory());
    assert.equal(await page.locator("#message-conversation-state").textContent(),"No messages yet.");
    history={...history,status:"UNAVAILABLE",cursor:null};await page.evaluate(()=>refreshMessageHistory());
    assert.match(await page.locator("#message-conversation-state").textContent(),/unavailable/);
    await page.locator("#message-recipient").focus();await page.keyboard.press("Escape");
    assert.equal(await page.locator("#message-composer").isVisible(),false);
    assert.deepEqual(errors,[]);await page.close();
  }
}
async function assertObservedTaskAndChat() {
  for (const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
    const page = await browser.newPage({viewport});
    const runtime = await mount(page, scopedFixture());
    await page.evaluate(() => {
      state.projectId="project:fixture"; state.ctrlId=""; state.connectionStatus="live";
      state.overview.nodes=[{id:"observed-chief",project_id:"project:fixture",title:"Observed task",status:"active",role:"independent",agent_role:null}];
      state.overview.roots=[];
      renderOverview(); renderAgentTable();
    });
    assert.match(await page.locator("#agents-summary").textContent(), /1 observed host task · no admitted agents/);
    assert.equal(await page.locator("#agent-table-body h3").textContent(), "Observed host tasks");
    assert.equal(await page.locator('#overview-project-cards [data-active-codex-task]').count(),0,"compact Overview does not duplicate host-task discovery");
    assert.equal(await page.locator('[data-overview-hierarchy-node="observed-chief"]').count(),0,"observed host task is not an admitted hierarchy agent");
    assert.equal(await page.locator('#agent-table-body [data-active-codex-task="observed-chief"]').count(),1);
    assert.equal(await page.locator('[data-active-codex-task] [role=progressbar]').count(),0);
    await page.evaluate(() => {
      state.overview.nodes.push({id:"ctrl",project_id:"project:fixture",status:"idle"},{id:"foreign-active",project_id:"project:foreign",status:"active",title:"Foreign task"});
      state.ctrlId="ctrl"; renderOverview(); renderAgentTable();
    });
    assert.equal(await page.locator('#agent-table-body [data-active-codex-task="observed-chief"]').count(),1);
    assert.equal(await page.locator('#agent-table-body [data-active-codex-task="foreign-active"]').count(),0);
    await page.evaluate(() => {state.ctrlId="unresolved";renderOverview();renderAgentTable();});
    assert.equal(await page.locator('#agent-table-body [data-active-codex-task]').count(),0);
    assert.match(await page.locator('#agent-table-body').textContent(),/Current host activity is unavailable/);
    await page.evaluate(() => {state.projectId="all";renderOverview();renderAgentTable();});
    assert.equal(await page.locator('#agent-table-body [data-active-codex-task]').count(),0,"unresolved CTRL is not All");
    await page.evaluate(() => {state.ctrlId="";renderOverview();renderAgentTable();});
    assert.equal(await page.locator('#agent-table-body [data-active-codex-task="foreign-active"]').count(),1,"explicit All includes foreign project");
    await page.evaluate(() => {state.projectId="project:fixture";});
    await page.evaluate(() => {state.connectionStatus="reconnecting";renderOverview();renderAgentTable();});
    assert.equal(await page.locator('#agent-table-body [data-active-codex-task]').count(),0);
    assert.equal(await page.locator('#overview-project-cards [data-active-codex-task]').count(),0);
    await page.evaluate(() => {state.connectionStatus="live";openMessageComposer();});
    const panel=page.locator("#message-composer");
    await panel.waitFor({state:"visible"});
    const geometry=await panel.evaluate(el => {
      const header=el.querySelector("header").getBoundingClientRect(),body=el.querySelector(".message-composer-body").getBoundingClientRect(),footer=el.querySelector("footer").getBoundingClientRect();
      return {ordered:header.bottom<=body.top+1 && body.bottom<=footer.top+1,inside:footer.bottom<=innerHeight+1,width:document.documentElement.scrollWidth<=innerWidth+1};
    });
    assert.deepEqual(geometry,{ordered:true,inside:true,width:true});
    assert.equal(await page.locator("#message-draft").getAttribute("rows"),"2");
    assert.match(await page.locator("#message-conversation-state").textContent(),/unavailable|Choose/);
    await page.keyboard.press("Escape");
    assert.equal(await panel.isVisible(),false);
    await page.close();
  }
}
proofFeed.items.push({
  task_id: "ctrl", project_id: "project:fixture", evidence_id: "fixture-generating-asset", digest: "9".repeat(64),
  media_type: "image/png", display_name: "Onboarding illustration", asset_type: "illustration",
  generation_stage: "GENERATING", progress_measured: true, progress_percent: 42, observed_at_ms: 1724900000000,
});
  const usageHistory = structuredClone(fixture.usageHistory);
  usageHistory.verified_yield = {
    schema_version: 1,
    formula: "net_scope_points * 100000 / observed_tokens",
    portfolio: { scope: { type: "portfolio", id: "all" }, measurement_state: "MEASURED", confidence: "HIGH", observed_tokens: 120000, yield_per_100k: 2.5, rework_drag: 4, series: [{ observed_tokens: 40000, net_scope_points: 1, scope_version: 1 }, { observed_tokens: 80000, net_scope_points: 2, scope_version: 1 }] },
    projects: [{ scope: { type: "project", id: "project:fixture" }, measurement_state: "MEASURED", confidence: "HIGH", observed_tokens: 80000, yield_per_100k: 3.1, rework_drag: 0, series: [{ observed_tokens: 30000, net_scope_points: 1, scope_version: 1 }, { observed_tokens: 50000, net_scope_points: 1.5, scope_version: 2 }] }],
    tasks: [{ scope: { type: "task", id: "ctrl", project_id: "project:fixture" }, measurement_state: "MEASURED", confidence: "HIGH", observed_tokens: 50000, yield_per_100k: 2, rework_drag: 0, series: [{ observed_tokens: 50000, net_scope_points: 1, scope_version: 1 }] }],
    owners: [{ scope: { type: "owner", id: "CTRL", project_id: "project:fixture" }, measurement_state: "MEASURED", confidence: "PARTIAL", observed_tokens: 50000, yield_per_100k: 2, rework_drag: 0, series: [{ observed_tokens: 50000, net_scope_points: 1, scope_version: 1 }] }],
  };
  const overview = scopedFixture();
  overview.overview_metrics = structuredClone(overviewMetricFixture);
  const projectProgress = {
    ok: true,
    project_id: "project:fixture",
    scope_version: 2,
    status: "MEASURED",
    percent: 60,
    cursor: { event_seq: 2, event_id: "progress-event-2", event_digest: "d".repeat(64) },
    blocks: [
      { milestone_id: "Foundation", block_id: "Identity contract", task_id: "ctrl", owner_id: "CTRL", lifecycle_state: "VERIFIED", measurement_state: "MEASURED", committed_weight: 5, admitted_proof_weight: 5, eta: {}, proof_receipt_ids: ["receipt-1"] },
      { milestone_id: "Interface", block_id: "Console surfaces", task_id: "nested-task", owner_id: "Designer", lifecycle_state: "ACTIVE", measurement_state: "MEASURED", committed_weight: 5, admitted_proof_weight: 1, eta: { end_ms: Date.now() + 3600000 }, proof_receipt_ids: [] },
    ],
  };
  projectProgress.progress_queue = {
    view_id: "view.project.progress", renderer: "table", project_id: "project:fixture", status: "CURRENT", available: true,
    scope_binding: { project_id: "project:fixture", ctrl_ids: ["ctrl", "nested-ctrl"], cursor: structuredClone(projectProgress.cursor) },
    accepted_cursor: structuredClone(projectProgress.cursor),
    segments: [
      { segment_id: "segment.project.progress.active", label: "Active", rows: [{
        scope_binding: { project_id: "project:fixture", ctrl_id: "nested-ctrl", cursor: structuredClone(projectProgress.cursor) },
        task_id: "nested-task", task_name: "Review screenshots", lifecycle: "ACTIVE", queue_state: null, runnable: null,
        progress: { state: "KNOWN", completed_milestones: 3, total_milestones: 5, percent: 60 },
        eta: { state: "KNOWN", start_ms: 1788076800000, end_ms: 1788080400000, confidence: "medium", basis_receipt_ids: ["eta-receipt"] },
        elapsed: { state: "KNOWN", elapsed_ms: 300000 }, freshness: { state: "CURRENT", observed_at_ms: 1788076800000 },
      }] },
      { segment_id: "segment.project.progress.queue", label: "Queue", rows: [] },
    ],
  };
  const overrides = {
    proofFeed,
    usageByHours: { 1: usageHistory, 24: usageHistory },
    projectProgress,
    projectProgressFeed: fixture.projectProgressFeed,
    notifications: notificationFixture(),
    roleManifests: roleManifestFixture(),
  };
  try {
    await assertCommandApprovalPage();
    await assertObservedTaskAndChat();
    await assertConversationHistoryBrowser();
    await assertHostWorkPage();
    const onboardingPage = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    {
      const usagePage = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
      let releaseDay;
      let delayed = false;
      const requestedHours = [];
      const usagePayload = (hours) => ({ ok: true, status: "ok", hours, items: [{ bucket_ms: 1, delta_tokens: 9 }], task_usage_status: "ok", task_usage: [
        { thread_id: "small", title: "Small task", project_id: "project:fixture", tokens: 5 },
        { thread_id: "large", title: hours === 168 ? "Weekly leader" : "Hourly leader", project_id: "project:fixture", tokens: hours === 168 ? 700 : 90 },
        { thread_id: "missing", title: "Missing measurement", project_id: "project:fixture", tokens: null },
      ] });
      const usageRuntime = await mount(usagePage, scopedFixture(), { ...overrides, usageResponse: async (url) => {
        const hours = Number(url.searchParams.get("hours"));
        requestedHours.push(hours);
        const body = usagePayload(hours);
        if (hours === 24 && delayed) { delayed = false; await new Promise((resolve) => { releaseDay = resolve; }); }
        return response(body);
      } });
      await usagePage.locator('[data-overview-metric="tbr"]').click();
      await usagePage.getByRole('button',{name:'By task',exact:true}).click();
      const table = usagePage.locator("#highest-usage-tasks");
      await usagePage.waitForFunction(() => document.querySelector("#highest-usage-tasks").textContent.includes("Hourly leader"));
      assert.deepEqual(await table.locator("tbody th button > span:first-child").allTextContents(), ["Hourly leader", "Small task"]);
      assert.deepEqual(await table.locator("tbody td:nth-child(3)").allTextContents(), ["90 tokens", "5 tokens"]);
      assert.equal(await table.locator("tbody button:disabled").count(), 2, 'Aggregate-only fixture exposes no enabled history action');
      const ranges = usagePage.getByRole("group", { name: "Task usage range", exact: true });
      assert.equal(await ranges.getByRole("button", { name: "1d", exact: true }).getAttribute("aria-pressed"), "true");
      assert.equal(await ranges.getByRole("button", { name: "1m", exact: true }).isDisabled(), true);
      await ranges.getByRole("button", { name: "1w", exact: true }).click();
      await usagePage.waitForFunction(() => document.querySelector("#highest-usage-tasks").textContent.includes("Weekly leader"));
      delayed = true;
      await ranges.getByRole("button", { name: "1d", exact: true }).click();
      await usagePage.waitForFunction(() => document.querySelector("#highest-usage-tasks").getAttribute("aria-busy") === "true");
      await ranges.getByRole("button", { name: "1w", exact: true }).focus();
      await usagePage.keyboard.press("Enter");
      await usagePage.waitForFunction(() => document.querySelector("#highest-usage-tasks").textContent.includes("Weekly leader"));
      releaseDay();
      await usagePage.waitForTimeout(100);
      assert.equal(await table.locator("tbody th button > span:first-child").first().textContent(), "Weekly leader");
      assert.deepEqual([...new Set(requestedHours)], [1, 24, 168]);
      assert.equal(await ranges.getByRole("button", { name: "1w", exact: true }).getAttribute("aria-pressed"), "true");
      await usagePage.locator(".highest-usage-section").scrollIntoViewIfNeeded();
      if (evidenceDir) await usagePage.screenshot({ path: path.join(evidenceDir, "highest-usage-desktop-1440x1000.png"), animations: "disabled" });
      await usagePage.setViewportSize({ width: 390, height: 844 });
      assert.ok(await usagePage.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      assert.ok(await ranges.locator("button").evaluateAll((buttons) => buttons.every((button) => { const box = button.getBoundingClientRect(); return box.width >= 44 && box.height >= 44; })));
      assert.ok(await ranges.locator("button").evaluateAll((buttons) => buttons.every((button) => parseFloat(getComputedStyle(button).fontSize) >= 12)));
      if (evidenceDir) await usagePage.screenshot({ path: path.join(evidenceDir, "highest-usage-mobile-390x844.png"), animations: "disabled" });
      await usagePage.evaluate(() => { state.usageHistory.task_usage = []; renderUsageCharts(); });
      assert.match(await table.textContent(), /No measured task usage/);
      await usagePage.evaluate(() => { delete state.usageHistory.task_usage; renderUsageCharts(); });
      assert.match(await table.textContent(), /unavailable/);
      await usagePage.evaluate(() => { state.usageStatus = "error"; renderUsageCharts(); });
      assert.match(await table.textContent(), /could not be loaded/);
      assert.deepEqual(usageRuntime.runtimeErrors, []);
      assert.deepEqual(usageRuntime.failedRequests, []);
      await usagePage.close();
    }
    {
      const page = await browser.newPage({viewport:{width:1440,height:1000}});
      const requested = [];
      const runtime = await mount(page, scopedFixture(), {...overrides, usageResponse:async url => {
        const hours=Number(url.searchParams.get('hours')), now=Date.now();
        const explicit=url.searchParams.has('after_ms');
        const after=explicit?Number(url.searchParams.get('after_ms')):now-hours*3600000;
        const before=explicit?Number(url.searchParams.get('before_ms')):now;
        requested.push({hours,after,before,explicit});
        const quota={status:'KNOWN',limit_id:'main',window:'primary',remaining_percent:40,reset_at_ms:now+21600000,forecast:{status:'ESTIMATED',exhaustion_at_ms:now+14400000},history:[{sampled_at_ms:now-60000,remaining_percent:60},{sampled_at_ms:now,remaining_percent:40}]};
        const task_usage=[{thread_id:'alpha',project_id:'project:fixture',title:'Project connections',tokens:100},{thread_id:'beta',project_id:'project:fixture',title:'Usage metrics',tokens:50}];
        const items=task_usage.flatMap((row,index)=>[0,1].map(offset=>({thread_id:row.thread_id,project_id:row.project_id,bucket_start_ms:after+offset*300000,bucket_end_ms:after+(offset+1)*300000,rate_start_ms:after+offset*300000,rate_end_ms:after+(offset+1)*300000,tokens:row.tokens/2,tokens_per_minute:index?5:10,model:null,model_status:'UNKNOWN'})));
        return response({ok:true,status:'partial',hours,scope:{type:'all-projects'},window:{after_ms:after,before_ms:before,explicit,retention_days:30},items:[],task_usage,task_usage_status:'partial',task_history:{items,status:'partial',total_tokens:150,truncated:false},rate_history:[0,1].map(offset=>({rate_start_ms:after+offset*300000,rate_end_ms:after+(offset+1)*300000,tokens_per_minute:15,status:'observed'})),usage_now:{status:'observed',source:'persisted_local_token_deltas',window_hours:hours,sampled_at_ms:before,rate_sampled_at_ms:after+600000,rate_observed_interval_ms:600000,rate_coverage:'partial',rate_tokens_per_minute:15},account_limits:{status:'KNOWN',scope:'account',source:'codex_app_server.account/rateLimits/read',sampled_at_ms:now,account_key:'fixture-account',windows:[quota]},account_history:{scope:'account',status:'partial',items:explicit?[]:[{sampled_at_ms:now-60000,account_key:'fixture-account',windows:[{...quota,remaining_percent:60}]},{sampled_at_ms:now,account_key:'fixture-account',windows:[quota]}]}});
      }});
      await page.locator('[data-overview-metric="usage"]').click();
      const dialog=page.locator('#metric-detail-dialog');
      await page.waitForFunction(()=>document.querySelector('.usage-detail-values')?.textContent.includes('40%'));
      assert.equal(await dialog.getByRole('button',{name:'By task',exact:true}).count(),0);
      assert.equal(await dialog.getByRole('button',{name:'1m',exact:true}).isEnabled(),true);
      await assertMetricDetailContainment(page);
      if(evidenceDir) await page.screenshot({path:path.join(evidenceDir,'usage-modal-desktop-1440x1000.png'),animations:'disabled'});
      await page.keyboard.press('Escape');
      await page.locator('[data-overview-metric="tbr"]').click();
      await dialog.getByRole('button',{name:'By task',exact:true}).click();
      assert.deepEqual(await dialog.locator('tbody th').allTextContents(),['Project connections›','Usage metrics›']);
      assert.equal(await dialog.locator('[aria-label="Historical model unavailable"]').count(),2);
      await dialog.getByRole('button',{name:'Project connections',exact:false}).click();
      assert.equal(await dialog.getByRole('button',{name:'← All tasks',exact:true}).count(),1);
      assert.equal(await dialog.locator('.task-usage-graph circle').count(),0);
      await dialog.getByRole('button',{name:'← All tasks',exact:true}).click();
      await dialog.getByRole('group',{name:'Task comparison view'}).getByRole('button',{name:'Graph',exact:true}).click();
      assert.equal(new Set(await dialog.locator('.task-usage-graph path[stroke]').evaluateAll(paths=>paths.map(path=>path.getAttribute('stroke')))).size,2);
      const seriesToggle=dialog.locator('[data-task-usage-visible]').first();
      await seriesToggle.focus(); await page.keyboard.press('Space');
      assert.equal(await seriesToggle.getAttribute('aria-pressed'),'false');
      assert.equal(await dialog.locator('.task-usage-graph path[stroke]').count(),1);
      await page.evaluate(()=>renderOverviewMetrics());
      assert.equal(await seriesToggle.getAttribute('aria-pressed'),'false');
      assert.equal(await seriesToggle.evaluate(el=>el===document.activeElement),true);
      await seriesToggle.click(); assert.equal(await dialog.locator('.task-usage-graph path[stroke]').count(),2);
      await dialog.getByRole('button',{name:'Legend',exact:true}).click();
      assert.equal(await dialog.locator('.task-usage-legend').count(),0);
      await page.evaluate(()=>renderOverviewMetrics());
      assert.equal(await dialog.getByRole('button',{name:'Legend',exact:true}).getAttribute('aria-pressed'),'false');
      const gear=dialog.getByLabel('Custom date range',{exact:true});
      await gear.focus(); await page.keyboard.press('Enter');
      const dates=await page.evaluate(()=>[2,1].map(days=>{const date=new Date(Date.now()-days*86400000);return new Date(date-date.getTimezoneOffset()*60000).toISOString().slice(0,16);}));
      await dialog.locator('[name="after"]').fill(dates[0]); await dialog.locator('[name="before"]').fill(dates[1]);
      await page.evaluate(()=>renderOverviewMetrics());
      assert.equal(await dialog.locator('[name="after"]').inputValue(),dates[0]);
      await dialog.getByRole('button',{name:'Apply dates',exact:true}).click();
      await page.waitForFunction(()=>document.querySelector('#metric-date-status').textContent==='Date range applied.');
      assert.equal(requested.at(-1).explicit,true);
      await gear.focus(); await page.keyboard.press('Escape');
      assert.equal(await dialog.isVisible(),true);
      await dialog.getByRole('button',{name:'1m',exact:true}).click();
      await page.waitForFunction(()=>state.usageStatus==='current'&&state.usageWindowHours===720);
      assert.equal(requested.at(-1).hours,720); assert.equal(requested.at(-1).explicit,false);
      if(evidenceDir) await page.screenshot({path:path.join(evidenceDir,'tbr-comparison-desktop-1440x1000.png'),animations:'disabled'});
      await page.setViewportSize({width:390,height:844});
      await assertMetricDetailContainment(page);
      if(evidenceDir) await page.screenshot({path:path.join(evidenceDir,'tbr-modal-mobile-390x844.png'),animations:'disabled'});
      assert.deepEqual(runtime.runtimeErrors,[]); assert.deepEqual(runtime.failedRequests,[]);
      await page.close();
    }
    const onboarding = await mount(onboardingPage, scopedFixture(), { ...overrides, keepOnboarding: true });
    await assertDecodedVisibleOnboardingImage(onboardingPage, "#onboarding-panel-1 img", 1920, 1080);
    await captureOnboardingEvidence(onboardingPage, "01-slide-1-desktop-1440x1000");
    assert.equal(await onboardingPage.getByText(/^Step [1-5] of 5$/).count(), 0);
    assert.equal(await onboardingPage.locator('[data-onboarding-step][aria-current="step"]').getAttribute("data-onboarding-step"), "0");
    const desktopGeometry = await onboardingPage.locator("#onboarding-dialog").evaluate((dialog) => {
      const rect = (element) => { const value = element.getBoundingClientRect(); return { left: value.left, top: value.top, right: value.right, bottom: value.bottom, width: value.width, height: value.height }; };
      const primary = rect(document.querySelector("#onboarding-primary"));
      const skip = rect(document.querySelector("#onboarding-skip"));
      const controls = [...dialog.querySelectorAll("button")].filter((button) => !button.hidden && getComputedStyle(button).display !== "none" && button.getClientRects().length).map(rect);
      const footerButtons = [...dialog.querySelectorAll(".dialog-footer button")].filter((button) => !button.hidden && getComputedStyle(button).display !== "none").map((button) => ({ id: button.id, text: button.textContent.trim() }));
      return { dialog: rect(dialog), primary, skip, controls, backVisible: document.querySelector("#onboarding-back").getClientRects().length > 0, footerButtons, viewport: { width: innerWidth, height: innerHeight }, documentWidth: document.documentElement.scrollWidth };
    });
    assert.ok(desktopGeometry.dialog.width <= 1041 && desktopGeometry.dialog.height <= 721);
    assert.ok(desktopGeometry.dialog.left >= 0 && desktopGeometry.dialog.right <= desktopGeometry.viewport.width);
    assert.ok(desktopGeometry.dialog.top >= 0 && desktopGeometry.dialog.bottom <= desktopGeometry.viewport.height);
    assert.ok(desktopGeometry.controls.every((control) => control.width >= 44 && control.height >= 44));
    assert.ok(Math.abs((desktopGeometry.primary.left + desktopGeometry.primary.width / 2) - (desktopGeometry.skip.left + desktopGeometry.skip.width / 2)) <= 1);
    assert.ok(desktopGeometry.skip.top >= desktopGeometry.primary.bottom);
    assert.equal(desktopGeometry.backVisible, false);
    assert.deepEqual(desktopGeometry.footerButtons, [{ id: "onboarding-skip", text: "Skip for now" }, { id: "onboarding-primary", text: "Start guided tour" }]);
    assert.ok(desktopGeometry.documentWidth <= desktopGeometry.viewport.width);
    await assertDialogFrame(onboardingPage, "#onboarding-dialog");
    await onboardingPage.getByRole("button", { name: "Start guided tour" }).click();
    await assertLaterStepNavigation(onboardingPage, "Continue");
    await assertOnboardingCoordination(onboardingPage, 1440);
    await captureOnboardingEvidence(onboardingPage, "02-slide-2-coordination-desktop-1440x1000");
    assert.equal(await onboardingPage.locator('[data-onboarding-step][aria-current="step"]').getAttribute("data-onboarding-step"), "1");
    const motionTiming = await onboardingPage.locator("#onboarding-dialog").evaluate((dialog) => {
      const timing = (selector) => {
        const style = getComputedStyle(dialog.querySelector(selector));
        return { delay: parseFloat(style.animationDelay) * 1000, duration: parseFloat(style.animationDuration) * 1000 };
      };
      return [timing(".onboarding-panel.is-active .onboarding-artwork"), timing(".onboarding-panel.is-active > h2"), timing(".onboarding-panel.is-active > p"), timing("#onboarding-primary")];
    });
    assert.deepEqual(motionTiming.map((item) => Math.round(item.delay)), [0, 55, 110, 220]);
    assert.ok(Math.max(...motionTiming.map((item) => item.delay + item.duration)) <= 550);
    assert.equal(await onboardingPage.locator('[data-asset-slot="swarm-guided-tour-coordination-v1"]').count(), 0);
     assert.match(await onboardingPage.locator("#onboarding-panel-2").textContent(), /One goal\. A coordinated team\.[\s\S]*SWARM turns a clear request into owned work, handoffs, and review\./);
    await onboardingPage.getByRole("button", { name: "Back" }).focus();
    await onboardingPage.keyboard.press("Enter");
    await onboardingPage.waitForFunction(() => document.activeElement?.id === "onboarding-primary");
    assert.equal(await onboardingPage.locator('[data-onboarding-step][aria-current="step"]').getAttribute("data-onboarding-step"), "0");
    assert.equal(await onboardingPage.getByRole("button", { name: "Skip for now" }).isVisible(), true);
    assert.equal(await onboardingPage.getByRole("button", { name: "Back" }).isVisible(), false);
    await onboardingPage.keyboard.press("Enter");
    assert.equal(await onboardingPage.locator('[data-onboarding-step][aria-current="step"]').getAttribute("data-onboarding-step"), "1");
    await assertLaterStepNavigation(onboardingPage, "Continue");
    await onboardingPage.getByRole("button", { name: "Continue" }).click();
    assert.equal(await onboardingPage.locator('[data-onboarding-step][aria-current="step"]').getAttribute("data-onboarding-step"), "2");
    assert.equal(await onboardingPage.locator("#onboarding-dialog").getAttribute("data-motion-step"), "2");
    assert.equal(await onboardingPage.evaluate(() => document.activeElement?.id), "onboarding-primary");
    await assertLaterStepNavigation(onboardingPage, "Continue");
    await assertOnboardingRoleGroup(onboardingPage, 1440);
    await captureOnboardingEvidence(onboardingPage, "03-slide-3-desktop-1440x1000");
    await onboardingPage.getByRole("button", { name: "Continue" }).click();
    assert.equal(await onboardingPage.locator('[data-onboarding-step][aria-current="step"]').getAttribute("data-onboarding-step"), "3");
    assert.equal(await onboardingPage.locator('.onboarding-project-tool').count(), 1);
    assert.equal(await onboardingPage.locator('.onboarding-project-tool').getAttribute("alt"), "The orange SWARM mascot controls connected flowchart, timeline, asset-library, and table views.");
    const desktopProjectToolProof = await assertDecodedVisibleOnboardingImage(onboardingPage, ".onboarding-project-tool", 1536, 1024);
    assert.ok(desktopProjectToolProof.rect.width <= await onboardingPage.locator("#onboarding-panel-4").evaluate((panel) => panel.clientWidth + 1));
     assert.match(await onboardingPage.locator("#onboarding-panel-4").textContent(), /Choose how SWARM works/);
    await assertLaterStepNavigation(onboardingPage, "Continue");
    await captureOnboardingEvidence(onboardingPage, "04-slide-4-desktop-1440x1000");
    await onboardingPage.getByRole("button", { name: "Continue" }).click();
    assert.equal(await onboardingPage.locator('[data-onboarding-step][aria-current="step"]').getAttribute("data-onboarding-step"), "4");
    assert.equal(await onboardingPage.locator("#onboarding-dialog .dialog-body").evaluate((body) => body.scrollTop), 0);
    assert.equal(await onboardingPage.getByRole("button", { name: "Start using SWARM" }).count(), 1);
    await assertLaterStepNavigation(onboardingPage, "Start using SWARM");
    const onboardingConfigPanel = onboardingPage.locator("#onboarding-panel-5");
    const taskLife = onboardingConfigPanel.getByRole("slider", { name: "Task life" });
    const advancedSettingsLink = onboardingConfigPanel.getByRole("button", { name: "Advanced settings" });
    assert.equal(await onboardingConfigPanel.getByLabel("Default", { exact: true }).isChecked(), true);
    assert.equal(await onboardingConfigPanel.getByLabel("Ultrafast", { exact: true }).count(), 0);
    assert.equal(await onboardingConfigPanel.getByLabel("Auto mode").isChecked(), true);
    assert.equal(await taskLife.inputValue(), "2");
    assert.equal(await taskLife.getAttribute("aria-valuetext"), "Balanced — unavailable");
    assert.equal(await taskLife.isDisabled(), true);
    assert.equal(await advancedSettingsLink.isVisible(), true);
    assert.equal(await onboardingConfigPanel.locator(".onboarding-config-advanced,.onboarding-advanced-content").count(), 0);
    assert.equal(await onboardingConfigPanel.getByLabel("Usage Saver").count(), 0);
    await captureOnboardingEvidence(onboardingPage, "05-slide-5-config-desktop-1440x1000");
    const taskLifeInfo = onboardingConfigPanel.locator('summary[aria-label="About task life"]');
    await taskLifeInfo.focus();
    await onboardingPage.keyboard.press("Enter");
    assert.equal(await onboardingConfigPanel.getByRole("tooltip").isVisible(), true);
    assert.match(await onboardingConfigPanel.getByRole("tooltip").textContent(), /Short clears context sooner[\s\S]*Balanced hands over[\s\S]*Long reduces handovers/);
    await captureOnboardingEvidence(onboardingPage, "05b-slide-5-task-life-tooltip-desktop-1440x1000");
    await onboardingPage.keyboard.press("Enter");
    await onboardingPage.evaluate(() => {
      window.__onboardingMotionClassMutations = 0;
      window.__onboardingMotionObserver = new MutationObserver((records) => { window.__onboardingMotionClassMutations += records.length; });
      window.__onboardingMotionObserver.observe(document.querySelector("#onboarding-dialog"), { attributes: true, attributeFilter: ["class"] });
    });
    await onboardingConfigPanel.locator('label:has([data-onboarding-control="speed-fast"])').click();
    await onboardingPage.waitForFunction(() => {
      const input = document.querySelector('#onboarding-configuration input[data-onboarding-control="speed-fast"]');
      return input?.checked && !input.disabled;
    });
    assert.deepEqual(await onboardingPage.locator("#onboarding-dialog").evaluate((dialog) => ({ step: dialog.dataset.motionStep, classMutations: window.__onboardingMotionClassMutations })), { step: "4", classMutations: 0 });
    await onboardingConfigPanel.getByLabel("Auto mode").focus();
    const autoModeRequest = onboardingPage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "POST" && configRequestValue(request.postDataJSON(), "automation.mode") === "manual");
    await onboardingPage.keyboard.press("Space");
    await autoModeRequest;
    await onboardingPage.waitForFunction(() => {
      const input = document.querySelector('#onboarding-configuration input[data-config-key="automation.mode"]');
      return !input?.checked && !input?.disabled;
    });
    assert.deepEqual(onboarding.configRequests.slice(-2).map((payload) => [configRequestValue(payload, "execution.fast_mode"), configRequestValue(payload, "automation.mode")]), [[true, "standard"], [true, "manual"]]);
    await onboardingPage.evaluate(() => window.__onboardingMotionObserver.disconnect());
    assert.equal(await onboardingPage.getByRole("button", { name: "Close onboarding" }).count(), 1);
    assert.equal(await onboardingPage.getByRole("button", { name: "Skip for now" }).count(), 0);
    await onboardingPage.getByRole("button", { name: "Start using SWARM" }).click();
    assert.equal(await onboardingPage.locator("#onboarding-dialog").isVisible(), false);
    assert.equal(await onboardingPage.evaluate(() => localStorage.getItem("swarm.onboarding.v2.seen")), "1");
    await onboardingPage.reload({ waitUntil: "domcontentloaded" });
     await onboardingPage.waitForFunction(() => !document.querySelector("#overview-content")?.hasAttribute("hidden"));
     assert.equal(await onboardingPage.locator("#onboarding-dialog").isVisible(), false);
     await onboardingPage.getByRole("tab", { name: "Settings", exact: true }).click();
     await onboardingPage.getByText("Advanced settings", { exact: true }).click();
     await onboardingPage.getByRole("button", { name: "Replay tour" }).click();
    assert.equal(await onboardingPage.locator('[data-onboarding-step][aria-current="step"]').getAttribute("data-onboarding-step"), "0");
    await onboardingPage.getByRole("button", { name: "Skip for now" }).click();
    await onboardingPage.reload({ waitUntil: "domcontentloaded" });
    await onboardingPage.waitForFunction(() => !document.querySelector("#overview-content")?.hasAttribute("hidden"));
    assert.equal(await onboardingPage.locator("#onboarding-dialog").isVisible(), false);
    assert.deepEqual(onboarding.runtimeErrors, [], `failed=${onboarding.failedRequests.join(" | ")}`);
    await onboardingPage.close();

    const onboardingAdvancedRoutePage = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const onboardingAdvancedRoute = await mount(onboardingAdvancedRoutePage, scopedFixture(), { ...overrides, keepOnboarding: true });
    await onboardingAdvancedRoutePage.getByRole("button", { name: "Start guided tour" }).click();
    for (let step = 0; step < 3; step += 1) await onboardingAdvancedRoutePage.getByRole("button", { name: "Continue" }).click();
    const advancedSettingsRoute = onboardingAdvancedRoutePage.getByRole("button", { name: "Advanced settings" });
    const advancedRouteTarget = await advancedSettingsRoute.evaluate((button) => {
      const rect = button.getBoundingClientRect();
      return { width: rect.width, height: rect.height };
    });
    assert.ok(advancedRouteTarget.width >= 44 && advancedRouteTarget.height >= 44);
    const configRequestsBeforeRoute = onboardingAdvancedRoute.configRequests.length;
    await advancedSettingsRoute.click();
    await onboardingAdvancedRoutePage.waitForFunction(() => location.hash === "#settings-advanced" && !document.querySelector('[data-view-panel="settings"]')?.hidden);
    assert.equal(await onboardingAdvancedRoutePage.locator("#onboarding-dialog").isVisible(), false);
    assert.equal(await onboardingAdvancedRoutePage.locator('[data-view-panel="settings"]').isVisible(), true);
    assert.equal(await onboardingAdvancedRoutePage.locator("#settings-advanced").count(), 1);
    if (evidenceDir) await onboardingAdvancedRoutePage.screenshot({ path: path.join(evidenceDir, "05c-advanced-settings-route-desktop-1440x1000.png"), fullPage: false, animations: "disabled" });
    assert.equal(await onboardingAdvancedRoutePage.evaluate(() => localStorage.getItem("swarm.onboarding.v2.seen")), "1");
    assert.equal(onboardingAdvancedRoute.configRequests.length, configRequestsBeforeRoute);
    await onboardingAdvancedRoutePage.goBack();
    await onboardingAdvancedRoutePage.waitForFunction(() => location.hash === "#overview" && !document.querySelector('[data-view-panel="overview"]')?.hidden);
    assert.deepEqual(onboardingAdvancedRoute.runtimeErrors, []);
    await onboardingAdvancedRoutePage.close();

    const onboardingTabletPage = await browser.newPage({ viewport: { width: 834, height: 1112 } });
    const onboardingTablet = await mount(onboardingTabletPage, scopedFixture(), { ...overrides, keepOnboarding: true });
    await assertDialogFrame(onboardingTabletPage, "#onboarding-dialog");
    await onboardingTabletPage.getByRole("button", { name: "Start guided tour" }).click();
    await assertLaterStepNavigation(onboardingTabletPage, "Continue");
    await assertOnboardingCoordination(onboardingTabletPage, 834);
    await onboardingTabletPage.getByRole("button", { name: "Continue" }).click();
    await assertOnboardingRoleGroup(onboardingTabletPage, 834);
    await onboardingTabletPage.getByRole("button", { name: "Continue" }).click();
    assert.ok(await onboardingTabletPage.locator(".onboarding-project-tool").evaluate((node) => node.scrollWidth <= node.closest(".onboarding-panel").clientWidth + 1));
    await onboardingTabletPage.getByRole("button", { name: "Continue" }).click();
    await captureOnboardingEvidence(onboardingTabletPage, "05d-slide-5-config-tablet-834x1112");
    assert.equal(await onboardingTabletPage.locator("#onboarding-panel-5 .onboarding-config-advanced").count(), 0);
    assert.equal(await onboardingTabletPage.getByRole("button", { name: "Advanced settings" }).isVisible(), true);
    assert.ok(await onboardingTabletPage.locator("#onboarding-configuration").evaluate((node) => node.scrollWidth <= node.clientWidth + 1));
    await onboardingTabletPage.getByRole("button", { name: "Advanced settings" }).click();
    await onboardingTabletPage.waitForFunction(() => location.hash === "#settings-advanced" && document.activeElement?.id === "settings-edit-config");
    if (evidenceDir) await onboardingTabletPage.screenshot({ path: path.join(evidenceDir, "05e-advanced-settings-route-tablet-834x1112.png"), fullPage: false, animations: "disabled" });
    assert.deepEqual(onboardingTablet.runtimeErrors, []);
    await onboardingTabletPage.close();

    const onboardingMobilePage = await browser.newPage({ viewport: { width: 390, height: 844 } });
    const onboardingMobile = await mount(onboardingMobilePage, scopedFixture(), { ...overrides, keepOnboarding: true });
    await assertDialogFrame(onboardingMobilePage, "#onboarding-dialog");
    await captureOnboardingEvidence(onboardingMobilePage, "06-slide-1-mobile-390x844");
    await onboardingMobilePage.getByRole("button", { name: "Start guided tour" }).click();
    await assertLaterStepNavigation(onboardingMobilePage, "Continue");
    await assertOnboardingCoordination(onboardingMobilePage, 390);
    await captureOnboardingEvidence(onboardingMobilePage, "07-slide-2-coordination-mobile-390x844");
    await onboardingMobilePage.getByRole("button", { name: "Continue" }).click();
    await assertOnboardingRoleGroup(onboardingMobilePage, 390);
    await captureOnboardingEvidence(onboardingMobilePage, "08-slide-3-mobile-390x844");
    await onboardingMobilePage.getByRole("button", { name: "Continue" }).click();
    assert.ok(await onboardingMobilePage.locator(".onboarding-project-tool").evaluate((node) => node.scrollWidth <= node.closest(".onboarding-panel").clientWidth + 1));
    await captureOnboardingEvidence(onboardingMobilePage, "09-slide-4-mobile-390x844");
    await onboardingMobilePage.getByRole("button", { name: "Continue" }).click();
    await captureOnboardingEvidence(onboardingMobilePage, "10-slide-5-config-mobile-390x844");
    const mobileTaskLifeInfo = onboardingMobilePage.locator('#onboarding-panel-5 summary[aria-label="About task life"]');
    await mobileTaskLifeInfo.click();
    assert.equal(await onboardingMobilePage.getByRole("tooltip").isVisible(), true);
    await captureOnboardingEvidence(onboardingMobilePage, "10b-slide-5-task-life-tooltip-mobile-390x844");
    await mobileTaskLifeInfo.click();
    const mobileGeometry = await onboardingMobilePage.locator("#onboarding-dialog").evaluate((dialog) => {
      const rect = (element) => { const value = element.getBoundingClientRect(); return { left: value.left, top: value.top, right: value.right, bottom: value.bottom, width: value.width, height: value.height }; };
      const primary = rect(document.querySelector("#onboarding-primary"));
      const back = rect(document.querySelector("#onboarding-back"));
      const panel = document.querySelector("#onboarding-panel-5");
      const heading = rect(panel.querySelector("h2"));
      const configuration = document.querySelector("#onboarding-configuration");
      const body = document.querySelector("#onboarding-dialog > .onboarding-shell > .onboarding-panels");
      const controls = [...dialog.querySelectorAll("button")].filter((control) => !control.hidden && getComputedStyle(control).display !== "none" && control.getClientRects().length).map(rect);
      const configControls = [...configuration.querySelectorAll("input,select,summary,button")].filter((control) => !control.hidden && getComputedStyle(control).display !== "none" && control.getClientRects().length).map((control) => rect(control.matches('input[type="checkbox"]') ? control.closest(".settings-switch,.toggle-row") : control.matches('input[type="radio"]') ? control.closest("label") : control));
      return { dialog: rect(dialog), primary, back, heading, controls, configControls, panel: { scrollWidth: panel.scrollWidth, clientWidth: panel.clientWidth, overflowY: getComputedStyle(panel).overflowY }, configuration: { scrollWidth: configuration.scrollWidth, clientWidth: configuration.clientWidth, overflowY: getComputedStyle(configuration).overflowY }, body: { scrollHeight: body.scrollHeight, clientHeight: body.clientHeight, overflowY: getComputedStyle(body).overflowY }, viewport: { width: innerWidth, height: innerHeight }, documentWidth: document.documentElement.scrollWidth };
    });
    assert.ok(Math.abs(mobileGeometry.dialog.width - 390) <= 1 && Math.abs(mobileGeometry.dialog.height - 844) <= 1);
    assert.ok(mobileGeometry.controls.every((control) => control.width >= 44 && control.height >= 44));
    assert.ok(mobileGeometry.panel.scrollWidth <= mobileGeometry.panel.clientWidth + 1);
    assert.equal(mobileGeometry.panel.overflowY, "visible");
    assert.equal(mobileGeometry.configuration.overflowY, "visible");
    assert.equal(mobileGeometry.body.overflowY, "auto");
    assert.ok(mobileGeometry.configuration.scrollWidth <= mobileGeometry.configuration.clientWidth + 1);
    assert.ok(mobileGeometry.body.scrollHeight >= mobileGeometry.body.clientHeight);
    assert.ok(
      mobileGeometry.heading.top >= mobileGeometry.back.bottom + 8
      || mobileGeometry.back.top >= mobileGeometry.heading.bottom + 8
      || mobileGeometry.heading.left >= mobileGeometry.back.right + 8
      || mobileGeometry.back.left >= mobileGeometry.heading.right + 8,
      JSON.stringify({ back: mobileGeometry.back, heading: mobileGeometry.heading }),
    );
    assert.ok(mobileGeometry.configControls.every((control) => control.width >= 44 && control.height >= 44), JSON.stringify(mobileGeometry.configControls));
    assert.ok(mobileGeometry.documentWidth <= mobileGeometry.viewport.width);
    assert.equal(await onboardingMobilePage.locator("#onboarding-panel-5 .onboarding-config-advanced").count(), 0);
    assert.equal(await onboardingMobilePage.getByRole("button", { name: "Advanced settings" }).isVisible(), true);
    await onboardingMobilePage.getByRole("button", { name: "Advanced settings" }).click();
    await onboardingMobilePage.waitForFunction(() => location.hash === "#settings-advanced" && document.activeElement?.id === "settings-edit-config");
    assert.ok(await onboardingMobilePage.locator("#settings-edit-config").evaluate((button) => {
      const rect = button.getBoundingClientRect();
      return rect.top >= 0 && rect.bottom <= innerHeight && document.documentElement.scrollWidth <= innerWidth;
    }));
    if (evidenceDir) await onboardingMobilePage.screenshot({ path: path.join(evidenceDir, "10c-advanced-settings-route-mobile-390x844.png"), fullPage: false, animations: "disabled" });
    assert.deepEqual(onboardingMobile.runtimeErrors, []);
    await onboardingMobilePage.close();

    const reducedMotionPage = await browser.newPage({ viewport: { width: 834, height: 1112 } });
    await reducedMotionPage.emulateMedia({ reducedMotion: "reduce" });
    const reducedMotion = await mount(reducedMotionPage, scopedFixture(), { ...overrides, keepOnboarding: true });
    await reducedMotionPage.getByRole("button", { name: "Start guided tour" }).click();
    const reducedMotionStyles = await reducedMotionPage.locator("#onboarding-dialog").evaluate((dialog) => [
      ".onboarding-panel.is-active .onboarding-artwork",
      ".onboarding-panel.is-active > h2",
      ".onboarding-panel.is-active > p",
      "#onboarding-primary",
    ].map((selector) => {
      const style = getComputedStyle(dialog.querySelector(selector));
      return { animationName: style.animationName, transform: style.transform };
    }));
    assert.ok(reducedMotionStyles.every((item) => item.animationName === "none" && item.transform === "none"));
    assert.deepEqual(reducedMotion.runtimeErrors, []);
    await reducedMotionPage.close();

    let releaseConfigPost;
    const pendingConfigControl = { failPost: false, feed: structuredClone(fixture.config), deferredPost: new Promise((resolve) => { releaseConfigPost = resolve; }) };
    const pendingPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const pending = await mount(pendingPage, scopedFixture(), { ...overrides, keepOnboarding: true, configControl: pendingConfigControl });
    await pendingPage.getByRole("button", { name: "Start guided tour" }).click();
    for (let step = 0; step < 3; step += 1) await pendingPage.getByRole("button", { name: "Continue" }).click();
    const pendingFastMode = pendingPage.locator("#onboarding-panel-5").getByLabel("Fast", { exact: true });
    await pendingFastMode.focus();
    const pendingRequest = pendingPage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "POST");
    await pendingFastMode.evaluate((input) => input.click());
    await pendingRequest;
    await pendingPage.waitForFunction(() => document.activeElement?.id === "onboarding-config-status");
    assert.equal(await pendingPage.getByRole("button", { name: "Start using SWARM" }).isDisabled(), true);
    assert.equal(await pendingPage.getByRole("button", { name: "Advanced settings" }).isDisabled(), true);
    assert.equal(await pendingPage.locator("#onboarding-config-status").textContent().then((text) => /Saving/.test(text)), true);
    assert.equal(await pendingPage.locator("#onboarding-panel-5").getByLabel("Fast", { exact: true }).isDisabled(), true);
    await pendingPage.locator("#onboarding-panel-5").getByLabel("Fast", { exact: true }).evaluate((input) => input.click());
    assert.equal(await pendingPage.locator("#onboarding-panel-5").getByLabel("Fast", { exact: true }).isChecked(), true);
    assert.equal(pending.configRequests.length, 1);
    assertConfigWriteEnvelope(pending.configRequests[0], { scope: { type: "global" }, expectedRevision: "global-revision-1", values: { "execution.fast_mode": true } });
    await pendingPage.keyboard.press("Escape");
    assert.equal(await pendingPage.locator("#onboarding-dialog").isVisible(), true);
    assert.equal(await pendingPage.evaluate(() => localStorage.getItem("swarm.onboarding.v2.seen")), null);
    assert.equal(await pendingPage.locator("#onboarding-config-status").textContent().then((text) => /Saving/.test(text)), true);
    const pendingTaskLifeInfo = pendingPage.locator('#onboarding-panel-5 summary[aria-label="About task life"]');
    await pendingTaskLifeInfo.focus();
    await pendingPage.evaluate(() => renderOnboarding());
    await pendingPage.waitForFunction(() => document.activeElement?.matches('#onboarding-panel-5 summary[aria-label="About task life"]'));
    releaseConfigPost();
    pendingConfigControl.deferredPost = null;
    await pendingPage.getByRole("button", { name: "Start using SWARM" }).waitFor({ state: "visible" });
    await pendingPage.waitForFunction(() => !document.querySelector("#onboarding-primary")?.disabled);
    assert.equal(await pendingPage.evaluate(() => document.activeElement?.dataset.configKey), "execution.fast_mode");
    assert.equal(pending.configRequests.length, 1);
    assert.deepEqual(pending.runtimeErrors, []);
    await pendingPage.close();

    let releaseFirstConfigPost;
    let releaseSecondConfigPost;
    const serialConfigControl = {
      failPost: false,
      feed: structuredClone(fixture.config),
      deferredPosts: [
        new Promise((resolve) => { releaseFirstConfigPost = resolve; }),
        new Promise((resolve) => { releaseSecondConfigPost = resolve; }),
      ],
    };
    const serialPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const serial = await mount(serialPage, scopedFixture(), { ...overrides, keepOnboarding: true, configControl: serialConfigControl });
    await serialPage.getByRole("button", { name: "Start guided tour" }).click();
    for (let step = 0; step < 3; step += 1) await serialPage.getByRole("button", { name: "Continue" }).click();
    const firstSerialRequest = serialPage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "POST");
    await serialPage.locator('#onboarding-panel-5 label:has([data-onboarding-control="speed-fast"])').click();
    await firstSerialRequest;
    await serialPage.locator("#onboarding-panel-5").getByLabel("Auto mode").click();
    await serialPage.waitForTimeout(100);
    assert.equal(serial.configRequests.length, 1);
    assert.equal(configRequestValue(serial.configRequests[0], "execution.fast_mode"), true);
    const secondSerialRequest = serialPage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "POST" && configRequestValue(request.postDataJSON(), "automation.mode") === "manual");
    releaseFirstConfigPost();
    await secondSerialRequest;
    releaseSecondConfigPost();
    await serialPage.waitForFunction(() => !document.querySelector("#onboarding-primary")?.disabled);
    assert.equal(serial.configRequests.length, 2);
    assert.deepEqual(serial.configRequests.map((payload) => configRequestValue(payload, "automation.mode")), ["standard", "manual"]);
    assert.equal(serial.configRequests[1].expected_revision, "global-revision-1-write-1");
    assert.equal(await serialPage.locator("#onboarding-panel-5").getByLabel("Fast", { exact: true }).isChecked(), true);
    assert.equal(await serialPage.locator("#onboarding-panel-5").getByLabel("Auto mode").isChecked(), false);
    assert.deepEqual(serial.runtimeErrors, []);
    await serialPage.close();

    const taskLifeConfig = structuredClone(fixture.config);
    taskLifeConfig.editable = [...taskLifeConfig.editable, "lifecycle.task_lifetime_hours"];
    taskLifeConfig.settings.lifecycle.task_lifetime_hours = 4;
    const taskLifeControl = { failPost: false, feed: taskLifeConfig, deferredPost: null };
    const taskLifePage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const taskLifeRuntime = await mount(taskLifePage, scopedFixture(), { ...overrides, keepOnboarding: true, configControl: taskLifeControl });
    await taskLifePage.getByRole("button", { name: "Start guided tour" }).click();
    for (let step = 0; step < 3; step += 1) await taskLifePage.getByRole("button", { name: "Continue" }).click();
    const enabledTaskLife = taskLifePage.getByRole("slider", { name: "Task life" });
    assert.equal(await enabledTaskLife.isEnabled(), true);
    assert.equal(await enabledTaskLife.inputValue(), "2");
    assert.equal(await enabledTaskLife.getAttribute("aria-valuetext"), "Balanced — 4 hours");
    await enabledTaskLife.focus();
    const taskLifeRequest = taskLifePage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "POST");
    await taskLifePage.keyboard.press("ArrowRight");
    await taskLifeRequest;
    await taskLifePage.waitForFunction(() => document.querySelector('#onboarding-task-life')?.getAttribute("aria-valuetext") === "Between Balanced and Long — 24 hours");
    assert.equal(taskLifeRuntime.configRequests.length, 1);
    assert.equal(configRequestValue(taskLifeRuntime.configRequests[0], "lifecycle.task_lifetime_hours"), 24);
    assert.equal(await taskLifePage.evaluate(() => document.activeElement?.id), "onboarding-task-life");
    assert.deepEqual(taskLifeRuntime.runtimeErrors, []);
    await taskLifePage.close();

    let releaseWriteBeforeRead;
    const writeBeforeReadControl = {
      failPost: false,
      feed: structuredClone(fixture.config),
      deferredPost: new Promise((resolve) => { releaseWriteBeforeRead = resolve; }),
      getSnapshots: [],
    };
    const writeBeforeReadPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const writeBeforeRead = await mount(writeBeforeReadPage, scopedFixture(), { ...overrides, configControl: writeBeforeReadControl });
    writeBeforeReadControl.getSnapshots.length = 0;
    const writeFirstRequest = writeBeforeReadPage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "POST");
    await writeBeforeReadPage.evaluate(() => { window.__configWriteBeforeRead = saveConfigMutation({ "execution.fast_mode": true }); });
    await writeFirstRequest;
    await writeBeforeReadPage.evaluate(() => { window.__configReadAfterWrite = readConfigState(); });
    await writeBeforeReadPage.waitForTimeout(80);
    assert.equal(writeBeforeReadControl.getSnapshots.length, 0, "a read queued behind an in-flight write must not capture the old config");
    const orderedGetRequest = writeBeforeReadPage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "GET");
    releaseWriteBeforeRead();
    writeBeforeReadControl.deferredPost = null;
    await orderedGetRequest;
    await writeBeforeReadPage.evaluate(() => Promise.all([window.__configWriteBeforeRead, window.__configReadAfterWrite]));
    assert.equal(writeBeforeReadControl.getSnapshots.length, 1);
    assert.equal(writeBeforeReadControl.getSnapshots[0].settings.execution.fast_mode, true);
    assert.equal(await writeBeforeReadPage.evaluate(() => state.config.settings.execution.fast_mode), true, "the acknowledged write survives its ordered readback");
    assert.equal(writeBeforeRead.configRequests.length, 1);
    assert.equal(configRequestValue(writeBeforeRead.configRequests[0], "execution.fast_mode"), true);
    assert.deepEqual(writeBeforeRead.runtimeErrors, []);
    await writeBeforeReadPage.close();

    let releaseStaleConfigGet;
    const readRaceControl = {
      failPost: false,
      feed: structuredClone(fixture.config),
      deferredGet: null,
    };
    const readRacePage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const readRace = await mount(readRacePage, scopedFixture(), { ...overrides, configControl: readRaceControl });
    readRaceControl.deferredGet = new Promise((resolve) => { releaseStaleConfigGet = resolve; });
    const staleGetRequest = readRacePage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "GET");
    const staleRefresh = readRacePage.evaluate(() => refreshOverview(false));
    await staleGetRequest;
    const newerPostRequest = readRacePage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "POST");
    await readRacePage.evaluate(() => saveConfigMutation({ "execution.fast_mode": true }));
    await newerPostRequest;
    assert.equal(await readRacePage.evaluate(() => state.config.settings.execution.fast_mode), true);
    releaseStaleConfigGet();
    readRaceControl.deferredGet = null;
    await staleRefresh;
    assert.equal(await readRacePage.evaluate(() => state.config.settings.execution.fast_mode), true, "a GET started before an acknowledged POST cannot overwrite its config");
    assert.equal(readRace.configRequests.length, 1);
    assert.equal(configRequestValue(readRace.configRequests[0], "execution.fast_mode"), true);
    assert.deepEqual(readRace.runtimeErrors, []);
    await readRacePage.close();

    let releaseFailedWriteReadback;
    const failedReadbackRaceControl = {
      failPost: false,
      feed: {
        ...structuredClone(fixture.config),
        editable: [...fixture.config.editable, "chat_relay.enabled"],
        settings: { ...structuredClone(fixture.config.settings), chat_relay: { enabled: false } },
      },
      deferredGet: null,
    };
    const failedReadbackRacePage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const failedReadbackRace = await mount(failedReadbackRacePage, scopedFixture(), { ...overrides, configControl: failedReadbackRaceControl });
    await failedReadbackRacePage.evaluate(() => setView("settings"));
    await failedReadbackRacePage.evaluate(() => document.body.insertAdjacentHTML("beforeend", chatRelaySettingsMarkup()));
     await failedReadbackRacePage.locator("#chat-relay-enabled").last().waitFor({ state: "visible" });
    failedReadbackRaceControl.failPost = true;
    failedReadbackRaceControl.deferredGet = new Promise((resolve) => { releaseFailedWriteReadback = resolve; });
    const failedRelayPost = failedReadbackRacePage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "POST");
    const delayedReadback = failedReadbackRacePage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "GET");
     await failedReadbackRacePage.locator("#chat-relay-enabled").last().click();
    await failedRelayPost;
    await delayedReadback;
    failedReadbackRaceControl.failPost = false;
    const replacementPost = failedReadbackRacePage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "POST");
    await failedReadbackRacePage.evaluate(() => saveConfigMutation({ "execution.usage_saver": true }));
    await replacementPost;
    assert.equal(await failedReadbackRacePage.evaluate(() => state.config.settings.execution.usage_saver), true);
    releaseFailedWriteReadback();
    failedReadbackRaceControl.deferredGet = null;
    await failedReadbackRacePage.waitForFunction(() => state.chatRelaySaving === false);
    assert.equal(await failedReadbackRacePage.evaluate(() => state.config.settings.execution.usage_saver), true, "a failed-write readback cannot overwrite a later acknowledged config");
    assert.equal(await failedReadbackRacePage.evaluate(() => state.configStatus), "current");
    assert.match(await failedReadbackRacePage.evaluate(() => state.configError), /setting acknowledgement unavailable[\s\S]*Current settings changed before the reload completed/);
    assert.equal(failedReadbackRace.configRequests.length, 2);
    assert.equal(configRequestValue(failedReadbackRace.configRequests[0], "chat_relay.enabled"), true);
    assert.equal(configRequestValue(failedReadbackRace.configRequests[1], "execution.usage_saver"), true);
    assert.equal(failedReadbackRace.runtimeErrors.length, 1);
    assert.match(failedReadbackRace.runtimeErrors[0], /503 \(Service Unavailable\)/);
    await failedReadbackRacePage.close();

    const failedConfigControl = { failPost: true, feed: structuredClone(fixture.config), deferredPost: null };
    const failedPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const failed = await mount(failedPage, scopedFixture(), { ...overrides, keepOnboarding: true, configControl: failedConfigControl });
    await failedPage.getByRole("button", { name: "Start guided tour" }).click();
    for (let step = 0; step < 3; step += 1) await failedPage.getByRole("button", { name: "Continue" }).click();
    await failedPage.locator('#onboarding-panel-5 label:has([data-onboarding-control="speed-fast"])').click();
    await failedPage.getByRole("button", { name: "Retry" }).waitFor({ state: "visible" });
    assert.equal(await failedPage.getByRole("button", { name: "Start using SWARM" }).isDisabled(), true);
    assert.equal(await failedPage.getByRole("button", { name: "Advanced settings" }).isDisabled(), true);
    assert.equal(await failedPage.locator("#onboarding-dialog").isVisible(), true);
    assert.equal(await failedPage.evaluate(() => localStorage.getItem("swarm.onboarding.v2.seen")), null);
    assert.equal(await failedPage.locator("#onboarding-panel-5").getByLabel("Fast", { exact: true }).isChecked(), true);
    await failedPage.getByRole("button", { name: "Retry" }).focus();
    await failedPage.keyboard.press("Escape");
    assert.equal(await failedPage.locator("#onboarding-dialog").isVisible(), true);
    assert.equal(await failedPage.getByRole("button", { name: "Retry" }).isVisible(), true);
    assert.equal(await failedPage.evaluate(() => localStorage.getItem("swarm.onboarding.v2.seen")), null);
    let releaseRetryPost;
    failedConfigControl.deferredPost = new Promise((resolve) => { releaseRetryPost = resolve; });
    failedConfigControl.failPost = false;
    const retryRequest = failedPage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "POST");
    await failedPage.getByRole("button", { name: "Retry" }).click();
    await retryRequest;
    await failedPage.waitForFunction(() => document.activeElement?.id === "onboarding-config-status");
    assert.match(await failedPage.locator("#onboarding-config-status").textContent(), /Saving/);
    releaseRetryPost();
    failedConfigControl.deferredPost = null;
    await failedPage.waitForFunction(() => !document.querySelector("#onboarding-primary")?.disabled);
    assert.equal(await failedPage.evaluate(() => document.activeElement?.id), "onboarding-config-status");
    assert.equal(failed.configRequests.length, 2);
    assert.equal(configRequestValue(failed.configRequests[0], "execution.fast_mode"), true);
    assert.equal(configRequestValue(failed.configRequests[1], "execution.fast_mode"), true);
    await failedPage.getByRole("button", { name: "Start using SWARM" }).click();
    assert.equal(await failedPage.locator("#onboarding-dialog").isVisible(), false);
    assert.equal(await failedPage.evaluate(() => localStorage.getItem("swarm.onboarding.v2.seen")), "1");
    assert.equal(failed.runtimeErrors.filter((message) => /503 \(Service Unavailable\)/.test(message)).length, 1);
    assert.deepEqual(failed.runtimeErrors.filter((message) => !/503 \(Service Unavailable\)/.test(message)), []);
    await failedPage.close();

    const projectWriteCursor = { event_seq: 31, event_digest: "c".repeat(64) };
    const projectWriteFeed = configDescriptorFixture();
    projectWriteFeed.scope = { type: "project", project_id: "project:fixture", accepted_cursor: projectWriteCursor };
    projectWriteFeed.revision = "project-config-revision-7";
    const projectWriteControl = { failPost: false, feed: projectWriteFeed };
    const projectWritePage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const projectWrite = await mount(projectWritePage, scopedFixture(), { ...overrides, configControl: projectWriteControl });
    const projectSaved = await projectWritePage.evaluate(() => {
      state.settingsDraft.set("execution.fast_mode", true);
      return saveSettingsDraft();
    });
    assert.equal(projectSaved, true);
    assert.equal(projectWrite.configRequests.length, 1);
    assertConfigWriteEnvelope(projectWrite.configRequests[0], {
      scope: { type: "project", project_id: "project:fixture", accepted_cursor: projectWriteCursor },
      expectedRevision: "project-config-revision-7",
      values: { "execution.fast_mode": true },
    });
    assert.equal(projectWriteControl.receipts[0].action, "config_update");
    assert.equal(projectWriteControl.receipts[0].replayed, false);
    assert.deepEqual(projectWriteControl.receipts[0].scope, { type: "project", project_id: "project:fixture", accepted_cursor: projectWriteCursor });
    assert.equal(await projectWritePage.evaluate(() => state.config.revision), "project-config-revision-7-write-1");
    assert.equal(await projectWritePage.evaluate(() => state.settingsDraft.size), 0);
    assert.equal(await projectWritePage.evaluate(() => state.settingsSaveMessage), "Saved");
    assert.deepEqual(projectWrite.runtimeErrors, []);
    await projectWritePage.close();

    const ambiguousWriteControl = { failPost: false, feed: configDescriptorFixture(), ambiguousAfterApply: true, restartAfterAmbiguous: true };
    const ambiguousWritePage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const ambiguousWrite = await mount(ambiguousWritePage, scopedFixture(), { ...overrides, configControl: ambiguousWriteControl });
    const ambiguousFresh = await ambiguousWritePage.evaluate(() => {
      state.settingsDraft.set("execution.fast_mode", true);
      return saveSettingsDraft();
    });
    assert.equal(ambiguousFresh, false);
    assert.match(await ambiguousWritePage.evaluate(() => state.settingsSaveError), /could not confirm the save[\s\S]*reuse this exact operation/);
    const uncertainRequest = structuredClone(ambiguousWrite.configRequests[0]);
    assert.deepEqual(await ambiguousWritePage.evaluate(() => [...state.settingsDraft]), [["execution.fast_mode", true]]);
    assert.equal(await ambiguousWritePage.evaluate(() => state.settingsSaveMessage), "Changes not saved");
    const ambiguousReplay = await ambiguousWritePage.evaluate(() => saveSettingsDraft());
    assert.equal(ambiguousReplay, true);
    assert.equal(ambiguousWrite.configRequests.length, 2);
    assert.equal(ambiguousWrite.configRequests[1].operation_id, uncertainRequest.operation_id);
    assert.equal(ambiguousWriteControl.writeOperations.size, 1, "an uncertain replay must not apply the logical write twice");
    assert.equal(ambiguousWriteControl.restartCount, 1, "the replay fixture must survive a simulated server restart");
    assert.equal(ambiguousWriteControl.receipts.at(-1).action, "config_update");
    assert.equal(ambiguousWriteControl.receipts.at(-1).replayed, true);
    assert.deepEqual(ambiguousWriteControl.receipts.at(-1).scope, { type: "global" });
    assert.equal(await ambiguousWritePage.evaluate(() => state.config.revision), "global-revision-1-write-1");
    assert.equal(await ambiguousWritePage.evaluate(() => state.settingsDraft.size), 0);
    assert.equal(await ambiguousWritePage.evaluate(() => state.settingsSaveMessage), "Saved");
    assert.equal(ambiguousWrite.runtimeErrors.filter((message) => /ERR_FAILED/.test(message)).length, 1);
    await ambiguousWritePage.close();

    const conflictWriteControl = { failPost: "conflict", feed: configDescriptorFixture() };
    const conflictWritePage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const conflictWrite = await mount(conflictWritePage, scopedFixture(), { ...overrides, configControl: conflictWriteControl });
    const conflictSaved = await conflictWritePage.evaluate(() => {
      state.settingsDraft.set("execution.fast_mode", true);
      return saveSettingsDraft();
    });
    assert.equal(conflictSaved, false);
    assert.match(await conflictWritePage.evaluate(() => state.settingsSaveError), /changed elsewhere[\s\S]*unsaved changes are preserved/);
    assert.deepEqual(await conflictWritePage.evaluate(() => [...state.settingsDraft]), [["execution.fast_mode", true]]);
    assert.equal(await conflictWritePage.evaluate(() => state.settingsSaveMessage), "Changes not saved");
    const conflictWriteOperationId = conflictWrite.configRequests[0].operation_id;
    conflictWriteControl.failPost = false;
    assert.equal(await conflictWritePage.evaluate(() => saveSettingsDraft()), true);
    assert.notEqual(conflictWrite.configRequests[1].operation_id, conflictWriteOperationId, "a confirmed conflict requires a new operation identity");
    assert.equal(await conflictWritePage.evaluate(() => state.settingsDraft.size), 0);
    await conflictWritePage.close();

    const changedIdentityControl = { failPost: "connection", feed: configDescriptorFixture() };
    const changedIdentityPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const changedIdentity = await mount(changedIdentityPage, scopedFixture(), { ...overrides, configControl: changedIdentityControl });
    await changedIdentityPage.evaluate(() => saveConfigMutation({ "execution.fast_mode": true }).catch(() => undefined));
    const priorIdentity = changedIdentity.configRequests[0].operation_id;
    changedIdentityControl.failPost = false;
    await changedIdentityPage.evaluate(() => saveConfigMutation({ "execution.usage_saver": true }));
    assert.notEqual(changedIdentity.configRequests[1].operation_id, priorIdentity, "changed config text must not reuse an uncertain operation identity");
    await changedIdentityPage.close();

    const exhaustedRetryControl = { failPost: "connection", feed: configDescriptorFixture() };
    const exhaustedRetryPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const exhaustedRetry = await mount(exhaustedRetryPage, scopedFixture(), { ...overrides, configControl: exhaustedRetryControl });
    await exhaustedRetryPage.evaluate(() => { state.settingsDraft.set("execution.fast_mode", true); });
    assert.equal(await exhaustedRetryPage.evaluate(() => saveSettingsDraft()), false);
    assert.equal(await exhaustedRetryPage.evaluate(() => saveSettingsDraft()), false);
    assert.equal(exhaustedRetry.configRequests.length, 2);
    assert.equal(exhaustedRetry.configRequests[0].operation_id, exhaustedRetry.configRequests[1].operation_id);
    assert.equal(await exhaustedRetryPage.evaluate(() => saveSettingsDraft()), false);
    assert.equal(exhaustedRetry.configRequests.length, 2, "an exhausted uncertain write must not send a third request");
    assert.equal(await exhaustedRetryPage.evaluate(() => saveSettingsDraft()), false);
    assert.equal(exhaustedRetry.configRequests.length, 2, "the exhausted identity must remain blocked on later attempts");
    assert.match(await exhaustedRetryPage.evaluate(() => state.settingsSaveError), /after one retry[\s\S]*unsaved changes are preserved/);
    assert.deepEqual(await exhaustedRetryPage.evaluate(() => [...state.settingsDraft]), [["execution.fast_mode", true]]);
    assert.notEqual(await exhaustedRetryPage.evaluate(() => state.settingsSaveMessage), "Saved");
    assert.equal(exhaustedRetry.runtimeErrors.filter((message) => /ERR_FAILED/.test(message)).length, 2);
    await exhaustedRetryPage.close();

    const invalidAcknowledgements = [
      ["operation id", (result) => { result.mutation_receipt.operation_id = "console-config-write-00000000000000000000000000000000"; }],
      ["expected revision", (result) => { result.mutation_receipt.expected_revision = "other-revision"; }],
      ["receipt scope cursor", (result) => { result.mutation_receipt.scope.accepted_cursor.event_seq += 1; }],
      ["projection scope cursor", (result) => { result.scope.accepted_cursor.event_seq += 1; }],
      ["action", (result) => { result.mutation_receipt.action = "config_reset"; }],
      ["replay marker", (result) => { result.mutation_receipt.replayed = "false"; }],
      ["accepted", (result) => { result.mutation_receipt.accepted = false; }],
      ["acknowledgement", (result) => { result.mutation_receipt.acknowledged = false; }],
      ["new revision", (result) => { result.mutation_receipt.new_revision = "other-new-revision"; }],
    ];
    for (const [label, mutate] of invalidAcknowledgements) {
      const mismatchFeed = configDescriptorFixture();
      mismatchFeed.scope = { type: "project", project_id: "project:fixture", accepted_cursor: structuredClone(projectWriteCursor) };
      mismatchFeed.revision = "project-config-revision-7";
      const mismatchControl = { failPost: false, feed: mismatchFeed, responseMutations: [(result) => { mutate(result); return result; }] };
      const mismatchPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
      const mismatchRuntime = await mount(mismatchPage, scopedFixture(), { ...overrides, configControl: mismatchControl });
      const mismatchSaved = await mismatchPage.evaluate(() => {
        state.settingsDraft.set("execution.fast_mode", true);
        return saveSettingsDraft();
      });
      assert.equal(mismatchSaved, false, label);
      assert.match(await mismatchPage.evaluate(() => state.settingsSaveError), /invalid config acknowledgement/, label);
      assert.equal(await mismatchPage.evaluate(() => state.config.revision), "project-config-revision-7", `${label} must not apply`);
      assert.deepEqual(await mismatchPage.evaluate(() => [...state.settingsDraft]), [["execution.fast_mode", true]], `${label} must preserve the draft`);
      assert.notEqual(await mismatchPage.evaluate(() => state.settingsSaveMessage), "Saved", `${label} must not report success`);
      if (label === "operation id") {
        const mismatchedRequestId = mismatchRuntime.configRequests[0].operation_id;
        assert.equal(await mismatchPage.evaluate(() => saveSettingsDraft()), true);
        assert.equal(mismatchRuntime.configRequests[1].operation_id, mismatchedRequestId, "a valid exact replay keeps the uncertain request identity");
        assert.equal(await mismatchPage.evaluate(() => state.config.revision), "project-config-revision-7-write-1");
      }
      assert.deepEqual(mismatchRuntime.runtimeErrors, []);
      await mismatchPage.close();
    }

    let releaseStaleWrite;
    const staleWriteControl = { failPost: false, feed: configDescriptorFixture(), deferredPost: new Promise((resolve) => { releaseStaleWrite = resolve; }) };
    const staleWritePage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const staleWrite = await mount(staleWritePage, scopedFixture(), { ...overrides, configControl: staleWriteControl });
    const staleWriteRequest = staleWritePage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "POST");
    await staleWritePage.evaluate(() => {
      state.settingsDraft.set("execution.fast_mode", true);
      window.__staleConfigWrite = saveSettingsDraft();
    });
    await staleWriteRequest;
    await staleWritePage.evaluate(() => {
      state.config = { ...state.config, scope: { type: "project", project_id: "project:other", accepted_cursor: { event_seq: 44, event_digest: "d".repeat(64) } }, revision: "other-revision" };
    });
    releaseStaleWrite();
    const staleWriteResult = await staleWritePage.evaluate(() => window.__staleConfigWrite);
    assert.equal(staleWriteResult, false);
    assert.equal(await staleWritePage.evaluate(() => state.config.revision), "other-revision");
    assert.deepEqual(await staleWritePage.evaluate(() => [...state.settingsDraft]), [["execution.fast_mode", true]]);
    assert.equal(await staleWritePage.evaluate(() => state.settingsSaveMessage), "Changes not saved");
    assert.match(await staleWritePage.evaluate(() => state.settingsSaveError), /scope changed[\s\S]*unsaved changes are preserved/);
    assert.deepEqual(staleWrite.runtimeErrors, []);
    await staleWritePage.close();

    const stateViewports = [
      { name: "desktop", width: 1440, height: 1000 },
      { name: "tablet", width: 834, height: 1112 },
      { name: "mobile", width: 390, height: 844 },
    ];
    for (const viewport of stateViewports) {
      const statePage = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
      const connection = { offline: true };
      const mounted = await mount(statePage, scopedFixture(), { connection, waitForConnectionState: true });
      const offlineImage = statePage.locator("#connection-state img");
      await offlineImage.evaluate(async (image) => { if (!image.complete) await new Promise((resolve, reject) => { image.addEventListener("load", resolve, { once: true }); image.addEventListener("error", reject, { once: true }); }); await image.decode(); });
      assert.equal(await statePage.getByRole("heading", { name: "Connection lost" }).count(), 1);
      assert.equal(await statePage.locator("#sync-time").textContent(), "Offline");
      assert.equal(await offlineImage.getAttribute("alt"), "");
      assert.match(await offlineImage.evaluate((image) => image.currentSrc), /\/assets\/swarm-offline-disconnected\.webp$/);
      assert.equal(await statePage.locator("#connection-state [aria-hidden=true]").count(), 1);
      const offlineGeometry = await statePage.locator("#connection-state").evaluate((surface) => {
        const rect = surface.getBoundingClientRect();
        const image = surface.querySelector("img");
        const button = surface.querySelector("button").getBoundingClientRect();
        return { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom, viewportWidth: innerWidth, viewportHeight: innerHeight, documentWidth: document.documentElement.scrollWidth, naturalWidth: image.naturalWidth, naturalHeight: image.naturalHeight, buttonHeight: button.height };
      });
      assert.ok(offlineGeometry.left >= 0 && offlineGeometry.top >= 0 && offlineGeometry.right <= offlineGeometry.viewportWidth && offlineGeometry.bottom <= offlineGeometry.viewportHeight, JSON.stringify(offlineGeometry));
      assert.ok(offlineGeometry.documentWidth <= offlineGeometry.viewportWidth, JSON.stringify(offlineGeometry));
      assert.deepEqual([offlineGeometry.naturalWidth, offlineGeometry.naturalHeight], [1024, 640]);
      assert.ok(offlineGeometry.buttonHeight >= 44, JSON.stringify(offlineGeometry));
      if (evidenceDir) await statePage.screenshot({ path: path.join(evidenceDir, `state-offline-${viewport.name}-${viewport.width}x${viewport.height}.png`), fullPage: false, animations: "disabled" });

      connection.offline = false;
      await statePage.evaluate(() => localStorage.setItem("swarm.onboarding.v2.seen", "1"));
      await statePage.getByRole("button", { name: "Retry connection" }).click();
      await statePage.locator("#overview-content").waitFor({ state: "visible" });
      await statePage.waitForFunction(() => document.activeElement?.id === "notifications");
      assert.equal(await statePage.locator("#connection-state").isVisible(), false);
      assert.match(await statePage.locator("#sync-time").textContent(), /^Live/);
      assert.ok(mounted.requests.filter((request) => request === "/api/bootstrap").length >= 2);

      await statePage.evaluate(() => showError("The latest project snapshot could not be loaded."));
      const errorSurface = statePage.locator("#error-surface");
      await errorSurface.waitFor({ state: "visible" });
      const errorImage = errorSurface.locator("img");
      assert.equal(await errorImage.getAttribute("alt"), "");
      await statePage.waitForFunction((image) => image.complete && image.naturalWidth > 0 && image.currentSrc.length > 0, await errorImage.elementHandle(), { timeout: 5000 });
      assert.match(await errorImage.evaluate((image) => image.currentSrc), /\/assets\/swarm-state-mascot-concerned\.webp$/);
      assert.equal(await errorSurface.locator('[data-state-variant="failed"]').count(), 1);
      const errorGeometry = await errorSurface.evaluate((surface) => {
        const rect = surface.getBoundingClientRect();
        const button = surface.querySelector("button").getBoundingClientRect();
        return { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom, viewportWidth: innerWidth, viewportHeight: innerHeight, documentWidth: document.documentElement.scrollWidth, buttonHeight: button.height };
      });
      assert.ok(errorGeometry.left >= 0 && errorGeometry.top >= 0 && errorGeometry.right <= errorGeometry.viewportWidth && errorGeometry.bottom <= errorGeometry.viewportHeight, JSON.stringify(errorGeometry));
      assert.ok(errorGeometry.documentWidth <= errorGeometry.viewportWidth && errorGeometry.buttonHeight >= 44, JSON.stringify(errorGeometry));
      if (evidenceDir) await statePage.screenshot({ path: path.join(evidenceDir, `state-failed-${viewport.name}-${viewport.width}x${viewport.height}.png`), fullPage: false, animations: "disabled" });
      await statePage.getByRole("button", { name: "Refresh SWARM" }).click();
      await errorSurface.waitFor({ state: "hidden" });
      await statePage.waitForFunction(() => document.activeElement?.id === "notifications");

      await statePage.evaluate(() => {
        setView("review");
        state.proofCollections.set(proofCollectionKey(), []);
        state.proofStatuses.set(proofCollectionKey(), "idle");
        renderReview();
      });
      const reviewEmpty = statePage.locator("#review-list .state-message");
      await reviewEmpty.waitFor({ state: "visible" });
      assert.equal(await reviewEmpty.locator('[data-state-variant="empty"]').count(), 1);
      assert.match(await reviewEmpty.textContent(), /No proof yet[\s\S]*Accepted proof will appear here/);
      if (evidenceDir) await statePage.screenshot({ path: path.join(evidenceDir, `state-empty-${viewport.name}-${viewport.width}x${viewport.height}.png`), fullPage: false, animations: "disabled" });

      await statePage.evaluate(() => { state.proofStatuses.set(proofCollectionKey(), "unavailable"); renderReview(); });
      const reviewRecovery = statePage.locator("#review-list .state-message");
      assert.equal(await reviewRecovery.locator('[data-state-variant="recovery"]').count(), 1);
      assert.match(await reviewRecovery.textContent(), /Proof is temporarily unavailable[\s\S]*Proof will appear here when SWARM receives it again\./);
      await statePage.emulateMedia({ reducedMotion: "reduce" });
      await statePage.waitForFunction(() => document.querySelector("#review-list .state-illustration")?.getAnimations({ subtree: true }).length === 0);
      assert.equal(await statePage.locator("#review-list .state-illustration").evaluate((surface) => surface.getAnimations({ subtree: true }).length), 0);
      const recoveryGeometry = await reviewRecovery.evaluate((surface) => {
        const rect = surface.getBoundingClientRect();
        return { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom, viewportWidth: innerWidth, viewportHeight: innerHeight, documentWidth: document.documentElement.scrollWidth };
      });
      assert.ok(recoveryGeometry.left >= 0 && recoveryGeometry.right <= recoveryGeometry.viewportWidth && recoveryGeometry.documentWidth <= recoveryGeometry.viewportWidth, JSON.stringify(recoveryGeometry));
      if (evidenceDir) await statePage.screenshot({ path: path.join(evidenceDir, `state-recovery-${viewport.name}-${viewport.width}x${viewport.height}.png`), fullPage: false, animations: "disabled" });
      await statePage.close();
    }

    let releaseStaleAssetList;
    const raceLibrary = assetLibraryFixture();
    raceLibrary.active.push(assetFixtureItem("asset-branch", "READY", { name: "Branch asset", projectId: "project:branch" }));
    const assetRaceControl = { library: raceLibrary, failGet: false, failMutation: false, deferredGets: [], operations: new Map() };
    const assetRacePage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const assetRace = await mount(assetRacePage, scopedFixture(), { ...overrides, assetControl: assetRaceControl });
    await assetRacePage.evaluate(() => setView("assets"));
    assetRaceControl.deferredGets.push(new Promise((resolve) => { releaseStaleAssetList = resolve; }));
    const staleAssetRequest = assetRacePage.waitForRequest((request) => request.url().includes("/api/assets?") && request.url().includes("project_id=project%3Afixture"));
    await assetRacePage.evaluate(() => { window.__staleAssetScope = selectProjectScope("project:fixture"); });
    await staleAssetRequest;
    const freshAssetRequest = assetRacePage.waitForRequest((request) => request.url().includes("/api/assets?") && request.url().includes("project_id=project%3Abranch"));
    await assetRacePage.evaluate(() => { window.__freshAssetScope = selectProjectScope("project:branch"); });
    await freshAssetRequest;
    await assetRacePage.evaluate(() => window.__freshAssetScope);
    releaseStaleAssetList();
    await assetRacePage.evaluate(() => window.__staleAssetScope);
    assert.equal(await assetRacePage.evaluate(() => state.view), "assets");
    assert.equal(await assetRacePage.evaluate(() => state.projectId), "project:branch");
    assert.deepEqual(await assetRacePage.evaluate(() => assetItems().map((item) => item.asset_id)), ["asset-branch"]);
    assert.deepEqual(assetRace.runtimeErrors, []);
    await assetRacePage.close();

    for (const raceCase of [
      { action: "retry", assetId: "asset-failed", projection: "active", endpoint: "/api/assets/generation/retry" },
      { action: "trash", assetId: "asset-roadmap", projection: "active", endpoint: "/api/assets/trash" },
      { action: "restore", assetId: "asset-trashed", projection: "trash", endpoint: "/api/assets/restore" },
    ]) {
      let releaseMutation;
      const raceLibrary = assetLibraryFixture();
      raceLibrary.active.push(assetFixtureItem("asset-branch", "READY", { name: "Branch asset", projectId: "project:branch" }));
      raceLibrary.trash.push(assetFixtureItem("asset-branch-trash", "TRASHED", { name: "Branch retired asset", projectId: "project:branch", revision: 2 }));
      const raceControl = { library: raceLibrary, failGet: false, failMutation: false, deferredGets: [], deferredMutations: [], operations: new Map() };
      const racePage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
      const race = await mount(racePage, scopedFixture(), { ...overrides, assetControl: raceControl });
      try {
        await racePage.evaluate(() => setView("assets"));
        await racePage.evaluate(() => selectProjectScope("project:fixture"));
        if (raceCase.projection === "trash") {
          await racePage.evaluate(async () => { state.assetProjection = "trash"; await refreshAssets(); renderAssets(); });
        }
        raceControl.deferredMutations.push(new Promise((resolve) => { releaseMutation = resolve; }));
        const postStarted = racePage.waitForRequest((request) => new URL(request.url()).pathname === raceCase.endpoint && request.method() === "POST");
        await racePage.evaluate(({ action, assetId }) => {
          const item = assetItems().find((candidate) => assetIdentity(candidate) === assetId);
          window.__assetMutationRace = mutateAsset(action, item);
        }, raceCase);
        await postStarted;
        await racePage.evaluate(() => selectProjectScope("project:branch"));
        assert.deepEqual(await racePage.evaluate(() => ({ view: state.view, projectId: state.projectId, projection: state.assetProjection })), { view: "assets", projectId: "project:branch", projection: raceCase.projection });
        releaseMutation();
        await racePage.evaluate(() => window.__assetMutationRace);
        await racePage.waitForFunction(() => state.assetMutationPending === null);
        assert.deepEqual(await racePage.evaluate(() => ({ view: state.view, projectId: state.projectId, projection: state.assetProjection, undo: state.assetUndo, error: state.assetError, items: assetItems().map((item) => item.asset_id) })), {
          view: "assets",
          projectId: "project:branch",
          projection: raceCase.projection,
          undo: null,
          error: "",
          items: raceCase.projection === "trash" ? ["asset-branch-trash"] : ["asset-branch"],
        }, `${raceCase.action} acknowledgement from project A must not overwrite project B`);
        assert.equal(race.assetRequests.at(-1).path, raceCase.endpoint);
        assert.deepEqual(race.runtimeErrors, []);
      } finally {
        releaseMutation?.();
        await racePage.close();
      }
    }

    const assetFailureControl = { library: assetLibraryFixture(), failGet: false, failMutation: true, deferredGets: [], operations: new Map() };
    const assetFailurePage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const assetFailure = await mount(assetFailurePage, scopedFixture(), { ...overrides, assetControl: assetFailureControl });
    await assetFailurePage.evaluate(() => setView("assets"));
    await assetFailurePage.getByRole("button", { name: "Open asset details for Roadmap" }).click();
    await assetFailurePage.locator("#asset-dialog").getByRole("button", { name: "Move to Trash" }).click();
    await assetFailurePage.locator("#asset-dialog").getByRole("button", { name: "Move to Trash" }).click();
    await assetFailurePage.locator("#asset-dialog").getByRole("button", { name: "Retry", exact: true }).waitFor({ state: "visible" });
    assert.equal(await assetFailurePage.evaluate(() => state.assetProjection), "active");
    assert.equal(assetFailure.assetRequests.length, 1);
    assetFailureControl.failMutation = false;
    await assetFailurePage.locator("#asset-dialog").getByRole("button", { name: "Retry", exact: true }).click();
    await assetFailurePage.waitForFunction(() => state.assetProjection === "trash");
    assert.equal(assetFailure.assetRequests.length, 2);
    assert.deepEqual(assetFailure.assetRequests[1].payload, assetFailure.assetRequests[0].payload, "ambiguous mutation retry must reuse the exact operation identity");
    assert.ok(assetFailure.runtimeErrors.every((message) => message.includes("503")), assetFailure.runtimeErrors.join(" | "));
    await assetFailurePage.close();

    const messageAckDeferred = {};
    messageAckDeferred.promise = new Promise((resolve) => { messageAckDeferred.resolve = resolve; });
    const messageControl = {
      timeoutMs: 500,
      deferredResponses: [messageAckDeferred.promise],
      responses: [
        { result_code: "ACKNOWLEDGED" },
        { result_code: "REPLAYED" },
        { result_code: "ACKNOWLEDGED", action_digest: "different" },
        { result_code: "ACKNOWLEDGED" },
        { result_code: "REPLAYED", action_digest: "different" },
        { result_code: "REPLAYED" },
        { result_code: "RESULT", action_digest: "different" },
        { result_code: "ACKNOWLEDGED" },
        { result_code: "STALE" },
        { result_code: "ACKNOWLEDGED" },
        { result_code: "ACKNOWLEDGED", result_event_digest: null },
        { type: "timeout" },
        { type: "abort" },
      ],
    };
    const messagePage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const messageRuntime = await mount(messagePage, scopedFixture(), { ...overrides, messageControl, testOrigin: "http://127.0.0.1" });
    await messagePage.evaluate(() => selectProjectScope("project:fixture"));
    await messagePage.waitForFunction(() => state.projectId === "project:fixture");
    await messagePage.locator("#message-launcher").click();
    await messagePage.locator("#message-draft").fill("Please review the selected screen.");
    await messagePage.evaluate(() => {
      state.messageAttachments = [{ artifact_id: "fixture-image-1", digest: "sha256:" + "1".repeat(64) }];
      renderMessageComposer();
    });
    assert.equal(await messagePage.getByRole("button", { name: "Send message" }).isDisabled(), false);
    await messagePage.getByRole("button", { name: "Send message" }).click();
    await messagePage.waitForFunction(() => state.messageStatus === "pending");
    assert.match(await messagePage.locator("#message-status").textContent(), /^Pending/);
    assert.equal(await messagePage.locator("#message-draft").inputValue(), "Please review the selected screen.");
    assert.deepEqual(await messagePage.evaluate(() => state.messageAttachments), [{ artifact_id: "fixture-image-1", digest: "sha256:" + "1".repeat(64) }]);
    messageAckDeferred.resolve();
    await messagePage.waitForFunction(() => state.messageStatus === "sent");
    assert.match(await messagePage.locator("#message-status").textContent(), /^Sent to /);
    assert.equal(await messagePage.locator("#message-draft").inputValue(), "");
    assert.deepEqual(await messagePage.evaluate(() => state.messageAttachments), []);
    const acknowledgedRequest = messageRuntime.messageRequests[0];
    assert.equal(acknowledgedRequest.type, "swarm.project_view_action");
    assert.equal(acknowledgedRequest.action_kind, "send_feedback");
    assert.equal(acknowledgedRequest.project_id, "project:fixture");
    assert.equal(acknowledgedRequest.manifest_id, "fixture-views");
    assert.equal(acknowledgedRequest.manifest_version, 1);
    assert.equal(acknowledgedRequest.manifest_digest, "sha256:" + "a".repeat(64));
    assert.equal(acknowledgedRequest.view_id, "overview");
    assert.equal(acknowledgedRequest.view_digest, "sha256:" + "d".repeat(64));
    assert.deepEqual(acknowledgedRequest.source_digests, ["sha256:" + "b".repeat(64), "sha256:" + "c".repeat(64)]);
    assert.deepEqual(acknowledgedRequest.observed_cursor, { stream_id: "project-ledger", project_id: "project:fixture", sequence: 42, event_id: "fixture-event-42", event_digest: "sha256:" + "e".repeat(64) });
    assert.deepEqual(acknowledgedRequest.attachments, [{ artifact_id: "fixture-image-1", digest: "sha256:" + "1".repeat(64) }]);
    assert.match(acknowledgedRequest.request_id, /^[a-z0-9][a-z0-9._:-]{7,127}$/i);
    assert.match(acknowledgedRequest.action_digest, /^sha256:[a-f0-9]{64}$/);

    await messagePage.locator("#message-draft").fill("Replay this exact message.");
    await messagePage.getByRole("button", { name: "Send message" }).click();
    await messagePage.waitForFunction(() => state.messageStatus === "sent");
    assert.equal(messageRuntime.messageRequests.length, 2);

    await messagePage.locator("#message-draft").fill("Preserve this ACK draft on digest conflict.");
    await messagePage.evaluate(() => { state.messageAttachments = [{ artifact_id: "fixture-image-ack", digest: "sha256:" + "4".repeat(64) }]; renderMessageComposer(); });
    await messagePage.getByRole("button", { name: "Send message" }).click();
    await messagePage.waitForFunction(() => state.messageStatus === "conflict");
    assert.match(await messagePage.locator("#message-status").textContent(), /acknowledged a different command/i);
    assert.equal(await messagePage.locator("#message-draft").inputValue(), "Preserve this ACK draft on digest conflict.");
    assert.deepEqual(await messagePage.evaluate(() => state.messageAttachments), [{ artifact_id: "fixture-image-ack", digest: "sha256:" + "4".repeat(64) }]);
    const mismatchedAckRequest = structuredClone(messageRuntime.messageRequests[2]);
    const mismatchedAckReceipt = await messagePage.evaluate(() => structuredClone(state.messageReceipt));
    assert.match(mismatchedAckReceipt.action_digest, /^sha256:[a-f0-9]{64}$/);
    assert.notEqual(mismatchedAckReceipt.action_digest, mismatchedAckRequest.action_digest, "a second valid digest must not admit an unrelated ACK");
    await messagePage.getByRole("button", { name: "Retry", exact: true }).click();
    await messagePage.waitForFunction(() => state.messageStatus === "sent");
    assert.deepEqual(messageRuntime.messageRequests[3], mismatchedAckRequest, "ACK conflict retry must preserve the exact action and request identity");

    await messagePage.locator("#message-draft").fill("Preserve this replay draft on digest conflict.");
    await messagePage.evaluate(() => { state.messageAttachments = [{ artifact_id: "fixture-image-replay", digest: "sha256:" + "5".repeat(64) }]; renderMessageComposer(); });
    await messagePage.getByRole("button", { name: "Send message" }).click();
    await messagePage.waitForFunction(() => state.messageStatus === "conflict");
    assert.match(await messagePage.locator("#message-status").textContent(), /acknowledged a different command/i);
    assert.equal(await messagePage.locator("#message-draft").inputValue(), "Preserve this replay draft on digest conflict.");
    assert.deepEqual(await messagePage.evaluate(() => state.messageAttachments), [{ artifact_id: "fixture-image-replay", digest: "sha256:" + "5".repeat(64) }]);
    const mismatchedReplayRequest = structuredClone(messageRuntime.messageRequests[4]);
    const mismatchedReplayReceipt = await messagePage.evaluate(() => structuredClone(state.messageReceipt));
    assert.match(mismatchedReplayReceipt.action_digest, /^sha256:[a-f0-9]{64}$/);
    assert.notEqual(mismatchedReplayReceipt.action_digest, mismatchedReplayRequest.action_digest, "a second valid digest must not admit an unrelated replay");
    await messagePage.getByRole("button", { name: "Retry", exact: true }).click();
    await messagePage.waitForFunction(() => state.messageStatus === "sent");
    assert.deepEqual(messageRuntime.messageRequests[5], mismatchedReplayRequest, "Replay conflict retry must preserve the exact action and request identity");

    await messagePage.locator("#message-draft").fill("A RESULT receipt cannot clear this draft.");
    await messagePage.evaluate(() => { state.messageAttachments = [{ artifact_id: "fixture-image-result", digest: "sha256:" + "6".repeat(64) }]; renderMessageComposer(); });
    await messagePage.getByRole("button", { name: "Send message" }).click();
    await messagePage.waitForFunction(() => state.messageStatus === "conflict");
    assert.equal(await messagePage.locator("#message-draft").inputValue(), "A RESULT receipt cannot clear this draft.");
    assert.deepEqual(await messagePage.evaluate(() => state.messageAttachments), [{ artifact_id: "fixture-image-result", digest: "sha256:" + "6".repeat(64) }]);
    const mismatchedResultRequest = structuredClone(messageRuntime.messageRequests[6]);
    await messagePage.getByRole("button", { name: "Retry", exact: true }).click();
    await messagePage.waitForFunction(() => state.messageStatus === "sent");
    assert.deepEqual(messageRuntime.messageRequests[7], mismatchedResultRequest, "RESULT conflict retry must preserve the exact action and request identity");

    await messagePage.locator("#message-draft").fill("Keep this draft on conflict.");
    await messagePage.evaluate(() => { state.messageAttachments = [{ artifact_id: "fixture-image-2", digest: "sha256:" + "2".repeat(64) }]; renderMessageComposer(); });
    await messagePage.getByRole("button", { name: "Send message" }).click();
    await messagePage.waitForFunction(() => state.messageStatus === "conflict");
    assert.equal(await messagePage.getByRole("button", { name: "Retry", exact: true }).isVisible(), true);
    assert.equal(await messagePage.locator("#message-draft").inputValue(), "Keep this draft on conflict.");
    if (evidenceDir) await messagePage.screenshot({ path: path.join(evidenceDir, "41-message-stale-retry-desktop-1024x760.png"), fullPage: false, animations: "disabled" });
    const staleRequest = structuredClone(messageRuntime.messageRequests[8]);
    await messagePage.getByRole("button", { name: "Retry", exact: true }).click();
    await messagePage.waitForFunction(() => state.messageStatus === "sent");
    assert.deepEqual(messageRuntime.messageRequests[9], staleRequest, "Retry must reuse the exact request, context, and attachment identity");

    await messagePage.locator("#message-draft").fill("Do not accept a malformed receipt.");
    await messagePage.evaluate(() => { state.messageAttachments = [{ artifact_id: "fixture-image-3", digest: "sha256:" + "3".repeat(64) }]; renderMessageComposer(); });
    await messagePage.getByRole("button", { name: "Send message" }).click();
    await messagePage.waitForFunction(() => state.messageStatus === "failed");
    assert.match(await messagePage.locator("#message-status").textContent(), /incomplete acknowledgement/);
    assert.equal(await messagePage.getByRole("button", { name: "Retry", exact: true }).isVisible(), true);
    assert.equal(await messagePage.locator("#message-draft").inputValue(), "Do not accept a malformed receipt.");
    assert.deepEqual(await messagePage.evaluate(() => state.messageAttachments), [{ artifact_id: "fixture-image-3", digest: "sha256:" + "3".repeat(64) }]);

    await messagePage.locator("#message-draft").fill("Keep this draft after timeout.");
    await messagePage.getByRole("button", { name: "Send message" }).click();
    await messagePage.waitForFunction(() => state.messageStatus === "failed");
    assert.match(await messagePage.locator("#message-status").textContent(), /timed out[\s\S]*draft is still here/i);
    assert.equal(await messagePage.locator("#message-draft").inputValue(), "Keep this draft after timeout.");
    await messagePage.locator("#message-draft").fill("Keep this draft after transport failure.");
    await messagePage.getByRole("button", { name: "Send message" }).click();
    await messagePage.waitForFunction(() => state.messageStatus === "failed");
    assert.match(await messagePage.locator("#message-status").textContent(), /cannot reach[\s\S]*draft is still here/i);
    assert.equal(await messagePage.locator("#message-draft").inputValue(), "Keep this draft after transport failure.");
    assert.ok(messageRuntime.runtimeErrors.every((message) => /ERR_FAILED/.test(message)), messageRuntime.runtimeErrors.join(" | "));
    await messagePage.close();

    const missingMessageContext = scopedFixture();
    delete missingMessageContext.project_view.identity.view_digest;
    const missingMessagePage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const missingMessageRuntime = await mount(missingMessagePage, missingMessageContext, { ...overrides, messageControl: { timeoutMs: 100, responses: [] } });
    await missingMessagePage.evaluate(() => selectProjectScope("project:fixture"));
    await missingMessagePage.locator("#message-launcher").click();
    await missingMessagePage.locator("#message-draft").fill("This context is incomplete.");
    assert.equal(await missingMessagePage.getByRole("button", { name: "Send message" }).isDisabled(), true);
    assert.match(await missingMessagePage.locator("#message-status").textContent(), /does not have a complete digest and cursor binding/);
    assert.deepEqual(missingMessageRuntime.messageRequests, []);
    await missingMessagePage.close();

    const profilePage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const profileRuntime = await mount(profilePage, scopedFixture(), { ...overrides, profileControl: { unavailable: true } });
    const profileTrigger = profilePage.getByRole("button", { name: "Open profile" });
    await profileTrigger.focus();
    await profileTrigger.click();
    await profilePage.locator("#profile-dialog").waitFor({ state: "visible" });
    await profilePage.waitForFunction(() => state.profileStatus === "unavailable");
    assert.match(await profilePage.locator("#profile-status").textContent(), /profile authority unavailable/i);
    assert.equal(await profilePage.getByRole("button", { name: "Save profile" }).isDisabled(), true);
    assert.deepEqual(profileRuntime.profileRequests.map((request) => request.method), ["GET", "GET"]);
    await profilePage.keyboard.press("Escape");
    assert.equal(await profilePage.locator("#profile-dialog").evaluate((dialog) => dialog.matches(":popover-open")), false);
    assert.equal(await profileTrigger.evaluate((element) => element === document.activeElement), true);
    await profileTrigger.click();
    await profilePage.waitForFunction(() => state.profileStatus === "unavailable");
    await profilePage.getByRole("button", { name: "Cancel" }).click();
    assert.equal(await profileTrigger.evaluate((element) => element === document.activeElement), true);
    await profileTrigger.click();
    await profilePage.locator("#view-title").click();
    assert.equal(await profilePage.locator("#profile-dialog").evaluate((element) => element.matches(":popover-open")), false);
    assert.equal(await profileTrigger.getAttribute("aria-expanded"), "false");
    assert.deepEqual(profileRuntime.profileRequests.map((request) => request.method), ["GET", "GET", "GET", "GET"]);
    assert.equal(profileRuntime.runtimeErrors.length, 4);
    assert.ok(profileRuntime.runtimeErrors.every((message) => /404 \(Not Found\)/.test(message)), profileRuntime.runtimeErrors.join(" | "));
    await profilePage.close();

    const profileAvatarPage = await browser.newPage({ viewport: { width: 1536, height: 1024 } });
    await mount(profileAvatarPage, scopedFixture(), { ...overrides, profileControl: { feed: { ok: true, profile: { display_name: "Peik Gabriel", avatar: { url: "/assets/missing-profile.png" }, preferences: {} } } } });
    await profileAvatarPage.waitForFunction(() => document.querySelector("#profile-button-image")?.hidden === true && document.querySelector("#profile-initials")?.textContent === "PG");
    assert.equal(await profileAvatarPage.locator("#profile-button-image").isVisible(), false);
    assert.equal(await profileAvatarPage.locator("#profile-initials").textContent(), "PG");
    assert.equal(await profileAvatarPage.locator("#profile-button-placeholder").isVisible(), false);
    if (evidenceDir) await profileAvatarPage.screenshot({ path: path.join(evidenceDir, "profile-avatar-fallback-overview-desktop-1536x1024.png"), fullPage: false, animations: "disabled" });
    await profileAvatarPage.close();

    const supportPage = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    await mount(supportPage, scopedFixture(), overrides);
    const supportTrigger = supportPage.getByRole("button", { name: "Support SWARM" });
    await supportTrigger.click();
    await supportPage.locator("#support-dialog").waitFor({ state: "visible" });
    assert.match(await supportPage.locator("#support-dialog").textContent(), /Stripe checkout is not available yet\./);
    assert.equal(await supportPage.getByText(/Buy me a coffee|Continue with Stripe|USD (?:5|10|20)|Address not configured/).count(), 0);
    assert.equal(await supportPage.locator('.support-method a[target="_blank"][rel="noopener noreferrer"]').count(), 2);
    if (evidenceDir) await supportPage.screenshot({ path: path.join(evidenceDir, "support-modal-midnight-desktop-1440x1000.png"), fullPage: false, animations: "disabled" });
    await supportPage.keyboard.press("Escape");
    assert.equal(await supportPage.locator("#support-dialog").evaluate((dialog) => dialog.open), false);
    assert.equal(await supportTrigger.evaluate((element) => element === document.activeElement), true);
    await supportTrigger.click();
    await supportPage.locator("#support-dialog").waitFor({ state: "visible" });
    await supportPage.mouse.click(40, 100);
    assert.equal(await supportPage.locator("#support-dialog").evaluate((dialog) => dialog.open), false);
    assert.equal(await supportTrigger.evaluate((element) => element === document.activeElement), true);
    await supportPage.close();

    const tabletSupportPage = await browser.newPage({ viewport: { width: 834, height: 1112 } });
    await mount(tabletSupportPage, scopedFixture(), overrides);
    await tabletSupportPage.locator("#support-open").click();
    await tabletSupportPage.locator("#support-dialog").waitFor({ state: "visible" });
    assert.equal(await tabletSupportPage.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    if (evidenceDir) await tabletSupportPage.screenshot({ path: path.join(evidenceDir, "support-modal-midnight-tablet-834x1112.png"), fullPage: false, animations: "disabled" });
    await tabletSupportPage.keyboard.press("Escape");
    assert.equal(await tabletSupportPage.locator("#support-open").evaluate((element) => element === document.activeElement), true);
    await tabletSupportPage.close();

    const mobileSupportPage = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await mount(mobileSupportPage, scopedFixture(), overrides);
    await mobileSupportPage.locator("#support-open").evaluate((button) => button.click());
    await mobileSupportPage.locator("#support-dialog").waitFor({ state: "visible" });
    assert.equal(await mobileSupportPage.locator("#support-dialog").evaluate((dialog) => {
      const box = dialog.getBoundingClientRect();
      return box.width === innerWidth && box.height === innerHeight && document.documentElement.scrollWidth <= innerWidth;
    }), true);
    if (evidenceDir) await mobileSupportPage.screenshot({ path: path.join(evidenceDir, "support-modal-midnight-mobile-390x844.png"), fullPage: false, animations: "disabled" });
    await mobileSupportPage.close();

    const shellPage = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const shellRuntime = await mount(shellPage, scopedFixture(), overrides);
    await shellPage.locator("#ask-anything").fill("Review the current project");
    await shellPage.locator("#ask-anything-form").press("Enter");
    assert.equal(await shellPage.locator("#message-composer").evaluate((dialog) => dialog.open), true);
    assert.equal(await shellPage.locator("#message-draft").inputValue(), "Review the current project");
    await shellPage.getByRole("button", { name: "Close Message" }).click();
    await shellPage.waitForFunction(() => !document.querySelector("#message-composer").open);
    await shellPage.getByRole("button", { name: "Create project" }).click();
    await shellPage.locator("#project-create-name").fill("Created project");
    await shellPage.locator("#project-create-root").fill("C:\\Projects\\created-project");
    await shellPage.locator("#project-create-acknowledge").check();
    await shellPage.getByRole("button", { name: "Create project", exact: true }).last().click();
    await shellPage.getByText(/create the project in Codex, then refresh SWARM HQ/i).waitFor();
    assert.equal(await shellPage.locator("#project-create-dialog").evaluate((dialog) => dialog.open), true);
    assert.deepEqual(shellRuntime.projectRequests, [{ name: "Created project", root: "C:\\Projects\\created-project", acknowledge: true }]);
    assert.ok(shellRuntime.runtimeErrors.every((message) => /400 \(Bad Request\)/.test(message)), shellRuntime.runtimeErrors.join(" | "));
    await shellPage.close();

    for (const viewport of [
      { name: "1270x714", width: 1270, height: 714, searchVisible: true },
      { name: "1280x720", width: 1280, height: 720, searchVisible: true },
      { name: "1440x900", width: 1440, height: 900, searchVisible: true },
      { name: "1600x900", width: 1600, height: 900, searchVisible: true },
      { name: "834x1112", width: 834, height: 1112, searchVisible: false },
      { name: "390x844", width: 390, height: 844, searchVisible: false },
    ]) {
      const narrowDesktopPage = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
      const narrowDesktop = await mount(narrowDesktopPage, scopedFixture(), overrides);
      const toolbarGeometry = await narrowDesktopPage.evaluate(() => {
        const search = document.querySelector("#ask-anything-form").getBoundingClientRect();
        const scope = document.querySelector("#scope-context").getBoundingClientRect();
        const title = document.querySelector("#view-title").getBoundingClientRect();
        const toolbar = document.querySelector(".header-toolbar").getBoundingClientRect();
        const profile = document.querySelector("#profile").getBoundingClientRect();
        const chevron = document.querySelector("#project-scope-filter .lucide").getBoundingClientRect();
        return {
          search: { left: search.left, top: search.top, right: search.right, bottom: search.bottom },
          scope: { left: scope.left, top: scope.top, right: scope.right, bottom: scope.bottom },
          chevron: { width: chevron.width, height: chevron.height },
          chevronHref: document.querySelector("#project-scope-filter use").getAttribute("href"),
          overlaps: search.left < scope.right && search.right > scope.left && search.top < scope.bottom && search.bottom > scope.top,
          desktopRow: search.bottom <= title.top && scope.bottom <= title.top && Math.abs(search.top - scope.top) <= 3,
          aligned: Math.abs(search.left - title.left) <= 1 && Math.abs(profile.right - toolbar.right) <= 1,
          documentWidth: document.documentElement.scrollWidth,
          viewportWidth: innerWidth,
        };
      });
      if (evidenceDir) await narrowDesktopPage.screenshot({ path: path.join(evidenceDir, `toolbar-${viewport.name}.png`), fullPage: false, animations: "disabled" });
      assert.equal(await narrowDesktopPage.locator("#ask-anything-form").isVisible(), viewport.searchVisible);
      assert.equal(toolbarGeometry.overlaps, false, JSON.stringify(toolbarGeometry));
      assert.ok(toolbarGeometry.documentWidth <= toolbarGeometry.viewportWidth, JSON.stringify(toolbarGeometry));
      assert.deepEqual(toolbarGeometry.chevron, { width: 14, height: 14 });
      assert.equal(toolbarGeometry.chevronHref, "#lucide-chevron-down");
      if (viewport.searchVisible) {
        assert.equal(toolbarGeometry.desktopRow, true, JSON.stringify(toolbarGeometry));
        assert.equal(toolbarGeometry.aligned, true, JSON.stringify(toolbarGeometry));
        await narrowDesktopPage.keyboard.press("Control+k");
        assert.equal(await narrowDesktopPage.evaluate(() => document.activeElement?.id), "ask-anything");
      }
      await narrowDesktopPage.locator("#project-scope-filter").focus();
      await narrowDesktopPage.keyboard.press("ArrowDown");
      assert.equal(await narrowDesktopPage.evaluate(() => document.activeElement?.dataset.projectScopeId), "all");
      await narrowDesktopPage.keyboard.press("Escape");
      assert.equal(await narrowDesktopPage.evaluate(() => document.activeElement?.id), "project-scope-filter");
      assert.deepEqual(narrowDesktop.runtimeErrors, []);
      assert.deepEqual(narrowDesktop.failedRequests, []);
      await narrowDesktopPage.close();
    }

    const diagnosticsControl = {
      feed: {
        ...structuredClone(fixture.diagnostics),
        health: {
          incidents: [],
          open_requests: [],
          repair_policy: { dispatch: "disabled", reason: "Repair dispatch is not available from this server." },
          checks: [{ id: "project.ctrl_binding", status: "WARN", summary: "The saved project does not have a current CTRL binding.", recommended_action: "Prepare a scoped CTRL binding repair." }],
        },
      },
      history: structuredClone(fixture.diagnosticHistory),
      repairResponses: [{ ok: true, repair_policy: { dispatch: "disabled", claim_limit: "Preview only." }, selected_check_ids: ["project.ctrl_binding"] }],
      getCount: 0,
    };
    const diagnosticsPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const diagnosticsRuntime = await mount(diagnosticsPage, scopedFixture(), { ...overrides, diagnosticsControl });
    await openPrimaryView(diagnosticsPage, "diagnostics");
    await diagnosticsPage.waitForFunction(() => state.diagnosticsHistoryStatus === "current");
    assert.match(await diagnosticsPage.locator("#diagnostics-health-heading").textContent(), /Healthy|Needs attention|Unknown/);
    assert.equal(await diagnosticsPage.locator("#diagnostics-check-strip .diagnostics-check-token").count(), 1);
    assert.equal(await diagnosticsPage.locator("#diagnostics-signal-list .diagnostics-signal-row").count(), 1);
    assert.equal(await diagnosticsPage.locator("#diagnostics-check-list input[type=checkbox]").count(), 0);
    const checkToken = diagnosticsPage.locator("#diagnostics-check-strip .diagnostics-check-token");
    await checkToken.focus();
    assert.match(await checkToken.getAttribute("title"), /Project\.Ctrl Binding: The saved project/);
    await checkToken.press("Enter");
    assert.equal(await diagnosticsPage.locator(".diagnostics-all-checks").evaluate((details) => details.open), true);
    assert.equal(await diagnosticsPage.evaluate(() => document.activeElement?.dataset.diagnosticDetail), "project.ctrl_binding");
    const diagnosticsReads = diagnosticsControl.getCount;
    const refreshedDiagnostics = diagnosticsPage.waitForResponse((response) => new URL(response.url()).pathname === "/api/diagnostics");
    await diagnosticsPage.evaluate(() => refreshOverview());
    await refreshedDiagnostics;
    assert.ok(diagnosticsControl.getCount > diagnosticsReads, "Refresh must reread the authoritative diagnostics feed");
    const ctrlReview = diagnosticsPage.getByRole("button", { name: "Review with CTRL" });
    await ctrlReview.click();
    await diagnosticsPage.locator("#agent-detail-dialog").waitFor({ state: "visible" });
    assert.equal(diagnosticsRuntime.repairRequests.length, 0);
    if (evidenceDir) await diagnosticsPage.screenshot({ path: path.join(evidenceDir, "43-diagnostics-ctrl-review-desktop-1024x760.png"), fullPage: false, animations: "disabled" });
    await diagnosticsPage.keyboard.press("Escape");
    assert.deepEqual(diagnosticsRuntime.runtimeErrors, []);
    await diagnosticsPage.close();

    const mobileDiagnosticsControl = { feed: structuredClone(diagnosticsControl.feed), history: structuredClone(fixture.diagnosticHistory), repairResponses: [], getCount: 0 };
    const mobileDiagnosticsPage = await browser.newPage({ viewport: { width: 390, height: 844 } });
    const mobileDiagnosticsRuntime = await mount(mobileDiagnosticsPage, scopedFixture(), { ...overrides, diagnosticsControl: mobileDiagnosticsControl });
    await mobileDiagnosticsPage.locator("#tab-diagnostics").evaluate((button) => button.click());
    await mobileDiagnosticsPage.waitForFunction(() => state.diagnosticsHistoryStatus === "current");
    assert.equal(await mobileDiagnosticsPage.locator("#view-diagnostics").evaluate((view) => getComputedStyle(view).overflowY), "visible");
    assert.equal(await mobileDiagnosticsPage.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true);
    assert.equal(await mobileDiagnosticsPage.locator("#diagnostics-check-strip").evaluate((strip) => getComputedStyle(strip).gridTemplateColumns.split(" ").length), 2);
    if (evidenceDir) await mobileDiagnosticsPage.screenshot({ path: path.join(evidenceDir, "44-diagnostics-mobile-390x844.png"), fullPage: false, animations: "disabled" });
    assert.equal(mobileDiagnosticsRuntime.repairRequests.length, 0);
    assert.deepEqual(mobileDiagnosticsRuntime.runtimeErrors, []);
    await mobileDiagnosticsPage.close();

    const page = await browser.newPage({ viewport: { width: 1536, height: 1024 } });
    const sampledAt = Date.now();
    const desktop = await mount(page, overview, {
      ...overrides,
      diagnosticsControl: {
        feed: fixture.diagnostics,
        history: { ok: true, items: [{ sampled_at_ms: sampledAt - 40_000, health_state: "WARN" }, { sampled_at_ms: sampledAt - 20_000, health_state: "HEALTHY" }, { sampled_at_ms: sampledAt, health_state: "HEALTHY" }] },
        repairResponses: [],
      },
    });
    await assertSharedCircleGeometry(page, ["#profile", "#notifications", ".scope-dot", ".agent-avatar-token", "#message-launcher"]);
    await page.locator("#notifications").click();
    await page.locator("#notifications-panel").waitFor({ state: "visible" });
    if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, "circle-invariant-notifications-desktop-1536x1024.png"), fullPage: false, animations: "disabled" });
    await page.locator("#notifications-close").click();
    if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, "circle-invariant-overview-desktop-1536x1024.png"), fullPage: false, animations: "disabled" });
    assert.equal(await page.locator("#message-launcher").isVisible(), true);
    assert.equal(await page.locator("#mobile-message-action").isVisible(), false);
    await page.locator("#message-launcher").click();
    await page.locator("#message-composer").waitFor({ state: "visible" });
    assert.equal(await page.locator("#message-title").textContent(), "Message");
    assert.deepEqual(await page.locator("#message-composer").evaluate((element) => {
      const box = element.getBoundingClientRect();
      return { top: Math.round(box.top), right: Math.round(innerWidth - box.right), bottom: Math.round(innerHeight - box.bottom), height: Math.round(box.height) };
    }), { top: 0, right: 0, bottom: 0, height: 1024 });
    assert.equal(await page.evaluate(() => document.activeElement?.id), "message-draft");
    assert.deepEqual(await page.locator("#message-recipient option").allTextContents(), ["No observed conversations"]);
    assert.equal(await page.locator("#message-recipient").isDisabled(), true);
    assert.deepEqual(await page.evaluate(() => ({ sendDisabled: document.querySelector("#message-send").disabled, retryHidden: document.querySelector("#message-retry").hidden })), { sendDisabled: true, retryHidden: true });
    assert.equal(await page.locator("#message-status").textContent(), "No authorized CTRL is available in this project scope.");
    await page.locator("#message-draft").fill("Please review this screen.");
    await page.keyboard.press("Escape");
    assert.equal(await page.locator("#message-composer").isVisible(), false);
    assert.equal(await page.evaluate(() => document.activeElement?.id), "message-launcher");
    await page.locator("#message-launcher").click();
    assert.equal(await page.locator("#message-draft").inputValue(), "Please review this screen.");
    await page.evaluate(() => sendMessageFromComposer());
    assert.deepEqual(desktop.requests.filter((requestPath) => /message|feedback|connector|project-view-action/i.test(requestPath)), []);
    assert.equal(await page.locator("#message-draft").inputValue(), "Please review this screen.");
    assert.equal(await page.locator("#message-composer").evaluate((element) => getComputedStyle(element.querySelector(".message-composer-body")).overflowY), "auto");
    assert.match(await page.locator("#message-conversation-state").textContent(), /unavailable|Choose a recipient/);
    assert.equal(await page.locator("#message-draft").getAttribute("rows"), "2");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true);
    if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, "40-message-unavailable-desktop-1536x1024.png"), fullPage: false, animations: "disabled" });
    await page.keyboard.press("Escape");
    for (const view of ["overview", "agents", "labs", "roles", "review", "assets", "diagnostics", "settings"]) assert.equal(await page.locator('.nav-item[data-view="' + view + '"]').count(), 1);
    assert.equal(await page.getByRole("tab", { name: "Projects", exact: true }).count(), 0);
    for (const retired of ["dashboard", "hierarchy", "kanban"]) assert.equal(await page.locator('.nav-item[data-view="' + retired + '"]').count(), 0);
    assert.equal(await page.locator("#project-scope-filter").isVisible(), true);
    assert.deepEqual(await page.locator("#project-navigation button").evaluateAll((elements) => elements.map((element) => element.getAttribute("aria-label") || element.textContent.trim())), [
      "Arc, Active",
      "Atlas, Active",
      "Flowwweb, Active",
      "swarm, Active",
      "Stalled project, Recently active",
      "Idle project, Inactive",
      "Unassigned planning, Inactive",
    ]);
    assert.deepEqual(await page.locator("#project-navigation .scope-dot").evaluateAll((elements) => elements.map((element) => [...element.classList].find((name) => name.startsWith("is-")))), [
      "is-active", "is-active", "is-active", "is-active", "is-recent", "is-inactive", "is-inactive",
    ]);
    assert.doesNotMatch(await page.locator("#project-navigation").textContent(), /All projects|Archived project|Resolve customer export/);
    await page.locator("#project-scope-filter").click();
    assert.equal(await page.locator('#project-scope-options .project-scope-logo[src="/assets/project-fixture.svg"]').count(), 1);
    assert.equal(await page.locator("#project-scope-options .scope-dot").count(), 7);
    if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, "27-project-dropdown-desktop-1536x1024.png"), fullPage: false, animations: "disabled" });
    assert.deepEqual(await page.locator("#project-scope-options [data-project-scope-id]").evaluateAll((elements) => elements.map((element) => ({ label: element.querySelector("span:nth-of-type(2)")?.textContent, status: element.querySelector("small")?.textContent }))), [
      { label: "All projects", status: "Portfolio" },
      { label: "Arc", status: "Active" },
      { label: "Atlas", status: "Active" },
      { label: "Flowwweb", status: "Active" },
      { label: "swarm", status: "Active" },
      { label: "Stalled project", status: "Recently active" },
      { label: "Idle project", status: "Inactive" },
      { label: "Unassigned planning", status: "Inactive" },
    ]);
    await page.keyboard.press("Escape");
    assert.equal(await page.locator("#project-scope-selector").getAttribute("open"), null);
    assert.equal(await page.evaluate(() => document.activeElement?.id), "project-scope-filter");
    await page.keyboard.press("ArrowDown");
    assert.equal(await page.evaluate(() => document.activeElement?.dataset.projectScopeId), "all");
    await page.keyboard.press("End");
    assert.equal(await page.evaluate(() => document.activeElement?.dataset.projectScopeId), "project:waiting");
    await page.keyboard.press("Home");
    assert.equal(await page.evaluate(() => document.activeElement?.dataset.projectScopeId), "all");
    await page.keyboard.press("Escape");
    const scopedViews = ["overview", "agents", "labs", "roles", "review", "assets", "diagnostics", "settings"];
    for (let index = 0; index < scopedViews.length; index += 1) {
      const view = scopedViews[index];
      const projectId = index % 2 ? "project:fixture" : "project:branch";
      await page.locator('.nav-item[data-view="' + view + '"]').click();
      await chooseProjectScope(page, projectId);
      await page.waitForFunction(({ view, projectId }) => state.view === view && state.projectId === projectId, { view, projectId });
      assert.equal(await page.locator('[data-view-panel="' + view + '"]').isVisible(), true);
      assert.equal(new URL(page.url()).searchParams.get("project"), projectId);
      assert.equal(new URL(page.url()).hash, "#" + view);
    }
    await chooseProjectScope(page, "project:fixture");
    assert.equal(await page.locator('#project-scope-selected-mark .project-scope-logo[src="/assets/project-fixture.svg"]').count(), 1);
    await openPrimaryView(page, "assets");
    await chooseProjectScope(page, "project:branch");
    await page.waitForFunction(() => state.view === "assets" && state.projectId === "project:branch");
    await chooseProjectScope(page, "project:fixture");
    await page.waitForFunction(() => state.view === "assets" && state.projectId === "project:fixture");
    await page.goBack();
    await page.waitForFunction(() => state.view === "assets" && state.projectId === "project:branch");
    assert.equal(await page.locator("#view-assets").isVisible(), true);
    await page.locator("#project-navigation-heading").focus();
    assert.equal(await page.locator("#project-navigation-heading").getAttribute("aria-label"), "All projects");
    await page.keyboard.press("Enter");
    await page.waitForFunction(() => state.view === "overview" && state.projectId === "all");
    assert.equal(new URL(page.url()).searchParams.has("project"), false);
    assert.equal(new URL(page.url()).hash, "#overview");
    if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, "11-overview-all-projects-link-desktop-1536x1024.png"), fullPage: false, animations: "disabled" });
    assert.equal(await page.locator("#profile").isDisabled(), false);
    assert.equal(await page.locator(".top-actions #profile").count(), 1);
    assert.equal(await page.locator("#profile-initials").textContent(), "PG");
    assert.doesNotMatch(await page.locator("#console-drawer").textContent(), /\bLive\b/);
    assert.equal(await page.locator("#notifications").evaluate((notification) => {
      const profile = document.querySelector("#profile").getBoundingClientRect();
      const box = notification.getBoundingClientRect();
      const header = document.querySelector(".topbar").getBoundingClientRect();
      return box.left < profile.left && Math.abs(profile.right - header.right) <= 1 && box.top >= header.top && profile.bottom <= header.bottom;
    }), true);
    assert.equal(await page.locator(".top-actions #system-health-control").count(), 0);
    assert.deepEqual(await page.locator(".top-actions > button").evaluateAll(items => items.map(item => item.id)), ["notifications", "profile"]);
    if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, "shell-profile-sidebar-desktop-1536x1024.png"), fullPage: false, animations: "disabled" });
    assert.deepEqual(await page.locator(".overview-metric-card > header > span").allTextContents(), ["Active work", "Needs attention", "TBR", "Usage remaining"]);
    assert.deepEqual(await page.locator(".overview-metric-card > strong").allTextContents(), ["3 / 5", "2", "—", "—"]);
    await page.waitForFunction(() => state.usageWindowHours === 1 && state.usageStatus === "current");
    await page.locator('[data-overview-metric="usage"]').focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.getByRole('dialog', {name:'Usage',exact:true}).isVisible(), true);
    const usageRanges = page.getByRole("group", { name: "Task usage range", exact: true });
    assert.equal(await usageRanges.getByRole("button", { name: "1d", exact: true }).getAttribute("aria-pressed"), "true");
    await assertMetricDetailContainment(page);
    const usageWeekRequest = page.waitForRequest((request) => new URL(request.url()).pathname === "/api/usage-history" && new URL(request.url()).searchParams.get("hours") === "168");
    await usageRanges.getByRole("button", { name: "1w", exact: true }).click();
    await usageWeekRequest;
    await page.waitForFunction(() => state.usageWindowHours === 168 && state.usageStatus === "current");
    assert.equal(await usageRanges.getByRole("button", { name: "1w", exact: true }).getAttribute("aria-pressed"), "true");
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('[data-overview-metric="usage"]').evaluate(el => el === document.activeElement), true);
    assert.equal(await page.locator("#overview-monitoring-heading").isVisible(), true);
    assert.equal(await page.locator("#overview-monitoring-heading").textContent(), "Swarm");
    assert.deepEqual(await page.locator("#overview-project-cards [data-overview-project-id] strong").allTextContents(), ["Arc", "Atlas", "Flowwweb", "swarm"]);
    assert.deepEqual(await page.locator("#overview-project-cards [data-overview-hierarchy-project]").evaluateAll((projects) => projects.map((project) => project.dataset.overviewHierarchyProject)), ["project:arc", "project:atlas", "project:branch", "project:fixture"]);
    assert.match(await page.locator("#overview-project-cards .overview-hierarchy-canvas > .overview-independent:not(.is-error)").textContent(), /Active host tasks[\s\S]*Resolve customer export[\s\S]*Inspect export evidence[\s\S]*Anonymous[\s\S]*Independent task/);
    assert.match(await page.locator("#overview-project-cards .overview-independent.is-error").textContent(), /Role binding needs attention[\s\S]*Reconnect role manifest[\s\S]*Role binding error/);
    assert.doesNotMatch(await page.locator("#overview-project-cards").textContent(), /Await customer decision|Resolve dependency|Unassigned planning/);
    await page.waitForFunction(() => [...document.querySelectorAll("[data-overview-hierarchy-edge]")].every((path) => Boolean(path.getAttribute("d"))));
    if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, "overview-hierarchy-desktop-1536x1024.png"), fullPage: false, animations: "disabled" });
    assert.equal(await page.locator("[data-overview-hierarchy-project]").evaluateAll((projects) => projects.every((project) => {
      const nodes = [...project.querySelectorAll("[data-overview-hierarchy-node]")].map((node) => node.getBoundingClientRect());
      return nodes.every((left, index) => nodes.slice(index + 1).every((right) => left.right <= right.left || right.right <= left.left || left.bottom <= right.top || right.bottom <= left.top));
    })), true);
    assert.equal(await page.locator("#overview-project-cards .overview-node-more").count(), 0);
    assert.equal(await page.locator("[data-overview-hierarchy-edge]").count(), await page.locator("[data-overview-output]").count());
    assert.equal(await page.locator('[data-overview-hierarchy-node="nested-ctrl"] [data-overview-output="nested-task"]').count(), 1);
    assert.equal(await page.locator('[data-overview-hierarchy-node="nested-task"] [data-overview-input]').count(), 1);
    const missingTopologySnapshot = await page.evaluate(() => structuredClone(state.overview));
    await page.evaluate(() => {
      state.overview.topology.nodes = state.overview.topology.nodes.filter((node) => node.agent_id !== "nested-task");
      renderOverviewProjectCards();
    });
    assert.equal(await page.locator('[data-overview-hierarchy-node="nested-task"]').count(), 0);
    assert.equal(await page.locator('[data-overview-hierarchy-edge][data-target="nested-task"]').count(), 0);
    await page.evaluate((snapshot) => { state.overview = snapshot; renderOverviewProjectCards(); }, missingTopologySnapshot);
    await page.waitForFunction(() => [...document.querySelectorAll("[data-overview-hierarchy-edge]")].every((path) => Boolean(path.getAttribute("d"))));
    assert.equal(await page.evaluate(() => [...document.querySelectorAll("[data-overview-hierarchy-edge]")].every((path) => {
      const svg = path.ownerSVGElement;
      const source = document.querySelector('[data-overview-hierarchy-node="' + path.dataset.source + '"]');
      const target = document.querySelector('[data-overview-hierarchy-node="' + path.dataset.target + '"]');
      const output = [...source.querySelectorAll("[data-overview-output]")].find((port) => port.dataset.overviewOutput === path.dataset.target);
      const input = target.querySelector("[data-overview-input]");
      const svgBox = svg.getBoundingClientRect();
      const from = output.getBoundingClientRect();
      const to = input.getBoundingClientRect();
      const start = path.getPointAtLength(0);
      const end = path.getPointAtLength(path.getTotalLength());
      return Math.abs(start.x - (from.left + from.width / 2 - svgBox.left)) <= 1
        && Math.abs(start.y - (from.top + from.height / 2 - svgBox.top)) <= 1
        && Math.abs(end.x - (to.left + to.width / 2 - svgBox.left)) <= 1
        && Math.abs(end.y - (to.top + to.height / 2 - svgBox.top)) <= 1;
    })), true);
    const hierarchyOverviewSnapshot = await page.evaluate(() => structuredClone(state.overview));
    await page.evaluate(() => { delete state.overview.topology; renderOverviewProjectCards(); });
    assert.equal(await page.locator("[data-overview-hierarchy-node]").count(), 0);
    assert.equal(await page.locator("[data-overview-hierarchy-edge]").count(), 0);
    assert.match(await page.locator("#overview-project-cards").textContent(), /Active agent topology is unavailable/);
    await page.evaluate((snapshot) => { state.overview = snapshot; renderOverviewProjectCards(); }, hierarchyOverviewSnapshot);
    await page.waitForFunction(() => [...document.querySelectorAll("[data-overview-hierarchy-edge]")].every((path) => Boolean(path.getAttribute("d"))));
    await page.evaluate(() => { state.overview = null; renderOverviewProjectCards(); });
    assert.equal(await page.locator("#overview-project-cards").getAttribute("aria-busy"), "true");
    assert.equal(await page.locator(".overview-hierarchy-skeleton-node").count(), 4);
    assert.equal(await page.locator(".overview-hierarchy-skeleton-edges path").count(), 1);
    await page.evaluate((snapshot) => { state.overview = snapshot; renderOverviewProjectCards(); }, hierarchyOverviewSnapshot);
    await page.waitForFunction(() => [...document.querySelectorAll("[data-overview-hierarchy-edge]")].every((path) => Boolean(path.getAttribute("d"))));
    const hierarchyWorkView = structuredClone(projectModelViewFixture().find((view) => view.id === "view.project.work"));
    await page.evaluate((acceptedWorkView) => {
      state.overview.project_view.views = [acceptedWorkView];
      const work = acceptedWorkView;
      work.content.rows.push(...[2, 3, 4].map((ordinal) => ({ id: "nested-work-" + ordinal, kind: "task", label: "Bound work " + ordinal, depth: 1, parent_id: "m-route", owner_id: "nested-task", task_id: "nested-work-" + ordinal, ctrl_id: "nested-ctrl", status: "active", progress_percent: ordinal * 10 })));
      renderOverview();
    }, hierarchyWorkView);
    const nestedHierarchy = page.locator('[data-overview-hierarchy-node="nested-task"]');
    assert.equal(await nestedHierarchy.locator(":scope > .overview-node-work-list > .overview-node-work").count(), 0);
    assert.equal(await nestedHierarchy.locator(":scope > .overview-node-work-list > .overview-node-more").count(), 0);
    await page.evaluate((legacyProjectView) => { state.overview.project_view = legacyProjectView; renderOverview(); }, projectViewFixture());
    const overviewAgent = page.locator('#overview-project-cards .overview-node-open[data-agent-detail="nested-task"]');
    await overviewAgent.focus();
    await overviewAgent.press("Enter");
    await page.locator("#agent-detail-dialog").waitFor({ state: "visible" });
    assert.match(await page.locator("#agent-detail-dialog").textContent(), /Review screenshots[\s\S]*(Tomato|Aqua|Gold|Violet)[\s\S]*Developer[\s\S]*Live ETA[\s\S]*UNKNOWN[\s\S]*Work[\s\S]*Work unavailable\. No accepted project hierarchy is bound\.[\s\S]*Log/);
    assert.equal(await page.locator("#agent-detail-dialog .agent-work-status[title]").count(), 0);
    await page.keyboard.press("Escape");
    assert.equal(await page.evaluate(() => document.activeElement?.dataset.agentDetail), "nested-task");
    const overviewAgentInspect = page.locator('#overview-project-cards [data-agent-inspect="nested-task"]');
    await overviewAgentInspect.focus();
    assert.match(await overviewAgentInspect.getAttribute("aria-label"), /^View .+ details$/);
    assert.equal(await overviewAgentInspect.getAttribute("title"), "View agent details");
    assert.equal(await overviewAgentInspect.locator('use[href="#lucide-eye"]').count(), 1);
    await overviewAgentInspect.press("Enter");
    await page.locator("#agent-detail-dialog").waitFor({ state: "visible" });
    await page.keyboard.press("Escape");
    assert.equal(await page.evaluate(() => document.activeElement?.dataset.agentInspect), "nested-task");
    assert.equal(await page.locator(".overview-metrics").evaluate((metrics) => metrics.getBoundingClientRect().bottom <= document.querySelector("#overview-monitoring-heading").closest(".overview-section").getBoundingClientRect().top), true);
    const keyboardScopeRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname === "/api/overview" && url.searchParams.get("project_id") === "project:arc";
    });
    await page.locator('#project-navigation [data-project-id="project:arc"]').focus();
    await page.keyboard.press("Enter");
    await keyboardScopeRequest;
    assert.equal(await page.locator('#project-navigation [data-project-id="project:arc"]').getAttribute("aria-pressed"), "true");
    assert.equal(await page.locator('#project-navigation [data-project-id="project:waiting"]').count(), 1);
    const scopedOverviewRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname === "/api/overview" && url.searchParams.get("project_id") === "project:fixture";
    });
    await page.locator('#project-navigation [data-project-id="project:fixture"]').click();
    await scopedOverviewRequest;
    await page.locator("#project-detail").waitFor({ state: "visible" });
    assert.ok(desktop.requests.includes("/api/overview?project_id=project%3Afixture"));
    assert.equal(await page.locator('#project-navigation [data-project-id="project:waiting"]').count(), 1);
    await page.locator("#notification-unread").waitFor({ state: "visible" });
    await page.waitForFunction(() => document.querySelector("#notification-unread")?.textContent === "1");
    assert.equal(await page.locator("#notification-unread").textContent(), "1");
    await assertCircleFrame(page, "#notifications", 44);
    const seenRequest = page.waitForRequest((request) => new URL(request.url()).pathname === "/api/notifications/seen");
    await page.locator("#notifications").click();
    assert.match(await page.locator("#notifications-panel").textContent(), /Independent review is required/);
    assert.deepEqual((await seenRequest).postDataJSON(), { ctrl_id: "ctrl", project_id: "project:fixture", notification_ids: ["a".repeat(64)] });
    await page.waitForFunction(() => {
      const unread = document.querySelector("#notification-unread");
      return unread?.hidden === true && unread.textContent === "0";
    });
    await page.locator("#notifications-close").click();
    assert.equal(await page.locator("[data-project-tab]").count(), 0);
    assert.equal(await page.locator("#project-tab-panel").getAttribute("aria-label"), "Project overview");
    assert.match(await page.locator("#project-detail-summary").textContent(), /60%/);
    assert.equal(await page.locator(".milestone-ring").count(), 2);
    assert.equal(await page.locator(".project-yield-chart").count(), 0);
    assert.equal(await page.locator(".project-yield-empty").count(), 1);
    assert.equal(await page.locator(".project-detail-feed > li").count(), 2);
    await page.evaluate(() => {
      state.projectUiGroupId = "workspace";
      state.projectId = "project:fixture";
      state.ctrlId = "branch-ctrl";
      state.notificationBindingKey = "project:branch|branch-ctrl";
      navigateNotification({
        project_id: "project:branch", ctrl_id: "branch-ctrl",
        action_target: { view: "review", project_id: "project:branch", ctrl_id: "branch-ctrl", task_id: "branch-ctrl", subject_id: "proof-branch" },
      });
    });
    assert.deepEqual(await page.evaluate(() => ({ projectId: state.projectId, ctrlId: state.ctrlId, groupId: state.projectUiGroupId })), { projectId: "project:branch", ctrlId: "branch-ctrl", groupId: "" });
    await page.evaluate(() => selectProjectScope("project:fixture"));
    await page.evaluate(() => { state.projectUiGroupId = "workspace"; setView("settings"); renderSettings(); });
    await page.locator("#settings-scope").selectOption("project|project:branch");
    await page.waitForFunction(() => state.projectId === "project:branch" && state.projectUiGroupId === "");
    assert.deepEqual(await page.evaluate(() => ({ projectId: state.projectId, ctrlId: state.ctrlId, groupId: state.projectUiGroupId })), { projectId: "project:branch", ctrlId: "", groupId: "" });
    await page.evaluate(() => selectProjectScope("project:fixture"));
    await page.evaluate((views) => {
      state.overview.project_view.views = views;
      state.overview.project_view.modes = views.map(({ id, label, renderer, mode }) => ({ id, label, renderer, mode }));
    }, projectModelViewFixture());
    await page.locator("#tab-agents").click();
    await page.waitForFunction(() => document.querySelectorAll("[data-agent-detail]").length >= 2);
    assert.doesNotMatch(await page.locator("#view-agents").textContent(), /idle-task|stalled-task|standalone-task/);
    const measuredAgent = page.locator('#view-agents [data-agent-detail="nested-task"]');
    assert.equal(await measuredAgent.count(), 1);
    assert.match(await measuredAgent.textContent(), /Review screenshots[\s\S]*swarm[\s\S]*In progress[\s\S]*60%/i);
    assert.equal(await measuredAgent.locator('[role="progressbar"][aria-valuenow="60"]').count(), 1);
    assert.equal(await measuredAgent.locator('time[data-label="Updated"]').getAttribute("datetime"), "2026-08-09T00:00:00.000Z");
    const unknownAgent = page.locator('#view-agents [data-agent-detail="nested-ctrl"]');
    assert.match(await unknownAgent.textContent(), /UNKNOWN/);
    assert.equal(await unknownAgent.locator('[role="progressbar"]').count(), 0);
    assert.equal(await measuredAgent.locator(".agent-avatar-token .role-avatar.is-mini").count(), 1);
    assert.ok(await page.locator(".agent-avatar-token .role-avatar.is-mini").count() >= 2);
    assert.doesNotMatch(await page.locator("#view-agents").textContent(), /Pending/);
    assert.match(await measuredAgent.textContent(), /Review screenshots[\s\S]*Violet[\s\S]*Developer[\s\S]*DOER/);
    assert.doesNotMatch(await measuredAgent.textContent(), /nested-task|01a[0-9a-f-]+/i);
    const malformedAgent = page.locator('#view-agents [data-agent-detail="malformed-task"]');
    assert.match(await malformedAgent.textContent(), /Reconnect role manifest[\s\S]*Identity unavailable[\s\S]*Role binding error[\s\S]*Needs attention/);
    assert.equal(await malformedAgent.isDisabled(), true);
    await measuredAgent.focus();
    await measuredAgent.press("Enter");
    await page.locator("#agent-detail-dialog").waitFor({ state: "visible" });
    assert.match(await page.locator("#agent-detail-dialog").textContent(), /Review screenshots[\s\S]*Violet[\s\S]*Developer[\s\S]*swarm[\s\S]*Live ETA[\s\S]*medium confidence[\s\S]*Work[\s\S]*Routing proof[\s\S]*Capture device proof[\s\S]*Bind the qualified APK[\s\S]*Log[\s\S]*3 of 5 checks passed/);
    assert.doesNotMatch(await page.locator("#agent-detail-dialog").textContent(), /nested-task|nested-ctrl|developer-v1/);
    assert.equal(await page.locator("#agent-detail-dialog .agent-work-status[title]").count(), 3);
    assert.equal(await page.locator("#agent-detail-dialog .agent-block-map").textContent(), "");
    await page.locator("#agent-detail-dialog .agent-detail-head").click();
    assert.equal(await page.locator("#agent-detail-dialog").getAttribute("open"), "");
    await page.mouse.click(40, 100);
    await page.waitForFunction(() => !document.querySelector("#agent-detail-dialog").open);
    assert.equal(await page.locator("#agent-detail-dialog").getAttribute("open"), null);
    assert.equal(await page.evaluate(() => document.activeElement?.dataset.agentDetail), "nested-task");
    await page.getByRole("button", { name: "Selected", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("#run-log-agent")?.textContent.includes("3 of 5 checks passed"));
    const selectedUpdates = await page.locator("#run-log-agent").textContent();
    assert.match(selectedUpdates, /Designer started onboarding settings|3 of 5 checks passed/);
    assert.doesNotMatch(selectedUpdates, /Waiting for review/);
    await page.getByRole("button", { name: "Material", exact: true }).click();
    const materialUpdates = await page.locator("#run-log-agent").textContent();
    assert.match(materialUpdates, /3 of 5 checks passed/);
    assert.doesNotMatch(materialUpdates, /Designer started onboarding settings/);
    await page.getByRole("button", { name: "All", exact: true }).click();
    await page.locator("#agent-updates-pause").click();
    assert.match(await page.locator("#run-log-agent").textContent(), /Paused/);
    await page.locator("#agent-updates-pause").click();
    assert.match(await page.locator("#run-log-agent").textContent(), /retained material entr/);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true);
    await page.setViewportSize({ width: 1440, height: 1000 });
    if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, "16-agents-desktop-1440x1000.png"), fullPage: false, animations: "disabled" });
    await page.setViewportSize({ width: 1536, height: 1024 });
    await page.evaluate(() => selectProjectScope("project:branch"));
    await page.waitForFunction(() => state.projectId === "project:branch" && document.querySelectorAll("[data-agent-detail]").length >= 2);
    assert.deepEqual(await page.evaluate(() => ({ view: state.view, selectedAgent: state.runLogAgent, filter: state.agentUpdatesFilter })), { view: "agents", selectedAgent: null, filter: "all" });
    assert.doesNotMatch(await page.locator("#view-agents").textContent(), /Review screenshots|3 of 5 checks passed/);
    assert.match(await page.locator("#view-agents").textContent(), /Confirm webhooks/);
    await page.evaluate(() => selectProjectScope("project:fixture"));
    await page.evaluate(() => selectProjectScope("all"));
    await page.waitForFunction(() => state.projectId === "all" && document.querySelector('[data-agent-detail="ctrl"]'));
    assert.equal(await page.locator('[data-agent-detail="ctrl"] [role="progressbar"][aria-valuenow="80"]').count(), 1);
    await page.evaluate(() => selectProjectScope("project:fixture"));
    await page.waitForFunction(() => state.projectId === "project:fixture");
    await openPrimaryView(page, "roles");
    await page.evaluate(() => {
      window.__roleManifestForLoadingTest = state.roleManifests;
      state.roleManifests = null;
      state.roleManifestStatus = "loading";
      renderRoleLibrary();
    });
    assert.equal(await page.locator("#role-library-grid").getAttribute("aria-busy"), "true");
    assert.equal(await page.locator("#view-roles .loading-skeleton i").count(), 12);
    await page.emulateMedia({ reducedMotion: "reduce" });
    assert.equal(await page.locator("#role-library-grid .loading-skeleton i").first().evaluate((node) => parseFloat(getComputedStyle(node).animationDuration) <= 0.001), true);
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.evaluate(() => {
      state.roleManifestStatus = "unavailable";
      state.roleManifestError = "Role roster unavailable for test";
      renderRoleLibrary();
    });
    assert.equal(await page.locator("#role-library-grid .loading-skeleton").count(), 0);
    assert.match(await page.locator("#role-library-grid").textContent(), /Role roster unavailable for test/);
    await page.evaluate(() => {
      state.roleManifests = window.__roleManifestForLoadingTest;
      state.roleManifestStatus = "current";
      state.roleManifestError = "";
      renderRoleLibrary();
    });
    assert.equal(await page.locator(".role-choice").count(), 24);
    assert.equal(await page.locator("#role-library-status").textContent(), "24 roles");
    assert.equal(await page.locator(".role-choice-description").count(), 24);
    assert.doesNotMatch(await page.locator("#role-library-grid").textContent(), /Apply the .* bounded SWARM assignment/);
    await page.setViewportSize({ width: 1280, height: 900 });
    assert.equal(await page.locator(".role-library-layout").evaluate((layout) => layout.scrollWidth <= layout.clientWidth), true);
    assert.equal(await page.locator("#role-library-detail").evaluate((detail) => detail.getBoundingClientRect().right <= innerWidth), true);
    await page.setViewportSize({ width: 1536, height: 1024 });
    const roleFetchesBeforePaging = desktop.requests.filter((request) => request === "/api/role-manifests").length;
    assert.equal(await page.locator('[data-collection-page="roles"], [data-collection-page-status="roles"]').count(), 0);
    assert.equal(desktop.requests.filter((request) => request === "/api/role-manifests").length, roleFetchesBeforePaging);
     assert.match(await page.locator("#view-roles").textContent(), /Role library/);
     assert.doesNotMatch(await page.locator("#view-roles").textContent(), /Server-owned manifests|24 server-owned role manifests/);
    await page.locator("#role-search").fill("Game Development");
    assert.equal(await page.locator(".role-choice").count(), 1);
    assert.equal(await page.locator('.role-choice[data-role-select="developer"]').getAttribute("aria-selected"), "true");
    assert.match(await page.locator('#role-library-detail .role-match').textContent(), /Matched: Game Development · specialization/);
    await page.locator("#role-search").fill("");
    assert.equal(await page.locator(".role-choice").count(), 24);
    await page.locator('.role-choice[data-role-select="developer"]').click();
    assert.equal(await page.locator('#role-library-detail .role-specializations li').count(), 4);
    assert.match(await page.locator('#role-library-detail').textContent(), /Developer[\s\S]*Instructions[\s\S]*Current owners[\s\S]*Review screenshots[\s\S]*Specializations/);
    assert.doesNotMatch(await page.locator('#role-library-detail').textContent(), /nested-task|developer-v1|No authority transfer/);
    await page.evaluate(() => {
      const developer = state.roleManifests.roles.find((role) => role.id === "developer");
      window.__developerInstructionsForDisclosureTest = developer.instructions;
      developer.instructions = [...developer.instructions, "Inspect the relevant implementation", "Exercise the failure boundary", "Record bounded evidence"];
      renderRoleLibrary("developer");
    });
    const roleDisclosure = page.locator("#role-library-detail .role-detail-disclosure").filter({ hasText: "Instructions" });
    const roleDisclosureSummary = roleDisclosure.locator(":scope > summary");
    assert.equal(await roleDisclosure.count(), 1);
    assert.equal(await roleDisclosure.evaluate((details) => details.open), false);
    assert.equal(await roleDisclosureSummary.textContent(), "Instructions");
    assert.equal(await roleDisclosureSummary.evaluate((summary) => summary.getBoundingClientRect().height >= 44), true);
    await roleDisclosureSummary.focus();
    await page.keyboard.press("Enter");
    assert.equal(await roleDisclosure.evaluate((details) => details.open), true);
    assert.ok(await roleDisclosure.locator(".role-detail-disclosure-body").isVisible());
    assert.equal(await roleDisclosureSummary.evaluate((summary) => summary === document.activeElement), true);
    await page.keyboard.press("Enter");
    assert.equal(await roleDisclosure.evaluate((details) => details.open), false);
    assert.equal(await roleDisclosureSummary.evaluate((summary) => summary === document.activeElement), true);
    await page.evaluate(() => {
      state.roleManifests.roles.find((role) => role.id === "developer").instructions = window.__developerInstructionsForDisclosureTest;
      renderRoleLibrary("developer");
    });
    assert.equal(await page.locator('#view-roles .role-avatar.is-mini[aria-label="Developer mascot avatar"]').count(), 2);
    assert.doesNotMatch(await page.locator("#view-roles").textContent(), /Pending/);
    await page.locator(".role-filter > summary").click();
    if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, "12-roles-desktop-1536x1024.png"), fullPage: false, animations: "disabled" });
    await page.locator('.role-choice[data-role-select="architect"]').click();
    assert.equal(await page.locator('#role-library-detail .role-avatar.is-mini[aria-label="Architect mascot avatar"]').count(), 1);
    if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, "12b-roles-architect-desktop-1536x1024.png"), fullPage: false, animations: "disabled" });
    await page.locator('.role-choice[data-role-select="reviewer"]').click();
    assert.match(await page.locator('#role-library-detail').textContent(), /Reviewer one[\s\S]*Reviewer four/);
    assert.doesNotMatch(await page.locator('#role-library-detail').textContent(), /Friendly|Hostile/);
    await page.locator('.role-choice[data-role-select="developer"]').click();
    await page.getByRole("button", { name: "Edit Developer avatar" }).focus();
    await page.keyboard.press("Enter");
    assert.equal(await page.locator("#role-editor").getByRole("button", { name: /Generate avatar/ }).count(), 0);
    assert.equal((await page.locator("#role-field-specializations").inputValue()).split("\n").length, 4);
    await assertDialogFrame(page, "#role-editor");
    assert.doesNotMatch(await page.locator("#role-editor .edge-scroll").evaluate((element) => getComputedStyle(element).scrollbarColor), /^auto$/);
    if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, "28-role-editor-edge-scroll-desktop-1536x1024.png"), fullPage: false, animations: "disabled" });
    await page.getByRole("button", { name: "Close role editor" }).click();
    await page.getByRole("tab", { name: "Review", exact: true }).click();
    assert.equal(await page.locator(".review-row").count(), 7);
     assert.equal(await page.getByRole("button", { name: "Copy proof ID" }).first().isVisible(), true);
    await openPrimaryView(page, "assets");
    await page.evaluate(() => {
      window.__assetsForLoadingTest = state.assets;
      state.assets = null;
      state.assetStatus = "loading";
      renderAssets();
    });
    assert.equal(await page.locator("#asset-gallery").getAttribute("aria-busy"), "true");
    assert.equal(await page.locator("#asset-gallery .loading-skeleton i").count(), 8);
    await page.evaluate(() => {
      state.assetStatus = "unavailable";
      state.assetError = "Asset inventory unavailable for test";
      renderAssets();
    });
    assert.equal(await page.locator("#asset-gallery .loading-skeleton").count(), 0);
    assert.match(await page.locator("#asset-gallery").textContent(), /Asset inventory unavailable for test/);
    await page.evaluate(() => {
      state.assets = window.__assetsForLoadingTest;
      state.assetStatus = "current";
      state.assetError = "";
      const base = structuredClone(state.assets.items[0]);
      state.assets = { ...state.assets, items: Array.from({ length: 20 }, (_, index) => {
        const item = structuredClone(base);
        item.asset_id = "paged-asset-" + index;
        item.presentation.display_name = "Paged asset " + index;
        item.technical.logical_asset_id = "paged-logical-" + index;
        item.preview.url = "/api/assets/" + item.asset_id + "/preview?digest=" + item.technical.digest;
        return item;
      }) };
      renderAssets();
    });
    assert.equal(await page.locator(".asset-tile").count(), 12);
    assert.ok(await page.locator(".asset-tile img").evaluateAll((images) => images.every((image) => image.loading === "lazy" && image.decoding === "async" && image.src.includes("/api/assets/") && image.src.includes("/preview?digest="))));
    const assetFetchesBeforePaging = desktop.requests.filter((request) => request.startsWith("/api/assets?")).length;
    await page.locator('[data-collection-more="assets"]').click();
    assert.equal(await page.locator(".asset-tile").count(), 20);
    assert.equal(await page.evaluate(() => document.activeElement?.dataset.collectionStatus), "assets");
    assert.equal(desktop.requests.filter((request) => request.startsWith("/api/assets?")).length, assetFetchesBeforePaging);
    await page.evaluate(() => {
      state.assets = window.__assetsForLoadingTest;
      state.assetPage = 0;
      renderAssets();
    });
    assert.equal(await page.locator(".asset-tile").count(), 8);
    assert.equal(await page.locator(".asset-tile .asset-list-copy").count(), 0);
    assert.equal(await page.locator(".asset-tile .asset-quick-actions").count(), 8);
    assert.equal(await page.locator('.asset-generation-placeholder[aria-label="Generating"]').count(), 1);
    assert.match(await page.locator('.asset-generation-placeholder[aria-label="Generating"]').textContent(), /Generating[\s\S]*42%/);
    assert.equal(await page.locator('.asset-generation-placeholder img').count(), 0);
    assert.equal(await page.locator(".usage-strip").count(), 0);
    await assertCircleFrame(page, "#profile");
    await assertCircleFrame(page, "#notifications");
    assert.ok(await page.getByRole("button", { name: "Open asset details for Overview direction" }).count() >= 1);
    if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, "20-assets-ready-desktop-1536x1024.png"), fullPage: false, animations: "disabled" });
    const assetTrigger = page.getByRole("button", { name: "Open asset details for Roadmap" });
    await assetTrigger.focus();
    await assetTrigger.click();
    assert.equal(await page.locator("#asset-dialog").evaluate((element) => element.open), true);
    assert.match(await page.locator("#asset-dialog").textContent(), /Roadmap/);
    assert.match(await page.locator("#asset-dialog").textContent(), /Created[\s\S]*Updated[\s\S]*File size[\s\S]*Advanced/);
    assert.equal(await page.locator("#asset-dialog details.asset-advanced").getAttribute("open"), null);
    await page.locator("#asset-dialog details.asset-advanced").click();
    assert.match(await page.locator("#asset-dialog").textContent(), /Immutable ID[\s\S]*MIME type[\s\S]*Digest/);
    await assertDialogFrame(page, "#asset-dialog");
    if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, "15-assets-dialog-desktop-1536x1024.png"), fullPage: false, animations: "disabled" });
    const requestsBeforeTrash = desktop.assetRequests.length;
    await page.locator("#asset-dialog").getByRole("button", { name: "Move to Trash" }).click();
    assert.equal(desktop.assetRequests.length, requestsBeforeTrash);
    assert.match(await page.locator("#asset-dialog").textContent(), /Move this revision to Trash\? You can restore it afterward\./);
    await page.locator("#asset-dialog").getByRole("button", { name: "Move to Trash" }).click();
    await page.locator("#asset-undo-toast").waitFor({ state: "visible" });
    const trashRequest = desktop.assetRequests.at(-1);
    assert.equal(trashRequest.path, "/api/assets/trash");
    assert.equal(trashRequest.payload.asset_id, "asset-roadmap");
    assert.equal(trashRequest.payload.expected_revision, 1);
    assert.match(trashRequest.payload.operation_id, /^asset-trash-/);
    assert.equal(await page.getByRole("button", { name: "Trash", exact: true }).getAttribute("aria-pressed"), "true");
    assert.equal(await page.locator("#asset-dialog").evaluate((element) => element.open), false);
    await page.getByRole("button", { name: "Open asset details for Roadmap" }).click();
    assert.match(await page.locator("#asset-dialog").textContent(), /Purge unavailable · no retention policy is configured\./);
    assert.equal(await page.locator("#asset-dialog").getByRole("button", { name: "Purge unavailable" }).isDisabled(), true);
    await page.getByRole("button", { name: "Close asset details" }).click();
    if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, "21-assets-trash-undo-desktop-1536x1024.png"), fullPage: false, animations: "disabled" });
    await page.getByRole("button", { name: "Undo", exact: true }).click();
    await page.waitForFunction(() => state.assetProjection === "active" && state.assetUndo === null);
    const restoreRequest = desktop.assetRequests.at(-1);
    assert.equal(restoreRequest.path, "/api/assets/restore");
    assert.equal(restoreRequest.payload.asset_id, "asset-roadmap");
    assert.equal(restoreRequest.payload.expected_revision, 2);
    assert.match(restoreRequest.payload.operation_id, /^asset-restore-/);
    assert.equal(await page.getByRole("button", { name: "Library", exact: true }).getAttribute("aria-pressed"), "true");
    assert.equal(await page.getByRole("button", { name: "Open asset details for Roadmap" }).evaluate((element) => element === document.activeElement), true);
    await page.getByRole("button", { name: "Open asset details for Onboarding illustration" }).click();
    assert.match(await page.locator("#asset-dialog").textContent(), /Onboarding illustration[\s\S]*Generating[\s\S]*42%/);
    assert.equal(await page.locator("#asset-dialog img").count(), 0);
    if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, "18-assets-generating-desktop-1536x1024.png"), fullPage: false, animations: "disabled" });
    await page.getByRole("button", { name: "Close asset details" }).click();
    await page.getByRole("button", { name: "Open asset details for Settings option" }).click();
    let releaseRetryAcknowledgement;
    desktop.assetControl.deferredMutations.push(new Promise((resolve) => { releaseRetryAcknowledgement = resolve; }));
    await page.locator("#asset-dialog").getByRole("button", { name: "Retry generation" }).click();
    const assetRetryRequest = desktop.assetRequests.at(-1);
    assert.equal(assetRetryRequest.path, "/api/assets/generation/retry");
    assert.equal(assetRetryRequest.payload.asset_id, "asset-failed");
    assert.match(assetRetryRequest.payload.generation_job_id, /^generation-/);
    assert.match(await page.locator("#asset-dialog").textContent(), /Saving this asset change…/);
    releaseRetryAcknowledgement();
    await page.waitForFunction(() => state.assetMutationPending === null && assetItems().some((item) => item.asset_id === "asset-failed" && item.presentation?.status === "QUEUED"));
    assert.match(await page.locator("#asset-dialog").textContent(), /Queued/);
    await page.getByRole("button", { name: "Close asset details" }).click();
    await page.getByRole("button", { name: "List", exact: true }).click();
    assert.equal(await page.locator(".asset-list-row").count(), 8);
    assert.match(await page.locator(".asset-list-row").first().textContent(), /Type[\s\S]*Updated[\s\S]*Status/);
    assert.doesNotMatch(await page.locator(".asset-list-row").first().textContent(), /Digest|MIME|Immutable ID|Source path/);
    await page.locator(".asset-list-row .asset-list-main").first().click();
    assert.equal(await page.locator("#asset-dialog details.asset-advanced").count(), 1);
    await page.keyboard.press("Escape");
    assert.equal(await page.locator("#asset-dialog").evaluate((element) => element.open), false);
    await page.getByRole("tab", { name: "Settings", exact: true }).click();
     assert.equal(await page.locator("#settings-grid .settings-card-workflow").count(), 1);
    assert.equal(await page.locator('[data-setting-action="replay-tour"]').count(), 1);
    assert.equal(await page.locator("#settings-advanced").count(), 1);
     assert.match(await page.locator("#settings-grid").textContent(), /Workflow[\s\S]*Auto-advance[\s\S]*Usage saver[\s\S]*Enable usage saver[\s\S]*Appearance/);
    assert.equal(await page.getByLabel("Ultrafast", { exact:true }).count(), 0);
     assert.equal(await page.getByLabel("Enable usage saver").isDisabled(), true);
    assert.equal(await page.getByRole("slider", { name: "Task life" }).count(), 0, "Unsupported Settings task life is omitted, not presented as writable");
    assert.equal(await page.locator("#settings-advanced").evaluate(el=>el.open), false);
    assert.equal(await page.locator(".settings-save-bar").isVisible(), false);
     assert.equal(await page.getByLabel("Auto-advance").isDisabled(), true);
    await page.locator("#settings-scope").selectOption("global|global");
    await page.waitForFunction(() => state.settingsScopeType === "global" && state.settingsScopeId === "global");
     assert.equal(await page.locator('.settings-theme-choice input[type="radio"]').count(), 4);
    assert.equal(await page.getByRole("radio", { name: "Midnight" }).isChecked(), true);
    assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), "midnight");
    assert.equal(await page.evaluate(() => localStorage.getItem("swarm.theme.v1")), null);
    const themeRequestsBefore = desktop.requests.length;
    const themeConfigRequestsBefore = desktop.configRequests.length;
    if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, "theme-midnight-desktop-1536x1024.png"), fullPage: false, animations: "disabled" });
    await page.getByRole("radio", { name: "Black" }).click();
    assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), "black");
    assert.equal(await page.evaluate(() => localStorage.getItem("swarm.theme.v1")), "black");
    if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, "theme-black-desktop-1536x1024.png"), fullPage: false, animations: "disabled" });
    await page.getByRole("radio", { name: "Graphite" }).focus();
    await page.keyboard.press("Space");
    assert.equal(await page.getByRole("radio", { name: "Graphite" }).isChecked(), true);
    assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), "graphite");
    if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, "theme-graphite-desktop-1536x1024.png"), fullPage: false, animations: "disabled" });
    await page.getByRole("radio", { name: "Pearl" }).click();
    assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), "pearl");
    assert.deepEqual(await page.evaluate(() => [
      getComputedStyle(document.querySelector(".scope-context summary")).color,
      getComputedStyle(document.querySelector(".top-actions #notifications")).color,
    ]), ["rgb(244, 248, 255)", "rgb(244, 248, 255)"]);
    assert.equal(await page.evaluate(() => state.settingsDraft.size), 0);
    assert.equal(desktop.requests.length, themeRequestsBefore);
    assert.equal(desktop.configRequests.length, themeConfigRequestsBefore);
    if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, "theme-pearl-desktop-1536x1024.png"), fullPage: false, animations: "disabled" });
    const themeReloadPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    await themeReloadPage.addInitScript(() => { if (!window.name) { localStorage.setItem("swarm.theme.v1", "pearl"); window.name = "theme-seeded"; } });
    await mount(themeReloadPage, scopedFixture(), overrides);
    assert.equal(await themeReloadPage.evaluate(() => document.documentElement.dataset.theme), "pearl");
    await themeReloadPage.evaluate(() => localStorage.setItem("swarm.theme.v1", "invalid"));
    await themeReloadPage.reload();
    await themeReloadPage.waitForFunction(() => document.documentElement.dataset.theme === "midnight");
    await themeReloadPage.close();
     await page.evaluate(() => setTheme("midnight"));
     await page.locator("#settings-advanced > summary").click();
     await page.waitForFunction(() => document.querySelector("#settings-advanced")?.open === true);
     assert.equal(await page.getByLabel("Auto-advance").isDisabled(), false);
     assert.equal(await page.getByLabel("Enable usage saver").isDisabled(), false);
     assert.equal(await page.getByLabel("Enable usage saver").isChecked(), false);
    if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, "31-settings-essentials-defaults-desktop-1536x1024.png"), fullPage: false, animations: "disabled" });
    const settingsRequestsBefore = desktop.configRequests.length;
     await page.getByLabel("Auto-advance").click();
     await page.getByLabel("Enable usage saver").click();
     assert.match(await page.getByLabel("Enable usage saver").locator("xpath=following-sibling::span").evaluate((element) => getComputedStyle(element).backgroundImage), /linear-gradient/);
    await page.locator(".settings-segmented label").filter({ hasText: "Fast" }).click();
    assert.match(await page.locator(".settings-save-bar").textContent(), /3 unsaved changes/);
    await page.getByRole("button", { name: "Save changes" }).click();
    await page.waitForFunction(() => state.settingsSaving === false && state.settingsDraft.size === 0);
    assert.equal(desktop.configRequests.length, settingsRequestsBefore + 1);
    assertConfigWriteEnvelope(desktop.configRequests.at(-1), { values: { "automation.mode": "manual", "execution.fast_mode": true, "execution.usage_saver": true } });
    assert.match(await page.locator(".settings-save-bar").textContent(), /Saved/);
    if (evidenceDir) await page.screenshot({ path: path.join(evidenceDir, "20-settings-essentials-desktop-1536x1024.png"), fullPage: false, animations: "disabled" });
    assert.equal(await page.locator("[data-qc-scope]").evaluate((element) => element.scrollWidth > element.clientWidth + 1), false);
    assert.deepEqual(desktop.runtimeErrors, []);
    await page.close();

    const resetPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const resetControl = { failPost: false, deferredPost: null, feed: configDescriptorFixture(), resetRequests: [], resetOperations: new Map() };
    const resetRuntime = await mount(resetPage, scopedFixture(), { ...overrides, configControl: resetControl });
    await resetPage.getByRole("tab", { name: "Settings", exact: true }).click();
    await resetPage.evaluate(() => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.settingAction = "restore";
      button.textContent = "Restore defaults test";
      document.querySelector("#settings-grid").append(button);
    });
    resetPage.once("dialog", (dialog) => dialog.dismiss());
    await resetPage.getByRole("button", { name: "Restore defaults test" }).click();
    assert.equal(resetControl.resetRequests.length, 0);
    resetPage.once("dialog", (dialog) => dialog.accept());
    await resetPage.getByRole("button", { name: "Restore defaults test" }).click();
    await resetPage.waitForFunction(() => state.configResetPending === null);
    assert.equal(resetControl.resetRequests.length, 1);
    assert.equal(resetControl.resetRequests[0].path, "/api/settings/restore");
    assert.deepEqual({ ...resetControl.resetRequests[0].payload, operation_id: "<operation>" }, { scope: { type: "global" }, expected_revision: "global-revision-1", acknowledge: true, operation_id: "<operation>" });
    assert.match(resetControl.resetRequests[0].payload.operation_id, /^console-config-reset-global-/);
    assert.deepEqual(resetRuntime.runtimeErrors, []);
    await resetPage.close();

    const retryPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const retryControl = { failPost: false, feed: configDescriptorFixture(), resetRequests: [], resetOperations: new Map(), failReset: "connection" };
    const retryRuntime = await mount(retryPage, scopedFixture(), { ...overrides, configControl: retryControl });
    await retryPage.evaluate(() => resetSettingsScope("global").catch((error) => error.message));
    const ambiguousOperationId = retryControl.resetRequests.at(-1).payload.operation_id;
    retryControl.failReset = null;
    await retryPage.evaluate(() => resetSettingsScope("global"));
    assert.equal(retryControl.resetRequests.at(-1).payload.operation_id, ambiguousOperationId);
    retryControl.failReset = "conflict";
    await retryPage.evaluate(() => resetSettingsScope("global").catch((error) => error.message));
    const conflictOperationId = retryControl.resetRequests.at(-1).payload.operation_id;
    retryControl.failReset = null;
    await retryPage.evaluate(() => resetSettingsScope("global"));
    assert.notEqual(retryControl.resetRequests.at(-1).payload.operation_id, conflictOperationId);
    assert.equal(retryRuntime.runtimeErrors.length, 2);
    assert.match(retryRuntime.runtimeErrors[0], /Failed to load resource: net::ERR_FAILED/);
    assert.match(retryRuntime.runtimeErrors[1], /status of 409 \(Conflict\)/);
    await retryPage.close();

    let releaseStaleReset;
    const staleResetControl = { failPost: false, feed: configDescriptorFixture(), resetRequests: [], resetOperations: new Map(), deferredResets: [new Promise((resolve) => { releaseStaleReset = resolve; })] };
    const staleResetPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const staleResetRuntime = await mount(staleResetPage, scopedFixture(), { ...overrides, configControl: staleResetControl });
    const staleResetPromise = staleResetPage.evaluate(() => resetSettingsScope("global"));
    await staleResetPage.waitForFunction(() => state.configResetPending !== null);
    await staleResetPage.evaluate(() => { state.settingsScopeType = "project"; state.settingsScopeId = "project:fixture"; });
    releaseStaleReset();
    assert.equal((await staleResetPromise).applied, false);
    assert.equal(await staleResetPage.evaluate(() => state.config.revision), "global-revision-1");
    assert.deepEqual(staleResetRuntime.runtimeErrors, []);
    await staleResetPage.close();

    const scopedResetPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const projectCursor = { event_seq: 18, event_digest: "f".repeat(64) };
    const projectConfig = { ...configDescriptorFixture(), scope: { type: "project", project_id: "project:fixture", accepted_cursor: projectCursor }, revision: "project-revision-3" };
    const scopedResetControl = { failPost: false, feed: projectConfig, resetRequests: [], resetOperations: new Map(), ctrlFeed: structuredClone(fixture.ctrlSettings) };
    const scopedResetRuntime = await mount(scopedResetPage, scopedFixture(), { ...overrides, configControl: scopedResetControl });
    await scopedResetPage.evaluate(() => { state.settingsScopeType = "project"; state.settingsScopeId = "project:fixture"; });
    await scopedResetPage.evaluate(() => resetSettingsScope("project"));
    assert.deepEqual({ ...scopedResetControl.resetRequests.at(-1).payload, operation_id: "<operation>" }, { scope: { type: "project", project_id: "project:fixture", accepted_cursor: projectCursor }, expected_revision: "project-revision-3", acknowledge: true, operation_id: "<operation>" });
    assert.equal(scopedResetControl.resetRequests.at(-1).path, "/api/config/reset");
    await scopedResetPage.evaluate(() => { state.settingsScopeType = "ctrl"; state.settingsScopeId = state.ctrlSettings.ctrl_id; });
    await scopedResetPage.evaluate(() => resetSettingsScope("ctrl"));
    assert.deepEqual({ ...scopedResetControl.resetRequests.at(-1).payload, operation_id: "<operation>" }, { ctrl_id: fixture.ctrlSettings.ctrl_id, expected_revision: fixture.ctrlSettings.revision, acknowledge: true, operation_id: "<operation>" });
    assert.equal(scopedResetControl.resetRequests.at(-1).path, "/api/ctrl-settings/reset");
    assert.deepEqual(scopedResetRuntime.runtimeErrors, []);
    await scopedResetPage.close();

    const deepLinkPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const deepLink = await mount(deepLinkPage, scopedFixture(), { ...overrides, initialURL: "http://swarm.test/?project=project%3Afixture#roles" });
    assert.deepEqual(await deepLinkPage.evaluate(() => ({ view: state.view, projectId: state.projectId })), { view: "roles", projectId: "project:fixture" });
    assert.equal(await deepLinkPage.locator("#view-roles").isVisible(), true);
    await deepLinkPage.evaluate(() => {
      state.overview.navigation.projects = state.overview.navigation.projects.filter((project) => project.id !== "project:fixture");
      renderProjectNavigation();
    });
    assert.deepEqual(await deepLinkPage.evaluate(() => ({ view: state.view, projectId: state.projectId })), { view: "roles", projectId: "all" });
    assert.match(await deepLinkPage.locator("#scope-change-status").textContent(), /is unavailable\. Showing All projects/);
    assert.equal(await deepLinkPage.locator("#scope-change-status").isVisible(), true);
    assert.deepEqual(deepLink.runtimeErrors, []);
    await deepLinkPage.close();

    const noManifestPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const noManifestOverview = scopedFixture();
    delete noManifestOverview.project_view;
    const noManifest = await mount(noManifestPage, noManifestOverview, overrides);
    await noManifestPage.locator('#project-navigation [data-project-id="project:fixture"]').click();
    assert.equal(await noManifestPage.locator("[data-project-tab]").count(), 0);
    assert.deepEqual(noManifest.runtimeErrors, []);
    await noManifestPage.close();

    const unknownPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const unknownOverview = scopedFixture();
    unknownOverview.project_inventory = { state: "UNKNOWN", available: false, source: "host_projects" };
    unknownOverview.navigation.project_inventory = structuredClone(unknownOverview.project_inventory);
    unknownOverview.navigation.projects = [];
    const unknown = await mount(unknownPage, unknownOverview, overrides);
    assert.equal(await unknownPage.locator("#project-navigation").textContent(), "Saved projects unavailable");
    assert.equal(await unknownPage.locator("#project-scope-filter").getAttribute("aria-disabled"), "true");
    assert.match(await unknownPage.locator("#overview-project-cards").textContent(), /Project team is unavailable/);
    assert.equal(await unknownPage.locator("#overview-summary").textContent(), "Team unavailable");
    assert.deepEqual(unknown.runtimeErrors, []);
    await unknownPage.close();

    const unsupportedConfigPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const unsupportedConfigFeed = configDescriptorFixture();
    unsupportedConfigFeed.descriptors = unsupportedConfigFeed.descriptors.filter((descriptor) => descriptor.key !== "execution.usage_saver");
    unsupportedConfigFeed.editable = unsupportedConfigFeed.editable.filter((key) => key !== "execution.usage_saver");
    const unsupportedConfig = await mount(unsupportedConfigPage, scopedFixture(), { ...overrides, configControl: { failPost: false, deferredPost: null, feed: unsupportedConfigFeed } });
    await unsupportedConfigPage.evaluate(() => setView("settings"));
    await unsupportedConfigPage.locator("#settings-scope").selectOption("global|global");
    assert.equal(await unsupportedConfigPage.getByLabel("Enable usage saver").isDisabled(), true);
    assert.match(await unsupportedConfigPage.locator("#settings-grid").textContent(), /Usage saver[\s\S]*Unavailable until the canonical setting is exposed\./);
    assert.deepEqual(unsupportedConfig.runtimeErrors, []);
    await unsupportedConfigPage.close();

    const tabletPage = await browser.newPage({ viewport: { width: 834, height: 1112 } });
    const tablet = await mount(tabletPage, scopedFixture(), overrides);
    await assertSharedCircleGeometry(tabletPage, ["#profile", "#notifications", ".scope-dot", ".agent-avatar-token", "#message-launcher"]);
    assert.equal(await tabletPage.locator("#notifications").evaluate((notification) => {
      const profile = document.querySelector("#profile");
      return Boolean(notification.compareDocumentPosition(profile) & Node.DOCUMENT_POSITION_FOLLOWING)
        && getComputedStyle(notification.closest(".top-actions")).justifyContent === "flex-end";
    }), true);
    assert.equal(await tabletPage.locator(".top-actions #profile").count(), 1);
    if (evidenceDir) await tabletPage.screenshot({ path: path.join(evidenceDir, "shell-profile-sidebar-tablet-834x1112.png"), fullPage: false, animations: "disabled" });
    if (evidenceDir) await tabletPage.screenshot({ path: path.join(evidenceDir, "circle-invariant-overview-tablet-834x1112.png"), fullPage: false, animations: "disabled" });
    assert.equal(await tabletPage.locator("#overview-project-cards .overview-hierarchy-project").count(), 4);
    await tabletPage.waitForFunction(() => [...document.querySelectorAll("[data-overview-hierarchy-edge]")].every((path) => Boolean(path.getAttribute("d"))));
    assert.equal(await tabletPage.locator("#overview-project-cards .overview-node-open").evaluateAll((nodes) => nodes.every((node) => node.getBoundingClientRect().height >= 68)), true);
    assert.equal(await tabletPage.locator("#overview-project-cards [data-overview-zoom]").evaluateAll((controls) => controls.length === 3 && controls.every((control) => control.getBoundingClientRect().width >= 44 && control.getBoundingClientRect().height >= 44)), true);
    if (evidenceDir) await tabletPage.screenshot({ path: path.join(evidenceDir, "overview-hierarchy-tablet-834x1112.png"), fullPage: false, animations: "disabled" });
    assert.equal(await tabletPage.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false);
    await assertCircleFrame(tabletPage, "#profile");
    await assertCircleFrame(tabletPage, "#notifications");
    assert.equal(await tabletPage.locator("#overview-project-cards [data-overview-project-id]").evaluateAll((elements) => elements.every((element) => {
      const box = element.getBoundingClientRect();
      return box.height >= 44 && box.right <= document.documentElement.clientWidth;
    })), true);
    await tabletPage.evaluate(() => selectProjectScope("project:fixture"));
    await tabletPage.evaluate(() => setView("agents"));
    assert.equal(await tabletPage.locator("#view-agents [data-agent-detail]").evaluateAll((rows) => rows.length >= 2 && rows.every((row) => row.getBoundingClientRect().height >= 44)), true);
    assert.equal(await tabletPage.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true);
    const tabletAgentTrigger = tabletPage.locator('#view-agents [data-agent-detail="nested-task"]');
    await tabletAgentTrigger.click();
    await assertDialogFrame(tabletPage, "#agent-detail-dialog");
    const tabletAgentDrawer = await tabletPage.locator("#agent-detail-dialog").evaluate((dialog) => { const box = dialog.getBoundingClientRect(); return { left: box.left, right: box.right, width: box.width, viewport: innerWidth }; });
    assert.ok(Math.abs(tabletAgentDrawer.right - tabletAgentDrawer.viewport) <= 1 && tabletAgentDrawer.left > 0 && tabletAgentDrawer.width < tabletAgentDrawer.viewport, JSON.stringify(tabletAgentDrawer));
    if (evidenceDir) await tabletPage.screenshot({ path: path.join(evidenceDir, "17-agents-detail-tablet-834x1112.png"), fullPage: false, animations: "disabled" });
    await tabletPage.locator("#agent-detail-dialog .agent-detail-head").click();
    assert.equal(await tabletPage.locator("#agent-detail-dialog").getAttribute("open"), "");
    await tabletPage.mouse.click(20, 120);
    await tabletPage.waitForFunction(() => !document.querySelector("#agent-detail-dialog").open);
    assert.equal(await tabletAgentTrigger.evaluate((element) => element === document.activeElement), true);
    assert.equal(await tabletPage.locator('#view-agents [data-label="Progress"]').evaluateAll((cells) => cells.every((cell) => {
      const box = cell.getBoundingClientRect();
      const row = cell.closest('.agent-table-row').getBoundingClientRect();
      return box.width >= 100 && box.left >= row.left && box.right <= row.right - 40 && cell.scrollWidth <= cell.clientWidth;
    })), true);
    assert.equal(await tabletPage.locator('.agent-table-row').first().evaluate((row) => getComputedStyle(row).gridTemplateColumns.split(' ').length), 2);
    if (evidenceDir) await tabletPage.screenshot({ path: path.join(evidenceDir, "16-agents-tablet-834x1112.png"), fullPage: false, animations: "disabled" });
    await openPrimaryView(tabletPage, "roles");
    const tabletGrid = tabletPage.locator("#role-library-grid");
    assert.equal(await tabletGrid.evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length), 3);
    assert.equal(await tabletGrid.evaluate((element) => getComputedStyle(element).overflowY), "visible");
    assert.equal(await tabletPage.locator('.role-choice[tabindex="0"]').count(), 1);
    assert.equal(await tabletPage.locator(".role-choice-description").count(), 24);
    if (evidenceDir) await tabletPage.screenshot({ path: path.join(evidenceDir, "13-roles-tablet-834x1112.png"), fullPage: false, animations: "disabled" });
    await tabletPage.locator('.role-choice[tabindex="0"]').focus();
    await tabletPage.keyboard.press("ArrowRight");
    assert.equal(await tabletPage.locator('.role-choice[aria-selected="true"]').getAttribute("data-role-select"), "analyst");
    await tabletPage.keyboard.press("ArrowDown");
    assert.equal(await tabletPage.locator('.role-choice[aria-selected="true"]').getAttribute("data-role-select"), "auditor");
    await tabletPage.keyboard.press("Home");
    assert.equal(await tabletPage.locator('.role-choice[aria-selected="true"]').getAttribute("data-role-select"), "accountant");
    const tabletPageLastRole = await tabletPage.locator(".role-choice").last().getAttribute("data-role-select");
    await tabletPage.keyboard.press("End");
    assert.equal(await tabletPage.locator('.role-choice[aria-selected="true"]').getAttribute("data-role-select"), tabletPageLastRole);
    assert.equal(await tabletPage.locator('.role-choice[aria-selected="true"]').evaluate((element) => {
      const grid = document.querySelector("#role-library-grid").getBoundingClientRect();
      const choice = element.getBoundingClientRect();
      return choice.top >= grid.top && choice.bottom <= grid.bottom;
    }), true);
    await tabletPage.keyboard.press("Home");
    await tabletPage.keyboard.press("Tab");
    assert.equal(await tabletPage.evaluate(() => document.activeElement?.getAttribute("aria-label")), "Edit Accountant avatar");
    assert.equal(await tabletPage.locator(".role-avatar-trigger").evaluate((element) => {
      const box = element.getBoundingClientRect();
      return box.width >= 44 && box.height >= 44;
    }), true);
    await tabletPage.getByRole("button", { name: "Edit Accountant avatar" }).click();
    await assertDialogFrame(tabletPage, "#role-editor");
    assert.equal(await tabletPage.locator("#role-editor button").evaluateAll((elements) => elements.filter((element) => !element.disabled).every((element) => {
      const box = element.getBoundingClientRect();
      return box.width >= 44 && box.height >= 44;
    })), true);
    await tabletPage.evaluate(() => renderRoleLibrary());
    await tabletPage.getByRole("button", { name: "Cancel" }).click();
    await tabletPage.waitForFunction(() => document.activeElement?.getAttribute("aria-label") === "Edit Accountant avatar");
    assert.equal(await tabletPage.evaluate(() => document.activeElement?.getAttribute("aria-label")), "Edit Accountant avatar");
    await tabletPage.getByRole("button", { name: "Edit Accountant avatar" }).click();
    await tabletPage.keyboard.press("Escape");
    await tabletPage.waitForFunction(() => document.activeElement?.getAttribute("aria-label") === "Edit Accountant avatar");
    assert.equal(await tabletPage.locator("#role-editor").isVisible(), false);
    assert.equal(await tabletPage.evaluate(() => document.activeElement?.getAttribute("aria-label")), "Edit Accountant avatar");
    assert.equal(await tabletPage.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false);
    await tabletPage.evaluate(() => setView("assets"));
    await tabletPage.locator(".asset-tile .asset-image-button").first().click();
    await assertDialogFrame(tabletPage, "#asset-dialog");
    if (evidenceDir) await tabletPage.screenshot({ path: path.join(evidenceDir, "16-assets-dialog-tablet-834x1112.png"), fullPage: false, animations: "disabled" });
    await tabletPage.keyboard.press("Escape");
    await tabletPage.evaluate(() => setView("settings"));
    assert.equal(await tabletPage.locator("#settings-grid").evaluate((element) => element.scrollWidth <= element.clientWidth + 1), true);
    await tabletPage.waitForFunction(() => { const elements = [...document.querySelectorAll(".settings-switch")]; return elements.length > 0 && elements.every((element) => element.getBoundingClientRect().height >= 44); });
    assert.equal(await tabletPage.locator(".settings-switch").evaluateAll((elements) => elements.every((element) => element.getBoundingClientRect().height >= 44)), true);
    if (evidenceDir) await tabletPage.screenshot({ path: path.join(evidenceDir, "21-settings-essentials-tablet-834x1112.png"), fullPage: false, animations: "disabled" });
    for (const [label, value] of [["Midnight", "midnight"], ["Black", "black"], ["Graphite", "graphite"], ["Pearl", "pearl"]]) {
      await tabletPage.getByRole("radio", { name: label }).click();
      assert.equal(await tabletPage.evaluate(() => document.documentElement.dataset.theme), value);
      assert.equal(await tabletPage.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true);
      if (evidenceDir) await tabletPage.screenshot({ path: path.join(evidenceDir, `theme-${value}-tablet-834x1112.png`), fullPage: false, animations: "disabled" });
    }
    await tabletPage.evaluate(() => setTheme("midnight"));
    assert.deepEqual(tablet.runtimeErrors, []);
    await tabletPage.close();

    const mobilePage = await browser.newPage({ viewport: { width: 390, height: 844 } });
    const mobile = await mount(mobilePage, overflowingProjectFixture(), overrides);
    await assertSharedCircleGeometry(mobilePage, ["#profile", "#mobile-message-action", ".agent-avatar-token"]);
    await mobilePage.locator("#mobile-menu-button").click();
    await mobilePage.locator("#console-drawer").waitFor({ state: "visible" });
    await assertSharedCircleGeometry(mobilePage, ["#console-drawer .scope-dot", ".support-mark"]);
    if (evidenceDir) await mobilePage.screenshot({ path: path.join(evidenceDir, "circle-invariant-drawer-mobile-390x844.png"), fullPage: false, animations: "disabled" });
    await mobilePage.locator("#drawer-close").click();
    await mobilePage.evaluate((metrics) => {
      state.overview.overview_metrics = metrics;
      renderOverviewMetrics();
    }, { ...overviewMetricFixture, usage: { ...overviewMetricFixture.usage, used_tokens: 3_207_000_000 } });
    assert.equal(await mobilePage.locator("#metric-usage-value").textContent(), "—");
    assert.equal(await mobilePage.locator('.usage-chart-card').evaluate((card) => {
      const value = card.querySelector("#metric-usage-value").getBoundingClientRect();
      const bounds = card.getBoundingClientRect();
      return value.left >= bounds.left && value.right <= bounds.right && value.bottom <= bounds.bottom && bounds.right <= innerWidth;
    }), true);
    await mobilePage.locator('[data-overview-metric="usage"]').focus();
    await mobilePage.keyboard.press('Space');
    await assertMetricDetailContainment(mobilePage);
    await mobilePage.getByRole('button',{name:'Close metric details',exact:true}).click();
    assert.equal(await mobilePage.locator('[data-overview-metric="usage"]').evaluate(el => el === document.activeElement), true);
    await mobilePage.waitForFunction(() => [...document.querySelectorAll("[data-overview-hierarchy-edge]")].every((path) => Boolean(path.getAttribute("d"))));
    assert.equal(await mobilePage.locator("#overview-project-cards .overview-hierarchy-children").evaluateAll((groups) => groups.every((group) => getComputedStyle(group).gridTemplateColumns.split(" ").length === 1)), true);
    assert.equal(await mobilePage.locator("#overview-project-cards .overview-node-inspect").evaluateAll((inspects) => inspects.every((inspect) => inspect.getBoundingClientRect().width >= 44 && inspect.getBoundingClientRect().height >= 44 && getComputedStyle(inspect).opacity === "1")), true);
    assert.equal(await mobilePage.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true);
    if (evidenceDir) await mobilePage.screenshot({ path: path.join(evidenceDir, "overview-hierarchy-mobile-390x844.png"), fullPage: false, animations: "disabled" });
    await mobilePage.evaluate(() => { setView("settings"); renderSettings(); });
    for (const [label, value] of [["Midnight", "midnight"], ["Black", "black"], ["Graphite", "graphite"], ["Pearl", "pearl"]]) {
      await mobilePage.getByRole("radio", { name: label }).click();
      assert.equal(await mobilePage.evaluate(() => document.documentElement.dataset.theme), value);
      assert.equal(await mobilePage.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true);
      if (evidenceDir) await mobilePage.screenshot({ path: path.join(evidenceDir, `theme-${value}-mobile-390x844.png`), fullPage: false, animations: "disabled" });
    }
    await mobilePage.evaluate(() => { setTheme("midnight"); setView("overview"); });
    assert.equal(await mobilePage.locator("#message-launcher").isVisible(), false);
    assert.equal(await mobilePage.locator("#mobile-message-action").isVisible(), true);
    assert.equal(await mobilePage.locator(".mobile-message-footer .mobile-destination").count(), 5);
    assert.equal(await mobilePage.locator("#mobile-message-action .message-mascot-silhouette").count(), 1);
    await mobilePage.locator('.mobile-message-footer [data-view="assets"]').click();
    assert.equal(await mobilePage.evaluate(() => state.view), "assets");
    assert.equal(await mobilePage.locator('.mobile-message-footer [data-view="assets"]').getAttribute("aria-current"), "page");
    const mobileMessageBox = await mobilePage.locator("#mobile-message-action").boundingBox();
    assert.ok(mobileMessageBox && mobileMessageBox.width >= 44 && mobileMessageBox.height >= 44);
    await mobilePage.locator("#mobile-message-action").click();
    assert.equal(await mobilePage.locator("#message-composer").isVisible(), true);
    assert.deepEqual(await mobilePage.locator("#message-composer").evaluate((element) => {
      const box = element.getBoundingClientRect();
      return { top: Math.round(box.top), left: Math.round(box.left), right: Math.round(innerWidth - box.right), bottom: Math.round(innerHeight - box.bottom) };
    }), { top: 0, left: 0, right: 0, bottom: 0 });
    assert.equal(await mobilePage.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true);
    await mobilePage.locator("#message-draft").fill("Mobile draft remains local.");
    if (evidenceDir) await mobilePage.screenshot({ path: path.join(evidenceDir, "41-message-unavailable-mobile-390x844.png"), fullPage: false, animations: "disabled" });
    await mobilePage.keyboard.press("Escape");
    assert.equal(await mobilePage.locator("#message-composer").isVisible(), false);
    assert.equal(await mobilePage.evaluate(() => document.activeElement?.id), "mobile-message-action");
    const menuButton = mobilePage.locator("#mobile-menu-button");
    const menuBox = await menuButton.boundingBox();
    assert.ok(menuBox && menuBox.width >= 44 && menuBox.height >= 44);
    await assertCircleFrame(mobilePage, "#profile", 44);
    await assertCircleFrame(mobilePage, "#notifications", 44);
    assert.equal(await mobilePage.locator("#notifications").isVisible(), true);
    await assertCircleFrame(mobilePage, "#notifications", 44);
    await mobilePage.evaluate(() => showError("Project refresh failed"));
    const errorBox = await mobilePage.locator("#error-surface").boundingBox();
    assert.ok(errorBox && menuBox && errorBox.y >= menuBox.y + menuBox.height);
    assert.ok((await mobilePage.getByRole("button", { name: "Refresh SWARM" }).boundingBox())?.height >= 44);
    await menuButton.click();
    assert.equal(await mobilePage.locator("#console-drawer").getAttribute("aria-hidden"), "false");
    assert.equal(await mobilePage.locator("#profile").isVisible(), false);
    assert.equal(await mobilePage.locator("#console-drawer #profile").count(), 0);
    assert.doesNotMatch(await mobilePage.locator("#console-drawer").textContent(), /\bLive\b/);
    if (evidenceDir) await mobilePage.screenshot({ path: path.join(evidenceDir, "shell-profile-sidebar-mobile-390x844.png"), fullPage: false, animations: "disabled" });
    assert.equal(await mobilePage.locator("#console-drawer .brand-wordmark").isVisible(), true);
    assert.ok((await mobilePage.locator("#drawer-close").boundingBox())?.height >= 44);
    assert.equal(await mobilePage.locator(".workspace").evaluate((element) => element.inert), true);
    assert.equal(await mobilePage.locator("#project-navigation button").evaluateAll((elements) => elements.every((element) => element.getBoundingClientRect().height >= 44)), true);
    assert.equal(await mobilePage.locator("#project-navigation").evaluate((element) => getComputedStyle(element).overflowY), "auto");
    assert.equal(await mobilePage.locator("#project-navigation").evaluate((element) => element.scrollHeight > element.clientHeight), true);
    assert.equal(await mobilePage.locator(".project-navigation").evaluate((element) => getComputedStyle(element).overflowY), "hidden");
    assert.equal(await mobilePage.locator(".nav-footer").evaluate((element) => element.getBoundingClientRect().bottom <= document.querySelector("#console-drawer").getBoundingClientRect().bottom), true);
    assert.equal(await mobilePage.locator("#project-navigation").textContent().then((text) => text.includes("All projects")), false);
    assert.equal(await mobilePage.locator('#project-navigation [data-project-id="project:overflow-24"]').count(), 1);
    await mobilePage.keyboard.press("Escape");
    assert.equal(await menuButton.evaluate((element) => element === document.activeElement), true);
    await mobilePage.locator('.mobile-message-footer [data-view="roles"]').click();
    const mobileGrid = mobilePage.locator("#role-library-grid");
    assert.equal(await mobileGrid.evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length), 2);
    assert.equal(await mobileGrid.evaluate((element) => getComputedStyle(element).overflowY), "visible");
    assert.equal(await mobilePage.locator('.role-choice[tabindex="0"]').count(), 1);
    assert.equal(await mobilePage.locator(".role-choice-description").count(), 24);
    assert.ok(await mobilePage.locator(".role-choice-description").evaluateAll((items) => items.every((item) => getComputedStyle(item).webkitLineClamp === "2")));
    await mobilePage.setViewportSize({ width: 610, height: 800 });
    const mobileHeaderGeometry = await mobilePage.locator(".top-actions").evaluate((actions) => {
      const scope = document.querySelector(".scope-context").getBoundingClientRect();
      const controls = [...actions.querySelectorAll(":scope > button")].map((button) => ({ rect: button.getBoundingClientRect().toJSON(), overflow: getComputedStyle(button).overflow }));
      return { scope: scope.toJSON(), controls, viewport: innerWidth };
    });
    assert.ok(mobileHeaderGeometry.scope.width <= 160 && mobileHeaderGeometry.scope.right <= mobileHeaderGeometry.viewport, JSON.stringify(mobileHeaderGeometry));
    assert.equal(mobileHeaderGeometry.controls.every(({ rect, overflow }) => rect.width >= 44 && rect.height >= 44 && overflow === "visible"), true);
    const mobileRoleTrigger = mobilePage.locator('.role-choice[data-role-select="developer"]');
    await mobileRoleTrigger.click();
    assert.equal(await mobilePage.locator("#role-library-detail").getAttribute("role"), "dialog");
    assert.equal(await mobilePage.locator("#role-library-detail").getAttribute("aria-modal"), "true");
    assert.equal(await mobilePage.locator("#role-library-detail").evaluate((detail) => { const box = detail.getBoundingClientRect(); return Math.abs(box.left) <= 1 && Math.abs(box.top) <= 1 && Math.abs(box.width - innerWidth) <= 1 && Math.abs(box.height - innerHeight) <= 1; }), true);
    assert.doesNotMatch(await mobilePage.locator("#role-library-detail").textContent(), /Metadata only|server-owned|Profession · not authority|No authority transfer|Built in/i);
    await mobilePage.getByRole("button", { name: "Back to roles" }).click();
    assert.equal(await mobileRoleTrigger.evaluate((element) => element === document.activeElement), true);
    await mobilePage.setViewportSize({ width: 390, height: 844 });
    await mobilePage.evaluate(() => clearError());
    if (evidenceDir) await mobilePage.screenshot({ path: path.join(evidenceDir, "14-roles-mobile-390x844.png"), fullPage: false, animations: "disabled" });
    const mobileRoleOrder = await mobilePage.locator(".role-choice").evaluateAll((items) => items.map((item) => item.dataset.roleSelect));
    await mobilePage.locator(".role-choice").first().focus();
    await mobilePage.keyboard.press("ArrowRight");
    assert.equal(await mobilePage.locator('.role-choice[aria-selected="true"]').getAttribute("data-role-select"), mobileRoleOrder[1]);
    await mobilePage.keyboard.press("ArrowDown");
    assert.equal(await mobilePage.locator('.role-choice[aria-selected="true"]').getAttribute("data-role-select"), mobileRoleOrder[3]);
    await mobilePage.keyboard.press("Home");
    const mobilePageLastRole = await mobilePage.locator(".role-choice").last().getAttribute("data-role-select");
    await mobilePage.keyboard.press("End");
    assert.equal(await mobilePage.locator('.role-choice[aria-selected="true"]').getAttribute("data-role-select"), mobilePageLastRole);
    assert.equal(await mobilePage.locator('.role-choice[aria-selected="true"]').evaluate((element) => {
      const grid = document.querySelector("#role-library-grid").getBoundingClientRect();
      const choice = element.getBoundingClientRect();
      return choice.top >= grid.top && choice.bottom <= grid.bottom;
    }), true);
    await mobilePage.evaluate(async () => { await selectProjectScope("project:fixture"); setView("agents"); });
    await mobilePage.waitForFunction(() => document.querySelectorAll("[data-agent-detail]").length >= 2);
    assert.equal(await mobilePage.locator("#view-agents [data-agent-detail]").evaluateAll((rows) => rows.every((row) => row.getBoundingClientRect().height >= 44)), true);
    assert.equal(await mobilePage.locator('#view-agents [data-label="Progress"]').evaluateAll((cells) => cells.every((cell) => {
      const box = cell.getBoundingClientRect();
      const row = cell.closest('.agent-table-row').getBoundingClientRect();
      return box.width >= 100 && box.left >= row.left && box.right <= row.right - 40 && cell.scrollWidth <= cell.clientWidth;
    })), true);
    assert.equal(await mobilePage.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true);
    await mobilePage.locator('#view-agents [role="progressbar"]').first().scrollIntoViewIfNeeded();
    if (evidenceDir) await mobilePage.screenshot({ path: path.join(evidenceDir, "18-agents-mobile-390x844.png"), fullPage: false, animations: "disabled" });
    await mobilePage.locator('#view-agents [data-agent-detail="nested-task"]').click();
    await assertDialogFrame(mobilePage, "#agent-detail-dialog");
    const mobileAgentDrawer = await mobilePage.locator("#agent-detail-dialog").evaluate((dialog) => { const box = dialog.getBoundingClientRect(); return { left: box.left, top: box.top, width: box.width, height: box.height, viewportWidth: innerWidth, viewportHeight: innerHeight }; });
    assert.deepEqual(mobileAgentDrawer, { left: 0, top: 0, width: mobileAgentDrawer.viewportWidth, height: mobileAgentDrawer.viewportHeight, viewportWidth: mobileAgentDrawer.viewportWidth, viewportHeight: mobileAgentDrawer.viewportHeight });
    if (evidenceDir) await mobilePage.screenshot({ path: path.join(evidenceDir, "19-agents-detail-mobile-390x844.png"), fullPage: false, animations: "disabled" });
    await mobilePage.locator("#agent-detail-dialog .agent-detail-head").click();
    assert.equal(await mobilePage.locator("#agent-detail-dialog").getAttribute("open"), "");
    await mobilePage.keyboard.press("Escape");
    await mobilePage.evaluate(() => setView("roles"));
    await mobilePage.locator('.role-choice[aria-selected="true"]').focus();
    await mobilePage.keyboard.press("Home");
    await mobilePage.keyboard.press("Enter");
    await mobilePage.locator("#role-library-detail.is-mobile-open").waitFor({ state: "visible" });
    await mobilePage.waitForFunction(() => document.activeElement?.getAttribute("aria-label") === "Back to roles");
    assert.equal(await mobilePage.evaluate(() => document.activeElement?.getAttribute("aria-label")), "Back to roles");
    await mobilePage.getByRole("button", { name: "Edit Accountant avatar" }).click();
    await assertDialogFrame(mobilePage, "#role-editor");
    assert.equal(await mobilePage.locator("#role-editor").evaluate((element) => {
      const box = element.getBoundingClientRect();
      return box.left >= 0 && box.right <= innerWidth && box.top >= 0 && box.bottom <= innerHeight;
    }), true);
    assert.equal(await mobilePage.locator("#role-editor button").evaluateAll((elements) => elements.filter((element) => !element.disabled).every((element) => {
      const box = element.getBoundingClientRect();
      return box.width >= 44 && box.height >= 44;
    })), true);
    assert.equal(await mobilePage.locator(".role-editor-body").evaluate((element) => getComputedStyle(element).overflowY), "auto");
    assert.equal(await mobilePage.locator(".role-editor-fields").evaluate((element) => getComputedStyle(element).overflowY), "visible");
    assert.doesNotMatch(await mobilePage.locator("#role-editor .edge-scroll").evaluate((element) => getComputedStyle(element).scrollbarColor), /^auto$/);
    if (evidenceDir) await mobilePage.screenshot({ path: path.join(evidenceDir, "29-role-editor-edge-scroll-mobile-390x844.png"), fullPage: false, animations: "disabled" });
    await mobilePage.keyboard.press("Escape");
    await mobilePage.waitForTimeout(50);
    assert.equal(await mobilePage.locator("#role-editor").isVisible(), false);
    assert.equal(await mobilePage.evaluate(() => document.activeElement?.getAttribute("aria-label")), "Edit Accountant avatar");
    assert.equal(await mobilePage.locator("#role-library-detail").isVisible(), true, "Escape closes only the topmost role editor");
    await mobilePage.keyboard.press("Escape");
    assert.equal(await mobilePage.locator("#role-library-detail").isVisible(), false);
    await menuButton.click();
    await mobilePage.getByRole("button", { name: /^swarm\b/i }).click();
    assert.equal(await mobilePage.locator("#view-roles").isVisible(), true, "project selection preserves the active Roles route");
    await mobilePage.locator('.mobile-message-footer [data-view="overview"]').click();
    if (await mobilePage.locator('[data-notification-toast-action="dismiss"]').isVisible().catch(() => false)) await mobilePage.locator('[data-notification-toast-action="dismiss"]').click();
    await mobilePage.evaluate(() => setView("assets"));
    if (evidenceDir) await mobilePage.screenshot({ path: path.join(evidenceDir, "24-assets-ready-mobile-390x844.png"), fullPage: false, animations: "disabled" });
    await mobilePage.locator(".asset-tile .asset-image-button").first().click();
    await assertDialogFrame(mobilePage, "#asset-dialog");
    if (evidenceDir) await mobilePage.screenshot({ path: path.join(evidenceDir, "17-assets-dialog-mobile-390x844.png"), fullPage: false, animations: "disabled" });
    await mobilePage.keyboard.press("Escape");
    await mobilePage.getByRole("button", { name: "Open asset details for Onboarding illustration" }).click();
    assert.match(await mobilePage.locator("#asset-dialog").textContent(), /Generating[\s\S]*42%/);
    if (evidenceDir) await mobilePage.screenshot({ path: path.join(evidenceDir, "25-assets-generating-mobile-390x844.png"), fullPage: false, animations: "disabled" });
    await mobilePage.keyboard.press("Escape");
    await mobilePage.getByRole("button", { name: "Open asset details for Roadmap" }).click();
    await mobilePage.locator("#asset-dialog").getByRole("button", { name: "Move to Trash" }).click();
    await mobilePage.locator("#asset-dialog").getByRole("button", { name: "Move to Trash" }).click();
    await mobilePage.locator("#asset-undo-toast").waitFor({ state: "visible" });
    assert.equal(await mobilePage.locator("#asset-dialog").evaluate((element) => element.open), false);
    if (evidenceDir) await mobilePage.screenshot({ path: path.join(evidenceDir, "26-assets-trash-undo-mobile-390x844.png"), fullPage: false, animations: "disabled" });
    await mobilePage.getByRole("button", { name: "Undo", exact: true }).click();
    await mobilePage.keyboard.press("Escape");
    await mobilePage.evaluate(() => setView("settings"));
    await mobilePage.locator("#settings-scope").selectOption("global|global");
    await mobilePage.waitForFunction(() => state.settingsScopeType === "global" && state.settingsScopeId === "global");
    await mobilePage.waitForFunction(() => { const elements = [...document.querySelectorAll(".settings-switch")].filter((element) => element.getClientRects().length); return elements.length > 0 && elements.every((element) => element.getBoundingClientRect().height >= 44); });
    assert.equal(await mobilePage.locator("#settings-grid").evaluate((element) => element.scrollWidth <= element.clientWidth + 1), true);
    assert.equal(await mobilePage.locator(".settings-switch").evaluateAll((elements) => elements.filter((element) => element.getClientRects().length).every((element) => element.getBoundingClientRect().height >= 44)), true);
    if (evidenceDir) await mobilePage.screenshot({ path: path.join(evidenceDir, "22-settings-essentials-mobile-390x844.png"), fullPage: false, animations: "disabled" });
    await mobilePage.getByLabel("Enable usage saver").scrollIntoViewIfNeeded();
    if (evidenceDir) await mobilePage.screenshot({ path: path.join(evidenceDir, "32-settings-usage-saver-default-mobile-390x844.png"), fullPage: false, animations: "disabled" });
    await mobilePage.locator("#project-scope-filter").click();
    if (evidenceDir) await mobilePage.screenshot({ path: path.join(evidenceDir, "30-project-dropdown-mobile-390x844.png"), fullPage: false, animations: "disabled" });
    await mobilePage.keyboard.press("Escape");
    assert.deepEqual(mobile.runtimeErrors, []);
    await mobilePage.close();
    console.log("SWARM console six-screen UI tests passed");
  } finally {
    await browser.close();
  }
