# 群交摘要 mod 设计

## 给玩家的效果

只在 Tk 模式、群交进行中生效（`cache.group_sex_mode`）。

- 一轮里 NPC 的常规口上、属性变化面板、逐动作暂停不再一条条刷屏。
- 一轮结束时出一页「本轮群交结算」：每个有绝顶或寸止记录的 NPC 一行，太累退出的也单独一行；玩家不列。版式见下文「摘要页」。
- 玩家点击后，按发生顺序回放要保留的信息：成就、刻印、素质取得、白名单口上（加入/受邀/发现群交、太累退出、结束群交等）。
- 重要过程仍当场显示：寸止失败、定向释放寸止导致的整条绝顶链、接近极限的寸止提示、玩家自己下达的指令引发的一切。
- 玩法变化：一轮里每个 NPC 最多绝顶一轮（见下文）。

## 轮次

一轮 = 最外层的 `character_behavior.init_character_behavior()` 调用。该函数可重入（群交中太累结束 H 等路径会真实嵌套），
所以用 `state.depth` 计数，只有深度 1 才开轮、在深度回到 0 时收轮。开轮时记下玩家本轮自选的行为id，
用来区分"玩家自选"与"群交模板派发"。原函数返回后：建行数据 → 画摘要页 → 回放缓冲队列。

## 捕获与回放

`capture.py` 在 mod 加载时给 `NormalDraw`、`WaitDraw`、`LineFeedWaitDraw` 各套一层常驻薄包装（只装一次）：

- 没有打开的窗口时，原样调用原 `draw`。
- `capture_into(列表)` 打开一个窗口；窗口内的 `draw` 只把 `(类, text, style, width, tooltip)` 记进**最内层**窗口，不绘制。
  窗口可嵌套，各收各的，异常时也会关闭。
- `draw_live(记录)` 用原 `draw` 直接画出，绕过所有窗口。用于"先捕获、事后决定要不要显示"的场合。
- `replay(记录)` 按顺序新建对象再画；摘要页之后回放缓冲队列用它。

子类（`FullDraw`、`CenterDraw`、`RightDraw` 等）各自覆写 `draw`，不经过包装，所以不会被捕获。
事件面板 `DrawEventTextPanel` 同理，事件总是原地显示。带按钮的交互面板也原地显示。

## 显示规则

**口上**（`handle_talk_draw`，`policy.talk_decision`），按顺序取第一个命中的：

1. 寸止链：该角色本轮寸止断了且实时显示，并且正处在它自己的二段结算窗口内 → 直显；
   或该角色接近极限，且这条是寸止族口上 → 直显。
2. 玩家真实指令期间 → 直显。
3. 白名单行为 → 缓冲到摘要页之后。必须排在第 4 条前：太累退出等口上说出时 NPC 的 `is_h` 仍为 True。
4. 模板派发期间，或群交 NPC 自己的背景 H 口上 → 吞掉。
5. 其余 → 直显。绝顶链与寸止提示多半已在外层捕获窗口里，由那一层决定。

**属性变化面板**（`handle_settle_behavior`）：这次结算里出现过玩家真实指令才交给本体画，否则返回 None。
`group_sex_mode` 下玩家的一次结算同时包含真实指令和整段模板派发，面板是合并的一个，只能整体放行或整体吞。

**NPC 绝顶结算、二段结算、寸止判定**：都先捕获，再按下表决定是否 `draw_live`，不显示的就丢弃。

| 位置 | 实时显示的条件 |
| --- | --- |
| `orgasm_settle_in_second_behavior` | 该角色寸止断了且实时显示，或玩家真实指令期间 |
| `check_second_effect` | 同上，或该角色接近极限 |
| `judge_orgasm_edge_success` | 判定失败，或成功但余量 ≤ 2，或玩家真实指令期间 |

**断因**（摘要行的寸止标记）有三种，优先级 tired > release > fail，只升不降：

- `<寸止失败>`：寸止判定失败。实时显示。
- `<寸止释放>`：绝顶结算入口发现寸止被解开（`orgasm_edge == 2` 且计数未清）。定向释放实时显示；
  结束群交、玩家体力为零中断等批量结束引起的释放只记账，不实时显示，避免结束时整屏刷新。
- `<累>`：指令结算看到 `GROUP_SEX_NPC_HP_0_END`。只记账。即使本轮没有绝顶/寸止记录也单独成行。

没断过的角色若仍憋着寸止，标记按实时余量显示 `<寸止>` / `<寸止!>` / `<寸止!!>`，
余量 = 玩家技巧等级 × 3 − 当前寸止次数之和；`<寸止!>` 的门槛与实时显示的"接近极限"同为余量 ≤ 2。

**玩家真实指令**：玩家结算、行为id 等于本轮自选、有目标、且不是波及全体的指令（结束族、全员玩具族）。
波及全体的指令不算，结束群交只显示白名单里的那一句。

