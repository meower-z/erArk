"""
群交邀请服务与无界面隔离测试
============================
验证群交邀请名单的同场、玩家、拒邀、疲劳与课堂入课门槛筛选规则。
验证发起邀请、取消邀请、无可用路径等待及各类拒邀与异常阻断结果。
验证独立子进程拦截 Script.UI 与 Script.Settle 时两个服务的公开函数及其主要分支正常运行。
"""

from typing import Any
from unittest import mock

from Script.Config import game_config
from Script.Core import constant
from Script.Design import handle_premise, instuct_judege
from Script.Kernel import core
from Script.Modules.domains import activity, flags, modes
from Script.Modules.gameplay_resolution import group_sex_editor_service as svc
from Script.Modules.gameplay_resolution import group_sex_invite_service as inv
from Script.Modules.gameplay_resolution import plan_queue, working
from Script.Modules.npc_action_choice import choice
from Script.System.Education_System import sex_class_handle
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import run_ui_free

NO_SERVE = [[-1], -1]
""" 侍奉槽位处于未选状态时的模板结构常量。 """
EMPTY = [-1, -1]
""" 对单部位槽位处于未选状态时的模板结构常量。 """
UI_FREE_RUN = """
from unittest import mock
from Script.Config import game_config, map_config
from Script.Core import constant
from Script.Design import attr_calculation, handle_premise, instuct_judege
from Script.Modules.domains import chara_life, flags, h_state, identity, modes
from Script.Modules.domains import relations, roster
from Script.Modules.gameplay_resolution import group_sex_editor_service as svc
from Script.Modules.gameplay_resolution import group_sex_invite_service as inv
from Script.Modules.gameplay_resolution import plan_queue
from Script.Modules.npc_action_choice import choice
from Script.System.Education_System import education_constant
from tests import chara_abilities, chara_data, kernel_data
from tests.chara_activity import place
from tests.world import DEFAULT_SCENE, STANDARD_OUTFIT, start_time
map_config.init_map_data()
kernel_data.reset_clock(start_time(), {})
for cid in range(6):
    kernel_data.put(identity.put, identity.Identity(cid, name=f"c{cid}", sex=1, adv=cid))
    chara_abilities.zero_tables(cid)
    chara_abilities.talent(cid)[121] = 1
    services = attr_calculation.get_assistant_services_zero()
    kernel_data.put(relations.assistant_services.set, cid, services)
    kernel_data.put(relations.favorability.set, cid, {0: 0})
    place(cid, DEFAULT_SCENE)
    chara_data.seed(cid, STANDARD_OUTFIT)
    if cid:
        kernel_data.put(roster.add, cid)
    kernel_data.set_needs(cid, hit=1000, hit_max=1000, sanity=1000, sanity_max=1000)
lists = game_config.config_behavior_id_list_of_group_sex_body_part
ids = {b: f"I_{b}" for part in lists.values() for b in part}
out = []
mark = plan_queue.mark()
with kernel_data.writing():
    modes.set_group_sex(True)
    out += [svc.info_text(0), svc.part_rows()]
    svc.set_target_chara("A", "mouth", 1)
    svc.set_status("A", "mouth", "kiss_h")
    for cid in (2, 3, 2, 3, 4, 5, 1, 2, 3):
        svc.set_target_chara("A", "侍奉", cid)
    svc.set_status("A", "侍奉", "handjob")
    out += [svc.info_text(0), svc.part_rows(), svc.controls()]
    out += [svc.target_choices("A", "mouth"), svc.target_choices("A", "侍奉")]
    with mock.patch.dict(constant.behavior_id_to_instruct_id, ids):
        out += [svc.status_choices("A", "mouth"), svc.status_choices("A", "侍奉")]
    out += [svc.status_choices("A", "penis")]
    for cid in (1, 2, 4):
        chara_life.work_type.set(cid, education_constant.STUDENT_WORK_TYPE)
        flags.set(cid, is_h=True)
    modes.set_sex_class(True)
    kernel_data.set_needs(4, hit=10)
    watch = svc.target_choices("A", "anal")
    payload["watch"] = [[c.cid, c.watch_only] for c in watch]
    kernel_data.set_needs(4, hit=1000)
    kernel_data.set_needs(2, hit=1)
    out += [watch, inv.invite_candidates([])]
    modes.set_sex_class(False)
    for flag in range(4):
        svc.change_npc_ai()
        svc.change_lock_flag()
        svc.change_b_temple_flag()
        out.append(svc.controls())
    svc.change_temple()
    svc.set_target_chara("A", "penis", 3)
    svc.change_b_temple_flag()
    svc.reset_unfinish_select()
    svc.reset_template()
    svc.set_status("A", "penis", "normal_sex")
    flags.set(4, go_to_join_group_sex=True)
    for judged in (True, False):
        with mock.patch.object(instuct_judege, "calculation_instuct_judege", return_value=[judged]):
            out.append(inv.invite_candidates([1]))
            for minutes in (0, 3):
                with mock.patch.object(choice, "route_minutes", return_value=minutes):
                    out += [inv.invite(cid) for cid in (4, 5)]
    out.append(inv.invite(2))
    with mock.patch.object(handle_premise, "handle_normal_24567", return_value=0):
        out.append(inv.invite(3))
    modes.set_sex_class(True)
    with mock.patch.object(instuct_judege, "calculation_instuct_judege", return_value=[False]):
        with mock.patch.object(choice, "route_minutes", return_value=0):
            out.append(inv.invite(5))
    payload["template"] = h_state.view(0).group_sex_body_template_dict
payload["calls"] = len(out)
payload["plans"] = len(plan_queue.take_since(mark))
payload["texts"] = [text for text in out if isinstance(text, str)]
"""
""" 在拦截界面与结算模块的子进程中调用两个服务公开函数及其主要分支的测试脚本。 """


