"""
H中被发现选择结算（hidden_sex_discovered）
==========================================
本模块提供「H中被发现」选择结算入口 resolve、模式邀请登记函数 on_invite，
以及提示标识 DISCOVERED_PROMPT_ID 与回调类型别名 InviteMode、Invite。
本模块不导入界面模块，仅在结束H分支调用时按需导入 handle_instruct。
"""

from collections.abc import Callable
from typing import Literal

from Script.Config import game_config
from Script.Core import constant, get_text
from Script.Design import handle_premise, instuct_judege, map_handle
from Script.Modules.domains import abilities, action_info, activity, flags
from Script.Modules.domains import identity
from Script.Modules.gameplay_resolution import achievement_service
from Script.Modules.gameplay_resolution import instruct_plan_service
from Script.Modules.gameplay_resolution import modal_hooks, plan_queue
from Script.Modules.gameplay_resolution import ui_hooks
from Script.Protocol.modal_prompts import ChoiceOption, ChoicePrompt

_ = get_text._
""" 文本翻译函数，指向 get_text._。 """
DISCOVERED_PROMPT_ID = "sex_be_discovered"
""" 「H中被发现」选择使用的 ChoicePrompt 标识（"sex_be_discovered"）。 """
type InviteMode = Literal["hidden", "exhibitionism"]
""" 模式邀请回调接收的目标模式字面量类型别名（"hidden" 或 "exhibitionism"）。 """
type Invite = Callable[[InviteMode], bool]
""" 模式邀请回调函数类型别名，接收 InviteMode 并在邀请失败时返回 True。 """


def _unregistered(mode: InviteMode) -> bool:
    """
    未登记模式邀请回调时的默认槽位函数，直接抛出 RuntimeError。
    Keyword arguments:
    mode -- InviteMode，请求的模式邀请类型（"hidden" 或 "exhibitionism"）
    Return arguments:
    bool -- 不正常返回，直接抛出 RuntimeError
    """
    raise RuntimeError(f"no invite handler for {mode}")


_invite: Invite = _unregistered
""" 当前生效的模式邀请回调槽位，默认为 _unregistered。 """


def on_invite(fn: Invite) -> Invite:
    """
    登记模式邀请回调槽位的处理函数，可作为装饰器使用。
    每次调用均会覆盖当前槽位中的处理函数。
    Keyword arguments:
    fn -- Invite，处理模式邀请并在邀请失败时返回 True 的回调函数
    Return arguments:
    Invite -- 原样返回传入的 fn
    """
    global _invite
    _invite = fn
    return fn


def resolve(discoverer_id: int, from_hidden_sex_flag: bool) -> None:
    """
    结算「H中被发现」选择流程并执行所选分支。
    先经 _h_target 确定当前H对象并组装提示正文，再写入主角的 h_interrupt_chara_name
    以及发现者的 npc_masturebate_for_player、交互目标与 see_pl_h。
    随后经 modal_hooks.ask 发起 DISCOVERED_PROMPT_ID 选项提示，按应答执行对应分支，
    分支返回后经 ui_hooks.switch_panel 切回 IN_SCENE。
    未登记选择处理器时，modal_hooks.ask 抛出 RuntimeError。
    Keyword arguments:
    discoverer_id -- int，发现者的角色编号
    from_hidden_sex_flag -- bool，本次是否由隐奸被发现触发
    Return arguments:
    None -- 无返回值
    """
    target_id = _h_target()
    finder_name = identity.of(discoverer_id).name
    text = _("\n{0}发现了{1}，要怎么做？\n").format(
        finder_name,
        _situation(identity.of(target_id).name, from_hidden_sex_flag),
    )
    activity.update_behavior(0, h_interrupt_chara_name=finder_name)
    flags.set(discoverer_id, npc_masturebate_for_player=False)
    activity.set_target(discoverer_id, 0)
    flags.set(discoverer_id, see_pl_h=True)
    prompt = ChoicePrompt(
        DISCOVERED_PROMPT_ID,
        _options(from_hidden_sex_flag),
        text=text,
        title=_("H中被发现"),
    )
    match modal_hooks.ask(prompt).selected_option_id:
        case "1":
            _talk_away(discoverer_id, target_id)
        case "2":
            _switch_to_hidden_sex(discoverer_id, target_id)
        case "3":
            _continue_exhibitionism_sex(discoverer_id, target_id)
        case "4":
            _invite_to_group_sex(discoverer_id, target_id)
        case "5":
            _end_current_h(discoverer_id, target_id)
    ui_hooks.switch_panel(constant.Panel.IN_SCENE)


def _h_target() -> int:
    """
    返回主角当前处于H状态的对象编号，必要时重设主角交互目标。
    主角当前目标处于H状态时直接返回其编号。
    否则遍历主角所在场景除自身外的角色，将首位处于H状态的角色设为目标并返回。
    若场景中无人处于H状态，则保留并返回原目标编号。
    Return arguments:
    int -- 确定的H对象角色编号
    """
    target_id = activity.target(0)
    if handle_premise.handle_self_is_h(target_id):
        return target_id
    for chara_id in map_handle.get_chara_now_scene_all_chara_id_list(
        0, remove_own_character=True
    ):
        if handle_premise.handle_self_is_h(chara_id):
            activity.set_target(0, chara_id)
            return chara_id
    return target_id


