# -*- coding: UTF-8 -*-
"""
旧存档读档后的成长阶段与体型
============================
开新游戏后按旧规则摆出存档状态：开着世界设定1（全岛干员的体型104~107换成103），一名静态干员持有未初潮与未成年，
四个女儿分处101、102、103与毕业（104），103的学员持有未初潮与未成年，101的婴儿有污浊、H状态、泌乳、妊娠与卵（含玩家持有的卵索引与她的体外卵），
102的孩子在线、与玩家在单人H中、有学生岗与宿舍、是玩家的助理、被玩家搬运与装袋、在别人的名单与收藏品里、在母亲的群交部位模板里、在见学、有课表与日程，道具栏里有外表年龄药，存档里还有配置表里没有的娱乐（含兴趣课的目标）与行为编号，以及改编号前的旧娱乐编号。
经 save_handle 真实写盘、读档，检查读档后的素质、见学与上课状态、道具与世界设定；
把读档后的游戏再写盘、读档一次，所有被检查的数据都没有变。
另一个测试关着世界设定1：持有103的静态干员读档后持有少女。
再两个测试在群交中读档：玩家、102的孩子与另一名干员同场景群交，玩家以孩子或那名干员为交互对象，读档后群交都按群交结束收尾。
"""
import shutil

from tests.slow.base import SlowTestCase

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
""" 摆出未初潮与未成年的静态干员 """


