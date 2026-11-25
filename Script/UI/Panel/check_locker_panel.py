"""衣柜面板：列出当前场景衣柜里存有衣服的干员并查看其衣物，可偷取全部内裤或袜子，或选择射在衣物上"""

from collections.abc import Callable
from types import FunctionType

from Script.Core import constant, flow_handle
from Script.Core import get_text, py_cmd, text_handle
from Script.Core.game_type import Scene
from Script.Design import attr_text, handle_premise, map_handle
from Script.Modules.domains import activity, identity
from Script.UI.Moudle import draw, panel, view
from Script.Modules.tk_ui import player_pick
from Script.Config import normal_config
from Script.Modules.gameplay_resolution import locker_service as svc

_: FunctionType = get_text._
line_feed = draw.NormalDraw()
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width


def _add(
    text: str,
    ret: str,
    return_list: list[str],
    func: Callable[..., object] | None = None,
    args: object = (),
    kind: type[draw.CenterButton] = draw.CenterButton,
) -> draw.CenterButton:
    """按窗口宽度绘制按钮与换行，将返回值记入列表并返回按钮对象"""
    button = kind(text, ret, window_width, cmd_func=func, args=args)
    button.draw()
    line_feed.draw()
    return_list.append(button.return_text)
    return button


def _left(
    text: str, ret: str, func: Callable[[], None], return_list: list[str]
) -> None:
    """二次翻译文案后绘制无参数左对齐按钮并登记返回值"""
    _add(_(text), ret, return_list, func, (), draw.LeftButton)


def _take(find: "FindDraw", part: int, text: str) -> None:
    """偷取快照末件衣物、清空快照该部位并显示提示文本"""
    held = find.now_locker[part]
    name = svc.steal_last(find.npc_id, find.locker_type, part, held)
    if name is None:
        return
    find.now_locker[part] = []
    now_draw = draw.WaitDraw()
    now_draw.width = window_width
    now_draw.text = text.format(find.character_data.name, name)
    now_draw.draw()


class Check_locker_Panel:
    """当前场景的衣柜检查主面板，列出有衣物干员并提供批量偷取与返回"""

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        self.handle_panel: panel.PageHandlePanel | None = None

    def draw(self) -> None:
        """绘制对象"""
        now_map = map_handle.get_map_for_path(activity.position(0))
        map_name = attr_text.get_map_path_text(now_map)
        site = svc.site_here()
        title_draw = draw.TitleLineDraw(
            _("{0}的衣柜").format(map_name), self.width
        )
        self.handle_panel = panel.PageHandlePanel(
            [], FindDraw, 20, 8, self.width, True, True, 0
        )
        while 1:
            py_cmd.clr_cmd()
            title_draw.draw()
            npc_id_list = svc.owners(site)
            info_draw = draw.NormalDraw()
            if len(npc_id_list):
                info_draw.text = _("\n发现以下衣柜里有衣服\n\n")
            else:
                info_draw.text = _("\n所有衣柜都是空的\n\n")
            info_draw.width = self.width
            info_draw.draw()
            self.handle_panel.text_list = npc_id_list
            self.handle_panel.update()
            self.handle_panel.draw()
            return_list = list(self.handle_panel.return_list)
            line_feed.draw()
            args = (npc_id_list, site.scene)
            if svc.has_part(npc_id_list, site.locker_type, svc.PANTIES):
                _add(
                    _("[偷取所有内裤]"),
                    _("偷取所有内裤"),
                    return_list,
                    self.steal_all_pan,
                    args,
                )
            if svc.has_part(npc_id_list, site.locker_type, svc.SOCKS):
                _add(
                    _("[偷取所有袜子]"),
                    _("偷取所有袜子"),
                    return_list,
                    self.steal_all_socks,
                    args,
                )
            back_draw = _add(_("[返回]"), _("返回"), return_list)
            if flow_handle.askfor_all(return_list) == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def steal_all_pan(self, npc_id_list: list[int], map_data: Scene) -> None:
        """结算：偷取所有内裤"""
        _steal_all(npc_id_list, map_data, svc.PANTIES)

    def steal_all_socks(self, npc_id_list: list[int], map_data: Scene) -> None:
        """结算：偷取所有袜子"""
        _steal_all(npc_id_list, map_data, svc.SOCKS)


def _steal_all(npc_ids: list[int], scene: Scene, part: int) -> None:
    """批量偷取衣柜指定部位衣物并显示收获清单与总数"""
    line = _("获得了{0}的{1}\n")
    total = (
        _("\n已偷取所有人衣柜里的内裤（共{0}件），可在藏品馆里纳入收藏\n"),
        _("\n已偷取所有人衣柜里的袜子（共{0}件），可在藏品馆里纳入收藏\n"),
    )[part == svc.SOCKS]
    stolen = svc.steal_all(npc_ids, scene.scene_tag, part)
    show_text = "\n"
    for one in stolen:
        show_text += line.format(one.owner_name, one.cloth_name)
    now_draw = draw.WaitDraw()
    now_draw.width = window_width
    now_draw.text = show_text + total.format(len(stolen))
    now_draw.draw()


