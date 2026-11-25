"""
多周目继承与重建服务（new_round_inherit_service）
=================================================
本模块在新周目空状态上执行全局数据恢复、角色重建与宿舍开放。
本模块公开函数 inherit_player、inherit_npcs、rebuild 与
open_dormitories。
本模块不执行界面绘制，也不导入 Script.UI、Script.Settle 或 Tk 模块。
"""

from collections.abc import Iterable, Mapping
from types import FunctionType
from typing import cast

from Script.Config import game_config
from Script.Core import constant, get_text
from Script.Core.num import Num
from Script.Design import character, character_handle, child_stage_gate
from Script.Kernel import core
from Script.Modules.domains import abilities, chara_life, facility
from Script.Modules.domains import first_record, h_meters, hypnosis
from Script.Modules.domains import identity, needs, npc_template
from Script.Modules.domains import player_collection, playthrough
from Script.Modules.domains import relations, roster
from Script.Modules.gameplay_resolution.new_round_service import GROWTH, KEYS
from Script.Modules.gameplay_resolution.new_round_service import rate

_: FunctionType = get_text._
""" 翻译api """


def _int(value: core.JSON) -> int:
    """校验值是否为整数类型并在不匹配时抛出 TypeError。"""
    if not isinstance(value, int):
        raise TypeError(f"{value!r} is not an int")
    return value


def _level(inherit: Mapping[str, core.JSON], type_id: int) -> int:
    """按继承类型编号从继承快照中读取并校验整数等级。"""
    return _int(inherit[KEYS[type_id]])


def _rate(inherit: Mapping[str, core.JSON], type_id: int) -> int:
    """按继承类型编号查询继承快照中对应等级的继承百分比。"""
    return rate(type_id, _level(inherit, type_id))


def _merge_scaled(
    old: Mapping[str, core.JSON], cid: int, now_rate: int
) -> None:
    """按比例缩放角色旧周目的能力与经验并合并写入新状态。"""
    for name in ("ability", "experience"):
        table = abilities.carried(old, cid, name)
        new = {i: int(v * now_rate / 100) for i, v in table.items()}
        abilities.Table(cid, abilities.PICKLED[name]).merge(new)


def _archive(cid: int, inherit: Mapping[str, core.JSON]) -> None:
    """以旧周目数为键归档指定角色的旧周目性行为履历。"""
    carried = cast(Mapping[str, object], inherit.get("first_records", {}))
    first_record.restore_for_new_round(cid, playthrough.game_round(), carried)


def inherit_player(inherit: Mapping[str, core.JSON]) -> str:
    """
    在新状态上重建博士角色并按快照应用各项玩家继承数据。
    Keyword arguments:
    inherit -- Mapping[str, core.JSON]，多周目继承快照字典
    Return arguments:
    str -- 玩家数据继承阶段生成的报告文本
    """
    text = "\n\n" + _("开始继承玩家数据\n")
    identity.put(identity.Identity(0, name=identity.of(0).name))
    character.init_attr(0)
    _archive(0, inherit)
    old = cast(Mapping[str, core.JSON], inherit["abilities"])
    _merge_scaled(old, 0, _rate(inherit, 1))
    text += _("玩家能力与经验继承完毕\n")
    if _level(inherit, 0) > 0:
        old_talent = abilities.carried(old, 0, "talent")
        for i in range(301, 350):
            if i in old_talent and old_talent[i]:
                abilities.talent(0)[i] = old_talent[i]
    text += _("玩家源石技艺继承完毕\n")
    now_rate = _rate(inherit, 2)
    old_max = cast(Mapping[str, Num], inherit["player_maxima"])
    grown = {
        key: int(base + (old_max[key] - base) * now_rate / 100)
        for key, (base, _per) in GROWTH.items()
    }
    needs.set(0, hit_max=grown["hit_max"])
    needs.set(0, mana_max=grown["mana_max"])
    needs.set(0, sanity_max=grown["sanity_max"])
    h_meters.set(0, semen_max=grown["semen_max"])
    text += _("玩家属性上限成长继承完毕\n")
    _inherit_collection(inherit, _rate(inherit, 3))
    return text + _("玩家收藏品继承完毕\n")


def _inherit_collection(
    inherit: Mapping[str, core.JSON], now_rate: int
) -> None:
    """按继承比例上限逐干员复制博士的内裤与袜子收藏品。"""
    carried = cast(
        Mapping[str, Mapping[str, tuple[str, ...]]],
        inherit.get("carried_collection", {}),
    )
    kept = {}
    for name in ("npc_panties", "npc_socks"):
        old = {int(k): list(v) for k, v in carried.get(name, {}).items()}
        limit = int(sum(len(v) for v in old.values()) * now_rate / 100)
        new, count = player_collection.get(name), 0
        for chara_cid, items in old.items():
            count += len(items)
            new[chara_cid] = items
            if count > limit:
                break
        kept[name] = new
    player_collection.update(**kept)


