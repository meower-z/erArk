# -*- coding: UTF-8 -*-
"""
全局文本生成 AI 设置
====================
每个测试把 save_load.settings 指向各自的临时 settings.json，内核只载入这一个插件。
- settings.json 读写来回：Ai_Setting 7 个字段写出后，新进程里 install 装回的对象等于写出内容并补齐缺失 0 值选项。
  文件里的整数键字典以字符串键保存。
- 内核 Reset 保留全局 AI 设置：替换 normal_config.ai_setting 后调用 core.reset_state，normal_config.ai_setting
  会恢复为改过的全局对象。改动同时写入 settings.json。
- 默认 AI 设置不落盘与同进程保护：只改系统设置并读入不含 AI 设置的存档时，settings.json 不写入 "ai_setting" 段。
  新进程里读旧存档仍能收下其 AI 设置。同进程里已改过但未落盘的 AI 设置在读旧存档时不被覆盖。
- 旧版本游戏的存档里的 AI 设置在 Reset 成功后生效：全局仍为未改动默认值时，读档收下旧存档的 AI 设置。
  之后的同进程与新进程读档都不覆盖它。settings.json 已有 "ai_setting" 段时，读档不覆盖文件里的设置。
  旧对象缺少部分字段或带有非 Ai_Setting 字段时，缺失字段取默认值。多余字段则忽略。
- 首次读旧档保系统设置、失败丢弃与换态后中止提交：无 settings.json 时先 adopt_ai 再 adopt，旧档系统设置仍被收下。
  adopt_ai 准备好设置后，无论 Reset 在输入钩子还是输出钩子失败，待生效设置都会被丢弃且不生成文件。
  Reset 换掉内核状态后再抛出中止时，待生效 AI 设置仍生效并写进 settings.json。
- 缺失选项补全与提示：读入无 AI 设置的存档或默认 AI 设置的旧档时静默补全（返回 0）且不写段。
  读入含非默认 AI 设置的旧档时只返回一次补全数并写出全部选项。
  settings.json 的 "ai_setting" 段缺项时，新游戏 Reset 会把缺失选项补为 0。
- 读档入口 save_handle.update_settings：存档字典含 "ai_setting" 时，函数弹出该键、收下已有值并把缺失选项补为 0。
  存档字典不含 "ai_setting" 时，函数保留全局 AI 设置并补齐缺失选项，随后的 Reset 写出到 settings.json。
"""

import json
import os
import tempfile
from types import MappingProxyType
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import game_type, save_handle
from Script.Kernel import core
from Script.Modules.save_load import kernel_state, settings
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.fast.kernel_toys import Toy


def empty_game() -> core.GameState:
    """
    返回时钟为 0、不含角色与全局数据的空 GameState
    Return arguments:
    GameState -- 空的游戏状态
    """
    return core.GameState(0, MappingProxyType({}), MappingProxyType({}))


def chosen_ai() -> game_type.Ai_Setting:
    """
    构造 7 个字段都填有非默认测试值的 Ai_Setting 对象（API 密钥使用占位文本）
    Return arguments:
    Ai_Setting -- 填好测试值的 AI 设置对象
    """
    ai = game_type.Ai_Setting()
    ai.ai_chat_setting.update({1: 1, 5: "test-model", 9: 3})
    ai.ai_chat_api_key["OPENAI_API_KEY"] = "dummy-key"
    ai.now_ai_chat_model = "test-model"
    ai.now_ai_chat_base_url = "http://chat.test/v1"
    ai.now_ai_chat_proxy = ["http://127.0.0.1:9", "127.0.0.2"]
    ai.ai_chat_translator_setting = 2
    ai.send_data_flags.update({11: True, 12: False})
    return ai


def filled(ai: game_type.Ai_Setting) -> game_type.Ai_Setting:
    """
    把 game_config.config_ai_chat_setting 中缺失的选项编号以 0 原地补进 ai.ai_chat_setting
    Keyword arguments:
    ai -- 待补全的 AI 设置对象
    Return arguments:
    Ai_Setting -- 补全后的同一个对象
    """
    for cid in game_config.config_ai_chat_setting:
        ai.ai_chat_setting.setdefault(cid, 0)
    return ai


