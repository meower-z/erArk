from collections import defaultdict
import datetime
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace


class Behavior:
    def __init__(self):
        self.behavior_id = "wait"
        self.duration = 1
        self.start_time = datetime.datetime(2026, 1, 1, 12, 0)
        self.move_src = []
        self.move_target = []
        self.move_final_target = []


class SpFlag:
    def __init__(self):
        self.is_h = True
        self.tired = False
        self.unconscious_h = 0
        self.move_stop = False
        self.masturebate = 0


class HState:
    def __init__(self):
        self.orgasm_edge = 0
        self.orgasm_edge_count = defaultdict(int)
        self.orgasm_count = defaultdict(lambda: [0, 0])
        self.orgasm_level = defaultdict(int)
        self.plural_orgasm_set = set()
        self.shoot_position_body = -1
        self.extra_orgasm_count = 0


class Character:
    def __init__(self, cid, target_character_id=None):
        self.cid = cid
        self.name = f"角色{cid}"
        self.target_character_id = cid if target_character_id is None else target_character_id
        self.behavior = Behavior()
        self.sp_flag = SpFlag()
        self.h_state = HState()
        self.second_behavior = {}
        self.must_settle_second_behavior_id_list = []
        self.must_show_second_behavior_id_list = []
        self.position = ["room"]
        self.ability = defaultdict(lambda: 10)
        self.hit_point = 10
        self.tired_point = 0


class Cache:
    def __init__(self, scene_ids=None):
        self.character_data = {0: Character(0, target_character_id=1)}
        self.scene_data = {"room": SimpleNamespace(character_list=set(scene_ids or [0, 1, 2]))}
        self.achievement = SimpleNamespace(group_sex_record={}, hidden_sex_record={}, exhibitionism_sex_record={}, sleep_sex_record={})
        self.group_sex_mode = True
        self.game_time = datetime.datetime(2026, 1, 1, 12, 0)
        self.over_behavior_character = set()
        self.pl_pre_behavior_instruce = []


class ChangeData:
    def __init__(self):
        self.target_change = {}
        self.status_data = defaultdict(int)


class StateConfig:
    def __init__(self, state_type=0):
        self.type = state_type
        self.name = "快感"


def load_local_bugfix():
    mod_root = Path(__file__).resolve().parents[1]
    script_path = mod_root / "scripts" / "local_bugfix.py"
    namespace = {"__name__": "mod_local_bugfix_group_edge_test"}
    source = script_path.read_text(encoding="utf-8").replace("\n_install_registry_patches()\n", "\n")
    exec(compile(source, str(script_path), "exec"), namespace)
    return namespace


def load_h_orgasm_batch(cache, game_config, constant):
    mod_root = Path(__file__).resolve().parents[1]
    script_path = mod_root / "scripts" / "h_orgasm_batch.py"
    namespace = {
        "__name__": "mod_local_bugfix_h_batch_group_edge_test",
        "cache": cache,
        "game_type": SimpleNamespace(TargetChange=ChangeData),
        "random": SimpleNamespace(shuffle=lambda values: values.reverse()),
        "_": lambda text: text,
        "game_config": game_config,
        "constant": constant,
    }
    exec(compile(script_path.read_text(encoding="utf-8"), str(script_path), "exec"), namespace)
    namespace["_cache"] = lambda: cache
    return namespace


def install_fake_modules(module_map):
    missing = object()
    old_modules = {name: sys.modules.get(name, missing) for name in module_map}
    sys.modules.update(module_map)

    def restore():
        for name, old_module in old_modules.items():
            if old_module is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old_module

    return restore


def edge_character(cache, character_id, part_id=2, count=1):
    character = cache.character_data[character_id]
    character.h_state.orgasm_edge = 1
    character.h_state.orgasm_edge_count[part_id] = count
    return character


