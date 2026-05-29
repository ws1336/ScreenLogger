"""
无声闹钟页面 - 创建和管理多个无声闹钟

支持同时添加多个独立闹钟，每个闹钟独立配置定时方式、
提醒文字，并独立控制闪烁。闹钟触发时屏幕边框闪烁红色，
对应条目也同步闪烁。
"""
import uuid
from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QWidget, QApplication, QVBoxLayout, QHBoxLayout,
    QFrame, QDialog, QStackedWidget, QPushButton
)
from PySide6.QtCore import Qt, QTime, QTimer, Signal
from PySide6.QtGui import QPalette, QColor, QPainter
from qfluentwidgets import (
    PrimaryPushButton, PushButton, ToolButton, SwitchButton, PillPushButton,
    CardWidget, BodyLabel, StrongBodyLabel, TitleLabel, FluentIcon,
    TimePicker, SpinBox, LineEdit, CheckBox, Pivot,
    ScrollArea, MessageBox, isDarkTheme, ThemeColor
)

from ui.silent_alarm import SilentAlarmOverlay, WEEKDAY_NAMES

class DismissPillPushButton(PillPushButton):
    """红色背景的停止闪烁按钮"""
    """
    #e74c3c,
    #c0392b,
    #a93226,
    """
    DISMISS_BG_COLOR = QColor("#e74c3c")
    DISMISS_HOVER_COLOR = QColor("#c0392b")
    DISMISS_PRESSED_COLOR = QColor("#a93226")

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing)

        rect = self.rect()
        if self.isPressed:
            bgColor = self.DISMISS_PRESSED_COLOR
        elif self.isHover:
            bgColor = self.DISMISS_HOVER_COLOR
        else:
            bgColor = self.DISMISS_BG_COLOR

        painter.setPen(Qt.transparent)
        painter.setBrush(bgColor)
        r = rect.height() / 2
        painter.drawRoundedRect(rect, r, r)
        QPushButton.paintEvent(self, e)


class AlarmData:
    """单个闹钟的配置数据"""

    MODE_SINGLE = "single"
    MODE_DAILY = "daily"
    MODE_CYCLE = "cycle"

    def __init__(self, alarm_id=None, enabled=True, mode=MODE_SINGLE,
                 message="⏰ 时间到！", countdown_seconds=10,
                 hour=9, minute=0, days_of_week=None,
                 start_hour=8, start_minute=0,
                 end_hour=22, end_minute=0, interval_minutes=60):
        self.alarm_id = alarm_id or str(uuid.uuid4())
        self.enabled = enabled
        self.mode = mode
        self.message = message
        self.countdown_seconds = countdown_seconds
        self.hour = hour
        self.minute = minute
        self.days_of_week = days_of_week if days_of_week is not None else list(range(5))
        self.start_hour = start_hour
        self.start_minute = start_minute
        self.end_hour = end_hour
        self.end_minute = end_minute
        self.interval_minutes = interval_minutes

    @classmethod
    def from_config(cls, mode: str, **kwargs):
        data = cls()
        data.mode = mode
        for k, v in kwargs.items():
            if hasattr(data, k):
                setattr(data, k, v)
        return data

    def display_description(self) -> str:
        from ui.silent_alarm import SilentAlarmOverlay
        if self.mode == self.MODE_SINGLE:
            return f"单次 {self.countdown_seconds} 秒倒计时"
        elif self.mode == self.MODE_DAILY:
            days = SilentAlarmOverlay._days_to_str(self.days_of_week)
            return f"每日 {self.hour:02d}:{self.minute:02d} ({days})"
        elif self.mode == self.MODE_CYCLE:
            days = SilentAlarmOverlay._days_to_str(self.days_of_week)
            return (f"循环 {self.start_hour:02d}:{self.start_minute:02d}"
                    f"~{self.end_hour:02d}:{self.end_minute:02d}"
                    f" 每{self.interval_minutes}分 ({days})")
        return ""


# ── Alarm Config Dialog ─────────────────────────────────────────


