from collections import defaultdict
import datetime
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace


class Character:
    def __init__(self, target_character_id):
        self.target_character_id = target_character_id
        self.name = "测试干员"
        self.behavior = Behavior()
        self.sp_flag = SpFlag()
        self.hit_point = 10
        self.tired_point = 0


class Behavior:
    def __init__(self):
        self.behavior_id = "share_blankly"
        self.duration = 1
        self.h_interrupt_chara_name = ""
        self.move_final_target = []


class SpFlag:
    def __init__(self):
        self.is_h = False
        self.tired = False
        self.masturebate = 0
        self.move_stop = False


class Cache:
    def __init__(self, target_character_id):
        self.character_data = {0: Character(target_character_id)}
        self.game_time = datetime.datetime(2026, 1, 1, 12, 0)
        self.over_behavior_character = set()
        self.pl_pre_behavior_instruce = []


class Hypnosis:
    def __init__(self):
        self.pain_as_pleasure = False


class HState:
    def __init__(self):
        self.extra_orgasm_count = 0
        self.npc_active_h = False


class StatusCharacter(Character):
    def __init__(self, target_character_id=0):
        super().__init__(target_character_id)
        self.dead = False
        self.name = "测试干员"
        self.hypnosis = Hypnosis()
        self.status_data = defaultdict(int)
        self.ability = defaultdict(int)
        self.h_state = HState()


class ChangeData:
    def __init__(self):
        self.status_data = defaultdict(int)


def load_local_bugfix():
    mod_root = Path(__file__).resolve().parents[1]
    script_path = mod_root / "scripts" / "local_bugfix.py"
    namespace = {"__name__": "mod_local_bugfix_test"}
    source = script_path.read_text(encoding="utf-8").replace("\n_install_registry_patches()\n", "\n")
    exec(compile(source, str(script_path), "exec"), namespace)
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


def test_npc_ai_in_group_sex_preserves_player_target():
    namespace = load_local_bugfix()
    cache = Cache(target_character_id=7)

    def fake_call_original(module_name, function_name, character_id):
        assert function_name == "npc_ai_in_group_sex"
        cache.character_data[0].target_character_id = character_id
        return "ok"

    namespace["_cache"] = lambda: cache
    namespace["call_original"] = fake_call_original

    result = namespace["patched_npc_ai_in_group_sex"](3)

    assert result == "ok"
    assert cache.character_data[0].target_character_id == 7


def test_npc_ai_in_group_sex_type_3_preserves_player_target():
    namespace = load_local_bugfix()
    cache = Cache(target_character_id=10)

    def fake_call_original(module_name, function_name):
        assert function_name == "npc_ai_in_group_sex_type_3"
        cache.character_data[0].target_character_id = 42
        return None

    namespace["_cache"] = lambda: cache
    namespace["call_original"] = fake_call_original

    namespace["patched_npc_ai_in_group_sex_type_3"]()

    assert cache.character_data[0].target_character_id == 10


def test_player_target_is_restored_when_original_raises():
    namespace = load_local_bugfix()
    cache = Cache(target_character_id=5)

    def fail_after_mutation():
        cache.character_data[0].target_character_id = 99
        raise RuntimeError("boom")

    namespace["_cache"] = lambda: cache

    try:
        namespace["_call_with_preserved_player_target"](fail_after_mutation)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError")

    assert cache.character_data[0].target_character_id == 5


def test_npc_active_h_delegates_to_original_after_stopping_stale_move():
    namespace = load_local_bugfix()
    cache = Cache(target_character_id=1)
    pl_data = cache.character_data[0]
    pl_data.behavior.behavior_id = "move"
    pl_data.behavior.move_final_target = ["目标房间"]
    calls = []

    script_module = ModuleType("Script")
    core_module = ModuleType("Script.Core")
    core_module.constant = SimpleNamespace(Behavior=SimpleNamespace(MOVE="move"))
    script_module.Core = core_module
    restore = install_fake_modules({"Script": script_module, "Script.Core": core_module})

    def fake_call_original(module_name, function_name):
        calls.append((module_name, function_name, pl_data.sp_flag.move_stop, list(pl_data.behavior.move_final_target)))
        return "original-active-h"

    try:
        namespace["_cache"] = lambda: cache
        namespace["call_original"] = fake_call_original

        result = namespace["patched_npc_active_h"]()

        assert result == "original-active-h"
        assert calls == [(namespace["HN_AI_H"], "npc_active_h", True, [])]
        assert pl_data.target_character_id == 1
    finally:
        restore()


def test_mind_control_active_h_talk_bypasses_unconscious_gate():
    namespace = load_local_bugfix()
    cache = Cache(target_character_id=1)
    cache.character_data[1] = StatusCharacter()
    cache.character_data[1].sp_flag.unconscious_h = 7
    cache.character_data[1].h_state.npc_active_h = True
    calls = []

    def fake_original(premises, character_id, calculated, weight_all_to_1_flag=False, unconscious_pass_flag=False):
        calls.append((set(premises), character_id, unconscious_pass_flag))
        if not unconscious_pass_flag:
            return 0, calculated
        return 1, calculated

    namespace["_cache"] = lambda: cache
    namespace["_ORIGINAL_GET_WEIGHT_FROM_PREMISE_DICT"] = fake_original

    weight, calculated = namespace["patched_get_weight_from_premise_dict"]({"t_npc_active_h"}, 0, {})

    assert weight == 1
    assert calculated == {}
    assert calls == [({"t_npc_active_h"}, 0, True)]


