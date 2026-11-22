"""初次体验与处女相关的前提处理函数"""

from types import FunctionType
from Script.Core import cache_control, constant_promise, game_type, get_text
from Script.Design import game_time
from Script.Design.handle_premise.premise_registry import add_premise
from Script.Modules.domains import abilities, activity, first_record

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
_: FunctionType = get_text._
""" 翻译api """


@add_premise(constant_promise.Premise.FIRST_KISS_IN_TODAY)
def handle_first_kiss_in_today(character_id: int) -> int:
    """
    自己今天失去了初吻
    参数:
        character_id (int): 角色id
    返回:
        int: 权重
    """
    t = first_record.get(character_id, "first_kiss_time")
    return 1 if game_time.count_day_for_datetime(t, game_time.now()) == 0 else 0


@add_premise(constant_promise.Premise.FIRST_KISS_BEFORE_TODAY)
def handle_first_kiss_before_today(character_id: int) -> int:
    """
    自己今天之前已经失去了初吻
    参数:
        character_id (int): 角色id
    返回:
        int: 权重
    """
    if handle_self_kiss_0(character_id) and not handle_first_kiss_in_today(
        character_id
    ):
        return 1
    return 0


@add_premise(constant_promise.Premise.FIRST_SEX_IN_TODAY)
def handle_first_sex_in_today(character_id: int) -> int:
    """
    自己今天失去了V处女（玩家则为今天失去了童贞）
    参数:
        character_id (int): 角色id
    返回:
        int: 权重
    """
    character_data = cache.character_data[character_id]
    # 玩家的童贞记录仍为平铺字段，NPC的V破处记录在first_part_sex_dict[6]
    if character_id == 0:
        first_time = first_record.get(character_data.cid, "first_sex_time")
    else:
        record = first_record.part_sex(character_data.cid, 6)
        if record is None:
            return 0
        first_time = record["time"]
    if game_time.count_day_for_datetime(first_time, game_time.now()) == 0:
        return 1
    return 0


@add_premise(constant_promise.Premise.FIRST_SEX_BEFORE_TODAY)
def handle_first_sex_before_today(character_id: int) -> int:
    """
    自己今天之前已经失去了V处女
    参数:
        character_id (int): 角色id
    返回:
        int: 权重
    """
    if handle_no_virgin(character_id) and not handle_first_sex_in_today(
        character_id
    ):
        return 1
    return 0


@add_premise(constant_promise.Premise.FIRST_A_SEX_IN_TODAY)
def handle_first_a_sex_in_today(character_id: int) -> int:
    """
    自己今天失去了A处女
    参数:
        character_id (int): 角色id
    返回:
        int: 权重
    """
    character_data = cache.character_data[character_id]
    # A破处记录在first_part_sex_dict[8]
    record = first_record.part_sex(character_data.cid, 8)
    if record is None:
        return 0
    if game_time.count_day_for_datetime(record["time"], game_time.now()) == 0:
        return 1
    return 0


@add_premise(constant_promise.Premise.FIRST_A_SEX_BEFORE_TODAY)
def handle_first_a_sex_before_today(character_id: int) -> int:
    """
    自己今天之前已经失去了A处女
    参数:
        character_id (int): 角色id
    返回:
        int: 权重
    """
    if handle_self_a_virgin_0(character_id) and not handle_first_a_sex_in_today(
        character_id
    ):
        return 1
    return 0


@add_premise(constant_promise.Premise.FIRST_U_SEX_IN_TODAY)
def handle_first_u_sex_in_today(character_id: int) -> int:
    """
    自己今天失去了U处女
    参数:
        character_id (int): 角色id
    返回:
        int: 权重
    """
    character_data = cache.character_data[character_id]
    # U破处记录在first_part_sex_dict[9]
    record = first_record.part_sex(character_data.cid, 9)
    if record is None:
        return 0
    if game_time.count_day_for_datetime(record["time"], game_time.now()) == 0:
        return 1
    return 0


@add_premise(constant_promise.Premise.FIRST_U_SEX_BEFORE_TODAY)
def handle_first_u_sex_before_today(character_id: int) -> int:
    """
    自己今天之前已经失去了U处女
    参数:
        character_id (int): 角色id
    返回:
        int: 权重
    """
    if handle_self_u_virgin_0(character_id) and not handle_first_u_sex_in_today(
        character_id
    ):
        return 1
    return 0


