# -*- coding: UTF-8 -*-
"""
群交摘要视图（group_sex_summary）。

仅在 cache.group_sex_mode 开启的 turn 内生效，且仅支持 Tk 模式（Web 模式下全部 10 个 wrapper 直接调用原函数）：
1. 一 turn 一轮高潮：NPC 在本 turn 内一旦高潮，本 turn 后续针对它的群交模板动作不再执行（wrapper #4）。
2. 摘要视图（v2，eraFL 式单行结算）：抑制 turn 内常规口上与属性变化面板，turn 结束时用一页摘要替代——
   每个 NPC 一行：锚点右对齐姓名 + 全角冒号 + 与状态栏同口径的 <寸止> 标记（#二，公式抄自
   character_info_head.py:237-257）+ 绝顶描述/寸止部位 token（hot_pink，"/"连接）；玩家点击后按发生顺序
   回放保留信息（成就、刻印/素质取得、疲劳退出、加入/发现群交等）。
3. 寸止过程信息语义（v2 用户新增，v5 用户裁定收窄批量解放的实时显示范围）：turn 内——寸止成功的全部过程
   信息（判定提示 wrapper #9、二段标题）一律隐去；普通高潮的过程信息照常隐去；但寸止断了导致的绝顶，从
   判定提示到二段标题/口上，原样实时显示，不吞不缓冲（例外：源自"结束群交等全体类结束指令"的批量解放，
   见下）——摘要页仍照常记入该角色行，按断因分三挂：<累>（太累退出H，little_dark_slate_blue，与状态栏
   <累>同色同源 character_info_head.py:148-153）/<寸止释放>（6014等主动释放，gold_enrod）/<寸止失败>
   （#9共同判定没扛住，gold_enrod），优先级 累>释放>失败（_edge_break_reason，#4/#5/#9写入，#2/#5/#10
   读取放行）。tired 判定（v5）与是否曾经历寸止解放事件解耦：#4 在结算链上一旦看到角色 behavior_id==
   GROUP_SEX_NPC_HP_0_END 就直接标记，不再依赖 #5 的 _is_edge_release_event——覆盖"太累退出但本turn没有
   任何寸止蓄积/解放事件"这类此前漏标的场景，摘要页凡 tired 必出"姓名:<累>"行，即便无任何绝顶/寸止记录
   （_summary_row_character_ids 相应纳入）。放行（edge_fail_passthrough，实时刷屏用）与记账
   （_edge_break_reason，摘要标记用）现已解耦：结束群交等全体类结束指令触发的批量解放（effect 529 逐成员
   release_orgasm_edge_now）只记账不放行，避免这类指令一次性刷出一大串实时结算；博士针对单人的定向解放
   （如6014）保持全程实时直显。
4. 博士针对性动作全显（v3 用户新增，v5 用户裁定收窄）：博士亲自下达且带明确目标的真实指令（非模板派发，
   且不属于"波及全体"的结束类/全员玩具类指令，见 #4 的 is_player_real 判据）在结算期间，直接引发的口上/
   属性变化面板/二段链原样实时全显（_player_real_instruction_active 窗口，#4 写入，#2/#3/#5/#9/#10 读取
   放行）；若该指令直接触发目标绝顶链，摘要页仍会重复记一行，视为预期行为。结束群交(GROUP_SEX_END)及同族
   （异常结束/太累退出等，_talk_whitelist 的结束族）、遥控全员玩具（REMOTE_ALL_*）不算定向命令，即便此刻
   target_character_id 恰好非零（结束类指令不主动清空该字段，handle_instruct.py:321-394
   chara_handle_instruct_common_settle 未传显式值时保留角色当前遗留值，不代表"这是针对该角色的定向指令"），
   不开全显窗口——用户原话："亲手下的指令导致的显示"只适用于针对一个角色的定向命令。
5. #2 黑名单翻转（v3 用户新增）：从"默认隐藏+id白名单放行"改为"默认显示+按上下文黑名单拦截"：模板派发窗口
   （_template_dispatch_active）与群交NPC背景H口上（character_id!=0 且 is_h）两类按上下文拦截，其余一律
   默认实时显示，白名单口上仍缓冲进摘要页后回放。判据顺序与理由见 modded_handle_talk_draw 自身注释。

turn 的定义：一次最外层 character_behavior.init_character_behavior() 调用，用嵌套深度计数判定归属
（该函数可重入，群交内疲劳结束 H 等路径会真实触发嵌套）。

设计决定（详见 mod/group_sex_summary/DESIGN.md）：
- 保留信息统一缓存，排在摘要页之后回放；缓存只存值不存对象（回放时新建绘制对象），因为绘制系统里
  line_feed 等模块级单例被大量复用，缓存 self 会踩别名 bug。
- 事件（event 系统）走 DrawEventTextPanel，它覆写了自己的 draw 方法，对本 mod 的定向缓冲天然免疫，
  不需要也不应该为它另开 wrapper——见下方 _ScopedBuffer 的类清单说明，请勿"顺手"把它加进去。
- 玩家自己的射精/忍耐面板、发现群交面板等交互面板（带按钮）原地放行，不缓冲，否则会卡死等待输入。
- 全部替换均为「薄 wrapper + call_original」，不复制任何原函数函数体；只在必须提前于 call_original
  做门判断的位置（#2 的行为 id 推导）实现极少量与原函数同口径的判断逻辑。

本 mod 的全部状态均为模块自身全局变量，不进 Character/cache，不进存档；每次最外层 turn 开头重置。

依赖链说明：mod 系统在 game.py 里于 Script.Design / Script.Settle / Script.UI 的绝大部分模块尚未被
主程序导入之前就完成 Mod 加载（game.py 先 init_mod_system() 再 import Script.Design.start_flow 等），
直接以本 mod 的 8 个替换目标为根挨个导入，容易撞上 settle_behavior -> handle_instruct -> update ->
character_behavior -> Script.Settle -> item_effect 的循环导入。这里沿用 local_orgasm_batch_talk_fix.py
已验证过的做法：先以 handle_npc_ai 为根，把整条依赖链按正确顺序完整导入一遍，之后 mod 管理器逐个导入
8 个目标模块时即可命中导入缓存。
"""

try:
    from Script.Design import handle_npc_ai as _preload_design_modules  # noqa: F401
except Exception:
    # 独立运行本文件做 _self_check() 自检时，游戏尚未走完 game.py 的配置加载流程（normal_config等
    # 未初始化），此处的预加载在这种脱离游戏运行时的场景下必然失败；自检本身不依赖任何真实Script.*
    # 模块，因此这里跳过即可。真实游戏运行时该导入必定成功（game.py先完成配置加载，之后才调用
    # init_mod_system()执行本脚本），不受此处防御性写法影响；跳过时打印一行提示，避免真出问题时完全静默。
    print("group_sex_summary: 预加载依赖链失败（独立自检环境下预期如此，游戏内运行若看到此提示需要排查）")


# ========================= 替换目标的模块路径常量 =========================
_CHARACTER_BEHAVIOR_MODULE = "Script.Design.character_behavior"
_TALK_MODULE = "Script.Design.talk"
_SETTLE_BEHAVIOR_MODULE = "Script.Design.settle_behavior"
_ORGASM_SETTLE_MODULE = "Script.Settle.orgasm_settle"
_ACHIEVEMENT_MODULE = "Script.UI.Panel.achievement_panel"
_SECOND_BEHAVIOR_MODULE = "Script.Design.second_behavior"
_HANDLE_TALENT_MODULE = "Script.Design.handle_talent"


# ========================= 摘要页文本用的现成映射（不硬编码英文部位） =========================
_ORGASM_PART_ORDER = ("s", "b", "c", "v", "a", "u", "w", "m", "f", "h")
""" 部位显示顺序，与 local_orgasm_batch_talk_fix.py 的 ORGASM_PART_ORDER 保持一致 """
_ORGASM_PART_NAME = {"s": "皮肤", "b": "胸部", "c": "阴蒂", "v": "阴道", "a": "肛肠", "u": "尿道", "w": "子宫", "m": "口喉", "f": "兽部", "h": "心理"}
""" 部位显示名，复用 local_orgasm_batch_talk_fix.py 中已核对过的现成映射，保持两个 mod 措辞一致 """
_ORGASM_DEGREE_TEXT = {0: "小绝顶", 1: "绝顶", 2: "强绝顶", 3: "超强绝顶"}
""" 档位序号（对应 orgasm_settle.orgasm_degree_order 的 rank）到显示文本的映射 """
_PLURAL_ORGASM_COUNT_NAME = ["双重", "三重", "四重", "五重", "六重", "七重", "八重", "九重", "十重"]
""" 多重绝顶数量前缀，照抄 talk.py:445 second_behavior_info_text 里的现成文本表（下标为 部位数-2） """


# ========================= 本 mod 自身的全局状态（不进存档，只在最外层 turn 开头重置） =========================
_depth = 0
""" init_character_behavior 的嵌套深度，只有最外层（值为1那一次）拥有 turn """
turn_active = False
""" 当前是否处于本 mod 接管的群交摘要 turn 内 """
player_behavior_id = ""
""" turn 开始时玩家自选的行为 id，功能1"玩家意志优先"判据（#4 用） """
orgasm_record = {}
""" dict[int, dict[str, int]]：角色id -> {部位: 本turn最高档位序号}，按部位取最高档去重 """
edge_record = {}
""" dict[int, dict[str, int]]：角色id -> {部位: 本turn寸止次数} """
replay_queue = []
""" list[tuple[type, str, str, int, str]]：保留信息缓冲，每项为 (draw类, text, style, width, tooltip)，只存值不存对象 """
edge_fail_passthrough = set()
""" set[int]：本turn内寸止断了过、且需要被"实时刷屏"的角色id集合（#4/#5/#9写入）——命中的角色，其随之而来的
绝顶二段标题/口上（#2）与性爱发电提示（#5）原样实时放行，不吞不缓冲，语义见模块docstring第3条。v5起与
_edge_break_reason解耦：并非所有写入_edge_break_reason的角色都会并入本集合——结束群交等全体类结束指令
触发的批量解放（见#5）只记账进_edge_break_reason，不并入本集合，避免那类指令一次性刷出一大串实时结算；
定向单人解放（如6014）与#9判定失败、#4太累退出仍照常并入（_mark_edge_break_reason的passthrough参数控制） """
_edge_break_reason = {}
""" dict[int, str]：角色id -> "tired"|"release"|"fail"，摘要页据此显示断因标记，优先级
累(tired) > 主动释放(release) > 判定失败(fail)，只升不降（见_mark_edge_break_reason）。三者摘要页标记/颜色
不同：tired是"太累被迫中断"，release是"主动指令/6014解放/批量结束解放"，fail是"#9共同寸止判定没扛住"——
归因不同，用户要求分开标注。v5起其key集合可能比edge_fail_passthrough更大（批量解放只记账不放行，见其定义
处docstring），_split_edge_parts/_edge_status_tag（摘要标记/token拆分）改按本dict的key判断，
edge_fail_passthrough专用于"是否实时放行"这一件事 """
edge_near_limit = set()
""" set[int]：本turn内寸止判定成功但余量<=2（状态栏带感叹号那两档）的角色id集合（#9写入）——命中的角色，
其寸止族二段标题/口上（#2）与批次合并寸止标题那行黄字（#10）原样实时放行，让"马上忍不住了"当场可见。
与edge_fail_passthrough分开两个集合：寸止成功不代表没有绝顶链，混用会把该角色本turn的绝顶口上一并放出来 """
_second_effect_character = None
""" int|None：当前正处在#10 modded_check_second_effect窗口内的角色id，无则None。
#2据此把"寸止链整体放行"限定在这一次二段结算的范围内，窗口外仍按白名单办（见_should_pass_through_talk） """
_TALK_WHITELIST_CACHE = None
""" #2 白名单集合的懒加载缓存，避免在模块顶层引用尚未导入的 constant 常量 """
_PRISTINE_DRAW_METHODS = {}
""" dict[type, Callable]：NormalDraw/WaitDraw/LineFeedWaitDraw 三个类从未被本 mod patch 过的原始 draw 方法，供 #1 的 finally 兜底恢复 """
_player_real_instruction_active = False
""" bool：当前是否正处于博士亲自指定目标的那条真实指令（非模板派发）结算窗口内（#4写入/试图恢复），
功能2判据——命中时#2/#5/#9/#10一律原样实时显示，不吞不缓冲，让博士亲自下达的指令所直接引发的一切
（口上+属性变化面板+二段链）当场可见；#3据此决定是否把面板真的返回给上游而不是吞掉 """
_player_real_instruction_seen = False
""" bool：#3每次调用handle_settle_behavior前清零、call_original期间若#4命中过_player_real_instruction_active
则置True的一次性锁存——#3读取它决定这次返回的面板是真的交给上游画，还是照常吞掉。之所以需要这个锁存而不能
直接判断character_id==0：group_sex_mode下character_id==0这一次call_original内部会连续处理"玩家真实指令"
与"整段模板派发循环"两部分（settle_behavior.py:51-68），必须用#4内部实际命中的窗口态来标记，不能按
character_id笼统放行，否则模板派发部分也会被误放行 """
_template_dispatch_active = False
""" bool：当前是否正处于群交模板派发（character_id==0、behavior_id!=player_behavior_id那个循环，见
settle_behavior.py:51-68）窗口内（#4写入/恢复），功能3黑名单案例①判据——#2据此拦掉模板派发过程中的
口上与标题，不受新default-show影响 """
_MASS_END_FAMILY_CACHE = None
""" set[str]|None：懒加载缓存，"波及全体的结束类行为id"集合（见_mass_end_behavior_family） """
_MASS_TOY_FAMILY_CACHE = None
""" set[str]|None：懒加载缓存，"遥控全员玩具"行为id集合（见_mass_toy_behavior_family） """


def _cache():
    """参数：无；返回：Cache对象；用途：延迟获取当前游戏缓存，避免持有可能被整体替换的旧引用（同 local_orgasm_batch_talk_fix.py 的既定写法）。"""
    from Script.Core import cache_control

    return cache_control.cache


def _t(text: str) -> str:
    """参数：text(str)为待翻译文本；返回：str为翻译后文本；用途：延迟取用翻译api，避免持有加载期注入的全局引用。"""
    from Script.Core import get_text

    return get_text._(text)


def _is_web_draw() -> bool:
    """参数：无；返回：bool；用途：判断当前是否为Web绘制模式；本mod仅支持Tk模式，Web模式下全部wrapper直通原函数。"""
    from Script.Config import normal_config

    return bool(getattr(normal_config.config_normal, "web_draw", False))


def _is_active() -> bool:
    """参数：无；返回：bool；用途：判断当前是否处于本mod接管的群交摘要turn内且为Tk模式，决定#2白名单分支/#3/#6/#7/#8是否接管。"""
    return turn_active and not _is_web_draw()


