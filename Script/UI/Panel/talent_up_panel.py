"""
角色素质升级显示面板
"""

from types import FunctionType
from typing import NoReturn

from Script.Config import game_config
from Script.Core import constant, get_text
from Script.Modules.gameplay_resolution import talent_up_service
from Script.Modules.tk_ui import player_pick
from Script.UI.Moudle import draw

_: FunctionType = get_text._
""" 翻译api """

line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1


def _prerequisite_label(kind: talent_up_service.PrereqKind) -> str:
    """将前提条件语义标识映射为对应的界面展示文案。"""
    if kind == "favorability":
        return _(" 好感度500以上")
    if kind == "trust":
        return _(" 信任度50%以上")
    if kind == "hate_mark":
        return _(" 反发刻印0")
    if kind == "pain_mark":
        return _(" 苦痛刻印0")
    if kind == "fear_mark":
        return _(" 恐怖刻印0")
    if kind == "intimacy":
        return _(" 亲密等级至少为2")
    if kind == "pleasure_mark":
        return _(" 快乐刻印>=1")
    if kind == "submission_mark":
        return _(" 屈服刻印>=1")
    return _(" 顺从等级至少为2")


def _requirement_label(req: talent_up_service.TalentRequirementCheck) -> str:
    """将单条素质获取需求渲染为对应的界面展示文案。"""
    if req.kind == "A":
        abi_name = game_config.config_ability[req.target_id].name
        return _("  需要能力[{0}]至少为 {1}\n").format(
            abi_name, str(req.required)
        )
    if req.kind == "T":
        tal_name = game_config.config_talent[req.target_id].name
        return _("  需要素质[{0}]\n").format(tal_name)
    if req.kind == "J":
        juel_name = game_config.config_juel[req.target_id].name
        return _("  需要宝珠[{0}]至少为 {1}\n").format(
            juel_name, str(req.required)
        )
    if req.kind == "E":
        exp_name = game_config.config_experience[req.target_id].name
        return _("  需要经验[{0}]至少为 {1}\n").format(
            exp_name, str(req.required)
        )
    if req.kind == "F":
        return _("  需要好感至少为 {0}\n").format(str(req.required))
    if req.kind == "X":
        return _("  需要信赖至少为 {0}\n").format(str(req.required))
    return ""