def build_fake_modules(cache, template_ids=None, effect_calls=None, immediate_flush=False, original_calls=None):
    effect_calls = effect_calls if effect_calls is not None else []
    original_calls = original_calls if original_calls is not None else []

    script_module = ModuleType("Script")
    config_module = ModuleType("Script.Config")
    core_module = ModuleType("Script.Core")
    design_module = ModuleType("Script.Design")
    system_module = ModuleType("Script.System")
    sex_system_module = ModuleType("Script.System.Sex_System")
    group_sex_panel = ModuleType("Script.System.Sex_System.group_sex_panel")
    settle_module = ModuleType("Script.Settle")
    common_default = ModuleType("Script.Settle.common_default")
    ui_module = ModuleType("Script.UI")
    panel_module = ModuleType("Script.UI.Panel")
    achievement_panel = ModuleType("Script.UI.Panel.achievement_panel")
    manage_power_system_panel = ModuleType("Script.UI.Panel.manage_power_system_panel")

    game_config = SimpleNamespace(
        config_character_state={0: StateConfig(), 1: StateConfig(), 2: StateConfig(), 3: StateConfig(1)},
        config_behavior_effect_data={
            "s_orgasm_small": [210],
            "b_orgasm_small": [211],
            "c_orgasm_small": [212],
            "c_orgasm_strong": [212],
            "c_orgasm_super": [212],
            "plural_orgasm_2": [409],
        },
    )

    def add_orgasm_count(part_id):
        def handle(character_id, change_data):
            cache.character_data[character_id].h_state.orgasm_count[part_id][0] += 1
            cache.character_data[character_id].h_state.orgasm_count[part_id][1] += 1
            effect_calls.append((character_id, part_id))

        return handle

    constant = SimpleNamespace(
        Behavior=SimpleNamespace(
            GROUP_SEX_END="group_sex_end",
            GROUP_SEX_PL_HP_0_END="group_sex_pl_hp_0_end",
            GROUP_SEX_NPC_HP_0_END="group_sex_npc_hp_0_end",
            GROUP_SEX_TO_H="group_sex_to_h",
        ),
        CharacterStatus=SimpleNamespace(STATUS_GROUP_SEX_TO_H=385),
        settle_second_behavior_effect_data={
            210: add_orgasm_count(0),
            211: add_orgasm_count(1),
            212: add_orgasm_count(2),
            409: lambda character_id, change_data: effect_calls.append((character_id, "plural")),
        },
        settle_behavior_effect_data={1503: "desire_original"},
    )

    game_type = SimpleNamespace(CharacterStatusChange=ChangeData, TargetChange=ChangeData)

    def orgasm_settle(character_id, change_data, normal_orgasm_dict=None, extra_orgasm_dict=None, un_count_orgasm_dict=None):
        un_count_orgasm_dict = un_count_orgasm_dict or {}
        character = cache.character_data[character_id]
        for part_id, count in un_count_orgasm_dict.items():
            if not count:
                continue
            if immediate_flush:
                for _ in range(count):
                    character.h_state.orgasm_count[part_id][0] += 1
                    character.h_state.orgasm_count[part_id][1] += 1
                effect_calls.append((character_id, part_id, "batch"))
            else:
                behavior_id = {0: "s_orgasm_small", 1: "b_orgasm_small", 2: "c_orgasm_small"}[part_id]
                character.second_behavior[behavior_id] = 1
                if behavior_id not in character.must_settle_second_behavior_id_list:
                    character.must_settle_second_behavior_id_list.append(behavior_id)

    def unexpected_check_second_effect(*args, **kwargs):
        raise AssertionError("不应调用宽泛的check_second_effect")

    second_behavior = ModuleType("Script.Design.second_behavior")
    second_behavior.orgasm_settle = orgasm_settle
    second_behavior.check_second_effect = unexpected_check_second_effect
    second_behavior.local_bugfix_is_orgasm_batch_settling = lambda character_id: False
    second_behavior.judge_orgasm_degree = lambda now_data: 0

    def character_get_second_behavior(character_id, second_behavior_id, reset=False):
        character = cache.character_data[character_id]
        character.second_behavior.setdefault(second_behavior_id, 0)
        character.second_behavior[second_behavior_id] = 0 if reset else 1

    second_behavior.character_get_second_behavior = character_get_second_behavior

    talk = ModuleType("Script.Design.talk")
    talk.handle_second_talk = lambda character_id, second_behavior_id: original_calls.append(("talk", character_id, second_behavior_id))
    talk.second_behavior_info_text = lambda character_id, second_behavior_id: None

    settle_behavior = ModuleType("Script.Design.settle_behavior")
    settle_behavior.handle_comprehensive_value_effect = lambda *args, **kwargs: original_calls.append(("cve", args))

    map_handle = ModuleType("Script.Design.map_handle")
    map_handle.get_map_system_path_str_for_list = lambda position: "room"

    handle_premise = ModuleType("Script.Design.handle_premise")
    handle_premise.handle_group_sex_mode_on = lambda character_id: cache.group_sex_mode
    handle_premise.handle_unconscious_flag_3 = lambda character_id: False
    handle_premise.handle_self_orgasm_edge = lambda character_id: cache.character_data[character_id].h_state.orgasm_edge == 1
    handle_premise.handle_hidden_sex_mode_ge_1 = lambda character_id: False
    handle_premise.handle_exhibitionism_sex_mode_ge_1 = lambda character_id: False
    handle_premise.handle_unconscious_flag_1 = lambda character_id: False
    handle_premise.handle_self_orgasm_edge_relase_or_time_stop_orgasm_relase = lambda character_id: cache.character_data[character_id].h_state.orgasm_edge == 2
    handle_premise.handle_milk_ge_80 = lambda character_id: False
    handle_premise.handle_urinate_ge_80 = lambda character_id: False
    handle_premise.handle_in_human_power_room = lambda character_id: False
    handle_premise.handle_in_player_scene = lambda character_id: True
    attr_calculation = ModuleType("Script.Design.attr_calculation")
    attr_calculation.get_tired_level = lambda tired_point: 0
    character_behavior = ModuleType("Script.Design.character_behavior")
    character_behavior.judge_character_status = lambda character_id: original_calls.append(("judge_status", character_id))
    common_default.base_chara_experience_common_settle = lambda *args, **kwargs: original_calls.append(("experience", args))
    achievement_panel.achievement_flow = lambda *args, **kwargs: original_calls.append(("achievement", args))
    manage_power_system_panel.store_power_by_human_power = lambda *args, **kwargs: 0

    group_sex_panel.count_group_sex_character_list = lambda: list(template_ids or [])

    config_module.game_config = game_config
    core_module.constant = constant
    core_module.game_type = game_type
    design_module.second_behavior = second_behavior
    design_module.talk = talk
    design_module.settle_behavior = settle_behavior
    design_module.map_handle = map_handle
    design_module.handle_premise = handle_premise
    design_module.attr_calculation = attr_calculation
    design_module.character_behavior = character_behavior
    sex_system_module.group_sex_panel = group_sex_panel
    system_module.Sex_System = sex_system_module
    settle_module.common_default = common_default
    panel_module.achievement_panel = achievement_panel
    panel_module.manage_power_system_panel = manage_power_system_panel
    ui_module.Panel = panel_module
    script_module.Config = config_module
    script_module.Core = core_module
    script_module.Design = design_module
    script_module.System = system_module
    script_module.Settle = settle_module
    script_module.UI = ui_module

    return {
        "Script": script_module,
        "Script.Config": config_module,
        "Script.Core": core_module,
        "Script.Core.constant": constant,
        "Script.Core.game_type": game_type,
        "Script.Design": design_module,
        "Script.Design.second_behavior": second_behavior,
        "Script.Design.talk": talk,
        "Script.Design.settle_behavior": settle_behavior,
        "Script.Design.map_handle": map_handle,
        "Script.Design.handle_premise": handle_premise,
        "Script.Design.attr_calculation": attr_calculation,
        "Script.Design.character_behavior": character_behavior,
        "Script.Settle": settle_module,
        "Script.Settle.common_default": common_default,
        "Script.UI": ui_module,
        "Script.UI.Panel": panel_module,
        "Script.UI.Panel.achievement_panel": achievement_panel,
        "Script.UI.Panel.manage_power_system_panel": manage_power_system_panel,
        "Script.System": system_module,
        "Script.System.Sex_System": sex_system_module,
        "Script.System.Sex_System.group_sex_panel": group_sex_panel,
    }, constant


