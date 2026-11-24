"""
助理服务测试
============
覆盖助理候选筛选、任免替换与每周抽签、服务档位切换与同居宿舍迁移、读档跟随状态修补，以及无界面导入与运行期隔离边界。
"""

import datetime
import json
import subprocess
import sys
from typing import Any
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import get_text, save_handle
from Script.Design import game_time, map_handle
from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.domains import activity, chara_life, flags, modes
from Script.Modules.domains import relations, visitor, work
from Script.Modules.gameplay_resolution import actions, assistant_service
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.Modules.tk_ui import callbacks
from Script.UI.Moudle import draw
from tests import chara_abilities as ca
from tests import kernel_data
from tests.chara_activity import aim
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT, banned_imports
from tests.fast.test_diplomacy_navigation_services import names_in

_ = get_text._

SERVICE_PATH = "Script/Modules/gameplay_resolution/assistant_service.py"
""" 助理服务模块的仓库相对路径。 """
SETTLE_PATH = "Script/Settle/past_day_settle.py"
""" 每日结算模块的仓库相对路径。 """
BABY_TALENT = 101
""" 用于构造离线异常角色的婴儿素质编号。 """
HOME = ["宿舍", "1区", "103"]
""" 测试同居宿舍迁移与恢复时使用的常规宿舍路径。 """
BLOCKED_RUN = """
import contextlib, importlib.abc, io, json, sys
BLOCKED = (
    "Script.UI",
    "Script.Settle",
    "Script.System.Instruct_System.handle_instruct",
    "Script.Core.flow_handle",
    "Script.Core.game_init",
    "Script.Core.io_init",
    "Script.Core.py_cmd",
    "Script.Frontend",
    "Script.Modules.tk_ui",
    "tkinter",
    "_tkinter",
    "PIL.ImageTk",
)
ALLOWED = frozenset({"Script.Modules.tk_ui", "Script.Modules.tk_ui.orders"})
ATTEMPTED = []
def blocked(name):
    return name not in ALLOWED and any(name == b or name.startswith(b + ".") for b in BLOCKED)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if blocked(fullname):
            ATTEMPTED.append(fullname)
            raise ImportError(fullname)
        return None
sys.meta_path.insert(0, Block())
with contextlib.redirect_stdout(io.StringIO()):
    import auto_build_config
from Script.Config import game_config, map_config, normal_config
normal_config.init_normal_config()
with contextlib.redirect_stdout(io.StringIO()):
    game_config.init()
    map_config.init_map_data()
from types import MappingProxyType
from Script.Design import attr_calculation, map_handle
from Script.Kernel import core
from Script.Modules.domains import abilities, chara_life, identity, relations, roster
from Script.Modules.gameplay_resolution import assistant_service as svc, working
from Script.Modules.save_load import reset
out = {"repair": svc.repair_follow_flag in reset._repairs}
core.reset_state(core.GameState(0, MappingProxyType({}), MappingProxyType({})))
home = map_handle.get_map_system_path_str_for_list(["宿舍", "1区", "103"])
with working.based_on(core.state()):
    for cid in (0, 1, 2, 3):
        identity.put(identity.Identity(cid, name=str(cid), sex=1))
        relations.assistant_services.set(cid, attr_calculation.get_assistant_services_zero())
        relations.favorability.set(cid, {0: 0})
        chara_life.dormitory.set(cid, home)
        for table in ("talent", "ability", "juel", "experience"):
            getattr(abilities, table)(cid).replace(getattr(attr_calculation, f"get_{table}_zero")({}))
        if cid:
            roster.add(cid)
    out["candidates"] = svc.get_assistant_candidates()
    svc.assistant_replace(1)
    out["appointed"] = relations.assistant_character_id(0)
    relations.favorability.set(1, {0: 10})
    relations.trust.set(1, 300)
    for cid in (2, 3, 4, 5, 6, 7, 8, 10):
        svc.cycle_service(cid)
    out["levels"] = [relations.assistant_services(1)[c] for c in (3, 4, 7, 10)]
    out["cohabit"] = chara_life.dormitory(1)
    svc.assistant_replace(2)
    out["replaced"] = [relations.assistant_character_id(0), chara_life.dormitory(1)]
    svc.assistant_replace(2)
    out["dismissed"] = relations.assistant_character_id(0)
    svc.select_random_assistant()
    out["lottery"] = relations.assistant_character_id(0)
    svc.repair_follow_flag()
out["loaded"] = sorted(filter(blocked, sys.modules))
out["attempted"] = ATTEMPTED
print(json.dumps(out, ensure_ascii=False))
"""
""" 子进程隔离脚本：在导入项目模块前屏蔽界面与结算等模块，以纯后端状态运行助理服务并输出 JSON。 """

