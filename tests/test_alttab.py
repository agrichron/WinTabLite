# -*- coding: utf-8 -*-
import os
import sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

"""验证 Alt+Tab 拦截：安装键盘钩子后发送 Alt+Tab，看是否被吞掉并触发回调。"""
import ctypes
import sys
import time

from PyQt5.QtCore import QTimer

import wintab_lite as W

W.Config.load(os.path.join(_ROOT, "config.ini"))
app = W.App(sys.argv)

hits = []
watcher = W.AltTabWatcher()
print("钩子安装:", watcher.ok)
watcher.triggered.connect(lambda: hits.append(1))

u = ctypes.windll.user32


def send_alt_tab():
    u.keybd_event(0x12, 0, 0, 0)          # Alt down
    time.sleep(0.05)
    u.keybd_event(0x09, 0, 0, 0)          # Tab down
    time.sleep(0.05)
    u.keybd_event(0x09, 0, 2, 0)          # Tab up
    time.sleep(0.05)
    u.keybd_event(0x12, 0, 2, 0)          # Alt up
    time.sleep(0.2)


QTimer.singleShot(400, send_alt_tab)


def check():
    print("触发了", len(hits), "次  ->", "OK 拦截成功" if hits else "FAIL 未捕获")
    app.qapp.quit()


QTimer.singleShot(1200, check)
sys.exit(app.run())
