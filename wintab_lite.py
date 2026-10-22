# -*- coding: utf-8 -*-
"""WinTab Lite —— 左侧抽屉式窗口缩略图切换器

形态：热键唤出，屏幕左侧滑出一个缩略图网格，点击即切换，全程不抢焦点。
依赖：Python 3 + PyQt5（本机已具备），无其他第三方包。
"""
import ctypes
import ctypes.wintypes as wt
import locale
import os
import sys
import threading
import zlib

# 开机自启的读写逻辑放在 autostart.py，托盘菜单复用它
try:
    import autostart as _autostart
except Exception:
    _autostart = None

# 中文按拼音而不是 Unicode 码位排序（阿里云盘 < 钉钉 < 飞书 < 腾讯会议 < 微信）
try:
    locale.setlocale(locale.LC_COLLATE, "Chinese (Simplified)_China.936")
except Exception:
    pass

from PyQt5.QtCore import Qt, QTimer, QRect, QPoint, QPointF, QObject, pyqtSignal, QFileInfo
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QIcon, QPixmap
from PyQt5.QtWidgets import (QApplication, QWidget, QSystemTrayIcon, QMenu,
                             QFileIconProvider)

# ------------------------------------------------------------------ DPI
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32
dwmapi = ctypes.WinDLL("dwmapi")

# ------------------------------------------------------------------ Win32
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x4, 0x10, 0x40
DWMWA_CLOAKED = 14
MOD_ALT = 0x0001
WM_HOTKEY = 0x0312
WM_CLOSE = 0x0010
VK_OEM_3 = 0xC0
MONITOR_DEFAULTTONULL = 0

DWM_TNP_RECTDESTINATION = 0x1
DWM_TNP_RECTSOURCE = 0x2
DWM_TNP_OPACITY = 0x4
DWM_TNP_VISIBLE = 0x8
DWM_TNP_SOURCECLIENTAREAONLY = 0x10


class DWM_THUMBNAIL_PROPERTIES(ctypes.Structure):
    _fields_ = [("dwFlags", wt.DWORD), ("rcDestination", wt.RECT), ("rcSource", wt.RECT),
                ("opacity", wt.BYTE), ("fVisible", wt.BOOL), ("fSourceClientAreaOnly", wt.BOOL)]


dwmapi.DwmRegisterThumbnail.argtypes = [wt.HWND, wt.HWND, ctypes.POINTER(ctypes.c_void_p)]
dwmapi.DwmRegisterThumbnail.restype = ctypes.c_long
dwmapi.DwmUnregisterThumbnail.argtypes = [ctypes.c_void_p]
dwmapi.DwmUnregisterThumbnail.restype = ctypes.c_long
dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]
dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
dwmapi.DwmQueryThumbnailSourceSize.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.SIZE)]
dwmapi.DwmQueryThumbnailSourceSize.restype = ctypes.c_long
try:
    _SET_PROPS = dwmapi.DwmSetThumbnailProperties
except AttributeError:
    _SET_PROPS = dwmapi.DwmUpdateThumbnailProperties
_SET_PROPS.argtypes = [ctypes.c_void_p, ctypes.POINTER(DWM_THUMBNAIL_PROPERTIES)]
_SET_PROPS.restype = ctypes.c_long

u32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
u32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
u32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
u32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
u32.GetWindowTextLengthW.argtypes = [wt.HWND]
u32.IsWindowVisible.argtypes = [wt.HWND]
u32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
u32.SetForegroundWindow.argtypes = [wt.HWND]
u32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
u32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
u32.GetWindowThreadProcessId.restype = wt.DWORD
u32.MonitorFromRect.argtypes = [ctypes.POINTER(wt.RECT), wt.DWORD]
u32.MonitorFromRect.restype = wt.HANDLE


def cursor_pos():
    p = wt.POINT()
    u32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def is_cloaked(hwnd):
    v = ctypes.c_int(0)
    hr = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(v), ctypes.sizeof(v))
    return hr == 0 and v.value != 0


def window_title(hwnd):
    n = u32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    u32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    u32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def window_rect(hwnd):
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    return r


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.OpenProcess.restype = wt.HANDLE
k32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
k32.CloseHandle.argtypes = [wt.HANDLE]


def exe_path(hwnd):
    """取窗口所属进程的可执行文件路径，用于拿应用图标。"""
    pid = wt.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wt.DWORD(1024)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
    finally:
        k32.CloseHandle(h)
    return ""


SKIP_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW",
                "Windows.UI.Core.CoreWindow", "ForegroundStaging", "MultitaskingViewFrame"}


def split_title(full):
    """VS Code 风格 title：'文件 - 项目 - App' → 主标题取倒数第二段。"""
    parts = [p.strip() for p in full.split(" - ")]
    parts = [p for p in parts if p]
    if len(parts) >= 3:
        return parts[-2], " - ".join(parts[:-2])
    if len(parts) == 2:
        return parts[1], parts[0]
    return full, ""


def enum_windows(exclude_pid=0, include_minimized=True):
    out = []
    PROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def cb(hwnd, _):
        if not u32.IsWindowVisible(hwnd):
            return True
        t = window_title(hwnd)
        if not t:
            return True
        if u32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        if is_cloaked(hwnd):
            return True
        if class_name(hwnd) in SKIP_CLASSES:
            return True
        pid = wt.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if exclude_pid and pid.value == exclude_pid:
            return True
        if not include_minimized and u32.IsIconic(hwnd):
            return True
        out.append(hwnd)
        return True

    u32.EnumWindows(PROC(cb), 0)
    return out