def test_hypnosis_target_generic_talk_bypasses_unconscious_gate():
    namespace = load_local_bugfix()
    calls = []

    def fake_original(premises, character_id, calculated, weight_all_to_1_flag=False, unconscious_pass_flag=False):
        calls.append((set(premises), character_id, unconscious_pass_flag))
        if not unconscious_pass_flag:
            return 0, calculated
        return 1, calculated

    namespace["_ORIGINAL_GET_WEIGHT_FROM_PREMISE_DICT"] = fake_original
    for hypnosis_flag in (4, 5, 6, 7):
        cache = Cache(target_character_id=1)
        cache.character_data[1] = StatusCharacter()
        cache.character_data[1].sp_flag.unconscious_h = hypnosis_flag
        namespace["_cache"] = lambda cache=cache: cache

        weight, calculated = namespace["patched_get_weight_from_premise_dict"]({"high_1"}, 0, {})

        assert weight == 1
        assert calculated == {}

    assert calls == [
        ({"high_1"}, 0, True),
        ({"high_1"}, 0, True),
        ({"high_1"}, 0, True),
        ({"high_1"}, 0, True),
    ]


def test_sleep_target_generic_talk_keeps_unconscious_gate():
    namespace = load_local_bugfix()
    cache = Cache(target_character_id=1)
    cache.character_data[1] = StatusCharacter()
    cache.character_data[1].sp_flag.unconscious_h = 1
    calls = []

    def fake_original(premises, character_id, calculated, weight_all_to_1_flag=False, unconscious_pass_flag=False):
        calls.append((set(premises), character_id, unconscious_pass_flag))
        if not unconscious_pass_flag:
            return 0, calculated
        return 1, calculated

    namespace["_cache"] = lambda: cache
    namespace["_ORIGINAL_GET_WEIGHT_FROM_PREMISE_DICT"] = fake_original

    weight, calculated = namespace["patched_get_weight_from_premise_dict"]({"high_1"}, 0, {})

    assert weight == 0
    assert calculated == {}
    assert calls == [({"high_1"}, 0, False)]


def test_hypnosis_cancel_clears_pain_as_pleasure():
    namespace = load_local_bugfix()
    cache = Cache(target_character_id=2)
    cache.character_data[2] = StatusCharacter()
    cache.character_data[2].hypnosis.pain_as_pleasure = True
    calls = []

    def fake_original(character_id, add_time, change_data, now_time):
        calls.append((character_id, add_time, now_time))

    namespace["_cache"] = lambda: cache
    namespace["_ORIGINAL_HYPNOSIS_CANCEL_EFFECT"] = fake_original

    namespace["patched_handle_hypnosis_cancel"](0, 1, ChangeData(), "now")

    assert calls == [(0, 1, "now")]
    assert cache.character_data[2].hypnosis.pain_as_pleasure is False


def test_pain_decrease_keeps_pain_as_pain_when_pain_as_pleasure_is_on():
    namespace = load_local_bugfix()
    cache = Cache(target_character_id=1)
    cache.character_data[1] = StatusCharacter()
    cache.character_data[1].hypnosis.pain_as_pleasure = True
    calls = []

    def fake_original(character_id, add_time, state_id, base_value=30, **kwargs):
        calls.append(
            {
                "character_id": character_id,
                "add_time": add_time,
                "state_id": state_id,
                "base_value": base_value,
                "flag_during_call": cache.character_data[character_id].hypnosis.pain_as_pleasure,
            }
        )

    namespace["_cache"] = lambda: cache
    namespace["_ORIGINAL_BASE_STATE_COMMON_SETTLE"] = fake_original

    namespace["patched_base_chara_state_common_settle"](1, -100, 17, base_value=0, change_data=ChangeData())

    assert calls == [
        {
            "character_id": 1,
            "add_time": -100,
            "state_id": 17,
            "base_value": 0,
            "flag_during_call": False,
        }
    ]
    assert cache.character_data[1].hypnosis.pain_as_pleasure is True


