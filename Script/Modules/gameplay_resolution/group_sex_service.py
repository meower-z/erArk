"""
群交模板服务（group_sex_service）
=================================
提供群交模板结算、指令与参与角色统计、部位可用行为筛选、当前部位状态查询及角色清理逻辑。
本模块不直接导入界面模块。
供群交面板与指令、行为结算、群交 AI、性技实操课旁观统计及 H 状态重置入口调用。
"""

from types import FunctionType

from Script.Config import game_config
from Script.Core import constant, get_text
from Script.Design import handle_premise, virgin_break_gate
from Script.Modules.domains import abilities, activity, h_state, modes
from Script.Modules.gameplay_resolution import instruct_filter

_: FunctionType = get_text._
""" 翻译api """


def group_sex_settle(
    character_id: int,
    target_character_id: int,
    behavior_id: str,
) -> None:
    """
    按行为分组更新玩家群交模板 A，不修改模板 B。
    群交模式关闭、执行者非玩家 0、目标为自身或模板锁定时直接返回。
    插入写入 penis 并清空侍奉。侍奉清空 penis，异行为时重置侍奉，同行为时追加未在列的目标。
    口与肛分别写入 mouth 与 anal。手优先写入空位或同目标的左手、右手，两手均为其他目标时将右手移至左手并把新项写入右手。
    行为名为六九式时，再写入 mouth 并将侍奉重置为该单人目标。
    Keyword arguments:
    character_id -- int，执行行为的角色编号
    target_character_id -- int，交互目标的角色编号
    behavior_id -- str，行为编号
    Return arguments:
    None -- 无返回值
    """
    if not modes.group_sex():
        return
    if character_id != 0 or target_character_id == character_id:
        return
    if h_state.get(character_id, "group_sex_lock_flag"):
        return
    with h_state.editing(character_id) as hs:
        now_template_data = hs.group_sex_body_template_dict["A"]
        if (
            behavior_id
            in game_config.config_behavior_id_list_of_group_sex_body_part[
                "插入"
            ]
        ):
            now_template_data[0]["penis"] = [target_character_id, behavior_id]
            now_template_data[1] = [[-1], -1]
        elif (
            behavior_id
            in game_config.config_behavior_id_list_of_group_sex_body_part[
                "侍奉"
            ]
        ):
            now_template_data[0]["penis"] = [-1, -1]
            if now_template_data[1][1] != behavior_id:
                now_template_data[1] = [[target_character_id], behavior_id]
            elif target_character_id not in now_template_data[1][0]:
                now_template_data[1][0].append(target_character_id)
        elif (
            behavior_id
            in game_config.config_behavior_id_list_of_group_sex_body_part["口"]
        ):
            now_template_data[0]["mouth"] = [target_character_id, behavior_id]
        elif (
            behavior_id
            in game_config.config_behavior_id_list_of_group_sex_body_part["手"]
        ):
            if (
                now_template_data[0]["L_hand"][1] == -1
                or now_template_data[0]["L_hand"][0] == target_character_id
            ):
                now_template_data[0]["L_hand"] = [
                    target_character_id,
                    behavior_id,
                ]
            elif (
                now_template_data[0]["R_hand"][1] == -1
                or now_template_data[0]["R_hand"][0] == target_character_id
            ):
                now_template_data[0]["R_hand"] = [
                    target_character_id,
                    behavior_id,
                ]
            else:
                now_template_data[0]["L_hand"] = now_template_data[0]["R_hand"]
                now_template_data[0]["R_hand"] = [
                    target_character_id,
                    behavior_id,
                ]
        elif (
            behavior_id
            in game_config.config_behavior_id_list_of_group_sex_body_part["肛"]
        ):
            now_template_data[0]["anal"] = [target_character_id, behavior_id]

        behavior_data = game_config.config_behavior[behavior_id]
        if behavior_data.name == _("六九式"):
            now_template_data[0]["mouth"] = [target_character_id, behavior_id]
            now_template_data[1] = [[target_character_id], behavior_id]


def count_group_sex_instruct_list() -> tuple[list[str], list[list]]:
    """
    统计玩家群交模板中的已填行为编号与目标对应记录。
    默认读取模板 A，当 handle_all_group_sex_temple_run_on(0) 成立时一并纳入模板 B。
    Return arguments:
    tuple[list[str], list[list]] -- 首项为经集合去重且顺序不固定的行为编号列表，
    次项为按模板与槽位顺序排列的 [目标编号列表, 行为编号] 记录列表
    """
    group_sex_instruct_list = []
    full_list_of_target_id_and_state_id = []
    tpl_dict = h_state.view(0).group_sex_body_template_dict
    template_data_list = [tpl_dict["A"]]
    if handle_premise.handle_all_group_sex_temple_run_on(0):
        template_data_list.append(tpl_dict["B"])
    for template_data in template_data_list:
        for body_part in template_data[0]:
            target_chara_id = [template_data[0][body_part][0]]
            state_id = template_data[0][body_part][1]
            if state_id != -1:
                group_sex_instruct_list.append(state_id)
                full_list_of_target_id_and_state_id.append(
                    [target_chara_id, state_id]
                )
        target_chara_id_list = template_data[1][0]
        state_id = template_data[1][1]
        if state_id != -1:
            group_sex_instruct_list.append(state_id)
            full_list_of_target_id_and_state_id.append(
                [target_chara_id_list, state_id]
            )
    group_sex_instruct_list = list(set(group_sex_instruct_list))

    return group_sex_instruct_list, full_list_of_target_id_and_state_id


