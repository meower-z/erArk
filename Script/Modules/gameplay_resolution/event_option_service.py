"""
子事件选项服务（event_option_service）
======================================
本模块提供普通子事件与多层嵌套子事件的选项筛选、标签文本转换、ChoicePrompt 构建及选择结果写回逻辑。
本模块不导入界面、Tk 或输入输出模块。
"""

from Script.Config import game_config
from Script.Design import handle_premise, talk
from Script.Modules.domains import activity, identity
from Script.Modules.gameplay_resolution import settle_hooks
from Script.Protocol.modal_prompts import (
    ChoiceOption,
    ChoicePrompt,
    ChoiceResult,
)


def option_label(text: str) -> str:
    """
    按 "|" 拆分事件文本，返回首段作为选项标签。
    Keyword arguments:
    text -- str，事件原始文本
    Return arguments:
    str -- 选项标签文本
    """
    return text.split("|")[0]


def _prompt(
    prompt_id: str, event_ids: list[str], character_id: int
) -> ChoicePrompt | None:
    """
    按首次出现顺序为候选事件标识去重并构建 ChoicePrompt，空列表返回 None。
    每个选项的标签取自事件文本的首段，并经 talk.code_text_to_draw_text 按 character_id 转为显示文本。
    Keyword arguments:
    prompt_id -- str，写入 ChoicePrompt 的提示标识
    event_ids -- list[str]，候选子事件标识列表
    character_id -- int，用于转换标签文本代码的角色编号
    Return arguments:
    ChoicePrompt | None -- 标识为 prompt_id 的选项提示，无候选时为 None
    """
    if not event_ids:
        return None
    return ChoicePrompt(
        prompt_id,
        tuple(
            ChoiceOption(
                event_id,
                talk.code_text_to_draw_text(
                    option_label(game_config.config_event[event_id].text),
                    character_id,
                ),
            )
            for event_id in dict.fromkeys(event_ids)
        ),
    )


def check_son_event_list_from_event_list(
    event_list: list,
    character_id: int,
    event_parent_chid_id: int,
    event_parent_value: int,
) -> list[str]:
    """
    按输入顺序筛选包含对应 CVP_A1_Son 嵌套前提的子事件。
    若事件含其余前提，仅在权重非零时保留并复用前提缓存，无其余前提时直接保留。
    Keyword arguments:
    event_list -- list，候选事件标识列表
    character_id -- int，角色编号
    event_parent_chid_id -- int，嵌套父子事件的序号编号（非事件标识）
    event_parent_value -- int，嵌套父子事件的值
    Return arguments:
    list[str] -- 通过筛选的子事件标识列表
    """
    son_event_list = []
    calculated_premise_dict: dict[str, float] = {}
    son_premise = f"CVP_A1_Son|{event_parent_chid_id}_E_{event_parent_value}"
    for event_id in event_list:
        event_config = game_config.config_event[event_id]
        if son_premise in event_config.premise:
            premise_dict = event_config.premise.copy()
            premise_dict.pop(son_premise)
            if len(premise_dict):
                now_weight, calculated_premise_dict = (
                    handle_premise.get_weight_from_premise_dict(
                        premise_dict,
                        character_id,
                        calculated_premise_dict,
                        unconscious_pass_flag=True,
                    )
                )
                if now_weight:
                    son_event_list.append(event_id)
            else:
                son_event_list.append(event_id)
    return son_event_list


def build_son_event_prompt(character_id: int) -> ChoicePrompt | None:
    """
    按当前行为的事件表顺序筛选含 option_son 且包含父事件全部前提键的子事件，交由 _prompt 构建选项提示。
    所构建提示的标识为 settle_hooks.SON_EVENT_PROMPT_ID，行为无事件表或无匹配子事件时返回 None。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    ChoicePrompt | None -- 普通子事件选项提示，无匹配项时为 None
    """
    cid = identity.of(character_id).cid
    behavior_id = activity.behavior(cid).behavior_id
    father_event_id = activity.event(cid).event_id
    father_premise = game_config.config_event[father_event_id].premise
    son_event_list = []
    for event_id in game_config.config_event_status_data.get(behavior_id, []):
        premise = game_config.config_event[event_id].premise
        if "option_son" in premise and all(
            key in premise for key in father_premise
        ):
            son_event_list.append(event_id)
    return _prompt(
        settle_hooks.SON_EVENT_PROMPT_ID, son_event_list, character_id
    )


def build_multi_layer_event_prompt(
    character_id: int, event_parent_chid_id: int, event_parent_value: int
) -> ChoicePrompt | None:
    """
    拼接角色与目标角色对应 adv 的候选事件并筛选多层嵌套子事件，交由 _prompt 构建选项提示。
    所构建提示的标识为 settle_hooks.NESTED_EVENT_PROMPT_ID，无匹配子事件时返回 None。
    Keyword arguments:
    character_id -- int，角色编号
    event_parent_chid_id -- int，嵌套父子事件的序号编号（非事件标识）
    event_parent_value -- int，嵌套父子事件的值
    Return arguments:
    ChoicePrompt | None -- 多层嵌套子事件选项提示，无匹配项时为 None
    """
    character_data = identity.of(character_id)
    target_data = identity.of(activity.target(character_data.cid))
    behavior_id = activity.behavior(character_data.cid).behavior_id
    events_by_adv = game_config.config_event_status_data_by_chara_adv.get(
        behavior_id, {}
    )
    event_list = events_by_adv.get(character_data.adv, []) + events_by_adv.get(
        target_data.adv, []
    )
    return _prompt(
        settle_hooks.NESTED_EVENT_PROMPT_ID,
        check_son_event_list_from_event_list(
            event_list, character_id, event_parent_chid_id, event_parent_value
        ),
        character_id,
    )


def apply_event_choice(character_id: int, result: ChoiceResult) -> None:
    """
    将子事件选择结果写入角色当前事件的 son_event_id。
    result.prompt_id 不是 SON_EVENT_PROMPT_ID 或 NESTED_EVENT_PROMPT_ID 时抛出 ValueError。
    result.selected_option_id 不在 game_config.config_event 中时也抛出 ValueError。
    Keyword arguments:
    character_id -- int，角色编号
    result -- ChoiceResult，待写入的选择结果
    Return arguments:
    None -- 无返回值
    """
    if result.prompt_id not in (
        settle_hooks.SON_EVENT_PROMPT_ID,
        settle_hooks.NESTED_EVENT_PROMPT_ID,
    ):
        raise ValueError(f"not a son event choice: {result.prompt_id!r}")
    if result.selected_option_id not in game_config.config_event:
        raise ValueError(f"unknown event id: {result.selected_option_id!r}")
    activity.update_event(
        identity.of(character_id).cid,
        son_event_id=result.selected_option_id,
    )
