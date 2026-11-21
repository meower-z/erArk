"""
体检的全局键
============
base.exam_setting 是 {体检设置id的字符串: 设置值}。
base.exam_today 是 {今日已体检的角色id的字符串: [做过的检查行为id]}。
base.exam_in_progress 记玩家正在进行、还没结束的体检，结构同 base.exam_today。
base.exam_examined、base.exam_waiting 与 base.exam_chosen 是角色id的升序列表。
这三个键依次记本周期内已体检的干员、正在等待体检的干员与手动选择的体检对象。
base.exam_week_days 是手动选择的体检日（星期几，0 为星期一），按选择的先后排列。
做过的检查行为id按文本升序存。写入函数整值替换一个键。新值与旧值相同时不写。没有某个键时读到空的值。
"""

from collections.abc import Collection, Mapping
from typing import Any, cast

from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

SETTING = "base.exam_setting"
""" 体检设置的全局键 """
TODAY = "base.exam_today"
""" 今日已体检的干员与做过的检查的全局键 """
IN_PROGRESS = "base.exam_in_progress"
""" 玩家正在进行的体检的全局键 """
EXAMINED = "base.exam_examined"
""" 本周期内已体检的干员的全局键 """
WAITING = "base.exam_waiting"
""" 正在等待体检的干员的全局键 """
CHOSEN = "base.exam_chosen"
""" 手动选择的体检对象的全局键 """
WEEK_DAYS = "base.exam_week_days"
""" 手动选择的体检日的全局键 """
ID_LISTS = (EXAMINED, WAITING, CHOSEN)
""" 存角色id升序列表的三个键 """

for _key in (SETTING, TODAY, IN_PROGRESS):
    working.register(_key, {})
for _key in (*ID_LISTS, WEEK_DAYS):
    working.register(_key, ())


def _stored(key: str, game: core.GameState | None) -> Any:
    return working.get(None, key, game)


def _put(key: str, new: core.JSON) -> None:
    old = _stored(key, None)
    if isinstance(new, Mapping):
        same = list(new.items()) == list(old.items())
    else:
        same = tuple(cast(Collection[Any], new)) == tuple(old)
    if not same:
        working.put(None, key, new)


def settings(game: core.GameState | None = None) -> dict[int, int]:
    """
    全部体检设置
    Keyword arguments:
    game -- 给出时只读这个状态，不给时读当前缓冲区
    Return arguments:
    dict -- 设置id到设置值
    """
    return {int(sid): v for sid, v in _stored(SETTING, game).items()}


def setting(sid: int, game: core.GameState | None = None) -> int:
    """
    一项体检设置
    Keyword arguments:
    sid -- 设置id
    game -- 给出时只读这个状态，不给时读当前缓冲区
    Return arguments:
    int -- 设置值。没有这项设置时报 KeyError
    """
    return cast(int, _stored(SETTING, game)[str(sid)])


def set_settings(new: Mapping[int, int]) -> None:
    """
    整值替换体检设置
    Keyword arguments:
    new -- 设置id到设置值，按给出的先后存
    """
    _put(SETTING, {str(sid): v for sid, v in new.items()})


def set_setting(sid: int, value: int) -> None:
    """
    改一项体检设置。没有这项时加在最后
    Keyword arguments:
    sid -- 设置id
    value -- 设置值
    """
    set_settings({**settings(), sid: value})


def checks(key: str, game: core.GameState | None = None) -> dict[int, set[str]]:
    """
    今日已体检的记录，或玩家正在进行的体检的记录
    Keyword arguments:
    key -- TODAY 或 IN_PROGRESS
    game -- 给出时只读这个状态，不给时读当前缓冲区
    Return arguments:
    dict -- 角色id到做过的检查行为id的集合
    """
    return {int(cid): set(done) for cid, done in _stored(key, game).items()}


def _put_checks(key: str, table: Mapping[int, Collection[str]]) -> None:
    stored = {str(c): tuple(sorted(d, key=str)) for c, d in table.items()}
    _put(key, cast(core.JSON, stored))


def record_check(cid: int, check: str) -> None:
    """
    给玩家对 cid 正在进行的体检记下做过的一项检查
    Keyword arguments:
    cid -- 受检角色id
    check -- 检查行为id
    """
    table = checks(IN_PROGRESS)
    table[cid] = table.get(cid, set()) | {check}
    _put_checks(IN_PROGRESS, table)


def finish(cid: int, done: Collection[str]) -> None:
    """
    结束对 cid 的体检。done 记进今日已体检。正在进行的这次体检的记录去掉。
    cid 加进本周期内已体检的名单，并移出等待体检的名单
    Keyword arguments:
    cid -- 受检角色id
    done -- 做过的检查行为id
    """
    _put_checks(TODAY, {**checks(TODAY), cid: done})
    progress = checks(IN_PROGRESS)
    progress.pop(cid, None)
    _put_checks(IN_PROGRESS, progress)
    add(EXAMINED, cid)
    discard(WAITING, cid)


def clear(key: str) -> None:
    """
    清空本模块的一个键
    Keyword arguments:
    key -- 本模块的键
    """
    if isinstance(_stored(key, None), Mapping):
        _put(key, {})
    else:
        _put(key, ())


