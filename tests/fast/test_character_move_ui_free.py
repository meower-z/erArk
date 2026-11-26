"""
主角寻路无界面运行与导入边界测试
================================
- 无界面运行（CharacterMoveUiFreeTest）：在无界面子进程验证 own_charcter_move 与 start_player_route。
- 界面选路（PickRouteTest）：在已加载界面的本进程中验证 see_map_panel.pick_route 选定的行动携带首段参数。
- 效果寻路（MoveEffectRouteTest）：在已加载界面的本进程验证 Move 寻路效果非结算期选定、结算期入队。
- 导入边界（CharacterMoveImportBoundaryTest）：验证 character_move.py 不导入界面、输入输出与 Tk 模块。
"""

from unittest import mock

from Script.Config import game_config
from Script.Core import constant, game_type, get_text
from Script.Design import map_handle, second_behavior
from Script.Kernel import core
from Script.Modules.domains import activity, plan
from Script.Modules.tk_ui import player_pick
from Script.UI.Panel import see_map_panel
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT, banned_imports
from tests.ui_free_subprocess import ChildRun, run_ui_free

CORRIDOR = ["宿舍", "1区", "外走廊"]
""" 测试主角出发位置对应的宿舍 1 区外走廊地图坐标 """
DORM = ["宿舍", "1区", "102"]
""" 测试锁门与开锁分支使用的宿舍 1 区 102 地图坐标 """
OFFICE = ["中枢", "博士办公室"]
""" 测试普通寻路目标对应的博士办公室地图坐标 """
MASTER_KEY = 152
""" 一次性万能钥匙的道具编号 """
_ = get_text._
""" 本地化文本翻译函数 """
SOURCE = "Script/Design/character_move.py"
""" 待检查导入边界的 character_move.py 仓库相对路径 """
PLACE_TAG = "寻路测试地点"
""" 寻路效果测试映射至 OFFICE 的临时地点标签 """
UI_FREE_RUN = f"""
import dataclasses
from unittest import mock
from Script.Config import map_config
from Script.Design import character_move, map_handle
from Script.Kernel import core
from Script.Modules.domains import flags, identity, inventory, plan, scene_state
from Script.Modules.gameplay_resolution import ui_hooks
from tests import chara_abilities, chara_data, kernel_data
from tests.chara_activity import place
from tests.world import start_time
map_config.init_map_data()
kernel_data.reset_clock(start_time(), {{}})
kernel_data.put(identity.put, identity.Identity(0, name="0", sex=1))
chara_abilities.zero_tables(0)
chara_data.seed(0, {{}})
panels = []
notices = []
chosen = []
ui_hooks.on_panel_switch(panels.append)
ui_hooks.on_notice(lambda text, **kw: notices.append(text))
ui_hooks.on_route_leg(
    lambda *leg: chosen.append(
        dict(zip(["behavior_id", "minutes", "state", "fields", "args"], leg))
    )
)
dorm = map_handle.get_map_system_path_str_for_list({DORM!r})


def run(name, target, settle=False, move=character_move.own_charcter_move, **kwargs):
    place(0, {CORRIDOR!r})
    panels.clear()
    notices.clear()
    chosen.clear()
    with mock.patch.object(core, "in_settlement", return_value=settle):
        leg = kernel_data.written(move, list(target), **kwargs)
    payload[name] = {{
        "leg": None if leg is None else dataclasses.asdict(leg),
        "route": None if plan.route() is None else list(plan.route()),
        "queue": [[kind, chosen["behavior_id"]] for kind, chosen in plan.queue(0)],
        "panels": list(panels),
        "notices": list(notices),
        "chosen": list(chosen),
    }}
    kernel_data.put(plan.set_route, None)
    kernel_data.put(plan.set_queue, 0, [])


run("pick", {OFFICE!r})
run("open_map", {OFFICE!r}, open_map=True)
kernel_data.put(flags.set, 0, hidden_sex_mode=5)
run("carry", {OFFICE!r})
kernel_data.put(flags.set, 0, hidden_sex_mode=0)
run("settle", {OFFICE!r}, settle=True)
run("start", {OFFICE!r}, move=character_move.start_player_route)
run("start_settle", {OFFICE!r}, settle=True, move=character_move.start_player_route)
run("end", {CORRIDOR!r})
kernel_data.put(flags.set, 0, move_stop=True)
run("stop", {OFFICE!r})
payload["stop_flag"] = bool(flags.get(0, "move_stop"))
kernel_data.put(scene_state.set_close_flag, dorm, 1)
kernel_data.put(inventory.set_item, 0, {MASTER_KEY}, 0)
run("locked", {DORM!r})
kernel_data.put(inventory.set_item, 0, {MASTER_KEY}, 1)
run("master_key", {DORM!r})
payload["keys_left"] = inventory.items(0)[{MASTER_KEY}]
payload["dorm_closed"] = scene_state.close_flag(dorm)
"""
""" 在无界面子进程中执行多组主角寻路场景并回传结果的代码片段 """


