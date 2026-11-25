"""
助理服务
========
本模块提供无界面依赖的助理业务规则，涵盖候选筛选、任免替换、每周轮换、读档跟随状态修补与服务档位切换。
本模块通过 ui_hooks 发送分隔线与提示文本。
本模块不直接导入界面、结算或输入输出模块。
"""

import random
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import attr_calculation, handle_premise, map_handle
from Script.Design import second_behavior
from Script.Modules.domains import chara_life, flags, identity, modes
from Script.Modules.domains import relations, roster, visitor, work
from Script.Modules.gameplay_resolution import ui_hooks
from Script.Modules.save_load import reset
from Script.System.Dormitory_System import common as dormitory_common

_: FunctionType = get_text._
""" 文本翻译函数，指向 get_text._。 """
COHABIT_ROOM = ["中枢", "博士房间"]
""" 同居房间的未翻译地图路径段列表，供 map_handle 拼接后与宿舍路径比对。 """
OPTION_PREFIXES = {
    4: "assistant_send_food_",
    5: "morning_service_",
    6: "night_service_",
}
""" 多档位助理服务编号（4 送饭、5 早安、6 晚安）到二段行为前缀的映射。 """
SWITCH_PREFIXES = {
    3: "support_service_",
    7: "cohabitation_",
    8: "love_support_",
}
""" 开关型助理服务编号（3 辅佐、7 同居、8 助攻）到二段行为前缀的映射。 """


def get_assistant_candidates() -> list[int]:
    """
    按角色编号升序筛选在编名单（roster.active_sorted）中可担任助理的角色。
    筛选排除玩家 0、处于 2 或 7 类异常状态（AI 停止或离线）的角色、监狱长与访客。
    Return arguments:
    list[int] -- 符合条件的候选角色编号列表
    """
    return [
        npc_id
        for npc_id in roster.active_sorted()
        if npc_id != 0
        and not handle_premise.handle_unnormal_27(npc_id)
        and npc_id != work.warden()
        and not visitor.is_visitor(npc_id)
    ]


def select_random_assistant() -> None:
    """
    从 get_assistant_candidates 返回的候选列表中随机抽取一名角色。
    函数通过 ui_hooks.emit_notice 发送本周抽签提示（等待确认并按文本宽度排版）。
    提示发出后，函数调用 assistant_replace 完成助理替换。
    Return arguments:
    None -- 无返回值
    """
    assistant_id = random.choice(get_assistant_candidates())
    ui_hooks.emit_notice(
        _("\n○本周抽签选中了{0}作为{1}的助理\n").format(
            identity.of(assistant_id).name, identity.of(0).name
        ),
        wait=True,
        use_text_width=True,
    )
    assistant_replace(assistant_id)


def assistant_replace(new_assistant_id: int) -> None:
    """
    执行助理的任命、解任或替换，并通过 ui_hooks 发送分隔线与结果提示。
    存在当前助理时，函数先清零其跟随状态与助理服务。
    若当前助理住在同居房间，函数同时恢复其宿舍。
    即便目标角色随后因异常状态被拒绝，这两步清理仍会执行。
    目标与当前助理相同时，函数将玩家助理编号置为 0。
    目标处于 2 或 7 类异常状态（AI 停止或离线）时，函数拒绝任命且不改动玩家助理编号。
    其余情况下，函数任命目标角色，将 is_follow 与服务 2（跟随服务）设为 1 并更新二段行为。
    Keyword arguments:
    new_assistant_id -- int，目标角色编号
    Return arguments:
    None -- 无返回值
    """
    old_id = relations.assistant_character_id(0)
    old_assistant_data: identity.Identity | None = None
    if old_id != 0:
        old_assistant_data = identity.of(old_id)
        flags.set(old_id, is_follow=0)
        if chara_life.dormitory(
            old_id
        ) == map_handle.get_map_system_path_str_for_list(COHABIT_ROOM):
            dormitory_common.restore_character_dormitory(old_id)
        zero = attr_calculation.get_assistant_services_zero()
        relations.assistant_services.set(old_id, zero)

    ui_hooks.emit_divider("-")
    info_text = ""
    if new_assistant_id == old_id:
        relations.assistant_character_id.set(0, 0)
    elif handle_premise.handle_unnormal_27(new_assistant_id):
        info_text += _("\n{0}的状态异常，无法任命为助理干员\n").format(
            identity.of(new_assistant_id).name
        )
        old_assistant_data = None
    else:
        relations.assistant_character_id.set(0, new_assistant_id)
        flags.set(new_assistant_id, is_follow=1)
        relations.assistant_services.set_item(new_assistant_id, 2, 1)
        second_behavior.character_get_second_behavior(
            new_assistant_id, "not_as_assistant", reset=True
        )
        second_behavior.character_get_second_behavior(
            new_assistant_id, "chosen_as_assistant"
        )
        info_text += _("\n{0}成为助理干员了，并默认开启智能跟随模式\n").format(
            identity.of(new_assistant_id).name
        )
        if old_assistant_data is not None:
            if relations.assistant_services(old_id).get(10) == 1:
                relations.assistant_services.set_item(new_assistant_id, 10, 1)
    if old_assistant_data is not None:
        second_behavior.character_get_second_behavior(
            new_assistant_id, "chosen_as_assistant", reset=True
        )
        second_behavior.character_get_second_behavior(
            old_assistant_data.cid, "not_as_assistant"
        )
        info_text += _(
            "\n\n{0}不再是助理干员了，已清零助理服务相关的设置\n\n"
        ).format(old_assistant_data.name)
    ui_hooks.emit_notice(info_text, wait=True, use_text_width=True)


