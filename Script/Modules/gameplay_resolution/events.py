"""
gameplay_resolution 的事件
==========================
疲劳、跟随、H 结束与睡中被吵醒是内核事件（core.event）：条件读缓存，内核每一步对每个角色检查；
结算当场写缓存、画字，接着要做的行动经计划队列（plan_queue.plan_next）排给对应角色，在他下一次选行动时开始，
要结束谁的行动就经计划队列打断他（plan_queue.interrupt），不在结算里嵌套另一次结算。
排下的打断在这一步的 ApplyEffects 里生效（plan_queue.drain），所以事件交回空的效果即可。
每个条件都带"还没排上"的检查（plan_queue.plan_has），排上之后不再成立。

内核每一步只结算一个事件：先按注册顺序、再按角色顺序找第一个成立的。注册顺序因此有意义：
H 结束排在停止跟随之前；actions 先导入，它的事件（Tick、NewDay、ActionOver）排在这里的事件之前。

两个事件互相让对方成立时，内核会在同一时刻无限循环。第一个注册的事件 CycleGuard 从不成立，
它的条件只数内核扫描事件条件的次数：两次行动开始或时间流逝之间超过 SCAN_LIMIT 次时抛 EventCycle。
"""

from types import FunctionType

from Script.Core import cache_control, constant, game_type, get_text, num
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions, plan_queue

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
_: FunctionType = get_text._
""" 翻译api """

SCAN_LIMIT = 2000
""" 两次行动开始或时间流逝之间，内核扫描事件条件的最多次数 """
scans = 0
""" 上一次行动开始或时间流逝以来，内核扫描事件条件的次数 """


def forget() -> None:
    """丢掉睡中被吵醒、还没结算的角色"""
    cache.noise_woken.clear()


@core.output_hook(core.reset)
def reset_scans(game: core.GameState) -> core.GameState:
    """
    kernel.Reset 的输出钩子：换了 GameState 后扫描计数清零
    Keyword arguments:
    game -- 新的 GameState
    Return arguments:
    GameState -- 原样交回
    """
    global scans
    scans = 0
    return game


class EventCycle(RuntimeError):
    """事件互相让对方成立，同一时刻无限循环"""


def _scanned(game: core.GameState, who: str) -> bool:
    """
    CycleGuard 的条件：内核每扫描一遍事件条件，对第一个角色调用一次，借此计数；从不成立
    Keyword arguments:
    game -- 当前的 GameState
    who -- 角色键
    Return arguments:
    bool -- 假
    """
    global scans
    if who == next(iter(game.characters)):
        scans += 1
        if scans > SCAN_LIMIT:
            raise EventCycle(
                f"两次行动之间事件条件扫描了 {scans} 次：事件互相让对方成立"
            )
    return False


@core.event("gameplay_resolution.events.CycleGuard", _scanned)
def cycle_guard(who: str) -> core.Effects:
    """
    循环守卫：条件从不成立，不会结算
    Keyword arguments:
    who -- 角色键
    Return arguments:
    Effects -- 空
    """
    return ()


@core.input_hook(core.start_action)
def reset_on_start(act: core.Action) -> tuple[core.Action]:
    """
    行动开始：扫描计数清零
    Keyword arguments:
    act -- 要开始的行动
    Return arguments:
    tuple -- 原样交给内层的参数
    """
    global scans
    scans = 0
    return (act,)


@core.input_hook(core.time_elapse)
def reset_on_elapse(start: int, end: int) -> tuple[int, int]:
    """
    时间流逝：扫描计数清零
    Keyword arguments:
    start -- 流逝前的时钟
    end -- 流逝到的时钟
    Return arguments:
    tuple -- 原样交给内层的参数
    """
    global scans
    scans = 0
    return (start, end)


def _npc(who: str) -> game_type.Character | None:
    """
    干员事件条件的共同前提：是干员、没死、不在时停中（时停中干员不结算）
    Keyword arguments:
    who -- 角色键
    Return arguments:
    Character | None -- 满足时为干员的数据
    """
    if who == actions.PLAYER or cache.time_stop_mode:
        return None
    character_data: game_type.Character = cache.character_data[int(who)]
    return None if character_data.dead else character_data


