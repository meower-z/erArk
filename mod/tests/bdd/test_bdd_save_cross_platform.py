#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
BDD 场景（近真实层）：跨平台存档读取

背景：场景/地图键与宿舍等路径字段以 os.sep 拼接后存入存档；在与存档来源
平台分隔符不同的系统上读档时，update_map 会把全部外来键场景当作过期数据
删除并换成空白场景，导致所有角色的场景注册丢失（group_sex_end 等依赖
scene_data.character_list 的流程随即崩溃或静默退化）。

本模块验证已进入 core 的跨平台读档修复：`save_handle.load_save` 将外来
分隔符的路径数据归一化为当前平台分隔符，且对应本地 mod 保持禁用。

用真实引导缓存构造"外来平台存档"（把已知路径字段的分隔符翻转，模拟
Windows 存档在 Linux 上读取），经真实 input_load_save 全流程断言状态存活。

注意：本模块会整体替换全局缓存内容，按文件名排序在其他近真实模块之后执行。

运行方式：.venv/bin/pytest mod/tests/bdd/test_bdd_save_cross_platform.py -v
"""

import io
import os
import pickle

import pytest

from mod.tests.bdd.near_real_boot import boot_game_once
from mod.tests.bdd.test_bdd_pain_as_pleasure import _make_character

FOREIGN_SEP = "\\" if os.sep == "/" else "/"


@pytest.fixture(scope="session")
def booted():
    """会话级近真实引导夹具；返回值类型：BootContext。"""
    return boot_game_once(enable_debug=True)


def _flip_sep(text: str) -> str:
    """
    把路径文本的当前平台分隔符翻转为外来分隔符

    参数:
    text (str): 以 os.sep 拼接的路径文本

    返回值类型：str
    """
    return text.replace(os.sep, FOREIGN_SEP)


def _build_foreign_cache(booted, scene_path_str: str):
    """
    构造一个模拟外来平台（分隔符不同）的存档缓存对象

    参数:
    booted (BootContext): 引导上下文
    scene_path_str (str): 玩家与NPC所在的真实场景路径（当前平台分隔符）

    返回值类型：object，翻转分隔符后的 Cache 副本
    功能描述：对真实引导缓存做 pickle 往返得到深拷贝，再按真实 Windows
    存档中实际存在的路径字段（scene_data/map_data 键、scene_path/map_path、
    宿舍字段、设施损坏与维护地点）翻转分隔符。
    """
    buf = io.BytesIO()
    pickle.dump(booted.cache, buf)
    buf.seek(0)
    copy = pickle.load(buf)

    copy.scene_data = {_flip_sep(key): value for key, value in copy.scene_data.items()}
    for scene in copy.scene_data.values():
        scene.scene_path = _flip_sep(scene.scene_path)
    copy.map_data = {_flip_sep(key): value for key, value in copy.map_data.items()}
    for map_item in copy.map_data.values():
        map_item.map_path = _flip_sep(map_item.map_path)
    for character in copy.character_data.values():
        character.dormitory = _flip_sep(character.dormitory)
        character.permanent_dormitory = _flip_sep(character.permanent_dormitory)
        character.work.dormitory_admin_target_room = _flip_sep(character.work.dormitory_admin_target_room)
        character.pl_ability.air_hypnosis_position = _flip_sep(character.pl_ability.air_hypnosis_position)
    copy.rhodes_island.facility_damage_data = {
        _flip_sep(key): value for key, value in copy.rhodes_island.facility_damage_data.items()
    }
    copy.rhodes_island.maintenance_place = {
        key: _flip_sep(value) for key, value in copy.rhodes_island.maintenance_place.items()
    }
    return copy


def _write_save(tmp_path, slot: str, cache_obj):
    """
    把缓存对象按存档文件布局写入临时目录

    参数:
    tmp_path: pytest 临时目录
    slot (str): 存档槽位名
    cache_obj: 要写入的缓存对象

    返回值类型：str，存档目录路径
    """
    save_dir = tmp_path / slot
    save_dir.mkdir(parents=True, exist_ok=True)
    head = {
        "game_verson": "test-foreign",
        "game_time": cache_obj.game_time,
        "character_name": cache_obj.character_data[0].name,
        "save_time": cache_obj.game_time,
    }
    with open(save_dir / "0", "wb") as f:
        pickle.dump(head, f)
    with open(save_dir / "1", "wb") as f:
        pickle.dump(cache_obj, f)
    return str(save_dir)


@pytest.fixture()
def foreign_save(booted, tmp_path, monkeypatch):
    """
    构造外来分隔符存档并把存档目录指向临时路径

    返回值类型：dict，含 slot/scene_path_str/npc_ids 等断言用信息
    功能描述：在真实场景中放入玩家0与NPC1（写入 position 与场景
    character_list、宿舍字段），翻转分隔符后写为存档文件，并
    monkeypatch save_handle.get_save_dir_path 使读档指向临时目录。
    """
    from Script.Core import save_handle

    cache = booted.cache
    cache.character_data.clear()
    # 选一个多级路径的真实场景（含分隔符），保证键翻转有实际效果
    scene_path_str = next(key for key in cache.scene_data if os.sep in key)
    position = scene_path_str.split(os.sep)
    dorm_path_str = next(
        key for key in cache.scene_data if os.sep in key and key != scene_path_str
    )
    for cid in (0, 1):
        chara = _make_character(booted, cid, target_id=0)
        # 真实存档角色都带 adv 编号；缺失时读档的花名册补全逻辑
        # （update_new_character）会用模板新建同名角色顶掉本角色
        chara.adv = cid
        chara.position = list(position)
        chara.dormitory = dorm_path_str
        chara.permanent_dormitory = dorm_path_str
    # 清理并重建场景注册，只保留本测试的两名角色
    for scene in cache.scene_data.values():
        scene.character_list = set()
    cache.scene_data[scene_path_str].character_list = {0, 1}
    cache.npc_id_got = {1}
    # 设施损坏/维护地点也使用真实场景路径
    cache.rhodes_island.facility_damage_data = {dorm_path_str: 1}
    cache.rhodes_island.maintenance_place = {0: dorm_path_str}

    foreign = _build_foreign_cache(booted, scene_path_str)
    slot = "zz_cross_platform_test"
    save_dir = _write_save(tmp_path, slot, foreign)
    # 模拟真实读档时机的活缓存状态：刚启动的游戏中所有场景注册为空。
    # update_map 会把活缓存场景对象并入读档数据，若活场景带有残留注册，
    # 断言会因测试自身污染而假绿。
    for scene in cache.scene_data.values():
        scene.character_list = set()
    monkeypatch.setattr(
        save_handle,
        "get_save_dir_path",
        lambda save_id: save_dir if save_id == slot else os.path.join("save", save_id),
    )
    return {
        "slot": slot,
        "scene_path_str": scene_path_str,
        "dorm_path_str": dorm_path_str,
    }


def test_foreign_save_keeps_scene_registration(booted, foreign_save):
    """
    场景：外来平台存档读档后场景注册存活（追踪弹）

    验证点：input_load_save 后，玩家0与NPC1仍注册在原场景的
    character_list 中（当前平台分隔符键）；不存在外来分隔符键残留。
    """
    from Script.Core import save_handle

    save_handle.input_load_save(foreign_save["slot"])

    cache = booted.cache
    scene_key = foreign_save["scene_path_str"]
    assert scene_key in cache.scene_data, "当前平台分隔符的场景键应存在"
    assert cache.scene_data[scene_key].character_list == {0, 1}, "场景角色注册不应在读档时丢失"
    assert all(FOREIGN_SEP not in key for key in cache.scene_data), "不应残留外来分隔符场景键"


def test_foreign_save_normalizes_map_data(booted, foreign_save):
    """
    场景：外来平台存档读档后地图键与地图路径归一化

    验证点：input_load_save 后 map_data 的键与每张地图的 map_path
    均使用当前平台分隔符（否则寻路/场景切换的地图查询将 KeyError）。
    """
    from Script.Core import save_handle

    save_handle.input_load_save(foreign_save["slot"])

    cache = booted.cache
    assert all(FOREIGN_SEP not in key for key in cache.map_data), "不应残留外来分隔符地图键"
    assert all(
        FOREIGN_SEP not in map_item.map_path for map_item in cache.map_data.values()
    ), "map_path 应使用当前平台分隔符"


def test_foreign_save_normalizes_character_path_fields(booted, foreign_save):
    """
    场景：外来平台存档读档后角色的路径字段归一化

    验证点：宿舍/前宿舍恢复为当前平台分隔符的原路径（宿舍分配、
    回宿舍睡觉等流程按此查场景）；宿管目标房间与空气催眠位置同理。
    """
    from Script.Core import save_handle

    save_handle.input_load_save(foreign_save["slot"])

    cache = booted.cache
    dorm = foreign_save["dorm_path_str"]
    for cid in (0, 1):
        character = cache.character_data[cid]
        assert character.dormitory == dorm, "dormitory 应归一化为当前平台分隔符"
        assert character.permanent_dormitory == dorm, "permanent_dormitory 应归一化为当前平台分隔符"
        assert FOREIGN_SEP not in character.work.dormitory_admin_target_room
        assert FOREIGN_SEP not in character.pl_ability.air_hypnosis_position


def test_foreign_save_normalizes_rhodes_island_places(booted, foreign_save):
    """
    场景：外来平台存档读档后罗德岛的地点数据归一化

    验证点：设施损坏数据的场景键与维护地点值恢复为当前平台分隔符
    （基建维修与损坏结算按场景路径查询）。
    """
    from Script.Core import save_handle

    save_handle.input_load_save(foreign_save["slot"])

    cache = booted.cache
    dorm = foreign_save["dorm_path_str"]
    assert dorm in cache.rhodes_island.facility_damage_data, "设施损坏键应归一化"
    assert all(FOREIGN_SEP not in key for key in cache.rhodes_island.facility_damage_data)
    assert list(cache.rhodes_island.maintenance_place.values()) == [dorm], "维护地点值应归一化"


def test_native_save_loads_unchanged(booted, tmp_path, monkeypatch):
    """
    场景：本平台存档读档行为不受修复影响（守卫）

    验证点：不翻转分隔符的存档经 input_load_save 后场景注册与
    宿舍字段原样存活——归一化对本平台存档是无操作。
    """
    from Script.Core import save_handle

    cache = booted.cache
    cache.character_data.clear()
    scene_path_str = next(key for key in cache.scene_data if os.sep in key)
    position = scene_path_str.split(os.sep)
    for cid in (0, 1):
        chara = _make_character(booted, cid, target_id=0)
        chara.adv = cid
        chara.position = list(position)
        chara.dormitory = scene_path_str
    for scene in cache.scene_data.values():
        scene.character_list = set()
    cache.scene_data[scene_path_str].character_list = {0, 1}
    cache.npc_id_got = {1}

    buf = io.BytesIO()
    pickle.dump(cache, buf)
    buf.seek(0)
    native = pickle.load(buf)
    slot = "zz_native_test"
    save_dir = _write_save(tmp_path, slot, native)
    monkeypatch.setattr(
        save_handle,
        "get_save_dir_path",
        lambda save_id: save_dir if save_id == slot else os.path.join("save", save_id),
    )
    for scene in cache.scene_data.values():
        scene.character_list = set()

    save_handle.input_load_save(slot)

    assert cache.scene_data[scene_path_str].character_list == {0, 1}
    assert cache.character_data[0].dormitory == scene_path_str


@pytest.mark.skipif(
    not os.path.exists(os.path.join("save", "99", "1")),
    reason="需要用户实机存档 save/99（未随仓库分发）",
)
def test_real_windows_save_slot99_keeps_group_session(booted):
    """
    场景：真实Windows崩溃存档（槽位99，版本2026.6.30-4）跨平台读档后群交会话存活

    验证点：读档（含跨版本迁移）后，玩家与全部10名群交参与者仍注册在
    动力/人力发电室的场景角色表中；群交模式开启；凯尔希的寸止解放态
    （orgasm_edge=2、部位23计数5）原样保留。此前该读档会丢失全部场景
    注册，使 group_sex_end 指令以 list.remove(x): x not in list 崩溃。
    """
    from Script.Core import save_handle

    save_handle.input_load_save("99")

    cache = booted.cache
    scene_key = os.sep.join(("动力", "人力发电室"))
    participant_ids = {0, 3, 7, 10, 56, 130, 241, 308, 385, 4080, 4122}
    assert scene_key in cache.scene_data
    assert cache.scene_data[scene_key].character_list == participant_ids, "群交场景注册应完整存活"
    assert cache.group_sex_mode is True
    kal = cache.character_data[3]
    assert kal.h_state.orgasm_edge == 2
    assert kal.h_state.orgasm_edge_count.get(23) == 5
    assert all(FOREIGN_SEP not in key for key in cache.scene_data)
