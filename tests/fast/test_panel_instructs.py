# -*- coding: UTF-8 -*-
"""
面板切换与诊疗指令测试
======================
PanelInstructsTest 核对 PANEL_INSTRUCTS 与 EXPECTED_PANEL_INSTRUCTS 一致。
该测试类验证每条预期指令经操作菜单面板切换 view.now_panel_id，并检查幼年阶段拦截与菜单登记。
CurePatientInstructTest 验证 CURE_PATIENT 指令在有待诊病人时打开诊疗面板，无待诊病人时提示并留在场景面板。
"""

from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import constant, get_text
from Script.Modules.domains import medical
from Script.System.Instruct_System import handle_instruct
from Script.System.Medical_System import medical_constant as mc
from Script.UI.Moudle import view
from Script.UI.Panel import see_instruct_panel
from tests import chara_abilities as ca
from tests.chara_activity import aim
from tests.fast.base import FastTestCase
from tests.fast.test_medical_diagnose_service import DiagnoseCase, patient

CHILD = 102
""" 幼年阶段年龄素质编号（102） """
_ = get_text._
""" 本地化文本翻译函数 """
NO_PATIENT = _("\n当前没有需要诊疗的病人\n")
""" 无待诊病人时 CURE_PATIENT 指令发出的预期提示文本 """
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


def open_from_menu(instruct_id: str) -> None:
    """
    以当前配置文本宽度创建 SeeInstructPanel 实例并执行指定指令。
    Keyword arguments:
    instruct_id -- str，待执行的指令 id
    Return arguments:
    None -- 无返回值
    """
    see_instruct_panel.SeeInstructPanel(
        normal_config.config_normal.text_width
    ).handle_instruct(instruct_id)


class PanelInstructsTest(FastTestCase):
    """PANEL_INSTRUCTS 表项核对，以及操作菜单面板切换、幼年阶段拦截与菜单登记测试。"""

    def setUp(self) -> None:
        """调用父类准备，创建角色 0 与角色 1，并将 view.now_panel_id 临时设为 Panel.IN_SCENE。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")
        self.enterContext(
            mock.patch.object(view, "now_panel_id", constant.Panel.IN_SCENE)
        )

    def test_table_lists_every_panel_instruct(self) -> None:
        """验证 handle_instruct.PANEL_INSTRUCTS 与 EXPECTED_PANEL_INSTRUCTS 完全一致。"""
        self.assertEqual(
            handle_instruct.PANEL_INSTRUCTS, EXPECTED_PANEL_INSTRUCTS
        )

    def test_each_instruct_opens_its_panel(self) -> None:
        """验证每条预期指令均映射到非 IN_SCENE 面板，且经操作菜单执行后将 view.now_panel_id 设为该面板。"""
        for instruct_id, panel_id in EXPECTED_PANEL_INSTRUCTS.items():
            with self.subTest(instruct_id=instruct_id):
                view.now_panel_id = constant.Panel.IN_SCENE
                self.assertNotEqual(panel_id, constant.Panel.IN_SCENE)
                open_from_menu(instruct_id)
                self.assertEqual(view.now_panel_id, panel_id)

    def test_child_target_keeps_scene_for_h_panel(self) -> None:
        """验证交互对象带幼年素质 102 时，经菜单执行 UNDRESS 保持 IN_SCENE，执行 SEE_ATTR 切换至 SEE_ATTR。"""
        aim(0, 1)
        ca.talent(1)[CHILD] = 1
        open_from_menu(constant.Instruct.UNDRESS)
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
        open_from_menu(constant.Instruct.SEE_ATTR)
        self.assertEqual(view.now_panel_id, constant.Panel.SEE_ATTR)

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


class CurePatientInstructTest(DiagnoseCase):
    """CURE_PATIENT 指令经操作菜单执行时打开诊疗面板或提示无病人的测试。"""

    def setUp(self) -> None:
        """调用父类准备，并将 view.now_panel_id 临时设为 Panel.IN_SCENE。"""
        super().setUp()
        self.enterContext(
            mock.patch.object(view, "now_panel_id", constant.Panel.IN_SCENE)
        )

    def test_waiting_patient_opens_cure_panel(self) -> None:
        """验证当日有待诊病人时，经菜单执行 CURE_PATIENT 切换至 Panel.CURE_PATIENT 且不产生等待提示。"""
        sick = patient([], state=mc.MedicalPatientState.REFRESHED)
        medical.state().today = {sick.patient_id: sick}
        open_from_menu(constant.Instruct.CURE_PATIENT)
        self.assertEqual(view.now_panel_id, constant.Panel.CURE_PATIENT)
        self.assertEqual(self.world.wait_texts, [])

    def test_no_patient_notices_and_stays(self) -> None:
        """验证当日无病人时，经菜单执行 CURE_PATIENT 保持 Panel.IN_SCENE 并发出 NO_PATIENT 等待提示。"""
        medical.state().today = {}
        open_from_menu(constant.Instruct.CURE_PATIENT)
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
        self.assertEqual(self.world.wait_texts, [NO_PATIENT])
