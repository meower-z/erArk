# -*- coding: UTF-8 -*-
"""
行为快照：逐步记下游戏状态，比较两次运行
========================================
记录：每一步调用 capture(cache) 取一份状态，名字 -> 值。名字固定、可读，例如
    clock                          游戏时间
    chara.12.position              角色 12 所在场景
    chara.12.behavior.behavior_id  角色 12 的行为id
    scene.中枢/会议室.occupants     场景里的角色id（排序；只记有人的场景）
    scene.中枢/会议室.close_flag    场景的关门状态（只记关着门的场景）
值只有 JSON 能表达的数据（布尔、整数、浮点、字符串、列表、以字符串为键的字典），集合排序成列表，不会是 null。

文件：每行「步<TAB>名字<TAB>值的 JSON」。第一步写下全部名字，之后每步只写变了、新出现或消失的名字，消失的名字值写 null，
所以文件里一行就是一处变化。步是这一步结束时的游戏时间，如 2020-12-22 10:05。

比较：python -m tests.snapshot compare <基准文件> <新文件> [--allow <放行文件>]
把两份文件还原成每一步的全部状态，逐步逐名比较；一处差异是 (步, 名字, 基准值, 新值)，某一边没有这个名字时值记作 null；
某一边整步缺失时只报一处名为 step 的差异，有这一步的一边值为 "present"，另一边为 null。
放行文件是 JSON 列表，每条放行一处差异：
    {"step": "2020-12-22 10:05", "name": "chara.12.position", "baseline": "中枢/走廊", "new": "中枢/会议室", "reason": "为什么允许"}
四个字段都要与差异完全相同，reason 不能为空，没有通配符。
没被放行的差异、没有用上的放行都让比较失败（退出码 1）；放行了的差异照样列出。
"""
import argparse
import json
import os
import sys

ABSENT = None
""" 比较时，一边没有的名字或步记作这个值（记录的值不会是 None） """

SKIPPED_SP_FLAGS = ("unnormal_flag",)
""" 不记的 sp_flag 字段：unnormal_flag 只为旧存档保留，游戏不读写它 """

POINTS = ("hit_point", "mana_point", "sanity_point", "eja_point", "semen_point", "hunger_point", "tired_point", "sleep_point", "urinate_point", "desire_point", "angry_point", "drunk_point")
""" 每个角色都记的数值 """


