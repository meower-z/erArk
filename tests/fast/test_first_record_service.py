"""
性行为履历后端服务测试（test_first_record_service）
===================================================
验证六个履历分组文本、体液数据文本、周目切换与分组折叠逻辑。
同时检查履历面板按钮渲染及多编码无界面子进程运行隔离。
"""

import datetime
import os
from unittest import mock

from Script.Config import game_config
from Script.Core import game_type
from Script.Design import attr_text, game_time
from Script.Modules.domains import dirty, player_collection
from Script.Modules.gameplay_resolution import first_record_service as service
from Script.Modules.gameplay_resolution import first_record_text as text
from Script.Modules.gameplay_resolution import hypnosis_service
from Script.UI.Panel import first_record_panel
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import run_ui_free

ENCODINGS = ("cp1252", "gbk", "utf-16")
""" 无界面子进程测试使用的编码元组。 """
WHEN = datetime.datetime(1, 3, 5, 10, 30)
""" 测试用例复用的记录时间。 """
WHERE = ["宿舍", "1区", "101"]
""" 测试用例复用的宿舍场景路径。 """
SCENARIO = """
import datetime
from fractions import Fraction
from Script.Kernel import core
from Script.Modules.domains import dirty, first_record, player_collection
from Script.Modules.domains import playthrough
from Script.Modules.gameplay_resolution import first_record_service as service
from Script.Modules.gameplay_resolution import first_record_text as text
from tests import kernel_data
when = datetime.datetime(1, 3, 5, 10, 30)
where = ["宿舍", "1区", "101"]
rows = []
with kernel_data.writing():
    with first_record.editing(1) as fr:
        fr.first_kiss_id = 0
        fr.first_kiss_time = when
        fr.first_kiss_place = where
        fr.first_part_sex_dict[2] = {"id": -1, "time": when, "place": where,
                                     "posture": "p", "item": 1}
    playthrough.set_game_round(1)
carried = first_record.carry_for_new_round({1: None}, core.state())
with kernel_data.writing():
    first_record.clear(1)
    first_record.restore_for_new_round(1, 1, carried)
    playthrough.set_game_round(2)
    with first_record.editing(1) as fr:
        fr.first_kiss_id = 0
        fr.first_kiss_body_part = 1
        fr.first_kiss_time = when
        fr.first_kiss_place = where
        fr.first_part_sex_dict[6] = {"id": 0, "time": when, "place": where,
                                     "posture": "q", "item": 0}
        fr.first_part_sex_dict[8] = {"id": 0, "time": when, "place": where,
                                     "posture": "", "item": 7}
        fr.first_shoot_body_dict[3] = [when, where]
        fr.first_shoot_body_dict[0] = [when, where]
        fr.first_strong_orgasm_dict[23] = [when, where]
        fr.first_strong_orgasm_dict[3] = [when, where]
        fr.first_strong_orgasm_dict[0] = [when, where]
        fr.first_plural_orgasm_dict[3] = [when, where, [0, 1, 999]]
        fr.first_plural_orgasm_dict[2] = [when, where, [2, 4]]
        fr.fall_talent_time_dict[211] = [when, where]
        fr.fall_talent_time_dict[201] = [when, where]
        fr.first_mark_dict["unconscious_mark_6"] = [when, where]
        fr.first_mark_dict["happy_mark_2"] = [when, where]
        fr.first_h_mode_dict["hidden_sex"] = [when, where, "x"]
        fr.first_h_mode_dict["group_sex"] = [when, where, "5"]
        fr.first_h_mode_dict["unconscious_3"] = [when, where]
        special = sorted(text.game_config.config_first_record_special)
        fr.first_special_record_dict[special[1]] = [when, where, "y"]
        fr.first_special_record_dict[special[0]] = [when, where, ""]
    with dirty.editing(1) as d:
        d.body_semen[0][3] = 4
        d.body_semen[2][3] = 3
        d.body_semen[6][3] = 5
        d.body_semen[15][3] = 2
        d.absorbed_total_semen = Fraction(117, 5)
    with dirty.editing(2) as d:
        d.absorbed_total_semen = 8
    player_collection.add_total("milk_total", 1, 30)
    player_collection.add_total("urine_total", 1, 20)
    player_collection.add_total("urine_total", 2, 9)
state = service.PanelState()
for selected in (-1, 1, 7):
    state.select_round(selected)
    view = service.round_view(1, state.selected_round)
    entries = service.group_entries(view)
    rows.append([list(view.rounds), view.current, view.shown, view.is_current,
                 [list(entry) for entry in entries],
                 [service.group_text(1, view, entry.group) for entry in entries]])
state.toggle_fold("2_0", True)
state.toggle_fold("2_1", False)
state.toggle_fold("2_1", False)
rows.append([sorted(state.folds.items()),
             [state.expanded(entry) for entry in entries]])
rows.append([service.fluid_text(2), service.fluid_text(3),
             service.group_text(3, service.round_view(3, -1), 0)])
odd = text.game_type.FIRST_RECORD()
odd.first_kiss_id = 9
odd.first_kiss_time = "bad"
odd.first_kiss_place = ["no", "such"]
rows.append(text.build_group_text(odd, 0))
payload["rows"] = rows
"""
""" 进程内与无界面子进程共用的多周目履历测试脚本。 """
CHILD_SETUP = """
from Script.Config import map_config
from Script.Modules.domains import identity
from tests import kernel_data
from tests.world import start_time
map_config.init_map_data()
kernel_data.reset_clock(start_time(), {})
for cid in (0, 1, 2, 3):
    kernel_data.put(identity.put, identity.Identity(cid, name=f"c{cid}"))
"""
""" 无界面子进程启动前初始化地图、时钟与测试角色的脚本。 """


