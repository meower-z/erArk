"""
五子棋引擎测试
==============
覆盖棋盘规则、增量评估、候选选点、缓存淘汰、搜索与无界面隔离。
"""

import random
from typing import Any, cast
from unittest import mock

from Script.Modules.gameplay_resolution import gomoku_shapes
from Script.Modules.gameplay_resolution.gomoku_board import (
    COLUMN,
    ROW,
    Gomoku_Board,
    check_winner,
)
from Script.Modules.gameplay_resolution.gomoku_cache import Gomoku_Cache
from Script.Modules.gameplay_resolution.gomoku_search import GomokuSearch
from Script.Modules.gameplay_resolution.gomoku_shapes import FIVE, FOUR
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import run_ui_free

LINES = {
    "row": [(3, 10 + k) for k in range(5)],
    "column": [(10 + k, 2) for k in range(5)],
    "diagonal": [(k, k) for k in range(5)],
    "anti_diagonal": [(10 + k, 4 - k) for k in range(5)],
}
"""四个方向各五连坐标样本字典。"""


def board_with(stones: list[tuple[int, int, int]]) -> Gomoku_Board:
    """用固定种子构造棋盘并依次落下给定棋子列表。"""
    board = Gomoku_Board(random.Random(0))
    for i, j, role in stones:
        board.put(i, j, role)
    return board


def snapshot(board: Gomoku_Board) -> tuple[object, ...]:
    """返回棋盘矩阵、历史记录与哈希值组成的状态快照。"""
    return (board.board.tolist(), list(board.history), board.hash())


class BoardRulesTest(FastTestCase):
    """验证棋盘落子、悔棋、哈希、胜负与翻转规则。"""

    def test_put_rejects_taken_and_off_board_cells(self) -> None:
        """验证已有棋子或越界坐标落子被拒绝且状态不变。"""
        board = board_with([(7, 7, 1)])
        before = snapshot(board)
        for i, j in ((7, 7), (15, 0), (0, 15), (-1, 3)):
            with self.subTest(cell=(i, j)):
                self.assertFalse(board.put(i, j, -1))
                self.assertEqual(snapshot(board), before)

    def test_put_and_undo_switch_turns_and_restore_hash(self) -> None:
        """验证落子与悔棋切换行棋方并还原哈希，空历史悔棋返回 False。"""
        board = Gomoku_Board(random.Random(0), first_role=-1)
        empty = snapshot(board)
        self.assertTrue(board.put(7, 7))
        self.assertEqual((board.board[7, 7], board.role), (-1, 1))
        self.assertNotEqual(board.hash(), empty[2])
        self.assertTrue(board.undo())
        self.assertEqual((snapshot(board), board.role), (empty, -1))
        self.assertFalse(board.undo())

    def test_hash_follows_the_seeded_source_and_the_colour(self) -> None:
        """验证同种子同棋色哈希一致，异色哈希不同。"""
        black, again, white = (
            board_with([(4, 4, 1)]),
            board_with([(4, 4, 1)]),
            board_with([(4, 4, -1)]),
        )
        self.assertEqual(black.hash(), again.hash())
        self.assertNotEqual(black.hash(), white.hash())

    def test_five_in_each_direction_wins(self) -> None:
        """验证四向四连不胜、五连判胜并给出正负 FIVE 分值。"""
        for name, cells in LINES.items():
            with self.subTest(line=name):
                four = board_with([(i, j, -1) for i, j in cells[:4]])
                self.assertEqual(four.get_winner(), 0)
                self.assertFalse(four.is_game_over())
                five = board_with([(i, j, -1) for i, j in cells])
                self.assertEqual(five.get_winner(), -1)
                self.assertTrue(five.is_game_over())
                self.assertEqual(five.evaluate(1), -FIVE)
                self.assertEqual(five.evaluate(-1), FIVE)

    def test_full_board_without_five_is_over(self) -> None:
        """验证无五连满盘判为终局，悔棋一步后恢复未终局。"""
        stones = [
            (i, j, 1 if (j + 2 * i) % 4 < 2 else -1)
            for i in range(15)
            for j in range(15)
        ]
        board = board_with(stones)
        self.assertEqual(board.get_winner(), 0)
        self.assertTrue(board.is_game_over())
        board.undo()
        self.assertFalse(board.is_game_over())

    def test_reverse_swaps_every_stone_colour(self) -> None:
        """验证 reverse 互换棋色与先手方且不改动原棋盘。"""
        board = board_with([(7, 7, 1), (7, 8, -1), (6, 6, 1)])
        before = snapshot(board)
        flipped = board.reverse()
        self.assertEqual(flipped.board.tolist(), (-board.board).tolist())
        self.assertEqual(flipped.first_role, -board.first_role)
        self.assertEqual(snapshot(board), before)

    def test_check_winner_reads_a_list_of_stones(self) -> None:
        """验证 check_winner 识别四向五连并拒绝四连与断连。"""
        for name, cells in LINES.items():
            with self.subTest(line=name):
                self.assertTrue(check_winner(cells, COLUMN, ROW))
                self.assertFalse(check_winner(cells[:4], COLUMN, ROW))
                gap = cells[:2] + cells[3:] + [(14, 14)]
                self.assertFalse(check_winner(gap, COLUMN, ROW))


