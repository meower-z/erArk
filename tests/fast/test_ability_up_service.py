"""能力升级与刻印变更服务测试，覆盖分组、需求、写入与无界面边界。"""

import json
import subprocess
import sys

from Script.Config import game_config
from Script.Design import attr_calculation
from Script.Kernel import core
from Script.Modules.domains import abilities, achievement, activity
from Script.Modules.domains import facility, flags, identity, modes
from Script.Modules.gameplay_resolution import ability_up_service as svc
from Script.Modules.gameplay_resolution import mark_change_service as marks
from Script.Modules.gameplay_resolution import working
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

NPC = 1
""" 测试用干员角色编号。 """
PRISON = 19
""" 关押区设施编号常量。 """
BACKEND_RUN = """
import contextlib, importlib.abc, io, json, sys
BLOCKED = ("Script.UI", "Script.Settle",
    "Script.System.Instruct_System.handle_instruct", "Script.Core.flow_handle",
    "Script.Core.io_init", "Script.Frontend", "Script.Modules.tk_ui",
    "tkinter", "_tkinter", "PIL.ImageTk")
attempted = []
def blocked(name):
    return any(name == root or name.startswith(root + ".") for root in BLOCKED)
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if blocked(fullname):
            attempted.append(fullname)
            raise ImportError(fullname)
        return None
sys.meta_path.insert(0, Blocker())
sys.path.insert(0, sys.argv[1])
from Script.Config import game_config, map_config, normal_config
with contextlib.redirect_stdout(io.StringIO()):
    normal_config.init_normal_config()
    game_config.init()
    map_config.init_map_data()
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, facility, flags
from Script.Modules.domains import identity, warehouse
from Script.Modules.gameplay_resolution import ability_up_service as svc
from Script.Modules.gameplay_resolution import mark_change_service as marks
from Script.Modules.gameplay_resolution import working
import datetime
from types import MappingProxyType
from Script.Design import game_time
start = game_time.minutes(datetime.datetime(2020, 5, 3)) + 9 * 60
core.reset_state(core.GameState(start, MappingProxyType({}), MappingProxyType({})))
def scenario(npc_scene):
    out = {}
    with working.based_on(core.state()):
        warehouse.start({})
        for cid in (0, 1):
            identity.put(identity.Identity(cid, name="c" + str(cid), sex=1))
            for table, ids in ((abilities.ability, game_config.config_ability),
                    (abilities.juel, game_config.config_juel),
                    (abilities.experience, game_config.config_experience)):
                for type_id in ids:
                    table(cid)[type_id] = 0
        activity.set_position(0, ["a", "b"])
        activity.set_position(1, npc_scene)
        flags.set(1, imprisonment=1)
        facility.set_level(19, 5)
        abilities.juel(1)[13] = 10000
        out["rows"] = [[group.ability_type,
            [[b.ability_id, b.route, b.highlight] for b in group.buttons]]
            for group in svc.ability_groups(1)]
        offer = marks.mark_up_offer(1, 13)
        out["up"] = [offer.need_juel, offer.enough]
        out["behavior"] = marks.mark_up(1, 13, offer.need_juel)
        out["second"] = activity.second_behavior(1, out["behavior"])
        abilities.ability(1)[18] = 1
        abilities.juel(1)[17] = 12000
        down = marks.mark_down_offer(1, 18)
        out["down"] = [down.need, [list(entry) for entry in down.entries]]
        out["count"] = marks.juel_count(1, 17, "99999")
        out["lowered"] = marks.mark_down(1, 18, {17: 10000})
        abilities.juel(1)[9] = 100
        abilities.experience(1)[80] = 40
        needs = svc.needs(1, svc.level_up_lists(40, 0)[0])
        out["needs"] = [needs.met, sorted(needs.cost.items())]
        out["verdict"] = list(svc.verdict(1, 40, needs.met, True))
        svc.level_up(1, 40, needs.cost)
        out["tables"] = [abilities.ability(1)[13], abilities.ability(1)[18],
            abilities.ability(1)[40], abilities.juel(1)[13],
            abilities.juel(1)[17], abilities.juel(1)[9]]
    return out
default = scenario(["a", "b"])
normal_config.config_normal.language = "en_US"
normal_config.ai_setting.ai_chat_translator_setting = 2
normal_config.ai_setting.ai_chat_setting[1] = 1
switched = scenario(["a", "c"])
print(json.dumps({"default": default, "switched": switched,
    "attempted": attempted,
    "loaded": sorted(name for name in sys.modules
        if name.startswith(("Script.UI", "Script.Settle")) or blocked(name))}))
"""
""" 在拦截界面、结算与窗口模块的子进程中执行两服务核心接口的脚本。 """


