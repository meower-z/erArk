# -*- coding: UTF-8 -*-
"""sex_class_handle：临时课程、提醒、开课下课、旁观结算"""

from _bootstrap import DEFAULT_TIME, SCENE_DORM, SCENE_EDU_ENTRY, _
from _bootstrap import check, child_growth, class_ai, classroom_path
from _bootstrap import clear_schedules, constant, constant_promise, datetime
from _bootstrap import drawn_text, education, education_constant, finish
from _bootstrap import game_config, game_time, game_type, growth
from _bootstrap import growth_handle, handle_premise, make_character, move_to
from _bootstrap import open_all_classroom, period_time, pl, play, random
from _bootstrap import remove_character, schedule_handle, section, set_time
from _bootstrap import sex_class_handle, sync
from Script.Design import handle_npc_ai, instuct_judege
from Script.Settle import common_default
from Script.Modules.domains import activity, chara_life, flags, modes
from Script.Modules.domains import player_ability, relations, status
from tests import chara_abilities as ca, kernel_data

open_all_classroom()
clear_schedules()
ROOM_P = _("实践教室一")
mother = make_character(102, "母亲", 0)
student_a = make_character(
    201, "女儿A", 152, daughter=True, stage=103, mother_id=102
)
student_a_exp = ca.experience(student_a)
student_b = make_character(
    202, "女儿B", 152, daughter=True, stage=103, mother_id=102
)
adult = make_character(301, "成年干员", 21)
today = game_time.now().date().toordinal()

section("键与存取")
check("键格式", sex_class_handle.get_class_key(739510, 3) == "739510-3")
check(
    "解析",
    sex_class_handle.parse_class_key("739510-3") == (739510, 3)
    and sex_class_handle.parse_class_key("739510--1") == (739510, -1),
)
check(
    "非法键 (-1, -1)",
    sex_class_handle.parse_class_key("abc") == (-1, -1)
    and sex_class_handle.parse_class_key("1-x") == (-1, -1),
)
check("没排时 None", sex_class_handle.get_temp_class(today, 0) is None)
data = sex_class_handle.set_temp_class(today, 2, ROOM_P, 70, must_attend=[201])
check(
    "排课数据",
    data["classroom"] == ROOM_P
    and data["ability_id"] == 70
    and data["must_attend"] == [201]
    and data["notified"] == [False, False, False]
    and not data["running"]
    and not data["reserved"],
)
check("读回同一条", sex_class_handle.get_temp_class(today, 2) == data)
check(
    "当场开课",
    sex_class_handle.set_temp_class(today, 3, ROOM_P, 71, running=True)[
        "notified"
    ]
    == [True, True, True],
)
running_class = sex_class_handle.get_running_class()
assert running_class is not None
check(
    "运行中的那条",
    running_class["ability_id"] == 71
    and sex_class_handle.get_running_class_key()
    == sex_class_handle.get_class_key(today, 3),
)
sex_class_handle.del_temp_class(today, 3)
check(
    "删掉后无运行课",
    sex_class_handle.get_running_class() is None
    and sex_class_handle.get_running_class_key() == "",
)
sex_class_handle.del_temp_class(today, 99)
check("删不存在的不报错", True)

section("过期清理")
sex_class_handle.set_temp_class(today - 1, 1, ROOM_P, 70)
sex_class_handle.set_temp_class(today - 2, 1, ROOM_P, 70, running=True)
sex_class_handle.set_temp_class(today + 1, 1, ROOM_P, 70)
kernel_data.set_world(modes.set_sex_class, True)
kernel_data.put(flags.set, pl.cid, is_h=True)
check(
    "清掉昨天的、保留运行中的（课还在上：课堂模式开着、玩家在 H 中）与今后的",
    sex_class_handle.clean_expired_temp_class() == 1
    and sex_class_handle.get_temp_class(today - 2, 1) is not None
    and sex_class_handle.get_temp_class(today + 1, 1) is not None,
)
kernel_data.set_world(modes.set_sex_class, False)
kernel_data.put(flags.set, pl.cid, is_h=False)
education.clear_temp_classes()

section("星期 → 日期")
set_time(period_time(3))
weekday = game_time.now().weekday()
check(
    "今天、还没开始的节次 → 今天",
    sex_class_handle.get_date_ordinal_by_week_day(weekday, 5) == today,
)
check(
    "今天、已开始的节次 → 下周",
    sex_class_handle.get_date_ordinal_by_week_day(weekday, 3) == today + 7,
)
check(
    "别的星期 → 未来 1~6 天内",
    1
    <= sex_class_handle.get_date_ordinal_by_week_day((weekday + 2) % 7, 0)
    - today
    <= 6,
)
# 季月最后一天的下一天是下个季月的 1 日，星期按游戏日历逐日连续（9/29 周二、9/30 周三 → 12/1 周四、12/2 周五）
set_time(datetime.datetime(2026, 9, 29, 10, 0))
month_jump = sex_class_handle.get_date_ordinal_by_week_day(4, 0)
check(
    "月底预约周五 → 按游戏时钟落在 12/2，而不是永远不会到的 10/2",
    month_jump == datetime.date(2026, 12, 2).toordinal(),
    datetime.date.fromordinal(month_jump),
)
check(
    "月底预约周三 → 就是明天 9/30",
    sex_class_handle.get_date_ordinal_by_week_day(2, 0)
    == datetime.date(2026, 9, 30).toordinal(),
)
set_time(period_time(3))

section("谁能参加")
check("玩家自己不算", not sex_class_handle.judge_can_join_sex_class(0))
check("不存在的角色不算", not sex_class_handle.judge_can_join_sex_class(999))
# 前置修习（口径 63 宽松版，第五轮）：个人课表里没有性技科目的教室课就不能来
check(
    "没修过性技课：不能参加",
    not sex_class_handle.judge_has_sex_skill_course(201)
    and not sex_class_handle.judge_can_join_sex_class(201),
)
check(
    "点名必修豁免前置修习",
    sex_class_handle.judge_can_join_sex_class(201, check_course=False),
)
schedule_handle.set_class_cell(ROOM_P, weekday, 8, 74, -1)
schedule_handle.set_class_cell(_("理论教室一"), weekday, 8, 45, -1)
schedule_handle.set_selected_course(
    202, weekday, 8, education_constant.COURSE_TYPE_THEORY, _("理论教室一")
)
check(
    "只修了学识：仍不能参加",
    not sex_class_handle.judge_has_sex_skill_course(202),
)
schedule_handle.set_selected_course(
    201, weekday, 8, education_constant.COURSE_TYPE_PRACTICE, ROOM_P
)
schedule_handle.set_selected_course(
    202, (weekday + 1) % 7, 8, education_constant.COURSE_TYPE_PRACTICE, ROOM_P
)
schedule_handle.set_class_cell(ROOM_P, (weekday + 1) % 7, 8, 71, -1)
check(
    "个人课表里有性技教室课：可以参加",
    sex_class_handle.judge_has_sex_skill_course(201)
    and sex_class_handle.judge_has_sex_skill_course(202),
)
check("女儿零门槛", sex_class_handle.judge_can_join_sex_class(201))
kernel_data.put(flags.set, student_a.cid, imprisonment=True)
check("被监禁不算", not sex_class_handle.judge_can_join_sex_class(201))
kernel_data.put(flags.set, student_a.cid, imprisonment=False)
kernel_data.put(activity.set_dead, student_a.cid, True)
check("死亡不算", not sex_class_handle.judge_can_join_sex_class(201))
kernel_data.put(activity.set_dead, student_a.cid, False)
try:
    adult_ok = sex_class_handle.judge_can_join_sex_class(301)
    check(
        "成年干员走实行值判定（无实行值 → 不能）", adult_ok is False, adult_ok
    )
except Exception as error:
    check("成年干员实行值判定不抛异常", False, repr(error))
