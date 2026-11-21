# -*- coding: UTF-8 -*-
"""
快照投影补充
============
供 tests/kernel_data.project_state 调用，把 GameState 里的全局键按旧缓存的属性名记进快照。
project_world_misc 记世界设定、周目、国家、模式、吵醒名单、成就、事件与指令记录、计划队列与寻路，共 14 个全局键。
指令记录只记最近行为，每日记录不在快照里。
project_base_tallies 记基地的派对排期、旅馆房间档次、计数与冰箱，共 4 个全局键。
它还记干员人数上限与仓库容量，这两项读时算出。
stepping 与 auto_commit_outside_step 供教育区测试在内核单步之外自动套用指定全局键的写入。
"""

from __future__ import annotations

import contextlib
import importlib
from collections.abc import Collection, Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from Script.Kernel import core

_in_step = 0
""" 经 stepping() 包住的内核单步嵌套层数 """


@contextlib.contextmanager
def stepping() -> Iterator[None]:
    """
    标出正在执行一次内核推进，让 auto_commit_outside_step 不拦截这一步里的 working.put
    Keyword arguments:
    无
    Return arguments:
    Iterator[None] -- 上下文管理器
    """
    global _in_step
    _in_step += 1
    try:
        yield
    finally:
        _in_step -= 1


def auto_commit_outside_step(keys: Collection[str]) -> None:
    """
    包装 working.put：在 stepping() 之外且没有打开缓冲区时，
    把 keys 里全局键的写入经 kernel_data.writing() 套用到内核状态。
    stepping() 内、角色键与其余全局键原样走 working.put
    Keyword arguments:
    keys -- 允许在一步之外自动套用的全局键集合
    """
    from Script.Modules.gameplay_resolution import working
    from tests import kernel_data

    allowed = frozenset(keys)
    raw_put = working.put

    def put(who: str | None, key: str, new: core.JSON) -> None:
        if _in_step or who is not None or key not in allowed:
            raw_put(who, key, new)
            return
        try:
            raw_put(who, key, new)
        except RuntimeError:
            with kernel_data.writing():
                raw_put(who, key, new)

    working.put = put


def domain(name: str) -> Any:
    """按模块名导入 Script.Modules.domains 下的领域模块，供慢速层延迟导入用"""
    return importlib.import_module(f"Script.Modules.domains.{name}")


def world_settings() -> dict[int, Any]:
    """本周目的世界设定表"""
    return dict(domain("playthrough").settings("world"))


def set_world_setting(cid: int, value: Any) -> None:
    """把一项世界设定设为 value"""
    from tests import kernel_data

    kernel_data.put(domain("playthrough").set_setting, "world", cid, value)


def mode(name: str) -> bool:
    """读一项模式开关（time_stop / group_sex / sex_class）"""
    return bool(getattr(domain("modes"), name)())


def project_world_misc(state: dict[str, object]) -> None:
    """
    快照里按旧缓存的属性名记下 GameState 里的本周目设定、周目数、势力与国家、模式开关、
    被吵醒的角色、成就、事件与最近行为记录、计划队列、寻路与睡觉存档标记
    Keyword arguments:
    state -- 快照，原地补上
    """
    from Script.Core import game_type
    from Script.Modules.domains import (
        achievement,
        country,
        history,
        modes,
        needs,
        plan,
        playthrough,
    )
    from tests.snapshot import CACHE_AREAS, flatten

    world_country = game_type.Country()
    world_country.nation_reputation = country.table(country.REPUTATION)
    world_country.country_infection_rate = country.table(country.INFECTION)
    world_country.country_infection_patient_ratio = country.table(country.RATIO)
    world_country.last_week_all_country_infection_rate = (
        country.last_week_rate()
    )
    fields: dict[str, object] = {
        "difficulty_setting": playthrough.settings(playthrough.DIFFICULTY),
        "birth_type_setting": playthrough.settings(playthrough.BIRTH_TYPE),
        "first_bonus": playthrough.settings(playthrough.FIRST_BONUS),
        "world_setting": playthrough.settings(playthrough.WORLD),
        "game_round": playthrough.game_round(),
        "country": world_country,
        "time_stop_mode": modes.time_stop(),
        "group_sex_mode": modes.group_sex(),
        "sex_class_mode": modes.sex_class(),
        "noise_woken": needs.noise_woken(),
        "achievement": achievement.view(),
        "taiggered_event_record": history.triggered_ids(),
        "today_taiggered_event_record": history.today_ids(),
        "pl_sleep_save_flag": plan.sleep_save(),
        "plan_queue": plan.queues(),
        "player_route": plan.route(),
        "pl_pre_behavior_instruce": history.recent(),
    }
    for field, value in fields.items():
        flatten(f"world.{CACHE_AREAS.get(field, field)}.{field}", value, state)


def project_base_tallies(state: dict[str, object]) -> None:
    """
    快照里按罗德岛对象上旧的属性名记下派对排期、旅馆房间档次、四项计数、冰箱的两个表与两项算出的上限。
    快照因此能与按这些名字录下的快照比较。冰箱的两个表记在 world.cooking 下，其余记在 world.base 下
    Keyword arguments:
    state -- 快照，原地补上
    """
    from Script.Modules.domains import entertainment, facility, fridge, tallies
    from Script.Modules.domains import warehouse
    from tests.snapshot import flatten

    base = {
        "party_day_of_week": entertainment.party_days(),
        "love_hotel_room_lv": entertainment.hotel_room(),
        "people_max": facility.people_max(),
        "warehouse_capacity": warehouse.capacity(),
    }
    for old, name in tallies.PICKLED.items():
        base[old] = tallies.get(name)
    for field, value in base.items():
        flatten(f"world.base.{field}", value, state)
    for old, kind in fridge.PICKLED.items():
        flatten(f"world.cooking.{old}", fridge.table(kind), state)
    from tests import chara_projection

    chara_projection.project(state)
