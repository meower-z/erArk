"""
招募服务面板逻辑测试
====================
覆盖招募线候选筛选、可选策略文本、专员表格与排序、主专员任命、策略写入及无界面子进程运行。
"""

import dataclasses
import json
import subprocess
import sys

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import attr_calculation, handle_ability
from Script.Kernel import core
from Script.Modules.domains import abilities, identity, location, npc_template
from Script.Modules.domains import recruit, relations, work
from Script.Modules.gameplay_resolution import recruit_service as svc
from Script.Modules.gameplay_resolution import working
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

_ = get_text._
AGE, CHEST, HIP = (101, 102), (122, 123), (126, 127)
""" 年龄、胸部与臀部三类素质各两个的测试用编号对 """
BLOCKED_RUN = """
import contextlib, importlib.abc, io, json, sys
BLOCKED = ("Script.UI", "Script.Settle",
    "Script.System.Instruct_System.handle_instruct", "Script.Core.flow_handle",
    "Script.Modules.tk_ui", "tkinter", "_tkinter", "PIL.ImageTk")
attempts = []
def blocked(name):
    return any(name == root or name.startswith(root + ".") for root in BLOCKED)
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if blocked(fullname):
            attempts.append(fullname)
            raise ImportError(fullname)
        return None
sys.meta_path.insert(0, Blocker())
sys.path.insert(0, sys.argv[1])
from types import MappingProxyType
from Script.Config import character_config, game_config, normal_config
with contextlib.redirect_stdout(io.StringIO()):
    normal_config.init_normal_config()
    game_config.init()
    character_config.init_character_tem_data()
from Script.Core import get_text
from Script.Kernel import core
from Script.Modules.domains import abilities, facility, identity, recruit, work
from Script.Modules.gameplay_resolution import recruit_service as svc, working
core.reset_state(core.GameState(0, MappingProxyType({}), MappingProxyType({})))
out = {}
with working.based_on(core.state()):
    for cid, name in ((0, "player"), (5, "first"), (7, "second")):
        identity.put(identity.Identity(cid, name=name))
        for talent_id in game_config.config_talent:
            abilities.talent(cid)[talent_id] = 0
    abilities.ability(5)[40] = 2
    abilities.ability(7)[40] = 4
    work.set_rosters({work.HR_WORK: (5, 7)})
    facility.set_level(7, 3)
    recruit.open_lines([0, 1])
    svc.appoint_main_hr(0, 5)
    svc.appoint_main_hr(1, 9)
    svc.set_line_strategy(1, 11)
    out["lines"] = [list(line.values()) for line in recruit.lines().values()]
    out["sub"] = svc.sub_hr_ids()
    out["rows"] = [svc.hr_cells(0, True)[0], svc.hr_cells(7, False)[0]]
    out["vacant"] = get_text._("空缺")
    out["candidates"] = [
        svc.line_candidates(1, 0, [7, 5]),
        svc.line_candidates(2, 0, [7, 5]),
        svc.line_candidates(4, 5, [7, 5]),
    ]
    out["options"] = [option.cid for option in svc.strategy_options(0)]
    out["stopped"] = svc.calculate_recruit_line_efficiency(1)[1]
out["attempts"] = attempts
out["loaded"] = sorted(
    name for name in sys.modules
    if name.startswith(("Script.UI", "Script.Settle")) or blocked(name)
)
print(json.dumps(out))
"""
""" 在拦截界面、结算与 Tk 导入的子进程中运行招募服务并输出 JSON 结果的脚本 """


def options(level: int) -> list[int]:
    """按配置顺序返回需求设施等级不超过 level 的招募策略编号列表。"""
    table = game_config.config_recruitment_strategy
    return [cid for cid, data in table.items() if data.lv <= level]


