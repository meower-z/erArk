"""决定"谁在什么时刻做什么"的模块。

游戏里玩家和 NPC 各自做行动，每个行动占用若干分钟的游戏时间。本包里每个部分各自独立，彼此不直接调用：
- scheduler 包：按时间顺序执行各角色的行动，直到轮到玩家输入。不知道任何游戏规则。
- npc_ai：轮到某个 NPC 时，为它选择下一个行动。
- action：两者共用的"行动"数据类型。

把它们接到游戏结算上的代码不在本包，在 Script/Design/game_actions.py 和 Script/Design/action_execution.py。
"""
