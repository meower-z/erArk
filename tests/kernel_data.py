# -*- coding: UTF-8 -*-
"""
测试读写内核状态里的游戏数据
============================
- writing：测试在一步之外跑写 GameState 数据的游戏代码（例如直接调用孕产结算）时用。
  写入记在以当前状态为底的缓冲区里，with 块结束时套用到内核状态上。
- set_needs 与 needs_of 在一步之外改、读角色的生理需求。
- reprojected 从缓存重新投影各角色的行动，每个角色的数据跟着这个角色留在角色数据或 roster.offstage 里。
- project_state 在快照里按生理需求与供电策略在缓存里时的名字记下它们的值，快照因此能与以前的快照比较。
"""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    from Script.Core import game_type
    from Script.Kernel import core
    from Script.Modules.domains.needs import Needs


@contextlib.contextmanager
def writing() -> Iterator[None]:
    """
    with 块里写的 GameState 数据记在以当前状态为底的缓冲区里，块结束时用 core.reset_state 套用到内核状态上
    Return arguments:
    Iterator -- with 块
    """
    from Script.Kernel import core
    from Script.Modules.gameplay_resolution import working

    with working.based_on(core.state()) as buffer:
        yield
        effects = buffer.effects()
    core.reset_state(core.preview(core.state(), effects))


def set_needs(cid: int, **values: int) -> None:
    """
    在一步之外把角色的几项生理需求（body.needs）换成新值，套用到内核状态上
    Keyword arguments:
    cid -- 角色id
    values -- 需求项到新值
    """
    from Script.Modules.domains import needs

    with writing():
        needs.set(cid, **values)


def needs_of(cid: int) -> Needs:
    """
    角色此刻的生理需求（body.needs）
    Keyword arguments:
    cid -- 角色id
    Return arguments:
    Needs -- 需求项到值
    """
    from Script.Modules.domains import needs

    return needs.of(cid)


def reprojected(game: core.GameState) -> core.GameState:
    """
    由 actions.state_from_cache 从缓存投影出各角色的行动，时钟取自 game。
    全局数据取自 game，只有 ticked 与 settled_day 取投影的值（时钟改过之后，第一次 Tick 从投影的时钟结算）。
    投影里原来就在 game 里的角色留着自己的数据，只去掉 open。
    离开投影的角色去掉 open 后还有数据时，数据放进 roster.offstage。
    最后由 working.reconcile 让每个角色的数据只在一处，新进投影的角色从 roster.offstage 取回数据
    Keyword arguments:
    game -- 当前的 GameState
    Return arguments:
    GameState -- 投影后的状态
    """
    from dataclasses import replace
    from types import MappingProxyType

    from Script.Kernel import core
    from Script.Modules.gameplay_resolution import actions, working

    fresh = actions.state_from_cache(game.clock)
    kept = {
        who: (
            replace(c, data=MappingProxyType(_without_open(game, who)))
            if who in game.characters
            else c
        )
        for who, c in fresh.characters.items()
    }
    fresh = replace(fresh, characters=MappingProxyType(kept))
    fresh = replace(fresh, data=MappingProxyType({**game.data, **fresh.data}))
    left = {
        who: data
        for who in game.characters
        if who not in fresh.characters and (data := _without_open(game, who))
    }
    if left:
        parked = core.value(fresh, None, working.OFFSTAGE) or {}
        assert isinstance(parked, Mapping)
        fresh = core.with_value(
            fresh, None, working.OFFSTAGE, {**parked, **left}
        )
    return working.reconcile(fresh)


def _without_open(game: core.GameState, who: str) -> dict[str, core.JSON]:
    """
    角色的数据去掉 open 键
    Keyword arguments:
    game -- GameState
    who -- 角色键
    Return arguments:
    dict -- 去掉 open 之后的数据
    """
    from Script.Modules.gameplay_resolution import actions

    data = game.characters[who].data
    return {k: v for k, v in data.items() if k != actions.OPEN}


def project_state(cache: game_type.Cache, state: dict[str, object]) -> None:
    """
    快照里按缓存里时的名字记下 GameState 里的生理需求与供电策略：chara.<id>.tired_point、hunger_point、
    urinate_point、pregnancy.milk，以及 world.base.power_supply_strategy.<区块id>（每个大区块的生效策略）
    Keyword arguments:
    cache -- 游戏缓存
    state -- 快照，原地补上
    """
    from Script.Config import game_config
    from Script.Modules.domains import needs, power
    from tests.snapshot import flatten

    names = {"tired": "tired_point", "hunger": "hunger_point"}
    names.update(urine="urinate_point", milk="pregnancy.milk")
    for cid in cache.character_data:
        for stat, value in needs.of(cid).items():
            flatten(f"chara.{cid}.{names[stat]}", value, state)
    for zone, facility in game_config.config_facility.items():
        if facility.type == -1:
            name = f"world.base.power_supply_strategy.{zone}"
            flatten(name, power.strategy_of(zone), state)
