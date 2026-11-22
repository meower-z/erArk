"""基础数值相关的前提处理函数"""

from types import FunctionType
from Script.Core import (
    cache_control,
    constant_promise,
    game_type,
    get_text,
    num,
)
from Script.Design import attr_calculation
from Script.Design.handle_premise.premise_registry import add_premise
from Script.Modules.domains import activity, needs, pregnancy, identity

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
_: FunctionType = get_text._
""" 翻译api """


@add_premise(constant_promise.Premise.HP_G_1)
def handle_self_not_tired(character_id: int) -> int:
    """
    自身体力大于1
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return needs.of(character_id)["hit"] > 1


@add_premise(constant_promise.Premise.HP_LOW)
def handle_hp_low(character_id: int) -> int:
    """
    角色体力低于30%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    value = needs.of(character_id)["hit"] / needs.of(character_id)["hit_max"]
    if value < 0.3:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.HP_HIGH)
def handle_hp_high(character_id: int) -> int:
    """
    角色体力高于70%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    value = needs.of(character_id)["hit"] / needs.of(character_id)["hit_max"]
    if value > 0.7:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.HP_MAX)
def handle_hp_max(character_id: int) -> int:
    """
    角色自身体力等于100%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    value = needs.of(character_id)["hit"] / needs.of(character_id)["hit_max"]
    if value >= 1:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.MP_0)
def handle_mp_0(character_id: int) -> int:
    """
    角色气力为0
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    value = needs.of(character_id)["mana"]
    if value == 0:
        return_value = max(
            1, needs.of(character_id)["hit_max"] - needs.of(character_id)["hit"]
        )
        return num.whole(return_value)
    else:
        return 0


@add_premise(constant_promise.Premise.MP_LOW)
def handle_mp_low(character_id: int) -> int:
    """
    角色气力低于30%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    value = needs.of(character_id)["mana"] / needs.of(character_id)["mana_max"]
    if value < 0.3:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.MP_HIGH)
def handle_mp_high(character_id: int) -> int:
    """
    角色气力高于70%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    value = needs.of(character_id)["mana"] / needs.of(character_id)["mana_max"]
    if value > 0.7:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.MP_MAX)
def handle_mp_max(character_id: int) -> int:
    """
    自身气力等于100%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    value = needs.of(character_id)["mana"] / needs.of(character_id)["mana_max"]
    if value >= 1:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.HP_OR_MP_LOW)
def handle_hp_or_mp_low(character_id: int) -> int:
    """
    自身体力或气力有一项低于30%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    hp_value = needs.of(character_id)["hit"] / needs.of(character_id)["hit_max"]
    mp_value = (
        needs.of(character_id)["mana"] / needs.of(character_id)["mana_max"]
    )
    if hp_value < 0.3:
        return 1
    elif mp_value < 0.3:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.HP_OR_MP_GE_80)
def handle_hp_or_mp_ge_80(character_id: int) -> int:
    """
    自身体力或气力有一项低于80%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    hp_value = needs.of(character_id)["hit"] / needs.of(character_id)["hit_max"]
    mp_value = (
        needs.of(character_id)["mana"] / needs.of(character_id)["mana_max"]
    )
    if hp_value < 0.8:
        return 1
    elif mp_value < 0.8:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_HP_LOW)
def handle_target_hp_low(character_id: int) -> int:
    """
    交互对象体力低于30%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_data = identity.of(activity.target(character_id))
    value = (
        needs.of(target_data.cid)["hit"] / needs.of(target_data.cid)["hit_max"]
    )
    if value < 0.3:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_HP_HIGH)
def handle_target_hp_high(character_id: int) -> int:
    """
    交互对象体力高于70%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_data = identity.of(activity.target(character_id))
    value = (
        needs.of(target_data.cid)["hit"] / needs.of(target_data.cid)["hit_max"]
    )
    if value > 0.7:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_HP_NE_1)
def handle_target_hp_ne_1(character_id: int) -> int:
    """
    交互对象体力不等于1
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_data = identity.of(activity.target(character_id))
    if needs.of(target_data.cid)["hit"] > 1:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_MP_0)
def handle_target_mp_0(character_id: int) -> int:
    """
    交互对象气力为0
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_data = identity.of(activity.target(character_id))
    value = needs.of(target_data.cid)["mana"]
    if value == 0:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_MP_LOW)