move_to(0, classroom_path(ROOM_P))
move_to(201, classroom_path(ROOM_P))
move_to(202, classroom_path(ROOM_P))
check(
    "场景学生名单",
    sex_class_handle.get_scene_student_list() == [201, 202]
    or sorted(sex_class_handle.get_scene_student_list()) == [201, 202],
)
check(
    "指定场景为空场景",
    sex_class_handle.get_scene_student_list(SCENE_EDU_ENTRY) == [],
)
schedule_handle.set_selected_course(
    201, weekday, 2, education_constant.COURSE_TYPE_PRACTICE, ROOM_P
)
check(
    "选修名单：这一节选了这间教室的人",
    sex_class_handle.get_selected_student_list(ROOM_P, weekday, 2) == [201],
)
chara_life.work_type.set(student_a.cid, 21)
check(
    "选修名单只收学生岗：改了岗的女儿课表里还留着这一格，也不算「会来」（Plan 28 §3.4）",
    sex_class_handle.get_selected_student_list(ROOM_P, weekday, 2) == [],
)
chara_life.work_type.set(student_a.cid, 152)
check("在实践教室 → 可开课场所", sex_class_handle.judge_in_sex_class_place(0))
move_to(0, SCENE_DORM)
check("在宿舍 → 不是", not sex_class_handle.judge_in_sex_class_place(0))
move_to(0, classroom_path(ROOM_P))

section("提醒")
now_a = datetime.datetime(2026, 9, 7, 13, 0)
check(
    "跨越判定",
    sex_class_handle.judge_time_crossed(
        now_a, now_a - datetime.timedelta(minutes=5), now_a
    )
    and not sex_class_handle.judge_time_crossed(
        now_a, now_a, now_a + datetime.timedelta(minutes=5)
    )
    and not sex_class_handle.judge_time_crossed(None, now_a, now_a),
)
check(
    "补齐旧档的 notified",
    sex_class_handle.fix_notified({"notified": [True]}) == [True, False, False]
    and sex_class_handle.fix_notified({"notified": "x"})
    == [False, False, False],
)
check(
    "节次起止时刻",
    sex_class_handle.get_period_start_time(today, 4) == period_time(4)
    and sex_class_handle.get_period_end_time(today, 4)
    == period_time(4) + datetime.timedelta(minutes=45)
    and sex_class_handle.get_period_start_time(today, 9) is None,
)
education.clear_temp_classes()
reserved = sex_class_handle.set_temp_class(
    today, 4, ROOM_P, 70, must_attend=[201]
)
text_list = sex_class_handle.check_and_send_notify(
    period_time(4) - datetime.timedelta(minutes=60),
    period_time(4) - datetime.timedelta(minutes=20),
)


def _temp(period: int, day: int | None = None) -> dict:
    return (
        sex_class_handle.get_temp_class(today if day is None else day, period)
        or {}
    )


def _patch_temp(period: int, day: int | None = None, **fields: object) -> dict:
    d = today if day is None else day
    key = sex_class_handle.get_class_key(d, period)
    return education.put_temp_class(key, {**_temp(period, d), **fields})


check(
    "跨过开始前 30 分钟 → 第二次提醒",
    len(text_list) == 1 and _temp(4)["notified"][1],
)
check(
    "再结算一次不重发",
    sex_class_handle.check_and_send_notify(
        period_time(4) - datetime.timedelta(minutes=20), period_time(4)
    )
    == [],
)
check(
    "没在上课时不发第三次",
    sex_class_handle.check_and_send_notify(
        period_time(4) + datetime.timedelta(minutes=40),
        period_time(4) + datetime.timedelta(minutes=50),
    )
    == [],
)
_patch_temp(4, running=True)
check(
    "上课中跨过下课时刻 → 第三次提醒",
    len(
        sex_class_handle.check_and_send_notify(
            period_time(4) + datetime.timedelta(minutes=40),
            period_time(4) + datetime.timedelta(minutes=50),
        )
    )
    == 1
    and _temp(4)["notified"][2],
)
_patch_temp(4, running=False)
set_time(period_time(0))
first_text = sex_class_handle.get_today_class_notify_text()
check(
    "起床提醒含教室与科目",
    ROOM_P in first_text
    and game_config.config_ability[70].name in first_text
    and _temp(4)["notified"][0],
)
check("起床提醒只发一次", sex_class_handle.get_today_class_notify_text() == "")

section("开课与下课")
set_time(period_time(4))
assert growth.has(student_a.cid)
student_a_growth = child_growth(student_a.cid)
student_a_growth.attend_class_count = 0
now_class = sex_class_handle.start_sex_class(70)
check(
    "预约的那节：复用条目、标记预约",
    now_class == _temp(4) and now_class["running"] and now_class["reserved"],
)
check(
    "到场学生记出勤",
    student_a_growth.attend_class_count == 1
    and child_growth(202).attend_class_count == 1,
)
check("当前主修科目 70", sex_class_handle.get_now_class_ability() == 70)
check(
    "主修经验 id = 指技的升级需求经验",
    sex_class_handle.get_now_bonus_exp_id()
    == growth_handle.get_subject_exp_id(70)
    > 0,
)
check(
    "玩家在课中",
    sex_class_handle.judge_in_running_class(0)
    and sex_class_handle.judge_in_running_class(201),
)
move_to(202, SCENE_DORM)
check(
    "不在那间教室的学生不算在课中",
    not sex_class_handle.judge_in_running_class(202),
)
move_to(202, classroom_path(ROOM_P))
set_time(period_time(4) + datetime.timedelta(minutes=10))
check("下课类型：提前", sex_class_handle.judge_end_type() == 0)
set_time(period_time(4) + datetime.timedelta(minutes=43))
check("下课类型：按时", sex_class_handle.judge_end_type() == 1)
set_time(period_time(4) + datetime.timedelta(minutes=70))
check("下课类型：拖堂", sex_class_handle.judge_end_type() == 2)
ca.ability(pl)[70] = 6
bonus = sex_class_handle.get_subject_bonus(201)
check(
    "主修加成 = 2.0 × 速度(1+0.25×6) × 教育区",
    abs(
        bonus
        - education_constant.SUBJECT_BONUS
        * 2.5
        * growth_handle.get_education_zone_adjust()
    )
    < 1e-9,
    bonus,
)
check("不存在的学生加成 1.0", sex_class_handle.get_subject_bonus(999) == 1.0)
sex_class_handle.end_sex_class()
check(
    "下课后没有运行中的课、类型 -1、加成 1.0",
    sex_class_handle.get_running_class() is None
    and sex_class_handle.judge_end_type() == -1
    and sex_class_handle.get_subject_bonus(201) == 1.0,
)
# 预约的课下课后条目留到跨天，但打上已下课标记，覆盖层不再认它（第五轮）
set_time(period_time(4) + datetime.timedelta(minutes=20))
check("预约下课", _temp(4).get("ended") is True)
check("已下课非有效", sex_class_handle.get_active_temp_class(today, 4) is None)
check(
    "已下课交还课表", schedule_handle.get_class_cell(ROOM_P, weekday, 4) is None
)
check(
    "已下课无教师反查", schedule_handle.get_teacher_cell(0, weekday, 4) is None
)
sex_class_handle.end_sex_class()
check("重复下课不报错", True)
education.clear_temp_classes()
set_time(period_time(5))
new_class = sex_class_handle.start_sex_class(71)
check(
    "当场开课：新建条目、非预约、运行中",
    new_class["reserved"] is False
    and new_class["running"]
    and new_class["classroom"] == ROOM_P
    and new_class["ability_id"] == 71,
)

