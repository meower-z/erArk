from types import ModuleType, SimpleNamespace
import sys


class SpFlag:
    """参数：无；返回：None；用途：保存测试所需的特殊标记。"""

    def __init__(self):
        self.is_h = True
        self.masturebate = 0


class Behavior:
    """参数：无；返回：None；用途：保存测试所需的行为状态。"""

    def __init__(self):
        self.behavior_id = ""


class Character:
    """参数：无；返回：None；用途：构造群交AI测试角色。"""

    def __init__(self):
        self.sp_flag = SpFlag()
        self.behavior = Behavior()
        self.state = ""
        self.h_state = SimpleNamespace(group_sex_body_template_dict={"A": [{}, [[], 0]]})


class Cache:
    """参数：无；返回：None；用途：构造群交AI测试缓存。"""

    def __init__(self):
        self.character_data = {0: Character(), 1: Character(), 2: Character()}


class NormalDraw:
    """参数：无；返回：None；用途：替代绘制对象避免导入真实UI。"""

    def __init__(self):
        self.text = ""
        self.width = 0


def install_fake_modules(cache, template_character_ids, npc_ai_type):
    """参数：cache(Cache)为缓存；template_character_ids(list)为模板角色；npc_ai_type(int)为群交AI类型；返回：tuple为恢复函数和调用记录。"""
    missing = object()
    settle_calls = []
    get_template_calls = []

    script_module = ModuleType("Script")
    core_module = ModuleType("Script.Core")
    cache_control = ModuleType("Script.Core.cache_control")
    game_path_config = ModuleType("Script.Core.game_path_config")
    game_type = ModuleType("Script.Core.game_type")
    constant = ModuleType("Script.Core.constant")
    get_text = ModuleType("Script.Core.get_text")
    design_module = ModuleType("Script.Design")
    ui_module = ModuleType("Script.UI")
    moudle_module = ModuleType("Script.UI.Moudle")
    draw = ModuleType("Script.UI.Moudle.draw")
    config_module = ModuleType("Script.Config")
    normal_config = ModuleType("Script.Config.normal_config")
    game_config = ModuleType("Script.Config.game_config")
    system_module = ModuleType("Script.System")
    sex_system_module = ModuleType("Script.System.Sex_System")
    group_sex_panel = ModuleType("Script.System.Sex_System.group_sex_panel")

    cache_control.cache = cache
    game_path_config.game_path = ""
    game_type.Cache = Cache
    game_type.Character = Character
    constant.Behavior = SimpleNamespace(SHARE_BLANKLY="share_blankly")
    constant.CharacterStatus = SimpleNamespace(STATUS_ARDER="status_arder")
    get_text._ = lambda text: text
    draw.NormalDraw = NormalDraw
    normal_config.config_normal = SimpleNamespace(text_width=80)

    handle_premise = ModuleType("Script.Design.handle_premise")
    handle_premise.handle_group_sex_mode_off = lambda character_id: False
    handle_premise.handle_self_now_bondage = lambda character_id: False
    handle_premise.handle_npc_ai_type_1_in_group_sex = lambda character_id: npc_ai_type == 1
    handle_premise.settle_chara_unnormal_flag = lambda character_id, flag_id: settle_calls.append((character_id, flag_id))

    group_sex_panel.count_group_sex_character_list = lambda: list(template_character_ids)

    def get_now_template_part_list():
        """参数：无；返回：tuple；用途：记录非类型1模板成员是否继续进入模板分配。"""
        get_template_calls.append("called")
        return [], []

    group_sex_panel.get_now_template_part_list = get_now_template_part_list

    core_module.cache_control = cache_control
    core_module.game_path_config = game_path_config
    core_module.game_type = game_type
    core_module.constant = constant
    core_module.get_text = get_text
    design_module.instuct_judege = ModuleType("Script.Design.instuct_judege")
    design_module.handle_premise = handle_premise
    design_module.update = ModuleType("Script.Design.update")
    design_module.character_behavior = ModuleType("Script.Design.character_behavior")
    design_module.attr_calculation = ModuleType("Script.Design.attr_calculation")
    design_module.map_handle = ModuleType("Script.Design.map_handle")
    moudle_module.draw = draw
    ui_module.Moudle = moudle_module
    config_module.game_config = game_config
    config_module.normal_config = normal_config
    sex_system_module.group_sex_panel = group_sex_panel
    system_module.Sex_System = sex_system_module
    script_module.Core = core_module
    script_module.Design = design_module
    script_module.UI = ui_module
    script_module.Config = config_module
    script_module.System = system_module

    module_map = {
        "Script": script_module,
        "Script.Core": core_module,
        "Script.Core.cache_control": cache_control,
        "Script.Core.game_path_config": game_path_config,
        "Script.Core.game_type": game_type,
        "Script.Core.constant": constant,
        "Script.Core.get_text": get_text,
        "Script.Design": design_module,
        "Script.Design.instuct_judege": design_module.instuct_judege,
        "Script.Design.handle_premise": handle_premise,
        "Script.Design.update": design_module.update,
        "Script.Design.character_behavior": design_module.character_behavior,
        "Script.Design.attr_calculation": design_module.attr_calculation,
        "Script.Design.map_handle": design_module.map_handle,
        "Script.UI": ui_module,
        "Script.UI.Moudle": moudle_module,
        "Script.UI.Moudle.draw": draw,
        "Script.Config": config_module,
        "Script.Config.game_config": game_config,
        "Script.Config.normal_config": normal_config,
        "Script.System": system_module,
        "Script.System.Sex_System": sex_system_module,
        "Script.System.Sex_System.group_sex_panel": group_sex_panel,
    }
    old_modules = {name: sys.modules.get(name, missing) for name in module_map}
    sys.modules.update(module_map)

    def restore():
        """参数：无；返回：None；用途：恢复测试前模块表。"""
        for name, old_module in old_modules.items():
            if old_module is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old_module

    return restore, settle_calls, get_template_calls


