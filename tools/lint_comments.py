"""
检查受跟踪 Python 文件的注释与文档字符串，以及文档里的旧缓存类名称。

对照基线 tools/lint_comments_baseline.json 检查未排除的 .py/.pyi 与文档：
1. 每文件 # 注释数不超基线（未列入为 0），首行 shebang 与第 1/2 行编码声明豁免，抑制指令计入。
2. 文档字符串经 inspect.cleandoc 清理后不超 500 字符，基线条目不超所记长度。
3. Script/ 注释与文档字符串及 DOC_FILES 禁用旧缓存类及其字段名。

用法：
  python3 tools/lint_comments.py [check]
  python3 tools/lint_comments.py update-baseline [--init]
"""

import argparse
import ast
import fnmatch
import inspect
import io
import json
import re
import subprocess
import sys
import tokenize
import tomllib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
BASELINE = "tools/lint_comments_baseline.json"
CAP = 500
DOC_FILES = tuple(
    "CLAUDE.md CLAUDE_cn.md CONTRIBUTING.md PROJECT_DESCRIPTION.md README*.md REVIEW.md docs/*.md Script/*.md".split()
)
LEGACY_SCOPE = "Script/"
CACHE_FIELDS = """
achievement ai_chat_api_key ai_chat_setting ai_setting all_npc_position_panel_move_type
all_npc_position_panel_select_type all_system_setting average_bodyfat_by_age average_height_by_age back_save_panel
base_resouce birth_type_setting character_data class_timetable_teacher_data classroom_students_data
classroom_teacher_data clothing_type_data cmd_data collect_position_list country course_data
course_school_phase_knowledge_experience course_school_phase_language_experience course_time_status
course_time_table_data current_draw_elements current_input_request current_interaction_type current_return_list
daily_intsruce debug_mode difficulty_setting dining_hall_data first_bonus font_size forbidden_npc_id game_round
game_time game_update_flow_running group_sex_mode image_id init_character_cloth_count input_cache input_cache_browsing
input_cache_draft input_position instruct_filter instruct_index_filter instruct_sex_type_filter instruct_type_filter
instruct_type_filter_cache is_H is_collection makefood_data map_data moon_phase noise_woken now_init_map_id
now_panel_id npc_id_got npc_image_index npc_name_data npc_tem_data old_character_id output_text_style
over_behavior_character pending_event_text pl_pre_behavior_instruce pl_pre_status_instruce pl_sleep_save_flag
plan_queue player_route pre_game_time pregnancy_panel_filter_type pregnancy_panel_sort_type random_npc_list recipe_data
restaurant_data rhodes_island scene_data scene_panel_show school_latitude school_longitude sex_class_mode
shoot_position show_non_h_in_hidden_sex sun_phase system_setting taiggered_event_record teacher_class_time_table
teacher_class_week_day_data teacher_course_experience teacher_phase_table teacher_school_timetable
text_one_by_one_rich_cache text_style_cache text_style_position text_wait time_stop_mode today_taiggered_event_record
total_bodyfat_by_age total_height_by_age total_number_of_people_of_all_ages wear_item_type_data web_current_major_type
web_current_minor_type web_dialog_queue web_dialog_speaker web_dialog_text web_dialog_text_color web_dialog_visible
web_dialog_wait_input web_draw_history web_draw_history_line_total web_game_state web_instruct_executing
web_instruct_executing_thread_id web_instruct_texts web_major_type_memory web_minor_dialog_queue web_mode
web_need_full_refresh web_other_texts web_selected_drug_id web_selected_item_id web_settlement_description
web_settlement_texts web_sub_panel_id web_sub_panel_mode web_sub_panel_name web_text_recording_flag web_value_changes
wframe_mouse world_setting
""".split()
CHARACTER_FIELDS = """
Originite_Prime a_sex_semen abi abi_grade ability achievement action_info adv age angry_point angry_with_player
assistant_character_id assistant_services assistant_state author_flag behavior birthday body_manage bodyfat bodyfat_tem
breast_semen chara_setting chest chest_tem child_growth cid classroom cloth cloth_off cloth_see clothing clothing_data
clothing_tem collection_character dead desire_point dirty dormitory drunk_point eja_point eja_point_max ejaculation
end_age engraving entertainment event event_id experience favorability first_a_sex_id first_a_sex_place
first_a_sex_posture first_a_sex_time first_hand_in_hand first_kiss first_kiss_id first_kiss_place first_kiss_time
first_record first_record_history first_sex_id first_sex_place first_sex_posture first_sex_time food_bag foot_semen
gold graces h_state hand_semen height hit_point hit_point_max hit_point_tem hunger_point hypnosis intimate is_follow
is_h item juel knowledge knowledge_interest language language_interest last_behavior_id_list last_hunger_time
last_move_time last_state mana_point mana_point_max mana_point_tem measurements money mother_tongue move_stop
must_settle_second_behavior_id_list must_show_second_behavior_id_list name nature nick_name nick_name_to_pl no_wear
officeroom orgasm_count orgasm_level orundum permanent_dormitory pl_ability pl_collection position pre_dormitory
pregnancy profession put_on race relationship sanity_point sanity_point_max second_behavior semen_point semen_point_max
sex sex_experience sex_experience_tem sex_grade sex_semen sleep_point social_contact social_contact_data
social_contact_last_cut_down_time social_contact_last_time sp_event_flag sp_flag state status status_data talent
talk_count talk_size talk_time target_character_id taste_semen tem_extra_semen_point text_color tired tired_point token
token_list token_text trust urethral_semen urinate_point wait_flag weight weight_tem work
""".split()
LEGACY = re.compile(
    r"\bcache_control\b|\bgame_type\.(?:Cache|Character|Rhodes_Island)\b"
    r"|\bgameplay_resolution\.draft\b|\bdraft\.py\b"
    r"|\bsave_load\.unsaved\b|\bunsaved\.py\b"
    r"|\bSaveUnpickler\b|\bPickledPatient\b|\b_reset_keeping_cache\b|\bRhodes_Island\b"
    rf"|\b[Cc]ache\.(?:{'|'.join(CACHE_FIELDS)})\b"
    rf"|\bCharacter\.(?:{'|'.join(CHARACTER_FIELDS)})\b",
    re.ASCII,
)
Baseline = dict[str, dict[str, int]]