class AbilityUpCase(FastTestCase):
    """能力升级服务测试基类，准备博士与阿米娅并开启临时状态缓冲。"""

    def setUp(self) -> None:
        """初始化角色 0 与角色 1 并进入内核状态的临时写缓冲。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(NPC, "阿米娅")
        self.enterContext(working.based_on(core.state()))

    def button(self, cid: int, ability_id: int) -> svc.AbilityButton:
        """从角色能力分组中查找并返回指定能力编号对应的按钮项。"""
        for group in svc.ability_groups(cid):
            for button in group.buttons:
                if button.ability_id == ability_id:
                    return button
        raise AssertionError(ability_id)

    def prison(self, imprisoned: bool, level: int = 5) -> None:
        """设置测试干员的关押状态与关押区设施等级。"""
        flags.set(NPC, imprisonment=int(imprisoned))
        facility.set_level(PRISON, level)


class AbilityRowsTest(AbilityUpCase):
    """能力分组列表、性别过滤、刻印路由、标签间距与升级标记测试。"""

    def test_marks_only_for_operators(self) -> None:
        """验证角色 0 不包含刻印分组而干员包含全部六个能力分组。"""
        player = [group.ability_type for group in svc.ability_groups(0)]
        operator = [group.ability_type for group in svc.ability_groups(NPC)]
        self.assertEqual(player, [0, 1, 3, 4, 5])
        self.assertEqual(operator, [0, 1, 2, 3, 4, 5])

    def test_rows_skip_abilities_of_the_other_sex(self) -> None:
        """验证角色能力列表按 sex_need 跳过不匹配当前性别的能力。"""
        needs = {
            aid: d.sex_need for aid, d in game_config.config_ability.items()
        }
        for sex in (0, 1):
            with self.subTest(sex=sex):
                identity.put(identity.Identity(NPC, name="阿米娅", sex=sex))
                shown = {
                    button.ability_id
                    for group in svc.ability_groups(NPC)
                    for button in group.buttons
                }
                kept = {aid for aid in shown if needs[aid] in (0, 1)}
                self.assertTrue(kept)
                self.assertEqual({needs[aid] for aid in kept}, {sex})

    def test_mark_routes_follow_level_and_data(self) -> None:
        """验证不同刻印在各等级下正确路由至 up、down 或 locked。"""
        cases = (
            (13, 1, "up"),
            (15, 2, "up"),
            (15, 3, "down"),
            (16, 2, "locked"),
            (17, 2, "down"),
            (18, 0, "locked"),
            (19, 1, "locked"),
        )
        for ability_id, level, route in cases:
            with self.subTest(ability_id=ability_id, level=level):
                abilities.ability(NPC)[ability_id] = level
                button = self.button(NPC, ability_id)
                self.assertEqual(button.route, route)
                self.assertTrue(button.text.endswith(f"   {level} "))
                self.assertFalse(button.highlight)

    def test_labels_pad_by_type(self) -> None:
        """验证不同类型普通能力的按钮文案按类型补齐间距并附带评级。"""
        grade = attr_calculation.judge_grade(2)
        cases = (
            (0, " 皮肤感度   "),
            (30, " 技巧       "),
            (40, " 话术技能   "),
        )
        for ability_id, head in cases:
            with self.subTest(ability_id=ability_id):
                abilities.ability(NPC)[ability_id] = 2
                button = self.button(NPC, ability_id)
                self.assertEqual(button.text, f"{head}{grade} 2")
                self.assertEqual(button.route, "ability")

    def test_plus_needs_every_main_requirement(self) -> None:
        """验证普通能力需满足全部主需求且未达 8 级才显示 (+) 高亮。"""
        abilities.juel(NPC)[9] = 100
        cases = ((0, 39, False), (0, 40, True), (8, 40, False))
        for level, exp, plus in cases:
            with self.subTest(level=level, exp=exp):
                abilities.ability(NPC)[40] = level
                abilities.experience(NPC)[80] = exp
                button = self.button(NPC, 40)
                self.assertEqual(button.text.endswith("(+)"), plus)
                self.assertEqual(button.highlight, plus)

    def test_extra_rule_and_debug_mode(self) -> None:
        """验证额外能力条件会阻断 (+) 标记且调试模式会覆盖该限制。"""
        abilities.ability(NPC)[30] = 1
        abilities.juel(NPC)[9] = 400
        self.assertFalse(self.button(NPC, 30).highlight)
        modes.set_debug(True)
        self.assertTrue(self.button(NPC, 30).highlight)
        self.assertTrue(self.button(NPC, 40).text.endswith("(+)"))


class MarkFlagsTest(AbilityUpCase):
    """刻印升降级标记、关押区折扣、宝珠权重与快感珠展开测试。"""

    def test_mark_up_plus_when_jewels_cover_the_gap(self) -> None:
        """验证刻印宝珠库存刚好覆盖缺口时按钮才附带 (+) 标记。"""
        for juel, plus in ((9999, False), (10000, True)):
            with self.subTest(juel=juel):
                abilities.juel(NPC)[13] = juel
                button = self.button(NPC, 13)
                self.assertEqual(button.text, " 快乐刻印   0 " + "(+)" * plus)

    def test_prisoner_discount_decides_minus(self) -> None:
        """验证干员被关押时按关押区折扣决定刻印降级 (-) 标记。"""
        abilities.ability(NPC)[18] = 1
        cases = (
            (True, 15000, True),
            (False, 15000, False),
            (True, 9000, False),
        )
        for imprisoned, pain, minus in cases:
            with self.subTest(imprisoned=imprisoned, pain=pain):
                self.prison(imprisoned)
                abilities.juel(NPC)[17] = pain
                button = self.button(NPC, 18)
                self.assertEqual(button.text.endswith("(-)"), minus)

    def test_jewel_weights_count_toward_minus(self) -> None:
        """验证刻印降级判定按配置权重累计多种宝珠的总值。"""
        abilities.ability(NPC)[18] = 1
        self.prison(False)
        abilities.juel(NPC)[15] = 6666
        self.assertFalse(self.button(NPC, 18).highlight)
        abilities.juel(NPC)[10] = 1
        self.assertTrue(self.button(NPC, 18).highlight)

    def test_placeholder_expands_to_pleasure_jewels(self) -> None:
        """验证占位符 "1" 展开为状态类型 0 的宝珠，且编号为 0 的条目不计入。"""
        abilities.ability(NPC)[15] = 3
        self.prison(False)
        offer = marks.mark_down_offer(NPC, 15)
        ids = [13, 1, 2, 3, 4, 5, 6, 7, 21, 22, 23]
        self.assertEqual(offer.entries, tuple((i, 1) for i in ids))
        abilities.juel(NPC)[1] = 50000
        self.assertEqual(self.button(NPC, 15).text, " 苦痛刻印   3 (-)")
        abilities.juel(NPC)[1] = 0
        abilities.juel(NPC)[0] = 50000
        self.assertEqual(self.button(NPC, 15).text, " 苦痛刻印   3 ")


class LevelUpTest(AbilityUpCase):
    """普通能力需求行生成、次需求、最终判定与升级写入测试。"""

    def test_needs_rows_cost_and_verdict(self) -> None:
        """验证主需求行文案、满足标志、宝珠消耗表与 verdict 透传。"""
        abilities.juel(NPC)[9] = 150
        abilities.experience(NPC)[80] = 10
        main, second = svc.level_up_lists(40, 0)
        self.assertEqual(second, [])
        needs = svc.needs(NPC, main)
        self.assertEqual(
            needs.rows,
            (
                "需要宝珠 : 习得珠 至少为100，当前为150\n",
                f"需要经验 : {game_config.config_experience[80].name} 至少为40，当前为10\n",
            ),
        )
        self.assertFalse(needs.met)
        self.assertEqual(dict(needs.cost), {9: 100})
        self.assertEqual(svc.verdict(NPC, 40, True, True), (True, True))
        self.assertEqual(svc.verdict(NPC, 40, False, True), (False, True))

    def test_secondary_list_and_extra_rule(self) -> None:
        """验证次需求列表读取、额外规则拦截与调试模式放行。"""
        self.assertEqual(svc.level_up_lists(31, 0)[1], ["J15|100"])
        abilities.ability(NPC)[30] = 1
        self.assertEqual(svc.verdict(NPC, 30, True, True), (False, False))
        modes.set_debug(True)
        self.assertEqual(svc.verdict(NPC, 30, False, False), (True, True))

    def test_level_up_spends_raises_and_awards(self) -> None:
        """验证 level_up 扣除宝珠、提升能力 1 级并解锁对应技能成就。"""
        abilities.juel(0)[9] = 130
        svc.level_up(0, 40, {9: 100})
        self.assertEqual(abilities.juel(0)[9], 30)
        self.assertEqual(abilities.ability(0)[40], 1)
        self.assertTrue(achievement.done(501))


class MarkWriteTest(AbilityUpCase):
    """刻印升降级报价文案、写入操作与宝珠数量输入校验测试。"""

    def test_mark_up_offer_and_write(self) -> None:
        """验证刻印升级报价内容及 mark_up 扣珠、升级与授予二段行为。"""
        abilities.juel(NPC)[13] = 9999
        self.assertFalse(marks.mark_up_offer(NPC, 13).enough)
        abilities.juel(NPC)[13] = 12000
        offer = marks.mark_up_offer(NPC, 13)
        self.assertEqual((offer.need_juel, offer.enough), (10000, True))
        for line in (
            "当前刻印及等级为：快乐刻印 - 0\n",
            "升级需要的总值为：10000\n",
            "减去提供值后需要消耗的宝珠为：快乐珠 10000，当前拥有：12000\n",
        ):
            self.assertIn(line, offer.text)
        behavior = marks.mark_up(NPC, 13, offer.need_juel)
        self.assertEqual(behavior, "happy_mark_1")
        self.assertEqual(abilities.juel(NPC)[13], 2000)
        self.assertEqual(abilities.ability(NPC)[13], 1)
        self.assertEqual(activity.second_behavior(NPC, behavior), 1)

    def test_mark_down_offer_states_discount(self) -> None:
        """验证关押状态下刻印降级报价包含折扣说明并折减所需总值。"""
        abilities.ability(NPC)[18] = 1
        self.prison(True)
        offer = marks.mark_down_offer(NPC, 18)
        self.assertEqual(offer.need, 10000)
        self.assertEqual(offer.entries, ((10, 2.0), (15, 3.0), (17, 1)))
        self.assertTrue(
            offer.text.endswith(
                "降级需要的总值为：20000\n该干员已被关押，当前关押区等级为5，"
                "降级所需宝珠值降低50%，降级所需宝珠值为10000\n"
            )
        )
        self.prison(False)
        self.assertEqual(marks.mark_down_offer(NPC, 18).need, 20000)

    def test_mark_down_lowers_and_spends(self) -> None:
        """验证 mark_down 降低刻印等级、扣除所选宝珠并返回成功提示。"""
        abilities.ability(NPC)[18] = 2
        abilities.juel(NPC)[10] = 7
        abilities.juel(NPC)[17] = 900
        text = marks.mark_down(NPC, 18, {10: 0, 17: 500})
        self.assertEqual(text, "\n刻印降级成功，反发刻印降至1级\n")
        self.assertEqual(abilities.ability(NPC)[18], 1)
        self.assertEqual(abilities.juel(NPC)[10], 7)
        self.assertEqual(abilities.juel(NPC)[17], 400)

    def test_jewel_prompt_and_count(self) -> None:
        """验证宝珠输入提示的预计需求计算及输入文本的解析与上限夹紧。"""
        abilities.juel(NPC)[15] = 80
        self.assertEqual(
            marks.juel_prompt(NPC, 15, 3.0, 3000, 10000, 2),
            "\n请输入要使用的宝珠数量，最多可以使用80个屈服珠，当前使用量为2，预计需要2333个\n",
        )
        self.assertIn("预计需要0个", marks.juel_prompt(NPC, 15, 3.0, 9, 9, 0))
        cases = (("abc", None), ("", None), ("0", 0), ("5", 5), ("999", 80))
        for text, count in cases:
            with self.subTest(text=text):
                self.assertEqual(marks.juel_count(NPC, 15, text), count)


class BackendIsolationTest(FastTestCase):
    """两服务模块的无界面与无结算导入边界独立子进程测试。"""

    def test_fresh_backend_process_loads_no_ui_or_settle(self) -> None:
        """验证默认与切换语言及 AI 设置下两服务运行一致且无受限导入。"""
        result = subprocess.run(
            [sys.executable, "-c", BACKEND_RUN, str(ROOT)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        out = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(out["attempted"], [])
        self.assertEqual(out["loaded"], [])
        self.assertEqual(out["switched"], out["default"])
        run = out["default"]
        self.assertEqual(run["up"], [10000, True])
        self.assertEqual(run["behavior"], "happy_mark_1")
        self.assertEqual(run["second"], 1)
        self.assertEqual(run["down"], [10000, [[10, 2.0], [15, 3.0], [17, 1]]])
        self.assertEqual(run["count"], 12000)
        self.assertEqual(run["needs"], [True, [[9, 100]]])
        self.assertEqual(run["verdict"], [True, True])
        self.assertEqual(run["tables"], [1, 0, 1, 0, 2000, 0])
        marks_row = dict((row[0], row[1]) for row in run["rows"])[2]
        self.assertIn([13, "up", True], marks_row)
