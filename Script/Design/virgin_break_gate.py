"""
破处行为的处女闸
处女素质指素质 0~4，依次为阴道处女、肛门处女、尿道处女、子宫处女与无接吻经验。
行为的标签含「破处」，且含角色仍有的某个处女素质对应的部位标签时，判定为会夺走该处女。
带「破处」与 W 标签的行为结算时都会清掉素质0。
所以素质0 对应 V 与 W。
NPC 主动H、群交的行为列表与调教助手可用的行为都跳过判定为真的行为
"""

from typing import Collection, Dict

VIRGIN_TALENT_TAGS: Dict[int, tuple[str, ...]] = {
    0: ("V", "W"),
    1: ("A",),
    2: ("U",),
    3: ("W",),
    4: ("N",),
}
""" 处女素质id: 对应的部位标签，破处行为带其中任一个就算作会夺走该处女 """


def takes_kept_virginity(
    tag_list: Collection[str], talent: Dict[int, int]
) -> bool:
  """
  按标签判断行为是否算作会夺走角色仍有的处女素质
  Keyword arguments:
  tag_list -- 行为的标签列表
  talent -- 角色的素质数据，素质id: 素质值
  Return arguments:
  bool -- 标签含「破处」，且含角色仍有的某个处女素质对应的部位标签时为 True
  """
  if "破处" not in tag_list:
    return False
  return any(
      talent[talent_id] and any(tag in tag_list for tag in tags)
      for talent_id, tags in VIRGIN_TALENT_TAGS.items()
  )
