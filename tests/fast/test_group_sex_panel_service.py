"""
群交模板编辑服务测试
====================
验证群交信息栏文本、编辑页部位行与控件文案的生成结果。
验证模板写入、penis 与侍奉互斥清空、重置、切换及未完成槽位清理规则。
验证交互对象筛选、课堂模式体力不足仅旁观标记与行为筛选时的玩家目标恢复。
"""

import json
from typing import Any
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import constant
from Script.Kernel import core
from Script.Modules.domains import activity, chara_life, flags, h_state
from Script.Modules.domains import modes
from Script.Modules.gameplay_resolution import group_sex_editor_service as svc
from Script.Modules.gameplay_resolution import working
from Script.System.Education_System import education_constant
from tests import kernel_data
from tests.fast.base import FastTestCase

NO_SERVE = [[-1], -1]
""" 侍奉槽位处于未选状态时的模板结构常量。 """
EMPTY = [-1, -1]
""" 对单部位槽位处于未选状态时的模板结构常量。 """


class PanelCase(FastTestCase):
    """初始化含主角与五名干员工作缓冲的群交服务测试基类。"""

    def setUp(self) -> None:
        """创建测试角色、开启工作写入缓冲并启用群交模式。"""
        super().setUp()
        self.world.chara(0, "博士")
        for cid in (1, 2, 3, 4, 5):
            self.world.chara(cid, f"干员{cid}", adv=cid * 11)
        self.enterContext(working.based_on(core.state()))
        modes.set_group_sex(True)

    def tpl(self, name: str = "A") -> list[Any]:
        """返回指定模板当前状态的深拷贝，便于断言比对。"""
        return json.loads(
            json.dumps(h_state.view(0).group_sex_body_template_dict[name])
        )

    def fill(self, name: str = "A", /, serve: Any = None, **parts: Any) -> None:
        """按给定部位与侍奉数据写入指定群交模板。"""
        with h_state.editing(0) as hs:
            tpl = hs.group_sex_body_template_dict[name]
            tpl[0].update(parts)
            if serve is not None:
                tpl[1] = serve

    def behavior(self, behavior_id: str) -> str:
        """按行为编号查询配置中的行为显示名称。"""
        return game_config.config_behavior[behavior_id].name


class TextTest(PanelCase):
    """群交信息栏文本、编辑页部位行与控件文案测试。"""

    def test_info_text_lists_filled_parts_and_servers(self) -> None:
        """验证信息文本列出已填部位与多人侍奉格式，无已选行为时返回空串。"""
        self.assertEqual(svc.info_text(0), "")
        self.fill(mouth=[1, "kiss_h"], L_hand=[2, -1])
        self.assertEqual(
            svc.info_text(3),
            f"干员3 嘴-{self.behavior('kiss_h')}-干员1 \n",
        )
        self.fill(serve=[[2, 4], "handjob"])
        self.assertEqual(
            svc.info_text(0),
            f"博士 嘴-{self.behavior('kiss_h')}-干员1 "
            f"阴茎正在被干员2、干员4一起{self.behavior('handjob')} \n",
        )
        self.fill(mouth=EMPTY, serve=[[4], "handjob"])
        self.assertEqual(
            svc.info_text(0),
            f"博士 阴茎正在被干员4{self.behavior('handjob')} \n",
        )

    def test_part_rows_follow_template_with_serve_after_penis(self) -> None:
        """验证编辑页部位行按模板顺序生成，并在 penis 行后插入侍奉行。"""
        self.fill(mouth=[1, "kiss_h"], anal=[2, -1], serve=[[3, 4], -1])
        rows = [
            (row.key, row.label, row.target_text, row.state_text)
            for row in svc.part_rows()
        ]
        self.assertEqual(
            rows,
            [
                (
                    "mouth",
                    "  嘴　　　　　　　",
                    "干员1",
                    self.behavior("kiss_h"),
                ),
                ("L_hand", "  左手　　　　　　", "未选择角色", "未选择指令"),
                ("R_hand", "  右手　　　　　　", "未选择角色", "未选择指令"),
                ("penis", "  阴茎（插入）　　", "未选择角色", "未选择指令"),
                ("侍奉", "  阴茎（侍奉）　　", "干员3 干员4 ", "未选择指令"),
                ("anal", "  肛门　　　　　　", "干员2", "未选择指令"),
            ],
        )
        self.fill(serve=[[-1], "handjob"])
        self.assertEqual(svc.part_rows()[4].target_text, "未选择角色")

    def test_controls_follow_settings(self) -> None:
        """验证副模板开关、锁定标志与干员行动循环切换后的控件文案。"""
        seen = []
        for _round in range(5):
            state = svc.controls()
            seen.append(
                (state.b_on, state.b_text, state.lock_text, state.npc_ai_text)
            )
            svc.change_npc_ai()
            svc.change_lock_flag()
            svc.change_b_temple_flag()
        self.assertEqual(
            seen,
            [
                (False, "未启用", "未锁定", "无行动"),
                (True, "已启用", "已锁定", "自慰"),
                (False, "未启用", "未锁定", "优先补空位，无空位则自慰"),
                (True, "已启用", "已锁定", "随机抢占替换当前位置，无位则自慰"),
                (False, "未启用", "未锁定", "无行动"),
            ],
        )


