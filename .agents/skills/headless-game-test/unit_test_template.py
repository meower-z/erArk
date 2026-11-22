# -*- coding: UTF-8 -*-
"""
erArk 无头**函数级单元测试** harness 模板
=========================================
用途：不读存档、不跑行为循环，自建角色 fixture 后直接调用前提函数 / 结算器 / 换装函数 /
      口上系统做断言。适合验证「新增的前提是否注册且判定正确」「新结算器数值是否落地」
      「效果链顺序是否符合预期」这类改动。

排查死循环、复刻指令、跑行为循环请改用同目录的 `harness_template.py`。

用法（从仓库根目录）：
    timeout 300 ./.conda/python.exe -u .agents/skills/headless-game-test/unit_test_template.py
    观察长输出时**不要接 `| tail`**，改为重定向到文件后再 cat（见 SKILL.md「输出观察」）。

注意：
  - 必须用 ./.conda/python.exe（裸 python 是商店空壳别名，exit 49 无输出）
  - 结尾的 os._exit() 按断言结果设退出码：全部通过时为 0，有失败时为 1
"""

import datetime
import io
import os
import random
import sys

sys.path.insert(0, os.getcwd())
# 从终端、管道或重定向文件运行时 sys.stdout 都是 TextIOWrapper
assert isinstance(sys.stdout, io.TextIOWrapper)
sys.stdout.reconfigure(
    encoding="utf-8", errors="replace"
)  # Windows GBK 控制台防乱码

FAIL: list[str] = []
PASS = 0


def check(name: str, cond: object, extra: object = "") -> None:
    """
    记录一条断言结果
    Keyword arguments:
    name -- 断言名
    cond -- 断言条件
    extra -- 失败时附带打印的实际值
    Return arguments:
    无
    """
    global PASS
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL.append(name)
        print(f"  [FAIL] {name} {extra}")


# ==== 1. 初始化链（照抄 game.py 顺序，顺序不能乱） ====
import auto_build_config  # noqa: F401,E402  增量构建游戏数据
from Script.Config import normal_config  # noqa: E402
from Script.Core import game_type, cache_control  # noqa: E402

cache_control.cache = game_type.Cache()  # 必须在 game_config.init() 之前
# 断言不受本机 config.local.ini 影响
os.environ[normal_config.DEFAULTS_ONLY_ENV] = "1"
normal_config.init_normal_config()
from Script.Config import game_config, character_config  # noqa: E402

game_config.init()
character_config.init_character_tem_data()
from Script.Config import map_config  # noqa: E402

map_config.init_map_data()
from Script.Design import (  # noqa: E402
    attr_calculation,
    character_behavior,
    clothing,
    game_time,
    handle_premise,
    instuct_judege,
    map_handle,
    settle_behavior,
)
import Script.Settle  # noqa: F401,E402  注册全部结算器（缺了会 KeyError）
import Script.StateMachine  # noqa: F401,E402  注册全部状态机
from Script.Core import (
    constant,
    constant_effect,
    flow_handle,
    save_handle,
)  # noqa: F401,E402
from Script.UI.Moudle import draw  # noqa: E402

from Script.Modules.domains import activity, identity, relations
from Script.Modules.save_load import kernel_state
from Script.Modules.domains import abilities, status
from tests import chara_data, kernel_data

kernel_state.reset_clock(kernel_state.first_clock())
cache = cache_control.cache

# ==== 2. 全局前置（不做这两件事会在结算里 KeyError） ====
# 数值结算会读全局设置 normal_config.system_setting 的各项，System_Setting() 默认是空壳
normal_config.system_setting = attr_calculation.get_system_setting_zero()
# 场景路径必须是 cache.scene_data 里真实存在的键；["0"] 之类的占位值会让关门/移动类结算 KeyError
SCENE = ["宿舍", "1区", "101"]
PREV_SCENE = ["宿舍", "1区", "0"]
assert map_handle.get_map_system_path_str_for_list(SCENE) in cache.scene_data

# ==== 3. 屏蔽 UI ====
for _n in dir(draw):
    _c = getattr(draw, _n)
    if isinstance(_c, type) and hasattr(_c, "draw"):
        try:
            _c.draw = lambda self, *a, **k: None
        except Exception:
            pass
# askfor_all 返回第一个可选项：面板的 `while 1: ... if yrn in return_list: break` 按钮循环才能退出
flow_handle.askfor_all = lambda return_list, *a, **k: (
    return_list[0] if return_list else ""
)
flow_handle.askfor_wait = lambda *a, **k: None

# 记录 WaitDraw 文本，供「某段提示是否被绘制」类断言使用
messages: list[str] = []


def record_draw(self: draw.WaitDraw, *a: object, **k: object) -> None:
    """
    记录型 WaitDraw 桩：把绘制文本收进 messages
    Keyword arguments:
    self -- 绘制对象
    Return arguments:
    无
    """
    if getattr(self, "text", None):
        messages.append(str(self.text))


setattr(draw.WaitDraw, "draw", record_draw)

print("初始化完成，游戏时间 =", game_time.now())