def _reset_turn_state():
    """参数：无；返回：无；用途：最外层turn开始时重置本mod的全部自身状态，不跨turn保留，存档兼容性零影响。"""
    global orgasm_record, edge_record, replay_queue, player_behavior_id, edge_fail_passthrough, edge_near_limit
    global _edge_break_reason, _player_real_instruction_active, _player_real_instruction_seen, _template_dispatch_active
    orgasm_record = {}
    edge_record = {}
    replay_queue = []
    player_behavior_id = ""
    edge_fail_passthrough = set()
    edge_near_limit = set()
    _edge_break_reason = {}
    _player_real_instruction_active = False
    _player_real_instruction_seen = False
    _template_dispatch_active = False


def _mark_edge_break_reason(character_id: int, reason: str, passthrough: bool = True) -> None:
    """参数：character_id(int)角色id；reason(str)寸止断了的原因，取值"tired"/"release"/"fail"；
    passthrough(bool，默认True)是否同时并入edge_fail_passthrough触发实时刷屏；返回：无；
    用途：v5起passthrough与reason解耦（用户裁定1b）：结束群交等全体类结束指令触发的批量解放调用方传
    False——只记账供摘要页显示断因，不触发实时刷屏；其余调用点（#9判定失败、#4太累退出、#5定向单人解放）
    保持默认True，与decoupling之前的行为一致。按优先级 累(tired) > 主动释放(release) > 判定失败(fail)
    写入_edge_break_reason，只升不降——同一角色本turn若已被更高优先级原因标记过，不会被后来的低优先级
    原因覆盖（passthrough不参与优先级比较，每次调用各自独立生效，只增不减）。"""
    if passthrough:
        edge_fail_passthrough.add(character_id)
    priority = {"tired": 3, "release": 2, "fail": 1}
    if priority.get(reason, 0) >= priority.get(_edge_break_reason.get(character_id, ""), 0):
        _edge_break_reason[character_id] = reason


def _mass_end_behavior_family() -> set:
    """参数：无；返回：set[str]；用途：懒加载缓存"波及全体的结束类行为id"集合，供#4排除is_player_real误判
    （用户裁定1a：结束群交及同族异常结束不算"针对一个角色的定向命令"，不应开全显窗口）与#5判定本次批量解放
    是否源自这类结束指令（用户裁定1b：源自结束指令的批量解放不实时刷屏）。取Behavior.GROUP_SEX_END、
    Behavior.GROUP_SEX_NPC_HP_0_END与constant.special_end_H_list的并集（Behavior.GROUP_SEX_PL_HP_0_END
    已在special_end_H_list内，见Script/Core/constant/__init__.py:293）——即_talk_whitelist()（见其定义处）
    去掉JOIN_GROUP_SEX/DISCOVER_OTHER_SEX_AND_JOIN/BE_INVITED_JOIN_GROUP_SEX等"加入"族后的结束子集：
    用户原话只提"结束群交及同族"，"加入"类不是结束语义，不应混入。"""
    global _MASS_END_FAMILY_CACHE
    if _MASS_END_FAMILY_CACHE is None:
        import Script.Core.constant as constant
        from Script.Core.constant import Behavior

        _MASS_END_FAMILY_CACHE = {Behavior.GROUP_SEX_END, Behavior.GROUP_SEX_NPC_HP_0_END} | set(constant.special_end_H_list)
    return _MASS_END_FAMILY_CACHE


def _mass_toy_behavior_family() -> set:
    """参数：无；返回：set[str]；用途：懒加载缓存"遥控全员玩具"行为id集合，供#4排除is_player_real误判
    （用户裁定1a："全员玩具"一并核对）。REMOTE_ALL_TURN_OFF_SEX_TOY/REMOTE_ALL_SET_SEX_TOY_WEAK/MEDIUM/STRONG
    （Script/Core/constant/Behavior.py:720-738）经Instruct_System/handle_instruct.py核实均经
    chara_handle_instruct_common_settle(behavior_id, judge="严重骚扰")调用（未显式传target_character_id），
    与GROUP_SEX_END同样存在"继承玩家当前遗留target_character_id"从而误判定向指令的结构性风险——群交面板
    count_group_sex_instruct_list()（group_sex_panel.py:98-134）确认这4个id不在per-member模板派发列表内，
    是真正的"影响全体成员"指令。"全员寸止"类指令确实存在——已启用的group_sex_extension mod有三条全员自定义
    指令（group_sex_extension.py:227全员寸止/:245全员戴玩具/:266全员催眠增强），但其handler直接改NPC数据后
    绘制结果返回，从不调chara_handle_instruct_common_settle、不设behavior.behavior_id、不触发game_update_flow，
    #4永远看不到它们，没有behavior_id可补进本族——不补不是因为指令不存在，而是它们不经过本判据所在的挂点。"""
    global _MASS_TOY_FAMILY_CACHE
    if _MASS_TOY_FAMILY_CACHE is None:
        from Script.Core.constant import Behavior

        _MASS_TOY_FAMILY_CACHE = {
            Behavior.REMOTE_ALL_TURN_OFF_SEX_TOY,
            Behavior.REMOTE_ALL_SET_SEX_TOY_WEAK,
            Behavior.REMOTE_ALL_SET_SEX_TOY_MEDIUM,
            Behavior.REMOTE_ALL_SET_SEX_TOY_STRONG,
        }
    return _MASS_TOY_FAMILY_CACHE


def _is_mass_instruction(behavior_id) -> bool:
    """参数：behavior_id(str)行为id；返回：bool，True表示该行为id属于"波及全体"的指令（结束族或全员玩具族）。
    用途：#4 is_player_real判据的排除条件（用户裁定1a）：即便target_character_id此刻恰好非零，只要
    behavior_id落在这两族内，就不算"针对一个角色的定向命令"，不开全显窗口。"""
    return behavior_id in _mass_end_behavior_family() or behavior_id in _mass_toy_behavior_family()


def _is_mass_end_release_source(player_current_behavior_id) -> bool:
    """参数：player_current_behavior_id(str)调用当下（非本turn开头快照）玩家(character_id==0)的实时
    behavior_id；返回：bool，True表示本次release_orgasm_edge_now批量解放源自"结束群交等全体类结束指令"
    （effect 529，见#5用途文档），不应实时刷屏。用途：#5判据抽出的纯函数版本（同_is_tired_exit的抽取动机，
    便于不依赖游戏运行环境的自检覆盖），单独一行判据即"player_current_behavior_id是否落在
    _mass_end_behavior_family()内"——为何必须传实时值而非turn开头快照，见#5函数体docstring。"""
    return player_current_behavior_id in _mass_end_behavior_family()


# ========================= 定向缓冲（scoped tee） =========================
# 只 patch 三个类：NormalDraw、WaitDraw、LineFeedWaitDraw——#2白名单分支/#6/#7/#8 四个调用窗口内实际只会
# 产生这三种绘制对象（talk 经 rich_text 产出前两者+LineFeedWaitDraw，#6/#7/#8 只用 WaitDraw）。
# 事件绘制走 DrawEventTextPanel，它覆写了自己的 draw 方法，不在这三个类之内，天然对本机制免疫——这是有意
# 为之的设计（事件要原地显示、原地交互），不要把它加进下面的补丁类列表。
def _draw_classes():
    """参数：无；返回：tuple[type,...]；用途：懒加载并返回本mod定向缓冲要接管的三个绘制类，首次访问时顺带记录三者当时未被patch的原始draw方法，供异常兜底恢复使用。"""
    from Script.UI.Moudle import draw

    classes = (draw.NormalDraw, draw.WaitDraw, draw.LineFeedWaitDraw)
    for target_class in classes:
        _PRISTINE_DRAW_METHODS.setdefault(target_class, target_class.draw)
    return classes


def _make_buffered_draw(target_list: list):
    """参数：target_list(list)为本次缓冲要写入的目标列表；返回：Callable，绑定了该列表的draw()替身函数；用途：为_ScopedBuffer生成
    "只记录不绘制"的替身闭包——v2起target_list可以是全局replay_queue，也可以是调用方自备的本地列表（wrapper #9/#5用于
    "先捕获、函数返回后按真实结果决定丢弃还是原样补绘"，不新开一套独立机制，复用同一个定向缓冲）。"""

    def _buffered_draw(self):
        target_list.append((type(self), self.text, self.style, self.width, self.tooltip))

    return _buffered_draw


def _draw_live(item_tuple):
    """参数：item_tuple(tuple[type,str,str,int,str])为(绘制类,文本,样式,宽度,悬浮提示)五元组；返回：无；用途：绕过当前任何
    生效中的定向缓冲，直接用_draw_classes()首次记录的原始draw方法真实渲染——供wrapper #9/#5"先捕获再按结果决定"的放行分支
    使用：#9/#5决定放行的那一刻可能仍处于外层缓冲窗口内（#9嵌套在#5的本地捕获窗口里），若用普通.draw()会被外层缓冲二次
    吞掉，因此改走原始方法直接绘制，与是否有外层窗口在生效无关。"""
    draw_class, text, style, width, tooltip = item_tuple
    _draw_classes()  # 确保_PRISTINE_DRAW_METHODS已就绪（懒加载，实际运行时早被#1等触发过）
    item = draw_class()
    item.text, item.style, item.width, item.tooltip = text, style, width, tooltip
    _PRISTINE_DRAW_METHODS[draw_class](item)


class _ScopedBuffer:
    """
    定向缓冲上下文管理器。只在 #2 白名单/放行分支、#5、#6、#7、#8、#9 的调用窗口内生效，绝不全局常开——
    全局拦截会缓冲掉交互面板的按钮、代码等输入，导致卡死。

    嵌套安全：__enter__ 保存的是进入那一刻各目标类当前的 draw 方法（可能已经是外层窗口打的补丁），
    __exit__ 用 finally 精确恢复为进入前的值，因此窗口可以安全嵌套（例如缓冲中的 mark_effect 内部
    又触发了白名单口上，或#5的本地捕获窗口内嵌套#9的本地捕获窗口）。#1 的 finally 会在turn结束时再
    整体兜底恢复一次，防止turn中途异常把UI留在吞噬状态。

    target_list：默认None时写入全局replay_queue（回放语义，#2/#6/#7/#8用法不变）；显式传入一个列表时
    写入该列表而不碰replay_queue（捕获语义，#5/#9用——函数返回后调用方自行决定这份捕获内容是丢弃还是
    经_draw_live原样补绘）。
    """

    def __init__(self, target_classes=None, target_list=None):
        """参数：target_classes(可选的类序列，默认懒加载真实的三个绘制类，便于自检时传入假类)；
        target_list(可选list，默认写入全局replay_queue)；返回：无；用途：记录本次要缓冲的目标类集合与写入目标。"""
        self._target_classes = list(target_classes) if target_classes is not None else list(_draw_classes())
        self._target_list = target_list if target_list is not None else replay_queue
        self._buffered_draw = _make_buffered_draw(self._target_list)
        self._saved_methods = {}

    def __enter__(self):
        """参数：无；返回：self；用途：保存各目标类当前的draw方法，并统一替换为本窗口的缓冲写入函数。"""
        for target_class in self._target_classes:
            self._saved_methods[target_class] = target_class.draw
            target_class.draw = self._buffered_draw
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """参数：异常信息（未使用）；返回：False（不吞异常）；用途：无论是否发生异常都恢复为进入前保存的draw方法。"""
        for target_class, original_draw in self._saved_methods.items():
            target_class.draw = original_draw
        return False


def _force_restore_draw_patches():
    """参数：无；返回：无；用途：#1最外层turn结束时的整体兜底——把三个绘制类的draw方法强制恢复为本mod从未patch过时的原始版本，防止turn中途异常导致某个类停留在缓冲状态。"""
    for target_class, original_draw in _PRISTINE_DRAW_METHODS.items():
        target_class.draw = original_draw


class _PristineWindow:
    """
    临时强制恢复三个绘制类为原始（未被本mod patch过）draw方法的上下文管理器，退出时精确恢复为进入前的值——
    与_force_restore_draw_patches()不同：那是turn结束时的一次性永久恢复，这里是可安全嵌套的临时窗口（进入
    前若已有外层窗口打了补丁，退出后必须原样交还外层的补丁，而不是留在pristine状态）。

    用途：#2放行分支的call_original一旦被套进#10（modded_check_second_effect）的本地捕获窗口内，若不做
    任何处理，其绘制会被#10的缓冲闭包捕获，推迟到#10返回后才统一补绘，不是真正"从头到尾原样实时显示"；
    包一层本窗口可以让它无视任意外层缓冲，真正立即落地。
    """

    def __init__(self, target_classes=None):
        """参数：target_classes(可选类序列，默认三个真实绘制类)；返回：无；用途：记录本次要临时转回pristine的目标类集合。"""
        self._target_classes = list(target_classes) if target_classes is not None else list(_draw_classes())
        self._saved_methods = {}

    def __enter__(self):
        """参数：无；返回：self；用途：保存各目标类当前(可能是某个外层窗口打的补丁)的draw方法，强制替换为pristine版本。"""
        for target_class in self._target_classes:
            self._saved_methods[target_class] = target_class.draw
            target_class.draw = _PRISTINE_DRAW_METHODS[target_class]
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """参数：异常信息（未使用）；返回：False（不吞异常）；用途：恢复为进入前保存的draw方法（可能仍是外层窗口的补丁，而非最初的pristine）。"""
        for target_class, original_draw in self._saved_methods.items():
            target_class.draw = original_draw
        return False


# ========================= #5 高潮/寸止记录合并（可独立自检的纯逻辑） =========================
def _merge_second_behavior_into_records(character_id: int, second_behavior_dict: dict, part_degree_parser=None):
    """
    参数：character_id(int)为角色id；second_behavior_dict(dict[str,int])为该角色当前的二段行为字典（id->是否触发）；
          part_degree_parser(Callable[[str],tuple]|None)为部位与档位解析函数，默认懒加载 orgasm_settle.get_orgasm_part_and_degree
          （允许调用方注入替身函数，便于不依赖真实游戏环境的自检）。
    返回：无。
    用途：扫描本次结算中非零的 {部位}_orgasm_{程度} / {部位}_orgasm_edge 二段行为id，按部位取最高档位并入
          orgasm_record，寸止次数按部位累加进 edge_record。
    """
    if part_degree_parser is None:
        from Script.Settle import orgasm_settle

        part_degree_parser = orgasm_settle.get_orgasm_part_and_degree
    for second_behavior_id, value in second_behavior_dict.items():
        if not value:
            continue
        if second_behavior_id.endswith("_orgasm_edge"):
            part = second_behavior_id[: -len("_orgasm_edge")]
            part_edge_count = edge_record.setdefault(character_id, {})
            part_edge_count[part] = part_edge_count.get(part, 0) + 1
            continue
        part, degree_rank = part_degree_parser(second_behavior_id)
        if part is None:
            continue
        part_degree = orgasm_record.setdefault(character_id, {})
        if part not in part_degree or degree_rank > part_degree[part]:
            part_degree[part] = degree_rank


