# -*- coding: UTF-8 -*-
"""
新游戏存进当前版本，再读再存
============================
开新游戏（SlowTestCase.setUp），存档目录换成临时目录。
- 等待 60 分钟，在动力系统管理面板里把一个区块的供电策略调高一档，存进新存档：文件 "2" 里有 Fraction 的标签。
  读回这个存档，内核状态的 JSON 与存档前相同。
- 存档之后接着玩 60 分钟，与读回存档后接着玩 60 分钟（随机数同样重设）比较：内核状态、花名册顺序、
  全部角色的生理需求、开始的行动序列与随机数状态都相同。
- 读回后再存一次，文件 "2" 除了存档标记都与上一次相同。再读一次，内核状态与存档前相同，缓存的 JSON 与第一次读回时相同。
- 文件 "2" 截断或换成另一次存档的，读档抛 SaveRefused，错误里有存档id。
"""

import hashlib
import importlib
import json
import os
import random
import tempfile
from typing import TYPE_CHECKING, Any
from unittest import mock

from tests.slow.base import SlowTestCase

if TYPE_CHECKING:
    from Script.Kernel import core

SLOT = "v1"
""" 测试写的存档id """
SEED = 20261120
""" 接着玩之前重设的随机种子 """
STATS = ("tired", "hunger", "urine", "milk")
""" 生理需求的各项 """


def game(name: str) -> Any:
    """
    游戏启动之后再导入游戏模块
    Keyword arguments:
    name -- 模块名
    Return arguments:
    Any -- 模块
    """
    return importlib.import_module(name)


