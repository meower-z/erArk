"""
角色的催眠状态（mind.hypnosis）
==============================
角色的键 mind.hypnosis 稀疏存储与默认值不同的催眠字段：
hypnosis_degree、increase_body_sensitivity、force_ovulation、blockhead、
active_h、roleplay（元组）、pain_as_pleasure。
没有这一项或为空表时读 DEFAULT（零拷贝）。写入整值替换，值未变时不写。
"""

from collections.abc import Mapping, Sequence
from typing import Any, TypedDict, cast

from Script.Core import game_type
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

KEY = "mind.hypnosis"
""" 催眠状态在角色数据里的键 """


class Hypnosis(TypedDict):
    """一个角色的催眠状态"""

    hypnosis_degree: int | float
    """ 催眠程度 """
    increase_body_sensitivity: bool
    """ 体控-敏感度提升 """
    force_ovulation: bool
    """ 体控-强制排卵 """
    blockhead: bool
    """ 体控-木头人 """
    active_h: bool
    """ 体控-逆推 """
    roleplay: tuple[int, ...]
    """ 心控-角色扮演列表 """
    pain_as_pleasure: bool
    """ 心控-苦痛快感化 """


DEFAULT: Hypnosis = {
    "hypnosis_degree": 0,
    "increase_body_sensitivity": False,
    "force_ovulation": False,
    "blockhead": False,
    "active_h": False,
    "roleplay": (),
    "pain_as_pleasure": False,
}
""" 角色没有 mind.hypnosis 时读到的默认值 """

working.register(KEY, {})


def _same_val(a: object, b: object) -> bool:
    return type(a) is type(b) and a == b


def _normalize(name: str, value: Any) -> core.JSON:
    if name == "roleplay":
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return tuple(value)
        return ()
    return cast(core.JSON, value)


def _sparse(values: Mapping[str, Any]) -> dict[str, core.JSON]:
    out: dict[str, core.JSON] = {}
    for name, default in DEFAULT.items():
        if name not in values:
            continue
        val = _normalize(name, values[name])
        if not _same_val(val, default):
            out[name] = val
    return out


def of(cid: int, game: core.GameState | None = None) -> Hypnosis:
    """
    读取角色的催眠状态；为空时直接返回 DEFAULT
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    Hypnosis -- 催眠状态映射
    """
    stored = cast(Mapping[str, Any], working.get(str(cid), KEY, game))
    if not stored:
        return DEFAULT
    merged = dict(DEFAULT)
    merged.update(stored)
    return cast(Hypnosis, merged)


def get(cid: int, field: str, game: core.GameState | None = None) -> Any:
    """零拷贝读取单个催眠字段"""
    if field not in DEFAULT:
        raise KeyError(f"{KEY} has no field {field}")
    stored = cast(Mapping[str, Any], working.get(str(cid), KEY, game))
    defaults = cast(Mapping[str, Any], DEFAULT)
    val = stored.get(field, defaults[field])
    return list(val) if field == "roleplay" else val


def degree(cid: int, game: core.GameState | None = None) -> int | float:
    """零拷贝读取角色的催眠深度"""
    return cast(int | float, get(cid, "hypnosis_degree", game))


def roleplay(cid: int, game: core.GameState | None = None) -> list[int]:
    """读取角色的角色扮演列表副本"""
    return cast(list[int], get(cid, "roleplay", game))


def set_roleplay(cid: int, value: list[int] | tuple[int, ...]) -> None:
    """写入角色的角色扮演列表"""
    set(cid, roleplay=value)


def view(cid: int, game: core.GameState | None = None) -> game_type.HYPNOSIS:
    """
    按当前状态构造一个 HYPNOSIS 对象（只读视图，改它不写回）
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    HYPNOSIS -- 催眠数据结构体
    """
    data = of(cid, game)
    out = game_type.HYPNOSIS()
    out.hypnosis_degree = data["hypnosis_degree"]
    out.increase_body_sensitivity = data["increase_body_sensitivity"]
    out.force_ovulation = data["force_ovulation"]
    out.blockhead = data["blockhead"]
    out.active_h = data["active_h"]
    out.roleplay = list(data["roleplay"])
    out.pain_as_pleasure = data["pain_as_pleasure"]
    return out


def set(cid: int, **values: Any) -> None:
    """
    更新角色的催眠字段，只存非默认项，值未变时不写
    Keyword arguments:
    cid -- 角色id
    values -- 要修改的字段名与值
    """
    stored = cast(Mapping[str, core.JSON], working.get(str(cid), KEY))
    merged: dict[str, Any] = dict(DEFAULT)
    merged.update(stored)
    for name, val in values.items():
        if name not in DEFAULT:
            raise KeyError(f"{KEY} has no field {name}")
        merged[name] = val
    new = _sparse(merged)
    if dict(stored) != new or any(
        type(stored.get(k)) is not type(v) for k, v in new.items()
    ):
        working.put(str(cid), KEY, cast(core.JSON, new))


def reset(cid: int) -> bool:
    """
    把角色催眠状态清空为默认；有改动时返回 True
    Keyword arguments:
    cid -- 角色id
    Return arguments:
    bool -- 清空前非空时为 True
    """
    stored = cast(Mapping[str, core.JSON], working.get(str(cid), KEY))
    if not stored:
        return False
    working.put(str(cid), KEY, {})
    return True


def copy_replaced(old: object, new: object, old_id: int, new_id: int) -> None:
    """
    角色替换迁移时复制催眠数据：旧档抄属性，v16+ 复制内核键
    Keyword arguments:
    old -- 旧角色对象
    new -- 新角色对象
    old_id -- 旧角色id
    new_id -- 新角色id
    """
    old_attrs = vars(old)
    if "hypnosis" in old_attrs:
        vars(new)["hypnosis"] = old_attrs["hypnosis"]
        return
    stored = cast(Mapping[str, core.JSON], working.get(str(old_id), KEY))
    if stored:
        working.put(str(new_id), KEY, dict(stored))


def adopt_old_save(loaded_dict: dict[str, Any]) -> int:
    """
    读档重建角色后，把旧角色对象上的 hypnosis 迁入 mind.hypnosis 并删除原属性；
    旧版 int 型的 roleplay 归一化为空元组并计 1 条更新
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    Return arguments:
    int -- 修复的旧版 int roleplay 条数
    """
    count = 0
    for cid, character in loaded_dict["character_data"].items():
        attrs = vars(character)
        if "hypnosis" not in attrs:
            continue
        old = attrs.pop("hypnosis")
        if old is None:
            continue
        roleplay = getattr(old, "roleplay", [])
        if isinstance(roleplay, int):
            roleplay = ()
            count += 1
        values = {
            name: (
                roleplay if name == "roleplay" else getattr(old, name, default)
            )
            for name, default in DEFAULT.items()
        }
        new = _sparse(values)
        if new:
            working.put(str(cid), KEY, cast(core.JSON, new))
    return count
