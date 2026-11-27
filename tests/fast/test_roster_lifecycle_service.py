"""
干员在编生命周期服务测试
========================
覆盖子进程无界面导入与运行隔离、离线与上线状态转换、导航与越狱调用路径，以及结算效果委托等价性。
"""

from collections.abc import Callable
import importlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any
from unittest import mock

from Script.Config import game_config
from Script.Core import constant, constant_effect, game_type
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import activity, diplomacy, dirty, flags, h_state
from Script.Modules.domains import location, needs, prison, relations, roster
from Script.Modules.domains import status
from Script.Modules.gameplay_resolution import achievement_service
from Script.Modules.gameplay_resolution import navigation_service, plan_queue
from Script.Modules.gameplay_resolution import prison_service, ui_hooks
from Script.Modules.gameplay_resolution import roster_lifecycle_service as svc
from Script.System.Field_Commission_System import field_commission_function
from tests import kernel_data
from tests.fast.base import FastTestCase

ASSISTANT, PRISONER, DIPLOMAT, ENVOY = 1, 2, 3, 4
""" 四个测试用干员角色编号：助理、囚犯、离任外交官与到任外交官。 """
AEGIR = 1
""" 出生地编号 1 对应的目标国家（阿戈尔）。 """
GATE = ["中枢", "博士房间"]
""" 上线前写入 move_target 的测试场景路径，用于核对合并行动时保留移动目标。 """
FEEL_STATES = tuple(
    sid
    for sid, state in game_config.config_character_state.items()
    if state.type == 0
)
""" 配置中类型为 0 的全部角色状态编号元组。 """
NEEDS = ("hit", "mana", "hunger", "tired", "urine", "sleep")
""" 角色上线时重置的六项基础需求字段名元组。 """
FX = constant_effect.BehaviorEffect
""" 行为结算效果枚举类引用。 """
OFF_LINE = {
    "roster": False,
    "position": ["0", "0"],
    "assistant": [0, [0]],
    "flags": [0, True, False, 0],
    "cleared": [[0], 0, 0],
    "behavior": [constant.Behavior.SHARE_BLANKLY, 0, False],
    "move_target": [],
    "event": ["", False],
}
""" 角色离线后各观测字段的预期快照，含行动与事件重置为默认值。 """
ON_LINE = {
    "roster": True,
    "needs": [100, 100, 0, 0, 0, 0],
    "flags": [0, True, False, AEGIR],
    "behavior": [constant.Behavior.SHARE_BLANKLY, 0, True],
    "move_target": GATE,
    "state": constant.CharacterStatus.STATUS_ARDER,
    "target": ASSISTANT,
}
""" 角色上线后各观测字段的预期快照。 """
BLOCKED_RUN = """
import importlib.abc, json, sys
BLOCKED = {roots!r}
def is_blocked(name):
    return any(
        name == root or name.startswith(root + ".") for root in BLOCKED)
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if is_blocked(fullname):
            raise ImportError(fullname)
sys.meta_path.insert(0, Blocker())
{body}
print(json.dumps([{result}, sorted(n for n in sys.modules if is_blocked(n))]))
"""
""" 在独立子进程拦截指定模块前缀并输出结果与命中列表的脚本模板。 """
BLOCKED = tuple(
    "Script.UI Script.Settle Script.System.Instruct_System.handle_instruct"
    " Script.Core.flow_handle Script.Core.io_init Script.Core.game_init"
    " Script.Frontend Script.Modules.tk_ui tkinter _tkinter PIL.ImageTk".split()
)
""" 子进程导入与运行测试共用的界面、结算包、流程初始化、前端与 Tk 拦截模块前缀元组。 """
UI_FREE_BOOT = """
from tests import kernel_data, world
loaded = world.MinimalWorld.__new__(world.MinimalWorld)
loaded._boot(); loaded._snapshot()
loaded.reset = lambda: (
    kernel_data.reset_clock(world.start_time(), loaded._data), world.seed_everything())
world.MinimalWorld._loaded = loaded
from tests.fast import test_roster_lifecycle_service as case
"""
""" 跳过界面绘制静默的无界面测试世界初始化脚本，用于运行期全量拦截子进程。 """
SERVICES = "roster_lifecycle_service, navigation_service, prison_service"
""" 导入隔离测试加载的三个无界面后端服务名列表。 """


