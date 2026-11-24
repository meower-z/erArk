"""
部位绝顶行为标识解析（orgasm_ids）
==================================
本模块用于解析部位绝顶二段行为的标识。
本模块定义程度排序表、部位字母到快感状态 id 的映射表与解析函数。
本模块不含任何导入语句。
"""

orgasm_degree_order = {"small": 0, "normal": 1, "strong": 2, "super": 3}
"""部位绝顶二段行为的程度后缀到递增程度序号（0 至 3）的映射。"""
orgasm_part_to_state_id = {
    "s": 0,
    "b": 1,
    "c": 2,
    "p": 3,
    "v": 4,
    "a": 5,
    "u": 6,
    "w": 7,
    "m": 21,
    "f": 22,
    "h": 23,
}
"""部位绝顶二段行为的部位字母到快感状态 id 的映射。"""


def get_orgasm_part_and_degree(
    second_behavior_id: str,
) -> tuple[str | None, int]:
    """
    按 {部位}_orgasm_{程度} 格式（例如 v_orgasm_strong）从二段行为 id 解析部位标识与程度序号。
    extra_orgasm、plural_orgasm_2、x_orgasm_edge、b_orgasm_to_milk 等不属于部位绝顶行为。
    函数不校验首段是否在 orgasm_part_to_state_id 中。
    Keyword arguments:
    second_behavior_id -- str，二段行为 id
    Return arguments:
    tuple[str | None, int] -- 按 _ 分割为三段、中段为 orgasm 且尾段在 orgasm_degree_order 中时
    返回 (首段, 程度序号)，否则返回 (None, -1)
    """
    id_split = second_behavior_id.split("_")
    if len(id_split) != 3 or id_split[1] != "orgasm":
        return None, -1
    if id_split[2] not in orgasm_degree_order:
        return None, -1
    return id_split[0], orgasm_degree_order[id_split[2]]
