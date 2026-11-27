"""
插件模块在内核里的加载顺序
==========================
LOAD_ORDER 由内到外列出各模块的文件。core.load 之后，内核只调用内核自己与这里列出的文件登记的钩子。
输入钩子由外到内调用，输出钩子由内到外调用。
一个输入钩子截下调用（Intercept）时，内层的钩子都不调用，只调用更外层的模块的输出钩子。
domains 的 medical、power、needs、pregnancy、abilities、facility、economy、work、warehouse、production、
kitchen、commission、location、visitor、recruit、official、diplomacy、dormitory、library、playthrough、
country、modes、bookmarks、achievement、history、plan、entertainment、tallies、fridge、prison、
education、maintenance、physical_exam、flags、action_info、player_ability、player_collection、roster、
npc_template、growth、status、inventory、wardrobe、body_manage、h_meters、h_state、dirty、hypnosis、
first_record、relations、chara_life、chara_profile、activity、identity 与 scene_state 排在最内，不挂钩子。
它们登记 working 的键：medical、power、facility、official、plan、education 与 roster 各三个，needs、work、
warehouse、commission、recruit、library、playthrough、entertainment、prison、inventory、h_meters 与
first_record 各两个，abilities、modes、history 与 chara_profile 各四个，economy 与 physical_exam 各七个，
maintenance 五个，relations 与 activity 各十个，chara_life 十三个，其余各一个。relations、chara_life 与
chara_profile 的键是角色键（domains.chara_key），不登记规则。needs、h_meters 分别登记 body.needs、h.meters 规则。
economy 登记今日收入与买卖总量两键规则。warehouse 登记库存规则。tallies、fridge 登记 base.tallies
与 base.fridge 规则。abilities 给四键各登记规则。status、inventory 登记 body.status、inventory.items 规则。
PickNextAction 上的输入钩子由外到内是：save_load 的自动存档、计划队列、tk_ui 的玩家选择。
内核本体给出 1 分钟的 Idle，npc_action_choice 的输出钩子把干员的 Idle 换成要开始的行动。
StartAction 上 gameplay_resolution 的输入钩子里，开始门（start_gate）在开始前的复查（starts.recheck）之外，
复查看到的是过了门的行动。最里层的是 actions 的时停（actions.time_stop），门与复查换上的行动都经过它。
tk_ui 的 orders 排在 player_hook 与 working 之间，在 StartAction 与 kernel.Reset 上挂输入钩子。
ApplyEffects 上由外到内是 plan_queue、cloth_see、working。working.flush 因此在 plan_queue.drain 之后运行，
看得到 drain 补上的角色加入与移除。cloth_see.look 也在 flush 之前把看见的内衣写进这一步的缓冲区。
save_load 的 settings 在 kernel.Reset 上的输出钩子在每次换 GameState 后再装一次全局设置。
save_load 的 reset 排在最外，它在 kernel.Reset 上的输入钩子最先运行，按原因跑读档、新周目、新游戏的步骤。
"""

from types import ModuleType

from Script.Modules.domains import abilities, achievement, action_info, activity
from Script.Modules.domains import body_manage, chara_life, chara_profile
from Script.Modules.domains import commission, country, diplomacy, dirty
from Script.Modules.domains import dormitory, economy, education, entertainment
from Script.Modules.domains import facility, first_record, flags, fridge, growth
from Script.Modules.domains import (
    h_meters,
    h_state,
    history,
    hypnosis,
    identity,
)
from Script.Modules.domains import inventory, kitchen, library, location
from Script.Modules.domains import maintenance, medical, modes, needs, official
from Script.Modules.domains import physical_exam, plan, player_ability
from Script.Modules.domains import player_collection, playthrough, power
from Script.Modules.domains import pregnancy, prison, production, recruit
from Script.Modules.domains import relations, roster, scene_state, status
from Script.Modules.domains import bookmarks, tallies, visitor
from Script.Modules.domains import npc_template, wardrobe, warehouse, work
from Script.Modules.gameplay_resolution import (
    actions,
    cloth_see,
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
from Script.Modules.tk_ui import callbacks, instruct_callbacks, orders
from Script.Modules.tk_ui import player_hook, player_pick

LOAD_ORDER: tuple[ModuleType, ...] = (
    medical,
    power,
    needs,
    pregnancy,
    abilities,
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
    playthrough,
    country,
    modes,
    bookmarks,
    achievement,
    history,
    plan,
    entertainment,
    tallies,
    fridge,
    prison,
    education,
    maintenance,
    physical_exam,
    flags,
    action_info,
    player_ability,
    player_collection,
    roster,
    npc_template,
    growth,
    status,
    inventory,
    wardrobe,
    body_manage,
    h_meters,
    h_state,
    dirty,
    hypnosis,
    first_record,
    relations,
    chara_life,
    chara_profile,
    activity,
    identity,
    scene_state,
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
    orders,
    callbacks,
    instruct_callbacks,
    working,
    cloth_see,
    plan_queue,
    settings,
    autosave,
    reset,
)
""" 由内到外的模块文件 """
