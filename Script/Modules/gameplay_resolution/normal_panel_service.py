"""
日常小面板规则与状态服务（normal_panel_service）
==============================================
本模块提供关门询问、照顾婴儿、初始奖励能力选择、冰箱母乳处理与酒店订房的纯查询及状态写入。
本模块公开常量 CARE_MINUTES、PINK_VOUCHER、FRESH_MILK、BONUS_SETTING 与 ROOMS，
数据类 DoorAsk、Baby、CareOption、BonusAbility、MilkRow 与 Room。
本模块公开函数 door_ask、babies、care_title、care_options、bonus_prompt、bonus_abilities、
choose_bonus、milk_rows、take_milk、turn_milk、room_offers、booked_text 与 order_room。
本模块不执行界面绘制，也不导入 Script.UI、Script.Settle 或 Tk 模块。
"""

from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config
from Script.Core import constant, get_text
from Script.Design import game_time, map_handle
from Script.Modules.domains import abilities, action_info, activity, identity
from Script.Modules.domains import entertainment, fridge, inventory
from Script.Modules.domains import npc_template, playthrough, warehouse

_: FunctionType = get_text._
""" 翻译api """

CARE_MINUTES = 30
"""每次照顾婴儿行为消耗的分钟数。"""
PINK_VOUCHER = 4
"""粉红凭证对应的罗德岛资源编号。"""
FRESH_MILK = 31
"""鲜母乳对应的罗德岛资源编号。"""
BONUS_SETTING = 21
"""初始奖励设置表中记录自选能力的键编号。"""


@dataclass(frozen=True, slots=True)
class DoorAsk:
    """关门询问结果，包含本地化提示文本 prompt 与选择否时是否取消行为的标志 cancel_on_no。"""

    prompt: str
    cancel_on_no: bool


@dataclass(frozen=True, slots=True)
class Baby:
    """育儿室中待照料的婴儿条目，包含角色编号 chara_id、剧情 NPC 编号 adv 与按钮显示文本 label。"""

    chara_id: int
    adv: int
    label: str


@dataclass(frozen=True, slots=True)
class CareOption:
    """照顾婴儿的单个选项，包含本地化按钮文案 label、行为标识 behavior_id 与角色状态值 state。"""

    label: str
    behavior_id: str
    state: int


@dataclass(frozen=True, slots=True)
class BonusAbility:
    """初始奖励可选能力条目，包含能力编号 ability_id 与按钮显示文本 label。"""

    ability_id: int
    label: str


@dataclass(frozen=True, slots=True)
class MilkRow:
    """冰箱母乳列表中的单条角色库存展示项，包含角色编号 chara_id 与全角补齐后的文本 label。"""

    chara_id: int
    label: str


@dataclass(frozen=True, slots=True)
class Room:
    """酒店房型定义，包含粉红凭证价格 price 与附赠道具（物品编号、数量）元组 gifts。"""

    price: int
    gifts: tuple[tuple[int, int], ...]


ROOMS = (
    Room(2, ()),
    Room(10, ((100, 1), (120, 5))),
    Room(100, ()),
)
"""酒店三种房型配置元组，按标间、情趣主题房与顶级套房顺序排列。"""


def door_ask() -> DoorAsk | None:
    """
    只读查询玩家当前位置是否需要弹出关门询问及对应提示。
    若玩家行动信息中的 ask_close_door_flag 已置位则返回 None，否则按当前场景 close_type 返回提示文本与取消标志。
    Return arguments:
    DoorAsk | None -- 关门询问数据，当前地点已询问过时返回 None
    """
    if action_info.get(0, "ask_close_door_flag"):
        return None
    scene_key = map_handle.get_map_system_path_str_for_list(
        activity.position(0)
    )
    close_type = constant.scene_data[scene_key].close_type
    if close_type == 0:
        prompt = _("\n当前地点无法关门，要继续吗：")
    elif close_type == 1:
        prompt = _(
            "\n当前地点可以关门，关上之后里面的人可以出去，但外面的人将不能进来，要关门吗："
        )
    else:
        prompt = _(
            "\n你正在一个可以关门的小隔间内，关上后别人仍可以进入该地点，但无法发现隔间内的人，要关门吗："
        )
    return DoorAsk(prompt, close_type == 0)


