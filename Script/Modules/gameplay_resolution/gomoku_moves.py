"""
五子棋候选落子筛选（gomoku_moves）
==================================
基于 Evaluate 的棋盘、历史与棋型缓存筛选并分级排序候选落子。
本模块不执行界面绘制，不导入 Script.UI、Script.Settle 或 Tk。
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from Script.Modules.gameplay_resolution.gomoku_shapes import (
    ALL_DIRECTIONS,
    SHAPES,
    config,
    coordinate2position,
    get_all_shapes_of_point,
    has_in_line,
    is_five,
    is_four,
    position2coordinate,
)

if TYPE_CHECKING:
    from typing import Literal

    from Script.Modules.gameplay_resolution.gomoku_evaluate import Evaluate


def get_points_in_line(
    evaluator: Evaluate, role: int
) -> defaultdict[int, set[int]] | Literal[False]:
    """
    沿最近数步落子的四方向线收集带棋型空位
    Keyword arguments:
    evaluator -- 局面评估对象
    role -- 当前行棋方，1 或 -1
    Return arguments:
    defaultdict | bool -- 按棋型分组的位置集合，无结果时为 False
    """
    points_in_line = defaultdict(set)
    has_points_in_line = False
    last2_points = [
        position for position, _ in evaluator.history[-config["inline_count"] :]
    ]
    processed: dict[int, int] = {}
    for r in [role, -role]:
        for point in last2_points:
            x, y = position2coordinate(point, evaluator.size)
            for ox, oy in ALL_DIRECTIONS:
                for sign in [
                    1,
                    -1,
                ]:
                    for step in range(1, config["in_line_distance"] + 1):
                        nx, ny = x + sign * step * ox, y + sign * step * oy
                        position = coordinate2position(nx, ny, evaluator.size)
                        if (
                            nx < 0
                            or nx >= evaluator.size
                            or ny < 0
                            or ny >= evaluator.size
                        ):
                            break
                        if evaluator.board[nx + 1, ny + 1] != 0:
                            continue
                        if processed.get(position) == r:
                            continue
                        processed[position] = r
                        for direction in range(4):
                            shape = evaluator.shape_cache[r][direction][nx][ny]
                            if shape:
                                points_in_line[shape].add(
                                    coordinate2position(nx, ny, evaluator.size)
                                )
                                has_points_in_line = True
    if has_points_in_line:
        return points_in_line
    return False


def get_points(
    evaluator: Evaluate, role: int, depth: int, vct: bool, vcf: bool
) -> defaultdict[int, set[int]]:
    """
    按搜索深度与算杀开关收集带棋型的候选位置
    Keyword arguments:
    evaluator -- 局面评估对象
    role -- 当前行棋方，1 或 -1
    depth -- 当前搜索深度
    vct -- 是否启用连续活三算杀过滤
    vcf -- 是否仅保留冲四与五连相关棋型
    Return arguments:
    defaultdict -- 按棋型编号分组的位置序号集合
    """
    first = role if depth % 2 == 0 else -role
    if (
        config["only_in_line"]
        and len(evaluator.history) >= config["inline_count"]
    ):
        points_in_line = get_points_in_line(evaluator, role)
        if points_in_line:
            return points_in_line

    points = defaultdict(set)
    last_points = [position for position, _ in evaluator.history[-4:]]

    for r in [role, -role]:
        for i in range(evaluator.size):
            for j in range(evaluator.size):
                four_count = block_four_count = three_count = 0
                for direction in range(4):
                    if evaluator.board[i + 1, j + 1] != 0:
                        continue
                    shape = evaluator.shape_cache[r][direction][i][j]
                    if not shape:
                        continue
                    point = i * evaluator.size + j
                    if vct:
                        if depth % 2 == 0:
                            if depth == 0 and r != first:
                                continue
                            if (
                                shape != SHAPES["THREE"]
                                and not is_four(shape)
                                and not is_five(shape)
                            ):
                                continue
                            if shape == SHAPES["THREE"] and r != first:
                                continue
                            if depth == 0 and r != first:
                                continue
                            if depth > 0:
                                if (
                                    shape == SHAPES["THREE"]
                                    and len(
                                        get_all_shapes_of_point(
                                            evaluator.shape_cache, i, j, r
                                        )
                                    )
                                    == 1
                                ):
                                    continue
                                if (
                                    shape == SHAPES["BLOCK_FOUR"]
                                    and len(
                                        get_all_shapes_of_point(
                                            evaluator.shape_cache, i, j, r
                                        )
                                    )
                                    == 1
                                ):
                                    continue
                        else:
                            if (
                                shape != SHAPES["THREE"]
                                and not is_four(shape)
                                and not is_five(shape)
                            ):
                                continue
                            if shape == SHAPES["THREE"] and r == -first:
                                continue
                            if depth > 1:
                                if (
                                    shape == SHAPES["BLOCK_FOUR"]
                                    and len(
                                        get_all_shapes_of_point(
                                            evaluator.shape_cache, i, j, r
                                        )
                                    )
                                    == 1
                                ):
                                    continue
                                if shape == SHAPES[
                                    "BLOCK_FOUR"
                                ] and not has_in_line(
                                    point, last_points, evaluator.size
                                ):
                                    continue
                    if vcf:
                        if not is_four(shape) and not is_five(shape):
                            continue
                    if (
                        depth > 2
                        and (
                            shape == SHAPES["TWO"]
                            or shape == SHAPES["TWO_TWO"]
                            or shape == SHAPES["BLOCK_THREE"]
                        )
                        and not has_in_line(point, last_points, evaluator.size)
                    ):
                        continue
                    points[shape].add(point)
                    if shape == SHAPES["FOUR"]:
                        four_count += 1
                    elif shape == SHAPES["BLOCK_FOUR"]:
                        block_four_count += 1
                    elif shape == SHAPES["THREE"]:
                        three_count += 1
                    union_shape = None
                    if four_count >= 2:
                        union_shape = SHAPES["FOUR_FOUR"]
                    elif block_four_count and three_count:
                        union_shape = SHAPES["FOUR_THREE"]
                    elif three_count >= 2:
                        union_shape = SHAPES["THREE_THREE"]
                    if union_shape:
                        points[union_shape].add(point)

    return points


def get_moves(
    evaluator: Evaluate,
    role: int,
    depth: int,
    only_three: bool = False,
    only_four: bool = False,
) -> list[tuple[int, int]]:
    """
    筛选候选落子并转换为坐标列表
    Keyword arguments:
    evaluator -- 局面评估对象
    role -- 当前行棋方，1 或 -1
    depth -- 当前搜索深度
    only_three -- 是否启用连续活三算杀过滤 (default False)
    only_four -- 是否仅保留四连与五连候选 (default False)
    Return arguments:
    list -- 候选落子的 (行, 列) 坐标列表
    """
    moves = [
        (move // evaluator.size, move % evaluator.size)
        for move in _get_moves(evaluator, role, depth, only_three, only_four)
    ]
    return moves


def _get_moves(
    evaluator: Evaluate,
    role: int,
    depth: int,
    only_three: bool = False,
    only_four: bool = False,
) -> set[int]:
    """
    按棋型优先级分档筛选候选位置序号集合
    Keyword arguments:
    evaluator -- 局面评估对象
    role -- 当前行棋方，1 或 -1
    depth -- 当前搜索深度
    only_three -- 是否启用连续活三算杀过滤 (default False)
    only_four -- 是否仅保留四连与五连候选 (default False)
    Return arguments:
    set -- 选中的位置序号集合
    """
    points = get_points(evaluator, role, depth, only_three, only_four)
    fives = points[SHAPES["FIVE"]]
    block_fives = points[SHAPES["BLOCK_FIVE"]]
    if fives or block_fives:
        return set(fives | block_fives)
    fours = points[SHAPES["FOUR"]]
    block_fours = points[SHAPES["BLOCK_FOUR"]]
    if only_four or fours:
        return set(fours | block_fours)
    four_fours = points[SHAPES["FOUR_FOUR"]]
    if four_fours:
        return set(four_fours | block_fours)
    threes = points[SHAPES["THREE"]]
    four_threes = points[SHAPES["FOUR_THREE"]]
    if four_threes:
        return set(four_threes | block_fours | threes)
    three_threes = points[SHAPES["THREE_THREE"]]
    if three_threes:
        return set(three_threes | block_fours | threes)
    if only_three:
        return set(block_fours | threes)
    block_threes = points[SHAPES["BLOCK_THREE"]]
    two_twos = points[SHAPES["TWO_TWO"]]
    twos = points[SHAPES["TWO"]]
    res = set(
        list(block_fours | threes | block_threes | two_twos | twos)[
            : config["points_limit"]
        ]
    )
    return res
