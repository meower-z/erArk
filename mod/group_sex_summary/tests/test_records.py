# -*- coding: UTF-8 -*-
"""
records.py 纯函数测试：合并、断因优先级、寸止余量与标记、拆分、摘要文本、摘要行、释放事件
运行：python3 mod/group_sex_summary/tests/test_records.py（不需要游戏环境）
"""
import sys

from _harness import check, finish, load_mod_package

package = load_mod_package()
from _erark_mod_group_sex_summary import records  # noqa: E402

check("records 不 import 游戏", "Script.Core.cache_control" not in sys.modules)

# 合并：绝顶按部位取最高档，未触发的忽略；寸止按部位计数
DEGREE = {"normal": 1, "strong": 2}


def parse(second_behavior_id):
    part, _, degree = second_behavior_id.partition("_orgasm_")
    if degree in DEGREE:
        return part, DEGREE[degree]
    return None, None


orgasm_record, edge_record = {}, {}
records.merge_second_behavior(orgasm_record, edge_record, 7, {"v_orgasm_strong": 1, "c_orgasm_normal": 0, "a_orgasm_edge": 1, "unrelated": 1}, parse)
check("合并：取最高档、忽略未触发", orgasm_record == {7: {"v": 2}}, orgasm_record)
check("合并：寸止按部位计数", edge_record == {7: {"a": 1}}, edge_record)
records.merge_second_behavior(orgasm_record, edge_record, 7, {"v_orgasm_normal": 1, "a_orgasm_edge": 1}, parse)
check("合并：低档不覆盖高档", orgasm_record[7]["v"] == 2)
check("合并：寸止次数累加", edge_record[7]["a"] == 2)

# 断因：只升不降
reasons = {}
records.mark_break_reason(reasons, 21, "fail")
check("断因：首次写入", reasons[21] == "fail")
records.mark_break_reason(reasons, 21, "release")
check("断因：release 覆盖 fail", reasons[21] == "release")
records.mark_break_reason(reasons, 21, "fail")
check("断因：fail 不覆盖 release", reasons[21] == "release")
records.mark_break_reason(reasons, 21, "tired")
check("断因：tired 覆盖 release", reasons[21] == "tired")
records.mark_break_reason(reasons, 21, "release")
check("断因：release 不覆盖 tired", reasons[21] == "tired")

# 寸止余量
check("余量 2*3-1=5", records.edge_margin(2, {"v": 1}) == 5)
check("余量 1*3-2=1", records.edge_margin(1, {"v": 1, "c": 1}) == 1)
check("余量 0*3-4=-4", records.edge_margin(0, {"v": 2}) == -4)
check("余量 5 不算接近极限", not records.is_near_limit(5))
check("余量 2 算接近极限", records.is_near_limit(2))
check("余量 -4 算接近极限", records.is_near_limit(-4))
for lv, counts in ((2, {"v": 1}), (1, {"v": 1, "c": 1}), (0, {"v": 2}), (1, {"v": 1})):
    margin = records.edge_margin(lv, counts)
    check(f"感叹号档位与实时显示门一致 lv={lv} {counts}", ("!" in records.holding_edge_tag(margin)[0]) == records.is_near_limit(margin))

# 标记
check("标记：<寸止>", records.holding_edge_tag(5) == (" <寸止>", "hot_pink"))
check("标记：<寸止!>", records.holding_edge_tag(2) == (" <寸止!>", "red"))
check("标记：<寸止!!>", records.holding_edge_tag(-4) == (" <寸止!!>", "levelex"))


def never():
    raise AssertionError("不该读余量")


