# -*- coding: UTF-8 -*-
"""
玩家选择的草稿（draft）
======================

- 编码：缓存里的对象、以 UUID 为键的食物、集合、分数与时间编码再解码后与原物 pickle 相等，经内核冻结后也一样。
- 测试在缓存上放一张测试用的条目表 ITEMS（条目id到食物对象），草稿的读写都对着它。
- 草稿：副本上的改动 diff 之后 apply 到原物上，原物与副本 pickle 相等。原值已变时 apply 报错。
- LazyDict 只复制读到的条目，pickle 成普通 dict。
- game_type.Cache.__getattr__：草稿外与 __ 开头的名字报 AttributeError。hasattr、带默认值的 getattr、vars、
  pickle（存档）与 copy.deepcopy 在草稿外照旧，草稿关闭后缓存里没有留下副本。
- player_pick.drafting：改了状态的一段选择定下一个 0 分钟的 Edit，定下的行为带上草稿，取消什么也不留下。
- 草稿里换入（读档、新周目）先换回原物：换入失败时缓存是原物，成功时换入在原物上进行。
"""

import copy
import datetime
import pickle
import sys
from collections.abc import Mapping
from fractions import Fraction
from typing import Any, cast
from types import SimpleNamespace
from unittest import mock

from Script.Core import cache_control, game_type
from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.gameplay_resolution import actions, draft, edits, intent
from Script.Modules.save_load import kernel_state
from Script.Modules.tk_ui import player_pick
from Script.Modules.domains import inventory
from tests import kernel_data
from tests.fast.base import FastTestCase
from Script.UI.Moudle import view

KEEP = player_pick.UI_STATE | player_pick.META_STATE
ITEMS = "draft_items"
""" 缓存上测试用条目表的属性名 """


def items() -> dict[int, Any]:
    """读取缓存上的测试条目表，在草稿内经 Cache.__getattr__ 返回副本"""
    return cast(dict[int, Any], getattr(cache_control.cache, ITEMS))


class DraftCase(FastTestCase):
    """每个测试结束时丢掉没关的草稿，一个失败的测试不连累后面的"""

    def setUp(self) -> None:
        """复原小世界，在缓存挂上两项食物测试条目（0 博士、1 阿米娅），并登记测试结束时的清理"""
        super().setUp()
        table: dict[int, Any] = {}
        for item_id, name in ((0, "博士"), (1, "阿米娅")):
            table[item_id] = game_type.Food()
            table[item_id].name = name
        vars(cache_control.cache)[ITEMS] = table
        self.addCleanup(vars(cache_control.cache).pop, ITEMS, None)
        self.addCleanup(draft.abandon)


def pickled(value: object) -> bytes:
    """值的 pickle 字节"""
    return pickle.dumps(value)


class CodecTest(DraftCase):
    """编码与解码"""

    def test_round_trip_game_objects(self) -> None:
        """
        测试条目、UUID 为键的食物映射、集合、分数、时间与元组经编解码往返后编码一致，经内核冻结后解码也一致
        """
        chara = items()[1]
        chara.at = datetime.datetime(2026, 11, 19, 12, 30)
        food = game_type.Food()
        food.name = "蛋糕"
        value = {
            "chara": chara,
            "foods": {food.uid: food},
            "tags": {3, 1, 2},
            "ratio": Fraction(7, 3),
            "at": datetime.datetime(2026, 11, 19, 12, 30),
            "pair": (1, "x"),
            "nested": [[1, 2], {"k": None}],
        }
        encoded = draft.encode(value)
        frozen = core._frozen(encoded)
        for back in (draft.decode(encoded), draft.decode(frozen)):
            self.assertEqual(draft.encode(back), encoded)
            assert isinstance(back, dict)
            self.assertIs(type(back["chara"].at), type(chara.at))
            self.assertEqual(back["ratio"], Fraction(7, 3))
            self.assertEqual(back["tags"], {1, 2, 3})
            self.assertEqual(list(back["foods"]), [food.uid])

    def test_unknown_type_raises(self) -> None:
        """不在 Script 下的对象报 TypeError"""
        with self.assertRaises(TypeError):
            draft.encode(object())