# ========================= 摘要页版式（v2） =========================
def _split_edge_parts(character_id: int) -> tuple:
    """
    参数：character_id(int)角色id。
    返回：tuple[dict,dict]为({已解放部位:寸止次数}, {仍憋着部位:寸止次数})。
    用途：把本turn的寸止记录按"这个部位后来有没有真的高潮"拆成两半，供摘要页消除"同一部位同时出现在绝顶侧
          与寸止侧"的自相矛盾显示。
          为什么会同时出现：orgasm_record/edge_record 都是turn级只增不减的累计账本。寸止判定成功时上游置
          {部位}_orgasm_edge（进edge_record）；之后这股憋住的量被解放时——无论是寸止判定失败
          （orgasm_settle.py:180-190 失败分支把已累积的orgasm_edge_count并入un_count_orgasm_dict），还是
          主动解放（orgasm_settle.py:333-347 release_orgasm_edge_now 把orgasm_edge_count整个当作
          un_count_orgasm_dict重新结算）——同一部位都会再走一遍普通的{部位}_orgasm_{程度}路径（进
          orgasm_record）。于是同一部位先后进了两个账本，并列显示就成了"又高潮又寸止"。
          语义裁定（用户拍板）：只要该部位本turn真的高潮了，就归到高潮侧，不再重复列进寸止侧；这种"憋住后
          又释放"的经历改用专门的断因标记表达（<累>/<寸止释放>/<寸止失败>，见_edge_status_tag），避免信息丢失。
    """
    part_edge_count = edge_record.get(character_id, {})
    # 寸止判定失败/解放过（不论是否实时放行）的角色：这一整轮憋住的量全部兑现掉了，无一例外算已解放。
    # 不能只靠"该部位也进了orgasm_record"来认——失败时上游根本不置{部位}_orgasm_edge
    # (orgasm_settle.py:179-190失败分支直接落普通绝顶路径)，edge_record里可能一条记录都没有，
    # 于是整行连标记都不显示，就是QA截图里"绝顶失败没被判成<寸止释放>"那几行。
    # v5起改判_edge_break_reason而非edge_fail_passthrough：二者已解耦（批量解放只记账不放行，见
    # edge_fail_passthrough定义处docstring），但"这部位是否兑现成绝顶"是记账语义，与是否实时放行无关。
    if character_id in _edge_break_reason:
        return part_edge_count, {}
    orgasm_part_map = orgasm_record.get(character_id, {})
    released_parts = {part: count for part, count in part_edge_count.items() if part in orgasm_part_map}
    holding_parts = {part: count for part, count in part_edge_count.items() if part not in orgasm_part_map}
    return released_parts, holding_parts


def _edge_margin(skill_ability_lv: int, orgasm_edge_count: dict) -> int:
    """
    参数：skill_ability_lv(int)玩家寸止技巧等级(ability[30])；orgasm_edge_count(dict[str|int,int])部位->寸止次数。
    返回：int为寸止余量margin，越小越憋不住，<0表示已超过能控制住的极限。
    用途：上游寸止余量公式的唯一副本，供两处共用，避免各写一份日后算法漂移：
          ①摘要页<寸止>三档标记(_edge_status_tag，口径源自character_info_head.py:239-241)；
          ②#9判断"是否已接近/超过极限"从而放行提示(口径源自orgasm_settle.py:412 over_count)。
          两处上游原本就是同一个式子：玩家寸止技巧*3 减去各部位寸止次数的平方和。
    """
    return skill_ability_lv * 3 - sum(value * value for value in orgasm_edge_count.values())


def _edge_break_tag_and_style(character_id: int) -> tuple:
    """参数：character_id(int)角色id（须已在_edge_break_reason中，调用方负责判断）；返回：tuple[str,str]为
    (标记文本,样式名)；用途：按_edge_break_reason查该角色的断因，映射为摘要页三选一标记，优先级
    累(tired) > 主动释放(release) > 判定失败(fail)（写入侧已在_mark_edge_break_reason保证只升不降，这里只需
    直接查表）。未查到条目（理论上不该发生，本函数的调用方总是先确认character_id在_edge_break_reason中才调用，
    此处兜底按release处理，不让显示直接报错）：tired→little_dark_slate_blue样式" <累>"；release→gold_enrod
    样式" <寸止释放>"；fail→gold_enrod样式" <寸止失败>"。release与fail颜色相同（都是gold_enrod，用户裁定
    "释放/失败保持原金色"）；tired（v5用户裁定2c）改用little_dark_slate_blue，与状态栏"体力耗尽"标记同色
    同源——Script/UI/Panel/character_info_head.py:148-153状态栏自身的<累>标记（handle_self_tired命中时）
    正是这个样式（#5550aa，FontConfig.csv cid 33，备注"比深岩暗蓝灰色亮一点（睡眠）"），用户原话"和状态栏
    保持一致"，故不再沿用之前误用的hp_point（#e15a5a，"体力的颜色"，与状态栏口径不符）。"""
    reason = _edge_break_reason.get(character_id, "release")
    if reason == "tired":
        return " <累>", "little_dark_slate_blue"
    if reason == "fail":
        return " <寸止失败>", "gold_enrod"
    return " <寸止释放>", "gold_enrod"


def _edge_status_tag(character_id: int, skill_ability_lv=None, orgasm_edge_count=None) -> tuple:
    """
    参数：character_id(int)角色id；skill_ability_lv(int|None)/orgasm_edge_count(dict[str,int]|None)为可选注入值，
          默认从cache实时读取（分别为cache.character_data[0].ability[30]玩家寸止技巧、该角色h_state.orgasm_edge_count），
          便于自检时不依赖真实游戏环境直接传入假值。
    返回：tuple[str,str]为(标记文本,样式名)；本turn该角色无寸止记录(edge_record中无该角色条目)时返回("", "")。
    用途：本turn寸止过的角色的metadata标记，分两种情况：
          ①有部位"憋住后又解放"（_split_edge_parts的released非空，即该部位既进了edge_record又进了
            orgasm_record）→ 按_edge_break_tag_and_style返回三选一断因标记（<累>/<寸止释放>/<寸止失败>）。
            这类角色的寸止已经兑现成绝顶，再按憋着的三档报警度显示会误导（而且解放时上游会清零
            h_state.orgasm_edge_count，实时margin恒为最宽松档，永远显示最轻的<寸止>，与"其实是没忍住爆了"
            的事实正好相反）。
          ②否则（纯粹还憋着）→ 与Script/UI/Panel/character_info_head.py:237-257的<寸止>状态栏标记公式与
            三档样式完全对齐（该处是本口径的权威来源，上游若调整公式/阈值/样式需同步本函数）：
            margin = 玩家寸止技巧(ability[30])*3 减去该角色各部位本次寸止次数的平方和；margin>=3为
            hot_pink" <寸止>"，0<=margin<3为red" <寸止!>"，margin<0为levelex" <寸止!!>"。档位按summary绘制
            那一刻的实时游戏状态计算（非本turn寸止累计次数），与状态栏语义一致。
    """
    # 寸止断了的角色优先判定：这一条不看edge_record有没有条目（失败路径压根不写edge_record，见_split_edge_parts）。
    # v5起改判_edge_break_reason而非edge_fail_passthrough——二者已解耦，记账（本函数用于摘要标记）与是否
    # 实时刷屏是两件事，见edge_fail_passthrough定义处docstring。
    if character_id in _edge_break_reason:
        return _edge_break_tag_and_style(character_id)
    if not edge_record.get(character_id):
        return "", ""
    released_parts, _holding_parts = _split_edge_parts(character_id)
    if released_parts:
        return _edge_break_tag_and_style(character_id)
    if skill_ability_lv is None:
        skill_ability_lv = _cache().character_data[0].ability[30]
    if orgasm_edge_count is None:
        orgasm_edge_count = _cache().character_data[character_id].h_state.orgasm_edge_count
    margin = _edge_margin(skill_ability_lv, orgasm_edge_count)
    if margin >= 3:
        return " <寸止>", "hot_pink"
    if margin >= 0:
        return " <寸止!>", "red"
    return " <寸止!!>", "levelex"


def _build_edge_token(part_count_map: dict) -> str:
    """
    参数：part_count_map(dict[str,int])为本turn该角色{部位:寸止次数}；返回：str为摘要页寸止token文本，无记录
          时返回空串。
    用途：按次数分组（分组写法与_build_orgasm_desc一致），组内部位用"、"连接，组末缀"绝顶寸止"，次数>1时加
          "×N"；不同次数的组之间也用"、"连接。例："阴蒂、心理绝顶寸止"（均1次）、"阴道绝顶寸止×2"（单部位2次）。
    """
    if not part_count_map:
        return ""
    groups = {}
    for part, count in part_count_map.items():
        groups.setdefault(count, []).append(part)
    group_text_list = []
    for count in sorted(groups, reverse=True):
        known_parts = [part for part in _ORGASM_PART_ORDER if part in groups[count]]
        unknown_parts = [part for part in groups[count] if part not in _ORGASM_PART_ORDER]
        part_names = "、".join(_ORGASM_PART_NAME.get(part, part) for part in known_parts + unknown_parts)
        suffix = "绝顶寸止" if count <= 1 else f"绝顶寸止×{count}"
        group_text_list.append(part_names + suffix)
    return "、".join(group_text_list)


def _build_orgasm_desc(part_degree_map: dict) -> str:
    """
    参数：part_degree_map(dict[str,int])为本turn该角色{部位:最高档位序号}；返回：str为摘要页用的绝顶描述文本，无记录时返回空串；
    用途：按档位从高到低分组，组内部位以"・"连接、组间以"、"连接，并加上"N重绝顶:"（单部位则"绝顶:"）前缀，
          "N重绝顶"口径与上游plural_orgasm一致（部位数=len(part_degree_map)）。不在_ORGASM_PART_ORDER排序表内的
          部位（如玩家专用的"p"）追加到本组末尾一并显示，而不是从描述里丢掉——否则会出现"N重绝顶"数字对不上
          实际列出的部位数。
    """
    if not part_degree_map:
        return ""
    groups = {}
    for part, degree_rank in part_degree_map.items():
        groups.setdefault(degree_rank, []).append(part)
    group_text_list = []
    for degree_rank in sorted(groups, reverse=True):
        known_parts = [part for part in _ORGASM_PART_ORDER if part in groups[degree_rank]]
        unknown_parts = [part for part in groups[degree_rank] if part not in _ORGASM_PART_ORDER]
        ordered_parts = known_parts + unknown_parts
        part_names = "・".join(_ORGASM_PART_NAME.get(part, part) for part in ordered_parts)
        group_text_list.append(part_names + _ORGASM_DEGREE_TEXT.get(degree_rank, ""))
    part_count = len(part_degree_map)
    if part_count == 1:
        header = "绝顶："
    else:
        header = _PLURAL_ORGASM_COUNT_NAME[min(part_count, len(_PLURAL_ORGASM_COUNT_NAME) + 1) - 2] + "绝顶："
    return header + "、".join(group_text_list)


def _summary_row_character_ids() -> list:
    """参数：无；返回：list[int]（已排序）；用途：本turn需要出现在摘要页的角色id。QA缺陷2根因修复：纳入
    条件从"在群交模板中或有记录"改为"本turn确有绝顶或寸止记录"——旧逻辑额外并入
    group_sex_panel.count_group_sex_character_list()（模板全体成员），本turn无人绝顶/寸止时仍会为每个
    模板成员画一行只有姓名/冒号的空行；orgasm_record/edge_record只在_merge_second_behavior_into_records
    确有非零记录时才setdefault写入，故改为只取这两个dict的key后，纳入的行必定带有描述/token内容，不需要
    再额外判断行内容是否为空。v5新增第三个来源：_edge_break_reason中reason=="tired"的角色id——用户裁定2b
    "凡tired必出一行"，覆盖"太累退出但本turn压根没有任何绝顶/寸止记录"这种此前会被整行跳过的场景（release/
    fail两种reason不需要单独并入：二者只会在#5/#9实际处理过orgasm/edge记录时才被标记，必然已在
    orgasm_record/edge_record中占有条目，不存在这个缺口，见docstring模块第3条）。这类零记录的tired行仅显示
    "姓名:<累>"：_edge_status_tag/_edge_break_tag_and_style对无orgasm_record/edge_record条目的角色同样能
    正常返回<累>标记（判据是_edge_break_reason而非那两个记录dict），_build_summary_rows的
    orgasm_desc/edge_token留空时"if orgasm_desc or edge_token"分支天然跳过，不需要额外改动那部分。
    玩家(id 0)永不列入。抽成独立纯函数，便于_self_check不依赖真实cache验证。"""
    tired_ids = {character_id for character_id, reason in _edge_break_reason.items() if reason == "tired"}
    return sorted((set(orgasm_record) | set(edge_record) | tired_ids) - {0})


def _summary_name_style(character_data) -> str:
    """参数：character_data(具备.name/.text_color属性的角色对象)；返回：str为摘要页姓名段应使用的style。
    用途：QA缺陷1根因修复——text_color是角色自定义颜色的原始取值（如"#ff88aa"），不是已注册的Tk样式
    标签名；本仓全部同类用法（talk.py:315-317、settle_behavior.py:169-171/255-256、
    common_select_NPC.py:322-323、all_npc_position_panel.py:284-285）在text_color非空时都把.style/
    富文本标签设成character_data.name本身，因为character_config.py:63-67在CSV加载阶段已为每个有
    TextColor的角色同步注册了以角色名为key的game_config.config_font_data条目——text_color与该注册
    是同一份CSV数据同步产生的，无需再校验该名字tag是否存在。此前误把text_color的值直接当style传给
    RightDraw，未注册的标签名导致该姓名整段（含右对齐补的空格）静默不绘制，冒号因此贴到锚点最左侧。"""
    return character_data.name if character_data.text_color else "standard"


def _build_summary_rows() -> list:
    """
    参数：无；返回：list[list[绘制对象]]；用途：汇总本turn需要在摘要页展示的每个NPC一行的绘制片段序列
          （eraFL式：锚点右对齐姓名+全角冒号+状态栏口径寸止标记+高潮描述/寸止token），角色范围与姓名style
          分别见_summary_row_character_ids/_summary_name_style（QA两处缺陷的修复点）。只列NPC，玩家
          (id 0)不列入。每行末尾自带换行片段，调用方按序对每个片段调用.draw()即可。
    """
    from Script.UI.Moudle import draw
    from Script.Config import normal_config

    cache_obj = _cache()
    anchor_width = normal_config.config_normal.text_width // 3
    rows = []
    for character_id in _summary_row_character_ids():
        character_data = cache_obj.character_data[character_id]
        segments = []

        name_draw = draw.RightDraw()
        name_draw.width = anchor_width
        name_draw.style = _summary_name_style(character_data)
        name_draw.text = character_data.name
        segments.append(name_draw)

        colon_draw = draw.NormalDraw()
        colon_draw.style = "standard"
        colon_draw.text = "："
        segments.append(colon_draw)

        tag_text, tag_style = _edge_status_tag(character_id)
        if tag_text:
            tag_draw = draw.NormalDraw()
            tag_draw.style = tag_style
            tag_draw.text = tag_text
            segments.append(tag_draw)

        orgasm_desc = _build_orgasm_desc(orgasm_record.get(character_id, {}))
        # 寸止token只列"仍憋着"的部位：已解放的部位本turn真的高潮了，归绝顶侧显示，不再重复列进寸止侧，
        # 那段经历改由_edge_status_tag的<寸止释放>标记表达（见_split_edge_parts的说明）
        _released_parts, holding_parts = _split_edge_parts(character_id)
        edge_token = _build_edge_token(holding_parts)
        if orgasm_desc or edge_token:
            space_draw = draw.NormalDraw()
            space_draw.style = "standard"
            space_draw.text = " "
            segments.append(space_draw)
            if orgasm_desc:
                desc_draw = draw.NormalDraw()
                desc_draw.style = "standard"
                desc_draw.text = orgasm_desc
                segments.append(desc_draw)
            if orgasm_desc and edge_token:
                sep_draw = draw.NormalDraw()
                sep_draw.style = "standard"
                sep_draw.text = "/"
                segments.append(sep_draw)
            if edge_token:
                edge_draw = draw.NormalDraw()
                edge_draw.style = "hot_pink"
                edge_draw.text = edge_token
                segments.append(edge_draw)

        newline_draw = draw.NormalDraw()
        newline_draw.style = "standard"
        newline_draw.text = "\n"
        segments.append(newline_draw)
        rows.append(segments)
    return rows


