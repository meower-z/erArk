# 本地绝顶口上批次合并显示

## 症状

NPC 在一次结算中多个部位同时绝顶时，每个部位都会被逐条绘制一整段完整的绝顶口上
（标题地文 + 正文）。部位一多就整屏刷绝顶口上，玩家很难看出这次到底发生了什么。

## 本 mod 承接的行为

把同一次结算里的绝顶口上合并成一批显示：

- 多重绝顶（`plural_orgasm_*`）口上先出。
- 同一部位只保留最高等级参与显示。
- 参与显示的部位按强度从高到低排序，同强度随机打乱。
- 前 3 个部位显示完整代表口上。
- 第 4 个起按强度分组汇总成一行黄色提示：`{角色名}{部位、部位}{强度名}`。
- 多部位寸止（`*_orgasm_edge`）合并成一行标题，再从有正文的部位里随机挑一条正文
  （只绘正文、不再绘标题）。
- 收藏模式下不在收藏名单内的 NPC 不进批次，交回上游循环由其内部检查静默处理。
- 玩家（`character_id == 0`）完全不进批次。

所有二段行为的**结算效果**仍由上游原函数逐项执行，本 mod 只改口上显示。

## 与上游 `part_max_degree_dict` 过滤的分工

当前上游 `second_behavior_effect()` 自带一层过滤（`orgasm_settle_flag=True` 时启用
`part_max_degree_dict` + `orgasm_settle.get_orgasm_part_and_degree`）：同一部位内非最高
程度的绝顶行为只结算效果、不触发口上。那是上游自己修掉的 bug，本 mod 不重复实现。

分工：

- **上游**负责单个部位内的去重（同部位取最高程度）。
- **本 mod**负责跨部位的批次合并显示（排序、前 3 名、汇总行、寸止合并）。

本 mod 的"同部位只取最高等级"是上游规则的超集，两者叠加不冲突：上游过滤掉的低等级
行为本来就在本 mod 的接管集合里，不会重复出口上。玩家不进批次，其部位去重完全由
上游过滤负责。

## 实现方式（钩子 + 薄包装，不复制上游函数体）

本体只有一行切口：`second_behavior_effect` 的逐条结算循环在决定"这一条画不画口上"之后，
调用 `talk_flag = mod_hook.second_behavior_talk(talk_flag, character_id, second_behavior_id)`。
这一行位于离屏早退之后、任何二段效果之前。

mod 分两块：

1. `patched_second_behavior_effect` 包装 `Script.Design.second_behavior.second_behavior_effect`
   （`mod_info.json` 声明）。对 NPC 的这次调用，先快照本次待结算的非零二段行为 id，
   开一个"批次"，再 `call_original`；`try/finally` 保证结束后关闭批次。
   玩家、以及同角色重入（外层批次还开着）直接 `call_original`。
2. `filter_second_talk` 挂在 `mod_hook.second_behavior_talk` 上。批次第一次被问到时整块
   绘制，之后对被批次接管的行为回答"不画"，其余行为保持本体的判定。

这样有两点自然成立，不需要 mod 自己去复制本体条件：

- **离屏角色不画批次**：本体离屏早退时根本不进循环，钩子不会被调用。
- **批次取到的是效果之前的状态**：第一次被问到时循环还没执行任何效果。
  这一点很重要：本体对同部位非最高程度的绝顶行为是**跳过口上但照常执行效果**。
  一次结算里可以同时出现 `c_orgasm_small` 与 `c_orgasm_strong`，小绝顶排在前面、
  效果先落地，会改掉"初次高潮"一类前提（如歌蕾蒂娅 `c_orgasm_strong` 的专属口上要求
  `CVP_A1_E|12_E_0`）。批次在第一条之前画完，专属口上不会漏掉。

本体 `handle_second_talk` 没有"只绘正文不绘标题"的开关（PR #253 曾为它加 `draw_title`
参数）。本 mod 改用等价路径：
`talk.handle_talk_sub` → `talk.choice_talk_from_talk_data` → `talk.handle_talk_draw(..., second_behavior_id="", ...)`。
标题地文由 `handle_talk_draw` 的 `second_behavior_id` 参数触发，置空即只绘正文。

部位与程度的解析直接复用本体 `Script.Settle.orgasm_settle.get_orgasm_part_and_degree`。

脚本顶层有一句 `from Script.Design import handle_npc_ai` 的预导入：mod 加载时
`Script.Design.second_behavior` 还没被导入过，若由 mod 管理器直接以它为根导入，会撞上
`settle_behavior` → `handle_instruct` → `update` → `character_behavior` → `Script.Settle`
→ `item_effect` 的循环导入而加载失败。先以 `handle_npc_ai` 为根把依赖链完整导入一遍即可。

## 边界

- 只改口上显示，不改任何数值结算。
- 本体函数体怎么改都不影响本 mod，只要钩子那一行仍在循环里、位于效果之前。
- 同角色嵌套调用 `second_behavior_effect` 在正常游玩中不会发生；若发生，内层沿用外层批次。

## 上游状态

对应上游 PR [#253](https://github.com/Godofcong-1/erArk/pull/253)。上游维护者的规划是用
"纸娃娃地文"系统重新生成组合文本，不接受这种批次合并方案，故 PR 被关闭、不合并。
用户选择在本地保留该行为，因此改由本 mod 承接。

## 依赖

无。

## 验证

```bash
python mod/local_orgasm_batch_talk_fix/tests/test_local_orgasm_batch_talk_fix_mod.py
```
