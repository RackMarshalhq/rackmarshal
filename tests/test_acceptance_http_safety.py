"""Standalone acceptance scripts must inspect their selected endpoint."""
import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AcceptanceHttpSafety(unittest.TestCase):
    def test_reject_non_http_credentials_and_controls_before_io(self):
        proof = load('prove-incident-narrative')
        promotion = load('promote-package-files')
        bad = ['file:///tmp/fixture', 'data:application/json,{}', 'ftp://localhost/a',
               'http://user:password@localhost/a', 'http://@localhost/a',
               'http://localhost:99999/a', 'http://localhost:0/a',
               'http://localhost/\nhealth', ' http://localhost/health',
               'http://localhost/a#fragment', 'http://localhost\\other/a']
        for module in (proof, promotion):
            with patch.object(module, 'build_opener') as opener:
                for url in bad:
                    with self.subTest(script=module.__name__, url=url):
                        with self.assertRaises(ValueError):
                            module.urlopen(url, timeout=1)
                opener.assert_not_called()

    def test_readiness_and_proof_reject_redirects_without_visiting_target(self):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                seen.append(self.path)
                if self.path == '/redirect':
                    self.send_response(302)
                    self.send_header('Location', '/target')
                else:
                    self.send_response(200)
                self.end_headers()

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            base = 'http://127.0.0.1:' + str(server.server_port)
            with patch.dict(os.environ, {'no_proxy': '*'}):
                for module in (load('prove-incident-narrative'), load('promote-package-files')):
                    with self.subTest(script=module.__name__):
                        with self.assertRaises(HTTPError) as caught:
                            module.urlopen(base + '/redirect', timeout=2)
                        caught.exception.close()
                        with module.urlopen(base + '/direct', timeout=2) as response:
                            self.assertEqual(response.status, 200)
                self.assertNotIn('/target', seen)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_optimized_narrative_cannot_emit_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'receipt.json'
            for mode in ('-O', '-OO'):
                result = subprocess.run([sys.executable, mode,
                    str(ROOT / 'scripts/prove-incident-narrative.py'),
                    '--base-url', 'http://127.0.0.1:1', '--output', str(output)],
                    capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('without optimization', result.stderr)
                self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
