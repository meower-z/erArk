# -*- coding: UTF-8 -*-
"""
H中与疲劳时，Tk指令面板按 InstructConfig.csv 的H模式显示类型与疲劳类型隐藏指令
==============================================================================
h_mode_show_type 列为1的指令在H中不显示，tired_type 列为1或2的指令在疲劳过高时不显示。
这两列对 premise_set 列为空的指令同样生效。
每个测试开一局新游戏，画一次Tk指令面板，读出面板列出的指令。
H中的测试照搬 test_ambush_event_keeps_door_locked 的开场，让博士与杜宾在会议室进入H。
此时面板列出 wait_5_min_in_h，不列出 h_mode_show_type 为1的指令。
疲劳的测试把博士的疲劳值设为150（满值160），面板列出 wait，不列出 tired_type 不为0的指令。
"""

import importlib

from tests.slow.base import SlowTestCase

ROOM = ["中枢", "会议室"]
PANEL_WIDTH = 100
""" 指令面板的绘制宽度 """
TIRED_POINT = 150
""" 博士的疲劳值，150/160 高于前提 TIRED_LE_84 的0.84与 TIRED_LE_74 的0.74 """


class InstructColumnsHideTest(SlowTestCase):
    """H中与疲劳时，面板按指令的H模式显示类型与疲劳类型隐藏指令"""

    def listed_columns(self) -> dict[str, tuple[int, int]]:
        """
        画一次Tk指令面板，返回面板列出的每条指令在 InstructConfig.csv 的两列
        Keyword arguments:
        无
        Return arguments:
        dict -- 指令id: (h_mode_show_type, tired_type)，CSV里缺的值按0计
        """
        game_config = importlib.import_module("Script.Config.game_config")
        constant = importlib.import_module("Script.Core.constant")
        see_instruct_panel = importlib.import_module(
            "Script.System.Instruct_System.see_instruct_panel"
        )

        panel = see_instruct_panel.SeeInstructPanel(PANEL_WIDTH)
        panel.draw()
        listed: dict[str, tuple[int, int]] = {}
        for return_text in panel.return_list:
            cid = int(return_text) if str(return_text).isdigit() else None
            if cid in constant.cid_to_instruct_id:
                config = game_config.config_instruct[cid]
                listed[constant.cid_to_instruct_id[cid]] = (
                    getattr(config, "h_mode_show_type", 0),
                    getattr(config, "tired_type", 0),
                )
        return listed

    def test_in_h_hides_non_h_instructs(self) -> None:
        """H中面板不列出 h_mode_show_type 为1的指令"""
        constant = importlib.import_module("Script.Core.constant")
        handle_premise = importlib.import_module("Script.Design.handle_premise")

        self.walk(ROOM)
        operator_id = self.npc("杜宾")
        self.world.move(operator_id, ROOM)
        self.cache.character_data[
            operator_id
        ].sp_flag.npc_masturebate_for_player = True
        self.world.player.press("逆来顺受")
        self.instruct(constant.Instruct.DOOR_LOCK_INNER)
        self.world.player.check_done()
        self.assertTrue(handle_premise.handle_is_h(0), "博士与杜宾进入H")

        listed = self.listed_columns()
        self.assertIn(constant.Instruct.WAIT_5_MIN_IN_H, listed)
        self.assertEqual(
            sorted(i for i, (h_type, _) in listed.items() if h_type == 1),
            [],
            "H中列出的非H显示指令",
        )

    def test_tired_hides_tired_instructs(self) -> None:
        """疲劳值高于两条界线时，面板不列出 tired_type 不为0的指令"""
        constant = importlib.import_module("Script.Core.constant")

        self.cache.character_data[0].tired_point = TIRED_POINT
        listed = self.listed_columns()
        self.assertIn(constant.Instruct.WAIT, listed)
        self.assertEqual(
            sorted(i for i, (_, tired_type) in listed.items() if tired_type),
            [],
            "疲劳时列出的有疲劳类型的指令",
        )
