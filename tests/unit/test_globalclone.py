"""GlobalClone (LG USB export) -> fixture converter.

Evidence: field meanings cross-checked against the real backup (frequency units, radio flag 0x4000, satellite
names) and against public GlobalClone exports; structure that the export does not carry (dvc_chan_id layout
for other satellites, min_no, LCN flag) follows the builder rules (SIMULATOR_ASSUMPTION, G10 in
docs/compatibility-gaps.md).  The test inputs below are invented; no third-party export is committed.
"""
import json
import sqlite3

import pytest

from lg_tv_sim.storage.fixtures import FixtureCatalog, FixtureError
from lg_tv_sim.storage.globalclone import parse_globalclone
from tests.conftest import LIVE_PAYLOAD, REPO
from tests.helpers import call

RADIO = 0x4000


def channel(name, number, source='SATELLITE DIGITAL', **extra):
    base = {'channelName': name, 'majorNumber': number, 'minorNumber': 0, 'sourceIndex': source,
            'physicalNumber': 7, 'frequency': 11766, 'TSID': 1, 'SVCID': 100 + number % RADIO, 'ONID': 318,
            'serviceType': 25, 'deleted': False, 'disabled': False, 'Invisible': False, 'ipChannel': False,
            'scrambled': False, 'validLCN': False, 'satelliteId': '0130'}
    base.update(extra)
    return base


def json_export(path, channels, model='OLED55TEST', country='DEU'):
    data = {'modelInfo': {'country': 'Germany'}, 'channelList': channels,
            'satelliteList': [{'satelliteId': '0130', 'satelliteName': 'EUTELSAT HOTBIRD 13.0E'},
                              {'satelliteId': '0192', 'satelliteName': 'ASTRA 19.2E'}]}
    path.write_text('<?xml version="1.0"?>\n<TLLDATA>\n<ModelInfo>\n'
                    f'<ModelName type="0">{model}</ModelName>\n'
                    f'<BroadcastCountrySetting type="0">{country}</BroadcastCountrySetting>\n'
                    '<CloneVersion type="1"><MajorVersion>200</MajorVersion></CloneVersion>\n</ModelInfo>\n'
                    f'<CHANNEL>\n<legacybroadcast>{json.dumps(data)}</legacybroadcast></CHANNEL></TLLDATA>',
                    encoding='utf-8')
    return path


def xml_item(name, number, source, **extra):
    fields = {'vchName': name, 'prNum': number, 'sourceIndex': source, 'physicalNum': 3, 'frequency': 11054,
              'transport_id': 2, 'service_id': 300 + number % RADIO, 'original_network_id': 1070,
              'serviceType': 1, 'isDeleted': 0, 'isDisabled': 0, 'isInvisable': 0, 'usSatelliteHandle': 2}
    fields.update(extra)
    return '<ITEM>' + ''.join(f'<{k}>{v}</{k}>' for k, v in fields.items()) + '</ITEM>'


def xml_export(path, items, atv_items=()):
    sats = ''.join(f'<idx{i}><Angle type="0">{a}</Angle><AnglePrec type="0">{p}</AnglePrec>'
                   f'<DirEastWest type="0">{d}</DirEastWest></idx{i}>'
                   for i, (a, p, d) in enumerate([(0, 8, 0), (19, 2, 1), (42, 0, 1)]))
    path.write_text('<?xml version="1.0"?>\n<TLLDATA><ModelInfo><ModelName type="0">42LBTEST</ModelName>'
                    '<BroadcastCountrySetting type="0">TUR</BroadcastCountrySetting>'
                    '<CloneVersion type="1"><MajorVersion>100</MajorVersion></CloneVersion></ModelInfo>'
                    f'<SatelliteDB><SATDBInfo><SatRecordInfo>{sats}</SatRecordInfo></SATDBInfo></SatelliteDB>'
                    f'<CHANNEL><ATV>{"".join(atv_items)}</ATV><DTV>{"".join(items)}</DTV></CHANNEL></TLLDATA>',
                    encoding='utf-8')
    return path


