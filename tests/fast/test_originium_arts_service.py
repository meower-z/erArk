"""
源石技艺与负面刻印服务的快速测试。
覆盖默认催眠类型读写、升级消耗与免费条件解锁、内裤重复款式优先扣减、
负面刻印降低结算、面板委托，以及两项源石技艺服务的纯后端子进程导入边界。
"""

import json
import subprocess
import sys
from unittest import mock

from Script.Config import game_config
from Script.Kernel import core
from Script.Modules.domains import abilities, dirty, hypnosis, modes
from Script.Modules.domains import player_ability, player_collection
from Script.Modules.domains import relations, status, warehouse
from Script.Modules.gameplay_resolution import originium_arts_service as svc
from Script.Modules.gameplay_resolution import working
from Script.UI.Moudle import draw
from Script.UI.Panel import originium_arts
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

BACKEND_RUN = """
import importlib.abc, sys
BLOCKED = ("Script.UI", "Script.Settle",
    "Script.System.Instruct_System.handle_instruct", "Script.Core.flow_handle",
    "Script.Core.io_init", "Script.Frontend", "Script.Modules.tk_ui",
    "tkinter", "_tkinter", "PIL.ImageTk")
ALLOWED = frozenset({"Script.Modules.tk_ui", "Script.Modules.tk_ui.orders"})
attempted = []
def is_blocked(name):
    if name in ALLOWED:
        return False
    return any(name == root or name.startswith(root + ".") for root in BLOCKED)
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if is_blocked(fullname):
            attempted.append(fullname)
            raise ImportError(fullname)
        return None
sys.meta_path.insert(0, Blocker())
import contextlib, io, json
from Script.Config import normal_config
with contextlib.redirect_stdout(io.StringIO()):
    normal_config.init_normal_config()
from Script.Config import game_config
with contextlib.redirect_stdout(io.StringIO()):
    game_config.init()
from Script.Kernel import core
from Script.Modules.domains import abilities, modes
from Script.Modules.gameplay_resolution import originium_arts_panel_service
from Script.Modules.gameplay_resolution import originium_arts_service
from Script.Modules.gameplay_resolution import working
with working.based_on(core.state()):
    for talent_id in (304, 305, 306, 307, 308, 309, 310, 311, 312,
            316, 317, 318, 331, 332, 333, 334):
        abilities.talent(0)[talent_id] = 0
    for talent_id in (316, 318, 305, 307, 309):
        abilities.talent(0)[talent_id] = 1
    modes.set_debug(True)
    out = {
        "menu": [[e.key, e.talent_names, e.sanity_per_hour]
            for e in originium_arts_panel_service.menu_entries()],
        "rows": [[r.talent_id, r.unlocked]
            for r in originium_arts_panel_service.group_rows(6)],
        "cost": originium_arts_service.calculate_art_cost(3),
        "panties": originium_arts_service.consume_panties_duplicate_first(
            ["a", "b", "a", "c", "b", "d", "e"]),
    }
out["attempted"] = attempted
out["loaded"] = sorted(n for n in sys.modules
    if n.startswith(("Script.UI", "Script.Settle")) or is_blocked(n))
print(json.dumps(out))
"""
"""在拦截界面、结算与窗口模块的独立子进程中初始化配置并运行两项源石技艺服务的测试脚本。"""


BLOCKED_IMPORT_RUN = """
import importlib.abc, sys
BLOCKED = ("Script.UI", "Script.Core.flow_handle", "Script.Core.io_init",
    "Script.Modules.tk_ui", "tkinter", "_tkinter")
def is_blocked(name):
    return any(name == root or name.startswith(root + ".") for root in BLOCKED)
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if is_blocked(fullname):
            raise ImportError(fullname)
sys.meta_path.insert(0, Blocker())
from Script.Modules.gameplay_resolution import originium_arts_service as svc
print(svc.calculate_art_cost(3))
print(svc.consume_panties_duplicate_first(["a", "b", "a", "c", "b", "d", "e"]))
print(sorted(name for name in sys.modules if is_blocked(name)))
"""
""" 在拦截界面与窗口模块的子进程中导入并调用源石技艺服务的脚本。 """


