from collections import defaultdict
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


class Character:
    def __init__(self, target_character_id=0, name="", position=None):
        self.target_character_id = target_character_id
        self.name = name
        self.position = position or []
        self.behavior = SimpleNamespace(move_src=[])
        self.second_behavior = {}
        self.must_settle_second_behavior_id_list = []
        self.must_show_second_behavior_id_list = []


class Cache:
    def __init__(self):
        self.character_data = {0: Character()}


class ChangeData:
    def __init__(self):
        self.target_change = {}
        self.status_data = defaultdict(int)


def load_script(script_name):
    mod_root = Path(__file__).resolve().parents[1]
    script_path = mod_root / "scripts" / script_name
    namespace = {
        "__name__": f"mod_local_bugfix_{script_name}_test",
        "cache": Cache(),
        "game_type": SimpleNamespace(TargetChange=lambda: ChangeData()),
        "random": SimpleNamespace(shuffle=lambda values: values.reverse()),
        "_": lambda text: text,
        "game_config": SimpleNamespace(config_behavior_effect_data={}),
        "constant": SimpleNamespace(settle_second_behavior_effect_data={}),
    }
    source = script_path.read_text(encoding="utf-8")
    if script_name == "local_bugfix.py":
        source = source.replace("\n_install_registry_patches()\n", "\n")
    exec(compile(source, str(script_path), "exec"), namespace)
    return namespace


def test_same_part_uses_only_highest_display_strength():
    namespace = load_script("h_orgasm_batch.py")
    batch = namespace["OrgasmBatch"]()

    batch.add_part_orgasm("b_orgasm_small")
    batch.add_part_orgasm("b_orgasm_strong")
    batch.add_part_orgasm("c_orgasm_normal")

    ordered = namespace["_get_ordered_orgasm_part_behaviors"](batch)

    assert ordered == ["b_orgasm_strong", "c_orgasm_normal"]
    assert batch.effect_behavior_set == {"b_orgasm_small", "b_orgasm_strong", "c_orgasm_normal"}


def test_npc_orgasm_settle_uses_new_unfiltered_second_effect_pass():
    namespace = load_script("h_orgasm_batch.py")
    cache = Cache()
    cache.character_data[1] = Character()
    cache.character_data[1].second_behavior = {"old_orgasm": 1, "mark_test": 1}
    namespace["_cache"] = lambda: cache
    calls = []

    fake_second_behavior = ModuleType("Script.Design.second_behavior")
    fake_second_behavior.judge_character_first_meet = lambda character_id: calls.append(("first", character_id))
    fake_second_behavior.insert_position_effect = lambda character_id, change_data: calls.append(("insert", character_id))
    fake_second_behavior.item_effect = lambda character_id: calls.append(("item", character_id))
    fake_second_behavior.orgasm_judge = lambda character_id, change_data: calls.append(("orgasm", character_id))
    fake_second_behavior.mark_effect = lambda character_id, change_data: calls.append(("mark", character_id))

    def fake_second_behavior_effect(character_id, change_data, second_behavior_list=[]):
        calls.append(("effect", character_id, tuple(second_behavior_list)))

    fake_second_behavior.second_behavior_effect = fake_second_behavior_effect
    fake_design = ModuleType("Script.Design")
    fake_design.second_behavior = fake_second_behavior

    with patch.dict("sys.modules", {"Script.Design": fake_design, "Script.Design.second_behavior": fake_second_behavior}):
        namespace["patched_check_second_effect"](1, ChangeData())

    assert ("effect", 1, ()) in calls
    assert calls.count(("effect", 1, ())) == 2
    assert ("effect", 1, ("old_orgasm",)) not in calls
    assert ("effect", 1, ("mark_test",)) in calls


def test_human_power_batch_suppresses_parts_and_draws_original_plural_text_once():
    namespace = load_script("h_orgasm_batch.py")
    original_calls = []
    draw_calls = []

    def fake_call_original(module_name, function_name, climax_degree, character_id, draw_flag):
        original_calls.append((climax_degree, character_id, draw_flag))
        return {1: 0.2, 3: 1.0, 7: 32.0}[climax_degree]

    namespace["call_original"] = fake_call_original
    namespace["_draw_plural_human_power_text"] = lambda climax_degree, character_id, amount: draw_calls.append((climax_degree, character_id, amount))

    power_batch = namespace["_push_power_batch"](7, 3, True)
    namespace["patched_store_power_by_human_power"](1, 3, True)
    namespace["patched_store_power_by_human_power"](3, 3, True)
    namespace["patched_store_power_by_human_power"](7, 3, True)
    namespace["_finish_power_batch"](power_batch)

    assert original_calls == [(1, 3, False), (3, 3, False), (7, 3, False)]
    assert draw_calls == [(7, 3, 33.2)]


def test_compact_part_info_keeps_only_one_following_line_feed():
    namespace = load_script("h_orgasm_batch.py")
    cache = Cache()
    cache.character_data[1] = Character()
    cache.character_data[1].name = "食铁兽"
    namespace["_cache"] = lambda: cache

    info_text = namespace["_get_part_orgasm_info_text"](1, "h_orgasm_strong", extra_blank_line=False)

    assert info_text == "\n食铁兽心理强绝顶\n"