section("旁观")
kernel_data.set_needs(student_b.cid, hit=10)
check(
    "体力不足只旁观",
    sex_class_handle.judge_hp_low_only_watch(202)
    and not sex_class_handle.judge_hp_low_only_watch(201)
    and not sex_class_handle.judge_hp_low_only_watch(999),
)
kernel_data.set_needs(student_b.cid, hit=100)
kernel_data.set_world(modes.set_sex_class, False)
check("没开课堂模式没有旁观者", sex_class_handle.get_watcher_list() == [])
kernel_data.set_world(modes.set_sex_class, True)
kernel_data.set_world(modes.set_group_sex, True)
kernel_data.put(flags.set, student_a.cid, is_h=True)
kernel_data.put(flags.set, student_b.cid, is_h=True)
watcher_list = sex_class_handle.get_watcher_list()
check(
    "在场、H 中、不在模板里的都是旁观者",
    sorted(watcher_list) == [201, 202],
    watcher_list,
)
kernel_data.put(flags.set, student_b.cid, is_h=False)
check("不在 H 状态的不算旁观", sex_class_handle.get_watcher_list() == [201])
kernel_data.put(flags.set, student_b.cid, is_h=True)
exp_id = sex_class_handle.get_now_bonus_exp_id()
change = game_type.CharacterStatusChange()
change.target_change.setdefault(202, game_type.TargetChange())
change.target_change[202].experience[exp_id] = 40
exp_before = student_a_exp.get(exp_id, 0)
shy_before = status.of(student_a.cid).get(16, 0)
_orig_random = random.random
random.random = lambda: 0.99
sex_class_handle.settle_watcher(5, change)
random.random = _orig_random
check("旁观者拿 25% 主修经验", student_a_exp.get(exp_id, 0) - exp_before == 10)
check("旁观者羞耻上升", status.of(student_a.cid).get(16, 0) > shy_before)
check(
    "变更记录里也记了旁观者",
    change.target_change[201].experience.get(exp_id, 0) == 10,
)
exp_before = student_a_exp.get(exp_id, 0)
sex_class_handle.settle_watcher(0, change)
check("add_time=0 不结算", student_a_exp.get(exp_id, 0) == exp_before)

section("当场开的课下课即删（第五轮）")
impromptu_key = sex_class_handle.get_running_class_key()
check(
    "当场开的课正在进行",
    impromptu_key == sex_class_handle.get_class_key(today, 5),
)
sex_class_handle.end_sex_class()
check(
    "当场开的课下课后条目直接删掉",
    impromptu_key not in education.temp_classes(),
)
kernel_data.set_world(modes.set_sex_class, False)
kernel_data.set_world(modes.set_group_sex, False)

section("出勤只给女儿与学生岗记（第五轮）")
adult_attend = make_character(302, "路过的成年干员", 21)
sex_class_handle.settle_attend(302)
check(
    "非学生的成年干员：不记、不惰性创建养成数据",
    growth.of(adult_attend.cid) is None,
)
adult_student = make_character(303, "成年学生", 152)
sex_class_handle.settle_attend(303)
check(
    "成年学生：记一节",
    (_asg := growth.of(adult_student.cid)) is not None
    and _asg.attend_class_count == 1,
)

section("Plan 26 §3.5：提前几分钟开讲预约的课，开的就是预约那节")
education.clear_temp_classes()
kernel_data.set_world(modes.set_sex_class, False)
kernel_data.set_world(modes.set_group_sex, False)
newbie = make_character(
    204, "没修过性技课的必修生", 152, daughter=True, stage=103, mother_id=102
)
move_to(0, classroom_path(ROOM_P))
move_to(204, classroom_path(ROOM_P))
reserved = sex_class_handle.set_temp_class(
    today, 6, ROOM_P, 72, must_attend=[204]
)
early = period_time(6) - datetime.timedelta(minutes=5)
set_time(early)
key_6 = sex_class_handle.get_class_key(today, 6)
check(
    "找得到这间教室半小时内开讲的预约",
    sex_class_handle.find_reserved_class(ROOM_P, early) == (key_6, reserved),
)
check(
    "别的教室、开课前 45 分钟都找不到",
    sex_class_handle.find_reserved_class(_("大礼堂"), early) == ("", None)
    and sex_class_handle.find_reserved_class(
        ROOM_P, period_time(6) - datetime.timedelta(minutes=45)
    )
    == ("", None),
)
check(
    "必修名单：不给教室按当前节次取（取不到），给了教室按这间教室的预约取",
    sex_class_handle.get_must_attend_set() == set()
    and sex_class_handle.get_must_attend_set(ROOM_P) == {204},
)
check(
    "开课前的场景学生名单含没修过性技课的必修生",
    204 in sex_class_handle.get_scene_student_list(),
    sex_class_handle.get_scene_student_list(),
)
check(
    "开课指令预读得到预约",
    sex_class_handle.find_class_to_start(ROOM_P, early)[1] == reserved,
)
now_class = sex_class_handle.start_sex_class(72)
check(
    "复用预约条目：运行中、标记预约、键还是第 6 节",
    now_class == _temp(6)
    and now_class["running"]
    and now_class["reserved"]
    and sex_class_handle.get_running_class_key() == key_6,
)
check("没有另开一节当场课", list(education.temp_classes()) == [key_6])
set_time(period_time(6) + datetime.timedelta(minutes=45))
check(
    "按预约的节次判档：到点下课是「按时」",
    sex_class_handle.judge_end_type() == 1,
)
sex_class_handle.end_sex_class()
check(
    "下课后预约那条打上 ended、不再覆盖",
    _temp(6).get("ended") is True
    and sex_class_handle.get_active_temp_class(today, 6) is None,
)
set_time(period_time(6) + datetime.timedelta(minutes=20))
check(
    "已下课的预约不再被当成等着开讲的",
    sex_class_handle.find_reserved_class(ROOM_P, game_time.now()) == ("", None),
)
check(
    "同一节下课后在同一间教室重开：沿用那条",
    sex_class_handle.find_class_to_start(ROOM_P, game_time.now())[1]
    == _temp(6),
)
reopen = sex_class_handle.start_sex_class(72, [])
check(
    "重开：清掉已下课标记、仍是预约",
    reopen == _temp(6) and reopen["ended"] is False and reopen["running"],
)
sex_class_handle.end_sex_class()

section("Plan 26 L4：别的教室当场开课，把占着键的预约挪过来而不是覆盖")
moved = sex_class_handle.set_temp_class(today, 7, ROOM_P, 73, must_attend=[204])
set_time(period_time(7) + datetime.timedelta(minutes=5))
move_to(0, classroom_path(_("大礼堂")))
started = sex_class_handle.start_sex_class(71, [])
check(
    "挪用：还是那一条，教室改成大礼堂，必修名单保留、算预约",
    started == _temp(7)
    and started["classroom"] == _("大礼堂")
    and started["must_attend"] == [204]
    and started["reserved"],
    started,
)
sex_class_handle.end_sex_class()
move_to(0, classroom_path(ROOM_P))

section("Plan 26 §3.10：课堂 H 只收学生岗")
chara_life.work_type.set(student_b.cid, 51)
check(
    "改了岗的女儿：点名必修也不能参加",
    not sex_class_handle.judge_can_join_sex_class(202, check_course=False),
)
check(
    "改了岗的女儿不进场景学生名单",
    202 not in sex_class_handle.get_scene_student_list(),
)
chara_life.work_type.set(student_b.cid, 152)
check("改回学生岗恢复", sex_class_handle.judge_can_join_sex_class(202))

section("Plan 26 L8：开课前半小时的提醒写实")
education.clear_temp_classes()
sex_class_handle.set_temp_class(today, 8, ROOM_P, 70)
text_list = sex_class_handle.check_and_send_notify(
    period_time(8) - datetime.timedelta(minutes=40),
    period_time(8) - datetime.timedelta(minutes=25),
)
check(
    "提醒写的是开课前 10 分钟动身，不再说「已经在往教室走了」",
    len(text_list) == 1
    and "10" in text_list[0]
    and "已经在往教室走了" not in text_list[0],
    text_list,
)
education.clear_temp_classes()

