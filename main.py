"""
ScreenLogger 应用入口文件
桌面屏幕录制与活动分析工具
"""
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from qfluentwidgets import setTheme, Theme
from logger import log_manager
from ui.main_window import MainWindow
import assets


def main():
    """应用主入口函数"""
    # 启用高DPI支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("ScreenLogger")
    app.setOrganizationName("ScreenLogger")
    app.setWindowIcon(QIcon(":/icon.png"))

    # 设置Fluent主题
    setTheme(Theme.AUTO)

    log_manager.info("ScreenLogger 启动")

    window = MainWindow()
    window.show()

    exit_code = app.exec()
    log_manager.info("ScreenLogger 退出")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()