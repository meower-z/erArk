"""
插件模块在内核里的加载顺序
==========================
LOAD_ORDER 由内到外列出各模块的文件。core.load 之后，内核只调用内核自己与这里列出的文件登记的钩子。
输入钩子由外到内调用，输出钩子由内到外调用。
一个输入钩子截下调用（Intercept）时，内层的钩子都不调用，只调用更外层的模块的输出钩子。
domains 的 medical、power、needs、pregnancy、facility、economy、work、warehouse、production、kitchen、commission、
location、visitor、recruit、official、diplomacy、dormitory 与 library 排在最内，不挂钩子。它们登记 working 的键。
medical、power、facility 与 official 各登记三个。economy 登记七个。work、warehouse、commission、recruit 与 library
各登记两个。其余各登记一个。
needs 还登记它的键的规则。economy 还登记今日收入与今日买卖总量两个键的规则。warehouse 还登记库存的规则。
PickNextAction 上的输入钩子由外到内是：save_load 的自动存档、计划队列、tk_ui 的玩家选择。
内核本体给出 1 分钟的 Idle，npc_action_choice 的输出钩子把干员的 Idle 换成要开始的行动。
StartAction 上 gameplay_resolution 的输入钩子里，开始门（start_gate）在开始前的复查（starts.recheck）之外，
复查看到的是过了门的行动。最里层的是 actions 的时停（actions.time_stop），门与复查换上的行动都经过它。
ApplyEffects 上 working 排在 plan_queue 之内。
working.flush 因此在 plan_queue.drain 之后运行，看得到 drain 补上的角色加入与移除。
save_load 的 settings 在 kernel.Reset 上的输出钩子在每次换 GameState 后再装一次全局设置。
save_load 的 reset 排在最外，它在 kernel.Reset 上的输入钩子最先运行，按原因跑读档、新周目、新游戏的步骤。
"""

from types import ModuleType

from Script.Modules.domains import (
    commission,
    diplomacy,
    dormitory,
    economy,
    facility,
    kitchen,
    library,
    location,
    medical,
    needs,
    official,
    power,
    pregnancy,
    production,
    recruit,
    visitor,
    warehouse,
    work,
)
from Script.Modules.gameplay_resolution import (
    actions,
    edits,
    events,
    npc_starters,
    panel_starters,
    plan_queue,
    player_starters,
    start_gate,
    starts,
    time_hooks,
    working,
)
from Script.Modules.npc_action_choice import choose, npc_hook
from Script.Modules.save_load import autosave, reset, settings
from Script.Modules.tk_ui import player_hook, player_pick

LOAD_ORDER: tuple[ModuleType, ...] = (
    medical,
    power,
    needs,
    pregnancy,
    facility,
    economy,
    work,
    warehouse,
    production,
    kitchen,
    commission,
    location,
    visitor,
    recruit,
    official,
    diplomacy,
    dormitory,
    library,
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
    edits,
    player_pick,
    player_hook,
    working,
    plan_queue,
    settings,
    autosave,
    reset,
)
""" 由内到外的模块文件 """
