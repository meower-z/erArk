# -*- coding: UTF-8 -*-
"""
基地关押区状态（base.prisoners 与 base.prison_settings）
=======================================================
- 读写：记录、更新、移除条目，换 id 与批量删除，配置项、开关与列表的读写与默认回落。
- 读档：旧存档的七项属性导入内核状态并从对象上删掉；当前版本对象无这些属性时状态不变；类型不符按缺项计数。
- 编解码：两个键经 kernel_state 往返后不变。
- 自检：ISLAND-29、ROSTER-05、ROSTER-06、ROSTER-13 在合法与违规状态下的结果。
"""

import datetime
from types import SimpleNamespace

from Script.Config import game_config
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import flags, prison
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import kernel_state, upgrade
from Script.Test.Static_Check.check_registry import get_all_checks
from tests.fast.base import FastTestCase
from tests import kernel_data


class PrisonStateTest(FastTestCase):
    """关押区数据在内核状态里的读写、旧存档导入、编解码与自检"""

    def setUp(self) -> None:
        """放入玩家并打开基于当前状态的缓冲区"""
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))

    def flagged(self, check_id: str) -> bool:
        """
        运行一项静态自检
        Keyword arguments:
        check_id -- 检查编号
        Return arguments:
        bool -- 检出问题时为 True
        """
        _name, run = get_all_checks()[check_id]
        return bool(run())

    def test_prisoner_crud_remap_and_drop(self) -> None:
        """登记、更新数值、移除、换 id 与批量移除按顺序生效"""
        now = game_time.now()
        self.assertEqual(prison.prisoners(), {})
        self.assertEqual(prison.prisoner_ids(), ())
        prison.imprison(10, now, 5)
        prison.imprison(20, now, 12)
        self.assertTrue(prison.is_prisoner(10))
        self.assertEqual(prison.prisoner_ids(), (10, 20))
        self.assertEqual(prison.escape_probability(10), 5)
        prison.set_escape_probability(10, 25)
        self.assertEqual(prison.escape_probability(10), 25)
        self.assertEqual(prison.prisoners()[10], [now, 25])
        prison.remap({10: 110})
        self.assertEqual(prison.prisoner_ids(), (110, 20))
        self.assertEqual(prison.escape_probability(110), 25)
        self.assertEqual(prison.drop_prisoners({20, 999}), 1)
        self.assertEqual(prison.prisoner_ids(), (110,))
        self.assertTrue(prison.release(110))
        self.assertFalse(prison.release(110))
        self.assertEqual(prison.prisoners(), {})

    def test_settings_defaults_updates_and_fill(self) -> None:
        """未写入时读配置默认值，改写、补全与列表切换生效"""
        config_keys = list(game_config.config_confinement_training_setting)
        self.assertEqual(prison.settings(), dict.fromkeys(config_keys, 0))
        self.assertEqual(prison.setting(config_keys[0]), 0)
        self.assertFalse(prison.cleaning())
        self.assertFalse(prison.lubrication())
        self.assertEqual(prison.tools(), {})
        self.assertEqual(prison.assistant_behaviors(), [])
        self.assertEqual(prison.assistant_ban_behaviors(), [])

        prison.reset_settings()
        prison.set_setting(4, 2)
        self.assertEqual(prison.setting(4), 2)
        prison.set_cleaning(True)
        prison.set_lubrication(True)
        prison.set_tool(0, 1)
        prison.toggle_assistant_behavior("act_a")
        prison.toggle_assistant_behavior("act_b")
        prison.toggle_assistant_behavior("act_a")
        prison.toggle_assistant_ban_behavior("act_c")
        self.assertTrue(prison.cleaning())
        self.assertTrue(prison.lubrication())
        self.assertEqual(prison.tool(0), 1)
        self.assertEqual(prison.tool(99), 0)
        self.assertEqual(prison.assistant_behaviors(), ["act_b"])
        self.assertEqual(prison.assistant_ban_behaviors(), ["act_c"])

    def test_adopt_old_save_v0_and_current(self) -> None:
        """旧存档的七项属性导入内核状态并删掉，当前版本无属性时不变"""
        now = game_time.now()
        island = SimpleNamespace(
            current_prisoners={15: [now, 18]},
            confinement_training_setting={1: 2, 4: 1},
            pre_training_cleaning=True,
            pre_training_lubrication=False,
            pre_training_tool_dict={0: 1, 1: 0},
            sex_assistant_ai_behavior_id_list=["act_x"],
            sex_assistant_ai_ban_behavior_id_list=["act_y"],
            other_field=42,
        )
        missing = prison.adopt_old_save({"rhodes_island": island}, 0)
        self.assertEqual(missing, 0)
        self.assertEqual(vars(island), {"other_field": 42})
        self.assertEqual(prison.prisoners(), {15: [now, 18]})
        self.assertEqual(prison.settings(), {1: 2, 4: 1})
        self.assertTrue(prison.cleaning())
        self.assertFalse(prison.lubrication())
        self.assertEqual(prison.tools(), {0: 1, 1: 0})
        self.assertEqual(prison.assistant_behaviors(), ["act_x"])
        self.assertEqual(prison.assistant_ban_behaviors(), ["act_y"])

        added = prison.fill_missing_settings()
        self.assertEqual(
            added, len(game_config.config_confinement_training_setting) - 2
        )
        self.assertEqual(prison.setting(1), 2)
        self.assertEqual(prison.setting(4), 1)

        before_p = working.get(None, prison.PRISONERS)
        before_s = working.get(None, prison.SETTINGS)
        current_missing = prison.adopt_old_save(
            {"rhodes_island": SimpleNamespace()}, upgrade.CURRENT
        )
        self.assertEqual(current_missing, 0)
        self.assertEqual(working.get(None, prison.PRISONERS), before_p)
        self.assertEqual(working.get(None, prison.SETTINGS), before_s)

    def test_adopt_wrong_type_counts_missing(self) -> None:
        """旧存档属性类型不符时删掉并计入缺项"""
        island = SimpleNamespace(
            current_prisoners=[],
            pre_training_cleaning=1,
        )
        missing = prison.adopt_old_save({"rhodes_island": island}, 0)
        self.assertEqual(missing, len(prison.PICKLED_TYPES))
        self.assertEqual(vars(island), {})
        self.assertEqual(prison.prisoners(), {})
        self.assertFalse(prison.cleaning())

    def test_codec_round_trip(self) -> None:
        """两个键经存档编解码往返后值与类型一致"""
        now = game_time.now()
        with working.based_on(core.state()) as buf:
            prison.imprison(30, now, 7)
            prison.reset_settings()
            prison.set_setting(4, 1)
            prison.set_cleaning(True)
            prison.set_tool(2, 1)
            prison.toggle_assistant_behavior("act_1")
            effects = buf.effects()
        state = core.preview(core.state(), effects)
        encoded = kernel_state.encode(state, "tok")
        self.assertEqual(encoded["version"], upgrade.CURRENT)
        decoded = kernel_state.decode(encoded, tagged=True)
        self.assertEqual(prison.prisoners(decoded), {30: [now, 7]})
        self.assertEqual(prison.setting(4, game=decoded), 1)
        self.assertTrue(prison.cleaning(decoded))
        self.assertEqual(prison.tools(decoded), {2: 1})
        self.assertEqual(prison.assistant_behaviors(decoded), ["act_1"])

    def test_static_checks(self) -> None:
        """合法时四项自检通过，违规时各报对应检查"""
        self.world.chara(1, "干员1")
        self.cache.npc_id_got.add(1)
        now = game_time.now()
        prison.reset_settings()
        kernel_data.put(flags.set, 1, imprisonment=True)
        prison.imprison(1, now, 10)
        self.assertFalse(self.flagged("ISLAND-29"))
        self.assertFalse(self.flagged("ROSTER-05"))
        self.assertFalse(self.flagged("ROSTER-06"))
        self.assertFalse(self.flagged("ROSTER-13"))

        prison.set_escape_probability(1, 150)
        self.assertTrue(self.flagged("ISLAND-29"))
        self.assertTrue(self.flagged("ROSTER-06"))

        prison.set_escape_probability(1, 10)
        kernel_data.put(flags.set, 1, imprisonment=False)
        self.assertTrue(self.flagged("ROSTER-05"))
        kernel_data.put(flags.set, 1, imprisonment=True)

        future = now + datetime.timedelta(hours=1)
        prison.imprison(1, future, 10)
        self.assertTrue(self.flagged("ROSTER-06"))
        prison.imprison(1, now, 10)

        prison.set_setting(4, 999)
        self.assertTrue(self.flagged("ROSTER-13"))


class PrisonWriteBlockTest(FastTestCase):
    """缓冲区之外写入关押区键会报错"""

    def test_write_outside_buffer_raises(self) -> None:
        """未打开 working 缓冲区时写两个键均报 RuntimeError"""
        with self.assertRaises(RuntimeError):
            prison.imprison(10, game_time.now(), 0)
        with self.assertRaises(RuntimeError):
            prison.set_setting(4, 1)