class FileScan(NamedTuple):
    """
    单个源码文本的扫描结果：comments 为计入注释的 (行号, 文本) 列表，
    strings 为纯字符串语句的 (行号, 源码文本) 列表（含文档字符串与属性文档字符串），
    docstrings 为超限文档字符串的限定名到 (长度, 行号) 映射。
    """

    comments: list[tuple[int, str]]
    strings: list[tuple[int, str]]
    docstrings: dict[str, tuple[int, int]]


class Measure(NamedTuple):
    """
    一次仓库扫描的度量结果：comments 为文件到计入注释行号列表的映射，
    docstrings 为「路径::限定名」到 (长度, 行号) 的超限文档字符串映射，
    legacy 为「路径:行号: 名称」格式的旧缓存类名称命中列表。
    """

    comments: dict[str, list[int]]
    docstrings: dict[str, tuple[int, int]]
    legacy: list[str]


def _is_header(tok: tokenize.TokenInfo, first_line_comment: bool) -> bool:
    """
    判断注释 token 是否属于豁免的文件头：第 1 行第 0 列的 shebang，或第 1 行的 PEP 263 编码声明，
    或第 1 行为空行或注释时第 2 行的编码声明。
    Keyword arguments:
    tok -- 词法分析得到的注释 TokenInfo
    first_line_comment -- 第 1 行是否仅含空行或注释
    Return arguments:
    bool -- 属于豁免文件头时返回 True，否则返回 False
    """
    row, col = tok.start
    if row == 1 and col == 0 and tok.string.startswith("#!"):
        return True
    if row > 2 or (row == 2 and not first_line_comment):
        return False
    return tokenize.cookie_re.match(tok.line) is not None


def _def_header(tokens: list[tokenize.TokenInfo]) -> tuple[str, int] | None:
    """
    判断一条语句的 token 序列是否以 def、async def 或 class 开头，并找出括号深度为 0 的头部冒号位置。
    Keyword arguments:
    tokens -- 一条语句的非换行 token 列表
    Return arguments:
    tuple[str, int] | None -- 命中时返回 (定义名称, 冒号索引)，否则返回 None
    """
    start = 1 if tokens[0].string == "async" else 0
    if len(tokens) < start + 3 or tokens[start].string not in ("def", "class"):
        return None
    level = 0
    for index, tok in enumerate(tokens[start + 2 :], start + 2):
        if tok.type == tokenize.OP:
            level += (tok.string in "([{") - (tok.string in ")]}")
            if tok.string == ":" and level == 0:
                return tokens[start + 1].string, index
    return None