def handle_target_mp_low(character_id: int) -> int:
    """
    交互对象气力低于30%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_data = identity.of(activity.target(character_id))
    value = (
        needs.of(target_data.cid)["mana"]
        / needs.of(target_data.cid)["mana_max"]
    )
    if value < 0.3:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_MP_HIGH)
def handle_target_mp_high(character_id: int) -> int:
    """
    交互对象气力高于70%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_data = identity.of(activity.target(character_id))
    value = (
        needs.of(target_data.cid)["mana"]
        / needs.of(target_data.cid)["mana_max"]
    )
    if value > 0.7:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.SELF_AND_TARGET_HP_GE_70)
def handle_self_and_target_hp_ge_70(character_id: int) -> int:
    """
    自身和交互对象体力都高于70%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_data = identity.of(activity.target(character_id))
    value1 = needs.of(character_id)["hit"] / needs.of(character_id)["hit_max"]
    value2 = (
        needs.of(target_data.cid)["hit"] / needs.of(target_data.cid)["hit_max"]
    )
    if value1 > 0.7 and value2 > 0.7:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_HP_OR_MP_LOW)
def handle_t_hp_or_mp_low(character_id: int) -> int:
    """
    交互对象体力或气力有一项低于30%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_data = identity.of(activity.target(character_id))
    value1 = (
        needs.of(target_data.cid)["hit"] / needs.of(target_data.cid)["hit_max"]
    )
    value2 = (
        needs.of(target_data.cid)["mana"]
        / needs.of(target_data.cid)["mana_max"]
    )
    if value1 < 0.3:
        return 1
    elif value2 < 0.3:
        return 1
    return 0


@add_premise(constant_promise.Premise.TIRED_LE_0)
def handle_tired_le_0(character_id: int) -> int:
    """
    疲劳条≤0%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(character_id)["tired"] / 160
    if value <= 0:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TIRED_GE_10)
def handle_tired_ge_10(character_id: int) -> int:
    """
    疲劳条≥10%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(character_id)["tired"] / 160
    if value >= 0.1:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TIRED_GE_50)
def handle_tired_ge_50(character_id: int) -> int:
    """
    疲劳条≥50%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(character_id)["tired"] / 160
    if value >= 0.5:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TIRED_LE_74)
def handle_tired_le_74(character_id: int) -> int:
    """
    疲劳条≤74%，全指令自由
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(character_id)["tired"] / 160
    if value <= 0.74:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TIRED_GE_75)
def handle_tired_ge_75(character_id: int) -> int:
    """
    疲劳条≥75%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(character_id)["tired"] / 160
    if value > 0.74:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TIRED_LE_84)
def handle_tired_le_84(character_id: int) -> int:
    """
    疲劳条≤84%，自由活动的极限
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(character_id)["tired"] / 160
    if value <= 0.84:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TIRED_GE_85)
def handle_tired_ge_85(character_id: int) -> int:
    """
    疲劳条≥85%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(character_id)["tired"] / 160
    if value > 0.84:
        return num.whole(needs.of(character_id)["tired"] * 5)
    else:
        return 0


@add_premise(constant_promise.Premise.TIRED_L_100)
def handle_tired_l_100(character_id: int) -> int:
    """
    疲劳条<100%，还不至于当场爆睡
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(character_id)["tired"] / 160
    if value < 1:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TIRED_100)
def handle_tired_100(character_id: int) -> int:
    """
    疲劳条100%，当场爆睡
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(character_id)["tired"] / 160
    if value >= 1:
        return num.whole(needs.of(character_id)["tired"] * 5)
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_TIRED_GE_50)
def handle_t_tired_ge_50(character_id: int) -> int:
    """
    交互对象疲劳条≥50%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(activity.target(character_id))["tired"] / 160
    if value >= 0.5:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_TIRED_LE_74)
def handle_t_tired_le_74(character_id: int) -> int:
    """
    交互对象疲劳条≤74%，全指令自由
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(activity.target(character_id))["tired"] / 160
    if value <= 0.74:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_TIRED_GE_75)
def handle_t_tired_ge_75(character_id: int) -> int:
    """
    交互对象疲劳条≥75%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(activity.target(character_id))["tired"] / 160
    if value > 0.74:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_TIRED_LE_84)
