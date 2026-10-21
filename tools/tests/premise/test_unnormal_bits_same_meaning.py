# -*- coding: UTF-8 -*-
"""
异常位3~6的短路求值与完整定义一致的测试
=======================================
异常位1~7每次读取时现算。为了现算便宜，handle_normal_3~6 先查便宜的条件：
位3先看助理和跟随，只有排了体检或在等待名单上时才判体检行动链；
位4只查5/6/8/9类衣物（全裸必然大致全裸）；
位5、6先看unconscious_h与时停，只有睡觉或睡眠无意识时才算睡眠等级，只有醉酒值大于0时才算醉酒等级。
这些只改变求值顺序，判定结果必须等于各位的完整定义（各叶子前提的「或」，写在本测试的 full_bit3~6 里）。
本测试随机生成角色状态，逐个对照完整定义与 handle_normal_3~6，两者必须处处相同；
再对照组合判定 normal_all 与 unnormal 是否等于逐位判定的「全部正常」与「任一异常」。

在仓库根目录运行：python tools/tests/premise/test_unnormal_bits_same_meaning.py
退出码：0 全部断言通过；1 有断言失败；2 未捕获异常。
"""
import datetime
import random
import sys

sys.path.insert(0, "tools/tests")
from headless_boot import boot, check, finish, mute_ui, new_chara  # noqa: E402

cache = boot()
mute_ui()

from Script.Config import game_config  # noqa: E402
from Script.Core import constant  # noqa: E402
from Script.Design import basement, handle_premise as HP  # noqa: E402

SAMPLES = 4000
rng = random.Random(20261021)

cache.rhodes_island = basement.get_base_zero()
basement.get_base_updata()
player = new_chara(0, "博士")
operator = new_chara(1, "干员")

# 每类衣物可选的衣服id，另加两个「仍算全裸」的特例：只戴项圈（3类352）、只戴戒指（7类751）
CLOTH_BY_TYPE = {}
for cloth_id, cloth in game_config.config_clothing_tem.items():
    CLOTH_BY_TYPE.setdefault(cloth.clothing_type, []).append(cloth_id)
SLEEP_POINTS = [0, 1, 29, 30, 31, 59, 60, 61, 80, 81, 100]
DRUNK_POINTS = [-10, 0, 1, 2, 4, 5, 13, 15, 19, 20, 21, 40, 50, 51, 66, 80, 81, 100, 120, 200, 800]


def full_bit3(cid):
    """位3的完整定义：助理、跟随、体检行动链任一成立即异常"""
    return bool(HP.handle_is_assistant(cid) or HP.handle_is_follow(cid) or HP.handle_self_in_health_check_action_chain(cid))


def full_bit4(cid):
    """位4的完整定义：全裸或大致全裸即异常"""
    return bool(HP.handle_cloth_off(cid) or HP.handle_cloth_most_off(cid))


def full_bit5(cid):
    """位5的完整定义：睡眠半梦半醒（且在睡觉或睡眠无意识）、醉酒、平然任一成立即异常"""
    return bool(
        (HP.handle_sleep_level_0(cid) and (HP.handle_action_sleep(cid) or HP.handle_unconscious_flag_1(cid)))
        or HP.handle_drunk_level_2(cid)
        or HP.handle_unconscious_flag_4(cid)
    )


def full_bit6(cid):
    """位6的完整定义：睡眠等级≥1（且在睡觉或睡眠无意识）、空气、烂醉、时停任一成立即异常"""
    return bool(
        (HP.handle_sleep_level_ge_1(cid) and (HP.handle_action_sleep(cid) or HP.handle_unconscious_flag_1(cid)))
        or HP.handle_unconscious_flag_5(cid)
        or HP.handle_drunk_level_3(cid)
        or (HP.handle_time_stop_on(cid) or HP.handle_unconscious_flag_3(cid))
    )


