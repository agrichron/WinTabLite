# -*- coding: utf-8 -*-
import os
import sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

"""验证：原生子窗口能否叠在 DWM 缩略图之上（决定 logo 叠角的实现方式）。"""
import ctypes
import sys
import time

from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QApplication, QWidget, QLabel

import wintab_lite as W

W.Config.load(os.path.join(_ROOT, "config.ini"))

app = QApplication(sys.argv)


class Panel(QWidget):
    def __init__(self):
        QWidget.__init__(self)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                            | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setGeometry(60, 60, 260, 170)
        self.setStyleSheet("background:#1b1d21;")
        self.badge = None

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#1b1d21"))


panel = Panel()
panel.show()
app.processEvents()
time.sleep(0.1)

# 取一个源窗口贴缩略图
wins = W.enum_windows()
src = wins[0]
tid = ctypes.c_void_p()
hr = W.dwmapi.DwmRegisterThumbnail(int(panel.winId()), src, ctypes.byref(tid))
print("register hr=", hr)

p = W.DWM_THUMBNAIL_PROPERTIES()
p.dwFlags = (W.DWM_TNP_RECTDESTINATION | W.DWM_TNP_VISIBLE | W.DWM_TNP_OPACITY
             | W.DWM_TNP_SOURCECLIENTAREAONLY)
p.rcDestination = W.wt.RECT(10, 10, 250, 145)
p.opacity = 255
p.fVisible = 1
p.fSourceClientAreaOnly = 1
W._SET_PROPS(tid, ctypes.byref(p))

# 关键验证：原生子窗口，压在缩略图右下角
badge = QLabel(panel)
badge.setAttribute(Qt.WA_NativeWindow, True)      # 强制独立 HWND
badge.setGeometry(210, 105, 34, 34)
badge.setStyleSheet("background:#ff2d55;border:0px;")
badge.setText("")
badge.show()
badge.raise_()

# 方案 B：独立顶层半透明覆盖窗
class Overlay(QWidget):
    def __init__(self, geo):
        QWidget.__init__(self)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                            | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setGeometry(geo)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(QRect(210, 105, 34, 34), QColor("#00c853"))


ov = Overlay(panel.geometry())
ov.show()
ov.raise_()

for _ in range(10):
    app.processEvents()
    time.sleep(0.04)

from PIL import ImageGrab
g = panel.geometry()
img = ImageGrab.grab(bbox=(g.x(), g.y(), g.x() + g.width(), g.y() + g.height()),
                     all_screens=True)
img.save("overlay_test.png")
# 取角标中心像素
print("子窗口像素 =", img.getpixel((225, 120)), "（期望红 255,45,85）")
print("覆盖窗像素 =", img.getpixel((250, 115)), "（期望绿 0,200,83）")

badge.hide()
W.dwmapi.DwmUnregisterThumbnail(tid)
panel.close()
