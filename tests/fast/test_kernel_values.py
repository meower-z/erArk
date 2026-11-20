# -*- coding: UTF-8 -*-
"""
内核能存的值与失败的一步
========================
- 一步抛错时，kernel.StepFailed 的钩子在状态恢复之后运行一次，错误照样抛出。
- with_value 存 Fraction（含分母为 1 的），读回仍是同值的 Fraction。集合与时间仍报 TypeError。
- 改一项时，同一角色别的项原样沿用。
- old 是 Fraction 的 StateChange 只在 old 等于当前值时应用。
"""

import datetime
from fractions import Fraction
from typing import cast

from Script.Kernel import core
from tests.fast.kernel_toys import KernelTestCase, Toy, game


class FailedStepTest(KernelTestCase):
    """一步抛错时的 kernel.StepFailed"""

    def test_failed_step_calls_step_failed_after_restoring(self) -> None:
        """开始函数抛错：StepFailed 的钩子在状态恢复之后运行一次，错误照样抛出"""
        toy = Toy()
        seen: list[core.GameState] = []

        @toy.action("Fragile")
        def fragile(act: core.Action) -> core.Effects:
            raise ValueError("broken start")

        @toy.input_hook(core.pick_next_action)
        def pick(who: str) -> core.Intercept[core.Action]:
            return core.Intercept(core.new_action(fragile, who, 2))

        @toy.input_hook(core.step_failed)
        def failed() -> tuple[()]:
            seen.append(core.state())
            return ()

        self.start(game(0, {"a": 0}), toy)
        before = core.state()
        with self.assertRaises(ValueError):
            core.step()
        self.assertEqual(seen, [before])
        self.assertIs(core.state(), before)


class ValueTest(KernelTestCase):
    """with_value 与 StateChange 能存的值"""

    def test_fraction_is_kept_exact(self) -> None:
        """Fraction（含分母为 1 的）存进去，读回来仍是同值的 Fraction"""
        state = game(0, {"a": 0})
        for value in (Fraction(3, 1), Fraction(7, 72)):
            after = core.with_value(state, "a", "x", value)
            stored = core.value(after, "a", "x")
            self.assertEqual(stored, value)
            self.assertIs(type(stored), Fraction)

    def test_non_json_values_raise(self) -> None:
        """集合与时间不能存，报 TypeError"""
        state = game(0, {"a": 0})
        for value in ({1, 2}, datetime.datetime(2020, 1, 1)):
            with self.assertRaises(TypeError):
                core.with_value(state, "a", "x", cast(core.JSON, value))

    def test_untouched_values_are_shared(self) -> None:
        """改一项时，同一角色别的项是原来的对象"""
        state = game(0, {"a": 0}, {"a": {"big": {"n": (1, 2)}}})
        after = core.with_value(state, "a", "x", 1)
        self.assertIs(
            after.characters["a"].data["big"],
            state.characters["a"].data["big"],
        )

    def test_state_change_checks_a_fraction_old(self) -> None:
        """old 是 Fraction 的 StateChange 只在 old 等于当前值时应用，不等时报错"""
        state = core.with_value(game(0, {"a": 0}), "a", "x", Fraction(7, 72))
        change = core.StateChange("a", "x", Fraction(7, 72), Fraction(1, 2))
        moved = core.preview(state, (change,))
        self.assertEqual(core.value(moved, "a", "x"), Fraction(1, 2))
        stale = core.StateChange("a", "x", Fraction(1, 3), 0)
        with self.assertRaisesRegex(RuntimeError, "does not follow"):
            core.preview(state, (stale,))
