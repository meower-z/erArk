"""
调试面板无界面服务测试
======================
验证口上测试与重建、全局及玩家调试修改与角色状态读写逻辑。
验证四个服务在拦截 Script.UI 与 Script.Settle 的子进程中独立运行。
"""

import json
import os
import tempfile
from types import SimpleNamespace
from unittest import mock

from Script.Config import game_config
from Script.Design import attr_calculation, game_time
from Script.Kernel import core
from Script.Modules.domains import abilities, action_info, chara_life, dirty
from Script.Modules.domains import entertainment, flags, h_meters, h_state
from Script.Modules.domains import hypnosis, needs, pregnancy, recruit
from Script.Modules.domains import relations, roster, status, warehouse
from Script.Modules.gameplay_resolution import debug_chara_edit as edit_svc
from Script.Modules.gameplay_resolution import debug_chara_view as view_svc
from Script.Modules.gameplay_resolution import debug_world_service as world
from Script.Modules.gameplay_resolution import talk_test_service as talk_test
from Script.Modules.gameplay_resolution import working
from tests.chara_activity import aim
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ChildRun, run_ui_free

NPC = 1
""" 测试用目标干员角色编号。 """
TALK_ROWS = [
    "cid,adv_id,context",
    "编号,角色,文本",
    "str,int,str",
    "0,0,1",
    "skip,skip,skip",
    "a,1,说「你好」",
    "b,0,公共",
    "c,2,别人",
]
""" 用于验证口上 CSV 解析与重建的样例行列表。 """
UI_FREE_RUN = """
import contextlib, io, json, os, shutil, tempfile
from types import MappingProxyType, SimpleNamespace
from Script.Config import game_config, map_config
from Script.Design import attr_calculation, game_time
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, identity, needs
from Script.Modules.domains import relations, roster, status, wardrobe
from Script.Modules.domains import warehouse
from Script.Modules.gameplay_resolution import debug_chara_edit as edit_svc
from Script.Modules.gameplay_resolution import debug_chara_view as view_svc
from Script.Modules.gameplay_resolution import debug_world_service as world
from Script.Modules.gameplay_resolution import talk_test_service as talk_test
from Script.Modules.gameplay_resolution import actions, working
from Script.Modules.save_load import kernel_state, settings
with contextlib.redirect_stdout(io.StringIO()):
    map_config.init_map_data()
scratch = tempfile.mkdtemp()
settings.path = os.path.join(scratch, "settings.json")
added = []
first = kernel_state.first_clock()
marks = {actions.TICKED: first, actions.SETTLED_DAY: game_time.day(first)}
state = core.GameState(first, MappingProxyType({}), MappingProxyType(marks))
core.reset_state(state)
world.edit_global(0, [0, 1], 3, added.append)
payload["month"] = game_time.now().month
with working.based_on(core.state()):
    warehouse.start({})
    for cid in (0, 1):
        identity.put(identity.Identity(cid, name=f"c{cid}", adv=cid, sex=cid))
        abilities.talent(cid).replace(attr_calculation.get_talent_zero({}))
        abilities.ability(cid).replace(attr_calculation.get_ability_zero({}))
        abilities.experience(cid).replace(
            attr_calculation.get_experience_zero({})
        )
        abilities.juel(cid).replace(attr_calculation.get_juel_zero({}))
        wardrobe.put(cid, attr_calculation.get_cloth_zero())
        relations.favorability.set(cid, {0: 0})
        status.replace(cid, attr_calculation.get_status_zero({}))
    roster.add(1)
    activity.set_target(0, 1)
    behavior_id = next(
        b
        for b, data in game_config.config_behavior.items()
        if "二段结算" not in data.tag
    )
    for talk_id, premises in (
        (7, {"sys_1", "sys_4", "CVP_A1_F_E_0"}),
        (8, {"sys_1", "sys_3"}),
    ):
        key = f"chara_0001_c1{talk_id}"
        game_config.config_talk[key] = SimpleNamespace(
            behavior_id=behavior_id, context="{Name}对{TargetName}说你好"
        )
        game_config.config_talk_premise_data[key] = premises
    payload["talks"] = [talk_test.test_single_talk(1, t) for t in (7, 8)]
    payload["missing"] = talk_test.test_single_talk(1, 999999)
    text = [world.global_info(k) for k in world.GLOBAL_KINDS]
    text += world.global_lines() + world.player_lines()
    entries = {1: [1, 1], 7: "0,1", 8: "0,2"}
    for key in set(world.GLOBAL_KINDS) - {0}:
        world.edit_global(key, entries.get(key), 3, added.append)
    for key in world.PLAYER_KINDS:
        text.append(world.edit_player(key, 1))
    text.append(view_svc.header(1))
    for key, (kind, lines) in view_svc.SCREENS.items():
        if key != 4:
            text += lines(1)
            continue
        try:
            lines(1)
        except TypeError as error:
            payload["screen4"] = str(error)
    inputs = {12: 3, 13: 1, 17: [2, 3], 18: 5, 19: [0, 2], 20: [2, 1]}
    inputs[21] = [5, 1]
    payload["edits"] = [
        edit_svc.edit(key, 1, inputs.get(key, 0), 2) for key in edit_svc.EDITS
    ]
    payload["stored"] = [needs.of(1)["hit"], abilities.ability(1)[0]]
    payload["ids"] = talk_test.parse_talk_id_list("1,3-2")
    text += talk_test.summary_lines([1], [2], True)
    payload["totals"] = list(talk_test.reload_talk())
    home = os.getcwd()
    os.makedirs(os.path.join(scratch, "data", "talk", "x"))
    rows = ["cid,adv_id,context", "编号,角色,文本", "str,int,str", "0,0,1"]
    rows += ["skip,skip,skip", "b,0,公共", "c,2,别人"]
    csv_path = os.path.join(scratch, "data", "talk", "x", "t_x_3.csv")
    with open(csv_path, "w", encoding="utf-8") as file:
        file.write("\\n".join(rows) + "\\n")
    os.chdir(scratch)
    try:
        talk_test.build_chara_talk(0)
        built_path = os.path.join("data", "Character_Talk.json")
        with open(built_path, encoding="utf-8") as file:
            payload["built"] = json.load(file)
    finally:
        os.chdir(home)
shutil.rmtree(scratch)
payload["added"] = added
payload["text"] = text
"""
""" 在无界面受限子进程中执行四个服务入口的脚本片段。 """


