# -*- coding: UTF-8 -*-
"""
连续数值带零头时，面板文字与整数时相同
======================================
开新游戏，博士以同一处的一名干员为交互对象。两人的每个连续数值（体力、气力、理智、射精欲、精液、疲劳、尿意、
饥饿、困倦、醉酒、各状态值、身体各部位的当前精液量、乳汁量）先设为整数 n 绘制一次，再设为 n + 1/3 绘制一次：
状态头（体力、气力、理智、精液条与状态标识）、状态栏（各状态的等级与数值条，H 外与 H 中各一次）、
身体栏（博士开着生理透视：各部位精液污浊与乳汁量）绘出的文字两次相同。
数值条在 n 取上限时宽度相同（n + 1/3 只多出不到一格）。

结算文字只列出玩家看得到的变化：干员的两个状态各记下 +1/3 与 -1/3 的变化、显示值没变，不列出；
第三个状态记下 +2、显示值也加了 2，列出「+2」。
"""

import importlib
from collections.abc import Callable
from fractions import Fraction
from unittest import mock

from tests.slow.base import SlowTestCase
from tests import chara_abilities as ca, kernel_data
from tests.chara_activity import aim
from tests.kernel_project import activity
from tests.kernel_project import identity

WIDTH = 120
""" 绘制宽度 """
THIRD = Fraction(1, 3)
""" 加在每个连续数值上的零头 """
H_METERS_MAX = {"semen": "semen_max"}
""" h.meters 里有上限、画成数值条的连续数值到它的上限项：n 取上限 """
NEEDS_MAX = {"hit": "hit_max", "mana": "mana_max", "sanity": "sanity_max"}
""" body.needs 里有上限、画成数值条的连续数值到它的上限项：n 取上限 """
H_METERS = ("eja",)
""" h.meters 里其余的连续数值：n 取 10 """
NEEDS = ("tired", "urine", "hunger", "milk", "sleep", "drunk")
""" body.needs 里其余的连续数值：n 取 10 """
STATUS_VALUE = 1000
""" 各状态值的 n """


