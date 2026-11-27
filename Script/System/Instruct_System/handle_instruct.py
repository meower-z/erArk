"""指令处理：执行入口 handle_instruct、指令注册装饰器 add_instruct，以及用 add_instruct 注册的各指令处理函数"""

import datetime
from functools import wraps
from collections.abc import Callable, Mapping
from typing import Any, NoReturn, ParamSpec, TypeVar
from types import FunctionType
from Script.Core import (
    constant,
    constant_promise,
    game_type,
    get_text,
)
from Script.Design import handle_ability, map_handle, instuct_judege
from Script.Design import handle_npc_ai_in_h, handle_premise, child_stage_gate
from Script.Kernel import core
from Script.Config import normal_config, game_config
from Script.Design import game_time
from Script.Modules.gameplay_resolution import achievement_service
from Script.Modules.gameplay_resolution import group_sex_service
from Script.Modules.gameplay_resolution import instruct_plan_service
from Script.Modules.gameplay_resolution import intent, player_starters
from Script.Modules.gameplay_resolution import instruct_hooks, pick_hooks
from Script.Modules.gameplay_resolution import ui_hooks
from Script.Modules.domains import (
    abilities,
    achievement,
    action_info,
    activity,
    flags,
)
from Script.Modules.domains import h_state, needs, player_collection, roster
from Script.Modules.domains import relations, scene_state
from Script.Modules.domains import identity, modes

_: FunctionType = get_text._
""" 翻译api """
InstructParams = ParamSpec("InstructParams")
""" 指令处理函数的参数 """
InstructReturn = TypeVar("InstructReturn")
""" 指令处理函数的返回值 """


def handle_instruct(instruct: str) -> None:
    """
    处理执行指令：在玩家选择草稿（pick_hooks.drafting）里运行，指令写的值随它定下的行动走，
    没有定下行动而改了游戏状态时随一个 0 分钟的 Edit 走
    Keyword arguments:
    instruct -- 指令id（字符串）
    """
    with pick_hooks.drafting(instruct):
        # 交互对象处于幼年阶段时不执行H类指令
        if child_stage_gate.blocks_instruct(instruct):
            return
        if instruct in constant.instruct_premise_data:
            constant.handle_instruct_data[instruct]()


# ========== 指令类型映射 ==========
INSTRUCT_TYPE_MAP = {
    "SYSTEM": constant.InstructType.SYSTEM,
    "DAILY": constant.InstructType.DAILY,
    "PLAY": constant.InstructType.PLAY,
    "WORK": constant.InstructType.WORK,
    "ARTS": constant.InstructType.ARTS,
    "OBSCENITY": constant.InstructType.OBSCENITY,
    "SEX": constant.InstructType.SEX,
    "STUDY": 7,  # 如果存在
}

# ========== 子类型映射 ==========
SUB_TYPE_MAP = {
    "0": 0,
    "BASE": (
        constant.SexInstructSubType.BASE
        if hasattr(constant, "SexInstructSubType")
        else 0
    ),
    "FOREPLAY": (
        constant.SexInstructSubType.FOREPLAY
        if hasattr(constant, "SexInstructSubType")
        else 1
    ),
    "WAIT_UPON": (
        constant.SexInstructSubType.WAIT_UPON
        if hasattr(constant, "SexInstructSubType")
        else 2
    ),
    "DRUG": (
        constant.SexInstructSubType.DRUG
        if hasattr(constant, "SexInstructSubType")
        else 3
    ),
    "ITEM": (
        constant.SexInstructSubType.ITEM
        if hasattr(constant, "SexInstructSubType")
        else 4
    ),
    "INSERT": (
        constant.SexInstructSubType.INSERT
        if hasattr(constant, "SexInstructSubType")
        else 5
    ),
    "SM": (
        constant.SexInstructSubType.SM
        if hasattr(constant, "SexInstructSubType")
        else 6
    ),
    "ARTS": 7,
}


def add_instruct(
    instruct_id: str,
    instruct_type: int | None = None,
    name: str | None = None,
    premise_set: set | None = None,
    behavior_id: str | None = None,
    sub_type: int | None = None,
) -> Callable[
    [Callable[InstructParams, InstructReturn]],
    Callable[InstructParams, InstructReturn],
]:
    """
    添加指令处理

    新版本：所有参数都可以从CSV配置中读取，装饰器参数优先级高于CSV配置

    Keyword arguments:
    instruct_id -- 指令id（字符串，如 "move", "chat"）
    instruct_type -- 指令类型（可选，不传则从CSV读取）
    name -- 指令绘制文本（可选，不传则从CSV读取）
    premise_set -- 指令所需前提集合（可选，不传则从CSV读取）
    behavior_id -- 行为id（可选，不传则从CSV读取）
    sub_type -- 指令子类型（可选，不传则从CSV读取）
    """

    def decorator(
        func: Callable[InstructParams, InstructReturn],
    ) -> Callable[InstructParams, InstructReturn]:
        @wraps(func)
        def return_wrapper(
            *args: InstructParams.args, **kwargs: InstructParams.kwargs
        ) -> InstructReturn:
            return func(*args, **kwargs)

        # 从CSV配置读取参数（如果未在装饰器中指定）
        csv_config_cid = game_config.config_instruct_by_id.get(instruct_id)
        csv_config = (
            game_config.config_instruct.get(csv_config_cid)
            if csv_config_cid is not None
            else None
        )

        # 解析指令类型
        actual_instruct_type = instruct_type
        if actual_instruct_type is None and csv_config:
            type_str = getattr(csv_config, "instruct_type", None)
            if type_str:
                actual_instruct_type = INSTRUCT_TYPE_MAP.get(
                    type_str, constant.InstructType.DAILY
                )
        if actual_instruct_type is None:
            actual_instruct_type = constant.InstructType.DAILY

        # 解析显示名称
        actual_name = name
        if actual_name is None and csv_config:
            actual_name = getattr(csv_config, "name", None) or instruct_id
        if actual_name is None:
            actual_name = instruct_id

        # 解析前提条件集
        actual_premise_set = premise_set
        if actual_premise_set is None and csv_config:
            actual_premise_set = set()
            premise_str = getattr(csv_config, "premise_set", None)
            if premise_str:
                for raw_premise_name in premise_str.split("|"):
                    premise_name = raw_premise_name.strip()
                    if premise_name and hasattr(
                        constant_promise.Premise, premise_name
                    ):
                        actual_premise_set.add(
                            getattr(constant_promise.Premise, premise_name)
                        )
            # 根据H模式显示类型、疲劳类型增加前提
            h_mode_show_type = getattr(csv_config, "h_mode_show_type", None)
            # 非H显示
            if h_mode_show_type == 1:
                actual_premise_set.add(constant_promise.Premise.NOT_H)
                actual_premise_set.add(
                    constant_promise.Premise.NOT_SHOW_NON_H_IN_HIDDEN_SEX
                )
            # H显示
            elif h_mode_show_type == 2:
                actual_premise_set.add(constant_promise.Premise.TARGET_IS_H)
            tired_type = getattr(csv_config, "tired_type", None)
            # 轻度疲劳
            if tired_type == 1:
                actual_premise_set.add(constant_promise.Premise.TIRED_LE_84)
                actual_premise_set.add(constant_promise.Premise.HP_G_1)
                actual_premise_set.add(
                    constant_promise.Premise.DRUNK_LEVEL_NOT_3
                )
            # 重度疲劳
            elif tired_type == 2:
                actual_premise_set.add(constant_promise.Premise.TIRED_LE_74)
                actual_premise_set.add(constant_promise.Premise.HP_G_1)
                actual_premise_set.add(
                    constant_promise.Premise.DRUNK_LEVEL_NOT_3
                )
        if actual_premise_set is None:
            actual_premise_set = set()

        # 解析行为ID
        actual_behavior_id = behavior_id
        if actual_behavior_id is None and csv_config:
            behavior_str = getattr(csv_config, "behavior_id", None)
            if behavior_str and hasattr(constant.Behavior, behavior_str):
                actual_behavior_id = getattr(constant.Behavior, behavior_str)
            elif behavior_str:
                actual_behavior_id = behavior_str
        if actual_behavior_id is None:
            actual_behavior_id = "share_blankly"

        # 解析子类型
        actual_sub_type = sub_type
        if actual_sub_type is None and csv_config:
            sub_type_val = getattr(csv_config, "instruct_sub_type", None)
            sub_type_str = (
                str(sub_type_val) if sub_type_val is not None else "0"
            )
            actual_sub_type = SUB_TYPE_MAP.get(sub_type_str, 0)
        if actual_sub_type is None:
            actual_sub_type = 0

        # 注册指令处理函数
        constant.handle_instruct_data[instruct_id] = return_wrapper
        constant.instruct_premise_data[instruct_id] = actual_premise_set
        constant.instruct_type_data.setdefault(actual_instruct_type, set())
        constant.instruct_type_data[actual_instruct_type].add(instruct_id)
        constant.behavior_id_to_instruct_id[actual_behavior_id] = instruct_id
        constant.instruct_sub_type_data[instruct_id] = actual_sub_type
        constant.handle_instruct_name_data[instruct_id] = actual_name

        # 注册ID映射（从 CSV 中读取 cid）
        if csv_config:
            cid = getattr(csv_config, "cid", None)
            if cid is not None:
                constant.instruct_id_to_cid[instruct_id] = cid
                constant.cid_to_instruct_id[cid] = instruct_id

        # print(f"debug 添加指令处理 instruct_id:{instruct_id} name:{actual_name}")
        return return_wrapper

    return decorator


def instruct_filter_H_change(on_off_flag: bool) -> None:
    """
    指令类型过滤器进出H变更（已弃用）
    Keyword arguments:
    on_off_flag -- true:进入H false:退出H
    """
    setting = normal_config.system_setting
    if on_off_flag:
        instruct_hooks.stash_filter(setting.instruct_type_filter.copy())
        # 自动开启性爱面板并关闭其他面板
        setting.instruct_type_filter[6] = True
        for i in {1, 2, 3, 4, 5}:
            setting.instruct_type_filter[i] = False
    elif len(instruct_hooks.stashed_filter()):
        setting.instruct_type_filter = instruct_hooks.stashed_filter().copy()


TARGET_WAIT = "target_wait"
""" Intent.args 的键：交互对象排上同样分钟数的等待 """
START = "start"
""" Intent.args 的键：指令自己的开始代码在 _start_parts 里的名字 """
CLOSE_DOOR = "close_door"
""" Intent.args 的键：关门面板问过玩家时的回答，开始时记下问过，为真时关门 """

type StartPart = Callable[[int, intent.Intent], None]
""" 一个指令在行动开始时自己的代码：角色id、意图 """
_start_parts: dict[str, StartPart] = {}
""" 名字到指令自己的开始代码 """


def start_part(name: str) -> Callable[[StartPart], StartPart]:
    """
    登记一个指令在行动开始时自己的代码，choose_instruct(start=name) 选出的行动开始时调用它。
    名字是失败的行为id时，开始门判定没过、换成这个行为的行动开始时调用它
    Keyword arguments:
    name -- 名字
    Return arguments:
    Callable -- 装饰器，原样交回被装饰的 fn(who, intent)
    """

    def register(fn: StartPart) -> StartPart:
        if name in _start_parts:
            raise RuntimeError(f"start part {name} is registered twice")
        _start_parts[name] = fn
        return fn

    return register


def choose_instruct(
    behavior_id: str,
    minutes: int,
    *,
    target: int | None = None,
    state: int | str | None = None,
    judge: str = "",
    target_wait: bool = False,
    start: str = "",
    args: Mapping[str, object] | None = None,
    fields: Mapping[str, object] | None = None,
) -> NoReturn:
    """
    定下玩家一个指令的行动（种类 Instruct），抛出 player_pick.Chosen
    Keyword arguments:
    behavior_id -- 行为id
    minutes -- 名义分钟数
    target -- 交互对象的角色id，None 时为玩家当前的交互对象
    state -- 开始时的角色状态，None 时为行为id
    judge -- 指令的判断条件：选择时先问玩家（instuct_judege.ask_judge），[返回]时退出选择（pick_hooks.back）；
        开始门再判定（催眠在那时扣理智）；为空时不判断。群交判定的是场景里的每个干员而不是交互对象，选择时不问
    target_wait -- 交互对象是否排上同样分钟数的等待
    start -- 指令自己的开始代码的名字（start_part），为空时没有
    args -- 指令自己的参数（Intent.args）
    fields -- 开始时写在玩家身上的值（Intent.fields）
    """
    instruct_args: dict[str, object] = dict(args or {})
    if target_wait:
        instruct_args[TARGET_WAIT] = True
    if start:
        instruct_args[START] = start
    if target is None:
        target = activity.target(0)
    if (
        judge
        and judge != _("群交")
        and not instuct_judege.ask_judge(0, target, judge)
    ):
        pick_hooks.back()
    pick_hooks.choose(
        behavior_id,
        minutes,
        kind=player_starters.KIND,
        target=target,
        state=state,
        fields=fields,
        args=instruct_args,
        judge=judge or None,
    )


_plan_target_wait = instruct_plan_service.plan_target_wait


def start_instruct(who: int, chosen: intent.Intent) -> None:
    """
    种类 Instruct 的行动开始时（player_starters 调用，在 begin 之后、结算之前）：
    交互对象排上等待，关门面板的回答，群交模板，指令自己的开始代码
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    args = chosen.get("args", {})
    target = chosen.get("target", who)
    if args.get(TARGET_WAIT) and target != who:
        _plan_target_wait(target, chosen["minutes"])
    if CLOSE_DOOR in args:
        _close_door(who, bool(args[CLOSE_DOOR]))
    group_sex_service.group_sex_settle(who, target, chosen["behavior_id"])
    part = args.get(START)
    if isinstance(part, str):
        _start_parts[part](who, chosen)


THEN = "then"
""" Intent.args 的键：这个行动开始时排在它之后的指令的行为id（开始代码 then） """


@start_part(THEN)
def _plan_then(who: int, chosen: intent.Intent) -> None:
    """
    行动开始时：args["then"] 的指令排进计划队列，这个行动结束后接着做，交互对象到时一起等待
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    from Script.Modules.gameplay_resolution import plan_queue

    then = str(chosen["args"][THEN])
    plan_queue.plan_next(
        who,
        then,
        _instruct_duration(then, 0),
        kind=player_starters.KIND,
        target=chosen.get("target", who),
        args={TARGET_WAIT: True},
    )


def chara_handle_instruct_common_settle(
    behavior_id: str,
    target_character_id: int = 0,
    duration: int = 0,
    judge: str = "",
    force_taget_wait: bool = False,
    *,
    start: str = "",
    args: Mapping[str, object] | None = None,
    fields: Mapping[str, object] | None = None,
) -> NoReturn:
    """
    玩家指令的通用选择：定下行动，抛出 player_pick.Chosen
    Keyword arguments:
    behavior_id -- 行为id
    target_character_id -- 交互对象的角色id，0 时为玩家当前的交互对象
    duration -- 分钟数，0 为查表
    judge -- 判断条件，为空时不判断；行动开始时开始门判断，没过的换成对应的失败行为
    force_taget_wait -- 交互对象是否排上同样分钟数的等待
    start -- 指令自己的开始代码的名字（start_part），为空时没有
    args -- 指令自己的参数（Intent.args）
    fields -- 开始时写在玩家身上的值（Intent.fields）
    """
    choose_instruct(
        behavior_id,
        _instruct_duration(behavior_id, duration),
        target=target_character_id or None,
        judge=judge,
        target_wait=force_taget_wait,
        start=start,
        args=args,
        fields=fields,
    )


_judged_behavior_id = instruct_plan_service.judged_behavior_id
_instruct_duration = instruct_plan_service.instruct_duration
plan_instruct_common_settle = instruct_plan_service.plan_instruct_common_settle
handle_comprehensive_state_effect = (
    instruct_plan_service.handle_comprehensive_state_effect
)


@add_instruct(constant.Instruct.REST)
def handle_rest() -> None:
    """处理休息指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.REST, force_taget_wait=True
    )


@add_instruct(constant.Instruct.BUY_FOOD)
def handle_buy_food() -> None:
    """处理购买食物指令"""
    ui_hooks.switch_panel(constant.Panel.FOOD_SHOP)


@add_instruct(constant.Instruct.EAT)
def handle_eat() -> None:
    """处理食物背包指令"""
    ui_hooks.switch_panel(constant.Panel.FOOD_BAG)


@add_instruct(constant.Instruct.PUT_SELFMADE_FOOD_IN)
def handle_put_selfmade_food_in() -> None:
    """处理放入正常食物指令"""
    from Script.Modules.gameplay_resolution import canteen_service

    canteen_service.put_selfmade_food_in()


@add_instruct(constant.Instruct.MOVE)
def handle_move() -> None:
    """处理移动指令"""
    ui_hooks.switch_panel(constant.Panel.SEE_MAP)


@add_instruct(constant.Instruct.CARRY_MOVE)
def handle_carry_move() -> None:
    """处理携带H中移动指令，与移动指令共用地图面板，实际行为在own_charcter_move中按携带模式区分"""
    ui_hooks.switch_panel(constant.Panel.SEE_MAP)


@add_instruct(constant.Instruct.SEE_ATTR)
def handle_see_attr() -> None:
    """查看属性"""
    ui_hooks.switch_panel(constant.Panel.SEE_ATTR)


@add_instruct(constant.Instruct.CHAT)
def handle_chat() -> None:
    """处理聊天指令"""
    target_data: identity.Identity = identity.of(activity.target(0))
    if (
        action_info.get(target_data.cid, "talk_count")
        > abilities.ability(0)[40] + 1
    ):
        chara_handle_instruct_common_settle(
            constant.Behavior.CHAT_FAILED, start="count_talk"
        )
    else:
        chara_handle_instruct_common_settle(
            constant.Behavior.CHAT, start="count_talk"
        )


@start_part("count_talk")
def _count_talk(who: int, chosen: intent.Intent) -> None:
    """
    聊天开始时：交互对象的聊天计数加一
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    action_info.add(chosen["target"], "talk_count", 1)


