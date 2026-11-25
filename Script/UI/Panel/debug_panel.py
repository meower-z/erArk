"""
调试与口上快速测试界面面板。
本模块负责 debug 面板与快速测试口上界面的绘制和输入循环。
口上测试与全局修改委托给 talk_test_service 与 debug_world_service。
角色调试子界面委托给 debug_chara_panel。
"""

from types import FunctionType

from Script.Config import normal_config
from Script.Core import constant, flow_handle, get_text, io_init, py_cmd
from Script.Design import character_handle
from Script.Modules.domains import activity, identity, npc_template
from Script.Modules.gameplay_resolution import debug_world_service as world
from Script.Modules.gameplay_resolution import talk_test_service as talk_test
from Script.Modules.gameplay_resolution.talk_test_service import (
    build_chara_talk,
)
from Script.UI.Moudle import draw, view
from Script.UI.Moudle.draw import Drawable, NormalDraw
from Script.UI.Panel import debug_chara_panel
from Script.UI.Panel.debug_chara_panel import ask, ask_value, line_feed

_: FunctionType = get_text._
""" 本地化翻译函数。 """
window_width: int = normal_config.config_normal.text_width
""" 全局配置的界面文本宽度。 """


def _wait(text: str) -> None:
    """使用等待绘制控件输出提示或报告文本。"""
    now_draw = draw.WaitDraw()
    now_draw.text = text
    now_draw.draw()


class TALK_QUICK_TEST:
    """快速测试口上面板类，负责菜单绘制、输入采集与结果展示。"""

    def __init__(self, width: int) -> None:
        """初始化快速测试口上面板宽度。"""
        self.width: int = width
        """ 面板内容绘制宽度。 """

    def draw(self) -> None:
        """运行快速测试口上的主交互循环。"""
        batch_mode = self._menu()
        if batch_mode is None:
            return
        while 1:
            py_cmd.clr_cmd()
            draw.LineDraw("-", window_width).draw()
            info_draw = draw.NormalDraw()
            info_draw.width = self.width
            if batch_mode:
                info_draw.text = _("\n\n批量测试开始\n\n")
            else:
                info_draw.text = _("\n\n测试开始\n\n")
            info_draw.draw()
            target_chara_id = talk_test.chara_by_adv(
                int(ask(_("请输入角色id")))
            )
            line_feed.draw()
            if batch_mode:
                talk_id_text = ask(_("请输入口上id（支持1,3,5或95-98）"))
            else:
                talk_id_text = ask(_("请输入口上id"))
            line_feed.draw()
            line_feed.draw()
            draw.LineDraw("-", self.width).draw()
            if batch_mode:
                self._batch(target_chara_id, talk_id_text)
            else:
                self._single(target_chara_id, talk_id_text)
            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            if flow_handle.askfor_all([back_draw.return_text]) == (
                back_draw.return_text
            ):
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def _menu(self) -> bool | None:
        """绘制模式选择菜单，返回是否进入批量测试或返回时的 None。"""
        title_draw = draw.TitleLineDraw(_("快速测试口上"), self.width)
        while 1:
            title_draw.draw()
            info_draw = draw.NormalDraw()
            info_draw.width = self.width
            info_draw.text = (
                _(
                    "本功能用于快速测试当前数据情况下，指定角色的指定id口上的触发情况，包括触发者与交互对象、是否能够触发、每个前提是否满足、最终输出文本等\n\n"
                )
                + _(
                    "刷新口上文件，用于在不重启游戏的情况，重新刷新并读取发生了变更的口上文件。即可以在编辑器中写完新的条目、保存，然后在游戏中点击该刷新按钮，读取刚写好的条目并进行测试\n\n"
                )
                + _(
                    "批量测试时，口上id支持逗号分隔（如1,3,5）和区间（如95-98）\n\n\n"
                )
            )
            info_draw.draw()
            modes = {}
            for text, func, batch in (
                (_("[001]刷新口上文件后测试"), self.refresh_talk_file, False),
                (_("[002]直接开始测试"), self.nothing, False),
                (_("[003]批量测试多条口上"), self.nothing, True),
            ):
                button_draw = draw.LeftButton(
                    text, text, len(text) * 2, cmd_func=func
                )
                button_draw.draw()
                modes[button_draw.return_text] = batch
                line_feed.draw()
            line_feed.draw()
            back_draw = draw.CenterButton(
                _("[返回]"), _("返回"), window_width / 4
            )
            back_draw.draw()
            line_feed.draw()
            yrn = flow_handle.askfor_all([*modes, back_draw.return_text])
            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                return None
            if yrn in modes:
                return modes[yrn]

    def _single(self, target_chara_id: int, talk_id_text: str) -> None:
        """解析单条口上编号并展示测试结果或错误提示。"""
        try:
            talk_id = int(talk_id_text)
        except ValueError:
            talk_id = -1
        if talk_id < 0:
            _wait(_("\n口上id输入错误，请重新进入面板输入\n"))
        else:
            _wait(talk_test.test_single_talk(target_chara_id, talk_id)[0])

    def _batch(self, target_chara_id: int, talk_id_text: str) -> None:
        """解析批量口上编号并在单组或分组模式下展示汇总结果。"""
        talk_id_list = talk_test.parse_talk_id_list(talk_id_text)
        if not talk_id_list:
            _wait(_("\n未输入有效的口上id，请重新进入面板输入\n"))
        elif len(talk_id_list) > talk_test.GROUP_SIZE:
            self.run_batch_talk_test_in_groups(target_chara_id, talk_id_list)
        else:
            with activity.target_as(0, activity.target(0)):
                lines, passed, failed = talk_test.run_tests(
                    target_chara_id, talk_id_list, 1, len(talk_id_list)
                )
            lines += talk_test.summary_lines(passed, failed)
            _wait("\n".join(lines))

    def run_batch_talk_test_in_groups(
        self, target_chara_id: int, talk_id_list: list[int]
    ) -> None:
        """按每组固定条数分页执行批量口上测试并支持中途停止。"""
        total = len(talk_id_list)
        size = talk_test.GROUP_SIZE
        all_passed: list[int] = []
        all_failed: list[int] = []
        stopped = False
        with activity.target_as(0, activity.target(0)):
            for start in range(0, total, size):
                end = min(start + size, total)
                lines, passed, failed = talk_test.run_tests(
                    target_chara_id, talk_id_list[start:end], start + 1, total
                )
                all_passed += passed
                all_failed += failed
                if end == total:
                    _wait("\n".join(lines))
                    break
                lines.append(talk_test.group_prompt(start + 1, end))
                _wait("\n".join(lines))
                line_feed.draw()
                continue_draw = draw.CenterButton(
                    _("[继续下一轮测试]"),
                    _("继续下一轮测试"),
                    window_width / 3,
                )
                continue_draw.draw()
                stop_draw = draw.CenterButton(
                    _("[停止测试并查看汇总]"),
                    _("停止测试并查看汇总"),
                    window_width / 3,
                )
                stop_draw.draw()
                line_feed.draw()
                yrn = flow_handle.askfor_all(
                    [continue_draw.return_text, stop_draw.return_text]
                )
                if yrn == stop_draw.return_text:
                    stopped = True
                    break
        _wait(
            "\n".join(talk_test.summary_lines(all_passed, all_failed, stopped))
        )

    def refresh_talk_file(self) -> None:
        """刷新指定角色的口上文件、重载配置并展示前后条目统计。"""
        chara_adv_id = int(ask(_("请输入角色id")))
        draw.LineDraw("-", window_width).draw()
        now_draw = draw.NormalDraw()
        now_draw.text = _("\n\n开始刷新口上文件，请稍等\n")
        now_draw.draw()
        for _i in range(5):
            line_feed.draw()
        io_init.flush()
        build_chara_talk(chara_adv_id)
        _wait(talk_test.refresh_text(*talk_test.reload_talk()))

    def nothing(self) -> None:
        """直接测试与批量测试按钮绑定的空回调。"""


