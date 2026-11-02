#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
arkeditor.py 的测试：对假 RFB 服务发出的指针与按键事件（含按住左键的拖动、拒收菜单键）、取到的帧与 actions.log、EGL 符号的收集与拒收、替身库被调用时报名并 abort、
bind() 替换把通配地址改绑到回环地址、在通配地址上监听时不报就绪、start 与 run 经 limited_run.run 启动并只在 scope 里设 LD_LIBRARY_PATH；不启动游戏，也不启动编辑器

用法：
    python3 tools/verify/test_arkeditor.py
"""

import contextlib
import io
import os
import pathlib
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import zlib
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import arkeditor
import limited_run

WIDTH, HEIGHT = 4, 3


class FakeVnc(threading.Thread):
  """
  只服务一个连接的假 RFB 服务：无认证握手，记下收到的指针与按键事件，收到整屏请求时先发 extra 里的消息，再发两个 raw 矩形拼成的整屏
  """

  def __init__(
      self,
      version: bytes = b"RFB 003.008\n",
      extra: bytes = b"",
      encoding: int = 0,
  ) -> None:
    """
    在空闲端口上监听
    参数：version (bytes) 握手的版本串；extra (bytes) 整屏更新前先发的消息；encoding (int) 矩形的编码号
    """
    super().__init__(daemon=True)
    self.version, self.extra, self.encoding = version, extra, encoding
    self.listener = socket.create_server(("127.0.0.1", 0))
    self.port = self.listener.getsockname()[1]
    self.events: list[tuple[object, ...]] = []
    self.start()

  def recv(self, conn: socket.socket, size: int) -> bytes:
    """
    读满 size 个字节，对方断开时返回空串
    参数：conn (socket.socket) 连接；size (int) 字节数
    返回：bytes 数据
    """
    buf = b""
    while len(buf) < size:
      chunk = conn.recv(size - len(buf))
      if not chunk:
        return b""
      buf += chunk
    return buf

  def run(self) -> None:
    """接受一个连接并按 RFB 应答，直到客户端断开"""
    with self.listener:
      conn, _ = self.listener.accept()
    try:
      self.serve(conn)
    except OSError:
      pass
    finally:
      conn.close()

  def serve(self, conn: socket.socket) -> None:
    """
    按 RFB 应答一个连接，直到客户端断开
    参数：conn (socket.socket) 连接
    """
    conn.sendall(self.version)
    self.recv(conn, 12)
    if self.version.startswith(b"RFB 003.003"):
      conn.sendall(struct.pack(">I", 1))
    else:
      conn.sendall(b"\x01\x01")
      self.recv(conn, 1)
      conn.sendall(struct.pack(">I", 0))
    self.recv(conn, 1)
    name = b"fake"
    conn.sendall(struct.pack(">HH16xI", WIDTH, HEIGHT, len(name)) + name)
    while True:
      kind = self.recv(conn, 1)
      if not kind:
        return
      if kind[0] == 0:
        self.recv(conn, 19)
      elif kind[0] == 2:
        count = struct.unpack(">xH", self.recv(conn, 3))[0]
        self.recv(conn, 4 * count)
      elif kind[0] == 3:
        self.recv(conn, 9)
        conn.sendall(self.extra + self.update())
      elif kind[0] == 4:
        down, sym = struct.unpack(">BxxI", self.recv(conn, 7))
        self.events.append(("key", down, sym))
      elif kind[0] == 5:
        self.events.append(
            ("pointer", *struct.unpack(">BHH", self.recv(conn, 5)))
        )

  def update(self) -> bytes:
    """
    整屏更新：上两行一个矩形、最后一行一个矩形；像素 (x, y) 的 B G R 为 (x, y, 200)
    返回：bytes FramebufferUpdate 消息
    """
    body = b""
    for top, rows in ((0, 2), (2, 1)):
      pixels = b"".join(
          bytes([x, y, 200, 0])
          for y in range(top, top + rows)
          for x in range(WIDTH)
      )
      body += struct.pack(">HHHHi", 0, top, WIDTH, rows, self.encoding) + pixels
    return struct.pack(">BxH", 0, 2) + body


def png_pixels(data: bytes) -> tuple[int, int, bytes]:
  """
  解出本测试里 PNG 的宽、高与 RGB 像素（只认 arkeditor.png 写的格式：一个 IDAT、每行滤波类型 0）
  参数：data (bytes) PNG 文件内容
  返回：tuple[int, int, bytes] 宽、高、逐行 RGB
  """
  assert data[:8] == b"\x89PNG\r\n\x1a\n"
  pos, chunks = 8, {}
  while pos < len(data):
    size = struct.unpack(">I", data[pos : pos + 4])[0]
    chunks[data[pos + 4 : pos + 8]] = data[pos + 8 : pos + 8 + size]
    pos += 12 + size
  width, height = struct.unpack(">II", chunks[b"IHDR"][:8])
  raw = zlib.decompress(chunks[b"IDAT"])
  stride = width * 3 + 1
  rows = [raw[row * stride : (row + 1) * stride] for row in range(height)]
  assert all(row[0] == 0 for row in rows)
  return width, height, b"".join(row[1:] for row in rows)


EXPECTED = b"".join(
    bytes([200, y, x]) for y in range(HEIGHT) for x in range(WIDTH)
)


class Drive(unittest.TestCase):
  """经 main() 对假 RFB 服务操作，检查事件、帧与 actions.log"""

  def setUp(self) -> None:
    """建临时证据目录，让 limited_run.live_runs 报出一次指向假服务的运行"""
    tmpdir = tempfile.TemporaryDirectory()
    self.addCleanup(tmpdir.cleanup)
    self.out = pathlib.Path(tmpdir.name).resolve()
    self.server = FakeVnc()
    patcher = mock.patch.object(
        limited_run,
        "live_runs",
        return_value=[
            {"out": str(self.out), "pid": 4321, "vnc_port": self.server.port}
        ],
    )
    patcher.start()
    self.addCleanup(patcher.stop)

  def drive(self, *args: str) -> str:
    """
    运行 main()，等假服务收完事件
    参数：args (str) --out 之后的命令行参数
    返回：str 标准输出
    """
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
      self.assertEqual(
          arkeditor.main(
              [args[0], "--out", str(self.out), "--wait", "0", *args[1:]]
          ),
          0,
      )
    self.server.join(5)
    return stdout.getvalue()

  def test_click_sends_press_and_release_and_saves_frame(self) -> None:
    """click 先移到坐标、再按下松开左键；帧是两个矩形拼成的整屏，actions.log 记下动作与帧名"""
    printed = self.drive("click", "3", "2", "--label", "open/menu now")
    self.assertEqual(
        self.server.events,
        [("pointer", 0, 3, 2), ("pointer", 1, 3, 2), ("pointer", 0, 3, 2)],
    )
    frame = self.out / "frames" / "001-open_menu_now.png"
    self.assertEqual(printed.strip(), f"frame: {frame}")
    self.assertEqual(png_pixels(frame.read_bytes()), (WIDTH, HEIGHT, EXPECTED))
    log = (self.out / "actions.log").read_text(encoding="utf-8").split("\t")
    self.assertEqual(log[1:], ["click 3 2", "001-open_menu_now.png\n"])

  def test_dclick_and_rclick_masks(self) -> None:
    """dclick 按两次左键；rclick 用右键位 4"""
    self.drive("dclick", "1", "1")
    self.assertEqual(
        [event[1] for event in self.server.events], [0, 1, 0, 1, 0]
    )
    self.server = FakeVnc()
    with mock.patch.object(
        limited_run,
        "live_runs",
        return_value=[
            {"out": str(self.out), "pid": 1, "vnc_port": self.server.port}
        ],
    ):
      self.drive("rclick", "1", "1")
    self.assertEqual([event[1] for event in self.server.events], [0, 4, 0])
    self.assertEqual(
        sorted(path.name[:3] for path in (self.out / "frames").iterdir()),
        ["001", "002"],
    )

  def test_drag_holds_left_button_from_start_to_end(self) -> None:
    """drag 先移到起点并按下左键，按住左键分多步移到终点，在终点松开；actions.log 记下起点与终点"""
    self.drive("drag", "10", "40", "70", "100")
    events = self.server.events
    self.assertEqual(
        events[:2], [("pointer", 0, 10, 40), ("pointer", 1, 10, 40)]
    )
    self.assertEqual(
        events[-2:], [("pointer", 1, 70, 100), ("pointer", 0, 70, 100)]
    )
    path = [(x, y) for _, _, x, y in events[1:-1]]
    self.assertTrue(all(mask == 1 for _, mask, _, _ in events[1:-1]))
    self.assertGreaterEqual(len(set(path)), 10)
    self.assertEqual(path, sorted(path))
    log = (self.out / "actions.log").read_text(encoding="utf-8").split("\t")
    self.assertEqual(log[1], "drag 10 40 70 100")

  def test_menu_key_refused_with_rclick_hint(self) -> None:
    """key Menu 在连接前退出，说明 vnc 平台收不到菜单键、要用 rclick；不发任何事件"""
    for keys in ("Menu", "shift+Menu"):
      with self.subTest(keys=keys), self.assertRaises(SystemExit) as caught:
        arkeditor.main(["key", "--out", str(self.out), keys])
      self.assertIn("rclick", str(caught.exception.code))
    self.assertEqual(self.server.events, [])

  def test_key_combo_presses_in_order_releases_in_reverse(self) -> None:
    """ctrl+s：先按 ctrl 再按 s，先松 s 再松 ctrl；之后的 Return 单独按放"""
    self.drive("key", "ctrl+s", "Return")
    ctrl, return_ = arkeditor.KEYS["ctrl"], arkeditor.KEYS["Return"]
    self.assertEqual(
        self.server.events,
        [
            ("key", 1, ctrl),
            ("key", 1, ord("s")),
            ("key", 0, ord("s")),
            ("key", 0, ctrl),
            ("key", 1, return_),
            ("key", 0, return_),
        ],
    )

  def test_type_sends_one_press_per_character(self) -> None:
    """type 每个字符按放一次，大写字母与加号都直接用它的 keysym"""
    self.drive("type", "aB+/")
    self.assertEqual(
        [event[2] for event in self.server.events if event[1]],
        [ord("a"), ord("B"), ord("+"), ord("/")],
    )

  def test_key_names_the_plus_key(self) -> None:
    """key 里加号写 plus：ctrl+plus 先按 ctrl 再按加号"""
    self.drive("key", "ctrl+plus")
    self.assertEqual(
        [event[2] for event in self.server.events if event[1]],
        [arkeditor.KEYS["ctrl"], ord("+")],
    )

  def test_non_ascii_and_unknown_keys_refused_before_connecting(self) -> None:
    """type 非 ASCII 文字、key 不认识的键名都在连接前退出，不发任何事件"""
    for args in (["type", "前提"], ["key", "ctrl+Hyper"], ["key", "ctrl++"]):
      with self.subTest(args=args), self.assertRaises(SystemExit):
        arkeditor.main([args[0], "--out", str(self.out), *args[1:]])
    self.assertEqual(self.server.events, [])
    self.assertFalse((self.out / "frames").exists())

  def test_not_ready_and_unknown_out(self) -> None:
    """运行还没有 vnc_port 时说明未就绪；没有以该目录启动的运行时说明要先 start"""
    with mock.patch.object(
        limited_run,
        "live_runs",
        return_value=[{"out": str(self.out), "pid": 1}],
    ):
      with self.assertRaises(SystemExit) as caught:
        arkeditor.main(["shot", "--out", str(self.out)])
    self.assertIn("还没就绪", str(caught.exception.code))
    with self.assertRaises(SystemExit) as caught:
      arkeditor.main(["shot", "--out", str(self.out / "other")])
    self.assertIn("start", str(caught.exception.code))

  def test_stop_asks_limited_run_to_stop_that_pid(self) -> None:
    """stop 按证据目录找到运行，交给 limited_run.cmd_stop 停掉它的 pid"""
    with mock.patch.object(limited_run, "cmd_stop", return_value=0) as stop:
      self.assertEqual(arkeditor.main(["stop", "--out", str(self.out)]), 0)
    stop.assert_called_once_with("4321")


class Protocol(unittest.TestCase):
  """RFB 客户端对握手版本与服务端消息的处理"""

  def test_rfb_33_and_skipped_messages(self) -> None:
    """3.3 版握手可用；整屏更新前的调色板、响铃、剪贴板消息被跳过"""
    extra = (
        struct.pack(">BxHH", 1, 0, 1)
        + b"\x00" * 6
        + b"\x02"
        + struct.pack(">B3xI", 3, 2)
        + b"hi"
    )
    server = FakeVnc(version=b"RFB 003.003\n", extra=extra)
    client = arkeditor.Rfb(server.port)
    with client.sock:
      self.assertEqual(client.frame(), EXPECTED)

  def test_unrequested_encoding_raises(self) -> None:
    """服务端发来 raw 以外的编码时报错，不把它当像素贴上"""
    client = arkeditor.Rfb(FakeVnc(encoding=7).port)
    with client.sock, self.assertRaisesRegex(ConnectionError, "编码 7"):
      client.frame()

  def test_vnc_ready(self) -> None:
    """端口应答 RFB 版本串时就绪，端口没人监听时不就绪"""
    server = FakeVnc()
    self.assertEqual(
        arkeditor.vnc_ready(server.port), {"vnc_port": server.port}
    )
    self.assertIsNone(arkeditor.vnc_ready(arkeditor.free_port()))

  def test_wildcard_listener_stops_instead_of_ready(self) -> None:
    """端口在通配地址（IPv4 或 IPv6）上监听时退出并说明会被别的主机连上，不报就绪"""
    for address in ("00000000", "0" * 32):
      with self.subTest(address=address), mock.patch.object(
          arkeditor, "listeners", return_value=[address]
      ), self.assertRaises(SystemExit) as caught:
        arkeditor.vnc_ready(5900)
      self.assertIn("所有网络接口", str(caught.exception.code))

  def test_listeners_reads_listening_sockets_on_port(self) -> None:
    """只收第 4 列为 0A（监听）且端口相符的行，地址原样返回"""
    header = "  sl  local_address rem_address   st\n"
    rows = {
        "tcp": header
        + "   0: 0100007F:170C 00000000:0000 0A\n"
        + "   1: 0100007F:170C 0100007F:9C40 01\n"
        + "   2: 00000000:170D 00000000:0000 0A\n",
        "tcp6": header
        + "   0: 0000000000000000FFFF00000100007F:170C 00000000000000000000000000000000:0000 0A\n",
    }
    with tempfile.TemporaryDirectory() as tmp:
      tables = []
      for name, text in rows.items():
        (pathlib.Path(tmp) / name).write_text(text)
        tables.append(pathlib.Path(tmp) / name)
      self.assertEqual(
          arkeditor.listeners(5900, tuple(tables)),
          ["0100007F", "0000000000000000FFFF00000100007F"],
      )


def dyn_syms(*rows: str) -> str:
  """
  拼出 readelf --dyn-syms -W 的输出
  参数：rows (str) 每行的 类型 绑定 节 名字
  返回：str 输出文字
  """
  lines = [
      "Symbol table '.dynsym' contains 3 entries:",
      "   Num:    Value          Size Type    Bind   Vis      Ndx Name",
  ]
  for number, row in enumerate(rows, 1):
    kind, bind, ndx, name = row.split()
    lines.append(
        f"     {number}: 0000000000000000     0 {kind}    {bind} DEFAULT  {ndx} {name}"
    )
  return "\n".join(lines) + "\n"


class Symbols(unittest.TestCase):
  """从 readelf 输出收集 EGL 符号，PySide6 变得替身代替不了时报清楚的错"""

  def fake_readelf(self, libs: dict[str, tuple[list[str], str]]) -> mock.Mock:
    """
    让 arkeditor.readelf 按库名返回给定的依赖与符号表
    参数：libs (dict) 库名到（依赖列表，--dyn-syms 输出）
    返回：mock.Mock 替换后的 readelf
    """

    def readelf(*args: str) -> str:
      needed, syms = libs[pathlib.Path(args[-1]).name]
      if args[0] == "-d":
        return "".join(
            f" 0x0000000000000001 (NEEDED)             Shared library: [{name}]\n"
            for name in needed
        )
      return syms

    patcher = mock.patch.object(arkeditor, "readelf", side_effect=readelf)
    self.addCleanup(patcher.stop)
    return patcher.start()

  def test_collects_global_egl_functions_from_egl_users_only(self) -> None:
    """只收依赖 libEGL.so.1 的库里未定义的 egl 全局函数；已定义的、弱符号、别的库的符号都不收，结果去重排序"""
    self.fake_readelf(
        {
            "gui.so": (
                ["libc.so.6", "libEGL.so.1"],
                dyn_syms(
                    "FUNC GLOBAL UND eglMakeCurrent",
                    "FUNC GLOBAL UND memcpy@GLIBC_2.14",
                    "FUNC WEAK UND eglExtra",
                    "FUNC GLOBAL 12 eglOwn",
                ),
            ),
            "widgets.so": (
                ["libEGL.so.1"],
                dyn_syms(
                    "FUNC GLOBAL UND eglMakeCurrent",
                    "FUNC GLOBAL UND eglBindAPI",
                ),
            ),
            "core.so": (
                ["libc.so.6"],
                dyn_syms("FUNC GLOBAL UND eglNotFromHere"),
            ),
        }
    )
    libs = [pathlib.Path(name) for name in ("gui.so", "widgets.so", "core.so")]
    self.assertEqual(
        arkeditor.egl_symbols(libs), ["eglBindAPI", "eglMakeCurrent"]
    )

  def test_refuses_what_a_function_stub_cannot_replace(self) -> None:
    """引用了带版本的或非函数的 EGL 符号、或者没有库再依赖 libEGL.so.1 时，报出原因而不编出一个错的替身"""
    cases = {
        "versioned": (
            ["libEGL.so.1"],
            dyn_syms("FUNC GLOBAL UND eglGetError@LIBEGL_1.0"),
            "eglGetError@LIBEGL_1.0",
        ),
        "object": (
            ["libEGL.so.1"],
            dyn_syms("OBJECT GLOBAL UND eglTable"),
            "eglTable",
        ),
        "no user": (["libc.so.6"], dyn_syms(), "不再依赖"),
    }
    for case, (needed, syms, message) in cases.items():
      with self.subTest(case=case):
        self.fake_readelf({"gui.so": (needed, syms)})
        with self.assertRaisesRegex(arkeditor.StubError, message):
          arkeditor.egl_symbols([pathlib.Path("gui.so")])

  def test_loaded_libraries_follow_needed_inside_pyside(self) -> None:
    """从三个扩展模块与 vnc 插件出发，沿依赖找 PySide6 目录内的库；目录外的库不收，缺插件时报错"""
    with tempfile.TemporaryDirectory() as tmp:
      pyside = pathlib.Path(tmp)
      (pyside / "Qt" / "lib").mkdir(parents=True)
      (pyside / "Qt" / "plugins" / "platforms").mkdir(parents=True)
      for name in (
          "QtCore.abi3.so",
          "QtGui.abi3.so",
          "QtWidgets.abi3.so",
          "Qt/plugins/platforms/libqvnc.so",
          "Qt/lib/libQt6Gui.so.6",
          "Qt/lib/libQt6Core.so.6",
      ):
        (pyside / name).touch()
      deps = {
          "QtGui.abi3.so": ["libQt6Gui.so.6", "libc.so.6"],
          "libQt6Gui.so.6": ["libQt6Core.so.6", "libEGL.so.1"],
          "libqvnc.so": ["libQt6Gui.so.6"],
      }
      with mock.patch.object(
          arkeditor, "needed", side_effect=lambda lib: deps.get(lib.name, [])
      ):
        names = [lib.name for lib in arkeditor.loaded_libraries(pyside)]
        self.assertEqual(
            names,
            [
                "QtCore.abi3.so",
                "QtGui.abi3.so",
                "QtWidgets.abi3.so",
                "libqvnc.so",
                "libQt6Gui.so.6",
                "libQt6Core.so.6",
            ],
        )
        (pyside / "Qt/plugins/platforms/libqvnc.so").unlink()
        with self.assertRaisesRegex(arkeditor.StubError, "libqvnc.so"):
          arkeditor.loaded_libraries(pyside)


@unittest.skipUnless(
    shutil.which("gcc") and shutil.which("readelf"), "需要本机的 gcc 与 readelf"
)
class Stub(unittest.TestCase):
  """用本机 gcc 编出的替身库"""

  def test_stub_has_soname_and_aborts_loudly_when_called(self) -> None:
    """替身库的 soname 是 libEGL.so.1；被调用的替身把名字写到 stderr 并 abort"""
    with tempfile.TemporaryDirectory() as tmp:
      lib = arkeditor.build_stub(
          pathlib.Path(tmp), ["eglBindAPI", "eglGetError"]
      )
      self.assertIn(
          "Library soname: [libEGL.so.1]", arkeditor.readelf("-d", str(lib))
      )
      code = f"import ctypes; ctypes.CDLL({str(lib)!r}).eglGetError()"
      result = subprocess.run(
          [sys.executable, "-c", code], capture_output=True, text=True
      )
    self.assertEqual(result.returncode, -6)
    self.assertIn("egl_stub: eglGetError called", result.stderr)

  def test_loopback_shim_rebinds_wildcard_addresses(self) -> None:
    """载入 bind() 替换的进程绑定 0.0.0.0 与双栈 :: 时都落到回环地址，经 127.0.0.1 仍连得上双栈监听"""
    code = """
