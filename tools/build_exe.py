"""Builds dist\\K580 Control.exe: one file with Python, the app and the bundled flasher inside.

Needs PyInstaller (pip install pyinstaller). Run from anywhere:  python tools\\build_exe.py
No Redragon firmware goes into the .exe; the Firmware page reads the user's own keyboard.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
BUILD = os.path.join(ROOT, "build")

sys.path.insert(0, APP)
import k580_tray  # noqa: E402

os.makedirs(BUILD, exist_ok=True)
icon = os.path.join(BUILD, "k580-control.ico")
k580_tray.make_icon(icon, size=64)

subprocess.check_call([
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
    "--name", "K580 Control", "--icon", icon,
    "--paths", APP,
    "--add-data", os.path.join(ROOT, "third_party", "sinowisp") + os.pathsep + "third_party/sinowisp",
    "--distpath", os.path.join(ROOT, "dist"), "--workpath", BUILD, "--specpath", BUILD,
    os.path.join(APP, "k580_app.py"),
])
print("built", os.path.join(ROOT, "dist", "K580 Control.exe"))
