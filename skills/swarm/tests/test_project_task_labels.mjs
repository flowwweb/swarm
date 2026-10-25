// Current compact task contract: stable IDs are not ticket display identities.
import assert from 'node:assert/strict';
import {projectDetail} from '../assets/ui/swarm-projects.mjs';
const task={id:'retained-task',project_id:'alpha',state:'PENDING'};
const view=tasks=>({projects:[{id:'alpha'}],nodes:[{id:'host-agent',project_id:'alpha',title:'Designer',node_kind:'AGENT'}],progress:{projects:{alpha:{scope:{project_id:'alpha'},tasks}}},overview_metrics:{accepted_scope_id:'alpha',accepted_cursor:{scope_id:'alpha',digest:'scope-cursor'}}});
const read=tasks=>projectDetail(view(tasks),'alpha');
assert.deepEqual(read([task]).taskRows,[{id:'retained-task',name:'Task retained-task',status:'PENDING'}]);
// Only explicit projected fields may label a retained scoped task; host titles cannot.
assert.deepEqual(read([{...task,title:'Host title'}]).taskRows,read([task]).taskRows);
assert.equal(read([{...task,display_id:'ALPH-8',label:'Review export'}]).taskRows[0].name,'ALPH-8 \u00b7 Review export');
assert.equal(read([{...task,display_id:'ALPH-8'}]).taskRows[0].name,'ALPH-8');
assert.equal(read([{...task,label:'Review export'}]).taskRows[0].name,'Review export');
for(const display_id of [null,42,'','x'.repeat(65),'bad\nlabel','ALPHA-8','A-0','A--2','A-01','a-1'])assert.equal(read([{...task,display_id}]).taskRows[0].name,'Task retained-task');
for(const label of [null,{},'','x'.repeat(161),'bad\tlabel'])assert.equal(read([{...task,label}]).taskRows[0].name,'Task retained-task');
assert.deepEqual(read([{...task,project_id:'beta',display_id:'BETA-1',label:'Foreign'}]).taskRows,[]);
const other={id:'another-task',project_id:'alpha',state:'BLOCKED'};
assert.deepEqual(read([task,other]).taskRows,read([other,task]).taskRows.reverse());
assert.equal(read(undefined).tasksAvailable,false);
assert.deepEqual(read([{...task,project_id:'beta'}]).taskRows,[]);
assert.equal(read([]).tasksAvailable,true);
console.log('PASS: stable-ID fallback, no agent/title/ticket inference, order independence, missing and foreign scope');

// J1: strict UTF-8 and exact display glyphs, independent of shell code page.
const {readFileSync}=await import('node:fs');
const {runInNewContext}=await import('node:vm');
const decoder=new TextDecoder('utf-8',{fatal:true});
for(const name of ['swarm-projects-bootstrap.mjs','swarm-projects.mjs','swarm-hq-projects.html','swarm-hq-host.css','swarm-hq-mcp-app.js']){
 const source=decoder.decode(readFileSync(new URL('../assets/ui/'+name,import.meta.url)));
 const decodedEscapes=source.replace(/\\(?:u([a-f\d]{4})|x([a-f\d]{2}))/gi,(_,u,x)=>String.fromCodePoint(parseInt(u||x,16)));
 assert.doesNotMatch(decodedEscapes,/\u00c3|\u00e2[\u20ac\u2020]|\u00c2\u00b7/,name+' contains escaped mojibake');
 assert.doesNotMatch(source,/\u00c3|\u00e2[\u20ac\u2020]|\u00c2\u00b7/,name+' contains mojibake');
}
const bootstrap=decoder.decode(readFileSync(new URL('../assets/ui/swarm-projects-bootstrap.mjs',import.meta.url)));
const numberSource=bootstrap.match(/const number=([^;]+);/)[1];
assert.equal(runInNewContext('('+numberSource+')(null)'),'\u2014');
assert.equal(runInNewContext('('+numberSource+')(42)'),'42');
for(const hex of ['2014','2192','2026','2019','00b7','00d7']){
 assert.ok(bootstrap.includes('\\u'+hex),'missing escaped display glyph '+hex);
 assert.equal(runInNewContext("'\\u"+hex+"'"),String.fromCodePoint(parseInt(hex,16)));
}
console.log('PASS: strict UTF-8, no mojibake, exact escaped display glyphs');

