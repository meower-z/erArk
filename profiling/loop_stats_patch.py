# -*- coding: UTF-8 -*-
"""
主循环 / NPC AI 结构统计补丁（monkey-patch，不改动产品代码）

用途：
    cProfile 能给出函数级耗时，但无法回答以下结构性问题：
    - 每个 NPC 每游戏小时开始了多少个行动（settle_start 调用数 / NPC 数 / 游戏小时）
    - search_target 每次实际检索了多长的 target 列表、多久落一次全量兜底
    - 内核每一步的耗时随 NPC 数量的分布（均值 / p95 / 最大值）
    本补丁包裹 core.step / character_behavior.settle_start / handle_npc_ai.choose_state_machine /
    handle_npc_ai.search_target 四个函数，收集上述计数，供 run_profile.py 以 --loop-stats 启用。

注意：
    - 只做只读统计，不改变任何参数与返回值，不破坏 premise_data / null_target_set
      等削减缓存的复用逻辑。
    - 需在 profile 运行前调用 apply_loop_stats_patch()，结束后 export_loop_stats()。
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import TypedDict

    class LoopStats(TypedDict):
        """loop_stats 的各项计数与累计耗时（秒）"""

        steps: int
        game_minutes: int
        npc_count: int
        step_times: list[float]
        settle_start_calls_player: int
        settle_start_calls_npc: int
        settle_start_time: float
        choose_state_machine_calls: int
        choose_state_machine_time: float
        search_target_calls: int
        search_target_time: float
        search_target_list_len_sum: int
        search_target_list_len_max: int
        search_target_full_scans: int


loop_stats: LoopStats = {
    "steps": 0,
    "game_minutes": 0,
    "npc_count": 0,
    "step_times": [],
    "settle_start_calls_player": 0,
    "settle_start_calls_npc": 0,
    "settle_start_time": 0.0,
    "choose_state_machine_calls": 0,
    "choose_state_machine_time": 0.0,
    "search_target_calls": 0,
    "search_target_time": 0.0,
    "search_target_list_len_sum": 0,
    "search_target_list_len_max": 0,
    "search_target_full_scans": 0,
}
""" 结构统计累计数据 """

_applied = False
""" 防止重复打补丁的标志 """


def apply_loop_stats_patch() -> None:
    """
    应用主循环结构统计补丁
    参数：无
    返回值类型：无
    功能描述：包裹 core.step / character_behavior.settle_start /
              handle_npc_ai.choose_state_machine / handle_npc_ai.search_target，
              收集每步耗时、行动开始数与 target 检索规模；幂等
    """
    global _applied
    if _applied:
        return
    _applied = True

    from Script.Core import cache_control
    from Script.Config import game_config
    from Script.Design import character_behavior, handle_npc_ai
    from Script.Kernel import core

    cache = cache_control.cache
    # 全量 target 列表长度，用于判定 search_target 是否落入全量兜底扫描
    full_target_count = len(game_config.config_target)

    # ---- 步级：内核每一步的耗时、时钟走过的分钟 + NPC 数 ----
    original_step = core.step

    def _timed_step() -> None:
        clock = core.state().clock
        t0 = time.perf_counter()
        original_step()
        loop_stats["step_times"].append(time.perf_counter() - t0)
        loop_stats["steps"] += 1
        loop_stats["game_minutes"] += core.state().clock - clock
        loop_stats["npc_count"] = len(cache.npc_id_got)

    core.step = _timed_step

    # ---- 角色级：settle_start 调用规模（每开始一个行动调用一次） ----
    original_settle_start = character_behavior.settle_start

    def _counted_settle_start(character_id: int, minutes: int) -> None:
        # 玩家与 NPC 分开计数，便于算"每 NPC 每游戏小时开始多少个行动"
        if character_id == 0:
            loop_stats["settle_start_calls_player"] += 1
        else:
            loop_stats["settle_start_calls_npc"] += 1
        t0 = time.perf_counter()
        original_settle_start(character_id, minutes)
        loop_stats["settle_start_time"] += time.perf_counter() - t0

    character_behavior.settle_start = _counted_settle_start

    # ---- AI 决策级：choose_state_machine / search_target ----
    original_choose_state_machine = handle_npc_ai.choose_state_machine

    def _timed_choose_state_machine(character_id: int) -> int | None:
        loop_stats["choose_state_machine_calls"] += 1
        t0 = time.perf_counter()
        result = original_choose_state_machine(character_id)
        loop_stats["choose_state_machine_time"] += time.perf_counter() - t0
        return result

    handle_npc_ai.choose_state_machine = _timed_choose_state_machine

    original_search_target = handle_npc_ai.search_target

    def _timed_search_target(
        character_id: int,
        target_list: list,
        null_target: set,
        premise_data: dict[str, float],
        target_weight_data: dict[str, float],
        *args: bool,
        **kwargs: bool,
    ) -> tuple[str, float, int, dict[str, float]]:
        # 记录检索列表规模：list_len 逼近全量即为兜底扫描
        list_len = len(target_list)
        loop_stats["search_target_calls"] += 1
        loop_stats["search_target_list_len_sum"] += list_len
        if list_len > loop_stats["search_target_list_len_max"]:
            loop_stats["search_target_list_len_max"] = list_len
        if list_len >= full_target_count:
            loop_stats["search_target_full_scans"] += 1
        t0 = time.perf_counter()
        result = original_search_target(
            character_id,
            target_list,
            null_target,
            premise_data,
            target_weight_data,
            *args,
            **kwargs,
        )
        loop_stats["search_target_time"] += time.perf_counter() - t0
        return result

    handle_npc_ai.search_target = _timed_search_target


def export_loop_stats(path: str) -> None:
    """
    导出结构统计结果
    参数:
        path (str) -- 输出 JSON 文件路径
    返回值类型：无
    功能描述：汇总每步耗时分布（均值/p50/p95/最大）与行动开始、检索规模等派生指标后写盘
    """
    step_times = sorted(loop_stats["step_times"])
    steps = loop_stats["steps"]
    hours = loop_stats["game_minutes"] / 60
    npc_count = loop_stats["npc_count"]
    npc_calls = loop_stats["settle_start_calls_npc"]

    def _pct(p: float) -> float:
        # 简易百分位：取排序后对应下标值
        if not step_times:
            return 0.0
        idx = min(len(step_times) - 1, int(len(step_times) * p))
        return step_times[idx]

    summary = {
        "steps": steps,
        "game_minutes": loop_stats["game_minutes"],
        "npc_count": npc_count,
        "step_time_ms": {
            "mean": round(sum(step_times) / steps * 1000, 3) if steps else 0.0,
            "p50": round(_pct(0.50) * 1000, 3),
            "p95": round(_pct(0.95) * 1000, 3),
            "max": round(step_times[-1] * 1000, 3) if step_times else 0.0,
        },
        "settle_start": {
            "calls_player": loop_stats["settle_start_calls_player"],
            "calls_npc": npc_calls,
            "total_time_s": round(loop_stats["settle_start_time"], 3),
            # 每 NPC 每游戏小时平均开始的行动数
            "npc_starts_per_hour": (
                round(npc_calls / (hours * npc_count), 2)
                if hours and npc_count
                else 0.0
            ),
        },
        "choose_state_machine": {
            "calls": loop_stats["choose_state_machine_calls"],
            "total_time_s": round(loop_stats["choose_state_machine_time"], 3),
        },
        "search_target": {
            "calls": loop_stats["search_target_calls"],
            "total_time_s": round(loop_stats["search_target_time"], 3),
            "avg_list_len": (
                round(
                    loop_stats["search_target_list_len_sum"]
                    / loop_stats["search_target_calls"],
                    1,
                )
                if loop_stats["search_target_calls"]
                else 0.0
            ),
            "max_list_len": loop_stats["search_target_list_len_max"],
            # 全量兜底扫描次数：premise 判定量最大的路径
            "full_scans": loop_stats["search_target_full_scans"],
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
