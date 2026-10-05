# -*- coding: UTF-8 -*-
"""
启动顺序测试：按 game.py 的顺序，在 game_config.init() 之后、其余 Script 模块导入之前加载本 mod
（与 init_mod_system 的位置相同；不读写 mod/mod_config.json，直接调 ModManager._load_single_mod），
再导入其余模块，确认本体后续导入不会冲掉或撞上本 mod 注册的东西
用法：python3 mod/lewd_tattoo/tests/test_startup_order.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import REPO_ROOT, check, finish  # noqa: E402

os.chdir(REPO_ROOT)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ==== game.py 第 10~31 行 ====
import auto_build_config  # noqa: F401,E402
from Script.Config import normal_config  # noqa: E402
from Script.Core import cache_control, game_type  # noqa: E402

cache_control.cache = game_type.Cache()
normal_config.init_normal_config()
from Script.Config import character_config, game_config  # noqa: E402

game_config.init()

# ==== game.py 第 35 行 init_mod_system 的位置：只加载本 mod ====
print("==== 加载 mod ====")
from Script.Core import mod_hook, mod_manager  # noqa: E402

manager = mod_manager.ModManager()
infos = {info.mod_id: info for info in manager.scan_mods()}
check("scan_mods 能找到 lewd_tattoo", "lewd_tattoo" in infos)
manager._load_single_mod(infos["lewd_tattoo"])
check("五个钩子点都已挂上", all(hook.has_fns() for hook in (mod_hook.state_gain, mod_hook.edge_judged, mod_hook.daily_desire_growth, mod_hook.character_info_draw_list, mod_hook.desire_written)))
package = sys.modules.get("_erark_mod_lewd_tattoo")
check("私有包已进 sys.modules", package is not None)
check("mod 加载时没有导入 ui 模块", "_erark_mod_lewd_tattoo.ui" not in sys.modules)

# ==== game.py 第 45~57 行：其余模块 ====
character_config.init_character_tem_data()
from Script.Config import map_config  # noqa: E402

map_config.init_map_data()
from Script.Design import character_handle, game_time, start_flow  # noqa: E402,F401
import Script.Settle  # noqa: E402,F401
import Script.StateMachine  # noqa: E402,F401
import Script.System.Medical_System  # noqa: E402,F401
from Script.Core import constant, flow_handle  # noqa: E402,F401
import Script.UI.Flow  # noqa: E402,F401

character_handle.init_character_tem()
game_time.init_time()

print("==== 本体导入完毕后 ====")
from _erark_mod_lewd_tattoo import instruct  # noqa: E402

for instruct_id in (instruct.APPLY_ID, instruct.ADJUST_ID):
    check(f"{instruct_id} 仍在 handle_instruct_data", instruct_id in constant.handle_instruct_data)
    check(f"{instruct_id} 仍在 ARTS 类型表", instruct_id in constant.instruct_type_data[constant.InstructType.ARTS])
    cid = constant.instruct_id_to_cid.get(instruct_id)
    check(f"{instruct_id} 的 cid 只对应本指令", cid is not None and constant.cid_to_instruct_id.get(cid) == instruct_id, cid)
for key in (instruct.P_TARGET_ELIGIBLE, instruct.P_SANITY_ENOUGH, instruct.P_TARGET_HAS, instruct.P_TARGET_HAS_NOT):
    check(f"前提 {key} 仍已注册", key in constant.handle_premise_data)
all_cids = [constant.instruct_id_to_cid[i] for i in constant.instruct_id_to_cid]
check("全体指令 cid 不重复", len(all_cids) == len(set(all_cids)))
check("本体 ARTS 指令照常注册（不止本 mod 两个）", len(constant.instruct_type_data[constant.InstructType.ARTS]) > 2)
check("share_blankly 的行为映射没被本 mod 覆盖", constant.behavior_id_to_instruct_id.get("share_blankly") not in (instruct.APPLY_ID, instruct.ADJUST_ID))

finish()
