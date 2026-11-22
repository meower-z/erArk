"""源石技艺相关的前提处理函数"""

from types import FunctionType
from Script.Core import constant_promise, get_text
from Script.Config import game_config
from Script.Design.handle_premise.premise_registry import add_premise
from Script.Modules.domains import abilities, activity, flags, hypnosis, modes
from Script.Modules.domains import player_ability
from Script.Modules.domains import identity

_: FunctionType = get_text._
""" 翻译api """


@add_premise(constant_promise.Premise.AT_LEAST_ONE_ARTS_ON)
def handle_at_least_one_arts_on(character_id: int) -> int:
    """
    至少有一种源石技艺开启中
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    # 催眠
    if handle_target_in_hypnosis(character_id):
        return 1
    # 透视
    if handle_penetrating_vision_on(character_id):
        return 1
    if handle_time_stop_on(character_id):
        return 1
    return 0


@add_premise(constant_promise.Premise.PRIMARY_HYPNOSIS)
def handle_primary_hypnosis(character_id: int) -> int:
    """
    自己拥有初级催眠
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return abilities.talent(character_id)[331]


@add_premise(constant_promise.Premise.INTERMEDIATE_HYPNOSIS)
def handle_intermediate_hypnosis(character_id: int) -> int:
    """
    自己拥有中级催眠
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return abilities.talent(character_id)[332]


@add_premise(constant_promise.Premise.ADVANCED_HYPNOSIS)
def handle_advanced_hypnosis(character_id: int) -> int:
    """
    自己拥有高级催眠
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return abilities.talent(character_id)[333]


@add_premise(constant_promise.Premise.SPECIAL_HYPNOSIS)
def handle_special_hypnosis(character_id: int) -> int:
    """
    自己拥有特级催眠
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return abilities.talent(character_id)[334]


@add_premise(constant_promise.Premise.SELF_HYPNOSIS_0)
def handle_self_hypnosis_0(character_id: int) -> int:
    """
    自己的被催眠程度为0%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    if hypnosis.of(character_id)["hypnosis_degree"] == 0:
        return 1
    return 0


@add_premise(constant_promise.Premise.SELF_HYPNOSIS_NE_0)
def handle_self_hypnosis_ne_0(character_id: int) -> int:
    """
    自己的被催眠程度不是0%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_self_hypnosis_0(character_id)


@add_premise(constant_promise.Premise.TARGET_HYPNOSIS_0)
def handle_target_hypnosis_0(character_id: int) -> int:
    """
    交互对象的被催眠程度为0%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return handle_self_hypnosis_0(activity.target(character_id))


@add_premise(constant_promise.Premise.TARGET_HYPNOSIS_NE_0)
def handle_target_hypnosis_ne_0(character_id: int) -> int:
    """
    交互对象的被催眠程度不是0%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_self_hypnosis_0(activity.target(character_id))


@add_premise(constant_promise.Premise.SELF_HAS_BEEN_HYPNOSIS)
def handle_self_has_been_hypnosis(character_id: int) -> int:
    """
    自己有至少一种被催眠素质
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    for cid in {71, 72, 73}:
        if abilities.talent(character_id)[cid]:
            return 1
    return 0


@add_premise(constant_promise.Premise.SELF_HAS_NOT_BEEN_HYPNOSIS)
def handle_self_has_not_been_hypnosis(character_id: int) -> int:
    """
    自己没有任何被催眠素质
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_self_has_been_hypnosis(character_id)


@add_premise(constant_promise.Premise.SELF_HAS_BEEN_PRIMARY_HYPNOSIS)
def handle_self_has_been_primary_hypnosis(character_id: int) -> int:
    """
    自己拥有被浅层催眠素质(50%)
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return abilities.talent(character_id)[71]


@add_premise(constant_promise.Premise.SELF_HAS_BEEN_DEEP_HYPNOSIS)
def handle_self_has_been_deep_hypnosis(character_id: int) -> int:
    """
    自己拥有被深层催眠素质(100%)
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return abilities.talent(character_id)[72]


@add_premise(constant_promise.Premise.SELF_HAS_BEEN_COMPLETE_HYPNOSIS)
def handle_self_has_been_complete_hypnosis(character_id: int) -> int:
    """
    自己拥有被完全催眠素质(200%)
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return abilities.talent(character_id)[73]


