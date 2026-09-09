from collections import defaultdict
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace


class Hypnosis:
    def __init__(self):
        self.hypnosis_degree = 0
        self.increase_body_sensitivity = False
        self.pain_as_pleasure = False


class SpFlag:
    def __init__(self):
        self.unconscious_h = 0
        self.is_h = True


class Character:
    def __init__(self):
        self.talent = defaultdict(int)
        self.hypnosis = Hypnosis()
        self.sp_flag = SpFlag()


class Cache:
    def __init__(self):
        self.character_data = {}


def load_group_sex_extension():
    mod_root = Path(__file__).resolve().parents[1]
    script_path = mod_root / "scripts" / "group_sex_extension.py"
    namespace = {"__name__": "mod_group_sex_extension_test"}
    source = script_path.read_text(encoding="utf-8").replace("\n_install_patch()\n", "\n")
    exec(compile(source, str(script_path), "exec"), namespace)
    return namespace


def install_fake_modules(module_map):
    """参数：module_map(dict)为要安装的模块；返回：callable为恢复函数；用途：为注册和场景收集测试安装伪模块。"""
    missing = object()
    old_modules = {name: sys.modules.get(name, missing) for name in module_map}
    sys.modules.update(module_map)

    def restore():
        """参数：无；返回：None；用途：恢复测试前模块表。"""
        for name, old_module in old_modules.items():
            if old_module is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old_module

    return restore


def install_group_context_modules(cache, template_character_ids, scene_character_ids):
    """参数：cache(Cache)为缓存；template_character_ids(list)为模板角色；scene_character_ids(list)为场景角色；返回：callable为恢复函数；用途：安装近真实群交上下文伪模块。"""
    script_module = ModuleType("Script")
    core_module = ModuleType("Script.Core")
    cache_control = ModuleType("Script.Core.cache_control")
    design_module = ModuleType("Script.Design")
    map_handle = ModuleType("Script.Design.map_handle")
    system_module = ModuleType("Script.System")
    sex_system_module = ModuleType("Script.System.Sex_System")
    group_sex_panel = ModuleType("Script.System.Sex_System.group_sex_panel")
    cache_control.cache = cache
    map_handle.get_map_system_path_str_for_list = lambda position: "/".join(position)
    group_sex_panel.count_group_sex_character_list = lambda: list(template_character_ids)
    core_module.cache_control = cache_control
    design_module.map_handle = map_handle
    sex_system_module.group_sex_panel = group_sex_panel
    system_module.Sex_System = sex_system_module
    script_module.Core = core_module
    script_module.Design = design_module
    script_module.System = system_module
    return install_fake_modules(
        {
            "Script": script_module,
            "Script.Core": core_module,
            "Script.Core.cache_control": cache_control,
            "Script.Design": design_module,
            "Script.Design.map_handle": map_handle,
            "Script.System": system_module,
            "Script.System.Sex_System": sex_system_module,
            "Script.System.Sex_System.group_sex_panel": group_sex_panel,
        }
    )


def test_install_registers_all_commands_and_custom_premise():
    """参数：无；返回：None；用途：验证三个群交扩展指令和自定义前提都会注册。"""
    namespace = load_group_sex_extension()
    script_module = ModuleType("Script")
    core_module = ModuleType("Script.Core")
    constant = SimpleNamespace(
        _group_sex_extension_installed=False,
        handle_premise_data={},
        handle_instruct_data={},
        instruct_premise_data={},
        instruct_type_data={},
        instruct_sub_type_data={},
        handle_instruct_name_data={},
        instruct_id_to_cid={},
        cid_to_instruct_id={},
        behavior_id_to_instruct_id={},
        instruct_category_data={},
        instruct_major_type_data={},
        instruct_minor_type_data={},
        instruct_body_parts_data={},
        InstructType=SimpleNamespace(ARTS="arts"),
        SexInstructSubType=SimpleNamespace(ARTS="sex_arts"),
        InstructCategory=SimpleNamespace(CHARACTER="character"),
    )
    constant_promise = SimpleNamespace(Premise=SimpleNamespace(GROUP_SEX_MODE_ON="group_sex_mode_on"))
    core_module.constant = constant
    core_module.constant_promise = constant_promise
    script_module.Core = core_module
    restore = install_fake_modules({"Script": script_module, "Script.Core": core_module})

    try:
        namespace["_install_patch"]()

        command_ids = {
            namespace["INSTRUCT_EDGE_ALL_ID"],
            namespace["INSTRUCT_EQUIP_TOYS_ALL_ID"],
            namespace["INSTRUCT_HYPNOSIS_BOOST_ALL_ID"],
        }
        assert namespace["PREMISE_GROUP_SEX_COMPLETE_HYPNOSIS_GE_2"] in constant.handle_premise_data
        assert command_ids <= set(constant.handle_instruct_data)
        assert command_ids <= constant.instruct_type_data["arts"]
        for command_id in command_ids:
            assert "group_sex_mode_on" in constant.instruct_premise_data[command_id]
        assert namespace["PREMISE_GROUP_SEX_COMPLETE_HYPNOSIS_GE_2"] in constant.instruct_premise_data[namespace["INSTRUCT_HYPNOSIS_BOOST_ALL_ID"]]
        assert constant.instruct_id_to_cid[namespace["INSTRUCT_EDGE_ALL_ID"]] == namespace["INSTRUCT_EDGE_ALL_CID"]
        assert constant.cid_to_instruct_id[namespace["INSTRUCT_HYPNOSIS_BOOST_ALL_CID"]] == namespace["INSTRUCT_HYPNOSIS_BOOST_ALL_ID"]
    finally:
        restore()