class AlarmConfigDialog(QDialog):
    """闹钟配置对话框"""

    def __init__(self, parent=None, edit_data: AlarmData = None):
        super().__init__(parent)
        self._edit_data = edit_data
        self._current_mode = "single"
        self._init_ui()

        if edit_data:
            self._load_data(edit_data)

    def _init_ui(self):
        title = "编辑闹钟" if self._edit_data else "添加闹钟"
        self.setWindowTitle(title)
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        self._segment = Pivot(self)
        self._segment.addItem("single", "单次定时")
        self._segment.addItem("daily", "每日定时")
        self._segment.addItem("cycle", "循环定时")
        self._segment.setCurrentItem("single")
        self._segment.setIndicatorLength(48)
        self._segment.currentItemChanged.connect(self._on_mode_changed)
        layout.addWidget(self._segment)

        self._config_card = CardWidget(self)
        self._config_card.setBorderRadius(8)
        card_layout = QVBoxLayout(self._config_card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        self._config_stack = QStackedWidget(self._config_card)
        self._config_stack.addWidget(self._build_single_panel())
        self._config_stack.addWidget(self._build_daily_panel())
        self._config_stack.addWidget(self._build_cycle_panel())
        card_layout.addWidget(self._config_stack)
        layout.addWidget(self._config_card)

        msg_label = StrongBodyLabel("提醒文字", self)
        layout.addWidget(msg_label)
        self._msg_input = LineEdit(self)
        self._msg_input.setMaxLength(10)
        self._msg_input.setText("⏰ 时间到！")
        self._msg_input.setPlaceholderText("输入提醒文字（10字以内）")
        layout.addWidget(self._msg_input)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = PushButton("取消", self)
        cancel_btn.clicked.connect(self.reject)
        ok_btn = PrimaryPushButton("确定", self)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

        self._on_mode_changed("single")

    def _on_mode_changed(self, mode: str):
        self._current_mode = mode
        idx = {"single": 0, "daily": 1, "cycle": 2}[mode]
        self._config_stack.setCurrentIndex(idx)

    def _build_single_panel(self) -> QFrame:
        panel = QFrame(self._config_card)
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(BodyLabel("倒计时", self._config_card))
        layout.addSpacing(8)
        self._single_picker = TimePicker(self._config_card, showSeconds=True)
        self._single_picker.setTime(QTime(0, 0, 10))
        layout.addWidget(self._single_picker)
        layout.addStretch()
        return panel

    def _build_daily_panel(self) -> QFrame:
        panel = QFrame(self._config_card)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        time_row = QHBoxLayout()
        time_row.addWidget(BodyLabel("触发时间", self._config_card))
        time_row.addSpacing(8)
        self._daily_picker = TimePicker(self._config_card)
        self._daily_picker.setTime(QTime(9, 0))
        time_row.addWidget(self._daily_picker)
        time_row.addStretch()
        layout.addLayout(time_row)

        day_row = QHBoxLayout()
        day_row.setSpacing(4)
        self._daily_days = {}
        for i, name in enumerate(WEEKDAY_NAMES):
            cb = CheckBox(name, self._config_card)
            if i < 5:
                cb.setChecked(True)
            day_row.addWidget(cb)
            self._daily_days[i] = cb
        day_row.addStretch()
        layout.addLayout(day_row)
        return panel

    def _build_cycle_panel(self) -> QFrame:
        panel = QFrame(self._config_card)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        sr = QHBoxLayout()
        sr.addWidget(BodyLabel("开始时间", self._config_card))
        sr.addSpacing(8)
        self._cycle_start = TimePicker(self._config_card)
        self._cycle_start.setTime(QTime(8, 0))
        sr.addWidget(self._cycle_start)
        sr.addStretch()
        layout.addLayout(sr)

        er = QHBoxLayout()
        er.addWidget(BodyLabel("结束时间", self._config_card))
        er.addSpacing(8)
        self._cycle_end = TimePicker(self._config_card)
        self._cycle_end.setTime(QTime(22, 0))
        er.addWidget(self._cycle_end)
        er.addStretch()
        layout.addLayout(er)

        ir = QHBoxLayout()
        ir.addWidget(BodyLabel("间隔时间", self._config_card))
        ir.addSpacing(8)
        self._cycle_iv = SpinBox(self._config_card)
        self._cycle_iv.setRange(1, 999)
        self._cycle_iv.setValue(60)
        self._cycle_iv.setSuffix(" 分钟")
        ir.addWidget(self._cycle_iv)
        ir.addStretch()
        layout.addLayout(ir)

        day_row = QHBoxLayout()
        day_row.setSpacing(4)
        self._cycle_days = {}
        for i, name in enumerate(WEEKDAY_NAMES):
            cb = CheckBox(name, self._config_card)
            if i < 5:
                cb.setChecked(True)
            day_row.addWidget(cb)
            self._cycle_days[i] = cb
        day_row.addStretch()
        layout.addLayout(day_row)
        return panel

    def _load_data(self, data: AlarmData):
        self._segment.setCurrentItem(data.mode)
        self._msg_input.setText(data.message)
        if data.mode == "single":
            self._single_picker.setTime(QTime(0, data.countdown_seconds // 60, data.countdown_seconds % 60))
        elif data.mode == "daily":
            self._daily_picker.setTime(QTime(data.hour, data.minute))
            for i in self._daily_days:
                self._daily_days[i].setChecked(i in data.days_of_week)
        elif data.mode == "cycle":
            self._cycle_start.setTime(QTime(data.start_hour, data.start_minute))
            self._cycle_end.setTime(QTime(data.end_hour, data.end_minute))
            self._cycle_iv.setValue(data.interval_minutes)
            for i in self._cycle_days:
                self._cycle_days[i].setChecked(i in data.days_of_week)

    def get_alarm_data(self) -> AlarmData:
        data = AlarmData()
        if self._edit_data:
            data.alarm_id = self._edit_data.alarm_id
        data.message = self._msg_input.text() or "⏰ 时间到！"
        data.mode = self._current_mode
        if self._current_mode == "single":
            t = self._single_picker.time
            data.countdown_seconds = max(1, t.hour() * 3600 + t.minute() * 60 + t.second())
        elif self._current_mode == "daily":
            t = self._daily_picker.time
            data.hour = t.hour()
            data.minute = t.minute()
            data.days_of_week = [i for i, cb in self._daily_days.items() if cb.isChecked()]
            if not data.days_of_week:
                data.days_of_week = list(range(7))
        elif self._current_mode == "cycle":
            st = self._cycle_start.time
            et = self._cycle_end.time
            data.start_hour = st.hour()
            data.start_minute = st.minute()
            data.end_hour = et.hour()
            data.end_minute = et.minute()
            data.interval_minutes = self._cycle_iv.value()
            data.days_of_week = [i for i, cb in self._cycle_days.items() if cb.isChecked()]
            if not data.days_of_week:
                data.days_of_week = list(range(7))
            start_m = data.start_hour * 60 + data.start_minute
            end_m = data.end_hour * 60 + data.end_minute
            if end_m <= start_m:
                MessageBox.warning(self, "参数错误", "结束时间必须晚于开始时间")
                return None
        return data


# ── Alarm Item Widget ───────────────────────────────────────────


class AlarmItemWidget(CardWidget):
    """单个闹钟条目控件，管理独立的定时逻辑与闪烁状态"""

    FLASH_INTERVAL_MS = 40
    OPACITY_STEP = 0.06

    delete_requested = Signal(str)

    def __init__(self, overlay: SilentAlarmOverlay, alarm_data: AlarmData, parent=None):
        super().__init__(parent)
        self._overlay = overlay
        self._data = alarm_data
        self._alarm_id = alarm_data.alarm_id

        self._enabled = alarm_data.enabled
        self._flashing = False
        self._flash_opacity = 0.0
        self._flash_direction = 1
        self._active = False
        self._remaining_seconds = 0
        self._last_fire_date = None

        self._scheduler = QTimer(self)
        self._scheduler.setSingleShot(True)
        self._scheduler.timeout.connect(self._on_scheduler_tick)

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._on_tick_timer)

        self._flash_timer = QTimer(self)
        self._flash_timer.setInterval(self.FLASH_INTERVAL_MS)
        self._flash_timer.timeout.connect(self._on_widget_flash_tick)

        self._init_ui()

        if self._enabled:
            self._activate()

    # ── UI ──

    def _init_ui(self):
        self.setBorderRadius(8)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(12)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)

        self._title_label = BodyLabel(self._data.message, self)
        self._title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #e0e0e0;")
        info_layout.addWidget(self._title_label)

        self._desc_label = BodyLabel(self._data.display_description(), self)
        self._desc_label.setStyleSheet("font-size: 13px; color: #888888;")
        info_layout.addWidget(self._desc_label)

        self._status_label = BodyLabel("", self)
        self._status_label.setStyleSheet("font-size: 12px; color: #666666;")
        info_layout.addWidget(self._status_label)

        main_layout.addLayout(info_layout, 1)

        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)
        controls_layout.setAlignment(Qt.AlignCenter)

        self._dismiss_btn = DismissPillPushButton("停止闪烁", self)

        self._dismiss_btn.clicked.connect(self._on_dismiss)
        self._dismiss_btn.setVisible(False)
        controls_layout.addWidget(self._dismiss_btn)

        self._switch_label = BodyLabel("", self)
        controls_layout.addWidget(self._switch_label)

        self._switch = SwitchButton(self)
        self._switch.setOnText("")
        self._switch.setOffText("")
        self._switch.setChecked(self._enabled)
        self._switch.checkedChanged.connect(self._on_toggled)
        controls_layout.addWidget(self._switch)

        self._delete_btn = ToolButton(FluentIcon.DELETE, self)
        # self._delete_btn.setFixedSize(32, 32)
        self._delete_btn.setToolTip("删除此闹钟")
        self._delete_btn.clicked.connect(self._on_delete)
        controls_layout.addWidget(self._delete_btn)

        main_layout.addLayout(controls_layout)

        self._update_switch_label()

    def _update_switch_label(self):
        """更新启用/停用标签显示"""
        if self._enabled:
            self._switch_label.setText("已启用")
        else:
            self._switch_label.setText("已停用")


    def _update_info_display(self):
        self._title_label.setText(self._data.message)
        self._desc_label.setText(self._data.display_description())
        if self._flashing:
            self._status_label.setText("🔴 提醒中")
            self._status_label.setStyleSheet("font-size: 12px; color: #ff4444; font-weight: bold;")
        elif self._active:
            remaining = max(0, self._remaining_seconds)
            hours = remaining // 3600
            mins = (remaining % 3600) // 60
            secs = remaining % 60
            if hours > 0:
                self._status_label.setText(f"⏳ {hours:02d}:{mins:02d}:{secs:02d}")
            else:
                self._status_label.setText(f"⏳ {mins:02d}:{secs:02d}")
            self._status_label.setStyleSheet("font-size: 12px; color: #4CAF50;")
        else:
            self._status_label.setText("⏸ 已停用")
            self._status_label.setStyleSheet("font-size: 12px; color: #666666;")

    # ── Click to edit ──

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._on_edit()
        super().mousePressEvent(event)

    def _on_edit(self):
        dlg = AlarmConfigDialog(self.window(), edit_data=self._data)
        if dlg.exec() == QDialog.Accepted:
            new_data = dlg.get_alarm_data()
            if new_data is not None:
                was_enabled = self._enabled
                if was_enabled:
                    self._deactivate()
                new_data.alarm_id = self._alarm_id
                self._data = new_data
                self._update_info_display()
                if was_enabled:
                    self._activate()
                alarm_page = self._find_alarm_page()
                if alarm_page:
                    alarm_page._save_item_to_db(self)

    def _on_delete(self):
        w = MessageBox(f"确定要删除闹钟「{self._data.message}」吗？", "删除闹钟", self.parent())
        w.yesButton.setText("确认删除")
        w.cancelButton.setText("取消")
        if w.exec():
            self.delete_requested.emit(self._alarm_id)

    # ── Alarm lifecycle ──

    def _activate(self):
        if not self._enabled:
            return
        self._active = True
        self._last_fire_date = None
        if self._data.mode == "single":
            self._remaining_seconds = self._data.countdown_seconds
            self._scheduler.start(self._data.countdown_seconds * 1000)
            self._tick_timer.start()
        elif self._data.mode == "daily":
            self._schedule_next_daily()
            self._tick_timer.start()
        elif self._data.mode == "cycle":
            self._schedule_next_cycle()
            self._tick_timer.start()
        self._update_info_display()

    def _deactivate(self):
        self._active = False
        self._remaining_seconds = 0
        self._last_fire_date = None
        self._scheduler.stop()
        self._tick_timer.stop()
        self._stop_widget_flash()
        self._set_normal_style()
        self._update_info_display()

    def _on_toggled(self, checked: bool):
        self._enabled = checked
        self._update_switch_label()
        if self._flashing:
            self._overlay.stop_flash(self._alarm_id)
            self._stop_widget_flash()
        if checked:
            self._activate()
        else:
            self._deactivate()
        alarm_page = self._find_alarm_page()
        if alarm_page:
            alarm_page._save_item_to_db(self)

    def _find_alarm_page(self):
        p = self.parent()
        while p is not None:
            from ui.alarm_page import AlarmPage
            if isinstance(p, AlarmPage):
                return p
            p = p.parent()
        return None

    def _on_dismiss(self):
        self._overlay.stop_flash(self._alarm_id)
        self._stop_widget_flash()
        self._set_normal_style()
        if self._data.mode == "single":
            self._deactivate()
            self._enabled = False
            self._switch.setChecked(False)
        alarm_page = self._find_alarm_page()
        if alarm_page:
            alarm_page._save_item_to_db(self)

    # ── Scheduling (reuses overlay logic) ──

    def _schedule_next_daily(self):
        now = datetime.now()
        target = now.replace(hour=self._data.hour, minute=self._data.minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        if not SilentAlarmOverlay._is_day_allowed(target, self._data.days_of_week):
            target = SilentAlarmOverlay._next_allowed_day(target, self._data.days_of_week,
                                                          self._data.hour, self._data.minute)
        ms = int((target - now).total_seconds() * 1000)
        self._remaining_seconds = max(0, int((target - now).total_seconds()))
        self._scheduler.start(ms)

    def _schedule_next_cycle(self):
        now = datetime.now()
        d = self._data
        start = now.replace(hour=d.start_hour, minute=d.start_minute, second=0, microsecond=0)
        end = now.replace(hour=d.end_hour, minute=d.end_minute, second=0, microsecond=0)

        if self._last_fire_date is not None and self._last_fire_date.date() == now.date():
            nxt = self._last_fire_date + timedelta(minutes=d.interval_minutes)
            if nxt <= end and SilentAlarmOverlay._is_day_allowed(now, d.days_of_week):
                ms = int((nxt - now).total_seconds() * 1000)
                self._remaining_seconds = max(0, int((nxt - now).total_seconds()))
                self._scheduler.start(ms)
                return

        if now < start:
            nxt = start
        elif now > end:
            nxt = start + timedelta(days=1)
        else:
            if SilentAlarmOverlay._is_day_allowed(now, d.days_of_week):
                elapsed = (now - start).total_seconds()
                iv = d.interval_minutes * 60
                slots = int(elapsed // iv) + 1
                nxt = start + timedelta(seconds=slots * iv)
                if nxt <= end:
                    ms = int((nxt - now).total_seconds() * 1000)
                    self._remaining_seconds = max(0, int((nxt - now).total_seconds()))
                    self._scheduler.start(ms)
                    return
            nxt = start + timedelta(days=1)

        nxt = SilentAlarmOverlay._next_allowed_day(nxt, d.days_of_week, d.start_hour, d.start_minute)
        ms = int((nxt - now).total_seconds() * 1000)
        self._remaining_seconds = max(0, int((nxt - now).total_seconds()))
        self._scheduler.start(ms)

    def _on_scheduler_tick(self):
        self._remaining_seconds = 0
        self._last_fire_date = datetime.now()
        self._overlay.trigger_flash(self._alarm_id, self._data.message)
        self._start_widget_flash()

        if self._data.mode == "daily" and self._enabled:
            self._schedule_next_daily()
        elif self._data.mode == "cycle" and self._enabled:
            self._schedule_next_cycle()

    def _on_tick_timer(self):
        if self._active and not self._flashing:
            self._remaining_seconds = max(0, self._remaining_seconds - 1)
            self._update_info_display()

    # ── Widget flash animation ──

    def _start_widget_flash(self):
        self._flashing = True
        self._flash_opacity = 0.0
        self._flash_direction = 1
        self._dismiss_btn.setVisible(True)
        self._flash_timer.start()
        self._update_info_display()

    def _stop_widget_flash(self):
        self._flashing = False
        self._flash_timer.stop()
        self._dismiss_btn.setVisible(False)
        self._update_info_display()

    def _on_widget_flash_tick(self):
        self._flash_opacity += self.OPACITY_STEP * self._flash_direction
        if self._flash_opacity >= 1.0:
            self._flash_opacity = 1.0
            self._flash_direction = -1
        elif self._flash_opacity <= 0.0:
            self._flash_opacity = 0.0
            self._flash_direction = 1

        a = int(200 * self._flash_opacity)
        self.setStyleSheet(f"""
            AlarmItemWidget {{
                background-color: #252525;
                border: 3px solid rgba(255, 30, 30, {a});
            }}
        """)

    def _set_normal_style(self):
        """重置为正常样式，移除闪烁边框"""
        self.setStyleSheet("""
            AlarmItemWidget {
                background-color: #252525;
                border: none;
            }
        """)


# ── Alarm Page ──────────────────────────────────────────────────


class AlarmPage(QWidget):
    """无声闹钟页面"""

    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self._overlay = SilentAlarmOverlay()
        self._alarm_items = []
        self._init_ui()
        self._load_alarms_from_db()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        title = TitleLabel("无声闹钟", self)
        main_layout.addWidget(title)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._add_btn = PrimaryPushButton(FluentIcon.ADD, "添加闹钟", self)
        self._add_btn.clicked.connect(self._on_add_alarm)
        toolbar.addWidget(self._add_btn)

        self._clear_btn = PushButton(FluentIcon.DELETE, "清除所有", self)
        self._clear_btn.clicked.connect(self._on_clear_all)
        toolbar.addWidget(self._clear_btn)

        toolbar.addStretch()

        # 当前时间显示（紧挨测试闹钟按钮左侧）
        self._current_time_label = BodyLabel("", self)
        self._current_time_label.setStyleSheet("font-size: 14px; color: #4CAF50; font-weight: bold;")
        toolbar.addWidget(self._current_time_label)

        self._test_btn = PushButton(FluentIcon.PLAY, "测试闹钟", self)
        self._test_btn.clicked.connect(self._on_test_flash)
        toolbar.addWidget(self._test_btn)

        # 初始化时间更新定时器
        self._time_update_timer = QTimer(self)
        self._time_update_timer.setInterval(1000)
        self._time_update_timer.timeout.connect(self._update_current_time)
        self._time_update_timer.start()
        self._update_current_time()

        main_layout.addLayout(toolbar)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = ScrollArea(container)
        scroll.setWidgetResizable(True)

        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(8, 8, 16, 8)
        self._list_layout.setSpacing(6)
        self._list_layout.addStretch()

        scroll.setWidget(self._list_widget)
        layout.addWidget(scroll)
        main_layout.addWidget(container, 1)

        self._refresh_empty_state()

    def alarm_overlay(self) -> SilentAlarmOverlay:
        return self._overlay

    def _update_current_time(self):
        """更新当前时间显示"""
        now = datetime.now()
        time_str = now.strftime("%Y年%m月%d日 %H:%M:%S")
        self._current_time_label.setText(time_str)

    # ── Alarm management ──

    def _on_add_alarm(self):
        dlg = AlarmConfigDialog(self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_alarm_data()
            if data is not None:
                self._add_alarm_item(data)
                self._save_item_to_db(self._alarm_items[-1])

    def _add_alarm_item(self, data: AlarmData):
        item = AlarmItemWidget(self._overlay, data, self)
        item.delete_requested.connect(self._on_delete_item)
        self._alarm_items.append(item)
        self._list_layout.insertWidget(self._list_layout.count() - 1, item)
        self._refresh_empty_state()

    def _on_delete_item(self, alarm_id: str):
        for i, item in enumerate(self._alarm_items):
            if item._alarm_id == alarm_id:
                item._deactivate()
                self._list_layout.removeWidget(item)
                item.deleteLater()
                self._alarm_items.pop(i)
                break
        if self.main_window and self.main_window.db_manager:
            try:
                self.main_window.db_manager.delete_alarm_config(alarm_id)
            except Exception as e:
                log_manager.debug(f"删除闹钟配置失败: {e}")

    def _on_clear_all(self):
        if not self._alarm_items:
            return
        w = MessageBox("确定要删除所有闹钟吗？", "确认清除", self)
        w.yesButton.setText("确认")
        w.cancelButton.setText("取消")
        if not w.exec():
            return
        while self._alarm_items:
            item = self._alarm_items.pop()
            item._deactivate()
            self._list_layout.removeWidget(item)
            item.deleteLater()
        self._overlay.stop()
        self._refresh_empty_state()
        if self.main_window and self.main_window.db_manager:
            try:
                self.main_window.db_manager.delete_all_alarm_configs()
            except Exception as e:
                log_manager.debug(f"清除闹钟配置失败: {e}")

    def _on_test_flash(self):
        test_id = "__test__"
        self._overlay.trigger_flash(test_id, "测试闹钟")
        QTimer.singleShot(3000, lambda: self._overlay.stop_flash(test_id))

    def _refresh_empty_state(self):
        pass

    # ── Database persistence ──

    def _alarm_data_to_dict(self, data: AlarmData) -> dict:
        import json
        return {
            "alarm_id": data.alarm_id,
            "enabled": data.enabled,
            "mode": data.mode,
            "message": data.message,
            "countdown_seconds": data.countdown_seconds,
            "hour": data.hour,
            "minute": data.minute,
            "days_of_week": json.dumps(data.days_of_week),
            "start_hour": data.start_hour,
            "start_minute": data.start_minute,
            "end_hour": data.end_hour,
            "end_minute": data.end_minute,
            "interval_minutes": data.interval_minutes,
        }

    def _save_item_to_db(self, item) -> None:
        if not self.main_window or not self.main_window.db_manager:
            return
        try:
            d = self._alarm_data_to_dict(item._data)
            d["enabled"] = item._enabled
            self.main_window.db_manager.save_alarm_config(d)
        except Exception as e:
            log_manager.debug(f"保存闹钟配置失败: {e}")

    def _load_alarms_from_db(self) -> None:
        import json
        if not self.main_window or not self.main_window.db_manager:
            return
        try:
            configs = self.main_window.db_manager.get_all_alarm_configs()
            for cfg in configs:
                days_of_week = json.loads(cfg.days_of_week) if cfg.days_of_week else []
                data = AlarmData(
                    alarm_id=cfg.alarm_id,
                    enabled=cfg.enabled,
                    mode=cfg.mode,
                    message=cfg.message,
                    countdown_seconds=cfg.countdown_seconds,
                    hour=cfg.hour,
                    minute=cfg.minute,
                    days_of_week=days_of_week,
                    start_hour=cfg.start_hour,
                    start_minute=cfg.start_minute,
                    end_hour=cfg.end_hour,
                    end_minute=cfg.end_minute,
                    interval_minutes=cfg.interval_minutes,
                )
                self._add_alarm_item(data)
        except Exception as e:
            log_manager.debug(f"加载闹钟配置失败: {e}")

    def closeEvent(self, event):
        self._overlay.stop()
        for item in self._alarm_items:
            item._deactivate()
        super().closeEvent(event)


def run_demo():
    import sys
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    page = AlarmPage()
    page.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_demo()