def _string_statement(
    found: FileScan, tokens: list[tokenize.TokenInfo], owner: str | None
) -> None:
    """
    处理纯字符串字面量（忽略圆括号）组成的语句，将字面量源码文本记入 found.strings。
    存在宿主 owner 且字符串经 inspect.cleandoc 处理后超过 500 字符时，
    记为该宿主的文档字符串（同名保留最长）。
    Keyword arguments:
    found -- 当前文件的扫描结果对象
    tokens -- 语句的 token 列表
    owner -- 宿主限定名，无宿主时为 None
    Return arguments:
    None -- 结果直接写入 found
    """
    parts = [t for t in tokens if t.string not in ("(", ")")]
    if not parts or any(t.type != tokenize.STRING for t in parts):
        return
    found.strings.extend((t.start[0], t.string) for t in parts)
    if owner is None or sum(len(t.string) for t in parts) <= CAP:
        return
    value = ast.literal_eval(" ".join(t.string for t in parts))
    if isinstance(value, str):
        length = len(inspect.cleandoc(value))
        if length > CAP and length >= found.docstrings.get(owner, (0, 0))[0]:
            found.docstrings[owner] = (length, parts[0].start[0])


def scan(source: str) -> FileScan:
    """
    对一份 Python 源码执行单遍 tokenize 扫描，收集计入注释、纯字符串语句及超限文档字符串，
    并为文档字符串宿主生成限定名（模块为 <module>，嵌套定义如 Outer.Inner.method）。
    Keyword arguments:
    source -- Python 源码文本
    Return arguments:
    FileScan -- 该源码的扫描结果
    """
    found = FileScan([], [], {})
    scopes: list[tuple[str, int]] = []
    depth = 0
    owner: str | None = "<module>"
    statement: list[tokenize.TokenInfo] = []
    first_line_comment = True
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        kind = tok.type
        if tok.start[0] == 1 and kind not in (tokenize.COMMENT, tokenize.NL):
            first_line_comment = False
        if kind == tokenize.COMMENT:
            if not _is_header(tok, first_line_comment):
                found.comments.append((tok.start[0], tok.string))
        elif kind == tokenize.INDENT:
            depth += 1
        elif kind == tokenize.DEDENT:
            depth -= 1
            while scopes and scopes[-1][1] > depth:
                scopes.pop()
        elif kind in (tokenize.NEWLINE, tokenize.ENDMARKER) or (
            kind == tokenize.OP and tok.string == ";"
        ):
            if not statement:
                continue
            header = _def_header(statement)
            if header is None:
                _string_statement(found, statement, owner)
                owner = None
            else:
                name, colon = header
                qualname = f"{scopes[-1][0]}.{name}" if scopes else name
                owner = qualname if colon == len(statement) - 1 else None
                if owner:
                    scopes.append((qualname, depth + 1))
                else:
                    _string_statement(found, statement[colon + 1 :], qualname)
            statement = []
        elif kind != tokenize.NL:
            statement.append(tok)
    return found


def legacy_names(line: int, text: str) -> list[tuple[int, str]]:
    """
    在起始行号为 line 的文本中查找禁用的旧缓存类及其字段名称。
    Keyword arguments:
    line -- 文本首行对应的源码行号
    text -- 待检查的文本内容
    Return arguments:
    list[tuple[int, str]] -- 每处命中的 (源码行号, 命中名称) 列表
    """
    return [
        (line + text.count("\n", 0, match.start()), match.group())
        for match in LEGACY.finditer(text)
    ]


