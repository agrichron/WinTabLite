# -*- coding: utf-8 -*-
import os
import sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

"""验证关闭按钮：
1) 点右上角按钮能正确命中对应格子（拦截真实关闭，只检查路由）
2) WM_CLOSE 能真的关掉一个窗口（用一个临时 tkinter 窗口做靶子）
"""
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes as wt

from PyQt5.QtCore import QTimer

import wintab_lite as W

TITLE = "CLOSE_TEST_TARGET"

W.Config.load(os.path.join(_ROOT, "config.ini"))
app = W.App(sys.argv)
d = app.drawer
d.no_autohide = True

u = ctypes.windll.user32
u.FindWindowW.restype = wt.HWND
u.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]

pt = wt.POINT()
u.GetCursorPos(ctypes.byref(pt))
orig = (pt.x, pt.y)

hits = []
_real_close = d._close_window


def fake_close(index):
    hits.append(index)
    print("命中关闭按钮 -> 格子 index =", index, " 标题 =", d.cells[index][1][:30])


d._close_window = fake_close


def click_at(x, y):
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    u.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.02)
    u.mouse_event(0x0004, 0, 0, 0, 0)


# ---------- 第 1 部分：点击路由 ----------
def step_open():
    u.SetCursorPos(1500, 800)
    time.sleep(0.15)
    d.open()


def step_click():
    if not d.isVisible():
        print("面板未显示，重开")
        d.open()
        time.sleep(0.3)
    if not d.cells:
        print("没有窗口可测")
        return
    r = d._close_rects.get(0)
    g = d.geometry()
    sx = g.x() + r.center().x()          # 面板局部 -> 屏幕绝对坐标
    sy = g.y() + r.center().y()
    print("格子0 =", d.cells[0][1][:30])
    print("关闭按钮 rect(局部) =", r.x(), r.y(), r.width(), r.height(), " -> 屏幕坐标", sx, sy)
    click_at(sx, sy)
    time.sleep(0.25)
    print("点击后: hits =", hits, " 面板是否仍可见 =", d.isVisible())


# ---------- 第 2 部分：WM_CLOSE 真的能关 ----------
def spawn_target():
    code = ("import tkinter as tk\n"
            "r=tk.Tk()\n"
            "r.title('%s')\n"
            "r.geometry('420x240+300+300')\n"
            "r.mainloop()\n" % TITLE)
    return subprocess.Popen([sys.executable, "-c", code])


def step_wmclose():
    proc = spawn_target()
    time.sleep(1.2)
    hwnd = u.FindWindowW(None, TITLE)
    print("靶子窗口 hwnd =", hwnd)
    if hwnd:
        u.PostMessageW(hwnd, W.WM_CLOSE, 0, 0)
        try:
            code = proc.wait(timeout=3)
            print("WM_CLOSE 后进程退出码 =", code, " -> 关闭成功")
        except subprocess.TimeoutExpired:
            print("WM_CLOSE 未生效（超时）")
            proc.kill()


def done():
    u.SetCursorPos(orig[0], orig[1])
    if d.isVisible():
        d.close_panel()
    d._close_window = _real_close
    app.qapp.quit()


QTimer.singleShot(400, step_open)
QTimer.singleShot(1100, step_click)
QTimer.singleShot(1600, step_wmclose)
QTimer.singleShot(4200, done)

sys.exit(app.run())
