"""农业生产界面面板，提供药田与温室的作物调整与种植员管理界面。"""

from __future__ import annotations

from types import FunctionType
from Script.Core import get_text, flow_handle, constant
from Script.Design import basement
from Script.UI.Moudle import draw, panel, view
from Script.Config import game_config, normal_config
from typing import TYPE_CHECKING
from Script.Modules.domains import facility, production, warehouse
from Script.Modules.domains import abilities, identity
from Script.Modules.gameplay_resolution import agriculture_service

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


class Agriculture_Production_Panel:
    """
    用于农业生产的面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_panel = _("农业生产")
        """ 当前绘制的页面 """
        self.draw_list: list[draw.NormalDraw] = []
        """ 绘制的文本列表 """

    def draw(self) -> None:
        """绘制对象"""

        title_text = _("农业生产")
        title_draw = draw.TitleLineDraw(title_text, self.width)

        while 1:
            basement.get_base_updata()
            return_list = []
            title_draw.draw()

            all_info_draw = draw.NormalDraw()
            now_text = ""
            now_text += _(
                " 当前仓库等级：{0}，容量（单资源存放上限）：{1}\n"
            ).format(
                facility.level(3),
                warehouse.capacity(),
            )

            # 遍历该类型的资源
            for material_id in [11, 16]:
                material_data = game_config.config_resouce[material_id]
                now_text += (
                    f"  {material_data.name}：{warehouse.amount(material_id)}"
                )
            now_text += "\n"

            all_info_draw.text = now_text
            all_info_draw.draw()

            for agriculture_line_id, line in production.lines(
                "herb_garden"
            ).items():
                now_text = _("\n 药田：")
                all_info_draw.text = now_text
                all_info_draw.draw()

                # 基础数据
                resouce_id = line["product"]
                resouce_data = game_config.config_resouce[resouce_id]
                # 生产效率
                detail_str, produce_effect = (
                    agriculture_service.calculate_agriculture_line_efficiency(
                        agriculture_line_id, 0
                    )
                )
                new_produce_value = int(10 * produce_effect)

                # 生产产品
                now_text = _("\n    当前生产：{0}").format(resouce_data.name)
                now_text += f"({new_produce_value}/d)      "
                all_info_draw.text = now_text
                all_info_draw.draw()
                button_text = _(" [生产调整] ")
                button_draw = draw.CenterButton(
                    _(button_text),
                    _("{0}_药田_{1}").format(button_text, agriculture_line_id),
                    len(button_text) * 2,
                    cmd_func=self.select_agriculture_line_produce,
                    args=(agriculture_line_id, 0),
                )
                return_list.append(button_draw.return_text)
                button_draw.draw()
                line_feed.draw()

                # 生产效率绘制
                all_info_draw.text = "    " + detail_str
                all_info_draw.draw()
                line_feed.draw()

            # 已开放温室再显示温室的生产情况
            if facility.is_open(71):
                for agriculture_line_id, line in production.lines(
                    "green_house"
                ).items():
                    now_text = _("\n 温室：")
                    all_info_draw.text = now_text
                    all_info_draw.draw()

                    # 基础数据
                    resouce_id = line["product"]
                    resouce_data = game_config.config_resouce[resouce_id]
                    # 生产效率
                    detail_str, produce_effect = (
                        agriculture_service.calculate_agriculture_line_efficiency(
                            agriculture_line_id, 1
                        )
                    )
                    new_produce_value = int(10 * produce_effect)

                    # 生产产品
                    now_text = _("\n    当前生产：{0}").format(
                        resouce_data.name
                    )
                    now_text += f"({new_produce_value}/d)      "
                    all_info_draw.text = now_text
                    all_info_draw.draw()
                    button_text = _(" [生产调整] ")
                    button_draw = draw.CenterButton(
                        _(button_text),
                        _("{0}_温室_{1}").format(
                            button_text, agriculture_line_id
                        ),
                        len(button_text) * 2,
                        cmd_func=self.select_agriculture_line_produce,
                        args=(agriculture_line_id, 1),
                    )
                    return_list.append(button_draw.return_text)
                    button_draw.draw()
                    line_feed.draw()

                    all_info_draw.text = "    " + detail_str
                    all_info_draw.draw()
                    line_feed.draw()

            line_feed.draw()
            button_text = _("[001]种植员管理")
            button_draw = draw.LeftButton(
                _(button_text),
                _(button_text),
                self.width,
                cmd_func=self.select_agri_position,
            )
            button_draw.draw()
            return_list.append(button_draw.return_text)

            line_feed.draw()
            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def select_agri_position(self) -> None:
        """种植员管理(任命各线主种植员)"""
        from Script.UI.Panel import manage_basement_panel

        while 1:
            basement.update_work_people()
            title = draw.TitleLineDraw(_("种植员管理"), self.width)
            title.draw()
            return_list = []

            info = draw.NormalDraw()
            info.text = _(
                "当前药田种植员数量：{0}，温室种植员数量：{1}"
            ).format(
                len(production.workers("herb_garden")),
                len(production.workers("green_house")),
            )
            info.text += "      "
            info.draw()

            # 增减按钮
            button_text = _("[种植员增减]")
            button_draw = draw.CenterButton(
                _(button_text),
                _(button_text),
                len(button_text) * 2 + 2,
                cmd_func=manage_basement_panel.change_npc_work_out,
                args=(self.width, [161, 162]),
            )
            return_list.append(button_draw.return_text)
            button_draw.draw()
            line_feed.draw()
            line_feed.draw()

            # 药田各线任命
            for line_id, line in production.lines("herb_garden").items():
                main_id = line["main"]
                name = (
                    identity.of(main_id).name
                    if main_id != 0 and identity.exists(main_id)
                    else _("(空缺)")
                )
                abi_lv = abilities.ability(main_id).get(47, 0)
                abi_lv_text = (
                    _("(农业lv{0})").format(abi_lv) if main_id != 0 else ""
                )
                row = draw.NormalDraw()
                row.text = _("药田{0}号线 主种植员: {1}{2}").format(
                    line_id + 1, name, abi_lv_text
                )
                row.draw()

                def _make(idx: int) -> Callable[[], None]:
                    return lambda: self._appoint_main_agri(idx, 0)

                btn = draw.CenterButton(
                    _("[任命]"),
                    _("任命") + str(line_id + 1) + _("药田主种植员"),
                    12,
                    cmd_func=_make(line_id),
                )
                btn.draw()
                return_list.append(btn.return_text)
                line_feed.draw()
            line_feed.draw()

            # 药田副种植员
            main_ids = {
                line["main"]
                for line in production.lines("herb_garden").values()
            }
            other_ops = [
                cid
                for cid in production.workers("herb_garden")
                if cid not in main_ids
            ]
            other_draw = draw.NormalDraw()
            if other_ops:
                other_names = []
                for c in other_ops:
                    chara = identity.of(c)
                    abi_lv = abilities.ability(c).get(47, 0)
                    other_names.append(
                        _("{chara_name}(农业lv{abi_lv})").format(
                            chara_name=chara.name, abi_lv=abi_lv
                        )
                    )
                other_draw.text = (
                    _("药田副种植员：") + "、".join(other_names) + "\n"
                )
            else:
                other_draw.text = _("药田副种植员：暂无\n")
            other_draw.draw()
            line_feed.draw()
            line_feed.draw()

            # 温室（仅开放后显示）
            if facility.is_open(71, False):
                for line_id, line in production.lines("green_house").items():
                    main_id = line["main"]
                    name = (
                        identity.of(main_id).name
                        if main_id != 0 and identity.exists(main_id)
                        else _("(空缺)")
                    )
                    abi_lv = abilities.ability(main_id).get(47, 0)
                    abi_lv_text = (
                        _("(农业lv{0})").format(abi_lv) if main_id != 0 else ""
                    )
                    row = draw.NormalDraw()
                    row.text = _("温室{0}号线 主种植员: {1}{2}").format(
                        line_id + 1, name, abi_lv_text
                    )
                    row.draw()

                    def _make2(idx: int) -> Callable[[], None]:
                        return lambda: self._appoint_main_agri(idx, 1)

                    btn = draw.CenterButton(
                        _("[任命]"),
                        _("任命温室主种植员") + str(line_id + 1),
                        12,
                        cmd_func=_make2(line_id),
                    )
                    btn.draw()
                    return_list.append(btn.return_text)
                    line_feed.draw()
                line_feed.draw()

                main_ids = {
                    line["main"]
                    for line in production.lines("green_house").values()
                }
                other_ops = [
                    cid
                    for cid in production.workers("green_house")
                    if cid not in main_ids
                ]
                other_draw = draw.NormalDraw()
                if other_ops:
                    other_names = []
                    for c in other_ops:
                        chara = identity.of(c)
                        abi_lv = abilities.ability(c).get(47, 0)
                        other_names.append(
                            _("{chara_name}(农业lv{abi_lv})").format(
                                chara_name=chara.name, abi_lv=abi_lv
                            )
                        )
                    other_draw.text = (
                        _("温室副种植员：") + "、".join(other_names) + "\n"
                    )
                else:
                    other_draw.text = _("温室副种植员：暂无\n")
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

    def _appoint_main_agri(self, line_id: int, agriculture_type: int) -> None:
        """任命某条农业线主种植员(重复选择同一人可撤销)"""
        from Script.UI.Panel import common_select_NPC

        kind = ("herb_garden", "green_house")[agriculture_type]
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

        def _make(chara_id: int) -> None:
            production.appoint(kind, line_id, chara_id)

        while 1:
            op_list = production.workers(kind)
            now_main = production.lines(kind)[line_id]["main"]
            type_name = _("药田") if agriculture_type == 0 else _("温室")
            info_text = _("请选择一名种植员担任{0}{1}号线主种植员:\n").format(
                type_name, line_id + 1
            )
            final_list = []
            for npc_id in op_list:
                if npc_id == 0:
                    continue
                final_list.append([npc_id, _make, [now_main]])
            now_draw_panel.text_list = final_list
            return_list, _other_return_list, select_state = (
                common_select_NPC.common_select_npc_button_list_func(
                    now_draw_panel, _("任命主种植员"), info_text, select_state
                )
            )
            yrn = flow_handle.askfor_all(return_list)
            if yrn == _("返回"):
                break

    def select_agriculture_line_produce(
        self, agriculture_line_id: int, agriculture_type: int
    ) -> None:
        """
        选择生产的资源\n
        agriculture_line_id: int 生产线id\n
        agriculture_type: int 农业类型，0药田，1温室\n
        """
        resouce_id_list = [11] if agriculture_type == 0 else [16]
        while 1:

            line = draw.LineDraw("-", window_width)
            line.draw()
            info_draw = draw.NormalDraw()
            return_list = []

            resouce_id = production.lines("herb_garden")[agriculture_line_id][
                "product"
            ]
            resouce_data = game_config.config_resouce[resouce_id]

            info_text = ""
            info_text += _(" 当前种植的是：{0}").format(resouce_data.name)

            info_text += _("\n\n 当前可以种植的有：\n\n")
            info_draw.text = info_text
            info_draw.draw()

            # 遍历配方列表，获取每个配方的信息
            for cid in resouce_id_list:
                resouce_now_data = game_config.config_resouce[cid]

                # 判断当前配方是否可以生产，未解锁则跳过
                flag_open = True

                if flag_open:

                    # 输出配方信息
                    button_draw = draw.LeftButton(
                        f"[{str(cid).rjust(3,'0')}]{resouce_now_data.name}：{resouce_now_data.info}",
                        f"\n{cid}",
                        window_width,
                        cmd_func=self.change_agriculture_line_produce,
                        args=(agriculture_line_id, cid, agriculture_type),
                    )
                    button_draw.draw()
                    return_list.append(button_draw.return_text)
                    line_feed.draw()

            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn in return_list:
                break

    def change_agriculture_line_produce(
        self, agriculture_line_id: int, formula_cid: int, agriculture_type: int
    ) -> None:
        """更改农产品的种植"""
        kind = ("herb_garden", "green_house")[agriculture_type]
        production.change_product(kind, agriculture_line_id, formula_cid)
