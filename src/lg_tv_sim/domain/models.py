"""Domain value objects.

Two identity levels are kept strictly apart (spec §6):

* ``DvbKey`` – the broadcast service (ONID/TSID/SID).  Several LG list entries
  can share it (e.g. WELT HD on 13, 403 and 1015).
* ``channel_id`` – the concrete LG list entry (``dvc_chan_id``).  It can change
  when the entry is renumbered.

``sim_entry_id`` is a simulator-internal, immutable UUID used to follow an
entry across ID changes.  It never leaves the simulator via the TV protocol.
"""
from __future__ import annotations

import enum
import json
from dataclasses import dataclass, field

GROUPS = 'ABCDEFGH'
NOT_MEMBER_INDEX = 250          # observed in real backups for non-members
FAVORITE_GROUP_ID_BASE = 200    # channel_group_tuner ids 200..207 = A..H
CHANNEL_TABLES = ('tuner_on', 'tuner_off')


class NumberEffect(enum.StrEnum):
    MOVE = 'MOVE'
    SWAP = 'SWAP'
    COPY = 'COPY'
    REUSE_COPY = 'REUSE_COPY'
    DENY = 'DENY'


class EvidenceLevel(enum.StrEnum):
    HARDWARE_CONFIRMED = 'HARDWARE_CONFIRMED'
    TRACE_CONFIRMED = 'TRACE_CONFIRMED'
    HISTORICAL_REPORTED = 'HISTORICAL_REPORTED'
    CURRENT_CLIENT_CONFIRMED = 'CURRENT_CLIENT_CONFIRMED'
    SIMULATOR_ASSUMPTION = 'SIMULATOR_ASSUMPTION'
    UNSUPPORTED = 'UNSUPPORTED'


@dataclass(frozen=True, order=True)
class DvbKey:
    onid: int
    tsid: int
    sid: int

    def __str__(self) -> str:
        return f'{self.onid}/{self.tsid}/{self.sid}'


@dataclass
class ChannelEntry:
    """Editor-visible view of one ``tuner_on`` row."""
    channel_id: str
    mso: str
    name: str
    number: int
    mode: str
    channel_type: str
    satellite: str
    dvb: DvbKey
    signal_id: str
    radio: bool
    invisible: bool
    satellite_lcn: bool
    groups: dict[str, bool] = field(default_factory=dict)
    index: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_row(cls, row) -> ChannelEntry:
        keys = row.keys()

        def num(column, default=0):
            value = row[column] if column in keys else None
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        return cls(
            channel_id=str(row['dvc_chan_id']), mso=str(row['mso_prdt_itm_code'] or ''),
            name=str(row['chan_std_name'] or ''), number=num('chan_no_int'),
            mode=str(row['chan_mode_name'] or ''), channel_type=str(row['chan_type_name'] or ''),
            satellite=str(row['sat_name'] or '').strip(),
            dvb=DvbKey(num('dvb_chan_nw_id'), num('dvb_chan_transf_strm_id'), num('dvb_chan_svc_id')),
            signal_id=str(row['signal_chan_id'] or ''), radio=bool(num('radio_flag')),
            invisible=bool(num('invisible_flag')), satellite_lcn=bool(num('satelliteLcn_flag')),
            groups={g: is_member_flag(row[f'fav_chan_gr_{g.lower()}']) for g in GROUPS},
            index={g: num(f'favoriteIdx{g}', NOT_MEMBER_INDEX) for g in GROUPS},
        )

    @property
    def member_of(self) -> list[str]:
        return [g for g in GROUPS if self.groups.get(g)]

    def snapshot(self) -> dict:
        """Compact state used in journal before/after records."""
        return {'channelId': self.channel_id, 'number': self.number, 'mode': self.mode,
                'groups': self.member_of,
                'index': {g: self.index[g] for g in self.member_of}}


def is_member_flag(value) -> bool:
    return str(value or '').strip().lower() in ('1', 'true')


def user_fav_json(groups: list[str]) -> str:
    return json.dumps(groups, separators=(',', ':'))


@dataclass
class Mutation:
    sim_entry_id: str
    before: dict | None
    after: dict | None
    note: str = ''


@dataclass
class LunaReply:
    """Outcome of one Luna call: what the client sees vs. what really changed."""
    response: dict
    mutations: list[Mutation] = field(default_factory=list)
    effect: str | None = None

    @property
    def mutated(self) -> bool:
        return bool(self.mutations)


class LunaError(Exception):
    """Business rejection reported to the client as ``returnValue:false``."""

    def __init__(self, code: str, text: str):
        super().__init__(f'{code}: {text}')
        self.code, self.text = code, text

    def response(self) -> dict:
        return {'returnValue': False, 'errorCode': self.code, 'errorText': self.text}


class UnsupportedOperation(LunaError):
    """Operation/format the simulator deliberately does not emulate (fail closed)."""

    def __init__(self, text: str):
        super().__init__('SIM_UNSUPPORTED', text)


class InvariantViolation(RuntimeError):
    pass
