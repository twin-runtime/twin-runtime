"""Real Core + Edge exercised through the local demo adapter and HTTP API."""
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from examples.demo_web import DemoState, make_handler
from reference.runtime_core import CoreDenied


class ManualClock:
    def __init__(self):
        self.wall_now = datetime(2026, 11, 11, 15, 0, tzinfo=timezone.utc)
        self.monotonic_now = 500.0

    def wall(self):
        return self.wall_now

    def monotonic(self):
        return self.monotonic_now

    def advance(self, seconds):
        self.wall_now += timedelta(seconds=seconds)
        self.monotonic_now += seconds


class TestWebDemoScenario(unittest.TestCase):
    def setUp(self):
        self.clock = ManualClock()
        self.service = DemoState(clock=self.clock.wall, monotonic=self.clock.monotonic)
        self.addCleanup(self.service.close)

    def test_real_core_edge_handover_and_rejection(self):
        initial = self.service.snapshot()
        self.assertEqual(initial['session']['session_status'], 'ready')
        self.assertEqual(initial['domains'][0]['controller'], None)
        self.service.perform('start')
        autonomous = self.service.snapshot()
        self.assertEqual(autonomous['session']['presence_mode'], 'autonomous')
        self.assertEqual({d['controller'] for d in autonomous['domains']}, {'ai-agent'})
        self.assertTrue(all(d['edge_authorized_now'] for d in autonomous['domains']))

        self.service.perform('ai_speak')
        self.assertEqual(self.service.snapshot()['last_command']['reason'], 'accepted')
        self.service.perform('ai_wave')
        self.assertTrue(self.service.snapshot()['last_command']['accepted'])

        self.service.perform('join')
        bridge = self.service.snapshot()
        self.assertEqual(bridge['session']['presence_mode'], 'bridge')
        self.assertEqual({d['name']: d['controller'] for d in bridge['domains']},
                         {'conversation': 'ai-agent', 'gesture': 'human-owner'})
        self.service.perform('stale_ai_wave')
        check = self.service.snapshot()['last_command']
        self.assertFalse(check['accepted'])
        self.assertEqual(check['reason'], 'stale_generation')
        self.service.perform('ai_speak')
        self.assertTrue(self.service.snapshot()['last_command']['accepted'])
        self.service.perform('owner_wave')
        self.assertTrue(self.service.snapshot()['last_command']['accepted'])

        self.service.perform('disconnect')
        suspended = self.service.snapshot()
        self.assertEqual(suspended['session']['session_status'], 'suspended')
        self.assertIsNone(suspended['session']['presence_mode'])
        self.assertFalse(any(d['edge_authorized_now'] for d in suspended['domains']))
        self.service.perform('stale_owner_wave')
        self.assertEqual(self.service.snapshot()['last_command']['reason'], 'revoked')
        self.assertFalse(self.service.snapshot()['last_command']['accepted'])
        events = self.service.core.events(self.service.session_id)
        self.assertEqual([x['session_sequence'] for x in events], list(range(1, len(events)+1)))
        self.assertTrue(any(x['event_type'] == 'fallback.triggered' for x in events))
        self.assertFalse(any(x['event_type'] == 'command.rejected' for x in events))

    def test_local_edge_ttl_fail_closed(self):
        self.service.perform('start')
        self.clock.advance(61)
        current = self.service.snapshot()
        self.assertTrue(all(not d['edge_authorized_now'] for d in current['domains']))
        self.service.perform('ai_speak')
        self.assertEqual(self.service.snapshot()['last_command']['reason'], 'expired')

    def test_reset_allocates_fresh_boot_and_does_not_reuse_leases(self):
        self.service.perform('start')
        old_boot = self.service.edge_boot_id
        old_ai = self.service.leases['conversation']['lease_id']
        self.service.perform('reset')
        self.assertNotEqual(self.service.edge_boot_id, old_boot)
        self.assertEqual(self.service.snapshot()['session']['session_status'], 'ready')
        self.assertIsNone(self.service.snapshot()['last_command'])
        self.service.perform('start')
        self.assertNotEqual(self.service.leases['conversation']['lease_id'], old_ai)

    def test_unavailable_actions_fail_and_do_not_progress_session(self):
        with self.assertRaises(CoreDenied):
            self.service.perform('join')
        with self.assertRaises(CoreDenied):
            self.service.perform('get_shell')
        with self.assertRaises(CoreDenied):
            self.service.perform('stale_ai_wave')
        self.assertEqual(self.service.snapshot()['session']['session_status'], 'ready')