def test_direct_pain_increase_converts_to_psychological_pleasure():
    namespace = load_local_bugfix()
    cache = Cache(target_character_id=1)
    cache.character_data[1] = StatusCharacter()
    cache.character_data[1].hypnosis.pain_as_pleasure = True
    cache.character_data[1].ability[36] = 4
    calls = []

    def fake_original(character_id, add_time, state_id, base_value=30, ability_level=-1, tenths_add=True, change_data=None, change_data_to_target_change=None, **kwargs):
        calls.append(
            {
                "character_id": character_id,
                "add_time": add_time,
                "state_id": state_id,
                "base_value": base_value,
                "ability_level": ability_level,
                "tenths_add": tenths_add,
                "change_data": change_data,
                "change_data_to_target_change": change_data_to_target_change,
            }
        )

    namespace["_cache"] = lambda: cache
    namespace["_ORIGINAL_BASE_STATE_COMMON_SETTLE"] = fake_original
    change_data = ChangeData()

    converted = namespace["_settle_direct_pain_increase"](1, 123, change_data)

    assert converted is True
    assert calls == [
        {
            "character_id": 1,
            "add_time": 123,
            "state_id": 23,
            "base_value": 0,
            "ability_level": 4,
            "tenths_add": False,
            "change_data": change_data,
            "change_data_to_target_change": None,
        }
    ]
    assert 17 not in change_data.status_data


def test_add_small_pain_second_effect_uses_direct_pain_conversion():
    namespace = load_local_bugfix()
    cache = Cache(target_character_id=1)
    cache.character_data[1] = StatusCharacter()
    cache.character_data[1].hypnosis.pain_as_pleasure = True
    cache.character_data[1].status_data[17] = 100
    cache.character_data[1].ability[15] = 2
    calls = []

    def fake_original(character_id, add_time, state_id, base_value=30, ability_level=-1, tenths_add=True, change_data=None, change_data_to_target_change=None, **kwargs):
        calls.append((character_id, add_time, state_id, base_value, ability_level, tenths_add, change_data))

    def unexpected_original_effect(character_id, change_data):
        raise AssertionError("direct pain effect should not add pain while pain_as_pleasure is on")

    namespace["_cache"] = lambda: cache
    namespace["_ORIGINAL_BASE_STATE_COMMON_SETTLE"] = fake_original
    namespace["_ORIGINAL_SECOND_EFFECTS"] = {270: unexpected_original_effect}
    namespace["_get_mark_debuff_adjust"] = lambda ability_level: 1
    change_data = ChangeData()

    namespace["patched_handle_add_small_pain"](1, change_data)

    assert calls == [(1, 25, 23, 0, 0, False, change_data)]
    assert change_data.status_data[17] == 0


def test_group_sex_masturbation_target_runs_once_per_player_action():
    namespace = load_local_bugfix()
    cache = Cache(target_character_id=1)
    cache.character_data[1] = Character(target_character_id=1)
    cache.character_data[1].sp_flag.is_h = True
    cache.character_data[1].sp_flag.masturebate = 3
    cache.pl_pre_behavior_instruce = ["group_sex"]
    state_machine_calls = []

    script_module = ModuleType("Script")
    config_module = ModuleType("Script.Config")
    core_module = ModuleType("Script.Core")
    design_module = ModuleType("Script.Design")
    game_config = SimpleNamespace(config_target={"default91": SimpleNamespace(state_machine_id=91)})
    constant = SimpleNamespace(handle_state_machine_data={91: lambda character_id: state_machine_calls.append(character_id)})
    handle_npc_ai = SimpleNamespace(search_target=lambda *args, **kwargs: ("default91", 100, True, {}))
    handle_premise = SimpleNamespace(
        handle_group_sex_mode_on=lambda character_id: True,
        handle_masturebate_flag_3=lambda character_id: True,
        settle_chara_unnormal_flag=lambda character_id, flag_id: None,
    )
    config_module.game_config = game_config
    core_module.constant = constant
    design_module.handle_npc_ai = handle_npc_ai
    design_module.handle_premise = handle_premise
    script_module.Config = config_module
    script_module.Core = core_module
    script_module.Design = design_module
    restore = install_fake_modules(
        {
            "Script": script_module,
            "Script.Config": config_module,
            "Script.Core": core_module,
            "Script.Design": design_module,
        }
    )

    try:
        namespace["_cache"] = lambda: cache

        namespace["patched_find_character_target"](1, cache.game_time)
        namespace["patched_find_character_target"](1, cache.game_time)

        assert state_machine_calls == [1]
        assert 1 in cache.over_behavior_character

        cache.over_behavior_character = set()
        cache.game_time += datetime.timedelta(minutes=10)
        namespace["patched_find_character_target"](1, cache.game_time)

        assert state_machine_calls == [1, 1]
    finally:
        restore()