type Drawn = tuple[str, object, object, object]
""" 记录绘制调用的四元组类型，依次为绘制类名、文本、宽度与样式。 """


def run_json(script: str) -> dict[str, Any]:
    """
    在仓库根目录用独立子进程执行 Python 脚本，退出码非零时抛出 AssertionError，否则解析末行 JSON 输出并返回。
    Keyword arguments:
    script -- str，传给 python -c 执行的脚本文本
    Return arguments:
    dict[str, Any] -- 末行标准输出解析得到的 JSON 字典
    """
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr[-2000:])
    return json.loads(result.stdout.splitlines()[-1])


def appointed(name: str) -> str:
    """构造任命指定名称干员为助理时的预期提示文本。"""
    return _("\n{0}成为助理干员了，并默认开启智能跟随模式\n").format(name)


def dismissed(name: str) -> str:
    """构造指定名称干员卸任助理时的预期提示文本。"""
    return _("\n\n{0}不再是助理干员了，已清零助理服务相关的设置\n\n").format(
        name
    )


class AssistantCase(FastTestCase):
    """助理服务测试基类，准备测试角色、内核工作集并拦截绘制调用以记录输出。"""

    def setUp(self) -> None:
        """创建测试角色、开启工作集、挂接 ui_hooks 的 Tk 回调并拦截 draw 模块绘制类的输出。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(3, "干员丙")
        self.world.chara(2, "干员乙")
        self.world.chara(1, "干员甲")
        self.enterContext(working.based_on(core.state()))
        self.drawn: list[Drawn] = []
        for cls in vars(draw).values():
            if isinstance(cls, type) and hasattr(cls, "draw"):
                self.enterContext(
                    mock.patch.object(
                        cls, "draw", autospec=True, side_effect=self.keep
                    )
                )
        self.enterContext(
            mock.patch.object(ui_hooks, "_dividers", [callbacks.draw_divider])
        )
        self.enterContext(
            mock.patch.object(ui_hooks, "_notices", [callbacks.draw_notice])
        )
        self.width = normal_config.config_normal.text_width
        self.home = map_handle.get_map_system_path_str_for_list(HOME)

    def keep(self, now: object) -> None:
        """记录单次绘制对象的类名、文本、宽度与样式到 self.drawn。"""
        self.drawn.append(
            (
                type(now).__name__,
                getattr(now, "text", None),
                getattr(now, "width", None),
                getattr(now, "style", None),
            )
        )

    def line(self) -> Drawn:
        """返回文本宽度标准样式的短横线分隔线绘制记录。"""
        return ("LineDraw", "-", self.width, "standard")

    def wait(self, text: str) -> Drawn:
        """返回文本宽度标准样式的等待提示绘制记录。"""
        return ("WaitDraw", text, self.width, "standard")

    def offline(self, cid: int) -> None:
        """将指定角色设为带婴儿素质且目标为自身以进入 7 类离线异常状态。"""
        ca.talent(cid)[BABY_TALENT] = 1
        aim(cid, cid)

    def unlock(self, cid: int, trust: int) -> None:
        """为指定角色设置对玩家好感度与信赖度以配合服务解锁测试。"""
        relations.favorability.set(cid, {0: 10})
        relations.trust.set(cid, trust)

    def services(self, cid: int) -> dict[int, int]:
        """返回指定角色当前助理服务映射的浅拷贝字典。"""
        return dict(relations.assistant_services(cid))


class CandidatesTest(AssistantCase):
    """助理候选列表筛选规则测试。"""

    def test_candidates_skip_player_offline_warden_and_visitor(self) -> None:
        """验证候选列表按角色编号升序返回，并跳过玩家 0、离线角色、监狱长与访客。"""
        self.world.chara(4, "访客")
        self.world.chara(5, "婴儿")
        self.offline(5)
        work.set_warden(2)
        visitor.arrive(4, game_time.now() + datetime.timedelta(days=1))
        self.assertEqual(assistant_service.get_assistant_candidates(), [1, 3])


class ReplaceTest(AssistantCase):
    """助理任命、解任、拒绝、替换与每周抽签行为测试。"""

    def test_appoint_without_assistant(self) -> None:
        """验证当前无助理时任命新助理会设置助理编号、跟随状态、服务 2、二段行为并绘制分隔线与任命提示。"""
        assistant_service.assistant_replace(1)
        self.assertEqual(relations.assistant_character_id(0), 1)
        self.assertEqual(flags.get(1, "is_follow"), 1)
        self.assertEqual(self.services(1)[2], 1)
        self.assertEqual(activity.second_behavior(1, "chosen_as_assistant"), 1)
        self.assertEqual(
            self.drawn, [self.line(), self.wait(appointed("干员甲"))]
        )

    def test_choosing_current_assistant_dismisses_her(self) -> None:
        """验证再次选择当前助理会解除职务、清零跟随与服务、更新二段行为并绘制解任提示。"""
        assistant_service.assistant_replace(1)
        relations.assistant_services.set_item(1, 5, 2)
        self.drawn.clear()
        assistant_service.assistant_replace(1)
        self.assertEqual(relations.assistant_character_id(0), 0)
        self.assertEqual(flags.get(1, "is_follow"), 0)
        self.assertEqual(set(self.services(1).values()), {0})
        self.assertEqual(activity.second_behavior(1, "chosen_as_assistant"), 0)
        self.assertEqual(activity.second_behavior(1, "not_as_assistant"), 1)
        self.assertEqual(
            self.drawn, [self.line(), self.wait(dismissed("干员甲"))]
        )

    def test_offline_character_is_not_appointed(self) -> None:
        """验证任命处于离线异常状态的角色会被拒绝、保留原助理编号并绘制拒绝提示。"""
        assistant_service.assistant_replace(1)
        self.offline(2)
        self.drawn.clear()
        assistant_service.assistant_replace(2)
        self.assertEqual(relations.assistant_character_id(0), 1)
        self.assertEqual(flags.get(2, "is_follow"), 0)
        refused = _("\n{0}的状态异常，无法任命为助理干员\n").format("干员乙")
        self.assertEqual(self.drawn, [self.line(), self.wait(refused)])

    def test_replace_moves_old_assistant_out_of_cohabitation(self) -> None:
        """验证替换同居中的旧助理会将其迁回原宿舍、清零跟随与服务并合并绘制任命与解任提示。"""
        assistant_service.assistant_replace(1)
        self.unlock(1, 200)
        chara_life.dormitory.set(1, self.home)
        assistant_service.cycle_service(7)
        self.drawn.clear()
        assistant_service.assistant_replace(3)
        self.assertEqual(relations.assistant_character_id(0), 3)
        self.assertEqual(flags.get(1, "is_follow"), 0)
        self.assertEqual(flags.get(3, "is_follow"), 1)
        self.assertEqual(chara_life.dormitory(1), self.home)
        self.assertEqual(set(self.services(1).values()), {0})
        self.assertEqual(activity.second_behavior(1, "not_as_assistant"), 1)
        self.assertEqual(
            self.drawn,
            [
                self.line(),
                self.wait(appointed("干员丙") + dismissed("干员甲")),
            ],
        )

    def test_weekly_lottery_appoints_a_candidate(self) -> None:
        """验证每周抽签会选中一名候选干员并依次绘制抽签提示、分隔线与任命提示。"""
        assistant_service.select_random_assistant()
        chosen = relations.assistant_character_id(0)
        self.assertIn(chosen, [1, 2, 3])
        name = {1: "干员甲", 2: "干员乙", 3: "干员丙"}[chosen]
        lottery = _("\n○本周抽签选中了{0}作为{1}的助理\n").format(name, "博士")
        self.assertEqual(
            self.drawn,
            [self.wait(lottery), self.line(), self.wait(appointed(name))],
        )


class CycleServiceTest(AssistantCase):
    """助理服务选项切换、解锁校验、二段行为与同居宿舍迁移测试。"""

    def setUp(self) -> None:
        """任命 1 号干员为当前助理并清空初始化阶段的绘制记录。"""
        super().setUp()
        assistant_service.assistant_replace(1)
        self.drawn.clear()

    def test_follow_service_toggles_and_steps_follow_state(self) -> None:
        """验证连续切换跟随服务会交替翻转开关并按预期步进与归零跟随状态。"""
        flags.set(1, is_follow=3)
        seen = []
        for _round in range(5):
            assistant_service.cycle_service(2)
            seen.append((bool(self.services(1)[2]), flags.get(1, "is_follow")))
        self.assertEqual(
            seen, [(False, 4), (True, 5), (False, 0), (True, 1), (False, 0)]
        )

    def test_locked_option_shows_reason_and_resets(self) -> None:
        """验证未满足解锁条件时以默认宽度绘制失败原因、将服务归零且不触发开启二段行为。"""
        relations.assistant_services.set_item(1, 3, 0)
        assistant_service.cycle_service(3)
        option = game_config.config_assistant_services_option[3][0][1]
        reason = _("需要:") + _("信赖度>={0}").format(50)
        reason += _("或催眠进度>={0}").format(25.0)
        text = _("\n  ○更改失败，[{0}]{1}\n").format(option, reason + "  ")
        self.assertEqual(self.services(1)[3], 0)
        self.assertEqual(
            self.drawn,
            [("WaitDraw", text, draw.WaitDraw().width, "standard")],
        )
        self.assertEqual(activity.second_behavior(1, "support_service_on"), 0)

    def test_debug_mode_skips_unlock_check(self) -> None:
        """验证调试模式下跳过解锁校验、直接开启服务并设置对应开启二段行为。"""
        modes.set_debug(True)
        assistant_service.cycle_service(3)
        self.assertEqual(self.services(1)[3], 1)
        self.assertEqual(activity.second_behavior(1, "support_service_on"), 1)
        self.assertEqual(activity.second_behavior(1, "support_service_off"), 0)
        self.assertEqual(self.drawn, [])

    def test_option_service_marks_only_current_option(self) -> None:
        """验证多档位服务受解锁条件约束、越过末档后归零，且同组二段行为仅保留当前档位标记。"""
        self.unlock(1, 100)
        food = [
            activity.second_behavior(1, f"assistant_send_food_{i}")
            for i in range(4)
        ]
        self.assertEqual(food, [0, 0, 0, 0])
        levels = []
        for _round in range(3):
            assistant_service.cycle_service(4)
            levels.append(self.services(1)[4])
        self.assertEqual(levels, [1, 2, 0])
        self.assertEqual(len(self.drawn), 1)
        relations.trust.set(1, 300)
        for _round in range(4):
            assistant_service.cycle_service(4)
        self.assertEqual(self.services(1)[4], 0)
        food = [
            activity.second_behavior(1, f"assistant_send_food_{i}")
            for i in range(4)
        ]
        self.assertEqual(food, [1, 0, 0, 0])

    def test_cohabitation_moves_dormitory_and_back(self) -> None:
        """验证开启同居服务会登记常住宿舍并迁入同居房间，关闭后迁回原宿舍并切换同居二段行为。"""
        self.unlock(1, 200)
        chara_life.dormitory.set(1, self.home)
        room = map_handle.get_map_system_path_str_for_list(
            assistant_service.COHABIT_ROOM
        )
        assistant_service.cycle_service(7)
        self.assertEqual(chara_life.dormitory(1), room)
        self.assertEqual(chara_life.permanent_dormitory(1), self.home)
        self.assertEqual(activity.second_behavior(1, "cohabitation_on"), 1)
        assistant_service.cycle_service(7)
        self.assertEqual(self.services(1)[7], 0)
        self.assertEqual(chara_life.dormitory(1), self.home)
        self.assertEqual(activity.second_behavior(1, "cohabitation_on"), 0)
        self.assertEqual(activity.second_behavior(1, "cohabitation_off"), 1)

    def test_weekly_rotation_sets_no_second_behavior(self) -> None:
        """验证开启每周轮换服务会更新服务档位且不改动角色二段行为表。"""
        self.unlock(1, 0)
        before = dict(activity.second_behaviors(1))
        assistant_service.cycle_service(10)
        self.assertEqual(self.services(1)[10], 1)
        self.assertEqual(dict(activity.second_behaviors(1)), before)


class RepairFollowFlagTest(FastTestCase):
    """读档跟随状态修补钩子测试。"""

    def test_load_resets_follow_state_above_four(self) -> None:
        """验证读档流程触发修补钩子后，大于 4 的跟随状态会归零，等于 4 的保持不变。"""
        self.world.chara(0, "博士")
        self.world.chara(1, "干员甲")
        self.world.chara(2, "干员乙")
        kernel_data.put(flags.set, 1, is_follow=7)
        kernel_data.put(flags.set, 2, is_follow=4)
        for module, name in (
            (save_handle, "install_save"),
            (save_handle, "exact_stats"),
            (save_handle, "repair_installed"),
        ):
            self.enterContext(mock.patch.object(module, name))
        self.enterContext(
            mock.patch.object(actions, "project", side_effect=lambda new: new)
        )
        core.load(load_order.LOAD_ORDER)
        core.reset_state(core.state(), {"cause": "load", "save": "1"})
        self.assertEqual(flags.get(1, "is_follow"), 0)
        self.assertEqual(flags.get(2, "is_follow"), 4)


class ImportBoundaryTest(FastTestCase):
    """助理服务无界面导入边界与每日结算调用方导入约束测试。"""

    def test_service_is_ui_free_and_settle_uses_it(self) -> None:
        """验证助理服务无禁用界面导入，且每日结算模块导入助理服务而非助理面板。"""
        self.assertEqual(
            banned_imports((ROOT / SERVICE_PATH).read_bytes(), SERVICE_PATH),
            [],
        )
        names = names_in(
            (ROOT / SETTLE_PATH).read_text(encoding="utf-8"), "Script.Settle"
        )
        self.assertIn(assistant_service.__name__, names)
        self.assertNotIn("Script.UI.Panel.assistant_panel", names)

    def test_service_runs_without_ui_or_settle_in_subprocess(self) -> None:
        """
        验证 BLOCKED_RUN 在子进程导入期登记跟随修补，并产出预期的候选列表、1 号任命、
        服务 3/4/7/10 的 1 级档位、1 号迁入并离开同居房间、2 号替换、解任无助理及抽签结果。
        同时验证该子进程全程未尝试导入被屏蔽模块，退出时在 sys.modules 中也不含被屏蔽模块。
        """
        out = run_json(BLOCKED_RUN)
        room = map_handle.get_map_system_path_str_for_list(
            assistant_service.COHABIT_ROOM
        )
        self.assertIn(out.pop("lottery"), (1, 2, 3))
        self.assertNotEqual(out["replaced"][1], room)
        out["replaced"] = out["replaced"][0]
        self.assertEqual(
            out,
            {
                "repair": True,
                "candidates": [1, 2, 3],
                "appointed": 1,
                "levels": [1, 1, 1, 1],
                "cohabit": room,
                "replaced": 2,
                "dismissed": 0,
                "loaded": [],
                "attempted": [],
            },
        )