@add_premise(constant_promise.Premise.TARGET_HAS_BEEN_HYPNOSIS)
def handle_target_has_been_hypnosis(character_id: int) -> int:
    """
    交互对象有至少一种被催眠素质
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return handle_self_has_been_hypnosis(activity.target(character_id))


@add_premise(constant_promise.Premise.TARGET_HAS_NOT_BEEN_HYPNOSIS)
def handle_target_has_not_been_hypnosis(character_id: int) -> int:
    """
    交互对象没有任何被催眠素质
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_self_has_been_hypnosis(activity.target(character_id))


@add_premise(constant_promise.Premise.TARGET_HAS_BEEN_PRIMARY_HYPNOSIS)
def handle_target_has_been_primary_hypnosis(character_id: int) -> int:
    """
    交互对象拥有被浅层催眠素质(50%)
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return handle_self_has_been_primary_hypnosis(activity.target(character_id))


@add_premise(constant_promise.Premise.TARGET_HAS_BEEN_DEEP_HYPNOSIS)
def handle_target_has_been_deep_hypnosis(character_id: int) -> int:
    """
    交互对象拥有被深层催眠素质(100%)
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return handle_self_has_been_deep_hypnosis(activity.target(character_id))


@add_premise(constant_promise.Premise.TARGET_HAS_BEEN_COMPLETE_HYPNOSIS)
def handle_target_has_been_complete_hypnosis(character_id: int) -> int:
    """
    交互对象拥有被完全催眠素质(200%)
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return handle_self_has_been_complete_hypnosis(activity.target(character_id))


@add_premise(constant_promise.Premise.IN_HYPNOSIS)
def handle_in_hypnosis(character_id: int) -> int:
    """
    自己正在被催眠中
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    if flags.get(character_id, "unconscious_h") in [4, 5, 6, 7]:
        return 1
    return 0


@add_premise(constant_promise.Premise.NOT_IN_HYPNOSIS)
def handle_not_in_hypnosis(character_id: int) -> int:
    """
    自己没有正在被催眠
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    if flags.get(character_id, "unconscious_h") in [4, 5, 6, 7]:
        return 0
    return 1


@add_premise(constant_promise.Premise.TARGET_IN_HYPNOSIS)
def handle_target_in_hypnosis(character_id: int) -> int:
    """
    交互对象正在被催眠中
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if flags.get(target_data.cid, "unconscious_h") in [4, 5, 6, 7]:
        return 1
    return 0


@add_premise(constant_promise.Premise.TARGET_NOT_IN_HYPNOSIS)
def handle_target_not_in_hypnosis(character_id: int) -> int:
    """
    交互对象没有正在被催眠
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_data: identity.Identity = identity.of(activity.target(character_id))
    if flags.get(target_data.cid, "unconscious_h") in [4, 5, 6, 7]:
        return 0
    return 1


@add_premise(constant_promise.Premise.PRIMARY_PENETRATING_VISION)
def handle_primary_penetrating_vision(character_id: int) -> int:
    """
    拥有初级透视
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return abilities.talent(character_id)[307]


@add_premise(constant_promise.Premise.INTERMEDIATE_PENETRATING_VISION)
def handle_intermediate_penetrating_vision(character_id: int) -> int:
    """
    拥有中级透视
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return abilities.talent(character_id)[308]


@add_premise(constant_promise.Premise.ADVANCED_PENETRATING_VISION)
def handle_advanced_penetrating_vision(character_id: int) -> int:
    """
    拥有高级透视
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return abilities.talent(character_id)[309]


@add_premise(constant_promise.Premise.PENETRATING_VISION_ON)
def handle_penetrating_vision_on(character_id: int) -> int:
    """
    透视开启中
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return player_ability.get(character_id, "visual")


@add_premise(constant_promise.Premise.PENETRATING_VISION_OFF)
def handle_penetrating_vision_off(character_id: int) -> int:
    """
    透视关闭中
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not player_ability.get(character_id, "visual")