def test_group_sex_masturbation_reroute_blocks_regenerated_marker_in_same_action():
    namespace = load_local_bugfix()
    cache = Cache(target_character_id=1)
    cache.character_data[1] = Character(target_character_id=1)
    cache.character_data[1].sp_flag.is_h = True
    cache.character_data[1].sp_flag.masturebate = 3
    state_machine_calls = []

    def run_default91(character_id):
        character_data = cache.character_data[character_id]
        character_data.behavior.behavior_id = "masturebate"
        character_data.behavior.duration = 10
        state_machine_calls.append(character_id)

    script_module = ModuleType("Script")
    config_module = ModuleType("Script.Config")
    core_module = ModuleType("Script.Core")
    design_module = ModuleType("Script.Design")
    game_config = SimpleNamespace(config_target={"default91": SimpleNamespace(state_machine_id=91)})
    constant = SimpleNamespace(handle_state_machine_data={91: run_default91})
    handle_npc_ai = SimpleNamespace(search_target=lambda *args, **kwargs: ("default91", 100, True, {}))
    handle_premise = SimpleNamespace(
        handle_group_sex_mode_on=lambda character_id: True,
        handle_masturebate_flag_3=lambda character_id: cache.character_data[character_id].sp_flag.masturebate == 3,
        settle_chara_unnormal_flag=lambda character_id, flag_id: None,
    )
    config_module.game_config = game_config
    core_module.constant = constant
    design_module.handle_npc_ai = handle_npc_ai
    design_module.handle_premise = handle_premise
    script_module.Config = config_module
    script_module.Core = core_module
    script_module.Design = design_module
    restore = install_fake_modules(
        {
            "Script": script_module,
            "Script.Config": config_module,
            "Script.Core": core_module,
            "Script.Design": design_module,
        }
    )

    try:
        namespace["_cache"] = lambda: cache

        namespace["patched_find_character_target"](1, cache.game_time)
        assert state_machine_calls == [1]
        assert cache.character_data[1].behavior.behavior_id == "masturebate"

        # 模拟正式自慰结算完成：效果 456 清理自慰标记，角色回到空闲。
        cache.character_data[1].sp_flag.masturebate = 0
        cache.character_data[1].behavior.behavior_id = "share_blankly"
        cache.character_data[1].behavior.duration = 1

        # 同一次玩家行动内，群交 AI 因无空位再次生成自慰意图。
        cache.character_data[1].sp_flag.masturebate = 3
        namespace["patched_find_character_target"](1, cache.game_time)

        assert state_machine_calls == [1]
        assert 1 in cache.over_behavior_character

        cache.over_behavior_character = set()
        cache.character_data[1].sp_flag.masturebate = 3
        namespace["patched_find_character_target"](1, cache.game_time)

        assert state_machine_calls == [1, 1]
    finally:
        restore()


def test_blocked_group_sex_masturbation_clears_stale_marker_before_next_action():
    namespace = load_local_bugfix()
    cache = Cache(target_character_id=1)
    cache.character_data[1] = Character(target_character_id=1)
    cache.character_data[1].sp_flag.is_h = True
    cache.character_data[1].sp_flag.masturebate = 3
    calls = []
    settle_calls = []

    script_module = ModuleType("Script")
    config_module = ModuleType("Script.Config")
    core_module = ModuleType("Script.Core")
    design_module = ModuleType("Script.Design")
    game_config = SimpleNamespace(config_target={"default91": SimpleNamespace(state_machine_id=91)})
    constant = SimpleNamespace(handle_state_machine_data={91: lambda character_id: calls.append(character_id)})
    handle_npc_ai = SimpleNamespace(search_target=lambda *args, **kwargs: ("default91", 100, True, {}))
    handle_premise = SimpleNamespace(
        handle_group_sex_mode_on=lambda character_id: True,
        handle_masturebate_flag_3=lambda character_id: cache.character_data[character_id].sp_flag.masturebate == 3,
        settle_chara_unnormal_flag=lambda character_id, flag_id: settle_calls.append((character_id, flag_id)),
    )
    config_module.game_config = game_config
    core_module.constant = constant
    design_module.handle_npc_ai = handle_npc_ai
    design_module.handle_premise = handle_premise
    script_module.Config = config_module
    script_module.Core = core_module
    script_module.Design = design_module
    restore = install_fake_modules(
        {
            "Script": script_module,
            "Script.Config": config_module,
            "Script.Core": core_module,
            "Script.Design": design_module,
        }
    )

    try:
        namespace["_cache"] = lambda: cache
        original_calls = []
        namespace["call_original"] = lambda module_name, function_name, character_id, now_time: original_calls.append((module_name, function_name, character_id, now_time))

        namespace["patched_find_character_target"](1, cache.game_time)
        assert calls == [1]

        cache.character_data[1].sp_flag.masturebate = 3
        namespace["patched_find_character_target"](1, cache.game_time)
        assert calls == [1]
        assert cache.character_data[1].sp_flag.masturebate == 0
        assert settle_calls == [(1, 1)]

        cache.over_behavior_character = set()
        namespace["patched_find_character_target"](1, cache.game_time)
        assert calls == [1]
        assert original_calls == [("Script.Design.handle_npc_ai", "find_character_target", 1, cache.game_time)]

        cache.character_data[1].sp_flag.masturebate = 3
        namespace["patched_find_character_target"](1, cache.game_time)
        assert calls == [1, 1]
    finally:
        restore()


