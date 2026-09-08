from enum import Enum
from inspect import Parameter, signature
from Script.Core import cache_control, constant, game_type


class EffectRole(Enum):
    """注册时声明的行为角色；分发时解析为角色id。"""
    ACTOR = "actor"
    TARGET = "target"
    PLAYER = "player"
    OTHER = "other"


_behavior_bindings = {}
_second_bindings = {}
"""效果id对应的调用方式、受体和来源绑定。"""


def _register(effect_id, *, second=False, kind="effect", recipient=None, source=None):
    """
    创建注册装饰器，按参数位置检查接口并保存角色绑定。
    effect_id -- 效果id，int；second -- 是否为二段效果，bool
    kind -- effect、operation或selector；recipient、source -- EffectRole或None
    返回 -- 接收并返回原函数的装饰器
    """
    for role in (recipient, source):
        if role is not None and not isinstance(role, EffectRole):
            raise ValueError(f"未知的效果角色绑定：{role!r}")
    if recipient == EffectRole.OTHER or (recipient is None and source is not None):
        raise ValueError("受体必须明确；来源只能随受体一起声明")
    table = constant.settle_second_behavior_effect_data if second else constant.settle_behavior_effect_data
    bindings = _second_bindings if second else _behavior_bindings
    if kind == "effect" and recipient is None:
        kind = "legacy"
    argument_count = (2 if second else 4) + (source is not None or kind in {"operation", "selector"})

    def decorator(func):
        """检查函数的参数数量和位置，注册后返回原函数，保留直接调用方式。"""
        parameters = tuple(signature(func).parameters.values())
        if len(parameters) != argument_count or any(p.kind not in {Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD} for p in parameters):
            raise TypeError(f"结算函数 {func.__name__} 应接收 {argument_count} 个位置参数")
        table[effect_id] = func
        bindings[effect_id] = (kind, recipient, source)
        return func

    return decorator


def add_settle_behavior_effect(behavior_effect_id: int, *, recipient=None, source=None):
    """
    注册普通效果，返回保留原函数的装饰器。
    behavior_effect_id -- 效果id；recipient、source -- EffectRole角色绑定
    省略绑定时保留旧四参数调用；声明受体时参数为recipient_id、add_time、change_data、now_time。
    声明source时在recipient_id后增加source_id；change_data属于受体。
    """
    return _register(behavior_effect_id, recipient=recipient, source=source)


def add_settle_second_behavior_effect(second_behavior_effect_id: int, *, recipient=None, source=None):
    """
    注册二段效果，返回保留原函数的装饰器。
    second_behavior_effect_id -- 效果id；recipient、source -- EffectRole角色绑定
    省略绑定时保留旧两参数调用；声明受体时参数为recipient_id、change_data。
    声明source时在recipient_id后增加source_id；change_data属于受体。
    """
    return _register(second_behavior_effect_id, second=True, recipient=recipient, source=source)


def add_behavior_operation(behavior_effect_id: int, *, second=False):
    """
    注册场景、调度或多人操作，返回保留原函数的装饰器。
    behavior_effect_id -- 效果id；second -- 是否为二段操作，bool
    普通操作接收actor_id、target_id、add_time、change_data、now_time；二段操作接收actor_id、target_id、change_data。
    change_data属于actor，操作自行安排各角色的结算。
    """
    return _register(behavior_effect_id, second=second, kind="operation")


def add_interaction_target_selector(behavior_effect_id: int):
    """
    注册交互目标选择器，返回保留原函数的装饰器。
    behavior_effect_id -- 效果id，int
    选择器接收actor_id、target_id、add_time、change_data、now_time，返回目标id或None（沿用原目标）。
    返回的id写入actor的交互对象，并传给后续效果。
    """
    return _register(behavior_effect_id, kind="selector")


