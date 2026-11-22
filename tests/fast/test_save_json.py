# -*- coding: UTF-8 -*-
"""
单文件存档测试（save.json）
===========================
- 存档只写出 save.json，版本为当前版本且含存档头；先对临时文件 fsync 再经 os.replace 替换，
  写入出错时保留原 save.json 不变。
- 覆盖写入旧槽位后，删除该槽位的文件 "0"、"1" 与 "2"。
- index.slots 列出 save.json 槽位及同时含 "0" 和 "1" 的旧槽位；
  index.head 读取两种槽位并给出 GameTime 与 datetime。
- 非 UTF-8 JSON、非对象、缺整型 version 或 dict 类型 head、版本高于当前版本或低于 28、
  存档头时间缺失或无效的 save.json 均抛 SaveRefused 且消息含槽位名。
- 同一存档按 save.json 与按版本 27 旧槽位读回，得到的内核状态相同。
- 读取版本 0 或版本 27 的旧槽位不修改其任何文件，也不写出 save.json。
"""

import hashlib
import json
import os
import random
import tempfile
from collections.abc import Callable
from typing import Any
from unittest import mock

from Script.Core import save_handle
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import country, playthrough, roster
from Script.Modules.save_load import index, kernel_state, upgrade
from tests import chara_projection, kernel_data, legacy_save
from tests.fast.base import FastTestCase

SLOT = "save_json_test"
""" 测试用的存档槽位 id """
SEED = 20261122
""" 每次读档前设定的随机种子（读档会为角色模板抽取随机值） """


def digests(save_id: str) -> dict[str, str]:
    """
    计算槽位目录内每个文件的 sha256 摘要
    Keyword arguments:
    save_id -- 存档id
    Return arguments:
    dict -- 文件名到 sha256 十六进制字符串
    """
    folder = index.path(save_id)
    out = {}
    for name in sorted(os.listdir(folder)):
        with open(os.path.join(folder, name), "rb") as f:
            out[name] = hashlib.sha256(f.read()).hexdigest()
    return out