def fresh_world() -> None:
    """重置测试世界并创建博士及四名测试干员。"""
    FastTestCase().setUp()
    world = FastTestCase.world
    world.chara(0, "博士")
    for cid in (ASSISTANT, PRISONER, DIPLOMAT, ENVOY):
        world.chara(cid, f"干员{cid}")


def prepare(cid: int) -> None:
    """为角色写入非默认状态：设助理与服务、跟随囚禁标记、状态污浊束缚、需求、等待行动与事件。"""
    relations.assistant_character_id.set(0, cid)
    services = relations.assistant_services(cid)
    relations.assistant_services.set(cid, {key: 1 for key in services})
    flags.set(cid, is_follow=1, imprisonment=True)
    for sid in FEEL_STATES:
        status.set(cid, sid, 50)
    dirty.set(cid, a_clean=2)
    h_state.set(cid, bondage=2)
    needs.set(cid, hit=1, mana=1, hunger=30, tired=30, urine=30, sleep=30)
    activity.update_behavior(
        cid, behavior_id=constant.Behavior.WAIT, duration=30, move_target=GATE
    )
    activity.set_event(cid, event_id="e", skip_instruct_talk=True)


def observe(cid: int) -> dict[str, Any]:
    """提取角色在编、位置、助理、标记、状态、需求、行动与事件的可序列化观测字典。"""
    b = activity.behavior(cid)
    e = activity.event(cid)
    need = needs.of(cid)
    services = relations.assistant_services(cid).values()
    assistant = relations.assistant_character_id(0)
    feel = sorted({status.of(cid)[sid] for sid in FEEL_STATES})
    cleaned = [dirty.get(cid, "a_clean"), h_state.get(cid, "bondage")]
    started = b.start_time == game_time.now()
    named = ("is_follow", "imprisonment", "escaping", "in_diplomatic_visit")
    return {
        "roster": roster.has(cid),
        "position": activity.position(cid),
        "assistant": [assistant, sorted(set(services))],
        "flags": [flags.get(cid, name) for name in named],
        "cleared": [feel, *cleaned],
        "needs": [need[key] for key in NEEDS],
        "behavior": [b.behavior_id, b.duration, started],
        "move_target": list(b.move_target),
        "state": activity.state(cid),
        "target": activity.target(cid),
        "event": [e.event_id, e.skip_instruct_talk],
    }


def run_lifecycle() -> dict[str, Any]:
    """在同一写入块内对角色依次执行离线与上线，返回两次观测结果及排入的打断列表。"""
    fresh_world()
    with kernel_data.writing():
        prepare(ASSISTANT)
        svc.chara_off_line(ASSISTANT)
        off = observe(ASSISTANT)
        flags.set(ASSISTANT, in_diplomatic_visit=AEGIR, escaping=True)
        activity.update_behavior(ASSISTANT, move_target=GATE)
        mark = plan_queue.mark()
        svc.chara_on_line(ASSISTANT, game_time.now())
        on = observe(ASSISTANT)
        interrupted = plan_queue.take_since(mark)
    return {"off": off, "on": on, "interrupted": interrupted}


def run_callers() -> dict[str, Any]:
    """打桩委托写入、提示与成就回调后执行越狱与抵达结算，返回抵达标志、观测结果与打断列表。"""
    fresh_world()
    now = game_time.now()
    with (
        kernel_data.writing(),
        mock.patch.object(field_commission_function, "create_temp_commission"),
        mock.patch.object(ui_hooks, "_notices", []),
        mock.patch.object(achievement_service, "_unlocked", []),
    ):
        prison.imprison(PRISONER, now, 90)
        flags.set(PRISONER, imprisonment=True)
        prison_service.escape_success(PRISONER)
        diplomacy.set_post(location.START, diplomat=DIPLOMAT, policy=1)
        diplomacy.set_post(AEGIR, diplomat=ENVOY, policy=1)
        roster.remove(ENVOY)
        location.set_move(AEGIR, now)
        mark = plan_queue.mark()
        arrived = navigation_service.judge_arrive()
        interrupted = plan_queue.take_since(mark)
        seen = [observe(cid) for cid in (PRISONER, DIPLOMAT, ENVOY)]
        return {"arrived": arrived, "seen": seen, "interrupted": interrupted}


