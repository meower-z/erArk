# 本地 Bug 修复记录

> 已废弃：该 monolithic mod 已由 `mod/LOCAL_BUGFIX_MIGRATION.md` 中列出的拆分组件替代。默认配置不再启用本目录；本目录仅作为迁移前源码备份。

这个 mod 用来承载本地验证过、但尚未向 upstream 提交的修复。每条修复都记录现象、原因、实现方式和验证方式，后续向 upstream 提 PR 时优先参考本文件。

## 群交自动补位残留玩家交互对象

- 观察：群交中玩家可见上在和其他干员交互，但底层结算可能落到另一个干员身上。一次异常案例中，凯尔希在非当前可见交互对象的情况下获得了异常高苦痛，并触发恐怖/反发刻印。
- 原因：`Script.Design.handle_npc_ai_in_h.npc_ai_in_group_sex()` 和 `npc_ai_in_group_sex_type_3()` 在自动补位时会临时把玩家 `target_character_id` 改为候选 NPC，用于前提过滤和指令筛选，但原函数没有恢复旧 target。后续群交结算会把“进入结算时的 target”当作初始 target 保存并在末尾恢复，导致污染值继续残留。
- 修复：`patched_npc_ai_in_group_sex()` 和 `patched_npc_ai_in_group_sex_type_3()` 通过 `_call_with_preserved_player_target()` 包裹 upstream 原函数，在调用前保存玩家 target，并在返回或抛错后恢复。
- 验证：`python mod/local_bugfix/tests/test_local_bugfix_mod.py` 会模拟 upstream 自动补位修改玩家 target，并断言 wrapper 调用后 target 被恢复。

## 群交中 H 状态干员离场或继续移动

- 观察：群交中的干员可能在 H 状态下离开现场，去执行吃饭、移动等普通 AI 行为。
- 原因：普通移动流程没有把群交 H 状态视为强制中断条件，NPC 已经处于移动行为时也可能继续走完路线。
- 修复：`patched_general_movement_module()` 和 `patched_character_continue_move()` 在群交 H 状态下调用 `_stop_group_sex_h_move()`，把 NPC 锁回等待状态并清空移动目标。
- 验证：手动测试群交场景中 NPC 不再离开现场；后续可补一个移动状态 fixture 回归测试。

## 群交中自动自慰标记被清理后不执行

- 观察：群交 AI 设置为“仅自慰”或“优先补空位，无位则自慰”时，部分 NPC 会进入要自慰状态后傻站。
- 原因：H 状态 NPC 默认不会继续走普通 AI 目标选择；群交自慰标记需要被导向 `default91` 目标才能实际产生自慰行为。
- 修复：`patched_find_character_target()` 在群交 H 状态且 `masturebate == 3` 时，直接搜索并执行 `default91`，否则才回退到 upstream 目标选择。
- 验证：群交中未占位 NPC 可以执行自慰行为；后续可用 fake target registry 补自动测试。

## 群交中同一行动内自动自慰重复结算

- 观察：玩家点击一次群交指令后，某些戴着玩具、没有占位而进入自慰逻辑的 NPC 会在同一轮结算里多次显示寸止。
- 原因：NPC 结算会循环到所有 NPC 都完成当前玩家行动；`masturebate == 3` 是群交中“应该自慰”的意图标记，不是一次性行为标记。自动自慰结算完成并回到空闲后，本地补丁会再次把同一个 NPC 导向 `default91`。
- 修复：`patched_find_character_target()` 为群交自动自慰增加玩家行动切片级消费记录。同一角色在同一次玩家行动里只允许被导向一次 `default91`，再次回到空闲时清理这次被抑制的自慰意图，并标记该 NPC 本轮结算完成。
- 验证：`python mod/local_bugfix/tests/test_local_bugfix_mod.py` 覆盖同一行动只执行一次、被抑制的 marker 不会泄漏到下一次行动、换到下一次玩家行动且 AI 重新设置 marker 后可再次执行。

## 群交中疲劳退出后立即发现群交

- 观察：群交中因很累而退出的干员可能马上触发“发现群交”面板，并显示“邀请对方加入群交”等按钮；邀请后又会立刻因为疲劳退出。新的疲劳路过角色也可能进入同样的无效邀请循环。
- 原因：群交疲劳退出会清理该 NPC 的 H 状态和群交模板占位，但当前群交仍在继续；发现 H 面板只按实行值判断能否邀请群交，未把体力归零、疲劳或困倦作为加入限制。
- 修复：`patched_sex_be_discovered_draw()` 在群交模式下拦截疲劳/体力归零的发现者，不弹出选择按钮，直接复用原版 `SEE_H_AND_LEAVE` 行为。旧参与者不会立刻打扰，新疲劳路过者也不会被邀请进来。
- 验证：`python mod/local_bugfix/tests/test_local_bugfix_mod.py` 覆盖疲劳发现者判定、自动离开行为和跳过原面板。

## 群交/打断时玩家移动状态未停止

