"""
PRTS 面板无界面服务测试
=======================
覆盖 PRTS 问答列表与回答拆行、角色口上与事件文件体积扫描、当前版本标签与回退规则、
版本选项与写入切换、面板按钮适配以及无界面子进程导入边界。
"""

import contextlib
import json
import os
import subprocess
import sys
import tempfile
from unittest import mock

from Script.Config import config_def, game_config, normal_config
from Script.Core import flow_handle
from Script.Modules.domains import identity
from Script.Modules.gameplay_resolution import prts_service as svc
from Script.UI.Moudle import draw
from Script.UI.Panel import prts_panel
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

BACKEND_RUN = """
import importlib.abc, sys
BLOCKED = ("Script.UI", "Script.Settle",
    "Script.System.Instruct_System.handle_instruct", "Script.Core.flow_handle",
    "Script.Modules.tk_ui", "tkinter", "_tkinter", "PIL.ImageTk")
def is_blocked(name):
    return any(name == root or name.startswith(root + ".") for root in BLOCKED)
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if is_blocked(fullname):
            raise ImportError(fullname)
        return None
sys.meta_path.insert(0, Blocker())
import contextlib, io, json
from Script.Config import game_config, normal_config
with contextlib.redirect_stdout(io.StringIO()):
    normal_config.init_normal_config()
    game_config.init()
from Script.Kernel import core
from Script.Modules.domains import identity
from Script.Modules.gameplay_resolution import prts_service, working
adv = int(sys.argv[1])
versions = normal_config.system_setting.character_text_version
with working.based_on(core.state()):
    identity.put(identity.Identity(adv, name=sys.argv[2], talk_size=7))
    versions[adv] = int(sys.argv[3])
    out = {
        "questions": [[q.son_type, q.text] for q in prts_service.questions(0)],
        "answer": prts_service.answer_text(0, prts_service.questions(0)[0].son_type),
        "sizes": sorted(prts_service.version_sizes(adv).items()),
        "label": prts_service.version_label(adv),
        "options": [[o.tip_cid, o.version_id, o.title]
            for o in prts_service.version_options(adv)],
    }
    prts_service.choose_version(adv, 0)
    out["chosen"] = versions[adv]
    out["label_after"] = prts_service.version_label(adv)
out["loaded"] = sorted(n for n in sys.modules
    if n.startswith(("Script.UI", "Script.Settle")) or is_blocked(n))
print(json.dumps(out))
"""
""" 在拦截界面、结算与窗口模块的子进程中调用 prts_service 全部公开接口并输出 JSON 结果与受限模块列表的脚本。 """


def tip(cid: int, version_id: int, writer: str) -> config_def.Tip_Chara:
    """
    构造供测试使用的角色提示配置对象 Tip_Chara。
    Keyword arguments:
    cid -- int，提示条目编号
    version_id -- int，文本版本编号
    writer -- str，作者名称
    Return arguments:
    config_def.Tip_Chara -- 填充角色 1 字段的提示配置对象
    """
    one = config_def.Tip_Chara()
    one.__dict__ = {
        "cid": cid,
        "chara_adv_id": 1,
        "version_id": version_id,
        "writer_name": writer,
        "talk_file_path": "",
        "event_file_path": "",
        "text": f"说明{cid}\\n第二行",
    }
    return one


def prts(text: str) -> config_def.Prts:
    """
    构造仅包含文本字段的 PRTS 问答配置对象。
    Keyword arguments:
    text -- str，问题或回答文本
    Return arguments:
    config_def.Prts -- 填充 text 字段的 PRTS 配置对象
    """
    one = config_def.Prts()
    one.__dict__ = {"text": text}
    return one