section(
    "Plan 27 L2（按设计保留）：同一节里下课后再开一次实操课，到场学生再记一节出勤"
)
kernel_data.set_world(modes.set_sex_class, False)
kernel_data.set_world(modes.set_group_sex, False)
move_to(0, classroom_path(ROOM_P))
move_to(201, classroom_path(ROOM_P))
kernel_data.put(flags.set, student_a.cid, is_h=False)
set_time(period_time(1) + datetime.timedelta(minutes=5))
_attend = child_growth(201).attend_class_count
sex_class_handle.start_sex_class(70)
sex_class_handle.end_sex_class()
_first = child_growth(201).attend_class_count
kernel_data.put(flags.set, student_a.cid, is_h=False)
set_time(period_time(1) + datetime.timedelta(minutes=15))
sex_class_handle.start_sex_class(70)
sex_class_handle.end_sex_class()
check(
    "每次开课单独记一次（用户拍板，复查时别当成重复计数去重）：开课 +1，同一节下课后再开又 +1",
    _first == _attend + 1
    and child_growth(201).attend_class_count == _attend + 2,
    (_attend, _first, child_growth(201).attend_class_count),
)
kernel_data.put(flags.set, student_a.cid, is_h=False)
education.clear_temp_classes()

section("Plan 30 §3.4：这一节已记缺课的学生，开课与 722 晚到都不记出勤")
kernel_data.set_world(modes.set_sex_class, False)
kernel_data.set_world(modes.set_group_sex, False)
move_to(0, classroom_path(ROOM_P))
move_to(201, classroom_path(ROOM_P))
set_time(period_time(2) + datetime.timedelta(minutes=5))
child_growth(201).last_absent_period = [
    game_time.now().toordinal(),
    2,
]
_attend = child_growth(201).attend_class_count
sex_class_handle.start_sex_class(70, [201])
check(
    "开课时到场的学生这一节已缺课：不记出勤（开课传此刻 game_time.now()）",
    child_growth(201).attend_class_count == _attend,
)
sex_class_handle.end_sex_class()
kernel_data.put(flags.set, student_a.cid, is_h=False)
sex_class_handle.settle_attend(201)
check(
    "722 晚到（取学生的行为开始时刻）：同一节同样不记",
    child_growth(201).attend_class_count == _attend,
)
set_time(period_time(3) + datetime.timedelta(minutes=5))
sex_class_handle.settle_attend(201)
check(
    "下一节没缺课：照常记",
    child_growth(201).attend_class_count == _attend + 1,
)
child_growth(201).last_absent_period = []
education.clear_temp_classes()

section(
    "Plan 31 M1：实操课门槛的实行值只判不扣——门槛与前提求值多次，不扣理智、不累加今日消耗、不解除催眠"
)

kernel_data.set_world(modes.set_sex_class, False)
kernel_data.set_world(modes.set_group_sex, False)
set_time(period_time(3))
_hypno_day = (game_time.now().weekday() + 3) % 7
hypno = make_character(305, "心控中的成年学生", 152)
ca.talent(hypno)[72] = 1  # 被深层催眠
kernel_data.put(flags.set, hypno.cid, unconscious_h=7)
schedule_handle.set_class_cell(ROOM_P, _hypno_day, 8, 74, -1)
schedule_handle.set_selected_course(
    305, _hypno_day, 8, education_constant.COURSE_TYPE_PRACTICE, ROOM_P
)
move_to(0, classroom_path(ROOM_P))
move_to(305, classroom_path(ROOM_P))
kernel_data.set_needs(pl.cid, sanity_max=2000, sanity=2000)
kernel_data.put(player_ability.set, pl.cid, today_sanity_point_cost=0)
ca.talent(pl)[332] = 0
check(
    "M1 前置：成年非女儿的学生岗、排过性技教室课、好感为 0；玩家没有中级催眠时实行值不足，进不了课堂",
    relations.father_id(hypno.cid) != 0
    and sex_class_handle.judge_has_sex_skill_course(305)
    and relations.favorability(hypno.cid).get(0, 0) == 0
    and not sex_class_handle.judge_can_join_sex_class(305),
)
# 中级催眠：对深层催眠的目标，实行值不足的部分由理智折算补上
ca.talent(pl)[332] = 1
_m1_list = []
for _index in range(4):
    _m1_list.append(sex_class_handle.judge_can_join_sex_class(305))
    _m1_list.append(
        bool(handle_premise.handle_premise("scene_have_sex_class_student", 0))
    )
check(
    "M1 理智够时门槛照样成立（催眠补正照算）：门槛与指令 5209 的前提 scene_have_sex_class_student 各求值 4 次都成立",
    all(_m1_list),
    _m1_list,
)
_m1_sanity = kernel_data.needs_of(pl.cid)["sanity"]
check(
    "M1 求值 8 次后玩家理智不变、今日消耗不累加（此前每求值一次扣一回）",
    _m1_sanity == 2000
    and player_ability.get(pl.cid, "today_sanity_point_cost") == 0,
    (_m1_sanity, player_ability.get(pl.cid, "today_sanity_point_cost")),
)
check(
    "M1 她的心控没被动过",
    flags.get(hypno.cid, "unconscious_h") == 7,
    flags.get(hypno.cid, "unconscious_h"),
)
kernel_data.set_world(modes.set_sex_class, True)
kernel_data.set_world(modes.set_group_sex, True)
_m1_running = sex_class_handle.set_temp_class(
    today, 3, ROOM_P, 74, running=True
)
kernel_data.put(flags.set, hypno.cid, is_h=True)
_m1_in_class = [
    bool(handle_premise.handle_premise("self_in_sex_class", 305))
    for _index in range(3)
]
kernel_data.put(flags.set, hypno.cid, is_h=False)
_m1_joinable = [
    class_ai.judge_pending_class_joinable(305, _m1_running, ROOM_P)
    for _index in range(3)
]
check(
    (
        "M1 口上前提 self_in_sex_class 与她自己决策时的入课判定（judge_pending_class_joinable）各求值 3 次都成立，"
        "理智仍不变"
    ),
    all(_m1_in_class)
    and all(_m1_joinable)
    and kernel_data.needs_of(pl.cid)["sanity"] == 2000
    and player_ability.get(pl.cid, "today_sanity_point_cost") == 0,
    (
        _m1_in_class,
        _m1_joinable,
        kernel_data.needs_of(pl.cid)["sanity"],
        player_ability.get(pl.cid, "today_sanity_point_cost"),
    ),
)
kernel_data.set_world(modes.set_sex_class, False)
kernel_data.set_world(modes.set_group_sex, False)
education.clear_temp_classes()
kernel_data.set_needs(pl.cid, sanity=0)
check(
    "M1 理智为 0：没有补正，门槛不成立",
    not sex_class_handle.judge_can_join_sex_class(305),
)
handle_premise.handle_premise("scene_have_sex_class_student", 0)
check(
    "M1 理智为 0 时判门槛、求值前提都不解除她的催眠（此前心控被清零），今日消耗仍为 0",
    flags.get(hypno.cid, "unconscious_h") == 7
    and kernel_data.needs_of(pl.cid)["sanity"] == 0
    and player_ability.get(pl.cid, "today_sanity_point_cost") == 0,
    (
        flags.get(hypno.cid, "unconscious_h"),
        kernel_data.needs_of(pl.cid)["sanity"],
        player_ability.get(pl.cid, "today_sanity_point_cost"),
    ),
)
kernel_data.set_needs(pl.cid, sanity=2000)
_m1_default = kernel_data.written(
    instuct_judege.calculation_instuct_judege, 0, 305, _("H模式"), True
)
_m1_cost = 2000 - kernel_data.needs_of(pl.cid)["sanity"]
check(
    "M1 其它系统的缺省调用（settle_hypnosis=True）照旧：补正后通过、扣理智、累加今日消耗",
    _m1_default[0] == 1
    and _m1_cost > 0
    and player_ability.get(pl.cid, "today_sanity_point_cost") == _m1_cost,
    (
        _m1_default,
        _m1_cost,
        player_ability.get(pl.cid, "today_sanity_point_cost"),
    ),
)
kernel_data.set_needs(pl.cid, sanity=0)
kernel_data.written(
    instuct_judege.calculation_instuct_judege, 0, 305, _("H模式"), True
)
check(
    "M1 缺省调用在理智不足时照旧解除催眠",
    flags.get(hypno.cid, "unconscious_h") == 0,
    flags.get(hypno.cid, "unconscious_h"),
)
ca.talent(pl)[332] = 0
kernel_data.set_needs(pl.cid, sanity=0, sanity_max=0)
kernel_data.put(player_ability.set, pl.cid, today_sanity_point_cost=0)
schedule_handle.clear_class_cell(ROOM_P, _hypno_day, 8)
remove_character(305)