def _draw_summary_page():
    """参数：无；返回：无；用途：结算完毕后绘制一页群交摘要（v2版式）——按角色列出右对齐姓名/寸止标记/高潮与
    寸止描述，末尾等待玩家点击继续；页眉页脚用现成的draw.LineDraw横线与draw.CenterDraw居中标题，不新增绘制类。
    行数为空（本turn所有参与者都无绝顶/寸止记录，QA缺陷2修复后rows的纳入条件本身就是"有记录"，不会再出现
    "模板成员在但本turn无事发生"的空行）时不画页眉页脚也不WaitDraw，避免弹出空框强制点击——replay_queue的
    回放不受影响，由调用方单独执行。
    S3：换行一律用独立的NormalDraw(text="\\n")输出，不拼进CenterDraw.text——CenterDraw.draw()把text整体
    （含换行符）一起做居中对齐，混入换行符会把可见标题挤偏半格，且对齐补的尾部空格会落到换行符之后，变成
    下一行行首的多余空格。
    A1：页脚"(点击继续)"文本直接放进末尾的WaitDraw本身（手动用text_handle.align居中，是CenterDraw.draw()
    内部用的同一对齐函数），不再单独画一个CenterDraw页脚——WaitDraw.draw()对空文本(width<=0 or not text)
    走短路分支，不调用askfor_wait；之前wait_draw.text=""导致摘要页画完就直接接上回放内容，不等玩家点击。"""
    from Script.UI.Moudle import draw
    from Script.Config import normal_config
    from Script.Core import text_handle

    rows = _build_summary_rows()
    if not rows:
        return
    width = normal_config.config_normal.text_width

    top_line = draw.LineDraw("─", width)
    top_line.draw()
    title_draw = draw.CenterDraw()
    title_draw.width = width
    title_draw.text = _t("本轮群交结算")
    title_draw.draw()
    title_newline = draw.NormalDraw()
    title_newline.text = "\n"
    title_newline.draw()

    for row in rows:
        for segment in row:
            segment.draw()

    bottom_line = draw.LineDraw("─", width)
    bottom_line.draw()
    wait_draw = draw.WaitDraw()
    wait_draw.width = width
    wait_draw.text = text_handle.align(_t("(点击继续)"), "center", False, 1, width)
    wait_draw.draw()


def _replay_buffered_queue():
    """参数：无；返回：无；用途：摘要页点击后按缓冲发生顺序依次回放保留信息（成就/刻印/素质取得/白名单口上等），回放完毕清空队列；每项都新建绘制对象绘制，不复用被缓冲进来的旧对象。"""
    global replay_queue
    for draw_class, text, style, width, tooltip in replay_queue:
        item = draw_class()
        item.text = text
        item.style = style
        item.width = width
        item.tooltip = tooltip
        item.draw()
    replay_queue = []


# ========================= 10 个替换函数（薄wrapper） =========================
def modded_init_character_behavior():
    """
    参数：无。
    返回：原函数返回值（通常为None）。
    用途：#1 角色行为树总控制的最外层turn边界。用_depth嵌套深度判定本次调用是否为最外层：_depth>1（嵌套调用，
          内层的记录/缓冲自然并入外层）、Web模式、或群交模式未开启，均直通原函数；只有最外层且Tk模式且群交模式
          开启时才接管——重置本mod状态、记录玩家自选行为id、结算完成后绘制摘要页并回放缓冲的保留信息。
          try/finally里递减深度；仅当本turn确实接管过(turn_active曾为True)才在turn结束(_depth归零)时
          整体兜底恢复三个绘制类的draw方法，防止turn中途异常把UI留在吞噬状态——未接管的turn不该无条件动手，
          否则会把其他mod日后打在这三个类上的补丁静默还原掉。
    """
    global _depth, turn_active, player_behavior_id
    _depth += 1
    try:
        if _depth > 1 or _is_web_draw() or not _cache().group_sex_mode:
            return call_original(_CHARACTER_BEHAVIOR_MODULE, "init_character_behavior")
        _reset_turn_state()
        turn_active = True
        player_behavior_id = _cache().character_data[0].behavior.behavior_id
        result = call_original(_CHARACTER_BEHAVIOR_MODULE, "init_character_behavior")
        _draw_summary_page()
        _replay_buffered_queue()
        return result
    finally:
        _depth -= 1
        if _depth == 0:
            was_active = turn_active
            turn_active = False
            if was_active:
                _force_restore_draw_patches()


def _derive_talk_behavior_id(now_talk_id: str, common_behavior_id) -> str:
    """
    参数：now_talk_id(str)为当前口上id；common_behavior_id(str|None)为纸娃娃地文对应的行为id；返回：str为推导出的当前行为id，推导不出时返回空串；
    用途：与原函数talk.py:281-289同口径，从入参而非character_data.behavior推导当前行为id——招呼口上等场景character_data.behavior携带的是玩家行为id，直接读会读错。
    """
    if now_talk_id:
        from Script.Config import game_config

        if now_talk_id in game_config.config_talk:
            return game_config.config_talk[now_talk_id].behavior_id
    if common_behavior_id is not None:
        return common_behavior_id
    return ""


def _talk_whitelist() -> set:
    """
    参数：无；返回：set[str]；用途：懒加载并缓存#2的白名单行为id集合（正常/异常结束群交、疲劳退出、加入/受邀/发现群交），
    常量引用自Script.Core.constant的Behavior/SecondBehavior及其现成的special_end_H_list（复用现有列表，不逐个手抄），
    避免在模块顶层就依赖尚未注入的常量。
    """
    global _TALK_WHITELIST_CACHE
    if _TALK_WHITELIST_CACHE is None:
        import Script.Core.constant as constant
        from Script.Core.constant import Behavior, SecondBehavior

        _TALK_WHITELIST_CACHE = {
            Behavior.GROUP_SEX_END,
            Behavior.GROUP_SEX_NPC_HP_0_END,
            Behavior.GROUP_SEX_PL_HP_0_END,
            Behavior.JOIN_GROUP_SEX,
            Behavior.DISCOVER_OTHER_SEX_AND_JOIN,
            Behavior.BE_INVITED_JOIN_GROUP_SEX,
            SecondBehavior.BE_INVITED_JOIN_GROUP_SEX,
        } | set(constant.special_end_H_list)
    return _TALK_WHITELIST_CACHE


def _should_pass_through_talk(character_id: int, second_behavior_id: str) -> bool:
    """
    参数：character_id(int)角色id；second_behavior_id(str)二段行为id。
    返回：bool，True表示这条口上要放行（不吞掉、不进回放队列）。
    用途：#2的放行判据，抽成纯函数以便自检覆盖。两条语义：
          ①寸止判定失败/解放过的角色（edge_fail_passthrough），且当前正处在自己的#10窗口内
            （_second_effect_character）——整条二段结算链**全部**放行，不再逐个id匹配。
            这是用户提的"改黑名单"：原先按id白名单挑（含"orgasm"且不以"_orgasm_edge"结尾，外加
            semen_drinking_climax等值补丁）本身就是误伤源——每发现一个漏网id就得补一条规则，
            extra_orgasm、semen_drinking_climax都是这么补上去的。既然判据已经收敛到"这个角色本turn
            寸止断了"，那这一次结算里属于他的东西就该整体可见，白名单只会继续漏。
            仍以#10窗口为界而不是无条件放行：窗口外的普通H口上不归这条管，否则该角色整轮刷屏，
            群交摘要就白做了——黑名单只在"寸止链"这个范围内成立，不能推广到全局。
          ②寸止成功但已接近极限的角色（edge_near_limit），只放行_orgasm_edge族本身——即那句
            "XX部位寸止"的黄字标题与口上，让玩家当场看到预警，其余照常隐去。
    """
    if character_id in edge_near_limit and second_behavior_id.endswith("_orgasm_edge"):
        return True
    return character_id in edge_fail_passthrough and character_id == _second_effect_character


def _is_group_sex_background_h(character_id: int, is_h=None) -> bool:
    """参数：character_id(int)角色id；is_h(bool|None)可选注入值，默认从cache实时读取该角色sp_flag.is_h，
    便于自检不依赖真实游戏环境。返回：bool。
    用途：功能3黑名单案例②判据——群交NPC阶段的H动作背景口上（NPC自己的behavior被结算，character_id是
    她自己而非玩家，走settle_behavior.py的character_id!=0一般分支/character_behavior.py主循环里对
    cache.npc_id_got逐个调用judge_character_status，与"玩家/模板派发把character_id固定为0"的路径结构上
    不同）。直接判该角色自身sp_flag.is_h，不碰npc_ai_in_group_sex（禁止改动，见MUST清单）。character_id==0
    （玩家）永远不算背景——玩家自己的口上要么走_should_pass_through_talk/player_real窗口放行，要么走默认
    显示，不该被本判据拦。"""
    if character_id == 0:
        return False
    if is_h is None:
        is_h = bool(_cache().character_data[character_id].sp_flag.is_h)
    return is_h


def _is_edge_release_event(orgasm_edge, orgasm_edge_count) -> bool:
    """
    参数：orgasm_edge(int)角色h_state.orgasm_edge当前值；orgasm_edge_count(dict)角色h_state.orgasm_edge_count当前内容。
    返回：bool，True表示这是一次真正的"寸止解放/失败"事件（而非latch态下同turn内的后续普通绝顶结算）。
    用途：#5入口判据的纯函数版本（v4新增，修复评审指出的老毛病，见#5函数体内注释）：orgasm_edge单独==2会
          一直latch到玩家重新开寸止为止，期间同turn的后续普通绝顶结算也会读到2，误判成新的release/fail事件，
          覆盖掉更早已正确标记的fail。判据：只有release_orgasm_edge_now自己触发的那次调用，orgasm_edge_count
          在调用时刻仍满编（清空动作在其调用返回之后才执行）；latch态下的后续普通调用，orgasm_edge_count
          早已被清空且不再被写入（orgasm_edge!=1时不再累积新计数），恒为空。抽成纯函数只为自检可覆盖，不改变
          #5内的调用语义。
    """
    return orgasm_edge == 2 and any(orgasm_edge_count.values())


def _is_tired_exit(behavior_id) -> bool:
    """
    参数：behavior_id(str)行为id；返回：bool，True表示该行为id是"太累退出H"(GROUP_SEX_NPC_HP_0_END)。
    用途：#5判据用到的纯函数版本（v4抽出，配合评审要求的自检），只认这一个id，其余一律False，不做模糊匹配。
    """
    import Script.Core.constant as constant

    return behavior_id == constant.Behavior.GROUP_SEX_NPC_HP_0_END


def _talk_decision(character_id: int, now_behavior_id: str, second_behavior_id: str, is_h=None) -> str:
    """
    参数：character_id(int)角色id；now_behavior_id(str)当前行为id（由_derive_talk_behavior_id推导）；
          second_behavior_id(str)二段行为id；is_h(bool|None)可选注入值，透传给_is_group_sex_background_h，
          便于自检不依赖真实游戏环境。
    返回：str，"pass"=直显（不缓冲）、"buffer"=缓冲后回放队列兜底、"drop"=吞掉不绘制。
    用途：modded_handle_talk_draw（#2）五级判据（原第2~6级，第1级"是否激活"仍留在调用方）的纯函数版本，
          v4抽出只为让自检能覆盖"白名单必须先于黑名单判"这条顺序约束——顺序本身v3就是对的（太累退出等白名单
          口上此刻character_id是NPC自己、is_h仍为True，黑名单先判会被案例②误伤），这里只是让它可单测。
    """
    if _should_pass_through_talk(character_id, second_behavior_id):
        return "pass"
    if _player_real_instruction_active:
        return "pass"
    if now_behavior_id in _talk_whitelist():
        return "buffer"
    if _template_dispatch_active or _is_group_sex_background_h(character_id, is_h):
        return "drop"
    return "pass"


def modded_handle_talk_draw(character_id: int, talk_text: str, now_talk_id: str, second_behavior_id="", common_behavior_id=None):
    """
    参数：与原函数talk.handle_talk_draw完全一致——character_id(int)角色id，talk_text(str)口上文本，
          now_talk_id(str)当前口上id，second_behavior_id(str)二段行为id，common_behavior_id(str|None)纸娃娃地文行为id。
    返回：原函数返回值，或None（被吞掉时）。
    用途：#2 v3起从"默认隐藏+id白名单放行"翻转为"默认显示+按上下文黑名单拦截"，判据按以下优先级依次判定
          （设计原则见模块docstring：可见性按"因果/来源轴"划分，而非id枚举；重要结果用回放队列兜底；
          整窗全放行只保留给本身不是自包含信息的情形，本轮复核未发现新的这类情形）：
          1. 非激活（不在本mod的Tk群交摘要turn内）：直通原函数。
          2. _should_pass_through_talk命中（寸止链黑名单化+接近极限的寸止族，判据见该函数，v2既有逻辑不变，
             优先级最高——不受v3改动影响）：直接调原函数，不再套_PristineWindow（理由见下方历史注释），
             落进外层#10的本地缓冲，由#10按引擎产生顺序整块补绘。
          3. 功能2窗口（_player_real_instruction_active）：博士亲自指定目标的真实指令直接引发的口上，
             不分白名单/黑名单一律直显（判据见#4：character_id==0且behavior_id==player_behavior_id且
             target_character_id!=0）。
          4. 白名单（_talk_whitelist，v2既有逻辑不变）：定向缓冲后调原函数，回放队列兜底，摘要页点击后
             补放。放在黑名单之前判——太累退出等白名单口上的character_id是NPC自己、is_h此刻仍为True
             （effect 528清is_h在talk绘制之后才跑），若黑名单先判会被案例②误伤，白名单等于白设。
          5. 黑名单（v3新增，按上下文而非id）：①模板派发窗口（_template_dispatch_active，见#4）——
             ②群交NPC阶段H动作背景口上（_is_group_sex_background_h）——命中任一律return None吞掉，
             不绘制不缓存。case③（正常绝顶链/纯粹寸止成功）不需要本层新代码：这类口上多数发生在#10/#9/#5
             自己的本地捕获窗口内，那层窗口本身就按"是否命中edge_fail_passthrough/edge_near_limit/
             _player_real_instruction_active"决定丢弃还是补绘，本函数在此对它们不做任何改动，走默认
             call_original即可，外层窗口自然接管。
          6. 默认（v3新增，取代旧版无条件return None）：直接调原函数，实时显示——所有未落入以上五类的
             口上兜底走这里，不再无条件吞掉。
    """
    if not _is_active():
        return call_original(_TALK_MODULE, "handle_talk_draw", character_id, talk_text, now_talk_id, second_behavior_id, common_behavior_id)
    now_behavior_id = _derive_talk_behavior_id(now_talk_id, common_behavior_id)
    decision = _talk_decision(character_id, now_behavior_id, second_behavior_id)
    if decision == "drop":
        return None
    if decision == "buffer":
        with _ScopedBuffer():
            return call_original(_TALK_MODULE, "handle_talk_draw", character_id, talk_text, now_talk_id, second_behavior_id, common_behavior_id)
    # "pass"分支不再套_PristineWindow：它必然嵌套在#10的本地捕获窗口内，让它落进#10的缓冲，由#10在
    # check_second_effect返回时按引擎产生顺序整块补绘。旧写法用_PristineWindow强行立刻落地，结果是
    # 这些口上抢在#10缓冲的内容（尤其是sibling mod手绘的黄字寸止标题）前面画出来，玩家看到的顺序被
    # 打乱成"先高潮文本后寸止标题"；改为同一条缓冲后，顺序回到引擎顺序：orgasm_judge里的"尝试寸止X的
    # 绝顶，但失败了"仍由#9直绘先出（它在second_behavior_effect之前执行），随后才是这批绝顶口上与黄字标题。
    return call_original(_TALK_MODULE, "handle_talk_draw", character_id, talk_text, now_talk_id, second_behavior_id, common_behavior_id)