def leg(
    target: list[str], behavior_id: str, state: int, args: object = None
) -> dict[str, object]:
    """
    根据 CORRIDOR 到目标场景的路径边数据构造预期首段移动结果字典。
    Keyword arguments:
    target -- list[str]，目标场景的地图绝对坐标
    behavior_id -- str，预期的移动行为编号
    state -- int，预期的角色状态编号
    args -- object，预期的行动附加参数，默认为 None
    Return arguments:
    dict[str, object] -- 与 PlayerLeg 序列化结果对应的字段字典
    """
    start = map_handle.get_map_system_path_str_for_list(CORRIDOR)
    end = map_handle.get_map_system_path_str_for_list(target)
    step, minutes = map_handle.scene_path_edge[start][end]
    return {
        "behavior_id": behavior_id,
        "minutes": minutes,
        "state": state,
        "fields": {
            "behavior.move_target": step,
            "behavior.move_src": CORRIDOR,
            "behavior.move_final_target": target,
            "action_info.ask_close_door_flag": False,
        },
        "args": args,
    }


def locked_notice() -> str:
    """
    按 DORM 对应的场景名生成预期的锁门提示字符串。
    Return arguments:
    str -- 格式化后的锁门提示文本
    """
    name = constant.scene_data[
        map_handle.get_map_system_path_str_for_list(DORM)
    ].scene_name
    return _(
        "\n  ●目标移动房间——{0}，当前门是锁着的，需要钥匙或其他方法进入\n"
    ).format(name)