def _matches(path: str, patterns: tuple[str, ...] | list[str]) -> bool:
    """
    判断路径是否匹配任一 fnmatch 通配模式（* 可跨过路径分隔符 /）。
    Keyword arguments:
    path -- 相对仓库根目录的文件路径
    patterns -- 通配模式序列
    Return arguments:
    bool -- 匹配任一模式时返回 True
    """
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def measure(root: Path) -> Measure:
    """
    通过 git ls-files 列出受跟踪文件，用进程池并行扫描未排除的 Python 文件，并扫描范围内文档，汇总度量结果。
    Keyword arguments:
    root -- 仓库根目录路径
    Return arguments:
    Measure -- 本次仓库扫描的度量结果
    """
    files = subprocess.run(
        ["git", "-c", "core.quotepath=off", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.split("\0")
    with open(root / "pyproject.toml", "rb") as f:
        table = tomllib.load(f).get("tool", {}).get("lint-ratchet", {})
    python = [
        path
        for path in files
        if path.endswith((".py", ".pyi"))
        and not _matches(path, table.get("exclude", []))
    ]
    result = Measure({}, {}, [])
    with ProcessPoolExecutor() as pool:
        sources = [(root / p).read_text(encoding="utf-8-sig") for p in python]
        scans = pool.map(scan, sources, chunksize=8)
        for path, found in zip(python, scans, strict=True):
            if found.comments:
                result.comments[path] = [line for line, _ in found.comments]
            for name, item in found.docstrings.items():
                result.docstrings[f"{path}::{name}"] = item
            if path.startswith(LEGACY_SCOPE):
                for line, text in found.comments + found.strings:
                    for hit, name in legacy_names(line, text):
                        result.legacy.append(f"{path}:{hit}: {name}")
    for path in files:
        if _matches(path, DOC_FILES):
            text = (root / path).read_text(encoding="utf-8-sig")
            for hit, name in legacy_names(1, text):
                result.legacy.append(f"{path}:{hit}: {name}")
    return result


def violations(found: Measure, baseline: Baseline) -> list[str]:
    """
    将扫描结果与基线对比，生成所有违规描述：每处注释数上升、每处超限文档字符串及每处禁用名称各一条。
    Keyword arguments:
    found -- 仓库扫描结果
    baseline -- 基线字典（含 comments 与 docstrings 两张表）
    Return arguments:
    list[str] -- 违规信息列表，无违规时为空列表
    """
    problems = []
    for path, lines in sorted(found.comments.items()):
        allowed = baseline["comments"].get(path, 0)
        if len(lines) > allowed:
            listed = ", ".join(map(str, lines))
            problems.append(
                f"{path}: {len(lines)} comments > {allowed} allowed"
                f" (lines {listed})"
            )
    for key, (length, line) in sorted(found.docstrings.items()):
        allowed = baseline["docstrings"].get(key, CAP)
        if length > allowed:
            path, name = key.split("::")
            problems.append(
                f"{path}:{line}: docstring of {name} has {length} characters"
                f" > {allowed} allowed"
            )
    problems.extend(f"{hit} is a deleted legacy name" for hit in found.legacy)
    return problems


def lowered(found: Measure, baseline: Baseline | None) -> Baseline:
    """
    将基线按当前扫描值单向收紧，每项取旧值与当前值的较小者，移除消失或回到默认限额内的条目。
    baseline 为 None 时直接以当前扫描值生成新基线。
    Keyword arguments:
    found -- 仓库扫描结果
    baseline -- 现有基线字典，初始化时为 None
    Return arguments:
    Baseline -- 更新后的基线字典
    """
    old = baseline or {"comments": {}, "docstrings": {}}
    comments = {path: len(lines) for path, lines in found.comments.items()}
    docstrings = {key: item[0] for key, item in found.docstrings.items()}
    if baseline is None:
        return {"comments": comments, "docstrings": docstrings}
    return {
        kind: {
            key: min(value, old[kind][key])
            for key, value in sorted(now.items())
            if key in old[kind]
        }
        for kind, now in (("comments", comments), ("docstrings", docstrings))
    }


def main(argv: list[str] | None = None) -> int:
    """
    命令行入口：解析参数并执行检查或基线更新，输出违规列表或 ok，返回进程退出码。
    Keyword arguments:
    argv -- 命令行参数列表，为 None 时读取 sys.argv
    Return arguments:
    int -- 无违规返回 0，存在违规返回 1
    """
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("check", "update-baseline"),
        default="check",
    )
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    path = args.root / BASELINE
    baseline = None if args.init else json.loads(path.read_text("utf-8"))
    found = measure(args.root)
    if args.command == "update-baseline":
        baseline = lowered(found, baseline)
        text = json.dumps(
            baseline, ensure_ascii=False, indent=1, sort_keys=True
        )
        path.write_text(text + "\n", encoding="utf-8")
    problems = violations(found, baseline or lowered(found, None))
    print("\n".join(problems) if problems else "ok")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
