# -*- coding: UTF-8 -*-
"""
H绝顶批处理修复。

这个脚本通过mod系统替换高潮结算、人力发电显示和二段结算入口，
把一次检测周期内的多部位绝顶合并显示，同时保持原本的属性和发电结算。
"""
from collections import defaultdict
from contextlib import contextmanager


SECOND_BEHAVIOR_MODULE = "Script.Design.second_behavior"
POWER_MODULE = "Script.UI.Panel.manage_power_system_panel"

ORGASM_REPRESENTATIVE_TALK_LIMIT = 3
ORGASM_PART_PREFIX = {0: "s", 1: "b", 2: "c", 3: "p", 4: "v", 5: "a", 6: "u", 7: "w", 21: "m", 22: "f", 23: "h"}
ORGASM_PART_ID_BY_PREFIX = {prefix: part_id for part_id, prefix in ORGASM_PART_PREFIX.items()}
ORGASM_DEGREE_ID_TO_NAME = {0: "small", 1: "normal", 2: "strong", 3: "super"}
ORGASM_DEGREE_RANK = {"edge": -1, "small": 0, "normal": 1, "strong": 2, "super": 3}
ORGASM_PART_NAME_BY_PREFIX = {"b": "胸部", "c": "阴蒂", "v": "阴道", "a": "肛肠", "u": "尿道", "w": "子宫", "s": "皮肤", "m": "口喉", "f": "兽部", "h": "心理"}
ORGASM_DEGREE_DISPLAY_TEXT = {"edge": "绝顶寸止", "small": "小绝顶", "normal": "绝顶", "strong": "强绝顶", "super": "超强绝顶"}
HYPNOSIS_UNCONSCIOUS_FLAGS = {4, 5, 6, 7}

_ORGASM_BATCH_SETTLING_CHARACTER_IDS = set()
_POWER_BATCH_STACK = []


def _cache():
    """获取游戏缓存"""
    from Script.Core import cache_control

    return cache_control.cache


def _can_show_second_behavior(character_id: int) -> bool:
    """判断指定角色的二段表现是否可被玩家看到"""
    cache_obj = _cache()
    if character_id == 0:
        return True
    character_data = cache_obj.character_data[character_id]
    player_position = cache_obj.character_data[0].position
    if character_data.position == player_position:
        return True
    return getattr(character_data.behavior, "move_src", None) == player_position


@contextmanager
def _suppress_draw_when_needed(suppress: bool):
    """远处后台结算时临时压制二段效果里的直接界面交互"""
    if not suppress:
        yield
        return

    def silent_draw(self, *args, **kwargs):
        """静默丢弃绘制请求"""
        return None

    def silent_askfor_all(input_list, *args, **kwargs):
        """静默返回一个可使普通面板退出的选项"""
        if isinstance(input_list, (list, tuple)) and input_list:
            return input_list[-1]
        return ""

    def silent_askfor_int(input_data=None, *args, **kwargs):
        """静默返回一个可使普通面板退出的数字选项"""
        if isinstance(input_data, (list, tuple)) and input_data:
            return input_data[-1]
        if "default_int" in kwargs:
            return kwargs["default_int"]
        if args:
            return args[0]
        return 0

    def silent_askfor_str(input_data=None, *args, **kwargs):
        """静默返回空输入"""
        if isinstance(input_data, str):
            if "default_str" in kwargs:
                return kwargs["default_str"]
            if args:
                return args[0]
            return "19"
        if input_data is None:
            return "19"
        return ""

    def silent_askfor_wait(*args, **kwargs):
        """静默跳过等待输入"""
        return None

    def silent_output(*args, **kwargs):
        """静默丢弃直接输出请求"""
        return None

    patched_draw_methods = []
    try:
        from Script.UI.Moudle import draw
    except Exception:
        draw = None
    if draw is not None:
        patched_draw_classes = set()
        for draw_class in vars(draw).values():
            if not isinstance(draw_class, type) or draw_class in patched_draw_classes or "draw" not in draw_class.__dict__:
                continue
            patched_draw_classes.add(draw_class)
            patched_draw_methods.append((draw_class, draw_class.draw))
            draw_class.draw = silent_draw

    patched_flow_methods = []
    flow_patch_data = {
        "askfor_all": silent_askfor_all,
        "askfor_int": silent_askfor_int,
        "askfor_str": silent_askfor_str,
        "askfor_wait": silent_askfor_wait,
        "print_cmd": silent_output,
        "print_image_cmd": silent_output,
    }
    for module_name in ("flow_handle", "flow_handle_web"):
        try:
            module = __import__(f"Script.Core.{module_name}", fromlist=[module_name])
        except Exception:
            continue
        for func_name, silent_func in flow_patch_data.items():
            if not hasattr(module, func_name):
                continue
            patched_flow_methods.append((module, func_name, getattr(module, func_name)))
            setattr(module, func_name, silent_func)

    patched_output_methods = []
    output_patch_data = {
        "era_print": silent_output,
        "clear_screen": silent_output,
        "clear_screen_and_history": silent_output,
    }
    for module_name in ("io_init", "io_web"):
        try:
            module = __import__(f"Script.Core.{module_name}", fromlist=[module_name])
        except Exception:
            continue
        for func_name, silent_func in output_patch_data.items():
            if not hasattr(module, func_name):
                continue
            patched_output_methods.append((module, func_name, getattr(module, func_name)))
            setattr(module, func_name, silent_func)

    try:
        yield
    finally:
        for draw_class, original_draw in patched_draw_methods:
            draw_class.draw = original_draw
        for module, func_name, original_func in patched_flow_methods:
            setattr(module, func_name, original_func)
        for module, func_name, original_func in patched_output_methods:
            setattr(module, func_name, original_func)


