# -*- coding: UTF-8 -*-
"""
淫纹 mod 存档双向兼容往返测试：四个阶段各起一个子进程（"卸 mod"只能靠"这个进程从没加载过 mod"来模拟）
    阶段 1 本体建档：不加载 mod；删掉角色的 mod_data 属性，模拟本字段出现之前的旧档；存档
    阶段 2 装 mod 读档：mod_data 为空、无淫纹；记无淫纹增量 g0；刻 boost:vagina 后增量 == int(g0×1.5)；跑一次 update_new_day；存档
    阶段 3 卸 mod 读档：拦截 _erark_mod_* 的导入；数据原样、增量 == g0、state_gain 未挂函数；存档
    阶段 4 再装 mod 读档：数据原样、增量恢复 int(g0×1.5)
每阶段存档后用 mod_hook.validate_mod_data 检查存档文件里全部角色的 mod_data。
存档目录猴补到临时目录，不碰 save/、config.ini、mod/mod_config.json；mod 用 ModManager().scan_mods() + _load_single_mod 加载。
用法：python3 mod/lewd_tattoo/tests/test_save_roundtrip.py
"""
import json
import os
import subprocess
import sys
import tempfile

SAVE_ID = "tattoo_roundtrip"
""" 临时存档id """
NPC_ID = 9001
""" 测试干员id """
VAGINA = 4
""" 阴道快感状态id """
KEYS = ["boost:vagina"]
""" 阶段 2 刻下的效果 """
MOD_PREFIX = "_erark_mod_"
""" mod 私有包名前缀（阶段 3 拦截） """


def run_driver() -> None:
    """
    驱动器：依次起 4 个子进程，任一阶段失败即停止，最后汇总
    Keyword arguments:
    无
    Return arguments:
    None
    """
    save_dir = tempfile.mkdtemp(prefix="tattoo_roundtrip_")
    names = {1: "本体建档", 2: "装 mod 读档、刻淫纹", 3: "卸 mod 读档", 4: "再装 mod 读档"}
    failed = []
    for phase in (1, 2, 3, 4):
        print(f"\n######## 阶段 {phase}：{names[phase]} ########", flush=True)
        result = subprocess.run([sys.executable, os.path.abspath(__file__), "--phase", str(phase), save_dir], capture_output=True, text=True, encoding="utf-8", errors="replace")
        lines = [line for line in result.stdout.splitlines() if line.startswith(("  [OK]", "  [FAIL]", "PASS=", "==== ", "  -"))]
        print("\n".join(lines))
        if result.returncode != 0:
            failed.append(phase)
            print(result.stderr[-3000:])
            break
    print("=" * 50)
    print("往返测试：" + ("全部阶段通过" if not failed else f"阶段 {failed[0]} 失败"))
    print(f"临时存档目录：{save_dir}")
    sys.stdout.flush()
    os._exit(0 if not failed else 1)


