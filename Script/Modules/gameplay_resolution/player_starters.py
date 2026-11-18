"""
gameplay_resolution 的玩家指令选出的种类开始函数
==========================================
各种类用 starts.starter(kind) 登记；本文件在 LOAD_ORDER 里。
种类 Instruct 是玩家指令（handle_instruct.choose_instruct）选出的行动：开始时在 begin 之后、结算之前跑
handle_instruct.start_instruct（交互对象等待、群交模板、指令自己的开始代码）。
"""

from Script.Modules.gameplay_resolution import intent, starts

KIND = "Instruct"
""" 玩家指令的行动种类 """


@starts.starter(KIND)
def instruct(who: int, chosen: intent.Intent) -> None:
    """
    种类 Instruct 的开始代码
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
    from Script.System.Instruct_System import handle_instruct

    handle_instruct.start_instruct(who, chosen)
