"""独立调度内核的接口约束。"""

from datetime import datetime, timedelta
from types import SimpleNamespace
import unittest

from Script.Modules.scheduler import AI, INPUT, Scheduler, Task


class SchedulerTests(unittest.TestCase):
    """使用简化行动检查时序、后续和替换。"""

    def test_time_order_and_player_input_priority(self):
        """无输入参数；验证按时间交错，玩家输入先于同刻 NPC；无返回值。"""
        now = datetime(2026, 1, 1)
        seen = []
        action = SimpleNamespace(duration=5)
        scheduler = Scheduler(now, choose_next=lambda actor, at: action, execute=lambda actor, action: seen.append((actor, scheduler.now)) or action.duration)
        scheduler.submit(Task(3, now + timedelta(minutes=5), action))
        scheduler.submit(Task(2, now + timedelta(minutes=2), action))
        scheduler.submit(Task(0, now + timedelta(minutes=5), INPUT))
        scheduler.submit(Task(1, now, action))
        result = scheduler.advance_until_input()
        self.assertEqual(seen, [(1, now), (2, now + timedelta(minutes=2))])
        self.assertIs(result.item, INPUT)
        self.assertTrue(scheduler.contains(1))
        self.assertTrue(scheduler.contains(2))

    def test_immediate_successor_runs_after_current_callback(self):
        """无输入参数；验证立即后续不递归，且优先于输入与同刻任务；无返回值。"""
        now = datetime(2026, 1, 1)
        seen = []
        first = SimpleNamespace(name="first", duration=5)
        second = SimpleNamespace(name="second", duration=5)

        def execute(actor, action):
            """记录角色与行动，首次行动提交立即后续；无返回值。"""
            seen.append(action)
            if action is first:
                scheduler.submit(Task(actor, now, second, immediate=True))
                seen.append("返回前")
            return action.duration

        scheduler = Scheduler(now, choose_next=lambda actor, at: first, execute=execute)
        scheduler.submit(Task(1, now, first, immediate=True))
        scheduler.submit(Task(0, now, INPUT))
        scheduler.advance_until_input()
        self.assertEqual(seen, [first, "返回前", second])

    def test_replace_validation_preserves_old_task_and_skips_stale_entries(self):
        """无输入参数；验证替换先检查且被替换条目永不执行；无返回值。"""
        now = datetime(2026, 1, 1)
        seen = []
        old = SimpleNamespace(name="old", duration=10)
        new = SimpleNamespace(name="new", duration=10)
        hooks = []
        scheduler = Scheduler(now, choose_next=lambda actor, at: old, execute=lambda actor, action: seen.append(action) or action.duration, before_task=lambda task: hooks.append(task.item))
        scheduler.submit(Task(1, now, old))
        with self.assertRaises(ValueError):
            scheduler.replace(Task(1, now - timedelta(minutes=1), new))
        self.assertTrue(scheduler.contains(1))
        self.assertIs(scheduler.pending(1).item, old)
        scheduler.replace(Task(1, now + timedelta(minutes=1), new))
        scheduler.submit(Task(0, now + timedelta(minutes=2), INPUT))
        scheduler.advance_until_input()
        self.assertEqual(seen, [new])
        self.assertEqual(hooks, [new, INPUT])

    def test_ai_choice_and_player_duration(self):
        """无输入参数；验证选择时刻和玩家时长生成输入占位符；无返回值。"""
        now = datetime(2026, 1, 1)
        decisions = []
        action = SimpleNamespace(duration=10)

        def choose(actor, at):
            """输入角色和时刻，记录后返回行动。"""
            decisions.append((actor, at))
            return action

        scheduler = Scheduler(now, choose_next=choose, execute=lambda actor, action: action.duration)
        scheduler.submit(Task(1, now, AI))
        scheduler.submit(Task(0, now, action))
        result = scheduler.advance_until_input()
        self.assertEqual(decisions, [(1, now)])
        self.assertEqual(result.at, now + timedelta(minutes=10))

    def test_nested_execution_is_rejected_and_guard_is_released(self):
        """无输入参数；验证回调不能嵌套推进，异常后运行锁释放；无返回值。"""
        now = datetime(2026, 1, 1)
        scheduler = Scheduler(now, choose_next=lambda actor, at: None, execute=lambda actor, action: scheduler.advance_until_input())
        scheduler.submit(Task(1, now, SimpleNamespace(duration=1)))
        with self.assertRaisesRegex(RuntimeError, "嵌套"):
            scheduler.advance_until_input()
        scheduler.submit(Task(0, now, INPUT))
        self.assertIs(scheduler.advance_until_input().item, INPUT)

    def test_validation_and_conflicting_submission(self):
        """无输入参数；验证占位符归属、立即时刻和重复提交约束；无返回值。"""
        now = datetime(2026, 1, 1)
        scheduler = Scheduler(now, choose_next=lambda actor, at: None, execute=lambda actor, action: action.duration)
        for task in (Task(1, now, INPUT), Task(0, now, AI), Task(1, now + timedelta(minutes=1), AI, True)):
            with self.assertRaises(ValueError):
                scheduler.submit(task)
        scheduler.submit(Task(1, now, AI))
        with self.assertRaises(ValueError):
            scheduler.submit(Task(1, now, AI))

    def test_none_is_rejected_even_if_ai_submitted_a_task(self):
        """无输入参数；AI 即使已提交后续也必须返回意图；无返回值。"""
        now = datetime(2026, 1, 1)
        seen = []
        action = SimpleNamespace(duration=10)

        def choose(actor, at):
            """输入角色与时刻，提交强制行动并返回 None。"""
            scheduler.submit(Task(actor, at, action, immediate=True))

        scheduler = Scheduler(now, choose_next=choose, execute=lambda actor, action: seen.append(action) or action.duration)
        scheduler.submit(Task(1, now, AI))
        scheduler.submit(Task(0, now + timedelta(minutes=1), INPUT))
        with self.assertRaisesRegex(RuntimeError, "未返回行动"):
            scheduler.advance_until_input()
        self.assertEqual(seen, [])
        self.assertFalse(scheduler.running)

    def test_before_task_replacement_skips_old_ai(self):
        """无需参数；维护钩子替换待办后只执行新行动；无返回值。"""
        now = datetime(2026, 1, 1)
        seen = []
        forced = SimpleNamespace(duration=10)

        def before(task):
            """输入待办，将 NPC 选择替换为强制动作；返回 None。"""
            if task.item is AI:
                self.assertIs(scheduler.pending(task.actor), task)
                scheduler.replace(Task(task.actor, now, forced, immediate=True))

        scheduler = Scheduler(now, choose_next=lambda *args: self.fail("旧 AI 待办被执行"), execute=lambda actor, action: seen.append(action) or action.duration, before_task=before)
        scheduler.submit(Task(1, now, AI))
        scheduler.submit(Task(0, now + timedelta(minutes=1), INPUT))
        scheduler.advance_until_input()
        self.assertEqual(seen, [forced])

    def test_hook_failure_removes_old_task_and_keeps_replacement(self):
        """无需参数；钩子异常清除原待办或保留新待办，释放运行锁；无返回值。"""
        now = datetime(2026, 1, 1)
        for replace_task in (False, True):
            with self.subTest(replace_task=replace_task):
                seen = []
                action = SimpleNamespace(duration=5)

                def before(task):
                    """输入待办，可先替换再抛出异常；无返回值。"""
                    if task.item is AI:
                        if replace_task:
                            scheduler.replace(Task(task.actor, now, action, immediate=True))
                        raise ValueError("维护失败")

                scheduler = Scheduler(now, choose_next=lambda *args: self.fail("不应选择"), execute=lambda actor, action: seen.append(action) or action.duration, before_task=before)
                scheduler.submit(Task(1, now, AI))
                with self.assertRaisesRegex(ValueError, "维护失败"):
                    scheduler.advance_until_input()
                self.assertFalse(scheduler.running)
                self.assertEqual(scheduler.contains(1), replace_task)
                scheduler.submit(Task(0, now + timedelta(minutes=1), INPUT))
                scheduler.advance_until_input()
                self.assertEqual(seen, [action] if replace_task else [])

    def test_missing_ai_action_is_an_error(self):
        """无输入参数；AI 未提供行动或后续必须报错；无返回值。"""
        now = datetime(2026, 1, 1)
        scheduler = Scheduler(now, choose_next=lambda actor, at: None, execute=lambda actor, action: action.duration)
        scheduler.submit(Task(1, now, AI))
        with self.assertRaisesRegex(RuntimeError, "未返回行动"):
            scheduler.advance_until_input()

    def test_calendar_callback_and_input_hook(self):
        """无输入参数；验证自定义历法与输入任务执行前钩子；无返回值。"""
        now = datetime(2026, 3, 31, 23, 55)
        next_at = datetime(2026, 6, 1, 0, 5)
        seen = []
        calendar_calls = []
        action = SimpleNamespace(duration=10)
        scheduler = Scheduler(
            now,
            choose_next=lambda actor, at: None,
            execute=lambda actor, action: action.duration,
            before_task=lambda task: seen.append((task.item, scheduler.now)),
            advance_time=lambda at, minutes: calendar_calls.append((at, minutes)) or next_at,
        )
        scheduler.submit(Task(0, now, action))
        result = scheduler.advance_until_input()
        self.assertEqual(result, Task(0, next_at, INPUT))
        self.assertEqual(calendar_calls, [(now, 10)])
        self.assertEqual(seen, [(action, now), (INPUT, next_at)])

    def test_duration_is_returned_by_execution(self):
        """无输入参数；执行时缩短片段或冻结时间后使用最终时长；无返回值。"""
        now = datetime(2026, 1, 1)
        for duration in (30, 0):
            scheduler = Scheduler(now, choose_next=lambda actor, at: None, execute=lambda actor, action: duration)
            scheduler.submit(Task(0, now, SimpleNamespace(duration=480)))
            self.assertFalse(scheduler.running)
            result = scheduler.advance_until_input()
            self.assertEqual(result.at, now + timedelta(minutes=duration))
            self.assertFalse(scheduler.running)

    def test_invalid_final_duration_is_rejected(self):
        """无输入参数；执行后产生负数、无穷和非数时长时拒绝继续；无返回值。"""
        now = datetime(2026, 1, 1)
        for duration in (-1, float("inf"), float("nan")):
            with self.subTest(duration=duration):
                action = SimpleNamespace(duration=5)
                scheduler = Scheduler(now, choose_next=lambda actor, at: None, execute=lambda actor, current: duration)
                scheduler.submit(Task(0, now, action))
                with self.assertRaisesRegex(ValueError, "有限非负"):
                    scheduler.advance_until_input()
                self.assertEqual(action.duration, 5)


if __name__ == "__main__":
    unittest.main()
