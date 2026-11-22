# -*- coding: UTF-8 -*-
"""
静态检查系统 - 行为/时间/状态机/主循环完整性相关检查
覆盖角色行为(Behavior)、全局时钟(内核时钟与ticked/settled_day)与模式开关相关的
19条不变式(BEHAV-01~BEHAV-22，无BEHAV-06、BEHAV-13与BEHAV-21)。钩子点为
Script/UI/Panel/in_scene_panel.py主循环重绘处、flow_handle.askfor_all()之前。

以下四条生命周期事实已烘焙进本文件全部检查，任何依赖它们的护栏都不得删除：
1. activity.state的整数取值(constant.CharacterStatus)与行为配表cid是两套已经漂移的编号，
   任何"state必须等于/映射到行为cid"的断言一律不做。
2. 时停模式下玩家结算完即break、全局时间回退pl_duration分钟，NPC本轮完全未结算。
   玩家合法领先game_time.now()，NPC数据合法陈旧。
3. H中的NPC可以合法地持有已过期行为(handle_npc_ai.py的提前入集与character_behavior.py的H捷径都会让行为原样留存)。
4. 新开局到达钩子时没有任何结算跑过，因此任何"必须刚结算过"语义的断言都不成立。

执行顺序约束：BEHAV-07(字段类型)在语义上必须先于一切时间比较类检查；本文件中BEHAV-10/11/12/22各自复用
_behavior_type_ok()对同一角色重做一次同源判定，字段类型损坏时对该角色跳过判定(既不算失败也不算通过)，
避免把领域失败(类型损坏本身已由BEHAV-07单独报告)降级成时间比较抛异常、被框架记成"检查器自身异常"。
"""

from __future__ import annotations

import datetime

from Script.Core import cache_control
from Script.Config import game_config
from Script.Design import game_time
from Script.Modules.domains import (
    achievement,
    action_info,
    activity,
    flags,
    h_state,
)
from Script.Modules.domains import history, modes, roster
from ..check_registry import CheckFailure, register_check, make_failure

from typing import TYPE_CHECKING
from Script.Modules.domains import identity

if TYPE_CHECKING:
    from Script.Core import game_type


def _live_ids(cache: game_type.Cache) -> set:
    """
    参数:
        cache -- 全局缓存对象
    返回值:
        set -- 只遍历确实存在的角色id集合
    功能:
        计算0号玩家与在编名单（roster.active()）的并集，再与角色身份表（identity.table()）的键取交集，
        避免一个悬空id让整条检查降级成"检查器自身异常"。在编名单成员是否都在身份表里由CORE-01覆盖，
        本域不重复报警
    """
    npc_id_got = roster.active()
    character_data = identity.table()
    return ({0} | set(npc_id_got)) & set(character_data)


def _end(chara: identity.Identity) -> datetime.datetime:
    """
    参数:
        chara -- 角色对象
    返回值:
        datetime.datetime -- 行为结束时间
    功能:
        与生产代码(character_behavior.py计算end_time处)同源地计算行为结束时间，必须调用
        game_time.get_sub_date而不能用datetime.timedelta近似——get_sub_date会把1/2月钳到3月、
        4/5钳到6月……用timedelta近似会在跨季当天把合法行为误判成"早已过期"
    """
    return game_time.get_sub_date(
        minute=activity.behavior(chara.cid).duration,
        old_date=activity.behavior(chara.cid).start_time,
    )


def _behavior_type_ok(chara: identity.Identity) -> bool:
    """
    参数:
        chara -- 角色对象
    返回值:
        bool -- behavior核心字段类型是否合法(BEHAV-07的字段类型检查即调用本函数)
    功能:
        供BEHAV-10/11/12/22在字段类型损坏时跳过该角色的时间比较，避免抛异常被框架降级为"检查器自身异常"；
        起时behavior.start_time用isinstance，因为起时取自游戏时钟，类型是datetime的子类GameTime。
        分钟数behavior.duration用type(...)is int而非isinstance，因为isinstance(True, int)为真，
        布尔值不应被当作合法分钟数
    """
    try:
        behavior = activity.behavior(chara.cid)
        return (
            isinstance(behavior.behavior_id, str)
            and isinstance(behavior.start_time, datetime.datetime)
            and behavior.start_time.tzinfo is None
            and type(behavior.duration) is int
        )
    except Exception:
        return False


