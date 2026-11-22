"""
角色的 H 状态（h.state）
======================
角色的键 h.state 稀疏存储与 BODY_H_STATE 默认值不同的字段。
身体道具只存启用或有结束时刻的项：{str(idx): (active_bool, end_minutes_or_None)}，
静态道具名从 game_config 还原；部位绝顶字典只存非零项；群交模板非默认时才存；
多重高潮集合存有序元组。提供热读、单字段写入与 editing(cid) 块。
"""

from collections.abc import Collection, Iterator, Mapping
from contextlib import contextmanager
import datetime
from typing import Any, cast

from Script.Config import game_config
from Script.Core import game_type
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import h_state_group
from Script.Modules.gameplay_resolution import working

KEY = "h.state"
""" H 状态在角色数据里的键 """

_SCALAR_DEFAULTS: Mapping[str, core.JSON] = {
    "bondage": 0,
    "insert_position": -1,
    "insert_position_change_save": -1,
    "shoot_position_body": -1,
    "shoot_position_cloth": -1,
    "current_sex_position": -1,
    "pre_sex_position": -1,
    "current_womb_sex_position": 0,
    "extra_orgasm_count": 0,
    "endure_not_shot_count": 0,
    "just_shoot": 0,
    "orgasm_edge": 0,
    "time_stop_release": False,
    "condom_info_show_flag": False,
    "condom_count": (0, 0),
    "used_semen_energy_agent": False,
    "npc_active_h": False,
    "h_in_love_hotel": False,
    "h_in_bathroom": False,
    "group_sex_lock_flag": False,
    "all_group_sex_temple_run": False,
    "npc_ai_type_in_group_sex": 0,
    "pretend_sleep": False,
    "sex_assist": False,
    "hidden_sex_discovery_dregree": 0,
    "shoot_semen_amount": 0,
}
_INT_ORGASM_DICTS = (
    "orgasm_level",
    "orgasm_edge_count",
    "time_stop_orgasm_count",
    "extra_orgasm_feel",
)
_PARTS = ("mouth", "L_hand", "R_hand", "penis", "anal")
_EMPTY_SIDE: core.JSON = (dict.fromkeys(_PARTS, (-1, -1)), ((-1,), -1))
_DEFAULT_TEMPLATE_FROZEN: core.JSON = {"A": _EMPTY_SIDE, "B": _EMPTY_SIDE}

working.register(KEY, {})
_open: dict[int, game_type.BODY_H_STATE] = {}


def _freeze(value: Any) -> core.JSON:
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(x) for x in value)
    if isinstance(value, dict):
        return {str(k): _freeze(v) for k, v in value.items()}
    return cast(core.JSON, value)


def _thaw(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_thaw(x) for x in value]
    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    return value


def _encode_end(end_time: Any) -> int | None:
    if not isinstance(end_time, datetime.datetime) or end_time.year <= 1:
        return None
    return game_time.minutes(end_time)


def _decode_end(raw: Any) -> datetime.datetime | None:
    if raw is None or isinstance(raw, datetime.datetime):
        return raw
    return game_time.at(int(raw))


def _body_item_name(item_idx: int) -> str:
    cfg = game_config.config_body_item.get(item_idx)
    if cfg is not None and cfg.item_id in game_config.config_item:
        return game_config.config_item[cfg.item_id].name
    return ""


def _feel_state_ids() -> list[int]:
    return [
        sid
        for sid, data in game_config.config_character_state.items()
        if data.type == 0
    ]


