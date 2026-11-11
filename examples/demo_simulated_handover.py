"""Runnable demo: autonomous -> owner takeover -> disconnect -> suspended.

Run from repository root:
    python -m examples.demo_simulated_handover

All Core/Edge calls are in one trusted Python process. No real robot, human
presence verification, authenticated transport or OEM safety is implemented.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from uuid import uuid4

from reference.edge_fence import EdgeFenceState
from reference.runtime_core import RuntimeCore


def stamp(value: datetime) -> str:
    return value.isoformat().replace('+00:00', 'Z')


def main() -> None:
    now = datetime.now(timezone.utc)
    clock = lambda: now
    with tempfile.TemporaryDirectory(prefix='twin-runtime-demo-') as temp:
        core = RuntimeCore(Path(temp) / 'runtime.sqlite', trusted_clock=clock)
        edge = EdgeFenceState('edge-demo', 'boot-demo',
                              supported_control_domains=['conversation'],
                              trusted_wall_clock=clock)
        core.register_edge('edge-demo', 'boot-demo', ['conversation'])

        core.provision_grant({
            'grant_id':'grant-demo', 'provider_id':'trusted-local-admin',
            'owner_id':'owner-demo', 'authorized_subject':'twin-demo',
            'valid_from':stamp(now-timedelta(seconds=10)),
            'valid_until':stamp(now+timedelta(minutes=10)),
            'allowed_presence_modes':['autonomous','bridge'],
            'allowed_control_domains':['conversation'], 'status':'active',
            'restrictions':{},
        })
        core.create_session('session-demo','owner-demo','twin-demo',['grant-demo'],'edge-demo')
        core.set_policies('session-demo', {
            'policy_id':'session-policy-demo','session_id':'session-demo',
            'version':'1','status':'active',
            'controller_authorizations':[
                {'controller_id':'ai-agent','allowed_presence_modes':['autonomous'],
                 'allowed_control_domains':['conversation']},
                {'controller_id':'human-owner','allowed_presence_modes':['bridge'],
                 'allowed_control_domains':['conversation']},
            ],
            'fallback_autonomous_allowed':False,
            'human_liveness_timeout_ms':2000,
        }, {
            'policy_id':'compliance-demo','session_id':'session-demo',
            'version':'1','status':'active',
            'allowed_presence_modes':['autonomous','bridge'],
            'allowed_control_domains':['conversation'],
        })

        def sync_edge() -> None:
            for update_id, message in core.pending_edge_updates('edge-demo'):
                accepted, reason = edge.install_authority(message)
                if not accepted:
                    raise RuntimeError(f'Edge update rejected: {reason}')
                core.acknowledge_edge_update(update_id, 'edge-demo')

        def command(lease: dict, controller: str):
            envelope = {
                'command_id':'command_'+uuid4().hex,
                'session_id':'session-demo', 'control_domain':'conversation',
                'controller_id':controller,
                'lease_id':lease['lease_id'],
                'lease_generation':lease['generation'],
                'issued_at':stamp(now), 'payload':{'say':'hello'},
            }
            return edge.check_command(envelope, controller)

        core.prepare_session('session-demo')
        core.activate_session('session-demo','autonomous')
        ai_lease=core.issue_lease('session-demo','ai-agent','ai-agent','conversation','grant-demo')
        sync_edge()
        print('1. Autonomous: AI command ->', command(ai_lease, 'ai-agent'))

        # The host's explicitly authenticated human-presence signal is SIMULATED.
        core.change_mode('session-demo','bridge',owner_presence_confirmed=True)
        owner_lease=core.issue_lease('session-demo','human-owner','human-owner','conversation','grant-demo')
        sync_edge()
        print('2. Bridge: stale AI command ->', command(ai_lease, 'ai-agent'))
        print('3. Bridge: Owner command ->', command(owner_lease, 'human-owner'))

        # Trusted loss-of-connection notification is SIMULATED (no heartbeat detector).
        core.owner_disconnected('session-demo')
        sync_edge()
        print('4. Disconnect: Owner command ->', command(owner_lease, 'human-owner'))
        state=core.session_snapshot('session-demo')
        print('5. Session:', state['session_status'], '| mode:',state['presence_mode'],
              '| operational:',state['operational_state'])
        events=core.events('session-demo')
        print('6. Audit events:', len(events), '| sequence:',
              [e['session_sequence'] for e in events])
        print('   Recent:', [e['event_type'] for e in events[-6:]])


if __name__ == '__main__':
    main()
