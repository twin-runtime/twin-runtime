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

    def test_totalmersion_reassigns_both_domains_to_owner(self):
        self.service.perform('start')
        self.service.perform('join')
        old_ai_conversation = self.service.leases['conversation']
        self.service.perform('totalmersion')
        snapshot = self.service.snapshot()
        self.assertEqual(snapshot['session']['session_status'], 'active')
        self.assertEqual(snapshot['session']['presence_mode'], 'totalmersion')
        self.assertEqual({d['name']: d['controller'] for d in snapshot['domains']},
                         {'conversation': 'human-owner', 'gesture': 'human-owner'})
        self.assertTrue(all(d['edge_authorized_now'] for d in snapshot['domains']))
        self.assertEqual(self.service.stale_ai_conversation['lease_id'], old_ai_conversation['lease_id'])

        self.service.perform('owner_speak')
        self.assertTrue(self.service.snapshot()['last_command']['accepted'])
        self.assertEqual(self.service.snapshot()['last_command']['controller'], 'human-owner')
        self.service.perform('owner_wave')
        self.assertTrue(self.service.snapshot()['last_command']['accepted'])
        self.service.perform('stale_ai_speak')
        self.assertFalse(self.service.snapshot()['last_command']['accepted'])
        self.assertEqual(self.service.snapshot()['last_command']['reason'], 'stale_generation')

        with self.assertRaises(CoreDenied):
            self.service.perform('ai_speak')
        with self.assertRaises(CoreDenied):
            self.service.perform('ai_wave')

        self.service.perform('disconnect')
        suspended = self.service.snapshot()
        self.assertEqual(suspended['session']['session_status'], 'suspended')
        self.assertIsNone(suspended['session']['presence_mode'])
        self.assertFalse(any(d['edge_authorized_now'] for d in suspended['domains']))
        self.service.perform('stale_owner_wave')
        self.assertFalse(self.service.snapshot()['last_command']['accepted'])
        self.assertEqual(self.service.snapshot()['last_command']['reason'], 'revoked')
        self.assertTrue(any(
            e['event_type'] == 'presence_mode.changed' and
            e['data'].get('to_mode') == 'totalmersion'
            for e in self.service.core.events(self.service.session_id)))

    def test_totalmersion_requires_bridge_and_owner_speech_is_mode_scoped(self):
        with self.assertRaises(CoreDenied):
            self.service.perform('totalmersion')
        self.service.perform('start')
        with self.assertRaises(CoreDenied):
            self.service.perform('totalmersion')
        with self.assertRaises(CoreDenied):
            self.service.perform('owner_speak')
        with self.assertRaises(CoreDenied):
            self.service.perform('stale_ai_speak')
        self.service.perform('join')
        with self.assertRaises(CoreDenied):
            self.service.perform('owner_speak')
        self.service.perform('totalmersion')
        with self.assertRaises(CoreDenied):
            self.service.perform('totalmersion')

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
        self.assertIn('OWNER SPEECH · SIMULATED', js)
        self.assertIn('id="pill-totalmersion"', html)
        self.assertIn('id="run-full-scenario"', html)
        self.assertIn('id="scenario-progress"', html)
        self.assertIn('role="status"', html)
        self.assertIn('const fullScenarioSteps = [', js)
        self.assertIn('verifyScenarioStep(step, state)', js)
        self.assertIn('byId("run-full-scenario").addEventListener("click", runFullScenario)', js)
        self.assertIn('isBusy = true;', js)
        self.assertIn('if (!isBusy) loadState()', js)
        self.assertIn('data-action="totalmersion"', html)
        self.assertNotIn('id="pill-suspended"', html)
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

    def test_http_totalmersion_handover_and_old_ai_rejection(self):
        for action in ('start', 'join', 'totalmersion'):
            with self.post(action) as response:
                snapshot = json.load(response)
        self.assertEqual(snapshot['session']['presence_mode'], 'totalmersion')
        self.assertEqual({d['name']: d['controller'] for d in snapshot['domains']},
                         {'conversation': 'human-owner', 'gesture': 'human-owner'})
        with self.post('stale_ai_speak') as response:
            self.assertEqual(json.load(response)['last_command']['reason'], 'stale_generation')
        with self.post('owner_speak') as response:
            self.assertTrue(json.load(response)['last_command']['accepted'])
        with self.post('disconnect') as response:
            self.assertEqual(json.load(response)['session']['session_status'], 'suspended')

    def test_http_guided_scenario_uses_real_core_edge_actions(self):
        # Reproduce the one-click browser sequence against the same HTTP endpoints.
        steps = [
            ('reset', 'ready', None, None),
            ('start', 'active', 'autonomous', None),
            ('ai_wave', 'active', 'autonomous', (True, 'accepted')),
            ('join', 'active', 'bridge', None),
            ('owner_wave', 'active', 'bridge', (True, 'accepted')),
            ('totalmersion', 'active', 'totalmersion', None),
            ('owner_speak', 'active', 'totalmersion', (True, 'accepted')),
            ('stale_ai_speak', 'active', 'totalmersion', (False, 'stale_generation')),
            ('disconnect', 'suspended', None, None),
            ('stale_owner_wave', 'suspended', None, (False, 'revoked')),
        ]
        for action, status, mode, check in steps:
            with self.subTest(action=action), self.post(action) as response:
                snapshot = json.load(response)
                self.assertEqual(snapshot['session']['session_status'], status)
                self.assertEqual(snapshot['session']['presence_mode'], mode)
                if check is not None:
                    self.assertEqual(
                        (snapshot['last_command']['accepted'], snapshot['last_command']['reason']),
                        check,
                    )
        self.assertFalse(any(x['edge_authorized_now'] for x in snapshot['domains']))
        self.assertTrue(any(e['event_type'] == 'fallback.triggered' for e in snapshot['audit']))
        self.assertEqual(snapshot['command_checks'][0]['label'], 'Disconnected owner tries to wave')

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
