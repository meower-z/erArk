# 本地绝顶链式门禁修复

## 症状

一次玩家行动的结算中，某个 NPC 发生多重绝顶（同一次结算中 >=2 个部位越过绝顶阈值）后，
在展示完大量绝顶口上之后，她仍可能在**同一次点击**内立即被重新调度、发起下一轮主动行为
（例如再次自慰并再次绝顶），于是同一次点击里反复主动、反复绝顶，堆叠出非常大量的口上。

## 根因

NPC 的实际高潮释放统一在 `Script/Settle/orgasm_settle.py` 的 `orgasm_settle()` 结算，但没有"本次玩家行动内
已多重绝顶"的记录；一次点击的结算中，NPC 完成多重绝顶后，其后续的自主行为生成入口——
普通空闲 AI `find_character_target()` 与群交 `npc_ai_in_group_sex()`——仍会照常为她生成
新的主动行为，形成同一点击内的绝顶连锁。

## 修复范围

新增角色临时结算标记 `sp_flag.multi_orgasm_this_player_action`（读写走 getattr/直接赋值，
不依赖 SPECIAL_FLAG 预声明该字段）：

- 替换 `Script.Design.second_behavior.character_get_second_behavior`：多重绝顶会触发唯一的
  `plural_orgasm_{part_count}` 二段行为（`orgasm_settle` 内 `part_count >= 2` 才调用；时停蓄积
  与成功寸止都在循环内提前 `continue`、`part_count` 保持 0，不会走到该调用）。wrapper 检测到
  `plural_orgasm_*` 且 `character_id` 非 0（排除玩家）时为该 NPC 置位标记。
- 替换 `Script.Design.update.game_update_flow`：进入前深度为 0（最外层点击）时重置全体 NPC 的
  标记；嵌套更新（深度 >0）复用同一标记，不重置。
- 替换 `Script.Design.handle_npc_ai.find_character_target`：已置位的 NPC 直接加入
  `over_behavior_character` 并返回，由 `character_behavior()` 继续走 `judge_character_status()`
  等被动结算尾部，不生成新目标。
- 替换 `Script.Design.handle_npc_ai_in_h.npc_ai_in_group_sex`：已置位的 NPC 早退，不写入自慰
  意图或群交模板占位；保留其现有群交参与关系，随后同一角色仍会到普通入口完成被动结算尾部。

## 边界

- 仅拦截**多重绝顶**后的再调度：单部位高潮不置位、不受影响。
- 玩家（`character_id == 0`）、成功寸止、时停蓄积均不置位。
- 被门禁的 NPC 仍接受刺激、累计快感、结算二段效果与被动高潮，并最终进入完成集合，无循环挂起。
- 按**玩家点击**恢复，不建立按游戏分钟倒计时的恢复状态；下一次最外层点击开始即解除。
- 标记随角色存档，但每次最外层点击开始必重置，不产生跨点击/跨存档效果；旧档缺省视为 `False`。

## 上游状态

对应上游 PR [#226](https://github.com/Godofcong-1/erArk/pull/226)（`codex/add-per-click-orgasm-chain-gate`）。
上游维护者计划把"绝顶后影响意识程度"纳入将来的负体力 H 系统 / 无意识 H 大系统，与本 PR 冲突，
故 PR 被关闭、不合并；现阶段上游接受"干员绝顶后还会再进行一次行动"。用户选择在本地保留该行为，
因此改由本 mod 承接（不再依赖内联树内代码，剥离内联代码后由 wrapper 在运行时等价重建）。

## 依赖

无。依赖的最外层更新深度恢复（`game_update_flow_running`，上游 PR #216）已在上游主线，属核心行为。

## 验证

```bash
python mod/local_orgasm_chain_gate_fix/tests/test_local_orgasm_chain_gate_fix_mod.py
```
