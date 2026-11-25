"""
口上快速测试与重建服务（talk_test_service）
===========================================
提供角色口上配置重建、重加载、编号列表解析与触发测试报告功能。
本模块不导入 Script.UI 与 Script.Settle。
"""

import csv
import json
import os
from types import FunctionType

from Script.Config import game_config
from Script.Core import constant, get_text
from Script.Design import handle_premise
from Script.Modules.domains import activity, identity, roster

_: FunctionType = get_text._
""" 本地化翻译函数。 """
GROUP_SIZE = 10
""" 批量口上测试每轮展示的口上条数上限（10）。 """


def build_csv_config(
    file_path: str, file_name: str, chara_adv_id: int, character_talk_data: dict
) -> None:
    """
    读取单个口上 CSV，筛出指定 adv_id 的条目并写入目标配置字典。
    Keyword arguments:
    file_path -- str，CSV 文件路径
    file_name -- str，CSV 文件名，含 premise 时归入 TalkPremise
    chara_adv_id -- int，目标角色 adv_id
    character_talk_data -- dict，待写入的口上配置字典
    Return arguments:
    None -- 结果直接写入 character_talk_data
    """
    with open(file_path, encoding="utf-8") as now_file:
        now_read = csv.DictReader(now_file)
        now_type_data = {}
        get_text_data = {}
        file_id = file_name.split(".")[0]
        path_list = file_path.split(os.sep)
        file_id = path_list[-2] + "_" + file_id
        i = 0
        type_text = "Talk"
        if "premise" in file_name:
            type_text = "TalkPremise"
        character_talk_data.setdefault(type_text, {})
        character_talk_data[type_text].setdefault("data", [])
        character_talk_data[type_text].setdefault("gettext", {})
        for row in now_read:
            if i in (0, 3):
                i += 1
                continue
            if i == 1:
                for k in row:
                    now_type_data[k] = row[k]
                i += 1
                continue
            if i == 2:
                for k in row:
                    get_text_data[k] = int(row[k])
                i += 1
                continue
            if int(row["adv_id"]) != chara_adv_id:
                continue
            for k in now_type_data:
                now_type = now_type_data[k]
                if not len(row[k]):
                    del row[k]
                    continue
                if now_type == "int":
                    row[k] = int(row[k])
                elif now_type == "str":
                    row[k] = str(row[k]).replace('"', '\\"')
                elif now_type == "bool":
                    row[k] = int(row[k])
                elif now_type == "float":
                    row[k] = float(row[k])
                if k == "cid":
                    row[k] = file_id + row[k]
            row["version"] = 1
            if int(row["adv_id"]) != 0 and file_id.count("_") == 3:
                row["version"] = int(file_id.rsplit("_", 1)[-1])
            character_talk_data[type_text]["data"].append(row)
        get_text_data["version"] = 0
        character_talk_data[type_text]["gettext"] = get_text_data


def build_chara_talk(chara_adv_id: int = 0) -> None:
    """
    读取 data/talk 除 ai 外全部 CSV，仅保留 adv_id 匹配行（0 为公共）。
    非 0 先读现有 JSON 删该 adv_id 的 Talk 行，读取失败则从空字典开始。
    入参为 0 时从空字典开始，最终重写 data/Character_Talk.json。
    Keyword arguments:
    chara_adv_id -- int，目标角色 adv_id，默认 0
    Return arguments:
    None -- 无返回值
    """
    talk_dir = os.path.join("data", "talk")
    character_talk_data_path = os.path.join("data", "Character_Talk.json")
    try:
        if chara_adv_id == 0:
            character_talk_data = {}
        else:
            with open(character_talk_data_path, encoding="utf-8") as f:
                character_talk_data = json.load(f)
            for key in character_talk_data["Talk"]["data"].copy():
                if key["adv_id"] == chara_adv_id:
                    character_talk_data["Talk"]["data"].remove(key)
    except BaseException:
        character_talk_data = {}
    for i in os.listdir(talk_dir):
        if i == "ai":
            continue
        now_dir = os.path.join(talk_dir, i)
        if os.path.isdir(now_dir):
            for root, _dirs, files in os.walk(now_dir):
                for talk_file in files:
                    now_f = os.path.join(root, talk_file)
                    build_csv_config(
                        now_f, talk_file, chara_adv_id, character_talk_data
                    )
        else:
            build_csv_config(now_dir, i, chara_adv_id, character_talk_data)
    with open(
        character_talk_data_path, "w", encoding="utf-8"
    ) as talk_data_file:
        json.dump(character_talk_data, talk_data_file, ensure_ascii=False)


def _talk_total() -> int:
    """统计当前已加载口上配置表中的条目总数。"""
    return sum(len(rows) for rows in game_config.config_talk_data.values())


