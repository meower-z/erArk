# -*- coding: UTF-8 -*-
"""
干员高潮口上里的人名回归测试
==========================
干员高潮时，second_behavior_effect 以高潮的干员为说话人调用 handle_second_talk，
口上里 {Name} 渲染为该干员，{TargetName} 渲染为她此刻的交互对象：H 中通常是她自己，也可能是博士。
本测试确认隐奸高潮口上与夕、澄闪、白金、歌蕾蒂娅的高潮口上，无论干员的交互对象是她自己还是博士，
都把高潮的人写成干员；B_climax 里替她掩护的人写成博士。

在仓库根目录运行：python tools/tests/talk/test_climax_line_names_operator.py
退出码：0 全部断言通过；1 有断言失败；2 未捕获异常。
"""
import re
import sys

sys.path.insert(0, "tools/tests")
from headless_boot import boot, check, finish, mute_ui, new_chara  # noqa: E402

cache = boot()
mute_ui()

from Script.Config import game_config  # noqa: E402
from Script.Core import game_type  # noqa: E402
from Script.Design import handle_premise, second_behavior, talk  # noqa: E402

DOC = "多克特"
""" 博士的名字：与口上里写死的“博士”区分开 """
OP = "测试干员"
""" 系统口上测试用干员的名字 """

player = new_chara(0, DOC)
# 纸娃娃地文的替换几率设为 0，让选中的口上原样输出（玩家可在设置里调成 0）
cache.all_system_setting.draw_setting[13] = 0

rendered = []
""" code_text_to_draw_text 每次的输出，按调用顺序追加 """
real_code_text_to_draw_text = talk.code_text_to_draw_text


def record_render(talk_text, character_id, common_talk_flag=False):
    """
    记录型包装：照常把口上代码转成文本，并把结果收进 rendered
    参数：talk_text (str) 原文本；character_id (int) 说话人id；common_talk_flag (bool) 是否纸娃娃地文
    返回：str 转化后的文本
    """
    text = real_code_text_to_draw_text(talk_text, character_id, common_talk_flag)
    rendered.append(text)
    return text


talk.code_text_to_draw_text = record_render
real_choice = talk.choice_talk_from_talk_data
pick = {"id": "", "candidates": set()}
""" 本轮要选中的口上id，以及前提筛出的候选口上 """


def choose_pinned(now_talk_data, behavior_id="share_blankly"):
    """
    记下候选口上，再只在要测的那条口上里选，其余选择逻辑照旧
    参数：now_talk_data (dict) 权重 -> 口上id集合；behavior_id (str) 行为id
    返回：tuple 与 choice_talk_from_talk_data 相同
    """
    pick["candidates"] = set().union(*now_talk_data.values()) if now_talk_data else set()
    if pick["id"] in pick["candidates"]:
        now_talk_data = {weight: {pick["id"]} for weight, ids in now_talk_data.items() if pick["id"] in ids}
    return real_choice(now_talk_data, behavior_id)


talk.choice_talk_from_talk_data = choose_pinned


def always_pass(premise_set, character_id, calculated_premise_dict, **kwargs):
    """
    让每条候选口上都通过前提（角色口上的能力、指令类前提与本测试无关）
    参数：premise_set (set) 前提集合；character_id (int) 角色id；calculated_premise_dict (dict) 已算过的前提
    返回：tuple[int, dict] 权重 1 与原样的已算前提
    """
    return 1, calculated_premise_dict


def climax_text(chara_id, behavior_id, talk_id, target_id, hidden_sex_mode=0, real_premise=True):
    """
    让干员经高潮结算入口触发一次二段高潮口上，返回渲染后的文本
    参数：chara_id (int) 干员id；behavior_id (str) 二段高潮行为id；talk_id (str) 要选中的口上id；
          target_id (int) 干员此刻的交互对象；hidden_sex_mode (int) 隐奸模式（博士与干员相同）；
          real_premise (bool) 是否按真实前提筛选候选口上
    返回：str 渲染后的口上文本；没选中该口上时返回空串
    """
    chara = cache.character_data[chara_id]
    chara.target_character_id = target_id
    player.target_character_id = chara_id
    player.sp_flag.hidden_sex_mode = hidden_sex_mode
    chara.sp_flag.hidden_sex_mode = hidden_sex_mode
    chara.second_behavior[behavior_id] = 1
    pick["id"] = talk_id
    rendered.clear()
    real_weight = handle_premise.get_weight_from_premise_dict
    if not real_premise:
        handle_premise.get_weight_from_premise_dict = always_pass
    try:
        # 与 check_second_effect 里 NPC 的高潮结算调用相同（orgasm_settle_flag=True）
        second_behavior.second_behavior_effect(chara_id, game_type.CharacterStatusChange(), [behavior_id], orgasm_settle_flag=True)
    finally:
        handle_premise.get_weight_from_premise_dict = real_weight
    if not check(f"{talk_id} 在候选口上里（交互对象 id{target_id}）", talk_id in pick["candidates"], f"candidates={sorted(pick['candidates'])[:5]}"):
        return ""
    text = next((t for t in rendered if t), "")
    print(f"     {talk_id} 交互对象 id{target_id}: {text[:80]}")
    return text


