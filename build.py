from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
BIN = ROOT / "bin"
BUILD = ROOT / "build"

IS_WIN = sys.platform == "win32"
NAME = "yas_filetool"

ICON = (ROOT / "src/yas_filetool/assets/images"
        / ("icon.ico" if IS_WIN else "icon.png"))

sep = ";" if IS_WIN else ":"
assets_src = ROOT / "src" / "yas_filetool" / "assets"
if not assets_src.exists():
    raise SystemExit(f"[FAIL] Error: no directory {assets_src}")
add_data = f"{assets_src}{sep}yas_filetool/assets"


EXCLUDES = [
    "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebEngineQuick",
    "PyQt6.QtWebChannel", "PyQt6.QtWebSockets",
    "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtQuick3D", "PyQt6.QtQuickWidgets",
    "PyQt6.Qt3DCore", "PyQt6.Qt3DRender", "PyQt6.Qt3DInput",
    "PyQt6.Qt3DLogic", "PyQt6.Qt3DAnimation", "PyQt6.Qt3DExtras",
    "PyQt6.QtMultimedia", "PyQt6.QtMultimediaWidgets", "PyQt6.QtSpatialAudio",
    "PyQt6.QtCharts", "PyQt6.QtDataVisualization",
    "PyQt6.QtDesigner", "PyQt6.QtHelp", "PyQt6.QtTest", "PyQt6.QtSql",
    "PyQt6.QtBluetooth", "PyQt6.QtNfc", "PyQt6.QtPositioning", "PyQt6.QtSensors",
    "PyQt6.QtSerialPort", "PyQt6.QtRemoteObjects", "PyQt6.QtScxml",
    "PyQt6.QtPdf", "PyQt6.QtPdfWidgets", "PyQt6.QtTextToSpeech",
    "tkinter", "_tkinter",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["onefile", "onedir"],
                    default="onedir",
                    help="onefile = one file (slow start), "
                         "onedir = directory (fast start, DEFAULT)")
    args = ap.parse_args()

    if BIN.exists():
        shutil.rmtree(BIN)
    BIN.mkdir()
    if BUILD.exists():
        shutil.rmtree(BUILD)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        f"--{args.mode}",
        "--windowed",
        "--noconfirm", "--clean",
        "--name", NAME,
        "--distpath", str(BIN),
        "--workpath", str(BUILD),
        "--specpath", str(BUILD),
        "--add-data", add_data,
        "--paths", "src",
        "--collect-submodules", "yas_filetool",
        "--hidden-import", "PIL._tkinter_finder",
        "--hidden-import", "scipy._lib.array_api_compat",
    ]
    for mod in EXCLUDES:
        cmd += ["--exclude-module", mod]

    if ICON.exists():
        cmd += ["--icon", str(ICON)]

    cmd.append("run_app.py")

    print("Building:", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)

    if args.mode == "onefile":
        out = BIN / (f"{NAME}.exe" if IS_WIN else NAME)
        if not out.exists():
            raise SystemExit(f"[FAIL] Error: {out} not created")
        print(f"\n[OK] Done: {out}  ({out.stat().st_size / 1e6:.1f} MB)")
    else:
        out_dir = BIN / NAME
        if not out_dir.exists():
            raise SystemExit(f"[FAIL] Error: {out_dir} not created")
        exe = out_dir / (f"{NAME}.exe" if IS_WIN else NAME)
        total = sum(f.stat().st_size for f in out_dir.rglob("*") if f.is_file())
        print(f"\n[OK] Done: {out_dir}")
        print(f"  Launch:  {exe}")
        print(f"  Size:  {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