def _situation(target_name: str, from_hidden_sex_flag: bool) -> str:
    """
    按当前H状态优先级返回用于拼装发现提示正文的情境描述文本。
    优先级依次为隐奸（含 from_hidden_sex_flag）、露出、无意识H、对象逆推、群交与普通单独H。
    Keyword arguments:
    target_name -- str，H对象的角色名称
    from_hidden_sex_flag -- bool，本次是否由隐奸被发现触发
    Return arguments:
    str -- 填入对象名称后的情境描述译文
    """
    if handle_premise.handle_hidden_sex_mode_ge_1(0) or from_hidden_sex_flag:
        return _("你和{0}的隐奸").format(target_name)
    if handle_premise.handle_exhibitionism_sex_mode_ge_1(0):
        return _("你和{0}的露出").format(target_name)
    if handle_premise.handle_is_unconscious_h(0):
        return _("你正在无意识奸{0}").format(target_name)
    if handle_premise.handle_t_npc_active_h(0):
        return _("{0}正在逆推你").format(target_name)
    if handle_premise.handle_group_sex_mode_on(0):
        return _("你正在和{0}等多人群交").format(target_name)
    return _("你正在和{0}单独H").format(target_name)


def _options(from_hidden_sex_flag: bool) -> tuple[ChoiceOption, ...]:
    """
    按主角当前的隐奸、露出与群交状态构造「H中被发现」提示的 ChoiceOption 元组。
    选项 "1"、"4"、"5" 始终提供，全部选项的可用状态均为 "open"。
    非隐奸、非群交且 from_hidden_sex_flag 为假时提供选项 "2"。
    非露出且非群交时选项 "3" 为转为露出，处于露出模式时选项 "3" 为无视对方，其余情况不提供。
    Keyword arguments:
    from_hidden_sex_flag -- bool，本次是否由隐奸被发现触发
    Return arguments:
    tuple[ChoiceOption, ...] -- 按选项编号顺序排列的选项元组
    """
    hidden = handle_premise.handle_hidden_sex_mode_ge_1(0)
    exhibitionism = handle_premise.handle_exhibitionism_sex_mode_ge_1(0)
    group = handle_premise.handle_group_sex_mode_on(0)
    options = [ChoiceOption("1", _("[1]用花言巧语支开对方"))]
    if not hidden and not group and not from_hidden_sex_flag:
        options.append(ChoiceOption("2", _("[2]迅速地隐藏起来，转为隐奸")))
    if not exhibitionism and not group:
        options.append(ChoiceOption("3", _("[3]光明正大地展示，转为露出")))
    elif exhibitionism:
        options.append(ChoiceOption("3", _("[3]无视对方，正常继续")))
    options.append(ChoiceOption("4", _("[4]邀请对方加入群交")))
    options.append(ChoiceOption("5", _("[5]尴尬地结束H")))
    return tuple(options)


def _talk_away(discoverer_id: int, target_id: int) -> None:
    """
    结算选项 "1"（用花言巧语支开对方）。
    发现者拥有 222 号素质时直接以糊弄文本通过。
    否则以 _("目击H后被话术支开") 判定，通过时提示文本为空串，未通过时转入 _end_current_h。
    通过后经 ui_hooks.emit_notice 发出提示，并为发现者排入 SEE_H_BUT_DECEIVED 反应。
    Keyword arguments:
    discoverer_id -- int，发现者的角色编号
    target_id -- int，当前H对象的角色编号
    Return arguments:
    None -- 无返回值
    """
    if abilities.talent(discoverer_id)[222]:
        text = _("{0}还不懂这是什么意义，被你随口糊弄走了\n").format(
            identity.of(discoverer_id).name
        )
    elif instuct_judege.calculation_instuct_judege(
        0, discoverer_id, _("目击H后被话术支开")
    )[0]:
        text = ""
    else:
        _end_current_h(discoverer_id, target_id)
        return
    ui_hooks.emit_notice(text)
    _plan_reaction(discoverer_id, constant.Behavior.SEE_H_BUT_DECEIVED)


def _switch_to_hidden_sex(discoverer_id: int, target_id: int) -> None:
    """
    结算选项 "2"（转为隐奸）。
    调用 _invite("hidden")，未登记邀请回调时抛出 RuntimeError。
    邀请返回失败（True）时转入 _end_current_h。
    否则若主角的 hidden_sex_mode 为 1，则触发 914 号成就判定。
    Keyword arguments:
    discoverer_id -- int，发现者的角色编号
    target_id -- int，当前H对象的角色编号
    Return arguments:
    None -- 无返回值
    """
    if _invite("hidden"):
        _end_current_h(discoverer_id, target_id)
    elif flags.get(0, "hidden_sex_mode") == 1:
        achievement_service.get_achievement_judge_by_value(914, 1)


