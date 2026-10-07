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
check("纯绝顶行", rows[0] == page.SummaryRow("甲", "甲", "", "standard", {"v": 2, "c": 1}, {}), rows[0])
# 乙：1*3-1=2 -> <寸止!>
check("仍憋着的行按实时余量", rows[1] == page.SummaryRow("乙", "standard", "<寸止!>", "red", {}, {"c": 1}), rows[1])
check("兑现的行显示 <寸止释放>，寸止侧为空", rows[2] == page.SummaryRow("丙", "standard", "<寸止释放>", "gold_enrod", {"m": 2, "c": 1}, {}), rows[2])
check("太累退出无记录也成行", rows[3] == page.SummaryRow("丁", "standard", "<累>", "little_dark_slate_blue", tired=True), rows[3])
check("空轮没有行", page.build_rows(state.TurnState(), data) == [])

# 排版
def text_of(line):
    return "".join(text for text, _style in line)


demo = [
    page.SummaryRow("夜莺", "standard", "<寸止释放>", "gold_enrod", {"v": 2, "c": 1, "b": 1}),
    page.SummaryRow("槐琥", "standard", "<寸止!>", "red", {}, {"v": 2, "c": 1}),
    page.SummaryRow("赤刃明霄陈", "standard", "", "standard", {"c": 0}),
    page.SummaryRow("可颂", "standard", "<累>", "little_dark_slate_blue", tired=True),
    page.SummaryRow("九", "standard", "", "standard", {"v": 3, "a": 3, "w": 2, "h": 1}, {"b": 3}),
]
lines = page.layout(demo, 100, "本轮群交结算", "(点击继续)")
texts = [text_of(line) for line in lines]
check("每行宽度不超过页宽", all(page._width(text) <= 100 for text in texts))
check("标题行与横线、页脚同宽", page._width(texts[0]) == page._width(texts[-2]) == page._width(texts[-1]), texts)
check("页宽跟内容走：最宽一行再加缩进", page._width(texts[-2]) == max(page._width(text) for text in texts[1:-2]) + 2, texts)
narrow = [text_of(line) for line in page.layout(demo, 40, "本轮群交结算", "(点击继续)")]
check("页宽不超过上限", page._width(narrow[0]) == page._width(narrow[-2]) == 40, narrow)
check("排序：部位多的绝顶在前，只有标记的在最后", [text.split()[0] for text in texts[1:-2]] == ["九", "夜莺", "赤刃明霄陈", "槐琥", "可颂"])
check("类别列对齐", len({page._width(text[: text.index(kind)]) for text, kind in zip(texts[1:3], ["四重绝顶", "三重绝顶"])}) == 1)
check("单部位绝顶的行类别列留空，明细与上方明细列对齐", page._width(texts[3][: texts[3].index("阴蒂")]) == page._width(texts[2][: texts[2].index("阴道")]), texts[2:4])
check("只寸止的行类别列留空，明细与上方明细列对齐", page._width(texts[4][: texts[4].index("阴道×2")]) == page._width(texts[3][: texts[3].index("阴蒂")]), texts[3:5])
check("明细：按档位分组并接寸止", texts[1].endswith("阴道、肛肠 超强绝顶 ・ 子宫 强绝顶 ・ 心理 绝顶   寸止 胸部×3"), texts[1])
check("明细：只寸止的行不加前缀", texts[4].endswith("<寸止!>               阴道×2、阴蒂") and "寸止中" not in texts[4], texts[4])
check("同次数的寸止部位各自带 ×N", text_of(page.detail_of(page.SummaryRow("仇白", "standard", holding={"v": 3, "c": 3, "b": 1}))) == "阴蒂×3、阴道×3、胸部")
check("只有标记的行不留行尾空格", texts[5] == "  可颂        <累>", repr(texts[5]))
check("页脚：人数统计 + 右侧提示", texts[-1].startswith("  绝顶 3 人 ・ 寸止中 2 人 ・ 体力耗尽 1 人") and texts[-1].endswith(" (点击继续)"), texts[-1])
lines = page.layout([page.SummaryRow("夜莺", "standard", "", "standard", {"v": 1})], 100, "本轮群交结算", "(点击继续)")
check("整页为空的列不占宽度", text_of(lines[1]) == "  夜莺  阴道 绝顶", text_of(lines[1]))
check("不 import 游戏", "Script.Core.cache_control" not in sys.modules)
finish()
