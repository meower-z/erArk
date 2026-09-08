"""按时间执行行动；游戏规则由回调提供。"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto
import heapq
import math
from typing import Any, Callable, Iterable


class Placeholder(Enum):
    """尚待自主选择的行动与等待玩家输入的位置。"""

    AI = auto()
    INPUT = auto()


AI = Placeholder.AI
INPUT = Placeholder.INPUT
PLAYER = 0


@dataclass(frozen=True)
class Task:
    """一次待办：角色编号、真实开始时刻、行动或占位符、是否立即执行。"""

    actor: int
    at: datetime
    item: Any
    immediate: bool = False


class Scheduler:
    """每个角色最多保留一条待办，直至玩家再次需要输入。"""

    def __init__(
        self,
        now: datetime,
        initial_tasks: Iterable[Task] = (),
        *,
        choose_next: Callable[[int, datetime], Any],
        execute: Callable[[int, Any], None],
        before_task: Callable[[Task], None] | None = None,
        advance_time: Callable[[datetime, float], datetime] | None = None,
    ) -> None:
        """输入初始时间、待办及选择/执行/执行前回调，建立调度器；无返回值。"""
        self.now = now
        self._choose_next = choose_next
        self._execute = execute
        self._before_task = before_task
        self._advance_time = advance_time
        self._running = False
        self._serial = 0
        self._queue: list[tuple] = []
        self._pending: dict[int, tuple[int, Task]] = {}
        for task in initial_tasks:
            self.submit(task)

    @property
    def running(self) -> bool:
        """无需参数，返回当前是否正在执行任务；外部不可修改。"""
        return self._running

    def contains(self, actor: int) -> bool:
        """输入角色编号，返回该角色是否已有待办。"""
        return actor in self._pending

    def pending(self, actor: int) -> Task | None:
        """输入角色编号，返回现有待办；没有待办时返回 None。"""
        entry = self._pending.get(actor)
        return entry[1] if entry is not None else None

    def submit(self, task: Task) -> None:
        """提交待办；角色已有待办或参数无效时抛出 ValueError，无返回值。"""
        self._validate(task)
        if self.contains(task.actor):
            raise ValueError(f"角色 {task.actor} 已有待办")
        self._put(task)

    def replace(self, task: Task) -> None:
        """验证后替换角色待办；无旧待办时直接提交，无返回值。"""
        self._validate(task)
        self._put(task)

    def _validate(self, task: Task) -> None:
        """输入待办，检查时间和占位符归属；无效时抛出 ValueError。"""
        if task.at < self.now:
            raise ValueError("不能提交过去的任务")
        if task.immediate and task.at != self.now:
            raise ValueError("立即任务必须在当前时刻执行")
        if task.item is INPUT and task.actor != PLAYER:
            raise ValueError("只有玩家可以等待输入")
        if task.item is AI and task.actor == PLAYER:
            raise ValueError("玩家不能使用 NPC AI")

    def _put(self, task: Task) -> None:
        """输入已验证待办，以新序号使同角色旧条目失效；无返回值。"""
        self._serial += 1
        # 立即任务单独排序，真实时刻仍保留；普通任务同刻由玩家输入优先。
        key = (0 if task.immediate else 1, task.at, 0 if task.item is INPUT else 1, self._serial)
        heapq.heappush(self._queue, (*key, task))
        self._pending[task.actor] = (self._serial, task)
        # 长时间替换远期任务时清理失效条目，避免堆持续增长。
        if len(self._queue) > max(64, 2 * len(self._pending)):
            self._queue = [entry for entry in self._queue if self._pending.get(entry[4].actor, (None,))[0] == entry[3]]
            heapq.heapify(self._queue)

    def advance_until_input(self) -> Task:
        """无需参数，顺序执行至玩家输入并返回该待办；禁止嵌套执行。"""
        if self._running:
            raise RuntimeError("调度器不能嵌套执行")
        self._running = True
        try:
            while self._queue:
                _, _, _, serial, task = heapq.heappop(self._queue)
                # 替换过的条目只负责出堆，不影响角色的新待办。
                entry = self._pending.get(task.actor)
                if entry is None or entry[0] != serial:
                    continue
                del self._pending[task.actor]
                self.now = task.at
                if self._before_task is not None:
                    self._before_task(task)
                if task.item is INPUT:
                    return task
                action = self._choose_next(task.actor, self.now) if task.item is AI else task.item
                if action is None:
                    if task.item is AI and self.contains(task.actor):
                        continue
                    raise RuntimeError("AI 未返回行动，也未提交后续")
                self._execute(task.actor, action)
                if not math.isfinite(action.duration) or action.duration < 0:
                    raise ValueError("行动时长必须为有限非负数")
                if not self.contains(task.actor):
                    next_at = self._advance_time(task.at, action.duration) if self._advance_time is not None else task.at + timedelta(minutes=action.duration)
                    if next_at < task.at:
                        raise ValueError("行动结束时间不能早于开始时间")
                    item = INPUT if task.actor == PLAYER else AI
                    self.submit(Task(task.actor, next_at, item))
            raise RuntimeError("队列耗尽，未找到玩家输入")
        finally:
            self._running = False
