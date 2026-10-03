// Rebuild the pinned Jev CLI without mutating the supplied upstream checkout.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const sourceRoot = resolve(process.argv[2] ?? '');
assert(process.argv.length === 3, 'Usage: node scripts/build_jev_bundle.mjs <pinned-jev-source-root>');
const require = createRequire(resolve(sourceRoot, 'package.json'));
const esbuild = require('esbuild');
assert.equal(esbuild.version, '0.28.2', 'Use the original pinned bundler');
const vendor = fileURLToPath(new URL('../skills/swarm/vendor/jev/', import.meta.url));
const provenance = JSON.parse(await readFile(resolve(vendor, 'provenance.json'), 'utf8'));
const baselineHash = '4d72f94bc08313e23a8d05e597defe9f6512007132f977fb54e85a7db4b5659f';
const hash = value => createHash('sha256').update(value).digest('hex');
const unsafeLiteral = '    return JSON.stringify(str);';
const safeLiteral = String.raw`    return JSON.stringify(str).replace(/[<>\u2028\u2029]/g,
        char => "\\u" + char.charCodeAt(0).toString(16).padStart(4, "0"));`;

function sourcePatches(harden) {
  return { name: 'swarm-jev-source-patches', setup(build) {
    build.onLoad({ filter: /[\\/]src[\\/]typesafe\.ts$/ }, async ({ path }) => {
      let contents = (await readFile(path, 'utf8')).replace(/\r\n/g, '\n');
      for (const model of ['model', 'config.model']) {
        const anchor = `    defaultModel: ${model},\n`;
        const patched = anchor + '    retry: { maxRetries: 0 },\n';
        if (!contents.includes(patched)) {
          assert.equal(contents.split(anchor).length, 2, 'Retry patch source changed');
          contents = contents.replace(anchor, patched);
        }
      }
      return { contents, loader: 'ts', resolveDir: dirname(path) };
    });
    if (harden) build.onLoad({ filter: /[\\/]zod[\\/]v4[\\/]core[\\/]util\.js$/ }, async ({ path }) => {
      const contents = await readFile(path, 'utf8');
      assert.equal(contents.split(unsafeLiteral).length, 2, 'Zod literal patch source changed');
      return { contents: contents.replace(unsafeLiteral, safeLiteral), loader: 'js', resolveDir: dirname(path) };
    });
  } };
}

async function bundle(harden) {
  return esbuild.build({ absWorkingDir: sourceRoot, entryPoints: ['src/index.ts'],
    bundle: true, platform: 'node', format: 'cjs', target: 'node20',
    write: false, metafile: true, plugins: [sourcePatches(harden)] });
}

const baseline = await bundle(false);
assert.equal(hash(baseline.outputFiles[0].contents), baselineHash,
  'Upstream source/dependencies differ from the reviewed original bundle');
const result = await bundle(true);
const bytes = result.outputFiles[0].contents;
const repeated = await bundle(true);
assert.equal(hash(bytes), hash(repeated.outputFiles[0].contents), 'Bundle is not reproducible');
const imports = Object.values(result.metafile.outputs)[0].imports;
assert.deepEqual(imports, provenance.external_imports, 'External import boundary changed');
provenance.patch = 'TypeSafeClient retry maxRetries set to 0 at both call sites; Zod code literals escape angle brackets and Unicode line separators';
provenance.bundle_sha256 = hash(bytes);
provenance.build = { script: 'scripts/build_jev_bundle.mjs', esbuild: esbuild.version,
  entrypoint: 'src/index.ts', platform: 'node', format: 'cjs', target: 'node20',
  baseline_bundle_sha256: baselineHash, zod: '4.6.5', reproducible: true };
await writeFile(resolve(vendor, 'swarm-jev.cjs'), bytes);
await writeFile(resolve(vendor, 'provenance.json'), JSON.stringify(provenance, null, 2) + '\n');
console.log(JSON.stringify({ status: 'PASS', baseline_sha256: baselineHash,
  bundle_sha256: hash(bytes), bytes: bytes.length, reproducible: true, imports }));
