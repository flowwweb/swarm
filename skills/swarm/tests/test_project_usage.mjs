// Project-scoped Usage contract: executable Node checks of the production reader and
// request helpers, plus static source checks. This is not browser or native host proof.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {usageView,readProjectUsage,latestRequest,projectUsageRequest} from '../assets/ui/swarm-usage.mjs';

const rows=[{bucket_ms:1100,delta_tokens:5},{bucket_ms:1200,delta_tokens:0},{bucket_ms:1900,delta_tokens:7}];
function fixture(scope,{hours=24,status='ok',items=rows}={}){
  const value={ok:true,hours,status,window:{after_ms:1000,before_ms:2000},items,
    total_tokens:items.reduce((sum,row)=>sum+row.delta_tokens,0),coverage:{observed_threads:1,expected_threads:2}};
  if(scope!==undefined)value.scope=scope;
  return value;
}
const project=id=>({type:'project',project_id:id});
const everyone={type:'all-projects'};

// Global reader: backward compatible, never accepts project-scoped data as global.
assert.equal(usageView(fixture(undefined),24).total,12);
assert.equal(usageView(fixture(everyone),24).total,12);
for(const scope of [project('alpha'),null,'all-projects',{type:'other'}])
  assert.throws(()=>usageView(fixture(scope),24),/Usage scope mismatch/);

// Selected project: exact scope, hours, window, total and coverage from one response.
assert.deepEqual(usageView(fixture(project('alpha'),{hours:168,status:'partial'}),168,'alpha'),
  {total:12,points:[{at:1100,tokens:5},{at:1200,tokens:0},{at:1900,tokens:7}],status:'partial',
   coverage:{observed_threads:1,expected_threads:2},window:{after_ms:1000,before_ms:2000}});
for(const scope of [project('beta'),everyone,undefined,null,'alpha',{type:'project'},project(' alpha ')])
  assert.throws(()=>usageView(fixture(scope),24,'alpha'),/Usage scope mismatch/);
assert.throws(()=>usageView(fixture(project('alpha')),168,'alpha'),/Invalid usage projection/);
for(const id of ['','  ',null,42,{}])
  assert.throws(()=>usageView(fixture(project('alpha')),24,id),/Invalid usage scope request/);
const empty=usageView(fixture(project('alpha'),{status:'no_data',items:[]}),24,'alpha');
assert.deepEqual([empty.total,empty.status,empty.points],[null,'no_data',[]]);
assert.throws(()=>usageView(fixture(project('alpha'),{status:'no_data'}),24,'alpha'),/Token total mismatch/);
assert.equal(usageView(fixture(project('alpha'),{items:[{bucket_ms:1500,delta_tokens:0}]}),24,'alpha').total,0);
const altered=fixture(project('alpha'));altered.total_tokens=13;
assert.throws(()=>usageView(altered,24,'alpha'),/Token total mismatch/);
console.log('PASS: global and exact project usage scope, window, total, partial and no_data');

// Bounded series: full-window tokens stay exact, never silently become the chart subset.
const bounded={...fixture(everyone),window:{after_ms:0,before_ms:40000000},
  items:Array.from({length:256},(_,i)=>({bucket_ms:(i+1)*120000,delta_tokens:1,bucket_start_ms:(i+1)*120000,connect_from_previous:false})),
  total_tokens:263,series_aggregation:{method:'contiguous_observed_sum',input_count:257,output_count:256,omitted_input_count:1,omitted_tokens:7}};
