"""
单步失败后计划队列清空待提交打断的测试
======================================
本测试在极简内核环境中加载记录钩子、plan_queue 与玩具动作插件。正常步骤排下的打断会在该步生效。
单步抛出异常时，forget_on_failure 会清空待提交打断与正在开始行动的角色键。后续正常步骤不会套用该打断。
"""

from types import MappingProxyType

from Script.Kernel import core
from Script.Modules.domains import roster
from Script.Modules.gameplay_resolution import plan_queue
from tests.fast.kernel_toys import KernelTestCase, Toy


class ForgetOnFailureTest(KernelTestCase):
    """验证正常步骤提交计划队列中的打断，以及失败步骤丢弃待提交打断与 acting 状态。"""

    def setUp(self) -> None:
        """
        搭建含博士（"0"）与干员（"1"）的内核状态，按 spy、plan_queue、toy 顺序加载插件。
        toy 为角色 "0" 提供 2 分钟的 Fragile 行动，按标志位决定是否排下打断或抛出 ValueError。
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")
        self.addCleanup(plan_queue.forget)
        self.broken = False
        self.interrupting = False
        self.applied: list[core.Effects] = []
        spy, toy = Toy(), Toy()

        @spy.input_hook(core.apply_effects)
        def seen(effects: core.Effects) -> tuple[core.Effects]:
            self.applied.append(effects)
            return (effects,)

        @toy.action("Fragile")
        def fragile(act: core.Action) -> core.Effects:
            if self.interrupting:
                plan_queue.interrupt(1)
            if self.broken:
                raise ValueError("broken start")
            return ()

        @toy.input_hook(core.pick_next_action)
        def pick(who: str) -> core.Intercept[core.Action]:
            return core.Intercept(core.new_action(fragile, who, 2))

        characters = {
            who: core.Character(
                core.Action(who, core.idle.name, None, 0, end),
                MappingProxyType({}),
            )
            for who, end in (("0", 0), ("1", 100))
        }
        core.load((spy.module, plan_queue, toy.module))
        core.reset_state(
            core.GameState(
                0,
                MappingProxyType(characters),
                MappingProxyType({roster.ACTIVE: (1,)}),
            )
        )

    def interrupts(self) -> list[str]:
        """
        执行一步内核推进，收集该步 apply_effects 收到的所有 Interrupt 目标。
        Return arguments:
        list -- 本步生效的打断目标角色键列表
        """
        self.applied.clear()
        core.step()
        return [
            e.who for e in self.applied[-1] if isinstance(e, core.Interrupt)
        ]

    def test_good_step_applies_its_interrupt(self) -> None:
        """对照用例：正常步骤排下对干员 1 的打断时，该步恰好对角色键 "1" 生效一次打断。"""
        self.interrupting = True
        self.assertEqual(self.interrupts(), ["1"])

    def test_failed_step_drops_its_interrupt(self) -> None:
        """
        失败步骤排下打断并抛出 ValueError 后，断言 plan_queue.mark() 为 0 且 acting 为 None。
        随后运行不排打断的正常步骤，断言不会套用任何打断。
        """
        self.broken = self.interrupting = True
        with self.assertRaises(ValueError):
            core.step()
        self.assertEqual(plan_queue.mark(), 0)
        self.assertIsNone(plan_queue.acting)
        self.broken = self.interrupting = False
        self.assertEqual(self.interrupts(), [])