section(
    "Plan 31 L3：提前几分钟开讲预约的实操课，按那一节判「本节已缺课」；L12：记出勤时累计实操课次数"
)
education.clear_temp_classes()
kernel_data.set_world(modes.set_sex_class, False)
kernel_data.set_world(modes.set_group_sex, False)
move_to(0, classroom_path(ROOM_P))
move_to(201, classroom_path(ROOM_P))
kernel_data.put(flags.set, student_a.cid, is_h=False)
_g201 = child_growth(201)
_l3_early = period_time(5) - datetime.timedelta(minutes=5)
check(
    "L3 前置：14:40 开讲还在上一节（节次 4），预约的是 14:45 开始的节次 5",
    game_time.get_class_period_by_time(_l3_early) == 4,
)
sex_class_handle.set_temp_class(today, 5, ROOM_P, 70)
set_time(_l3_early)
_g201.last_absent_period = [today, 4]
_attend, _sex = _g201.attend_class_count, _g201.sex_class_count
sex_class_handle.start_sex_class(70, [201])
check(
    "L3 提前 5 分钟开讲、上一节缺过课：出勤 +1（此前按开讲时刻判成本节已缺课，出勤记不上）",
    _g201.attend_class_count == _attend + 1,
    (_attend, _g201.attend_class_count),
)
check(
    "L12 记出勤的同时累计实操课次数 +1，养成数值 25 读得到",
    _g201.sex_class_count == _sex + 1
    and growth_handle.get_growth_value(
        201, education_constant.GROWTH_VALUE_SEX_CLASS
    )
    == _sex + 1,
    (_sex, _g201.sex_class_count),
)
_g201.last_absent_period = [today, 5]
_attend, _sex = _g201.attend_class_count, _g201.sex_class_count
sex_class_handle.settle_attend(201)
check(
    "L3 722 晚到（取行为开始时刻 14:40）同样按那一节判：这一节已缺课，出勤与实操课次数都不加",
    _g201.attend_class_count == _attend and _g201.sex_class_count == _sex,
    (_attend, _g201.attend_class_count, _sex, _g201.sex_class_count),
)
_g201.last_absent_period = [today, 4]
sex_class_handle.settle_attend(201)
check(
    "L3 722 晚到、只有上一节缺过课：出勤与实操课次数照记",
    _g201.attend_class_count == _attend + 1
    and _g201.sex_class_count == _sex + 1,
    (_attend, _g201.attend_class_count, _sex, _g201.sex_class_count),
)
sex_class_handle.end_sex_class()
education.clear_temp_classes()
sex_class_handle.set_temp_class(today, 5, ROOM_P, 70)
set_time(_l3_early)
_g201.last_absent_period = [today, 5]
_attend, _sex = _g201.attend_class_count, _g201.sex_class_count
sex_class_handle.start_sex_class(70, [201])
check(
    "L3 提前开讲、这一节本身已记缺课：开课时出勤与实操课次数都不加",
    _g201.attend_class_count == _attend and _g201.sex_class_count == _sex,
    (_attend, _g201.attend_class_count, _sex, _g201.sex_class_count),
)
sex_class_handle.end_sex_class()
education.clear_temp_classes()
set_time(
    datetime.datetime(_l3_early.year, _l3_early.month, _l3_early.day, 12, 30)
)
_g201.last_absent_period = [today, 3]
_attend, _sex = _g201.attend_class_count, _g201.sex_class_count
sex_class_handle.start_sex_class(70, [201])
check(
    "L3 节次外的当场课（节次 -1）没有开始时刻，照旧按参照时刻判：不报错，出勤与实操课次数照记",
    sex_class_handle.get_running_class_key()
    == sex_class_handle.get_class_key(today, -1)
    and _g201.attend_class_count == _attend + 1
    and _g201.sex_class_count == _sex + 1,
    (
        sex_class_handle.get_running_class_key(),
        _attend,
        _g201.attend_class_count,
    ),
)
sex_class_handle.end_sex_class()
_g201.last_absent_period = []
education.clear_temp_classes()

section("Plan 32 H1：课堂 H 以别的方式结束（玩家已不在 H）时一并下课")

EFFECT_DATA = constant.settle_behavior_effect_data
BEHAVIOR_EFFECT = game_config.config_behavior_effect_data


def run_effect_list(effect_id_list: list) -> None:
    """
    以玩家为结算主体、按顺序结算一串效果（结算时长 5 分钟）
    Keyword arguments:
    effect_id_list -- 效果id列表
    Return arguments:
    无
    """
    with kernel_data.writing():
        for effect_id in effect_id_list:
            EFFECT_DATA[effect_id](
                0, 5, game_type.CharacterStatusChange(), game_time.now()
            )


def judge_instruct_show(instruct_id: str) -> bool:
    """
    按 InstructConfig.csv 的原始前提串逐个求值（以玩家为主体），判断某条指令此刻显示与否
    Keyword arguments:
    instruct_id -- 指令id（InstructConfig 第二列）
    Return arguments:
    bool -- 前提全部成立为 True
    """
    instruct_config = game_config.config_instruct[
        game_config.config_instruct_by_id[instruct_id]
    ]
    return all(
        handle_premise.handle_premise(
            getattr(constant_promise.Premise, name), 0
        )
        for name in instruct_config.premise_set.split("|")
        if name
    )


def open_class_for_h1(period: int, reserved: bool = True) -> dict:
    """
    在实践教室一开一节实操课并进入课堂 H：照开课指令的顺序先 start_sex_class 记出勤，再结算效果 10014 把学生拉进 H；
    玩家自己进 H 是开课效果串里 462 的事，这里直接置位
    Keyword arguments:
    period -- 今天的第几节
    reserved -- 是否先预约再开（False 为当场开课）
    Return arguments:
    dict -- 本节课的数据
    """
    education.clear_temp_classes()
    kernel_data.set_world(modes.set_sex_class, False)
    kernel_data.set_world(modes.set_group_sex, False)
    for chara_id in (0, 201, 202):
        move_to(chara_id, classroom_path(ROOM_P))
        kernel_data.put(flags.set, chara_id, is_h=False)
    set_time(period_time(period) + datetime.timedelta(minutes=5))
    if reserved:
        sex_class_handle.set_temp_class(today, period, ROOM_P, 70)
    now_class = sex_class_handle.start_sex_class(70, [201, 202])
    kernel_data.put(flags.set, pl.cid, is_h=True)
    kernel_data.put(activity.set_target, pl.cid, 201)
    run_effect_list([10014])
    return now_class


