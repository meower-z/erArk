"""
助理服务
========
本模块提供无界面依赖的助理干员业务规则，包含候选列表筛选、助理任免与替换、每周随机轮换、读档跟随状态修补与助理服务选项切换。
本模块通过 ui_hooks 发送分隔线与提示文本，不直接导入界面、窗口或输入输出模块。
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
""" 同居房间的未翻译系统路径，因需与宿舍路径字符串比对而不可翻译。 """
OPTION_PREFIXES = {
    4: "assistant_send_food_",
    5: "morning_service_",
    6: "night_service_",
}
""" 多档位助理服务编号到对应二段行为前缀的映射表。 """
SWITCH_PREFIXES = {
    3: "support_service_",
    7: "cohabitation_",
    8: "love_support_",
}
""" 开关型助理服务编号到对应二段行为前缀的映射表。 """


def get_assistant_candidates() -> list[int]:
    """
    按编号升序筛选可担任助理的在编干员，排除玩家 0、处于 2 或 7 类异常状态的角色、监狱长与访客。
    Return arguments:
    list[int] -- 符合条件的候选干员角色编号列表
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
    从助理候选列表中随机抽取一名干员，发出每周抽签提示并调用 assistant_replace 完成替换。
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
    执行助理的任命、解任或替换，并发送分隔线与结果提示。
    存在当前助理时先清理其跟随状态、同居宿舍与服务设置。
    新目标与当前助理相同时解除助理职务，处于 2 或 7 类异常状态时拒绝任命，否则任命新目标并更新二段行为。
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
    """读档时修补：跟随状态超出 0-4 的角色归零"""
    for character_data in identity.table().values():
        if flags.get(character_data.cid, "is_follow") > 4:
            flags.set(character_data.cid, is_follow=0)


def cycle_service(service_cid: int) -> None:
    """
    按规则切换当前助理指定服务的档位，并在切换成功时同步关联状态。
    服务 2 翻转开关并步进跟随状态，随后直接返回，不调用 _settle_service_behaviors。
    其余服务处于末档时将档位归零，未到末档时校验下一档解锁条件。
    非调试模式解锁失败时提示原因并将档位归零，随后直接返回，不调用 _settle_service_behaviors。
    末档归零或推进到下一档完成后，调用 _settle_service_behaviors 同步二段行为与宿舍。
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
    按当前助理服务档位同步对应的二段行为标记，并在服务 7 开关变化时迁移或恢复宿舍。
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