def test_group_character_ids_merge_template_and_scene_h_characters():
    """参数：无；返回：None；用途：验证群交参与者来自群交模板和当前场景H状态角色。"""
    namespace = load_group_sex_extension()
    cache = Cache()
    cache.character_data = {0: Character(), 1: Character(), 2: Character(), 3: Character(), 5: Character()}
    cache.character_data[0].position = ["room"]
    cache.character_data[2].sp_flag.is_h = True
    cache.character_data[3].sp_flag.is_h = False
    cache.character_data[5].sp_flag.is_h = True
    cache.scene_data = {"room": SimpleNamespace(character_list={2, 3, 4, 5})}

    script_module = ModuleType("Script")
    core_module = ModuleType("Script.Core")
    cache_control = ModuleType("Script.Core.cache_control")
    design_module = ModuleType("Script.Design")
    map_handle = ModuleType("Script.Design.map_handle")
    system_module = ModuleType("Script.System")
    sex_system_module = ModuleType("Script.System.Sex_System")
    group_sex_panel = ModuleType("Script.System.Sex_System.group_sex_panel")
    cache_control.cache = cache
    map_handle.get_map_system_path_str_for_list = lambda position: "/".join(position)
    group_sex_panel.count_group_sex_character_list = lambda: [1, 2, 3, 9, 0]
    core_module.cache_control = cache_control
    design_module.map_handle = map_handle
    sex_system_module.group_sex_panel = group_sex_panel
    system_module.Sex_System = sex_system_module
    script_module.Core = core_module
    script_module.Design = design_module
    script_module.System = system_module
    restore = install_fake_modules(
        {
            "Script": script_module,
            "Script.Core": core_module,
            "Script.Core.cache_control": cache_control,
            "Script.Design": design_module,
            "Script.Design.map_handle": map_handle,
            "Script.System": system_module,
            "Script.System.Sex_System": sex_system_module,
            "Script.System.Sex_System.group_sex_panel": group_sex_panel,
        }
    )

    try:
        assert namespace["_get_group_sex_character_ids"]() == [1, 2, 5]
    finally:
        restore()


