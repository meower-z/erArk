"""
动力系统管理面板的绘制与按钮。设施、储能与公式在 power 与 power_supply 模块
"""

from types import FunctionType

# 依赖模块，与生产线面板保持一致的导入方式
from Script.Core import get_text, flow_handle, constant
from Script.Config import game_config, normal_config
from Script.Design import attr_calculation
from Script.UI.Moudle import draw, panel, view
from Script.Modules.domains import facility, power, power_supply, warehouse
from Script.Modules.domains import abilities, location, identity

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

_: FunctionType = get_text._
window_width: int = normal_config.config_normal.text_width
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


# ---------------------------- 面板类 ---------------------------- #
class Manage_Power_System_Panel:
    """动力系统管理面板"""

    def __init__(self, width: int) -> None:
        """
        初始化面板
        Keyword arguments:
        width -- 绘制宽度
        """
        self.width = width

    # ---------- 主绘制 ---------- #
    def draw(self) -> None:
        """
        循环绘制动力系统概览与四个子界面按钮（供电策略、调控员、发电设施、蓄电池）
        选择返回时把当前面板设为主场景并退出
        Return arguments:
        None
        """
        while 1:
            title = draw.TitleLineDraw(_("动力系统管理"), self.width)
            title.draw()

            info = draw.NormalDraw()
            info.width = self.width
            # 概览文本
            overview = []
            overview.append(_("--概览--"))
            overview.append(
                _("  当前理论用电量: {0} / 理论供电量:{1}").format(
                    power_supply.power_consumption(),
                    power_supply.power_generation(),
                )
            )
            overview.append(
                _("  储能: {0:.1f}/{1:.1f}").format(
                    power.storage(), power.storage_max()
                )
            )
            overview.append(
                _("  调控员人数: {0}").format(len(power.operator_ids()))
            )
            # 显示分项发电潜力
            plant = power.plant()
            main_level = power.main_reactor_level()
            aux_count = plant["aux_reactors"]
            fire_theory = power_supply.fire_generation()
            hydro, wind, solar = plant["clean"]
            hydro_t = power_supply.clean_generation(0)
            wind_t = power_supply.clean_generation(1)
            solar_t = power_supply.clean_generation(2)
            # 开始拼接
            overview.append(
                _("  源石反应炉(每天) 主:{0} 副:{1} 理论产出:{2:.1f}").format(
                    main_level, aux_count, fire_theory
                )
            )
            overview.append(
                _(
                    "  清洁能源(每天) 水力:{0}({3:.1f}) 风能:{1}({4:.1f}) 光伏:{2}({5:.1f})"
                ).format(hydro, wind, solar, hydro_t, wind_t, solar_t)
            )
            overview.append(
                _("  蓄电池(L1/L2/L3): {0}/{1}/{2}").format(*plant["batteries"])
            )
            info.text = "\n".join(overview) + "\n"
            info.draw()

            line_feed.draw()
            return_list = []

            # 按钮 1 供电策略
            btn = draw.LeftButton(
                _("[001]供电策略调整"),
                _("供电策略调整"),
                self.width,
                cmd_func=self._panel_supply_strategy,
            )
            btn.draw()
            line_feed.draw()
            return_list.append(btn.return_text)
            # 按钮 2 调控员
            btn = draw.LeftButton(
                _("[002]调控员管理"),
                _("调控员管理"),
                self.width,
                cmd_func=self._panel_operator,
            )
            btn.draw()
            line_feed.draw()
            return_list.append(btn.return_text)
            # 按钮 3 发电设施
            btn = draw.LeftButton(
                _("[003]发电设施管理"),
                _("发电设施管理"),
                self.width,
                cmd_func=self._panel_facilities,
            )
            btn.draw()
            line_feed.draw()
            return_list.append(btn.return_text)
            # 按钮 4 蓄电池管理
            btn = draw.LeftButton(
                _("[004]蓄电池管理"),
                _("蓄电池管理"),
                self.width,
                cmd_func=self._panel_battery,
            )
            btn.draw()
            line_feed.draw()
            return_list.append(btn.return_text)

            line_feed.draw()
            line_feed.draw()
            back = draw.CenterButton(_("[返回]"), _("返回"), self.width)
            back.draw()
            return_list.append(back.return_text)
            line_feed.draw()

            yrn = flow_handle.askfor_all(return_list)
            if yrn == back.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    # ---------- 供电策略子界面 ---------- #
    def _panel_supply_strategy(self) -> None:
        """供电策略调整子界面"""
        # 获取供电策略数据
        supply_strategy = game_config.config_supply_strategy
        while 1:
            title = draw.TitleLineDraw(_("供电策略"), self.width)
            title.draw()
            return_list = []
            # 汇总
            summary = draw.NormalDraw()
            summary.width = self.width
            summary.text = _(
                "\n  当前理论用电量: {0} / 理论供电量:{1}\n"
            ).format(
                power_supply.power_consumption(),
                power_supply.power_generation(),
            )
            summary.draw()
            line_feed.draw()
            # 表头
            head = draw.NormalDraw()
            block_name = attr_calculation.pad_display_width(
                "　" + _("区块"), 12, "center"
            )
            now_strategy_text = attr_calculation.pad_display_width(
                _("当前策略"), 23, "center"
            )
            head.text = _("{0} | {1} | [-]降级   [+]升级\n").format(
                block_name, now_strategy_text
            )
            head.draw()
            # 列表
            for cid, fac_data in game_config.config_facility.items():
                try:
                    if fac_data.type != -1:
                        continue
                except Exception:
                    continue
                # 跳过动力区本身
                if cid == 1:
                    continue
                st = power.strategy_of(cid)
                # 设施名称
                fac_name = attr_calculation.pad_display_width(
                    "　" + fac_data.name, 12
                )
                # 当前策略
                now_strategy_text = f"{supply_strategy[st].name}({int(supply_strategy[st].adjust*100)}%)"
                now_strategy_text = attr_calculation.pad_display_width(
                    now_strategy_text, 10
                )
                # 当前耗电
                zone_use = str(power_supply.zone_consumption(cid)).ljust(10)
                # 行文本
                row_draw = draw.NormalDraw()
                row_draw.text = (
                    f"{fac_name} | {now_strategy_text} = {zone_use} | "
                )
                row_draw.draw()

                # 按钮
                def make_dec(cid_inner: int) -> "Callable[[], None]":
                    return lambda: self._set_strategy(
                        cid_inner,
                        (power.strategy_of(cid_inner) - 1) % 5,
                    )

                def make_inc(cid_inner: int) -> "Callable[[], None]":
                    return lambda: self._set_strategy(
                        cid_inner,
                        (power.strategy_of(cid_inner) + 1) % 5,
                    )

                btn_dec = draw.CenterButton(
                    _("[-]"),
                    _("降低") + fac_data.name,
                    6,
                    cmd_func=make_dec(cid),
                )
                btn_dec.draw()
                return_list.append(btn_dec.return_text)
                btn_inc = draw.CenterButton(
                    _("[+]"),
                    _("提升") + fac_data.name,
                    6,
                    cmd_func=make_inc(cid),
                )
                btn_inc.draw()
                return_list.append(btn_inc.return_text)
                line_feed.draw()

            line_feed.draw()
            back = draw.CenterButton(_("[返回]"), _("返回"), self.width)
            back.draw()
            return_list.append(back.return_text)
            line_feed.draw()
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back.return_text:
                break

    def _set_strategy(self, cid: int, value: int) -> None:
        """
        设置某区块的供电策略
        Keyword arguments:
        cid -- 区块id
        value -- 供电策略值
        Return arguments:
        None
        """
        power.set_strategy(cid, value)

    # ---------- 调控员管理 ---------- #
    def _panel_operator(self) -> None:
        """调控员管理子界面"""
        from Script.UI.Panel import manage_basement_panel

        while 1:
            title = draw.TitleLineDraw(_("调控员管理"), self.width)
            title.draw()
            return_list = []
            info = draw.NormalDraw()
            op_bonus = power_supply.operator_bonus()
            info.text = _("当前调控员数量：{0}  总效率加成：{1:.2%}").format(
                len(power.operator_ids()), op_bonus
            )
            info.text += " " * 4
            info.draw()

            button_text = _("[调控员增减]")
            button_draw = draw.CenterButton(
                _(button_text),
                _(button_text),
                len(button_text) * 2 + 2,
                cmd_func=manage_basement_panel.change_npc_work_out,
                args=(self.width, [11]),
            )
            return_list.append(button_draw.return_text)
            button_draw.draw()
            line_feed.draw()
            line_feed.draw()

            # 遍历显示各主调控员
            main_ops = power.plant()["main_operators"]
            type_name = [
                _("源石反应炉"),
                _("水力发电"),
                _("风力发电"),
                _("光伏发电"),
            ]
            for idx, cid in enumerate(main_ops):
                name = self._get_chara_name(cid)
                # 显示文本
                now_type_name = attr_calculation.pad_display_width(
                    type_name[idx], 12
                )
                chara_name = name if name else _("(空缺)")
                chara_name = attr_calculation.pad_display_width(chara_name, 12)
                abi_lv = abilities.ability(cid).get(48, 0)
                abi_lv_text = (
                    _("(制造lv{0})").format(abi_lv) if cid != 0 else ""
                )
                main_text = _("{0}主调控员: {1}{2}").format(
                    now_type_name, chara_name, abi_lv_text
                )
                main_draw = draw.NormalDraw()
                main_draw.text = main_text
                main_draw.draw()

                # 任命按钮
                def _make_appoint(i: int) -> "Callable[[], None]":
                    return lambda: self._appoint_main_operator(i)

                btn = draw.CenterButton(
                    _("[任命]"),
                    _("任命") + type_name[idx],
                    12,
                    cmd_func=_make_appoint(idx),
                )
                btn.draw()
                return_list.append(btn.return_text)
                line_feed.draw()
            line_feed.draw()

            # 遍历显示其他调控员
            other_ops = [
                cid for cid in power.operator_ids() if cid not in main_ops
            ]
            other_text = _("辅助调控员: ")
            if other_ops:
                names = []
                for cid in other_ops:
                    name = self._get_chara_name(cid) or _("(未知)")
                    chara_data = identity.get(cid)
                    if chara_data:
                        abi_lv = abilities.ability(chara_data.cid).get(48, 0)
                        name += _("(制造lv{0})").format(abi_lv)
                    names.append(name)
                other_text += "、".join(names)
            else:
                other_text += _("暂无")
            other_draw = draw.NormalDraw()
            other_draw.text = other_text
            other_draw.draw()

            line_feed.draw()
            line_feed.draw()
            back = draw.CenterButton(_("[返回]"), _("返回"), self.width)
            back.draw()
            return_list.append(back.return_text)
            line_feed.draw()
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back.return_text:
                break

    def _appoint_main_operator(self, type_idx: int) -> None:
        """
        任命某类型主调控员
        Keyword arguments:
        commision_id -- 委托编号
        """

        type_name = [_("源石反应炉"), _("水力"), _("风能"), _("光伏")]
        return_list: list[str] = []

        def _make_appoint(c_id: int) -> None:
            power.appoint_main_operator(type_idx, c_id)

        from Script.UI.Panel import common_select_NPC

        now_draw_panel: panel.PageHandlePanel = panel.PageHandlePanel(
            [],
            common_select_NPC.CommonSelectNPCButtonList,
            50,
            5,
            window_width,
            True,
            False,
            0,
        )
        select_state: dict[str, int | str] = {}

        while 1:
            info_text = _("请选择一名调控员担任{0}主调控员:\n").format(
                type_name[type_idx]
            )

            # 已选择的角色id列表
            final_list = []
            # 遍历角色id
            for npc_id in power.operator_ids():
                if npc_id == 0:
                    continue
                now_list = [
                    npc_id,
                    _make_appoint,
                    [power.plant()["main_operators"][type_idx]],
                ]
                final_list.append(now_list)
            now_draw_panel.text_list = final_list

            # 调用通用选择按钮列表函数
            return_list, _other_return_list, select_state = (
                common_select_NPC.common_select_npc_button_list_func(
                    now_draw_panel, _("任命主调控员"), info_text, select_state
                )
            )

            yrn = flow_handle.askfor_all(return_list)
            if yrn == _("返回"):
                break

    # ---------- 发电设施管理 ---------- #
    def _panel_facilities(self) -> None:
        """发电设施管理子界面"""
        fac_lv = facility.level(1, 1)
        # 计算区块等级提供的基础发电设施数量
        base_power_facility_by_fac_lv = fac_lv * 2 + 3
        while 1:
            return_list = []
            title = draw.TitleLineDraw(_("发电设施管理"), self.width)
            title.draw()

            # 汇总
            summary = draw.NormalDraw()
            summary.text = _(
                "\n  当前理论用电量: {0} / 理论供电量:{1}\n"
            ).format(
                power_supply.power_consumption(),
                power_supply.power_generation(),
            )
            # 燃料库存
            now_have = warehouse.stock().get(15, 0)
            daily_use = power_supply.fire_detail()["fuel_daily_plan"]
            support_days = (
                int(now_have // daily_use) if daily_use > 1e-6 else 9999
            )
            summary.text += _(
                "  当前燃料库存: {0} 单位，每日计划消耗 {1:.1f} 单位，约可支持 {2} 天\n"
            ).format(now_have, daily_use, support_days)
            # 如果燃料不够3天，提示警告
            if support_days < 3:
                summary.text += _(
                    "！燃料库存不足3天，建议尽快前往贸易区采购补充！\n"
                )
            # 如果当前罗德岛在行驶中
            move_flag = False
            if location.move() is not None:
                summary.text += _(
                    "！当前罗德岛处于行驶中，水力与风力发电设施无法工作！\n"
                )
                move_flag = True
            summary.draw()
            # 显示文本
            extra_module = draw.NormalDraw()
            extra_module.text = _(
                "  副源石反应炉扩展模块 ：已用 {0} / 总 {1} （含区块等级提供的{2}）\n"
            ).format(
                power.plant()["aux_reactors"],
                warehouse.amount(51) + base_power_facility_by_fac_lv,
                base_power_facility_by_fac_lv,
            )
            extra_module.text += _(
                "  清洁能源通用扩展模块 ：已用 {0} / 总 {1} （含区块等级提供的{2}）\n"
            ).format(
                sum(power.plant()["clean"]),
                warehouse.amount(53) + base_power_facility_by_fac_lv,
                base_power_facility_by_fac_lv,
            )
            extra_module.draw()
            line_feed.draw()
            # 提示信息
            info = draw.NormalDraw()
            info.text = _(
                "○ 如果每日发电量+已储存蓄电量不够覆盖当日总用电量，将会影响罗德岛整体运营效率\n"
            )
            info.text += _(
                "○ 每日过剩的电量将优先充入蓄电池，溢出部分将被浪费\n"
            )
            info.text += _(
                "○ 扩展模块可以在生产制造区的流水线上消耗资源进行制造\n"
            )
            info.text += _(
                "○ 清洁能源设施的发电量受环境与天气影响较大，当前未实装地区环境与天气系统，暂为固定值乘以随机量\n"
            )
            info.draw()
            line_feed.draw()
            head = draw.NormalDraw()
            facility_text = attr_calculation.pad_display_width(
                _("设施"), 12, "center"
            )
            value_text = attr_calculation.pad_display_width(
                _("数值"), 9, "center"
            )
            info_text = attr_calculation.pad_display_width(
                _("信息"), 60, "center"
            )
            change_text = attr_calculation.pad_display_width(
                _("操作"), 14, "center"
            )
            head.text = _(" {0} | 当前 | {1} | {2} | {3}\n").format(
                facility_text, value_text, info_text, change_text
            )
            head.draw()
            # 主反应炉
            main_lv: int | str = power.main_reactor_level()
            main_lv = str(main_lv).rjust(2, " ")
            # 读取当前等级单位燃料效率
            cid_eff = game_config.config_power_generation_level_index[
                _("主反应炉")
            ][int(main_lv)]
            eff_value = int(game_config.config_power_generation[cid_eff].value)
            eff_value_str = str(eff_value).rjust(4)
            main_info = attr_calculation.pad_display_width(
                _("主炉等级等于动力区等级，决定单位燃料的发电效率"), 60
            )
            row = draw.NormalDraw()
            row.text = _(" 主源石反应炉 | {0}级 | {1}/燃料 | {2} | ").format(
                main_lv, eff_value_str, main_info
            )
            row.draw()
            line_feed.draw()
            # 副反应炉
            aux: int | str = power.plant()["aux_reactors"]
            aux = str(aux).rjust(2, " ")
            # 副反应炉燃料增量(统一使用等级1配置数值作为单台每日燃料)
            cid_aux = game_config.config_power_generation_level_index[
                _("副反应炉")
            ][1]
            aux_fuel = int(game_config.config_power_generation[cid_aux].value)
            aux_fuel_str = str(aux_fuel).rjust(4)
            aux_info = attr_calculation.pad_display_width(
                _("副炉数量影响每日燃料的燃烧数量，启用台数越多燃料消耗越多"),
                60,
            )
            row = draw.NormalDraw()
            row.text = _(" 副源石反应炉 | {0}台 | {1}/台日 | {2} | ").format(
                aux, aux_fuel_str, aux_info
            )
            row.draw()
            # 如果等级小于2则不允许调整，固定为3台
            if fac_lv < 2:
                aux_limit_text = _("（区块等级不足，无法调整副源石反应炉）\n")
                aux_limit_draw = draw.NormalDraw()
                aux_limit_draw.text = aux_limit_text
                aux_limit_draw.draw()
            # 反应炉增减按钮
            else:
                btn_add = draw.CenterButton(
                    _("[+]"),
                    _("增加副源石反应炉"),
                    8,
                    cmd_func=power.change_aux_reactors,
                    args=(1,),
                )
                btn_add.draw()
                return_list.append(btn_add.return_text)
                btn_sub = draw.CenterButton(
                    _("[-]"),
                    _("减少副源石反应炉"),
                    8,
                    cmd_func=power.change_aux_reactors,
                    args=(-1,),
                )
                btn_sub.draw()
                return_list.append(btn_sub.return_text)
                line_feed.draw()
            # 清洁能源
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
            for idx in range(4):
                clean = power.plant()["clean"]
                if idx >= len(clean):
                    num: int | str = 0
                else:
                    num = clean[idx]
                num = str(num).rjust(2, " ")
                # 对应类别名称
                cat_map = {
                    0: _("水力"),
                    1: _("风力"),
                    2: _("光伏"),
                    3: _("人力"),
                }
                cid_lv3 = game_config.config_power_generation_level_index[
                    cat_map[idx]
                ][3]
                base_val = float(
                    game_config.config_power_generation[cid_lv3].value
                )
                # 检测是否可以发电
                cant_flag = False
                # 如果是在行驶中，则水力与风力发电设施无效
                if move_flag and idx in (0, 1):
                    cant_flag = True
                # 如果设施等级小于4，则风力发电无效
                if idx == 1 and fac_lv < 4:
                    cant_flag = True
                # 如果设施等级小于5，则光伏发电无效
                if idx == 2 and fac_lv < 5:
                    cant_flag = True
                if cant_flag:
                    base_val = 0.0
                base_val_str = str(round(base_val, 1)).rjust(4)
                row = draw.NormalDraw()
                descs_now = attr_calculation.pad_display_width(descs[idx], 60)
                row.text = _(" {0} | {1}组 | {2}/组日 | {3} | ").format(
                    names[idx], num, base_val_str, descs_now
                )
                if idx == 3:
                    row.text = _(" {0} | 人力 |  按次计算 | {1} | ").format(
                        names[idx], descs_now
                    )
                row.draw()
                # 如果设施不可用则不显示增减按钮
                if cant_flag:
                    cant_draw = draw.NormalDraw()
                    cant_draw.text = _("（当前设施不可用，无法调整数量）\n")
                    cant_draw.draw()
                    continue
                # 人力发电不允许调整
                if idx == 3:
                    continue

                # 增减按钮
                def _make_add(i: int) -> "Callable[[], None]":
                    return lambda: self._inc_clean(i, +1)

                def _make_sub(i: int) -> "Callable[[], None]":
                    return lambda: self._inc_clean(i, -1)

                btn_add = draw.CenterButton(
                    _("[+]"), _("增加") + names[idx], 8, cmd_func=_make_add(idx)
                )
                btn_add.draw()
                return_list.append(btn_add.return_text)
                btn_sub = draw.CenterButton(
                    _("[-]"), _("减少") + names[idx], 8, cmd_func=_make_sub(idx)
                )
                btn_sub.draw()
                return_list.append(btn_sub.return_text)
                line_feed.draw()

            line_feed.draw()
            back = draw.CenterButton(_("[返回]"), _("返回"), self.width)
            back.draw()
            return_list.append(back.return_text)
            line_feed.draw()
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back.return_text:
                break

    def _inc_clean(self, idx: int, delta: int) -> None:
        """增减一组某类清洁能源设施（power.change_clean），增加被上限挡下时绘制提示"""
        limit = power.change_clean(idx, delta)
        if limit is not None:
            self._hint(
                _(
                    "三种清洁能源设施总数已达上限({0})，可通过生产清洁能源模块扩展上限"
                ).format(limit)
            )

    # ---------- 蓄电池管理 ---------- #
    def _panel_battery(self) -> None:
        """蓄电池管理子界面"""
        fac_lv = facility.level(1, 1)
        # 设施等级提供的基础上限
        base_battery_by_fac_lv = fac_lv * 2 + 8
        while 1:
            title = draw.TitleLineDraw(_("蓄电池管理"), self.width)
            title.draw()
            return_list = []
            # 蓄电池总量限制与生产入口
            batteries = power.plant()["batteries"]
            total_batt = sum(batteries)
            # 汇总
            summary = draw.NormalDraw()
            summary.text = _(
                "\n  当前理论用电量: {0} / 理论供电量:{1}\n"
            ).format(
                power_supply.power_consumption(),
                power_supply.power_generation(),
            )
            summary.text += _("  当前储能: {0:.1f}/{1:.1f}\n").format(
                power.storage(), power.storage_max()
            )
            summary.text += _(
                "  蓄电池通用扩展模块 ：已用 {0} / 总 {1} （含区块等级提供的{2}）\n"
            ).format(
                total_batt,
                warehouse.amount(52) + base_battery_by_fac_lv,
                base_battery_by_fac_lv,
            )
            summary.draw()
            line_feed.draw()
            head = draw.NormalDraw()
            head.text = _(" 类型 | 数量 | 容量/台 | 自放电/天 |")
            head.text += " " * 7 + _("操作\n")
            head.draw()
            # 动态容量与自放电率显示
            cap_table = power.storage_levels(_("电池容量"), int, 0)
            rate_table = power.storage_levels(_("自放电率"), float, 0.0)
            names = [_("L1"), _("L2"), _("L3")]
            for idx in range(3):
                num = batteries[idx]
                num_str = attr_calculation.pad_display_width(
                    str(num), 4, "center"
                )
                cap_str = str(cap_table[idx]).rjust(4)
                row = draw.NormalDraw()
                row.text = f"  {names[idx]}  | {num_str} |  {cap_str}   |    {int(rate_table[idx]*1000)/10}%   | "
                row.draw()
                # 如果设施等级小于3，则L2不可用
                if idx == 1 and fac_lv < 3:
                    limit_draw = draw.NormalDraw()
                    limit_draw.text = _("（区块等级不足，无法调整L2蓄电池）\n")
                    limit_draw.draw()
                    continue
                # 如果设施等级小于4，则L3不可用
                if idx == 2 and fac_lv < 4:
                    limit_draw = draw.NormalDraw()
                    limit_draw.text = _("（区块等级不足，无法调整L3蓄电池）\n")
                    limit_draw.draw()
                    continue

                def make_add(i: int) -> "Callable[[], None]":
                    return lambda: self._change_battery(i, +1)

                def make_sub(i: int) -> "Callable[[], None]":
                    return lambda: self._change_battery(i, -1)

                btn_add = draw.CenterButton(
                    _("[+]"), _("增加") + names[idx], 8, cmd_func=make_add(idx)
                )
                btn_add.draw()
                return_list.append(btn_add.return_text)
                btn_sub = draw.CenterButton(
                    _("[-]"), _("减少") + names[idx], 8, cmd_func=make_sub(idx)
                )
                btn_sub.draw()
                return_list.append(btn_sub.return_text)
                line_feed.draw()
            line_feed.draw()
            line_feed.draw()
            back = draw.CenterButton(_("[返回]"), _("返回"), self.width)
            back.draw()
            return_list.append(back.return_text)
            line_feed.draw()
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back.return_text:
                break

    def _change_battery(self, level: int, delta: int) -> None:
        """
        增减一台某级蓄电池（power.change_battery），增加被上限挡下时绘制提示
        Keyword arguments:
        level -- 0、1、2 分别为 L1、L2、L3
        delta -- 大于 0 为增加，否则为减少
        """
        limit = power.change_battery(level, delta)
        if limit is not None:
            self._hint(
                _("蓄电池总数已达上限({0})，可通过生产蓄电池扩展上限").format(
                    limit
                )
            )

    # ---------- 小提示 ---------- #
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

    # ---------- 角色名工具 ---------- #
    def _get_chara_name(self, chara_id: int) -> str:
        """获取角色名称，失败则返回默认"""
        # 如果为id为0则为玩家，返回空字符串
        if chara_id == 0:
            return ""
        try:
            chara = identity.get(chara_id)
            if chara and hasattr(chara, "name"):
                return str(chara.name)
        except Exception:
            pass
        return _("干员") + str(chara_id)
