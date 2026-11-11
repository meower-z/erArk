# -*- coding: UTF-8 -*-
"""
erArk 无头行为循环诊断模板
==========================
读档入内存、复刻一条玩家指令，再带护栏地跑一轮真实的行为循环 init_character_behavior。
运行中可以逐轮查看指定角色，也可以在内存里模拟候选修复。
游戏世界取自被测 checkout 的 tests/world.py：FullWorld 完整启动游戏（结算器、状态机、界面流程），
玩家输入由 world.player 给出。
本脚本不存档：循环里会写文件的两处（玩家睡觉时的自动存档、临时外勤委托追加写 Commission.csv）被替换掉；
但 FullWorld 启动时的 import auto_build_config 会在 CSV 变动时增量重建 data/ 下的生成物。

用法：先把本文件拷进 checkout 之外的一个运行目录再改拷贝；
从被测 checkout 的根目录经 limited_run.py 启动：
    <venv>/bin/python tools/verify/limited_run.py --timeout 600 -- <venv>/bin/python -u <运行目录>/test.py
需要存档：先把要读的存档装进 save/（`unzip -o <存档>.zip -d save/`），再把 SAVE_ID 改成它的编号。

退出码：0 玩家阶段与 NPC 阶段都收敛；1 有阶段超过轮数上限（卡死）；
2 未捕获异常（存档不存在、循环要玩家选择而没有安排输入，都落在这里）。
判读：玩家阶段通常 1 轮。读档后的第一轮循环要让 NPC 追平存档时刻，一次实测中 NPC 阶段约 20 轮；
      任一阶段达到 10 轮会打印提醒，是否异常以同一存档、同一指令的未修复基线轮数为准。
"""

import io
import os
import random
import sys
import traceback

# ==== 0. 断言与收尾：finish() 打印断言汇总并以对应的退出码结束进程 ====
FAILED: list[str] = []
PASSED: list[str] = []


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

from tests.world import FullWorld

world = FullWorld.load()
cache = world.cache
# 循环里要玩家选择时，按 world.player.press("按钮文字的一部分") 事先安排；没安排就抛 UnplannedInput（退出码 2），
# 并列出屏幕上的按钮

from Script.Config import game_config
from Script.Core import constant, io_init, save_handle
from Script.Design import (
    character_behavior,
    game_time,
    handle_npc_ai,
    instuct_judege,
)
from Script.System.Field_Commission_System import field_commission_function

# ==== 1. 读档 ====
SAVE_ID = "<存档编号>"  # 存档目录 save/<SAVE_ID>/
WATCH_NAME = "阿米娅"  # 重点观察的角色名；None 则不观察
CAPTURE_KEYWORD = "吵醒"  # 结果里只打印含此关键词的屏幕文字；None 则全部打印
captured_texts: list[str] = []
"""输出时就收下的屏幕文字（world.player.screen 只留最近 400 段，循环跑完再筛会漏掉早先的文字）"""
player_print = (
    io_init.era_print
)  # FullWorld 载入时由 world.player 换上的输出函数


def capture_print(string, *args, **kwargs):
    """
    包装 io_init.era_print：含 CAPTURE_KEYWORD 的文字收进 captured_texts，再照常交给 world.player
    Keyword arguments:
    string -- 输出的文字
    args / kwargs -- 原样传给原函数的其余参数
    Return arguments:
    原函数的返回值
    """
    if str(string).strip() and (
        not CAPTURE_KEYWORD or CAPTURE_KEYWORD in str(string)
    ):
        captured_texts.append(str(string))
    return player_print(string, *args, **kwargs)


io_init.era_print = capture_print

save_handle.input_load_save(SAVE_ID)
pl = cache.character_data[0]
WATCH = {
    cid
    for cid, cd in cache.character_data.items()
    if WATCH_NAME and cd.name == WATCH_NAME
}


def describe(cid):
    """
    把角色的行为与关键状态格式化成一行，供读档体检、逐轮内窥、结果判读共用
    Keyword arguments:
    cid -- 角色id
    Return arguments:
    str -- 状态描述
    """
    cd = cache.character_data[cid]
    flag = cd.sp_flag
    return (
        f"{cd.name}(id{cid}) 位置={cd.position} bhv={cd.behavior.behavior_id} dur={cd.behavior.duration}"
        f" start={cd.behavior.start_time} state={cd.state} tired={cd.tired_point} sleep={cd.sleep_point}"
        f" hp={cd.hit_point}/{cd.hit_point_max} mp={cd.mana_point}/{cd.mana_point_max}"
        f" sp_flag(sleep={flag.sleep} unconscious_h={flag.unconscious_h} is_h={flag.is_h} is_follow={flag.is_follow})"
        f" 完成={cid in cache.over_behavior_character}"
    )


