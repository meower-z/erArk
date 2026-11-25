"""
玩家能力服务（player_ability_service）
======================================
提供玩家能力五系分组、已装备信物文本、信物可选列表及装备状态切换。
同时向读档修补机制注册装备信物异常初始值修正钩子。
本模块不导入 Script.UI 与 Script.Settle。
"""

from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Modules.domains import abilities, identity, player_collection
from Script.Modules.domains import roster
from Script.Modules.save_load import reset

_: FunctionType = get_text._
""" 本地化翻译函数。 """


@dataclass(frozen=True, slots=True)
class TokenChoice:
    """信物装备界面中单名可切换干员的选项数据。"""

    character_id: int
    """ 对应干员的角色编号。 """
    text: str
    """ 带四位零填充编号与信物描述的展示文本。 """
    equipped: bool
    """ 该干员信物当前是否已装备。 """
    selectable: bool
    """ 当前是否允许点击切换，未达上限或已装备时为 True。 """


@reset.repair
def repair_eqip_token() -> None:
    """
    读档修补钩子，当主角存在且装备信物数据为 [0, [0]] 时，将其修正为 [1, []]。
    Keyword arguments:
    无
    Return arguments:
    None -- 无返回值
    """
    if identity.exists(0):
        if player_collection.get("eqip_token") == [0, [0]]:
            player_collection.set_eqip_token(1, [])


def arts_groups(character_id: int) -> list[tuple[str, str]]:
    """
    按五个系别分组汇总角色已拥有的对应素质名称与说明。
    Keyword arguments:
    character_id -- int，目标角色编号
    Return arguments:
    list[tuple[str, str]] -- 各系别名称与对应素质说明拼接文本的列表
    """
    groups = {
        _("视觉系"): {307, 308, 309},
        _("触觉系"): {310, 311, 312},
        _("激素系"): {304, 305, 306},
        _("催眠系"): {331, 332, 333, 334},
        _("时间系"): {316, 317, 318},
    }
    owned = abilities.talent(character_id)
    return [
        (
            name,
            "".join(
                f"  {game_config.config_talent[i].name}："
                f"{game_config.config_talent[i].info}\n"
                for i in ids
                if owned[i]
            ),
        )
        for name, ids in groups.items()
    ]


def equipped_token_text() -> str:
    """
    构造装备信物规则说明、当前上限与已装备干员列表文本。
    Keyword arguments:
    无
    Return arguments:
    str -- 已装备信物区块展示文本
    """
    limit, equipped = player_collection.get("eqip_token")
    text = "\n" + _(
        "○装备信物时，信物干员正面数值结算+10%，负面数值结算-10%，其他干员为+1%和-1%（可叠加，上限同装备信物上限）\n"
    )
    text += _("  当前最大可装备数量：{0}\n\n").format(limit)
    text += _("  当前装备的信物：\n")
    for chara_id in equipped:
        if chara_id != 0:
            chara = identity.of(chara_id)
            text += f"  {chara.name}：{chara.token_text}\n"
    return text


def token_heading() -> str:
    """
    构造更改装备信物界面顶部的当前装备数量与提示标题文本。
    Keyword arguments:
    无
    Return arguments:
    str -- 更改装备信物界面标题文本
    """
    limit, equipped = player_collection.get("eqip_token")
    text = _("\n更改装备信物\n")
    text += _("当前已装备数量/最大可装备数量：{0}/{1}\n").format(
        len(equipped), limit
    )
    return text + _("请选择要装备的信物：\n")


def token_choices() -> list[TokenChoice]:
    """
    列出持有信物的在编非主角干员及其装备与可选状态。
    Keyword arguments:
    无
    Return arguments:
    list[TokenChoice] -- 按在编顺序排列的信物选项列表
    """
    limit, equipped = player_collection.get("eqip_token")
    tokens = player_collection.get("token_list")
    choices = []
    for character_id in roster.active():
        if character_id == 0 or not tokens.get(character_id):
            continue
        chara = identity.of(character_id)
        choices.append(
            TokenChoice(
                character_id,
                f"[{str(chara.adv).rjust(4, '0')}]{chara.name}：{chara.token_text}",
                character_id in equipped,
                len(equipped) < limit or character_id in equipped,
            )
        )
    return choices


def toggle_token(character_id: int) -> None:
    """
    切换指定干员信物的装备状态，保持装备上限不变并写回收藏数据。
    Keyword arguments:
    character_id -- int，待切换装备状态的干员编号
    Return arguments:
    None -- 无返回值
    """
    limit, equipped = player_collection.get("eqip_token")
    if character_id in equipped:
        equipped.remove(character_id)
    else:
        equipped.append(character_id)
    player_collection.set_eqip_token(limit, equipped)