def modded_handle_settle_behavior(character_id: int, now_time, event_flag=1):
    """
    参数：与原函数settle_behavior.handle_settle_behavior完全一致——character_id(int)角色id，now_time(datetime)结算时间，event_flag(int)事件结算变量。
    返回：原函数返回的面板对象；本mod激活时通常返回None，命中功能2窗口时返回真实面板。
    用途：#3 非激活直通原函数。激活时结算计算照常执行（call_original的副作用——数值结算、二段行为写入等全部保留）。
          功能2（v3新增）：调用前存旧值、把_player_real_instruction_seen清零，call_original期间若#4命中过
          博士真实指令（is_player_real）会把它置True——命中则本次call_original内部确有一段博士亲自下达、
          直接针对某个目标的真实结算，其属性变化面板必须原样交还上游绘制，不能吞。之所以要靠这个一次性锁存
          而不能直接判断character_id==0：group_sex_mode下character_id==0这一次call_original内部会连续处理
          "玩家真实指令"与"整段模板派发循环"两部分（settle_behavior.py:51-68），二者共用同一个返回的面板对象，
          只能靠#4实际命中的窗口态来标记，不能按character_id笼统放行——否则模板派发部分产生的面板也会被一并放出来。
          存旧值+try/finally恢复（与_second_effect_character/_player_real_instruction_active同一写法，评审
          指出的老毛病）：CSE_*事件→chara_handle_instruct_common_settle(game_update_flag=True)→嵌套
          init_character_behavior→嵌套本函数，属于本次call_original内部的正常事件链；若不恢复，嵌套调用
          进入时的无条件清零会把外层已经锁存的True静默抹掉，外层call_original返回后读到False，博士的属性
          面板被误吞。恢复放在读取seen之后——本次call_original期间（含其内部触发的嵌套调用）只要锁存过一次
          True就应判定为命中，不能被嵌套调用退出时的恢复动作影响这次的判断。
          未命中（含非群交模式下的普通调用、或本次结算全是模板派发）时按原逻辑丢弃返回的面板；上游
          character_behavior.py里对该返回值的判断是"if panel != None and len(...)"，短路安全，原函数自身也
          有多个返回None的路径，上游习以为常。
    """
    if not _is_active():
        return call_original(_SETTLE_BEHAVIOR_MODULE, "handle_settle_behavior", character_id, now_time, event_flag)
    global _player_real_instruction_seen
    previous_seen = _player_real_instruction_seen
    _player_real_instruction_seen = False
    try:
        panel = call_original(_SETTLE_BEHAVIOR_MODULE, "handle_settle_behavior", character_id, now_time, event_flag)
        seen = _player_real_instruction_seen
    finally:
        _player_real_instruction_seen = previous_seen
    if seen:
        return panel
    return None


def modded_handle_instruct_data(character_id: int, behavior_id: str, now_time, add_time, change_data):
    """
    参数：与原函数settle_behavior.handle_instruct_data完全一致——character_id(int)角色id，behavior_id(str)行动id，
          now_time(datetime)结算时间，add_time(int)行动已经过时间，change_data(CharacterStatusChange)状态变更记录对象。
    返回：原函数返回值，或原样返回change_data（跳过执行时）。
    用途：#4 承担三件事，前两件都靠同一个"是否模板派发"判据（settle_behavior.py:51-68：group_sex_mode下
          character_id恒为玩家自身0，模板循环把behavior_id依次换成各NPC目标的状态id，玩家自己真实指令的
          那一次behavior_id==player_behavior_id）：
          1. 功能1"一turn一轮高潮"（唯一改变游戏结果的挂点）：是模板派发、且玩家当前交互目标已经在
             orgasm_record里（本turn已高潮过）时，原样返回change_data不执行本次模板动作。is_template判据
             自v5评审修正起额外排除结束族与GROUP_SEX_TO_H（理由见函数体内注释）——此前v1起的"仅凭
             behavior_id!=player_behavior_id"在级联结束场景会把真实结束结算误判成模板派发而整条跳过。
          2. 功能2"博士针对性动作全显"窗口标记（v3新增，v5用户裁定1a收窄，纯显示层，不改变何时执行）：
             博士亲自指定目标的那次真实指令（is_player_real：character_id==0、behavior_id==player_behavior_id、
             当前有target_character_id、且behavior_id不属于"波及全体"的结束族/全员玩具族——
             _is_mass_instruction，见其定义处）期间，把_player_real_instruction_active置True并锁存
             _player_real_instruction_seen，让#2/#5/#9/#10在这个窗口内原样实时显示；同时把
             _template_dispatch_active在整个模板派发窗口内置True，供#3黑名单案例①识别、拦掉模板派发的
             口上与标题。两个窗口标记都靠try/finally保存旧值再恢复，嵌套安全（同_second_effect_character
             的既定写法），即使非群交模式下的普通调用也不会误触发（is_player_real/is_template都以
             cache_obj.group_sex_mode为前提）。新增排除的理由：GROUP_SEX_END等结束指令、REMOTE_ALL_*等
             全员玩具指令，走的都是chara_handle_instruct_common_settle(behavior_id, character_id)不显式
             传target_character_id的调用路径（handle_instruct.py:321-396），该函数未传值时不会清空/重置
             角色当前的target_character_id字段，只是原样保留其之前的遗留值——玩家此刻的target_character_id
             很可能因群交过程中先前的定向指令而非零，这个非零值不代表"结束/全员玩具"这次调用是针对该角色
             的定向指令，若不排除会误开全显窗口，刷出用户否掉的"结束群交时一大串实时结算"。
          3. tired 判定标记（v5用户裁定2a新增，纯记账，不改变何时执行）：只要看到behavior_id==
             GROUP_SEX_NPC_HP_0_END（不看character_id是否为0，NPC太累退出的character_id是该NPC自己）
             就直接_mark_edge_break_reason(character_id, "tired", passthrough=False)，不再依赖#5的
             _is_edge_release_event。挂点可靠性依据：commit_group_sex_tired_exit(handle_npc_ai.py:145-179)
             先经chara_handle_instruct_common_settle把该NPC的behavior.behavior_id改成这个专属id，再直接调用
             character_behavior.judge_character_status(character_id)（不经过init_character_behavior，
             不改变_depth/turn_active，仍在外层turn窗口内），其内部
             (character_behavior.py:230)调用settle_behavior.handle_settle_behavior（#3），NPC路径
             （character_id!=0）落入settle_behavior.py的直接调用分支（非模板循环），必然单独调用一次
             handle_instruct_data（#4）且此刻的behavior_id就是刚被设置的GROUP_SEX_NPC_HP_0_END——是这个
             行为id在结算链上的必经点，比依赖#5的release事件（该事件仅在批量结束链effect 529里出现，个体
             NPC自己的太累退出走的是1503/528/403/635清理链，通常不触发release_orgasm_edge_now）更可靠，
             修复了DESIGN.md记录的窄缺口"先寸止失败再太累退出，标记停留在<寸止失败>"。passthrough显式传
             False：用户裁定2只要求tired挂标记、进摘要行、配紫色，未要求改变是否实时刷屏——这里不新增
             edge_fail_passthrough写入，避免把"标记"和"是否放行实时显示"这两件事再次耦合回去（重蹈本轮
             要拆掉的旧耦合）；若该角色后续确实触发了#5的真实release事件，是否实时显示由#5按当时判据
             （是否源自批量结束链）独立决定，两处各管一段互不覆盖（_mark_edge_break_reason对
             edge_fail_passthrough是并集式add，对reason是优先级式更新，两套语义分别独立生效）。
    """
    if not turn_active or _is_web_draw():
        return call_original(_SETTLE_BEHAVIOR_MODULE, "handle_instruct_data", character_id, behavior_id, now_time, add_time, change_data)
    if _is_tired_exit(behavior_id):
        _mark_edge_break_reason(character_id, "tired", passthrough=False)
    cache_obj = _cache()
    from Script.Core.constant import Behavior

    # is_template必须同步排除结束族与GROUP_SEX_TO_H：settle_behavior.py:38-44本就把这两类排除在群交模板
    # 循环之外、路由到普通分支——被路由到非模板分支的行为按定义不是模板派发。级联场景（handle_npc_ai.py
    # :171-178：NPC耗尽后剩0人转结束群交/剩1人转普通H）会中途改写玩家behavior_id，而player_behavior_id
    # 仍是turn开头旧快照，仅凭"!=快照"会把这次真实的结束/转H结算误判成模板派发——若此刻玩家
    # target_character_id恰好在orgasm_record里（本turn高潮过，很常见），就会整条跳过结束结算
    # （529批量解放/407清H状态/636穿衣等一条不跑），是改变游戏状态的错误跳过，不只是显示问题。
    is_template = (
        cache_obj.group_sex_mode
        and character_id == 0
        and behavior_id != player_behavior_id
        and behavior_id not in _mass_end_behavior_family()
        and behavior_id != Behavior.GROUP_SEX_TO_H
    )
    if is_template and cache_obj.character_data[0].target_character_id in orgasm_record:
        return change_data
    is_player_real = (
        cache_obj.group_sex_mode
        and character_id == 0
        and behavior_id == player_behavior_id
        and cache_obj.character_data[0].target_character_id != 0
        and not _is_mass_instruction(behavior_id)
    )
    global _player_real_instruction_active, _player_real_instruction_seen, _template_dispatch_active
    if is_player_real:
        _player_real_instruction_seen = True
    previous_real_active, previous_template_active = _player_real_instruction_active, _template_dispatch_active
    if is_player_real:
        _player_real_instruction_active = True
    if is_template:
        _template_dispatch_active = True
    try:
        return call_original(_SETTLE_BEHAVIOR_MODULE, "handle_instruct_data", character_id, behavior_id, now_time, add_time, change_data)
    finally:
        _player_real_instruction_active, _template_dispatch_active = previous_real_active, previous_template_active


