"""Data-driven decision which effect a ``changeChannelNumber`` call has.

The firmware behaviour is not uniform (spec §7): MOVE, SWAP, COPY, REUSE_COPY
and DENY are selected by ordered profile rules; the first matching rule wins.
Rules carry their evidence level so nobody mistakes an assumption for a fact.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from lg_tv_sim.domain.models import IP_FIRST_INDEX, IP_NOT_MEMBER_INDEX, ChannelEntry, EvidenceLevel, NumberEffect

Occupancy = Literal['none', 'one', 'same_dvb', 'other_dvb', 'many', 'occupied', 'any']
PROFILES_DIR = Path(__file__).resolve().parent.parent / 'profiles'


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class NumberCondition(Strict):
    source_mode: str | None = None
    source_min: int | None = None
    source_max: int | None = None
    target_min: int | None = None
    target_max: int | None = None
    target_occupant: Occupancy = 'any'
    tags_any: list[str] = Field(default_factory=list)
    channel_id_regex: str | None = None


class NumberRule(Strict):
    id: str
    when: NumberCondition = NumberCondition()
    effect: NumberEffect
    error_code: str = 'CHANNEL_ERROR_1003'
    error_text: str = 'Channel Move Denied'
    evidence: EvidenceLevel = EvidenceLevel.SIMULATOR_ASSUMPTION
    note: str = ''


class FavoriteLayout(Strict):
    """favoriteIdx model for lists with tuner and LG Channels (IP) members.

    Tuner members 0.., IP members from ``ip_first_index`` (E5, E8 confirmed for a pure IP block). Whether IP
    members can move before tuner members is UNKNOWN (U1): with ``ip_block_after_tuner`` the IP block stays
    behind the tuner members and a crossing move changes nothing but still answers returnValue true;
    ``false`` keeps one joint order 0..n-1 (SIMULATOR_ASSUMPTION either way).
    """
    ip_block_after_tuner: bool = True
    ip_first_index: int = IP_FIRST_INDEX
    ip_not_member_index: int = IP_NOT_MEMBER_INDEX


class Profile(Strict):
    id: str
    description: str = ''
    number_min: int = 1
    number_max: int = 9999
    read_after_write_stale_reads: int = 0
    favorites: FavoriteLayout = FavoriteLayout()
    number_rules: list[NumberRule]

    @classmethod
    def load(cls, name_or_path: str | Path) -> Profile:
        path = Path(name_or_path)
        if not path.suffix:
            path = PROFILES_DIR / f'{name_or_path}.yaml'
        return cls.model_validate(yaml.safe_load(path.read_text(encoding='utf-8')))


@dataclass(frozen=True)
class NumberContext:
    source: ChannelEntry
    target: int
    occupants: list[ChannelEntry]
    tags: list[str]

    @property
    def occupancy(self) -> set[str]:
        n = len(self.occupants)
        if n == 0:
            return {'none', 'any'}
        if n > 1:
            return {'many', 'occupied', 'any'}
        same = self.occupants[0].dvb == self.source.dvb
        return {'one', 'occupied', 'any', 'same_dvb' if same else 'other_dvb'}


def matches(condition: NumberCondition, ctx: NumberContext) -> bool:
    source = ctx.source
    checks = (
        condition.source_mode is None or condition.source_mode == source.mode,
        condition.source_min is None or source.number >= condition.source_min,
        condition.source_max is None or source.number <= condition.source_max,
        condition.target_min is None or ctx.target >= condition.target_min,
        condition.target_max is None or ctx.target <= condition.target_max,
        condition.target_occupant in ctx.occupancy,
        not condition.tags_any or bool(set(condition.tags_any) & set(ctx.tags)),
        condition.channel_id_regex is None or re.fullmatch(condition.channel_id_regex, source.channel_id) is not None,
    )
    return all(checks)


NO_RULE = NumberRule(id='no-matching-rule', effect=NumberEffect.DENY, error_code='SIM_NO_NUMBER_RULE',
                     error_text='No simulator profile rule covers this number change',
                     evidence=EvidenceLevel.UNSUPPORTED)


def decide(profile: Profile, ctx: NumberContext) -> NumberRule:
    for rule in profile.number_rules:
        if matches(rule.when, ctx):
            return rule
    return NO_RULE
