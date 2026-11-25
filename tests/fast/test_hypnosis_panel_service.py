"""
催眠面板规则服务测试
====================
覆盖催眠能力与类型可用性、体控与心控指令列表、强制排卵拦截、角色扮演目录与标签、
角色扮演可选判定、缓存变更与结算写入、面板联动行为以及无界面导入边界。
"""

import json
import subprocess
import sys
from unittest import mock

from Script.Kernel import core
from Script.Modules.domains import abilities, flags, hypnosis, player_ability
from Script.Modules.domains import pregnancy
from Script.Modules.gameplay_resolution import hypnosis_panel_service as svc
from Script.Modules.gameplay_resolution import working
from Script.System.Instruct_System import handle_instruct
from Script.UI.Panel import hypnosis_panel
from tests.chara_activity import aim
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
with contextlib.redirect_stdout(io.StringIO()):
    from Script.Config import normal_config
    normal_config.init_normal_config()
    from Script.Config import game_config
    game_config.init()
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, flags, hypnosis
from Script.Modules.domains import identity
from Script.Modules.gameplay_resolution import hypnosis_panel_service as svc
from Script.Modules.gameplay_resolution import working
with working.based_on(core.state()):
    identity.put(identity.Identity(1, name="A"))
    activity.set_target(0, 1)
    for talent_id in (331, 332, 333, 334):
        abilities.talent(0)[talent_id] = int(talent_id == 331)
    for talent_id in (20, 21, 22, 23):
        abilities.talent(1)[talent_id] = 0
    hypnosis.set(1, hypnosis_degree=60)
    catalog = svc.roleplay_catalog()
    out = {
        "unlocked": [r.unlocked for r in svc.talent_rows()],
        "types": [r.type_id for r in svc.type_rows(1) if r.available],
        "body": [r.behavior_id for r in svc.control_rows(False)],
        "blocked": svc.force_ovulation_blocked(),
        "family": [o.selectable for o in svc.roleplay_options(
            catalog, catalog.type_list[0], False, [1])],
        "picked": svc.with_roleplay(catalog, [1, 31], 15),
        "names": svc.settle_roleplay(1, [1]),
        "mode": flags.get(1, "unconscious_h"),
    }
out["loaded"] = sorted(n for n in sys.modules
    if n.startswith(("Script.UI", "Script.Settle")) or is_blocked(n))
out["attempted"] = sorted(set(attempted))
print(json.dumps(out))
"""
""" 在拦截界面、结算与窗口模块的子进程中调用 hypnosis_panel_service 并输出结果与受限模块记录的脚本。 """


class HypnosisPanelCase(FastTestCase):
    """催眠面板服务测试基类，初始化玩家与目标角色、启用临时缓冲、重置玩家催眠素质并构建角色扮演目录。"""

    def setUp(self) -> None:
        """创建玩家 0（博士）与目标 1（干员甲），设定交互目标、开启临时状态缓冲并清零玩家素质 331 至 334。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "干员甲")
        aim(0, 1)
        self.enterContext(working.based_on(core.state()))
        for talent_id in (331, 332, 333, 334):
            abilities.talent(0)[talent_id] = 0
        self.catalog = svc.roleplay_catalog()

    def options(self, section: str, selected: list[int]) -> dict:
        """
        查询指定分组在给定已选列表下的角色扮演选项，并返回按编号索引的字典。
        Keyword arguments:
        section -- str，角色扮演分组名称
        selected -- list[int]，当前已选角色扮演编号列表
        Return arguments:
        dict -- 角色扮演编号到 RoleplayOption 的映射
        """
        special = section == self.catalog.special_type
        return {
            o.cid: o
            for o in svc.roleplay_options(
                self.catalog, section, special, selected
            )
        }

    def open_ids(self, section: str, selected: list[int]) -> list[int]:
        """
        返回指定分组在给定已选列表下所有可选角色扮演条目的编号列表。
        Keyword arguments:
        section -- str，角色扮演分组名称
        selected -- list[int]，当前已选角色扮演编号列表
        Return arguments:
        list[int] -- 可选角色扮演编号列表
        """
        options = self.options(section, selected).values()
        return [o.cid for o in options if o.selectable]