def handle_t_tired_le_84(character_id: int) -> int:
    """
    交互对象疲劳条≤84%，自由活动的极限
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(activity.target(character_id))["tired"] / 160
    if value <= 0.84:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_TIRED_GE_85)
def handle_t_tired_ge_85(character_id: int) -> int:
    """
    交互对象疲劳条≥85%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(activity.target(character_id))["tired"] / 160
    if value > 0.84:
        return num.whole(needs.of(activity.target(character_id))["tired"] * 5)
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_TIRED_100)
def handle_t_tired_100(character_id: int) -> int:
    """
    交互对象疲劳条100%，当场爆睡
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(activity.target(character_id))["tired"] / 160
    if value >= 1:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.URINATE_LE_12)
def handle_urinate_le_12(character_id: int) -> int:
    """
    尿意条≤12.5%，刚排空过
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(character_id)["urine"] / 240
    if value <= 0.125:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.URINATE_LE_49)
def handle_urinate_le_49(character_id: int) -> int:
    """
    尿意条≤49%，可以继续喝咖啡
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(character_id)["urine"] / 240
    if value <= 0.49:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.URINATE_LE_79)
def handle_urinate_le_79(character_id: int) -> int:
    """
    尿意条≤79%，不需要排尿
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(character_id)["urine"] / 240
    if value <= 0.79:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.URINATE_GE_80)
def handle_urinate_ge_80(character_id: int) -> int:
    """
    尿意条≥80%，需要排尿
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(character_id)["urine"] / 240
    if value > 0.79:
        extra_value = int(needs.of(character_id)["urine"] - 240 * 0.8)
        return extra_value * 5
    else:
        return 0


@add_premise(constant_promise.Premise.URINATE_GE_125)
def handle_urinate_ge_125(character_id: int) -> int:
    """
    尿意条≥150%，需要当场排尿
    之前设为125%，但出现失禁的频率过高，所以改为150%
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(character_id)["urine"] / 240
    if value >= 1.5:
        return num.whole(needs.of(character_id)["urine"] * 5)
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_URINATE_LE_49)
def handle_target_urinate_le_49(character_id: int) -> int:
    """
    交互对象尿意条≤49%，可以继续喝咖啡
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(activity.target(character_id))["urine"] / 240
    if value <= 0.49:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.PL_URINATE_LE_49)
def handle_pl_urinate_le_49(character_id: int) -> int:
    """
    玩家尿意条≤49%，可以继续喝咖啡
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(0)["urine"] / 240
    if value <= 0.49:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_URINATE_LE_79)
def handle_target_urinate_le_79(character_id: int) -> int:
    """
    交互对象尿意条≤79%，不需要排尿
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(activity.target(character_id))["urine"] / 240
    if value <= 0.79:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_URINATE_GE_80)
def handle_target_urinate_ge_80(character_id: int) -> int:
    """
    交互对象尿意条≥80%，需要排尿
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(activity.target(character_id))["urine"] / 240
    if value > 0.79:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.HUNGER_LE_20)
def handle_hunger_le_20(character_id: int) -> int:
    """
    饥饿值≤20%，很饱
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(character_id)["hunger"] / 240
    if value <= 0.20:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.HUNGER_LE_79)
def handle_hunger_le_79(character_id: int) -> int:
    """
    饥饿值≤79%，不需要吃饭
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(character_id)["hunger"] / 240
    if value <= 0.79:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.HUNGER_GE_80)
def handle_hunger_ge_80(character_id: int) -> float:
    """
    饥饿值≥80%，需要吃饭
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    float -- 权重
    """

    value = needs.of(character_id)["hunger"] / 240
    if value > 0.79:
        # print(f"debug {character_id}角色饿了")
        extra_value = needs.of(character_id)["hunger"] - 240 * 0.8
        return extra_value * 5
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_HUNGER_LE_79)
def handle_target_hunger_le_79(character_id: int) -> int:
    """
    交互对象饥饿值≤79%，不需要吃饭
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(activity.target(character_id))["hunger"] / 240
    if value <= 0.79:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_HUNGER_GE_80)
def handle_target_hunger_ge_80(character_id: int) -> int:
    """
    交互对象饥饿值≥80%，需要吃饭
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(activity.target(character_id))["hunger"] / 240
    if value > 0.79:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.MILK_LE_29)
def handle_milk_le_29(character_id: int) -> int:
    """
    奶量≤29%，无法挤奶
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(character_id)["milk"] / pregnancy.milk_max(character_id)
    if value <= 0.29:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.MILK_GE_30)
def handle_milk_ge_30(character_id: int) -> int:
    """
    奶量≥30%，可以挤奶
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(character_id)["milk"] / pregnancy.milk_max(character_id)
    if value > 0.29:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.MILK_LE_79)
