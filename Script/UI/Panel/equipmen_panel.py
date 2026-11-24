"""装备维护界面面板 Equipment_Maintain_Panel 以及损坏与保养情况一览界面。"""

from types import FunctionType
from Script.Core import constant, flow_handle, get_text
from Script.UI.Moudle import draw, panel, view
from Script.Config import game_config, normal_config
from Script.Design import handle_premise
from Script.Modules.domains import identity
from Script.Modules.domains import maintenance, physical_exam, roster, wardrobe
from Script.Modules.gameplay_resolution import equipment_service

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


def show_damaged_equipment() -> None:
    """
    显示所有装备损坏（equipment_condition < 0）的干员及其装备情况
    输入/输出：无
    """
    title_text = _("装备损坏情况一览")
    title_draw = draw.TitleLineDraw(title_text, window_width)
    while 1:
        title_draw.draw()
        info_draw = draw.NormalDraw()
        now_text = _(
            "○中度损坏的装备会降低进行外勤委托的干员的能力值，如果装备严重损坏了则无法安排进行外勤委托\n\n"
        )
        damaged_count = 0
        for npc_id in roster.active():
            npc_data = identity.of(npc_id)
            condition_val = wardrobe.of(npc_id).equipment_condition
            if condition_val < 0:
                condition_name = equipment_service.get_equipment_condition_name(
                    condition_val
                )
                now_text += (
                    f"  {npc_data.name}：{condition_name} ({condition_val})\n"
                )
                damaged_count += 1
        if damaged_count == 0:
            now_text += _("  当前无装备损坏的干员\n")
        info_draw.text = now_text
        info_draw.draw()
        line_feed.draw()
        back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
        back_draw.draw()
        line_feed.draw()
        yrn = flow_handle.askfor_all([back_draw.return_text])
        if yrn == back_draw.return_text:
            break


def show_maintained_equipment() -> None:
    """
    显示所有装备保养（equipment_condition > 0）的干员及其装备情况
    输入/输出：无
    """
    title_text = _("装备保养情况一览")
    title_draw = draw.TitleLineDraw(title_text, window_width)
    while 1:
        title_draw.draw()
        info_draw = draw.NormalDraw()
        now_text = _(
            "○良好保养的装备有更高的耐久度，完美保养的装备还可以为外勤干员提供额外的能力加成\n\n"
        )
        maintained_count = 0
        for npc_id in roster.active():
            npc_data = identity.of(npc_id)
            condition_val = wardrobe.of(npc_id).equipment_condition
            if condition_val > 0:
                condition_name = equipment_service.get_equipment_condition_name(
                    condition_val
                )
                now_text += (
                    f"  {npc_data.name}：{condition_name} ({condition_val})\n"
                )
                maintained_count += 1
        if maintained_count == 0:
            now_text += _("  当前无装备保养的干员\n")
        info_draw.text = now_text
        info_draw.draw()
        line_feed.draw()
        back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
        back_draw.draw()
        line_feed.draw()
        yrn = flow_handle.askfor_all([back_draw.return_text])
        if yrn == back_draw.return_text:
            break


