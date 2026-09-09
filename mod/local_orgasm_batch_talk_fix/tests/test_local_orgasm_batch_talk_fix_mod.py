# -*- coding: UTF-8 -*-
"""
local_orgasm_batch_talk_fix 单元自检。

直接 exec 真实 mod 脚本，注入假的 call_original 与桩模块（cache_control / get_text /
orgasm_settle / talk / draw / normal_config），验证：
1. 同一部位只取最高等级、按强度从高到低排序；
2. 前 3 个部位走完整口上、第 4 个起进汇总行的分界；
3. wrapper 在原函数执行期间接管口上，把接管的 id 吞掉、未接管的 id 透传，并在结束后恢复；
4. 批次绘制发生在原函数执行任何二段效果之前（假原函数按上游语义：同部位低等级跳口上但照常执行效果）；
5. 离屏角色与玩家不进批次。
不启动完整游戏，无第三方测试框架。
"""
import ast
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "local_orgasm_batch_talk_fix.py"
REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_real_get_orgasm_part_and_degree():
    """参数：无；返回：Callable为上游的部位/程度解析函数；用途：从真实的Script/Settle/orgasm_settle.py中抽出解析函数与其程度表，上游改名或改语义时本自检会直接失败（整模块导入会触发游戏的循环依赖，故只取需要的两个顶层节点）。"""
    source_path = REPO_ROOT / "Script" / "Settle" / "orgasm_settle.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    wanted_nodes = [
        node
        for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name == "get_orgasm_part_and_degree")
        or (isinstance(node, ast.Assign) and any(getattr(target, "id", "") == "orgasm_degree_order" for target in node.targets))
    ]
    assert len(wanted_nodes) == 2, f"上游orgasm_settle缺少orgasm_degree_order或get_orgasm_part_and_degree: {source_path}"
    namespace = {}
    exec(compile(ast.Module(body=wanted_nodes, type_ignores=[]), str(source_path), "exec"), namespace)
    return namespace["get_orgasm_part_and_degree"]


REAL_GET_ORGASM_PART_AND_DEGREE = _load_real_get_orgasm_part_and_degree()


def _stub_module(name: str, **attrs) -> ModuleType:
    """参数：name(str)为模块名，**attrs为模块属性；返回：ModuleType为桩模块；用途：注册一个桩模块到sys.modules供mod脚本的延迟导入命中。"""
    module = ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    # 同时挂到父包上，使 `from 包 import 子模块` 形式的导入能取到桩
    parent_name, _sep, child_name = name.rpartition(".")
    if parent_name in sys.modules:
        setattr(sys.modules[parent_name], child_name, module)
    return module


