# group_sex_summary mod:设计定稿与实施状态(2026-08-18)

会话 era2 的工作快照。权威规格 = worktree 内 `mod/group_sex_summary/DESIGN.md`(v2,经 opus 代码级评审修正 4 处阻塞问题后定稿,用户已批准实施)。本页记录:进行中状态、定稿要点、以及评审/探查得出的**可复用领域事实**。

## 进行中状态(恢复点)

- worktree:`/home/ubuntu/games/erArk/.claude/worktrees/group-sex-summary-mod`,分支 `worktree-group-sex-summary-mod`。
- `mod/group_sex_summary/DESIGN.md` 已写入(未提交,untracked)。
- **Worker 实现子代理在进程退出时丢失**(未完成);重派前先检查 worktree 内 `mod/group_sex_summary/scripts/`、`mod_info.json`、`mod/mod_config.json` 是否有半成品。
- 任务清单:#1 实现(in_progress)→ #2 opus 对照 DESIGN.md 验收 diff → #3 Tk 真实游玩截图验收(用户明确要求详尽验收:真实游玩、相关场景截图、时刻留意行为与预期不一致处;可用 `capture-tk-evidence` 技能)。
- 用户已定稿的决定:仅 Tk(Web 下 mod 直通不生效);保留信息(成就/刻印/素质/白名单口上)缓存到摘要页之后回放;metadata 栏只放 `<寸止>` 分档标记;事件原地显示不缓存;改动量最小/精确优先;功能 1 语义 = 仅"高潮成功"触发跳过(寸止不算),玩家自选动作永不被跳过。

## 定稿方案速览(细节以 DESIGN.md 为准)

`mod/group_sex_summary/`(mod_info.json + 约 300 行脚本),对本体 0 行修改,8 个薄 wrapper(全部 call_original,零函数体复制)+ 一个约 25 行定向缓冲上下文管理器;状态全在 mod 模块全局变量,不进存档:

1. `character_behavior.init_character_behavior` — turn 边界:**深度计数,只有最外层拥有 turn**;末尾画摘要页+WaitDraw+回放;finally 兜底恢复一切补丁。
2. `talk.handle_talk_draw` — 吞常规口上;白名单(GROUP_SEX_NPC_HP_0_END / GROUP_SEX_PL_HP_0_END / JOIN_GROUP_SEX / DISCOVER_OTHER_SEX_AND_JOIN / BE_INVITED_JOIN_GROUP_SEX,Behavior.py 与 SecondBehavior.py 常量均存在)缓冲回放。行为 id 必须**按入参推导**(talk.py:281-289 口径),不能读 character_data.behavior(招呼口上带玩家行为 id 会读错)。
3. `settle_behavior.handle_settle_behavior` — call_original 后返回 None(上游 character_behavior.py:245 有 `!= None and len(...)` 守卫,None 安全,second_settle_panel 同 if 内一并被吞)。
4. `settle_behavior.handle_instruct_data` — 功能 1:`turn_active && cache.group_sex_mode(调用时判)&& character_id==0 && behavior_id != player_behavior_id && 目标在 orgasm_record` → 跳过。目标 = `cache.character_data[0].target_character_id`(群交循环每次调用前在 settle_behavior.py:62 设好)。唯一改变游戏结果的 hook,与功能 2 零耦合可分步开。
5. `orgasm_settle.orgasm_settle_in_second_behavior` — call_original 后扫描该角色 `second_behavior` 里非零 `{part}_orgasm_{small|normal|strong}` / `{part}_orgasm_edge` id 记录。
6. `achievement_panel.draw_achievement_notice` — 缓冲窗口下直通(成就唯一绘制出口,achievement_panel.py:152,全仓单一调用点 :125)。
7. `second_behavior.mark_effect` — 缓冲窗口下直通(它在 :585-588 直接 WaitDraw().draw(),绕过口上出口)。
8. `handle_talent` 的素质获得提示函数(handle_talent.py:71-73 所在函数,实现期确认名) — 缓冲窗口下直通。

定向缓冲三纪律:只 patch `NormalDraw/WaitDraw/LineFeedWaitDraw` 三类的 draw;replay_queue **存值元组不存对象**(line_feed 等模块级单例复用,存 self 有别名 bug);嵌套按"进入时刻的方法"保存/finally 恢复。摘要数据:orgasm_record 按部位取**最高档**去重(同一部位一次结算可能置两个档位 id;上游口径 get_orgasm_part_and_degree / plural_orgasm_{n});寸止分档按次数 `<寸止>`/`<寸止!>`/`<寸止!!>`。

v1 接受的边角:玩家射精忍耐/射精面板与发现群交面板(带按钮交互)原地放行;玩家太累提示、理智不足源石技艺中断(realtime_settle.py:504-509)、无意识恢复、发电提示 v1 原地放行,试玩碍事再逐个加同构 wrapper。

