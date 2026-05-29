"""
日志查看器页面 - 实时显示应用日志，支持级别和时间筛选
"""
from datetime import datetime, timedelta
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout)

from PySide6.QtGui import QTextCharFormat, QColor, QFont
from qfluentwidgets import (
    ComboBox, PushButton, FluentIcon,
    BodyLabel, PlainTextEdit
)

from logger import log_manager


class LogViewerPage(QWidget):
    """日志查看器页面，实时显示和筛选应用日志"""

    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self._all_logs = []  # 存储所有日志条目 (level, message, timestamp)
        self._current_filter_level = "ALL"
        self._filter_start = None
        self._filter_end = None
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        """初始化日志查看器UI布局"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(12)

        # 顶部工具栏
        self._create_toolbar()

        # 日志显示区域
        self.log_text_edit = PlainTextEdit(self)
        self.log_text_edit.setReadOnly(True)
        self.log_text_edit.setMaximumBlockCount(10000)  # 限制最大行数
        font = QFont("Consolas", 10)
        self.log_text_edit.setFont(font)
        self.main_layout.addWidget(self.log_text_edit)

        # 状态栏
        self.status_label = BodyLabel("就绪", self)
        self.main_layout.addWidget(self.status_label)

    def _create_toolbar(self):
        """创建顶部工具栏"""
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(12)

        # 日志级别筛选
        level_label = BodyLabel("日志级别:", self)
        toolbar_layout.addWidget(level_label)

        self.level_combo = ComboBox(self)
        self.level_combo.addItems(["ALL", "DEBUG", "INFO", "WARNING", "ERROR"])
        self.level_combo.currentTextChanged.connect(self._on_level_filter_changed)
        toolbar_layout.addWidget(self.level_combo)

        toolbar_layout.addSpacing(20)

        # 时间范围筛选
        time_label = BodyLabel("最近:", self)
        toolbar_layout.addWidget(time_label)

        self.time_combo = ComboBox(self)
        self.time_combo.addItems([
            "不筛选", "最近5分钟", "最近15分钟", "最近30分钟",
            "最近1小时", "最近3小时", "最近6小时", "最近12小时", "最近24小时"
        ])
        self.time_combo.currentIndexChanged.connect(self._on_time_filter_changed)
        toolbar_layout.addWidget(self.time_combo)

        toolbar_layout.addStretch()

        # 清除按钮
        self.clear_btn = PushButton(FluentIcon.DELETE, "清除日志", self)
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        toolbar_layout.addWidget(self.clear_btn)

        self.main_layout.addLayout(toolbar_layout)

    def _connect_signals(self):
        """连接日志信号"""
        try:
            emitter = log_manager.get_emitter()
            if emitter:
                emitter.log_emitted.connect(self._on_log_emitted)
        except Exception as e:
            pass  # 某些环境下发射器可能未初始化

    def _on_log_emitted(self, level, message, timestamp):
        """接收日志发射信号，追加日志条目"""
        self._all_logs.append((level, message, timestamp))
        if self._should_display(level, timestamp):
            self._append_log_text(level, message, timestamp)

    def _should_display(self, level, timestamp):
        """判断日志是否应该根据当前筛选条件显示"""
        if self._current_filter_level != "ALL":
            level_names = {10: "DEBUG", 20: "INFO", 30: "WARNING", 40: "ERROR"}
            level_name = level_names.get(level, "DEBUG")
            if level_name != self._current_filter_level:
                return False
        if self._filter_start or self._filter_end:
            try:
                ts_dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S") if isinstance(timestamp, str) else timestamp
            except (ValueError, TypeError):
                return True
            if self._filter_start and ts_dt < self._filter_start:
                return False
            if self._filter_end and ts_dt > self._filter_end:
                return False
        return True

    def _append_log_text(self, level, message, timestamp):
        """向日志文本框追加一条带颜色的日志"""
        time_str = timestamp[:19] if isinstance(timestamp, str) else str(timestamp)
        # 将日志级别整数转换为字符串
        level_names = {10: "DEBUG", 20: "INFO", 30: "WARNING", 40: "ERROR"}
        level_name = level_names.get(level, "DEBUG") if isinstance(level, int) else str(level)
        line = f"[{time_str}] [{level_name}] {message}"

        # 根据日志级别设置不同颜色
        color_map = {
            "ERROR": QColor("#f44747"),
            "WARNING": QColor("#e5a72e"),
            "INFO": QColor("#4fc1ff"),
            "DEBUG": QColor("#888888"),
        }
        color = color_map.get(level_name, QColor("#d4d4d4"))

        cursor = self.log_text_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)

        fmt = QTextCharFormat()
        fmt.setForeground(color)
        cursor.insertText(line + "\n", fmt)

        # 自动滚动到底部
        scrollbar = self.log_text_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_level_filter_changed(self, level):
        """日志级别筛选变更事件"""
        self._current_filter_level = level
        self._apply_filter()

    def _on_time_filter_changed(self, index):
        """时间范围筛选变更事件"""
        text = self.time_combo.currentText()
        now = datetime.now()
        time_deltas = {
            "最近5分钟": timedelta(minutes=5),
            "最近15分钟": timedelta(minutes=15),
            "最近30分钟": timedelta(minutes=30),
            "最近1小时": timedelta(hours=1),
            "最近3小时": timedelta(hours=3),
            "最近6小时": timedelta(hours=6),
            "最近12小时": timedelta(hours=12),
            "最近24小时": timedelta(hours=24),
        }
        delta = time_deltas.get(text)
        if delta:
            self._filter_start = now - delta
            self._filter_end = now
        else:
            self._filter_start = None
            self._filter_end = None
        self._apply_filter()

    def _apply_filter(self):
        """根据当前筛选条件重新渲染日志内容"""
        self.log_text_edit.clear()
        for level, message, timestamp in self._all_logs:
            if self._should_display(level, timestamp):
                self._append_log_text(level, message, timestamp)
        count = len(self._all_logs)
        displayed = self.log_text_edit.document().blockCount() - 1
        self.status_label.setText(f"共 {count} 条日志，显示 {max(0, displayed)} 条")

    def _on_clear_clicked(self):
        """清除日志按钮点击事件"""
        self._all_logs.clear()
        self.log_text_edit.clear()
        self.status_label.setText("日志已清除")