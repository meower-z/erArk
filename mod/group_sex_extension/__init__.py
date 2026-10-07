# -*- coding: UTF-8 -*-
"""
群交功能扩展 mod 包（由 entry.py 以私有包名 _erark_mod_group_sex_extension 加载，不放进 sys.path）

在群交模式的"技艺"类别里加三个批量指令：全员寸止、全员戴上玩具、全员催眠增强。
模块分工（外部只调用 install）：
- members.py  谁在本次群交里、谁已完全催眠
- actions.py  三个指令的效果与结果提示
- instruct.py 指令与前提注册
本文件顶层不 import 任何 Script 模块。
"""

MOD_ID = "group_sex_extension"
""" mod_id """

_installed = False
""" 是否已安装（防止重复注册） """


def install() -> None:
    """
    安装 mod：注册前提与三个指令。重复调用什么都不做
    Keyword arguments:
    无
    Return arguments:
    None
    """
    global _installed
    if _installed:
        return
    from . import instruct

    instruct.register_all()
    _installed = True