def _at() -> str:
    """返回复用时间与地点拼接后的预期前缀文本。"""
    when = game_time.get_date_until_day(WHEN)[3:]
    return f"于{when}在{attr_text.get_scene_path_text(WHERE)}"


class FirstRecordTextTest(FastTestCase):
    """覆盖六个履历分组文本构建规则的单元测试。"""

    def setUp(self) -> None:
        """准备测试角色与空白履历记录对象。"""
        super().setUp()
        self.world.chara(0, "c0")
        self.world.chara(1, "c1")
        self.record = game_type.FIRST_RECORD()

    def test_empty_record_lists_nothing(self) -> None:
        """验证空白履历记录在六个分组下均返回空串。"""
        texts = [
            text.build_group_text(self.record, index)
            for index in range(len(text.GROUP_NAMES))
        ]
        self.assertEqual(texts, [""] * 6)

    def test_part_sex_lines(self) -> None:
        """验证初吻与部位初体验的文案、回退、顺序与道具标注。"""
        record = self.record
        record.first_kiss_id = 0
        vars(record).update(first_kiss_time="bad")
        record.first_kiss_place = ["no", "such"]
        record.first_kiss_body_part = 1
        base = {"time": WHEN, "place": WHERE}
        record.first_part_sex_dict = {
            9: dict(base, id=0, posture=""),
            6: dict(base, id=0, posture="正常位", item=1),
            2: dict(base, id=-1, posture="跪姿", item=2),
            3: dict(base, id=5, item=9),
            7: dict(base, id=-1, posture="侧位"),
        }
        self.assertEqual(
            text.build_group_text(record, 0),
            "  初吻：于未知时间在未知地点，向c0博士的阴茎献上了初吻\n"
            f"  口交：{_at()}初次体验（姿势：跪姿）（使用道具：采尿器）\n"
            f"  乳交：{_at()}初次体验\n"
            f"  V性交：{_at()}，被c0博士以正常位夺走了处女（使用道具：振动棒）\n"
            f"  子宫性交：{_at()}初次体验（姿势：侧位）\n"
            f"  U性交：{_at()}，与c0博士初次体验\n",
        )

    def test_shoot_body_follows_body_part_table(self) -> None:
        """验证初次被射精分组按身体部位配表顺序输出并跳过空项。"""
        parts = list(game_config.config_body_part)
        self.record.first_shoot_body_dict = {
            parts[3]: [WHEN, WHERE],
            parts[0]: [WHEN, WHERE],
        }
        names = [game_config.config_body_part[parts[i]].name for i in (0, 3)]
        self.assertEqual(
            text.build_group_text(self.record, 1),
            "".join(f"  {name}：{_at()}\n" for name in names),
        )

    def test_orgasm_sections(self) -> None:
        """验证强绝顶与多重绝顶分节顺序、部位排除与未知编号跳过。"""
        states = game_config.config_character_state
        self.record.first_strong_orgasm_dict = {
            23: [WHEN, WHERE],
            3: [WHEN, WHERE],
            0: [WHEN, WHERE],
        }
        self.record.first_plural_orgasm_dict = {
            3: [WHEN, WHERE, [0, 999, 1]],
            2: [WHEN, WHERE, [2]],
        }
        self.assertEqual(
            text.build_group_text(self.record, 2),
            " 【强绝顶】\n"
            f"  {states[0].name}：{_at()}\n"
            f"  {states[23].name}：{_at()}\n"
            " 【多重绝顶】\n"
            f"  2重绝顶：{_at()}，参与部位：{states[2].name}\n"
            f"  3重绝顶：{_at()}，参与部位：{states[0].name}、{states[1].name}\n",
        )

    def test_fall_and_mark_sections(self) -> None:
        """验证陷落素质与刻印的固定顺序及未知或越界项过滤。"""
        talents = game_config.config_talent
        ability = game_config.config_ability
        self.record.fall_talent_time_dict = {
            214: [WHEN, WHERE],
            201: [WHEN, WHERE],
            999: [WHEN, WHERE],
        }
        self.record.first_mark_dict = {
            "unconscious_mark_6": [WHEN, WHERE],
            "happy_mark_3": [WHEN, WHERE],
            "happy_mark_4": [WHEN, WHERE],
            "hate_mark_1": [WHEN, WHERE],
        }
        self.assertEqual(
            text.build_group_text(self.record, 3),
            " 【陷落素质】\n"
            f"  {talents[201].name}：{_at()}获得\n"
            f"  {talents[214].name}：{_at()}获得\n"
            " 【刻印】\n"
            f"  {ability[13].name}3级：{_at()}\n"
            f"  {ability[18].name}1级：{_at()}\n"
            f"  {ability[19].name}6级：{_at()}\n",
        )

    def test_h_mode_lines(self) -> None:
        """验证H模式初体验固定顺序、人数备注、括号备注与未知键过滤。"""
        self.record.first_h_mode_dict = {
            "pretend_sleep": [WHEN, WHERE, ""],
            "group_sex": [WHEN, WHERE, "5"],
            "exhibitionism": [WHEN, WHERE, "x"],
            "unconscious_7": [WHEN, WHERE],
            "unknown": [WHEN, WHERE],
        }
        name = hypnosis_service.unconscious_list[7]
        self.assertEqual(
            text.build_group_text(self.record, 4),
            f"  第一次{name}H：{_at()}\n"
            f"  第一次群交：{_at()}（当时场景内共5人）\n"
            f"  第一次露出H：{_at()}（x）\n"
            f"  第一次装睡H：{_at()}\n",
        )

    def test_special_lines_follow_config(self) -> None:
        """验证特殊履历按配置表编号升序输出并附带备注。"""
        table = game_config.config_first_record_special
        first, second = sorted(table)[:2]
        self.record.first_special_record_dict = {
            second: [WHEN, WHERE, "y"],
            first: [WHEN, WHERE],
        }
        self.assertEqual(
            text.build_group_text(self.record, 5),
            f"  {table[first].name}：{_at()}\n"
            f"  {table[second].name}：{_at()}（y）\n",
        )