@add_instruct(constant.Instruct.BUY_H_ITEM)
def handle_buy_h_item() -> None:
    """处理购买成人用品指令"""
    ui_hooks.switch_panel(constant.Panel.H_ITEM_SHOP)


@add_instruct(constant.Instruct.ITEM)
def handle_item() -> None:
    """处理道具指令"""
    ui_hooks.switch_panel(constant.Panel.ITEM)


@add_instruct(constant.Instruct.SAVE)
def handle_save() -> None:
    """处理读写存档指令"""
    ui_hooks.switch_panel(constant.Panel.SAVE)


@add_instruct(constant.Instruct.ABL_UP)
def handle_abl_up() -> None:
    """处理属性上升"""
    ui_hooks.switch_panel(constant.Panel.ABL_UP)


@add_instruct(constant.Instruct.OWNER_ABL_UP)
def handle_owner_abl_up() -> None:
    """处理自身属性上升"""
    ui_hooks.switch_panel(constant.Panel.OWNER_ABL_UP)


@add_instruct(constant.Instruct.DEBUG_MODE_ON)
def debug_mode() -> None:
    """处理开启DEBUG模式指令"""
    modes.set_debug(True)


@add_instruct(constant.Instruct.DEBUG_MODE_OFF)
def debug_mode_off() -> None:
    """处理关闭DEBUG模式指令"""
    modes.set_debug(False)


@add_instruct(constant.Instruct.DEBUG_ADJUST)
def debug_adjust() -> None:
    """处理debug数值调整指令"""
    ui_hooks.switch_panel(constant.Panel.DEBUG_ADJUST)


@add_instruct(constant.Instruct.SYSTEM_SETTING)
def handle_system_setting() -> None:
    """系统设置"""
    ui_hooks.switch_panel(constant.Panel.SYSTEM_SETTING)


@add_instruct(constant.Instruct.TALK_QUICK_TEST)
def handle_talk_quick_test() -> None:
    """快速测试口上"""
    ui_hooks.switch_panel(constant.Panel.TALK_QUICK_TEST)


@add_instruct(constant.Instruct.CHAT_WITH_AI)
def handle_chat_with_ai() -> None:
    """与文本生成AI对话"""
    ui_hooks.switch_panel(constant.Panel.CHAT_WITH_AI)


@add_instruct(constant.Instruct.TEACH)
def handle_teach() -> None:
    """处理授课指令：授课45分钟，开始时把在场的学生拉来听课"""
    choose_instruct(
        constant.Behavior.TEACH,
        45,
        state=constant.CharacterStatus.STATUS_TEACH,
        start="teach",
    )


@start_part("teach")
def _start_teach(who: int, chosen: intent.Intent) -> None:
    """
    授课开始时：在场能拉来听课、又没在听课的学生，打断手上的行动，排上听课到本节课结束
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    from Script.Modules.gameplay_resolution import plan_queue
    from Script.System.Education_System import class_ai, schedule_handle

    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(who)
    )
    for chara_id in scene_state.occupants(scene_path_str):
        if chara_id == who:
            continue
        # 只拉学生岗、不在 H / 睡觉 / 翘课 / 休息中的人，已经在听别的教师讲课的不抢
        if (
            class_ai.judge_student_pullable(chara_id)
            and activity.behavior(chara_id).behavior_id
            != constant.Behavior.ATTENT_CLASS
        ):
            plan_queue.plan_next(
                chara_id,
                constant.Behavior.ATTENT_CLASS,
                schedule_handle.get_period_left_minute(
                    chara_id, from_time=game_time.now()
                ),
                state=constant.CharacterStatus.STATUS_ATTENT_CLASS,
                interrupt=True,
            )


@add_instruct(constant.Instruct.BORROW_BOOK)
def handle_borrow_book() -> None:
    """处理借阅书籍指令"""
    ui_hooks.switch_panel(constant.Panel.BORROW_BOOK)


@add_instruct(constant.Instruct.READ_BOOK)
def handle_read_book() -> None:
    """处理读书指令"""
    ui_hooks.switch_panel(constant.Panel.READ_BOOK)


@add_instruct(constant.Instruct.MANAGE_LIBRARY)
def handle_manage_library() -> None:
    """处理管理图书馆指令"""
    ui_hooks.switch_panel(constant.Panel.MANAGE_LIBRARY)


@add_instruct(constant.Instruct.MANAGE_ASSEMBLY_LINE)
def handle_manage_assembly_line() -> None:
    """处理管理流水线指令"""
    ui_hooks.switch_panel(constant.Panel.MANAGE_ASSEMBLY_LINE)


@add_instruct(constant.Instruct.PLANT_MANAGE_CROP)
def handle_plant_manage_crop() -> None:
    """处理种植与养护作物指令"""
    chara_handle_instruct_common_settle(constant.Behavior.PLANT_MANAGE_CROP)


@add_instruct(constant.Instruct.MANAGE_AGRICULTURE)
def handle_manage_agriculture() -> None:
    """处理管理农业生产指令"""
    ui_hooks.switch_panel(constant.Panel.MANAGE_AGRICULTURE)


@add_instruct(constant.Instruct.MANAGE_VEHICLE)
def handle_manage_vehicle() -> None:
    """处理管理载具指令"""
    ui_hooks.switch_panel(constant.Panel.MANAGE_VEHICLE)


@add_instruct(constant.Instruct.PHYSICAL_CHECK_AND_MANAGE)
def handle_physical_check_and_manage() -> None:
    """处理身体检查与管理指令"""
    ui_hooks.switch_panel(constant.Panel.PHYSICAL_CHECK_AND_MANAGE)


@add_instruct(constant.Instruct.MANAGE_CONFINEMENT_AND_TRAINING)
def handle_manage_vonfinement_and_training() -> None:
    """处理管理监禁调教指令"""
    ui_hooks.switch_panel(constant.Panel.MANAGE_CONFINEMENT_AND_TRAINING)


@add_instruct(constant.Instruct.INVESTIGATE_RESOURCE_MARKET)
def handle_investigate_resource_market() -> None:
    """处理研判资源市场指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.INVESTIGATE_RESOURCE_MARKET
    )


@add_instruct(constant.Instruct.MANAGE_RESOURCE_EXCHANGE)
def handle_manage_resource_exchange() -> None:
    """处理管理资源交易指令"""
    ui_hooks.switch_panel(constant.Panel.MANAGE_RESOURCE_EXCHANGE)


@add_instruct(constant.Instruct.NAVIGATION)
def handle_navigation() -> None:
    """处理导航指令"""
    ui_hooks.switch_panel(constant.Panel.NAVIGATION)


@add_instruct(constant.Instruct.MANAGE_BASEMENT)
def handle_manage_basement() -> None:
    """处理管理罗德岛指令"""
    ui_hooks.switch_panel(constant.Panel.MANAGE_BASEMENT)


@add_instruct(constant.Instruct.EDUCATION_MANAGE)
def handle_education_manage() -> None:
    """处理教育管理系统指令"""
    ui_hooks.switch_panel(constant.Panel.EDUCATION_MANAGE)


@add_instruct(constant.Instruct.CHECK_REPORT_CARD)
def handle_check_report_card() -> None:
    """处理检查成绩单指令"""
    chara_handle_instruct_common_settle(constant.Behavior.CHECK_REPORT_CARD)


@add_instruct(constant.Instruct.MANAGE_DORMITORY)
def handle_manage_dormitory() -> None:
    """处理宿舍管理系统指令"""
    ui_hooks.switch_panel(constant.Panel.MANAGE_DORMITORY)


# 以下为源石技艺#


@add_instruct(constant.Instruct.HYPNOSIS_ONE)
def handle_hypnosis_one() -> None:
    """处理单人催眠"""
    now_scene_str = map_handle.get_map_system_path_str_for_list(
        activity.position(0)
    )
    door: dict[str, object] = {}
    if scene_state.close_flag(now_scene_str) == 0:
        door = ask_close_door()
    chara_handle_instruct_common_settle(
        constant.Behavior.HYPNOSIS_ONE, args=door
    )


@add_instruct(constant.Instruct.DEEPENING_HYPNOSIS)
def handle_deepening_hypnosis() -> None:
    """处理加深催眠"""
    chara_handle_instruct_common_settle(constant.Behavior.HYPNOSIS_ONE)


@add_instruct(constant.Instruct.HYPNOSIS_ALL)
def handle_hypnosis_all() -> None:
    """处理集体催眠"""
    character_data: identity.Identity = identity.of(0)
    now_scene_str = map_handle.get_map_system_path_str_for_list(
        activity.position(0)
    )
    # 计算当前理智值是否足够进行催眠
    now_npc_num = len(scene_state.occupants(now_scene_str)) - 1
    sanity_point_cost = 10 + 10 * now_npc_num
    if needs.of(character_data.cid)["sanity"] < sanity_point_cost:
        draw_text = _(
            "\n当前理智值不足，至少需要{0}点理智值，无法进行集体催眠\n"
        ).format(sanity_point_cost)
        ui_hooks.emit_notice(draw_text, wait=True)
        return
    door: dict[str, object] = {}
    if scene_state.close_flag(now_scene_str) == 0:
        door = ask_close_door()
    chara_handle_instruct_common_settle(
        constant.Behavior.HYPNOSIS_ALL, args=door
    )


@add_instruct(constant.Instruct.CHANGE_HYPNOSIS_MODE)
def handle_change_hypnosis_mode() -> None:
    """处理切换催眠模式"""
    ui_hooks.switch_panel(constant.Panel.CHANGE_HYPNOSIS_MODE)


@add_instruct(constant.Instruct.HYPNOSIS_CANCEL)
def handle_hypnosis_cancel() -> None:
    """处理解除催眠"""
    chara_handle_instruct_common_settle(constant.Behavior.HYPNOSIS_CANCEL)


@add_instruct(constant.Instruct.HYPNOSIS_INCREASE_BODY_SENSITIVITY)
def handle_hypnosis_increase_body_sensitivity() -> None:
    """处理体控-敏感度提升"""
    chara_handle_instruct_common_settle(
        constant.Behavior.HYPNOSIS_INCREASE_BODY_SENSITIVITY
    )


@add_instruct(constant.Instruct.HYPNOSIS_FORCE_CLIMAX)
def handle_hypnosis_force_climax() -> None:
    """处理体控-强制高潮"""
    chara_handle_instruct_common_settle(constant.Behavior.HYPNOSIS_FORCE_CLIMAX)


@add_instruct(constant.Instruct.HYPNOSIS_FORCE_OVULATION)
def handle_hypnosis_force_ovulation() -> None:
    """处理体控-强制排卵"""
    chara_handle_instruct_common_settle(
        constant.Behavior.HYPNOSIS_FORCE_OVULATION
    )


@add_instruct(constant.Instruct.HYPNOSIS_PAIN_AS_PLEASURE)
def handle_hypnosis_pain_as_pleasure() -> None:
    """处理心控-苦痛快感化"""
    chara_handle_instruct_common_settle(
        constant.Behavior.HYPNOSIS_PAIN_AS_PLEASURE
    )


@add_instruct(constant.Instruct.PENETRATING_VISION_ON)
def handle_penetrating_vision_on() -> None:
    """处理开启透视"""
    chara_handle_instruct_common_settle(constant.Behavior.PENETRATING_VISION_ON)


@add_instruct(constant.Instruct.PENETRATING_VISION_OFF)
def handle_penetrating_vision_off() -> None:
    """处理关闭透视"""
    chara_handle_instruct_common_settle(
        constant.Behavior.PENETRATING_VISION_OFF
    )


@add_instruct(constant.Instruct.HORMONE_ON)
def handle_hormone_on() -> None:
    """处理开启信息素"""
    chara_handle_instruct_common_settle(constant.Behavior.HORMONE_ON)


@add_instruct(constant.Instruct.HORMONE_OFF)
def handle_hormone_off() -> None:
    """处理关闭信息素"""
    chara_handle_instruct_common_settle(constant.Behavior.HORMONE_OFF)


@add_instruct(constant.Instruct.TIME_STOP_ON)
def handle_time_stop_on() -> None:
    """处理时间停止流动"""
    chara_handle_instruct_common_settle(constant.Behavior.TIME_STOP_ON)


@add_instruct(constant.Instruct.TIME_STOP_OFF)
def handle_time_stop_off() -> None:
    """处理时间重新流动"""
    chara_handle_instruct_common_settle(constant.Behavior.TIME_STOP_OFF)


@add_instruct(constant.Instruct.TIME_STOP_OFF_IN_H)
def handle_time_stop_off_in_h() -> None:
    """处理在H中取消时停"""
    chara_handle_instruct_common_settle(constant.Behavior.TIME_STOP_OFF)


@add_instruct(constant.Instruct.CARRY_TARGET)
def handle_carry_target() -> None:
    """处理搬运对方"""
    chara_handle_instruct_common_settle(constant.Behavior.CARRY_TARGET)


@add_instruct(constant.Instruct.STOP_CARRY_TARGET)
def handle_stop_carry_target() -> None:
    """处理停止搬运对方"""
    chara_handle_instruct_common_settle(constant.Behavior.STOP_CARRY_TARGET)


@add_instruct(constant.Instruct.TARGET_FREE_IN_TIME_STOP)
def handle_target_free_in_time_stop() -> None:
    """处理让在时停中正常行动"""
    # TODO，到写隐奸和露出的时候一起写
    chara_handle_instruct_common_settle(
        constant.Behavior.TARGET_FREE_IN_TIME_STOP
    )


@add_instruct(constant.Instruct.TARGET_STOP_IN_TIME_STOP)
def handle_target_stop_in_time_stop() -> None:
    """处理在时停中再次停止"""
    # TODO，到写隐奸和露出的时候一起写
    chara_handle_instruct_common_settle(
        constant.Behavior.TARGET_STOP_IN_TIME_STOP
    )


@add_instruct(constant.Instruct.DIRAY)
def handle_diary() -> None:
    """处理日记指令"""
    ui_hooks.switch_panel(constant.Panel.DIRAY)


@add_instruct(constant.Instruct.SLEEP)
def handle_sleep() -> None:
    """处理睡觉指令"""
    ui_hooks.switch_panel(constant.Panel.SLEEP)


@add_instruct(constant.Instruct.TAKE_SHOWER)
def handle_take_shower() -> None:
    """处理淋浴指令"""
    chara_handle_instruct_common_settle(constant.Behavior.TAKE_SHOWER)


@add_instruct(constant.Instruct.STROKE)
def handle_stroke() -> None:
    """处理身体接触指令"""
    chara_handle_instruct_common_settle(constant.Behavior.STROKE)


@add_instruct(constant.Instruct.MASSAGE)
def handle_massage() -> None:
    """处理按摩指令"""
    chara_handle_instruct_common_settle(constant.Behavior.MASSAGE)


@add_instruct(constant.Instruct.WAIT)
def handle_wait() -> None:
    """处理等待五分钟指令"""
    chara_handle_instruct_common_settle(constant.Behavior.WAIT, duration=5)


@add_instruct(constant.Instruct.WAIT_1_HOUR)
def handle_wait_1_hour() -> None:
    """处理等待一个小时指令"""
    instruct_hooks.skip_pauses(True)
    chara_handle_instruct_common_settle(constant.Behavior.WAIT, duration=60)


@add_instruct(constant.Instruct.WAIT_6_HOUR)
def handle_wait_6_hour() -> None:
    """处理等待六个小时指令"""
    instruct_hooks.skip_pauses(True)
    chara_handle_instruct_common_settle(constant.Behavior.WAIT, duration=360)


@add_instruct(constant.Instruct.MAKE_COFFEE)
def handle_make_coffee() -> None:
    """处理泡咖啡指令"""
    chara_handle_instruct_common_settle(constant.Behavior.MAKE_COFFEE)


@add_instruct(constant.Instruct.MAKE_COFFEE_ADD)
def handle_make_coffee_add() -> None:
    """处理泡咖啡（加料）指令"""
    ui_hooks.switch_panel(constant.Panel.MAKE_COFFEE_ADD)


@add_instruct(constant.Instruct.ASK_MAKE_COFFEE)
def handle_ask_make_coffee() -> None:
    """处理让对方泡咖啡指令"""
    chara_handle_instruct_common_settle(constant.Behavior.ASK_MAKE_COFFEE)


@add_instruct(constant.Instruct.MAKE_FOOD)
def handle_make_food() -> None:
    """做饭"""
    ui_hooks.switch_panel(constant.Panel.MAKE_FOOD)


@add_instruct(constant.Instruct.MIXOLOGY)
def handle_mixology() -> None:
    """处理调酒指令"""
    ui_hooks.switch_panel(constant.Panel.MIXOLOGY)


@add_instruct(constant.Instruct.ALL_NPC_POSITION)
def handle_all_npc_position() -> None:
    """处理干员位置一览指令"""
    ui_hooks.switch_panel(constant.Panel.ALL_NPC_POSITION)


@add_instruct(constant.Instruct.FOLLOW)
def handle_followed() -> None:
    """处理邀请同行指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FOLLOW, duration=5, start="follow"
    )


@start_part("follow")
def _start_follow(who: int, chosen: intent.Intent) -> None:
    """
    邀请同行开始时：其他干员退出跟随（助理与交互对象除外，debug 模式不限人数）
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    target_data: identity.Identity = identity.of(chosen["target"])

    # 提示信息
    text = _("\n{0}进入智能跟随模式\n").format(target_data.name)

    # 去掉其他NPC的跟随
    if not modes.debug():
        for npc_id in roster.active():
            if npc_id not in {
                0,
                chosen["target"],
                relations.assistant_character_id(who),
            }:
                other_character_data = identity.of(npc_id)
                if flags.get(other_character_data.cid, "is_follow"):
                    flags.set(other_character_data.cid, is_follow=0)
                    text += _(
                        "当前最大跟随数量：1人，{0}退出跟随模式\n"
                    ).format(other_character_data.name)
    ui_hooks.emit_notice(text)


@add_instruct(constant.Instruct.END_FOLLOW)
def handle_end_followed() -> None:
    """处理结束同行指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.END_FOLLOW, duration=5
    )


@add_instruct(constant.Instruct.ASK_TARGET_REST)
def handle_ask_target_rest() -> None:
    """处理让对方休息指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.WAIT,
        duration=1,
        start="target_sp_flag",
        args={"flag": "rest"},
    )


