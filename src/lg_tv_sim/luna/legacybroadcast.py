"""``com.webos.service.legacybroadcast.channel`` – historically used by the editor (<= v0.5.x).

Since v0.6.0 the editor renumbers through iepg; these methods stay available
for older clients and behave identically (HARDWARE_CONFIRMED per tv_write.py:
"same move/swap results and IDs").  ``copyDvbSatelliteChannelForAstra`` exists
in the firmware but must never be used automatically: it fails closed.
"""
from __future__ import annotations

from lg_tv_sim.domain.models import UnsupportedOperation
from lg_tv_sim.luna import iepg

SERVICE = 'com.webos.service.legacybroadcast.channel'


def copy_dvb_satellite_channel_for_astra(*_, **__):
    raise UnsupportedOperation('copyDvbSatelliteChannelForAstra is deliberately not simulated')


HANDLERS = {
    'getChannel': iepg.get_channel,
    'changeChannelNumber': iepg.change_channel_number,
    'copyDvbSatelliteChannelForAstra': copy_dvb_satellite_channel_for_astra,
}
