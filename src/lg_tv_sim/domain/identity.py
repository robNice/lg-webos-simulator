"""Changeable LG channel IDs and the simulator-internal stable identity.

``ChannelIdPolicy`` derives the ID an entry gets after a renumbering.  The
satellite format ``<src>_<phy>_<maj>_<min>_<tsid>_<sid>_<onid>`` with
``maj == min == channel number`` was observed in real backups (e.g.
``7_32_13_13_1053_21108_1`` for programme 13).  That the firmware rewrites
maj/min to the new number is a SIMULATOR_ASSUMPTION consistent with the
historical reports (ID changes on renumbering, technical tail stays).  Every
other format fails closed with ``UnsupportedChannelId``.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from lg_tv_sim.domain.models import UnsupportedOperation

SIM_NAMESPACE = uuid.UUID('6b1f3a52-8f0e-4c55-9d43-1c7e5a0e7f21')


class UnsupportedChannelId(UnsupportedOperation):
    def __init__(self, channel_id: str, reason: str):
        super().__init__(f'unsupported channel ID format {channel_id!r}: {reason}')
        self.code = 'SIM_UNSUPPORTED_CHANNEL_ID'
        self.channel_id = channel_id


class SatelliteIdPolicy:
    PATTERN = re.compile(r'(\d+)_(\d+)_(\d+)_(\d+)_(\d+)_(\d+)_(\d+)')

    def renumbered(self, channel_id: str, old_number: int, new_number: int, signal_id: str = '') -> str:
        match = self.PATTERN.fullmatch(channel_id)
        if not match:
            raise UnsupportedChannelId(channel_id, 'expected 7 numeric parts')
        src, phy, major, minor, tsid, sid, onid = match.groups()
        if major != minor or int(major) != int(old_number):
            raise UnsupportedChannelId(channel_id, f'major/minor do not encode the programme number {old_number}')
        if signal_id and signal_id != f'{tsid}_{sid}_{onid}':
            raise UnsupportedChannelId(channel_id, f'technical tail differs from signal_chan_id {signal_id!r}')
        return f'{src}_{phy}_{new_number}_{new_number}_{tsid}_{sid}_{onid}'


class ChannelIdPolicy:
    """Per reception mode; unknown modes (e.g. Cable IDs ``3_1_<x>_0_...``) fail closed."""

    def __init__(self, policies: dict[str, SatelliteIdPolicy] | None = None):
        self.policies = policies if policies is not None else {'Satellite': SatelliteIdPolicy()}

    def renumbered(self, mode: str, channel_id: str, old_number: int, new_number: int, signal_id: str = '') -> str:
        policy = self.policies.get(mode)
        if policy is None:
            raise UnsupportedChannelId(channel_id, f'no ID policy for reception mode {mode!r}')
        return policy.renumbered(channel_id, old_number, new_number, signal_id)


@dataclass
class IdentityRecord:
    sim_entry_id: str
    channel_id: str
    mso: str = ''
    tags: list[str] = field(default_factory=list)
    copy_of: str | None = None
    id_history: list[str] = field(default_factory=list)


class IdentityRegistry:
    """sim_entry_id <-> current LG channel ID.  Never exposed over the TV protocol."""

    def __init__(self, records: dict[str, IdentityRecord] | None = None):
        self.records: dict[str, IdentityRecord] = records or {}

    @staticmethod
    def initial_id(seed: str, channel_id: str, mso: str) -> str:
        return str(uuid.uuid5(SIM_NAMESPACE, f'{seed}|{channel_id}|{mso}'))

    @classmethod
    def build(cls, seed: str, rows: list[tuple[str, str]], tags: dict[str, list[str]] | None = None) -> IdentityRegistry:
        tags = tags or {}
        records = {}
        for channel_id, mso in rows:
            sim_id = cls.initial_id(seed, channel_id, mso)
            records[sim_id] = IdentityRecord(sim_id, channel_id, mso, list(tags.get(channel_id, [])),
                                             id_history=[channel_id])
        return cls(records)

    def find(self, channel_id: str, mso: str = '') -> IdentityRecord | None:
        for record in self.records.values():
            if record.channel_id == channel_id and record.mso == mso:
                return record
        return None

    def require(self, channel_id: str, mso: str = '') -> IdentityRecord:
        record = self.find(channel_id, mso)
        if record is None:
            raise KeyError(f'no simulator identity for channel {channel_id!r}')
        return record

    def rename(self, sim_entry_id: str, new_channel_id: str) -> None:
        record = self.records[sim_entry_id]
        record.channel_id = new_channel_id
        record.id_history.append(new_channel_id)

    def add_copy(self, parent: IdentityRecord, new_channel_id: str, sequence: int) -> IdentityRecord:
        sim_id = str(uuid.uuid5(SIM_NAMESPACE, f'{parent.sim_entry_id}|copy|{sequence}'))
        record = IdentityRecord(sim_id, new_channel_id, parent.mso, list(parent.tags), parent.sim_entry_id,
                                [new_channel_id])
        self.records[sim_id] = record
        return record

    def tags_of(self, channel_id: str, mso: str = '') -> list[str]:
        record = self.find(channel_id, mso)
        return list(record.tags) if record else []

    def to_json(self) -> str:
        return json.dumps({k: asdict(v) for k, v in sorted(self.records.items())}, indent=1, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> IdentityRegistry:
        return cls({k: IdentityRecord(**v) for k, v in json.loads(text).items()})

    def save(self, path: Path) -> None:
        tmp = path.with_suffix('.tmp')
        tmp.write_text(self.to_json(), encoding='utf-8')
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> IdentityRegistry:
        return cls.from_json(path.read_text(encoding='utf-8'))
