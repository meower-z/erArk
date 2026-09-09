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

## 实现方式（wrapper，不复制上游函数体）

只替换一个函数：`Script.Design.second_behavior.second_behavior_effect`。

`patched_second_behavior_effect` 的做法：

1. 玩家、以及同角色重入（外层已经在批次中）直接 `call_original` 走上游原逻辑。
2. 离屏守卫：角色位置与玩家不同、且 `behavior.move_src` 也不是玩家位置时，直接
   `call_original`，不绘制批次。
3. NPC：先快照本次待结算的非零二段行为 id（趁上游还没把行为值归零）。
4. **在 `call_original` 之前**把合并批次整块绘制完。
5. 随后临时把 `Script.Design.talk.handle_second_talk` 换成"只吞不画"的接管版本，
   再 `call_original` 调用上游原函数，`try/finally` 保证恢复。接管版本吞掉已被批次
   接管的行为口上，未接管的行为原样透传。

批次必须画在原函数之前：上游对同部位非最高程度的绝顶行为是**跳过口上但照常执行效果**
（`second_behavior.py` 的结算循环 + `Script/Settle/Second_effect.py`）。一次结算里可以
同时出现 `c_orgasm_small` 与 `c_orgasm_strong`，小绝顶排在前面、效果先落地，就会改掉
"初次高潮"一类前提（如歌蕾蒂娅 `c_orgasm_strong` 的专属口上要求
`CVP_A1_E|12_E_0`）。若把批次推迟到口上时点绘制，取到的就是效果之后的状态，专属口上会
被漏掉。

上游 `handle_second_talk` 没有"只绘正文不绘标题"的开关（PR #253 曾为它加 `draw_title`
参数）。本 mod 不改 `Script/`，改用等价路径实现：
`talk.handle_talk_sub` → `talk.choice_talk_from_talk_data` → `talk.handle_talk_draw(..., second_behavior_id="", ...)`。
标题地文由 `handle_talk_draw` 的 `second_behavior_id` 参数触发，置空即只绘正文。

部位与程度的解析直接复用上游 `Script.Settle.orgasm_settle.get_orgasm_part_and_degree`，
不在 mod 内另写一套规则。

脚本顶层有一句 `from Script.Design import handle_npc_ai` 的预导入：mod 加载时
`Script.Design.second_behavior` 还没被导入过，若由 mod 管理器直接以它为根导入，会撞上
`settle_behavior` → `handle_instruct` → `update` → `character_behavior` → `Script.Settle`
→ `item_effect` 的循环导入而加载失败。先以 `handle_npc_ai` 为根把依赖链完整导入一遍即可
（`local_orgasm_chain_gate_fix` 因为函数列表第一项就是 `handle_npc_ai`，等价地绕开了同一个坑）。

## 上游漂移风险

- **离屏守卫必须与上游 `second_behavior_effect` 的位置早退条件保持一致。** 上游在
  `角色位置 != 玩家位置 and behavior.move_src != 玩家位置` 时走 `must_show_talk_check`
  分支直接返回、不显示口上；本 mod 因为改在原函数之前绘制，必须自己复制这一条件。
  上游一旦改这个条件，本 mod 的守卫要同步改，否则会把离屏角色的绝顶口上画上屏。
  代码里该守卫处有同样的注释。
- 接管钩子是改写 `talk` 模块的全局属性。已加同角色重入守卫
  （`_BATCH_ACTIVE_CHARACTER_IDS`），避免同一角色的内外层批次互相串扰；当前基线里不
  存在这种调用链，属于结构性防御。跨角色嵌套本来就各管各的接管集合，不受影响。

## 边界

- 只改口上显示，不改任何数值结算。
- 上游函数体怎么改都不影响本 mod，只要 `second_behavior_effect` 仍通过
  `talk.handle_second_talk` 输出二段口上、且位置早退条件不变（见"上游漂移风险"）。
- 若上游改名或不再走 `talk.handle_second_talk`，本 mod 会退化为"批次不绘制、
  全部按上游原样逐条显示"，不会报错也不会丢结算。

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
