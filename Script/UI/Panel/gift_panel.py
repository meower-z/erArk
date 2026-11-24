"""赠送礼物的界面面板模块，提供 Gift_Panel 面板类以及模块级换行绘制对象 line_feed 与窗口宽度 window_width。"""

from types import FunctionType
from Script.UI.Moudle import draw, view
from Script.Core import constant, flow_handle
from Script.Core import get_text
from Script.Config import normal_config
from Script.Modules.domains import activity
from Script.Modules.domains import identity
from Script.Modules.gameplay_resolution import gift_service

_: FunctionType = get_text._
""" 翻译api """

line_feed = draw.NormalDraw()
line_feed.text = "\n"
line_feed.width = 1
window_width = normal_config.config_normal.text_width


def _passes(reason: str | None) -> bool:
    """
    根据阻止原因返回是否放行的布尔值。
    当 reason 不为 None 时绘制一条等待确认的提示文本。
    Keyword arguments:
    reason -- str | None，阻止原因文本，None 表示允许通过
    Return arguments:
    bool -- reason 为 None 时返回 True，否则返回 False
    """
    if reason is None:
        return True
    now_draw = draw.WaitDraw()
    now_draw.text = reason
    now_draw.draw()
    return False


class Gift_Panel:
    """
    用于赠送礼物的面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """
        初始化绘制对象
        参数：
            width (int): 绘制的最大宽度
        返回值：
            None
        """
        self.width: int = width
        """ 绘制的最大宽度 """
        self.show_drug_gift: bool = False
        """ 药物类礼物的展开状态标志，False 为收起，True 为展开 """

    def toggle_drug_gift(self) -> None:
        """
        切换药物类礼物的展开/收起状态
        参数：无
        返回值：无
        """
        self.show_drug_gift = not self.show_drug_gift

    def draw(self) -> None:
        """
        绘制对象
        参数：无
        返回值：无
        """
        title_text = _("赠送礼物")
        title_draw = draw.TitleLineDraw(title_text, self.width)
        while 1:
            return_list = []
            title_draw.draw()
            for entry in gift_service.gift_menu(self.show_drug_gift):
                if isinstance(entry, gift_service.DrugToggle):
                    button_draw = draw.LeftButton(
                        _(entry.text),
                        _(entry.text),
                        self.width,
                        cmd_func=self.toggle_drug_gift,
                        args=(),
                    )
                    return_list.append(button_draw.return_text)
                    button_draw.draw()
                elif entry.selectable:
                    button_draw = draw.LeftButton(
                        _(entry.text),
                        _(str(entry.gift_id)),
                        self.width,
                        cmd_func=self.select_gift,
                        args=(entry.gift_id,),
                    )
                    return_list.append(button_draw.return_text)
                    button_draw.draw()
                else:
                    text_draw = draw.NormalDraw()
                    text_draw.text = entry.text
                    text_draw.style = "deep_gray"
                    text_draw.draw()
                line_feed.draw()
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

    def select_gift(self, gift_id: int) -> None:
        """礼物的确认选择"""
        from Script.System.Instruct_System import handle_instruct
        from Script.System.Pregnancy_System import pregnancy_handle

        if not self.check_gift_available(gift_id):
            return
        fields: dict[str, object] = {"behavior.gift_id": gift_id}
        if gift_id == 36:
            egg_id = self.select_target_egg()
            if egg_id is None:
                return
            fields["behavior.gift_egg_id"] = egg_id
        if gift_id == 39 and not pregnancy_handle.is_growth_drug_self_target(
            activity.target(0)
        ):
            child_id = self.select_target_baby()
            if child_id is None:
                return
            fields["behavior.gift_child_id"] = child_id
        handle_instruct.chara_handle_instruct_common_settle(
            constant.Behavior.GIVE_GIFT,
            judge=gift_service.gift_judge(gift_id),
            force_taget_wait=True,
            fields=fields,
        )

    def select_target_egg(self) -> int | None:
        """
        孵化加速药的选卵交互：绘制交互对象全部可加速的孵化中卵供玩家选择\n
        仅一枚可加速卵时跳过选择直接选中\n
        Returns:\n
        int | None -- 选中的卵编号（None为玩家取消或无可选卵）
        """
        pick = gift_service.egg_pick(identity.of(activity.target(0)).cid)
        if not pick.options:
            return pick.chosen
        return self._pick(pick.options, _("选择要加速孵化的卵"), _("返回选卵"))

    def select_target_baby(self) -> int | None:
        """
        成长加速药的选婴儿交互：绘制交互对象名下全部可加速的婴儿供玩家选择\n
        仅一名可加速婴儿时跳过选择直接选中\n
        Returns:\n
        int | None -- 选中的婴儿角色id（None为玩家取消或无可选婴儿）
        """
        pick = gift_service.baby_pick(identity.of(activity.target(0)).cid)
        if not pick.options:
            return pick.chosen
        return self._pick(
            pick.options, _("选择要加速成长的婴儿"), _("返回选婴儿")
        )

    def _pick(
        self,
        options: tuple[gift_service.PickOption, ...],
        title: str,
        back_text: str,
    ) -> int | None:
        """
        绘制候选选项列表与返回按钮，并等待玩家选择一项或返回。
        Keyword arguments:
        options -- tuple[gift_service.PickOption, ...]，待绘制的候选按钮元组
        title -- str，列表标题文本
        back_text -- str，返回按钮的回传文本
        Return arguments:
        int | None -- 选中项的整型编号，选择返回时为 None
        """
        draw.TitleLineDraw(title, self.width).draw()
        return_list = []
        for option in options:
            button_draw = draw.LeftButton(
                option.text, str(option.choice_id), self.width
            )
            return_list.append(button_draw.return_text)
            button_draw.draw()
            line_feed.draw()
        line_feed.draw()
        back_draw = draw.CenterButton(_("[返回]"), back_text, window_width)
        back_draw.draw()
        line_feed.draw()
        return_list.append(back_draw.return_text)
        yrn = flow_handle.askfor_all(return_list)
        if yrn == back_draw.return_text:
            return None
        return int(yrn)

    def check_gift_available(self, gift_id: int) -> bool:
        """
        检查是否可以赠送礼物\n
        Keyword arguments:\n
        gift_id -- 礼物ID\n
        Returns:\n
        bool -- 是否可以赠送\n
        """
        target = identity.of(activity.target(0))
        return _passes(gift_service.gift_block_reason(gift_id, target))

    def is_drug_effective(
        self, drug_id: int, target_character_data: identity.Identity
    ) -> bool:
        """
        检查药物是否对目标角色有效
        Keyword arguments:
        drug_id -- 药物ID
        target_character_data -- 目标角色数据
        """
        reason = gift_service.drug_block_reason(drug_id, target_character_data)
        return _passes(reason)
