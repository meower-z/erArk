# -*- coding: UTF-8 -*-
"""
群交摘要 mod 包（由 entry.py 以私有包名 _erark_mod_group_sex_summary 加载，不放进 sys.path）

模块分工：
- records.py   本轮绝顶/寸止记录的纯函数（合并、断因、寸止余量、标记、摘要文本），不 import 任何 Script 模块
- state.py     运行状态：轮次深度 + 本轮状态对象 TurnState
- policy.py    显示与跳过的判据（口上直显/缓冲/吞掉、模板派发、玩家真实指令、指令族）
- capture.py   三个绘制类的常驻薄包装：捕获窗口、实时绘制、回放
- page.py      摘要页：行数据 + 绘制
- wrappers.py  mod_info.json 登记的 10 个替换函数
本文件顶层不 import 任何 Script 模块：纯函数测试可以只加载包与 records。
"""

_installed = False
""" 是否已安装（防止重复安装） """


def install() -> None:
    """
    安装 mod：预加载本体依赖链，给三个绘制类套上捕获包装。重复调用什么都不做
    函数替换由 mod_manager 按 mod_info.json 完成，entry.py 只负责把替换函数按登记的名字暴露出来
    Keyword arguments:
    无
    Return arguments:
    None
    """
    global _installed
    if _installed:
        return
    # mod 在本体大部分模块导入之前加载；直接按替换目标挨个导入会撞上
    # settle_behavior -> handle_instruct -> update -> character_behavior -> Script.Settle -> item_effect 的循环导入。
    # 先以 handle_npc_ai 为根把整条依赖链按正确顺序导入一遍，之后 mod_manager 导入各目标模块时都命中缓存
    from Script.Design import handle_npc_ai  # noqa: F401
    from Script.UI.Moudle import draw

    from . import capture

    capture.install_draw_wrappers((draw.NormalDraw, draw.WaitDraw, draw.LineFeedWaitDraw))
    _installed = True
