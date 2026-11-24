"""提取口上文本里的图片标签，经 ui_hooks 发出图片名并从文本中去掉标签"""

import re

from Script.Modules.gameplay_resolution import ui_hooks


def draw_image_in_talk(talk_text: str) -> str:
    """
    绘制口上中的图片
    """
    # 用正则来查找是否有符合{img:图片名}的格式的图片标签，key为图片名，将所有找到的存储为列表
    img_tags = re.findall(r"\{img:([^\}]+)\}", talk_text)
    for img_name in img_tags:
        ui_hooks.emit_image(img_name)
        # 将标签替换为空字符串
        talk_text = talk_text.replace(f"{{img:{img_name}}}", "")
    # 返回处理后的文本
    return talk_text