class DebugCase(FastTestCase):
    """调试面板服务测试基类，初始化主角与测试干员的工作态。"""

    def setUp(self) -> None:
        """创建测试主角与干员并开启基于当前状态的工作态上下文。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(NPC, "干员", adv=NPC)
        self.enterContext(working.based_on(core.state()))


class TalkTestServiceTest(DebugCase):
    """验证 talk_test_service 的解析、报告与口上重建行为。"""

    def fake_talk(self, premises: set[str]) -> None:
        """在当前测试中注入一条指定前提集合的样例口上配置。"""
        behavior_id = next(
            b
            for b, data in game_config.config_behavior.items()
            if "二段结算" not in data.tag
        )
        key = "chara_0001_干员7"
        talk = SimpleNamespace(behavior_id=behavior_id, context="{Name}说你好")
        self.enterContext(mock.patch.dict(game_config.config_talk, {key: talk}))
        self.enterContext(
            mock.patch.dict(
                game_config.config_talk_premise_data, {key: premises}
            )
        )

    def test_parse_ids(self) -> None:
        """验证口上编号列表解析支持中英文逗号、区间与去重。"""
        self.assertEqual(
            talk_test.parse_talk_id_list("3，1, 5-3 ,x,7-,1"), [3, 1, 4, 5]
        )
        self.assertEqual(talk_test.parse_talk_id_list(" , "), [])

    def test_summary(self) -> None:
        """验证批量测试汇总行在正常结束与中途停止时的文本格式。"""
        self.assertEqual(
            talk_test.summary_lines([1, 2], [3], True),
            [
                "\n测试已停止，以下是已测试部分的汇总",
                "\n汇总：共测试 3 条，通过 2 条，未通过 1 条",
                "\n通过的口上id：1、2",
                "未通过的口上id：3\n",
            ],
        )
        self.assertEqual(
            talk_test.summary_lines([], []),
            [
                "\n汇总：共测试 0 条，通过 0 条，未通过 0 条",
                "\n通过的口上id：无",
                "未通过的口上id：无\n",
            ],
        )

    def test_missing_character_or_talk(self) -> None:
        """验证缺失角色或口上时的提示文本及按 adv_id 查找回退。"""
        self.assertEqual(
            talk_test.test_single_talk(0, 7),
            ("\n未找到该角色，请确认是否输入正确\n", False),
        )
        text, passed = talk_test.test_single_talk(NPC, 7)
        self.assertFalse(passed)
        self.assertIn("未找到该口上（id=7）", text)
        self.assertEqual(talk_test.chara_by_adv(NPC), NPC)
        self.assertEqual(talk_test.chara_by_adv(4321), 0)

    def test_talk_report(self) -> None:
        """验证通过与失败、名册和交互对象检查及 {Name} 渲染为角色名。"""
        self.fake_talk({"sys_1", "sys_4"})
        aim(0, NPC)
        text, passed = talk_test.test_single_talk(NPC, 7)
        self.assertTrue(passed)
        for line in (
            "  博士已获得该角色(√)\n",
            "  博士当前交互对象是该角色(√)\n",
            "  触发人：NPC\n  交互对象：博士\n",
            "口上输出文本：\n  干员说你好\n",
            "  sys_1：满足(√)\n",
            "  sys_4：满足(√)\n",
            "测试通过，该口上可以触发",
        ):
            self.assertIn(line, text)
        aim(0, 0)
        text, passed = talk_test.test_single_talk(NPC, 7)
        self.assertFalse(passed)
        self.assertIn("  博士当前交互对象不是该角色(X)\n", text)

    def test_default_roles_and_failed_premise(self) -> None:
        """验证批量执行时的默认触发角色推断与未满足前提标记。"""
        self.fake_talk({"sys_3"})
        aim(0, NPC)
        lines, passed, failed = talk_test.run_tests(NPC, [7, 8], 11, 20)
        self.assertEqual((passed, failed), ([], [7, 8]))
        self.assertEqual(
            lines[0], "\n===== 第 11 条 / 共 20 条（口上id：7） ====="
        )
        self.assertIn("  触发人：未填写，本测试中默认选择为", lines[1])
        self.assertIn("  sys_3：不满足(X)\n", lines[1])
        self.assertIn("未找到该口上（id=8）", lines[3])

    def test_build_chara_talk(self) -> None:
        """验证按 adv_id 局部重建口上 JSON 时保留其余角色条目。"""
        scratch = self.enterContext(tempfile.TemporaryDirectory())
        folder = os.path.join(scratch, "data", "talk", "0001")
        os.makedirs(os.path.join(scratch, "data", "talk", "ai"))
        os.makedirs(folder)
        with open(
            os.path.join(folder, "t_x_3.csv"), "w", encoding="utf-8"
        ) as file:
            file.write("\n".join(TALK_ROWS) + "\n")
        old = {"Talk": {"data": [{"adv_id": 1}, {"adv_id": 2}]}}
        with open(
            os.path.join(scratch, "data", "Character_Talk.json"),
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(old, f)
        home = os.getcwd()
        os.chdir(scratch)
        self.addCleanup(os.chdir, home)
        talk_test.build_chara_talk(1)
        with open(
            os.path.join("data", "Character_Talk.json"), encoding="utf-8"
        ) as file:
            built = json.load(file)
        self.assertEqual(
            built["Talk"]["data"],
            [
                {"adv_id": 2},
                {"cid": "0001_t_x_3a", "adv_id": 1, "context": "说「你好」"}
                | {"version": 3},
            ],
        )
        self.assertEqual(
            built["Talk"]["gettext"],
            {"cid": 0, "adv_id": 0, "context": 1, "version": 0},
        )


class WorldEditTest(DebugCase):
    """验证 debug_world_service 的全局与玩家调试修改及索引解析。"""

    def test_global_edits(self) -> None:
        """验证全局变量页资源、待确认招募、派对、进度与名册修改。"""
        added: list[int] = []
        for key, value in ((3, 11), (4, 22), (5, 44), (9, 7)):
            self.assertTrue(world.edit_global(key, None, value, added.append))
        self.assertEqual([warehouse.amount(r) for r in (1, 2, 4)], [11, 22, 44])
        self.assertEqual(world.global_lines()[3], "[003]:龙门币：11")
        self.assertEqual(recruit.pending(), {7})
        world.edit_global(7, "2,5", 0, added.append)
        self.assertEqual(entertainment.party_days()[2], 5)
        world.edit_global(8, "0,6", 0, added.append)
        self.assertEqual(recruit.lines()[0]["progress"], 6)
        world.edit_global(1, [9, 1], 0, added.append)
        world.edit_global(1, [NPC, 0], 0, added.append)
        self.assertEqual(added, [9])
        self.assertFalse(roster.has(NPC))
        self.assertIn(f"{NPC}:干员", world.global_info(1))

    def test_player_edits(self) -> None:
        """验证玩家基础数值、全源石技艺与资源满额快捷修改。"""
        for key, value in ((0, 50), (3, 80), (4, 6), (7, 9)):
            self.assertEqual(world.edit_player(key, value), "")
        self.assertEqual(
            [needs.of(0)[k] for k in ("hit", "mana_max", "hunger")],
            [50, 80, 9],
        )
        self.assertEqual(h_meters.of(0)["eja"], 6)
        self.assertEqual(world.player_info(0), "[000]:当前HP：50")
        world.edit_player(8, 0)
        self.assertEqual(abilities.talent(0)[333], 1)
        self.assertEqual(needs.of(0)["sanity_max"], 9999)
        world.edit_player(9, 0)
        self.assertEqual(set(warehouse.stock().values()), {99999})

    def test_recruit_edits(self) -> None:
        """验证按 adv_id 招募、重置招募数据与交互对象快感增加。"""
        self.assertEqual(world.edit_player(16, NPC), "\n已招募过\n")
        roster.discard(NPC)
        self.assertEqual(world.edit_player(16, NPC), "\n招募成功\n")
        self.assertEqual(recruit.pending(), {NPC})
        world.edit_player(14, 0)
        self.assertEqual(recruit.pending(), set())
        aim(0, NPC)
        world.edit_player(15, 3)
        touch = [
            s
            for s, data in game_config.config_character_state.items()
            if data.type == 0
        ]
        self.assertEqual({status.of(NPC)[s] for s in touch}, {3})

    def test_parse_index(self) -> None:
        """验证索引解析函数区分单整数与逗号分隔整数列表。"""
        self.assertEqual(world.parse_index("1,2"), [1, 2])
        self.assertEqual(world.parse_index("4"), 4)


class CharaEditTest(DebugCase):
    """验证 debug_chara_view 与 debug_chara_edit 的展示与写入。"""

    def test_screens_show_state(self) -> None:
        """验证角色页眉、基础属性与特殊 flag 展示及子页键集合一致。"""
        self.assertEqual(view_svc.header(NPC), "[0001]：干员\n\n")
        edit_svc.edit(0, NPC, 1, 120)
        edit_svc.edit(0, NPC, 17, 33)
        base = view_svc.SCREENS[0][1](NPC)
        self.assertIn("[001]:最大HP：120", base)
        self.assertIn("[017]:对玩家的好感度：33", base)
        edit_svc.edit(20, NPC, [2, 1], 0)
        edit_svc.edit(20, NPC, [29, 2], 0)
        text = view_svc.SCREENS[20][1](NPC)[0]
        self.assertEqual(flags.get(NPC, "is_follow"), 1)
        self.assertEqual(action_info.get(NPC, "health_check_today"), 2)
        self.assertIn("4前往博士当前位置]：1\n", text)
        self.assertIn("3新干员立刻体检]：2\n", text)
        kinds = {key: kind for key, (kind, _) in view_svc.SCREENS.items()}
        self.assertEqual(set(kinds), set(edit_svc.EDITS))
        self.assertEqual(kinds[18], "gap")

    def test_tables_and_stats(self) -> None:
        """验证基础属性、信赖度及能力与素质数值表的写入和读取。"""
        edit_svc.edit(0, NPC, 23, 70)
        edit_svc.edit(0, NPC, 18, 4)
        edit_svc.edit(7, NPC, 3, 2)
        edit_svc.edit(10, NPC, 21, 1)
        self.assertEqual(h_meters.of(NPC)["semen_max"], 70)
        self.assertEqual(relations.trust(NPC), 4)
        self.assertEqual(abilities.ability(NPC)[3], 2)
        self.assertEqual(abilities.talent(NPC)[21], 1)
        self.assertIn("3:", view_svc.SCREENS[7][1](NPC)[0])

    def test_dirty_and_h_state(self) -> None:
        """验证污浊精液量重算等级、本次 H 修改。"""
        before = dirty.view(NPC).body_semen[0][1]
        edit_svc.edit(12, NPC, 8, 40)
        slot = dirty.view(NPC).body_semen[0]
        self.assertEqual(slot[1], before + 40)
        self.assertEqual(
            slot[2], attr_calculation.get_semen_now_level(slot[1], 0, 0)
        )
        edit_svc.edit(12, NPC, [5, 0], 3)
        self.assertEqual(dirty.view(NPC).body_semen[0][2], 3)
        edit_svc.edit(13, NPC, 2, 4)
        self.assertEqual(h_state.view(NPC).insert_position, 4)

    def test_lists_and_dates(self) -> None:
        """验证借书集合、孩子列表、怀孕日期与催眠状态的修改规则。"""
        edit_svc.edit(17, NPC, [1, 1, 5], 0)
        self.assertEqual(chara_life.borrow_book_id_set(NPC), {5})
        edit_svc.edit(17, NPC, [1, 0, 5], 0)
        self.assertEqual(chara_life.borrow_book_id_set(NPC), set())
        edit_svc.edit(19, NPC, [2, 1, 7], 0)
        self.assertEqual(relations.child_id_list(NPC), [7])
        edit_svc.edit(18, NPC, [2, 1], 3)
        self.assertEqual(pregnancy.of(NPC).fertilization_time.month, 3)
        edit_svc.edit(18, NPC, 5, 0)
        self.assertEqual(abilities.talent(NPC)[22], 1)
        self.assertEqual(
            pregnancy.of(NPC).fertilization_time.year,
            game_time.now().year - 1,
        )
        self.assertFalse(edit_svc.edit(18, NPC, [3], 1))
        edit_svc.edit(21, NPC, [1, 1], 0)
        edit_svc.edit(21, NPC, [5, 2], 0)
        edit_svc.edit(21, NPC, [5, 4], 0)
        view = hypnosis.view(NPC)
        self.assertTrue(view.increase_body_sensitivity)
        self.assertEqual(view.roleplay[-2:], [2, 4])


class UiFreeRunTest(FastTestCase):
    """验证四个服务在拦截界面与结算导入的独立子进程中可运行。"""

    child: ChildRun
    out: dict

    @classmethod
    def setUpClass(cls) -> None:
        """启动一次受限子进程并保存数据，失败则测试类带其输出报错。"""
        cls.child = run_ui_free(UI_FREE_RUN, boot=True)
        cls.out = cls.child.payload

    def test_no_ui_or_settle_loaded(self) -> None:
        """断言子进程未加载也未尝试导入任何被拦截模块。"""
        self.assertEqual((self.child.loaded, self.child.attempted), ([], []))

    def test_results(self) -> None:
        """断言时钟、名册回调、解析、编辑回读、总数、文本与重建JSON。"""
        out = self.out
        self.assertEqual((out["added"], out["month"]), ([1], 3))
        self.assertEqual(out["ids"], [1, 2, 3])
        self.assertEqual(out["edits"], [True] * len(edit_svc.EDITS))
        self.assertEqual(out["stored"], [2, 2])
        self.assertGreater(out["totals"][0], 0)
        self.assertEqual(out["totals"][0], out["totals"][1])
        for line in (
            "[0001]：c1\n\n",
            "\n已招募过\n",
            "[003]:龙门币：0",
            "\n汇总：共测试 2 条，通过 1 条，未通过 1 条",
        ):
            self.assertIn(line, out["text"])
        self.assertEqual(
            out["built"]["Talk"]["data"],
            [{"cid": "x_t_x_3b", "adv_id": 0, "context": "公共", "version": 1}],
        )

    def test_talk_reports(self) -> None:
        """断言子进程通过/失败注入口上的渲染、前提、结果及缺失提示。"""
        (met, met_ok), (unmet, unmet_ok) = self.out["talks"]
        self.assertEqual((met_ok, unmet_ok), (True, False))
        for line in (
            "口上输出文本：\n  c1对c0说你好\n",
            "  sys_1：满足(√)\n",
            "  sys_4：满足(√)\n",
            "  CVP_A1_F_E_0：满足(√)\n",
            "测试通过，该口上可以触发",
        ):
            self.assertIn(line, met)
        for line in ("  sys_3：不满足(X)\n", "测试未通过，该口上无法触发"):
            self.assertIn(line, unmet)
        self.assertEqual(
            self.out["missing"],
            ["\n未找到该口上（id=999999），请确认是否输入正确\n", False],
        )

    def test_screen_004_error(self) -> None:
        """断言子进程子页004抛已知TypeError消息，其余出错则整类报错。"""
        self.assertEqual(
            self.out.get("screen4"),
            "not all arguments converted during string formatting",
        )