def activate_window(hwnd):
    """先做屏幕外归位，再抢前台（绕过前台锁）。"""
    r = window_rect(hwnd)
    if not u32.MonitorFromRect(ctypes.byref(r), MONITOR_DEFAULTTONULL):
        mon = u32.MonitorFromWindow(hwnd, 2)  # NEAREST
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if u32.GetMonitorInfoW(mon, ctypes.byref(info)):
            wa = info.rcWork
            w = min(r.right - r.left, wa.right - wa.left - 80)
            h = min(r.bottom - r.top, wa.bottom - wa.top - 80)
            u32.SetWindowPos(hwnd, 0, wa.left + 40, wa.top + 40, w, h, 0x0004 | 0x0010)

    fg = u32.GetForegroundWindow()
    cur = k32.GetCurrentThreadId()
    fg_tid = u32.GetWindowThreadProcessId(fg, None) if fg else 0
    if u32.IsIconic(hwnd):
        u32.ShowWindow(hwnd, 9)  # SW_RESTORE
    if fg_tid and fg_tid != cur:
        u32.AttachThreadInput(cur, fg_tid, True)
    u32.BringWindowToTop(hwnd)
    u32.SetForegroundWindow(hwnd)
    if fg_tid and fg_tid != cur:
        u32.AttachThreadInput(cur, fg_tid, False)


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT),
                ("dwFlags", wt.DWORD)]


u32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
u32.MonitorFromWindow.restype = wt.HANDLE
u32.GetMonitorInfoW.argtypes = [wt.HANDLE, ctypes.POINTER(MONITORINFO)]
u32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                             ctypes.c_int, ctypes.c_int, ctypes.c_uint]
u32.IsIconic.argtypes = [wt.HWND]
u32.BringWindowToTop.argtypes = [wt.HWND]
u32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]


# ------------------------------------------------------------------ 配置
class Config(object):
    thumb = "standard"      # standard | compact
    scale = "auto"          # auto 按屏幕自动算 | 数字=物理像素倍数（0.6~3.0）
    max_width_ratio = 0.42  # 面板宽度不超过工作区的这个比例
    max_height_ratio = 0.90  # 面板高度不超过工作区的这个比例
    sort = "app_group"      # app_group 按应用分组+字母序 | zorder 纯 Z 序
    fit = "cover"           # cover 裁切填满 | contain 保持完整留边
    show_logo = True        # 缩略图右下角叠加应用图标
    logo_bg = "white"       # white | none | dark
    hotkey = True           # Alt+` 唤出
    intercept_alt_tab = False  # 拦截系统 Alt+Tab，改成打开本面板
    edge_dwell = True       # 鼠标撞左边缘唤出
    edge_px = 2
    include_minimized = True

    @classmethod
    def load(cls, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k == "thumb":
                        cls.thumb = v if v in ("standard", "compact") else "standard"
                    elif k == "scale":
                        v = v.strip().lower()
                        if v == "auto":
                            cls.scale = "auto"
                        else:
                            try:
                                cls.scale = max(0.6, min(3.0, float(v)))
                            except ValueError:
                                pass
                    elif k == "max_width_ratio":
                        try:
                            cls.max_width_ratio = max(0.2, min(0.9, float(v)))
                        except ValueError:
                            pass
                    elif k == "max_height_ratio":
                        try:
                            cls.max_height_ratio = max(0.3, min(1.0, float(v)))
                        except ValueError:
                            pass
                    elif k == "sort":
                        cls.sort = v if v in ("app_group", "zorder") else "app_group"
                    elif k == "fit":
                        cls.fit = v if v in ("cover", "contain") else "cover"
                    elif k == "show_logo":
                        cls.show_logo = v.lower() in ("1", "true", "yes", "on")
                    elif k == "logo_bg":
                        cls.logo_bg = v if v in ("white", "none", "dark") else "white"
                    elif k == "hotkey":
                        cls.hotkey = v.lower() in ("1", "true", "yes", "on")
                    elif k == "intercept_alt_tab":
                        cls.intercept_alt_tab = v.lower() in ("1", "true", "yes", "on")
                    elif k == "edge_dwell":
                        cls.edge_dwell = v.lower() in ("1", "true", "yes", "on")
                    elif k == "edge_px":
                        cls.edge_px = int(v)
                    elif k == "include_minimized":
                        cls.include_minimized = v.lower() in ("1", "true", "yes", "on")
        except FileNotFoundError:
            pass


# ------------------------------------------------------------------ 全局鼠标点击监听
WH_MOUSE_LL = 14
WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN, WM_XBUTTONDOWN = 0x0201, 0x0204, 0x0207, 0x020B
MOUSEDOWN_MSGS = (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN, WM_XBUTTONDOWN)


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wt.POINT), ("mouseData", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wt.WPARAM, wt.LPARAM)
u32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
u32.SetWindowsHookExW.restype = wt.HANDLE
u32.CallNextHookEx.argtypes = [wt.HANDLE, ctypes.c_int, wt.WPARAM, wt.LPARAM]
u32.CallNextHookEx.restype = ctypes.c_ssize_t


class ClickWatcher(QObject):
    """低级鼠标钩子，只用来知道"哪里发生了一次点击"，不拦截任何事件。"""
    clicked = pyqtSignal(int, int)

    def __init__(self):
        QObject.__init__(self)
        self._proc = HOOKPROC(self._cb)          # 必须持有引用，否则会被回收
        self._hook = u32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, None, 0)

    def _cb(self, nCode, wParam, lParam):
        if nCode == 0 and wParam in MOUSEDOWN_MSGS:
            try:
                info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                self.clicked.emit(info.pt.x, info.pt.y)
            except Exception:
                pass
        return u32.CallNextHookEx(None, nCode, wParam, lParam)