class PrtsServiceCase(FastTestCase):
    """PRTS 服务测试基类，准备玩家与角色 1、注入模拟提示配置并切换至临时工作目录。"""

    def setUp(self) -> None:
        """初始化角色 0 与角色 1、替换角色提示配置、备份并设置角色 1 当前版本为 2，同时切入临时工作目录。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")
        kernel_data.put(identity.update, 1, talk_size=7)
        self.patch(game_config, "config_tip_chara_data_by_adv", {1: [10, 11]})
        self.patch(
            game_config,
            "config_tip_chara_data",
            {10: tip(10, 1, "甲"), 11: tip(11, 2, "乙")},
        )
        versions = normal_config.system_setting.character_text_version
        self.enterContext(mock.patch.dict(versions))
        self.set_version(2)
        self.root = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(contextlib.chdir(self.root))

    def set_version(self, version_id: int) -> None:
        """
        设置角色 1 在系统设置中的当前文本版本编号。
        Keyword arguments:
        version_id -- int，目标文本版本编号
        Return arguments:
        None -- 无返回值
        """
        normal_config.system_setting.character_text_version[1] = version_id

    def patch(self, owner: object, name: str, value: object) -> None:
        """
        在当前测试用例生命周期内临时替换对象属性。
        Keyword arguments:
        owner -- object，待替换属性的宿主对象或模块
        name -- str，属性名称
        value -- object，替换后的属性值
        Return arguments:
        None -- 无返回值
        """
        self.enterContext(mock.patch.object(owner, name, value))

    def text_file(self, kind: str, name: str, size: int) -> None:
        """
        在临时工作目录的 data/<kind>/chara 下写入指定字节长度的测试文件。
        Keyword arguments:
        kind -- str，目录类别（如 talk 或 event）
        name -- str，文件名
        size -- int，写入的字节长度
        Return arguments:
        None -- 无返回值
        """
        folder = os.path.join(self.root, "data", kind, "chara")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, name), "wb") as handle:
            handle.write(b"x" * size)


class QuestionTest(PrtsServiceCase):
    """PRTS 问题列表组装与回答文本格式化测试。"""

    def test_questions_keep_order_and_pad_ids(self) -> None:
        """验证 questions 保持配置顺序并左补零至三位编号，以及 answer_text 按字面量 \\n 拆行并添加前置空格与换行。"""
        table = {
            3: {
                12: {0: prts("怎样休息"), 1: prts("去宿舍\\n睡觉")},
                5: {0: prts("怎样吃饭"), 1: prts("去食堂")},
            }
        }
        self.patch(game_config, "config_prts_data", table)
        self.assertEqual(
            svc.questions(3),
            [
                svc.Question(12, "[012]怎样休息"),
                svc.Question(5, "[005]怎样吃饭"),
            ],
        )
        self.assertEqual(svc.answer_text(3, 12), " 去宿舍\n 睡觉\n")
        self.assertEqual(svc.answer_text(3, 5), " 去食堂\n")


class VersionSizeTest(PrtsServiceCase):
    """角色口上与事件文件按版本汇总体积的扫描测试。"""

    def test_sizes_sum_talk_and_event_files_per_version(self) -> None:
        """验证 version_sizes 按版本号合并 talk 与 event 目录中匹配角色名或剧情编号的文件体积，并忽略无关文件。"""
        self.text_file("talk", "0001_阿米娅.csv", 1000)
        self.text_file("event", "0001_阿米娅.json", 100)
        self.text_file("talk", "0001_阿米娅_2.csv", 2048)
        self.text_file("event", "x_1_3.json", 10)
        self.text_file("talk", "0002_凯尔希.csv", 5000)
        self.text_file("talk", "1.csv", 5000)
        self.assertEqual(svc.version_sizes(1), {1: 2, 2: 3, 3: 1})
        self.assertEqual(svc.version_sizes(9), {})

    def test_missing_character_matches_the_player_name(self) -> None:
        """验证目标角色不存在时 version_sizes 回退至角色 0 的名称进行文件匹配。"""
        self.text_file("talk", "0000_博士.csv", 3000)
        self.assertEqual(svc.version_sizes(9), {1: 3})


class VersionLabelTest(PrtsServiceCase):
    """当前文本版本展示标签及异常回退规则测试。"""

    def test_label_prefers_file_size_then_talk_size(self) -> None:
        """验证 version_label 优先展示文件扫描体积、无文件时回退至 talk_size，以及版本为 0 时主标签显示为“无”。"""
        self.text_file("talk", "0001_阿米娅_2.csv", 4096)
        self.assertEqual(svc.version_label(1), "by 乙(5kb)(有2个版本)")
        self.set_version(1)
        self.assertEqual(svc.version_label(1), "by 甲(7kb)(有2个版本)")
        self.set_version(0)
        self.assertEqual(svc.version_label(1), "无(有2个版本)")

    def test_unreadable_size_falls_back_to_talk_size(self) -> None:
        """验证文件体积读取抛出 OSError 时 version_label 回退使用角色 talk_size。"""
        self.text_file("talk", "0001_阿米娅_2.csv", 4096)
        self.patch(svc.os.path, "getsize", mock.Mock(side_effect=OSError))
        self.assertEqual(svc.version_label(1), "by 乙(7kb)(有2个版本)")

    def test_single_version_has_no_count(self) -> None:
        """验证角色仅有一个版本时 version_label 不追加版本数量后缀。"""
        self.patch(game_config, "config_tip_chara_data_by_adv", {1: [11]})
        self.assertEqual(svc.version_label(1), "by 乙(7kb)")


class VersionOptionTest(PrtsServiceCase):
    """版本切换选项列表与版本选择写入测试。"""

    def test_options_mark_size_and_current_version(self) -> None:
        """验证 version_options 仅为存在文件的版本附加 KB 体积，并为当前选中版本追加当前版本标记。"""
        self.text_file("talk", "0001_阿米娅.csv", 10)
        self.assertEqual(
            svc.version_options(1),
            [
                svc.VersionOption(
                    10, 1, "版本：1  by 甲 (1kb)", "说明10\\n第二行"
                ),
                svc.VersionOption(
                    11, 2, "版本：2  by 乙(当前版本)", "说明11\\n第二行"
                ),
            ],
        )

    def test_choose_version_moves_the_current_mark(self) -> None:
        """验证 choose_version 更新系统设置后当前版本标记随之移动，传入 0 时标签回退为“无”。"""
        svc.choose_version(1, 1)
        self.assertEqual(
            normal_config.system_setting.character_text_version[1], 1
        )
        titles = [option.title for option in svc.version_options(1)]
        self.assertEqual(titles, ["版本：1  by 甲(当前版本)", "版本：2  by 乙"])
        svc.choose_version(1, 0)
        self.assertEqual(svc.version_label(1), "无(有2个版本)")


class PanelAdapterTest(PrtsServiceCase):
    """ShowCharaNameDraw 面板行标签展示与版本选择按钮联动测试。"""

    def test_row_shows_padded_label_and_buttons_choose_versions(self) -> None:
        """验证角色行包含当前版本标签，且版本切换界面的选择按钮与不使用版本按钮通过服务写入设置。"""
        row = prts_panel.ShowCharaNameDraw(1, 100, True, False, 0)
        self.assertIn("当前选择版本：by 乙(7kb)(有2个版本)", row.info_draw.text)
        buttons: list[draw.CenterButton] = []
        self.enterContext(
            mock.patch.object(
                draw.CenterButton,
                "draw",
                autospec=True,
                side_effect=buttons.append,
            )
        )
        self.patch(flow_handle, "askfor_all", mock.Mock(return_value="返回"))
        row.show_character_text_version()
        picks = {button.return_text: button for button in buttons}
        self.assertLessEqual({"10", "11", " [不使用任何版本] "}, set(picks))
        self.enterContext(mock.patch.dict(flow_handle.cmd_map))
        for key in picks:
            flow_handle.bind_cmd(key, picks[key].cmd_func, picks[key].args)
        flow_handle.cmd_map["10"]()
        self.assertEqual(svc.version_label(1), "by 甲(7kb)(有2个版本)")
        flow_handle.cmd_map[" [不使用任何版本] "]()
        self.assertEqual(svc.version_label(1), "无(有2个版本)")


class BackendIsolationTest(FastTestCase):
    """prts_service 无界面与无结算导入边界的独立子进程测试。"""

    def test_fresh_backend_process_loads_no_ui_or_settle(self) -> None:
        """
        在拦截界面、结算与窗口模块的全新 Python 子进程中以 cp1252 编码运行 prts_service 全部接口，
        验证未加载受限模块且输出与当前进程一致。
        """
        result = subprocess.run(
            [sys.executable, "-c", BACKEND_RUN, "1", "阿米娅", "1"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "cp1252"},
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        out = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(out.pop("loaded"), [])
        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")
        kernel_data.put(identity.update, 1, talk_size=7)
        versions = normal_config.system_setting.character_text_version
        self.enterContext(mock.patch.dict(versions, {1: 1}))
        self.enterContext(contextlib.chdir(ROOT))
        first = svc.questions(0)[0].son_type
        self.assertIn(1, svc.version_sizes(1))
        expected = {
            "questions": [[q.son_type, q.text] for q in svc.questions(0)],
            "answer": svc.answer_text(0, first),
            "sizes": [
                list(pair) for pair in sorted(svc.version_sizes(1).items())
            ],
            "label": svc.version_label(1),
            "options": [
                [o.tip_cid, o.version_id, o.title]
                for o in svc.version_options(1)
            ],
            "chosen": 0,
            "label_after": "无",
        }
        self.assertEqual(out, expected)
