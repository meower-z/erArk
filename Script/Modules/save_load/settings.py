"""
save_load 的全局设置
====================
系统设置（System_Setting，不含本存档的难度与生殖方式）与文本生成 AI 设置（Ai_Setting）都是全局的，
存在游戏根目录的 settings.json，不随存档。
玩家在面板上要长期保留的选择（指令过滤、场景面板的子面板开关、做饭的模式与份数）是 System_Setting 的字段。
文本生成 AI 设置在有非默认改动或文件已有 "ai_setting" 段时写入 settings.json 的 "ai_setting" 键。
未改动的默认 AI 设置（含读档补齐的 0 值选项）不写入文件。
其中的 API 密钥随 AI 设置写进 settings.json，不进入存档。
字体大小与 DPI 存在游戏根目录的 config.ini，也是全局的，不归本模块管。
install 把这两个全局对象装到 normal_config.system_setting 与 normal_config.ai_setting。
settings.json 已有 "ai_setting" 段时，install 同时把缺失的 AI 选项补为 0。读设置的代码从这两个属性读取。
kernel.Reset 的输出钩子在每次换 GameState（读档、新游戏、改时钟）时先把设置写进文件，再装一次。
旧版本游戏的存档里的系统设置与面板选择何时成为全局设置，见 adopt。
全局 AI 设置仍为未改动的默认值且文件还没有 "ai_setting" 段时，adopt_ai 从旧版本游戏的存档里准备一份 AI 设置。
对未改动的默认 AI 设置补齐 0 值选项时，adopt_ai 返回 0，读档不弹出更新提示。
读档的 Reset 换掉内核状态后，kernel_state._reset 调用 commit_pending_ai 使其生效并按需写盘。
若 Reset 未换掉内核状态，它调用 drop_pending_ai 丢弃暂存的 AI 设置。
当 settings.json 已有 "ai_setting" 段、玩家改过 AI 设置，或已收下含非默认值的存档 AI 设置时，
后续读档不覆盖全局 AI 设置。
游戏退出走 os._exit，不跑 atexit。没在设置面板里改的设置，到下一次存档或换 GameState 时写进文件。
本模块不登记行动、事件或规则。
"""

import copy
import json
import os
from typing import Any

from Script.Config import character_config, game_config, normal_config
from Script.Core import game_path_config, game_type
from Script.Design import attr_calculation
from Script.Kernel import core

path: str = os.path.join(game_path_config.game_path, "settings.json")
""" 全局设置文件 """
_INT_KEYED = (
    "base_setting",
    "draw_setting",
    "character_text_version",
    "instruct_type_filter",
    "instruct_sex_type_filter",
    "makefood_cook_mode",
    "makefood_make_count",
)
""" 键是整数的设置字典，JSON 里存成字符串键 """
PREFERENCES = (
    "instruct_type_filter",
    "instruct_sex_type_filter",
    "instruct_index_filter",
    "scene_panel_show",
    "makefood_cook_mode",
    "makefood_make_count",
)
""" 玩家的面板选择：旧版本的游戏把它们存在存档里，读这样的存档时 adopt 收下一次 """
_AI_INT_KEYED = ("ai_chat_setting", "send_data_flags")
""" Ai_Setting 里键是整数的字典字段，JSON 里存成字符串键 """
_AI_SCALARS = (
    "now_ai_chat_model",
    "now_ai_chat_base_url",
    "ai_chat_translator_setting",
)
""" Ai_Setting 里直接按原值读写到 JSON 的标量字段名 """
_live: game_type.System_Setting | None = None
""" 装好的全局设置对象，第一次 install 时建 """
_live_ai = game_type.Ai_Setting()
""" 装好的全局 AI 设置对象，install 重建 _live 时一并新建 """
_saved: str | None = None
""" 装好时或最近一次写出时设置的文本，内容没变就不再写 """
_has_preferences = False
""" 全局设置里已有玩家的面板选择：装好时 settings.json 里有它们，或已从存档收下过 """
_has_ai = False
""" 全局 AI 设置已归属本地：装好时 settings.json 有 "ai_setting" 键，或 save 时 _owns_ai() 为真 """
_pending_ai: game_type.Ai_Setting | None = None
""" 读档由 adopt_ai 准备的待生效 AI 设置，由 kernel_state._reset 在换态后提交或未换态时丢弃 """


def _dump(setting: game_type.System_Setting) -> dict[str, Any]:
    """
    设置对象换成可写成 JSON 的字典
    Keyword arguments:
    setting -- 设置对象
    Return arguments:
    dict -- 设置的字典
    """
    data: dict[str, Any] = {
        name: {str(k): v for k, v in getattr(setting, name).items()}
        for name in _INT_KEYED
    }
    data["line_before_main_update"] = setting.line_before_main_update
    data["value_draw"] = dict(setting.value_draw)
    data["instruct_index_filter"] = dict(setting.instruct_index_filter)
    data["scene_panel_show"] = list(setting.scene_panel_show)
    return data