class DiffApplyTest(DraftCase):
    """草稿的比较与写入"""

    def setUp(self) -> None:
        """玩家与一名干员在场"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")

    def test_diff_then_apply_reproduces_copy(self) -> None:
        """草稿内修改条目 quality、向 notes 追加一项、删去条目 0 并改动干员背包。apply 后原物与副本 pickle 相等"""
        items()[1].notes = []
        session = draft.Session(KEEP)
        items()[1].quality = 5
        kernel_data.put(inventory.set_item, 1, 99, 1)
        notes: list[str] = items()[1].notes
        notes.append("中枢")
        items().pop(0)
        changed = (pickled(dict(items())), pickled(notes))
        changes, interrupts = session.close()
        self.assertEqual(interrupts, [])
        self.assertIn(0, items())
        self.assertNotEqual(items()[1].quality, 5)
        frozen = core._frozen(cast(core.JSON, changes))
        draft.apply(cast(list[draft.Change], frozen))
        after = (pickled(dict(items())), pickled(items()[1].notes))
        self.assertEqual(after, changed)

    def test_new_and_removed_dict_values_apply(self) -> None:
        """草稿里给嵌套字典加了一项（值是字典）、删了另一项：apply 之后原物与副本 pickle 相等"""
        nested: dict[Any, Any] = {0: {1: [0, "理论教室一"]}}
        items()[1].notes = nested
        session = draft.Session(KEEP)
        selected: dict[Any, Any] = items()[1].notes
        selected[1] = {2: [1, "实践教室一"]}
        del selected[0]
        changed = pickled(items()[1].notes)
        changes, _ = session.close()
        self.assertEqual(items()[1].notes, {0: {1: [0, "理论教室一"]}})
        frozen = core._frozen(cast(core.JSON, changes))
        draft.apply(cast(list[draft.Change], frozen))
        self.assertEqual(pickled(items()[1].notes), changed)

    def test_apply_refuses_stale_draft(self) -> None:
        """草稿之后原值变了：apply 报错"""
        session = draft.Session(KEEP)
        items()[1].quality = 5
        changes, _ = session.close()
        items()[1].quality = 6
        with self.assertRaises(RuntimeError):
            draft.apply(changes)

    def test_lazy_dict_copies_only_touched(self) -> None:
        """只访问并修改条目 1 时条目 0 保持原引用，pickle 与 deepcopy 后得到普通 dict"""
        original = items()
        lazy = draft.LazyDict(original)
        lazy[1].quality = 5
        self.assertIs(dict.__getitem__(lazy, 0), original[0])
        self.assertIsNot(dict.__getitem__(lazy, 1), original[1])
        self.assertIs(type(pickle.loads(pickle.dumps(lazy))), dict)
        self.assertIs(type(copy.deepcopy(lazy)), dict)


class CacheAttributeTest(DraftCase):
    """Cache.__getattr__ 在草稿内外"""

    def setUp(self) -> None:
        """玩家在场"""
        super().setUp()
        self.world.chara(0, "博士")

    def test_outside_session_behaves_as_before(self) -> None:
        """草稿外：没有的属性报 AttributeError，hasattr、getattr 默认值、vars、pickle 与 deepcopy 照旧"""
        cache = cache_control.cache
        self.assertFalse(hasattr(cache, "no_such_name"))
        self.assertEqual(getattr(cache, "no_such_name", 5), 5)
        dunder = "__no_such_dunder__"
        with self.assertRaises(AttributeError):
            getattr(cache, dunder)
        names = set(vars(cache))
        self.assertIn(ITEMS, names)
        loaded = pickle.loads(pickle.dumps(cache))
        self.assertEqual(set(vars(loaded)), names)
        copied = copy.deepcopy(cache)
        self.assertEqual(set(vars(copied)), names)
        self.assertEqual(getattr(copied, ITEMS)[0].name, items()[0].name)

    def test_session_leaves_no_copy(self) -> None:
        """草稿里读写过的属性：关闭后缓存的每个顶层属性都是打开前的那个对象，没有 LazyDict 留下"""
        cache = cache_control.cache
        before = dict(vars(cache))
        session = draft.Session(KEEP)
        self.assertNotIn(ITEMS, vars(cache))
        self.assertFalse(hasattr(cache, "no_such_name"))
        self.assertEqual(getattr(cache, "no_such_name", 5), 5)
        other = game_type.Cache()
        self.assertFalse(hasattr(other, ITEMS), "别的 Cache 对象不取草稿")
        items()[0].name = "草稿"
        self.assertIsInstance(vars(cache)[ITEMS], draft.LazyDict)
        dunder = "__deepcopy__"
        with self.assertRaises(AttributeError):
            getattr(cache, dunder)
        session.close()
        self.assertEqual(set(vars(cache)), set(before))
        for name, value in before.items():
            self.assertIs(vars(cache)[name], value, name)
        self.assertEqual(items()[0].name, "博士")
        self.assertFalse(draft.active())


class DraftingTest(DraftCase):
    """player_pick.drafting 在玩家选择里"""

    def setUp(self) -> None:
        """玩家与一名干员在场，当作在选行动中"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")
        self.enterContext(player_pick.picking())

    def test_changed_state_commits_one_edit(self) -> None:
        """改了干员的体力而没有定下行动：抛出 0 分钟的 Edit，草稿里是这一项，缓存是原物"""
        with self.assertRaises(player_pick.Chosen) as raised:
            with player_pick.drafting("test"):
                items()[1].quality = 5
        act = raised.exception.action
        self.assertEqual(
            (act.action_id, act.who, act.duration), (edits.EDIT, "0", 0)
        )
        data = act.action_data
        assert isinstance(data, dict)
        self.assertEqual(len(data["draft"]), 1)
        self.assertNotEqual(items()[1].quality, 5)

    def test_look_only_commits_nothing(self) -> None:
        """只读、只改界面状态：没有 Edit"""
        with player_pick.drafting("test"):
            _ = items()[1].name
            view.now_panel_id = 5
        self.assertEqual(view.now_panel_id, 5)

    def test_back_leaves_nothing(self) -> None:
        """改了之后取消：抛出 Back，缓存是原物"""
        with self.assertRaises(player_pick.Back):
            with player_pick.drafting("test"):
                items()[1].quality = 5
                player_pick.back()
        self.assertNotEqual(items()[1].quality, 5)
        self.assertFalse(draft.active())

    def test_chosen_behavior_carries_draft(self) -> None:
        """改了之后定下一个行为：Intent 带上草稿；判定没过时开始门不带过去"""
        with self.assertRaises(player_pick.Chosen) as raised:
            with player_pick.drafting("test"):
                items()[1].quality = 5
                player_pick.choose("wait", 5)
        data = raised.exception.action.action_data
        assert isinstance(data, dict)
        self.assertEqual(len(data["draft"]), 1)

    def test_other_action_with_draft_raises(self) -> None:
        """改了之后定下的行动既不是 Edit 也没有行为id：TypeError"""
        other = core.Action("0", core.idle.name, None, 0, 1)
        with self.assertRaises(TypeError):
            with player_pick.drafting("test"):
                items()[1].quality = 5
                raise player_pick.Chosen(other)

    def test_outside_pick_runs_plain(self) -> None:
        """不在选行动中：直接写缓存"""
        player_pick._in_pick = False
        with player_pick.drafting("test"):
            items()[1].quality = 5
        self.assertEqual(items()[1].quality, 5)


