"""选择睡眠时间的面板与睡到玩家起床时间的计算"""

import datetime
from fractions import Fraction
from types import FunctionType
from Script.UI.Moudle import draw, view
from Script.UI.Panel import diary_panel
from Script.Core import (
    cache_control,
    get_text,
    game_type,
    flow_handle,
    constant,
)
from Script.Config import normal_config
from Script.Design import (
    map_handle,
    game_time,
    handle_premise,
)
from Script.Modules.tk_ui import player_pick
import math
from Script.Modules.domains import action_info, needs

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
_: FunctionType = get_text._
""" 翻译api """

line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width = normal_config.config_normal.text_width
""" 屏幕宽度 """


def judge_time_to_pl_awake(start_time: datetime.datetime) -> int:
    """计算睡到玩家起床的时间"""
    plan_to_wake_time = action_info.get(0, "plan_to_wake_time")
    wake_time_hour, wake_time_minute = (
        plan_to_wake_time[0],
        plan_to_wake_time[1],
    )
    # 12点后则为明天，否则为今天
    if start_time.hour > 12:
        judge_wake_up_time = game_time.get_sub_date(day=1, old_date=start_time)
    else:
        judge_wake_up_time = start_time
    # 替换时间和分钟
    judge_wake_up_time = judge_wake_up_time.replace(
        hour=wake_time_hour, minute=wake_time_minute
    )
    # 计算时间差
    min_to_moring_service_min = int(
        (judge_wake_up_time - start_time).seconds / 60
    )
    return min_to_moring_service_min


