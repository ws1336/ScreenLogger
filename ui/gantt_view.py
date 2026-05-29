"""
甘特图视图组件 - 基于QGraphicsView重构，实现更完善的交互与美观度
Y轴：活动类型
X轴：时间线
"""
from datetime import datetime
from typing import List, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGraphicsView, QGraphicsScene,
    QGraphicsObject, QToolTip
)
from PySide6.QtCore import (
    Qt, QRectF, Signal, QPointF
)
from PySide6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QFontMetrics,
    QLinearGradient, QPainterPath, QWheelEvent
)

from logger import log_manager


class ActivityBlockItem(QGraphicsObject):
    """甘特图活动块图形项 - 支持悬停、选中、渐变填充和阴影效果"""
    clicked = Signal(dict)

    def __init__(self, activity: dict, rect: QRectF, color: QColor, parent=None):
        super().__init__(parent)
        self._activity = activity
        self._rect = rect
        self._color = color
        self._is_hovered = False

        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def boundingRect(self):
        return self._rect.adjusted(-6, -3, 6, 3)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self._rect
        margin = 3
        radius = 3

        body_rect = QRectF(rect.x() + margin, rect.y() + margin,
                           rect.width() - margin * 2, rect.height() - margin * 2)

        if body_rect.height() <= 0:
            return

        # 阴影偏移
        shadow_offset = 1 if not self._is_hovered else 2
        shadow_rect = QRectF(body_rect.x() + shadow_offset, body_rect.y() + shadow_offset,
                             body_rect.width(), body_rect.height())

        # 绘制阴影
        painter.setPen(Qt.PenStyle.NoPen)
        shadow_color = QColor(0, 0, 0, 50 if not self._is_hovered else 70)
        painter.setBrush(shadow_color)
        painter.drawRoundedRect(shadow_rect, radius, radius)

        # 主体渐变填充
        if self._is_hovered:
            gradient = QLinearGradient(body_rect.topLeft(), body_rect.bottomLeft())
            gradient.setColorAt(0, self._color.lighter(140))
            gradient.setColorAt(1, self._color.lighter(115))
            painter.setBrush(QBrush(gradient))
            painter.setPen(QPen(self._color.lighter(130), 2))
        else:
            gradient = QLinearGradient(body_rect.topLeft(), body_rect.bottomLeft())
            gradient.setColorAt(0, self._color)
            gradient.setColorAt(1, self._color.darker(115))
            painter.setBrush(QBrush(gradient))
            painter.setPen(QPen(self._color.darker(120), 1))

        painter.drawRoundedRect(body_rect, radius, radius)

        # 顶部高光线（增加立体感）
        highlight_rect = QRectF(body_rect.x() + 3, body_rect.y() + 1,
                                body_rect.width() - 6, body_rect.height() * 0.45)
        if highlight_rect.height() > 4 and highlight_rect.width() > 10:
            h_gradient = QLinearGradient(highlight_rect.topLeft(), highlight_rect.bottomLeft())
            h_gradient.setColorAt(0, QColor(255, 255, 255, 50))
            h_gradient.setColorAt(1, QColor(255, 255, 255, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(h_gradient))
            clip_path = QPainterPath()
            clip_path.addRoundedRect(body_rect, radius, radius)
            painter.setClipPath(clip_path)
            painter.drawRect(highlight_rect)
            painter.setClipping(False)

        # 绘制文字
        text_width = body_rect.width() - 18
        if text_width > 40:
            painter.setPen(QColor("#ffffff"))
            font = QFont()
            font.setPixelSize(11)
            font.setBold(True)
            painter.setFont(font)

            name = self._activity.get("activity_type", "")
            metrics = QFontMetrics(font)
            elided = metrics.elidedText(name, Qt.TextElideMode.ElideRight, int(text_width))
            painter.drawText(body_rect.adjusted(10, 0, -8, 0),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)

    def hoverEnterEvent(self, event):
        self._is_hovered = True
        self._show_tooltip()
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._is_hovered = False
        QToolTip.hideText()
        self.update()
        super().hoverLeaveEvent(event)

    def hoverMoveEvent(self, event):
        self._show_tooltip()
        super().hoverMoveEvent(event)

    def _show_tooltip(self):
        start = self._activity.get("start_time", "")
        end = self._activity.get("end_time", "")
        start_str = start.strftime("%H:%M") if hasattr(start, "strftime") else str(start)
        end_str = end.strftime("%H:%M") if hasattr(end, "strftime") else str(end)
        title = self._activity.get("window_title", "")
        tooltip_lines = [
            f"<b>{self._activity.get('activity_type', '未知')}</b>",
            f"⏱ {start_str} - {end_str}",
        ]
        if title:
            tooltip_lines.append(f"📄 {title}")
        view = self.scene().views()[0] if self.scene() and self.scene().views() else None
        if view:
            QToolTip.showText(self.cursor().pos(), "<br>".join(tooltip_lines), view)

    def activity_data(self) -> dict:
        return self._activity


class GridLinesItem(QGraphicsObject):
    """网格线与行背景项"""
    def __init__(self, total_width: float, total_height: float, chart_x: float,
                 row_height: float, hour_width: float, start_hour: int,
                 num_hours: int, num_rows: int, margin_top: float, parent=None):
        super().__init__(parent)
        self._total_width = total_width
        self._total_height = total_height
        self._chart_x = chart_x
        self._row_height = row_height
        self._hour_width = hour_width
        self._start_hour = start_hour
        self._num_hours = num_hours
        self._num_rows = num_rows
        self._margin_top = margin_top

    def boundingRect(self):
        return QRectF(0, 0, self._total_width, self._total_height)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        chart_right = self._chart_x + self._num_hours * self._hour_width
        top = self._margin_top
        content_height = self._num_rows * self._row_height

        # 交替行背景
        for i in range(self._num_rows):
            y = top + i * self._row_height
            color = QColor("#242424") if i % 2 == 0 else QColor("#1e1e1e")
            painter.fillRect(QRectF(self._chart_x, y, chart_right - self._chart_x, self._row_height), color)

        # 活动类型标签区域背景
        painter.fillRect(QRectF(0, top, self._chart_x, content_height), QColor("#1c1c1c"))

        # 水平网格线
        painter.setPen(QPen(QColor("#333333"), 1))
        for i in range(self._num_rows + 1):
            y = top + i * self._row_height
            painter.drawLine(QPointF(self._chart_x, y), QPointF(chart_right, y))

        # 垂直小时线
        for i in range(self._num_hours + 1):
            x = self._chart_x + i * self._hour_width
            line_color = QColor("#3a3a3a") if i == 0 else QColor("#2a2a2a")
            painter.setPen(QPen(line_color, 1))
            painter.drawLine(QPointF(x, top), QPointF(x, top + content_height))

        # 半小时刻度虚线
        painter.setPen(QPen(QColor("#222222"), 1, Qt.PenStyle.DashLine))
        for i in range(self._num_hours):
            x = self._chart_x + i * self._hour_width + self._hour_width / 2
            painter.drawLine(QPointF(x, top), QPointF(x, top + content_height))


class TimeAxisItem(QGraphicsObject):
    """顶部时间轴刻度项"""
    def __init__(self, total_width: float, height: float, chart_x: float,
                 start_hour: int, end_hour: int, hour_width: float, parent=None):
        super().__init__(parent)
        self._total_width = total_width
        self._height = height
        self._chart_x = chart_x
        self._start_hour = start_hour
        self._end_hour = end_hour
        self._hour_width = hour_width
        self._num_rows = 0

    def boundingRect(self):
        return QRectF(0, 0, self._total_width, self._height)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 背景
        painter.fillRect(QRectF(0, 0, self._total_width, self._height), QColor("#282828"))

        # 底部边框线
        painter.setPen(QPen(QColor("#3c3c3c"), 1))
        painter.drawLine(QPointF(0, self._height), QPointF(self._total_width, self._height))

        # 左侧标签区域分隔线
        painter.drawLine(QPointF(self._chart_x, 0), QPointF(self._chart_x, self._height))

        # 行标题"时间"
        font = QFont()
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#aaaaaa"))
        painter.drawText(QRectF(0, 0, self._chart_x, self._height),
                         Qt.AlignmentFlag.AlignCenter, "时间")

        # 绘制小时刻度
        hour_font = QFont()
        hour_font.setPixelSize(11)
        painter.setFont(hour_font)
        num_hours = self._end_hour - self._start_hour

        for i in range(num_hours + 1):
            x = self._chart_x + i * self._hour_width
            hour = self._start_hour + i
            time_str = str(hour)

            # 主刻度线
            painter.setPen(QPen(QColor("#555555"), 1))
            painter.drawLine(QPointF(x, self._height - 10), QPointF(x, self._height))

            # 时间标签（居中对齐于网格线）
            painter.setPen(QColor("#aaaaaa"))
            text_rect = QRectF(x - self._hour_width / 2, 6, self._hour_width, self._height - 16)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, time_str)


