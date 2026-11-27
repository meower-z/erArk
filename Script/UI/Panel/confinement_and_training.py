"""监禁调教管理面板"""

import os
from types import FunctionType
from Script.Core import get_text, flow_handle, constant
from Script.UI.Moudle import draw, view
from Script.Config import game_config, normal_config
from Script.Modules.domains import chara_life
from Script.Modules.domains import inventory
from Script.Modules.domains import prison
from Script.Modules.gameplay_resolution import prison_service, training_prep
from Script.Modules.domains import identity

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


class Confinement_And_Training_Manage_Panel:
    """
    用于监禁调教管理的面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_panel = _("监禁调教管理")
        """ 当前绘制的页面 """
        self.draw_list: list[draw.NormalDraw] = []
        """ 绘制的文本列表 """
        self.pl_character_data = identity.of(0)
        """ 玩家的角色数据 """
        self.done_training_status_id_set: set[int] = set()
        """ 已经调教过的状态id集合 """

    def draw(self) -> None:
        """绘制对象"""

        title_text = _("监禁调教管理")
        title_draw = draw.TitleLineDraw(title_text, self.width)
        while 1:
            return_list = []
            title_draw.draw()

            # 输出提示信息
            now_draw = draw.NormalDraw()
            info_text = _(
                " \n ○点击[选项标题]显示[选项介绍]，点击[选项本身]即可[改变该选项]\n"
            )
            now_draw.text = info_text
            now_draw.width = self.width
            now_draw.draw()

            all_info_draw = draw.NormalDraw()
            now_text = "   "
            prisoner_ids = prison.prisoner_ids()
            if not prisoner_ids:
                now_text += _("目前没有囚犯\n")
            else:
                now_text += _("目前的囚犯有：")
                for chara_id in prisoner_ids:
                    tem_character_data: identity.Identity = identity.of(
                        chara_id
                    )
                    live_room = chara_life.dormitory(chara_id).split(os.sep)[-1]
                    now_text += _(" [{0}]{1} - {2}  ").format(
                        str(tem_character_data.adv).rjust(4, "0"),
                        tem_character_data.name,
                        live_room,
                    )
                now_text += "\n"

            all_info_draw.text = now_text
            all_info_draw.width = self.width
            all_info_draw.draw()

            # 遍历全部设置
            for cid in game_config.config_confinement_training_setting:
                # 如果是第13序号[调教目标]的话，需要12[调教助手]已开启
                if cid == 13 and prison.setting(12) == 0:
                    continue
                line_feed.draw()
                confinement_training_setting_data = (
                    game_config.config_confinement_training_setting[cid]
                )
                # 选项名
                button_text = f"  [{confinement_training_setting_data.name}]： "
                button_len = max(len(button_text) * 2, 60)
                button_draw = draw.LeftButton(
                    button_text,
                    button_text,
                    button_len,
                    cmd_func=self.draw_info,
                    args=(cid),
                )
                button_draw.draw()
                return_list.append(button_draw.return_text)

                now_setting_flag = prison.setting(cid)  # 当前设置的值
                option_len = len(
                    game_config.config_confinement_training_setting_option[cid]
                )  # 选项的长度

                # 当前选择的选项的名字
                button_text = f" [{game_config.config_confinement_training_setting_option[cid][now_setting_flag]}] "
                button_len = max(len(button_text) * 2, 20)

                # 绘制选项
                if cid not in {11}:
                    button_draw = draw.LeftButton(
                        button_text,
                        str(cid) + button_text,
                        button_len,
                        cmd_func=self.change_setting,
                        args=(cid, option_len),
                    )
                    button_draw.draw()
                    return_list.append(button_draw.return_text)
                # 调教前准备单独处理
                elif cid == 11:
                    clean_flag = prison.cleaning()
                    lubrication_flag = prison.lubrication()

                    if clean_flag:
                        clean_text = _(" [进行污浊清洗] ")
                    else:
                        clean_text = _(" [不进行污浊清洗] ")
                    clean_button = draw.LeftButton(
                        clean_text,
                        _("污浊清洗"),
                        len(clean_text) * 2,
                        cmd_func=self.change_pre_training_cleaning,
                    )
                    clean_button.draw()
                    return_list.append(clean_button.return_text)
                    if lubrication_flag:
                        lubrication_text = _(" [使用润滑液提前润滑] ")
                    else:
                        lubrication_text = _(" [不使用润滑液提前润滑] ")
                    lubrication_button = draw.LeftButton(
                        lubrication_text,
                        _("润滑液"),
                        len(lubrication_text) * 2,
                        cmd_func=self.change_pre_training_lubrication,
                    )
                    lubrication_button.draw()
                    return_list.append(lubrication_button.return_text)
                    tool_text = _(" [调整道具使用] ")
                    tool_button = draw.LeftButton(
                        tool_text,
                        _("道具使用"),
                        len(tool_text) * 2,
                        cmd_func=self.adjust_tool_list,
                    )
                    tool_button.draw()
                    return_list.append(tool_button.return_text)
                # 调教助手的额外选项
                if cid == 12:
                    # 如果选择的是从指定列表中选择，则显示指定列表按钮
                    if prison.setting(cid) == 3:
                        target_text = _(" [调整指令列表] ")
                        target_button = draw.LeftButton(
                            target_text,
                            _("指令列表"),
                            len(target_text) * 2,
                            cmd_func=self.adjust_sex_assistant_instruct_list,
                        )
                        target_button.draw()
                        return_list.append(target_button.return_text)
                    # 绘制禁止指令列表按钮
                    ban_button_text = _(" [调整禁止指令列表] ")
                    ban_button = draw.LeftButton(
                        ban_button_text,
                        _("禁止指令列表"),
                        len(ban_button_text) * 2,
                        cmd_func=self.adjust_sex_assistant_instruct_list,
                        args=(True,),
                    )
                    ban_button.draw()
                    return_list.append(ban_button.return_text)

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

    def draw_info(self, cid: int) -> None:
        """绘制设置的详细信息"""
        line = draw.LineDraw("-", self.width)
        line.draw()
        now_draw = draw.WaitDraw()
        setting_data = game_config.config_confinement_training_setting[cid]
        new_info = setting_data.info.replace("\\n", "\n")
        info_text = f"\n {new_info}\n"
        now_draw.text = info_text
        now_draw.width = self.width
        now_draw.draw()
        line = draw.LineDraw("-", self.width)
        line.draw()

    def change_setting(self, cid: int, option_len: int) -> None:
        """修改设置"""
        cur = prison.setting(cid)
        prison.set_setting(cid, cur + 1 if cur < option_len - 1 else 0)

    def change_pre_training_cleaning(self) -> None:
        """切换是否进行污浊清洗"""
        prison.set_cleaning(not prison.cleaning())

    def change_pre_training_lubrication(self) -> None:
        """切换是否使用润滑液提前润滑"""
        prison.set_lubrication(not prison.lubrication())

    def adjust_tool_list(self) -> None:
        """调整道具使用"""
        body_item_list = training_prep.body_item_list

        while 1:
            return_list = []
            line = draw.LineDraw("-", self.width)
            line.draw()
            line_feed.draw()
            # 输出提示信息
            info_draw = draw.NormalDraw()
            info_text = _("○开启后，监狱长会在进行调教准备时依次使用选择道具\n")
            info_text += _("○消耗类道具会在使用时减少，数量不足时会自动关闭\n")
            info_draw.text = info_text
            info_draw.width = self.width
            info_draw.draw()
            line_feed.draw()

            # 遍历道具列表
            for i in range(len(body_item_list)):
                # 持有道具数量
                item_id = training_prep.get_item_id_from_body_item_list(i)
                item_num = inventory.items(0)[item_id]
                name_draw_text = f"[{(str(i)).rjust(2, '0')}]"
                len_add = 40 - len(body_item_list[i])  # 排版用的空格数量
                if i in {2, 3}:
                    len_add += 1
                # 如果是消耗类道具，显示数量
                if i in {8, 9, 10, 11, 12, 13}:
                    name_draw_text += f"{body_item_list[i]}(有{item_num}个) "
                    len_add += 1
                # 否则只显示是否持有
                else:
                    name_draw_text += f"{body_item_list[i]}"
                    if item_num > 0:
                        name_draw_text += _("(已持有)")
                    else:
                        name_draw_text += _("(未持有)")
                # 给name_draw_text从右侧补空格到40个字符
                name_draw_text = name_draw_text.ljust(len_add, " ")

                # 绘制道具名
                name_draw = draw.NormalDraw()
                name_draw.text = name_draw_text
                name_draw.width = len(name_draw_text)
                name_draw.draw()

                # 如果数量为0，则绘制灰色不可选按钮
                button_draw: draw.NormalDraw | draw.LeftButton
                if item_num <= 0:
                    if prison.tool(i):
                        prison.set_tool(i, 0)
                    button_text = _(" [不使用] ")
                    button_draw = draw.NormalDraw()
                    button_draw.text = button_text
                    button_draw.style = "deep_gray"
                    button_draw.width = 20
                    button_draw.draw()
                else:
                    if prison.tool(i):
                        button_text = _(" [使用] ")
                    else:
                        button_text = _(" [不使用] ")
                    button_draw = draw.LeftButton(
                        button_text,
                        str(i) + button_text,
                        20,
                        cmd_func=self.change_pre_training_tool,
                        args=(i,),
                    )
                    button_draw.draw()
                    return_list.append(button_draw.return_text)
                line_feed.draw()

            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            line_feed.draw()

            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                break

    def change_pre_training_tool(self, tool_id: int) -> None:
        """切换是否使用道具"""
        prison.set_tool(tool_id, 0 if prison.tool(tool_id) else 1)

    def adjust_sex_assistant_instruct_list(
        self, ban_flag: bool = False
    ) -> None:
        """调整调教助手指令列表"""
        new_status_id_list = (
            prison_service.get_all_can_use_behavior_id_for_sex_assistant()
        )
        while 1:
            return_list = []
            selected_behaviors = prison.assistant_behaviors()
            banned_behaviors = prison.assistant_ban_behaviors()
            line = draw.LineDraw("-", self.width)
            line.draw()
            line_feed.draw()
            # 遍历指令，绘制为按钮
            count = 0
            for status_id in new_status_id_list:
                # 获取状态数据
                status_data = game_config.config_behavior[status_id]
                # 获取指令id
                instruct_id = constant.behavior_id_to_instruct_id[status_id]
                # 绘制格式
                button_text = f" [{status_data.name}] "
                button_len = max(len(button_text) * 2, 30)
                # 选择下，选择变黄
                if not ban_flag and status_id in selected_behaviors:
                    draw_style = "gold_enrod"
                # 禁止下，选择变灰
                elif ban_flag and status_id in banned_behaviors:
                    draw_style = "deep_gray"
                else:
                    draw_style = "standard"
                # 绘制按钮
                button_draw = draw.CenterButton(
                    button_text,
                    str(instruct_id) + button_text,
                    button_len,
                    normal_style=draw_style,
                    cmd_func=self.change_select_instruct,
                    args=(status_id, ban_flag),
                )
                button_draw.draw()
                return_list.append(button_draw.return_text)
                # 换行
                count += 1
                if count % 6 == 0:
                    line_feed.draw()

            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            line_feed.draw()
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                break

    def change_select_instruct(
        self, instruct_id: str, ban_flag: bool = False
    ) -> None:
        """
        切换调教助手指令选择状态
        Keyword arguments:
        instruct_id -- 指令id
        ban_flag -- 是否禁止该指令
        """
        if not ban_flag:
            prison.toggle_assistant_behavior(instruct_id)
        else:
            prison.toggle_assistant_ban_behavior(instruct_id)