def by_name(conversion, name):
    [found] = [c for c in conversion.channels if c['name'] == name]
    return found


def test_json_export_modes_numbers_satellites_and_skips(tmp_path):
    source = json_export(tmp_path / 'GlobalClone00001.TLL', [
        channel('Hotbird Eins', 1, physicalNumber=9, frequency=11766),
        channel('Hotbird Radio', RADIO + 5, serviceType=2),
        channel('Astra Info', 2, satelliteId='0192', ONID=1, TSID=1019, frequency=11494),
        channel('Kabel Eins', 1, 'CABLE DIGITAL', frequency=346000, ONID=133, TSID=5, satelliteId=None,
                serviceType=1),
        channel('Antenne Eins', 1, 'ANTENNA DIGITAL', frequency=474000, ONID=8468, TSID=12289, satelliteId=None),
        channel('Geloescht', 3, deleted=True),
        channel('LG Stream', 4, ipChannel=True),
        channel('Analog', 5, 'CABLE ANALOG', satelliteId=None),
        channel('Hotbird Eins', 1, physicalNumber=9, frequency=11766),          # duplicate entry
    ])
    conversion = parse_globalclone(source)
    assert conversion.meta['model'] == 'OLED55TEST' and conversion.meta['format'] == 'json'
    assert conversion.meta['country'] == 'DEU'
    sat = by_name(conversion, 'Hotbird Eins')
    assert sat == {'name': 'Hotbird Eins', 'mode': 'Satellite', 'number': 1, 'phy': 9, 'tsid': 1, 'sid': 101,
                   'onid': 318, 'frequency': 11766, 'satellite': 'EUTELSAT HOTBIRD 13.0E', 'svc_type': 25}
    radio = by_name(conversion, 'Hotbird Radio')
    assert radio['number'] == 5 and radio['radio'] is True and radio['svc_type'] == 2
    assert by_name(conversion, 'Astra Info')['satellite'] == 'ASTRA 19.2E'
    cable = by_name(conversion, 'Kabel Eins')
    assert cable['mode'] == 'Cable' and cable['frequency'] == 346000 and cable['satellite'] == ' '
    assert by_name(conversion, 'Antenne Eins')['mode'] == 'Terrestrial'
    report = conversion.report
    assert report['converted'] == 5 and report['by_mode'] == {'Satellite': 3, 'Cable': 1, 'Terrestrial': 1}
    assert report['skipped'] == {'deleted': 1, 'ip': 1, 'analog': 1, 'duplicate_id': 1}
    assert report['satellites'] == {'EUTELSAT HOTBIRD 13.0E': 2, 'ASTRA 19.2E': 1}


def test_invisible_entries_are_kept_and_counted_unless_ignored(tmp_path):
    source = json_export(tmp_path / 'a.TLL', [channel('Sichtbar', 1), channel('Versteckt', 2, Invisible=True)])
    conversion = parse_globalclone(source)
    assert by_name(conversion, 'Versteckt')['invisible'] == 1 and 'invisible' not in by_name(conversion, 'Sichtbar')
    assert conversion.report['invisible'] == 1
    ignored = parse_globalclone(source, ignore_invisible=True)
    assert 'invisible' not in by_name(ignored, 'Versteckt') and ignored.report['invisible_ignored'] == 1


def test_unknown_source_and_truncated_export_fail_closed(tmp_path):
    source = json_export(tmp_path / 'a.TLL', [channel('X', 1, 'SATELLITE MYSTERY')])
    with pytest.raises(FixtureError, match="unknown sourceIndex 'SATELLITE MYSTERY'"):
        parse_globalclone(source)
    broken = tmp_path / 'b.TLL'
    broken.write_bytes(b'<TLLDATA><CHANNEL><legacybroadcast>{"channelList": [{"channelName": "A"' + b'\x9c\x00\xff' * 50)
    with pytest.raises(FixtureError, match='JSON in <legacybroadcast> is incomplete'):
        parse_globalclone(broken)
    (tmp_path / 'c.TLL').write_text('<TLLDATA><CHANNEL></CHANNEL></TLLDATA>')
    with pytest.raises(FixtureError, match='no channel list'):
        parse_globalclone(tmp_path / 'c.TLL')


