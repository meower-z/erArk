"""多周目点数结算面板：负责界面绘制、玩家交互、重置入口与唤醒报告展示。"""

from collections.abc import Callable, Mapping
from types import FunctionType
from Script.Core import flow_handle, get_text
from Script.UI.Moudle import draw, panel
from Script.UI.Panel import see_character_info_panel
from Script.Config import normal_config, game_config
from Script.Kernel import core
from Script.Modules.save_load import kernel_state
from Script.Modules.domains import abilities, identity, playthrough, roster
from Script.Modules.gameplay_resolution import new_round_inherit_service
from Script.Modules.gameplay_resolution import new_round_service as svc

_: FunctionType = get_text._
""" 翻译api """
width = normal_config.config_normal.text_width
""" 屏幕宽度 """
line_feed_draw = draw.NormalDraw()
""" 绘制换行对象 """
line_feed_draw.text = "\n"
line = draw.LineDraw("=", width)
""" 标题线绘制对象 """
awakening: tuple[str, tuple[int, ...]] = ("", ())
""" setup 暂存的新周目唤醒数据：(继承报告文本, 新达成成就 ID 元组)，供 start_new_round 换态后绘制。 """


class New_Round_Handle:
    """周目点数结算面板控制器，管理继承等级选择与新周目启动交互。"""

    def __init__(self) -> None:
        """初始化绘制对象"""
        self.width = normal_config.config_normal.text_width
        """ 屏幕宽度 """
        self.return_list: list[str] = []
        """ 当前面板监听的按钮列表 """
        self.levels = [0] * len(svc.KEYS)
        """ 按继承类型编号 0 至 6 排列的当前继承等级列表。 """
        self.show_npc_flag = False
        """ 干员显示 """
        self.show_panel_flag_list = [False, False]
        """ 源石技艺与博士能力经验两块详情区的展开标志列表。 """
        self.all_fall_chara_list: list[int] = []
        """ 所有陷落干员列表 """
        self.farewell_npc_id = 0
        """ 送别干员id """
        self.show_world_setting = False
        """ 显示世界设定面板 """
        self.world_setting: dict[int, int] = playthrough.settings(
            playthrough.WORLD
        )
        """ 新周目的世界设定：设定id -> 是否选择 """

    def _text(self, text: str) -> None:
        """按面板宽度绘制普通文本块。"""
        info_draw = draw.NormalDraw()
        info_draw.width = self.width
        info_draw.text = text
        info_draw.draw()

    def _toggle(
        self,
        text: str,
        flag: bool,
        func: Callable[..., None],
        args: tuple[int, ...] = (),
    ) -> None:
        """绘制带展开箭头的折叠按钮并加入监听列表。"""
        text += "▼" if flag else "▶"
        button = draw.LeftButton(
            text, text, len(text) * 2, cmd_func=func, args=args
        )
        self.return_list.append(text)
        button.draw()

    def _level_row(self, type_id: int, head: str, cost: int) -> int:
        """绘制单项继承等级行及提高与降低按钮并返回继承比例。"""
        level = self.levels[type_id]
        now_rate = svc.rate(type_id, level)
        self._text(
            head
            + _("\n   当前继承等级{0}，继承比例{1}%，点数消耗{2}\n  ").format(
                level, now_rate, cost
            )
        )
        for delta, text in ((1, _(" [提高] ")), (-1, _(" [降低] "))):
            button = draw.CenterButton(
                text,
                text + f"_{type_id}",
                len(text) * 2,
                cmd_func=self.value_change_buton,
                args=(delta, type_id),
            )
            self.return_list.append(button.return_text)
            button.draw()
        line_feed_draw.draw()
        return now_rate

    def _points(self, points: svc.Points) -> None:
        """绘制周目、陷落干员与收藏品点数统计并更新陷落列表。"""
        self._text(
            "\n"
            + _("当前周目数：{0}(+{1})\n\n").format(
                points.game_round, points.round_point
            )
        )
        self.all_fall_chara_list = [row.chara_id for row in points.fallen]
        self._toggle(_("○全陷落干员"), self.show_npc_flag, self.show_npc_change)
        info_text = "\n"
        for count, row in enumerate(points.fallen, 1):
            if self.show_npc_flag:
                name = identity.of(row.chara_id).name.rjust(6, "　")
                talent_name = game_config.config_talent[row.talent_id].name
                info_text += f"  {name}-{talent_name}(+{row.point})"
                if count % 8 == 0:
                    info_text += "\n"
        if self.show_npc_flag:
            info_text += "\n"
        info_text += _("  陷落干员总数：{0}，总点数：{1}\n\n").format(
            len(points.fallen), points.fallen_point
        )
        self._text(info_text)
        self._text(
            _("○全收藏品")
            + _("全干员内裤共{0}条，全干员袜子共{1}双，总点数{2}\n\n").format(
                points.panties, points.socks, points.collection_point
            )
        )
        if points.debug:
            self._text(_("debug模式+9999\n\n").format(points.total))
        self._text(_("总周目点数：{0}\n\n").format(points.total))

    def draw(self) -> None:
        """绘制面板"""
        while 1:
            title_draw = draw.TitleLineDraw(_("周目点数结算"), self.width)
            title_draw.draw()
            self.return_list = []
            points = svc.points()
            self._points(points)
            costs = [svc.cost(i, lv) for i, lv in enumerate(self.levels)]
            flags = self.show_panel_flag_list
            func = self.show_panel_change
            self._toggle(_("[0]博士的源石技艺"), flags[0], func, (0,))
            self._level_row(0, "", costs[0])
            if flags[0]:
                see_character_info_panel.PlayerAbilityText(
                    0, self.width, 8
                ).draw()
            line_feed_draw.draw()
            self._toggle(_("[1]博士的能力与经验"), flags[1], func, (1,))
            now_rate = self._level_row(1, "", costs[1])
            if flags[1]:
                abi_draw = CharacterabiText(0, self.width, now_rate)
                exp_draw = CharacterExperienceText(0, self.width, 8, now_rate)
                abi_draw.draw()
                exp_draw.draw()
            line_feed_draw.draw()
            now_rate = self._level_row(2, _("[2]博士的属性上限成长"), costs[2])
            self._text(
                _(
                    "  属性上限成长：当前体力上限{0}(→{1})，气力上限{2}(→{3})，理智上限{4}(→{5})，精液上限{6}(→{7})\n\n"
                ).format(*svc.growth_preview(now_rate))
            )
            now_rate = self._level_row(3, _("[3]博士的收藏品"), costs[3])
            self._text(
                _(
                    "  收藏品统计：当前内裤{0}(→{1})条，袜子{2}(→{3})双\n\n"
                ).format(
                    points.panties,
                    int(points.panties * now_rate / 100),
                    points.socks,
                    int(points.socks * now_rate / 100),
                )
            )
            self._text(
                _("已陷落干员将直接继承至新的周目，无需重新招募\n")
                + _(
                    "耗费点数可以进一步继承这些干员一定比例的好感、信赖、能力、经验\n"
                )
                + _("\n[4]干员的好感与信任")
            )
            self._level_row(4, "", costs[4])
            self._text(_("\n[5]干员的能力与经验"))
            self._level_row(5, "", costs[5])
            self._text(_("\n[6]干员的催眠进度"))
            self._level_row(6, "", costs[6])
            self._text(
                _("\n总点数消耗：{0}，剩余：{1}\n").format(
                    sum(costs), points.total - sum(costs)
                )
            )
            world_setting_return_list = self._world_setting()
            self._farewell_row()
            line_feed_draw.draw()
            yes_draw = draw.CenterButton(_("[确定]"), _("确定"), self.width)
            if points.total >= sum(costs):
                yes_draw.draw()
                self.return_list.append(yes_draw.return_text)
                line_feed_draw.draw()
            self.return_list.extend(world_setting_return_list)
            yrn = flow_handle.askfor_all(self.return_list)
            if yrn == yes_draw.return_text:
                self.start_new_round()
                break

    def _world_setting(self) -> list[str]:
        """绘制世界设定折叠按钮与内嵌面板并返回其监听按钮列表。"""
        self._text(_("\n○世界设定（不消耗周目点数）"))
        button_text = _(" [更改世界设定] ")
        if self.show_world_setting:
            button_text = _(" [隐藏世界设定] ")
        button = draw.CenterButton(
            button_text,
            button_text,
            len(button_text) * 2,
            cmd_func=self.toggle_world_setting,
        )
        self.return_list.append(button_text)
        button.draw()
        line_feed_draw.draw()
        if not self.show_world_setting:
            return []
        from Script.UI.Flow import creator_character_flow

        world_setting_panel = creator_character_flow.World_Setting(
            self.width, self.world_setting
        )
        world_setting_panel.draw()
        line_feed_draw.draw()
        return world_setting_panel.return_list.copy()

    def _farewell_row(self) -> None:
        """绘制送别干员当前选择与更改按钮行。"""
        info_text = _("\n○送别干员：")
        if self.farewell_npc_id:
            info_text += f"{identity.of(self.farewell_npc_id).name}"
        else:
            info_text += _("未选择")
        self._text(info_text + "        ")
        button_text = _(" [更改送别干员] ")
        button = draw.CenterButton(
            button_text,
            button_text,
            len(button_text) * 2,
            cmd_func=self.farewell_npc_change,
        )
        self.return_list.append(button_text)
        button.draw()
        line_feed_draw.draw()
        line_feed_draw.draw()

    def show_npc_change(self) -> None:
        """切换陷落干员明细列表的展开状态。"""
        self.show_npc_flag = not self.show_npc_flag

    def show_panel_change(self, type: int) -> None:
        """切换指定索引的博士详情区展开状态。"""
        self.show_panel_flag_list[type] = not self.show_panel_flag_list[type]

    def value_change_buton(self, value: int, type: int) -> None:
        """按步长调整指定继承类型的当前等级。"""
        self.levels[type] = svc.step(type, self.levels[type], value)

    def farewell_npc_change(self) -> None:
        """绘制送别干员选择子页面并等待玩家确认或返回。"""
        while 1:
            title_draw = draw.TitleLineDraw(_("送别干员"), self.width)
            title_draw.draw()
            return_list = []
            self._text(_("选择送别干员\n"))
            for count, chara_id in enumerate(self.all_fall_chara_list, 1):
                now_character_data = identity.of(chara_id)
                button_text = (
                    f"[{now_character_data.adv}]{now_character_data.name}"
                )
                chosen = chara_id == self.farewell_npc_id
                button = draw.LeftButton(
                    button_text,
                    button_text,
                    max(len(button_text), 24),
                    normal_style="gold_enrod" if chosen else "standard",
                    cmd_func=self.farewell_npc_change_confirm,
                    args=(chara_id,),
                )
                return_list.append(button_text)
                button.draw()
                if count % 8 == 0:
                    line_feed_draw.draw()
            line_feed_draw.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), self.width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn in return_list:
                break

    def farewell_npc_change_confirm(self, chara_id: int) -> None:
        """记录选中的送别干员角色编号。"""
        self.farewell_npc_id = chara_id

    def toggle_world_setting(self) -> None:
        """切换世界设定内嵌面板的展开状态。"""
        self.show_world_setting = not self.show_world_setting

    def choices(self) -> dict[str, core.JSON]:
        """收集当前面板选择并生成多周目继承快照字典。"""
        return svc.choices(
            self.levels, self.all_fall_chara_list, self.world_setting
        )

    def start_new_round(self) -> None:
        """播放送别对话、触发新周目重置并在换态后展示唤醒报告。"""
        from Script.Design import talk, second_behavior

        if self.farewell_npc_id:
            second_behavior.character_get_second_behavior(
                self.farewell_npc_id, "new_round_farewell"
            )
            line_draw = draw.LineDraw("-", self.width)
            line_draw.draw()
            line_feed_draw.draw()
            line_feed_draw.draw()
            talk.must_show_talk_check(self.farewell_npc_id)
            line_feed_draw.draw()
            line_feed_draw.draw()
            line_feed_draw.draw()

        line_draw = draw.LineDraw("-", self.width)
        line_draw.draw()
        before = core.state()
        try:
            kernel_state.new_round(self.choices())
        finally:
            if core.state() is not before:
                from Script.UI.Panel import achievement_panel

                report, achieved = awakening
                info_draw = draw.NormalDraw()
                info_draw.text = report + "\n\n\n\n\n\n\n\n\n"
                info_draw.draw()
                while 1:
                    return_list = []
                    button_draw = draw.CenterButton(
                        _("[醒来]"), _("醒来\n"), width
                    )
                    return_list.append(button_draw.return_text)
                    button_draw.draw()
                    if flow_handle.askfor_all(return_list) in return_list:
                        break
                achievement_panel.draw_achievement_notice(list(achieved))


