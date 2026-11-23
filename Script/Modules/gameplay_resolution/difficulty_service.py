"""
难度系数服务（difficulty_service）
==================================
提供按难度等级计算游戏内修正系数的逻辑。
本模块不导入其他模块，供结算逻辑调用。
"""


def get_difficulty_coefficient(difficulty: int) -> float:
    """
    根据设定的难度值返回对应的游戏内修正系数。
    难度值在 0 到 6 之间时，依次对应系数表 [0.25, 0.5, 0.75, 1.0, 1.25, 2.0, 4.0] 中的条目。
    难度值超出该范围时返回默认值 1.0。
    Keyword arguments:
    difficulty -- int，设定的难度等级值
    Return arguments:
    float -- 对应的修正系数，超出范围时为 1.0
    """
    coefficients = [0.25, 0.5, 0.75, 1.0, 1.25, 2.0, 4.0]
    if 0 <= difficulty < len(coefficients):
        return coefficients[difficulty]
    else:
        return 1.0
