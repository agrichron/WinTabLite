# -*- coding: utf-8 -*-
"""把开机自启的快捷方式改指向打包后的 exe。"""
import os
import sys

from win32com.client import Dispatch

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(HERE, "dist", "WinTabLite.exe")
LNK = os.path.join(os.environ["APPDATA"],
                   r"Microsoft\Windows\Start Menu\Programs\Startup\WinTabLite.lnk")

if not os.path.exists(EXE):
    print("找不到 exe:", EXE)
    sys.exit(1)

shell = Dispatch("WScript.Shell")
lnk = shell.CreateShortCut(LNK)
lnk.Targetpath = EXE
lnk.Arguments = ""
lnk.WorkingDirectory = os.path.dirname(EXE)
lnk.IconLocation = EXE
lnk.Description = "WinTab Lite - 左侧窗口缩略图抽屉"
lnk.save()

chk = shell.CreateShortCut(LNK)
print("快捷方式:", LNK)
print("  目标:", chk.Targetpath)
print("  参数:", repr(chk.Arguments))
print("  图标:", chk.IconLocation)
print("  目标存在:", os.path.exists(chk.Targetpath))
