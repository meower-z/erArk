# -*- coding: UTF-8 -*-
"""
lint_base_diff 的夹具测试：合法钩子形状必须放行，非法改动必须报错
用法：python3 mod/lewd_tattoo/tests/test_lint_base_diff.py
"""
import os
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import REPO_ROOT, check, finish  # noqa: E402
import lint_base_diff as lint  # noqa: E402

with open(os.path.join(REPO_ROOT, "Script/Core/mod_hook.py"), encoding="utf-8") as _f:
    HOOKS = lint.load_hook_names(_f.read())
""" 真实钩子名单 """


def errors_of(old: str, new: str, path: str = "Script/Settle/x.py") -> list:
    """
    对一对 (main 源码, 新源码) 跑语义闸与文本闸
    Keyword arguments:
    old -- main 版本源码
    new -- 新源码
    path -- 假装的文件路径
    Return arguments:
    list -- 违规描述
    """
    old = textwrap.dedent(old)
    new = textwrap.dedent(new)
    return lint.check_semantic(path, old, new, HOOKS) + lint.check_text(path, old, new)


def ok(name: str, old: str, new: str, path: str = "Script/Settle/x.py") -> None:
    """
    断言放行
    Keyword arguments:
    name -- 用例名
    old -- main 源码
    new -- 新源码
    path -- 文件路径
    Return arguments:
    None
    """
    errors = errors_of(old, new, path)
    check(f"放行: {name}", not errors, errors)


def bad(name: str, old: str, new: str, path: str = "Script/Settle/x.py") -> None:
    """
    断言报错
    Keyword arguments:
    name -- 用例名
    old -- main 源码
    new -- 新源码
    path -- 文件路径
    Return arguments:
    None
    """
    errors = errors_of(old, new, path)
    check(f"拒绝: {name}", errors, "（未报错）")


print("==== 钩子名单 ====")
check("名单来自 mod_hook.py", HOOKS == {"state_gain": True, "edge_judged": False, "daily_desire_growth": False, "character_info_draw_list": False, "desire_written": False}, HOOKS)

# ---------- 夹具源码 ----------
OLD_H1 = """
from Script.Core import cache_control, game_type


def settle(character_id, state_id, final_value, change_data, target_change):
    final_value = int(final_value)
    data = cache_control.cache.character_data[character_id]
    data.status_data[state_id] += final_value
    data.status_data[state_id] = min(data.status_data[state_id], 99999)
"""

NEW_H1 = """
from Script.Core import cache_control, game_type, mod_hook


def settle(character_id, state_id, final_value, change_data, target_change):
    final_value = int(final_value)
    # mod 钩子
    final_value = mod_hook.state_gain(final_value, character_id, state_id, change_data, target_change)
    if final_value is None:
        return
    data = cache_control.cache.character_data[character_id]
    data.status_data[state_id] += final_value
    data.status_data[state_id] = min(data.status_data[state_id], 99999)
"""

OLD_WRAP = """
def sing(target_data, change_data):
    for i in {18, 19, 20}:
        now_add_lust = int(10 * 1.5)
        target_data.status_data[i] += now_add_lust
        target_data.status_data[i] = min(target_data.status_data[i], 99999)
        change_data.target_change.setdefault(target_data.cid, 0)
        change_data.target_change[target_data.cid] += now_add_lust
        target_data.angry_point += 5
"""

NEW_WRAP = """
def sing(target_data, change_data):
    for i in {18, 19, 20}:
        now_add_lust = int(10 * 1.5)
        now_add_lust = mod_hook.state_gain(now_add_lust, target_data.cid, i, None, change_data)
        if now_add_lust is not None:
            target_data.status_data[i] += now_add_lust
            target_data.status_data[i] = min(target_data.status_data[i], 99999)
            change_data.target_change.setdefault(target_data.cid, 0)
            change_data.target_change[target_data.cid] += now_add_lust
        target_data.angry_point += 5
"""

OLD_MISC = """
import random


def day(character_data, character_id, info_draw_text, flag, over_count, self_obj, width):
    character_data.desire_point += random.randint(1, 2)
    character_data.desire_point = 0
    flag, info_draw_text = (flag, info_draw_text)
    print(info_draw_text)
    self_obj.draw_list = [1, 2]
    return flag
"""

NEW_MISC = """
import random
from Script.Core import mod_hook


def day(character_data, character_id, info_draw_text, flag, over_count, self_obj, width):
    character_data.desire_point += mod_hook.daily_desire_growth(random.randint(1, 2), character_id)
    character_data.desire_point = 0
    mod_hook.desire_written(character_data)
    flag, info_draw_text = (flag, info_draw_text)
    flag, info_draw_text = mod_hook.edge_judged((flag, info_draw_text), character_id, over_count)
    print(info_draw_text)
    self_obj.draw_list = [1, 2]
    self_obj.draw_list = mod_hook.character_info_draw_list(self_obj.draw_list, character_id, width)
    return flag
"""

OLD_CHARA = """
class Character:
    def __init__(self):
        self.author_flag = 1
        \"\"\" 作者 \"\"\"


class Cache:
    def __init__(self):
        self.x = 1
"""

