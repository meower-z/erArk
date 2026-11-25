"""
调试面板全局与玩家编辑服务（debug_world_service）
=================================================
提供调试面板全局变量与常用更改页的文本构造、时钟调整及状态修改。
本模块不导入 Script.UI 与 Script.Settle。
"""

import datetime
from collections.abc import Callable
from dataclasses import replace
from types import FunctionType, MappingProxyType
from typing import Any, Literal, cast

from Script.Config import game_config
from Script.Core import get_text, num
from Script.Design import basement, clothing, game_time, map_handle
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, chara_life
from Script.Modules.domains import entertainment, facility, flags, h_meters
from Script.Modules.domains import identity, needs, npc_template, recruit
from Script.Modules.domains import roster, status, warehouse
from Script.Modules.gameplay_resolution import actions

_: FunctionType = get_text._
""" 本地化翻译函数。 """

type GlobalKind = Literal["date", "roster", "value", "pair"]
""" 全局变量项的输入模式字面量类型。 """
type PlayerKind = Literal["stat", "value", "adv", "direct"]
""" 常用更改项的输入模式字面量类型。 """

GLOBAL_KINDS: MappingProxyType[int, GlobalKind] = MappingProxyType(
    {0: "date", 1: "roster", 3: "value", 4: "value", 5: "value"}
    | {6: "value", 7: "pair", 8: "pair", 9: "value"}
)
""" 全局变量可编辑项键到输入模式的只读映射。 """
PLAYER_KINDS: MappingProxyType[int, PlayerKind] = MappingProxyType(
    {key: "stat" for key in range(8)}
    | {key: "direct" for key in (8, 9, 10, 11, 12, 13, 14, 17)}
    | {15: "value", 16: "adv"}
)
""" 常用更改项键到输入模式的只读映射。 """
_PLAYER_STATS: tuple[Callable[[], str], ...] = (
    lambda: f"[000]:当前HP：{num.shown(needs.of(0)['hit'])}",
    lambda: f"[001]:最大HP：{needs.of(0)['hit_max']}",
    lambda: f"[002]:当前MP：{num.shown(needs.of(0)['mana'])}",
    lambda: f"[003]:最大MP：{needs.of(0)['mana_max']}",
    lambda: f"[004]:当前射精槽：{num.shown(h_meters.of(0)['eja'])}",
    lambda: (
        "[005]:疲劳值 6m=1点，16h=160点(max)："
        f"{num.shown(needs.of(0)['tired'])}"
    ),
    lambda: (
        "[006]:尿意值 1m=1点，4h=240点(max)："
        f"{num.shown(needs.of(0)['urine'])}"
    ),
    lambda: (
        "[007]:饥饿值 1m=1点，4h=240点(max)："
        f"{num.shown(needs.of(0)['hunger'])}"
    ),
)
""" 玩家常用基础数值的展示行构造回调元组。 """
_PLAYER_ACTIONS = (
    "[008]:全源石技艺全开，理智9999",
    "[009]:资源全99999",
    "[010]:设施全满级、全开放",
    "[011]:重置全角色特殊flag",
    "[012]:重置全角色服装",
    "[013]:重置全角色位置至宿舍",
    "[014]:重置文职部的招募数据",
    "[015]:交互对象全部位快感增加",
    "[016]:招募指定adv_id的干员",
    "[017]:重置全角色娱乐",
)
""" 常用更改页中快捷操作项的展示标签元组。 """
_STAT_FIELDS = (
    (0, needs.set, "hit"),
    (1, needs.set, "hit_max"),
    (2, needs.set, "mana"),
    (3, needs.set, "mana_max"),
    (4, h_meters.set, "eja"),
    (5, needs.set, "tired"),
    (6, needs.set, "urine"),
    (7, needs.set, "hunger"),
)
""" 玩家基础数值项键到领域写入函数及字段名的映射表。 """
_RESOURCES = MappingProxyType({3: 1, 4: 2, 5: 4})
""" 全局变量资源项键（3、4、5）到仓库物品编号的映射。 """


