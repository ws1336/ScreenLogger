import os
import sys

import PyInstaller.__main__

""" 打包脚本，使用 PyInstaller 将 Python 代码打包为可执行文件 """

filename = "main.py"
app_name = "ScreenLogger"
icon_png = "assets/icon.png"
copy_dirs = ["conf"]

if sys.platform == "darwin":
    args = [
        "--name={}".format(app_name),
        "--onedir",
        "--noconfirm",
        "--clean",
        "--icon={}".format(icon_png),
        filename,
    ]
elif sys.platform == "win32":
    args = [
        "--name={}".format(app_name),
        "--noconsole",
        "--onedir",
        "--noconfirm",
        "--clean",
        "--icon={}".format(icon_png),
        filename,
    ]
else:
    args = [
        "--name={}".format(app_name),
        "--onedir",
        "--noconfirm",
        "--clean",
        filename,
    ]

for copy_dir in copy_dirs:
    if copy_dir and os.path.exists(copy_dir):
        sep = ";" if sys.platform == "win32" else ":"
        args.append("--add-data={}{}{}".format(copy_dir, sep, copy_dir))


def build_app():
    print(f"开始打包 {app_name} ...")
    PyInstaller.__main__.run(args)
    print(f"打包 {app_name} 完成！")
    if sys.platform == "win32":
        output_dir = f"dist\\{app_name}\\"
        exe_path = f"dist\\{app_name}\\{app_name}.exe"
        print(f"输出目录: {output_dir}")
        print(f"可执行文件: {exe_path}")
    elif sys.platform == "darwin":
        print(f"输出目录: dist/{app_name}/")
        print(f"可执行文件: dist/{app_name}/{app_name}.app")

def remove_private_info():
    """移除隐私信息"""
    if sys.platform == "win32":
        ini_path = f"dist\\{app_name}\\_internal\\conf\\settings.ini"
    else:
        ini_path = f"dist/{app_name}/_internal/conf/settings.ini"
    if os.path.exists(ini_path):
        os.remove(ini_path)
        print(f"已删除 {ini_path}")
    else:
        print(f"{ini_path} 不存在")


if __name__ == "__main__":
    build_app()
    remove_private_info()