def count_group_sex_character_list() -> list[int]:
    """
    统计玩家群交模板中已参与的角色编号列表。
    默认读取模板 A，当 handle_all_group_sex_temple_run_on(0) 成立时一并纳入模板 B。
    收集对单部位中非 -1 的目标编号，以及不含 -1 的侍奉目标列表。
    Return arguments:
    list[int] -- 经集合去重且顺序不固定的参与角色编号列表
    """
    group_sex_chara_id_list = []
    tpl_dict = h_state.view(0).group_sex_body_template_dict
    template_data_list = [tpl_dict["A"]]
    if handle_premise.handle_all_group_sex_temple_run_on(0):
        template_data_list.append(tpl_dict["B"])
    for template_data in template_data_list:
        for body_part in template_data[0]:
            target_chara_id = template_data[0][body_part][0]
            if target_chara_id != -1:
                group_sex_chara_id_list.append(target_chara_id)
        target_chara_id_list = template_data[1][0]
        if -1 not in target_chara_id_list:
            group_sex_chara_id_list += target_chara_id_list
    group_sex_chara_id_list = list(set(group_sex_chara_id_list))

    return group_sex_chara_id_list


def get_status_id_list_from_group_sex_body_part(body_part: str) -> list[str]:
    """
    按群交部位键筛选当前可用的行为编号列表，并保持配置顺序。
    先将部位键映射至行为分组（未知键抛出 KeyError），再保留存在指令映射
    且通过 instruct_filter.judge_single_instruct_filter（关闭类型过滤、共用前提缓存）的项。
    当玩家当前交互目标非自身时，经 virgin_break_gate.takes_kept_virginity 剔除会夺走目标仍有的处女素质的行为。
    Keyword arguments:
    body_part -- str，部位键（mouth、L_hand、R_hand、penis、侍奉或 anal）
    Return arguments:
    list[str] -- 通过过滤的可用行为编号列表
    """
    new_status_id_list: list[str] = []
    config_body_part = {
        "mouth": "口",
        "L_hand": "手",
        "R_hand": "手",
        "penis": "插入",
        "侍奉": "侍奉",
        "anal": "肛",
    }[body_part]
    status_id_list = game_config.config_behavior_id_list_of_group_sex_body_part[
        config_body_part
    ]
    now_premise_data: dict[str, float] = {}
    new_status_id_list = []
    for status_id in status_id_list:
        if status_id in constant.behavior_id_to_instruct_id:
            instruct_id = constant.behavior_id_to_instruct_id[status_id]
            filter_judge, now_premise_data = (
                instruct_filter.judge_single_instruct_filter(
                    instruct_id,
                    now_premise_data,
                    constant.InstructType.SEX,
                    use_type_filter_flag=False,
                )
            )
            if filter_judge:
                status_data = game_config.config_behavior[status_id]
                status_tag_list = status_data.tag.split("|")
                if activity.target(0) != 0:
                    target_id = activity.target(0)
                    if virgin_break_gate.takes_kept_virginity(
                        status_tag_list, abilities.talent(target_id)
                    ):
                        continue

                new_status_id_list.append(status_id)

    return new_status_id_list


def get_now_template_part_list() -> tuple[list[str], list[str]]:
    """
    查询玩家群交模板 A 中各部位的空缺与占用列表。
    未填行为的对单部位计入空缺，已填行为的对单部位计入占用，但 penis 仅在侍奉未设时计入空缺。
    当 penis 已占时，两列表均不含侍奉。
    当 penis 未占时，侍奉未设则计入空缺，已设则计入占用。侍奉已设且人数少于 4 时，向空缺追加加入侍奉的译文。
    Return arguments:
    tuple[list[str], list[str]] -- 首项为空缺部位列表，次项为已占用部位列表
    """

    A_template_data = h_state.view(0).group_sex_body_template_dict["A"]

    now_template_empty_part_list = []
    now_template_not_empty_part_list = []
    wait_upon_flag = True
    wait_upon_state_id = A_template_data[1][1]
    for body_part in A_template_data[0]:
        state_id = A_template_data[0][body_part][1]
        if state_id == -1:
            if body_part != "penis":
                now_template_empty_part_list.append(body_part)
            elif wait_upon_state_id == -1:
                now_template_empty_part_list.append(body_part)
        elif body_part == "penis":
            wait_upon_flag = False
        if state_id != -1:
            now_template_not_empty_part_list.append(body_part)

    if wait_upon_flag:
        target_chara_id_list = A_template_data[1][0]
        if wait_upon_state_id == -1:
            now_template_empty_part_list.append("侍奉")
        elif wait_upon_state_id != -1:
            now_template_not_empty_part_list.append("侍奉")
            if len(target_chara_id_list) < 4:
                now_template_empty_part_list.append(_("加入侍奉"))

    return now_template_empty_part_list, now_template_not_empty_part_list


def clear_character_data_in_group_sex_template(character_id: int) -> bool:
    """
    从玩家群交模板 A 与模板 B 的各部位及侍奉列表中清除指定角色。
    内部调用 h_state.remove_from_group_sex_template 完成移除，并在至少一处发生变化时返回 True。
    Keyword arguments:
    character_id -- int，待清除的角色编号
    Return arguments:
    bool -- 模板内容发生变更时返回 True，否则返回 False
    """

    return h_state.remove_from_group_sex_template(0, (character_id,)) > 0
