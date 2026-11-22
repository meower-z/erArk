"""
孩子日常日程的模板读写与每日改写
================================
日程与课表是**两层不同粒度**的东西，本模块只管前者：

    课表 —— 按 45 分钟的**节次**排（见 schedule_handle），管的是"上什么课"
    日程 —— 按上午/下午/晚上三个**时段**排（本模块），管的是"没课的时候干什么"

日程不另造一条 AI 链，只改写角色键 `life.entertainment_type` 的三个槽位。娱乐 AI 链照着这三个槽位做事。

**改写必须在每日娱乐刷新之后**：`past_day_settle` 先调用 `get_chara_entertainment` 与
`egg_handle.replace_entertainment_for_eggs`，再调用 `apply_schedule_for_child`。
顺序颠倒时，当天写进去的值会被随机值冲掉。

**优先级按节次算**：有课的节次由工作链里学生岗的上课目标先接管。
没课的节次工作链没有行命中，才轮到槽位里的活动，所以改写时不避让有课的时段。
学生岗白天也算娱乐时间（handle_premise_time._judge_free_daytime），否则周一到周六的白天走不到娱乐链。

数据分两层存，孩子再多，改日程的操作量也不翻倍：

    模板本体  base.child_schedule_template（经 education 读写）  全局共享一份
    孩子身上  CHILD_GROWTH.schedule_template_id       只存模板编号
              CHILD_GROWTH.schedule_override          只存对模板的单项覆盖

给三个孩子都改成玩乐优先，是改一个模板而不是改三份日程。
"""

from types import FunctionType
from Script.Core import get_text
from Script.Config import game_config
from Script.Modules.domains import education, growth, chara_life, relations
from Script.System.Education_System import (
    education_constant,
    schedule_handle,
)
from Script.Modules.domains import identity

_: FunctionType = get_text._
""" 翻译api """


def get_entertainment_cid_by_name(name: str) -> int:
    """
    按娱乐名反查 Entertainment.csv 的cid
    Keyword arguments:
    name -- 娱乐名
    Return arguments:
    int -- 娱乐cid，查不到则为0
    """
    if not name:
        return 0
    for cid, data in game_config.config_entertainment.items():
        if data.name == name:
            return cid
    return 0


def _default_templates() -> dict[int, dict]:
    return {
        tid: {
            education_constant.TEMPLATE_KEY_NAME: name,
            education_constant.TEMPLATE_KEY_SLOT: {
                slot: get_entertainment_cid_by_name(ent_name)
                for slot, ent_name in enumerate(
                    education_constant.PRESET_TEMPLATE_SLOT_NAME[tid]
                )
            },
        }
        for tid, name in education_constant.PRESET_TEMPLATE_NAME.items()
    }


def init_default_template() -> None:
    """把四套预设模板写进全局模板表（只在表为空时写一次，已有模板时跳过）"""
    if not education.templates():
        education.set_templates(_default_templates())


def get_template_data(template_id: int) -> dict | None:
    """取一套模板的数据；全局模板表为空时返回预设模板副本而不写入"""
    stored = education.templates()
    return (stored if stored else _default_templates()).get(template_id, None)


def get_all_template_id() -> list[int]:
    """取全部模板编号，按编号升序"""
    stored = education.templates()
    return sorted((stored if stored else _default_templates()).keys())


def set_template_slot(
    template_id: int, slot: int, entertainment_id: int
) -> None:
    """改一套模板某个时段的活动（entertainment_id 为 0 表示保持随机）"""
    init_default_template()
    template_data = education.template(template_id)
    if template_data is None:
        return
    template_data.setdefault(education_constant.TEMPLATE_KEY_SLOT, {})[
        slot
    ] = entertainment_id
    education.put_template(template_id, template_data)


def judge_template_is_preset(template_id: int) -> bool:
    """校验一套模板是不是四套预设之一"""
    return template_id in education_constant.PRESET_TEMPLATE_NAME


def create_template(name: str) -> int:
    """新建一套空模板，编号取现存最大编号 + 1；name 留空则自动命名"""
    init_default_template()
    template_dict = education.templates()
    new_id = (max(template_dict.keys()) if template_dict else 0) + 1
    name = name.strip() if name else ""
    if not name:
        name = _("模板{0}").format(new_id)
    education.put_template(
        new_id,
        {
            education_constant.TEMPLATE_KEY_NAME: name,
            education_constant.TEMPLATE_KEY_SLOT: {},
        },
    )
    return new_id


