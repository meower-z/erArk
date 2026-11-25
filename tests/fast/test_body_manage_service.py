"""
身体管理服务测试
================
验证身体管理条件判定、硬性前置与冲突校验、管理行过滤与调试模式放开。
验证管理表补齐、开关切换与性爱练习生职业联动、批量取消及无界面子进程隔离。
"""

from Script.Config import game_config
from Script.Design import attr_calculation
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, body_manage, chara_life
from Script.Modules.domains import hypnosis, inventory, modes
from Script.Modules.domains import player_collection, work
from Script.Modules.gameplay_resolution import body_manage_service as svc
from Script.Modules.gameplay_resolution import working
from tests.chara_activity import aim
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ChildRun, run_ui_free

NPC = 1
""" 测试用目标干员编号。 """
CORSET = 3
""" 无前置检查要求的测试管理项编号（编号 3）。 """
NIPPLE_CLAMP = 11
""" 需要乳头检查前置与乳夹道具的测试管理项编号（编号 11）。 """
UI_FREE_RUN = """
from Script.Config import game_config
from Script.Design import attr_calculation
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, body_manage, chara_life
from Script.Modules.domains import hypnosis, identity, inventory, modes, roster
from Script.Modules.gameplay_resolution import body_manage_service as svc
from Script.Modules.gameplay_resolution import working
with working.based_on(core.state()):
    for cid, name in ((0, "doctor"), (1, "patient")):
        identity.put(identity.Identity(cid, name=name))
        abilities.talent(cid).replace(attr_calculation.get_talent_zero({}))
        abilities.ability(cid).replace(attr_calculation.get_ability_zero({}))
        abilities.experience(cid).replace(attr_calculation.get_experience_zero({}))
        inventory.replace_items(cid, attr_calculation.get_item_zero({}))
    roster.add(1)
    activity.set_target(0, 1)
    body_manage.replace(1, {})
    svc.ensure_table(1)
    body_manage.replace(1, {3: 1})
    svc.ensure_table(1)
    payload["filled"] = len(body_manage.of(1))
    ids = list(game_config.config_body_manage_requirement)
    payload["low"] = [svc.requirement(i, 1) for i in ids]
    abilities.talent(1)[0] = abilities.talent(1)[1] = 1
    hypnosis.set(1, hypnosis_degree=300)
    for item in (122, 123, 125):
        inventory.set_item(0, item, 1)
    body_manage.set(1, 23, 1)
    body_manage.set(1, 26, 1)
    payload["high"] = [svc.requirement(i, 1) for i in ids]
    payload["rows"] = [r.available for r in svc.manage_rows(1, set())]
    modes.set_debug(True)
    payload["debug"] = [r.available for r in svc.manage_rows(1, set())]
    texts = [svc.toggle(31, 1), svc.toggle(32, 1)]
    payload["job_on"] = chara_life.work_type(1)
    texts += [svc.toggle(31, 1), svc.toggle(32, 1), svc.toggle(3, 1)]
    payload["job_off"] = chara_life.work_type(1)
    payload["texts"] = texts
    payload["managed"] = svc.managed_npcs()
    svc.cancel_all(1)
    payload["cancelled"] = svc.managed_npcs()
"""
""" 在无界面子进程中执行身体管理服务各主要入口的测试脚本。 """


