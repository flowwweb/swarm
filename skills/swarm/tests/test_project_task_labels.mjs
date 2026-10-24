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