def rename_template(template_id: int, name: str) -> bool:
    """给一套模板改名；预设也可改名，留空不改"""
    init_default_template()
    template_data = education.template(template_id)
    if template_data is None:
        return False
    name = name.strip() if name else ""
    if not name:
        return False
    template_data[education_constant.TEMPLATE_KEY_NAME] = name
    education.put_template(template_id, template_data)
    return True


def delete_template(template_id: int) -> bool:
    """删掉一套自建模板（预设不可删），删前把全部引用该模板的角色解开"""
    init_default_template()
    if judge_template_is_preset(template_id):
        return False
    if education.template(template_id) is None:
        return False
    for cid in identity.table():
        with growth.editing(cid, create=False) as growth_data:
            if (
                growth_data is None
                or growth_data.schedule_template_id != template_id
            ):
                continue
            growth_data.schedule_template_id = 0
            growth_data.schedule_override = {}
    return education.delete_template(template_id)


def apply_template(character_id: int, template_id: int) -> None:
    """给一个孩子套用模板（0 表示取消），换模板时清空该孩子的单项覆盖"""
    if template_id:
        init_default_template()
    with growth.editing(character_id) as growth_data:
        assert growth_data is not None
        if growth_data.schedule_template_id != template_id:
            growth_data.schedule_override = {}
        growth_data.schedule_template_id = template_id


def batch_apply_template(character_id_list: list[int], template_id: int) -> int:
    """
    把同一套模板批量套用到多个孩子（口径 4 的核心操作）
    Keyword arguments:
    character_id_list -- 角色id列表
    template_id -- 模板编号
    Return arguments:
    int -- 实际套用成功的人数
    """
    count = 0
    for character_id in character_id_list:
        if not identity.exists(character_id):
            continue
        apply_template(character_id, template_id)
        count += 1
    return count


def set_child_override(
    character_id: int, slot: int, entertainment_id: int
) -> None:
    """
    给一个孩子单独覆盖某个时段的活动，不影响模板本体与其他孩子
    Keyword arguments:
    character_id -- 角色id
    slot -- 时段0~2
    entertainment_id -- 娱乐cid，0表示取消覆盖（回到模板值）
    Return arguments:
    无
    """
    with growth.editing(character_id) as growth_data:
        assert growth_data is not None
        if entertainment_id:
            growth_data.schedule_override[slot] = entertainment_id
        else:
            growth_data.schedule_override.pop(slot, None)


def get_child_slot_activity(character_id: int, slot: int) -> int:
    """
    取一个孩子某时段最终生效的日程活动（覆盖优先于模板）
    Keyword arguments:
    character_id -- 角色id
    slot -- 时段0~2
    Return arguments:
    int -- 娱乐cid，0表示该时段没有固定日程（保持每日随机）
    """
    growth_data = growth.of(character_id)
    if growth_data is None:
        return 0
    # 单孩覆盖优先
    if slot in growth_data.schedule_override:
        return growth_data.schedule_override[slot]
    template_data = get_template_data(growth_data.schedule_template_id)
    if template_data is None:
        return 0
    return template_data.get(education_constant.TEMPLATE_KEY_SLOT, {}).get(
        slot, 0
    )


def judge_activity_need_pass(character_id: int, entertainment_id: int) -> bool:
    """
    校验一个孩子是否满足某项娱乐的 need 条件（Plan 22 二期第一轮追加）

    这道校验非做不可：模板是**全局共享**的，而 need 是**逐人**的。
       如上课（无课时自习）配的是 W152|1（限学生岗）；同一套模板套到非学生岗的干员身上时，
       不校验就会把活动照写进她的 entertainment_type，那一格既做不了该活动也不会随机娱乐，白白空转一个时段。
       不满足的时段就跳过不改写、保留当天的随机娱乐——这就是面板上说的「退回到自由选择娱乐活动」。
    引擎只在**随机抽娱乐**时校验过 need（handle_npc_ai.get_chara_entertainment），
       日程改写是另一条写入路径，必须自己校验。
    Keyword arguments:
    character_id -- 角色id
    entertainment_id -- 娱乐配置cid
    Return arguments:
    bool -- 是否满足；无 need 条件的一律为True
    """
    from Script.Design import attr_calculation

    if entertainment_id not in game_config.config_entertainment:
        return False
    need_text = game_config.config_entertainment[entertainment_id].need
    if not need_text or need_text == education_constant.TEMPLATE_NEED_NONE:
        return True
    need_list = (
        need_text.split(education_constant.TEMPLATE_NEED_SPLIT)
        if education_constant.TEMPLATE_NEED_SPLIT in need_text
        else [need_text]
    )
    judge, _reason = attr_calculation.judge_require(need_list, character_id)
    return bool(judge)