@register_check("BEHAV-01", "角色字典键与角色自身cid一致")
def check_character_dict_key_matches_cid() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure] -- 失败记录列表
    功能:
        校验身份表（identity.table()）的键与对应 Identity 的 cid 一致。
        调度器按 0 与在编名单里的 id 查找角色身份，键与 cid 不一致会让按 id 定位的结算写错角色
    """
    cache = cache_control.cache
    character_data = identity.table()
    npc_id_got = roster.active()
    failures = []
    for cid in _live_ids(cache):
        chara = character_data.get(cid)
        if chara is None:
            continue
        if getattr(chara, "cid", None) == cid:
            continue
        failures.append(
            make_failure(
                "BEHAV-01",
                "角色字典键与角色自身cid一致",
                f"character_data字典键cid={cid}对应的角色对象自身cid={getattr(chara, 'cid', None)!r}"
                f"(name={getattr(chara, 'name', '?')!r})，字典键与角色对象分裂会让按id定位的结算写错角色；"
                f"character_data键(前20个)={sorted(character_data.keys())[:20]}，npc_id_got(前20个)={sorted(npc_id_got)[:20]}",
                [cid],
            )
        )
    return failures


def _clock_marks() -> tuple[int, object, object]:
    """
    返回值:
        tuple -- 内核时钟(分钟)，GameState的ticked与settled_day(缺失时为None)
    功能:
        读一步边界上的时钟记账：ticked是上一次Tick结算到的时钟，settled_day是已跑过新一天结算的游戏日
    """
    from Script.Kernel import core

    game = core.state()
    return game.clock, game.data.get("ticked"), game.data.get("settled_day")


@register_check("BEHAV-02", "全局时钟健全性")
def check_global_clock_sanity() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure] -- 失败记录列表
    功能:
        校验GameState的时钟记账ticked/settled_day都是整数。游戏只有内核这一个时钟(分钟数，构造上就只到分钟)，
        两项缺失只可能来自没经state_from_cache或存档读入的GameState——那正是要抓的迁移缺陷
    """
    clock, ticked, settled_day = _clock_marks()
    if isinstance(ticked, int) and isinstance(settled_day, int):
        return []
    return [
        make_failure(
            "BEHAV-02",
            "全局时钟健全性",
            f"ticked={ticked!r}或settled_day={settled_day!r}不是整数；clock={clock}",
            [],
        )
    ]


@register_check("BEHAV-03", "世界月份只能是四季月")
def check_world_month_is_seasonal() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure] -- 失败记录列表
    功能:
        校验当前游戏时间的月份属于四季月{3,6,9,12}。全年被折叠为四个月，get_date_text()对第五种月份没有else分支，
        出现第五种月份下一次绘制就会UnboundLocalError崩溃
    """
    now_time = game_time.now()
    if now_time.month in {3, 6, 9, 12}:
        return []
    return [
        make_failure(
            "BEHAV-03",
            "世界月份只能是四季月",
            f"game_time={now_time!r}(月={now_time.month})不属于四季月{{3,6,9,12}}；get_date_text()对第五种月份"
            f"没有else分支，下一次绘制会UnboundLocalError崩溃",
            [],
        )
    ]


@register_check("BEHAV-04", "上一循环时间不得晚于当前时间")
def check_pre_game_time_not_after_game_time() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure] -- 失败记录列表
    功能:
        校验ticked不晚于内核时钟、settled_day不晚于今天。两者只由Tick/NewDay记成当时的时钟与日子，
        是单调追赶的锚点；本条是时钟倒流探测器。类型损坏由BEHAV-02负责，此处跳过
    """
    clock, ticked, settled_day = _clock_marks()
    if not isinstance(ticked, int) or not isinstance(settled_day, int):
        return []
    if ticked <= clock and settled_day <= game_time.day(clock):
        return []
    return [
        make_failure(
            "BEHAV-04",
            "上一循环时间不得晚于当前时间",
            f"ticked={ticked}或settled_day={settled_day}晚于clock={clock}(day={game_time.day(clock)})，"
            f"时钟疑似倒流；time_stop_mode={modes.time_stop()}",
            [],
        )
    ]


