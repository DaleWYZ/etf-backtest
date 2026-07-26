"""PyInstaller 打包脚本 — 将程序打包为单个 EXE 文件

使用方法:
    python build_exe.py

或直接在命令行:
    pyinstaller --onefile --windowed --name "ETF回测工具" --add-data "static;static" main.py
"""

import os
import sys
import subprocess


def build():
    """执行 PyInstaller 打包"""
    print("=" * 60)
    print("  ETF 定投回测工具 — 打包 EXE")
    print("=" * 60)

    # 确定分隔符 (Windows 用 ;)
    sep = ";"

    # 静态文件路径
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

    if not os.path.exists(static_dir):
        print(f"[错误] 找不到 static 目录: {static_dir}")
        sys.exit(1)

    # PyInstaller 参数
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "ETF回测工具",
        "--add-data", f"static{sep}static",
        "--clean",
        "--noconfirm",
        "main.py",
    ]

    print(f"\n执行命令:")
    print("  " + " ".join(cmd))
    print()

    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))

    if result.returncode == 0:
        exe_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "dist",
            "ETF回测工具.exe",
        )
        print(f"\n✅ 打包成功!")
        print(f"   EXE 位置: {exe_path}")
    else:
        print(f"\n❌ 打包失败，返回码: {result.returncode}")
        sys.exit(result.returncode)


if __name__ == "__main__":
    build()
