# -*- coding: utf-8 -*-
import os
import sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

"""验证"唤出后驻留"：唤出后鼠标不在面板上，1.2 秒后应仍然可见。"""
import sys
from PyQt5.QtCore import QTimer

import wintab_lite as W

W.Config.load(os.path.join(_ROOT, "config.ini"))
app = W.App(sys.argv)
app.drawer.no_autohide = False        # 走真实的自动收起逻辑

QTimer.singleShot(300, app.drawer.open)


def check():
    vis = app.drawer.isVisible()
    print("RESIDENT_OK" if vis else "RESIDENT_FAIL", "visible=", vis,
          "entered=", app.drawer._entered)
    app.drawer.close_panel()
    app.qapp.quit()


QTimer.singleShot(1500, check)
sys.exit(app.run())
