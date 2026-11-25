"""
PRTS 面板无界面服务（prts_service）
===================================
本模块提供 PRTS 问答列表、回答文本格式化、角色口上文件体积扫描、当前版本标签、版本选项列表与版本选择写入。
本模块公开常量 TEXT_DIRS 与只读数据类 Question、VersionOption。
本模块公开函数 questions、answer_text、version_sizes、version_label、version_options 与 choose_version。
本模块不执行界面绘制，也不导入 Script.UI、Script.Settle 或 Tk 模块。
"""

import glob
import os
from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config, normal_config
from Script.Core import get_text
from Script.Modules.domains import identity

_: FunctionType = get_text._
""" 翻译api """
TEXT_DIRS = (
    os.path.join("data", "talk", "chara"),
    os.path.join("data", "event", "chara"),
)
""" 角色口上与事件文本文件的相对扫描目录元组。 """


@dataclass(frozen=True, slots=True)
class Question:
    """PRTS 分类下的单条问题数据，包含子分类编号 son_type 与带编号前缀的问题文本 text。"""

    son_type: int
    text: str


@dataclass(frozen=True, slots=True)
class VersionOption:
    """角色文本版本切换界面的单条版本选项，包含提示编号 tip_cid、版本编号 version_id、标题 title 与说明文本 text。"""

    tip_cid: int
    version_id: int
    title: str
    text: str


def _chara(adv_id: int) -> identity.Identity:
    """
    按剧情角色编号获取角色身份视图，该角色不存在时回退为角色 0（玩家）。
    Keyword arguments:
    adv_id -- int，角色剧情编号
    Return arguments:
    identity.Identity -- 对应角色或玩家的角色身份视图
    """
    return identity.of(adv_id if identity.exists(adv_id) else 0)


def questions(father_type: int) -> list[Question]:
    """
    按配置顺序返回指定父分类下的 PRTS 问题列表，每条问题文本附带左补零至三位的子分类编号前缀。
    Keyword arguments:
    father_type -- int，PRTS 问答父分类编号
    Return arguments:
    list[Question] -- 按配置顺序排列的问题数据列表
    """
    return [
        Question(son_type, f"[{str(son_type).rjust(3, '0')}]{pair[0].text}")
        for son_type, pair in game_config.config_prts_data[father_type].items()
    ]


def answer_text(father_type: int, son_type: int) -> str:
    """
    读取指定父分类与子分类对应的 PRTS 回答文本，按字面量 \\n 拆行并为每行添加前置空格与换行符。
    Keyword arguments:
    father_type -- int，PRTS 问答父分类编号
    son_type -- int，PRTS 问答子分类编号
    Return arguments:
    str -- 格式化后的回答文本
    """
    answer = game_config.config_prts_data[father_type][son_type][1]
    return "".join(f" {line}\n" for line in answer.text.split("\\n"))


def version_sizes(adv_id: int) -> dict[int, int]:
    """
    扫描当前工作目录下 TEXT_DIRS 中的角色口上与事件文件，按版本累计匹配角色名或剧情编号的字节数，
    并按 int(bytes / 1024 + 1) 换算为 KB。
    Keyword arguments:
    adv_id -- int，角色剧情编号
    Return arguments:
    dict[int, int] -- 版本编号到对应文本总大小（KB）的映射
    """
    find_name = _chara(adv_id).name
    adv_text = str(adv_id)
    totals: dict[int, int] = {}
    for directory in TEXT_DIRS:
        for path in glob.glob(os.path.join(directory, "*")):
            base = os.path.basename(path).split(".")[0]
            parts = base.split("_")
            name = parts[1] if len(parts) > 1 else ""
            version = (
                int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
            )
            if name == "" and adv_text not in base:
                continue
            if name in (find_name, adv_text):
                totals[version] = totals.get(version, 0) + os.path.getsize(path)
    return {version: int(size / 1024 + 1) for version, size in totals.items()}


def version_label(adv_id: int) -> str:
    """
    组装角色当前所选文本版本的展示标签（不含宽度填充）。
    未匹配到版本条目时主标签为“无”，匹配时优先采用文件扫描体积并在无结果或异常时回退至角色 talk_size。
    角色存在多个不同版本编号时在末尾追加版本数量后缀。
    Keyword arguments:
    adv_id -- int，角色剧情编号
    Return arguments:
    str -- 当前版本展示标签文本
    """
    tip_cids = game_config.config_tip_chara_data_by_adv[adv_id]
    now_version = normal_config.system_setting.character_text_version[adv_id]
    label = "无"
    for tip_cid in tip_cids:
        tip = game_config.config_tip_chara_data[tip_cid]
        if tip.version_id != now_version:
            continue
        try:
            size = version_sizes(adv_id).get(tip.version_id)
        except Exception:
            size = None
        if not size:
            size = _chara(adv_id).talk_size
        label = f"by {tip.writer_name}({size}kb)"
    versions = {
        game_config.config_tip_chara_data[tip_cid].version_id
        for tip_cid in tip_cids
    }
    if len(versions) > 1:
        label += _("(有{0}个版本)").format(len(versions))
    return label


def version_options(adv_id: int) -> list[VersionOption]:
    """
    按角色提示表顺序组装该角色的全部文本版本选项。
    选项标题包含版本编号与作者名，扫描到对应体积时附带 KB 大小，命中当前设置版本时追加当前版本标记。
    Keyword arguments:
    adv_id -- int，角色剧情编号
    Return arguments:
    list[VersionOption] -- 按提示表顺序排列的版本选项列表
    """
    now_version = normal_config.system_setting.character_text_version[adv_id]
    sizes = version_sizes(adv_id)
    options = []
    for tip_cid in game_config.config_tip_chara_data_by_adv[adv_id]:
        tip = game_config.config_tip_chara_data[tip_cid]
        size = sizes.get(tip.version_id)
        title = _("版本：{0}  ").format(tip.version_id)
        title += f"by {tip.writer_name}"
        if size:
            title += f" ({size}kb)"
        if tip.version_id == now_version:
            title += _("(当前版本)")
        options.append(VersionOption(tip_cid, tip.version_id, title, tip.text))
    return options


def choose_version(adv_id: int, version_id: int) -> None:
    """
    在内存系统设置中写入指定角色选用的文本版本编号，传入 0 表示不使用任何口上版本。
    Keyword arguments:
    adv_id -- int，角色剧情编号
    version_id -- int，目标文本版本编号（0 表示不使用版本）
    Return arguments:
    None -- 无返回值
    """
    normal_config.system_setting.character_text_version[adv_id] = version_id
