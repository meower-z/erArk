# -*- coding: UTF-8 -*-
"""Mod加载器依赖测试。"""

import json
import sys
import tempfile
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Script.Core import mod_manager


def reset_manager(mod_root: Path):
    """参数：mod_root(Path)为临时mod根目录；返回：ModManager；用途：重置单例并指向测试目录。"""
    manager = mod_manager.ModManager()
    manager.mod_folder = str(mod_root)
    manager.mods.clear()
    manager.enabled_mods = []
    manager.load_order = []
    mod_manager._original_functions.clear()
    mod_manager._mod_functions.clear()
    mod_manager._mod_assets.clear()
    return manager


def write_mod(mod_root: Path, mod_id: str, dependencies=None, script_body=None, folder_name=None, functions=None, assets=None):
    """参数：mod_root(Path)为mod根目录，mod_id(str)为mod ID，其余参数为清单覆盖项；返回：Path为mod目录；用途：创建最小测试mod。"""
    dependencies = dependencies or []
    mod_path = mod_root / (folder_name or mod_id)
    script_path = mod_path / "scripts"
    script_path.mkdir(parents=True)
    script_file = script_path / "main.py"
    script_file.write_text(script_body or "", encoding="utf-8")
    mod_info = {
        "mod_id": mod_id,
        "name": mod_id,
        "version": "1.0.0",
        "dependencies": dependencies,
        "incompatible": [],
        "load_priority": 100,
        "scripts": [{"file": "scripts/main.py", "functions": functions or []}],
    }
    if assets:
        mod_info["assets"] = assets
    (mod_path / "mod_info.json").write_text(json.dumps(mod_info, ensure_ascii=False, indent=2), encoding="utf-8")
    return mod_path