def test_compact_orgasm_summary_groups_remaining_parts_on_one_line():
    namespace = load_script("h_orgasm_batch.py")
    cache = Cache()
    cache.character_data[1] = Character()
    cache.character_data[1].name = "食铁兽"
    namespace["_cache"] = lambda: cache
    draw_calls = []

    class FakeWaitDraw:
        def __init__(self):
            self.text = ""
            self.style = ""
            self.width = 0

        def draw(self):
            draw_calls.append((self.text, self.style, self.width))

    fake_draw = ModuleType("Script.UI.Moudle.draw")
    fake_draw.WaitDraw = FakeWaitDraw
    fake_moudle = ModuleType("Script.UI.Moudle")
    fake_moudle.draw = fake_draw
    fake_config = ModuleType("Script.Config")
    fake_config.normal_config = SimpleNamespace(config_normal=SimpleNamespace(text_width=80))

    with patch.dict(
        "sys.modules",
        {
            "Script.Config": fake_config,
            "Script.UI.Moudle": fake_moudle,
            "Script.UI.Moudle.draw": fake_draw,
        },
    ):
        namespace["_draw_compact_orgasm_summary"](1, ["a_orgasm_strong", "v_orgasm_strong", "c_orgasm_normal", "u_orgasm_small", "b_orgasm_small"])

    assert draw_calls == [("\n食铁兽 肛肠、阴道 强绝顶，阴蒂 绝顶，尿道、胸部 小绝顶\n", "gold_enrod", 80)]


def test_orgasm_settle_keeps_translation_function_available_for_achievements():
    namespace = load_script("h_orgasm_batch.py")
    cache = Cache()
    character = Character()
    character.h_state = SimpleNamespace(orgasm_level=defaultdict(int), shoot_position_body=-1, plural_orgasm_set=set())
    character.ability = defaultdict(lambda: 10)
    cache.character_data[1] = character
    cache.achievement = SimpleNamespace(group_sex_record={}, hidden_sex_record={}, exhibitionism_sex_record={}, sleep_sex_record={})
    namespace["_cache"] = lambda: cache
    namespace["game_config"].config_behavior_effect_data = {
        "s_orgasm_small": [],
        "b_orgasm_small": [],
        "plural_orgasm_2": [],
    }
    achievement_calls = []

    fake_handle_premise = ModuleType("Script.Design.handle_premise")
    for name in (
        "handle_unconscious_flag_3",
        "handle_self_orgasm_edge",
        "handle_group_sex_mode_on",
        "handle_hidden_sex_mode_ge_1",
        "handle_exhibitionism_sex_mode_ge_1",
        "handle_unconscious_flag_1",
        "handle_self_orgasm_edge_relase_or_time_stop_orgasm_relase",
        "handle_milk_ge_80",
        "handle_urinate_ge_80",
        "handle_in_human_power_room",
        "handle_in_player_scene",
    ):
        setattr(fake_handle_premise, name, lambda character_id: False)

    fake_second_behavior = ModuleType("Script.Design.second_behavior")
    fake_second_behavior.judge_orgasm_degree = lambda now_data: 0
    fake_second_behavior.character_get_second_behavior = lambda character_id, behavior_id: cache.character_data[character_id].second_behavior.__setitem__(behavior_id, 1)

    fake_talk = ModuleType("Script.Design.talk")
    fake_talk.handle_second_talk = lambda character_id, behavior_id: None
    fake_talk.second_behavior_info_text = lambda character_id, behavior_id: None

    fake_design = ModuleType("Script.Design")
    fake_design.handle_premise = fake_handle_premise
    fake_design.second_behavior = fake_second_behavior
    fake_design.talk = fake_talk
    fake_settle_behavior = ModuleType("Script.Design.settle_behavior")
    fake_settle_behavior.handle_comprehensive_value_effect = lambda *args, **kwargs: None
    fake_design.settle_behavior = fake_settle_behavior
    fake_common = ModuleType("Script.Settle.common_default")
    fake_common.base_chara_experience_common_settle = lambda *args, **kwargs: None
    fake_achievement_panel = ModuleType("Script.UI.Panel.achievement_panel")
    fake_achievement_panel.achievement_flow = lambda achievement_type, achievement_id: achievement_calls.append((achievement_type, achievement_id))
    fake_panel = ModuleType("Script.UI.Panel")
    fake_panel.achievement_panel = fake_achievement_panel
    fake_power = ModuleType("Script.UI.Panel.manage_power_system_panel")
    fake_power.store_power_by_human_power = lambda *args, **kwargs: 0

    with patch.dict(
        "sys.modules",
        {
            "Script.Design": fake_design,
            "Script.Design.handle_premise": fake_handle_premise,
            "Script.Design.second_behavior": fake_second_behavior,
            "Script.Design.talk": fake_talk,
            "Script.Design.settle_behavior": fake_settle_behavior,
            "Script.Settle.common_default": fake_common,
            "Script.UI.Panel": fake_panel,
            "Script.UI.Panel.achievement_panel": fake_achievement_panel,
            "Script.UI.Panel.manage_power_system_panel": fake_power,
        },
    ):
        namespace["patched_orgasm_settle"](1, ChangeData(), normal_orgasm_dict={0: 1, 1: 1})

    assert achievement_calls == [("绝顶", 1221)]


