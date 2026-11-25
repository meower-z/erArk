"""
系统设置纯逻辑服务测试
======================
覆盖选项行组装与控件映射、选项循环与数值范围约束、本地配置文件写入、生殖方式开关与存量清理、禁止干员列表切换、面板提示适配以及独立子进程中的无界面导入边界。
"""

import json
import subprocess
import sys
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import flow_handle
from Script.Design import attr_calculation, game_time
from Script.Kernel import core
from Script.Modules.domains import activity, chara_life, chara_profile
from Script.Modules.domains import identity, player_collection, playthrough
from Script.Modules.domains import pregnancy, roster
from Script.Modules.gameplay_resolution import system_setting_service as svc
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import kernel_state
from Script.System.Pregnancy_System import pregnancy_constant
from Script.UI.Moudle import draw
from Script.UI.Panel import system_setting
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

EGG = pregnancy_constant.BIRTH_TYPE_EGG
""" 带壳卵生生育方式编号常量 """
TEND = pregnancy_constant.TEND_EGGS_ENTERTAINMENT_ID
""" 照料卵娱乐活动编号常量 """
BACKEND_RUN = """
import contextlib, importlib.abc, io, json, sys
BLOCKED = ("Script.UI", "Script.Settle", "Script.Core.flow_handle",
    "Script.Core.io_init", "Script.Core.game_init", "Script.Frontend",
    "Script.System.Instruct_System.handle_instruct", "Script.Modules.tk_ui",
    "tkinter", "_tkinter", "PIL.ImageTk")
ALLOWED = frozenset({"Script.Modules.tk_ui", "Script.Modules.tk_ui.orders"})
REFUSED = []
def is_blocked(name):
    if name in ALLOWED:
        return False
    return any(name == root or name.startswith(root + ".") for root in BLOCKED)
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if is_blocked(fullname):
            REFUSED.append(fullname)
            raise ImportError(fullname)
        return None
sys.meta_path.insert(0, Blocker())
payload = json.loads(sys.stdin.read())
with contextlib.redirect_stdout(io.StringIO()):
    from Script.Config import normal_config
    normal_config.init_normal_config()
    from Script.Config import game_config
    game_config.init()
from Script.Modules.domains import activity, chara_life, chara_profile
from Script.Modules.domains import pregnancy, roster, playthrough
from Script.Modules.gameplay_resolution import system_setting_service as svc
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import kernel_state
from Script.Kernel import core
core.reset_state(kernel_state.decode(payload["state"], True))
setting = normal_config.system_setting
setting.base_setting = {int(k): v for k, v in payload["base"].items()}
setting.draw_setting = {int(k): v for k, v in payload["draw"].items()}
written = []
normal_config.write_local_config = written.append
egg, npc, stay = payload["egg"], payload["npc"], payload["stay"]
out = {}
with working.based_on(core.state()):
    out["rows"] = {kind.value: [[r.cid, r.control.value, r.option_len]
        for r in svc.option_rows(kind)] for kind in svc.Kind}
    out["ban_link"] = [r.cid for r in svc.option_rows(svc.Kind.BASE)
        if r.ban_list]
    draw_len = len(game_config.config_draw_setting_option[2])
    out["steps"] = [svc.cycle(svc.Kind.DRAW, 2, draw_len).value,
        svc.cycle(svc.Kind.BASE, 12, 2).value,
        svc.cycle(svc.Kind.DRAW, 11, 10).value,
        svc.cycle(svc.Kind.DIFFICULTY, payload["level"], 3).value]
    out["text_flag"] = [chara_profile.chara_setting(cid)[1]
        for cid in (0, npc, egg)]
    out["level"] = playthrough.setting(playthrough.DIFFICULTY, payload["level"])
    out["number"] = svc.set_draw_number(11, 20)
    out["config"] = [svc.apply_font_size(99), svc.apply_dpi(10)]
    svc.apply_language("en_US")
    out["written"] = written
    out["birth_rows"] = [[r.birth_type, r.enabled]
        for r in svc.birth_type_rows()]
    out["closed"] = bool(svc.close_birth_type(payload["birth"]))
    out["birth_on"] = svc.birth_type_on(payload["birth"])
    out["eggs"] = len(pregnancy.of(egg).eggs)
    out["tend"] = payload["tend"] in chara_life.entertainment_type(egg)
    svc.open_birth_type(payload["birth"])
    out["reopened"] = svc.birth_type_on(payload["birth"])
    out["ban_rows"] = [[r.npc_id, r.banned] for r in svc.ban_rows()]
    out["off"] = [svc.toggle_ban(npc), svc.toggle_ban(stay)]
    out["after_off"] = [roster.has(npc), roster.is_forbidden(npc),
        activity.position(npc)]
    out["info"] = [bool(svc.setting_info(kind, cid)) for kind, cid in
        ((svc.Kind.BASE, 1), (svc.Kind.DIFFICULTY, payload["level"]),
        (svc.Kind.DRAW, 2))]
    out["birth_text"] = [bool(t) for t in svc.birth_type_text(payload["birth"])]
out["loaded"] = sorted(n for n in sys.modules if is_blocked(n))
out["refused"] = REFUSED
print(json.dumps(out))
"""
""" 在拦截界面、结算与窗口模块的子进程中执行系统设置服务全部路径并输出校验结果的脚本。 """


