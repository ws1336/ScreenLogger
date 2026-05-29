"""
无声闹钟 - 屏幕边框闪烁提醒组件
通过透明、可穿透的覆盖层，在定时到达后于屏幕边框闪烁红色脉冲，
同时屏幕中央显示巨大的自定义提醒文字。

支持三种定时模式（参考小米智能插座）：
  - 单次定时：倒计时，到期触发一次
  - 每日定时：指定时刻触发，可设置生效星期
  - 循环定时：指定时间窗口+间隔重复，可设置生效星期
"""
import sys
from datetime import datetime, timedelta

from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, QTimer, Signal, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QFontMetricsF, QLinearGradient


WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
WEEKDAY_SHORT = ["一", "二", "三", "四", "五", "六", "日"]


class SilentAlarmOverlay(QWidget):
    """
    无声闹钟覆盖层

    全屏透明窗口，鼠标事件穿透，不影响用户操作。
    支持单次/每日/循环三种定时模式。
    定时到达后屏幕四周边框脉冲闪烁红色 + 中央巨大提醒文字。
    """
    alarm_triggered = Signal()
    alarm_stopped = Signal()
    flash_dismissed = Signal()

    FLASH_INTERVAL_MS = 40
    OPACITY_STEP = 0.06

    MODE_SINGLE = "single"
    MODE_DAILY = "daily"
    MODE_CYCLE = "cycle"

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_QuitOnClose, False)

        self._apply_click_through()

        self._flash_opacity = 0.0
        self._flash_direction = 1
        self._is_flashing = False
        self._active_alarm_ids = set()

        self._message = "⏰ 时间到！"

        self._flash_timer = QTimer(self)
        self._flash_timer.setInterval(self.FLASH_INTERVAL_MS)
        self._flash_timer.timeout.connect(self._on_flash_tick)

        self._mode = self.MODE_SINGLE
        self._config = {}
        self._active = False
        self._remaining_seconds = 0
        self._last_fire_date = None

        self._scheduler = QTimer(self)
        self._scheduler.setSingleShot(True)
        self._scheduler.timeout.connect(self._on_scheduler_tick)

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._on_tick_timer)

        self._update_geometry()

    def _apply_click_through(self):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes
            WS_EX_TRANSPARENT = 0x00000020
            GWL_EXSTYLE = -20
            hwnd = int(self.winId())
            current = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, current | WS_EX_TRANSPARENT)
        except Exception:
            pass

    # ── Public API ──────────────────────────────────────────────

    def set_message(self, text: str):
        self._message = text[:10] if text else ""

    def trigger_flash(self, alarm_id: str, message: str = ""):
        self._active_alarm_ids.add(alarm_id)
        if message:
            self.set_message(message)
        if not self._is_flashing:
            self._show_overlay()
        self.alarm_triggered.emit()

    def stop_flash(self, alarm_id: str):
        self._active_alarm_ids.discard(alarm_id)
        if not self._active_alarm_ids:
            self._hide_overlay()

    def set_single(self, seconds: int, message: str = ""):
        self.stop()
        self._mode = self.MODE_SINGLE
        self._config = {"seconds": seconds}
        if message:
            self.set_message(message)
        self._remaining_seconds = seconds
        self._active = True
        self._scheduler.start(seconds * 1000)
        self._tick_timer.start()

    def set_daily(self, hour: int, minute: int, days_of_week: list, message: str = ""):
        self.stop()
        self._mode = self.MODE_DAILY
        self._config = {"hour": hour, "minute": minute, "days": days_of_week}
        if message:
            self.set_message(message)
        self._active = True
        self._last_fire_date = None
        self._schedule_next_daily()
        self._tick_timer.start()

    def set_cycle(self, start_hour: int, start_minute: int,
                  end_hour: int, end_minute: int,
                  interval_minutes: int, days_of_week: list,
                  message: str = ""):
        self.stop()
        self._mode = self.MODE_CYCLE
        self._config = {
            "start_hour": start_hour, "start_minute": start_minute,
            "end_hour": end_hour, "end_minute": end_minute,
            "interval_minutes": interval_minutes,
            "days": days_of_week,
        }
        if message:
            self.set_message(message)
        self._active = True
        self._last_fire_date = None
        self._schedule_next_cycle()
        self._tick_timer.start()

    def stop(self):
        self._scheduler.stop()
        self._tick_timer.stop()
        self._active = False
        self._remaining_seconds = 0
        self._last_fire_date = None
        self._active_alarm_ids.clear()
        self._hide_overlay()

    def dismiss(self):
        self._active_alarm_ids.clear()
        self._hide_overlay()
        self.flash_dismissed.emit()

    def is_active(self) -> bool:
        return self._active or self._is_flashing

    def mode(self) -> str:
        return self._mode

    def config(self) -> dict:
        return dict(self._config)

    def remaining_seconds(self) -> int:
        return max(0, self._remaining_seconds)

    def status_description(self) -> str:
        if self._is_flashing:
            return "提醒中"
        if not self._active:
            return "空闲"
        if self._mode == self.MODE_SINGLE:
            return f"剩余 {self._remaining_seconds} 秒"
        elif self._mode == self.MODE_DAILY:
            c = self._config
            days_str = self._days_to_str(c["days"])
            return f"每日 {c['hour']:02d}:{c['minute']:02d} ({days_str})"
        elif self._mode == self.MODE_CYCLE:
            c = self._config
            days_str = self._days_to_str(c["days"])
            return (f"循环 {c['start_hour']:02d}:{c['start_minute']:02d}"
                    f"~{c['end_hour']:02d}:{c['end_minute']:02d}"
                    f" 每{c['interval_minutes']}分 ({days_str})")
        return ""

    # ── Scheduling ──────────────────────────────────────────────

    def _schedule_next_daily(self):
        now = datetime.now()
        cfg = self._config
        target = now.replace(hour=cfg["hour"], minute=cfg["minute"], second=0, microsecond=0)

        if target <= now:
            target += timedelta(days=1)

        if not self._is_day_allowed(target, cfg["days"]):
            target = self._next_allowed_day(target, cfg["days"], cfg["hour"], cfg["minute"])

        ms_until = int((target - now).total_seconds() * 1000)
        self._remaining_seconds = int((target - now).total_seconds())
        self._scheduler.start(ms_until)

    def _schedule_next_cycle(self):
        now = datetime.now()
        cfg = self._config

        start = now.replace(hour=cfg["start_hour"], minute=cfg["start_minute"], second=0, microsecond=0)
        end = now.replace(hour=cfg["end_hour"], minute=cfg["end_minute"], second=0, microsecond=0)

        if self._last_fire_date is not None and self._last_fire_date.date() == now.date():
            last = self._last_fire_date
            next_fire = last + timedelta(minutes=cfg["interval_minutes"])
            if next_fire <= end:
                if self._is_day_allowed(now, cfg["days"]):
                    ms_until = int((next_fire - now).total_seconds() * 1000)
                    self._remaining_seconds = max(0, int((next_fire - now).total_seconds()))
                    self._scheduler.start(ms_until)
                    return

        if now < start:
            next_start = start
        elif now > end:
            next_start = start + timedelta(days=1)
        else:
            if self._is_day_allowed(now, cfg["days"]):
                elapsed = (now - start).total_seconds()
                interval_s = cfg["interval_minutes"] * 60
                slots = int(elapsed // interval_s) + 1
                next_fire = start + timedelta(seconds=slots * interval_s)
                if next_fire <= end:
                    ms_until = int((next_fire - now).total_seconds() * 1000)
                    self._remaining_seconds = max(0, int((next_fire - now).total_seconds()))
                    self._scheduler.start(ms_until)
                    return
            next_start = start + timedelta(days=1)

        next_start = self._next_allowed_day(next_start, cfg["days"],
                                            cfg["start_hour"], cfg["start_minute"])
        ms_until = int((next_start - now).total_seconds() * 1000)
        self._remaining_seconds = max(0, int((next_start - now).total_seconds()))
        self._scheduler.start(ms_until)

    def _on_scheduler_tick(self):
        self._remaining_seconds = 0
        self._last_fire_date = datetime.now()
        self._show_overlay()
        self.alarm_triggered.emit()

        if self._mode == self.MODE_DAILY and self._active:
            self._schedule_next_daily()
        elif self._mode == self.MODE_CYCLE and self._active:
            self._schedule_next_cycle()

    def _on_tick_timer(self):
        if self._active and not self._is_flashing:
            self._remaining_seconds = max(0, self._remaining_seconds - 1)

    @staticmethod
    def _is_day_allowed(dt: datetime, days: list) -> bool:
        wd = dt.weekday()
        return wd in days

    @staticmethod
    def _next_allowed_day(dt: datetime, days: list, hour: int, minute: int) -> datetime:
        candidate = dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
        for _ in range(8):
            if SilentAlarmOverlay._is_day_allowed(candidate, days):
                if candidate > dt:
                    return candidate
            candidate += timedelta(days=1)
        return candidate

    @staticmethod
    def _days_to_str(days: list) -> str:
        if not days:
            return "从不"
        if len(days) == 7:
            return "每天"
        if days == list(range(5)):
            return "工作日"
        if days == [5, 6]:
            return "周末"
        parts = [WEEKDAY_SHORT[d] for d in sorted(days)]
        return " ".join(parts)

    # ── Flash control ───────────────────────────────────────────

    def _show_overlay(self):
        if self._is_flashing:
            return
        self._is_flashing = True
        self._flash_opacity = 0.0
        self._flash_direction = 1
        self._update_geometry()
        self.showFullScreen()
        self.raise_()
        self._apply_click_through()
        self._flash_timer.start()

    def _hide_overlay(self):
        self._is_flashing = False
        self._flash_timer.stop()
        self.hide()
        self.alarm_stopped.emit()

    def _on_flash_tick(self):
        self._flash_opacity += self.OPACITY_STEP * self._flash_direction
        if self._flash_opacity >= 1.0:
            self._flash_opacity = 1.0
            self._flash_direction = -1
        elif self._flash_opacity <= 0.0:
            self._flash_opacity = 0.0
            self._flash_direction = 1
        self.update()

    def _update_geometry(self):
        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())

    # ── Painting ────────────────────────────────────────────────

    BORDER_WIDTH = 100

    def paintEvent(self, event):
        if not self._is_flashing:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self._draw_gradient_border(painter)
        self._draw_center_text(painter)

    def _draw_gradient_border(self, painter: QPainter):
        opacity = self._flash_opacity
        bw = self.BORDER_WIDTH
        w = self.width()
        h = self.height()

        def _fade_color(stop_ratio: float, base_alpha: int = 220) -> QColor:
            t = stop_ratio * stop_ratio
            a = int(base_alpha * opacity * (1.0 - t))
            return QColor(255, 30, 30, max(0, a))

        top_grad = QLinearGradient(0, 0, 0, bw)
        top_grad.setColorAt(0.0, _fade_color(0.0, 240))
        top_grad.setColorAt(0.4, _fade_color(0.4, 180))
        top_grad.setColorAt(0.7, _fade_color(0.7, 90))
        top_grad.setColorAt(1.0, _fade_color(1.0, 0))
        painter.fillRect(0, 0, w, bw, top_grad)

        bottom_grad = QLinearGradient(0, h - bw, 0, h)
        bottom_grad.setColorAt(0.0, _fade_color(1.0, 0))
        bottom_grad.setColorAt(0.3, _fade_color(0.7, 90))
        bottom_grad.setColorAt(0.6, _fade_color(0.4, 180))
        bottom_grad.setColorAt(1.0, _fade_color(0.0, 240))
        painter.fillRect(0, h - bw, w, bw, bottom_grad)

        left_grad = QLinearGradient(0, 0, bw, 0)
        left_grad.setColorAt(0.0, _fade_color(0.0, 240))
        left_grad.setColorAt(0.4, _fade_color(0.4, 180))
        left_grad.setColorAt(0.7, _fade_color(0.7, 90))
        left_grad.setColorAt(1.0, _fade_color(1.0, 0))
        painter.fillRect(0, 0, bw, h, left_grad)

        right_grad = QLinearGradient(w - bw, 0, w, 0)
        right_grad.setColorAt(0.0, _fade_color(1.0, 0))
        right_grad.setColorAt(0.3, _fade_color(0.7, 90))
        right_grad.setColorAt(0.6, _fade_color(0.4, 180))
        right_grad.setColorAt(1.0, _fade_color(0.0, 240))
        painter.fillRect(w - bw, 0, bw, h, right_grad)

    def _draw_center_text(self, painter: QPainter):
        opacity = self._flash_opacity
        if not self._message or opacity < 0.05:
            return

        text = self._message
        w = self.width()
        h = self.height()

        font_size = int(min(w, h) * 0.12)
        font_size = max(36, min(font_size, 160))

        text_font = QFont("Microsoft YaHei UI", font_size, QFont.Weight.Bold)
        painter.setFont(text_font)

        fm = QFontMetricsF(text_font)
        text_w = fm.horizontalAdvance(text)
        text_h = fm.height()
        padding = 40
        bg_w = text_w + padding * 2
        bg_h = text_h + padding * 0.8
        cx = w / 2
        cy = h / 2

        bg_rect = QRectF(cx - bg_w / 2, cy - bg_h / 2, bg_w, bg_h)

        bg_color = QColor(0, 0, 0, int(140 * opacity))
        painter.setBrush(bg_color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(bg_rect, 16, 16)

        border_alpha = int(180 * opacity)
        border_pen = QPen(QColor(255, 40, 40, border_alpha), 3)
        painter.setPen(border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(bg_rect, 16, 16)

        text_color = QColor(255, 50, 50, int(255 * opacity))
        painter.setPen(text_color)
        painter.setBrush(Qt.NoBrush)
        painter.drawText(bg_rect, Qt.AlignCenter, text)

        shadow_color = QColor(255, 200, 200, int(60 * opacity))
        painter.setPen(shadow_color)
        shadow_rect = bg_rect.adjusted(2, 2, 2, 2)
        painter.drawText(shadow_rect, Qt.AlignCenter, text)
