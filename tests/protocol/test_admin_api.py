"""Admin API (loopback, confirmations, strict validation, token)."""
import json

import pytest
from fastapi.testclient import TestClient

from lg_tv_sim.admin.api import create_app
from tests.helpers import find, live, renumber


@pytest.fixture
def admin(sim):
    return TestClient(create_app(sim)), sim


def test_status_and_banner(admin):
    client, sim = admin
    status = client.get('/api/status').json()
    assert status['simulator'].startswith('SIMULATOR') and status['fixture'] == 'mini'
    assert status['favorites']['A'] == 8
    page = client.get('/').text
    assert 'kein echter LG-TV' not in page and 'class="banner"' not in page   # red banner removed on request
    assert client.get('/static/app.js').status_code == 200
    assert client.get('/static/../api.py').status_code == 404


def test_t40_manipulated_requests_are_rejected_without_mutation(admin):
    client, sim = admin
    state = sim.engine.content_hash()
    assert client.post('/api/reset', json={'confirm': False}).status_code == 400
    assert client.post('/api/reset', json={'confirm': True, 'evil': 1}).status_code == 422
    assert client.post('/api/reset', json={'confirm': True, 'fixture': '../../etc/passwd'}).status_code == 422
    assert client.post('/api/reset', json={'confirm': 'yes'}).status_code == 422
    assert client.post('/api/snapshots/restore', json={'confirm': True, 'snapshot': 'snap-9999'}).status_code == 404
    assert client.post('/api/scenarios/activate', json={'confirm': True, 'scenario': 'nope'}).status_code == 404
    assert sim.engine.content_hash() == state


def test_foreign_host_header_is_refused(admin):
    client, _ = admin
    assert client.get('/api/status', headers={'host': 'evil.example:8766'}).status_code == 403


def test_token_required_when_configured(sim):
    client = TestClient(create_app(sim, token='s3cret'))
    assert client.get('/api/status').status_code == 401
    assert client.get('/api/status', headers={'X-Sim-Token': 's3cret'}).status_code == 200


def test_snapshot_restore_reset_export(admin):
    client, sim = admin
    snap = client.post('/api/snapshots', json={'label': 'base'}).json()['snapshot']
    base = sim.engine.content_hash()
    renumber(sim, find(live(sim), 'QVC HD')['channelId'], 40)
    assert sim.engine.content_hash() != base
    assert client.post('/api/snapshots/restore', json={'confirm': True, 'snapshot': snap}).status_code == 200
    assert sim.engine.content_hash() == base
    renumber(sim, find(live(sim), 'QVC HD')['channelId'], 40)
    result = client.post('/api/reset', json={'confirm': True}).json()
    assert result['state_hash'] == result['fixture_hash']
    trace = client.get('/api/export/trace').text.splitlines()
    assert json.loads(trace[0])['kind'] == 'reset'
    state = client.get('/api/export/state').json()
    assert len(state['channels']) == state['status']['channels']


def test_activate_scenario_and_lists(admin):
    client, sim = admin
    assert 'mini' in client.get('/api/fixtures').json()
    ids = [s['id'] for s in client.get('/api/scenarios').json()]
    assert 'delayed_visibility' in ids
    status = client.post('/api/scenarios/activate', json={'confirm': True, 'scenario': 'delayed_visibility'}).json()
    assert status['scenario'] == 'delayed_visibility' and sim.engine.stale_reads_default == 2
    journal = client.get('/api/journal').json()
    assert journal[-1]['kind'] == 'reset'


def test_logo_and_icons_are_served(admin):
    client, _ = admin
    page = client.get('/').text
    for name, media in (('logo.png', 'image/png'), ('favicon-96x96.png', 'image/png'),
                        ('apple-touch-icon.png', 'image/png')):
        assert f'/static/{name}' in page
        response = client.get(f'/static/{name}')
        assert response.status_code == 200 and response.headers['content-type'] == media
        assert response.content.startswith(b'\x89PNG') and len(response.content) < 100_000
    favicon = client.get('/favicon.ico')
    assert favicon.status_code == 200 and favicon.content[:4] == b'\x00\x00\x01\x00'


def test_assets_are_cache_busted_with_the_version(admin):
    from lg_tv_sim import __version__
    client, _ = admin
    page = client.get('/')
    assert '{{' not in page.text and page.headers['cache-control'] == 'no-store'
    for name in ('app.js', 'style.css', 'logo.png', 'favicon-96x96.png', 'apple-touch-icon.png'):
        assert f'/static/{name}?v={__version__}' in page.text
    assert f'/favicon.ico?v={__version__}' in page.text
    current = client.get(f'/static/app.js?v={__version__}')
    assert 'immutable' in current.headers['cache-control']
    assert client.get('/static/app.js?v=0.0.0-old').headers['cache-control'] == 'no-store'
    assert client.get('/static/app.js').headers['cache-control'] == 'no-store'


def test_admin_lists_lg_channels_read_only(sim_factory):
    sim = sim_factory('real_20261011_1417_ipfav')
    client = TestClient(create_app(sim))
    channels = client.get('/api/channels').json()
    ip = [c for c in channels if c['mode'] == 'IP']
    assert len(ip) == 220 and all(c['read_only'] for c in ip)
    assert not any(c['read_only'] for c in channels if c['mode'] != 'IP')
    assert sorted(c['index']['B'] for c in ip if 'B' in c['groups']) == list(range(251, 266))
    assert all(c['sim_entry_id'] for c in ip)
    status = client.get('/api/status').json()
    assert status['modes'] == {'Cable': 170, 'Satellite': 709}               # tuner only, as before
    assert status['ip'] == {'channels': 220, 'favorites': {'B': 15}}
    assert status['favorites']['B'] == 15                                       # lists count tuner_on and ip
    assert len(sim.channels()) == 879                                           # engine view stays tuner-only


def test_mode_filter_offers_all_reception_modes(admin):
    client, _ = admin
    script = client.get('/static/app.js').text
    for mode, label in (('Satellite', 'Satellit'), ('Cable', 'Kabel'), ('Terrestrial', 'Antenne'),
                        ('IP', 'LG Channels (IP)')):
        assert f"{mode}: '{label}'" in script


def test_token_opens_the_admin_ui_for_any_host(sim):
    """Without a token only localhost Host headers (DNS rebinding); with a token any host, API only with token."""
    closed = TestClient(create_app(sim), base_url='http://omv:8767').get('/')
    assert closed.status_code == 403 and 'LG_TV_SIM_ADMIN_TOKEN' in closed.text
    client = TestClient(create_app(sim, token='s3cret'), base_url='http://omv:8767')
    assert client.get('/').status_code == 200
    assert client.get('/api/status').status_code == 401
    assert client.get('/api/status', headers={'X-Sim-Token': 's3cret'}).status_code == 200
    assert client.post('/api/reset', json={'confirm': True}).status_code == 401
    by_ip = TestClient(create_app(sim, token='s3cret'), base_url='http://192.168.1.10:8767')
    assert by_ip.get('/api/status', headers={'X-Sim-Token': 's3cret'}).status_code == 200
