import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

BASE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BASE))
spec = importlib.util.spec_from_file_location('proof_console_fixture', BASE / 'console/server.py')
console = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = console
spec.loader.exec_module(console)

class ProofRegistrationErrorTests(unittest.TestCase):
    def test_unbound_bound_and_unknown_error(self):
        with tempfile.TemporaryDirectory(prefix='swarm-proof-test-') as tmp:
            root = Path(tmp)
            home = root / 'home'
            home.mkdir()
            source = root / 'fixture.png'
            source.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
            package = root / 'candidate'
            (package / 'scripts').mkdir(parents=True)
            (package / 'runtime').mkdir()
            shutil.copyfile(BASE / 'skills/swarm/runtime/proof_events.py', package / 'runtime/proof_events.py')
            selected = BASE / 'skills/swarm/scripts/swarm_proof.py'
            shutil.copyfile(selected, package / 'scripts/swarm_proof.py')
            class Store:
                def record_proof_media(self, payload, **kwargs):
                    return {'evidence_id': payload['evidence_id']}
            app = SimpleNamespace(_host_overview=lambda: {'nodes': []}, store=Store(), overview_lock=threading.Lock(), _store_generation=0)
            class Handler(BaseHTTPRequestHandler):
                mode = 'normal'
                def log_message(self, *args): pass
                def send_json(self, status, obj):
                    body = json.dumps(obj).encode()
                    self.send_response(status)
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                def do_GET(self): self.send_json(200, {'local_only': True, 'token': 'fixture-only', 'codex_home': str(home)})
                def do_POST(self):
                    event = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                    if Handler.mode == 'unknown':
                        self.send_json(400, {'error': 'private fixture detail must not be echoed'})
                        return
                    try:
                        result = console.App.authorize_original_proof(app, event)
                        self.send_json(200, {'ok': True, 'proof': result})
                    except console.ConsoleError as exc: self.send_json(400, {'ok': False, 'error': str(exc)})
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            def invoke(case):
                args = [sys.executable, str(package / 'scripts/swarm_proof.py'), str(source), '--evidence-id', case, '--task-id', 'fixture-task', '--kind', 'screenshot', '--caption', 'Fixture', '--codex-home', str(home), '--console-url', f'http://127.0.0.1:{server.server_port}']
                start = time.perf_counter()
                result = subprocess.run(args, text=True, capture_output=True)
                print(json.dumps({'case': case, 'exit': result.returncode, 'elapsed_ms': round((time.perf_counter()-start)*1000), 'saved_events': len(list((home/'swarm/proof-events').glob('*.json')))}), flush=True)
                return result
            try:
                unbound = invoke('unbound')
                print('unbound_error:', unbound.stderr.strip().splitlines()[-1], flush=True)
                self.assertEqual(unbound.returncode, 2)
                self.assertIn('original event saved but console registration failed: proof media requires an observed project-bound task', unbound.stderr)
                self.assertEqual(len(list((home/'swarm/proof-events').glob('*.json'))), 1)
                event_path = next((home/'swarm/proof-events').glob('*.json'))
                saved = event_path.read_bytes()
                event = json.loads(saved)
                self.assertEqual(event['disposition'], 'PENDING')
                app._host_overview = lambda: {'nodes': [{'id': 'fixture-task', 'virtual': False, 'project_id': 'fixture-project'}]}
                resumed = invoke('unbound')
                self.assertEqual(resumed.returncode, 0)
                self.assertEqual(event_path.read_bytes(), saved)
                self.assertEqual(len(list((home/'swarm/proof-events').glob('*.json'))), 1)
                bound = invoke('bound')
                self.assertEqual(bound.returncode, 0)
                Handler.mode = 'unknown'
                unknown = invoke('unknown')
                self.assertEqual(unknown.returncode, 2)
                self.assertIn('HTTP Error 400', unknown.stderr)
                self.assertNotIn('private fixture detail', unknown.stderr)
            finally:
                server.shutdown()
                server.server_close()
                worker.join()

if __name__ == '__main__':
    unittest.main(verbosity=2)