def judge_activity_place_open(entertainment_id: int) -> bool:
    """
    校验一项娱乐的地点此刻是否已开放（Plan 27 §3.1）
    Keyword arguments:
    entertainment_id -- 娱乐配置cid
    Return arguments:
    bool -- 是否已开放；地点为「无」或不在 Facility_open 表里的恒为True，配置里没有的娱乐为False
    功能: 与寻路的 wait_open、成年干员随机娱乐的场所判定同口径（schedule_handle.judge_scene_open）。
          日程改写是把活动直接写进 entertainment_type 的路径，不查这一道就会把孩子派到还没解锁的场所
             （如教育区 2 级才开的黄澄澄游戏室）：寻路在门口返回 wait_open、移动时长为 0，通用移动模块退成等待 1 分钟，
             下一次决策又派同一个移动，整个时段在门口一分钟一分钟地空转
    """
    if entertainment_id not in game_config.config_entertainment:
        return False
    return schedule_handle.judge_scene_open(
        game_config.config_entertainment[entertainment_id].place
    )


def judge_activity_schedulable(entertainment_id: int) -> bool:
    """
    校验一项娱乐能不能排进孩子的日程（Plan 28 §3.3）
    Keyword arguments:
    entertainment_id -- 娱乐配置cid
    Return arguments:
    bool -- 能排为True；照料卵（pregnancy_constant.TEND_EGGS_ENTERTAINMENT_ID）为False
    功能: 照料卵是妊娠系统给持卵者的专用娱乐：随机池专门排除它，
    只由每日的持卵钩子（egg_handle.replace_entertainment_for_eggs）换上；
          它的 need 列却是「无」，不在这里挡的话「选择活动」里就有它。排给孩子后她每晚去育儿室，
          状态机 427 找不到可鉴定的卵就「孵化卵」一小时，还拿医疗经验。
          候选表、每日改写、日程行三处共用本函数
    """
    from Script.System.Pregnancy_System import pregnancy_constant

    return entertainment_id != pregnancy_constant.TEND_EGGS_ENTERTAINMENT_ID


def apply_schedule_for_child(character_id: int) -> None:
    """
    按日程把一个孩子今天的 entertainment_type 三个槽位改写掉（每日一次）

    本函数必须在 `handle_npc_ai.get_chara_entertainment` **之后**调用，见模块头注释。
    时段里有课的节次不用避让：上课（工作链里学生岗的目标行，Plan 24）在**节次**级别排在娱乐链之前，
       有课的节次照常上课，同一时段里没课的节次才按这里写进去的活动走（2026-09-10 二期方案 §9.2.9；
       此前要求整段没课才改写，结果上午只要有一节课，整个上午的日程都不生效）。
    不满足 need 的、地点还没开放的（Plan 27 §3.1）、不可排进日程的（旧档里排上的照料卵，Plan 28 §3.3）时段都跳过不改写，
       保留当天的随机娱乐，即退回自由选择。
    当天已被持卵钩子换成照料卵的时段也不覆盖（Plan 28 §3.3）：跨天结算里钩子先于本函数（past_day_settle），
       改回模板的活动的话，持卵者那个时段就不去照料卵了。
    不是女儿、又不在学生岗的整个跳过（Plan 32 §3.12 L18）：成年干员当学生时套的模板，改岗后不再改写她的娱乐
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    无
    """
    growth_data = growth.of(character_id)
    # 没有养成数据、或没套用任何模板且没有任何覆盖的，不改写
    if growth_data is None:
        return
    if (
        not growth_data.schedule_template_id
        and not growth_data.schedule_override
    ):
        return
    if (
        relations.father_id(character_id) != 0
        and chara_life.work_type(character_id)
        != education_constant.STUDENT_WORK_TYPE
    ):
        return
    with chara_life.entertainment_type.editing(character_id) as slots:
        for slot in range(education_constant.SLOT_COUNT):
            entertainment_id = get_child_slot_activity(character_id, slot)
            if not entertainment_id:
                continue
            if entertainment_id not in game_config.config_entertainment:
                continue
            # 持卵钩子今天换上的照料卵不覆盖：照料卵只有钩子会写（随机池与日程候选都排除它），槽位里是它就是今天换上的
            if not judge_activity_schedulable(slots[slot]):
                continue
            # 不可排进日程的（旧档里已排上的照料卵）跳过，退回自由选择
            if not judge_activity_schedulable(entertainment_id):
                continue
            # 不满足该娱乐 need 条件的孩子跳过这一格，留着当天的随机娱乐比空转强
            if not judge_activity_need_pass(character_id, entertainment_id):
                continue
            # 地点还没开放的活动也跳过。写进去的话，角色会在门口一分钟一分钟地空转一整个时段
            if not judge_activity_place_open(entertainment_id):
                continue
            slots[slot] = entertainment_id


