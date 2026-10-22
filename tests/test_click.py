# -*- coding: utf-8 -*-
import os
import sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

"""端到端验证：鼠标点击能不能让面板收起。
1) 唤出             -> 应该可见
2) 点面板内部空白处  -> 仍可见（视为"已进入"）
3) 点面板外部        -> 应该立刻收起
"""
import ctypes
import sys
import time

from PyQt5.QtCore import QTimer

import wintab_lite as W

W.Config.load(os.path.join(_ROOT, "config.ini"))
app = W.App(sys.argv)
app.drawer.no_autohide = True       # 排除 0.35s 自动收起，专测点击

u = ctypes.windll.user32
orig = (ctypes.c_long(0), ctypes.c_long(0))
pt = W.wt.POINT()
u.GetCursorPos(ctypes.byref(pt))
orig = (pt.x, pt.y)


def click_at(x, y):
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    u.mouse_event(0x0002, 0, 0, 0, 0)   # LEFTDOWN
    time.sleep(0.02)
    u.mouse_event(0x0004, 0, 0, 0, 0)   # LEFTUP
    time.sleep(0.15)


QTimer.singleShot(400, app.drawer.open)


def step_in():
    d = app.drawer
    g = d.geometry()
    print("1) opened =", d.isVisible(), " geom=", g.x(), g.y(), g.width(), g.height())
    click_at(g.x() + 5, g.y() + 5)              # 面板内边距空白处
    print("2) after inside click: visible =", d.isVisible(), " entered =", d._entered)


def step_out():
    d = app.drawer
    g = d.geometry()
    click_at(g.x() + g.width() + 400, g.y() + 10)   # 面板外侧
    print("3) after outside click: visible =", d.isVisible(), " (期望 False)")


def done():
    u.SetCursorPos(orig[0], orig[1])
    if app.drawer.isVisible():
        app.drawer.close_panel()
    app.qapp.quit()


QTimer.singleShot(1000, step_in)
QTimer.singleShot(1700, step_out)
QTimer.singleShot(2300, done)

sys.exit(app.run())
