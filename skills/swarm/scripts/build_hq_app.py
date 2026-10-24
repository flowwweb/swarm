"""Rebuild the pinned official MCP App from retained SDK inputs; no download/install.

The console's existing canonical-text editor is extracted at build time, not
forked into a second maintained TOML writer. Output goes to an explicit path;
the caller must review and update the MCP pin separately.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
SDK_SHA = 'fb56376b7583ecafb4820bdebc150abee18feb6258ff84b83c2c944ebd9c3602'
ESBUILD_SHA = 'c7bee37877d0aa6a046e52783fa0a2cf1a9ce5579d68bb3083bda99d4bff18ef'


def build(sdk_root: Path, output: Path) -> dict:
    sdk = sdk_root / 'package/dist/src/app-with-deps.js'
    if hashlib.sha256(sdk.read_bytes()).hexdigest() != SDK_SHA:
        raise ValueError('retained official SDK digest mismatch')
    package = json.loads((sdk_root / 'package/package.json').read_text(encoding='utf-8'))
    if package['name'] != '@modelcontextprotocol/ext-apps' or package['version'] != '2.0.3':
        raise ValueError('retained SDK package identity mismatch')
    compiler = sdk_root / 'package/esbuild.exe'
    if hashlib.sha256(compiler.read_bytes()).hexdigest() != ESBUILD_SHA:
        raise ValueError('retained compiler digest mismatch')
    if subprocess.check_output([str(compiler), '--version'], text=True).strip() != '0.28.2':
        raise ValueError('unsupported retained compiler')
    source = (ROOT / 'console/static/app.js').read_text(encoding='utf-8')
    start, end = 'function configTomlLiteral(', 'function configWriteRequest('
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError('canonical config editor boundary changed')
    editor = source[source.index(start):source.index(end)] + '\nexport {configTextWithChanges};\n'
    entry = ROOT / 'skills/swarm/assets/ui/swarm-hq-bootstrap.mjs'
    with tempfile.TemporaryDirectory(prefix='swarm-hq-build-') as directory:
        editor_path = Path(directory) / 'config-editor.mjs'
        editor_path.write_text(editor, encoding='utf-8')
        payload = subprocess.check_output([str(compiler), str(entry), '--bundle', '--format=esm',
            '--platform=browser', '--target=es2022', '--minify', '--legal-comments=inline',
            '--loader:.css=text', f'--alias:@swarm/sdk={sdk}',
            f'--alias:@swarm/config-editor={editor_path}'], cwd=ROOT)
    # esbuild retains blank indentation in SDK-generated code templates.
    payload = re.sub(rb'(?m)^[ \t]+(?=\r?$)', b'', payload)
    if len(payload) > 524288 or b'</script' in payload.lower():
        raise ValueError('bundle exceeds embedding contract')
    output.write_bytes(payload)
    return {'sdk': '@modelcontextprotocol/ext-apps@2.0.3', 'sdk_sha256': SDK_SHA, 'compiler_sha256': ESBUILD_SHA,
            'editor_sha256': hashlib.sha256(editor.encode()).hexdigest(),
            'entry_sha256': hashlib.sha256(entry.read_bytes()).hexdigest(),
            'bundle_sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.sdk_root, args.output), sort_keys=True))