def reload_talk() -> tuple[int, int]:
    """
    重新加载口上配置数据，返回加载前后的条目总数。
    Keyword arguments:
    无
    Return arguments:
    tuple[int, int] -- 加载前与加载后的口上条目总数
    """
    old_total = _talk_total()
    game_config.reload_talk_data()
    return old_total, _talk_total()


def refresh_text(old_total: int, new_total: int) -> str:
    """
    生成口上文件刷新完毕的统计提示文本。
    Keyword arguments:
    old_total -- int，刷新前的口上条目总数
    new_total -- int，刷新后的口上条目总数
    Return arguments:
    str -- 含原总数、新总数与新增数的提示文本
    """
    return _("\n口上文件刷新完毕\n") + _(
        "原数据总数为{0}，新数据总数为{1}，新增数据总数为{2}\n\n"
    ).format(old_total, new_total, new_total - old_total)


def chara_by_adv(chara_adv_id: int) -> int:
    """
    按 adv_id 查找首个匹配的角色编号，未找到时返回 0。
    Keyword arguments:
    chara_adv_id -- int，角色的 adv_id
    Return arguments:
    int -- 匹配到的角色编号，不存在时为 0
    """
    for chara_id in identity.table():
        if identity.of(chara_id).adv == chara_adv_id:
            return chara_id
    return 0


def parse_talk_id_list(input_text: str) -> list[int]:
    """
    解析逗号与区间格式的口上编号文本，忽略无效片段并保序去重。
    Keyword arguments:
    input_text -- str，支持中英文逗号及 a-b 区间的输入文本
    Return arguments:
    list[int] -- 去重后的口上编号列表
    """
    result: list[int] = []
    for raw_part in input_text.replace("，", ",").split(","):
        part = raw_part.strip()
        if not part:
            continue
        if "-" in part:
            ends = [end.strip() for end in part.split("-")]
            if len(ends) == 2 and ends[0].isdigit() and ends[1].isdigit():
                low, high = sorted((int(ends[0]), int(ends[1])))
                result.extend(range(low, high + 1))
        elif part.isdigit():
            result.append(int(part))
    return list(dict.fromkeys(result))


def _roles(full_talk_id: str, target_chara_id: int) -> tuple[str, int, int]:
    """推断口上的触发人与交互对象角色编号，并生成对应说明文本。"""
    premises = game_config.config_talk_premise_data[full_talk_id]
    behavior = game_config.config_behavior[
        game_config.config_talk[full_talk_id].behavior_id
    ]
    if "sys_0" in premises:
        text, start = _("  触发人：博士\n"), 0
    elif "sys_1" in premises:
        text, start = _("  触发人：NPC\n"), target_chara_id
    elif behavior.trigger == "npc":
        text = _("  触发人：未填写，本测试中默认选择为NPC\n")
        start = target_chara_id
    else:
        text, start = _("  触发人：未填写，本测试中默认选择为博士\n"), 0
    if "二段结算" in behavior.tag:
        text += _("  交互对象：同触发人，二段结算的交互对象只能是触发人自己\n")
        end = start
    elif "sys_4" in premises:
        text, end = text + _("  交互对象：博士\n"), 0
    elif "sys_5" in premises:
        text, end = text + _("  交互对象：NPC\n"), target_chara_id
    elif start == 0:
        text += _("  交互对象：未填写，本测试中默认选择为NPC\n")
        end = target_chara_id
    else:
        text, end = text + _("  交互对象：未填写，本测试中默认选择为博士\n"), 0
    return text, start, end


def _premise_met(premise: str, chara_id: int) -> float:
    """判定单条前提条件是否满足，CVP 前缀走综合数值判定。"""
    if "CVP" in premise:
        return handle_premise.handle_comprehensive_value_premise(
            chara_id, premise.split("_")[1:]
        )
    return constant.handle_premise_data[premise](chara_id)


