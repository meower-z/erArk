"""
射精目标与部位选择测试
======================
EjaculationUiFreeTest 在无界面子进程中验证自动射精、未登记报错与界面模块隔离。
EjaculationFlowTest 验证独处、自动射精、深喉、手动部位、服装、无壳卵、群交与前提查找。
EjaculationTkTest 验证 Tk 对象按钮按名应答、按钮清理回调与部位按配置槽位换行。
"""

from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import constant, flow_handle, io_init, save_handle
from Script.Design import handle_premise, instuct_judege
from Script.Kernel import core
from Script.Modules.domains import activity, h_state, modes
from Script.Modules.gameplay_resolution import ejaculation_service
from Script.Modules.gameplay_resolution import modal_hooks, ui_hooks
from Script.Modules.gameplay_resolution import working
from Script.Modules.tk_ui import ejaculation_callbacks
from Script.Protocol.modal_prompts import ChoiceOption, ChoicePrompt
from Script.Protocol.modal_prompts import ChoiceResult
from Script.System.Pregnancy_System import soft_egg_handle
from Script.UI.Moudle import draw
from tests import kernel_data
from tests.chara_activity import aim
from tests.fast.base import FastTestCase

TARGET = 1
""" 测试使用的主要目标角色编号（1）。 """
OTHER = 2
""" 测试使用的另一同场景角色编号（2）。 """
EGGS = {3: {"semen_count": 12.5}}
""" 测试使用的场景体外无壳卵映射样例（编号 3，精液量 12.5）。 """
CHILD_RUN = """
from Script.Config import map_config, normal_config
from Script.Kernel import core
from Script.Modules.domains import h_state, identity
from Script.Modules.gameplay_resolution import ejaculation_service as service
from Script.Modules.gameplay_resolution import working
from tests import chara_abilities, chara_data, kernel_data
from tests.chara_activity import aim, place
from tests.world import DEFAULT_SCENE, start_time

map_config.init_map_data()
kernel_data.reset_clock(start_time(), {})
for cid in (0, 1):
    kernel_data.put(identity.put, identity.Identity(cid, name=f"c{cid}", sex=1))
    chara_abilities.zero_tables(cid)
    chara_data.seed(cid, {})
    place(cid, DEFAULT_SCENE)
aim(0, 1)
core.reset_state(kernel_data.reprojected(core.state()))
shots = []
service.ejaculation_flow = lambda *args, **kwargs: shots.append([*args])
service.instuct_judege.calculation_instuct_judege = lambda *args, **kwargs: [1]
normal_config.system_setting.base_setting[3] = 0
with working.based_on(core.state()):
    h_state.set(1, insert_position=8)
    service.resolve_ejaculation()
    payload["positions"] = [h_state.get(0, "insert_position"), h_state.get(1, "insert_position")]
    normal_config.system_setting.base_setting[3] = 1
    try:
        service.resolve_ejaculation()
    except RuntimeError as error:
        payload["unasked"] = str(error)
payload["shots"] = shots
"""
""" 在无界面子进程中验证自动射精、手动模式未登记报错与模块隔离的脚本源码。 """


class EjaculationUiFreeTest(FastTestCase):
    """无界面子进程中 ejaculation_service.resolve_ejaculation 的执行与模块隔离测试。"""

    def test_resolve_without_ui(self) -> None:
        """验证无界面子进程可直接完成自动射精，手动模式未登记时报错且不加载界面模块。"""
        from tests.ui_free_subprocess import run_ui_free

        child = run_ui_free(CHILD_RUN, boot=True)
        self.assertEqual(child.payload["shots"], [[8, 0]])
        self.assertEqual(child.payload["positions"], [8, 8])
        self.assertEqual(
            child.payload["unasked"], "no choice handler for ejaculation_part"
        )
        self.assertEqual((child.attempted, child.loaded), ([], []))