class ResetInSessionTest(DraftCase):
    """草稿里换入"""

    def setUp(self) -> None:
        """玩家在场；新周目的面板换成改缓存的替身"""
        super().setUp()
        self.world.chara(0, "博士")
        self.broken = False

        def setup(inherit: object) -> None:
            self.cache.old_character_id += 1
            if self.broken:
                raise RuntimeError("setup")

        panel = SimpleNamespace(setup=setup)
        self.enterContext(
            mock.patch.dict(sys.modules, {"Script.UI.Panel.new_round": panel})
        )
        core.load(load_order.LOAD_ORDER)

    def test_failed_reset_in_session_restores_originals(self) -> None:
        """
        草稿内修改条目名后新周目出错时，缓存恢复为原物，条目名与 old_character_id 保持不变，条目表仍为原 dict。
        草稿在失败后关闭
        """
        before = dict(vars(cache_control.cache))
        old_id = self.cache.old_character_id
        draft.Session(KEEP)
        items()[0].name = "草稿"
        self.broken = True
        with self.assertRaises(RuntimeError):
            kernel_state.new_round({})
        self.assertFalse(draft.active())
        self.assertEqual(self.cache.old_character_id, old_id)
        self.assertEqual(items()[0].name, "博士")
        self.assertIs(type(items()), dict)
        self.assertEqual(set(vars(cache_control.cache)), set(before))

    def test_reset_in_session_runs_on_originals(self) -> None:
        """草稿内修改条目名后新周目成功时，old_character_id 加一，草稿中的条目名不写入缓存。草稿在换入后关闭"""
        old_id = self.cache.old_character_id
        draft.Session(KEEP)
        items()[0].name = "草稿"
        with mock.patch.object(actions, "project", lambda new: new):
            kernel_state.new_round({})
        self.assertFalse(draft.active())
        self.assertEqual(self.cache.old_character_id, old_id + 1)
        self.assertEqual(items()[0].name, "博士")


class IntentDraftTest(DraftCase):
    """开始门的判定没过时不带草稿"""

    def test_failed_judge_drops_draft(self) -> None:
        """_judged 换成失败行为时，draft 与 interrupts 都不带过去"""
        from Script.Modules.gameplay_resolution import start_gate
        from Script.System.Instruct_System import handle_instruct

        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")
        chosen = intent.Intent(behavior_id="kiss", minutes=5, target=1)
        chosen["judge"] = "亲吻"
        chosen["draft"] = [((("a", "x"),), 1, 2)]
        chosen["interrupts"] = ["1"]
        act = intent.behavior_action(0, chosen)
        with mock.patch.object(
            handle_instruct, "_judged_behavior_id", lambda *a: "kiss_fail"
        ), mock.patch.object(
            handle_instruct, "_instruct_duration", lambda b, d: 1
        ):
            data = act.action_data
            assert isinstance(data, Mapping)
            judged = start_gate._judged(act, 0, data)
        judged_data = judged.action_data
        assert isinstance(judged_data, Mapping)
        self.assertNotIn("draft", judged_data)
        self.assertNotIn("interrupts", judged_data)