@add_premise(constant_promise.Premise.FIRST_W_SEX_IN_TODAY)
def handle_first_w_sex_in_today(character_id: int) -> int:
    """
    自己今天失去了W处女
    参数:
        character_id (int): 角色id
    返回:
        int: 权重
    """
    character_data = cache.character_data[character_id]
    # W破处记录在first_part_sex_dict[7]
    record = first_record.part_sex(character_data.cid, 7)
    if record is None:
        return 0
    if game_time.count_day_for_datetime(record["time"], game_time.now()) == 0:
        return 1
    return 0


@add_premise(constant_promise.Premise.FIRST_W_SEX_BEFORE_TODAY)
def handle_first_w_sex_before_today(character_id: int) -> int:
    """
    自己今天之前已经失去了W处女
    参数:
        character_id (int): 角色id
    返回:
        int: 权重
    """
    if handle_self_w_virgin_0(character_id) and not handle_first_w_sex_in_today(
        character_id
    ):
        return 1
    return 0


@add_premise(constant_promise.Premise.FIRST_M_SEX_IN_TODAY)
def handle_first_m_sex_in_today(character_id: int) -> int:
    """
    自己今天失去了M处女
    参数:
        character_id (int): 角色id
    返回:
        int: 权重
    """
    character_data = cache.character_data[character_id]
    # 口交初体验记录在first_part_sex_dict[2]
    record = first_record.part_sex(character_data.cid, 2)
    if record is None:
        return 0
    if game_time.count_day_for_datetime(record["time"], game_time.now()) == 0:
        return 1
    return 0


@add_premise(constant_promise.Premise.TARGET_FIRST_KISS_IN_TODAY)
def handle_target_first_kiss_in_today(character_id: int) -> int:
    """
    校验交互对象今天是否失去了初吻
    参数:
        character_id (int): 角色id（当前角色）
    返回:
        int: 权重
    说明:
        直接调用自己的初吻函数，传入交互对象的角色id
    """
    target_id = activity.target(character_id)
    return handle_first_kiss_in_today(target_id)


@add_premise(constant_promise.Premise.TARGET_FIRST_KISS_BEFORE_TODAY)
def handle_target_first_kiss_before_today(character_id: int) -> int:
    """
    校验交互对象今天之前已经失去了初吻
    参数:
        character_id (int): 角色id（当前角色）
    返回:
        int: 权重
    说明:
        直接调用自己的初吻函数，传入交互对象的角色id
    """
    target_id = activity.target(character_id)
    return handle_first_kiss_before_today(target_id)


@add_premise(constant_promise.Premise.TARGET_FIRST_SEX_IN_TODAY)
def handle_target_first_sex_in_today(character_id: int) -> int:
    """
    校验交互对象今天是否失去了V处女
    参数:
        character_id (int): 角色id（当前角色）
    返回:
        int: 权重
    说明:
        直接调用自己的V处女函数，传入交互对象的角色id
    """
    target_id = activity.target(character_id)
    return handle_first_sex_in_today(target_id)


@add_premise(constant_promise.Premise.TARGET_FIRST_SEX_BEFORE_TODAY)
def handle_target_first_sex_before_today(character_id: int) -> int:
    """
    校验交互对象今天之前已经失去了V处女
    参数:
        character_id (int): 角色id（当前角色）
    返回:
        int: 权重
    说明:
        直接调用自己的函数，传入交互对象的角色id
    """
    target_id = activity.target(character_id)
    return handle_first_sex_before_today(target_id)


@add_premise(constant_promise.Premise.TARGET_FIRST_A_SEX_IN_TODAY)
def handle_target_first_a_sex_in_today(character_id: int) -> int:
    """
    校验交互对象今天是否失去了A处女
    参数:
        character_id (int): 角色id（当前角色）
    返回:
        int: 权重
    说明:
        直接调用自己的A处女函数，传入交互对象的角色id
    """
    target_id = activity.target(character_id)
    return handle_first_a_sex_in_today(target_id)


