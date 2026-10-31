# K580 VATA PRO Control

A simple, open-source replacement for the Redragon K580 VATA PRO (K580RGB-PRO) software, with lighting,
key remapping, macros, backups, and an optional firmware patch that keeps the media-key lights on.

Unofficial. Not affiliated with or endorsed by Redragon. Use at your own risk.

## Features

- **Lighting:** effect, brightness, speed and color, applied instantly over the USB cable or the 2.4G dongle.
- **Keys:** remap any key on the normal or Fn layer to a key, key combination, mouse button,
  multimedia key, Windows command or lighting control, or disable it. You can also reset a key.
- **Macros:** record keystrokes with their timing, or type text. A macro can play once,
  N times, while the key is held, or until another key is pressed.
- **Key colors:** click keys on a picture of the keyboard and pick colors (the Self-define effect).
- **Settings:** debounce, wireless sleep timer, start with Windows, update check, factory reset.
- **System tray:** closing the window keeps the app running in the tray; it can start with Windows.
- **Backup and restore** of lighting, all key layers and macros, including the G1–G5 recordings.
- **Optional custom firmware:** keeps the media-key lights and the volume/brightness-key light on,
  each with an instant on/off checkbox. See [below](#custom-firmware).

## Requirements

- Windows with Python 3.10 or newer ([python.org](https://www.python.org/downloads/)). Nothing else to install;
  the app uses only Tkinter and the Windows HID API.
- A K580 VATA PRO. Wired mode is its USB ID `258A:010C`; the 2.4G dongle is `3554:FA09`.

## Running

Download the repository (green **Code** button → **Download ZIP**, or `git clone`), then double-click
`K580 Control.bat`, or run `pythonw k580_app.py`.

Lighting works over the cable or the dongle. Keys, Macros, Key colors and Firmware need the
**cable with the keyboard's wireless switch off**.

## Custom firmware

The stock firmware only flashes the media-key lights briefly when you press them. The patch changes 30
bytes so those lights, and the volume/brightness-key light, can stay on. You switch each one on or off
from the Lighting page.

- **No Redragon firmware is included in this repository.** The installer reads your keyboard's own
  firmware, checks that it's the exact version the patch was made for (by checksum), and saves an
  untouched copy for undo. Only then does it apply the patch and write it back. If the check fails,
  nothing is changed.
- Flashing uses [sinowisp](https://github.com/karstx/sinowisp) v2.1.0, an open-source (MIT) SinoWealth ISP
  tool. It's bundled in `third_party/sinowisp/` (unmodified official release; checksum and license there),
  so there's nothing extra to download.
- Installing resets the keyboard's settings. The app saves them first and puts them back.
- **Uninstall** on the Firmware page writes your saved original back.
- Side effect: the patch drops a hidden WASD/arrow-swap mode that no key on the K580 is set up to use.

Flashing firmware always carries some risk. The keyboard's bootloader isn't touched, so a failed
flash can normally be recovered by writing the original back with sinowisp.

## Command-line library

`k580.py` can be used on its own:

```bash
python k580.py info                  # connection, password/ID, lighting block
python k580.py keys 0                # list layer 0 key assignments
python k580.py led                   # decode the lighting settings
python k580.py backup my.json        # save settings
python k580.py restore my.json       # put them back
python k580.py live 5 0=ff0000       # light Esc red for 5 seconds (live mode)
```

## Files

| File | What it is |
|------|------------|
| `k580_app.py` | The desktop app (Tkinter) |
| `k580.py` | Wired HID protocol library and CLI |
| `k580_wireless.py` | 2.4G dongle protocol |
| `k580_patch.py` | Firmware patch definition and installer helpers |
| `k580_layout.py` | Key positions for drawing the keyboard |
| `k580_theme.py` | Dark theme and RGB header |
| `k580_tray.py` | System-tray icon (Win32, no extra packages) |
| `K580 Control.bat` | Double-click launcher |
| `third_party/sinowisp/` | Bundled flasher (sinowisp v2.1.0, MIT) used by the Firmware page |
