"""
图书馆管理面板纯规则服务测试
============================
覆盖已借出书籍列表顺序与催还处理、阅读推荐切换与上限边界、读书会排期与冲突拒绝、
借阅历史持有人与借书卡格式化、面板适配器联动以及无界面独立子进程导入边界。
"""

import datetime
import json
import subprocess
import sys

from Script.Config import game_config
from Script.Kernel import core
from Script.Modules.domains import chara_life, entertainment, library
from Script.Modules.gameplay_resolution import library_panel_service as svc
from Script.Modules.gameplay_resolution import working
from Script.UI.Moudle import draw
from Script.UI.Panel import manage_library
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

BACKEND_RUN = """
import importlib.abc, sys
BLOCKED = ("Script.UI", "Script.Settle",
    "Script.System.Instruct_System.handle_instruct", "Script.Core.flow_handle",
    "Script.Core.io_init", "Script.Frontend", "Script.Modules.tk_ui",
    "tkinter", "_tkinter", "PIL.ImageTk")
attempted = []
def is_blocked(name):
    return any(name == root or name.startswith(root + ".") for root in BLOCKED)
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if is_blocked(fullname):
            attempted.append(fullname)
            raise ImportError(fullname)
        return None
sys.meta_path.insert(0, Blocker())
import contextlib, io, json
from Script.Config import normal_config, game_config
with contextlib.redirect_stdout(io.StringIO()):
    normal_config.init_normal_config()
    game_config.init()
from Script.Kernel import core
from Script.Modules.domains import chara_life, entertainment, identity, library
from Script.Modules.gameplay_resolution import library_panel_service as svc
from Script.Modules.gameplay_resolution import working
book = next(iter(game_config.config_book_type_data[11]))
with working.based_on(core.state()):
    identity.put(identity.Identity(1, name="A"))
    library.set_holder(book, 1)
    chara_life.entertainment_type.set(1, [0, 0])
    chara_life.borrow_book_history.set(1, [{"book_id": book}])
    notice = svc.urge_return(1)
    for type_id in (11, 12, 13, 14):
        svc.toggle_recommend(type_id)
    refusals = []
    entertainment.set_party_day(4, 51)
    for day in (2, 5, 4):
        refusals.append(svc.pick_party_day(day) is not None)
    card = svc.history_card(1)
    out = {
        "lent": [row.holder_id for row in svc.lent_books()],
        "urged": [chara_life.book_return_possibility(1),
            chara_life.entertainment_type(1), "A" in notice],
        "recommended": sorted(library.recommended()),
        "left": svc.recommend_left(),
        "days": [entertainment.party_day(d) for d in range(7)],
        "refusals": refusals,
        "holders": list(svc.history_holders()),
        "card": [card.total_books, card.total_reads, len(card.records)],
        "option": svc.recommend_option(11).picked,
        "rows": len(svc.party_rows()),
    }
out["attempted"] = sorted(set(attempted))
out["loaded"] = sorted(n for n in sys.modules
    if n.startswith(("Script.UI", "Script.Settle")) or is_blocked(n))
print(json.dumps(out))
"""
""" 在拦截界面、结算、流程与窗口模块的子进程中调用 library_panel_service 并输出结果的脚本。 """

NOW = datetime.datetime(2020, 12, 22, 10, 0)
""" 借阅历史格式化测试使用的固定基准时间常量。 """


def first_books(type_id: int, count: int) -> list[int]:
    """
    按存储迭代顺序取指定书籍类型下的前若干本书籍编号。
    Keyword arguments:
    type_id -- int，书籍类型编号
    count -- int，需要截取的书籍数量
    Return arguments:
    list[int] -- 截取得到的书籍编号列表
    """
    return list(game_config.config_book_type_data[type_id])[:count]


