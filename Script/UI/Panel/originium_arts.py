"""
源石技艺面板，与降低负面素质的面板
"""

from types import FunctionType
from Script.Core import get_text, flow_handle, constant
from Script.UI.Moudle import draw, view
from Script.Config import game_config, normal_config
from Script.Modules.domains import identity, modes
from Script.Modules.gameplay_resolution import originium_arts_service
from Script.Modules.gameplay_resolution import originium_arts_panel_service

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


class Originium_Arts_Panel:
    """
    用于源石技艺的面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.pl_character_data = identity.of(0)
        """ 玩家的属性 """

    def _menu_button(
        self, entry: originium_arts_panel_service.ArtMenuEntry
    ) -> draw.LeftButton:
        """
        将单条主菜单条目映射为对应的左对齐按钮对象，补齐翻译文案、默认催眠类型、理智消耗与点击回调。
        Keyword arguments:
        entry -- originium_arts_panel_service.ArtMenuEntry，主菜单条目数据
        Return arguments:
        draw.LeftButton -- 配置完成的菜单按钮绘制对象
        """
        texts = {
            1: (_("[001]消除负面刻印"), _("1")),
            2: (_("[002]时间系能力："), _("2")),
            3: (_("[003]催眠系能力："), _("3")),
            4: (_("[004]自我强化(未实装)"), _("4")),
            5: (_("[005]激素系能力："), _("5")),
            6: (_("[006]视觉系能力："), _("6")),
            7: (_("[007]触觉系能力(未实装)"), _("7")),
            11: (_("[011]能力获得与升级"), _("11")),
            12: (_("[012]Re:败者食尘"), _("12")),
        }
        actions = {
            1: (Down_Negative_Talent_Panel(self.width).draw, ()),
            4: (self.to_do, ()),
            7: (self.to_do, 7),
            11: (self.gain_and_upgrade_ability, ()),
            12: (self.new_round_for_sure, ()),
        }
        text, return_text = texts[entry.key]
        text += entry.talent_names
        if entry.key == 3:
            type_id = originium_arts_service.get_hypnosis_type(
                self.pl_character_data.cid
            )
            type_name = game_config.config_hypnosis_type[type_id].name
            text += _("当前默认催眠类型：{0}").format(type_name)
        if entry.sanity_per_hour is not None:
            text += _("({0}理智/h)").format(entry.sanity_per_hour)
        cmd_func, args = actions.get(entry.key, (self.arts_show, entry.key))
        return draw.LeftButton(
            _(text), return_text, window_width, cmd_func=cmd_func, args=args
        )

    def draw(self) -> None:
        """绘制对象"""
        title_draw = draw.TitleLineDraw(_("源石技艺"), self.width)
        while 1:
            return_list = []
            title_draw.draw()
            cinfo_draw = draw.NormalDraw()
            cinfo_draw.text = _("\n要使用哪一个源石技艺呢？\n")
            cinfo_draw.draw()
            for entry in originium_arts_panel_service.menu_entries():
                button_draw = self._menu_button(entry)
                line_feed.draw()
                button_draw.draw()
                return_list.append(button_draw.return_text)
            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text or yrn == "12":
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def to_do(self, n: object) -> None:
        """暂未实装"""

        now_draw = draw.WaitDraw()
        now_draw.width = window_width
        now_draw.text = _("\n暂未实装\n")
        now_draw.draw()

    def arts_show(self, ability_type: int) -> None:
        """源石技艺展示"""
        if ability_type == 3:
            from Script.UI.Panel import hypnosis_panel

            now_panel = hypnosis_panel.Chose_Hypnosis_Type_Panel(self.width)
            now_panel.draw()
            return
        line_draw = draw.LineDraw("-", self.width)
        line_draw.draw()
        while 1:
            headers = {
                2: _("\n时间系能力（消耗2理智/min）：\n"),
                5: _("\n激素系能力（不消耗理智）：\n"),
                6: _("\n视觉系能力（每级消耗5理智/h）：\n"),
            }
            info_draw = draw.NormalDraw()
            info_draw.text = _(headers[ability_type])
            info_draw.draw()
            for row in originium_arts_panel_service.group_rows(ability_type):
                draw_text = f"  {row.name}：{row.info}\n"
                now_draw = draw.NormalDraw()
                if not row.unlocked:
                    draw_text = _("  {0}(未解锁)：{1}\n").format(
                        row.name, row.info
                    )
                    now_draw.style = "deep_gray"
                now_draw.text = _(draw_text)
                now_draw.draw()
            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list = [back_draw.return_text]
            yrn = flow_handle.askfor_all(return_list)
            if yrn in return_list:
                break

    def draw_lv_up_button(
        self, condition: bool, draw_text: str, cid: int, return_list: list[str]
    ) -> list[str]:
        """绘制升级按钮"""
        now_draw: draw.LeftButton | draw.NormalDraw
        if condition:
            now_draw = draw.LeftButton(
                _(draw_text),
                _(str(cid) + "1"),
                window_width,
                cmd_func=self.gain_and_upgrade_ability_which,
                args=(cid, True),
            )
            return_list.append(now_draw.return_text)
            now_draw.draw()
        else:
            now_draw = draw.NormalDraw()
            now_draw.text = _(draw_text)
            now_draw.style = "deep_gray"
            now_draw.draw()
        line_feed.draw()
        return return_list

    def _format_condition_text(
        self, condition: originium_arts_service.ArtConditionProgress
    ) -> str:
        """按条件类型将解锁进度格式化为界面展示文案。"""
        templates = {
            "max_favorability_trust": _(
                "：需要单干员最高好感度≥{0}（当前{1}），最高信赖度≥{2}（当前{3}）"
            ),
            "total_favorability_fall": _(
                "：需要全干员总好感度≥{0}（当前{1}），已进入任意陷落路线的干员人数≥{2}（当前{3}）"
            ),
            "total_favorability_deep_fall": _(
                "：需要全干员总好感度≥{0}（当前{1}），陷落程度为[爱侣]或[奴隶]的干员人数≥{2}（当前{3}）"
            ),
            "panty_collection_total": _(
                "：需要全干员内裤收藏总数量≥{0}（当前{1}）"
            ),
            "internal_semen_orgasm_exp": _(
                "：需要全干员的体内部位被射精总量≥{0}ml（当前{1}ml），全干员总绝顶经验≥{2}（当前{3}）"
            ),
            "child_count": _("：需要生育孩子数量≥{0}（当前{1}）"),
            "unconscious_sex_orgasm_exp": _(
                "：需要全干员无意识性交经验≥{0}（当前{1}），全干员总无意识绝顶经验≥{2}（当前{3}）"
            ),
            "time_stop_sex_orgasm_exp": _(
                "：需要对干员的时姦经验≥{0}（当前{1}），全干员总无意识绝顶经验≥{2}（当前{3}）"
            ),
            "sleep_sex_exp": _("：需要对干员的睡姦经验≥{0}（当前{1}）"),
        }
        template = templates.get(
            condition.kind,
            _(
                "：需要博士催眠经验≥{0}（当前{1}），需要全干员总催眠深度≥{2}%（当前{3}%）"
            ),
        )
        return template.format(
            condition.required_primary,
            condition.current_primary,
            condition.required_secondary,
            condition.current_secondary,
        )

    def gain_and_upgrade_ability(self) -> None:
        """能力获得与升级"""
        while 1:
            return_list: list[str] = []
            line_draw = draw.LineDraw("-", self.width)
            line_draw.draw()
            info_draw = draw.NormalDraw()
            info_text = _(
                "\n能力可以直接消耗至纯源石或满足特定条件解锁，当前至纯源石：{0}\n"
            ).format(originium_arts_service.originite_prime_amount())
            info_text += _("\n当前可以获得/升级的能力有：\n\n")
            info_draw.text = _(info_text)
            info_draw.draw()
            now_draw: draw.NormalDraw | draw.LeftButton
            for option in originium_arts_service.list_upgradeable_arts():
                talent_name = game_config.config_talent[option.talent_id].name
                talent_info = game_config.config_talent[option.talent_id].info
                draw_text = f"  [{talent_name}]"
                if option.todo:
                    now_draw = draw.NormalDraw()
                    draw_text += _("(未实装)：{0}\n").format(talent_info)
                    now_draw.text = _(draw_text)
                    now_draw.style = "deep_gray"
                    now_draw.draw()
                elif not option.can_buy_with_prime:
                    now_draw = draw.NormalDraw()
                    draw_text += _("({0}至纯源石-当前源石不足)：{1}\n").format(
                        option.money_cost, talent_info
                    )
                    now_draw.text = _(draw_text)
                    now_draw.style = "deep_gray"
                    now_draw.draw()
                else:
                    draw_text += _("( {0} 至纯源石)：{1}").format(
                        option.money_cost, talent_info
                    )
                    now_draw = draw.LeftButton(
                        _(draw_text),
                        _(str(option.cid)),
                        window_width,
                        cmd_func=self.gain_and_upgrade_ability_which,
                        args=(option.cid,),
                    )
                    return_list.append(now_draw.return_text)
                    now_draw.draw()
                    line_feed.draw()

                if option.condition is not None:
                    cond_text = (
                        f"  [{talent_name}]"
                        f"{self._format_condition_text(option.condition)}"
                    )
                    return_list = self.draw_lv_up_button(
                        option.condition.satisfied,
                        cond_text,
                        option.cid,
                        return_list,
                    )
            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                break

    def change_hypnosis_type(self, hypnosis_type_cid: int) -> None:
        """改变当前的催眠类型"""
        originium_arts_service.set_hypnosis_type(
            hypnosis_type_cid, character_id=self.pl_character_data.cid
        )

    def gain_and_upgrade_ability_which(
        self, cid: int, no_cost_flag: bool = False
    ) -> None:
        """获得或升级能力"""
        result = originium_arts_service.learn_or_upgrade_art(
            cid, no_cost_flag=no_cost_flag
        )
        if not result.success:
            return
        talent_name = game_config.config_talent[result.talent_id].name
        info_text = _("\n习得了{0}\n").format(talent_name)
        info_draw = draw.WaitDraw()
        info_draw.text = _(info_text)
        info_draw.draw()

    def new_round_for_sure(self) -> None:
        """确认开始新的周目"""
        from Script.UI.Panel import new_round

        while 1:
            line_draw = draw.LineDraw("-", self.width)
            line_draw.draw()
            now_draw = draw.NormalDraw()
            now_draw.width = window_width
            now_draw.text = _(
                "\n你可以继承目前的部分数据，从头开始一个全新的周目，重新做出不一样的抉择，体验不一样的风景\n"
            )
            now_draw.text += _("此选择不可撤销，请备份好存档，谨慎决定\n")
            now_draw.text += _("\n\n\n确定开始新的周目吗？\n\n\n\n")
            now_draw.draw()
            return_list = []
            yes_draw = draw.CenterButton(_("[是]"), _("是"), window_width / 2)
            yes_draw.draw()
            return_list.append(yes_draw.return_text)
            no_draw = draw.CenterButton(_("[否]"), _("否"), window_width / 2)
            no_draw.draw()
            return_list.append(no_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == yes_draw.return_text:
                now_panel = new_round.New_Round_Handle()
                now_panel.draw()
                break
            elif yrn == no_draw.return_text:
                break


class Down_Negative_Talent_Panel:
    """
    用于降低负面素质的面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """

    def draw(self) -> None:
        """绘制对象"""
        while 1:
            return_list = []
            info_draw = draw.NormalDraw()
            info_text = _(
                "\n当前拥有苦痛刻印、反发刻印或恐怖刻印的角色有：\n\n"
            )
            info_draw.text = info_text
            info_draw.draw()

            eligible_ids = (
                originium_arts_service.list_negative_mark_characters()
            )
            for chara_id in eligible_ids:
                character_data = identity.of(chara_id)
                name = character_data.name
                adv_id = character_data.adv
                button_text = f"[{str(adv_id).rjust(4, '0')}]:{name} "
                button_draw = draw.LeftButton(
                    _(button_text),
                    _(str(adv_id)),
                    self.width,
                    cmd_func=self.choice_down_which,
                    args=(chara_id,),
                )
                return_list.append(button_draw.return_text)
                button_draw.draw()
                line_feed.draw()

            if not eligible_ids:
                info_draw = draw.NormalDraw()
                info_text = _("  没有符合条件的角色\n")
                info_draw.text = info_text
                info_draw.draw()

            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                break

    def choice_down_which(self, chara_id: int) -> None:
        """选择降低哪一个"""
        character_data = identity.of(chara_id)
        self.chara_id = chara_id
        name = character_data.name

        while 1:
            return_list = []
            info_draw = draw.NormalDraw()
            panties_count = originium_arts_service.get_npc_panties_count(
                self.chara_id
            )
            info_text = _(
                "\n要降低[{0}]的哪个刻印呢？(需要消耗该角色已收藏至藏品馆的5条内裤，当前共{1}条，优先消耗重复款式)\n\n"
            ).format(name, panties_count)
            if modes.debug():
                info_text += _("当前为debug模式，不需要消耗内裤\n\n")
            info_draw.text = info_text
            info_draw.draw()

            for (
                ability_id,
                ability_lv,
            ) in originium_arts_service.list_character_negative_marks(chara_id):
                ability_name = game_config.config_ability[ability_id].name
                button_text = f"  {ability_name}[lv{ability_lv}]"
                button_draw = draw.LeftButton(
                    _(button_text),
                    _(str(ability_id)),
                    self.width,
                    cmd_func=self.settle_down,
                    args=(ability_id,),
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
                break

    def settle_down(self, ability_id: int) -> None:
        """结算刻印降低"""
        info_draw = draw.NormalDraw()
        character_data = identity.of(self.chara_id)
        result = originium_arts_service.reduce_negative_mark(
            character_data.cid, ability_id
        )
        if result.success:
            info_text = _("  随着一阵火焰，5条内裤化为一缕青烟，消散在空中\n")
            info_text += _(
                "  {0}感觉心里轻松了很多，对{1}的印象有些改观了，{2}下降到了{3}级\n"
            ).format(
                character_data.name,
                identity.of(0).name,
                game_config.config_ability[ability_id].name,
                result.new_level,
            )
        else:
            info_text = _("  内裤数量不足\n")
        info_draw.text = info_text
        info_draw.draw()
        line = draw.LineDraw("-", self.width)
        line.draw()
