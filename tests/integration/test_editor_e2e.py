"""End-to-end: the current local Channel Editor checkout talks to the simulator over real SSH/SFTP.

Set LG_EDITOR_PATH to the editor checkout (default ~/PhpstormProjects/lg-webos-channel-editor)
and LG_EDITOR_PYTHON to its interpreter (default: python3).  Skipped if unavailable.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.conftest import PASSWORD

pytestmark = pytest.mark.editor

EDITOR = Path(os.environ.get('LG_EDITOR_PATH', Path.home() / 'PhpstormProjects' / 'lg-webos-channel-editor'))
PYTHON = os.environ.get('LG_EDITOR_PYTHON', 'python3')
DRIVER = Path(__file__).resolve().parent / 'editor_driver.py'


def _editor_available() -> str | None:
    if not (EDITOR / 'app.py').is_file() or not (EDITOR / 'tv_write.py').is_file():
        return f'editor checkout not found at {EDITOR}'
    probe = subprocess.run([PYTHON, '-c', 'import paramiko'], capture_output=True)
    if probe.returncode != 0:
        return f'{PYTHON} has no paramiko'
    return None


@pytest.fixture
def editor(tmp_path, running):
    reason = _editor_available()
    if reason:
        pytest.skip(reason)
    copy = tmp_path / 'editor'
    shutil.copytree(EDITOR, copy, ignore=shutil.ignore_patterns('data', '.git', '__pycache__', '.idea', '*.sqlite'))
    home = tmp_path / 'home'

    class Editor:
        def __init__(self):
            self.sim = None
            self.calls = 0

        def start(self, fixture='synthetic_favorites_47', scenario=None, device=None):
            self.sim = running(fixture, scenario, device)
            (home / '.ssh').mkdir(parents=True, exist_ok=True)
            shutil.copy(self.sim.known_hosts, home / '.ssh' / 'known_hosts')
            return self.sim

        def run(self, action, *args, timeout=600):
            self.calls += 1
            env = {'HOME': str(home), 'PATH': os.environ.get('PATH', ''), 'SIM_PASSWORD': PASSWORD,
                   'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1'}
            data = tmp_path / f'data-{self.calls}'
            proc = subprocess.run([PYTHON, str(DRIVER), str(copy), str(data), str(self.sim.port), action, *args],
                                  capture_output=True, text=True, env=env, timeout=timeout)
            assert proc.returncode == 0, proc.stderr[-3000:]
            return json.loads(proc.stdout.strip().splitlines()[-1])

    return Editor()


def by_id(state):
    return {c['id']: c for c in state['channels']}


def test_editor_login_check_and_import(editor):
    sim = editor.start('mini')
    login = editor.run('login')['login']
    assert login['ok'] is True and login['host'] == '127.0.0.1'
    assert login['tv']['model'] == 'OLED55C27LA' and login['tv']['serial'].startswith('SIM-')   # v0.6.4 identity
    result = editor.run('import')
    assert result['ok'], result
    imported = by_id(result['state'])
    live = {c['channel_id']: c for c in sim.sim.channels()}
    assert set(imported) == set(live)
    for cid, channel in live.items():
        assert imported[cid]['number'] == channel['number']
        assert sorted(imported[cid]['groups']) == channel['groups']
    welt = [c for c in imported.values() if c['name'] == 'WELT HD']
    assert sorted(c['number'] for c in welt) == [13, 403, 1015]                       # T09
    assert sorted(c['number'] for c in imported.values() if c['number'] == 101) == [101, 101]  # T10
    kinds = [e['effect'] for e in sim.sim.journal.events() if e['kind'] == 'command']
    assert kinds[-3:] == ['BACKUP', 'REMOVE_TEMP', 'LOGIN_CHECK'] or 'BACKUP' in kinds
    assert not list(sim.sim.run.tmp_dir.iterdir()), 'editor must remove its remote temp file'


def test_editor_imports_realistic_fixture_with_all_reception_modes(editor):
    sim = editor.start('synthetic_realistic')
    result = editor.run('import')
    assert result['ok'], result
    imported = by_id(result['state'])
    live = {c['channel_id']: c for c in sim.sim.channels()}
    assert set(imported) == set(live)
    modes = {}
    for channel in imported.values():
        modes[channel['mode']] = modes.get(channel['mode'], 0) + 1
    assert modes == {'Satellite': 709, 'Cable': 170, 'Terrestrial': 36}
    a = sorted((c['groups']['A'], c['number']) for c in imported.values() if 'A' in c['groups'])
    assert [number for _, number in a] == list(range(1, 52))


def test_editor_rejects_wrong_host_key(editor, tmp_path):
    editor.start('mini')
    (tmp_path / 'home' / '.ssh' / 'known_hosts').write_text(
        f'[127.0.0.1]:{editor.sim.port} ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl\n')
    result = editor.run('import')
    assert not result['ok']
    assert 'BadHostKey' in result['error_type'] or 'host' in result['error'].lower()


def test_golden_full_renumbering_of_47_favorites(editor, tmp_path):
    """Spec §14.1: reset, import, renumber A to 1..47, preview, transfer, re-import and verify."""
    sim = editor.start('synthetic_favorites_47')
    result = editor.run('renumber-write', 'A', '1')
    (tmp_path / 'golden-journal.jsonl').write_text(
        ''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in sim.sim.journal.events()))
    assert result['ok'], (result.get('error_keys'), result.get('error'), result.get('traceback'))

    before, after = by_id(result['before']), result['after']['channels']
    favorites_a = sorted((c for c in after if 'A' in c['groups']), key=lambda c: c['groups']['A'])
    assert [c['number'] for c in favorites_a] == list(range(1, 48))
    # order of the list is unchanged (same services in the same sequence)
    old_order = [c['name'] for c in sorted((c for c in before.values() if 'A' in c['groups']),
                                           key=lambda c: c['groups']['A'])]
    assert [c['name'] for c in favorites_a] == old_order
    # Astra copies: originals stay on their old numbers without A, copies carry A
    for name, old in (('ProSieben MAXX HD', 418), ('ARD-alpha HD', 125), ('NDR FS HH HD', 101), ('HGTV HD', 1827)):
        entries = [c for c in after if c['name'] == name and c['mode'] == 'Satellite']
        originals = [c for c in entries if c['number'] == old]
        copies = [c for c in entries if c['number'] <= 99]
        assert len(originals) == 1 and 'A' not in originals[0]['groups'], (name, entries)
        assert len(copies) == 1 and 'A' in copies[0]['groups'], (name, entries)
    # unrelated entries untouched: cable list and the WELT HD twins
    for c in after:
        if c['mode'] == 'Cable' or (c['name'] == 'WELT HD' and c['number'] in (403, 1015)):
            assert c['id'] in before and before[c['id']]['number'] == c['number']
    # Pinned for fixture synthetic_favorites_47 v1 only (spec §14.1: never a universal constant).
    preview = {}
    for op in result['preview']:
        preview[op['type']] = preview.get(op['type'], 0) + 1
    assert preview == {'number': 49, 'swap': 7, 'copy_favorite': 4, 'order': 1}
    effects = {}
    for event in sim.sim.journal.events():
        if event['kind'] == 'luna' and event['method'] == 'changeChannelNumber':
            effects[event['effect']] = effects.get(event['effect'], 0) + 1
    assert effects == {'MOVE': 49, 'SWAP': 7, 'COPY': 4}
    # simulator truth equals what the editor re-imported
    live = {c['channel_id']: c for c in sim.sim.channels()}
    assert {c['id']: c['number'] for c in after} == {k: v['number'] for k, v in live.items()}
    assert not sim.sim.engine.invariant_violations()


def test_favorites_and_group_name_transfer(editor):
    sim = editor.start('mini')
    channels = {c['name'] + str(c['number']): c for c in sim.sim.channels()}
    wanted = [channels['RTL HD3']['channel_id'], channels['Das Erste HD1']['channel_id'],
              channels['SAT.1 HD4']['channel_id']]
    result = editor.run('set-favorites-write', json.dumps({'group': 'C', 'ids': wanted, 'rename': 'Privat'}))
    assert result['ok'], (result.get('error_keys'), result.get('error'))
    after = sorted((c for c in result['after']['channels'] if 'C' in c['groups']), key=lambda c: c['groups']['C'])
    assert [c['id'] for c in after] == wanted
    assert result['after']['group_names']['202'] == 'Privat'
    # B and the other lists stay untouched (T43)
    for c in sim.sim.channels():
        if c['name'] == 'ZDF HD':
            assert c['groups'] == ['A', 'B']


def test_partial_failure_then_reimport_shows_intermediate_state(editor):
    """T33/T34: the third number change fails; steps 1-2 remain, the re-import shows the real state."""
    sim = editor.start('synthetic_favorites_47', scenario='fail_after_second_step')
    result = editor.run('renumber-write', 'A', '1')
    assert not result['ok']
    changes = [e for e in sim.sim.journal.events() if e['kind'] == 'luna' and e['method'] == 'changeChannelNumber']
    assert len(changes) == 3 and changes[-1]['effect'] == 'DISCONNECT_BEFORE_MUTATION'
    reimport = editor.run('import')
    live = {c['channel_id']: c['number'] for c in sim.sim.channels()}
    assert {c['id']: c['number'] for c in reimport['state']['channels']} == live


# ---------------------------------------------------------------- editor v0.6.4: all modes and LG Channels

def _ids(sim):
    return {c['name']: c['channel_id'] for c in sim.sim.channels(include_ip=True)}


def _list(state, group):
    members = [c for c in state['channels'] if group in c['groups']]
    return [c['name'] for c in sorted(members, key=lambda c: c['groups'][group])]


def _failed(result):
    return f"{result.get('error_keys')} {result.get('error')}"


def test_v064_cable_channel_into_list_a(editor):
    sim = editor.start('mixed_modes')
    ids = _ids(sim)
    a = _list(editor.run('import')['state'], 'A')
    tuner_before = sim.sim.engine.content_hash()
    result = editor.run('edit-write', json.dumps([{'op': 'members', 'group': 'A',
                                                   'ids': [ids[n] for n in a] + [ids['Kabel Regional']]}]))
    assert result['ok'], _failed(result)
    assert sim.sim.engine.content_hash() != tuner_before
    cable = next(c for c in sim.sim.channels() if c['name'] == 'Kabel Regional')
    assert 'A' in cable['groups']


def test_v064_lg_channels_list_add_reorder_remove(editor):
    sim = editor.start('mixed_modes')
    ids = _ids(sim)
    wanted = ['Stream News', 'LG 1', 'Stream Doku']          # remove "LG 1: Film", add "Stream Doku", reorder
    result = editor.run('edit-write', json.dumps([{'op': 'members', 'group': 'D', 'ids': [ids[n] for n in wanted]}]))
    assert result['ok'], _failed(result)
    assert {op['type'] for op in result['preview']} >= {'add', 'remove', 'order'}
    assert _list(result['after'], 'D') == _list(result['local'], 'D') == wanted
    live = sorted((c for c in sim.sim.channels(include_ip=True) if 'D' in c['groups']), key=lambda c: c['index']['D'])
    assert [(c['name'], c['index']['D']) for c in live] == [('Stream News', 251), ('LG 1', 252), ('Stream Doku', 253)]
    assert sim.sim.engine.invariant_violations() == set()


def test_v064_satellite_onto_a_number_only_cable_holds(editor):
    sim = editor.start('mixed_modes')
    ids = _ids(sim)
    result = editor.run('edit-write', json.dumps([{'op': 'number', 'id': ids['VOX HD'], 'number': 20}]))
    assert result['ok'], _failed(result)
    effects = [e['effect'] for e in sim.sim.journal.events() if e.get('method') == 'changeChannelNumber']
    assert effects == ['MOVE']
    numbers = {(c['name'], c['mode']): c['number'] for c in sim.sim.channels()}
    assert numbers[('VOX HD', 'Satellite')] == 20 and numbers[('Kabel Regional', 'Cable')] == 20


def test_v064_ip_before_satellite_in_mixed_list_is_unconfirmed(editor):
    sim = editor.start('mixed_modes')
    ids = _ids(sim)
    a = _list(editor.run('import')['state'], 'A')
    first_ip = next(n for n in a if n.startswith('Stream'))
    wanted = [first_ip] + [n for n in a if n != first_ip]
    result = editor.run('edit-write', json.dumps([{'op': 'members', 'group': 'A', 'ids': [ids[n] for n in wanted]}]))
    assert not result['ok'] and 'error.order.unconfirmed' in result['error_keys'], _failed(result)
    blocked = [e for e in sim.sim.journal.events() if e.get('effect') == 'FAVORITE_ORDER_BLOCKED_IP']
    assert blocked and blocked[-1]['response'] == {'returnValue': True}
    reimport = editor.run('import')
    assert _list(reimport['state'], 'A') == a                       # nothing moved, state stays consistent
    assert sim.sim.engine.invariant_violations() == set()


def test_v064_cable_number_change_is_an_honest_error(editor):
    sim = editor.start('mixed_modes')
    ids = _ids(sim)
    state = sim.sim.engine.content_hash()
    result = editor.run('edit-write', json.dumps([{'op': 'number', 'id': ids['Kabel Regional'], 'number': 30}]))
    assert not result['ok'], 'a cable number change must not pretend success'
    assert 'SIM_UNSUPPORTED_CHANNEL_ID' in result['error']
    assert sim.sim.engine.content_hash() == state


def test_v064_backups_are_kept_per_tv(editor):
    folders = []
    for serial in ('SIM-LIVINGROOM', 'SIM-KITCHEN'):
        editor.start('mixed_modes', device={'model_name': 'OLED55C27LA', 'serial_number': serial})
        result = editor.run('backup-folders')
        assert result['ok'], _failed(result)
        folders.append(result['folders'])
    assert folders == [['OLED55C27LA-SIM-LIVINGROOM'], ['OLED55C27LA-SIM-KITCHEN']]


def test_v064_reload_lists_restores_lg_channels_list(editor):
    sim = editor.start('mixed_modes')
    ids = _ids(sim)
    result = editor.run('reload-groups', json.dumps({'group': 'D', 'ids': [ids['Stream Kino'], ids['LG 1']]}))
    assert result['ok'], _failed(result)
    assert _list(result['local'], 'D') == ['Stream Kino', 'LG 1']
    assert result['reload']['changed'] == ['D']
    assert _list(result['after'], 'D') == ['LG 1', 'LG 1: Film', 'Stream News']        # TV state, IP from 251