import socket
v4 = socket.socket()
v4.bind(("0.0.0.0", 0))
v6 = socket.socket(socket.AF_INET6)
v6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
v6.bind(("::", 0))
v6.listen()
socket.create_connection(("127.0.0.1", v6.getsockname()[1])).close()
print(v4.getsockname()[0], v6.getsockname()[0])
"""
    with tempfile.TemporaryDirectory() as tmp:
      shim = arkeditor.build_loopback(pathlib.Path(tmp))
      result = subprocess.run(
          [sys.executable, "-c", code],
          capture_output=True,
          text=True,
          env={**os.environ, "LD_PRELOAD": str(shim)},
      )
    self.assertEqual(result.stdout.split(), ["127.0.0.1", "::ffff:127.0.0.1"])

  def test_gcc_failure_is_reported(self) -> None:
    """符号名编不过时报出 gcc 的错误"""
    with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(
        arkeditor.StubError, "gcc"
    ):
      arkeditor.build_stub(pathlib.Path(tmp), ["not a name"])


class Start(unittest.TestCase):
  """start 编替身、选端口，经 limited_run.run 启动"""

  def setUp(self) -> None:
    """建一个带 tools/ArkEditor/main.py 的假 checkout 并切换进去，替身的编译换成记下目录"""
    tmpdir = tempfile.TemporaryDirectory()
    self.addCleanup(tmpdir.cleanup)
    self.root = pathlib.Path(tmpdir.name).resolve()
    (self.root / "tools" / "ArkEditor").mkdir(parents=True)
    (self.root / "tools" / "ArkEditor" / "main.py").touch()
    (self.root / "game.py").touch()
    self.addCleanup(os.chdir, os.getcwd())
    os.chdir(self.root)
    self.stub_dirs: list[pathlib.Path] = []
    for name, value in (
        ("pyside_dir", mock.Mock()),
        ("loaded_libraries", mock.Mock()),
        ("egl_symbols", mock.Mock(return_value=["eglBindAPI"])),
    ):
      patcher = mock.patch.object(arkeditor, name, value)
      patcher.start()
      self.addCleanup(patcher.stop)
    patcher = mock.patch.object(
        arkeditor,
        "build_stub",
        side_effect=lambda dest, symbols: self.stub_dirs.append(dest),
    )
    patcher.start()
    self.addCleanup(patcher.stop)
    patcher = mock.patch.object(arkeditor, "build_loopback")
    self.build_loopback = patcher.start()
    self.addCleanup(patcher.stop)

  def test_runs_through_limited_run_with_stub_only_in_scope(self) -> None:
    """tk 模式、2G、证据目录与 vnc 就绪检查交给 limited_run.run；替身目录只作为 scope 的环境变量 LD_LIBRARY_PATH 传下，
    bind() 替换只经 LD_PRELOAD 给编辑器那一行，运行结束后删掉临时目录"""
    out = self.root / "run"
    with mock.patch.object(
        limited_run, "run", return_value=0
    ) as run, contextlib.redirect_stdout(io.StringIO()) as stdout:
      self.assertEqual(
          arkeditor.main(["start", "--out", str(out), "--size", "1600x900"]), 0
      )
    (
        mode,
        command,
        mem_max,
        timeout,
        extra,
        out_dir,
        ready_check,
        ready_timeout,
    ) = run.call_args.args
    stub_dir = self.stub_dirs[0]
    self.assertEqual(
        (mode, mem_max, timeout, extra, out_dir, ready_timeout),
        ("editor", 2 << 30, 600, {"LD_LIBRARY_PATH": str(stub_dir)}, out, 120),
    )
    self.assertNotIn("LD_LIBRARY_PATH", os.environ)
    self.build_loopback.assert_called_once_with(stub_dir)
    editor_line = [
        line for line in command[2].splitlines() if "main.py" in line
    ]
    self.assertEqual(len(editor_line), 1)
    self.assertTrue(
        editor_line[0].startswith(
            f"LD_PRELOAD={stub_dir / arkeditor.LOOPBACK} exec "
        )
    )
    self.assertIn("main.py -platform vnc:size=1600x900:port=", editor_line[0])
    self.assertEqual(command[2].count("LD_PRELOAD"), 1)
    self.assertIn('"event": "egl-stub"', stdout.getvalue())
    self.assertIsNone(ready_check())
    self.assertFalse(stub_dir.exists())

  def test_stub_error_and_bad_out_stop_before_launch(self) -> None:
    """替身编不出时以 2 退出；证据目录不空时退出；两种情况都不启动"""
    with mock.patch.object(limited_run, "run", return_value=0) as run:
      with mock.patch.object(
          arkeditor,
          "egl_symbols",
          side_effect=arkeditor.StubError("PySide6 变了"),
      ), contextlib.redirect_stderr(io.StringIO()) as stderr:
        self.assertEqual(
            arkeditor.main(["start", "--out", str(self.root / "a")]), 2
        )
      self.assertIn("PySide6 变了", stderr.getvalue())
      (self.root / "b").mkdir()
      (self.root / "b" / "editor.log").touch()
      with self.assertRaises(SystemExit):
        arkeditor.main(["start", "--out", str(self.root / "b")])
    run.assert_not_called()

  def test_run_passes_any_command_with_stub(self) -> None:
    """run 按 headless 模式把 -- 之后的命令交给 limited_run.run，带替身目录与固定的 PYTHONHASHSEED，不编 bind() 替换；没给命令时退出、不启动"""
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/fast/test_arkeditor_effect_menu.py",
    ]
    with mock.patch.object(
        limited_run, "run", return_value=5
    ) as run, mock.patch.dict(
        os.environ, {}, clear=True
    ), contextlib.redirect_stdout(
        io.StringIO()
    ):
      self.assertEqual(
          arkeditor.main(["run", "--mem", "3G", "--", *command]), 5
      )
      with self.assertRaises(SystemExit):
        arkeditor.main(["run"])
    self.assertEqual(run.call_count, 1)
    self.build_loopback.assert_not_called()
    stub_dir = self.stub_dirs[0]
    self.assertEqual(
        run.call_args.args,
        (
            "headless",
            command,
            3 << 30,
            600,
            {
                "PYTHONHASHSEED": limited_run.DEFAULT_SEED,
                "LD_LIBRARY_PATH": str(stub_dir),
            },
        ),
    )
    self.assertFalse(stub_dir.exists())


if __name__ == "__main__":
  unittest.main()