def test_unavailable_group_sex_masturbation_target_clears_marker():
    namespace = load_local_bugfix()
    cache = Cache(target_character_id=1)
    cache.character_data[1] = Character(target_character_id=1)
    cache.character_data[1].sp_flag.is_h = True
    cache.character_data[1].sp_flag.masturebate = 3
    settle_calls = []

    script_module = ModuleType("Script")
    config_module = ModuleType("Script.Config")
    core_module = ModuleType("Script.Core")
    design_module = ModuleType("Script.Design")
    config_module.game_config = SimpleNamespace(config_target={})
    core_module.constant = SimpleNamespace(handle_state_machine_data={})
    design_module.handle_npc_ai = SimpleNamespace(search_target=lambda *args, **kwargs: ("", 0, False, {}))
    design_module.handle_premise = SimpleNamespace(
        handle_group_sex_mode_on=lambda character_id: True,
        handle_masturebate_flag_3=lambda character_id: cache.character_data[character_id].sp_flag.masturebate == 3,
        settle_chara_unnormal_flag=lambda character_id, flag_id: settle_calls.append((character_id, flag_id)),
    )
    script_module.Config = config_module
    script_module.Core = core_module
    script_module.Design = design_module
    restore = install_fake_modules(
        {
            "Script": script_module,
            "Script.Config": config_module,
            "Script.Core": core_module,
            "Script.Design": design_module,
        }
    )

    try:
        namespace["_cache"] = lambda: cache

        namespace["patched_find_character_target"](1, cache.game_time)

        assert cache.character_data[1].sp_flag.masturebate == 0
        assert settle_calls == [(1, 1)]
        assert 1 in cache.over_behavior_character
    finally:
        restore()


def test_tired_group_sex_discoverer_should_auto_leave():
    namespace = load_local_bugfix()
    cache = Cache(target_character_id=1)
    cache.character_data[2] = Character(target_character_id=2)
    cache.character_data[2].tired_point = 80

    script_module = ModuleType("Script")
    design_module = ModuleType("Script.Design")
    attr_calculation = SimpleNamespace(get_tired_level=lambda tired_point: 2)
    handle_premise = SimpleNamespace(handle_group_sex_mode_on=lambda character_id: True)
    design_module.attr_calculation = attr_calculation
    design_module.handle_premise = handle_premise
    script_module.Design = design_module
    restore = install_fake_modules({"Script": script_module, "Script.Design": design_module})

    try:
        namespace["_cache"] = lambda: cache

        assert namespace["_should_auto_leave_group_sex_discovery"](2) is True

        handle_premise.handle_group_sex_mode_on = lambda character_id: False
        assert namespace["_should_auto_leave_group_sex_discovery"](2) is False
    finally:
        restore()


def test_auto_leave_group_sex_discovery_uses_existing_leave_behavior():
    namespace = load_local_bugfix()
    cache = Cache(target_character_id=1)
    cache.character_data[2] = Character(target_character_id=2)
    cache.character_data[2].name = "发现者"
    cache.character_data[0].target_character_id = 1
    cache.now_panel_id = "sex_be_discovered"
    calls = []

    script_module = ModuleType("Script")
    config_module = ModuleType("Script.Config")
    core_module = ModuleType("Script.Core")
    settle_module = ModuleType("Script.Settle")
    game_config = SimpleNamespace(config_behavior={"see_h_and_leave": SimpleNamespace(duration=7)})
    constant = SimpleNamespace(Behavior=SimpleNamespace(SEE_H_AND_LEAVE="see_h_and_leave"), Panel=SimpleNamespace(IN_SCENE="in_scene"))
    game_type = SimpleNamespace(CharacterStatusChange=ChangeData)
    default = SimpleNamespace(
        handle_masturebate_to_pl_flag_0=lambda character_id, add_time, change_data, now_time: calls.append(("masturebate", character_id, now_time)),
        handle_target_to_player=lambda character_id, add_time, change_data, now_time: calls.append(("target", character_id, now_time)),
        handle_see_pl_h=lambda character_id, add_time, change_data, now_time: calls.append(("see", character_id, now_time)),
    )
    config_module.game_config = game_config
    core_module.constant = constant
    core_module.game_type = game_type
    settle_module.default = default
    script_module.Config = config_module
    script_module.Core = core_module
    script_module.Settle = settle_module
    restore = install_fake_modules(
        {
            "Script": script_module,
            "Script.Config": config_module,
            "Script.Core": core_module,
            "Script.Settle": settle_module,
        }
    )

    try:
        namespace["_cache"] = lambda: cache
        panel = SimpleNamespace(
            character_id=2,
            find_chara_data=cache.character_data[2],
            pl_chara_data=cache.character_data[0],
        )

        namespace["_auto_leave_group_sex_discovery"](panel)

        assert cache.character_data[0].behavior.h_interrupt_chara_name == "发现者"
        assert cache.character_data[2].behavior.behavior_id == "see_h_and_leave"
        assert cache.character_data[2].behavior.duration == 7
        assert cache.now_panel_id == "in_scene"
        assert calls == [
            ("masturebate", 2, cache.game_time),
            ("target", 2, cache.game_time),
            ("see", 2, cache.game_time),
        ]
    finally:
        restore()


