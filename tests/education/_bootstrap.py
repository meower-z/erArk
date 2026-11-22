# -*- coding: UTF-8 -*-
"""
生长养成系统回归测试的公共引导

每个 test_*.py 开头从 _bootstrap 导入它用到的名字，即可拿到：
    已初始化的游戏配置与内核状态（不启动 Tk）、被屏蔽并可记录文本的绘制类、
    check() / section() / finish() 三个断言工具、make_character() 角色 fixture 工厂、
    set_time() / move_to() / open_all_classroom() / clear_schedules() 等环境工具。

铁律（详见 .agents/skills/headless-game-test/SKILL.md）：
    1. 脚本末尾必须调用 finish()。它打印汇总行，并按断言结果设退出码。
       慢速层的套件测试靠这两样判定脚本是否通过。
    2. 含中文的脚本一律写成文件跑，不要走 heredoc / stdin（GBK 会把中文喂坏）
    3. 只读：绝不调用 save_handle.establish_save()，不 inline 调用 init_character_behavior()
"""

import contextlib
import datetime
import io
import os
import random
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType
    from typing import NoReturn

    from Script.Kernel import core as kernel

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
os.chdir(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
assert isinstance(sys.stdout, io.TextIOWrapper)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PASS = 0
""" 已通过的断言数 """
FAIL: list[str] = []
""" 失败的断言名列表 """


def check(name: str, cond: object, extra: object = "") -> bool:
    """
    记录一条断言结果
    Keyword arguments:
    name -- 断言名
    cond -- 断言条件
    extra -- 失败时附带打印的实际值
    Return arguments:
    bool -- 断言是否通过
    """
    global PASS
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
        return True
    FAIL.append(name)
    print(f"  [FAIL] {name} {extra}")
    return False


def section(title: str) -> None:
    """
    打印一个分节标题
    Keyword arguments:
    title -- 标题
    Return arguments:
    无
    """
    print(f"\n==== {title} ====")


def finish() -> None:
    """
    打印汇总并结束进程：断言全部通过时退出码为 0，否则为 1
    Keyword arguments:
    无
    Return arguments:
    无
    """
    print()
    print("=" * 50)
    print(f"PASS={PASS} FAIL={len(FAIL)}")
    for name in FAIL:
        print("  -", name)
    sys.stdout.flush()
    os._exit(0 if not FAIL else 1)


# ==== 1. 初始化链（照 game.py 的顺序，顺序不能乱） ====
import auto_build_config  # noqa: F401,E402  增量构建游戏数据
from Script.Config import normal_config  # noqa: E402

normal_config.init_normal_config()
from Script.Config import game_config, character_config  # noqa: E402

game_config.init()
character_config.init_character_tem_data()
from Script.Config import map_config  # noqa: E402

map_config.init_map_data()
from Script.Design import (  # noqa: E402
    attr_calculation,
    game_time,
    handle_premise,
    map_handle,
    settle_behavior,
)
import Script.Settle  # noqa: F401,E402  注册全部结算器
import Script.StateMachine  # noqa: F401,E402  注册全部状态机
from Script.Core import (
    constant,
    constant_effect,
    constant_promise,
    flow_handle,
    get_text,
    save_handle,
)  # noqa: F401,E402
from Script.UI.Moudle import draw  # noqa: E402
from tests import chara_abilities as ca, chara_data, kernel_data, kernel_project
from tests import world
from tests.chara_activity import behave

_ = get_text._
""" 翻译api：配置里的名字都过了翻译，测试里比对名字一律包 _() """

from Script.Modules.save_load import kernel_state
from Script.Modules.domains import activity, body_manage, chara_key, chara_life
from Script.Modules.domains import education, facility, growth, inventory, modes
from Script.Modules.domains import identity, official, plan, playthrough
from Script.Modules.domains import pregnancy
from Script.Modules.domains import relations, roster, status, wardrobe
from Script.Modules.domains import warehouse
from tests.education._growth_ref import child_growth as child_growth

kernel_state.reset_clock(kernel_state.first_clock())

# ==== 2. 全局前置 ====
normal_config.system_setting = attr_calculation.get_system_setting_zero()
kernel_data.written(playthrough.reset_difficulty_and_birth)
kernel_data.written(warehouse.start, {})
# 教育测试允许单步外写入教育、名册、妊娠、养成、状态值、道具、食物背包、服装、身体管理与全部角色键（chara_key.BY_KEY）
chara_keys = (status.KEY, inventory.ITEMS, inventory.FOODS, wardrobe.KEY)
kernel_project.auto_commit_outside_step(
    {
        *education.KEYS,
        *roster.KEYS,
        pregnancy.KEY,
        growth.KEY,
        *chara_keys,
        body_manage.KEY,
        *chara_key.BY_KEY,
        *activity.KEYS,
    }
)
ca.auto_commit_outside_step()
# 书库：library.holders() 把配置里的每本书读作在架、没被借走；兴趣课读书要先借书（Plan 29）

# ==== 3. 屏蔽 UI，并把绘制文本收进 drawn_text ====
drawn_text: list[str] = []
""" 全部绘制类 draw() 时的文本记录，断言「某段提示是否被画出」时用；测试可自行 clear() """


def _record_draw(self: object, *args: object, **kwargs: object) -> None:
    """
    记录型绘制桩
    Keyword arguments:
    self -- 绘制对象
    Return arguments:
    无
    """
    # 标题线类（TitleLineDraw / LittleTitleLineDraw）的文字在 title 属性上
    text = getattr(self, "text", None) or getattr(self, "title", None)
    if text:
        drawn_text.append(str(text))


for _cls_name in dir(draw):
    _cls = getattr(draw, _cls_name)
    if isinstance(_cls, type) and hasattr(_cls, "draw"):
        with contextlib.suppress(Exception):
            _cls.draw = _record_draw
# askfor_all 默认返回第一个可选项，面板的按钮循环才退得出去；测试可自行替换
flow_handle.askfor_all = lambda return_list, *a, **k: (
    return_list[0] if return_list else ""
)
flow_handle.askfor_wait = lambda *a, **k: None

from Script.System.Education_System import (  # noqa: E402
    auto_schedule,
    baby_growth_handle,
    class_ai,
    education_constant,
    growth_event_handle,
    growth_handle,
    schedule_handle,
    schedule_template_handle,
    semester_handle,
    sex_class_handle,
)

# ==== 4. 环境工具 ====
DEFAULT_TIME = datetime.datetime(2026, 9, 7, 9, 0)
""" 默认游戏时间：2026-09-07 周一 09:00，秋季学期（9月）第一节课的开始时刻 """
SCENE_DORM = ["宿舍", "1区", "101"]
""" 一间真实宿舍 """
SCENE_EDU_ENTRY = ["教", "0"]
""" 教育区入口 """
SCENE_NURSERY = ["教", "育儿"]
""" 育儿室 """
assert (
    map_handle.get_map_system_path_str_for_list(SCENE_DORM)
    in constant.scene_data
)
assert (
    map_handle.get_map_system_path_str_for_list(SCENE_EDU_ENTRY)
    in constant.scene_data
)


def scene_str(path: list) -> str:
    """场景路径列表 → 场景路径字符串"""
    return map_handle.get_map_system_path_str_for_list(path)


def move_to(character_id: int, path: list) -> None:
    """
    直接将角色的 activity.position 设为目标场景路径（不走寻路）
    Keyword arguments:
    character_id -- 角色id
    path -- 目标场景路径列表
    Return arguments:
    无
    """
    kernel_data.put(activity.set_position, character_id, list(path))


def set_time(now_time: datetime.datetime) -> None:
    """
    设置游戏时间，并把全部角色的行为起始时间同步过去
    get_class_period 等函数读的是 behavior.start_time（默认是公元1年），不同步会永远算成不在节次内
    与真实游戏一致，游戏时间一律规整成 GameTime（按游戏日历计算）
    Keyword arguments:
    now_time -- 新的游戏时间
    Return arguments:
    无
    """
    now_time = game_time.to_game_time(now_time)
    world.set_clock(now_time)
    for character_data in identity.table().values():
        behave(character_data.cid, start_time=now_time)


def make_character(
    cid: int,
    name: str,
    work_type: int = 0,
    daughter: bool = False,
    stage: int = 0,
    mother_id: int = -1,
    position: list[str] | None = None,
    born_days: int = 30,
) -> identity.Identity:
    """
    造一个能跑通结算 / 前提 / 面板链路的最小角色 fixture，写入角色身份表并登记进场景，
    再把它的疲劳、饥饿、尿意、乳汁设为 0（吃饱、歇足），体力、气力与它们的上限设为 100
    Keyword arguments:
    cid -- 角色id（0 为玩家）
    name -- 角色名
    work_type -- 岗位id（151 教师 / 152 学生 / 153 保育员）
    daughter -- 是否为玩家的女儿（father_id = 0）
    stage -- 成长阶段素质id（101 至 104），0 为成年干员。stage 为 101 或 102 时不进在编名单
    mother_id -- 母亲的角色id
    position -- 初始场景路径，默认宿舍
    born_days -- 出生距今的游戏天数（成长天数用）
    Return arguments:
    identity.Identity -- 角色身份
    """
    relations.favorability.set(cid, {0: 0})
    relations.assistant_services.set(
        cid, attr_calculation.get_assistant_services_zero()
    )  # 实行值计算会读助理服务[8]
    ca.zero_tables(cid)
    ca.talent(cid)[121] = 1
    chara_life.work_type.set(cid, work_type)
    chara_life.dormitory.set(cid, scene_str(SCENE_DORM))
    behave(cid, start_time=game_time.now())
    if stage:
        ca.talent(cid)[stage] = 1
    if daughter:
        relations.father_id.set(cid, 0)
        relations.mother_id.set(cid, mother_id)
        if identity.exists(mother_id):
            with relations.child_id_list.editing(mother_id) as children:
                if cid not in children:
                    children.append(cid)
    where = list(position if position is not None else SCENE_DORM)
    kernel_data.put(activity.set_position, cid, where)
    kernel_data.put(identity.put, identity.Identity(cid, name=name, sex=1))
    chara_data.seed(cid, {})
    if daughter:
        pregnancy.update(
            cid,
            born_time=game_time.now() - datetime.timedelta(days=born_days),
        )
    kernel_data.set_needs(cid, tired=0, hunger=0, urine=0, milk=0)
    kernel_data.set_needs(cid, hit=100, hit_max=100, mana=100, mana_max=100)
    # 婴儿/幼女不进在编名册，与真实成长阶段边界一致
    if cid and stage not in (101, 102):
        roster.add(cid)
    return identity.of(cid)


def remove_character(cid: int) -> None:
    """
    把一个 fixture 角色从身份表与在编名册里撤掉
    Keyword arguments:
    cid -- 角色id
    Return arguments:
    无
    """
    if identity.exists(cid):
        kernel_data.put(identity.discard, cid)
    roster.discard(cid)


def open_all_classroom() -> None:
    """
    把 Facility_open.csv 里的全部房间置为已开放（10 间教室全开）
    Keyword arguments:
    无
    Return arguments:
    无
    """
    for open_cid in game_config.config_facility_open:
        kernel_data.set_room_open(open_cid, True)


def clear_schedules() -> None:
    """清空课表、临时实操课、日程模板与公务事件队列，供各组用例之间隔离"""
    education.clear_all()
    kernel_data.put(official.set_queue, [])
    kernel_data.put(official.set_history, {})
    kernel_data.set_world(modes.set_sex_class, False)
    kernel_data.set_world(modes.set_group_sex, False)


def classroom_path(classroom: str) -> list:
    """
    教室场景名 → 场景路径
    Keyword arguments:
    classroom -- 教室场景名
    Return arguments:
    list -- 场景路径
    """
    return schedule_handle.get_classroom_position(classroom)


def period_time(
    period: int, day: datetime.date | None = None
) -> datetime.datetime:
    """
    取某天某节次的开始时刻
    Keyword arguments:
    period -- 节次0~8
    day -- 日期，默认 DEFAULT_TIME 那天
    Return arguments:
    datetime.datetime -- 开始时刻
    """
    if day is None:
        day = DEFAULT_TIME.date()
    hour, minute = game_time.CLASS_PERIOD_START[period]
    return datetime.datetime(day.year, day.month, day.day, hour, minute)


_kernel_left: object = None
""" 上一次 play / start 停下时的 GameState：内核还是它时接着跑，不重新投影 """


def sync(keep_queue: bool = False) -> None:
    """
    内核状态不是上一次 play 停下时的那个（脚本改过游戏数据或拨过时钟）时，
    用 kernel_data.reprojected 在此刻重新投影。各角色的行动由 activity.behavior 投影，
    各角色留着自己的 GameState 数据。玩家的行为截在此刻，玩家第一步就选行动。
    计划队列清空（脚本直接调结算时排下、内核没跑过的计划）。干员当前行为的时长为 0 时，第一步就收尾、重新选
    Keyword arguments:
    keep_queue -- 为真时不清计划队列
    """
    from Script.Kernel import core
    from Script.Modules import load_order

    global _kernel_left
    core.load(load_order.LOAD_ORDER)
    if core.state() is not _kernel_left:
        behave(0, start_time=game_time.now(), duration=0)
        if not keep_queue:
            kernel_data.set_world(plan.clear_queues)
        core.reset_state(kernel_data.reprojected(core.state()))
        _kernel_left = core.state()


def play(
    fn: "Callable[[], object] | None" = None,
    stop_at_same_minute: bool = False,
    limit: int = 100000,
    keep_queue: bool = False,
) -> int:
    """先 sync(keep_queue) 再推进内核：玩家选行动时跑 fn，到下次选行动停下；fn 为 None 时队首行动照常开始
    Keyword arguments:
    fn -- 玩家选行动时跑的操作
    stop_at_same_minute -- 玩家定下行动后这一分钟各角色都开始行动即停下
    limit -- 步数上限（超限抛 RuntimeError）；keep_queue 为真时不清计划队列
    Return arguments:
    int -- 推进的步数
    """
    from Script.Kernel import core
    from Script.Modules.tk_ui import player_pick

    global _kernel_left
    ran = False

    def chooser() -> None:
        """玩家的选择：第一次跑 fn，之后结束推进"""
        nonlocal ran
        if fn is not None and not ran:
            ran = True
            fn()
        raise player_pick.LeftGame

    sync(keep_queue)
    saved, player_pick.chooser = player_pick.chooser, chooser
    steps = 0
    try:
        while True:
            if steps >= limit:
                raise RuntimeError(f"内核推进 {limit} 步还没停下")
            with kernel_project.stepping():
                core.step()
            steps += 1
            game = core.state()
            if (
                stop_at_same_minute
                and ran
                and all(
                    c.action.start + c.action.duration > game.clock
                    for c in game.characters.values()
                )
            ):
                break
    except player_pick.LeftGame:
        pass
    finally:
        player_pick.chooser = saved
        _kernel_left = core.state()
    return steps


def npc_turn(character_id: int, keep_queue: bool = False) -> None:
    """
    只让一名干员此刻选、开始下一个行动（PickNextAction、StartAction 走内核），别的角色不动：
    sync() 之后，内核里别的角色的行动延到很久以后，这名干员换成此刻用完的 0 分钟 kernel.Idle、
    不经行为的结束函数收尾（脚本造的角色没有结算过时间，收尾的结算会从很久以前算起）；
    这一步里事件的条件一律不成立。之后的 play / sync 由领域数据重新投影
    Keyword arguments:
    character_id -- 干员的角色id
    keep_queue -- 为真时不清计划队列（sync），队首的行动先开始
    """
    from dataclasses import replace
    from types import MappingProxyType

    from Script.Kernel import core
    from Script.Modules import load_order

    global _kernel_left
    sync(keep_queue)
    game = core.state()
    who = str(character_id)
    characters = {
        key: replace(
            c,
            action=(
                core.Action(key, core.idle.name, None, game.clock, 0)
                if key == who
                else replace(c.action, start=game.clock, duration=10**6)
            ),
        )
        for key, c in game.characters.items()
    }
    core.reset_state(replace(game, characters=MappingProxyType(characters)))
    core.load((*load_order.LOAD_ORDER, sys.modules[__name__]))
    try:
        with kernel_project.stepping():
            core.step()
    finally:
        core.load(load_order.LOAD_ORDER)
        _kernel_left = None


def _no_event(game: "kernel.GameState") -> "kernel.Intercept[None]":
    """
    npc_turn 里事件触发函数的输入钩子：一律不成立
    Keyword arguments:
    game -- 当前的 GameState
    Return arguments:
    Intercept -- 交回 None
    """
    from Script.Kernel import core

    return core.Intercept(None)


def _hook_events() -> None:
    """给内核登记过的每个事件的触发函数挂上 _no_event（只在 npc_turn 把本模块排进载入顺序时生效）"""
    from Script.Kernel import core
    from Script.Modules import load_order

    core.load(load_order.LOAD_ORDER)
    for name in core._events:
        core.input_hook(core.trigger(core.Event(name)))(_no_event)


def start(fn: "Callable[[], object]") -> int:
    """
    玩家此刻做 fn 里的操作，内核推进到这一分钟里各角色都开始了行动（时间前进之前）停下
    Keyword arguments:
    fn -- 玩家选行动时跑的操作
    Return arguments:
    int -- 推进的步数
    """
    return play(fn, stop_at_same_minute=True)


def wait(minute: int) -> int:
    """
    玩家此刻等待 minute 分钟，内核推进到玩家等完、要选下一个行动时停下
    Keyword arguments:
    minute -- 等待的分钟数
    Return arguments:
    int -- 推进的步数
    """
    from Script.Modules.tk_ui import player_pick

    return play(
        lambda: player_pick.choose(
            constant.Behavior.WAIT,
            minute,
            state=constant.CharacterStatus.STATUS_WAIT,
        )
    )


_hook_events()
set_time(DEFAULT_TIME)
pl = make_character(0, "博士")
""" 玩家 """


def _exit_on_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: "TracebackType | None",
) -> "NoReturn":
    """
    未捕获异常时打印回溯和崩溃汇总行，再以退出码 2 结束进程。退出码 2 与断言失败的退出码 1 区分开。
    Keyword arguments:
    exc_type -- 异常类型
    exc_value -- 异常对象
    exc_traceback -- 异常的回溯，没有时为 None
    Return arguments:
    不返回
    """
    import traceback

    traceback.print_exception(exc_type, exc_value, exc_traceback)
    print(f"\nPASS={PASS} FAIL={len(FAIL) + 1} (crashed)")
    sys.stdout.flush()
    os._exit(2)


sys.excepthook = _exit_on_exception

# `from _bootstrap import *` 默认不导出下划线开头的名字，而翻译函数 `_` 正是测试里最常用的一个
__all__ = [_name for _name in list(globals()) if not _name.startswith("__")]