def test_group_sex_end_releases_pending_edge_before_summary_and_reset():
    namespace = load_local_bugfix()
    cache = Cache(scene_ids=[0, 1])
    cache.character_data[1] = Character(1)
    edge_character(cache, 1, part_id=2, count=1)
    summary_counts = []
    modules, _constant = build_fake_modules(cache, template_ids=[1])
    restore = install_fake_modules(modules)

    def original_529(character_id, add_time, change_data, now_time):
        summary_counts.append(cache.character_data[1].h_state.orgasm_count[2][0])
        cache.character_data[1].h_state.orgasm_edge_count[2] = 0
        cache.character_data[1].h_state.orgasm_edge = 0

    try:
        namespace["_cache"] = lambda: cache
        namespace["_ORIGINAL_GROUP_SEX_END_H_ADD_HPMP_MAX"] = original_529

        namespace["patched_handle_group_sex_end_h_add_hpmp_max"](0, 1, ChangeData(), cache.game_time)

        assert summary_counts == [1]
        assert cache.character_data[1].h_state.orgasm_edge_count[2] == 0
        assert cache.character_data[1].h_state.orgasm_edge == 0
    finally:
        restore()


def test_group_sex_end_releases_multiple_participants_with_stable_dedupe():
    namespace = load_local_bugfix()
    cache = Cache(scene_ids=[0, 1, 2, 3])
    cache.character_data.update({1: Character(1), 2: Character(2), 3: Character(3)})
    edge_character(cache, 1, part_id=1, count=1)
    edge_character(cache, 2, part_id=2, count=1)
    modules, _constant = build_fake_modules(cache, template_ids=[2, 1, 2])
    restore = install_fake_modules(modules)
    seen_participants = []

    try:
        namespace["_cache"] = lambda: cache
        namespace["_ORIGINAL_GROUP_SEX_END_H_ADD_HPMP_MAX"] = lambda *args: seen_participants.extend(namespace["_collect_group_sex_participant_ids"]())

        namespace["patched_handle_group_sex_end_h_add_hpmp_max"](0, 1, ChangeData(), cache.game_time)

        assert seen_participants == [2, 1, 3]
        assert cache.character_data[1].h_state.orgasm_count[1][0] == 1
        assert cache.character_data[2].h_state.orgasm_count[2][0] == 1
    finally:
        restore()


