# -*- coding: UTF-8 -*-
"""拆分本地bugfix组件清单与默认配置测试。"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from types import ModuleType, SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


ACTIVE_COMPONENT_IDS = [
    "local_orgasm_chain_gate_fix",
]

DISABLED_HISTORICAL_COMPONENT_IDS = [
    "local_group_edge_release_fix",
]

CORE_RETIRED_COMPONENT_IDS = [
    "local_commission_number_display_fix",
    "local_cross_platform_save_fix",
    "local_group_target_context_fix",
    "local_h_movement_interrupt_fix",
    "local_group_participant_admission_fix",
    "local_pain_as_pleasure_fix",
    "local_h_orgasm_batch_fix",
    "local_hypnosis_state_fix",
]


def read_json(path: Path) -> dict:
    """参数：path(Path)为JSON路径；返回：dict为解析结果；用途：读取测试所需JSON文件。"""
    return json.loads(path.read_text(encoding="utf-8"))


def _empty_func(*args, **kwargs):
    """参数：任意；返回：None；用途：作为加载烟雾测试的空实现。"""
    return None


class _DummyDraw:
    """参数：任意；返回：_DummyDraw；用途：伪造绘制类。"""

    def __init__(self, *args, **kwargs):
        """参数：任意；返回：None；用途：初始化绘制占位对象。"""
        self.text = ""
        self.width = 0
        self.style = ""

    def draw(self):
        """参数：无；返回：None；用途：跳过实际绘制。"""
        return None


def install_loader_smoke_stubs():
    """参数：无；返回：callable为恢复函数；用途：为真实ModManager加载拆分组件安装最小伪模块边界。"""
    missing = object()
    module_names = [
        "Script",
        "Script.Config",
        "Script.Config.game_config",
        "Script.Config.normal_config",
        "Script.Core",
        "Script.Core.cache_control",
        "Script.Core.constant",
        "Script.Core.constant_promise",
        "Script.Core.flow_handle",
        "Script.Core.flow_handle_web",
        "Script.Core.game_type",
        "Script.Core.get_text",
        "Script.Core.io_init",
        "Script.Core.io_web",
        "Script.Design",
        "Script.Design.attr_calculation",
        "Script.Design.character_behavior",
        "Script.Design.character_move",
        "Script.Design.handle_npc_ai",
        "Script.Design.handle_npc_ai_in_h",
        "Script.Design.handle_premise",
        "Script.Design.map_handle",
        "Script.Design.second_behavior",
        "Script.Design.settle_behavior",
        "Script.Design.talk",
        "Script.Design.update",
        "Script.Settle",
        "Script.Settle.Second_effect",
        "Script.Settle.common_default",
        "Script.Settle.default",
        "Script.Settle.item_effect",
        "Script.Settle.realtime_settle",
        "Script.StateMachine",
        "Script.StateMachine.default",
        "Script.System",
        "Script.System.Sex_System",
        "Script.System.Sex_System.group_sex_panel",
        "Script.System.Sex_System.hidden_sex_panel",
        "Script.System.Sex_System.sex_be_discovered_panel",
        "Script.UI",
        "Script.UI.Moudle",
        "Script.UI.Moudle.draw",
        "Script.UI.Panel",
        "Script.UI.Panel.achievement_panel",
        "Script.UI.Panel.hypnosis_panel",
        "Script.UI.Panel.manage_power_system_panel",
    ]
    modules = {name: ModuleType(name) for name in module_names}
    old_modules = {name: sys.modules.get(name, missing) for name in module_names}

    def link(parent_name, attr_name, child_name):
        """参数：parent_name(str)为父模块，attr_name(str)为属性名，child_name(str)为子模块；返回：None；用途：建立伪包属性。"""
        setattr(modules[parent_name], attr_name, modules[child_name])

    link("Script", "Config", "Script.Config")
    link("Script", "Core", "Script.Core")
    link("Script", "Design", "Script.Design")
    link("Script", "Settle", "Script.Settle")
    link("Script", "StateMachine", "Script.StateMachine")
    link("Script", "System", "Script.System")
    link("Script", "UI", "Script.UI")
    link("Script.Config", "game_config", "Script.Config.game_config")
    link("Script.Config", "normal_config", "Script.Config.normal_config")
    link("Script.Core", "cache_control", "Script.Core.cache_control")
    link("Script.Core", "constant", "Script.Core.constant")
    link("Script.Core", "constant_promise", "Script.Core.constant_promise")
    link("Script.Core", "flow_handle", "Script.Core.flow_handle")
    link("Script.Core", "flow_handle_web", "Script.Core.flow_handle_web")
    link("Script.Core", "game_type", "Script.Core.game_type")
    link("Script.Core", "get_text", "Script.Core.get_text")
    link("Script.Core", "io_init", "Script.Core.io_init")
    link("Script.Core", "io_web", "Script.Core.io_web")
    link("Script.Design", "attr_calculation", "Script.Design.attr_calculation")
    link("Script.Design", "character_behavior", "Script.Design.character_behavior")
    link("Script.Design", "character_move", "Script.Design.character_move")
    link("Script.Design", "handle_npc_ai", "Script.Design.handle_npc_ai")
    link("Script.Design", "handle_npc_ai_in_h", "Script.Design.handle_npc_ai_in_h")
    link("Script.Design", "handle_premise", "Script.Design.handle_premise")
    link("Script.Design", "map_handle", "Script.Design.map_handle")
    link("Script.Design", "second_behavior", "Script.Design.second_behavior")
    link("Script.Design", "settle_behavior", "Script.Design.settle_behavior")
    link("Script.Design", "talk", "Script.Design.talk")
    link("Script.Design", "update", "Script.Design.update")
    link("Script.Settle", "Second_effect", "Script.Settle.Second_effect")
    link("Script.Settle", "common_default", "Script.Settle.common_default")
    link("Script.Settle", "default", "Script.Settle.default")
    link("Script.Settle", "item_effect", "Script.Settle.item_effect")
    link("Script.Settle", "realtime_settle", "Script.Settle.realtime_settle")
    link("Script.StateMachine", "default", "Script.StateMachine.default")
    link("Script.System", "Sex_System", "Script.System.Sex_System")
    link("Script.System.Sex_System", "group_sex_panel", "Script.System.Sex_System.group_sex_panel")
    link("Script.System.Sex_System", "hidden_sex_panel", "Script.System.Sex_System.hidden_sex_panel")
    link("Script.System.Sex_System", "sex_be_discovered_panel", "Script.System.Sex_System.sex_be_discovered_panel")
    link("Script.UI", "Moudle", "Script.UI.Moudle")
    link("Script.UI", "Panel", "Script.UI.Panel")
    link("Script.UI.Moudle", "draw", "Script.UI.Moudle.draw")
    link("Script.UI.Panel", "achievement_panel", "Script.UI.Panel.achievement_panel")
    link("Script.UI.Panel", "hypnosis_panel", "Script.UI.Panel.hypnosis_panel")
    link("Script.UI.Panel", "manage_power_system_panel", "Script.UI.Panel.manage_power_system_panel")

    cache = SimpleNamespace(character_data={}, scene_data={}, group_sex_mode=False, game_time=None, over_behavior_character=set())
    modules["Script.Core.cache_control"].cache = cache
    modules["Script.Core.get_text"]._ = lambda text: text
    modules["Script.Core.game_type"].CharacterStatusChange = lambda: SimpleNamespace(target_change={}, status_data=defaultdict(int))
    modules["Script.Core.game_type"].TargetChange = lambda: SimpleNamespace(status_data=defaultdict(int))

    constant = modules["Script.Core.constant"]
    constant.Behavior = SimpleNamespace(MOVE="move", WAIT="wait", GROUP_SEX_TO_H="group_sex_to_h", GROUP_SEX_NPC_HP_0_END="group_sex_npc_hp_0_end", SEE_H_AND_LEAVE="see_h_and_leave")
    constant.CharacterStatus = SimpleNamespace(STATUS_WAIT="status_wait")
    constant.Panel = SimpleNamespace(IN_SCENE="in_scene", SEE_MAP="see_map")
    constant.StateMachine = SimpleNamespace(CONTINUE_MOVE=100)
    constant.handle_state_machine_data = defaultdict(lambda: _empty_func)
    constant.settle_behavior_effect_data = {}
    constant.settle_second_behavior_effect_data = {}
    constant.handle_premise_data = {}
    constant.handle_instruct_data = {}
    constant.instruct_premise_data = defaultdict(set)
    constant.instruct_type_data = defaultdict(set)
    constant.instruct_sub_type_data = defaultdict(set)
    constant.handle_instruct_name_data = {}
    constant.instruct_id_to_cid = {}
    constant.cid_to_instruct_id = {}
    constant.behavior_id_to_instruct_id = {}
    constant.instruct_category_data = {}
    constant.instruct_major_type_data = {}
    constant.instruct_minor_type_data = {}
    constant.instruct_body_parts_data = {}
    constant.InstructType = SimpleNamespace(ARTS="arts")
    constant.SexInstructSubType = SimpleNamespace(ARTS="sex_arts")
    constant.InstructCategory = SimpleNamespace(CHARACTER="character")
    modules["Script.Core.constant_promise"].Premise = SimpleNamespace(GROUP_SEX_MODE_ON="group_sex_mode_on")

    game_config = modules["Script.Config.game_config"]
    game_config.config_target = defaultdict(lambda: SimpleNamespace(state_machine_id=0))
    game_config.config_behavior = defaultdict(lambda: SimpleNamespace(duration=1))
    game_config.config_hypnosis_type = {0: SimpleNamespace(name="手动", hypnosis_degree=50)}
    game_config.config_character_state = {}
    game_config.config_behavior_effect_data = {}
    game_config.config_body_item = {}
    game_config.config_item = {}
    modules["Script.Config.normal_config"].config_normal = SimpleNamespace(text_width=80)

    modules["Script.Design.attr_calculation"].get_tired_level = lambda tired_point: 0
    modules["Script.Design.attr_calculation"].get_mark_debuff_adjust = lambda ability_level: 1
    modules["Script.Design.character_behavior"].judge_character_status = _empty_func
    modules["Script.Design.character_behavior"].init_character_behavior = _empty_func
    modules["Script.Design.character_move"].own_charcter_move = _empty_func
    modules["Script.Design.character_move"].character_move = lambda character_id, target_scene: ("end", [], target_scene, 1)
    modules["Script.Design.character_move"].update = SimpleNamespace(game_update_flow=_empty_func)
    modules["Script.Design.handle_npc_ai"].find_character_target = _empty_func
    modules["Script.Design.handle_npc_ai"].judge_character_tired_sleep = _empty_func
    modules["Script.Design.handle_npc_ai"].search_target = lambda *args, **kwargs: ("default91", 1, False, {})
    modules["Script.Design.handle_npc_ai_in_h"].npc_ai_in_group_sex = _empty_func
    modules["Script.Design.handle_npc_ai_in_h"].npc_ai_in_group_sex_type_3 = _empty_func
    modules["Script.Design.handle_npc_ai_in_h"].npc_active_h = _empty_func
    modules["Script.Design.handle_npc_ai_in_h"].judge_character_h_obscenity_unconscious = _empty_func
    modules["Script.Design.handle_npc_ai_in_h"].recover_from_unconscious_h = _empty_func
    handle_premise = modules["Script.Design.handle_premise"]
    handle_premise.handle_group_sex_mode_on = lambda character_id: False
    handle_premise.handle_masturebate_flag_3 = lambda character_id: False
    handle_premise.settle_chara_unnormal_flag = _empty_func
    handle_premise.handle_t_unconscious_hypnosis_flag = lambda character_id: False
    handle_premise.get_weight_from_premise_dict = lambda talk_premise_dict, character_id, calculated_premise_dict, weight_all_to_1_flag=False, unconscious_pass_flag=False: (0, calculated_premise_dict)
    modules["Script.Design.map_handle"].get_map_system_path_str_for_list = lambda position: "/".join(position)
    second_behavior = modules["Script.Design.second_behavior"]
    second_behavior.check_second_effect = _empty_func
    second_behavior.orgasm_settle = _empty_func
    second_behavior.character_get_second_behavior = _empty_func
    second_behavior.judge_orgasm_degree = lambda now_data: 0
    modules["Script.Design.settle_behavior"].handle_comprehensive_value_effect = _empty_func
    modules["Script.Design.talk"].handle_second_talk = _empty_func
    modules["Script.Design.talk"].second_behavior_info_text = _empty_func
    modules["Script.Design.update"].game_update_flow = _empty_func

    settle_default = modules["Script.Settle.default"]
    settle_default.handle_masturebate_to_pl_flag_0 = _empty_func
    settle_default.handle_target_to_player = _empty_func
    settle_default.handle_see_pl_h = _empty_func
    settle_default.handle_hypnosis_one = _empty_func
    settle_default.handle_hypnosis_cancel = _empty_func
    settle_default.handle_end_h_add_hpmp_max = _empty_func
    settle_default.handle_group_sex_end_h_add_hpmp_max = _empty_func
    modules["Script.Settle.common_default"].base_chara_state_common_settle = _empty_func
    for module_name in ["Script.Settle.Second_effect", "Script.Settle.realtime_settle", "Script.Settle.item_effect"]:
        modules[module_name].base_chara_state_common_settle = _empty_func
    for func_name in ["handle_add_small_pain", "handle_add_middle_pain", "handle_add_large_pain", "handle_extra_orgasm"]:
        setattr(modules["Script.Settle.Second_effect"], func_name, _empty_func)

    modules["Script.StateMachine.default"].general_movement_module = _empty_func
    modules["Script.StateMachine.default"].character_continue_move = _empty_func
    modules["Script.System.Sex_System.group_sex_panel"].count_group_sex_character_list = lambda: []
    modules["Script.System.Sex_System.group_sex_panel"].Edit_Group_Sex_Temple_Panel = type(
        "Edit_Group_Sex_Temple_Panel",
        (),
        {"show_invite_npc_panel": _empty_func, "invite_npc": _empty_func},
    )
    modules["Script.System.Sex_System.group_sex_panel"].window_width = 80
    modules["Script.System.Sex_System.group_sex_panel"]._ = lambda text: text
    modules["Script.System.Sex_System.hidden_sex_panel"].get_nearby_conscious_unfallen_characters = lambda character_id: []
    modules["Script.System.Sex_System.sex_be_discovered_panel"].Sex_Be_Discovered_Panel = type(
        "Sex_Be_Discovered_Panel",
        (),
        {"draw": _empty_func, "_invite_find_char_to_join": _empty_func},
    )
    for draw_name in ["NormalDraw", "WaitDraw", "LineDraw"]:
        setattr(modules["Script.UI.Moudle.draw"], draw_name, _DummyDraw)
    modules["Script.UI.Panel.achievement_panel"].achievement_flow = _empty_func
    hypnosis_panel = modules["Script.UI.Panel.hypnosis_panel"]
    hypnosis_panel.cache = cache
    hypnosis_panel.window_width = 80
    hypnosis_panel.game_config = game_config
    hypnosis_panel.draw = modules["Script.UI.Moudle.draw"]
    hypnosis_panel._ = lambda text: text
    hypnosis_panel.Chose_Hypnosis_Type_Panel = type(
        "Chose_Hypnosis_Type_Panel",
        (),
        {
            "__init__": lambda self, width, instruct_flag=False: None,
            "draw": _empty_func,
            "change_hypnosis_type": _empty_func,
            "body_or_mind_control_option": _empty_func,
        },
    )
    modules["Script.UI.Panel.manage_power_system_panel"].store_power_by_human_power = _empty_func
    for module_name in ["Script.Core.flow_handle", "Script.Core.flow_handle_web", "Script.Core.io_init", "Script.Core.io_web"]:
        for func_name in ["askfor_all", "askfor_int", "askfor_str", "askfor_wait", "print_cmd", "print_image_cmd", "era_print", "clear_screen", "clear_screen_and_history"]:
            setattr(modules[module_name], func_name, _empty_func)

    sys.modules.update(modules)

    def restore():
        """参数：无；返回：None；用途：恢复真实模块表。"""
        for name, old_module in old_modules.items():
            if old_module is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old_module

    return restore


def enable_only_with_dependencies(manager, mod_id: str):
    """参数：manager(ModManager)为加载器，mod_id(str)为目标mod；返回：list[str]为依赖优先的启用列表；用途：真实加载烟雾测试只启用目标组件及依赖。"""
    result = []

    def visit(now_mod_id: str):
        if now_mod_id in result:
            return
        for dependency_id in manager.mods[now_mod_id].dependencies:
            visit(dependency_id)
        result.append(now_mod_id)

    visit(mod_id)
    manager.enabled_mods = result.copy()
    manager.load_order = [mod_id] + [now_mod_id for now_mod_id in result if now_mod_id != mod_id]
    for now_mod_id, mod_info in manager.mods.items():
        mod_info.enabled = now_mod_id in result
        mod_info.loaded = False
        mod_info.error_message = ""
    return result


def reset_mod_manager_globals(mod_manager):
    """参数：mod_manager(module)为加载器模块；返回：None；用途：清理真实加载烟雾测试的全局注册。"""
    mod_manager._original_functions.clear()
    mod_manager._mod_functions.clear()
    mod_manager._mod_assets.clear()


def test_runtime_config_excludes_retired_and_historical_components():
    """参数：无；返回：None；用途：验证运行配置不启用已退役组件与刻意禁用的历史组件。"""
    config = read_json(REPO_ROOT / "mod" / "mod_config.json")

    assert "local_bugfix" not in config["enabled_mods"]
    assert "local_bugfix" not in config["load_order"]
    for mod_id in CORE_RETIRED_COMPONENT_IDS:
        assert mod_id not in config["enabled_mods"]
        assert mod_id not in config["load_order"]
        assert not (REPO_ROOT / "mod" / mod_id).exists()
    for mod_id in DISABLED_HISTORICAL_COMPONENT_IDS:
        assert mod_id not in config["enabled_mods"]
        assert mod_id not in config["load_order"]


def test_active_component_manifests():
    """参数：无；返回：None；用途：验证仍由mod承担责任的活动组件清单完整。"""
    for mod_id in ACTIVE_COMPONENT_IDS:
        manifest = read_json(REPO_ROOT / "mod" / mod_id / "mod_info.json")
        assert manifest["mod_id"] == mod_id
        assert manifest["scripts"]
        assert manifest["dependencies"] == []


def test_disabled_historical_component_manifest():
    """参数：无；返回：None；用途：验证刻意禁用的历史组件仍保留其已退役依赖声明。"""
    manifest = read_json(REPO_ROOT / "mod" / "local_group_edge_release_fix" / "mod_info.json")

    assert manifest["mod_id"] == "local_group_edge_release_fix"
    assert manifest["scripts"]
    assert manifest["dependencies"] == ["local_h_orgasm_batch_fix"]


def test_deprecated_local_bugfix_is_not_scanned_as_active_mod():
    """参数：无；返回：None；用途：验证废弃备份不在顶层mod扫描结果中。"""
    from Script.Core.mod_manager import ModManager

    ModManager._instance = None
    manager = ModManager()
    manager.scan_mods()

    assert (REPO_ROOT / "mod" / "deprecated" / "local_bugfix" / "mod_info.json").exists()
    assert "local_bugfix" not in manager.mods
    assert "deprecated" not in manager.mods


def test_each_active_component_loads_through_mod_manager():
    """参数：无；返回：None；用途：验证每个活动组件可通过真实ModManager独立加载。"""
    from Script.Core import mod_manager
    from Script.Core.mod_manager import ModManager

    reset_mod_manager_globals(mod_manager)

    for mod_id in ACTIVE_COMPONENT_IDS:
        restore = install_loader_smoke_stubs()
        try:
            ModManager._instance = None
            manager = ModManager()
            manager.scan_mods()
            enabled_ids = enable_only_with_dependencies(manager, mod_id)
            errors = manager.load_all_enabled_mods()
            sorted_ids = [info.mod_id for info in manager.get_sorted_enabled_mods()]

            assert errors == {}
            assert set(sorted_ids) == set(enabled_ids)
            assert manager.mods[mod_id].loaded is True
            for enabled_id in enabled_ids:
                assert manager.mods[enabled_id].loaded is True
        finally:
            restore()
            reset_mod_manager_globals(mod_manager)
            ModManager._instance = None


def main():
    """参数：无；返回：None；用途：直接运行全部清单与配置测试。"""
    test_runtime_config_excludes_retired_and_historical_components()
    test_active_component_manifests()
    test_disabled_historical_component_manifest()
    test_deprecated_local_bugfix_is_not_scanned_as_active_mod()
    test_each_active_component_loads_through_mod_manager()
    print("split local bugfix manifest tests passed", flush=True)


if __name__ == "__main__":
    main()