def egg_race() -> int:
    """
    从种族配置中查找首个带壳卵生种族的编号。
    Return arguments:
    int -- 首个带壳卵生种族编号
    """
    for race_id, race in game_config.config_race.items():
        if getattr(race, "birth_type", 0) == EGG:
            return race_id
    raise AssertionError("no egg-laying race in the config")


class SettingCase(FastTestCase):
    """系统设置服务测试基类，初始化测试角色、临时设置对象、本地配置写入记录与状态缓冲。"""

    def setUp(self) -> None:
        """创建玩家角色 0 与两名测试干员，将干员乙设为未在册状态，替换系统设置与本地配置写入函数并开启临时状态缓冲。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.npc = self.world.chara(1, "干员甲").cid
        self.stay = self.world.chara(2, "干员乙").cid
        kernel_data.put(roster.remove, self.stay)
        self.written: list[dict[str, str]] = []
        fresh = attr_calculation.get_system_setting_zero()
        config = normal_config.config_normal
        patches: list[tuple[object, str, object]] = [
            (normal_config, "system_setting", fresh),
            (normal_config, "write_local_config", self.written.append),
        ]
        for name in ("font_size", "order_font_size", "tk_dpi", "language"):
            patches.append((config, name, getattr(config, name, None)))
        for owner, name, value in patches:
            patch = mock.patch.object(owner, name, value, create=True)
            self.enterContext(patch)
        self.buffer = self.enterContext(working.based_on(core.state()))

    def row(self, kind: svc.Kind, cid: int) -> svc.OptionRow:
        """
        按分类与编号查找对应的单条选项展示行。
        Keyword arguments:
        kind -- svc.Kind，设置分类枚举值
        cid -- int，设置项编号
        Return arguments:
        svc.OptionRow -- 匹配的选项展示行
        """
        return next(r for r in svc.option_rows(kind) if r.cid == cid)


class OptionRowsTest(SettingCase):
    """选项行组装、控件类型、缺失值回退、禁止干员入口条件与说明换行测试。"""

    def test_controls_and_values(self) -> None:
        """验证三类设置的控件类型映射以及数值、字体、DPI 与循环选项行的显示文本和选项数。"""
        draw_setting = normal_config.system_setting.draw_setting
        draw_setting[14] = 37
        draw_setting[3] = 1
        normal_config.config_normal.font_size = 23
        normal_config.config_normal.tk_dpi = 125
        special = {
            (svc.Kind.BASE, 13): svc.Control.BIRTH_TYPE,
            (svc.Kind.DRAW, 12): svc.Control.FONT_SIZE,
            (svc.Kind.DRAW, 18): svc.Control.DPI,
            (svc.Kind.DRAW, 14): svc.Control.NUMBER,
            (svc.Kind.DRAW, 15): svc.Control.NUMBER,
        }
        for kind in svc.Kind:
            for row in svc.option_rows(kind):
                with self.subTest(kind=kind, cid=row.cid):
                    self.assertEqual(
                        row.control,
                        special.get((kind, row.cid), svc.Control.CYCLE),
                    )
        self.assertEqual(self.row(svc.Kind.DRAW, 14).value, "37")
        self.assertEqual(self.row(svc.Kind.DRAW, 12).value, "23")
        self.assertEqual(self.row(svc.Kind.DRAW, 18).value, "125")
        labels = game_config.config_draw_setting_option[3]
        cycle_row = self.row(svc.Kind.DRAW, 3)
        self.assertEqual(cycle_row.value, labels[1])
        self.assertEqual(cycle_row.option_len, len(labels))
        self.assertEqual(
            cycle_row.name, game_config.config_draw_setting[3].name
        )

    def test_dpi_defaults_to_150(self) -> None:
        """验证运行时配置缺少 tk_dpi 属性时，绘制设置 18 号默认显示 150。"""
        del normal_config.config_normal.tk_dpi
        self.assertEqual(self.row(svc.Kind.DRAW, 18).value, "150")

    def test_missing_values_read_as_zero(self) -> None:
        """验证缺失基础设置会回填 0 到运行时字典，缺失难度设置仅在读取副本中按 0 展示而不回写存档。"""
        base = normal_config.system_setting.base_setting
        del base[1]
        self.assertEqual(
            self.row(svc.Kind.BASE, 1).value,
            game_config.config_system_setting_option[1][0],
        )
        self.assertEqual(base[1], 0)
        level = min(playthrough.settings(playthrough.DIFFICULTY))
        table = playthrough.settings(playthrough.DIFFICULTY)
        del table[level]
        playthrough.set_settings(playthrough.DIFFICULTY, table)
        self.row(svc.Kind.DIFFICULTY, level)
        self.assertNotIn(level, playthrough.settings(playthrough.DIFFICULTY))

    def test_ban_list_link_follows_base_7(self) -> None:
        """验证仅在基础设置 7 号为非零值时返回禁止干员列表入口标记。"""
        base = normal_config.system_setting.base_setting
        base[7] = 0
        self.assertFalse(
            any(r.ban_list for r in svc.option_rows(svc.Kind.BASE))
        )
        base[7] = 1
        linked = [r.cid for r in svc.option_rows(svc.Kind.BASE) if r.ban_list]
        self.assertEqual(linked, [7])
        normal_config.system_setting.draw_setting[7] = 1
        self.assertFalse(
            any(r.ban_list for r in svc.option_rows(svc.Kind.DRAW))
        )

    def test_setting_info_breaks_lines(self) -> None:
        """验证 setting_info 会把说明文本中的字面换行符 \\n 转为带空格的换行符。"""
        config = game_config.config_system_setting[1]
        self.enterContext(mock.patch.object(config, "info", "甲\\n乙"))
        self.assertEqual(svc.setting_info(svc.Kind.BASE, 1), "甲 \n乙")


class CycleTest(SettingCase):
    """选项循环推进、锁定项保护、全局同步与数值设置范围约束测试。"""

    def test_cycle_wraps_to_zero(self) -> None:
        """验证普通循环设置递增并在达到上限后回绕为 0。"""
        base = normal_config.system_setting.base_setting
        base[1] = 0
        self.assertIs(svc.cycle(svc.Kind.BASE, 1, 3), svc.Step.DONE)
        self.assertEqual(base[1], 1)
        base[1] = 2
        svc.cycle(svc.Kind.BASE, 1, 3)
        self.assertEqual(base[1], 0)

    def test_difficulty_is_written_back(self) -> None:
        """验证难度分类调用 cycle 后会将新值写回当前存档设置表。"""
        level = min(playthrough.settings(playthrough.DIFFICULTY))
        playthrough.set_setting(playthrough.DIFFICULTY, level, 1)
        self.assertIs(svc.cycle(svc.Kind.DIFFICULTY, level, 3), svc.Step.DONE)
        self.assertEqual(playthrough.setting(playthrough.DIFFICULTY, level), 2)

    def test_base_12_is_locked(self) -> None:
        """验证基础设置 12 号调用 cycle 时保持原值并返回 Step.LOCKED。"""
        base = normal_config.system_setting.base_setting
        base[12] = 0
        self.assertIs(svc.cycle(svc.Kind.BASE, 12, 2), svc.Step.LOCKED)
        self.assertEqual(base[12], 0)

    def test_draw_2_reaches_every_character(self) -> None:
        """验证绘制设置 2 号切换后会同步写入包含玩家与离册角色在内的全部角色配置第 1 项。"""
        normal_config.system_setting.draw_setting[2] = 0
        svc.cycle(svc.Kind.DRAW, 2, 2)
        for cid in (0, self.npc, self.stay):
            with self.subTest(cid=cid):
                self.assertEqual(chara_profile.chara_setting(cid)[1], 1)

    def test_number_options_ask_for_input(self) -> None:
        """验证绘制设置 11、14、15 号在 cycle 后分别返回数量与倍率输入步骤，普通项返回完成。"""
        ask, rate = svc.Step.ASK_COUNT, svc.Step.ASK_RATE
        expected = {11: ask, 14: rate, 15: rate, 3: svc.Step.DONE}
        for cid, step in expected.items():
            with self.subTest(cid=cid):
                self.assertIs(svc.cycle(svc.Kind.DRAW, cid, 10), step)

    def test_set_draw_number_clamps(self) -> None:
        """验证 set_draw_number 对 11 号减 1 后限制在 0 到 9，对其余项限制在 1 到 99 并写入 draw_setting。"""
        cases = [(11, 0, 0), (11, 5, 4), (11, 20, 9)]
        cases += [(14, 0, 1), (15, 50, 50), (14, 200, 99)]
        draw_setting = normal_config.system_setting.draw_setting
        for cid, number, value in cases:
            with self.subTest(cid=cid, number=number):
                self.assertEqual(svc.set_draw_number(cid, number), value)
                self.assertEqual(draw_setting[cid], value)


class LocalConfigTest(SettingCase):
    """字体大小、DPI 缩放与语言切换的本地配置写入测试。"""

    def test_font_size_is_clamped_and_written(self) -> None:
        """验证 apply_font_size 将字体限制在 1 到 50，同步更新 order_font_size 并写入 font_size 与 text_width。"""
        normal_config.config_normal.window_width = 2000
        self.assertEqual(svc.apply_font_size(99), 50)
        self.assertEqual(svc.apply_font_size(0), 1)
        self.assertEqual(normal_config.config_normal.font_size, 1)
        self.assertEqual(normal_config.config_normal.order_font_size, -1)
        self.assertEqual(
            self.written,
            [
                {"font_size": "50", "text_width": "80"},
                {"font_size": "1", "text_width": "4000"},
            ],
        )

    def test_dpi_is_clamped_and_written(self) -> None:
        """验证 apply_dpi 将缩放值限制在 50 到 300，更新 tk_dpi 并写入本地配置。"""
        self.assertEqual(svc.apply_dpi(10), 50)
        self.assertEqual(svc.apply_dpi(999), 300)
        self.assertEqual(svc.apply_dpi(125), 125)
        self.assertEqual(normal_config.config_normal.tk_dpi, 125)
        self.assertEqual(
            self.written,
            [{"tk_dpi": "50"}, {"tk_dpi": "300"}, {"tk_dpi": "125"}],
        )

    def test_language_is_written(self) -> None:
        """验证 apply_language 更新运行时语言代码并写入本地配置。"""
        svc.apply_language("ko_KR")
        self.assertEqual(normal_config.config_normal.language, "ko_KR")
        self.assertEqual(self.written, [{"language": "ko_KR"}])


class BirthTypeTest(SettingCase):
    """生殖方式开关列表读取、关闭清库存、重新开启与说明文本换行测试。"""

    def test_rows_read_missing_as_on(self) -> None:
        """验证存档中缺失的生殖方式键按开启状态展示且不修改原始设置字典。"""
        playthrough.set_settings(playthrough.BIRTH_TYPE, {EGG: 0})
        rows = {r.birth_type: r for r in svc.birth_type_rows()}
        self.assertEqual(
            list(rows), list(game_config.config_birth_type_setting)
        )
        options = game_config.config_birth_type_setting_option
        for birth_type, row in rows.items():
            with self.subTest(birth_type=birth_type):
                on = birth_type != EGG
                self.assertEqual(row.enabled, on)
                self.assertEqual(row.state, options[birth_type][int(on)])
                self.assertEqual(svc.birth_type_on(birth_type), on)
        self.assertEqual(playthrough.settings(playthrough.BIRTH_TYPE), {EGG: 0})

    def test_close_clears_eggs_and_open_restores(self) -> None:
        """验证关闭带壳卵生会清空角色卵与玩家持有卵并返回报告，重新开启后恢复开启状态。"""
        mother = self.world.chara(3, "干员丙", race=egg_race()).cid
        with pregnancy.editing(mother) as data:
            laid = {"lay_time": game_time.now()}
            data.eggs = {1: laid, 2: dict(laid)}
        player_collection.put("held_eggs", {7: [mother, 3]})
        report = svc.close_birth_type(EGG)
        self.assertIn("2", report)
        self.assertFalse(svc.birth_type_on(EGG))
        self.assertEqual(pregnancy.of(mother).eggs, {})
        self.assertEqual(player_collection.get("held_eggs"), {})
        svc.open_birth_type(EGG)
        self.assertTrue(svc.birth_type_on(EGG))

    def test_birth_type_text_breaks_lines(self) -> None:
        """验证 birth_type_text 返回名称并将说明中的字面换行符 \\n 转为带空格的换行符。"""
        config = game_config.config_birth_type_setting[EGG]
        self.enterContext(mock.patch.object(config, "info", "甲\\n乙"))
        self.assertEqual(svc.birth_type_text(EGG), (config.name, "甲 \n乙"))


class BanTest(SettingCase):
    """禁止干员列表组装与在册、离册干员禁止切换测试。"""

    def test_rows_skip_player(self) -> None:
        """验证 ban_rows 跳过玩家角色 0，按四位补零序号格式化文本并正确标记已禁止状态。"""
        kernel_data.put(identity.update, self.npc, adv=12)
        roster.forbid(self.stay)
        rows = svc.ban_rows()
        self.assertEqual(
            [(r.npc_id, r.banned) for r in rows],
            [(self.npc, False), (self.stay, True)],
        )
        self.assertEqual(rows[0].text, "[0012]：干员甲")

    def test_toggle_sends_recruited_off_island(self) -> None:
        """验证禁止在册干员会令其离岛并置位置为 ["0", "0"] 返回 True，再次切换则解除禁止并返回 False。"""
        self.assertTrue(svc.toggle_ban(self.npc))
        self.assertTrue(roster.is_forbidden(self.npc))
        self.assertFalse(roster.has(self.npc))
        self.assertEqual(activity.position(self.npc), ["0", "0"])
        self.assertFalse(svc.toggle_ban(self.npc))
        self.assertFalse(roster.is_forbidden(self.npc))

    def test_toggle_keeps_unrecruited_in_place(self) -> None:
        """验证禁止未在册干员只更新禁止集合，不改动其位置并返回 False。"""
        place = activity.position(self.stay)
        self.assertFalse(svc.toggle_ban(self.stay))
        self.assertTrue(roster.is_forbidden(self.stay))
        self.assertEqual(activity.position(self.stay), place)


class PanelAdapterTest(SettingCase):
    """系统设置面板对锁定提示、数值输入与离岛通知的适配测试。"""

    def setUp(self) -> None:
        """构造宽度为 80 的系统设置面板并拦截 NormalDraw.draw 以记录输出文本。"""
        super().setUp()
        self.panel = system_setting.System_Setting_Panel(80)
        self.normal_texts: list[str] = []
        texts = self.normal_texts
        self.enterContext(
            mock.patch.object(
                draw.NormalDraw,
                "draw",
                lambda drawn: texts.append(str(drawn.text)),
            )
        )

    def test_locked_option_shows_notice(self) -> None:
        """验证面板点击基础设置 12 号时不改值并绘制锁定提示。"""
        normal_config.system_setting.base_setting[12] = 0
        self.panel.change_setting_value("基础", 12, 2)
        self.assertEqual(normal_config.system_setting.base_setting[12], 0)
        self.assertEqual(
            self.world.wait_texts,
            ["\n\n该选项需要在诊疗病人面板中修改，无法在此处修改\n\n"],
        )

    def test_count_option_reads_typed_number(self) -> None:
        """验证面板点击绘制设置 11 号后读取用户输入并经服务限制范围后写入配置。"""
        self.enterContext(
            mock.patch.object(flow_handle, "askfor_str", return_value="20")
        )
        self.panel.change_setting_value("绘制", 11, 10)
        self.assertEqual(normal_config.system_setting.draw_setting[11], 9)

    def test_ban_notice_only_for_recruited(self) -> None:
        """验证面板仅在禁止在册干员时绘制离岛提示，禁止未在册干员时不绘制该提示。"""
        self.panel.change_ban_list_cmd(self.stay)
        self.assertNotIn("\n\n干员乙干员已离岛\n\n", self.normal_texts)
        self.panel.change_ban_list_cmd(self.npc)
        self.assertIn("\n\n干员甲干员已离岛\n\n", self.normal_texts)


class BackendIsolationTest(SettingCase):
    """系统设置服务的独立子进程无界面导入边界测试。"""

    def test_fresh_process_runs_every_service_path(self) -> None:
        """在阻止加载界面、结算与窗口模块的子进程中运行服务全部公开路径，验证结果正确且无受限模块加载或导入尝试。"""
        egg = self.world.chara(3, "干员丙", race=egg_race()).cid
        with pregnancy.editing(egg) as data:
            data.eggs = {1: {"lay_time": game_time.now()}}
        chara_life.entertainment_type.set_item(egg, 0, TEND)
        level = min(playthrough.settings(playthrough.DIFFICULTY))
        playthrough.set_setting(playthrough.DIFFICULTY, level, 0)
        setting = normal_config.system_setting
        setting.base_setting[7] = 1
        setting.draw_setting[2] = 0
        state = core.preview(core.state(), self.buffer.effects())
        payload: dict[str, object] = {"egg": egg, "npc": self.npc}
        payload.update(stay=self.stay, level=level, birth=EGG, tend=TEND)
        payload.update(base=setting.base_setting, draw=setting.draw_setting)
        payload["state"] = kernel_state.encode(state)
        command = [sys.executable, "-c", BACKEND_RUN]
        result = subprocess.run(
            command,
            cwd=ROOT,
            input=json.dumps(payload),
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        out = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual([out["loaded"], out["refused"]], [[], []])
        rows = {}
        for kind in svc.Kind:
            shown = svc.option_rows(kind)
            rows[kind.value] = [
                [r.cid, r.control.value, r.option_len] for r in shown
            ]
        self.assertEqual(out["rows"], rows)
        self.assertEqual(out["steps"], ["done", "locked", "ask_count", "done"])
        simple = [out[k] for k in ("ban_link", "text_flag", "level", "number")]
        self.assertEqual(simple, [[7], [1, 1, 1], 1, 9])
        self.assertEqual(out["config"], [50, 50])
        self.assertEqual(
            out["written"][1:], [{"tk_dpi": "50"}, {"language": "en_US"}]
        )
        self.assertIn([EGG, True], out["birth_rows"])
        switch = [out[k] for k in ("closed", "birth_on", "tend", "reopened")]
        self.assertEqual(switch, [True, False, False, True])
        self.assertEqual(out["eggs"], 0)
        bans = [[self.npc, False], [self.stay, False], [egg, False]]
        self.assertEqual(out["ban_rows"], bans)
        self.assertEqual(out["off"], [True, False])
        self.assertEqual(out["after_off"], [False, True, ["0", "0"]])
        self.assertEqual(out["info"], [True, True, True])
        self.assertEqual(out["birth_text"], [True, True])
