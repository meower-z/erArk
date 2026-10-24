# -*- coding: UTF-8 -*-
"""按当前语言构建翻译函数 _"""

import gettext
import os
from types import FunctionType
from typing import Dict, List, Optional, cast
from Script.Config import normal_config

po_data = os.path.join("data", "po")
""" po文件路径 """
# 如果language在normal_config.config_normal中，就使用normal_config.config_normal.language，否则使用zh_CN
now_language = (
    normal_config.config_normal.language
    if hasattr(normal_config.config_normal, "language")
    else "zh_CN"
)
# print(now_language)

# 创建一个字典来存储原始字符串和它们的翻译
translation_dict: Dict[str, str] = {}

# 可能每种语言都有多个.mo文件，这里是.mo文件的名称列表
mo_files_per_language = {
    "en_US": ["erArk", "erArk_py", "erArk_csv", "erArk_talk"],
    "ko_KR": ["erArk", "erArk_py", "erArk_csv", "erArk_talk"],
}


# 接受一个语言和对应的.mo文件列表，然后为这些文件创建一个GNUTranslations实例链
def create_translation_chain(
    language: str, mo_files: List[str]
) -> Optional[gettext.GNUTranslations]:
  """
  按顺序加载指定语言的 .mo 文件，第一个加载到的作为主翻译，其余依次加为它的回退翻译，不存在的 .mo 文件跳过
  Keyword arguments:
  language -- 语言代码
  mo_files -- .mo 文件名列表（不含扩展名）
  Return arguments:
  gettext.NullTranslations -- 链接好回退的翻译对象，一个 .mo 文件都没加载到时为 None
  """
  main_translation = None
  for mo_file in mo_files:
    try:
      translation = gettext.translation(mo_file, po_data, languages=[language])
      # print(f"Loaded {mo_file}.mo for {language}")
      if main_translation is None:
        main_translation = translation
      else:
        main_translation.add_fallback(translation)
    except FileNotFoundError:
      pass  # 如果.mo文件不存在，忽略该异常
  return main_translation


# 根据当前语言，创建翻译链
if now_language in mo_files_per_language:
  translation_chain = create_translation_chain(
      now_language, mo_files_per_language[now_language]
  )
  # 仓库为 en_US 与 ko_KR 都带有编译好的 .mo 文件，翻译链至少加载到一个，不会为 None
  assert translation_chain is not None
  translation = translation_chain

  def _translation_gettext(
      message: str,
      skip_translation: bool = False,
      revert_translation: bool = False,
  ) -> str:
    """
    翻译文本，可跳过翻译或由译文还原原文
    Keyword arguments:
    message -- 要翻译的文本，还原时为译文
    skip_translation -- 为真时直接返回原文 (default False)
    revert_translation -- 为真时在已翻译过的文本中查找译文对应的原文，找不到则返回传入的文本 (default False)
    Return arguments:
    str -- 译文、原文或传入的文本
    """
    # 如果需要跳过翻译，直接返回原文
    if skip_translation:
      return message
    # 如果需要恢复原始字符串，查找字典
    elif revert_translation:
      for original, translated in translation_dict.items():
        if translated == message:
          return original
      return message  # 如果找不到，返回翻译后的字符串
    else:
      translated = translation.gettext(message)
      # 存储原始字符串和它的翻译
      translation_dict[message] = translated
      return translated

  # _catalog 是 GNUTranslations 解析 .mo 后存放译文的字典，类型存根没有声明这个私有属性
  translation_values = set(getattr(translation, "_catalog").values())
else:

  def _translation_gettext(
      message: str,
      skip_translation: bool = False,
      revert_translation: bool = False,
  ) -> str:
    """
    没有对应语言的翻译时的翻译函数，直接返回传入的文本
    Keyword arguments:
    message -- 要翻译的文本
    skip_translation -- 不使用 (default False)
    revert_translation -- 不使用 (default False)
    Return arguments:
    str -- 传入的文本
    """
    return message  # 如果没有找到对应语言的翻译，直接返回原文

  translation_values = set()

# 两个分支定义的 _translation_gettext 都是 def 函数，运行时即 FunctionType；mypy 不把 def 函数当作 FunctionType
_: FunctionType = cast(FunctionType, _translation_gettext)
""" 翻译api """
