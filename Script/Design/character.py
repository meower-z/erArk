"""角色属性的初始化、输入角色名、校验角色时间是否过24点与按剧情id查角色id"""

import random
import datetime
from types import FunctionType
from Script.Core import get_text
from Script.Design import (
    map_handle,
    attr_calculation,
    clothing,
    game_time,
    instuct_judege,
)
from Script.Config import normal_config
from Script.UI.Moudle import panel, draw
from Script.Modules.domains import (
    abilities,
    action_info,
    activity,
    body_manage,
    dirty,
)
from Script.Modules.domains import first_record, flags, h_meters, h_state
from Script.Modules.domains import inventory, needs, player_ability
from Script.Modules.domains import player_collection, pregnancy, roster, status
from Script.Modules.domains import wardrobe, chara_key, chara_life
from Script.Modules.domains import bookmarks, chara_profile, relations
from Script.Modules.domains import identity

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


def init_attr(character_id: int) -> None:
    """
    初始化角色属性
    Keyword arguments:
    character_id -- 角色id
    """
    # print("进入第二步的init_attr")
    # print("进入第二步的character_id :",character_id)
    talent = abilities.talent(character_id)
    # character_data.birthday = attr_calculation.get_rand_npc_birthday(character_data.age)
    # character_data.height = attr_calculation.get_height(character_data.sex, character_data.age)
    # character_data.weight = attr_calculation.get_weight(bmi, character_data.height.now_height)

    # 一系列归零函数
    for table, zero in (
        (abilities.ability(character_id), attr_calculation.get_ability_zero),
        (talent, attr_calculation.get_talent_zero),
        (
            abilities.experience(character_id),
            attr_calculation.get_experience_zero,
        ),
        (abilities.juel(character_id), attr_calculation.get_juel_zero),
    ):
        table.replace(zero(table.copy()))
    status.replace(
        character_id,
        attr_calculation.get_status_zero(dict(status.of(character_id))),
    )
    dirty.clear(character_id)
    items = attr_calculation.get_item_zero(dict(inventory.items(character_id)))
    inventory.replace_items(character_id, items)
    h_state.clear(character_id)
    first_record.clear(character_id)
    action_info.init_zero(character_id)
    chara_key.reset(character_id, (*chara_life.WORK, *chara_life.ENTERTAINMENT))
    pregnancy.put(character_id, attr_calculation.get_pregnancy_zero())
    flags.reset(character_id)
    chara_profile.chara_setting.set(
        character_id, attr_calculation.get_chara_setting_zero()
    )
    relations.assistant_services.set(
        character_id, attr_calculation.get_assistant_services_zero()
    )
    body_manage.replace(character_id, attr_calculation.get_body_manage_zero())

    # 主角的初始处理，HP和MP的最大值默认为1000，EP最大值默认为1000，初始化信物，困倦程度归零
    if character_id == 0:
        attr_calculation.get_Dr_talent_zero(talent)
        needs.set(character_id, hit_max=1000, mana_max=1000)
        h_meters.set(
            character_id,
            eja=0,
            eja_max=1000,
            semen=100,
            semen_max=100,
        )
        needs.set(character_id, sanity=100, sanity_max=100)
        h_meters.set(character_id, semen=100, semen_max=100)
        player_ability.reset(0)
        player_collection.init_zero(0)
        wardrobe.put(character_id, attr_calculation.get_cloth_zero())
        relations.favorability.set(character_id, {0: 0})
        chara_life.dormitory.set(
            character_id,
            map_handle.get_map_system_path_str_for_list(["中枢", "博士房间"]),
        )  # 此处不可使用翻译
        # 初始收藏地点
        bookmarks.reset()

    # 一系列初始化函数
    instuct_judege.init_character_behavior_start_time(
        character_id, game_time.now()
    )
    needs.set(character_id, hit=needs.of(character_id)["hit_max"])
    needs.set(character_id, mana=needs.of(character_id)["mana_max"])
    needs.set(character_id, angry=random.randrange(1, 35))
    if character_id:
        clothing.get_underwear(character_id)
    # default_clothing_data = clothing.creator_suit(character_data.clothing_tem, character_data.sex)
    # for clothing_id in default_clothing_data:
    #     clothing_data = default_clothing_data[clothing_id]
    #     character_data.clothing.setdefault(clothing_id, {})
    #     character_data.clothing[clothing_id][clothing_data.uid] = clothing_data
    #     character_data.clothing_data.setdefault(clothing_data.tem_id, set())
    #     character_data.clothing_data[clothing_data.tem_id].add(clothing_data.uid)
    # init_class(character_data)


def input_name_func(ask_text: str) -> str:
    """
    输入角色名函数
    Keyword arguments:
    ask_text -- 询问的文本
    Return arguments:
    str -- 角色名
    """
    ask_name_panel = panel.AskForOneMessage()
    ask_name_panel.set(ask_text, 10)
    line_feed.draw()
    line = draw.LineDraw("=", width=window_width)
    line.draw()
    # 几种错误提示
    not_num_error = draw.NormalDraw()
    not_num_error.text = _("角色名不能为纯数字，请重新输入\n")
    not_system_error = draw.NormalDraw()
    not_system_error.text = _("角色名不能为系统保留字，请重新输入\n")
    not_name_error = draw.NormalDraw()
    not_name_error.text = _("已有角色使用该姓名，请重新输入\n")
    # 返回的角色名
    return_name = ""
    # 开始循环
    while 1:
        now_name = ask_name_panel.draw()
        if now_name.isdigit():
            not_num_error.draw()
            continue
        if now_name in get_text.translation_values:
            not_system_error.draw()
            continue
        if roster.has_name(now_name):
            not_name_error.draw()
            continue
        return_name = now_name
        break

    return return_name


def judge_character_time_over_24(character_id: int) -> int:
    """
    校验角色的时间是否已过24点
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重
    """
    start_time: datetime.datetime = activity.behavior(character_id).start_time
    end_time = game_time.get_sub_date(
        minute=activity.behavior(character_id).duration, old_date=start_time
    )

    if end_time.day != start_time.day:
        return 1
    return 0


def get_character_id_from_adv(adv_id: int) -> int:
    """
    通过剧情id获取角色id
    重构后character_id等于adv_id，直接判断是否存在即可
    Keyword arguments:
    adv_id -- 剧情id
    Return arguments:
    int -- 角色id
    """
    if identity.exists(adv_id):
        return adv_id
    return 0