def write_config(mod_root: Path, enabled_mods, load_order):
    """参数：mod_root(Path)为mod根目录，enabled_mods(list)为启用列表，load_order(list)为加载顺序；返回：None；用途：写入测试mod配置。"""
    config = {"enabled_mods": enabled_mods, "load_order": load_order}
    (mod_root / "mod_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def install_order_probe():
    """参数：无；返回：ModuleType为记录模块；用途：记录测试mod脚本的实际加载顺序。"""
    probe = ModuleType("mod_order_probe")
    probe.events = []
    sys.modules["mod_order_probe"] = probe
    return probe


def enable_only_with_dependencies(manager, mod_id: str):
    """参数：manager(ModManager)为加载器，mod_id(str)为目标mod；返回：list[str]为目标mod及依赖；用途：提供单mod加依赖的烟雾测试启用辅助。"""
    result = []

    def visit(now_mod_id: str):
        if now_mod_id in result:
            return
        for dependency_id in manager.mods[now_mod_id].dependencies:
            visit(dependency_id)
        result.append(now_mod_id)

    visit(mod_id)
    manager.enabled_mods = result.copy()
    manager.load_order = result.copy()
    for now_mod_id, mod_info in manager.mods.items():
        mod_info.enabled = now_mod_id in result
    return result


def test_missing_dependency_reports_error_and_skips_dependent():
    """参数：无；返回：None；用途：验证缺失依赖会产生清晰诊断且不运行依赖方脚本。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        mod_root = Path(temp_dir)
        probe = install_order_probe()
        write_mod(mod_root, "dependent", dependencies=["base"], script_body='import mod_order_probe\nmod_order_probe.events.append("dependent")\n')
        write_config(mod_root, ["dependent"], ["dependent"])

        manager = reset_manager(mod_root)
        manager.scan_mods()
        errors = manager.load_all_enabled_mods()

        assert "dependent" in errors
        assert "缺少依赖mod: base" in errors["dependent"]
        assert probe.events == []


def test_enabled_missing_mod_reports_error_without_crashing():
    """参数：无；返回：None；用途：验证配置启用但目录缺失的mod会返回诊断且不阻断启动流程。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        mod_root = Path(temp_dir)
        write_config(mod_root, ["ghost"], ["ghost"])

        manager = reset_manager(mod_root)
        manager.scan_mods()
        errors = manager.load_all_enabled_mods()

        assert errors == {"ghost": "已启用mod未找到: ghost"}


def test_duplicate_mod_id_reports_error_and_keeps_first_scan_result():
    """参数：无；返回：None；用途：验证重复mod_id保留稳定扫描的首个目录并返回诊断。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        mod_root = Path(temp_dir)
        probe = install_order_probe()
        first_path = write_mod(mod_root, "dup", folder_name="01_dup", script_body='import mod_order_probe\nmod_order_probe.events.append("first")\n')
        write_mod(mod_root, "dup", folder_name="02_dup", script_body='import mod_order_probe\nmod_order_probe.events.append("second")\n')
        write_config(mod_root, ["dup"], ["dup"])

        manager = reset_manager(mod_root)
        manager.scan_mods()
        errors = manager.load_all_enabled_mods()

        assert manager.mods["dup"].mod_path == str(first_path)
        assert "dup" in errors
        assert "重复mod_id" in errors["dup"]
        assert probe.events == []


def test_dependent_skips_when_dependency_has_duplicate_mod_id_error():
    """参数：无；返回：None；用途：验证依赖mod因重复ID诊断跳过时依赖方也不会加载。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        mod_root = Path(temp_dir)
        probe = install_order_probe()
        write_mod(mod_root, "base", folder_name="01_base", script_body='import mod_order_probe\nmod_order_probe.events.append("base-first")\n')
        write_mod(mod_root, "base", folder_name="02_base", script_body='import mod_order_probe\nmod_order_probe.events.append("base-second")\n')
        write_mod(mod_root, "dependent", dependencies=["base"], script_body='import mod_order_probe\nmod_order_probe.events.append("dependent")\n')
        write_config(mod_root, ["dependent", "base"], ["dependent", "base"])

        manager = reset_manager(mod_root)
        manager.scan_mods()
        errors = manager.load_all_enabled_mods()

        assert "base" in errors
        assert "重复mod_id" in errors["base"]
        assert "dependent" in errors
        assert "依赖mod尚未成功加载: base" in errors["dependent"]
        assert probe.events == []


def test_dependency_loads_before_dependent_even_when_configured_after():
    """参数：无；返回：None；用途：验证依赖会早于依赖方加载，即使配置顺序相反。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        mod_root = Path(temp_dir)
        probe = install_order_probe()
        write_mod(mod_root, "base", script_body='import mod_order_probe\nmod_order_probe.events.append("base")\n')
        write_mod(mod_root, "dependent", dependencies=["base"], script_body='import mod_order_probe\nmod_order_probe.events.append("dependent")\n')
        write_config(mod_root, ["dependent", "base"], ["dependent", "base"])

        manager = reset_manager(mod_root)
        manager.scan_mods()
        errors = manager.load_all_enabled_mods()

        assert errors == {}
        assert probe.events == ["base", "dependent"]


def test_independent_mods_keep_configured_order():
    """参数：无；返回：None；用途：验证无依赖关系的mod不会被依赖排序改变相对顺序。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        mod_root = Path(temp_dir)
        probe = install_order_probe()
        write_mod(mod_root, "alpha", script_body='import mod_order_probe\nmod_order_probe.events.append("alpha")\n')
        write_mod(mod_root, "beta", script_body='import mod_order_probe\nmod_order_probe.events.append("beta")\n')
        write_config(mod_root, ["beta", "alpha"], ["beta", "alpha"])

        manager = reset_manager(mod_root)
        manager.scan_mods()
        errors = manager.load_all_enabled_mods()

        assert errors == {}
        assert probe.events == ["beta", "alpha"]


def test_dependency_sort_preserves_unrelated_order():
    """参数：无；返回：None；用途：验证依赖排序不会把依赖mod提前到无关mod之前。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        mod_root = Path(temp_dir)
        probe = install_order_probe()
        write_mod(mod_root, "base", script_body='import mod_order_probe\nmod_order_probe.events.append("base")\n')
        write_mod(mod_root, "unrelated", script_body='import mod_order_probe\nmod_order_probe.events.append("unrelated")\n')
        write_mod(mod_root, "dependent", dependencies=["base"], script_body='import mod_order_probe\nmod_order_probe.events.append("dependent")\n')
        write_config(mod_root, ["dependent", "unrelated", "base"], ["dependent", "unrelated", "base"])

        manager = reset_manager(mod_root)
        manager.scan_mods()
        errors = manager.load_all_enabled_mods()

        assert errors == {}
        assert probe.events == ["unrelated", "base", "dependent"]


def test_dependent_skips_when_dependency_load_fails():
    """参数：无；返回：None；用途：验证依赖加载失败时依赖方不会以部分行为运行。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        mod_root = Path(temp_dir)
        probe = install_order_probe()
        write_mod(mod_root, "base", script_body='raise RuntimeError("base failed")\n')
        write_mod(mod_root, "dependent", dependencies=["base"], script_body='import mod_order_probe\nmod_order_probe.events.append("dependent")\n')
        write_config(mod_root, ["dependent", "base"], ["dependent", "base"])

        manager = reset_manager(mod_root)
        manager.scan_mods()
        errors = manager.load_all_enabled_mods()

        assert "base" in errors
        assert "dependent" in errors
        assert "依赖mod尚未成功加载: base" in errors["dependent"]
        assert probe.events == []


def test_failed_mod_rolls_back_declared_global_mutations():
    """参数：无；返回：None；用途：验证mod加载失败时回滚已声明的函数替换、新函数注册和素材别名。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        mod_root = Path(temp_dir)
        target_module = ModuleType("mod_manager_rollback_target")

        def original_func():
            """参数：无；返回：str；用途：作为被替换函数的原始实现。"""
            return "original"

        target_module.old_func = original_func
        sys.modules["mod_manager_rollback_target"] = target_module
        mod_path = write_mod(
            mod_root,
            "rollback",
            script_body='def patched_func():\n    return "patched"\n\ndef new_func():\n    return "new"\n',
            functions=[
                {"name": "patched_func", "type": "replace", "target_module": "mod_manager_rollback_target", "target_function": "old_func"},
                {"name": "new_func", "type": "new", "register_to": "mod_manager_rollback_target"},
                {"name": "missing_func", "type": "new"},
            ],
            assets={"image": [{"file": "asset.txt", "alias": "rollback_asset"}]},
        )
        (mod_path / "asset.txt").write_text("asset", encoding="utf-8")
        write_config(mod_root, ["rollback"], ["rollback"])

        manager = reset_manager(mod_root)
        try:
            manager.scan_mods()
            errors = manager.load_all_enabled_mods()

            assert "rollback" in errors
            assert target_module.old_func is original_func
            assert not hasattr(target_module, "new_func")
            assert mod_manager._mod_functions == {}
            assert mod_manager._mod_assets == {}
            assert mod_manager._original_functions == {}
        finally:
            sys.modules.pop("mod_manager_rollback_target", None)


def test_smoke_helper_enables_only_target_and_declared_dependencies():
    """参数：无；返回：None；用途：验证烟雾测试辅助只启用目标mod和声明依赖，不加载无关mod。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        mod_root = Path(temp_dir)
        probe = install_order_probe()
        write_mod(mod_root, "base", script_body='import mod_order_probe\nmod_order_probe.events.append("base")\n')
        write_mod(mod_root, "target", dependencies=["base"], script_body='import mod_order_probe\nmod_order_probe.events.append("target")\n')
        write_mod(mod_root, "unrelated", script_body='import mod_order_probe\nmod_order_probe.events.append("unrelated")\n')
        write_config(mod_root, ["base", "target", "unrelated"], ["base", "target", "unrelated"])

        manager = reset_manager(mod_root)
        manager.scan_mods()
        enabled_mods = enable_only_with_dependencies(manager, "target")
        errors = manager.load_all_enabled_mods()

        assert enabled_mods == ["base", "target"]
        assert errors == {}
        assert probe.events == ["base", "target"]


def main():
    """参数：无；返回：None；用途：直接运行全部mod加载器依赖测试。"""
    test_missing_dependency_reports_error_and_skips_dependent()
    test_enabled_missing_mod_reports_error_without_crashing()
    test_duplicate_mod_id_reports_error_and_keeps_first_scan_result()
    test_dependent_skips_when_dependency_has_duplicate_mod_id_error()
    test_dependency_loads_before_dependent_even_when_configured_after()
    test_independent_mods_keep_configured_order()
    test_dependency_sort_preserves_unrelated_order()
    test_dependent_skips_when_dependency_load_fails()
    test_failed_mod_rolls_back_declared_global_mutations()
    test_smoke_helper_enables_only_target_and_declared_dependencies()
    print("mod_manager dependency tests passed", flush=True)


if __name__ == "__main__":
    main()