class SaveJsonTest(FastTestCase):
    """save.json 槽位的写出、列举、拒绝与读档测试"""

    def setUp(self) -> None:
        """存档目录换到临时目录，准备玩家、名册、国家与本周目设定"""
        super().setUp()
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", folder))
        self.enterContext(mock.patch.object(core, "_events", []))
        self.world.chara(0, "博士")
        kernel_data.put(roster.set_active, {0})
        kernel_data.written(country.fill)
        kernel_data.written(playthrough.reset_difficulty_and_birth)

    def rewrite(self, change: Callable[[dict[str, Any]], object]) -> None:
        """
        对槽位 save.json 的 JSON 对象原地应用 change 后写回磁盘
        Keyword arguments:
        change -- 原地修改 JSON 对象的函数
        """
        path = index.file(SLOT, index.SAVE_FILE)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        change(data)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def test_save_writes_only_save_json(self) -> None:
        """槽位只含 save.json，版本为 28 且等于 upgrade.CURRENT，存档头含游戏时间与存档时间"""
        save_handle.establish_save(SLOT)
        self.assertEqual(os.listdir(index.path(SLOT)), [index.SAVE_FILE])
        data = index.document(SLOT)
        self.assertEqual((data["version"], upgrade.CURRENT), (28, 28))
        self.assertNotIn(kernel_state.TOKEN, data)
        head = index.head(SLOT)
        self.assertEqual(
            set(head),
            {"game_verson", "game_time", "character_name", "save_time"},
        )
        self.assertIs(type(head["game_time"]), game_time.GameTime)
        self.assertEqual(head["game_time"], game_time.now())
        self.assertEqual(head["character_name"], "博士")

    def test_write_syncs_before_replace(self) -> None:
        """先对临时文件调用 os.fsync 再经 os.replace 替换为 save.json，不遗留临时文件"""
        calls: list[str] = []
        real_fsync, real_replace = os.fsync, os.replace

        def fsync(fd: int) -> None:
            calls.append("fsync")
            real_fsync(fd)

        def replace(src: str, dst: str) -> None:
            calls.append(f"replace {os.path.basename(src)}")
            real_replace(src, dst)

        with (
            mock.patch.object(os, "fsync", fsync),
            mock.patch.object(os, "replace", replace),
        ):
            kernel_state.write(SLOT, {})
        self.assertEqual(calls, ["fsync", f"replace {index.SAVE_FILE}.tmp"])
        self.assertEqual(os.listdir(index.path(SLOT)), [index.SAVE_FILE])

    def test_failed_write_keeps_old_save(self) -> None:
        """写出过程中抛错时，原有 save.json 逐字节保持不变"""
        save_handle.establish_save(SLOT)
        before = digests(SLOT)[index.SAVE_FILE]

        def broken(*args: object, **kwargs: object) -> None:
            raise OSError("disk full")

        with mock.patch.object(kernel_state.json, "dump", broken):
            with self.assertRaises(OSError):
                kernel_state.write(SLOT, {})
        self.assertEqual(digests(SLOT), {index.SAVE_FILE: before})

    def test_save_over_old_slot_removes_old_files(self) -> None:
        """向旧槽位存档后，槽位内只剩 save.json"""
        save_handle.establish_save(SLOT)
        legacy_save.to_legacy(SLOT, legacy_save.old("Cache"))
        self.assertEqual(sorted(os.listdir(index.path(SLOT))), ["0", "1", "2"])
        save_handle.establish_save(SLOT)
        self.assertEqual(os.listdir(index.path(SLOT)), [index.SAVE_FILE])

    def test_slots_and_heads_of_both_layouts(self) -> None:
        """index.slots 列出 save.json 与含 "0"/"1" 的旧槽位，排除仅含 "0" 的目录，且两者存档头一致"""
        save_handle.establish_save("a")
        save_handle.establish_save("b")
        head = index.head("b")
        legacy_save.to_legacy("b", legacy_save.old("Cache"))
        legacy_save.write_head("c", {})
        self.assertEqual(index.slots(), ["a", "b"])
        old_head = index.head("b")
        old_head.pop(kernel_state.TOKEN)
        self.assertEqual(old_head, head)
        self.assertIs(type(old_head["save_time"]), type(head["save_time"]))

    def test_broken_save_json_is_refused(self) -> None:
        """各类损坏的 save.json 在 read、head 或两者中均抛 SaveRefused 且消息含槽位名"""
        save_handle.establish_save(SLOT)
        path = index.file(SLOT, index.SAVE_FILE)
        with open(path, "rb") as f:
            good = f.read()
        current = upgrade.CURRENT
        cases: dict[str, Callable[[dict[str, Any]], object]] = {
            "no version": lambda d: d.pop("version"),
            "str version": lambda d: d.update(version="28"),
            "bool version": lambda d: d.update(version=True),
            "too new": lambda d: d.update(version=current + 1),
            "too old": lambda d: d.update(version=27),
            "no head": lambda d: d.pop("head"),
            "head list": lambda d: d.update(head=[]),
            "no characters": lambda d: d.pop("characters"),
        }
        for name, change in cases.items():
            with self.subTest(name):
                with open(path, "wb") as f:
                    f.write(good)
                self.rewrite(change)
                with self.assertRaisesRegex(index.SaveRefused, SLOT):
                    kernel_state.read(SLOT)
        for name, body in (
            ("list", b"[]"),
            ("truncated", good[: len(good) // 2]),
            ("not utf-8", b"\xff" + good),
        ):
            with self.subTest(name):
                with open(path, "wb") as f:
                    f.write(body)
                with self.assertRaisesRegex(index.SaveRefused, SLOT):
                    kernel_state.read(SLOT)
                with self.assertRaisesRegex(index.SaveRefused, SLOT):
                    index.head(SLOT)
        for name, change in (
            ("no game time", lambda d: d["head"].pop("game_time")),
            ("bad save time", lambda d: d["head"].update(save_time="x")),
            ("int game time", lambda d: d["head"].update(game_time=5)),
        ):
            with self.subTest(name):
                with open(path, "wb") as f:
                    f.write(good)
                self.rewrite(change)
                with self.assertRaisesRegex(index.SaveRefused, SLOT):
                    index.head(SLOT)

    def test_too_new_save_is_not_loaded(self) -> None:
        """读取版本高于当前版本的 save.json 抛 SaveRefused 且内核状态保持不变"""
        save_handle.establish_save(SLOT)
        self.rewrite(lambda d: d.update(version=upgrade.CURRENT + 1))
        before = core.state()
        with self.assertRaisesRegex(index.SaveRefused, SLOT):
            save_handle.input_load_save(SLOT)
        self.assertIs(core.state(), before)

    def test_json_load_matches_old_load(self) -> None:
        """
        同一份存档分别以 save.json 与版本 27 旧槽位读取，在相同随机种子下得到相等的内核状态
        """
        difficulty = playthrough.DIFFICULTY
        kernel_data.set_world(playthrough.set_setting, difficulty, 1, 3)
        save_handle.establish_save(SLOT)
        kernel_data.set_world(playthrough.set_setting, difficulty, 1, 1)
        random.seed(SEED)
        save_handle.input_load_save(SLOT)
        from_json = core.state()
        self.assertEqual(playthrough.setting(difficulty, 1), 3)
        legacy_save.to_legacy(SLOT, legacy_save.old("Cache"))
        kernel_data.set_world(playthrough.set_setting, difficulty, 1, 1)
        random.seed(SEED)
        save_handle.input_load_save(SLOT)
        self.assertTrue(core.state() == from_json, "两种存档读回的状态相同")

    def test_old_slots_load_read_only(self) -> None:
        """
        读取版本 27 与版本 0 的旧槽位均不修改其任何文件，也不写出 save.json
        """
        save_handle.establish_save(SLOT)
        head = index.head(SLOT)
        legacy_save.to_legacy(SLOT, legacy_save.old("Cache"))
        before = digests(SLOT)
        save_handle.input_load_save(SLOT)
        self.assertEqual(digests(SLOT), before)
        os.remove(index.file(SLOT, kernel_state.LEGACY_FILE))
        legacy_save.write_head(SLOT, head)
        cache = legacy_save.old(
            "Cache",
            npc_id_got=roster.active(),
            forbidden_npc_id=roster.forbidden(),
            npc_name_data=roster.names(),
            character_data=chara_projection.pickled_characters(),
        )
        legacy_save.write_cache(SLOT, cache)
        before = digests(SLOT)
        self.assertEqual(kernel_state.read(SLOT), (None, 0))
        save_handle.input_load_save(SLOT)
        self.assertEqual(digests(SLOT), before)
        self.assertEqual(sorted(before), ["0", "1"])
