"""Loopback-only admin API and developer UI.  Uses the same engine/transactions as the SSH path."""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from lg_tv_sim import __version__
from lg_tv_sim.storage.fixtures import FixtureError

if TYPE_CHECKING:
    from lg_tv_sim.app import Simulator

STATIC = Path(__file__).resolve().parent / 'static'
STATIC_FILES = {'app.js', 'style.css', 'logo.png', 'favicon-96x96.png', 'apple-touch-icon.png'}
ALLOWED_HOSTS = {'127.0.0.1', 'localhost', '[::1]', 'testserver'}


def asset_tag() -> str:
    """?v= value: version plus a hash of the static files, so an asset edited within one version is never
    served from a browser cache that holds the old file as immutable."""
    digest = hashlib.sha256()
    for name in sorted(STATIC_FILES | {'favicon.ico'}):
        digest.update(name.encode() + b'\0' + (STATIC / name).read_bytes())
    return f'{__version__}-{digest.hexdigest()[:8]}'


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class ResetRequest(Strict):
    confirm: bool
    fixture: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_.-]{1,64}$')
    scenario: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_.-]{1,64}$')
    force: bool = False


class ScenarioRequest(Strict):
    confirm: bool
    scenario: str = Field(pattern=r'^[A-Za-z0-9_.-]{1,64}$')
    force: bool = False


class SnapshotRequest(Strict):
    label: str = Field(default='', max_length=200)


class RestoreRequest(Strict):
    confirm: bool
    snapshot: str = Field(pattern=r'^snap-\d{4}$')
    force: bool = False


def create_app(sim: Simulator, token: str | None = None) -> FastAPI:
    """Without a token the admin UI answers only localhost Host headers (protection against DNS rebinding).
    With a token it answers any host name (e.g. a NAS in the LAN): every API call then needs X-Sim-Token, which
    a foreign web page never has."""
    app = FastAPI(title='LG TV Simulator – admin', docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def guard(request: Request, call_next):
        host = (request.headers.get('host') or '').rsplit(':', 1)[0].lower()
        if not token and host not in ALLOWED_HOSTS:
            return PlainTextResponse('forbidden host: without LG_TV_SIM_ADMIN_TOKEN the admin UI only answers on '
                                     '127.0.0.1/localhost. Set LG_TV_SIM_ADMIN_TOKEN (e.g. in docker-compose) to '
                                     'open it under any host name; the page then asks for that password.',
                                     status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers.setdefault('Cache-Control', 'no-store')
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'"
        return response

    def authorized(request: Request) -> None:
        if token and not hmac.compare_digest(request.headers.get('x-sim-token', ''), token):
            raise HTTPException(401, 'missing or wrong X-Sim-Token')

    def confirmed(flag: bool) -> None:
        if flag is not True:
            raise HTTPException(400, 'explicit confirmation required (confirm: true)')

    def guarded(action):
        from lg_tv_sim.app import BusyError
        try:
            return action()
        except BusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (KeyError, FixtureError) as exc:
            raise HTTPException(404, str(exc).strip('"\'')) from exc

    api = [Depends(authorized)]

    tag = asset_tag()
    page = (STATIC / 'index.html').read_text(encoding='utf-8').replace('{{asset}}', tag)
    page = page.replace('{{version}}', __version__)

    @app.get('/', include_in_schema=False)
    def index():
        return HTMLResponse(page)

    @app.get('/static/{name}', include_in_schema=False)
    def static(name: str, v: str | None = None):
        if name not in STATIC_FILES:
            raise HTTPException(404)
        # ?v=<version>-<content hash> (cache busting): that exact tag never changes, so browsers may keep it.
        headers = {'Cache-Control': 'public, max-age=31536000, immutable'} if v == tag else None
        return FileResponse(STATIC / name, headers=headers)

    @app.get('/favicon.ico', include_in_schema=False)
    def favicon():
        return FileResponse(STATIC / 'favicon.ico', media_type='image/x-icon')

    @app.get('/api/status', dependencies=api)
    def status():
        return sim.status()

    @app.get('/api/channels', dependencies=api)
    def channels():
        return sim.channels(include_ip=True)

    @app.get('/api/journal', dependencies=api)
    def journal(since: int = 0, limit: int = 500):
        events = sim.journal.events(since)
        return events[-max(1, min(limit, 5000)):]

    @app.get('/api/scenarios', dependencies=api)
    def scenarios():
        # Full rules (match/action without unset fields) so the UI can explain them in plain words.
        return [{'id': s.id, 'description': s.description, 'fixture': s.fixture, 'profile': s.profile,
                 'evidence': s.evidence, 'read_after_write_stale_reads': s.read_after_write_stale_reads,
                 'rules': [{'id': r.id, 'description': r.description, 'times': r.times,
                            'match': r.match.model_dump(mode='json', exclude_none=True),
                            'action': r.action.model_dump(mode='json', exclude_none=True)} for r in s.rules],
                 'expectations': s.expectations} for s in sim.scenarios().values()]

    @app.get('/api/fixtures', dependencies=api)
    def fixtures():
        return sim.catalog.names()

    @app.post('/api/reset', dependencies=api)
    def reset(body: ResetRequest):
        confirmed(body.confirm)
        return guarded(lambda: sim.reset(fixture=body.fixture, scenario=body.scenario, force=body.force,
                                         keep_scenario=body.scenario is None))

    @app.post('/api/scenarios/activate', dependencies=api)
    def activate(body: ScenarioRequest):
        confirmed(body.confirm)
        return guarded(lambda: sim.activate_scenario(body.scenario, reset=True, force=body.force))

    @app.post('/api/snapshots', dependencies=api)
    def snapshot(body: SnapshotRequest):
        return {'snapshot': sim.snapshot(body.label)}

    @app.post('/api/snapshots/restore', dependencies=api)
    def restore(body: RestoreRequest):
        confirmed(body.confirm)
        return guarded(lambda: sim.restore(body.snapshot, force=body.force))

    @app.get('/api/export/state', dependencies=api)
    def export_state():
        state = {'status': sim.status(), 'channels': sim.channels()}
        return JSONResponse(state, headers={'Content-Disposition': f'attachment; filename="state-{sim.run.id}.json"'})

    @app.get('/api/export/trace', dependencies=api)
    def export_trace():
        body = ''.join(json.dumps(e, ensure_ascii=False, sort_keys=True) + '\n' for e in sim.journal.events())
        return PlainTextResponse(body, media_type='application/x-ndjson',
                                 headers={'Content-Disposition': f'attachment; filename="trace-{sim.run.id}.jsonl"'})

    return app
