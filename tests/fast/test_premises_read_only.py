# -*- coding: UTF-8 -*-
"""
前提只读
========
每条已注册的前提对玩家与一名干员各判定两次，两次结果一致。
世界有三种，都是一对互为交互对象的博士和干员：普通的一对；干员被浅层、深层催眠，博士有中级催眠和理智的一对，
这时实行值类前提走催眠补正的分支；博士没登记宿舍、干员是助理而助理服务表为空的一对，这时前提读到缺省值。
小世界缺数据而抛错的判定跳过，但抛错的不能过半。
"""

from tests import chara_abilities as ca, kernel_data
from tests.chara_activity import aim
from collections.abc import Callable
from typing import Any

from Script.Core import constant
from Script.Design import handle_premise
from tests.fast.base import FastTestCase
from Script.Modules.domains import flags, chara_life, relations

LOADED = handle_premise
""" 导入即注册全部前提 """
NPC = 1
""" 干员的id """
WHO = (0, NPC)
""" 做判定角色的id """


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
        aim(self.player.cid, NPC)
        aim(self.npc.cid, 0)

    def check(self, prepare: Callable[[], None]) -> None:
        """
        布置世界后对每条前提各判定两次：两次结果一致，抛错次数不足一半
        Keyword arguments:
        prepare -- 布置世界
        Return arguments:
        无
        """
        prepare()
        differ = {}
        failed = 0
        for premise, func in sorted(constant.handle_premise_data.items()):
            for cid in WHO:
                answers = judge(func, cid)
                if answers is None:
                    failed += 1
                elif answers[0] != answers[1]:
                    differ[premise, cid] = answers
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
            kernel_data.put(chara_life.dormitory.set, self.player.cid, "")
            kernel_data.put(
                relations.assistant_character_id.set, self.player.cid, NPC
            )
            kernel_data.put(relations.assistant_services.set, self.npc.cid, {})

        self.check(prepare)