@reset.repair
def repair_follow_flag() -> None:
    """
    读档修补钩子，遍历身份表中全部角色，将 is_follow 大于 4 的角色该标记归零。
    小于等于 4（含负数）的取值保持不变。
    Return arguments:
    None -- 无返回值
    """
    for character_data in identity.table().values():
        if flags.get(character_data.cid, "is_follow") > 4:
            flags.set(character_data.cid, is_follow=0)


def cycle_service(service_cid: int) -> None:
    """
    按规则切换当前助理指定服务的档位。
    服务 2（跟随服务）翻转开关布尔值、步进 is_follow（为 1 或大于 4 时归零，其余加 1）后直接返回。
    其余服务处于末档时归零，未到末档时校验下一档解锁条件。
    非调试模式下解锁失败时，函数通过 ui_hooks 发送失败提示、将档位归零并直接返回。
    由于跳过 _settle_service_behaviors，已设置的二段行为标记保持不变。
    末档归零或推进档位后，函数调用 _settle_service_behaviors 同步二段行为与宿舍。
    Keyword arguments:
    service_cid -- int，助理服务编号
    Return arguments:
    None -- 无返回值
    """
    assistant_id = relations.assistant_character_id(0)
    if service_cid == 2:
        with relations.assistant_services.editing(assistant_id) as services:
            services[2] = not services.get(2, 0)
        follow = flags.get(assistant_id, "is_follow")
        flags.set(
            assistant_id,
            is_follow=0 if follow == 1 or follow > 4 else follow + 1,
        )
        return
    option_data = game_config.config_assistant_services_option[service_cid]
    options = option_data[0]
    with relations.assistant_services.editing(assistant_id) as services:
        level = services.setdefault(service_cid, 0)
    if level == len(options) - 1:
        relations.assistant_services.set_item(assistant_id, service_cid, 0)
    else:
        judge, reason = attr_calculation.judge_require(
            [option_data[1][level + 1]],
            assistant_id,
            hypnosis_replace_trust_flag=True,
        )
        if not judge and not modes.debug():
            ui_hooks.emit_notice(
                _("\n  ○更改失败，[{0}]{1}\n").format(
                    options[level + 1], reason
                ),
                wait=True,
            )
            relations.assistant_services.set_item(assistant_id, service_cid, 0)
            return
        relations.assistant_services.set_item(
            assistant_id, service_cid, level + 1
        )
    _settle_service_behaviors(assistant_id, service_cid, len(options))


def _settle_service_behaviors(
    assistant_id: int, service_cid: int, option_len: int
) -> None:
    """
    按当前助理的服务档位同步二段行为标记，并在服务 7（同居服务）下同步同居宿舍。
    属于 OPTION_PREFIXES 的服务先重置 0 至 option_len - 1 的同名标记，再设置当前档位标记。
    属于 SWITCH_PREFIXES 的服务先重置 on 与 off 标记，再按档位真假设置对应标记。
    服务 7 档位为 1 时先登记常住宿舍再迁入 COHABIT_ROOM。
    服务 7 档位不为 1 且当前宿舍为 COHABIT_ROOM 时调用 restore_character_dormitory 恢复宿舍。
    Keyword arguments:
    assistant_id -- int，当前助理角色编号
    service_cid -- int，助理服务编号
    option_len -- int，该服务的选项总数
    Return arguments:
    None -- 无返回值
    """
    level = relations.assistant_services(assistant_id)[service_cid]
    if service_cid in OPTION_PREFIXES:
        prefix = OPTION_PREFIXES[service_cid]
        for index in range(option_len):
            second_behavior.character_get_second_behavior(
                assistant_id, f"{prefix}{index}", reset=True
            )
        second_behavior.character_get_second_behavior(
            assistant_id, f"{prefix}{level}"
        )
    elif service_cid in SWITCH_PREFIXES:
        prefix = SWITCH_PREFIXES[service_cid]
        second_behavior.character_get_second_behavior(
            assistant_id, f"{prefix}on", reset=True
        )
        second_behavior.character_get_second_behavior(
            assistant_id, f"{prefix}off", reset=True
        )
        second_behavior.character_get_second_behavior(
            assistant_id, f"{prefix}on" if level else f"{prefix}off"
        )
    if service_cid == 7:
        room = map_handle.get_map_system_path_str_for_list(COHABIT_ROOM)
        if level == 1:
            dormitory_common.register_permanent_dormitory(assistant_id)
            chara_life.dormitory.set(assistant_id, room)
        elif chara_life.dormitory(assistant_id) == room:
            dormitory_common.restore_character_dormitory(assistant_id)
