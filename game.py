#!/usr/bin/python3
# -*- coding: UTF-8 -*-
"""
游戏入口：作为主程序运行时构建数据，初始化配置、Mod、角色模板、地图与内核时钟，
再以 Tk 窗口启动游戏
"""

import sys
import logging
import secrets
from types import FunctionType

WORKER_JOIN_SECONDS = 5
"""Tk 主循环退出后主线程等待游戏流程线程结束的最长秒数。"""

if __name__ == "__main__":

    import auto_build_config
    from Script.Config import normal_config

    logging.basicConfig(
        format="等级：%(levelname)s，函数名：%(funcName)s，信息为：%(message)s",
        level=logging.WARNING,
    )

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

    from Script.Design import start_flow
    import Script.Settle
    import Script.StateMachine
    import Script.System.Medical_System
    from Script.Core import game_init
    import Script.UI.Flow

    # 初始化游戏时间：内核时钟从开局时刻开始，新游戏或读档时再换掉内核的 GameState
    from Script.Modules.save_load import kernel_state

    kernel_state.reset_clock(kernel_state.first_clock())

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

    from Script.Frontend.Tk.app import TkFrontend
    from Script.Protocol import ThreadedUiPort

    token = secrets.token_hex(16)
    port = ThreadedUiPort(token)
    try:
        frontend = TkFrontend(port, token)
        worker = game_init.start(
            start_flow.start_frame, port, frontend.init_config
        )
    except Exception as e:
        print(f"游戏初始化失败: {e}")
        logging.error(f"游戏初始化失败: {str(e)}", exc_info=True)
        sys.exit(1)
    frontend.run()
    port.close("window closed")
    worker.join(WORKER_JOIN_SECONDS)
