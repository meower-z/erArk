"""
基地教育区的全局键 base.class_schedule、base.temp_sex_class 与 base.child_schedule_template
===========================================================================================
base.class_schedule 是全局课表：{教室名: {星期字符串: {节次字符串: (能力id, 教师id)}}}。
base.temp_sex_class 是临时课程表：{"日期序数-节次": {classroom, ability_id,
must_attend, notified, running, reserved, ended?}}。
base.child_schedule_template 是日程模板表：{模板编号字符串: {"name": 名称, "slot": {时段字符串: 娱乐id}}}。
三个键缺省时均读空表，写入整值替换对应键，新值与旧值相同时不写。
"""

from collections.abc import Collection, Mapping
from typing import Any, cast

from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

SCHEDULE = "base.class_schedule"
""" 全局课表在全局数据里的键 """
TEMP_SEX_CLASS = "base.temp_sex_class"
""" 临时实操课在全局数据里的键 """
TEMPLATES = "base.child_schedule_template"
""" 日程模板在全局数据里的键 """
KEYS = (SCHEDULE, TEMP_SEX_CLASS, TEMPLATES)
""" 本模块拥有的全部键 """

PICKLED_TYPES: Mapping[str, type] = {
    "class_schedule": dict,
    "temp_sex_class": dict,
    "child_schedule_template": dict,
}
""" 版本 14 之前的存档里，罗德岛对象上三项教育区属性名与应有类型 """

working.register(SCHEDULE, {})
working.register(TEMP_SEX_CLASS, {})
working.register(TEMPLATES, {})


def _raw_schedule(
    game: core.GameState | None = None,
) -> Mapping[str, Mapping[str, Mapping[str, tuple[int, int]]]]:
    return cast(
        Mapping[str, Mapping[str, Mapping[str, tuple[int, int]]]],
        working.get(None, SCHEDULE, game),
    )


def class_schedule(
    game: core.GameState | None = None,
) -> dict[str, dict[int, dict[int, list[int]]]]:
    """
    整张全局课表的可变副本
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- {教室名: {星期int: {节次int: [能力id, 教师id]}}}
    """
    stored = _raw_schedule(game)
    if not stored:
        return {}
    return {
        room: {
            int(day): {
                int(period): list(cell) for period, cell in cells.items()
            }
            for day, cells in week.items()
        }
        for room, week in stored.items()
    }


def class_cell(
    classroom: str,
    week_day: int,
    period: int,
    game: core.GameState | None = None,
) -> list[int] | None:
    """
    读取全局课表的一个格子
    Keyword arguments:
    classroom -- 教室场景名
    week_day -- 星期（0 到 6）
    period -- 节次（0 到 8）
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    list | None -- [能力id, 教师id]，未排课为 None
    """
    cell = (
        _raw_schedule(game)
        .get(classroom, {})
        .get(str(week_day), {})
        .get(str(period))
    )
    return list(cell) if cell is not None else None


def teacher_slot(
    teacher_id: int,
    week_day: int,
    period: int,
    skip_classroom: str | None = None,
    game: core.GameState | None = None,
) -> tuple[str, int] | None:
    """在已存课表里按星期与节次反查教师的 (教室名, 能力id)，未查到为 None，不复制整表；可跳过指定教室"""
    stored = _raw_schedule(game)
    if not stored:
        return None
    day_key, period_key = str(week_day), str(period)
    for classroom, week_data in stored.items():
        if skip_classroom is not None and classroom == skip_classroom:
            continue
        cell = week_data.get(day_key, {}).get(period_key)
        if cell is not None and cell[1] == teacher_id:
            return classroom, cell[0]
    return None


def teacher_week_schedule(
    teacher_id: int, game: core.GameState | None = None
) -> dict[int, dict[int, tuple[str, int]]]:
    """在已存课表里反查一名教师的整周课表 {星期int: {节次int: (教室名, 能力id)}}，不复制无关格子"""
    stored = _raw_schedule(game)
    if not stored:
        return {}
    result: dict[int, dict[int, tuple[str, int]]] = {}
    for classroom, week_data in stored.items():
        for day_key, period_data in week_data.items():
            for period_key, cell in period_data.items():
                if cell[1] == teacher_id:
                    result.setdefault(int(day_key), {})[int(period_key)] = (
                        classroom,
                        cell[0],
                    )
    return result


def set_class_cell(
    classroom: str, week_day: int, period: int, ability_id: int, teacher_id: int
) -> None:
    """
    写入全局课表的一个格子，值未变时不写
    Keyword arguments:
    classroom -- 教室场景名
    week_day -- 星期
    period -- 节次
    ability_id -- 科目能力id
    teacher_id -- 授课教师id
    """
    stored = _raw_schedule()
    day_key, period_key = str(week_day), str(period)
    value = (ability_id, teacher_id)
    if stored.get(classroom, {}).get(day_key, {}).get(period_key) == value:
        return
    room_map = dict(stored.get(classroom, {}))
    day_map = dict(room_map.get(day_key, {}))
    day_map[period_key] = value
    room_map[day_key] = day_map
    working.put(
        None, SCHEDULE, cast(core.JSON, {**stored, classroom: room_map})
    )


