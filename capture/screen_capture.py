"""
屏幕截图模块
使用 Pillow 和 PySide6 实现定时屏幕截图功能。
支持暂停/恢复以保护隐私，自动记录活动窗口标题。
"""
import os
import sys
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal
from qfluentwidgets import MessageBox
from PIL import ImageGrab

from config import Settings
from database import DatabaseManager
from logger import log_manager

try:
    import pygetwindow as gw
    _HAS_GW = True
except ImportError:
    _HAS_GW = False


class ScreenCapture(QObject):
    """
    屏幕截图管理类
    使用 QTimer 定时触发截图，支持暂停/恢复。
    """

    # 截图成功信号：文件路径、时间戳、窗口标题
    screenshot_taken = Signal(str, str, str)
    # 截图失败信号：错误信息
    capture_error = Signal(str)

    def __init__(self, config_manager: Settings, db_manager: DatabaseManager):
        """
        初始化屏幕截图管理器

        Args:
            config_manager: 配置管理实例
            db_manager: 数据库管理实例
        """
        super().__init__()
        self._config = config_manager
        self._db = db_manager
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._capture_screenshot)
        self._is_paused = False
        self._screenshot_dir = ""

    def start(self):
        """启动定时截图"""
        interval_seconds = self._config.get("screenshot_settings/screenshot_interval", 1)
        if interval_seconds <= 0:
            log_manager.warning("截图间隔配置无效，使用默认值 1 秒")
            interval_seconds = 1

        interval_ms = interval_seconds * 1000
        self._screenshot_dir = self._config.get_screenshot_path()

        self._timer.start(interval_ms)
        log_manager.info(f"屏幕截图已启动，间隔: {interval_seconds}秒，目录: {self._screenshot_dir}")

    def stop(self):
        """停止定时截图"""
        self._timer.stop()
        log_manager.info("屏幕截图已停止")

    def pause(self):
        """暂停截图（用于隐私保护）"""
        self._is_paused = True
        log_manager.info("屏幕截图已暂停")

    def resume(self):
        """恢复截图"""
        self._is_paused = False
        log_manager.info("屏幕截图已恢复")

    @property
    def is_recording(self) -> bool:
        """返回是否正在录制"""
        return self._timer.isActive()

    def _capture_screenshot(self):
        """
        核心截图逻辑
        使用 PIL.ImageGrab 截取屏幕，保存为 JPG 文件，
        同时记录当前活动窗口标题并写入数据库。
        """
        if self._is_paused:
            return

        try:
            img = ImageGrab.grab()
        except Exception as e:
            error_msg = f"截图失败: {str(e)}"
            log_manager.error(error_msg)
            if sys.platform == "darwin":
                log_manager.error("macOS 需要授予屏幕录制权限: 系统设置 → 隐私与安全性 → 屏幕录制 → 允许终端/Python")
                MessageBox("请在系统设置中授予屏幕录制权限", "系统设置 → 隐私与安全性 → 屏幕录制 → 允许终端/Python")     
            self.capture_error.emit(error_msg)
            return

        now = datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.jpg"
        filepath = os.path.join(self._screenshot_dir, filename)

        try:
            quality = self._config.get("screenshot_settings/screenshot_quality", 95)
            img.save(filepath, "JPEG", quality=quality)
        except Exception as e:
            error_msg = f"保存截图文件失败: {filepath}, 错误: {str(e)}"
            log_manager.error(error_msg)
            self.capture_error.emit(error_msg)
            return

        window_title = self._get_active_window_title()

        try:
            self._db.add_screenshot(filepath, now, window_title)
        except Exception as e:
            log_manager.error(f"写入截图数据库记录失败: {str(e)}")

        self.screenshot_taken.emit(filepath, now.isoformat(), window_title)
    
    def _get_active_window_title(self) -> str:
        """
        获取当前活动窗口标题
        优先使用 pygetwindow 库，支持Windows、macOS平台获取活动窗口标题
        """
        if not _HAS_GW:
            return "Unknown"
        try:
            active_window = gw.getActiveWindow()
            if active_window:
                return active_window.title
            else:
                return "Unknown"
        except Exception as e:
            log_manager.error(f"获取活动窗口标题失败: {str(e)}")
            return "Unknown"