@add_instruct(constant.Instruct.ASK_TARGET_SLEEP)
def handle_ask_target_sleep() -> None:
    """处理让对方睡觉指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.WAIT,
        duration=1,
        start="target_sp_flag",
        args={"flag": "tired"},
    )


@start_part("target_sp_flag")
def _set_target_sp_flag(who: int, chosen: intent.Intent) -> None:
    """
    行动开始时：交互对象的 sp_flag 里 args["flag"] 这一项设为真
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    flags.set(chosen["target"], **{str(chosen["args"]["flag"]): True})


@add_instruct(constant.Instruct.APOLOGIZE)
def handle_apologize() -> None:
    """处理道歉指令"""
    target_data: identity.Identity = identity.of(activity.target(0))
    value = _calm_value()
    # 判定减掉愤怒值后是否不生气了
    if needs.of(target_data.cid)["angry"] - value <= 30:
        behavior_id = constant.Behavior.APOLOGIZE
    else:
        behavior_id = constant.Behavior.APOLOGIZE_FAILED
    chara_handle_instruct_common_settle(
        behavior_id,
        force_taget_wait=True,
        start="calm_target",
        args={"value": value},
    )


def _calm_value() -> int:
    """
    玩家道歉、听牢骚时交互对象减掉的愤怒值：按口才调整
    Return arguments:
    int -- 愤怒值
    """
    adjust = handle_ability.get_ability_adjust(abilities.ability(0)[40])
    return int(10 + adjust * 10)


@start_part("calm_target")
def _calm_target(who: int, chosen: intent.Intent) -> None:
    """
    道歉、听牢骚开始时：交互对象减掉 args["value"] 的愤怒值，不低于0
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    target_data = identity.of(chosen["target"])
    value = chosen["args"]["value"]
    assert isinstance(value, int)
    needs.add(target_data.cid, "angry", -value, min=0)


@add_instruct(constant.Instruct.LISTEN_COMPLAINT)
def handle_listen_complaint() -> None:
    """处理听牢骚指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.LISTEN_COMPLAINT,
        force_taget_wait=True,
        start="calm_target",
        args={"value": _calm_value()},
    )


@add_instruct(constant.Instruct.GIVE_GIFT)
def handle_give_gift() -> None:
    """处理赠送礼物指令"""
    ui_hooks.switch_panel(constant.Panel.GIVE_GIFT)


@add_instruct(constant.Instruct.ORIGINIUM_ARTS)
def handle_originium_arts() -> None:
    """处理源石技艺指令"""
    ui_hooks.switch_panel(constant.Panel.ORIGINIUM_ARTS)


@add_instruct(constant.Instruct.TARGET_TO_SELF)
def handle_target_to_self() -> None:
    """处理对自己交互指令"""
    choose_instruct(constant.Behavior.WAIT, 1, target=0)


@add_instruct(constant.Instruct.DOOR_LOCK_INNER)
def handle_door_lock_inner() -> None:
    """处理锁上门内侧锁指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.WAIT, duration=1, start="door", args={"lock": True}
    )


@add_instruct(constant.Instruct.DOOR_UNLOCK_INNER)
def handle_door_unlock_inner() -> None:
    """处理解开门内侧锁指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.WAIT, duration=1, start="door", args={"lock": False}
    )


def ask_close_door() -> dict[str, object]:
    """
    经 instruct_hooks.ask_close_door 询问玩家是否关门，只读游戏状态。
    Return arguments:
    dict[str, object] -- 交给 choose 的 args，问过时为 {CLOSE_DOOR: 回答}，未询问时为空字典
    """
    answer = instruct_hooks.ask_close_door()
    if answer is None:
        return {}
    return {CLOSE_DOOR: answer}


def _close_door(who: int, close: bool) -> None:
    """
    关门面板的回答在行动开始时生效：记下在这里问过，回答关门时关上
    Keyword arguments:
    who -- 角色id
    close -- 是否关门
    """
    action_info.set(who, "ask_close_door_flag", True)
    if close:
        now_scene_data = constant.scene_data[
            map_handle.get_map_system_path_str_for_list(activity.position(who))
        ]
        scene_state.set_close_flag(
            now_scene_data.scene_path, now_scene_data.close_type
        )


@start_part("door")
def _set_door(who: int, chosen: intent.Intent) -> None:
    """
    锁门、开锁开始时：角色所在场景的门锁上（args["lock"] 为真）或解开
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    now_scene_str = map_handle.get_map_system_path_str_for_list(
        activity.position(who)
    )
    now_scene_data = constant.scene_data[now_scene_str]
    if chosen["args"]["lock"]:
        scene_state.set_close_flag(now_scene_str, now_scene_data.close_type)
    else:
        scene_state.set_close_flag(now_scene_str, 0)


@add_instruct(constant.Instruct.CHARA_DIY_INSTRUCT)
def handle_chara_diy_instruct(event_id: str) -> None:
    """
    处理角色特殊指令：只由指令面板的角色特殊指令按钮调用（see_instruct_panel.handle_chara_diy_instruct），
    行动的分钟数是事件文本里的时间，开始时玩家记下这个事件
    Keyword arguments:
    event_id -- 事件id
    """
    event_data = game_config.config_event[event_id]
    new_duration = int(event_data.text.split("|")[1])
    chara_handle_instruct_common_settle(
        constant.Behavior.CHARA_DIY_INSTRUCT,
        duration=new_duration,
        start="diy_event",
        args={"event_id": event_id},
    )


@start_part("diy_event")
def _start_diy_event(who: int, chosen: intent.Intent) -> None:
    """
    角色特殊指令开始时：角色记下 args["event_id"] 的事件，标为角色特殊指令的事件
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    activity.update_event(
        who,
        event_id=str(chosen["args"]["event_id"]),
        chara_diy_event_flag=True,
    )


@start_part("bondage")
def _start_bondage(who: int, chosen: intent.Intent) -> None:
    """
    捆绑、解除捆绑开始时：交互对象换上 args["bondage_id"] 的捆绑（0 为解除）
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    bondage_id = chosen["args"]["bondage_id"]
    assert isinstance(bondage_id, int)
    h_state.set(chosen["target"], bondage=bondage_id)


@start_part("sex_position")
def _start_sex_position(who: int, chosen: intent.Intent) -> None:
    """
    选体位性交开始时：换体位（args["change_position"] 为真）记下换之前的体位，否则清掉上一个体位
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    pre = (
        h_state.get(who, "current_sex_position")
        if chosen["args"]["change_position"]
        else -1
    )
    h_state.set(who, pre_sex_position=pre)


@add_instruct(constant.Instruct.TEST_INSTRUCT)
def handle_test_instruct() -> None:
    """处理测试用临时指令"""
    chara_handle_instruct_common_settle(constant.Behavior.TEST_INSTRUCT)


@add_instruct(constant.Instruct.LISTEN_INFLATION)
def handle_listen_inflation() -> None:
    """处理听肚子里的动静指令"""
    chara_handle_instruct_common_settle(constant.Behavior.LISTEN_INFLATION)


@add_instruct(constant.Instruct.PRENATAL_TALK)
def handle_prenatal_talk() -> None:
    """处理对孕肚说话指令（胎教，Plan 22 四期）"""
    chara_handle_instruct_common_settle(constant.Behavior.PRENATAL_TALK)


@add_instruct(constant.Instruct.PRENATAL_MUSIC)
def handle_prenatal_music() -> None:
    """处理给孕肚放音乐指令（胎教，Plan 22 四期）"""
    chara_handle_instruct_common_settle(constant.Behavior.PRENATAL_MUSIC)


@add_instruct(constant.Instruct.PRENATAL_TOUCH)
def handle_prenatal_touch() -> None:
    """处理抚摸孕肚指令（胎教，Plan 22 四期）"""
    chara_handle_instruct_common_settle(constant.Behavior.PRENATAL_TOUCH)


@add_instruct(constant.Instruct.TAKE_CARE_BABY)
def handle_take_care_baby() -> None:
    """处理照顾婴儿指令"""
    ui_hooks.switch_panel(constant.Panel.TAKE_CARE_BABY)


@add_instruct(constant.Instruct.ORDER_HOTEL_ROOM)
def handle_order_hotel_room() -> None:
    """处理预定房间指令"""
    ui_hooks.switch_panel(constant.Panel.ORDER_HOTEL_ROOM)


@add_instruct(constant.Instruct.SEE_COLLECTION)
def handle_see_collection() -> None:
    """处理查看收藏品指令"""
    ui_hooks.switch_panel(constant.Panel.COLLECTION)


@add_instruct(constant.Instruct.SEE_ACHIEVEMENT)
def handle_see_achievement() -> None:
    """处理查看蚀刻章指令"""
    ui_hooks.switch_panel(constant.Panel.SEE_ACHIEVEMENT)


@add_instruct(constant.Instruct.SEE_FRIDGE)
def handle_see_fridge() -> None:
    """处理查看冰箱指令"""
    ui_hooks.switch_panel(constant.Panel.FRIDGE)


@add_instruct(constant.Instruct.PREGNANCY_OVERVIEW)
def handle_pregnancy_overview() -> None:
    """处理怀孕总览指令"""
    ui_hooks.switch_panel(constant.Panel.PREGNANCY_OVERVIEW)


@add_instruct(constant.Instruct.TAKE_CHARA_EGGS)
def handle_take_chara_eggs() -> None:
    """处理拿走产下的卵指令"""
    # 数据结算由行为挂接的专用结算（BehaviorEffect.TAKE_CHARA_EGGS_SETTLE=546）在行为结算阶段完成
    chara_handle_instruct_common_settle(
        constant.Behavior.TAKE_CHARA_EGGS, duration=5
    )


@add_instruct(constant.Instruct.IDENTIFY_HELD_EGGS)
def handle_identify_held_eggs() -> None:
    """处理鉴定持有的卵指令"""
    # 数据结算由行为挂接的专用结算（BehaviorEffect.IDENTIFY_HELD_EGGS_SETTLE=547）在行为结算阶段完成
    chara_handle_instruct_common_settle(
        constant.Behavior.IDENTIFY_HELD_EGGS, duration=30
    )


@add_instruct(constant.Instruct.FIELD_COMMISSION)
def handle_field_commission() -> None:
    """处理外勤委托指令"""
    ui_hooks.switch_panel(constant.Panel.FIELD_COMMISSION)


@add_instruct(constant.Instruct.CHECK_LOCKER)
def handle_check_locker() -> None:
    """处理检查衣柜指令"""
    ui_hooks.switch_panel(constant.Panel.CHECK_LOCKER)


@add_instruct(constant.Instruct.COLLCET_PANTY)
def handle_collect_panty() -> None:
    """处理收起内裤指令"""
    pick_hooks.choose(constant.Behavior.SHARE_BLANKLY, 5)


@add_instruct(constant.Instruct.ASK_DATE)
def handle_ask_date() -> None:
    """处理邀请约会指令"""
    pick_hooks.choose(constant.Behavior.SHARE_BLANKLY, 5)


@add_instruct(constant.Instruct.CONFESSION)
def handle_confession() -> None:
    """处理告白指令：需要信赖≥200%且满足实行值，开始时交出戒指"""
    judge = _token_judge(_("告白"))
    if _token_accepted(judge):
        behavior_id = constant.Behavior.CONFESSION
        state = constant.CharacterStatus.STATUS_CONFESSION
    else:
        behavior_id = constant.Behavior.CONFESSION_FAILED
        state = constant.CharacterStatus.STATUS_CONFESSION_FAILED
    choose_instruct(behavior_id, 10, state=state, start="token", judge=judge)


@add_instruct(constant.Instruct.GIVE_NECKLACE)
def handle_give_necklace() -> None:
    """处理戴上项圈指令：需要信赖≥200%且满足实行值，开始时戴上项圈"""
    judge = _token_judge(_("戴上项圈"))
    if _token_accepted(judge):
        behavior_id = constant.Behavior.GIVE_NECKLACE
        state = constant.CharacterStatus.STATUS_GIVE_NECKLACE
    else:
        behavior_id = constant.Behavior.GIVE_NECKLACE_FAILED
        state = constant.CharacterStatus.STATUS_GIVE_NECKLACE_FAILED
    choose_instruct(behavior_id, 10, state=state, start="token", judge=judge)


def _token_judge(judge: str) -> str:
    """
    信物指令开始时开始门要过的判定：信赖≥200%时才判定
    Keyword arguments:
    judge -- 判定名
    Return arguments:
    str -- 信赖≥200%时为 judge，否则为空（不判定）
    """
    return judge if handle_premise.handle_target_trust_ge_200(0) else ""


def _token_accepted(judge: str) -> bool:
    """
    交互对象是否接受信物：有判定且判定通过（只判，不绘制、不扣催眠的理智；开始门再判时才扣）
    Keyword arguments:
    judge -- _token_judge 给出的判定名
    Return arguments:
    bool -- 接受时为真
    """
    return bool(
        judge
        and instuct_judege.calculation_instuct_judege(
            0,
            activity.target(0),
            judge,
            not_draw_flag=True,
            settle_hypnosis=False,
        )[0]
    )


@start_part("token")
def _give_token(who: int, chosen: intent.Intent) -> None:
    """
    告白、戴上项圈开始时：成功时交互对象的[恋慕]转为[恋人]（或[驯服]转为[宠物]）、得到信物，失败时提示条件
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    from Script.Design import handle_talent

    target_id = chosen["target"]
    target_data = identity.of(target_id)
    behavior_id = chosen["behavior_id"]
    if behavior_id == constant.Behavior.CONFESSION:
        old, new, mark = 202, 203, 205
        text = _(
            "\n告白成功，{0}收下了你赠予的[戒指]，[恋慕]转为[恋人]\n"
        ).format(target_data.name)
    elif behavior_id == constant.Behavior.GIVE_NECKLACE:
        old, new, mark = 212, 213, 215
        text = _(
            "\n{0}接受了项圈，戴在了自己的脖子上，[驯服]转为[宠物]\n"
        ).format(target_data.name)
    else:
        if behavior_id == constant.Behavior.CONFESSION_FAILED:
            text = _("\n告白失败，需要[恋慕]、信赖≥200%、且满足实行值\n")
        else:
            text = _("\n戴上项圈失败，需要[驯服]、信赖≥200%、且满足实行值\n")
        ui_hooks.emit_notice(text, wait=True, use_text_width=True)
        return
    abilities.talent(target_id)[old] = 0
    abilities.talent(target_id)[new] = 1
    # 记录陷落素质的获得时间与地点（此处直接赋值绕过了gain_talent，需补记）
    handle_talent.record_fall_talent_time(target_id, new)
    abilities.talent(target_id)[mark] = 1
    abilities.talent(target_id)[411] = 1
    player_collection.set_token(target_id, True)
    text += _("\n获得了{0}的信物：{1}\n").format(
        target_data.name, target_data.token_text
    )
    text += _("\n可以在[角色属性]-[角色设置]修改对彼此的称呼了\n")
    ui_hooks.emit_notice(text, wait=True, use_text_width=True)


@add_instruct(constant.Instruct.DRINK_ALCOHOL)
def handle_drink_alcohol() -> None:
    """处理劝酒指令"""
    pick_hooks.choose(constant.Behavior.SHARE_BLANKLY, 5)


@add_instruct(constant.Instruct.PEE)
def handle_pee() -> None:
    """处理解手指令"""
    chara_handle_instruct_common_settle(constant.Behavior.PEE)


@add_instruct(constant.Instruct.COLLECT)
def handle_collect() -> None:
    """处理摆放藏品指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.WAIT, duration=5, start="collect"
    )


@start_part("collect")
def _collect(who: int, chosen: intent.Intent) -> None:
    """
    摆放藏品开始时：收起身上的藏品
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    from Script.Modules.gameplay_resolution import collection_service

    collection_service.collapse_collection()


@add_instruct(constant.Instruct.DO_H)
def handle_do_h(place: str = "") -> None:
    """
    处理邀请H指令
    Keyword arguments:
    place -- 在特别地点H时，玩家与交互对象 h_state 里要设为真的那一项（如 h_in_love_hotel），为空时没有
    """
    chara_handle_instruct_common_settle(
        constant.Behavior.H,
        judge=_("H模式"),
        start="do_h",
        args={"place": place},
    )


@start_part("do_h")
def _start_do_h(who: int, chosen: intent.Intent) -> None:
    """
    邀请H开始时：记下特别地点，没关的门自动关上，交互对象停止跟随并记下进入H的时间，提示进入
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    target_data = identity.of(chosen["target"])
    place = str(chosen["args"]["place"])
    if place:
        h_state.set(who, **{place: True})
        h_state.set(chosen["target"], **{place: True})
    now_draw_text = "\n"
    now_scene_str = map_handle.get_map_system_path_str_for_list(
        activity.position(who)
    )
    # 如果没关门，则自动将门关上
    if scene_state.close_flag(now_scene_str) == 0:
        scene_state.set_close_flag(
            now_scene_str, constant.scene_data[now_scene_str].close_type
        )
        now_draw_text += _("已自动关门\n")
    flags.set(target_data.cid, is_follow=0)
    action_info.set(target_data.cid, "last_conscious_h_time", game_time.now())
    now_draw_text += _("进入H模式\n\n")
    ui_hooks.emit_notice(
        now_draw_text, wait=True, style="gold_enrod", use_text_width=True
    )


