# -*- coding: UTF-8 -*-
"""
本体 mod 钩子点（叶子模块，不 import 任何 Script 模块）

约定：
1. 每个钩子点是本模块里的一个模块级对象。本体用 `mod_hook.<钩子名>(值, *上下文)` 调用，
   mod 用 `mod_hook.<钩子名>.register(fn, owner="mod_id")` 挂载。名字写错立刻 AttributeError，没有字符串注册表。
2. 全部钩子都是"折叠"语义：被折叠的值是第一个位置参数，每个 fn 收到上一个 fn 的结果并返回新值。
   没装 mod 时 `__call__` 只做一次空列表判断，原样返回第一个参数。
3. 多个 mod 挂同一钩子：按注册顺序（即 mod 加载顺序）依次折叠。
4. fn 抛异常时异常直接传播，不摘钩子、不用旧值继续（否则 mod 已写入一半的结算会和本体状态不一致）。
5. stop_on_none=True 的钩子允许 fn 返回 None，表示"这次结算已被 mod 接管"，后续 fn 不再调用，本体紧接着跳过原写入。
6. 本模块里 `X = FoldHook(...)` 的定义行是 mod/lewd_tattoo/tests/lint_base_diff.py 认识的钩子名单的唯一来源（lint 用 AST 读本文件）。

为什么不用 mod_manager 的函数替换：替换只能改模块属性，`from X import f` 拿到的副本、
注册表 dict 里存的函数引用都替换不到；钩子对象靠对象身份共享，不受副本影响。
"""
import math
from typing import Any, Callable, List, Tuple


class FoldHook:
    """
    折叠式钩子点
    Keyword arguments:
    name -- 钩子名（与模块属性名一致，只用于报错信息）
    stop_on_none -- 是否允许 fn 返回 None 表示接管并短路
    """

    __slots__ = ("name", "stop_on_none", "_fns")

    def __init__(self, name: str, stop_on_none: bool = False):
        """
        初始化钩子点
        Keyword arguments:
        name -- 钩子名
        stop_on_none -- 是否允许返回 None 短路
        Return arguments:
        None
        """
        self.name = name
        """ 钩子名 """
        self.stop_on_none = stop_on_none
        """ 是否允许返回 None 短路 """
        self._fns: List[Tuple[str, Callable]] = []
        """ 已挂载的 (owner, fn)，按注册顺序 """

    def register(self, fn: Callable, owner: str) -> None:
        """
        挂载一个 mod 函数；同一 (owner, fn) 重复注册时忽略
        Keyword arguments:
        fn -- mod 函数，签名为 fn(值, *上下文) -> 新值
        owner -- 挂载者 mod_id，用于按 mod 卸载
        Return arguments:
        None
        """
        if (owner, fn) not in self._fns:
            self._fns.append((owner, fn))

    def unregister(self, owner: str) -> None:
        """
        摘掉某个 mod 在本钩子上的全部函数
        Keyword arguments:
        owner -- mod_id
        Return arguments:
        None
        """
        self._fns[:] = [item for item in self._fns if item[0] != owner]

    def has_fns(self) -> bool:
        """
        是否挂有任何函数（测试用）
        Keyword arguments:
        无
        Return arguments:
        bool -- 是否挂有函数
        """
        return bool(self._fns)

    def __call__(self, value: Any, *ctx: Any) -> Any:
        """
        本体调用入口：依次折叠全部已挂载函数
        Keyword arguments:
        value -- 被折叠的值（本体原本要用的值）
        ctx -- 只读上下文参数，原样传给每个 fn
        Return arguments:
        Any -- 折叠后的值；stop_on_none 钩子可能返回 None
        """
        fns = self._fns
        # 没装 mod：一次判断后原样返回（热路径的全部开销）
        if not fns:
            return value
        for _owner, fn in tuple(fns):
            value = fn(value, *ctx)
            if value is None and self.stop_on_none:
                return None
        return value


# ========== 钩子点定义（lint 的钩子名单唯一来源）==========

state_gain = FoldHook("state_gain", stop_on_none=True)
""" 状态增量写入前：值=增量(int)；上下文=(character_id, state_id, change_data, change_data_to_target_change)；
    返回新的增量，或 None 表示 mod 已自行结算（本体随即跳过原写入）。
    调用点 common_default.base_chara_state_common_settle，以及 default.py / item_effect.py 的 5 处状态直写 """