@add_premise(constant_promise.Premise.PRIMARY_HORMONE)
def handle_primary_hormone(character_id: int) -> int:
    """
    拥有初级信息素
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return abilities.talent(character_id)[304]


@add_premise(constant_promise.Premise.INTERMEDIATE_HORMONE)
def handle_intermediate_hormone(character_id: int) -> int:
    """
    拥有中级信息素
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return abilities.talent(character_id)[305]


@add_premise(constant_promise.Premise.ADVANCED_HORMONE)
def handle_advanced_hormone(character_id: int) -> int:
    """
    拥有高级信息素
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return abilities.talent(character_id)[306]


@add_premise(constant_promise.Premise.HORMONE_ON)
def handle_hormone_on(character_id: int) -> int:
    """
    信息素开启中
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return player_ability.get(character_id, "hormone")


@add_premise(constant_promise.Premise.HORMONE_OFF)
def handle_hormone_off(character_id: int) -> int:
    """
    信息素关闭中
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not player_ability.get(character_id, "hormone")


@add_premise(constant_promise.Premise.PRIMARY_TELEKINESIS)
def handle_primary_telekinesis(character_id: int) -> int:
    """
    拥有初级隔空肢体
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return abilities.talent(character_id)[310]


@add_premise(constant_promise.Premise.INTERMEDIATE_TELEKINESIS)
def handle_intermediate_telekinesis(character_id: int) -> int:
    """
    拥有中级隔空肢体
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return abilities.talent(character_id)[311]


@add_premise(constant_promise.Premise.ADVANCED_TELEKINESIS)
def handle_advanced_telekinesis(character_id: int) -> int:
    """
    拥有高级隔空肢体
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return abilities.talent(character_id)[312]


@add_premise(constant_promise.Premise.HYPNOSIS_INCREASE_BODY_SENSITIVITY)
def handle_hypnosis_increase_body_sensitivity(character_id: int) -> int:
    """
    自己被体控-敏感度提升
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    character_data: identity.Identity = identity.of(character_id)
    return hypnosis.of(character_data.cid)["increase_body_sensitivity"]


@add_premise(constant_promise.Premise.NOT_HYPNOSIS_INCREASE_BODY_SENSITIVITY)
def handle_not_hypnosis_increase_body_sensitivity(character_id: int) -> int:
    """
    自己未被体控-敏感度提升
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_hypnosis_increase_body_sensitivity(character_id)


@add_premise(constant_promise.Premise.TARGET_HYPNOSIS_INCREASE_BODY_SENSITIVITY)
def handle_target_hypnosis_increase_body_sensitivity(character_id: int) -> int:
    """
    交互对象被体控-敏感度提升
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return handle_hypnosis_increase_body_sensitivity(
        activity.target(character_id)
    )


@add_premise(
    constant_promise.Premise.TARGET_NOT_HYPNOSIS_INCREASE_BODY_SENSITIVITY
)
def handle_target_not_hypnosis_increase_body_sensitivity(
    character_id: int,
) -> int:
    """
    交互对象未被体控-敏感度提升
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_hypnosis_increase_body_sensitivity(
        activity.target(character_id)
    )


@add_premise(constant_promise.Premise.HYPNOSIS_FORCE_OVULATION)
def handle_hypnosis_force_ovulation(character_id: int) -> int:
    """
    自己被体控-强制排卵
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    character_data: identity.Identity = identity.of(character_id)
    return hypnosis.of(character_data.cid)["force_ovulation"]


@add_premise(constant_promise.Premise.NOT_HYPNOSIS_FORCE_OVULATION)
def handle_not_hypnosis_force_ovulation(character_id: int) -> int:
    """
    自己未被体控-强制排卵
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_hypnosis_force_ovulation(character_id)


@add_premise(constant_promise.Premise.TARGET_HYPNOSIS_FORCE_OVULATION)
def handle_target_hypnosis_force_ovulation(character_id: int) -> int:
    """
    交互对象被体控-强制排卵
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return handle_hypnosis_force_ovulation(activity.target(character_id))


@add_premise(constant_promise.Premise.TARGET_NOT_HYPNOSIS_FORCE_OVULATION)
def handle_target_not_hypnosis_force_ovulation(character_id: int) -> int:
    """
    交互对象未被体控-强制排卵
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_hypnosis_force_ovulation(activity.target(character_id))