def test_remote_orgasm_batch_settles_without_drawing():
    namespace = load_script("h_orgasm_batch.py")
    cache = Cache()
    cache.character_data[0] = Character(name="博士", position=["A"])
    character = Character(name="远处干员", position=["B"])
    character.h_state = SimpleNamespace(orgasm_level=defaultdict(int), shoot_position_body=-1, plural_orgasm_set=set())
    character.ability = defaultdict(lambda: 10)
    cache.character_data[1] = character
    cache.achievement = SimpleNamespace(group_sex_record={}, hidden_sex_record={}, exhibitionism_sex_record={}, sleep_sex_record={})
    namespace["_cache"] = lambda: cache
    namespace["game_config"].config_behavior_effect_data = {"s_orgasm_small": ["draw_effect"]}
    talk_calls = []
    effect_calls = []
    draw_calls = []

    fake_handle_premise = ModuleType("Script.Design.handle_premise")
    for name in (
        "handle_unconscious_flag_3",
        "handle_self_orgasm_edge",
        "handle_group_sex_mode_on",
        "handle_hidden_sex_mode_ge_1",
        "handle_exhibitionism_sex_mode_ge_1",
        "handle_unconscious_flag_1",
        "handle_self_orgasm_edge_relase_or_time_stop_orgasm_relase",
        "handle_milk_ge_80",
        "handle_urinate_ge_80",
        "handle_in_human_power_room",
        "handle_in_player_scene",
    ):
        setattr(fake_handle_premise, name, lambda character_id: False)

    fake_second_behavior = ModuleType("Script.Design.second_behavior")
    fake_second_behavior.judge_orgasm_degree = lambda now_data: 0
    fake_second_behavior.character_get_second_behavior = lambda character_id, behavior_id: cache.character_data[character_id].second_behavior.__setitem__(behavior_id, 1)
    fake_second_behavior.judge_orgasm_edge_success = lambda character_id: True

    fake_talk = ModuleType("Script.Design.talk")
    fake_talk.handle_second_talk = lambda character_id, behavior_id: talk_calls.append((character_id, behavior_id))
    fake_talk.second_behavior_info_text = lambda character_id, behavior_id: None

    class FakeNormalDraw:
        def draw(self):
            draw_calls.append("draw")

    fake_draw = ModuleType("Script.UI.Moudle.draw")
    fake_draw.NormalDraw = FakeNormalDraw
    fake_draw.WaitDraw = FakeNormalDraw
    fake_draw.LineFeedWaitDraw = FakeNormalDraw
    fake_moudle = ModuleType("Script.UI.Moudle")
    fake_moudle.draw = fake_draw

    def fake_draw_effect(character_id, change_data):
        effect_calls.append((character_id, "draw_effect"))
        from Script.UI.Moudle import draw

        draw.NormalDraw().draw()

    namespace["constant"].settle_second_behavior_effect_data = {"draw_effect": fake_draw_effect}

    fake_design = ModuleType("Script.Design")
    fake_design.handle_premise = fake_handle_premise
    fake_design.second_behavior = fake_second_behavior
    fake_design.talk = fake_talk
    fake_settle_behavior = ModuleType("Script.Design.settle_behavior")
    fake_settle_behavior.handle_comprehensive_value_effect = lambda *args, **kwargs: None
    fake_design.settle_behavior = fake_settle_behavior
    fake_common = ModuleType("Script.Settle.common_default")
    fake_common.base_chara_experience_common_settle = lambda *args, **kwargs: None
    fake_achievement_panel = ModuleType("Script.UI.Panel.achievement_panel")
    fake_achievement_panel.achievement_flow = lambda *args, **kwargs: None
    fake_panel = ModuleType("Script.UI.Panel")
    fake_panel.achievement_panel = fake_achievement_panel
    fake_power = ModuleType("Script.UI.Panel.manage_power_system_panel")
    fake_power.store_power_by_human_power = lambda *args, **kwargs: 0

    with patch.dict(
        "sys.modules",
        {
            "Script.Design": fake_design,
            "Script.Design.handle_premise": fake_handle_premise,
            "Script.Design.second_behavior": fake_second_behavior,
            "Script.Design.talk": fake_talk,
            "Script.Design.settle_behavior": fake_settle_behavior,
            "Script.Settle.common_default": fake_common,
            "Script.UI.Moudle": fake_moudle,
            "Script.UI.Moudle.draw": fake_draw,
            "Script.UI.Panel": fake_panel,
            "Script.UI.Panel.achievement_panel": fake_achievement_panel,
            "Script.UI.Panel.manage_power_system_panel": fake_power,
        },
    ):
        namespace["patched_orgasm_settle"](1, ChangeData(), normal_orgasm_dict={0: 1})

    assert talk_calls == []
    assert effect_calls == [(1, "draw_effect")]
    assert draw_calls == []
    assert cache.character_data[1].second_behavior["s_orgasm_small"] == 0