class OrgasmBatch:
    """一次高潮检测周期内产生的二段行为集合"""

    def __init__(self):
        self.effect_behavior_ids = []
        self.effect_behavior_set = set()
        self.part_display_behavior = {}
        self.part_display_rank = {}
        self.plural_behavior_id = ""
        self.plural_orgasm_set = set()
        self.human_power_climax_degree = 0
        self.human_power_draw_flag = False

    def add_effect_behavior(self, second_behavior_id: str):
        """加入需要结算的二段行为"""
        if not second_behavior_id or second_behavior_id in self.effect_behavior_set:
            return
        self.effect_behavior_set.add(second_behavior_id)
        self.effect_behavior_ids.append(second_behavior_id)

    def add_part_orgasm(self, second_behavior_id: str):
        """加入部位绝顶，并记录该部位最高强度用于显示"""
        self.add_effect_behavior(second_behavior_id)
        parse_data = parse_orgasm_part_behavior(second_behavior_id)
        if parse_data is None:
            return
        part_id = parse_data[0]
        rank = parse_data[2]
        if part_id not in self.part_display_rank or rank > self.part_display_rank[part_id]:
            self.part_display_rank[part_id] = rank
            self.part_display_behavior[part_id] = second_behavior_id

    def add_plural_orgasm(self, second_behavior_id: str, orgasm_set: set):
        """加入多重绝顶行为"""
        self.plural_behavior_id = second_behavior_id
        self.plural_orgasm_set = orgasm_set.copy()
        self.add_effect_behavior(second_behavior_id)

    def all_behavior_ids(self) -> set:
        """返回本批次已经接管的二段行为id"""
        behavior_ids = set(self.effect_behavior_set)
        behavior_ids.update(self.part_display_behavior.values())
        if self.plural_behavior_id:
            behavior_ids.add(self.plural_behavior_id)
        return behavior_ids


def local_bugfix_is_orgasm_batch_settling(character_id: int) -> bool:
    """供其他本地修复判断指定角色是否处于绝顶批处理"""
    return character_id in _ORGASM_BATCH_SETTLING_CHARACTER_IDS


def parse_orgasm_part_behavior(second_behavior_id: str):
    """解析部位绝顶二段行为id"""
    if "_orgasm_" not in second_behavior_id:
        return None
    part_prefix, degree_name = second_behavior_id.split("_orgasm_", 1)
    if part_prefix not in ORGASM_PART_ID_BY_PREFIX or degree_name not in ORGASM_DEGREE_RANK:
        return None
    return ORGASM_PART_ID_BY_PREFIX[part_prefix], degree_name, ORGASM_DEGREE_RANK[degree_name]