def test_group_character_ids_filter_stale_template_ids_before_hypnosis_lookup():
    """参数：无；返回：None；用途：验证模板中不存在或非H角色不会进入后续群交参与者列表。"""
    namespace = load_group_sex_extension()
    cache = Cache()
    cache.character_data = {0: Character(), 1: Character(), 2: Character()}
    cache.character_data[0].position = ["room"]
    cache.character_data[1].hypnosis.hypnosis_degree = 200
    cache.character_data[1].sp_flag.unconscious_h = 7
    cache.character_data[2].sp_flag.is_h = False
    cache.character_data[2].hypnosis.hypnosis_degree = 200
    cache.scene_data = {"room": SimpleNamespace(character_list=set())}

    script_module = ModuleType("Script")
    core_module = ModuleType("Script.Core")
    cache_control = ModuleType("Script.Core.cache_control")
    design_module = ModuleType("Script.Design")
    map_handle = ModuleType("Script.Design.map_handle")
    system_module = ModuleType("Script.System")
    sex_system_module = ModuleType("Script.System.Sex_System")
    group_sex_panel = ModuleType("Script.System.Sex_System.group_sex_panel")
    cache_control.cache = cache
    map_handle.get_map_system_path_str_for_list = lambda position: "/".join(position)
    group_sex_panel.count_group_sex_character_list = lambda: [1, 2, 9]
    core_module.cache_control = cache_control
    design_module.map_handle = map_handle
    sex_system_module.group_sex_panel = group_sex_panel
    system_module.Sex_System = sex_system_module
    script_module.Core = core_module
    script_module.Design = design_module
    script_module.System = system_module
    restore = install_fake_modules(
        {
            "Script": script_module,
            "Script.Core": core_module,
            "Script.Core.cache_control": cache_control,
            "Script.Design": design_module,
            "Script.Design.map_handle": map_handle,
            "Script.System": system_module,
            "Script.System.Sex_System": sex_system_module,
            "Script.System.Sex_System.group_sex_panel": group_sex_panel,
        }
    )

    try:
        assert namespace["_get_group_sex_character_ids"]() == [1]
        assert namespace["_get_complete_hypnosis_character_ids"]() == [1]
    finally:
        restore()


def test_hypnosis_boost_visibility_requires_two_complete_hypnosis_characters():
    """参数：无；返回：None；用途：验证全员催眠增强统计完全催眠角色且不要求当前催眠态。"""
    namespace = load_group_sex_extension()
    cache = Cache()
    cache.character_data = {1: Character(), 2: Character(), 3: Character()}
    cache.character_data[1].talent[73] = 1
    cache.character_data[1].sp_flag.unconscious_h = 6
    cache.character_data[2].hypnosis.hypnosis_degree = 200
    cache.character_data[2].sp_flag.unconscious_h = 0
    cache.character_data[3].hypnosis.hypnosis_degree = 199
    cache.character_data[3].sp_flag.unconscious_h = 7

    namespace["_get_cache"] = lambda: cache
    namespace["_get_group_sex_character_ids"] = lambda: [1, 2, 3]

    assert namespace["_handle_complete_hypnosis_ge_2"](0) == 1

    cache.character_data[2].sp_flag.unconscious_h = 7

    assert namespace["_handle_complete_hypnosis_ge_2"](0) == 1

    cache.character_data[2].hypnosis.hypnosis_degree = 199

    assert namespace["_handle_complete_hypnosis_ge_2"](0) == 0


def test_direct_invited_complete_hypnosis_counts_without_active_state():
    """参数：无；返回：None；用途：验证直接邀请加入的完全催眠角色即使未处于催眠态也计入按钮前提。"""
    namespace = load_group_sex_extension()
    cache = Cache()
    cache.character_data = {0: Character(), 1: Character(), 2: Character()}
    cache.character_data[0].position = ["room"]
    cache.character_data[1].hypnosis.hypnosis_degree = 200
    cache.character_data[1].sp_flag.unconscious_h = 7
    cache.character_data[2].hypnosis.hypnosis_degree = 200
    cache.character_data[2].sp_flag.unconscious_h = 0
    cache.scene_data = {"room": SimpleNamespace(character_list={2})}
    restore = install_group_context_modules(cache, [1], {2})

    try:
        assert namespace["_get_group_sex_character_ids"]() == [1, 2]
        assert namespace["_handle_complete_hypnosis_ge_2"](0) == 1
    finally:
        restore()


def test_hypnosis_boost_sets_flags_without_changing_hypnosis_state():
    """参数：无；返回：None；用途：验证催眠增强不会给非生效催眠角色写入短期催眠子状态。"""
    namespace = load_group_sex_extension()
    cache = Cache()
    cache.character_data = {1: Character(), 2: Character(), 3: Character()}
    cache.character_data[1].talent[73] = 1
    cache.character_data[1].sp_flag.unconscious_h = 6
    cache.character_data[2].hypnosis.hypnosis_degree = 200
    cache.character_data[2].sp_flag.unconscious_h = 7
    cache.character_data[3].hypnosis.hypnosis_degree = 199
    draw_texts = []

    namespace["_get_cache"] = lambda: cache
    namespace["_get_group_sex_character_ids"] = lambda: [1, 2, 3]
    namespace["_draw_result"] = draw_texts.append

    namespace["group_sex_extension_hypnosis_boost_all"]()

    assert cache.character_data[1].hypnosis.increase_body_sensitivity is True
    assert cache.character_data[1].hypnosis.pain_as_pleasure is True
    assert cache.character_data[1].sp_flag.unconscious_h == 6
    assert cache.character_data[2].hypnosis.increase_body_sensitivity is True
    assert cache.character_data[2].hypnosis.pain_as_pleasure is True
    assert cache.character_data[2].sp_flag.unconscious_h == 7
    assert cache.character_data[3].hypnosis.increase_body_sensitivity is False
    assert cache.character_data[3].hypnosis.pain_as_pleasure is False
    assert "2名完全催眠干员" in draw_texts[0]