def tired_case(character_id: int) -> str | None:
    """
    疲劳或困倦的干员在 H 或跟随中时该怎么收场
    Keyword arguments:
    character_id -- 干员id
    Return arguments:
    str | None -- "follow" 停止跟随，"group" 退出群交，"h" 结束 H，None 不用收场
    （已排上力竭退出群交的干员，退出开始前群交可能已经转成普通 H，这时也不用收场）
    """
    from Script.Design import attr_calculation

    character_data: game_type.Character = cache.character_data[character_id]
    flag = character_data.sp_flag
    if not (flag.is_h or flag.is_follow):
        return None
    if plan_queue.plan_has(
        character_id, constant.Behavior.GROUP_SEX_NPC_HP_0_END
    ):
        return None
    if not (
        flag.tired
        or attr_calculation.get_tired_level(
            num.whole(character_data.tired_point)
        )
        >= 2
    ):
        return None
    if (
        flag.is_follow
        and character_data.behavior.behavior_id != constant.Behavior.WAIT
    ):
        return "follow"
    if cache.group_sex_mode and flag.is_h:
        return "group"
    if flag.is_h and (not flag.unconscious_h or character_data.hit_point <= 1):
        return "h"
    return None


def _become_tired_when(game: core.GameState, who: str) -> bool:
    """
    R1 的条件：干员体力到 1 而还没疲劳
    Keyword arguments:
    game -- 当前的 GameState
    who -- 角色键
    Return arguments:
    bool -- 成立时为真
    """
    character_data = _npc(who)
    return (
        character_data is not None
        and character_data.hit_point <= 1
        and not character_data.sp_flag.tired
    )


@core.event("gameplay_resolution.events.BecomeTired", _become_tired_when)
def become_tired(who: str) -> core.Effects:
    """
    R1 BecomeTired：干员疲劳
    Keyword arguments:
    who -- 角色键
    Return arguments:
    Effects -- 空
    """
    character_id = int(who)
    cache.character_data[character_id].sp_flag.tired = True
    return ()


def _player_spent_when(game: core.GameState, who: str) -> bool:
    """
    R5 的条件：玩家体力到 1 而还在 H 或群交中，玩家的队列里还没排着任何 H 或群交的结束
    （排着别的结束时 plan_h_end 与 plan_group_sex_end 什么也不排，条件就会一直成立）
    Keyword arguments:
    game -- 当前的 GameState
    who -- 角色键
    Return arguments:
    bool -- 成立时为真
    """
    if who != actions.PLAYER:
        return False
    character_data: game_type.Character = cache.character_data[0]
    if character_data.hit_point > 1:
        return False
    target_data = cache.character_data[character_data.target_character_id]
    if not (cache.group_sex_mode or target_data.sp_flag.is_h):
        return False
    ends = {
        constant.Behavior.END_H,
        constant.Behavior.GROUP_SEX_END,
        *constant.special_end_H_list,
    }
    return not any(p["behavior_id"] in ends for p in plan_queue.planned(0))


@core.event("gameplay_resolution.events.PlayerSpent", _player_spent_when)
def player_spent(who: str) -> core.Effects:
    """
    R5 PlayerSpent：玩家力竭，群交或 H 结束；玩家的结束行动排进队列
    Keyword arguments:
    who -- 角色键
    Return arguments:
    Effects -- 交互对象们的打断
    """
    from Script.System.Instruct_System import handle_instruct

    character_id = int(who)
    character_data: game_type.Character = cache.character_data[character_id]
    if character_data.sp_flag.is_h:
        _draw(character_data.name + _("太累了，无法继续H\n"))
    character_data.sp_flag.tired = False
    if cache.group_sex_mode:
        return handle_instruct.plan_group_sex_end(
            constant.Behavior.GROUP_SEX_PL_HP_0_END
        )
    return handle_instruct.plan_h_end(constant.Behavior.H_HP_0)


def _h_end_when(game: core.GameState, who: str) -> bool:
    """
    R4 的条件：H 中的干员疲劳，玩家的力竭结束还没排上
    Keyword arguments:
    game -- 当前的 GameState
    who -- 角色键
    Return arguments:
    bool -- 成立时为真
    """
    return (
        _npc(who) is not None
        and tired_case(int(who)) == "h"
        and not plan_queue.plan_has(0, constant.Behavior.T_H_HP_0)
    )


@core.event("gameplay_resolution.events.HEnd", _h_end_when)
def h_end(who: str) -> core.Effects:
    """
    R4 HEnd：干员太累，H 结束；玩家的 T_H_HP_0 排进队列
    Keyword arguments:
    who -- 角色键
    Return arguments:
    Effects -- 交互对象的打断
    """
    from Script.System.Instruct_System import handle_instruct

    character_id = int(who)
    character_data: game_type.Character = cache.character_data[character_id]
    character_data.sp_flag.is_h = False
    _draw(character_data.name + _("太累了，H 结束\n"))
    return handle_instruct.plan_h_end(constant.Behavior.T_H_HP_0)