def _get_ordered_orgasm_part_behaviors(orgasm_batch: OrgasmBatch) -> list:
    """按强度从高到低排列部位绝顶，同强度随机"""
    rank_to_behaviors = defaultdict(list)
    for part_id, second_behavior_id in orgasm_batch.part_display_behavior.items():
        rank_to_behaviors[orgasm_batch.part_display_rank[part_id]].append(second_behavior_id)

    ordered_behavior_list = []
    for rank in sorted(rank_to_behaviors.keys(), reverse=True):
        same_rank_behaviors = rank_to_behaviors[rank]
        random.shuffle(same_rank_behaviors)
        ordered_behavior_list.extend(same_rank_behaviors)
    return ordered_behavior_list


def _get_orgasm_part_name(part_prefix: str) -> str:
    """获取绝顶部位显示名"""
    return _(ORGASM_PART_NAME_BY_PREFIX.get(part_prefix, "通用"))


def _get_orgasm_degree_text(degree_name: str) -> str:
    """获取绝顶强度显示名"""
    return _(ORGASM_DEGREE_DISPLAY_TEXT.get(degree_name, "绝顶"))


def _get_part_orgasm_info_text(character_id: int, second_behavior_id: str, extra_blank_line: bool = True) -> str:
    """生成部位绝顶提示文本"""
    parse_data = parse_orgasm_part_behavior(second_behavior_id)
    if parse_data is None:
        return ""
    character_data = _cache().character_data[character_id]
    part_prefix, degree_name = second_behavior_id.split("_orgasm_", 1)
    line_end = "\n\n" if extra_blank_line else "\n"
    return "\n{0}{1}{2}{3}".format(character_data.name, _get_orgasm_part_name(part_prefix), _get_orgasm_degree_text(degree_name), line_end)


def _draw_compact_part_orgasm_info(character_id: int, second_behavior_id: str) -> str:
    """绘制紧凑间距的部位绝顶提示"""
    from Script.UI.Moudle import draw

    info_text = _get_part_orgasm_info_text(character_id, second_behavior_id, extra_blank_line=False)
    if not info_text:
        return info_text
    info_draw = draw.WaitDraw()
    info_draw.style = "gold_enrod"
    info_draw.text = info_text
    info_draw.draw()
    return info_text


def _handle_part_orgasm_second_talk(character_id: int, second_behavior_id: str):
    """播放部位绝顶口上，并把黄色提示与口上之间控制为一个空行"""
    from Script.Design import talk

    original_info_func = talk.second_behavior_info_text

    def compact_info_func(info_character_id: int, info_second_behavior_id: str):
        if info_character_id == character_id and info_second_behavior_id == second_behavior_id:
            return _draw_compact_part_orgasm_info(info_character_id, info_second_behavior_id)
        return original_info_func(info_character_id, info_second_behavior_id)

    talk.second_behavior_info_text = compact_info_func
    try:
        _handle_orgasm_batch_second_talk(character_id, second_behavior_id)
    finally:
        talk.second_behavior_info_text = original_info_func


def _should_pass_unconscious_gate_for_orgasm_second_talk(character_id: int) -> bool:
    """判断催眠绝顶二段口上是否需要跳过通用无意识门禁"""
    try:
        character_data = _cache().character_data.get(character_id)
        return getattr(getattr(character_data, "sp_flag", None), "unconscious_h", 0) in HYPNOSIS_UNCONSCIOUS_FLAGS
    except Exception:
        return False


def _handle_orgasm_batch_second_talk(character_id: int, second_behavior_id: str):
    """播放绝顶批处理二段口上，催眠状态下保留通用绝顶口上兜底"""
    from Script.Design import talk

    if not _should_pass_unconscious_gate_for_orgasm_second_talk(character_id):
        return talk.handle_second_talk(character_id, second_behavior_id)

    cache_obj = _cache()
    if getattr(cache_obj, "is_collection", False) and character_id:
        player_data = cache_obj.character_data.get(0)
        if player_data is None or character_id not in getattr(player_data, "collection_character", []):
            return

    calculated_premise_dict = {}
    now_talk_data, calculated_premise_dict = talk.handle_talk_sub(character_id, second_behavior_id, calculated_premise_dict, unconscious_pass_flag=True)
    talk_text, now_talk_id = talk.choice_talk_from_talk_data(now_talk_data, second_behavior_id)
    talk.handle_talk_draw(character_id, talk_text, now_talk_id, second_behavior_id)