check(
    "H1 前置：结束群交（371）与玩家体力归零（373）的效果串都以 407 清全场 H 状态、10011 关群交，都没有 10015",
    all(
        407 in BEHAVIOR_EFFECT.get(behavior_id, [])
        and 10011 in BEHAVIOR_EFFECT.get(behavior_id, [])
        and 10015 not in BEHAVIOR_EFFECT.get(behavior_id, [])
        for behavior_id in ("group_sex_end", "group_sex_pl_hp_0_end")
    ),
)
check(
    "H1 前置：转单人 H（375）只关群交、不清 H 状态；结束 H（362）以 404 清双方 H 状态；两条都没有 10015",
    10011 in BEHAVIOR_EFFECT.get("group_sex_to_h", [])
    and 407 not in BEHAVIOR_EFFECT.get("group_sex_to_h", [])
    and 404 not in BEHAVIOR_EFFECT.get("group_sex_to_h", [])
    and 10015 not in BEHAVIOR_EFFECT.get("group_sex_to_h", [])
    and 404 in BEHAVIOR_EFFECT.get("end_h", [])
    and 10015 not in BEHAVIOR_EFFECT.get("end_h", []),
)
# 结束群交（371）：预约的课
_h1_class = open_class_for_h1(1)
check(
    "H1 前置：开课后课堂模式与群交模式都开着、玩家与两名学生都在 H 中、那节课 running",
    modes.sex_class()
    and modes.group_sex()
    and flags.get(pl.cid, "is_h")
    and flags.get(student_a.cid, "is_h")
    and flags.get(student_b.cid, "is_h")
    and _h1_class["running"],
)
check(
    (
        "H1 课上「结束群交」6008 不再显示（前提加了 SEX_CLASS_MODE_OFF，此前与 6021 并排显示），「结束性技实操课」6021 "
        "照常显示"
    ),
    not judge_instruct_show("group_sex_end")
    and judge_instruct_show("end_sex_class"),
)
run_effect_list([407, 10011])
check(
    (
        "H1 结束群交（371 效果串里的 407 / 10011）之后：群交模式已关、玩家与学生都已不在 H，"
        "课堂模式此刻还开着（效果串里没有 10015）"
    ),
    not modes.group_sex()
    and not flags.get(pl.cid, "is_h")
    and not flags.get(student_a.cid, "is_h")
    and modes.sex_class(),
)
play()
check(
    "H1 下一步的 OrphanClass 事件里下课：课堂模式已关、那节课不再 running（预约的打上 ended）",
    not modes.sex_class()
    and sex_class_handle.get_running_class() is None
    and _temp(1).get("ended") is True,
    _temp(1),
)
check(
    "H1 SEX_CLASS_MODE_OFF",
    bool(
        handle_premise.handle_premise(
            constant_promise.Premise.SEX_CLASS_MODE_OFF, 0
        )
    ),
)
check("H1 主修加成失效", sex_class_handle.get_now_bonus_exp_id() == 0)
check(
    "H1 常规课不拉进H",
    class_ai.get_attend_or_join_stage(201, {"classroom": ROOM_P})
    == education_constant.COURSE_STAGE_ATTEND,
)
kernel_data.set_world(modes.set_group_sex, True)
kernel_data.put(flags.set, pl.cid, is_h=True)
check(
    "H1 对照：普通群交（课堂模式没开）照常显示「结束群交」、不显示「结束性技实操课」",
    judge_instruct_show("group_sex_end")
    and not judge_instruct_show("end_sex_class"),
)
kernel_data.set_world(modes.set_group_sex, False)
kernel_data.put(flags.set, pl.cid, is_h=False)
# 玩家体力归零（373，效果串与 371 相同）：当场开的课
_h1_class = open_class_for_h1(2, reserved=False)
_h1_key = sex_class_handle.get_running_class_key()
check(
    "H1 前置：当场开的课正在进行",
    _h1_key == sex_class_handle.get_class_key(today, 2)
    and _h1_class["reserved"] is False,
)
run_effect_list([407, 10011])
play()
check(
    "H1 玩家体力归零（373）收尾后同样下课：课堂模式已关、当场开的课条目直接删掉",
    not modes.sex_class() and _h1_key not in education.temp_classes(),
)
# 只剩一名学生、转单人 H（375）后再结束 H（362）
_h1_class = open_class_for_h1(3)
kernel_data.put(flags.set, student_b.cid, is_h=False)
run_effect_list([10011])
play()
check(
    "H1 转单人 H（375 只有 10011）后玩家仍在 H：课照上（课堂模式开着、那节课仍 running）",
    modes.sex_class() and _temp(3).get("running") and flags.get(pl.cid, "is_h"),
)
check(
    "H1 课还在上时 settle_orphan_class 什么都不做、返回 False",
    sex_class_handle.settle_orphan_class() is False
    and modes.sex_class()
    and _temp(3).get("running"),
)
kernel_data.put(activity.set_target, pl.cid, 201)
run_effect_list([404])
play()
check(
    "H1 这场单人 H 结束（362 的 404 清双方 H 状态）后下课",
    not modes.sex_class()
    and sex_class_handle.get_running_class() is None
    and _temp(3).get("ended") is True
    and not flags.get(pl.cid, "is_h")
    and not flags.get(student_a.cid, "is_h"),
)
_h1_class = open_class_for_h1(5)
kernel_data.put(
    flags.set, student_b.cid, is_h=False
)  # 女儿B 已先力竭退出，只剩女儿A
sync()
kernel_data.written(handle_npc_ai.commit_group_sex_tired_exit, 201)
play(keep_queue=True)
check(
    (
        "H1 复审补：最后一名学生力竭退出（commit_group_sex_tired_exit 的真实调用链）→ 玩家结束群交 → "
        "这个行动收尾时下课：课堂模式已关、那节课打上 ended、学生已不在 H"
    ),
    activity.last_behaviors(pl.cid)[-1:] == [constant.Behavior.GROUP_SEX_END]
    and not modes.sex_class()
    and sex_class_handle.get_running_class() is None
    and _temp(5).get("ended") is True
    and not flags.get(student_a.cid, "is_h"),
    (activity.last_behaviors(pl.cid)[-1:], modes.sex_class(), _temp(5)),
)
# 旧档里已经留下的幽灵课堂：课堂模式开着、那节课 running，玩家早已不在 H
education.clear_temp_classes()
kernel_data.set_world(modes.set_group_sex, False)
kernel_data.put(flags.set, pl.cid, is_h=False)
sex_class_handle.set_temp_class(today, 4, ROOM_P, 70, running=True)
_patch_temp(4, reserved=True)
kernel_data.set_world(modes.set_sex_class, True)
play()
check(
    "H1 旧档里的幽灵课堂（课堂模式开着、玩家不在 H）：下一步的 OrphanClass 事件里收掉",
    not modes.sex_class()
    and _temp(4).get("running") is False
    and _temp(4).get("ended") is True,
    _temp(4),
)
check(
    "H1 settle_orphan_class 在课堂模式没开时什么都不做、返回 False",
    sex_class_handle.settle_orphan_class() is False,
)
education.clear_temp_classes()
sex_class_handle.set_temp_class(today - 1, 3, ROOM_P, 70, running=True)
_patch_temp(3, today - 1, reserved=True)
kernel_data.set_world(modes.set_sex_class, True)
check(
    "H1 跨天清理：昨天留下的幽灵课堂按过期清掉、课堂模式一并关掉（此前跳过 running 的那条，永远不清）",
    kernel_data.written(sex_class_handle.clean_expired_temp_class) == 1
    and sex_class_handle.get_temp_class(today - 1, 3) is None
    and not modes.sex_class(),
)
sex_class_handle.set_temp_class(today - 1, 3, ROOM_P, 70, running=True)
kernel_data.set_world(modes.set_sex_class, False)
check(
    "H1 跨天清理：课堂模式没开、条目却还挂着 running 的，照样按过期清掉",
    sex_class_handle.clean_expired_temp_class() == 1
    and not education.temp_classes(),
)
education.clear_temp_classes()
kernel_data.set_world(modes.set_sex_class, False)
kernel_data.set_world(modes.set_group_sex, False)
for _cid in (0, 201, 202):
    kernel_data.put(flags.set, _cid, is_h=False)