@start_part(constant.Behavior.DO_H_FAIL)
def _start_do_h_fail(who: int, chosen: intent.Intent) -> None:
    """
    邀请H判定没过、开始的是邀请H失败时：提示进入H模式失败
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    ui_hooks.emit_notice(
        _("\n进入H模式失败\n\n"),
        wait=True,
        style="warning",
        use_text_width=True,
    )


@add_instruct(constant.Instruct.DO_H_IN_LOVE_HOTEL)
def handle_do_h_in_love_hotel() -> None:
    """处理邀请在爱情旅馆H指令"""
    handle_do_h("h_in_love_hotel")


@add_instruct(constant.Instruct.DO_H_IN_BATHROOM)
def handle_do_h_in_bathroom() -> None:
    """处理邀请在浴室H指令"""
    handle_do_h("h_in_bathroom")


@add_instruct(constant.Instruct.DO_H_WITH_DAUGHTER)
def handle_do_h_with_daughter() -> None:
    """处理邀请乱伦H指令"""
    handle_do_h()


@add_instruct(constant.Instruct.PREPARE_TRAINING)
def handle_prepare_training() -> None:
    """
    处理调教前准备指令，经 pick_hooks.choose 定下种类为 prepare_training 的 10 分钟等待行动。
    行动以当前交互对象为目标，开始时由对应开始函数执行准备流程。
    Return arguments:
    None -- 经 pick_hooks.choose 结束本次选择，无正常返回值
    """
    pick_hooks.choose(
        constant.Behavior.WAIT,
        10,
        kind="prepare_training",
        target=activity.target(0),
        state=constant.CharacterStatus.STATUS_WAIT,
    )


@add_instruct(constant.Instruct.SWITCH_TO_H_INTERFACE)
def handle_switch_to_h_interface() -> None:
    """处理切换到H指令"""
    instruct_hooks.show_non_h(False)


@add_instruct(constant.Instruct.SLEEP_OBSCENITY)
def handle_sleep_obscenity() -> None:
    """处理睡眠猥亵指令"""
    target_data = identity.of(activity.target(0))
    now_scene_str = map_handle.get_map_system_path_str_for_list(
        activity.position(0)
    )
    if scene_state.close_flag(now_scene_str) == 0:
        door = ask_close_door()
        if door:
            _close_door(0, bool(door[CLOSE_DOOR]))
    flags.set(target_data.cid, unconscious_h=1)
    ui_hooks.emit_notice(
        _("\n进入睡眠猥亵模式\n"), wait=True, use_text_width=True
    )
    # 虽然在无意识奸中会刷新该数值，但是为了防止仅睡奸猥亵不H，在这里也初始化一下
    achievement.put("sleep_sex_record", {1: 0, 2: 0, 3: 0})


@add_instruct(constant.Instruct.STOP_SLEEP_OBSCENITY)
def handle_stop_sleep_obscenity() -> None:
    """处理停止睡眠猥亵指令"""
    from Script.Settle import default

    target_data = identity.of(activity.target(0))
    flags.set(target_data.cid, unconscious_h=0)
    ui_hooks.emit_notice(
        _("\n退出睡眠猥亵模式\n"), wait=True, use_text_width=True
    )
    default.handle_door_close_reset(
        0, 1, game_type.CharacterStatusChange(), datetime.datetime(1, 1, 1)
    )


@add_instruct(constant.Instruct.IMPRISONMENT_H)
def handle_imprisonment_h() -> None:
    """处理监禁奸指令"""
    handle_do_h()


@add_instruct(constant.Instruct.UNCONSCIOUS_H)
def handle_unconscious_h(type_name: str = "") -> None:
    """
    处理无意识奸指令
    type_name: str = ""  # 用于区分无意识奸类型
    """
    now_scene_str = map_handle.get_map_system_path_str_for_list(
        activity.position(0)
    )
    door: dict[str, object] = {}
    if scene_state.close_flag(
        now_scene_str
    ) == 0 and handle_premise.handle_time_stop_off(0):
        door = ask_close_door()
    chara_handle_instruct_common_settle(
        constant.Behavior.H,
        start="unconscious_h",
        args={"type": type_name, **door},
    )


@start_part("unconscious_h")
def _start_unconscious_h(who: int, chosen: intent.Intent) -> None:
    """
    无意识奸开始时：交互对象记下时间、停止跟随，按 args["type"] 进入睡奸、醉奸等模式并提示
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    from Script.Settle import default

    target_id = chosen["target"]
    type_name = chosen["args"]["type"]
    action_info.set(target_id, "last_unconscious_h_time", game_time.now())
    flags.set(target_id, is_follow=0)
    if type_name == "sleep":
        text = _("\n进入睡奸模式\n")
        default.handle_unconscious_flag_to_1(
            target_id, 1, game_type.CharacterStatusChange(), game_time.now()
        )
        achievement.put("sleep_sex_record", {1: 0, 2: 0, 3: 0})
    elif type_name == "drunk":
        text = _("\n进入醉奸模式\n")
        default.handle_unconscious_flag_to_2(
            target_id, 1, game_type.CharacterStatusChange(), game_time.now()
        )
        achievement.put("drunk_sex_record", {1: 0, 2: 0, 3: 0})
    elif type_name == "time_stop":
        text = _("\n进入时停奸模式\n")
    elif type_name == "hypnosis":
        text = _("\n进入催眠奸模式\n")
    else:
        text = _("\n进入无意识奸模式\n")
    ui_hooks.emit_notice(text, wait=True, use_text_width=True)


@add_instruct(constant.Instruct.SLEEP_H)
def handle_sleep_h() -> None:
    """处理睡奸指令"""
    handle_unconscious_h("sleep")


@add_instruct(constant.Instruct.DRUNK_H)
def handle_drunk_h() -> None:
    """处理醉奸指令"""
    handle_unconscious_h("drunk")


@add_instruct(constant.Instruct.TIME_STOP_H)
def handle_time_stop_h() -> None:
    """处理时停奸指令"""
    handle_unconscious_h("time_stop")


@add_instruct(constant.Instruct.HYPNOSIS_H)
def handle_hypnosis_h() -> None:
    """处理催眠奸指令"""
    handle_unconscious_h("hypnosis")


@add_instruct(constant.Instruct.ASK_HIDDEN_SEX)
def handle_ask_hidden_sex() -> None:
    """处理邀请隐奸指令"""
    ui_hooks.switch_panel(constant.Panel.ASK_HIDDEN_SEX)


@add_instruct(constant.Instruct.ASK_EXHIBITIONISM_SEX)
def handle_ask_exhibitionism_sex() -> None:
    """处理邀请露出指令"""
    ui_hooks.switch_panel(constant.Panel.ASK_EXHIBITIONISM_SEX)


@start_part(constant.Behavior.ASK_HIDDEN_SEX_FAIL)
def _start_ask_hidden_sex_fail(who: int, chosen: intent.Intent) -> None:
    """
    邀请隐奸判定没过、开始的是邀请隐奸失败时：提示邀请隐奸失败
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    ui_hooks.emit_notice(_("\n邀请隐奸失败\n"), wait=True)


@start_part(constant.Behavior.ASK_EXHIBITIONISM_SEX_FAIL)
def _start_ask_exhibitionism_sex_fail(who: int, chosen: intent.Intent) -> None:
    """
    邀请露出判定没过、开始的是邀请露出失败时：提示邀请露出失败
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    ui_hooks.emit_notice(_("\n邀请露出失败\n"), wait=True)


@add_instruct(constant.Instruct.ASK_GROUP_SEX)
def handle_ask_group_sex() -> None:
    """处理邀请群交指令：行动开始时场景里的干员逐个判定实行值，全部同意时进入群交模式"""
    choose_instruct(
        constant.Behavior.ASK_GROUP_SEX,
        5,
        state=constant.CharacterStatus.STATUS_ASK_GROUP_SEX,
        judge=_("群交"),
        start="ask_group_sex",
    )


_group_members = instruct_plan_service.group_members
_judged_group_sex = instruct_plan_service.judged_group_sex


def _ints(value: core.JSON) -> list[int]:
    """
    Intent.args 里的整数列表（内核冻结后是元组），如角色id、存量池下标
    Keyword arguments:
    value -- args 里的值
    Return arguments:
    list -- 整数
    """
    assert isinstance(value, tuple | list)
    return [int(c) for c in value if isinstance(c, int)]


@start_part("ask_group_sex")
def _start_ask_group_sex(who: int, chosen: intent.Intent) -> None:
    """
    邀请群交开始时：提示进入群交模式，场景里的干员都排上加入群交
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    from Script.Modules.gameplay_resolution import plan_queue

    ui_hooks.emit_notice(_("\n进入群交模式\n"), wait=True, use_text_width=True)
    for chara_id in _group_members(who):
        plan_queue.plan_next(
            chara_id,
            constant.Behavior.JOIN_GROUP_SEX,
            _instruct_duration(constant.Behavior.JOIN_GROUP_SEX, 0),
            interrupt=True,
        )


@start_part(constant.Behavior.ASK_GROUP_SEX_FAIL)
def _start_ask_group_sex_fail(who: int, chosen: intent.Intent) -> None:
    """
    邀请群交判定没过、开始的是邀请群交失败时：提示拒绝的人，场景里的干员都排上1分钟的等待
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    from Script.Modules.gameplay_resolution import plan_queue

    text = _("\n进入群交模式失败\n")
    for chara_id in action_info.get(who, "ask_group_sex_refuse_chara_id_list"):
        text += _("{0}拒绝了群交\n").format(identity.of(chara_id).name)
    ui_hooks.emit_notice(text, wait=True, use_text_width=True)
    for chara_id in _group_members(who):
        plan_queue.plan_next(
            chara_id,
            constant.Behavior.WAIT,
            1,
            state=constant.CharacterStatus.STATUS_WAIT,
            interrupt=True,
        )


@add_instruct(constant.Instruct.WAIT_5_MIN_IN_H)
def handle_wait_5_min_in_h() -> None:
    """处理等待五分钟指令"""
    # 如果场景里已经没有除自己以外的在H中的角色，则转为结束H
    now_scene_character_list = map_handle.get_chara_now_scene_all_chara_id_list(
        0, remove_own_character=True
    )
    h_in_scene_flag = False
    for now_chara_id in now_scene_character_list:
        if handle_premise.handle_self_is_h(now_chara_id):
            h_in_scene_flag = True
            break
    if not h_in_scene_flag:
        handle_h_end()
    # 否则正常等待五分钟
    else:
        chara_handle_instruct_common_settle(constant.Behavior.WAIT, duration=5)


@add_instruct(constant.Instruct.H_END)
def handle_h_end(daughter: bool = False) -> None:
    """
    处理H结束指令：玩家结束5分钟，开始时对方原地等待10分钟
    Keyword arguments:
    daughter -- 是否是乱伦H的结束（开始时记成就）
    """
    behavior_id, state = _planned_end(
        None, constant.Behavior.END_H, constant.CharacterStatus.STATUS_END_H
    )
    choose_instruct(
        behavior_id,
        5,
        state=state,
        start="h_end",
        args={"daughter": daughter},
    )


@start_part("h_end")
def _start_h_end(who: int, chosen: intent.Intent) -> None:
    """
    结束H开始时：乱伦H记成就，正常结束时对方进入跟随，对方原地等待10分钟，提示结束
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    if chosen["args"]["daughter"]:
        achievement.add("h_with_daughter_count", 1)
        achievement_service.settle_and_notify(_("乱伦"))
    _h_end_others(chosen["behavior_id"], chosen["target"])


def _h_end_others(behavior_id: str, target_id: int) -> None:
    """
    结束H时玩家以外的处理：正常结束时对方进入跟随，对方排上原地等待10分钟，提示结束
    Keyword arguments:
    behavior_id -- 玩家的结束行为
    target_id -- 对方的角色id，0 为没有
    """
    from Script.Modules.gameplay_resolution import plan_queue

    if behavior_id == constant.Behavior.END_H:
        _h_end_follow(target_id)
    if target_id != 0:
        plan_queue.plan_next(
            target_id,
            constant.Behavior.WAIT,
            10,
            state=constant.CharacterStatus.STATUS_WAIT,
            interrupt=True,
        )
    _draw_end_text(_("\n结束H模式\n"))


def _h_end_follow(target_character_id: int) -> None:
    """
    正常结束H时，异常1、2、6都正常的对方进入跟随
    Keyword arguments:
    target_character_id -- 对方的角色id
    """
    if (
        handle_premise.handle_normal_1(target_character_id)
        and handle_premise.handle_normal_2(target_character_id)
        and handle_premise.handle_normal_6(target_character_id)
    ):
        flags.set(target_character_id, is_follow=1)


def _draw_end_text(text: str) -> None:
    """
    绘制结束H的提示并等玩家确认
    Keyword arguments:
    text -- 提示文本
    """
    ui_hooks.emit_notice(text, wait=True, use_text_width=True)


def _planned_end(
    end_behavior_id: str | None, normal_end: str, normal_state: int | str
) -> tuple[str, int | str]:
    """
    结束H时玩家接着做的行为与状态：指定了特殊结束时用它、状态不变，玩家正在特殊结束时保留，否则正常结束
    Keyword arguments:
    end_behavior_id -- 指定的结束行为，None 为不指定
    normal_end -- 正常结束的行为id
    normal_state -- 正常结束的角色状态
    Return arguments:
    tuple -- 行为id与角色状态
    """
    if end_behavior_id == normal_end:
        return normal_end, normal_state
    if end_behavior_id is not None:
        return end_behavior_id, activity.state(0)
    if activity.behavior(0).behavior_id in constant.special_end_H_list:
        return activity.behavior(0).behavior_id, activity.state(0)
    return normal_end, normal_state


def _end_planned(normal_end: str) -> bool:
    """
    玩家的计划队列里是否已排着这种结束（正常结束或任一特殊结束）
    Keyword arguments:
    normal_end -- 正常结束的行为id
    Return arguments:
    bool -- 已排着时为真
    """
    from Script.Modules.gameplay_resolution import plan_queue

    ends = {normal_end, *constant.special_end_H_list}
    return any(p["behavior_id"] in ends for p in plan_queue.planned(0))


def plan_h_end(
    end_behavior_id: str | None = None,
) -> tuple[core.Interrupt, ...]:
    """
    结算途中用的结束H：当场写入并显示"结束H模式"，玩家的结束行动（5分钟）与对方的等待（10分钟）排进计划队列
    Keyword arguments:
    end_behavior_id -- 玩家的特殊结束行为，None 时照玩家当前的行为定
    Return arguments:
    tuple -- 空元组：排下的打断由计划队列在这一步交给内核
    """
    from Script.Modules.gameplay_resolution import plan_queue

    if _end_planned(constant.Behavior.END_H):
        return ()
    behavior_id, state = _planned_end(
        end_behavior_id,
        constant.Behavior.END_H,
        constant.CharacterStatus.STATUS_END_H,
    )
    _h_end_others(behavior_id, activity.target(0))
    plan_queue.plan_next(0, behavior_id, 5, state=state)
    return ()


@add_instruct(constant.Instruct.H_WITH_DAUGHTER_END)
def handle_h_with_daughter_end() -> None:
    """处理结束乱伦H指令"""
    handle_h_end(daughter=True)


@add_instruct(constant.Instruct.IMPRISONMENT_H_END)
def handle_imprisonment_h_end() -> None:
    """处理结束监禁奸指令"""
    handle_h_end()


@add_instruct(constant.Instruct.UNCONSCIOUS_H_END)
def handle_unconscious_h_end() -> None:
    """处理结束无意识奸指令"""
    choose_instruct(
        constant.Behavior.NO_CONSCIOUS_H_END,
        5,
        state=constant.CharacterStatus.STATUS_NO_CONSCIOUS_H_END,
        start="unconscious_h_end",
    )


@start_part("unconscious_h_end")
def _start_unconscious_h_end(who: int, chosen: intent.Intent) -> None:
    """
    结束无意识奸开始时：结算成就，提示结束
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    achievement_service.settle_and_notify(_("睡奸"))
    _draw_end_text(_("\n结束无意识奸\n"))


@add_instruct(constant.Instruct.HIDDEN_SEX_END)
def handle_hidden_sex_end() -> None:
    """处理结束隐奸指令"""
    choose_instruct(
        constant.Behavior.END_H,
        5,
        state=constant.CharacterStatus.STATUS_END_H,
        start="sex_mode_end",
        args={"mode": "hidden"},
    )


@add_instruct(constant.Instruct.EXHIBITIONISM_SEX_END)
def handle_exhibitionism_sex_end() -> None:
    """处理结束露出指令"""
    choose_instruct(
        constant.Behavior.END_H,
        5,
        state=constant.CharacterStatus.STATUS_END_H,
        start="sex_mode_end",
        args={"mode": "exhibitionism"},
    )


@start_part("sex_mode_end")
def _start_sex_mode_end(who: int, chosen: intent.Intent) -> None:
    """
    结束隐奸、露出开始时：异常1、2、6都正常的对方进入跟随，结算成就，对方原地等待10分钟，提示结束
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    from Script.Modules.gameplay_resolution import plan_queue

    target_id = chosen["target"]
    _h_end_follow(target_id)
    if chosen["args"]["mode"] == "hidden":
        achievement_service.settle_and_notify(_("隐奸"))
        text = _("\n结束隐奸\n")
    else:
        achievement_service.settle_and_notify(_("露出"))
        text = _("\n结束露出\n")
    if target_id != 0:
        plan_queue.plan_next(
            target_id,
            constant.Behavior.WAIT,
            10,
            state=constant.CharacterStatus.STATUS_WAIT,
            interrupt=True,
        )
    _draw_end_text(text)


@add_instruct(constant.Instruct.START_SEX_CLASS)
def handle_start_sex_class() -> None:
    """处理性技实操课（开课）指令"""
    from Script.System.Education_System import (
        education_constant,
        sex_class_handle,
    )

    student_list = sex_class_handle.get_scene_student_list()
    if not student_list:
        ui_hooks.emit_notice(
            _("\n这里没有可以上课的学生。\n"), wait=True, use_text_width=True
        )
        return
    # 选主修科目：预约的那节课已经定好了（提前几分钟开讲的也算，Plan 26 §3.5），当场开课则现选一门
    classroom = sex_class_handle.get_scene_name(activity.position(0))
    temp_class = sex_class_handle.find_class_to_start(
        classroom, game_time.now()
    )[1]
    ability_id = -1
    if temp_class is not None:
        ability_id = temp_class.get("ability_id", -1)
    if ability_id not in education_constant.SEX_CLASS_ABILITY_LIST:
        ability_id = instruct_hooks.ask_sex_class_ability(
            education_constant.SEX_CLASS_ABILITY_LIST
        )
        if ability_id == -1:
            return
    # 交互对象取第一名学生：行为效果串里的464会让交互对象进H，其余学生由10014的结算器补上
    chara_handle_instruct_common_settle(
        constant.Behavior.START_SEX_CLASS,
        target_character_id=student_list[0],
        start="start_sex_class",
        args={"ability_id": ability_id, "students": student_list},
    )


@start_part("start_sex_class")
def _start_sex_class(who: int, chosen: intent.Intent) -> None:
    """
    性技实操课开课时：建/取本节课的数据并记出勤，之后模式开关、主修加成、旁观结算都从这条数据读
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    from Script.System.Education_System import sex_class_handle

    ability_id = chosen["args"]["ability_id"]
    assert isinstance(ability_id, int)
    sex_class_handle.start_sex_class(
        ability_id, _ints(chosen["args"]["students"])
    )


