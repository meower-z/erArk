# 行动调度器

[Scheduler](../../Script/Modules/scheduler.py) 保存各角色接下来要做的事，按时间依次执行，直到轮到玩家选择行动。

一条待办用 `Task(actor, at, item, immediate=False)` 表示，包含角色编号、开始时刻、要做的事和是否立即执行。
其中 `item` 可以是具体行动，也可以是表示“让 NPC 选择行动”的 `AI`，或表示“等待玩家输入”的 `INPUT`。

调用方通过 `submit(task)` 添加待办、`replace(task)` 替换待办、`pending(actor)` 查询待办；每个角色保留一条有效待办。
`advance_until_input()` 推进行动，遇到玩家输入待办时返回；立即任务优先执行，普通任务按时间排序，同时刻人物以玩家输入优先，其余按提交顺序执行。

[game_actions](../../Script/Modules/game_actions.py) 创建调度器时，把 `choose_next` 和 `execute` 两个函数交给它。
轮到 NPC 自主选择时，调度器调用 `choose_next(actor, now)` 来选择这个 NPC 的下一个行动（这个函数应该进一步调用 NPC AI 模块）；取得行动后，调用 `execute(actor, action)` 执行该角色的行动（接入结算逻辑），并返回本次占用的分钟数。
`execute` 返回后，若已为该角色安排下一条待办，调度器就沿用它；否则，在本次行动结束时（即开始时刻加上 `execute` 返回的分钟数），安排 NPC 再次选择行动或等待玩家输入。
