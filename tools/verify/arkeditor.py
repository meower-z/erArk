#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
经 limited_run 启动 erArk 的 ArkEditor（tools/ArkEditor/main.py），并用真实的鼠标与键盘事件操作它。

编辑器在 Qt 自带的 vnc 平台上运行，启动参数是 -platform vnc:size=<宽x高>:port=<端口>。
这个平台在内存里绘制窗口，并在本机端口上以 RFB（VNC 协议）提供画面。
这个平台不需要 X 显示，也不需要 Qt xcb 平台要的那些库。
本脚本的 RFB 客户端连上这个端口发指针与按键事件，并在每个动作后存一帧画面。

PySide6 的 libQt6Gui.so.6 依赖 libEGL.so.1，没装这个库的机器上 PySide6.QtGui 载入不了。
每次运行时，本脚本用本机 gcc 把 egl_stub.c 编成替身库。
替身库放在本脚本自己建的临时目录里，编辑器或 run 的命令结束、本脚本返回前删掉。
编辑器跑在一个 scope（systemd 管理的一组进程）里。scope 里的 LD_LIBRARY_PATH 指向替身库的目录，
动态链接器先在那里找 libEGL.so.1，所以编辑器总是载入替身，装了 libEGL.so.1 的机器上也一样。
本脚本自己的进程不设这个变量。
vnc 平台在软件里绘制，不调用 EGL。
替身函数一旦被调用，就报出自己的名字并 abort。

Qt 的 vnc 服务在所有网络接口上监听，也不要求认证。
start 因此把 loopback_bind.c 编成 bind() 替换，只经 LD_PRELOAD 载入编辑器进程。
这个替换让编辑器的监听套接字绑定到本机回环地址，而不是通配地址。
就绪检查读 /proc/net/tcp 与 tcp6。
端口在通配地址上监听时，就绪检查报错退出，limited_run.run 随之停掉编辑器。

run 子命令用同一个 EGL 替身，在 limited_run 下运行任意命令，例如导入 PySide6 的编辑器测试。
内存上限、运行时限和游戏槽位都由 limited_run.run() 负责。
start 按 editor 模式运行：停掉是正常结束，退出码为 0。
limited_run.py status 把它列成 ArkEditor 运行，并带上它的 --out 目录；tk.py 只操作 tk 模式的运行，不会选中它。
run 按 headless 模式运行；比起 limited_run.py 直接运行命令，它只多编一个替身库，并在 scope 里设 LD_LIBRARY_PATH。

用法（在 erArk checkout 的根目录，用 .venv 的 python 运行本脚本）：
  arkeditor.py start --out <证据目录> [--mem 2G] [--timeout 600] [--ready-timeout 120] [--size 2100x1100]
  arkeditor.py click|rclick|dclick|move --out <证据目录> X Y [--label L] [--wait 1]
  arkeditor.py drag --out <证据目录> X1 Y1 X2 Y2 [--label L] [--wait 1]
  arkeditor.py key --out <证据目录> KEY [KEY ...] [--label L] [--wait 1]
  arkeditor.py type --out <证据目录> TEXT [--label L] [--wait 1]
  arkeditor.py shot --out <证据目录> [--label L] [--wait 1]
  arkeditor.py stop --out <证据目录>
  arkeditor.py run [--mem 2G] [--timeout 600] -- <命令...>
