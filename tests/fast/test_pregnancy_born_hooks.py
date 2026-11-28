"""
生产与破壳触发入口及无界面子进程测试
====================================
BornCase 与 EggCase 提供共用的角色初始化、回调打桩与产卵辅助方法。
CheckBornTest 验证 check_born 按过期天数与掷骰几率触发胎生生产。
CheckHardEggBornTest 验证带壳卵生单次检查仅孵化首枚到期受精卵。
CheckSoftEggBornTest 验证无壳卵生一次孵化全部到期受精卵。
UiFreeTest 在无界面子进程中验证未登记报错、胎生生产、无壳卵孵化与界面模块隔离，
并在流程中运行真实的 talk.must_show_talk_check 必显对话检查。
"""

import datetime
from unittest import mock

from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import abilities, pregnancy, relations
from Script.Modules.gameplay_resolution import achievement_service, modal_hooks
from Script.Modules.gameplay_resolution import pregnancy_hooks, working
from Script.Protocol.modal_prompts import ChoicePrompt, ChoiceResult
from Script.System.Pregnancy_System import egg_handle
from Script.System.Pregnancy_System import pregnancy_constant, pregnancy_handle
from tests import chara_abilities as ca
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import run_ui_free

MOTHER = 1
""" 测试使用的母亲角色编号（1）。 """
HARD_EGG_RACE = 6
""" 测试使用的带壳卵生种族编号（6）。 """
SOFT_EGG_RACE = 11
""" 测试使用的无壳卵生种族编号（11）。 """
UI_FREE_RUN = """
import datetime
from Script.Config import map_config, normal_config
from Script.Design import attr_calculation, game_time, talk
from Script.Modules.domains import abilities, activity, identity, pregnancy
from Script.Modules.domains import relations, roster, warehouse
from Script.Modules.gameplay_resolution import modal_hooks, pregnancy_hooks
from Script.Protocol.modal_prompts import ChoiceResult
from Script.System.Pregnancy_System import egg_handle, pregnancy_constant
from Script.System.Pregnancy_System import pregnancy_handle
from tests import chara_abilities, chara_data, kernel_data
from tests.chara_activity import place
from tests.world import DEFAULT_SCENE, start_time
map_config.init_map_data()
normal_config.system_setting = attr_calculation.get_system_setting_zero()
real_check = talk.must_show_talk_check
shown = []
def check(cid):
    shown.append([cid, list(activity.must_show(cid))])
    real_check(cid)
talk.must_show_talk_check = check
kernel_data.reset_clock(start_time(), {})
kernel_data.written(warehouse.start, {})
for cid, race in ((0, 0), (1, 0), (2, 11)):
    kernel_data.put(identity.put, identity.Identity(cid, name=f"c{cid}", sex=1, race=race))
    chara_abilities.zero_tables(cid)
    chara_data.seed(cid, {})
    place(cid, DEFAULT_SCENE)
days = datetime.timedelta(days=pregnancy_constant.PARTURIENT_DAY + 5)
hatch = datetime.timedelta(days=pregnancy_constant.HATCH_TOTAL_DAY)
try:
    pregnancy_hooks.ask_name("x")
except RuntimeError as error:
    payload["unnamed"] = str(error)
asked = []
with kernel_data.writing():
    roster.add(1)
    roster.add(2)
    abilities.talent(1)[22] = 1
    pregnancy.update(1, fertilization_time=game_time.now() - days, fetus_count=1)
    try:
        pregnancy_handle.check_born(1)
    except RuntimeError as error:
        payload["unasked"] = str(error)
    modal_hooks.on_choice(lambda prompt: asked.append(prompt.prompt_id) or ChoiceResult(prompt.prompt_id, "wait"))
    names = iter(["kid1", "kid2", "kid3"])
    pregnancy_hooks.on_name_input(lambda text: next(names))
    pregnancy_handle.check_born(1)
    for _ in range(2):
        egg_id = egg_handle.add_egg(2, True, soft=True)
        with pregnancy.editing(2) as preg:
            preg.eggs[egg_id]["identified"] = True
            preg.eggs[egg_id]["lay_time"] -= hatch
    egg_handle.check_egg_born(2)
    payload["children"] = [[identity.of(c).name for c in relations.child_id_list(m)] for m in (1, 2)]
    payload["eggs"] = len(pregnancy.of(2).eggs)
    behaviors = ("born", "postpartum", "soft_egg_born")
    payload["left"] = [[activity.must_show(c), [activity.second_behavior(c, b) for b in behaviors]] for c in (1, 2)]
payload["shown"] = shown
payload["asked"] = asked
"""
""" 在无界面子进程中验证未登记报错、真实必显对话检查、生产与无壳卵孵化及隔离的脚本源码。 """


