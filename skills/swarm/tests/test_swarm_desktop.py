"""Prove the packaged entrypoint, not a parallel test launcher."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class PackagedDesktopTests(unittest.TestCase):
    def test_packaged_settings_and_sidebar(self):
        config = json.loads((ROOT / '.mcp.json').read_bytes())['mcpServers']['swarm']
        self.assertEqual(config['cwd'], '.')
        self.assertEqual(config['args'], ['-B', 'skills/swarm/scripts/swarm_desktop.py'])
        spec = importlib.util.spec_from_file_location('desktop_test', ROOT / config['args'][1])
        desktop = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(desktop)
        snapshot = ROOT / 'skills/swarm/assets/ui/swarm-hq-snapshot.json'
        before = snapshot.read_bytes()
        hq = desktop.SidebarHQ(snapshot, hashlib.sha256(before).hexdigest(), projects=True)
        requests = [('tools/list', {}), ('resources/read', {'uri': hq.uri}),
                    ('tools/call', {'name': 'swarm_hq_view', 'arguments': {}})]
        wire = ''.join(json.dumps({'jsonrpc': '2.0', 'id': i, 'method': method, 'params': params}) + '\n'
                       for i, (method, params) in enumerate(requests, 1))
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, PYTHONIOENCODING='utf-8', CODEX_HOME=directory, SWARM_CONFIG_PATH=str(Path(directory) / 'absent.toml'),
                       SWARM_MCP_TELEMETRY_PATH=str(Path(directory) / 'telemetry.jsonl'))
            run = subprocess.run([config['command'], *config['args']], cwd=ROOT, env=env,
                                 input=wire, text=True, encoding='utf-8', capture_output=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        responses = [json.loads(line) for line in run.stdout.splitlines()]
        self.assertEqual(len(responses), 3)
        for response in responses:
            self.assertNotIn('error', response)
        tools = responses[0]['result']['tools']
        self.assertTrue({'swarm_hq_view', 'swarm_settings_read', 'swarm_settings_save'} <= {t['name'] for t in tools})
        tool = next(t for t in tools if t['name'] == 'swarm_hq_view')
        self.assertEqual(tool['title'], 'SWARM')
        self.assertTrue(tool['icons'][0]['src'].startswith('data:image/svg+xml;base64,'))
        self.assertEqual(tool['_meta']['openai/ui']['entrypoints'], [{'type': 'global'}])
        resource = responses[1]['result']['contents'][0]
        self.assertEqual(resource['_meta']['openai/ui']['availableDisplayModes'], ['fullscreen'])
        html = resource['text']
        self.assertIn('id="settings"', html)
        self.assertIn('id="all-projects"', html)
        self.assertNotIn('__SCRIPT__', html)
        self.assertEqual(html.count('data-swarm-mcp-sdk='), 1)
        result = responses[2]['result']
        self.assertFalse(result['isError'])
        self.assertEqual(result['structuredContent']['served_html_sha256'], hashlib.sha256(html.encode()).hexdigest())
        self.assertFalse(result['structuredContent']['approval_verified'])
        self.assertEqual(snapshot.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
