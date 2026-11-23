"""生产流水线管理界面面板，提供流水线的配方调整与生产工人管理界面。"""

from __future__ import annotations

from types import FunctionType
from Script.Core import constant, flow_handle, get_text
from Script.Design import attr_calculation, basement
from Script.UI.Moudle import draw, panel, view
from Script.Config import game_config, normal_config
from typing import TYPE_CHECKING
from Script.Modules.domains import facility, production, warehouse
from Script.Modules.domains import abilities, identity
from Script.Modules.gameplay_resolution import assembly_service

if TYPE_CHECKING:
    from collections.abc import Callable

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


class Manage_Assembly_Line_Panel:
    """
    用于生产产品的面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_panel = _("产品生产")
        """ 当前绘制的页面 """
        self.draw_list: list[draw.NormalDraw] = []
        """ 绘制的文本列表 """
        self.show_resource_type_dict: dict = {
            _("药剂"): False,
            _("乳制品"): False,
            _("香水"): False,
            _("基建"): False,
        }

    def draw(self) -> None:
        """绘制对象"""
        title_text = _("产品生产")
        title_draw = draw.TitleLineDraw(title_text, self.width)

        while 1:
            return_list = []
            title_draw.draw()

            all_info_draw = draw.NormalDraw()
            now_text = _(
                " 当前仓库等级：{0}，容量（单资源存放上限）：{1}\n"
            ).format(
                facility.level(3),
                warehouse.capacity(),
            )

            # 遍历全资源类型
            self.resouce_list = [
                _("材料"),
                _("药剂"),
                _("乳制品"),
                _("香水"),
                _("基建"),
            ]
            for resouce in self.resouce_list:
                now_text += (
                    f"\n {attr_calculation.pad_display_width(resouce, 8)}："
                )
                # 遍历该类型的资源
                for material_id in warehouse.stock():
                    material_data = game_config.config_resouce[material_id]
                    if material_data.type == resouce:
                        now_text += f"  {material_data.name}：{warehouse.amount(material_id)}"

            all_info_draw.text = now_text
            all_info_draw.draw()
            line_feed.draw()
            line_feed.draw()

            for assembly_line_id, line in production.lines("assembly").items():
                now_text = _("\n {0}号流水线：").format(assembly_line_id + 1)
                all_info_draw.text = now_text
                all_info_draw.draw()

                # 基础数据
                formula_id = line["product"]
                formula_data = game_config.config_productformula[formula_id]
                product_id = formula_data.product_id
                product_data = game_config.config_resouce[product_id]

                # 生产产品
                now_text = _("\n    当前生产：{0}(1/h)      ").format(
                    product_data.name
                )
                all_info_draw.text = now_text
                all_info_draw.draw()
                button_text = _(" [生产调整] ")
                button_draw = draw.CenterButton(
                    _(button_text),
                    f"{button_text}_{assembly_line_id}",
                    len(button_text) * 2,
                    cmd_func=self.select_assembly_line_produce,
                    args=assembly_line_id,
                )
                return_list.append(button_draw.return_text)
                button_draw.draw()
                line_feed.draw()

                # 生产效率展示
                detail_str, _total_eff = (
                    assembly_service.calculate_assembly_line_efficiency(
                        assembly_line_id
                    )
                )
                all_info_draw.text = "    " + detail_str
                all_info_draw.draw()

                # 生产消耗
                now_text = _("\n    当前生产消耗：")
                formula_text = formula_data.formula
                # 以&为分割判定是否有多个需求
                if "&" not in formula_text:
                    need_list = [formula_text]
                else:
                    need_list = formula_text.split("&")
                for need_text in need_list:
                    need_type = int(need_text.split("|")[0])
                    need_value = int(need_text.split("|")[1])
                    now_text += f"  {game_config.config_resouce[need_type].name}:{need_value}/h"
                all_info_draw.text = now_text
                all_info_draw.draw()
                line_feed.draw()

            line_feed.draw()
            # 管理按钮
            button_text = _("[001]生产工人管理")
            button_draw = draw.LeftButton(
                _(button_text),
                _(button_text),
                self.width,
                cmd_func=self.select_npc_position,
            )
            return_list.append(button_draw.return_text)
            button_draw.draw()

            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def select_npc_position(self) -> None:
        """生产工人管理(任命各线主生产工人 & 管理副工人列表)"""
        from Script.UI.Panel import manage_basement_panel

        while 1:
            # 刷新一下
            basement.update_work_people()
            title = draw.TitleLineDraw(_("生产工人管理"), self.width)
            title.draw()
            return_list = []

            # 提示信息
            info = draw.NormalDraw()
            info.text = _("当前生产工人数量：{0}").format(
                len(production.workers("assembly"))
            )
            info.text += "      "
            info.draw()

            # 生产工人增减按钮
            button_text = _("[生产工人增减]")
            btn = draw.CenterButton(
                _(button_text),
                _(button_text),
                len(button_text) * 2 + 2,
                cmd_func=manage_basement_panel.change_npc_work_out,
                args=(self.width, [121]),
            )
            btn.draw()
            return_list.append(btn.return_text)
            line_feed.draw()
            line_feed.draw()

            # 各生产线主生产工人显示与任命按钮
            for line_id, line in production.lines("assembly").items():
                main_id = line["main"]
                main_chara_data = identity.of(main_id)
                name = main_chara_data.name if main_id != 0 else _("(空缺)")
                abi_lv = abilities.ability(main_id).get(48, 0)
                abi_lv_text = (
                    _("(制造lv{0})").format(abi_lv) if main_id != 0 else ""
                )
                row = draw.NormalDraw()
                row.text = _("{0}号生产线 主生产工人: {1}{2}").format(
                    line_id + 1, name, abi_lv_text
                )
                row.draw()

                def _make(lid: int) -> Callable[[], None]:
                    return lambda: self._appoint_main_worker(lid)

                appoint_btn = draw.CenterButton(
                    _("[任命]"),
                    _("任命") + str(line_id + 1),
                    12,
                    cmd_func=_make(line_id),
                )
                appoint_btn.draw()
                return_list.append(appoint_btn.return_text)
                line_feed.draw()
                line_feed.draw()
            line_feed.draw()

            # 显示所有副生产工人
            main_ids = {
                line["main"] for line in production.lines("assembly").values()
            }
            other_ops = [
                cid
                for cid in production.workers("assembly")
                if cid not in main_ids and identity.exists(cid)
            ]
            other_draw = draw.NormalDraw()
            if other_ops:
                other_names = []
                for c in other_ops:
                    chara = identity.of(c)
                    abi_lv = abilities.ability(c).get(48, 0)
                    other_names.append(
                        _("{chara_name}(制造lv{abi_lv})").format(
                            chara_name=chara.name, abi_lv=abi_lv
                        )
                    )
                other_draw.text = (
                    _("副生产工人：") + "、".join(other_names) + "\n"
                )
            else:
                other_draw.text = _("副生产工人：暂无\n")
            other_draw.draw()
            line_feed.draw()
            line_feed.draw()

            # 返回按钮
            back = draw.CenterButton(_("[返回]"), _("返回"), self.width)
            back.draw()
            return_list.append(back.return_text)
            line_feed.draw()
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back.return_text:
                break

    def _appoint_main_worker(self, line_id: int) -> None:
        """任命主生产工人(重复选择撤销)"""
        from Script.UI.Panel import common_select_NPC

        now_panel = panel.PageHandlePanel(
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

        def _handler(chara_id: int) -> None:
            production.appoint("assembly", line_id, chara_id)

        while 1:
            info_text = _(
                "请选择一名生产工人担任第{0}号生产线主生产工人:\n"
            ).format(line_id + 1)
            final_list = []
            # 遍历生产工人列表
            main = production.lines("assembly")[line_id]["main"]
            for npc_id in production.workers("assembly"):
                if npc_id == 0:
                    continue
                final_list.append([npc_id, _handler, [main]])
            now_panel.text_list = final_list
            return_list, _other_return_list, select_state = (
                common_select_NPC.common_select_npc_button_list_func(
                    now_panel, _("任命主生产工人"), info_text, select_state
                )
            )
            yrn = flow_handle.askfor_all(return_list)
            if yrn == _("返回"):
                break

    def select_assembly_line_produce(self, assembly_line_id: int) -> None:
        """选择流水线生产的产品"""
        while 1:

            line = draw.LineDraw("-", window_width)
            line.draw()
            info_draw = draw.NormalDraw()
            return_list = []

            formula_now_id = production.lines("assembly")[assembly_line_id][
                "product"
            ]
            formula_now_data = game_config.config_productformula[formula_now_id]
            product_now_id = formula_now_data.product_id
            product_now_data = game_config.config_resouce[product_now_id]
            now_level = facility.level(12)

            info_text = ""
            # info_text = f" ○需要先结算然后才可以变动生产的产品\n\n"
            info_text += _(" {0}号流水线当前生产的产品为：{1}").format(
                assembly_line_id + 1, product_now_data.name
            )

            info_text += _("\n\n 当前可以生成的产品有：\n\n")
            info_draw.text = info_text
            info_draw.draw()

            resouce_list = [_("药剂"), _("乳制品"), _("香水"), _("基建")]

            # 遍历全资源类型
            for resouce in resouce_list:

                # 判断是否显示该类型的资源
                if self.show_resource_type_dict[resouce]:
                    draw_text = f" ▼[{resouce}]"
                else:
                    draw_text = f" ▶[{resouce}]"
                button_draw = draw.LeftButton(
                    f"{draw_text}",
                    f"{resouce}",
                    len(draw_text) * 2,
                    cmd_func=self.settle_show_resource_type,
                    args=(resouce),
                )
                button_draw.draw()
                return_list.append(button_draw.return_text)
                line_feed.draw()

                if not self.show_resource_type_dict[resouce]:
                    continue

                # 遍历该类型的资源
                for material_id in warehouse.stock():
                    material_data = game_config.config_resouce[material_id]
                    if material_data.type == resouce:
                        # 根据资源id来查找配方id
                        for (
                            formula_data
                        ) in game_config.config_productformula.values():
                            if formula_data.product_id == material_id:
                                formula_cid = formula_data.cid
                                break
                        else:
                            continue
                        # 如果没有配方id则跳过
                        if formula_cid == 0:
                            continue
                        # 判断当前配方是否可以生产，未解锁则跳过
                        flag_open = True
                        if formula_data.difficulty > now_level:
                            flag_open = False
                        # 可以生产的话则输出
                        if flag_open:
                            line_feed.draw()
                            button_draw = draw.LeftButton(
                                f"[{str(formula_cid).rjust(3,'0')}]{material_data.name}：{material_data.info}",
                                f"\n{formula_cid}",
                                window_width,
                                cmd_func=self.change_assembly_line_produce,
                                args=(assembly_line_id, formula_cid),
                            )
                            button_draw.draw()
                            return_list.append(button_draw.return_text)

                            formula_text = formula_data.formula
                            now_text = _("\n     生产消耗：")
                            # 以&为分割判定是否有多个需求
                            if "&" not in formula_text:
                                need_list = []
                                need_list.append(formula_text)
                            else:
                                need_list = formula_text.split("&")
                            for need_text in need_list:
                                need_type = int(need_text.split("|")[0])
                                need_value = int(need_text.split("|")[1])
                                now_text += f"  {game_config.config_resouce[need_type].name}：{need_value}/h"

                            info_draw.text = now_text
                            info_draw.draw()
                            line_feed.draw()
                line_feed.draw()

            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn in return_list and yrn not in resouce_list:
                break

    def change_assembly_line_produce(
        self, assembly_line_id: int, formula_cid: int
    ) -> None:
        """更改流水线生产的产品"""
        production.change_product("assembly", assembly_line_id, formula_cid)

    def settle_npc_id(self, chara_id: int) -> None:
        """结算干员的id变更"""
        self.now_chara_id = chara_id

    def settle_assembly_line_id(self, assembly_line_id: int) -> None:
        """结算流水线的id变更"""
        self.target_position = assembly_line_id

    def settle_show_resource_type(self, resouce_type: str) -> None:
        """设置显示的资源类型"""
        self.show_resource_type_dict[resouce_type] = (
            not self.show_resource_type_dict[resouce_type]
        )
