# -*- coding: UTF-8 -*-
"""
显示与跳过的判据：口上直显/缓冲/吞掉、模板派发、玩家真实指令、波及全体的指令族、寸止断因来源

判据只读 state.turn 与传入的值；用到的本体常量在第一次调用时才 import 并缓存，
因为 mod 加载时本体常量模块未必已经导入。
"""
from typing import Callable

from . import state

TALK_PASS = "pass"
""" 口上直接显示 """
TALK_BUFFER = "buffer"
""" 口上进回放队列，摘要页之后显示 """
TALK_DROP = "drop"
""" 口上吞掉，不显示也不回放 """

_talk_whitelist_cache = None
""" 口上白名单行为id集合（懒加载） """
_mass_end_cache = None
""" 结束族行为id集合（懒加载） """
_mass_toy_cache = None
""" 全员玩具族行为id集合（懒加载） """


def talk_whitelist() -> set:
    """
    口上白名单：结束群交（正常/异常/太累）与加入、受邀、发现群交。这些口上要让玩家看到，但放到摘要页之后
    Keyword arguments:
    无
    Return arguments:
    set -- 行为id集合
    """
    global _talk_whitelist_cache
    if _talk_whitelist_cache is None:
        import Script.Core.constant as constant
        from Script.Core.constant import Behavior, SecondBehavior

        _talk_whitelist_cache = {
            Behavior.GROUP_SEX_END,
            Behavior.GROUP_SEX_NPC_HP_0_END,
            Behavior.GROUP_SEX_PL_HP_0_END,
            Behavior.JOIN_GROUP_SEX,
            Behavior.DISCOVER_OTHER_SEX_AND_JOIN,
            Behavior.BE_INVITED_JOIN_GROUP_SEX,
            SecondBehavior.BE_INVITED_JOIN_GROUP_SEX,
        } | set(constant.special_end_H_list)
    return _talk_whitelist_cache


def mass_end_family() -> set:
    """
    结束族：结束群交、NPC 太累退出、以及本体 special_end_H_list（含玩家体力为零中断）。不含"加入"类
    Keyword arguments:
    无
    Return arguments:
    set -- 行为id集合
    """
    global _mass_end_cache
    if _mass_end_cache is None:
        import Script.Core.constant as constant
        from Script.Core.constant import Behavior

        _mass_end_cache = {Behavior.GROUP_SEX_END, Behavior.GROUP_SEX_NPC_HP_0_END} | set(constant.special_end_H_list)
    return _mass_end_cache


def mass_toy_family() -> set:
    """
    全员玩具族：遥控全员玩具的四条指令
    Keyword arguments:
    无
    Return arguments:
    set -- 行为id集合
    """
    global _mass_toy_cache
    if _mass_toy_cache is None:
        from Script.Core.constant import Behavior

        _mass_toy_cache = {
            Behavior.REMOTE_ALL_TURN_OFF_SEX_TOY,
            Behavior.REMOTE_ALL_SET_SEX_TOY_WEAK,
            Behavior.REMOTE_ALL_SET_SEX_TOY_MEDIUM,
            Behavior.REMOTE_ALL_SET_SEX_TOY_STRONG,
        }
    return _mass_toy_cache


def is_mass_instruction(behavior_id: str) -> bool:
    """
    波及全体的指令（结束族或全员玩具族）
    这些指令经 chara_handle_instruct_common_settle 结算时不传目标，玩家的 target_character_id 只是之前的遗留值，
    不能据此当成"对一个角色下的指令"
    Keyword arguments:
    behavior_id -- 行为id
    Return arguments:
    bool -- 是否波及全体
    """
    return behavior_id in mass_end_family() or behavior_id in mass_toy_family()


def is_mass_end_release_source(player_behavior_id_now: str) -> bool:
    """
    这次寸止释放是不是结束群交等全体结束指令触发的批量释放
    批量释放只由玩家结束族行为的效果串触发，触发时玩家的实时行为id必然在结束族里；
    本轮开头的快照可能已经过时（NPC 耗尽时本体会把玩家行为改成结束群交），所以必须传实时值
    Keyword arguments:
    player_behavior_id_now -- 玩家此刻的行为id
    Return arguments:
    bool -- 是否批量释放
    """
    return player_behavior_id_now in mass_end_family()


def is_tired_exit(behavior_id: str) -> bool:
    """
    NPC 太累退出群交（GROUP_SEX_NPC_HP_0_END），只认这一个id
    Keyword arguments:
    behavior_id -- 行为id
    Return arguments:
    bool -- 是否太累退出
    """
    import Script.Core.constant as constant

    return behavior_id == constant.Behavior.GROUP_SEX_NPC_HP_0_END


