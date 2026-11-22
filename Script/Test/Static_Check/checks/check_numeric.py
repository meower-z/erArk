# -*- coding: UTF-8 -*-
"""
静态检查系统 - 数值范围域检查
覆盖 NUM-01…NUM-30，校验 GameState 里角色的状态值（status.of）、能力/经验/宝珠/素质表（abilities）与
好感（relations.favorability）的键集完整性、当前值/上限值的合法范围，以及基地资源、仓库容量等全局数值。均为纯读取。

执行顺序说明：框架按注册顺序、每个检查项独立 try/except 调用。_NUMERIC_DICT_FIELDS 为空元组，角色对象上没有
待查的数值字典字段，NUM-01 无项可查。读角色对象字段的检查用 getattr 加默认值；状态值经 status.of 读，
能力、经验、宝珠与素质表经 abilities 读，好感经 relations.favorability 读，缺少该项时返回空表。

配表访问一律走 Script.Config.game_config，检查函数只在执行时才引用配表字典（模块顶层不校验 config_xxx 是否存在）。
某个配表字段本身缺失时，对应检查退化为跳过（返回空列表），不影响其余检查项。
"""

import math
from fractions import Fraction
from typing import TypeGuard

from Script.Core import cache_control, num
from Script.Config import game_config
from Script.Design import game_time
from Script.Modules.domains import activity, facility, flags, h_meters
from Script.Modules.domains import h_state as h_state_domain
from Script.Modules.domains import hypnosis as hypnosis_domain, needs
from Script.Modules.domains import player_ability, playthrough, status
from Script.Modules.domains import warehouse
from ..check_registry import CheckFailure, register_check, make_failure
from Script.Modules.domains import abilities, relations
from Script.Modules.domains import identity


def _exact(value: object) -> TypeGuard[int | Fraction]:
    """
    随时间结算的连续数值（num.Num）的合法类型：int 或 Fraction，不含 bool
    Keyword arguments:
    value -- 数值
    Return arguments:
    bool -- 是否为 int 或 Fraction
    """
    return type(value) is int or type(value) is Fraction


# NUM-01 检查的角色对象数值容器字段（为空）；状态值经 status.of、四张表经 abilities、好感经 relations.favorability 读
_NUMERIC_DICT_FIELDS: tuple[str, ...] = ()


def _is_finite_number(v: object) -> bool:
    """
    参数:
        v: 任意待检测值
    返回值:
        bool: v的类型是int或float且为有限数（非NaN/inf）时返回True
    功能:
        判断数值是否为"类型合法且有限"的实数，先做类型短路再调用math.isfinite，避免对None/字符串等非数值类型
        直接调用math.isfinite触发TypeError；同时type(...) in (int, float)正确排除bool（bool是int子类会被isinstance
        误判，但这里用的是type()精确匹配，不受影响）
    """
    return (type(v) is int or type(v) is float) and math.isfinite(v)


def _chara_name(chara: object) -> str:
    """
    参数:
        chara: 角色对象
    返回值:
        str: 角色名字，取不到时返回"?"
    功能:
        安全获取角色名字，避免坏档角色对象连name字段都缺失时检查函数自身抛异常
    """
    return getattr(chara, "name", "?")


def _dict_field_ok(chara: object, field: str) -> bool:
    """
    参数:
        chara: 角色对象
        field (str): 字段名
    返回值:
        bool: 该字段存在且类型为dict时返回True
    功能:
        NUM-01核心判据的单字段版本，供后续各检查在真正使用某个数值字典前廉价复核该字段是否可安全当作dict使用，
        使各检查在NUM-01已经失败的坏档上依然不会抛异常
    """
    return type(getattr(chara, field, None)) is dict