class LibraryPanelCase(FastTestCase):
    """图书馆管理面板服务测试基类，初始化玩家与两名测试角色并进入临时状态写缓冲。"""

    def setUp(self) -> None:
        """创建玩家角色 0（博士）及测试角色 1（甲）、2（乙），并在当前用例生命周期内启用临时状态缓冲。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "甲")
        self.world.chara(2, "乙")
        self.enterContext(working.based_on(core.state()))


class LentBooksTest(LibraryPanelCase):
    """已借出书籍查询 lent_books 与催还处理 urge_return 的行为测试。"""

    def test_rows_follow_type_order_and_skip_free_and_player(self) -> None:
        """验证 lent_books 按书籍类型配置顺序编号组装已借出条目，并跳过未借出与玩家（角色 0）持有的书籍。"""
        self.assertEqual(svc.lent_books(), ())
        first, second = first_books(11, 2)
        (third,) = first_books(13, 1)
        library.set_holder(third, 2)
        library.set_holder(second, 0)
        library.set_holder(first, 1)
        type_one = game_config.config_book_type[11].son_type_name
        type_two = game_config.config_book_type[13].son_type_name
        self.assertEqual(
            svc.lent_books(),
            (
                svc.LentBook(
                    1,
                    f"  [001]({type_one}){game_config.config_book[first].name}"
                    "  (被甲借走)",
                ),
                svc.LentBook(
                    2,
                    f"  [002]({type_two}){game_config.config_book[third].name}"
                    "  (被乙借走)",
                ),
            ),
        )

    def test_urge_return_raises_chance_and_queues_reading(self) -> None:
        """验证 urge_return 将还书概率加 100、娱乐槽位全设 101、返回含姓名提示且不影响其他角色。"""
        chara_life.book_return_possibility.set(1, 15)
        chara_life.entertainment_type.set(1, [3, 4, 5])
        self.assertEqual(svc.urge_return(1), "\n甲将在空闲时间前往图书馆还书\n")
        self.assertEqual(chara_life.book_return_possibility(1), 115)
        self.assertEqual(chara_life.entertainment_type(1), [101, 101, 101])
        self.assertEqual(chara_life.book_return_possibility(2), 0)


class RecommendTest(LibraryPanelCase):
    """阅读推荐计数、切换逻辑与按钮展示数据测试。"""

    def test_toggle_adds_removes_and_stops_at_three(self) -> None:
        """验证 toggle_recommend 与 recommend_left 未满 3 项新增、满 3 项停止新增并支持取消。"""
        self.assertEqual(svc.recommend_left(), 3)
        for type_id in (11, 12, 13, 14):
            svc.toggle_recommend(type_id)
        self.assertEqual(library.recommended(), {11, 12, 13})
        self.assertEqual(svc.recommend_left(), 0)
        svc.toggle_recommend(12)
        self.assertEqual(library.recommended(), {11, 13})
        self.assertEqual(svc.recommend_left(), 1)

    def test_over_cap_save_still_adds_and_counts_below_zero(self) -> None:
        """验证存档中已推荐超过 3 项时，toggle_recommend 仍允许追加新类别且 recommend_left 返回负数。"""
        library.set_recommended({11, 12, 13, 14})
        svc.toggle_recommend(15)
        self.assertEqual(library.recommended(), {11, 12, 13, 14, 15})
        self.assertEqual(svc.recommend_left(), -2)

    def test_option_label_marks_picked_types(self) -> None:
        """验证 recommend_option 返回未推荐与已推荐两种状态下的类别按钮文本和选中标志。"""
        type_data = game_config.config_book_type[13]
        label = f"[13]：{type_data.father_type_name}-{type_data.son_type_name}"
        self.assertEqual(
            svc.recommend_option(13), svc.RecommendOption(label, False)
        )
        library.set_recommended({13})
        self.assertEqual(
            svc.recommend_option(13),
            svc.RecommendOption(label + " (已推荐)", True),
        )


class ReadingPartyTest(LibraryPanelCase):
    """读书会排期行文本 party_rows 与选日逻辑 pick_party_day 的行为测试。"""

    def test_rows_name_each_day_and_its_party(self) -> None:
        """验证 party_rows 返回一周七天按钮文本，并在已安排活动的日期后追加对应娱乐名称。"""
        entertainment.set_party_day(3, 101)
        rows = svc.party_rows()
        self.assertEqual(len(rows), 7)
        self.assertEqual(
            rows[0], f"  [0]:{game_config.config_week_day[0].name}"
        )
        self.assertEqual(
            rows[3],
            f"  [3]:{game_config.config_week_day[3].name}"
            f" ({game_config.config_entertainment[101].name})",
        )

    def test_pick_moves_clears_and_refuses_other_parties(self) -> None:
        """验证 pick_party_day 可改期移动读书会、拒绝已被其他活动占用的日期以及重复点击取消当日读书会。"""
        entertainment.set_party_day(4, 51)
        self.assertIsNone(svc.pick_party_day(2))
        self.assertIsNone(svc.pick_party_day(5))
        self.assertEqual(
            [entertainment.party_day(d) for d in range(7)],
            [0, 0, 0, 0, 51, 101, 0],
        )
        self.assertEqual(
            svc.pick_party_day(4), "\n这一天已经被选为其他活动了\n"
        )
        self.assertEqual(entertainment.party_day(4), 51)
        self.assertIsNone(svc.pick_party_day(5))
        self.assertEqual(
            [entertainment.party_day(d) for d in range(7)],
            [0, 0, 0, 0, 51, 0, 0],
        )


class HistoryTest(LibraryPanelCase):
    """借阅历史持有人筛选 history_holders 与借书卡组装 history_card 的行为测试。"""

    def test_holders_skip_player_and_empty_cards(self) -> None:
        """验证 history_holders 跳过玩家角色 0 与无历史记录的角色，仅返回有记录的非玩家角色编号。"""
        record = {"book_id": 0, "return_time": None}
        chara_life.borrow_book_history.set(0, [record])
        self.assertEqual(svc.history_holders(), ())
        chara_life.borrow_book_history.set(2, [record])
        self.assertEqual(svc.history_holders(), (2,))

    def test_card_counts_and_lists_newest_first(self) -> None:
        """验证 history_card 汇总借阅本数与阅读次数，按最新在前格式化时间、未知书籍、未归还与空历史。"""
        book = first_books(11, 1)[0]
        name = game_config.config_book[book].name
        son = game_config.config_book_type[11].son_type_name
        chara_life.borrow_book_history.set(
            1,
            [
                {
                    "book_id": book,
                    "book_name": name,
                    "borrow_time": NOW,
                    "return_time": NOW + datetime.timedelta(days=2, minutes=7),
                    "total_read_count": 3,
                },
                {"book_id": 987654, "borrow_time": None, "return_time": None},
            ],
        )
        self.assertEqual(
            svc.history_card(1),
            svc.HistoryCard(
                "甲",
                2,
                3,
                (
                    "  [01] 《未知书籍》\n      借书时间：\n"
                    "      还书时间：仍在借阅中\n      阅读次数：0次\n",
                    f"  [02] 《{name}》 ({son})\n"
                    "      借书时间：2020年12月22日 10:00\n"
                    "      还书时间：2020年12月24日 10:07\n"
                    "      阅读次数：3次\n",
                ),
            ),
        )
        self.assertEqual(svc.history_card(2), svc.HistoryCard("乙", 0, 0, ()))


class PanelAdapterTest(LibraryPanelCase):
    """Manage_Library_Panel 与 SelectRecommendBookButton 调用服务并驱动界面绘制的适配测试。"""

    def test_panel_draws_service_notices_and_toggles(self) -> None:
        """验证面板催还与读书会冲突各绘单条等待提示、空闲日正常排期，以及推荐按钮样式与切换联动。"""
        panel = manage_library.Manage_Library_Panel(80)
        panel.return_book(1)
        self.assertEqual(
            self.world.wait_texts, ["\n甲将在空闲时间前往图书馆还书\n"]
        )
        self.world.wait_texts.clear()
        entertainment.set_party_day(4, 51)
        panel.choice_read_party(4)
        panel.choice_read_party(1)
        self.assertEqual(
            self.world.wait_texts, ["\n这一天已经被选为其他活动了\n"]
        )
        self.assertEqual(entertainment.party_day(1), 101)
        button = manage_library.SelectRecommendBookButton(13, 80, True, True, 0)
        self.assertIsInstance(button.now_draw, draw.LeftButton)
        self.assertEqual(button.now_draw.normal_style, "standard")
        button.button_0()
        self.assertEqual(library.recommended(), {13})
        picked = manage_library.SelectRecommendBookButton(13, 80, True, True, 0)
        self.assertEqual(picked.now_draw.normal_style, "gold_enrod")
        self.assertTrue(picked.now_draw.text.endswith(" (已推荐)"))


class BackendIsolationTest(FastTestCase):
    """library_panel_service 无界面与无结算导入边界的独立子进程测试。"""

    def test_fresh_backend_process_loads_no_ui_or_settle(self) -> None:
        """在屏蔽界面、结算、流程与窗口模块的独立子进程中调用服务接口，验证结果正确且无受限导入。"""
        result = subprocess.run(
            [sys.executable, "-c", BACKEND_RUN],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        line = result.stdout.splitlines()[-1]
        self.assertTrue(line.isascii())
        out = json.loads(line)
        self.assertEqual(out["attempted"], [])
        self.assertEqual(out["loaded"], [])
        self.assertEqual(out["lent"], [1])
        self.assertEqual(out["urged"], [100, [101, 101], True])
        self.assertEqual(out["recommended"], [11, 12, 13])
        self.assertEqual(out["left"], 0)
        self.assertEqual(out["days"], [0, 0, 0, 0, 51, 101, 0])
        self.assertEqual(out["refusals"], [False, False, True])
        self.assertEqual(out["holders"], [1])
        self.assertEqual(out["card"], [1, 0, 1])
        self.assertTrue(out["option"])
        self.assertEqual(out["rows"], 7)