def _encode(hs: game_type.BODY_H_STATE) -> dict[str, core.JSON]:
    out: dict[str, core.JSON] = {}
    for name, default in _SCALAR_DEFAULTS.items():
        val = getattr(hs, name, default)
        if name == "condom_count":
            val = tuple(val) if isinstance(val, (list, tuple)) else (0, 0)
        if val != default or type(val) is not type(default):
            out[name] = cast(core.JSON, val)
    plural = getattr(hs, "plural_orgasm_set", None)
    if plural:
        out["plural_orgasm_set"] = tuple(sorted(plural))
    for dname in _INT_ORGASM_DICTS:
        raw_d = getattr(hs, dname, None)
        if isinstance(raw_d, Mapping):
            kept = {str(k): v for k, v in raw_d.items() if v}
            if kept:
                out[dname] = kept
    oc = getattr(hs, "orgasm_count", None)
    if isinstance(oc, Mapping):
        kept_oc: dict[str, core.JSON] = {
            str(k): (v[0], v[1])
            for k, v in oc.items()
            if isinstance(v, (list, tuple))
            and len(v) >= 2
            and (v[0], v[1]) != (0, 0)
        }
        if kept_oc:
            out["orgasm_count"] = kept_oc
    bi = getattr(hs, "body_item", None)
    if isinstance(bi, Mapping):
        kept_bi: dict[str, core.JSON] = {}
        for k, entry in bi.items():
            if isinstance(entry, (list, tuple)) and len(entry) >= 3:
                active, end_enc = bool(entry[1]), _encode_end(entry[2])
                if active or end_enc is not None:
                    kept_bi[str(k)] = (active, end_enc)
        if kept_bi:
            out["body_item"] = kept_bi
    tpl = getattr(hs, "group_sex_body_template_dict", None)
    if isinstance(tpl, Mapping):
        frozen_tpl = _freeze(tpl)
        if frozen_tpl != _DEFAULT_TEMPLATE_FROZEN:
            out["group_sex_body_template_dict"] = frozen_tpl
    return out


def _decode(raw: Mapping[str, Any]) -> game_type.BODY_H_STATE:
    hs = game_type.BODY_H_STATE()
    for name in _SCALAR_DEFAULTS:
        if name in raw:
            val = raw[name]
            setattr(hs, name, list(val) if name == "condom_count" else val)
    if "plural_orgasm_set" in raw:
        hs.plural_orgasm_set = {*raw["plural_orgasm_set"]}
    feel_ids = _feel_state_ids()
    for dname in _INT_ORGASM_DICTS:
        stored_d = raw.get(dname, {})
        target = {sid: 0 for sid in feel_ids}
        if isinstance(stored_d, Mapping):
            target.update({int(k): v for k, v in stored_d.items()})
        setattr(hs, dname, target)
    stored_oc = raw.get("orgasm_count", {})
    oc_out: dict[int, list[int]] = {sid: [0, 0] for sid in feel_ids}
    if isinstance(stored_oc, Mapping):
        for k, v in stored_oc.items():
            oc_out[int(k)] = [v[0], v[1]]
    hs.orgasm_count = oc_out
    bi_out: dict[int, list[Any]] = {
        idx: [_body_item_name(idx), False, None]
        for idx in game_config.config_body_item
    }
    stored_bi = raw.get("body_item", {})
    if isinstance(stored_bi, Mapping):
        for k, v in stored_bi.items():
            idx = int(k)
            bi_out[idx] = [_body_item_name(idx), bool(v[0]), _decode_end(v[1])]
    hs.body_item = bi_out
    if "group_sex_body_template_dict" in raw:
        hs.group_sex_body_template_dict = _thaw(
            raw["group_sex_body_template_dict"]
        )
    return hs


def get(cid: int, field: str, game: core.GameState | None = None) -> Any:
    """零拷贝读取单个标量/成对字段"""
    if game is None and cid in _open:
        return getattr(_open[cid], field)
    if field not in _SCALAR_DEFAULTS:
        raise KeyError(f"{KEY} has no scalar field {field}")
    stored = cast(Mapping[str, Any], working.get(str(cid), KEY, game))
    val = stored.get(field, _SCALAR_DEFAULTS[field])
    return list(val) if field == "condom_count" else val


def body_item_on(
    cid: int, item_id: int, game: core.GameState | None = None
) -> bool:
    """零拷贝判断指定身体道具是否启用"""
    if game is None and cid in _open:
        entry = _open[cid].body_item.get(item_id)
        return bool(entry[1]) if entry is not None else False
    bi = cast(Mapping[str, Any], working.get(str(cid), KEY, game)).get(
        "body_item"
    )
    entry = bi.get(str(item_id)) if isinstance(bi, Mapping) else None
    return bool(entry[0]) if entry is not None else False


