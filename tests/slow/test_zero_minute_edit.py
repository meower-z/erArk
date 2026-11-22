# -*- coding: UTF-8 -*-
"""
零分钟的界面编辑。面板里改了游戏状态，确认后是一个 0 分钟的 Edit，玩家在同一分钟里接着选
========================================================================================
- 动力系统管理面板里把一个区块的供电策略调高一档再退出。内核开始玩家的一个行动，是 0 分钟的 Edit。
  时钟不动，玩家在同一分钟里再选。Edit 开始之后，GameState 的 base.power_strategy 里只有这个区块的新策略。
  面板运行期间（定下 Edit 之前），缓存的指纹与 GameState 的全局数据都不变。
- 蓄电池管理里加一台 L1 蓄电池再退出，也是一个 0 分钟的 Edit。面板运行期间缓存的指纹与全局数据不变。
  Edit 之后 GameState 的 base.power 里有这台蓄电池。
- 基建面板里把访客区升到 2 级再退出，也是一个 0 分钟的 Edit。面板运行期间缓存的指纹与全局数据不变。
  Edit 之后 GameState 的 base.facility_level 里访客区是 2 级。
- 打开面板什么也不改就退出。没有行动，缓存的指纹不变。
- 面板里改过之后整个选择取消（player_pick.back）。没有行动，策略不变。
- 下 constant.Instruct.SLEEP_OBSCENITY 指令。交互对象进入对应的模式，也是一个 0 分钟的 Edit。
"""

from collections.abc import Callable

from tests.slow.base import SlowTestCase
from tests import kernel_data
from tests.chara_activity import aim
from tests.kernel_project import activity

VISITOR_ZONE = 13
""" 访客区的设施id """


