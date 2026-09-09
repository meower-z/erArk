# 行动模块

[调度器](../../Script/Modules/scheduler.py)负责安排角色何时行动、何时交还玩家输入；[NPC AI](../../Script/Modules/npc_ai.py)负责角色自主选择，角色的需求与意图由具体 AI 逻辑维护。两者通过 [Action](../../Script/Modules/action.py) 交接一次行动的意图，执行中的状态由 Behavior 保存。[游戏接入层](../../Script/Modules/game_actions.py)负责将游戏效果、强制后续和角色状态接入调度流程。理解执行顺序从调度器读起，理解具体游戏规则从接入层读起。