@register_check("NUM-01", "数值容器字段存在且为dict")
def check_num_01_numeric_dict_fields_exist() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验 _NUMERIC_DICT_FIELDS 列出的数值容器字段在每个角色对象上存在且类型为 dict。
        _NUMERIC_DICT_FIELDS 为空元组，角色对象上没有纳入检查的数值字典字段，本检查返回空列表。
        状态值经 status.of 读，能力、经验、宝珠与素质表经 abilities 读，好感经 relations.favorability 读。
    """
    failures = []
    for cid, chara in identity.table().items():
        type_map = {
            f: type(getattr(chara, f, None)).__name__
            for f in _NUMERIC_DICT_FIELDS
        }
        if not all(
            type(getattr(chara, f, None)) is dict for f in _NUMERIC_DICT_FIELDS
        ):
            failures.append(
                make_failure(
                    "NUM-01",
                    "数值容器字段存在且为dict",
                    f"角色cid={cid} name={_chara_name(chara)} 数值容器字段类型异常: {type_map}",
                    [cid],
                )
            )
    return failures


@register_check("NUM-02", "能力字典键集覆盖配表且键为纯int")
def check_num_02_ability_dict_keys() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验config_ability的每个id都在角色的能力表中存在（配表⊆角色，方向不可颠倒——补零与迁移只补不删，
        角色⊆配表或键集相等的方向会在每份升级存档上每回合误报），且能力表的键类型均为精确int
        （避免Python集合里True==1、1.0==1造成的伪装键）。多余键是合法的旧存档残留，仅记录不作为失败条件。
        若config_ability配表本身不存在（独立运行/未初始化），本检查退化为跳过。
    """
    config_ability = getattr(game_config, "config_ability", None)
    if not isinstance(config_ability, dict):
        return []
    config_keys = set(config_ability)
    failures = []
    for cid, chara in identity.table().items():
        ability = abilities.ability(chara.cid)
        missing = config_keys - set(ability)
        bad_key_type = not all(type(k) is int for k in ability)
        if missing or bad_key_type:
            extra = set(ability) - config_keys
            failures.append(
                make_failure(
                    "NUM-02",
                    "能力字典键集覆盖配表且键为纯int",
                    f"角色cid={cid} name={_chara_name(chara)} ability缺键={missing} 多余键(仅记录)={extra} "
                    f"非int键存在={bad_key_type}",
                    [cid],
                )
            )
    return failures


@register_check("NUM-03", "能力值必须是Ability_Lv_Adjust的合法键")
def check_num_03_ability_value_valid_lv() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验角色的能力表的每个值都是config_ability_lv_adjust中的合法键（配表键仅0-10）。get_ability_adjust用能力值
        直接做字典下标且无.get兜底，越界值会在下一次进入该调用点时KeyError崩游戏。type(v) is int而非isinstance，
        避免False当键0、1.0当键1被放行。带cache.debug_mode守卫（debug面板可写任意整数）。
        若config_ability_lv_adjust配表不存在，本检查退化为跳过。
    """
    cache = cache_control.cache
    config_lv_adjust = getattr(game_config, "config_ability_lv_adjust", None)
    if not isinstance(config_lv_adjust, dict):
        return []
    if cache.debug_mode:
        return []
    config_ability = (
        getattr(game_config, "config_ability", {})
        if isinstance(getattr(game_config, "config_ability", None), dict)
        else {}
    )
    valid_keys = set(config_lv_adjust)
    failures = []
    for cid, chara in identity.table().items():
        for ability_id, value in abilities.ability(chara.cid).items():
            if not (type(value) is int and value in valid_keys):
                ability_name = (
                    config_ability[ability_id].name
                    if ability_id in config_ability
                    else "?"
                )
                failures.append(
                    make_failure(
                        "NUM-03",
                        "能力值必须是Ability_Lv_Adjust的合法键",
                        f"角色cid={cid} name={_chara_name(chara)} ability_id={ability_id}({ability_name}) "
                        f"value={value!r} 合法键={sorted(valid_keys)}",
                        [cid],
                    )
                )
    return failures


# NUM-04: 全库唯一可越过8级钳制的能力事件效果 CVE_A2_A|71_G_2（能力71=舌技），见 data/event/chara/0204_白金.json；
# 若日后新增能力事件效果，必须同步更新此白名单，否则本项退化为噪声
_NUM04_UNCLAMPED_ABILITY = {71}


@register_check("NUM-04", "能力等级不超过8（事件白名单除外）")
def check_num_04_ability_level_upper_bound() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验角色的能力表的值不超过8（自动升级循环硬停在8）。能力71（舌技）在白名单内被排除——全库唯一一条能力
        事件效果CVE_A2_A|71_G_2可把已升到8的舌技推到10，不受此上限约束。超过8值得人工复核但不是硬失败，故为warning。
        带cache.debug_mode守卫。若config_ability配表不存在，取名字时退化为"?"，不影响主体判定。
    """
    cache = cache_control.cache
    if cache.debug_mode:
        return []
    config_ability = (
        getattr(game_config, "config_ability", {})
        if isinstance(getattr(game_config, "config_ability", None), dict)
        else {}
    )
    failures = []
    for cid, chara in identity.table().items():
        over = {
            k: v
            for k, v in abilities.ability(chara.cid).items()
            if k not in _NUM04_UNCLAMPED_ABILITY and type(v) is int and v > 8
        }
        if over:
            detail = {
                k: (
                    v,
                    config_ability[k].name if k in config_ability else "?",
                    (
                        config_ability[k].ability_type
                        if k in config_ability
                        else "?"
                    ),
                )
                for k, v in over.items()
            }
            failures.append(
                make_failure(
                    "NUM-04",
                    "能力等级不超过8（事件白名单除外）",
                    f"[warning] 角色cid={cid} name={_chara_name(chara)} adv={getattr(chara, 'adv', '?')} "
                    f"能力越界(id:(值,名字,类型))={detail}",
                    [cid],
                )
            )
    return failures


