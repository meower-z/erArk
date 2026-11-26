"""
日程模板文本与套用服务测试
==========================
验证模板表对齐、时段按钮、活动标签、各类选择页分行与批量套用结果。
验证独立子进程拦截 Script.UI 与 Script.Settle 时服务全部公开入口正常运行。
"""

import re
import unicodedata
from typing import cast
from unittest import mock

from Script.Config import game_config
from Script.Core import game_type
from Script.Kernel import core
from Script.Modules.domains import growth
from Script.Modules.gameplay_resolution import schedule_template_service as svc
from Script.Modules.gameplay_resolution import working
from Script.System.Education_System import education_constant as E
from Script.System.Education_System import schedule_template_handle as handle
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ChildRun, run_ui_free

FREE = E.SCHEDULE_FREE_CHOICE_NAME
""" 自由选择娱乐活动的显示名称常量。 """
AGE_NEED = "T103|1"
""" 测试年龄限制标注时注入的成长阶段需求字符串。 """
UI_FREE_RUN = """
from unittest import mock
from Script.Kernel import core
from Script.Modules.domains import identity
from Script.Modules.gameplay_resolution import schedule_template_service as svc
from Script.Modules.gameplay_resolution import working
from Script.System.Education_System import schedule_template_handle as handle
from Script.Modules.save_load import kernel_state
from Script.Config import game_config
core.reset_state(core.GameState(kernel_state.first_clock(), {}, {}))
with working.based_on(core.state()):
    for cid, name in ((0, "p"), (1, "a"), (2, "b")):
        identity.put(identity.Identity(cid, name=name))
    texts = [svc.head_text(), svc.batch_apply(1, {2, 1, 9}), svc.batch_apply(2, set())]
    texts += [text for _, text in svc.template_rows()]
    texts += [text for _, text in svc.slot_buttons(1)]
    texts += [svc.template_name(1), str(svc.template_name(99)), str(svc.slot_buttons(99))]
    texts += [text for row in svc.template_choice_rows() for _, text in row]
    texts += [text for row in svc.child_rows([1, 2], {2}) for _, text in row]
    texts += [text for row in svc.activity_rows() for _, text in row]
    limited, plain = handle.get_schedule_activity_rows()[2][:2]
    with mock.patch.object(game_config.config_entertainment[limited], "need", "T103|1"):
        texts += [text for row in svc.activity_rows() for _, text in row]
        with mock.patch.object(handle, "judge_activity_place_open", return_value=True):
            texts += [svc.activity_label(limited), svc.activity_label(plain)]
        with mock.patch.object(handle, "judge_activity_place_open", return_value=False):
            texts += [svc.activity_label(limited), svc.activity_label(plain), svc.activity_label(0)]
    with mock.patch.object(handle, "get_schedule_activity_rows", return_value=([0], [], [plain] * 7)):
        payload["sizes"] = [len(row) for row in svc.activity_rows()]
    with mock.patch.object(handle, "get_template_data", return_value=None):
        payload["missing"] = [svc.template_rows(), svc.template_choice_rows()]
    payload["texts"] = len([t for t in texts if t])
"""
""" 在拦截界面与结算模块的子进程中执行全部服务入口的测试脚本。 """


def width(text: str) -> int:
    """计算字符串按东亚宽字符计两列时的显示列宽。"""
    return sum(
        2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
        for ch in text
    )


class TemplateCase(FastTestCase):
    """初始化含主角与七名孩子角色的工作缓冲测试基类。"""

    def setUp(self) -> None:
        """创建测试角色并打开基于当前状态的工作写入缓冲。"""
        super().setUp()
        self.world.chara(0, "博士")
        for cid in range(1, 8):
            self.world.chara(cid, f"孩子{cid}")
        self.enterContext(working.based_on(core.state()))