@register_check("BEHAV-05", "跨日刷新已经完成")
def check_daily_refresh_completed() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure] -- 失败记录列表
    功能:
        校验settled_day就是今天。时钟在0点停下，NewDay在任何人选行动之前跑，所以钩子处(玩家选行动时)
        今天的刷新一定已经跑过；不等说明今日事件记录/每日计数器等都没清
    """
    clock, __, settled_day = _clock_marks()
    if not isinstance(settled_day, int) or settled_day == game_time.day(clock):
        return []
    return [
        make_failure(
            "BEHAV-05",
            "跨日刷新已经完成",
            f"settled_day={settled_day}不是今天(day={game_time.day(clock)}, game_time={game_time.now()!r})，"
            f"跨日刷新疑似尚未执行；events.triggered_today长度={history.today_count()}",
            [],
        )
    ]


@register_check("BEHAV-07", "行为核心字段类型正确")
def check_behavior_core_field_types() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure] -- 失败记录列表
    功能:
        校验每个被调度角色的behavior有字符串id、朴素datetime起时、非布尔整数分钟数。旧存档迁移直接复用整个
        behavior对象，老存档里behavior_id可能还是int，类型损坏必须先于时间运算被识别。本条失败时，
        BEHAV-10/11/12/22对同一角色跳过判定，避免时间比较抛异常被框架记成"检查器自身异常"而丢掉本该有的诊断
    """
    cache = cache_control.cache
    character_data = identity.table()
    failures = []
    for cid in _live_ids(cache):
        chara = character_data.get(cid)
        if chara is None or _behavior_type_ok(chara):
            continue
        behavior = activity.behavior(chara.cid)
        failures.append(
            make_failure(
                "BEHAV-07",
                "行为核心字段类型正确",
                (
                    f"角色cid={cid}(name={getattr(chara, 'name', '?')!r})的behavior字段类型损坏："
                    f"behavior类型={type(behavior).__name__}, behavior_id={getattr(behavior, 'behavior_id', None)!r}, "
                    f"start_time={getattr(behavior, 'start_time', None)!r}, "
                    f"duration={getattr(behavior, 'duration', None)!r}；"
                    f"类型损坏必须先于时间比较类检查被识别，BEHAV-10/11/12/22对该角色本轮跳过判定"
                ),
                [cid],
            )
        )
    return failures


@register_check("BEHAV-08", "当前行为id必须已注册")
def check_behavior_id_registered() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure] -- 失败记录列表
    功能:
        校验每个被调度角色的behavior_id都能在game_config.config_behavior(键为en_name)中查到。未注册id会让
        生产代码的直接下标必KeyError。旧存档携带已删除行为id会触发——那属于应当迁移处理的真问题，不加豁免。
        若config_behavior配表本身未加载(空)，视为独立跑本模块之类的场景，降级为跳过本条
    """
    cache = cache_control.cache
    config_behavior = getattr(game_config, "config_behavior", None)
    if not config_behavior:
        return []
    character_data = identity.table()
    failures = []
    for cid in _live_ids(cache):
        chara = character_data.get(cid)
        if chara is None:
            continue
        behavior = activity.behavior(chara.cid)
        behavior_id = getattr(behavior, "behavior_id", None)
        if behavior_id in config_behavior:
            continue
        failures.append(
            make_failure(
                "BEHAV-08",
                "当前行为id必须已注册",
                f"角色cid={cid}(name={getattr(chara, 'name', '?')!r})的behavior.behavior_id={behavior_id!r}"
                f"未在game_config.config_behavior中注册，直接下标会KeyError；state={activity.state(chara.cid)!r}, "
                f"last_behavior_id_list={activity.last_behaviors(chara.cid)!r}",
                [cid],
            )
        )
    return failures


@register_check("BEHAV-09", "运行中行为时长为非负整数")
def check_behavior_duration_non_negative_int() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure] -- 失败记录列表
    功能:
        校验每个被调度角色的behavior.duration是非负整数。负时长会让结束时间早于开始时间，负值源真实存在且
        未被钳制(助理同居睡眠duration = min_to_wake_time - 10没有下限)。不设上界：1440是经验值而非程序约束，
        睡眠时长由运行时算出；0是合法值(Behavior()默认、H中add_time==0的分支)
    """
    cache = cache_control.cache
    character_data = identity.table()
    failures = []
    for cid in _live_ids(cache):
        chara = character_data.get(cid)
        if chara is None:
            continue
        behavior = activity.behavior(chara.cid)
        duration = getattr(behavior, "duration", None)
        if type(duration) is int and duration >= 0:
            continue
        wake_time = action_info.get(chara.cid, "wake_time")
        failures.append(
            make_failure(
                "BEHAV-09",
                "运行中行为时长为非负整数",
                f"角色cid={cid}(name={getattr(chara, 'name', '?')!r})的behavior.duration={duration!r}不是非负整数"
                f"(不设上界)；behavior_id={getattr(behavior, 'behavior_id', None)!r}, "
                f"start_time={getattr(behavior, 'start_time', None)!r}, action_info.wake_time={wake_time!r}",
                [cid],
            )
        )
    return failures


