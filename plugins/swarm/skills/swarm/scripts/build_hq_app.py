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
COMPACT_SDK_SHA = 'db527097cae6677ea4b50e598bf68a0dc65f880d82e12e653528f4d246c18fca'
ACORN_SHA = '2261c5f0e4abe860e889dfc67081683a4ba4d27deb7f4cbc8ad06a1b7fdd510c'


def build(sdk_root: Path, output: Path, *, compact_sdk: Path | None = None, acorn: Path | None = None) -> dict:
    sdk = sdk_root / 'package/dist/src/app-with-deps.js'
    if hashlib.sha256(sdk.read_bytes()).hexdigest() != SDK_SHA:
        raise ValueError('retained official SDK digest mismatch')
    package = json.loads((sdk_root / 'package/package.json').read_text(encoding='utf-8'))
    if package['name'] != '@modelcontextprotocol/ext-apps' or package['version'] != '2.0.3':
        raise ValueError('retained SDK package identity mismatch')
    if (compact_sdk is None) != (acorn is None):
        raise ValueError('compact SDK and parser must be supplied together')
    if compact_sdk is not None:
        if hashlib.sha256(compact_sdk.read_bytes()).hexdigest() != COMPACT_SDK_SHA:
            raise ValueError('compact SDK digest mismatch')
        if hashlib.sha256(acorn.read_bytes()).hexdigest() != ACORN_SHA:
            raise ValueError('HQ parser digest mismatch')
        sdk = compact_sdk.resolve()
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
    original_entry = entry
    with tempfile.TemporaryDirectory(prefix='swarm-hq-build-') as directory:
        compact_dir = None
        helper = ROOT / 'skills/swarm/scripts/compact_hq_literals.cjs'
        if compact_sdk is not None:
            compact_dir = Path(directory) / 'ui'
            compact_dir.mkdir()
            subprocess.check_output(['node', str(helper), str(acorn.resolve()), str(entry.parent), str(compact_dir)], cwd=ROOT)
            entry = compact_dir / entry.name
        editor_path = Path(directory) / 'config-editor.mjs'
        editor_path.write_text(editor, encoding='utf-8')
        metadata_path = Path(directory) / 'inputs.json'
        bundle_path = Path(directory) / 'bundle.js'
        subprocess.check_output([str(compiler), str(entry), '--bundle', '--format=esm',
            '--platform=browser', '--target=es2022', '--minify', '--charset=utf8', '--legal-comments=inline',
            '--loader:.css=text', f'--alias:@swarm/sdk={sdk}',
            f'--alias:@swarm/config-editor={editor_path}', f'--metafile={metadata_path}', f'--outfile={bundle_path}'], cwd=ROOT)
        payload = bundle_path.read_bytes()
        inputs = {'console/static/app.js': hashlib.sha256((ROOT / 'console/static/app.js').read_bytes()).hexdigest()}
        if compact_dir is not None:
            inputs[helper.relative_to(ROOT).as_posix()] = hashlib.sha256(helper.read_bytes()).hexdigest()
        for name in json.loads(metadata_path.read_text(encoding='utf-8'))['inputs']:
            path = (ROOT / name).resolve()
            if compact_dir is not None and path.is_relative_to(compact_dir.resolve()):
                path = ROOT / 'skills/swarm/assets/ui' / path.relative_to(compact_dir.resolve())
            if path.is_relative_to(ROOT.resolve()):
                inputs[path.relative_to(ROOT.resolve()).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        payload = b'// swarm-hq-inputs:' + json.dumps(inputs, sort_keys=True, separators=(',', ':')).encode() + b'\n' + payload
    # esbuild retains blank indentation in SDK-generated code templates.
    payload = re.sub(rb'(?m)^[ \t]+(?=\r?$)', b'', payload)
    if len(payload) > 512 * 1024 or b'</script' in payload.lower():
        raise ValueError('bundle exceeds embedding contract')
    output.write_bytes(payload)
    return {'sdk': '@modelcontextprotocol/ext-apps@2.0.3', 'sdk_sha256': SDK_SHA, 'compiler_sha256': ESBUILD_SHA,
            **({'compact_sdk_sha256': COMPACT_SDK_SHA, 'acorn_sha256': ACORN_SHA} if compact_sdk is not None else {}),
            'editor_sha256': hashlib.sha256(editor.encode()).hexdigest(),
            'entry_sha256': hashlib.sha256(original_entry.read_bytes()).hexdigest(),
            'bundle_sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload), 'inputs': inputs}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compact-sdk', type=Path, help='pinned pre-minified official SDK')
    parser.add_argument('--acorn', type=Path, help='pinned Acorn parser used for HQ literal pooling')
    args = parser.parse_args()
    print(json.dumps(build(args.sdk_root, args.output, compact_sdk=args.compact_sdk, acorn=args.acorn), sort_keys=True))