def setup(inherit: Mapping[str, core.JSON]) -> None:
    """执行新周目状态重建与游戏数据重置，并暂存唤醒报告数据。"""
    global awakening
    report, world_setting = new_round_inherit_service.rebuild(inherit)
    reset_report, achieved = _reset_game_data(world_setting)
    awakening = (report + reset_report, tuple(achieved))


def _reset_game_data(world_setting: dict[int, int]) -> tuple[str, list[int]]:
    """重置医疗与初始设定、推进周目、结算周目成就并开放宿舍。"""
    from Script.UI.Flow import creator_character_flow
    from Script.System.Medical_System import medical_service
    from Script.Modules.gameplay_resolution import achievement_service

    info_draw_text = "\n"
    info_draw_text += _("开始重置游戏数据\n")
    new_game_round = playthrough.game_round() + 1
    new_npc_id_got = roster.active()
    kept = {
        table: playthrough.settings(table)
        for table in (playthrough.DIFFICULTY, playthrough.BIRTH_TYPE)
    }
    medical_service.init_medical_department_data()
    playthrough.reset_difficulty_and_birth()
    info_draw_text += _("游戏数据重置完毕\n")
    creator_character_flow.first_bonus_and_setting_updata()
    playthrough.set_settings(playthrough.WORLD, world_setting)
    for table, values in kept.items():
        playthrough.set_settings(table, values)
    playthrough.set_game_round(new_game_round)
    roster.set_active(new_npc_id_got)
    achieved = achievement_service.settle_by_type(_("周目"))
    creator_character_flow.game_start()
    new_round_inherit_service.open_dormitories(new_npc_id_got)
    info_draw_text += _("继承数据覆盖完毕\n")
    return info_draw_text, achieved


