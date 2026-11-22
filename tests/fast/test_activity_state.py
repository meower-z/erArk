# -*- coding: UTF-8 -*-
"""
角色的活动在内核状态里（activity.*）
====================================
- 默认：没写过的角色读出各键的默认值。行为与事件的字段同 Behavior()、Chara_Event()，食物的 uid 除外。
- 读写：整值写入。行为与事件可以改给出的字段，也可以换成默认再改。读出的行为与事件只读，读出的列表是新列表。
- 报错：未知的字段名报 AttributeError，不在整游戏分钟上的开始时间报 ValueError。
- 二段行为：只存不为 0 的值，按配置的顺序排。second_ids 列出配置里的全部id，再接角色存着的其他id。
- 给出 GameState 时只读那个 GameState。
- 读档：旧存档角色对象上的十个属性写进状态，再从对象上删掉。整数的行为id与二段行为键换成名字。
  adopt_old_save 交回缺的二段行为配置项数。
- 编解码：十个键经 kernel_state 往返后不变，写出的版本等于 upgrade.CURRENT 且不低于 22。
- 角色对象上没有这十个属性。
"""

import datetime
from types import SimpleNamespace

from Script.Core import constant, game_type
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import activity
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import kernel_state, upgrade
from tests.fast.base import FastTestCase

NPC = 1
NOBODY = 77
""" 没建过的角色 """


def _first_pair(numbers: type, names: type) -> tuple[int, str]:
    """
    整数编号表里的第一项
    Keyword arguments:
    numbers -- 名字到整数编号的常量类
    names -- 名字到行为id的常量类
    Return arguments:
    tuple -- (整数编号, 行为id)
    """
    key = next(k for k in vars(numbers) if not k.startswith("__"))
    return getattr(numbers, key), getattr(names, key)