KEY 是 KEYS 里的名字、+ 以外的单个可打印 ASCII 字符，或 ctrl+s 这样用 + 连起来的组合；加号写 plus。
KEYS 没有菜单键（keysym 0xFF67）：Qt vnc 平台的键表里没有它，按了也不会到达编辑器；右键菜单只能用 rclick 打开。
type 只收可打印 ASCII，每个字符按一次键。
"""

import argparse
import importlib.util
import os
import re
import shlex
import socket
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import limited_run

STUB_SOURCE = Path(__file__).resolve().parent / "egl_stub.c"
EGL = "libEGL.so.1"
LOOPBACK_SOURCE = Path(__file__).resolve().parent / "loopback_bind.c"
LOOPBACK = "loopback_bind.so"
# 本机的 TCP 套接字表；第 4 列 0A 表示在监听，通配地址写成全 0
PROC_TCP = (Path("/proc/net/tcp"), Path("/proc/net/tcp6"))
# 编辑器导入的 PySide6 模块（tools/ArkEditor 只导入这三个）与它用的平台插件；替身要覆盖它们连同依赖里必须找到的 EGL 函数，弱引用除外
ROOT_MODULES = ("QtCore", "QtGui", "QtWidgets")
PLATFORM_PLUGIN = "Qt/plugins/platforms/libqvnc.so"
DEFAULT_MEM = "2G"
DEFAULT_SIZE = "2100x1100"
# 编辑器启动前先在同一环境里导入一次 PySide6.QtWidgets，把结果和 libEGL.so.1 的实际来源写进 editor.log
IMPORT_CHECK = (
    "import PySide6.QtWidgets\n"
    "maps = open('/proc/self/maps').read().split()\n"
    "print('import PySide6.QtWidgets ok; libEGL.so.1 from', next(w for w in maps if w.endswith('/libEGL.so.1')), flush=True)\n"
)

# RFB 按键的 X keysym；单个 ASCII 字符直接用它的码位
KEYS = {
    "Return": 0xFF0D,
    "Tab": 0xFF09,
    "Escape": 0xFF1B,
    "BackSpace": 0xFF08,
    "Delete": 0xFFFF,
    "Home": 0xFF50,
    "End": 0xFF57,
    "Left": 0xFF51,
    "Up": 0xFF52,
    "Right": 0xFF53,
    "Down": 0xFF54,
    "Page_Up": 0xFF55,
    "Page_Down": 0xFF56,
    "F10": 0xFFC7,
    "space": 0x20,
    "plus": 0x2B,
    "ctrl": 0xFFE3,
    "shift": 0xFFE1,
    "alt": 0xFFE9,
}
# 指针动作：RFB 按键位（1 左键，4 右键）与点击次数；move 只移动不点击
BUTTONS = {"click": (1, 1), "dclick": (1, 2), "rclick": (4, 1), "move": (0, 0)}
# drag 按住左键后分几步移到终点；每步之间的秒数。Qt 要按住时收到移过拖动起始距离的指针事件，才开始拖动
DRAG_STEPS = 20
DRAG_STEP_WAIT = 0.03


class StubError(Exception):
  """EGL 替身库或 bind() 替换编不出来：找不到 PySide6 或它的库，readelf 或 gcc 缺失或失败，编辑器载入的库不再依赖 libEGL.so.1，或它们引用的 EGL 符号替身代替不了"""


def readelf(*args: str) -> str:
  """
  运行本机的 readelf
  参数：
      args (str): readelf 参数
  返回：
      str: 标准输出
  """
  try:
    result = subprocess.run(
        ["readelf", *args], capture_output=True, text=True, check=False
    )
  except FileNotFoundError as error:
    raise StubError(
        "本机没有 readelf，列不出 PySide6 库引用的 EGL 符号"
    ) from error
  if result.returncode != 0:
    raise StubError(f"readelf {' '.join(args)} 失败：{result.stderr.strip()}")
  return result.stdout


def needed(lib: Path) -> list[str]:
  """
  列出一个 ELF 文件的 DT_NEEDED 依赖
  参数：
      lib (Path): 库文件
  返回：
      list[str]: 依赖的库名
  """
  return re.findall(
      r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]",
      readelf("-d", "-W", str(lib)),
  )


def loaded_libraries(pyside: Path) -> list[Path]:
  """
  找出编辑器会载入的 PySide6 库：ROOT_MODULES 的扩展模块与 vnc 平台插件，加上它们在 PySide6 目录内的依赖闭包
  参数：
      pyside (Path): PySide6 包目录
  返回：
      list[Path]: 库文件，按发现顺序
  """
  roots = []
  for module in ROOT_MODULES:
    found = sorted(pyside.glob(f"{module}.*.so"))
    if not found:
      raise StubError(
          f"{pyside} 下没有 {module} 的扩展模块；PySide6 的布局变了，先查明再改 arkeditor.py"
      )
    roots.append(found[0])
  plugin = pyside / PLATFORM_PLUGIN
  if not plugin.is_file():
    raise StubError(
        f"没有 {plugin}；PySide6 的布局变了，先查明再改 arkeditor.py"
    )
  roots.append(plugin)
  search = [pyside / "Qt" / "lib", pyside]
  seen: list[Path] = []
  queue = roots
  while queue:
    lib = queue.pop(0)
    if lib in seen:
      continue
    seen.append(lib)
    for name in needed(lib):
      queue += [
          folder / name for folder in search if (folder / name).is_file()
      ][:1]
  return seen


def egl_symbols(libs: list[Path]) -> list[str]:
  """
  收集库里引用的 EGL 符号，只收依赖 libEGL.so.1 的库里未定义的、名字以 egl 开头的全局函数；弱符号允许留空，不收
  参数：
      libs (list[Path]): 库文件
  返回：
      list[str]: 排好序的符号名
  """
  users = [lib for lib in libs if EGL in needed(lib)]
  if not users:
    raise StubError(
        f"编辑器载入的 PySide6 库都不再依赖 {EGL}；替身可能不再需要，先查明再改 arkeditor.py"
    )
  symbols = set()
  for lib in users:
    for line in readelf("--dyn-syms", "-W", str(lib)).splitlines():
      fields = line.split()
      if (
          len(fields) < 8
          or fields[6] != "UND"
          or not fields[7].startswith("egl")
      ):
        continue
      kind, bind, name = fields[3], fields[4], fields[7]
      if bind == "WEAK":
        continue
      if kind != "FUNC" or bind != "GLOBAL" or "@" in name:
        raise StubError(
            f"{lib} 引用的 {name}（{kind} {bind}）不是无版本的全局函数，函数替身代替不了；PySide6 变了，先查明再改 egl_stub.c"
        )
      symbols.add(name)
  return sorted(symbols)


def gcc(source: Path, out: Path, *flags: str) -> Path:
  """
  用本机 gcc 把一个 C 文件编成共享库
  参数：
      source (Path): C 源文件
      out (Path): 输出的库文件
      flags (str): 额外的 gcc 参数
  返回：
      Path: 库文件
  """
  command = ["gcc", "-shared", "-fPIC", *flags, "-o", str(out), str(source)]
  try:
    result = subprocess.run(
        command, capture_output=True, text=True, check=False
    )
  except FileNotFoundError as error:
    raise StubError(f"本机没有 gcc，编不出 {out.name}") from error
  if result.returncode != 0:
    raise StubError(f"gcc 编 {out.name} 失败：{result.stderr.strip()}")
  return out


def build_stub(dest: Path, symbols: list[str]) -> Path:
  """
  用本机 gcc 把 egl_stub.c 编成 dest/libEGL.so.1，每个符号一个替身函数
  参数：
      dest (Path): 输出目录
      symbols (list[str]): 符号名
  返回：
      Path: 替身库文件
  """
  (dest / "egl_symbols.h").write_text(
      "".join(f"STUB({name})\n" for name in symbols)
  )
  return gcc(STUB_SOURCE, dest / EGL, f"-Wl,-soname,{EGL}", "-I", str(dest))


def build_loopback(dest: Path) -> Path:
  """
  用本机 gcc 把 loopback_bind.c 编成 dest/loopback_bind.so
  参数：
      dest (Path): 输出目录
  返回：
      Path: 库文件
  """
  return gcc(LOOPBACK_SOURCE, dest / LOOPBACK, "-ldl")


def pyside_dir() -> Path:
  """
  找到当前 python 的 PySide6 包目录，不导入它
  返回：
      Path: 包目录
  """
  spec = importlib.util.find_spec("PySide6")
  if spec is None or not spec.submodule_search_locations:
    raise StubError(
        f"{sys.executable} 找不到 PySide6；用 erArk 的 .venv 的 python 运行本脚本"
    )
  return Path(list(spec.submodule_search_locations)[0])


def free_port() -> int:
  """
  向系统要一个当前空闲的 TCP 端口
  返回：
      int: 端口号
  """
  with socket.socket() as sock:
    sock.bind(("", 0))
    port: int = sock.getsockname()[1]
    return port


def editor_command(
    root: Path, out_dir: Path, shim: Path, python: str, size: str, port: int
) -> list[str]:
  """
  拼出在 scope 里运行的脚本：先检查 PySide6.QtWidgets 能导入，再以 vnc 平台运行编辑器，只给编辑器载入 bind() 替换，输出都写进 editor.log
  参数：
      root (Path): erArk checkout 根目录
      out_dir (Path): 证据目录
      shim (Path): loopback_bind.so
      python (str): 运行编辑器用的 python
      size (str): 画面大小，形如 2100x1100
      port (int): vnc 端口
  返回：
      list[str]: argv
  """
  log = shlex.quote(str(out_dir / "editor.log"))
  py = shlex.quote(python)
  script = f"""
