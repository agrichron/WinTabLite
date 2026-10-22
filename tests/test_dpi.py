# -*- coding: utf-8 -*-
import os
import sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

"""跨屏 DPI 验证：先在主屏显示（144dpi），再挪到副屏（96dpi），
检查窗口有没有被 WM_DPICHANGED 按 2/3 缩小。"""
import ctypes
import sys
import time
from ctypes import wintypes as wt

from PyQt5.QtCore import QTimer

import wintab_lite as W

W.Config.load(os.path.join(_ROOT, "config.ini"))
app = W.App(sys.argv)
d = app.drawer
d.no_autohide = True

u = ctypes.windll.user32
orig = wt.POINT()
u.GetCursorPos(ctypes.byref(orig))


def on_primary():
    u.SetCursorPos(2500, 800)          # 主屏
    time.sleep(0.2)
    d.open()


def check_primary():
    print("主屏: geom=%s dpi_hits=%s" % ((d.x(), d.y(), d.width(), d.height()),
                                        getattr(d, "_dpi_hits", 0)))
    d.close_panel()
    QTimer.singleShot(300, on_secondary)


def on_secondary():
    u.SetCursorPos(-900, 1000)         # 副屏
    time.sleep(0.2)
    d.open()


def check_secondary():
    w, h = d.width(), d.height()
    dpi_hits = getattr(d, "_dpi_hits", 0)
    print("副屏: geom=%s dpi_hits=%s" % ((d.x(), d.y(), w, h), dpi_hits))
    print("判定: 宽度=%d  期望=%d  %s" % (w, d._shot.width(),
                                         "OK 未被缩放" if w == d._shot.width() else "FAIL 被缩放"))
    u.SetCursorPos(orig.x, orig.y)
    d.close_panel()
    app.qapp.quit()


QTimer.singleShot(400, on_primary)
QTimer.singleShot(1100, check_primary)
QTimer.singleShot(2600, check_secondary)

sys.exit(app.run())
