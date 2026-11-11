"""Executable v0.1 Core + Edge reference slice; no real transport or robot."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator

from reference.runtime_core import RuntimeCore, CoreDenied
from reference.edge_fence import EdgeFenceState

BASE = datetime(2026, 11, 11, 14, 0, 0, tzinfo=timezone.utc)


def iso(t):
    return t.isoformat().replace('+00:00', 'Z')


class FakeClock:
    def __init__(self):
        self.now = BASE
        self.mono = 123.0

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)
        self.mono += seconds

    def wall(self):
        return self.now

    def monotonic(self):
        return self.mono


class TestRuntimeCore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'core.sqlite'
        self.clock = FakeClock()
        self.core = RuntimeCore(self.path, trusted_clock=self.clock.wall)
        self.edge = EdgeFenceState('edge-1', 'boot-1',
                                   supported_control_domains=['conversation', 'gesture'],
                                   monotonic_clock=self.clock.monotonic,
                                   trusted_wall_clock=self.clock.wall)
        self.core.register_edge('edge-1', 'boot-1', ['conversation', 'gesture'])
        self.core.provision_grant(self.grant())
        self.core.create_session('session-1', 'owner-1', 'twin-1', ['grant-1'], 'edge-1')
        self.core.set_policies('session-1', self.policy(), self.compliance())
        self.core.prepare_session('session-1')

    def grant(self, **overrides):
        return {
            'grant_id': 'grant-1', 'provider_id': 'provider-local',
            'owner_id': 'owner-1', 'authorized_subject': 'twin-1',
            'valid_from': iso(BASE-timedelta(minutes=1)),
            'valid_until': iso(BASE+timedelta(minutes=30)),
            'allowed_presence_modes': ['autonomous', 'bridge', 'totalmersion'],
            'allowed_control_domains': ['conversation','gesture'],
            'status': 'active', 'restrictions': {},
            **overrides,
        }

    def policy(self, version='1', **overrides):
        return {
            'policy_id':'policy-1','session_id':'session-1','version':version,'status':'active',
            'controller_authorizations': [
                {'controller_id':'ai-1','allowed_presence_modes':['autonomous','bridge'],
                 'allowed_control_domains':['conversation','gesture']},
                {'controller_id':'owner-controller','allowed_presence_modes':['bridge','totalmersion'],
                 'allowed_control_domains':['conversation','gesture']},
            ],
            'fallback_autonomous_allowed':False, 'human_liveness_timeout_ms':2000,
            **overrides,
        }

    def compliance(self, version='1', **overrides):
        return {
            'policy_id':'compliance-1','session_id':'session-1','version':version,'status':'active',
            'allowed_presence_modes':['autonomous','bridge','totalmersion'],
            'allowed_control_domains':['conversation','gesture'],
            **overrides,
        }

    def start(self, mode='autonomous'):
        self.core.activate_session('session-1',mode,owner_presence_confirmed=mode!='autonomous')

    def lease(self, controller='ai-1', domain='conversation'):
        return self.core.issue_lease('session-1',controller,controller,domain,'grant-1')

    def pump(self):
        results=[]
        for update_id,msg in self.core.pending_edge_updates('edge-1'):
            result=self.edge.install_authority(msg)
            if result[0]:
                self.core.acknowledge_edge_update(update_id,'edge-1')
            results.append((msg['kind'],result))
        return results

    def command(self, lease, command_id=None):
        return {'command_id':command_id or 'command_'+uuid4().hex,
                'session_id':lease['session_id'],'control_domain':lease['control_domain'],
                'lease_id':lease['lease_id'],'controller_id':lease['controller_id'],
                'lease_generation':lease['generation'],'issued_at':iso(self.clock.now),
                'payload':{'text':'hello'}}

    def assertReason(self, reason, fn, *args, **kwargs):
        with self.assertRaises(CoreDenied) as cm:
            fn(*args, **kwargs)
        self.assertEqual(cm.exception.reason, reason)

    def test_autonomous_grant_session_lease_edge_works(self):
        self.start()
        lease=self.lease()
        self.assertEqual(self.pump(), [('edge.authority_install',(True,'accepted'))])
        self.assertEqual(self.edge.check_command(self.command(lease),'ai-1'),(True,'accepted'))

    def test_unlisted_controller_never_authorized(self):
        self.start()
        self.assertReason('controller_not_authorized',self.core.issue_lease,
                          'session-1','random','random','conversation','grant-1')
        self.assertEqual(self.core.active_leases('session-1'),[])

    def test_controller_id_must_match_authenticated_identity(self):
        self.start()
        self.assertReason('controller_mismatch',self.core.issue_lease,
                          'session-1','ai-1','hacker','conversation','grant-1')

    def test_grant_is_not_controller_authority(self):
        self.start()
        self.assertReason('controller_not_authorized',self.core.issue_lease,
                          'session-1','owner-controller','owner-controller','conversation','grant-1')

    def test_handover_fences_old_commands(self):
        self.start()
        ai=self.lease();self.pump()
        self.core.change_mode('session-1','bridge',owner_presence_confirmed=True)
        owner=self.lease('owner-controller')
        self.assertGreater(owner['generation'],ai['generation'])
        self.pump()
        self.assertEqual(self.edge.check_command(self.command(ai),'ai-1')[0],False)
        self.assertEqual(self.edge.check_command(self.command(owner),'owner-controller'),(True,'accepted'))
        events=[e['event_type'] for e in self.core.events('session-1')]
        self.assertIn('presence_mode.changed',events)
        self.assertIn('lease.revoked',events)

    def test_handover_same_mode_records_controller_transfer(self):
        self.start('bridge')
        ai=self.lease();self.pump()
        owner=self.lease('owner-controller');self.pump()
        self.assertEqual(len(self.core.active_leases('session-1')),1)
        self.assertEqual(self.edge.check_command(self.command(ai),'ai-1')[0],False)
        self.assertEqual(self.edge.check_command(self.command(owner),'owner-controller'),(True,'accepted'))
        self.assertIn('control.handover',[e['event_type'] for e in self.core.events('session-1')])

    def test_owner_disconnect_suspends_and_fences(self):
        self.start('bridge')
        owner=self.lease('owner-controller');self.pump()
        self.core.owner_disconnected('session-1');self.pump()
        state=self.core.session_snapshot('session-1')
        self.assertEqual(state['session_status'],'suspended')
        self.assertIsNone(state['presence_mode'])
        self.assertEqual(state['operational_state'],'standby')
        self.assertEqual(self.edge.check_command(self.command(owner),'owner-controller')[0],False)
        self.assertIn('fallback.triggered',[e['event_type'] for e in self.core.events('session-1')])

    def test_owner_disconnect_not_an_autonomous_fallback(self):
        self.start('totalmersion')
        self.lease('owner-controller')
        self.core.owner_disconnected('session-1')
        self.assertEqual(self.core.session_snapshot('session-1')['session_status'],'suspended')
        self.assertEqual(self.core.active_leases('session-1'),[])

    def test_grant_revocation_invalidates_dependent_lease(self):
        self.start()
        lease=self.lease();self.pump()
        self.core.revoke_grant('grant-1');self.pump()
        self.assertEqual(self.core.session_snapshot('session-1')['session_status'],'suspended')
        self.assertEqual(self.core.active_leases('session-1'),[])
        self.assertEqual(self.edge.check_command(self.command(lease),'ai-1')[0],False)
        self.assertReason('no_valid_representation_authority',self.core.activate_session,'session-1','autonomous')

    def test_policy_change_revokes_all_leases_and_policy_version_immutable(self):
        self.start()
        self.lease();self.pump()
        self.core.set_policies('session-1',self.policy(version='2'),self.compliance())
        self.assertEqual(self.core.session_snapshot('session-1')['session_status'],'suspended')
        self.assertEqual(self.core.active_leases('session-1'),[])
        self.assertReason('policy_version_not_immutable',self.core.set_policies,
                          'session-1',self.policy(version='2',fallback_autonomous_allowed=True),self.compliance())

    def test_compliance_policy_blocks_control_domain(self):
        self.core.set_policies('session-1',self.policy(),self.compliance(version='2',allowed_control_domains=['conversation']))
        self.start()
        self.assertReason('compliance_domain_denied',self.core.issue_lease,
                          'session-1','ai-1','ai-1','gesture','grant-1')

    def test_undeclared_edge_domain_is_denied(self):
        # A Grant may include a domain absent from the Edge's trusted capabilities.
        self.core.register_edge('edge-1','boot-1',['gesture'])
        self.start()
        self.assertReason('domain_unsupported',self.core.issue_lease,
                          'session-1','ai-1','ai-1','conversation','grant-1')

    def test_liveness_configuration_required_for_bridge(self):
        policy=self.policy(version='2')
        del policy['human_liveness_timeout_ms']
        self.core.set_policies('session-1',policy,self.compliance())
        self.assertReason('missing_human_liveness_timeout',self.core.activate_session,
                          'session-1','bridge',owner_presence_confirmed=True)
        self.core.set_policies('session-1',self.policy(version='3'),self.compliance())
        self.assertReason('owner_presence_not_confirmed',self.core.activate_session,'session-1','bridge')
        state=self.core.session_snapshot('session-1')
        self.assertEqual(state['session_status'],'suspended')

    def test_totalmersion_inactive_if_not_in_compliance(self):
        self.core.set_policies('session-1',self.policy(),self.compliance(version='2',allowed_presence_modes=['autonomous','bridge']))
        self.assertReason('compliance_mode_denied',self.core.activate_session,'session-1','totalmersion',owner_presence_confirmed=True)

    def test_core_restart_does_not_reset_generation(self):
        self.start()
        first=self.lease();self.pump()
        after_restart=RuntimeCore(self.path,trusted_clock=self.clock.wall)
        after_restart.change_mode('session-1','bridge',owner_presence_confirmed=True)
        second=after_restart.issue_lease('session-1','owner-controller','owner-controller','conversation','grant-1')
        self.assertGreater(second['generation'],first['generation'])
        self.assertEqual(after_restart.events('session-1')[-1]['event_type'],'lease.issued')

    def test_edge_boot_change_invalidates_core_and_suspends(self):
        self.start('bridge');self.lease('owner-controller');self.pump()
        self.core.register_edge('edge-1','boot-2',['conversation','gesture'])
        self.assertEqual(self.core.active_leases('session-1'),[])
        self.assertEqual(self.core.session_snapshot('session-1')['session_status'],'suspended')
        queued=self.core.pending_edge_updates('edge-1')
        self.assertTrue(queued)
        self.assertTrue(all(m['edge_boot_id']=='boot-2' and m['kind']=='edge.authority_revoke' for _,m in queued))

    def test_events_are_session_scoped_and_strictly_ordered(self):
        self.start();self.lease();self.core.revoke_grant('grant-1')
        events=self.core.events('session-1')
        self.assertEqual([e['session_sequence'] for e in events],list(range(1,len(events)+1)))
        self.assertEqual(len({e['event_id'] for e in events}),len(events))
        for e in events:
            self.assertTrue(e['correlation_id'])

    def test_multi_presence_independent_sessions(self):
        self.core.create_session('session-2','owner-1','twin-1',['grant-1'],'edge-1')
        policy2=self.policy();policy2.update(policy_id='policy-2',session_id='session-2')
        compliance2=self.compliance();compliance2.update(policy_id='compliance-2',session_id='session-2')
        self.core.set_policies('session-2',policy2,compliance2)
        self.core.prepare_session('session-2');self.core.activate_session('session-2','autonomous')
        self.start();a=self.lease()
        b=self.core.issue_lease('session-2','ai-1','ai-1','conversation','grant-1')
        self.assertEqual(a['generation'],1)
        self.assertEqual(b['generation'],1)
        self.assertNotEqual(a['lease_id'],b['lease_id'])
        self.core.revoke_session_control('session-1')
        self.assertEqual(len(self.core.active_leases('session-2')),1)

    def test_schema_definitions_are_valid_draft_2020_12(self):
        import json
        root=Path(__file__).resolve().parents[1]/'spec'/'v0.1'
        for name in ('session','representation-grant','session-policy','compliance-policy','control-lease','runtime-event'):
            Draft202012Validator.check_schema(json.loads((root/f'{name}.schema.json').read_text()))

    def test_reused_edge_boot_epoch_is_rejected(self):
        self.core.register_edge('edge-1','boot-2',['conversation','gesture'])
        self.assertReason('edge_boot_epoch_reused',self.core.register_edge,
                          'edge-1','boot-1',['conversation','gesture'])

    def test_capability_manifest_change_fences_active_authority(self):
        self.start()
        self.lease(); self.pump()
        self.core.register_edge('edge-1','boot-1',['gesture'])
        self.assertEqual(self.core.active_leases('session-1'),[])
        self.assertEqual(self.core.session_snapshot('session-1')['session_status'],'suspended')

    def test_wrong_grant_subject_fails_before_session_activation(self):
        with tempfile.TemporaryDirectory() as temp:
            second=RuntimeCore(Path(temp)/'core.sqlite',trusted_clock=self.clock.wall)
            second.register_edge('edge-x','boot-x',['conversation'])
            second.provision_grant(self.grant(authorized_subject='other-twin'))
            second.create_session('session-x','owner-1','twin-1',['grant-1'],'edge-x')
            policy=self.policy(); policy.update(policy_id='policy-x',session_id='session-x')
            compliance=self.compliance(); compliance.update(policy_id='comp-x',session_id='session-x')
            second.set_policies('session-x',policy,compliance)
            self.assertReason('no_valid_representation_authority',second.prepare_session,'session-x')

    def test_session_mode_schema_rejects_active_null_mode(self):
        from reference.runtime_core import _VALIDATORS
        state=self.core.session_snapshot('session-1')
        state['session_status']='active'
        self.assertFalse(_VALIDATORS['session'].is_valid(state))
        state['session_status']='suspended';state['presence_mode']='bridge'
        self.assertFalse(_VALIDATORS['session'].is_valid(state))

    def test_concurrent_lease_issuance_is_serialized(self):
        from concurrent.futures import ThreadPoolExecutor
        self.start()
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures=[executor.submit(self.core.issue_lease,'session-1','ai-1','ai-1',
                                     'conversation','grant-1') for _ in range(2)]
            issued=[f.result() for f in futures]
        self.assertEqual(len(self.core.active_leases('session-1')),1)
        self.assertNotEqual(issued[0]['generation'],issued[1]['generation'])
        self.assertTrue(all(lease['generation']>=1 for lease in issued))

    def test_grant_expiration_blocks_new_lease_even_if_session_is_active(self):
        self.start()
        self.clock.advance(31*60)
        self.assertReason('grant_inactive_or_expired',self.core.issue_lease,
                          'session-1','ai-1','ai-1','conversation','grant-1')
        self.assertEqual(self.core.active_leases('session-1'),[])

    def test_unknown_grant_restrictions_fail_closed_at_provisioning(self):
        grant=self.grant(grant_id='grant-other',restrictions={'unknown_scope':True})
        self.assertReason('malformed_representation_grant',self.core.provision_grant,grant)

    def test_rejected_lease_issue_rolls_back_without_audit_or_outbox(self):
        self.start()
        before_events=len(self.core.events('session-1'))
        self.assertReason('controller_not_authorized',self.core.issue_lease,
                          'session-1','unknown','unknown','conversation','grant-1')
        self.assertEqual(len(self.core.events('session-1')),before_events)
        self.assertEqual(self.core.pending_edge_updates('edge-1'),[])

    def test_core_refuses_in_memory_non_durable_fencing(self):
        with self.assertRaises(ValueError):
            RuntimeCore(':memory:')


if __name__=='__main__':
    unittest.main()