class AiSettingTestCase(FastTestCase):
    """全局 AI 设置测试基类：每个测试使用独立的临时 settings.json，重置 settings 的装入状态并只在内核载入设置插件"""

    def setUp(self) -> None:
        """创建临时 settings.json 路径，重置 settings 的装入状态，并在内核中只载入 settings 插件"""
        super().setUp()
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.path = os.path.join(folder, "settings.json")
        self.enterContext(mock.patch.object(settings, "path", self.path))
        self.enterContext(mock.patch.object(settings, "_live", None))
        self.enterContext(mock.patch.object(settings, "_saved", None))
        self.enterContext(mock.patch.object(settings, "_has_ai", False))
        self.enterContext(mock.patch.object(settings, "_pending_ai", None))
        core.load((settings,))

    def fresh_process(self) -> None:
        """模拟新进程：清空 settings 的内存状态，并把 normal_config.ai_setting 换成空的 Ai_Setting 对象"""
        settings._live = None
        settings._saved = None
        settings._has_ai = False
        settings._pending_ai = None
        normal_config.ai_setting = game_type.Ai_Setting()

    def load_ai(self, ai: game_type.Ai_Setting | None) -> int:
        """
        模拟一次读档：把存档里的 AI 设置交给 adopt_ai 准备，再经 _reset_keeping_cache 完成读档
        Keyword arguments:
        ai -- 存档里的 AI 设置对象，不含 AI 设置的存档传 None
        Return arguments:
        int -- adopt_ai 返回的需提示补全选项数
        """
        notice = settings.adopt_ai(ai)
        self.finish_load()
        return notice

    def finish_load(self) -> None:
        """以空 GameState 经 kernel_state._reset_keeping_cache 跑完一次读档 Reset，使暂存 AI 设置生效或被丢弃"""
        kernel_state._reset_keeping_cache(empty_game(), {"cause": "load"})

    def has_section(self) -> bool:
        """
        检查临时 settings.json 是否存在且包含 "ai_setting" 段
        Return arguments:
        bool -- 文件存在且含 "ai_setting" 段时为 True
        """
        if not os.path.exists(self.path):
            return False
        with open(self.path, encoding="utf-8") as setting_file:
            return "ai_setting" in json.load(setting_file)

    def on_disk(self) -> dict:
        """
        读取临时 settings.json 里的 "ai_setting" 段
        Return arguments:
        dict -- 磁盘上的 AI 设置字典
        """
        with open(self.path, encoding="utf-8") as setting_file:
            return json.load(setting_file)["ai_setting"]


class AiSettingFile(AiSettingTestCase):
    """验证全局 AI 设置在 settings.json 读写与内核 Reset 下的持久性"""

    def test_round_trip(self) -> None:
        """
        写入全部 7 个字段并保存后，新进程里 install 装回的结果等于写出内容并补齐缺失的 0 值选项。
        文件里的 ai_chat_setting 以字符串键保存模型名。
        """
        settings.install()
        vars(normal_config.ai_setting).update(vars(chosen_ai()))
        settings.save()
        self.fresh_process()
        settings.install()
        self.assertEqual(
            vars(normal_config.ai_setting), vars(filled(chosen_ai()))
        )
        self.assertEqual(self.on_disk()["ai_chat_setting"]["5"], "test-model")

    def test_reset_keeps_ai_setting(self) -> None:
        """
        替换 normal_config.ai_setting 后触发 core.reset_state，全局对象仍保留改过的翻译设置与 send_data_flags。
        settings.json 也写出了字符串键的 send_data_flags。
        """
        settings.install()
        normal_config.ai_setting.ai_chat_translator_setting = 1
        normal_config.ai_setting.send_data_flags[61] = True
        normal_config.ai_setting = game_type.Ai_Setting()
        core.reset_state(empty_game())
        ai = normal_config.ai_setting
        self.assertEqual(
            (ai.ai_chat_translator_setting, ai.send_data_flags), (1, {61: True})
        )
        self.assertEqual(self.on_disk()["send_data_flags"], {"61": True})