def ids(key: str, game: core.GameState | None = None) -> set[int]:
    """
    一份名单里的角色
    Keyword arguments:
    key -- ID_LISTS 里的键
    game -- 给出时只读这个状态，不给时读当前缓冲区
    Return arguments:
    set -- 角色id
    """
    return set(_stored(key, game))


def has(key: str, cid: int, game: core.GameState | None = None) -> bool:
    """
    角色是否在一份名单里，或在 TODAY、IN_PROGRESS 的记录里
    Keyword arguments:
    key -- ID_LISTS 里的键，或 TODAY、IN_PROGRESS
    cid -- 角色id
    game -- 给出时只读这个状态，不给时读当前缓冲区
    Return arguments:
    bool -- 在时为 True
    """
    stored = _stored(key, game)
    return (str(cid) if isinstance(stored, Mapping) else cid) in stored


def _put_ids(key: str, new: Collection[int]) -> None:
    _put(key, tuple(sorted(new)))


def add(key: str, cid: int) -> None:
    """
    把角色加进一份名单。角色已在名单里时不写
    Keyword arguments:
    key -- ID_LISTS 里的键
    cid -- 角色id
    """
    _put_ids(key, ids(key) | {cid})


def discard(key: str, cid: int) -> None:
    """
    把角色移出一份名单。角色不在名单里时不写
    Keyword arguments:
    key -- ID_LISTS 里的键
    cid -- 角色id
    """
    _put_ids(key, ids(key) - {cid})


def week_days(game: core.GameState | None = None) -> list[int]:
    """
    手动选择的体检日
    Keyword arguments:
    game -- 给出时只读这个状态，不给时读当前缓冲区
    Return arguments:
    list -- 星期几（0 为星期一），按选择的先后排列
    """
    return list(_stored(WEEK_DAYS, game))


def toggle_week_day(day: int) -> None:
    """
    切换一天是否选作体检日。
    这一天已选时，去掉它第一次出现的那一项。这一天没选时，加在最后
    Keyword arguments:
    day -- 星期几（0 为星期一）
    """
    current = week_days()
    if day in current:
        current.remove(day)
    else:
        current.append(day)
    _put(WEEK_DAYS, tuple(current))


def remap(old_to_new: Mapping[int, int]) -> None:
    """
    角色换id时，把今日已体检、本周期内已体检、等待体检与手动选择的体检对象里的旧id换成新id。
    正在进行的体检不换
    Keyword arguments:
    old_to_new -- 旧id到新id，表里没有的id不变
    """
    today = checks(TODAY)
    _put_checks(TODAY, {old_to_new.get(c, c): d for c, d in today.items()})
    for key in ID_LISTS:
        _put_ids(key, {old_to_new.get(cid, cid) for cid in ids(key)})


def drop(cids: Collection[int]) -> int:
    """
    把 cids 里的角色从今日已体检、本周期内已体检、等待体检与手动选择的体检对象里去掉。
    正在进行的体检不动
    Keyword arguments:
    cids -- 角色id
    Return arguments:
    int -- 去掉的项数。今日已体检里的一名角色算一项，一份名单里的一名角色也算一项
    """
    today = checks(TODAY)
    kept = {cid: done for cid, done in today.items() if cid not in cids}
    count = len(today) - len(kept)
    _put_checks(TODAY, kept)
    for key in ID_LISTS:
        current = ids(key)
        count += len(current & set(cids))
        _put_ids(key, current - set(cids))
    return count


PICKLED = {
    "physical_examination_setting": (SETTING, dict),
    "today_physical_examination_chara_id_dict": (TODAY, dict),
    "physical_examination_in_progress": (IN_PROGRESS, dict),
    "examined_operator_ids": (EXAMINED, set),
    "waiting_for_exam_operator_ids": (WAITING, set),
    "manually_selected_exam_operator_ids": (CHOSEN, set),
    "manually_selected_exam_week_day_list": (WEEK_DAYS, list),
}
""" 版本 15 之前的存档里，罗德岛对象上的属性名到 (全局键, 这个属性应有的类型) """


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从罗德岛对象上删掉 PICKLED 里的属性，把类型正是 PICKLED 所列类型的值写进当前缓冲区。
    集合存成升序列表，做过的检查行为id按文本升序存
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 对象带着 PICKLED 里任一属性或 version 低于 15 时，为缺了或类型不符的属性个数，
    计法同 save_handle.update_dict_with_default。其余为 0
    """
    attrs = vars(loaded_dict["rhodes_island"])
    found = {name: attrs.pop(name) for name in PICKLED if name in attrs}
    kept = {n: v for n, v in found.items() if type(v) is PICKLED[n][1]}
    for name, value in kept.items():
        key = PICKLED[name][0]
        if key == SETTING:
            set_settings(value)
        elif key in (TODAY, IN_PROGRESS):
            _put_checks(key, value)
        elif key in ID_LISTS:
            _put_ids(key, value)
        else:
            _put(key, tuple(value))
    return len(PICKLED) - len(kept) if found or version < 15 else 0