def test_group_sex_end_no_pending_edge_is_noop():
    namespace = load_local_bugfix()
    cache = Cache(scene_ids=[0, 1])
    cache.character_data[1] = Character(1)
    effect_calls = []
    modules, _constant = build_fake_modules(cache, template_ids=[1], effect_calls=effect_calls)
    restore = install_fake_modules(modules)
    original_calls = []

    try:
        namespace["_cache"] = lambda: cache
        namespace["_ORIGINAL_GROUP_SEX_END_H_ADD_HPMP_MAX"] = lambda *args: original_calls.append(args[0])

        namespace["patched_handle_group_sex_end_h_add_hpmp_max"](0, 1, ChangeData(), cache.game_time)

        assert original_calls == [0]
        assert effect_calls == []
    finally:
        restore()


def test_group_sex_player_hp_zero_and_discovered_interrupt_share_529_wrapper():
    namespace = load_local_bugfix()
    cache = Cache(scene_ids=[0, 1])
    cache.character_data[1] = Character(1)
    modules, _constant = build_fake_modules(cache, template_ids=[1])
    restore = install_fake_modules(modules)
    summaries = []

    def original_529(character_id, add_time, change_data, now_time):
        summaries.append((cache.character_data[0].behavior.behavior_id, cache.character_data[1].h_state.orgasm_count[2][0]))

    try:
        namespace["_cache"] = lambda: cache
        namespace["_ORIGINAL_GROUP_SEX_END_H_ADD_HPMP_MAX"] = original_529

        cache.character_data[0].behavior.behavior_id = "group_sex_pl_hp_0_end"
        edge_character(cache, 1, part_id=2, count=1)
        namespace["patched_handle_group_sex_end_h_add_hpmp_max"](0, 1, ChangeData(), cache.game_time)

        cache.character_data[0].behavior.behavior_id = "group_sex_end"
        edge_character(cache, 1, part_id=2, count=1)
        namespace["patched_handle_group_sex_end_h_add_hpmp_max"](0, 1, ChangeData(), cache.game_time)

        assert summaries == [("group_sex_pl_hp_0_end", 1), ("group_sex_end", 2)]
    finally:
        restore()