class CharacterabiText:
    """绘制角色各分类能力及对应继承后数值的文本面板。"""

    def __init__(self, character_id: int, width: int, rate: int) -> None:
        """初始化绘制对象"""
        self.draw_list: list[draw.Drawable] = []
        """ 绘制对象列表 """
        type_line = draw.LittleTitleLineDraw(_("能力"), width, ":")
        self.draw_list.append(type_line)
        groups = svc.ability_groups(character_id)
        for anility_type, (size, shown) in groups.items():
            for ability_id in shown:
                now_draw = draw.NormalDraw()
                now_draw_value = draw.NormalDraw()
                now_draw.text = game_config.config_ability[ability_id].name
                now_draw_1 = draw.NormalDraw()
                now_draw_1.text = " "
                now_draw_1.width = 1
                now_draw.width = width / size
                now_exp = abilities.ability(character_id)[ability_id]
                if now_exp > 0:
                    inherit_exp = int(now_exp * rate / 100)
                    now_draw_value.text = f"{now_exp}(→{inherit_exp})"
                else:
                    now_draw_value.text = str(now_exp)
                level_draw = draw.ExpLevelDraw(now_exp)
                new_draw = draw.LeftMergeDraw(width / 10)
                if ability_id == 48:
                    new_draw.draw_list.append(_break())
                new_draw.draw_list += [now_draw_1, now_draw, now_draw_1]
                pad = {2: 0, 4: 0, 6: 0, 3: 4, 5: 4}.get(anility_type, 2)
                new_draw.draw_list += [now_draw_1] * pad
                new_draw.draw_list += [level_draw, now_draw_1, now_draw_value]
                self.draw_list.append(new_draw)
            if anility_type != 6:
                self.draw_list.append(_break())

    def draw(self) -> None:
        """绘制对象"""
        line_feed_draw.draw()
        for value in self.draw_list:
            value.draw()


