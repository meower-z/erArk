"""
四个模块在内核里的加载顺序
==========================
LOAD_ORDER 由内到外列出各模块的文件。core.load 之后，内核只调用内核自己与这里列出的文件登记的钩子。
输入钩子由外到内调用，输出钩子由内到外调用。一个输入钩子截下调用（Intercept）时，内层的钩子都不调用，只调用更外层的模块的输出钩子。
PickNextAction 上的输入钩子由外到内是：save_load 的自动存档、计划队列、tk_ui 的玩家选择。
内核本体给出 1 分钟的 Idle，npc_action_choice 的输出钩子把干员的 Idle 换成要开始的行动。
StartAction 上 gameplay_resolution 的输入钩子里，开始门（start_gate）在开始前的复查（starts.recheck）之外，
复查看到的是过了门的行动。
save_load 的 settings 在 kernel.Reset 上的输出钩子在每次换 GameState 后再装一次全局设置。
"""

from types import ModuleType

from Script.Modules.gameplay_resolution import (
    actions,
    events,
    npc_starters,
    panel_starters,
    plan_queue,
    player_starters,
    start_gate,
    starts,
    time_hooks,
)
from Script.Modules.npc_action_choice import choose, npc_hook
from Script.Modules.save_load import autosave, settings
from Script.Modules.tk_ui import player_hook, player_pick

LOAD_ORDER: tuple[ModuleType, ...] = (
    actions,
    starts,
    npc_starters,
    player_starters,
    panel_starters,
    start_gate,
    time_hooks,
    events,
    choose,
    npc_hook,
    player_pick,
    player_hook,
    plan_queue,
    settings,
    autosave,
)
""" 由内到外的模块文件 """
