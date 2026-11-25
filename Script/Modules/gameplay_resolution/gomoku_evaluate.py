"""
五子棋局面评估（gomoku_evaluate）
=================================
提供 Evaluate，增量维护带边界棋盘、四向棋型缓存与双方得分表。
本模块不执行界面绘制，不导入 Script.UI、Script.Settle 或 Tk。
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from Script.Modules.gameplay_resolution.gomoku_shapes import (
    ALL_DIRECTIONS,
    SHAPES,
    coordinate2position,
    direction2index,
    get_real_shape_score,
    get_shape_fast,
)


class Evaluate:
    """增量维护带边界棋盘、棋型缓存与双方点位得分表的评估器。"""

    def __init__(self, size: int = 15) -> None:
        """
        初始化局面评估对象
        Keyword arguments:
        size -- 棋盘边长 (default 15)
        """
        self.size = size
        self.board = np.zeros((self.size + 2, self.size + 2), dtype=int)
        self.board[0, :] = self.board[:, 0] = self.board[-1, :] = self.board[
            :, -1
        ] = 2
        self.black_scores = np.zeros((self.size, self.size), dtype=int)
        self.white_scores = np.zeros((self.size, self.size), dtype=int)
        self.init_points()
        self.history: list[tuple[int, int]] = []

    def move(self, x: int, y: int, role: int) -> None:
        """
        在评估棋盘上落子并更新评估数据
        Keyword arguments:
        x -- 行号
        y -- 列号
        role -- 落子方，1 或 -1
        """
        for d in range(4):
            self.shape_cache[role][d][x][y] = 0
            self.shape_cache[-role][d][x][y] = 0
        self.black_scores[x][y] = 0
        self.white_scores[x][y] = 0

        self.board[x + 1, y + 1] = role
        self.update_point(x, y)
        self.history.append((coordinate2position(x, y, self.size), role))

    def undo(self, x: int, y: int) -> None:
        """
        在评估棋盘上撤销某点的落子并更新评估数据
        Keyword arguments:
        x -- 行号
        y -- 列号
        """
        self.board[x + 1, y + 1] = 0
        self.update_point(x, y)
        self.history.pop()

    def init_points(self) -> None:
        """初始化按行棋方与方向索引的二维棋型缓存 shape_cache。"""
        self.shape_cache: defaultdict[
            int, defaultdict[int | None, np.ndarray]
        ] = defaultdict(
            lambda: defaultdict(
                lambda: np.full(
                    (self.size, self.size), SHAPES["NONE"], dtype=int
                )
            )
        )

    def update_point(self, x: int, y: int) -> None:
        """
        重算该点及其周围点位中空位的形状与得分
        Keyword arguments:
        x -- 行号
        y -- 列号
        """
        self.update_single_point(x, y, 1)
        self.update_single_point(x, y, -1)

        for ox, oy in ALL_DIRECTIONS:
            for sign in [
                1,
                -1,
            ]:
                for step in range(1, 6):
                    reach_edge = False
                    for role in [1, -1]:
                        nx, ny = (
                            x + sign * step * ox + 1,
                            y + sign * step * oy + 1,
                        )
                        if self.board[nx, ny] == 2:
                            reach_edge = True
                            break
                        elif self.board[nx, ny] == -role:
                            continue
                        elif self.board[nx, ny] == 0:
                            self.update_single_point(
                                nx - 1, ny - 1, role, (sign * ox, sign * oy)
                            )
                    if reach_edge:
                        break

    def update_single_point(
        self,
        x: int,
        y: int,
        role: int,
        direction: tuple[int, int] | None = None,
    ) -> float | None:
        """
        重算某点对指定一方的形状缓存与得分
        Keyword arguments:
        x -- 行号
        y -- 列号
        role -- 假设落子的一方，1 或 -1
        direction -- 只重算的方向 (ox, oy)，为 None 时为四个方向 (default None)
        Return arguments:
        int | float | None -- 该点得分，该点已有棋子时为 None
        """
        if self.board[x + 1, y + 1] != 0:
            return None

        self.board[x + 1, y + 1] = role

        directions = [direction] if direction else ALL_DIRECTIONS
        shape_cache = self.shape_cache[role]

        for ox, oy in directions:
            shape_cache[direction2index(ox, oy)][x][y] = SHAPES["NONE"]

        score: float = 0
        block_four_count = three_count = two_count = 0
        for int_direction in range(4):
            shape = shape_cache[int_direction][x][y]
            if shape > SHAPES["NONE"]:
                score += get_real_shape_score(shape)
                if shape == SHAPES["BLOCK_FOUR"]:
                    block_four_count += 1
                if shape == SHAPES["THREE"]:
                    three_count += 1
                if shape == SHAPES["TWO"]:
                    two_count += 1

        for ox, oy in directions:
            int_direction = direction2index(ox, oy)
            shape, _self_count = get_shape_fast(self.board, x, y, ox, oy, role)
            if not shape:
                continue
            shape_cache[int_direction][x][y] = shape
            if shape == SHAPES["BLOCK_FOUR"]:
                block_four_count += 1
            if shape == SHAPES["THREE"]:
                three_count += 1
            if shape == SHAPES["TWO"]:
                two_count += 1
            if block_four_count >= 2:
                shape = SHAPES["FOUR_FOUR"]
            elif block_four_count and three_count:
                shape = SHAPES["FOUR_THREE"]
            elif three_count >= 2:
                shape = SHAPES["THREE_THREE"]
            elif two_count >= 2:
                shape = SHAPES["TWO_TWO"]
            score += get_real_shape_score(shape)

        self.board[x + 1, y + 1] = 0

        if role == 1:
            self.black_scores[x][y] = score
        else:
            self.white_scores[x][y] = score

        return score

    def evaluate(self, role: int) -> int | float | np.integer:
        """
        根据双方得分表计算局面分数
        Keyword arguments:
        role -- 评估视角，1 或 -1
        Return arguments:
        numpy 整数 -- 局面分数
        """
        black_score = np.sum(self.black_scores)
        white_score = np.sum(self.white_scores)
        score = (
            black_score - white_score
            if role == 1
            else white_score - black_score
        )
        return score