def _handle_non_part_orgasm_second_talk(character_id: int, orgasm_batch: OrgasmBatch):
    """播放绝顶批次中非部位二段行为的口上"""
    character_data = _cache().character_data[character_id]
    for second_behavior_id in orgasm_batch.effect_behavior_ids:
        if second_behavior_id == orgasm_batch.plural_behavior_id:
            continue
        if parse_orgasm_part_behavior(second_behavior_id) is not None:
            continue
        if character_data.second_behavior.get(second_behavior_id, 0) == 0:
            continue
        _handle_orgasm_batch_second_talk(character_id, second_behavior_id)


def _draw_compact_orgasm_summary(character_id: int, second_behavior_ids: list):
    """把多个非代表部位绝顶压缩为一行显示"""
    if not second_behavior_ids:
        return

    from Script.Config import normal_config
    from Script.UI.Moudle import draw

    degree_to_part_names = defaultdict(list)
    degree_order = []
    for second_behavior_id in second_behavior_ids:
        parse_data = parse_orgasm_part_behavior(second_behavior_id)
        if parse_data is None:
            continue
        degree_name = parse_data[1]
        part_prefix = second_behavior_id.split("_orgasm_", 1)[0]
        if degree_name not in degree_to_part_names:
            degree_order.append(degree_name)
        degree_to_part_names[degree_name].append(_get_orgasm_part_name(part_prefix))

    summary_parts = []
    for degree_name in degree_order:
        part_names_text = "、".join(degree_to_part_names[degree_name])
        summary_parts.append("{0} {1}".format(part_names_text, _get_orgasm_degree_text(degree_name)))
    if not summary_parts:
        return

    character_data = _cache().character_data[character_id]
    info_draw = draw.WaitDraw()
    info_draw.style = "gold_enrod"
    info_draw.width = normal_config.config_normal.text_width
    info_draw.text = "\n{0} {1}\n".format(character_data.name, "，".join(summary_parts))
    info_draw.draw()


def _queue_second_behavior(character_id: int, orgasm_batch: OrgasmBatch, second_behavior_id: str, is_part_orgasm: bool = False):
    """用原版入口标记二段行为，并登记到批处理"""
    from Script.Design import second_behavior

    second_behavior.character_get_second_behavior(character_id, second_behavior_id)
    if is_part_orgasm:
        orgasm_batch.add_part_orgasm(second_behavior_id)
    else:
        orgasm_batch.add_effect_behavior(second_behavior_id)


def _remove_second_behavior_from_must_lists(character_data, second_behavior_id: str):
    """清理必须显示/必须结算列表中的批处理行为"""
    for list_name in ("must_settle_second_behavior_id_list", "must_show_second_behavior_id_list"):
        behavior_list = getattr(character_data, list_name, [])
        while second_behavior_id in behavior_list:
            behavior_list.remove(second_behavior_id)


def _clear_queued_second_behaviors(character_data, second_behavior_ids: set):
    """清理本批次已经显示和结算过的二段行为标记"""
    for second_behavior_id in second_behavior_ids:
        if second_behavior_id in character_data.second_behavior:
            character_data.second_behavior[second_behavior_id] = 0
        _remove_second_behavior_from_must_lists(character_data, second_behavior_id)


def _apply_second_behavior_effect(character_id: int, change_data, second_behavior_id: str):
    """静默执行二段行为效果"""
    if second_behavior_id not in game_config.config_behavior_effect_data:
        print(f"debug second_behavior_id = {second_behavior_id}没有找到对应的结算效果")
        return

    from Script.Design import settle_behavior

    for effect_id in game_config.config_behavior_effect_data[second_behavior_id]:
        if isinstance(effect_id, str) and "CVE" in effect_id:
            effect_all_value_list = effect_id.split("_")[1:]
            settle_behavior.handle_comprehensive_value_effect(character_id, effect_all_value_list, change_data)
        else:
            if effect_id not in constant.settle_second_behavior_effect_data:
                print(f"debug second_behavior_id = {second_behavior_id}，effect_id = {effect_id}没有找到对应的结算效果")
                continue
            constant.settle_second_behavior_effect_data[effect_id](character_id, change_data)


