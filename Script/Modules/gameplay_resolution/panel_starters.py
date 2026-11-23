"""
gameplay_resolution 的界面面板选出的种类开始函数
================================================
各种类用 starts.starter(kind) 登记；本文件在 LOAD_ORDER 里。
面板经 tk_ui.player_pick.choose 定下这些种类时只读不写：要改的数据记在 Intent 的 args 与 fields 里，
行动开始时（begin 写好行为、状态与交互对象之后）由这里的函数照着写进游戏状态。
带id的种类在开始前用 starts.check 再查一次：同一分钟里更早的开始拿走了这个id时，退回 1 分钟的等待。
"""

from types import FunctionType
from typing import cast
from uuid import UUID

from Script.Config import game_config
from Script.Core import constant, get_text
from Script.Design import (
    clothing,
    game_time,
    handle_premise,
    handle_talent,
    map_handle,
)
from Script.Kernel import core
from Script.Modules.domains import (
    achievement,
    action_info,
    activity,
    economy,
    flags,
)
from Script.Modules.domains import player_ability, tallies, scene_state
from Script.Modules.gameplay_resolution import intent, plan_queue, starts
from Script.System.Cooking_System import cooking
from Script.System.Sex_System import drunk_sex_common
from Script.UI.Moudle import draw
from Script.UI.Panel import (
    achievement_panel,
    borrow_book_panel,
    cloth_panel,
    confinement_and_training,
)
from Script.Modules.domains import kitchen, needs, warehouse
from Script.Modules.domains import inventory, wardrobe, relations

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


def _still_there(args: dict[str, core.JSON]) -> bool:
    """
    要买的食物还在食堂、地摊小贩或餐馆的货架上
    Keyword arguments:
    args -- player_buy_food 的 food_cid、food_uid、restaurant（None 为食堂，"Stall_Vendor" 为地摊小贩，其余为餐馆id）
    Return arguments:
    bool -- 还在时为 True
    """
    cid, uid = str(args["food_cid"]), str(args["food_uid"])
    restaurant = args.get("restaurant")
    if restaurant is None:
        return kitchen.find(cid, uid) is not None
    return uid in economy.shelf(cast(int | str, restaurant)).get(cid, {})


@starts.check("player_buy_food")
def check_buy_food(who: int, chosen: intent.Intent) -> core.Action | None:
    """买食物：同一分钟里更早的开始买走了这份食物时退回 1 分钟的等待"""
    if _still_there(_args(chosen)):
        return None
    return _wait_one_minute(who)


@starts.starter("player_buy_food")
def start_buy_food(who: int, chosen: intent.Intent) -> None:
    """买食物：从货架移进背包，作为行为的目标食物"""
    args = _args(chosen)
    cid, uid = str(args["food_cid"]), str(args["food_uid"])
    restaurant = args.get("restaurant")
    if restaurant is None:
        food = kitchen.take(cid, uid)
    else:
        taken = economy.take(cast(int | str, restaurant), cid, uid)
        assert taken is not None
        food = taken
    inventory.put_food(who, food)
    activity.update_behavior(who, target_food=food)


@starts.check("eat_food")
def check_eat_food(who: int, chosen: intent.Intent) -> core.Action | None:
    """
    吃背包里的食物前的判定：这份食物已不在背包里时退回 1 分钟的等待；
    交互对象不接受酒时换成拒绝饮酒；不接受特殊调味时，味道调味只生气，
    其余在高级性骚扰实行值够时换成低级性骚扰（肛），不够时换成拒绝食用
    """
    args = _args(chosen)
    food = inventory.foods(who).get(UUID(str(args["food_uid"])))
    if food is None:
        return _wait_one_minute(who)
    target_id = activity.target(who)
    if not drunk_sex_common.judge_accept_alcohol_food(target_id, food):
        refused = (
            constant.Behavior.REFUSE_DRINK,
            constant.CharacterStatus.STATUS_REFUSE_DRINK,
        )
    elif food.special_seasoning == 0 or (
        cooking.judge_accept_special_seasoning_food(target_id, food)
    ):
        return None
    elif food.special_seasoning in [1, 2, 3, 4]:
        angry = intent.Intent(**chosen)
        angry["args"] = {**args, "angry": True}
        return intent.behavior_action(who, angry, "eat_food")
    elif handle_premise.handle_instruct_judge_high_obscenity(who):
        refused = (
            constant.Behavior.LOW_OBSCENITY_ANUS,
            constant.CharacterStatus.STATUS_LOW_OBSCENITY_ANUS,
        )
    else:
        refused = (
            constant.Behavior.REFUSE_EAT,
            constant.CharacterStatus.STATUS_REFUSE_EAT,
        )
    instead = intent.Intent(**chosen)
    instead["behavior_id"], instead["state"] = refused
    return intent.behavior_action(who, instead, "eat_food")