for(const cp of [0x80,0x85,0x9f,0x61c,0x200e,0x200f,0x202a,0x202e,0x2066,0x2069]){
 const result=read([{...task,label:'Unsafe'+String.fromCodePoint(cp)+'label'}]);
 assert.equal(result.taskRows[0].name,'Task retained-task');
 assert.equal(result.taskRows[0].id,task.id);
}
assert.equal(read([{...task,label:'Review caf\u00e9'}]).taskRows[0].name,'Review caf\u00e9');
const partial=view([task]);partial.progress.projects.alpha.truncated=true;
assert.equal(projectDetail(partial,'alpha').tasksTruncated,true);
assert.equal(read([task]).tasksTruncated,false);
partial.progress.projects.alpha.tasks=[{...task,project_id:'foreign'}];
assert.equal(projectDetail(partial,'alpha').tasksTruncated,false);
assert.ok(bootstrap.includes("data.tasksTruncated?'<p>More tasks unavailable.</p>':''"));
console.log('PASS: partial-list flag, unsafe display controls rejected, stable identity retained');

// Durable acceptance is a separate, cursor-bound server projection, never host activity.
const ledgerCursor={event_seq:13,event_id:'bound-accepted:retained-task:b',event_digest:'a'.repeat(64)};
const lifecycle={state:'COMPLETED',accepted_blocks:2,total_blocks:2,manifest_digest:'sha256:'+'b'.repeat(64),
 source:'ledger:bound-task-acceptance',ledger_cursor:ledgerCursor};
const completed=view([{...task,state:'active',durable_lifecycle:lifecycle}]);
completed.progress.task_identity={state:'KNOWN',digest:'c'.repeat(64),ledger_cursor:ledgerCursor};
const taskStatus=raw=>projectDetail(raw,'alpha').taskRows[0].status;
assert.equal(taskStatus(completed),'COMPLETED');
completed.progress.projects.alpha.tasks[0].state='quiet';
assert.equal(taskStatus(completed),'COMPLETED');
const revised=structuredClone(completed);
Object.assign(revised.progress.projects.alpha.tasks[0].durable_lifecycle,{state:'OPEN',accepted_blocks:0,manifest_digest:'sha256:'+'d'.repeat(64)});
assert.equal(taskStatus(revised),'OPEN');
for(const mutate of [
 raw=>raw.progress.task_identity.state='UNAVAILABLE',
 raw=>raw.progress.task_identity.ledger_cursor.event_seq++,
 raw=>raw.progress.projects.alpha.tasks[0].durable_lifecycle.source='host:activity',
 raw=>raw.progress.projects.alpha.tasks[0].durable_lifecycle.manifest_digest='bad',
 raw=>raw.progress.projects.alpha.tasks[0].durable_lifecycle.state='ACCEPT',
 raw=>raw.progress.projects.alpha.tasks[0].durable_lifecycle=null,
]){const bad=structuredClone(completed);bad.progress.task_identity.ledger_cursor={...ledgerCursor};mutate(bad);assert.equal(taskStatus(bad),'Unknown');}
assert.equal(read([{...task,state:'active'}]).taskRows[0].status,'active');
assert.equal(read([{...task,state:'quiet'}]).taskRows[0].status,'quiet');
assert.deepEqual(completed,JSON.parse(JSON.stringify(completed)));
assert.equal(taskStatus(JSON.parse(JSON.stringify(completed))),'COMPLETED');
console.log('PASS: durable completion separate from host activity; revised OPEN, cursor mismatch and malformed lifecycle fail closed; reload parity');