@add_instruct(constant.Instruct.END_SEX_CLASS)
def handle_end_sex_class() -> None:
    """处理结束性技实操课（下课）指令：玩家下课5分钟，开始时场景内H中的角色原地等待10分钟"""
    behavior_id, state = _planned_end(
        None, constant.Behavior.END_SEX_CLASS, constant.Behavior.END_SEX_CLASS
    )
    choose_instruct(
        behavior_id,
        5,
        state=state,
        start="h_members_wait",
        args={"text": "end_sex_class"},
    )


@add_instruct(constant.Instruct.GROUP_SEX_END)
def handle_group_sex_end() -> None:
    """处理结束群交指令：玩家结束5分钟，开始时场景内H中的角色原地等待10分钟"""
    behavior_id, state = _planned_end(
        None,
        constant.Behavior.GROUP_SEX_END,
        constant.CharacterStatus.STATUS_GROUP_SEX_END,
    )
    choose_instruct(
        behavior_id,
        5,
        state=state,
        start="h_members_wait",
        args={"text": "group_sex_end"},
    )


@start_part("h_members_wait")
def _start_h_members_wait(who: int, chosen: intent.Intent) -> None:
    """
    下课、结束群交开始时：场景内H中的角色排上原地等待10分钟，提示结束
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    _h_members_wait()
    if chosen["args"]["text"] == "end_sex_class":
        _draw_end_text(_("\n下课\n"))
    else:
        _draw_end_text(_("\n结束群交模式\n"))


def _h_members_wait() -> None:
    """场景内H中的角色打断手上的行动，排上原地等待10分钟"""
    from Script.Modules.gameplay_resolution import plan_queue

    for chara_id in _scene_h_members():
        plan_queue.plan_next(
            chara_id,
            constant.Behavior.WAIT,
            10,
            state=constant.CharacterStatus.STATUS_WAIT,
            interrupt=True,
        )


def _scene_h_members() -> list[int]:
    """
    和玩家同场景、在H中的角色
    Return arguments:
    list -- 角色id
    """
    now_scene_character_list = map_handle.get_chara_now_scene_all_chara_id_list(
        0, remove_own_character=True
    )
    return [
        c
        for c in now_scene_character_list
        if handle_premise.handle_self_is_h(c)
    ]


def plan_group_sex_end(
    end_behavior_id: str | None = None,
) -> tuple[core.Interrupt, ...]:
    """
    结算途中用的结束群交：当场显示"结束群交模式"，玩家的结束行动（5分钟）与在场H中各人的等待（10分钟）排进计划队列
    Keyword arguments:
    end_behavior_id -- 玩家的特殊结束行为，None 时照玩家当前的行为定
    Return arguments:
    tuple -- 空元组：排下的打断由计划队列在这一步交给内核
    """
    from Script.Modules.gameplay_resolution import plan_queue

    if _end_planned(constant.Behavior.GROUP_SEX_END):
        return ()
    behavior_id, state = _planned_end(
        end_behavior_id,
        constant.Behavior.GROUP_SEX_END,
        constant.CharacterStatus.STATUS_GROUP_SEX_END,
    )
    _h_members_wait()
    _draw_end_text(_("\n结束群交模式\n"))
    plan_queue.plan_next(0, behavior_id, 5, state=state)
    return ()


# 以下为娱乐#


@add_instruct(constant.Instruct.SINGING)
def handle_singing() -> None:
    """处理唱歌指令"""
    # 如果音乐等级过低，且周围有其他角色，则进行需要确认再唱歌
    if abilities.ability(0)[44] <= 2 and handle_premise.handle_scene_over_one(
        0
    ):
        if not instruct_hooks.confirm_poor_music():
            return
    chara_handle_instruct_common_settle(constant.Behavior.SINGING)


@add_instruct(constant.Instruct.PLAY_INSTRUMENT)
def handle_play_instrument() -> None:
    """处理演奏乐器指令"""
    # 如果音乐等级过低，且周围有其他角色，则进行需要确认再演奏
    if abilities.ability(0)[44] <= 2 and handle_premise.handle_scene_over_one(
        0
    ):
        if not instruct_hooks.confirm_poor_music():
            return
    chara_handle_instruct_common_settle(constant.Behavior.PLAY_INSTRUMENT)


@add_instruct(constant.Instruct.WATCH_MOVIE)
def handle_watch_movie() -> None:
    """处理看电影指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.WATCH_MOVIE, force_taget_wait=True
    )


@add_instruct(constant.Instruct.PHOTOGRAPHY)
def handle_photography() -> None:
    """处理摄影指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.PHOTOGRAPHY, force_taget_wait=True
    )


@add_instruct(constant.Instruct.PLAY_WATER)
def handle_play_water() -> None:
    """处理玩水指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.PLAY_WATER, force_taget_wait=True
    )


@add_instruct(constant.Instruct.PLAY_GOMOKU)
def handle_play_gomoku() -> None:
    """处理下五子棋指令"""
    ui_hooks.switch_panel(constant.Panel.PLAY_GOMOKU)


@add_instruct(constant.Instruct.PLAY_CHESS)
def handle_play_chess() -> None:
    """处理下棋指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.PLAY_CHESS, force_taget_wait=True
    )


@add_instruct(constant.Instruct.PLAY_MAHJONG)
def handle_play_mahjong() -> None:
    """处理打麻将指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.PLAY_MAHJONG, force_taget_wait=True
    )


@add_instruct(constant.Instruct.PLAY_CARDS)
def handle_play_cards() -> None:
    """处理打牌指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.PLAY_CARDS, force_taget_wait=True
    )


@add_instruct(constant.Instruct.REHEARSE_DANCE)
def handle_rehearse_dance() -> None:
    """处理排演舞剧指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.REHEARSE_DANCE, force_taget_wait=True
    )


@add_instruct(constant.Instruct.PLAY_ARCADE_GAME)
def handle_play_arcade_game() -> None:
    """处理玩街机游戏指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.PLAY_ARCADE_GAME, force_taget_wait=True
    )


@add_instruct(constant.Instruct.SWIMMING)
def handle_swimming() -> None:
    """处理游泳指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.SWIMMING, force_taget_wait=True
    )


@add_instruct(constant.Instruct.TASTE_WINE)
def handle_taste_wine() -> None:
    """处理品酒指令"""
    ui_hooks.switch_panel(constant.Panel.FOOD_BAG)


@add_instruct(constant.Instruct.TASTE_TEA)
def handle_taste_tea() -> None:
    """处理品茶指令"""
    chara_handle_instruct_common_settle(constant.Behavior.TASTE_TEA)


@add_instruct(constant.Instruct.TASTE_COFFEE)
def handle_taste_coffee() -> None:
    """处理品咖啡指令"""
    chara_handle_instruct_common_settle(constant.Behavior.TASTE_COFFEE)


@add_instruct(constant.Instruct.TASTE_DESSERT)
def handle_taste_dessert() -> None:
    """处理品尝点心指令"""
    chara_handle_instruct_common_settle(constant.Behavior.TASTE_DESSERT)


@add_instruct(constant.Instruct.TASTE_FOOD)
def handle_taste_food() -> None:
    """处理品尝美食指令"""
    chara_handle_instruct_common_settle(constant.Behavior.TASTE_FOOD)


@add_instruct(constant.Instruct.PLAY_HOUSE)
def handle_play_house() -> None:
    """处理过家家指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.PLAY_HOUSE, force_taget_wait=True
    )


@add_instruct(constant.Instruct.STYLE_HAIR)
def handle_style_hair() -> None:
    """处理修整发型指令"""
    chara_handle_instruct_common_settle(constant.Behavior.STYLE_HAIR)


@add_instruct(constant.Instruct.FULL_BODY_STYLING)
def handle_full_body_styling() -> None:
    """处理全身造型服务指令"""
    chara_handle_instruct_common_settle(constant.Behavior.FULL_BODY_STYLING)


@add_instruct(constant.Instruct.SOAK_FEET)
def handle_soak_feet() -> None:
    """处理泡脚指令"""
    chara_handle_instruct_common_settle(constant.Behavior.SOAK_FEET)


@add_instruct(constant.Instruct.STEAM_SAUNA)
def handle_steam_sauna() -> None:
    """处理蒸桑拿指令"""
    chara_handle_instruct_common_settle(constant.Behavior.STEAM_SAUNA)


@add_instruct(constant.Instruct.HYDROTHERAPY_TREATMENT)
def handle_hydrotherapy_treatment() -> None:
    """处理水疗护理指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.HYDROTHERAPY_TREATMENT
    )


@add_instruct(constant.Instruct.ONSEN_BATH)
def handle_onsen_bath() -> None:
    """处理泡温泉指令"""
    chara_handle_instruct_common_settle(constant.Behavior.ONSEN_BATH)


@add_instruct(constant.Instruct.AROMATHERAPY)
def handle_aromatherapy() -> None:
    """处理香薰疗愈指令"""
    ui_hooks.switch_panel(constant.Panel.AROMATHERAPY)


# 以下为工作#


@add_instruct(constant.Instruct.OFFICIAL_WORK)
def handle_official_work() -> None:
    """
    处理公务指令，先经 choose_official_option 为待决断队列中第一条可选公务事件选定选项。
    选定后随处理公务行动带入 official_option 开始代码，在行动开始时结算。
    Return arguments:
    None -- 经行动选择结束本次处理，无正常返回值
    """
    option = choose_official_option()
    chara_handle_instruct_common_settle(
        constant.Behavior.OFFICIAL_WORK,
        force_taget_wait=True,
        start="official_option" if option else "",
        args=option,
    )


@start_part("official_option")
def _start_official_option(who: int, chosen: intent.Intent) -> None:
    """
    处理公务行动开始时，按行动参数中的公务选项调用 settle_official_option 完成结算并显示后果。
    Keyword arguments:
    who -- int，执行行动的角色编号，本函数不使用
    chosen -- intent.Intent，本次行动的意图，其 args 包含 uid、chara_id、partner_id 与 option
    Return arguments:
    None -- 无返回值
    """
    settle_official_option(chosen["args"])


def choose_official_option() -> dict[str, object] | None:
    """
    初始化公务事件提供者并逐条出队待决断事件，经 instruct_hooks.ask_official_option 询问选项。
    返回非零选项序号时立即返回该事件选项字典。
    返回 0 时以选项 0 调用 record_event_done 记入履历，以免事件保持未完成状态而被再次派发。
    Return arguments:
    dict[str, object] | None -- 含 uid、chara_id、partner_id 与 option 的字典，队列无可选事件时为 None
    """
    from Script.System.Official_Event_System import official_event_handle

    official_event_handle.init_provider()
    while (
        queue_data := official_event_handle.pop_official_event()
    ) is not None:
        uid, character_id = queue_data["uid"], queue_data.get("chara_id", 0)
        option_index = instruct_hooks.ask_official_option(queue_data)
        if option_index:
            partner_id = queue_data.get("partner_id", 0)
            return {
                "uid": uid,
                "chara_id": character_id,
                "partner_id": partner_id,
                "option": option_index,
            }
        official_event_handle.record_event_done(uid, character_id, 0)
    return None


def settle_official_option(option: Mapping[str, Any]) -> None:
    """
    调用 official_event_handle.settle_official_event_option 结算已选公务选项并写入履历。
    结算完成后，经 instruct_hooks.show_official_result 展示该选项的后果。
    Keyword arguments:
    option -- Mapping[str, Any]，包含 uid、chara_id、partner_id 与 option 的选项映射
    Return arguments:
    None -- 无返回值
    """
    from Script.System.Official_Event_System import official_event_handle

    uid = str(option["uid"])
    character_id = int(option["chara_id"])
    partner_id = int(option["partner_id"])
    option_index = int(option["option"])
    official_event_handle.settle_official_event_option(
        uid, character_id, partner_id, option_index
    )
    instruct_hooks.show_official_result(
        uid, character_id, partner_id, option_index
    )


@add_instruct(constant.Instruct.BATTLE_COMMAND)
def handle_battle_command() -> None:
    """处理指挥作战指令"""
    pick_hooks.choose(constant.Behavior.SHARE_BLANKLY, 5)


@add_instruct(constant.Instruct.ASSISTANT_ADJUSTMENTS)
def handle_ASSISTANT_ADJUSTMENTS() -> None:
    """处理助理相关调整指令"""
    ui_hooks.switch_panel(constant.Panel.ASSISTANT)


@add_instruct(constant.Instruct.BUILDING)
def handle_building() -> None:
    """处理基建系统指令"""
    ui_hooks.switch_panel(constant.Panel.BUILDING)


@add_instruct(constant.Instruct.EQUIPMENT_MAINTAIN)
def handle_equipment_maintain() -> None:
    """处理管理装备维护指令"""
    ui_hooks.switch_panel(constant.Panel.EQUIPMENT_MAINTAIN)


@add_instruct(constant.Instruct.RECRUITMENT)
def handle_recruiment() -> None:
    """处理招募情况指令"""
    ui_hooks.switch_panel(constant.Panel.RECRUITMENT)


@add_instruct(constant.Instruct.VISITOR_SYSTEM)
def handle_visitor_system() -> None:
    """处理访客系统指令"""
    ui_hooks.switch_panel(constant.Panel.VISITOR)


@add_instruct(constant.Instruct.NATION_DIPLOMACY)
def handle_nation_diplomacy() -> None:
    """处理势力与外交指令"""
    ui_hooks.switch_panel(constant.Panel.NATION_DIPLOMACY)


@add_instruct(constant.Instruct.INVITE_VISITOR)
def handle_invite_visitor() -> None:
    """处理邀请访客指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.INVITE_VISITOR, force_taget_wait=True
    )


@add_instruct(constant.Instruct.PRTS)
def handle_prts() -> None:
    """处理普瑞赛斯指令"""
    ui_hooks.switch_panel(constant.Panel.PRTS)


@add_instruct(constant.Instruct.TRAINING)
def handle_training() -> None:
    """处理战斗训练指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.TRAINING, force_taget_wait=True
    )


@add_instruct(constant.Instruct.EXERCISE)
def handle_exercise() -> None:
    """处理锻炼身体指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.EXERCISE, force_taget_wait=True
    )


@add_instruct(constant.Instruct.CURE_PATIENT)
def handle_cure_patient() -> None:
    """处理诊疗病人指令"""
    # 如果当前没有病人，输出提示并返回
    if not handle_premise.handle_patient_wait(0):
        ui_hooks.emit_notice(
            _("\n当前没有需要诊疗的病人\n"), wait=True, use_text_width=True
        )
        return
    ui_hooks.switch_panel(constant.Panel.CURE_PATIENT)


@add_instruct(constant.Instruct.MANAGE_DEDICAL_DEPARTMENT)
def handle_manage_dedical_department() -> None:
    """处理管理医疗系统指令"""
    ui_hooks.switch_panel(constant.Panel.MANAGE_DEDICAL_DEPARTMENT)


@add_instruct(constant.Instruct.RECRUIT)
def handle_recruit() -> None:
    """处理招募干员指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.RECRUIT, force_taget_wait=True
    )


@add_instruct(constant.Instruct.CONFIM_RECRUIT)
def handle_confim_recruit() -> None:
    """处理确认已招募干员指令：有空余宿舍与待确认的干员时定下 5 分钟的等待，开始时招募（开始代码 recruit）"""
    from Script.Modules.gameplay_resolution import recruit_service

    if recruit_service.can_recruit():
        chara_handle_instruct_common_settle(
            constant.Behavior.WAIT, duration=5, start="recruit"
        )


@start_part("recruit")
def _start_recruit(who: int, chosen: intent.Intent) -> None:
    """
    确认招募的行动开始时：招募一名待确认的干员（含成就结算）
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    from Script.Modules.gameplay_resolution import recruit_service

    recruit_service.recruit_new_chara()


@add_instruct(constant.Instruct.MAINTENANCE_FACILITIES)
def handle_maintenance_facilities() -> None:
    """处理维护设施指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.MAINTENANCE_FACILITIES
    )


@add_instruct(constant.Instruct.MANAGE_FACILITY_POWER)
def handle_manage_facility_power() -> None:
    """处理调控设施供能指令"""
    chara_handle_instruct_common_settle(constant.Behavior.MANAGE_FACILITY_POWER)


@add_instruct(constant.Instruct.MANAGE_POWER_SYSTEM)
def handle_manage_power_system() -> None:
    """处理管理能源系统指令"""
    ui_hooks.switch_panel(constant.Panel.MANAGE_POWER_SYSTEM)


@add_instruct(constant.Instruct.REPAIR_EQUIPMENT)
def handle_repair_equipment() -> None:
    """处理维修装备指令"""
    chara_handle_instruct_common_settle(constant.Behavior.REPAIR_EQUIPMENT)


# 以下为猥亵#


@add_instruct(constant.Instruct.EMBRACE)
def handle_embrace() -> None:
    """处理拥抱指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.EMBRACE, judge=_("初级骚扰"), force_taget_wait=True
    )


@add_instruct(constant.Instruct.KISS)
def handle_kiss() -> None:
    """处理亲吻指令"""
    chara_handle_instruct_common_settle(constant.Behavior.KISS, judge=_("亲吻"))


@add_instruct(constant.Instruct.TOUCH_HEAD)
def handle_touch_head() -> None:
    """处理摸头指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.TOUCH_HEAD, judge=_("初级骚扰")
    )


@add_instruct(constant.Instruct.TOUCH_BREAST)
def handle_touch_breast() -> None:
    """处理摸胸指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.TOUCH_BREAST, judge=_("初级骚扰")
    )


@add_instruct(constant.Instruct.TOUCH_BUTTOCKS)
def handle_touch_buttocks() -> None:
    """处理摸屁股指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.TOUCH_BUTTOCKS, judge=_("初级骚扰")
    )