class OldSaveAiSetting(AiSettingTestCase):
    """验证读档时收下旧版本游戏的存档里的 AI 设置以及补全缺失选项的行为"""

    def test_adopted_once(self) -> None:
        """首次经 load_ai 收下旧存档里的 AI 设置后，同进程与新进程里后续的 load_ai 都不覆盖它。"""
        self.load_ai(chosen_ai())
        other = game_type.Ai_Setting()
        other.ai_chat_translator_setting = 1
        self.load_ai(other)
        self.fresh_process()
        settings.install()
        self.load_ai(other)
        self.assertEqual(
            vars(normal_config.ai_setting), vars(filled(chosen_ai()))
        )

    def test_file_with_section_not_overwritten(self) -> None:
        """settings.json 已有 "ai_setting" 段时，新进程里经 load_ai 读旧存档不覆盖文件里原有的接口地址。"""
        settings.install()
        normal_config.ai_setting.now_ai_chat_base_url = "http://local.test/v1"
        settings.save()
        self.fresh_process()
        self.load_ai(chosen_ai())
        self.assertEqual(
            normal_config.ai_setting.now_ai_chat_base_url,
            "http://local.test/v1",
        )

    def test_older_shape(self) -> None:
        """
        旧版本游戏的存档里的 AI 设置对象缺少部分字段且带有非 Ai_Setting 字段 now_ai_chat_api_endpoint 时，
        load_ai 对缺失字段保留默认值并忽略多余字段。已有选项被保留并写进 settings.json。
        """
        older = game_type.Ai_Setting()
        del older.send_data_flags, older.ai_chat_translator_setting
        del older.now_ai_chat_base_url, older.now_ai_chat_proxy
        vars(older)["now_ai_chat_api_endpoint"] = "http://old.test"
        older.ai_chat_setting.update({1: 1, 5: "test-model"})
        self.load_ai(older)
        expected = game_type.Ai_Setting()
        expected.ai_chat_setting.update({1: 1, 5: "test-model"})
        self.assertEqual(vars(normal_config.ai_setting), vars(filled(expected)))
        self.assertEqual(self.on_disk()["ai_chat_setting"]["5"], "test-model")

    def test_load_takes_and_fills(self) -> None:
        """
        save_handle.update_settings 处理带 "ai_setting" 的旧版本游戏的存档字典并经 finish_load 完成读档后，
        字典已弹出该键，全局 AI 设置收下已有选项并把缺失选项补为 0。
        """
        older = game_type.Ai_Setting()
        older.ai_chat_setting.update({1: 1, 5: "test-model"})
        loaded = {"ai_setting": older}
        kernel_data.written(save_handle.update_settings, loaded)
        self.finish_load()
        ai_chat_setting = normal_config.ai_setting.ai_chat_setting
        self.assertNotIn("ai_setting", loaded)
        self.assertEqual(
            set(ai_chat_setting), set(game_config.config_ai_chat_setting)
        )
        self.assertEqual(
            (ai_chat_setting[1], ai_chat_setting[5], ai_chat_setting[14]),
            (1, "test-model", 0),
        )

    def test_load_without_ai_setting(self) -> None:
        """
        save_handle.update_settings 处理不含 "ai_setting" 的存档字典并经 finish_load 完成读档后，
        全局保留已有的模型名、补全缺失选项并写进 settings.json。
        """
        settings.install()
        normal_config.ai_setting.ai_chat_setting[5] = "test-model"
        kernel_data.written(save_handle.update_settings, {})
        self.finish_load()
        ai_chat_setting = normal_config.ai_setting.ai_chat_setting
        self.assertEqual(
            set(ai_chat_setting), set(game_config.config_ai_chat_setting)
        )
        self.assertEqual(ai_chat_setting[5], "test-model")
        self.assertEqual(self.on_disk()["ai_chat_setting"]["5"], "test-model")

    def test_default_not_written(self) -> None:
        """
        修改系统设置并读入不含 AI 设置的存档后，settings.json 不含 "ai_setting" 段。
        新进程里读入旧存档时仍能收下其 AI 设置。
        """
        settings.install()
        normal_config.system_setting.line_before_main_update = 5
        self.load_ai(None)
        with open(self.path, encoding="utf-8") as setting_file:
            self.assertNotIn("ai_setting", json.load(setting_file))
        self.fresh_process()
        self.load_ai(chosen_ai())
        self.assertEqual(
            vars(normal_config.ai_setting), vars(filled(chosen_ai()))
        )

    def test_choice_kept_in_process(self) -> None:
        """同进程里已改过但尚未落盘的自定义接口地址，在读入含其他 AI 设置的旧存档后保持不变。"""
        settings.install()
        normal_config.ai_setting.now_ai_chat_base_url = "http://local.test/v1"
        self.load_ai(chosen_ai())
        self.assertEqual(
            normal_config.ai_setting.now_ai_chat_base_url,
            "http://local.test/v1",
        )

    def test_first_load_takes_system_setting(self) -> None:
        """
        尚无 settings.json 时，先对旧存档调用 adopt_ai 再调用 adopt，
        旧存档的 line_before_main_update（5）仍能成为全局设置。
        """
        older = game_type.System_Setting()
        older.line_before_main_update = 5
        settings.adopt_ai(chosen_ai())
        settings.adopt(older, {})
        self.assertEqual(
            normal_config.system_setting.line_before_main_update, 5
        )

    def test_failed_load_drops(self) -> None:
        """
        adopt_ai 为旧存档准备好 AI 设置后，无论 Reset 在输入钩子（设置钩子前）还是设置钩子后的输出钩子失败，
        下一次成功 Reset 后全局 AI 设置仍为默认值，且不生成 settings.json。
        """
        toy = Toy()
        fail_at: list[str] = []

        @toy.input_hook(core.reset)
        def load(
            new: core.GameState, why: core.Data
        ) -> tuple[core.GameState, core.Data]:
            if fail_at:
                settings.adopt_ai(chosen_ai())
            if fail_at == ["input"]:
                raise RuntimeError("load failed")
            return (new, why)

        @toy.output_hook(core.reset)
        def late(game: core.GameState) -> core.GameState:
            if fail_at == ["output"]:
                raise RuntimeError("load failed")
            return game

        core.load((settings, toy.module))
        settings.install()
        for point in ("input", "output"):
            with self.subTest(point):
                fail_at[:] = [point]
                with self.assertRaisesRegex(RuntimeError, "load failed"):
                    self.finish_load()
                fail_at.clear()
                core.reset_state(empty_game())
                self.assertEqual(
                    vars(normal_config.ai_setting), vars(game_type.Ai_Setting())
                )
                self.assertFalse(os.path.exists(self.path))

    def test_abort_after_swap_commits(self) -> None:
        """reset_state 换掉内核状态后再抛出中止（模拟选行动中读档）时，暂存的 AI 设置仍会生效并写进 settings.json。"""

        class Aborted(BaseException):
            """模拟选行动中读档在内核状态切换后抛出的中止异常"""

        swap = core.reset_state

        def swap_then_abort(
            new: core.GameState, why: core.Data = MappingProxyType({})
        ) -> None:
            swap(new, why)
            raise Aborted

        settings.adopt_ai(chosen_ai())
        with mock.patch.object(core, "reset_state", swap_then_abort):
            with self.assertRaises(Aborted):
                self.finish_load()
        self.assertEqual(
            vars(normal_config.ai_setting), vars(filled(chosen_ai()))
        )
        self.assertEqual(self.on_disk()["now_ai_chat_model"], "test-model")