@register_check("BEHAV-10", "活动角色的行为起时不得是哨兵")
def check_behavior_start_time_not_sentinel() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure] -- 失败记录列表
    功能:
        校验每个被调度角色的behavior.start_time不是哨兵0001-01-01。主循环在每个角色处理开头就会把哨兵修成
        玩家起时，钩子处仍见哨兵即意味着该角色被跳过。新开局不会误伤：角色初始化与新上线访客都会显式写入起时。
        字段类型损坏(BEHAV-07已报告)的角色本条跳过判定，避免时间比较异常
    """
    cache = cache_control.cache
    character_data = identity.table()
    sentinel = datetime.datetime(1, 1, 1)
    failures = []
    for cid in _live_ids(cache):
        chara = character_data.get(cid)
        if chara is None or not _behavior_type_ok(chara):
            continue
        behavior = activity.behavior(chara.cid)
        if behavior.start_time != sentinel:
            continue
        failures.append(
            make_failure(
                "BEHAV-10",
                "活动角色的行为起时不得是哨兵",
                (
                    f"角色cid={cid}(name={getattr(chara, 'name', '?')!r})的behavior.start_time仍是哨兵0001-01-01，"
                    f"说明该角色被主循环跳过未处理；behavior_id={behavior.behavior_id!r}, "
                    f"game_time={game_time.now()!r}"
                ),
                [cid],
            )
        )
    return failures


@register_check("BEHAV-11", "行为起时不得晚于游戏时间")
def check_behavior_start_time_not_future() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure] -- 失败记录列表
    功能:
        校验每个被调度角色的behavior.start_time不晚于game_time.now()。judge_character_status_time_over()
        开头会把未来的start_time无条件钳到当前时间，钩子处出现"起时在未来"意味着某条路径绕过了主循环。
        时停模式下整条跳过(不能只跳过玩家)：装袋释放/投监两条路径会在时停期间把NPC的start_time写成回退前的
        推进后时刻，随后主循环回退全局时钟，该NPC合法领先
    """
    cache = cache_control.cache
    if modes.time_stop():
        return []
    character_data = identity.table()
    game_t = game_time.now()
    failures = []
    for cid in _live_ids(cache):
        chara = character_data.get(cid)
        if chara is None or not _behavior_type_ok(chara):
            continue
        behavior = activity.behavior(chara.cid)
        try:
            ok = behavior.start_time <= game_t
        except Exception:
            continue
        if ok:
            continue
        failures.append(
            make_failure(
                "BEHAV-11",
                "行为起时不得晚于游戏时间",
                (
                    f"角色cid={cid}(name={getattr(chara, 'name', '?')!r})的behavior.start_time={behavior.start_time!r}"
                    f"晚于game_time.now()={game_t!r}；behavior_id={behavior.behavior_id!r}, "
                    f"duration={behavior.duration!r}, "
                    f"time_stop_mode={modes.time_stop()}"
                ),
                [cid],
            )
        )
    return failures