class CharacterMoveUiFreeTest(FastTestCase):
    """验证屏蔽受禁模块时 own_charcter_move 与 start_player_route 可在无界面子进程中正确执行。"""

    child: ChildRun
    """ 无界面子进程的单次执行结果 """

    @classmethod
    def setUpClass(cls) -> None:
        """在启用后端初始化的无界面子进程中执行一次 UI_FREE_RUN，子进程失败时抛出 RuntimeError。"""
        super().setUpClass()
        cls.child = run_ui_free(UI_FREE_RUN, boot=True)

    def test_loads_no_ui(self) -> None:
        """验证无界面子进程未尝试导入也未加载任何受拦截模块。"""
        self.assertEqual((self.child.attempted, self.child.loaded), ([], []))

    def test_pick_returns_first_leg(self) -> None:
        """验证非结算期常规与 open_map 寻路返回预期首段移动结果、路线及面板切换，且不排入计划队列。"""
        move = constant.Behavior.MOVE
        status = constant.CharacterStatus.STATUS_MOVE
        self.assertEqual(
            self.child.payload["pick"],
            {
                "leg": leg(OFFICE, move, status),
                "route": [OFFICE, CORRIDOR, 0, False],
                "queue": [],
                "panels": [constant.Panel.IN_SCENE],
                "notices": [],
                "chosen": [],
            },
        )
        self.assertEqual(
            self.child.payload["open_map"],
            {
                "leg": leg(OFFICE, move, status, {"open_map": True}),
                "route": [OFFICE, CORRIDOR, 0, True],
                "queue": [],
                "panels": [constant.Panel.IN_SCENE],
                "notices": [],
                "chosen": [],
            },
        )

    def test_carry_mode_returns_carry_leg(self) -> None:
        """验证 hidden_sex_mode 为 5 时返回 CARRY_MOVE 与 STATUS_CARRY_MOVE 对应的移动参数。"""
        carry = leg(
            OFFICE,
            constant.Behavior.CARRY_MOVE,
            constant.CharacterStatus.STATUS_CARRY_MOVE,
        )
        self.assertEqual(
            self.child.payload["carry"],
            {
                "leg": carry,
                "route": [OFFICE, CORRIDOR, 0, False],
                "queue": [],
                "panels": [constant.Panel.IN_SCENE],
                "notices": [],
                "chosen": [],
            },
        )

    def test_settlement_queues_first_leg(self) -> None:
        """验证结算期寻路返回 None、将首段移动排入计划队列、记录路线并切至场景面板。"""
        self.assertEqual(
            self.child.payload["settle"],
            {
                "leg": None,
                "route": [OFFICE, CORRIDOR, 0, False],
                "queue": [["Behavior", constant.Behavior.MOVE]],
                "panels": [constant.Panel.IN_SCENE],
                "notices": [],
                "chosen": [],
            },
        )

    def test_no_leg_switches_panel(self) -> None:
        """验证已抵达、被叫停与门锁受阻分支均返回 None、按分支切换面板，并清除 move_stop 标记。"""
        payload = self.child.payload
        for name, panel in (
            ("end", constant.Panel.IN_SCENE),
            ("stop", constant.Panel.IN_SCENE),
            ("locked", constant.Panel.SEE_MAP),
        ):
            with self.subTest(name):
                self.assertEqual(
                    payload[name],
                    {
                        "leg": None,
                        "route": None,
                        "queue": [],
                        "panels": [panel],
                        "notices": (
                            [locked_notice()] if name == "locked" else []
                        ),
                        "chosen": [],
                    },
                )
        self.assertFalse(payload["stop_flag"])

    def test_master_key_opens_door(self) -> None:
        """验证持有道具 152 时解锁目标宿舍、返回首段移动参数、发出两条提示并清空门锁与道具数量。"""
        payload = self.child.payload
        opened = leg(
            DORM, constant.Behavior.MOVE, constant.CharacterStatus.STATUS_MOVE
        )
        notices = [
            locked_notice(),
            _("\n  ●你拿出了一次性万能钥匙，悄悄打开了门\n\n"),
        ]
        self.assertEqual(
            payload["master_key"],
            {
                "leg": opened,
                "route": [DORM, CORRIDOR, 0, False],
                "queue": [],
                "panels": [constant.Panel.IN_SCENE],
                "notices": notices,
                "chosen": [],
            },
        )
        self.assertEqual((payload["keys_left"], payload["dorm_closed"]), (0, 0))

    def test_start_route_hands_leg_to_ui(self) -> None:
        """验证 start_player_route 非结算期经回调交出首段，结算期排入计划队列且不触发回调。"""
        move = constant.Behavior.MOVE
        route = [OFFICE, CORRIDOR, 0, False]
        self.assertEqual(
            self.child.payload["start"],
            {
                "leg": None,
                "route": route,
                "queue": [],
                "panels": [constant.Panel.IN_SCENE],
                "notices": [],
                "chosen": [
                    leg(OFFICE, move, constant.CharacterStatus.STATUS_MOVE)
                ],
            },
        )
        self.assertEqual(
            self.child.payload["start_settle"],
            {
                "leg": None,
                "route": route,
                "queue": [["Behavior", move]],
                "panels": [constant.Panel.IN_SCENE],
                "notices": [],
                "chosen": [],
            },
        )