class TestWebDemoHttp(unittest.TestCase):
    def setUp(self):
        self.clock = ManualClock()
        self.service = DemoState(clock=self.clock.wall, monotonic=self.clock.monotonic)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.service))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.root = f'http://127.0.0.1:{self.server.server_port}'
        # LIFO cleanup: shutdown server first, then join, close, clean state.
        self.addCleanup(self.service.close)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join, 2.0)
        self.addCleanup(self.server.shutdown)

    def post(self, action, *, headers=None):
        all_headers = {'Content-Type': 'application/json',
                       'X-Demo-Token': self.service.token,
                       'Origin': self.root}
        if headers:
            all_headers.update(headers)
        req = Request(self.root + '/api/action',
                      data=json.dumps({'action': action}).encode(),
                      headers=all_headers, method='POST')
        return urlopen(req, timeout=3)

    def test_get_static_assets_and_api(self):
        with urlopen(self.root + '/', timeout=3) as r:
            html = r.read().decode()
            self.assertIn('Concept UI - Simulated Twin Runtime Demo', html)
            self.assertIn('Simulation', html)
            self.assertIn('no physical robot', html.lower())
            self.assertIn('text/html', r.headers['Content-Type'])
        with urlopen(self.root + '/styles.css', timeout=3) as r:
            self.assertIn('text/css', r.headers['Content-Type'])
        with urlopen(self.root + '/app.js', timeout=3) as r:
            self.assertIn('text/javascript', r.headers['Content-Type'])
        with urlopen(self.root + '/api/state', timeout=3) as r:
            value = json.load(r)
            self.assertTrue(value['simulation'])
            self.assertEqual(value['csrf_token'], self.service.token)

    def test_visual_demo_has_accepted_only_animation_and_reduced_motion_fallback(self):
        # Static contract smoke-test; browser rendering is verified separately.
        with urlopen(self.root + '/', timeout=3) as r:
            html = r.read().decode()
        with urlopen(self.root + '/styles.css', timeout=3) as r:
            css = r.read().decode()
        with urlopen(self.root + '/app.js', timeout=3) as r:
            js = r.read().decode()
        self.assertIn('id="robot-action-label"', html)
        self.assertIn('class="robot-mouth"', html)
        self.assertIn('if (!check || !check.accepted) return;', js)
        self.assertIn('clearTimeout(animationTimer)', js)
        self.assertIn('OWNER GESTURE · SIMULATED', js)
        self.assertIn('.robot-wrap.is-waving .robot-arm-right{animation:none!important;', css)
        self.assertIn('.robot-wrap.is-talking .robot-head{animation:none!important;', css)

    def test_http_start_join_disconnect_changes_real_state(self):
        with self.post('start') as r:
            self.assertEqual(json.load(r)['session']['presence_mode'], 'autonomous')
        with self.post('join') as r:
            self.assertEqual(json.load(r)['session']['presence_mode'], 'bridge')
        with self.post('stale_ai_wave') as r:
            self.assertEqual(json.load(r)['last_command']['reason'], 'stale_generation')
        with self.post('disconnect') as r:
            self.assertEqual(json.load(r)['session']['session_status'], 'suspended')

    def test_http_rejects_missing_token_cross_origin_bad_actions_and_json(self):
        for override in ({'X-Demo-Token': 'invalid'}, {'Origin': 'http://evil.invalid'}):
            with self.assertRaises(HTTPError) as cm:
                self.post('start', headers=override)
            self.assertEqual(cm.exception.code, 403)
        with self.assertRaises(HTTPError) as cm:
            self.post('undefined_action')
        self.assertEqual(cm.exception.code, 409)
        request = Request(self.root + '/api/action', method='POST', data=b'{}',
                          headers={'Content-Type': 'text/plain', 'X-Demo-Token': self.service.token})
        with self.assertRaises(HTTPError) as cm:
            urlopen(request, timeout=3)
        self.assertEqual(cm.exception.code, 415)
        self.assertEqual(self.service.snapshot()['session']['session_status'], 'ready')


if __name__ == '__main__':
    unittest.main()