@register_check("BEHAV-12", "不得残留已过期的行为")
def check_no_stale_expired_behavior() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure] -- 失败记录列表
    功能:
        校验非H、duration>0的被调度角色，其行为结束时间END()不早于game_time.now()。主循环靠
        "结束时间已到就重跑一次"推进，钩子处不该再有结束时间早于当前时间的角色。必须用END()(get_sub_date)，
        不能用timedelta近似，跨季当天生产代码会把月份钳位、timedelta近似会稳定误报。非严格>=且不排除玩家：
        新开局全体角色是Behavior()默认值(duration 0)，部分路径会让玩家带着duration=5、
        start_time==game_time-5走到钩子，此时END==game_time恰好是合法边界。H中角色豁免、时停整条跳过；
        duration<=0被过滤：完成分支会把behavior重置为duration=0，属于合法终态
    """
    cache = cache_control.cache
    if modes.time_stop():
        return []
    character_data = identity.table()
    game_t = game_time.now()
    group_sex_mode = modes.group_sex()
    failures = []
    for cid in _live_ids(cache):
        chara = character_data.get(cid)
        if chara is None or not _behavior_type_ok(chara):
            continue
        is_h = flags.get(cid, "is_h")
        if is_h:
            continue
        behavior = activity.behavior(chara.cid)
        if behavior.duration <= 0:
            continue
        try:
            end_time = _end(chara)
            ok = end_time >= game_t
        except Exception:
            continue
        if ok:
            continue
        failures.append(
            make_failure(
                "BEHAV-12",
                "不得残留已过期的行为",
                (
                    f"角色cid={cid}(name={getattr(chara, 'name', '?')!r})的行为已过期未被结算："
                    f"behavior_id={behavior.behavior_id!r}, "
                    f"start_time={behavior.start_time!r}, duration={behavior.duration!r}, END={end_time!r} < "
                    f"game_time={game_t!r}；"
                    f"is_h={is_h}, unconscious_h={flags.get(cid, 'unconscious_h')}, "
                    f"time_stop_mode={modes.time_stop()}, group_sex_mode={group_sex_mode}, "
                    f"target_character_id={activity.target(chara.cid)}"
                ),
                [cid],
            )
        )
    return failures


# BEHAV-13（已删除，2026-08-31）：曾断言"behavior_id为share_blankly、非H的角色，state必须落在
# (0, 'share_blankly')两个空闲哨兵值之内"。用户裁定该断言结构性过严：生产代码合法存在的一阶段等待过渡——
# behavior已经重置为share_blankly、但state尚未同步到空闲哨兵值——会被误报为异常，而这只是同一次结算内
# 两个字段先后落地的正常中间态，不是脱节故障。不做收窄，直接删除。


@register_check("BEHAV-14", "移动行为必须带着可执行的路径")
def check_move_behavior_has_executable_path() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure] -- 失败记录列表
    功能:
        校验behavior_id为move的角色带着可执行的路径快照。玩家指令记录会无保护地取
        move_src[-1]/move_target[-1]，末项为"0"时还取[-2]，空列表直接IndexError；正常寻路只在
        move_time>0时提交移动，零时长空路径属于非法快照。move_src只对玩家(cid==0)要求：NPC通用移动只写
        move_target/move_final_target，消费move_src的函数只对0号调用。不加state白名单：
        judge_same_position_npc_follow提交move时完全不写state，跟随者会带着state==0通过钩子。
        duration>0对H角色豁免：寻路失败时非H角色会被重置后重跑，H角色可能被H捷径保留
    """
    cache = cache_control.cache
    character_data = identity.table()
    failures = []
    for cid in _live_ids(cache):
        chara = character_data.get(cid)
        if chara is None:
            continue
        behavior = activity.behavior(chara.cid)
        if getattr(behavior, "behavior_id", None) != "move":
            continue
        is_h = flags.get(cid, "is_h")
        duration = getattr(behavior, "duration", None)
        move_target = getattr(behavior, "move_target", None)
        move_src = getattr(behavior, "move_src", None)
        problems = []
        target_ok = (
            isinstance(move_target, list)
            and len(move_target) >= 1
            and all(isinstance(x, str) for x in move_target)
        )
        if not target_ok:
            problems.append(f"move_target非法: {move_target!r}")
        if not (is_h or (type(duration) is int and duration > 0)):
            problems.append(f"非H角色但duration不为正: duration={duration!r}")
        # target_ok为真即已确认move_target是list，这里重复判断只为让类型收窄
        if (
            target_ok
            and isinstance(move_target, list)
            and move_target[-1] == "0"
            and len(move_target) < 2
        ):
            problems.append(
                f"move_target末项为哨兵'0'且长度不足2，取[-2]会IndexError: move_target={move_target!r}"
            )
        if cid == 0:
            src_ok = isinstance(move_src, list) and len(move_src) >= 1
            if not src_ok:
                problems.append(f"玩家move_src非法: {move_src!r}")
            # src_ok为真即已确认move_src是list，这里重复判断只为让类型收窄
            elif (
                isinstance(move_src, list)
                and move_src[-1] == "0"
                and len(move_src) < 2
            ):
                problems.append(
                    f"玩家move_src末项为哨兵'0'且长度不足2: move_src={move_src!r}"
                )
        if not problems:
            continue
        failures.append(
            make_failure(
                "BEHAV-14",
                "移动行为必须带着可执行的路径",
                (
                    f"角色cid={cid}(name={getattr(chara, 'name', '?')!r})的move行为快照非法：{'; '.join(problems)}；"
                    f"position={activity.position(chara.cid)!r}, "
                    f"move_final_target={getattr(behavior, 'move_final_target', None)!r}, "
                    f"duration={duration!r}, state={activity.state(chara.cid)!r}, "
                    f"is_follow={flags.get(cid, 'is_follow')!r}"
                ),
                [cid],
            )
        )
    return failures


