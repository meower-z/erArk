# -*- coding: UTF-8 -*-
"""
旧存档读档后的成长阶段与体型
============================
开新游戏后按旧规则摆出存档状态：开着世界设定1（全岛干员的体型104~107换成103），一名静态干员持有素质表里没有的素质6与7、没有素质28的键，
四个女儿分处101、102、103与毕业（104），103的学员持有未初潮与未成年，101的婴儿有污浊、H状态、泌乳、妊娠与卵（含玩家持有的卵索引与她的体外卵），
102的孩子在线、与玩家在单人H中、有学生岗与宿舍、是玩家的助理、被玩家搬运与装袋、在别人的名单与收藏品里、在母亲的群交部位模板里、在见学、有课表与日程，道具栏里有外表年龄药，存档里还有配置表里没有的娱乐（含兴趣课的目标）与行为编号，以及改编号前的旧娱乐编号。
经 save_handle 真实写盘、读档，检查读档后的素质（每个角色的素质键与素质表的键相同）、见学与上课状态、道具与世界设定。
把读档后的游戏再写盘、读档一次，所有被检查的数据都没有变。
另一个测试关着世界设定1：持有103的静态干员读档后持有少女。
再两个测试在群交中读档：玩家、102的孩子与另一名干员同场景群交，玩家以孩子或那名干员为交互对象，读档后群交都按群交结束收尾。
"""

import importlib
import shutil
from typing import TYPE_CHECKING

from tests import chara_abilities as ca, kernel_data as kd
from tests.chara_activity import aim, behave, doing, scene_of
from tests.slow.base import SlowTestCase
from tests.kernel_project import activity
from tests import kernel_data

if TYPE_CHECKING:
    from typing import Any

SAVE_ID = "test_old_save_age_and_body_type"
""" 本测试写入 save/ 的存档id，测试结束时删掉 """
STAGE_TALENT_TUPLE = (101, 102, 103)
""" 成长阶段素质 """
BODY_TALENT_TUPLE = (104, 105, 106, 107, 108)
""" 体型素质 """
FOLLOW_MOTHER_ENTERTAINMENT = 153
""" 跟随母亲（见学）的娱乐编号 """
MISSING_ENTERTAINMENT = 159
""" Entertainment.csv 里没有的娱乐编号，代表存档里存着、配置表里已经去掉的娱乐 """
MISSING_BEHAVIOR = "behavior_not_in_table"
""" Behavior_Data.csv 里没有的行为id，代表存档里存着、配置表里已经去掉的行为 """
MINOR_OPERATOR_ADV = 254
""" 旧存档里持有素质6与7、没有素质28的键的静态干员的剧情npc编号 """