@register_check("NUM-05", "感度/扩张类能力与角色性别一致")
def check_num_05_ability_sex_consistency() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验sex_need标注为0(男)/1(女)的能力，对性别不符的角色应恒为0（自动升级明确跳过不符项）。非0说明角色性别
        被中途改写或存档串行。依赖NUM-02（键完整）与NUM-06（性别合法）先通过，本检查内部对二者做廉价复核以保持
        独立性。定为warning，因为也可能反映设计内的"双性/扶她"类扩展。带cache.debug_mode守卫。
    """
    cache = cache_control.cache
    if cache.debug_mode:
        return []
    config_ability = getattr(game_config, "config_ability", None)
    if not isinstance(config_ability, dict):
        return []
    failures = []
    for cid, chara in identity.table().items():
        sex = getattr(chara, "sex", None)
        if type(sex) is not int or sex not in (0, 1):
            continue  # 性别本身不合法，交由NUM-06报告，避免级联噪声
        violations = {}
        for aid, d in config_ability.items():
            if d.sex_need in (0, 1) and d.sex_need != sex:
                value = abilities.ability(chara.cid).get(aid)
                if value != 0:
                    violations[aid] = value
        if violations:
            detail = {
                k: (v, config_ability[k].name, config_ability[k].sex_need)
                for k, v in violations.items()
            }
            failures.append(
                make_failure(
                    "NUM-05",
                    "感度/扩张类能力与角色性别一致",
                    f"[warning] 角色cid={cid} name={_chara_name(chara)} sex={sex} "
                    f"性别不符的非零能力(id:(值,名字,sex_need))={detail}",
                    [cid],
                )
            )
    return failures


@register_check("NUM-06", "角色性别取值域")
def check_num_06_sex_domain() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验chara.sex只能是0或1。全库仅四处写.sex，均来自角色模板或玩家二选一创建流程，域外值无合法来源。
        本项是NUM-05的根因守卫。无debug_mode守卫（键集/取值域类检查不加该守卫）。
    """
    failures = []
    for cid, chara in identity.table().items():
        sex = getattr(chara, "sex", None)
        if not (type(sex) is int and sex in {0, 1}):
            failures.append(
                make_failure(
                    "NUM-06",
                    "角色性别取值域",
                    f"角色cid={cid} name={_chara_name(chara)} adv={getattr(chara, 'adv', '?')} sex={sex!r}",
                    [cid],
                )
            )
    return failures


@register_check("NUM-07", "经验字典键集覆盖配表且键为纯int")
def check_num_07_experience_dict_keys() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验config_experience的每个id都在角色的经验表中存在（配表⊆角色），键类型均为精确int。能力升级需求
        以裸下标读经验表[need_type_id]，缺键即崩。多余键是合法残留，仅记录。
        若config_experience配表不存在，退化为跳过。
    """
    config_experience = getattr(game_config, "config_experience", None)
    if not isinstance(config_experience, dict):
        return []
    config_keys = set(config_experience)
    failures = []
    for cid, chara in identity.table().items():
        experience = abilities.experience(chara.cid)
        missing = config_keys - set(experience)
        bad_key_type = not all(type(k) is int for k in experience)
        if missing or bad_key_type:
            extra = set(experience) - config_keys
            failures.append(
                make_failure(
                    "NUM-07",
                    "经验字典键集覆盖配表且键为纯int",
                    f"角色cid={cid} name={_chara_name(chara)} experience缺键={missing} 多余键(仅记录)={extra} "
                    f"非int键存在={bad_key_type}",
                    [cid],
                )
            )
    return failures


@register_check("NUM-08", "经验为非负整数")
def check_num_08_experience_non_negative() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验角色的经验表的每个值都是非负整数。通用经验结算在任何增减后执行max(0, ...)，事件通道的经验操作
        转发给同一函数，因此也走同一套下限钳制。带cache.debug_mode守卫（debug面板允许负数直写）。
    """
    cache = cache_control.cache
    if cache.debug_mode:
        return []
    failures = []
    for cid, chara in identity.table().items():
        bad = {
            k: v
            for k, v in abilities.experience(chara.cid).items()
            if type(v) is not int or v < 0
        }
        if bad:
            failures.append(
                make_failure(
                    "NUM-08",
                    "经验为非负整数",
                    f"角色cid={cid} name={_chara_name(chara)} 非法经验值={bad}",
                    [cid],
                )
            )
    return failures


