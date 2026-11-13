#!/usr/bin/python3
# -*- coding: UTF-8 -*-
"""
游戏入口：作为主程序运行时构建数据，初始化缓存、配置、Mod、角色与时间，
再以 Tk 窗口启动游戏
"""

import sys
import logging
import time
from types import FunctionType

if __name__ == "__main__":

    import auto_build_config
    from Script.Config import normal_config
    from Script.Core import game_type, cache_control

    logging.basicConfig(
        format="等级：%(levelname)s，函数名：%(funcName)s，信息为：%(message)s",
        level=logging.WARNING,
    )

    # 初始化游戏缓存数据
    cache_control.cache = game_type.Cache()
    # 初始化游戏基础配置数据
    normal_config.init_normal_config()

    from Script.Core import get_text
    from Script.Config import game_config, character_config

    _: FunctionType = get_text._
    """ 翻译api """

    # 载入游戏配置
    game_config.init()
    # 初始化Mod系统
    from Script.Core.mod_manager import init_mod_system

    print("正在加载Mod...")
    mod_load_success = init_mod_system()
    if mod_load_success:
        print("Mod加载完成")
    else:
        print("部分Mod加载失败，请检查mod文件夹")
    # 初始化角色人物卡数据
    character_config.init_character_tem_data()

    # 载入地图数据
    from Script.Config import map_config

    map_config.init_map_data()

    from Script.Design import start_flow, character_handle, game_time
    import Script.Settle
    import Script.StateMachine
    import Script.System.Medical_System
    from Script.Core import game_init
    import Script.UI.Flow

    # 载入角色人物卡数据
    character_handle.init_character_tem()

    # 初始化游戏时间
    game_time.init_time()

    # 性能监控开关：config.ini 中 perf_monitor = 1 时启用 TK 渲染性能埋点与排版补丁
    perf_monitor: int = getattr(normal_config.config_normal, "perf_monitor", 0)
    if perf_monitor:
        from Script.Core import perf_hook

        perf_hook.enabled = True
        try:
            from profiling import ui_perf_patch

            ui_perf_patch.apply_flow_draw_patches()
        except Exception as e:
            print(f"警告：性能监控排版补丁加载失败: {e}")
        print(
            f"性能监控已开启，每屏渲染耗时将写入 {perf_hook.get_output_path()}"
        )

    try:
        game_init.run(start_flow.start_frame)
    except Exception as e:
        print(f"游戏初始化失败: {e}")
        logging.error(f"游戏初始化失败: {str(e)}", exc_info=True)
        sys.exit(1)

    # 保持主线程运行
    try:
        while True:
            # 主循环保持程序运行，减少CPU使用率
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n游戏已被用户中断")
        sys.exit(0)
