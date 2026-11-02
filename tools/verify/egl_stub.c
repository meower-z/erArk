/*
 * libEGL.so.1 的替身。PySide6 的 libQt6Gui.so.6 把它列为依赖，没装这个库的机器上 PySide6.QtGui 载入不了。
 * 编辑器用的 Qt vnc 平台在软件里绘制，按理不调用 EGL。每个替身函数被调用时把自己的名字写到 stderr 并 abort，意外的调用会立刻暴露，不会悄悄出错。
 * egl_symbols.h 由 arkeditor.py 每次启动时从编辑器载入的 PySide6 库的未定义 EGL 符号生成，每行一个 STUB(名字)。
 */
#include <stdio.h>
#include <stdlib.h>

#define STUB(name)                                         \
  void name(void) {                                        \
    fputs("egl_stub: " #name " called, aborting\n", stderr); \
    abort();                                               \
  }

#include "egl_symbols.h"