@add_premise(constant_promise.Premise.HYPNOSIS_BLOCKHEAD)
def handle_hypnosis_blockhead(character_id: int) -> int:
    """
    自己被体控-木头人
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    character_data: identity.Identity = identity.of(character_id)
    return hypnosis.of(character_data.cid)["blockhead"]


@add_premise(constant_promise.Premise.NOT_HYPNOSIS_BLOCKHEAD)
def handle_not_hypnosis_blockhead(character_id: int) -> int:
    """
    自己未被体控-木头人
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_hypnosis_blockhead(character_id)


@add_premise(constant_promise.Premise.TARGET_HYPNOSIS_BLOCKHEAD)
def handle_target_hypnosis_blockhead(character_id: int) -> int:
    """
    交互对象被体控-木头人
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return handle_hypnosis_blockhead(activity.target(character_id))


@add_premise(constant_promise.Premise.TARGET_NOT_HYPNOSIS_BLOCKHEAD)
def handle_target_not_hypnosis_blockhead(character_id: int) -> int:
    """
    交互对象未被体控-木头人
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_hypnosis_blockhead(activity.target(character_id))


@add_premise(constant_promise.Premise.HYPNOSIS_ACTIVE_H)
def handle_hypnosis_active_h(character_id: int) -> int:
    """
    自己被体控-逆推
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    character_data: identity.Identity = identity.of(character_id)
    return hypnosis.of(character_data.cid)["active_h"]


@add_premise(constant_promise.Premise.NOT_HYPNOSIS_ACTIVE_H)
def handle_not_hypnosis_active_h(character_id: int) -> int:
    """
    自己未被体控-逆推
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_hypnosis_active_h(character_id)


@add_premise(constant_promise.Premise.TARGET_HYPNOSIS_ACTIVE_H)
def handle_target_hypnosis_active_h(character_id: int) -> int:
    """
    交互对象被体控-逆推
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return handle_hypnosis_active_h(activity.target(character_id))


@add_premise(constant_promise.Premise.TARGET_NOT_HYPNOSIS_ACTIVE_H)
def handle_target_not_hypnosis_active_h(character_id: int) -> int:
    """
    交互对象未被体控-逆推
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_hypnosis_active_h(activity.target(character_id))


@add_premise(constant_promise.Premise.HYPNOSIS_ROLEPLAY)
def handle_hypnosis_roleplay(character_id: int) -> int:
    """
    自己被心控-角色扮演
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    character_data: identity.Identity = identity.of(character_id)
    return len(hypnosis.of(character_data.cid)["roleplay"])


@add_premise(constant_promise.Premise.NOT_HYPNOSIS_ROLEPLAY)
def handle_not_hypnosis_roleplay(character_id: int) -> int:
    """
    自己未被心控-角色扮演
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_hypnosis_roleplay(character_id)


@add_premise(constant_promise.Premise.TARGET_HYPNOSIS_ROLEPLAY)
def handle_target_hypnosis_roleplay(character_id: int) -> int:
    """
    交互对象被心控-角色扮演
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return handle_hypnosis_roleplay(activity.target(character_id))


@add_premise(constant_promise.Premise.TARGET_NOT_HYPNOSIS_ROLEPLAY)
def handle_target_not_hypnosis_roleplay(character_id: int) -> int:
    """
    交互对象未被心控-角色扮演
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_hypnosis_roleplay(activity.target(character_id))


@add_premise(constant_promise.Premise.TARGET_HYPNOSIS_ROLEPLAY_1)
def handle_target_hypnosis_roleplay_1(character_id: int) -> int:
    """
    交互对象被心控-角色扮演-妻子
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_data = identity.of(activity.target(character_id))
    for cid in game_config.config_roleplay:
        roleplay_data = game_config.config_roleplay[cid]
        if (
            roleplay_data.name == _("妻子")
            and cid in hypnosis.of(target_data.cid)["roleplay"]
        ):
            return 1
    return 0


@add_premise(constant_promise.Premise.TARGET_HYPNOSIS_ROLEPLAY_2)
def handle_target_hypnosis_roleplay_2(character_id: int) -> int:
    """
    交互对象被心控-角色扮演-妹妹
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_data = identity.of(activity.target(character_id))
    for cid in game_config.config_roleplay:
        roleplay_data = game_config.config_roleplay[cid]
        if (
            roleplay_data.name == _("妹妹")
            and cid in hypnosis.of(target_data.cid)["roleplay"]
        ):
            return 1
    return 0