# ------------------------------------------------------------------ Alt+Tab 拦截
WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
VK_TAB = 0x09
VK_MENU = 0x12


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class AltTabWatcher(QObject):
    """拦截 Alt+Tab（含 Alt+Shift+Tab），吞掉事件并通知上层。
    注意：Win 把 Alt+Tab 列为系统保留键，RegisterHotKey 注册不了，只能钩。"""
    triggered = pyqtSignal()

    def __init__(self):
        QObject.__init__(self)
        self._proc = HOOKPROC(self._cb)          # 保持引用
        self._hook = u32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        self._swallow_alt_up = False
        self.ok = bool(self._hook)

    def _cb(self, nCode, wParam, lParam):
        if nCode == 0:
            try:
                kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                alt_down = bool(u32.GetAsyncKeyState(VK_MENU) & 0x8000)
                if kb.vkCode == VK_TAB and alt_down:
                    if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        self._swallow_alt_up = True
                        self.triggered.emit()
                    return 1                     # 按下和抬起都吞掉
                # 吞掉紧随其后的 Alt 抬起，避免触发窗口菜单栏
                if kb.vkCode == VK_MENU and wParam in (WM_KEYUP, WM_SYSKEYUP) \
                        and self._swallow_alt_up:
                    self._swallow_alt_up = False
                    return 1
            except Exception:
                pass
        return u32.CallNextHookEx(None, nCode, wParam, lParam)


# ------------------------------------------------------------------ 角标覆盖层
class BadgeOverlay(QWidget):
    """独立顶层半透明窗口：DWM 缩略图会盖住同窗口内的绘制内容，
    所以应用图标必须画在另一个顶层窗口上才能浮在缩略图之上。"""

    def __init__(self):
        QWidget.__init__(self)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                            | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.items = []      # [(QRect badge, QPixmap)]
        self.closes = []     # [(QRect 关闭按钮, 是否悬停)]
        self.bg = Config.logo_bg

    def set_badges(self, items):
        self.items = items
        self.update()

    def set_closes(self, closes):
        self.closes = closes
        self.update()

    def nativeEvent(self, eventType, message):
        # 覆盖窗同样会被跨屏的 WM_DPICHANGED 缩小，直接拒绝，保持与面板同尺寸
        try:
            if eventType == b"windows_generic_MSG":
                msg = ctypes.cast(int(message), ctypes.POINTER(wt.MSG)).contents
                if msg.message == 0x02E0:      # WM_DPICHANGED
                    g = self.geometry()
                    h = int(self.winId())
                    u32.SetWindowPos(h, None, g.x(), g.y(), g.width(), g.height(),
                                     SWP_NOZORDER | SWP_NOACTIVATE)
                    return True, 0
        except Exception:
            pass
        return False, 0

    def paintEvent(self, e):
        if not self.items and not self.closes:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        for rect, pm in self.items:
            if self.bg == "white":
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, 232))
                p.drawRoundedRect(rect, 5, 5)
            elif self.bg == "dark":
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(10, 12, 16, 200))
                p.drawRoundedRect(rect, 5, 5)
            # bg == "none"：不加底，直接贴图标
            p.drawPixmap(rect.x() + (rect.width() - pm.width()) // 2,
                         rect.y() + (rect.height() - pm.height()) // 2, pm)

        # 关闭按钮：state 0=不显示 1=该卡片悬停 2=按钮自身悬停
        for rect, state in self.closes:
            if state == 0:
                continue
            cx = rect.center().x()
            cy = rect.center().y()
            rad = rect.width() / 2.0
            p.setPen(Qt.NoPen)
            # 投影：往下 1px 的暗圈，浅色缩略图上更有层次
            p.setBrush(QColor(0, 0, 0, 70))
            p.drawEllipse(QPointF(cx, cy + 1.5), rad, rad)
            if state == 2:
                p.setBrush(QColor(232, 17, 35, 245))
            else:
                p.setBrush(QColor(14, 16, 20, 190))
            p.drawEllipse(QPointF(cx, cy), rad, rad)
            # 细描边：保证深色缩略图上也有边界
            ring = QPen(QColor(255, 255, 255, 58 if state == 2 else 78))
            ring.setWidthF(max(1.0, rect.width() * 0.045))
            p.setPen(ring)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), rad - 0.6, rad - 0.6)
            # 叉号
            pen = QPen(QColor(255, 255, 255, 250))
            pen.setWidthF(max(1.4, rect.width() * 0.085))
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            k = rect.width() * 0.26
            p.drawLine(QPointF(cx - k, cy - k), QPointF(cx + k, cy + k))
            p.drawLine(QPointF(cx + k, cy - k), QPointF(cx - k, cy + k))