def get_child_schedule_text(character_id: int) -> str:
    """
    取一个孩子当前日程的一行摘要，供个人课表面板显示
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    str -- 形如「均衡（上课（无课时自习） / 下棋 / 看电影）」，未套用模板则为「未设置」；
           时段值为 0 显示「自由选择娱乐活动」，这个孩子不满足条件的活动带「（条件不符→自由选择）」标注，
           地点还没开放的带「（未开放→自由选择）」（Plan 27）
    """
    growth_data = growth.of(character_id)
    if growth_data is None or (
        not growth_data.schedule_template_id
        and not growth_data.schedule_override
    ):
        return _("未设置")
    template_data = get_template_data(growth_data.schedule_template_id)
    template_name = (
        template_data[education_constant.TEMPLATE_KEY_NAME]
        if template_data is not None
        else _("自定义")
    )
    slot_text_list = [
        get_child_slot_activity_text(character_id, slot)
        for slot in range(education_constant.SLOT_COUNT)
    ]
    return "{}（{}）".format(template_name, " / ".join(slot_text_list))


def get_template_use_count(template_id: int) -> int:
    """
    统计有多少个孩子正在套用某套模板，供模板面板的「套用中」列显示
    Keyword arguments:
    template_id -- 模板编号
    Return arguments:
    int -- 人数
    功能: 遍历全部角色（Plan 32 §3.12 L17）：外勤 / 外交 / 离线中的女儿不在 npc_id_got，回岛后照样套着这套模板，
          此前漏数；与 delete_template 解开引用的范围一致
    """
    count = 0
    for cid in identity.table():
        cg = growth.of(cid)
        if cg is not None and cg.schedule_template_id == template_id:
            count += 1
    return count


def get_schedule_activity_candidate() -> list[int]:
    """
    取可排进日程的娱乐候选表：全部娱乐（含教育区 15x 段的日程专用活动），去掉0号模板行与不可排的照料卵（Plan 28 §3.3）
    Keyword arguments:
    无
    Return arguments:
    List[int] -- 娱乐cid列表，按cid升序
    """
    return sorted(
        cid
        for cid in game_config.config_entertainment
        if cid and judge_activity_schedulable(cid)
    )


def get_activity_name(entertainment_id: int) -> str:
    """
    取一项日程活动的显示名
    Keyword arguments:
    entertainment_id -- 娱乐cid，0 表示「自由选择娱乐活动」
    Return arguments:
    str -- 0 为「自由选择娱乐活动」；配置里有的取娱乐名；配置里没有的（如被删掉的旧编号）为「--」
    """
    if entertainment_id == education_constant.SCHEDULE_FREE_CHOICE:
        return education_constant.SCHEDULE_FREE_CHOICE_NAME
    if entertainment_id in game_config.config_entertainment:
        return game_config.config_entertainment[entertainment_id].name
    return "--"