def test_auto_leave_discovery_behavior_can_be_consumed_by_status_settlement():
    namespace = load_local_bugfix()
    cache = Cache(target_character_id=1)
    cache.character_data[2] = Character(target_character_id=2)
    cache.character_data[2].position = ["h_room"]

    script_module = ModuleType("Script")
    config_module = ModuleType("Script.Config")
    core_module = ModuleType("Script.Core")
    settle_module = ModuleType("Script.Settle")
    game_config = SimpleNamespace(config_behavior={"see_h_and_leave": SimpleNamespace(duration=7)})
    constant = SimpleNamespace(Behavior=SimpleNamespace(SEE_H_AND_LEAVE="see_h_and_leave"), Panel=SimpleNamespace(IN_SCENE="in_scene"))
    game_type = SimpleNamespace(CharacterStatusChange=ChangeData)
    default = SimpleNamespace(
        handle_masturebate_to_pl_flag_0=lambda *args, **kwargs: None,
        handle_target_to_player=lambda *args, **kwargs: None,
        handle_see_pl_h=lambda *args, **kwargs: None,
    )
    config_module.game_config = game_config
    core_module.constant = constant
    core_module.game_type = game_type
    settle_module.default = default
    script_module.Config = config_module
    script_module.Core = core_module
    script_module.Settle = settle_module
    restore = install_fake_modules(
        {
            "Script": script_module,
            "Script.Config": config_module,
            "Script.Core": core_module,
            "Script.Settle": settle_module,
        }
    )

    try:
        namespace["_cache"] = lambda: cache
        panel = SimpleNamespace(
            character_id=2,
            find_chara_data=cache.character_data[2],
            pl_chara_data=cache.character_data[0],
        )

        namespace["_auto_leave_group_sex_discovery"](panel)

        def fake_judge_character_status(character_id):
            character_data = cache.character_data[character_id]
            if character_data.behavior.behavior_id == "see_h_and_leave":
                character_data.position = ["dormitory"]

        fake_judge_character_status(2)

        assert cache.character_data[2].position == ["dormitory"]
    finally:
        restore()


def test_sex_be_discovered_draw_auto_leave_skips_original_panel():
    namespace = load_local_bugfix()
    original_calls = []
    auto_calls = []
    panel = SimpleNamespace(character_id=2)

    namespace["_ORIGINAL_SEX_BE_DISCOVERED_DRAW"] = lambda self: original_calls.append(self.character_id) or "original"
    namespace["_should_auto_leave_group_sex_discovery"] = lambda character_id: True
    namespace["_auto_leave_group_sex_discovery"] = lambda self: auto_calls.append(self.character_id) or "auto"

    assert namespace["patched_sex_be_discovered_draw"](panel) == "auto"
    assert auto_calls == [2]
    assert original_calls == []

    namespace["_should_auto_leave_group_sex_discovery"] = lambda character_id: False
    assert namespace["patched_sex_be_discovered_draw"](panel) == "original"
    assert original_calls == [2]


class DummyDraw:
    def __init__(self, *args, **kwargs):
        self.text = ""
        self.style = ""

    def draw(self):
        return None


def install_fake_hypnosis_panel(calls, instruct_flag=True):
    pl_data = SimpleNamespace(name="博士", target_character_id=1, position=["room"], pl_ability=SimpleNamespace(hypnosis_type=0))
    target_data = SimpleNamespace(name="亚叶", hypnosis=SimpleNamespace(hypnosis_degree=200), sp_flag=SimpleNamespace(unconscious_h=0))
    cache = SimpleNamespace(character_data={0: pl_data, 1: target_data}, scene_data={})
    hypnosis_panel = ModuleType("Script.UI.Panel.hypnosis_panel")
    hypnosis_panel.cache = cache
    hypnosis_panel.game_config = SimpleNamespace(config_hypnosis_type={4: SimpleNamespace(name="心控", hypnosis_degree=200)})
    hypnosis_panel.draw = SimpleNamespace(LineDraw=DummyDraw, WaitDraw=DummyDraw)
    hypnosis_panel._ = lambda text: text

    script_module = ModuleType("Script")
    design_module = ModuleType("Script.Design")
    ui_module = ModuleType("Script.UI")
    panel_module = ModuleType("Script.UI.Panel")
    handle_premise = SimpleNamespace(settle_chara_unnormal_flag=lambda character_id, flag_id: calls.append(("settle", character_id, flag_id)))
    map_handle = SimpleNamespace(get_map_system_path_str_for_list=lambda position: "/".join(position))
    design_module.handle_premise = handle_premise
    design_module.map_handle = map_handle
    panel_module.hypnosis_panel = hypnosis_panel
    restore = install_fake_modules(
        {
            "Script": script_module,
            "Script.Design": design_module,
            "Script.UI": ui_module,
            "Script.UI.Panel": panel_module,
            "Script.UI.Panel.hypnosis_panel": hypnosis_panel,
        }
    )
    panel = SimpleNamespace(
        width=80,
        instruct_flag=instruct_flag,
        body_or_mind_control_option=lambda flag: calls.append(("body_or_mind", flag)),
    )
    return cache, pl_data, target_data, panel, restore


