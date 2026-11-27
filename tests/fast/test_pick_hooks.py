# -*- coding: UTF-8 -*-
"""
玩家选择钩子无界面隔离与接入测试
================================
PickHooksUiFreeTest 在无界面子进程中验证 pick_hooks 的默认行为、槽位登记与界面模块隔离。
PickHooksPlayerPickTest 在本进程中验证 pick_hooks 向 player_pick 的转发以及调用时查找行为。
HandleInstructPickTest 替换 pick_hooks 槽位，验证 handle_instruct 通过 pick_hooks 调用选择与返回入口。
"""

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from unittest import mock

from Script.Core import constant
from Script.Design import instuct_judege
from Script.Modules.domains import inventory
from Script.Modules.gameplay_resolution import edits, pick_hooks
from Script.Modules.tk_ui import player_pick
from Script.System.Instruct_System import handle_instruct
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ChildRun, run_ui_free

ITEM = 99
""" PickHooksPlayerPickTest 读写角色 1 背包条目时使用的测试物品编号。 """
RUNS = """
payload["error"] = None
try:
    from contextlib import nullcontext
    from Script.Modules.gameplay_resolution import pick_hooks

    with pick_hooks.drafting("instruct 1") as value:
        payload["plain"] = repr(value)
    for name, call in (
        ("choose", lambda: pick_hooks.choose("wait", 5)),
        ("back", pick_hooks.back),
    ):
        try:
            call()
        except RuntimeError as error:
            payload[name] = repr(error)

    calls = []

    def choose(*args, **kwargs):
        calls.append(["choose", list(args), kwargs])
        raise KeyError("chosen")

    def back():
        calls.append(["back"])
        raise LookupError("back")

    def drafting(origin):
        calls.append(["drafting", origin])
        return nullcontext(origin)

    pick_hooks.on_pick(choose, back, drafting)
    with pick_hooks.drafting("instruct 2") as value:
        payload["entered"] = value
    for call in (
        lambda: pick_hooks.choose("wait", 5, target=1, judge="j"),
        pick_hooks.back,
    ):
        try:
            call()
        except LookupError as error:
            payload.setdefault("raised", []).append(repr(error))
    payload["calls"] = calls
except ImportError as error:
    payload["error"] = repr(error)
"""
""" 无界面子进程脚本，导入 nullcontext 与 pick_hooks，测试默认与登记后调用并向 payload 记录结果与异常。 """


class PickHooksUiFreeTest(FastTestCase):
    """无界面子进程中的 pick_hooks 默认行为、槽位登记与界面模块隔离测试。"""

    child: ChildRun

    @classmethod
    def setUpClass(cls) -> None:
        """调用父类类级准备并经 run_ui_free 执行 RUNS，将结果保存到 cls.child。"""
        super().setUpClass()
        cls.child = run_ui_free(RUNS)

    def test_defaults_without_ui(self) -> None:
        """
        验证无界面子进程未记录导入错误且默认 drafting 绑定 None。
        同时断言默认 choose 与 back 抛出预期的 RuntimeError。
        """
        payload = self.child.payload
        self.assertIsNone(payload["error"])
        self.assertEqual(payload["plain"], "None")
        message = "no player pick handler registered in pick_hooks"
        self.assertEqual(payload["choose"], f"RuntimeError({message!r})")
        self.assertEqual(payload["back"], f"RuntimeError({message!r})")

    def test_registered_handlers_get_calls(self) -> None:
        """
        验证经 on_pick 登记假处理函数后，drafting 绑定返回上下文的值且 choose 与 back 抛出假函数异常。
        同时断言三次调用及参数按顺序记入 payload["calls"]。
        """
        payload = self.child.payload
        self.assertEqual(payload["entered"], "instruct 2")
        self.assertEqual(
            payload["raised"], ["KeyError('chosen')", "LookupError('back')"]
        )
        self.assertEqual(
            payload["calls"],
            [
                ["drafting", "instruct 2"],
                ["choose", ["wait", 5], {"target": 1, "judge": "j"}],
                ["back"],
            ],
        )

    def test_hooks_touch_no_ui_module(self) -> None:
        """验证无界面子进程未尝试导入也未加载任何受拦截模块。"""
        self.assertEqual(self.child.attempted, [])
        self.assertEqual(self.child.loaded, [])