- 观察：玩家移动途中进入 H 或群交相关状态后，移动路径可能继续保留，导致面板或状态不一致。
- 原因：玩家移动流程只按目标地点推进，没有在 H 中断、移动停止或群交模式开启时统一清空移动目标。
- 修复：`patched_own_charcter_move()` 通过 `_stop_player_move_if_interrupted()` 检测 `move_stop`、`is_h` 和 `group_sex_mode`，命中时清空移动目标并结束移动循环。
- 验证：手动测试移动中被 H/群交打断后不再继续前往旧目的地；后续可补移动 fixture 回归测试。

## 群交中疲劳/睡眠状态重判

- 观察：群交中的 H 状态或跟随状态 NPC 在疲劳边界上可能没有及时刷新状态。
- 原因：upstream 疲劳睡眠判定完成后，群交 H 状态下的异常状态可能还需要重新触发角色状态结算。
- 修复：`patched_judge_character_tired_sleep()` 在调用 upstream 后，对群交 H/跟随且达到疲劳条件的 NPC 再调用 `character_behavior.judge_character_status()`。
- 验证：手动测试疲劳边界不再把群交 NPC 推入普通行动；后续可补疲劳状态 fixture 回归测试。

## NPC 主动 H 打断玩家移动

- 观察：NPC 主动 H 触发时，玩家可能仍保留移动最终目标。
- 原因：`npc_active_h()` 直接给玩家赋予 H 行为并推进时间，但没有清空玩家正在进行的移动计划。
- 修复：`patched_npc_active_h()` 在选定主动 H 行为后调用 `_stop_player_move_on_h_interrupt()`，清除玩家移动最终目标。
- 验证：手动测试 NPC 主动 H 后玩家不继续旧移动路线；后续可补主动 H fixture 回归测试。

## 心控-苦痛快感化的残留和旁路苦痛

- 观察：解除催眠后，`心控-苦痛快感化` 可能继续残留；开关开启时，群交或额外绝顶等场景仍可能出现苦痛增加；多重绝顶触发的苦痛下降会被错误转成心理快感下降。
- 原因：`handle_hypnosis_cancel()` 只清理 `increase_body_sensitivity`、木头人、逆推和角色扮演，没有清理 `pain_as_pleasure`。通用状态结算在 `state_id == 17` 时无论最终值正负都会转到心理快感。部分二段效果直接写 `status_data[17]`，绕过通用状态结算，典型路径包括小/中/大量苦痛刻印补正和额外绝顶苦痛。
- 修复：`patched_handle_hypnosis_cancel()` 在 upstream 解除催眠后额外关闭 `pain_as_pleasure`。`patched_base_chara_state_common_settle()` 只让正向苦痛继续走 upstream 的苦痛转心理快感逻辑，苦痛下降时临时关闭该 flag 并复用原结算。`patched_handle_add_small_pain()`、`patched_handle_add_middle_pain()`、`patched_handle_add_large_pain()` 和 `patched_handle_extra_orgasm()` 把二段效果的正向直接苦痛统一转入心理快感，不再写入苦痛。
- 验证：`python mod/local_bugfix/tests/test_local_bugfix_mod.py` 覆盖解除催眠清 flag、苦痛下降不转心理快感、直接苦痛增加转心理快感，以及小量苦痛二段效果不再绕过转换。
- 关联假说：几百万苦痛的链路更可能是“苦痛快感化把通用苦痛转成大量心理快感，心理快感推动额外高潮，额外高潮二段效果又直接写入苦痛”。如果寸止成功并跳过了 `extra_orgasm` 二段结算，则这条链路不能解释那一次特殊样本。

## H 多重绝顶批处理

- 观察：多部位在同一次 H 结算中绝顶时，原版会先逐个显示部位绝顶，再显示多重绝顶；同一部位若同时产生小/普/强绝顶会重复播放口上。人力发电室中还会逐个显示每个小部位的发电量，最后再显示多重绝顶发电量。
- 原因：`orgasm_settle()` 只负责给角色写入二段行为，后续 `second_behavior_effect()` 按二段行为逐个显示和结算；NPC 分支还会用进入高潮结算前的旧 `orgasm_list` 过滤新生成的高潮二段行为，导致多重提示之后残留单独部位提示。
- 修复：`scripts/h_orgasm_batch.py` 替换 `check_second_effect()`、`orgasm_settle()` 和 `store_power_by_human_power()`。同一批次先显示原版多重绝顶口上；部位绝顶每个部位只显示一次，最多 3 个最高强度部位播放原格式“强度提示+口上”，其余只显示强度提示；所有二段效果仍按原标记结算一次。批处理期间疲劳/体力耗尽不会中断 H，等批次结束后再由原流程判断。人力发电只合并显示一次，文本沿用原版多重绝顶发电文本，只把电量替换为本批次合计值。
- 验证：`python mod/local_bugfix/tests/test_h_orgasm_batch_mod.py` 覆盖同部位显示去重、NPC 新高潮不再被旧过滤列表漏掉、人力发电显示合并，以及疲劳判定在绝顶批处理中延后。