class EjaculationFlowTest(FastTestCase):
    """ejaculation_service.resolve_ejaculation 各决策分支与状态写入的进程内测试。"""

    def setUp(self) -> None:
        """准备角色与工作集，打桩提示、射精流程、分隔线、面板切换、按钮清理、无壳卵与口交判定。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(TARGET, "对方", naked=True)
        self.world.chara(OTHER, "旁人", adv=7)
        self.enterContext(working.based_on(core.state()))
        self.events: list[object] = []
        self.prompts: list[ChoicePrompt] = []
        self.answers: list[str] = []
        self.eggs: dict[int, dict[str, float]] = {}
        self.settings = dict(normal_config.system_setting.base_setting)
        self.settings[3] = 0
        for owner, name, value in (
            (modal_hooks, "_ask", self.ask),
            (ejaculation_service, "ejaculation_flow", self.shoot),
            (
                ui_hooks,
                "_dividers",
                [lambda char: self.events.append("divider")],
            ),
            (ui_hooks, "_panel_switches", [self.events.append]),
            (ui_hooks, "_button_clears", [lambda: self.events.append("clear")]),
            (normal_config.system_setting, "base_setting", self.settings),
            (soft_egg_handle, "get_soft_eggs_in_scene", lambda _: self.eggs),
            (
                soft_egg_handle,
                "get_soft_egg_name",
                lambda egg_id: f"卵{egg_id}",
            ),
            (instuct_judege, "calculation_instuct_judege", self.judge),
        ):
            self.enterContext(mock.patch.object(owner, name, value))

    def ask(self, prompt: ChoicePrompt) -> ChoiceResult:
        """
        记录收到的提示对象与提示标识，并按预设列表顺序返回 ChoiceResult。
        Keyword arguments:
        prompt -- ChoicePrompt，待处理的选项提示
        Return arguments:
        ChoiceResult -- 包含下一项预设选项标识的结果
        """
        self.prompts.append(prompt)
        self.events.append(prompt.prompt_id)
        return ChoiceResult(prompt.prompt_id, self.answers.pop(0))

    def shoot(self, part_cid: int, part_type: int, **kwargs: int) -> None:
        """
        将射精总流程调用的部位参数与关键字参数追加记录到 self.events。
        Keyword arguments:
        part_cid -- int，射精部位编号
        part_type -- int，部位类型编号
        kwargs -- int，附加关键字参数
        Return arguments:
        None -- 无返回值
        """
        self.events.append(("shot", part_cid, part_type, kwargs))

    def judge(self, *args: object, **kwargs: object) -> list[float]:
        """
        指令判定的测试桩实现，固定返回 [1, 1, 1.0]。
        Keyword arguments:
        args -- object，忽略的位置参数
        kwargs -- object，忽略的关键字参数
        Return arguments:
        list[float] -- 固定的三元素判定结果列表
        """
        return [1, 1, 1.0]

    def positions(self) -> list[int]:
        """
        读取并返回玩家与 TARGET 当前的 insert_position 列表。
        Return arguments:
        list[int] -- 依次为玩家与 TARGET 的 insert_position
        """
        return [h_state.get(cid, "insert_position") for cid in (0, TARGET)]

    def open_ids(self) -> list[str]:
        """
        返回最近一次选项提示中可用状态为 "open" 的选项标识列表。
        Return arguments:
        list[str] -- 可用选项的 option_id 列表
        """
        return [
            option.option_id
            for option in self.prompts[-1].options
            if option.availability == "open"
        ]

    def test_alone_shoots_as_usual(self) -> None:
        """验证无目标且无场景无壳卵时不提问，直接射向部位 6、写入位置并输出分隔线。"""
        ejaculation_service.resolve_ejaculation()
        self.assertEqual(self.events, ["clear", ("shot", 6, 0, {}), "divider"])
        self.assertEqual(h_state.get(0, "insert_position"), 6)

    def test_alone_with_eggs_asks_egg_or_usual(self) -> None:
        """验证无目标但有场景无壳卵时仅提供卵块与照常射出选项，并按选择执行射精。"""
        self.eggs = EGGS
        self.answers = ["normal", "egg_3"]
        ejaculation_service.resolve_ejaculation()
        self.assertEqual(
            [(o.option_id, o.label) for o in self.prompts[0].options],
            [("egg_3", "[卵块3]卵3（12ml）"), ("normal", "[照常射出]")],
        )
        self.assertEqual(self.prompts[0].title, "选择射精部位")
        ejaculation_service.resolve_ejaculation()
        self.assertEqual(
            self.events,
            [
                ejaculation_service.PART_PROMPT_ID,
                "clear",
                ("shot", 6, 0, {}),
                constant.Panel.IN_SCENE,
                "divider",
                ejaculation_service.PART_PROMPT_ID,
                "clear",
                ("shot", -1, 0, {"soft_egg_id": 3}),
                constant.Panel.IN_SCENE,
                "divider",
            ],
        )
        self.assertEqual(h_state.get(0, "insert_position"), 6)

    def test_setting_off_follows_insert_position(self) -> None:
        """验证关闭系统设置 3 时按 insert_position 自动射精，为 -1 时发起部位提问。"""
        aim(0, TARGET)
        for position, shot in ((8, (8, 0)), (25, (5, 1))):
            self.events.clear()
            h_state.set(TARGET, insert_position=position)
            ejaculation_service.resolve_ejaculation()
            self.assertEqual(
                self.events, ["clear", ("shot", *shot, {}), "divider"]
            )
            self.assertEqual(self.positions(), [position, position])
        h_state.set(TARGET, insert_position=-1)
        self.answers = ["body_0"]
        ejaculation_service.resolve_ejaculation()
        self.assertEqual(
            self.events[-4:],
            ["clear", ("shot", 0, 0, {}), constant.Panel.IN_SCENE, "divider"],
        )
        self.assertEqual(self.positions(), [0, 0])

    def test_deep_throat_lands_in_stomach(self) -> None:
        """
        验证上一指令为深喉时，身体射精改向部位 15，服装射精不受影响。
        两次射精后插入位置均为所选位置。
        """
        aim(0, TARGET)
        with mock.patch.object(
            handle_premise, "handle_last_cmd_deep_throat", return_value=1
        ):
            for position in (2, 22):
                h_state.set(TARGET, insert_position=position)
                ejaculation_service.resolve_ejaculation()
        self.assertEqual(
            self.events,
            ["clear", ("shot", 15, 0, {}), "divider"]
            + ["clear", ("shot", 2, 1, {}), "divider"],
        )
        self.assertEqual(self.positions(), [22, 22])

    def test_setting_on_lists_reachable_parts(self) -> None:
        """验证开启设置 3 时按配置列出全部身体与服装选项，标出 blocked 并按选择射精。"""
        aim(0, TARGET)
        self.settings[3] = 1
        h_state.set(TARGET, insert_position=7)
        self.answers = ["body_7"]
        ejaculation_service.resolve_ejaculation()
        prompt = self.prompts[0]
        self.assertEqual(prompt.title, "选择射精部位")
        bodies = [o for o in prompt.options if o.option_id.startswith("body_")]
        self.assertEqual(
            [(o.option_id, o.label) for o in bodies],
            [
                (f"body_{cid}", f"[{cid}]{part.name}")
                for cid, part in game_config.config_body_part.items()
            ],
        )
        shut = {f"body_{cid}" for cid in (8, 9, 12, 13, 14, 15)}
        self.assertEqual(
            {o.option_id for o in bodies if o.availability == "blocked"}, shut
        )
        self.assertEqual(
            [o.option_id for o in prompt.options[len(bodies) :]],
            [f"cloth_{kind}" for kind in game_config.config_clothing_type],
        )
        self.assertNotIn("cloth_5", self.open_ids())
        self.assertEqual(
            self.events,
            [
                ejaculation_service.PART_PROMPT_ID,
                "clear",
                ("shot", 7, 0, {}),
                constant.Panel.IN_SCENE,
                "divider",
            ],
        )
        self.assertEqual(self.positions(), [7, 7])

    def test_worn_clothes_open_and_eggs_force_the_ask(self) -> None:
        """验证已穿服装处于可用状态，且有场景无壳卵时关闭设置 3 也会提问并支持射向卵块。"""
        aim(0, OTHER)
        h_state.set(OTHER, insert_position=8)
        self.eggs = EGGS
        self.answers = ["egg_3"]
        ejaculation_service.resolve_ejaculation()
        self.assertIn("cloth_5", self.open_ids())
        self.assertIn("body_8", self.open_ids())
        self.assertEqual(self.open_ids()[-1], "egg_3")
        self.assertEqual(
            self.events[1:3], ["clear", ("shot", -1, 0, {"soft_egg_id": 3})]
        )
        self.assertEqual(h_state.get(OTHER, "insert_position"), 8)

    def test_group_sex_picks_target_first(self) -> None:
        """验证群交模式先提问并切换交互目标，再按新目标列出可用部位并完成射精。"""
        aim(0, TARGET)
        kernel_data.put(modes.set_group_sex, True)
        h_state.set(OTHER, insert_position=6)
        self.answers = [str(OTHER), "body_6"]
        ejaculation_service.resolve_ejaculation()
        target_prompt = self.prompts[0]
        self.assertEqual(target_prompt.title, "选择射精对象")
        self.assertEqual(
            [(o.option_id, o.label) for o in target_prompt.options],
            [(str(TARGET), "[0]对方"), (str(OTHER), "[7]旁人")],
        )
        self.assertEqual(activity.target(0), OTHER)
        self.assertIn("body_6", self.open_ids())
        self.assertEqual(
            self.events,
            [
                ejaculation_service.TARGET_PROMPT_ID,
                ejaculation_service.PART_PROMPT_ID,
                "clear",
                ("shot", 6, 0, {}),
                constant.Panel.IN_SCENE,
                "divider",
            ],
        )
        self.assertEqual(h_state.get(OTHER, "insert_position"), 6)

    def test_inserted_parts_read_premises_when_asked(self) -> None:
        """验证替换 handle_premise 插入前提函数后，部位 8 的可选状态随之生效。"""
        aim(0, TARGET)
        self.settings[3] = 1
        self.answers = ["body_0", "body_8"]
        for inserted in (0, 1):
            with mock.patch.object(
                handle_premise, "handle_penis_in_t_anal", return_value=inserted
            ):
                ejaculation_service.resolve_ejaculation()
            self.assertEqual("body_8" in self.open_ids(), bool(inserted))


class EjaculationTkTest(FastTestCase):
    """ejaculation_callbacks 中两个 Tk 射精选项渲染函数的绘制与交互测试。"""

    def setUp(self) -> None:
        """接管绘制 draw、askfor_all 包装、回显输出、自动存档与会话结束，并初始化记录字段。"""
        super().setUp()
        self.drawn: list[tuple[object, ...]] = []
        self.offers: list[list[str]] = []
        self.pick = 0
        for shown in (draw.NormalDraw, draw.TitleLineDraw, draw.CenterButton):
            self.enterContext(
                mock.patch.object(
                    shown, "draw", autospec=True, side_effect=self.record
                )
            )
        self.ask = flow_handle.askfor_all
        self.enterContext(
            mock.patch.object(flow_handle, "askfor_all", self.answer)
        )
        self.exits = [
            self.enterContext(mock.patch.object(owner, name))
            for owner, name in (
                (io_init, "era_print"),
                (save_handle, "establish_save"),
                (io_init, "end_session"),
            )
        ][1:]
        self.width = normal_config.config_normal.text_width

    def record(self, shown: draw.NormalDraw) -> None:
        """
        按类型将绘制对象记录到 self.drawn，并为按钮调用 flow_handle.bind_cmd 绑定命令。
        Keyword arguments:
        shown -- draw.NormalDraw，被调用 draw 的绘制对象
        Return arguments:
        None -- 无返回值
        """
        if isinstance(shown, draw.CenterButton):
            self.drawn.append(
                ("button", shown.text, shown.return_text, shown.width)
            )
            flow_handle.bind_cmd(shown.return_text, shown.cmd_func, shown.args)
        elif isinstance(shown, draw.TitleLineDraw):
            self.drawn.append(("title", shown.title, shown.width))
        else:
            self.drawn.append(("text", shown.text, shown.width))

    def answer(self, return_list: list[str]) -> str:
        """
        记录返回键列表，用索引 self.pick 对应的键应答输入读取并调用原 askfor_all。
        Keyword arguments:
        return_list -- list[str]，传给 askfor_all 的响应文本列表
        Return arguments:
        str -- 原 askfor_all 返回的响应文本
        """
        self.offers.append(list(return_list))
        with mock.patch.object(
            flow_handle, "order_deal", return_value=return_list[self.pick]
        ):
            return self.ask(return_list)

    def test_target_buttons_answer_by_name(self) -> None:
        """
        验证 draw_target_choice 按首个 "]" 拆出对象名作为响应文本并映射回 option_id，
        且选择名为 999 的对象时不触发自动存档与会话结束。
        """
        prompt = ChoicePrompt(
            ejaculation_service.TARGET_PROMPT_ID,
            (ChoiceOption("1", "[12]甲]乙"), ChoiceOption("2", "[3]999")),
            title="选对象",
        )
        self.pick = 1
        self.assertEqual(ejaculation_callbacks.draw_target_choice(prompt), "2")
        self.assertEqual(
            self.drawn,
            [
                ("title", "选对象", self.width),
                ("button", "[12]甲]乙", "甲]乙", 24),
                ("button", "[3]999", "999", 21),
                ("text", "\n", 1),
            ],
        )
        self.assertEqual(self.offers, [["甲]乙", "999"]])
        self.assertEqual([end.call_count for end in self.exits], [0, 0])

    def test_clear_buttons_drops_bound_commands(self) -> None:
        """验证 ui_hooks.clear_buttons 会清除 flow_handle.cmd_map 中已绑定的命令。"""
        flow_handle.bind_cmd("旧按钮", print)
        ui_hooks.clear_buttons()
        self.assertNotIn("旧按钮", flow_handle.cmd_map)

    def test_part_grid_wraps_on_config_slots(self) -> None:
        """
        验证 draw_part_choice 按配置槽位在可用且逢 8 时换行、每 4 个卵块换行，
        且应答后保留 flow_handle.cmd_map 中已绑定的命令。
        """
        bodies = tuple(
            ChoiceOption(
                f"body_{cid}",
                f"[{cid}]部{cid}",
                "open" if cid in (1, 7, 8) else "blocked",
            )
            for cid in range(9)
        )
        cloths = (
            ChoiceOption("cloth_0", "[0]帽", "blocked"),
            ChoiceOption("cloth_1", "[1]衣"),
        )
        eggs = tuple(ChoiceOption(f"egg_{i}", f"卵{i}") for i in range(5))
        prompt = ChoicePrompt(
            ejaculation_service.PART_PROMPT_ID,
            bodies + cloths + eggs + (ChoiceOption("normal", "[照常]"),),
            title="选部位",
        )
        self.pick = -1
        self.assertEqual(
            ejaculation_callbacks.draw_part_choice(prompt), "normal"
        )
        feed = ("text", "\n", 1)
        eggs_drawn = [("button", f"卵{i}", f"卵{i}", 6) for i in range(5)]
        self.assertEqual(
            self.drawn,
            [
                ("title", "选部位", self.width),
                ("button", "[1]部1", "\n部1", 12),
                ("button", "[7]部7", "\n部7", 12),
                feed,
                ("button", "[8]部8", "\n部8", 12),
                feed,
                ("button", "[1]衣", "衣", 10),
                feed,
                *eggs_drawn[:4],
                feed,
                eggs_drawn[4],
                feed,
                ("button", "[照常]", "[照常]", 10),
            ],
        )
        self.assertEqual(
            self.offers,
            [
                [
                    "\n部1",
                    "\n部7",
                    "\n部8",
                    "衣",
                    *[f"卵{i}" for i in range(5)],
                    "[照常]",
                ]
            ],
        )
        self.assertIn("[照常]", flow_handle.cmd_map)