class ActivityTypeLabelItem(QGraphicsObject):
    """左侧活动类型标签项"""
    def __init__(self, label: str, rect: QRectF, color: QColor, parent=None):
        super().__init__(parent)
        self._label = label
        self._rect = rect
        self._color = color

    def boundingRect(self):
        return self._rect

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 颜色指示圆点
        dot_center = QPointF(14, self._rect.center().y())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(dot_center, 5, 5)

        # 圆点发光
        glow_color = QColor(self._color)
        glow_color.setAlpha(40)
        painter.setBrush(glow_color)
        painter.drawEllipse(dot_center, 9, 9)

        # 标签文字
        painter.setPen(QColor("#d0d0d0"))
        font = QFont()
        font.setPixelSize(12)
        font.setBold(True)
        painter.setFont(font)
        text_rect = self._rect.adjusted(26, 0, -4, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._label)


class CurrentTimeLine(QGraphicsObject):
    """当前时间指示线（红色竖线）"""
    def __init__(self, total_height: float, x: float, parent=None):
        super().__init__(parent)
        self._total_height = total_height
        self._line_x = x

    def set_position(self, x: float):
        self._line_x = x
        self.update()

    def boundingRect(self):
        return QRectF(self._line_x - 8, -8, 16, self._total_height + 8)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 发光背景光晕
        glow_color = QColor("#ff6b6b")
        glow_color.setAlpha(30)
        painter.fillRect(QRectF(self._line_x - 8, 0, 16, self._total_height), glow_color)

        # 主线
        painter.setPen(QPen(QColor("#ff6b6b"), 2))
        painter.drawLine(QPointF(self._line_x, 0), QPointF(self._line_x, self._total_height))

        # 顶部三角指针
        tri_path = QPainterPath()
        tri_path.moveTo(self._line_x, -6)
        tri_path.lineTo(self._line_x - 5, 2)
        tri_path.lineTo(self._line_x + 5, 2)
        tri_path.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ff6b6b"))
        painter.drawPath(tri_path)