def test_remote_orgasm_edge_success_draw_is_suppressed():
    namespace = load_script("h_orgasm_batch.py")
    cache = Cache()
    cache.character_data[0] = Character(name="博士", position=["A"])
    character = Character(name="远处干员", position=["B"])
    character.h_state = SimpleNamespace(
        orgasm_level=defaultdict(int),
        orgasm_edge_count=defaultdict(int),
        shoot_position_body=-1,
        plural_orgasm_set=set(),
    )
    character.ability = defaultdict(lambda: 10)
    cache.character_data[1] = character
    cache.achievement = SimpleNamespace(group_sex_record={}, hidden_sex_record={}, exhibitionism_sex_record={}, sleep_sex_record={})
    namespace["_cache"] = lambda: cache
    namespace["game_config"].config_behavior_effect_data = {"s_orgasm_edge": ["edge_effect"]}
    effect_calls = []
    draw_calls = []

    fake_handle_premise = ModuleType("Script.Design.handle_premise")
    premise_values = {
        "handle_unconscious_flag_3": False,
        "handle_self_orgasm_edge": True,
        "handle_group_sex_mode_on": False,
        "handle_hidden_sex_mode_ge_1": False,
        "handle_exhibitionism_sex_mode_ge_1": False,
        "handle_unconscious_flag_1": False,
        "handle_self_orgasm_edge_relase_or_time_stop_orgasm_relase": False,
        "handle_milk_ge_80": False,
        "handle_urinate_ge_80": False,
        "handle_in_human_power_room": False,
        "handle_in_player_scene": False,
    }
    for name, value in premise_values.items():
        setattr(fake_handle_premise, name, lambda character_id, value=value: value)

    class FakeNormalDraw:
        def draw(self):
            draw_calls.append("edge_draw")

    fake_draw = ModuleType("Script.UI.Moudle.draw")
    fake_draw.NormalDraw = FakeNormalDraw
    fake_draw.WaitDraw = FakeNormalDraw
    fake_draw.LineFeedWaitDraw = FakeNormalDraw
    fake_moudle = ModuleType("Script.UI.Moudle")
    fake_moudle.draw = fake_draw

    fake_second_behavior = ModuleType("Script.Design.second_behavior")
    fake_second_behavior.character_get_second_behavior = lambda character_id, behavior_id: cache.character_data[character_id].second_behavior.__setitem__(behavior_id, 1)

    def fake_judge_orgasm_edge_success(character_id):
        from Script.UI.Moudle import draw

        draw.NormalDraw().draw()
        return True

    fake_second_behavior.judge_orgasm_edge_success = fake_judge_orgasm_edge_success

    fake_talk = ModuleType("Script.Design.talk")
    fake_talk.handle_second_talk = lambda character_id, behavior_id: draw_calls.append(("talk", character_id, behavior_id))
    fake_talk.second_behavior_info_text = lambda character_id, behavior_id: None

    def fake_edge_effect(character_id, change_data):
        effect_calls.append((character_id, "edge_effect"))
        from Script.UI.Moudle import draw

        draw.NormalDraw().draw()

    namespace["constant"].settle_second_behavior_effect_data = {"edge_effect": fake_edge_effect}

    fake_design = ModuleType("Script.Design")
    fake_design.handle_premise = fake_handle_premise
    fake_design.second_behavior = fake_second_behavior
    fake_design.talk = fake_talk
    fake_settle_behavior = ModuleType("Script.Design.settle_behavior")
    fake_settle_behavior.handle_comprehensive_value_effect = lambda *args, **kwargs: None
    fake_design.settle_behavior = fake_settle_behavior
    fake_common = ModuleType("Script.Settle.common_default")
    fake_common.base_chara_experience_common_settle = lambda *args, **kwargs: None
    fake_achievement_panel = ModuleType("Script.UI.Panel.achievement_panel")
    fake_achievement_panel.achievement_flow = lambda *args, **kwargs: None
    fake_panel = ModuleType("Script.UI.Panel")
    fake_panel.achievement_panel = fake_achievement_panel
    fake_power = ModuleType("Script.UI.Panel.manage_power_system_panel")
    fake_power.store_power_by_human_power = lambda *args, **kwargs: 0

    with patch.dict(
        "sys.modules",
        {
            "Script.Design": fake_design,
            "Script.Design.handle_premise": fake_handle_premise,
            "Script.Design.second_behavior": fake_second_behavior,
            "Script.Design.talk": fake_talk,
            "Script.Design.settle_behavior": fake_settle_behavior,
            "Script.Settle.common_default": fake_common,
            "Script.UI.Moudle": fake_moudle,
            "Script.UI.Moudle.draw": fake_draw,
            "Script.UI.Panel": fake_panel,
            "Script.UI.Panel.achievement_panel": fake_achievement_panel,
            "Script.UI.Panel.manage_power_system_panel": fake_power,
        },
    ):
        namespace["patched_orgasm_settle"](1, ChangeData(), normal_orgasm_dict={0: 1})

    assert draw_calls == []
    assert effect_calls == [(1, "edge_effect")]
    assert cache.character_data[1].second_behavior["s_orgasm_edge"] == 0


