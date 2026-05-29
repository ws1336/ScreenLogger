"""
录制控制页面 - 控制屏幕录制、显示状态和图片回放
"""
import os
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout
)
from PySide6.QtCore import Qt, QDate, QRunnable, QThreadPool
from qfluentwidgets import (
    PrimaryPushButton, PushButton, CardWidget, FluentIcon,
    InfoBar, InfoBarPosition, BodyLabel, StrongBodyLabel, TitleLabel,
    FastCalendarPicker  
)

from logger import log_manager
from ui.image_player import ImagePlayer


class RecordingPage(QWidget):
    """录制控制页面，管理录制和图片回放"""

    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self._screenshot_count = 0
        self._last_screenshot_time = None
        self._is_recording = False
        self._is_paused = False
        self._screenshots_since_last_analysis = 0
        self._last_analysis_time = None
        self._init_ui()
        self._connect_signals()
        self._load_today_images()

    def _init_ui(self):
        """初始化录制页面UI布局"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(12)

        self._create_recording_control()

        self._create_status_display()

        self._create_image_player()

        self._create_date_selector()

    def _create_recording_control(self):
        """创建录制控制按钮区域"""
        control_card = CardWidget(self)
        control_layout = QHBoxLayout(control_card)
        control_layout.setContentsMargins(16, 12, 16, 12)
        control_layout.setSpacing(12)

        title = TitleLabel("录制控制", control_card)
        control_layout.addWidget(title)
        control_layout.addStretch()

        self.start_btn = PrimaryPushButton(FluentIcon.PLAY, "开始录制", control_card)
        self.start_btn.clicked.connect(self._on_start_recording)
        control_layout.addWidget(self.start_btn)

        self.pause_btn = PushButton(FluentIcon.PAUSE, "暂停", control_card)
        self.pause_btn.clicked.connect(self._on_pause_recording)
        self.pause_btn.setEnabled(False)
        control_layout.addWidget(self.pause_btn)

        self.stop_btn = PushButton(FluentIcon.CANCEL, "停止录制", control_card)
        self.stop_btn.clicked.connect(self._on_stop_recording)
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.stop_btn)

        self.main_layout.addWidget(control_card)

    def _create_status_display(self):
        """创建状态显示区域"""
        status_card = CardWidget(self)
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(16, 12, 16, 12)
        status_layout.setSpacing(20)

        status_left = QVBoxLayout()
        self.recording_status_label = BodyLabel("状态: 未录制", status_card)
        status_left.addWidget(self.recording_status_label)
        self.screenshot_count_label = BodyLabel("截图数: 0", status_card)
        status_left.addWidget(self.screenshot_count_label)
        status_layout.addLayout(status_left)

        status_layout.addStretch()

        status_right = QVBoxLayout()
        self.last_screenshot_label = BodyLabel("最后截图: --", status_card)
        status_right.addWidget(self.last_screenshot_label)
        status_layout.addLayout(status_right)

        self.main_layout.addWidget(status_card)

    def _create_image_player(self):
        """创建图片播放器区域"""
        player_card = CardWidget(self)
        player_layout = QVBoxLayout(player_card)
        player_layout.setContentsMargins(12, 12, 12, 12)
        player_layout.setSpacing(8)

        title_layout = QHBoxLayout()
        title = StrongBodyLabel("图片回放", player_card)
        title_layout.addWidget(title)
        title_layout.addStretch()

        self.player_date_label = BodyLabel("", player_card)
        self.player_date_label.setStyleSheet("color: #888888;")
        title_layout.addWidget(self.player_date_label)

        player_layout.addLayout(title_layout)

        self.image_player = ImagePlayer(player_card)
        self.image_player.play_interval_changed.connect(self._on_image_play_interval_changed)
        player_layout.addWidget(self.image_player, 1)

        if self.main_window and self.main_window._config:
            saved_interval = self.main_window._config.get("image_settings/image_play_interval", 1)
            self.image_player.timeline_slider.set_interval(saved_interval)

        self.main_layout.addWidget(player_card, 1)

    def _create_date_selector(self):
        """创建日期选择区域"""
        date_card = CardWidget(self)
        date_layout = QHBoxLayout(date_card)
        date_layout.setContentsMargins(16, 12, 16, 12)
        date_layout.setSpacing(12)

        date_label = BodyLabel("选择日期:", date_card)
        date_layout.addWidget(date_label)

        self.date_picker = FastCalendarPicker(date_card)
        self.date_picker.setFixedWidth(140)
        self.date_picker.setDate(QDate.currentDate())
        self.date_picker.dateChanged.connect(self._on_date_changed)
        date_layout.addWidget(self.date_picker)

        date_layout.addStretch()

        refresh_btn = PushButton(FluentIcon.SYNC, "刷新截图", date_card)
        refresh_btn.clicked.connect(self._load_today_images)
        date_layout.addWidget(refresh_btn)

        self.main_layout.addWidget(date_card)

    def _connect_signals(self):
        """连接各模块信号"""
        if not self.main_window:
            return

        if self.main_window.screen_capture:
            self.main_window.screen_capture.screenshot_taken.connect(
                self._on_screenshot_taken
            )
            self.main_window.screen_capture.capture_error.connect(
                self._on_capture_error
            )

        if self.main_window.ai_analyzer:
            self.main_window.ai_analyzer.analysis_complete.connect(
                self._on_analysis_complete
            )
            self.main_window.ai_analyzer.analysis_error.connect(
                self._on_analysis_error
            )

    def _on_date_changed(self, date):
        """日期选择改变事件"""
        self._load_images_for_date(date)

    def _load_today_images(self):
        """加载今天的截图"""
        self._load_images_for_date(QDate.currentDate())

    def _load_images_for_date(self, qdate):
        """
        加载指定日期的截图

        Args:
            qdate: QDate对象
        """
        if not self.main_window or not self.main_window.db_manager:
            return

        target_date = qdate.toPython()
        start_time = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0)
        end_time = start_time + timedelta(days=1)

        try:
            screenshots = self.main_window.db_manager.get_screenshots_in_range(start_time, end_time)

            if not screenshots:
                self.image_player.clear()
                self.player_date_label.setText(f"{target_date.strftime('%Y-%m-%d')} (无截图)")
                return

            self.image_player.load_images(screenshots, target_date)
            self.player_date_label.setText(f"{target_date.strftime('%Y-%m-%d')} ({len(screenshots)} 张截图)")

            log_manager.info(f"加载日期 {target_date.strftime('%Y-%m-%d')} 的截图: {len(screenshots)} 张")

        except Exception as e:
            log_manager.error(f"加载截图失败: {e}")
            InfoBar.error(
                "加载失败",
                f"无法加载截图: {e}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

    def _on_start_recording(self):
        """开始录制按钮点击事件"""
        if not self.main_window:
            return

        try:
            self.main_window.screen_capture.start()

            self._is_recording = True
            self._is_paused = False
            self._screenshots_since_last_analysis = 0
            self._last_analysis_time = datetime.now()

            self.start_btn.setEnabled(False)
            self.pause_btn.setEnabled(True)
            self.stop_btn.setEnabled(True)

            self.recording_status_label.setText("状态: 录制中")
            self.recording_status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")

            InfoBar.success(
                "开始录制",
                "屏幕录制已开始",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )

        except Exception as e:
            log_manager.error(f"开始录制失败: {e}")
            InfoBar.error(
                "启动失败",
                f"无法开始录制: {e}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

    def _on_pause_recording(self):
        """暂停/恢复录制按钮点击事件"""
        if not self.main_window:
            return

        if self._is_paused:
            self.main_window.screen_capture.resume()
            self._is_paused = False
            self.pause_btn.setText("暂停")
            self.pause_btn.setIcon(FluentIcon.PAUSE)
            self.recording_status_label.setText("状态: 录制中")
            InfoBar.info(
                "恢复录制",
                "屏幕录制已恢复",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )
        else:
            self.main_window.screen_capture.pause()
            self._is_paused = True
            self.pause_btn.setText("恢复")
            self.pause_btn.setIcon(FluentIcon.PLAY)
            self.recording_status_label.setText("状态: 已暂停")
            InfoBar.warning(
                "暂停录制",
                "屏幕录制已暂停",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )

    def _on_stop_recording(self):
        """停止录制按钮点击事件"""
        if not self.main_window:
            return

        try:
            self.main_window.screen_capture.stop()

            self._is_recording = False
            self._is_paused = False

            self.start_btn.setEnabled(True)
            self.pause_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)

            self.pause_btn.setText("暂停")
            self.pause_btn.setIcon(FluentIcon.PAUSE)

            self.recording_status_label.setText("状态: 未录制")
            self.recording_status_label.setStyleSheet("")

            InfoBar.success(
                "停止录制",
                "屏幕录制已停止",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )

            self._load_today_images()

        except Exception as e:
            log_manager.error(f"停止录制失败: {e}")
            InfoBar.error(
                "停止失败",
                f"无法停止录制: {e}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

    def _on_screenshot_taken(self, filepath, timestamp, window_title):
        """截图完成事件处理"""
        self._screenshot_count += 1
        self.screenshot_count_label.setText(f"截图数: {self._screenshot_count}")

        now = datetime.now()
        self._last_screenshot_time = now
        self.last_screenshot_label.setText(f"最后截图: {now.strftime('%H:%M:%S')}")

        self._check_auto_ai_analysis()

    def _check_auto_ai_analysis(self):
        """检查是否需要自动触发AI分析"""
        if not self._is_recording or not self.main_window:
            return

        provider = self.main_window._config.get("ai_settings/ai_provider", "off")
        if provider == "off":
            return

        analysis_interval = self.main_window._config.get("image_settings/ai_analysis_interval", 60)
        self._screenshots_since_last_analysis += 1

        if self._screenshots_since_last_analysis >= analysis_interval:
            self._screenshots_since_last_analysis = 0
            self._trigger_auto_ai_analysis()

    def _trigger_auto_ai_analysis(self):
        """在后台触发AI分析，只分析上次分析以来的新截图"""
        try:
            now = datetime.now()
            start_time = self._last_analysis_time

            if start_time is None:
                log_manager.warning("上次分析时间为空，跳过自动AI分析")
                return

            self._last_analysis_time = now

            ai_analyzer = self.main_window.ai_analyzer

            class AIAnalysisTask(QRunnable):
                def __init__(self, analyzer, start, end):
                    super().__init__()
                    self.analyzer = analyzer
                    self.start = start
                    self.end = end
                    self.setAutoDelete(True)

                def run(self):
                    try:
                        result = self.analyzer.analyze_screenshots_in_range(self.start, self.end)
                        if result:
                            activities = result.get('activities', {})
                            log_manager.info(f"自动AI分析完成: {activities}")
                        else:
                            log_manager.warning("自动AI分析未返回结果")
                    except Exception as e:
                        log_manager.error(f"自动AI分析失败: {e}")

            task = AIAnalysisTask(ai_analyzer, start_time.isoformat(), now.isoformat())
            QThreadPool.globalInstance().start(task)

            log_manager.info(f"自动AI分析已触发: {start_time.isoformat()} ~ {now.isoformat()}")

        except Exception as e:
            log_manager.error(f"触发自动AI分析失败: {e}")

    def _on_capture_error(self, error_msg):
        """截图错误事件处理"""
        log_manager.error(f"截图错误: {error_msg}")
        InfoBar.error(
            "截图错误",
            error_msg,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self
        )
        # 停止录制
        self._on_stop_recording()

    def _on_analysis_complete(self, result):
        """AI分析完成事件处理"""
        log_manager.info(f"AI分析完成: {result.get('activity_type', '未知')}")

    def _on_analysis_error(self, error_msg):
        """AI分析错误事件处理"""
        log_manager.error(f"AI分析错误: {error_msg}")

    def _on_image_play_interval_changed(self, interval: int):
        """图片播放间隔变更时同步到配置和设置页面"""
        if self.main_window and self.main_window._config:
            self.main_window._config.set("image_settings/image_play_interval", interval)
            log_manager.info(f"图片播放间隔已更新为: {interval} 张")

        if self.main_window and hasattr(self.main_window, 'settings_page'):
            settings = self.main_window.settings_page
            if hasattr(settings, 'image_play_interval_spin'):
                settings.image_play_interval_spin.setValue(interval)