def test_group_sex_to_h_releases_only_pre_transition_leavers():
    namespace = load_local_bugfix()
    cache = Cache(scene_ids=[0, 1, 2, 3])
    cache.character_data.update({1: Character(1), 2: Character(2), 3: Character(3)})
    edge_character(cache, 1, part_id=2, count=1)
    edge_character(cache, 2, part_id=2, count=1)
    edge_character(cache, 3, part_id=2, count=1)
    modules, _constant = build_fake_modules(cache, template_ids=[1, 2, 3])
    restore = install_fake_modules(modules)

    def fake_call_original(module_name, function_name, character_id):
        cache.character_data[0].target_character_id = 2
        cache.character_data[0].behavior.behavior_id = "group_sex_to_h"

    try:
        namespace["_cache"] = lambda: cache
        namespace["call_original"] = fake_call_original

        namespace["patched_judge_character_tired_sleep"](1)

        assert cache.character_data[1].h_state.orgasm_count[2][0] == 1
        assert cache.character_data[2].h_state.orgasm_count[2][0] == 0
        assert cache.character_data[3].h_state.orgasm_count[2][0] == 1
        assert cache.character_data[2].h_state.orgasm_edge_count[2] == 1
        assert cache.character_data[2].h_state.orgasm_edge == 1
    finally:
        restore()


def test_group_sex_npc_exit_releases_only_exiting_npc_before_528():
    namespace = load_local_bugfix()
    cache = Cache(scene_ids=[0, 1, 2])
    cache.character_data.update({1: Character(1), 2: Character(2)})
    cache.character_data[1].behavior.behavior_id = "group_sex_npc_hp_0_end"
    edge_character(cache, 1, part_id=2, count=1)
    edge_character(cache, 2, part_id=2, count=1)
    modules, _constant = build_fake_modules(cache, template_ids=[1, 2])
    restore = install_fake_modules(modules)
    original_counts = []

    def original_528(character_id, add_time, change_data, now_time):
        original_counts.append(cache.character_data[character_id].h_state.orgasm_count[2][0])

    try:
        namespace["_cache"] = lambda: cache
        namespace["_ORIGINAL_END_H_ADD_HPMP_MAX"] = original_528

        namespace["patched_handle_end_h_add_hpmp_max"](1, 1, ChangeData(), cache.game_time)

        assert original_counts == [1]
        assert cache.character_data[1].h_state.orgasm_edge == 0
        assert cache.character_data[2].h_state.orgasm_count[2][0] == 0
        assert cache.character_data[2].h_state.orgasm_edge_count[2] == 1
    finally:
        restore()


def test_non_group_npc_exit_528_does_not_release_edge_counts():
    namespace = load_local_bugfix()
    cache = Cache(scene_ids=[0, 1])
    cache.character_data[1] = Character(1)
    cache.character_data[1].behavior.behavior_id = "other_1503_user"
    edge_character(cache, 1, part_id=2, count=1)
    effect_calls = []
    modules, _constant = build_fake_modules(cache, template_ids=[1], effect_calls=effect_calls)
    restore = install_fake_modules(modules)

    try:
        namespace["_cache"] = lambda: cache
        namespace["_ORIGINAL_END_H_ADD_HPMP_MAX"] = lambda *args: None

        namespace["patched_handle_end_h_add_hpmp_max"](1, 1, ChangeData(), cache.game_time)

        assert effect_calls == []
        assert cache.character_data[1].h_state.orgasm_edge == 1
        assert cache.character_data[1].h_state.orgasm_edge_count[2] == 1
    finally:
        restore()


def test_fallback_flush_applies_only_release_generated_second_effects():
    namespace = load_local_bugfix()
    cache = Cache(scene_ids=[0, 1])
    cache.character_data[1] = Character(1)
    cache.character_data[1].second_behavior["old_orgasm"] = 1
    cache.character_data[1].second_behavior["mark_test"] = 1
    edge_character(cache, 1, part_id=2, count=1)
    effect_calls = []
    modules, _constant = build_fake_modules(cache, template_ids=[1], effect_calls=effect_calls)
    restore = install_fake_modules(modules)

    try:
        namespace["_cache"] = lambda: cache

        released = namespace["_release_group_edge_for_character"](1, ChangeData(), owner_character_id=0, group_context_ids=[1])

        assert released is True
        assert effect_calls == [(1, 2)]
        assert cache.character_data[1].h_state.orgasm_count[2][0] == 1
        assert cache.character_data[1].second_behavior["old_orgasm"] == 1
        assert cache.character_data[1].second_behavior["mark_test"] == 1
        assert cache.character_data[1].second_behavior["c_orgasm_small"] == 0
    finally:
        restore()