## 玩法变化：每个 NPC 一轮只绝顶一轮

`handle_instruct_data` 中，群交模板派发（玩家结算、id 不是本轮自选、不属结束族、不是 `GROUP_SEX_TO_H`）
的目标若已在本轮 `orgasm_record` 中，就跳过这次结算，原样返回 `change_data`。

- 只有绝顶触发跳过；寸止不触发。
- 玩家自选的动作永不跳过。模板里恰好有与自选同 id 的项时，该项也不跳过。
- 一个 NPC 占多个模板槽时，第一槽让它绝顶，之后的槽跳过。
- NPC 阶段的 `npc_ai_in_group_sex` 不替换：它只排下一轮的程，记录在下一轮开头已重置。

这是 10 个替换里唯一改变游戏结果的部分，其余都只影响显示。

## 替换函数

`mod_info.json` 登记 10 个 `replace`，实现在 `wrappers.py`，由 `entry.py` 按登记名暴露。
接管条件：轮次进行中且非 Web 模式（`init_character_behavior` 自己判断是否开轮）。

| 登记名 | 目标 | 作用 |
| --- | --- | --- |
| `modded_init_character_behavior` | `character_behavior.init_character_behavior` | 轮次边界、摘要页、回放 |
| `modded_handle_talk_draw` | `talk.handle_talk_draw` | 口上直显/缓冲/吞 |
| `modded_handle_settle_behavior` | `settle_behavior.handle_settle_behavior` | 属性变化面板 |
| `modded_handle_instruct_data` | `settle_behavior.handle_instruct_data` | 跳过、`<累>`、模板与真实指令窗口 |
| `modded_orgasm_settle_in_second_behavior` | `orgasm_settle.orgasm_settle_in_second_behavior` | `<寸止释放>`、并入记录 |
| `modded_draw_achievement_notice` | `achievement_panel.draw_achievement_notice` | 缓冲 |
| `modded_mark_effect` | `second_behavior.mark_effect` | 缓冲 |
| `modded_gain_talent` | `handle_talent.gain_talent` | 缓冲 |
| `modded_judge_orgasm_edge_success` | `orgasm_settle.judge_orgasm_edge_success` | `<寸止失败>`、接近极限 |
| `modded_check_second_effect` | `second_behavior.check_second_effect` | 二段结算窗口 |

## 摘要页

```
──────────────────────── 本轮群交结算 ────────────────────────
  夜莺  <寸止释放>  三重绝顶  阴道 强绝顶 ・ 胸部、阴蒂 绝顶
  九                          胸部 小绝顶
  槐琥  <寸止!>               阴道×2、阴蒂
  可颂  <累>
──────────────────────────────────────────────────────────────
  绝顶 2 人 ・ 寸止中 1 人 ・ 体力耗尽 1 人         (点击继续)
```

- 四列：姓名 | 寸止标记 | 类别 | 明细。列宽取本页实际内容的最大值；整页都空的列不占宽度，行尾不留空格。
- 类别列只写"N重绝顶"。单部位绝顶的行留空，否则会和明细里的"小绝顶"等字样重复；只寸止的行也留空。
- 明细：绝顶部位按档位从高到低分组，部位白字、档位按档位上色（小绝顶浅粉 → 超强绝顶最深）；
  之后接仍憋着的寸止部位（青色，次数大于 1 时写 ×N）。同一行既有绝顶又有寸止时，寸止部位前加灰色"寸止"二字。
- 排序：有绝顶的在前（部位多、档位高的更前），其次仍憋着的，最后只有标记的；同组内按角色id。
- 页宽跟内容走，不铺满整行，上限是 `text_width`；标题横线、底部横线、页脚同宽。人少时整页紧凑，人多时只是行数变多。
- 页脚是人数统计（为 0 的项不写）和右侧的点击提示，用 `WaitDraw` 画，点击后才回放缓冲队列。

## 模块

| 文件 | 内容 |
| --- | --- |
| `entry.py` | 唯一执行入口：以私有包名加载本目录，`install()`，暴露 10 个替换函数 |
| `__init__.py` | `install()`：预加载本体依赖链（避开循环导入），装绘制包装 |
| `records.py` | 纯函数：合并记录、断因、余量与标记、部位名与分组、要列出的角色；不 import 游戏 |
| `state.py` | 轮次深度与本轮状态 `TurnState` |
| `policy.py` | 显示与跳过的判据、指令族、白名单 |
| `capture.py` | 绘制包装、捕获窗口、`draw_live`、`replay` |
| `page.py` | `SummaryRow` 行数据、`build_rows` 与 `layout`（纯）、`draw_page` 绘制 |
| `wrappers.py` | 10 个替换函数 |

测试在 `tests/`，从仓库根目录运行 `python3 mod/group_sex_summary/tests/test_<名>.py`：
`test_records.py`、`test_capture.py`、`test_page.py` 不需要游戏环境；`test_policy.py` 只读导入 `Script.Core.constant`。