class GanttScene(QGraphicsScene):
    """甘特图场景 - 管理所有图形项及布局计算"""

    # 布局参数
    LABEL_WIDTH = 130
    ROW_HEIGHT = 46
    MARGIN_LEFT = 0
    MARGIN_TOP = 38
    MARGIN_RIGHT = 10
    MARGIN_BOTTOM = 10
    HOUR_WIDTH = 80
    START_HOUR = 8
    END_HOUR = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self._activities: List[Dict] = []
        self._activity_types: List[str] = []
        self._activity_colors: Dict[str, QColor] = {}
        self._current_date = None
        self._zoom = 1.0

        self._items: Dict = {}

    def set_date(self, date):
        self._current_date = date

    def set_zoom(self, zoom: float):
        self._zoom = max(0.3, min(3.0, zoom))

    def set_activities(self, activities: List[Dict]):
        self._activities = activities
        self._update_activity_types()
        self._rebuild_scene()

    def _update_activity_types(self):
        type_set = set()
        color_map = {}

        for activity in self._activities:
            act_type = activity.get("activity_type", "未分类")
            if not act_type or act_type == "未知":
                act_type = "未分类"
            type_set.add(act_type)

            if "color" in activity:
                color_map[act_type] = activity["color"]

        self._activity_types = sorted(list(type_set))

        default_colors = [
            "#3498db", "#e74c3c", "#2ecc71", "#f39c12",
            "#9b59b6", "#1abc9c", "#e67e22", "#34495e",
            "#16a085", "#c0392b", "#27ae60", "#d35400",
            "#2980b9", "#8e44ad", "#27ae60", "#d35400",
        ]

        for i, act_type in enumerate(self._activity_types):
            if act_type not in color_map:
                color_map[act_type] = default_colors[i % len(default_colors)]

        self._activity_colors = {k: QColor(v) for k, v in color_map.items()}

    def _rebuild_scene(self):
        self.clear()
        self._items.clear()

        num_types = len(self._activity_types)
        total_hours = self.END_HOUR - self.START_HOUR
        hour_width = self.HOUR_WIDTH * self._zoom
        chart_width = total_hours * hour_width
        chart_x = self.LABEL_WIDTH
        total_width = chart_x + chart_width + self.MARGIN_RIGHT
        total_height = self.MARGIN_TOP + num_types * self.ROW_HEIGHT + self.MARGIN_BOTTOM

        log_manager.debug(
            f"甘特图: _rebuild_scene  num_types={num_types} total_activities={len(self._activities)} "
            f"total_width={total_width:.0f} total_height={total_height:.0f} zoom={self._zoom}"
        )

        if num_types == 0:
            return

        self.setSceneRect(0, 0, total_width, total_height)

        content_height = num_types * self.ROW_HEIGHT

        # 网格线
        grid = GridLinesItem(total_width, total_height, chart_x,
                             self.ROW_HEIGHT, hour_width, self.START_HOUR,
                             total_hours, num_types, self.MARGIN_TOP)
        grid.setZValue(0)
        self.addItem(grid)
        self._items["grid"] = grid

        # 时间轴
        time_axis = TimeAxisItem(total_width, self.MARGIN_TOP, chart_x,
                                 self.START_HOUR, self.END_HOUR, hour_width)
        time_axis.setZValue(10)
        self.addItem(time_axis)
        self._items["time_axis"] = time_axis

        # 活动类型标签
        for i, act_type in enumerate(self._activity_types):
            label_rect = QRectF(0, self.MARGIN_TOP + i * self.ROW_HEIGHT,
                                self.LABEL_WIDTH, self.ROW_HEIGHT)
            color = self._activity_colors.get(act_type, QColor("#3498db"))
            label_item = ActivityTypeLabelItem(act_type, label_rect, color)
            label_item.setZValue(11)
            self.addItem(label_item)

        # 活动块
        for activity in self._activities:
            start = activity.get("start_time", "")
            end = activity.get("end_time", "")
            act_type = activity.get("activity_type", "未分类")

            if not hasattr(start, "hour") or not hasattr(end, "hour"):
                continue

            x1 = self._time_to_x(start, chart_x, hour_width)
            x2 = self._time_to_x(end, chart_x, hour_width)
            y = self._activity_type_to_y(act_type)

            rect = QRectF(x1 - 3, y, max(x2 - x1, 2) + 6, self.ROW_HEIGHT)
            color = self._activity_colors.get(act_type, QColor("#3498db"))

            block = ActivityBlockItem(activity, rect, color)
            block.setZValue(5)
            block.clicked.connect(self._on_block_clicked)
            self.addItem(block)

        # 当前时间线
        if self._current_date is not None:
            now = datetime.now()
            if (hasattr(self._current_date, "date") and
                self._current_date.date() == now.date()):
                is_today = True
            elif hasattr(self._current_date, "year"):
                is_today = (self._current_date == now.date())
            else:
                is_today = False

            if is_today:
                time_x = self._time_to_x(now, chart_x, hour_width)
                current_line = CurrentTimeLine(content_height, time_x)
                current_line.setZValue(6)
                self.addItem(current_line)

    def _time_to_x(self, time: datetime, chart_x: float, hour_width: float) -> float:
        hour = time.hour if hasattr(time, "hour") else self.START_HOUR
        minute = time.minute if hasattr(time, "minute") else 0

        if hour < self.START_HOUR:
            hour = self.START_HOUR
            minute = 0
        if hour > self.END_HOUR:
            hour = self.END_HOUR
            minute = 0

        offset_hours = (hour - self.START_HOUR) + minute / 60.0
        return chart_x + offset_hours * hour_width

    def _activity_type_to_y(self, activity_type: str) -> float:
        if activity_type not in self._activity_types:
            return self.MARGIN_TOP
        index = self._activity_types.index(activity_type)
        return self.MARGIN_TOP + index * self.ROW_HEIGHT

    def _on_block_clicked(self, activity_data: dict):
        log_manager.debug(f"甘特图活动块被点击: {activity_data.get('activity_type', '')}")
        self.parent()._on_activity_clicked(activity_data)


