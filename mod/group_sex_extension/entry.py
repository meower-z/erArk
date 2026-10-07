# -*- coding: UTF-8 -*-
"""
群交功能扩展 mod 的唯一 exec 入口

mod_manager 用 exec 执行本文件，命名空间里的 __file__ 是 mod 目录（不是本文件路径）。
exec 出来的代码不能被 import，所以实现放在同目录的普通包里：本文件按文件路径把 mod 目录加载成
私有包 _erark_mod_group_sex_extension（不改 sys.path，包名不会与 Script 或其他 mod 撞），然后调用 install()。
mod_info.json 的 functions 留空：本 mod 不用函数替换。
"""

import importlib.util
import os
import sys

PACKAGE_NAME = "_erark_mod_group_sex_extension"
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