def run_phase(phase: int, save_dir: str) -> None:
    """
    子进程：执行一个阶段
    Keyword arguments:
    phase -- 阶段号 1~4
    save_dir -- 临时存档根目录
    Return arguments:
    None
    """
    # 阶段 3：拦截 mod 私有包的导入，确保这个进程里 mod 不可能被加载
    if phase == 3:
        import importlib.abc

        class _BlockMod(importlib.abc.MetaPathFinder):
            """拒绝导入任何 mod 私有包"""

            def find_spec(self, name, path, target=None):
                """
                Keyword arguments:
                name -- 模块名
                path -- 搜索路径
                target -- 目标模块
                Return arguments:
                None -- 不拦截时
                """
                if name.startswith(MOD_PREFIX):
                    raise ImportError(f"阶段 3 禁止导入 {name}")
                return None

        sys.meta_path.insert(0, _BlockMod())

    tests_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(tests_dir, "..", "..", "..", "tools", "tests", "education"))
    from _bootstrap import cache, check, finish, make_character, section  # noqa: E402  无头引导

    import pickle

    from Script.Core import game_type, mod_hook, mod_manager, save_handle
    from Script.Settle import common_default

    # 存档目录猴补到临时目录
    save_handle.get_save_dir_path = lambda save_id: os.path.join(save_dir, save_id)
    record_path = os.path.join(save_dir, "record.json")

    def load_mod():
        """
        经 ModManager 加载淫纹 mod（不改 mod_config.json）
        Keyword arguments:
        无
        Return arguments:
        module -- 私有包
        """
        manager = mod_manager.ModManager()
        infos = {info.mod_id: info for info in manager.scan_mods()}
        check("ModManager 加载淫纹 mod", manager._load_single_mod(infos["lewd_tattoo"]) is not False)
        return sys.modules[MOD_PREFIX + "lewd_tattoo"]

    def gain() -> int:
        """
        清零快感后，以本体 base_chara_state_common_settle 结算一次阴道快感，返回增量
        Keyword arguments:
        无
        Return arguments:
        int -- 阴道快感增量
        """
        npc = cache.character_data[NPC_ID]
        for sid in list(npc.status_data):
            npc.status_data[sid] = 0
        common_default.base_chara_state_common_settle(NPC_ID, 10, VAGINA, 30, change_data=game_type.CharacterStatusChange())
        return npc.status_data[VAGINA]

    def save_and_validate() -> None:
        """
        存档，再从文件读回，校验全部角色的 mod_data 只由内建类型构成
        Keyword arguments:
        无
        Return arguments:
        None
        """
        save_handle.establish_save(SAVE_ID)
        with open(os.path.join(save_dir, SAVE_ID, "1"), "rb") as f:
            saved = pickle.load(f)
        errors = []
        for cid, character in saved.character_data.items():
            if "mod_data" in character.__dict__:
                errors += mod_hook.validate_mod_data(character.mod_data, f"character_data[{cid}].mod_data")
        check("存档文件里的 mod_data 全是内建类型", errors == [], errors)

    def load() -> game_type.Character:
        """
        以本体 input_load_save 读档
        Keyword arguments:
        无
        Return arguments:
        game_type.Character -- 读档后的测试干员
        """
        save_handle.input_load_save(SAVE_ID)
        check("读档后测试干员存在", NPC_ID in cache.character_data)
        return cache.character_data[NPC_ID]

    def read_record() -> dict:
        """
        读取前面阶段记下的数据
        Keyword arguments:
        无
        Return arguments:
        dict -- 记录
        """
        with open(record_path, encoding="utf-8") as f:
            return json.load(f)

    section(f"阶段 {phase}")
    if phase == 1:
        # 引导里的罗德岛与大地图数据不完整（医疗日计数为 None、感染率为空，读档会崩），按新开游戏的方式补齐
        from Script.Design import attr_calculation, basement

        cache.rhodes_island = basement.get_base_zero()
        cache.country = attr_calculation.get_country_reset(cache.country)
        if 0 not in cache.character_data:
            make_character(0, "博士").sex = 0
        npc = make_character(NPC_ID, "往返干员")
        npc.sex = 1
        npc.sp_flag.imprisonment = 1
        check("未加载 mod：state_gain 没挂函数", not mod_hook.state_gain.has_fns())
        # 模拟本字段出现之前的旧档：角色对象里没有 mod_data
        for character in cache.character_data.values():
            character.__dict__.pop("mod_data", None)
        save_and_validate()
        with open(os.path.join(save_dir, SAVE_ID, "1"), "rb") as f:
            saved = pickle.load(f)
        check("存档里的角色确实没有 mod_data 属性", all("mod_data" not in c.__dict__ for c in saved.character_data.values()))
    elif phase == 2:
        package = load_mod()
        npc = load()
        check("旧档读入后 mod_data 为空 dict", npc.mod_data == {}, npc.mod_data)
        check("读到'没有淫纹'", not package.store.view(NPC_ID).present)
        g0 = gain()
        check("无淫纹增量 g0 > 0", g0 > 0, g0)
        package.store.write(NPC_ID, KEYS)
        g1 = gain()
        check("刻 boost:vagina 后增量 == int(g0×1.5)", g1 == int(g0 * 1.5), (g0, g1))
        from Script.Settle import past_day_settle

        past_day_settle.update_new_day()
        check("update_new_day 后淫纹仍在", package.store.active_keys(NPC_ID) == frozenset(KEYS))
        g0_after = gain()
        check("update_new_day 后增量仍为 int(g0×1.5)", g0_after == int(g0 * 1.5), (g0, g0_after))
        entry = cache.character_data[NPC_ID].mod_data["lewd_tattoo"]
        with open(record_path, "w", encoding="utf-8") as f:
            json.dump({"g0": g0, "entry": entry}, f, ensure_ascii=False)
        save_and_validate()
    elif phase == 3:
        record = read_record()
        npc = load()
        check("mod 私有包没有被导入", not any(name.startswith(MOD_PREFIX) for name in sys.modules))
        check("state_gain 没挂函数", not mod_hook.state_gain.has_fns())
        check("淫纹数据原样留在存档", npc.mod_data.get("lewd_tattoo") == record["entry"], npc.mod_data)
        g = gain()
        check("卸 mod 后增量 == g0（淫纹无效果）", g == record["g0"], (record["g0"], g))
        save_and_validate()
    elif phase == 4:
        record = read_record()
        package = load_mod()
        npc = load()
        check("淫纹数据经过卸 mod 再存档仍原样", npc.mod_data.get("lewd_tattoo") == record["entry"], npc.mod_data)
        check("淫纹恢复激活", package.store.active_keys(NPC_ID) == frozenset(KEYS))
        g = gain()
        check("再装 mod 后增量恢复 int(g0×1.5)", g == int(record["g0"] * 1.5), (record["g0"], g))
        save_and_validate()
    finish()


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--phase":
        run_phase(int(sys.argv[2]), sys.argv[3])
    else:
        run_driver()
