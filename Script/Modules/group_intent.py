"""群交候选准备、NPC 选择和意图执行。"""

import random
from dataclasses import dataclass

from Script.Core import cache_control, constant, game_type, get_text
from Script.Design import handle_premise
from Script.Modules.action import Action

_ = get_text._


@dataclass(frozen=True)
class GroupOptions:
    """可补位的部位、各部位可用动作，以及仅自慰设置。"""

    empty_parts: tuple[str, ...]
    statuses: dict[str, tuple[int, ...]]
    masturbate_only: bool = False


def prepare_group_options(actor: int) -> GroupOptions | None:
    """输入 NPC 编号，准备候选部位和动作；返回候选，非适用角色返回 None。"""
    character = cache_control.cache.character_data[actor]
    # 睡眠和异常状态沿用行为前置检查的处理顺序。
    if actor == 0 or not character.sp_flag.is_h or handle_premise.handle_group_sex_mode_off(actor):
        return None
    if character.behavior.behavior_id == constant.Behavior.SLEEP or not handle_premise.handle_normal_6(actor, read_only=True):
        return None
    if not (handle_premise.handle_npc_ai_type_1_in_group_sex(actor) or handle_premise.handle_npc_ai_type_2_in_group_sex(actor)):
        return None
    from Script.System.Sex_System import group_sex_panel

    if actor in group_sex_panel.count_group_sex_character_list() or handle_premise.handle_self_now_bondage(actor):
        return None
    if handle_premise.handle_npc_ai_type_1_in_group_sex(actor):
        return GroupOptions((), {}, True)

    empty_parts, _occupied_parts = group_sex_panel.get_now_template_part_list()
    statuses = {}
    # 显式查询候选 NPC，不改变玩家目标或角色缓存。
    for body_part in empty_parts:
        if body_part != _("加入侍奉"):
            statuses[body_part] = tuple(group_sex_panel.get_status_id_list_from_group_sex_body_part(body_part, target_id=actor))
    return GroupOptions(tuple(empty_parts), statuses)


def choose_group_action(actor: int, options: GroupOptions) -> Action:
    """输入 NPC 编号和已准备候选，记录自身自慰需求并返回选定的 Action。"""
    if options.masturbate_only or not options.empty_parts:
        from Script.Design import handle_npc_ai

        character = cache_control.cache.character_data[actor]
        character.sp_flag.masturebate = 3
        # 自慰需求属于自身决策记录；同步该需求所属的缓存位。
        if not isinstance(character.sp_flag.unnormal_flag, game_type.UnnormalFlagMask):
            character.sp_flag.unnormal_flag = game_type.UnnormalFlagMask(character.sp_flag.unnormal_flag)
        character.sp_flag.unnormal_flag.update(1, True)
        return handle_npc_ai.choose_character_target(actor, cache_control.cache.game_time)
    # 保留先选部位、再选动作的概率；无可用动作时维持当前行为。
    body_part = random.choice(options.empty_parts)
    if body_part == _("加入侍奉"):
        return Action("group_join", 0, 0)
    statuses = options.statuses[body_part]
    if not statuses:
        character = cache_control.cache.character_data[actor]
        if character.behavior.behavior_id == constant.Behavior.SHARE_BLANKLY:
            return Action(constant.Behavior.WAIT, 5, actor, state=constant.CharacterStatus.STATUS_WAIT)
        return Action.from_character(character)
    return Action("group_fill", 0, 0, params={"body_part": body_part, "status_id": random.choice(statuses)})


def execute_group_action(actor: int, action: Action) -> None:
    """输入 NPC 编号及行动，更新模板并为闲置角色准备等待；返回 None。"""
    character = cache_control.cache.character_data[actor]
    template = cache_control.cache.character_data[0].h_state.group_sex_body_template_dict["A"]
    if action.behavior_id == "group_join":
        template[1][0].append(actor)
    elif action.behavior_id == "group_fill":
        body_part, status_id = action.params["body_part"], action.params["status_id"]
        if body_part == _("侍奉"):
            template[1] = [[actor], status_id]
        else:
            template[0][body_part] = [actor, status_id]
    # 原有非闲置行为继续执行；刚选完补位的闲置 NPC 等待五分钟。
    if character.behavior.behavior_id == constant.Behavior.SHARE_BLANKLY:
        character.behavior.behavior_id = constant.Behavior.WAIT
        character.behavior.duration = 5
        character.target_character_id = actor
        character.state = constant.CharacterStatus.STATUS_WAIT