class EvaluationTest(FastTestCase):
    """验证局面评估的方向性、活四高分与悔棋分数恢复。"""

    def test_score_favours_the_side_with_the_stronger_shape(self) -> None:
        """验证己方活三得分为正，对手视角得分互为相反数。"""
        board = board_with([(7, 6, 1), (7, 7, 1), (7, 8, 1), (0, 0, -1)])
        self.assertGreater(board.evaluate(1), 0)
        self.assertEqual(board.evaluate(-1), -board.evaluate(1))

    def test_an_open_four_outscores_a_four_point(self) -> None:
        """验证己方活四局面分高于单个成五点对应的 FOUR 分值。"""
        board = board_with([(7, c, 1) for c in range(4, 8)] + [(0, 0, -1)])
        self.assertGreater(board.evaluate(1), FOUR)

    def test_undo_restores_the_score(self) -> None:
        """验证落子后悔棋能恢复评估器的局面分。"""
        board = board_with([(7, 7, 1), (8, 8, -1)])
        before = board.evaluator.evaluate(1)
        board.put(7, 8, 1)
        self.assertNotEqual(board.evaluator.evaluate(1), before)
        board.undo()
        self.assertEqual(board.evaluator.evaluate(1), before)


class MoveGenerationTest(FastTestCase):
    """验证候选落子的中心点、五连优先、四连过滤与限线选点。"""

    def test_empty_board_offers_the_centre(self) -> None:
        """验证空棋盘只返回中心点 (7, 7)。"""
        self.assertEqual(board_with([]).get_valuable_moves(1), [(7, 7)])

    def test_a_five_point_beats_every_other_candidate(self) -> None:
        """验证活四的两个成五点独占返回的候选列表。"""
        own = [(7, c, 1) for c in range(4, 8)]
        board = board_with(own + [(0, 0, -1), (0, 2, -1), (14, 14, -1)])
        self.assertEqual(sorted(board.get_valuable_moves(1)), [(7, 3), (7, 8)])

    def test_the_opponents_five_point_is_offered(self) -> None:
        """验证对手成五点会作为唯一候选点返回。"""
        theirs = [(7, c, -1) for c in range(4, 8)] + [(7, 3, 1)]
        board = board_with(theirs + [(0, 0, 1), (14, 14, 1)])
        self.assertEqual(board.get_valuable_moves(1), [(7, 8)])

    def test_four_only_search_keeps_four_points(self) -> None:
        """
        验证 only_four=True 恰好返回活三所在行的四个成四点。
        常规选点同时包含空天元 (7, 7)。
        """
        own = [(3, 5, 1), (3, 6, 1), (3, 7, 1)]
        board = board_with(own + [(0, 0, -1), (0, 2, -1), (14, 14, -1)])
        fours = board.get_valuable_moves(1, only_four=True)
        self.assertEqual(sorted(fours), [(3, 3), (3, 4), (3, 8), (3, 9)])
        self.assertIn((7, 7), board.get_valuable_moves(1))

    def test_line_limited_candidates_stay_near_the_latest_moves(self) -> None:
        """
        验证默认选点返回远端两个成五点。
        开启 only_in_line 后返回非空候选且不含这两个成五点。
        """
        own = [(7, c, 1) for c in range(4, 8)]
        late = [(0, 0, -1), (0, 1, -1), (14, 14, 1), (14, 13, 1)]
        self.assertEqual(
            sorted(board_with(own + late).get_valuable_moves(1)),
            [(7, 3), (7, 8)],
        )
        with mock.patch.dict(gomoku_shapes.config, {"only_in_line": True}):
            near = board_with(own + late).get_valuable_moves(1)
        self.assertTrue(near)
        self.assertTrue(set(near).isdisjoint({(7, 3), (7, 8)}))


class CacheTest(FastTestCase):
    """验证定容缓存的先进先出淘汰与开关关闭行为。"""

    def test_every_write_to_a_full_cache_drops_its_oldest_key(self) -> None:
        """验证满容缓存每次写入均淘汰最早进入的键。"""
        cache = Gomoku_Cache(capacity=2)
        cache.put(1, "a")
        cache.put(2, "b")
        cache.put(1, "c")
        cache.put(3, "d")
        self.assertEqual(
            [cache.get(1), cache.get(2), cache.get(3)], ["c", None, "d"]
        )

    def test_switched_off_cache_stores_nothing(self) -> None:
        """验证关闭缓存开关时读写返回 False 且不存条目。"""
        cache = Gomoku_Cache()
        with mock.patch.dict(gomoku_shapes.config, {"enable_cache": False}):
            self.assertIs(cache.put(1, "a"), False)
            self.assertIs(cache.get(1), False)
        self.assertIsNone(cache.get(1))


