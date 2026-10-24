"""Isolated fixture only: real App/config authority, no user config or host DB."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from console.tests.test_console import SwarmConsoleTests

root = Path(sys.argv[1]).resolve()
root.mkdir(exist_ok=True)
fixture = SwarmConsoleTests()
with patch('console.tests.test_console.tempfile.TemporaryDirectory', return_value=SimpleNamespace(name=str(root), cleanup=lambda: None)):
    fixture.setUp()
spec = importlib.util.spec_from_file_location('settings_mcp', REPO / 'skills/swarm/scripts/swarm_mcp.py')
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)
html = '<!doctype html><html><head><title>Isolated SDK/backend integration fixture</title></head><body><main class="space-baseline">Fixture project snapshot</main></body></html>'
raw = json.dumps({'status': 'READY_SOURCE_BOUND_SPACE_HTML_NOT_PUBLISHED', 'html': html,
    'html_sha256': hashlib.sha256(html.encode()).hexdigest(), 'size_bytes': len(html.encode()),
    'snapshot_digest': 'sha256:' + '1' * 64, 'approval_verified': False, 'destination': None}).encode()
export = root / 'export.json'
export.write_bytes(raw)
app = mcp.HQApp(export, hashlib.sha256(raw).hexdigest(), projects=True)
(root / 'rendered.html').write_text(app.render(), encoding='utf-8')
print(json.dumps({'resource_uri': app.uri, 'served_html_sha256': hashlib.sha256(app.render().encode()).hexdigest()}))