def modded_orgasm_settle_in_second_behavior(character_id: int, change_data, normal_orgasm_dict: dict = {}, extra_orgasm_dict: dict = {}, un_count_orgasm_dict: dict = {}):
    """
    参数：与原函数orgasm_settle.orgasm_settle_in_second_behavior完全一致——character_id(int)角色id，
          change_data(CharacterStatusChange)状态变更记录对象，normal_orgasm_dict/extra_orgasm_dict/un_count_orgasm_dict
          为各类高潮次数字典。
    返回：原函数返回值（该函数本身无显式return，此处透传以保持签名兼容）。
    用途：#5 功能1判据与摘要数据的唯一采集点，v2起还兼管性爱发电提示（orgasm_settle.py:322-329附近，函数体内
          直绘，与二段标题不是同一调用路径，需单独处理）的隐去/放行。非激活直通原函数。激活时用本地列表捕获
          call_original期间产生的绘制（该窗口内还嵌套着#9的本地捕获窗口——各自只保存/写自己进入时生效的那个
          draw方法，互不干扰，可安全嵌套；#6的成就通知走的是默认target_list即全局replay_queue，同理不受影响，
          仍会正常进回放队列）：character_id命中edge_fail_passthrough（本turn需要实时刷屏）则原样补绘（发电
          提示属于该角色寸止断了链的一部分，与二段标题同一套"原样直显"语义）；否则整段丢弃（普通高潮过程信息，
          隐去）。丢弃/补绘之后照常扫描该角色character_data.second_behavior中本次新置位的部位绝顶/寸止id并入
          orgasm_record/edge_record——挂这里而不是orgasm_judge：它是这些二段行为id的唯一写入点，寸止强制解放
          与时停解放不经过orgasm_judge但都经过它，一个挂点收口全部调用路径；扫描时机在消费清零
          (second_behavior_effect)之前，窗口成立。玩家(character_id==0)的射精/绝顶另有专门面板，记录里直接排除。
          v5变化：不再在这里判定tired（用户裁定2a，改由#4在看到behavior_id==GROUP_SEX_NPC_HP_0_END时统一、
          更早、更可靠地标记，覆盖个体NPC太累退出通常不触发本函数release分支的窄缺口，见#4文档）；
          _is_edge_release_event命中时只标"release"，若#4已先标过"tired"，_mark_edge_break_reason的优先级
          只升不降不会被这里覆盖。同时落实用户裁定1b：本次release事件是否源自"结束群交等全体类结束指令"
          触发的批量解放链，判据（抽成纯函数_is_mass_end_release_source，见其定义处）是调用当下（不是本turn
          开头捕获的player_behavior_id——两者可能不同值，理由见下）玩家(character_id==0)的实时behavior_id
          是否落在_mass_end_behavior_family()内。是则
          passthrough=False——只记账供摘要页<寸止释放>正确显示，不并入edge_fail_passthrough，避免这类批量
          解放触发用户否掉的"结束群交时一大串实时刷屏"；否则（定向单人解放，如6014/ORGASM_EDGE_OFF，与
          结束族行为id不相交）保持passthrough=True，全程实时直显不变。
          为何必须实时读而非用player_behavior_id：批量解放的真正触发源是effect 529
          （GROUP_SEX_END_H_ADD_HPMP_MAX，constant_effect.py:477；实现在default.py:6873
          handle_group_sex_end_h_add_hpmp_max，循环scene_data.character_list、对orgasm_edge!=0的每个
          角色调release_orgasm_edge_now），而529只挂在玩家自身行为371(group_sex_end)和373
          (group_sex_pl_hp_0_end)的效果串上（Behavior_Effect.csv:167,169；374 group_sex_npc_hp_0_end的
          效果串是1503/528/403/635，不含529）。effect串按当前behavior_id触发是settle_behavior的既定
          机制，因此本函数只要是被effect 529的循环调进来的，就必然发生在玩家的behavior_id已经等于
          group_sex_end/group_sex_pl_hp_0_end的那次结算内——不论这个值是玩家本turn自己选的（直接选"结束
          群交"指令），还是被handle_group_sex_end(handle_instruct.py:1578-1590)当作NPC耗尽级联的副作用
          现改（该函数固定操作character_data[0]，1585-1586先把玩家behavior_id置为GROUP_SEX_END，effect
          串才据此触发）——两种路径下这次调用发生的同一调用栈内，玩家的实时behavior_id都必然已经是
          结束族成员，读取当下值恒可靠；而player_behavior_id是turn开头的快照，级联场景下玩家那一turn
          原本选的可能是别的动作（如某个部位模板动作），到NPC耗尽触发副作用式结束时该快照早已过期，
          若拿它判据会在这条"NPC耗尽引发的批量结束"路径上误判为非批量、漏掉本该抑制的实时刷屏——
          这正是用户想修的观感问题，故必须用实时读法。
    """
    if not _is_active() or character_id == 0:
        return call_original(_ORGASM_SETTLE_MODULE, "orgasm_settle_in_second_behavior", character_id, change_data, normal_orgasm_dict, extra_orgasm_dict, un_count_orgasm_dict)
    # 手动/被动解放寸止（release_orgasm_edge_now）与寸止判定失败是同一类"憋不住了，全放出来"的事件，
    # 玩家都该看到全过程；但解放路径不经过judge_orgasm_edge_success（#9），不会被#9登记进
    # edge_fail_passthrough，此前整条链被当普通高潮吞掉，一个字都不显示。
    # 判据（v4订正，评审指出v3版有老毛病）：release_orgasm_edge_now(orgasm_settle.py:345先置2、347再调本函数、
    # 349-351调用返回后才清空orgasm_edge_count)是解放的唯一入口。但orgasm_edge一旦置2，会一直latch到玩家
    # 重新下"开启绝顶寸止"指令(SELF_ORGASM_EDGE_ON效果，default.py:2284，同时清零orgasm_edge_count)或"关闭"
    # (SELF_ORGASM_EDGE_OFF，:2308置0)为止——期间该角色任何后续正常绝顶结算进入本函数时orgasm_edge同样读到
    # 2，但这些调用不是新的解放事件（寸止判定失败分支:189同理，把edge置2发生在本函数体内部、call_original
    # 期间，早于本次判据要判的那次调用的入口检查不算，属于#9独立标记的路径）。v3版只看orgasm_edge==2，会把
    # 这类"latch态下的普通后续绝顶"也误判成一次新的release，用_mark_edge_break_reason标"release"(优先级2)，
    # 覆盖掉同turn更早由#9正确标记的"fail"(优先级1)，导致<寸止失败>标记几乎显示不出来。
    # 修法：额外要求orgasm_edge_count本身有非零计数——只有release_orgasm_edge_now自己触发的这次调用才满足
    # （:347传入的un_count_orgasm_dict就是当时仍满编的orgasm_edge_count，清空动作在:349-351、即本次调用
    # 返回之后才执行）；latch态下的后续普通调用，orgasm_edge_count早已在上一次解放/失败时被清空且不再被
    # 写入（该角色orgasm_edge!=1时，:168 orgasm_edge_flag恒False，本函数体内更新候选计数的分支根本不执行），
    # 恒为空，不会被误判。
    h_state = _cache().character_data[character_id].h_state
    if _is_edge_release_event(h_state.orgasm_edge, h_state.orgasm_edge_count):
        is_mass_end_release = _is_mass_end_release_source(_cache().character_data[0].behavior.behavior_id)
        _mark_edge_break_reason(character_id, "release", passthrough=not is_mass_end_release)
    local_capture = []
    with _ScopedBuffer(target_list=local_capture):
        result = call_original(_ORGASM_SETTLE_MODULE, "orgasm_settle_in_second_behavior", character_id, change_data, normal_orgasm_dict, extra_orgasm_dict, un_count_orgasm_dict)
    # or _player_real_instruction_active：功能2——博士亲自指定目标的真实指令直接引发的绝顶链也要原样实时显示
    if character_id in edge_fail_passthrough or _player_real_instruction_active:
        for item_tuple in local_capture:
            _draw_live(item_tuple)
    character_data = _cache().character_data[character_id]
    _merge_second_behavior_into_records(character_id, character_data.second_behavior)
    return result


def modded_draw_achievement_notice(achievement_id_list: list):
    """
    参数：achievement_id_list(list[int])为成就id列表，与原函数一致。
    返回：原函数返回值（None）。
    用途：#6 非激活直通原函数。激活时在定向缓冲下调用原函数，把成就获得提示缓存进replay_queue延后到摘要页
          之后统一回放。挂这里而不是achievement_flow：它是全部成就的唯一绘制出口（全仓单一调用点），覆盖turn内
          多重绝顶成就(orgasm_settle.py:319-323，群交最高频成就)、turn末群交/时停成就等所有来源。
    """
    if not _is_active():
        return call_original(_ACHIEVEMENT_MODULE, "draw_achievement_notice", achievement_id_list)
    with _ScopedBuffer():
        return call_original(_ACHIEVEMENT_MODULE, "draw_achievement_notice", achievement_id_list)


def modded_mark_effect(character_id: int, change_data):
    """
    参数：character_id(int)角色id，change_data(CharacterStatusChange)状态变更记录对象，与原函数second_behavior.mark_effect一致。
    返回：原函数返回值。
    用途：#7 非激活直通原函数。激活时在定向缓冲下调用原函数，把刻印取得文本缓存进replay_queue延后回放。
          它在函数尾直接WaitDraw().draw()，绕过#2的handle_talk_draw，必须单独包一层。
    """
    if not _is_active():
        return call_original(_SECOND_BEHAVIOR_MODULE, "mark_effect", character_id, change_data)
    with _ScopedBuffer():
        return call_original(_SECOND_BEHAVIOR_MODULE, "mark_effect", character_id, change_data)


def modded_gain_talent(character_id: int, now_gain_type: int, traget_talent_id=0):
    """
    参数：character_id(int)角色id，now_gain_type(int)素质获得类型，traget_talent_id(int)手动获得时的目标素质id，与原函数handle_talent.gain_talent一致。
    返回：原函数返回值（None）。
    用途：#8 非激活直通原函数。激活时在定向缓冲下调用原函数，把素质取得提示缓存进replay_queue延后回放；
          该提示的WaitDraw在handle_talent.py:71-73处绘制，由character_behavior.py:189每角色每turn调用一次。
    """
    if not _is_active():
        return call_original(_HANDLE_TALENT_MODULE, "gain_talent", character_id, now_gain_type, traget_talent_id)
    with _ScopedBuffer():
        return call_original(_HANDLE_TALENT_MODULE, "gain_talent", character_id, now_gain_type, traget_talent_id)


def modded_judge_orgasm_edge_success(character_id: int, orgasm_edge_count: dict = {}, crossed_part_count: int = 1) -> bool:
    """
    参数：与原函数orgasm_settle.judge_orgasm_edge_success完全一致——character_id(int)角色id，
          orgasm_edge_count(dict)本次寸止次数字典，crossed_part_count(int)本次跨越部位数。
    返回：原函数返回值（bool，寸止判定是否成功），透传不改变。
    用途：#9 非激活直通原函数。激活时用本地列表捕获原函数体内唯一一处判定提示绘制（orgasm_settle.py:417/419/
          430/433四种成功/失败文本分支，函数内只有这一处NormalDraw().draw()）——判定结果在函数返回前不可知，
          call_original结束、拿到真实bool返回值后才分流：成功→整段丢弃（不绘制不回放，寸止过程信息隐去）；
          失败→立即用_draw_live按序原样补绘（寸止失败导致的绝顶从判定提示起原样实时显示），并把该角色id计入
          edge_fail_passthrough，供#2放行其随之而来的绝顶二段标题/口上、#5放行其性爱发电提示。
    """
    if not _is_active():
        return call_original(_ORGASM_SETTLE_MODULE, "judge_orgasm_edge_success", character_id, orgasm_edge_count, crossed_part_count)
    local_capture = []
    with _ScopedBuffer(target_list=local_capture):
        success = call_original(_ORGASM_SETTLE_MODULE, "judge_orgasm_edge_success", character_id, orgasm_edge_count, crossed_part_count)
    if not success:
        _mark_edge_break_reason(character_id, "fail")
    # 寸止成功但已经接近/超过能控制住的极限时也放行这条提示（用户要求：让"马上忍不住了"当场可见）。
    # 上游同一处直绘按余量分三种成功文本(orgasm_settle.py:414-419/431-433)：余量>2是平淡的"成功寸止了X"，
    # 余量<=2是"差不多也到了能控制住的极限了"，余量<0（骰子侥幸过了）是"已经超过了能控制住的极限，随时
    # 都可能释放出来"。后两种正是玩家需要据以决策的预警，故以余量<=2为门放行，平淡的那种继续隐去。
    # 只放行这一次提示，不写入edge_fail_passthrough——寸止毕竟成功了，本次没有绝顶链要跟着放行；
    # 该提示本身只是文本，不含任何数值结算，放行它不改变游戏结果。
    # 余量<=2这道门与状态栏"快忍不住"的感叹号是同一条线：character_info_head.py:242-254按同一余量分档，
    # 余量>=3为平静的<寸止>（不放行），0<=余量<=2为<寸止!>，余量<0为<寸止!!>，带感叹号的两档正是这里放行的两档。
    near_limit = False
    if success:
        # 与上游判定同源：入参为空时上游会回落到角色实时寸止计数(orgasm_settle.py:404-405)，此处保持一致
        now_edge_count = orgasm_edge_count or _cache().character_data[character_id].h_state.orgasm_edge_count
        near_limit = _edge_margin(_cache().character_data[0].ability[30], now_edge_count) <= 2
        if near_limit:
            # 让#2放行该角色的_orgasm_edge族标题/口上、#10放行批次合并的黄字寸止标题，
            # 即玩家说的"黄色提示字样的XX部位寸止"。只影响显示，不碰任何结算。
            edge_near_limit.add(character_id)
    # or _player_real_instruction_active：功能2——博士亲自指定目标的真实指令期间，寸止判定提示（无论成败）
    # 也要原样实时显示，与其后续的整条二段链保持"全过程可见"一致
    if not success or near_limit or _player_real_instruction_active:
        for item_tuple in local_capture:
            _draw_live(item_tuple)
    return success


def modded_check_second_effect(character_id: int, change_data, pl_to_npc: bool = False):
    """
    参数：与原函数second_behavior.check_second_effect完全一致——character_id(int)角色id，
          change_data(CharacterStatusChange)状态变更记录对象，pl_to_npc(bool)是否为玩家对NPC的行为结算。
    返回：原函数返回值（该函数本身无显式return，此处透传以保持签名兼容）。
    用途：#10（A2真因修复）非激活或character_id==0（玩家路径，与#5同口径）直通原函数——玩家侧
          check_second_effect(0)→orgasm_judge(0)会触发忍耐询问文本（ejaculation_panel.py:64-68
          NormalDraw）与射精面板内文本（同文件:468 WaitDraw），若不直通会被本窗口捕获丢弃（id 0永不在
          edge_fail_passthrough），但面板自带的CenterButton不受影响照常画出、askfor_all照常阻塞，
          变成只有按钮没有文字的残缺面板；直通也不会重新放出gold直绘泄漏——
          local_orgasm_batch_talk_fix.py:194的`if not character_id or ...`本身已经把character_id==0
          排除在批次接管之外，其手绘只发生在NPC侧调用。激活且非玩家时：用本地列表捕获call_original期间
          产生的绘制，character_id命中edge_fail_passthrough则按序用_draw_live原样补绘，否则整段丢弃——
          语义与#5/#9同一套"先捕获再按结果决定"，复用同一个_ScopedBuffer(target_list=...)机制，不新开
          一套。

          挂这里而非second_behavior_effect本身，是v1泄漏真因的收口点：本仓已启用的
          local_orgasm_batch_talk_fix mod包装了second_behavior_effect，在函数体内直接手绘WaitDraw
          （_draw_orgasm_info_text，第163/172行，gold_enrod样式，用于多部位寸止合并标题与>3部位绝顶
          汇总行），完全绕开talk.handle_talk_draw，#2的白名单/放行逻辑对它不可见——这是v1泄漏发生的真实
          机制。check_second_effect是second_behavior_effect唯一的上游调用点（settle_behavior.py:426/440
          两处module-attribute调用均只经过这一个函数），在这里捕获可以连同批次汇总一起收口，不必改动那个
          mod（它是冻结复核的fix-mod，按协调者裁定不动）。

          A2-3 无重复推理（订正：#5/#9确实嵌套在本窗口内，正确性不靠"不嵌套"）：second_behavior.py:98/121
          在check_second_effect内部调用orgasm_judge，orgasm_judge内部再调orgasm_settle_in_second_behavior
          （#5），其内部又调judge_orgasm_edge_success（#9）——调用栈是check_second_effect→orgasm_judge→
          #5→#9，#5/#9的窗口确实嵌套在本窗口内。不重复靠两条：①嵌套的_ScopedBuffer各自只保存/写自己
          进入那一刻生效的draw方法（"嵌套安全"，见_ScopedBuffer类文档）——#5/#9自己窗口内产生的绘制被
          它们自己当前生效的缓冲闭包捕获进各自的本地列表，此刻target_class.draw是#5/#9的闭包而不是
          本窗口的，落不进本窗口的local_capture；②#5/#9决定补绘时走_draw_live，直接调用
          _PRISTINE_DRAW_METHODS[draw_class](item)，绕开target_class.draw这个属性查找，不经过当前无论
          谁装的补丁（含本窗口）——因此#5/#9的_draw_live输出也不会被本窗口二次捕获。
    """
    if not _is_active() or character_id == 0:
        return call_original(_SECOND_BEHAVIOR_MODULE, "check_second_effect", character_id, change_data, pl_to_npc)
    global _second_effect_character
    local_capture = []
    previous_character = _second_effect_character
    _second_effect_character = character_id
    try:
        with _ScopedBuffer(target_list=local_capture):
            result = call_original(_SECOND_BEHAVIOR_MODULE, "check_second_effect", character_id, change_data, pl_to_npc)
    finally:
        _second_effect_character = previous_character
    # edge_near_limit也放行：多部位寸止时那行黄字合并标题"XX、YY绝顶寸止"是sibling mod直接手绘的
    # （local_orgasm_batch_talk_fix.py:172），不经过handle_talk_draw，#2看不见它，只能在这一层放行。
    # ponytail: 整段放行，不按文本挑行。若该角色同turn还绝顶了>3个部位，那行黄色汇总也会一起放出来——
    # 内容与摘要页重复但不矛盾，为它写文本过滤不值当；真觉得吵再按draw顺序切分。
    # or _player_real_instruction_active：功能2——博士亲自指定目标的真实指令引发的二段结算批次汇总同理放行
    if character_id in edge_fail_passthrough or character_id in edge_near_limit or _player_real_instruction_active:
        for item_tuple in local_capture:
            _draw_live(item_tuple)
    return result


