"""
载具服务（vehicle_service）
===========================
提供基地载具表补齐与外勤委托载具损坏回收结算。
不直接导入界面模块，供新游戏初始化、读档修补与外勤委托结算调用。
"""

import random
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Modules.domains import commission
from Script.Modules.save_load import reset

_: FunctionType = get_text._
""" 翻译api """


@reset.repair
def update_basement_vehicle_data() -> None:
    """
    补齐基地载具表中缺失的载具配置条目。
    已通过 reset.repair 注册为读档修补步骤，也在新游戏初始化时调用。
    底层调用 commission.fill_vehicles，按配置顺序在表尾为缺失载具追加 (0, 0)，无缺失时不写入。
    Return arguments:
    None -- 直接更新基地载具表
    """
    commission.fill_vehicles()


def settle_vehicle(commision_id: int) -> str:
    """
    结算指定外勤委托派出载具的损坏与归还。
    按委托等级乘以 0.05 作为初始损坏率，逐辆抽取随机数。
    随机数低于当前损坏率时，该载具持有数与外勤中数各减 1，拼接损坏提示并将后续损坏率减半。
    未命中损坏时仅将该载具外勤中数减 1。
    Keyword arguments:
    commision_id -- int，外勤委托编号
    Return arguments:
    str -- 拼接后的载具损坏提示文本，无载具损坏时返回空字符串
    """
    vehicle_text = ""
    send_vehicle_list = commission.ongoing()[commision_id].vehicles
    base_rate = 0.05 * game_config.config_commission[commision_id].level
    for vehicle_id in send_vehicle_list:
        if random.random() < base_rate:
            commission.add_vehicle(vehicle_id, owned=-1, out=-1)
            vehicle_text += _("({0}损坏)").format(
                game_config.config_vehicle[vehicle_id].name
            )
            base_rate *= 0.5
        else:
            commission.add_vehicle(vehicle_id, out=-1)

    return vehicle_text