## 可复用领域事实(本次探查/评审确证,含行号,截至 2026-08-18 HEAD)

**群交 turn 机制**
- 一个 turn = 一次最外层 `init_character_behavior()`;`cache.over_behavior_character` 在 :50 重置;结束点在 update.py:23-25(跑完后 focus 输入框前)。
- **`init_character_behavior` 可重入**:update.py:12-13 允许嵌套深度 2;真实嵌套路径:群交中玩家/NPC 疲劳 → handle_group_sex_end / handle_h_end(handle_instruct.py:1607/1475)→ `update.game_update_flow` → 嵌套调用;另有 Settle/default.py:2586、handle_npc_ai_in_h.py:271。
- **群交模板动作全部在玩家阶段执行**:settle_behavior.py:48-70 临时换玩家 behavior/target 逐项调 handle_instruct_data;NPC 目标侧二段效果在 :430-442。NPC 阶段的 `npc_ai_in_group_sex`(handle_npc_ai_in_h.py:634-708)只为**下一 turn**排程(填模板/自慰),模板内成员被 :645-648 membership guard 跳过。群交 NPC AI"类型 3"(:651-736)是死代码,无调用点。
- `cache.group_sex_mode` 是全局开关(premise `group_sex_mode_on` 无视 character_id)。

**高潮/寸止结算**
- `orgasm_settle_in_second_behavior`(orgasm_settle.py:134-331)是 `{part}_orgasm_{degree}`(:233-235、:267-289)与 `{part}_orgasm_edge`(:224-226)的**唯一写入点**;挂它可收口全部 5 条调用路径。只挂 `orgasm_judge` 会漏寸止强制解放 `release_orgasm_edge_now`(:333-354,调用者 Settle/default.py:6766/6824/6899)和时停解放(default.py:6795)。
- 扫描时机成立:NPC 路径 second_behavior.py:118 先跑普通二段 → :121 orgasm_judge 写入 → :123 才消费清零;写入与消费之间有窗口。
- `orgasm_count` 是[本场H, 累计],**没有 per-turn 高潮字段**;`character_get_second_behavior`(second_behavior.py:54)是 `=1` 不是 `+=1`,拿不到次数只有集合。

**输出/绘制路径**
- `talk.handle_talk_draw` 是全部口上+二段行为标题的**唯一 Tk 出口**(7 个调用点全在 talk.py;must_show_talk_check 也走它)。
- `handle_settle_behavior` 返回 None 安全(上游习以为常,函数本就有多个 None 返回路径)。
- 成就唯一绘制出口 = `draw_achievement_notice`;多重绝顶成就在 orgasm_settle.py:319-323 触发(群交内最高频成就来源),挂 achievement_flow 会漏。
- 刻印文本 mark_effect 直接 draw,绕过口上出口;WaitDraw 对空文本不等待(draw.py:95-103)。
- **事件绘制对 draw 类补丁天然免疫**:DrawEventTextPanel 继承 LineFeedWaitDraw 但覆写了 draw(draw_event_text_panel.py:136);子事件走 settle_behavior.py:100-105。事件按 behavior_id 命中(data/event 无任何 `group_sex_mode_on`/「群交」引用),群交模板动作是普通动作 id,所以普通事件(雷蛇堕落、铃兰深喉、喷乳、白金初夜等)群交中照常触发,且常带玩家选项。

**mod 系统**
- 模块属性替换(setattr);全仓相关调用点均为 `module.f()` 形式,无 from-import 绕过。call_original 只保存**首个**原函数;dependencies/load_priority 只解析**不执行**(mod/tests 里的依赖测试与当前源码不符,是期望非现实)。manifest `functions: []` 的 mod 在脚本体内自行打补丁,冲突要看脚本。
- 当前 6 个启用 mod 的占用(与本 mod 8 挂点零重叠):chain_gate=find_character_target/npc_ai_in_group_sex/character_get_second_behavior/game_update_flow;batch_talk=second_behavior_effect;easy_mode=hypnosis_degree_calculation/sanity_point_grow/order_hotel_room_flow;semen_boost=common_ejaculation;tk_output_pump_fix=main_frame.read_queue(脚本内);fontfix=无函数替换。**本 mod 禁挂**:second_behavior_effect、character_get_second_behavior、game_update_flow、npc_ai_in_group_sex(前两个已被占用,叠第三层会静默丢中间层)。

**QA 环境(本机)**
- Xvfb/xdotool/import/scrot 已装;更纱字体已装;tkinter 8.6 / Python 3.12。主 checkout `config.ini` 当前 `web_draw=1`、`debug=1`——Tk QA 需在 worktree 把 web_draw 临时置 0(不提交);存档在主 checkout `save/`(0-8+ 槽)可复制进 worktree。`group_sex_extension` mod 提供"全员寸止"快捷指令,测寸止标记极方便。群交发起路线见 memory「证据从正常存档正向游玩」。