class ManageCase(FastTestCase):
    """身体管理服务测试的公共基类。"""

    def setUp(self) -> None:
        """创建主角与测试干员、设定查看目标、开启状态写缓冲并初始化管理表。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(NPC, "干员")
        aim(0, NPC)
        self.enterContext(working.based_on(core.state()))
        for cid in (0, NPC):
            inventory.replace_items(cid, attr_calculation.get_item_zero({}))
        svc.ensure_table(NPC)

    def rows(self, done: set[str]) -> dict[int, svc.ManageRow]:
        """
        将当前测试干员的身体管理行列表转为按管理项编号索引的字典。
        Keyword arguments:
        done -- set[str]，已完成的检查行为编号集合
        Return arguments:
        dict[int, svc.ManageRow] -- 管理项编号到管理行对象的映射
        """
        return {row.manage_id: row for row in svc.manage_rows(NPC, done)}

    @staticmethod
    def name(manage_id: int) -> str:
        """
        读取指定身体管理项去掉「被要求」字样后的展示名称。
        Keyword arguments:
        manage_id -- int，身体管理项目编号
        Return arguments:
        str -- 处理后的管理项目名称
        """
        data = game_config.config_body_manage_requirement[manage_id]
        name = game_config.config_behavior[data.second_behavior_id].name
        return name.replace("被要求", "")


class RequirementTest(ManageCase):
    """身体管理主指标、替代条件、硬性阻塞与冲突规则测试。"""

    def test_measure_text_and_threshold(self) -> None:
        """验证主指标文本拼接以及达到阈值后条件转为满足。"""
        abilities.ability(NPC)[34] = 3
        met, text = svc.requirement(CORSET, NPC)
        self.assertFalse(met)
        self.assertEqual(
            text, "露出能力等级3/4 或 攻略进度0/3 或 催眠程度0%/150%"
        )
        abilities.ability(NPC)[34] = 4
        self.assertTrue(svc.requirement(CORSET, NPC)[0])

    def test_shared_measures_read_the_same_value(self) -> None:
        """验证共用同一主指标的多项管理读取相同收藏或经验数值。"""
        player_collection.put("npc_panties", {NPC: ["p"] * 10})
        self.assertEqual(
            [svc.requirement(i, NPC) for i in (1, 5)],
            [
                (False, "内裤收藏数量10/20 或 攻略进度0/2 或 催眠程度0%/100%"),
                (True, "内裤收藏数量10/10 或 攻略进度0/1 或 催眠程度0%/50%"),
            ],
        )
        abilities.experience(NPC)[121] = 100
        self.assertTrue(svc.requirement(4, NPC)[0])
        self.assertTrue(svc.requirement(24, NPC)[0])

    def test_hypnosis_is_an_alternative(self) -> None:
        """验证催眠程度达标时可作为主指标与攻略进度的替代条件。"""
        hypnosis.set(NPC, hypnosis_degree=150)
        met, text = svc.requirement(CORSET, NPC)
        self.assertTrue(met)
        self.assertTrue(text.endswith(" 或 催眠程度150%/150%"))

    def test_virginity_and_items_block(self) -> None:
        """验证处女素质、阴茎倒模与乳夹道具等硬性前提会阻塞条件达成。"""
        hypnosis.set(NPC, hypnosis_degree=300)
        abilities.talent(NPC)[0] = 1
        met, text = svc.requirement(36, NPC)
        self.assertFalse(met)
        self.assertTrue(
            text.endswith(" 需要非处女 需要已送给对方自己的阴茎倒模")
        )
        inventory.set_item(NPC, 175, 1)
        self.assertFalse(svc.requirement(36, NPC)[0])
        abilities.talent(NPC)[1] = 1
        abilities.talent(NPC)[0] = 0
        self.assertTrue(svc.requirement(36, NPC)[0])
        met, text = svc.requirement(NIPPLE_CLAMP, NPC)
        self.assertFalse(met)
        self.assertTrue(text.endswith(" 需要持有乳夹"))
        inventory.set_item(0, 122, 1)
        self.assertTrue(svc.requirement(NIPPLE_CLAMP, NPC)[0])

    def test_conflicting_order_blocks(self) -> None:
        """验证存在互斥的已开启管理项时目标项目判定为不满足并附加提示。"""
        hypnosis.set(NPC, hypnosis_degree=300)
        self.assertTrue(svc.requirement(22, NPC)[0])
        body_manage.set(NPC, 23, 1)
        met, text = svc.requirement(22, NPC)
        self.assertFalse(met)
        self.assertTrue(text.endswith(" 需要未选择[禁止自慰]"))


class ManageRowsTest(ManageCase):
    """身体管理项目列表过滤、标签格式与调试模式测试。"""

    def test_orders_wait_for_their_check_unless_active(self) -> None:
        """验证未激活项目需先完成前置检查才显示，已激活项目始终显示并带进行中后缀。"""
        self.assertNotIn(NIPPLE_CLAMP, self.rows(set()))
        self.assertIn(NIPPLE_CLAMP, self.rows({"examine_nipple_and_areola"}))
        body_manage.set(NPC, NIPPLE_CLAMP, 1)
        row = self.rows(set())[NIPPLE_CLAMP]
        self.assertTrue(row.available)
        name = self.name(NIPPLE_CLAMP)
        self.assertEqual(row.label, f"[{row.number:02}]：{name}(进行中)")

    def test_unavailable_label_shows_the_requirement(self) -> None:
        """验证不可选管理行的序号、全角对齐名称与括号内条件说明格式。"""
        ids = list(game_config.config_body_manage_requirement)
        row = self.rows(set())[CORSET]
        self.assertFalse(row.available)
        self.assertEqual(row.number, ids.index(CORSET) + 1)
        name = self.name(CORSET).ljust(20, "　")
        need = "露出能力等级0/4 或 攻略进度0/3 或 催眠程度0%/150%"
        self.assertEqual(row.label, f"[{row.number:02}]：{name}（ {need} ）\n")

    def test_exercise_label_starts_with_the_progress(self) -> None:
        """验证无主指标的练习项目去除开头的「 或 」并从攻略进度开始显示条件。"""
        row = self.rows({"examine_sucking_and_swallowing"})[31]
        self.assertIn("（ 攻略进度0/2 或 催眠程度0%/100%", row.label)

    def test_debug_makes_every_row_available(self) -> None:
        """验证调试模式将所有可见行标为可选但不绕过前置检查过滤。"""
        self.assertFalse(all(r.available for r in self.rows(set()).values()))
        modes.set_debug(True)
        rows = self.rows(set())
        self.assertTrue(all(row.available for row in rows.values()))
        self.assertNotIn(NIPPLE_CLAMP, rows)


class TableTest(ManageCase):
    """身体管理表补齐、受管名单查询与批量取消测试。"""

    def test_missing_orders_are_added_as_off(self) -> None:
        """验证 ensure_table 保留已有开关值并将缺失的管理项编号补写为 0。"""
        ids = set(game_config.config_body_manage_requirement)
        self.assertEqual(dict(body_manage.of(NPC)), dict.fromkeys(ids, 0))
        body_manage.replace(NPC, {CORSET: 1})
        svc.ensure_table(NPC)
        expected = {**dict.fromkeys(ids, 0), CORSET: 1}
        self.assertEqual(dict(body_manage.of(NPC)), expected)

    def test_cancel_all_clears_the_managed_list(self) -> None:
        """验证 cancel_all 将管理表清零并使干员从 managed_npcs 结果中消失。"""
        self.world.chara(2, "干员乙")
        inventory.replace_items(2, attr_calculation.get_item_zero({}))
        svc.ensure_table(2)
        self.assertEqual(svc.managed_npcs(), [])
        body_manage.set(2, CORSET, 1)
        self.assertEqual(svc.managed_npcs(), [2])
        svc.cancel_all(2)
        self.assertEqual(svc.managed_npcs(), [])
        self.assertEqual(set(body_manage.of(2).values()), {0})


class ToggleTest(ManageCase):
    """身体管理开关切换与性爱练习生职业联动测试。"""

    def test_toggle_starts_and_stops_an_order(self) -> None:
        """验证 toggle 开启时赋予二段行为并置 1，再次调用时置 0 并返回对应提示。"""
        data = game_config.config_body_manage_requirement[CORSET]
        name = game_config.config_behavior[data.second_behavior_id].name
        text = svc.toggle(CORSET, NPC)
        self.assertEqual(
            text, f"\n对干员进行了{name}的身体管理，将在明天睡醒后生效。\n"
        )
        self.assertEqual(body_manage.of(NPC)[CORSET], 1)
        self.assertEqual(
            activity.second_behavior(NPC, data.second_behavior_id), 1
        )
        text = svc.toggle(CORSET, NPC)
        self.assertTrue(text.startswith(f"\n取消了对干员的{name}的身体管理"))
        self.assertEqual(body_manage.of(NPC)[CORSET], 0)

    def test_exercises_switch_the_trainee_job(self) -> None:
        """验证练习项目开启时切至性爱练习生并更新工作名单，全部关闭后恢复为 0。"""
        job = game_config.config_work_type[svc.SEX_TRAINEE].name
        self.assertIn(f"特殊职业-{job}了", svc.toggle(31, NPC))
        self.assertEqual(chara_life.work_type(NPC), svc.SEX_TRAINEE)
        self.assertEqual(work.roster(svc.SEX_TRAINEE), (NPC,))
        self.assertNotIn("特殊职业", svc.toggle(32, NPC))
        self.assertNotIn("特殊职业", svc.toggle(31, NPC))
        self.assertEqual(chara_life.work_type(NPC), svc.SEX_TRAINEE)
        self.assertIn(f"特殊职业-{job}被取消了", svc.toggle(32, NPC))
        self.assertEqual(chara_life.work_type(NPC), 0)
        self.assertEqual(work.roster(svc.SEX_TRAINEE), ())


class UiFreeRunTest(FastTestCase):
    """身体管理服务的无界面子进程隔离测试。"""

    child: ChildRun
    out: dict
    error: str

    @classmethod
    def setUpClass(cls) -> None:
        """
        通过 run_ui_free 在隔离子进程运行身体管理脚本并缓存结果。
        捕获 RuntimeError 时将错误文本存入 error 并置为空的 ChildRun。
        """
        cls.error = ""
        try:
            cls.child = run_ui_free(UI_FREE_RUN, boot=True)
        except RuntimeError as error:
            cls.error = str(error)
            cls.child = ChildRun({}, [], [])
        cls.out = cls.child.payload

    def test_no_ui_or_settle_loaded(self) -> None:
        """验证隔离子进程无错误退出，且运行期间未加载也未尝试导入受限界面或结算模块。"""
        self.assertEqual(self.error, "")
        self.assertEqual((self.child.loaded, self.child.attempted), ([], []))

    def test_manage_results(self) -> None:
        """验证隔离运行中的补表、条件判定、调试行、职业联动与批量取消结果正确。"""
        out = self.out
        count = len(game_config.config_body_manage_requirement)
        self.assertEqual(out["filled"], count)
        self.assertFalse(any(met for met, _ in out["low"]))
        high = dict(
            zip(
                game_config.config_body_manage_requirement,
                out["high"],
                strict=True,
            )
        )
        self.assertEqual(
            [i for i, (met, _) in high.items() if not met],
            [21, 22, 25, 31, 32, 33, 35, 36, 37, 38, 39],
        )
        self.assertEqual(out["debug"], [True] * len(out["debug"]))
        self.assertIn(False, out["rows"])
        self.assertEqual((out["job_on"], out["job_off"]), (svc.SEX_TRAINEE, 0))
        self.assertEqual(len(out["texts"]), 5)
        self.assertEqual((out["managed"], out["cancelled"]), ([1], []))