def _push_power_batch(plural_climax_degree: int, character_id: int, draw_flag: bool):
    """开启一次多重绝顶人力发电显示合并"""
    power_batch = {
        "plural_climax_degree": plural_climax_degree,
        "character_id": character_id,
        "draw_flag": draw_flag,
        "amount": 0.0,
    }
    _POWER_BATCH_STACK.append(power_batch)
    return power_batch


def _finish_power_batch(power_batch):
    """结束人力发电显示合并，并输出原版多重绝顶发电文本"""
    if not _POWER_BATCH_STACK or _POWER_BATCH_STACK[-1] is not power_batch:
        return
    _POWER_BATCH_STACK.pop()
    if not power_batch["draw_flag"] or power_batch["amount"] <= 0:
        return
    _draw_plural_human_power_text(power_batch["plural_climax_degree"], power_batch["character_id"], power_batch["amount"])


def _draw_plural_human_power_text(climax_degree: int, character_id: int, power_amount: float):
    """使用原版多重绝顶人力发电文本显示合计电量"""
    from Script.Config import normal_config
    from Script.UI.Moudle import draw

    character_data = _cache().character_data[character_id]
    draw_text = draw.WaitDraw()
    draw_text.width = normal_config.config_normal.text_width
    draw_text.text = _("\n在{0}{1}重绝顶的同时，").format(character_data.name, climax_degree - 3)
    draw_text.text += _("性爱发电装置产生了 {0:.1f} 单位电量\n").format(power_amount)
    draw_text.draw()


def _flush_orgasm_batch(character_id: int, change_data, orgasm_batch: OrgasmBatch):
    """显示并结算一次绝顶批次"""
    if not orgasm_batch.effect_behavior_ids:
        return

    from Script.Design import talk
    from Script.UI.Panel.manage_power_system_panel import store_power_by_human_power

    cache_obj = _cache()
    character_data = cache_obj.character_data[character_id]
    show_second_behavior = _can_show_second_behavior(character_id)
    _ORGASM_BATCH_SETTLING_CHARACTER_IDS.add(character_id)
    power_batch = None
    try:
        if orgasm_batch.plural_behavior_id:
            character_data.h_state.plural_orgasm_set = orgasm_batch.plural_orgasm_set.copy()
            if show_second_behavior:
                _handle_orgasm_batch_second_talk(character_id, orgasm_batch.plural_behavior_id)

        ordered_part_behaviors = _get_ordered_orgasm_part_behaviors(orgasm_batch)
        representative_part_behaviors = ordered_part_behaviors
        compact_part_behaviors = []
        if orgasm_batch.plural_behavior_id:
            representative_part_behaviors = ordered_part_behaviors[:ORGASM_REPRESENTATIVE_TALK_LIMIT]
            compact_part_behaviors = ordered_part_behaviors[ORGASM_REPRESENTATIVE_TALK_LIMIT:]
        if show_second_behavior:
            for second_behavior_id in representative_part_behaviors:
                _handle_part_orgasm_second_talk(character_id, second_behavior_id)
            _draw_compact_orgasm_summary(character_id, compact_part_behaviors)
            _handle_non_part_orgasm_second_talk(character_id, orgasm_batch)

        if orgasm_batch.human_power_climax_degree:
            human_power_draw_flag = orgasm_batch.human_power_draw_flag and show_second_behavior
            power_batch = _push_power_batch(orgasm_batch.human_power_climax_degree, character_id, human_power_draw_flag)
            with _suppress_draw_when_needed(not show_second_behavior):
                store_power_by_human_power(orgasm_batch.human_power_climax_degree, character_id, human_power_draw_flag)

        with _suppress_draw_when_needed(not show_second_behavior):
            for second_behavior_id, behavior_data in list(character_data.second_behavior.items()):
                if behavior_data != 0 and second_behavior_id in orgasm_batch.effect_behavior_set:
                    _apply_second_behavior_effect(character_id, change_data, second_behavior_id)

        _clear_queued_second_behaviors(character_data, orgasm_batch.all_behavior_ids())
    finally:
        if power_batch is not None:
            _finish_power_batch(power_batch)
        _ORGASM_BATCH_SETTLING_CHARACTER_IDS.discard(character_id)