def canonical(value):
    """
    把值转成只含 JSON 数据的形式：集合排序成列表，元组转列表，字典的键转成字符串并排序
    Keyword arguments:
    value -- 任意值
    Return arguments:
    bool | int | float | str | list | dict -- 转换后的值
    功能描述:
        None 或其他对象抛 TypeError：快照只收确定、可比较的数据，不用 repr 兜底。
    """
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [canonical(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(canonical(item) for item in value)
    if isinstance(value, dict):
        return {str(key): canonical(value[key]) for key in sorted(value, key=str)}
    raise TypeError(f"快照不收 {type(value).__name__} 类型的值：{value!r}")


def capture(cache) -> dict:
    """
    取当前游戏状态的一份快照
    Keyword arguments:
    cache -- 游戏缓存
    Return arguments:
    dict[str, object] -- 名字: 值
    功能描述:
        时钟；玩家与本局每名干员的位置、行为、状态、交互对象、各项数值、对博士的好感与信赖、身上的衣服、除 unnormal_flag 外的全部 sp_flag；
        有人的场景里的角色，关着门的场景的关门状态。
    """
    state = {"clock": cache.game_time.strftime("%Y-%m-%d %H:%M")}
    for cid in sorted({0} | set(cache.npc_id_got)):
        cd = cache.character_data[cid]
        prefix = f"chara.{cid}."
        values = {
            "name": cd.name,
            "position": "/".join(cd.position),
            "state": cd.state,
            "target_character_id": cd.target_character_id,
            "behavior.behavior_id": cd.behavior.behavior_id,
            "behavior.start_time": cd.behavior.start_time.strftime("%Y-%m-%d %H:%M"),
            "behavior.duration": cd.behavior.duration,
            "behavior.move_target": cd.behavior.move_target,
            "behavior.move_final_target": cd.behavior.move_final_target,
            "favorability": cd.favorability.get(0, 0),
            "trust": cd.trust,
            "cloth_wear": cd.cloth.cloth_wear,
        }
        values.update({point: getattr(cd, point) for point in POINTS})
        values.update({f"sp_flag.{key}": value for key, value in cd.sp_flag.__dict__.items() if key not in SKIPPED_SP_FLAGS})
        for key, value in values.items():
            state[prefix + key] = canonical(value)
    for scene in cache.scene_data.values():
        prefix = f"scene.{scene.scene_path.replace(os.sep, '/')}."
        if scene.character_list:
            state[prefix + "occupants"] = canonical(scene.character_list)
        if scene.close_flag:
            state[prefix + "close_flag"] = scene.close_flag
    return state


class Recorder:
    """逐步收集快照，写成「步<TAB>名字<TAB>值」的文件，只写每步变了、新出现或消失的名字"""

    def __init__(self):
        """
        Keyword arguments:
        无
        Return arguments:
        无
        """
        self.lines = []
        """ 已记下的行：(步, 名字, 值的 JSON) """
        self._last = {}
        """ 上一步的全部状态 """
        self._steps = set()
        """ 已记下的步 """

    def record(self, step: str, state: dict):
        """
        记下一步：写出与上一步相比变了、新出现或消失的名字，消失的名字值为 null
        Keyword arguments:
        step -- 步名（游戏时间）
        state -- capture() 的结果
        Return arguments:
        无
        功能描述:
            步名重复抛 ValueError：还原时一步只能对应一份状态。
        """
        if step in self._steps:
            raise ValueError(f"步 {step} 记了两次")
        self._steps.add(step)
        for name in sorted(set(state) | set(self._last)):
            value = state.get(name, ABSENT)
            if self._last.get(name, ABSENT) != value:
                self.lines.append((step, name, json.dumps(value, ensure_ascii=False, sort_keys=True)))
        self._last = dict(state)

    def write(self, path: str):
        """
        写出快照文件
        Keyword arguments:
        path -- 文件路径
        Return arguments:
        无
        """
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for line in self.lines:
                f.write("\t".join(line) + "\n")


def load(path: str) -> dict:
    """
    读快照文件，还原每一步的全部状态
    Keyword arguments:
    path -- 文件路径
    Return arguments:
    dict[str, dict[str, object]] -- 步: (名字: 值)，按文件里的顺序
    """
    steps = {}
    state = {}
    with open(path, encoding="utf-8") as f:
        for number, line in enumerate(f, 1):
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3:
                raise ValueError(f"{path}:{number} 不是「步<TAB>名字<TAB>值」")
            step, name, value = parts
            if step in steps and steps[step] is not state:
                raise ValueError(f"{path}:{number} 步 {step} 的行不连续")
            if step not in steps:
                state = dict(state)
                steps[step] = state
            value = json.loads(value)
            if value is ABSENT:
                state.pop(name, None)
            else:
                state[name] = value
    return steps


def diff(baseline: dict, new: dict) -> list:
    """
    逐步逐名比较两次运行
    Keyword arguments:
    baseline -- load() 读出的基准
    new -- load() 读出的新运行
    Return arguments:
    list[tuple[str, str, object, object]] -- 差异 (步, 名字, 基准值, 新值)，按基准的步序，新运行多出的步排在最后
    功能描述:
        一边没有的步或名字，值记作 ABSENT；整步缺失时报一处 (步, "step", ...) 差异，不逐名展开。
    """
    differences = []
    for step in list(baseline) + [step for step in new if step not in baseline]:
        if step not in baseline or step not in new:
            differences.append((step, "step", "present" if step in baseline else ABSENT, "present" if step in new else ABSENT))
            continue
        old_state, new_state = baseline[step], new[step]
        for name in sorted(set(old_state) | set(new_state)):
            old_value, new_value = old_state.get(name, ABSENT), new_state.get(name, ABSENT)
            if old_value != new_value:
                differences.append((step, name, old_value, new_value))
    return differences


def load_allowances(path: str) -> list:
    """
    读放行文件并核对格式
    Keyword arguments:
    path -- 文件路径
    Return arguments:
    list[dict] -- 放行条目，每条有 step、name、baseline、new、reason
    """
    with open(path, encoding="utf-8") as f:
        allowances = json.load(f)
    if not isinstance(allowances, list):
        raise ValueError(f"{path} 应是 JSON 列表")
    for index, allowance in enumerate(allowances):
        if not isinstance(allowance, dict) or set(allowance) != {"step", "name", "baseline", "new", "reason"}:
            raise ValueError(f"{path} 第 {index} 条放行应正好有 step、name、baseline、new、reason 五个字段")
        if not isinstance(allowance["reason"], str) or not allowance["reason"].strip():
            raise ValueError(f"{path} 第 {index} 条放行没写 reason")
    return allowances


def compare(baseline: dict, new: dict, allowances: list) -> tuple:
    """
    比较两次运行并套用放行
    Keyword arguments:
    baseline -- load() 读出的基准
    new -- load() 读出的新运行
    allowances -- load_allowances() 读出的放行
    Return arguments:
    tuple[list, list, list] -- (没放行的差异, 放行了的差异及其理由, 没用上的放行)
    功能描述:
        一条放行只放行与它四个字段完全相同的一处差异。
    """
    unused = list(allowances)
    unexpected, allowed = [], []
    for difference in diff(baseline, new):
        match = next((a for a in unused if (a["step"], a["name"], a["baseline"], a["new"]) == difference), None)
        if match is None:
            unexpected.append(difference)
        else:
            unused.remove(match)
            allowed.append((difference, match["reason"]))
    return unexpected, allowed, unused


def _show(value) -> str:
    """
    差异里的值的显示形式
    Keyword arguments:
    value -- 值
    Return arguments:
    str -- JSON 文本
    """
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def main(argv=None) -> int:
    """
    命令行入口：compare <基准文件> <新文件> [--allow <放行文件>]
    Keyword arguments:
    argv -- 命令行参数，默认 sys.argv[1:]
    Return arguments:
    int -- 退出码：0 没有未放行的差异也没有未用的放行，1 其他情况
    """
    parser = argparse.ArgumentParser(prog="python -m tests.snapshot")
    sub = parser.add_subparsers(dest="command", required=True)
    cmp_parser = sub.add_parser("compare", help="比较两次运行的快照")
    cmp_parser.add_argument("baseline")
    cmp_parser.add_argument("new")
    cmp_parser.add_argument("--allow", help="放行文件（JSON 列表）")
    args = parser.parse_args(argv)
    allowances = load_allowances(args.allow) if args.allow else []
    unexpected, allowed, unused = compare(load(args.baseline), load(args.new), allowances)
    for step, name, old, new in unexpected:
        print(f"差异\t{step}\t{name}\t{_show(old)} -> {_show(new)}")
    for (step, name, old, new), reason in allowed:
        print(f"已放行\t{step}\t{name}\t{_show(old)} -> {_show(new)}\t{reason}")
    for allowance in unused:
        print(f"未用的放行\t{allowance['step']}\t{allowance['name']}\t{_show(allowance['baseline'])} -> {_show(allowance['new'])}")
    print(f"差异 {len(unexpected)}，已放行 {len(allowed)}，未用的放行 {len(unused)}")
    return 1 if unexpected or unused else 0


if __name__ == "__main__":
    sys.exit(main())