class FreshProcessTest(FastTestCase):
    """独立子进程模块隔离与无结算包运行测试类。"""

    def run_blocked(self, roots: tuple, body: str, result: str) -> Any:
        """在子进程以指定拦截前缀执行 BLOCKED_RUN 脚本，并解析标准输出末行 JSON。"""
        script = BLOCKED_RUN.format(roots=roots, body=body, result=result)
        done = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            check=False,
            text=True,
            timeout=300,
        )
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        return json.loads(done.stdout.splitlines()[-1])

    def test_imports_load_no_ui_or_settle(self) -> None:
        """在子进程按 BLOCKED 拦截导入三项无界面服务，断言导入成功且无拦截模块加载。"""
        body = f"from Script.Modules.gameplay_resolution import {SERVICES}"
        self.assertEqual(self.run_blocked(BLOCKED, body, "0"), [0, []])

    def test_lifecycle_and_callers_run_without_settle(self) -> None:
        """在全量拦截 BLOCKED 的无界面子进程中执行生命周期与越狱抵达路径，校验字段与打断且无拦截加载。"""
        result = "[case.run_lifecycle(), case.run_callers()]"
        report, loaded = self.run_blocked(BLOCKED, UI_FREE_BOOT, result)
        self.assertEqual(loaded, [])
        lifecycle, callers = report
        off, on = lifecycle["off"], lifecycle["on"]
        self.assertEqual({key: off[key] for key in OFF_LINE}, OFF_LINE)
        self.assertEqual({key: on[key] for key in ON_LINE}, ON_LINE)
        self.assertEqual(lifecycle["interrupted"], [str(ASSISTANT)])
        self.assertTrue(callers["arrived"])
        prisoner, diplomat, envoy_seen = callers["seen"]
        self.assertEqual(prisoner["position"], ["0", "0"])
        self.assertEqual(diplomat["position"], ["0", "0"])
        envoy = [envoy_seen[key] for key in ("roster", "behavior", "state")]
        self.assertEqual(envoy, [True, ON_LINE["behavior"], ON_LINE["state"]])
        self.assertEqual(callers["interrupted"], [str(ENVOY)])


class SettleEffectTest(FastTestCase):
    """结算效果包装函数与生命周期服务等价性测试类。"""

    def outcome(self, call: Callable[[], object]) -> core.GameState:
        """在已准备好的世界单次写入块内执行调用，记录排入打断并返回最终游戏状态。"""
        fresh_world()
        kernel_data.written(prepare, ASSISTANT)
        with kernel_data.writing():
            mark = plan_queue.mark()
            call()
            self.interrupted = plan_queue.take_since(mark)
        return core.state()

    def settle(self, effect: int, add_time: int) -> core.GameState:
        """加载默认结算模块并经 outcome 调用已登记的行为结算效果处理函数。"""
        importlib.import_module("Script.Settle.default")
        handler = constant.settle_behavior_effect_data[effect]
        change = game_type.CharacterStatusChange()
        now = game_time.now()
        return self.outcome(lambda: handler(ASSISTANT, add_time, change, now))

    def test_zero_add_time_changes_nothing(self) -> None:
        """验证三项已登记结算效果在 add_time 为 0 时不改动游戏状态且不排入打断。"""
        before = self.outcome(lambda: None)
        for effect in (FX.ASSISTANT_RESET, FX.CHARA_OFF_LINE, FX.CHARA_ON_LINE):
            with self.subTest(effect=effect):
                self.assertEqual(self.settle(effect, 0), before)
                self.assertEqual(self.interrupted, [])

    def test_effects_match_service_calls(self) -> None:
        """验证三项结算效果在 add_time 为 1 时会修改状态，且结果与打断列表与对应服务调用一致。"""
        now = game_time.now()
        untouched = self.outcome(lambda: None)
        for effect, call in (
            (FX.ASSISTANT_RESET, lambda: svc.clear_assistant(ASSISTANT)),
            (FX.CHARA_OFF_LINE, lambda: svc.chara_off_line(ASSISTANT)),
            (FX.CHARA_ON_LINE, lambda: svc.chara_on_line(ASSISTANT, now)),
        ):
            with self.subTest(effect=effect):
                settled = self.settle(effect, 1)
                settled_interrupts = self.interrupted
                self.assertNotEqual(settled, untouched)
                self.assertEqual(settled, self.outcome(call))
                self.assertEqual(settled_interrupts, self.interrupted)
