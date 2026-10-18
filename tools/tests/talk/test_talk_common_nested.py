# -*- coding: UTF-8 -*-
"""
通用占位符嵌套替换的回归测试
==========================
通用口上的文本里会嵌套别的通用占位符（例如 m_orgasm_* 插入 {mouth}，{mouth} 再插入 {mouth_s}）。
talk_common_judge 不能依赖 config_talk_common_cid_list_by_type 的加载顺序：里层的 key 排在外层前面时，
外层插入的里层占位符也必须被替换，否则 code_text_to_draw_text 的 str.format 会抛 KeyError。

在仓库根目录运行：python tools/tests/talk/test_talk_common_nested.py
退出码：0 全部断言通过；1 有断言失败；2 未捕获异常。
"""
import random
import re
import sys
from unittest import mock

sys.path.insert(0, "tools/tests")
from headless_boot import boot, check, finish, mute_ui, new_chara  # noqa: E402

cache = boot()
mute_ui()

from Script.Config import game_config  # noqa: E402
from Script.Design import handle_premise, talk  # noqa: E402

new_chara(0, "博士")


def always_pass(premise_set, character_id, calculated_premise_dict, **kwargs):
    """
    让每条候选文本都通过前提，只测替换逻辑本身
    参数：premise_set (set) 前提集合；character_id (int) 角色id；calculated_premise_dict (dict) 已算过的前提
    返回：tuple[int, dict] 权重 1 与原样的已算前提
    """
    return 1, calculated_premise_dict


def left_keys(text: str) -> list:
    """
    列出文本里仍未替换的通用占位符
    参数：text (str) 替换后的文本
    返回：list[str] 仍以 {key} 形式留在文本里的通用占位符 key
    """
    return [key for key in game_config.config_talk_common_cid_list_by_type if "{" + key + "}" in text]


# ==== 1. 构造的三层嵌套：outer 插入 {mid}，mid 插入 {inner}，加载顺序是最坏的 inner → mid → outer ====
fake_data = {
    "t_outer_1": mock.Mock(context="外[{mid}]", type_id="outer"),
    "t_mid_1": mock.Mock(context="中<{inner}>", type_id="mid"),
    "t_inner_1": mock.Mock(context="内", type_id="inner"),
}
fake_order = {"inner": ["t_inner_1"], "mid": ["t_mid_1"], "outer": ["t_outer_1"]}
with mock.patch.object(game_config, "config_talk_common_cid_list_by_type", fake_order), \
        mock.patch.object(game_config, "config_talk_common_data", fake_data), \
        mock.patch.object(game_config, "config_talk_common_premise_data", {cid: set() for cid in fake_data}), \
        mock.patch.object(game_config, "config_talk_common_cid_list_by_part", {}), \
        mock.patch.object(handle_premise, "get_weight_from_premise_dict", always_pass):
    result = talk.talk_common_judge("{outer}", 0)
check("里层排在外层前面时，三层嵌套全部替换", result == "外[中<内>]", f"got={result!r}")

# ==== 2. 真实口上数据：把加载顺序整个倒过来，各类高潮文本（*_orgasm_*）里嵌套的 {mouth}/{throat} 等也都要替换 ====
# 这一段依赖现有数据的嵌套方式；不依赖数据的主检查是第 1 段
reversed_order = dict(reversed(list(game_config.config_talk_common_cid_list_by_type.items())))
with mock.patch.object(game_config, "config_talk_common_cid_list_by_type", reversed_order), \
        mock.patch.object(handle_premise, "get_weight_from_premise_dict", always_pass):
    orgasm_keys = [key for key in reversed_order if re.match(r"^[a-z]+_orgasm_", key)]
    check("通用口上数据里有 m_orgasm_* 四档高潮", {"m_orgasm_small", "m_orgasm_normal", "m_orgasm_strong", "m_orgasm_super"} <= set(orgasm_keys), f"orgasm_keys={orgasm_keys}")
    for key in orgasm_keys:
        left = set()
        for seed in range(10):
            random.seed(seed)
            left |= set(left_keys(talk.talk_common_judge("{" + key + "}", 0)))
        check(f"倒序加载时 {{{key}}} 不留下通用占位符", not left, f"left={sorted(left)}")

# ==== 3. 原本的加载顺序照常工作：各类高潮文本替换后不留下占位符、渲染不抛异常 ====
left = set()
errors = {}
with mock.patch.object(handle_premise, "get_weight_from_premise_dict", always_pass):
    for key in orgasm_keys:
        for seed in range(10):
            random.seed(seed)
            left |= set(left_keys(talk.talk_common_judge("{" + key + "}", 0)))
        for seed in range(5):
            random.seed(seed)
            try:
                talk.code_text_to_draw_text("{" + key + "}", 0, True)
            except Exception as exc:  # noqa: BLE001
                errors.setdefault(f"{type(exc).__name__}: {exc}", set()).add(key)
check(f"原顺序下 {len(orgasm_keys)} 种高潮文本不留下通用占位符", not left, f"left={sorted(left)}")
check(f"原顺序下渲染 {len(orgasm_keys)} 种高潮文本都不抛异常", not errors, f"errors={ {err: len(keys) for err, keys in sorted(errors.items())} }")

# ==== 4. 渲染：倒序加载时，各类高潮的纸娃娃地文经 code_text_to_draw_text 渲染不抛异常（修复前在 str.format 抛 KeyError） ====
errors = {}
with mock.patch.object(game_config, "config_talk_common_cid_list_by_type", reversed_order), \
        mock.patch.object(handle_premise, "get_weight_from_premise_dict", always_pass):
    for key in orgasm_keys:
        for seed in range(5):
            random.seed(seed)
            try:
                talk.code_text_to_draw_text("{" + key + "}", 0, True)
            except Exception as exc:  # noqa: BLE001
                errors.setdefault(f"{type(exc).__name__}: {exc}", set()).add(key)
check(f"倒序加载时渲染 {len(orgasm_keys)} 种高潮文本都不抛异常", not errors, f"errors={ {err: len(keys) for err, keys in sorted(errors.items())} }")

finish()
