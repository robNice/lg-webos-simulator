"""Real SSH/SFTP protocol tests with a paramiko client configured like the editor."""
import sqlite3
import threading

import paramiko
import pytest

from tests.conftest import LIVE_PAYLOAD, TV_DB, exec_command, luna

LOGIN = 'command -v sqlite3 >/dev/null && command -v luna-send >/dev/null'


def test_t01_login_with_simulator_credentials_and_host_key(running):
    sim = running()
    client = sim.client()
    assert exec_command(client, LOGIN)[0] == 0
    key = client.get_transport().get_remote_server_key()
    assert key.get_name() == 'ssh-ed25519'
    client.close()


def test_t01_unknown_host_key_is_rejected(running, tmp_path):
    sim = running()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    with pytest.raises(paramiko.SSHException):
        client.connect('127.0.0.1', port=sim.port, username='root', password='x', look_for_keys=False,
                       allow_agent=False, timeout=5)


def test_t02_wrong_password(running):
    sim = running()
    with pytest.raises(paramiko.AuthenticationException):
        sim.client(password='wrong')
    assert any(e['kind'] == 'auth' and not e['accepted'] for e in sim.sim.journal.events())


def test_t03_unsupported_and_injected_commands(running, tmp_path):
    sim = running()
    client = sim.client()
    marker = tmp_path / 'pwned'
    for command in ('id', 'ls /', f'touch {marker}', f'rm -f /tmp/x; touch {marker}', f'sh -c "touch {marker}"',
                    f'luna-send -n 1 luna://com.webos.service.iepg/getChannelList \'{{}}\' && touch {marker}',
                    f"sqlite3 -readonly {TV_DB} '.shell touch {marker}'", f'sqlite3 {TV_DB} "DELETE FROM tuner_on"',
                    f'rm -f {marker}', 'rm -rf /tmp/x'):
        status, out, err = exec_command(client, command)
        assert status == 127 and 'SIMULATOR' in err, command
    assert not marker.exists()
    # interactive shell request
    channel = client.get_transport().open_session()
    channel.invoke_shell()
    assert channel.recv_exit_status() == 126
    client.close()


def test_t04_sftp_sandbox(running):
    sim = running()
    client = sim.client()
    exec_command(client, f"sqlite3 -readonly {TV_DB} '.backup /tmp/ok.sqlite'")
    with client.open_sftp() as sftp:
        for path in ('/etc/passwd', '/tmp/../etc/passwd', TV_DB, '/tmp/missing.sqlite'):
            with pytest.raises(OSError):
                sftp.stat(path)
        with pytest.raises(OSError):
            sftp.open('/tmp/ok.sqlite', 'wb')
        with pytest.raises(OSError):
            sftp.remove('/tmp/ok.sqlite')
        with pytest.raises(OSError):
            sftp.listdir('/tmp')
        with pytest.raises(OSError):
            sftp.put(__file__, '/tmp/upload.py')
    assert (sim.sim.run.tmp_dir / 'ok.sqlite').exists()
    client.close()


def test_t05_backup_download_is_consistent(running, tmp_path):
    sim = running()
    client = sim.client()
    assert exec_command(client, f"sqlite3 -readonly {TV_DB} '.backup /tmp/lg-favoriten-1.sqlite'")[0] == 0
    local = tmp_path / 'tv.sqlite'
    with client.open_sftp() as sftp:
        size = sftp.stat('/tmp/lg-favoriten-1.sqlite').st_size
        sftp.get('/tmp/lg-favoriten-1.sqlite', str(local))
    assert local.stat().st_size == size
    with sqlite3.connect(local) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert conn.execute('SELECT COUNT(*) FROM tuner_on').fetchone()[0] == len(sim.sim.channels())
    assert exec_command(client, 'rm -f /tmp/lg-favoriten-1.sqlite')[0] == 0
    assert not (sim.sim.run.tmp_dir / 'lg-favoriten-1.sqlite').exists()
    client.close()


def test_t06_sftp_abort_leaves_fixture_intact(running, tmp_path):
    sim = running(scenario='sftp_abort')
    state = sim.sim.engine.content_hash()
    client = sim.client()
    exec_command(client, f"sqlite3 -readonly {TV_DB} '.backup /tmp/a.sqlite'")
    with pytest.raises((OSError, EOFError, paramiko.SSHException)):
        with client.open_sftp() as sftp:
            sftp.get('/tmp/a.sqlite', str(tmp_path / 'partial.sqlite'))
    assert sim.sim.engine.content_hash() == state
    assert any(e.get('effect') == 'SFTP_ABORT' for e in sim.sim.journal.events())


def test_group_name_select_like_editor(running):
    sim = running()
    client = sim.client()
    luna(client, 'setGroupName', {'channelMode': 'TUNER', 'channelGroupId': 201, 'channelGroupName': "Kids' TV"})
    query = 'SELECT user_edited_name FROM channel_group_tuner WHERE channel_group_id=201'
    status, out, _ = exec_command(client, f'sqlite3 -readonly {TV_DB} "{query}"')
    assert status == 0 and out == "Kids' TV\n"
    status, _, err = exec_command(client, f'sqlite3 -readonly {TV_DB} "SELECT nope FROM tuner_on"')
    assert status == 1 and err.startswith('Error:')
    client.close()


