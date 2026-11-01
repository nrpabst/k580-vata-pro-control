"""System-tray icon for K580 Control using the plain Win32 API (ctypes), no extra packages.

The icon runs its own message loop in a background thread and hands events to Tk through a
queue, because Tk must only be touched from its own thread.
"""
import colorsys
import ctypes
import math
import os
import queue
import struct
import tempfile
import threading
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

WM_DESTROY, WM_CLOSE, WM_COMMAND, WM_NULL = 0x0002, 0x0010, 0x0111, 0x0000
WM_APP = 0x8000
WM_DEVICECHANGE = 0x0219      # sent to top-level windows when devices are added or removed
WM_TRAY = WM_APP + 1          # tray icon callback
WM_SHOW = WM_APP + 2          # another instance asks us to show the window
WM_LBUTTONUP, WM_LBUTTONDBLCLK, WM_RBUTTONUP = 0x0202, 0x0203, 0x0205
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x1, 0x2, 0x4, 0x10
CLASS_NAME = "K580ControlTrayWnd"
MENU_OPEN, MENU_QUIT = 1, 2


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


class GUID(ctypes.Structure):
    _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                ("szTip", ctypes.c_wchar * 128), ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                ("szInfo", ctypes.c_wchar * 256), ("uTimeout", wintypes.UINT),
                ("szInfoTitle", ctypes.c_wchar * 64), ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", GUID), ("hBalloonIcon", wintypes.HICON)]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                   wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.LoadImageW.restype = wintypes.HANDLE
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int,
                              ctypes.c_int, wintypes.UINT]
user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  wintypes.HWND, ctypes.c_void_p]
user32.FindWindowW.restype = wintypes.HWND
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


def make_icon(path, size=32):
    """Write a small .ico: an RGB ring on a dark rounded square, like the app's accent."""
    px = []
    c = (size - 1) / 2
    for y in range(size - 1, -1, -1):                 # BMP rows are bottom-up
        for x in range(size):
            dx, dy = x - c, y - c
            r = math.hypot(dx, dy) / c
            inside = max(abs(dx), abs(dy)) <= c - 0.5
            if 0.55 <= r <= 0.9:
                h = (math.atan2(dy, dx) / (2 * math.pi)) % 1.0
                rr, gg, bb = colorsys.hsv_to_rgb(h, 0.85, 1.0)
                px.append(struct.pack("<BBBB", int(bb * 255), int(gg * 255), int(rr * 255), 255))
            elif inside:
                px.append(struct.pack("<BBBB", 0x1d, 0x15, 0x13, 255))
            else:
                px.append(b"\0\0\0\0")
    xor = b"".join(px)
    and_mask = b"\0" * (((size + 31) // 32) * 4 * size)
    bih = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, len(xor) + len(and_mask), 0, 0, 0, 0)
    img = bih + xor + and_mask
    ico = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32, len(img), 22) + img
    with open(path, "wb") as f:
        f.write(ico)
    return path


def icon_path():
    p = os.path.join(tempfile.gettempdir(), "k580-control.ico")
    if not os.path.exists(p):
        make_icon(p)
    return p


def show_existing():
    """If another copy of the app is running, ask it to show its window. Returns True if found."""
    hwnd = user32.FindWindowW(CLASS_NAME, None)
    if hwnd:
        user32.PostMessageW(hwnd, WM_SHOW, 0, 0)
        return True
    return False


class Tray:
    """Tray icon. Events ('open' / 'quit') are put on self.events for the Tk thread to poll."""

    def __init__(self, tooltip="K580 Control"):
        self.tooltip = tooltip
        self.events = queue.Queue()
        self.hwnd = None
        self.nid = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(3)

    def _run(self):
        hinst = kernel32.GetModuleHandleW(None)
        self._proc = WNDPROC(self._wndproc)                # keep a reference so it isn't collected
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.lpszClassName = CLASS_NAME
        user32.RegisterClassW(ctypes.byref(wc))
        self.hwnd = user32.CreateWindowExW(0, CLASS_NAME, "K580 Control tray", 0, 0, 0, 0, 0,
                                           None, None, hinst, None)
        hicon = user32.LoadImageW(None, icon_path(), 1, 0, 0, 0x10 | 0x40)   # IMAGE_ICON, FROMFILE|DEFAULTSIZE
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = hicon
        nid.szTip = self.tooltip
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        self.nid = nid
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_DEVICECHANGE:
            self.events.put("devices")              # a USB device came or went (cable, dongle)
        if msg == WM_TRAY:
            if lparam in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                self.events.put("open")
            elif lparam == WM_RBUTTONUP:
                self._menu(hwnd)
            return 0
        if msg == WM_SHOW:
            self.events.put("open")
            return 0
        if msg == WM_CLOSE:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _menu(self, hwnd):
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, 0, MENU_OPEN, "Open K580 Control")
        user32.AppendMenuW(menu, 0x800, 0, None)          # separator
        user32.AppendMenuW(menu, 0, MENU_QUIT, "Quit")
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(hwnd)
        cmd = user32.TrackPopupMenu(menu, 0x0100 | 0x0002, pt.x, pt.y, 0, hwnd, None)  # RETURNCMD|RIGHTBUTTON
        user32.PostMessageW(hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(menu)
        if cmd == MENU_OPEN:
            self.events.put("open")
        elif cmd == MENU_QUIT:
            self.events.put("quit")

    def notify(self, title, text):
        """Show a balloon/toast from the tray icon."""
        if not self.nid:
            return
        n = self.nid
        n.uFlags = NIF_INFO
        n.szInfoTitle = title
        n.szInfo = text
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(n))

    def close(self):
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
            self._thread.join(2)