section(
    "Plan 32 L7：实操课记出勤时一并写「这一节已结算」标记（同一节只落一种记录的另一个方向）"
)
move_to(0, classroom_path(ROOM_P))
move_to(201, classroom_path(ROOM_P))
_g201 = child_growth(201)
_g201.last_absent_period = []
_g201.last_attend_period = []
set_time(period_time(2) + datetime.timedelta(minutes=5))
_attend = _g201.attend_class_count
sex_class_handle.start_sex_class(70, [201])
check(
    "L7 开课记出勤时写下 last_attend_period（此前不写：本节内提前下课、体力落在 1~30% 的学生回到 AI 会再记一节缺课）",
    _g201.attend_class_count == _attend + 1
    and _g201.last_attend_period == [today, 2],
    _g201.last_attend_period,
)
check(
    "L7 同一节里常规课的学生侧结算（557 / 512 共用的 settle_student_class_gain）按去重不再结算",
    not growth_handle.settle_student_class_gain(
        201, -1, 45, education_constant.COURSE_TYPE_THEORY, 45
    ),
)
sex_class_handle.end_sex_class()
education.clear_temp_classes()
sex_class_handle.set_temp_class(today, 5, ROOM_P, 70)
set_time(period_time(5) - datetime.timedelta(minutes=5))
_g201.last_attend_period = []
sex_class_handle.start_sex_class(70, [201])
check(
    "L7 提前 5 分钟开讲预约的第 5 节：标记记在第 5 节（按 get_attend_judge_time 那一节），不记在开讲时刻所在的第 4 节",
    _g201.last_attend_period == [today, 5],
    _g201.last_attend_period,
)
sex_class_handle.end_sex_class()
education.clear_temp_classes()
set_time(DEFAULT_TIME.replace(hour=12, minute=30))
_g201.last_attend_period = [today, 3]
sex_class_handle.start_sex_class(70, [201])
check(
    "L7 节次外的当场课没有节次可记：标记不动",
    _g201.last_attend_period == [today, 3],
    _g201.last_attend_period,
)
sex_class_handle.end_sex_class()
education.clear_temp_classes()
set_time(period_time(6) + datetime.timedelta(minutes=5))
_g201.last_absent_period = [today, 6]
_g201.last_attend_period = []
_attend = _g201.attend_class_count
sex_class_handle.start_sex_class(70, [201])
check(
    "L7 这一节已记缺课（不记出勤）时也不写标记",
    _g201.attend_class_count == _attend and _g201.last_attend_period == [],
    _g201.last_attend_period,
)
sex_class_handle.end_sex_class()
_g201.last_absent_period = []
_g201.last_attend_period = []
_absent = _g201.absent_count
for _open_time, _period, _label in (
    (period_time(2) + datetime.timedelta(minutes=5), 2, "按时开讲"),
    (
        period_time(5) - datetime.timedelta(minutes=5),
        5,
        "提前 5 分钟开讲预约的第 5 节",
    ),
):
    education.clear_temp_classes()
    if _period == 5:
        sex_class_handle.set_temp_class(today, 5, ROOM_P, 70)
    set_time(_open_time)
    _g201.last_absent_period = []
    _g201.last_attend_period = []
    _attend, _absent = _g201.attend_class_count, _g201.absent_count
    sex_class_handle.start_sex_class(70, [201])
    sex_class_handle.end_sex_class()
    set_time(period_time(_period) + datetime.timedelta(minutes=20))
    _recorded = class_ai.settle_absent(201)
    check(
        f"L7 跨单元整链（{_label}）：开课记出勤、本节内下课，本节后来回到 AI 派 721（调 settle_absent）不再记缺课",
        _g201.attend_class_count == _attend + 1
        and not _recorded
        and _g201.absent_count == _absent
        and _g201.last_absent_period == [],
        (_g201.last_attend_period, _recorded, _g201.last_absent_period),
    )
set_time(period_time(6) + datetime.timedelta(minutes=20))
check(
    "L7 跨单元整链对照：下一节没记出勤，settle_absent 照常记缺课",
    class_ai.settle_absent(201) and _g201.absent_count == _absent + 1,
)
education.clear_temp_classes()
_g201.last_absent_period = []
_g201.last_attend_period = []

section(
    "Plan 32 L8：同一节下课后在同一间教室重开预约的课，开课前的必修名单与开课时沿用的条目同源"
)
move_to(0, classroom_path(ROOM_P))
move_to(204, classroom_path(ROOM_P))
kernel_data.put(flags.set, newbie.cid, is_h=False)
sex_class_handle.set_temp_class(today, 7, ROOM_P, 72, must_attend=[204])
set_time(period_time(7) + datetime.timedelta(minutes=5))
check(
    "L8 前置：第一次开课前，按教室取的必修名单与场景学生名单都含这名没修过性技课的必修生",
    sex_class_handle.get_must_attend_set(ROOM_P) == {204}
    and 204 in sex_class_handle.get_scene_student_list(),
)
sex_class_handle.start_sex_class(72, sex_class_handle.get_scene_student_list())
sex_class_handle.end_sex_class()
set_time(period_time(7) + datetime.timedelta(minutes=20))
check(
    "L8 前置：预约的第 7 节下课后打上 ended，find_reserved_class 不再认它，find_class_to_start 沿用它",
    _temp(7).get("ended") is True
    and sex_class_handle.find_reserved_class(ROOM_P, game_time.now())
    == ("", None)
    and sex_class_handle.find_class_to_start(ROOM_P, game_time.now())[1]
    == _temp(7),
)
check(
    "L8 同一节下课后：按教室取的必修名单沿用那条已下课的预约（此前走 find_reserved_class 取到空集）",
    sex_class_handle.get_must_attend_set(ROOM_P) == {204},
    sex_class_handle.get_must_attend_set(ROOM_P),
)
_l8_list = sex_class_handle.get_scene_student_list()
check(
    "L8 重开前的场景学生名单（开课前提与开课指令取的那份）仍含这名必修生",
    204 in _l8_list,
    _l8_list,
)
_g204 = child_growth(204)
_attend, _sex = _g204.attend_class_count, _g204.sex_class_count
sex_class_handle.start_sex_class(72, _l8_list)
check(
    "L8 重开时她照记出勤与实操课次数（此前开课前被排除、开课后又被 10014 按必修名单拉进课，两样都不记）",
    _g204.attend_class_count == _attend + 1
    and _g204.sex_class_count == _sex + 1,
    (_attend, _g204.attend_class_count, _sex, _g204.sex_class_count),
)
sex_class_handle.end_sex_class()
education.clear_temp_classes()

section(
    "Plan 32 L9：课堂成员按身份认——课中实行值跌破门槛的成年学生仍在旁观名单与在课前提里"
)
kernel_data.set_world(modes.set_sex_class, False)
kernel_data.set_world(modes.set_group_sex, False)
set_time(period_time(3))
_l9_day = (game_time.now().weekday() + 4) % 7
schedule_handle.set_class_cell(ROOM_P, _l9_day, 8, 74, -1)
schedule_handle.set_selected_course(
    303, _l9_day, 8, education_constant.COURSE_TYPE_PRACTICE, ROOM_P
)
for _cid in (0, 201, 202, 301, 303):
    move_to(_cid, classroom_path(ROOM_P))
    kernel_data.set_needs(_cid, hit=100)