def test_old_xml_format_positions_from_satellite_db_and_mode_map(tmp_path):
    items = [xml_item('Turk Bir', 1, 7), xml_item('Turk Radyo', RADIO + 2, 7, serviceType=2),
             xml_item('Anten Bir', 1, 1, frequency=474000, original_network_id=8232, usSatelliteHandle=0),
             xml_item('Kablo Bir', 4, 3, frequency=346000, original_network_id=1537, usSatelliteHandle=0),
             xml_item('Silindi', 5, 7, isDeleted=1)]
    source = xml_export(tmp_path / 'tv.tll', items, atv_items=[xml_item('S 02', 1, 2)])
    with pytest.raises(FixtureError, match="sourceIndex 3 has no evidenced mode.*mode_map"):
        parse_globalclone(source)
    conversion = parse_globalclone(source, mode_map={'3': 'Cable'})
    assert conversion.meta['format'] == 'xml' and conversion.meta['model'] == '42LBTEST'
    assert by_name(conversion, 'Turk Bir')['satellite'] == 'TURKSAT 42.0E'
    assert by_name(conversion, 'Turk Radyo')['number'] == 2 and by_name(conversion, 'Turk Radyo')['radio'] is True
    assert by_name(conversion, 'Anten Bir')['mode'] == 'Terrestrial'
    assert by_name(conversion, 'Kablo Bir')['mode'] == 'Cable'
    assert conversion.report['skipped'] == {'deleted': 1, 'analog': 1}
    assert conversion.report['mode_map'] == {'3': 'Cable'}


def test_satellite_override_for_mislabelled_exports(tmp_path):
    source = xml_export(tmp_path / 'tv.tll', [xml_item('Sky One', 106, 7, original_network_id=2,
                                                        usSatelliteHandle=1)])
    assert by_name(parse_globalclone(source), 'Sky One')['satellite'] == 'ASTRA 19.2E'
    fixed = parse_globalclone(source, satellite='ASTRA 28.2E')
    assert by_name(fixed, 'Sky One')['satellite'] == 'ASTRA 28.2E'
    assert fixed.report['satellite_override'] == 'ASTRA 28.2E'


def test_import_globalclone_runs_in_the_simulator(sim_factory, tmp_path):
    source = json_export(tmp_path / 'GlobalClone00001.TLL', [
        channel('Hotbird Eins', 1), channel('Hotbird Radio', RADIO + 5, serviceType=2),
        channel('Kabel Eins', 1, 'CABLE DIGITAL', frequency=346000, ONID=133, TSID=5, satelliteId=None,
                serviceType=1),
        channel('Antenne Eins', 1, 'ANTENNA DIGITAL', frequency=474000, ONID=8468, TSID=12289,
                satelliteId=None)])
    sim = sim_factory('mini')
    sim.catalog.private_dir = tmp_path / 'private'
    meta = sim.catalog.import_globalclone(source, 'gc_test', origin='https://example.invalid/issue/1')
    assert meta['format'] == 'json' and meta['model'] == 'OLED55TEST' and meta['origin'].endswith('/issue/1')
    assert meta['report']['converted'] == 4 and 'SIMULATOR_ASSUMPTION' in meta['evidence']
    assert (tmp_path / 'private' / 'gc_test.sqlite').is_file()
    sim.reset(fixture='gc_test')
    sat = call(sim, 'getChannelList', {**LIVE_PAYLOAD, 'channelMode': 'Satellite'})['channelList']
    assert {c['channelName'] for c in sat} == {'Hotbird Eins', 'Hotbird Radio'}
    assert {c['satelliteName'] for c in sat} == {'EUTELSAT HOTBIRD 13.0E'}
    tuner = call(sim, 'getChannelList', {**LIVE_PAYLOAD, 'channelMode': 'Tuner'})['channelList']
    assert {c['channelMode'] for c in tuner} == {'Satellite', 'Cable', 'Terrestrial'}
    with sqlite3.connect(f'file:{sim.run.db_path}?mode=ro', uri=True) as conn:
        rows = dict(conn.execute('SELECT chan_std_name, svc_type FROM tuner_on').fetchall())
    assert rows == {'Hotbird Eins': 25, 'Hotbird Radio': 2, 'Kabel Eins': 1, 'Antenne Eins': 25}
    with pytest.raises(FixtureError, match='already exists'):
        sim.catalog.import_globalclone(source, 'gc_test')