class Sleep_Panel:
    """
    用于选择睡眠时间的面板
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.close_door_flag = True
        """ 关门情况 """
        self.sleep_time_hour = 0
        """ 睡眠时间_小时 """
        self.sleep_time_min = 0
        """ 睡眠时间_分钟 """
        self.pl_character_data: game_type.Character = cache.character_data[0]
        """ 玩家角色数据 """
        self.min_to_moring_service_min = 0
        """ 睡到早安服务的时间_分钟 """
        self.min_to_moring_service_hour = 0
        """ 睡到早安服务的时间_小时 """
        self.morning_service_time_text = ""
        """ 早安服务时间文本 """

    def draw(self) -> None:
        """绘制对象"""

        # 计算回复时间（小时），然后向上取整，且最小为1
        # 比率同 realtime_settle.settle_sleep：体力每分钟 上限/400+3，气力每分钟 上限/200+6，疲劳每分钟 1/3
        hit_point_add_base = (
            needs.of(self.pl_character_data.cid)["hit_max"] * Fraction(1, 400)
            + 3
        )
        mana_point_add_base = (
            needs.of(self.pl_character_data.cid)["mana_max"] * Fraction(1, 200)
            + 6
        )
        hp_recover_time = math.ceil(
            (
                needs.of(self.pl_character_data.cid)["hit_max"]
                - needs.of(self.pl_character_data.cid)["hit"]
            )
            / hit_point_add_base
            / 60
        )
        mp_recover_time = math.ceil(
            (
                needs.of(self.pl_character_data.cid)["mana_max"]
                - needs.of(self.pl_character_data.cid)["mana"]
            )
            / mana_point_add_base
            / 60
        )
        hpmp_need_time = max(hp_recover_time, mp_recover_time)
        hpmp_need_time = max(hpmp_need_time, 1)
        # 其他回复所需时间，最大为8小时
        tired_recover_time = math.ceil(
            Fraction(needs.of(self.pl_character_data.cid)["tired"] * 3, 60)
        )  # 疲劳
        # 理智和精液
        sanity_recover_time = math.ceil(
            (
                needs.of(self.pl_character_data.cid)["sanity_max"]
                - needs.of(self.pl_character_data.cid)["sanity"]
            )
            / needs.of(self.pl_character_data.cid)["sanity_max"]
            / 0.15
        )  # 理智
        semen_recover_time = math.ceil(
            (
                self.pl_character_data.semen_point_max
                - self.pl_character_data.semen_point
            )
            / needs.of(self.pl_character_data.cid)["sanity_max"]
            / 0.15
        )  # 精液
        all_recover_time = max(
            tired_recover_time, sanity_recover_time, semen_recover_time
        )
        # 全状态回复所需时间，最大为8小时
        all_recover_time = min(all_recover_time, 8)
        all_recover_time = max(hpmp_need_time, all_recover_time)
        need_time = all_recover_time
        self.sleep_time_hour = need_time

        # 检测是否开启了早安服务
        morning_service_flag = False
        if self.pl_character_data.assistant_character_id:
            # 如果开启了，则默认睡到早安服务时间
            if handle_premise.handle_assistant_morning_salutation_on(
                self.pl_character_data.assistant_character_id
            ):
                morning_service_flag = True
                self.get_time_to_morning_service()
                self.sleep_to_morning_service()

        title_text = _("睡眠")
        title_draw = draw.TitleLineDraw(title_text, self.width)

        while 1:
            title_draw.draw()
            return_list = []
            line = draw.LineDraw("-", window_width)
            line.draw()
            now_draw = draw.NormalDraw()

            # 计算地点数据
            now_position = self.pl_character_data.position
            now_scene_str = map_handle.get_map_system_path_str_for_list(
                now_position
            )
            now_scene_data = cache.scene_data[now_scene_str]

            # 地点关门判定的三个分支
            if now_scene_data.close_type == 0:
                info_text = _("\n 当前地点无法关门，")
            elif now_scene_data.close_type == 1:
                info_text = _("\n 当前地点可以关门，关上之后其他人就进不来了，")
            else:
                info_text = _(
                    "\n 当前地点有可以关门的小隔间，关上后别人无法发现隔间内的人，但仍可以进入该地点，"
                )
            info_text += _("当前：   ")
            now_draw.text = info_text
            now_draw.draw()

            # 绘制关门按钮
            button_text = (
                _(" [关门] ") if self.close_door_flag else _(" [不关门] ")
            )
            button_draw = draw.CenterButton(
                button_text,
                button_text,
                len(button_text) * 2,
                cmd_func=self.close_door_switch,
            )
            button_draw.draw()
            return_list.append(button_draw.return_text)

            now_draw_text = _(
                "\n\n 预计回满体力和气力最少需要 {0} 小时，"
                "全状态完全回复(包括体力、气力、疲劳、理智、精液等)至少需要 {1} 小时\n"
            ).format(hpmp_need_time, all_recover_time)
            # 早安服务模式下默认睡到早安时间
            if morning_service_flag:
                now_draw_text += _(
                    " 当前设定的早安服务时间为：{0} ，睡到早安服务时间预计为 {1} 小时左右\n\n"
                ).format(
                    self.morning_service_time_text,
                    self.min_to_moring_service_hour,
                )
                now_draw_text += _(
                    " 当前决定的睡眠时间为：{0} 小时（默认睡到早安服务时间）"
                ).format(self.sleep_time_hour)
            else:
                now_draw_text += _(
                    " 当前决定的睡眠时间为：{0} 小时（默认取两者最大值）"
                ).format(self.sleep_time_hour)
            now_draw.text = now_draw_text
            now_draw.draw()

            now_draw_text = _("\n 睡眠时间选择：")
            now_draw.text = now_draw_text
            now_draw.draw()
            for i in [1, 4, 8]:
                button_text = _(" [{0}小时] ").format(i)
                button_draw = draw.CenterButton(
                    button_text,
                    button_text,
                    len(button_text) * 2,
                    cmd_func=self.fast_choice_sleep_time,
                    args=i,
                )
                button_draw.draw()
                return_list.append(button_draw.return_text)

            # 如果已经启用了早安服务，则增加一个睡到早安服务时间的按钮
            if morning_service_flag:
                button_text = _(" [睡到早安服务时间] ")
                button_draw = draw.CenterButton(
                    button_text,
                    button_text,
                    len(button_text) * 2,
                    cmd_func=self.sleep_to_morning_service,
                )
                button_draw.draw()
                return_list.append(button_draw.return_text)

            button_text = _(" [自定义睡眠时间] ")
            button_draw = draw.CenterButton(
                button_text,
                _("请输入睡眠时间(最小1小时，最大12小时)："),
                len(button_text) * 2,
                cmd_func=self.input_sleep_time,
            )
            button_draw.draw()
            return_list.append(button_draw.return_text)
            line_feed.draw()
            now_draw_text = _("\n 睡前日记：")
            now_draw.text = now_draw_text
            now_draw.draw()
            button_text = _(" [记日记] ")
            diary_draw = draw.CenterButton(
                button_text,
                button_text + "\n",
                len(button_text) * 2,
                cmd_func=self.show_diary,
            )
            diary_draw.draw()
            line_feed.draw()
            return_list.append(diary_draw.return_text)

            line_feed.draw()
            line_feed.draw()
            yes_draw = draw.CenterButton(
                _("[确定]"), _("确定\n\n"), window_width // 2
            )
            yes_draw.draw()
            return_list.append(yes_draw.return_text)
            back_draw = draw.CenterButton(
                _("[返回]"), _("返回\n"), window_width // 2
            )
            back_draw.draw()
            return_list.append(back_draw.return_text)
            line_feed.draw()
            line_feed.draw()

            yrn = flow_handle.askfor_all(return_list)
            if yrn == yes_draw.return_text:
                if self.sleep_time_min == 0:
                    self.sleep_time_min = self.sleep_time_hour * 60
                view.now_panel_id = constant.Panel.IN_SCENE
                player_pick.choose(
                    constant.Behavior.SLEEP,
                    self.sleep_time_min,
                    kind="sleep",
                    state=constant.CharacterStatus.STATUS_SLEEP,
                    args={"close_door": bool(self.close_door_flag)},
                )
            elif yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def input_sleep_time(self) -> None:
        """输入睡眠时间"""
        while 1:
            input_text = flow_handle.askfor_str(
                _(_("请输入睡眠时间(最小1小时，最大8小时)："))
            )
            try:
                user_input = int(input_text)
            except BaseException:
                continue
            if user_input <= 0:
                continue
            elif user_input > 0:
                if user_input > 12:
                    user_input = 12
                self.sleep_time_hour = user_input
                self.sleep_time_min = user_input * 60
                break

    def fast_choice_sleep_time(self, sleep_time: int) -> None:
        """快速选择睡眠时间"""
        self.sleep_time_hour = sleep_time
        self.sleep_time_min = sleep_time * 60

    def get_time_to_morning_service(self) -> None:
        """计算睡到早安服务的时间"""
        # 计算时间差
        self.min_to_moring_service_min = judge_time_to_pl_awake(
            self.pl_character_data.behavior.start_time
        )
        self.min_to_moring_service_hour = int(
            self.min_to_moring_service_min / 60
        )
        self.min_to_moring_service_hour = max(
            self.min_to_moring_service_hour, 1
        )
        # 获得早安服务时间的文本
        plan_to_wake_time = action_info.get(
            self.pl_character_data.cid, "plan_to_wake_time"
        )
        wake_time_hour, wake_time_minute = (
            plan_to_wake_time[0],
            plan_to_wake_time[1],
        )
        self.morning_service_time_text = _("{0}:{1}").format(
            str(wake_time_hour).rjust(2, "0"),
            str(wake_time_minute).rjust(2, "0"),
        )

    def sleep_to_morning_service(self) -> None:
        """睡到早安服务时间"""
        self.sleep_time_min = max(self.min_to_moring_service_min, 60)
        self.sleep_time_hour = self.min_to_moring_service_hour

    def close_door_switch(self) -> None:
        """关门开关"""
        self.close_door_flag = not self.close_door_flag

    def show_diary(self) -> None:
        """显示日记"""
        now_draw = diary_panel.Diary_Panel(window_width)
        now_draw.draw()