def babies() -> tuple[Baby, ...]:
    """
    按 NPC 模板编号顺序收集当前存在且持有素质 101 的婴儿条目。
    Return arguments:
    tuple[Baby, ...] -- 含角色编号、剧情 NPC 编号与四位补零标签的婴儿元组
    """
    rows: list[Baby] = []
    for chara_id in npc_template.ids():
        if not identity.exists(chara_id):
            continue
        if not abilities.talent(chara_id)[101]:
            continue
        chara = identity.of(chara_id)
        label = f"[{str(chara.adv).rjust(4, '0')}]:{chara.name} "
        rows.append(Baby(chara_id, chara.adv, label))
    return tuple(rows)


def care_title(chara_id: int) -> str:
    """
    生成照顾指定婴儿方式选择页的标题文本。
    Keyword arguments:
    chara_id -- int，目标婴儿角色编号
    Return arguments:
    str -- 包含角色姓名的本地化标题文本
    """
    name = identity.of(chara_id).name
    return _("\n选择照顾[{0}]的方式：\n\n").format(name)


def care_options() -> tuple[CareOption, ...]:
    """
    返回按界面按钮顺序排列的六项照顾婴儿选项。
    Return arguments:
    tuple[CareOption, ...] -- 包含按钮文案、行为常量与角色状态常量的选项元组
    """
    behavior = constant.Behavior
    status = constant.CharacterStatus
    return (
        CareOption(
            _("抱一抱她"), behavior.HOLD_CHILD, status.STATUS_HOLD_CHILD
        ),
        CareOption(
            _("哼唱儿歌"),
            behavior.SING_CHILDREN_SONG,
            status.STATUS_SING_CHILDREN_SONG,
        ),
        CareOption(
            _("喂奶"), behavior.NUIRSE_CHILD, status.STATUS_NUIRSE_CHILD
        ),
        CareOption(
            _("换尿布"), behavior.CHANGE_DIAPERS, status.STATUS_CHANGE_DIAPERS
        ),
        CareOption(
            _("教她说话"), behavior.TEACH_TALK, status.STATUS_TEACH_TALK
        ),
        CareOption(_("给她玩玩具"), behavior.GIVE_TOY, status.STATUS_GIVE_TOY),
    )


def bonus_prompt(ability_id: int) -> str:
    """
    根据当前已选能力编号生成初始奖励能力选择页的提示文本。
    Keyword arguments:
    ability_id -- int，当前选中的能力编号，0 表示尚未选择
    Return arguments:
    str -- 对应的本地化提示文本
    """
    if ability_id != 0:
        ability_name = game_config.config_ability[ability_id].name
        return _("当前选择的能力为{0}，请选择新的能力：").format(ability_name)
    return _("当前没有选择能力，请选择：")


def bonus_abilities() -> tuple[BonusAbility, ...]:
    """
    按能力配置顺序返回编号在 40 至 49 之间的初始奖励候选能力。
    Return arguments:
    tuple[BonusAbility, ...] -- 含能力编号与格式化标签的候选元组
    """
    return tuple(
        BonusAbility(cid, f"[{cid}]{ability.name}")
        for cid, ability in game_config.config_ability.items()
        if 40 <= cid <= 49
    )


def choose_bonus(ability_id: int) -> None:
    """
    将选定的初始奖励能力编号写入 playthrough.FIRST_BONUS 的设置键 21。
    Keyword arguments:
    ability_id -- int，选定的能力编号
    Return arguments:
    None -- 无返回值
    """
    playthrough.set_setting(playthrough.FIRST_BONUS, BONUS_SETTING, ability_id)