def randomize():
    """随机生成一组会影响位1~7的状态"""
    hour = rng.randrange(24)
    operator.behavior.start_time = datetime.datetime(2020, 12, 22, hour, rng.choice([0, 30]))
    operator.behavior.behavior_id = rng.choice([constant.Behavior.SLEEP, constant.Behavior.SHARE_BLANKLY, constant.Behavior.WAIT])
    operator.sp_flag.unconscious_h = rng.randrange(8)
    operator.sp_flag.is_follow = rng.choice([1, 2, 3, 4]) if rng.random() < 0.15 else 0
    player.assistant_character_id = 1 if rng.random() < 0.15 else 0
    operator.action_info.health_check_today = rng.randrange(4)
    waiting = cache.rhodes_island.waiting_for_exam_operator_ids
    waiting.discard(1)
    if rng.random() < 0.3:
        waiting.add(1)
    operator.sleep_point = rng.choice(SLEEP_POINTS)
    operator.drunk_point = rng.choice(DRUNK_POINTS)
    for talent_id in range(350, 360):
        if talent_id in operator.talent:
            operator.talent[talent_id] = 1 if rng.random() < 0.15 else 0
    cache.time_stop_mode = rng.random() < 0.2
    for clothing_type in game_config.config_clothing_type:
        roll = rng.random()
        if roll < 0.45:
            operator.cloth.cloth_wear[clothing_type] = []
        elif clothing_type == 3 and roll < 0.6:
            operator.cloth.cloth_wear[clothing_type] = [352]
        elif clothing_type == 7 and roll < 0.6:
            operator.cloth.cloth_wear[clothing_type] = [751]
        else:
            operator.cloth.cloth_wear[clothing_type] = [rng.choice(CLOTH_BY_TYPE[clothing_type])]


mismatch = {3: [], 4: [], 5: [], 6: [], "normal_all": [], "unnormal": []}
abnormal_count = {3: 0, 4: 0, 5: 0, 6: 0}
FULL = {3: full_bit3, 4: full_bit4, 5: full_bit5, 6: full_bit6}
NEW = {3: HP.handle_normal_3, 4: HP.handle_normal_4, 5: HP.handle_normal_5, 6: HP.handle_normal_6}
ALL_BITS = [HP.handle_normal_1, HP.handle_normal_2, HP.handle_normal_3, HP.handle_normal_4, HP.handle_normal_5, HP.handle_normal_6, HP.handle_normal_7]
for n in range(SAMPLES):
    randomize()
    for bit in (3, 4, 5, 6):
        full = FULL[bit](1)
        new = not NEW[bit](1)
        abnormal_count[bit] += full
        if full != new and len(mismatch[bit]) < 5:
            mismatch[bit].append((n, full, new, operator.sp_flag.unconscious_h, operator.behavior.behavior_id, operator.sleep_point, operator.drunk_point))
    per_bit_normal = [bool(f(1)) for f in ALL_BITS]
    if bool(HP.handle_normal_all(1)) != all(per_bit_normal) and len(mismatch["normal_all"]) < 5:
        mismatch["normal_all"].append((n, per_bit_normal))
    if bool(HP.handle_unnormal(1)) != (not all(per_bit_normal)) and len(mismatch["unnormal"]) < 5:
        mismatch["unnormal"].append((n, per_bit_normal))

for bit in (3, 4, 5, 6):
    check(f"位{bit}：{SAMPLES} 组随机状态下与完整定义相同（其中 {abnormal_count[bit]} 组为异常）", not mismatch[bit] and 0 < abnormal_count[bit] < SAMPLES, mismatch[bit])
check("normal_all 等于位1~7全部正常", not mismatch["normal_all"], mismatch["normal_all"])
check("unnormal 等于位1~7任一异常", not mismatch["unnormal"], mismatch["unnormal"])
check("玩家的位1~7恒为正常，unnormal 恒不成立", all(f(0) == 1 for f in ALL_BITS) and HP.handle_unnormal(0) == 0)

finish()