class TemplateTableTest(TemplateCase):
    """模板表头、模板行与时段按钮构造测试。"""

    def test_rows_align_with_head(self) -> None:
        """验证表头与各模板行在套用人数前的显示列宽一致。"""
        head = svc.head_text()
        self.assertTrue(head.endswith("套用中\n"))
        column = width(head[: -len("套用中\n")])
        self.assertEqual(column, 2 + 4 + 10 + 20 * 3)
        for _template_id, text in svc.template_rows():
            self.assertEqual(width(re.sub(r"\d+ 人$", "", text)), column)

    def test_rows_list_presets_slots_and_use_count(self) -> None:
        """验证模板行列出预设与新建空模板，并正确统计套用人数。"""
        new_id = handle.create_template("空表")
        handle.set_template_slot(new_id, 1, 0)
        self.assertEqual(
            svc.batch_apply(new_id, {3, 1}), "\n已把[空表]套用到 2 名孩子\n"
        )
        rows = dict(svc.template_rows())
        self.assertEqual(
            sorted(rows), sorted([*E.PRESET_TEMPLATE_NAME, new_id])
        )
        self.assertTrue(rows[new_id].endswith("2 人"))
        self.assertEqual(rows[new_id].count(FREE), 3)
        self.assertTrue(rows[new_id].startswith(f"  {new_id}"))
        for template_id, name in E.PRESET_TEMPLATE_NAME.items():
            self.assertIn(name, rows[template_id])
            self.assertTrue(rows[template_id].endswith("0 人"))

    def test_slot_buttons_and_name(self) -> None:
        """验证模板名称与时段按钮标签构造，以及缺失模板编号的空返回。"""
        new_id = handle.create_template("周末")
        entertainment_id = handle.get_schedule_activity_rows()[2][0]
        handle.set_template_slot(new_id, 2, entertainment_id)
        name = handle.get_activity_name(entertainment_id)
        self.assertEqual(
            svc.slot_buttons(new_id),
            [
                (0, f"[上午：{FREE}]"),
                (1, f"[下午：{FREE}]"),
                (2, f"[晚上：{name}]"),
            ],
        )
        self.assertEqual(svc.template_name(new_id), "周末")
        self.assertIsNone(svc.template_name(new_id + 1))
        self.assertEqual(svc.slot_buttons(new_id + 1), [])

    def test_missing_template_data_is_skipped(self) -> None:
        """验证模板数据返回 None 时，表格行与选择行均跳过该项。"""
        with mock.patch.object(handle, "get_template_data", return_value=None):
            self.assertEqual(svc.template_rows(), [])
            self.assertEqual(svc.template_choice_rows(), [])


