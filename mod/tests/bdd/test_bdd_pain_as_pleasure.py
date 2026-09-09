#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
BDD 场景（近真实层）LB-BDD-007：苦痛快感化一致性

对应 openspec bdd-scenarios.md 的 LB-BDD-007。通过真实 ModManager 加载全部 mod 后，
在未 mock 的真实 Script.Settle 结算函数与真实配置数据上驱动苦痛结算，验证：
- 持续性 `pain_as_pleasure` 开关开启时，无论当前意识状态，正向苦痛
  （状态17）都转化为心理快感（状态23），苦痛本身不增加；
- 开关关闭或取消催眠后，正向苦痛恢复普通结算；
- 苦痛下降仍按苦痛处理（不被转化吞掉）；
- 直接苦痛二段效果（小/中/大苦痛及额外绝顶）同样被转化；
- 取消催眠行为效果会清除目标的 pain_as_pleasure 开关。

这些结算函数是全局被 mod 替换后的真实实现，因此本场景是 design.md 定义的
near-real-game BDD，而非隔离单测（隔离单测在 mod 自身 tests/ 内用假模块覆盖）。

运行方式：.venv/bin/pytest mod/tests/bdd/test_bdd_pain_as_pleasure.py -v
"""

import pytest

from mod.tests.bdd.near_real_boot import boot_game_once

# 状态id：17=苦痛，23=心理快感，18=恐怖
PAIN = 17
PSYCH_PLEASURE = 23
TERROR = 18


@pytest.fixture(scope="session")
def booted():
    """会话级近真实引导夹具；返回值类型：BootContext。"""
    return boot_game_once(enable_debug=True)


def _make_character(booted, character_id: int, target_id: int = 0):
    """
    在真实缓存中构造一个字段完整的角色

    参数:
    booted (BootContext): 引导上下文
    character_id (int): 新角色id
    target_id (int): 该角色的交互对象id

    返回值类型：game_type.Character
    功能描述：复用与 Script.Design.character 相同的一整套 attr_calculation 归零函数，
    补齐 ability/status_data/talent/experience/juel/h_state 等，保证真实结算函数
    （如 chara_base_state_adjust 读取 talent[229]）不会 KeyError；随后置于缓存。
    """
    from Script.Design import attr_calculation

    character = booted.game_type.Character()
    character.cid = character_id
    character.name = f"测试{character_id}"
    character.ability = attr_calculation.get_ability_zero(character.ability)
    character.status_data = attr_calculation.get_status_zero(character.status_data)
    character.talent = attr_calculation.get_talent_zero(character.talent)
    character.experience = attr_calculation.get_experience_zero(character.experience)
    character.juel = attr_calculation.get_juel_zero(character.juel)
    character.second_behavior = attr_calculation.get_second_behavior_zero(character.second_behavior)
    character.h_state = attr_calculation.get_h_state_reset(character.h_state)
    character.sp_flag = booted.game_type.SPECIAL_FLAG()
    character.target_character_id = target_id
    character.dead = False
    booted.cache.character_data[character_id] = character
    return character


def _reset_scene(booted):
    """
    重置最小场景：玩家(0)+目标(1)，目标为玩家交互对象

    参数:
    booted (BootContext): 引导上下文

    返回值类型：tuple(player, target)
    功能描述：每个用例独立构造角色，避免用例间状态串扰。
    """
    booted.cache.character_data.clear()
    player = _make_character(booted, 0, target_id=1)
    target = _make_character(booted, 1, target_id=0)
    # 玩家最近行为指令栏位，苦痛公式会读取；给一个稳定默认
    booted.cache.pl_pre_behavior_instruce = []
    booted.cache.group_sex_mode = False
    return player, target


def _enable_pain_as_pleasure(target):
    """
    使目标进入"催眠无意识 + 苦痛快感化"态

    参数:
    target (game_type.Character): 目标角色

    返回值类型：无
    功能描述：设置催眠类无意识状态并开启持续性的苦痛快感化开关。
    """
    target.sp_flag.unconscious_h = 7
    target.hypnosis.pain_as_pleasure = True


def test_positive_pain_converts_to_psychological_pleasure(booted):
    """
    场景：正向苦痛转化为心理快感

    验证点：调用真实（被替换后的）base_chara_state_common_settle 对状态17施加正向
    苦痛时，苦痛值(17)不增长，心理快感(23)增长。
    """
    from Script.Settle import common_default

    _, target = _reset_scene(booted)
    _enable_pain_as_pleasure(target)
    pain_before = target.status_data[PAIN]
    pleasure_before = target.status_data[PSYCH_PLEASURE]

    common_default.base_chara_state_common_settle(1, 30, PAIN, base_value=30, ability_level=0)

    assert target.status_data[PAIN] == pain_before, "苦痛快感化态下苦痛不应增长"
    assert target.status_data[PSYCH_PLEASURE] > pleasure_before, "正向苦痛应转化为心理快感"


def test_all_loaded_mods_keep_common_pain_aliases_installed(booted):
    """场景：全部启用mod按真实顺序加载完成。

    验证点：持有模块级别名的通用、行为与二段入口仍引用同一个
    苦痛快感化补丁；实时与道具入口使用函数内动态导入，由独立行为测试验证。
    """
    from Script.Settle import Second_effect, common_default, default

    assert booted.mod_success is True
    patched = common_default.base_chara_state_common_settle
    assert default.base_chara_state_common_settle is patched
    assert Second_effect.base_chara_state_common_settle is patched


def test_realtime_and_item_pain_callers_use_loaded_common_patch(booted, monkeypatch):
    """场景：实时持续苦痛与道具苦痛通过函数内动态导入进入通用结算。

    验证点：两个真实上层入口在全mod加载后都将正向苦痛转为心理快感，
    避免仅直接测试 common_default 而遗漏真实调用者。
    """
    from Script.Design import handle_premise, map_handle
    from Script.Settle import item_effect, realtime_settle

    _, target = _reset_scene(booted)
    target.hypnosis.pain_as_pleasure = True
    target.sp_flag.unconscious_h = 0

    false_premises = (
        "handle_scene_over_two",
        "handle_exhibitionism_sex_mode_ge_1",
        "handle_self_is_player_daughter",
        "handle_self_is_h",
        "handle_self_now_bondage",
        "handle_first_sex_in_today",
        "handle_first_a_sex_in_today",
        "handle_first_u_sex_in_today",
        "handle_first_w_sex_in_today",
        "handle_imprisonment_1",
        "handle_h_in_bathroom",
    )
    for premise_name in false_premises:
        monkeypatch.setattr(handle_premise, premise_name, lambda _character_id: 0)
    monkeypatch.setattr(handle_premise, "handle_enema", lambda _character_id: 1)
    monkeypatch.setattr(map_handle, "get_chara_now_scene_all_chara_id_list", lambda _character_id: [0, 1])

    realtime_settle.settle_conscious_continuous(1, 5)

    assert target.status_data[PAIN] == 0
    assert target.status_data[PSYCH_PLEASURE] > 0

    player, target = _reset_scene(booted)
    target.hypnosis.pain_as_pleasure = True
    target.sp_flag.unconscious_h = 0
    player.target_character_id = 1
    change_data = booted.game_type.CharacterStatusChange()

    item_effect.handle_target_enema(0, 1, change_data, booted.cache.game_time)

    assert target.status_data[PAIN] == 0
    assert target.status_data[PSYCH_PLEASURE] > 0
    assert PAIN not in change_data.target_change[1].status_data
    assert change_data.target_change[1].status_data[PSYCH_PLEASURE] > 0


def test_pain_decrease_stays_pain(booted):
    """
    场景：苦痛下降仍按苦痛处理

    验证点：add_time+base_value<=0 时走原结算（关闭转化开关），苦痛(17)真实下降，
    心理快感(23)不因此增长。
    """
    from Script.Settle import common_default

    _, target = _reset_scene(booted)
    _enable_pain_as_pleasure(target)
    target.status_data[PAIN] = 500
    pleasure_before = target.status_data[PSYCH_PLEASURE]

    common_default.base_chara_state_common_settle(1, -100, PAIN, base_value=0, ability_level=0)

    assert target.status_data[PAIN] < 500, "苦痛下降应真实减少苦痛值"
    assert target.status_data[PSYCH_PLEASURE] == pleasure_before, "苦痛下降不应转化为心理快感"


def test_conscious_late_group_joiner_positive_pain_still_converts(booted):
    """
    场景：后来清醒加入群交的角色已开启 pain_as_pleasure

    验证点：加入群交不会强行改变意识状态；持续性开关开启后，正向苦痛仍应转为
    心理快感(23)，不能出现状态栏显示开启但实际增加苦痛的分裂状态。
    """
    from Script.Settle import common_default

    _, target = _reset_scene(booted)
    target.hypnosis.pain_as_pleasure = True
    target.sp_flag.unconscious_h = 0
    target.sp_flag.is_h = True
    pain_before = target.status_data[PAIN]
    pleasure_before = target.status_data[PSYCH_PLEASURE]

    common_default.base_chara_state_common_settle(1, 30, PAIN, base_value=30, ability_level=0)

    assert target.status_data[PAIN] == pain_before, "后来清醒加入者不应因意识状态而绕过苦痛快感化"
    assert target.status_data[PSYCH_PLEASURE] > pleasure_before, "后来清醒加入者的正向苦痛应转为心理快感"


def test_disabled_flag_keeps_common_and_direct_pain_as_pain(booted):
    """
    场景：苦痛快感化开关关闭

    验证点：通用正向苦痛与直接苦痛二段都继续增加苦痛，
    不能因补丁安装而误转全部角色的苦痛。
    """
    from Script.Core import constant
    from Script.Settle import common_default

    _, target = _reset_scene(booted)
    target.hypnosis.pain_as_pleasure = False
    pain_before = target.status_data[PAIN]
    pleasure_before = target.status_data[PSYCH_PLEASURE]

    common_default.base_chara_state_common_settle(1, 30, PAIN, base_value=0, ability_level=0, tenths_add=False)

    assert target.status_data[PAIN] > pain_before
    assert target.status_data[PSYCH_PLEASURE] == pleasure_before

    pain_before = target.status_data[PAIN]
    change_data = booted.game_type.CharacterStatusChange()
    constant.settle_second_behavior_effect_data[270](1, change_data)

    assert target.status_data[PAIN] > pain_before
    assert target.status_data[PSYCH_PLEASURE] == pleasure_before
    assert change_data.status_data[PAIN] > 0


def test_converted_target_change_records_only_psychological_pleasure(booted):
    """
    场景：交互对象的苦痛通过 target_change 记录

    验证点：角色实值与目标变更记录都只增加心理快感，
    根变更对象和目标记录都不伪造苦痛增量。
    """
    from Script.Settle import common_default

    _, target = _reset_scene(booted)
    target.hypnosis.pain_as_pleasure = True
    target.sp_flag.unconscious_h = 0
    root_change = booted.game_type.CharacterStatusChange()

    common_default.base_chara_state_common_settle(
        1,
        50,
        PAIN,
        base_value=0,
        ability_level=0,
        tenths_add=False,
        change_data_to_target_change=root_change,
    )

    assert target.status_data[PAIN] == 0
    assert target.status_data[PSYCH_PLEASURE] > 0
    assert PAIN not in root_change.status_data
    assert root_change.target_change[1].status_data[PSYCH_PLEASURE] > 0
    assert PAIN not in root_change.target_change[1].status_data


def test_direct_second_effect_pain_converts(booted):
    """
    场景：直接苦痛二段效果（小/中/大苦痛）被转化

    验证点：绕过通用结算的直接苦痛二段效果在持续性开关开启时转化为心理快感(23)，
    不增加苦痛(17)。
    """
    from Script.Core import constant

    for effect_id in (270, 283, 296):
        _, target = _reset_scene(booted)
        target.hypnosis.pain_as_pleasure = True
        target.sp_flag.unconscious_h = 0
        change_data = booted.game_type.CharacterStatusChange()
        pain_before = target.status_data[PAIN]
        pleasure_before = target.status_data[PSYCH_PLEASURE]

        handler = constant.settle_second_behavior_effect_data[effect_id]
        handler(1, change_data)

        assert target.status_data[PAIN] == pain_before, f"直接苦痛二段效果{effect_id}不应增加苦痛"
        assert target.status_data[PSYCH_PLEASURE] > pleasure_before, f"直接苦痛二段效果{effect_id}应转化为心理快感"

    _, target = _reset_scene(booted)
    target.hypnosis.pain_as_pleasure = True
    target.sp_flag.unconscious_h = 0
    target.h_state.extra_orgasm_count = 1
    change_data = booted.game_type.CharacterStatusChange()
    pain_before = target.status_data[PAIN]
    pleasure_before = target.status_data[PSYCH_PLEASURE]
    constant.settle_second_behavior_effect_data[408](1, change_data)
    assert target.status_data[PAIN] == pain_before, "额外绝顶苦痛不应增加苦痛"
    assert target.status_data[PSYCH_PLEASURE] > pleasure_before, "额外绝顶苦痛应转化为心理快感"


def test_dead_character_pain_is_not_converted(booted):
    """
    场景：已死亡角色的苦痛不被转化（与上游死亡早返回一致）

    验证点：上游 base_chara_state_common_settle 对 dead 角色立即返回、不做任何结算
    （common_default.py:180-181）；苦痛快感化转化路径也应先判定死亡并委派原逻辑，
    不向死亡角色写入心理快感(23)。这是 F1 深化的回归测试。
    """
    from Script.Settle import common_default

    _, target = _reset_scene(booted)
    _enable_pain_as_pleasure(target)
    target.dead = True
    pleasure_before = target.status_data[PSYCH_PLEASURE]

    common_default.base_chara_state_common_settle(1, 30, PAIN, base_value=30, ability_level=0)

    assert target.status_data[PSYCH_PLEASURE] == pleasure_before, "死亡角色不应被写入心理快感"


def test_hypnosis_cancel_clears_pain_as_pleasure_flag(booted):
    """
    场景：取消催眠清除目标苦痛快感化开关

    验证点：催眠取消行为效果(1213)在有效结算(add_time 非零)后清除施术者目标的
    pain_as_pleasure 开关。
    """
    from Script.Core import constant
    import datetime

    player, target = _reset_scene(booted)
    _enable_pain_as_pleasure(target)
    player.target_character_id = 1
    change_data = booted.game_type.CharacterStatusChange()

    handler = constant.settle_behavior_effect_data[1213]
    handler(0, 5, change_data, datetime.datetime(2019, 1, 1))

    assert target.hypnosis.pain_as_pleasure is False, "取消催眠应清除目标苦痛快感化开关"

    from Script.Settle import common_default

    pain_before = target.status_data[PAIN]
    pleasure_before = target.status_data[PSYCH_PLEASURE]
    common_default.base_chara_state_common_settle(1, 30, PAIN, base_value=0, ability_level=0, tenths_add=False)

    assert target.status_data[PAIN] > pain_before, "取消催眠后苦痛应恢复普通结算"
    assert target.status_data[PSYCH_PLEASURE] == pleasure_before, "取消催眠后苦痛不应再转为心理快感"
