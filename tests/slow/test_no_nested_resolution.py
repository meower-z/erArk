# -*- coding: UTF-8 -*-
"""
结算途中不嵌套调用结算函数
==========================================================
开新游戏，博士与阿米娅进一间能锁门的空房间；博士下「邀请H」进入H。
博士每次下「等待五分钟」，在他这一行动的开始结算里（行动前的前置结算处）跑一个要测的地方，
记下 player_pick.choose、judge_character_status 与 chara_handle_instruct_common_settle 的调用：
- 结算途中（core.in_settlement() 为真）调用 choose 算嵌套；
- 结算途中，这三个之一还没返回时又调用其中之一，也算嵌套。
要测的地方：等对方行动结束（效果 1701）、开关体控-逆推（效果 1228）、事件的寻路移动（效果 move 寻路）、
旁人目睹H（状态机 SEE_H_AND_MOVE_TO_DORMITORY，发现者选「尴尬地结束H」）。
- 四处都走到，且没有嵌套；
- 目睹H：发现者的打断反应与博士的被打断各结算一次，「结束H模式」只显示一次，
  发现者被打断，在博士这一行动结束前就打开了被发现面板；
- 寻路移动：博士最终走到目标地点，走的段数有上限。
"""

import contextlib
import datetime
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING
from unittest import mock

from tests.slow.base import SlowTestCase
from tests import kernel_data

if TYPE_CHECKING:
    from typing import Any

PARTNER_NAME = "阿米娅"
""" 和博士H的干员 """
FAVORABILITY = 10000
""" 她对博士的好感，与信赖一起让「邀请H」成功 """
TRUST = 200
""" 她对博士的信赖 """
MAX_LEGS = 30
""" 寻路移动最多走的段数 """
END_H_TEXT = "结束H模式"
""" 结束H时显示的文字 """