@register_check("NUM-09", "宝珠字典键集覆盖配表且键为纯int")
def check_num_09_juel_dict_keys() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验config_juel的每个id都在角色的宝珠表中存在（配表⊆角色），键类型均为精确int。升级需求解析出的
        J<id>以裸下标读宝珠表[need_type_id]。多余键是合法残留，仅记录。若config_juel配表不存在，退化为跳过。
    """
    config_juel = getattr(game_config, "config_juel", None)
    if not isinstance(config_juel, dict):
        return []
    config_keys = set(config_juel)
    failures = []
    for cid, chara in identity.table().items():
        juel = abilities.juel(chara.cid)
        missing = config_keys - set(juel)
        bad_key_type = not all(type(k) is int for k in juel)
        if missing or bad_key_type:
            extra = set(juel) - config_keys
            failures.append(
                make_failure(
                    "NUM-09",
                    "宝珠字典键集覆盖配表且键为纯int",
                    f"角色cid={cid} name={_chara_name(chara)} juel缺键={missing} 多余键(仅记录)={extra} "
                    f"非int键存在={bad_key_type}",
                    [cid],
                )
            )
    return failures


@register_check("NUM-10", "宝珠为非负整数")
def check_num_10_juel_non_negative() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验角色的宝珠表的每个值都是非负整数。全部扣除路径都有前置校验或数学下界（升级前先比较再扣、面板夹到
        持有量、睡眠反发珠双侧扣减不透支）。带cache.debug_mode守卫（debug面板可写负数）。
    """
    cache = cache_control.cache
    if cache.debug_mode:
        return []
    failures = []
    for cid, chara in identity.table().items():
        bad = {
            k: v
            for k, v in abilities.juel(chara.cid).items()
            if type(v) is not int or v < 0
        }
        if bad:
            failures.append(
                make_failure(
                    "NUM-10",
                    "宝珠为非负整数",
                    f"角色cid={cid} name={_chara_name(chara)} 非法宝珠值={bad}",
                    [cid],
                )
            )
    return failures


@register_check("NUM-11", "素质字典键集覆盖配表且值为int")
def check_num_11_talent_dict_keys() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验config_talent的每个id都在角色的素质表中存在（配表⊆角色），键与值类型均为精确int（排除bool）。
        素质升级面板的需求T<n>以裸下标读素质表[need_value]。不需要对玩家(cid 0)放宽。玩家先经get_talent_zero
        取得完整config_talent键集，再由get_Dr_talent_zero额外设置几项，只增不减。多余键是迁移残留，仅记录。
        若config_talent配表不存在，退化为跳过。
    """
    config_talent = getattr(game_config, "config_talent", None)
    if not isinstance(config_talent, dict):
        return []
    config_keys = set(config_talent)
    failures = []
    for cid, chara in identity.table().items():
        talent = abilities.talent(chara.cid)
        missing = config_keys - set(talent)
        bad_key_type = not all(type(k) is int for k in talent)
        bad_value_type = not all(type(v) is int for v in talent.values())
        if missing or bad_key_type or bad_value_type:
            extra = set(talent) - config_keys
            failures.append(
                make_failure(
                    "NUM-11",
                    "素质字典键集覆盖配表且值为int",
                    f"角色cid={cid} name={_chara_name(chara)} talent缺键={missing} 多余键(仅记录)={extra} "
                    f"非int键存在={bad_key_type} 非int值存在={bad_value_type}",
                    [cid],
                )
            )
    return failures


@register_check("NUM-12", "状态值字典键集覆盖配表且键为纯int")
def check_num_12_status_data_dict_keys() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验config_character_state的每个id都在角色的状态值（status.of）里（配表⊆角色），键类型均为精确int。
        多余的键不算失败，有失败时一并写进说明。
        config_character_state配表不存在时跳过。
    """
    config_state = getattr(game_config, "config_character_state", None)
    if not isinstance(config_state, dict):
        return []
    config_keys = set(config_state)
    failures = []
    for cid, chara in identity.table().items():
        status_data = status.of(cid)
        missing = config_keys - set(status_data)
        bad_key_type = not all(type(k) is int for k in status_data)
        if missing or bad_key_type:
            extra = set(status_data) - config_keys
            failures.append(
                make_failure(
                    "NUM-12",
                    "状态值字典键集覆盖配表且键为纯int",
                    f"角色cid={cid} name={_chara_name(chara)} status_data缺键={missing} 多余键(仅记录)={extra} "
                    f"非int键存在={bad_key_type}",
                    [cid],
                )
            )
    return failures


