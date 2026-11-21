"""
衣柜面板：列出当前场景衣柜里存有衣服的干员并查看其衣物，
可偷取全部内裤或袜子，或选择射在衣物上
"""

from collections.abc import Mapping
from types import FunctionType
from typing import cast

from Script.Core import cache_control, constant, flow_handle, game_type
from Script.Core import get_text, py_cmd, text_handle
from Script.Design import attr_text, clothing, handle_premise, map_handle
from Script.UI.Moudle import draw, panel, view
from Script.Kernel import core
from Script.Modules.gameplay_resolution import edits
from Script.Modules.tk_ui import player_pick
from Script.Config import game_config, normal_config
from Script.UI.Panel import ejaculation_panel

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


class Check_locker_Panel:
    """
    总面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.handle_panel: panel.PageHandlePanel | None = None
        """ 当前名字列表控制面板 """

    def draw(self) -> None:
        """绘制对象"""
        pl_data: game_type.Character = cache.character_data[0]

        # 获得地图相关的数据
        now_map = map_handle.get_map_for_path(pl_data.position)
        map_name = attr_text.get_map_path_text(now_map)
        map_path_str = map_handle.get_map_system_path_str_for_list(
            pl_data.position
        )
        map_data = cache.scene_data[map_path_str]
        title_draw = draw.TitleLineDraw(
            _("{0}的衣柜").format(map_name), self.width
        )

        self.handle_panel = panel.PageHandlePanel(
            [], FindDraw, 20, 8, self.width, True, True, 0
        )
        while 1:
            py_cmd.clr_cmd()
            title_draw.draw()
            npc_id_list = []

            # 宿舍的情况（同居助理的宿舍地址即博士房间，故博士房间也走这一支）
            if (
                "Dormitory" in map_data.scene_tag
                or "Dr_room" in map_data.scene_tag
            ):
                # 读取当前宿舍的npc列表
                for npc_id in cache.npc_id_got:
                    if npc_id:
                        character_data = cache.character_data[npc_id]
                        if map_path_str == character_data.dormitory:
                            for (
                                clothing_type
                            ) in game_config.config_clothing_type:
                                if len(
                                    character_data.cloth.cloth_locker_in_dormitory[
                                        clothing_type
                                    ]
                                ):
                                    npc_id_list.append(npc_id)
                                    break

            # 更衣室的情况
            elif "Locker_Room" in map_data.scene_tag:
                # 读取所有人物是否有在衣柜里存放衣服
                for npc_id in cache.npc_id_got:
                    if npc_id:
                        character_data = cache.character_data[npc_id]
                        for clothing_type in game_config.config_clothing_type:
                            if len(
                                character_data.cloth.cloth_locker_in_shower[
                                    clothing_type
                                ]
                            ):
                                npc_id_list.append(npc_id)
                                break

            info_draw = draw.NormalDraw()
            if len(npc_id_list):
                info_draw.text = _("\n发现以下衣柜里有衣服\n\n")
            else:
                info_draw.text = _("\n所有衣柜都是空的\n\n")
            info_draw.width = self.width
            info_draw.draw()

            self.handle_panel.text_list = npc_id_list
            self.handle_panel.update()
            return_list = []
            self.handle_panel.draw()
            return_list.extend(self.handle_panel.return_list)
            line_feed.draw()

            # 检查是否有内衣或袜子可以偷
            can_steal_pan = False
            can_steal_socks = False
            for npc_id in npc_id_list:
                now_locker = clothing.get_cloth_locker_by_type(
                    npc_id,
                    clothing.get_cloth_locker_type_by_scene(map_data.scene_tag),
                )
                if len(now_locker[9]):
                    can_steal_pan = True
                if len(now_locker[10]):
                    can_steal_socks = True

            steal_all_pan_draw = None
            steal_all_socks_draw = None
            if can_steal_pan:
                steal_all_pan_draw = draw.CenterButton(
                    _("[偷取所有内裤]"),
                    _("偷取所有内裤"),
                    window_width,
                    cmd_func=self.steal_all_pan,
                    args=(npc_id_list, map_data),
                )
                steal_all_pan_draw.draw()
                line_feed.draw()
                return_list.append(steal_all_pan_draw.return_text)

            if can_steal_socks:
                steal_all_socks_draw = draw.CenterButton(
                    _("[偷取所有袜子]"),
                    _("偷取所有袜子"),
                    window_width,
                    cmd_func=self.steal_all_socks,
                    args=(npc_id_list, map_data),
                )
                steal_all_socks_draw.draw()
                line_feed.draw()
                return_list.append(steal_all_socks_draw.return_text)

            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)

            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def steal_all_pan(
        self, npc_id_list: list[int], map_data: game_type.Scene
    ) -> None:
        """结算：偷取所有内裤"""
        count = 0
        show_text = "\n"
        for npc_id in npc_id_list:
            character_data = cache.character_data[npc_id]
            now_locker = clothing.get_cloth_locker_by_type(
                npc_id,
                clothing.get_cloth_locker_type_by_scene(map_data.scene_tag),
            )

            if len(now_locker[9]):
                from Script.Modules.domains import player_collection

                for pan_id in now_locker[9]:
                    # 跳过序号不存在的服装
                    if pan_id not in game_config.config_clothing_tem:
                        continue
                    player_collection.append_list_map(
                        "npc_panties_tem", npc_id, pan_id
                    )
                    pan_name = game_config.config_clothing_tem[pan_id].name
                    show_text += _("获得了{0}的{1}\n").format(
                        character_data.name, pan_name
                    )
                    count += 1
                now_locker[9] = []
        now_draw = draw.WaitDraw()
        now_draw.width = window_width
        now_draw.text = show_text + _(
            "\n已偷取所有人衣柜里的内裤（共{0}件），可在藏品馆里纳入收藏\n"
        ).format(count)
        now_draw.draw()

    def steal_all_socks(
        self, npc_id_list: list[int], map_data: game_type.Scene
    ) -> None:
        """结算：偷取所有袜子"""
        count = 0
        show_text = "\n"
        for npc_id in npc_id_list:
            character_data = cache.character_data[npc_id]
            now_locker = clothing.get_cloth_locker_by_type(
                npc_id,
                clothing.get_cloth_locker_type_by_scene(map_data.scene_tag),
            )

            if len(now_locker[10]):
                from Script.Modules.domains import player_collection

                for socks_id in now_locker[10]:
                    # 跳过序号不存在的服装
                    if socks_id not in game_config.config_clothing_tem:
                        continue
                    player_collection.append_list_map(
                        "npc_socks_tem", npc_id, socks_id
                    )
                    socks_name = game_config.config_clothing_tem[socks_id].name
                    show_text += _("获得了{0}的{1}\n").format(
                        character_data.name, socks_name
                    )
                    count += 1
                now_locker[10] = []
        now_draw = draw.WaitDraw()
        now_draw.width = window_width
        now_draw.text = show_text + _(
            "\n已偷取所有人衣柜里的袜子（共{0}件），可在藏品馆里纳入收藏\n"
        ).format(count)
        now_draw.draw()


class FindDraw:
    """
    显示可点击的NPC名字按钮对象
    Keyword arguments:
    text -- 食物名字
    width -- 最大宽度
    is_button -- 绘制按钮
    num_button -- 绘制数字按钮
    button_id -- 数字按钮id
    """

    def __init__(
        self,
        npc_id: int,
        width: int,
        is_button: bool,
        num_button: bool,
        button_id: int,
    ) -> None:
        """初始化绘制对象"""
        self.npc_id = npc_id
        """ 角色id """
        self.character_data = cache.character_data[npc_id]
        """ 角色数据 """
        self.pl_data: game_type.Character = cache.character_data[0]
        """ 玩家角色数据 """
        self.draw_text: str = ""
        """ 名字绘制文本 """
        self.width: int = width
        """ 最大宽度 """
        self.num_button: bool = num_button
        """ 绘制数字按钮 """
        self.button_id: int = button_id
        """ 数字按钮的id """
        self.button_return: str = str(button_id)
        """ 按钮返回值 """
        self.draw_list: list[draw.NormalDraw] = []
        """ 绘制的文本列表 """

        # 获得地图相关的数据
        pl_character_data: game_type.Character = cache.character_data[0]
        map_path_str = map_handle.get_map_system_path_str_for_list(
            pl_character_data.position
        )
        map_data = cache.scene_data[map_path_str]

        # 获取当前衣柜是哪个衣柜
        self.now_locker = clothing.get_cloth_locker_by_type(
            self.npc_id,
            clothing.get_cloth_locker_type_by_scene(map_data.scene_tag),
        )

        name_draw: draw.NormalDraw | draw.LeftButton = draw.NormalDraw()
        # print("text :",text)
        if is_button:
            if num_button:
                index_text = text_handle.id_index(button_id)
                button_text = _("{0}{1}的衣柜").format(
                    index_text, self.character_data.name
                )
                name_draw = draw.LeftButton(
                    button_text,
                    self.button_return,
                    self.width,
                    cmd_func=self.check_cloth,
                )
                self.draw_text = button_text
        self.now_draw = name_draw
        """ 绘制的对象 """

    def draw(self) -> None:
        """绘制对象"""
        self.now_draw.draw()

    def check_cloth(self) -> None:
        """点击后进入衣服操作子界面"""
        # title_draw = draw.TitleLineDraw(self.text, window_width)
        return_list: list[str] = []
        # title_draw.draw()
        cloth_show_draw = draw.NormalDraw()
        while 1:
            return_list.clear()
            line = draw.LineDraw("-", window_width)
            line.draw()
            cloth_show_text = _("\n{0}的衣柜里放着刚脱下来的：\n").format(
                self.character_data.name
            )
            for clothing_type in game_config.config_clothing_type:
                cloth_list = self.now_locker[clothing_type]
                if len(cloth_list):
                    for cloth_id in cloth_list:
                        # 跳过序号不存在的服装
                        if cloth_id not in game_config.config_clothing_tem:
                            continue
                        cloth_name = game_config.config_clothing_tem[
                            cloth_id
                        ].name
                        cloth_show_text += f" {cloth_name}"
                    semen_now_count = (
                        self.character_data.dirty.cloth_locker_semen[
                            clothing_type
                        ][1]
                    )
                    if semen_now_count:
                        cloth_show_text += _("({0}ml精液)").format(
                            semen_now_count
                        )
            cloth_show_draw.text = cloth_show_text + "\n\n"
            cloth_show_draw.draw()

            # 选项面板
            # button_all_draw = panel.LeftDrawTextListPanel()

            button0_text = _("[001]把内衣拿起来闻一闻味道")
            button0_draw = draw.LeftButton(
                _(button0_text),
                _("1"),
                window_width,
                cmd_func=self.smell,
                args=(),
            )
            line_feed.draw()
            button0_draw.draw()
            return_list.append(button0_draw.return_text)

            if len(self.now_locker[9]) > 0:
                button1_text = _("[002]偷走内裤")
                button1_draw = draw.LeftButton(
                    _(button1_text),
                    _("2"),
                    window_width,
                    cmd_func=self.get_pan,
                    args=(),
                )
                line_feed.draw()
                button1_draw.draw()
                return_list.append(button1_draw.return_text)

            if len(self.now_locker[10]) > 0:
                button2_text = _("[003]偷走袜子")
                button2_draw = draw.LeftButton(
                    _(button2_text),
                    _("3"),
                    window_width,
                    cmd_func=self.get_socks,
                    args=(),
                )
                line_feed.draw()
                button2_draw.draw()
                return_list.append(button2_draw.return_text)

            # 仅在玩家合计精液大于2ml时显示衣柜射精选项
            if handle_premise.handle_pl_semen_g_2(0):
                button3_text = _("[004]用衣服冲，射在上面")
                button3_draw = draw.LeftButton(
                    _(button3_text),
                    _("4"),
                    window_width,
                    cmd_func=self.shoot_in_cloth,
                    args=(),
                )
                line_feed.draw()
                button3_draw.draw()
                return_list.append(button3_draw.return_text)

            # return_list.append(button0_draw.return_text)
            # button_all_draw.draw_list.append(button0_draw)
            # button_all_draw.width += len(button0_draw.text)
            # button_all_draw.draw_list.append(line_feed)
            # button_all_draw.width += 1

            # self.draw_list.extend(button_all_draw.draw_list)
            # for label in self.draw_list:
            #     if isinstance(label, list):
            #         for value in label:
            #             value.draw()
            #         line_feed.draw()
            #     else:
            #         label.draw()

            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                break

    def smell(self) -> None:
        """闻味道"""

        player_pick.choose(
            constant.Behavior.SMELL_UNDERWEAR,
            1,
            target=self.npc_id,
            state=constant.CharacterStatus.STATUS_SMELL_UNDERWEAR,
        )

    def get_pan(self) -> None:
        """偷内裤"""
        # 如果没有内裤则直接返回
        if not len(self.now_locker[9]):
            return

        pan_id = self.now_locker[9][-1]
        pan_name = game_config.config_clothing_tem[pan_id].name
        from Script.Modules.domains import player_collection

        player_collection.append_list_map(
            "npc_panties_tem", self.npc_id, pan_id
        )
        self.now_locker[9] = []
        now_draw = draw.WaitDraw()
        now_draw.width = window_width
        now_draw.text = _("\n获得了{0}的{1}，可在藏品馆里纳入收藏\n").format(
            self.character_data.name, pan_name
        )
        now_draw.draw()

    def get_socks(self) -> None:
        """偷袜子"""
        # 如果没有袜子则直接返回
        if not len(self.now_locker[10]):
            return

        socks_id = self.now_locker[10][-1]
        socks_name = game_config.config_clothing_tem[socks_id].name
        from Script.Modules.domains import player_collection

        player_collection.append_list_map(
            "npc_socks_tem", self.npc_id, socks_id
        )
        self.now_locker[10] = []
        now_draw = draw.WaitDraw()
        now_draw.width = window_width
        now_draw.text = _("\n获得了{0}的{1}，可在藏品馆里纳入收藏\n").format(
            self.character_data.name, socks_name
        )
        now_draw.draw()

    def shoot_in_cloth(self) -> None:
        """射在衣服上"""

        shoot_in_cloth_panel = panel.PageHandlePanel(
            [], Ejaculation_NameDraw, 20, 1, window_width, True, True, 0
        )

        while 1:
            return_list = []
            line_feed.draw()
            line = draw.LineDraw("-", window_width)
            line.draw()

            cloth_type_list = []
            for clothing_type in game_config.config_clothing_type:
                cloth_list = self.now_locker[clothing_type]
                if len(cloth_list):
                    cloth_type_list.append([clothing_type, self.npc_id])
            # print(f"debug cloth_type_list = {cloth_type_list}")

            # 绘制面板本体
            shoot_in_cloth_panel.text_list = cloth_type_list
            shoot_in_cloth_panel.update()
            shoot_in_cloth_panel.draw()
            return_list.extend(shoot_in_cloth_panel.return_list)
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)

            # 在非页面切换时退出面板
            if yrn == back_draw.return_text:
                break


class Ejaculation_NameDraw:
    """
    点击后可选择射精部位按钮对象
    Keyword arguments:
    text -- 部位名
    width -- 最大宽度
    is_button -- 绘制按钮
    num_button -- 绘制数字按钮
    button_id -- 数字按钮id
    """

    def __init__(
        self,
        text: list,
        width: int,
        is_button: bool,
        num_button: bool,
        button_id: int,
    ) -> None:
        """初始化绘制对象"""
        self.index = text[0]
        """ 部位id """
        self.npc_id = text[1]
        """ 角色id """
        self.draw_text: str = ""
        """ 部位名字绘制文本 """
        self.width: int = width
        """ 最大宽度 """
        self.num_button: bool = num_button
        """ 绘制数字按钮 """
        self.button_id: int = button_id
        """ 数字按钮的id """
        self.button_return: str = str(button_id)
        """ 按钮返回值 """

        # 获得地图相关的数据
        pl_character_data: game_type.Character = cache.character_data[0]
        target_data: game_type.Character = cache.character_data[self.npc_id]
        map_path_str = map_handle.get_map_system_path_str_for_list(
            pl_character_data.position
        )
        map_data = cache.scene_data[map_path_str]

        # 获取当前衣柜是哪个衣柜（2大浴场更衣室/3宿舍，博士房间按宿舍处理）
        self.locker_type = clothing.get_cloth_locker_type_by_scene(
            map_data.scene_tag
        )
        now_locker = clothing.get_cloth_locker_by_type(
            self.npc_id, self.locker_type
        )

        # 获取衣服名字
        now_text = game_config.config_clothing_type[self.index].name
        cloth_name_text = ":"
        for cloth_id in now_locker[self.index]:
            cloth_name_text += (
                f" {game_config.config_clothing_tem[cloth_id].name}"
            )
        now_text += cloth_name_text
        # print(f"debug text = {text}, self.text = {self.text}")

        # 绘制按钮
        if is_button:
            if num_button:
                index_text = text_handle.id_index(button_id)
                button_text = f"{index_text} {now_text}"
                if target_data.dirty.cloth_locker_semen[self.index][1] != 0:
                    button_text += _(" ({0}ml精液)").format(
                        str(target_data.dirty.cloth_locker_semen[self.index][1])
                    )
                name_draw: draw.CenterButton = draw.LeftButton(
                    button_text,
                    self.button_return,
                    self.width,
                    cmd_func=self.shoot_here,
                )
            else:
                button_text = f"[{now_text}]"
                name_draw = draw.CenterButton(
                    button_text, now_text, self.width, cmd_func=self.shoot_here
                )
                self.button_return = now_text
            self.draw_text = button_text
            self.now_draw = name_draw
            """ 绘制的对象 """

    def draw(self) -> None:
        """绘制对象"""
        self.now_draw.draw()

    def shoot_here(self) -> None:
        """清除当前命令，定下射在该干员衣柜里这一衣物类型上的具名编辑"""
        py_cmd.clr_cmd()
        player_pick.commit_edit(
            "locker_shoot",
            {
                "part": self.index,
                "locker": self.locker_type,
                "target": self.npc_id,
            },
        )


@edits.edit("locker_shoot")
def shoot_in_locker(who: int, args: Mapping[str, core.JSON]) -> None:
    """
    射在衣柜的衣物上：射精流程（射精量的随机数与高潮结算）在编辑开始时运行
    Keyword arguments:
    who -- 角色id
    args -- part 衣物类型，locker 衣柜类型（2 大浴场更衣室，3 宿舍），target 衣柜主人的角色id
    """
    ejaculation_panel.ejaculation_flow(
        part_cid=int(cast(int, args["part"])),
        part_type=int(cast(int, args["locker"])),
        target_character_id=int(cast(int, args["target"])),
        draw_flag=True,
    )