class PickRouteTest(FastTestCase):
    """在已加载界面的本进程中验证 see_map_panel.pick_route 提交的行动携带首段移动参数。"""

    def setUp(self) -> None:
        """初始化测试世界并将主角置于 CORRIDOR 位置。"""
        super().setUp()
        self.world.chara(0, "博士", position=CORRIDOR)

    def test_chosen_action_carries_leg(self) -> None:
        """验证非结算期 pick_route(OFFICE, open_map=True) 抛出 Chosen。断言所选行动五项参数与预期一致。"""
        with self.assertRaises(player_pick.Chosen) as caught:
            kernel_data.written(
                see_map_panel.pick_route, list(OFFICE), open_map=True
            )
        data = caught.exception.action.action_data
        if not isinstance(data, dict):
            self.fail(f"action data is {type(data).__name__}")
        keys = ("behavior_id", "minutes", "state", "fields", "args")
        self.assertEqual(
            {key: data.get(key) for key in keys},
            leg(
                OFFICE,
                constant.Behavior.MOVE,
                constant.CharacterStatus.STATUS_MOVE,
                {"open_map": True},
            ),
        )


class MoveEffectRouteTest(FastTestCase):
    """在已加载界面的本进程中验证 Move 寻路效果在非结算期选定首段、结算期排入计划队列。"""

    mark: str
    """ 当前用例使用的刻印升级二段行为编号 """

    def setUp(self) -> None:
        """
        初始化测试世界，将主角与 1 号干员置于 CORRIDOR 并将 1 号干员的交互对象设为主角。
        为 1 号干员赋予配置表首项刻印升级对应的二段行为。
        在用例期间将 PLACE_TAG 映射至 OFFICE，并将该二段行为的效果配置为面向交互对象的 Move 寻路。
        """
        super().setUp()
        self.world.chara(0, "博士", position=CORRIDOR)
        self.world.chara(1, position=CORRIDOR)
        kernel_data.put(activity.set_target, 1, 0)
        data = next(iter(game_config.config_mark_up_data.values()))
        self.mark = data.second_behavior
        kernel_data.put(activity.set_second_behavior, 1, self.mark, 1)
        office = map_handle.get_map_system_path_str_for_list(OFFICE)
        effect = f"CVE_A2_Move|0_寻路_{PLACE_TAG}"
        self.enterContext(
            mock.patch.dict(constant.place_data, {PLACE_TAG: [office]})
        )
        self.enterContext(
            mock.patch.dict(
                game_config.config_behavior_effect_data, {self.mark: [effect]}
            )
        )

    def settle_mark(self) -> None:
        """在写入上下文中为 1 号干员执行 self.mark 对应的二段行为效果结算。"""
        kernel_data.written(
            second_behavior.second_behavior_effect,
            1,
            game_type.CharacterStatusChange(),
            [self.mark],
        )

    def test_pick_chooses_first_leg(self) -> None:
        """验证非结算期执行 Move 寻路效果抛出 Chosen，且所选行动的五项参数与预期首段一致。"""
        with self.assertRaises(player_pick.Chosen) as caught:
            self.settle_mark()
        data = caught.exception.action.action_data
        if not isinstance(data, dict):
            self.fail(f"action data is {type(data).__name__}")
        keys = ("behavior_id", "minutes", "state", "fields", "args")
        self.assertEqual(
            {key: data.get(key) for key in keys},
            leg(
                OFFICE,
                constant.Behavior.MOVE,
                constant.CharacterStatus.STATUS_MOVE,
            ),
        )

    def test_settlement_queues_first_leg(self) -> None:
        """验证结算期执行 Move 寻路效果将首段移动排入主角计划队列并记录预期路线。"""
        with mock.patch.object(core, "in_settlement", return_value=True):
            self.settle_mark()
        self.assertEqual(
            [[kind, chosen["behavior_id"]] for kind, chosen in plan.queue(0)],
            [["Behavior", constant.Behavior.MOVE]],
        )
        self.assertEqual(plan.route(), [OFFICE, CORRIDOR, 0, False])


class CharacterMoveImportBoundaryTest(FastTestCase):
    """验证 Script/Design/character_move.py 源码的导入边界。"""

    def test_source_imports_no_ui(self) -> None:
        """验证 banned_imports 检查 character_move.py 源码返回空列表。"""
        self.assertEqual(
            banned_imports((ROOT / SOURCE).read_bytes(), SOURCE), []
        )