def load_ai_module():
    """参数：无；返回：dict为AI模块命名空间；用途：加载真实群交AI函数。"""
    from pathlib import Path

    script_path = Path(__file__).resolve().parents[2] / "Script" / "Design" / "handle_npc_ai_in_h.py"
    namespace = {"__name__": "handle_npc_ai_in_h_type1_component_test"}
    exec(compile(script_path.read_text(encoding="utf-8"), str(script_path), "exec"), namespace)
    return namespace


def test_type1_template_members_get_masturbation_intent_before_early_return():
    """参数：无；返回：None；用途：验证AI类型1下模板内初始和受邀参与者不会在生成自慰意图前早退。"""
    cache = Cache()
    restore, settle_calls, get_template_calls = install_fake_modules(cache, [1, 2], npc_ai_type=1)
    try:
        namespace = load_ai_module()

        namespace["npc_ai_in_group_sex"](1)
        namespace["npc_ai_in_group_sex"](2)

        assert cache.character_data[1].sp_flag.masturebate == 3
        assert cache.character_data[2].sp_flag.masturebate == 3
        assert cache.character_data[1].behavior.behavior_id == "share_blankly"
        assert cache.character_data[2].behavior.behavior_id == "share_blankly"
        assert settle_calls == [(1, 1), (2, 1)]
        assert get_template_calls == []
    finally:
        restore()


def test_non_type1_template_members_keep_template_early_return():
    """参数：无；返回：None；用途：记录非类型1下模板成员仍由原模板保护早退且不强制自慰。"""
    cache = Cache()
    restore, settle_calls, get_template_calls = install_fake_modules(cache, [1, 2], npc_ai_type=0)
    try:
        namespace = load_ai_module()

        namespace["npc_ai_in_group_sex"](1)
        namespace["npc_ai_in_group_sex"](2)

        assert cache.character_data[1].sp_flag.masturebate == 0
        assert cache.character_data[2].sp_flag.masturebate == 0
        assert settle_calls == []
        assert get_template_calls == []
    finally:
        restore()


if __name__ == "__main__":
    test_type1_template_members_get_masturbation_intent_before_early_return()
    test_non_type1_template_members_keep_template_early_return()
    print("group sex AI type1 template-member tests passed", flush=True)
