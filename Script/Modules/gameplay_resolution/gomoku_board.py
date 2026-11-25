"""
五子棋棋盘引擎（gomoku_board）
==============================
提供尺寸常量、Gomoku_Board 棋盘类与列表五连判定 check_winner。
本模块不执行界面绘制，不导入 Script.UI、Script.Settle 或 Tk。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from Script.Modules.gameplay_resolution.gomoku_cache import (
    Gomoku_Cache,
    ZobristCache,
)
from Script.Modules.gameplay_resolution.gomoku_evaluate import Evaluate
from Script.Modules.gameplay_resolution.gomoku_moves import get_moves
from Script.Modules.gameplay_resolution.gomoku_shapes import FIVE

if TYPE_CHECKING:
    import random

COLUMN = 15
ROW = 15


class Gomoku_Board:
    """维护棋盘数组、落子历史、哈希、缓存与增量评估的棋盘类。"""

    def __init__(
        self, rng: random.Random, size: int = 15, first_role: int = 1
    ) -> None:
        """
        初始化空棋盘、Zobrist 哈希、结果缓存与增量评估器
        Keyword arguments:
        rng -- 用于生成哈希键的 random.Random 实例
        size -- 棋盘边长 (default 15)
        first_role -- 先手棋子值，1 或 -1 (default 1)
        """
        self.size = size
        self.board = np.zeros((self.size, self.size), dtype=int)
        self.first_role = first_role
        self.role = first_role
        self.history: list[tuple[int, int, int]] = []
        self.zobrist = ZobristCache(self.size, rng)
        self.winner_cache = Gomoku_Cache()
        self.gameover_cache = Gomoku_Cache()
        self.evaluate_cache = Gomoku_Cache()
        self.valuable_moves_cache = Gomoku_Cache()
        self.evaluator = Evaluate(self.size)

    def is_game_over(self) -> bool:
        """
        判断对局是否结束
        Return arguments:
        bool -- 对局是否结束
        """
        hash_value = self.hash()
        if self.gameover_cache.get(hash_value):
            return self.gameover_cache.get(hash_value)
        if self.get_winner() != 0:
            self.gameover_cache.put(hash_value, True)
            return True
        if np.any(self.board == 0):
            self.gameover_cache.put(hash_value, False)
            return False
        self.gameover_cache.put(hash_value, True)
        return True

    def get_winner(self) -> int | np.integer:
        """
        判断获胜方
        Return arguments:
        numpy 整数 | int -- 获胜方的棋子值，无人获胜为 0
        """
        hash_value = self.hash()
        if self.winner_cache.get(hash_value):
            return self.winner_cache.get(hash_value)
        directions = [
            (1, 0),
            (0, 1),
            (1, 1),
            (1, -1),
        ]
        for i in range(self.size):
            for j in range(self.size):
                if self.board[i, j] == 0:
                    continue
                for direction in directions:
                    count = 0
                    while (
                        0 <= i + direction[0] * count < self.size
                        and 0 <= j + direction[1] * count < self.size
                        and self.board[
                            i + direction[0] * count, j + direction[1] * count
                        ]
                        == self.board[i, j]
                    ):
                        count += 1
                    if count >= 5:
                        self.winner_cache.put(hash_value, self.board[i, j])
                        return self.board[i, j]
        self.winner_cache.put(hash_value, 0)
        return 0

    def get_valid_moves(self) -> list[tuple[np.integer, np.integer]]:
        """
        返回棋盘上所有空位
        Return arguments:
        list -- 空位坐标列表
        """
        print("get_valid_moves is deprecated. Use get_valuable_moves instead.")
        return list(zip(*np.where(self.board == 0), strict=False))

    def put(self, i: int, j: int, role: int | None = None) -> bool:
        """
        在指定坐标落子
        Keyword arguments:
        i -- 行号
        j -- 列号
        role -- 落子方，为 None 时用当前行棋方 (default None)
        Return arguments:
        bool -- 是否落子成功
        """
        if role is None:
            role = self.role
        if not (0 <= i < self.size and 0 <= j < self.size):
            print("Invalid move Not Number!", i, j)
            return False
        if self.board[i, j] != 0:
            print("Invalid move!", i, j)
            return False
        self.board[i, j] = role
        self.history.append((i, j, role))
        self.zobrist.toggle_piece(i, j, role)
        self.evaluator.move(i, j, role)
        self.role *= -1
        return True

    def undo(self) -> bool:
        """
        撤销最近一步落子
        Return arguments:
        bool -- 是否撤销成功
        """
        if not self.history:
            print("No moves to undo!")
            return False
        last_move = self.history.pop()
        self.board[last_move[0], last_move[1]] = 0
        self.role = last_move[2]
        self.zobrist.toggle_piece(last_move[0], last_move[1], last_move[2])
        self.evaluator.undo(last_move[0], last_move[1])
        return True

    def get_valuable_moves(
        self,
        role: int,
        depth: int = 0,
        only_three: bool = False,
        only_four: bool = False,
    ) -> list[tuple[int, int]]:
        """
        获取指定行棋方值得搜索的落子点
        Keyword arguments:
        role -- 落子方，1 或 -1
        depth -- 当前搜索深度 (default 0)
        only_three -- 传给评估器 get_moves 的同名开关 (default False)
        only_four -- 传给评估器 get_moves 的同名开关 (default False)
        Return arguments:
        list -- 落子坐标列表
        """
        hash_value = self.hash()
        prev = self.valuable_moves_cache.get(hash_value)
        if (
            prev
            and prev["role"] == role
            and prev["depth"] == depth
            and prev["only_three"] == only_three
            and prev["only_four"] == only_four
        ):
            return prev["moves"]
        moves = get_moves(self.evaluator, role, depth, only_three, only_four)
        if not only_three and not only_four:
            center = self.size // 2
            if self.board[center, center] == 0:
                moves.append((center, center))
        self.valuable_moves_cache.put(
            hash_value,
            {
                "role": role,
                "moves": moves,
                "depth": depth,
                "only_three": only_three,
                "only_four": only_four,
            },
        )
        return moves

    def hash(self) -> int:
        """
        获取当前棋盘的哈希值
        Return arguments:
        int -- 哈希值
        """
        return self.zobrist.get_hash()

    def evaluate(self, role: int) -> int | float | np.integer:
        """
        评估当前局面对指定一方的分数
        Keyword arguments:
        role -- 评估视角，1 或 -1
        Return arguments:
        numpy 整数 -- 局面分数
        """
        hash_value = self.hash()
        prev = self.evaluate_cache.get(hash_value)
        if prev and prev["role"] == role:
            return prev["score"]
        winner = self.get_winner()
        if winner != 0:
            score: int | float | np.integer = FIVE * winner * role
        else:
            score = self.evaluator.evaluate(role)
        self.evaluate_cache.put(hash_value, {"role": role, "score": score})
        return score

    def reverse(self) -> Gomoku_Board:
        """
        生成黑白互换的新棋盘
        Return arguments:
        Gomoku_Board -- 新棋盘对象
        """
        new_board = Gomoku_Board(self.zobrist.rng, self.size, -self.first_role)
        for move in self.history:
            new_board.put(move[0], move[1], -move[2])
        return new_board


def check_winner(list: list[tuple[int, int]], COLUMN: int, ROW: int) -> bool:
    """
    判断棋子坐标列表里是否有五子连珠
    Keyword arguments:
    list -- 一方棋子的坐标 (行, 列) 列表
    COLUMN -- 棋盘尺寸
    ROW -- 棋盘尺寸
    Return arguments:
    bool -- 是否有五子连珠
    """
    for m in range(COLUMN):
        for n in range(ROW):
            if (
                n < ROW - 4
                and (m, n) in list
                and (m, n + 1) in list
                and (m, n + 2) in list
                and (m, n + 3) in list
                and (m, n + 4) in list
            ):
                return True
            elif (
                m < ROW - 4
                and (m, n) in list
                and (m + 1, n) in list
                and (m + 2, n) in list
                and (m + 3, n) in list
                and (m + 4, n) in list
            ):
                return True
            elif (
                m < ROW - 4
                and n < ROW - 4
                and (m, n) in list
                and (m + 1, n + 1) in list
                and (m + 2, n + 2) in list
                and (m + 3, n + 3) in list
                and (m + 4, n + 4) in list
            ):
                return True
            elif (
                m < ROW - 4
                and n > 3
                and (m, n) in list
                and (m + 1, n - 1) in list
                and (m + 2, n - 2) in list
                and (m + 3, n - 3) in list
                and (m + 4, n - 4) in list
            ):
                return True
    return False
