# -*- coding: UTF-8 -*-
"""
按行为结算键控的随机流（只给测试用）
====================================
游戏的随机全部来自一条全局流（random、numpy.random 与 tests.world 换上的 uuid4）。
两个角色的结算换了先后，之后的每一次抽取都跟着变，快照比较就分不出「先后变了」与「结算算错了」。

打开后（环境变量 ERARK_KEYED_RANDOM=1，由 tests.world.seed_everything 读），
每一次行动开始时的结算（character_behavior.settle_start 的一次调用）开始前记下三条随机流的状态，
再用 (测试种子, 角色id, 这个角色当前行为的开始时间, 内核时钟) 重设它们；结算结束后恢复记下的状态。
于是一次结算抽到的数与它之前跑过哪些结算无关，结算之外的抽取也不受结算的次数与先后影响。
关闭时什么都不做。

别的代码要让一段结算用同一把键，就把那段放进 keyed(character_id)。
"""

from __future__ import annotations

import contextlib
import functools
import hashlib
import random
import sys
from typing import TYPE_CHECKING

import numpy
from tests.kernel_project import activity

if TYPE_CHECKING:
    import datetime
    from collections.abc import Callable, Iterator

MODULE = "Script.Design.character_behavior"
""" 被包上的结算函数所在的模块 """

_seed: int | None = None
""" 测试种子，install 设定 """

_uuid_rng: random.Random | None = None
""" tests.world 的 uuid4 随机源，install 设定 """

_original: Callable[..., None] | None = None
""" 包上之前的 character_behavior.settle_start """


def _minute(moment: datetime.datetime) -> str:
    """
    时间精确到分钟的文本，年份补足 4 位（未初始化的开始时间是第 1 年）
    Keyword arguments:
    moment -- 时间
    Return arguments:
    str -- 「年-月-日 时:分」
    """
    return (
        f"{moment.year:04d}-{moment.month:02d}-{moment.day:02d} "
        f"{moment.hour:02d}:{moment.minute:02d}"
    )


def pass_key(character_id: int) -> str:
    """
    一次结算的键：测试种子、角色id、角色当前行为的开始时间、内核时钟（game_time.now()）
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    str -- 键
    """
    from Script.Design import game_time

    start = activity.behavior(character_id).start_time
    return f"{_seed}|{character_id}|{_minute(start)}|{_minute(game_time.now())}"


@contextlib.contextmanager
def keyed(character_id: int) -> Iterator[str]:
    """
    在这段代码里用这个角色此刻的键重设三条随机流，离开时恢复进入前的状态
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    str -- 用的键
    """
    if _uuid_rng is None:
        raise RuntimeError("先调用 install：键控随机流还没有种子")
    key = pass_key(character_id)
    saved = (random.getstate(), numpy.random.get_state(), _uuid_rng.getstate())
    digest = hashlib.sha256(key.encode()).digest()
    random.seed(key)
    numpy.random.seed(int.from_bytes(digest[:4], "big"))
    _uuid_rng.seed(f"{key}|uuid")
    try:
        yield key
    finally:
        random.setstate(saved[0])
        numpy.random.set_state(saved[1])
        _uuid_rng.setstate(saved[2])


def install(seed: int, uuid_rng: random.Random) -> None:
    """
    记下测试种子；结算模块已经载入时把 character_behavior.settle_start 换成键控的版本（只换一次）
    Keyword arguments:
    seed -- 测试种子
    uuid_rng -- tests.world 的 uuid4 随机源
    Return arguments:
    无
    功能描述:
        结算模块在缓存建好之后才能导入，所以第一次在它载入之后的 seed_everything（FullWorld.new_game 的末尾）才换上。
        开新游戏的流程不经内核开始行动，所以从构建状态的第一步起每次结算都是键控的。
    """
    global _seed, _uuid_rng, _original
    _seed = seed
    _uuid_rng = uuid_rng
    if MODULE not in sys.modules or _original is not None:
        return
    from Script.Design import character_behavior as module

    original = module.settle_start
    _original = original

    @functools.wraps(original)
    def keyed_settle_start(character_id: int, minutes: int) -> None:
        """
        键控的 settle_start：在 keyed(character_id) 里跑原来的 settle_start，这次结算抽到的随机数与之前跑过哪些结算无关
        Keyword arguments:
        character_id -- 角色id
        minutes -- 行动在内核里的分钟数
        Return arguments:
        无
        """
        with keyed(character_id):
            original(character_id, minutes)

    module.settle_start = keyed_settle_start