print("== 读档体检 ==")
print("game_time:", cache.game_time)
for _cid in [0, *sorted(WATCH)]:
    print(" ", describe(_cid))

# 按需制造前置条件，例如把玩家搬到观察角色所在场景、压低熟睡度：
# map_handle.character_move_scene(pl.position, cache.character_data[next(iter(WATCH))].position, 0)
# cache.character_data[next(iter(WATCH))].sleep_point = 20

# ==== 2. 随机 ====
random.seed(1)
# True：只把 randint(1, 100) 的结果固定为 1，抽到 1 就命中的判定必中（如 rate >= randint(1, 100) 在 rate 至少为 1 时）；
# 其他范围的 randint 照常随机（全换成下界会让 born_new_character 找空 id 的循环永不结束）
FORCE_RANDINT_MIN = False
if FORCE_RANDINT_MIN:
    _real_randint = random.randint
    random.randint = lambda a, b: (
        1 if (a, b) == (1, 100) else _real_randint(a, b)
    )

# ==== 3. 复刻玩家指令（不进真实主循环） ====
BEHAVIOR = constant.Behavior.PLAY_INSTRUMENT
# 指令处理函数给 chara_handle_instruct_common_settle 传了非 0 的 duration= 时填那个值（如等待五分钟是 5）；
# 没传或传 0 时用查表值，与游戏一样不足 1 记 1
DURATION = max(game_config.config_behavior[BEHAVIOR].duration, 1)

# 处理函数不调 chara_handle_instruct_common_settle、自己赋值时（如 handle_teach 设 STATUS_TEACH、拉学生听课），
# 把下面四行换成它的赋值
instuct_judege.init_character_behavior_start_time(0, cache.game_time)
pl.state = BEHAVIOR  # chara_handle_instruct_common_settle 也把 state 设为行为id
pl.behavior.behavior_id = BEHAVIOR
pl.behavior.duration = DURATION
game_time.sub_time_now(
    pl.behavior.duration
)  # 真实流程也是先推进时间再进入行为循环
print(
    f"== 模拟指令 {BEHAVIOR} dur={pl.behavior.duration} | 推进后 game_time: {cache.game_time} =="
)


# ==== 4. 逐轮内窥：对 WATCH 中的角色打印被包装函数调用前后的状态 ====
def probe(module, func_name):
    """
    包装 module.func_name（首个参数须为角色id），对 WATCH 中的角色打印调用前后的状态
    Keyword arguments:
    module -- 函数所在模块；character_behavior 经 handle_npc_ai.xxx 调用，替换模块属性即生效
    func_name -- 函数名
    Return arguments:
    无
    """
    original = getattr(module, func_name)

    def wrapper(cid, *args, **kwargs):
        """
        被包装后的函数：调用原函数，并对观察角色打印前后状态
        Keyword arguments:
        cid -- 角色id
        args / kwargs -- 原样传给原函数的其余参数
        Return arguments:
        原函数的返回值
        """
        if cid not in WATCH:
            return original(cid, *args, **kwargs)
        before = describe(cid)
        result = original(cid, *args, **kwargs)
        print(
            f"    [{func_name}] 返回={result!r}\n      前: {before}\n      后: {describe(cid)}"
        )
        return result

    setattr(module, func_name, wrapper)


ENABLE_PROBE = True
if ENABLE_PROBE and WATCH:
    probe(handle_npc_ai, "find_character_target")
    probe(handle_npc_ai, "judge_interrupt_character_behavior")
    probe(
        handle_npc_ai, "judge_student_leave_truncate"
    )  # 学生赶去上课的截短，在实时结算之前调用

# ==== 5. 内存模拟候选修复（改源码前先在这里验证收敛） ====
# _original = handle_npc_ai.judge_interrupt_character_behavior
# def _patched(cid):
#     if <候选修复条件>:
#         return 0
#     return _original(cid)
# handle_npc_ai.judge_interrupt_character_behavior = _patched

# ==== 6. 带护栏地跑真实的行为循环 init_character_behavior ====
PASS_LIMIT = 100  # 真死循环每轮约 0.1 秒，100 轮也只要十来秒
WARN_PASSES = 10