def patched_check_second_effect(character_id: int, change_data, pl_to_npc: bool = False):
    """修复NPC高潮结算后仍使用旧高潮过滤列表的问题"""
    from Script.Design import second_behavior

    mark_list = []
    character_data = _cache().character_data[character_id]
    for second_behavior_id in character_data.second_behavior:
        if "mark" in second_behavior_id:
            mark_list.append(second_behavior_id)

    if character_id == 0:
        character_data = _cache().character_data[0]
        second_behavior.orgasm_judge(character_id, change_data)
        second_behavior.item_effect(character_id)
        second_behavior.second_behavior_effect(character_id, change_data)
        change_data.target_change.setdefault(character_data.target_character_id, game_type.TargetChange())
        target_change = change_data.target_change[character_data.target_character_id]
        second_behavior.mark_effect(character_data.target_character_id, target_change)
        second_behavior.second_behavior_effect(character_data.target_character_id, target_change, mark_list)

    if character_id != 0:
        second_behavior.judge_character_first_meet(character_id)
        second_behavior.insert_position_effect(character_id, change_data)
        second_behavior.item_effect(character_id)
        second_behavior.second_behavior_effect(character_id, change_data)
        second_behavior.orgasm_judge(character_id, change_data)
        second_behavior.second_behavior_effect(character_id, change_data)
        second_behavior.mark_effect(character_id, change_data)
        second_behavior.second_behavior_effect(character_id, change_data, mark_list)


