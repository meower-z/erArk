#!/usr/bin/env python3
"""
erArk TK 渲染性能自动化基准脚本

原理：
    加载存档后进入 InScenePanel 或 SeeMapPanel 的真实重绘循环，将 flow_handle.askfor_all 替换为
    io_init.ask_choice(()) 阻塞等待，并在 TkFrontend 就绪时自动提交空输入以驱动 N 次完整重绘。
    每屏耗时由 Script/Core/perf_hook.py、Script/Frontend/Tk、io_init 埋点及 ui_perf_patch.py 收集。

使用示例：
    python -m profiling.ui_render_benchmark --load-save 1 --screens 30

输出：
    profiling_output/ui_perf_<时间戳>.jsonl            —— 每屏分类耗时明细
    profiling_output/ui_render_benchmark_<时间戳>.json —— 会话汇总（分类耗时总表 + 每屏端到端延迟）
"""

import argparse
import json
import os
import secrets
import sys
import time
from datetime import datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING

from profiling.ui_benchmark_session import BenchmarkSession, BenchmarkState, log
from Script.Modules.domains import roster
from Script.Modules.domains import identity

if TYPE_CHECKING:
    from Script.UI.Panel import in_scene_panel, see_map_panel

    BenchmarkPanel = see_map_panel.SeeMapPanel | in_scene_panel.InScenePanel


PROFILE_DIR = "profiling_output"
os.makedirs(PROFILE_DIR, exist_ok=True)


def parse_args() -> argparse.Namespace:
    """
    解析命令行参数

    参数：无

    返回值类型：argparse.Namespace
    功能描述：提供存档号、重绘屏数、目标面板、预热选项与汇总文件前缀等参数
    """
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--load-save",
        type=str,
        default="1",
        help="要加载的存档 id（数字或 auto）",
    )
    ap.add_argument(
        "--screens", type=int, default=30, help="要执行的主界面完整重绘次数"
    )
    ap.add_argument(
        "--summary-name",
        type=str,
        default="ui_render_benchmark",
        help="汇总输出文件前缀",
    )
    ap.add_argument(
        "--panel",
        type=str,
        default="scene",
        choices=["scene", "map"],
        help="基准面板：scene=主场景互动界面，map=查看地图界面",
    )
    ap.add_argument(
        "--warmup-screens",
        type=int,
        default=0,
        help="预热屏数：先绘制N屏（不计入统计）让Tk完成字形/行度量，然后清屏再开始正式测量，用于验证启动期预热方案的效果",
    )
    ap.add_argument(
        "--no-warmup-clear",
        action="store_true",
        help="预热后不清屏（对照实验：区分尖峰来自字形度量还是清屏后重建）",
    )
    ap.add_argument(
        "--timeout-per-screen",
        type=float,
        default=60.0,
        help="单屏渲染等待超时（秒）",
    )
    ap.add_argument(
        "--prewarm",
        action="store_true",
        help="保留启动期的常用字符度量预热 Script.Frontend.Tk.warmup.warm_up()（与正常游戏启动流程一致）",
    )
    return ap.parse_args()


