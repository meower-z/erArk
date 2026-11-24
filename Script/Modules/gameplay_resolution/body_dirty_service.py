"""
身体污秽与状态栏计算服务（body_dirty_service）
==============================================
封装角色身体栏所需的透视等级、暴露部位、各部位污浊与差分文本编号、
头发避孕套装饰、同场景体外无壳卵、腹部累计、灌肠及附带状态文本的纯数据计算。
本模块仅依赖配置、领域数据与无界面工具，不导入任何界面、窗口或 Tk 模块。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config, normal_config
from Script.Core import game_type, get_text, num
from Script.Design import attr_calculation, game_time
from Script.Modules.domains import (
    abilities,
    activity,
    dirty,
    first_record,
    flags,
    h_state,
    identity,
    needs,
    player_ability,
    player_collection,
    pregnancy,
    status,
    wardrobe,
)
from Script.System.Item_System import condom_handle
from Script.System.Pregnancy_System import pregnancy_constant

_: FunctionType = get_text._
""" 翻译接口。 """

ABDOMEN_PART_IDS: frozenset[int] = frozenset({6, 7, 8, 15})
CAVITY_PART_IDS: frozenset[int] = frozenset({7, 9, 15})
INSERT_POSITION_WITH_POSE: frozenset[int] = frozenset({6, 7, 8, 9})
OPTIONAL_PART_TALENTS: dict[int, int] = {12: 113, 13: 112, 14: 111}
BODY_CLOTH_PARTS: dict[int, tuple[int, ...]] = {
    0: (0,),
    1: (4,),
    2: (4,),
    3: (5, 6),
    4: (5,),
    5: (7,),
    6: (9,),
    8: (9,),
    9: (9,),
    11: (11,),
    16: (8, 9),
    17: (8,),
    18: (5,),
}
_AGE_TALENTS: tuple[int, ...] = (101, 102, 103, 104, 105, 106, 107)
PART_TALENT_GROUPS: dict[int, tuple[int, ...]] = {
    1: _AGE_TALENTS,
    2: _AGE_TALENTS,
    3: (121, 122, 123, 124, 125),
    4: _AGE_TALENTS,
    5: _AGE_TALENTS,
    8: (126, 127, 128),
    10: (129, 130),
    11: (131, 132),
}


@dataclass(frozen=True)
class BodyDirtyReport:
    """角色身体污秽与状态栏的纯数据构建结果。"""

    part_lines: tuple[str, ...]
    rendered_text: str

    @property
    def has_content(self) -> bool:
        """报告是否包含至少一条可展示的状态文本。"""
        return bool(self.part_lines)


def get_visual_level(player_id: int = 0) -> int:
    """计算角色当前生效的透视等级（0 无、1 服装、2 腔内、3 生理）。"""
    if not player_ability.get(player_id, "visual"):
        return 0
    talent = abilities.talent(player_id)
    if talent[309]:
        return 3
    if talent[308]:
        return 2
    return 1


def get_exposed_body_parts(character_id: int) -> list[int]:
    """返回指定角色当前未被衣物遮挡且实际拥有的身体部位编号列表。"""
    talent = abilities.talent(character_id)
    cloth_wear = wardrobe.of(character_id).cloth_wear
    exposed: list[int] = []
    for body_part_cid in game_config.config_body_part:
        req_talent = OPTIONAL_PART_TALENTS.get(body_part_cid)
        if req_talent is not None and not talent[req_talent]:
            continue
        cloth_slots = BODY_CLOTH_PARTS.get(body_part_cid, ())
        if all(not cloth_wear[slot] for slot in cloth_slots):
            exposed.append(body_part_cid)
    return exposed


def get_soft_egg_semen_level(semen_count: float) -> int:
    """根据体外无壳卵上的精液量计算污浊等级（0 至 15）。"""
    if semen_count <= 0:
        return 0
    base_volume = pregnancy_constant.SOFT_EGG_SEMEN_LEVEL_MAX_VOLUME
    if semen_count < base_volume:
        return attr_calculation.get_semen_level_by_volume(
            semen_count, base_volume
        )
    extra_level = int(
        (semen_count - base_volume)
        / pregnancy_constant.SOFT_EGG_SEMEN_LEVEL_EXTRA_STEP
    )
    return min(10 + extra_level, pregnancy_constant.SOFT_EGG_SEMEN_LEVEL_MAX)


def _first_talent_id(character_id: int, candidates: tuple[int, ...]) -> int:
    """返回候选素质元组中角色首个持有的素质编号，未持有时返回 0。"""
    talent = abilities.talent(character_id)
    for talent_id in candidates:
        if talent[talent_id]:
            return talent_id
    return 0


def get_dirty_diff_text_cid(
    character_id: int, body_part_index: int, semen_level: int
) -> str:
    """获取指定角色与身体部位的精液污浊差分文本编号，无对应分组时返回空字符串。"""
    part_name = game_config.config_body_part[body_part_index].name
    base_part_name = _(part_name, revert_translation=True)
    if body_part_index in {6, 7}:
        talent = abilities.talent(character_id)
        if talent[21] == 1:
            stage = "妊娠"
        elif talent[20] == 1:
            stage = "受精"
        else:
            stage = "未孕"
        return f"{base_part_name}{stage}精液污浊{str(semen_level)}"
    candidates = PART_TALENT_GROUPS.get(body_part_index)
    if candidates is None:
        return ""
    talent_name = game_config.config_talent[
        _first_talent_id(character_id, candidates)
    ].name
    return f"{base_part_name}{talent_name}精液污浊{str(semen_level)}"


def format_body_dirty_text(part_lines: Sequence[str]) -> str:
    """按身体栏排版规则拼接全部状态条目，每逢第 6 的倍数项且末尾无换行时补换行。"""
    if not part_lines:
        return ""
    rendered = ""
    last_idx = len(part_lines) - 1
    for idx, now_text in enumerate(part_lines):
        rendered += now_text
        if idx % 6 == 0 and idx != 0 and not now_text.endswith("\n"):
            rendered += "\n"
        if idx == last_idx and not rendered.endswith("\n"):
            rendered += "\n"
    return rendered


def _tagged_dirty_line(
    text_index: str,
    full_dirty: bool,
    label: str,
    tag: str,
    *,
    bracket_compact: bool = False,
) -> str:
    """从 dirty_full 或 dirty 文本表取出指定条目并按详略模式包装。"""
    if full_dirty:
        text = game_config.ui_text_data["dirty_full"][text_index]
        return f" {label}<{tag}>{text}</{tag}>\n"
    text = game_config.ui_text_data["dirty"][text_index]
    return f" <{text}>" if bracket_compact else f" {text}"


def _is_first_sex_today(character_id: int) -> bool:
    """判断角色是否在游戏当日发生初次 V 破处（玩家为童贞记录）。"""
    cid = identity.of(character_id).cid
    if character_id == 0:
        first_time = first_record.get(cid, "first_sex_time")
    else:
        record = first_record.part_sex(cid, 6)
        if record is None:
            return False
        first_time = record["time"]
    return game_time.count_day_for_datetime(first_time, game_time.now()) == 0


def _urine_text_index(character_id: int) -> str:
    """根据角色当前尿意占比返回对应的尿液污浊文本键。"""
    ratio = needs.of(character_id)["urine"] / 240
    if ratio <= 0.125:
        return "尿液0"
    if ratio <= 0.49:
        return "尿液1"
    if ratio <= 0.79:
        return "尿液2"
    return "尿液3" if ratio < 1.5 else "尿液4"


def _love_juice_text_index(juice_val: num.Num) -> str:
    """根据爱液状态等级返回对应的爱液污浊文本键。"""
    level = attr_calculation.get_status_level(juice_val)
    if level <= 2:
        return "爱液1"
    if level <= 4:
        return "爱液2"
    return "爱液3" if level <= 6 else "爱液4"


def _semen_part_text(
    character_id: int,
    part_idx: int,
    part_name: str,
    semen_level: int,
    full_dirty: bool,
) -> str:
    """生成单个身体部位的精液污浊条目，详细模式优先选用差分文本。"""
    dirty_text_cid = (
        f"{_(part_name, revert_translation=True)}精液污浊{str(semen_level)}"
    )
    if not full_dirty:
        context = game_config.ui_text_data["dirty"][dirty_text_cid]
        return f" {part_name}{context}"
    diff_cid = get_dirty_diff_text_cid(character_id, part_idx, semen_level)
    if (
        diff_cid != ""
        and diff_cid in game_config.ui_text_data["dirty_full_diff"]
    ):
        context = game_config.ui_text_data["dirty_full_diff"][diff_cid]
    else:
        context = game_config.ui_text_data["dirty_full"][dirty_text_cid]
    return f"  [{part_name}]:<semen>{context}</semen>\n"


def _hair_condom_text(
    target_cid: int,
    part_name: str,
    has_hair_semen: bool,
    lines: list[str],
    full_dirty: bool,
) -> str | None:
    """生成头发上的避孕套装饰条目，未挂避孕套时返回 None。"""
    count = condom_handle.get_decoration_count(target_cid, 0, 0)
    if not count:
        return None
    if full_dirty:
        level = condom_handle.get_decoration_level(count)
        deco_cid = (
            f"{_(part_name, revert_translation=True)}避孕套装饰{str(level)}"
        )
        deco_ctx = game_config.ui_text_data["condom_dirty"][deco_cid]
        now_text: str = f"  [{part_name}]:<semen>{deco_ctx}</semen>\n"
    else:
        now_text = _(" {0}上挂着{1}个用过的避孕套").format(
            part_name, str(count)
        )
    if has_hair_semen and lines and not lines[-1].endswith("\n"):
        now_text = "\n" + now_text
    return now_text


def _collect_body_part_lines(
    character_id: int,
    target_cid: int,
    target_dirty: game_type.DIRTY,
    visual_flag: int,
    full_dirty: bool,
    lines: list[str],
) -> num.Num:
    """遍历全部身体部位追加可见污浊条目，并返回腹部四部位累计精液量。"""
    exposed_parts = get_exposed_body_parts(target_cid)
    body_semen = dict(target_dirty.body_semen)
    abdomen_all_semen: num.Num = 0
    for part_idx in range(len(game_config.config_body_part)):
        part_name = game_config.config_body_part[part_idx].name
        if len(body_semen) <= part_idx:
            body_semen[part_idx] = [part_name, 0, 0, 0]
        if part_idx in ABDOMEN_PART_IDS:
            abdomen_all_semen += body_semen[part_idx][1]
        if part_idx not in exposed_parts and visual_flag == 0:
            continue
        if visual_flag <= 1 and part_idx in CAVITY_PART_IDS:
            continue
        if part_idx == 6:
            juice_val = status.of(target_cid)[8]
            if juice_val:
                lines.append(
                    _tagged_dirty_line(
                        _love_juice_text_index(juice_val),
                        full_dirty,
                        _(" [爱液]:"),
                        "lavender",
                    )
                )
            if (
                visual_flag >= 2
                and not abilities.talent(target_cid)[0]
                and _is_first_sex_today(target_cid)
            ):
                if full_dirty:
                    blood = game_config.ui_text_data["dirty_full"]["破处血1"]
                    lines.append(f"  [破处]:{blood}\n")
                else:
                    blood = game_config.ui_text_data["dirty"]["破处血1"]
                    lines.append(f" <{blood}>")
        if part_idx == 9:
            lines.append(
                _tagged_dirty_line(
                    _urine_text_index(target_cid),
                    full_dirty,
                    _(" [尿液]:"),
                    "khaki",
                )
            )
        semen_level = body_semen[part_idx][2]
        if semen_level:
            lines.append(
                _semen_part_text(
                    character_id, part_idx, part_name, semen_level, full_dirty
                )
            )
        if part_idx == 0:
            condom_text = _hair_condom_text(
                target_cid, part_name, bool(semen_level), lines, full_dirty
            )
            if condom_text is not None:
                lines.append(condom_text)
    return abdomen_all_semen


def _collect_soft_egg_lines(full_dirty: bool, lines: list[str]) -> None:
    """为玩家所在场景中的每枚体外无壳卵追加一条精液污浊文本。"""
    if not player_collection.has_soft_eggs():
        return
    player_pos = list(activity.position(0))
    for egg_data in player_collection.get("soft_eggs").values():
        if list(egg_data["position"]) != player_pos:
            continue
        mother_id = egg_data["mother_id"]
        mother_name = (
            identity.of(mother_id).name
            if identity.exists(mother_id)
            else _("某人")
        )
        egg_name = _("{0}排出的卵块").format(mother_name)
        egg_semen_count = int(egg_data["semen_count"])
        if full_dirty:
            egg_level = get_soft_egg_semen_level(egg_semen_count)
            count_text = _("({egg_semen_count}ml精液)").format(
                egg_semen_count=egg_semen_count
            )
            egg_ctx = game_config.ui_text_data["soft_egg_dirty_full"][
                f"体外卵精液污浊{str(egg_level)}"
            ]
            lines.append(
                _("  [卵块]:")
                + f"<semen>{egg_name}{count_text}：{egg_ctx}</semen>\n"
            )
        else:
            egg_ctx = game_config.ui_text_data["dirty"][
                "体外卵精液污浊"
            ].format(egg_semen_count)
            lines.append(f" {egg_name}{egg_ctx}")


def _append_h_state_lines(
    player_cid: int, target_cid: int, lines: list[str]
) -> None:
    """追加插入位置与体位、捆绑状态、H 身体道具、避孕套存量池与香薰条目。"""
    target_hs = h_state.view(target_cid)
    if target_hs.insert_position != -1:
        pos = target_hs.insert_position
        insert_text = " "
        sex_pos = h_state.get(player_cid, "current_sex_position")
        if pos in INSERT_POSITION_WITH_POSE and sex_pos != -1:
            pose_text = game_config.ui_text_data["h_state"][
                f"体位{str(sex_pos)}"
            ]
            insert_text += _("以{0}").format(pose_text)
        insert_text += game_config.ui_text_data["h_state"][
            f"阴茎位置{str(pos)}"
        ]
        lines.append(insert_text)
    if target_hs.bondage:
        bondage_name = game_config.config_bondage[target_hs.bondage].name
        lines.append(_(" 被绳子捆成了{0}").format(bondage_name))
    sex_toy_level = flags.get(target_cid, "sex_toy_level")
    lv_labels = {0: _("(关)"), 1: _("(弱)"), 2: _("(中)")}
    lv_text = lv_labels.get(sex_toy_level, _("(强)"))
    item_text = ""
    for idx in range(len(target_hs.body_item)):
        if target_hs.body_item[idx][1]:
            name = target_hs.body_item[idx][0]
            if game_config.config_body_item[idx].type == 2:
                name += lv_text
            item_text += f" {name}"
    if item_text:
        lines.append(item_text)
    used_condoms = condom_handle.get_used_condoms()
    if used_condoms:
        lines.append(
            _(" 现留有{0}个用过的避孕套（{1}）").format(
                str(len(used_condoms)),
                "、".join(f"{ml}ml" for ml in used_condoms),
            )
        )
    aromatherapy_id = flags.get(target_cid, "aromatherapy")
    if aromatherapy_id != 0:
        aroma_name = game_config.config_aromatherapy_recipes[
            aromatherapy_id
        ].name
        lines.append(f" <{aroma_name}>")


def build_body_dirty_report(character_id: int) -> BodyDirtyReport:
    """构建交互对象的身体污秽与状态栏完整纯数据报告。"""
    player_cid = identity.of(0).cid
    target_cid = identity.of(activity.target(0)).cid
    full_dirty = bool(normal_config.system_setting.draw_setting[10])
    visual_flag = get_visual_level(0)
    target_dirty = dirty.view(target_cid)

    lines: list[str] = []
    abdomen_all_semen = _collect_body_part_lines(
        character_id, target_cid, target_dirty, visual_flag, full_dirty, lines
    )
    _collect_soft_egg_lines(full_dirty, lines)

    if abdomen_all_semen:
        abdomen_level = attr_calculation.get_semen_now_level(
            abdomen_all_semen, 20, 0
        )
        if abdomen_level >= 2:
            lines.append(
                _tagged_dirty_line(
                    f"腹部整体精液污浊{str(abdomen_level)}",
                    full_dirty,
                    _(" [腹部]:"),
                    "semen",
                )
            )
    if target_dirty.a_clean:
        lines.append(
            _tagged_dirty_line(
                f"灌肠{str(target_dirty.a_clean)}",
                full_dirty,
                _(" [肠道]:"),
                "semen",
                bracket_compact=True,
            )
        )
    if target_dirty.enema_capacity:
        lines.append(
            _tagged_dirty_line(
                f"灌肠液量{str(target_dirty.enema_capacity)}",
                full_dirty,
                _(" [灌肠]:"),
                "semen",
                bracket_compact=True,
            )
        )
    if visual_flag >= 2 and needs.of(target_cid)["milk"]:
        lines.append(
            _(" 乳汁量为{0}ml").format(num.shown(needs.of(target_cid)["milk"]))
        )
    if visual_flag >= 3:
        target_preg = pregnancy.of(target_cid)
        period_type = game_config.config_reproduction_period[
            target_preg.reproduction_period
        ].type
        repro = game_config.ui_text_data["h_state"][f"生理期{period_type}"]
        fert = _("受精概率{0}%").format(target_preg.fertilization_rate)
        desire = _("欲望值{0}%").format(needs.of(target_cid)["desire"])
        lines.append(_(" 当前为{0},{1},{2}").format(repro, fert, desire))

    _append_h_state_lines(player_cid, target_cid, lines)

    part_lines = tuple(lines)
    return BodyDirtyReport(
        part_lines=part_lines,
        rendered_text=format_body_dirty_text(part_lines),
    )