@register_check("NUM-13", "状态值为非负的整数或分数")
def check_num_13_status_data_non_negative() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验角色的状态值（status.of）都是非负的int或Fraction。cache.debug_mode为真时跳过。
    """
    cache = cache_control.cache
    if cache.debug_mode:
        return []
    failures = []
    for cid, chara in identity.table().items():
        bad = {
            k: v for k, v in status.of(cid).items() if not _exact(v) or v < 0
        }
        if bad:
            failures.append(
                make_failure(
                    "NUM-13",
                    "状态值为非负的整数或分数",
                    f"角色cid={cid} name={_chara_name(chara)} 非法状态值={bad} "
                    f"behavior_id={activity.behavior(chara.cid).behavior_id}",
                    [cid],
                )
            )
    return failures


@register_check("NUM-14", "状态值不超过99999")
def check_num_14_status_data_upper_bound() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验角色的状态值（status.of）不超过99999。越界报warning，不报error。
        cache.debug_mode为真时跳过。
    """
    cache = cache_control.cache
    if cache.debug_mode:
        return []
    config_state = (
        getattr(game_config, "config_character_state", {})
        if isinstance(
            getattr(game_config, "config_character_state", None), dict
        )
        else {}
    )
    failures = []
    for cid, chara in identity.table().items():
        over = {
            k: v
            for k, v in status.of(cid).items()
            if type(v) in (int, float, Fraction) and v > 99999
        }
        if over:
            detail = {
                k: (v, config_state[k].name if k in config_state else "?")
                for k, v in over.items()
            }
            failures.append(
                make_failure(
                    "NUM-14",
                    "状态值不超过99999",
                    f"[warning] 角色cid={cid} name={_chara_name(chara)} 越界状态(id:(值,名字))={detail} "
                    f"behavior_id={activity.behavior(chara.cid).behavior_id}",
                    [cid],
                )
            )
    return failures