def test_luna_over_ssh_and_backup_failure_fault(running):
    sim = running(scenario='backup_locked')
    client = sim.client()
    status, _, err = exec_command(client, f"sqlite3 -readonly {TV_DB} '.backup /tmp/b.sqlite'")
    assert status == 1 and 'locked' in err
    assert exec_command(client, f"sqlite3 -readonly {TV_DB} '.backup /tmp/b.sqlite'")[0] == 0
    assert len(luna(client, 'getChannelList', LIVE_PAYLOAD)['channelList']) == 17
    status, _, err = exec_command(client, "luna-send -n 1 luna://com.webos.service.iepg/getChannelList '{bad'")
    assert status == 1
    client.close()


def test_t32_disconnect_after_write_over_ssh(running):
    sim = running(scenario='timeout_after_mutation')
    client = sim.client()
    qvc = [c for c in sim.sim.channels() if c['name'] == 'QVC HD'][0]
    _, out, _ = client.exec_command('luna-send -n 1 luna://com.webos.service.iepg/changeChannelNumber '
                                    f'\'{{"channelId":"{qvc["channel_id"]}","channelNumber":40}}\'', timeout=10)
    assert out.read() == b''
    assert out.channel.recv_exit_status() == -1          # no exit status: write status uncertain
    assert [c for c in sim.sim.channels() if c['name'] == 'QVC HD'][0]['number'] == 40


def test_client_timeout_on_slow_answer(running):
    sim = running(scenario='slow_write_answer')
    client = sim.client()
    qvc = [c for c in sim.sim.channels() if c['name'] == 'QVC HD'][0]
    _, out, _ = client.exec_command('luna-send -n 1 luna://com.webos.service.iepg/changeChannelNumber '
                                    f'\'{{"channelId":"{qvc["channel_id"]}","channelNumber":40}}\'', timeout=0.5)
    with pytest.raises(TimeoutError):
        out.read()
    assert [c for c in sim.sim.channels() if c['name'] == 'QVC HD'][0]['number'] == 40


def test_t41_concurrent_sessions_serialize_writes(running):
    sim = running('synthetic_favorites_47')
    names = [f'Regional {n}' for n in range(61, 71)]
    errors = []

    def worker(index):
        try:
            client = sim.client()
            for _ in range(3):
                channels = luna(client, 'getChannelList', LIVE_PAYLOAD)['channelList']
                me = [c for c in channels if c['channelName'] == names[index]][0]
                target = 96 + index % 4 if me['channelNumber'] != str(96 + index % 4) else 61 + index
                luna(client, 'changeChannelNumber', {'channelId': me['channelId'], 'channelNumber': target})
            client.close()
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(names))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert not errors
    assert not sim.sim.engine.invariant_violations()
    numbers = [c['number'] for c in sim.sim.channels() if c['mode'] == 'Satellite' and c['number'] <= 99]
    assert len(numbers) == len(set(numbers))


def test_t42_backups_during_mutations_are_consistent(running, tmp_path):
    sim = running('synthetic_favorites_47')
    stop = threading.Event()

    def mutate():
        client = sim.client()
        while not stop.is_set():
            channels = luna(client, 'getChannelList', LIVE_PAYLOAD)['channelList']
            a = [c for c in channels if c['channelName'] == 'Regional 61'][0]
            luna(client, 'changeChannelNumber', {'channelId': a['channelId'],
                                                 'channelNumber': 62 if a['channelNumber'] == '61' else 61})
        client.close()

    thread = threading.Thread(target=mutate)
    thread.start()
    try:
        client = sim.client()
        for i in range(8):
            assert exec_command(client, f"sqlite3 -readonly {TV_DB} '.backup /tmp/c{i}.sqlite'")[0] == 0
            local = tmp_path / f'c{i}.sqlite'
            with client.open_sftp() as sftp:
                sftp.get(f'/tmp/c{i}.sqlite', str(local))
            with sqlite3.connect(local) as conn:
                assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
                numbers = sorted(r[0] for r in conn.execute(
                    "SELECT chan_no_int FROM tuner_on WHERE chan_std_name IN ('Regional 61','Regional 62')"))
                assert numbers == [61, 62]
        client.close()
    finally:
        stop.set()
        thread.join(30)


def test_reset_refused_while_writer_connected(running):
    from lg_tv_sim.app import BusyError
    sim = running()
    client = sim.client()
    qvc = [c for c in sim.sim.channels() if c['name'] == 'QVC HD'][0]
    luna(client, 'changeChannelNumber', {'channelId': qvc['channel_id'], 'channelNumber': 40})
    with pytest.raises(BusyError):
        sim.sim.reset()
    sim.sim.reset(force=True)
    client.close()


def test_busy_admin_port_fails_cleanly_before_ssh_starts(tmp_path, monkeypatch, capsys):
    """Regression 2026-10-11: port 8766 taken (e.g. editor browser-test server) gave a traceback."""
    import socket

    from lg_tv_sim.cli import main
    from tests.conftest import REPO, free_port
    blocker = socket.socket()
    blocker.bind(('127.0.0.1', 0))
    blocker.listen(1)
    busy, ssh_port = blocker.getsockname()[1], free_port()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('LG_TV_SIM_PASSWORD', 'x')
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config' / 'local.toml').write_text(
        f'[storage]\nfixtures_dir = "{REPO / "fixtures" / "synthetic"}"\ninitial_fixture = "mini"\n')
    try:
        assert main(['serve', '--admin-port', str(busy), '--ssh-port', str(ssh_port)]) == 1
    finally:
        blocker.close()
    captured = capsys.readouterr()
    assert f'admin port 127.0.0.1:{busy} is not available' in captured.err and '--admin-port' in captured.err
    assert 'Traceback' not in captured.err and 'SIMULATOR – kein echter' not in captured.out
    with socket.socket() as probe:          # SSH was never started, port still free
        probe.bind(('127.0.0.1', ssh_port))