def _apply(setting: game_type.System_Setting, data: dict[str, Any]) -> None:
    """
    把字典里有的设置写到设置对象上，没有的保持原值
    Keyword arguments:
    setting -- 设置对象
    data -- _dump 的字典或其中一部分
    """
    for name in _INT_KEYED:
        getattr(setting, name).update(
            {int(k): v for k, v in data.get(name, {}).items()}
        )
    setting.line_before_main_update = data.get(
        "line_before_main_update", setting.line_before_main_update
    )
    setting.value_draw.update(data.get("value_draw", {}))
    setting.instruct_index_filter.update(data.get("instruct_index_filter", {}))
    setting.scene_panel_show = list(
        data.get("scene_panel_show", setting.scene_panel_show)
    )


def _dump_ai(ai: game_type.Ai_Setting) -> dict[str, Any]:
    """
    把 AI 设置对象转为可写成 JSON 的字典。整数键字典转为字符串键。字典与列表字段另做拷贝。
    Keyword arguments:
    ai -- AI 设置对象
    Return arguments:
    dict -- 可序列化为 JSON 的 AI 设置字典
    """
    data: dict[str, Any] = {
        name: {str(k): v for k, v in getattr(ai, name).items()}
        for name in _AI_INT_KEYED
    }
    data.update({name: getattr(ai, name) for name in _AI_SCALARS})
    data["ai_chat_api_key"] = dict(ai.ai_chat_api_key)
    data["now_ai_chat_proxy"] = list(ai.now_ai_chat_proxy)
    return data


def _apply_ai(ai: game_type.Ai_Setting, data: dict[str, Any]) -> None:
    """
    把字典里属于 Ai_Setting 的字段写到 AI 设置对象上。字典里没有的字段保持原值。不属于 Ai_Setting 的键不处理。
    Keyword arguments:
    ai -- AI 设置对象
    data -- _dump_ai 的字典、其中一部分或对象的属性字典
    """
    for name in _AI_INT_KEYED:
        getattr(ai, name).update(
            {int(k): v for k, v in data.get(name, {}).items()}
        )
    for name in _AI_SCALARS:
        setattr(ai, name, data.get(name, getattr(ai, name)))
    ai.ai_chat_api_key.update(data.get("ai_chat_api_key", {}))
    ai.now_ai_chat_proxy = list(
        data.get("now_ai_chat_proxy", ai.now_ai_chat_proxy)
    )


def _is_owned_ai(ai: game_type.Ai_Setting) -> bool:
    """
    判断一份 AI 设置是否偏离默认值（忽略 ai_chat_setting 中值为 0 的项）
    Keyword arguments:
    ai -- 待判断的 AI 设置对象
    Return arguments:
    bool -- 含非默认设置时为 True，否则为 False
    """
    data = _dump_ai(ai)
    chosen = {k: v for k, v in data["ai_chat_setting"].items() if v != 0}
    data["ai_chat_setting"] = chosen
    return data != _dump_ai(game_type.Ai_Setting())


def _owns_ai() -> bool:
    """
    判断全局 AI 设置是否已由本地持有（_has_ai 为真，或 _live_ai 偏离默认值）
    Return arguments:
    bool -- 全局 AI 设置已由本地持有时为 True
    """
    return _has_ai or _is_owned_ai(_live_ai)


def _fill_ai(ai: game_type.Ai_Setting) -> int:
    """
    把 game_config.config_ai_chat_setting 里缺失的选项编号以 0 原地补进 ai.ai_chat_setting
    Keyword arguments:
    ai -- 待补全的 AI 设置对象
    Return arguments:
    int -- 补全的选项数
    """
    missing = [
        cid
        for cid in game_config.config_ai_chat_setting
        if cid not in ai.ai_chat_setting
    ]
    ai.ai_chat_setting.update(dict.fromkeys(missing, 0))
    return len(missing)


def _text(setting: game_type.System_Setting) -> str:
    """
    把系统设置对象合成写进 settings.json 的文本。仅在 _owns_ai() 为真时把 _live_ai 写入 "ai_setting" 键。
    口上版本只写角色模板的剧情编号：本存档女儿的id随存档，读档时补上
    Keyword arguments:
    setting -- 系统设置对象
    Return arguments:
    str -- JSON 文本
    """
    data = _dump(setting)
    if _owns_ai():
        data["ai_setting"] = _dump_ai(_live_ai)
    data["character_text_version"] = {
        k: v
        for k, v in data["character_text_version"].items()
        if int(k) in character_config.character_tem_list
    }
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True)


