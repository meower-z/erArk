"""动力系统管理面板，绘制概览与四个子界面，规则和文案来自 power_panel_service 与动力领域模块。"""

from functools import partial
from types import FunctionType

from Script.Core import get_text, flow_handle, constant
from Script.Config import normal_config
from Script.Design import attr_calculation
from Script.UI.Moudle import draw, panel, view
from Script.Modules.domains import power, power_supply
from Script.Modules.gameplay_resolution import power_panel_service as svc

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

_: FunctionType = get_text._
window_width: int = normal_config.config_normal.text_width
pad = attr_calculation.pad_display_width
line_feed = draw.NormalDraw()
line_feed.text = "\n"
line_feed.width = 1

"""
动力系统管理面板 (Rhodes Power Management Panel)
================================================
概览显示理论耗电与发电、储能、调控员人数与各类设施数量，下面四个按钮进入子界面。
 1. [001]供电策略调整，逐区块显示策略与耗电，[-]/[+] 轮换策略。
 2. [002]调控员管理，增减调控员，任命火力、水力、风力、光伏的主调控员。
 3. [003]发电设施管理，显示燃料库存，增减副源石反应炉与清洁能源设施。
 4. [004]蓄电池管理，显示储能，增减 L1、L2、L3 蓄电池。
按钮的修改记进玩家选择的缓冲区，离开面板时随一个 0 分钟的 Edit 生效。绘制本身不写游戏状态。
"""


def _say(text: str, width: int | None = None) -> None:
    """绘制普通文本 text，width 非 None 时同步设置绘制宽度。"""
    now_draw = draw.NormalDraw()
    if width is not None:
        now_draw.width = width
    now_draw.text = text
    now_draw.draw()


def _center(
    return_list: list[str],
    text: str,
    name: str,
    width: int,
    func: "Callable[..., object] | None" = None,
    args: object = (),
) -> None:
    """
    绘制居中按钮并将返回键追加至 return_list。
    Keyword arguments:
    return_list -- list[str]，按钮返回键列表
    text -- str，按钮显示文本
    name -- str，按钮返回键名称
    width -- int，按钮绘制宽度
    func -- Callable | None，点击回调，默认 None
    args -- object，回调参数，默认空元组
    """
    button = draw.CenterButton(text, name, width, cmd_func=func, args=args)
    button.draw()
    return_list.append(button.return_text)


def _more_less(
    return_list: list[str], name: str, act: "Callable[[int], object]"
) -> None:
    """
    绘制宽度 8 的 [+] 增加与 [-] 减少居中按钮对并换行。
    Keyword arguments:
    return_list -- list[str]，按钮返回键列表
    name -- str，拼入返回键的设施名
    act -- Callable[[int], object]，接收 1 或 -1 的回调
    """
    for text, verb, delta in (
        (_("[+]"), _("增加"), 1),
        (_("[-]"), _("减少"), -1),
    ):
        _center(return_list, text, verb + name, 8, partial(act, delta))
    line_feed.draw()


def _back(return_list: list[str], width: int) -> str:
    """绘制宽度为 width 的返回居中按钮并换行，记入 return_list 后返回该键。"""
    _center(return_list, _("[返回]"), _("返回"), width)
    line_feed.draw()
    return return_list[-1]


def _craft(operator: svc.Operator) -> str:
    """将调控员 operator 的制造等级格式化为括号后缀，为 None 时返回空串。"""
    if operator.craft is None:
        return ""
    return _("(制造lv{0})").format(operator.craft)


def _supply_line() -> str:
    """返回当前理论用电量与理论供电量的本地化汇总行。"""
    return _("\n  当前理论用电量: {0} / 理论供电量:{1}\n").format(
        power_supply.power_consumption(), power_supply.power_generation()
    )


