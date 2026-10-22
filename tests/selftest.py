# -*- coding: utf-8 -*-
import os
import sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

"""核心机制自测：窗口枚举 + DWM 缩略图贴图。
跑法：python selftest.py
产出：selftest.png（截取面板区域），用于确认缩略图真的贴上去了。
"""
import ctypes
import sys
import time
from ctypes import wintypes

# ---------- DPI ----------
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
except Exception as e:
    print("DPI:", e)

u32 = ctypes.windll.user32
dwmapi = ctypes.WinDLL("dwmapi")

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
DWMWA_CLOAKED = 14

DWM_TNP_RECTDESTINATION = 0x00000001
DWM_TNP_VISIBLE = 0x00000008
DWM_TNP_OPACITY = 0x00000004
DWM_TNP_SOURCECLIENTAREAONLY = 0x00000010


class DWM_THUMBNAIL_PROPERTIES(ctypes.Structure):
    _fields_ = [
        ("dwFlags", wintypes.DWORD),
        ("rcDestination", wintypes.RECT),
        ("rcSource", wintypes.RECT),
        ("opacity", wintypes.BYTE),
        ("fVisible", wintypes.BOOL),
        ("fSourceClientAreaOnly", wintypes.BOOL),
    ]


dwmapi.DwmRegisterThumbnail.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.POINTER(ctypes.c_void_p)]
dwmapi.DwmRegisterThumbnail.restype = ctypes.c_long

# 注意：本机 dwmapi.dll 不导出 DwmSetThumbnailProperties，只导出旧名
# DwmUpdateThumbnailProperties（两者结构体完全一致）。
try:
    _set_props = dwmapi.DwmSetThumbnailProperties
except AttributeError:
    _set_props = dwmapi.DwmUpdateThumbnailProperties
_set_props.argtypes = [ctypes.c_void_p, ctypes.POINTER(DWM_THUMBNAIL_PROPERTIES)]
_set_props.restype = ctypes.c_long
dwmapi.DwmUnregisterThumbnail.argtypes = [ctypes.c_void_p]
dwmapi.DwmUnregisterThumbnail.restype = ctypes.c_long
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long

u32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
u32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
u32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
u32.IsWindowVisible.argtypes = [wintypes.HWND]


def is_cloaked(hwnd):
    val = ctypes.c_int(0)
    hr = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(val), ctypes.sizeof(val))
    return hr == 0 and val.value != 0


def class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    u32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def title(hwnd):
    n = u32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    u32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


SKIP_CLASSES = {"Shell_TrayWnd", "Progman", "WorkerW", "Windows.UI.Core.CoreWindow",
                "Shell_SecondaryTrayWnd", "ForegroundStaging"}


def enum_windows(exclude_pid=0):
    out = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, lparam):
        if not u32.IsWindowVisible(hwnd):
            return True
        t = title(hwnd)
        if not t:
            return True
        if u32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        if is_cloaked(hwnd):
            return True
        if class_name(hwnd) in SKIP_CLASSES:
            return True
        pid = wintypes.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if exclude_pid and pid.value == exclude_pid:
            return True
        out.append((hwnd, t))
        return True

    u32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def win_rect(hwnd):
    r = wintypes.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    return r


# ---------- 贴图 ----------
class Thumb(object):
    def __init__(self, dst_hwnd, src_hwnd):
        self.id = ctypes.c_void_p()
        hr = dwmapi.DwmRegisterThumbnail(dst_hwnd, src_hwnd, ctypes.byref(self.id))
        self.ok = (hr == 0 and self.id.value)

    def place(self, x, y, w, h):
        if not self.ok:
            return
        p = DWM_THUMBNAIL_PROPERTIES()
        p.dwFlags = (DWM_TNP_RECTDESTINATION | DWM_TNP_VISIBLE | DWM_TNP_OPACITY
                     | DWM_TNP_SOURCECLIENTAREAONLY)
        p.rcDestination = wintypes.RECT(x, y, x + w, y + h)
        p.opacity = 255
        p.fVisible = 1
        p.fSourceClientAreaOnly = 1
        _set_props(self.id, ctypes.byref(p))

    def destroy(self):
        if self.ok:
            dwmapi.DwmUnregisterThumbnail(self.id)
            self.ok = False


def main():
    wins = enum_windows()
    print("枚举到 %d 个窗口" % len(wins))
    for h, t in wins[:12]:
        print("   %08X  %s" % (h & 0xFFFFFFFF, t[:70]))
    if not wins:
        print("没有可测试窗口")
        return 1

    from PyQt5.QtWidgets import QApplication, QWidget
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QColor, QPainter, QFont

    app = QApplication(sys.argv)
    w = QWidget()
    w.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
    w.setAttribute(Qt.WA_ShowWithoutActivating, True)
    w.setGeometry(80, 80, 460, 300)
    w.setStyleSheet("background:#202225;")

    def paint(ev):
        p = QPainter(w)
        p.fillRect(w.rect(), QColor("#202225"))
        p.setPen(QColor("#4a4f57"))
        for i in range(2):
            p.drawRect(8 + i * 226, 8, 208, 117)
        p.setPen(QColor("#e6e6e6"))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(10, 146, "DWM thumbnail self-test")
    w.paintEvent = paint

    w.show()
    app.processEvents()
    time.sleep(0.15)
    app.processEvents()

    dst = int(w.winId())
    thumbs = []
    for i, (h, t) in enumerate(wins[:2]):
        th = Thumb(dst, h)
        print("register %s -> ok=%s" % (t[:30], th.ok))
        th.place(9 + i * 226, 9, 206, 115)
        thumbs.append(th)

    for _ in range(8):
        app.processEvents()
        time.sleep(0.04)

    from PIL import ImageGrab
    g = w.geometry()
    img = ImageGrab.grab(bbox=(g.x(), g.y(), g.x() + g.width(), g.y() + g.height()))
    img.save("selftest.png")
    print("saved selftest.png", img.size)

    for th in thumbs:
        th.destroy()
    w.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
