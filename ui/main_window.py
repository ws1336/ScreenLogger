"""
主窗口 - ScreenLogger 应用的主界面，管理所有子页面和模块
"""
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from qfluentwidgets import (
    FluentWindow, FluentIcon, NavigationItemPosition,
    InfoBar, InfoBarPosition, SplashScreen
)
from config import Settings
from logger import log_manager


class MainWindow(FluentWindow):
    """ScreenLogger 主窗口，继承 FluentWindow 实现导航式界面"""

    def __init__(self):
        super().__init__()
        self._config = Settings()
        self._reconfigure_log_path()
        self._init_window()
        self._init_tray()
        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(self.size())
        self.show()
        QApplication.processEvents()

        self._init_modules()
        self._init_pages()
        self.splashScreen.finish()
        log_manager.info("主窗口初始化完成")

    def _reconfigure_log_path(self):
        """使用配置的数据根目录重新设置日志输出路径"""
        log_manager.reconfigure(self._config.get_log_dir())

    def _init_modules(self):
        """初始化所有子模块"""
        from database import DatabaseManager
        from capture import ScreenCapture
        from ai import AIAnalyzer
        from storage import StorageManager

        self.db_manager = DatabaseManager(self._config.get_db_path())

        # 初始化数据库
        try:
            self.db_manager.init_db()
            log_manager.info("数据库初始化完成")
        except Exception as e:
            log_manager.error(f"数据库初始化失败: {e}")

        self.screen_capture = ScreenCapture(self._config, self.db_manager)
        self.ai_analyzer = AIAnalyzer(self._config, self.db_manager)
        self.storage_manager = StorageManager(self._config, self.db_manager)

        self._init_preset_tags()

        # 连接存储管理器信号
        self.storage_manager.cleanup_complete.connect(self._on_cleanup_complete)
        self.storage_manager.migration_complete.connect(self._on_migration_complete)
        self.storage_manager.storage_error.connect(self._on_storage_error)

        # 连接AI分析完成信号
        self.ai_analyzer.analysis_complete.connect(self._on_ai_analysis_complete)

    def _init_window(self):
        """初始化窗口基本属性"""
        self.setWindowIcon(self.windowIcon())
        self.setWindowTitle("ScreenLogger - 屏幕记录与活动分析")
        self.resize(1200, 800)

        # 设置窗口最小尺寸
        self.setMinimumSize(900, 600)
        
        # 设置窗口位置屏幕居中（在 show() 之后会生效）
        # 使用 QTimer 延迟执行，确保窗口已完全初始化
        QTimer.singleShot(0, self._center_window)

    def _center_window(self):
        """居中显示窗口"""
        screen_geometry = self.screen().geometry()
        window_geometry = self.frameGeometry()
        
        # 计算居中位置
        center_point = screen_geometry.center()
        window_geometry.moveCenter(center_point)
        
        self.move(window_geometry.topLeft())

    def _init_tray(self):
        """初始化系统托盘"""
        self._tray_icon = QSystemTrayIcon(self.windowIcon(), self)
        self._tray_icon.setToolTip("ScreenLogger - 屏幕记录与活动分析")

        self._tray_menu = QMenu(self)
        restore_action = QAction("还原", self)
        restore_action.triggered.connect(self.showNormal)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self._quit_app)
        self._tray_menu.addAction(restore_action)
        self._tray_menu.addAction(quit_action)
        self._tray_icon.setContextMenu(self._tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)

    def _init_pages(self):
        """初始化所有子页面并注册到导航"""
        from ui.recording_page import RecordingPage
        from ui.timeline_page import TimelinePage
        from ui.log_viewer_page import LogViewerPage
        from ui.classifier_page import ClassifierPage
        from ui.settings_page import SettingsPage
        from ui.alarm_page import AlarmPage
        # 创建子页面实例，传入 main_window 引用
        self.recording_page = RecordingPage(main_window=self)
        self.recording_page.setObjectName("recordingInterface")
        self.timeline_page = TimelinePage(main_window=self)
        self.timeline_page.setObjectName("timelineInterface")
        self.log_viewer_page = LogViewerPage(main_window=self)
        self.log_viewer_page.setObjectName("logViewerInterface")
        self.classifier_page = ClassifierPage(main_window=self)
        self.classifier_page.setObjectName("classifierInterface")
        self.settings_page = SettingsPage(main_window=self)
        self.settings_page.setObjectName("settingsInterface")
        self.alarm_page = AlarmPage(main_window=self)
        self.alarm_page.setObjectName("alarmInterface")

        # 注册导航页面
        self.addSubInterface(
            self.recording_page,
            FluentIcon.PLAY,
            "录制控制",
            position=NavigationItemPosition.TOP
        )

        self.addSubInterface(
            self.timeline_page,
            FluentIcon.HISTORY,
            "活动时间线",
            position=NavigationItemPosition.TOP
        )

        self.addSubInterface(
            self.log_viewer_page,
            FluentIcon.DOCUMENT,
            "日志查看",
            position=NavigationItemPosition.BOTTOM
        )

        self.addSubInterface(
            self.classifier_page,
            FluentIcon.TAG,
            "分类管理",
            position=NavigationItemPosition.TOP
        )

        self.addSubInterface(
            self.alarm_page,
            FluentIcon.RINGER,
            "无声闹钟",
            position=NavigationItemPosition.TOP
        )

        self.addSubInterface(
            self.settings_page,
            FluentIcon.SETTING,
            "设置",
            position=NavigationItemPosition.BOTTOM
        )

    def closeEvent(self, event):
        """关闭时询问是否最小化到托盘，从托盘菜单退出时直接关闭"""
        if not self._tray_icon.isVisible():
            reply = QMessageBox.question(
                self, "关闭确认",
                "是否将窗口最小化到系统托盘？\n选择「否」将直接退出程序。",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes
            )

            if reply == QMessageBox.Yes:
                self.hide()
                self._tray_icon.show()
                self._tray_icon.showMessage(
                    "ScreenLogger",
                    "程序已最小化到系统托盘，双击图标恢复。",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
                event.ignore()
                return

            if reply == QMessageBox.Cancel:
                event.ignore()
                return

        self._do_cleanup()
        self._tray_icon.hide()
        event.accept()


    def _quit_app(self):
        """从托盘菜单退出程序"""
        self._do_cleanup()
        self._tray_icon.hide()
        QApplication.quit()

    def _do_cleanup(self):
        """停止所有后台任务"""
        log_manager.info("正在关闭主窗口，停止所有后台任务...")
        if self.screen_capture and self.screen_capture.is_recording:
            try:
                self.screen_capture.stop()
                log_manager.info("录制已停止")
            except Exception as e:
                log_manager.error(f"停止录制时发生错误: {e}")
        if hasattr(self, 'alarm_page'):
            try:
                self.alarm_page._overlay.stop()
                log_manager.info("闹钟已关闭")
            except Exception as e:
                log_manager.error(f"关闭闹钟时发生错误: {e}")

    def showNormal(self):
        """还原窗口时隐藏托盘图标"""
        self._tray_icon.hide()
        super().showNormal()
        self.activateWindow()
        self.raise_()

    def _on_tray_activated(self, reason):
        """双击托盘图标还原窗口"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()

    def _on_cleanup_complete(self, deleted_count):
        """存储清理完成槽函数"""
        log_manager.info(f"存储清理完成，删除 {deleted_count} 条记录")
        InfoBar.success(
            "清理完成",
            f"已清理 {deleted_count} 条旧记录",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self
        )

    def _on_migration_complete(self):
        """数据迁移完成槽函数"""
        log_manager.info("数据迁移完成，数据库和日志已切换到新路径")

        self.settings_page._load_settings()

        InfoBar.success(
            "迁移完成",
            f"数据已迁移至新位置，设置页面已刷新。如正在录制，建议重启以确保截图路径同步更新。",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=8000,
            parent=self
        )

    def _on_storage_error(self, error_msg):
        """存储错误槽函数"""
        log_manager.error(f"存储错误: {error_msg}")
        InfoBar.error(
            "存储错误",
            error_msg,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self
        )

    def _on_ai_analysis_complete(self, result):
        """AI分析完成槽函数（全局通知）"""
        log_manager.info("全局AI分析完成")
        if hasattr(self, 'timeline_page'):
            self.timeline_page._on_refresh()

    def _init_preset_tags(self):
        """初始化预设分类标签"""
        try:
            existing_tags = self.db_manager.get_all_tags()
            if existing_tags:
                return

            preset_tags = [
                {"name": "编程开发", "color": "#9C27B0", "pattern": "code"},
                {"name": "文档写作", "color": "#00BCD4", "pattern": "word"},
                {"name": "网页浏览", "color": "#FF5722", "pattern": "chrome"},
                {"name": "视频会议", "color": "#E91E63", "pattern": "meeting"},
                {"name": "娱乐休闲", "color": "#FF9800", "pattern": "video"},
                {"name": "设计创作", "color": "#795548", "pattern": "photoshop"},
                {"name": "办公处理", "color": "#4CAF50", "pattern": "excel"},
                {"name": "社交聊天", "color": "#3F51B5", "pattern": "wechat"},
                {"name": "其他", "color": "#607D8B", "pattern": ""},
            ]
            for tag_data in preset_tags:
                self.db_manager.add_tag(
                    name=tag_data["name"],
                    color=tag_data["color"],
                    is_preset=True,
                    pattern=tag_data["pattern"],
                    description=f"预设标签: {tag_data['name']}"
                )
            log_manager.info(f"已初始化 {len(preset_tags)} 个预设分类标签")
        except Exception as e:
            log_manager.error(f"初始化预设标签失败: {e}")