@add_premise(constant_promise.Premise.TARGET_FIRST_A_SEX_BEFORE_TODAY)
def handle_target_first_a_sex_before_today(character_id: int) -> int:
    """
    校验交互对象今天之前已经失去了A处女
    参数:
        character_id (int): 角色id（当前角色）
    返回:
        int: 权重
    说明:
        直接调用自己的函数，传入交互对象的角色id
    """
    target_id = activity.target(character_id)
    return handle_first_a_sex_before_today(target_id)


@add_premise(constant_promise.Premise.TARGET_FIRST_U_SEX_IN_TODAY)
def handle_target_first_u_sex_in_today(character_id: int) -> int:
    """
    校验交互对象今天是否失去了U处女
    参数:
        character_id (int): 角色id（当前角色）
    返回:
        int: 权重
    说明:
        直接调用自己的U处女函数，传入交互对象的角色id
    """
    target_id = activity.target(character_id)
    return handle_first_u_sex_in_today(target_id)


@add_premise(constant_promise.Premise.TARGET_FIRST_U_SEX_BEFORE_TODAY)
def handle_target_first_u_sex_before_today(character_id: int) -> int:
    """
    校验交互对象今天之前已经失去了U处女
    参数:
        character_id (int): 角色id（当前角色）
    返回:
        int: 权重
    说明:
        直接调用自己的函数，传入交互对象的角色id
    """
    target_id = activity.target(character_id)
    return handle_first_u_sex_before_today(target_id)


@add_premise(constant_promise.Premise.TARGET_FIRST_W_SEX_IN_TODAY)
def handle_target_first_w_sex_in_today(character_id: int) -> int:
    """
    校验交互对象今天是否失去了W处女
    参数:
        character_id (int): 角色id（当前角色）
    返回:
        int: 权重
    说明:
        直接调用自己的W处女函数，传入交互对象的角色id
    """
    target_id = activity.target(character_id)
    return handle_first_w_sex_in_today(target_id)


@add_premise(constant_promise.Premise.TARGET_FIRST_W_SEX_BEFORE_TODAY)
def handle_target_first_w_sex_before_today(character_id: int) -> int:
    """
    校验交互对象今天之前已经失去了W处女
    参数:
        character_id (int): 角色id（当前角色）
    返回:
        int: 权重
    说明:
        直接调用自己的函数，传入交互对象的角色id
    """
    target_id = activity.target(character_id)
    return handle_first_w_sex_before_today(target_id)


@add_premise(constant_promise.Premise.TARGET_FIRST_M_SEX_IN_TODAY)
def handle_target_first_m_sex_in_today(character_id: int) -> int:
    """
    校验交互对象今天是否失去了M处女
    参数:
        character_id (int): 角色id（当前角色）
    返回:
        int: 权重
    说明:
        直接调用自己的M处女函数，传入交互对象的角色id
    """
    target_id = activity.target(character_id)
    return handle_first_m_sex_in_today(target_id)


@add_premise(constant_promise.Premise.HAVE_FIRST_KISS)
def handle_have_first_kiss(character_id: int) -> int:
    """
    玩家保有初吻
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    if abilities.talent(0)[4]:
        return 1
    return 0


@add_premise(constant_promise.Premise.NO_FIRST_KISS)
def handle_no_first_kiss(character_id: int) -> int:
    """
    玩家未保有初吻
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    if abilities.talent(0)[4]:
        return 0
    return 1


@add_premise(constant_promise.Premise.PL_HAVE_VIRGIN)
def handle_pl_have_virgin(character_id: int) -> int:
    """
    校验玩家是否是童贞
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    if abilities.talent(0)[5]:
        return 1
    return 0


@add_premise(constant_promise.Premise.PL_NO_VIRGIN)
def handle_pl_no_virgin(character_id: int) -> int:
    """
    玩家非童贞
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    if abilities.talent(0)[5]:
        return 0
    return 1


@add_premise(constant_promise.Premise.HAVE_A_VIRGIN)
def handle_have_a_virgin(character_id: int) -> int:
    """
    校验玩家是否是A处
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    if abilities.talent(0)[1]:
        return 1
    return 0


@add_premise(constant_promise.Premise.NO_A_VIRGIN)
def handle_no_a_virgin(character_id: int) -> int:
    """
    玩家非A处
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    if abilities.talent(0)[1]:
        return 0
    return 1