@register_check("BEHAV-15", '"谁在跟我互动"的记录必须指向真实角色')
def check_interacting_character_end_info_valid() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure] -- 失败记录列表
    功能:
        校验每个角色的action_info.interacting_character_end_info[0]（结算交互行为时写进对方的"发起方id"）
        要么是哨兵-1，要么指向身份表（identity.characters）中存在的角色。旧存档id重映射可能让这个字段失效，
        报出的悬空id是迁移缺陷信号，不加豁免。与CORE-02不重复：CORE-02查的是activity.target
    """
    cache = cache_control.cache
    character_data = identity.table()
    failures = []
    for cid in _live_ids(cache):
        chara = character_data.get(cid)
        if chara is None:
            continue
        info = action_info.get(cid, "interacting_character_end_info")
        if not (isinstance(info, (list, tuple)) and len(info) >= 1):
            continue
        other_id = info[0]
        if other_id == -1 or other_id in character_data:
            continue
        failures.append(
            make_failure(
                "BEHAV-15",
                '"谁在跟我互动"的记录必须指向真实角色',
                (
                    f"角色cid={cid}(name={getattr(chara, 'name', '?')!r})的action_info.interacting_character_end_info="
                    f"{info!r}指向的角色id={other_id!r}既不是哨兵-1也不在character_data中；"
                    f"game_time={game_time.now()!r}, "
                    f"character_data键(前20个)={sorted(character_data.keys())[:20]}"
                ),
                [cid],
            )
        )
    return failures


@register_check("BEHAV-16", "生效中的身体道具不得已过期")
def check_active_body_item_not_expired() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure] -- 失败记录列表
    功能:
        校验h_state.body_item中"生效中(item[1]为真)"的道具，其结束时间item[2]要么为None要么晚于
        game_time.now()。每个参与结算的角色每轮都会跑一次持续状态结算，H中结算全部部位、非H只结算8号
        (持续性利尿剂)与9号(安眠药)，结束时间已到(相等也算到期)的置为失效；钩子处还留着"生效中+结束时间≤当前
        时间"说明该角色本轮没被结算到。非H时必须收窄到8/9，否则会把"H中挂上、退出H后自然留存"的道具误报成脏数据。
        时停模式下只查玩家：NPC本轮完全未结算持续状态。比较用严格>：生产用judge_date_big_or_small判到期，
        相等返回2(真)，即item[2]<=game_time才算过期
    """
    cache = cache_control.cache
    character_data = identity.table()
    time_stop = modes.time_stop()
    game_t = game_time.now()
    failures = []
    for cid in _live_ids(cache):
        if time_stop and cid != 0:
            continue
        chara = character_data.get(cid)
        if chara is None:
            continue
        hs = h_state.view(cid)
        body_item = getattr(hs, "body_item", None)
        if not isinstance(body_item, dict):
            continue
        is_h = flags.get(cid, "is_h")
        indices = range(len(body_item)) if is_h else (8, 9)
        for i in indices:
            if i not in body_item:
                continue
            item = body_item[i]
            try:
                item_name, active, end_time = item[0], item[1], item[2]
            except Exception:
                continue
            if not active:
                continue
            if end_time is None or end_time > game_t:
                continue
            failures.append(
                make_failure(
                    "BEHAV-16",
                    "生效中的身体道具不得已过期",
                    f"角色cid={cid}(name={getattr(chara, 'name', '?')!r})部位{i}({item_name!r})生效中(active=True)"
                    f"但结束时间{end_time!r}已<=当前game_time={game_t!r}，说明该角色本轮未被结算到；"
                    f"is_h={is_h}, unconscious_h={flags.get(cid, 'unconscious_h')}, time_stop_mode={time_stop}",
                    [cid],
                )
            )
    return failures


