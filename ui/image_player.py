"""
基于截图数据的图片播放器
从数据库中加载截图，按时间顺序播放，固定1帧/秒。
"""
import os
from datetime import datetime, timedelta
from typing import List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSlider, QLabel,
    QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap, QPainter, QColor
from qfluentwidgets import (
    PrimaryPushButton, FluentIcon, BodyLabel, ComboBox
)

from config import Settings
from logger import log_manager


class TimelineSliderWidget(QFrame):
    """
    时间轴滑块组件
    支持截图时间段显示和点击跳转
    """
    seek_to = Signal(object)
    play_pause_toggled = Signal(bool)
    interval_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._time_range = (0, 24 * 60 * 60 * 1000)
        self._screenshot_timestamps = []
        self._current_position_ms = 0
        self._is_playing = False
        self._config = Settings()

        self._init_ui()

    def _init_ui(self):
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            TimelineSliderWidget {
                background-color: #1a1a1a;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        time_layout = QHBoxLayout()
        self.current_time_label = BodyLabel("00:00:00", self)
        self.current_time_label.setStyleSheet("color: #4CAF50; font-size: 14px; font-weight: bold;")
        time_layout.addWidget(self.current_time_label)

        time_layout.addStretch()

        self.total_time_label = BodyLabel("00:00:00", self)
        self.total_time_label.setStyleSheet("color: #888888; font-size: 14px;")
        time_layout.addWidget(self.total_time_label)

        layout.addLayout(time_layout)

        self.slider = QSlider(Qt.Orientation.Horizontal, self)
        self.slider.setRange(0, 10000)
        self.slider.setValue(0)
        self.slider.setSingleStep(10)
        self.slider.setPageStep(100)

        self.slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 8px;
                background: #2a2a2a;
                border-radius: 4px;
            }
            QSlider::sub-page:horizontal {
                background: #4CAF50;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                width: 16px;
                height: 16px;
                background: #ffffff;
                border-radius: 50%;
                margin: -4px 0;
            }
            QSlider::handle:horizontal:hover {
                background: #e0e0e0;
            }
        """)

        self.slider.valueChanged.connect(self._on_slider_changed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        layout.addWidget(self.slider)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        self.play_btn = PrimaryPushButton("", self)
        self.play_btn.setIcon(FluentIcon.PLAY)
        self.play_btn.setFixedWidth(80)
        self.play_btn.clicked.connect(self._on_play_pause)
        button_layout.addWidget(self.play_btn)

        interval_label = BodyLabel("间隔:", self)
        interval_label.setStyleSheet("color: #888888;")
        button_layout.addWidget(interval_label)

        self.interval_combo = ComboBox(self)
        self.interval_combo.addItems(["1张", "2张", "5张", "10张", "30张", "60张", "300张"])
        self.interval_combo.setCurrentIndex(0)
        self.interval_combo.setFixedWidth(80)
        self.interval_combo.currentIndexChanged.connect(self._on_interval_changed)
        button_layout.addWidget(self.interval_combo)

        button_layout.addStretch()

        self.screenshot_count_label = BodyLabel("", self)
        self.screenshot_count_label.setStyleSheet("color: #888888; font-size: 12px;")
        button_layout.addWidget(self.screenshot_count_label)

        layout.addLayout(button_layout)

    def set_time_range(self, start_ms: int, end_ms: int):
        self._time_range = (start_ms, end_ms)
        total_ms = end_ms - start_ms
        if total_ms <= 0:
            total_ms = 24 * 60 * 60 * 1000
        max_slider_value = min(total_ms, 10000)
        self.slider.setRange(0, max_slider_value)
        self.total_time_label.setText(self._format_time(end_ms))
        self.update()

    def set_screenshot_timestamps(self, timestamps: List[int]):
        self._screenshot_timestamps = timestamps

    def set_position(self, position_ms: int):
        self._current_position_ms = position_ms
        range_start, range_end = self._time_range
        total_range = range_end - range_start
        if total_range <= 0:
            return
        ratio = (position_ms - range_start) / total_range
        slider_value = int(ratio * self.slider.maximum())
        slider_value = max(0, min(slider_value, self.slider.maximum()))
        self.slider.blockSignals(True)
        self.slider.setValue(slider_value)
        self.slider.blockSignals(False)
        self.current_time_label.setText(self._format_time(position_ms))
        self.update()

    def set_playing(self, is_playing: bool):
        self._is_playing = is_playing
        if is_playing:
            self.play_btn.setText("暂停")
            self.play_btn.setIcon(FluentIcon.PAUSE)
        else:
            self.play_btn.setText("播放")
            self.play_btn.setIcon(FluentIcon.PLAY)

    def get_interval(self) -> int:
        interval_map = {"1张": 1, "2张": 2, "5张": 5, "10张": 10, "30张": 30, "60张": 60, "300张": 300}
        return interval_map.get(self.interval_combo.currentText(), 1)

    def set_interval(self, interval: int):
        """设置间隔张数（从配置初始化时使用，不触发信号）"""
        interval_map = {1: "1张", 2: "2张", 5: "5张", 10: "10张", 30: "30张", 60: "60张", 300: "300张"}
        text = interval_map.get(interval, "1张")
        idx = self.interval_combo.findText(text)
        if idx >= 0:
            self.interval_combo.blockSignals(True)
            self.interval_combo.setCurrentIndex(idx)
            self.interval_combo.blockSignals(False)

    def _format_time(self, ms: int) -> str:
        # 从配置中获取时区设置，默认为 UTC+8
        _time_zone = self._config.get("other_settings/time_zone", 8)
        total_seconds = ms // 1000
        hours = (total_seconds // 3600 + _time_zone) % 24
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _on_slider_changed(self, value):
        range_start, range_end = self._time_range
        total_range = range_end - range_start
        if total_range <= 0:
            return
        ratio = value / self.slider.maximum() if self.slider.maximum() > 0 else 0
        position_ms = int(range_start + ratio * total_range)
        self.current_time_label.setText(self._format_time(position_ms))

    def _on_slider_released(self):
        range_start, range_end = self._time_range
        total_range = range_end - range_start
        if total_range <= 0:
            return
        ratio = self.slider.value() / self.slider.maximum() if self.slider.maximum() > 0 else 0
        absolute_position = int(range_start + ratio * total_range)
        self.seek_to.emit(absolute_position)

    def _on_play_pause(self):
        self._is_playing = not self._is_playing
        self.set_playing(self._is_playing)
        self.play_pause_toggled.emit(self._is_playing)

    def _on_interval_changed(self, index):
        interval = self.get_interval()
        log_manager.info(f"播放间隔: {self.interval_combo.currentText()}")
        self.interval_changed.emit(interval)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._screenshot_timestamps:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        slider_rect = self.slider.geometry()
        range_start, range_end = self._time_range
        total_range = range_end - range_start

        if total_range <= 0:
            return

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#4CAF50"))

        for ts in self._screenshot_timestamps:
            if range_start <= ts <= range_end:
                x = slider_rect.left() + ((ts - range_start) / total_range) * slider_rect.width()
                painter.drawRect(int(x), slider_rect.top() - 2, 2, 3)


class ImagePlayer(QWidget):
    """
    图片播放器组件
    基于截图数据进行时间轴播放，固定1帧/秒，支持间隔跳帧。
    """
    playback_state_changed = Signal(bool)
    play_interval_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._screenshots = []
        self._display_indices = []
        self._current_display_index = -1
        self._current_timestamp_ms = 0
        self._time_range = (0, 24 * 60 * 60 * 1000)
        self._is_playing = False
        self._playback_timer = QTimer(self)
        self._playback_timer.timeout.connect(self._on_timer_tick)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.image_display = QFrame(self)
        self.image_display.setMinimumHeight(300)
        self.image_display.setStyleSheet("background-color: #000000;")
        self.image_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        display_layout = QVBoxLayout(self.image_display)
        display_layout.setContentsMargins(0, 0, 0, 0)

        self.image_label = QLabel(self.image_display)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: #000000;")
        self.image_label.setMinimumSize(320, 180)
        self.image_label.hide()
        display_layout.addWidget(self.image_label)

        self.no_image_label = QLabel("无截图数据", self.image_display)
        self.no_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_image_label.setStyleSheet("""
            color: #888888;
            font-size: 24px;
            background-color: rgba(0, 0, 0, 150);
        """)
        self.no_image_label.setMinimumSize(200, 100)
        self.no_image_label.show()
        display_layout.addWidget(self.no_image_label)

        layout.addWidget(self.image_display, 1)

        self.timeline_slider = TimelineSliderWidget(self)
        self.timeline_slider.seek_to.connect(self._on_seek)
        self.timeline_slider.play_pause_toggled.connect(self._on_play_pause_toggled)
        self.timeline_slider.interval_changed.connect(self._on_interval_changed)
        layout.addWidget(self.timeline_slider)

        info_layout = QHBoxLayout()
        self.info_label = BodyLabel("未加载截图", self)
        self.info_label.setStyleSheet("color: #888888;")
        info_layout.addWidget(self.info_label)

        info_layout.addStretch()

        self.range_label = BodyLabel("", self)
        self.range_label.setStyleSheet("color: #666666; font-size: 12px;")
        info_layout.addWidget(self.range_label)

        layout.addLayout(info_layout)

        self._playback_timer.start(1000)

    def load_images(self, screenshots, date: datetime):
        """
        加载截图数据

        Args:
            screenshots: 截图记录列表（数据库对象字典或ORM对象）
            date: 日期
        """
        if not screenshots:
            self._time_range = (
                int(datetime(date.year, date.month, date.day, 0, 0, 0).timestamp() * 1000),
                int((datetime(date.year, date.month, date.day, 0, 0, 0) + timedelta(days=1)).timestamp() * 1000)
            )
            self._screenshots = []
            self._display_indices = []
            self._current_display_index = -1
            self.timeline_slider.set_time_range(*self._time_range)
            self.timeline_slider.set_screenshot_timestamps([])
            self.info_label.setText("该日期无截图记录")
            self._show_no_image()
            return

        self._screenshots = []
        for s in screenshots:
            if hasattr(s, 'filepath'):
                self._screenshots.append({
                    "id": getattr(s, "id", 0),
                    "filepath": s.filepath,
                    "timestamp": s.timestamp,
                })
            else:
                self._screenshots.append({
                    "id": s.get("id", 0),
                    "filepath": s.get("filepath", ""),
                    "timestamp": s.get("timestamp", datetime.now()),
                })

        self._screenshots.sort(key=lambda x: x["timestamp"])

        if not self._screenshots:
            self._show_no_image()
            return

        interval = self.timeline_slider.get_interval()
        self._build_display_indices(interval)

        earliest_ts = int(self._screenshots[0]["timestamp"].timestamp() * 1000)
        latest_ts = int(self._screenshots[-1]["timestamp"].timestamp() * 1000)
        self._time_range = (earliest_ts, latest_ts)

        screenshot_timestamps = [int(s["timestamp"].timestamp() * 1000) for s in self._screenshots]
        self.timeline_slider.set_time_range(*self._time_range)
        self.timeline_slider.set_screenshot_timestamps(screenshot_timestamps)

        start_dt = self._screenshots[0]["timestamp"]
        end_dt = self._screenshots[-1]["timestamp"]
        self.range_label.setText(f"{start_dt.strftime('%H:%M:%S')} ~ {end_dt.strftime('%H:%M:%S')}")
        self.info_label.setText(f"已加载 {len(self._screenshots)} 张截图（显示 {len(self._display_indices)} 张）")
        self.timeline_slider.screenshot_count_label.setText(f"截图: {len(self._screenshots)} | 显示: {len(self._display_indices)}")

        self._current_display_index = 0 if self._display_indices else -1
        if self._current_display_index >= 0:
            actual_idx = self._display_indices[self._current_display_index]
            self._current_timestamp_ms = int(self._screenshots[actual_idx]["timestamp"].timestamp() * 1000)
            self.timeline_slider.set_position(self._current_timestamp_ms)
            self._display_current_image()
        else:
            self._show_no_image()

        log_manager.info(f"加载截图：{len(self._screenshots)} 张，显示索引 {len(self._display_indices)} 个")

    def _build_display_indices(self, interval: int):
        """根据间隔构建显示索引列表"""
        self._display_indices = list(range(0, len(self._screenshots), interval))

    def _on_interval_changed(self, interval: int):
        """播放间隔改变时重新构建显示索引并重置位置"""
        if not self._screenshots:
            return
        self._build_display_indices(interval)
        self.info_label.setText(f"已加载 {len(self._screenshots)} 张截图（显示 {len(self._display_indices)} 张）")
        self.timeline_slider.screenshot_count_label.setText(f"截图: {len(self._screenshots)} | 显示: {len(self._display_indices)}")
        self._current_display_index = 0 if self._display_indices else -1
        if self._current_display_index >= 0:
            actual_idx = self._display_indices[self._current_display_index]
            self._current_timestamp_ms = int(self._screenshots[actual_idx]["timestamp"].timestamp() * 1000)
            self.timeline_slider.set_position(self._current_timestamp_ms)
            self._display_current_image()
        else:
            self._show_no_image()
        self.play_interval_changed.emit(interval)

    def _on_timer_tick(self):
        """定时器驱动，每秒触发一次"""
        if not self._is_playing or not self._display_indices:
            return

        self._current_display_index += 1
        if self._current_display_index >= len(self._display_indices):
            self._current_display_index = 0

        actual_idx = self._display_indices[self._current_display_index]
        self._current_timestamp_ms = int(self._screenshots[actual_idx]["timestamp"].timestamp() * 1000)
        self.timeline_slider.set_position(self._current_timestamp_ms)
        self._display_current_image()

    def _display_current_image(self):
        """显示当前索引的截图"""
        if self._current_display_index < 0 or self._current_display_index >= len(self._display_indices):
            self._show_no_image()
            return

        actual_idx = self._display_indices[self._current_display_index]
        if actual_idx < 0 or actual_idx >= len(self._screenshots):
            self._show_no_image()
            return

        filepath = self._screenshots[actual_idx]["filepath"]
        if not filepath or not os.path.exists(filepath):
            self._show_no_image()
            return

        pixmap = QPixmap(filepath)
        if pixmap.isNull():
            self._show_no_image()
            return

        scaled_pixmap = pixmap.scaled(
            self.image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.image_label.setPixmap(scaled_pixmap)
        self.image_label.show()
        self.image_label.raise_()
        self.no_image_label.hide()

    def _show_no_image(self):
        self.image_label.clear()
        self.image_label.hide()
        self.no_image_label.show()
        self.no_image_label.raise_()

    def _find_closest_display_index(self, timestamp_ms: int) -> int:
        """找到最接近指定时间戳的显示索引"""
        if not self._display_indices:
            return -1
        closest = 0
        min_diff = abs(int(self._screenshots[self._display_indices[0]]["timestamp"].timestamp() * 1000) - timestamp_ms)
        for i, actual_idx in enumerate(self._display_indices):
            ts = int(self._screenshots[actual_idx]["timestamp"].timestamp() * 1000)
            diff = abs(ts - timestamp_ms)
            if diff < min_diff:
                min_diff = diff
                closest = i
        return closest

    def _on_seek(self, timestamp_ms):
        """跳转到指定时间"""
        self._current_timestamp_ms = timestamp_ms
        idx = self._find_closest_display_index(timestamp_ms)
        if idx >= 0:
            self._current_display_index = idx
            self.timeline_slider.set_position(timestamp_ms)
            self._display_current_image()

    def _on_play_pause_toggled(self, is_playing: bool):
        """播放/暂停切换"""
        self._is_playing = is_playing
        self.playback_state_changed.emit(is_playing)
        if is_playing and self._current_display_index < 0 and self._display_indices:
            self._current_display_index = 0
            self._display_current_image()

    def play(self):
        """开始播放"""
        self._is_playing = True
        self.timeline_slider.set_playing(True)
        if self._current_display_index < 0 and self._display_indices:
            self._current_display_index = 0
            self._display_current_image()

    def pause(self):
        """暂停播放"""
        self._is_playing = False
        self.timeline_slider.set_playing(False)

    def clear(self):
        """清除所有截图数据"""
        self._screenshots = []
        self._display_indices = []
        self._current_display_index = -1
        self._current_timestamp_ms = 0
        self._is_playing = False
        self.timeline_slider.set_playing(False)
        self.timeline_slider.set_time_range(0, 24 * 60 * 60 * 1000)
        self.timeline_slider.set_screenshot_timestamps([])
        self.info_label.setText("未加载截图")
        self.range_label.setText("")
        self.timeline_slider.screenshot_count_label.setText("")
        self._show_no_image()