def test_direct_invited_inactive_complete_hypnosis_gets_boost_without_state_change():
    """参数：无；返回：None；用途：验证未激活催眠态的直接受邀完全催眠角色会获得强化且不改变催眠态。"""
    namespace = load_group_sex_extension()
    cache = Cache()
    cache.character_data = {0: Character(), 1: Character(), 2: Character(), 3: Character()}
    cache.character_data[0].position = ["room"]
    cache.character_data[1].talent[73] = 1
    cache.character_data[1].sp_flag.unconscious_h = 6
    cache.character_data[2].hypnosis.hypnosis_degree = 200
    cache.character_data[2].sp_flag.unconscious_h = 0
    cache.character_data[3].hypnosis.hypnosis_degree = 199
    cache.character_data[3].sp_flag.unconscious_h = 7
    cache.scene_data = {"room": SimpleNamespace(character_list={2, 3})}
    draw_texts = []
    restore = install_group_context_modules(cache, [1], {2, 3})

    try:
        namespace["_draw_result"] = draw_texts.append
        namespace["group_sex_extension_hypnosis_boost_all"]()

        assert cache.character_data[1].hypnosis.increase_body_sensitivity is True
        assert cache.character_data[1].hypnosis.pain_as_pleasure is True
        assert cache.character_data[1].sp_flag.unconscious_h == 6
        assert cache.character_data[2].hypnosis.increase_body_sensitivity is True
        assert cache.character_data[2].hypnosis.pain_as_pleasure is True
        assert cache.character_data[2].sp_flag.unconscious_h == 0
        assert cache.character_data[3].hypnosis.increase_body_sensitivity is False
        assert cache.character_data[3].hypnosis.pain_as_pleasure is False
        assert "2名完全催眠干员" in draw_texts[0]
    finally:
        restore()


def test_hypnosis_boost_requires_two_complete_hypnosis_characters():
    """参数：无；返回：None；用途：验证直接调用指令时仍要求至少两名完全催眠角色。"""
    namespace = load_group_sex_extension()
    cache = Cache()
    cache.character_data = {1: Character(), 2: Character()}
    cache.character_data[1].talent[73] = 1
    cache.character_data[1].sp_flag.unconscious_h = 0
    cache.character_data[2].hypnosis.hypnosis_degree = 199
    cache.character_data[2].sp_flag.unconscious_h = 7
    draw_texts = []

    namespace["_get_cache"] = lambda: cache
    namespace["_get_group_sex_character_ids"] = lambda: [1, 2]
    namespace["_draw_result"] = draw_texts.append

    namespace["group_sex_extension_hypnosis_boost_all"]()

    assert cache.character_data[1].hypnosis.increase_body_sensitivity is False
    assert cache.character_data[1].hypnosis.pain_as_pleasure is False
    assert cache.character_data[2].hypnosis.increase_body_sensitivity is False
    assert cache.character_data[2].hypnosis.pain_as_pleasure is False
    assert "不足2人" in draw_texts[0]


if __name__ == "__main__":
    test_install_registers_all_commands_and_custom_premise()
    test_group_character_ids_merge_template_and_scene_h_characters()
    test_group_character_ids_filter_stale_template_ids_before_hypnosis_lookup()
    test_hypnosis_boost_visibility_requires_two_complete_hypnosis_characters()
    test_direct_invited_complete_hypnosis_counts_without_active_state()
    test_hypnosis_boost_sets_flags_without_changing_hypnosis_state()
    test_direct_invited_inactive_complete_hypnosis_gets_boost_without_state_change()
    test_hypnosis_boost_requires_two_complete_hypnosis_characters()
    print("group_sex_extension mod tests passed", flush=True)
