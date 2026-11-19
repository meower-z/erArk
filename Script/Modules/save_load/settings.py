"""
save_load 的全局设置
====================
系统设置（System_Setting，不含本存档的难度与生殖方式）是全局的，存在游戏根目录的 settings.json，不随存档。
字体大小与 DPI 本来就在游戏根目录的 config.ini，也是全局的，不归本模块管。
install 把这个对象装到 cache.all_system_setting，读设置的代码照旧读那里。
kernel.Reset 的输出钩子在每次换 GameState（读档、新游戏、改时钟）时先把设置写进文件，再装一次，所以读档不改全局设置。
游戏退出走 os._exit，不跑 atexit；没在设置面板里改的设置，到下一次换 GameState 时才写进文件。
本模块不登记行动、事件或规则。
"""

import json
import os
from typing import Any

from Script.Config import character_config
from Script.Core import cache_control, game_path_config, game_type
from Script.Design import attr_calculation
from Script.Kernel import core

path: str = os.path.join(game_path_config.game_path, "settings.json")
""" 全局设置文件 """
_INT_KEYED = ("base_setting", "draw_setting", "character_text_version")
""" 键是整数的设置字典，JSON 里存成字符串键 """
_live: game_type.System_Setting | None = None
""" 装在缓存上的全局设置对象，第一次 install 时建 """
_saved: str | None = None
""" 装好时或最近一次写出时设置的文本，内容没变就不再写 """


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


def install(cache: game_type.Cache) -> None:
    """
    把全局设置装到缓存的 all_system_setting。
    第一次装时，以默认值为底，盖上 settings.json 的内容；还没有这个文件（或读不出）时，盖上缓存里此刻的设置，
    这样旧存档里的设置在第一次读档时成为全局设置。装好后到有设置改动为止，save 不写文件
    Keyword arguments:
    cache -- 游戏缓存
    """
    global _live, _saved
    if _live is None:
        _live = attr_calculation.get_system_setting_zero()
        try:
            with open(path, encoding="utf-8") as setting_file:
                data = json.load(setting_file)
        except (OSError, ValueError):
            data = _dump(cache.all_system_setting)
        _apply(_live, data)
        _saved = _text(_live)
    cache.all_system_setting = _live


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


def adopt(setting: game_type.System_Setting) -> None:
    """
    读档时交来存档里的系统设置：还没有 settings.json 时（第一次读入旧存档），存档的设置盖到全局设置上并写出；
    已有 settings.json 时不改全局设置
    Keyword arguments:
    setting -- 存档里的设置对象
    """
    if os.path.exists(path):
        return
    install(cache_control.cache)
    assert _live is not None
    _apply(_live, _dump(setting))
    save()


@core.output_hook(core.reset)
def reinstall(game: core.GameState) -> core.GameState:
    """
    kernel.Reset 的输出钩子：换了 GameState 之后先保存全局设置，再装到（可能已换掉的）缓存上
    Keyword arguments:
    game -- 新的 GameState
    Return arguments:
    GameState -- 原样交回
    """
    save()
    install(cache_control.cache)
    return game