def handle_milk_le_79(character_id: int) -> int:
    """
    奶量≤79%，未涨奶
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    value = needs.of(character_id)["milk"] / pregnancy.milk_max(character_id)
    if value <= 0.79:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.MILK_GE_80)
def handle_milk_ge_80(character_id: int) -> int:
    """
    奶量≥80%，涨奶
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    if needs.of(character_id)["milk"] == 0:
        return 0

    value = needs.of(character_id)["milk"] / pregnancy.milk_max(character_id)

    if value > 0.80:
        return num.whole(needs.of(character_id)["milk"])
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_MILK_LE_29)
def handle_target_milk_le_29(character_id: int) -> int:
    """
    交互对象奶量≤29%，无法挤奶
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_character_data: identity.Identity = identity.of(
        activity.target(character_id)
    )

    value = needs.of(target_character_data.cid)["milk"] / pregnancy.milk_max(
        target_character_data.cid
    )
    if value <= 0.29:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_MILK_GE_30)
def handle_target_milk_ge_30(character_id: int) -> int:
    """
    交互对象奶量≥30%，可以挤奶
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_character_data: identity.Identity = identity.of(
        activity.target(character_id)
    )

    value = needs.of(target_character_data.cid)["milk"] / pregnancy.milk_max(
        target_character_data.cid
    )
    if value > 0.29:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_MILK_LE_79)
def handle_target_milk_le_79(character_id: int) -> int:
    """
    交互对象奶量≤79%，未涨奶
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_character_data: identity.Identity = identity.of(
        activity.target(character_id)
    )

    value = needs.of(target_character_data.cid)["milk"] / pregnancy.milk_max(
        target_character_data.cid
    )
    if value <= 0.79:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_MILK_GE_80)
def handle_target_milk_ge_80(character_id: int) -> int:
    """
    交互对象奶量≥80%，涨奶
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_character_data: identity.Identity = identity.of(
        activity.target(character_id)
    )

    value = needs.of(target_character_data.cid)["milk"] / pregnancy.milk_max(
        target_character_data.cid
    )
    if value > 0.79:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.SLEEP_LEVEL_0)
def handle_sleep_level_0(character_id: int) -> int:
    """
    睡眠等级：半梦半醒
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    level, __ = attr_calculation.get_sleep_level(
        needs.of(character_id)["sleep"]
    )
    if level == 0:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.SLEEP_LEVEL_1)
def handle_sleep_level_1(character_id: int) -> int:
    """
    睡眠等级：浅睡
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    level, __ = attr_calculation.get_sleep_level(
        needs.of(character_id)["sleep"]
    )
    if level == 1:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.SLEEP_LEVEL_2)
def handle_sleep_level_2(character_id: int) -> int:
    """
    睡眠等级：熟睡
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    level, __ = attr_calculation.get_sleep_level(
        needs.of(character_id)["sleep"]
    )
    if level == 2:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.SLEEP_LEVEL_3)
def handle_sleep_level_3(character_id: int) -> int:
    """
    睡眠等级：完全深眠
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    level, __ = attr_calculation.get_sleep_level(
        needs.of(character_id)["sleep"]
    )
    if level == 3:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.SLEEP_LEVEL_GE_1)
def handle_sleep_level_ge_1(character_id: int) -> int:
    """
    睡眠等级≥1
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    level, __ = attr_calculation.get_sleep_level(
        needs.of(character_id)["sleep"]
    )
    if level >= 1:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.T_SLEEP_LEVEL_GE_1)
def handle_t_sleep_level_ge_1(character_id: int) -> int:
    """
    交互对象睡眠等级≥1
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return handle_sleep_level_ge_1(activity.target(character_id))


@add_premise(constant_promise.Premise.DRUNK_LEVEL_0)
def handle_drunk_level_0(character_id: int) -> int:
    """
    酒精等级：清醒
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    from Script.System.Sex_System import drunk_sex_common

    level, __ = drunk_sex_common.get_drunk_level(character_id)
    if level == 0:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.T_DRUNK_LEVEL_0)
def handle_t_drunk_level_0(character_id: int) -> int:
    """
    交互对象酒精等级：清醒
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return handle_drunk_level_0(activity.target(character_id))


@add_premise(constant_promise.Premise.DRUNK_LEVEL_1)
def handle_drunk_level_1(character_id: int) -> int:
    """
    醉酒等级：微醺
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    from Script.System.Sex_System import drunk_sex_common

    level, __ = drunk_sex_common.get_drunk_level(character_id)
    if level == 1:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.DRUNK_LEVEL_2)
def handle_drunk_level_2(character_id: int) -> int:
    """
    醉酒等级：醉酒
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    from Script.System.Sex_System import drunk_sex_common

    level, __ = drunk_sex_common.get_drunk_level(character_id)
    if level == 2:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.DRUNK_LEVEL_3)
