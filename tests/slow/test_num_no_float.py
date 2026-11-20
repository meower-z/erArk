# -*- coding: UTF-8 -*-
"""
连续数值从不为浮点
==================
读用户存档 99（不入库，装在 save/99 时才跑，没装时报跳过），玩家每次选行动都等待五分钟，内核推进 3 个游戏小时。
每一步之后，每个角色的每个连续数值（Num：体力、气力、理智、射精欲、精液、疲劳、尿意、饥饿、困倦、醉酒、各状态值、
身体各部位的当前精液量、累计吸收精液量、精液流通的剩余量、乳汁量、当日理智消耗）都是 int 或 Fraction，
Fraction 的分母都小于 2**64。

结算效果（Settle/default.py、Second_effect.py、item_effect.py 里登记的行为效果与二段行为效果）逐个结算一次：
开新游戏，博士与同一处的一名干员互为交互对象，两人的每个连续数值先设为 n + 1/3
（生成临时外勤委托会追加写入 data/csv/Commission.csv，换成不做事的替身）。
结算之后两人的连续数值仍都是 int 或分母有界的 Fraction，
也没有效果因为 Fraction 抛错（只收整数的地方收到了 Fraction）。
"""

import importlib
from collections.abc import Iterator
from fractions import Fraction
import os
from typing import TYPE_CHECKING
from unittest import mock

from tests.slow.base import SlowTestCase

if TYPE_CHECKING:
    from Script.Core import game_type

EFFECT_MODULES = frozenset(
    {
        "Script.Settle.default",
        "Script.Settle.Second_effect",
        "Script.Settle.item_effect",
    }
)
""" 要逐个结算的效果所在的模块 """
THIRD = Fraction(1, 3)
""" 加在每个连续数值上的零头 """

USER_SAVE_ID = "99"
""" 用户存档的存档id（不入库，装在 save/99） """
MINUTES = 180
""" 推进的游戏分钟数 """
DENOMINATOR_LIMIT = 2**64
""" 分母的上限（不含） """
PLAIN = (
    "hit_point",
    "mana_point",
    "sanity_point",
    "eja_point",
    "semen_point",
    "sleep_point",
    "drunk_point",
)
""" 角色上直接存放的连续数值 """


def num_fields(
    character: "game_type.Character",
) -> Iterator[tuple[str, object]]:
    """
    列出一个角色的全部连续数值，含 GameState 里的生理需求（body.needs）
    Keyword arguments:
    character -- 角色数据（game_type.Character）
    Return arguments:
    Iterator[tuple[str, object]] -- (数值路径, 值)
    """
    needs = importlib.import_module("Script.Modules.domains.needs")
    for name in PLAIN:
        yield name, getattr(character, name)
    for stat, value in needs.of(character.cid).items():
        yield f"needs.{stat}", value
    for status_id, value in character.status_data.items():
        yield f"status_data[{status_id}]", value
    dirty = character.dirty
    for part, slot in dirty.body_semen.items():
        yield f"dirty.body_semen[{part}][1]", slot[1]
    yield "dirty.absorbed_total_semen", dirty.absorbed_total_semen
    for i, flow in enumerate(dirty.semen_flow):
        for j, target in enumerate(flow.get("targets", [])):
            yield (
                f"dirty.semen_flow[{i}].targets[{j}].remaining_volume",
                target["remaining_volume"],
            )
    yield "pl_ability.today_sanity_point_cost", (
        character.pl_ability.today_sanity_point_cost
    )


def set_thirds(character: "game_type.Character") -> None:
    """
    把一个角色的每个连续数值与生理需求设为一个整数加 1/3（整数取当前值，不小于 1）
    Keyword arguments:
    character -- 角色数据（game_type.Character）
    Return arguments:
    无
    """
    for name in PLAIN:
        setattr(character, name, max(int(getattr(character, name)), 1) + THIRD)
    for status_id, value in character.status_data.items():
        character.status_data[status_id] = max(int(value), 1) + THIRD
    for slot in character.dirty.body_semen.values():
        slot[1] = max(int(slot[1]), 1) + THIRD
    needs = importlib.import_module("Script.Modules.domains.needs")
    stats = needs.of(character.cid)
    needs.set(
        character.cid, **{k: max(int(v), 1) + THIRD for k, v in stats.items()}
    )


def wrong(value: object) -> bool:
    """
    值不是 int 或 Fraction，或者是分母过大的 Fraction
    Keyword arguments:
    value -- 数值
    Return arguments:
    bool -- 不合规则时为 True
    """
    if isinstance(value, bool) or not isinstance(value, int | Fraction):
        return True
    return (
        isinstance(value, Fraction) and value.denominator >= DENOMINATOR_LIMIT
    )