class Equipment_Maintain_Panel:
    """
    用于装备维护的面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_panel = _("装备维护")
        """ 当前绘制的页面 """
        self.draw_list: list[draw.NormalDraw] = []
        """ 绘制的文本列表 """

    def draw(self) -> None:
        """
        绘制装备维护主界面
        """
        from Script.UI.Panel import manage_basement_panel

        title_text = _("装备维护")
        title_draw = draw.TitleLineDraw(title_text, self.width)
        while 1:
            return_list = []
            title_draw.draw()
            line_feed.draw()
            # 维护策略按钮
            button_text1 = _("[001]指定维护策略")
            button_draw1 = draw.LeftButton(
                button_text1,
                button_text1,
                len(button_text1) * 3,
                cmd_func=self.select_maintain_strategy,
            )
            button_draw1.draw()
            return_list.append(button_draw1.return_text)
            line_feed.draw()
            # 变更铁匠人数按钮
            button_text2 = _("[002]变更铁匠人数")
            button_draw2 = draw.LeftButton(
                button_text2,
                button_text2,
                len(button_text2) * 3,
                cmd_func=manage_basement_panel.change_npc_work_out,
                args=(self.width, [22]),
            )
            button_draw2.draw()
            return_list.append(button_draw2.return_text)
            line_feed.draw()
            # 装备损坏一览按钮
            button_text3 = _("[003]干员装备损坏情况一览")
            button_draw3 = draw.LeftButton(
                button_text3,
                button_text3,
                len(button_text3) * 3,
                cmd_func=show_damaged_equipment,
            )
            button_draw3.draw()
            return_list.append(button_draw3.return_text)
            line_feed.draw()
            # 装备保养一览按钮
            button_text4 = _("[004]干员装备保养情况一览")
            button_draw4 = draw.LeftButton(
                button_text4,
                button_text4,
                len(button_text4) * 3,
                cmd_func=show_maintained_equipment,
            )
            button_draw4.draw()
            return_list.append(button_draw4.return_text)
            line_feed.draw()
            line_feed.draw()
            # 返回按钮
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            line_feed.draw()
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def select_maintain_strategy(self) -> None:
        """
        选择装备维护策略和保养目标（基于配置表）
        """
        title_text = _("调整装备维护策略和保养目标")
        title_draw = draw.TitleLineDraw(title_text, self.width)

        while 1:
            return_list = []
            line_feed.draw()
            title_draw.draw()

            # 输出提示信息
            now_draw = draw.NormalDraw()
            info_text = _(
                " \n ○点击[选项标题]显示[选项介绍]，点击[选项本身]即可[改变该选项]\n"
            )
            now_draw.text = info_text
            now_draw.width = self.width
            now_draw.draw()

            # 遍历全部设置
            for cid in game_config.config_equipment_maintain_setting:
                line_feed.draw()
                equipment_maintain_setting_data = (
                    game_config.config_equipment_maintain_setting[cid]
                )
                # 选项名
                button_text = f"  [{equipment_maintain_setting_data.name}]： "
                button_len = max(len(button_text) * 2, 60)
                button_draw: draw.CenterButton = draw.LeftButton(
                    button_text,
                    button_text,
                    button_len,
                    cmd_func=self.draw_info,
                    args=(cid),
                )
                button_draw.draw()
                return_list.append(button_draw.return_text)

                # 如果没有该键，则创建一个，并置为0
                if cid not in maintenance.settings():
                    maintenance.set_setting(cid, 0)
                now_setting_flag = maintenance.settings()[cid]  # 当前设置的值
                option_len = len(
                    game_config.config_equipment_maintain_setting_option[cid]
                )  # 选项的长度

                # 当前选择的选项的名字
                button_text = f" [{game_config.config_equipment_maintain_setting_option[cid][now_setting_flag]}] "
                button_len = max(len(button_text) * 2, 20)

                # 绘制选项
                button_draw = draw.LeftButton(
                    button_text,
                    str(cid) + button_text,
                    button_len,
                    cmd_func=self.change_setting,
                    args=(cid, option_len),
                )
                button_draw.draw()
                return_list.append(button_draw.return_text)

                # 部分选项有额外的手动选择按钮
                if cid == 2 and maintenance.settings()[cid] == 1:
                    now_len = len(physical_exam.ids(physical_exam.CHOSEN))
                    button_text = _("[调整干员名单]({0}人)").format(now_len)
                    button_len = max(len(button_text) * 2, 20)
                    button_draw = draw.CenterButton(
                        button_text,
                        str(cid) + button_text,
                        button_len,
                        cmd_func=self.adjust_target_list,
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
                break

    def draw_info(self, cid: int) -> None:
        """绘制设置的详细信息"""
        line = draw.LineDraw("-", self.width)
        line.draw()
        now_draw = draw.WaitDraw()
        setting_data = game_config.config_equipment_maintain_setting[cid]
        info_text = f"\n {setting_data.info}\n"
        now_draw.text = info_text
        now_draw.width = self.width
        now_draw.draw()
        line = draw.LineDraw("-", self.width)
        line.draw()

    def change_setting(self, cid: int, option_len: int) -> None:
        """修改设置"""
        now_value = maintenance.settings()[cid]
        maintenance.set_setting(
            cid, now_value + 1 if now_value < option_len - 1 else 0
        )

    def adjust_target_list(self) -> None:
        """调整装备维护名单"""
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
            npc_id_got_list = list(roster.active_sorted())
            # 已选择的角色id列表
            selected_id_list = maintenance.operators()
            final_list = []
            # 遍历角色id
            for npc_id in npc_id_got_list:
                if npc_id == 0:
                    continue
                # 跳过2、7异常的角色
                if not handle_premise.handle_normal_2(npc_id):
                    continue
                if not handle_premise.handle_normal_7(npc_id):
                    continue
                now_list = [
                    npc_id,
                    self.switch_chara_in_target_list,
                    selected_id_list,
                ]
                final_list.append(now_list)
            now_draw_panel.text_list = final_list

            # 调用通用选择按钮列表函数
            return_list, _other_return_list, select_state = (
                common_select_NPC.common_select_npc_button_list_func(
                    now_draw_panel,
                    _("装备维护对象名单"),
                    select_state=select_state,
                )
            )

            yrn = flow_handle.askfor_all(return_list)
            if yrn == _("返回"):
                break

    def switch_chara_in_target_list(self, character_id: int) -> None:
        """切换对象名单中的角色"""
        maintenance.toggle_operator(character_id)
