# -*- coding: UTF-8 -*-
"""
选行动只读的检查：缓存与内核状态的指纹，和记下每一轮选择是否写了东西的包装
==========================================================================
- fingerprint()：游戏缓存去掉 player_pick.UI_STATE 里的路径后的 pickle，加上 core.state()。
- watch()：包住一轮选择（player_pick.chooser 或交给 tests.world.act 的操作），每轮记下面板id、
  是否抛出 Chosen、以及这一轮里（Chosen 抛出之前）指纹是否变了。
"""

import copy
import pickle
from collections.abc import Callable
from dataclasses import dataclass, field
from types import TracebackType
from typing import Self

from Script.Core import cache_control
from Script.Kernel import core
from Script.Modules.tk_ui import player_pick

type Fingerprint = tuple[bytes, core.GameState]


def fingerprint() -> Fingerprint:
    """
    缓存除界面状态外的全部内容与内核状态
    Return arguments:
    Fingerprint -- (缓存的 pickle, core.state())
    """
    data = dict(vars(cache_control.cache))
    for path in sorted(player_pick.UI_STATE):
        head, _, rest = path.partition(".")
        if not rest:
            data.pop(head, None)
            continue
        if head in data:
            part = copy.copy(data[head])
            vars(part).pop(rest, None)
            data[head] = part
    return (pickle.dumps(sorted(data.items())), core.state())


@dataclass(frozen=True)
class Round:
    """一轮选择的记录"""

    panel: int
    """ 这一轮开始时的面板id """
    chosen: bool
    """ 这一轮抛出了 Chosen """
    changed: bool
    """ 这一轮里（Chosen 抛出之前）指纹变了 """


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
            panel = cache_control.cache.now_panel_id
            before = fingerprint()
            chosen = False
            try:
                round_fn()
            except player_pick.Chosen:
                chosen = True
                raise
            finally:
                changed = fingerprint() != before
                self.rounds.append(Round(panel, chosen, changed))

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