@register_check("NUM-15", "好感键有效且必含玩家")
def check_num_15_favorability_keys() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        本域唯一方向为"角色⊆全局"的键集检查：校验角色键 social.favorability 的每个目标id都必须是身份表
        （identity.characters）中现存角色，且必须含键0（玩家），因为能力升级需求F<n>与事件通道直接访问
        favorability[0]。未招募角色也在身份表里有条目，因此不构成假阳性，真正会命中的是存档迁移遗留的悬空引用。
    """
    failures = []
    valid_cids = set(identity.table())
    for cid, chara in identity.table().items():
        favorability = relations.favorability(cid)
        dangling = set(favorability) - valid_cids
        has_player = 0 in favorability
        if dangling or not has_player:
            failures.append(
                make_failure(
                    "NUM-15",
                    "好感键有效且必含玩家",
                    f"角色cid={cid} name={_chara_name(chara)} 悬空目标id={dangling} 含玩家键0={has_player}",
                    [cid],
                )
            )
    return failures


@register_check("NUM-16", "好感值为整数")
def check_num_16_favorability_type() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        只检查chara.favorability值的类型为int，不设上下界。下界：extra_adjust允许为负且无max(0,..)，负好感是
        设计内合法态。上界：事件直写与可重复的外勤委托奖励都不钳制100000，满好感角色再吃一次奖励即越界，属合法
        流程假阳性，因此上界只作观测信息随失败一并输出，不构成失败条件本身。带cache.debug_mode守卫。
    """
    cache = cache_control.cache
    if cache.debug_mode:
        return []
    failures = []
    for cid, chara in identity.table().items():
        favorability = relations.favorability(cid)
        bad = {k: v for k, v in favorability.items() if type(v) is not int}
        if bad:
            observe_over = {
                k: v
                for k, v in favorability.items()
                if type(v) in (int, float) and v > 100000
            }
            failures.append(
                make_failure(
                    "NUM-16",
                    "好感值为整数",
                    (
                        f"角色cid={cid} name={_chara_name(chara)} 非int好感值={bad} 观测(>100000,"
                        f"非失败条件)={observe_over}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("NUM-17", "信赖与催眠程度为有限实数")
def check_num_17_trust_hypnosis_finite() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验chara.trust与chara.hypnosis.hypnosis_degree都是类型合法(int/float)且有限(非NaN/inf)的实数。一旦某个
        连乘系数产出NaN，min(300, nan)会静默返回nan，之后所有比较恒False，角色行为诡异"卡住"而不报错，是最难
        靠日志发现的一类bug。不加上界（同NUM-16理由：事件与外勤委托的+=不钳制且可重复触发）。
        绝不先裸调math.isfinite——_is_finite_number先做类型短路，避免坏档写入None/字符串时检查器自身抛异常。
    """
    failures = []
    for cid, chara in identity.table().items():
        trust = relations.trust(cid)
        hypnosis_degree = hypnosis_domain.degree(cid)
        if not (
            _is_finite_number(trust) and _is_finite_number(hypnosis_degree)
        ):
            failures.append(
                make_failure(
                    "NUM-17",
                    "信赖与催眠程度为有限实数",
                    f"角色cid={cid} name={_chara_name(chara)} trust={trust!r} hypnosis_degree={hypnosis_degree!r} "
                    f"target_character_id={activity.target(chara.cid)}",
                    [cid],
                )
            )
    return failures


@register_check("NUM-18", "体力/气力上限为正整数")
def check_num_18_hp_mp_max_positive() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验每个角色的体力上限与气力上限（needs.of(cid) 的 hit_max、mana_max）都是正整数。
        实时结算用体力、气力除以各自的上限，上限为0时ZeroDivisionError。
        debug面板可以把上限改成0或负数，所以debug模式下不检查。
    """
    cache = cache_control.cache
    if cache.debug_mode:
        return []
    failures = []
    for cid, chara in identity.table().items():
        hp_max = needs.of(cid)["hit_max"]
        mp_max = needs.of(cid)["mana_max"]
        if not (
            type(hp_max) is int
            and hp_max > 0
            and type(mp_max) is int
            and mp_max > 0
        ):
            failures.append(
                make_failure(
                    "NUM-18",
                    "体力/气力上限为正整数",
                    f"角色cid={cid} name={_chara_name(chara)} adv={getattr(chara, 'adv', '?')} "
                    f"hit_point_max={hp_max!r} mana_point_max={mp_max!r}",
                    [cid],
                )
            )
    return failures


@register_check("NUM-19", "玩家专属槽位上限为正整数")
def check_num_19_player_only_max_fields() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        只校验玩家（cid 0）的理智上限（needs.of(0)["sanity_max"]）、eja_point_max、semen_point_max都是正整数，
        且理智上限<=9999（理智上限的成长封顶在9999）。角色初始化只给玩家设这三项，NPC的停在默认值0，
        所以不查NPC。debug模式下不检查。
    """
    cache = cache_control.cache
    if cache.debug_mode:
        return []
    chara = identity.get(0)
    if chara is None:
        return []
    meters = h_meters.of(0)
    s_max = needs.of(0)["sanity_max"]
    e_max, sm_max = meters["eja_max"], meters["semen_max"]
    if (
        all(type(v) is int and v > 0 for v in (e_max, sm_max, s_max))
        and s_max <= 9999
    ):
        return []
    return [
        make_failure(
            "NUM-19",
            "玩家专属槽位上限为正整数",
            f"玩家cid=0 sanity_point_max={s_max!r} eja_point_max={e_max!r} "
            f"semen_point_max={sm_max!r} sanity_point={num.shown(needs.of(0)['sanity'])} "
            f"eja_point={meters['eja']} semen_point={meters['semen']}",
            [0],
        )
    ]


@register_check("NUM-20", "当前体力在[1,上限]")
def check_num_20_hit_point_range() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验每个活着的角色的体力（needs.of(cid)["hit"]）在[1, 体力上限]内，体力的下限是1不是0。
        死亡角色不查。debug模式下不检查。
    """
    cache = cache_control.cache
    if cache.debug_mode:
        return []
    failures = []
    for cid, chara in identity.table().items():
        if activity.dead(chara.cid):
            continue
        hp = needs.of(cid)["hit"]
        hp_max = needs.of(cid)["hit_max"]
        if (
            not _exact(hp)
            or (type(hp_max) is not int and type(hp_max) is not float)
            or not (1 <= hp <= hp_max)
        ):
            failures.append(
                make_failure(
                    "NUM-20",
                    "当前体力在[1,上限]",
                    (
                        f"角色cid={cid} name={_chara_name(chara)} hit_point={hp!r} hit_point_max={hp_max!r} "
                        f"dead={activity.dead(chara.cid)} behavior_id={activity.behavior(chara.cid).behavior_id}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("NUM-21", "当前气力在[0,上限]")
def check_num_21_mana_point_range() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验每个角色的气力（needs.of(cid)["mana"]）在[0, 气力上限]内。
        上限为0时只有气力0合法，上限的问题由NUM-18报出。debug模式下不检查。
    """
    cache = cache_control.cache
    if cache.debug_mode:
        return []
    failures = []
    for cid, chara in identity.table().items():
        mp = needs.of(cid)["mana"]
        mp_max = needs.of(cid)["mana_max"]
        if (
            not _exact(mp)
            or (type(mp_max) is not int and type(mp_max) is not float)
            or not (0 <= mp <= mp_max)
        ):
            failures.append(
                make_failure(
                    "NUM-21",
                    "当前气力在[0,上限]",
                    f"角色cid={cid} name={_chara_name(chara)} mana_point={mp!r} mana_point_max={mp_max!r} "
                    f"hit_point={num.shown(needs.of(cid)['hit'])} "
                    f"behavior_id={activity.behavior(chara.cid).behavior_id}",
                    [cid],
                )
            )
    return failures


@register_check("NUM-22", "当前理智在[0,上限]")
def check_num_22_sanity_point_range() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验每个角色的理智（needs.of(cid)["sanity"]）在[0, 理智上限]内。debug模式下不检查。
    """
    cache = cache_control.cache
    if cache.debug_mode:
        return []
    failures = []
    for cid, chara in identity.table().items():
        sp = needs.of(cid)["sanity"]
        sp_max = needs.of(cid)["sanity_max"]
        if (
            not _exact(sp)
            or (type(sp_max) is not int and type(sp_max) is not float)
            or not (0 <= sp <= sp_max)
        ):
            extra = ""
            if cid == 0:
                extra = f" today_sanity_point_cost={num.shown(player_ability.get(0, 'today_sanity_point_cost'))}"
            failures.append(
                make_failure(
                    "NUM-22",
                    "当前理智在[0,上限]",
                    f"角色cid={cid} name={_chara_name(chara)} sanity_point={sp!r} sanity_point_max={sp_max!r}{extra}",
                    [cid],
                )
            )
    return failures


@register_check("NUM-23", "射精槽非负且不设上限")
def check_num_23_eja_point_non_negative() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验chara.eja_point非负，不检查<=eja_point_max——槽满时"忍住射精"会直接return，合法保留
        eja_point>=eja_point_max。类型放宽到(int, float)：default.py:3298处的+=写入产出float而漏了int()转换，
        属已知缺陷，硬性type is int会误报此路径；缺陷修好后本项可收紧回int。带cache.debug_mode守卫。
    """
    cache = cache_control.cache
    if cache.debug_mode:
        return []
    failures = []
    for cid, chara in identity.table().items():
        meters = h_meters.of(cid)
        eja = meters["eja"]
        if not ((_exact(eja) or type(eja) is float) and eja >= 0):
            failures.append(
                make_failure(
                    "NUM-23",
                    "射精槽非负且不设上限",
                    (
                        f"角色cid={cid} name={_chara_name(chara)} eja_point={eja!r} "
                        f"eja_point_max={meters['eja_max']} "
                        f"endure_not_shot_count={h_state_domain.get(cid, 'endure_not_shot_count')} "
                        f"is_h={flags.get(cid, 'is_h')}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("NUM-24", "精液槽与临时精液槽范围")
def check_num_24_semen_point_range() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验chara.semen_point在[0, semen_point_max]，chara.tem_extra_semen_point在[0, semen_point_max*4]。
        恢复侧封顶semen_point_max，临时槽封顶4倍，射精面板先扣临时槽再扣基础槽并max(0,...)。对NPC（两值均为0）
        退化为0<=0<=0，不产生假阳性，可对全体跑。带cache.debug_mode守卫。
    """
    cache = cache_control.cache
    if cache.debug_mode:
        return []
    failures = []
    for cid, chara in identity.table().items():
        meters = h_meters.of(cid)
        semen = meters["semen"]
        semen_max = meters["semen_max"]
        tem_extra = meters["extra_semen"]
        ok = (
            _exact(semen)
            and type(tem_extra) is int
            and (type(semen_max) is int or type(semen_max) is float)
            and 0 <= semen <= semen_max
            and 0 <= tem_extra <= semen_max * 4
        )
        if not ok:
            failures.append(
                make_failure(
                    "NUM-24",
                    "精液槽与临时精液槽范围",
                    f"角色cid={cid} name={_chara_name(chara)} semen_point={semen!r} semen_point_max={semen_max!r} "
                    f"tem_extra_semen_point={tem_extra!r}",
                    [cid],
                )
            )
    return failures


@register_check("NUM-25", "基地资源键集覆盖配表且为非负整数")
def check_num_25_base_resource() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验config_resouce的每个id都在base.stock中有记录，且值为非负整数。键集方向同NUM-02（配表⊆资源）：读档只补缺的
        配置资源，不删已下线的资源id，多余键合法。各面板按固定id直接取库存，没有统一的max(0,...)兜底，负库存意味着某条
        支付路径漏判。键类型也查，但warehouse.stock()给出的键总是int。不检查库存<=warehouse_capacity：外勤委托的奖励
        入库不按容量截断。debug_mode下不查数值（debug面板可以把资源1、2、4设成任意整数），键集照查。
        config_resouce不是dict时跳过。
    """
    cache = cache_control.cache
    config_resouce = getattr(game_config, "config_resouce", None)
    if not isinstance(config_resouce, dict):
        return []
    materials = warehouse.stock()
    config_keys = set(config_resouce)
    missing = config_keys - set(materials)
    key_type_ok = all(type(k) is int for k in materials)
    failures = []
    value_bad = (
        {}
        if cache.debug_mode
        else {k: v for k, v in materials.items() if type(v) is not int or v < 0}
    )
    if missing or not key_type_ok or value_bad:
        detail_names = {
            k: config_resouce[k].name
            for k in list(value_bad) + list(missing)
            if k in config_resouce
        }
        failures.append(
            make_failure(
                "NUM-25",
                "基地资源键集覆盖配表且为非负整数",
                (
                    f"资源缺键={missing} 键类型合法={key_type_ok} 非法值={value_bad} 涉及资源名={detail_names} "
                    f"game_time={game_time.now()} "
                    f"warehouse_capacity={warehouse.capacity()}"
                ),
            )
        )
    return failures


@register_check("NUM-26", "仓库容量为非负整数")
def check_num_26_warehouse_capacity() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验warehouse.capacity()为非负整数。日结按这个值截断资源31与资源12的库存，
        负容量会把它们写成负数，比NUM-25更靠近根因。debug_mode下不查。
    """
    cache = cache_control.cache
    if cache.debug_mode:
        return []
    capacity = warehouse.capacity()
    if type(capacity) is int and capacity >= 0:
        return []
    materials = warehouse.stock()
    warehouse_level = facility.levels().get(3)
    return [
        make_failure(
            "NUM-26",
            "仓库容量为非负整数",
            (
                f"warehouse_capacity={capacity!r} facility_level[3]={warehouse_level} "
                f"base.warehouse_modules={warehouse.extra_modules()} "
                f"base.stock[31]={materials.get(31)} base.stock[12]={materials.get(12)}"
            ),
        )
    ]


@register_check("NUM-27", "疲劳/饥饿/熟睡/醉酒在各自量程内")
def check_num_27_fatigue_family_range() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验body.needs的tired∈[0,160]、hunger∈[0,240]、sleep∈[0,100]、drunk∈[0,100]，都须是int或Fraction。
        出界说明有写入越过了上下限。debug面板可以直接改写这四项，所以debug模式下不检查。
    """
    cache = cache_control.cache
    if cache.debug_mode:
        return []
    bounds = {
        "needs.tired": 160,
        "needs.hunger": 240,
        "needs.sleep": 100,
        "needs.drunk": 100,
    }
    failures = []
    for cid, chara in identity.table().items():
        values = {f"needs.{k}": v for k, v in needs.of(cid).items()}
        bad_fields = {}
        for field, upper in bounds.items():
            v = values[field]
            if not (_exact(v) and 0 <= v <= upper):
                bad_fields[field] = v
        if bad_fields:
            failures.append(
                make_failure(
                    "NUM-27",
                    "疲劳/饥饿/熟睡/醉酒在各自量程内",
                    (
                        f"角色cid={cid} name={_chara_name(chara)} 越界字段={bad_fields} "
                        f"behavior_id={activity.behavior(chara.cid).behavior_id} "
                        f"state={activity.state(chara.cid)} "
                        f"unconscious_h={flags.get(chara.cid, "unconscious_h")}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("NUM-28", "尿意值非负且为整数")
def check_num_28_urinate_point_non_negative() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验body.needs的urine是非负的int或Fraction。上界见NUM-29。debug模式下不检查。
    """
    cache = cache_control.cache
    if cache.debug_mode:
        return []
    failures = []
    for cid, chara in identity.table().items():
        urinate = needs.of(cid)["urine"]
        if not (_exact(urinate) and urinate >= 0):
            failures.append(
                make_failure(
                    "NUM-28",
                    "尿意值非负且为整数",
                    f"角色cid={cid} name={_chara_name(chara)} urine={urinate!r} "
                    f"drunk_point={num.shown(needs.of(cid)['drunk'])} "
                    f"behavior_id={activity.behavior(chara.cid).behavior_id}",
                    [cid],
                )
            )
    return failures


@register_check("NUM-29", "角色尿意值不超过300")
def check_num_29_urinate_point_upper_bound() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验所有角色（含玩家cid=0）body.needs的urine不超过300。失败记录带[warning]前缀。debug模式下不检查。
        300是设计上界，realtime_settle、drunk_sex_common与default.py加尿意时都用它封顶。
    """
    cache = cache_control.cache
    if cache.debug_mode:
        return []
    difficulty_setting = playthrough.settings(playthrough.DIFFICULTY)
    failures = []
    for cid, chara in identity.table().items():
        urinate = needs.of(cid)["urine"]
        if (_exact(urinate) or type(urinate) is float) and urinate > 300:
            failures.append(
                make_failure(
                    "NUM-29",
                    "角色尿意值不超过300",
                    (
                        f"[warning] 角色cid={cid} name={_chara_name(chara)} urine={urinate!r} "
                        f"behavior_id={activity.behavior(chara.cid).behavior_id} "
                        f"difficulty_setting[11]={difficulty_setting.get(11)} "
                        f"difficulty_setting[12]={difficulty_setting.get(12)}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("NUM-30", "欲望值为非负整数且不设上限")
def check_num_30_desire_point_non_negative() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验每个角色的欲望值（needs.of(cid)["desire"]）是非负整数，不查上限。
        逐日结算按欲望等级累加欲望值而不封顶，前提函数在欲望值>=100时权重仍随数值增长。debug模式下不检查。
    """
    cache = cache_control.cache
    if cache.debug_mode:
        return []
    failures = []
    for cid, chara in identity.table().items():
        desire = needs.of(cid)["desire"]
        if not (type(desire) is int and desire >= 0):
            ability_33 = abilities.ability(cid).get(33)
            failures.append(
                make_failure(
                    "NUM-30",
                    "欲望值为非负整数且不设上限",
                    f"角色cid={cid} name={_chara_name(chara)} desire_point={desire!r} ability[33]={ability_33} "
                    f"game_time={game_time.now()}",
                    [cid],
                )
            )
    return failures