class NumDisplayTest(SlowTestCase):
    """连续数值的零头不出现在面板文字里，也不让结算文字多出一行"""

    def setUp(self) -> None:
        """
        开新游戏，博士以一名干员为交互对象，两人在同一处。GameState 数据的读写记在以当前状态为底的缓冲区里
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.player = identity.of(0)
        self.operator_id = min(
            cid for cid in kernel_data.domain("roster").active() if cid != 0
        )
        self.operator = identity.of(self.operator_id)
        kernel_data.put(
            activity.set_position,
            self.operator.cid,
            list(activity.position(self.player.cid)),
        )
        aim(self.player.cid, self.operator_id)
        kernel_data.put(
            kernel_data.domain("player_ability").set,
            self.player.cid,
            visual=True,
        )
        ca.talent(self.player)[309] = 1
        core = importlib.import_module("Script.Kernel.core")
        working = importlib.import_module(
            "Script.Modules.gameplay_resolution.working"
        )
        self.enterContext(working.based_on(core.state()))

    def set_values(self, extra: Fraction) -> None:
        """
        把两人的每个连续数值设为 n + extra
        Keyword arguments:
        extra -- 加在 n 上的零头
        Return arguments:
        无
        """
        from Script.Modules.domains import status

        dirty = importlib.import_module("Script.Modules.domains.dirty")
        h_meters = importlib.import_module("Script.Modules.domains.h_meters")
        needs = importlib.import_module("Script.Modules.domains.needs")
        for character in (self.player, self.operator):
            needs.set(character.cid, **dict.fromkeys(NEEDS, 10 + extra))
            current = needs.of(character.cid)
            needs.set(
                character.cid,
                **{k: current[m] + extra for k, m in NEEDS_MAX.items()},
            )
            meters = h_meters.of(character.cid)
            h_meters.set(
                character.cid,
                **{k: meters[m] + extra for k, m in H_METERS_MAX.items()},
                **dict.fromkeys(H_METERS, 10 + extra),
            )
            for status_id in status.of(character.cid):
                kernel_data.put(
                    status.set, character.cid, status_id, STATUS_VALUE + extra
                )
            with dirty.editing(character.cid) as d:
                for slot in d.body_semen.values():
                    slot[1] = 10 + extra
                    slot[2] = 1

    def screen(self, extra: Fraction) -> list[str]:
        """
        数值设为 n + extra 后绘制状态头、状态栏（H 外与 H 中）与身体栏，返回绘出的文字
        Keyword arguments:
        extra -- 加在 n 上的零头
        Return arguments:
        list[str] -- 按绘制顺序的文字
        """
        character_info_head = importlib.import_module(
            "Script.UI.Panel.character_info_head"
        )
        dirty_panel = importlib.import_module("Script.UI.Panel.dirty_panel")
        see_character_info_panel = importlib.import_module(
            "Script.UI.Panel.see_character_info_panel"
        )

        self.set_values(extra)
        drawn: list[str] = []

        def draw(paint: Callable[[], None]) -> None:
            """绘制一个面板，收下它绘出的文字（屏幕只留最近的一段，所以逐个面板收）"""
            self.world.player.screen.clear()
            paint()
            self.assertLess(
                len(self.world.player.screen), self.world.player.SCREEN_LIMIT
            )
            drawn.extend(self.world.player.screen)

        for cid in (0, self.operator_id):
            draw(character_info_head.CharacterInfoHead(cid, WIDTH).draw)
        for in_h in (False, True):
            kernel_data.put(
                kernel_data.domain("flags").set, self.player.cid, is_h=in_h
            )
            kernel_data.put(
                kernel_data.domain("flags").set, self.operator.cid, is_h=in_h
            )
            for cid in (0, self.operator_id):
                draw(
                    see_character_info_panel.SeeCharacterStatusPanel(
                        cid, WIDTH, 7, 0, False
                    ).draw
                )
                draw(
                    dirty_panel.SeeCharacterBodyPanel(
                        cid, WIDTH, 9, 0, False
                    ).draw
                )
        return drawn

    def test_panels_same_text_with_thirds(self) -> None:
        """n 与 n + 1/3 绘出的状态头、状态栏与身体栏文字相同"""
        whole = self.screen(Fraction(0))
        self.assertIn("乳汁量为10ml", "".join(whole))
        self.assertEqual(self.screen(THIRD), whole)

    def test_settle_text_lists_only_seen_changes(self) -> None:
        """显示值没变的 ±1/3 不列出，显示值变了 2 的列出 +2"""
        from Script.Modules.domains import status

        from Script.Config import normal_config

        game_config = importlib.import_module("Script.Config.game_config")
        game_type = importlib.import_module("Script.Core.game_type")
        settle_behavior = importlib.import_module(
            "Script.Design.settle_behavior"
        )

        self.set_values(Fraction(0))
        quiet_up, quiet_down, seen = sorted(status.of(self.operator.cid))[:3]
        kernel_data.put(
            status.set, self.operator.cid, quiet_up, STATUS_VALUE + THIRD
        )
        kernel_data.put(status.set, self.operator.cid, quiet_down, STATUS_VALUE)
        kernel_data.put(status.set, self.operator.cid, seen, STATUS_VALUE + 2)
        change = game_type.CharacterStatusChange()
        target_change = game_type.TargetChange()
        target_change.status_data = {
            quiet_up: THIRD,
            quiet_down: -THIRD,
            seen: 2,
        }
        change.target_change[self.operator_id] = target_change
        normal_config.system_setting.draw_setting[7] = 1
        now_time = activity.behavior(self.player.cid).start_time
        with mock.patch.object(
            settle_behavior, "handle_instruct_data", return_value=change
        ):
            panel = settle_behavior.handle_settle_behavior(0, now_time)
        self.assertIsNotNone(panel)
        self.world.player.screen.clear()
        panel.draw()
        text = "".join(self.world.player.screen)
        names = {
            sid: game_config.config_character_state[sid].name
            for sid in (quiet_up, quiet_down, seen)
        }
        self.assertIn(names[seen], text)
        self.assertIn("+2", text)
        self.assertNotIn(names[quiet_up], text)
        self.assertNotIn(names[quiet_down], text)