@add_premise(constant_promise.Premise.TARGET_HYPNOSIS_ROLEPLAY_3)
def handle_target_hypnosis_roleplay_3(character_id: int) -> int:
    """
    交互对象被心控-角色扮演-女儿
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_data = identity.of(activity.target(character_id))
    for cid in game_config.config_roleplay:
        roleplay_data = game_config.config_roleplay[cid]
        if (
            roleplay_data.name == _("女儿")
            and cid in hypnosis.of(target_data.cid)["roleplay"]
        ):
            return 1
    return 0


@add_premise(constant_promise.Premise.TARGET_HYPNOSIS_ROLEPLAY_4)
def handle_target_hypnosis_roleplay_4(character_id: int) -> int:
    """
    交互对象被心控-角色扮演-女仆
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_data = identity.of(activity.target(character_id))
    for cid in game_config.config_roleplay:
        roleplay_data = game_config.config_roleplay[cid]
        if (
            roleplay_data.name == _("女仆")
            and cid in hypnosis.of(target_data.cid)["roleplay"]
        ):
            return 1
    return 0


@add_premise(constant_promise.Premise.TARGET_HYPNOSIS_ROLEPLAY_5)
def handle_target_hypnosis_roleplay_5(character_id: int) -> int:
    """
    交互对象被心控-角色扮演-宠物猫
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_data = identity.of(activity.target(character_id))
    for cid in game_config.config_roleplay:
        roleplay_data = game_config.config_roleplay[cid]
        if (
            roleplay_data.name == _("宠物猫")
            and cid in hypnosis.of(target_data.cid)["roleplay"]
        ):
            return 1
    return 0


@add_premise(constant_promise.Premise.TARGET_HYPNOSIS_ROLEPLAY_6)
def handle_target_hypnosis_roleplay_6(character_id: int) -> int:
    """
    交互对象被心控-角色扮演-宠物狗
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_data = identity.of(activity.target(character_id))
    for cid in game_config.config_roleplay:
        roleplay_data = game_config.config_roleplay[cid]
        if (
            roleplay_data.name == _("宠物狗")
            and cid in hypnosis.of(target_data.cid)["roleplay"]
        ):
            return 1
    return 0


@add_premise(constant_promise.Premise.HYPNOSIS_PAIN_AS_PLEASURE)
def handle_hypnosis_pain_as_pleasure(character_id: int) -> int:
    """
    自己被心控-苦痛快感化
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    character_data: identity.Identity = identity.of(character_id)
    return hypnosis.of(character_data.cid)["pain_as_pleasure"]


@add_premise(constant_promise.Premise.NOT_HYPNOSIS_PAIN_AS_PLEASURE)
def handle_not_hypnosis_pain_as_pleasure(character_id: int) -> int:
    """
    自己未被心控-苦痛快感化
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_hypnosis_pain_as_pleasure(character_id)


@add_premise(constant_promise.Premise.TARGET_HYPNOSIS_PAIN_AS_PLEASURE)
def handle_t_hypnosis_pain_as_pleasure(character_id: int) -> int:
    """
    交互对象被心控-苦痛快感化
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return handle_hypnosis_pain_as_pleasure(activity.target(character_id))


@add_premise(constant_promise.Premise.TARGET_NOT_HYPNOSIS_PAIN_AS_PLEASURE)
def handle_t_not_hypnosis_pain_as_pleasure(character_id: int) -> int:
    """
    交互对象未被心控-苦痛快感化
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_hypnosis_pain_as_pleasure(activity.target(character_id))


@add_premise(constant_promise.Premise.PRIMARY_TIME_STOP)
def handle_primary_time_stop(character_id: int) -> int:
    """
    自己拥有初级时停
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    if abilities.talent(character_id)[316]:
        return 1
    return 0


@add_premise(constant_promise.Premise.INTERMEDIATE_TIME_STOP)
def handle_intermediate_time_stop(character_id: int) -> int:
    """
    自己拥有中级时停
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    if abilities.talent(character_id)[317]:
        return 1
    return 0


