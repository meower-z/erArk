# -*- coding: UTF-8 -*-
"""
local_orgasm_chain_gate_fix 单元自检。

直接 exec 真实 mod 脚本，注入假的 call_original 与桩 cache_control，
验证四个 wrapper 的门禁/置位/重置逻辑，无需启动完整游戏。
sp_flag 用不预声明标记字段的对象，同时覆盖"缺省视为 False"与"setattr 创建字段"。
"""
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

FLAG = "multi_orgasm_this_player_action"
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "local_orgasm_chain_gate_fix.py"


def _make_char(cid):
    return SimpleNamespace(cid=cid, sp_flag=SimpleNamespace())  # sp_flag 初始无 FLAG 字段


def _load(cache):
    """exec 真实 mod 脚本，注入 call_original 记录器与桩 cache_control，返回 (命名空间, 调用记录)。"""
    calls = []

    def call_original(module, func, *args, **kwargs):
        calls.append((func, args))
        return ("ORIG", func, args)

    # 桩 Script.Core.cache_control，供脚本内 _cache() 的延迟导入使用
    core = ModuleType("Script.Core.cache_control")
    core.cache = cache
    sys.modules["Script.Core.cache_control"] = core
    sys.modules.setdefault("Script.Core", ModuleType("Script.Core"))
    sys.modules.setdefault("Script", ModuleType("Script"))

    ns = {"call_original": call_original}
    exec(compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec"), ns)
    return ns, calls


def _new_cache():
    chars = {0: _make_char(0), 1: _make_char(1), 2: _make_char(2)}
    return SimpleNamespace(
        character_data=chars,
        npc_id_got={1, 2},
        over_behavior_character=set(),
        game_update_flow_running=0,
    )


def test_reset_only_at_outermost_depth():
    cache = _new_cache()
    ns, calls = _load(cache)
    setattr(cache.character_data[1].sp_flag, FLAG, True)
    # 最外层（深度 0）：重置全体 NPC，并调用原函数
    ns["patched_game_update_flow"](1)
    assert getattr(cache.character_data[1].sp_flag, FLAG) is False, "最外层点击未重置标记"
    assert ("game_update_flow", (1,)) in calls, "未调用原 game_update_flow"
    # 嵌套（深度 >0）：复用标记，不重置
    cache.game_update_flow_running = 1
    setattr(cache.character_data[1].sp_flag, FLAG, True)
    ns["patched_game_update_flow"](1)
    assert getattr(cache.character_data[1].sp_flag, FLAG) is True, "嵌套更新不应重置标记"


def test_plural_orgasm_sets_flag_for_npc_only():
    cache = _new_cache()
    ns, calls = _load(cache)
    f = ns["patched_character_get_second_behavior"]
    # NPC 多重绝顶 → 置位；原函数被调用且参数透传
    f(1, "plural_orgasm_2")
    assert getattr(cache.character_data[1].sp_flag, FLAG, False) is True, "NPC 多重绝顶未置位"
    assert ("character_get_second_behavior", (1, "plural_orgasm_2", False)) in calls, "未透传原调用"
    # 玩家（id 0）多重绝顶 → 不置位
    f(0, "plural_orgasm_3")
    assert getattr(cache.character_data[0].sp_flag, FLAG, False) is False, "玩家不应被置位"
    # 单部位/其它二段行为 → 不置位
    f(2, "v_orgasm_small")
    assert getattr(cache.character_data[2].sp_flag, FLAG, False) is False, "非多重绝顶不应置位"


def test_find_target_gated():
    cache = _new_cache()
    ns, calls = _load(cache)
    setattr(cache.character_data[1].sp_flag, FLAG, True)
    ns["patched_find_character_target"](1, None)
    assert 1 in cache.over_behavior_character, "门禁 NPC 未加入完成集合"
    assert not any(c[0] == "find_character_target" for c in calls), "门禁 NPC 不应调用原函数"
    # 未门禁 NPC → 调用原函数
    ns["patched_find_character_target"](2, None)
    assert ("find_character_target", (2, None)) in calls, "未门禁 NPC 应调用原函数"


def test_group_sex_gated():
    cache = _new_cache()
    ns, calls = _load(cache)
    setattr(cache.character_data[1].sp_flag, FLAG, True)
    ns["patched_npc_ai_in_group_sex"](1)
    assert not any(c[0] == "npc_ai_in_group_sex" for c in calls), "门禁 NPC 不应进入群交生成入口"
    ns["patched_npc_ai_in_group_sex"](2)
    assert ("npc_ai_in_group_sex", (2,)) in calls, "未门禁 NPC 应调用原函数"


if __name__ == "__main__":
    test_reset_only_at_outermost_depth()
    test_plural_orgasm_sets_flag_for_npc_only()
    test_find_target_gated()
    test_group_sex_gated()
    print("local_orgasm_chain_gate_fix: all self-checks PASS")