def test_release_clears_preexisting_edge_second_behavior_queue():
    namespace = load_local_bugfix()
    cache = Cache(scene_ids=[0, 1])
    cache.character_data[1] = Character(1)
    cache.character_data[1].second_behavior["c_orgasm_edge"] = 1
    cache.character_data[1].must_settle_second_behavior_id_list.append("c_orgasm_edge")
    cache.character_data[1].must_show_second_behavior_id_list.append("c_orgasm_edge")
    edge_character(cache, 1, part_id=2, count=1)
    modules, _constant = build_fake_modules(cache, template_ids=[1])
    restore = install_fake_modules(modules)

    try:
        namespace["_cache"] = lambda: cache

        released = namespace["_release_group_edge_for_character"](1, ChangeData(), owner_character_id=0, group_context_ids=[1])

        assert released is True
        assert cache.character_data[1].h_state.orgasm_count[2][0] == 1
        assert cache.character_data[1].second_behavior["c_orgasm_edge"] == 0
        assert "c_orgasm_edge" not in cache.character_data[1].must_settle_second_behavior_id_list
        assert "c_orgasm_edge" not in cache.character_data[1].must_show_second_behavior_id_list
    finally:
        restore()


def test_batch_immediate_flush_is_not_applied_twice():
    namespace = load_local_bugfix()
    cache = Cache(scene_ids=[0, 1])
    cache.character_data[1] = Character(1)
    edge_character(cache, 1, part_id=2, count=2)
    effect_calls = []
    modules, _constant = build_fake_modules(cache, template_ids=[1], effect_calls=effect_calls, immediate_flush=True)
    restore = install_fake_modules(modules)

    try:
        namespace["_cache"] = lambda: cache

        released = namespace["_release_group_edge_for_character"](1, ChangeData(), owner_character_id=0, group_context_ids=[1])

        assert released is True
        assert cache.character_data[1].h_state.orgasm_count[2][0] == 2
        assert effect_calls == [(1, 2, "batch"), (1, 2, "batch")]
        assert "c_orgasm_small" not in cache.character_data[1].second_behavior
    finally:
        restore()


def test_real_h_orgasm_batch_release_preserves_multi_count_edges():
    namespace = load_local_bugfix()
    cache = Cache(scene_ids=[0, 1])
    cache.character_data[1] = Character(1)
    edge_character(cache, 1, part_id=2, count=2)
    effect_calls = []
    modules, constant = build_fake_modules(cache, template_ids=[1], effect_calls=effect_calls)
    h_batch_namespace = load_h_orgasm_batch(cache, modules["Script.Config"].game_config, constant)
    modules["Script.Design.second_behavior"].orgasm_settle = h_batch_namespace["patched_orgasm_settle"]
    restore = install_fake_modules(modules)

    try:
        namespace["_cache"] = lambda: cache

        released = namespace["_release_group_edge_for_character"](1, ChangeData(), owner_character_id=0, group_context_ids=[1])

        assert released is True
        assert cache.character_data[1].h_state.orgasm_count[2][0] == 2
        assert effect_calls == [(1, 2), (1, 2)]
        assert cache.character_data[1].h_state.orgasm_edge_count[2] == 0
        assert cache.character_data[1].h_state.orgasm_edge == 0
    finally:
        restore()