def _resolve_role(role, actor_id, target_id, recipient_id=None):
    """把EffectRole绑定解析为角色id；OTHER为受体相对行为双方中的另一方。"""
    if role == EffectRole.ACTOR:
        return actor_id
    if role == EffectRole.TARGET:
        if target_id is None:
            raise ValueError("该效果需要行为目标")
        return target_id
    if role == EffectRole.PLAYER:
        return 0
    if role == EffectRole.OTHER:
        if recipient_id == actor_id:
            return _resolve_role(EffectRole.TARGET, actor_id, target_id)
        if recipient_id == target_id:
            return actor_id
        raise ValueError("受体不在行为双方中，无法确定OTHER来源")
    raise ValueError(f"未知的效果角色绑定：{role!r}")


def get_recipient_change(change_owner_id, recipient_id, change_data):
    """
    取得受体本人的变化记录，返回CharacterStatusChange或TargetChange。
    change_owner_id -- 根记录所属角色id；recipient_id -- 受体id；change_data -- 根记录
    """
    if recipient_id == change_owner_id:
        return change_data
    if recipient_id not in change_data.target_change:
        change_data.target_change[recipient_id] = game_type.TargetChange()
    return change_data.target_change[recipient_id]


def _invoke(effect_id, actor_id, target_id, change_data, add_time=None, now_time=None, *, second=False, root_change=None, change_owner_id=None):
    """
    按注册方式解析角色与记录并执行，返回后续效果使用的目标id。
    effect_id、actor_id、target_id -- 效果与行为双方id；change_data -- actor的变化记录
    add_time、now_time -- 普通效果的时长和时间；second -- 是否为二段效果
    root_change、change_owner_id -- 本轮根记录及其所属角色，省略时为change_data和actor_id
    """
    table = constant.settle_second_behavior_effect_data if second else constant.settle_behavior_effect_data
    bindings = _second_bindings if second else _behavior_bindings
    kind, recipient, source = bindings[effect_id]
    if root_change is None:
        root_change = change_data
    if change_owner_id is None:
        change_owner_id = actor_id
    if kind == "effect":
        recipient_id = _resolve_role(recipient, actor_id, target_id)
        role_ids = [recipient_id]
        if source is not None:
            role_ids.append(_resolve_role(source, actor_id, target_id, recipient_id))
        effect_change = get_recipient_change(change_owner_id, recipient_id, root_change)
    else:
        role_ids = [actor_id] if kind == "legacy" else [actor_id, target_id]
        effect_change = change_data
    args = [effect_change] if second else [add_time, effect_change, now_time]
    result = table[effect_id](*role_ids, *args)
    # 兼容注册通过持久交互对象选目标；选择器返回的玩家id 0也是有效结果。
    if kind == "legacy":
        return cache_control.cache.character_data[actor_id].target_character_id
    if kind == "selector" and result is not None:
        if type(result) is not int:
            raise TypeError("目标选择器必须返回角色id或None")
        cache_control.cache.character_data[actor_id].target_character_id = result
        return result
    return target_id


def invoke_behavior_effect(effect_id, actor_id, target_id, add_time, change_data, now_time, *, root_change=None, change_owner_id=None):
    """
    分发普通效果并返回后续目标id，int。
    effect_id -- 效果id；actor_id、target_id -- 行为双方id；add_time、now_time -- 时长和时间
    change_data -- actor的变化记录；root_change、change_owner_id -- 本轮根记录及其所属角色
    """
    return _invoke(effect_id, actor_id, target_id, change_data, add_time, now_time, root_change=root_change, change_owner_id=change_owner_id)


def invoke_second_effect(effect_id, actor_id, target_id, change_data, *, root_change=None, change_owner_id=None):
    """
    分发二段效果并返回后续目标id，int。
    effect_id -- 效果id；actor_id、target_id -- 行为双方id
    change_data -- actor的变化记录；root_change、change_owner_id -- 本轮根记录及其所属角色
    """
    return _invoke(effect_id, actor_id, target_id, change_data, second=True, root_change=root_change, change_owner_id=change_owner_id)
