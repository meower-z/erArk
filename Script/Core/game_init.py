# -*- coding: UTF-8 -*-
"""游戏流程的初始化与运行入口，以及命令输入请求函数的别名"""

import os
import threading
import traceback
from types import FunctionType
from collections.abc import Callable
from Script.Core import (
    flow_handle,
    io_init,
    constant,
    py_cmd,
    get_text,
    save_handle,
)
from Script.Config import game_config, normal_config
from Script.UI.Moudle import panel, view
from Script.Design import game_time
from Script.Modules.domains import history
from Script.Protocol import FrontendInitConfig, SessionCancelled, UiPort

_: FunctionType = get_text._
""" 翻译api """

# 字符串定义###########################################################
NO_EVENT_FUNC = "no_event_func"

# 系统函数#############################################################
# 初始化函数
_main_flow: Callable[[], object] | None = None
error_path = os.path.join("error.log")


def init(main_flow: Callable[[], object]) -> None:
    """
    游戏流程初始化
    Keyword argument:
    main_flow -- 游戏主流程
    """
    io_init.clear_screen()
    io_init.clear_order()
    flow_handle.cmd_clear()
    # 设置背景颜色
    io_init.set_background(normal_config.config_normal.background)
    # 初始化字体
    io_init.init_style()
    # 初始化地图数据
    global _main_flow
    _main_flow = main_flow

    _have_run = False

    def run_main_flow() -> None:
        nonlocal _have_run
        while True:
            if not _have_run:
                main_flow()
                _have_run = True
            askfor_order()
            flow_handle.call_default_flow()
            if flow_handle.exit_flag:
                break

    while True:

        try:
            run_main_flow()
        except Exception:
            # 最近玩家指令状态
            instruct_cn_name_list = ""
            for behavior_id in history.recent():
                if behavior_id in game_config.config_behavior:
                    behavior_data = game_config.config_behavior[behavior_id]
                    instruct_cn_name_list += behavior_data.name + "，"
            if len(instruct_cn_name_list) and instruct_cn_name_list[-1] == "，":
                instruct_cn_name_list = instruct_cn_name_list[:-1]
            # 向error_log写入回溯用信息
            with open(error_path, "a", encoding="utf-8") as e:
                e.write(f"\n版本信息：{normal_config.config_normal.verson}\n")
                e.write(f"最近输入指令：{view.input_cache}\n")
                e.write(f"玩家最近状态：{instruct_cn_name_list}\n")
                e.write(
                    f"当前游戏内时间：{game_time.get_date_text(game_time.now())}\n"
                )
                traceback.print_exc(file=e)
            # 向游戏内写入错误信息
            error_text = "\n"
            error_text += _("版本信息：{0}\n").format(
                normal_config.config_normal.verson
            )
            error_text += _("最近输入指令：{0}\n").format(view.input_cache)
            error_text += _("玩家最近状态：{0}\n").format(instruct_cn_name_list)
            error_text += _("当前游戏内时间：{0}\n").format(
                game_time.get_date_text(game_time.now())
            )
            error_text += traceback.format_exc()
            error_text += _(
                "\n\n游戏发生错误，已将上述错误信息写入error.log\n\n"
            )
            error_text += _(
                "报错数据文件已保存至99号档位，请将error.log和存档发送给游戏作者以帮助解决问题\n\n"
            )
            save_handle.establish_save("99")
            # 输出选择面板
            ask_list: list[str] = []
            askfor_panel = panel.OneMessageAndSingleColumnButton()
            askfor_list = [(_("回到标题画面")), (_("退出游戏"))]
            askfor_panel.set(askfor_list, (error_text), 0)
            askfor_panel.draw()
            askfor_panel_return_list = askfor_panel.get_return_list()
            ask_list.extend(askfor_panel_return_list.keys())
            yrn = flow_handle.askfor_all(ask_list)
            py_cmd.clr_cmd()
            # 回到标题画面
            if yrn == "0":
                io_init.clear_screen()
                io_init.clear_order()
                flow_handle.cmd_clear()
                view.now_panel_id = constant.Panel.TITLE
            else:
                io_init.end_session("error")


def start(
    main_func: Callable[[], object], port: UiPort, config: FrontendInitConfig
) -> threading.Thread:
    """
    配置通信端口与前端初始尺寸并启动游戏主流程工作线程

    参数：
    main_func (Callable[[], object]) -- 游戏主流程入口函数
    port (UiPort) -- 后端通信端口实例
    config (FrontendInitConfig) -- 前端按屏幕尺寸算出的初始配置

    返回值类型：threading.Thread -- 已启动的名为 "flowthread" 的守护线程
    """
    io_init.configure(port)
    io_init.apply_frontend_config(config)
    worker = threading.Thread(
        target=_serve, args=(main_func,), name="flowthread", daemon=True
    )
    worker.start()
    return worker


def _serve(main_func: Callable[[], object]) -> None:
    try:
        init(main_func)
    except SessionCancelled:
        return


def console_log(string: str) -> None:
    """
    向后台打印日志
    Keyword arguments:
    string -- 游戏日志信息
    """
    print("game log:")
    print(string + "\n")


# 请求输入命令
askfor_order = flow_handle.order_deal

# 请求输入一个字符串
askfor_str = flow_handle.askfor_str

# 请求输入一个数字
askfor_int = flow_handle.askfor_int
askfor_all = flow_handle.askfor_all

# 设置尾命令处理函数
set_deal_cmd_func = flow_handle.set_tail_deal_cmd_func

# 设置尾命令处理函数装饰器
set_deal_cmd_func_deco = flow_handle.deco_set_tail_deal_cmd_func
