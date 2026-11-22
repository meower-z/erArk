# -*- coding: UTF-8 -*-
"""
场景里内嵌的子面板：点一下改了世界，就是一个 0 分钟的 Edit
============================================================
场景面板本身不开草稿（每次选择都读全部角色），它里面画的子面板的按钮自己开草稿：
- H 中的服装穿脱按钮（cloth_panel.SwitchClothButton）脱下交互对象的一件衣服：内核开始玩家的一个 0 分钟 Edit，
  时钟不动，玩家在同一分钟里再选；选择期间缓存的指纹不变；Edit 之后那件衣服在 cloth_off 里，
  下一次选择取消（player_pick.back）之后也还在。
- 立绘按钮（chara_image_list_panel.CharacterImageButton）与场景角色名按钮换交互对象：同样是一个 0 分钟 Edit。
"""

import importlib
from collections.abc import Callable
from typing import TYPE_CHECKING

from tests.slow.base import SlowTestCase
from tests import kernel_data

if TYPE_CHECKING:
    from Script.Kernel import core


class InlineSubpanelTest(SlowTestCase):
    """场景内嵌子面板的点击"""

    def setUp(self) -> None:
        """开新游戏，让一名干员与玩家在同一处并作为交互对象，记下内核开始的每个行动"""
        super().setUp()
        self.core = importlib.import_module("Script.Kernel.core")
        self.edits = importlib.import_module(
            "Script.Modules.gameplay_resolution.edits"
        )
        self.pick_guard = importlib.import_module("tests.pick_guard")
        self.tests_world = importlib.import_module("tests.world")
        self.started: list[core.Action] = []
        saved = self.core._bodies["kernel.StartAction"]

        def spy(act: "core.Action") -> "core.Effects":
            self.started.append(act)
            return saved(act)

        self.core._bodies["kernel.StartAction"] = spy
        self.addCleanup(
            self.core._bodies.__setitem__, "kernel.StartAction", saved
        )
        player = self.cache.character_data[0]
        self.npcs = sorted(kernel_data.domain("roster").active())[:2]
        for cid in self.npcs:
            self.world.move(cid, player.position)
        player.target_character_id = self.npcs[0]

    def run_pick(self, fn: "Callable[[], None]") -> tuple[int, int, bool]:
        """
        玩家这一次选择跑 fn
        Return arguments:
        tuple -- (选择前的分钟, 推进到玩家下一次选行动时的分钟, 选择期间指纹变了)
        """
        changed: list[bool] = []

        def pick() -> None:
            before = self.pick_guard.fingerprint()
            try:
                fn()
            finally:
                changed.append(self.pick_guard.fingerprint() != before)

        clock = self.core.state().clock
        self.started.clear()
        self.tests_world.act(pick)
        return clock, self.core.state().clock, changed[0]

    def player_starts(self) -> list[tuple[str, int]]:
        """这次选择以来玩家开始的行动：(action_id, 分钟数)"""
        return [(a.action_id, a.duration) for a in self.started if a.who == "0"]

    def test_cloth_switch_commits_edit_and_stays(self) -> None:
        """H 中脱下一件衣服：一个 0 分钟 Edit，之后衣服在 cloth_off；下一次选择取消也不会穿回去"""
        cloth_panel = importlib.import_module("Script.UI.Panel.cloth_panel")
        game_config = importlib.import_module("Script.Config.game_config")
        cloth_id = min(game_config.config_clothing_tem)
        clothing_type = game_config.config_clothing_tem[cloth_id].clothing_type
        target = self.cache.character_data[self.npcs[0]]
        target.cloth.cloth_wear[clothing_type] = [cloth_id]
        target.cloth.cloth_off[clothing_type] = []

        def click() -> None:
            panel = cloth_panel.SwitchCharacterClothPanel(0, 120, 20, 0, False)
            cloth_panel.SwitchClothButton(
                cloth_id, clothing_type, True, panel
            ).switch_cloth()

        start, end, changed = self.run_pick(click)
        self.assertEqual(self.player_starts(), [(self.edits.EDIT, 0)])
        self.assertEqual(end, start)
        self.assertFalse(changed, "点击时缓存被写了")
        target = self.cache.character_data[self.npcs[0]]
        self.assertIn(cloth_id, target.cloth.cloth_off[clothing_type])
        self.assertNotIn(cloth_id, target.cloth.cloth_wear[clothing_type])

        player_pick = importlib.import_module(
            "Script.Modules.tk_ui.player_pick"
        )

        self.run_pick(player_pick.back)
        target = self.cache.character_data[self.npcs[0]]
        self.assertIn(cloth_id, target.cloth.cloth_off[clothing_type])

    def test_target_clicks_commit_edit(self) -> None:
        """立绘按钮与场景角色名按钮换交互对象：各是一个 0 分钟 Edit，之后交互对象已换"""
        image = importlib.import_module(
            "Script.UI.Panel.chara_image_list_panel"
        )
        info = importlib.import_module(
            "Script.UI.Panel.see_character_info_panel"
        )
        start, end, changed = self.run_pick(
            image.CharacterImageButton(self.npcs[1], 120).change_target
        )
        self.assertEqual(self.player_starts(), [(self.edits.EDIT, 0)])
        self.assertEqual(end, start)
        self.assertFalse(changed)
        self.assertEqual(
            self.cache.character_data[0].target_character_id, self.npcs[1]
        )
        name_button = info.SeeCharacterInfoByNameDrawInScene(
            str(self.npcs[0]), 120, True, False, 0
        )
        start, end, changed = self.run_pick(name_button.see_character)
        self.assertEqual(self.player_starts(), [(self.edits.EDIT, 0)])
        self.assertEqual(end, start)
        self.assertFalse(changed)
        self.assertEqual(
            self.cache.character_data[0].target_character_id, self.npcs[0]
        )