edge_judged = FoldHook("edge_judged")
""" 寸止判定绘制前：值=(是否成功: bool, 提示文本: str)；上下文=(character_id, over_count)；
    返回新的二元组。调用点 orgasm_settle.judge_orgasm_edge_success """

daily_desire_growth = FoldHook("daily_desire_growth")
""" 新一天 NPC 欲望值增长：值=本日增长量(int)；上下文=(character_id,)；返回新的增长量。调用点 past_day_settle """

character_info_draw_list = FoldHook("character_info_draw_list")
""" 角色信息"肉体情况"页 NPC 分支的绘制列表：值=draw_list(list)；上下文=(character_id, width)；
    返回新列表。调用点 see_character_info_panel.SeeCharacterThirdPanel.__init__ """

desire_written = FoldHook("desire_written")
""" 本体降低欲望值之后的通知：值=角色对象(game_type.Character)；无上下文；返回值被忽略（约定原样返回）。
    调用点 default.py / handle_npc_ai.py 的 6 处降欲望写入 """


hypnosis_random_factor = FoldHook("hypnosis_random_factor")
""" 催眠增长的随机系数：值=本体抽到的系数(float，0.5~1.5)；上下文=(target_character_id,)；返回新系数。
    调用点 hypnosis_panel.hypnosis_degree_calculation """

sanity_point_growth = FoldHook("sanity_point_growth")
""" 睡眠时玩家理智上限成长量：值=本体算出的成长量(int)；上下文=(today_cost,)；返回新的成长量。调用点 sleep_settle.sanity_point_grow """

hotel_room_price = FoldHook("hotel_room_price")
""" 预订酒店房间的价格表：值=[标间, 情趣主题房, 顶级套房] 的粉红凭证价格(list)；无上下文；返回新价格表。
    调用点 normal_panel.Order_Hotel_Room_Panel.order_room """

# ========== mod_data 形状约定（本体拥有这条约定，所以校验器也放在本体）==========


def validate_mod_data(obj: Any, path: str = "mod_data") -> List[str]:
    """
    校验一棵 mod_data 子树只由内建类型构成且 dict 键全为 str
    允许：None / bool / int / float(有限值) / str / list / dict[str, ...]，类型必须严格相等（不接受子类、Enum）
    不允许：tuple、set、任何自定义类、NaN/inf、非 str 键、循环引用
    （理由：存档是 pickle，自定义类会让卸载 mod 后的本体反序列化失败；tuple/set 不报错但不利于跨版本迁移，一并禁止）
    Keyword arguments:
    obj -- 待校验对象
    path -- 当前路径，用于报错文本
    Return arguments:
    List[str] -- 违规描述列表，空列表表示通过
    """
    errors: List[str] = []
    _validate_node(obj, path, set(), errors)
    return errors


def _validate_node(obj: Any, path: str, visiting: set, errors: List[str]) -> None:
    """
    validate_mod_data 的递归体
    Keyword arguments:
    obj -- 当前节点
    path -- 当前路径
    visiting -- 当前递归链上的容器 id，用于发现循环引用
    errors -- 违规描述收集列表（原地追加）
    Return arguments:
    None
    """
    obj_type = type(obj)
    # 标量
    if obj is None or obj_type is bool or obj_type is int or obj_type is str:
        return
    if obj_type is float:
        if not math.isfinite(obj):
            errors.append(f"{path}: 浮点数 {obj!r} 不允许")
        return
    # 容器
    if obj_type is list or obj_type is dict:
        if id(obj) in visiting:
            errors.append(f"{path}: 循环引用")
            return
        visiting.add(id(obj))
        if obj_type is list:
            for index, item in enumerate(obj):
                _validate_node(item, f"{path}[{index}]", visiting, errors)
        else:
            for key, item in obj.items():
                if type(key) is not str:
                    errors.append(f"{path}: 键 {key!r} 的类型 {type(key).__name__} 不允许，只许 str")
                    continue
                _validate_node(item, f"{path}[{key!r}]", visiting, errors)
        visiting.discard(id(obj))
        return
    errors.append(f"{path}: 类型 {obj_type.__name__} 不允许")
