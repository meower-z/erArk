# -*- coding: UTF-8 -*-
"""
erArk 无头验证的公共引导
========================
无头脚本与测试都从这里取：
    boot()       -- 按 game.py 的顺序初始化游戏配置与缓存，不启动 Tk / Web
    mute_ui()    -- 屏蔽全部绘制，记录 WaitDraw 文本，给 askfor_* 打桩
    new_chara()  -- 造一个能跑通结算 / 前提 / 口上的角色夹具，并登记进 cache
    check() / finish() -- 记录断言，打印汇总后用 os._exit 结束进程

导入本模块即装上 sys.excepthook：未捕获异常打印堆栈后 os._exit(2)。
游戏导入链会起非守护的 Flask 线程，脚本正常返回或抛异常都不会自行退出，
所以脚本必须以 finish() 结尾，崩溃则由 excepthook 收尾。

仓库根目录取当前目录：请在 erArk 仓库根目录下运行脚本，并先 sys.path.insert(0, "tools/tests") 再导入本模块。
"""
import os
import sys
import traceback

ROOT = os.getcwd()
""" 被测 erArk checkout 的根目录（当前目录） """
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCENE = ["宿舍", "1区", "101"]
""" new_chara 的默认位置：一间真实宿舍。场景路径必须是 cache.scene_data 的真实键 """

PASS = 0
""" 已通过的断言数 """
FAIL = []
""" 失败的断言名列表 """


def _exit_on_error(exc_type, exc, tb):
    """
    未捕获异常时打印堆栈与汇总，并以退出码 2 立即结束进程
    Keyword arguments:
    exc_type -- 异常类型
    exc -- 异常对象
    tb -- 回溯对象
    Return arguments:
    无（进程直接退出）
    """
    traceback.print_exception(exc_type, exc, tb)
    print(f"\nPASS={PASS} FAIL={len(FAIL)} (crashed)")
    sys.stdout.flush()
    os._exit(2)


sys.excepthook = _exit_on_error


def boot():
    """
    按 game.py 的顺序初始化游戏（顺序不能乱），并补上结算必需的全局前置
    Keyword arguments:
    无
    Return arguments:
    game_type.Cache -- 游戏缓存（读档会原地更新它，引用一直有效）
    功能描述:
        import auto_build_config 会按需增量重建 data/ 下的生成物；
        cache 必须在 game_config.init() 之前建好；
        Script.Settle / Script.StateMachine 靠装饰器注册结算器与状态机，缺了会 KeyError；
        不加载 mod 系统，也不导入 Script.UI.Flow。
    """
    import auto_build_config  # noqa: F401
    from Script.Config import normal_config
    from Script.Core import game_type, cache_control

    cache_control.cache = game_type.Cache()
    normal_config.init_normal_config()
    from Script.Config import game_config, character_config

    game_config.init()
    character_config.init_character_tem_data()
    from Script.Config import map_config

    map_config.init_map_data()
    from Script.Design import attr_calculation, character_handle, game_time, map_handle
    import Script.Settle  # noqa: F401
    import Script.StateMachine  # noqa: F401

    character_handle.init_character_tem()
    game_time.init_time()
    cache = cache_control.cache
    # 数值结算会读 all_system_setting.difficulty_setting 等，Cache() 默认是空壳；读档时会被存档里的值覆盖
    cache.all_system_setting = attr_calculation.get_system_setting_zero()
    assert map_handle.get_map_system_path_str_for_list(SCENE) in cache.scene_data
    print("初始化完成，游戏时间 =", cache.game_time)
    return cache


def mute_ui():
    """
    屏蔽全部绘制类，并给等待输入的函数打桩
    Keyword arguments:
    无
    Return arguments:
    list[str] -- WaitDraw 绘制过的文本，按绘制顺序追加；调用方可随时 clear()
    功能描述:
        askfor_all 返回第一个可选项：面板的 `while 1: ... if yrn in return_list: break`
        按钮循环才能退出。若自行替换它，返回值必须是 return_list 里的成员。
    """
    from Script.Core import flow_handle
    from Script.UI.Moudle import draw

    wait_texts = []

    def record_wait_draw(self, *args, **kwargs):
        """
        记录型 WaitDraw 桩：把绘制文本收进 wait_texts
        Keyword arguments:
        self -- 绘制对象
        Return arguments:
        无
        """
        if getattr(self, "text", None):
            wait_texts.append(str(self.text))

    for cls_name in dir(draw):
        cls = getattr(draw, cls_name)
        if isinstance(cls, type) and hasattr(cls, "draw"):
            try:
                cls.draw = lambda self, *args, **kwargs: None
            except (AttributeError, TypeError):
                pass
    draw.WaitDraw.draw = record_wait_draw
    flow_handle.askfor_all = lambda return_list, *args, **kwargs: return_list[0] if return_list else ""
    flow_handle.askfor_wait = lambda *args, **kwargs: None
    return wait_texts


