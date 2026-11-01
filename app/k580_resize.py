"""Smooth window resizing on Windows.

Tk registers its window classes with CS_HREDRAW | CS_VREDRAW, so every change in the window's size
makes Windows repaint every widget in it (about 1 ms each): dragging the border of a busy window
stutters. Without those flags only the part that actually changed is repainted; Tk still redraws
any widget whose own size changes.
"""
import ctypes

GCL_STYLE = -26
CS_VREDRAW, CS_HREDRAW = 0x0001, 0x0002

user32 = ctypes.windll.user32
user32.GetParent.restype = ctypes.c_void_p
user32.GetParent.argtypes = [ctypes.c_void_p]
user32.GetClassLongPtrW.restype = ctypes.c_size_t
user32.GetClassLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
user32.SetClassLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]


def install(root):
    """Drop the full-repaint flags from Tk's toplevel and child window classes (one call is enough)."""
    try:
        root.update_idletasks()
        child = root.winfo_id()                          # class TkChild: every widget
        for hwnd in (user32.GetParent(child), child):    # class TkTopLevel: the window frame
            style = user32.GetClassLongPtrW(hwnd, GCL_STYLE)
            user32.SetClassLongPtrW(hwnd, GCL_STYLE, style & ~(CS_HREDRAW | CS_VREDRAW))
    except Exception:
        pass