@register_check("BEHAV-17", "二段行为取值与待结算id合法")
def check_second_behavior_values_and_pending_ids() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure] -- 失败记录列表
    功能:
        校验activity.second_behaviors(二段行为id→0/1触发标记字典)的取值只能是0或1的int，以及
        activity.must_settle/activity.must_show两个待处理id列表中的每个id都在
        game_config.config_behavior_effect_data中——must_settle_check()与must_show_talk_check()都会无保护地
        下标该配表，键错即KeyError。不要求二段行为的键都在效果配表里(普通路径对未知键是continue)；
        不要求待处理id在二段行为里有非0值(两个消费函数读到0时跳过这个id)；
        不要求钩子处所有值都为0(可以在结算之外置1，残留的1是合法中间态)。只查取值类型，不查键类型：
        旧存档可能带int键。配表未加载时，待结算id合法性部分降级为跳过
    """
    cache = cache_control.cache
    character_data = identity.table()
    config_effect = getattr(game_config, "config_behavior_effect_data", None)
    failures = []
    for cid in _live_ids(cache):
        chara = character_data.get(cid)
        if chara is None:
            continue
        second_behavior = activity.second_behaviors(chara.cid)
        try:
            values = list(second_behavior.values())
        except Exception:
            values = []
        must_settle = activity.must_settle(chara.cid)
        must_show = activity.must_show(chara.cid)
        behavior_id = getattr(activity.behavior(chara.cid), "behavior_id", None)
        is_h = flags.get(chara.cid, "is_h")
        for v in values:
            if type(v) is int and v in (0, 1):
                continue
            failures.append(
                make_failure(
                    "BEHAV-17",
                    "二段行为取值与待结算id合法",
                    (
                        f"角色cid={cid}(name={getattr(chara, 'name', '?')!r})的second_behavior存在非法取值v={v!r}"
                        f"(type={type(v).__name__})，要求type是int且取值只能是0或1；"
                        f"must_settle_second_behavior_id_list={must_settle!r}, must_show_second_behavior_id_list="
                        f"{must_show!r}, "
                        f"behavior_id={behavior_id!r}, is_h={is_h}"
                    ),
                    [cid],
                )
            )
        if not config_effect:
            continue  # 效果配表未加载，降级为跳过待结算id合法性部分
        for bid in list(must_settle) + list(must_show):
            if bid in config_effect:
                continue
            failures.append(
                make_failure(
                    "BEHAV-17",
                    "二段行为取值与待结算id合法",
                    f"角色cid={cid}(name={getattr(chara, 'name', '?')!r})的待处理二段行为id={bid!r}不在"
                    f"game_config.config_behavior_effect_data中，must_settle_check()/must_show_talk_check()会"
                    f"无保护KeyError；must_settle_second_behavior_id_list={must_settle!r}, "
                    f"must_show_second_behavior_id_list={must_show!r}, behavior_id={behavior_id!r}, is_h={is_h}",
                    [cid],
                )
            )
    return failures


@register_check("BEHAV-18", "行为历史队列有界且条目可比")
def check_last_behavior_id_list_bounded() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure] -- 失败记录列表
    功能:
        校验last_behavior_id_list是长度在[1,5]的list，且每个元素要么是0要么是字符串。初值[0]，完成行为时
        追加并裁到5，是全仓库唯一写入点。定为warning而非error：旧存档迁移原样复制列表且不裁剪，超长列表每轮只
        缩短1项，会连续多个合法回合告警。不加x in game_config.config_behavior成员校验(旧存档必然噪声)；
        不并入全局键 log.instructions 的 recent(它没有任何读档裁剪路径)
    """
    cache = cache_control.cache
    character_data = identity.table()
    failures = []
    for cid in _live_ids(cache):
        chara = character_data.get(cid)
        if chara is None:
            continue
        lst = activity.last_behaviors(chara.cid)
        ok = (
            isinstance(lst, list)
            and 1 <= len(lst) <= 5
            and all(x == 0 or isinstance(x, str) for x in lst)
        )
        if ok:
            continue
        behavior_id = getattr(activity.behavior(chara.cid), "behavior_id", None)
        length = len(lst) if isinstance(lst, list) else None
        failures.append(
            make_failure(
                "BEHAV-18",
                "行为历史队列有界且条目可比",
                f"[warning] 角色cid={cid}(name={getattr(chara, 'name', '?')!r})的last_behavior_id_list={lst!r}"
                f"(长度{length})不满足'非空列表、长度<=5、元素为0或字符串'；"
                f"behavior_id={behavior_id!r}",
                [cid],
            )
        )
    return failures