@add_premise(constant_promise.Premise.ADVANCED_TIME_STOP)
def handle_advanced_time_stop(character_id: int) -> int:
    """
    自己拥有高级时停
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    if abilities.talent(character_id)[318]:
        return 1
    return 0


@add_premise(constant_promise.Premise.TIME_STOP_ON)
def handle_time_stop_on(character_id: int) -> int:
    """
    时停开启中
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return modes.time_stop()


@add_premise(constant_promise.Premise.TIME_STOP_OFF)
def handle_time_stop_off(character_id: int) -> int:
    """
    时停关闭中
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_time_stop_on(character_id)


@add_premise(constant_promise.Premise.TIME_STOP_JUDGE_FOR_MOVE)
def handle_time_stop_judge_for_move(character_id: int) -> int:
    """
    (移动用)未开启时停，或时停开启且有中级时停
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    if handle_time_stop_off(character_id):
        return 1
    else:
        if handle_intermediate_time_stop(character_id):
            return 1
    return 0


@add_premise(constant_promise.Premise.NOBODY_FREE_IN_TIME_STOP)
def handle_nobody_free_in_time_stop(character_id: int) -> int:
    """
    没有指定可以在时停中自由活动的干员
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    if player_ability.get(0, "free_in_time_stop_chara_id") > 0:
        return 0
    return 1


@add_premise(constant_promise.Premise.NOT_CARRY_ANYBODY_IN_TIME_STOP)
def handle_not_carry_anybody_in_time_stop(character_id: int) -> int:
    """
    没有在时停中搬运干员
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    if player_ability.get(0, "carry_chara_id_in_time_stop") > 0:
        return 0
    return 1


@add_premise(constant_promise.Premise.CARRY_SOMEBODY_IN_TIME_STOP)
def handle_carry_somebody_in_time_stop(character_id: int) -> int:
    """
    正在时停中搬运干员
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_not_carry_anybody_in_time_stop(character_id)


@add_premise(constant_promise.Premise.TARGET_IS_CARRIED_IN_TIME_STOP)
def handle_target_is_carried_in_time_stop(character_id: int) -> int:
    """
    交互对象是自己正在时停中搬运的干员
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    if player_ability.get(0, "carry_chara_id_in_time_stop") > 0:
        if activity.target(0) == player_ability.get(
            0, "carry_chara_id_in_time_stop"
        ):
            return 1
    return 0


@add_premise(constant_promise.Premise.SOMEBODY_FREE_IN_TIME_STOP)
def handle_somebody_free_in_time_stop(character_id: int) -> int:
    """
    玩家已指定可以在时停中自由活动的干员
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    if handle_nobody_free_in_time_stop(character_id):
        return 0
    return 1


@add_premise(constant_promise.Premise.SELF_FREE_IN_TIME_STOP)
def handle_self_free_in_time_stop(character_id: int) -> int:
    """
    自己是在时停中自由活动的干员
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    if character_id > 0 and character_id == player_ability.get(
        0, "free_in_time_stop_chara_id"
    ):
        return 1
    return 0


@add_premise(constant_promise.Premise.SELF_NOT_FREE_IN_TIME_STOP)
def handle_self_not_free_in_time_stop(character_id: int) -> int:
    """
    自己不是在时停中自由活动的干员
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    if handle_self_free_in_time_stop(character_id):
        return 0
    return 1


@add_premise(constant_promise.Premise.TARGET_FREE_IN_TIME_STOP)
def handle_target_free_in_time_stop(character_id: int) -> int:
    """
    交互对象是在时停中自由活动的干员
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    if handle_self_free_in_time_stop(activity.target(character_id)):
        return 1
    return 0


@add_premise(constant_promise.Premise.TARGET_NOT_FREE_IN_TIME_STOP)
def handle_target_not_free_in_time_stop(character_id: int) -> int:
    """
    交互对象不是在时停中自由活动的干员
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    if handle_self_free_in_time_stop(activity.target(character_id)):
        return 0
    return 1