def inherit_npcs(inherit: Mapping[str, core.JSON], fallen_ids: set[int]) -> str:
    """
    仅清空在编名单，从只读的现有模板重建各干员角色数据，按快照为通过阶段判定的陷落干员应用继承并归档全员履历。
    Keyword arguments:
    inherit -- Mapping[str, core.JSON]，多周目继承快照字典
    fallen_ids -- set[int]，待继承的陷落干员编号集合
    Return arguments:
    str -- 干员数据继承阶段生成的报告文本
    """
    text = "\n" + _("开始继承干员数据\n")
    old = cast(Mapping[str, core.JSON], inherit["abilities"])
    social = cast(Mapping[str, tuple[Num, Num]], inherit["fallen_social"])
    hyp = cast(Mapping[str, float], inherit.get("npc_hypnosis", {}))
    roster.clear_active()
    for now_id, now_npc_data in npc_template.table().items():
        character_handle.init_character(
            now_id, now_npc_data, collect_reset=False
        )
        if now_id in fallen_ids and child_stage_gate.restore_grown_stage(
            now_id, abilities.carried(old, now_id, "talent")
        ):
            roster.add(now_id)
            text += _("共有{0}名陷落干员继承到下一周目\n").format(
                roster.count()
            )
            now_rate = _rate(inherit, 4)
            trust, favorability = social[str(now_id)]
            relations.trust.set(now_id, int(trust * now_rate / 100))
            relations.favorability.set_item(
                now_id, 0, int(favorability * now_rate / 100)
            )
            text += _done(
                now_rate,
                _("干员好感与信任继承完毕，共继承了{rate}%的好感与信任\n"),
                _("干员好感与信任未继承\n"),
            )
            now_rate = _rate(inherit, 5)
            _merge_scaled(old, now_id, now_rate)
            text += _done(
                now_rate,
                _("干员能力与经验继承完毕，共继承了{rate}%的能力与经验\n"),
                _("干员能力与经验未继承\n"),
            )
            now_rate = _rate(inherit, 6)
            degree = int(hyp.get(str(now_id), 0) * now_rate / 100)
            hypnosis.set(now_id, hypnosis_degree=degree)
            text += _done(
                now_rate,
                _("干员催眠进度继承完毕，共继承了{rate}%的催眠进度\n"),
                _("干员催眠进度未继承\n"),
            )
        _archive(now_id, inherit)
    return text


def rebuild(inherit: Mapping[str, core.JSON]) -> tuple[str, dict[int, int]]:
    """
    校验继承快照并依次恢复全局数据、重建玩家与干员状态。
    Keyword arguments:
    inherit -- Mapping[str, core.JSON]，多周目继承快照字典
    Return arguments:
    tuple[str, dict[int, int]] -- 继承报告文本与整数键世界设定映射
    """
    fallen = inherit["all_fall_chara_list"]
    world_setting = inherit["world_setting"]
    carried = inherit["carried"]
    if not isinstance(fallen, tuple) or not isinstance(world_setting, Mapping):
        raise TypeError(f"inherit {inherit!r} is malformed")
    playthrough.restore_carried(cast(Mapping[str, core.JSON], carried))
    report = inherit_player(inherit)
    report += inherit_npcs(inherit, {_int(cid) for cid in fallen})
    return report, {int(cid): _int(v) for cid, v in world_setting.items()}


def _done(now_rate: int, done: str, skipped: str) -> str:
    """按继承比例是否大于零返回完成提示或未继承提示文本。"""
    return done.format(rate=now_rate) if now_rate > 0 else skipped


def open_dormitories(chara_ids: Iterable[int]) -> None:
    """
    为指定角色的宿舍检查设施开关并开放尚未开启的宿舍设施。
    Keyword arguments:
    chara_ids -- Iterable[int]，需要检查宿舍设施的角色编号序列
    Return arguments:
    None -- 无返回值
    """
    for now_id in chara_ids:
        scene = constant.scene_data[chara_life.dormitory(now_id)].scene_name
        if scene in game_config.config_facility_open_name_set:
            open_cid = game_config.config_facility_open_name_to_cid[scene]
            if not facility.is_open(open_cid):
                facility.set_open(open_cid, True)
