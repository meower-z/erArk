"""
怀孕总览服务测试
================
验证怀孕总览服务的阶段判定、关键时间文本、胎数后缀与总览行排序筛选规则。
验证页签显隐、角色存活检查、疑似误入女儿统计文案及移除后的中心编号更新。
在拦截 Script.UI 与 Script.Settle 的子进程中运行服务入口以确认无受限导入。
"""

from Script.Config import game_config
from Script.System.Pregnancy_System import pregnancy_constant as P
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ChildRun, run_ui_free

SCENARIO = """
import contextlib, io
from Script.Config import map_config
with contextlib.redirect_stdout(io.StringIO()):
    map_config.init_map_data()
from Script.Core import constant
from Script.Design import attr_calculation, game_time, map_handle
from Script.Kernel import core
from Script.Modules.domains import abilities, identity, player_collection
from Script.Modules.domains import pregnancy, relations, roster, status
from Script.Modules.gameplay_resolution import working
from Script.Modules.gameplay_resolution import pregnancy_overview_service as svc
from Script.Modules.save_load import kernel_state
from Script.System.Pregnancy_System import egg_handle
from Script.System.Pregnancy_System import pregnancy_constant as P
core.reset_state(core.GameState(kernel_state.first_clock(), {}, {}))
out = payload
NAMES = {0: "Doc", 201: "baby", 301: "lost1", 302: "lost2", 303: "kept"}
TALENTS = {
    101: (20,), 102: (21,), 106: (22,), 107: (23,), 108: (24,), 109: (24,),
    111: (20, 21), 112: (24,), 201: (101,), 301: (104,),
}
with working.based_on(core.state()):
    now = game_time.now()
    ago = lambda day: game_time.get_sub_date(day=-day, old_date=now)
    fmt = P.format_season_date
    due = lambda day, start: fmt(game_time.get_predict_date(day, start))
    for cid in (0, *range(101, 114), 201, 301, 302, 303):
        identity.put(identity.Identity(cid, name=NAMES.get(cid, f"c{cid}"), sex=1))
        abilities.talent(cid).replace(attr_calculation.get_talent_zero({}))
        status.replace(cid, attr_calculation.get_status_zero({}))
        for talent_id in TALENTS.get(cid, ()):
            abilities.talent(cid)[talent_id] = 1
        if cid and cid != 201:
            roster.add(cid)
    pregnancy.update(101, fertilization_time=ago(3), acceleration_days=4.9)
    pregnancy.update(102, fertilization_time=ago(10), fetus_count=3, acceleration_days=10.7)
    pregnancy.update(106, fetus_count=2, identical_twins=True)
    pregnancy.update(111, fertilization_time=ago(200), fetus_count=2)
    held_id = [egg_handle.add_egg(103, True) for n in range(2)][1]
    with pregnancy.editing(103) as preg:
        preg.eggs[held_id]["held_by_player"] = True
    only_held = egg_handle.add_egg(113, False)
    with pregnancy.editing(113) as preg:
        preg.eggs[only_held]["held_by_player"] = True
    hatch_ids = []
    for lay_day, acc in ((20, 5.6), (5, 0.0)):
        hatch_ids.append(egg_handle.add_egg(105, True))
        with pregnancy.editing(105) as preg:
            preg.eggs[hatch_ids[-1]].update(identified=True, lay_time=ago(lay_day), acceleration_days=acc)
    egg_handle.add_egg(112, False)
    scene = sorted(constant.scene_data)[0]
    position = map_handle.get_map_system_path_for_str(scene)
    player_collection.add_soft_egg(104, now, position, 120.6)
    player_collection.add_soft_egg(104, game_time.get_sub_date(hour=-2, old_date=now), position, 0)
    pregnancy.update(201, born_time=ago(4), growth_acceleration_days=2.5)
    relations.mother_id.set(201, 108)
    relations.child_id_list.set(108, [201])
    for cid in (301, 302, 303):
        relations.father_id.set(cid, 0)
    relations.mother_id.set(301, 102)
    relations.mother_id.set(302, 999)
    relations.child_id_list.set(0, [303])
    out["dates"] = {
        "f_start": fmt(ago(3)), "f_due": due(P.PREGNANCY_DAY - 4, ago(3)),
        "p_start": fmt(ago(10)), "p_due": due(P.PARTURIENT_DAY - 10, ago(10)),
        "x_start": fmt(ago(200)), "today": fmt(now),
        "hatch_due": due(P.HATCH_TOTAL_DAY - 5, ago(20)),
        "hatch_day": egg_handle.get_hatch_day(pregnancy.of(105).eggs[hatch_ids[0]]),
        "grow_due": due(P.REARING_COMPLETE_DAY - 2, ago(4)),
    }
    out["scene"] = constant.scene_data[scene].scene_name
    out["stages"] = {cid: svc.get_chara_pregnancy_stage(cid) for cid in (*range(101, 114), 0)}
    out["info"] = {cid: svc.get_stage_info_text(cid, out["stages"][cid]) for cid in range(101, 114)}
    out["fetus"] = [svc.get_fetus_count_text(cid) for cid in (101, 102, 106)]
    out["rows"] = {
        f"{flt}/{srt}": [list(row) for row in svc.overview_rows(flt, srt)]
        for flt, srt in ((0, 0), (0, 1), (P.STAGE_PREGNANCY, 0), (P.STAGE_HATCHING, 1))
    }
    out["sort"] = [svc.sort_button_text(0), svc.sort_button_text(1)]
    out["pages"] = [svc.page_names()]
    out["live"] = [svc.live_id(cid) for cid in (0, 101, 9999)]
    out["confirm"] = svc.remove_confirm_text(301)
    out["count"] = svc.abnormal_count_text()
    out["abnormal"] = [list(row) for row in svc.abnormal_rows()]
    out["remove"] = [
        svc.remove_abnormal(303, 303),
        svc.remove_abnormal(301, 301),
        svc.remove_abnormal(302, 101),
        svc.remove_abnormal(9999, 9999),
    ]
    out["after"] = [identity.exists(cid) for cid in (301, 302, 303)]
    out["pages"].append(svc.page_names())
    out["count_after"] = svc.abnormal_count_text()
"""
""" 在无界面子进程中构造测试数据并调用怀孕总览服务各公开入口的脚本。 """


