"""Synthetic loopback-only transport/security regression tests."""
import json
import io
import ssl
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from rackmarshal import http


@contextmanager
def server():
    events = []
    routes = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            events.append((self.path, dict(self.headers), body))
            status, headers, result = routes.get(self.path, (200, {}, b'{"data": []}'))
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(result)

        do_POST = do_GET

    instance = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=instance.serve_forever, daemon=True)
    worker.start()
    try:
        yield f'http://127.0.0.1:{instance.server_port}', events, routes
    finally:
        instance.shutdown()
        worker.join()
        instance.server_close()


class HTTPTransportTests(unittest.TestCase):
    def test_unsafe_initial_urls_rejected_before_io(self):
        bad = ['file:///etc/passwd', 'data:text/plain,secret', 'ftp://localhost/a',
               'http://user:secret@localhost/', 'http://@localhost/',
               ' http://localhost/', 'http://localhost/\n', 'http://localhost/\t',
               'http://local host/', 'http://localhost\\@evil/', 'http:///x',
               'http://localhost:0/', 'http://localhost:65536/', 'http://localhost:x/',
               'http://localhost:/', 'http://[::1]garbage/', 'http://[bad]/', 'http://host%2eexample/',
               'http://-bad/', 'http://bad../', 'http://localhost/\x7f']
        with patch('urllib.request.build_opener') as opener:
            for url in bad:
                with self.subTest(url=url):
                    with self.assertRaises(urllib.error.URLError):
                        http.urlopen(url)
                    with self.assertRaises(urllib.error.URLError):
                        http.Request(url)
            opener.assert_not_called()

    def test_valid_private_and_public_initial_urls(self):
        for url in ['http://localhost/a', 'https://127.0.0.1:8443/',
                    'http://[fd00::1]/', 'http://[::1]:8000/',
                    'https://example.org/', 'http://pbs-store/', 'http://host.example./']:
            self.assertEqual(http.validate_url(url), url)

    def test_plain_urllib_reproduces_cross_port_authorization_leak(self):
        # Control demonstrates the defect without contacting an external host.
        with server() as (source, _, routes), server() as (target, received, _):
            routes['/redirect'] = (302, {'Location': target + '/sink'}, b'')
            request = urllib.request.Request(source + '/redirect', data=b'private',
                                             headers={'Authorization': 'Bearer synthetic'})
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request) as response:
                response.read()
            self.assertEqual(received[0][1]['Authorization'], 'Bearer synthetic')

    def test_cross_origin_receiver_untouched_for_redirect_methods(self):
        with server() as (source, _, routes), server() as (target, received, _):
            for method in ['GET', 'POST']:
                for code in [301, 302, 303, 307, 308]:
                    with self.subTest(method=method, code=code):
                        routes['/redirect'] = (code, {'Location': target + '/sink'}, b'')
                        req = http.Request(source + '/redirect',
                                           data=b'private body' if method == 'POST' else None,
                                           headers={'Authorization': 'Bearer synthetic',
                                                    'Cookie': 'synthetic=secret'}, method=method)
                        with self.assertRaises(urllib.error.URLError):
                            http.urlopen(req, timeout=2)
                        self.assertEqual(received, [])

    def test_relative_same_origin_redirect_preserves_get_credentials(self):
        with server() as (base, events, routes):
            routes['/redirect'] = (302, {'Location': '/target'}, b'')
            with http.urlopen(http.Request(base + '/redirect',
                                          headers={'Authorization': 'Bearer synthetic'})) as response:
                self.assertEqual(json.load(response), {'data': []})
            self.assertEqual([e[0] for e in events], ['/redirect', '/target'])
            self.assertEqual(events[1][1]['Authorization'], 'Bearer synthetic')

    def test_same_origin_post_302_keeps_urllib_method_semantics(self):
        with server() as (base, events, routes):
            routes['/redirect'] = (302, {'Location': '/target'}, b'')
            with http.urlopen(http.Request(base + '/redirect', data=b'private')) as response:
                response.read()
            self.assertEqual(events[0][2], b'private')
            self.assertEqual(events[1][2], b'')

    def test_redirect_scheme_host_port_change_and_downgrade(self):
        handler = http._SameOriginRedirectHandler()
        req = http.Request('https://example.test/private',
                           headers={'Authorization': 'Bearer synthetic'})
        for url in ['http://example.test/private', 'https://example.test:444/private',
                    'https://other.test/private', 'file:///tmp/private']:
            with self.subTest(url=url), self.assertRaises(urllib.error.URLError):
                response = io.BytesIO(b"never read")
                try:
                    handler.redirect_request(req, response, 302, 'redirect', {}, url)
                finally:
                    self.assertTrue(response.closed)
        result = handler.redirect_request(req, None, 302, 'redirect', {},
                                          'https://EXAMPLE.TEST:443/next')
        self.assertEqual(result.headers['Authorization'], 'Bearer synthetic')

    def test_custom_tls_context_and_timeout_are_forwarded(self):
        context = ssl.create_default_context()
        with patch('urllib.request.build_opener') as build:
            http.urlopen('https://localhost/', data=b'hello', timeout=7, context=context)
            tls = next(h for h in build.call_args.args if isinstance(h, urllib.request.HTTPSHandler))
            self.assertIs(tls._context, context)
            build.return_value.open.assert_called_once_with('https://localhost/', data=b'hello', timeout=7)

    def test_proxy_configuration_still_used(self):
        # Proxy receives an absolute URI; no DNS or remote connection occurs.
        with server() as (proxy, events, _):
            with patch.dict('os.environ', {'http_proxy': proxy, 'HTTP_PROXY': '',
                                         'no_proxy': '', 'NO_PROXY': ''}, clear=True):
                with http.urlopen('http://not-a-real-destination.invalid/data', timeout=2) as response:
                    response.read()
            self.assertEqual(events[0][0], 'http://not-a-real-destination.invalid/data')

    def test_http_errors_and_redirect_loops_preserve_exceptions(self):
        with server() as (base, _, routes):
            routes['/missing'] = (404, {}, b'not found')
            routes['/loop'] = (302, {'Location': '/loop'}, b'')
            with self.assertRaises(urllib.error.HTTPError) as caught:
                http.urlopen(base + '/missing')
            self.assertEqual(caught.exception.code, 404)
            self.assertEqual(caught.exception.read(), b'not found')
            caught.exception.close()
            with self.assertRaises(urllib.error.HTTPError) as caught:
                http.urlopen(base + '/loop')
            caught.exception.close()

    def test_backup_collector_success_and_redirect_error_contract(self):
        with patch("rackmarshal.core.config.load_config", return_value={"PVE_NODE": "synthetic"}):
            from rackmarshal.domains.backup.collector import api_get, CollectionError
        with server() as (source, _, routes), server() as (target, received, _):
            self.assertEqual(api_get(source, '/api', {'Authorization': 'synthetic'}, None, 'PBS'), [])
            routes['/api'] = (302, {'Location': target + '/sink'}, b'')
            with self.assertRaises(CollectionError):
                api_get(source, '/api', {'Authorization': 'synthetic'}, None, 'PBS')
            self.assertEqual(received, [])
            with self.assertRaises(CollectionError):
                api_get("file:///tmp/synthetic", "/api", {}, None, "PBS")

    def test_ha_delivery_export_and_pve_mount_callers_block_redirects(self):
        from rackmarshal.notifications.delivery import send_ha, DeliveryError
        from rackmarshal.evidence.export import fetch_status
        with patch("rackmarshal.core.config.load_config", return_value={"PVE_NODE": "synthetic"}):
            from rackmarshal.domains.ha.collector import api_get as ha_get, CollectorError
            from rackmarshal.domains.pve.collector import api_get as pve_get
            from rackmarshal.domains.mount.collector import api_request
        context = ssl.create_default_context()
        with server() as (source, _, routes), server() as (target, received, _):
            config = {"PVE_API_URL": source, "PVE_TOKEN_ID": "synthetic", "PVE_TOKEN_SECRET": "secret"}
            with patch("ssl.create_default_context", return_value=context), patch("rackmarshal.core.config.load_config", return_value={"PVE_NODE": "synthetic"}):
                self.assertEqual(ha_get(source, "synthetic", "/api"), {"data": []})
                self.assertEqual(pve_get(config, "/api"), [])
                self.assertEqual(api_request(config, "POST", "/api", {"test": "value"}), {"data": []})
                self.assertEqual(fetch_status(source + "/api"), {"data": []})
                send_ha(source, "synthetic", "id", "title", "message")
                for path in ["/api", "/api/services/persistent_notification/create"]:
                    routes[path] = (302, {"Location": target + "/sink"}, b"")
                calls = [(lambda: ha_get(source, "synthetic", "/api"), CollectorError),
                         (lambda: pve_get(config, "/api"), RuntimeError),
                         (lambda: api_request(config, "POST", "/api", {"test": "value"}), RuntimeError),
                         (lambda: fetch_status(source + "/api"), RuntimeError),
                         (lambda: send_ha(source, "synthetic", "id", "title", "message"), DeliveryError)]
                for call, error in calls:
                    with self.assertRaises(error):
                        call()
                self.assertEqual(received, [])
                bad_config = dict(config, PVE_API_URL="file:///tmp/synthetic")
                invalid_calls = [(lambda: ha_get("file:///tmp/synthetic", "synthetic", "/api"), CollectorError),
                                 (lambda: pve_get(bad_config, "/api"), RuntimeError),
                                 (lambda: api_request(bad_config, "GET", "/api"), RuntimeError),
                                 (lambda: fetch_status("file:///tmp/synthetic"), RuntimeError),
                                 (lambda: send_ha("file:///tmp/synthetic", "synthetic", "id", "title", "message"), DeliveryError)]
                with patch("urllib.request.build_opener") as opener:
                    for call, error in invalid_calls:
                        with self.assertRaises(error):
                            call()
                    opener.assert_not_called()


if __name__ == '__main__':
    unittest.main()