def test_real_h_orgasm_batch_release_preserves_three_count_bonus():
    namespace = load_local_bugfix()
    cache = Cache(scene_ids=[0, 1])
    cache.character_data[1] = Character(1)
    edge_character(cache, 1, part_id=2, count=3)
    effect_calls = []
    modules, constant = build_fake_modules(cache, template_ids=[1], effect_calls=effect_calls)
    h_batch_namespace = load_h_orgasm_batch(cache, modules["Script.Config"].game_config, constant)
    modules["Script.Design.second_behavior"].orgasm_settle = h_batch_namespace["patched_orgasm_settle"]
    restore = install_fake_modules(modules)

    try:
        namespace["_cache"] = lambda: cache

        released = namespace["_release_group_edge_for_character"](1, ChangeData(), owner_character_id=0, group_context_ids=[1])

        assert released is True
        assert cache.character_data[1].h_state.orgasm_count[2][0] == 4
        assert effect_calls == [(1, 2), (1, 2), (1, 2), (1, 2)]
        assert cache.character_data[1].h_state.orgasm_edge_count[2] == 0
        assert cache.character_data[1].h_state.orgasm_edge == 0
    finally:
        restore()


def test_real_h_orgasm_batch_release_runs_plural_effect_once_for_multi_part_counts():
    namespace = load_local_bugfix()
    cache = Cache(scene_ids=[0, 1])
    cache.character_data[1] = Character(1)
    edge_character(cache, 1, part_id=1, count=2)
    edge_character(cache, 1, part_id=2, count=2)
    effect_calls = []
    modules, constant = build_fake_modules(cache, template_ids=[1], effect_calls=effect_calls)
    h_batch_namespace = load_h_orgasm_batch(cache, modules["Script.Config"].game_config, constant)
    modules["Script.Design.second_behavior"].orgasm_settle = h_batch_namespace["patched_orgasm_settle"]
    restore = install_fake_modules(modules)

    try:
        namespace["_cache"] = lambda: cache

        released = namespace["_release_group_edge_for_character"](1, ChangeData(), owner_character_id=0, group_context_ids=[1])

        assert released is True
        assert cache.character_data[1].h_state.orgasm_count[1][0] == 2
        assert cache.character_data[1].h_state.orgasm_count[2][0] == 2
        assert effect_calls.count((1, "plural")) == 1
        assert effect_calls.count((1, 1)) == 2
        assert effect_calls.count((1, 2)) == 2
    finally:
        restore()


def test_stale_template_participant_is_cleaned_without_summary_inclusion():
    namespace = load_local_bugfix()
    cache = Cache(scene_ids=[0, 1])
    cache.character_data[1] = Character(1)
    cache.character_data[4] = Character(4)
    cache.character_data[4].sp_flag.is_h = False
    edge_character(cache, 4, part_id=2, count=1)
    modules, _constant = build_fake_modules(cache, template_ids=[4])
    restore = install_fake_modules(modules)
    summary_scene_ids = []

    def original_529(character_id, add_time, change_data, now_time):
        summary_scene_ids.extend(cache.scene_data["room"].character_list)

    try:
        namespace["_cache"] = lambda: cache
        namespace["_ORIGINAL_GROUP_SEX_END_H_ADD_HPMP_MAX"] = original_529

        namespace["patched_handle_group_sex_end_h_add_hpmp_max"](0, 1, ChangeData(), cache.game_time)

        assert 4 not in summary_scene_ids
        assert cache.character_data[4].h_state.orgasm_edge_count[2] == 0
        assert cache.character_data[4].h_state.orgasm_edge == 0
    finally:
        restore()


def test_recover_from_unconscious_releases_before_clear_and_mode_off_without_double_release():
    namespace = load_local_bugfix()
    cache = Cache(scene_ids=[0, 1, 2])
    cache.character_data[0].target_character_id = 1
    cache.character_data.update({1: Character(1), 2: Character(2)})
    cache.character_data[1].sp_flag.unconscious_h = 1
    edge_character(cache, 1, part_id=2, count=1)
    edge_character(cache, 2, part_id=2, count=1)
    effect_calls = []
    modules, _constant = build_fake_modules(cache, template_ids=[1, 2], effect_calls=effect_calls)
    restore = install_fake_modules(modules)
    events = []

    def fake_call_original(module_name, function_name, character_id, info_text=""):
        events.append(("clear_template", cache.character_data[1].h_state.orgasm_edge_count[2], cache.character_data[2].h_state.orgasm_edge_count[2]))
        events.append(("mode_off", cache.character_data[1].h_state.orgasm_edge, cache.character_data[2].h_state.orgasm_edge))
        return "original"

    try:
        namespace["_cache"] = lambda: cache
        namespace["call_original"] = fake_call_original

        result = namespace["patched_recover_from_unconscious_h"](0)

        assert result == "original"
        assert events == [("clear_template", 0, 0), ("mode_off", 0, 0)]
        assert effect_calls == [(1, 2), (2, 2)]
        assert cache.character_data[1].h_state.orgasm_count[2][0] == 1
        assert cache.character_data[2].h_state.orgasm_count[2][0] == 1
    finally:
        restore()