def test_public_globalclone_import_refuses_personal_data(tmp_path):
    source = json_export(tmp_path / 'GlobalClone00001.TLL', [channel('Kontakt max@example.org', 1)])
    catalog = FixtureCatalog(REPO / 'fixtures' / 'synthetic', tmp_path / 'private', tmp_path / 'recorded')
    with pytest.raises(FixtureError, match='possible personal data'):
        catalog.import_globalclone(source, 'gc_public', public=True, origin='https://example.invalid/1')
    assert not list((tmp_path / 'recorded').glob('gc_public*'))
    with pytest.raises(FixtureError, match='origin'):
        catalog.import_globalclone(json_export(tmp_path / 'ok.TLL', [channel('Eins', 1)]), 'gc_public',
                                   public=True)


def test_cli_import_globalclone(tmp_path, monkeypatch, capsys):
    from lg_tv_sim.cli import main
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config' / 'local.toml').write_text(
        f'[storage]\nfixtures_dir = "{REPO / "fixtures" / "synthetic"}"\n'
        f'scenarios_dir = "{REPO / "fixtures" / "scenarios"}"\n')
    source = xml_export(tmp_path / 'tv.tll', [xml_item('Turk Bir', 1, 7),
                                               xml_item('Kablo Bir', 4, 3, usSatelliteHandle=0)])
    assert main(['import-globalclone', str(source), '--name', 'gc_cli']) == 1
    assert 'mode_map' in capsys.readouterr().err
    assert main(['import-globalclone', str(source), '--name', 'gc_cli', '--mode-map', '3=Cable',
                 '--satellite', 'TURKSAT 42.0E']) == 0
    meta = json.loads(capsys.readouterr().out)
    assert meta['report']['by_mode'] == {'Satellite': 1, 'Cable': 1} and meta['report']['mode_map'] == {'3': 'Cable'}
    assert (tmp_path / '.simulator' / 'fixtures' / 'gc_cli.sqlite').is_file()
    assert main(['import-globalclone', str(source), '--name', 'gc_cli2', '--mode-map', '3']) == 1
    assert 'CODE=MODE' in capsys.readouterr().err


@pytest.mark.parametrize('name', sorted(p.stem for p in (REPO / 'fixtures' / 'recorded').glob('gc_*.sqlite')))
def test_committed_globalclone_fixtures_load_and_show_channels(sim_factory, name):
    meta = json.loads((REPO / 'fixtures' / 'recorded' / f'{name}.json').read_text(encoding='utf-8'))
    sim = sim_factory(name)
    with sqlite3.connect(f'file:{sim.run.db_path}?mode=ro', uri=True) as conn:
        assert conn.execute('SELECT count(*) FROM tuner_on').fetchone()[0] == meta['report']['converted']
    rows = call(sim, 'getChannelList', {**LIVE_PAYLOAD, 'channelMode': 'Tuner'})['channelList']
    assert rows and {r['channelMode'] for r in rows} == set(meta['report']['by_mode'])
    satellites = {r['satelliteName'] for r in rows if r['channelMode'] == 'Satellite'}
    assert satellites <= set(meta['report']['satellites'])
