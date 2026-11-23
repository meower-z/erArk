"""
玩家看见交互对象的内衣（cloth_see）
===================================
seen 判定角色穿着的胸衣（部位 6）与内裤（部位 9）能否被玩家看见。
玩家开启透视（visual 为真且拥有素质 307）或对应外层部位（外衣 5、下衣 8）未穿衣物时，该内衣可见。
look 作为 ApplyEffects 输入钩子排在 working.flush 之外，在每一步套用效果之前运行。
当玩家或交互对象处于 H 中时，look 将交互对象的 seen 结果合并写入其 cloth_see。
"""

from Script.Kernel import core
from Script.Modules.domains import abilities, activity, flags, player_ability
from Script.Modules.domains import wardrobe

UNDERWEAR = (6, 9)
""" 胸衣（部位 6）与内裤（部位 9）的部位编号，外层分别是外衣（5）与下衣（8） """


def seen(cid: int) -> dict[int, bool]:
    """
    判定玩家此刻能否看见角色穿着的胸衣与内裤
    Keyword arguments:
    cid -- 角色id
    Return arguments:
    dict -- 已穿着的胸衣或内裤部位编号到是否可见的映射，未穿着的部位不包含在内
    """
    cloth = wardrobe.of(cid)
    xray = bool(player_ability.get(0, "visual") and abilities.talent(0)[307])
    return {
        part: xray or not cloth.cloth_wear[part - 1]
        for part in UNDERWEAR
        if cloth.cloth_wear[part]
    }


@core.input_hook(core.apply_effects)
def look(effects: core.Effects) -> tuple[core.Effects]:
    """
    ApplyEffects 的输入钩子。玩家或交互对象处于 H 中时，将交互对象的 seen 结果合并写入其 cloth_see
    Keyword arguments:
    effects -- 这一步要套用的效果
    Return arguments:
    tuple -- 原样传给内层的效果元组 (effects,)
    """
    cid = activity.target(0)
    if flags.get(0, "is_h") or flags.get(cid, "is_h"):
        see = {**wardrobe.of(cid).cloth_see, **seen(cid)}
        wardrobe.set(cid, "cloth_see", see)
    return (effects,)
