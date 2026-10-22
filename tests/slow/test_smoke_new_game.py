# -*- coding: UTF-8 -*-
"""
冒烟测试：新开局后经主循环跑几个游戏小时，每小时跑全部静态自检，并录下行为快照
================================================================================
开新游戏（开局时间为 tests.world.START_TIME，10:00）后，博士在原地反复用「等待五分钟」，主循环推进 HOURS 个小时，
其间至少一名干员吃饭（12:00 的午饭）；每一步结束都记一份行为快照（tests/snapshot.py）。
开局时和此后每个整点各跑一遍全部静态自检（Script.Test.Static_Check.run_all_checks，游戏在主界面等待输入前经 run_turn_check 调用它），
任何一条失败都让测试失败，失败信息写明整点与检查编号。
唯一的例外是已知的未修缺陷 KNOWN_OPEN_BUG，它是严格的预期失败：只认 is_known_open_bug 描述的那一种失败，
而且它必须出现；不出现时测试失败（XPASS），说明缺陷已修好，要删掉这个预期失败。

快照写到 LAST_RUN；与基准 BASELINE 比较：python -m tests.snapshot compare tests/snapshots/smoke_new_game.tsv tests/snapshots/smoke_new_game.last.tsv
行为有意改变时，把 LAST_RUN 复制成 BASELINE，随改动一起提交。
"""
import os

from tests.slow.base import SlowTestCase
from tests.world import ROOT

HOURS = 6
""" 推进的游戏小时数：10:00 到 16:00 """
STEP_MINUTES = 5
""" 每一步「等待五分钟」推进的分钟数 """
BASELINE = os.path.join(ROOT, "tests", "snapshots", "smoke_new_game.tsv")
""" 提交在仓库里的基准快照 """
LAST_RUN = os.path.join(ROOT, "tests", "snapshots", "smoke_new_game.last.tsv")
""" 本次运行写出的快照（不提交） """
KNOWN_OPEN_BUG = "已知的未修缺陷：阿米娅在大浴场把袜子和鞋子放进衣柜时，结算「袜子和鞋子转移到大浴场衣柜」只往空的 cloth_locker_semen 写入 10、11 两类衣物，BODY-10 报告它半初始化"
""" 本测试唯一的预期失败；缺陷修好后测试因它不再出现而失败，届时删掉它与 is_known_open_bug """
KNOWN_OPEN_BUG_NAME = "阿米娅"
""" 已知缺陷涉及的干员 """


class SmokeNewGameTest(SlowTestCase):
    """新开局跑几个游戏小时，静态自检除已知缺陷外全部通过"""

    def is_known_open_bug(self, failure, foot_cloth_settled: set) -> bool:
        """
        这条自检失败是不是已知缺陷 KNOWN_OPEN_BUG
        Keyword arguments:
        failure -- CheckFailure
        foot_cloth_settled -- 结算过「袜子和鞋子转移到大浴场衣柜」的角色id
        Return arguments:
        bool -- 是 BODY-10、只涉及阿米娅、报告 cloth_locker_semen 半初始化、她的这张表正好只有 10、11 两类，且她结算过那个效果时为真
        """
        cid = self.npc(KNOWN_OPEN_BUG_NAME)
        locker = self.cache.character_data[cid].dirty.cloth_locker_semen
        return (
            failure.check_id == "BODY-10"
            and failure.involved_character_ids == [cid]
            and "cloth_locker_semen半初始化" in failure.message
            and sorted(locker) == [10, 11]
            and cid in foot_cloth_settled
        )

    def test_hours_pass_static_checks(self):
        """10:00 到 16:00 有干员吃饭，每个整点的全部静态自检除已知缺陷外都通过，已知缺陷出现；逐步录下行为快照"""
        from Script.Core import constant, constant_effect
        from Script.Test import Static_Check
        from Script.Test.Static_Check import checks
        from tests.snapshot import Recorder, capture

        checks_dir = os.path.dirname(checks.__file__)
        modules = sorted(name[:-3] for name in os.listdir(checks_dir) if name.startswith("check_") and name.endswith(".py"))
        missing = [name for name in modules if not hasattr(checks, name)]
        self.assertEqual(missing, [], "这些检查模块没有载入，它们的检查没有注册")

        foot_cloth_settled = set()
        """ 结算过「袜子和鞋子转移到大浴场衣柜」的角色id """
        effect_id = constant_effect.BehaviorEffect.FOOT_CLOTH_TO_SHOWER_LOCKER
        real_effect = constant.settle_behavior_effect_data[effect_id]

        def record_effect(character_id, add_time, *args):
            """
            记录型包装：结算时间不为 0 时记下角色id，照常结算
            Keyword arguments:
            character_id -- 角色id
            add_time -- 结算时间
            args -- 状态变更记录与结算的时间
            Return arguments:
            与原结算函数相同
            """
            if add_time:
                foot_cloth_settled.add(character_id)
            return real_effect(character_id, add_time, *args)

        constant.settle_behavior_effect_data[effect_id] = record_effect

        failures = []
        """ 失败的自检：「整点 检查编号 检查名: 说明」 """
        known = []
        """ 已知缺陷 KNOWN_OPEN_BUG 出现的整点 """

        def run_checks():
            """
            跑一遍全部静态自检，已知缺陷记进 known，其他失败记进 failures
            Keyword arguments:
            无
            Return arguments:
            无
            """
            hour = self.cache.game_time.strftime("%m-%d %H:%M")
            for f in Static_Check.run_all_checks():
                if self.is_known_open_bug(f, foot_cloth_settled):
                    known.append(hour)
                else:
                    failures.append(f"{hour} {f.check_id} {f.check_name}: {f.message[:300]}")

        recorder = Recorder()
        npc_behaviors = set()
        """ 干员在各步结束时的行为id """
        start = self.cache.game_time
        recorder.record(start.strftime("%Y-%m-%d %H:%M"), capture(self.cache))
        run_checks()
        for _ in range(HOURS * 60 // STEP_MINUTES):
            self.instruct(constant.Instruct.WAIT)
            now = self.cache.game_time
            recorder.record(now.strftime("%Y-%m-%d %H:%M"), capture(self.cache))
            npc_behaviors.update(self.cache.character_data[cid].behavior.behavior_id for cid in self.cache.npc_id_got)
            if now.minute == 0:
                run_checks()
        os.makedirs(os.path.dirname(LAST_RUN), exist_ok=True)
        recorder.write(LAST_RUN)
        self.assertEqual((self.cache.game_time - start).total_seconds(), HOURS * 3600, "主循环推进的时间")
        self.assertIn(constant.Behavior.EAT, npc_behaviors, "没有干员吃饭")
        self.maxDiff = None
        self.assertEqual(failures, [])
        self.assertTrue(known, f"预期失败没有出现（XPASS）：{KNOWN_OPEN_BUG}。缺陷已修好，删掉 KNOWN_OPEN_BUG 与 is_known_open_bug")
