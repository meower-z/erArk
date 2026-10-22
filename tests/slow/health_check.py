# -*- coding: UTF-8 -*-
"""
体检测试的共用场景
==================
开新游戏后，博士走进体检科，打开「身体检查与管理」面板，在「调整体检日程」里开启每天的定期体检，体检对象只有手动名单上的一名干员；
博士晚上回博士房间睡觉，午夜抽签必然抽中她，排在上午（9:00~12:00）或下午（14:00~18:00）时段。
体检科要医疗部升到 2 级才开放，这里按已开放处理。
"""
from tests.slow.base import SlowTestCase

EXAM_ROOM = ["医疗", "体检科"]
DR_OFFICE = ["中枢", "博士办公室"]
DR_ROOM = ["中枢", "博士房间"]
SLOT_START = {1: 9, 2: 14}
""" 今日体检时间（1 上午，2 下午）: 时段开始的整点 """
MOVE_TO_EXAM = 662
""" 状态机「移动至体检科」（constant.StateMachine.MOVE_TO_PHYSICAL_EXAMINATION） """


class HealthCheckTestCase(SlowTestCase):
    """体检测试的基类：排体检、博士睡过午夜、记录干员选出的行动、招募干员坐满体检科"""

    def book_daily_exam(self, name: str) -> int:
        """
        经「身体检查与管理」面板给一名干员排每天的体检，然后博士回到博士办公室
        Keyword arguments:
        name -- 干员名字
        Return arguments:
        int -- 她的角色id
        功能描述:
            「调整体检日程」里依次点：定期体检「否」改「是」；周期「每年」点到「每天」；对象「源石病患者干员」点到「手动选择干员名单」；
            「调整干员名单」里选中她。设置都在面板的选项里。
        """
        from Script.Config import game_config
        from Script.Core import constant

        cid = self.npc(name)
        scene_name = self.world.scene(EXAM_ROOM).scene_name
        self.cache.rhodes_island.facility_open[game_config.config_facility_open_name_to_cid[scene_name]] = 1
        self.walk(EXAM_ROOM)
        self.world.player.press("调整体检日程", "否", "每年体检一次", "每月体检一次", "每周体检一次", "源石病患者干员", "全部干员", "调整干员名单", name, "返回", "返回", "返回")
        self.instruct(constant.Instruct.PHYSICAL_CHECK_AND_MANAGE)
        self.show_panel()
        self.world.player.check_done()
        setting = self.cache.rhodes_island.physical_examination_setting
        self.assertEqual((setting[2], setting[3], setting[4]), (1, 3, 2), "定期体检、每天、手动名单")
        self.assertEqual(self.cache.rhodes_island.manually_selected_exam_operator_ids, {cid})
        self.walk(DR_OFFICE)
        return cid

    def sleep_through_midnight(self):
        """
        博士 23:00 回博士房间睡 8 小时，午夜结算（含体检抽签）在睡眠中进行；醒来后回博士办公室
        Keyword arguments:
        无
        Return arguments:
        无
        """
        from Script.Core import constant

        today = self.cache.game_time.day
        self.wait_until_hour(23)
        self.walk(DR_ROOM)
        self.world.player.press("8小时", "确定")
        self.instruct(constant.Instruct.SLEEP)
        self.show_panel()
        self.world.player.check_done()
        self.assertNotEqual(self.cache.game_time.day, today, "博士睡过了午夜")
        self.walk(DR_OFFICE)

    def wait_until_hour(self, hour: int):
        """
        用「等待五分钟」推进到当天的某个整点之后
        Keyword arguments:
        hour -- 整点
        Return arguments:
        无
        """
        self.assertTrue(self.wait_until(lambda: self.cache.game_time.hour >= hour, 24 * 60))

    def record_picks(self, cid: int) -> list:
        """
        之后该角色每次执行状态机（constant.handle_state_machine_data 中的函数，AI 选出行动后调用它），都记下 (她的行为开始时间, 状态机id)
        Keyword arguments:
        cid -- 角色id
        Return arguments:
        list -- 记录列表，按执行顺序追加
        """
        from Script.Core import constant

        picks = []
        character_data = self.cache.character_data[cid]

        def recorder(state_machine_id, run):
            """
            包装一个状态机：记下该角色的执行，照常运行
            Keyword arguments:
            state_machine_id -- 状态机id
            run -- 原状态机函数
            Return arguments:
            function -- 包装后的状态机函数
            """

            def wrapped(character_id):
                """
                记录型状态机
                Keyword arguments:
                character_id -- 执行的角色id
                Return arguments:
                无
                """
                if character_id == cid:
                    picks.append((character_data.behavior.start_time, state_machine_id))
                run(character_id)

            return wrapped

        for state_machine_id, run in list(constant.handle_state_machine_data.items()):
            constant.handle_state_machine_data[state_machine_id] = recorder(state_machine_id, run)
        return picks

    def fill_exam_room(self) -> list:
        """
        招募 10 名新干员并把她们带进体检科：新干员原地等待 30 分钟，这段时间里体检科（Room_Area 0，上限 10 人）满员
        Keyword arguments:
        无
        Return arguments:
        list -- 新干员的角色id
        """
        from Script.Design import character_handle, map_handle

        recruits = sorted(cid for cid in self.cache.character_data if cid and cid not in self.cache.npc_id_got)[:10]
        for cid in recruits:
            character_handle.get_new_character(cid)
            self.world.move(cid, EXAM_ROOM)
        self.assertTrue(map_handle.judge_scene_is_full(map_handle.get_map_system_path_str_for_list(EXAM_ROOM)))
        return recruits