def _continue_exhibitionism_sex(discoverer_id: int, target_id: int) -> None:
    """
    结算选项 "3"（转为露出或无视对方继续）。
    未处于露出模式时调用 _invite("exhibitionism")，未登记时抛出 RuntimeError。
    邀请失败时转入 _end_current_h，否则触发 934 号成就判定。
    已处于露出模式时依次判定 _("露出") 与 _("H模式")，分别排入 SEE_H_BUT_IGNORE 或
    SEE_H_AND_LEAVE，均未通过时转入 _end_current_h。
    Keyword arguments:
    discoverer_id -- int，发现者的角色编号
    target_id -- int，当前H对象的角色编号
    Return arguments:
    None -- 无返回值
    """
    if not handle_premise.handle_exhibitionism_sex_mode_ge_1(0):
        if _invite("exhibitionism"):
            _end_current_h(discoverer_id, target_id)
        else:
            achievement_service.get_achievement_judge_by_value(934, 1)
    elif instuct_judege.calculation_instuct_judege(0, discoverer_id, _("露出"))[
        0
    ]:
        _plan_reaction(discoverer_id, constant.Behavior.SEE_H_BUT_IGNORE)
    elif instuct_judege.calculation_instuct_judege(
        0, discoverer_id, _("H模式")
    )[0]:
        _plan_reaction(discoverer_id, constant.Behavior.SEE_H_AND_LEAVE)
    else:
        _end_current_h(discoverer_id, target_id)


def _invite_to_group_sex(discoverer_id: int, target_id: int) -> None:
    """
    结算选项 "4"（邀请对方加入群交）。
    发现者通过群交判定且未力竭、疲劳或重度困倦时，已在群交中则排入 JOIN_GROUP_SEX。
    未在群交中则排入 DISCOVER_OTHER_SEX_AND_JOIN，为主角排入
    OTHER_SEX_BE_FOUND_TO_GROUP_SEX 并触发 905 号成就判定。
    否则已在群交中时排入 REFUSE_JOIN_GROUP_SEX，未在群交中则转入 _end_current_h。
    Keyword arguments:
    discoverer_id -- int，发现者的角色编号
    target_id -- int，当前H对象的角色编号
    Return arguments:
    None -- 无返回值
    """
    if handle_premise.handle_instruct_judge_group_sex(
        discoverer_id
    ) and not handle_premise.handle_self_exhausted(discoverer_id):
        if handle_premise.handle_group_sex_mode_on(0):
            _plan_reaction(discoverer_id, constant.Behavior.JOIN_GROUP_SEX)
        else:
            _plan_reaction(
                discoverer_id, constant.Behavior.DISCOVER_OTHER_SEX_AND_JOIN
            )
            instruct_plan_service.plan_instruct_common_settle(
                constant.Behavior.OTHER_SEX_BE_FOUND_TO_GROUP_SEX
            )
            achievement_service.get_achievement_judge_by_value(905, 1)
    elif handle_premise.handle_group_sex_mode_on(0):
        _plan_reaction(discoverer_id, constant.Behavior.REFUSE_JOIN_GROUP_SEX)
    else:
        _end_current_h(discoverer_id, target_id)


def _end_current_h(discoverer_id: int, target_id: int) -> None:
    """
    结算选项 "5" 及各失败分支共用的结束当前H流程。
    在调用时按需导入 handle_instruct，将对象的 h_interrupt 设为 1，
    并为发现者排入 SEE_H_AND_INTERRUPT。
    随后在群交模式下调用 plan_group_sex_end(GROUP_SEX_END)，
    否则调用 plan_h_end(H_INTERRUPT)。
    Keyword arguments:
    discoverer_id -- int，发现者的角色编号
    target_id -- int，当前H对象的角色编号
    Return arguments:
    None -- 无返回值
    """
    from Script.System.Instruct_System import handle_instruct

    action_info.set(target_id, "h_interrupt", 1)
    _plan_reaction(discoverer_id, constant.Behavior.SEE_H_AND_INTERRUPT)
    if handle_premise.handle_group_sex_mode_on(0):
        handle_instruct.plan_group_sex_end(constant.Behavior.GROUP_SEX_END)
    else:
        handle_instruct.plan_h_end(constant.Behavior.H_INTERRUPT)


def _plan_reaction(discoverer_id: int, behavior_id: str) -> None:
    """
    按行为配置时长将发现者的反应行为排入计划队列，并请求打断其当前行动。
    Keyword arguments:
    discoverer_id -- int，发现者的角色编号
    behavior_id -- str，要排入的行为编号
    Return arguments:
    None -- 无返回值
    """
    plan_queue.plan_next(
        discoverer_id,
        behavior_id,
        game_config.config_behavior[behavior_id].duration,
        interrupt=True,
    )
