import os
import csv
import random

from Script.Config import normal_config
from Script.Core import cache_control, game_type, get_text
from Script.Design import game_time
from Script.UI.Moudle import draw
from Script.UI.Panel import normal_panel
from Script.UI.Panel.hypnosis_panel import hypnosis_degree_limit_calculation

cache: game_type.Cache = cache_control.cache
_ = get_text._
window_width = normal_config.config_normal.text_width
width = window_width


def modded_hypnosis(target_character_id):
    """
    计算催眠的增长程度
    Keyword arguments:
    target_character_id -- 角色id
    Return arguments:
    float -- 催眠增长值
    """

    from Script.Design import handle_premise, handle_ability
    from Script.UI.Panel.hypnosis_panel import hypnosis_degree_limit_calculation

    pl_character_data: game_type.Character = cache.character_data[0]
    target_character_data: game_type.Character = cache.character_data[target_character_id]

    if target_character_id == 0:
        return 0

    # 如果已经达到当前玩家的能力上限，则不再增加
    hypnosis_degree_limit = hypnosis_degree_limit_calculation()
    if target_character_data.hypnosis.hypnosis_degree >= hypnosis_degree_limit:
        return 0

    base_addition = 1

    # 根据玩家的催眠能力，计算催眠增长系数
    hypnosis_degree_adjust = 2
    if pl_character_data.talent[334]:
        hypnosis_degree_adjust = 6
    elif pl_character_data.talent[333]:
        hypnosis_degree_adjust = 4

    # 调香的加成
    if target_character_data.sp_flag.aromatherapy == 6:
        hypnosis_degree_adjust += 5

    # 根据无觉刻印的等级，计算催眠增长系数
    hypnosis_degree_adjust *= handle_ability.get_ability_adjust(target_character_data.ability[19])

    """
    变更点：系数由0.5~1.5改为5~10
    """
    # 乘以5~10的随机系数
    hypnosis_degree_adjust *= random.uniform(5, 10)

    # 最后计算
    final_addition = base_addition * hypnosis_degree_adjust
    # 限制为1位小数
    final_addition = round(final_addition, 1)
    # print(f"debug final_addition = {final_addition}")

    return final_addition

def modded_sanity_grow():
    """
    玩家理智值的自然成长\n
    Keyword arguments:
    无
    """
    character_data: game_type.Character = cache.character_data[0]
    today_cost = character_data.pl_ability.today_sanity_point_cost
    character_data.pl_ability.today_sanity_point_cost = 0
    # 消耗超过90时进行成长
    if today_cost >= 50 and character_data.sanity_point_max < 9999:
        """
        变更点：成长值变为消耗值的100%
        """
        # 成长值为消耗值的1/1，四舍五入取整
        grow_value = round(today_cost)
        character_data.sanity_point_max += grow_value
        character_data.sanity_point_max = min(character_data.sanity_point_max,9999)
        # 绘制说明信息
        now_draw = draw.WaitDraw()
        now_draw.width = window_width
        now_draw.text = _("\n在刻苦的锻炼下，博士理智最大值成长了{0}点\n").format(grow_value)
        now_draw.draw()

#暂且还没找到如何直接替换类的实例方法
#但是可以通过在静态方法初始化实例的时候替换实例方法来实现
#文本的话，我太懒了，就不替换了
def handle_order_hotel_room():
    from types import MethodType
    """处理预定房间指令"""
    now_draw = normal_panel.Order_Hotel_Room_Panel(width)
    now_draw.order_room = MethodType(cheaper_room, now_draw)
    now_draw.draw()
def cheaper_room(self, room_id):
    """预订房间
    变更点：房间价格由2,10,100变为1,2,3
    """
    room_price = [1, 2, 3]
    room_name = [_("标间"),_("情趣主题房"),_("顶级套房")]
    # 判断粉红凭证是否足够
    if cache.rhodes_island.materials_resouce[4] < room_price[room_id]:
        now_draw = draw.WaitDraw()
        draw_text = _("\n粉红凭证不足，无法预订{0}\n").format(room_name[room_id])
        now_draw.text = draw_text
        now_draw.draw()
        return
    # 进行结算
    cache.rhodes_island.materials_resouce[4] -= room_price[room_id]
    cache.rhodes_island.love_hotel_room_lv = room_id + 1
    pl_character_data: game_type.Character = cache.character_data[0]
    pl_character_data.action_info.check_out_time = game_time.get_sub_date(day=1, old_date=cache.game_time)
    pl_character_data.action_info.check_out_time = pl_character_data.action_info.check_out_time.replace(hour=12)
    # 情趣房的赠送
    if room_id == 1:
        pl_character_data.item[100] += 1
        pl_character_data.item[120] += 5
    # 输出预订成功信息
    now_draw = draw.WaitDraw()
    draw_text = _("\n成功预订了{0}，退房时间为{1}\n").format(room_name[room_id], pl_character_data.action_info.check_out_time)
    now_draw.text = draw_text
    now_draw.draw()