def patched_orgasm_settle(
    character_id: int,
    change_data,
    normal_orgasm_dict: dict = None,
    extra_orgasm_dict: dict = None,
    un_count_orgasm_dict: dict = None,
):
    """批量显示和结算NPC部位绝顶"""
    from Script.Design import handle_premise, second_behavior
    from Script.Settle.common_default import base_chara_experience_common_settle
    from Script.UI.Panel import achievement_panel

    normal_orgasm_dict = normal_orgasm_dict or {}
    extra_orgasm_dict = extra_orgasm_dict or {}
    un_count_orgasm_dict = un_count_orgasm_dict or {}

    cache_obj = _cache()
    character_data = cache_obj.character_data[character_id]
    show_second_behavior = _can_show_second_behavior(character_id)
    orgasm_batch = OrgasmBatch()
    part_count = 0
    tem_orgasm_set = set()

    for orgasm in ORGASM_PART_PREFIX:
        if orgasm == 3:
            continue

        pre_data = character_data.h_state.orgasm_level[orgasm]
        normal_orgasm_data = normal_orgasm_dict.get(orgasm, 0)
        extra_orgasm_data = extra_orgasm_dict.get(orgasm, 0)
        un_count_orgasm_data = un_count_orgasm_dict.get(orgasm, 0)

        if extra_orgasm_data > 0:
            now_data = pre_data + extra_orgasm_data
        else:
            now_data = pre_data + normal_orgasm_data

        if normal_orgasm_data > 0 or extra_orgasm_data > 0 or un_count_orgasm_data > 0:
            climax_count = normal_orgasm_data + un_count_orgasm_data
            character_data.h_state.orgasm_level[orgasm] = now_data

            if handle_premise.handle_unconscious_flag_3(character_id):
                character_data.h_state.time_stop_orgasm_count.setdefault(orgasm, 0)
                character_data.h_state.time_stop_orgasm_count[orgasm] += climax_count
                continue

            if handle_premise.handle_self_orgasm_edge(character_id):
                with _suppress_draw_when_needed(not show_second_behavior):
                    orgasm_edge_success_flag = second_behavior.judge_orgasm_edge_success(character_id)
                if not orgasm_edge_success_flag:
                    character_data.h_state.orgasm_edge = 3
                    _flush_orgasm_batch(character_id, change_data, orgasm_batch)
                    return
                character_data.h_state.orgasm_edge_count.setdefault(orgasm, 0)
                character_data.h_state.orgasm_edge_count[orgasm] += climax_count
                second_behavior_id = f"{ORGASM_PART_PREFIX[orgasm]}_orgasm_edge"
                _queue_second_behavior(character_id, orgasm_batch, second_behavior_id, is_part_orgasm=True)
                continue

            if handle_premise.handle_group_sex_mode_on(character_id):
                cache_obj.achievement.group_sex_record.setdefault(2, [])
                if character_id not in cache_obj.achievement.group_sex_record[2]:
                    cache_obj.achievement.group_sex_record[2].append(character_id)
            elif handle_premise.handle_hidden_sex_mode_ge_1(character_id):
                cache_obj.achievement.hidden_sex_record.setdefault(4, 0)
                cache_obj.achievement.hidden_sex_record[4] += 1
            elif handle_premise.handle_exhibitionism_sex_mode_ge_1(character_id):
                cache_obj.achievement.exhibitionism_sex_record.setdefault(4, 0)
                cache_obj.achievement.exhibitionism_sex_record[4] += 1

            if handle_premise.handle_unconscious_flag_1(character_id):
                cache_obj.achievement.sleep_sex_record.setdefault(3, 0)
                cache_obj.achievement.sleep_sex_record[3] += 1

            part_count += 1
            tem_orgasm_set.add(orgasm)
            for climax_index in range(climax_count):
                now_degree = second_behavior.judge_orgasm_degree(now_data)
                if now_degree >= 2:
                    if orgasm <= 7:
                        ability_id = orgasm
                    else:
                        ability_id = orgasm + 79
                    if character_data.ability[ability_id] < 3:
                        now_degree = 1
                second_behavior_id = f"{ORGASM_PART_PREFIX[orgasm]}_orgasm_{ORGASM_DEGREE_ID_TO_NAME[now_degree]}"
                _queue_second_behavior(character_id, orgasm_batch, second_behavior_id, is_part_orgasm=True)

            if handle_premise.handle_self_orgasm_edge_relase_or_time_stop_orgasm_relase(character_id) and climax_count >= 3:
                now_degree = 3
                if orgasm <= 7:
                    ability_id = orgasm
                else:
                    ability_id = orgasm + 79
                if character_data.ability[ability_id] < 6:
                    now_degree = 2
                second_behavior_id = f"{ORGASM_PART_PREFIX[orgasm]}_orgasm_{ORGASM_DEGREE_ID_TO_NAME[now_degree]}"
                _queue_second_behavior(character_id, orgasm_batch, second_behavior_id, is_part_orgasm=True)

            if orgasm == 1 and handle_premise.handle_milk_ge_80(character_id):
                _queue_second_behavior(character_id, orgasm_batch, "b_orgasm_to_milk")
            if orgasm == 6 and handle_premise.handle_urinate_ge_80(character_id):
                _queue_second_behavior(character_id, orgasm_batch, "u_orgasm_to_pee")
            if extra_orgasm_data > 0:
                _queue_second_behavior(character_id, orgasm_batch, "extra_orgasm")

    if part_count >= 1 and character_data.h_state.shoot_position_body in [2, 15]:
        base_chara_experience_common_settle(character_id, 111, change_data=change_data)

    if part_count >= 2:
        second_behavior_id = f"plural_orgasm_{part_count}"
        _queue_second_behavior(character_id, orgasm_batch, second_behavior_id)
        orgasm_batch.add_plural_orgasm(second_behavior_id, tem_orgasm_set)

        with _suppress_draw_when_needed(not show_second_behavior):
            achievement_panel.achievement_flow(_("绝顶"), 1221)
            if part_count >= 6:
                achievement_panel.achievement_flow(_("绝顶"), 1222)
            if part_count >= 10:
                achievement_panel.achievement_flow(_("绝顶"), 1223)

        if handle_premise.handle_in_human_power_room(character_id):
            orgasm_batch.human_power_climax_degree = part_count + 3
            orgasm_batch.human_power_draw_flag = bool(handle_premise.handle_in_player_scene(character_id))

    _flush_orgasm_batch(character_id, change_data, orgasm_batch)


def patched_store_power_by_human_power(climax_degree: int, character_id: int, draw_flag: bool = True) -> float:
    """在多重绝顶批处理中合并人力发电显示，不改变原计算"""
    if not _POWER_BATCH_STACK:
        return call_original(POWER_MODULE, "store_power_by_human_power", climax_degree, character_id, draw_flag)

    power_batch = _POWER_BATCH_STACK[-1]
    power_amount = call_original(POWER_MODULE, "store_power_by_human_power", climax_degree, character_id, False)
    if draw_flag:
        power_batch["draw_flag"] = True
    power_batch["amount"] += power_amount
    return power_amount