class TemplateWriteTest(PanelCase):
    """群交模板写入、重置、切换与半成品清理测试。"""

    def test_serve_toggles_and_keeps_last_four(self) -> None:
        """验证侍奉对象可切换选入与取消，且最多保留最近选入的四人。"""
        self.fill(penis=[1, "normal_sex"])
        svc.set_target_chara("A", "侍奉", 2)
        self.assertEqual(self.tpl()[0]["penis"], EMPTY)
        self.assertEqual(self.tpl()[1], [[2], -1])
        svc.set_target_chara("A", "侍奉", 2)
        self.assertEqual(self.tpl()[1], NO_SERVE)
        for cid in (1, 2, 3, 4, 5):
            svc.set_target_chara("A", "侍奉", cid)
        self.assertEqual(self.tpl()[1], [[2, 3, 4, 5], -1])
        svc.set_target_chara("A", "侍奉", 3)
        self.assertEqual(self.tpl()[1], [[2, 4, 5], -1])

    def test_penis_and_serve_exclude_each_other(self) -> None:
        """验证写入 penis 与侍奉的对象或状态时会互相清空另一项。"""
        self.fill(serve=[[2, 3], "handjob"])
        svc.set_status("A", "penis", "normal_sex")
        self.assertEqual(self.tpl()[1], NO_SERVE)
        self.fill(serve=[[2, 3], "handjob"])
        svc.set_target_chara("A", "penis", 1)
        self.assertEqual(self.tpl()[1], NO_SERVE)
        self.assertEqual(self.tpl()[0]["penis"], [1, "normal_sex"])
        svc.set_status("A", "侍奉", "handjob")
        self.assertEqual(self.tpl()[0]["penis"], EMPTY)
        self.assertEqual(self.tpl()[1], [[-1], "handjob"])
        svc.set_status("A", "mouth", "kiss_h")
        svc.set_target_chara("A", "mouth", 4)
        self.assertEqual(self.tpl()[0]["mouth"], [4, "kiss_h"])
        self.assertEqual(self.tpl()[1], [[-1], "handjob"])

    def test_reset_template_clears_only_a(self) -> None:
        """验证重置模板只清空模板 A，不改动模板 B。"""
        self.fill(mouth=[1, "kiss_h"], serve=[[2], "handjob"])
        self.fill("B", anal=[3, "make_lick_anal"])
        svc.reset_template()
        self.assertEqual(
            self.tpl(), [dict.fromkeys(self.tpl()[0], EMPTY), NO_SERVE]
        )
        self.assertEqual(self.tpl("B")[0]["anal"], [3, "make_lick_anal"])

    def test_change_temple_swaps_a_and_b(self) -> None:
        """验证切换模板会互换模板 A 与模板 B 的内容。"""
        self.fill(mouth=[1, "kiss_h"])
        self.fill("B", anal=[3, "make_lick_anal"])
        a, b = self.tpl(), self.tpl("B")
        svc.change_temple()
        self.assertEqual((self.tpl(), self.tpl("B")), (b, a))

    def test_reset_unfinish_select_clears_half_filled_slots(self) -> None:
        """验证未完成槽位清理始终作用于模板 A，并随副模板开关决定是否清理模板 B。"""
        for b_on in (False, True):
            with self.subTest(b_on=b_on), working.based_on(core.state()):
                h_state.set(0, all_group_sex_temple_run=b_on)
                self.fill(mouth=[1, -1], L_hand=[-1, "making_out"])
                self.fill(R_hand=[2, "making_out"], serve=[[3], -1])
                self.fill("B", anal=[4, -1], serve=[[-1], "handjob"])
                svc.reset_unfinish_select()
                parts = self.tpl()[0]
                self.assertEqual(
                    [parts["mouth"], parts["L_hand"], parts["R_hand"]],
                    [EMPTY, EMPTY, [2, "making_out"]],
                )
                self.assertEqual(self.tpl()[1], NO_SERVE)
                b = self.tpl("B")
                cleaned = (b[0]["anal"], b[1]) == (EMPTY, NO_SERVE)
                self.assertEqual(cleaned, b_on)