class PassLimitReached(Exception):
    """某个角色跑满 PASS_LIMIT 轮仍未完成，由护栏抛出以中止真实循环"""


saved_ids: list[str] = []


def skip_save(save_id):
    """
    替换 save_handle.establish_save：只记下存档编号，不写文件（玩家睡觉时真实循环会自动存档）
    Keyword arguments:
    save_id -- 存档编号
    """
    saved_ids.append(save_id)


def skip_file_write(path, mode="r", *args, **kwargs):
    """
    替换 field_commission_function 模块里的 open：写模式丢进内存，
    读模式照常打开（临时委托会追加写 data/csv/Commission.csv）
    Keyword arguments:
    path -- 文件路径
    mode -- 打开模式
    Return arguments:
    文件对象；写模式时为丢弃内容的 io.StringIO
    """
    if any(flag in mode for flag in "wax+"):
        return io.StringIO()
    return open(path, mode, *args, **kwargs)


save_handle.establish_save = skip_save
field_commission_function.open = skip_file_write

pass_count: dict[int, int] = {}
"""每个角色已被 character_behavior 结算的轮数；真实循环每轮对每个未完成的角色各调用一次"""
real_character_behavior = character_behavior.character_behavior


def guarded_character_behavior(cid, now_time, pl_start_time):
    """
    包装 character_behavior：按角色计轮，跑满 PASS_LIMIT 轮仍要再跑时抛出 PassLimitReached；
    对 WATCH 中的 NPC 打印每轮前后状态
    Keyword arguments:
    cid -- 角色id
    now_time -- 当前时间
    pl_start_time -- 玩家行为开始时间
    """
    if pass_count.get(cid, 0) >= PASS_LIMIT:
        raise PassLimitReached(f"{describe(cid)} 跑满 {PASS_LIMIT} 轮仍未完成")
    pass_count[cid] = pass_count.get(cid, 0) + 1
    if cid in WATCH:
        print(f"[NPC 第{pass_count[cid]}轮] 前: {describe(cid)}")
    real_character_behavior(cid, now_time, pl_start_time)
    if cid in WATCH:
        print(f"[NPC 第{pass_count[cid]}轮] 后: {describe(cid)}")


character_behavior.character_behavior = (
    guarded_character_behavior  # init_character_behavior 按模块全局名调用它
)
limit_error = None
# 指令经 update.game_update_flow 进入行为循环：cache.game_update_flow_running >= 2 时它直接返回（update.py:15），
# 否则加 1 再进入循环（update.py:19-20），结束后恢复（update.py:30）。所以指令的循环里计数是 1：
# 嵌套的 game_update_flow 还会再跑一层循环，
# 那一层里再嵌套的直接返回。这里照样加 1，结束后恢复
caller_depth = cache.game_update_flow_running
cache.game_update_flow_running = caller_depth + 1
try:
    character_behavior.init_character_behavior()
except PassLimitReached as error:
    limit_error = error
finally:
    cache.game_update_flow_running = caller_depth
player_passes = pass_count.get(0, 0)
npc_passes = max((n for cid, n in pass_count.items() if cid != 0), default=0)
player_stuck = 0 not in cache.over_behavior_character
id_list = cache.npc_id_got - {0}
# 时停中真实循环结算完玩家就回退时间、不进 NPC 阶段，NPC 本来就不会完成
npc_unfinished = (
    []
    if cache.time_stop_mode
    else sorted(id_list - cache.over_behavior_character)
)

# ==== 7. 结果 ====
print()
print(
    f"玩家阶段轮数: {player_passes} | NPC阶段轮数: {npc_passes} | 上限 {PASS_LIMIT}"
)
print(
    f"循环结束后 game_time: {cache.game_time} | 时停: {cache.time_stop_mode} | 被跳过的存档: {saved_ids or '无'}"
)
if limit_error:
    print("!! 护栏中止了循环:", limit_error)
for phase, passes in (("玩家", player_passes), ("NPC", npc_passes)):
    if passes >= WARN_PASSES:
        print(f"!! 提醒：{phase}阶段用了 {passes} 轮，请与未修复基线的轮数对比")
for cid in sorted(WATCH):
    print("最终:", describe(cid))
shown = [t.strip() for t in captured_texts]
print("屏幕文字:", shown if shown else "无")
check("玩家阶段收敛", not player_stuck, describe(0))
check(
    "NPC阶段收敛",
    not npc_unfinished,
    f"未完成(前8个): {[(c, cache.character_data[c].name) for c in npc_unfinished[:8]]}",
)
finish()
