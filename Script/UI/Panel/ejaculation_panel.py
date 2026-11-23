"""射精界面面板：忍耐射精询问与射精目标、部位选择面板。"""

from types import FunctionType
from Script.Core import constant, flow_handle
from Script.Core import get_text, py_cmd
from Script.Design import handle_premise
from Script.Design import map_handle
from Script.UI.Moudle import draw, view
from Script.Config import game_config, normal_config

from Script.Modules.gameplay_resolution import ejaculation_service
from Script.Modules.domains import abilities, activity, h_meters, h_state
from Script.Modules.domains import modes, wardrobe
from Script.Modules.domains import identity, scene_state

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


def show_endure_ejaculation_panel() -> bool:
    """
    进行是否忍住射精的判断
    return
    bool -- 是否忍住 True为忍住 False为射出
    """
    character_data: identity.Identity = identity.of(0)
    now_lv = abilities.ability(0)[30]
    now_count = h_state.get(0, "endure_not_shot_count")
    line = draw.LineDraw("-", window_width)

    # 判断忍耐几率
    if now_count <= now_lv:
        now_rate = 100
        endure_text = _("必定忍住")
    else:
        # 超出的次数
        over_count = now_count - now_lv
        # 下降的动态几率
        down_rate = 50 - now_lv * 5
        # 当前忍耐几率
        now_rate = 100 - over_count * down_rate
        now_rate = max(0, now_rate)
        if now_rate >= 75:
            endure_text = _("高")
        elif now_rate >= 50:
            endure_text = _("中")
        elif now_rate >= 25:
            endure_text = _("低")
        else:
            endure_text = _("无")

    return_flag = ejaculation_service.judge_endure_ejaculation(now_rate)

    # 如果系统设置中选择了手动选择是否忍耐
    if normal_config.system_setting.base_setting.get(11, 2) == 2:
        while 1:
            line.draw()
            line_feed.draw()
            return_list = []

            # 询问是否要忍住
            now_draw = draw.NormalDraw()
            now_draw_text = _(
                "要射精了，是否要忍住射精，忍耐次数越多则射精量越多（当前已忍住{0}次，忍耐几率 {1}）\n"
            ).format(now_count, endure_text)
            now_draw.text = now_draw_text
            now_draw.width = window_width
            now_draw.draw()
            line_feed.draw()

            # 选择是否忍住
            yes_draw = draw.CenterButton(
                _("[忍住]"), _("忍住"), int(window_width / 3)
            )
            yes_draw.draw()
            return_list.append(yes_draw.return_text)
            no_draw = draw.CenterButton(
                _("[射出]"), _("射出"), int(window_width / 3)
            )
            no_draw.draw()
            return_list.append(no_draw.return_text)

            line_feed.draw()

            yrn = flow_handle.askfor_all(return_list)
            if yrn in return_list:
                # 如果是射出，则返回False
                if yrn == _("射出"):
                    return_flag = False
                break
    # 如果系统设置中选择了一定忍耐
    elif normal_config.system_setting.base_setting.get(11, 2) == 1:
        pass
    # 如果系统设置中选择了不忍耐直接射出
    else:
        return_flag = False

    # 忍住的结算
    if return_flag:
        h_state.set(0, endure_not_shot_count=now_count + 1)
        h_meters.set(0, eja=0)
        endure_text = _("\n{0}忍住了射精\n").format(character_data.name)
        now_draw = draw.NormalDraw()
        now_draw.text = endure_text
        now_draw.width = window_width
        now_draw.draw()
        line.draw()

    return return_flag