class HypnosisTypeTest(HypnosisPanelCase):
    """催眠能力解锁、催眠类型可用条件与面板类型写入测试。"""

    def test_talents_gate_types_without_target(self) -> None:
        """验证无目标时玩家素质 331 与 333 决定能力解锁、可用类型编号及各类型前置能力名与所需深度。"""
        abilities.talent(0)[331] = 1
        abilities.talent(0)[333] = 1
        self.assertEqual(
            [r.unlocked for r in svc.talent_rows()], [True, False, True, False]
        )
        rows = svc.type_rows(0)
        self.assertEqual([r.type_id for r in rows if r.available], [0, 1, 2])
        self.assertEqual(rows[3].talent_name, rows[4].talent_name)
        self.assertEqual([r.need_degree for r in rows], [50, 50, 100, 200, 200])

    def test_target_degree_and_birth_state_gate_types(self) -> None:
        """验证有目标时按目标催眠深度放行类型，目标持有临产或产后素质（22、23）及无效目标 -1 时全部不可用。"""
        for talent_id in (331, 332, 333, 334):
            abilities.talent(0)[talent_id] = 1
        hypnosis.set(1, hypnosis_degree=100)
        available = [r.type_id for r in svc.type_rows(1) if r.available]
        self.assertEqual(available, [0, 1, 2])
        hypnosis.set(1, hypnosis_degree=200)
        available = [r.type_id for r in svc.type_rows(1) if r.available]
        self.assertEqual(available, [0, 1, 2, 3, 4])
        for birth_talent in (22, 23):
            with self.subTest(birth_talent=birth_talent):
                abilities.talent(1)[birth_talent] = 1
                self.assertFalse(any(r.available for r in svc.type_rows(1)))
                abilities.talent(1)[birth_talent] = 0
        self.assertFalse(any(r.available for r in svc.type_rows(-1)))

    def test_panel_choice_writes_player_type(self) -> None:
        """验证面板 change_hypnosis_type(2) 写入玩家催眠类型 2 并绘制一条包含“空气”的等待确认提示。"""
        hypnosis_panel.Chose_Hypnosis_Type_Panel(80).change_hypnosis_type(2)
        self.assertEqual(player_ability.get(0, "hypnosis_type"), 2)
        self.assertEqual(len(self.world.wait_texts), 1)
        self.assertIn("空气", self.world.wait_texts[0])


class ControlTest(HypnosisPanelCase):
    """体控与心控指令列表筛选、强制排卵拦截判定及面板子指令联动测试。"""

    def test_body_and_mind_lists(self) -> None:
        """验证体控与心控指令列表分别返回预期行为编号，并核对首条体控指令的名称与子类型说明。"""
        body = svc.control_rows(False)
        self.assertEqual(
            [r.behavior_id for r in body],
            ["hypnosis_blockhead", "hypnosis_active_h"],
        )
        self.assertIn("木头人", body[0].name)
        self.assertIn("持续性效果", body[0].introduce or "")
        mind = svc.control_rows(True)
        self.assertEqual([r.behavior_id for r in mind], ["hypnosis_roleplay"])

    def test_force_ovulation_block(self) -> None:
        """验证目标处于排卵日（reproduction_period=5）或持有素质 20 至 23 时强制排卵返回拦截，常态放行。"""
        self.assertFalse(svc.force_ovulation_blocked())
        pregnancy.update(1, reproduction_period=5)
        self.assertTrue(svc.force_ovulation_blocked())
        pregnancy.update(1, reproduction_period=0)
        for pregnant_talent in (20, 21, 22, 23):
            with self.subTest(pregnant_talent=pregnant_talent):
                abilities.talent(1)[pregnant_talent] = 1
                self.assertTrue(svc.force_ovulation_blocked())
                abilities.talent(1)[pregnant_talent] = 0

    def test_blocked_ovulation_draws_notice_and_skips_settle(self) -> None:
        """验证强制排卵受阻时 son_instruct 绘制一条等待提示且跳过结算，解除拦截后调用一次通用结算。"""
        settle = mock.Mock()
        self.enterContext(
            mock.patch.object(
                handle_instruct, "chara_handle_instruct_common_settle", settle
            )
        )
        panel = hypnosis_panel.Chose_Hypnosis_Type_Panel(80, True)
        abilities.talent(1)[21] = 1
        panel.son_instruct("hypnosis_force_ovulation")
        self.assertEqual(len(self.world.wait_texts), 1)
        settle.assert_not_called()
        abilities.talent(1)[21] = 0
        panel.son_instruct("hypnosis_force_ovulation")
        settle.assert_called_once_with("hypnosis_force_ovulation")