class FirstRecordServiceTest(FastTestCase):
    """覆盖体液文本、周目视图、面板按钮与无界面运行的测试。"""

    def setUp(self) -> None:
        """初始化测试角色数据。"""
        super().setUp()
        for cid in (0, 1, 2, 3):
            self.world.chara(cid, f"c{cid}")

    def _scenario(self) -> list:
        """在当前进程中执行共享场景脚本并返回结果行。"""
        payload: dict = {}
        exec(SCENARIO, {"payload": payload})
        return payload["rows"]

    def test_fluid_lines(self) -> None:
        """验证精液总量、各部位差异文案及乳汁与圣水收集文本。"""
        parts = game_config.config_body_part
        with kernel_data.writing(), dirty.editing(1) as d:
            d.body_semen[0][3] = 4
            d.body_semen[2][3] = 3
            d.body_semen[6][3] = 5
            d.body_semen[15][3] = 2
            d.absorbed_total_semen = 7
        kernel_data.put(player_collection.add_total, "milk_total", 1, 30)
        kernel_data.put(player_collection.add_total, "urine_total", 1, 20)
        self.assertEqual(
            service.fluid_text(1),
            "  全身总共被射上过14ml精液\n"
            " 【各部位累计被射精液量】\n"
            f"  {parts[0].name}：总共被淋上过4ml精液\n"
            f"  {parts[2].name}：总共喝过3ml精液\n"
            f"  {parts[6].name}：总共被射入过5ml精液\n"
            f"  {parts[15].name}：有2ml精液在食道直接射进了胃里，"
            "肠胃一共吸收了7ml精液\n"
            "  总共收集了30ml乳汁\n"
            "  总共收集了20ml圣水\n",
        )

    def test_fluid_absorbed_only_shows_with_semen(self) -> None:
        """验证仅有吸收精液量时不展示，有射精记录后才展示吸收行。"""
        parts = game_config.config_body_part
        with kernel_data.writing(), dirty.editing(1) as d:
            d.absorbed_total_semen = 7
        self.assertEqual(service.fluid_text(1), "")
        with kernel_data.writing(), dirty.editing(1) as d:
            d.body_semen[1][3] = 1
        self.assertEqual(
            service.fluid_text(1),
            "  全身总共被射上过1ml精液\n"
            " 【各部位累计被射精液量】\n"
            f"  {parts[1].name}：总共被淋上过1ml精液\n"
            f"  {parts[15].name}：肠胃一共吸收了7ml精液\n",
        )

    def test_rounds_and_groups(self) -> None:
        """验证多周目回退、分组列表、无记录文案与折叠状态切换。"""
        rows = self._scenario()
        current, history, fallback, folds, empty, odd = rows
        self.assertEqual(current[:4], [[1, 2], 2, 2, True])
        self.assertEqual(history[:4], [[1, 2], 2, 1, False])
        self.assertEqual(fallback[:5], current[:5])
        names = [*text.GROUP_NAMES[:2], service.FLUID_GROUP_NAME]
        names += text.GROUP_NAMES[2:]
        self.assertEqual(
            current[4],
            [
                [name, group, f"2_{slot}", group == 0]
                for slot, (name, group) in enumerate(
                    zip(names, [0, 1, -1, 2, 3, 4, 5], strict=True)
                )
            ],
        )
        self.assertEqual(
            history[4],
            [
                [name, slot, f"1_{slot}", slot == 0]
                for slot, name in enumerate(text.GROUP_NAMES)
            ],
        )
        self.assertIn("被c0博士以q夺走了处女（使用道具：手指）", current[5][0])
        self.assertIn("肠胃一共吸收了23ml精液", current[5][2])
        self.assertIn("初次体验（姿势：p）（使用道具：振动棒）", history[5][0])
        self.assertEqual(history[5][1:], ["  无记录\n"] * 5)
        self.assertEqual(folds[0], [("2_0", False), ("2_1", False)])
        self.assertEqual(folds[1], [False] * 7)
        self.assertEqual(empty, ["  总共收集了9ml圣水\n", "", "  无记录\n"])
        self.assertEqual(
            odd, "  初吻：于未知时间在未知地点，向博士献上了初吻\n"
        )

    def test_panel_draws_round_and_fold_buttons(self) -> None:
        """验证履历面板按钮编号、周目标签及点击切换周目的行为。"""
        self._scenario()
        state = first_record_panel._state
        self.addCleanup(vars(state).update, vars(service.PanelState()))
        panel = first_record_panel.FirstRecordText(1, 120)
        self.assertEqual(
            panel.return_list,
            ["first_record_round_1", "first_record_round_2"]
            + [f"first_record_fold_2_{slot}" for slot in range(7)],
        )
        record = service.round_view(1, -1).record
        part_sex, shoot = (text.build_group_text(record, i) for i in (0, 1))
        labels = [getattr(item, "text", "") for item in panel.draw_list]
        self.assertIn("[第1周目]", labels)
        self.assertIn("▶第2周目(当前)", labels)
        self.assertIn("\n◆ 第2周目（当前）\n", labels)
        self.assertEqual((part_sex in labels, shoot in labels), (True, False))
        fold = next(
            item
            for item in panel.draw_list
            if getattr(item, "return_text", "") == "first_record_fold_2_1"
        )
        fold.cmd_func(*fold.args)
        panel = first_record_panel.FirstRecordText(1, 120)
        self.assertIn(shoot, [getattr(i, "text", "") for i in panel.draw_list])
        self.assertEqual(
            first_record_panel.FirstRecordText(3, 120).return_list,
            [f"first_record_fold_2_{slot}" for slot in range(7)],
        )
        panel.draw_list[2].cmd_func(*panel.draw_list[2].args)
        panel = first_record_panel.FirstRecordText(1, 120)
        self.assertIn(
            "▶第1周目", [getattr(i, "text", "") for i in panel.draw_list]
        )
        self.assertEqual(
            panel.return_list[2:],
            [f"first_record_fold_1_{s}" for s in range(6)],
        )

    def test_backend_runs_without_ui(self) -> None:
        """验证多编码无界面子进程运行不触碰受限模块且结果一致。"""
        expected = self._scenario()
        for encoding in ENCODINGS:
            with self.subTest(encoding=encoding):
                with mock.patch.dict(
                    os.environ, {"PYTHONIOENCODING": encoding}
                ):
                    run = run_ui_free(CHILD_SETUP + SCENARIO, boot=True)
                self.assertEqual((run.loaded, run.attempted), ([], []))
                self.assertEqual(run.payload["rows"], _json(expected))


def _json(value: object) -> object:
    """递归将元组转为列表以便与子进程 JSON 载荷比对。"""
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    return value