class SaveV1Test(SlowTestCase):
    """新游戏的存、读与接着玩"""

    time_limit = 900

    def setUp(self) -> None:
        """开新游戏（SlowTestCase.setUp），存档目录换成临时目录，记下内核开始的每个行动"""
        super().setUp()
        index = game("Script.Modules.save_load.index")
        kernel = game("Script.Kernel.core")
        self.folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", self.folder))
        self.started: list[tuple[int, str, str]] = []
        saved = kernel._bodies["kernel.StartAction"]

        def spy(act: "core.Action") -> "core.Effects":
            self.started.append((kernel.state().clock, act.who, act.action_id))
            return saved(act)

        kernel._bodies["kernel.StartAction"] = spy
        self.addCleanup(kernel._bodies.__setitem__, "kernel.StartAction", saved)

    def load(self, save_id: str) -> None:
        """
        读档，回到场景面板，载入插件
        Keyword arguments:
        save_id -- 存档id
        """
        constant = game("Script.Core.constant")
        save_handle = game("Script.Core.save_handle")
        kernel = game("Script.Kernel.core")
        load_order = game("Script.Modules.load_order")
        save_handle.input_load_save(save_id)
        self.cache.now_panel_id = constant.Panel.IN_SCENE
        kernel.load(load_order.LOAD_ORDER)

    def wait(self, minutes: int) -> None:
        """
        玩家每次选行动都等待，内核推进 minutes 分钟
        Keyword arguments:
        minutes -- 分钟数
        """
        constant = game("Script.Core.constant")
        kernel = game("Script.Kernel.core")
        player_pick = game("Script.Modules.tk_ui.player_pick")
        handle_instruct = game("Script.System.Instruct_System.handle_instruct")

        def wait() -> None:
            handle_instruct.handle_instruct(constant.Instruct.WAIT)

        start = kernel.state().clock
        with mock.patch.object(player_pick, "chooser", wait):
            while kernel.state().clock < start + minutes:
                kernel.step()

    def state_json(self) -> str:
        """
        内核此刻的状态按文件 "2" 的编码换成排好键的 JSON，存档标记固定
        Return arguments:
        str -- JSON 文本
        """
        kernel = game("Script.Kernel.core")
        kernel_state = game("Script.Modules.save_load.kernel_state")
        return json.dumps(
            kernel_state.encode(kernel.state(), "fixed"), sort_keys=True
        )

    def cache_json(self) -> str:
        """
        缓存的属性（全局设置除外）按草稿的编码换成排好键的 JSON
        Return arguments:
        str -- JSON 文本
        """
        draft = game("Script.Modules.gameplay_resolution.draft")
        attrs = {
            name: draft.encode(value)
            for name, value in sorted(vars(self.cache).items())
            if name != "all_system_setting"
        }
        return json.dumps(attrs, sort_keys=True, ensure_ascii=False)

    def digest(self) -> tuple[object, ...]:
        """
        接着玩之后比较的五项：内核状态的 JSON、花名册顺序、全部角色的生理需求、开始的行动序列、随机数状态的 sha256
        Return arguments:
        tuple -- 各项
        """
        kernel = game("Script.Kernel.core")
        needs = game("Script.Modules.domains.needs")
        stats = repr(
            [
                (cid, [needs.of(cid)[k] for k in STATS])
                for cid in sorted(self.cache.character_data)
            ]
        )
        rng = hashlib.sha256(repr(random.getstate()).encode()).hexdigest()
        return (
            self.state_json(),
            tuple(kernel.state().characters),
            stats,
            tuple(self.started),
            rng,
        )

    def test_save_load_and_continue(self) -> None:
        """存进新存档后读回与存档前相同，存档后接着玩与读回后接着玩相同，再存再读不变"""
        constant = game("Script.Core.constant")
        save_handle = game("Script.Core.save_handle")
        world = game("tests.world")
        kernel_state = game("Script.Modules.save_load.kernel_state")
        power = game("Script.Modules.domains.power")
        self.wait(60)
        strategies = power.strategies()
        self.cache.now_panel_id = constant.Panel.MANAGE_POWER_SYSTEM
        self.world.player.press("供电策略调整", "[+]", "返回", "返回")
        world.act(constant.panel_data[self.cache.now_panel_id])
        self.world.player.check_done()
        self.assertNotEqual(power.strategies(), strategies, "面板里改了策略")
        before_save = self.state_json()
        save_handle.establish_save(SLOT)
        path = os.path.join(self.folder, SLOT, kernel_state.SAVE_FILE)
        with open(path, encoding="utf-8") as f:
            first_file = json.load(f)
        self.assertIn('"$frac"', json.dumps(first_file), "文件 2 里有 Fraction")

        random.seed(SEED)
        self.started.clear()
        self.wait(60)
        played = self.digest()
        self.assertGreater(
            len(self.started), 12, "接着玩的 60 分钟里开始了行动"
        )

        self.load(SLOT)
        self.assertTrue(
            self.state_json() == before_save, "读回的内核状态与存档前相同"
        )
        first_cache = self.cache_json()
        random.seed(SEED)
        self.started.clear()
        self.wait(60)
        replayed = self.digest()
        same = [a == b for a, b in zip(played, replayed, strict=True)]
        self.assertEqual(
            same, [True] * 5, "（内核状态，花名册，生理需求，行动序列，随机数）"
        )

        self.load(SLOT)
        save_handle.establish_save(SLOT)
        with open(path, encoding="utf-8") as f:
            second_file = json.load(f)
        for data in (first_file, second_file):
            data.pop(kernel_state.TOKEN)
        self.assertTrue(second_file == first_file, "再存一次，文件 2 不变")
        self.load(SLOT)
        self.assertTrue(self.state_json() == before_save)
        self.assertTrue(self.cache_json() == first_cache, "两次读回的缓存相同")

    def test_broken_v1_slots_are_refused(self) -> None:
        """存档头有标记的存档：文件 "2" 截断或换成另一次存档的，读档抛 SaveRefused，错误里有存档id，不当旧存档读"""
        save_handle = game("Script.Core.save_handle")
        kernel_state = game("Script.Modules.save_load.kernel_state")
        save_handle.establish_save(SLOT)
        save_handle.establish_save("other")
        path = os.path.join(self.folder, SLOT, kernel_state.SAVE_FILE)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        with open(
            os.path.join(self.folder, "other", "2"), encoding="utf-8"
        ) as f:
            other = f.read()
        for body in (text[: len(text) // 2], other):
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)
            with self.assertRaisesRegex(kernel_state.SaveRefused, SLOT):
                save_handle.input_load_save(SLOT)
