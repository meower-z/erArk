"""
五子棋搜索（gomoku_search）
===========================
提供深度阈值 only_three_threshold 与极小极大算杀类 GomokuSearch。
本模块不执行界面绘制，不导入 Script.UI、Script.Settle 或 Tk。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from Script.Modules.gameplay_resolution.gomoku_cache import Gomoku_Cache
from Script.Modules.gameplay_resolution.gomoku_shapes import FIVE, MAX

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from Script.Modules.gameplay_resolution.gomoku_board import Gomoku_Board

only_three_threshold = 6


class GomokuSearch:
    """持有共享置换表并对绑定棋盘执行极小极大与算杀搜索的引擎。"""

    def __init__(self, board: Gomoku_Board) -> None:
        """
        绑定棋盘并创建共享置换表与搜索闭包
        Keyword arguments:
        board -- 搜索目标棋盘对象
        """
        self._minmax = self.factory()
        self.vct = self.factory(True)
        self.gomoku_cache = Gomoku_Cache()
        self.board_class = board

    def factory(
        self, only_three: bool = False, only_four: bool = False
    ) -> Callable[..., list[Any]]:
        """
        生成搜索函数
        Keyword arguments:
        only_three -- 搜索选点用的 only_three 开关 (default False)
        only_four -- 搜索选点用的 only_four 开关 (default False)
        Return arguments:
        function -- 搜索函数 helper，返回 [分数, 落子或 None, 路径]
        """

        def helper(
            board: Gomoku_Board,
            role: int,
            depth: int,
            c_depth: int = 0,
            path: list[tuple[int, int]] | None = None,
            alpha: float = -MAX,
            beta: float = MAX,
        ) -> list[Any]:
            board = self.board_class
            if path is None:
                path = []
            if c_depth >= depth or board.is_game_over():
                return [board.evaluate(role), None, path[:]]
            hash_value = board.hash()
            prev = self.gomoku_cache.get(hash_value)
            if prev and prev["role"] == role:
                if (
                    (
                        abs(prev["value"]) >= FIVE
                        or prev["depth"] >= depth - c_depth
                    )
                    and prev["only_three"] == only_three
                    and prev["only_four"] == only_four
                ):
                    return [prev["value"], prev["move"], path + prev["path"]]
            value = -MAX
            move = None
            best_path = path[:]
            best_depth = 0
            points = board.get_valuable_moves(
                role,
                c_depth,
                only_three or c_depth > only_three_threshold,
                only_four,
            )
            if not points:
                return [board.evaluate(role), None, path[:]]
            for d in range(c_depth + 1, depth + 1):
                if d % 2 != 0:
                    continue
                break_all = False
                for point in points:
                    board.put(point[0], point[1], role)
                    new_path = path + [point]
                    current_value, _current_move, current_path = helper(
                        board, -role, d, c_depth + 1, new_path, -beta, -alpha
                    )
                    current_value = -current_value
                    board.undo()
                    if current_value >= FIVE or d == depth:
                        if (current_value > value) or (
                            current_value <= -FIVE
                            and value <= -FIVE
                            and len(current_path) > best_depth
                        ):
                            value = current_value
                            move = point
                            best_path = current_path
                            best_depth = len(current_path)
                    alpha = max(alpha, value)
                    if alpha >= FIVE:
                        break_all = True
                        break
                    if alpha >= beta:
                        break
                if break_all:
                    break
            if (c_depth < only_three_threshold or only_three or only_four) and (
                not prev or prev["depth"] < depth - c_depth
            ):
                self.gomoku_cache.put(
                    hash_value,
                    {
                        "depth": depth - c_depth,
                        "value": value,
                        "move": move,
                        "role": role,
                        "path": best_path[c_depth:],
                        "only_three": only_three,
                        "only_four": only_four,
                    },
                )
            return [value, move, best_path]

        return helper

    def minmax(
        self,
        role: int,
        depth: int = 4,
        enable_vct: bool = True,
    ) -> list[Any]:
        """
        为指定行棋方搜索推荐落子并返回分数与路径
        Keyword arguments:
        role -- 当前搜索视角，1 或 -1
        depth -- 常规搜索深度 (default 4)
        enable_vct -- 是否先执行连续活三算杀与复查 (default True)
        Return arguments:
        list -- [分数, 落子坐标或 None, 路径列表]
        """
        board = self.board_class
        if enable_vct:
            vct_depth = depth + 4
            value, move, best_path = self.vct(board, role, vct_depth)
            if value >= FIVE:
                return [value, move, best_path]
            value, move, best_path = self._minmax(board, role, depth)
            if move is not None:
                board.put(move[0], move[1], role)
                value2, move2, best_path2 = self.vct(
                    board.reverse(), role, vct_depth
                )
                board.undo()
                if (
                    value < FIVE
                    and value2 == FIVE
                    and len(best_path2) > len(best_path)
                ):
                    _value3, _move3, best_path3 = self.vct(
                        board.reverse(), role, vct_depth
                    )
                    if len(best_path2) <= len(best_path3):
                        return [
                            value,
                            move2,
                            best_path2,
                        ]
            if move is None:
                valid_moves = board.get_valid_moves()
                if valid_moves:
                    move = valid_moves[0]
            return [value, move, best_path]
        else:
            value, move, best_path = self._minmax(board, role, depth)
            if move is None:
                print("因为没有找到合适的移动，返回一个默认的有效移动")
                valid_moves = board.get_valid_moves()
                if valid_moves:
                    move = valid_moves[0]
            return [value, move, best_path]