class InviteTest(FastTestCase):
    """群交邀请候选名单与邀请执行结果分支测试。"""

    def setUp(self) -> None:
        """创建测试角色、开启工作缓冲与群交模式，记录计划队列起点并替换判定和寻路接口。"""
        super().setUp()
        self.world.chara(0, "博士")
        for cid in (1, 2, 3, 4, 5):
            self.world.chara(cid, f"干员{cid}")
        self.enterContext(working.based_on(core.state()))
        modes.set_group_sex(True)
        self.mark = plan_queue.mark()
        self.addCleanup(plan_queue.take_since, self.mark)
        self.judged = True
        self.judge = self.enterContext(
            mock.patch.object(
                instuct_judege,
                "calculation_instuct_judege",
                side_effect=lambda *a, **k: [self.judged],
            )
        )
        self.enterContext(
            mock.patch.object(choice, "route_minutes", return_value=7)
        )

    def test_candidates_skip_scene_player_refused_and_exhausted(self) -> None:
        """验证邀请名单排除同场、玩家、拒邀与疲劳角色，且不结算催眠代价。"""
        flags.set(4, go_to_join_group_sex=True)
        kernel_data.set_needs(5, hit=1)
        self.assertEqual(inv.invite_candidates([1]), ([2, 3, 4], [4]))
        self.judged = False
        self.assertEqual(inv.invite_candidates([1]), ([], []))
        self.assertEqual(
            self.judge.call_args.kwargs,
            {"not_draw_flag": True, "settle_hypnosis": False},
        )

    def test_candidates_in_sex_class(self) -> None:
        """验证课堂模式下按入课门槛筛选邀请名单，且必修学生跳过前置修习检查。"""
        modes.set_sex_class(True)
        self.judged = False
        calls = []

        def can_join(chara_id: int, check_course: bool) -> bool:
            """记录入课判定调用参数，并模拟除 5 号角色外均允许加入课堂。"""
            calls.append((chara_id, check_course))
            return chara_id != 5

        with (
            mock.patch.object(
                sex_class_handle, "get_must_attend_set", return_value={3}
            ),
            mock.patch.object(
                sex_class_handle, "judge_can_join_sex_class", can_join
            ),
        ):
            self.assertEqual(inv.invite_candidates([1]), ([2, 3, 4], []))
        self.assertEqual(calls, [(2, True), (3, False), (4, True), (5, True)])

    def test_invite_and_cancel(self) -> None:
        """验证邀请成功、取消邀请与无可用路径回退等待时的标志、二段行为及计划队列。"""
        self.assertEqual(inv.invite(1), "\n已邀请干员1来这里参加群交\n")
        self.assertTrue(flags.get(1, "go_to_join_group_sex"))
        self.assertEqual(
            activity.second_behavior(1, "be_invited_join_group_sex"), 1
        )
        self.assertEqual(
            self.judge.call_args.kwargs,
            {"not_draw_flag": True},
        )
        move = plan_queue.planned(1)[-1]
        self.assertEqual(
            (move["behavior_id"], move["minutes"], move.get("move")),
            (
                constant.Behavior.MOVE,
                7,
                {"to": list(activity.position(0)), "show": True},
            ),
        )
        self.assertEqual(
            inv.invite(1),
            "\n已取消对干员1的群交邀请，干员1不会来这里参加群交了\n",
        )
        self.assertFalse(flags.get(1, "go_to_join_group_sex"))
        wait = plan_queue.planned(1)[-1]
        self.assertEqual(
            (wait["behavior_id"], wait["minutes"], wait.get("state")),
            (constant.Behavior.WAIT, 5, constant.CharacterStatus.STATUS_WAIT),
        )
        with mock.patch.object(choice, "route_minutes", return_value=0):
            inv.invite(2)
        wait = plan_queue.planned(2)[-1]
        self.assertEqual(
            (wait["behavior_id"], wait["minutes"]), (constant.Behavior.WAIT, 5)
        )
        self.assertEqual(len(plan_queue.take_since(self.mark)), 3)

    def test_invite_refusals(self) -> None:
        """验证疲劳、拒邀、状态异常优先阻断以及课堂模式跳过实行值判定的邀请分支。"""
        kernel_data.set_needs(2, hit=1)
        self.assertEqual(inv.invite(2), "***干员2过于疲劳，无法参加群交***\n")
        self.judged = False
        self.assertEqual(inv.invite(3), "\n干员3拒绝了群交邀请\n")
        flags.set(4, go_to_join_group_sex=True)
        with mock.patch.object(
            handle_premise, "handle_normal_24567", return_value=0
        ):
            self.assertEqual(inv.invite(4), "***干员4状态异常，无法召集***\n")
        modes.set_sex_class(True)
        self.assertEqual(inv.invite(3), "\n已邀请干员3来这里参加群交\n")
        self.assertEqual(
            [flags.get(cid, "go_to_join_group_sex") for cid in (2, 3, 4)],
            [False, True, True],
        )
        self.assertEqual(plan_queue.planned(2), [])