cd {shlex.quote(str(root / "tools" / "ArkEditor"))} || exit 9
{py} -c {shlex.quote(IMPORT_CHECK)} >>{log} 2>&1 || exit $?
LD_PRELOAD={shlex.quote(str(shim))} exec {py} -u main.py -platform {shlex.quote(f"vnc:size={size}:port={port}")} >>{log} 2>&1
"""
  return ["bash", "-c", script]


def listeners(port: int, tables: tuple[Path, ...] = PROC_TCP) -> list[str]:
  """
  列出在端口上监听的 TCP 套接字的本地地址
  参数：
      port (int): 端口
      tables (tuple[Path, ...]): 套接字表，默认 /proc/net/tcp 与 tcp6
  返回：
      list[str]: 十六进制地址，通配地址为全 0
  """
  found = []
  for table in tables:
    for line in table.read_text().splitlines()[1:]:
      fields = line.split()
      address, _, hex_port = fields[1].partition(":")
      if fields[3] == "0A" and int(hex_port, 16) == port:
        found.append(address)
  return found


def vnc_ready(port: int) -> dict[str, int] | None:
  """
  检查编辑器的 vnc 端口是否有监听、没有一个在通配地址上，并已应答 RFB 版本串；有监听在通配地址上时退出，limited_run.run 随之停掉编辑器
  参数：
      port (int): vnc 端口
  返回：
      dict[str, int] | None: 就绪时为要并入运行状态的字段，否则为 None
  """
  addresses = listeners(port)
  if any(set(address) == {"0"} for address in addresses):
    sys.exit(
        f"编辑器的 vnc 端口 {port} 在所有网络接口上监听，别的主机也能连上并操作它；{LOOPBACK} 没起作用，已停掉编辑器。"
    )
  if not addresses:
    return None
  try:
    with socket.create_connection(("127.0.0.1", port), timeout=1) as sock:
      return {"vnc_port": port} if sock.recv(12).startswith(b"RFB ") else None
  except OSError:
    return None


class Rfb:
  """连到 Qt vnc 平台的最小 RFB 客户端：无认证、raw 编码、32 位 BGRX 像素"""

  def __init__(self, port: int) -> None:
    """
    连接并完成握手，设好像素格式与编码
    参数：
        port (int): vnc 端口
    """
    self.sock = socket.create_connection(("127.0.0.1", port), timeout=10)
    version = self.recv(12)
    self.sock.sendall(version)
    if version.startswith(b"RFB 003.003"):
      security = struct.unpack(">I", self.recv(4))[0]
      if security != 1:
        raise ConnectionError(f"vnc 服务要求认证（类型 {security}）")
    else:
      types = self.recv(self.recv(1)[0])
      if 1 not in types:
        raise ConnectionError(f"vnc 服务不提供无认证方式：{list(types)}")
      self.sock.sendall(b"\x01")
      if version >= b"RFB 003.008" and struct.unpack(">I", self.recv(4))[0]:
        raise ConnectionError("vnc 服务拒绝了无认证连接")
    self.sock.sendall(b"\x01")
    self.width, self.height = struct.unpack(">HH", self.recv(4))
    self.recv(16)
    self.recv(struct.unpack(">I", self.recv(4))[0])
    # 32 位、小端、真彩色，红绿蓝各 8 位、移位 16/8/0：每个像素按字节是 B G R X
    self.sock.sendall(
        struct.pack(
            ">B3xBBBBHHHBBB3x", 0, 32, 24, 0, 1, 255, 255, 255, 16, 8, 0
        )
    )
    self.sock.sendall(struct.pack(">BxHi", 2, 1, 0))
    self.pixels = bytearray(self.width * self.height * 3)

  def recv(self, size: int) -> bytes:
    """
    读满 size 个字节
    参数：
        size (int): 字节数
    返回：
        bytes: 数据
    """
    buf = bytearray()
    while len(buf) < size:
      chunk = self.sock.recv(size - len(buf))
      if not chunk:
        raise ConnectionError("vnc 服务断开了连接")
      buf += chunk
    return bytes(buf)

  def pointer(self, mask: int, x: int, y: int) -> None:
    """
    发一个指针事件
    参数：
        mask (int): 按下的键位
        x (int): 横坐标
        y (int): 纵坐标
    """
    self.sock.sendall(struct.pack(">BBHH", 5, mask, x, y))

  def key(self, down: bool, sym: int) -> None:
    """
    发一个按键事件
    参数：
        down (bool): 按下为 True，松开为 False
        sym (int): X keysym
    """
    self.sock.sendall(struct.pack(">BBxxI", 4, 1 if down else 0, sym))

  def frame(self) -> bytes:
    """
    请求整屏并读到这次更新结束
    返回：
        bytes: 整屏 RGB 像素，逐行排列
    """
    self.sock.sendall(
        struct.pack(">BBHHHH", 3, 0, 0, 0, self.width, self.height)
    )
    while True:
      kind = self.recv(1)[0]
      if kind == 0:
        self.recv(1)
        for _ in range(struct.unpack(">H", self.recv(2))[0]):
          x, y, w, h, encoding = struct.unpack(">HHHHi", self.recv(12))
          if encoding != 0:
            raise ConnectionError(f"vnc 服务发来了没请求的编码 {encoding}")
          self.paste(x, y, w, h, self.recv(w * h * 4))
        return bytes(self.pixels)
      if kind == 1:
        self.recv(6 * struct.unpack(">xHH", self.recv(5))[1])
      elif kind == 3:
        self.recv(3)
        self.recv(struct.unpack(">I", self.recv(4))[0])
      elif kind != 2:
        raise ConnectionError(f"vnc 服务发来了不认识的消息 {kind}")

  def paste(self, x: int, y: int, w: int, h: int, bgrx: bytes) -> None:
    """
    把一个 raw 矩形贴进整屏缓冲
    参数：
        x (int): 左上角横坐标
        y (int): 左上角纵坐标
        w (int): 宽
        h (int): 高
        bgrx (bytes): 每像素 B G R X 四个字节
    """
    rgb = bytearray(w * h * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = bgrx[2::4], bgrx[1::4], bgrx[0::4]
    for row in range(h):
      start = ((y + row) * self.width + x) * 3
      self.pixels[start : start + w * 3] = rgb[row * w * 3 : (row + 1) * w * 3]


def png(width: int, height: int, rgb: bytes) -> bytes:
  """
  把 RGB 像素编成 PNG
  参数：
      width (int): 宽
      height (int): 高
      rgb (bytes): 逐行排列的 RGB 像素
  返回：
      bytes: PNG 文件内容
  """

  def chunk(kind: bytes, data: bytes) -> bytes:
    """拼一个 PNG 块：长度、类型、数据、CRC"""
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data))
    )

  stride = width * 3
  raw = b"".join(
      b"\x00" + rgb[row * stride : (row + 1) * stride] for row in range(height)
  )
  header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
  return (
      b"\x89PNG\r\n\x1a\n"
      + chunk(b"IHDR", header)
      + chunk(b"IDAT", zlib.compress(raw, 6))
      + chunk(b"IEND", b"")
  )


def keysyms(spec: str) -> list[int]:
  """
  把 ctrl+s 这样的按键写法拆成 keysym
  参数：
      spec (str): 按键写法
  返回：
      list[int]: keysym，按按下顺序
  """
  syms = []
  for part in spec.split("+"):
    if part == "Menu":
      raise ValueError(
          "Qt 的 vnc 平台丢掉菜单键（keysym 0xFF67），编辑器收不到；右键菜单用 rclick 打开"
      )
    if part in KEYS:
      syms.append(KEYS[part])
    elif len(part) == 1 and " " <= part <= "~":
      syms.append(ord(part))
    else:
      raise ValueError(
          f"不认识的按键 {part!r}（在 {spec!r} 里）；可用：{' '.join(KEYS)}，或单个 ASCII 字符"
      )
  return syms


def press(client: Rfb, syms: list[int]) -> None:
  """
  按下再松开一个键或组合键：依次按下，倒序松开
  参数：
      client (Rfb): RFB 连接
      syms (list[int]): keysym，按按下顺序
  """
  for sym in syms:
    client.key(True, sym)
    time.sleep(0.03)
  for sym in reversed(syms):
    client.key(False, sym)
    time.sleep(0.03)


def find_run(out_dir: Path) -> dict[str, object]:
  """
  按证据目录找出以它启动、仍在运行的那次运行
  参数：
      out_dir (Path): 证据目录
  返回：
      dict[str, object]: limited_run 的运行状态
  """
  runs = [
      run
      for run in limited_run.live_runs()
      if run.get("out") and Path(run["out"]) == out_dir
  ]
  if not runs:
    sys.exit(
        f"没有以 --out {out_dir} 启动、仍在运行的编辑器。先用 start 启动；limited_run.py status 列出正在运行的实例。"
    )
  return dict(runs[0])


def save_frame(
    out_dir: Path, client: Rfb, label: str, description: str
) -> Path:
  """
  取一帧存为证据目录下的下一帧，并在 actions.log 记一行
  参数：
      out_dir (Path): 证据目录
      client (Rfb): RFB 连接
      label (str): 写进文件名的标签
      description (str): 写进 actions.log 的动作描述
  返回：
      Path: 帧文件路径
  """
  frames = out_dir / "frames"
  frames.mkdir(exist_ok=True)
  # 斜杠与空白换成下划线，免得斜杠被当成目录；只取前 40 个字符；动作的完整描述写在 actions.log 里
  label = re.sub(r"[\s/]+", "_", label)[:40]
  path = frames / f"{len(list(frames.glob('*.png'))) + 1:03d}-{label}.png"
  path.write_bytes(png(client.width, client.height, client.frame()))
  with open(out_dir / "actions.log", "a", encoding="utf-8") as log:
    log.write(f"{time.strftime('%H:%M:%S')}\t{description}\t{path.name}\n")
  return path


def act(out_dir: Path, port: int, args: argparse.Namespace) -> Path:
  """
  连上编辑器的 vnc 服务，发一个动作的事件，等 --wait 秒后存帧
  参数：
      out_dir (Path): 证据目录
      port (int): vnc 端口
      args (argparse.Namespace): 命令行参数
  返回：
      Path: 帧文件路径
  """
  action = args.action
  if action == "type" and not all(" " <= ch <= "~" for ch in args.text):
    sys.exit("type 只收可打印 ASCII")
  if action == "key":
    for spec in args.keys:
      try:
        keysyms(spec)
      except ValueError as error:
        sys.exit(str(error))
  client = Rfb(port)
  with client.sock:
    if action in BUTTONS:
      description = f"{action} {args.x} {args.y}"
      client.pointer(0, args.x, args.y)
      time.sleep(0.1)
      mask, count = BUTTONS[action]
      for _ in range(count):
        client.pointer(mask, args.x, args.y)
        time.sleep(0.05)
        client.pointer(0, args.x, args.y)
        time.sleep(0.05)
    elif action == "drag":
      description = f"drag {args.x1} {args.y1} {args.x2} {args.y2}"
      client.pointer(0, args.x1, args.y1)
      time.sleep(0.1)
      client.pointer(1, args.x1, args.y1)
      time.sleep(0.1)
      for step in range(1, DRAG_STEPS + 1):
        client.pointer(
            1,
            args.x1 + (args.x2 - args.x1) * step // DRAG_STEPS,
            args.y1 + (args.y2 - args.y1) * step // DRAG_STEPS,
        )
        time.sleep(DRAG_STEP_WAIT)
      time.sleep(0.2)
      client.pointer(0, args.x2, args.y2)
    elif action == "key":
      description = f"key {' '.join(args.keys)}"
      for spec in args.keys:
        press(client, keysyms(spec))
        time.sleep(0.1)
    elif action == "type":
      description = f"type {args.text}"
      for ch in args.text:
        press(client, [ord(ch)])
    else:
      description = "shot"
    time.sleep(args.wait)
    return save_frame(
        out_dir,
        client,
        args.label or description.replace(" ", "-"),
        description,
    )


def with_stub(launch: Callable[[Path], int], loopback: bool) -> int:
  """
  在临时目录里编出 EGL 替身库（loopback 为 True 时还编 bind() 替换），把目录交给 launch，launch 返回后删掉临时目录
  参数：
      launch (Callable[[Path], int]): 经 limited_run.run 启动的函数，参数是放库的临时目录
      loopback (bool): 是否也编 loopback_bind.so
  返回：
      int: launch 的退出码；库编不出时为 2
  """
  with tempfile.TemporaryDirectory(prefix="arkeditor-") as scratch:
    folder = Path(scratch)
    try:
      symbols = egl_symbols(loaded_libraries(pyside_dir()))
      build_stub(folder, symbols)
      if loopback:
        build_loopback(folder)
    except StubError as error:
      print(error, file=sys.stderr)
      return 2
    limited_run.emit(
        {"event": "egl-stub", "symbols": len(symbols), "dir": str(folder)}
    )
    return launch(folder)


def start(out_dir: Path, args: argparse.Namespace) -> int:
  """
  编替身库与 bind() 替换，经 limited_run.run 在空闲端口上启动编辑器，等到 vnc 服务应答、且端口没有在通配地址上监听后打印 ready 事件，编辑器结束后返回
  参数：
      out_dir (Path): 证据目录
      args (argparse.Namespace): 命令行参数
  返回：
      int: 退出码
  """
  root = limited_run.game_checkout()
  if not (root / "tools" / "ArkEditor" / "main.py").is_file():
    sys.exit(f"{root} 下没有 tools/ArkEditor/main.py")
  if out_dir.exists() and any(out_dir.iterdir()):
    sys.exit(
        f"{out_dir} 不是空目录。每次启动用一个新目录，免得读到上一次的帧。"
    )
  if not re.fullmatch(r"\d+x\d+", args.size):
    sys.exit(f"--size 要写成 宽x高，例如 {DEFAULT_SIZE}")
  out_dir.mkdir(parents=True, exist_ok=True)
  port = free_port()
  return with_stub(
      lambda folder: limited_run.run(
          "editor",
          editor_command(
              root, out_dir, folder / LOOPBACK, sys.executable, args.size, port
          ),
          args.mem,
          args.timeout,
          {"LD_LIBRARY_PATH": str(folder)},
          out_dir,
          lambda: vnc_ready(port),
          args.ready_timeout,
      ),
      loopback=True,
  )


def run_command(args: argparse.Namespace) -> int:
  """
  编替身库，经 limited_run.run 按 headless 模式运行给定命令，与 limited_run.py 直接运行相同，只多了 scope 里的 LD_LIBRARY_PATH
  参数：
      args (argparse.Namespace): 命令行参数
  返回：
      int: 命令的退出码，或 limited_run 的退出码
  """
  if args.command[:1] != ["--"] or len(args.command) < 2:
    sys.exit("在 -- 之后给出要运行的命令")
  limited_run.game_checkout()
  seed = {
      "PYTHONHASHSEED": os.environ.get("PYTHONHASHSEED", limited_run.seed())
  }
  return with_stub(
      lambda folder: limited_run.run(
          "headless",
          args.command[1:],
          args.mem,
          args.timeout,
          {**seed, "LD_LIBRARY_PATH": str(folder)},
      ),
      loopback=False,
  )


def main(argv: list[str] | None = None) -> int:
  """
  命令行入口
  参数：
      argv (list[str] | None): 命令行参数，不含脚本名；为 None 时读 sys.argv
  返回：
      int: 退出码
  """
  parser = argparse.ArgumentParser(
      prog="arkeditor.py",
      description="经 limited_run 启动 ArkEditor 并用真实输入操作它，或带替身 libEGL.so.1 运行任意命令",
  )
  sub = parser.add_subparsers(dest="action", required=True)
  limits = argparse.ArgumentParser(add_help=False)
  limits.add_argument(
      "--mem",
      type=limited_run.parse_size,
      default=DEFAULT_MEM,
      help=f"内存上限，默认 {DEFAULT_MEM}",
  )
  limits.add_argument(
      "--timeout", type=int, default=600, help="运行时限（秒），默认 600"
  )
  out = argparse.ArgumentParser(add_help=False)
  out.add_argument(
      "--out",
      required=True,
      type=Path,
      help="证据目录：start 时必须不存在或为空，之后的命令用它找到这次运行",
  )
  frame = argparse.ArgumentParser(add_help=False, parents=[out])
  frame.add_argument("--label", help="写进帧文件名的标签")
  frame.add_argument(
      "--wait", type=float, default=1.0, help="动作后等多少秒再取帧，默认 1"
  )
  launch = sub.add_parser(
      "start",
      parents=[out, limits],
      help="启动编辑器并一直运行到 stop 或时限为止；它占着终端，要接着发动作就在命令后加 & 放到后台",
  )
  launch.add_argument(
      "--ready-timeout",
      type=int,
      default=120,
      help="等 vnc 服务应答的秒数，默认 120",
  )
  launch.add_argument(
      "--size", default=DEFAULT_SIZE, help=f"画面大小，默认 {DEFAULT_SIZE}"
  )
  for name in BUTTONS:
    pointer = sub.add_parser(name, parents=[frame])
    pointer.add_argument("x", type=int)
    pointer.add_argument("y", type=int)
  drag = sub.add_parser("drag", parents=[frame])
  for name in ("x1", "y1", "x2", "y2"):
    drag.add_argument(name, type=int)
  sub.add_parser("key", parents=[frame]).add_argument("keys", nargs="+")
  sub.add_parser("type", parents=[frame]).add_argument("text")
  sub.add_parser("shot", parents=[frame])
  sub.add_parser("stop", parents=[out])
  sub.add_parser(
      "run",
      parents=[limits],
      help="带替身 libEGL.so.1 在 limited_run 下运行 -- 之后的命令",
  ).add_argument("command", nargs=argparse.REMAINDER)
  args = parser.parse_args(argv)
  if args.action == "run":
    return run_command(args)
  out_dir = args.out.expanduser().resolve()
  if args.action == "start":
    return start(out_dir, args)
  run = find_run(out_dir)
  if args.action == "stop":
    return limited_run.cmd_stop(str(run["pid"]))
  if "vnc_port" not in run:
    sys.exit("编辑器还没就绪，等 start 打印 ready 事件后再操作。")
  print(f"frame: {act(out_dir, int(str(run['vnc_port'])), args)}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
