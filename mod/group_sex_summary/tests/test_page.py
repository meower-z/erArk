# -*- coding: UTF-8 -*-
"""
page.py 行数据测试（假角色对象）：姓名样式、行内容、只在仍憋着时读实时余量
运行：python3 mod/group_sex_summary/tests/test_page.py（不需要游戏环境）
"""
import sys
from types import SimpleNamespace

from _harness import check, finish, load_mod_package

load_mod_package()
from _erark_mod_group_sex_summary import page, state  # noqa: E402


def character(name, text_color="", edge_count=None):
    return SimpleNamespace(name=name, text_color=text_color, h_state=SimpleNamespace(orgasm_edge_count=edge_count or {}))


check("无自定义颜色用 standard", page.name_style(character("阿米娅")) == "standard")
check("有自定义颜色用角色名（已注册的样式名）", page.name_style(character("阿米娅", "#ff88aa")) == "阿米娅")

player = SimpleNamespace(ability={30: 1})
data = {0: player, 11: character("甲", "#fff"), 12: character("乙", "", {"c": 1}), 13: character("丙"), 16: character("丁")}
turn = state.TurnState("bid")
turn.orgasm_record = {11: {"v": 2, "c": 1}, 13: {"m": 2, "c": 1}, 0: {"v": 1}}
turn.edge_record = {12: {"c": 1}, 13: {"c": 1}}
turn.break_reason = {16: "tired"}
rows = page.build_rows(turn, data)
check("行顺序按角色id，玩家不列", [row.name for row in rows] == ["甲", "乙", "丙", "丁"], rows)
check(
    "纯绝顶行",
    rows[0] == page.SummaryRow("甲", "甲", "", "", "双重绝顶：阴道强绝顶、阴蒂绝顶", ""),
    rows[0],
)
# 乙：1*3-1=2 -> <寸止!>
check("仍憋着的行按实时余量", rows[1] == page.SummaryRow("乙", "standard", " <寸止!>", "red", "", "阴蒂绝顶寸止"), rows[1])
check("兑现的行显示 <寸止释放>，寸止说明为空", rows[2] == page.SummaryRow("丙", "standard", " <寸止释放>", "gold_enrod", "双重绝顶：口喉强绝顶、阴蒂绝顶", ""), rows[2])
check("太累退出无记录也成行", rows[3] == page.SummaryRow("丁", "standard", " <累>", "little_dark_slate_blue", "", ""), rows[3])
check("空轮没有行", page.build_rows(state.TurnState(), data) == [])
check("不 import 游戏", "Script.Core.cache_control" not in sys.modules)
finish()