class RoleplayCatalogTest(HypnosisPanelCase):
    """角色扮演分组顺序、成员归属与选项展示标签测试。"""

    def test_sections_and_labels(self) -> None:
        """验证分组顺序与特殊分组末尾位置、特殊成员不归入原类型，以及带前缀与无前缀选项的展示标签。"""
        self.assertEqual(
            self.catalog.sections(),
            (
                ("家庭", False),
                ("职业", False),
                ("关系", False),
                ("人外", False),
                ("场景", False),
                ("特殊", True),
            ),
        )
        self.assertEqual(self.catalog.members["特殊"], (51, 52, 105, 107, 124))
        self.assertNotIn(51, self.catalog.members["人外"])
        self.assertEqual(self.options("职业", [])[15].text, "[15](校园)教师")
        self.assertEqual(self.options("家庭", [])[1].text, "[1]妻子")
        self.assertEqual(self.options("特殊", [])[51].text, "[51]宠物猫")


class RoleplaySelectTest(HypnosisPanelCase):
    """角色扮演可选规则与面板 judge_can_select 适配测试。"""

    def test_empty_selection(self) -> None:
        """验证空选择状态下家庭、关系、人外、场景与特殊各分组的初始可选编号集合。"""
        self.assertEqual(self.open_ids("家庭", []), [1, 2, 3, 4, 5])
        self.assertEqual(self.open_ids("关系", []), [])
        self.assertEqual(self.open_ids("人外", []), [53])
        self.assertEqual(self.open_ids("场景", []), [101, 102, 103, 104])
        self.assertEqual(
            self.open_ids("特殊", []), list(self.catalog.members["特殊"])
        )

    def test_one_choice_per_type(self) -> None:
        """验证同分组仅保留已选项可选且标记 chosen，同时不影响无冲突的其他分组可选范围。"""
        options = self.options("家庭", [2])
        self.assertEqual([o.cid for o in options.values() if o.chosen], [2])
        self.assertEqual(self.open_ids("家庭", [2]), [2])
        self.assertEqual(self.open_ids("人外", [2]), [53])

    def test_job_unlocks_matching_prefix(self) -> None:
        """验证已选职业解锁同子类型前缀的关系或场景项，且教师与同学互斥、职业分组本身单选。"""
        self.assertEqual(self.open_ids("关系", [15]), [32])
        self.assertEqual(self.open_ids("关系", [11]), [32, 33])
        self.assertEqual(self.open_ids("场景", [21]), [101, 102, 103, 104, 106])
        self.assertEqual(self.open_ids("场景", [26]), [101, 102, 103, 104, 112])
        self.assertEqual(self.open_ids("职业", [26]), [26])

    def test_special_locks_everything_else(self) -> None:
        """验证已选特殊项 105 时仅其自身在特殊分组可选且 chosen 为 False，所有普通分组均不可选。"""
        self.assertEqual(self.open_ids("特殊", [105]), [105])
        self.assertFalse(self.options("特殊", [105])[105].chosen)
        for section in ("家庭", "职业", "关系", "人外", "场景"):
            with self.subTest(section=section):
                self.assertEqual(self.open_ids(section, [105]), [])

    def test_panel_judge_matches_options(self) -> None:
        """验证面板 judge_can_select 对同学与教师互斥、校园职业放行及特殊项锁定的判定结果。"""
        panel = hypnosis_panel.Chose_Roleplay_Type_Panel(80)
        self.assertFalse(
            panel.judge_can_select(33, None, {"职业": 15}, "关系", [15])
        )
        self.assertTrue(
            panel.judge_can_select(33, None, {"职业": 11}, "关系", [11])
        )
        self.assertFalse(panel.judge_can_select(1, 51, {}, "家庭", [51]))