def body_item_end(
    cid: int, item_id: int, game: core.GameState | None = None
) -> datetime.datetime | None:
    """读取指定身体道具的结束时间，未设置时返回 None"""
    if game is None and cid in _open:
        entry = _open[cid].body_item.get(item_id)
        return entry[2] if entry is not None else None
    bi = cast(Mapping[str, Any], working.get(str(cid), KEY, game)).get(
        "body_item"
    )
    entry = bi.get(str(item_id)) if isinstance(bi, Mapping) else None
    return _decode_end(entry[1]) if entry is not None else None


def active_body_items(
    cid: int,
    ids: Collection[int] | None = None,
    game: core.GameState | None = None,
) -> list[tuple[int, datetime.datetime | None]]:
    """返回处于启用状态的身体道具列表 [(item_id, end_time)]，无启用项时零拷贝返回空表"""
    if game is None and cid in _open:
        bi_open = _open[cid].body_item
        target_ids = ids if ids is not None else bi_open.keys()
        return [
            (i, bi_open[i][2])
            for i in target_ids
            if i in bi_open and bi_open[i][1]
        ]
    bi = cast(Mapping[str, Any], working.get(str(cid), KEY, game)).get(
        "body_item"
    )
    if not isinstance(bi, Mapping) or not bi:
        return []
    if ids is not None:
        return [
            (i, _decode_end(entry[1]))
            for i in ids
            for entry in (bi.get(str(i)),)
            if entry is not None and entry[0]
        ]
    return [
        (int(k), _decode_end(entry[1])) for k, entry in bi.items() if entry[0]
    ]


def orgasm_level(
    cid: int, part_id: int, game: core.GameState | None = None
) -> int:
    """零拷贝读取单个部位的高潮等级（默认 0）"""
    if game is None and cid in _open:
        return int(_open[cid].orgasm_level.get(part_id, 0))
    ol = cast(Mapping[str, Any], working.get(str(cid), KEY, game)).get(
        "orgasm_level"
    )
    return int(ol.get(str(part_id), 0)) if isinstance(ol, Mapping) else 0


def view(
    cid: int, game: core.GameState | None = None
) -> game_type.BODY_H_STATE:
    """构造 BODY_H_STATE 视图；editing 块内返回正在编辑的对象"""
    if game is None and cid in _open:
        return _open[cid]
    return _decode(cast(Mapping[str, Any], working.get(str(cid), KEY, game)))


def set(cid: int, **fields: Any) -> None:
    """更新一个或多个标量/成对字段，值未变时不写"""
    if cid in _open:
        for name, val in fields.items():
            setattr(
                _open[cid], name, list(val) if name == "condom_count" else val
            )
        return
    stored = cast(Mapping[str, core.JSON], working.get(str(cid), KEY))
    new = dict(stored)
    for name, val in fields.items():
        if name not in _SCALAR_DEFAULTS:
            raise KeyError(f"{KEY} has no scalar field {name}")
        default = _SCALAR_DEFAULTS[name]
        enc: Any = tuple(val) if name == "condom_count" else val
        if enc == default and type(enc) is type(default):
            new.pop(name, None)
        else:
            new[name] = cast(core.JSON, enc)
    if dict(stored) != new:
        working.put(str(cid), KEY, cast(core.JSON, new))


def set_body_item(
    cid: int,
    item_id: int,
    active: bool,
    end_time: datetime.datetime | None = None,
) -> None:
    """设置单个身体道具的启用状态与结束时间"""
    if cid in _open:
        _open[cid].body_item[item_id] = [
            _body_item_name(item_id),
            bool(active),
            end_time,
        ]
        return
    stored = cast(Mapping[str, core.JSON], working.get(str(cid), KEY))
    bi = dict(cast(Mapping[str, core.JSON], stored.get("body_item", {})))
    end_enc, key = _encode_end(end_time), str(item_id)
    if not active and end_enc is None:
        bi.pop(key, None)
    else:
        bi[key] = (bool(active), end_enc)
    new = dict(stored)
    if bi:
        new["body_item"] = bi
    else:
        new.pop("body_item", None)
    if dict(stored) != new:
        working.put(str(cid), KEY, cast(core.JSON, new))


@contextmanager
def editing(cid: int) -> Iterator[game_type.BODY_H_STATE]:
    """修改角色 H 状态的上下文块；退出最外层块时有改动才写回"""
    if cid in _open:
        yield _open[cid]
        return
    hs = view(cid)
    _open[cid] = hs
    try:
        yield hs
    except Exception:
        raise
    except BaseException:
        _commit(cid, hs)
        raise
    else:
        _commit(cid, hs)
    finally:
        _open.pop(cid, None)


