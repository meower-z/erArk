"""
选择学生服务（student_select_service）
======================================
提供当前学生校验、选人行文本、候选列表构造与选中状态管理。
本模块不导入 Script.UI 与 Script.Settle。
"""

from collections.abc import Callable
from dataclasses import dataclass
from types import FunctionType

from Script.Core import get_text
from Script.Modules.domains import identity

_: FunctionType = get_text._
""" 本地化翻译函数。 """


def has_student(now_student: int) -> bool:
    """
    判断角色编号是否指向已存在的学生。
    Keyword arguments:
    now_student -- int，待判断的角色编号，未选择时为 -1
    Return arguments:
    bool -- 编号不为 -1 且角色存在时返回 True，否则返回 False
    """
    return now_student != -1 and identity.exists(now_student)


def current_student_text(now_student: int) -> str:
    """
    构造已选学生时在选人行左侧显示的当前学生文本。
    Keyword arguments:
    now_student -- int，已存在的当前学生角色编号
    Return arguments:
    str -- 含「当前学生」标签与角色姓名的本地化文本
    """
    return _("  当前学生：{0}").format(identity.of(now_student).name)


def select_button_text() -> str:
    """
    返回「选择学生」按钮的本地化标签文本。
    Return arguments:
    str -- 带方括号的「选择学生」按钮文本
    """
    return _("[选择学生]")


def select_hint_text() -> str:
    """
    返回未选择学生时绘制在选人行下方的提示文本。
    Return arguments:
    str -- 提示玩家点击「选择学生」的本地化文本
    """
    return _("\n  点击[选择学生]从名单里挑一个人，再查看或编辑她的内容\n")


def candidate_rows(
    candidate_list: list[int],
    on_select: Callable[[int], None],
    now_student: int,
) -> tuple[list[list], dict[str, int]]:
    """
    按候选名单顺序构造选人列表行数据与姓名到角色编号的映射。
    Keyword arguments:
    candidate_list -- list[int]，候选角色编号列表，跳过不存在的角色
    on_select -- Callable[[int], None]，点击角色名按钮时以角色编号调用的回调
    now_student -- int，当前选中的角色编号，用于标记列表高亮项
    Return arguments:
    tuple[list[list], dict[str, int]] -- 列表行数据与姓名到首个同名编号的映射
    """
    rows: list[list] = []
    name_to_id: dict[str, int] = {}
    for character_id in candidate_list:
        if not identity.exists(character_id):
            continue
        rows.append([character_id, on_select, [now_student]])
        name_to_id.setdefault(identity.of(character_id).name, character_id)
    return rows, name_to_id


@dataclass(slots=True)
class StudentPick:
    """单次选人流程中的选中状态，记录当前角色编号与按钮回调触发标记。"""

    student_id: int
    """ 当前选中的角色编号，初始为传入的起始编号。 """
    picked: bool = False
    """ 角色名按钮回调是否已触发。 """

    def pick(self, character_id: int) -> None:
        """
        记录按钮回调传入的角色编号并标记已通过回调选中。
        Keyword arguments:
        character_id -- int，被点击角色按钮对应的角色编号
        Return arguments:
        None -- 无返回值
        """
        self.student_id = character_id
        self.picked = True

    def result(self, answer: str, name_to_id: dict[str, int]) -> int:
        """
        返回本次选人的最终角色编号，按钮回调未触发时按返回姓名反查编号。
        角色名按钮以角色名作为返回值。测试输入桩不执行回调时，姓名反查可据此取得编号。
        Keyword arguments:
        answer -- str，选人循环退出时收到的返回值文本
        name_to_id -- dict[str, int]，角色姓名到首个同名角色编号的映射
        Return arguments:
        int -- 未触发回调且 answer 命中映射时返回映射编号，否则返回 student_id
        """
        if not self.picked and answer in name_to_id:
            return name_to_id[answer]
        return self.student_id
