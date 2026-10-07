# -*- coding: UTF-8 -*-
"""
easy_mode 单元自检

用真实的 Script/Core/mod_hook.py 加载 mod 脚本，验证：
1. 三个钩子都挂上，且数值改写符合预期
2. 重复执行脚本不会重复挂载
3. 本体三处调用点仍在（调用点被改名或删掉时本自检直接失败）
无需启动完整游戏。
"""
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "easy_mode.py"
CALL_SITES = {
    "Script/UI/Panel/hypnosis_panel.py": "mod_hook.hypnosis_random_factor(random.uniform(0.5, 1.5), target_character_id)",
    "Script/Settle/sleep_settle.py": "grow_value = mod_hook.sanity_point_growth(grow_value, today_cost)",
    "Script/UI/Panel/normal_panel.py": "room_price = mod_hook.hotel_room_price(room_price)",
}
""" 本体调用点所在文件 -> 必须出现的调用行 """


def _load():
    """
    加载真实钩子模块并 exec mod 脚本两次（模拟重复加载）
    Return arguments:
    ModuleType -- 钩子模块
    """
    sys.modules.setdefault("Script", ModuleType("Script"))
    sys.modules.setdefault("Script.Core", ModuleType("Script.Core"))
    spec = importlib.util.spec_from_file_location("Script.Core.mod_hook", REPO_ROOT / "Script" / "Core" / "mod_hook.py")
    mod_hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod_hook)
    sys.modules["Script.Core.mod_hook"] = mod_hook
    sys.modules["Script.Core"].mod_hook = mod_hook
    for _ in range(2):
        exec(compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec"), {})
    return mod_hook


def test_hooks_rewrite_values():
    """三个钩子的改写结果，且重复加载后结果不叠加"""
    mod_hook = _load()
    assert mod_hook.hypnosis_random_factor(0.5, 1) == 5.0
    assert mod_hook.hypnosis_random_factor(1.5, 1) == 10.0
    assert mod_hook.hypnosis_random_factor(1.0, 1) == 7.5
    assert mod_hook.sanity_point_growth(1, 80) == 80
    assert mod_hook.hotel_room_price([2, 10, 100]) == [1, 2, 3]


def test_call_sites_present():
    """本体三处调用点仍在"""
    for rel_path, line in CALL_SITES.items():
        source = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        assert line in source, f"本体调用点缺失: {rel_path}: {line}"


if __name__ == "__main__":
    test_hooks_rewrite_values()
    test_call_sites_present()
    print("easy_mode: all self-checks PASS")