def _commit(cid: int, hs: game_type.BODY_H_STATE) -> None:
    new = _encode(hs)
    old = cast(Mapping[str, core.JSON], working.get(str(cid), KEY))
    if dict(old) != new:
        working.put(str(cid), KEY, cast(core.JSON, new))


def reset(cid: int) -> None:
    """H 结束/入睡重置：保留 0/2 类身体道具、时停绝顶、忍住计数与群交设置"""
    if cid in _open:
        stored: Mapping[str, core.JSON] = _encode(_open[cid])
    else:
        stored = cast(Mapping[str, core.JSON], working.get(str(cid), KEY))
        if not stored:
            return
    new: dict[str, core.JSON] = {
        f: stored[f]
        for f in (
            "endure_not_shot_count",
            "group_sex_lock_flag",
            "all_group_sex_temple_run",
            "npc_ai_type_in_group_sex",
            "time_stop_orgasm_count",
        )
        if f in stored
    }
    old_bi = stored.get("body_item")
    if isinstance(old_bi, Mapping):
        kept_bi = {
            str(k): entry
            for k, entry in old_bi.items()
            if (cfg := game_config.config_body_item.get(int(k))) is not None
            and cfg.type in {0, 2}
        }
        if kept_bi:
            new["body_item"] = kept_bi
    if cid in _open:
        vars(_open[cid]).update(vars(_decode(new)))
        return
    if dict(stored) != new:
        working.put(str(cid), KEY, cast(core.JSON, new))


def clear(cid: int) -> bool:
    """清空角色全部 H 状态（返回是否发生改动）"""
    if cid in _open:
        prev = _encode(_open[cid])
        vars(_open[cid]).update(vars(_decode({})))
        return bool(prev)
    if not working.get(str(cid), KEY):
        return False
    working.put(str(cid), KEY, {})
    return True


def remap_group_sex_ids(cid: int, id_map: Mapping[int, int]) -> None:
    """重映射角色群交部位模板里引用的角色id"""
    h_state_group.remap_group_sex_ids(KEY, editing, cid, id_map)


def remove_from_group_sex_template(cid: int, drop_ids: Collection[int]) -> int:
    """从角色群交部位模板中移除指定角色id集合，返回改动的项数"""
    return h_state_group.remove_from_group_sex_template(
        KEY, editing, cid, drop_ids
    )


def group_sex_template_has(
    cid: int, id_set: Collection[int], game: core.GameState | None = None
) -> bool:
    """检查角色群交部位模板里是否包含 id_set 中任一角色id"""
    return h_state_group.group_sex_template_has(KEY, cid, id_set, game)


def copy_replaced(old: object, new: object, old_id: int, new_id: int) -> None:
    """角色替换迁移时复制 H 状态：旧档抄属性，v16+ 复制内核键"""
    old_attrs = vars(old)
    if "h_state" in old_attrs:
        vars(new)["h_state"] = old_attrs["h_state"]
        return
    stored = cast(Mapping[str, core.JSON], working.get(str(old_id), KEY))
    if stored:
        working.put(str(new_id), KEY, dict(stored))


def adopt_old_save(loaded_dict: dict[str, Any]) -> int:
    """读档重建角色后，把旧角色对象上的 h_state 迁入 h.state 并修复旧档结构"""
    count = 0
    feel_ids = _feel_state_ids()
    for cid, character in loaded_dict["character_data"].items():
        attrs = vars(character)
        if "h_state" not in attrs:
            continue
        old = attrs.pop("h_state")
        if old is None:
            continue
        oc = getattr(old, "orgasm_count", None)
        if isinstance(oc, dict):
            for sid in feel_ids:
                if oc.get(sid) == 0:
                    oc[sid] = [0, 0]
                    count += 1
        bi = getattr(old, "body_item", None)
        if not isinstance(bi, dict):
            count += len(game_config.config_body_item)
            old.body_item = {}
        elif len(bi) != len(game_config.config_body_item):
            count += sum(1 for k in game_config.config_body_item if k not in bi)
        enc = _encode(old)
        if enc:
            working.put(str(cid), KEY, cast(core.JSON, enc))
    return count