# ========================= 轻量自检（assert，无测试框架，可直接 python 运行） =========================
def _self_check():
    """参数：无；返回：无；用途：用假对象验证定向缓冲的嵌套保存/恢复（含本地target_list与全局replay_queue的
    嵌套隔离，以及#10本地窗口+内层默认窗口+绕过补丁直绘的三层嵌套无串扰无重复、_PristineWindow在外层有
    补丁时的强制转回与精确恢复）、orgasm_record按部位取
    最高档去重、状态栏口径寸止标记公式、寸止token分组文案、未知部位不丢弃、摘要页角色纳入条件与姓名style
    根因（QA真机缺陷1/2）、右对齐依赖的CJK显示宽度计算等核心逻辑，不依赖真实游戏运行
    环境，可用`python group_sex_summary.py`或`python -c`直接跑。
    两种跑法与差别：裸跑（不设PYTHONPATH，或从scripts/子目录内直接跑）时import Script.Core.constant会
    失败，依赖白名单集合/行为id常量的那组断言（如3a3b/3a3c，_talk_decision/_is_tired_exit相关）会被
    对应的try/except静默跳过、只打印提示，不算失败；只有在仓库根目录下用
    `PYTHONPATH=. python mod/group_sex_summary/scripts/group_sex_summary.py`跑，import才会成功，
    这组断言才会被真正执行。CI/复核时须用后一种跑法，否则这组断言形同虚设。"""

    # 1. 定向缓冲的嵌套保存/恢复（v2起缓冲函数是按target_list生成的闭包，不再是单一模块函数，用各自的
    #    ._buffered_draw属性做身份比对）
    class _FakeDraw:
        log = []

        def draw(self):
            _FakeDraw.log.append("real_draw")

    original_draw = _FakeDraw.draw
    outer_buffer = _ScopedBuffer([_FakeDraw])
    with outer_buffer:
        assert _FakeDraw.draw is outer_buffer._buffered_draw, "外层进入后应替换为外层自己的缓冲闭包"
        inner_buffer = _ScopedBuffer([_FakeDraw])
        with inner_buffer:
            assert _FakeDraw.draw is inner_buffer._buffered_draw, "内层进入后仍应是内层自己的缓冲闭包"
            replay_queue.clear()
            item = _FakeDraw()
            item.text, item.style, item.width, item.tooltip = "内层文本", "standard", 10, "提示文本"
            item.draw()
        # 内层退出应恢复为"进入内层前"的值——此时仍是外层打上的缓冲闭包，而不是最初的真实draw
        assert _FakeDraw.draw is outer_buffer._buffered_draw, "内层退出后应恢复为外层的缓冲闭包，而非真实draw"
    # 外层退出后应恢复为最初真实的draw
    assert _FakeDraw.draw is original_draw, "外层退出后应恢复为最初的真实draw方法"
    assert replay_queue == [(_FakeDraw, "内层文本", "standard", 10, "提示文本")], "默认target_list应写入全局replay_queue（缓冲应存值元组而非对象）"
    replay_queue.clear()
    _FakeDraw().draw()
    assert _FakeDraw.log == ["real_draw"], "恢复后调用draw应重新执行真实绘制"

    # 1b. 嵌套隔离：外层用本地target_list捕获（对应#5/#9的"先捕获再决定"），内层用默认target_list
    #     （全局replay_queue，对应嵌套其中的#6成就通知）——二者应只收到各自窗口内的绘制，互不串扰
    outer_local = []
    with _ScopedBuffer([_FakeDraw], target_list=outer_local):
        before = _FakeDraw()
        before.text, before.style, before.width, before.tooltip = "外层文本1", "standard", 5, ""
        before.draw()
        with _ScopedBuffer([_FakeDraw]):
            nested = _FakeDraw()
            nested.text, nested.style, nested.width, nested.tooltip = "内层文本2", "standard", 5, ""
            nested.draw()
        after = _FakeDraw()
        after.text, after.style, after.width, after.tooltip = "外层文本3", "standard", 5, ""
        after.draw()
    assert [t[1] for t in outer_local] == ["外层文本1", "外层文本3"], "外层本地列表应只收到外层窗口内的绘制，不含嵌套内层的"
    assert [t[1] for t in replay_queue] == ["内层文本2"], "嵌套内层的默认target_list应写入全局replay_queue，不受外层本地窗口影响"
    replay_queue.clear()

    # 1c. 三层嵌套（A2要求）：外层#10风格的本地捕获窗口 + 内层默认target_list窗口（对应嵌套其中的#2放行分支
    #     走_PristineWindow后、或#6/#7/#8的默认窗口，二者行为等价：都是"当前生效的缓冲/pristine与外层不同"）
    #     + 绕过当前一切补丁的直接绘制（对应_draw_live/_PristineWindow"直接调用未被patch的原始方法"这一
    #     机制——_draw_live本身要import真实Script.UI.Moudle.draw，脱离游戏环境的自检里无法直接调用，这里
    #     用保存下来的原始未patch方法直接调用来等价模拟同一机制）。验证三者互不串扰、互不重复。
    _FakeDraw.log = []
    outer_capture = []
    with _ScopedBuffer([_FakeDraw], target_list=outer_capture):
        first = _FakeDraw()
        first.text, first.style, first.width, first.tooltip = "外层A", "standard", 5, ""
        first.draw()
        with _ScopedBuffer([_FakeDraw]):
            second = _FakeDraw()
            second.text, second.style, second.width, second.tooltip = "内层B", "standard", 5, ""
            second.draw()
        # 等价于_draw_live：无视当前生效中的外层缓冲闭包，直接调用最初的原始draw方法
        bypass = _FakeDraw()
        bypass.text = "直绘C"
        original_draw(bypass)
        fourth = _FakeDraw()
        fourth.text, fourth.style, fourth.width, fourth.tooltip = "外层D", "standard", 5, ""
        fourth.draw()
    assert [t[1] for t in outer_capture] == ["外层A", "外层D"], "三层嵌套：外层本地列表应只收到外层窗口自己的绘制，不含内层默认窗口与直绘"
    assert [t[1] for t in replay_queue] == ["内层B"], "三层嵌套：内层默认窗口应写入全局replay_queue，不受外层本地窗口影响，也不进外层本地列表"
    assert _FakeDraw.log == ["real_draw"], "三层嵌套：绕过当前补丁的直绘应真实执行且仅此一次，不落进外层本地列表也不落进replay_queue（无重复）"
    replay_queue.clear()

    # 1d. _PristineWindow（顺手补的自检）：外层已有补丁生效时进入 → 窗口内绘制应真实落地（走pristine，
    #     不被外层补丁捕获）→ 退出后应精确恢复为外层的补丁（而非留在pristine状态）
    _FakeDraw.log = []
    _PRISTINE_DRAW_METHODS[_FakeDraw] = original_draw  # _PristineWindow.__enter__依赖此表；真实类由_draw_classes()注册，假类需手动补
    outer_patch = _ScopedBuffer([_FakeDraw])
    with outer_patch:
        assert _FakeDraw.draw is outer_patch._buffered_draw, "外层补丁进入后应生效"
        with _PristineWindow([_FakeDraw]):
            assert _FakeDraw.draw is original_draw, "_PristineWindow内应强制转回真实draw方法，无视外层补丁"
            _FakeDraw().draw()
        assert _FakeDraw.log == ["real_draw"], "_PristineWindow内的绘制应真实落地，不被外层补丁捕获"
        assert _FakeDraw.draw is outer_patch._buffered_draw, "_PristineWindow退出后应恢复为外层补丁，而非留在pristine状态"
    assert _FakeDraw.draw is original_draw, "外层补丁退出后应恢复为最初真实draw"
    del _PRISTINE_DRAW_METHODS[_FakeDraw]  # 清理假类注册，避免污染_PRISTINE_DRAW_METHODS

    # 2. orgasm_record 按部位取最高档去重（同一turn多次结算，后来的低档不应覆盖已记录的高档）
    def _fake_part_degree_parser(second_behavior_id: str):
        rank_by_suffix = {"small": 0, "normal": 1, "strong": 2, "super": 3}
        pieces = second_behavior_id.split("_")
        if len(pieces) == 3 and pieces[1] == "orgasm" and pieces[2] in rank_by_suffix:
            return pieces[0], rank_by_suffix[pieces[2]]
        return None, -1

    orgasm_record.clear()
    edge_record.clear()
    first_call_second_behavior = {"v_orgasm_small": 1, "v_orgasm_strong": 1, "c_orgasm_normal": 0, "a_orgasm_edge": 1}
    _merge_second_behavior_into_records(7, first_call_second_behavior, part_degree_parser=_fake_part_degree_parser)
    assert orgasm_record[7] == {"v": 2}, "同一部位应取最高档(strong=2)，未触发(value=0)的c部位应被忽略"
    assert edge_record[7] == {"a": 1}, "寸止应按部位计数"
    _merge_second_behavior_into_records(7, {"v_orgasm_normal": 1}, part_degree_parser=_fake_part_degree_parser)
    assert orgasm_record[7]["v"] == 2, "本turn第二次结算的更低档(normal=1)不应覆盖已记录的更高档(strong=2)"
    orgasm_record.clear()
    edge_record.clear()

    # 3. 状态栏口径的寸止标记（margin = 寸止技巧*3 - 各部位次数平方和，与character_info_head.py三档对齐）
    edge_record.clear()
    assert _edge_status_tag(11) == ("", ""), "本turn无寸止记录(edge_record无该角色条目)不应显示标记"
    edge_record[11] = {"v": 1}
    assert _edge_status_tag(11, skill_ability_lv=2, orgasm_edge_count={"v": 1}) == (" <寸止>", "hot_pink"), "margin=2*3-1=5>=3应为<寸止>"
    assert _edge_status_tag(11, skill_ability_lv=1, orgasm_edge_count={"v": 1}) == (" <寸止!>", "red"), "margin=1*3-1=2，0<=2<3应为<寸止!>"
    assert _edge_status_tag(11, skill_ability_lv=0, orgasm_edge_count={"v": 2}) == (" <寸止!!>", "levelex"), "margin=0*3-4=-4<0应为<寸止!!>"
    edge_record.clear()

    # 3a2. #2放行判据：寸止链在#10窗口内整体放行（黑名单化），接近极限只放寸止族
    global _second_effect_character
    edge_fail_passthrough.clear()
    edge_near_limit.clear()
    _second_effect_character = None
    assert not _should_pass_through_talk(11, "v_orgasm_edge"), "两个集合都没命中时不放行"
    edge_fail_passthrough.add(11)
    assert not _should_pass_through_talk(11, "v_orgasm_strong"), "不在自己的#10窗口内时不放行，窗口外仍按白名单办"
    _second_effect_character = 11
    assert _should_pass_through_talk(11, "v_orgasm_strong"), "寸止断了的角色在窗口内应整体放行"
    assert _should_pass_through_talk(11, "extra_orgasm"), "无前缀下划线的extra_orgasm不再需要单独补规则"
    assert _should_pass_through_talk(11, "semen_drinking_climax"), "不含orgasm子串的饮精高潮同样自然放行"
    assert _should_pass_through_talk(11, ""), "sibling mod那条second_behavior_id为空的寸止正文也放行"
    assert not _should_pass_through_talk(12, "v_orgasm_strong"), "窗口属于11时，12不受影响"
    edge_fail_passthrough.clear()
    edge_near_limit.add(11)
    assert _should_pass_through_talk(11, "v_orgasm_edge"), "接近极限时应放行黄字寸止标题/口上"
    assert not _should_pass_through_talk(11, "v_orgasm_strong"), "接近极限只放寸止族，不放绝顶族"
    assert not _should_pass_through_talk(12, "v_orgasm_edge"), "未命中的角色不受影响"
    edge_near_limit.clear()
    _second_effect_character = None

    # 3a3. #2黑名单案例②判据：_is_group_sex_background_h（纯函数，character_id==0恒False；否则看is_h）
    assert not _is_group_sex_background_h(0, is_h=True), "玩家id 0永不算背景H，即便注入is_h=True"
    assert _is_group_sex_background_h(21, is_h=True), "非玩家角色is_h为True时应判定为背景H"
    assert not _is_group_sex_background_h(21, is_h=False), "非玩家角色is_h为False时不应判定为背景H"

    # 3a3b. #2判据抽出的纯函数（v4新增，评审要求）：_talk_decision顺序约束 + _is_tired_exit窄识别。
    #       二者都需要真实Script.Core.constant（白名单集合/行为id常量），与5b同理——不同cwd/PYTHONPATH下
    #       可能导入失败，失败时跳过并提示，不假报错。
    global _player_real_instruction_active, _template_dispatch_active
    try:
        import Script.Core.constant as constant

        whitelisted_behavior_id = next(iter(_talk_whitelist()))
    except Exception:
        constant = None
    if constant is not None:
        previous_real_active, previous_template_active = _player_real_instruction_active, _template_dispatch_active
        _player_real_instruction_active = False
        _template_dispatch_active = True
        try:
            assert (
                _talk_decision(21, whitelisted_behavior_id, "", is_h=True) == "buffer"
            ), "白名单必须先于黑名单判：character_id!=0、is_h=True（同时命中背景H黑名单）、行为id在白名单内时，仍应是buffer而非drop"
            assert _talk_decision(21, "不在白名单里的id", "", is_h=True) == "drop", "不在白名单内时，命中黑名单（模板派发窗口）应drop"
            _template_dispatch_active = False
            assert _talk_decision(21, "不在白名单里的id", "", is_h=True) == "drop", "命中背景H黑名单同样应drop"
            assert _talk_decision(21, "不在白名单里的id", "", is_h=False) == "pass", "未命中任何一档时兜底pass"
        finally:
            _player_real_instruction_active, _template_dispatch_active = previous_real_active, previous_template_active

        assert _is_tired_exit(constant.Behavior.GROUP_SEX_NPC_HP_0_END), "_is_tired_exit只应认这一个行为id"
        assert not _is_tired_exit(constant.Behavior.GROUP_SEX_PL_HP_0_END), "外观相近的其他结束态不应被误认成太累退出"
        assert not _is_tired_exit(constant.Behavior.GROUP_SEX_END), "正常结束群交不应被误认成太累退出"
        assert not _is_tired_exit(""), "空行为id不应被误认成太累退出"

        # 3a3d. 用户裁定1a/1b新增的"波及全体"判据（_mass_end_behavior_family/_mass_toy_behavior_family/
        #       _is_mass_instruction/_is_mass_end_release_source），同样依赖真实Script.Core.constant。
        Behavior = constant.Behavior
        assert Behavior.GROUP_SEX_END in _mass_end_behavior_family(), "结束群交自身应在结束族内"
        assert Behavior.GROUP_SEX_NPC_HP_0_END in _mass_end_behavior_family(), "NPC太累退出应在结束族内（供#4排除is_player_real）"
        assert Behavior.GROUP_SEX_PL_HP_0_END in _mass_end_behavior_family(), "博士体力为零中断应在结束族内（经special_end_H_list并入）"
        assert Behavior.ORGASM_EDGE_OFF not in _mass_end_behavior_family(), "6014定向解放不属于结束族——定向单人指令应保持passthrough=True全程实时直显"
        for toy_behavior_id in (Behavior.REMOTE_ALL_TURN_OFF_SEX_TOY, Behavior.REMOTE_ALL_SET_SEX_TOY_WEAK, Behavior.REMOTE_ALL_SET_SEX_TOY_MEDIUM, Behavior.REMOTE_ALL_SET_SEX_TOY_STRONG):
            assert toy_behavior_id in _mass_toy_behavior_family(), f"{toy_behavior_id}应在全员玩具族内"
            assert _is_mass_instruction(toy_behavior_id), "全员玩具族成员应被_is_mass_instruction判定为波及全体指令"
        assert _is_mass_instruction(Behavior.GROUP_SEX_END), "结束族成员应被_is_mass_instruction判定为波及全体指令"
        assert not _is_mass_instruction(Behavior.ORGASM_EDGE_OFF), "6014不属于任一族，不应被误判为波及全体指令（否则会漏开#4的定向全显窗口）"
        assert _is_mass_end_release_source(Behavior.GROUP_SEX_END), "玩家实时behavior_id为group_sex_end时，批量解放应判定源自结束族（#5用户裁定1b核心判据）"
        assert _is_mass_end_release_source(Behavior.GROUP_SEX_PL_HP_0_END), "玩家实时behavior_id为群交时博士体力为零中断时，同样应判定源自结束族"
        assert not _is_mass_end_release_source(Behavior.ORGASM_EDGE_OFF), "玩家实时behavior_id为6014定向解放时，不应误判为批量结束链——保持定向解放passthrough=True"
    else:
        print("group_sex_summary._self_check: Script.Core不可导入，跳过3a3b/3a3d的_talk_decision/_is_tired_exit/_is_mass_instruction断言（不影响其余用例）")

    # 3a3c. #5入口判据的纯函数版本（v4新增）：_is_edge_release_event，覆盖两条release路径+失败后续路径
    assert _is_edge_release_event(2, {"v": 1}), "release_orgasm_edge_now自己触发的那次调用：edge==2且counts仍满编，应判定为真正的release/fail事件"
    assert not _is_edge_release_event(2, {}), "latch态下同turn内的后续普通绝顶结算：edge仍为2但counts已被清空，不应重复判定为新事件（此前老毛病会在此处误标release，覆盖掉更早的fail）"
    assert not _is_edge_release_event(2, {"v": 0, "c": 0}), "counts条目存在但全为0，同样不应判定为新事件"
    assert not _is_edge_release_event(1, {"v": 1}), "edge==1（寸止判定失败分支自己触发的那次调用，入口时仍是1，置2发生在call_original内部）不应判定为release事件，留给#9单独标记fail"

    # 3a4. _mark_edge_break_reason 优先级只升不降：累(tired) > 主动释放(release) > 判定失败(fail)
    edge_fail_passthrough.clear()
    _edge_break_reason.clear()
    _mark_edge_break_reason(21, "fail")
    assert _edge_break_reason[21] == "fail" and 21 in edge_fail_passthrough, "首次标记应直接生效并并入edge_fail_passthrough"
    _mark_edge_break_reason(21, "release")
    assert _edge_break_reason[21] == "release", "release优先级高于fail，应升级覆盖"
    _mark_edge_break_reason(21, "fail")
    assert _edge_break_reason[21] == "release", "fail优先级低于已有的release，不应降级覆盖"
    _mark_edge_break_reason(21, "tired")
    assert _edge_break_reason[21] == "tired", "tired优先级最高，应升级覆盖release"
    _mark_edge_break_reason(21, "release")
    assert _edge_break_reason[21] == "tired", "tired已是最高优先级，release不应降级覆盖"
    assert _edge_break_tag_and_style(21) == (" <累>", "little_dark_slate_blue"), "tired应显示<累>标记，样式为little_dark_slate_blue（与状态栏character_info_head.py:148-153一致，用户裁定2c）"
    _edge_break_reason[21] = "release"
    assert _edge_break_tag_and_style(21) == (" <寸止释放>", "gold_enrod"), "release应显示<寸止释放>，样式沿用gold_enrod"
    _edge_break_reason[21] = "fail"
    assert _edge_break_tag_and_style(21) == (" <寸止失败>", "gold_enrod"), "fail应显示<寸止失败>，样式沿用gold_enrod（与release同色不同字）"
    del _edge_break_reason[21]
    assert _edge_break_tag_and_style(21) == (" <寸止释放>", "gold_enrod"), "无_edge_break_reason条目时兜底按release处理，不报错"
    edge_fail_passthrough.clear()
    _edge_break_reason.clear()

    # 3a4b. _mark_edge_break_reason 的 passthrough 参数解耦（用户裁定1b/2a，v5新增）：reason记账（供摘要页
    #       显示）与是否并入edge_fail_passthrough（是否实时刷屏）是两件独立的事，不再必然同时发生。
    edge_fail_passthrough.clear()
    _edge_break_reason.clear()
    _mark_edge_break_reason(22, "tired", passthrough=False)
    assert _edge_break_reason[22] == "tired", "passthrough=False不影响reason记账，摘要页仍应显示<累>"
    assert 22 not in edge_fail_passthrough, "passthrough=False不应并入edge_fail_passthrough——批量结束链/tired标记默认不实时刷屏"
    _mark_edge_break_reason(22, "release", passthrough=True)
    assert 22 in edge_fail_passthrough, "同一角色后续若有passthrough=True的调用（如非批量结束的定向解放），仍应并入——两次调用的passthrough语义是并集，不因先前False而被锁死"
    assert _edge_break_reason[22] == "tired", "tired优先级最高，release不应降级覆盖reason（passthrough变化不影响优先级规则）"
    edge_fail_passthrough.clear()
    _edge_break_reason.clear()
    _mark_edge_break_reason(23, "release", passthrough=True)
    assert 23 in edge_fail_passthrough, "默认调用形式（不传passthrough）应等价于passthrough=True，保持v4既有行为不变（向后兼容）"
    edge_fail_passthrough.clear()
    _edge_break_reason.clear()

    # 3b. _build_edge_token 两个给定示例（均1次不带×N；单部位多次带×N）
    assert _build_edge_token({}) == ""
    assert _build_edge_token({"c": 1, "h": 1}) == "阴蒂、心理绝顶寸止"
    assert _build_edge_token({"v": 2}) == "阴道绝顶寸止×2"

    # 3c. "又高潮又寸止"矛盾显示的修复（真机QA缺陷3）：同一部位既进orgasm_record又进edge_record时，
    #     该部位归绝顶侧、不再重复列进寸止侧，整行标记改为<寸止释放>
    orgasm_record.clear()
    edge_record.clear()
    # 灰喉那一行的真实数据：5部位绝顶，其中阴蒂/阴道是"憋住后被解放"的
    orgasm_record[13] = {"m": 2, "h": 2, "c": 1, "v": 1, "a": 0}
    edge_record[13] = {"c": 1, "v": 1}
    released_parts, holding_parts = _split_edge_parts(13)
    assert released_parts == {"c": 1, "v": 1}, "阴蒂/阴道本turn真的高潮了，应判定为已解放"
    assert holding_parts == {}, "没有仍憋着的部位"
    assert _build_edge_token(holding_parts) == "", "已解放的部位不应再出现在寸止token里（否则与绝顶侧自相矛盾）"
    assert _edge_status_tag(13) == (" <寸止释放>", "gold_enrod"), "有部位憋住后被解放时应显示<寸止释放>，而非按憋着的三档报警度显示"
    # 注：解放是全角色一次性的，不存在"一个部位解放、另一个还憋着"的混合态——失败分支
    # (orgasm_settle.py:183-188)遍历全部supported_orgasm_list把所有held_count>0的部位一起并入释放，
    # release_orgasm_edge_now(:347)则直接把整个orgasm_edge_count当un_count_orgasm_dict重新结算，
    # 两条路径都是全放。故正常游玩下released与holding必有一个为空，不为不可达的混合态写用例。
    # 寸止判定失败：上游不写{部位}_orgasm_edge，edge_record里一条记录都没有，只能靠_edge_break_reason认
    # （v5起判据从edge_fail_passthrough改成_edge_break_reason，见_split_edge_parts/_edge_status_tag文档，
    # 这里改用_mark_edge_break_reason模拟#9标记fail的真实调用路径，而非直接摆弄旧的edge_fail_passthrough）
    orgasm_record.clear()
    edge_record.clear()
    edge_fail_passthrough.clear()
    _edge_break_reason.clear()
    orgasm_record[14] = {"v": 2, "c": 1}
    assert _edge_status_tag(14) == ("", ""), "没寸止过的纯高潮角色不该有任何寸止标记"
    _mark_edge_break_reason(14, "fail")
    assert _edge_status_tag(14) == (" <寸止失败>", "gold_enrod"), "寸止失败的角色即使edge_record为空也必须显示<寸止失败>"
    _mark_edge_break_reason(14, "tired")
    assert _edge_status_tag(14) == (" <累>", "little_dark_slate_blue"), "标为tired后_edge_status_tag应通过_edge_break_tag_and_style走<累>分支（QA真机缺陷：太累退出H被误标<寸止释放>）"
    _edge_break_reason.clear()
    assert _split_edge_parts(14) == ({}, {}), "edge_record为空时两侧都为空，不会凭空列出寸止部位"
    edge_record[14] = {"v": 1}
    assert _split_edge_parts(14) == ({"v": 1}, {}), "失败前已寸止成功过的部位也一并算已解放，不能留在憋着侧"
    edge_fail_passthrough.clear()
    orgasm_record.clear()
    edge_record.clear()
    # 纯憋着（无任何部位高潮）仍走原状态栏三档，不被本次改动影响
    orgasm_record.clear()
    edge_record.clear()
    edge_record[15] = {"v": 1}
    assert _split_edge_parts(15) == ({}, {"v": 1}), "没高潮过的部位应全部算作仍憋着"
    assert _edge_status_tag(15, skill_ability_lv=2, orgasm_edge_count={"v": 1}) == (" <寸止>", "hot_pink"), "纯憋着的角色仍走原三档，不应被<寸止释放>抢走"
    orgasm_record.clear()
    edge_record.clear()

    # 3d. 共用的寸止余量公式（摘要三档标记与#9"接近极限才放行提示"同源，见_edge_margin）
    assert _edge_margin(2, {"v": 1}) == 5, "2*3-1²=5"
    assert _edge_margin(1, {"v": 1, "c": 1}) == 1, "1*3-(1²+1²)=1"
    assert _edge_margin(0, {"v": 2}) == -4, "0*3-2²=-4"
    # #9的放行门是余量<=2：平淡的"成功寸止了X"隐去，"到极限了"/"随时可能释放"放行
    assert _edge_margin(2, {"v": 1}) > 2, "余量充裕时属于平淡成功，应继续隐去"
    assert _edge_margin(1, {"v": 1, "c": 1}) <= 2, "余量吃紧时应放行提示"
    assert _edge_margin(0, {"v": 2}) <= 2, "已超极限（余量为负）时必须放行提示"
    # 放行门(余量<=2)必须与状态栏带感叹号的两档完全重合：有感叹号则放行，无感叹号则不放行
    edge_record[11] = {"v": 1}
    for lv, count_dict in ((2, {"v": 1}), (1, {"v": 1, "c": 1}), (0, {"v": 2})):
        tag_text = _edge_status_tag(11, skill_ability_lv=lv, orgasm_edge_count=count_dict)[0]
        assert ("!" in tag_text) == (_edge_margin(lv, count_dict) <= 2), f"放行门与感叹号档位不一致：{tag_text}"
    edge_record.clear()

    # 4. 不在 _ORGASM_PART_ORDER 排序表内的部位不能从描述里丢掉，只是排到本档末尾
    desc = _build_orgasm_desc({"v": 2, "p": 2})
    assert "阴道" in desc and "p" in desc, "未知部位p应追加显示，而非被排序过滤丢弃"
    assert desc.startswith("双重绝顶："), "两个部位应计为双重绝顶（含未知部位），且冒号应为全角"

    # 5. QA真机缺陷复核（缺陷2：摘要页角色纳入条件；缺陷1：姓名style根因）
    orgasm_record.clear()
    edge_record.clear()
    orgasm_record[11] = {"v": 1}
    edge_record[12] = {"c": 1}
    orgasm_record[0] = {"v": 1}  # 防御性验证：即便记录里意外混入玩家id也不应列入摘要页
    assert _summary_row_character_ids() == [11, 12], "只有本turn确有绝顶/寸止记录的角色才应入摘要页，玩家id 0永不列入（即便记录里出现）"
    orgasm_record.clear()
    edge_record.clear()
    assert _summary_row_character_ids() == [], "本turn无人绝顶/寸止时摘要页角色列表应为空——不应因'仍在群交模板中'而画出只有姓名/冒号的空行（QA缺陷2）"

    # 5c. tired 无任何绝顶/寸止记录也必须单独成行（用户裁定2b，修复DESIGN.md记录的窄缺口：太累退出但本turn
    #     未曾寸止/绝顶过的角色，之前会被5的"无记录空跳过"语义连带漏掉，现在tired本身就是第三个纳入来源）。
    _edge_break_reason.clear()
    orgasm_record.clear()
    edge_record.clear()
    _mark_edge_break_reason(16, "tired", passthrough=False)
    assert _summary_row_character_ids() == [16], "太累退出但本turn无任何绝顶/寸止记录的角色，也必须单独成行显示<累>"
    _edge_break_reason.clear()
    assert _summary_row_character_ids() == [], "清空tired标记后（且无绝顶/寸止记录）应恢复为空——确认5的既有'无任何记录且无tired则整跳过'语义未被破坏"
    orgasm_record.clear()
    edge_record.clear()

    class _FakeCharacter:
        def __init__(self, name, text_color):
            self.name = name
            self.text_color = text_color

    assert _summary_name_style(_FakeCharacter("阿米娅", "")) == "standard", "无自定义颜色时应使用standard"
    assert _summary_name_style(_FakeCharacter("阿米娅", "#ff88aa")) == "阿米娅", "有自定义颜色时style必须是已注册的角色名tag，不能是text_color原始取值（未注册的tag会让该段静默不绘制，即QA缺陷1的根因）"

    # 5b. 摘要页锚点右对齐依赖的显示宽度计算：CJK按全角(2)计入，不能按len()的半角(1)计入，否则同一
    #     anchor_width下不同姓名的右对齐补齐量会算错，冒号锚点跟着漂移（RightDraw内部即调用get_text_index，
    #     本mod未自行重算宽度）。text_handle是真实Script.Core模块，与自检本身不依赖Script.*的设计不冲突时
    #     才断言——不同cwd/PYTHONPATH下可能导入失败（例如从scripts/子目录直接跑），失败时跳过并提示，不假报错。
    try:
        from Script.Core import text_handle
    except Exception:
        text_handle = None
    if text_handle is not None:
        assert text_handle.get_text_index("测试") == 4 and text_handle.get_text_index("测试") != len("测试"), "CJK文本的显示宽度须按get_text_index（全角=2）计算，不能用len()，否则右对齐锚点会算错"
    else:
        print("group_sex_summary._self_check: Script.Core不可导入，跳过5b的CJK显示宽度断言（不影响其余用例）")

    print("group_sex_summary._self_check 全部通过")


if __name__ == "__main__":
    _self_check()