check("状态标记：没寸止过不显示", records.edge_status_tag(None, {}, {"v": 1}, never) == ("", ""))
check("状态标记：tired", records.edge_status_tag("tired", {}, {}, never) == (" <累>", "little_dark_slate_blue"))
check("状态标记：fail 即使无寸止记录", records.edge_status_tag("fail", {}, {"v": 2}, never) == (" <寸止失败>", "gold_enrod"))
check("状态标记：release", records.edge_status_tag("release", {"v": 1}, {"v": 1}, never) == (" <寸止释放>", "gold_enrod"))
check("状态标记：憋住后兑现显示 <寸止释放>", records.edge_status_tag(None, {"c": 1, "v": 1}, {"m": 2, "c": 1, "v": 1}, never) == (" <寸止释放>", "gold_enrod"))
check("状态标记：仍憋着按实时余量", records.edge_status_tag(None, {"v": 1}, {}, lambda: 5) == (" <寸止>", "hot_pink"))
check("状态标记：仍憋着 余量<0", records.edge_status_tag(None, {"v": 1}, {}, lambda: -1) == (" <寸止!!>", "levelex"))

# 拆分
check("拆分：兑现部位归绝顶侧", records.split_edge_parts({"c": 1, "v": 1}, {"m": 2, "c": 1, "v": 1}, False) == ({"c": 1, "v": 1}, {}))
check("拆分：没绝顶的部位仍憋着", records.split_edge_parts({"v": 1}, {}, False) == ({}, {"v": 1}))
check("拆分：断过的角色全部算已兑现", records.split_edge_parts({"v": 1}, {}, True) == ({"v": 1}, {}))
check("拆分：空记录", records.split_edge_parts({}, {}, True) == ({}, {}))

# 摘要文本
check("寸止说明：空", records.edge_token({}) == "")
check("寸止说明：同次数合组", records.edge_token({"h": 1, "c": 1}) == "阴蒂、心理绝顶寸止")
check("寸止说明：×N", records.edge_token({"v": 2}) == "阴道绝顶寸止×2")
check("寸止说明：多组按次数降序", records.edge_token({"c": 1, "v": 2}) == "阴道绝顶寸止×2、阴蒂绝顶寸止")
check("绝顶描述：空", records.orgasm_desc({}) == "")
check("绝顶描述：单部位", records.orgasm_desc({"v": 1}) == "绝顶：阴道绝顶")
check("绝顶描述：按档位分组", records.orgasm_desc({"c": 1, "v": 2}) == "双重绝顶：阴道强绝顶、阴蒂绝顶")
check("绝顶描述：同档组内用・", records.orgasm_desc({"v": 2, "c": 2}) == "双重绝顶：阴蒂・阴道强绝顶")
desc = records.orgasm_desc({"v": 2, "p": 2})
check("绝顶描述：未知部位排末尾不丢", desc == "双重绝顶：阴道・p强绝顶", desc)
many = {part: 0 for part in records.PART_ORDER}
many.update({"x": 0, "y": 0})
check("绝顶描述：超过十重时封顶为十重", records.orgasm_desc(many).startswith("十重绝顶："))

# 摘要行
check("摘要行：有记录的 NPC，玩家不列", records.summary_row_ids({11: {"v": 1}, 0: {"v": 1}}, {12: {"c": 1}}, {}) == [11, 12])
check("摘要行：无记录为空", records.summary_row_ids({}, {}, {}) == [])
check("摘要行：太累退出无记录也列", records.summary_row_ids({}, {}, {16: "tired"}) == [16])
check("摘要行：fail/release 不单独并入", records.summary_row_ids({}, {}, {17: "fail", 18: "release"}) == [])

# 释放事件
check("释放事件：edge=2 且计数未清", records.is_edge_release_event(2, {"v": 1}))
check("释放事件：计数已清不算", not records.is_edge_release_event(2, {}))
check("释放事件：计数全 0 不算", not records.is_edge_release_event(2, {"v": 0, "c": 0}))
check("释放事件：edge=1 不算", not records.is_edge_release_event(1, {"v": 1}))

check("全程不 import 游戏", "Script.Core.cache_control" not in sys.modules)
finish()
