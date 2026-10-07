# -*- coding: UTF-8 -*-
"""
本 mod 的全部运行状态：轮次边界 + 一个"本轮状态"对象

一轮 = 一次最外层 character_behavior.init_character_behavior()。该函数会重入（群交里太累结束 H 等路径），
所以用嵌套深度判断归属：只有深度 1 的那次拥有这一轮，内层调用产生的记录与缓冲自然并入外层。
状态只在内存里，不进 Character / cache，不进存档；每轮开头整体换一个新的 TurnState。
其他模块一律通过 state.turn 访问，不要 from state import turn（开新一轮时会换对象）。
"""
from typing import Dict, List, Optional, Set, Tuple


class TurnState:
    """
    一轮群交结算的全部状态
    Keyword arguments:
    player_behavior_id -- 本轮开头玩家自选的行为id，用来区分玩家的真实指令与模板派发
    orgasm_record -- {角色id: {部位: 最高档位序号}}
    edge_record -- {角色id: {部位: 寸止次数}}
    break_reason -- {角色id: "tired" | "release" | "fail"}，摘要页的断因标记
    edge_break_live -- 寸止断了、且绝顶链要实时显示的角色id；断因与是否实时显示分开记：全体结束指令触发的批量释放只记断因
    edge_near_limit -- 寸止成功但余量 <=2 的角色id，其寸止标题/口上实时显示
    replay_queue -- 摘要页之后按顺序回放的保留信息 [(绘制类, text, style, width, tooltip)]，只存值不存绘制对象
    player_real_active -- 是否正在结算玩家亲自对一个目标下的真实指令
    player_real_seen -- 本次 handle_settle_behavior 期间是否出现过玩家真实指令（决定属性变化面板交不交给本体画）
    template_dispatch_active -- 是否正在结算群交模板派发
    second_effect_character -- 正处在 check_second_effect 窗口内的角色id，没有时为 None
    """

    def __init__(self, player_behavior_id: str = ""):
        self.player_behavior_id: str = player_behavior_id
        self.orgasm_record: Dict[int, Dict[str, int]] = {}
        self.edge_record: Dict[int, Dict[str, int]] = {}
        self.break_reason: Dict[int, str] = {}
        self.edge_break_live: Set[int] = set()
        self.edge_near_limit: Set[int] = set()
        self.replay_queue: List[Tuple[type, str, str, int, str]] = []
        self.player_real_active: bool = False
        self.player_real_seen: bool = False
        self.template_dispatch_active: bool = False
        self.second_effect_character: Optional[int] = None


depth = 0
""" init_character_behavior 的嵌套深度 """
turn_active = False
""" 当前是否处在本 mod 接管的一轮内 """
turn = TurnState()
""" 当前一轮的状态 """


def begin_turn(player_behavior_id: str) -> None:
    """
    开始接管一轮：换一个新的本轮状态
    Keyword arguments:
    player_behavior_id -- 玩家此刻的行为id
    Return arguments:
    None
    """
    global turn, turn_active
    turn = TurnState(player_behavior_id)
    turn_active = True


def end_turn() -> None:
    """
    结束一轮（最外层调用退出时）；本轮状态留着不清，下一轮开头整体替换
    Keyword arguments:
    无
    Return arguments:
    None
    """
    global turn_active
    turn_active = False
