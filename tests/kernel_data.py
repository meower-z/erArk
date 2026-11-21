# -*- coding: UTF-8 -*-
"""
测试读写内核状态里的游戏数据
============================
- writing：测试在一步之外跑写 GameState 数据的游戏代码（例如直接调用孕产结算）时用。
  写入记在以当前状态为底的缓冲区里，with 块结束时套用到内核状态上。
- written 在 writing 里跑一个游戏函数并交回它的返回值。born 用 written 在一步之外生一个孩子。
- reset_clock 把内核换成一个没有角色、时钟在给定时刻、带着给定全局数据的 GameState。
- set_facility_level 改设施等级。set_room_open 改待开放设施的开放情况。
- set_needs 与 needs_of 改、读角色的 body.needs，set_milk_max 与 milk_max_of 改、读角色的乳汁上限（body.pregnancy）。
- set_ward 在一步之外换掉医疗部的住院病人表。
- put 调用一个领域模块的写函数，在一步之外时经 written 套用（例如换公务事件队列）。
- set_book_holders 改借阅表里给出的书的借书人。
- reprojected 从缓存重新投影各角色的行动，每个角色的数据跟着这个角色留在角色数据或 roster.offstage 里。
- project_state 在快照里用这些数据在缓存里时的属性名记下 body.needs、乳汁上限、动力、设施、经济、岗位名册、监狱长、
  仓库、生产线、食堂货架、医疗部、外勤委托、载具、访客、罗德岛位置、招募、公务、外交、宿舍管理员与图书馆的值，
  快照因此能与按缓存属性录下的快照比较。
"""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import datetime
    from collections.abc import Callable, Iterator

    from Script.Core import game_type
    from Script.Core.num import Num
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