class PickerRowsTest(TemplateCase):
    """活动标签、活动分行、模板选择与孩子多选分行测试。"""

    def age_limit(self, *entertainment_ids: int) -> None:
        """为指定娱乐项临时注入年龄阶段需求条件。"""
        for entertainment_id in entertainment_ids:
            self.enterContext(
                mock.patch.object(
                    game_config.config_entertainment[entertainment_id],
                    "need",
                    AGE_NEED,
                )
            )

    def test_activity_label_marks_age_limit_and_closed_place(self) -> None:
        """验证活动标签在年龄限制、未开放与编号 0 组合下的四种格式。"""
        limited, plain = handle.get_schedule_activity_rows()[2][:2]
        self.age_limit(limited)
        limit = handle.get_activity_age_limit_text(limited)
        self.assertEqual(limit, f"限{E.STAGE_TALENT_NAME[103]}")
        name = handle.get_activity_name
        with mock.patch.object(
            handle, "judge_activity_place_open", return_value=True
        ):
            self.assertEqual(
                svc.activity_label(limited), f"[{name(limited)}（{limit}）]"
            )
            self.assertEqual(svc.activity_label(plain), f"[{name(plain)}]")
        with mock.patch.object(
            handle, "judge_activity_place_open", return_value=False
        ):
            self.assertEqual(
                svc.activity_label(limited),
                f"[{name(limited)}（{limit}，未开放）]",
            )
            self.assertEqual(
                svc.activity_label(plain), f"[{name(plain)}（未开放）]"
            )
            self.assertEqual(svc.activity_label(0), f"[{FREE}]")

    def test_activity_rows_group_and_wrap_at_six(self) -> None:
        """验证活动行按首行、年龄行与每行六个分组，并略过空行。"""
        first, age, other = handle.get_schedule_activity_rows()
        self.assertEqual(age, [])
        self.age_limit(other[3], other[1])
        rows = svc.activity_rows()
        ids = [[cid for cid, _text in row] for row in rows]
        self.assertEqual(ids[0], first)
        self.assertEqual(ids[1], [other[1], other[3]])
        rest = [cid for cid in other if cid not in (other[1], other[3])]
        self.assertEqual(sum(ids[2:], []), rest)
        self.assertTrue(all(len(row) == 6 for row in ids[2:-1]))
        self.assertTrue(0 < len(ids[-1]) <= 6)
        with mock.patch.object(
            handle,
            "get_schedule_activity_rows",
            return_value=([0], [], [other[0]] * 7),
        ):
            self.assertEqual(
                [len(row) for row in svc.activity_rows()], [1, 6, 1]
            )

    def test_template_choices_wrap_at_six(self) -> None:
        """验证模板选择按钮包含全部模板并按每行六个分行。"""
        new_ids = [handle.create_template(f"自建{n}") for n in range(3)]
        rows = svc.template_choice_rows()
        self.assertEqual([len(row) for row in rows], [6, 1])
        flat = dict(button for row in rows for button in row)
        self.assertEqual(flat[new_ids[2]], "[自建2]")
        self.assertEqual(
            sorted(flat), sorted([*E.PRESET_TEMPLATE_NAME, *new_ids])
        )

    def test_child_rows_mark_selected(self) -> None:
        """验证孩子多选行保持输入顺序、标记已选项并按每行六个分行。"""
        rows = svc.child_rows([7, 1, 2, 3, 4, 5, 6], {1, 6})
        self.assertEqual([len(row) for row in rows], [6, 1])
        self.assertEqual(rows[0][:2], [(7, "[  孩子7]"), (1, "[√孩子1]")])
        self.assertEqual(rows[1], [(6, "[√孩子6]")])


class BatchApplyTest(TemplateCase):
    """批量套用模板服务测试。"""

    def test_applies_to_existing_children_only(self) -> None:
        """验证批量套用仅写入存在角色、统计实际人数并更新套用计数。"""
        name = E.PRESET_TEMPLATE_NAME[2]
        text = svc.batch_apply(2, {5, 99, 4})
        self.assertEqual(text, f"\n已把[{name}]套用到 2 名孩子\n")
        applied = {
            cid: cast(
                game_type.CHILD_GROWTH, growth.of(cid)
            ).schedule_template_id
            for cid in (4, 5)
        }
        self.assertEqual(applied, {4: 2, 5: 2})
        self.assertIsNone(growth.of(99))
        self.assertTrue(dict(svc.template_rows())[2].endswith("2 人"))


class UiFreeRunTest(FastTestCase):
    """验证服务在无界面与无结算模块环境下的独立子进程测试。"""

    child: ChildRun
    """ 子进程隔离运行的返回结果对象。 """
    error: str = ""
    """ 子进程启动或执行失败时记录的错误信息。 """

    @classmethod
    def setUpClass(cls) -> None:
        """启动隔离子进程执行全部公开服务入口并缓存结果。"""
        super().setUpClass()
        try:
            cls.child = run_ui_free(UI_FREE_RUN, boot=True)
        except RuntimeError as error:
            cls.error = str(error)
            cls.child = ChildRun({}, [], [])

    def test_no_ui_or_settle_loaded(self) -> None:
        """验证子进程运行无报错且未加载或尝试导入界面与结算模块。"""
        self.assertEqual(self.error, "")
        self.assertEqual((self.child.loaded, self.child.attempted), ([], []))

    def test_child_results(self) -> None:
        """验证隔离子进程返回的活动分行、空数据跳过与文本计数结果。"""
        out = self.child.payload
        self.assertEqual(out["sizes"], [1, 6, 1])
        self.assertEqual(out["missing"], [[], []])
        self.assertGreater(cast(int, out["texts"]), 20)
