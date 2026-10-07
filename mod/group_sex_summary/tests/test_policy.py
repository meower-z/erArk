# -*- coding: UTF-8 -*-
"""
policy.py 测试：口上处理顺序、寸止链口上、指令族、太累退出、模板派发与玩家真实指令判据
需要导入本体常量 Script.Core.constant（只读，不启动游戏）
运行：python3 mod/group_sex_summary/tests/test_policy.py
"""
from _harness import check, finish, load_mod_package

load_mod_package()
from _erark_mod_group_sex_summary import policy, state  # noqa: E402
from Script.Core import constant  # noqa: E402

Behavior = constant.Behavior
state.begin_turn("player_bid")
turn = state.turn

# 寸止链口上
turn.edge_break_live.add(11)
turn.second_effect_character = 11
check("断了的角色在自己窗口内整条链直显", policy.edge_chain_talk_shows_live(11, "v_orgasm_strong"))
check("断了的角色：second_behavior_id 为空也直显", policy.edge_chain_talk_shows_live(11, ""))
check("窗口属于 11 时 12 不受影响", not policy.edge_chain_talk_shows_live(12, "v_orgasm_strong"))
turn.second_effect_character = None
check("窗口外不直显", not policy.edge_chain_talk_shows_live(11, "v_orgasm_strong"))
turn.edge_break_live.clear()
turn.edge_near_limit.add(11)
check("接近极限：寸止族直显", policy.edge_chain_talk_shows_live(11, "v_orgasm_edge"))
check("接近极限：绝顶族不直显", not policy.edge_chain_talk_shows_live(11, "v_orgasm_strong"))
check("接近极限：别的角色不受影响", not policy.edge_chain_talk_shows_live(12, "v_orgasm_edge"))
turn.edge_near_limit.clear()

# 口上处理顺序
whitelisted = Behavior.GROUP_SEX_NPC_HP_0_END
yes, no = (lambda: True), (lambda: False)


def boom():
    raise AssertionError("不该读 is_h")


turn.template_dispatch_active = True
check("白名单先于吞掉：模板窗口 + is_h 仍缓冲", policy.talk_decision(21, whitelisted, "", yes) == policy.TALK_BUFFER)
check("模板派发窗口吞掉", policy.talk_decision(21, "other", "", no) == policy.TALK_DROP)
turn.template_dispatch_active = False
check("NPC 背景 H 吞掉", policy.talk_decision(21, "other", "", yes) == policy.TALK_DROP)
check("其余直显", policy.talk_decision(21, "other", "", no) == policy.TALK_PASS)
check("玩家口上不读 is_h", policy.talk_decision(0, "other", "", boom) == policy.TALK_PASS)
turn.player_real_active = True
check("玩家真实指令期间直显（先于白名单）", policy.talk_decision(21, whitelisted, "", boom) == policy.TALK_PASS)
turn.player_real_active = False
turn.edge_near_limit.add(21)
turn.template_dispatch_active = True
check("寸止链直显排第一", policy.talk_decision(21, "other", "v_orgasm_edge", boom) == policy.TALK_PASS)
turn.template_dispatch_active = False
turn.edge_near_limit.clear()

# 口上行为id
check("口上行为id：无口上id时用地文行为id", policy.derive_talk_behavior_id("", "bid_x") == "bid_x")
check("口上行为id：都没有时为空串", policy.derive_talk_behavior_id("", None) == "")

# 太累退出
check("太累退出只认 NPC_HP_0_END", policy.is_tired_exit(Behavior.GROUP_SEX_NPC_HP_0_END))
check("玩家体力为零中断不算太累退出", not policy.is_tired_exit(Behavior.GROUP_SEX_PL_HP_0_END))
check("结束群交不算太累退出", not policy.is_tired_exit(Behavior.GROUP_SEX_END))
check("空串不算太累退出", not policy.is_tired_exit(""))

# 指令族
end_family = policy.mass_end_family()
check("结束族含结束群交", Behavior.GROUP_SEX_END in end_family)
check("结束族含 NPC 太累退出", Behavior.GROUP_SEX_NPC_HP_0_END in end_family)
check("结束族含玩家体力为零中断", Behavior.GROUP_SEX_PL_HP_0_END in end_family)
check("定向释放不在结束族", Behavior.ORGASM_EDGE_OFF not in end_family)
for toy in (Behavior.REMOTE_ALL_TURN_OFF_SEX_TOY, Behavior.REMOTE_ALL_SET_SEX_TOY_WEAK, Behavior.REMOTE_ALL_SET_SEX_TOY_MEDIUM, Behavior.REMOTE_ALL_SET_SEX_TOY_STRONG):
    check(f"{toy} 是波及全体的指令", toy in policy.mass_toy_family() and policy.is_mass_instruction(toy))
check("结束群交是波及全体的指令", policy.is_mass_instruction(Behavior.GROUP_SEX_END))
check("定向释放不是波及全体的指令", not policy.is_mass_instruction(Behavior.ORGASM_EDGE_OFF))
check("结束群交触发的释放是批量释放", policy.is_mass_end_release_source(Behavior.GROUP_SEX_END))
check("玩家体力为零中断触发的释放是批量释放", policy.is_mass_end_release_source(Behavior.GROUP_SEX_PL_HP_0_END))
check("定向释放不是批量释放", not policy.is_mass_end_release_source(Behavior.ORGASM_EDGE_OFF))
check("白名单含加入群交", Behavior.JOIN_GROUP_SEX in policy.talk_whitelist())

# 模板派发 / 玩家真实指令
check("模板派发：玩家结算、id 不是自选的", policy.is_template_dispatch(True, 0, "template_bid"))
check("模板派发：自选的不算", not policy.is_template_dispatch(True, 0, "player_bid"))
check("模板派发：NPC 结算不算", not policy.is_template_dispatch(True, 5, "template_bid"))
check("模板派发：群交模式关着不算", not policy.is_template_dispatch(False, 0, "template_bid"))
check("模板派发：结束族不算", not policy.is_template_dispatch(True, 0, Behavior.GROUP_SEX_END))
check("模板派发：GROUP_SEX_TO_H 不算", not policy.is_template_dispatch(True, 0, Behavior.GROUP_SEX_TO_H))
check("玩家真实指令：自选、有目标", policy.is_player_real(True, 0, "player_bid", 3))
check("玩家真实指令：无目标不算", not policy.is_player_real(True, 0, "player_bid", 0))
check("玩家真实指令：非自选不算", not policy.is_player_real(True, 0, "template_bid", 3))
state.begin_turn(Behavior.GROUP_SEX_END)
check("玩家真实指令：波及全体的不算", not policy.is_player_real(True, 0, Behavior.GROUP_SEX_END, 3))
finish()