# ==== 4. 角色 fixture ====
def new_chara(
    cid: int, name: str = "测试干员", adv: int = 0, race: int = 0
) -> identity.Identity:
    """
    构造一个能跑通结算/前提/口上的最小角色
    Keyword arguments:
    cid -- 角色id（0 为玩家）
    name -- 角色名
    adv -- 剧情npc编号，影响可穿服装的筛选
    race -- 种族id（生育方式等按 game_config.config_race[race] 判定，测卵生/多胎时显式传入）
    Return arguments:
    identity.Identity -- 已写入角色身份表（identity.characters）的角色身份
    功能描述:
        角色在 GameState 里的多项字典默认是空的，代码里普遍直接用下标访问，不预填会报 KeyError。
        这里填入跑通「结算器 + 前提 + talk.handle_talk」全链路所需的最小数据集合。
        置零函数的命名不规律，容易记错（见 SKILL.md「fixture 字段与置零函数对照表」）。
    """
    talent = abilities.talent(cid)
    kernel_data.put(
        relations.favorability.set, cid, {0: 0}
    )  # 一些前提直接读 favorability[0]，表里要有键 0
    kernel_data.put(activity.set_position, cid, list(SCENE))
    kernel_data.put(
        identity.put,
        identity.Identity(cid, name=name, sex=1, adv=adv, race=race),
    )
    # 能力、经验、宝珠与素质表在 GameState 里，一步之外的写入要放在 kernel_data.writing 里
    with kernel_data.writing():
        talent.replace(attr_calculation.get_talent_zero({}))
        abilities.ability(cid).replace(attr_calculation.get_ability_zero({}))
        abilities.juel(cid).replace(attr_calculation.get_juel_zero({}))
        experience = attr_calculation.get_experience_zero({})
        abilities.experience(cid).replace(experience)
        # 罩杯素质 121~125 至少一个为 1，否则胸部成长/乳汁上限处 UnboundLocalError
        talent[121] = 1
    # 服装（含两个衣柜）、状态值与身体管理存在内核状态里，由 chara_data.seed 置零
    chara_data.seed(cid, {})
    return identity.of(cid)


pl = new_chara(0, "博士")

# ==== 5. 断言区（按需替换） ====
print()
print("========== 示例断言 ==========")

# 5.1 注册断言：新前提 / 新结算器 / 新行为 / 新口上是否都进了运行时与生成物
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

# 5.2 效果链顺序断言（改过 Behavior_Effect.csv 时用）
chain = [
    e
    for e in game_config.config_behavior_effect_data.get("sleep", [])
    if isinstance(e, int)
]
print("  sleep 效果链:", chain)

# 5.3 直接调用结算器：constant.settle_behavior_effect_data[效果id](角色id, add_time, change_data, now_time)
#     add_time 传 0 会命中绝大多数结算器开头的 `if not add_time: return`，断言会假阴性
target = new_chara(101, "样例干员")
kernel_data.put(activity.set_target, pl.cid, 101)
change = game_type.CharacterStatusChange()
# 结算器写内核状态。一步之外调用时，kernel_data.written 在调用结束后把写入套用到内核状态上
kernel_data.written(
    constant.settle_behavior_effect_data[62], 0, 1, change, game_time.now()
)  # 交互对象增加少量反感
check(
    "结算器确实改动了数值",
    status.of(101).get(20, 0) > 0,
    f"disgust={status.of(101).get(20, 0)}",
)

# 5.4 前提函数：直接调 handle_premise.handle_xxx(cid)
check("前提返回值符合预期", handle_premise.handle_high_1(101) == 1)

# 5.5 控制随机分支：需要「概率判定必中」时整体替换 randint，用完记得还原
_orig_randint = random.randint
random.randint = lambda a, b: a
# ... 在这里调用带概率判定的函数 ...
random.randint = _orig_randint


# 5.6 可记录、可控序列的 randint 桩：验证「调了几次随机、每次的范围、按序命中/不命中」
class RandStub:
    """
    记录型 randint 桩
    Keyword arguments:
    seq -- 依次返回的值序列，耗尽后返回上界（概率判定不命中）
    功能描述:
        每次调用把 (a, b) 追加到 calls，便于断言随机调用次数与参数；
        按阈值探测概率：第 i 轮返回 int(p_i) 应命中、int(p_i)+1 应不命中
    """

    def __init__(self, seq: list[int]) -> None:
        """
        把依次返回的值序列复制成列表记下
        Keyword arguments:
        seq -- 依次返回的值序列
        """
        self.seq = list(seq)

    def __call__(self, a: int, b: int) -> int:
        """
        把 (a, b) 追加到模块级的 calls，返回序列里的下一个值，序列耗尽后返回 b
        Keyword arguments:
        a -- 下界
        b -- 上界
        Return arguments:
        int -- 序列里的下一个值，或 b
        """
        calls.append((a, b))
        return self.seq.pop(0) if self.seq else b


calls: list[tuple[int, int]] = []
random.randint = RandStub([1, 100])
check(
    "randint 桩按序返回",
    random.randint(1, 100) == 1
    and random.randint(1, 100) == 100
    and calls == [(1, 100), (1, 100)],
)
random.randint = _orig_randint

# 5.7 面板/事件级测试的打桩组见 SKILL.md「面板 / 事件级测试」：
#     直接调面板的 _draw_xxx_content() 而非 .draw()；input_name_func / achievement_flow / get_new_character 打桩；
#     cache.npc_id_got 非空且有 profession=3 的角色

# ==== 6. 汇总 ====
print()
print("=" * 50)
print(f"通过 {PASS} 项，失败 {len(FAIL)} 项")
for f in FAIL:
    print("  失败:", f)
print("=" * 50)
os._exit(0 if not FAIL else 1)  # 按断言结果设退出码
