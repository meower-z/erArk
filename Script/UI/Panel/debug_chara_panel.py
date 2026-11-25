"""
调试面板角色编辑子界面（debug_chara_panel）
===========================================
本模块负责 NPC 角色调试菜单与各状态子页面的界面绘制和输入采集。
"""

from types import FunctionType

from Script.Config import normal_config
from Script.Core import flow_handle, get_text
from Script.Modules.domains import identity
from Script.Modules.gameplay_resolution import debug_chara_edit as edit_svc
from Script.Modules.gameplay_resolution import debug_chara_view as view_svc
from Script.Modules.gameplay_resolution.debug_world_service import parse_index
from Script.UI.Moudle import draw, panel
from Script.UI.Moudle.draw import Drawable, NormalDraw

_: FunctionType = get_text._
""" 本地化翻译函数。 """
line_feed = draw.NormalDraw()
""" 用于输出单个换行的通用绘制对象。 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 全局配置的界面文本宽度。 """
FORMAT_ERROR = "\n输出格式错误，请重试\n"
""" 输入格式不合法时显示的错误提示文本。 """


def ask(prompt: str) -> str:
    """弹出单条消息输入框并返回用户输入的文本。"""
    now_panel = panel.AskForOneMessage()
    now_panel.set(prompt, 100)
    return now_panel.draw()


def ask_value() -> int:
    """提示用户输入修改后的整数值并返回解析结果。"""
    return int(ask(_("输入改变后的值")))


def index_prompt() -> str:
    """返回带子项索引输入提示的本地化文本。"""
    return _("输入改变第几项，如果是带子项的项的话，中间用英文小写逗号隔开")


def pair_prompt() -> str:
    """返回列表键值逗号输入提示的本地化文本。"""
    return _(
        "输入改变的项目，如果是列表则输入要改变第几号数据，以及这一项变成几，中间用英文小写逗号隔开"
    )


def _block_prompt(key: int) -> str:
    """按子页编号返回娱乐或社会关系页的单行输入提示文本。"""
    if key == 17:
        return _(
            "输入改变的项目，中间用英文小写逗号隔开。娱乐活动输入三个int；借还书则先输入0为删除1为增加，然后再输入书籍编号；可能性直接输入对应数字"
        )
    return _(
        "输入改变的项目，如果是列表则输入要改变第几号数据，以及这一项变成0或者1，中间用英文小写逗号隔开。列表的内容元素0为删除1为增加"
    )


def draw_all(items: list[Drawable]) -> None:
    """依次调用列表中每个绘制对象的绘制方法。"""
    for item in items:
        item.draw()


class DebugCharaPanel:
    """单个 NPC 角色的调试编辑面板类，负责菜单与子页面交互。"""

    def __init__(self, width: int, target_character_id: int) -> None:
        """初始化角色调试面板宽度、目标角色编号与绘制列表。"""
        self.width: int = width
        """ 面板内容绘制宽度。 """
        self.target_character_id: int = target_character_id
        """ 当前编辑的目标角色编号。 """
        self.draw_list: list[draw.Drawable] = []
        """ 当前菜单页待绘制的控件列表。 """

    def draw(self) -> None:
        """绘制角色页眉与 22 项调试菜单并处理返回交互。"""
        while 1:
            draw.LineDraw("-", self.width).draw()
            info_draw = draw.NormalDraw()
            info_draw.width = self.width
            return_list = []
            info_draw.text = view_svc.header(self.target_character_id)
            info_draw.draw()
            self.draw_list = []
            for i, label in enumerate(view_svc.MENU):
                button_draw = draw.LeftButton(
                    label,
                    f"\n{i}",
                    self.width,
                    cmd_func=self.change_target_value,
                    args=i,
                )
                self.draw_list += [button_draw, line_feed]
                return_list.append(button_draw.return_text)
            draw_all(self.draw_list)
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            if flow_handle.askfor_all(return_list) == back_draw.return_text:
                break

    def change_target_value(self, key_index: int) -> None:
        """运行单个角色调试子页面的展示、输入修改与重绘循环。"""
        change_draw_flag = True
        while 1:
            draw.LineDraw("-", self.width).draw()
            cid = identity.of(self.target_character_id).cid
            name_draw, info_draw = draw.NormalDraw(), draw.NormalDraw()
            name_draw.text = view_svc.header(self.target_character_id)
            name_draw.width = self.width
            name_draw.draw()
            if key_index in view_svc.SCREENS:
                kind, lines = view_svc.SCREENS[key_index]
                done = self._screen(
                    key_index,
                    cid,
                    kind,
                    lines(cid),
                    info_draw,
                    change_draw_flag,
                )
                if done is not None:
                    change_draw_flag = not done
                    continue
            line_feed.draw()
            back_draw = draw.CenterButton(
                _("[返回]"), _("返回"), window_width / 2
            )
            back_draw.draw()
            again_draw = draw.CenterButton(
                _("[继续修改]"), _("继续修改"), window_width / 2
            )
            again_draw.draw()
            line_feed.draw()
            return_list = [again_draw.return_text, back_draw.return_text]
            if flow_handle.askfor_all(return_list) == back_draw.return_text:
                break
            change_draw_flag = True

    def _screen(
        self,
        key: int,
        cid: int,
        kind: view_svc.ScreenKind,
        lines: list[str],
        info_draw: NormalDraw,
        ask_input: bool,
    ) -> bool | None:
        """绘制子页并返回：未询输入 None、被拒重询 False、接受 True。"""
        if kind in ("list", "gap"):
            for line in lines:
                info_draw.text = line
                info_draw.draw()
                line_feed.draw()
        else:
            info_draw.text = lines[0]
            info_draw.draw()
            line_feed.draw()
        if kind != "list":
            line_feed.draw()
        if not ask_input:
            return None
        if kind == "list":
            line_feed.draw()
        if kind in ("list", "gap"):
            index = parse_index(ask(index_prompt()))
            value = ask_value()
        elif kind == "block":
            index, value = parse_index(ask(_block_prompt(key))), 0
        else:
            text = ask(pair_prompt())
            if "," not in text:
                info_draw.text = FORMAT_ERROR
                info_draw.draw()
                return False
            index, value = parse_index(text), 0
        if not edit_svc.edit(key, cid, index, value):
            info_draw.text = FORMAT_ERROR
            info_draw.draw()
            return False
        return True