def test_change_hypnosis_type_in_instruct_mode_applies_current_target():
    namespace = load_local_bugfix()
    calls = []
    cache, pl_data, target_data, panel, restore = install_fake_hypnosis_panel(calls, instruct_flag=True)
    try:
        namespace["_cache"] = lambda: cache
        namespace["patched_change_hypnosis_type"](panel, 4)

        assert pl_data.pl_ability.hypnosis_type == 4
        assert target_data.sp_flag.unconscious_h == 7
        assert ("body_or_mind", 1) in calls
    finally:
        restore()


def test_change_hypnosis_type_outside_instruct_mode_only_changes_default():
    namespace = load_local_bugfix()
    calls = []
    cache, pl_data, target_data, panel, restore = install_fake_hypnosis_panel(calls, instruct_flag=False)
    try:
        namespace["_cache"] = lambda: cache
        namespace["patched_change_hypnosis_type"](panel, 4)

        assert pl_data.pl_ability.hypnosis_type == 4
        assert target_data.sp_flag.unconscious_h == 0
        assert ("body_or_mind", 1) not in calls
    finally:
        restore()


def install_fake_hypnosis_one_modules(cache, calls):
    hypnosis_panel = ModuleType("Script.UI.Panel.hypnosis_panel")
    hypnosis_panel.window_width = 80
    hypnosis_panel.game_config = SimpleNamespace(config_hypnosis_type={0: SimpleNamespace(hypnosis_degree=50), 4: SimpleNamespace(hypnosis_degree=200)})
    hypnosis_panel.calculate_hypnosis_sanity_cost = lambda target_character_id: 1

    class FakeChooseHypnosisTypePanel:
        def __init__(self, width, instruct_flag=False):
            self.width = width
            self.instruct_flag = instruct_flag
            calls.append(("panel", width, instruct_flag))

        def draw(self):
            calls.append(("draw",))
            pl_data = cache.character_data[0]
            target_data = cache.character_data[pl_data.target_character_id]
            pl_data.pl_ability.hypnosis_type = 4
            target_data.sp_flag.unconscious_h = 7

    hypnosis_panel.Chose_Hypnosis_Type_Panel = FakeChooseHypnosisTypePanel

    script_module = ModuleType("Script")
    design_module = ModuleType("Script.Design")
    ui_module = ModuleType("Script.UI")
    panel_module = ModuleType("Script.UI.Panel")
    handle_premise = SimpleNamespace(settle_chara_unnormal_flag=lambda character_id, flag_id: calls.append(("settle", character_id, flag_id)))
    map_handle = SimpleNamespace(get_map_system_path_str_for_list=lambda position: "/".join(position))
    design_module.handle_premise = handle_premise
    design_module.map_handle = map_handle
    panel_module.hypnosis_panel = hypnosis_panel
    return install_fake_modules(
        {
            "Script": script_module,
            "Script.Design": design_module,
            "Script.UI": ui_module,
            "Script.UI.Panel": panel_module,
            "Script.UI.Panel.hypnosis_panel": hypnosis_panel,
        }
    )


def test_hypnosis_one_manual_type_prompts_and_applies_current_target():
    namespace = load_local_bugfix()
    cache = SimpleNamespace(character_data={})
    pl_data = SimpleNamespace(dead=False, target_character_id=1, position=["room"], pl_ability=SimpleNamespace(hypnosis_type=0))
    target_data = SimpleNamespace(hypnosis=SimpleNamespace(hypnosis_degree=200), sp_flag=SimpleNamespace(unconscious_h=0))
    cache.character_data[0] = pl_data
    cache.character_data[1] = target_data
    calls = []
    restore = install_fake_hypnosis_one_modules(cache, calls)
    try:
        namespace["_cache"] = lambda: cache
        namespace["_ORIGINAL_HYPNOSIS_ONE_EFFECT"] = lambda character_id, add_time, change_data, now_time: calls.append(("original", character_id, add_time))

        namespace["patched_handle_hypnosis_one"](0, 1, ChangeData(), datetime.datetime(2026, 1, 1, 12, 0))

        assert calls == [("original", 0, 1), ("panel", 80, True), ("draw",)]
        assert target_data.sp_flag.unconscious_h == 7
        assert pl_data.pl_ability.hypnosis_type == 0
    finally:
        restore()


def test_hypnosis_one_default_type_does_not_prompt_again():
    namespace = load_local_bugfix()
    cache = SimpleNamespace(character_data={})
    pl_data = SimpleNamespace(dead=False, target_character_id=1, position=["room"], pl_ability=SimpleNamespace(hypnosis_type=4))
    target_data = SimpleNamespace(hypnosis=SimpleNamespace(hypnosis_degree=200), sp_flag=SimpleNamespace(unconscious_h=7))
    cache.character_data[0] = pl_data
    cache.character_data[1] = target_data
    calls = []
    restore = install_fake_hypnosis_one_modules(cache, calls)
    try:
        namespace["_cache"] = lambda: cache
        namespace["_ORIGINAL_HYPNOSIS_ONE_EFFECT"] = lambda character_id, add_time, change_data, now_time: calls.append(("original", character_id, add_time))

        namespace["patched_handle_hypnosis_one"](0, 1, ChangeData(), datetime.datetime(2026, 1, 1, 12, 0))

        assert calls == [("original", 0, 1), ("settle", 1, 5), ("settle", 1, 6)]
        assert target_data.sp_flag.unconscious_h == 7
        assert pl_data.pl_ability.hypnosis_type == 4
    finally:
        restore()


