"""Package-local Projects and acknowledged Settings through existing MCP tools."""
import base64
import hashlib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'skills/swarm/scripts/swarm_mcp.py'
if hashlib.sha256(SCRIPT.read_bytes()).hexdigest() != 'aadc18169cb2049b82ec51be4b4b0b273789a713e6f3be52526696ddeda3ab5c':
    raise RuntimeError('Packaged MCP identity mismatch')
spec = importlib.util.spec_from_file_location('accepted_swarm_mcp', SCRIPT)
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)
ASSETS = {'console/static/swarm-sidebar-round-outline.svg': '5ad36087322e2706b68bc296fe67d00743b5e340aace7b5b926b5a657c79abcb'}


def asset(name):
    path = ROOT / name
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ASSETS[name]:
        raise mcp.MCPError('Projects resource identity mismatch')
    return raw


class SidebarHQ(mcp.HQApp):
    def resource(self):
        resource = super().resource()
        resource['contents'][0]['_meta']['openai/ui'] = {'availableDisplayModes': ['fullscreen']}
        return resource

    def tool(self):
        tool = super().tool()
        icon = asset('console/static/swarm-sidebar-round-outline.svg')
        tool['title'] = 'SWARM'
        tool['icons'] = [{'src': 'data:image/svg+xml;base64,' + base64.b64encode(icon).decode('ascii'), 'mimeType': 'image/svg+xml', 'sizes': ['24x24']}]
        return tool


if __name__ == '__main__':
    raise SystemExit(mcp.serve(hq_app=SidebarHQ(
        ROOT / 'skills/swarm/assets/ui/swarm-hq-snapshot.json',
        '3b229a52f8689cdcc943b1f7ab320c0f6dc64fb8fc24e8ccc7143af573b1cb07', projects=True)))