def test_remote_plural_orgasm_achievement_notice_is_suppressed():
    namespace = load_script("h_orgasm_batch.py")
    cache = Cache()
    cache.character_data[0] = Character(name="博士", position=["A"])
    character = Character(name="远处干员", position=["B"])
    character.h_state = SimpleNamespace(orgasm_level=defaultdict(int), shoot_position_body=-1, plural_orgasm_set=set())
    character.ability = defaultdict(lambda: 10)
    cache.character_data[1] = character
    cache.achievement = SimpleNamespace(group_sex_record={}, hidden_sex_record={}, exhibitionism_sex_record={}, sleep_sex_record={})
    namespace["_cache"] = lambda: cache
    namespace["game_config"].config_behavior_effect_data = {
        "s_orgasm_small": [],
        "b_orgasm_small": [],
        "plural_orgasm_2": [],
    }
    achievement_calls = []
    draw_calls = []

    fake_handle_premise = ModuleType("Script.Design.handle_premise")
    for name in (
        "handle_unconscious_flag_3",
        "handle_self_orgasm_edge",
        "handle_group_sex_mode_on",
        "handle_hidden_sex_mode_ge_1",
        "handle_exhibitionism_sex_mode_ge_1",
        "handle_unconscious_flag_1",
        "handle_self_orgasm_edge_relase_or_time_stop_orgasm_relase",
        "handle_milk_ge_80",
        "handle_urinate_ge_80",
        "handle_in_human_power_room",
        "handle_in_player_scene",
    ):
        setattr(fake_handle_premise, name, lambda character_id: False)

    fake_second_behavior = ModuleType("Script.Design.second_behavior")
    fake_second_behavior.judge_orgasm_degree = lambda now_data: 0
    fake_second_behavior.character_get_second_behavior = lambda character_id, behavior_id: cache.character_data[character_id].second_behavior.__setitem__(behavior_id, 1)

    fake_talk = ModuleType("Script.Design.talk")
    fake_talk.handle_second_talk = lambda character_id, behavior_id: draw_calls.append(("talk", character_id, behavior_id))
    fake_talk.second_behavior_info_text = lambda character_id, behavior_id: None

    class FakeWaitDraw:
        def draw(self):
            draw_calls.append("achievement_draw")

    fake_draw = ModuleType("Script.UI.Moudle.draw")
    fake_draw.WaitDraw = FakeWaitDraw
    fake_moudle = ModuleType("Script.UI.Moudle")
    fake_moudle.draw = fake_draw

    fake_design = ModuleType("Script.Design")
    fake_design.handle_premise = fake_handle_premise
    fake_design.second_behavior = fake_second_behavior
    fake_design.talk = fake_talk
    fake_settle_behavior = ModuleType("Script.Design.settle_behavior")
    fake_settle_behavior.handle_comprehensive_value_effect = lambda *args, **kwargs: None
    fake_design.settle_behavior = fake_settle_behavior
    fake_common = ModuleType("Script.Settle.common_default")
    fake_common.base_chara_experience_common_settle = lambda *args, **kwargs: None
    fake_achievement_panel = ModuleType("Script.UI.Panel.achievement_panel")

    def fake_achievement_flow(achievement_type, achievement_id):
        achievement_calls.append((achievement_type, achievement_id))
        from Script.UI.Moudle import draw

        draw.WaitDraw().draw()

    fake_achievement_panel.achievement_flow = fake_achievement_flow
    fake_panel = ModuleType("Script.UI.Panel")
    fake_panel.achievement_panel = fake_achievement_panel
    fake_power = ModuleType("Script.UI.Panel.manage_power_system_panel")
    fake_power.store_power_by_human_power = lambda *args, **kwargs: 0

    with patch.dict(
        "sys.modules",
        {
            "Script.Design": fake_design,
            "Script.Design.handle_premise": fake_handle_premise,
            "Script.Design.second_behavior": fake_second_behavior,
            "Script.Design.talk": fake_talk,
            "Script.Design.settle_behavior": fake_settle_behavior,
            "Script.Settle.common_default": fake_common,
            "Script.UI.Moudle": fake_moudle,
            "Script.UI.Moudle.draw": fake_draw,
            "Script.UI.Panel": fake_panel,
            "Script.UI.Panel.achievement_panel": fake_achievement_panel,
            "Script.UI.Panel.manage_power_system_panel": fake_power,
        },
    ):
        namespace["patched_orgasm_settle"](1, ChangeData(), normal_orgasm_dict={0: 1, 1: 1})

    assert achievement_calls == [("绝顶", 1221)]
    assert draw_calls == []
    assert cache.character_data[1].second_behavior["plural_orgasm_2"] == 0


