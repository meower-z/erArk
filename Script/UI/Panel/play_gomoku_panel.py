"""五子棋面板模块，负责难度与先后手菜单、棋盘绘制、落子与结算。"""

from __future__ import annotations

from types import FunctionType
from typing import NoReturn

from Script.Config import game_config
from Script.Core import constant, flow_handle, get_text, io_init, py_cmd
from Script.Modules.domains import abilities, activity, identity, modes
from Script.Modules.gameplay_resolution import gomoku_board, gomoku_search
from Script.Modules.tk_ui import player_pick
from Script.UI.Moudle import draw, view

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1


class GomokuPanel:
    """
    五子棋面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.board_draw = [["┼" for _ in range(15)] for _ in range(15)]
        """ 棋盘绘制 """
        self.selected_row = -1
        """ 选中的行 """
        self.selected_col = -1
        """ 选中的列 """
        self.current_player = "O"
        """ 当前玩家 """
        self.game_over = False
        """ 游戏是否结束 """
        self.list1: list[tuple[int, int]] = []
        self.list2: list[tuple[int, int]] = []
        self.next_point = [0, 0]
        self.DEPTH = 2
        self.last_player_move: tuple[int, int] | None = None
        self.last_ai_move: tuple[int, int] | None = None

        self.pl_character_data = identity.of(0)
        self.target_character_data = identity.of(activity.target(0))

        self.choose_ai_difficulty()

        self.board_class = gomoku_board.Gomoku_Board(player_pick.ui_random)
        """当前对局使用的五子棋棋盘引擎实例。"""
        self.search = gomoku_search.GomokuSearch(self.board_class)
        """绑定当前棋盘的五子棋搜索引擎实例。"""

    def choose_ai_difficulty(self) -> None:
        """选择AI难度"""
        line_draw = draw.LineDraw("-", self.width)
        line_draw.draw()
        line_feed.draw()
        target_ability_lv = abilities.ability(self.target_character_data.cid)[
            45
        ]

        while 1:
            return_list = []
            low_button = draw.CenterButton(
                _("[低难度，计算速度快]"),
                _("低难度"),
                self.width // 3,
                cmd_func=self.set_ai_difficulty,
                args=(2,),
            )
            low_button.draw()
            return_list.append(low_button.return_text)

            if target_ability_lv >= 4 or modes.debug():
                medium_button = draw.CenterButton(
                    _("[中难度，计算速度中等]"),
                    _("中难度"),
                    self.width // 3,
                    cmd_func=self.set_ai_difficulty,
                    args=(4,),
                )
                medium_button.draw()
                return_list.append(medium_button.return_text)
            else:
                info_draw = draw.CenterDraw()
                info_draw.text = _(
                    "[中难度 - 需要{0}的{1}达到4级]".format(
                        self.target_character_data.name,
                        game_config.config_ability[45].name,
                    )
                )
                info_draw.width = self.width // 3
                info_draw.draw()

            if target_ability_lv >= 6 or modes.debug():
                high_button = draw.CenterButton(
                    _("[高难度，计算速度慢]"),
                    _("高难度"),
                    self.width // 3,
                    cmd_func=self.set_ai_difficulty,
                    args=(6,),
                )
                high_button.draw()
                return_list.append(high_button.return_text)
            else:
                info_draw = draw.CenterDraw()
                info_draw.text = _(
                    "[高难度 - 需要{0}的{1}达到6级]".format(
                        self.target_character_data.name,
                        game_config.config_ability[45].name,
                    )
                )
                info_draw.width = self.width // 3
                info_draw.draw()

            line_feed.draw()
            back_button = draw.CenterButton(_("[返回]"), _("返回"), self.width)
            back_button.draw()
            return_list.append(back_button.return_text)
            line_feed.draw()

            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_button.return_text:
                player_pick.back()
            if yrn in return_list:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def set_ai_difficulty(self, depth: int) -> None:
        """设置AI难度"""
        self.DEPTH = depth

    def draw(self) -> None:
        """绘制对象"""
        title_draw = draw.TitleLineDraw(_("五子棋"), self.width)
        title_draw.draw()
        py_cmd.clr_cmd()

        self.choose_first_player()

        while 1:
            return_list = []
            line_draw = draw.LineDraw("-", self.width)
            line_draw.draw()

            empty_col = "    "
            empty_draw = draw.NormalDraw()
            empty_draw.text = empty_col
            empty_draw.width = 4
            empty_draw.draw()
            for col in range(15):
                col_button = draw.CenterButton(
                    f"[{col:2}]",
                    f"col_{col}",
                    4,
                    cmd_func=self.select_col,
                    args=(col,),
                )
                if self.selected_col == col:
                    col_button = draw.CenterButton(
                        f"[{col:2}]",
                        f"col_{col}",
                        4,
                        cmd_func=self.select_col,
                        args=(col),
                        normal_style="gold_enrod",
                    )
                col_button.draw()
                return_list.append(col_button.return_text)
            line_feed.draw()

            for row in range(15):
                row_button = draw.LeftButton(
                    f"[{row:2}]",
                    f"row_{row}",
                    4,
                    cmd_func=self.select_row,
                    args=(row,),
                )
                if self.selected_row == row:
                    row_button = draw.LeftButton(
                        f"[{row:2}]",
                        f"row_{row}",
                        4,
                        cmd_func=self.select_row,
                        args=(row),
                        normal_style="gold_enrod",
                    )
                row_button.draw()
                return_list.append(row_button.return_text)

                row_cells = ""

                row_draw = draw.NormalDraw()
                for col in range(15):
                    cell = self.board_draw[row][col]
                    if self.selected_col == col and self.selected_row == row:
                        row_cells += "-[O]"
                    elif self.last_player_move == (
                        row,
                        col,
                    ) or self.last_ai_move == (
                        row,
                        col,
                    ):
                        row_cells += f"-'{cell}-"
                    else:
                        row_cells += f"--{cell}-"
                row_draw.text = row_cells
                row_draw.width = self.width - 4
                row_draw.draw()
                line_feed.draw()

            line_feed.draw()
            if (
                not self.game_over
                and self.selected_row != -1
                and self.selected_col != -1
            ):
                confirm_button = draw.CenterButton(
                    _("[确定]"),
                    _("确定"),
                    self.width // 2,
                    cmd_func=self.place_piece,
                )
                confirm_button.draw()
                return_list.append(confirm_button.return_text)

            if self.game_over:
                line_feed.draw()
                line_feed.draw()
                winner = 0 if self.current_player == "O" else 1
                winner_name = (
                    self.pl_character_data.name
                    if winner == 0
                    else self.target_character_data.name
                )
                win_draw = draw.WaitDraw()
                win_draw.text = _("{0} 获胜!\n\n\n").format(winner_name)
                win_draw.width = self.width
                win_draw.draw()
                self.end_settle(winner)

            back_draw = draw.CenterButton(
                _("[结束游戏]"), _("结束游戏"), self.width // 2
            )
            back_draw.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def end_settle(self, winner: int) -> NoReturn:
        """
        游戏结束：定下胜或负的行为，游戏类型与难度在行动开始时写进玩家的行为数据
        Keyword arguments:
        winner -- 0 玩家胜，1 交互对象胜
        """

        from Script.System.Instruct_System import handle_instruct

        behavior_id = (
            constant.Behavior.PL_WIN_IN_BOARD_GAME
            if winner == 0
            else constant.Behavior.PL_LOSE_IN_BOARD_GAME
        )
        handle_instruct.chara_handle_instruct_common_settle(
            behavior_id,
            force_taget_wait=True,
            fields={
                "behavior.board_game_type": 1,
                "behavior.board_game_ai_difficulty": self.DEPTH // 2,
            },
        )

    def choose_first_player(self) -> None:
        """选择先后手"""
        line_feed.draw()
        while 1:
            return_list = []
            first_button = draw.CenterButton(
                _("[玩家先手]"),
                _("玩家先手"),
                self.width // 2,
                cmd_func=self.set_first_player,
                args=("player",),
            )
            first_button.draw()
            return_list.append(first_button.return_text)

            second_button = draw.CenterButton(
                _("[AI先手]"),
                _("AI先手"),
                self.width // 2,
                cmd_func=self.set_first_player,
                args=("ai",),
            )
            second_button.draw()
            return_list.append(second_button.return_text)
            line_feed.draw()
            back_button = draw.CenterButton(_("[返回]"), _("返回"), self.width)
            back_button.draw()
            return_list.append(back_button.return_text)

            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_button.return_text:
                player_pick.back()
            if yrn in return_list:
                break

    def set_first_player(self, first_player: str) -> None:
        """设置先后手"""
        if first_player == "player":
            self.current_player = "O"
        else:
            self.current_player = "X"
            self.board_draw[7][7] = self.current_player
            self.list1.append((7, 7))
            self.last_ai_move = (7, 7)
            self.current_player = "O"

    def select_row(self, row: int) -> None:
        """选择行"""
        if self.selected_row == row:
            self.selected_row = -1
        else:
            self.selected_row = row

    def select_col(self, col: int) -> None:
        """选择列"""
        if self.selected_col == col:
            self.selected_col = -1
        else:
            self.selected_col = col

    def place_piece(self) -> None:
        """放置棋子"""
        if self.board_draw[self.selected_row][self.selected_col] == "┼":
            piece_type = 1 if self.current_player == "O" else -1
            self.board_draw[self.selected_row][
                self.selected_col
            ] = self.current_player
            self.list2.append((self.selected_row, self.selected_col))
            self.last_player_move = (self.selected_row, self.selected_col)
            self.board_class.put(
                self.selected_row, self.selected_col, piece_type
            )
            if self.check_winner(self.list2):
                self.game_over = True
            else:
                self.current_player = "X"
                self.selected_row = -1
                self.selected_col = -1
                info_draw = draw.NormalDraw()
                info_draw.text = _(
                    "\n{0}思考中...\n".format(self.target_character_data.name)
                )
                info_draw.width = self.width
                info_draw.draw()
                io_init.flush()
                self.ai_move()

    def ai_move(self) -> None:
        """AI 使用算法选择棋子位置"""
        x, y = self.ai()
        self.board_draw[x][y] = self.current_player
        self.list1.append((x, y))
        self.last_ai_move = (x, y)
        piece_type = 1 if self.current_player == "O" else -1
        self.board_class.put(x, y, piece_type)

        if self.check_winner(self.list1):
            self.game_over = True
        else:
            self.current_player = "O"

    def check_winner(self, lst: list[tuple[int, int]]) -> bool:
        """检查是否有玩家获胜"""
        return gomoku_board.check_winner(
            lst, gomoku_board.COLUMN, gomoku_board.ROW
        )

    def ai(self) -> tuple[int, int]:
        """AI决策，返回下一步位置"""
        ai_role = 1 if self.current_player == "O" else -1
        _, move, _ = self.search.minmax(ai_role, depth=self.DEPTH)
        self.next_point[0], self.next_point[1] = move

        return self.next_point[0], self.next_point[1]
