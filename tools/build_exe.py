"""Builds dist\\K580 Control.exe (one file with Python, the app and the bundled flasher inside) and,
if Inno Setup 6 is installed, the installer dist\\K580-Control-Setup-<version>.exe.

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

import k580_app  # noqa: E402  (for the version number)
iscc = [p for p in (os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
                    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe", r"C:\Program Files\Inno Setup 6\ISCC.exe")
        if os.path.exists(p)]
if iscc:
    subprocess.check_call([iscc[0], "/Q", f"/DAppVersion={k580_app.APP_VERSION}",
                           os.path.join(ROOT, "tools", "installer.iss")])
    print("built", os.path.join(ROOT, "dist", f"K580-Control-Setup-{k580_app.APP_VERSION}.exe"))
else:
    print("Inno Setup 6 not found: skipped the installer (winget install JRSoftware.InnoSetup)")