ca.talent(pl)[332] = 0
check(
    "L9 前置：成年学生排过性技教室课，但 H 模式实行值不足（好感为 0、玩家没有催眠补正），此刻过不了入课门槛",
    sex_class_handle.judge_has_sex_skill_course(303)
    and not sex_class_handle.judge_can_join_sex_class(303),
)
kernel_data.set_world(modes.set_sex_class, True)
kernel_data.set_world(modes.set_group_sex, True)
sex_class_handle.set_temp_class(today, 3, ROOM_P, 74, running=True)
kernel_data.put(flags.set, pl.cid, is_h=True)
kernel_data.put(flags.set, adult_student.cid, is_h=True)
kernel_data.put(flags.set, student_a.cid, is_h=True)
kernel_data.put(flags.set, adult.cid, is_h=True)
kernel_data.put(flags.set, student_b.cid, is_h=False)  # 在场但没进课堂 H 的学生
_l9_members = sex_class_handle.get_class_member_list()
check(
    "L9 课堂成员：已在 H 中的成年学生与女儿在；非学生岗的成年干员、没进 H 的学生、玩家自己都不在",
    303 in _l9_members
    and 201 in _l9_members
    and 301 not in _l9_members
    and 202 not in _l9_members
    and 0 not in _l9_members,
    _l9_members,
)
check(
    "L9 她仍在旁观名单里（此前按门槛重算，跌破门槛就拿不到观摩收益）",
    303 in sex_class_handle.get_watcher_list(),
    sex_class_handle.get_watcher_list(),
)
check(
    "L9 在课前提 self_in_sex_class 对她成立、对与课无关的成年干员不成立",
    bool(handle_premise.handle_premise("self_in_sex_class", 303))
    and not handle_premise.handle_premise("self_in_sex_class", 301),
)
# 课堂 H 中玩家开时停（U1 单元复审补）：成员名单按身份认，旁观名单另判状态那一层（judge_sex_class_state_ok）。
kernel_data.set_world(modes.set_time_stop, True)
check(
    (
        "L9 复审补：时停中（全体 NPC 判意识不清）旁观名单为空：被冻结的学生不拿观摩收益、不派旁观口上（L9 "
        "按身份认之后此前照拿）"
    ),
    sex_class_handle.get_watcher_list() == [],
    sex_class_handle.get_watcher_list(),
)
check(
    "L9 复审补：时停中课堂成员名单照旧按身份认（群交模板选人、在课前提不受影响）",
    303 in sex_class_handle.get_class_member_list(),
    sex_class_handle.get_class_member_list(),
)
kernel_data.set_world(modes.set_time_stop, False)
check(
    "L9 复审补：关掉时停后旁观名单恢复",
    303 in sex_class_handle.get_watcher_list(),
    sex_class_handle.get_watcher_list(),
)

section("Plan 32 L11：课堂模式下群交模板的选人只列课堂成员")
from Script.System.Sex_System import group_sex_panel  # noqa: E402

drawn_text.clear()
group_sex_panel.Edit_Group_Sex_Temple_Panel(190).show_target_chara_list(
    "A", "mouth"
)
_l11_text = list(drawn_text)
check(
    (
        "L11 课堂模式：只列已在课堂 H 里的学生（女儿A、成年学生），不列跟随进教室的成年干员与没进 H "
        "的学生（此前场上任何人都能选进模板）"
    ),
    "[0000]女儿A" in _l11_text
    and "[0000]成年学生" in _l11_text
    and "[0000]成年干员" not in _l11_text
    and "[0000]女儿B" not in _l11_text,
    _l11_text,
)
kernel_data.set_world(modes.set_sex_class, False)
drawn_text.clear()
group_sex_panel.Edit_Group_Sex_Temple_Panel(190).show_target_chara_list(
    "A", "mouth"
)
_l11_text = list(drawn_text)
check(
    "L11 对照：普通群交照旧列场上所有人",
    "[0000]成年干员" in _l11_text and "[0000]女儿B" in _l11_text,
    _l11_text,
)
check(
    "L9 课堂模式没开时成员名单为空",
    sex_class_handle.get_class_member_list() == [],
)
for _cid in (0, 201, 202, 301, 303):
    kernel_data.put(flags.set, _cid, is_h=False)
move_to(301, SCENE_DORM)
move_to(303, SCENE_DORM)
schedule_handle.clear_class_cell(ROOM_P, _l9_day, 8)
schedule_handle.clear_selected_course(303, _l9_day, 8)
education.clear_temp_classes()
kernel_data.set_world(modes.set_group_sex, False)

section(
    "Plan 32 实施复审补：L11 主修加成只给课堂成员——经验写入段（common_default.base_chara_experience_common_settle）"
    "对非成员不乘加成"
)

for _cid in (0, 201, 202, 204, 301, 303):
    kernel_data.put(flags.set, _cid, is_h=False)
for _cid in (0, 201, 301):
    move_to(_cid, classroom_path(ROOM_P))
for _cid in (202, 204, 303):
    move_to(_cid, SCENE_DORM)
set_time(period_time(3) + datetime.timedelta(minutes=5))
sex_class_handle.start_sex_class(70, [201])
kernel_data.put(flags.set, pl.cid, is_h=True)
kernel_data.put(activity.set_target, pl.cid, 301)
# 开课效果串里的 464 拉交互对象进 H，10014 置位两个模式并拉场景里符合门槛的学生进 H
run_effect_list([464, 10014])
kernel_data.put(flags.set, student_b.cid, is_h=True)
_l11_exp = sex_class_handle.get_now_bonus_exp_id()
""" 本节主修（指技）对应的经验：手交 """
_l11_other_exp = growth_handle.get_subject_exp_id(72)
""" 别门性技（足技）对应的经验：足交 """
_l11_members = sex_class_handle.get_class_member_list()
_l11_bonus = sex_class_handle.get_subject_bonus(201)
check(
    (
        "L11 前提：课堂模式开着、主修指技（主修经验 = 手交经验）；女儿A 被 10014 拉进课堂 H、是课堂成员；开课效果 464 "
        "把玩家的交互对象（非学生岗的成年干员）拉进了 H，"
        "她在玩家场景、在 H 里却不是成员；在宿舍 H 里的女儿B 不在玩家场景、也不是成员"
    ),
    modes.sex_class()
    and modes.group_sex()
    and _l11_exp == growth_handle.get_subject_exp_id(70) > 0
    and flags.get(student_a.cid, "is_h")
    and 201 in _l11_members
    and flags.get(adult.cid, "is_h")
    and activity.position(adult.cid) == activity.position(pl.cid)
    and 301 not in _l11_members
    and 202 not in _l11_members,
    (_l11_members, flags.get(adult.cid, "is_h"), activity.position(adult.cid)),
)
check(
    (
        "L11 前提：主修加成倍率大于 1（为 1 时下面几条「不乘」恒真），对成年干员算出的倍率同样大于 "
        "1（挡住她的是成员判定，不是倍率）；别门性技的经验 id 与主修不同"
    ),
    _l11_bonus > 1
    and sex_class_handle.get_subject_bonus(301) > 1
    and _l11_other_exp not in (0, _l11_exp),
    (_l11_bonus, sex_class_handle.get_subject_bonus(301), _l11_other_exp),
)


def l11_exp_gain(character_id: int, experience_id: int) -> int:
    """
    以角色自己为主体走一次经验写入（基础值 10），返回实际加上的经验
    Keyword arguments:
    character_id -- 角色id
    experience_id -- 经验id
    Return arguments:
    int -- 这次加上的经验
    """
    experience = ca.experience(character_id)
    before = experience.get(experience_id, 0)
    common_default.base_chara_experience_common_settle(
        character_id, experience_id, base_value=10
    )
    return experience.get(experience_id, 0) - before


_l11_gain = l11_exp_gain(201, _l11_exp)
check(
    "L11 课堂成员（女儿A）拿主修经验：基础 10 乘主修加成",
    _l11_gain == int(10 * _l11_bonus),
    (_l11_gain, _l11_bonus),
)
_l11_gain = l11_exp_gain(201, _l11_other_exp)
check("L11 课堂成员拿别门性技的经验（足交）：不乘", _l11_gain == 10, _l11_gain)
_l11_gain = l11_exp_gain(301, _l11_exp)
check(
    "L11 被开课效果 464 拉进 H 的成年干员（同场景、在 H 里，但不是学生岗也不是女儿）拿主修经验：不乘加成（此前乘）",
    _l11_gain == 10,
    _l11_gain,
)
_l11_gain_list = [l11_exp_gain(202, _l11_exp), l11_exp_gain(102, _l11_exp)]
check(
    "L11 不在玩家场景的角色（宿舍 H 里的女儿B、别处的母亲）拿主修经验：不乘加成（此前岛上别处拿到这门经验的人都乘）",
    _l11_gain_list == [10, 10],
    _l11_gain_list,
)
sex_class_handle.end_sex_class()
education.clear_temp_classes()
kernel_data.set_world(modes.set_sex_class, False)
kernel_data.set_world(modes.set_group_sex, False)
for _cid in (0, 201, 202, 301):
    kernel_data.put(flags.set, _cid, is_h=False)
kernel_data.put(activity.set_target, pl.cid, 0)
move_to(301, SCENE_DORM)

finish()
