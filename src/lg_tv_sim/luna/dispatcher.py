"""Routes ``luna://service/method`` calls to handlers, applies faults and journals everything.

Client-visible response, real mutations and injected faults are recorded
separately: ``returnValue`` is never treated as proof of a state change.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from lg_tv_sim.config import DeviceConfig
from lg_tv_sim.domain.engine import EngineResult, TvEngine
from lg_tv_sim.domain.models import GROUPS, InvariantViolation, LunaError
from lg_tv_sim.faults.engine import AppliedFault, CallInfo, FaultEngine
from lg_tv_sim.luna import iepg, legacybroadcast, systemproperty
from lg_tv_sim.traces.recorder import Journal

REGISTRY = {iepg.SERVICE: iepg.HANDLERS, legacybroadcast.SERVICE: legacybroadcast.HANDLERS,
            systemproperty.SERVICE: systemproperty.HANDLERS}


@dataclass
class LunaOutcome:
    response: dict | None
    disconnect: bool = False
    hang_ms: int = 0
    exit_status: int = 0
    stderr: str = ''
    mutated: bool = False


class LunaDispatcher:
    def __init__(self, engine: TvEngine, faults: FaultEngine, journal: Journal, device: DeviceConfig | None = None):
        self.engine, self.faults, self.journal = engine, faults, journal
        self.device = device if device is not None else DeviceConfig()

    def call_info(self, service: str, method: str, params: dict) -> CallInfo:
        ids: list[str] = []
        groups: list[str] = []
        target = None
        if isinstance(params, dict):
            for name in ('channelId', 'destinationChannelId'):
                value = params.get(name)
                ids += [v for v in (value if isinstance(value, list) else [value]) if isinstance(v, str)]
            fav = params.get('favoriteGroup')
            groups += [g for g in (fav if isinstance(fav, list) else []) if isinstance(g, str)]
            gid = params.get('favoriteGroupId')
            if type(gid) is int and 0 <= gid < len(GROUPS):
                groups.append(GROUPS[gid])
            if type(params.get('channelNumber')) is int:
                target = params['channelNumber']
        tags = sorted({t for cid in ids for record in self.engine.identity.records.values()
                       if record.channel_id == cid for t in record.tags})
        return CallInfo('luna', service, method, tuple(ids), tuple(tags), target, tuple(groups))

    def call(self, service: str, method: str, params: dict, connection: str = '') -> LunaOutcome:
        fault: AppliedFault | None = self.faults.select(self.call_info(service, method, params))
        action = fault.action if fault else None
        event = {'command': 'luna-send', 'service': service, 'method': method, 'params': params,
                 'connection': connection, 'fault': fault.rule_id if fault else None}
        if action and action.disconnect == 'before':
            self.journal.record('luna', **event, response=None, effect='DISCONNECT_BEFORE_MUTATION', mutations=[])
            return LunaOutcome(None, disconnect=True, hang_ms=action.hang_ms)
        handler = REGISTRY.get(service, {}).get(method)
        result = EngineResult()
        if handler is None:
            known = service in REGISTRY
            text = (f'Unknown method "{method}" for category "/"' if known else f'Service does not exist: {service}.')
            response = {'returnValue': False, 'errorCode': -1, 'errorText': text}
            result.effect = 'UNSUPPORTED'
        else:
            try:
                result = handler(self.engine, params, fault=fault, device=self.device)
                response = result.value
            except LunaError as exc:
                response = exc.response()
                result.effect = 'REJECTED'
            except InvariantViolation as exc:
                response = {'returnValue': False, 'errorCode': 'SIM_INVARIANT_VIOLATION', 'errorText': str(exc)}
                result.effect = 'INVARIANT_VIOLATION'
        client_response = response
        if action and action.response is not None:
            client_response = action.response if action.response_mode == 'replace' else {**response, **action.response}
        self.journal.record(
            'luna', **event, response=client_response,
            true_response=response if client_response is not response else None,
            effect=str(result.effect) if result.effect else None, rule=result.rule,
            mutations=[asdict(m) for m in result.mutations],
            suppressed_mutations=[asdict(m) for m in result.suppressed],
            stale=self.engine.stale_status())
        if action and action.disconnect == 'after':
            return LunaOutcome(None, disconnect=True, hang_ms=action.hang_ms, mutated=bool(result.mutations))
        return LunaOutcome(mutated=bool(result.mutations), response=client_response, hang_ms=action.hang_ms if action else 0,
                           exit_status=action.exit_status if action and action.exit_status is not None else 0,
                           stderr=action.stderr or '' if action else '')