class ActivityStateTest(FastTestCase):
    """角色活动的读写、默认值、二段行为顺序、读档导入与编解码"""

    def setUp(self) -> None:
        """放入玩家与一名干员，打开基于当前状态的缓冲区"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(NPC, "干员")
        self.enterContext(working.based_on(core.state()))

    def test_character_has_no_activity_attributes(self) -> None:
        """角色对象上没有这十个属性"""
        fields = vars(game_type.Character())
        self.assertEqual([n for n in activity.PICKLED if n in fields], [])

    def test_defaults_match_old_character(self) -> None:
        """没写过的角色读出各键的默认值，行为与事件的字段同 Behavior()、Chara_Event()（食物的 uid 除外）"""
        self.assertEqual(activity.state(NOBODY), 0)
        self.assertEqual(activity.last_behaviors(NOBODY), [0])
        self.assertEqual(activity.second_behaviors(NOBODY), {})
        self.assertEqual(activity.must_settle(NOBODY), [])
        self.assertEqual(activity.must_show(NOBODY), [])
        self.assertEqual(activity.position(NOBODY), ["0", "0"])
        self.assertEqual(activity.target(NOBODY), 0)
        self.assertIs(activity.dead(NOBODY), False)
        read = activity.behavior(NOBODY).as_dict()
        made = vars(game_type.Behavior())
        food, made_food = read.pop("target_food"), made.pop("target_food")
        self.assertEqual(read, made)
        self.assertIs(type(read["start_time"]), type(made["start_time"]))
        self.assertIsInstance(food, game_type.Food)
        self.assertEqual(
            {k: v for k, v in vars(food).items() if k != "uid"},
            {k: v for k, v in vars(made_food).items() if k != "uid"},
        )
        self.assertEqual(
            activity.event(NOBODY).as_dict(), vars(game_type.Chara_Event())
        )

    def test_writes_replace_and_merge(self) -> None:
        """整值写入，行为与事件的改字段与换新"""
        now = game_time.now()
        activity.set_state(NPC, constant.CharacterStatus.STATUS_WAIT)
        activity.set_last_behaviors(NPC, [0, "eat"])
        activity.set_position(NPC, ["宿舍", "1区", "101"])
        activity.set_target(NPC, 0)
        activity.set_dead(NPC, True)
        activity.update_behavior(
            NPC, behavior_id="eat", duration=5, start_time=now
        )
        activity.update_behavior(NPC, move_target=["宿舍", "1区"])
        self.assertEqual(
            activity.state(NPC), constant.CharacterStatus.STATUS_WAIT
        )
        self.assertEqual(activity.last_behaviors(NPC), [0, "eat"])
        self.assertEqual(activity.position(NPC), ["宿舍", "1区", "101"])
        self.assertIs(activity.dead(NPC), True)
        behavior = activity.behavior(NPC)
        self.assertEqual((behavior.behavior_id, behavior.duration), ("eat", 5))
        self.assertEqual(behavior.start_time, now)
        self.assertEqual(behavior.move_target, ["宿舍", "1区"])
        activity.set_behavior(NPC, duration=3)
        behavior = activity.behavior(NPC)
        self.assertEqual(behavior.behavior_id, game_type.Behavior().behavior_id)
        self.assertEqual((behavior.duration, behavior.move_target), (3, []))
        activity.update_event(NPC, event_id="e1", son_event_id="e2")
        activity.update_event(NPC, son_event_id="")
        self.assertEqual(
            (activity.event(NPC).event_id, activity.event(NPC).son_event_id),
            ("e1", ""),
        )
        activity.set_event(NPC, skip_instruct_talk=True)
        self.assertEqual(activity.event(NPC).event_id, "")
        self.assertTrue(activity.event(NPC).skip_instruct_talk)

    def test_reads_are_copies_and_records_read_only(self) -> None:
        """读出的列表改了不影响状态。行为与事件的属性不能赋值。未知字段与不在整分钟上的开始时间报错"""
        activity.set_position(NPC, ["宿舍", "1区"])
        activity.position(NPC).append("101")
        activity.last_behaviors(NPC).append("eat")
        self.assertEqual(activity.position(NPC), ["宿舍", "1区"])
        self.assertEqual(activity.last_behaviors(NPC), [0])
        with self.assertRaises(AttributeError):
            activity.behavior(NPC).duration = 1
        with self.assertRaises(AttributeError):
            activity.event(NPC).event_id = "e1"
        with self.assertRaises(AttributeError):
            activity.update_behavior(NPC, no_such_field=1)
        half = game_time.now() + datetime.timedelta(seconds=30)
        with self.assertRaises(ValueError):
            activity.update_behavior(NPC, start_time=half)

    def test_second_behaviors_sparse_in_config_order(self) -> None:
        """二段行为只存非 0 值，按配置顺序排，配置里没有的id排在后面。second_ids 先列配置里的全部id"""
        order = list(activity.second_order())
        self.assertGreater(len(order), 3)
        activity.set_second_behavior(NPC, order[2], 1)
        activity.set_second_behavior(NPC, "not_in_config", 1)
        activity.set_second_behavior(NPC, order[0], 2)
        self.assertEqual(
            list(activity.second_behaviors(NPC).items()),
            [(order[0], 2), (order[2], 1), ("not_in_config", 1)],
        )
        self.assertEqual(activity.second_behavior(NPC, order[1]), 0)
        activity.set_second_behavior(NPC, order[0], 0)
        self.assertEqual(
            list(activity.second_behaviors(NPC)), [order[2], "not_in_config"]
        )
        self.assertEqual(activity.second_ids(NPC), [*order, "not_in_config"])

    def test_given_state_is_read(self) -> None:
        """给出 GameState 时读那个 GameState，不读缓冲区"""
        before = core.state()
        old = activity.position(NPC)
        activity.set_position(NPC, [*old, "宿舍"])
        self.assertEqual(activity.position(NPC), [*old, "宿舍"])
        self.assertEqual(activity.position(NPC, before), old)

    def test_adopt_old_save(self) -> None:
        """
        旧存档角色对象上的十个属性写进状态并删掉，整数编号换成名字，交回缺的二段行为配置项数。
        旧行为上为 None 的字段读出默认值，不带这些属性的对象不处理
        """
        number, behavior_id = _first_pair(
            constant.Behavior_Int, constant.Behavior
        )
        second_number, second_id = _first_pair(
            constant.SecondBehavior_Int, constant.SecondBehavior
        )
        order = activity.second_order()
        kept = next(i for i in order if i != second_id)
        old_behavior = game_type.Behavior()
        vars(old_behavior)["behavior_id"] = number
        vars(old_behavior)["target_food"] = None
        old_behavior.start_time = game_time.now()
        old_behavior.duration = 10
        old_event = game_type.Chara_Event()
        old_event.event_id = "e1"
        old = SimpleNamespace(
            state=3,
            last_behavior_id_list=[0, "eat"],
            behavior=old_behavior,
            second_behavior={second_number: 1, kept: 0},
            must_settle_second_behavior_id_list=[second_id],
            must_show_second_behavior_id_list=[],
            event=old_event,
            position=["宿舍", "1区"],
            target_character_id=0,
            dead=False,
            other_field=42,
        )
        missing = activity.adopt_old_save({"character_data": {NPC: old}})
        expected = sum(1 for i in order if i not in {second_id, kept})
        self.assertEqual(missing, expected)
        self.assertEqual(vars(old), {"other_field": 42})
        self.assertEqual(activity.state(NPC), 3)
        self.assertEqual(activity.last_behaviors(NPC), [0, "eat"])
        behavior = activity.behavior(NPC)
        self.assertEqual(behavior.behavior_id, behavior_id)
        self.assertEqual(behavior.start_time, game_time.now())
        self.assertEqual(behavior.duration, 10)
        self.assertEqual(behavior.target_food.uid.int, 0)
        self.assertEqual(activity.second_behaviors(NPC), {second_id: 1})
        self.assertEqual(activity.must_settle(NPC), [second_id])
        self.assertEqual(activity.event(NPC).event_id, "e1")
        self.assertEqual(activity.position(NPC), ["宿舍", "1区"])

        current = SimpleNamespace(other_field=1)
        before = working.get(str(0), activity.BEHAVIOR)
        self.assertEqual(
            activity.adopt_old_save({"character_data": {0: current}}), 0
        )
        self.assertEqual(working.get(str(0), activity.BEHAVIOR), before)

    def test_target_as(self) -> None:
        """target_as 块内交互对象读作给定值，块内 set_target 只改块内值、不写缓冲区，退出块后状态不变"""
        before = activity.target(NPC)
        with activity.target_as(NPC, 0):
            self.assertEqual(activity.target(NPC), 0)
            activity.set_target(NPC, 7)
            self.assertEqual(activity.target(NPC), 7)
        self.assertEqual(activity.target(NPC), before)
        self.assertEqual(working.get(str(NPC), activity.TARGET), before)

    def test_codec_round_trip(self) -> None:
        """十个键经存档编解码往返后不变，写出的版本等于 upgrade.CURRENT 且不低于 22"""
        now = game_time.now()
        food = game_type.Food()
        food.name = "便当"
        food.recipe = 7
        order = list(activity.second_order())
        with working.based_on(core.state()) as buf:
            activity.set_state(NPC, "eat")
            activity.set_last_behaviors(NPC, [0, "eat"])
            activity.set_behavior(
                NPC,
                behavior_id="eat",
                start_time=now,
                duration=15,
                target_food=food,
                move_final_target=["宿舍", "1区"],
            )
            activity.set_second_behaviors(NPC, {order[1]: 1, order[0]: 2})
            activity.set_must_settle(NPC, [order[1]])
            activity.set_must_show(NPC, [order[0]])
            activity.set_event(NPC, event_id="e1")
            activity.set_position(NPC, ["宿舍", "1区"])
            activity.set_target(NPC, 0)
            activity.set_dead(NPC, True)
            effects = buf.effects()
        state = core.preview(core.state(), effects)
        encoded = kernel_state.encode(state, "tok")
        self.assertEqual(encoded["version"], upgrade.CURRENT)
        self.assertGreaterEqual(upgrade.CURRENT, 22)
        decoded = kernel_state.decode(encoded, tagged=True)
        self.assertEqual(activity.state(NPC, decoded), "eat")
        self.assertEqual(activity.last_behaviors(NPC, decoded), [0, "eat"])
        behavior = activity.behavior(NPC, decoded)
        self.assertEqual(behavior.start_time, now)
        self.assertEqual(behavior.duration, 15)
        self.assertEqual(behavior.move_final_target, ["宿舍", "1区"])
        self.assertEqual(vars(behavior.target_food), vars(food))
        self.assertEqual(
            list(activity.second_behaviors(NPC, decoded).items()),
            [(order[0], 2), (order[1], 1)],
        )
        self.assertEqual(activity.must_settle(NPC, decoded), [order[1]])
        self.assertEqual(activity.must_show(NPC, decoded), [order[0]])
        self.assertEqual(activity.event(NPC, decoded).event_id, "e1")
        self.assertEqual(activity.position(NPC, decoded), ["宿舍", "1区"])
        self.assertIs(activity.dead(NPC, decoded), True)
