# -*- coding: UTF-8 -*-
"""
淫纹 mod 包（由 entry.py 以私有包名 _erark_mod_lewd_tattoo 加载，不放进 sys.path）

模块分工（外部只调用 install）：
- effects.py  效果定义表（唯一来源）+ 纯函数数学，不 import 任何 Script 模块
- store.py    唯一读写 character.mod_data 的模块（tests/lint_mod_data.py 强制）
- hooks.py    把本体 Script/Core/mod_hook.py 的五个钩子点接到 effects + store 上
- instruct.py 指令与前提注册
- ui.py       效果选择面板 + 结果提示 + 信息页绘制对象
本文件顶层不 import 任何 Script 模块：纯数学测试可以只加载包与 effects。
"""

MOD_ID = "lewd_tattoo"
""" mod_id，也是 mod_data 里的键 """

_installed = False
""" 是否已安装（防止重复注册） """


def install() -> None:
    """
    安装 mod：注册钩子、前提、指令。重复调用什么都不做
    Keyword arguments:
    无
    Return arguments:
    None
    """
    global _installed
    if _installed:
        return
    from . import hooks, instruct

    hooks.register_all()
    instruct.register_all()
    _installed = True
