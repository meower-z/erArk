"""
gameplay_resolution 的界面面板选出的种类开始函数
==========================================
各种类用 starts.starter(kind) 登记；本文件在 LOAD_ORDER 里。
面板经 tk_ui.player_pick.choose 定下这些种类时只读不写：要改的数据记在 Intent 的 args 与 fields 里，
行动开始时（begin 写好行为、状态与交互对象之后）由这里的函数照着写进缓存。
带id的种类在开始前用 starts.check 再查一次：同一分钟里更早的开始拿走了这个id时，退回 1 分钟的等待。
"""

from types import FunctionType
from typing import cast
from uuid import UUID

from Script.Config import game_config
from Script.Core import cache_control, constant, game_type, get_text
from Script.Design import clothing, game_time, handle_premise, map_handle
from Script.Kernel import core
from Script.Modules.gameplay_resolution import intent, plan_queue, starts
from Script.UI.Panel import (
    achievement_panel,
    borrow_book_panel,
    cloth_panel,
    confinement_and_training,
)

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """

_: FunctionType = get_text._
""" 翻译api """


def _args(chosen: intent.Intent) -> dict[str, core.JSON]:
    """
    意图里本种类自己的参数
    Keyword arguments:
    chosen -- 意图
    Return arguments:
    dict -- 参数，没有时为空
    """
    return chosen.get("args", {})


def _wait_one_minute(who: int) -> core.Action:
    """
    退回的行动：1 分钟的等待
    Keyword arguments:
    who -- 角色id
    Return arguments:
    Action -- 通用种类的等待
    """
    wait = intent.Intent(
        behavior_id=constant.Behavior.WAIT,
        minutes=1,
        state=constant.CharacterStatus.STATUS_WAIT,
    )
    return intent.behavior_action(who, wait)


@starts.starter("player_read_book")
def start_read_book(who: int, chosen: intent.Intent) -> None:
    """读书：历史记录里这本书的阅读次数加一"""
    borrow_book_panel.update_read_count_in_history(
        who, int(cast(int, _args(chosen)["book_id"]))
    )


def _shop_food(args: dict[str, core.JSON]) -> dict[UUID, game_type.Food]:
    """
    要买的食物所在的货架：食堂、摊贩或餐厅里这种食物的那一格
    Keyword arguments:
    args -- player_buy_food 的参数：food_cid、restaurant（None、"Stall_Vendor" 或餐厅id）
    Return arguments:
    dict -- 食物uid到食物
    """
    cid = str(args["food_cid"])
    restaurant = args.get("restaurant")
    if restaurant is None:
        return cache.rhodes_island.dining_hall_data.get(cid, {})
    if restaurant == "Stall_Vendor":
        return cache.rhodes_island.stall_vendor_data[0].get(cid, {})
    restaurant_data = cache.rhodes_island.restaurant_data
    return restaurant_data.get(cast(int, restaurant), {}).get(cid, {})


@starts.check("player_buy_food")
def check_buy_food(who: int, chosen: intent.Intent) -> core.Action | None:
    """买食物：同一分钟里更早的开始买走了这份食物时退回 1 分钟的等待"""
    args = _args(chosen)
    if UUID(str(args["food_uid"])) in _shop_food(args):
        return None
    return _wait_one_minute(who)


@starts.starter("player_buy_food")
def start_buy_food(who: int, chosen: intent.Intent) -> None:
    """买食物：从货架移进背包，作为行为的目标食物"""
    args = _args(chosen)
    uid = UUID(str(args["food_uid"]))
    character_data = cache.character_data[who]
    character_data.food_bag[uid] = _shop_food(args).pop(uid)
    character_data.behavior.target_food = character_data.food_bag[uid]


@starts.check("eat_food")
def check_eat_food(who: int, chosen: intent.Intent) -> core.Action | None:
    """吃背包里的食物：这份食物已不在背包里时退回 1 分钟的等待"""
    uid = UUID(str(_args(chosen)["food_uid"]))
    if uid in cache.character_data[who].food_bag:
        return None
    return _wait_one_minute(who)


@starts.starter("eat_food")
def start_eat_food(who: int, chosen: intent.Intent) -> None:
    """吃背包里的食物：目标食物；味道调味被拒时生气；吃下加了精液的食物时结算成就"""
    args = _args(chosen)
    character_data = cache.character_data[who]
    food = character_data.food_bag[UUID(str(args["food_uid"]))]
    character_data.behavior.target_food = food
    if args.get("angry"):
        character_data.angry_point += 40
        character_data.sp_flag.angry_with_player = True
    if args.get("achievement"):
        achievement_panel.achievement_flow(_("进食"), 1076)


@starts.starter("make_food")
def start_make_food(who: int, chosen: intent.Intent) -> None:
    """做饭：最后做好的一份是行为的目标食物；结算成就"""
    uid = UUID(str(_args(chosen)["food_uid"]))
    character_data = cache.character_data[who]
    character_data.behavior.target_food = character_data.food_bag[uid]
    achievement_panel.achievement_flow(_("烹饪"))


@starts.starter("aromatherapy")
def start_aromatherapy(who: int, chosen: intent.Intent) -> None:
    """
    调香：消耗资源与今天的调香次数，对方带上调香效果并停下等待同样的时间，结算成就
    """
    recipe_id = int(cast(int, _args(chosen)["recipe_id"]))
    target_id = cache.character_data[who].target_character_id
    island = cache.rhodes_island
    formula = game_config.config_aromatherapy_recipes[recipe_id].formula
    for need_text in formula.split("&"):
        need_type, need_value = (int(v) for v in need_text.split("|"))
        island.materials_resouce[need_type] -= need_value
    island.remaining_aromatherapy_sessions_today -= 1
    cache.character_data[target_id].sp_flag.aromatherapy = recipe_id
    plan_queue.plan_next(
        target_id,
        constant.Behavior.WAIT,
        chosen["minutes"],
        target=target_id,
        state=constant.CharacterStatus.STATUS_WAIT,
        interrupt=True,
    )
    cache.achievement.aromatherapy_count += 1
    achievement_panel.achievement_flow(_("调香"))


@starts.starter("sleep")
def start_sleep(who: int, chosen: intent.Intent) -> None:
    """睡觉：关门，记下睡觉与醒来的时间，关闭透视，助理随之进入晚安问候或要睡觉状态"""
    character_data = cache.character_data[who]
    if _args(chosen).get("close_door"):
        scene_path = map_handle.get_map_system_path_str_for_list(
            character_data.position
        )
        scene_data = cache.scene_data[scene_path]
        scene_data.close_flag = scene_data.close_type
    now = game_time.now()
    character_data.action_info.sleep_time = now
    character_data.action_info.wake_time = game_time.get_sub_date(
        minute=chosen["minutes"], old_date=now
    )
    character_data.pl_ability.visual = False
    _assistant_goes_to_sleep(character_data.assistant_character_id)


def _assistant_goes_to_sleep(assistant_id: int) -> None:
    """
    玩家睡下时助理的安排：开着晚安问候且还没问候时先去问候，同居时去睡觉
    Keyword arguments:
    assistant_id -- 助理的角色id，没有助理时为 0
    """
    if assistant_id == 0:
        return
    if handle_premise.handle_action_sleep(
        assistant_id
    ) or not handle_premise.handle_normal_6(assistant_id):
        return
    if handle_premise.handle_assistant_night_salutation_on(
        assistant_id
    ) and handle_premise.handle_night_salutation_flag_0(assistant_id):
        fields: dict[str, object] = {
            "sp_flag.night_salutation": 1,
            "sp_flag.morning_salutation": 0,
        }
    elif handle_premise.handle_assistant_live_together_on(assistant_id) and (
        handle_premise.handle_assistant_night_salutation_0(assistant_id)
        or handle_premise.handle_night_salutation_flag_2(assistant_id)
    ):
        fields = {"sp_flag.sleep": True}
    else:
        return
    plan_queue.plan_next(
        assistant_id,
        constant.Behavior.SHARE_BLANKLY,
        1,
        target=assistant_id,
        state=constant.CharacterStatus.STATUS_WAIT,
        fields=fields,
        interrupt=True,
    )


@starts.starter("undress")
def start_undress(who: int, chosen: intent.Intent) -> None:
    """
    给对方脱衣：0 脱到只穿内衣，1 脱到只剩袜子手套，2 脱光，3 收走内裤；之后的结算同脱衣
    """
    target_id = cache.character_data[who].target_character_id
    target_data = cache.character_data[target_id]
    choice = int(cast(int, _args(chosen)["choice"]))
    cloth = target_data.cloth
    if choice == 0:
        for i in (5, 8):
            cloth.cloth_off[i].extend(cloth.cloth_wear[i])
        clothing.undress_out_cloth(target_id)
    elif choice == 1:
        for i in (5, 6, 8, 9):
            cloth.cloth_off[i].extend(cloth.cloth_wear[i])
        clothing.strip_down_till_socks_and_gloves_left(target_id)
    elif choice == 2:
        for i in game_config.config_clothing_type:
            cloth.cloth_off[i].extend(cloth.cloth_wear[i])
        clothing.get_all_cloth_off(target_id)
    elif choice == 3:
        clothing.pl_get_chara_pan(target_id)
    cloth_panel.cloth_off_after_settle(target_id)


@starts.starter("prepare_training")
def start_prepare_training(who: int, chosen: intent.Intent) -> None:
    """调教前准备：三人到调教室，监狱长做好准备，交互对象与监狱长随玩家等待"""
    confinement_and_training.start_training_preparation(
        chosen.get("target", cache.character_data[who].target_character_id)
    )