def handle_drunk_level_3(character_id: int) -> int:
    """
    醉酒等级：烂醉
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    from Script.System.Sex_System import drunk_sex_common

    level, __ = drunk_sex_common.get_drunk_level(character_id)
    if level == 3:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.DRUNK_LEVEL_NOT_3)
def handle_drunk_level_not_3(character_id: int) -> int:
    """
    醉酒等级≠烂醉
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_drunk_level_3(character_id)


@add_premise(constant_promise.Premise.DRUNK_LEVEL_GE_1)
def handle_drunk_level_ge_1(character_id: int) -> int:
    """
    醉酒等级≥1
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    from Script.System.Sex_System import drunk_sex_common

    level, __ = drunk_sex_common.get_drunk_level(character_id)
    if level >= 1:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.T_DRUNK_LEVEL_GE_1)
def handle_t_drunk_level_ge_1(character_id: int) -> int:
    """
    交互对象醉酒等级≥1
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return handle_drunk_level_ge_1(activity.target(character_id))


@add_premise(constant_promise.Premise.SANITY_POINT_0)
def handle_sanity_point_0(character_id: int) -> int:
    """
    理智值为0
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    if needs.of(character_id)["sanity"] == 0:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.SANITY_POINT_G_0)
def handle_sanity_point_g_0(character_id: int) -> int:
    """
    理智值不为0
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    if needs.of(character_id)["sanity"] > 0:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.SANITY_POINT_L_5)
def handle_sanity_point_l_5(character_id: int) -> int:
    """
    理智值<5
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    if needs.of(character_id)["sanity"] < 5:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.SANITY_POINT_GE_5)
def handle_sanity_point_ge_5(character_id: int) -> int:
    """
    理智值≥5
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    if needs.of(character_id)["sanity"] >= 5:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.SANITY_POINT_L_10)
def handle_sanity_point_l_10(character_id: int) -> int:
    """
    理智值<10
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    if needs.of(character_id)["sanity"] < 10:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.SANITY_POINT_GE_10)
def handle_sanity_point_ge_10(character_id: int) -> int:
    """
    理智值≥10
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    if needs.of(character_id)["sanity"] >= 10:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.SANITY_POINT_GE_20)
def handle_sanity_point_ge_20(character_id: int) -> int:
    """
    理智值≥20
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    if needs.of(character_id)["sanity"] >= 20:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.SANITY_POINT_GE_40)
def handle_sanity_point_ge_40(character_id: int) -> int:
    """
    理智值≥40
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    if needs.of(character_id)["sanity"] >= 40:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.SANITY_POINT_GE_50)
def handle_sanity_point_ge_50(character_id: int) -> int:
    """
    理智值≥50
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    if needs.of(character_id)["sanity"] >= 50:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.DESIRE_POINT_GE_80)
def handle_desire_point_ge_80(character_id: int) -> int:
    """
    欲望值≥80
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    if needs.of(character_id)["desire"] >= 80:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.DESIRE_POINT_L_80)
def handle_desire_point_l_80(character_id: int) -> int:
    """
    欲望值<80
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    if needs.of(character_id)["desire"] < 80:
        return 1
    else:
        return 0


@add_premise(constant_promise.Premise.DESIRE_POINT_GE_100)
def handle_desire_point_ge_100(character_id: int) -> int:
    """
    欲望值≥100
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """

    if needs.of(character_id)["desire"] >= 100:
        return needs.of(character_id)["desire"] * 2
    else:
        return 0


@add_premise(constant_promise.Premise.TARGET_DESIRE_POINT_GE_80)
def handle_t_desire_point_ge_80(character_id: int) -> int:
    """
    交互对象欲望值≥80
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return handle_desire_point_ge_80(activity.target(character_id))


@add_premise(constant_promise.Premise.TARGET_DESIRE_POINT_L_80)
def handle_t_desire_point_l_80(character_id: int) -> int:
    """
    交互对象欲望值<80
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return handle_desire_point_l_80(activity.target(character_id))


@add_premise(constant_promise.Premise.TARGET_DESIRE_POINT_GE_100)
def handle_t_desire_point_ge_100(character_id: int) -> int:
    """
    交互对象欲望值≥100
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return handle_desire_point_ge_100(activity.target(character_id))