const boundedView=usageView(bounded,24);
assert.equal(boundedView.total,263);assert.equal(boundedView.points.reduce((n,p)=>n+p.tokens,0),256);
assert.deepEqual(boundedView.omitted,{observations:1,tokens:7});
assert.equal(usageView({...bounded,scope:project('alpha')},24,'alpha').total,263);
assert.throws(()=>usageView({...bounded,scope:project('beta')},24,'alpha'),/scope mismatch/);
for(const [key,bad] of [['method','sum'],['input_count',256],['input_count',256.5],['output_count',255],['omitted_input_count',-1],['omitted_input_count',2],['omitted_input_count','1'],['omitted_tokens',-7],['omitted_tokens','7'],['omitted_tokens',8],['omitted_tokens',Number.MAX_SAFE_INTEGER]]){
  assert.throws(()=>usageView({...bounded,series_aggregation:{...bounded.series_aggregation,[key]:bad}},24),/aggregation|total mismatch/);
}
for(const bad of [null,{},undefined])assert.throws(()=>usageView({...bounded,series_aggregation:bad},24),/aggregation|total mismatch/);
assert.throws(()=>usageView({...bounded,series_aggregation:{...bounded.series_aggregation,omitted_input_count:0}},24),/aggregation/);
const zeroOmitted=usageView({...bounded,total_tokens:256,series_aggregation:{...bounded.series_aggregation,omitted_tokens:0}},24);
assert.deepEqual(zeroOmitted.omitted,{observations:1,tokens:0},'omitted observed zero is still disclosed');
const grouped=usageView({...bounded,total_tokens:256,series_aggregation:{...bounded.series_aggregation,omitted_input_count:0,omitted_tokens:0}},24);
assert.equal(grouped.total,256);assert.equal(grouped.omitted,undefined);
const interval=fixture(everyone,{items:[{bucket_ms:1500,bucket_start_ms:1100,delta_tokens:7}]});
assert.deepEqual(usageView(interval,24).points,[{at:1500,start:1100,tokens:7}]);
for(const start of [999,1501,'1100',null,NaN])assert.throws(()=>usageView({...interval,items:[{...interval.items[0],bucket_start_ms:start}]},24),/interval/);
assert.throws(()=>usageView(fixture(everyone,{items:[{bucket_ms:1200,delta_tokens:1},{bucket_ms:1500,bucket_start_ms:1200,delta_tokens:2}]}),24),/Conflicting/);
console.log('PASS: exact omission conservation, typed metadata, zero omission and project scope');

// Exercise the production compactor, not a reimplementation of its grouping algorithm.
const inputs=[];
for(const count of [1,256,257,513,4097])for(const run of [1,31,count]){
  const items=Array.from({length:count},(_,i)=>({bucket_ms:60000*(i+Math.floor(i/run)+1),delta_tokens:i%7}));
  inputs.push({...fixture(everyone,{items,status:'partial'}),window:{after_ms:0,before_ms:60000*(count*2+1)}});
}
const compact=JSON.parse(execFileSync('python',['-B','-c',
  "import importlib.util,json,sys; s=importlib.util.spec_from_file_location('usage_mcp','skills/swarm/scripts/swarm_mcp.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(json.dumps([m._compact_usage(v) for v in json.load(sys.stdin)]))"],
  {cwd:fileURLToPath(new URL('../../../',import.meta.url)),input:JSON.stringify(inputs),encoding:'utf8',maxBuffer:8*1024*1024}));
for(let i=0;i<compact.length;i++){
  const view=usageView(compact[i],24);
  assert.equal(view.total,inputs[i].total_tokens);assert.ok(view.points.length<=256);
  assert.equal(view.points.reduce((sum,p)=>sum+p.tokens,0)+(view.omitted?.tokens||0),inputs[i].total_tokens);
  assert.deepEqual(view.window,inputs[i].window);
  assert.equal(compact[i].items[0].connect_from_previous,false);
  for(let j=1;j<compact[i].items.length;j++)assert.equal(compact[i].items[j].connect_from_previous,
    compact[i].items[j].bucket_start_ms-compact[i].items[j-1].bucket_ms===60000);
}
assert.ok(compact.some(v=>v.series_aggregation?.omitted_input_count>0));
console.log('PASS: 15 production compactor/reader contrasts, bounded disconnected runs and full-window conservation');

// Request helpers used by the production project page.
assert.deepEqual(projectUsageRequest('alpha',24),{project_id:'alpha',hours:24});
for(const [id,hours] of [['',24],['  ',24],[null,24],[42,24],['alpha',12],['alpha','24']])
  assert.throws(()=>projectUsageRequest(id,hours),/Invalid project usage request/);
const gate=latestRequest();const first=gate.next(),second=gate.next();
assert.equal(gate.isLatest(first),false);assert.equal(gate.isLatest(second),true);

function deferred(){let resolve,reject;const promise=new Promise((ok,fail)=>{resolve=ok;reject=fail;});return {promise,resolve,reject};}
function harness(){
  const calls=[],requests=latestRequest(),state={selected:null,detail:0};
  const call=(name,args)=>{const d=deferred();calls.push({name,args,d});return d.promise;};
  // Mirrors the production predicate: newest request, same detail generation, same selected project.
  const start=(id,hours)=>{const token=requests.next(),detail=state.detail;
    return readProjectUsage(call,id,hours,()=>requests.isLatest(token)&&detail===state.detail&&state.selected===id);};
  const open=id=>{state.selected=id;state.detail++;};
  const close=()=>{state.selected=null;state.detail++;};
  return {calls,start,open,close};
}