def test_remote_orgasm_effect_suppresses_panel_draws_and_input_wait():
    namespace = load_script("h_orgasm_batch.py")
    cache = Cache()
    cache.character_data[0] = Character(name="博士", position=["A"])
    character = Character(name="远处干员", position=["B"])
    character.h_state = SimpleNamespace(plural_orgasm_set=set())
    character.second_behavior = {"extra_orgasm": 1}
    cache.character_data[1] = character
    namespace["_cache"] = lambda: cache
    namespace["game_config"].config_behavior_effect_data = {"extra_orgasm": ["panel_effect"]}
    draw_calls = []
    choice_calls = []
    store_calls = []

    class FakeTitleLineDraw:
        def __init__(self, *args, **kwargs):
            pass

        def draw(self):
            draw_calls.append("title")

    class FakeLeftButton:
        def __init__(self, *args, **kwargs):
            pass

        def draw(self):
            draw_calls.append("button")

    fake_draw = ModuleType("Script.UI.Moudle.draw")
    fake_draw.TitleLineDraw = FakeTitleLineDraw
    fake_draw.LeftButton = FakeLeftButton
    fake_moudle = ModuleType("Script.UI.Moudle")
    fake_moudle.draw = fake_draw

    fake_flow_handle = ModuleType("Script.Core.flow_handle")

    def unexpected_askfor_all(*args, **kwargs):
        raise AssertionError("远处后台结算不应等待玩家输入")

    fake_flow_handle.askfor_all = unexpected_askfor_all
    fake_flow_handle.askfor_int = unexpected_askfor_all
    fake_flow_handle.askfor_str = unexpected_askfor_all
    fake_flow_handle.askfor_wait = unexpected_askfor_all
    fake_flow_handle.print_cmd = unexpected_askfor_all
    fake_flow_handle.print_image_cmd = unexpected_askfor_all
    fake_flow_handle_web = ModuleType("Script.Core.flow_handle_web")
    fake_flow_handle_web.askfor_all = unexpected_askfor_all
    fake_flow_handle_web.askfor_int = unexpected_askfor_all
    fake_flow_handle_web.askfor_str = unexpected_askfor_all
    fake_flow_handle_web.askfor_wait = unexpected_askfor_all
    fake_flow_handle_web.print_cmd = unexpected_askfor_all
    fake_flow_handle_web.print_image_cmd = unexpected_askfor_all
    fake_io_init = ModuleType("Script.Core.io_init")
    fake_io_init.era_print = unexpected_askfor_all
    fake_io_init.clear_screen = unexpected_askfor_all
    fake_io_init.clear_screen_and_history = unexpected_askfor_all
    fake_io_web = ModuleType("Script.Core.io_web")
    fake_io_web.era_print = unexpected_askfor_all
    fake_io_web.clear_screen = unexpected_askfor_all
    fake_io_web.clear_screen_and_history = unexpected_askfor_all
    fake_core = ModuleType("Script.Core")
    fake_core.flow_handle = fake_flow_handle
    fake_core.flow_handle_web = fake_flow_handle_web
    fake_core.io_init = fake_io_init
    fake_core.io_web = fake_io_web

    def fake_panel_effect(character_id, change_data):
        from Script.Core import flow_handle, flow_handle_web, io_init, io_web
        from Script.UI.Moudle import draw

        draw.TitleLineDraw("后台面板", 80).draw()
        draw.LeftButton("[返回]", "返回", 80).draw()
        io_init.era_print("不应显示")
        io_web.era_print("不应显示")
        flow_handle.print_cmd("[确认]", "确认")
        choice_calls.append(flow_handle.askfor_all(["继续", "返回"]))
        choice_calls.append(flow_handle.askfor_str("请输入文本："))
        choice_calls.append(flow_handle_web.askfor_int("请输入数字：", 7))
        choice_calls.append(flow_handle_web.askfor_str("请输入文本："))
        choice_calls.append(flow_handle_web.askfor_str("请输入文本：", "默认值"))

    namespace["constant"].settle_second_behavior_effect_data = {"panel_effect": fake_panel_effect}

    fake_talk = ModuleType("Script.Design.talk")
    fake_talk.handle_second_talk = lambda character_id, behavior_id: draw_calls.append(("talk", character_id, behavior_id))
    fake_talk.second_behavior_info_text = lambda character_id, behavior_id: None

    fake_design = ModuleType("Script.Design")
    fake_design.talk = fake_talk
    fake_settle_behavior = ModuleType("Script.Design.settle_behavior")
    fake_settle_behavior.handle_comprehensive_value_effect = lambda *args, **kwargs: None
    fake_design.settle_behavior = fake_settle_behavior
    fake_power = ModuleType("Script.UI.Panel.manage_power_system_panel")

    def fake_store_power_by_human_power(climax_degree, character_id, draw_flag=True):
        store_calls.append((climax_degree, character_id, draw_flag))
        from Script.UI.Moudle import draw

        draw.TitleLineDraw("发电提示", 80).draw()
        return 0

    fake_power.store_power_by_human_power = fake_store_power_by_human_power

    batch = namespace["OrgasmBatch"]()
    batch.add_effect_behavior("extra_orgasm")
    batch.human_power_climax_degree = 5
    batch.human_power_draw_flag = False

    with patch.dict(
        "sys.modules",
        {
            "Script.Core": fake_core,
            "Script.Core.flow_handle": fake_flow_handle,
            "Script.Core.flow_handle_web": fake_flow_handle_web,
            "Script.Core.io_init": fake_io_init,
            "Script.Core.io_web": fake_io_web,
            "Script.Design": fake_design,
            "Script.Design.talk": fake_talk,
            "Script.Design.settle_behavior": fake_settle_behavior,
            "Script.UI.Moudle": fake_moudle,
            "Script.UI.Moudle.draw": fake_draw,
            "Script.UI.Panel.manage_power_system_panel": fake_power,
        },
    ):
        namespace["_flush_orgasm_batch"](1, ChangeData(), batch)

    assert draw_calls == []
    assert choice_calls == ["返回", "19", 7, "19", "默认值"]
    assert store_calls == [(5, 1, False)]
    assert cache.character_data[1].second_behavior["extra_orgasm"] == 0