def _load(cache, character_id=1):
    """参数：cache(SimpleNamespace)为桩缓存，character_id(int)为受测角色id；返回：(命名空间dict, 事件列表list)；用途：exec真实mod脚本并接管所有绘制出口，事件列表按顺序记录绘制行为。"""
    events = []

    for parent in ("Script", "Script.Core", "Script.Design", "Script.Settle", "Script.Config", "Script.UI", "Script.UI.Moudle"):
        sys.modules.setdefault(parent, ModuleType(parent))
    _stub_module("Script.Design.handle_npc_ai")  # 满足脚本顶层用于打破循环导入的预导入
    _stub_module("Script.Core.cache_control", cache=cache)
    _stub_module("Script.Core.get_text", _=lambda text: text)
    _stub_module("Script.Settle.orgasm_settle", get_orgasm_part_and_degree=REAL_GET_ORGASM_PART_AND_DEGREE)
    _stub_module("Script.Config.normal_config", config_normal=SimpleNamespace(text_width=50))

    class _StubWaitDraw:
        """桩绘制对象：把绘制内容记入事件列表。"""

        def __init__(self):
            self.style = ""
            self.width = 0
            self.text = ""

        def draw(self):
            """参数：无；返回：None；用途：记录一次汇总行绘制。"""
            events.append(("info", self.text))

    _stub_module("Script.UI.Moudle.draw", WaitDraw=_StubWaitDraw)

    def handle_second_talk(cid, behavior_id="share_blankly"):
        """参数：cid(int)为角色id，behavior_id(str)为二段行为id；返回：None；用途：桩的原始二段口上绘制，记录完整口上事件。"""
        events.append(("talk", behavior_id))

    def handle_talk_sub(cid, behavior_id, calculated_premise_dict=None):
        """参数：cid(int)为角色id，behavior_id(str)为二段行为id，calculated_premise_dict(dict)为前提缓存；返回：tuple(口上数据dict, 前提缓存dict)；用途：桩的口上取用，只有以a_/v_开头的寸止行为有正文。"""
        has_text = behavior_id in ("a_orgasm_edge", "v_orgasm_edge")
        return ({1: ["t"]} if has_text else {}), {}

    talk_module = _stub_module(
        "Script.Design.talk",
        handle_second_talk=handle_second_talk,
        handle_talk_sub=handle_talk_sub,
        choice_talk_from_talk_data=lambda data, behavior_id="share_blankly": ("text", "id", None),
        handle_talk_draw=lambda cid, talk_text, now_talk_id, second_behavior_id="", common_behavior_id=None: events.append(("talk_no_title", now_talk_id, second_behavior_id)),
    )

    def call_original(module, func, *args, **kwargs):
        """参数：module(str)为模块名，func(str)为函数名，*args/**kwargs为透传参数；返回：str标记；用途：按上游second_behavior_effect的真实语义模拟结算循环——先按部位统计最高程度，同部位非最高程度的行为跳过口上但照常执行效果（记为可观测的effect事件），随后把行为值归零。"""
        events.append(("original", func))
        cid = args[0]
        active_behavior_ids = [behavior_id for behavior_id, value in cache.character_data[cid].second_behavior.items() if value]
        # 上游 part_max_degree_dict：同部位只保留最高程度触发口上
        part_max_degree = {}
        for behavior_id in active_behavior_ids:
            orgasm_part, orgasm_degree = REAL_GET_ORGASM_PART_AND_DEGREE(behavior_id)
            if orgasm_part is not None and orgasm_degree > part_max_degree.get(orgasm_part, -1):
                part_max_degree[orgasm_part] = orgasm_degree
        for behavior_id in active_behavior_ids:
            talk_flag = True
            if part_max_degree:
                orgasm_part, orgasm_degree = REAL_GET_ORGASM_PART_AND_DEGREE(behavior_id)
                if orgasm_part is not None and orgasm_degree < part_max_degree.get(orgasm_part, -1):
                    talk_flag = False
            if talk_flag:
                talk_module.handle_second_talk(cid, behavior_id)
            # 效果照常执行：这是口上取用前提时能看见的状态变化，用事件记录以便断言绘制时点
            events.append(("effect", behavior_id))
            cache.character_data[cid].second_behavior[behavior_id] = 0
        return "ORIG"

    namespace = {"call_original": call_original}
    exec(compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec"), namespace)
    namespace["_talk_module"] = talk_module
    namespace["_original_handle_second_talk"] = handle_second_talk
    return namespace, events


def _new_cache(second_behavior: dict, position=None, move_src=None):
    """参数：second_behavior(dict)为角色1的二段行为字典，position(list)为角色1所在位置，move_src(list)为角色1的移动来源；返回：SimpleNamespace为桩缓存；用途：构造最小可用的游戏缓存，默认角色1与玩家同处一地。"""
    player_position = ["1", "2"]
    return SimpleNamespace(
        is_collection=False,
        character_data={
            0: SimpleNamespace(name="博士", collection_character=[], second_behavior={}, position=player_position, behavior=SimpleNamespace(move_src=player_position)),
            1: SimpleNamespace(
                name="阿米娅",
                collection_character=[],
                second_behavior=dict(second_behavior),
                position=player_position if position is None else position,
                behavior=SimpleNamespace(move_src=player_position if move_src is None else move_src),
            ),
        },
    )


def test_same_part_keeps_highest_and_sorts_by_degree():
    """参数：无；返回：None；用途：验证同一部位只保留最高等级，且结果按强度从高到低排序。"""
    namespace, _events = _load(_new_cache({}))
    ordered = namespace["select_batch_parts"](["v_orgasm_small", "v_orgasm_super", "b_orgasm_normal", "a_orgasm_strong", "plural_orgasm_3", "b_orgasm_to_milk"])
    assert [item[0] for item in ordered] == ["v", "a", "b"], f"排序结果错误: {ordered}"
    assert [item[1] for item in ordered] == ["v_orgasm_super", "a_orgasm_strong", "b_orgasm_normal"], f"同部位未取最高等级: {ordered}"
    assert [item[2] for item in ordered] == [3, 2, 1], f"强度序号错误: {ordered}"


def test_summary_starts_at_fourth_part():
    """参数：无；返回：None；用途：验证前3个部位不进汇总，第4个起按强度分组进汇总行。"""
    namespace, _events = _load(_new_cache({}))
    three_parts = namespace["select_batch_parts"](["v_orgasm_super", "a_orgasm_strong", "b_orgasm_normal"])
    assert namespace["build_summary_text"]("阿米娅", three_parts) == "", "仅3个部位时不应产生汇总行"
    five_parts = namespace["select_batch_parts"](["v_orgasm_super", "a_orgasm_strong", "b_orgasm_normal", "c_orgasm_normal", "u_orgasm_small"])
    summary_text = namespace["build_summary_text"]("阿米娅", five_parts)
    assert "阿米娅" in summary_text, f"汇总行缺少角色名: {summary_text!r}"
    assert "绝顶" in summary_text and "小绝顶" in summary_text, f"汇总行缺少强度名: {summary_text!r}"
    assert "阴道" not in summary_text and "肛肠" not in summary_text, f"前3名部位不应进汇总行: {summary_text!r}"


def test_wrapper_batches_and_restores():
    """参数：无；返回：None；用途：验证wrapper在原函数期间接管口上：批次先绘制，被接管的部位绝顶不再逐条出口上，未接管行为透传，结束后钩子被恢复。"""
    cache = _new_cache(
        {
            "plural_orgasm_5": 1,
            "v_orgasm_super": 1,
            "v_orgasm_small": 1,
            "a_orgasm_strong": 1,
            "b_orgasm_normal": 1,
            "c_orgasm_normal": 1,
            "u_orgasm_small": 1,
            "add_favorability": 1,
        }
    )
    namespace, events = _load(cache)
    result = namespace["patched_second_behavior_effect"](1, SimpleNamespace(), [], True)
    assert result == "ORIG", "未透传原函数返回值"
    assert namespace["_talk_module"].handle_second_talk is namespace["_original_handle_second_talk"], "结束后未恢复原handle_second_talk"

    talk_ids = [event[1] for event in events if event[0] == "talk"]
    # 多重绝顶最先，随后是前3个部位的完整口上，最后是未被接管的普通二段行为
    assert talk_ids[0] == "plural_orgasm_5", f"多重绝顶未最先显示: {talk_ids}"
    assert talk_ids[1:3] == ["v_orgasm_super", "a_orgasm_strong"], f"高强度部位未按强度优先显示: {talk_ids}"
    # 胸部与阴蒂同为普通绝顶，同强度随机打乱，第3位取其一，另一个落入汇总行
    assert talk_ids[3] in ("b_orgasm_normal", "c_orgasm_normal"), f"第3个完整口上部位错误: {talk_ids}"
    assert talk_ids[4:] == ["add_favorability"], f"未接管行为应原样透传且仅此一条: {talk_ids}"
    assert "v_orgasm_small" not in talk_ids, "同部位低等级不应再出完整口上"
    info_texts = [event[1] for event in events if event[0] == "info"]
    left_out_name = "阴蒂" if talk_ids[3] == "b_orgasm_normal" else "胸部"
    assert len(info_texts) == 1 and left_out_name in info_texts[0] and "尿道" in info_texts[0], f"汇总行内容错误: {info_texts}"


def test_wrapper_merges_multi_part_edge():
    """参数：无；返回：None；用途：验证多部位寸止合并成一行标题，并只补一条无标题正文（且从有正文的部位中挑选）。"""
    cache = _new_cache({"v_orgasm_edge": 1, "a_orgasm_edge": 1, "c_orgasm_edge": 1})
    namespace, events = _load(cache)
    namespace["patched_second_behavior_effect"](1, SimpleNamespace(), [], True)
    info_texts = [event[1] for event in events if event[0] == "info"]
    assert len(info_texts) == 1 and "绝顶寸止" in info_texts[0], f"寸止合并标题错误: {info_texts}"
    assert "阴蒂" in info_texts[0] and "阴道" in info_texts[0] and "肛肠" in info_texts[0], f"寸止标题缺部位: {info_texts}"
    no_title_events = [event for event in events if event[0] == "talk_no_title"]
    assert len(no_title_events) == 1 and no_title_events[0][2] == "", f"应只补一条无标题正文: {no_title_events}"
    assert not [event for event in events if event[0] == "talk"], f"寸止行为不应再逐条出完整口上: {events}"


def test_batch_drawn_before_any_effect():
    """参数：无；返回：None；用途：验证批次整块绘制在原函数执行任何二段效果之前——上游对同部位低等级行为是「跳过口上但照常执行效果」，若批次改在口上时点绘制，阴蒂小绝顶的效果会先落地，导致强绝顶的初次高潮专属口上前提失效。"""
    # 阴蒂小绝顶排在强绝顶之前：上游会吞掉小绝顶的口上但先执行它的效果
    cache = _new_cache({"c_orgasm_small": 1, "c_orgasm_strong": 1})
    namespace, events = _load(cache)
    namespace["patched_second_behavior_effect"](1, SimpleNamespace(), [], True)
    event_kinds = [event[0] for event in events]
    original_index = event_kinds.index("original")
    batch_events = [event for event in events[:original_index] if event[0] in ("talk", "info", "talk_no_title")]
    assert ("talk", "c_orgasm_strong") in batch_events, f"批次未在原函数之前绘制强绝顶口上: {events}"
    first_effect_index = event_kinds.index("effect")
    assert not [event for event in events[first_effect_index:] if event[0] in ("talk", "info", "talk_no_title")], f"批次绘制晚于二段效果执行: {events}"


def test_off_screen_skips_batch():
    """参数：无；返回：None；用途：验证角色位置与移动来源都不在玩家处时不进批次，直接透传给上游（上游自身会在该情况下早退不显示口上）。"""
    # 用4个部位+多重绝顶，使「进批次」与「不进批次」在口上顺序和汇总行上都可区分
    cache = _new_cache(
        {"u_orgasm_small": 1, "v_orgasm_super": 1, "plural_orgasm_5": 1, "a_orgasm_strong": 1, "b_orgasm_normal": 1},
        position=["9", "9"],
        move_src=["9", "8"],
    )
    namespace, events = _load(cache)
    namespace["patched_second_behavior_effect"](1, SimpleNamespace(), [], True)
    assert not [event for event in events if event[0] == "info"], f"离屏角色不应绘制批次汇总行: {events}"
    assert [event[1] for event in events if event[0] == "talk"] == [
        "u_orgasm_small",
        "v_orgasm_super",
        "plural_orgasm_5",
        "a_orgasm_strong",
        "b_orgasm_normal",
    ], f"离屏角色口上应按原字典顺序原样透传给上游: {events}"


def test_player_skips_batch():
    """参数：无；返回：None；用途：验证玩家（id 0）不进批次，直接走上游原逻辑。"""
    cache = _new_cache({})
    cache.character_data[0].second_behavior = {"v_orgasm_super": 1, "a_orgasm_strong": 1}
    namespace, events = _load(cache)
    namespace["patched_second_behavior_effect"](0, SimpleNamespace(), [], True)
    assert [event[1] for event in events if event[0] == "talk"] == ["v_orgasm_super", "a_orgasm_strong"], f"玩家口上不应被合并: {events}"
    assert not [event for event in events if event[0] == "info"], "玩家不应出现批次汇总行"


if __name__ == "__main__":
    test_same_part_keeps_highest_and_sorts_by_degree()
    test_summary_starts_at_fourth_part()
    test_wrapper_batches_and_restores()
    test_wrapper_merges_multi_part_edge()
    test_batch_drawn_before_any_effect()
    test_off_screen_skips_batch()
    test_player_skips_batch()
    print("local_orgasm_batch_talk_fix: all self-checks PASS")
