"""按时间顺序执行各角色的行动，直到轮到玩家输入。

游戏里玩家和 NPC 各自做行动，每个行动占用若干分钟。本模块为每个角色保存接下来要做的一件事（Task，下文称"待办"），
按开始时刻从早到晚逐条执行；执行到"等待玩家输入"的待办时停下，把控制权交回界面。

本模块不知道任何具体的游戏规则。创建 Scheduler 时由调用方提供三个函数：轮到 NPC 时如何选择行动（choose_next）、
如何执行一个行动并返回它占用的分钟数（execute）、执行每条待办之前要做的维护（before_task）；
另可选提供一个按游戏历法计算行动结束时刻的函数（advance_time）。游戏侧的这些函数在 game_actions.py。

排序规则：标记为立即执行的待办最先；其余按开始时刻排序；同一时刻玩家输入优先；仍相同时按提交顺序。
每个角色同一时间只保留一条待办：submit 只在该角色没有待办时可用，replace 用新待办换掉旧的。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto
import heapq
import math
from typing import Any, Callable


class Placeholder(Enum):
    """待办里"要做的事"尚未确定时用的占位符：AI 表示到时让 NPC 自己选择行动，INPUT 表示到时等待玩家输入。"""

    AI = auto()
    INPUT = auto()


AI = Placeholder.AI
INPUT = Placeholder.INPUT
PLAYER = 0


@dataclass(frozen=True)
class Task:
    """一条待办：角色编号 actor、开始时刻 at、要做的事 item（具体行动或上面的占位符）、是否立即执行 immediate。"""

    actor: int
    at: datetime
    item: Any
    immediate: bool = False


class Scheduler:
    """按开始时刻执行待办的队列。

    每个角色最多一条待办。一条待办执行完后，若该角色没有新的待办，就在这次行动结束的时刻为它安排一条：
    NPC 安排"自己选择行动"，玩家安排"等待输入"。用 cancel 撤销某角色的待办后，该角色不再出现在队列里，直到调用方再次提交。
    """

    def __init__(
        self,
        now: datetime,
        *,
        choose_next: Callable[[int, datetime], Any],
        execute: Callable[[int, Any], float],
        before_task: Callable[[Task], None] | None = None,
        advance_time: Callable[[datetime, float], datetime] | None = None,
    ) -> None:
        """输入初始时间及选择/执行/执行前回调，建立调度器；无返回值。"""
        self.now = now
        self._choose_next = choose_next
        self._execute = execute
        self._before_task = before_task
        self._advance_time = advance_time
        self._running = False
        self._serial = 0
        self._queue: list[tuple] = []
        self._pending: dict[int, tuple[int, Task]] = {}

    @property
    def running(self) -> bool:
        """无需参数，以只读属性返回当前是否正在执行任务。"""
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

    def cancel(self, actor: int) -> None:
        """输入角色编号，撤销其待办；没有待办时不做任何事，无返回值。"""
        self._pending.pop(actor, None)

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
        # 立即任务优先；普通任务按真实时刻排序，同刻玩家输入优先。
        key = (0 if task.immediate else 1, task.at, 0 if task.item is INPUT else 1, self._serial)
        heapq.heappush(self._queue, (*key, task))
        self._pending[task.actor] = (self._serial, task)
        # 失效条目累积到阈值时压缩堆。
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
                # 序号匹配的条目代表角色当前待办。
                entry = self._pending.get(task.actor)
                if entry is None or entry[0] != serial:
                    continue
                self.now = task.at
                if self._before_task is not None:
                    try:
                        self._before_task(task)
                    except Exception:
                        # 失败的原待办已出队；保留回调中另行提交的替代待办。
                        if self._pending.get(task.actor, (None,))[0] == serial:
                            del self._pending[task.actor]
                        raise
                # 执行前的状态维护可以替换待办；仅执行仍有效的条目。
                entry = self._pending.get(task.actor)
                if entry is None or entry[0] != serial:
                    continue
                del self._pending[task.actor]
                if task.item is INPUT:
                    return task
                action = self._choose_next(task.actor, self.now) if task.item is AI else task.item
                if action is None:
                    raise RuntimeError("AI 未返回行动")
                duration = self._execute(task.actor, action)
                if not math.isfinite(duration) or duration < 0:
                    raise ValueError("行动时长必须为有限非负数")
                if not self.contains(task.actor):
                    next_at = self._advance_time(task.at, duration) if self._advance_time is not None else task.at + timedelta(minutes=duration)
                    if next_at < task.at:
                        raise ValueError("行动结束时间不能早于开始时间")
                    item = INPUT if task.actor == PLAYER else AI
                    self.submit(Task(task.actor, next_at, item))
            raise RuntimeError("队列耗尽，未找到玩家输入")
        finally:
            self._running = False