@add_premise(constant_promise.Premise.SELF_FIRST_KISS_0)
def handle_self_kiss_0(character_id: int) -> int:
    """
    自己未保有初吻
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_self_kiss_1(character_id)


@add_premise(constant_promise.Premise.SELF_FIRST_KISS_1)
def handle_self_kiss_1(character_id: int) -> int:
    """
    自己保有初吻
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return abilities.talent(character_id)[4] == 1


@add_premise(constant_promise.Premise.TARGET_NO_FIRST_KISS)
def handle_target_no_first_kiss(character_id: int) -> int:
    """
    校验交互对象是否初吻不在
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_data: game_type.Character = cache.character_data[
        activity.target(character_id)
    ]
    return abilities.talent(target_data.cid)[4] == 0


@add_premise(constant_promise.Premise.TARGET_HAVE_FIRST_KISS)
def handle_target_have_first_kiss(character_id: int) -> int:
    """
    校验交互对象是否初吻还在
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_data: game_type.Character = cache.character_data[
        activity.target(character_id)
    ]
    return abilities.talent(target_data.cid)[4] == 1


@add_premise(constant_promise.Premise.NO_VIRGIN)
def handle_no_virgin(character_id: int) -> int:
    """
    校验自己是否非处女
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return abilities.talent(character_id)[0] == 0


@add_premise(constant_promise.Premise.HAVE_VIRGIN)
def handle_have_virgin(character_id: int) -> int:
    """
    校验自己是处女
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_no_virgin(character_id)


@add_premise(constant_promise.Premise.TARGET_NO_VIRGIN)
def handle_target_no_virgin(character_id: int) -> int:
    """
    校验交互对象是否非处女
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_target_have_virgin(character_id)


@add_premise(constant_promise.Premise.TARGET_HAVE_VIRGIN)
def handle_target_have_virgin(character_id: int) -> int:
    """
    校验交互对象是否是处女
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_data: game_type.Character = cache.character_data[
        activity.target(character_id)
    ]
    return abilities.talent(target_data.cid)[0] == 1


@add_premise(constant_promise.Premise.SELF_NO_A_VIRGIN)
def handle_self_a_virgin_0(character_id: int) -> int:
    """
    校验自己是否非A处女
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_self_a_virgin_1(character_id)


@add_premise(constant_promise.Premise.SELF_HAVE_A_VIRGIN)
def handle_self_a_virgin_1(character_id: int) -> int:
    """
    校验自己是A处女
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return abilities.talent(character_id)[1] == 1


@add_premise(constant_promise.Premise.TARGET_NO_A_VIRGIN)
def handle_target_no_a_virgin(character_id: int) -> int:
    """
    校验交互对象是否非A处女
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_target_have_a_virgin(character_id)


@add_premise(constant_promise.Premise.TARGET_HAVE_A_VIRGIN)
def handle_target_have_a_virgin(character_id: int) -> int:
    """
    校验交互对象是否是A处女
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    target_data: game_type.Character = cache.character_data[
        activity.target(character_id)
    ]
    return abilities.talent(target_data.cid)[1] == 1


@add_premise(constant_promise.Premise.SELF_NO_U_VIRGIN)
def handle_self_u_virgin_0(character_id: int) -> int:
    """
    校验自己是否非U处女
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_self_u_virgin_1(character_id)


@add_premise(constant_promise.Premise.SELF_HAVE_U_VIRGIN)
def handle_self_u_virgin_1(character_id: int) -> int:
    """
    校验自己是U处女
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return abilities.talent(character_id)[2] == 1


@add_premise(constant_promise.Premise.SELF_NO_W_VIRGIN)
def handle_self_w_virgin_0(character_id: int) -> int:
    """
    校验自己是否非W处女
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return not handle_self_u_virgin_1(character_id)


@add_premise(constant_promise.Premise.SELF_HAVE_W_VIRGIN)
def handle_self_w_virgin_1(character_id: int) -> int:
    """
    校验自己是W处女
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    return abilities.talent(character_id)[3] == 1