def test_single_talk(target_chara_id: int, talk_id: int) -> tuple[str, bool]:
    """
    测试指定角色与口上编号的触发条件并渲染文本，返回报告与结果。
    Keyword arguments:
    target_chara_id -- int，目标角色编号，0 表示未找到角色
    talk_id -- int，待测试的口上数字编号
    Return arguments:
    tuple[str, bool] -- 完整测试报告文本与是否通过标志
    """
    from Script.Design import talk

    target = identity.of(target_chara_id)
    full_adv_id = str(target.adv).rjust(4, "0")
    full_talk_id = f"chara_{full_adv_id}_{target.name}{talk_id}"
    text = "\n"
    if target_chara_id == 0:
        return text + _("未找到该角色，请确认是否输入正确\n"), False
    if full_talk_id not in game_config.config_talk:
        text += _("未找到该口上（id={0}），请确认是否输入正确\n").format(
            talk_id
        )
        return text, False
    passed = True
    text += _("测试角色：{0}\n").format(target.name)
    text += _("口上id：{0}\n").format(full_talk_id)
    if not roster.has(target_chara_id):
        text += _("  博士未获得该角色(X)\n")
        passed = False
    else:
        text += _("  博士已获得该角色(√)\n")
    if activity.target(0) != target_chara_id:
        text += _("  博士当前交互对象不是该角色(X)\n")
        passed = False
    else:
        text += _("  博士当前交互对象是该角色(√)\n")
    behavior_id = game_config.config_talk[full_talk_id].behavior_id
    text += _("\n指令状态：{0}\n").format(
        game_config.config_behavior[behavior_id].name
    )
    text += _("\n触发人与交互对象：\n")
    roles, start, end = _roles(full_talk_id, target_chara_id)
    text += roles
    with activity.target_as(start, end):
        context = game_config.config_talk[full_talk_id].context
        text += _("\n口上原文本：\n  {0}\n").format(context)
        text += _("口上输出文本：\n  {0}\n").format(
            talk.code_text_to_draw_text(context, start)
        )
        text += _("\n前提条件：\n")
        for premise in game_config.config_talk_premise_data[full_talk_id]:
            if _premise_met(premise, start):
                text += _("  {0}：满足(√)\n").format(premise)
            else:
                text += _("  {0}：不满足(X)\n").format(premise)
                passed = False
        if passed:
            text += _("\n最终结果：\n  测试通过，该口上可以触发\n")
        else:
            text += _("\n最终结果：\n  测试未通过，该口上无法触发\n")
        return text, passed


def item_header(index: int, total: int, talk_id: int) -> str:
    """
    生成批量测试中单条口上的序号标题行。
    Keyword arguments:
    index -- int，当前条目在总列表中的 1 起序号
    total -- int，本次批量测试的总条数
    talk_id -- int，当前测试的口上编号
    Return arguments:
    str -- 格式化后的单条标题文本
    """
    return _("\n===== 第 {0} 条 / 共 {1} 条（口上id：{2}） =====").format(
        index, total, talk_id
    )


def group_prompt(start: int, end: int) -> str:
    """
    生成分组批量测试的轮次完成提示文本。
    Keyword arguments:
    start -- int，本轮起始序号
    end -- int，本轮结束序号
    Return arguments:
    str -- 提示玩家确认是否继续下一轮的文本
    """
    return _("\n本轮已测试第 {0}-{1} 条，请确认后选择是否继续下一轮").format(
        start, end
    )


def summary_lines(
    pass_ids: list[int], fail_ids: list[int], stopped: bool = False
) -> list[str]:
    """
    生成批量口上测试的汇总统计与通过、未通过编号文本行。
    Keyword arguments:
    pass_ids -- list[int]，通过测试的口上编号列表
    fail_ids -- list[int]，未通过测试的口上编号列表
    stopped -- bool，是否中途停止测试，默认 False
    Return arguments:
    list[str] -- 汇总提示行列表
    """
    lines = [_("\n测试已停止，以下是已测试部分的汇总")] if stopped else []
    lines.append(
        _("\n汇总：共测试 {0} 条，通过 {1} 条，未通过 {2} 条").format(
            len(pass_ids) + len(fail_ids), len(pass_ids), len(fail_ids)
        )
    )
    if pass_ids:
        joined = "、".join(str(talk_id) for talk_id in pass_ids)
        lines.append(_("\n通过的口上id：{0}").format(joined))
    else:
        lines.append(_("\n通过的口上id：无"))
    if fail_ids:
        joined = "、".join(str(talk_id) for talk_id in fail_ids)
        lines.append(_("未通过的口上id：{0}\n").format(joined))
    else:
        lines.append(_("未通过的口上id：无\n"))
    return lines


def run_tests(
    target_chara_id: int, talk_ids: list[int], start: int, total: int
) -> tuple[list[str], list[int], list[int]]:
    """
    依次执行一组口上测试并按编号汇总报告行、通过列表与未通过列表。
    Keyword arguments:
    target_chara_id -- int，目标角色编号
    talk_ids -- list[int]，本组待测口上编号列表
    start -- int，本组首条的 1 起显示序号
    total -- int，整次批量测试的总条数
    Return arguments:
    tuple[list[str], list[int], list[int]] -- 报告行、通过与未通过列表
    """
    lines: list[str] = []
    passed: list[int] = []
    failed: list[int] = []
    for index, talk_id in enumerate(talk_ids, start):
        text, ok = test_single_talk(target_chara_id, talk_id)
        lines += [item_header(index, total, talk_id), text]
        (passed if ok else failed).append(talk_id)
    return lines, passed, failed
