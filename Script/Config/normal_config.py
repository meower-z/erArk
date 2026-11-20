"""
通用配置与游戏版本号的读取，以及玩家设置的写入
通用配置先取 config.ini 的值，再用 config.local.ini 里的同名键覆盖。
write_local_config 只写 config.local.ini。
"""

import os
import json
import configparser
import sys
from Script.Core import game_type, game_path_config

config_normal: game_type.NormalConfig = game_type.NormalConfig()
""" 游戏通用配置数据 """
system_setting: game_type.System_Setting = game_type.System_Setting()
""" 全局的系统设置与玩家的面板选择（settings.json），由 save_load.settings 装好与写出 """
package_path = os.path.join("package.json")
DEFAULTS_ONLY_ENV = "ERARK_CONFIG_DEFAULTS_ONLY"
""" 环境变量名。这个变量非空时，init_normal_config 只读 config.ini。 """


def get_config_ini_path() -> str:
    """获取 config.ini 的绝对路径"""
    candidate_paths = []
    if getattr(sys, "frozen", False):
        candidate_paths.append(
            os.path.join(os.path.dirname(sys.executable), "config.ini")
        )
    candidate_paths.append(
        os.path.join(game_path_config.game_path, "config.ini")
    )
    candidate_paths.append(os.path.abspath("config.ini"))
    for candidate_path in candidate_paths:
        if os.path.exists(candidate_path):
            return candidate_path
    return candidate_paths[0]


def get_config_local_ini_path() -> str:
    """在 get_config_ini_path 所选 config.ini 的目录下取 config.local.ini 的绝对路径"""
    return os.path.join(
        os.path.dirname(get_config_ini_path()), "config.local.ini"
    )


def write_local_config(values: dict[str, str]) -> None:
    """
    把 values 合并进 config.local.ini 的 game 段并写回文件
    文件里已有的其他键保留。
    文件和 game 段不存在时都会新建。
    Keyword arguments:
    values -- 键名对应值文本的字典
    Return arguments:
    无
    """
    local_path = get_config_local_ini_path()
    ini_config = configparser.ConfigParser()
    ini_config.read(local_path, encoding="utf8")
    ini_config.read_dict({"game": values})
    with open(local_path, "w", encoding="utf8") as config_file:
        ini_config.write(config_file)


def init_normal_config() -> None:
    """
    初始化游戏通用配置数据和版本号
    先读 config.ini 的 game 段，再读 config.local.ini 的 game 段。
    两份文件都有的键取 config.local.ini 的值。
    DEFAULTS_ONLY_ENV 指定的环境变量非空时，不读 config.local.ini。
    能转成 int 的值存为 int，其余的值存为文本。
    版本号取自 package.json 的 version，没有这个文件时为 "Orgin"。
    Keyword arguments:
    无
    Return arguments:
    无
    """
    ini_paths = [get_config_ini_path()]
    if not os.environ.get(DEFAULTS_ONLY_ENV):
        ini_paths.append(get_config_local_ini_path())
    ini_config = configparser.ConfigParser()
    ini_config.read(ini_paths, encoding="utf8")
    ini_data = ini_config["game"]
    for k in ini_data.keys():
        try:
            config_normal.__dict__[k] = int(ini_data[k])
        except BaseException:
            config_normal.__dict__[k] = ini_data[k]
    if os.path.exists(package_path):
        with open(package_path, encoding="utf-8") as package_file:
            version_data = json.load(package_file)
            config_normal.verson = version_data["version"]
    else:
        config_normal.verson = "Orgin"