def test_move_src_visible_non_part_orgasm_batch_keeps_second_talk():
    namespace = load_script("h_orgasm_batch.py")
    cache = Cache()
    cache.character_data[0] = Character(name="博士", position=["A"])
    character = Character(name="移动中的干员", position=["B"])
    character.behavior.move_src = ["A"]
    character.h_state = SimpleNamespace(plural_orgasm_set=set())
    character.second_behavior = {"extra_orgasm": 1}
    cache.character_data[1] = character
    namespace["_cache"] = lambda: cache
    namespace["game_config"].config_behavior_effect_data = {"extra_orgasm": []}
    talk_calls = []

    fake_talk = ModuleType("Script.Design.talk")
    fake_talk.handle_second_talk = lambda character_id, behavior_id: talk_calls.append((character_id, behavior_id))
    fake_talk.second_behavior_info_text = lambda character_id, behavior_id: None

    fake_design = ModuleType("Script.Design")
    fake_design.talk = fake_talk
    fake_settle_behavior = ModuleType("Script.Design.settle_behavior")
    fake_settle_behavior.handle_comprehensive_value_effect = lambda *args, **kwargs: None
    fake_design.settle_behavior = fake_settle_behavior
    fake_power = ModuleType("Script.UI.Panel.manage_power_system_panel")
    fake_power.store_power_by_human_power = lambda *args, **kwargs: 0

    batch = namespace["OrgasmBatch"]()
    batch.add_effect_behavior("extra_orgasm")

    with patch.dict(
        "sys.modules",
        {
            "Script.Design": fake_design,
            "Script.Design.talk": fake_talk,
            "Script.Design.settle_behavior": fake_settle_behavior,
            "Script.UI.Panel.manage_power_system_panel": fake_power,
        },
    ):
        namespace["_flush_orgasm_batch"](1, ChangeData(), batch)

    assert talk_calls == [(1, "extra_orgasm")]
    assert cache.character_data[1].second_behavior["extra_orgasm"] == 0


def test_hypnosis_orgasm_second_talk_gate_only_bypasses_hypnosis_states():
    namespace = load_script("h_orgasm_batch.py")
    cache = Cache()
    cache.character_data[1] = Character()
    cache.character_data[1].sp_flag = SimpleNamespace(unconscious_h=0)
    namespace["_cache"] = lambda: cache

    for hypnosis_flag in (4, 5, 6, 7):
        cache.character_data[1].sp_flag.unconscious_h = hypnosis_flag
        assert namespace["_should_pass_unconscious_gate_for_orgasm_second_talk"](1) is True

    for non_hypnosis_flag in (0, 1, 2, 3):
        cache.character_data[1].sp_flag.unconscious_h = non_hypnosis_flag
        assert namespace["_should_pass_unconscious_gate_for_orgasm_second_talk"](1) is False


def test_mind_control_plural_orgasm_keeps_second_talk_past_unconscious_gate():
    namespace = load_script("h_orgasm_batch.py")
    cache = Cache()
    cache.is_collection = False
    cache.character_data[0] = Character(name="博士", position=["A"])
    character = Character(name="赤刀明霄陈", position=["A"])
    character.h_state = SimpleNamespace(plural_orgasm_set=set())
    character.sp_flag = SimpleNamespace(unconscious_h=7)
    character.second_behavior = {"plural_orgasm_7": 1}
    cache.character_data[1] = character
    namespace["_cache"] = lambda: cache
    namespace["game_config"].config_behavior_effect_data = {"plural_orgasm_7": []}
    calls = []

    fake_talk = ModuleType("Script.Design.talk")

    def fake_handle_talk_sub(character_id, behavior_id, calculated_premise_dict, unconscious_pass_flag=False):
        calls.append(("sub", behavior_id, unconscious_pass_flag))
        if unconscious_pass_flag:
            return {1: {"talk_id"}}, calculated_premise_dict
        return {}, calculated_premise_dict

    def fake_choice_talk_from_talk_data(now_talk_data, behavior_id):
        if now_talk_data:
            return "二段口上正文", "talk_id"
        return "", ""

    def fake_handle_talk_draw(character_id, talk_text, now_talk_id, second_behavior_id=""):
        calls.append(("draw", second_behavior_id, talk_text))

    def fake_original_handle_second_talk(character_id, behavior_id):
        now_talk_data, calculated_premise_dict = fake_handle_talk_sub(character_id, behavior_id, {}, unconscious_pass_flag=False)
        talk_text, now_talk_id = fake_choice_talk_from_talk_data(now_talk_data, behavior_id)
        fake_handle_talk_draw(character_id, talk_text, now_talk_id, behavior_id)

    fake_talk.handle_second_talk = fake_original_handle_second_talk
    fake_talk.handle_talk_sub = fake_handle_talk_sub
    fake_talk.choice_talk_from_talk_data = fake_choice_talk_from_talk_data
    fake_talk.handle_talk_draw = fake_handle_talk_draw
    fake_talk.second_behavior_info_text = lambda character_id, behavior_id: None

    fake_design = ModuleType("Script.Design")
    fake_design.talk = fake_talk
    fake_settle_behavior = ModuleType("Script.Design.settle_behavior")
    fake_settle_behavior.handle_comprehensive_value_effect = lambda *args, **kwargs: None
    fake_design.settle_behavior = fake_settle_behavior
    fake_power = ModuleType("Script.UI.Panel.manage_power_system_panel")
    fake_power.store_power_by_human_power = lambda *args, **kwargs: 0

    batch = namespace["OrgasmBatch"]()
    batch.add_plural_orgasm("plural_orgasm_7", {0, 1, 2, 4, 5, 6, 7})

    with patch.dict(
        "sys.modules",
        {
            "Script.Design": fake_design,
            "Script.Design.talk": fake_talk,
            "Script.Design.settle_behavior": fake_settle_behavior,
            "Script.UI.Panel.manage_power_system_panel": fake_power,
        },
    ):
        namespace["_flush_orgasm_batch"](1, ChangeData(), batch)

    assert ("sub", "plural_orgasm_7", True) in calls
    assert ("draw", "plural_orgasm_7", "二段口上正文") in calls
    assert cache.character_data[1].second_behavior["plural_orgasm_7"] == 0


