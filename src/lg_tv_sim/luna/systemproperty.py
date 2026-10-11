"""``com.webos.service.tv.systemproperty`` – only what the editor (v0.6.4, tv_identity.py) reads.

``getSystemInfo`` with ``keys`` modelName/serialNumber.  Request form: CURRENT_CLIENT_CONFIRMED; the answer
layout (keys at top level plus returnValue) is what the editor parses (SIMULATOR_ASSUMPTION for the TV).
The serial number is always a simulator value (config ``[device]``), never a real one.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from lg_tv_sim.domain.engine import EngineResult
from lg_tv_sim.domain.models import UnsupportedOperation
from lg_tv_sim.luna.iepg import Params

if TYPE_CHECKING:
    from lg_tv_sim.config import DeviceConfig
    from lg_tv_sim.domain.engine import TvEngine

SERVICE = 'com.webos.service.tv.systemproperty'


def get_system_info(engine: TvEngine, params: dict, device: DeviceConfig, **_) -> EngineResult:
    keys = Params(params, {'keys'}).string_list('keys')
    values = {'modelName': device.model_name, 'serialNumber': device.serial_number}
    unknown = [k for k in keys if k not in values]
    if not keys or unknown:
        raise UnsupportedOperation(f'getSystemInfo keys {unknown or keys!r} are not simulated '
                                   '(only modelName, serialNumber)')
    return EngineResult(value={**{k: values[k] for k in keys}, 'returnValue': True}, effect='READ')


HANDLERS = {'getSystemInfo': get_system_info}
