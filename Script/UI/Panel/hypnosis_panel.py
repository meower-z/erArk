"""催眠类型与角色扮演类型的选择面板"""

from types import FunctionType
from Script.Core import constant, flow_handle
from Script.Core import get_text
from Script.UI.Moudle import draw, view
from Script.Config import game_config, normal_config
from Script.Modules.domains import activity, hypnosis, identity
from Script.Modules.gameplay_resolution import hypnosis_panel_service as rules
from Script.Modules.gameplay_resolution import hypnosis_service

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


class Chose_Hypnosis_Type_Panel:
    """
    用于选择催眠类型的面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int, instruct_flag: bool = False) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.instruct_flag: bool = instruct_flag
        """ 是否为指令模式 """

    def draw(self) -> None:
        """绘制对象"""
        title_draw = draw.TitleLineDraw(_("选择催眠类型"), self.width)
        while 1:
            return_list = []
            title_draw.draw()
            target_character_data: identity.Identity = identity.of(
                activity.target(0)
            )
            info_draw = draw.NormalDraw()
            info_text = _(
                "\n○进行催眠时会消耗理智，催眠结束后会自动合理化催眠过程中的记忆，未被催眠的干员也不会对催眠中的行为起疑\n"
            )
            if activity.target(0) > 0:
                info_text += _("○当前催眠对象：{0}，催眠深度：{1}%\n").format(
                    target_character_data.name,
                    hypnosis.degree(activity.target(0)),
                )
            info_text += _("\n催眠系能力：\n")
            info_draw.text = _(info_text)
            info_draw.draw()
            for talent_row in rules.talent_rows():
                now_draw = draw.NormalDraw()
                if talent_row.unlocked:
                    draw_text = _("  {0}(最高催眠深度{1}%)：{2}\n").format(
                        talent_row.name, talent_row.max_degree, talent_row.info
                    )
                else:
                    draw_text = _("  {0}(未解锁)：{1}\n").format(
                        talent_row.name, talent_row.info
                    )
                    now_draw.style = "deep_gray"
                now_draw.text = _(draw_text)
                now_draw.draw()
            info_text = _("\n可用的催眠类型：\n")
            info_draw.text = _(info_text)
            info_draw.draw()
            for type_row in rules.type_rows(activity.target(0)):
                draw_text = f"  [{type_row.name}]"
                draw_text += _("(需要[{0}]，且催眠深度达到{1}%)").format(
                    type_row.talent_name, type_row.need_degree
                )
                draw_text += f"：{type_row.introduce}"
                if type_row.available:
                    button_draw = draw.LeftButton(
                        _(draw_text),
                        _(type_row.name),
                        window_width,
                        cmd_func=self.change_hypnosis_type,
                        args=(type_row.type_id,),
                    )
                    return_list.append(button_draw.return_text)
                    button_draw.draw()
                    line_feed.draw()
                else:
                    now_draw = draw.NormalDraw()
                    draw_text += "\n"
                    now_draw.text = _(draw_text)
                    now_draw.style = "deep_gray"
                    now_draw.draw()

            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn in return_list:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def change_hypnosis_type(self, hypnosis_type_cid: int) -> None:
        """改变当前的催眠类型"""
        pl_character_data: identity.Identity = identity.of(0)
        rules.set_hypnosis_type(hypnosis_type_cid)
        target_data: identity.Identity = identity.of(activity.target(0))
        draw.LineDraw("-", self.width).draw()
        if hypnosis_type_cid <= 0:
            return
        hypnosis_type_name = game_config.config_hypnosis_type[
            hypnosis_type_cid
        ].name
        now_draw = draw.WaitDraw()
        draw_text = _("\n已选择{0}催眠类型\n\n").format(hypnosis_type_name)
        now_draw.style = "pink"
        now_draw.text = draw_text
        now_draw.draw()
        if not (self.instruct_flag and activity.target(0)):
            return
        if not hypnosis_service.evaluate_hypnosis_completion(
            activity.target(0)
        ):
            return
        result_texts = {
            1: _("\n{0}会理所当然地接受{1}的不合理行为了\n\n"),
            2: _("\n{0}会把{1}视为空气了\n\n"),
            3: _("\n{0}可以随意地操纵{1}的身体了\n\n"),
            4: _("\n{0}可以向{1}的潜意识灌输指令了\n\n"),
        }
        if hypnosis_type_cid not in result_texts:
            return
        names = (target_data.name, pl_character_data.name)
        control = hypnosis_type_cid in (3, 4)
        if control:
            names = names[::-1]
        now_draw = draw.WaitDraw()
        now_draw.style = "pink"
        now_draw.text = result_texts[hypnosis_type_cid].format(*names)
        now_draw.draw()
        if control:
            self.body_or_mind_control_option(hypnosis_type_cid - 3)

    def body_or_mind_control_option(self, body_or_mind_flag: int = 0) -> None:
        """
        身体或心灵的控制选项
        Keyword arguments:
        body_or_mind_flag -- 0为身体控制，1为心灵控制
        """
        target_data: identity.Identity = identity.of(activity.target(0))
        type_text = _("身体") if body_or_mind_flag == 0 else _("心灵")
        control_rows = rules.control_rows(body_or_mind_flag != 0)
        while 1:
            return_list = []
            title_draw = draw.TitleLineDraw(
                _("选择{0}控制选项").format(type_text), self.width
            )
            title_draw.draw()
            info_draw = draw.NormalDraw()
            info_text = _("\n可以对{0}使用的控制指令：\n\n").format(
                target_data.name
            )
            info_draw.text = info_text
            info_draw.draw()
            for count, control_row in enumerate(control_rows):
                draw_text = f"[{count}]{control_row.name}"
                if control_row.introduce is not None:
                    draw_text += f"：{control_row.introduce}"
                button_draw = draw.LeftButton(
                    _(draw_text),
                    _(control_row.name),
                    window_width,
                    cmd_func=self.son_instruct,
                    args=(control_row.behavior_id,),
                )
                return_list.append(button_draw.return_text)
                button_draw.draw()
                line_feed.draw()
            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn in return_list:
                break

    def son_instruct(self, behavbior_cid: str) -> None:
        """进行子选项"""
        from Script.System.Instruct_System import handle_instruct

        draw.LineDraw("-", self.width).draw()
        if behavbior_cid == "hypnosis_roleplay":
            Chose_Roleplay_Type_Panel(self.width).draw()
            if hypnosis.roleplay(activity.target(0)):
                handle_instruct.chara_handle_instruct_common_settle(
                    behavbior_cid
                )
            return
        if (
            behavbior_cid == "hypnosis_force_ovulation"
            and rules.force_ovulation_blocked()
        ):
            now_draw = draw.WaitDraw()
            now_draw.text = _("\n当前干员不满足条件，无法进行强制排卵\n")
            now_draw.draw()
            return
        handle_instruct.chara_handle_instruct_common_settle(behavbior_cid)


class Chose_Roleplay_Type_Panel:
    """
    用于选择心控催眠-角色扮演的面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化角色扮演选择面板，加载分组目录、收起各分组并复制目标当前已选列表。"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.catalog = rules.roleplay_catalog()
        """ 角色扮演分组目录 """
        self.type_expand_flag = dict.fromkeys(self.catalog.type_list, False)
        """ 各角色扮演分组的展开状态映射 """
        if self.catalog.has_special:
            self.type_expand_flag[self.catalog.special_type] = False
        self.selected_roleplay_cache = list(
            hypnosis.roleplay(activity.target(0))
        )
        """ 当前待确认的角色扮演编号缓存列表 """

    def draw(self) -> None:
        """绘制角色扮演选择面板并循环处理分组展开、选项点击、确认结算与返回。"""
        title_draw = draw.TitleLineDraw(_("选择角色扮演类型"), self.width)
        while 1:
            return_list = []
            title_draw.draw()
            info_draw = draw.NormalDraw()
            info_text = _(
                "\n○被催眠后会完全带入对应的角色或场景，直到催眠解除为止\n"
            )
            info_text += _("○非特殊类里，每类可各选一个，同时起效\n")
            info_text += _("○特殊类与其他催眠相冲突，只能单独起效\n")
            info_text += _(
                "  （当前版本中，该催眠的文本对应较少，仅有功能和数值上的效果）\n"
            )
            info_text += _("\n  要催眠为哪一种角色扮演呢？")
            info_text += _("（当前为：")
            if len(self.selected_roleplay_cache) == 0:
                info_text += _("无）\n")
            else:
                self.selected_roleplay_cache.sort()
                for name in rules.selected_names(self.selected_roleplay_cache):
                    info_text += _("{0} ").format(name)
                info_text += "）\n"
            info_draw.text = info_text
            info_draw.draw()
            line_feed.draw()
            for section, special in self.catalog.sections():
                line_feed.draw()
                expanded = self.type_expand_flag.get(section, False)
                btn_text = f"▼{section}" if expanded else f"▶{section}"
                button_draw = draw.LeftButton(
                    _(btn_text),
                    _(btn_text),
                    window_width / 4,
                    cmd_func=self.toggle_type_expand,
                    args=(section,),
                )
                return_list.append(button_draw.return_text)
                button_draw.draw()
                line_feed.draw()
                if not expanded:
                    continue
                options = rules.roleplay_options(
                    self.catalog,
                    section,
                    special,
                    self.selected_roleplay_cache,
                )
                for count, option in enumerate(options, 1):
                    if option.selectable:
                        draw_text = option.text
                        draw_style = "standard"
                        if option.chosen:
                            draw_style = "gold_enrod"
                            draw_text += _("(已选)")
                        button_draw = draw.LeftButton(
                            _(draw_text),
                            _(option.name),
                            window_width / 5,
                            normal_style=draw_style,
                            cmd_func=self.choose_this_type,
                            args=(option.cid,),
                        )
                        return_list.append(button_draw.return_text)
                        button_draw.draw()
                    else:
                        now_draw = draw.LeftDraw()
                        now_draw.text = _(option.text)
                        now_draw.style = "deep_gray"
                        now_draw.width = window_width / 5
                        now_draw.draw()
                    if count % 5 == 0:
                        line_feed.draw()
                line_feed.draw()

            line_feed.draw()
            yes_draw = draw.CenterButton(
                _("[确认]"), _("确认"), window_width / 2
            )
            return_list.append(yes_draw.return_text)
            if len(self.selected_roleplay_cache):
                yes_draw.draw()
            back_draw = draw.CenterButton(
                _("[返回]"), _("返回"), window_width / 2
            )
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == yes_draw.return_text:
                self.settle_roleplay_selection()
                view.now_panel_id = constant.Panel.IN_SCENE
                break
            elif yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def toggle_type_expand(self, t: str) -> None:
        """切换指定分组名称 t 在 type_expand_flag 中的展开状态。"""
        self.type_expand_flag[t] = not self.type_expand_flag.get(t, False)

    def judge_can_select(
        self,
        cid: int,
        selected_special_cid: int | None,
        selected_type_cid: dict[str, int],
        t: str,
        selected_roleplay_cache: list[int],
    ) -> bool:
        """按当前选择状态判断角色扮演编号 cid 在分组 t 中是否可选。"""
        return rules.can_select(
            cid,
            selected_special_cid,
            selected_type_cid,
            t,
            selected_roleplay_cache,
        )

    def choose_this_type(self, cid: int) -> None:
        """
        处理角色扮演条目 cid 的点击：未选条目打开确认弹窗，已选条目直接移出缓存。
        配置中不存在的 cid 会被忽略。
        """
        if cid not in game_config.config_roleplay:
            return
        if cid in self.selected_roleplay_cache:
            self.selected_roleplay_cache.remove(cid)
            return
        while 1:
            draw.LineDraw("-", self.width).draw()
            return_list = []
            line_feed.draw()
            role_play_data = game_config.config_roleplay[cid]
            info_text = _("\n{0}：{1}\n").format(
                role_play_data.name, role_play_data.info
            )
            prefix = rules.job_prefix(cid)
            if prefix is not None:
                info_text += _(
                    "进行该扮演后，可进一步选择其他类中带有{0}前缀的子项。\n"
                ).format(prefix)
            info_text += _("是否确定进行该扮演？\n")
            info_draw = draw.NormalDraw()
            info_draw.text = info_text
            info_draw.draw()
            line_feed.draw()
            confirm_draw = draw.CenterButton(
                _("[确认]"),
                _("确认"),
                window_width / 2,
                cmd_func=self.confirm_roleplay,
                args=(cid,),
            )
            confirm_draw.draw()
            return_list.append(confirm_draw.return_text)
            cancel_draw = draw.CenterButton(
                _("[取消]"), _("取消"), window_width / 2
            )
            cancel_draw.draw()
            return_list.append(cancel_draw.return_text)
            line_feed.draw()
            yrn = flow_handle.askfor_all(return_list)
            if yrn in return_list:
                break

    def confirm_roleplay(self, cid: int) -> None:
        """按规则追加已确认的角色扮演编号 cid，并原地更新 selected_roleplay_cache。"""
        self.selected_roleplay_cache[:] = rules.with_roleplay(
            self.catalog, self.selected_roleplay_cache, cid
        )

    def settle_roleplay_selection(self) -> None:
        """结算当前角色扮演缓存至目标角色状态，并绘制等待确认的结果提示。"""
        target_data: identity.Identity = identity.of(activity.target(0))
        names = rules.settle_roleplay(
            activity.target(0), self.selected_roleplay_cache
        )
        info_draw = draw.WaitDraw()
        info_draw.style = "purple"
        info_text = _("\n已为{0}开始进行以下的角色扮演了：").format(
            target_data.name
        )
        if names is None:
            info_text += _("无\n")
        else:
            for name in names:
                info_text += _("{0} ").format(name)
            info_text += "\n"
        info_draw.text = info_text
        info_draw.draw()
