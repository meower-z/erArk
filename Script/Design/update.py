from Script.Design import action_scheduler


def game_update_flow(add_time: int):
    """
    游戏流程刷新：执行玩家已写好的行动并推进时间，直到再次轮到玩家输入
    Keyword arguments:
    add_time -- 玩家行动的分钟数
    """
    action_scheduler.advance(add_time)
