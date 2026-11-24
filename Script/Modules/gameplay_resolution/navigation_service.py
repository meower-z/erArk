"""
导航抵达结算服务（navigation_service）
======================================
提供罗德岛基地移动抵达的每日判定与抵达后结算逻辑。
本模块不直接导入界面模块，供每日结算入口调用。
抵达提示通过 ui_hooks.emit_notice 发出。
导航成就通过 achievement_service.settle_and_notify 结算。
"""

from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import game_time
from Script.Modules.domains import achievement, diplomacy, location, visitor
from Script.Modules.gameplay_resolution import achievement_service, ui_hooks
from Script.Modules.gameplay_resolution import roster_lifecycle_service

_: FunctionType = get_text._
""" 翻译api """


def judge_arrive() -> bool:
    """
    判断罗德岛是否抵达移动目的地，并在到达时执行抵达结算。
    未移动或尚未到达抵达时刻时，函数直接返回 False。
    到达时函数更新所在国家与访客移动标记，并切换出发国与目标国外交官的在编状态。
    随后函数经 ui_hooks.emit_notice 以 gold_enrod 样式按文本宽度发出等待确认的抵达提示。
    最后函数将国家 17 与目标国家补入已访问国家列表，并调用 achievement_service.settle_and_notify 结算导航成就。
    Keyword arguments:
    无
    Return arguments:
    bool -- 本次调用完成抵达结算时返回 True，否则返回 False
    """
    going = location.move()
    if going is not None:
        target_scene_id, arrive_time = going
        if game_time.judge_date_big_or_small(game_time.now(), arrive_time):
            now_scene_id = location.country()
            visitor.set_moved(True)
            target_scene_name = game_config.config_birthplace[
                target_scene_id
            ].name
            location.arrive()
            if now_scene_id in diplomacy.table():
                now_diplomat_chara_id = diplomacy.of(now_scene_id)["diplomat"]
                if now_diplomat_chara_id != 0:
                    roster_lifecycle_service.chara_off_line(
                        now_diplomat_chara_id
                    )
            if target_scene_id in diplomacy.table():
                target_diplomat_chara_id = diplomacy.of(target_scene_id)[
                    "diplomat"
                ]
                if target_diplomat_chara_id != 0:
                    roster_lifecycle_service.chara_on_line(
                        target_diplomat_chara_id, game_time.now()
                    )
            ui_hooks.emit_notice(
                _("\n罗德岛已抵达目的地：{0}\n").format(target_scene_name),
                wait=True,
                style="gold_enrod",
                use_text_width=True,
            )
            if 17 not in achievement.get("visited_nation_list"):
                achievement.append("visited_nation_list", 17)
            if target_scene_id not in achievement.get("visited_nation_list"):
                achievement.append("visited_nation_list", target_scene_id)
            achievement_service.settle_and_notify(_("导航"))
            return True
    return False