class RoleplayChangeTest(HypnosisPanelCase):
    """角色扮演选择变更、面板缓存原地更新与结算状态写入测试。"""

    def test_with_roleplay(self) -> None:
        """验证 with_roleplay 对特殊项清空、家庭与职业项清除非锚点项及普通项直接追加的行为。"""
        self.assertEqual(svc.with_roleplay(self.catalog, [1, 15], 51), [51])
        self.assertEqual(
            svc.with_roleplay(self.catalog, [1, 101, 53, 31], 15), [1, 15]
        )
        self.assertEqual(svc.with_roleplay(self.catalog, [51], 1), [1])
        self.assertEqual(
            svc.with_roleplay(self.catalog, [1, 15], 101), [1, 15, 101]
        )
        self.assertEqual(svc.with_roleplay(self.catalog, [51], 52), [52])

    def test_panel_confirm_keeps_cache_object(self) -> None:
        """验证面板 confirm_roleplay 原地更新 selected_roleplay_cache 且保持同一列表对象。"""
        panel = hypnosis_panel.Chose_Roleplay_Type_Panel(80)
        cache = panel.selected_roleplay_cache
        panel.confirm_roleplay(1)
        panel.confirm_roleplay(101)
        panel.confirm_roleplay(15)
        self.assertIs(panel.selected_roleplay_cache, cache)
        self.assertEqual(cache, [1, 15])

    def test_settle_writes_roleplay_and_mode(self) -> None:
        """
        验证 settle_roleplay 在非空结算时写入列表、置模式 7 并清空木头人，
        在空列表结算时仅归零模式 7，保留模式 6 与木头人状态。
        """
        hypnosis.set(1, blockhead=True)
        flags.set(1, unconscious_h=6)
        self.assertEqual(svc.settle_roleplay(1, [2, 21]), ("姐姐", "护士"))
        self.assertEqual(hypnosis.roleplay(1), [2, 21])
        self.assertFalse(hypnosis.of(1)["blockhead"])
        self.assertEqual(flags.get(1, "unconscious_h"), 7)
        self.assertIsNone(svc.settle_roleplay(1, []))
        self.assertEqual(hypnosis.roleplay(1), [])
        self.assertEqual(flags.get(1, "unconscious_h"), 0)
        hypnosis.set(1, blockhead=True)
        flags.set(1, unconscious_h=6)
        self.assertIsNone(svc.settle_roleplay(1, []))
        self.assertTrue(hypnosis.of(1)["blockhead"])
        self.assertEqual(flags.get(1, "unconscious_h"), 6)

    def test_panel_settle_draws_names(self) -> None:
        """验证面板 settle_roleplay_selection 绘制以已选名称结尾的等待提示，且新面板能读回已保存列表。"""
        panel = hypnosis_panel.Chose_Roleplay_Type_Panel(80)
        panel.selected_roleplay_cache[:] = [2, 21]
        panel.settle_roleplay_selection()
        self.assertEqual(len(self.world.wait_texts), 1)
        self.assertTrue(self.world.wait_texts[0].endswith("姐姐 护士 \n"))
        self.assertEqual(
            hypnosis_panel.Chose_Roleplay_Type_Panel(
                80
            ).selected_roleplay_cache,
            [2, 21],
        )


class BackendIsolationTest(FastTestCase):
    """hypnosis_panel_service 无界面与无结算导入边界的独立子进程测试。"""

    def test_fresh_backend_process_loads_no_ui_or_settle(self) -> None:
        """
        在拦截界面、结算与窗口模块的全新子进程中调用 hypnosis_panel_service 核心接口，
        验证返回值正确且未加载或尝试导入任何受限模块。
        """
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
        self.assertEqual(out["loaded"], [])
        self.assertEqual(out["attempted"], [])
        self.assertEqual(out["unlocked"], [True, False, False, False])
        self.assertEqual(out["types"], [0, 1])
        self.assertEqual(
            out["body"], ["hypnosis_blockhead", "hypnosis_active_h"]
        )
        self.assertFalse(out["blocked"])
        self.assertEqual(out["family"], [True, False, False, False, False])
        self.assertEqual(out["picked"], [1, 15])
        self.assertEqual(out["names"], ["妻子"])
        self.assertEqual(out["mode"], 7)