# ------------------------------------------------------------------ 抽屉
class Drawer(QWidget):
    PAD = 16
    GAP = 10
    TITLE_H = 40
    ANIM_STEPS = 8

    def __init__(self):
        QWidget.__init__(self, None)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                            | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)

        # 尺寸先给个初值，真正的大小在 refresh() 里按目标屏幕重算
        self._scale = None
        self._apply_scale(Config.scale if isinstance(Config.scale, (int, float)) else 1.0,
                          force=True)

        self.cols = 1
        self.rows = 0
        self.cells = []          # [(hwnd, main, sub)]
        self.thumbs = []         # [(thumb_id or None)]
        self.scroll = 0
        self.hover = -1
        self.visible_band = (0, 0)
        self._hwnd = None
        self._noactivate_applied = False
        self._shot = QRect()
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._anim_step)
        self._anim_left = 0
        self.no_autohide = False
        self._entered = False       # 本次唤出后鼠标是否进入过面板
        self._opened_at = 0.0
        self._last_closed = 0.0

        self._icon_provider = QFileIconProvider()
        self._icon_cache = {}
        self._dest_rects = {}
        self._close_rects = {}
        self.hover_close = -1
        self.overlay = BadgeOverlay()      # 关闭按钮也要靠它，所以始终创建

    # ---------------- 定位与显隐
    def _apply_noactivate(self):
        if self._noactivate_applied:
            return
        h = int(self.winId())
        self._hwnd = h
        ex = u32.GetWindowLongPtrW(h, GWL_EXSTYLE)
        u32.SetWindowLongPtrW(h, GWL_EXSTYLE,
                              ex | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)
        self._noactivate_applied = True

    def _target_monitor(self):
        x, y = cursor_pos()
        mon = u32.MonitorFromPoint(wt.POINT(x, y), 2)
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        u32.GetMonitorInfoW(mon, ctypes.byref(info))
        return info.rcMonitor, info.rcWork

    def _apply_scale(self, S, force=False):
        """按倍数重算全部尺寸与字号（缩略图/间距/字号/角标等比）。"""
        if not force and self._scale == S:
            return
        self._scale = S
        self.S = S
        base_w, base_h, base_title = (208, 117, 40)
        if Config.thumb == "compact":
            base_w, base_h, base_title = (148, 84, 36)
        self.THUMB_W = int(round(base_w * S))
        self.THUMB_H = int(round(base_h * S))
        self.TITLE_H = int(round(base_title * S))
        self.PAD = int(round(16 * S))
        self.GAP = int(round(10 * S))
        self._h_main = int(round(18 * S))
        self._h_sub = int(round(16 * S))
        # 用像素字号，避免 point 与 pixel 换算导致文字被裁
        f = QFont("Microsoft YaHei UI")
        f.setPixelSize(max(10, int(round(13 * S))))
        f.setBold(True)
        s = QFont("Microsoft YaHei UI")
        s.setPixelSize(max(9, int(round(12 * S))))
        self.f_main, self.f_sub = f, s
        self.fm_main, self.fm_sub = QFontMetrics(f), QFontMetrics(s)
        if hasattr(self, "_icon_cache"):
            self._icon_cache.clear()      # 图标尺寸随 scale 变，缓存要失效

    def _auto_scale(self, work):
        """auto 模式：由物理工作区反推倍数，保证「2 列 × 5 行」放得下。"""
        if not isinstance(Config.scale, str):
            return Config.scale
        ww = float(work.right - work.left)
        wh = float(work.bottom - work.top)
        base_w, base_h, base_title = (208, 117, 40)
        if Config.thumb == "compact":
            base_w, base_h, base_title = (148, 84, 36)
        pitch1 = base_h + base_title + 10
        by_w = ww * Config.max_width_ratio / float(2 * base_w + 10 + 32)
        by_h = wh * Config.max_height_ratio / float(5 * pitch1 - 10 + 32)
        return max(0.9, min(2.6, min(by_w, by_h)))

    def refresh(self):
        pids = {os.getpid()}
        hwnds = enum_windows(os.getpid(), Config.include_minimized)
        self.cells = []
        raw = []
        for z, h in enumerate(hwnds):
            full = window_title(h)
            main, sub = split_title(full)
            raw.append((h, main, sub, exe_path(h), z))

        if Config.sort == "app_group":
            # 组按进程 exe 文件名（ASCII）升序；组内按标题字母序（中文走 locale 拼音），
            # 最后用 Z 序兜底保证同标题时顺序稳定。
            raw.sort(key=lambda it: (os.path.basename(it[3]).lower() or "\uffff",
                                     locale.strxfrm(it[1]),
                                     locale.strxfrm(it[2]),
                                     it[4]))
        self.cells = [(h, m, s, e) for (h, m, s, e, _z) in raw]
        n = len(self.cells)

        mon, work = self._target_monitor()
        # 先按目标屏幕定尺寸：auto 模式下由物理工作区反推，DPI 自然被算进来
        self._apply_scale(self._auto_scale(work))

        ww = work.right - work.left
        wh = work.bottom - work.top
        if n <= 2:
            want_cols = 1
        elif n <= 12:
            want_cols = 2
        else:
            want_cols = 3
        # 宽度上限：放不下就自动减列，仍放不下就缩小 scale
        max_cols = max(1, int((ww * Config.max_width_ratio - self.PAD * 2 + self.GAP)
                              // (self.THUMB_W + self.GAP)))
        self.cols = min(want_cols, max_cols)
        need_w = self.cols * self.THUMB_W + (self.cols - 1) * self.GAP + self.PAD * 2
        if need_w > ww * Config.max_width_ratio:
            k = (ww * Config.max_width_ratio) / float(need_w)
            self._apply_scale(max(0.6, self._scale * k))

        self.rows = (n + self.cols - 1) // self.cols if n else 0
        self.scroll = 0

        cell_h = self.THUMB_H + self.TITLE_H
        pitch = cell_h + self.GAP
        avail_h = int(wh * Config.max_height_ratio)
        max_rows = max(1, avail_h // pitch)
        vis_rows = min(self.rows, max_rows)
        w = self.cols * self.THUMB_W + (self.cols - 1) * self.GAP + self.PAD * 2
        h = vis_rows * pitch - self.GAP + self.PAD * 2
        x = work.left
        y = work.top + (wh - h) // 2
        # 兜底：无论如何都不让面板跑出工作区（副屏坐标可能是负数或比主屏小）
        x = max(work.left, min(x, work.right - w))
        y = max(work.top, min(y, work.bottom - h))
        self._shot = QRect(x, y, w, h)
        self.setGeometry(self._shot)
        self._visible_rows = vis_rows
        self._pitch = pitch
        self._cell_h = cell_h
        self._content_h = self.rows * pitch - self.GAP + self.PAD * 2

        self._build_thumbs()
        self.update()

    def _build_thumbs(self):
        for t in self.thumbs:
            if t:
                dwmapi.DwmUnregisterThumbnail(t)
        self.thumbs = []
        if not self._hwnd:
            return
        for hwnd, main, sub, exe in self.cells:
            tid = ctypes.c_void_p()
            hr = dwmapi.DwmRegisterThumbnail(self._hwnd, hwnd, ctypes.byref(tid))
            self.thumbs.append(tid if hr == 0 and tid.value else None)

    def _place_thumbs(self):
        """把每个缩略图贴到对应单元格（物理像素），保持宽高比、居中留边。"""
        dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
        base_y = self.PAD - self.scroll
        cw, ch = self.THUMB_W - 4, self.THUMB_H - 4
        for i, tid in enumerate(self.thumbs):
            if not tid:
                continue
            col = i % self.cols
            row = i // self.cols
            x = self.PAD + col * (self.THUMB_W + self.GAP) + 2
            y = base_y + row * self._pitch + 2
            on_screen = (y + ch > 0) and (y < self.height())

            sz = wt.SIZE()
            sw = sh = 0
            if dwmapi.DwmQueryThumbnailSourceSize(tid, ctypes.byref(sz)) == 0:
                sw, sh = sz.cx, sz.cy

            src = wt.RECT(0, 0, 0, 0)
            use_src = False
            if sw > 0 and sh > 0 and Config.fit == "cover":
                cell_ar = float(cw) / ch
                src_ar = float(sw) / sh
                if src_ar > cell_ar:                 # 太宽 → 裁掉左右
                    nw = int(sh * cell_ar)
                    x0 = (sw - nw) // 2
                    src = wt.RECT(x0, 0, x0 + nw, sh)
                else:                                # 太高 → 裁掉上下
                    nh = int(sw / cell_ar)
                    y0 = (sh - nh) // 2
                    src = wt.RECT(0, y0, sw, y0 + nh)
                use_src = True
                dw, dh, dx, dy = cw, ch, x, y
            elif sw > 0 and sh > 0:                  # contain：留边不裁
                s = min(float(cw) / sw, float(ch) / sh)
                dw, dh = int(sw * s), int(sh * s)
                dx = x + (cw - dw) // 2
                dy = y + (ch - dh) // 2
            else:
                dw, dh, dx, dy = cw, ch, x, y

            p = DWM_THUMBNAIL_PROPERTIES()
            p.dwFlags = (DWM_TNP_RECTDESTINATION | DWM_TNP_VISIBLE | DWM_TNP_OPACITY
                         | DWM_TNP_SOURCECLIENTAREAONLY)
            if use_src:
                p.dwFlags |= DWM_TNP_RECTSOURCE
                p.rcSource = src
            p.rcDestination = wt.RECT(int(dx * dpr), int(dy * dpr),
                                      int((dx + dw) * dpr), int((dy + dh) * dpr))
            p.opacity = 255
            p.fVisible = 1 if on_screen else 0
            p.fSourceClientAreaOnly = 1
            _SET_PROPS(tid, ctypes.byref(p))

            if on_screen:
                self._dest_rects[i] = QRect(dx, dy, dw, dh)
            else:
                self._dest_rects.pop(i, None)

        self._sync_overlay()

    def _group_color(self, key):
        palette = ("#4f8cff", "#35c07e", "#f2994a", "#eb5757", "#9b51e0",
                   "#2d9cdb", "#f2c94c", "#56ccf2", "#bb6bd9", "#6fcf97")
        return QColor(palette[zlib.crc32(key.encode("utf-8")) % len(palette)])

    def _icon_for(self, exe):
        if not exe:
            return None
        key = exe.lower()
        if key in self._icon_cache:
            return self._icon_cache[key]
        pm = None
        try:
            icon = self._icon_provider.icon(QFileInfo(exe))
            if not icon.isNull():
                px = max(12, int(round(16 * self.S)))
                pm = icon.pixmap(px, px)
                if pm.isNull() or pm.width() < 4:
                    pm = None
        except Exception:
            pm = None
        self._icon_cache[key] = pm
        return pm

    def _sync_overlay(self):
        """把应用图标贴到缩略图右下角、关闭按钮贴到右上角（都画在独立覆盖窗上）。"""
        if self.overlay is None:
            return
        badges = []
        closes = []
        self._close_rects = {}
        icon_size = int(round(22 * self.S))
        logo_pad = int(round(5 * self.S))
        close_size = int(round(20 * self.S))
        close_pad = int(round(6 * self.S))
        for i, cell in enumerate(self.cells):
            r = self._dest_rects.get(i)
            if r is None or r.width() < 40 or r.height() < 30:
                continue
            if r.bottom() < 4 or r.top() > self.height() - 4:
                continue
            cr = QRect(r.right() - close_size - close_pad, r.top() + close_pad,
                       close_size, close_size)
            self._close_rects[i] = cr
            if i == self.hover_close:
                state = 2
            elif i == self.hover:
                state = 1
            else:
                state = 0
            closes.append((cr, state))
            if not Config.show_logo:
                continue
            pm = self._icon_for(cell[3])
            if pm is not None:
                badges.append((QRect(r.right() - icon_size - logo_pad,
                                     r.bottom() - icon_size - logo_pad,
                                     icon_size, icon_size), pm))
        self.overlay.set_badges(badges)
        self.overlay.set_closes(closes)

    def _anim_step(self):
        self._anim_left -= 1
        t = 1.0 - (float(self._anim_left) / self.ANIM_STEPS)
        ease = 1 - (1 - t) ** 3
        g = self._shot
        x = int(g.x() - g.width() * (1 - ease))
        self.move(x, g.y())
        if self._anim_left <= 0:
            self._anim_timer.stop()
            self.move(g.x(), g.y())
            self._place_thumbs()       # 动画结束后按最终尺寸重贴一次

    def resizeEvent(self, e):
        # 首次 show 时几何尺寸才真正生效，这里重贴可避免按旧高度算出的"不可见"
        QWidget.resizeEvent(self, e)
        # 被系统或 Qt 擅自改过尺寸（典型：跨 DPI 屏幕时 WM_DPICHANGED 缩放窗口）
        # 立刻恢复成自己算的尺寸，否则右下列会被切掉
        if self._shot.width() and (self.width() != self._shot.width()
                                   or self.height() != self._shot.height()):
            self._force_geometry()
            return
        if self.thumbs:
            self._place_thumbs()
        if self.overlay is not None and self.overlay.isVisible():
            self.overlay.setGeometry(self.geometry())

    def _force_geometry(self):
        """用物理像素强制回到 _shot 的矩形（绕过 Qt 的 DPI 换算）。"""
        if not self._hwnd or self._shot.width() <= 0:
            return
        g = self._shot
        u32.SetWindowPos(self._hwnd, None, g.x(), g.y(), g.width(), g.height(),
                         SWP_NOZORDER | SWP_NOACTIVATE)

    def nativeEvent(self, eventType, message):
        # 拦截 WM_DPICHANGED：我们自己按目标屏幕重算过尺寸了，
        # 不能让系统再按 DPI 比例把窗口缩放一遍（副屏 DPI 不同就会缩成 2/3）
        try:
            if eventType == b"windows_generic_MSG":
                msg = ctypes.cast(int(message), ctypes.POINTER(wt.MSG)).contents
                if msg.message == 0x02E0:          # WM_DPICHANGED
                    self._dpi_hits = getattr(self, "_dpi_hits", 0) + 1
                    self._force_geometry()
                    return True, 0
        except Exception:
            pass
        return False, 0

    def moveEvent(self, e):
        # 覆盖窗必须跟着面板走（含滑出动画的每一帧）
        if self.overlay is not None and self.overlay.isVisible():
            self.overlay.setGeometry(self.geometry())
        QWidget.moveEvent(self, e)

    def open(self):
        if self.isVisible():
            self.close_panel()
            return
        self._apply_noactivate()
        self.refresh()
        if not self.cells:
            return
        import time as _t
        self._entered = False
        self._opened_at = _t.time()
        # 滑入起点不能超出虚拟桌面左边界（副屏在左侧时坐标是负的，
        # 超出边界 Windows 会拒绝移动，导致面板停在错误位置、看着"显示不全"）
        vleft = u32.GetSystemMetrics(76)          # SM_XVIRTUALSCREEN
        start_x = self._shot.x() - self._shot.width()
        if start_x < vleft:
            start_x = vleft
            self._anim_left = 0                   # 没有滑入空间，直接显示
        else:
            self._anim_left = self.ANIM_STEPS
        self.move(start_x, self._shot.y())
        self.show()
        self.raise_()
        self._place_thumbs()
        if self.overlay is not None:
            self.overlay.setGeometry(self.geometry())
            self.overlay.show()
            self.overlay.raise_()
        if self._anim_left:
            self._anim_timer.start(10)

    def close_panel(self):
        import time as _t
        self._last_closed = _t.time()
        self._anim_timer.stop()
        if self.overlay is not None:
            self.overlay.hide()
            self.overlay.set_badges([])
        for t in self.thumbs:
            if t:
                dwmapi.DwmUnregisterThumbnail(t)
        self.thumbs = []
        self.hide()

    # ---------------- 命中与交互
    def _hit(self, px, py):
        base_y = self.PAD - self.scroll
        for i in range(len(self.cells)):
            col = i % self.cols
            row = i // self.cols
            x = self.PAD + col * (self.THUMB_W + self.GAP)
            y = base_y + row * self._pitch
            if x <= px < x + self.THUMB_W and y <= py < y + self._cell_h:
                return i
        return -1

    def mouseMoveEvent(self, e):
        hc = -1
        for i, r in self._close_rects.items():
            if r.adjusted(-4, -4, 4, 4).contains(e.x(), e.y()):
                hc = i
                break
        i = self._hit(e.x(), e.y())
        if hc != self.hover_close or i != self.hover:
            self.hover_close = hc
            self.hover = i
            self.update()
            self._sync_overlay()

    def leaveEvent(self, e):
        if self.hover != -1 or self.hover_close != -1:
            self.hover = -1
            self.hover_close = -1
            self.update()
            self._sync_overlay()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        # 先判右上角关闭按钮（只有该卡片处于悬停、按钮可见时才生效）
        for i, r in self._close_rects.items():
            if i == self.hover and r.adjusted(-4, -4, 4, 4).contains(e.x(), e.y()):
                self._close_window(i)
                return
        i = self._hit(e.x(), e.y())
        if i < 0:
            return
        hwnd = self.cells[i][0]
        self.close_panel()
        activate_window(hwnd)

    def _close_window(self, index):
        """给目标窗口发 WM_CLOSE（不是强杀，程序自己的保存提示会正常弹出）。"""
        if index < 0 or index >= len(self.cells):
            return
        hwnd = self.cells[index][0]
        u32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        self.hover_close = -1
        QTimer.singleShot(450, self._refresh_if_visible)

    def _refresh_if_visible(self):
        if not self.isVisible():
            return
        entered = self._entered
        self.refresh()
        self._entered = entered
        self._place_thumbs()
        if self.overlay is not None:
            self.overlay.setGeometry(self.geometry())
        self.update()

    def wheelEvent(self, e):
        step = self.THUMB_H + self.TITLE_H + self.GAP
        delta = -step if e.angleDelta().y() < 0 else step
        max_scroll = max(0, self._content_h - self.height())
        new = min(max(0, self.scroll + delta), max_scroll)
        if new != self.scroll:
            self.scroll = new
            self._place_thumbs()
            self.update()

    # ---------------- 绘制
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.fillRect(self.rect(), QColor("#1b1d21"))

        fm_main, fm_sub = self.fm_main, self.fm_sub
        base_y = self.PAD - self.scroll
        for i, cell in enumerate(self.cells):
            hwnd, main, sub = cell[0], cell[1], cell[2]
            col = i % self.cols
            row = i // self.cols
            x = self.PAD + col * (self.THUMB_W + self.GAP)
            y = base_y + row * self._pitch
            if y + self._cell_h < 0 or y > self.height():
                continue
            # 缩略图区域底色（缩略图会覆盖它）
            p.fillRect(QRect(x + 2, y + 2, self.THUMB_W - 4, self.THUMB_H - 4), QColor("#0e0f11"))
            # 标题区
            ty = y + self.THUMB_H + int(round(4 * self.S))
            p.setPen(QColor("#e8eaed"))
            p.setFont(self.f_main)
            p.drawText(QRect(x + 2, ty, self.THUMB_W - 4, self._h_main), Qt.AlignLeft | Qt.AlignTop,
                       fm_main.elidedText(main, Qt.ElideRight, self.THUMB_W - 6))
            if sub:
                p.setPen(QColor("#8b9096"))
                p.setFont(self.f_sub)
                p.drawText(QRect(x + 2, ty + self._h_main, self.THUMB_W - 4, self._h_sub),
                           Qt.AlignLeft | Qt.AlignTop,
                           fm_sub.elidedText(sub, Qt.ElideRight, self.THUMB_W - 6))
            # hover 描边（画在缩略图外侧 2px，避免被 DWM 缩略图盖住）
            # 鼠标停在关闭按钮上时不画，避免和按钮抢视觉
            if i == self.hover and i != self.hover_close:
                pen = QPen(QColor("#3b82f6"))
                pen.setWidth(2)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawRect(QRect(x, y, self.THUMB_W - 1, self._cell_h - 1))

        # 滚动条
        max_scroll = max(0, self._content_h - self.height())
        if max_scroll > 0:
            track_h = self.height() - 2 * self.PAD
            bar_h = max(30, int(track_h * (self.height() - 2 * self.PAD) / float(self._content_h)))
            bar_y = self.PAD + int((track_h - bar_h) * (self.scroll / float(max_scroll)))
            p.fillRect(QRect(self.width() - 6, bar_y, 3, bar_h), QColor("#4a4f57"))


# ------------------------------------------------------------------ 热键线程
class HotkeySignals(QObject):
    fired = pyqtSignal()


class HotkeyThread(threading.Thread):
    def __init__(self, sig):
        threading.Thread.__init__(self)
        self.daemon = True
        self.sig = sig
        self.ok = False

    def run(self):
        if not u32.RegisterHotKey(None, 0xB001, MOD_ALT, VK_OEM_3):
            return
        self.ok = True
        msg = wt.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY:
                self.sig.fired.emit()
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))


# ------------------------------------------------------------------ 主程序
class App(object):
    def __init__(self, argv):
        self.qapp = QApplication(argv)
        self.drawer = Drawer()
        self.signals = HotkeySignals()
        self.signals.fired.connect(self.drawer.open)

        if Config.hotkey:
            self.hk = HotkeyThread(self.signals)
            self.hk.start()

        # 鼠标移出面板 350ms 后收起
        self._outside_since = 0.0
        self._tick = QTimer()
        self._tick.timeout.connect(self._poll)
        self._tick.start(80)

        self._edge_ticks = 0
        self.tray = None
        self._init_tray()

        # 任何位置的鼠标点击都通知一次：鼠标没进过面板就点别处 → 直接收起
        self.clicker = ClickWatcher()
        self.clicker.clicked.connect(self._on_click)

        # Alt+Tab 拦截（可选）
        self.alt_tab = None
        if Config.intercept_alt_tab:
            self.alt_tab = AltTabWatcher()
            if not self.alt_tab.ok:
                print("Alt+Tab 钩子安装失败（可能被安全软件拦截）")
            self.alt_tab.triggered.connect(self._on_alt_tab)

    def _on_alt_tab(self):
        """在钩子回调里只排个定时器，不要在钩子里直接建窗口。"""
        if self.drawer.isVisible():
            return
        QTimer.singleShot(0, self.drawer.open)

    def _on_click(self, x, y):
        d = self.drawer
        if not d.isVisible():
            return
        g = d.geometry()
        if g.x() <= x <= g.x() + g.width() and g.y() <= y <= g.y() + g.height():
            d._entered = True
            return
        d.close_panel()

    def _make_icon(self):
        pm = QPixmap(64, 64)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#3b82f6"))
        p.drawRoundedRect(4, 10, 56, 44, 9, 9)
        p.setBrush(QColor("#ffffff"))
        for i in range(2):
            for j in range(2):
                p.drawRoundedRect(12 + i * 21, 19 + j * 16, 17, 11, 2, 2)
        p.end()
        return QIcon(pm)

    def _init_tray(self):
        self.tray = QSystemTrayIcon(self._make_icon(), self.qapp)
        self.tray.setToolTip("WinTab Lite" + ("　Alt+` 唤出" if Config.hotkey else ""))
        menu = QMenu()
        menu.addAction("唤出面板", self.drawer.open)
        self.act_autostart = menu.addAction("开机自启")
        self.act_autostart.setCheckable(True)
        self.act_autostart.setChecked(self._autostart_on())
        self.act_autostart.triggered.connect(self._toggle_autostart)
        if _autostart is None:
            self.act_autostart.setEnabled(False)
            self.act_autostart.setText("开机自启（缺少 autostart.py）")
        menu.aboutToShow.connect(self._sync_autostart)
        menu.addSeparator()
        menu.addAction("退出", self.qapp.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray)
        self.tray.show()

    def _autostart_on(self):
        if _autostart is None:
            return False
        try:
            return os.path.exists(_autostart.link_path())
        except Exception:
            return False

    def _sync_autostart(self):
        self.act_autostart.setChecked(self._autostart_on())

    def _toggle_autostart(self, checked):
        if _autostart is None:
            return
        try:
            if checked:
                _autostart.make_shortcut()
            else:
                p = _autostart.link_path()
                if os.path.exists(p):
                    os.remove(p)
        except Exception as ex:
            print("切换开机自启失败:", ex)
        self._sync_autostart()

    def _on_tray(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.drawer.open()

    def _poll(self):
        import time
        x, y = cursor_pos()
        if self.drawer.isVisible():
            if self.drawer.no_autohide:
                return
            g = self.drawer.geometry()
            inside = (g.x() - 6 <= x <= g.x() + g.width() + 6 and
                      g.y() - 6 <= y <= g.y() + g.height() + 6)
            if inside:
                self.drawer._entered = True
                self._outside_since = 0.0
                return
            if not self.drawer._entered:
                # 宽限期：唤出后鼠标还没进来过，就一直驻留，绝不自动收
                self._outside_since = 0.0
                return
            if time.time() - self.drawer._opened_at < 0.25:
                return
            if self._outside_since == 0.0:
                self._outside_since = time.time()
            elif time.time() - self._outside_since > 0.35:
                self._outside_since = 0.0
                self.drawer.close_panel()
        elif Config.edge_dwell:
            if time.time() - self.drawer._last_closed < 1.2:   # 刚收起，别立刻又被边缘触发
                self._edge_ticks = 0
                return
            mon, _ = self.drawer._target_monitor()
            if x <= mon.left + Config.edge_px:
                self._edge_ticks += 1
                if self._edge_ticks >= 4:      # ~320ms 驻留
                    self._edge_ticks = 0
                    self.drawer.open()
            else:
                self._edge_ticks = 0

    def run(self):
        # 预热：先创建 HWND，避免首次唤出卡顿
        self.drawer._apply_noactivate()
        return self.qapp.exec_()


def main():
    # PyInstaller 打包后 __file__ 在临时解包目录里，配置要跟着 exe 走
    if getattr(sys, "frozen", False):
        here = os.path.dirname(os.path.abspath(sys.executable))
    else:
        here = os.path.dirname(os.path.abspath(__file__))

    # PyQt5 默认会在槽函数抛异常时直接 abort 进程，改成只记录日志。
    def _hook(tp, val, tb):
        import traceback
        traceback.print_exception(tp, val, tb)
    sys.excepthook = _hook

    # 单实例：已有实例在跑就直接退出（自测模式跳过，方便与常驻实例共存）
    if not ("--shot" in sys.argv or "--show" in sys.argv):
        k32.CreateMutexW(None, False, "WinTabLite_SingleInstance_v1")
        if k32.GetLastError() == 183:      # ERROR_ALREADY_EXISTS
            return 0

    Config.load(os.path.join(here, "config.ini"))
    app = App(sys.argv)

    if "--shot" in sys.argv:                       # 自测：唤出 → 截图 → 退出
        i = sys.argv.index("--shot")
        out = sys.argv[i + 1] if i + 1 < len(sys.argv) else "shot.png"
        app.drawer.no_autohide = True
        QTimer.singleShot(600, app.drawer.open)

        def _grab():
            from PIL import ImageGrab
            d = app.drawer
            d._place_thumbs()
            app.qapp.processEvents()
            dpr = d.devicePixelRatioF() if hasattr(d, "devicePixelRatioF") else 1.0
            g = app.drawer.geometry()
            box = (int(g.x() * dpr), int(g.y() * dpr),
                   int((g.x() + g.width()) * dpr), int((g.y() + g.height()) * dpr))
            img = ImageGrab.grab(bbox=box, all_screens=True)
            img.save(out)
            print("saved %s %s dpr=%.2f geom=%s" % (out, img.size, dpr, g))
            app.qapp.quit()

        QTimer.singleShot(1600, _grab)
    elif "--show" in sys.argv:
        app.drawer.no_autohide = True
        QTimer.singleShot(600, app.drawer.open)

    return app.run()


if __name__ == "__main__":
    sys.exit(main())
