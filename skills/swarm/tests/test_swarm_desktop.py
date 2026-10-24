"""Prove the packaged entrypoint, not a parallel test launcher."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]


class PackagedDesktopTests(unittest.TestCase):
    def test_packaged_settings_and_sidebar(self):
        config = json.loads((ROOT / '.mcp.json').read_bytes())['mcpServers']['swarm']
        self.assertEqual(config['command'], sys.executable)
        self.assertEqual(config['type'], 'stdio')
        self.assertEqual(config['cwd'], '.')
        self.assertEqual(config['args'], ['-B', 'skills/swarm/scripts/swarm_desktop.py'])
        resolved_cwd = (ROOT / config['cwd']).resolve()
        self.assertEqual(resolved_cwd, ROOT.resolve())
        spec = importlib.util.spec_from_file_location('desktop_test', resolved_cwd / config['args'][1])
        desktop = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(desktop)
        snapshot = ROOT / 'skills/swarm/assets/ui/swarm-hq-snapshot.json'
        before = snapshot.read_bytes()
        hq = desktop.SidebarHQ(snapshot, hashlib.sha256(before).hexdigest(), projects=True)
        requests = [('initialize', {'protocolVersion': '2024-11-05', 'capabilities': {},
                                   'clientInfo': {'name': 'desktop-contract', 'version': '1'}}),
                    ('tools/list', {}), ('resources/read', {'uri': hq.uri}),
                    ('tools/call', {'name': 'swarm_hq_view', 'arguments': {}})]
        wire = ''.join(json.dumps({'jsonrpc': '2.0', 'id': i, 'method': method, 'params': params}) + '\n'
                       for i, (method, params) in enumerate(requests, 1))
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, PYTHONIOENCODING='utf-8', CODEX_HOME=directory, SWARM_CONFIG_PATH=str(Path(directory) / 'absent.toml'),
                       SWARM_MCP_TELEMETRY_PATH=str(Path(directory) / 'telemetry.jsonl'))
            # Exercise the exact package-local command, arguments and working directory.
            run = subprocess.run([config['command'], *config['args']], cwd=resolved_cwd, env=env,
                                 input=wire, text=True, encoding='utf-8', capture_output=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        responses = [json.loads(line) for line in run.stdout.splitlines()]
        self.assertEqual(len(responses), 4)
        for response in responses:
            self.assertNotIn('error', response)
        self.assertIn('serverInfo', responses[0]['result'])
        tools = responses[1]['result']['tools']
        self.assertTrue({'swarm_hq_view', 'swarm_settings_read', 'swarm_settings_save'} <= {t['name'] for t in tools})
        tool = next(t for t in tools if t['name'] == 'swarm_hq_view')
        self.assertEqual(tool['title'], 'SWARM')
        self.assertTrue(tool['icons'][0]['src'].startswith('data:image/svg+xml;base64,'))
        self.assertEqual(tool['_meta']['openai/ui']['entrypoints'], [{'type': 'global'}])
        resource = responses[2]['result']['contents'][0]
        self.assertEqual(resource['_meta']['openai/ui']['availableDisplayModes'], ['fullscreen'])
        html = resource['text']
        self.assertIn('id="settings"', html)
        self.assertIn('id="all-projects"', html)
        self.assertNotIn('__SCRIPT__', html)
        self.assertEqual(html.count('data-swarm-mcp-sdk='), 1)
        result = responses[3]['result']
        self.assertFalse(result['isError'])
        self.assertEqual(result['structuredContent']['served_html_sha256'], hashlib.sha256(html.encode()).hexdigest())
        self.assertFalse(result['structuredContent']['approval_verified'])
        self.assertEqual(snapshot.read_bytes(), before)

    def test_packaged_entrypoint_rejects_changed_mcp_before_loading_it(self):
        script = ROOT / 'skills/swarm/scripts/swarm_desktop.py'
        mcp = ROOT / 'skills/swarm/scripts/swarm_mcp.py'
        read_bytes = Path.read_bytes
        def changed(path):
            return b'changed MCP source' if path == mcp else read_bytes(path)
        spec = importlib.util.spec_from_file_location('desktop_changed_mcp', script)
        desktop = importlib.util.module_from_spec(spec)
        with patch.object(Path, 'read_bytes', changed):
            with self.assertRaisesRegex(RuntimeError, 'Packaged MCP identity mismatch'):
                spec.loader.exec_module(desktop)


if __name__ == '__main__':
    unittest.main()
