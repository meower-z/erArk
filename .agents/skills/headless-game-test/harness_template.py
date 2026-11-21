# -*- coding: UTF-8 -*-
"""
erArk 无头行为循环诊断模板
==========================
读档入内存，让玩家下一条真实指令，再带护栏地让内核一步一步推进（core.step），直到玩家下一次选行动。
运行中可以查看指定角色每次选行动、开始行动前后的状态，也可以在内存里模拟候选修复。
游戏世界取自被测 checkout 的 tests/world.py：FullWorld 完整启动游戏（结算器、状态机、界面流程），
玩家输入由 world.player 给出。
本脚本不存档：循环里会写文件的两处（玩家睡觉时的自动存档、临时外勤委托追加写 Commission.csv）被替换掉；
但 FullWorld 启动时的 import auto_build_config 会在 CSV 变动时增量重建 data/ 下的生成物。

用法：按 ==== 分段标记修改后，从仓库根目录运行（外层必须加 timeout，输出重定向到文件再读）：
    timeout 600 ./.conda/python.exe -u harness_template.py > <scratchpad>/run.log 2>&1
需要存档：先把要读的存档放进 save/，再把 SAVE_ID 改成它的编号。

退出码：0 推进到了玩家下一次选行动；1 时钟停在同一分钟超过步数上限（卡死），或玩家的指令没有开始；
2 未捕获异常（存档不存在、推进中要玩家选择而没有安排输入，都落在这里）。
判读：各角色开始行动的次数与内核步数随指令时长增长；是否异常以同一存档、同一指令的未修复基线为准。
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
# 推进中要玩家选择时，按 world.player.press("按钮文字的一部分") 事先安排；没安排就抛 UnplannedInput（退出码 2），
# 并列出屏幕上的按钮

from Script.Core import io_init, save_handle
from Script.Design import character_behavior, game_time, handle_npc_ai
from Script.Kernel import core
from Script.Modules.domains import flags, modes, needs
from Script.System.Field_Commission_System import field_commission_function
from Script.System.Instruct_System import handle_instruct
from tests.world import act

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
    kernel = core.state().characters.get(str(cid))
    end = (
        game_time.at(kernel.action.start + kernel.action.duration)
        if kernel
        else "不在内核里"
    )
    n = needs.of(cid)
    return (
        f"{cd.name}(id{cid}) 位置={cd.position} bhv={cd.behavior.behavior_id} dur={cd.behavior.duration}"
        f" start={cd.behavior.start_time} state={cd.state} tired={n['tired']} sleep={n['sleep']}"
        f" hp={n['hit']}/{n['hit_max']} mp={n['mana']}/{n['mana_max']}"
        f" sp_flag(sleep={flags.get(cid, 'sleep')} unconscious_h={flags.get(cid, 'unconscious_h')}"
        f" is_h={flags.get(cid, 'is_h')} is_follow={flags.get(cid, 'is_follow')})"
        f" 内核行动结束于={end}"
    )


print("== 读档体检 ==")
print("game_time:", game_time.now())
for _cid in [0, *sorted(WATCH)]:
    print(" ", describe(_cid))

# 按需制造前置条件，例如把玩家搬到观察角色所在场景、压低熟睡度：
# map_handle.character_move_scene(pl.position, cache.character_data[next(iter(WATCH))].position, 0)
# from tests import kernel_data; kernel_data.set_needs(next(iter(WATCH)), sleep=20)

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

# ==== 3. 玩家的指令：act 里玩家第一次选行动时调用它，指令经 player_pick.choose 定下玩家的行动 ====
# 换成被测指令的处理函数（Script/System/Instruct_System/handle_instruct.py 里 @add_instruct 的函数）；
# 指令要面板选择时，先按 world.player.press 安排好输入
INSTRUCT = handle_instruct.handle_play_instrument


# ==== 4. 内窥：对 WATCH 中的角色打印被包装函数调用前后的状态 ====
def probe(module, func_name):
    """
    包装 module.func_name（首个参数须为角色id），对 WATCH 中的角色打印调用前后的状态
    Keyword arguments:
    module -- 函数所在模块；内核模块按 module.func_name 调用它，替换模块属性即生效
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
    probe(handle_npc_ai, "choose_state_machine")  # 干员选下一个行动的状态机
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

