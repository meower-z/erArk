# -*- coding: UTF-8 -*-
"""
存档内核状态编码：Fraction 标签与旧存档校验标记
===============================================
- Fraction（96 位分子、88 位分母，以及分母为 1 的）写进 save.json 再读回，值与类型不变。int 读回仍是 int。
- {"$frac": [3, 4]} 与带 "$frac" 的两键映射原样读回。只有一个键 "$frac" 且值是字符串的映射不能写。
- 进行中的玩家行动带着标签样本与选择时的写入，写进 save.json 再读回不变。
- 旧存档头有标记时，文件 "2" 缺失、截断、标记不同或版本过高都抛 SaveRefused，不当版本 0 读。
- 版本 1 的旧存档文件 "2" 读回时升到当前版本：角色数据与 roster.offstage 里的每份 body.needs 补上体力、气力、
  理智与它们的上限，愤怒、熟睡、欲望、醉酒，都取默认值 0，原有的项不变。
存档都写在临时目录里（index.SAVE_DIR 换成它）。
"""

import os
import tempfile
from fractions import Fraction
from types import MappingProxyType
from unittest import mock

from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions
from Script.Modules.save_load import index, kernel_state, upgrade
from tests import legacy_save
from tests.fast.base import FastTestCase

SAVE_ID = "save_codec_test"
""" 测试用的存档id """
BIG = Fraction(3**60 + 1, 2**88 - 1)
""" 96 位分子、88 位分母的 Fraction """


def state(data: dict[str, core.JSON]) -> core.GameState:
    """
    内核换成时钟 100、只有玩家的状态。玩家的行动带着标签样本与选择时的写入，
    玩家数据里有生理需求，全局数据是 data
    Keyword arguments:
    data -- 全局数据
    Return arguments:
    GameState -- 换入后的状态
    """
    act = core.Action(
        "0",
        actions.behave.name,
        {
            "behavior_id": "wait",
            "minutes": 5,
            "tags": ((("a", "x"), {"$frac": (3, 4)}, {"$frac": (1, 2)}),),
            "effects": (
                {
                    "who": "0",
                    "key": "body.needs",
                    "op": "add",
                    "operand": {"stat": "tired", "by": Fraction(7, 72)},
                },
                {
                    "who": None,
                    "key": "base.power_strategy",
                    "old": None,
                    "new": {"4": 1},
                },
            ),
        },
        100,
        5,
    )
    player = core.Character(
        act,
        {"body.needs": {"tired": BIG, "urine": Fraction(3, 1), "hunger": 12}},
    )
    core.reset_state(core.GameState(100, MappingProxyType({"0": player}), data))
    return core.state()


class SaveCodecTest(FastTestCase):
    """存档内核状态的编码与旧存档读档前检查"""

    def setUp(self) -> None:
        """存档写进临时目录"""
        super().setUp()
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", folder))

    def write(self) -> None:
        """把内核状态写入测试槽位的 save.json，存档头含游戏时间与存档时间"""
        when = "2026-06-01T08:00:00"
        kernel_state.write(SAVE_ID, {"game_time": when, "save_time": when})

    def test_round_trip_keeps_values_and_types(self) -> None:
        """Fraction、分母为 1 的 Fraction、int、值为元组的 "$frac" 与带 "$frac" 的两键映射读回不变"""
        saved = state({"two": {"$frac": "1/2", "n": 1}, "big": -BIG})
        self.write()
        loaded, version = kernel_state.read(SAVE_ID)
        self.assertEqual(version, upgrade.CURRENT)
        self.assertTrue(loaded == saved, "读回的状态与写下的相等")
        assert loaded is not None
        needs = loaded.characters["0"].data["body.needs"]
        assert isinstance(needs, MappingProxyType)
        self.assertEqual(
            {k: type(v) for k, v in needs.items()},
            {"tired": Fraction, "urine": Fraction, "hunger": int},
        )

    def test_literal_tag_is_refused(self) -> None:
        """只有一个键 "$frac"、值是字符串的映射读回会变成 Fraction，所以写的时候报 TypeError"""
        with self.assertRaisesRegex(TypeError, "reads back as a Fraction"):
            kernel_state.encode(state({"tag": {"$frac": "1/2"}}))

    def test_broken_files_are_refused(self) -> None:
        """
        存档头带标记的旧槽位中，文件 "2" 截断、标记不符、缺失或版本过高都抛 SaveRefused 且消息含槽位名
        """
        path = index.file(SAVE_ID, kernel_state.LEGACY_FILE)
        state({})
        self.write()
        legacy_save.to_legacy(SAVE_ID, legacy_save.old("Cache"))
        with open(path, encoding="utf-8") as f:
            text = f.read()
        token = f'"{kernel_state.TOKEN}": "legacy-token"'
        self.assertIn(token, text)
        cases = {
            "truncated": text[: len(text) // 2],
            "other token": text.replace(token, f'"{kernel_state.TOKEN}": "u"'),
            "too new": text.replace(
                '"version": 27', f'"version": {upgrade.CURRENT + 1}', 1
            ),
            "missing": None,
        }
        for name, body in cases.items():
            with self.subTest(name):
                if body is None:
                    os.remove(path)
                else:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(body)
                with self.assertRaisesRegex(index.SaveRefused, SAVE_ID):
                    kernel_state.read(SAVE_ID)

    def test_version_1_gains_the_new_stats(self) -> None:
        """版本 1 的文件读回后版本为当前版本，玩家与 roster.offstage 里的 body.needs 补上十项默认值 0，原有的项不变"""
        parked: core.JSON = {
            "7": {"body.needs": {"tired": 3, "hunger": Fraction(5, 2)}}
        }
        state({"roster.offstage": parked})
        self.write()
        legacy_save.to_legacy(SAVE_ID, legacy_save.old("Cache"), version=1)
        loaded, version = kernel_state.read(SAVE_ID)
        self.assertEqual(version, upgrade.CURRENT)
        assert loaded is not None
        added = dict.fromkeys(upgrade.PICKLED_NEEDS.values(), 0)
        player = loaded.characters["0"].data["body.needs"]
        offstage = loaded.data["roster.offstage"]
        assert isinstance(player, MappingProxyType)
        assert isinstance(offstage, MappingProxyType)
        self.assertEqual(
            dict(player),
            {**added, "tired": BIG, "urine": Fraction(3, 1), "hunger": 12},
        )
        self.assertEqual(
            dict(offstage["7"]["body.needs"]),
            {**added, "tired": 3, "hunger": Fraction(5, 2)},
        )
