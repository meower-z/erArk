#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
近真实游戏内进程引导（near-real-game harness）

按 game.py 的初始化顺序，在当前 Python 进程内完成：初始化缓存、载入配置、
通过真实 Script.Core.mod_manager.init_mod_system() 全量加载启用 mod、载入角色
人物卡与地图、注册结算/状态机/指令等。加载后，被 mod 替换的 Script 函数即为
mod 版本本体（例如 Script.Design.second_behavior.orgasm_settle 就是批处理修复的实现），
因此后续对这些函数的调用是"未 mock 的真实 Script 模块 + 真实配置数据"上的行为验证。

这与 design.md 中"near-real-game harness"的定义一致，用于承载对成本较高的
群交/H 流程之外、可通过真实缓存与结算入口直接驱动的 mod 不变量断言。

用法：
    from mod.tests.bdd.near_real_boot import boot_game_once
    ctx = boot_game_once()          # 进程内仅需一次
    cache = ctx.cache
"""

import os
import sys
import types
from dataclasses import dataclass
from typing import Optional

# 仓库根目录（mod/tests/bdd/ 向上三级）
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

_BOOTED: Optional["BootContext"] = None


@dataclass
class BootContext:
    """
    引导上下文

    功能描述：持有引导后常用的模块与缓存引用，供场景直接使用。
    """
    cache: object
    constant: types.ModuleType
    game_type: types.ModuleType
    mod_success: bool


def boot_game_once(enable_debug: bool = True) -> BootContext:
    """
    在当前进程内完成一次近真实游戏初始化（幂等）

    参数:
    enable_debug (bool): 是否置 cache.debug_mode=True（部分前提/结算走 debug 分支）

    返回值类型：BootContext
    功能描述：镜像 game.py 的初始化顺序（去掉 Web 服务器与 GUI 启动）。多次调用
    只初始化一次。必须在仓库根目录布局下、且已 python buildconfig.py 生成数据后运行。
    """
    global _BOOTED
    if _BOOTED is not None:
        if enable_debug:
            _BOOTED.cache.debug_mode = True
        return _BOOTED

    cwd = os.getcwd()
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    os.chdir(REPO_ROOT)
    try:
        import auto_build_config  # noqa: F401  # 触发与 game.py 一致的构建校验
        from Script.Config import normal_config
        from Script.Core import game_type, cache_control

        cache_control.cache = game_type.Cache()
        normal_config.init_normal_config()

        from Script.Core import get_text  # noqa: F401
        from Script.Config import game_config, character_config

        game_config.init()

        # 通过真实加载器全量加载启用 mod（会把补丁安装进真实 Script 模块）
        from Script.Core.mod_manager import init_mod_system

        mod_success = init_mod_system()

        cache_control.cache.web_mode = normal_config.config_normal.web_draw

        character_config.init_character_tem_data()

        from Script.Config import map_config

        map_config.init_map_data()

        from Script.Design import character_handle, game_time
        import Script.Settle  # noqa: F401
        import Script.StateMachine  # noqa: F401
        import Script.System.Medical_System  # noqa: F401
        import Script.UI.Flow  # noqa: F401
        from Script.Core import constant

        character_handle.init_character_tem()
        game_time.init_time()

        # 初始化系统设置与新档基础数据，与创建角色流程一致；
        # 真实结算函数会读取 difficulty_setting、rhodes_island 资源、country 等。
        from Script.Design import attr_calculation, basement

        if not getattr(cache_control.cache, "all_system_setting", None) or not getattr(
            cache_control.cache.all_system_setting, "difficulty_setting", None
        ):
            cache_control.cache.all_system_setting = attr_calculation.get_system_setting_zero()
        # 与 creator_character_flow 的开局初始化保持一致（基地/初始资源/国家数据），
        # 使成就统计等真实路径（achievement_flow 读 materials_resouce[1]）不缺键。
        cache_control.cache.rhodes_island = basement.get_base_zero()
        cache_control.cache.rhodes_island.materials_resouce[1] = 20000
        cache_control.cache.rhodes_island.materials_resouce[11] = 20
        cache_control.cache.rhodes_island.materials_resouce[15] = 300
        cache_control.cache.rhodes_island.materials_resouce[21] = 10
        cache_control.cache.country = attr_calculation.get_country_reset(cache_control.cache.country)

        if enable_debug:
            cache_control.cache.debug_mode = True

        _BOOTED = BootContext(
            cache=cache_control.cache,
            constant=constant,
            game_type=game_type,
            mod_success=mod_success,
        )
        return _BOOTED
    finally:
        os.chdir(cwd)
