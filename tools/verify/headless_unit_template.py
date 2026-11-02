# -*- coding: UTF-8 -*-
"""
erArk 无头函数级单元测试模板
============================
在内存里造角色夹具，再直接调用前提函数 / 结算器 / 换装函数 / 口上系统做断言，不读存档、不跑行为循环。
排查死循环、复刻指令、跑行为循环请用同目录的 headless_harness_template.py。
游戏世界取自被测 checkout 的 tests/world.py：MinimalWorld 读入真实配置、造出空的游戏状态，不启动游戏。

用法：先把本文件拷进 checkout 之外的一个运行目录再改拷贝；
从被测 checkout 的根目录经 limited_run.py 启动：
    <venv>/bin/python tools/verify/limited_run.py --timeout 600 -- <venv>/bin/python -u <运行目录>/test.py

退出码：0 全部断言通过；1 有断言失败；2 未捕获异常（堆栈在日志里）。
"""

import os
import sys
import traceback
from unittest import mock

# ==== 0. 断言与收尾：现有代码里 handle_instruct 的非守护线程 init_instruct_handle_thread 永不结束，进程只能以 os._exit 结束 ====
FAILED = []
PASSED = []


def check(name, cond, extra=""):
  """
  记录并打印一条断言结果
  Keyword arguments:
  name -- 断言名
  cond -- 断言条件
  extra -- 失败时附带打印的实际值
  Return arguments:
  bool -- 断言是否通过
  """
  (PASSED if cond else FAILED).append(name)
  print(f"  [OK] {name}" if cond else f"  [FAIL] {name} {extra}", flush=True)
  return bool(cond)


def finish(code=None):
  """
  打印断言汇总并结束进程：全过退出码 0，有失败退出码 1
  Keyword arguments:
  code -- 指定退出码；None 时按断言结果决定
  Return arguments:
  无（进程直接退出）
  """
  print(
      f"\nPASS={len(PASSED)} FAIL={len(FAILED)}",
      *[f"  - {name}" for name in FAILED],
      sep="\n",
      flush=True,
  )
  os._exit(code if code is not None else (1 if FAILED else 0))


def crash(exc_type, exc, tb):
  """
  未捕获异常：打印堆栈与汇总，以退出码 2 结束进程
  Keyword arguments:
  exc_type -- 异常类型
  exc -- 异常对象
  tb -- 回溯对象
  Return arguments:
  无（进程直接退出）
  """
  traceback.print_exception(exc_type, exc, tb)
  finish(2)


sys.excepthook = crash
sys.path.insert(0, os.getcwd())  # 当前目录即被测 checkout 的根目录

from tests.world import MinimalWorld

world = MinimalWorld.load()
cache = world.cache
wait_texts = world.wait_texts  # WaitDraw 文本，断言「某段提示是否画出」时读它

import Script.Settle  # 结算器靠装饰器注册，MinimalWorld 不导入它
from Script.Config import game_config
from Script.Core import constant, game_type
from Script.Design import attr_calculation, handle_premise

pl = world.chara(0, "博士")

# ==== 1. 注册：新前提 / 新结算器 / 新行为 / 新口上是否进了运行时与生成物 ====
check("前提已注册", "high_1" in constant.handle_premise_data)
check("结算器已注册", 62 in constant.settle_behavior_effect_data)
check("行为配置存在", "sleep" in game_config.config_behavior)
check("行为效果链存在", "sleep" in game_config.config_behavior_effect_data)
check(
    "口上已编译进 Character_Talk",
    any(
        getattr(t, "behavior_id", "") == "sleep"
        for t in game_config.config_talk.values()
    ),
)

# ==== 2. 结算器：settle_behavior_effect_data[效果id](角色id, add_time, change_data, now_time) ====
target = world.chara(101, "样例干员")
pl.target_character_id = 101
change = game_type.CharacterStatusChange()
constant.settle_behavior_effect_data[62](
    0, 1, change, cache.game_time
)  # 交互对象增加少量反感
check(
    "结算器改动了交互对象的反感",
    target.status_data.get(20, 0) > 0,
    f"disgust={target.status_data.get(20, 0)}",
)

# ==== 3. 前提函数：handle_premise.handle_xxx(cid) ====
check("前提返回值符合预期", handle_premise.handle_high_1(101) == 1)

# ==== 4. 固定随机：side_effect 依次给出每次 randint 的返回值，call_args_list 记下每次的参数 ====
with mock.patch("random.randint", side_effect=[3]) as randint:
  pregnancy = attr_calculation.get_pregnancy_zero()
check(
    "生理周期取自 randint",
    pregnancy.reproduction_period == 3,
    f"got={pregnancy.reproduction_period}",
)
check(
    "randint 只调一次且范围为 0~6",
    randint.call_args_list == [mock.call(0, 6)],
    f"calls={randint.call_args_list}",
)

finish()