def _break() -> draw.NormalDraw:
    """构造宽度为 1 的单个换行绘制对象。"""
    new_draw_n = draw.NormalDraw()
    new_draw_n.text = "\n"
    new_draw_n.width = 1
    return new_draw_n


class CharacterExperienceText:
    """绘制角色非零经验及对应继承后数值的分栏文本面板。"""

    def __init__(
        self, character_id: int, width: int, column: int, rate: int
    ) -> None:
        """初始化绘制对象"""
        self.draw_list: list[draw.Drawable | list[draw.LeftDraw]] = []
        """ 绘制的文本列表 """
        type_line = draw.LittleTitleLineDraw(_("经验"), width, ":")
        self.draw_list.append(type_line)
        now_draw = panel.LeftDrawTextListPanel()
        now_draw.set(svc.experience_texts(character_id, rate), width, column)
        self.draw_list.extend(now_draw.draw_list)

    def draw(self) -> None:
        """绘制面板"""
        line_feed_draw.draw()
        count = 0
        for label in self.draw_list:
            if isinstance(label, list):
                for value in label:
                    value.draw()
                    count += 1
                line_feed_draw.draw()
            else:
                label.draw()
        if count <= 8:
            line_feed_draw.draw()
            if count == 0:
                line_feed_draw.draw()
