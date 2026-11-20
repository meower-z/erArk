"""
gameplay_resolution 的事件
==========================
疲劳、跟随与 H 结束是内核事件（core.event）：触发函数读缓存，按名单顺序检查干员，交回第一个成立的角色键；
结算当场写缓存、画字，接着要做的行动经计划队列（plan_queue.plan_next）排给对应角色，在他下一次选行动时开始，
要结束谁的行动就经计划队列打断他（plan_queue.interrupt），不在结算里嵌套另一次结算。
排下的打断在这一步的 ApplyEffects 里生效（plan_queue.drain），所以事件交回空的效果即可。
每个条件都带"还没排上"的检查（plan_queue.plan_has），排上之后不再成立。

内核不保证同时成立的事件的先后，要先等另一个事件的，前提写在触发函数里：
每个事件等这一分钟的 Tick 与 NewDay（time_hooks.clock_settled）；给玩家排结束的 PlayerSpent、HEnd、GroupExit
等 ArtsBreak（time_hooks.arts_settled）；结束干员 H 的 HEnd、GroupExit、HLeftBehind 等玩家力竭（PlayerSpent）；
StopFollowing 等同一干员的 BecomeTired；HLeftBehind 等同一干员力竭的收场（tired_case）。
"""

from collections.abc import Callable
from types import FunctionType

from Script.Core import cache_control, constant, game_type, get_text, num
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions, plan_queue, time_hooks
from Script.Modules.domains import needs

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
_: FunctionType = get_text._
""" 翻译api """


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


def _first_npc(
    game: core.GameState, holds: Callable[[int], bool]
) -> str | None:
    """
    名单顺序里第一个满足 holds 的干员（没死、不在时停中）；这一分钟时钟的结算没跑完时谁都不算
    Keyword arguments:
    game -- 当前的 GameState
    holds -- 收到干员id，成立时为真
    Return arguments:
    str | None -- 角色键，没有时为 None
    """
    if not time_hooks.clock_settled(game):
        return None
    for who in game.characters:
        if _npc(who) is not None and holds(int(who)):
            return who
    return None


def _becomes_tired(character_id: int) -> bool:
    """
    BecomeTired 对这个干员成立：体力到 1 而还没疲劳
    Keyword arguments:
    character_id -- 干员id
    Return arguments:
    bool -- 成立时为真
    """
    character_data: game_type.Character = cache.character_data[character_id]
    return character_data.hit_point <= 1 and not character_data.sp_flag.tired


def tired_case(character_id: int, game: core.GameState) -> str | None:
    """
    疲劳或困倦的干员在 H 或跟随中时该怎么收场
    Keyword arguments:
    character_id -- 干员id
    game -- 触发函数收到的 GameState，疲劳从它读
    Return arguments:
    str | None -- "follow" 停止跟随，"group" 退出群交，"h" 结束 H，None 不用收场。
    已排上力竭退出群交的干员也是 None，因为退出开始前群交可能已经转成普通 H
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
            num.whole(needs.of(character_id, game)["tired"])
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


def _become_tired_when(game: core.GameState) -> str | None:
    """
    R1 的触发：干员体力到 1 而还没疲劳
    Keyword arguments:
    game -- 当前的 GameState
    Return arguments:
    str | None -- 第一个成立的干员的键
    """
    return _first_npc(game, _becomes_tired)


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


def _player_spent(game: core.GameState) -> bool:
    """
    玩家力竭：体力到 1 而还在 H 或群交中，玩家的队列里还没排着任何 H 或群交的结束
    （排着别的结束时 plan_h_end 与 plan_group_sex_end 什么也不排，所以排着就算已收场）
    Keyword arguments:
    game -- 当前的 GameState
    Return arguments:
    bool -- 成立时为真
    """
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


def _player_spent_when(game: core.GameState) -> str | None:
    """
    R5 的触发：玩家力竭，在这一分钟时钟的结算与源石技艺中断之后
    Keyword arguments:
    game -- 当前的 GameState
    Return arguments:
    str | None -- 成立时为玩家的键
    """
    if (
        time_hooks.clock_settled(game)
        and time_hooks.arts_settled(game)
        and _player_spent(game)
    ):
        return actions.PLAYER
    return None


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


def _h_end_when(game: core.GameState) -> str | None:
    """
    R4 的触发：H 中的干员疲劳，玩家的 T_H_HP_0 还没排上；在源石技艺中断与玩家力竭之后
    Keyword arguments:
    game -- 当前的 GameState
    Return arguments:
    str | None -- 第一个成立的干员的键
    """
    if (
        not time_hooks.arts_settled(game)
        or _player_spent(game)
        or plan_queue.plan_has(0, constant.Behavior.T_H_HP_0)
    ):
        return None
    return _first_npc(game, lambda cid: tired_case(cid, game) == "h")


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


def _group_exit_when(game: core.GameState) -> str | None:
    """
    R3 的触发：群交中的干员疲劳，退出行动还没排上（排上后 tired_case 为 None）；在源石技艺中断与玩家力竭之后
    Keyword arguments:
    game -- 当前的 GameState
    Return arguments:
    str | None -- 第一个成立的干员的键
    """
    if not time_hooks.arts_settled(game) or _player_spent(game):
        return None
    return _first_npc(game, lambda cid: tired_case(cid, game) == "group")


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


def _stop_following_when(game: core.GameState) -> str | None:
    """
    R2 的触发：跟随中的干员疲劳或困倦，且他的 BecomeTired 已结算（疲劳标记决定说"太累"还是"太困"）
    Keyword arguments:
    game -- 当前的 GameState
    Return arguments:
    str | None -- 第一个成立的干员的键
    """
    return _first_npc(
        game,
        lambda cid: not _becomes_tired(cid)
        and tired_case(cid, game) == "follow",
    )


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


def _h_left_behind_when(game: core.GameState) -> str | None:
    """
    HLeftBehind 的触发：玩家离开了场景，留下的干员还在 H、睡奸、空气催眠、隐奸或露出中
    （隐奸携带模式中被携带的角色除外）；在玩家力竭与这个干员力竭的收场（tired_case）之后
    Keyword arguments:
    game -- 当前的 GameState
    Return arguments:
    str | None -- 第一个成立的干员的键
    """
    if _player_spent(game):
        return None
    return _first_npc(game, lambda cid: _left_behind(cid, game))


def _left_behind(character_id: int, game: core.GameState) -> bool:
    """
    这个干员被留在 H 里：玩家离开了场景，干员还在 H 或某种性爱模式中，且没有要先收场的疲劳
    Keyword arguments:
    character_id -- 干员id
    game -- 触发函数收到的 GameState，交给 tired_case
    Return arguments:
    bool -- 成立时为真
    """
    from Script.Design import handle_premise

    if tired_case(character_id, game) is not None:
        return False
    character_data: game_type.Character = cache.character_data[character_id]
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
    return bool(handle_premise.handle_not_in_player_scene(character_id))


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