{ // Exact forwarding of the selected project and period.
  const h=harness();h.open('alpha');const read=h.start('alpha',24);
  assert.deepEqual(h.calls.map(c=>[c.name,c.args]),[['swarm_usage',{project_id:'alpha',hours:24}]]);
  h.calls[0].d.resolve(fixture(project('alpha')));const result=await read;
  assert.equal(result.state,'ready');assert.equal(result.view.total,12);
}
{ // A->B: a late A response never presents.
  const h=harness();h.open('alpha');const a=h.start('alpha',24);h.open('beta');const b=h.start('beta',24);
  h.calls[1].d.resolve(fixture(project('beta')));assert.equal((await b).state,'ready');
  h.calls[0].d.resolve(fixture(project('alpha')));assert.deepEqual(await a,{state:'stale'});
}
{ // A->B->A: only the newest A read presents.
  const h=harness();h.open('alpha');const a1=h.start('alpha',24);h.open('beta');const b=h.start('beta',24);h.open('alpha');const a2=h.start('alpha',24);
  h.calls[2].d.resolve(fixture(project('alpha'),{items:[{bucket_ms:1500,delta_tokens:3}]}));
  const fresh=await a2;assert.equal(fresh.state,'ready');assert.equal(fresh.view.total,3);
  h.calls[0].d.resolve(fixture(project('alpha')));h.calls[1].d.resolve(fixture(project('beta')));
  assert.deepEqual(await a1,{state:'stale'});assert.deepEqual(await b,{state:'stale'});
}
{ // A newer period is never overwritten by an older one.
  const h=harness();h.open('alpha');const day=h.start('alpha',24),week=h.start('alpha',168);
  assert.deepEqual(h.calls[1].args,{project_id:'alpha',hours:168});
  h.calls[1].d.resolve(fixture(project('alpha'),{hours:168}));assert.equal((await week).state,'ready');
  h.calls[0].d.resolve(fixture(project('alpha')));assert.deepEqual(await day,{state:'stale'});
}
{ // Close or Settings: neither a late success nor a late failure presents.
  const h=harness();h.open('alpha');const ok=h.start('alpha',24);h.close();
  h.calls[0].d.resolve(fixture(project('alpha')));assert.deepEqual(await ok,{state:'stale'});
  h.open('alpha');const failed=h.start('alpha',24);h.close();
  h.calls[1].d.reject(Error('Unavailable'));assert.deepEqual(await failed,{state:'stale'});
}
{ // A current failure or scope leak is unavailable and never throws into project detail.
  const h=harness();h.open('alpha');
  const rejected=h.start('alpha',24);h.calls[0].d.reject(Error('Unavailable'));assert.deepEqual(await rejected,{state:'unavailable'});
  const leaked=h.start('alpha',24);h.calls[1].d.resolve(fixture(project('beta')));assert.deepEqual(await leaked,{state:'unavailable'});
  const wide=h.start('alpha',24);h.calls[2].d.resolve(fixture(everyone));assert.deepEqual(await wide,{state:'unavailable'});
  let invoked=0;
  assert.deepEqual(await readProjectUsage(()=>{invoked++;},'',24,()=>true),{state:'unavailable'});
  assert.deepEqual(await readProjectUsage(()=>{invoked++;},'alpha',12,()=>true),{state:'unavailable'});
  assert.equal(invoked,0);
}
console.log('PASS: exact project request, A->B, A->B->A, newer period, close/Settings and failure isolation');

// Static source checks only: wiring and encoding, not rendered behavior.
const decoder=new TextDecoder('utf-8',{fatal:true});
const source=name=>decoder.decode(readFileSync(new URL('../assets/ui/'+name,import.meta.url)));
const bootstrap=source('swarm-projects-bootstrap.mjs'),usageSource=source('swarm-usage.mjs');
for(const [name,text] of [['bootstrap',bootstrap],['usage',usageSource]]){
  assert.doesNotMatch(text,/\u00c3|\u00e2[\u20ac\u2020]|\u00c2\u00b7/,name+' contains mojibake');
  assert.doesNotMatch(text,/[^\x00-\x7f]/,name+' must keep display glyphs escaped');
}
assert.ok(bootstrap.includes('readProjectUsage(call,id,value,current)'),'project page uses the tested reader');
assert.ok(bootstrap.includes('detail===detailGeneration&&selectedProject===id'),'project usage keeps the detail guard');
assert.ok(bootstrap.includes("call('swarm_usage',{hours:value})"),'global usage call unchanged');
assert.ok(!bootstrap.includes('Project-scoped usage is not available from this connection.'));
assert.ok(!bootstrap.includes('data-hours="'),'project periods must not join the global period buttons');
assert.doesNotMatch(bootstrap,/setInterval|setTimeout/,'no timer or polling');
console.log('PASS: source wiring, escaped Unicode, no mojibake, no timers (source checks, not browser proof)');
