# -*- coding: UTF-8 -*-
"""
面板切换指令表测试
==================
PanelInstructsTest 核对 PANEL_INSTRUCTS 与 EXPECTED_PANEL_INSTRUCTS 一致，
并验证每条预期指令经 handle_instruct 切换到对应面板且已登记 cid 与前提条件。
"""

from unittest import mock

from Script.Config import game_config
from Script.Core import constant
from Script.Modules.gameplay_resolution import ui_hooks
from Script.System.Instruct_System import handle_instruct
from Script.UI.Moudle import view
from tests.fast.base import FastTestCase

EXPECTED_PANEL_INSTRUCTS: dict[str, int] = {
    constant.Instruct.BUY_FOOD: constant.Panel.FOOD_SHOP,
    constant.Instruct.EAT: constant.Panel.FOOD_BAG,
    constant.Instruct.MOVE: constant.Panel.SEE_MAP,
    constant.Instruct.CARRY_MOVE: constant.Panel.SEE_MAP,
    constant.Instruct.SEE_ATTR: constant.Panel.SEE_ATTR,
    constant.Instruct.BUY_H_ITEM: constant.Panel.H_ITEM_SHOP,
    constant.Instruct.ITEM: constant.Panel.ITEM,
    constant.Instruct.SAVE: constant.Panel.SAVE,
    constant.Instruct.ABL_UP: constant.Panel.ABL_UP,
    constant.Instruct.OWNER_ABL_UP: constant.Panel.OWNER_ABL_UP,
    constant.Instruct.DEBUG_ADJUST: constant.Panel.DEBUG_ADJUST,
    constant.Instruct.SYSTEM_SETTING: constant.Panel.SYSTEM_SETTING,
    constant.Instruct.TALK_QUICK_TEST: constant.Panel.TALK_QUICK_TEST,
    constant.Instruct.CHAT_WITH_AI: constant.Panel.CHAT_WITH_AI,
    constant.Instruct.BORROW_BOOK: constant.Panel.BORROW_BOOK,
    constant.Instruct.READ_BOOK: constant.Panel.READ_BOOK,
    constant.Instruct.MANAGE_LIBRARY: constant.Panel.MANAGE_LIBRARY,
    constant.Instruct.MANAGE_ASSEMBLY_LINE: constant.Panel.MANAGE_ASSEMBLY_LINE,
    constant.Instruct.MANAGE_AGRICULTURE: constant.Panel.MANAGE_AGRICULTURE,
    constant.Instruct.MANAGE_VEHICLE: constant.Panel.MANAGE_VEHICLE,
    constant.Instruct.PHYSICAL_CHECK_AND_MANAGE: constant.Panel.PHYSICAL_CHECK_AND_MANAGE,
    constant.Instruct.MANAGE_CONFINEMENT_AND_TRAINING: constant.Panel.MANAGE_CONFINEMENT_AND_TRAINING,
    constant.Instruct.MANAGE_RESOURCE_EXCHANGE: constant.Panel.MANAGE_RESOURCE_EXCHANGE,
    constant.Instruct.NAVIGATION: constant.Panel.NAVIGATION,
    constant.Instruct.MANAGE_BASEMENT: constant.Panel.MANAGE_BASEMENT,
    constant.Instruct.EDUCATION_MANAGE: constant.Panel.EDUCATION_MANAGE,
    constant.Instruct.MANAGE_DORMITORY: constant.Panel.MANAGE_DORMITORY,
    constant.Instruct.CHANGE_HYPNOSIS_MODE: constant.Panel.CHANGE_HYPNOSIS_MODE,
    constant.Instruct.DIRAY: constant.Panel.DIRAY,
    constant.Instruct.SLEEP: constant.Panel.SLEEP,
    constant.Instruct.MAKE_COFFEE_ADD: constant.Panel.MAKE_COFFEE_ADD,
    constant.Instruct.MAKE_FOOD: constant.Panel.MAKE_FOOD,
    constant.Instruct.MIXOLOGY: constant.Panel.MIXOLOGY,
    constant.Instruct.ALL_NPC_POSITION: constant.Panel.ALL_NPC_POSITION,
    constant.Instruct.GIVE_GIFT: constant.Panel.GIVE_GIFT,
    constant.Instruct.ORIGINIUM_ARTS: constant.Panel.ORIGINIUM_ARTS,
    constant.Instruct.TAKE_CARE_BABY: constant.Panel.TAKE_CARE_BABY,
    constant.Instruct.ORDER_HOTEL_ROOM: constant.Panel.ORDER_HOTEL_ROOM,
    constant.Instruct.SEE_COLLECTION: constant.Panel.COLLECTION,
    constant.Instruct.SEE_ACHIEVEMENT: constant.Panel.SEE_ACHIEVEMENT,
    constant.Instruct.SEE_FRIDGE: constant.Panel.FRIDGE,
    constant.Instruct.PREGNANCY_OVERVIEW: constant.Panel.PREGNANCY_OVERVIEW,
    constant.Instruct.FIELD_COMMISSION: constant.Panel.FIELD_COMMISSION,
    constant.Instruct.CHECK_LOCKER: constant.Panel.CHECK_LOCKER,
    constant.Instruct.ASK_HIDDEN_SEX: constant.Panel.ASK_HIDDEN_SEX,
    constant.Instruct.ASK_EXHIBITIONISM_SEX: constant.Panel.ASK_EXHIBITIONISM_SEX,
    constant.Instruct.PLAY_GOMOKU: constant.Panel.PLAY_GOMOKU,
    constant.Instruct.TASTE_WINE: constant.Panel.FOOD_BAG,
    constant.Instruct.AROMATHERAPY: constant.Panel.AROMATHERAPY,
    constant.Instruct.ASSISTANT_ADJUSTMENTS: constant.Panel.ASSISTANT,
    constant.Instruct.BUILDING: constant.Panel.BUILDING,
    constant.Instruct.EQUIPMENT_MAINTAIN: constant.Panel.EQUIPMENT_MAINTAIN,
    constant.Instruct.RECRUITMENT: constant.Panel.RECRUITMENT,
    constant.Instruct.VISITOR_SYSTEM: constant.Panel.VISITOR,
    constant.Instruct.NATION_DIPLOMACY: constant.Panel.NATION_DIPLOMACY,
    constant.Instruct.PRTS: constant.Panel.PRTS,
    constant.Instruct.MANAGE_DEDICAL_DEPARTMENT: constant.Panel.MANAGE_DEDICAL_DEPARTMENT,
    constant.Instruct.MANAGE_POWER_SYSTEM: constant.Panel.MANAGE_POWER_SYSTEM,
    constant.Instruct.BONDAGE: constant.Panel.BONDAGE,
    constant.Instruct.UNDRESS: constant.Panel.UNDRESS,
    constant.Instruct.EDIT_GROUP_SEX_TEMPLE: constant.Panel.EDIT_GROUP_SEX_TEMPLE,
}
""" 61 条纯面板切换指令的预期映射表（指令 id 到面板 id），独立列出以校验表项完整与面板切换行为 """