def set_clock(new_time: datetime.datetime) -> None:
    """
    通过单次 reset_state 将时钟与已走时刻设为新时间。
    仅在新日期更早时调低已结算日。在行动选择期间调用会结束该次选择。
    Keyword arguments:
    new_time -- datetime.datetime，目标游戏时间
    Return arguments:
    None -- 无返回值
    """
    game = core.state()
    clock = game_time.minutes(new_time)
    settled_day = cast(int, game.data[actions.SETTLED_DAY])
    data = {
        **game.data,
        actions.TICKED: clock,
        actions.SETTLED_DAY: min(settled_day, game_time.day(clock)),
    }
    core.reset_state(
        replace(game, clock=clock, data=MappingProxyType(data)),
        {"cause": "clock"},
    )


def parse_index(text: str) -> Any:
    """
    解析索引输入，含逗号时返回整数列表，否则返回单个整数。
    Keyword arguments:
    text -- str，用户输入的索引字符串
    Return arguments:
    Any -- list[int] 或 int 形式的解析结果
    """
    if "," in text:
        return list(map(int, text.split(",")))
    return int(text)


def global_lines() -> list[str]:
    """
    构造全局变量页十条展示文本。
    Keyword arguments:
    无
    Return arguments:
    list[str] -- 按 000 至 009 顺序排列的全局变量展示行
    """
    return [
        f"[000]:游戏时间：{game_time.now()}",
        f"[001]:已拥有的干员id列表：{roster.active()}",
        "[002]:全干员id列表（太长了无法显示）",
        f"[003]:龙门币：{warehouse.amount(1)}",
        f"[004]:合成玉：{warehouse.amount(2)}",
        f"[005]:粉红凭证：{warehouse.amount(4)}",
        "[006]:基地当前所有待开放设施的开放情况",
        "[007]:一周内的派对计划，周一0~周日6:娱乐id："
        f"{entertainment.party_days()}",
        f"[008]:当前招募进度：{recruit.lines()}",
        f"[009]:已招募待确认的干员id：{recruit.pending()}",
    ]


def _roster_text() -> str:
    """构造已拥有干员与全干员编号姓名对照文本。"""
    text = "[001]:已拥有的干员id列表：\n"
    for chara_id in roster.active():
        text += f"{chara_id}:{identity.of(chara_id).name} "
    text += "\n\n全干员id列表：\n"
    for chara_id in npc_template.ids():
        if identity.exists(chara_id):
            text += f"{chara_id}:{identity.of(chara_id).name} "
    return text


def global_info(key: int) -> str:
    """
    返回指定全局变量项进入编辑前显示的说明文本。
    Keyword arguments:
    key -- int，全局变量项键（0 至 9）
    Return arguments:
    str -- 该项的当前状态与格式提示文本
    """
    if key == 0:
        return f"[000]:游戏时间：{game_time.now()}      年月日分别为0,1,2"
    if key == 1:
        return _roster_text()
    if key == 6:
        return f"[006]:基地当前所有待开放设施的开放情况{facility.opens()}"
    return global_lines()[key]


def edit_global(
    key: int, entry: Any, value: int, new_character: Callable[[int], object]
) -> bool:
    """
    按项键修改全局状态，键 6 及其他键或子值均不改动。
    Keyword arguments:
    key -- int，0 日期、1 名册、3/4/5 仓库、7 派对、8 招募进度、9 待招
    entry -- Any，0 传年月日 0-2，1 传 [id, 0] 从名册移除，7/8 逗号对
    value -- int，日期分量、仓库物品数量或待确认招募集合单值
    new_character -- Callable[[int], object]，键 1 传 [id, 1] 时调用
    Return arguments:
    bool -- 仅当键 0 或 1 收到单元素列表时返回 False，否则返回 True
    """
    if key == 0:
        if len(entry) == 1:
            return False
        if entry[1] == 0:
            set_clock(game_time.now().replace(year=value))
        elif entry[1] == 1:
            set_clock(game_time.now().replace(month=value))
        elif entry[1] == 2:
            set_clock(game_time.now().replace(day=value))
    elif key == 1:
        if len(entry) == 1:
            return False
        if entry[1] == 0:
            roster.discard(entry[0])
        elif entry[1] == 1:
            new_character(entry[0])
    elif key in _RESOURCES:
        warehouse.set(_RESOURCES[key], value)
    elif key == 7:
        week_day, entertainment_id = map(int, entry.split(","))
        entertainment.set_party_day(week_day, entertainment_id)
    elif key == 8:
        line_id, progress = map(int, entry.split(","))
        recruit.set_line(line_id, progress=progress)
    elif key == 9:
        recruit.set_pending({value})
    return True