@add_instruct(constant.Instruct.TOUCH_EARS)
def handle_touch_ears() -> None:
    """处理摸耳朵指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.TOUCH_EARS, judge=_("初级骚扰")
    )


@add_instruct(constant.Instruct.TOUCH_HORN)
def handle_touch_horn() -> None:
    """处理摸角指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.TOUCH_HORN, judge=_("初级骚扰")
    )


@add_instruct(constant.Instruct.TOUCH_TAIL)
def handle_touch_tail() -> None:
    """处理摸尾巴指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.TOUCH_TAIL, judge=_("初级骚扰")
    )


@add_instruct(constant.Instruct.TOUCH_RING)
def handle_touch_ring() -> None:
    """处理摸光环指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.TOUCH_RING, judge=_("初级骚扰")
    )


@add_instruct(constant.Instruct.TOUCH_WING)
def handle_touch_wing() -> None:
    """处理摸翅膀指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.TOUCH_WING, judge=_("初级骚扰")
    )


@add_instruct(constant.Instruct.TOUCH_TENTACLE)
def handle_touch_tentacle() -> None:
    """处理摸触手指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.TOUCH_TENTACLE, judge=_("初级骚扰")
    )


@add_instruct(constant.Instruct.TOUCH_CAR)
def handle_touch_car() -> None:
    """处理摸小车指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.TOUCH_CAR, judge=_("初级骚扰")
    )


@add_instruct(constant.Instruct.HAND_IN_HAND)
def handle_handle_in_handle() -> None:
    """处理牵手指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.HAND_IN_HAND, judge=_("初级骚扰")
    )


@add_instruct(constant.Instruct.LAP_PILLOW)
def handle_lap_pillow() -> None:
    """处理膝枕指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.LAP_PILLOW, judge=_("初级骚扰")
    )


@add_instruct(constant.Instruct.RAISE_SKIRT)
def handle_raise_skirt() -> None:
    """处理掀起裙子指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.RAISE_SKIRT, judge=_("严重骚扰")
    )


@add_instruct(constant.Instruct.ASK_FOR_PAN)
def handle_ask_for_pan() -> None:
    """处理索要内裤指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.ASK_FOR_PAN, judge=_("严重骚扰")
    )


@add_instruct(constant.Instruct.ASK_FOR_SOCKS)
def handle_ask_for_socks() -> None:
    """处理索要袜子指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.ASK_FOR_SOCKS, judge=_("严重骚扰")
    )


@add_instruct(constant.Instruct.INVITE_TO_BATH)
def handle_invite_to_bath() -> None:
    """处理一起洗澡指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.INVITE_TO_BATH,
        judge=_("严重骚扰"),
        force_taget_wait=True,
    )


@add_instruct(constant.Instruct.ASK_COPY_KEY)
def handle_ask_copy_key() -> None:
    """处理要求复制钥匙指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.ASK_COPY_KEY, judge=_("严重骚扰")
    )


@add_instruct(constant.Instruct.STEAL_PAN)
def handle_steal_pan() -> None:
    """处理偷走内裤指令"""
    chara_handle_instruct_common_settle(constant.Behavior.STEAL_PAN)


@add_instruct(constant.Instruct.STEAL_SOCKS)
def handle_steal_socks() -> None:
    """处理偷走袜子指令"""
    chara_handle_instruct_common_settle(constant.Behavior.STEAL_SOCKS)


@add_instruct(constant.Instruct.STEAL_SCENE_ALL_PAN)
def handle_steal_scene_all_pan() -> None:
    """处理偷走所有人内裤指令"""
    chara_handle_instruct_common_settle(constant.Behavior.STEAL_SCENE_ALL_PAN)


@add_instruct(constant.Instruct.STEAL_SCENE_ALL_SOCKS)
def handle_steal_scene_all_socks() -> None:
    """处理偷走所有人袜子指令"""
    chara_handle_instruct_common_settle(constant.Behavior.STEAL_SCENE_ALL_SOCKS)


@add_instruct(constant.Instruct.TOUCH_CLITORIS)
def handle_touch_clitoris() -> None:
    """处理阴蒂爱抚指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.TOUCH_CLITORIS, judge=_("严重骚扰")
    )


@add_instruct(constant.Instruct.TOUCH_VAGINA)
def handle_touch_vagina() -> None:
    """处理手指插入（V）指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.TOUCH_VAGINA, judge=_("严重骚扰")
    )


@add_instruct(constant.Instruct.TOUCH_ANUS)
def handle_touch_anus() -> None:
    """处理手指插入（A）指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.TOUCH_ANUS, judge=_("严重骚扰")
    )


@add_instruct(constant.Instruct.MILK)
def handle_milk() -> None:
    """处理挤奶指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.MILK, judge=_("严重骚扰")
    )


@add_instruct(constant.Instruct.REMOTE_TOY_ON)
def handle_remote_toy_on() -> None:
    """处理遥控启动玩具指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.REMOTE_TURN_ON_SEX_TOY, judge=_("严重骚扰")
    )


@add_instruct(constant.Instruct.REMOTE_TOY_OFF)
def handle_remote_toy_off() -> None:
    """处理遥控关闭玩具指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.REMOTE_TURN_OFF_SEX_TOY
    )


@add_instruct(constant.Instruct.REMOTE_TOY_LEVEL_UP)
def handle_remote_toy_level_up() -> None:
    """处理调高玩具档位指令"""
    if handle_premise.handle_target_now_sex_toy_weak(0):
        chara_handle_instruct_common_settle(
            constant.Behavior.REMOTE_SET_SEX_TOY_WEAK_TO_MEDIUM,
            judge=_("严重骚扰"),
        )
    else:
        chara_handle_instruct_common_settle(
            constant.Behavior.REMOTE_SET_SEX_TOY_STRONG, judge=_("严重骚扰")
        )


@add_instruct(constant.Instruct.REMOTE_TOY_LEVEL_DOWN)
def handle_remote_toy_level_down() -> None:
    """处理降低玩具档位指令"""
    if handle_premise.handle_target_now_sex_toy_strong(0):
        chara_handle_instruct_common_settle(
            constant.Behavior.REMOTE_SET_SEX_TOY_STRONG_TO_MEDIUM,
            judge=_("严重骚扰"),
        )
    else:
        chara_handle_instruct_common_settle(
            constant.Behavior.REMOTE_SET_SEX_TOY_WEAK, judge=_("严重骚扰")
        )


@add_instruct(constant.Instruct.REMOTE_TOY_ALL_OFF)
def handle_remote_toy_all_off() -> None:
    """处理遥控关闭全员玩具指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.REMOTE_ALL_TURN_OFF_SEX_TOY
    )


@add_instruct(constant.Instruct.REMOTE_ALL_SET_SEX_TOY_WEAK)
def handle_remote_all_set_sex_toy_weak() -> None:
    """处理全员玩具调到弱档指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.REMOTE_ALL_SET_SEX_TOY_WEAK, judge=_("严重骚扰")
    )


@add_instruct(constant.Instruct.REMOTE_ALL_SET_SEX_TOY_MEDIUM)
def handle_remote_all_set_sex_toy_medium() -> None:
    """处理全员玩具调到中档指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.REMOTE_ALL_SET_SEX_TOY_MEDIUM, judge=_("严重骚扰")
    )


@add_instruct(constant.Instruct.REMOTE_ALL_SET_SEX_TOY_STRONG)
def handle_remote_all_set_sex_toy_strong() -> None:
    """处理全员玩具调到强档指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.REMOTE_ALL_SET_SEX_TOY_STRONG, judge=_("严重骚扰")
    )


@add_instruct(constant.Instruct.BAGGING_AND_MOVING)
def handle_bagging_and_moving() -> None:
    """处理装袋搬走指令"""
    chara_handle_instruct_common_settle(constant.Behavior.BAGGING_AND_MOVING)


@add_instruct(constant.Instruct.RELEASE_FROM_BAG)
def handle_release_from_bag() -> None:
    """处理从袋中放出来指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.RELEASE_FROM_BAG,
        target_character_id=flags.get(0, "bagging_chara_id"),
        force_taget_wait=True,
    )


@add_instruct(constant.Instruct.PUT_INTO_PRISON)
def handle_put_into_prision() -> None:
    """处理投入监牢指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.PUT_INTO_PRISON,
        target_character_id=flags.get(0, "bagging_chara_id"),
        force_taget_wait=True,
    )


@add_instruct(constant.Instruct.SET_FREE)
def handle_set_free() -> None:
    """处理解除囚禁指令"""
    chara_handle_instruct_common_settle(constant.Behavior.SET_FREE)


# 以下为性爱#


@add_instruct(constant.Instruct.MAKING_OUT)
def handle_making_out() -> None:
    """处理身体爱抚指令"""
    chara_handle_instruct_common_settle(constant.Behavior.MAKING_OUT)


@add_instruct(constant.Instruct.KISS_H)
def handle_kiss_h() -> None:
    """处理接吻指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.KISS_H, judge=_("亲吻")
    )


@add_instruct(constant.Instruct.BREAST_CARESS)
def handle_breast_caress() -> None:
    """处理胸爱抚指令"""
    chara_handle_instruct_common_settle(constant.Behavior.BREAST_CARESS)


@add_instruct(constant.Instruct.TWIDDLE_NIPPLES)
def handle_twiddle_nipples() -> None:
    """处理玩弄乳头指令"""
    chara_handle_instruct_common_settle(constant.Behavior.TWIDDLE_NIPPLES)


@add_instruct(constant.Instruct.BREAST_SUCKING)
def handle_breast_sucking() -> None:
    """处理舔吸乳头指令"""
    chara_handle_instruct_common_settle(constant.Behavior.BREAST_SUCKING)


@add_instruct(constant.Instruct.EXTERNAL_WOMB_MASSAGE)
def handle_external_womb_massage() -> None:
    """处理体外子宫按摩指令"""
    chara_handle_instruct_common_settle(constant.Behavior.EXTERNAL_WOMB_MASSAGE)


@add_instruct(constant.Instruct.CLIT_CARESS)
def handle_cilt_caress() -> None:
    """处理阴蒂爱抚指令"""
    chara_handle_instruct_common_settle(constant.Behavior.CLIT_CARESS)


@add_instruct(constant.Instruct.OPEN_LABIA)
def handle_open_labia() -> None:
    """处理掰开阴唇观察指令"""
    chara_handle_instruct_common_settle(constant.Behavior.OPEN_LABIA)


@add_instruct(constant.Instruct.OPEN_ANUS)
def handle_open_anus() -> None:
    """处理掰开肛门观察指令"""
    chara_handle_instruct_common_settle(constant.Behavior.OPEN_ANUS)


@add_instruct(constant.Instruct.CUNNILINGUS)
def handle_cunnilingus() -> None:
    """处理舔阴指令"""
    chara_handle_instruct_common_settle(constant.Behavior.CUNNILINGUS)


@add_instruct(constant.Instruct.LICK_ANAL)
def handle_lict_anal() -> None:
    """处理舔肛指令"""
    chara_handle_instruct_common_settle(constant.Behavior.LICK_ANAL)


@add_instruct(constant.Instruct.FINGER_INSERTION)
def handle_finger_insertion() -> None:
    """处理手指插入(V)指令"""
    chara_handle_instruct_common_settle(constant.Behavior.FINGER_INSERTION)


@add_instruct(constant.Instruct.ANAL_CARESS)
def handle_anal_caress() -> None:
    """处理手指插入(A)指令"""
    chara_handle_instruct_common_settle(constant.Behavior.ANAL_CARESS)


@add_instruct(constant.Instruct.URETHRAL_FINGER_INSERTION)
def handle_urethral_finger_insertion() -> None:
    """处理尿道指姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.URETHRAL_FINGER_INSERTION, judge=_("U开发")
    )


@add_instruct(constant.Instruct.MAKE_MASTUREBATE)
def handle_make_masturebate() -> None:
    """处理命令对方自慰指令"""
    chara_handle_instruct_common_settle(constant.Behavior.MAKE_MASTUREBATE)


@add_instruct(constant.Instruct.MAKE_LICK_ANAL)
def handle_make_lick_anal() -> None:
    """处理命令对方舔自己肛门指令"""
    chara_handle_instruct_common_settle(constant.Behavior.MAKE_LICK_ANAL)


@add_instruct(constant.Instruct.ASK_PEE)
def handle_ask_pee() -> None:
    """处理命令对方小便指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.ASK_PEE, judge=_("严重骚扰")
    )


@add_instruct(constant.Instruct.SEDECU)
def handle_sedecu() -> None:
    """处理诱惑对方指令"""
    chara_handle_instruct_common_settle(constant.Behavior.SEDECU)


@add_instruct(constant.Instruct.HANDJOB)
def handle_handjob() -> None:
    """处理手交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.HANDJOB)


@add_instruct(constant.Instruct.BLOWJOB)
def handle_blowjob() -> None:
    """处理口交指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BLOWJOB, judge=_("口交")
    )


@add_instruct(constant.Instruct.PAIZURI)
def handle_paizuri() -> None:
    """处理乳交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.PAIZURI)


@add_instruct(constant.Instruct.FOOTJOB)
def handle_footjob() -> None:
    """处理足交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.FOOTJOB)


@add_instruct(constant.Instruct.HAIRJOB)
def handle_hairjob() -> None:
    """处理发交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.HAIRJOB)


@add_instruct(constant.Instruct.AXILLAJOB)
def handle_axillajob() -> None:
    """处理腋交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.AXILLAJOB)


@add_instruct(constant.Instruct.RUB_BUTTOCK)
def handle_rub_buttock() -> None:
    """处理素股指令"""
    chara_handle_instruct_common_settle(constant.Behavior.RUB_BUTTOCK)


@add_instruct(constant.Instruct.HAND_BLOWJOB)
def handle_hand_blowjob() -> None:
    """处理手交口交指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.HAND_BLOWJOB, judge=_("口交")
    )


@add_instruct(constant.Instruct.TITS_BLOWJOB)
def handle_tits_blowjob() -> None:
    """处理乳交口交指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.TITS_BLOWJOB, judge=_("口交")
    )


@add_instruct(constant.Instruct.FOCUS_BLOWJOB)
def handle_focus_blowjob() -> None:
    """处理真空口交指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FOCUS_BLOWJOB, judge=_("口交")
    )


@add_instruct(constant.Instruct.DEEP_THROAT)
def handle_deep_throat() -> None:
    """处理深喉插入指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.DEEP_THROAT, judge=_("SM")
    )


@add_instruct(constant.Instruct.CLEAN_BLOWJOB)
def handle_clean_blowjob() -> None:
    """处理清洁口交指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.CLEAN_BLOWJOB, judge=_("口交")
    )


@add_instruct(constant.Instruct.SIXTY_NINE)
def handle_sixty_nine() -> None:
    """处理六九式指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.SIXTY_NINE, judge=_("口交")
    )


@add_instruct(constant.Instruct.LEGJOB)
def handle_legjob() -> None:
    """处理腿交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.LEGJOB)


@add_instruct(constant.Instruct.TAILJOB)
def handle_tailjob() -> None:
    """处理尾交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.TAILJOB)


@add_instruct(constant.Instruct.FACE_RUB)
def handle_face_rub() -> None:
    """处理阴茎蹭脸指令"""
    chara_handle_instruct_common_settle(constant.Behavior.FACE_RUB)


@add_instruct(constant.Instruct.HORN_RUB)
def handle_horn_rub() -> None:
    """处理阴茎蹭角指令"""
    chara_handle_instruct_common_settle(constant.Behavior.HORN_RUB)


@add_instruct(constant.Instruct.EARS_RUB)
def handle_eras_rub() -> None:
    """处理阴茎蹭耳朵指令"""
    chara_handle_instruct_common_settle(constant.Behavior.EARS_RUB)


@add_instruct(constant.Instruct.HAT_JOB)
def handle_hat_job() -> None:
    """处理帽子交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.HAT_JOB)


@add_instruct(constant.Instruct.GLASSES_JOB)
def handle_glasses_job() -> None:
    """处理眼镜交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.GLASSES_JOB)


@add_instruct(constant.Instruct.EAR_ORNAMENT_JOB)
def handle_ear_ornament_job() -> None:
    """处理耳饰交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.EAR_ORNAMENT_JOB)


@add_instruct(constant.Instruct.NECK_ORNAMENT_JOB)
def handle_neck_ornament_job() -> None:
    """处理脖饰交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.NECK_ORNAMENT_JOB)


@add_instruct(constant.Instruct.MOUTH_ORNAMENT_JOB)
def handle_mouth_ornament_job() -> None:
    """处理口罩交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.MOUTH_ORNAMENT_JOB)


@add_instruct(constant.Instruct.TOP_JOB)
def handle_top_job() -> None:
    """处理上衣交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.TOP_JOB)


@add_instruct(constant.Instruct.CORSET_JOB)
def handle_corset_job() -> None:
    """处理胸衣交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.CORSET_JOB)


@add_instruct(constant.Instruct.GLOVES_JOB)
def handle_gloves_job() -> None:
    """处理手套交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.GLOVES_JOB)


@add_instruct(constant.Instruct.SKIRT_JOB)
def handle_skirt_job() -> None:
    """处理裙子交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.SKIRT_JOB)


@add_instruct(constant.Instruct.TROUSERS_JOB)
def handle_trousers_job() -> None:
    """处理裤子交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.TROUSERS_JOB)


@add_instruct(constant.Instruct.UNDERWEAR_JOB)
def handle_underwear_job() -> None:
    """处理内裤交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.UNDERWEAR_JOB)


@add_instruct(constant.Instruct.SOCKS_JOB)
def handle_socks_job() -> None:
    """处理袜子交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.SOCKS_JOB)


@add_instruct(constant.Instruct.SHOES_JOB)
def handle_shoes_job() -> None:
    """处理鞋子交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.SHOES_JOB)


