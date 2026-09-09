# 群交摘要视图 mod 设计方案(group_sex_summary)v5(同步 73a329414 现状,用户两条裁定已落地)

## 目标与范围

五个功能,均只在 `cache.group_sex_mode` 开启的 turn 内生效:

1. **一 turn 一轮高潮**:NPC 在本 turn 内一旦高潮,本 turn 后续针对它的群交模板动作不再执行。
2. **摘要视图**(eraFL 式单行结算):抑制 turn 内的常规口上与属性变化面板,turn 结束时用一页摘要替代——每个
   NPC 一行:锚点右对齐姓名 + 全角冒号 + 与状态栏同口径的寸止/断因标记 + 绝顶描述/寸止 token(hot_pink,
   `/`连接);玩家点击后,按发生顺序回放保留信息(成就、刻印/素质取得、疲劳退出、加入/发现群交等)。
3. **寸止/H中断断因三分**:turn 内寸止断了(判定失败或被解放)导致的绝顶,从判定提示到二段标题/口上/发电
   提示全链原样实时显示,不吞不缓冲(除下述用户裁定1b的批量结束例外);摘要页按断因分三挂,优先级从高到低、
   只升不降(`_mark_edge_break_reason`,v5起该函数新增 `passthrough: bool = True` 参数——是否显示 `<累>`/
   `<寸止释放>`/`<寸止失败>` 标记只看 `_edge_break_reason` 是否有该角色的条目,与是否实时刷屏
   (`edge_fail_passthrough`)彻底解耦,详见下方"输出抑制与放行"小节与状态表):
   - **`<累>`**(`little_dark_slate_blue`,v5用户裁定2c改用与状态栏疲劳标记同色,见
     `character_info_head.py:148-153`;此前误用 `hp_point`(#e15a5a,"体力的颜色"),与状态栏口径不符):
     v5用户裁定2a起,判据从"#5 命中 `_is_edge_release_event` 时用 `_is_tired_exit` 区分"整体移到 #4:
     只要看到 `behavior_id==Behavior.GROUP_SEX_NPC_HP_0_END`(不看 `character_id` 是否为0,NPC太累退出的
     `character_id` 是该NPC自己)就直接 `_mark_edge_break_reason(character_id, "tired", passthrough=False)`,
     不再依赖是否曾经过 `release_orgasm_edge_now`。挂点可靠性:`commit_group_sex_tired_exit`
     (handle_npc_ai.py:145-179)先把该NPC的 `behavior.behavior_id` 改成这个专属id,再直接调用
     `character_behavior.judge_character_status(character_id)`(不经过 `init_character_behavior`,不改变
     `_depth`/`turn_active`,仍在外层turn窗口内),其内部(character_behavior.py:230)调用
     `settle_behavior.handle_settle_behavior`(#3),NPC路径(`character_id!=0`)落入非模板循环的直接调用分支,
     必然单独调用一次 `handle_instruct_data`(#4)且此刻 `behavior_id` 就是刚被设置的
     `GROUP_SEX_NPC_HP_0_END`——是这个行为id在结算链上的必经点,比依赖 #5 的release事件(该事件仅在批量
     结束链effect 529里出现,个体NPC自己的太累退出走的是1503/528/403/635清理链,通常不触发
     `release_orgasm_edge_now`)更可靠,修复了本文档 v3 曾记录的窄缺口"先寸止失败再太累退出,标记停留在
     `<寸止失败>`"(见下方"已知语义后果")。`passthrough=False`:用户裁定2只要求tired挂标记、进摘要行、配
     紫色,未要求改变是否实时刷屏,这里不新增 `edge_fail_passthrough` 写入,避免把"标记"与"是否放行实时
     显示"两件事再度耦合。
   - **`<寸止释放>`**(`gold_enrod`):命中 `_is_edge_release_event` 时(#5 写入)标记为 `"release"`
     (v5起不再在这里判定 tired,该分支已整体移到 #4,见上)。同时落实用户裁定1b:本次release是否源自
     "结束群交等全体类结束指令"触发的批量解放链(effect 529,`constant_effect.py:477` 数值529,只挂在玩家
     自身行为 `group_sex_end`(371)与 `group_sex_pl_hp_0_end`(373)的效果串上,`Behavior_Effect.csv:167,169`;
     实现见 `default.py:6873 handle_group_sex_end_h_add_hpmp_max`,循环 `scene_data.character_list`、对
     `orgasm_edge!=0` 的每个角色调 `release_orgasm_edge_now`)——判据(抽成纯函数
     `_is_mass_end_release_source`)是**调用当下**玩家(`character_id==0`)的**实时** `behavior.behavior_id`
     是否落在 `_mass_end_behavior_family()`(结束族,见下方新增小节)内。是则
     `_mark_edge_break_reason(character_id, "release", passthrough=False)`——只记账供摘要页
     `<寸止释放>` 正确显示,不并入 `edge_fail_passthrough`,避免这类批量解放触发用户否掉的"结束群交时一
     大串实时刷屏";否则(定向单人解放,如6014/`ORGASM_EDGE_OFF`,与结束族行为id不相交)保持
     `passthrough=True`,全程实时直显不变。**必须用实时读而非 turn 开头快照
     `player_behavior_id`**:effect 529 只挂在371/373的效果串上,只要它在执行,说明玩家的 `behavior_id`
     此刻必然已经是这两者之一(不论这个值是玩家本turn自己选的,还是被
     `handle_group_sex_end`(handle_instruct.py:1578-1590)当作NPC耗尽级联的副作用现改,1585-1586先置位
     behavior_id、effect串才据此触发)——同一调用栈内读该实时值恒可靠;而 `player_behavior_id` 是turn
     开头快照,级联场景下玩家那一turn原本选的可能是别的动作,快照早已过期,若拿它判据会在"NPC耗尽引发的
     批量结束"这条路径上误判为非批量、漏掉本该抑制的实时刷屏。
   - **`<寸止失败>`**(`gold_enrod`):#9(`judge_orgasm_edge_success`)本次判定返回 `False` 时直接标记——与
     `_is_edge_release_event` 是两个独立写入点,不共用判据(#9 在函数返回前不可能知道 `orgasm_edge` 是否已被
     置 2,只看自己的返回值)。
   - 判据入口 `_is_edge_release_event(orgasm_edge, orgasm_edge_count)` 要求 **`orgasm_edge==2` 且
     `orgasm_edge_count` 存在非零计数**,不能只看 `orgasm_edge==2`:该字段是 **latch**——`release_orgasm_edge_now`
     (orgasm_settle.py:345)与寸止判定失败分支(orgasm_settle.py:189)都会把它置 2,此后一直保持 2 直到玩家
     重新下"开启绝顶寸止"(`SELF_ORGASM_EDGE_ON`,同时清零 `orgasm_edge_count`)或"关闭"(`SELF_ORGASM_EDGE_OFF`,
     置 0)为止;期间该角色任何后续正常绝顶结算进入 #5 时 `orgasm_edge` 同样读到 2,若只判 `==2` 会把这些
     也误标成新的 release 事件,而 release 优先级(2)高于 fail(1),会把同 turn 更早由 #9 正确标记的 fail 覆盖
     掉。只有 `release_orgasm_edge_now` 自己触发的那次调用满足"计数非零"这个门(它先置 2、期间
     `orgasm_edge_count` 仍满编,清空动作在调用返回之后才执行 orgasm_settle.py:349-351);latch 态下的后续
     普通调用,`orgasm_edge_count` 早已被清空且不再被写入(`orgasm_edge!=1` 时不再累积新计数),恒为空。
   - **摘要行纳入**(v5用户裁定2b新增):`_summary_row_character_ids` 新增第三个来源——`_edge_break_reason`
     中 `reason=="tired"` 的角色id,即便该角色本turn没有任何 `orgasm_record`/`edge_record` 条目也单独成行,
     只显示"姓名:`<累>`"。原有"本turn无任何绝顶/寸止记录则整页/整行跳过"的语义只对"无任何记录**且无
     tired**"成立,不再对tired角色生效。
4. **博士针对性动作全显**:博士亲自下达且带明确目标的真实指令(非模板派发)在结算期间,直接引发的口上/
   属性变化面板/二段链原样实时全显——命中该窗口的绝顶链若同时满足摘要页纳入条件,摘要页仍会重复记一行,
   视为预期行为。**v5用户裁定1a收窄**:`is_player_real` 判据新增排除条件——即便此刻
   `target_character_id` 非零,只要 `behavior_id` 属于"波及全体"的指令(结束族 `_mass_end_behavior_family()`
   或全员玩具族 `_mass_toy_behavior_family()`,经 `_is_mass_instruction` 判定,见下方新增小节)也不算"针对
   一个角色的定向命令",不开全显窗口。原因:`Behavior.GROUP_SEX_END` 等结束指令、
   `REMOTE_ALL_TURN_OFF_SEX_TOY` 等全员玩具指令,走的都是
   `chara_handle_instruct_common_settle(behavior_id, character_id)` 不显式传 `target_character_id` 的
   调用路径(`handle_instruct.py:321-396`),该函数未传值时不会清空/重置角色当前的 `target_character_id`
   字段,只是原样保留其之前的遗留值——玩家此刻的 `target_character_id` 很可能因群交过程中先前的定向指令
   而非零,这个非零值不代表"结束/全员玩具"这次调用是针对该角色的定向指令,不排除会误开全显窗口,刷出
   用户否掉的"结束群交时一大串实时刷屏"(见下方用户裁定1b与"已知语义后果")。
5. **口上可见性五级判定**(取代早期"默认隐藏+id 白名单放行"的单层机制):turn 内每一条口上按下列优先级
   依次判定,命中即停(`modded_handle_talk_draw` / 其纯函数版本 `_talk_decision` 实现,#3/#5/#9/#10 各自的
   局部窗口只复用其中与自己相关的判据子集,不是本判定链的重复实现):
   1. **寸止断裂/极限放行**(`_should_pass_through_talk`):`edge_fail_passthrough` 命中的角色且当前正处在
      自己的 #10(`check_second_effect`)窗口内 → 整条二段结算链原样直显;`edge_near_limit` 命中的角色 →
      只放行 `_orgasm_edge` 族本身(该部位的寸止标题/口上)。
   2. **博士真实指令窗口**(`_player_real_instruction_active`,功能4):命中 → 直显,不分白名单/黑名单。
   3. **白名单回放**(`_talk_whitelist`:正常/异常结束群交、疲劳退出、加入/受邀/发现群交等):定向缓冲后
      回放队列兜底,摘要页点击后补放。**必须排在黑名单之前判**——疲劳退出等白名单口上的 `character_id`
      是 NPC 自己、`is_h` 此刻仍为 `True`(effect 528 清 `is_h` 在 talk 绘制之后才跑),黑名单先判会把它
      误伤成下一档的"背景H口上"。
   4. **黑名单隐去**(按上下文而非 id 枚举):模板派发窗口(`_template_dispatch_active`)或群交NPC阶段的
      背景H口上(`character_id!=0` 且 `is_h`)→ 直接吞掉,不绘制不缓存。
   5. **默认实时显示**:未落入以上四档的口上一律直接调原函数实时显示——取代早期版本"推导不出/未命中
      即吞"的兜底方向。

已定稿的设计决定:
- 仅支持 Tk 模式;Web 模式下所有 wrapper 直接调用原函数。
- 保留信息缓存,统一排在摘要页之后回放。
- metadata 栏的寸止/断因标记,公式与三档样式与状态栏(`character_info_head.py:237-257`)完全对齐,不是本
  mod 自造的按次数分档口径。
- 事件(event 系统)原地显示、原地交互,不缓存。事件绘制走 `DrawEventTextPanel`,它覆写了 `draw` 方法,对本 mod 的定向缓冲天然免疫(此事实要写进代码注释,防止日后被"顺手修复")。
- 玩家自己的射精/忍耐面板是交互面板(带按钮),同样原地放行——玩家射精瞬间摘要流会被打断一次,这是接受的(玩家自己触发、自己交互)。

### 可见性设计原则(用户原子性裁定,新增判据须先过这三条再落地)

- **可见性由"原因/来源轴"决定,不是逐 id 枚举**。id 白名单本身就是误伤源——每漏一个新 id 就得补一条规则
  (`extra_orgasm`、`semen_drinking_climax` 都是这么补上去的);判据一旦能收敛成"这个角色本 turn 寸止断了"
  这样的上下文状态,就不该再退回到按具体二段行为 id 挑。
- **重要结果用回放队列或原样直显兜底,不能吞**:成就、刻印/素质取得、寸止失败/接近极限预警、博士真实指令
  引发的一切,信息丢失的代价高于"turn 内多刷一行"。
- **整窗/整链全放行只保留给"本身不是自包含信息"的情形**:某个事件必须跟着完整链条看才成立(例如寸止失败
  到绝顶的整条过程,单拎出判定提示或单拎出绝顶口上都读不出发生了什么)才整窗放行;本身自包含、单独一行
  就能读懂的普通信息(如平淡的绝顶口上)不整窗放行,继续走默认吞/缓冲逻辑。这条是用户明确裁定的边界,不是
  工程上的近似简化。

turn 的定义:一次**最外层** `character_behavior.init_character_behavior()` 调用。注意该函数是可重入的(`update.py:12-13` 允许嵌套到深度 2;群交内疲劳结束 H 等路径会真实触发嵌套),因此 turn 归属必须用深度计数判定,见 wrapper #1。

## 总体结构

```
mod/group_sex_summary/
├── mod_info.json        # 声明 10 个 replace 函数
└── scripts/
    └── group_sex_summary.py
```

- **开关**:mod 启用即生效;要关就在 `mod/mod_config.json` 停用。日后若需游戏内开关可挂 `draw_setting`,不影响结构。
- **模式门**:每个 wrapper 开头判断 `normal_config.config_normal.web_draw`,Web 模式一律直通原函数。
- **实现纪律**:所有替换均为「薄 wrapper + `call_original`」,**不复制任何原函数函数体**。上游改这些函数的内部实现,mod 自动跟随;只有签名或二段行为 id 命名约定变化才需适配。
- **冲突边界**:已逐一核对当前启用的全部 6 个 mod(local_fontfix、local_tk_output_pump_fix、local_orgasm_chain_gate_fix、local_orgasm_batch_talk_fix、group_sex_extension、easy_mode)的替换/补丁目标,与本 mod 的 10 个挂点零重叠,可共存(群交 turn 内它们合并的口上仍经 `handle_talk_draw` 被 #2 吞掉,群交外照常)。**禁止**本 mod 再挂 `second_behavior.second_behavior_effect` 或 `character_get_second_behavior`——已被上述 mod 占用,mod 系统对同一目标只保存首个原函数,叠加会静默丢失中间层。

## 新增状态(全部为 mod 模块自身全局变量,不进 Character/cache,不进存档)

| 变量 | 类型 | 含义 |
| --- | --- | --- |
| `_depth` | int | `init_character_behavior` 嵌套深度,只有最外层拥有 turn |
| `turn_active` | bool | 当前处于群交摘要 turn 内 |
| `player_behavior_id` | str | turn 开始时玩家自选的行为 id(功能 1 的"玩家意志优先"判据,亦是功能4 `is_player_real` 判据的一部分) |
| `orgasm_record` | dict[int, dict[str, int]] | 角色 id → {部位: 本 turn 最高档位 rank}。档位存 `get_orgasm_part_and_degree`/`orgasm_degree_order` 返回的 rank int(0=small…3=super),与上游口径对齐,按部位取最高档(同一部位一次结算可能置上两个档位 id,直接存 list 会把"N重绝顶"算多) |
| `edge_record` | dict[int, dict[str, int]] | 角色 id → {部位: 寸止次数} |
| `replay_queue` | list[tuple] | 保留信息缓冲。**存值不存对象**:每项 `(draw类, text, style, width, tooltip)`,回放时新建对象绘制——绘制系统里 `line_feed` 等模块级单例被大量复用,缓存 self 会踩别名 bug |
| `edge_fail_passthrough` | set[int] | v5起纯粹是"本 turn 该角色是否实时刷屏"的开关,与下面 `_edge_break_reason` 是否有条目彻底解耦(此前二者同步写入,v5拆开):判定失败(#9 写入)、非批量的定向寸止解放(#5 写入)会加入;源自"结束群交等全体类结束指令"的批量解放(#5 判定,用户裁定1b)与 #4 的 tired 标记(用户裁定2a)**不会**加入。命中的角色,其随之而来的绝顶二段标题/口上(#2)与性爱发电提示(#5)原样实时放行 |
| `_edge_break_reason` | dict[int, str] | 角色 id → `"tired"`/`"release"`/`"fail"`,该角色本 turn 的断因(#4/#5/#9 写入,`_mark_edge_break_reason` 按优先级只升不降;`tired`>`release`>`fail`),供摘要页 `_edge_break_tag_and_style` 显示 `<累>`/`<寸止释放>`/`<寸止失败>` 三选一标记与 `_split_edge_parts`/`_edge_status_tag` 判定"是否兑现成绝顶"——v5起这两处判据都改判本字典而非 `edge_fail_passthrough`(是否有断因记录是记账语义,与是否实时放行无关),`_summary_row_character_ids` 也从这里取 `reason=="tired"` 的角色id作为摘要行第三来源 |
| `_MASS_END_FAMILY_CACHE` / `_MASS_TOY_FAMILY_CACHE` | set[str]&#124;None | `_mass_end_behavior_family()`/`_mass_toy_behavior_family()` 的懒加载缓存(v5新增,用户裁定1a/1b),首次调用时用真实 `Script.Core.constant` 填充,详见下方新增小节 |
| `edge_near_limit` | set[int] | 本 turn 内寸止成功但余量≤2(状态栏感叹号两档)的角色 id 集合(#9 写入)。命中的角色,其 `_orgasm_edge` 族标题/口上(#2)与 batch_talk_fix 黄字合并寸止标题(#10)原样实时放行 |
| `_player_real_instruction_active` | bool | 当前是否处于博士亲自指定目标的真实指令(`is_player_real`)结算窗口内(#4 写入/`try`/`finally` 恢复)。命中时 #2/#3/#5/#9/#10 均原样实时放行 |
| `_player_real_instruction_seen` | bool | #3 专用的一次性锁存:每次调用 `handle_settle_behavior` 前存旧值并清零,`call_original` 期间只要命中过一次 `_player_real_instruction_active` 就置 `True`;#3 据此决定这次返回的属性面板是否真的交还上游。存旧值 + `try`/`finally` 恢复(与 `_second_effect_character`/`_player_real_instruction_active` 同一写法)——`CSE_*` 事件可能在同一次 `call_original` 内触发嵌套 `init_character_behavior`→嵌套 #3,不恢复会让嵌套调用的清零静默抹掉外层已锁存的 `True` |
| `_template_dispatch_active` | bool | 当前是否处于群交模板派发循环(`character_id==0`、`behavior_id!=player_behavior_id` 那个循环,见 settle_behavior.py:51-68)窗口内(#4 写入/恢复)。口上五级判定第4档(黑名单)判据之一 |
| `in_buffer` | bool(或上下文管理器内部状态) | 定向缓冲是否生效 |

所有状态在最外层 turn 开头重置,不跨 turn,存档兼容性零影响。

下表"非激活/激活"均指 `_is_active()`(`turn_active and not web`)——`turn_active` 只在 #1 turn 起点判一次
`cache.group_sex_mode` 后置位,turn 中途 `group_sex_mode` 被关闭不会让本 turn 剩余部分的 `_is_active()`
立即翻转为假,不是逐次调用时的实时判断(#4 自己的 `is_template`/`is_player_real` 判据除外——那两个额外
再判一次 `cache_obj.group_sex_mode`,是真正的实时口径)。

## 替换函数清单(10 个,全部薄 wrapper,无函数体复制)

| # | 目标函数 | wrapper 行为 | 服务功能 |
| --- | --- | --- | --- |
| 1 | `Script.Design.character_behavior.init_character_behavior` | `_depth += 1`;`_depth > 1` 或非 Tk 或非群交模式 → 直通(内层的记录/缓冲自然并入外层,疲劳退出正是发生在嵌套层里)。最外层:重置状态、`turn_active=True` → `call_original` → 绘制摘要页 + 一次 `WaitDraw` → 依序回放 `replay_queue` → 清理。`try/finally` 里递减深度、并在本 turn 确实接管过(turn_active 曾为 True)时兜底恢复绘制补丁(防 turn 中途异常把 UI 留在吞噬状态;非接管 turn 不触碰,避免误还原其他 mod 的补丁) | turn 边界、摘要、回放 |
| 2 | `Script.Design.talk.handle_talk_draw` | 非激活 → 直通。激活:按入参推当前行为 id(`_derive_talk_behavior_id`,与原函数 talk.py:281-289 同口径,不读 `character_data.behavior`——招呼口上等场景那里携带的是玩家行为 id 会读错),交给纯函数 `_talk_decision(character_id, now_behavior_id, second_behavior_id, is_h=None)` 按目标与范围"口上可见性五级判定"的优先级返回 `"pass"`/`"buffer"`/`"drop"` 三选一,wrapper 本身只是薄壳分支:`"drop"`→`return None`;`"buffer"`→套 `_ScopedBuffer` 后调原函数(落入回放队列);`"pass"`→直接调原函数(若正处在 #10 本地捕获窗口内则落入该窗口的本地列表,由 #10 按引擎产生顺序整块补绘,不再用 `_PristineWindow` 强行立即落地——那样会抢在 #10 缓冲的黄字寸止标题前面画出来,顺序错乱) | 五级口上可见性判定 |
| 3 | `Script.Design.settle_behavior.handle_settle_behavior` | 非激活 → 直通。激活:`call_original` 前存旧值、把 `_player_real_instruction_seen` 清零(结算计算照常执行,数值副作用全部保留);`call_original` 期间若 #4 命中过博士真实指令窗口,该标记会被置 `True`——命中则本次返回的属性变化面板必须原样交还上游绘制(`return panel`),不能吞;未命中(含非群交模式的普通调用、或本次结算全是模板派发)按原逻辑丢弃返回的面板(`return None`,上游 `character_behavior.py` 对该返回值的判断本就是短路安全的 `if panel != None and len(...)`)。`try`/`finally` 恢复旧值,兼容 `CSE_*` 事件触发的嵌套调用 | 抑制/放行属性面板 |
| 4 | `Script.Design.settle_behavior.handle_instruct_data` | 直通条件之外,当且仅当 `turn_active` 且 `cache.group_sex_mode` 且 `character_id==0` 且当前 `behavior_id != player_behavior_id`(模板派发中)**且 `behavior_id` 不属于结束族/`GROUP_SEX_TO_H`**(v5评审修正:settle_behavior.py:38-44 本就把这两类排除在模板循环外路由到普通分支,被路由到非模板分支的行为按定义不是模板派发;级联结束场景玩家 `behavior_id` 被中途改写而快照过期,不排除会把真实结束结算误判成模板派发、在玩家 target 本turn高潮过时整条跳过 529解放/407清H态/636穿衣,是改变游戏状态的错误)且玩家当前 `target_character_id` 已在 `orgasm_record` → 原样返回 `change_data` 不执行本次模板动作(功能1,唯一改变游戏结果的挂点)。同时用同一次调用的上下文标记两个显示层窗口(均 `try`/`finally` 恢复,嵌套安全):`is_template`(即上面判据的前半段,不看 `orgasm_record` 命中与否)成立时把 `_template_dispatch_active` 置 `True`;`is_player_real`(`character_id==0` 且 `behavior_id==player_behavior_id` 且 `target_character_id!=0` 且**不属于波及全体的结束族/全员玩具族**(`not _is_mass_instruction(behavior_id)`,v5用户裁定1a新增))成立时把 `_player_real_instruction_active` 置 `True` 并锁存 `_player_real_instruction_seen=True`。**v5新增第三件事**(用户裁定2a):只要 `behavior_id==Behavior.GROUP_SEX_NPC_HP_0_END` 就直接 `_mark_edge_break_reason(character_id, "tired", passthrough=False)`,不看 `character_id` 是否为0——tired判定的唯一挂点,见目标与范围第3条 | 功能1(跳过已高潮NPC的模板项)+ 功能4/口上五级判定的两个窗口标记(v5收窄)+ tired标记(v5新增) |
| 5 | `Script.Settle.orgasm_settle.orgasm_settle_in_second_behavior` | 非激活/玩家(id 0) → 直通。激活:读该角色 `h_state`,`_is_edge_release_event(orgasm_edge, orgasm_edge_count)` 命中(即 `orgasm_edge==2` 且计数非零,判据见目标与范围第3条)→ `_mark_edge_break_reason(character_id, "release", passthrough=not is_mass_end_release)` 写入断因,`is_mass_end_release`(`_is_mass_end_release_source`,v5用户裁定1b新增)判据是调用当下玩家实时 `behavior.behavior_id` 是否属于结束族——是则只记账不实时刷屏,否则(定向解放,如6014)保持实时刷屏;**v5起不再在这里判定tired**(已整体移到 #4,见上);再用本地列表(`_ScopedBuffer(target_list=...)`)捕获 `call_original` 期间的绘制(含函数体内的性爱发电提示直绘,以及嵌套其中的 #9 判定提示窗口),`character_id` 命中 `edge_fail_passthrough` 或 `_player_real_instruction_active` → 按序原样补绘(`_draw_live`,绕开任何生效中的外层缓冲);否则整段丢弃。之后照常扫描该角色 `character_data.second_behavior` 中非零的 `{part}_orgasm_{degree}`/`{part}_orgasm_edge` id,并入 `orgasm_record`/`edge_record`(按部位取最高档)。**挂这里而不是 `orgasm_judge`**:它是这些 id 的唯一写入点,寸止强制解放与时停解放不经过 `orgasm_judge` 但都经过它,一个挂点收口全部调用路径 | 功能1判据 + 摘要数据 + 发电提示隐去/放行 + 断因三分写入(release,v5起不再写tired)+ 批量结束解放不刷屏(v5新增) |
| 6 | `Script.UI.Panel.achievement_panel.draw_achievement_notice` | 非激活 → 直通;激活 → 定向缓冲下调原函数(默认 target_list,即全局 `replay_queue`——即便嵌套在 #5 的本地捕获窗口内也不受影响,见下方"定向缓冲"小节的嵌套隔离说明)。**挂这里而不是 `achievement_flow`**:它是全部成就的唯一绘制出口(全仓单一调用点),覆盖 turn 内多重绝顶成就(orgasm_settle.py:319-323,群交最高频成就)、turn 末群交/时停成就等所有来源,且函数体只有一个 WaitDraw,wrapper 最薄 | 成就后置回放 |
| 7 | `Script.Design.second_behavior.mark_effect` | 非激活 → 直通;激活 → 定向缓冲下调原函数。它在函数尾直接 `WaitDraw().draw()`,绕过 #2,必须单独包 | 刻印文本后置回放 |
| 8 | `Script.Design.handle_talent.gain_talent` | 同 #6/#7:激活 → 定向缓冲下调原函数(`handle_talent.py:71-73` 处画 WaitDraw,由 `character_behavior.py:189` 每角色每 turn 调用一次) | 素质取得后置回放 |
| 9 | `Script.Settle.orgasm_settle.judge_orgasm_edge_success` | 非激活 → 直通。激活:用本地列表捕获函数体内唯一一处判定提示绘制(orgasm_settle.py:417/419/430/433 四种成功/失败文本分支)——判定结果在函数返回前不可知,`call_original` 拿到真实 `bool` 返回值后才分流:失败 → `_mark_edge_break_reason(character_id, "fail")` 写入断因;成功但余量≤2(接近/超过极限,`_edge_margin` 公式与状态栏感叹号两档同源)→ 计入 `edge_near_limit`;失败、或余量≤2、或命中 `_player_real_instruction_active` → `_draw_live` 按序原样补绘本次判定提示;其余(平淡成功)整段丢弃 | 断因三分写入(fail)+ 极限预警放行 + 博士窗口放行 |
| 10 | `Script.Design.second_behavior.check_second_effect` | 非激活或 `character_id == 0`(玩家路径,同 #5 口径)→ 直通:玩家侧忍耐询问/射精面板文本若被本窗口捕获会变成有按钮无文字的残缺面板,直通规避;`local_orgasm_batch_talk_fix.py:194` 的 `if not character_id or ...` 本就把 `character_id == 0` 排除在批次接管外,直通不会重开泄漏。激活且非玩家:标记 `_second_effect_character=character_id`(供 #2 的 `_should_pass_through_talk` 判断寸止链放行是否在窗口内),用本地列表捕获 `call_original` 期间的一切绘制(含 `local_orgasm_batch_talk_fix` 在 `second_behavior_effect` 内直接手绘的黄字合并寸止标题/绝顶汇总行,完全绕开 `handle_talk_draw`,#2 看不见它,只能在这一层收口),`character_id` 命中 `edge_fail_passthrough`、`edge_near_limit` 或 `_player_real_instruction_active` → 按序 `_draw_live` 原样补绘;否则整段丢弃 | 断因链/极限预警/博士窗口的批次汇总放行,收口 batch_talk_fix 的直绘泄漏 |

## 关键机制

### 功能 1 的语义边界(默认决定,可改)

- 只有"高潮成功"触发跳过;**寸止不触发**(寸止本就是"没让它高潮")。
- 玩家自选动作永不跳过(#4 的 `behavior_id != player_behavior_id` 门)。已知可接受的边角:模板里恰好存在与玩家自选同 id 的项时,该项也不会被跳过——罕见且语义上无害。
- 一个 NPC 占多个模板槽时,第一槽让它高潮,后续槽被 #4 跳过——正是需求语义。
- NPC 阶段的 `npc_ai_in_group_sex` 不替换:它只为下一 turn 排程,记录在下一 turn 开头已重置,拦它无意义(且该函数已被 chain_gate mod 占用,不可再挂)。
- #4 的模板跳过判据是 8 个 hook 里**唯一改变游戏结果**的部分;#4 内同时承载的两个显示层窗口标记(`_template_dispatch_active`/`_player_real_instruction_active`)是纯显示层,不影响这条边界。

### 输出抑制与放行的完整分类

| 类别 | 路径 | 处理 |
| --- | --- | --- |
| 常规口上 + 二段行为标题 | `handle_talk_draw`(经核查为唯一 Tk 出口,7 个调用点全在 talk.py) | 按口上五级判定(#2)分流:寸止链/极限放行 → 直显;博士真实指令窗口 → 直显;白名单 → 缓冲回放;黑名单(模板派发/背景H)→ 吞;其余 → 默认直显 |
| 属性面板 + 逐动作暂停 | `handle_settle_behavior` 返回面板 | 命中博士真实指令窗口(`_player_real_instruction_seen`)→ 原样返回;否则吞(#3 返回 None) |
| 寸止判定提示 | `judge_orgasm_edge_success` 内唯一一处直绘 | 平淡成功(余量>2)吞;接近/超过极限的成功(余量≤2)只放行提示本身;失败原样直显;命中博士窗口同样直显(#9) |
| **寸止断了导致的高潮链**(判定提示 + 二段标题/口上 + 发电提示 + batch_talk_fix 手绘汇总) | #9 捕获窗口(失败) / #5 入口 `_is_edge_release_event` 判据(解放) + #2 五级判定第1档(`_should_pass_through_talk`,命中角色在其自己的 #10 窗口内整链放行) + #5/#10 捕获窗口 | **原样实时显示**(摘要页仍记入该角色行,按断因分 `<累>`/`<寸止释放>`/`<寸止失败>`;#9 失败提示因执行更早自然排最前)。**v5例外(用户裁定1b)**:源自"结束群交等全体类结束指令"(effect 529)的批量解放不实时显示,只记账供摘要页显示 `<寸止释放>`;定向单人解放(如6014)不受影响,仍全程实时直显 |
| 性爱发电提示(普通高潮触发) | `orgasm_settle_in_second_behavior` 内直绘(orgasm_settle.py:322-329 附近) | 吞(#5 本地捕获,非断因链/非博士窗口则丢弃) |
| `local_orgasm_batch_talk_fix` mod 手绘的多部位寸止合并标题 / >3 部位绝顶汇总行 | `_draw_orgasm_info_text`(该 mod 脚本第 69-78 行),调用点第 163/172 行,`gold_enrod` `WaitDraw`,绕开 `handle_talk_draw` | #10 本地捕获,断因链/极限预警/博士窗口原样补绘、否则丢弃 |
| 搾乳机 / 采尿器提示(`Second_effect.py:2146` `handle_milking_machine`、`:2198` `handle_urine_collector` 内 `NormalDraw`) | `second_behavior_effect` 分发,`check_second_effect` 的下游 | #10 本地捕获范围连带覆盖:非断因链/非博士窗口则整段丢弃 |
| 博士真实指令直接引发的一切(口上/属性面板/二段链) | `_player_real_instruction_active` 命中窗口内的任意 #2/#3/#5/#9/#10 调用 | 原样实时放行,不分白名单/黑名单 |
| 白名单口上(疲劳退出、加入/受邀/发现群交、正常/异常结束群交) | `handle_talk_draw` 五级判定第3档 | 缓冲回放(#2) |
| 模板派发窗口口上 / 群交NPC背景H口上 | `handle_talk_draw` 五级判定第4档(黑名单) | 吞 |
| 成就 / 刻印 / 素质取得 | #6 / #7 / #8 | 缓冲回放 |
| 事件、子事件 | `DrawEventTextPanel`(覆写 draw,天然免疫缓冲) | 原地放行 |
| 玩家射精忍耐/射精面板、发现群交面板 | 带按钮 + `askfor_all` 的交互面板 | 原地放行 |
| 玩家太累结束 H 提示(handle_npc_ai.py:93-99)| 直接 WaitDraw | 原地放行(此时群交正在结束,可接受) |
| 理智不足源石技艺中断(realtime_settle.py:504-509)、无意识恢复提示 | 直接绘制,低~中频 | 原地放行,试玩后哪个真的碍事再为其加同构缓冲 wrapper(每个 +5 行),不预先加 |

**白名单**(常量均已确认存在):`Behavior.GROUP_SEX_END`(玩家正常结束群交)、`Behavior.GROUP_SEX_NPC_HP_0_END`、
`Behavior.GROUP_SEX_PL_HP_0_END`、`Behavior.JOIN_GROUP_SEX`、`Behavior.DISCOVER_OTHER_SEX_AND_JOIN`、
`Behavior.BE_INVITED_JOIN_GROUP_SEX`、`SecondBehavior.BE_INVITED_JOIN_GROUP_SEX`,以及
`constant.special_end_H_list` 全部成员(`H_INTERRUPT`/`H_HP_0`/`T_H_HP_0`/`HYPNOSIS_CANCEL`/`TIME_STOP_OFF`,
与前面重复的成员并入 set 后自动去重)。白名单由 `_talk_whitelist()` 懒加载缓存为一个模块内集合常量,试玩后
增删即可。

### 波及全体的指令族(v5新增,用户裁定1a/1b)

`_talk_whitelist()` 覆盖的是"该显示的口上"这一更宽的范围(含 `JOIN_GROUP_SEX` 等"加入"类,非结束语义)。
v5为 #4 的 `is_player_real` 排除、#5 的批量解放判据新增两个更窄的族,均为懒加载缓存的纯函数:

- **`_mass_end_behavior_family()`**:`{Behavior.GROUP_SEX_END, Behavior.GROUP_SEX_NPC_HP_0_END} |
  set(constant.special_end_H_list)`——即白名单去掉"加入"族后的"结束"子集(`Behavior.GROUP_SEX_PL_HP_0_END`
  已在 `special_end_H_list` 内,见 `Script/Core/constant/__init__.py:293`)。用户原话只提"结束群交及同族",
  "加入"类不是结束语义,不应混入。
- **`_mass_toy_behavior_family()`**:`{REMOTE_ALL_TURN_OFF_SEX_TOY, REMOTE_ALL_SET_SEX_TOY_WEAK,
  REMOTE_ALL_SET_SEX_TOY_MEDIUM, REMOTE_ALL_SET_SEX_TOY_STRONG}`(`Script/Core/constant/Behavior.py:720-738`)。
  经核实均通过 `chara_handle_instruct_common_settle` 调用(未显式传 `target_character_id`),与
  `GROUP_SEX_END` 同样存在"继承玩家当前遗留 `target_character_id`"的结构性风险;`group_sex_panel.py:98-134`
  的 `count_group_sex_instruct_list()` 确认这4个id不在per-member模板派发列表内,是真正的"影响全体成员"
  指令。"全员寸止"类指令确实存在——已启用的 group_sex_extension mod 有三条全员自定义指令
  (`group_sex_extension.py:227` 全员寸止 / `:245` 全员戴玩具 / `:266` 全员催眠增强),但其 handler 直接改
  NPC 数据后绘制结果返回,从不调 `chara_handle_instruct_common_settle`、不设 `behavior.behavior_id`、不触发
  `game_update_flow`,#4 永远看不到它们,没有 behavior_id 可补进本族——不补不是因为指令不存在,而是它们
  不经过本判据所在的挂点(其中"全员寸止"给全员置 `orgasm_edge=1`,恰是裁定1b要抑制的"结束群交时一大串
  批量解放"的最典型来源,本轮修复经 effect 529 实时读判据已覆盖它)。
- **`_is_mass_instruction(behavior_id)`**:两族的并集判定,供 #4 的 `is_player_real` 排除条件使用。
- **`_is_mass_end_release_source(player_current_behavior_id)`**:单独判定是否属于结束族(不含玩具族——
  玩具族不触发 effect 529,与批量解放无关),供 #5 判定本次release是否源自批量结束链使用;必须传入调用
  当下的实时值,不能传 turn 开头快照,理由见目标与范围第3条 `<寸止释放>` 段落。

### 定向缓冲(scoped tee)

上下文管理器,只在 #2 白名单/放行分支、#5、#6、#7、#8、#9、#10 的调用窗口内生效,绝不全局常开(全局拦截会缓冲掉交互面板的按钮,代码等输入 → 卡死)。四条实现纪律:

1. **只 patch 三个类**:`NormalDraw`、`WaitDraw`、`LineFeedWaitDraw`——各窗口内实际只会产生这三种(talk 经 rich_text 产出前两者+LineFeedWaitDraw,#6/#7/#8/#9 只用 WaitDraw/NormalDraw)。多 patch 只扩大风险面。
2. **存值不存对象**(见状态表 `replay_queue` 一行)。
3. **嵌套安全**:`__enter__` 保存的是进入那一刻的方法(不是全局"原始函数"),`__exit__` 用 `finally` 恢复;窗口可能嵌套(缓冲中的 mark_effect 内部再触发白名单口上,或 #5 的本地捕获窗口内嵌套 #9 的本地捕获窗口)。#1 的 `finally` 再整体兜底恢复一次。
4. **target_list 可参数化**(`_ScopedBuffer(target_list=...)`)。默认 `None` 时写入全局 `replay_queue`(回放语义,#2/#6/#7/#8 用法不变);#5/#9 显式传入各自的本地列表(捕获语义)——函数返回后调用方自己决定这份捕获内容是丢弃还是经 `_draw_live` 原样补绘。`_draw_live` 直接调用 `_PRISTINE_DRAW_METHODS` 里记录的原始 `draw`,绕开当前任何生效中的外层缓冲——#9 嵌套在 #5 窗口内时,#9 决定放行的那一刻仍处于 #5 的窗口中,若用普通 `.draw()` 会被 #5 的缓冲二次吞掉,故必须走原始方法。没有新造一套"丢弃模式"类,复用同一个 `_ScopedBuffer` 机制,只是多了一个可选参数。#10 同一手法多一层,嵌套是真实发生的:`second_behavior.py:98/121` 在 `check_second_effect` 内部直接调 `orgasm_judge`,`orgasm_judge` 再调 `orgasm_settle_in_second_behavior`(#5),其内部又调 `judge_orgasm_edge_success`(#9)——调用栈是 `check_second_effect`→`orgasm_judge`→#5→#9,#5/#9 的窗口确实嵌套在 #10 的窗口内。不重复靠两条:①嵌套的 `_ScopedBuffer` 各自只保存/写自己进入那一刻生效的 `draw` 方法,#5/#9 窗口内产生的绘制被它们自己当前生效的缓冲闭包捕获进各自本地列表,不会落进 #10 的列表;②#5/#9 决定补绘时走 `_draw_live`,绕开 `target_class.draw` 属性查找直接调 `_PRISTINE_DRAW_METHODS[draw_class]`,不经过当前任何生效中的补丁(含 #10),因此也不会被 #10 二次捕获。

5. **`_PristineWindow`**——与 `_ScopedBuffer` 是两个不同职责的上下文管理器:`_ScopedBuffer` 把当前 `.draw()` 换成"记录不绘制"的缓冲闭包;`_PristineWindow` 反过来强制换回从未被 patch 的原始方法,退出时精确恢复为进入前的值。**生产代码目前不使用**(9c3f29402 起):原用于 #2 放行分支"立即落地",但立即落地恰恰是顺序错乱的根源(抢在 #10 缓冲的黄字寸止标题之前);现放行内容改为落入 #10 缓冲按引擎顺序补绘。类保留(自检仍覆盖),供日后需要"绕过一切缓冲立即绘制"的场景使用。

### 摘要页版式(eraFL 式单行结算)

```
────────────── 本轮群交结算 ──────────────
                       能天使： 三重绝顶：口・阴道强绝顶、肛肠小绝顶
                     德克萨斯： <寸止> 阴蒂、心理绝顶寸止
                           空： 绝顶：胸小绝顶/阴道绝顶寸止×2
──────────────────────────────
                    (点击继续)
```

- 只列 NPC;只列本 turn 有高潮/寸止记录、或本 turn 因太累退出(`<累>`,v5用户裁定2b,不要求同时有高潮/寸止
  记录)的角色(既无记录又非tired的 turn 整页跳过)。
- 姓名列用 `RightDraw` 锚定在 `text_width // 3` 处右对齐,颜色取 `character_data.text_color`(无则 standard);
  后接全角冒号 `：`。
- 寸止/断因标记(`_edge_status_tag`,分两种情况,v5起判据从 `edge_fail_passthrough` 改为 `_edge_break_reason`
  ——是否显示断因标记是记账语义,与是否曾实时刷屏(`edge_fail_passthrough`)无关,详见目标与范围第3条):
  - 该角色在 `_edge_break_reason` 中有条目(本 turn 寸止断了过,或太累退出,不论是否曾实时刷屏)→ 按
    `_edge_break_reason` 查表,经 `_edge_break_tag_and_style` 返回三选一断因标记:`tired`→
    `little_dark_slate_blue` 的 `" <累>"`(v5改用与状态栏疲劳标记同色,`character_info_head.py:148-153`,
    此前误用的 `hp_point` 已废弃);`release`→`gold_enrod` 的 `" <寸止释放>"`;`fail`→`gold_enrod` 的
    `" <寸止失败>"`(`release`/`fail` 同色不同字)。这类角色的寸止已经兑现成绝顶(或被打断)或角色已太累
    退出,再按憋着的三档报警度显示会误导——且解放/失败时上游会清零 `h_state.orgasm_edge_count`,实时
    margin 恒为最宽松档,按三档只会显示最轻的档位,与事实相反。
  - 否则(纯粹仍憋着,`edge_record` 有该角色条目但未命中 `_edge_break_reason`)→ 与状态栏
    (`character_info_head.py:237-257`)完全对齐的三档:`margin = 玩家寸止技巧(ability[30])*3 - 该角色各
    部位本次寸止次数的平方和`;`margin>=3` 为 `hot_pink` 的 `" <寸止>"`,`0<=margin<3` 为 `red` 的
    `" <寸止!>"`,`margin<0` 为 `levelex` 的 `" <寸止!!>"`。档位按摘要绘制那一刻的实时游戏状态计算(不是本
    turn 寸止次数累计值)。
  - 两个角色都无记录时不显示任何标记。
- "N重绝顶"= 该角色 `orgasm_record` 的部位数(按部位最高档去重后),与上游 `plural_orgasm` 口径一致,冒号为全角。
- 寸止 token:只列"仍憋着"的部位(已解放的部位本 turn 真的高潮了,归绝顶侧显示,不再重复列进寸止侧,消除
  "同一部位又高潮又寸止"的自相矛盾,该经历改由断因标记表达);按次数分组,组内部位 `、` 连接,组末缀"绝顶
  寸止"(次数>1 加 `×N`);与绝顶描述同时存在时用 `/` 连接,寸止 token 部分整体着色 `hot_pink`。
- 页眉页脚用现成的 `draw.LineDraw` 横线 + `draw.CenterDraw` 居中标题,不新增绘制类;摘要行为空时整页(含页眉
  页脚与该次等待)直接跳过。摘要页之后按序回放 `replay_queue`,队列空则直接结束。

### 寸止相关二段行为 id 的 success-only 事实

静态核对 `orgasm_settle.py:180-292`(`orgasm_settle_in_second_behavior` 内部)确认:`{part}_orgasm_edge`
这一族二段行为 id **只在寸止判定成功时才会置位**——成功分支在设置该 id 后 `continue` 提前跳出本部位循环;
失败分支则清空 `orgasm_edge_count`、置 `h_state.orgasm_edge=2`,转而落入普通的 `{part}_orgasm_{degree}`
档位路径。也就是说"寸止成功"与"寸止失败导致的绝顶"分别唯一对应 `_orgasm_edge` 后缀族与
`_orgasm_{degree}` 后缀族两个**互斥**的 id 家族。

## 已知语义后果

- **结束群交等全体类指令不再算博士真实指令窗口(v5用户裁定1a,此前是"预期行为",现已按用户裁定收窄)**:
  玩家亲自下达"结束群交"(`Behavior.GROUP_SEX_END`)时,该次调用的 `character_id`/`behavior_id`/
  `target_character_id` 三项虽仍可能满足 `is_player_real` 表面条件,但 v5 新增的
  `not _is_mass_instruction(behavior_id)` 排除项(见目标与范围第4条、"波及全体的指令族"小节)会让结束族
  (及同族的异常结束、全员玩具族)恒不满足 `is_player_real`——不再走第2档全显,而是回落到第3档白名单
  (只显示一句"结束了群交"的白名单口上,回放队列兜底)。该指令引发的批量解放链(effect 529)是否实时刷屏
  由 #5 的 `_is_mass_end_release_source` 独立判定(用户裁定1b),默认不实时刷屏,只记账供摘要页
  `<寸止释放>` 显示。这正是用户明确否掉的"结束群交时一大串实时刷屏"观感问题的修复,替换了 v3 记录的旧
  "预期行为"结论。
- **太累退出恒挂 `<累>`,不再要求有寸止蓄积(v5用户裁定2a/2b,修复了以下两条 v3 记录的旧限制)**:
  v3版 `<累>`/`<寸止释放>`/`<寸止失败>` 三选一标记只在角色命中 `edge_fail_passthrough`(即
  `_is_edge_release_event` 或 #9 失败判定确实写入过)时才会显示,导致两个已知限制——①无寸止蓄积的疲劳
  退出(`orgasm_edge` 从未置过 2)不挂 `<累>`;②同 turn 先寸止失败再疲劳退出时,断因停留在 `<寸止失败>`
  而非 `<累>`(因 `orgasm_edge_count` 已被失败分支清空,`_is_edge_release_event` 判定不成立)。v5 起
  tired 判定整体移到 #4,只要看到 `behavior_id==Behavior.GROUP_SEX_NPC_HP_0_END` 就无条件标记
  `_mark_edge_break_reason(character_id, "tired", passthrough=False)`(见目标与范围第3条),不再依赖
  `_is_edge_release_event`,①②两个限制均已修复:太累退出的角色恒挂 `<累>`(优先级最高,不会被之前的
  `fail`/`release` 记录覆盖),即便本 turn 完全没有绝顶/寸止记录也会单独成行(`_summary_row_character_ids`
  新增第三来源,见目标与范围第3条摘要行纳入段落)。
- **功能4的属性面板是整次 `handle_settle_behavior` 调用的合并面板**:`group_sex_mode` 下
  `character_id==0` 的那一次 `call_original` 内部会连续处理"博士真实指令"与"整段模板派发循环"两部分
  (settle_behavior.py:51-68),二者共用同一个返回的面板对象。#3 只能整体放行(`_player_real_instruction_seen`
  命中)或整体吞掉,无法在 wrapper 层按来源把面板拆成"博士这部分"和"模板那部分"分别处理——这是薄 wrapper
  实现方式的天然局限,不是遗漏。

### 三.2 根因复核(评审证据 vs 静态代码核对)

协调者转达的用户截图证据指向"该角色有无匹配口上语料决定 #2 wrapper 推导走向、无语料时存在兜底放行分支"。
对此做了两项独立核对:
1. 语料存在性:对 `data/talk/`、`data/talk_common/` 原始 CSV 及编译产物 `data/Character_Talk.json` /
   `data/Talk_Common.json` 做穷举检索,未发现任何 `{part}_orgasm_edge` 对应的语料条目(唯一相关匹配是
   无关的玩家指令 id `orgasm_edge_off`,非二段行为 id)——即全部角色对 `_orgasm_edge` 族均无语料,不存在
   "部分角色有、部分没有"的语料差异,该假说被数据证伪。
2. 代码路径:核对早期版 `modded_handle_talk_draw` 的分支结构,推导不出行为 id 时唯一路径是 `return None`
   (吞),不存在任何"推导失败→ 放行"的兜底分支。
   
静态复核未能重现"语料差异"这一具体假说,但真因随后由协调者定位、并经本 mod 独立读源码核实:
`mod/local_orgasm_batch_talk_fix/scripts/local_orgasm_batch_talk_fix.py` 的 `_draw_orgasm_info_text`
(第 69-78 行,`gold_enrod` 样式的手绘 `WaitDraw`)在 `patched_second_behavior_effect` 内被直接调用——
第 163 行(>3 部位绝顶按强度分组的汇总行)、第 172 行(多部位寸止合并标题)。该 mod 包装的是
`Script.Design.second_behavior.second_behavior_effect`,在其函数体内直接 `.draw()`,完全绕开
`talk.handle_talk_draw`(#2 唯一能看到的绘制出口),因此不受 #2 白名单/放行逻辑影响,是与早期语料假说
完全独立的另一条泄漏路径——两次核对本身没有矛盾,只是分别核对了两个不同的可能机制,第二个才是真的。

**收口方案**:不修改 `local_orgasm_batch_talk_fix.py`(协调者裁定:它是冻结复核的 fix-mod,不因本 mod 的
需要改动)。改为在调用树的上一层收口——`check_second_effect` 是 `second_behavior_effect` 唯一的调用点
(`settle_behavior.py:426/440`),新增 #10 wrapper 包装它,用本地列表捕获整个 `call_original` 期间产生的
一切绘制(不论来自上游原函数还是 `local_orgasm_batch_talk_fix` 的直绘,只要经过 `.draw()` 就会被捕获),
按断因/极限预警/博士窗口的结果决定原样补绘还是整段丢弃——与 #5/#9 同一套语义,不针对某个具体 mod 写
特判,天然也覆盖将来其他 mod 在这条调用链上新增的任何直绘。

## 实现期核对点

1. #8 素质提示函数的确切名字(handle_talent.py:71-73 所在函数,已确认为 `gain_talent`)。
2. `orgasm_record` 扫描处对玩家(character_id=0)的处理:玩家路径的射精/绝顶另有面板,记录里排除 id 0 即可。
3. 白名单各常量对应的 talk 侧取值口径(#2 内按入参推导后与常量比对)。
4. 试玩验证:嵌套 turn(疲劳结束群交)路径上摘要只出现一次、且在最外层末尾。
5. `edge_fail_passthrough` 是 turn 级、只增不减的集合(不做单次事件后移除),角色本 turn 内寸止断了一次后,
   该 turn 剩余时间内其绝顶族标题/口上/发电提示均按原样直显处理。

**已知低概率边角**(评审后记录,暂不处理,试玩碰到再修):
1. 白名单口上内若夹带 `ImageDraw` 图片,图片不经定向缓冲(只 patch 三个文字类),会与被缓冲的文字乱序显示。
2. 玩家同一 turn 内被多次结算时,`player_behavior_id` 只在 turn 开头捕获一次;若玩家中途改变自选动作,理论上可能误跳玩家的新选择,实战概率低。
3. `local_orgasm_batch_talk_fix` 的 >3 部位黄色汇总行是在 `second_behavior_effect` 函数体中途手绘的,被 #10 捕获后要等 `call_original` 整体返回才按序补绘,相当于被推迟到 `check_second_effect` 窗口末尾——与其前后的口上/二段标题存在轻微顺序错位(汇总行本该夹在中间,现在挪到最后)。接受,试玩若观感明显再收紧捕获粒度。

## 改动量与维护性

- 脚本约 1600 行(含中文注释与自检);对本体 **0 行修改**。
- 10 个薄 wrapper + 1 个可参数化(target_list)的上下文管理器(`_ScopedBuffer`) + 1 个临时强制转回原始
  draw 方法的上下文管理器(`_PristineWindow`,当前未在生产路径使用) + 1 个 `_draw_live` 直绘辅助函数,零
  函数体复制;若干纯函数(`_should_pass_through_talk`/`_is_group_sex_background_h`/`_talk_decision`/
  `_is_tired_exit`/`_is_edge_release_event`/`_mass_end_behavior_family`/`_mass_toy_behavior_family`/
  `_is_mass_instruction`/`_is_mass_end_release_source`(v5新增,用户裁定1a/1b/2a)等)抽出判据逻辑,便于
  `_self_check()` 覆盖。
- 上游脆弱面 = 10 个函数的签名 + `{part}_orgasm_{degree}` / `{part}_orgasm_edge` id 命名约定 +
  `character_info_head.py` 的寸止状态栏公式(三处口径同步依赖,上游改动其一都需要同步本 mod),均为项目
  长期稳定接口。