def talent_name(talent_id: int) -> str:
    """
    按素质编号读取配置表中的素质名称。
    Keyword arguments:
    talent_id -- int，素质配置编号
    Return arguments:
    str -- 配置表中的素质名称
    """
    return game_config.config_talent[talent_id].name


class OriginiumArtsCase(FastTestCase):
    """源石技艺服务测试基类，初始化玩家与两名在编干员并打开工作集。"""

    def setUp(self) -> None:
        """重置测试世界，创建玩家与干员 1、2 并进入工作集上下文。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "干员甲")
        self.world.chara(2, "干员乙")
        self.enterContext(working.based_on(core.state()))


class HypnosisTypeTest(OriginiumArtsCase):
    """默认催眠类型读写服务的测试。"""

    def test_set_and_get_hypnosis_type(self) -> None:
        """设置默认催眠类型会更新玩家能力表并可通过查询函数读回。"""
        self.assertEqual(svc.get_hypnosis_type(), 0)
        for value in (2, 4, 0):
            svc.set_hypnosis_type(value)
            self.assertEqual(player_ability.get(0, "hypnosis_type"), value)
            self.assertEqual(svc.get_hypnosis_type(), value)


class OriginiumArtsUpgradeTest(OriginiumArtsCase):
    """源石技艺消耗、学习升级结算与解锁条件评估的测试。"""

    def test_calculate_art_cost(self) -> None:
        """各等级源石技艺消耗按 10 ** (level - 1) 计算。"""
        for level, cost in ((1, 1), (2, 10), (3, 100), (4, 1000)):
            with self.subTest(level=level):
                self.assertEqual(svc.calculate_art_cost(level), cost)

    def test_learn_or_upgrade_art_cost_and_free_unlock(self) -> None:
        """验证至纯源石不足、正常扣费学习与免费条件解锁三种结算路径。"""
        warehouse.set(3, 5)
        self.assertEqual(
            svc.learn_or_upgrade_art(2),
            svc.LearnArtResult(False, 2, 305, 10, 0, True),
        )
        self.assertEqual(
            (warehouse.amount(3), abilities.talent(0)[305]), (5, 0)
        )

        warehouse.set(3, 25)
        self.assertEqual(
            svc.learn_or_upgrade_art(2),
            svc.LearnArtResult(True, 2, 305, 10, 10, False),
        )
        self.assertEqual(
            (warehouse.amount(3), abilities.talent(0)[305]), (15, 1)
        )

        warehouse.set(3, 0)
        self.assertEqual(
            svc.learn_or_upgrade_art(3, no_cost_flag=True),
            svc.LearnArtResult(True, 3, 306, 100, 0, False),
        )
        self.assertEqual(
            (warehouse.amount(3), abilities.talent(0)[306]), (0, 1)
        )

    def test_list_upgradeable_arts_respects_owned_and_prereq(self) -> None:
        """列表仅返回未持有且前置素质已满足的源石技艺，并正确标记未实装项。"""
        warehouse.set(3, 1)
        options = {o.talent_id: o for o in svc.list_upgradeable_arts()}
        self.assertEqual(set(options), {304, 307, 310, 331, 316})
        self.assertTrue(options[304].can_buy_with_prime)
        self.assertFalse(options[304].todo)
        self.assertTrue(options[310].todo)
        self.assertIsNone(options[310].condition)

        abilities.talent(0)[304] = 1
        next_opts = {o.talent_id: o for o in svc.list_upgradeable_arts()}
        self.assertNotIn(304, next_opts)
        self.assertIn(305, next_opts)
        self.assertEqual(next_opts[305].money_cost, 10)
        self.assertFalse(next_opts[305].can_buy_with_prime)

    def test_evaluate_unlock_conditions(self) -> None:
        """覆盖激素、视觉、时停与催眠全部特殊解锁条件的统计与判定。"""
        relations.favorability.set(1, {0: 1200})
        relations.trust.set(1, 150)
        c304 = svc.evaluate_art_unlock_condition(1)
        assert c304 is not None
        self.assertEqual(
            (
                c304.kind,
                c304.current_primary,
                c304.current_secondary,
                c304.satisfied,
            ),
            ("max_favorability_trust", 1200, 150, True),
        )

        abilities.talent(1)[201] = 1
        abilities.talent(2)[214] = 1
        relations.favorability.set(2, {0: 9000})
        c305 = svc.evaluate_art_unlock_condition(2)
        c306 = svc.evaluate_art_unlock_condition(3)
        assert c305 is not None and c306 is not None
        self.assertEqual(
            (c305.current_primary, c305.current_secondary, c305.satisfied),
            (10200, 2, False),
        )
        self.assertEqual(
            (c306.current_primary, c306.current_secondary, c306.satisfied),
            (10200, 1, False),
        )

        player_collection.set_list_map_entry("npc_panties", 1, ["p"] * 12)
        player_collection.set_list_map_entry("npc_panties", 2, ["q"] * 8)
        c307 = svc.evaluate_art_unlock_condition(4)
        assert c307 is not None
        self.assertEqual((c307.current_primary, c307.satisfied), (20, True))

        with dirty.editing(1) as d:
            d.body_semen[6][3] = 2000
            d.body_semen[8][3] = 1000
            d.body_semen[1][3] = 999
        abilities.experience(1)[20] = 60
        abilities.experience(2)[20] = 40
        c308 = svc.evaluate_art_unlock_condition(5)
        assert c308 is not None
        self.assertEqual(
            (c308.current_primary, c308.current_secondary, c308.satisfied),
            (3000, 100, True),
        )

        relations.child_id_list.set(0, [99])
        c309 = svc.evaluate_art_unlock_condition(6)
        assert c309 is not None
        self.assertEqual((c309.current_primary, c309.satisfied), (1, True))

        abilities.experience(1)[79] = 50
        abilities.experience(2)[78] = 12
        c316 = svc.evaluate_art_unlock_condition(14)
        assert c316 is not None
        self.assertEqual(
            (c316.current_primary, c316.current_secondary, c316.satisfied),
            (50, 12, True),
        )

        abilities.experience(0)[124] = 200
        abilities.experience(1)[78] = 38
        c317 = svc.evaluate_art_unlock_condition(15)
        assert c317 is not None
        self.assertEqual(
            (c317.current_primary, c317.current_secondary, c317.satisfied),
            (200, 50, True),
        )

        abilities.experience(0)[120] = 50
        c331 = svc.evaluate_art_unlock_condition(10)
        assert c331 is not None
        self.assertEqual((c331.current_primary, c331.satisfied), (50, True))

        abilities.experience(0)[122] = 10
        hypnosis.set(1, hypnosis_degree=120.7)
        hypnosis.set(2, hypnosis_degree=80.2)
        c332 = svc.evaluate_art_unlock_condition(11)
        assert c332 is not None
        self.assertEqual(
            (
                c332.kind,
                c332.current_primary,
                c332.current_secondary,
                c332.satisfied,
            ),
            ("hypnosis_exp_degree", 10, 200, True),
        )


class NegativeMarkReductionTest(OriginiumArtsCase):
    """内裤重复款式优先扣减与负面刻印降低结算的测试。"""

    def test_consume_panties_duplicate_first_cases(self) -> None:
        """覆盖不足 5 条、全唯一、混合重复与重复数达 5 条及以上四类情形，且不修改原列表。"""
        short = ["a", "a", "b", "b"]
        self.assertIsNone(svc.consume_panties_duplicate_first(short))
        self.assertEqual(short, ["a", "a", "b", "b"])

        unique = ["a", "b", "c", "d", "e", "f"]
        self.assertEqual(svc.consume_panties_duplicate_first(unique), ["f"])
        self.assertEqual(unique, ["a", "b", "c", "d", "e", "f"])

        mixed = ["a", "b", "a", "c", "b", "d", "e"]
        self.assertEqual(svc.consume_panties_duplicate_first(mixed), ["d", "e"])

        many_dups = ["a", "a", "a", "a", "b", "b", "b", "b", "c"]
        self.assertEqual(
            svc.consume_panties_duplicate_first(many_dups),
            ["a", "b", "b", "c"],
        )

    def test_list_negative_mark_queries(self) -> None:
        """验证持有负面刻印角色筛选、刻印等级查询与内裤数量读取。"""
        abilities.ability(1)[15] = 2
        abilities.ability(1)[18] = 1
        player_collection.set_list_map_entry("npc_panties", 1, ["a", "b", "c"])
        self.assertEqual(svc.list_negative_mark_characters(), [1])
        self.assertEqual(
            svc.list_character_negative_marks(1), [(15, 2), (18, 1)]
        )
        self.assertEqual(svc.get_npc_panties_count(1), 3)

    def test_reduce_negative_mark_normal_debug_and_status_reset(self) -> None:
        """验证内裤不足、正常扣减并清零对应主状态、非映射能力与 debug 模式跳过消耗。"""
        abilities.ability(1)[15] = 2
        status.set(1, 17, 500)
        player_collection.set_list_map_entry("npc_panties", 1, ["a", "b", "c"])
        self.assertEqual(
            svc.reduce_negative_mark(1, 15),
            svc.NegativeMarkReductionResult(False, 1, 15, 0, 3, 2, None),
        )
        self.assertEqual((abilities.ability(1)[15], status.of(1)[17]), (2, 500))

        for ability_id, status_id in ((15, 17), (17, 18), (18, 20)):
            with self.subTest(ability_id=ability_id, status_id=status_id):
                abilities.ability(1)[ability_id] = 3
                status.set(1, status_id, 420)
                player_collection.set_list_map_entry(
                    "npc_panties", 1, ["a", "b", "a", "c", "b", "d", "e"]
                )
                self.assertEqual(
                    svc.reduce_negative_mark(1, ability_id),
                    svc.NegativeMarkReductionResult(
                        True, 1, ability_id, 5, 2, 2, status_id
                    ),
                )
                self.assertEqual(abilities.ability(1)[ability_id], 2)
                self.assertEqual(status.of(1)[status_id], 0)
                self.assertEqual(
                    player_collection.get("npc_panties")[1], ["d", "e"]
                )

        abilities.ability(1)[14] = 2
        for sid, val in ((17, 77), (18, 88), (20, 99)):
            status.set(1, sid, val)
        player_collection.set_list_map_entry("npc_panties", 1, ["x"] * 5)
        other = svc.reduce_negative_mark(1, 14)
        self.assertTrue(other.success)
        self.assertIsNone(other.reset_status_id)
        self.assertEqual(abilities.ability(1)[14], 1)
        self.assertEqual(
            (status.of(1)[17], status.of(1)[18], status.of(1)[20]),
            (77, 88, 99),
        )

        modes.set_debug(True)
        abilities.ability(2)[17] = 1
        status.set(2, 18, 300)
        player_collection.set_list_map_entry("npc_panties", 2, ["only_one"])
        self.assertEqual(
            svc.reduce_negative_mark(2, 17),
            svc.NegativeMarkReductionResult(True, 2, 17, 0, 1, 0, 18),
        )
        self.assertEqual(player_collection.get("npc_panties")[2], ["only_one"])
        self.assertEqual((abilities.ability(2)[17], status.of(2)[18]), (0, 0))


class OriginiumArtsPanelDelegationTest(OriginiumArtsCase):
    """面板方法向源石技艺与负面刻印服务委托并保持提示文案一致的测试。"""

    def test_panel_delegates_hypnosis_and_learn_art(self) -> None:
        """验证面板切换催眠类型及学习源石技艺的委托与等待提示输出。"""
        panel = originium_arts.Originium_Arts_Panel(80)
        with mock.patch.object(
            svc, "set_hypnosis_type", wraps=svc.set_hypnosis_type
        ) as set_type:
            panel.change_hypnosis_type(3)
        set_type.assert_called_once_with(3, character_id=0)
        self.assertEqual(player_ability.get(0, "hypnosis_type"), 3)

        shown: list[str] = []
        warehouse.set(3, 0)
        with (
            mock.patch.object(
                svc, "learn_or_upgrade_art", wraps=svc.learn_or_upgrade_art
            ) as learn,
            mock.patch.object(
                draw.WaitDraw, "draw", lambda inst: shown.append(inst.text)
            ),
        ):
            panel.gain_and_upgrade_ability_which(1, no_cost_flag=False)
            self.assertEqual(shown, [])
            panel.gain_and_upgrade_ability_which(1, no_cost_flag=True)

        self.assertEqual(
            learn.call_args_list,
            [
                mock.call(1, no_cost_flag=False),
                mock.call(1, no_cost_flag=True),
            ],
        )
        expected_name = game_config.config_talent[304].name
        self.assertEqual(shown, [f"\n习得了{expected_name}\n"])

    def test_down_negative_talent_panel_delegates_settle_down(self) -> None:
        """验证降低负面素质面板委托服务结算并输出对应不足提示与成功提示。"""
        panel = originium_arts.Down_Negative_Talent_Panel(80)
        panel.chara_id = 1
        abilities.ability(1)[15] = 2
        status.set(1, 17, 120)
        player_collection.set_list_map_entry("npc_panties", 1, ["a", "b"])
        texts: list[str] = []

        with (
            mock.patch.object(
                svc, "reduce_negative_mark", wraps=svc.reduce_negative_mark
            ) as reduce_fn,
            mock.patch.object(
                draw.NormalDraw, "draw", lambda inst: texts.append(inst.text)
            ),
            mock.patch.object(draw.LineDraw, "draw"),
        ):
            panel.settle_down(15)
            player_collection.set_list_map_entry(
                "npc_panties", 1, ["a", "a", "b", "b", "c", "d"]
            )
            panel.settle_down(15)

        self.assertEqual(
            reduce_fn.call_args_list, [mock.call(1, 15), mock.call(1, 15)]
        )
        self.assertEqual(texts[0], "  内裤数量不足\n")
        ability_name = game_config.config_ability[15].name
        self.assertIn("5条内裤化为一缕青烟", texts[1])
        self.assertIn(f"{ability_name}下降到了1级", texts[1])


class ImportBoundaryTest(FastTestCase):
    """源石技艺服务与面板菜单规则服务的界面与结算导入边界测试。"""

    def test_fresh_backend_process_loads_no_ui_or_settle(self) -> None:
        """断言独立子进程在拦截界面、结算与窗口模块时可正常运行两项服务且零受限模块加载。"""
        result = subprocess.run(
            [sys.executable, "-c", BACKEND_RUN],
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
        self.assertEqual(
            out["menu"],
            [
                [1, "", None],
                [2, f"{talent_name(316)} + {talent_name(318)}", None],
                [4, "", None],
                [5, f" + {talent_name(305)}", None],
                [6, f"{talent_name(307)} + {talent_name(309)}", 10],
                [11, "", None],
                [12, "", None],
            ],
        )
        self.assertEqual(out["rows"], [[307, True], [308, False], [309, True]])
        self.assertEqual(out["cost"], 100)
        self.assertEqual(out["panties"], ["d", "e"])

    def test_fresh_subprocess_import_loads_no_ui(self) -> None:
        """独立子进程拦截界面与窗口模块时可导入并执行服务，且未加载被拦截模块。"""
        result = subprocess.run(
            [sys.executable, "-c", BLOCKED_IMPORT_RUN],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertEqual(
            result.stdout.splitlines()[-3:],
            ["100", "['d', 'e']", "[]"],
        )
