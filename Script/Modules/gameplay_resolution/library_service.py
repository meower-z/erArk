"""
图书馆借还书服务（library_service）
===================================
提供图书馆的借书、还书、阅读能力门槛判定、借阅历史记录读写，以及玩家读书时的书籍摘录提示输出逻辑。
不依赖界面模块，供行动开始、状态机、结算、口上、课表与借书面板调用。
"""

import random
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import game_time
from Script.Modules.domains import abilities, activity, chara_life, library
from Script.Modules.gameplay_resolution import ui_hooks

_: FunctionType = get_text._
""" 翻译api """


def check_return_book(character_id: int) -> int:
    """
    按角色的还书概率判定是否归还一本已借书籍。
    掷出 1 到 100 的随机整数小于角色还书概率时，归还已借书籍集合中遍历到的第一本书，释放其借阅状态并更新还书历史。
    每次调用最多归还一本书。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    int -- 成功归还一本书时返回 1，未借书或未触发还书时返回 0
    """
    if len(chara_life.borrow_book_id_set(character_id)) == 0:
        return 0
    else:
        return_d100 = random.randint(1, 100)
        if return_d100 < chara_life.book_return_possibility(character_id):
            for book_id in chara_life.borrow_book_id_set(character_id):
                library.set_holder(book_id, library.FREE)
                with chara_life.borrow_book_id_set.editing(
                    character_id
                ) as borrow_book_id_set:
                    borrow_book_id_set.discard(book_id)
                update_return_history_record(character_id, book_id)
                return 1
        return 0


def check_random_borrow_book(character_id: int) -> int:
    """
    为角色随机借阅一本可读且未读完的空闲书籍。
    角色已借有书籍时直接返回 1。
    存在命中图书馆推荐类型的候选书时，有 50% 概率优先从推荐候选池随机抽取，否则从全部候选书随机抽取。
    借出后更新借阅人、已借书籍集合与借阅历史记录。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    int -- 已有借书或成功借出时返回 1，无合格书籍可借时返回 0
    """
    if len(chara_life.borrow_book_id_set(character_id)):
        return 1
    else:
        recommend_book_id_set, book_id_set = [], []
        recommended = library.recommended()
        for book_id, holder in library.holders().items():
            if holder != library.FREE:
                continue
            ability_pass = can_read_book(character_id, book_id)
            if not ability_pass:
                continue
            if book_id in chara_life.read_book_progress(character_id):
                if chara_life.read_book_progress(character_id)[book_id] >= 100:
                    continue
            book_id_set.append(book_id)
            if game_config.config_book[book_id].type in recommended:
                recommend_book_id_set.append(book_id)
        if len(recommend_book_id_set) and random.randint(0, 1) == 1:
            borrow_book_id = random.choice(recommend_book_id_set)
        elif len(book_id_set):
            borrow_book_id = random.choice(book_id_set)
        else:
            return 0
        library.set_holder(borrow_book_id, character_id)
        with chara_life.borrow_book_id_set.editing(
            character_id
        ) as borrow_book_id_set:
            borrow_book_id_set.add(borrow_book_id)
        add_borrow_history_record(character_id, borrow_book_id)
        return 1


def judge_can_get_read_book(character_id: int) -> bool:
    """
    只读判定角色当前能否获得可阅读的书籍，不修改任何状态。
    角色已借有书籍，或图书馆存在未借出、通过 can_read_book 且阅读进度低于 100 的书籍时返回 True。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    bool -- 能拿到可读书籍时返回 True，否则返回 False
    """
    if len(chara_life.borrow_book_id_set(character_id)):
        return True
    for book_id, holder in library.holders().items():
        if holder != library.FREE:
            continue
        if not can_read_book(character_id, book_id):
            continue
        if chara_life.read_book_progress(character_id).get(book_id, 0) >= 100:
            continue
        return True
    return False


def prepare_npc_read_book(character_id: int) -> bool:
    """
    为 NPC 读书行为借书并写入当前行为的书籍信息。
    先调用 check_random_borrow_book 确保角色持有书籍，再取已借集合中遍历到的最后一本书。
    该编号在 config_book 中时，将其编号与名称写入 behavior。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    bool -- 成功写入书籍信息时返回 True，借书失败或书籍不在配置中时返回 False
    """
    if not check_random_borrow_book(character_id):
        return False
    book_id = -1
    for book_id_all in chara_life.borrow_book_id_set(character_id):
        book_id = book_id_all
    if book_id not in game_config.config_book:
        return False
    name = game_config.config_book[book_id].name
    activity.update_behavior(character_id, book_id=book_id, book_name=name)
    return True


