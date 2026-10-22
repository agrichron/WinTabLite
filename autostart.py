# -*- coding: utf-8 -*-
"""开机自启管理（写入当前用户的「启动」文件夹，不需要管理员权限）。

用法：
    python autostart.py            查看状态
    python autostart.py --install  设置开机自启
    python autostart.py --remove   取消开机自启
"""
import os
import sys

HERE = (os.path.dirname(os.path.abspath(sys.executable))
        if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(HERE, "wintab_lite.py")
FROZEN = getattr(sys, "frozen", False)
NAME = "WinTabLite.lnk"


def pythonw():
    exe = sys.executable
    cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return cand if os.path.exists(cand) else exe


def startup_dir():
    return os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs\Startup")


def link_path():
    return os.path.join(startup_dir(), NAME)


def make_shortcut():
    from win32com.client import Dispatch
    shell = Dispatch("WScript.Shell")
    lnk = shell.CreateShortCut(link_path())
    if FROZEN:                                  # 打包后直接指向 exe 本身
        lnk.Targetpath = sys.executable
        lnk.Arguments = ""
        lnk.IconLocation = sys.executable
    else:
        lnk.Targetpath = pythonw()
        lnk.Arguments = '"%s"' % SCRIPT
        lnk.IconLocation = pythonw()
    lnk.WorkingDirectory = HERE
    lnk.Description = "WinTab Lite - 左侧窗口缩略图抽屉"
    lnk.save()


def status():
    p = link_path()
    if not os.path.exists(p):
        print("未设置开机自启")
        return
    from win32com.client import Dispatch
    lnk = Dispatch("WScript.Shell").CreateShortCut(p)
    print("已设置开机自启")
    print("  快捷方式:", p)
    print("  目标    :", lnk.Targetpath)
    print("  参数    :", lnk.Arguments)


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--install":
        if not os.path.exists(SCRIPT):
            print("找不到主程序:", SCRIPT)
            return 1
        make_shortcut()
        print("已写入启动文件夹:", link_path())
        status()
    elif arg == "--remove":
        p = link_path()
        if os.path.exists(p):
            os.remove(p)
            print("已取消开机自启:", p)
        else:
            print("本来就没有设置")
    else:
        status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