def get_activity_age_limit_talent_list(entertainment_id: int) -> list[int]:
    """
    从一项娱乐的 need 列里解出它要求的成长阶段素质（年龄限制）
    Keyword arguments:
    entertainment_id -- 娱乐cid
    Return arguments:
    List[int] -- 要求持有的阶段素质id列表（101~104 之一或多个），没有年龄限制则为空表
    功能: need 先按 & 拆成「且」项，再按 / 拆成「或」项，只认 T<阶段素质id>|1 这种写法。
          不写死具体活动：年龄限制是配置，往后加一项带年龄需求的活动，
             面板的第二行与「限××」标注会自动跟上
    """
    if entertainment_id not in game_config.config_entertainment:
        return []
    need_text = game_config.config_entertainment[entertainment_id].need
    if not need_text or need_text == education_constant.TEMPLATE_NEED_NONE:
        return []
    result = []
    for and_text in need_text.split(education_constant.TEMPLATE_NEED_SPLIT):
        for raw_text in and_text.split(
            education_constant.TEMPLATE_NEED_OR_SPLIT
        ):
            one_text = raw_text.strip()
            if not one_text.startswith("T") or "|" not in one_text:
                continue
            talent_part, value_part = one_text[1:].split("|", 1)
            if not talent_part.isdigit() or value_part.strip() != "1":
                continue
            talent_id = int(talent_part)
            if (
                talent_id in education_constant.STAGE_TALENT_NAME
                and talent_id not in result
            ):
                result.append(talent_id)
    return result


def get_activity_age_limit_text(entertainment_id: int) -> str:
    """
    取一项娱乐的年龄限制标注文本，供「选择活动」面板显示
    Keyword arguments:
    entertainment_id -- 娱乐cid
    Return arguments:
    str -- 形如「限学员」，没有年龄限制则为空串
    """
    talent_list = get_activity_age_limit_talent_list(entertainment_id)
    if not talent_list:
        return ""
    return _("限{0}").format(
        "/".join(
            education_constant.STAGE_TALENT_NAME[talent_id]
            for talent_id in talent_list
        )
    )


def get_schedule_activity_rows() -> tuple[list[int], list[int], list[int]]:
    """
    把可排进日程的活动分成「选择活动」面板的三组
    Keyword arguments:
    无
    Return arguments:
    Tuple[List[int], List[int], List[int]] -- (第一行, 第二行, 其余)：
        第一行固定是 上课（无课时自习）与 自由选择娱乐活动（0）；
        第二行是有年龄需求的活动（从 need 列现算，没有时为空）；
        其余娱乐按 cid 升序
    """
    candidate_list = get_schedule_activity_candidate()
    first_row = [
        cid
        for cid in education_constant.CHILD_SCHEDULE_FIRST_ROW
        if cid == education_constant.SCHEDULE_FREE_CHOICE
        or cid in candidate_list
    ]
    age_row = [
        cid
        for cid in candidate_list
        if cid not in first_row and get_activity_age_limit_talent_list(cid)
    ]
    other_list = [
        cid
        for cid in candidate_list
        if cid not in first_row and cid not in age_row
    ]
    return first_row, age_row, other_list


def get_child_slot_activity_text(character_id: int, slot: int) -> str:
    """
    取一个孩子某时段日程活动的显示文本，条件不符时标注会退回自由选择
    Keyword arguments:
    character_id -- 角色id
    slot -- 时段0~2
    Return arguments:
    str -- 活动名；0 为「自由选择娱乐活动」；
    活动存在但这个孩子不满足其 need 条件、或是不可排进日程的照料卵（Plan 28 §3.3）时为
           「X（条件不符→自由选择）」，满足条件但地点还没开放时为「X（未开放→自由选择）」（Plan 27 §3.1）
    功能: 供个人课表的日程行与日程微调页共用。
          只做显示：真正的「退回」发生在 apply_schedule_for_child 的可排、need 与地点校验里，这里只是把它说给玩家听
    """
    entertainment_id = get_child_slot_activity(character_id, slot)
    name = get_activity_name(entertainment_id)
    if (
        entertainment_id
        and entertainment_id in game_config.config_entertainment
    ):
        # 旧档里已排上的照料卵：改写时直接跳过，排在 need 判定之前
        if not judge_activity_schedulable(
            entertainment_id
        ) or not judge_activity_need_pass(character_id, entertainment_id):
            return _("{0}（条件不符→自由选择）").format(name)
        if not judge_activity_place_open(entertainment_id):
            return _("{0}（未开放→自由选择）").format(name)
    return name
