# -*- coding: UTF-8 -*-
"""
游戏时钟（GameTime）通过行为域自检的回归测试
============================================
游戏时钟 cache.game_time / pre_game_time 与行为起时 behavior.start_time 都是 GameTime（datetime 的子类）。
自检 BEHAV-02（全局时钟健全性）与 BEHAV-07（行为核心字段类型）必须接受它们；否则打开自检后每局都报「状态不自洽」。
BEHAV-10/11/12/22 与 BEHAV-07 共用同一个类型判定，类型判定通过后它们才真正比较时间。
本测试的时钟与起时都用 game_time.to_game_time 构造；开局流程 game_time.init_time() 也用它生成时钟。

在仓库根目录运行：python tools/tests/static_check/test_game_clock_passes_checks.py
退出码：0 全部断言通过；1 有断言失败；2 未捕获异常。
"""
import datetime
import sys

sys.path.insert(0, "tools/tests")
from headless_boot import boot, check, finish, mute_ui, new_chara  # noqa: E402

cache = boot()
mute_ui()

from Script.Design import game_time  # noqa: E402
from Script.Test.Static_Check.check_registry import get_all_checks  # noqa: E402
import Script.Test.Static_Check  # noqa: E402,F401  导入即注册全部检查


def run(check_id):
    """
    运行一条已注册的自检
    Keyword arguments:
    check_id -- 检查编号，如 "BEHAV-02"
    Return arguments:
    list[CheckFailure] -- 该检查报告的失败
    """
    return get_all_checks()[check_id][1]()


def messages(failures):
    """
    取失败记录的说明文字，供断言失败时打印
    Keyword arguments:
    failures -- 失败记录列表
    Return arguments:
    list[str] -- 每条失败的说明（截断到 200 字）
    """
    return [f.message[:200] for f in failures]


# ==== 1. 开局时钟 ====
player = new_chara(0, "博士")
player.behavior.behavior_id = "share_blankly"
player.behavior.start_time = game_time.to_game_time(datetime.datetime(2020, 9, 10, 7, 0))
player.behavior.duration = 5
cache.game_time = game_time.to_game_time(datetime.datetime(2020, 9, 10, 7, 3))
cache.pre_game_time = cache.game_time
check("时钟与起时都是 GameTime", type(cache.game_time) is game_time.GameTime and type(player.behavior.start_time) is game_time.GameTime)

failures = run("BEHAV-02")
check("BEHAV-02 接受 GameTime 时钟", not failures, messages(failures))
failures = run("BEHAV-07")
check("BEHAV-07 接受 GameTime 起时", not failures, messages(failures))

# ==== 2. 类型判定通过后，时间比较真正运行 ====
player.behavior.start_time = game_time.to_game_time(datetime.datetime(2020, 9, 10, 8, 0))
failures = run("BEHAV-11")
check("BEHAV-11 报告晚于游戏时间的起时", [f.check_id for f in failures] == ["BEHAV-11"], messages(failures))

# ==== 3. 时钟的其他条件照旧生效 ====
cache.game_time = game_time.to_game_time(datetime.datetime(2020, 9, 10, 7, 3, 30))
failures = run("BEHAV-02")
check("BEHAV-02 只报告带秒数的 game_time", len(failures) == 1 and failures[0].message.startswith("cache.game_time="), messages(failures))

finish()
