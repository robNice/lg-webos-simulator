"""Drives the REAL LG WebOS Channel Editor code (not a re-implementation) against the simulator.

Runs under the editor's own interpreter (system python3 + its paramiko) inside a
temporary COPY of the editor checkout; the editor's own data/ is never touched.
Host keys come from ``$HOME/.ssh/known_hosts`` exactly as in production
(``load_system_host_keys`` + ``RejectPolicy``); HOME points to a test directory.

Usage: python3 editor_driver.py <editor_copy> <data_dir> <port> <action> [args...]
Password: environment variable SIM_PASSWORD.  Prints one JSON document.
"""
import json
import os
import sqlite3
import sys
import traceback


def summary(app):
    with sqlite3.connect(str(app.DB)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute('SELECT dvc_chan_id, chan_std_name, chan_no_int, chan_mode_name, '
                            + ','.join(f'fav_chan_gr_{g.lower()}, favoriteIdx{g}' for g in 'ABCDEFGH')
                            + ' FROM tuner_on ORDER BY chan_mode_name, chan_no_int, dvc_chan_id').fetchall()
        names = dict(conn.execute('SELECT channel_group_id, user_edited_name FROM channel_group_tuner').fetchall())
    channels = []
    for r in rows:
        groups = {g: int(r[f'favoriteIdx{g}']) for g in 'ABCDEFGH'
                  if str(r[f'fav_chan_gr_{g.lower()}'] or '') in ('1', 'true')}
        channels.append({'id': r['dvc_chan_id'], 'name': r['chan_std_name'], 'number': r['chan_no_int'],
                         'mode': r['chan_mode_name'], 'groups': groups})
    return {'channels': channels, 'group_names': {str(k): v for k, v in names.items()}}


def error_keys(exc):
    from i18n import Joined, LocalizedError, Message

    def walk(value):
        if isinstance(value, LocalizedError):
            yield from walk(value.message)
        elif isinstance(value, Message):
            yield value.key
            for param in value.params.values():
                yield from walk(param)
        elif isinstance(value, Joined):
            for part in value.parts:
                yield from walk(part)
    return list(walk(exc))


def main():
    editor, data, port, action, *rest = sys.argv[1:]
    sys.path.insert(0, editor)
    os.chdir(editor)
    from pathlib import Path

    import app
    app.DATA = Path(data)
    app.DB = app.DATA / 'working.sqlite'
    app.DATA.mkdir(parents=True, exist_ok=True)
    host, password, port = '127.0.0.1', os.environ['SIM_PASSWORD'], int(port)
    result = {'action': action}
    try:
        if action == 'login':
            from tv_login import TvLoginCheck
            check = TvLoginCheck(lambda h, p, po, trust=None: app.connect_tv(h, p, po, trust))
            result['login'] = check.check(host, password, port)
        elif action == 'import':
            app.import_from_tv(host, password, port)
            result['state'] = summary(app)
        elif action == 'renumber-write':
            group, start = rest[0], int(rest[1])
            app.import_from_tv(host, password, port)
            result['before'] = summary(app)
            with app.connection() as conn:
                with conn:
                    plan = app.renumber_plan(conn, group, start)
                    app.apply_renumber(conn, plan)
            result['renumber_plan'] = {'changes': plan['changes'], 'merged': plan['mergedFavorites']}
            preview = app.prepare_tv_write(host, password, port)
            result['preview'] = [{k: v for k, v in op.items() if k != 'warning'} for op in preview['operations']]
            commit = app.commit_tv_write(host, password, port, preview['token'])
            result['results'] = commit['operations']
            app.import_from_tv(host, password, port)
            result['after'] = summary(app)
        elif action == 'set-favorites-write':
            # rest: JSON {"group": "A", "ids": [...]} – replaces the local list, then transfers it
            spec = json.loads(rest[0])
            app.import_from_tv(host, password, port)
            with app.connection() as conn:
                with conn:
                    app.replace_group_members(conn, spec['group'], spec['ids'])
                    if spec.get('rename'):
                        app.rename_group(conn, spec['group'], spec['rename'])
            preview = app.prepare_tv_write(host, password, port)
            result['preview'] = [{k: v for k, v in op.items() if k != 'warning'} for op in preview['operations']]
            commit = app.commit_tv_write(host, password, port, preview['token'])
            result['results'] = commit['operations']
            app.import_from_tv(host, password, port)
            result['after'] = summary(app)
        else:
            raise SystemExit(f'unknown action {action}')
        result['ok'] = True
    except Exception as exc:  # report everything to the test as data
        result.update({'ok': False, 'error_type': type(exc).__name__, 'error': str(exc)[:4000],
                       'error_keys': error_keys(exc), 'traceback': traceback.format_exc()[-4000:]})
        try:
            result['state_after_error'] = summary(app)
        except Exception:
            pass
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