@register_check("BEHAV-19", "时停中玩家必须处于时停无意识态")
def check_time_stop_player_unconscious() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure] -- 失败记录列表
    功能:
        校验time_stop_mode为真时，0号玩家的sp_flag.unconscious_h必须等于3(时停语义)。开启时停会把玩家与
        全体已获得干员置3，关闭时置0；玩家这一侧脱节说明时停开关只跑了一半。只保留玩家单向：不扩展到全体NPC
        的双向一致性，时停期间角色上线有多个入口，只有装袋释放/投监两条显式补写3，其他入口直接重置sp_flag，
        NPC侧差异只适合另做告警
    """
    cache = cache_control.cache
    if not modes.time_stop():
        return []
    character_data = identity.table()
    player = character_data.get(0)
    if player is None:
        return []
    u = flags.get(0, "unconscious_h")
    if u == 3:
        return []
    unconscious_npcs = []
    for cid in _live_ids(cache):
        other = character_data.get(cid)
        if other is not None and flags.get(cid, "unconscious_h") == 3:
            unconscious_npcs.append(cid)
        if len(unconscious_npcs) >= 10:
            break
    return [
        make_failure(
            "BEHAV-19",
            "时停中玩家必须处于时停无意识态",
            (
                f"[warning] time_stop_mode=True但0号玩家sp_flag.unconscious"
                f"_h={u!r}"
                f"!=3，时停开关可能只跑了一半；is_h={flags.get(0, 'is_h')}, "
                f"已置3的NPC样本(至多10个)={unconscious_npcs}, "
                f"time_stop_duration={achievement.get('time_stop_duration')!r}"
            ),
            [0],
        )
    ]


@register_check("BEHAV-20", "群交模式必须有玩家在H中")
def check_group_sex_mode_player_in_h() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure] -- 失败记录列表
    功能:
        校验cache.group_sex_mode为真时，0号玩家的sp_flag.is_h必须为真。群交是玩家主导的H场景，标记为真但
        玩家不在H意味着模式泄漏，之后NPC的AI会一直走群交分支。级别为warning：GROUP_SEX_MODE_OFF是配表驱动的
        结算效果，能结束群交的行为是否都挂了该效果并无逐条保证，可能存在合法但暂时不同步的窗口。隐奸把玩家
        is_h清零的路径用的是hidden_sex_mode而非group_sex_mode，不构成本条反例
    """
    cache = cache_control.cache
    if not modes.group_sex():
        return []
    character_data = identity.table()
    player = character_data.get(0)
    if player is None:
        return []
    if flags.get(0, "is_h"):
        return []
    h_npcs = []
    for cid in _live_ids(cache):
        other = character_data.get(cid)
        if other is not None and flags.get(cid, "is_h"):
            h_npcs.append(cid)
        if len(h_npcs) >= 10:
            break
    return [
        make_failure(
            "BEHAV-20",
            "群交模式必须有玩家在H中",
            f"[warning] mode.group_sex=True但0号玩家sp_flag.is_h=False，模式可能已泄漏，NPC的AI会一直走"
            f"群交分支；behavior_id={getattr(activity.behavior(player.cid), 'behavior_id', None)!r}, "
            f"当前在H中的角色样本(至多10个)={h_npcs}, time_stop_mode={modes.time_stop()}",
            [0],
        )
    ]


@register_check("BEHAV-22", "行为起时落在四季月上")
def check_behavior_start_time_seasonal_month() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure] -- 失败记录列表
    功能:
        校验每个被调度角色(排除哨兵值)的behavior.start_time月份属于四季月{3,6,9,12}。start_time的所有来源
        要么是game_time.now()的拷贝，要么是get_sub_date的输出，因此继承BEHAV-03的月份约束。显式排除哨兵，
        以免与BEHAV-10双重报警。级别为warning：保留的价值在于旧存档迁移会原样复制整个behavior对象，是唯一可能
        带进历史月份的通道，读档后、任何一次结算之前的窗口内触发属于迁移问题而非运行期缺陷
    """
    cache = cache_control.cache
    character_data = identity.table()
    sentinel = datetime.datetime(1, 1, 1)
    failures = []
    for cid in _live_ids(cache):
        chara = character_data.get(cid)
        if chara is None or not _behavior_type_ok(chara):
            continue
        behavior = activity.behavior(chara.cid)
        if behavior.start_time == sentinel:
            continue
        if behavior.start_time.month in {3, 6, 9, 12}:
            continue
        failures.append(
            make_failure(
                "BEHAV-22",
                "行为起时落在四季月上",
                f"[warning] 角色cid={cid}(name={getattr(chara, 'name', '?')!r})的behavior.start_time="
                f"{behavior.start_time!r}月份不属于四季月{{3,6,9,12}}，疑似旧存档迁移带入的历史月份；"
                f"behavior_id={behavior.behavior_id!r}, game_time={game_time.now()!r}",
                [cid],
            )
        )
    return failures