class Ejaculation_Panel:
    """
    用于显示射精界面面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_panel = _("身体")
        """ 当前绘制的射精页面 """

    def draw(self) -> None:
        """绘制对象"""
        target_data: identity.Identity = identity.of(activity.target(0))
        # 当前地点有体外无壳卵时，无论是否开启自动射精都必须手动选择（可选择射在卵上）
        from Script.System.Pregnancy_System import soft_egg_handle

        soft_egg_flag = (
            len(soft_egg_handle.get_soft_eggs_in_scene(activity.position(0)))
            > 0
        )

        # 如果当前交互对象不是NPC的话，则跳过部位选择；有体外卵时改为只列卵按钮与照常射出
        if activity.target(0) == 0:
            if soft_egg_flag:
                self.draw_choose_part(self_mode=True)
            else:
                self.shoot_here(6, 0)
        # 群交模式下手动选择对象与部位
        elif modes.group_sex():
            self.draw_choose_target_chara_in_group_sex()
            self.draw_choose_part()
        # 有体外卵时强制手动选择
        elif soft_egg_flag:
            self.draw_choose_part()
        # 如果没有选择射精部位，则直接在当前阴茎位置射精
        elif not normal_config.system_setting.base_setting[3]:
            now_position = h_state.get(target_data.cid, "insert_position")
            if now_position != -1:
                # 身体
                if now_position < 20:
                    self.shoot_here(now_position, 0)
                # 衣服
                else:
                    self.shoot_here(now_position - 20, 1)
            # 如果没有插入位置，则也手动选择射精部位
            else:
                self.draw_choose_part()
        # 手动选择射精部位
        else:
            self.draw_choose_part()

    def part_can_choose(self, body_part_cid: int) -> bool:
        """判断该部位是否可以绘制"""
        from Script.Design import clothing
        from Script.Design import instuct_judege

        # 不插在对应部位，则无法射在对应部位
        if body_part_cid == 6 and not (
            handle_premise.handle_penis_in_t_vagina(0)
            or handle_premise.handle_penis_in_t_womb(0)
        ):
            return False
        elif body_part_cid == 7 and not handle_premise.handle_penis_in_t_womb(
            0
        ):
            return False
        elif body_part_cid == 8 and not handle_premise.handle_penis_in_t_anal(
            0
        ):
            return False
        elif (
            body_part_cid == 9
            and not handle_premise.handle_penis_in_t_nrethral(0)
        ):
            return False
        elif (
            body_part_cid == 15
            and not handle_premise.handle_penis_in_t_deep_throat(0)
        ):
            return False

        # 如果没有口交合意则无法射在口腔
        if (
            body_part_cid == 2
            and not instuct_judege.calculation_instuct_judege(
                0,
                activity.target(0),
                _("口交"),
                not_draw_flag=True,
            )
        ):
            return False

        # 获取没有穿衣服的部位列表
        no_cloth_body_list = clothing.get_exposed_body_parts(
            activity.target(0), ignore_panties=True
        )

        # 如果该部位没有穿衣服，则可以
        if body_part_cid in no_cloth_body_list:
            return True
        return False

    def draw_choose_target_chara_in_group_sex(self) -> None:
        """绘制选择射精对象"""

        title_name = _("选择射精对象")
        title_draw = draw.TitleLineDraw(title_name, self.width)
        while 1:
            return_list = []
            title_draw.draw()

            scene_path_str = map_handle.get_map_system_path_str_for_list(
                activity.position(0)
            )

            # 当前场景的角色列表
            for chara_id in scene_state.occupants(scene_path_str):
                # 不显示自己
                if chara_id == 0:
                    continue
                now_character_data: identity.Identity = identity.of(chara_id)
                chara_name = now_character_data.name
                chara_adv = now_character_data.adv
                draw_text = f"[{chara_adv}]{chara_name}"
                name_draw = draw.CenterButton(
                    draw_text,
                    chara_name,
                    (len(draw_text) + 1) * 3,
                    cmd_func=self.change_shoot_target,
                    args=(chara_id),
                )
                name_draw.draw()
                return_list.append(name_draw.return_text)

            line_feed.draw()

            yrn = flow_handle.askfor_all(return_list)

            # 在非页面切换时退出面板
            if yrn in return_list:
                break

    def draw_choose_part(self, self_mode: bool = False) -> None:
        """
        绘制选择射精部位
        Keyword arguments:
        self_mode -- 交互对象为自己（自慰）且当前地点有体外无壳卵：不列身体/服装部位，只列卵按钮与照常射出按钮
        """
        from Script.System.Pregnancy_System import soft_egg_handle

        title_name = _("选择射精部位")
        title_draw = draw.TitleLineDraw(title_name, self.width)
        while 1:

            target_data: identity.Identity = identity.of(activity.target(0))

            return_list = []
            title_draw.draw()

            if not self_mode:
                # 绘制身体部位按钮
                body_count = 0
                for body_part_cid in game_config.config_body_part:
                    part_name = game_config.config_body_part[body_part_cid].name
                    draw_text = f"[{body_part_cid}]{part_name}"
                    body_count += 1
                    show_flag: bool | int = self.part_can_choose(body_part_cid)
                    if show_flag:
                        name_draw = draw.CenterButton(
                            draw_text,
                            "\n" + part_name,
                            (len(draw_text) + 1) * 2,
                            cmd_func=self.shoot_here,
                            args=(body_part_cid, 0),
                        )
                        name_draw.draw()
                        return_list.append(name_draw.return_text)
                        if body_count > 0 and body_count % 8 == 0:
                            line_feed.draw()

                line_feed.draw()

                # 绘制服装部位按钮
                cloth_count = 0
                target_worn = wardrobe.of(target_data.cid).cloth_wear
                for clothing_type in game_config.config_clothing_type:
                    cloth_name = game_config.config_clothing_type[
                        clothing_type
                    ].name
                    draw_text = f"[{clothing_type}]{cloth_name}"
                    cloth_count += 1
                    show_flag = len(target_worn[clothing_type])
                    if show_flag:
                        name_draw = draw.CenterButton(
                            draw_text,
                            cloth_name,
                            (len(draw_text) + 1) * 2,
                            cmd_func=self.shoot_here,
                            args=(clothing_type, 1),
                        )
                        name_draw.draw()
                        return_list.append(name_draw.return_text)
                        if cloth_count > 0 and cloth_count % 8 == 0:
                            line_feed.draw()

            # 绘制当前地点的体外无壳卵按钮（选中即射在该卵上）
            soft_eggs = soft_egg_handle.get_soft_eggs_in_scene(
                activity.position(0)
            )
            if len(soft_eggs):
                line_feed.draw()
                egg_count = 0
                for egg_id, egg_data in soft_eggs.items():
                    egg_name = soft_egg_handle.get_soft_egg_name(egg_id)
                    draw_text = _("[卵块{0}]{1}（{2}ml）").format(
                        egg_id, egg_name, int(egg_data["semen_count"])
                    )
                    egg_count += 1
                    name_draw = draw.CenterButton(
                        draw_text,
                        draw_text,
                        (len(draw_text) + 1) * 2,
                        cmd_func=self.shoot_soft_egg,
                        args=(egg_id,),
                    )
                    name_draw.draw()
                    return_list.append(name_draw.return_text)
                    if egg_count > 0 and egg_count % 4 == 0:
                        line_feed.draw()
            # 自慰时保留原来的射精行为作为兜底选项
            if self_mode:
                line_feed.draw()
                normal_text = _("[照常射出]")
                normal_draw = draw.CenterButton(
                    normal_text,
                    normal_text,
                    (len(normal_text) + 1) * 2,
                    cmd_func=self.shoot_here,
                    args=(6, 0),
                )
                normal_draw.draw()
                return_list.append(normal_draw.return_text)

            yrn = flow_handle.askfor_all(return_list)

            # 在非页面切换时退出面板
            if yrn not in [_("身体"), _("服装")]:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def change_shoot_target(self, target_character_id: int) -> None:
        """更改射精目标"""
        activity.set_target(0, target_character_id)

    def shoot_soft_egg(self, egg_id: int) -> None:
        """
        结算射在体外无壳卵上（不涉及任何身体/服装部位，不更新阴茎插入与射精部位记录）
        Keyword arguments:
        egg_id -- 体外无壳卵编号
        """
        py_cmd.clr_cmd()
        ejaculation_service.ejaculation_flow(-1, 0, soft_egg_id=egg_id)

    def shoot_here(self, part_cid: int, part_type: int) -> None:
        """结算射精"""
        py_cmd.clr_cmd()
        # 更新阴茎插入部位
        target_id = activity.target(0)
        if part_type == 0:
            h_state.set(0, insert_position=part_cid)
            h_state.set(target_id, insert_position=part_cid)
            # 如果是深喉插入状态，则将部位改为食道射精
            if handle_premise.handle_last_cmd_deep_throat(0):
                part_cid = 15
        else:
            h_state.set(0, insert_position=part_cid + 20)
            h_state.set(target_id, insert_position=part_cid + 20)
        ejaculation_service.ejaculation_flow(part_cid, part_type)