# ==== 1. 系统隐奸高潮口上：每个文件各渲染一条，A 文件两种隐奸模式各一条 ====
new_chara(1, OP)
cases = [
    ("a_orgasm_small", "second_climax_A_climax1180", 1, f"在公共场合中，{OP}看似正常地与他人交流"),
    ("a_orgasm_small", "second_climax_A_climax1201", 2, f"躲在隐蔽处的{OP}感受到肛门深处"),
    ("c_orgasm_small", "second_climax_C_climax1200", 1, f"让{OP}的身体微微颤抖"),
    ("v_orgasm_small", "second_climax_V_climax1220", 2, f"{OP}小穴中积累的快感"),
    ("b_orgasm_normal", "second_climax_B_climax1227", 2, f"隐藏在暗处的{OP}因胸部的强烈刺激而达到高潮"),
]
for target_id in (1, 0):
    for behavior_id, talk_id, mode, expect in cases:
        text = climax_text(1, behavior_id, talk_id, target_id, hidden_sex_mode=mode)
        check(f"{talk_id} 把高潮的人写成干员（交互对象 id{target_id}）", expect in text, f"text={text[:120]!r}")
    # B_climax 1227-1239 里另有一位替她掩护的人，那是博士
    check(f"B_climax1227 掩护的人是博士（交互对象 id{target_id}）", f"{DOC}不得不故意制造一些声响来掩盖{OP}无法控制的急促呼吸声" in text, f"text={text[-120:]!r}")

# ==== 2. 角色高潮口上：每个角色文件各渲染一条 ====
chara_cases = [
    (2015, "夕", "v_orgasm_strong", "chara_2015_夕18", f"随着{DOC}用力的一顶，夕的眼眸顿时打湿"),
    (377, "澄闪", "v_orgasm_small", "chara_0377_澄闪92", "澄闪嘗試忍住這種快感"),
    (204, "白金", "s_orgasm_strong", "chara_0204_白金1118", "呻吟着蜷缩着身体发抖的白金一下子润湿了双眼"),
    (474, "歌蕾蒂娅", "b_orgasm_small", "chara_0474_歌蕾蒂娅2290", "表明了歌蕾蒂娅品尝到了高潮的快乐"),
]
for chara_id, name, behavior_id, talk_id, expect in chara_cases:
    new_chara(chara_id, name, adv=chara_id)
    for target_id in (chara_id, 0):
        text = climax_text(chara_id, behavior_id, talk_id, target_id, real_premise=False)
        check(f"{talk_id} 把高潮的人写成{name}（交互对象 id{target_id}）", expect in text, f"text={text[:120]!r}")

# ==== 3. 本次改动的全部口上：以干员为说话人渲染，交互对象是她自己或博士时都写出了干员的名字，且两种渲染的文字相同 ====
rows = {
    "second_climax_A_climax": range(1180, 1220),
    "second_climax_B_climax": range(1220, 1240),
    "second_climax_V_climax": range(1220, 1240),
    "second_climax_C_climax": range(1200, 1220),
}
fixed = [f"{prefix}{cid}" for prefix, cids in rows.items() for cid in cids]
fixed += ["chara_2015_夕18", "chara_2015_夕19"]
fixed += [f"chara_0377_澄闪{cid}" for cid in (92, 93, 94, 105)]
fixed += [f"chara_0204_白金{cid}" for cid in (971, 1118, 1139)]
fixed += [f"chara_0474_歌蕾蒂娅{cid}" for cid in (2290, 2291, 2292)]
texts = {"self": {}, "doctor": {}}
""" 交互对象 -> {口上id: 渲染后的文本} """
for target in texts:
    missing = []
    for talk_id in fixed:
        # 角色口上的说话人是该角色（本测试里角色id与 adv_id 相同），系统口上的说话人是测试干员
        chara_id = game_config.config_talk[talk_id].adv_id or 1
        cache.character_data[chara_id].target_character_id = chara_id if target == "self" else 0
        texts[target][talk_id] = real_code_text_to_draw_text(game_config.config_talk[talk_id].context, chara_id)
        if cache.character_data[chara_id].name not in texts[target][talk_id]:
            missing.append(talk_id)
    check(f"{len(fixed)} 条口上都写出了高潮干员的名字（交互对象是{'她自己' if target == 'self' else '博士'}）", not missing, f"缺名字的 {len(missing)} 条，例如 {missing[:3]}")
# 人名只来自 {Name}（干员）与 {PlayerName}（博士），与干员的交互对象无关
differ = [talk_id for talk_id in fixed if texts["self"][talk_id] != texts["doctor"][talk_id]]
check(f"{len(fixed)} 条口上在两种交互对象下渲染出的文字相同", not differ, f"不同的 {len(differ)} 条，例如 {differ[:3]}")
# B_climax 里写到替她掩护的人的 11 行：掩护的人是博士
helper_rows = [f"second_climax_B_climax{cid}" for cid in (1227, 1228, *range(1231, 1240))]
no_doctor = [talk_id for talk_id in helper_rows if any(DOC not in texts[target][talk_id] for target in texts)]
check(f"{len(helper_rows)} 条 B_climax 掩护行都写出了博士的名字", not no_doctor, f"没写出博士的 {len(no_doctor)} 条，例如 {no_doctor[:3]}")
# 全部口上数据里，干员的高潮描写（p_ 开头的是博士射精）都不用 {TargetName}
left = sorted(tid for tid, cfg in game_config.config_talk.items() if re.match(r"^[a-z]_orgasm_", cfg.behavior_id) and not cfg.behavior_id.startswith("p_") and "{TargetName}" in cfg.context)
check("干员的高潮描写都不用 {TargetName}", not left, f"仍用的 {len(left)} 条，例如 {left[:3]}")

finish()