def test_mind_control_part_orgasm_keeps_second_talk_past_unconscious_gate():
    namespace = load_script("h_orgasm_batch.py")
    cache = Cache()
    cache.is_collection = False
    cache.character_data[0] = Character(name="博士", position=["A"])
    character = Character(name="赤刀明霄陈", position=["A"])
    character.h_state = SimpleNamespace(plural_orgasm_set=set())
    character.sp_flag = SimpleNamespace(unconscious_h=7)
    character.second_behavior = {"v_orgasm_strong": 1}
    cache.character_data[1] = character
    namespace["_cache"] = lambda: cache
    namespace["game_config"].config_behavior_effect_data = {"v_orgasm_strong": []}
    calls = []

    fake_talk = ModuleType("Script.Design.talk")

    def fake_handle_talk_sub(character_id, behavior_id, calculated_premise_dict, unconscious_pass_flag=False):
        calls.append(("sub", behavior_id, unconscious_pass_flag))
        if unconscious_pass_flag:
            return {1: {"talk_id"}}, calculated_premise_dict
        return {}, calculated_premise_dict

    def fake_choice_talk_from_talk_data(now_talk_data, behavior_id):
        if now_talk_data:
            return "部位绝顶口上正文", "talk_id"
        return "", ""

    def fake_handle_talk_draw(character_id, talk_text, now_talk_id, second_behavior_id=""):
        calls.append(("draw", second_behavior_id, talk_text))

    def fake_original_handle_second_talk(character_id, behavior_id):
        now_talk_data, calculated_premise_dict = fake_handle_talk_sub(character_id, behavior_id, {}, unconscious_pass_flag=False)
        talk_text, now_talk_id = fake_choice_talk_from_talk_data(now_talk_data, behavior_id)
        fake_handle_talk_draw(character_id, talk_text, now_talk_id, behavior_id)

    fake_talk.handle_second_talk = fake_original_handle_second_talk
    fake_talk.handle_talk_sub = fake_handle_talk_sub
    fake_talk.choice_talk_from_talk_data = fake_choice_talk_from_talk_data
    fake_talk.handle_talk_draw = fake_handle_talk_draw
    fake_talk.second_behavior_info_text = lambda character_id, behavior_id: None

    fake_design = ModuleType("Script.Design")
    fake_design.talk = fake_talk
    fake_settle_behavior = ModuleType("Script.Design.settle_behavior")
    fake_settle_behavior.handle_comprehensive_value_effect = lambda *args, **kwargs: None
    fake_design.settle_behavior = fake_settle_behavior
    fake_power = ModuleType("Script.UI.Panel.manage_power_system_panel")
    fake_power.store_power_by_human_power = lambda *args, **kwargs: 0

    batch = namespace["OrgasmBatch"]()
    batch.add_part_orgasm("v_orgasm_strong")

    with patch.dict(
        "sys.modules",
        {
            "Script.Design": fake_design,
            "Script.Design.talk": fake_talk,
            "Script.Design.settle_behavior": fake_settle_behavior,
            "Script.UI.Panel.manage_power_system_panel": fake_power,
        },
    ):
        namespace["_flush_orgasm_batch"](1, ChangeData(), batch)

    assert ("sub", "v_orgasm_strong", True) in calls
    assert ("draw", "v_orgasm_strong", "部位绝顶口上正文") in calls
    assert cache.character_data[1].second_behavior["v_orgasm_strong"] == 0


def test_tired_sleep_is_skipped_during_orgasm_batch():
    namespace = load_script("local_bugfix.py")
    cache = Cache()
    cache.character_data[0] = Character(target_character_id=2)
    namespace["_cache"] = lambda: cache
    namespace["_is_orgasm_batch_settling"] = lambda character_id: character_id == 2

    def unexpected_original(*args, **kwargs):
        raise AssertionError("疲劳判定不应在绝顶批处理期间调用原函数")

    namespace["call_original"] = unexpected_original

    assert namespace["patched_judge_character_tired_sleep"](0) is None


if __name__ == "__main__":
    test_same_part_uses_only_highest_display_strength()
    test_npc_orgasm_settle_uses_new_unfiltered_second_effect_pass()
    test_human_power_batch_suppresses_parts_and_draws_original_plural_text_once()
    test_compact_part_info_keeps_only_one_following_line_feed()
    test_compact_orgasm_summary_groups_remaining_parts_on_one_line()
    test_orgasm_settle_keeps_translation_function_available_for_achievements()
    test_remote_orgasm_batch_settles_without_drawing()
    test_remote_orgasm_edge_success_draw_is_suppressed()
    test_remote_plural_orgasm_achievement_notice_is_suppressed()
    test_remote_orgasm_effect_suppresses_panel_draws_and_input_wait()
    test_move_src_visible_non_part_orgasm_batch_keeps_second_talk()
    test_hypnosis_orgasm_second_talk_gate_only_bypasses_hypnosis_states()
    test_mind_control_plural_orgasm_keeps_second_talk_past_unconscious_gate()
    test_mind_control_part_orgasm_keeps_second_talk_past_unconscious_gate()
    test_tired_sleep_is_skipped_during_orgasm_batch()
    print("h_orgasm_batch mod tests passed", flush=True)
