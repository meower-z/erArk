"""
角色的污浊数据（body.dirty）
==========================
角色的键 body.dirty 稀疏存储与新角色默认值不同的污浊字段。
三张精液表（body_semen、cloth_semen、cloth_locker_semen）按 {str(id): (当前量Num, 等级int, 总量Num)}
稀疏存储非零项，静态部位名在视图里从 game_config 还原；三表相互独立，不共享可变列表。
新角色的 cloth_locker_semen 为空字典，仅在衣柜精液初始化或非空时记 locker_init=True。
condom_decoration 的元组键 (part_type, part_cid) 编成 "part_type:part_cid"。
提供零拷贝热读（has_semen_flow、body_semen_amount、enema_capacity、get）、
set、editing(cid)、reset(cid) 与 clear(cid)。
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any, cast

from Script.Config import game_config
from Script.Core import game_type, num
from Script.Core.num import Num
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

KEY = "body.dirty"
""" 污浊数据在角色数据里的键 """

_SCALAR_DEFAULTS: Mapping[str, Any] = {
    "a_clean": 0,
    "enema_capacity": 0,
    "absorbed_total_semen": 0,
}

working.register(KEY, {})

_open: dict[int, game_type.DIRTY] = {}


def _is_zero_entry(cur: Any, lv: Any, total: Any) -> bool:
    return (
        cur == 0
        and type(cur) is int
        and lv == 0
        and type(lv) is int
        and total == 0
        and type(total) is int
    )


def _encode_table(table: Any, exact_cur: bool = False) -> dict[str, core.JSON]:
    if not isinstance(table, Mapping):
        return {}
    out: dict[str, core.JSON] = {}
    for k, v in table.items():
        if isinstance(v, (list, tuple)) and len(v) >= 4:
            cur = num.exact(v[1]) if exact_cur else v[1]
            lv = v[2]
            total = v[3]
            if not _is_zero_entry(cur, lv, total):
                out[str(k)] = (cur, lv, total)
    return out


def _decode_table(
    stored: Any, config_map: Mapping[int, Any]
) -> dict[int, list[Any]]:
    out: dict[int, list[Any]] = {
        k: [cfg.name, 0, 0, 0] for k, cfg in config_map.items()
    }
    if isinstance(stored, Mapping):
        for k_str, entry in stored.items():
            k = int(k_str)
            name = config_map[k].name if k in config_map else ""
            out[k] = [name, entry[0], entry[1], entry[2]]
    return out


def _encode_flow(flows: Any, exact: bool = False) -> tuple[core.JSON, ...]:
    if not isinstance(flows, (list, tuple)) or not flows:
        return ()
    out: list[core.JSON] = []
    for flow in flows:
        if not isinstance(flow, Mapping):
            continue
        item: dict[str, core.JSON] = {}
        if "source" in flow and isinstance(flow["source"], Mapping):
            item["source"] = dict(flow["source"])
        if "targets" in flow and isinstance(flow["targets"], (list, tuple)):
            t_list: list[core.JSON] = []
            for t in flow["targets"]:
                if isinstance(t, Mapping):
                    td = dict(t)
                    if exact and "remaining_volume" in td:
                        td["remaining_volume"] = num.exact(
                            td["remaining_volume"]
                        )
                    t_list.append(td)
            item["targets"] = tuple(t_list)
        out.append(item)
    return tuple(out)


def _decode_flow(stored: Any) -> list[dict[str, Any]]:
    if not isinstance(stored, (list, tuple)) or not stored:
        return []
    out: list[dict[str, Any]] = []
    for flow in stored:
        if not isinstance(flow, Mapping):
            continue
        item: dict[str, Any] = {}
        if "source" in flow and isinstance(flow["source"], Mapping):
            item["source"] = dict(flow["source"])
        if "targets" in flow and isinstance(flow["targets"], (list, tuple)):
            item["targets"] = [
                dict(t) for t in flow["targets"] if isinstance(t, Mapping)
            ]
        out.append(item)
    return out


def _encode_condom(dec: Any) -> dict[str, core.JSON]:
    if not isinstance(dec, Mapping) or not dec:
        return {}
    out: dict[str, core.JSON] = {}
    for k, v in dec.items():
        if isinstance(k, (list, tuple)) and len(k) == 2:
            key = f"{k[0]}:{k[1]}"
        else:
            key = str(k)
        out[key] = tuple(v) if isinstance(v, (list, tuple)) else ()
    return out


def _decode_condom(stored: Any) -> dict[tuple[int, int], list[int]]:
    if not isinstance(stored, Mapping) or not stored:
        return {}
    out: dict[tuple[int, int], list[int]] = {}
    for k_str, v in stored.items():
        parts = str(k_str).split(":", 1)
        key = (int(parts[0]), int(parts[1]))
        out[key] = list(v) if isinstance(v, (list, tuple)) else []
    return out


def _encode(d: game_type.DIRTY, exact: bool = False) -> dict[str, core.JSON]:
    out: dict[str, core.JSON] = {}
    bs = _encode_table(getattr(d, "body_semen", None), exact_cur=exact)
    if bs:
        out["body_semen"] = bs
    cs = _encode_table(getattr(d, "cloth_semen", None))
    if cs:
        out["cloth_semen"] = cs
    locker_raw = getattr(d, "cloth_locker_semen", None)
    cls = _encode_table(locker_raw)
    if cls:
        out["cloth_locker_semen"] = cls
        out["locker_init"] = True
    elif isinstance(locker_raw, Mapping) and len(locker_raw) > 0:
        out["locker_init"] = True

    bu = getattr(d, "body_semen_in_unconscious", None)
    if bu:
        out["body_semen_in_unconscious"] = tuple(bu)
    cu = getattr(d, "cloth_semen_in_unconscious", None)
    if cu:
        out["cloth_semen_in_unconscious"] = tuple(cu)

    ac = getattr(d, "a_clean", 0)
    if ac:
        out["a_clean"] = ac
    ec = getattr(d, "enema_capacity", 0)
    if ec:
        out["enema_capacity"] = ec

    flow = _encode_flow(getattr(d, "semen_flow", None), exact=exact)
    if flow:
        out["semen_flow"] = flow

    pd = getattr(d, "penis_dirty_dict", None)
    if isinstance(pd, Mapping) and pd:
        out["penis_dirty_dict"] = {str(k): bool(v) for k, v in pd.items()}

    abs_raw = getattr(d, "absorbed_total_semen", 0)
    abs_val: Num = num.exact(abs_raw) if exact else abs_raw
    if abs_val != 0 or type(abs_val) is not int:
        out["absorbed_total_semen"] = abs_val

    cd = _encode_condom(getattr(d, "condom_decoration", None))
    if cd:
        out["condom_decoration"] = cd
    return out


def _decode(raw: Mapping[str, Any]) -> game_type.DIRTY:
    d = game_type.DIRTY()
    d.body_semen = _decode_table(
        raw.get("body_semen"), game_config.config_body_part
    )
    d.cloth_semen = _decode_table(
        raw.get("cloth_semen"), game_config.config_clothing_type
    )
    if raw.get("locker_init") or raw.get("cloth_locker_semen"):
        d.cloth_locker_semen = _decode_table(
            raw.get("cloth_locker_semen"), game_config.config_clothing_type
        )
    else:
        d.cloth_locker_semen = {}
    if "body_semen_in_unconscious" in raw:
        d.body_semen_in_unconscious = list(raw["body_semen_in_unconscious"])
    if "cloth_semen_in_unconscious" in raw:
        d.cloth_semen_in_unconscious = list(raw["cloth_semen_in_unconscious"])
    d.a_clean = raw.get("a_clean", 0)
    d.enema_capacity = raw.get("enema_capacity", 0)
    d.semen_flow = _decode_flow(raw.get("semen_flow"))
    if "penis_dirty_dict" in raw:
        d.penis_dirty_dict = dict(raw["penis_dirty_dict"])
    d.absorbed_total_semen = raw.get("absorbed_total_semen", 0)
    d.condom_decoration = _decode_condom(raw.get("condom_decoration"))
    return d


def get(cid: int, field: str, game: core.GameState | None = None) -> Any:
    """零拷贝读取标量字段（a_clean、enema_capacity、absorbed_total_semen）"""
    if game is None and cid in _open:
        return getattr(_open[cid], field)
    if field not in _SCALAR_DEFAULTS:
        raise KeyError(f"{KEY} has no scalar field {field}")
    stored = cast(Mapping[str, Any], working.get(str(cid), KEY, game))
    return stored.get(field, _SCALAR_DEFAULTS[field])


def has_semen_flow(cid: int, game: core.GameState | None = None) -> bool:
    """零拷贝判断角色是否有正在流动的精液"""
    if game is None and cid in _open:
        return bool(_open[cid].semen_flow)
    stored = cast(Mapping[str, Any], working.get(str(cid), KEY, game))
    return bool(stored.get("semen_flow"))


def body_semen_amount(
    cid: int, part_id: int, game: core.GameState | None = None
) -> Num:
    """零拷贝读取指定身体部位的当前精液量（默认 0）"""
    if game is None and cid in _open:
        entry = _open[cid].body_semen.get(part_id)
        return entry[1] if entry is not None else 0
    stored = cast(Mapping[str, Any], working.get(str(cid), KEY, game))
    bs = stored.get("body_semen")
    if not isinstance(bs, Mapping):
        return 0
    entry = bs.get(str(part_id))
    return entry[0] if entry is not None else 0


def body_semen_level(
    cid: int, part_id: int, game: core.GameState | None = None
) -> int:
    """零拷贝读取指定身体部位的当前精液等级（默认 0）"""
    if game is None and cid in _open:
        entry = _open[cid].body_semen.get(part_id)
        return int(entry[2]) if entry is not None else 0
    stored = cast(Mapping[str, Any], working.get(str(cid), KEY, game))
    bs = stored.get("body_semen")
    if not isinstance(bs, Mapping):
        return 0
    entry = bs.get(str(part_id))
    return int(entry[1]) if entry is not None else 0


def body_semen_total(
    cid: int, part_id: int, game: core.GameState | None = None
) -> Num:
    """零拷贝读取指定身体部位的累计精液量（默认 0）"""
    if game is None and cid in _open:
        entry = _open[cid].body_semen.get(part_id)
        return entry[3] if entry is not None else 0
    stored = cast(Mapping[str, Any], working.get(str(cid), KEY, game))
    bs = stored.get("body_semen")
    if not isinstance(bs, Mapping):
        return 0
    entry = bs.get(str(part_id))
    return entry[2] if entry is not None else 0


def cloth_semen_amount(
    cid: int, cloth_type: int, game: core.GameState | None = None
) -> Num:
    """零拷贝读取指定穿着服装部位的当前精液量（默认 0）"""
    if game is None and cid in _open:
        entry = _open[cid].cloth_semen.get(cloth_type)
        return entry[1] if entry is not None else 0
    stored = cast(Mapping[str, Any], working.get(str(cid), KEY, game))
    cs = stored.get("cloth_semen")
    if not isinstance(cs, Mapping):
        return 0
    entry = cs.get(str(cloth_type))
    return entry[0] if entry is not None else 0


def enema_capacity(cid: int, game: core.GameState | None = None) -> int:
    """零拷贝读取灌肠容量（默认 0）"""
    return int(get(cid, "enema_capacity", game))


def view(cid: int, game: core.GameState | None = None) -> game_type.DIRTY:
    """构造 DIRTY 视图；editing 块内返回正在编辑的对象"""
    if game is None and cid in _open:
        return _open[cid]
    stored = cast(Mapping[str, Any], working.get(str(cid), KEY, game))
    return _decode(stored)


def set(cid: int, **fields: Any) -> None:
    """更新标量字段（a_clean、enema_capacity、absorbed_total_semen）"""
    if cid in _open:
        for name, val in fields.items():
            setattr(_open[cid], name, val)
        return
    stored = cast(Mapping[str, core.JSON], working.get(str(cid), KEY))
    new = dict(stored)
    for name, val in fields.items():
        if name not in _SCALAR_DEFAULTS:
            raise KeyError(f"{KEY} has no scalar field {name}")
        if val == 0 and type(val) is int:
            new.pop(name, None)
        else:
            new[name] = cast(core.JSON, val)
    if dict(stored) != new or any(
        type(stored.get(k)) is not type(v) for k, v in new.items()
    ):
        working.put(str(cid), KEY, cast(core.JSON, new))


@contextmanager
def editing(cid: int) -> Iterator[game_type.DIRTY]:
    """修改角色污浊数据的上下文块；退出最外层块时有改动才写回"""
    if cid in _open:
        yield _open[cid]
        return
    d = view(cid)
    _open[cid] = d
    try:
        yield d
    except Exception:
        raise
    except BaseException:
        _commit(cid, d)
        raise
    else:
        _commit(cid, d)
    finally:
        _open.pop(cid, None)


def _same_json(a: Any, b: Any) -> bool:
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        return a.keys() == b.keys() and all(_same_json(a[k], b[k]) for k in a)
    if isinstance(a, tuple) and isinstance(b, tuple):
        return len(a) == len(b) and all(
            _same_json(x, y) for x, y in zip(a, b, strict=True)
        )
    return type(a) is type(b) and a == b


def _same_encoded(
    old: Mapping[str, core.JSON], new: Mapping[str, core.JSON]
) -> bool:
    return _same_json(old, new)


def _commit(cid: int, d: game_type.DIRTY) -> None:
    new = _encode(d)
    old = cast(Mapping[str, core.JSON], working.get(str(cid), KEY))
    if not _same_encoded(old, new):
        working.put(str(cid), KEY, cast(core.JSON, new))


def reset(cid: int) -> None:
    """
    洗浴/清理重置：
    清零身体与穿着服装的当前精液量与等级（保留累计量）、清零 a_clean、enema_capacity、
    condom_decoration，阴茎污浊键保留但值置 False；保留衣柜、无意识、流通与累计吸收
    """
    with editing(cid) as d:
        for entry in d.body_semen.values():
            entry[1] = 0
            entry[2] = 0
        for entry in d.cloth_semen.values():
            entry[1] = 0
            entry[2] = 0
        d.a_clean = 0
        d.enema_capacity = 0
        d.condom_decoration = {}
        for k in d.penis_dirty_dict:
            d.penis_dirty_dict[k] = False


def clear(cid: int) -> bool:
    """
    把角色污浊数据重置为全空（返回是否发生改动；若原本已有 locker_init 则保留该标记）
    Keyword arguments:
    cid -- 角色id
    Return arguments:
    bool -- 除 locker_init 外存在非默认污浊数据时为 True
    """
    if cid in _open:
        prev = _encode(_open[cid])
        target: dict[str, core.JSON] = (
            {"locker_init": True} if prev.get("locker_init") else {}
        )
        vars(_open[cid]).update(vars(_decode(target)))
        return not _same_encoded(prev, target)
    stored = cast(Mapping[str, core.JSON], working.get(str(cid), KEY))
    target = {"locker_init": True} if stored.get("locker_init") else {}
    if _same_encoded(stored, target):
        return False
    working.put(str(cid), KEY, cast(core.JSON, target))
    return True


def copy_replaced(old: object, new: object, old_id: int, new_id: int) -> None:
    """角色替换迁移时复制污浊数据：旧档抄属性，v16+ 复制内核键"""
    old_attrs = vars(old)
    if "dirty" in old_attrs:
        vars(new)["dirty"] = old_attrs["dirty"]
        return
    stored = cast(Mapping[str, core.JSON], working.get(str(old_id), KEY))
    if stored:
        working.put(str(new_id), KEY, dict(stored))


def adopt_old_save(loaded_dict: dict[str, Any]) -> int:
    """
    读档重建角色后，把旧角色对象上的 dirty 迁入 body.dirty 并删除原属性：
    对 body_semen[*][1]、absorbed_total_semen 与 semen_flow 剩余量套用 num.exact；
    NPC 缺键的服装表重置为空表，玩家保留缺键表中的合法条目并由解码补齐其余槽位；
    衣柜表始终独立存储（消除旧档别名共享）
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    Return arguments:
    int -- 更新条数（恒为 0）
    """
    chars = loaded_dict["character_data"]
    if not any("dirty" in vars(c) for c in chars.values()):
        return 0
    valid_cloth = game_config.config_clothing_type
    cloth_len = len(valid_cloth)
    for cid, character in chars.items():
        attrs = vars(character)
        if "dirty" not in attrs:
            if cid != 0:
                stored = cast(
                    Mapping[str, core.JSON], working.get(str(cid), KEY)
                )
                if not stored.get("locker_init"):
                    working.put(
                        str(cid),
                        KEY,
                        cast(core.JSON, {**stored, "locker_init": True}),
                    )
            continue
        old = attrs.pop("dirty")
        if old is None:
            continue
        cs = getattr(old, "cloth_semen", None)
        cls = getattr(old, "cloth_locker_semen", None)
        if cid == 0:
            old.cloth_semen = (
                {k: v for k, v in cs.items() if k in valid_cloth}
                if isinstance(cs, dict)
                else {}
            )
            old.cloth_locker_semen = (
                {k: v for k, v in cls.items() if k in valid_cloth}
                if isinstance(cls, dict)
                else {}
            )
        else:
            if not isinstance(cs, dict) or len(cs) != cloth_len:
                old.cloth_semen = {}
            if not isinstance(cls, dict) or len(cls) != cloth_len:
                old.cloth_locker_semen = {}
        enc = _encode(old, exact=True)
        if cid != 0:
            # 旧档经 update_chara_cloth 后 NPC 的 cloth_locker_semen 均已按全部服装类型初始化
            enc["locker_init"] = True
        working.put(str(cid), KEY, cast(core.JSON, enc))
    return 0