# ==== 6. 带护栏地推进内核：act 一步一步调用 core.step，直到玩家下一次选行动 ====
STEP_LIMIT = 500  # 时钟停在同一分钟时最多推进的步数；真死循环每步约 0.1 秒以内


class StepLimitReached(Exception):
    """时钟停在同一分钟已推进 STEP_LIMIT 步，由护栏在下一步之前抛出以中止推进"""


saved_ids: list[str] = []


def skip_save(save_id):
    """
    替换 save_handle.establish_save：只记下存档编号，不写文件（玩家睡觉后自动存档）
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
# 模块里的 open 读的是模块全局名，没有就落到内置的 open
vars(field_commission_function)["open"] = skip_file_write

starts: dict[int, int] = {}
"""每个角色开始行动的次数（character_behavior.settle_start 的调用数）"""
same_minute: dict[int, int] = {}
"""时钟停在当前这一分钟以来，每个角色开始行动的次数"""
steps = 0
"""内核推进的步数"""
stalled = 0
"""时钟停在当前这一分钟以来的步数"""
real_settle_start = character_behavior.settle_start
real_step = core.step


def counted_settle_start(cid, minutes):
    """
    包装 settle_start：按角色计开始行动的次数，对 WATCH 中的角色打印开始前后的状态
    Keyword arguments:
    cid -- 角色id
    minutes -- 行动的分钟数
    """
    starts[cid] = starts.get(cid, 0) + 1
    same_minute[cid] = same_minute.get(cid, 0) + 1
    if cid in WATCH:
        print(f"[开始行动 第{starts[cid]}次] 前: {describe(cid)}")
    real_settle_start(cid, minutes)
    if cid in WATCH:
        print(f"[开始行动 第{starts[cid]}次] 后: {describe(cid)}")


def guarded_step():
    """
    包装 core.step：计步；时钟停在同一分钟跑满 STEP_LIMIT 步仍要再推进时抛出 StepLimitReached
    """
    global steps, stalled
    if stalled >= STEP_LIMIT:
        busiest = sorted(same_minute.items(), key=lambda kv: -kv[1])[:5]
        raise StepLimitReached(
            f"时钟停在 {game_time.now()} 已推进 {stalled} 步；这一分钟开始行动最多的角色: {busiest}"
        )
    clock = core.state().clock
    real_step()
    steps += 1
    if core.state().clock == clock:
        stalled += 1
    else:
        stalled = 0
        same_minute.clear()


character_behavior.settle_start = (
    counted_settle_start  # 开始行动经 character_behavior.settle_start 调用它
)
core.step = guarded_step  # act 按 core.step 调用它
limit_error = None
clock_before = game_time.now()
try:
    act(INSTRUCT)
except StepLimitReached as error:
    limit_error = error

# ==== 7. 结果 ====
print()
print(
    f"内核步数: {steps} | 玩家开始行动: {starts.get(0, 0)} 次 | 干员开始行动最多: "
    f"{max((n for cid, n in starts.items() if cid != 0), default=0)} 次 | 同一分钟步数上限 {STEP_LIMIT}"
)
print(
    f"game_time: {clock_before} -> {game_time.now()} | 时停: {modes.time_stop()} | 被跳过的存档: {saved_ids or '无'}"
)
if limit_error:
    print("!! 护栏中止了推进:", limit_error)
for cid in sorted(WATCH):
    print("最终:", describe(cid), f"开始行动 {starts.get(cid, 0)} 次")
shown = [t.strip() for t in captured_texts]
print("屏幕文字:", shown if shown else "无")
check("玩家的指令开始了", starts.get(0, 0) >= 1, describe(0))
check("推进到了玩家下一次选行动", limit_error is None, str(limit_error))
finish()
