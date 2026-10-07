# -*- coding: UTF-8 -*-
"""
local_orgasm_chain_gate_fix 单元自检

直接 exec 真实 mod 脚本，注入假的 call_original 与桩 cache_control，
验证四个包装的门禁/记名/清空逻辑，并确认门禁名单不写进角色数据（不进存档）。无需启动完整游戏。
"""
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "local_orgasm_chain_gate_fix.py"


def _load(cache):
    """
    exec 真实 mod 脚本
    Keyword arguments:
    cache -- 桩缓存
    Return arguments:
    tuple -- (脚本命名空间dict, call_original 调用记录list)
    """
    calls = []

    def call_original(module, func, *args, **kwargs):
        """记录一次对本体原函数的调用"""
        calls.append((func, args))
        return ("ORIG", func, args)

    for parent in ("Script", "Script.Core"):
        sys.modules.setdefault(parent, ModuleType(parent))
    cache_control = ModuleType("Script.Core.cache_control")
    cache_control.cache = cache
    sys.modules["Script.Core.cache_control"] = cache_control
    sys.modules["Script.Core"].cache_control = cache_control

    namespace = {"call_original": call_original}
    exec(compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec"), namespace)
    return namespace, calls


def _new_cache():
    """
    构造最小桩缓存：玩家0与NPC 1、2
    Return arguments:
    SimpleNamespace -- 桩缓存
    """
    return SimpleNamespace(
        character_data={cid: SimpleNamespace(cid=cid, sp_flag=SimpleNamespace()) for cid in (0, 1, 2)},
        npc_id_got={1, 2},
        over_behavior_character=set(),
        game_update_flow_running=0,
    )


def test_plural_orgasm_gates_npc_only():
    """NPC 得到 plural_orgasm_* 才进门禁名单；玩家与其他二段行为不进；原函数参数原样透传；角色数据不被写入"""
    cache = _new_cache()
    namespace, calls = _load(cache)
    get_second_behavior = namespace["patched_character_get_second_behavior"]
    get_second_behavior(1, "plural_orgasm_2")
    get_second_behavior(0, "plural_orgasm_3")
    get_second_behavior(2, "v_orgasm_small")
    assert namespace["_gated_ids"] == {1}, f"门禁名单错误: {namespace['_gated_ids']}"
    assert ("character_get_second_behavior", (1, "plural_orgasm_2", False)) in calls, "未透传原调用"
    assert all(not vars(cache.character_data[cid].sp_flag) for cid in (0, 1, 2)), "不应写入角色数据"


def test_reset_only_at_outermost_depth():
    """最外层点击清空门禁名单并调用原函数；嵌套更新不清空"""
    cache = _new_cache()
    namespace, calls = _load(cache)
    namespace["_gated_ids"].add(1)
    cache.game_update_flow_running = 1
    namespace["patched_game_update_flow"](1)
    assert namespace["_gated_ids"] == {1}, "嵌套更新不应清空门禁名单"
    cache.game_update_flow_running = 0
    namespace["patched_game_update_flow"](1)
    assert not namespace["_gated_ids"], "最外层点击未清空门禁名单"
    assert calls.count(("game_update_flow", (1,))) == 2, "未调用原 game_update_flow"


def test_find_target_gated():
    """门禁中的 NPC 直接进结束集合、不调原函数；未门禁的照常调原函数"""
    cache = _new_cache()
    namespace, calls = _load(cache)
    namespace["_gated_ids"].add(1)
    namespace["patched_find_character_target"](1, None)
    namespace["patched_find_character_target"](2, None)
    assert cache.over_behavior_character == {1}, "门禁 NPC 未加入完成集合"
    assert [call for call in calls if call[0] == "find_character_target"] == [("find_character_target", (2, None))], f"调用记录错误: {calls}"


def test_group_sex_gated():
    """门禁中的 NPC 不进群交行为生成入口；未门禁的照常调原函数"""
    cache = _new_cache()
    namespace, calls = _load(cache)
    namespace["_gated_ids"].add(1)
    namespace["patched_npc_ai_in_group_sex"](1)
    namespace["patched_npc_ai_in_group_sex"](2)
    assert [call for call in calls if call[0] == "npc_ai_in_group_sex"] == [("npc_ai_in_group_sex", (2,))], f"调用记录错误: {calls}"


if __name__ == "__main__":
    test_plural_orgasm_gates_npc_only()
    test_reset_only_at_outermost_depth()
    test_find_target_gated()
    test_group_sex_gated()
    print("local_orgasm_chain_gate_fix: all self-checks PASS")
