// Produce the pinned compact SDK input from the retained official SDK and tools.
const fs = require('node:fs');
const crypto = require('node:crypto');
const [sdkPath, terserPath, swcPath, output] = process.argv.slice(2);
if (!output) throw Error('Expected SDK, Terser bundle, SWC native module and output paths');
function verify(file, expected) {
  const bytes = fs.readFileSync(file);
  if (crypto.createHash('sha256').update(bytes).digest('hex') !== expected) throw Error('Input digest mismatch: ' + file);
  return bytes;
}
const sdk = verify(sdkPath, 'fb56376b7583ecafb4820bdebc150abee18feb6258ff84b83c2c944ebd9c3602');
verify(terserPath, 'e4ae9a64825ea7f53606c3ee01633f08b64e12000a30d3687f52b64977f9a652');
verify(swcPath, '283e25268bf10faf562e9cf62dd6765f51605ff83251e4bfd8dbb06ee7fa2c4c');
const terser = require(terserPath), swc = require(swcPath);
(async () => {
  const first = await terser.minify(sdk.toString('utf8'), {module: true, compress: {passes: 2}, mangle: true, format: {comments: 'all', ascii_only: false}});
  const result = swc.minifySync(Buffer.from(first.code), Buffer.from(JSON.stringify({compress: {passes: 5}, mangle: true, ecma: 2022, module: true, format: {comments: 'all', asciiOnly: false}}))).code;
  if (crypto.createHash('sha256').update(result).digest('hex') !== 'db527097cae6677ea4b50e598bf68a0dc65f880d82e12e653528f4d246c18fca') throw Error('Compact SDK output digest mismatch');
  fs.writeFileSync(output, result, 'utf8');
})().catch(error => { console.error(error); process.exitCode = 1; });