@add_instruct(constant.Instruct.WEAPONS_JOB)
def handle_weapons_job() -> None:
    """处理武器交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.WEAPONS_JOB)


@add_instruct(constant.Instruct.NIPPLE_CLAMP_ON)
def handle_nipple_clamp_on() -> None:
    """处理戴上乳头夹指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.NIPPLE_CLAMP_ON, judge=_("道具")
    )


@add_instruct(constant.Instruct.NIPPLE_CLAMP_OFF)
def handle_nipple_clamp_off() -> None:
    """处理取下乳头夹指令"""
    chara_handle_instruct_common_settle(constant.Behavior.NIPPLE_CLAMP_OFF)


@add_instruct(constant.Instruct.URETHRAL_SWAB)
def handle_urethral_swab() -> None:
    """处理尿道棉棒指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.URETHRAL_SWAB, judge=_("U开发")
    )


@add_instruct(constant.Instruct.NIPPLES_LOVE_EGG)
def handle_nipples_love_egg() -> None:
    """处理乳头跳蛋指令"""
    chara_handle_instruct_common_settle(constant.Behavior.NIPPLES_LOVE_EGG)


@add_instruct(constant.Instruct.CLIT_CLAMP_ON)
def handle_clit_clamp_on() -> None:
    """处理戴上阴蒂夹指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.CLIT_CLAMP_ON, judge=_("道具")
    )


@add_instruct(constant.Instruct.CLIT_CLAMP_OFF)
def handle_clit_clamp_off() -> None:
    """处理取下阴蒂夹指令"""
    chara_handle_instruct_common_settle(constant.Behavior.CLIT_CLAMP_OFF)


@add_instruct(constant.Instruct.CLIT_LOVE_EGG)
def handle_clit_love_egg() -> None:
    """处理阴蒂跳蛋指令"""
    chara_handle_instruct_common_settle(constant.Behavior.CLIT_LOVE_EGG)


@add_instruct(constant.Instruct.ELECTRIC_MESSAGE_STICK)
def handle_electric_message_stick() -> None:
    """处理电动按摩棒指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.ELECTRIC_MESSAGE_STICK
    )


@add_instruct(constant.Instruct.VIBRATOR_INSERTION)
def handle_vibrator_insertion() -> None:
    """处理插入震动棒指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.VIBRATOR_INSERTION, judge=_("道具")
    )


@add_instruct(constant.Instruct.VIBRATOR_INSERTION_ANAL)
def handle_vibrator_insertion_anal() -> None:
    """处理肛门插入震动棒指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.VIBRATOR_INSERTION_ANAL, judge=_("道具")
    )


@add_instruct(constant.Instruct.VIBRATOR_INSERTION_OFF)
def handle_vibrator_insertion_off() -> None:
    """处理拔出震动棒指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.VIBRATOR_INSERTION_OFF
    )


@add_instruct(constant.Instruct.VIBRATOR_INSERTION_ANAL_OFF)
def handle_vibrator_insertion_anal_off() -> None:
    """处理拔出肛门震动棒指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.VIBRATOR_INSERTION_ANAL_OFF
    )


@add_instruct(constant.Instruct.CLYSTER)
def handle_clyster() -> None:
    """处理灌肠指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.CLYSTER, judge=_("SM")
    )


@add_instruct(constant.Instruct.CONTINUE_CLYSTER)
def handle_continue_clyster() -> None:
    """处理继续灌肠指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.CLYSTER, judge=_("SM")
    )


@add_instruct(constant.Instruct.CLYSTER_END)
def handle_clyster_end() -> None:
    """处理拔出肛塞指令"""
    chara_handle_instruct_common_settle(constant.Behavior.CLYSTER_END)


@add_instruct(constant.Instruct.ANAL_PLUG)
def handle_anal_plug() -> None:
    """处理肛塞指令"""
    chara_handle_instruct_common_settle(constant.Behavior.ANAL_PLUG)


@add_instruct(constant.Instruct.ANAL_BEADS)
def handle_anal_beads() -> None:
    """处理塞入肛门拉珠指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.ANAL_BEADS, judge=_("道具")
    )


@add_instruct(constant.Instruct.ANAL_BEADS_OFF)
def handle_anal_beads_off() -> None:
    """处理拔出肛门拉珠指令"""
    chara_handle_instruct_common_settle(constant.Behavior.ANAL_BEADS_OFF)


@add_instruct(constant.Instruct.MILKING_MACHINE_ON)
def handle_milking_machine_on() -> None:
    """处理装上搾乳机指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.MILKING_MACHINE_ON, judge=_("道具")
    )


@add_instruct(constant.Instruct.MILKING_MACHINE_OFF)
def handle_milking_machine_off() -> None:
    """处理取下搾乳机指令"""
    chara_handle_instruct_common_settle(constant.Behavior.MILKING_MACHINE_OFF)


@add_instruct(constant.Instruct.URINE_COLLECTOR_ON)
def handle_urine_collector_on() -> None:
    """处理装上采尿器指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.URINE_COLLECTOR_ON, judge=_("U开发")
    )


@add_instruct(constant.Instruct.URINE_COLLECTOR_OFF)
def handle_urine_collector_off() -> None:
    """处理取下采尿器指令"""
    chara_handle_instruct_common_settle(constant.Behavior.URINE_COLLECTOR_OFF)


@add_instruct(constant.Instruct.REMOTE_TOY_ON_IN_H)
def handle_remote_toy_on_in_h() -> None:
    """处理遥控启动玩具指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.REMOTE_TURN_ON_SEX_TOY
    )


@add_instruct(constant.Instruct.REMOTE_TOY_OFF_IN_H)
def handle_remote_toy_off_in_h() -> None:
    """处理遥控关闭玩具指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.REMOTE_TURN_OFF_SEX_TOY
    )


@add_instruct(constant.Instruct.REMOTE_TOY_LEVEL_UP_IN_H)
def handle_remote_toy_level_up_in_h() -> None:
    """处理调高玩具档位指令"""
    if handle_premise.handle_target_now_sex_toy_weak(0):
        chara_handle_instruct_common_settle(
            constant.Behavior.REMOTE_SET_SEX_TOY_WEAK_TO_MEDIUM
        )
    else:
        chara_handle_instruct_common_settle(
            constant.Behavior.REMOTE_SET_SEX_TOY_STRONG
        )


@add_instruct(constant.Instruct.REMOTE_TOY_LEVEL_DOWN_IN_H)
def handle_remote_toy_level_down_in_h() -> None:
    """处理降低玩具档位指令"""
    if handle_premise.handle_target_now_sex_toy_strong(0):
        chara_handle_instruct_common_settle(
            constant.Behavior.REMOTE_SET_SEX_TOY_STRONG_TO_MEDIUM
        )
    else:
        chara_handle_instruct_common_settle(
            constant.Behavior.REMOTE_SET_SEX_TOY_WEAK
        )


@add_instruct(constant.Instruct.REMOTE_TOY_ALL_OFF_IN_H)
def handle_remote_toy_all_off_in_h() -> None:
    """处理遥控关闭全员玩具指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.REMOTE_ALL_TURN_OFF_SEX_TOY, judge=_("严重骚扰")
    )


@add_instruct(constant.Instruct.REMOTE_ALL_SET_SEX_TOY_WEAK_IN_H)
def handle_remote_all_set_sex_toy_weak_in_h() -> None:
    """处理全员玩具调到弱档指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.REMOTE_ALL_SET_SEX_TOY_WEAK, judge=_("严重骚扰")
    )


@add_instruct(constant.Instruct.REMOTE_ALL_SET_SEX_TOY_MEDIUM_IN_H)
def handle_remote_all_set_sex_toy_medium_in_h() -> None:
    """处理全员玩具调到中档指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.REMOTE_ALL_SET_SEX_TOY_MEDIUM, judge=_("严重骚扰")
    )


@add_instruct(constant.Instruct.REMOTE_ALL_SET_SEX_TOY_STRONG_IN_H)
def handle_remote_all_set_sex_toy_strong_in_h() -> None:
    """处理全员玩具调到强档指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.REMOTE_ALL_SET_SEX_TOY_STRONG, judge=_("严重骚扰")
    )


@add_instruct(constant.Instruct.BONDAGE)
def handle_bondage() -> None:
    """处理绳艺指令"""
    ui_hooks.switch_panel(constant.Panel.BONDAGE)


@add_instruct(constant.Instruct.PATCH_ON)
def handle_patch_on() -> None:
    """处理戴上眼罩指令"""
    chara_handle_instruct_common_settle(constant.Behavior.PATCH_ON)


@add_instruct(constant.Instruct.PATCH_OFF)
def handle_patch_off() -> None:
    """处理摘下眼罩指令"""
    chara_handle_instruct_common_settle(constant.Behavior.PATCH_OFF)


@add_instruct(constant.Instruct.GAG_ON)
def handle_gag_on() -> None:
    """处理戴上口球指令"""
    chara_handle_instruct_common_settle(constant.Behavior.GAG_ON)


@add_instruct(constant.Instruct.GAG_OFF)
def handle_gag_off() -> None:
    """处理摘下口球指令"""
    chara_handle_instruct_common_settle(constant.Behavior.GAG_OFF)


@add_instruct(constant.Instruct.WHIP)
def handle_whip() -> None:
    """处理鞭子指令"""
    chara_handle_instruct_common_settle(constant.Behavior.WHIP, judge=_("SM"))


@add_instruct(constant.Instruct.NEEDLE)
def handle_neddle() -> None:
    """处理针指令"""
    chara_handle_instruct_common_settle(constant.Behavior.NEEDLE, judge=_("SM"))


@add_instruct(constant.Instruct.PUT_CONDOM)
def handle_put_condom() -> None:
    """处理戴上避孕套指令"""
    chara_handle_instruct_common_settle(constant.Behavior.PUT_CONDOM)


@add_instruct(constant.Instruct.TAKE_CONDOM_OUT)
def handle_take_condom_out() -> None:
    """处理摘掉避孕套指令"""
    chara_handle_instruct_common_settle(constant.Behavior.TAKE_CONDOM_OUT)


def handle_condom_instruct_common(mode: str, behavior_id: str) -> None:
    """
    避孕套指令的公共处理流程，先进行不绘制且不结算催眠代价的严重骚扰实行值判定。
    判定失败时定下严重骚扰失败行为。判定通过后经 instruct_hooks.select_condom 询问，取消时调用 pick_hooks.back()。
    确认选择后将结果带入行动参数，行动开始时由开始代码 condom 结算。
    Keyword arguments:
    mode -- str，面板操作类型，可选 hang（挂装饰）、take_back（取回装饰）、drink（饮用）或 squeeze（挤出）
    behavior_id -- str，判定通过后定下的行为编号
    Return arguments:
    None -- 经行动选择或取消选择结束，无正常返回值
    """
    judge = _("严重骚扰")
    if not instuct_judege.calculation_instuct_judege(
        0,
        activity.target(0),
        judge,
        not_draw_flag=True,
        settle_hypnosis=False,
    )[0]:
        chara_handle_instruct_common_settle(
            constant.Behavior.HIGH_OBSCENITY_ANUS, judge=judge
        )
    selection = instruct_hooks.select_condom(mode)
    if selection is None:
        pick_hooks.back()
    chara_handle_instruct_common_settle(
        behavior_id, judge=judge, start="condom", args=selection
    )


@start_part("condom")
def _start_condom(who: int, chosen: intent.Intent) -> None:
    """
    避孕套指令开始时：按选择面板的选择（args 的 op、part、condom）结算挂装饰、取回装饰、饮用或挤出
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    from Script.System.Item_System import condom_handle

    args = chosen["args"]
    target = int(chosen["target"])
    op = args["op"]
    condom = args["condom"]
    assert isinstance(condom, tuple | list)
    if op == "take_back":
        condom_handle.settle_take_back(
            target, [((c[0], c[1]), c[2]) for c in map(_ints, condom)]
        )
        return
    condoms = _ints(condom)
    if op == "drink":
        condom_handle.settle_drink(target, condoms)
        return
    part = _ints(args["part"])
    settle = (
        condom_handle.settle_hang
        if op == "hang"
        else condom_handle.settle_squeeze
    )
    settle(target, part[0], part[1], condoms)


@add_instruct(constant.Instruct.HANG_CONDOM_DECORATION)
def handle_hang_condom_decoration() -> None:
    """处理挂上避孕套装饰指令，数据结算在选择面板确认时直接完成"""
    handle_condom_instruct_common(
        "hang", constant.Behavior.HANG_CONDOM_DECORATION
    )


@add_instruct(constant.Instruct.TAKE_BACK_CONDOM_DECORATION)
def handle_take_back_condom_decoration() -> None:
    """处理取回避孕套装饰指令，数据结算在选择面板确认时直接完成"""
    handle_condom_instruct_common(
        "take_back", constant.Behavior.TAKE_BACK_CONDOM_DECORATION
    )


@add_instruct(constant.Instruct.DRINK_CONDOM_SEMEN)
def handle_drink_condom_semen() -> None:
    """处理饮用避孕套精液指令，数据结算在选择面板确认时直接完成"""
    handle_condom_instruct_common("drink", constant.Behavior.DRINK_CONDOM_SEMEN)


@add_instruct(constant.Instruct.SQUEEZE_CONDOM_SEMEN)
def handle_squeeze_condom_semen() -> None:
    """处理挤出避孕套精液指令，数据结算在选择面板确认时直接完成"""
    handle_condom_instruct_common(
        "squeeze", constant.Behavior.SQUEEZE_CONDOM_SEMEN
    )


@add_instruct(constant.Instruct.HANG_CONDOM_DECORATION_DAILY)
def handle_hang_condom_decoration_daily() -> None:
    """处理非H下的挂上避孕套装饰指令，与H版共用行为与面板"""
    handle_condom_instruct_common(
        "hang", constant.Behavior.HANG_CONDOM_DECORATION
    )


@add_instruct(constant.Instruct.TAKE_BACK_CONDOM_DECORATION_DAILY)
def handle_take_back_condom_decoration_daily() -> None:
    """处理非H下的取回避孕套装饰指令，与H版共用行为与面板"""
    handle_condom_instruct_common(
        "take_back", constant.Behavior.TAKE_BACK_CONDOM_DECORATION
    )


@add_instruct(constant.Instruct.DRINK_CONDOM_SEMEN_DAILY)
def handle_drink_condom_semen_daily() -> None:
    """处理非H下的饮用避孕套精液指令，与H版共用行为与面板"""
    handle_condom_instruct_common("drink", constant.Behavior.DRINK_CONDOM_SEMEN)


@add_instruct(constant.Instruct.SQUEEZE_CONDOM_SEMEN_DAILY)
def handle_squeeze_condom_semen_daily() -> None:
    """处理非H下的挤出避孕套精液指令，与H版共用行为与面板"""
    handle_condom_instruct_common(
        "squeeze", constant.Behavior.SQUEEZE_CONDOM_SEMEN
    )


@add_instruct(constant.Instruct.SAFE_CANDLES)
def handle_safe_candles() -> None:
    """处理滴蜡指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.SAFE_CANDLES, judge=_("SM")
    )


@add_instruct(constant.Instruct.BODY_LUBRICANT)
def handle_body_lubricant() -> None:
    """处理润滑液指令"""
    chara_handle_instruct_common_settle(constant.Behavior.BODY_LUBRICANT)


@add_instruct(constant.Instruct.PHILTER)
def handle_philter() -> None:
    """处理媚药指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.PHILTER, judge=_("药物")
    )


@add_instruct(constant.Instruct.ENEMAS)
def handle_enemas() -> None:
    """处理灌肠液指令"""
    pick_hooks.choose(constant.Behavior.SHARE_BLANKLY, 5)


@add_instruct(constant.Instruct.DIURETICS_ONCE)
def handle_diuretics_once() -> None:
    """处理一次性利尿剂指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.DIURETICS_ONCE, judge=_("药物")
    )


@add_instruct(constant.Instruct.DIURETICS_PERSISTENT)
def handle_diuretics_persistent() -> None:
    """处理持续性利尿剂指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.DIURETICS_PERSISTENT, judge=_("药物")
    )


@add_instruct(constant.Instruct.SLEEPING_PILLS)
def handle_sleeping_pills() -> None:
    """处理安眠药指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.SLEEPING_PILLS, judge=_("药物")
    )


@add_instruct(constant.Instruct.CLOMID)
def handle_clomid() -> None:
    """处理排卵促进药指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.CLOMID, judge=_("药物")
    )


@add_instruct(constant.Instruct.BIRTH_CONTROL_PILLS_BEFORE)
def handle_birth_control_pills_before() -> None:
    """处理事前避孕药指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BIRTH_CONTROL_PILLS_BEFORE
    )


@add_instruct(constant.Instruct.BIRTH_CONTROL_PILLS_AFTER)
def handle_birth_control_pills_after() -> None:
    """处理事后避孕药指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BIRTH_CONTROL_PILLS_AFTER
    )


@add_instruct(constant.Instruct.VAGINAL_SEX)
def handle_vaginal_sex() -> None:
    """处理阴道性交指令"""
    instruct_hooks.choose_sex_position(1, False)


@add_instruct(constant.Instruct.CHANGE_VAGINAL_SEX_POSITION)
def handle_change_vaginal_sex_position() -> None:
    """处理换阴道性交体位指令"""
    instruct_hooks.choose_sex_position(1, True)


@add_instruct(constant.Instruct.NORMAL_SEX)
def handle_normal_sex() -> None:
    """处理正常位指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.NORMAL_SEX, judge=_("性交")
    )


@add_instruct(constant.Instruct.BACK_SEX)
def handle_back_sex() -> None:
    """处理背后位指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_SEX, judge=_("性交")
    )


@add_instruct(constant.Instruct.RIDING_SEX)
def handle_riding_sex() -> None:
    """处理对面骑乘位指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.RIDING_SEX, judge=_("性交")
    )


@add_instruct(constant.Instruct.BACK_RIDING_SEX)
def handle_back_riding_sex() -> None:
    """处理背面骑乘位指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_RIDING_SEX, judge=_("性交")
    )


@add_instruct(constant.Instruct.FACE_SEAT_SEX)
def handle_face_seat_sex() -> None:
    """处理对面座位指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FACE_SEAT_SEX, judge=_("性交")
    )


