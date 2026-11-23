# -*- coding: UTF-8 -*-
"""
无限射精Mod
功能：
1. 移除精液耗尽判断，即使精液耗尽也能射精
2. 新增乘以十的函数，使射精量变为原来的十倍
3. 使用mod自带的数据文件替代游戏原数据文件
4. 替换精液量前提函数，绕过绝顶结算中的无精液高潮分支（2026-07起新增的射精前置判断）
"""

from __future__ import annotations

import os
import csv
import random
from contextlib import suppress
from typing import TYPE_CHECKING
from Script.Modules.domains import abilities, activity
from Script.Modules.domains import identity

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Protocol

    from Script.Config import game_config
    from Script.Core.get_text import _

    # mod 系统注入的 get_mod_asset：素材别名 -> 实际路径，找不到时为 None
    get_mod_asset: Callable[[str], str | None]

    class _SemenConfig(Protocol):
        """_load_mod_semen_data 用 type() 现造的射精量数据对象"""

        cid: int
        base_semen_amount: int

else:
    # globals() 返回 Mod 加载器用 exec 运行本脚本时传入的字典。
    # 本分支在运行时把 game_config、_ 和 get_mod_asset 绑定为该字典中的同名值。
    # 该字典缺少某个名字时，suppress(KeyError) 让这个名字保持未绑定。
    with suppress(KeyError):
        game_config = globals()["game_config"]
    with suppress(KeyError):
        _ = globals()["_"]
    with suppress(KeyError):
        get_mod_asset = globals()["get_mod_asset"]


# ===== 以下变量由mod系统自动注入 =====
# game_config - 游戏配置
# game_type - 游戏类型定义
# _ - 翻译函数
# get_mod_asset - 获取mod素材路径的函数
# call_original - 调用原函数的方法

# ===== Mod自带的射精量数据 =====
# 在mod加载时读取自带的CSV数据文件
_mod_semen_config: dict[int, _SemenConfig] = {}