class SearchTest(FastTestCase):
    """验证搜索器的冲五、防守、活三算杀与配置分支。"""

    def best(
        self, stones: list[tuple[int, int, int]], role: int
    ) -> tuple[Any, Any]:
        """以深度 2 运行搜索并断言搜索前后棋盘状态不变。"""
        board = board_with(stones)
        before = snapshot(board)
        value, move, _path = GomokuSearch(board).minmax(role, depth=2)
        self.assertEqual(snapshot(board), before)
        return value, move

    def test_takes_its_own_five(self) -> None:
        """验证搜索器选择己方成五点 (7, 8) 并返回必胜分。"""
        own = [(7, c, -1) for c in range(4, 8)] + [(7, 3, 1)]
        value, move = self.best(own + [(0, 0, 1), (14, 14, 1), (14, 0, 1)], -1)
        self.assertEqual((move, value >= FIVE), ((7, 8), True))

    def test_blocks_the_opponents_five(self) -> None:
        """验证搜索器优先堵住对手的成五点 (8, 7)。"""
        theirs = [(c, 7, 1) for c in range(4, 8)] + [(3, 7, -1)]
        value, move = self.best(theirs + [(0, 0, -1), (14, 14, -1)], -1)
        self.assertEqual(move, (8, 7))

    def test_open_three_is_a_forced_win(self) -> None:
        """验证己方活三返回必胜分且落子在活三所在行。"""
        own = [(7, 5, -1), (7, 6, -1), (7, 7, -1)]
        value, move = self.best(own + [(0, 0, 1), (0, 14, 1), (14, 14, 1)], -1)
        self.assertGreaterEqual(value, FIVE)
        self.assertIn(move, {(7, 3), (7, 4), (7, 8), (7, 9)})

    def test_search_without_vct(self) -> None:
        """验证关闭 enable_vct 开关时仍返回可落子的合法坐标。"""
        board = board_with([(7, 7, 1)])
        _value, move, _path = GomokuSearch(board).minmax(-1, 2, False)
        self.assertTrue(board.put(move[0], move[1], -1))

    def test_line_limited_candidates_still_find_the_five(self) -> None:
        """验证开启 only_in_line 限线选点后仍能找到成五点。"""
        own = [(7, c, -1) for c in range(4, 8)] + [(7, 3, 1)]
        stones = own + [(0, 0, 1), (14, 14, 1), (14, 0, 1)]
        with mock.patch.dict(gomoku_shapes.config, {"only_in_line": True}):
            value, move = self.best(stones, -1)
        self.assertEqual((move, value >= FIVE), ((7, 8), True))


BACKEND_RUN = """
import random
from Script.Modules.gameplay_resolution import gomoku_shapes
from Script.Modules.gameplay_resolution.gomoku_board import (
    COLUMN, ROW, Gomoku_Board, check_winner,
)
from Script.Modules.gameplay_resolution.gomoku_search import GomokuSearch

def play(depth, flags):
    gomoku_shapes.config.update(flags)
    board = Gomoku_Board(random.Random(depth))
    search = GomokuSearch(board)
    moves = []
    for i, j in ((7, 7), (8, 8))[: 4 // depth]:
        board.put(i, j, 1)
        if board.is_game_over():
            break
        _value, move, _path = search.minmax(-1, depth=depth)
        board.put(move[0], move[1], -1)
        moves.append([int(move[0]), int(move[1])])
    flipped = board.reverse()
    mirrored = int(flipped.board.sum()) == -int(board.board.sum())
    return [moves, mirrored, board.put(7, 7, 1)]

payload["plain"] = play(2, {})
payload["no_cache"] = play(2, {"enable_cache": False})
payload["in_line"] = play(2, {"only_in_line": True, "enable_cache": True})
payload["deep"] = play(4, {"only_in_line": False})
payload["valid"] = len(Gomoku_Board(random.Random(1)).get_valid_moves())
payload["winner"] = check_winner([(0, k) for k in range(5)], COLUMN, ROW)
"""
"""在无界面子进程中运行多配置五子棋对局的脚本代码。"""


class BackendIsolationTest(FastTestCase):
    """验证五子棋引擎可在无界面、无结算环境下运行。"""

    def test_engine_runs_without_ui_or_settle(self) -> None:
        """验证无界面子进程运行各配置分支时未触及受限模块。"""
        run = run_ui_free(BACKEND_RUN)
        self.assertEqual((run.attempted, run.loaded), ([], []))
        for key in ("plain", "no_cache", "in_line", "deep"):
            with self.subTest(game=key):
                moves, mirrored, retaken = cast(list[object], run.payload[key])
                self.assertTrue(moves)
                self.assertEqual((mirrored, retaken), (True, False))
        self.assertEqual(run.payload["valid"], 225)
        self.assertIs(run.payload["winner"], True)