def _group_exit_when(game: core.GameState, who: str) -> bool:
    """
    R3 的条件：群交中的干员疲劳，退出行动还没排上（排上后 tired_case 为 None）
    Keyword arguments:
    game -- 当前的 GameState
    who -- 角色键
    Return arguments:
    bool -- 成立时为真
    """
    return _npc(who) is not None and tired_case(int(who)) == "group"


@core.event("gameplay_resolution.events.GroupExit", _group_exit_when)
def group_exit(who: str) -> core.Effects:
    """
    R3 GroupExit 与 R7 GroupShrinks：干员力竭退出群交，剩下的人数决定群交是转成普通 H 还是结束
    Keyword arguments:
    who -- 角色键
    Return arguments:
    Effects -- 空（排给别人的打断由计划队列交回内核）
    """
    from Script.Design import handle_npc_ai

    character_id = int(who)
    handle_npc_ai.commit_group_sex_tired_exit(character_id)
    return ()


def _stop_following_when(game: core.GameState, who: str) -> bool:
    """
    R2 的条件：跟随中的干员疲劳或困倦
    Keyword arguments:
    game -- 当前的 GameState
    who -- 角色键
    Return arguments:
    bool -- 成立时为真
    """
    return _npc(who) is not None and tired_case(int(who)) == "follow"


@core.event("gameplay_resolution.events.StopFollowing", _stop_following_when)
def stop_following(who: str) -> core.Effects:
    """
    R2 StopFollowing：干员太累或太困，不再跟随
    Keyword arguments:
    who -- 角色键
    Return arguments:
    Effects -- 空
    """
    character_id = int(who)
    character_data: game_type.Character = cache.character_data[character_id]
    text = (
        _("太累了，无法继续跟随\n")
        if character_data.sp_flag.tired
        else _("太困了，无法继续跟随\n")
    )
    _draw(character_data.name + text)
    character_data.sp_flag.is_follow = 0
    return ()


def _h_left_behind_when(game: core.GameState, who: str) -> bool:
    """
    HLeftBehind 的条件：玩家离开了场景，留下的干员还在 H、睡奸、空气催眠、隐奸或露出中
    （隐奸携带模式中被携带的角色除外）
    Keyword arguments:
    game -- 当前的 GameState
    who -- 角色键
    Return arguments:
    bool -- 成立时为真
    """
    from Script.Design import handle_premise

    character_data = _npc(who)
    if character_data is None:
        return False
    flag = character_data.sp_flag
    if flag.hidden_sex_mode == 5:
        return False
    air = (
        flag.unconscious_h == 5
        and character_data.position
        != cache.character_data[0].pl_ability.air_hypnosis_position
    )
    if not (
        flag.is_h
        or flag.unconscious_h == 1
        or air
        or flag.hidden_sex_mode > 0
        or flag.exhibitionism_sex_mode > 0
    ):
        return False
    return bool(handle_premise.handle_not_in_player_scene(int(who)))


@core.event("gameplay_resolution.events.HLeftBehind", _h_left_behind_when)
def h_left_behind(who: str) -> core.Effects:
    """
    HLeftBehind：玩家离开后，留下的干员的 H 与各种性爱模式结束
    Keyword arguments:
    who -- 角色键
    Return arguments:
    Effects -- 空（H 中的干员排上结束 H 并被打断，由计划队列交给内核）
    """
    from Script.Design import handle_npc_ai_in_h

    handle_npc_ai_in_h.end_h_left_behind(int(who))
    return ()


def _woken_by_noise_when(game: core.GameState, who: str) -> bool:
    """
    WokenByNoise 的条件：时间结算掷骰判定这个角色被吵醒了
    Keyword arguments:
    game -- 当前的 GameState
    who -- 角色键
    Return arguments:
    bool -- 成立时为真
    """
    return int(who) in cache.noise_woken


@core.event("gameplay_resolution.events.WokenByNoise", _woken_by_noise_when)
def woken_by_noise(who: str) -> core.Effects:
    """
    WokenByNoise：睡着的角色被动静吵醒
    Keyword arguments:
    who -- 角色键
    Return arguments:
    Effects -- 空（被吵醒的角色的打断由计划队列在这一步交给内核）
    """
    from Script.Design import handle_npc_ai_in_h

    character_id = int(who)
    handle_npc_ai_in_h.wake_by_noise(
        cache.noise_woken.pop(character_id), character_id
    )
    return ()


def _draw(text: str) -> None:
    """
    画一行要玩家确认的文本
    Keyword arguments:
    text -- 文本
    """
    from Script.Config import normal_config
    from Script.UI.Moudle import draw

    now_draw = draw.WaitDraw()
    now_draw.width = normal_config.config_normal.text_width
    now_draw.text = text
    now_draw.draw()
