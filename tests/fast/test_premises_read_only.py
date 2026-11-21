# -*- coding: UTF-8 -*-
"""
前提只读
========
每个已注册的前提在博士和一名干员身上各判定两次：两次的答案相同，判定完全部前提后游戏缓存逐字节不变（按 pickle 比较）。
缓存变了时再逐条判定一遍，报出写缓存的前提。
世界有三种，都是一对互为交互对象的博士和干员：普通的一对；干员被浅层、深层催眠，博士有中级催眠和理智的一对，
这时实行值类前提走催眠补正的分支；博士没登记宿舍、干员是助理而助理服务表为空的一对，这时前提读到缺省值。
小世界缺数据而抛错的判定跳过，但抛错的不能过半。
"""

from tests import chara_abilities as ca, kernel_data
import pickle
from collections.abc import Callable
from typing import Any

from Script.Core import constant
from Script.Design import handle_premise
from tests.fast.base import FastTestCase
from Script.Modules.domains import flags

LOADED = handle_premise
""" 导入即注册全部前提 """
NPC = 1
""" 干员的id """
WHO = (0, NPC)
""" 做判定角色的id """


def pickled(cache: Any, keys: list[str] | None = None) -> dict[str, bytes]:
    """
    缓存的每个属性的 pickle；character_data 与 scene_data 按条拆开
    Keyword arguments:
    cache -- 游戏缓存
    keys -- 只取这些属性名，默认全取
    Return arguments:
    dict -- 属性名 -> pickle
    """
    split = ("character_data", "scene_data")
    parts = {k: v for k, v in vars(cache).items() if k not in split}
    for name in split:
        for key, value in getattr(cache, name).items():
            parts[f"{name}[{key}]"] = value
    return {
        k: pickle.dumps(v)
        for k, v in parts.items()
        if keys is None or k in keys
    }


def changed(before: dict[str, bytes], after: dict[str, bytes]) -> list[str]:
    """
    两次 pickle 之间变了的属性名
    Keyword arguments:
    before -- 先取的 pickle
    after -- 后取的 pickle
    Return arguments:
    list -- 变了的属性名
    """
    return sorted(
        k for k in before.keys() | after.keys() if before.get(k) != after.get(k)
    )


def judge(func: Callable[[int], float], cid: int) -> tuple[Any, Any] | None:
    """
    同一前提连判两次
    Keyword arguments:
    func -- 前提处理函数
    cid -- 判定角色id
    Return arguments:
    tuple -- 两次的答案；抛错时为 None
    """
    try:
        return func(cid), func(cid)
    except Exception:  # 小世界缺这条前提要读的数据
        return None


class PremisesReadOnlyTest(FastTestCase):
    """前提只判不写，同一状态下答案不变"""

    def setUp(self) -> None:
        """
        博士和干员互为交互对象
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.player = self.world.chara(0, "博士")
        self.npc = self.world.chara(NPC, "干员")
        self.player.target_character_id = NPC
        self.npc.target_character_id = 0

    def writers(
        self, prepare: Callable[[], None], keys: list[str]
    ) -> dict[tuple[str, int], list[str]]:
        """
        复原世界后逐条判定，找出写了 keys 中属性的前提
        Keyword arguments:
        prepare -- 复原后布置世界
        keys -- 判定全部前提后变了的属性名
        Return arguments:
        dict -- (前提, 角色id) -> 变了的属性名
        """
        self.setUp()
        prepare()
        found = {}
        before = pickled(self.cache, keys)
        for premise, func in sorted(constant.handle_premise_data.items()):
            for cid in WHO:
                judge(func, cid)
                after = pickled(self.cache, keys)
                diff = changed(before, after)
                if diff:
                    found[premise, cid] = diff
                    before = after
        return found

    def check(self, prepare: Callable[[], None]) -> None:
        """
        布置世界后判定全部前提：答案都不变，缓存不变，抛错的不过半
        Keyword arguments:
        prepare -- 布置世界
        Return arguments:
        无
        """
        prepare()
        differ = {}
        failed = 0
        before = pickled(self.cache)
        for premise, func in sorted(constant.handle_premise_data.items()):
            for cid in WHO:
                answers = judge(func, cid)
                if answers is None:
                    failed += 1
                elif answers[0] != answers[1]:
                    differ[premise, cid] = answers
        keys = changed(before, pickled(self.cache))
        if keys:
            self.fail(f"前提写了缓存：{self.writers(prepare, keys)}")
        self.assertEqual(differ, {}, "连判两次答案不同")
        total = len(WHO) * len(constant.handle_premise_data)
        self.assertLess(failed, total / 2, f"{failed}/{total} 次判定抛错")

    def test_plain_pair(self) -> None:
        """
        普通的博士和干员
        Keyword arguments:
        无
        Return arguments:
        无
        """
        self.check(lambda: None)

    def test_hypnotized_pair(self) -> None:
        """
        干员在催眠中，被浅层、深层催眠；博士有中级催眠和100理智
        Keyword arguments:
        无
        Return arguments:
        无
        """

        def prepare() -> None:
            kernel_data.put(flags.set, self.npc.cid, unconscious_h=4)
            ca.talent(self.npc)[71] = ca.talent(self.npc)[72] = 1
            ca.talent(self.player)[332] = 1
            kernel_data.set_needs(self.player.cid, sanity=100, sanity_max=100)

        self.check(prepare)

    def test_sparse_pair(self) -> None:
        """
        博士的宿舍为空；干员是博士的助理，助理服务表为空
        Keyword arguments:
        无
        Return arguments:
        无
        """

        def prepare() -> None:
            self.player.dormitory = ""
            self.player.assistant_character_id = NPC
            self.npc.assistant_services = {}

        self.check(prepare)