def new_chara(cid, name="测试干员", position=None, race=0, adv=0):
    """
    造一个能跑通结算 / 前提 / 口上 / 面板链路的最小角色夹具，并登记进 cache
    Keyword arguments:
    cid -- 角色id（0 为玩家）
    name -- 角色名
    position -- 初始场景路径列表，默认 SCENE
    race -- 种族id（生育方式等读 game_config.config_race[race]，测卵生 / 多胎时显式传入）
    adv -- 剧情npc编号，影响可穿服装的筛选
    Return arguments:
    game_type.Character -- 已登记的角色对象
    功能描述:
        game_type.Character() 的多数容器字段初值是空 dict，代码普遍直接下标访问，不预填就 KeyError。
        各字段的置零函数与缺失时的报错见 references/headless-unit.md 的角色夹具字段表。
        NPC 进 cache.npc_id_got，并登记进所在场景的 character_list，与真实在岗干员一致。
    """
    from Script.Core import cache_control, game_type
    from Script.Design import attr_calculation, map_handle

    cache = cache_control.cache
    position = list(position if position is not None else SCENE)
    cd = game_type.Character()
    cd.cid = cid
    cd.name = name
    cd.adv = adv
    cd.sex = 1
    cd.race = race
    cd.cloth = attr_calculation.get_cloth_zero()
    cd.cloth.cloth_locker_in_dormitory = attr_calculation.get_cloth_locker_in_dormitory_zero()
    cd.cloth.cloth_locker_in_shower = attr_calculation.get_shower_cloth_locker_zero()
    cd.dirty = attr_calculation.get_zero_dirty()
    cd.talent = attr_calculation.get_talent_zero({})
    cd.ability = attr_calculation.get_ability_zero({})
    cd.status_data = attr_calculation.get_status_zero({})
    cd.juel = attr_calculation.get_juel_zero({})
    cd.experience = attr_calculation.get_experience_zero({})
    cd.second_behavior = attr_calculation.get_second_behavior_zero({})
    cd.h_state = attr_calculation.get_h_state_reset(cd.h_state)
    cd.body_manage = attr_calculation.get_body_manage_zero()
    cd.assistant_services = attr_calculation.get_assistant_services_zero()
    cd.favorability = {0: 0}
    cd.social_contact = {}
    cd.social_contact_data = {}
    cd.talent[121] = 1
    cd.hit_point_max = cd.hit_point = 100
    cd.mana_point_max = cd.mana_point = 100
    cd.dormitory = map_handle.get_map_system_path_str_for_list(SCENE)
    cd.behavior.start_time = cache.game_time
    cd.position = position
    cache.character_data[cid] = cd
    if cid:
        cache.npc_id_got.add(cid)
    cache.scene_data[map_handle.get_map_system_path_str_for_list(position)].character_list.add(cid)
    return cd


def check(name, cond, extra=""):
    """
    记录并打印一条断言结果
    Keyword arguments:
    name -- 断言名
    cond -- 断言条件
    extra -- 失败时附带打印的实际值
    Return arguments:
    bool -- 断言是否通过
    """
    global PASS
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
        return True
    FAIL.append(name)
    print(f"  [FAIL] {name} {extra}")
    return False


def finish():
    """
    打印断言汇总并结束进程：全过退出码 0，有失败退出码 1
    Keyword arguments:
    无
    Return arguments:
    无（进程直接退出）
    """
    print()
    print("=" * 50)
    print(f"PASS={PASS} FAIL={len(FAIL)}")
    for name in FAIL:
        print("  -", name)
    sys.stdout.flush()
    os._exit(0 if not FAIL else 1)
