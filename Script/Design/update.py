from Script.Modules.scheduler import game_actions


def game_update_flow(add_time: int):
    """输入玩家行动分钟数，提交行动并推进至下一次输入；返回 None。"""
    game_actions.get_runtime().advance(add_time)