class PregnancyOverviewServiceTest(FastTestCase):
    """怀孕总览服务的规则、文案与无界面导入隔离测试。"""

    child: ChildRun
    out: dict

    @classmethod
    def setUpClass(cls) -> None:
        """启动无界面子进程执行测试场景并保存运行结果与受限导入记录。"""
        cls.child = run_ui_free(SCENARIO, boot=True)
        cls.out = cls.child.payload

    def test_ui_free(self) -> None:
        """验证无界面子进程运行期间未加载也未尝试导入受限模块。"""
        self.assertEqual((self.child.loaded, self.child.attempted), ([], []))

    def test_stages(self) -> None:
        """验证各阶段判定结果及同时满足多项时按时间顺序取最靠后者的规则。"""
        stages = {int(cid): stage for cid, stage in self.out["stages"].items()}
        self.assertEqual(
            stages,
            {
                101: P.STAGE_FERTILIZATION,
                102: P.STAGE_PREGNANCY,
                103: P.STAGE_EGG_WAIT,
                104: P.STAGE_SOFT_EGG_WAIT,
                105: P.STAGE_HATCHING,
                106: P.STAGE_PARTURIENT,
                107: P.STAGE_POSTPARTUM,
                108: P.STAGE_REARING,
                109: P.STAGE_REARING,
                110: P.STAGE_NONE,
                111: P.STAGE_PREGNANCY,
                112: P.STAGE_REARING,
                113: P.STAGE_EGG_WAIT,
                0: P.STAGE_NONE,
            },
        )

    def test_stage_info(self) -> None:
        """验证各阶段关键时间说明、加速药整天扣除、到期兜底当天与胎数后缀文本。"""
        d = self.out["dates"]
        info = {int(cid): text for cid, text in self.out["info"].items()}
        scene = self.out["scene"]
        self.assertEqual(
            info,
            {
                101: f"受精于{d['f_start']}，预计{d['f_due']}妊娠",
                102: f"受精于{d['p_start']}，预计{d['p_due']}临盆（3胞胎）",
                103: "2枚卵待鉴定",
                104: f"待受精卵块：{scene}的卵块（120ml，60分钟后判定）、"
                f"{scene}的卵块（0ml，即将判定）",
                105: f"孵化第{d['hatch_day']}天，预计{d['hatch_due']}破壳",
                106: "已在住院区待产，预计近日生产（同卵双胞胎）",
                107: "生产完毕，正在住院区休养",
                108: f"正在育儿室照顾baby（预计{d['grow_due']}长大）",
                109: "育儿中",
                110: "",
                111: f"受精于{d['x_start']}，预计{d['today']}临盆（2胞胎）",
                112: "育儿中",
                113: "1枚卵待鉴定",
            },
        )
        self.assertEqual(self.out["fetus"], ["", "（3胞胎）", "（同卵双胞胎）"])

    def test_overview_rows(self) -> None:
        """验证总览列表的升降序排列、阶段筛选、行文本格式与排序按钮标签。"""
        rows = self.out["rows"]
        self.assertEqual(
            [row[0] for row in rows["0/0"]],
            [108, 109, 112, 107, 106, 105, 102, 111, 104, 103, 113, 101],
        )
        self.assertEqual(
            [row[0] for row in rows["0/1"]],
            [101, 103, 113, 104, 102, 111, 105, 106, 107, 108, 109, 112],
        )
        self.assertEqual([row[0] for row in rows["4/0"]], [102, 111])
        self.assertEqual(rows["5/1"], [[105, "c105", rows["0/0"][5][2]]])
        name = P.STAGE_NAME_LIST[P.STAGE_POSTPARTUM]
        self.assertEqual(
            rows["0/0"][3],
            [107, "c107", f"　{name}　　生产完毕，正在住院区休养"],
        )
        self.assertEqual(self.out["sort"], ["[按阶段降序▼]", "[按阶段升序▲]"])

    def test_abnormal_daughters(self) -> None:
        """验证页签显隐、存活编号检查、排查文案、移除行为及移除后计数与页签更新。"""
        self.assertEqual(
            self.out["pages"],
            [["总览", "生育谱系图", "异常女儿排查"], ["总览", "生育谱系图"]],
        )
        self.assertEqual(self.out["live"], [0, 101, 0])
        self.assertEqual(
            self.out["confirm"],
            "\n　确定要从本存档彻底移除女儿「lost1」（id:301）吗？\n　此操作不可撤销。\n",
        )
        self.assertEqual(
            self.out["count"],
            "　本存档共有 3 名博士女儿，其中 1 名在册（正常），2 名疑似误入：\n",
        )
        girl = game_config.config_talent[104].name
        self.assertEqual(
            self.out["abnormal"],
            [
                [301, f"　lost1（id:301）　母亲：c102　成长阶段：{girl}\n"],
                [302, "　lost2（id:302）　母亲：未知　成长阶段：成年\n"],
            ],
        )
        self.assertEqual(self.out["remove"], [303, 0, 101, 9999])
        self.assertEqual(self.out["after"], [False, False, True])
        self.assertEqual(
            self.out["count_after"],
            "　本存档共有 1 名博士女儿，其中 1 名在册（正常），0 名疑似误入：\n",
        )