class TestOldSaveAgeAndBodyType(SlowTestCase):
    """旧存档读档后的成长阶段、体型、见学与上课状态、外表年龄药、世界设定1"""

    def tearDown(self):
        """
        删掉本测试写入的存档
        Keyword arguments:
        无
        Return arguments:
        无
        """
        from Script.Core import save_handle

        shutil.rmtree(save_handle.get_save_dir_path(SAVE_ID), ignore_errors=True)
        super().tearDown()

    def _template_body(self, adv: int) -> list:
        """
        角色模板（data/character）持有的体型素质
        Keyword arguments:
        adv -- 角色的adv
        Return arguments:
        list -- 体型素质id列表
        """
        from Script.Config import character_config

        tem_character = character_config.character_tem_list.get(adv)
        if tem_character is None:
            return []
        return [talent_id for talent_id in BODY_TALENT_TUPLE if tem_character.Talent.get(talent_id, 0)]

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
        from Script.Core import game_type
        from Script.Design import character_handle

        daughter_id = character_handle.born_new_character(mother_id, name)
        daughter = self.cache.character_data[daughter_id]
        for talent_id in (101, 102, 103, 104, 6, 7):
            daughter.talent[talent_id] = 0
        daughter.talent[stage] = 1
        if stage <= 102:
            daughter.talent[6] = 1
        if stage <= 103:
            daughter.talent[7] = 1
        if stage >= 102:
            daughter.work.work_type = 152
        daughter.child_growth = game_type.CHILD_GROWTH()
        return daughter_id

    def _build_old_save(self) -> dict:
        """
        按旧规则摆出存档状态
        Keyword arguments:
        无
        Return arguments:
        dict -- 各角色的id：minor、shrink（世界设定1缩小的、模板体型为大姐姐或熟女的干员）、shrunk（持有103的静态干员集合）、d101~d104、mother，
           以及检查要用的婴儿出生时间、外勤委托id、书id、孩子脱下的衣服、快感状态id
        """
        from Script.Config import game_config

        cache = self.cache
        static_id_list = [cid for cid, chara in cache.character_data.items() if cid != 0 and chara.relationship.father_id != 0]
        # 世界设定1开局时把104~107换成103
        for cid in static_id_list:
            talent = cache.character_data[cid].talent
            for talent_id in (104, 105, 106, 107):
                if talent.get(talent_id, 0):
                    talent[talent_id] = 0
                    talent[103] = 1
        cache.world_setting[1] = 1
        minor_id = [cid for cid in static_id_list if cache.character_data[cid].adv == MINOR_OPERATOR_ADV][0]
        cache.character_data[minor_id].talent[6] = 1
        cache.character_data[minor_id].talent[7] = 1
        cache.character_data[minor_id].item[31] = 1
        shrink_id = min(cid for cid in static_id_list if self._template_body(cache.character_data[cid].adv) in ([105], [106]))
        cache.character_data[0].item[32] = 2
        mother_id = min(cid for cid in cache.npc_id_got if cid in static_id_list)
        id_dict = {"minor": minor_id, "shrink": shrink_id, "shrunk": {cid for cid in static_id_list if cache.character_data[cid].talent.get(103, 0)}}
        for stage in (101, 102, 103, 104):
            id_dict[f"d{stage}"] = self._daughter(mother_id, f"测试女儿{stage}", stage)
        # 102的孩子：在线（与母亲同场景、在当前干员列表里，跟随玩家），正在见学，有课表、日程模板、单项覆盖与翘课标记，
        #    身上有精液、在H中；玩家与母亲都以她为目标
        from Script.Design import map_handle

        child = cache.character_data[id_dict["d102"]]
        mother = cache.character_data[mother_id]
        map_handle.character_move_scene(child.position, mother.position, id_dict["d102"])
        cache.npc_id_got.add(id_dict["d102"])
        self.assertIn(id_dict["d102"], cache.scene_data[map_handle.get_map_system_path_str_for_list(mother.position)].character_list, "存档前102的孩子在母亲所在的场景里")
        # 学生岗在职业名单里，分到宿舍床位（旧规则下长成102时上线所做的）
        from Script.System.Dormitory_System import common as dormitory_common

        cache.rhodes_island.all_work_npc_set.setdefault(152, set()).add(id_dict["d102"])
        dormitory_common.new_character_get_dormitory(id_dict["d102"])
        self.assertIn(child.dormitory, dormitory_common.get_open_dormitory_room_occupancy(), "存档前102的孩子住在开放的普通宿舍里")
        child.sp_flag.is_follow = 1
        child.sp_flag.is_h = True
        child.dirty.body_semen[min(game_config.config_body_part)] = ["", 20, 20, 1]
        cache.character_data[0].target_character_id = id_dict["d102"]
        mother.target_character_id = id_dict["d102"]
        # 玩家正在搬运她、以她为助理（她开着一项助理服务）；母亲的群交部位模板 A 的嘴、模板 B 的阴茎侍奉里有她（B 里还有玩家）
        player = cache.character_data[0]
        player.action_info.carry_chara_id = id_dict["d102"]
        player.assistant_character_id = id_dict["d102"]
        child.assistant_services[min(child.assistant_services)] = 1
        mother.h_state.group_sex_body_template_dict["A"][0]["mouth"] = [id_dict["d102"], 5]
        mother.h_state.group_sex_body_template_dict["B"][1] = [[id_dict["d102"], 0], 3]
        # 其他结构里对她的引用：时停自由活动、装袋、交互中、拒绝群交名单、收藏品、冷库、囚犯、外勤、实操课必修、体检、借书、场景面板
        child_id = id_dict["d102"]
        player.pl_ability.free_in_time_stop_chara_id = child_id
        player.sp_flag.bagging_chara_id = child_id
        child.sp_flag.be_bagged = True
        mother.action_info.interacting_character_end_info = [child_id, cache.game_time]
        player.action_info.ask_group_sex_refuse_chara_id_list = [child_id, mother_id]
        player.pl_collection.first_panties[child_id] = "测试"
        player.pl_collection.npc_panties[child_id] = ["测试"]
        player.pl_collection.npc_socks[child_id] = ["测试"]
        player.pl_collection.milk_total[child_id] = 30
        player.pl_collection.urine_total[child_id] = 20
        island = cache.rhodes_island
        island.milk_in_fridge[child_id] = 30
        island.urine_in_fridge[child_id] = 10
        island.current_prisoners[child_id] = [cache.game_time, 0]
        child.sp_flag.imprisonment = True
        commission_id = min(game_config.config_commission)
        island.ongoing_field_commissions[commission_id] = [[child_id, mother_id], cache.game_time, []]
        child.sp_flag.field_commission = commission_id
        island.temp_sex_class["1-1"] = {"classroom": "理论教室一", "ability_id": 70, "must_attend": [child_id, mother_id], "notified": [False, False, False], "running": False}
        island.examined_operator_ids.add(child_id)
        island.waiting_for_exam_operator_ids.add(child_id)
        island.manually_selected_exam_operator_ids.add(child_id)
        island.today_physical_examination_chara_id_dict[child_id] = {1}
        book_id = min(game_config.config_book)
        island.book_borrow_dict[book_id] = child_id
        child.entertainment.borrow_book_id_set = {book_id}
        cache.old_character_id = child_id
        # 玩家与她在单人H中（双方都在H、玩家所在房间关着门，她脱了一件衣服），母亲正对她做着别的行为；
        #    她身上有快感、催眠、待触发事件与必须结算的二段行为
        player.sp_flag.is_h = True
        player.h_state.insert_position = 2
        cache.scene_data[map_handle.get_map_system_path_str_for_list(player.position)].close_flag = 1
        clothing_type = min(game_config.config_clothing_type)
        child.cloth.cloth_wear[clothing_type] = []
        child.cloth.cloth_off[clothing_type] = [min(game_config.config_clothing_tem)]
        mother.behavior.behavior_id = "wait"
        pleasure_state = min(state_id for state_id, state in game_config.config_character_state.items() if state.type == 0)
        child.status_data[pleasure_state] = 500
        child.hypnosis.hypnosis_degree = 50
        child.event.event_id = "test_event"
        child.must_settle_second_behavior_id_list = ["test_second_behavior"]
        id_dict["cloth"] = (clothing_type, min(game_config.config_clothing_tem))
        id_dict["pleasure_state"] = pleasure_state
        id_dict["commission"] = commission_id
        id_dict["book"] = book_id
        child.behavior.behavior_id = "follow_mother"
        child.state = 231
        child.target_character_id = mother_id
        child.entertainment.entertainment_type = [FOLLOW_MOTHER_ENTERTAINMENT, FOLLOW_MOTHER_ENTERTAINMENT, 0]
        child.child_growth.follow_mother_flag = True
        child.child_growth.selected_course = {0: {0: [0, "理论教室一"]}}
        child.child_growth.schedule_template_id = 1
        child.child_growth.schedule_override = {0: FOLLOW_MOTHER_ENTERTAINMENT}
        child.child_growth.skip_class_flag = True
        child.child_growth.skip_class_day = cache.game_time.toordinal()
        cache.rhodes_island.child_schedule_template[1] = {"name": "测试日程", "slot": {0: FOLLOW_MOTHER_ENTERTAINMENT, 1: MISSING_ENTERTAINMENT, 2: 0}}
        # 103的学员：未初潮、未成年、在见学，有课表；毕业的女儿：有听课与成绩单记录
        student = cache.character_data[id_dict["d103"]]
        student.talent[6] = 1
        student.child_growth.follow_mother_flag = True
        student.child_growth.selected_course = {1: {2: [0, "理论教室一"], 3: [4, MISSING_ENTERTAINMENT]}}
        # 103的学员与一名静态干员身上有配置表里没有的娱乐（含兴趣课的目标）与行为；毕业的女儿的娱乐槽位里有改编号前的旧编号176
        graduate_entertainment = cache.character_data[id_dict["d104"]].entertainment
        graduate_entertainment.entertainment_type = [176, 0, 0]
        student.entertainment.entertainment_type = [MISSING_ENTERTAINMENT, 0, 0]
        student.child_growth.schedule_override = {1: MISSING_ENTERTAINMENT}
        cache.character_data[minor_id].behavior.behavior_id = MISSING_BEHAVIOR
        graduate = cache.character_data[id_dict["d104"]]
        graduate.child_growth.attend_class_count = 30
        graduate.child_growth.report_card_history = [{"semester": [2020, 6]}]
        # 101的婴儿：有污浊、H状态与身体道具、H标记与后续链、泌乳、妊娠与卵；母亲在产后、育儿、泌乳
        baby = cache.character_data[id_dict["d101"]]
        body_part = min(game_config.config_body_part)
        clothing_type = min(game_config.config_clothing_type)
        baby.dirty.body_semen[body_part] = ["", 50, 50, 1]
        baby.dirty.cloth_semen[clothing_type] = ["", 50, 50, 1]
        baby.dirty.cloth_locker_semen[clothing_type] = ["", 50, 50, 1]
        baby.h_state.body_item[min(game_config.config_body_item)] = ["", True, None]
        baby.h_state.orgasm_count[min(state_id for state_id, state in game_config.config_character_state.items() if state.type == 0)] = [3, 3]
        baby.sp_flag.is_h = True
        baby.sp_flag.milk = 1
        baby.sp_flag.masturebate = 1
        baby.sp_flag.go_to_join_group_sex = True
        baby.target_character_id = 0
        for talent_id in (20, 21, 27):
            baby.talent[talent_id] = 1
        baby.pregnancy.milk = 50
        baby.pregnancy.lactation_flag = True
        baby.pregnancy.fertilization_rate = 30
        baby.pregnancy.eggs = {0: {"identified": False, "fertilized": True}}
        baby.pregnancy.next_egg_id = 1
        collection = cache.character_data[0].pl_collection
        collection.held_eggs = {0: (id_dict["d101"], 0)}
        collection.soft_eggs = {0: {"mother_id": id_dict["d101"], "semen_count": 5.0}, 1: {"mother_id": mother_id, "semen_count": 5.0}}
        baby.pregnancy.born_time = cache.game_time
        id_dict["baby_born_time"] = cache.game_time
        mother = cache.character_data[mother_id]
        for talent_id in (23, 24, 27):
            mother.talent[talent_id] = 1
        mother.pregnancy.milk = 80
        id_dict["mother"] = mother_id
        return id_dict

    def _save_and_load(self):
        """
        写盘再读档
        Keyword arguments:
        无
        Return arguments:
        无
        """
        from Script.Core import save_handle

        save_handle.establish_save(SAVE_ID)
        self.assertTrue(save_handle.judge_save_file_exist(SAVE_ID), "存档应已写到盘上")
        save_handle.input_load_save(SAVE_ID)

    def _snapshot(self) -> dict:
        """
        记下本测试检查的全部数据
        Keyword arguments:
        无
        Return arguments:
        dict -- 角色id到数据的字典，外加世界设定、日程模板、玩家收藏品里的卵、当前干员列表、各场景的角色、各职业名单、
           罗德岛里的冷库、囚犯、外勤、实操课、体检与借书数据，以及场景面板记着的角色
        """
        collection = self.cache.character_data[0].pl_collection
        snapshot = {
            "world_setting": dict(self.cache.world_setting),
            "template": repr(self.cache.rhodes_island.child_schedule_template),
            "eggs": repr((collection.held_eggs, collection.soft_eggs)),
            "npc_id_got": sorted(self.cache.npc_id_got),
            "scene": {path: sorted(scene.character_list) for path, scene in self.cache.scene_data.items()},
            "work": {work_id: sorted(work_set) for work_id, work_set in self.cache.rhodes_island.all_work_npc_set.items()},
            "island": repr([getattr(self.cache.rhodes_island, name) for name in (
                "milk_in_fridge", "urine_in_fridge", "current_prisoners", "ongoing_field_commissions", "temp_sex_class", "examined_operator_ids",
                "waiting_for_exam_operator_ids", "manually_selected_exam_operator_ids", "today_physical_examination_chara_id_dict", "book_borrow_dict")]),
            "old_character_id": self.cache.old_character_id,
        }
        for cid, chara in self.cache.character_data.items():
            growth = chara.child_growth
            snapshot[cid] = (
                dict(chara.talent),
                dict(chara.item),
                chara.behavior.behavior_id,
                chara.state,
                list(chara.entertainment.entertainment_type),
                list(chara.position),
                chara.target_character_id,
                chara.action_info.carry_chara_id,
                repr((chara.cloth.cloth_wear, chara.cloth.cloth_off, chara.hypnosis.hypnosis_degree, chara.event.event_id, chara.must_settle_second_behavior_id_list, sorted(chara.status_data.items()))),
                chara.assistant_character_id,
                dict(chara.assistant_services),
                repr((chara.pl_ability.free_in_time_stop_chara_id, chara.sp_flag.bagging_chara_id, chara.sp_flag.be_bagged, chara.action_info.interacting_character_end_info[0], chara.action_info.ask_group_sex_refuse_chara_id_list)),
                repr([sorted(getattr(chara.pl_collection, name).items()) for name in ("first_panties", "npc_panties", "npc_socks", "milk_total", "urine_total")]),
                chara.work.work_type,
                chara.dormitory,
                None if growth is None else repr(sorted(vars(growth).items())),
                repr([sorted(vars(part).items()) for part in (chara.dirty, chara.h_state, chara.sp_flag, chara.pregnancy)]),
            )
        return snapshot

    def _assert_converted(self, id_dict: dict):
        """
        检查读档后的数据
        Keyword arguments:
        id_dict -- _build_old_save 返回的角色id
        Return arguments:
        无
        """
        from Script.Config import game_config

        cache = self.cache
        self.assertEqual(cache.world_setting.get(1, 0), 0, "世界设定1应已关闭")
        for cid, chara in cache.character_data.items():
            stage_list = [talent_id for talent_id in STAGE_TALENT_TUPLE if chara.talent.get(talent_id, 0)]
            body_list = [talent_id for talent_id in BODY_TALENT_TUPLE if chara.talent.get(talent_id, 0)]
            self.assertFalse(chara.item.get(31, 0) or chara.item.get(32, 0), f"角色{cid}的道具栏里不应有外表年龄药")
            self.assertFalse(chara.child_growth is not None and chara.child_growth.follow_mother_flag, f"角色{cid}不应在见学")
            self.assertNotEqual(chara.behavior.behavior_id, "follow_mother", f"角色{cid}的行为不应是跟随母亲")
            for value in chara.entertainment.entertainment_type:
                self.assertIn(value, game_config.config_entertainment, f"角色{cid}的娱乐槽位{value}应在 Entertainment.csv 里")
            if cid == 0:
                continue
            if chara.relationship.father_id == 0:
                continue
            self.assertEqual(stage_list, [], f"静态干员{cid}不应持有成长阶段")
            self.assertFalse(chara.talent.get(6, 0) or chara.talent.get(7, 0), f"静态干员{cid}不应持有未初潮或未成年")
            if cid in id_dict["shrunk"]:
                self.assertEqual(body_list, self._template_body(chara.adv) or [104], f"世界设定1缩小的静态干员{cid}应取回模板的体型，模板没有体型时为少女")
        self.assertEqual(self._template_body(cache.character_data[id_dict["shrink"]].adv), [t for t in BODY_TALENT_TUPLE if cache.character_data[id_dict["shrink"]].talent.get(t, 0)], "世界设定1缩小的干员应取回模板的体型")
        self.assertEqual([t for t in BODY_TALENT_TUPLE if cache.character_data[id_dict["minor"]].talent.get(t, 0)], [104], "持有103的静态干员应持有少女")
        for stage in (101, 102, 103):
            daughter = cache.character_data[id_dict[f"d{stage}"]]
            self.assertEqual([t for t in STAGE_TALENT_TUPLE if daughter.talent.get(t, 0)], [stage], f"{stage}阶段的女儿应保留成长阶段")
            minor_talent = [daughter.talent.get(6, 0), daughter.talent.get(7, 0)]
            self.assertEqual(minor_talent, [0, 0] if stage == 103 else [1, 1], f"{stage}阶段的女儿的未初潮与未成年：103去掉，101/102保留")
        graduate = cache.character_data[id_dict["d104"]]
        self.assertEqual(([t for t in STAGE_TALENT_TUPLE if graduate.talent.get(t, 0)], graduate.talent.get(104, 0)), ([], 1), "毕业的女儿保持少女")
        self.assertEqual((graduate.child_growth.attend_class_count, graduate.child_growth.report_card_history), (30, [{"semester": [2020, 6]}]), "毕业的女儿的养成记录保持原样")
        child = cache.character_data[id_dict["d102"]]
        self.assertEqual((child.behavior.behavior_id, child.state), ("share_blankly", 0), "102的孩子应在发呆")
        growth = child.child_growth
        self.assertEqual((growth.selected_course, growth.schedule_template_id, growth.schedule_override, growth.skip_class_flag, growth.skip_class_day), ({}, 0, {}, False, 0), "102的孩子应没有课表、日程与翘课标记")
        student = cache.character_data[id_dict["d103"]]
        self.assertEqual(student.child_growth.selected_course, {1: {2: [0, "理论教室一"]}}, "103的学员保留课表，目标不在娱乐表里的兴趣课删掉")
        self.assertEqual((student.entertainment.entertainment_type, student.child_growth.schedule_override), ([0, 0, 0], {}), "表里没有的娱乐：槽位换成0，单项覆盖删掉")
        self.assertEqual(cache.character_data[id_dict["minor"]].behavior.behavior_id, "share_blankly", "表里没有的行为换成发呆")
        self.assertEqual(cache.rhodes_island.child_schedule_template[1]["slot"][1], 0, "日程模板里表里没有的娱乐换成0")
        baby = cache.character_data[id_dict["d101"]]
        for semen_table in (baby.dirty.body_semen, baby.dirty.cloth_semen, baby.dirty.cloth_locker_semen):
            self.assertEqual([key for key, semen_list in semen_table.items() if any(semen_list[1:])], [], "101的婴儿身上与服装上没有精液")
        self.assertEqual([key for key, item_data in baby.h_state.body_item.items() if item_data[1]], [], "101的婴儿没有在用的身体道具")
        self.assertEqual([key for key, count in baby.h_state.orgasm_count.items() if count != [0, 0]], [], "101的婴儿没有绝顶记录")
        self.assertEqual((baby.sp_flag.is_h, baby.sp_flag.milk, baby.sp_flag.masturebate, baby.sp_flag.go_to_join_group_sex), (False, 0, 0, False), "101的婴儿没有H标记与后续链")
        self.assertEqual([talent_id for talent_id in (20, 21, 22, 23, 24, 25, 26, 27, 32, 35) if baby.talent.get(talent_id, 0)], [], "101的婴儿没有妊娠与泌乳素质")
        self.assertEqual((baby.pregnancy.milk, baby.pregnancy.lactation_flag, baby.pregnancy.fertilization_rate, baby.pregnancy.eggs, baby.pregnancy.next_egg_id), (0, False, 0, {}, 0), "101的婴儿没有奶、受精率与卵")
        self.assertEqual(baby.pregnancy.born_time, id_dict["baby_born_time"], "101的婴儿保留出生时间")
        from Script.System.Education_System import growth_handle

        for stage in (101, 102):
            child_id = id_dict[f"d{stage}"]
            child = cache.character_data[child_id]
            self.assertEqual((child.work.work_type, child.dormitory, child.permanent_dormitory), (0, "", ""), f"{stage}的孩子没有职业、没有宿舍")
            self.assertEqual([work_id for work_id, work_set in cache.rhodes_island.all_work_npc_set.items() if child_id in work_set], [], f"{stage}的孩子不在任何职业名单里")
            self.assertNotIn(child_id, growth_handle.get_student_candidate_list() + growth_handle.get_course_candidate_list(), f"{stage}的孩子不在养成与课表的学生名单里")
            self.assertEqual([path for path, scene in cache.scene_data.items() if child_id in scene.character_list], [], f"{stage}的孩子不在任何场景里")
            self.assertNotIn(child_id, cache.npc_id_got, f"{stage}的孩子不在当前干员列表里")
            self.assertEqual((child.position, child.sp_flag.is_follow, child.target_character_id), (["0", "0"], 0, child_id), f"{stage}的孩子的位置、跟随与目标都不指向场景或别人")
            self.assertEqual([cid for cid, chara in cache.character_data.items() if cid != child_id and chara.target_character_id == child_id], [], f"没有角色以{stage}的孩子为目标")
        player = cache.character_data[0]
        template_dict = cache.character_data[id_dict["mother"]].h_state.group_sex_body_template_dict
        self.assertEqual(
            (player.action_info.carry_chara_id, player.assistant_character_id, template_dict["A"][0]["mouth"], template_dict["B"][1]),
            (0, 0, [-1, -1], [[0], 3]),
            "玩家没有在搬运102的孩子，她不是助理，母亲的群交部位模板里没有她，玩家留在阴茎侍奉里",
        )
        from Script.Design import child_stage_gate

        child_id_set = {id_dict["d101"], id_dict["d102"]}
        self.assertEqual([cid for cid in cache.character_data if cid not in child_id_set and child_stage_gate.involves_child_stage(cid)], [], "读档后幼年阶段的H闸找不到以孩子为交互对象的角色")
        child = cache.character_data[id_dict["d102"]]
        self.assertEqual([key for key, value in child.assistant_services.items() if value], [], "102的孩子没有开着的助理服务")
        self._assert_no_child_reference(id_dict)
        self._assert_h_session_ended(id_dict)
        self.assertEqual((child.sp_flag.is_h, [key for key, semen_list in child.dirty.body_semen.items() if any(semen_list[1:])]), (False, []), "102的孩子没有H标记与精液")
        collection = cache.character_data[0].pl_collection
        self.assertEqual((collection.held_eggs, [egg["mother_id"] for egg in collection.soft_eggs.values()]), ({}, [id_dict["mother"]]), "玩家收藏品里没有101婴儿的卵，母亲的体外卵保留")
        mother = cache.character_data[id_dict["mother"]]
        self.assertEqual(([mother.talent.get(talent_id, 0) for talent_id in (23, 24, 27)], mother.pregnancy.milk), ([1, 1, 1], 80), "母亲的产后、育儿与泌乳保持原样")
        for value in cache.rhodes_island.child_schedule_template[1]["slot"].values():
            self.assertTrue(value == 0 or value in game_config.config_entertainment, f"日程模板的时段{value}应是自由选择或 Entertainment.csv 里的娱乐")

    def _assert_no_child_reference(self, id_dict: dict):
        """
        检查其他结构里没有对102孩子的引用，与她并列的母亲的条目保留
        Keyword arguments:
        id_dict -- _build_old_save 返回的角色id
        Return arguments:
        无
        """
        cache = self.cache
        child_id = id_dict["d102"]
        mother_id = id_dict["mother"]
        child = cache.character_data[child_id]
        player = cache.character_data[0]
        island = cache.rhodes_island
        collection = player.pl_collection
        self.assertEqual((player.pl_ability.free_in_time_stop_chara_id, player.sp_flag.bagging_chara_id, child.sp_flag.be_bagged), (0, 0, False), "没有以孩子为时停自由活动或装袋的对象")
        self.assertEqual(cache.character_data[mother_id].action_info.interacting_character_end_info[0], -1, "母亲的交互中对象不是孩子")
        self.assertEqual(player.action_info.ask_group_sex_refuse_chara_id_list, [mother_id], "拒绝群交名单里没有孩子，母亲保留")
        self.assertEqual(
            (collection.first_panties.get(child_id, ""), collection.npc_panties.get(child_id, []), collection.npc_socks.get(child_id, []), collection.milk_total.get(child_id, 0), collection.urine_total.get(child_id, 0)),
            ("", [], [], 0, 0),
            "玩家收藏品里没有孩子的胖次、袜子、乳汁与圣水",
        )
        self.assertEqual(
            [child_id in one for one in (island.milk_in_fridge, island.urine_in_fridge, island.current_prisoners, island.today_physical_examination_chara_id_dict, island.examined_operator_ids, island.waiting_for_exam_operator_ids, island.manually_selected_exam_operator_ids)],
            [False] * 7,
            "冷库、囚犯与体检名单里没有孩子",
        )
        self.assertEqual((child.sp_flag.imprisonment, child.sp_flag.field_commission), (False, 0), "孩子不在监禁与外勤中")
        self.assertEqual((island.ongoing_field_commissions[id_dict["commission"]][0], island.temp_sex_class["1-1"]["must_attend"]), ([mother_id], [mother_id]), "外勤委托与实操课必修名单里没有孩子，母亲保留")
        self.assertEqual((island.book_borrow_dict[id_dict["book"]], child.entertainment.borrow_book_id_set, cache.old_character_id), (-1, set(), 0), "孩子借的书还回去，场景面板记着的角色不是她")

    def _assert_h_session_ended(self, id_dict: dict):
        """
        检查与102孩子的单人H已按结束H收尾：玩家不在H中、交互对象是自己、插入位置复位、房门打开；
           孩子穿回衣服，快感、催眠、待触发事件与必须结算的二段行为归零；母亲对她的行为换成发呆
        Keyword arguments:
        id_dict -- _build_old_save 返回的角色id
        Return arguments:
        无
        """
        from Script.Design import map_handle

        cache = self.cache
        player = cache.character_data[0]
        child = cache.character_data[id_dict["d102"]]
        mother = cache.character_data[id_dict["mother"]]
        clothing_type, cloth_id = id_dict["cloth"]
        self.assertEqual((player.sp_flag.is_h, player.target_character_id, player.h_state.insert_position, player.sp_flag.hidden_sex_mode), (False, 0, -1, 0), "玩家已结束H，交互对象是自己")
        self.assertEqual(cache.scene_data[map_handle.get_map_system_path_str_for_list(player.position)].close_flag, 0, "结束H后房门打开")
        self.assertEqual((child.sp_flag.is_h, child.cloth.cloth_off[clothing_type], cloth_id in child.cloth.cloth_wear[clothing_type]), (False, [], True), "孩子不在H中，穿回了脱下的衣服")
        self.assertEqual(
            (child.status_data[id_dict["pleasure_state"]], child.hypnosis.hypnosis_degree, child.event.event_id, child.must_settle_second_behavior_id_list),
            (0, 0, "", []),
            "孩子的快感、催眠、待触发事件与必须结算的二段行为归零",
        )
        self.assertEqual((mother.behavior.behavior_id, mother.target_character_id), ("share_blankly", id_dict["mother"]), "母亲对孩子的行为换成发呆")

    def test_old_save_converts_once(self):
        """
        旧存档读档后符合现行规则；再写盘读档一次，数据不变
        Keyword arguments:
        无
        Return arguments:
        无
        """
        id_dict = self._build_old_save()
        self._save_and_load()
        self._assert_converted(id_dict)
        first = self._snapshot()
        self._save_and_load()
        self._assert_converted(id_dict)
        self.assertEqual(self._snapshot(), first, "第二次读档不应改动任何被检查的数据")

    def test_stage_without_world_setting(self):
        """
        没开世界设定1时，持有103的静态干员读档后持有少女，不取模板的体型
        Keyword arguments:
        无
        Return arguments:
        无
        """
        cache = self.cache
        cache.world_setting[1] = 0
        static_id_list = [cid for cid, chara in cache.character_data.items() if cid != 0 and chara.relationship.father_id != 0]
        operator_id = min(cid for cid in static_id_list if self._template_body(cache.character_data[cid].adv) in ([105], [106]))
        talent = cache.character_data[operator_id].talent
        for talent_id in BODY_TALENT_TUPLE:
            talent[talent_id] = 0
        talent[103] = 1
        self._save_and_load()
        talent = cache.character_data[operator_id].talent
        self.assertEqual([t for t in STAGE_TALENT_TUPLE + BODY_TALENT_TUPLE if talent.get(t, 0)], [104], "没开世界设定1时持有103的静态干员应只持有少女")

    def _group_h_case(self, child_in_template: bool):
        """
        摆出群交中的旧存档并检查读档：玩家、102的孩子与另一名干员同场景在群交；
           读档后群交按群交结束收尾，三人有效的交互对象，再写盘读档一次，数据不变
        Keyword arguments:
        child_in_template -- True：玩家以孩子为交互对象，孩子在玩家的部位模板里；False：玩家以那名干员为交互对象，没有模板写着孩子
        Return arguments:
        无
        """
        from Script.Design import map_handle

        cache = self.cache
        player = cache.character_data[0]
        static_id_list = sorted(cid for cid in cache.npc_id_got if cid != 0 and cache.character_data[cid].relationship.father_id != 0)
        mother_id, other_id = static_id_list[0], static_id_list[1]
        child_id = self._daughter(mother_id, "测试女儿群交", 102)
        for character_id in (child_id, other_id):
            map_handle.character_move_scene(cache.character_data[character_id].position, player.position, character_id)
        cache.npc_id_got.add(child_id)
        cache.group_sex_mode = True
        player.sp_flag.is_h = True
        for character_id in (child_id, other_id):
            cache.character_data[character_id].sp_flag.is_h = True
            cache.character_data[character_id].target_character_id = 0
        player.h_state.group_sex_body_template_dict["A"][0]["L_hand"] = [other_id, 5]
        if child_in_template:
            player.target_character_id = child_id
            player.h_state.group_sex_body_template_dict["A"][0]["mouth"] = [child_id, 5]
            player.h_state.group_sex_body_template_dict["B"][1] = [[child_id, other_id], 3]
        else:
            player.target_character_id = other_id
        player.h_state.insert_position = 2
        scene_path = map_handle.get_map_system_path_str_for_list(player.position)
        self.assertTrue({0, child_id, other_id} <= set(cache.scene_data[scene_path].character_list), "存档前三人同场景")
        snapshot_list = []
        for _ in range(2):
            self._save_and_load()
            self.assertFalse(cache.group_sex_mode, "群交模式已关闭")
            for character_id in (0, child_id, other_id):
                chara = cache.character_data[character_id]
                self.assertFalse(chara.sp_flag.is_h, f"角色{character_id}不在H中")
                self.assertIn(chara.target_character_id, cache.character_data, f"角色{character_id}的交互对象是存在的角色")
                if character_id != child_id:
                    self.assertNotEqual(chara.target_character_id, child_id, f"角色{character_id}的交互对象不是孩子")
                template_id_list = [part[0] for template in chara.h_state.group_sex_body_template_dict.values() for part in template[0].values()] + [one for template in chara.h_state.group_sex_body_template_dict.values() for one in template[1][0]]
                self.assertEqual(set(template_id_list), {-1}, f"角色{character_id}的群交部位模板已清空")
            loaded_player = cache.character_data[0]
            self.assertEqual((loaded_player.h_state.insert_position, loaded_player.target_character_id), (-1, 0 if child_in_template else other_id), "玩家的插入位置复位，交互对象有效")
            self.assertNotIn(child_id, cache.scene_data[scene_path].character_list, "孩子离开了场景")
            snapshot_list.append(self._snapshot())
        self.assertEqual(snapshot_list[0], snapshot_list[1], "第二次读档不应改动任何被检查的数据")

    def test_group_h_with_child_ends(self):
        """
        群交中玩家以102的孩子为交互对象、孩子在部位模板里：读档后群交结束
        Keyword arguments:
        无
        Return arguments:
        无
        """
        self._group_h_case(True)

    def test_group_h_child_not_in_template_ends(self):
        """
        群交中孩子与玩家同场景在H中，玩家以另一名干员为交互对象，没有部位模板写着孩子：读档后群交同样结束
        Keyword arguments:
        无
        Return arguments:
        无
        """
        self._group_h_case(False)