class Character_talent_show_Text:
    """
    角色素质升级显示面板
    Keyword arguments:
    character_id -- 角色id
    width -- 最大宽度
    """

    def __init__(self, character_id: int, width: int) -> None:
        """初始化绘制对象"""
        self.character_id = character_id
        """ 绘制的角色id """
        self.width = width
        """ 当前最大可绘制宽度 """
        self.return_list: list[str] = []
        """ 监听的按钮列表 """

    def _draw_text(self, text: str) -> None:
        """按默认样式绘制一段普通文本。"""
        text_draw = draw.NormalDraw()
        text_draw.text = text
        text_draw.draw()

    def _draw_condition(
        self, text: str, is_met: bool, show_suffix: bool = True
    ) -> bool:
        """
        通用判断与绘制函数：自动根据判定结果改色并附加(√)/(X)
        返回 is_met 以便调用方复用判定结果
        """
        cond_draw = draw.NormalDraw()
        if is_met:
            cond_draw.text = f"{text}(√)" if show_suffix else text
            cond_draw.style = "green"
        else:
            cond_draw.text = f"{text}(X)" if show_suffix else text
            cond_draw.style = "warning"
        cond_draw.draw()
        return is_met

    def _draw_confirm_button(self, talent_id: int) -> None:
        """绘制素质获取确认按钮并登记监听返回文本。"""
        yes_draw = draw.CenterButton(
            _("[确定]"),
            _("确定") + "_" + str(talent_id),
            self.width / 3,
            cmd_func=self.level_up,
            args=talent_id,
        )
        yes_draw.draw()
        self.return_list.append(yes_draw.return_text)
        line_feed.draw()

    def _render_gain_evaluation(
        self, evaluation: talent_up_service.TalentGainEvaluation
    ) -> None:
        """按素质获取评估结果绘制下一级素质名称、需求明细与操作区。"""
        talent_id = evaluation.talent_id
        talent_name = game_config.config_talent[talent_id].name
        self._draw_text(_("下一级为：[{0}]\n").format(talent_name))

        for req in evaluation.requirements:
            self._draw_condition(
                _requirement_label(req), req.met, show_suffix=False
            )

        mode = evaluation.action_mode
        if mode == "route_confirm":
            line_feed.draw()
            self._draw_text(_("满足条件，确定选择此路线吗？\n"))
            self._draw_confirm_button(talent_id)
        elif mode == "route_blocked":
            line_feed.draw()
            self._draw_text(_("不满足条件，无法选择\n"))
        elif mode == "ring_confession":
            line_feed.draw()
            self._draw_text(
                _(
                    "满足条件后需要准备【戒指】，然后进行【告白】，成功后即可获得\n"
                )
            )
        elif mode == "collar_equip":
            line_feed.draw()
            self._draw_text(
                _(
                    "满足条件后需要准备【项圈】，然后进行【戴上项圈】，成功后即可获得\n"
                )
            )
        elif mode == "upgrade_confirm":
            self._draw_text(
                _(
                    "\n满足条件，确定要现在获得该素质吗（也可以在过夜时自动获得）\n"
                )
            )
            self._draw_confirm_button(talent_id)

    def _render_route(self, route: talent_up_service.FallRouteStatus) -> None:
        """绘制单条可见陷落路线的前提条件及下一阶段或满级信息。"""
        draw.LineDraw("-", self.width).draw()
        if route.route == "love":
            self._draw_text(_("爱情路线前提："))
        else:
            self._draw_text(_("隶属路线前提："))

        for check in route.prerequisites:
            self._draw_condition(_prerequisite_label(check.kind), check.met)

        line_feed.draw()
        if route.is_max_level:
            if route.route == "love":
                self._draw_text(_("已达到最高级-爱侣\n"))
            else:
                self._draw_text(_("已达到最高级-奴隶\n"))
        elif route.next_gain is not None:
            self._render_gain_evaluation(route.next_gain)

    def draw(self) -> None:
        """绘制对象"""
        self.return_list = []
        overview = talent_up_service.build_talent_upgrade_overview(
            self.character_id
        )
        line_feed.draw()
        draw.LittleTitleLineDraw("素质", self.width, ":").draw()
        self._draw_text(_("陷落系素质\n 共通基础前提："))

        for check in overview.common_prerequisites:
            self._draw_condition(_prerequisite_label(check.kind), check.met)

        self._draw_text(
            _(
                "\n 分为爱情系与隶属系两条路线，只能任选其一，选择后另一路线消失，仅在新周目时可以重置\n"
            )
        )

        if overview.love_route is not None:
            self._render_route(overview.love_route)
        if overview.obey_route is not None:
            self._render_route(overview.obey_route)

    def show_gain_need(self, talent_id: int, judge: int) -> None:
        """具体显示需要什么"""
        evaluation = talent_up_service.evaluate_talent_gain(
            self.character_id, talent_id, route_ok=bool(judge)
        )
        self._render_gain_evaluation(evaluation)

    def level_up(self, talent_id: int) -> NoReturn:
        """
        定下获得该素质：1 分钟的等待，开始时由 panel_starters 的 talent_up 提示选择成功并以手动获得类型结算该素质
        Keyword arguments:
        talent_id -- 素质id
        """
        player_pick.choose(
            constant.Behavior.WAIT,
            1,
            kind="talent_up",
            state=constant.CharacterStatus.STATUS_WAIT,
            args={"character_id": self.character_id, "talent_id": talent_id},
        )
