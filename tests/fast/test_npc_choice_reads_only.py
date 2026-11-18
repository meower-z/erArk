# -*- coding: UTF-8 -*-
"""
NPC 选行动的代码只读缓存
========================
npc_action_choice 的代码（状态机、选目标、宿舍管理员的状态机、模块自己的文件）不写游戏状态：
不给缓存或角色数据赋值，不调用会改变状态或嵌套结算的函数。状态机把选出的行动记进计划，由行动开始时写进缓存。
写入的判定是静态的启发式：赋值或变更调用的目标链上有 cache 的属性，或有 Character 的字段名（基底不是 self）。
还没搬走的写入列在 REMAINING 里：某个函数不再写时要从表里删掉，表只减不增。
"""

import ast
import pathlib

from tests.fast.base import FastTestCase
from tests.world import ROOT

MUTATORS = frozenset(
    {
        "append",
        "add",
        "pop",
        "remove",
        "discard",
        "clear",
        "update",
        "extend",
        "insert",
        "setdefault",
        "popitem",
    }
)
""" 会改变容器的方法名 """
FORBIDDEN_CALLS = frozenset(
    {
        "general_movement_module",
        "judge_character_status",
        "chara_handle_instruct_common_settle",
        "game_update_flow",
        "start_choice",
        "start_plan",
        "run_plan",
        "settle_npc_pass",
        "starter",
    }
)
""" 选行动的代码不能调用的函数（另有宿舍的 _set_ 开头的辅助函数）：会改变状态、嵌套结算，或开始选出的行动 """
SCOPE: dict[str, frozenset[str] | None] = {
    "Script/Modules/npc_action_choice/choice.py": None,
    "Script/Modules/npc_action_choice/choose.py": None,
    "Script/Modules/npc_action_choice/npc_hook.py": None,
    "Script/Design/handle_state_machine.py": None,
    "Script/StateMachine/default.py": frozenset(
        {"general_movement_module", "character_see_h_and_move_to_dormitory"}
    ),
    "Script/Design/handle_npc_ai.py": frozenset(
        {
            "run_npc_pre_behavior_checks",
            "commit_group_sex_tired_exit",
            "judge_assistant_character",
            "judge_character_follow",
            "judge_character_cant_move",
            "judge_student_leave_truncate",
            "judge_interrupt_character_behavior",
            "judge_same_position_npc_follow",
            "get_chara_entertainment",
            "select_random_free_character",
        }
    ),
    "Script/Design/handle_npc_ai_in_h.py": frozenset(
        {
            "judge_character_h_obscenity_unconscious",
            "end_h_left_behind",
            "wake_by_noise",
            "recover_from_unconscious_h",
            "handle_unconscious_h_response",
            "judge_weak_up_in_sleep_h",
            "settle_unconscious_semen_and_cloth",
            "evaluate_npc_body_part_prefs",
            "npc_active_h",
        }
    ),
    "Script/System/Dormitory_System/dormitory_manager_system.py": frozenset(
        {
            "get_dormitory_layer_by_character",
            "get_dormitory_manager_knowledge",
            "ask_copy_key",
        }
    ),
}
""" 选行动的代码：文件 -> 不属于选行动的顶层函数（None 为整个文件都是） """
REMAINING: dict[tuple[str, str], str] = {
    (
        "Script/Design/handle_npc_ai.py",
        "find_character_target",
    ): "今天的行为循环调用的入口：选出状态机后交给 gameplay_resolution 的 npc_start 开始",
    (
        "Script/Design/handle_state_machine.py",
        "add_state_machine",
    ): "登记给面板用的入口：选出计划后交给 npc_start 开始",
    (
        "Script/Design/handle_npc_ai_in_h.py",
        "npc_ai_in_group_sex",
    ): "H 中判断调用的入口：选出计划后交给 npc_start 执行",
    (
        "Script/Design/handle_npc_ai_in_h.py",
        "choose_in_group_sex",
    ): "临时改玩家的交互对象来查询部位的状态，查完复原",
}
""" 还没搬走的写入：(文件, 函数) -> 写的是什么 """


def chain(node: ast.AST) -> list[ast.AST]:
    """
    属性与下标的链，从基底开始
    Keyword arguments:
    node -- 表达式
    Return arguments:
    list -- 链上的节点
    """
    out: list[ast.AST] = []
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        out.append(node)
        node = node.value
    out.append(node)
    return out[::-1]


def cache_attr(target: ast.AST) -> str | None:
    """
    目标链上 cache 的属性名
    Keyword arguments:
    target -- 赋值目标
    Return arguments:
    str | None -- 属性名，链上没有 cache 时为 None
    """
    nodes = chain(target)
    for i, node in enumerate(nodes):
        if isinstance(node, ast.Attribute) and i:
            base = nodes[i - 1]
            if isinstance(base, ast.Name) and base.id == "cache":
                return node.attr
            if (
                isinstance(base, ast.Attribute)
                and base.attr == "cache"
                and isinstance(base.value, ast.Name)
                and base.value.id == "cache_control"
            ):
                return node.attr
    return None