@add_instruct(constant.Instruct.BACK_SEAT_SEX)
def handle_back_seat_sex() -> None:
    """处理背面座位指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_SEAT_SEX, judge=_("性交")
    )


@add_instruct(constant.Instruct.FACE_STAND_SEX)
def handle_face_stand_sex() -> None:
    """处理对面立位指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FACE_STAND_SEX, judge=_("性交")
    )


@add_instruct(constant.Instruct.BACK_STAND_SEX)
def handle_back_stand_sex() -> None:
    """处理背面立位指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_STAND_SEX, judge=_("性交")
    )


@add_instruct(constant.Instruct.FACE_HUG_SEX)
def handle_face_hug_sex() -> None:
    """处理对面抱位指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FACE_HUG_SEX, judge=_("性交")
    )


@add_instruct(constant.Instruct.BACK_HUG_SEX)
def handle_back_hug_sex() -> None:
    """处理背面抱位指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_HUG_SEX, judge=_("性交")
    )


@add_instruct(constant.Instruct.FACE_LAY_SEX)
def handle_face_lay_sex() -> None:
    """处理对面卧位指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FACE_LAY_SEX, judge=_("性交")
    )


@add_instruct(constant.Instruct.BACK_LAY_SEX)
def handle_back_lay_sex() -> None:
    """处理背面卧位指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_LAY_SEX, judge=_("性交")
    )


@add_instruct(constant.Instruct.STIMULATE_G_POINT)
def handle_stimulate_g_point() -> None:
    """处理刺激G点指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.STIMULATE_G_POINT, judge=_("性交")
    )


@add_instruct(constant.Instruct.WOMB_OS_CARESS)
def handle_womb_os_caress() -> None:
    """处理玩弄子宫口指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.WOMB_OS_CARESS, judge=_("性交")
    )


# @add_instruct(#     constant.Instruct.WOMB_INSERTION)
# def handle_womb_insertion():
#     """处理插入子宫口指令"""
#     chara_handle_instruct_common_settle(constant.Behavior.WOMB_INSERTION, judge = _("W性交"))


@add_instruct(constant.Instruct.CHANGE_CERVIX_SEX_POSITION)
def handle_change_cervix_sex_position() -> None:
    """处理换子宫姦口体位指令"""
    instruct_hooks.choose_sex_position(2, True)


@add_instruct(constant.Instruct.NORMAL_CERVIX_SEX)
def handle_normal_cervix_sex() -> None:
    """处理正常位子宫口姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.NORMAL_CERVIX_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.BACK_CERVIX_SEX)
def handle_back_cervix_sex() -> None:
    """处理后背位子宫口姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_CERVIX_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.RIDING_CERVIX_SEX)
def handle_riding_cervix_sex() -> None:
    """处理对面骑乘位子宫口姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.RIDING_CERVIX_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.BACK_RIDING_CERVIX_SEX)
def handle_back_riding_cervix_sex() -> None:
    """处理背面骑乘位子宫口姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_RIDING_CERVIX_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.FACE_SEAT_CERVIX_SEX)
def handle_face_seat_cervix_sex() -> None:
    """处理对面座位子宫口姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FACE_SEAT_CERVIX_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.BACK_SEAT_CERVIX_SEX)
def handle_back_seat_cervix_sex() -> None:
    """处理背面座位子宫口姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_SEAT_CERVIX_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.FACE_STAND_CERVIX_SEX)
def handle_face_stand_cervix_sex() -> None:
    """处理对面立位子宫口姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FACE_STAND_CERVIX_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.BACK_STAND_CERVIX_SEX)
def handle_back_stand_cervix_sex() -> None:
    """处理背面立位子宫口姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_STAND_CERVIX_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.FACE_HUG_CERVIX_SEX)
def handle_face_hug_cervix_sex() -> None:
    """处理对面抱位子宫口姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FACE_HUG_CERVIX_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.BACK_HUG_CERVIX_SEX)
def handle_back_hug_cervix_sex() -> None:
    """处理背面抱位子宫口姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_HUG_CERVIX_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.FACE_LAY_CERVIX_SEX)
def handle_face_lay_cervix_sex() -> None:
    """处理对面卧位子宫口姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FACE_LAY_CERVIX_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.BACK_LAY_CERVIX_SEX)
def handle_back_lay_cervix_sex() -> None:
    """处理背面卧位子宫口姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_LAY_CERVIX_SEX, judge=_("W性交")
    )


# @add_instruct(#     constant.Instruct.WOMB_SEX)
# def handle_womb_sex():
#     """处理子宫姦指令"""
#     chara_handle_instruct_common_settle(constant.Behavior.WOMB_SEX, judge = _("W性交"))


@add_instruct(constant.Instruct.CHANGE_WOMB_SEX_POSITION)
def handle_change_womb_sex_position() -> None:
    """处理换子宫姦体位指令"""
    instruct_hooks.choose_sex_position(3, True)


@add_instruct(constant.Instruct.NORMAL_WOMB_SEX)
def handle_normal_womb_sex() -> None:
    """处理正常位子宫姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.NORMAL_WOMB_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.BACK_WOMB_SEX)
def handle_back_womb_sex() -> None:
    """处理后背位子宫姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_WOMB_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.RIDING_WOMB_SEX)
def handle_riding_womb_sex() -> None:
    """处理对面骑乘位子宫姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.RIDING_WOMB_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.BACK_RIDING_WOMB_SEX)
def handle_back_riding_womb_sex() -> None:
    """处理背面骑乘位子宫姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_RIDING_WOMB_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.FACE_SEAT_WOMB_SEX)
def handle_face_seat_womb_sex() -> None:
    """处理对面座位子宫姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FACE_SEAT_WOMB_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.BACK_SEAT_WOMB_SEX)
def handle_back_seat_womb_sex() -> None:
    """处理背面座位子宫姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_SEAT_WOMB_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.FACE_STAND_WOMB_SEX)
def handle_face_stand_womb_sex() -> None:
    """处理对面立位子宫姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FACE_STAND_WOMB_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.BACK_STAND_WOMB_SEX)
def handle_back_stand_womb_sex() -> None:
    """处理背面立位子宫姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_STAND_WOMB_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.FACE_HUG_WOMB_SEX)
def handle_face_hug_womb_sex() -> None:
    """处理对面抱位子宫姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FACE_HUG_WOMB_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.BACK_HUG_WOMB_SEX)
def handle_back_hug_womb_sex() -> None:
    """处理背面抱位子宫姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_HUG_WOMB_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.FACE_LAY_WOMB_SEX)
def handle_face_lay_womb_sex() -> None:
    """处理对面卧位子宫姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FACE_LAY_WOMB_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.BACK_LAY_WOMB_SEX)
def handle_back_lay_womb_sex() -> None:
    """处理背面卧位子宫姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_LAY_WOMB_SEX, judge=_("W性交")
    )


@add_instruct(constant.Instruct.ANAL_SEX)
def handle_anal_sex() -> None:
    """处理肛门性交指令"""
    instruct_hooks.choose_sex_position(4, False)


@add_instruct(constant.Instruct.CHANGE_ANAL_SEX_POSITION)
def handle_change_anal_sex_position() -> None:
    """处理换肛交体位指令"""
    instruct_hooks.choose_sex_position(4, True)


@add_instruct(constant.Instruct.NORMAL_ANAL_SEX)
def handle_normal_anal_sex() -> None:
    """处理正常位肛交指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.NORMAL_ANAL_SEX, judge=_("A性交")
    )


@add_instruct(constant.Instruct.BACK_ANAL_SEX)
def handle_back_anal_sex() -> None:
    """处理后背位肛交指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_ANAL_SEX, judge=_("A性交")
    )


@add_instruct(constant.Instruct.RIDING_ANAL_SEX)
def handle_riding_anal_sex() -> None:
    """处理对面骑乘位肛交指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.RIDING_ANAL_SEX, judge=_("A性交")
    )


@add_instruct(constant.Instruct.BACK_RIDING_ANAL_SEX)
def handle_back_riding_anal_sex() -> None:
    """处理背面骑乘位肛交指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_RIDING_ANAL_SEX, judge=_("A性交")
    )


@add_instruct(constant.Instruct.FACE_SEAT_ANAL_SEX)
def handle_face_seat_anal_sex() -> None:
    """处理对面座位肛交指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FACE_SEAT_ANAL_SEX, judge=_("A性交")
    )


@add_instruct(constant.Instruct.BACK_SEAT_ANAL_SEX)
def handle_back_seat_anal_sex() -> None:
    """处理背面座位肛交指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_SEAT_ANAL_SEX, judge=_("A性交")
    )


@add_instruct(constant.Instruct.FACE_STAND_ANAL_SEX)
def handle_face_stand_anal_sex() -> None:
    """处理对面立位肛交指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FACE_STAND_ANAL_SEX, judge=_("A性交")
    )


@add_instruct(constant.Instruct.BACK_STAND_ANAL_SEX)
def handle_back_stand_anal_sex() -> None:
    """处理背面立位肛交指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_STAND_ANAL_SEX, judge=_("A性交")
    )


@add_instruct(constant.Instruct.FACE_HUG_ANAL_SEX)
def handle_face_hug_anal_sex() -> None:
    """处理对面抱位肛交指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FACE_HUG_ANAL_SEX, judge=_("A性交")
    )


@add_instruct(constant.Instruct.BACK_HUG_ANAL_SEX)
def handle_back_hug_anal_sex() -> None:
    """处理背面抱位肛交指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_HUG_ANAL_SEX, judge=_("A性交")
    )


@add_instruct(constant.Instruct.FACE_LAY_ANAL_SEX)
def handle_face_lay_anal_sex() -> None:
    """处理对面卧位肛交指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FACE_LAY_ANAL_SEX, judge=_("A性交")
    )


@add_instruct(constant.Instruct.BACK_LAY_ANAL_SEX)
def handle_back_lay_anal_sex() -> None:
    """处理背面卧位肛交指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_LAY_ANAL_SEX, judge=_("A性交")
    )


@add_instruct(constant.Instruct.STIMULATE_SIGMOID_COLON)
def handle_stimulate_sigmoid_colon() -> None:
    """处理玩弄s状结肠指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.STIMULATE_SIGMOID_COLON, judge=_("A性交")
    )


@add_instruct(constant.Instruct.STIMULATE_VAGINA)
def handle_stimulate_vagina() -> None:
    """处理隔着刺激阴道指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.STIMULATE_VAGINA, judge=_("A性交")
    )


@add_instruct(constant.Instruct.DOUBLE_PENETRATION)
def handle_double_penetration() -> None:
    """处理二穴插入指令"""
    pick_hooks.choose(constant.Behavior.SHARE_BLANKLY, 5)


@add_instruct(constant.Instruct.URETHRAL_SEX)
def handle_urethral_sex() -> None:
    """处理尿道姦指令"""
    instruct_hooks.choose_sex_position(5, False)


@add_instruct(constant.Instruct.CHANGE_URETHRAL_SEX_POSITION)
def handle_change_urethral_sex_position() -> None:
    """处理换尿道姦体位指令"""
    instruct_hooks.choose_sex_position(5, True)


@add_instruct(constant.Instruct.NORMAL_URETHRAL_SEX)
def handle_normal_urethral_sex() -> None:
    """处理正常位尿道姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.NORMAL_URETHRAL_SEX, judge=_("U性交")
    )


@add_instruct(constant.Instruct.BACK_URETHRAL_SEX)
def handle_back_urethral_sex() -> None:
    """处理后背位尿道姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_URETHRAL_SEX, judge=_("U性交")
    )


@add_instruct(constant.Instruct.RIDING_URETHRAL_SEX)
def handle_riding_urethral_sex() -> None:
    """处理对面骑乘位尿道姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.RIDING_URETHRAL_SEX, judge=_("U性交")
    )


@add_instruct(constant.Instruct.BACK_RIDING_URETHRAL_SEX)
def handle_back_riding_urethral_sex() -> None:
    """处理背面骑乘位尿道姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_RIDING_URETHRAL_SEX, judge=_("U性交")
    )


@add_instruct(constant.Instruct.FACE_SEAT_URETHRAL_SEX)
def handle_face_seat_urethral_sex() -> None:
    """处理对面座位尿道姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FACE_SEAT_URETHRAL_SEX, judge=_("U性交")
    )


@add_instruct(constant.Instruct.BACK_SEAT_URETHRAL_SEX)
def handle_back_seat_urethral_sex() -> None:
    """处理背面座位尿道姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_SEAT_URETHRAL_SEX, judge=_("U性交")
    )


@add_instruct(constant.Instruct.FACE_STAND_URETHRAL_SEX)
def handle_face_stand_urethral_sex() -> None:
    """处理对面立位尿道姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FACE_STAND_URETHRAL_SEX, judge=_("U性交")
    )


@add_instruct(constant.Instruct.BACK_STAND_URETHRAL_SEX)
def handle_back_stand_urethral_sex() -> None:
    """处理背面立位尿道姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_STAND_URETHRAL_SEX, judge=_("U性交")
    )


@add_instruct(constant.Instruct.FACE_HUG_URETHRAL_SEX)
def handle_face_hug_urethral_sex() -> None:
    """处理对面抱位尿道姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FACE_HUG_URETHRAL_SEX, judge=_("U性交")
    )


@add_instruct(constant.Instruct.BACK_HUG_URETHRAL_SEX)
def handle_back_hug_urethral_sex() -> None:
    """处理背面抱位尿道姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_HUG_URETHRAL_SEX, judge=_("U性交")
    )


@add_instruct(constant.Instruct.FACE_LAY_URETHRAL_SEX)
def handle_face_lay_urethral_sex() -> None:
    """处理对面卧位尿道姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.FACE_LAY_URETHRAL_SEX, judge=_("U性交")
    )


@add_instruct(constant.Instruct.BACK_LAY_URETHRAL_SEX)
def handle_back_lay_urethral_sex() -> None:
    """处理背面卧位尿道姦指令"""
    chara_handle_instruct_common_settle(
        constant.Behavior.BACK_LAY_URETHRAL_SEX, judge=_("U性交")
    )


@add_instruct(constant.Instruct.BEAT_BREAST)
def handle_beat_breast() -> None:
    """处理打胸部指令"""
    pick_hooks.choose(constant.Behavior.SHARE_BLANKLY, 5)


@add_instruct(constant.Instruct.SPANKING)
def handle_spanking() -> None:
    """处理打屁股指令"""
    chara_handle_instruct_common_settle(constant.Behavior.SPANKING)


@add_instruct(constant.Instruct.SHAME_PLAY)
def handle_shame_play() -> None:
    """处理羞耻play指令"""
    pick_hooks.choose(constant.Behavior.SHARE_BLANKLY, 5)


@add_instruct(constant.Instruct.TAKE_SHOWER_H)
def handle_take_shower_h() -> None:
    """处理淋浴指令"""
    pick_hooks.choose(constant.Behavior.SHARE_BLANKLY, 5)


@add_instruct(constant.Instruct.BUBBLE_BATH)
def handle_bubble_bath() -> None:
    """处理泡泡浴指令"""
    pick_hooks.choose(constant.Behavior.SHARE_BLANKLY, 5)


@add_instruct(constant.Instruct.GIVE_BLOWJOB)
def handle_give_blowjob() -> None:
    """处理给对方口交指令"""
    pick_hooks.choose(constant.Behavior.SHARE_BLANKLY, 5)


@add_instruct(constant.Instruct.CHANGE_TOP_AND_BOTTOM)
def handle_change_top_and_bottom() -> None:
    """处理交给对方指令"""
    h_state.set(activity.target(0), npc_active_h=True)
    handle_npc_ai_in_h.npc_active_h(pick_hooks.choose)


@add_instruct(constant.Instruct.KEEP_ENJOY)
def handle_keep_enjoy() -> None:
    """处理继续享受指令"""
    handle_npc_ai_in_h.npc_active_h(pick_hooks.choose)


@add_instruct(constant.Instruct.TRY_PL_ACTIVE_H)
def handle_try_pl_active_h() -> None:
    """处理尝试掌握主动权指令"""
    h_state.set(activity.target(0), npc_active_h=False)


@add_instruct(constant.Instruct.UNDRESS)
def handle_undress() -> None:
    """处理脱衣服指令"""
    ui_hooks.switch_panel(constant.Panel.UNDRESS)


@add_instruct(constant.Instruct.ORGASM_EDGE_ON)
def handle_orgasm_edge_on() -> None:
    """处理绝顶寸止指令"""
    chara_handle_instruct_common_settle(constant.Behavior.ORGASM_EDGE_ON)


@add_instruct(constant.Instruct.ORGASM_EDGE_OFF)
def handle_orgasm_edge_off() -> None:
    """处理绝顶解放指令"""
    chara_handle_instruct_common_settle(constant.Behavior.ORGASM_EDGE_OFF)


@add_instruct(constant.Instruct.RUN_GROUP_SEX_TEMPLE)
def handle_run_group_sex_temple() -> None:
    """处理进行一次当前群交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.WAIT, duration=10)


@add_instruct(constant.Instruct.RUN_ALL_GROUP_SEX_TEMPLE)
def handle_run_all_group_sex_temple() -> None:
    """处理进行一次轮流群交指令"""
    chara_handle_instruct_common_settle(constant.Behavior.WAIT, duration=10)


@add_instruct(constant.Instruct.EDIT_GROUP_SEX_TEMPLE)
def handle_edit_group_sex_temple() -> None:
    """处理编辑群交行动指令"""
    ui_hooks.switch_panel(constant.Panel.EDIT_GROUP_SEX_TEMPLE)


@add_instruct(constant.Instruct.SWITCH_TO_NON_H_INTERFACE)
def handle_switch_to_non_h_interface() -> None:
    """处理切换到非H指令"""
    instruct_hooks.show_non_h(True)


@add_instruct(constant.Instruct.PULL_OUT_PENIS)
def handle_pull_out_penis() -> None:
    """处理拔出阴茎指令"""
    chara_handle_instruct_common_settle(constant.Behavior.PULL_OUT_PENIS)


@add_instruct(constant.Instruct.STOP_ENDURE)
def handle_stop_endure() -> None:
    """处理停止忍耐指令"""
    chara_handle_instruct_common_settle(constant.Behavior.STOP_ENDURE)