class NumNoFloatTest(SlowTestCase):
    """存档 99 推进 3 个小时，每一步之后连续数值都是 int 或分母有界的 Fraction"""

    time_limit = 600

    def test_three_hours_from_save_99(self) -> None:
        """读档后玩家一直等待：每一步之后没有浮点、没有分母过大的连续数值"""
        from Script.UI.Moudle import view

        constant = importlib.import_module("Script.Core.constant")
        save_handle = importlib.import_module("Script.Core.save_handle")
        core = importlib.import_module("Script.Kernel.core")
        load_order = importlib.import_module("Script.Modules.load_order")
        player_pick = importlib.import_module(
            "Script.Modules.tk_ui.player_pick"
        )
        handle_instruct = importlib.import_module(
            "Script.System.Instruct_System.handle_instruct"
        )

        if not os.path.isdir(os.path.join("save", USER_SAVE_ID)):
            self.skipTest("用户存档 99 没装在 save/99")
        save_handle.input_load_save(USER_SAVE_ID)
        view.now_panel_id = constant.Panel.IN_SCENE
        core.load(load_order.LOAD_ORDER)

        def wait() -> None:
            """玩家每次选行动都等待"""
            handle_instruct.handle_instruct(constant.Instruct.WAIT)

        found: dict[tuple[int, str], str] = {}
        start = core.state().clock
        steps = 0
        with mock.patch.object(player_pick, "chooser", wait):
            while core.state().clock < start + MINUTES:
                core.step()
                steps += 1
                for cid, character in self.cache.character_data.items():
                    for path, value in num_fields(character):
                        if wrong(value) and (cid, path) not in found:
                            found[cid, path] = (
                                f"{type(value).__name__} {value!r:.40} "
                                f"at minute {core.state().clock - start}"
                            )
        self.assertGreater(steps, MINUTES // 5)
        self.assertEqual(
            [f"{cid} {path}: {what}" for (cid, path), what in found.items()],
            [],
        )

    def test_every_settle_effect_keeps_fractions(self) -> None:
        """两人的连续数值带 1/3 零头时，每个结算效果结算之后都没有浮点"""
        constant = importlib.import_module("Script.Core.constant")
        game_type = importlib.import_module("Script.Core.game_type")
        game_time = importlib.import_module("Script.Design.game_time")
        field_commission_function = importlib.import_module(
            "Script.System.Field_Commission_System.field_commission_function"
        )

        player = self.cache.character_data[0]
        operator_id = min(cid for cid in self.cache.npc_id_got if cid != 0)
        operator = self.cache.character_data[operator_id]
        operator.position = list(player.position)
        player.target_character_id = operator_id
        operator.target_character_id = 0
        effects = [
            (f"{kind}{effect_id}", effect, second)
            for kind, table, second in (
                ("effect ", constant.settle_behavior_effect_data, False),
                ("second ", constant.settle_second_behavior_effect_data, True),
            )
            for effect_id, effect in sorted(table.items())
            if effect.__wrapped__.__module__ in EFFECT_MODULES
        ]
        self.assertGreater(len(effects), 100)
        found: dict[tuple[str, int, str], str] = {}
        raised: dict[str, str] = {}
        no_csv_write = mock.patch.object(
            field_commission_function, "create_temp_commission"
        )
        no_csv_write.start()
        self.addCleanup(no_csv_write.stop)
        core = importlib.import_module("Script.Kernel.core")
        working = importlib.import_module(
            "Script.Modules.gameplay_resolution.working"
        )
        self.enterContext(working.based_on(core.state()))
        for name, effect, second in effects:
            set_thirds(player)
            set_thirds(operator)
            change = game_type.CharacterStatusChange()
            try:
                if second:
                    effect(0, change)
                else:
                    effect(0, 10, change, game_time.now())
            except Exception as error:
                raised[name] = f"{type(error).__name__}: {error}"
            for cid in (0, operator_id):
                fields = num_fields(self.cache.character_data[cid])
                for path, value in fields:
                    if wrong(value):
                        found[name, cid, path] = f"{type(value).__name__}"
        self.assertEqual(
            [
                f"{name} {cid} {path}: {what}"
                for (name, cid, path), what in found.items()
            ],
            [],
        )
        self.assertEqual(
            [
                f"{name} {what}"
                for name, what in raised.items()
                if "Fraction" in what
            ],
            [],
        )
