# -*- coding: UTF-8 -*-
"""
群交摘要 mod 的唯一 exec 入口

mod_manager 用 exec 执行本文件，命名空间里的 __file__ 是 mod 目录（不是本文件路径）。
exec 出来的代码不能被 import，所以实现放在同目录的普通包里：本文件按文件路径把 mod 目录加载成
私有包 _erark_mod_group_sex_summary（不改 sys.path，包名不会与 Script 或其他 mod 撞），调用 install()，
再把 10 个替换函数按 mod_info.json 登记的名字放进本命名空间，供 mod_manager 读取。
"""
import importlib
import importlib.util
import os
import sys

PACKAGE_NAME = "_erark_mod_group_sex_summary"
""" 私有包名 """


def _entry() -> None:
    """
    加载私有包并安装 mod；包已加载过（例如测试先加载）则直接复用
    Keyword arguments:
    无（读取 exec 命名空间里的 __file__，它是 mod 目录）
    Return arguments:
    None
    """
    package = sys.modules.get(PACKAGE_NAME)
    if package is None:
        mod_dir = os.path.abspath(__file__)
        spec = importlib.util.spec_from_file_location(PACKAGE_NAME, os.path.join(mod_dir, "__init__.py"), submodule_search_locations=[mod_dir])
        package = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE_NAME] = package
        try:
            spec.loader.exec_module(package)
        except BaseException:
            del sys.modules[PACKAGE_NAME]
            raise
    package.install()


_entry()
_wrappers = importlib.import_module(PACKAGE_NAME + ".wrappers")

modded_init_character_behavior = _wrappers.modded_init_character_behavior
modded_handle_talk_draw = _wrappers.modded_handle_talk_draw
modded_handle_settle_behavior = _wrappers.modded_handle_settle_behavior
modded_handle_instruct_data = _wrappers.modded_handle_instruct_data
modded_orgasm_settle_in_second_behavior = _wrappers.modded_orgasm_settle_in_second_behavior
modded_draw_achievement_notice = _wrappers.modded_draw_achievement_notice
modded_mark_effect = _wrappers.modded_mark_effect
modded_gain_talent = _wrappers.modded_gain_talent
modded_judge_orgasm_edge_success = _wrappers.modded_judge_orgasm_edge_success
modded_check_second_effect = _wrappers.modded_check_second_effect