def test_group_edge_registry_patch_does_not_patch_shared_1503():
    namespace = load_local_bugfix()
    cache = Cache()
    modules, constant = build_fake_modules(cache)
    settle_module = ModuleType("Script.Settle")
    settle_default = ModuleType("Script.Settle.default")
    settle_default.handle_group_sex_end_h_add_hpmp_max = lambda *args: "529"
    settle_default.handle_end_h_add_hpmp_max = lambda *args: "528"
    settle_module.default = settle_default
    modules["Script.Settle"] = settle_module
    modules["Script.Settle.default"] = settle_default
    constant.settle_behavior_effect_data[528] = settle_default.handle_end_h_add_hpmp_max
    constant.settle_behavior_effect_data[529] = settle_default.handle_group_sex_end_h_add_hpmp_max
    original_1503 = constant.settle_behavior_effect_data[1503]
    restore = install_fake_modules(modules)

    try:
        namespace["_cache"] = lambda: cache

        namespace["_patch_group_sex_edge_release_effects"]()

        assert constant.settle_behavior_effect_data[1503] is original_1503
        assert constant.settle_behavior_effect_data[528] is namespace["patched_handle_end_h_add_hpmp_max"]
        assert constant.settle_behavior_effect_data[529] is namespace["patched_handle_group_sex_end_h_add_hpmp_max"]
    finally:
        restore()


def test_existing_helpers_still_stop_interrupted_move_and_delegate_tired_sleep():
    namespace = load_local_bugfix()
    cache = Cache(scene_ids=[0, 1])
    cache.group_sex_mode = False
    cache.character_data[1] = Character(1)
    calls = []
    modules, _constant = build_fake_modules(cache, template_ids=[])
    restore = install_fake_modules(modules)

    try:
        namespace["_cache"] = lambda: cache
        namespace["call_original"] = lambda module_name, function_name, character_id: calls.append((module_name, function_name, character_id))

        cache.character_data[0].sp_flag.move_stop = True
        cache.character_data[0].behavior.move_target = ["a"]
        cache.character_data[0].behavior.move_final_target = ["b"]

        assert namespace["_stop_player_move_if_interrupted"](cache.character_data[0]) is True
        assert cache.character_data[0].behavior.move_target == []
        assert cache.character_data[0].behavior.move_final_target == []

        namespace["patched_judge_character_tired_sleep"](1)

        assert calls == [("Script.Design.handle_npc_ai", "judge_character_tired_sleep", 1)]
    finally:
        restore()


if __name__ == "__main__":
    test_group_sex_end_releases_pending_edge_before_summary_and_reset()
    test_group_sex_end_releases_multiple_participants_with_stable_dedupe()
    test_group_sex_end_no_pending_edge_is_noop()
    test_group_sex_player_hp_zero_and_discovered_interrupt_share_529_wrapper()
    test_group_sex_to_h_releases_only_pre_transition_leavers()
    test_group_sex_npc_exit_releases_only_exiting_npc_before_528()
    test_non_group_npc_exit_528_does_not_release_edge_counts()
    test_fallback_flush_applies_only_release_generated_second_effects()
    test_release_clears_preexisting_edge_second_behavior_queue()
    test_batch_immediate_flush_is_not_applied_twice()
    test_real_h_orgasm_batch_release_preserves_multi_count_edges()
    test_real_h_orgasm_batch_release_preserves_three_count_bonus()
    test_real_h_orgasm_batch_release_runs_plural_effect_once_for_multi_part_counts()
    test_stale_template_participant_is_cleaned_without_summary_inclusion()
    test_recover_from_unconscious_releases_before_clear_and_mode_off_without_double_release()
    test_group_edge_registry_patch_does_not_patch_shared_1503()
    test_existing_helpers_still_stop_interrupted_move_and_delegate_tired_sleep()
    print("group sex edge release local_bugfix mod tests passed", flush=True)
