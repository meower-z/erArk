# -*- coding: UTF-8 -*-
"""
编辑器外勤委托编辑控件的「保存修改」按钮
========================================
在 offscreen 平台上建出 tools/ArkEditor 的 CommissionEditWidget，点击保存按钮：
- 没有选中委托时（ID 框为空或已填数字），点击不抛异常，也不发出 commission_saved；
- 选中委托并改动表单后，点击发出一次 commission_saved，委托对象的各字段等于表单内容。
槽函数里的异常由 PySide6 交给 sys.excepthook，不会传到 click() 的调用处，所以测试接管 sys.excepthook 收集。
"""

import importlib
import os
import sys
import unittest
from typing import TYPE_CHECKING, Any
from unittest import mock

from tests.fast.base import FastTestCase
from tests.world import ROOT

if TYPE_CHECKING:
  from types import ModuleType, TracebackType

  from PySide6.QtCore import QCoreApplication

# 只导入模块：Qt 的控件类带 testAttribute 方法，放进本模块的命名空间会被 tests/registration.py 当成有测试的类
try:
  from PySide6 import QtWidgets

  QT_ERROR = ""
except ImportError as error:
  QT_ERROR = str(error)

EDITOR_DIR = os.path.join(ROOT, "tools", "ArkEditor")
""" 编辑器目录，编辑器模块之间用顶层名字互相导入 """
EDITOR_MODULES = ("ui.commission_edit", "ui", "cache_control", "game_type")
""" 载入控件时新加进 sys.modules 的编辑器模块名，测试类结束时移除 """


@unittest.skipUnless(not QT_ERROR, f"PySide6 的 QtWidgets 无法导入：{QT_ERROR}")
class CommissionEditSaveTest(FastTestCase):
  """外勤委托编辑控件的保存按钮：未选中委托时什么也不做，选中时把表单写回委托"""

  app: "QCoreApplication"
  edit_module: "ModuleType"
  game_type: "ModuleType"

  @classmethod
  def setUpClass(cls) -> None:
    """
    建好 offscreen 的 QApplication，并从编辑器目录载入委托编辑控件模块
    Keyword arguments:
    无
    Return arguments:
    无
    """
    super().setUpClass()
    with mock.patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}):
      cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    for name in EDITOR_MODULES:
      cls.addClassCleanup(sys.modules.pop, name, None)
    with mock.patch.object(sys, "path", [EDITOR_DIR, *sys.path]):
      cls.edit_module = importlib.import_module("ui.commission_edit")
      cls.game_type = importlib.import_module("game_type")

  def make_widget(self) -> "tuple[Any, list]":
    """
    建一个委托编辑控件，记录它发出的 commission_saved
    Keyword arguments:
    无
    Return arguments:
    CommissionEditWidget -- 新建的控件
    list -- 每次 commission_saved 发出的委托对象
    """
    widget = self.edit_module.CommissionEditWidget()
    self.addCleanup(widget.deleteLater)
    saved: list = []
    widget.commission_saved.connect(saved.append)
    return widget, saved

  def click_save(self, widget: Any) -> "list[str]":
    """
    点击控件的保存按钮
    Keyword arguments:
    widget -- 委托编辑控件
    Return arguments:
    list[str] -- 点击时槽函数抛出的异常类型名
    """
    errors: "list[str]" = []

    def collect(
        exc_type: "type[BaseException]",
        exc: BaseException,
        tb: "TracebackType | None",
    ) -> None:
      """
      记下槽函数抛出的异常类型名
      Keyword arguments:
      exc_type -- 异常类型
      exc -- 异常对象
      tb -- 回溯
      Return arguments:
      无
      """
      errors.append(exc_type.__name__)

    with mock.patch.object(sys, "excepthook", collect):
      widget.save_btn.click()
    return errors

  def test_save_without_selection(self) -> None:
    """没有选中委托时点击保存：ID 框为空或填了数字，都不抛异常、不发出 commission_saved"""
    for cid_text in ("", "1"):
      with self.subTest(cid_text=cid_text):
        widget, saved = self.make_widget()
        widget.cid_edit.setText(cid_text)
        self.assertEqual(self.click_save(widget), [])
        self.assertEqual(saved, [])

  def test_save_selected_commission(self) -> None:
    """选中委托、改动表单后点击保存：发出一次 commission_saved，委托的各字段等于表单内容"""
    widget, saved = self.make_widget()
    commission = self.game_type.Commission(
        1, "原名", -1, 1, "资源", 1, 1, "a_46_2", "r_11_10", -1, 0, "原描述"
    )
    widget.set_commission(commission)
    widget.cid_edit.setText("7")
    widget.name_edit.setText("新名")
    widget.level_edit.setValue(3)
    widget.type_edit.setText("源石")
    widget.people_edit.setValue(2)
    widget.time_edit.setValue(4)
    widget.demand_edit.setText("r_22_2")
    widget.reward_edit.setText("声望_0_5")
    widget.related_id_edit.setValue(5)
    widget.special_edit.setValue(1)
    widget.description_edit.setPlainText("新描述")
    self.assertEqual(self.click_save(widget), [])
    self.assertEqual(saved, [commission])
    self.assertEqual(
        vars(commission),
        {
            "cid": 7,
            "name": "新名",
            "country_id": -1,
            "level": 3,
            "type": "源石",
            "people": 2,
            "time": 4,
            "demand": "r_22_2",
            "reward": "声望_0_5",
            "related_id": 5,
            "special": 1,
            "description": "新描述",
        },
    )