class TestOldSaveAgeAndBodyType(SlowTestCase):
    """旧存档读档后的成长阶段、体型、见学与上课状态、外表年龄药、世界设定1"""

    def tearDown(self) -> None:
        """删掉本测试写入的存档"""
        from Script.Core import save_handle

        shutil.rmtree(
            save_handle.get_save_dir_path(SAVE_ID), ignore_errors=True
        )
        super().tearDown()

    def _template_body(self, adv: int) -> list:
        """角色模板（data/character）持有的体型素质"""
        from Script.Config import character_config

        tem_character = character_config.character_tem_list.get(adv)
        if tem_character is None:
            return []
        return [
            talent_id
            for talent_id in BODY_TALENT_TUPLE
            if tem_character.Talent.get(talent_id, 0)
        ]

    def _daughter(self, mother_id: int, name: str, stage: int) -> int:
        """
        生一个女儿，摆到旧规则下的成长阶段：101婴儿，102幼女（学生岗、未成年、未初潮），103（未成年），104毕业
        Keyword arguments:
        mother_id -- 母亲角色id
        name -- 女儿的名字
        stage -- 101~104
        Return arguments:
        int -- 女儿的角色id
        """
        from Script.Modules.domains import chara_life
        from Script.Core import game_type

        daughter_id = kd.born(mother_id, name)
        for talent_id in (101, 102, 103, 104, 6, 7):
            ca.talent(daughter_id)[talent_id] = 0
        ca.talent(daughter_id)[stage] = 1
        if stage <= 102:
            ca.talent(daughter_id)[6] = 1
        if stage <= 103:
            ca.talent(daughter_id)[7] = 1
        if stage >= 102:
            kd.put(chara_life.work_type.set, daughter_id, 152)
        kd.put(kd.domain("growth").put, daughter_id, game_type.CHILD_GROWTH())
        return daughter_id

    def _build_old_save(self) -> dict:
        """
        按旧规则摆出存档状态
        Keyword arguments:
        无
        Return arguments:
        dict -- 各角色的id：minor、shrink（世界设定1缩小的、模板体型为大姐姐或熟女的干员）、
        shrunk（持有103的静态干员集合）、d101~d104、mother，
           以及检查要用的婴儿出生时间、外勤委托id、书id、孩子脱下的衣服、快感状态id
        """
        from Script.Modules.domains import chara_life, relations
        from Script.Design import game_time
        from Script.Config import game_config
        from Script.Modules.domains.commission import start

        cache = self.cache
        static_id_list = [
            c for c in cache.character_data if c and relations.father_id(c)
        ]
        # 世界设定1开局时把104~107换成103
        for cid in static_id_list:
            talent = ca.talent(cid)
            for talent_id in (104, 105, 106, 107):
                if talent.get(talent_id, 0):
                    talent[talent_id] = 0
                    talent[103] = 1
        kd.set_world_setting(1, 1)
        minor_id = [
            cid
            for cid in static_id_list
            if cache.character_data[cid].adv == MINOR_OPERATOR_ADV
        ][0]
        ca.talent(minor_id)[6] = 1
        ca.talent(minor_id)[7] = 1
        del ca.talent(minor_id)[28]
        kd.put(kd.domain("inventory").set_item, minor_id, 31, 1)
        shrink_id = min(
            cid
            for cid in static_id_list
            if self._template_body(cache.character_data[cid].adv)
            in ([105], [106])
        )
        kd.put(kd.domain("inventory").set_item, 0, 32, 2)
        roster = kd.domain("roster")
        mother_id = min(cid for cid in roster.active() if cid in static_id_list)
        id_dict: dict[str, Any] = {
            "minor": minor_id,
            "shrink": shrink_id,
            "shrunk": {
                cid for cid in static_id_list if ca.talent(cid).get(103, 0)
            },
        }
        for stage in (101, 102, 103, 104):
            id_dict[f"d{stage}"] = self._daughter(
                mother_id, f"测试女儿{stage}", stage
            )
        # 102的孩子：在线（与母亲同场景、在当前干员列表里，跟随玩家），正在见学，有课表、日程模板、单项覆盖与翘课标记，
        #    身上有精液、在H中；玩家与母亲都以她为目标
        from Script.Design import map_handle

        child = cache.character_data[id_dict["d102"]]
        mother = cache.character_data[mother_id]
        with kd.writing():
            map_handle.character_move_scene(
                activity.position(child.cid),
                activity.position(mother.cid),
                id_dict["d102"],
            )
        self.assertIn(
            id_dict["d102"],
            cache.scene_data[scene_of(mother.cid)].character_list,
            "存档前102的孩子在母亲所在的场景里",
        )
        # 学生岗在职业名单里，分到宿舍床位（旧规则下长成102时上线所做的）
        from Script.System.Dormitory_System import common as dormitory_common

        work = importlib.import_module("Script.Modules.domains.work")
        students = [*work.roster(152), id_dict["d102"]]
        kd.written(work.set_rosters, {**work.rosters(), 152: students})
        kd.written(
            dormitory_common.new_character_get_dormitory, id_dict["d102"]
        )
        self.assertIn(
            chara_life.dormitory(child.cid),
            dormitory_common.get_open_dormitory_room_occupancy(),
            "存档前102的孩子住在开放的普通宿舍里",
        )
        from Script.Modules.domains import action_info as ai, dirty, education
        from Script.Modules.domains import flags as fl, h_state, hypnosis
        from Script.Modules.domains import physical_exam as exam
        from Script.Modules.domains import player_ability as pa
        from Script.Modules.domains import player_collection as pc, prison

        with kd.writing(), dirty.editing(id_dict["d102"]) as d:
            d.body_semen[min(game_config.config_body_part)] = ["", 20, 20, 1]
        aim(0, id_dict["d102"])
        aim(mother.cid, id_dict["d102"])
        kd.put(relations.assistant_character_id.set, 0, id_dict["d102"])
        first = min(relations.assistant_services(child.cid))
        kd.put(relations.assistant_services.set_item, child.cid, first, 1)
        with kd.writing(), h_state.editing(mother_id) as mhs:
            mhs.group_sex_body_template_dict["A"][0]["mouth"] = [
                id_dict["d102"],
                5,
            ]
            mhs.group_sex_body_template_dict["B"][1] = [[id_dict["d102"], 0], 3]
        child_id = id_dict["d102"]
        commission_id = min(game_config.config_commission)
        team = [child_id, mother_id]
        now = game_time.now()
        with kd.writing():
            start(commission_id, team, now, [])
            ai.set(0, "carry_chara_id", child_id)
            pa.set(0, free_in_time_stop_chara_id=child_id)
            fl.set(0, bagging_chara_id=child_id, is_h=True)
            fl.set(child_id, is_follow=1, is_h=True, be_bagged=True)
            fl.set(child_id, imprisonment=True, field_commission=commission_id)
            ai.set(mother_id, "interacting_character_end_info", [child_id, now])
            ai.set(0, "ask_group_sex_refuse_chara_id_list", team)
            pc.put("first_panties", {child_id: "测试"})
            pc.put("npc_panties", {child_id: ["测试"]})
            pc.put("npc_socks", {child_id: ["测试"]})
            pc.put("milk_total", {child_id: 30})
            pc.put("urine_total", {child_id: 20})
            exam.finish(child_id, {"1"})
            exam.add(exam.WAITING, child_id)
            exam.add(exam.CHOSEN, child_id)
            prison.imprison(child_id, now, 0)
            education.put_temp_class(
                "1-1",
                {
                    "classroom": "理论教室一",
                    "ability_id": 70,
                    "must_attend": [child_id, mother_id],
                    "notified": [False, False, False],
                    "running": False,
                },
            )
            education.put_template(
                1,
                {
                    "name": "测试日程",
                    "slot": {
                        0: FOLLOW_MOTHER_ENTERTAINMENT,
                        1: MISSING_ENTERTAINMENT,
                        2: 0,
                    },
                },
            )
        book_id = min(game_config.config_book)
        kd.set_book_holders({book_id: child_id})
        kd.put(chara_life.borrow_book_id_set.set, child.cid, {book_id})
        cache.old_character_id = child_id
        # 玩家与她在单人H中（双方都在H、玩家所在房间关着门，她脱了一件衣服），母亲正对她做着别的行为；
        #    她身上有快感、催眠、待触发事件与必须结算的二段行为
        kd.put(h_state.set, 0, insert_position=2)
        cache.scene_data[
            map_handle.get_map_system_path_str_for_list(activity.position(0))
        ].close_flag = 1
        clothing_type = min(game_config.config_clothing_type)
        cloth = kd.domain("wardrobe").of(child.cid)
        cloth.cloth_wear[clothing_type] = []
        cloth.cloth_off[clothing_type] = [min(game_config.config_clothing_tem)]
        kd.put(kd.domain("wardrobe").put, child.cid, cloth)
        behave(mother.cid, "wait")
        pleasure_state = min(
            state_id
            for state_id, state in game_config.config_character_state.items()
            if state.type == 0
        )
        kd.put(kd.domain("status").set, child.cid, pleasure_state, 500)
        kd.put(hypnosis.set, child_id, hypnosis_degree=50)
        kernel_data.put(activity.update_event, child.cid, event_id="test_event")
        kd.put(activity.set_must_settle, child.cid, ["test_second_behavior"])
        id_dict["cloth"] = (clothing_type, min(game_config.config_clothing_tem))
        id_dict["pleasure_state"] = pleasure_state
        id_dict["commission"] = commission_id
        id_dict["book"] = book_id
        behave(child.cid, "follow_mother")
        kernel_data.put(activity.set_state, child.cid, 231)
        aim(child.cid, mother_id)
        follow = FOLLOW_MOTHER_ENTERTAINMENT
        kd.put(chara_life.entertainment_type.set, child.cid, [follow] * 2 + [0])
        growth = kd.domain("growth")
        pregnancy = kd.domain("pregnancy")
        student = cache.character_data[id_dict["d103"]]
        ca.talent(student)[6] = 1
        kd.put(chara_life.entertainment_type.set, id_dict["d104"], [176, 0, 0])
        missing = [MISSING_ENTERTAINMENT, 0, 0]
        kd.put(chara_life.entertainment_type.set, student.cid, missing)
        behave(minor_id, MISSING_BEHAVIOR)
        with kd.writing():
            with growth.editing(id_dict["d102"]) as child_g:
                child_g.follow_mother_flag = True
                child_g.selected_course = {0: {0: [0, "理论教室一"]}}
                child_g.schedule_template_id = 1
                child_g.schedule_override = {0: FOLLOW_MOTHER_ENTERTAINMENT}
                child_g.skip_class_flag = True
                child_g.skip_class_day = game_time.now().toordinal()
            with growth.editing(id_dict["d103"]) as stu_g:
                stu_g.follow_mother_flag = True
                stu_g.selected_course = {
                    1: {2: [0, "理论教室一"], 3: [4, MISSING_ENTERTAINMENT]}
                }
                stu_g.schedule_override = {1: MISSING_ENTERTAINMENT}
            with growth.editing(id_dict["d104"]) as grad_g:
                grad_g.attend_class_count = 30
                grad_g.report_card_history = [{"semester": [2020, 6]}]
        # 101的婴儿：有污浊、H状态与身体道具、H标记与后续链、泌乳、妊娠与卵；母亲在产后、育儿、泌乳
        baby = cache.character_data[id_dict["d101"]]
        body_part = min(game_config.config_body_part)
        clothing_type = min(game_config.config_clothing_type)
        baby_id = baby.cid
        with kd.writing():
            with dirty.editing(baby_id) as bd:
                bd.body_semen[body_part] = ["", 50, 50, 1]
                bd.cloth_semen[clothing_type] = ["", 50, 50, 1]
                bd.cloth_locker_semen[clothing_type] = ["", 50, 50, 1]
            with h_state.editing(baby_id) as bhs:
                bhs.body_item[min(game_config.config_body_item)] = [
                    "",
                    True,
                    None,
                ]
                bhs.orgasm_count[
                    min(
                        s
                        for s, st in game_config.config_character_state.items()
                        if st.type == 0
                    )
                ] = [3, 3]
            fl.set(baby_id, is_h=True, milk=True, masturebate=1)
            fl.set(baby_id, go_to_join_group_sex=True)
            pc.put("held_eggs", {0: (baby_id, 0)})
            pc.put(
                "soft_eggs",
                {
                    0: {"mother_id": baby_id, "semen_count": 5.0},
                    1: {"mother_id": mother_id, "semen_count": 5.0},
                },
            )
        aim(baby.cid, 0)
        for talent_id in (20, 21, 27):
            ca.talent(baby)[talent_id] = 1
        kd.set_needs(baby.cid, milk=50)
        kd.put(
            pregnancy.update,
            baby.cid,
            lactation_flag=True,
            fertilization_rate=30,
            eggs={0: {"identified": False, "fertilized": True}},
            next_egg_id=1,
            born_time=game_time.now(),
        )
        id_dict["baby_born_time"] = game_time.now()
        mother = cache.character_data[mother_id]
        for talent_id in (23, 24, 27):
            ca.talent(mother_id)[talent_id] = 1
        kd.set_needs(mother_id, milk=80)
        id_dict["mother"] = mother_id
        return id_dict

    def _save_and_load(self, inject_active: tuple[int, ...] = ()) -> None:
        """写盘（可选往旧存档文件注入在编 id）再读档"""
        import json
        import os
        from Script.Core import save_handle
        from Script.Modules.save_load import index, kernel_state

        save_handle.establish_save(SAVE_ID)
        self.assertTrue(
            save_handle.judge_save_file_exist(SAVE_ID), "存档应已写到盘上"
        )
        if inject_active:
            path = os.path.join(index.path(SAVE_ID), kernel_state.SAVE_FILE)
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
            active = set(payload["data"].get("roster.active", []))
            payload["data"]["roster.active"] = sorted(
                active | set(inject_active)
            )
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
        save_handle.input_load_save(SAVE_ID)

    def _snapshot(self) -> dict:
        """
        记下本测试检查的全部数据
        Keyword arguments:
        无
        Return arguments:
        dict -- 角色id到数据的字典，外加世界设定、日程模板、玩家收藏品里的卵、当前干员列表、各场景的角色、GameState 的
           全部全局数据，以及场景面板记着的角色
        """
        from Script.Modules.domains import action_info as ai, dirty, education
        from Script.Modules.domains import flags as fl, growth as growth_mod
        from Script.Modules.domains import h_state, hypnosis
        from Script.Modules.domains import player_ability as pa
        from Script.Modules.domains import player_collection as pc
        from Script.Modules.domains import pregnancy as pregnancy_mod, roster
        from Script.Modules.domains import chara_life as life, relations
        from Script.Kernel import core

        snapshot: dict[str | int, object] = {
            "world_setting": kd.world_settings(),
            "template": repr(education.templates()),
            "eggs": repr((pc.get("held_eggs"), pc.get("soft_eggs"))),
            "npc_id_got": sorted(roster.active()),
            "scene": {
                path: sorted(scene.character_list)
                for path, scene in self.cache.scene_data.items()
            },
            "data": dict(core.state().data),
            "old_character_id": self.cache.old_character_id,
        }
        for cid, chara in self.cache.character_data.items():
            growth = growth_mod.of(cid)
            snapshot[cid] = (
                dict(ca.talent(chara)),
                dict(kd.domain("inventory").items(chara.cid)),
                activity.behavior(chara.cid).behavior_id,
                activity.state(chara.cid),
                list(life.entertainment_type(chara.cid)),
                list(activity.position(chara.cid)),
                activity.target(chara.cid),
                ai.get(chara.cid, "carry_chara_id"),
                repr(
                    (
                        vars(kd.domain("wardrobe").of(chara.cid)),
                        hypnosis.degree(cid),
                        activity.event(chara.cid).event_id,
                        activity.must_settle(chara.cid),
                        sorted(kd.domain("status").of(chara.cid).items()),
                    )
                ),
                relations.assistant_character_id(chara.cid),
                dict(relations.assistant_services(chara.cid)),
                repr(
                    (
                        pa.get(chara.cid, "free_in_time_stop_chara_id"),
                        fl.get(chara.cid, "bagging_chara_id"),
                        fl.get(chara.cid, "be_bagged"),
                        ai.get(chara.cid, "interacting_character_end_info")[0],
                        ai.get(chara.cid, "ask_group_sex_refuse_chara_id_list"),
                    )
                ),
                repr(
                    [
                        sorted(pc.get(name, chara.cid).items())
                        for name in (
                            "first_panties",
                            "npc_panties",
                            "npc_socks",
                            "milk_total",
                            "urine_total",
                        )
                    ]
                ),
                life.work_type(chara.cid),
                life.dormitory(chara.cid),
                None if growth is None else repr(sorted(vars(growth).items())),
                repr(
                    [
                        sorted(vars(part).items())
                        for part in (
                            dirty.view(cid),
                            h_state.view(cid),
                            pregnancy_mod.of(cid),
                        )
                    ]
                    + [sorted(fl.snapshot(chara.cid).items())]
                ),
            )
        return snapshot

    def _assert_converted(self, id_dict: dict) -> None:
        """
        检查读档后的数据
        Keyword arguments:
        id_dict -- _build_old_save 返回的角色id
        Return arguments:
        无
        """
        from Script.Modules.domains import chara_life, relations
        from Script.Config import game_config

        cache = self.cache
        work = kd.domain("work")
        growth_mod = kd.domain("growth")
        pregnancy_mod = kd.domain("pregnancy")
        roster = kd.domain("roster")
        self.assertEqual(kd.world_settings().get(1, 0), 0, "世界设定1应已关闭")
        for cid, chara in cache.character_data.items():
            stage_list = [
                talent_id
                for talent_id in STAGE_TALENT_TUPLE
                if ca.talent(chara).get(talent_id, 0)
            ]
            body_list = [
                talent_id
                for talent_id in BODY_TALENT_TUPLE
                if ca.talent(chara).get(talent_id, 0)
            ]
            self.assertFalse(
                any(kd.domain("inventory").items(cid).get(i) for i in (31, 32)),
                f"角色{cid}的道具栏里不应有外表年龄药",
            )
            cg = growth_mod.of(cid)
            self.assertFalse(
                cg is not None and cg.follow_mother_flag,
                f"角色{cid}不应在见学",
            )
            self.assertNotEqual(
                doing(chara.cid),
                "follow_mother",
                f"角色{cid}的行为不应是跟随母亲",
            )
            for value in chara_life.entertainment_type(chara.cid):
                self.assertIn(
                    value,
                    game_config.config_entertainment,
                    f"角色{cid}的娱乐槽位{value}应在 Entertainment.csv 里",
                )
            self.assertEqual(
                ca.talent(chara).keys(),
                game_config.config_talent.keys(),
                f"角色{cid}读档后的素质键应与素质表的键相同",
            )
            if cid == 0:
                continue
            if relations.father_id(chara.cid) == 0:
                continue
            self.assertEqual(stage_list, [], f"静态干员{cid}不应持有成长阶段")
            if cid in id_dict["shrunk"]:
                self.assertEqual(
                    body_list,
                    self._template_body(chara.adv) or [104],
                    f"世界设定1缩小的静态干员{cid}应取回模板的体型，模板没有体型时为少女",
                )
        self.assertEqual(
            self._template_body(cache.character_data[id_dict["shrink"]].adv),
            [
                t
                for t in BODY_TALENT_TUPLE
                if ca.talent(id_dict["shrink"]).get(t, 0)
            ],
            "世界设定1缩小的干员应取回模板的体型",
        )
        self.assertEqual(
            [
                t
                for t in BODY_TALENT_TUPLE
                if ca.talent(id_dict["minor"]).get(t, 0)
            ],
            [104],
            "持有103的静态干员应持有少女",
        )
        for stage in (101, 102, 103):
            daughter_talent = ca.talent(id_dict[f"d{stage}"])
            self.assertEqual(
                [t for t in STAGE_TALENT_TUPLE if daughter_talent.get(t, 0)],
                [stage],
                f"{stage}阶段的女儿应保留成长阶段",
            )
        graduate = cache.character_data[id_dict["d104"]]
        graduate_talent = ca.talent(graduate)
        self.assertEqual(
            (
                [t for t in STAGE_TALENT_TUPLE if graduate_talent.get(t, 0)],
                graduate_talent.get(104, 0),
            ),
            ([], 1),
            "毕业的女儿保持少女",
        )
        grad_g = growth_mod.of(graduate.cid)
        assert grad_g is not None
        self.assertEqual(
            (grad_g.attend_class_count, grad_g.report_card_history),
            (30, [{"semester": [2020, 6]}]),
            "毕业的女儿的养成记录保持原样",
        )
        child = cache.character_data[id_dict["d102"]]
        self.assertEqual(
            (doing(child.cid), activity.state(child.cid)),
            ("share_blankly", 0),
            "102的孩子应在发呆",
        )
        growth = growth_mod.of(child.cid)
        assert growth is not None
        self.assertEqual(
            (
                growth.selected_course,
                growth.schedule_template_id,
                growth.schedule_override,
                growth.skip_class_flag,
                growth.skip_class_day,
            ),
            ({}, 0, {}, False, 0),
            "102的孩子应没有课表、日程与翘课标记",
        )
        student = cache.character_data[id_dict["d103"]]
        stu_g = growth_mod.of(student.cid)
        assert stu_g is not None
        self.assertEqual(
            stu_g.selected_course,
            {1: {2: [0, "理论教室一"]}},
            "103的学员保留课表，目标不在娱乐表里的兴趣课删掉",
        )
        self.assertEqual(
            (
                chara_life.entertainment_type(student.cid),
                stu_g.schedule_override,
            ),
            ([0, 0, 0], {}),
            "表里没有的娱乐：槽位换成0，单项覆盖删掉",
        )
        self.assertEqual(
            doing(id_dict["minor"]),
            "share_blankly",
            "表里没有的行为换成发呆",
        )
        education = importlib.import_module("Script.Modules.domains.education")
        self.assertEqual(
            education.templates()[1]["slot"][1],
            0,
            "日程模板里表里没有的娱乐换成0",
        )
        from Script.Modules.domains import dirty, h_state

        baby = cache.character_data[id_dict["d101"]]
        baby_dirty, baby_hs = dirty.view(baby.cid), h_state.view(baby.cid)
        for semen_table in (
            baby_dirty.body_semen,
            baby_dirty.cloth_semen,
            baby_dirty.cloth_locker_semen,
        ):
            self.assertEqual(
                [
                    key
                    for key, semen_list in semen_table.items()
                    if any(semen_list[1:])
                ],
                [],
                "101的婴儿身上与服装上没有精液",
            )
        self.assertEqual(
            [
                key
                for key, item_data in baby_hs.body_item.items()
                if item_data[1]
            ],
            [],
            "101的婴儿没有在用的身体道具",
        )
        self.assertEqual(
            [
                key
                for key, count in baby_hs.orgasm_count.items()
                if count != [0, 0]
            ],
            [],
            "101的婴儿没有绝顶记录",
        )
        from Script.Modules.domains import action_info as ai, flags as fl

        self.assertEqual(
            (
                fl.get(baby.cid, "is_h"),
                fl.get(baby.cid, "milk"),
                fl.get(baby.cid, "masturebate"),
                fl.get(baby.cid, "go_to_join_group_sex"),
            ),
            (False, 0, 0, False),
            "101的婴儿没有H标记与后续链",
        )
        self.assertEqual(
            [
                talent_id
                for talent_id in (20, 21, 22, 23, 24, 25, 26, 27, 32, 35)
                if ca.talent(baby).get(talent_id, 0)
            ],
            [],
            "101的婴儿没有妊娠与泌乳素质",
        )
        baby_preg = pregnancy_mod.of(baby.cid)
        self.assertEqual(
            (
                kd.needs_of(baby.cid)["milk"],
                baby_preg.lactation_flag,
                baby_preg.fertilization_rate,
                baby_preg.eggs,
                baby_preg.next_egg_id,
            ),
            (0, False, 0, {}, 0),
            "101的婴儿没有奶、受精率与卵",
        )
        self.assertEqual(
            baby_preg.born_time,
            id_dict["baby_born_time"],
            "101的婴儿保留出生时间",
        )
        from Script.System.Education_System import growth_handle

        for stage in (101, 102):
            child_id = id_dict[f"d{stage}"]
            child = cache.character_data[child_id]
            self.assertEqual(
                (
                    chara_life.work_type(child.cid),
                    chara_life.dormitory(child.cid),
                    chara_life.permanent_dormitory(child.cid),
                ),
                (0, "", ""),
                f"{stage}的孩子没有职业、没有宿舍",
            )
            self.assertEqual(
                [w for w, ids in work.rosters().items() if child_id in ids],
                [],
                f"{stage}的孩子不在任何职业名单里",
            )
            self.assertNotIn(
                child_id,
                growth_handle.get_student_candidate_list()
                + growth_handle.get_course_candidate_list(),
                f"{stage}的孩子不在养成与课表的学生名单里",
            )
            self.assertEqual(
                [
                    path
                    for path, scene in cache.scene_data.items()
                    if child_id in scene.character_list
                ],
                [],
                f"{stage}的孩子不在任何场景里",
            )
            self.assertFalse(
                roster.has(child_id), f"{stage}的孩子不在当前干员列表里"
            )
            self.assertEqual(
                (
                    activity.position(child.cid),
                    fl.get(child.cid, "is_follow"),
                    activity.target(child.cid),
                ),
                (["0", "0"], 0, child_id),
                f"{stage}的孩子的位置、跟随与目标都不指向场景或别人",
            )
            self.assertEqual(
                [
                    cid
                    for cid, chara in cache.character_data.items()
                    if cid != child_id and activity.target(cid) == child_id
                ],
                [],
                f"没有角色以{stage}的孩子为目标",
            )
        template_dict = h_state.view(
            id_dict["mother"]
        ).group_sex_body_template_dict
        self.assertEqual(
            (
                ai.get(0, "carry_chara_id"),
                relations.assistant_character_id(0),
                template_dict["A"][0]["mouth"],
                template_dict["B"][1],
            ),
            (0, 0, [-1, -1], [[0], 3]),
            "玩家没有在搬运102的孩子，她不是助理，母亲的群交部位模板里没有她，玩家留在阴茎侍奉里",
        )
        from Script.Design import child_stage_gate

        child_id_set = {id_dict["d101"], id_dict["d102"]}
        self.assertEqual(
            [
                cid
                for cid in cache.character_data
                if cid not in child_id_set
                and child_stage_gate.involves_child_stage(cid)
            ],
            [],
            "读档后幼年阶段的H闸找不到以孩子为交互对象的角色",
        )
        child = cache.character_data[id_dict["d102"]]
        self.assertFalse(
            any(relations.assistant_services(child.cid).values()),
            "102的孩子没有开着的助理服务",
        )
        self._assert_no_child_reference(id_dict)
        self._assert_h_session_ended(id_dict)
        self.assertEqual(
            (
                fl.get(child.cid, "is_h"),
                [
                    key
                    for key, semen_list in dirty.view(
                        child.cid
                    ).body_semen.items()
                    if any(semen_list[1:])
                ],
            ),
            (False, []),
            "102的孩子没有H标记与精液",
        )
        pc = kd.domain("player_collection")
        self.assertEqual(
            (
                pc.get("held_eggs"),
                [egg["mother_id"] for egg in pc.get("soft_eggs").values()],
            ),
            ({}, [id_dict["mother"]]),
            "玩家收藏品里没有101婴儿的卵，母亲的体外卵保留",
        )
        mother = cache.character_data[id_dict["mother"]]
        self.assertEqual(
            (
                [ca.talent(mother).get(t, 0) for t in (23, 24, 27)],
                kd.needs_of(mother.cid)["milk"],
            ),
            ([1, 1, 1], 80),
            "母亲的产后、育儿与泌乳保持原样",
        )
        for value in education.templates()[1]["slot"].values():
            self.assertTrue(
                value == 0 or value in game_config.config_entertainment,
                f"日程模板的时段{value}应是自由选择或 Entertainment.csv 里的娱乐",
            )

    def _assert_no_child_reference(self, id_dict: dict) -> None:
        """检查其他结构里没有对102孩子的引用，与她并列的母亲的条目保留"""
        life = importlib.import_module("Script.Modules.domains.chara_life")
        cache = self.cache
        child_id = id_dict["d102"]
        mother_id = id_dict["mother"]
        from Script.Modules.domains import action_info as ai, commission
        from Script.Modules.domains import education, flags as fl, library
        from Script.Modules.domains import physical_exam as exam, prison
        from Script.Modules.domains import player_ability as pa
        from Script.Modules.domains import player_collection as pc

        self.assertEqual(
            (
                pa.get(0, "free_in_time_stop_chara_id"),
                fl.get(0, "bagging_chara_id"),
                fl.get(child_id, "be_bagged"),
            ),
            (0, 0, False),
            "没有以孩子为时停自由活动或装袋的对象",
        )
        self.assertEqual(
            ai.get(mother_id, "interacting_character_end_info")[0],
            -1,
            "母亲的交互中对象不是孩子",
        )
        self.assertEqual(
            ai.get(0, "ask_group_sex_refuse_chara_id_list"),
            [mother_id],
            "拒绝群交名单里没有孩子，母亲保留",
        )
        self.assertEqual(
            (
                pc.get("first_panties").get(child_id, ""),
                pc.get("npc_panties").get(child_id, []),
                pc.get("npc_socks").get(child_id, []),
                pc.get("milk_total").get(child_id, 0),
                pc.get("urine_total").get(child_id, 0),
            ),
            ("", [], [], 0, 0),
            "玩家收藏品里没有孩子的胖次、袜子、乳汁与圣水",
        )
        self.assertEqual(
            [child_id in one for one in (prison.prisoner_ids(),)]
            + [exam.has(key, child_id) for key in (exam.TODAY, *exam.ID_LISTS)],
            [False] * 5,
            "囚犯与体检名单里没有孩子",
        )
        self.assertEqual(
            (
                fl.get(child_id, "imprisonment"),
                fl.get(child_id, "field_commission"),
            ),
            (False, 0),
            "孩子不在监禁与外勤中",
        )
        self.assertEqual(
            (
                list(commission.ongoing()[id_dict["commission"]].team),
                (education.temp_class("1-1") or {}).get("must_attend"),
            ),
            ([mother_id], [mother_id]),
            "外勤委托与实操课必修名单里没有孩子，母亲保留",
        )
        self.assertEqual(
            (
                library.holders()[id_dict["book"]],
                life.borrow_book_id_set(child_id),
                cache.old_character_id,
            ),
            (-1, set(), 0),
            "孩子借的书还回去，场景面板记着的角色不是她",
        )

    def _assert_h_session_ended(self, id_dict: dict) -> None:
        """
        检查与102孩子的单人H已按结束H收尾：玩家不在H中、交互对象是自己、插入位置复位、房门打开；
           孩子穿回衣服，快感、催眠、待触发事件与必须结算的二段行为归零；母亲对她的行为换成发呆
        Keyword arguments:
        id_dict -- _build_old_save 返回的角色id
        Return arguments:
        无
        """
        cache = self.cache
        child = cache.character_data[id_dict["d102"]]
        mother = cache.character_data[id_dict["mother"]]
        from Script.Modules.domains import h_state, hypnosis

        clothing_type, cloth_id = id_dict["cloth"]
        fl = kd.domain("flags")
        self.assertEqual(
            (
                fl.get(0, "is_h"),
                activity.target(0),
                h_state.get(0, "insert_position"),
                fl.get(0, "hidden_sex_mode"),
            ),
            (False, 0, -1, 0),
            "玩家已结束H，交互对象是自己",
        )
        self.assertEqual(
            cache.scene_data[scene_of(0)].close_flag,
            0,
            "结束H后房门打开",
        )
        cloth = kd.domain("wardrobe").of(child.cid)
        self.assertEqual(
            (
                fl.get(child.cid, "is_h"),
                cloth.cloth_off[clothing_type],
                cloth_id in cloth.cloth_wear[clothing_type],
            ),
            (False, [], True),
            "孩子不在H中，穿回了脱下的衣服",
        )
        self.assertEqual(
            (
                kd.domain("status").of(child.cid)[id_dict["pleasure_state"]],
                hypnosis.degree(child.cid),
                activity.event(child.cid).event_id,
                activity.must_settle(child.cid),
            ),
            (0, 0, "", []),
            "孩子的快感、催眠、待触发事件与必须结算的二段行为归零",
        )
        self.assertEqual(
            (doing(mother.cid), activity.target(mother.cid)),
            ("share_blankly", id_dict["mother"]),
            "母亲对孩子的行为换成发呆",
        )

    def test_old_save_converts_once(self) -> None:
        """旧存档读档后符合现行规则；再写盘读档一次，数据不变"""
        id_dict = self._build_old_save()
        self._save_and_load(inject_active=(id_dict["d102"],))
        self._assert_converted(id_dict)
        first = self._snapshot()
        self._save_and_load()
        self._assert_converted(id_dict)
        self.assertEqual(
            self._snapshot(), first, "第二次读档不应改动任何被检查的数据"
        )

    def test_stage_without_world_setting(self) -> None:
        """没开世界设定1时，持有103的静态干员读档后持有少女，不取模板的体型"""
        relations = importlib.import_module("Script.Modules.domains.relations")
        cache = self.cache
        kd.set_world_setting(1, 0)
        static_id_list = [
            c for c in cache.character_data if c and relations.father_id(c)
        ]
        operator_id = min(
            cid
            for cid in static_id_list
            if self._template_body(cache.character_data[cid].adv)
            in ([105], [106])
        )
        talent = ca.talent(operator_id)
        for talent_id in BODY_TALENT_TUPLE:
            talent[talent_id] = 0
        talent[103] = 1
        self._save_and_load()
        talent = ca.talent(operator_id)
        self.assertEqual(
            [
                t
                for t in STAGE_TALENT_TUPLE + BODY_TALENT_TUPLE
                if talent.get(t, 0)
            ],
            [104],
            "没开世界设定1时持有103的静态干员应只持有少女",
        )

    def _group_h_case(self, child_in_template: bool) -> None:
        """
        摆出群交中的旧存档并检查读档：玩家、102的孩子与另一名干员同场景在群交；
           读档后群交按群交结束收尾，三人有效的交互对象，再写盘读档一次，数据不变
        Keyword arguments:
        child_in_template -- True：玩家以孩子为交互对象，孩子在玩家的部位模板里；
        False：玩家以那名干员为交互对象，没有模板写着孩子
        Return arguments:
        无
        """
        from Script.Modules.domains import relations
        from Script.Design import map_handle

        cache = self.cache
        roster = kd.domain("roster")
        static_id_list = sorted(
            cid
            for cid in roster.active()
            if cid != 0 and relations.father_id(cid) != 0
        )
        mother_id, other_id = static_id_list[0], static_id_list[1]
        child_id = self._daughter(mother_id, "测试女儿群交", 102)
        from Script.Modules.domains import flags as fl, modes

        with kd.writing():
            for cid in (child_id, other_id):
                map_handle.character_move_scene(
                    activity.position(cid), activity.position(0), cid
                )
                activity.set_target(cid, 0)
            modes.set_group_sex(True)
            for cid in (0, child_id, other_id):
                fl.set(cid, is_h=True)
        from Script.Modules.domains import h_state

        with kd.writing(), h_state.editing(0) as phs:
            tpl = phs.group_sex_body_template_dict
            tpl["A"][0]["L_hand"] = [other_id, 5]
            if child_in_template:
                aim(0, child_id)
                tpl["A"][0]["mouth"] = [child_id, 5]
                tpl["B"][1] = [[child_id, other_id], 3]
            else:
                aim(0, other_id)
            phs.insert_position = 2
        scene_path = map_handle.get_map_system_path_str_for_list(
            activity.position(0)
        )
        self.assertTrue(
            {0, child_id, other_id}
            <= set(cache.scene_data[scene_path].character_list),
            "存档前三人同场景",
        )
        snapshot_list = []
        for idx in range(2):
            self._save_and_load(inject_active=(child_id,) if idx == 0 else ())
            self.assertFalse(kd.mode("group_sex"), "群交模式已关闭")
            for character_id in (0, child_id, other_id):
                chara = cache.character_data[character_id]
                self.assertFalse(
                    fl.get(chara.cid, "is_h"),
                    f"角色{character_id}不在H中",
                )
                self.assertIn(
                    activity.target(character_id),
                    cache.character_data,
                    f"角色{character_id}的交互对象是存在的角色",
                )
                if character_id != child_id:
                    self.assertNotEqual(
                        activity.target(character_id),
                        child_id,
                        f"角色{character_id}的交互对象不是孩子",
                    )
                tpls = h_state.view(
                    character_id
                ).group_sex_body_template_dict.values()
                template_id_list = [
                    part[0]
                    for template in tpls
                    for part in template[0].values()
                ] + [one for template in tpls for one in template[1][0]]
                self.assertEqual(
                    set(template_id_list),
                    {-1},
                    f"角色{character_id}的群交部位模板已清空",
                )
            self.assertEqual(
                (
                    h_state.get(0, "insert_position"),
                    activity.target(0),
                ),
                (-1, 0 if child_in_template else other_id),
                "玩家的插入位置复位，交互对象有效",
            )
            self.assertNotIn(
                child_id,
                cache.scene_data[scene_path].character_list,
                "孩子离开了场景",
            )
            snapshot_list.append(self._snapshot())
        self.assertEqual(
            snapshot_list[0],
            snapshot_list[1],
            "第二次读档不应改动任何被检查的数据",
        )

    def test_group_h_with_child_ends(self) -> None:
        """
        群交中玩家以102的孩子为交互对象、孩子在部位模板里：读档后群交结束
        Keyword arguments:
        无
        Return arguments:
        无
        """
        self._group_h_case(True)

    def test_group_h_child_not_in_template_ends(self) -> None:
        """
        群交中孩子与玩家同场景在H中，玩家以另一名干员为交互对象，没有部位模板写着孩子：读档后群交同样结束
        Keyword arguments:
        无
        Return arguments:
        无
        """
        self._group_h_case(False)