@starts.starter("eat_food")
def start_eat_food(who: int, chosen: intent.Intent) -> None:
    """
    吃背包里的食物：目标食物；味道调味被拒时生气；
    吃下加了精液的特殊调味食物时结算成就
    """
    args = _args(chosen)
    food = inventory.foods(who)[UUID(str(args["food_uid"]))]
    activity.update_behavior(who, target_food=food)
    if args.get("angry"):
        needs.add(who, "angry", 40)
        flags.set(who, angry_with_player=True)
    elif (
        chosen["behavior_id"] == constant.Behavior.EAT
        and food.special_seasoning in [11, 12]
        and food.special_seasoning_amount > 0
    ):
        achievement_panel.achievement_flow(_("进食"), 1076)


@starts.starter("make_food")
def start_make_food(who: int, chosen: intent.Intent) -> None:
    """
    做饭：照选好的菜谱、份数、品质与调味做出食物（材料不够时少做并提示），
    记下做好的份数，最后做好的一份是行为的目标食物；结算成就
    """
    args = _args(chosen)
    count = int(cast(int, args["count"]))
    made = cooking.player_make_dishes(
        int(cast(int, args["recipe_id"])),
        count,
        int(cast(int, args["quality"])),
        int(cast(int, args["seasoning"])),
    )
    activity.update_behavior(who, make_food_count=len(made))
    if made:
        activity.update_behavior(
            who, target_food=inventory.foods(who)[made[-1]]
        )
    if len(made) < count:
        now_draw = draw.NormalDraw()
        now_draw.text = _(
            "因为调味材料或精液量不足，实际制作数量为 {0} 个\n"
        ).format(len(made))
        now_draw.draw()
    achievement_panel.achievement_flow(_("烹饪"))


@starts.starter("talent_up")
def start_talent_up(who: int, chosen: intent.Intent) -> None:
    """手动获得素质：提示选择成功，以手动获得类型结算该素质"""
    args = _args(chosen)
    now_draw = draw.WaitDraw()
    now_draw.text = _("选择成功\n")
    now_draw.draw()
    handle_talent.gain_talent(
        int(cast(int, args["character_id"])),
        1,
        int(cast(int, args["talent_id"])),
    )


@starts.starter("aromatherapy")
def start_aromatherapy(who: int, chosen: intent.Intent) -> None:
    """
    调香：消耗资源与今天的调香次数，对方带上调香效果并停下等待同样的时间，结算成就
    """
    recipe_id = int(cast(int, _args(chosen)["recipe_id"]))
    target_id = activity.target(who)
    formula = game_config.config_aromatherapy_recipes[recipe_id].formula
    for need_text in formula.split("&"):
        need_type, need_value = (int(v) for v in need_text.split("|"))
        warehouse.add(need_type, -need_value)
    tallies.add(tallies.AROMATHERAPY, -1)
    flags.set(target_id, aromatherapy=recipe_id)
    plan_queue.plan_next(
        target_id,
        constant.Behavior.WAIT,
        chosen["minutes"],
        target=target_id,
        state=constant.CharacterStatus.STATUS_WAIT,
        interrupt=True,
    )
    achievement.add("aromatherapy_count", 1)
    achievement_panel.achievement_flow(_("调香"))


@starts.starter("sleep")
def start_sleep(who: int, chosen: intent.Intent) -> None:
    """睡觉：关门，记下睡觉与醒来的时间，关闭透视，助理随之进入晚安问候或要睡觉状态"""
    if _args(chosen).get("close_door"):
        scene_path = map_handle.get_map_system_path_str_for_list(
            activity.position(who)
        )
        scene_data = constant.scene_data[scene_path]
        scene_state.set_close_flag(scene_path, scene_data.close_type)
    now = game_time.now()
    action_info.set(who, "sleep_time", now)
    action_info.set(
        who,
        "wake_time",
        game_time.get_sub_date(minute=chosen["minutes"], old_date=now),
    )
    player_ability.set(who, visual=False)
    _assistant_goes_to_sleep(relations.assistant_character_id(who))


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
    target_id = activity.target(who)
    choice = int(cast(int, _args(chosen)["choice"]))
    cloth = wardrobe.clone_mutable_snapshot(target_id)
    if choice == 0:
        for i in (5, 8):
            cloth.cloth_off[i].extend(cloth.cloth_wear[i])
        wardrobe.put(target_id, cloth)
        clothing.undress_out_cloth(target_id)
    elif choice == 1:
        for i in (5, 6, 8, 9):
            cloth.cloth_off[i].extend(cloth.cloth_wear[i])
        wardrobe.put(target_id, cloth)
        clothing.strip_down_till_socks_and_gloves_left(target_id)
    elif choice == 2:
        for i in game_config.config_clothing_type:
            cloth.cloth_off[i].extend(cloth.cloth_wear[i])
        wardrobe.put(target_id, cloth)
        clothing.get_all_cloth_off(target_id)
    elif choice == 3:
        clothing.pl_get_chara_pan(target_id)
    cloth_panel.cloth_off_after_settle(target_id)


@starts.starter("prepare_training")
def start_prepare_training(who: int, chosen: intent.Intent) -> None:
    """调教前准备：三人到调教室，监狱长做好准备，交互对象与监狱长随玩家等待"""
    confinement_and_training.start_training_preparation(
        chosen.get("target", activity.target(who))
    )