def milk_rows() -> tuple[MilkRow, ...]:
    """
    读取冰箱母乳表并生成按全角空格补齐至 20 字符的展示行元组。
    Return arguments:
    tuple[MilkRow, ...] -- 冰箱中各干员母乳库存的展示行元组
    """
    rows: list[MilkRow] = []
    for chara_id, milk in fridge.table(fridge.MILK).items():
        chara = identity.of(chara_id)
        label = ("  [{}]{}：{}ml").format(
            str(chara.adv).rjust(4, "0"), chara.name, milk
        )
        rows.append(MilkRow(chara_id, label.ljust(20, "　")))
    return tuple(rows)


def take_milk(chara_id: int) -> str:
    """
    从冰箱取出指定角色的母乳，生成菜谱 1001 食物并放入玩家背包。
    Keyword arguments:
    chara_id -- int，产出该母乳的角色编号
    Return arguments:
    str -- 带走成功后的本地化提示文本
    """
    from Script.System.Cooking_System import cooking

    name = identity.of(chara_id).name
    food = cooking.create_food("", 1001, 5, name)
    food.milk_ml = fridge.take(fridge.MILK, chara_id)
    inventory.put_food(0, food)
    return _("\n  你将{0}的母乳（{1}ml）放进了背包\n").format(
        name, food.milk_ml
    )


def turn_milk(chara_id: int) -> str:
    """
    从冰箱取出指定角色的母乳并按等量计入罗德岛资源鲜母乳。
    Keyword arguments:
    chara_id -- int，产出该母乳的角色编号
    Return arguments:
    str -- 转化成功后的本地化提示文本
    """
    name = identity.of(chara_id).name
    milk = fridge.take(fridge.MILK, chara_id)
    warehouse.add(FRESH_MILK, milk)
    return _("\n  你将{0}的母乳（{1}ml）转化为了【鲜母乳】\n").format(
        name, milk
    )


def _room_names() -> tuple[str, str, str]:
    """
    返回酒店三种房型的本地化名称元组。
    Return arguments:
    tuple[str, str, str] -- 标间、情趣主题房与顶级套房的本地化名称
    """
    return (_("标间"), _("情趣主题房"), _("顶级套房"))


def room_offers() -> tuple[str, ...]:
    """
    在尚未预订酒店房间时返回三种房型的按钮文案，已预订时返回空元组。
    Return arguments:
    tuple[str, ...] -- 可选房型文案元组或空元组
    """
    if entertainment.hotel_room() != 0:
        return ()
    return (
        _("标间(2粉红凭证)"),
        _("情趣主题房(10粉红凭证)"),
        _("顶级套房(100粉红凭证)"),
    )


def booked_text() -> str | None:
    """
    查询当前酒店预订状态提示，未预订时返回 None。
    Return arguments:
    str | None -- 包含已订房型与次日 12 点退房日期的提示文本，或 None
    """
    room = entertainment.hotel_room()
    if room == 0:
        return None
    return _("当前已预订{0}，退房时间为{1}日12点\n").format(
        _room_names()[room - 1],
        action_info.get(0, "check_out_time").day,
    )


def order_room(room_id: int) -> str:
    """
    检查粉红凭证余额并完成指定房型预订，扣费、记录房型与次日 12 点退房时间并发放附赠道具。
    Keyword arguments:
    room_id -- int，房型下标（0 标间、1 情趣主题房、2 顶级套房）
    Return arguments:
    str -- 凭证不足时的拒绝提示或预订成功的本地化提示文本
    """
    room = ROOMS[room_id]
    name = _room_names()[room_id]
    if warehouse.amount(PINK_VOUCHER) < room.price:
        return _("\n粉红凭证不足，无法预订{0}\n").format(name)
    warehouse.add(PINK_VOUCHER, -room.price)
    entertainment.set_hotel_room(room_id + 1)
    tomorrow = game_time.get_sub_date(day=1, old_date=game_time.now())
    action_info.set(0, "check_out_time", tomorrow.replace(hour=12))
    for item_id, count in room.gifts:
        inventory.add_item(0, item_id, count)
    return _("\n成功预订了{0}，退房时间为{1}\n").format(
        name, action_info.get(0, "check_out_time")
    )
