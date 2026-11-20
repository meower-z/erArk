"""
save_load 的全局设置
====================
系统设置（System_Setting，不含本存档的难度与生殖方式）是全局的，存在游戏根目录的 settings.json，不随存档。
玩家在面板上要长期保留的选择（指令过滤、场景面板的子面板开关、做饭的模式与份数）也是它的字段。
字体大小与 DPI 本来就在游戏根目录的 config.ini，也是全局的，不归本模块管。
install 把这个对象装到 normal_config.system_setting，读设置的代码读那里。
kernel.Reset 的输出钩子在每次换 GameState（读档、新游戏、改时钟）时先把设置写进文件，再装一次。
存档里的设置与面板选择什么时候成为全局的，见 adopt。
游戏退出走 os._exit，不跑 atexit；没在设置面板里改的设置，到下一次换 GameState 时才写进文件。
本模块不登记行动、事件或规则。
"""

import json
import os
from typing import Any

from Script.Config import character_config, normal_config
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
_live: game_type.System_Setting | None = None
""" 装好的全局设置对象，第一次 install 时建 """
_saved: str | None = None
""" 装好时或最近一次写出时设置的文本，内容没变就不再写 """
_has_preferences = False
""" 全局设置里已有玩家的面板选择：装好时 settings.json 里有它们，或已从存档收下过 """


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


def _text(setting: game_type.System_Setting) -> str:
    """
    设置对象写进 settings.json 的文本。口上版本只写角色模板的剧情编号：本存档女儿的id随存档，读档时补上
    Keyword arguments:
    setting -- 设置对象
    Return arguments:
    str -- JSON 文本
    """
    data = _dump(setting)
    data["character_text_version"] = {
        k: v
        for k, v in data["character_text_version"].items()
        if int(k) in character_config.character_tem_list
    }
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True)


def install() -> None:
    """
    把全局设置装到 normal_config.system_setting。
    第一次装时，以默认值为底，盖上 settings.json 的内容；还没有这个文件（或读不出）时，盖上 normal_config 上此刻的设置。
    装好后到有设置改动为止，save 不写文件
    """
    global _live, _saved, _has_preferences
    if _live is None:
        _live = attr_calculation.get_system_setting_zero()
        try:
            with open(path, encoding="utf-8") as setting_file:
                data = json.load(setting_file)
            _has_preferences = PREFERENCES[0] in data
        except (OSError, ValueError):
            data = _dump(normal_config.system_setting)
            _has_preferences = False
        _apply(_live, data)
        _saved = _text(_live)
    normal_config.system_setting = _live


def save() -> None:
    """全局设置写进 settings.json；还没装过，或与装好时、上次写出时相同时不写"""
    global _saved
    if _live is None:
        return
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
