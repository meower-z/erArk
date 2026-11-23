"""角色服装：换装、穿脱衣物、衣柜的读写与衣物精液，以及玩家获得角色的内裤与袜子"""

import random
from types import FunctionType
from Script.Core import get_text
from Script.Config import game_config, normal_config
from Script.Design import attr_calculation, handle_premise, map_handle
from Script.Modules.domains import abilities, activity, dirty, prison, wardrobe
from Script.Modules.domains import npc_template
from Script.UI.Moudle import draw
from Script.Modules.domains import identity
from Script.Core import constant

window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """
_: FunctionType = get_text._
""" 翻译api """


def get_npc_cloth(character_id: int) -> None:
    """
    根据csv换一身同样的衣服，然后随机内衣
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    无
    """
    if character_id:
        wardrobe.set(
            character_id, "cloth_wear", attr_calculation.get_cloth_wear_zero()
        )
        # 换衣时去除服装部位上的避孕套装饰
        from Script.System.Item_System import condom_handle

        condom_handle.remove_cloth_decoration(character_id)
        tem_character = npc_template.get(character_id)
        if tem_character is None:
            return  # 模板不存在时安全返回

        # 如果装备严重损坏，则换为通用衣服
        if handle_premise.handle_self_equipment_damaged_ge_3(character_id):
            get_common_cloth(character_id)
        # 否则正常换衣服
        else:
            for cloth_id in tem_character.Cloth:
                type = game_config.config_clothing_tem[cloth_id].clothing_type
                wardrobe.append(character_id, "cloth_wear", type, cloth_id)
            get_underwear(character_id)
            chara_special_wear_cloth(character_id)


CLOTH_LOCKER_TYPE_SHOWER = 2
""" 衣柜类型_大浴场（更衣室）衣柜 """
CLOTH_LOCKER_TYPE_DORMITORY = 3
""" 衣柜类型_宿舍衣柜 """

CLOTH_LOCKER_ATTR_NAME = {
    CLOTH_LOCKER_TYPE_SHOWER: "cloth_locker_in_shower",
    CLOTH_LOCKER_TYPE_DORMITORY: "cloth_locker_in_dormitory",
}
""" 衣柜类型对应的CLOTH属性名 """


def get_cloth_locker_type_by_scene(scene_tag: list[str]) -> int:
    """
    根据场景标签判断该场景使用哪个衣柜
    博士房间没有独立衣柜：同居助理的宿舍地址已被改写为博士房间，
    因此那里用的就是她的宿舍衣柜
    Keyword arguments:
    scene_tag -- 场景标签列表
    Return arguments:
    int -- 衣柜类型（2大浴场更衣室/3宿舍）
    """
    if "Locker_Room" in scene_tag:
        return CLOTH_LOCKER_TYPE_SHOWER
    return CLOTH_LOCKER_TYPE_DORMITORY


def get_now_cloth_locker_type(character_id: int) -> int:
    """
    根据角色当前所在场景，判断应该使用哪个衣柜
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 衣柜类型（2大浴场更衣室/3宿舍）
    """
    now_scene_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id)
    )
    now_scene_data = constant.scene_data[now_scene_str]
    return get_cloth_locker_type_by_scene(now_scene_data.scene_tag)


def get_cloth_locker_by_type(character_id: int, locker_type: int) -> dict:
    """
    按衣柜类型取出角色对应的衣柜数据
    Keyword arguments:
    character_id -- 角色id
    locker_type -- 衣柜类型（2大浴场更衣室/3宿舍）
    Return arguments:
    dict -- 部位到衣服id列表，是按服装新建的副本，改它不改衣柜
    """
    cloth = wardrobe.clone_mutable_snapshot(character_id)
    return getattr(cloth, CLOTH_LOCKER_ATTR_NAME[locker_type])


def empty_cloth_locker_part(
    character_id: int, locker_type: int, part: int
) -> None:
    """
    把角色一个衣柜里一个部位的衣服清空，写进当前缓冲区
    Keyword arguments:
    character_id -- 角色id
    locker_type -- 衣柜类型（2大浴场更衣室/3宿舍）
    part -- 服装部位
    """
    name = CLOTH_LOCKER_ATTR_NAME[locker_type]
    wardrobe.set_part(character_id, name, part, [])


def get_cloth_locker_zero_by_type(locker_type: int) -> dict:
    """
    按衣柜类型获得一个全空的衣柜数据
    Keyword arguments:
    locker_type -- 衣柜类型（2大浴场更衣室/3宿舍）
    Return arguments:
    dict -- 全空的衣柜数据
    """
    if locker_type == CLOTH_LOCKER_TYPE_SHOWER:
        return attr_calculation.get_shower_cloth_locker_zero()
    return attr_calculation.get_cloth_locker_in_dormitory_zero()


def get_cloth_from_dormitory_locker(character_id: int) -> None:
    """
    清空身上的旧衣服，从宿舍的衣柜里穿上衣服、内衣内裤，并转移衣柜中的精液数据到穿着的衣服上\n
    Keyword arguments:\n
    character_id -- 角色id\n
    Return arguments:\n
    无
    """
    if character_id:
        # 监禁的根据要求换对应服装
        if handle_premise.handle_imprisonment_1(character_id):
            handle_prisoner_clothing(character_id)
            return
        # 临盆或产后的换病号服
        elif handle_premise.handle_self_parturient_or_postpartum(character_id):
            get_patient_cloth(character_id)
            return
        tem_character = npc_template.get(character_id)
        if tem_character is None:
            return  # 模板不存在时安全返回
        tem_cloth_list = tem_character.Cloth.copy()
        # 同居助理的宿舍地址即博士房间，因此她在博士房间起床时读到的也是这份宿舍衣柜
        cloth = wardrobe.clone_mutable_snapshot(character_id)
        now_locker = cloth.cloth_locker_in_dormitory
        # 检查宿舍衣柜中是否有衣服
        wear_locker_flag = False
        for cloth_type in now_locker:
            if len(now_locker[cloth_type]):
                wear_locker_flag = True
                # 去掉里面不符合角色csv的衣服
                for cloth_id in now_locker[cloth_type].copy():
                    if cloth_id not in tem_cloth_list:
                        now_locker[cloth_type].remove(cloth_id)
                    else:
                        tem_cloth_list.remove(cloth_id)
        # 宿舍衣柜中有衣服的话，穿上衣服
        if wear_locker_flag:
            wardrobe.set(
                character_id,
                "cloth_wear",
                attr_calculation.get_cloth_wear_zero(),
            )
            # 换衣时去除服装部位上的避孕套装饰
            from Script.System.Item_System import condom_handle

            condom_handle.remove_cloth_decoration(character_id)
            wardrobe.set(character_id, "cloth_wear", now_locker)
            wardrobe.set(
                character_id,
                "cloth_locker_in_dormitory",
                attr_calculation.get_cloth_locker_in_dormitory_zero(),
            )
            # 如果在范例里的衣服还有没穿着的，则穿上
            for cloth_id in tem_cloth_list:
                type = game_config.config_clothing_tem[cloth_id].clothing_type
                # 跳过内衣内裤
                if type in {6, 9}:
                    continue
                wardrobe.append(character_id, "cloth_wear", type, cloth_id)
            # 换内衣内裤
            get_underwear(character_id)
            # 将衣柜里的衣服精液转移到穿着的衣服上
            locker_cloth_semen_to_wear_cloth_semen(character_id)
        # 宿舍衣柜中没有衣服的话，根据csv穿衣服
        if not wear_locker_flag:
            get_npc_cloth(character_id)

        # 如果被命令了每条换新袜子
        if handle_premise.handle_ask_wear_different_socks_everyday(
            character_id
        ):
            get_socks(character_id)

    # 穿特殊服装
    chara_special_wear_cloth(character_id)


def handle_prisoner_clothing(character_id: int) -> None:
    """
    处理囚犯的服装\n
    参数:
        character_id -- 囚犯角色的id
    返回:
        无
    """
    if character_id:
        cloth_setting = prison.setting(2)
        underwear_setting = prison.setting(3)
        # 全裸
        if cloth_setting == 0:
            get_all_cloth_off(character_id)
        # 囚服
        elif cloth_setting == 1:
            get_prison_cloth(character_id)
        # 正常衣服
        else:
            get_npc_cloth(character_id)
        # 清空内衣
        wardrobe.set_part(character_id, "cloth_wear", 6, [])
        wardrobe.set_part(character_id, "cloth_wear", 9, [])
        # 清空袜子
        if underwear_setting == 0:
            wardrobe.set_part(character_id, "cloth_wear", 10, [])
        # 提供情趣内衣与袜子
        elif underwear_setting == 1:
            get_underwear(character_id, type_cid=2)
            get_socks(character_id)
        # 提供正常内衣与袜子
        else:
            get_underwear(character_id)
            get_socks(character_id)
        chara_special_wear_cloth(character_id)


def get_random_underwear() -> tuple[int, int]:
    """
    随机返回一件内衣和一件内裤
    Keyword arguments:
    无
    Return arguments:
    无
    """
    bra_list = []
    pan_list = []
    for cloth_id in game_config.config_clothing_tem:
        cloth = game_config.config_clothing_tem[cloth_id]
        if cloth.clothing_type == 6:
            bra_list.append(cloth_id)
        elif cloth.clothing_type == 9:
            pan_list.append(cloth_id)
    bra_id = random.choice(bra_list)
    pan_id = random.choice(pan_list)
    return bra_id, pan_id


def get_underwear(
    character_id: int, part_flag: int = 0, type_cid: int = 0
) -> None:
    """
    随机穿内衣，包括胸罩和内裤\n
    Keyword arguments:\n
    character_id -- 角色id\n
    part_flag -- 是否只穿某个部件，0都穿，1仅胸衣，2仅内裤\n
    Return arguments:\n
    无
    """
    talent = abilities.talent(character_id)
    character_data = identity.of(character_id)
    # 60,幼女,61,萝莉,62,少女,63,成年,64,长生者

    # 遍历全衣服，以下分别是正常/童装/情趣的胸衣和内裤
    bra_nor_list = []
    bra_loli_list = []
    bra_H_list = []
    pan_nor_list = []
    pan_loli_list = []
    pan_H_list = []
    for cloth_id in game_config.config_clothing_tem:
        cloth = game_config.config_clothing_tem[cloth_id]
        # 跳过非自己的衣服
        if cloth.npc != 0 and cloth.npc != character_data.adv:
            continue
        if cloth.clothing_type == 6:
            if cloth.tag == 0:
                bra_nor_list.append(cloth_id)
            elif cloth.tag == 1:
                bra_loli_list.append(cloth_id)
            elif cloth.tag == 2:
                bra_H_list.append(cloth_id)
        elif cloth.clothing_type == 9:
            if cloth.tag == 0:
                pan_nor_list.append(cloth_id)
            elif cloth.tag == 1:
                pan_loli_list.append(cloth_id)
            elif cloth.tag == 2:
                pan_H_list.append(cloth_id)

    # 解锁了情趣内衣的情况下，对2级攻略以上的角色增加情趣内衣
    character_fall_level = attr_calculation.get_character_fall_level(
        character_id
    )
    if character_fall_level >= 2:
        from Script.Modules.domains import player_collection

        if player_collection.bonus(102):
            bra_nor_list += bra_H_list
            pan_nor_list += pan_H_list

    # 判断是否需要穿，包括是否已穿和part_flag限制
    if (
        not len(wardrobe.of(character_id).cloth_wear[6])  # 当前没有穿胸衣
        and part_flag != 2  # 本次穿胸衣
        and len(bra_nor_list)  # 有可穿的胸衣
        and not handle_premise.handle_ask_not_wear_corset(
            character_id
        )  # 没有禁止穿胸衣
    ):
        # 随机选择胸衣和内裤
        # 指定类别
        if type_cid == 2 and len(bra_H_list):
            bra_id = random.choice(bra_H_list)
            wardrobe.append(character_id, "cloth_wear", 6, bra_id)
        # 童装：幼女
        elif talent[102]:
            bra_id = random.choice(bra_loli_list)
            wardrobe.append(character_id, "cloth_wear", 6, bra_id)
        # 正常
        else:
            bra_id = random.choice(bra_nor_list)
            wardrobe.append(character_id, "cloth_wear", 6, bra_id)

    if (
        not len(wardrobe.of(character_id).cloth_wear[9])  # 当前没有穿内裤
        and part_flag != 1  # 本次穿内裤
        and len(pan_nor_list)  # 有可穿的内裤
    ):
        if type_cid == 2 and len(pan_H_list):
            pan_id = random.choice(pan_H_list)
            wardrobe.append(character_id, "cloth_wear", 9, pan_id)
        elif talent[102]:
            pan_id = random.choice(pan_loli_list)
            wardrobe.append(character_id, "cloth_wear", 9, pan_id)
        else:
            pan_id = random.choice(pan_nor_list)
            wardrobe.append(character_id, "cloth_wear", 9, pan_id)


def get_socks(character_id: int) -> None:
    """
    随机穿袜子
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    无
    """
    character_data = identity.of(character_id)

    # 遍历全衣服
    socks_list = []
    for cloth_id in game_config.config_clothing_tem:
        cloth = game_config.config_clothing_tem[cloth_id]
        # 跳过非自己的衣服
        if cloth.npc != 0 and cloth.npc != character_data.adv:
            continue
        if cloth.clothing_type == 10:
            socks_list.append(cloth_id)

    # 清空旧袜子
    wardrobe.set_part(character_id, "cloth_wear", 10, [])
    # 随机穿袜子
    socks_id = random.choice(socks_list)
    wardrobe.append(character_id, "cloth_wear", 10, socks_id)


def undress_out_cloth(character_id: int) -> None:
    """
    脱掉外衣
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    无
    """
    if character_id:
        for i in {5, 8}:
            wardrobe.set_part(character_id, "cloth_wear", i, [])
        chara_special_wear_cloth(character_id)


def strip_down_till_socks_and_gloves_left(character_id: int) -> None:
    """
    脱到只穿袜子手套等
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    无
    """
    if character_id:
        for i in {5, 6, 8, 9}:
            wardrobe.set_part(character_id, "cloth_wear", i, [])
        chara_special_wear_cloth(character_id)


def pl_get_chara_pan(character_id: int) -> None:
    """
    玩家获得该角色的内裤
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    无
    """
    if character_id > 0:
        character_data = identity.of(character_id)
        # 如果角色穿了内裤
        if len(wardrobe.of(character_id).cloth_wear[9]):
            TagetPanId = wardrobe.of(character_id).cloth_wear[9][-1]
            cloth_use_type = game_config.config_clothing_tem[TagetPanId].tag
            # 加到玩家的内裤收藏里
            from Script.Modules.domains import player_collection

            player_collection.append_list_map(
                "npc_panties_tem", character_id, TagetPanId
            )
            # 加到玩家的行动记录里
            TPanName = game_config.config_clothing_tem[TagetPanId].name
            activity.update_behavior(0, pan_name=TPanName)
            # 脱掉内裤
            wardrobe.set_part(character_id, "cloth_wear", 9, [])
            wardrobe.set_part(character_id, "cloth_see", 9, True)
            # 如果该服装为泳装，则将胸衣也一起脱掉
            if cloth_use_type == 3:
                wardrobe.set_part(character_id, "cloth_wear", 6, [])
                wardrobe.set_part(character_id, "cloth_see", 6, True)
            # 如果该角色在无意识中，则标注无意识flag
            if handle_premise.handle_unconscious_flag_ge_1(character_id):
                wardrobe.set(
                    character_id, "stolen_panties_in_unconscious", True
                )
            # 绘制信息
            now_draw = draw.NormalDraw()
            now_draw.width = window_width
            now_draw.text = _(
                "\n获得了{0}的{1}，可在藏品馆里纳入收藏\n"
            ).format(character_data.name, TPanName)
            now_draw.draw()


def pl_get_chara_socks(character_id: int) -> None:
    """
    玩家获得该角色的袜子
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    无
    """
    if character_id > 0:
        character_data = identity.of(character_id)
        # 如果角色穿了袜子
        if len(wardrobe.of(character_id).cloth_wear[10]):
            TagetSocId = wardrobe.of(character_id).cloth_wear[10][-1]
            # 加到玩家的袜子收藏里
            from Script.Modules.domains import player_collection

            player_collection.append_list_map(
                "npc_socks_tem", character_id, TagetSocId
            )
            # 加到玩家的行动记录里
            TSocName = game_config.config_clothing_tem[TagetSocId].name
            activity.update_behavior(0, socks_name=TSocName)
            # 脱掉袜子
            wardrobe.set_part(character_id, "cloth_wear", 10, [])
            wardrobe.set_part(character_id, "cloth_see", 10, True)
            # 如果该角色在无意识中，则标注无意识flag
            if handle_premise.handle_unconscious_flag_ge_1(character_id):
                wardrobe.set(character_id, "stolen_socks_in_unconscious", True)
            # 绘制信息
            now_draw = draw.NormalDraw()
            now_draw.width = window_width
            now_draw.text = _(
                "\n获得了{0}的{1}，可在藏品馆里纳入收藏\n"
            ).format(character_data.name, TSocName)
            now_draw.draw()


def get_all_cloth_off(character_id: int) -> None:
    """
    脱成全裸
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    无
    """
    if character_id:
        wardrobe.set(
            character_id, "cloth_wear", attr_calculation.get_cloth_wear_zero()
        )
        # 脱衣时去除服装部位上的避孕套装饰
        from Script.System.Item_System import condom_handle

        condom_handle.remove_cloth_decoration(character_id)
        chara_special_wear_cloth(character_id)


def get_shower_cloth(character_id: int) -> None:
    """
    清零其他衣服并换上浴帽和浴巾
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    无
    """
    if character_id:
        get_cloth_wear_zero_except_need(character_id)
        wardrobe.append(character_id, "cloth_wear", 0, 51)
        wardrobe.append(character_id, "cloth_wear", 5, 551)
        wardrobe.append(character_id, "cloth_wear", 8, 851)
        chara_special_wear_cloth(character_id)


def get_sleep_cloth(character_id: int) -> None:
    """
    清零其他衣服并换上睡衣和内裤
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    无
    """
    if character_id:
        # 已经穿着睡衣时直接跳过，避免被吵醒后再次入睡（以及爆睡、安眠药、烂醉等所有重睡路径）
        # 重新随机内裤，把玩家偷走的贴身衣物刷回来；也顺带免掉睡觉时509与634各换一次衣服的浪费
        if (
            552 in wardrobe.of(character_id).cloth_wear[5]
            or 553 in wardrobe.of(character_id).cloth_wear[5]
        ) and (
            852 in wardrobe.of(character_id).cloth_wear[8]
            or 853 in wardrobe.of(character_id).cloth_wear[8]
        ):
            return
        get_cloth_wear_zero_except_need(character_id)
        choic_flag = random.randint(0, 1)
        if choic_flag:
            wardrobe.append(character_id, "cloth_wear", 5, 552)
            wardrobe.append(character_id, "cloth_wear", 8, 852)
        else:
            wardrobe.append(character_id, "cloth_wear", 5, 553)
            wardrobe.append(character_id, "cloth_wear", 8, 853)
        get_underwear(character_id, part_flag=2)
        chara_special_wear_cloth(character_id)


def get_swim_cloth(character_id: int) -> None:
    """
    清零其他衣服并换上泳衣的胸衣和内裤
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    无
    """
    if character_id:
        get_cloth_wear_zero_except_need(character_id)
        choic_type = random.randint(1, 14)
        wardrobe.append(character_id, "cloth_wear", 6, choic_type + 680)
        wardrobe.append(character_id, "cloth_wear", 9, choic_type + 980)
        chara_special_wear_cloth(character_id)


def get_prison_cloth(character_id: int) -> None:
    """
    清零其他衣服并换上囚服的上衣和下衣
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    无
    """
    if character_id:
        get_cloth_wear_zero_except_need(character_id)
        wardrobe.append(character_id, "cloth_wear", 5, 561)
        wardrobe.append(character_id, "cloth_wear", 8, 861)
        chara_special_wear_cloth(character_id)


def get_patient_cloth(character_id: int) -> None:
    """
    清零其他衣服并换上病号服的上衣和下衣
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    无
    """
    if character_id:
        get_cloth_wear_zero_except_need(character_id)
        wardrobe.append(character_id, "cloth_wear", 5, 562)
        wardrobe.append(character_id, "cloth_wear", 8, 862)
        chara_special_wear_cloth(character_id)


def get_common_cloth(character_id: int) -> None:
    """
    清零其他衣服并换上通用的衣服和随机内衣
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    无
    """
    if character_id:
        get_cloth_wear_zero_except_need(character_id)
        wardrobe.append(character_id, "cloth_wear", 5, 581)
        wardrobe.append(character_id, "cloth_wear", 5, 582)
        down_cloth_random = random.randint(0, 1)
        wardrobe.append(character_id, "cloth_wear", 8, 881 + down_cloth_random)
        shoes_random = random.randint(0, 3)
        wardrobe.append(character_id, "cloth_wear", 11, 1181 + shoes_random)
        get_underwear(character_id, part_flag=2)
        chara_special_wear_cloth(character_id)


def chara_special_wear_cloth(character_id: int) -> list[int]:
    """
    角色穿上必须穿的衣物
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    无
    """
    talent = abilities.talent(character_id)
    return_list = []
    if character_id:
        # 阿米娅必须戴抑制戒指
        if identity.of(character_id).adv == 1:
            if 701 not in wardrobe.of(character_id).cloth_wear[7]:
                wardrobe.append(character_id, "cloth_wear", 7, 701)
            return_list.append(701)
        # 源石病感染者必须戴监测环
        if talent[150]:
            if 1301 not in wardrobe.of(character_id).cloth_wear[13]:
                wardrobe.append(character_id, "cloth_wear", 13, 1301)
            return_list.append(1301)
        # 囚犯必须戴镣铐
        if handle_premise.handle_imprisonment_1(character_id):
            if 1302 not in wardrobe.of(character_id).cloth_wear[13]:
                wardrobe.append(character_id, "cloth_wear", 13, 1302)
            return_list.append(1302)
        # 有戒指素质的必须戴戒指
        if talent[205]:
            if 751 not in wardrobe.of(character_id).cloth_wear[7]:
                wardrobe.append(character_id, "cloth_wear", 7, 751)
            return_list.append(751)
        # 项圈同理
        elif talent[215]:
            if 352 not in wardrobe.of(character_id).cloth_wear[3]:
                wardrobe.append(character_id, "cloth_wear", 3, 352)
            return_list.append(352)
    return return_list


def get_cloth_wear_zero_except_need(character_id: int) -> None:
    """
    遍历当前穿着服装类型，将首饰和必要物品以外的设为空
    """
    for clothing_type in game_config.config_clothing_type:
        if len(wardrobe.of(character_id).cloth_wear[clothing_type]):
            remove_tem_list = []
            for cloth_id in wardrobe.of(character_id).cloth_wear[clothing_type]:
                # 只要不是首饰和必须穿着的衣服，就把该服装加入删掉的list里
                if game_config.config_clothing_tem[
                    cloth_id
                ].tag != 6 and cloth_id not in chara_special_wear_cloth(
                    character_id
                ):
                    remove_tem_list.append(cloth_id)
            # 获得两个list的差，并赋值给当前服装
            result = [
                item
                for item in wardrobe.of(character_id).cloth_wear[clothing_type]
                if item not in remove_tem_list
            ]
            wardrobe.set_part(character_id, "cloth_wear", clothing_type, result)
    chara_special_wear_cloth(character_id)
    # 衣物离开身体时去除服装部位上的避孕套装饰
    from Script.System.Item_System import condom_handle

    condom_handle.remove_cloth_decoration(character_id)


def clean_locker_semen(character_id: int) -> None:
    """
    清理衣柜里的衣服精液
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    无
    """
    with dirty.editing(character_id) as d:
        d.cloth_locker_semen = {
            ct: [game_config.config_clothing_type[ct].name, 0, 0, 0]
            for ct in game_config.config_clothing_type
        }


def locker_cloth_semen_to_wear_cloth_semen(character_id: int) -> None:
    """
    将衣柜里的衣服精液转移到穿着的衣服上
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    无
    """
    semen_flag = False
    with dirty.editing(character_id) as d:
        for clothing_type in game_config.config_clothing_type:
            now_add = d.cloth_locker_semen.get(clothing_type, [0, 0])[1]
            if now_add > 0:
                d.cloth_semen[clothing_type][1] += now_add
                # 更新当前精液等级
                d.cloth_semen[clothing_type][2] = (
                    attr_calculation.get_semen_now_level(
                        d.cloth_semen[clothing_type][1],
                        clothing_type,
                        1,
                    )
                )
                semen_flag = True
    if semen_flag:
        clean_locker_semen(character_id)


def get_exposed_body_parts(
    character_id: int, ignore_panties: bool = False
) -> list[int]:
    """
    获得角色暴露在外的身体部位
    参数:
        character_id (int): 角色id
        ignore_panties (bool): 是否忽略内裤的覆盖效果，True表示忽略内裤
    返回:
        List[int]: 可暴露的身体部位序号列表
    """
    # 初始化返回列表
    talent = abilities.talent(character_id)
    return_list = []

    # 身体部位所对应的服装部位，-1表示无对应部位，列表表示多个对应部位
    body_cloth_list: list[int | list[int]] = [
        0,
        4,
        4,
        [5, 6],
        5,
        7,
        9,
        -1,
        9,
        9,
        -1,
        11,
        -1,
        -1,
        -1,
        -1,
        [8, 9],
        8,
        5,
    ]

    # 遍历所有身体部位
    for body_part_cid in game_config.config_body_part:
        # 如果角色没有该身体部位则跳过
        if body_part_cid == 12 and not talent[113]:
            continue
        elif body_part_cid == 13 and not talent[112]:
            continue
        elif body_part_cid == 14 and not talent[111]:
            continue

        now_body_cloth_cid = body_cloth_list[body_part_cid]
        # 判断对应项是否为多个服装部位
        if isinstance(now_body_cloth_cid, list):
            # 遍历所有对应的服装部位
            for cloth_type in now_body_cloth_cid:
                # 如果该服装为内裤且忽略内裤标记为True，则跳过检测这一项
                if cloth_type == 9 and ignore_panties:
                    continue
                # 如果身体部位对应的服装非空，则跳出循环
                if len(wardrobe.of(character_id).cloth_wear[cloth_type]):
                    break
            else:
                # 如果所有对应部位均无服装，则将该身体部位加入返回列表
                return_list.append(body_part_cid)
        else:
            # 如果对应部位为-1，表示无需服装，直接加入返回列表
            if now_body_cloth_cid == -1:
                return_list.append(body_part_cid)
            # 如果对应服装为内裤且忽略内裤标记为True，则视为未穿着
            elif now_body_cloth_cid == 9 and ignore_panties:
                return_list.append(body_part_cid)
            # 如果对应服装为空，则加入返回列表
            elif (
                len(wardrobe.of(character_id).cloth_wear[now_body_cloth_cid])
                == 0
            ):
                return_list.append(body_part_cid)

    # 返回可暴露的身体部位列表
    return return_list