def install() -> None:
    """
    把全局设置装到 normal_config.system_setting 与 normal_config.ai_setting。
    第一次装时（或 _live 为 None 时），函数以默认值为底，盖上 settings.json 的内容。
    文件有 "ai_setting" 段时，函数同时把缺失的 AI 选项补为 0，随后记录用于对比的设置文本。
    文件不存在或读不出时，函数取 normal_config 上此刻的两个设置对象的内容，不补全未改动的默认 AI 选项。
    装好后，在设置发生改动之前，save 不写文件。
    """
    global _live, _live_ai, _saved, _has_preferences, _has_ai
    if _live is None:
        _live = attr_calculation.get_system_setting_zero()
        _live_ai = game_type.Ai_Setting()
        try:
            with open(path, encoding="utf-8") as setting_file:
                data = json.load(setting_file)
            _has_preferences = PREFERENCES[0] in data
            _has_ai = "ai_setting" in data
        except (OSError, ValueError):
            data = _dump(normal_config.system_setting)
            data["ai_setting"] = _dump_ai(normal_config.ai_setting)
            _has_preferences = False
            _has_ai = False
        _apply(_live, data)
        _apply_ai(_live_ai, data.get("ai_setting", {}))
        if _has_ai:
            _fill_ai(_live_ai)
        _saved = _text(_live)
    normal_config.system_setting = _live
    normal_config.ai_setting = _live_ai


def save() -> None:
    """全局设置写进 settings.json；还没装过，或与装好时、上次写出时相同时不写"""
    global _saved, _has_ai
    if _live is None:
        return
    _has_ai = _owns_ai()
    text = _text(_live)
    if text == _saved:
        return
    with open(path, "w", encoding="utf-8") as setting_file:
        setting_file.write(text)
    _saved = text


def adopt(setting: object | None, preferences: dict[str, Any]) -> None:
    """
    读档时交来存档里的系统设置与玩家的面板选择（旧版本的游戏把面板选择存在存档里）。
    还没有 settings.json 时（第一次读入旧存档），存档的设置盖到全局设置上；
    全局设置里还没有面板选择、存档里有时，收下存档里的面板选择。收下一次之后，读档不再改面板选择
    Keyword arguments:
    setting -- 存档里的设置对象，存档里没有时为 None
    preferences -- 存档里的面板选择，PREFERENCES 里的名字到值，没有的不给
    """
    global _has_preferences
    fresh = not os.path.exists(path)
    install()
    assert _live is not None
    if fresh and setting is not None:
        _apply(_live, vars(setting))
    if preferences and not _has_preferences:
        _apply(_live, preferences)
        _has_preferences = True
    save()


def adopt_ai(ai: object | None) -> int:
    """
    读档时准备一份待生效的 AI 设置副本并暂存到 _pending_ai，不修改 _live_ai 也不写文件。
    函数先调用 install 确保全局设置已装好。当 ai 不为 None 且 _owns_ai() 为假时，函数以新的默认 Ai_Setting
    为底写入 ai 的字段，否则深拷贝 _live_ai。随后函数调用 _fill_ai 补齐缺失选项并存入 _pending_ai。
    仅在 _has_ai 为真或副本偏离默认值时返回补全的选项数，否则返回 0（使未改动默认设置的补全保持静默）。
    Keyword arguments:
    ai -- 存档里的 AI 设置对象，存档里没有时为 None
    Return arguments:
    int -- 需提示给玩家的补全选项数（未改动默认设置时为 0）
    """
    global _pending_ai
    install()
    if ai is not None and not _owns_ai():
        pending = game_type.Ai_Setting()
        _apply_ai(pending, vars(ai))
    else:
        pending = copy.deepcopy(_live_ai)
    filled = _fill_ai(pending)
    _pending_ai = pending
    return filled if _has_ai or _is_owned_ai(pending) else 0


def commit_pending_ai() -> None:
    """将 _pending_ai 的字段写回 _live_ai 并清空，随后调用 save 与 install（无待生效设置时直接返回）"""
    global _pending_ai
    if _pending_ai is None:
        return
    vars(_live_ai).update(vars(_pending_ai))
    _pending_ai = None
    save()
    install()


def drop_pending_ai() -> None:
    """丢弃读档期间暂存在 _pending_ai 的待生效 AI 设置"""
    global _pending_ai
    _pending_ai = None


@core.output_hook(core.reset)
def reinstall(game: core.GameState) -> core.GameState:
    """
    kernel.Reset 的输出钩子：换了 GameState 之后先保存全局设置，再装一次（第一次换 GameState 时建全局设置）
    Keyword arguments:
    game -- 新的 GameState
    Return arguments:
    GameState -- 原样交回
    """
    save()
    install()
    return game
