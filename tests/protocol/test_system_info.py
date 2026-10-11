"""TV identity for editor v0.6.4 (tv_identity.TvIdentity): one read-only luna-send -f getSystemInfo call.

The serial number is always a recognisable simulator value, so the editor never files simulator backups
under the real TV's folder (model + serial)."""
import json

import pytest

from lg_tv_sim.config import ConfigError, SimulatorConfig

COMMAND = ("luna-send -n 1 -f luna://com.webos.service.tv.systemproperty/getSystemInfo "
           "'{\"keys\":[\"modelName\",\"serialNumber\"]}'")


def run(sim, command):
    return sim.router.execute(command, 'test')


def test_editor_identity_command(sim_factory):
    sim = sim_factory()
    result = run(sim, COMMAND)
    assert result.exit_status == 0
    text = result.stdout.decode()
    assert text.count('\n') > 1                                   # -f: formatted output
    info = json.loads(text)
    assert info == {'modelName': 'OLED55C27LA', 'serialNumber': 'SIM-000000000001', 'returnValue': True}
    event = sim.journal.events()[-1]
    assert event['method'] == 'getSystemInfo' and not event.get('mutations')


def test_device_identity_is_configurable(sim_factory):
    sim = sim_factory()
    sim.dispatcher.device = SimulatorConfig().with_overrides(
        device={'model_name': 'OLED65G29LA', 'serial_number': 'SIM-LIVINGROOM'}).device
    info = json.loads(run(sim, COMMAND).stdout)
    assert (info['modelName'], info['serialNumber']) == ('OLED65G29LA', 'SIM-LIVINGROOM')


@pytest.mark.parametrize('payload', ['{"keys":["modelName","firmwareVersion"]}', '{"keys":[]}',
                                     '{"keys":["modelName"],"subscribe":true}', '{}'])
def test_unknown_keys_and_parameters_fail_closed(sim_factory, payload):
    sim = sim_factory()
    info = json.loads(run(sim, f"luna-send -n 1 -f luna://com.webos.service.tv.systemproperty/getSystemInfo "
                               f"'{payload}'").stdout)
    assert info['returnValue'] is False


def test_unformatted_call_works_too(sim_factory):
    result = run(sim_factory(), COMMAND.replace(' -f ', ' '))
    assert result.stdout.decode().count('\n') == 1 and json.loads(result.stdout)['returnValue'] is True


@pytest.mark.parametrize('serial', ['', '0123ABCD', '602KXYZ1234', 'sim-1'])
def test_serial_must_be_a_simulator_value(serial):
    with pytest.raises(ConfigError, match='SIM-'):
        SimulatorConfig().with_overrides(device={'serial_number': serial})