def char_field(target: ast.AST, fields: frozenset[str]) -> str | None:
    """
    目标链上 Character 的字段名
    Keyword arguments:
    target -- 赋值目标
    fields -- Character 的字段名
    Return arguments:
    str | None -- 字段名，没有时为 None
    """
    if cache_attr(target) not in (None, "character_data"):
        return None
    nodes = chain(target)
    for i, node in enumerate(nodes):
        if isinstance(node, ast.Attribute) and node.attr in fields:
            base = nodes[i - 1]
            if isinstance(base, ast.Name) and base.id not in ("self", "cache"):
                return node.attr
            if (
                isinstance(base, ast.Subscript)
                and cache_attr(base) == "character_data"
            ):
                return node.attr
            return None
    return None


def character_fields() -> frozenset[str]:
    """
    Character 在 __init__ 里设的字段名
    Return arguments:
    frozenset -- 字段名
    """
    source = (pathlib.Path(ROOT) / "Script/Core/game_type.py").read_text(
        encoding="utf-8"
    )
    for cls in ast.parse(source).body:
        if isinstance(cls, ast.ClassDef) and cls.name == "Character":
            names = set()
            for node in ast.walk(cls):
                targets = getattr(
                    node, "targets", [getattr(node, "target", None)]
                )
                for target in targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"
                    ):
                        names.add(target.attr)
            return frozenset(names)
    raise AssertionError("game_type.py 里没有 Character")


def problems(tree: ast.AST, fields: frozenset[str]) -> list[str]:
    """
    一段代码里的写入与禁用调用
    Keyword arguments:
    tree -- 语法树
    fields -- Character 的字段名
    Return arguments:
    list -- 每处一行：行号与说明
    """
    out = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)) and node.value:
            targets = [node.target]
        elif isinstance(node, ast.Call):
            func = node.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else getattr(func, "id", "")
            )
            if name in FORBIDDEN_CALLS or name.startswith("_set_"):
                out.append(f"{line} 调用 {name}")
            if isinstance(func, ast.Attribute) and func.attr in MUTATORS:
                targets = [func.value]
        for target in targets:
            if cache_attr(target) or char_field(target, fields):
                out.append(f"{line} 写 {ast.unparse(target)}")
    return out


def scanned() -> dict[tuple[str, str], list[str]]:
    """
    选行动的代码里每个顶层函数的问题
    Return arguments:
    dict -- (文件, 函数) -> 问题；模块层的代码记在函数名 "<module>" 下
    """
    fields = character_fields()
    found: dict[tuple[str, str], list[str]] = {}
    for rel, skipped in SCOPE.items():
        tree = ast.parse((pathlib.Path(ROOT) / rel).read_text(encoding="utf-8"))
        rest = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if skipped is not None and node.name in skipped:
                    continue
                hits = problems(node, fields)
                if hits:
                    found[(rel, node.name)] = hits
            elif isinstance(node, ast.ClassDef):
                hits = problems(node, fields)
                if hits:
                    found[(rel, node.name)] = hits
            else:
                rest.append(node)
        hits = problems(ast.Module(body=rest, type_ignores=[]), fields)
        if hits:
            found[(rel, "<module>")] = hits
    return found


class NpcChoiceReadsOnlyTest(FastTestCase):
    """选行动的代码不写状态"""

    def test_no_new_write(self) -> None:
        """
        REMAINING 之外的选行动的代码没有写入，也不调用禁用的函数
        Keyword arguments:
        无
        Return arguments:
        无
        """
        found = scanned()
        new = {
            f"{rel}:{name}": hits
            for (rel, name), hits in found.items()
            if (rel, name) not in REMAINING
        }
        self.assertEqual(new, {}, "选行动的代码写了状态")

    def test_remaining_still_writes(self) -> None:
        """
        REMAINING 里的函数都还在写：搬走后要从表里删掉
        Keyword arguments:
        无
        Return arguments:
        无
        """
        found = scanned()
        stale = sorted(
            f"{rel}:{name}"
            for rel, name in REMAINING
            if (rel, name) not in found
        )
        self.assertEqual(stale, [], "这些函数不再写，从 REMAINING 删掉")

    def test_scope_files_exist(self) -> None:
        """
        SCOPE 里的文件都在，跳过的函数名都还在文件里
        Keyword arguments:
        无
        Return arguments:
        无
        """
        missing = []
        for rel, skipped in SCOPE.items():
            path = pathlib.Path(ROOT) / rel
            self.assertTrue(path.is_file(), rel)
            names = {
                node.name
                for node in ast.parse(path.read_text(encoding="utf-8")).body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            missing += sorted(f"{rel}:{n}" for n in (skipped or set()) - names)
        self.assertEqual(missing, [])