class UiFreeRunTest(FastTestCase):
    """无界面子进程中执行群交编辑与邀请服务的隔离测试。"""

    @classmethod
    def setUpClass(cls) -> None:
        """在拦截 Script.UI 与 Script.Settle 的子进程中执行一次分支脚本。"""
        super().setUpClass()
        cls.child = run_ui_free(UI_FREE_RUN, boot=True)

    def test_no_ui_or_settle_loaded(self) -> None:
        """验证子进程运行期间未加载也未尝试导入任何界面或结算模块。"""
        self.assertEqual((self.child.loaded, self.child.attempted), ([], []))

    def test_child_results(self) -> None:
        """验证子进程返回的信息文本、邀请提示、最终模板与计划队列条目数。"""
        out = self.child.payload
        kiss, handjob = (
            game_config.config_behavior[b].name for b in ("kiss_h", "handjob")
        )
        cancel = "\n已取消对c{0}的群交邀请，c{0}不会来这里参加群交了\n"
        self.assertEqual(
            out["texts"],
            [
                "",
                f"c0 嘴-{kiss}-c1 阴茎正在被c5、c1、c2、c3一起{handjob} \n",
                cancel.format(4),
                "\n已邀请c5来这里参加群交\n",
                "\n已邀请c4来这里参加群交\n",
                cancel.format(5),
                cancel.format(4),
                "\nc5拒绝了群交邀请\n",
                "\nc4拒绝了群交邀请\n",
                "\nc5拒绝了群交邀请\n",
                "***c2过于疲劳，无法参加群交***\n",
                "***c3状态异常，无法召集***\n",
                "\n已邀请c5来这里参加群交\n",
            ],
        )
        a_parts: dict[str, list[Any]] = dict.fromkeys(
            svc.BODY_PART_NAMES, EMPTY
        )
        a_parts["penis"] = [-1, "normal_sex"]
        b_parts: dict[str, list[Any]] = dict.fromkeys(
            svc.BODY_PART_NAMES, EMPTY
        )
        b_parts["mouth"] = [1, "kiss_h"]
        self.assertEqual(
            out["template"],
            {
                "A": [a_parts, NO_SERVE],
                "B": [b_parts, [[5, 1, 2, 3], "handjob"]],
            },
        )
        self.assertEqual((out["calls"], out["plans"]), (29, 6))
        self.assertEqual(out["watch"], [[4, True]])
