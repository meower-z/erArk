"""
五子棋棋型与评分常量（gomoku_shapes）
=====================================
提供棋型评分常量、config、四向偏移、SHAPES 及坐标与棋型函数。
本模块不执行界面绘制，不导入 Script.UI、Script.Settle 或 Tk。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Mapping

FIVE = 10000000
FOUR = 100000
THREE_THREE = FOUR / 2
BLOCK_FOUR = 1500
THREE = 1000
BLOCK_THREE = 150
TWO_TWO = 200
TWO = 100
BLOCK_TWO = 15
ONE = 10
MAX = 1000000000

config = {
    "enable_cache": True,
    "points_limit": 20,
    "only_in_line": False,
    "inline_count": 4,
    "in_line_distance": 5,
}

ALL_DIRECTIONS = [
    (0, 1),
    (1, 0),
    (1, 1),
    (1, -1),
]

SHAPES = {
    "FIVE": 5,
    "BLOCK_FIVE": 50,
    "FOUR": 4,
    "FOUR_FOUR": 44,
    "FOUR_THREE": 43,
    "THREE_THREE": 33,
    "BLOCK_FOUR": 40,
    "THREE": 3,
    "BLOCK_THREE": 30,
    "TWO_TWO": 22,
    "TWO": 2,
    "NONE": 0,
}


def get_real_shape_score(shape: int) -> float:
    """
    将形状编号转换为评估用的得分
    Keyword arguments:
    shape -- 形状编号
    Return arguments:
    int | float -- 得分
    """
    if shape == SHAPES["FIVE"]:
        return FOUR
    elif shape == SHAPES["BLOCK_FIVE"]:
        return BLOCK_FOUR
    elif shape == SHAPES["FOUR"]:
        return THREE
    elif shape == SHAPES["FOUR_FOUR"]:
        return THREE
    elif shape == SHAPES["FOUR_THREE"]:
        return THREE
    elif shape == SHAPES["BLOCK_FOUR"]:
        return BLOCK_THREE
    elif shape == SHAPES["THREE"]:
        return TWO
    elif shape == SHAPES["THREE_THREE"]:
        return THREE_THREE / 10
    elif shape == SHAPES["BLOCK_THREE"]:
        return BLOCK_TWO
    elif shape == SHAPES["TWO"]:
        return ONE
    elif shape == SHAPES["TWO_TWO"]:
        return TWO_TWO / 10
    else:
        return 0


def direction2index(ox: int, oy: int) -> int:
    """
    将方向向量转换为方向序号
    Keyword arguments:
    ox -- 行方向偏移
    oy -- 列方向偏移
    Return arguments:
    int -- 方向序号
    """
    if ox == 0:
        return 0
    if oy == 0:
        return 1
    if ox == oy:
        return 2
    return 3


def position2coordinate(position: int, size: int) -> list[int]:
    """
    将位置序号转换为 [行号, 列号]
    Keyword arguments:
    position -- 位置序号
    size -- 棋盘边长
    Return arguments:
    list -- [行号, 列号]
    """
    return [position // size, position % size]


def coordinate2position(x: int, y: int, size: int) -> int:
    """
    将行号与列号转换为位置序号
    Keyword arguments:
    x -- 行号
    y -- 列号
    size -- 棋盘边长
    Return arguments:
    int -- 位置序号
    """
    return x * size + y


def is_line(a: int, b: int, size: int) -> bool:
    """
    判断两个位置是否在同一行、同一列或同一斜线上，且距离小于配置的 in_line_distance
    Keyword arguments:
    a -- 位置序号
    b -- 位置序号
    size -- 棋盘边长
    Return arguments:
    bool -- 是否满足
    """
    max_distance = config["in_line_distance"]
    x1, y1 = position2coordinate(a, size)
    x2, y2 = position2coordinate(b, size)
    return (
        (x1 == x2 and abs(y1 - y2) < max_distance)
        or (y1 == y2 and abs(x1 - x2) < max_distance)
        or (abs(x1 - x2) == abs(y1 - y2) and abs(x1 - x2) < max_distance)
    )


def has_in_line(p: int, arr: list[int], size: int) -> bool:
    """
    判断列表里是否有位置与指定位置满足 is_line
    Keyword arguments:
    p -- 指定位置序号
    arr -- 位置序号列表
    size -- 棋盘边长
    Return arguments:
    bool -- 是否有满足的位置
    """
    for i in range(len(arr)):
        if is_line(p, arr[i], size):
            return True
    return False


def count_shape(
    board: np.ndarray, x: int, y: int, offsetX: int, offsetY: int, role: int
) -> dict[str, int]:
    """
    沿指定方向统计某点一侧的棋子与空位
    Keyword arguments:
    board -- 带边界的评估棋盘
    x -- 行号
    y -- 列号
    offsetX -- 行方向偏移
    offsetY -- 列方向偏移
    role -- 落子方，1 或 -1
    Return arguments:
    dict -- 键为 self_count、total_length、no_empty_self_count、one_empty_self_count、inner_empty_count、
    side_empty_count 的计数
    """
    opponent = -role

    inner_empty_count = 0
    temp_empty_count = 0
    self_count = 0
    total_length = 0

    side_empty_count = 0
    no_empty_self_count = 0
    one_empty_self_count = 0

    for i in range(1, 6):
        nx, ny = x + i * offsetX + 1, y + i * offsetY + 1
        current_role = board[nx][ny]
        if current_role == 2 or current_role == opponent:
            break
        if current_role == role:
            self_count += 1
            side_empty_count = 0
            if temp_empty_count:
                inner_empty_count += temp_empty_count
                temp_empty_count = 0
            if inner_empty_count == 0:
                no_empty_self_count += 1
                one_empty_self_count += 1
            elif inner_empty_count == 1:
                one_empty_self_count += 1
        total_length += 1
        if current_role == 0:
            temp_empty_count += 1
            side_empty_count += 1
        if side_empty_count >= 2:
            break
    if not inner_empty_count:
        one_empty_self_count = 0
    return {
        "self_count": self_count,
        "total_length": total_length,
        "no_empty_self_count": no_empty_self_count,
        "one_empty_self_count": one_empty_self_count,
        "inner_empty_count": inner_empty_count,
        "side_empty_count": side_empty_count,
    }


def get_shape_fast(
    board: np.ndarray, x: int, y: int, offsetX: int, offsetY: int, role: int
) -> list[int]:
    """
    判断某点沿指定方向的形状
    Keyword arguments:
    board -- 带边界的评估棋盘
    x -- 行号
    y -- 列号
    offsetX -- 行方向偏移
    offsetY -- 列方向偏移
    role -- 落子方，1 或 -1
    Return arguments:
    list -- [形状, self_count]
    """
    if (
        board[x + offsetX + 1][y + offsetY + 1] == 0
        and board[x - offsetX + 1][y - offsetY + 1] == 0
        and board[x + 2 * offsetX + 1][y + 2 * offsetY + 1] == 0
        and board[x - 2 * offsetX + 1][y - 2 * offsetY + 1] == 0
    ):
        return [SHAPES["NONE"], 1]

    self_count = 1
    total_length = 1
    shape = SHAPES["NONE"]

    left_empty = 0
    right_empty = 0
    no_empty_self_count = 1
    one_empty_self_count = 1

    left = count_shape(board, x, y, -offsetX, -offsetY, role)
    right = count_shape(board, x, y, offsetX, offsetY, role)

    self_count = left["self_count"] + right["self_count"] + 1
    total_length = left["total_length"] + right["total_length"] + 1
    no_empty_self_count = (
        left["no_empty_self_count"] + right["no_empty_self_count"] + 1
    )
    one_empty_self_count = (
        max(
            left["one_empty_self_count"] + right["no_empty_self_count"],
            left["no_empty_self_count"] + right["one_empty_self_count"],
        )
        + 1
    )
    right_empty = right["side_empty_count"]
    left_empty = left["side_empty_count"]

    if total_length < 5:
        return [shape, self_count]
    if no_empty_self_count >= 5:
        if right_empty > 0 and left_empty > 0:
            return [SHAPES["FIVE"], self_count]
        else:
            return [SHAPES["BLOCK_FIVE"], self_count]
    if no_empty_self_count == 4:
        if (
            right_empty >= 1
            or right["one_empty_self_count"] > right["no_empty_self_count"]
        ) and (
            left_empty >= 1
            or left["one_empty_self_count"] > left["no_empty_self_count"]
        ):
            return [SHAPES["FOUR"], self_count]
        elif not (right_empty == 0 and left_empty == 0):
            return [SHAPES["BLOCK_FOUR"], self_count]
    if one_empty_self_count == 4:
        return [SHAPES["BLOCK_FOUR"], self_count]
    if no_empty_self_count == 3:
        if (right_empty >= 2 and left_empty >= 1) or (
            right_empty >= 1 and left_empty >= 2
        ):
            return [SHAPES["THREE"], self_count]
        else:
            return [SHAPES["BLOCK_THREE"], self_count]
    if one_empty_self_count == 3:
        if right_empty >= 1 and left_empty >= 1:
            return [SHAPES["THREE"], self_count]
        else:
            return [SHAPES["BLOCK_THREE"], self_count]
    if (
        no_empty_self_count == 2 or one_empty_self_count == 2
    ) and total_length > 5:
        shape = SHAPES["TWO"]

    return [shape, self_count]


def is_five(shape: int) -> bool:
    """
    判断形状是否为 FIVE 或 BLOCK_FIVE
    Keyword arguments:
    shape -- 形状编号
    Return arguments:
    bool -- 是否为其中之一
    """
    return shape == SHAPES["FIVE"] or shape == SHAPES["BLOCK_FIVE"]


def is_four(shape: int) -> bool:
    """
    判断形状是否为 FOUR 或 BLOCK_FOUR
    Keyword arguments:
    shape -- 形状编号
    Return arguments:
    bool -- 是否为其中之一
    """
    return shape == SHAPES["FOUR"] or shape == SHAPES["BLOCK_FOUR"]


def get_all_shapes_of_point(
    shape_cache: Mapping[int, Mapping[int | None, np.ndarray]],
    x: int,
    y: int,
    role: int,
) -> list[np.integer]:
    """
    收集某点在四个方向上大于 0 的形状
    Keyword arguments:
    shape_cache -- 形状缓存，shape_cache[角色][方向][行][列]
    x -- 行号
    y -- 列号
    role -- 1 或 -1，为假值时取双方
    Return arguments:
    list -- 形状编号列表
    """
    roles = [role] if role else [1, -1]
    result = []
    for r in roles:
        for d in range(4):
            shape = shape_cache[r][d][x][y]
            if shape > 0:
                result.append(shape)
    return result