def test_hypnosis_one_does_not_apply_when_degree_is_not_enough():
    namespace = load_local_bugfix()
    cache = SimpleNamespace(character_data={})
    pl_data = SimpleNamespace(dead=False, target_character_id=1, position=["room"], pl_ability=SimpleNamespace(hypnosis_type=4))
    target_data = SimpleNamespace(hypnosis=SimpleNamespace(hypnosis_degree=199), sp_flag=SimpleNamespace(unconscious_h=0))
    cache.character_data[0] = pl_data
    cache.character_data[1] = target_data
    calls = []
    restore = install_fake_hypnosis_one_modules(cache, calls)
    try:
        namespace["_cache"] = lambda: cache
        namespace["_ORIGINAL_HYPNOSIS_ONE_EFFECT"] = lambda character_id, add_time, change_data, now_time: calls.append(("original", character_id, add_time))

        namespace["patched_handle_hypnosis_one"](0, 1, ChangeData(), datetime.datetime(2026, 1, 1, 12, 0))

        assert calls == [("original", 0, 1)]
        assert target_data.sp_flag.unconscious_h == 0
    finally:
        restore()


def test_hypnosis_one_mind_control_survives_last_sanity_cost():
    namespace = load_local_bugfix()
    cache = SimpleNamespace(character_data={})
    pl_data = SimpleNamespace(dead=False, target_character_id=1, sanity_point=1, position=["room"], pl_ability=SimpleNamespace(hypnosis_type=4))
    target_data = SimpleNamespace(hypnosis=SimpleNamespace(hypnosis_degree=200), sp_flag=SimpleNamespace(unconscious_h=0))
    cache.character_data[0] = pl_data
    cache.character_data[1] = target_data
    calls = []
    restore = install_fake_hypnosis_one_modules(cache, calls)

    def fake_original(character_id, add_time, change_data, now_time):
        calls.append(("original_sanity", cache.character_data[0].sanity_point))
        character_data = cache.character_data[character_id]
        target_character_data = cache.character_data[character_data.target_character_id]
        character_data.sanity_point = max(character_data.sanity_point - 1, 0)
        target_character_data.sp_flag.unconscious_h = character_data.pl_ability.hypnosis_type + 3
        if character_data.sanity_point == 0 and target_character_data.sp_flag.unconscious_h:
            target_character_data.sp_flag.unconscious_h = 0

    try:
        namespace["_cache"] = lambda: cache
        namespace["_ORIGINAL_HYPNOSIS_ONE_EFFECT"] = fake_original

        namespace["patched_handle_hypnosis_one"](0, 1, ChangeData(), datetime.datetime(2026, 1, 1, 12, 0))

        assert calls == [("original_sanity", 1), ("settle", 1, 5), ("settle", 1, 6)]
        assert pl_data.sanity_point == 0
        assert target_data.sp_flag.unconscious_h == 7
    finally:
        restore()


if __name__ == "__main__":
    test_npc_ai_in_group_sex_preserves_player_target()
    test_npc_ai_in_group_sex_type_3_preserves_player_target()
    test_player_target_is_restored_when_original_raises()
    test_npc_active_h_delegates_to_original_after_stopping_stale_move()
    test_mind_control_active_h_talk_bypasses_unconscious_gate()
    test_hypnosis_target_generic_talk_bypasses_unconscious_gate()
    test_sleep_target_generic_talk_keeps_unconscious_gate()
    test_hypnosis_cancel_clears_pain_as_pleasure()
    test_pain_decrease_keeps_pain_as_pain_when_pain_as_pleasure_is_on()
    test_direct_pain_increase_converts_to_psychological_pleasure()
    test_add_small_pain_second_effect_uses_direct_pain_conversion()
    test_group_sex_masturbation_target_runs_once_per_player_action()
    test_group_sex_masturbation_reroute_blocks_regenerated_marker_in_same_action()
    test_blocked_group_sex_masturbation_clears_stale_marker_before_next_action()
    test_unavailable_group_sex_masturbation_target_clears_marker()
    test_tired_group_sex_discoverer_should_auto_leave()
    test_auto_leave_group_sex_discovery_uses_existing_leave_behavior()
    test_auto_leave_discovery_behavior_can_be_consumed_by_status_settlement()
    test_sex_be_discovered_draw_auto_leave_skips_original_panel()
    test_change_hypnosis_type_in_instruct_mode_applies_current_target()
    test_change_hypnosis_type_outside_instruct_mode_only_changes_default()
    test_hypnosis_one_manual_type_prompts_and_applies_current_target()
    test_hypnosis_one_default_type_does_not_prompt_again()
    test_hypnosis_one_does_not_apply_when_degree_is_not_enough()
    test_hypnosis_one_mind_control_survives_last_sanity_cost()
    print("local_bugfix mod tests passed", flush=True)