def _load_mod_semen_data() -> None:
    """加载mod自带的射精量数据"""
    global _mod_semen_config

    # 获取mod素材路径
    data_path = get_mod_asset(
        "mod:semen_boost/assets/data/Semen_Shoot_Amount.csv"
    )

    if data_path and os.path.exists(data_path):
        try:
            with open(data_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                # CSV格式：
                # 第1行(表头)：字段名 - 由DictReader自动处理
                # 第2行：字段描述
                # 第3行：字段类型
                # 第4行：标记行（全0）
                # 第5行：数据分组名
                # 第6行开始：实际数据
                rows = list(reader)
                for i, row in enumerate(rows):
                    # 跳过前4行（描述、类型、标记、分组名），从第5行开始是数据
                    if i < 4:
                        continue
                    # 检查cid是否为有效数字
                    cid_str = row.get("cid", "")
                    if not cid_str or not cid_str.isdigit():
                        continue
                    cid = int(cid_str)
                    base_amount_str = row.get("base_semen_amount", "10")
                    if not base_amount_str.isdigit():
                        base_amount_str = "10"
                    base_amount = int(base_amount_str)
                    _mod_semen_config[cid] = type(
                        "SemenConfig",
                        (),
                        {"cid": cid, "base_semen_amount": base_amount},
                    )()
            print(f"[semen_boost] 成功加载mod射精量数据: {_mod_semen_config}")
        except Exception as e:
            print(f"[semen_boost] 加载数据文件失败: {e}")
            # 加载失败时使用默认值（原版数值的两倍）
            _mod_semen_config = {
                0: type(
                    "SemenConfig", (), {"cid": 0, "base_semen_amount": 20}
                )(),
                1: type(
                    "SemenConfig", (), {"cid": 1, "base_semen_amount": 40}
                )(),
                2: type(
                    "SemenConfig", (), {"cid": 2, "base_semen_amount": 100}
                )(),
            }
    else:
        # 如果找不到数据文件，使用硬编码的默认值（原版两倍）
        _mod_semen_config = {
            0: type("SemenConfig", (), {"cid": 0, "base_semen_amount": 20})(),
            1: type("SemenConfig", (), {"cid": 1, "base_semen_amount": 40})(),
            2: type("SemenConfig", (), {"cid": 2, "base_semen_amount": 100})(),
        }
        print(f"[semen_boost] 使用默认射精量数据:  {_mod_semen_config}")


# 在模块加载时执行数据加载
_load_mod_semen_data()


# ===== 新增函数：乘以十 =====
def multiply_by_ten(value: int) -> int:
    """
    乘积函数 - 将输入的数字乘以十

    参数:
        value:  输入的数字

    返回:
        该数字乘以十的结果
    """
    return value * 10


# ===== 替换函数：无精液时也判定为"有精液"，跳过绝顶结算中的无精液高潮分支 =====
def modded_handle_pl_semen_le_2(character_id: int) -> int:
    """
    用于替换「玩家精液量小于等于 2ml」前提的函数，恒返回 0。

    参数:
        character_id: int，角色编号（前提函数统一签名，本函数不使用）

    返回:
        int -- 权重，恒为 0

    用途:
        Script/Settle/orgasm_settle.py 的 orgasm_judge 在打开射精面板前调用 handle_premise.handle_pl_semen_le_2(0)。
        返回真时登记 p_no_semen_climax 并跳过射精结算。
        替换本函数后，精液耗尽也能进入射精流程。

    注意:
        本替换只影响通过 handle_premise.handle_pl_semen_le_2 属性的调用
        （含 orgasm_settle 与 ejaculation_service.common_ejaculation）。
        constant.handle_premise_data["pl_semen_le_2"] 保留导入时的原函数引用，口上与事件前提仍按真实精液量判定。
    """
    return 0


# ===== 替换函数：修改后的通用射精结算 =====
def modded_common_ejaculation() -> tuple[str, int]:
    """
    修改后的通用射精结算函数

    修改内容：
    1. 移除了 handle_premise. handle_pl_semen_le_2(0) 的判断，即使精液耗尽也能射精
    2. 使用mod自带的射精量数据文件替代原版数据
    3. 计算semen_count时调用multiply_by_ten函数使数值变大十倍

    返回:
        semen_text: 射精文本
        semen_count:  射精量
    """
    from Script.Design import handle_premise, handle_ability
    from Script.Modules.domains import action_info, dirty, h_meters, h_state
    from Script.Modules.domains import tallies

    # 乘以一个随机数补正
    random_weight = random.uniform(0.8, 1.2)

    # 额外调整的文本提示
    extra_text = ""

    # ===== 修改点1：移除了精液耗尽判断 =====
    # 原代码：
    # if handle_premise.handle_pl_semen_le_2(0):
    #     return _("只流出了些许前列腺液，已经射不出精液了"), 0
    # 现在不再进行该判断，直接进入射精计算
    # 注意：同样的判断在 Script/Settle/orgasm_settle.py 的 orgasm_judge 中还有一处，
    # 位于本函数被调用之前，由 modded_handle_pl_semen_le_2 负责绕过

    # ===== 修改点2：使用mod自带的数据文件 =====
    # 原代码使用 game_config.config_semen_shoot_amount
    # 现在使用 _mod_semen_config（基础值为原版两倍）

    # 基础射精值，小中多射精区分
    endure_cnt = h_state.get(0, "endure_not_shot_count")
    semen_count: float
    if activity.second_behavior(0, "p_orgasm_strong") == 1:
        base_amount = _mod_semen_config[2].base_semen_amount
        semen_count = int(base_amount * random_weight) * (endure_cnt + 1)
        semen_text = _("超大量射精，射出了")
    elif activity.second_behavior(0, "p_orgasm_normal") == 1:
        base_amount = _mod_semen_config[1].base_semen_amount
        semen_count = int(base_amount * random_weight) * (endure_cnt + 1)
        semen_text = _("大量射精，射出了")
    else:
        base_amount = _mod_semen_config[0].base_semen_amount
        semen_count = int(base_amount * random_weight)
        semen_text = _("射精，射出了")

    # ===== 修改点3：调用乘以十的新增函数 =====
    semen_count = multiply_by_ten(int(semen_count))
    extra_text += _("（Mod强化+）")

    # 如果有交互对象，则根据交互对象的榨精能力等级来调整射精量
    if activity.target(0) > 0:
        target_data = identity.of(activity.target(0))
        squeeze_adjust = handle_ability.get_ability_adjust(
            abilities.ability(target_data.cid)[77]
        )
        # 根据榨精能力等级调整射精量
        semen_count *= squeeze_adjust
        if squeeze_adjust > 1:
            extra_text += _("（{0}榨精+）").format(target_data.name)

    # 每日首次射精量翻倍
    if action_info.get(0, "day_first_shoot_semen"):
        semen_count *= 2
        action_info.set(0, "day_first_shoot_semen", False)
        extra_text += _("（醒来第一发+）")

    # 如果使用了精液精力剂，则本次射精量翻倍
    if handle_premise.handle_self_semen_energy_agent(0):
        semen_count *= 2
        h_state.set(0, used_semen_energy_agent=False)
        extra_text += _("（精力剂+）")

    # 如果施加了香薰疗愈-射精状态，则射精量翻倍
    if handle_premise.handle_aromatherapy_flag_7(0):
        semen_count *= 2
        extra_text += f"（{game_config.config_aromatherapy_recipes[7].name}+）"

    # 如果当前的临时精液量大于等于最大精液量，则射精量翻倍
    if handle_premise.handle_pl_semen_tmp_ge_max(0):
        semen_count *= 2
        extra_text += _("（积攒精液+）")

    # 如果当前是浓厚精液的话，则射精量翻倍
    if handle_premise.handle_self_semen_thick_1(0):
        semen_count *= 2
        extra_text += _("（浓厚精液+）")

    # ===== 修改点4：移除了射精量不高于剩余精液值的判断 =====
    # 原代码：
    # semen_count = min(int(semen_count), character_data.semen_point + character_data.tem_extra_semen_point)
    # 现在不再进行该判断，直接进入后续
    semen_count = int(semen_count)

    # ===== 以下为原版逻辑，保持不变 =====

    # 组合射精文本
    semen_text += str(semen_count) + _("ml精液") + extra_text

    with h_state.editing(0) as hs:
        hs.orgasm_level[3] += 1  # 更新射精次数
        hs.just_shoot = 1  # 更新刚射精状态
        hs.endure_not_shot_count = 0  # 清零忍住不射次数
    with dirty.editing(0) as d:
        d.penis_dirty_dict["semen"] = True  # 更新阴茎精液污浊状态
    tallies.add(tallies.SEMEN, semen_count)  # 更新总精液量

    # 优先扣除临时额外精液值，不够的再扣除基础精液值
    meters = h_meters.of(0)
    extra = meters["extra_semen"]
    if extra > semen_count:
        h_meters.set(
            0,
            extra_semen=extra - semen_count,
            semen=max(0, meters["semen"]),
        )
    else:
        remaining = semen_count - extra
        h_meters.set(
            0,
            semen=max(0, meters["semen"] - remaining),
            extra_semen=0,
        )

    return semen_text, semen_count
