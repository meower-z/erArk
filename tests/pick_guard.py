# -*- coding: UTF-8 -*-
"""
选行动只读的检查：缓存与内核状态的指纹，和记下每一轮选择是否写了东西的包装
==========================================================================
- fingerprint()：游戏缓存去掉 player_pick.UI_STATE 与 META_STATE 里的路径后的 pickle，加上 core.state()、
  随机数状态、计划队列里待交给内核的打断数与自动存档的请求。
- watch()：包住一轮选择（player_pick.chooser 或交给 tests.world.act 的操作），每轮记下面板id、
  是否抛出 Chosen、这一轮里（Chosen 抛出之前）指纹是否变了，以及这一轮里为写打开的文件。
"""

import builtins
import copy
import os
import pickle
import random
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Self

from Script.Core import cache_control
from Script.Kernel import core
from Script.Modules.gameplay_resolution import plan_queue
from Script.Modules.save_load import autosave
from Script.Modules.tk_ui import player_pick
from Script.UI.Moudle import view

type Fingerprint = tuple[bytes, core.GameState, object, int, bool]


def fingerprint() -> Fingerprint:
    """
    缓存除界面状态与全局设置外的全部内容、内核状态、随机数状态、待交给内核的打断数与自动存档的请求
    Return arguments:
    Fingerprint -- (缓存的 pickle, core.state(), random.getstate(), 打断数, 自动存档请求)
    """
    data = dict(vars(cache_control.cache))
    for path in sorted(player_pick.UI_STATE | player_pick.META_STATE):
        head, _, rest = path.partition(".")
        if not rest:
            data.pop(head, None)
            continue
        if head in data:
            part = copy.copy(data[head])
            vars(part).pop(rest, None)
            data[head] = part
    return (
        pickle.dumps(sorted(data.items())),
        core.state(),
        random.getstate(),
        len(plan_queue._pending),
        autosave._requested,
    )


@contextmanager
def file_writes() -> Iterator[list[str]]:
    """
    这段代码里为写打开的文件（builtins.open 的 w、a、x、+ 模式）与 os.replace 的目标，按顺序记进交回的列表
    Return arguments:
    list -- 写过的路径
    """
    wrote: list[str] = []
    real_open, real_replace = builtins.open, os.replace

    def watched_open(file: Any, mode: str = "r", *args: Any, **kw: Any) -> Any:
        if any(flag in mode for flag in "wax+"):
            wrote.append(str(file))
        return real_open(file, mode, *args, **kw)

    def watched_replace(src: Any, dst: Any, *args: Any, **kw: Any) -> None:
        wrote.append(str(dst))
        real_replace(src, dst, *args, **kw)

    builtins.open, os.replace = watched_open, watched_replace
    try:
        yield wrote
    finally:
        builtins.open, os.replace = real_open, real_replace


@dataclass(frozen=True)
class Round:
    """一轮选择的记录"""

    panel: int
    """ 这一轮开始时的面板id """
    chosen: bool
    """ 这一轮抛出了 Chosen """
    changed: bool
    """ 这一轮里（Chosen 抛出之前）指纹变了 """
    wrote: tuple[str, ...] = ()
    """ 这一轮里为写打开的文件 """


@dataclass
class Watch:
    """记下每一轮选择的包装；作为上下文时包住 player_pick.chooser"""

    rounds: list[Round] = field(default_factory=list)
    """ 每一轮的记录 """
    _saved: Callable[[], None] | None = None

    def __call__(self, round_fn: Callable[[], None]) -> Callable[[], None]:
        """
        包住一轮选择
        Keyword arguments:
        round_fn -- 一轮选择
        Return arguments:
        Callable -- 记下这一轮的选择
        """

        def watched() -> None:
            panel = view.now_panel_id
            before = fingerprint()
            chosen = False
            with file_writes() as wrote:
                try:
                    round_fn()
                except player_pick.Chosen:
                    chosen = True
                    raise
                finally:
                    changed = fingerprint() != before
                    self.rounds.append(
                        Round(panel, chosen, changed, tuple(wrote))
                    )

        return watched

    def __enter__(self) -> Self:
        """换上包住的 player_pick.chooser"""
        self._saved = player_pick.chooser
        player_pick.chooser = self(self._saved)
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """换回原来的 player_pick.chooser"""
        if self._saved is not None:
            player_pick.chooser = self._saved


def watch() -> Watch:
    """
    新的记录
    Return arguments:
    Watch -- 可以包住一轮选择，也可以作为上下文包住 player_pick.chooser
    """
    return Watch()
