import argparse
import ctypes
import os
import sys
import tempfile
import traceback
from pathlib import Path


def load_local_fontfix(mod_root: Path) -> dict:
    script_path = mod_root / "scripts" / "local_fontfix.py"
    namespace = {
        "__builtins__": __builtins__,
        "__name__": "mod_local_fontfix",
        "__file__": str(mod_root),
        "_LOCAL_FONTFIX_DISABLE_AUTO_REGISTER": True,
    }
    script = script_path.read_text(encoding="utf-8")
    exec(compile(script, str(script_path), "exec"), namespace)
    return namespace


def test_registers_supported_font_files_with_private_scope(mod_root: Path) -> None:
    namespace = load_local_fontfix(mod_root)
    calls = []

    class FakeGdi32:
        def AddFontResourceExW(self, font_path, flags, reserved):
            calls.append((font_path, flags, reserved))
            return 1

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        first = temp_path / "first.ttf"
        second = temp_path / "second.otf"
        ignored = temp_path / "ignored.txt"
        first.write_bytes(b"not a real font")
        second.write_bytes(b"not a real font")
        ignored.write_text("ignore", encoding="utf-8")

        total = namespace["register_local_fonts"](
            font_dirs=[str(temp_path), str(temp_path)],
            gdi32=FakeGdi32(),
        )

    assert total == 2
    assert calls == [
        (str(first.resolve()), namespace["FR_PRIVATE"], 0),
        (str(second.resolve()), namespace["FR_PRIVATE"], 0),
    ]
    assert namespace["_registered_font_paths"] == [
        str(first.resolve()),
        str(second.resolve()),
    ]


def test_private_registration_makes_sarasa_family_available_to_tk(mod_root: Path) -> None:
    if os.name != "nt":
        return

    import tkinter as tk
    from tkinter import font

    namespace = load_local_fontfix(mod_root)
    game_root = mod_root.parent.parent
    font_path = game_root / "static" / "fonts" / "等距更纱黑体.ttf"
    assert font_path.exists()

    root = tk.Tk()
    root.withdraw()
    try:
        namespace["register_local_fonts"](font_dirs=[str(font_path.parent)])
        sarasa = font.Font(root=root, family="等距更纱黑体 SC", size=20)
        assert sarasa.actual("family") == "等距更纱黑体 SC"
    finally:
        ctypes.windll.gdi32.RemoveFontResourceExW(
            str(font_path.resolve()),
            namespace["FR_PRIVATE"],
            0,
        )
        root.destroy()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mod-root", required=True, type=Path)
    args = parser.parse_args()
    mod_root = args.mod_root.resolve()

    test_registers_supported_font_files_with_private_scope(mod_root)
    test_private_registration_makes_sarasa_family_available_to_tk(mod_root)
    print("local_fontfix mod tests passed", flush=True)


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        traceback.print_exc()
        sys.exit(1)
