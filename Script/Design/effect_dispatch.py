from functools import wraps
from inspect import Parameter, signature
from Script.Core import constant


def _register(effect_id, table, parameter_count):
    """
    创建效果注册装饰器，按位置参数数量适配单角色或双角色函数。
    effect_id -- 效果id，int；table -- 效果注册表，dict；parameter_count -- 单角色参数数量，int
    返回 -- 接收并返回原函数的装饰器
    """
    def decorator(func):
        """检查并注册效果函数，返回原函数以保留直接调用方式。"""
        parameters = tuple(signature(func).parameters.values())
        if len(parameters) not in (parameter_count, parameter_count + 1) or any(
            p.kind not in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD) or p.default is not Parameter.empty for p in parameters
        ):
            raise TypeError(f"结算函数 {func.__name__} 应有 {parameter_count} 或 {parameter_count + 1} 个固定位置参数")
        needs_target = len(parameters) == parameter_count + 1

        @wraps(func)
        def wrapper(character_id, target_character_id, *args):
            """接收当前角色、目标id和其余结算参数，按注册格式调用并返回效果结果。"""
            if needs_target:
                if target_character_id is None:
                    raise ValueError(f"结算函数 {func.__name__} 需要目标角色id")
                return func(character_id, target_character_id, *args)
            return func(character_id, *args)

        table[effect_id] = wrapper
        return func

    return decorator


def add_settle_behavior_effect(behavior_effect_id: int):
    """
    注册普通效果，返回注册装饰器。
    behavior_effect_id -- 效果id，int
    函数接收character_id、add_time、change_data、now_time；需要目标时在character_id后增加target_character_id。
    """
    return _register(behavior_effect_id, constant.settle_behavior_effect_data, 4)


def add_settle_second_behavior_effect(second_behavior_effect_id: int):
    """
    注册二段效果，返回注册装饰器。
    second_behavior_effect_id -- 效果id，int
    函数接收character_id、change_data；需要目标时在character_id后增加target_character_id。
    """
    return _register(second_behavior_effect_id, constant.settle_second_behavior_effect_data, 2)