class FilledOptions(AiSettingTestCase):
    """验证缺失 AI 选项的补全与更新提示行为"""

    def test_new_save_silent(self) -> None:
        """读入不含 AI 设置的存档时返回 0（无更新提示），且不向 settings.json 写入 "ai_setting" 段。"""
        self.assertEqual(self.load_ai(None), 0)
        self.assertFalse(self.has_section())

    def test_default_old_save_silent(self) -> None:
        """
        读入带默认 AI 设置的旧存档时返回 0 且不写入 "ai_setting" 段。
        新进程里再次读入同样返回 0 且不写段。
        """
        self.assertEqual(self.load_ai(game_type.Ai_Setting()), 0)
        self.assertFalse(self.has_section())
        self.fresh_process()
        self.assertEqual(self.load_ai(game_type.Ai_Setting()), 0)
        self.assertFalse(self.has_section())

    def test_chosen_old_save_once(self) -> None:
        """
        读入设了 1 号与 5 号选项的旧存档时返回其余缺失选项数，并把全部选项写进 settings.json。
        之后的同进程读档与新进程读档均返回 0。
        """
        older = game_type.Ai_Setting()
        older.ai_chat_setting.update({1: 1, 5: "test-model"})
        ids = game_config.config_ai_chat_setting
        self.assertEqual(self.load_ai(older), len(ids) - 2)
        self.assertEqual(
            set(self.on_disk()["ai_chat_setting"]), {str(cid) for cid in ids}
        )
        self.assertEqual(self.load_ai(older), 0)
        self.fresh_process()
        self.assertEqual(self.load_ai(older), 0)

    def test_partial_file_filled(self) -> None:
        """
        settings.json 的 "ai_setting" 段只含 1 号选项时，新游戏 Reset 后全部选项均存在，
        1 号保持为 1，2 号补为 0。
        """
        with open(self.path, "w", encoding="utf-8") as setting_file:
            json.dump(
                {"ai_setting": {"ai_chat_setting": {"1": 1}}}, setting_file
            )
        core.reset_state(empty_game())
        ai_chat_setting = normal_config.ai_setting.ai_chat_setting
        self.assertEqual(
            set(ai_chat_setting), set(game_config.config_ai_chat_setting)
        )
        self.assertEqual((ai_chat_setting[1], ai_chat_setting[2]), (1, 0))
