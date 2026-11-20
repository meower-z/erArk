# -*- coding: UTF-8 -*-
"""
存档文件 "2" 的编码：Fraction 的标签与存档头的标记
==================================================
- Fraction（96 位分子、88 位分母，以及分母为 1 的）写进文件再读回，值与类型不变。int 读回仍是 int。
- 草稿那种 {"$frac": [3, 4]} 与带 "$frac" 的两键映射原样读回。只有一个键 "$frac" 且值是字符串的映射不能写。
- 进行中的玩家行动带着草稿与选择时的写入，写进文件再读回不变。
- 存档头有标记时，文件 "2" 缺失、截断、标记不同或版本过高都拒绝读档，不当旧存档读。
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
from tests.fast.base import FastTestCase

SAVE_ID = "save_codec_test"
""" 测试用的存档id """
BIG = Fraction(3**60 + 1, 2**88 - 1)
""" 96 位分子、88 位分母的 Fraction """


def state(data: dict[str, core.JSON]) -> core.GameState:
    """
    内核换成时钟 100、只有玩家的状态。玩家的行动带着草稿与选择时的写入，玩家数据里有生理需求，全局数据是 data
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
            "draft": ((("a", "x"), {"$frac": (3, 4)}, {"$frac": (1, 2)}),),
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
    """文件 "2" 的编码与读档前的检查"""

    def setUp(self) -> None:
        """存档写进临时目录"""
        super().setUp()
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", folder))

    def write(self, token: str = "t") -> None:
        """
        把内核此刻的状态写成存档头带标记 token 的存档
        Keyword arguments:
        token -- 本次存档的标记
        """
        index.write_head(SAVE_ID, {kernel_state.TOKEN: token})
        kernel_state.write(SAVE_ID, token)

    def test_round_trip_keeps_values_and_types(self) -> None:
        """Fraction、分母为 1 的 Fraction、int、草稿的标签与带 "$frac" 的两键映射读回不变"""
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
            kernel_state.encode(state({"tag": {"$frac": "1/2"}}), "t")

    def test_broken_files_are_refused(self) -> None:
        """存档头有标记时，文件 "2" 截断、标记不同、缺失或版本过高都抛 SaveRefused，错误里有存档id"""
        path = os.path.join(index.path(SAVE_ID), kernel_state.SAVE_FILE)
        state({})
        self.write()
        with open(path, encoding="utf-8") as f:
            text = f.read()
        cases = {
            "truncated": text[: len(text) // 2],
            "other token": text.replace('"t"', '"u"', 1),
            "too new": text.replace('"version": 1', '"version": 2', 1),
            "missing": None,
        }
        for name, body in cases.items():
            with self.subTest(name):
                if body is None:
                    os.remove(path)
                else:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(body)
                with self.assertRaisesRegex(kernel_state.SaveRefused, SAVE_ID):
                    kernel_state.read(SAVE_ID)