class ZeroMinuteEditTest(SlowTestCase):
    """零分钟的界面编辑"""

    def setUp(self) -> None:
        """开新游戏，记下内核开始的每个行动"""
        super().setUp()
        from Script.Kernel import core

        self.started: list[core.Action] = []
        saved = core._bodies["kernel.StartAction"]

        def spy(act: core.Action) -> core.Effects:
            self.started.append(act)
            return saved(act)

        core._bodies["kernel.StartAction"] = spy
        self.addCleanup(core._bodies.__setitem__, "kernel.StartAction", saved)

    def run_pick(self, fn: "Callable[[], None]") -> tuple[int, int, bool]:
        """
        玩家这一次选择跑 fn；记下选择期间（fn 结束或抛出之前）缓存的指纹是否变了
        Return arguments:
        tuple -- (选择前的分钟, 推进到玩家下一次选行动时的分钟, 选择期间指纹变了)
        """
        from Script.Kernel import core
        from tests import pick_guard, world

        changed: list[bool] = []
        self.data_moved: list[bool] = []

        def pick() -> None:
            before = pick_guard.fingerprint()
            data = core.state().data
            try:
                fn()
            finally:
                changed.append(pick_guard.fingerprint() != before)
                self.data_moved.append(core.state().data is not data)

        clock = core.state().clock
        self.started.clear()
        world.act(pick)
        return clock, core.state().clock, changed[0]

    def player_starts(self) -> list[tuple[str, int]]:
        """这次选择以来玩家开始的行动：(action_id, 分钟数)"""
        return [(a.action_id, a.duration) for a in self.started if a.who == "0"]

    def open_power(self) -> None:
        """「管理能源系统」指令做的事：面板id换成动力系统管理面板（指令要在动力区才列出，这里直接换面板）"""
        from Script.UI.Moudle import view
        from Script.Core import constant

        view.now_panel_id = constant.Panel.MANAGE_POWER_SYSTEM

    def show(self) -> None:
        """显示此刻的面板（与主循环的一轮相同）"""
        from Script.UI.Moudle import view
        from Script.Core import constant

        constant.panel_data[view.now_panel_id]()
        self.world.player.check_done()

    def strategy(self) -> dict[int, int]:
        """各区块此刻的供电策略（未登记的按默认值）"""
        from Script.Config import game_config
        from Script.Modules.domains import power

        return {
            cid: power.strategy_of(cid)
            for cid, data in game_config.config_facility.items()
            if data.type == -1
        }

    def test_power_change_commits_one_edit(self) -> None:
        """调高一档供电策略再退出：一个 0 分钟的 Edit，时钟不动，Edit 之后策略已改，选择期间缓存不变"""
        from Script.Kernel import core
        from Script.Modules.domains import power
        from Script.Modules.gameplay_resolution import edits

        self.open_power()
        before = self.strategy()
        self.world.player.press("供电策略调整", "[+]", "返回", "返回")
        start, end, changed = self.run_pick(self.show)
        self.assertEqual(self.player_starts(), [(edits.EDIT, 0)])
        self.assertEqual(end, start)
        self.assertFalse(changed, "面板运行期间缓存被写了")
        self.assertEqual(self.data_moved, [False], "面板运行期间全局数据变了")
        after = self.strategy()
        moved = {cid for cid in before if before[cid] != after[cid]}
        self.assertEqual(len(moved), 1, f"{before} -> {after}")
        (zone,) = moved
        stored = core.state().data[power.KEY]
        self.assertEqual(stored, {str(zone): after[zone]})

    def test_battery_change_commits_one_edit(self) -> None:
        """
        加一台 L1 蓄电池再退出，是一个 0 分钟的 Edit
        面板运行期间缓存与全局数据不变，Edit 之后 base.power 里有这台蓄电池
        """
        from Script.Kernel import core
        from Script.Modules.domains import power
        from Script.Modules.gameplay_resolution import edits

        self.open_power()
        self.world.player.press("蓄电池管理", "[+]", "返回", "返回")
        _start, _end, changed = self.run_pick(self.show)
        self.assertEqual(self.player_starts(), [(edits.EDIT, 0)])
        self.assertFalse(changed, "面板运行期间缓存被写了")
        self.assertEqual(self.data_moved, [False], "面板运行期间全局数据变了")
        stored = power.plant(core.state())
        self.assertEqual(stored["batteries"], (1, 0, 0))

    def test_facility_upgrade_commits_one_edit(self) -> None:
        """
        基建面板里把访客区升到 2 级再退出，玩家开始的行动只有一个 0 分钟的 Edit。
        面板运行期间缓存与全局数据不变。Edit 之后内核状态的 base.facility_level 里访客区是 2 级
        """
        from Script.Core import constant
        from Script.Kernel import core
        from Script.Modules.domains import facility
        from Script.Modules.gameplay_resolution import edits
        from Script.UI.Moudle import view

        view.now_panel_id = constant.Panel.BUILDING
        self.world.player.press("访客区", "【升级】", "返回")
        _start, _end, changed = self.run_pick(self.show)
        self.assertEqual(self.player_starts(), [(edits.EDIT, 0)])
        self.assertFalse(changed, "面板运行期间缓存被写了")
        self.assertEqual(self.data_moved, [False], "面板运行期间全局数据变了")
        self.assertEqual(facility.level(VISITOR_ZONE, game=core.state()), 2)

    def test_open_and_leave_commits_nothing(self) -> None:
        """打开面板直接退出：没有行动，缓存不变"""
        self.open_power()
        self.world.player.press("返回")
        start, end, changed = self.run_pick(self.show)
        self.assertEqual(self.player_starts(), [])
        self.assertEqual(end, start)
        self.assertFalse(changed)

    def test_back_after_change_keeps_nothing(self) -> None:
        """面板里调过策略之后取消整个选择：没有行动，策略不变"""
        from Script.Modules.tk_ui import player_pick

        self.open_power()
        before = self.strategy()
        self.world.player.press("供电策略调整", "[+]", "返回", "返回")

        def change_then_back() -> None:
            with player_pick.drafting("test"):
                self.show()
                player_pick.back()

        self.run_pick(change_then_back)
        self.assertEqual(self.player_starts(), [])
        self.assertEqual(self.strategy(), before)

    def test_sleep_obscenity_commits_edit(self) -> None:
        """对同一场景里的干员下睡眠猥亵指令：一个 0 分钟的 Edit，之后她在睡眠猥亵模式里"""
        from Script.Core import constant
        from Script.Design import map_handle
        from Script.Modules.gameplay_resolution import edits
        from Script.System.Instruct_System import handle_instruct

        target = sorted(kernel_data.domain("roster").active())[0]
        self.world.move(target, activity.position(0))
        aim(0, target)
        scene = map_handle.get_map_system_path_str_for_list(
            activity.position(0)
        )
        self.cache.scene_data[scene].close_flag = 1
        kernel_data.put(
            kernel_data.domain("flags").set, target, unconscious_h=0
        )
        start, end, changed = self.run_pick(
            lambda: handle_instruct.handle_instruct(
                constant.Instruct.SLEEP_OBSCENITY
            )
        )
        self.assertEqual(self.player_starts(), [(edits.EDIT, 0)])
        self.assertEqual(end, start)
        self.assertFalse(changed)
        self.assertEqual(
            kernel_data.domain("flags").get(target, "unconscious_h"), 1
        )