class PickHooksPlayerPickTest(FastTestCase):
    """本进程导入 player_pick 后，pick_hooks 的转发与调用时查找行为测试。"""

    def setUp(self) -> None:
        """调用父类准备并创建角色 0 与角色 1。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")

    def test_choose_raises_player_chosen(self) -> None:
        """
        验证以相同参数调用 pick_hooks.choose 与 player_pick.choose 均抛出 player_pick.Chosen。
        同时断言两个异常携带的行动属性字典相等。
        """
        behavior = constant.Behavior.SHARE_BLANKLY
        with self.assertRaises(player_pick.Chosen) as direct:
            player_pick.choose(behavior, 5, target=1, judge="j")
        with self.assertRaises(player_pick.Chosen) as hooked:
            pick_hooks.choose(behavior, 5, target=1, judge="j")
        self.assertEqual(
            vars(hooked.exception.action), vars(direct.exception.action)
        )

    def test_back_raises_player_back(self) -> None:
        """验证调用 pick_hooks.back() 会抛出 player_pick.Back。"""
        with self.assertRaises(player_pick.Back):
            pick_hooks.back()

    def test_drafting_carries_writes(self) -> None:
        """
        验证在 player_pick.picking() 内，pick_hooks.drafting 块中的背包写入在退出时抛出携带 0 分钟 Edit 的 Chosen。
        同时断言该 Edit 的来源为 instruct probe，且退出后角色 1 的背包中不含 ITEM。
        """
        self.enterContext(player_pick.picking())
        with self.assertRaises(player_pick.Chosen) as raised:
            with pick_hooks.drafting("instruct probe"):
                inventory.set_item(1, ITEM, 3)
        act = raised.exception.action
        self.assertEqual((act.action_id, act.duration), (edits.EDIT, 0))
        data = act.action_data
        assert isinstance(data, Mapping)
        self.assertEqual(data["origin"], "instruct probe")
        self.assertIsNone(inventory.items(1).get(ITEM))

    def test_patched_player_pick_seen_at_call_time(self) -> None:
        """
        验证用 mock.patch.object 替换 player_pick 的三个函数后，经 pick_hooks 的调用会命中替换后的对象。
        同时断言替换对象收到了对应参数并按设定抛出异常。
        """
        seen: list[str] = []

        @contextmanager
        def drafting(origin: str) -> Generator[None]:
            seen.append(origin)
            yield

        choose = self.enterContext(
            mock.patch.object(player_pick, "choose", side_effect=KeyError)
        )
        back = self.enterContext(
            mock.patch.object(player_pick, "back", side_effect=LookupError)
        )
        self.enterContext(mock.patch.object(player_pick, "drafting", drafting))
        with pick_hooks.drafting("instruct probe"):
            pass
        with self.assertRaises(KeyError):
            pick_hooks.choose("wait", 5, target=1)
        with self.assertRaises(LookupError):
            pick_hooks.back()
        self.assertEqual(seen, ["instruct probe"])
        choose.assert_called_once_with("wait", 5, target=1)
        back.assert_called_once_with()


class HandleInstructPickTest(FastTestCase):
    """替换 pick_hooks 槽位后，handle_instruct 通过 pick_hooks 发起选择与返回的测试。"""

    def setUp(self) -> None:
        """
        调用父类准备，创建角色 0 与角色 1，并初始化记录列表与模拟对象。
        随后用 mock.patch.multiple 替换 pick_hooks 的三个内部槽位。
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")
        self.seen: list[str] = []
        self.choose = mock.Mock(side_effect=KeyError)
        self.back = mock.Mock(side_effect=LookupError)
        self.enterContext(
            mock.patch.multiple(
                pick_hooks,
                _choose=self.choose,
                _back=self.back,
                _drafting=self.drafting,
            )
        )

    @contextmanager
    def drafting(self, origin: str) -> Generator[None]:
        """
        记录传入的来源标识并让出控制权的测试用草稿上下文生成器。
        Keyword arguments:
        origin -- str，传入的来源标识，会追加到 self.seen
        Return arguments:
        Generator[None] -- 供 contextmanager 包装的空上下文生成器
        """
        self.seen.append(origin)
        yield

    def test_instruct_picks_through_hooks(self) -> None:
        """
        验证 handle_instruct 执行 BATTLE_COMMAND 时会经 pick_hooks 触发草稿记录与 _choose 调用并抛出 KeyError。
        同时断言 self.seen 记入该指令编号，_choose 收到 SHARE_BLANKLY 与 5，且 _back 未被调用。
        """
        instruct = constant.Instruct.BATTLE_COMMAND
        self.assertIn(instruct, constant.instruct_premise_data)
        with self.assertRaises(KeyError):
            handle_instruct.handle_instruct(instruct)
        self.assertEqual(self.seen, [instruct])
        self.choose.assert_called_once_with(constant.Behavior.SHARE_BLANKLY, 5)
        self.back.assert_not_called()

    def test_failed_judge_backs_through_hooks(self) -> None:
        """
        验证 instuct_judege.ask_judge 返回 False 时，choose_instruct 经 pick_hooks 调用 _back 并抛出 LookupError。
        同时断言 _back 被无参调用一次且 _choose 未被调用。
        """
        self.enterContext(
            mock.patch.object(instuct_judege, "ask_judge", return_value=False)
        )
        with self.assertRaises(LookupError):
            handle_instruct.choose_instruct(
                constant.Behavior.SHARE_BLANKLY, 5, judge="judge probe"
            )
        self.back.assert_called_once_with()
        self.choose.assert_not_called()