def written[**P, T](fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """
    在一步之外跑写 GameState 数据的游戏函数 fn：在 writing 的 with 块里调用它，块结束时写下的数据套用到内核状态上
    Keyword arguments:
    fn -- 游戏函数
    args -- fn 的位置参数
    kwargs -- fn 的关键字参数
    Return arguments:
    T -- fn 的返回值
    """
    with writing():
        return fn(*args, **kwargs)


def new_island() -> game_type.Rhodes_Island:
    """
    测试世界启动时的罗德岛对象（basement.get_base_zero），随后像游戏的新开局一样重置医疗部数据，写进内核状态。
    get_base_zero 自己不再重置医疗部；这里补上，测试世界的医疗部数据与随机数消耗才和游戏开局时相同
    Return arguments:
    game_type.Rhodes_Island -- 新的罗德岛对象
    """
    from Script.Design import basement
    from Script.System.Medical_System import medical_service

    island = basement.get_base_zero()
    written(medical_service.init_medical_department_data, island)
    return island


def reset_clock(dt: datetime.datetime, data: Mapping[str, core.JSON]) -> None:
    """
    内核换成一个没有角色、时钟在 dt 的 GameState。它的全局数据是 data 加上此刻的 ticked 与 settled_day
    Keyword arguments:
    dt -- 游戏时间
    data -- 全局数据
    """
    from types import MappingProxyType

    from Script.Design import game_time
    from Script.Kernel import core

    m = game_time.minutes(dt)
    day = game_time.day(m)
    core.reset_state(
        core.GameState(
            m,
            MappingProxyType({}),
            MappingProxyType({**data, "ticked": m, "settled_day": day}),
        )
    )


def set_facility_level(cid: int, level: int) -> None:
    """
    把一个设施的等级设为 level。
    在一步、一次挑选或一个缓冲区里时写进当前缓冲区，不在这些里时套用到内核状态上
    Keyword arguments:
    cid -- 设施id
    level -- 等级
    """
    from Script.Modules.domains import facility

    try:
        facility.set_level(cid, level)
    except RuntimeError:
        with writing():
            facility.set_level(cid, level)


def set_room_open(cid: int, value: bool = True) -> None:
    """
    把一个待开放设施的开放情况设为 value。
    在一步、一次挑选或一个缓冲区里时写进当前缓冲区，不在这些里时套用到内核状态上
    Keyword arguments:
    cid -- 待开放设施id
    value -- 是否开放
    """
    from Script.Modules.domains import facility

    try:
        facility.set_open(cid, value)
    except RuntimeError:
        with writing():
            facility.set_open(cid, value)


def born(mother_id: int, name: str) -> int:
    """
    在一步之外由 character_handle.born_new_character 生一个孩子，经 written 把写下的数据套用到内核状态上
    Keyword arguments:
    mother_id -- 母亲的角色id
    name -- 孩子的名字
    Return arguments:
    int -- 孩子的角色id
    """
    from Script.Design import character_handle

    return written(character_handle.born_new_character, mother_id, name)


def set_needs(cid: int, **values: Num) -> None:
    """
    把角色 body.needs 里给出的项换成新值。
    在一步、一次挑选或一个缓冲区里时写进当前缓冲区，不在这些里时套用到内核状态上
    Keyword arguments:
    cid -- 角色id
    values -- 项到新值
    """
    from Script.Modules.domains import needs

    try:
        needs.set(cid, **values)
    except RuntimeError:
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


def set_milk_max(cid: int, value: int) -> None:
    """
    把角色的乳汁上限（body.pregnancy）换成 value。
    在一步、一次挑选或一个缓冲区里时写进当前缓冲区，不在这些里时套用到内核状态上
    Keyword arguments:
    cid -- 角色id
    value -- 乳汁上限
    """
    from Script.Modules.domains import pregnancy

    try:
        pregnancy.set_milk_max(cid, value)
    except RuntimeError:
        with writing():
            pregnancy.set_milk_max(cid, value)


def milk_max_of(cid: int) -> int:
    """
    角色此刻的乳汁上限（body.pregnancy），在缓冲区里时含还没套用的写入
    Keyword arguments:
    cid -- 角色id
    Return arguments:
    int -- 乳汁上限
    """
    from Script.Modules.domains import pregnancy

    return pregnancy.milk_max(cid)


def put[**P](
    fn: Callable[P, object], *args: P.args, **kwargs: P.kwargs
) -> None:
    """
    调用只写 GameState 数据的 fn（领域模块的写函数，例如 official.set_queue、library.set_holder）。
    在一步、一次挑选或一个缓冲区里时写进当前缓冲区，不在这些里时经 written 套用到内核状态上
    Keyword arguments:
    fn -- 写函数
    args -- fn 的位置参数
    kwargs -- fn 的关键字参数
    """
    try:
        fn(*args, **kwargs)
    except RuntimeError:
        written(fn, *args, **kwargs)


def set_book_holders(holders: Mapping[int, int]) -> None:
    """
    把给出的书的借书人换成新值，别的书不变，写法同 put
    Keyword arguments:
    holders -- 书id 到借书人
    """
    from Script.Modules.domains import library

    put(library.put_holders, {**library.holders(), **holders})


def set_ward(*patient_ids: int) -> None:
    """
    在一步之外把住院病人表换成只有给出编号的住院病人
    Keyword arguments:
    patient_ids -- 病人编号，不给则清空住院表
    """
    from Script.Modules.domains import medical, medical_patient
    from Script.System.Medical_System import medical_constant

    with writing(), medical.editing() as m:
        m.hospitalized = {
            pid: medical_patient.MedicalPatient(
                patient_id=pid,
                state=medical_constant.MedicalPatientState.HOSPITALIZED,
            )
            for pid in patient_ids
        }


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
    快照里按旧缓存的属性名记下 GameState 里的生理需求、体力等数值、动力与仓库，以便与按这些名字录下的基准逐项比较。
    body.needs 记作 chara.<id>.tired_point、hunger_point、urinate_point、pregnancy.milk
    与 upgrade.PICKLED_NEEDS 里的属性名，乳汁上限记作 chara.<id>.pregnancy.milk_max。
    每个大区块的生效策略记作 world.base.power_supply_strategy.<区块id>。
    设施等级、待开放设施的开放情况与基地效率记作 world.base 下的 facility_level.<设施id>、
    facility_open.<待开放设施id> 与 effectiveness。
    动力记在 world.base 下，名字为 power_storage、power_storage_max、power_operator_ids_list、
    main_power_facility_operator_ids、orundum_reactor_list（主反应炉等级与副反应炉数量）、other_power_facility_list
    与 battery_list。岗位名册与监狱长记在 world.base 下，名字为 all_work_npc_set（岗位id到角色id的集合）、
    work_people_now、hr_operator_ids_list 与 current_warden_id。
    资源库存记作 world.base.materials_resouce.<资源id>，已用的仓储空间扩展模块数记作
    world.base.used_extra_warehouse_capacity_module。
    生产线按旧的五项列表记作 world.base.<production.PICKLED_LINES 里的属性名>.<线id>。
    效率一项在流水线上记 0.0，在药田与温室上记 0。待换生产一项记 0。
    工人名单记作 world.base.<production.PICKLED_WORKERS 里的属性名>。
    食堂货架记作 world.cooking.dining_hall_data。医疗部数据记在 world.medical 下，
    名字为罗德岛对象上旧的属性名（medical.OLD_NAMES），病人按字段展开。
    外勤委托、载具、访客、邀请与罗德岛的位置由 _project_travel 记下。
    Keyword arguments:
    cache -- 游戏缓存
    state -- 快照，原地补上
    """
    from Script.Config import game_config
    from Script.Modules.domains import (
        facility,
        kitchen,
        medical,
        needs,
        power,
        pregnancy,
        production,
        warehouse,
        work,
    )
    from Script.Modules.save_load import upgrade
    from tests import base_projection
    from tests.snapshot import flatten

    names = {"tired": "tired_point", "hunger": "hunger_point"}
    names.update(urine="urinate_point", milk="pregnancy.milk")
    names.update({stat: name for name, stat in upgrade.PICKLED_NEEDS.items()})
    for cid in cache.character_data:
        for stat, value in needs.of(cid).items():
            flatten(f"chara.{cid}.{names[stat]}", value, state)
        name = f"chara.{cid}.pregnancy.milk_max"
        flatten(name, pregnancy.milk_max(cid), state)
    for zone, zone_data in game_config.config_facility.items():
        if zone_data.type == -1:
            name = f"world.base.power_supply_strategy.{zone}"
            flatten(name, power.strategy_of(zone), state)
    plant = power.plant()
    island = {
        "power_storage": power.storage(),
        "power_storage_max": power.storage_max(),
        "power_operator_ids_list": power.operator_ids(),
        "main_power_facility_operator_ids": plant["main_operators"],
        "orundum_reactor_list": (
            power.main_reactor_level(),
            plant["aux_reactors"],
        ),
        "other_power_facility_list": plant["clean"],
        "battery_list": plant["batteries"],
        "facility_level": facility.levels(),
        "facility_open": facility.opens(),
        "effectiveness": facility.effectiveness(),
        "all_work_npc_set": {w: set(ids) for w, ids in work.rosters().items()},
        "work_people_now": work.people_now(),
        "hr_operator_ids_list": list(work.roster(work.HR_WORK)),
        "current_warden_id": work.warden(),
        "materials_resouce": warehouse.stock(),
        "used_extra_warehouse_capacity_module": warehouse.extra_modules(),
    }
    for field, value in island.items():
        flatten(f"world.base.{field}", value, state)
    for field, kind in production.PICKLED_LINES.items():
        rate = 0.0 if kind == "assembly" else 0
        for line_id, line in production.lines(kind).items():
            old = [line["product"], line["main"], rate, 0, line["hour"]]
            flatten(f"world.base.{field}.{line_id}", old, state)
    for field, kind in production.PICKLED_WORKERS.items():
        flatten(f"world.base.{field}", production.workers(kind), state)
    name = "world.cooking.dining_hall_data"
    flatten(name, kitchen.shelves(), state)
    for field, value in medical.state().as_fields().items():
        if field in medical.OLD_TABLES:
            patients = {pid: p.as_dict() for pid, p in value.items()}
            flatten(f"world.medical.{field}", patients, state)
        else:
            flatten(f"world.medical.{field}", value, state)
    _project_economy(state)
    _project_travel(state)
    base_projection.project(state)


def _project_travel(state: dict[str, object]) -> None:
    """
    快照里按罗德岛对象上旧的属性名与形状记下外勤委托、载具、访客、邀请与罗德岛的位置。
    进行中的委托记作 world.commission.ongoing_field_commissions.<委托id> 下的 [队伍, 返回时刻, 载具]。
    已完成与不可进行的委托记作 world.commission 下的两个集合。
    载具记作 world.vehicle.vehicles.<载具id> 下的 [拥有数, 外勤中数]。访客、上次随机来访时刻、邀请、移动标记、访客上限、
    所在位置与移动记在 world.base 下，名字为旧的属性名。GameState 不存的列表项按新游戏里的值记：位置的第二项为 1701，
    邀请的第三项为 0，移动的第二项为 0。停着时移动记作 [0, 0, 0]
    Keyword arguments:
    state -- 快照，原地补上
    """
    from Script.Modules.domains import commission, location, visitor
    from tests.snapshot import flatten

    ongoing = {
        cid: [list(one.team), one.end, list(one.vehicles)]
        for cid, one in commission.ongoing().items()
    }
    flatten("world.commission.ongoing_field_commissions", ongoing, state)
    for name, ids in (
        ("finished_field_commissions_set", commission.finished()),
        ("shut_down_field_commissions_set", commission.shut_down()),
    ):
        flatten(f"world.commission.{name}", set(ids), state)
    rows = {vid: list(row) for vid, row in commission.vehicles().items()}
    flatten("world.vehicle.vehicles", rows, state)
    going = location.move()
    island = {
        "visitor_info": visitor.visitors(),
        "last_visitor_time": visitor.last_arrival(),
        "invite_visitor": [*visitor.invite(), 0],
        "base_move_visitor_flag": visitor.moved(),
        "visitor_max": visitor.capacity(),
        "current_location": [location.country(), 1701],
        "move_target_and_time": [going[0], 0, going[1]] if going else [0] * 3,
    }
    for field, value in island.items():
        flatten(f"world.base.{field}", value, state)


def _project_economy(state: dict[str, object]) -> None:
    """
    快照里按旧罗德岛对象的属性名记下 GameState 里的经济与贸易数据。
    今日收入、已开放商店、供需系数、今日买卖总量、交易员名单、主交易员与自动交易设置记在 world.base 下。
    自动交易设置记配置里的每种资源与表里的每种资源经 economy.auto_trade 读出的值。
    餐馆的货架记在 world.cooking.restaurant_data.<餐馆id> 下，地摊小贩的记在 world.cooking.stall_vendor_data.0 下。
    每份食物记作 economy.food 按货架记录做出的食物对象
    Keyword arguments:
    state -- 快照，原地补上
    """
    from Script.Config import game_config
    from Script.Modules.domains import economy
    from tests.snapshot import flatten

    rids = [*game_config.config_resouce, *economy.auto_trade_table()]
    island = {
        "all_income": economy.income(),
        "shop_open_list": list(economy.shops_open()),
        "supply_demand_dict": economy.supply_demand(),
        "today_trade_resource_count": economy.traded_today(),
        "trade_operator_ids_list": economy.trade_operator_ids(),
        "resource_type_main_trader": economy.main_traders(),
        "resource_type_auto_trade_setting": {
            rid: economy.auto_trade(rid) for rid in rids
        },
    }
    for field, value in island.items():
        flatten(f"world.base.{field}", value, state)
    shelves = economy.shelf_table()
    for shop, foods in shelves.items():
        name = (
            "world.cooking.stall_vendor_data.0"
            if shop == economy.STALL
            else f"world.cooking.restaurant_data.{shop}"
        )
        for recipe, row in foods.items():
            for uid, quality in row.items():
                food = economy.food(recipe, uid, quality)
                flatten(f"{name}.{recipe}.{uid}", food, state)
