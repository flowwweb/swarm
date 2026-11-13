const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
if (!process.argv[2]) throw Error('Pass the pinned Acorn parser path');
const acornPath = path.resolve(process.argv[2]);
const acorn = require(acornPath);
const helper = path.resolve(__dirname, '../scripts/compact_hq_literals.cjs');
const names = ['swarm-projects-bootstrap.mjs', 'swarm-settings.js', 'swarm-velocity.mjs', 'swarm-projects.mjs', 'swarm-usage.mjs'];
const fixture = `import { value as imported } from 'shared';
class Example { 'shared' = 'shared'; method() { return 'shared'; } }
const value = 'shared'; export { value as 'shared' };
globalThis.fixture = ['shared', 'shared', new Example()['shared'], imported];`;
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'swarm-literals-'));
try {
  const source = path.join(temporary, 'source'), output = path.join(temporary, 'output');
  fs.mkdirSync(source); fs.mkdirSync(output);
  for (const name of names) fs.writeFileSync(path.join(source, name), fixture);
  fs.writeFileSync(path.join(source, 'swarm-hq-bootstrap.mjs'), '');
  const run = spawnSync(process.execPath, [helper, acornPath, source, output], {encoding: 'utf8'});
  assert.equal(run.status, 0, run.stderr);
  const original = acorn.parse(fixture, {ecmaVersion: 'latest', sourceType: 'module'});
  const transformed = acorn.parse(fs.readFileSync(path.join(output, names[0]), 'utf8'), {ecmaVersion: 'latest', sourceType: 'module'});
  const pooled = new Map();
  while (transformed.body[0]?.type === 'VariableDeclaration' && transformed.body[0].declarations[0].id.name.startsWith('__swarmProfileConst')) {
    const declaration = transformed.body.shift().declarations[0];
    pooled.set(declaration.id.name, declaration.init.value);
  }
  assert.ok(pooled.size > 0, 'fixture must exercise literal pooling');
  function normalize(node) {
    if (Array.isArray(node)) return node.map(normalize);
    if (!node || typeof node !== 'object') return node;
    if (node.type === 'Identifier' && pooled.has(node.name)) return {type: 'Literal', value: pooled.get(node.name)};
    return Object.fromEntries(Object.entries(node).filter(([key]) => !['start', 'end', 'raw'].includes(key)).map(([key, value]) => [key, normalize(value)]));
  }
  assert.deepEqual(normalize(transformed), normalize(original));
  fs.writeFileSync(path.join(source, names[0]), "eval('shared'); 'shared'; 'shared';");
  const denied = spawnSync(process.execPath, [helper, acornPath, source, output], {encoding: 'utf8'});
  assert.notEqual(denied.status, 0, 'direct eval must fail closed');
  console.log('PASS: pooled literals preserve class fields, module names and expression syntax; direct eval rejected');
} finally {
  fs.rmSync(temporary, {recursive: true, force: true});
}