class NoNestedResolutionTest(SlowTestCase):
    """结算途中接着做的行动排进计划队列，不在当场开始"""

    def setUp(self) -> None:
        """
        开新游戏，记下调用
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.nested: list[str] = []
        """ 嵌套的调用：函数名与当时的角色和行为 """
        self.settled: list[tuple[int, str]] = []
        """ 结算过的 (角色id, 行为id) """
        self.texts: list[str] = []
        """ 等待确认的文字 """
        self.depth = 0
        """ 结算途中还没返回的被测函数的个数 """

    def watched(
        self, name: str, fn: "Callable[..., Any]"
    ) -> "Callable[..., Any]":
        """
        包一层：结算途中调用时检查嵌套
        Keyword arguments:
        name -- 函数名
        fn -- 原函数
        Return arguments:
        Callable -- 包好的函数
        """
        from Script.Kernel import core

        def call(*args: "Any", **kwargs: "Any") -> "Any":
            """
            调用原函数；结算途中调用时，choose 或已有被测函数没返回就记为嵌套
            Keyword arguments:
            args -- 原函数的参数
            kwargs -- 原函数的参数
            Return arguments:
            Any -- 原函数的返回值
            """
            if not core.in_settlement():
                return fn(*args, **kwargs)
            if name == "choose" or self.depth:
                self.nested.append(f"{name}{args}")
            if name == "judge_character_status":
                behavior_id = self.cache.character_data[args[0]].behavior
                self.settled.append((args[0], behavior_id.behavior_id))
            self.depth += 1
            try:
                return fn(*args, **kwargs)
            finally:
                self.depth -= 1

        return call

    @contextlib.contextmanager
    def watching(self) -> Iterator[None]:
        """
        换上包好的三个函数，并记下等待确认的文字
        Keyword arguments:
        无
        Return arguments:
        无
        """
        from Script.Design import character_behavior
        from Script.Modules.tk_ui import player_pick
        from Script.System.Instruct_System import handle_instruct
        from Script.UI.Moudle import draw

        real_wait_draw = draw.WaitDraw.draw

        def record_wait_draw(drawn: draw.WaitDraw) -> None:
            """
            记下文字后照常绘制
            Keyword arguments:
            drawn -- 绘制对象
            Return arguments:
            无
            """
            self.texts.append(str(drawn.text))
            real_wait_draw(drawn)

        with (
            mock.patch.object(
                player_pick,
                "choose",
                self.watched("choose", player_pick.choose),
            ),
            mock.patch.object(
                character_behavior,
                "judge_character_status",
                self.watched(
                    "judge_character_status",
                    character_behavior.judge_character_status,
                ),
            ),
            mock.patch.object(
                handle_instruct,
                "chara_handle_instruct_common_settle",
                self.watched(
                    "chara_handle_instruct_common_settle",
                    handle_instruct.chara_handle_instruct_common_settle,
                ),
            ),
            mock.patch.object(draw.WaitDraw, "draw", record_wait_draw),
        ):
            yield

    def wait_running(self, site: "Callable[[], None]") -> None:
        """
        博士等待五分钟，site 在这一行动的开始结算里（行动前的前置结算处）跑一次
        Keyword arguments:
        site -- 要测的地方
        Return arguments:
        无
        """
        from Script.Core import constant
        from Script.Design import character_behavior
        from Script.System.Instruct_System import handle_instruct
        from tests import world

        real_pre_step = character_behavior.judge_before_pl_behavior
        pending = [site]

        def pre_step() -> None:
            """
            第一次调用时先跑 site
            Keyword arguments:
            无
            Return arguments:
            无
            """
            while pending:
                pending.pop()()
            real_pre_step()

        def wait() -> None:
            """玩家这一次选行动：等待五分钟"""
            handle_instruct.chara_handle_instruct_common_settle(
                constant.Behavior.WAIT, duration=5
            )

        with mock.patch.object(
            character_behavior, "judge_before_pl_behavior", pre_step
        ):
            world.act(wait)
        self.assertEqual(pending, [], "要测的地方在博士的行动开始时跑过")

    def start_h(self) -> int:
        """
        博士与阿米娅进一间能锁门的空房间，经「邀请H」进入H
        Keyword arguments:
        无
        Return arguments:
        int -- 她的角色id
        """
        from Script.Core import constant
        from Script.Design import map_handle

        player = self.cache.character_data[0]
        partner_id = self.npc(PARTNER_NAME)
        partner = self.cache.character_data[partner_id]
        room_key = next(
            key
            for key, scene in sorted(self.cache.scene_data.items())
            if scene.close_type == 1 and not scene.character_list
        )
        self.room = map_handle.get_map_system_path_for_str(room_key)
        self.world.move(0, self.room)
        self.world.move(partner_id, self.room)
        partner.favorability[0] = FAVORABILITY
        partner.trust = TRUST
        player.target_character_id = partner_id
        self.instruct(constant.Instruct.DO_H)
        self.assertTrue(kernel_data.domain("flags").get(0, "is_h"), "博士在H中")
        return partner_id

    def test_sites_plan_instead_of_nesting(self) -> None:
        """四处都在结算途中走到，没有嵌套"""
        from Script.Core import constant, game_type
        from Script.Design import settle_behavior
        from Script.Settle import default

        partner_id = self.start_h()
        finder_id = next(
            cid
            for cid in sorted(kernel_data.domain("roster").active())
            if cid not in (0, partner_id)
        )
        reached: list[str] = []

        def wait_partner() -> None:
            """效果 1701：博士等对方行动结束"""
            from Script.Design import game_time

            partner = self.cache.character_data[partner_id]
            partner.behavior.start_time = game_time.now()
            partner.behavior.duration = 30
            default.handle_wait_unitl_traget_action_end(
                0, 5, game_type.CharacterStatusChange(), game_time.now()
            )
            reached.append("A1")

        def active_h_switch() -> None:
            """效果 1228：开关体控-逆推"""
            from Script.Design import game_time

            default.handle_target_hypnosis_active_h_switch_change(
                0, 5, game_type.CharacterStatusChange(), game_time.now()
            )
            reached.append("A2")

        def discovery() -> None:
            """状态机：旁人目睹H，选出的行动排进发现者的计划队列并打断她"""
            self.world.move(finder_id, self.room)
            self.world.player.press("尴尬地结束H")
            constant.handle_state_machine_data[
                constant.StateMachine.SEE_H_AND_MOVE_TO_DORMITORY
            ](finder_id)
            reached.append("discovery")

        def event_move() -> None:
            """效果 move 寻路：事件让博士走到另一处"""
            tag = self.far_place_tag()
            settle_behavior.handle_comprehensive_value_effect(
                0,
                ["A1", "Move|0", "寻路", tag],
                game_type.CharacterStatusChange(),
            )
            reached.append("A13")

        with self.watching():
            for site in (wait_partner, active_h_switch, discovery):
                self.wait_running(site)
            kernel_data.put(kernel_data.domain("flags").set, 0, is_h=False)
            self.cache.character_data[0].behavior.behavior_id = (
                constant.Behavior.SHARE_BLANKLY
            )
            self.wait_running(event_move)
        self.world.player.check_done()
        self.assertEqual(reached, ["A1", "A2", "discovery", "A13"])
        self.assertEqual(self.nested, [], "结算途中没有嵌套的调用")

    def far_place_tag(self) -> str:
        """
        一个地点标签：它的地点都不是博士所在的地点
        Keyword arguments:
        无
        Return arguments:
        str -- 地点标签
        """
        from Script.Core import constant
        from Script.Design import map_handle

        here = map_handle.get_map_system_path_str_for_list(
            self.cache.character_data[0].position
        )
        return next(
            tag
            for tag, places in sorted(constant.place_data.items())
            if places and here not in places and "Dormitory" not in tag
        )

    def test_discovery_ends_h_once(self) -> None:
        """目睹H后发现者的反应与博士的结束H各一次，「结束H模式」只显示一次"""
        from Script.Core import constant
        from Script.Kernel import core
        from Script.System.Sex_System import sex_be_discovered_panel

        partner_id = self.start_h()
        finder_id = next(
            cid
            for cid in sorted(kernel_data.domain("roster").active())
            if cid not in (0, partner_id)
        )
        opened: list[tuple[int, int]] = []
        real_panel_draw = sex_be_discovered_panel.Sex_Be_Discovered_Panel.draw

        def panel_draw(panel: "Any") -> None:
            """
            记下打开被发现面板时的内核时钟与博士当前行动的结束时刻
            Keyword arguments:
            panel -- 面板
            Return arguments:
            无
            """
            game = core.state()
            act = game.characters["0"].action
            opened.append((game.clock, act.start + act.duration))
            real_panel_draw(panel)

        def discovery() -> None:
            """状态机：旁人目睹H，选出的行动排进发现者的计划队列并打断她"""
            self.world.move(finder_id, self.room)
            self.world.player.press("尴尬地结束H")
            constant.handle_state_machine_data[
                constant.StateMachine.SEE_H_AND_MOVE_TO_DORMITORY
            ](finder_id)

        with self.watching(), mock.patch.object(
            sex_be_discovered_panel.Sex_Be_Discovered_Panel, "draw", panel_draw
        ):
            self.wait_running(discovery)
        self.world.player.check_done()
        self.assertEqual(self.nested, [], "结算途中没有嵌套的调用")
        self.assertEqual(len(opened), 1, "被发现面板打开一次")
        clock, player_end = opened[0]
        self.assertLess(
            clock, player_end, "发现者被打断，在博士的行动结束前就来发现"
        )
        self.assertEqual(
            self.settled.count(
                (finder_id, constant.Behavior.SEE_H_AND_INTERRUPT)
            ),
            1,
            f"发现者的打断反应结算一次：{self.settled}",
        )
        self.assertEqual(
            self.settled.count((0, constant.Behavior.H_INTERRUPT)),
            1,
            f"博士的被打断结算一次：{self.settled}",
        )
        self.assertEqual(
            sum(END_H_TEXT in text for text in self.texts),
            1,
            f"「{END_H_TEXT}」显示一次",
        )

    def test_event_move_reaches_target(self) -> None:
        """事件的寻路移动让博士走到目标地点，段数有上限"""
        from Script.Design import game_time

        from Script.Core import constant, game_type
        from Script.Design import map_handle, settle_behavior

        tag = self.far_place_tag()
        targets = {
            map_handle.get_map_system_path_str_for_list(
                map_handle.get_map_system_path_for_str(place)
            )
            for place in constant.place_data[tag]
        }

        def event_move() -> None:
            """效果 move 寻路：事件让博士走到另一处"""
            settle_behavior.handle_comprehensive_value_effect(
                0,
                ["A1", "Move|0", "寻路", tag],
                game_type.CharacterStatusChange(),
            )

        start = game_time.now()
        with self.watching():
            self.wait_running(event_move)
        legs = [
            behavior_id
            for cid, behavior_id in self.settled
            if cid == 0 and behavior_id == constant.Behavior.MOVE
        ]
        here = map_handle.get_map_system_path_str_for_list(
            self.cache.character_data[0].position
        )
        self.assertEqual(self.nested, [], "结算途中没有嵌套的调用")
        self.assertIn(here, targets, "博士走到了目标地点")
        self.assertGreater(len(legs), 0, "博士走了寻路的各段")
        self.assertLessEqual(len(legs), MAX_LEGS, "段数有上限")
        self.assertGreater(
            game_time.now() - start, datetime.timedelta(minutes=5)
        )