class Debug_Panel:
    """debug 面板主类，协调常用更改、全局变量与 NPC 角色分页绘制。"""

    def __init__(self, width: int) -> None:
        """初始化 debug 面板宽度、默认分页与绘制列表。"""
        self.width: int = width
        """ 面板内容绘制宽度。 """
        self.now_panel = _("常用更改")
        """ 当前激活的分页名称。 """
        self.draw_list: list[draw.Drawable] = []
        """ 当前分页待绘制的控件列表。 """

    def draw(self) -> None:
        """运行 debug 面板主循环并处理分页切换与返回。"""
        tabs = [_("常用更改"), _("全局变量"), _("NPC角色")]
        title_draw = draw.TitleLineDraw("debug面板", self.width)
        while 1:
            return_list = []
            title_draw.draw()
            for tab in tabs:
                if tab == self.now_panel:
                    tab_draw = draw.CenterDraw()
                    tab_draw.text = f"[{tab}]"
                    tab_draw.style = "onbutton"
                    tab_draw.width = self.width / len(tabs)
                    tab_draw.draw()
                else:
                    tab_button = draw.CenterButton(
                        f"[{tab}]",
                        f"\n{tab}",
                        self.width / len(tabs),
                        cmd_func=self.change_panel,
                        args=(tab,),
                    )
                    tab_button.draw()
                    return_list.append(tab_button.return_text)
            line_feed.draw()
            draw.LineDraw("+", self.width).draw()
            self.draw_list = self._tab_items(return_list)
            debug_chara_panel.draw_all(self.draw_list)
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            if flow_handle.askfor_all(return_list) == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def _tab_items(self, return_list: list[str]) -> list[Drawable]:
        """按当前分页构造提示文本与按钮控件列表。"""
        items: list[Drawable] = []
        info_draw = draw.NormalDraw()
        info_draw.width = self.width
        if self.now_panel == _("NPC角色"):
            info_draw.text = "选择角色："
            items += [info_draw, line_feed]
            id_list = npc_template.ids()
            id_list.append(0)
            for count, npc_id in enumerate(id_list, 1):
                target = identity.of(npc_id)
                button_draw = draw.LeftButton(
                    f"[{str(target.adv).rjust(4, '0')}]：{target.name}",
                    f"\n{npc_id}",
                    int(self.width / 6),
                    cmd_func=self.change_target_character,
                    args=npc_id,
                    normal_style=(
                        "standard" if target.text_color == "" else target.name
                    ),
                )
                items.append(button_draw)
                return_list.append(button_draw.return_text)
                if count % 6 == 0:
                    items.append(line_feed)
            return items + [line_feed]
        if self.now_panel == _("全局变量"):
            info_draw.text = _("全局变量一览：")
            lines = world.global_lines()
        elif self.now_panel == _("常用更改"):
            info_draw.text = _(
                "！！！特别注意事项！！！\n！debug前请一定要进行存档备份，不正确和过大的数值修改可能会出现数据超限、跳过中间值结算、数据类型错误和长度错误等问题\n！这些问题会导致游戏的部分结算和功能无法运行和使用，进而坏档\n！总之请一定要进行存档备份，存档数据很珍贵的，坏档了就太痛了\n！！！特别注意事项！！！\n\n"
            ) + _("玩家的各项属性")
            lines = world.player_lines()
        else:
            return items
        items += [info_draw, line_feed]
        for i, text in enumerate(lines):
            button_draw = draw.LeftButton(
                text, f"\n{i}", self.width, cmd_func=self.change_value, args=i
            )
            items += [button_draw, line_feed]
            return_list.append(button_draw.return_text)
        return items

    def change_panel(self, department_type: str) -> None:
        """切换当前激活的分页名称。"""
        self.now_panel = department_type

    def change_target_character(self, NPC_id: int) -> None:
        """打开指定角色的调试编辑子面板。"""
        debug_chara_panel.DebugCharaPanel(self.width, NPC_id).draw()

    def change_value(self, key_index: int) -> None:
        """按当前分页执行所选全局变量或常用更改项的编辑流程。"""
        while 1:
            draw.LineDraw("-", self.width).draw()
            info_draw = draw.NormalDraw()
            info_draw.width = self.width
            if self.now_panel == "全局变量":
                if not self._edit_global(key_index, info_draw):
                    info_draw.text = debug_chara_panel.FORMAT_ERROR
                    info_draw.draw()
                    continue
            elif self.now_panel == "常用更改":
                self._edit_player(key_index, info_draw)
            line_feed.draw()
            break

    def _edit_global(self, key: int, info_draw: NormalDraw) -> bool:
        """展示全局变量项说明、采集输入并委托服务写入状态。"""
        kind = world.GLOBAL_KINDS.get(key)
        if kind is None:
            return True
        info_draw.text = world.global_info(key)
        info_draw.draw()
        line_feed.draw()
        entry, value = None, 0
        if kind == "date":
            entry = world.parse_index(ask(debug_chara_panel.index_prompt()))
            value = ask_value()
        elif kind == "roster":
            line_feed.draw()
            entry = world.parse_index(
                ask(
                    _(
                        "输入要改变第几号角色，以及这一项变成0或者1，中间用英文小写逗号隔开"
                    )
                )
            )
        elif kind == "pair":
            entry = ask(debug_chara_panel.pair_prompt())
        else:
            value = ask_value()
        return world.edit_global(
            key, entry, value, character_handle.get_new_character
        )

    def _edit_player(self, key: int, info_draw: NormalDraw) -> None:
        """按常用更改项类型采集输入、委托服务修改并输出提示。"""
        kind = world.PLAYER_KINDS.get(key)
        value = 0
        if kind == "stat":
            info_draw.text = world.player_info(key)
            info_draw.draw()
            line_feed.draw()
            value = ask_value()
        elif kind == "value":
            line_feed.draw()
            value = ask_value()
        elif kind == "adv":
            line_feed.draw()
            value = int(ask(_("输入adv_id")))
        message = world.edit_player(key, value) if kind else ""
        if kind == "adv":
            info_draw.text = message
            info_draw.draw()
            line_feed.draw()