class ChoiceTest(PanelCase):
    """群交交互对象候选与部位行为候选筛选测试。"""

    def setUp(self) -> None:
        """继承基类初始化并确认六名测试角色均在当前场景内。"""
        super().setUp()
        here = svc.scene_occupants()
        self.assertEqual(sorted(here), [0, 1, 2, 3, 4, 5])

    def test_target_choices_skip_player_and_other_parts(self) -> None:
        """验证对象候选排除玩家与其他槽位已占角色，并正确标记当前已选者。"""
        self.fill(mouth=[1, "kiss_h"], anal=[2, "make_lick_anal"])
        kernel_data.set_needs(5, hit=1)
        choices = svc.target_choices("A", "mouth")
        self.assertEqual(
            [
                (c.cid, c.text, c.name, c.watch_only, c.selected)
                for c in choices
            ],
            [
                (1, "[0011]干员1", "干员1", False, True),
                (3, "[0033]干员3", "干员3", False, False),
                (4, "[0044]干员4", "干员4", False, False),
                (5, "[0055]干员5", "干员5", False, False),
            ],
        )
        self.fill(serve=[[3, 4], "handjob"])
        serve = svc.target_choices("A", "侍奉")
        self.assertEqual(
            [(c.cid, c.selected) for c in serve],
            [(3, True), (4, True), (5, False)],
        )

    def test_target_choices_in_sex_class(self) -> None:
        """验证课堂模式下仅列出在课学生，并将体力不足者标记为仅旁观。"""
        for cid in (2, 3):
            chara_life.work_type.set(cid, education_constant.STUDENT_WORK_TYPE)
            flags.set(cid, is_h=True)
        modes.set_sex_class(True)
        kernel_data.set_needs(3, hit=1)
        choices = svc.target_choices("A", "mouth")
        self.assertEqual(
            [(c.cid, c.watch_only) for c in choices], [(2, False), (3, True)]
        )

    def test_status_choices_use_slot_target_and_restore_it(self) -> None:
        """验证行为筛选临时切换玩家目标为槽位对象，调用结束后恢复原目标。"""
        lists = game_config.config_behavior_id_list_of_group_sex_body_part
        ids = {b: f"I_{b}" for part in lists.values() for b in part}
        self.enterContext(
            mock.patch.dict(constant.behavior_id_to_instruct_id, ids)
        )
        self.enterContext(
            mock.patch.dict(constant.instruct_premise_data, clear=True)
        )
        self.enterContext(
            mock.patch.dict(
                normal_config.system_setting.instruct_index_filter, clear=True
            )
        )
        activity.set_target(0, 5)
        self.fill(mouth=[1, -1], serve=[[2, 3], -1])
        seen = []
        real = svc.group_sex_service.get_status_id_list_from_group_sex_body_part

        def spy(body_part: str) -> list[str]:
            """记录筛选时玩家当前交互目标并转发至真实行为筛选函数。"""
            seen.append(activity.target(0))
            return real(body_part)

        with mock.patch.object(
            svc.group_sex_service,
            "get_status_id_list_from_group_sex_body_part",
            spy,
        ):
            mouth = svc.status_choices("A", "mouth")
            svc.status_choices("A", "侍奉")
            svc.status_choices("A", "anal")
        self.assertEqual(seen, [1, 3, 5])
        self.assertEqual(activity.target(0), 5)
        self.assertEqual(
            [status_id for status_id, _text, _name in mouth], lists["口"]
        )
        self.assertEqual(
            mouth[0],
            (
                "kiss_h",
                f"[kiss_h]{self.behavior('kiss_h')}",
                self.behavior("kiss_h"),
            ),
        )