def player_lines() -> list[str]:
    """
    构造常用更改页十八条展示文本。
    Keyword arguments:
    无
    Return arguments:
    list[str] -- 玩家基础数值行与快捷操作标签拼接列表
    """
    return [stat() for stat in _PLAYER_STATS] + list(_PLAYER_ACTIONS)


def player_info(key: int) -> str:
    """
    返回玩家常用基础数值项（0 至 7）的当前展示文本。
    Keyword arguments:
    key -- int，玩家数值项键（0 至 7）
    Return arguments:
    str -- 对应数值项的展示文本
    """
    return _PLAYER_STATS[key]()


def _reset_positions() -> None:
    """规范在编干员宿舍区名称并将位置重置到对应宿舍路径。"""
    for chara_id in roster.active():
        cid = identity.of(chara_id).cid
        chara_life.dormitory.set(
            cid, chara_life.dormitory(cid).replace("01区", "1区")
        )
        activity.set_position(
            cid,
            map_handle.get_map_system_path_for_str(chara_life.dormitory(cid)),
        )


def _open_facilities() -> None:
    """将所有设施升至 5 级、全部开放并刷新基地数据。"""
    for all_cid in facility.levels():
        facility.set_level(all_cid, 5)
        for cid in facility.opens():
            facility.set_open(cid, True)
        basement.get_base_updata()


def _recruit_adv(adv_id: int) -> str:
    """按 adv_id 查找角色，未招募时加入待确认队列并返回提示。"""
    from Script.Design import character

    character_id = character.get_character_id_from_adv(adv_id)
    if roster.has(character_id):
        return _("\n已招募过\n")
    recruit.set_pending(recruit.pending() | {character_id})
    return _("\n招募成功\n")


_ARTS_TALENTS = frozenset(
    {304, 305, 306, 307, 308, 309, 310, 311, 312, 316, 317, 318}
    | {331, 332, 333, 334}
)
""" 一键开启全源石技艺时赋予玩家的素质编号集合。 """


def edit_player(key: int, value: int) -> str:
    """
    执行常用更改页指定项的修改，键 16 返回招募提示文本。
    Keyword arguments:
    key -- int，常用更改项键（0 至 17）
    value -- int，0-7 赋值，15 增交互对象触碰状态，16 作 adv_id，余忽略
    Return arguments:
    str -- 键 16 的招募结果提示，其余项返回空字符串
    """
    for stat_key, setter, field in _STAT_FIELDS:
        if key == stat_key:
            setter(0, **{field: value})
    if key == 8:
        for talent_id in _ARTS_TALENTS:
            abilities.talent(0)[talent_id] = 1
            needs.set(0, sanity=9999, sanity_max=9999)
    elif key == 9:
        for material_id in warehouse.stock():
            warehouse.set(material_id, 99999)
    elif key == 10:
        _open_facilities()
    elif key == 11:
        roster.discard(0)
        for chara_id in roster.active():
            flags.reset(identity.of(chara_id).cid)
    elif key == 12:
        roster.discard(0)
        for chara_id in roster.active():
            clothing.get_npc_cloth(chara_id)
    elif key == 13:
        roster.discard(0)
        _reset_positions()
    elif key == 14:
        for i in range(len(recruit.lines())):
            recruit.set_line(i, **recruit.IDLE)
        recruit.set_pending(())
    elif key == 15:
        target_id = activity.target(0)
        for state_id, state in game_config.config_character_state.items():
            if state.type == 0:
                status.add(target_id, state_id, value)
    elif key == 16:
        return _recruit_adv(value)
    elif key == 17:
        _reset_entertainment()
    return ""


def _reset_entertainment() -> None:
    """从在编名册移除主角并为其余在编干员重新分配娱乐活动。"""
    from Script.Design import handle_npc_ai

    roster.discard(0)
    for chara_id in roster.active():
        handle_npc_ai.get_chara_entertainment(chara_id)