class BornCase(FastTestCase):
    """生产与破壳入口进程内测试的共用基类。"""

    race = 0

    def setUp(self) -> None:
        """初始化玩家与母亲角色、工作集，并打桩选项提示、取名与成就回调。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(MOTHER, "测试母亲", race=self.race)
        self.enterContext(working.based_on(core.state()))
        self.asked: list[str] = []
        self.named = 0
        for owner, name, value in (
            (modal_hooks, "_ask", self.answer),
            (pregnancy_hooks, "_name_input", self.name),
            (achievement_service, "settle_and_notify", mock.Mock()),
        ):
            self.enterContext(mock.patch.object(owner, name, value))

    def answer(self, prompt: ChoicePrompt) -> ChoiceResult:
        """记录提示标识并返回首项对应的 ChoiceResult。"""
        self.asked.append(prompt.prompt_id)
        return ChoiceResult(prompt.prompt_id, prompt.options[0].option_id)

    def name(self, ask_text: str) -> str:
        """按调用顺序依次返回不重复的新生儿测试名「小宝1」「小宝2」等。"""
        self.named += 1
        return f"小宝{self.named}"

    def children(self) -> int:
        """返回母亲名下当前子女数量。"""
        return len(relations.child_id_list(MOTHER))


class CheckBornTest(BornCase):
    """pregnancy_handle.check_born 触发条件与掷骰边界的测试。"""

    def pregnant(self, parturient: bool, extra_days: int) -> None:
        """按临盆标记与超期天数设置母亲素质（22、23）及受精时间。"""
        talent = ca.talent(MOTHER)
        talent[22] = int(parturient)
        talent[23] = 0
        past = pregnancy_constant.PARTURIENT_DAY + extra_days
        when = game_time.now() - datetime.timedelta(days=past)
        pregnancy.update(MOTHER, fertilization_time=when)

    def test_no_birth_without_winning_roll(self) -> None:
        """验证未临盆、未超期或掷骰高于几率时 check_born 不触发生产且保留原临盆素质。"""
        for parturient, extra_days, roll in (
            (False, 5, 1),
            (True, 0, 1),
            (True, 2, 41),
        ):
            with self.subTest(parturient=parturient, extra_days=extra_days):
                self.pregnant(parturient, extra_days)
                with mock.patch.object(
                    pregnancy_handle.random, "randint", return_value=roll
                ):
                    pregnancy_handle.check_born(MOTHER)
                self.assertEqual((self.asked, self.children()), ([], 0))
                self.assertEqual(abilities.talent(MOTHER)[22], int(parturient))

    def test_winning_roll_gives_birth(self) -> None:
        """验证掷骰等于触发几率（含临界 40 与 100）时 check_born 触发生产并转为产后。"""
        for count, (extra_days, roll) in enumerate(((2, 40), (5, 100)), 1):
            with self.subTest(extra_days=extra_days, roll=roll):
                self.pregnant(True, extra_days)
                with mock.patch.object(
                    pregnancy_handle.random, "randint", return_value=roll
                ):
                    pregnancy_handle.check_born(MOTHER)
                self.assertEqual(self.children(), count)
                talent = abilities.talent(MOTHER)
                self.assertEqual((talent[22], talent[23]), (0, 1))


class EggCase(BornCase):
    """卵生破壳入口测试基类，提供产卵、读取孵化阶段与未到期断言辅助。"""

    def lay(
        self, days_ago: int, identified: bool = True, fertilized: bool = True
    ) -> int:
        """为母亲添加一枚指定产卵天数、鉴定状态与受精状态的卵并返回其编号。"""
        egg_id = egg_handle.add_egg(
            MOTHER, fertilized, soft=self.race == SOFT_EGG_RACE
        )
        with pregnancy.editing(MOTHER) as preg:
            egg = preg.eggs[egg_id]
            egg["identified"] = identified
            egg["lay_time"] -= datetime.timedelta(days=days_ago)
        return egg_id

    def stages(self) -> dict[int, int]:
        """返回母亲当前全部卵编号到 hatch_stage 的映射字典。"""
        return {
            egg_id: egg["hatch_stage"]
            for egg_id, egg in pregnancy.of(MOTHER).eggs.items()
        }

    def assert_no_due_egg_hatches(self) -> None:
        """断言未鉴定、未受精与未满孵化天数的卵均不触发破壳且阶段计数符合预期。"""
        total = pregnancy_constant.HATCH_TOTAL_DAY
        unidentified = self.lay(total, identified=False)
        unfertilized = self.lay(total, fertilized=False)
        young = self.lay(total - 1)
        egg_handle.check_egg_born(MOTHER)
        self.assertEqual((self.asked, self.children()), ([], 0))
        self.assertEqual(
            self.stages(),
            {unidentified: 0, unfertilized: 0, young: total - 1},
        )


class CheckHardEggBornTest(EggCase):
    """egg_handle.check_egg_born 在带壳卵生种族下的触发测试。"""

    race = HARD_EGG_RACE

    def test_no_due_egg_hatches(self) -> None:
        """验证带壳卵生没有到期已鉴定受精卵时不触发破壳。"""
        self.assert_no_due_egg_hatches()

    def test_hatches_first_due_egg_only(self) -> None:
        """验证带壳卵生存在多枚到期卵时仅孵化首枚到期卵，其余到期卵暂留且保持原孵化阶段。"""
        total = pregnancy_constant.HATCH_TOTAL_DAY
        young = self.lay(total - 1)
        self.lay(total + 1)
        second = self.lay(total)
        egg_handle.check_egg_born(MOTHER)
        self.assertEqual(self.children(), 1)
        self.assertEqual(self.stages(), {young: total - 1, second: 0})


class CheckSoftEggBornTest(EggCase):
    """egg_handle.check_egg_born 在无壳卵生种族下的触发测试。"""

    race = SOFT_EGG_RACE

    def test_no_due_egg_hatches(self) -> None:
        """验证无壳卵生没有到期已鉴定受精卵时不触发破壳。"""
        self.assert_no_due_egg_hatches()

    def test_hatches_all_due_eggs(self) -> None:
        """验证无壳卵生一次孵化全部到期卵且仅发起一次等待提示，未到期卵保留原状。"""
        total = pregnancy_constant.HATCH_TOTAL_DAY
        self.lay(total + 1)
        young = self.lay(total - 1)
        self.lay(total)
        egg_handle.check_egg_born(MOTHER)
        self.assertEqual(self.children(), 2)
        self.assertEqual(self.stages(), {young: total - 1})
        self.assertEqual(self.asked, ["born_wait"])


class UiFreeTest(FastTestCase):
    """无界面子进程中生产与破壳链路及模块隔离测试。"""

    def test_birth_and_hatch_run_without_ui(self) -> None:
        """
        验证无界面子进程中未登记报错、胎生与无壳卵孵化结果及零界面模块加载。
        同时验证真实 talk.must_show_talk_check 依次消费必显队列并清零对应二段行为。
        """
        child = run_ui_free(UI_FREE_RUN, boot=True)
        self.assertEqual(
            child.payload,
            {
                "unnamed": "no name input handler for 'x'",
                "unasked": "born flow needs choice and name input handlers",
                "children": [["kid1"], ["kid2", "kid3"]],
                "eggs": 0,
                "asked": ["born_wait", "born_wait"],
                "shown": [
                    [1, ["born"]],
                    [1, ["postpartum"]],
                    [2, ["soft_egg_born"]],
                ],
                "left": [[[], [0, 0, 0]], [[], [0, 0, 0]]],
            },
        )
        self.assertEqual((child.attempted, child.loaded), ([], []))