class GanttGraphicsView(QGraphicsView):
    """甘特图视图 - 处理缩放、平移和交互"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = GanttScene(self)
        self.setScene(self._scene)

        # 视图设置
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setInteractive(True)

        # 滚动条
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # 样式
        self.setStyleSheet("""
            QGraphicsView {
                background-color: #1e1e1e;
                border: none;
            }
            QScrollBar:horizontal {
                background-color: #2a2a2a;
                height: 12px;
            }
            QScrollBar::handle:horizontal {
                background-color: #555555;
                min-width: 30px;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #666666;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar:vertical {
                background-color: #2a2a2a;
                width: 12px;
            }
            QScrollBar::handle:vertical {
                background-color: #555555;
                min-height: 30px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #666666;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # 缩放状态
        self._current_zoom = 1.0
        self._pending_click_item = None
        self._press_pos = None

    def mousePressEvent(self, event):
        self._pending_click_item = None
        self._press_pos = None
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            if isinstance(item, ActivityBlockItem):
                self._pending_click_item = item
                self._press_pos = event.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self._pending_click_item and event.button() == Qt.MouseButton.LeftButton:
            drag_distance = (event.pos() - self._press_pos).manhattanLength() if self._press_pos else 0
            if drag_distance < 10:
                item = self._pending_click_item
                self._pending_click_item = None
                item.clicked.emit(item.activity_data())

    def wheelEvent(self, event: QWheelEvent):
        modifiers = event.modifiers()

        if modifiers == Qt.KeyboardModifier.ControlModifier:
            # Ctrl + 滚轮 → 缩放
            delta = event.angleDelta().y()
            zoom_factor = 1.1 if delta > 0 else 0.9
            new_zoom = self._current_zoom * zoom_factor
            if 0.3 <= new_zoom <= 3.0:
                self._current_zoom = new_zoom
                self.scale(zoom_factor, zoom_factor)
                self._scene.set_zoom(new_zoom)
        elif modifiers == Qt.KeyboardModifier.ShiftModifier:
            # Shift + 滚轮 → 水平滚动
            delta = event.angleDelta().y()
            h_bar = self.horizontalScrollBar()
            h_bar.setValue(h_bar.value() - delta)
        else:
            super().wheelEvent(event)

    def set_activities(self, activities: List[Dict]):
        self._scene.set_activities(activities)
        self._reset_view()

    def set_date(self, date):
        self._scene.set_date(date)

    def set_time_range(self, start_hour: int, end_hour: int):
        self._scene.START_HOUR = start_hour
        self._scene.END_HOUR = end_hour
        self._scene._rebuild_scene()
        self._reset_view()

    def set_zoom_level(self, zoom: float):
        zoom = max(0.3, min(3.0, zoom))
        scale_factor = zoom / self._current_zoom
        self._current_zoom = zoom
        self.scale(scale_factor, scale_factor)
        self._scene.set_zoom(zoom)

    def _reset_view(self):
        self.resetTransform()
        self._current_zoom = 1.0
        self._scene.set_zoom(1.0)

    def _on_activity_clicked(self, activity_data: dict):
        parent = self.parent()
        while parent and not hasattr(parent, 'activity_clicked'):
            parent = parent.parent()
        if parent and hasattr(parent, 'activity_clicked'):
            parent.activity_clicked.emit(activity_data)


class GanttViewWidget(QWidget):
    """
    甘特图视图组件（对外接口，保持与原API兼容）
    基于QGraphicsView实现，提供更完善的交互与美观度
    """
    activity_clicked = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._graphics_view = GanttGraphicsView(self)
        self._graphics_view._scene._on_block_clicked = self._on_block_clicked

        layout.addWidget(self._graphics_view)

    def _on_block_clicked(self, activity_data: dict):
        self.activity_clicked.emit(activity_data)

    def set_activities(self, activities: List[Dict]):
        self._graphics_view.set_activities(activities)

    def set_date(self, date):
        self._graphics_view.set_date(date)

    def set_time_range(self, start_hour: int, end_hour: int):
        self._graphics_view.set_time_range(start_hour, end_hour)

    def set_zoom(self, zoom: float):
        self._graphics_view.set_zoom_level(zoom)