class FindDraw:
    """单个干员衣柜分页按钮，点击进入其衣物详情、闻味道、偷取与射精界面"""

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
        self.character_data = identity.of(npc_id)
        self.pl_data: identity.Identity = identity.of(0)
        self.draw_text: str = ""
        self.width: int = width
        self.num_button: bool = num_button
        self.button_id: int = button_id
        self.button_return: str = str(button_id)
        self.draw_list: list[draw.NormalDraw] = []
        self.locker_type, self.now_locker = svc.locker_here(npc_id)
        self.now_draw: draw.NormalDraw | draw.LeftButton = draw.NormalDraw()
        if is_button and num_button:
            self.draw_text = _("{0}{1}的衣柜").format(
                text_handle.id_index(button_id), self.character_data.name
            )
            self.now_draw = draw.LeftButton(
                self.draw_text,
                self.button_return,
                self.width,
                cmd_func=self.check_cloth,
            )

    def draw(self) -> None:
        """绘制对象"""
        self.now_draw.draw()

    def check_cloth(self) -> None:
        """点击后进入衣服操作子界面"""
        cloth_show_draw = draw.NormalDraw()
        while 1:
            return_list: list[str] = []
            draw.LineDraw("-", window_width).draw()
            cloth_show_text = _("\n{0}的衣柜里放着刚脱下来的：\n").format(
                self.character_data.name
            )
            for part in svc.contents(self.character_data.cid, self.now_locker):
                cloth_show_text += "".join(f" {n}" for n in part.cloth_names)
                if part.semen:
                    cloth_show_text += _("({0}ml精液)").format(part.semen)
            cloth_show_draw.text = cloth_show_text + "\n\n"
            cloth_show_draw.draw()
            line_feed.draw()
            _left(
                _("[001]把内衣拿起来闻一闻味道"),
                _("1"),
                self.smell,
                return_list,
            )
            if len(self.now_locker[svc.PANTIES]) > 0:
                _left(_("[002]偷走内裤"), _("2"), self.get_pan, return_list)
            if len(self.now_locker[svc.SOCKS]) > 0:
                _left(_("[003]偷走袜子"), _("3"), self.get_socks, return_list)
            if handle_premise.handle_pl_semen_g_2(0):
                _left(
                    _("[004]用衣服冲，射在上面"),
                    _("4"),
                    self.shoot_in_cloth,
                    return_list,
                )
            back_draw = _add(_("[返回]"), _("返回"), return_list)
            if flow_handle.askfor_all(return_list) == back_draw.return_text:
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
        _take(self, svc.PANTIES, _("\n获得了{0}的{1}，可在藏品馆里纳入收藏\n"))

    def get_socks(self) -> None:
        """偷袜子"""
        _take(self, svc.SOCKS, _("\n获得了{0}的{1}，可在藏品馆里纳入收藏\n"))

    def shoot_in_cloth(self) -> None:
        """射在衣服上"""
        shoot_in_cloth_panel = panel.PageHandlePanel(
            [], Ejaculation_NameDraw, 20, 1, window_width, True, True, 0
        )
        while 1:
            line_feed.draw()
            draw.LineDraw("-", window_width).draw()
            shoot_in_cloth_panel.text_list = [
                [part, self.npc_id]
                for part in svc.filled_parts(self.now_locker)
            ]
            shoot_in_cloth_panel.update()
            shoot_in_cloth_panel.draw()
            return_list = list(shoot_in_cloth_panel.return_list)
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            if flow_handle.askfor_all(return_list) == back_draw.return_text:
                break


class Ejaculation_NameDraw:
    """单个非空衣物部位分页按钮，点击提交该部位的衣柜射精具名编辑"""

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
        self.npc_id = text[1]
        self.draw_text: str = ""
        self.width: int = width
        self.num_button: bool = num_button
        self.button_id: int = button_id
        self.button_return: str = str(button_id)
        self.locker_type = svc.site_here().locker_type
        option = svc.shoot_option(self.npc_id, self.locker_type, self.index)
        if is_button and num_button:
            index_text = text_handle.id_index(button_id)
            self.draw_text = f"{index_text} {option.label}"
            if option.semen != 0:
                self.draw_text += _(" ({0}ml精液)").format(str(option.semen))
            self.now_draw = draw.LeftButton(
                self.draw_text,
                self.button_return,
                self.width,
                cmd_func=self.shoot_here,
            )

    def draw(self) -> None:
        """绘制对象"""
        self.now_draw.draw()

    def shoot_here(self) -> None:
        """清除当前命令，定下射在该干员衣柜里这一衣物类型上的具名编辑"""
        py_cmd.clr_cmd()
        player_pick.commit_edit(
            svc.SHOOT_EDIT,
            svc.shoot_args(self.index, self.locker_type, self.npc_id),
        )