class PanelInstructsTest(FastTestCase):
    """PANEL_INSTRUCTS 表项核对，以及各预期指令的面板切换与 cid、前提登记测试。"""

    def setUp(self) -> None:
        """
        调用父类准备，创建角色 0（博士）与角色 1（阿米娅），并将 view.now_panel_id 临时设为 Panel.IN_SCENE。
        随后在 ui_hooks 的面板切换回调末尾追加 self.panels.append 以记录目标面板，并保留现有 Tk 回调。
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")
        self.enterContext(
            mock.patch.object(view, "now_panel_id", constant.Panel.IN_SCENE)
        )
        self.panels: list[int] = []
        self.enterContext(
            mock.patch.object(
                ui_hooks,
                "_panel_switches",
                [*ui_hooks._panel_switches, self.panels.append],
            )
        )

    def test_table_lists_every_panel_instruct(self) -> None:
        """验证 handle_instruct.PANEL_INSTRUCTS 与 EXPECTED_PANEL_INSTRUCTS 完全一致。"""
        self.assertEqual(
            handle_instruct.PANEL_INSTRUCTS, EXPECTED_PANEL_INSTRUCTS
        )

    def test_each_instruct_opens_its_panel(self) -> None:
        """
        验证遍历 EXPECTED_PANEL_INSTRUCTS 逐项经 handle_instruct 执行后，记录器仅收到一次对应面板编号。
        同时断言每项的目标面板不为 IN_SCENE，且 view.now_panel_id 随之更新为该面板编号。
        """
        for instruct_id, panel_id in EXPECTED_PANEL_INSTRUCTS.items():
            with self.subTest(instruct_id=instruct_id):
                self.panels.clear()
                view.now_panel_id = constant.Panel.IN_SCENE
                self.assertNotEqual(panel_id, constant.Panel.IN_SCENE)
                handle_instruct.handle_instruct(instruct_id)
                self.assertEqual(self.panels, [panel_id])
                self.assertEqual(view.now_panel_id, panel_id)

    def test_each_instruct_has_a_menu_entry(self) -> None:
        """
        验证 EXPECTED_PANEL_INSTRUCTS 中每条指令的 constant.instruct_id_to_cid 与 game_config 配置行 cid 一致，
        且已登记在 constant.instruct_premise_data 中，满足执行入口调度要求。
        同时断言其在 constant.instruct_type_data 中恰好仅属于配置 instruct_type 对应的类型，确保指令菜单按类列出。
        """
        for instruct_id in EXPECTED_PANEL_INSTRUCTS:
            with self.subTest(instruct_id=instruct_id):
                cid = game_config.config_instruct_by_id[instruct_id]
                row = game_config.config_instruct[cid]
                self.assertEqual(constant.instruct_id_to_cid[instruct_id], cid)
                self.assertIn(instruct_id, constant.instruct_premise_data)
                self.assertEqual(
                    [
                        instruct_type
                        for instruct_type, ids in constant.instruct_type_data.items()
                        if instruct_id in ids
                    ],
                    [getattr(constant.InstructType, row.instruct_type)],
                )
