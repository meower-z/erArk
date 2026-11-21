"""
gameplay_resolution 的干员状态机选出的种类开始函数
===========================================
各种类用 starts.starter(kind) 登记；本文件在 LOAD_ORDER 里。
状态机选行动时只记下种类与参数（choice.Plan.kind、Plan.arg），这里在行动开始时做种类自己的结算。
带着食物、病人或持卵角色id的种类在开始前用 starts.check 复查：id 已经无效时换成原地等待1分钟。
兴趣课读书借不到书时也换成等待。
"""

from collections.abc import Mapping
from uuid import UUID

from Script.Core import cache_control, constant, game_type
from Script.Kernel import core
from Script.Modules.domains import economy, kitchen
from Script.Modules.gameplay_resolution import intent, starts

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """


def _args(data: intent.Intent) -> Mapping[str, core.JSON]:
    """
    意图里本种类自己的参数
    Keyword arguments:
    data -- 意图
    Return arguments:
    Mapping -- 参数，没有时为空
    """
    return data.get("args", {})


def _wait_one_minute(who: int) -> core.Action:
    """
    原地等待1分钟的行动，换掉 id 已经无效的行动
    Keyword arguments:
    who -- 角色id
    Return arguments:
    Action -- 等待的行动
    """
    return intent.behavior_action(
        who,
        {
            "behavior_id": constant.Behavior.WAIT,
            "minutes": 1,
            "target": who,
            "state": constant.CharacterStatus.STATUS_WAIT,
        },
    )


@starts.starter("assign_dormitory")
def assign_dormitory(who: int, data: intent.Intent) -> None:
    """还没有宿舍的干员分到一间宿舍"""
    from Script.System.Dormitory_System import common as dormitory_common

    if cache.character_data[who].dormitory == "无":
        dormitory_common.new_character_get_dormitory(who)


@starts.starter("join_exam_queue")
def join_exam_queue(who: int, data: intent.Intent) -> None:
    """加入等待体检的名单"""
    cache.rhodes_island.waiting_for_exam_operator_ids.add(who)


@starts.starter("leave_exam_queue")
def leave_exam_queue(who: int, data: intent.Intent) -> None:
    """退出等待体检的名单"""
    cache.rhodes_island.waiting_for_exam_operator_ids.discard(who)


@starts.starter("private_move")
def private_move(who: int, data: intent.Intent) -> None:
    """结算私密房间前的结果：取消跟随或放弃逆推，并显示提示"""
    from Script.Design import character_move

    character_move.settle_private_move(who, str(_args(data)["outcome"]))


@starts.starter("see_h")
def see_h(who: int, data: intent.Intent) -> None:
    """目睹H：发现的结算排进自己的计划队列"""
    from Script.System.Sex_System import sex_be_discovered_panel

    sex_be_discovered_panel.plan_discovery(who)


@starts.starter("read_book")
def read_book(who: int, data: intent.Intent) -> None:
    """借一本书，并把借着的那本写进 behavior"""
    from Script.UI.Panel import borrow_book_panel

    borrow_book_panel.prepare_npc_read_book(who)


@starts.check("identify_eggs")
def identify_eggs_still_there(
    who: int, data: intent.Intent
) -> core.Action | None:
    """持卵角色已没有可鉴定的卵时等1分钟"""
    from Script.System.Pregnancy_System import egg_handle

    owner_id = int(str(_args(data)["owner_id"]))
    if owner_id in cache.character_data and egg_handle.get_identifiable_eggs(
        owner_id
    ):
        return None
    return _wait_one_minute(who)


@starts.starter("identify_eggs")
def identify_eggs(who: int, data: intent.Intent) -> None:
    """鉴定持卵角色的卵"""
    from Script.System.Pregnancy_System import egg_handle

    owner_id = int(str(_args(data)["owner_id"]))
    egg_handle.npc_identify_eggs_settle(owner_id, identifier_id=who)


@starts.starter("npc_cloth")
def npc_cloth(who: int, data: intent.Intent) -> None:
    """换上标准衣服"""
    from Script.Design import clothing

    clothing.get_npc_cloth(who)


@starts.starter("restock_shop")
def restock_shop(who: int, data: intent.Intent) -> None:
    """刷新食堂（-1）或餐厅的食物"""
    from Script.System.Cooking_System import cooking

    cooking.init_food_shop_data(int(str(_args(data)["shop"])))


def _find(
    foods: Mapping[UUID, game_type.Food] | None, uid: object
) -> tuple[UUID, game_type.Food] | None:
    """
    在食物uid到食物的表里按记成字符串的uid找食物
    Keyword arguments:
    foods -- 食物uid到食物，可为 None
    uid -- 记成字符串的食物uid
    Return arguments:
    tuple | None -- (表里的键, 食物)，找不到时为 None
    """
    for key, food in (foods or {}).items():
        if str(key) == uid:
            return key, food
    return None


@starts.check("buy_food")
def food_still_there(who: int, data: intent.Intent) -> core.Action | None:
    """选中的食物已被买走时等1分钟"""
    args = _args(data)
    shop, uid = int(str(args["shop"])), str(args["food_uid"])
    if shop == -1:
        there = kitchen.find(str(args["recipe_id"]), uid) is not None
    else:
        there = uid in economy.shelf(shop).get(str(args["recipe_id"]), {})
    return None if there else _wait_one_minute(who)


@starts.starter("buy_food")
def buy_food(who: int, data: intent.Intent) -> None:
    """把选中的食物从食堂或餐厅拿进背包，并作为行为的目标食物"""
    args = _args(data)
    shop, uid = int(str(args["shop"])), str(args["food_uid"])
    if shop == -1:
        food = kitchen.take(str(args["recipe_id"]), uid)
        key = food.uid
    else:
        taken = economy.take(shop, str(args["recipe_id"]), uid)
        assert taken is not None
        key, food = taken.uid, taken
    character_data = cache.character_data[who]
    character_data.food_bag[key] = food
    character_data.behavior.target_food = food


@starts.check("eat_bag_food")
def bag_food_still_there(who: int, data: intent.Intent) -> core.Action | None:
    """背包里已没有选中的食物时等1分钟"""
    bag = cache.character_data[who].food_bag
    if _find(bag, _args(data)["food_uid"]) is not None:
        return None
    return _wait_one_minute(who)


@starts.starter("eat_bag_food")
def eat_bag_food(who: int, data: intent.Intent) -> None:
    """背包里选中的食物作为行为的目标食物"""
    character_data = cache.character_data[who]
    found = _find(character_data.food_bag, _args(data)["food_uid"])
    assert found is not None
    character_data.behavior.target_food = found[1]


@starts.starter("hunger_zero")
def hunger_zero(who: int, data: intent.Intent) -> None:
    """背包里没有食物：清空饥饿值和进食状态，防止进食失败的死循环"""
    from Script.Design import game_time
    from Script.Settle import default

    for settle in (
        default.handle_hunger_point_zero,
        default.handle_eat_food_flag_to_0,
    ):
        settle(who, 1, game_type.CharacterStatusChange(), game_time.now())


def _surgery_patient(who: int, patient_id: int) -> object | None:
    """
    医生此刻还能做手术的这位患者
    Keyword arguments:
    who -- 医生的角色id
    patient_id -- 患者编号
    Return arguments:
    MedicalPatient | None -- 患者，已不在候选里时为 None
    """
    from Script.System.Medical_System import medical_service

    for patient in medical_service.get_surgery_candidate_patient_ids(
        doctor_character=cache.character_data[who],
        target_base=cache.rhodes_island,
    ):
        if patient.patient_id == patient_id:
            return patient
    return None


@starts.check("schedule_surgery")
def patient_still_there(who: int, data: intent.Intent) -> core.Action | None:
    """选中的患者已不能手术时等1分钟"""
    if _surgery_patient(who, int(str(_args(data)["patient_id"]))) is not None:
        return None
    return _wait_one_minute(who)


@starts.starter("schedule_surgery")
def schedule_surgery(who: int, data: intent.Intent) -> None:
    """扣除手术资源并给患者安排这位医生的手术；资源不足时什么都不改"""
    from Script.System.Medical_System import medical_constant, medical_service

    patient = _surgery_patient(who, int(str(_args(data)["patient_id"])))
    assert isinstance(patient, medical_constant.MedicalPatient)
    if not medical_service.consume_surgery_resources(
        patient, cache.rhodes_island
    ):
        return
    patient.assigned_hospital_doctor_id = who
    patient.last_surgery_result = "scheduled"
    patient.surgery_blocked_resource = None
    patient.surgery_blocked = False
    cache.character_data[who].work.surgery_patient_id = patient.patient_id


@starts.starter("teach")
def teach(who: int, data: intent.Intent) -> None:
    """把本节来上这间教室的学生拉进听课"""
    from Script.StateMachine import default

    default.pull_students(who)


@starts.starter("skip_class")
def skip_class(who: int, data: intent.Intent) -> None:
    """翘课：记一节缺课"""
    from Script.System.Education_System import class_ai

    class_ai.settle_absent(who, by_skip=True)


@starts.starter("absent_rest")
def absent_rest(who: int, data: intent.Intent) -> None:
    """体力不足：记一节缺课"""
    from Script.System.Education_System import class_ai

    class_ai.settle_absent(who)


@starts.check("do_course")
def course_book_ready(who: int, data: intent.Intent) -> core.Action | None:
    """兴趣课读书：借书，借不到书时等1分钟"""
    if not _args(data).get("read_book"):
        return None
    from Script.UI.Panel import borrow_book_panel

    if borrow_book_panel.prepare_npc_read_book(who):
        return None
    return _wait_one_minute(who)


@starts.starter("do_course")
def do_course(who: int, data: intent.Intent) -> None:
    """个人式课：兴趣课读书把借着的书装配进行为；体育课与兴趣课记一节出勤"""
    args = _args(data)
    if args.get("read_book"):
        from Script.UI.Panel import borrow_book_panel

        borrow_book_panel.prepare_npc_read_book(who)
    if args.get("attend"):
        from Script.System.Education_System import growth_handle

        growth_handle.settle_course_attend(who)


@starts.starter("join_sex_class")
def join_sex_class(who: int, data: intent.Intent) -> None:
    """走进正在上实操课的教室：加入课堂 H 并记一节出勤"""
    from Script.System.Education_System import sex_class_handle

    sex_class_handle.pull_student_into_class(who)
    sex_class_handle.settle_attend(who)


@starts.starter("maintenance")
def maintenance(who: int, data: intent.Intent) -> None:
    """记下检修地点"""
    cache.rhodes_island.maintenance_place[who] = str(_args(data)["place"])