def can_read_book(character_id: int, book_cid: int) -> bool:
    """
    判定角色是否满足指定书籍的能力阅读门槛。
    书籍类型对应的 ability_id 为 0 时直接返回 True。
    大类为技能时，难度 2 要求对应能力不少于 3，难度 3 要求不少于 6。
    大类为色情时，仅对非玩家角色（character_id 不为 0）套用相同的难度能力门槛。
    Keyword arguments:
    character_id -- int，角色编号
    book_cid -- int，书籍配置编号
    Return arguments:
    bool -- 满足阅读门槛时返回 True，否则返回 False
    """
    ability = abilities.ability(character_id)
    book_data = game_config.config_book[book_cid]
    book_difficulty = book_data.difficulty
    book_type_id = book_data.type
    book_type_data = game_config.config_book_type[book_type_id]
    book_ability_id = book_type_data.ability_id
    if book_ability_id == 0:
        return True

    if book_type_data.father_type_name == _("技能"):
        if book_difficulty == 3 and ability[book_ability_id] < 6:
            return False
        if book_difficulty == 2 and ability[book_ability_id] < 3:
            return False
    elif book_type_data.father_type_name == _("色情") and character_id != 0:
        if book_difficulty == 3 and ability[book_ability_id] < 6:
            return False
        if book_difficulty == 2 and ability[book_ability_id] < 3:
            return False
    return True


def add_borrow_history_record(character_id: int, book_id: int) -> None:
    """
    向角色的借阅历史末尾追加一条新借书记录。
    书名取自 config_book，编号不存在时使用翻译后的未知书籍名称。
    新记录的借书时间为当前游戏时间，还书时间为 None，阅读次数初始为 0。
    Keyword arguments:
    character_id -- int，角色编号
    book_id -- int，书籍编号
    Return arguments:
    None -- 直接写入角色的借阅历史列表
    """
    book_name = _("未知书籍")
    if book_id in game_config.config_book:
        book_name = game_config.config_book[book_id].name

    new_record = {
        "book_id": book_id,
        "book_name": book_name,
        "borrow_time": game_time.now(),
        "return_time": None,
        "total_read_count": 0,
    }

    with chara_life.borrow_book_history.editing(
        character_id
    ) as borrow_book_history:
        borrow_book_history.append(new_record)


def update_return_history_record(character_id: int, book_id: int) -> None:
    """
    更新角色指定书籍最新一条未归还历史记录的还书信息。
    倒序查找 return_time 为 None 的匹配记录，将 return_time 设为当前游戏时间。
    若角色存在该书的阅读进度，按 max(1, 进度 // 30) 覆写该记录的 total_read_count。
    Keyword arguments:
    character_id -- int，角色编号
    book_id -- int，书籍编号
    Return arguments:
    None -- 将更新后的借阅历史写回角色状态
    """
    history = chara_life.borrow_book_history(character_id)
    for record in reversed(history):
        if record["book_id"] == book_id and record["return_time"] is None:
            record["return_time"] = game_time.now()
            if book_id in chara_life.read_book_progress(character_id):
                estimated_reads = max(
                    1,
                    chara_life.read_book_progress(character_id)[book_id] // 30,
                )
                record["total_read_count"] = estimated_reads
            break
    chara_life.borrow_book_history.set(character_id, history)


def update_read_count_in_history(character_id: int, book_id: int) -> None:
    """
    将角色指定书籍最新一条未归还历史记录的阅读次数加 1。
    倒序查找 return_time 为 None 的匹配记录，递增其 total_read_count 后写回借阅历史。
    Keyword arguments:
    character_id -- int，角色编号
    book_id -- int，书籍编号
    Return arguments:
    None -- 将更新后的借阅历史写回角色状态
    """
    history = chara_life.borrow_book_history(character_id)
    for record in reversed(history):
        if record["book_id"] == book_id and record["return_time"] is None:
            record["total_read_count"] += 1
            break
    chara_life.borrow_book_history.set(character_id, history)


def draw_book_fragment(book_id: int) -> None:
    """
    随机选取指定书籍的一条摘录，并以默认选项经 ui_hooks.emit_notice 发出提示文本。
    书籍在 config_book_excerpt_list 中无条目或摘录列表为空时直接返回，不调用随机数也不发出提示。
    Keyword arguments:
    book_id -- int，书籍配置编号
    Return arguments:
    None -- 通过 ui_hooks.emit_notice 发出格式为 "\\n……{fragment}……\\n" 的提示，无返回值
    """
    excerpt_list = game_config.config_book_excerpt_list.get(book_id)
    if not excerpt_list:
        return
    fragment = random.choice(excerpt_list)
    ui_hooks.emit_notice(f"\n……{fragment}……\n")