class Manage_Power_System_Panel:
    """动力系统管理面板"""

    def __init__(self, width: int) -> None:
        """
        初始化面板
        Keyword arguments:
        width -- 绘制宽度
        """
        self.width = width

    def draw(self) -> None:
        """
        循环绘制动力系统概览与四个子界面按钮（供电策略、调控员、发电设施、蓄电池）
        选择返回时把当前面板设为主场景并退出
        Return arguments:
        None
        """
        while 1:
            draw.TitleLineDraw(_("动力系统管理"), self.width).draw()
            plant = power.plant()
            hydro, wind, solar = plant["clean"]
            clean = [power_supply.clean_generation(kind) for kind in range(3)]
            overview = [
                _("--概览--"),
                _("  当前理论用电量: {0} / 理论供电量:{1}").format(
                    power_supply.power_consumption(),
                    power_supply.power_generation(),
                ),
                _("  储能: {0:.1f}/{1:.1f}").format(
                    power.storage(), power.storage_max()
                ),
                _("  调控员人数: {0}").format(len(power.operator_ids())),
                _("  源石反应炉(每天) 主:{0} 副:{1} 理论产出:{2:.1f}").format(
                    power.main_reactor_level(),
                    plant["aux_reactors"],
                    power_supply.fire_generation(),
                ),
                _(
                    "  清洁能源(每天) 水力:{0}({3:.1f}) 风能:{1}({4:.1f}) 光伏:{2}({5:.1f})"
                ).format(hydro, wind, solar, *clean),
                _("  蓄电池(L1/L2/L3): {0}/{1}/{2}").format(
                    *plant["batteries"]
                ),
            ]
            _say("\n".join(overview) + "\n", self.width)
            line_feed.draw()
            return_list: list[str] = []
            for text, name, func in (
                (
                    _("[001]供电策略调整"),
                    _("供电策略调整"),
                    self._panel_supply_strategy,
                ),
                (_("[002]调控员管理"), _("调控员管理"), self._panel_operator),
                (
                    _("[003]发电设施管理"),
                    _("发电设施管理"),
                    self._panel_facilities,
                ),
                (_("[004]蓄电池管理"), _("蓄电池管理"), self._panel_battery),
            ):
                button = draw.LeftButton(text, name, self.width, cmd_func=func)
                button.draw()
                return_list.append(button.return_text)
                line_feed.draw()
            line_feed.draw()
            line_feed.draw()
            back = _back(return_list, self.width)
            if flow_handle.askfor_all(return_list) == back:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def _panel_supply_strategy(self) -> None:
        """供电策略调整子界面"""
        while 1:
            draw.TitleLineDraw(_("供电策略"), self.width).draw()
            return_list: list[str] = []
            _say(_supply_line(), self.width)
            line_feed.draw()
            _say(
                _("{0} | {1} | [-]降级   [+]升级\n").format(
                    pad("　" + _("区块"), 12, "center"),
                    pad(_("当前策略"), 23, "center"),
                )
            )
            for zone in svc.zones():
                name = pad("　" + zone.name, 12)
                strategy = pad(zone.strategy, 10)
                use = str(zone.consumption).ljust(10)
                _say(f"{name} | {strategy} = {use} | ")
                for text, verb, step in (
                    (_("[-]"), _("降低"), -1),
                    (_("[+]"), _("提升"), 1),
                ):
                    func = partial(svc.step_strategy, zone.cid, step)
                    _center(return_list, text, verb + zone.name, 6, func)
                line_feed.draw()
            line_feed.draw()
            back = _back(return_list, self.width)
            if flow_handle.askfor_all(return_list) == back:
                break

    def _panel_operator(self) -> None:
        """调控员管理子界面"""
        from Script.UI.Panel import manage_basement_panel

        type_name = [
            _("源石反应炉"),
            _("水力发电"),
            _("风力发电"),
            _("光伏发电"),
        ]
        while 1:
            draw.TitleLineDraw(_("调控员管理"), self.width).draw()
            return_list: list[str] = []
            _say(
                _("当前调控员数量：{0}  总效率加成：{1:.2%}").format(
                    len(power.operator_ids()), power_supply.operator_bonus()
                )
                + " " * 4
            )
            button_text = _("[调控员增减]")
            _center(
                return_list,
                _(button_text),
                _(button_text),
                len(button_text) * 2 + 2,
                manage_basement_panel.change_npc_work_out,
                (self.width, [11]),
            )
            line_feed.draw()
            line_feed.draw()
            for idx, operator in enumerate(svc.main_operators()):
                _say(
                    _("{0}主调控员: {1}{2}").format(
                        pad(type_name[idx], 12),
                        pad(operator.name or _("(空缺)"), 12),
                        _craft(operator),
                    )
                )
                appoint = partial(self._appoint_main_operator, idx)
                name = _("任命") + type_name[idx]
                _center(return_list, _("[任命]"), name, 12, appoint)
                line_feed.draw()
            line_feed.draw()
            names = [op.name + _craft(op) for op in svc.assistants()]
            _say(_("辅助调控员: ") + ("、".join(names) if names else _("暂无")))
            line_feed.draw()
            line_feed.draw()
            back = _back(return_list, self.width)
            if flow_handle.askfor_all(return_list) == back:
                break

    def _appoint_main_operator(self, type_idx: int) -> None:
        """
        打开通用干员选择器为指定发电类型任命或撤下主调控员，循环至返回。
        Keyword arguments:
        type_idx -- int，发电类型下标（0 火、1 水、2 风、3 光）
        """

        type_name = [_("源石反应炉"), _("水力"), _("风能"), _("光伏")]
        return_list: list[str] = []

        def _make_appoint(c_id: int) -> None:
            power.appoint_main_operator(type_idx, c_id)

        from Script.UI.Panel import common_select_NPC

        button_list = common_select_NPC.CommonSelectNPCButtonList
        now_draw_panel: panel.PageHandlePanel = panel.PageHandlePanel(
            [], button_list, 50, 5, window_width, True, False, 0
        )
        select_state: dict[str, int | str] = {}

        while 1:
            info_text = _("请选择一名调控员担任{0}主调控员:\n").format(
                type_name[type_idx]
            )
            now_draw_panel.text_list = [
                [
                    npc_id,
                    _make_appoint,
                    [power.plant()["main_operators"][type_idx]],
                ]
                for npc_id in svc.candidates()
            ]
            return_list, _other_return_list, select_state = (
                common_select_NPC.common_select_npc_button_list_func(
                    now_draw_panel, _("任命主调控员"), info_text, select_state
                )
            )

            yrn = flow_handle.askfor_all(return_list)
            if yrn == _("返回"):
                break

    def _panel_facilities(self) -> None:
        """发电设施管理子界面"""
        names = [
            _("水力发电轮组"),
            _("风力发电机组"),
            _("光伏发电板组"),
            _("人力性爱发电"),
        ]
        descs = [
            _("发电量受水流速影响，仅在停靠时可用，行驶中无法使用"),
            _("发电量受风速影响，仅在停靠时可用，行驶中无法使用"),
            _("发电量受日照影响，停靠或行驶中均可使用"),
            _("在人力发电室中绝顶/射精即可发电，发电量受绝顶/射精程度影响"),
        ]
        while 1:
            return_list: list[str] = []
            draw.TitleLineDraw(_("发电设施管理"), self.width).draw()
            _say(_supply_line() + svc.fuel_text())
            _say(svc.plant_modules_text())
            line_feed.draw()
            _say(
                _(
                    "○ 如果每日发电量+已储存蓄电量不够覆盖当日总用电量，将会影响罗德岛整体运营效率\n"
                )
                + _("○ 每日过剩的电量将优先充入蓄电池，溢出部分将被浪费\n")
                + _("○ 扩展模块可以在生产制造区的流水线上消耗资源进行制造\n")
                + _(
                    "○ 清洁能源设施的发电量受环境与天气影响较大，当前未实装地区环境与天气系统，暂为固定值乘以随机量\n"
                )
            )
            line_feed.draw()
            _say(
                _(" {0} | 当前 | {1} | {2} | {3}\n").format(
                    pad(_("设施"), 12, "center"),
                    pad(_("数值"), 9, "center"),
                    pad(_("信息"), 60, "center"),
                    pad(_("操作"), 14, "center"),
                )
            )
            _say(
                _(" 主源石反应炉 | {0}级 | {1}/燃料 | {2} | ").format(
                    str(power.main_reactor_level()).rjust(2, " "),
                    str(svc.main_efficiency()).rjust(4),
                    pad(
                        _("主炉等级等于动力区等级，决定单位燃料的发电效率"), 60
                    ),
                )
            )
            line_feed.draw()
            _say(
                _(" 副源石反应炉 | {0}台 | {1}/台日 | {2} | ").format(
                    str(power.plant()["aux_reactors"]).rjust(2, " "),
                    str(svc.aux_fuel()).rjust(4),
                    pad(
                        _(
                            "副炉数量影响每日燃料的燃烧数量，启用台数越多燃料消耗越多"
                        ),
                        60,
                    ),
                )
            )
            if svc.aux_adjustable():
                for text, name, delta in (
                    (_("[+]"), _("增加副源石反应炉"), 1),
                    (_("[-]"), _("减少副源石反应炉"), -1),
                ):
                    func = power.change_aux_reactors
                    _center(return_list, text, name, 8, func, (delta,))
                line_feed.draw()
            else:
                _say(_("（区块等级不足，无法调整副源石反应炉）\n"))
            for idx, row in enumerate(svc.clean_rows()):
                desc = pad(descs[idx], 60)
                if idx == 3:
                    _say(
                        _(" {0} | 人力 |  按次计算 | {1} | ").format(
                            names[idx], desc
                        )
                    )
                else:
                    _say(
                        _(" {0} | {1}组 | {2}/组日 | {3} | ").format(
                            names[idx],
                            str(row.count).rjust(2, " "),
                            str(round(row.output, 1)).rjust(4),
                            desc,
                        )
                    )
                if not row.usable:
                    _say(_("（当前设施不可用，无法调整数量）\n"))
                    continue
                if idx == 3:
                    continue
                act = partial(self._change, svc.change_clean, idx)
                _more_less(return_list, names[idx], act)
            line_feed.draw()
            back = _back(return_list, self.width)
            if flow_handle.askfor_all(return_list) == back:
                break

    def _panel_battery(self) -> None:
        """蓄电池管理子界面"""
        names = [_("L1"), _("L2"), _("L3")]
        locked = [
            _("（区块等级不足，无法调整L2蓄电池）\n"),
            _("（区块等级不足，无法调整L3蓄电池）\n"),
        ]
        while 1:
            draw.TitleLineDraw(_("蓄电池管理"), self.width).draw()
            return_list: list[str] = []
            storage = _("  当前储能: {0:.1f}/{1:.1f}\n").format(
                power.storage(), power.storage_max()
            )
            _say(_supply_line() + storage + svc.battery_modules_text())
            line_feed.draw()
            head = _(" 类型 | 数量 | 容量/台 | 自放电/天 |")
            _say(head + " " * 7 + _("操作\n"))
            for idx, row in enumerate(svc.battery_rows()):
                count = pad(str(row.count), 4, "center")
                capacity = str(row.capacity).rjust(4)
                rate = int(row.rate * 1000) / 10
                _say(
                    f"  {names[idx]}  | {count} |  {capacity}   |    {rate}%   | "
                )
                if not row.usable:
                    _say(locked[idx - 1])
                    continue
                act = partial(self._change, svc.change_battery, idx)
                _more_less(return_list, names[idx], act)
            line_feed.draw()
            line_feed.draw()
            back = _back(return_list, self.width)
            if flow_handle.askfor_all(return_list) == back:
                break

    def _change(
        self, change: "Callable[[int, int], str | None]", kind: int, delta: int
    ) -> None:
        """
        调用服务层增减函数，返回上限提示时通过 _hint 展示并等待确认。
        Keyword arguments:
        change -- Callable[[int, int], str | None]，增减函数
        kind -- int，设施类型或电池等级下标
        delta -- int，增减步长
        """
        hint = change(kind, delta)
        if hint is not None:
            self._hint(hint)

    def _hint(self, text: str) -> None:
        """
        绘制一条前后带空行的提示文本，并等待玩家确认
        Keyword arguments:
        text -- 提示文本
        Return arguments:
        None
        """
        msg = draw.WaitDraw()
        msg.width = self.width
        msg.text = "\n" + str(text) + "\n"
        msg.draw()