class RecruitCase(FastTestCase):
    """招募服务测试基类，初始化测试角色、工作集写缓冲及特征配置样本。"""

    def setUp(self) -> None:
        """创建博士与四名非女儿模板角色、开启写缓冲，并各取两项势力、出生地、职业与种族配置编号。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.ids = sorted(
            cid
            for cid, tem in npc_template.table().items()
            if cid and tem.Mother_id == 0 and tem.AdvNpc < 9000
        )[:4]
        for index, cid in enumerate(self.ids):
            self.world.chara(cid, f"角色{index}")
        self.enterContext(working.based_on(core.state()))
        self.nations = sorted(game_config.config_nation)[:2]
        self.places = sorted(game_config.config_birthplace)[:2]
        self.jobs = sorted(game_config.config_profession)[:2]
        self.races = sorted(game_config.config_race)[:2]

    def traits(self, cid: int, pick: int) -> None:
        """按 pick 为角色 cid 设置四项基础特征、清零素质 121，并启用对应年龄、胸部与臀部素质。"""
        relations.nation.set(cid, self.nations[pick])
        relations.birthplace.set(cid, self.places[pick])
        identity.put(
            dataclasses.replace(
                identity.of(cid),
                profession=self.jobs[pick],
                race=self.races[pick],
            )
        )
        talent = abilities.talent(cid)
        talent[121] = 0
        for pair in (AGE, CHEST, HIP):
            talent[pair[pick]] = 1


class LineCandidatesTest(RecruitCase):
    """line_candidates 招募线候选筛选测试。"""

    def test_local_and_all_strategies(self) -> None:
        """断言策略 0 按输入顺序保留所在国出身候选，策略 1 按原序返回全部候选。"""
        local, far, other = self.ids[:3]
        country = location.country()
        elsewhere = next(
            i for i in game_config.config_birthplace if i != country
        )
        relations.birthplace.set(local, country)
        relations.birthplace.set(far, elsewhere)
        relations.birthplace.set(other, country)
        order = [other, far, local]
        self.assertEqual(svc.line_candidates(0, 0, order), [other, local])
        self.assertEqual(svc.line_candidates(1, 0, order), order)

    def test_same_trait_as_main(self) -> None:
        """断言策略 2 至 8 各自保留与主专员特征一致的候选并排除不一致的候选。"""
        main, same, other = self.ids[:3]
        self.traits(main, 0)
        self.traits(same, 0)
        self.traits(other, 1)
        for strategy in range(2, 9):
            with self.subTest(strategy=strategy):
                self.assertEqual(
                    svc.line_candidates(strategy, main, [other, same]), [same]
                )

    def test_vacant_main_or_closed_strategy_finds_nobody(self) -> None:
        """断言主专员为 0 时的策略 2 至 8 以及有主专员时的策略 10 与 11 均返回空列表。"""
        main = self.ids[0]
        for cid in self.ids:
            self.traits(cid, 0)
        for strategy in range(2, 9):
            with self.subTest(strategy=strategy):
                self.assertEqual(svc.line_candidates(strategy, 0, self.ids), [])
        for strategy in (10, 11):
            with self.subTest(strategy=strategy):
                self.assertEqual(
                    svc.line_candidates(strategy, main, self.ids), []
                )


class StrategyOptionsTest(RecruitCase):
    """strategy_options 可选策略列表与文案测试。"""

    def test_options_follow_facility_level(self) -> None:
        """断言设施 7 等级为 1、3、6 时返回的策略编号列表与对应等级配置一致。"""
        recruit.open_lines([0])
        for level in (1, 3, 6):
            kernel_data.set_facility_level(7, level)
            with self.subTest(level=level):
                cids = [option.cid for option in svc.strategy_options(0)]
                self.assertEqual(cids, options(level))

    def test_option_text_names_country_and_main_trait(self) -> None:
        """断言策略文案格式正确，策略 0 附所在国名，策略 2 至 8 有主专员时附特征名，1 与 10 无后缀。"""
        main = self.ids[0]
        self.traits(main, 1)
        recruit.open_lines([0])
        kernel_data.set_facility_level(7, 6)
        table = game_config.config_recruitment_strategy
        heads = {
            cid: f"[{cid:02}]"
            + attr_calculation.pad_display_width(data.name, 24)
            + _("(调整系数{0})").format(data.adjust)
            + "："
            + data.introduce
            for cid, data in table.items()
        }
        country = game_config.config_birthplace[location.country()].name
        suffix = _("（{0}）")
        vacant = {o.cid: o.text for o in svc.strategy_options(0)}
        self.assertEqual(vacant[0], heads[0] + suffix.format(country))
        self.assertEqual(vacant[1], heads[1])
        self.assertEqual(vacant[2], heads[2])
        recruit.appoint(0, main)
        named = {o.cid: o.text for o in svc.strategy_options(0)}
        names = {
            2: game_config.config_nation[self.nations[1]].name,
            3: game_config.config_birthplace[self.places[1]].name,
            4: game_config.config_profession[self.jobs[1]].name,
            5: game_config.config_race[self.races[1]].name,
            6: game_config.config_talent[AGE[1]].name,
            7: game_config.config_talent[CHEST[1]].name,
            8: game_config.config_talent[HIP[1]].name,
        }
        for cid, name in names.items():
            with self.subTest(strategy=cid):
                self.assertEqual(named[cid], heads[cid] + suffix.format(name))
        self.assertEqual(named[10], heads[10])


class HrTest(RecruitCase):
    """专员表格单元格、副专员排序与主专员任命测试。"""

    def test_vacant_row(self) -> None:
        """断言角色编号为 0 时 hr_cells 返回空缺及九个横线单元格。"""
        self.assertEqual(svc.hr_cells(0, True), (_("空缺"),) + ("-",) * 9)

    def test_main_and_sub_rows(self) -> None:
        """断言 hr_cells 正确生成主专员与副专员单元格，且副专员加成为主专员的五分之一。"""
        cid = self.ids[0]
        self.traits(cid, 1)
        abilities.ability(cid)[40] = 3
        effect = 2 * handle_ability.get_ability_adjust(3)
        names = (
            game_config.config_nation[self.nations[1]].name,
            game_config.config_birthplace[self.places[1]].name,
            game_config.config_profession[self.jobs[1]].name,
            game_config.config_race[self.races[1]].name,
            game_config.config_talent[AGE[1]].name,
            game_config.config_talent[CHEST[1]].name,
            game_config.config_talent[HIP[1]].name,
        )
        grade = f"{attr_calculation.judge_grade(3)} 3"
        name = identity.of(cid).name
        main = (name, f"{round(effect, 1)}%", grade, *names)
        sub = (name, f"{round(effect / 5, 1)}%", grade, *names)
        self.assertEqual(svc.hr_cells(cid, True), main)
        self.assertEqual(svc.hr_cells(cid, False), sub)

    def test_unknown_trait_shows_dash(self) -> None:
        """断言特征编号不在配置表内时对应单元格显示为短横线。"""
        cid = self.ids[0]
        self.traits(cid, 0)
        relations.nation.set(cid, max(game_config.config_nation) + 1)
        self.assertEqual(svc.hr_cells(cid, True)[3], "-")

    def test_sub_staff_skip_mains_by_speech_level(self) -> None:
        """断言 sub_hr_ids 排除主专员，按话术等级降序排列并在同级时保持名册顺序。"""
        first, second, main, third = self.ids
        work.set_rosters({work.HR_WORK: (first, second, main, third)})
        for cid, level in zip(self.ids, (1, 5, 3, 5), strict=True):
            abilities.ability(cid)[40] = level
        recruit.open_lines([0])
        svc.appoint_main_hr(0, main)
        self.assertEqual(svc.sub_hr_ids(), [second, third, first])

    def test_appoint_only_staff_and_toggle(self) -> None:
        """断言 appoint_main_hr 忽略非人事名册角色，并支持任命、换线与重复点击撤销。"""
        staff, outsider = self.ids[:2]
        work.set_rosters({work.HR_WORK: (staff,)})
        recruit.open_lines([0, 1])

        def mains() -> list[int]:
            """按当前招募线顺序返回各线主专员角色编号列表。"""
            return [line["main"] for line in recruit.lines().values()]

        svc.appoint_main_hr(0, outsider)
        self.assertEqual(mains(), [0, 0])
        svc.appoint_main_hr(0, staff)
        self.assertEqual(mains(), [staff, 0])
        svc.appoint_main_hr(1, staff)
        self.assertEqual(mains(), [0, staff])
        svc.appoint_main_hr(1, staff)
        self.assertEqual(mains(), [0, 0])


class LineStrategyTest(RecruitCase):
    """set_line_strategy 招募线策略写入测试。"""

    def test_stopping_clears_progress_others_keep_it(self) -> None:
        """断言策略设为 11 时清零招募线进度，设为其他策略时保留当前进度。"""
        recruit.open_lines([0, 1])
        recruit.set_line(0, progress=40)
        recruit.set_line(1, progress=40)
        svc.set_line_strategy(0, 3)
        svc.set_line_strategy(1, 11)
        lines = recruit.lines()
        self.assertEqual(
            lines[0], {**recruit.IDLE, "progress": 40, "strategy": 3}
        )
        self.assertEqual(lines[1], {**recruit.IDLE, "strategy": 11})


class FreshProcessTest(FastTestCase):
    """招募服务无界面无结算模块运行的子进程测试。"""

    def test_backend_runs_without_ui_or_settle(self) -> None:
        """断言拦截界面与结算导入的子进程可正常调用招募服务接口且不加载受限模块。"""
        result = subprocess.run(
            [sys.executable, "-c", BLOCKED_RUN, str(ROOT)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        out = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(out["attempts"], [])
        self.assertEqual(out["loaded"], [])
        self.assertEqual(out["lines"], [[0, 0, 5], [0, 11, 0]])
        self.assertEqual(out["sub"], [7])
        self.assertEqual(out["rows"], [out["vacant"], "second"])
        self.assertEqual(out["candidates"], [[7, 5], [], [7, 5]])
        self.assertEqual(out["options"], options(3))
        self.assertEqual(out["stopped"], 0.0)