NEW_CHARA = """
class Character:
    def __init__(self):
        self.author_flag = 1
        \"\"\" 作者 \"\"\"
        self.mod_data: Dict[str, dict] = {}
        \"\"\" mod 数据 \"\"\"


class Cache:
    def __init__(self):
        self.x = 1
"""

print("==== 放行 ====")
ok("无改动", OLD_H1, OLD_H1)
ok("H1 形状 + import + 注释", OLD_H1, NEW_H1)
ok("if v is not None 包裹原写入块", OLD_WRAP, NEW_WRAP)
ok("增量钩子 / 通知钩子 / 元组自赋值 / 列表自赋值", OLD_MISC, NEW_MISC)
ok("Character.__init__ 白名单字段", OLD_CHARA, NEW_CHARA, path="Script/Core/game_type.py")

print("==== 拒绝：语义闸 ====")
bad("未知钩子名", OLD_H1, NEW_H1.replace("mod_hook.state_gain", "mod_hook.state_gian"))
bad("上下文参数是调用表达式", OLD_H1, NEW_H1.replace("state_id, change_data, target_change)", "state_id, change_data, target_change.pop())"))
bad("上下文参数是下标表达式", OLD_H1, NEW_H1.replace("character_id, state_id, change_data", "character_id, state_id[0], change_data"))
bad("关键字参数", OLD_H1, NEW_H1.replace("change_data, target_change)", "change_data, t=target_change)"))
bad("stop_on_none 钩子缺守卫", OLD_H1, NEW_H1.replace("    if final_value is None:\n        return\n", ""))
bad("守卫里夹带逻辑", OLD_H1, NEW_H1.replace("        return\n", "        final_value = 0\n"))
bad("结果赋给别的变量", OLD_H1, NEW_H1.replace("    final_value = mod_hook.state_gain(final_value", "    other = mod_hook.state_gain(final_value"))
bad("钩子之外顺手改逻辑", OLD_H1, NEW_H1.replace("99999", "9999"))
bad("包裹块里多夹一句", OLD_WRAP, NEW_WRAP.replace("            change_data.target_change[target_data.cid] += now_add_lust\n", "            change_data.target_change[target_data.cid] += now_add_lust\n            target_data.extra = 1\n"))
bad(
    "把块外的愤怒语句包进块里",
    OLD_WRAP,
    NEW_WRAP.replace("\n        target_data.angry_point += 5\n", "\n            target_data.angry_point += 5\n"),
)
bad("包裹块有 else", OLD_WRAP, NEW_WRAP.replace("        target_data.angry_point += 5\n", "        else:\n            pass\n        target_data.angry_point += 5\n"))
bad("mod_hook 当参数传", OLD_MISC, NEW_MISC.replace("    mod_hook.desire_written(character_data)\n", "    print(mod_hook)\n"))
bad("取钩子属性不调用", OLD_MISC, NEW_MISC.replace("    mod_hook.desire_written(character_data)\n", "    mod_hook.desire_written.register(print, 'x')\n"))
bad("从别处导入 mod_hook", OLD_H1, NEW_H1.replace("from Script.Core import cache_control, game_type, mod_hook", "from Script.Core import cache_control, game_type\nfrom evil import mod_hook"))
bad("白名单字段写在别的方法", OLD_CHARA + "\n    def reset(self):\n        pass\n", NEW_CHARA.replace("        self.mod_data: Dict[str, dict] = {}\n        \"\"\" mod 数据 \"\"\"\n", "") + "\n    def reset(self):\n        pass\n        self.mod_data: Dict[str, dict] = {}\n", path="Script/Core/game_type.py")
bad("白名单字段写在别的文件", OLD_CHARA, NEW_CHARA, path="Script/Core/other.py")
bad("白名单字段写到 Cache", OLD_CHARA, OLD_CHARA.replace("        self.x = 1\n", "        self.x = 1\n        self.mod_data: Dict[str, dict] = {}\n"), path="Script/Core/game_type.py")

print("==== 拒绝：文本闸 ====")
bad("AST 相同但改了引号", "x = 'a'\ny = 1\n", 'x = "a"\ny = 1\n')
bad("AST 相同但拆了行", "x = f(1, 2)\n", "x = f(\n    1, 2)\n")

print("==== 路径闸 ====")
check("允许新增 mod_hook.py", not lint.check_paths([("A", "Script/Core/mod_hook.py")]))
check("允许修改 Script 下已有 py", not lint.check_paths([("M", "Script/Settle/default.py")]))
check("允许 mod/ .agents/ .scratch/", not lint.check_paths([("A", "mod/lewd_tattoo/x.py"), ("M", ".agents/a.md"), ("A", ".scratch/b")]))
check("拒绝新增其他本体文件", lint.check_paths([("A", "Script/Core/evil.py")]))
check("拒绝删除本体文件", lint.check_paths([("D", "Script/Settle/default.py")]))
check("拒绝改名", lint.check_paths([("R", "Script/Settle/default.py")]))
check("拒绝改 CSV", lint.check_paths([("M", "data/csv/InstructConfig.csv")]))
check("拒绝改 config.ini", lint.check_paths([("M", "config.ini")]))
check("拒绝改 Script 下非 py", lint.check_paths([("M", "Script/System/x.md")]))

print("==== 真实工作区 ====")
real_errors = lint.run("main")
check("当前工作区相对 main 通过三道闸", not real_errors, real_errors)

finish()