def is_template_dispatch(group_sex_mode: bool, character_id: int, behavior_id: str) -> bool:
    """
    是不是群交模板派发：群交模式下玩家的结算里，行为id不是本轮玩家自选的那个
    结束族与 GROUP_SEX_TO_H 本体就不走模板循环；NPC 耗尽时本体会中途改写玩家行为id，不排除会把真实的结束结算当成模板跳过
    Keyword arguments:
    group_sex_mode -- cache.group_sex_mode
    character_id -- 结算角色id
    behavior_id -- 结算行为id
    Return arguments:
    bool -- 是否模板派发
    """
    from Script.Core.constant import Behavior

    return bool(
        group_sex_mode
        and character_id == 0
        and behavior_id != state.turn.player_behavior_id
        and behavior_id not in mass_end_family()
        and behavior_id != Behavior.GROUP_SEX_TO_H
    )


def is_player_real(group_sex_mode: bool, character_id: int, behavior_id: str, player_target_id: int) -> bool:
    """
    是不是玩家亲自对一个目标下的真实指令：玩家自选的那个行为、有目标、且不是波及全体的指令
    Keyword arguments:
    group_sex_mode -- cache.group_sex_mode
    character_id -- 结算角色id
    behavior_id -- 结算行为id
    player_target_id -- 玩家此刻的 target_character_id
    Return arguments:
    bool -- 是否玩家真实指令
    """
    return bool(group_sex_mode and character_id == 0 and behavior_id == state.turn.player_behavior_id and player_target_id != 0 and not is_mass_instruction(behavior_id))


def derive_talk_behavior_id(now_talk_id: str, common_behavior_id) -> str:
    """
    从口上参数推出行为id，与 talk.handle_talk_draw 本体同口径
    招呼口上等场景角色身上的 behavior 是玩家的，不能直接读
    Keyword arguments:
    now_talk_id -- 口上id
    common_behavior_id -- 纸娃娃地文的行为id，没有时为 None
    Return arguments:
    str -- 行为id，推不出时为空串
    """
    if now_talk_id:
        from Script.Config import game_config

        if now_talk_id in game_config.config_talk:
            return game_config.config_talk[now_talk_id].behavior_id
    if common_behavior_id is not None:
        return common_behavior_id
    return ""


def edge_chain_talk_shows_live(character_id: int, second_behavior_id: str) -> bool:
    """
    寸止链上的口上是否实时显示
    - 寸止成功但接近极限：只放 {部位}_orgasm_edge 那一族（"XX寸止"标题与口上）
    - 寸止断了：在该角色自己的 check_second_effect 窗口内整条二段链都放；窗口外的普通 H 口上不放，否则该角色整轮刷屏
    Keyword arguments:
    character_id -- 角色id
    second_behavior_id -- 二段行为id
    Return arguments:
    bool -- 是否实时显示
    """
    turn = state.turn
    if character_id in turn.edge_near_limit and second_behavior_id.endswith("_orgasm_edge"):
        return True
    return character_id in turn.edge_break_live and character_id == turn.second_effect_character


def talk_decision(character_id: int, now_behavior_id: str, second_behavior_id: str, read_is_h: Callable[[], bool]) -> str:
    """
    一条口上怎么处理（只在接管的一轮内调用）。顺序有讲究：
    1. 寸止链实时显示 -> 直显
    2. 玩家真实指令期间 -> 直显
    3. 白名单 -> 缓冲。要排在吞掉之前：太累退出等口上此刻是 NPC 自己在说、is_h 还是 True，后判会被吞
    4. 模板派发期间、或群交 NPC 自己的背景 H 口上 -> 吞掉
    5. 其余 -> 直显。绝顶链与寸止成功的口上多半在外层捕获窗口里，由那一层决定显示还是丢弃
    Keyword arguments:
    character_id -- 角色id
    now_behavior_id -- 由 derive_talk_behavior_id 推出的行为id
    second_behavior_id -- 二段行为id
    read_is_h -- 读取该角色此刻 sp_flag.is_h（只在需要时调用）
    Return arguments:
    str -- TALK_PASS / TALK_BUFFER / TALK_DROP
    """
    turn = state.turn
    if edge_chain_talk_shows_live(character_id, second_behavior_id):
        return TALK_PASS
    if turn.player_real_active:
        return TALK_PASS
    if now_behavior_id in talk_whitelist():
        return TALK_BUFFER
    if turn.template_dispatch_active or (character_id != 0 and read_is_h()):
        return TALK_DROP
    return TALK_PASS
