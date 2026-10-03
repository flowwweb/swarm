import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import test from 'node:test';

const bundle = process.argv[2] ?? fileURLToPath(new URL('../vendor/jev/swarm-jev.cjs', import.meta.url));
const source = readFileSync(bundle, 'utf8');
const sandbox = { require: createRequire(import.meta.url),
  process: { argv: ['node', 'jev', 'help'], env: {}, stderr: { write() {} }, stdout: { write() {} } },
  console: { error() {}, log() {} }, fetch() { throw new Error('No provider calls'); } };
vm.createContext(sandbox);
vm.runInContext(source + '\ninit_doc(); init_evaluate(); globalThis.contract = { Doc, esc, z: external_exports, evaluateInputSchema };', sandbox);
const { Doc, esc, z, evaluateInputSchema } = sandbox.contract;
const hostileKeys = ['</script><script>alert(1)</script>', '<!-- -->',
  '\u2028line\u2029paragraph', '";globalThis.swarmInjected=true;//',
  "');globalThis.swarmInjected=true;/*", '\\"quoted\\', '\r\n\t\b\f\0',
  '${globalThis.swarmInjected=true}', '/* comment */', '__proto__.polluted'];

test('generated JavaScript literals escape dangerous characters without changing values', () => {
  for (const key of [...hostileKeys, 'normal', 'emoji🐙', '\ud800']) {
    const literal = esc(key);
    assert.equal(/[<>\u2028\u2029]/u.test(literal), false, `unsafe code literal for ${JSON.stringify(key)}`);
    const doc = new Doc([]);
    doc.write(`return ${literal};`);
    assert.equal(doc.compile()(), key);
  }
  assert.equal(sandbox.swarmInjected, undefined);
});

test('actual bundled Zod parser preserves hostile keys and validation paths', () => {
  for (const key of hostileKeys) {
    const schema = z.object({ [key]: z.string() });
    assert.equal(schema.parse({ [key]: 'accepted' })[key], 'accepted');
    const rejected = schema.safeParse({ [key]: 42 });
    assert.equal(rejected.success, false);
    assert.equal(rejected.error.issues[0].path[0], key);
  }
  assert.equal(sandbox.swarmInjected, undefined);
});

test('Jev schemas retain valid primitive questions and reject invalid types', () => {
  const request = { model: 'jev-1.13.0', state: { context: 'synthetic' }, questions: {
    verdict: { type: 'noul', instructions: 'Is this complete?' },
    route: { type: 'choice', instructions: 'Choose a route', criteria: { one: 'First', two: 'Second' } },
    score: { type: 'score', instructions: 'Rate this', criteria: ['Low', 'High'] },
  } };
  assert.equal(evaluateInputSchema.safeParse(request).success, true);
  assert.equal(evaluateInputSchema.safeParse({ ...request, questions: {
    verdict: { type: 'shell', instructions: 'Invalid type' },
  } }).success, false);
});

test('vendored provenance binds bytes and mock CLI still evaluates valid requests', () => {
  if (!process.argv[2]) {
    const provenance = JSON.parse(readFileSync(new URL('../vendor/jev/provenance.json', import.meta.url)));
    assert.equal(createHash('sha256').update(readFileSync(bundle)).digest('hex'), provenance.bundle_sha256);
  }
  const request = { model: 'jev-1.13.0', state: 'synthetic task complete', questions: {
    verdict: { type: 'noul', instructions: 'Is this complete?' },
  } };
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) =>
    ['SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP'].includes(key.toUpperCase())));
  Object.assign(env, { JEV_MCP_MOCK: '1', JEV_MCP_MODEL: 'jev-1.13.0' });
  const run = spawnSync(process.execPath, [bundle, 'eval', '--stdin'],
    { input: JSON.stringify(request), encoding: 'utf8', env, timeout: 10000 });
  assert.equal(run.status, 0, run.stderr || run.error?.message);
  const answer = JSON.parse(run.stdout);
  assert.equal(answer.model, 'jev-1.13.0+mock');
  assert.equal(answer.answers.verdict.type, 'noul');
  assert.equal(typeof answer.answers.verdict.noul, 'number');
});