def main() -> None:
    """
    基准主入口
    参数：无
    返回值类型：无
    功能描述：初始化游戏环境 -> 打开性能埋点 -> 替换输入等待函数 ->
              启动 Tk 主循环与 flow 线程执行 N 次主界面重绘 -> 输出汇总后退出进程
    """
    args = parse_args()

    # 复用无渲染基准脚本的环境初始化（不打 IO 补丁，保留真实绘制）
    from profiling.run_profile import init_game_environment

    env_args = SimpleNamespace(
        with_premise_profiler=False,
        load_save=args.load_save,
        try_load_auto=False,
    )
    init_game_environment(env_args)

    from Script.Core import perf_hook

    # 打开性能埋点并应用 flow 侧排版补丁
    perf_hook.enabled = True
    from profiling import ui_perf_patch

    ui_perf_patch.apply_flow_draw_patches()

    from Script.Core import constant, flow_handle, io_init
    from Script.Config import normal_config
    from Script.Frontend.Tk import warmup
    from Script.Frontend.Tk.app import TkFrontend
    from Script.Protocol import ThreadedUiPort
    from Script.UI.Moudle import view

    if not identity.exists(0):
        log("错误：存档未正确加载（无玩家数据），中止。")
        sys.exit(1)
    log(f"存档已加载：NPC 数量 = {roster.count()}")

    # 基准运行状态
    state: BenchmarkState = {
        "screens_done": 0,
        "screen_wall_times": [],
        "warmup_wall_times": [],
        "warmup_cleared": False,
        "aborted": False,
        "exit_code": 0,
    }
    total_screens = args.screens + args.warmup_screens

    def benchmark_askfor_all(
        input_list: list, print_order: bool = False
    ) -> str:
        """
        askfor_all 的基准替身：调用 `io_init.ask_choice(())` 阻塞等待前端渲染完成与自动应答并记录单屏耗时，
        达标后置 `view.now_panel_id = -999` 退出循环

        参数：
        input_list (list) -- askfor_all 的可选项列表（此处忽略）
        print_order (bool) -- askfor_all 的回显开关（此处忽略）

        返回值类型：str -- 恒为空字符串
        """
        t0 = time.perf_counter()
        io_init.ask_choice(())
        wall = time.perf_counter() - t0
        state["screens_done"] += 1
        # 预热屏与正式测量屏分开记录
        if state["screens_done"] <= args.warmup_screens:
            state["warmup_wall_times"].append(wall)
            log(
                f"预热屏 {state['screens_done']}/{args.warmup_screens} 完成，flow等待GUI渲染 {wall * 1000:.1f} ms"
            )
        else:
            state["screen_wall_times"].append(wall)
            measured = state["screens_done"] - args.warmup_screens
            if measured % 5 == 0 or measured == 1:
                log(
                    f"屏 {measured}/{args.screens} 完成，flow等待GUI渲染 {wall * 1000:.1f} ms"
                )
        # 预热结束后清屏一次，模拟"启动期预热后清屏进入正式界面"（--no-warmup-clear 时跳过）
        if (
            args.warmup_screens
            and state["screens_done"] == args.warmup_screens
            and not state["warmup_cleared"]
        ):
            state["warmup_cleared"] = True
            if not args.no_warmup_clear:
                io_init.clear_screen()
        if state["screens_done"] >= total_screens:
            # 让面板的 while-1 循环在下一次条件检查时退出
            view.now_panel_id = -999
        return ""

    flow_handle.askfor_all = benchmark_askfor_all

    def draw() -> None:
        """
        注册样式并按参数进入主场景或查看地图面板的重绘循环，直至基准屏数达标或会话取消

        参数：无

        返回值类型：None
        """
        io_init.init_style()
        width = normal_config.config_normal.text_width
        log(
            f"开始基准：面板={args.panel}，{args.screens} 屏完整重绘，文本宽度 {width}"
        )
        panel: BenchmarkPanel
        if args.panel == "map":
            view.now_panel_id = constant.Panel.SEE_MAP
            from Script.UI.Panel import see_map_panel

            panel = see_map_panel.SeeMapPanel(width)
        else:
            view.now_panel_id = constant.Panel.IN_SCENE
            from Script.UI.Panel import in_scene_panel

            panel = in_scene_panel.InScenePanel(width)
        panel.draw()

    def report(total_wall: float) -> None:
        """
        将本次基准的汇总 JSON 写入 profiling_output 目录，并向日志输出分类耗时表与每屏等待统计

        参数：
        total_wall (float) -- 重绘循环总墙钟耗时（秒）

        返回值类型：None
        """
        log(
            f"重绘循环结束：{state['screens_done']} 屏，总墙钟 {total_wall:.2f}s"
        )
        summary = {
            "screens_requested": args.screens,
            "screens_done": len(state["screen_wall_times"]),
            "warmup_screens": args.warmup_screens,
            "aborted": state["aborted"],
            "warmup_wall_ms": [
                round(t * 1000, 1) for t in state["warmup_wall_times"]
            ],
            "npc_count": roster.count(),
            "total_wall_s": round(total_wall, 3),
            "screen_wall_ms": [
                round(t * 1000, 1) for t in state["screen_wall_times"]
            ],
            "session": perf_hook.get_session_summary(),
            "jsonl_path": perf_hook.get_output_path(),
        }
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_path = os.path.join(
            PROFILE_DIR, f"{args.summary_name}_{ts}.json"
        )
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        times = summary["session"]["times_ms"]
        log("=" * 60)
        log(f"分类耗时汇总（{state['screens_done']} 屏累计，按总耗时降序）：")
        for key, rec in sorted(
            times.items(), key=lambda kv: kv[1]["total_ms"], reverse=True
        )[:25]:
            log(
                f"  {key:<40} calls={rec['calls']:<7} total={rec['total_ms']:>10.1f}ms max={rec['max_ms']:>8.2f}ms"
            )
        log(f"消息计数：{summary['session']['counts']}")
        wall_list = state["screen_wall_times"]
        if wall_list:
            sorted_wall = sorted(wall_list)
            log(
                f"每屏flow等待GUI耗时: mean={sum(wall_list) / len(wall_list) * 1000:.1f}ms "
                f"p50={sorted_wall[len(sorted_wall) // 2] * 1000:.1f}ms "
                f"max={sorted_wall[-1] * 1000:.1f}ms"
            )
        log(f"每屏明细 JSONL: {summary['jsonl_path']}")
        log(f"会话汇总 JSON: {summary_path}")
        log("基准完成。")

    token = secrets.token_hex(16)
    port = ThreadedUiPort(token)
    frontend = TkFrontend(port, token)
    io_init.configure(port)
    io_init.apply_frontend_config(frontend.init_config)
    session = BenchmarkSession(
        frontend, frontend.window.root, port, state, args.timeout_per_screen
    )
    arm = frontend._do_arm

    def arm_and_answer() -> None:
        """
        先执行前端输入就绪回调完成本屏耗时统计，再立即提交空输入以驱动下一屏重绘并重置单屏超时定时器

        参数：无

        返回值类型：None
        """
        arm()
        frontend.submit_input()
        session.restart_deadline()

    frontend._do_arm = arm_and_answer
    if not args.prewarm:
        warmup.warm_up = lambda *_, **__: None
    session.serve(draw, report)
    sys.exit(state["exit_code"])


if __name__ == "__main__":
    main()