def clear_class_cell(classroom: str, week_day: int, period: int) -> None:
    """
    清空全局课表的一个格子，顺带裁掉空的星期与教室映射
    Keyword arguments:
    classroom -- 教室场景名
    week_day -- 星期
    period -- 节次
    """
    stored = _raw_schedule()
    day_key, period_key = str(week_day), str(period)
    if period_key not in stored.get(classroom, {}).get(day_key, {}):
        return
    new_schedule = dict(stored)
    room_map = dict(new_schedule[classroom])
    day_map = dict(room_map[day_key])
    del day_map[period_key]
    if day_map:
        room_map[day_key] = day_map
    else:
        del room_map[day_key]
    if room_map:
        new_schedule[classroom] = room_map
    else:
        del new_schedule[classroom]
    working.put(None, SCHEDULE, cast(core.JSON, new_schedule))


def clear_class_schedule() -> None:
    """清空全部全局课表"""
    if _raw_schedule():
        working.put(None, SCHEDULE, {})


def _raw_temp(
    game: core.GameState | None = None,
) -> Mapping[str, Mapping[str, core.JSON]]:
    return cast(
        Mapping[str, Mapping[str, core.JSON]],
        working.get(None, TEMP_SEX_CLASS, game),
    )


def _thaw_temp(entry: Mapping[str, core.JSON]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in entry.items():
        out[k] = list(v) if isinstance(v, tuple) else v
    return out


def _freeze_temp(entry: Mapping[str, Any]) -> dict[str, core.JSON]:
    out: dict[str, core.JSON] = {}
    for k, v in entry.items():
        if isinstance(v, list):
            out[k] = tuple(v)
        else:
            out[k] = cast(core.JSON, v)
    return out


def temp_classes(
    game: core.GameState | None = None,
) -> dict[str, dict[str, Any]]:
    """全部临时实操课的可变副本：课程键到课程数据字典"""
    stored = _raw_temp(game)
    if not stored:
        return {}
    return {key: _thaw_temp(val) for key, val in stored.items()}


def temp_class(
    class_key: str, game: core.GameState | None = None
) -> dict[str, Any] | None:
    """读取一条临时实操课的可变副本，没有则为 None"""
    found = _raw_temp(game).get(class_key)
    return _thaw_temp(found) if found is not None else None


def put_temp_class(class_key: str, data: Mapping[str, Any]) -> dict[str, Any]:
    """写入或覆盖一条临时实操课，返回写入后的可变副本"""
    stored = _raw_temp()
    frozen = _freeze_temp(data)
    if stored.get(class_key) != frozen:
        working.put(
            None, TEMP_SEX_CLASS, cast(core.JSON, {**stored, class_key: frozen})
        )
    return _thaw_temp(frozen)


def delete_temp_class(class_key: str) -> bool:
    """删掉一条临时实操课，存在并删掉为 True，不存在为 False"""
    stored = _raw_temp()
    if class_key not in stored:
        return False
    updated = {k: v for k, v in stored.items() if k != class_key}
    working.put(None, TEMP_SEX_CLASS, cast(core.JSON, updated))
    return True


def delete_temp_classes(keys: Collection[str]) -> int:
    """一次删掉多条临时实操课，返回实际删掉的条数"""
    stored = _raw_temp()
    if not stored or not keys:
        return 0
    drop = set(keys)
    updated = {k: v for k, v in stored.items() if k not in drop}
    removed = len(stored) - len(updated)
    if removed:
        working.put(None, TEMP_SEX_CLASS, cast(core.JSON, updated))
    return removed


def clear_temp_classes() -> None:
    """清空全部临时实操课"""
    if _raw_temp():
        working.put(None, TEMP_SEX_CLASS, {})


def drop_must_attend(cids: Collection[int]) -> int:
    """
    从每条临时实操课的 must_attend 名单里移除 cids 中的角色
    Keyword arguments:
    cids -- 要移除的角色id集合
    Return arguments:
    int -- 移除的人次
    """
    stored = _raw_temp()
    if not stored or not cids:
        return 0
    drop = set(cids)
    removed = 0
    updated: dict[str, Mapping[str, core.JSON]] = {}
    for key, entry in stored.items():
        raw_list = entry.get("must_attend")
        if isinstance(raw_list, tuple):
            kept = tuple(cid for cid in raw_list if cid not in drop)
            diff = len(raw_list) - len(kept)
            if diff:
                removed += diff
                updated[key] = {**entry, "must_attend": kept}
                continue
        updated[key] = entry
    if removed:
        working.put(None, TEMP_SEX_CLASS, cast(core.JSON, updated))
    return removed


def _raw_templates(
    game: core.GameState | None = None,
) -> Mapping[str, Mapping[str, core.JSON]]:
    return cast(
        Mapping[str, Mapping[str, core.JSON]],
        working.get(None, TEMPLATES, game),
    )


def _thaw_template(entry: Mapping[str, core.JSON]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in entry.items():
        if k == "slot" and isinstance(v, Mapping):
            out[k] = {int(s): cast(int, act) for s, act in v.items()}
        else:
            out[k] = v
    return out


def _freeze_template(entry: Mapping[str, Any]) -> dict[str, core.JSON]:
    out: dict[str, core.JSON] = {}
    for k, v in entry.items():
        if k == "slot" and isinstance(v, Mapping):
            out[k] = {str(s): cast(int, act) for s, act in v.items()}
        else:
            out[k] = cast(core.JSON, v)
    return out


def templates(game: core.GameState | None = None) -> dict[int, dict[str, Any]]:
    """全部已存的日程模板：模板编号到 {"name": 名称, "slot": {时段int: 娱乐id}}"""
    stored = _raw_templates(game)
    if not stored:
        return {}
    return {int(tid): _thaw_template(val) for tid, val in stored.items()}


def template(
    template_id: int, game: core.GameState | None = None
) -> dict[str, Any] | None:
    """读取一套已存的日程模板，不存在为 None"""
    found = _raw_templates(game).get(str(template_id))
    return _thaw_template(found) if found is not None else None


def set_templates(new: Mapping[int, Mapping[str, Any]]) -> None:
    """整表替换日程模板"""
    frozen = {str(tid): _freeze_template(val) for tid, val in new.items()}
    if frozen != _raw_templates():
        working.put(None, TEMPLATES, cast(core.JSON, frozen))


def put_template(template_id: int, data: Mapping[str, Any]) -> None:
    """写入或更新一套日程模板"""
    stored = _raw_templates()
    key = str(template_id)
    frozen = _freeze_template(data)
    if stored.get(key) != frozen:
        working.put(None, TEMPLATES, cast(core.JSON, {**stored, key: frozen}))


def delete_template(template_id: int) -> bool:
    """删掉一套日程模板，存在并删掉为 True，不存在为 False"""
    stored = _raw_templates()
    key = str(template_id)
    if key not in stored:
        return False
    updated = {k: v for k, v in stored.items() if k != key}
    working.put(None, TEMPLATES, cast(core.JSON, updated))
    return True


def clear_templates() -> None:
    """清空全部日程模板"""
    if _raw_templates():
        working.put(None, TEMPLATES, {})


def clear_all() -> None:
    """清空全局课表、临时实操课与日程模板"""
    clear_class_schedule()
    clear_temp_classes()
    clear_templates()


def clear_missing_template_slots(valid_ids: Collection[int]) -> int:
    """
    把日程模板里不在 valid_ids 中的活动编号清为 0
    Keyword arguments:
    valid_ids -- 有效的娱乐配置id集合
    Return arguments:
    int -- 清为 0 的时段数
    """
    current = templates()
    if not current:
        return 0
    cleared = 0
    for entry in current.values():
        slot_data = entry.get("slot")
        if not isinstance(slot_data, dict):
            continue
        for slot in [s for s, val in slot_data.items() if val not in valid_ids]:
            slot_data[slot] = 0
            cleared += 1
    if cleared:
        set_templates(current)
    return cleared


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从罗德岛对象上删掉 PICKLED_TYPES 里的三项属性，把其中类型相符的值写进当前缓冲区。
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档版本，旧存档为 0
    Return arguments:
    int -- 版本 14 之前的存档里缺了或类型不符的属性个数，版本 14 及以后为 0
    """
    island = loaded_dict.get("rhodes_island")
    attrs = vars(island) if island is not None else {}
    found: dict[str, Any] = {
        name: attrs.pop(name) for name in PICKLED_TYPES if name in attrs
    }
    kept: dict[str, Any] = {
        n: v for n, v in found.items() if type(v) is PICKLED_TYPES[n]
    }
    raw_schedule = kept.get("class_schedule")
    if raw_schedule:
        sched = {
            str(room): {
                str(day): {
                    str(period): tuple(cell)
                    for period, cell in cells.items()
                    if isinstance(cell, (list, tuple))
                }
                for day, cells in week.items()
                if isinstance(cells, Mapping)
            }
            for room, week in raw_schedule.items()
            if isinstance(week, Mapping)
        }
        working.put(None, SCHEDULE, cast(core.JSON, sched))
    raw_temp = kept.get("temp_sex_class")
    if raw_temp:
        temps = {
            str(key): _freeze_temp(val)
            for key, val in raw_temp.items()
            if isinstance(val, Mapping)
        }
        working.put(None, TEMP_SEX_CLASS, cast(core.JSON, temps))
    raw_tpl = kept.get("child_schedule_template")
    if raw_tpl:
        tpls = {
            str(tid): _freeze_template(val)
            for tid, val in raw_tpl.items()
            if isinstance(val, Mapping)
        }
        working.put(None, TEMPLATES, cast(core.JSON, tpls))
    return len(PICKLED_TYPES) - len(kept) if version < 14 else 0
