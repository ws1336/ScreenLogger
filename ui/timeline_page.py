"""
活动时间线页面 - 以时间线形式展示每日活动记录
支持列表视图和甘特图视图切换
"""
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QDialog, QFormLayout, QStackedWidget, QSplitter
)
from PySide6.QtCore import Qt, QDate, QObject, Signal
from qfluentwidgets import (
    PrimaryPushButton, PushButton, FluentIcon,
    InfoBar, InfoBarPosition, CardWidget, BodyLabel, StrongBodyLabel,
    FastCalendarPicker, Pivot, ScrollArea, TextEdit
)

from logger import log_manager
from database.models import ActivityRecord
from ui.gantt_view import GanttViewWidget


class ActivityBlock(QFrame):
    """单个活动时间块组件，显示时间段、活动类型和窗口标题"""

    def __init__(self, activity_data, index, parent=None):
        super().__init__(parent)
        self.activity_data = activity_data
        self.index = index
        self._init_ui()

    def _init_ui(self):
        """初始化活动块UI"""
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            ActivityBlock {
                background-color: #2b2b2b;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
                padding: 8px;
            }
            ActivityBlock:hover {
                background-color: #333333;
                border-color: #555555;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        # 时间范围
        start = self.activity_data.get("start_time", "")
        end = self.activity_data.get("end_time", "")
        start_str = start.strftime("%H:%M") if hasattr(start, 'strftime') else str(start)
        end_str = end.strftime("%H:%M") if hasattr(end, 'strftime') else str(end)
        time_label = BodyLabel(f"{start_str} - {end_str}", self)
        time_label.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addWidget(time_label)

        # 活动类型（带颜色标签）
        type_layout = QHBoxLayout()
        type_layout.setSpacing(8)

        activity_type = self.activity_data.get("activity_type", "未知")
        color = self.activity_data.get("color", "#3498db")

        self.color_indicator = QLabel(self)
        self.color_indicator.setFixedSize(12, 12)
        self.color_indicator.setStyleSheet(
            f"background-color: {color}; border-radius: 6px;"
        )
        type_layout.addWidget(self.color_indicator)

        type_label = StrongBodyLabel(activity_type, self)
        type_layout.addWidget(type_label)
        type_layout.addStretch()
        layout.addLayout(type_layout)
        self.type_label = type_label

        # 窗口标题
        window_title = self.activity_data.get("window_title", "")
        if window_title:
            title_label = BodyLabel(window_title, self)
            title_label.setStyleSheet("color: #aaaaaa; font-size: 11px;")
            title_label.setWordWrap(True)
            layout.addWidget(title_label)

        # AI 分析描述
        description = self.activity_data.get("description", "")
        self.desc_label = BodyLabel(description, self)
        self.desc_label.setStyleSheet("color: #666666; font-size: 11px; font-style: italic;")
        self.desc_label.setWordWrap(True)
        self.desc_label.setVisible(bool(description))
        layout.addWidget(self.desc_label)

        # 置信度
        confidence = self.activity_data.get("confidence", None)
        if confidence is not None:
            conf_text = f"置信度：{confidence:.1%}" if isinstance(confidence, float) else f"置信度：{confidence}"
            conf_label = BodyLabel(conf_text, self)
            conf_label.setStyleSheet("color: #777777; font-size: 10px;")
            layout.addWidget(conf_label)

    def mouseReleaseEvent(self, event):
        """鼠标点击事件，弹出详情对话框"""
        self._show_detail_dialog()

    def _show_detail_dialog(self):
        """显示活动详情对话框，支持修改分类"""
        from qfluentwidgets import ComboBox

        dialog = QDialog(self.window())
        dialog.setWindowTitle("活动详情")
        dialog.setMinimumWidth(400)

        layout = QFormLayout(dialog)
        layout.setSpacing(10)

        data = self.activity_data
        start = data.get("start_time", "")
        end = data.get("end_time", "")
        start_str = start.strftime("%Y-%m-%d %H:%M:%S") if hasattr(start, 'strftime') else str(start)
        end_str = end.strftime("%Y-%m-%d %H:%M:%S") if hasattr(end, 'strftime') else str(end)

        layout.addRow("时间段:", BodyLabel(f"{start_str} ~ {end_str}"))
        layout.addRow("窗口标题:", BodyLabel(data.get("window_title", "无")))

        # 描述编辑框（可修改）
        self.description_edit = TextEdit(dialog)
        self.description_edit.setText(data.get("description", ""))
        self.description_edit.setPlaceholderText("输入活动描述...")
        self.description_edit.setFixedHeight(80)
        layout.addRow("描述:", self.description_edit)

        confidence = data.get("confidence", None)
        if confidence is not None:
            conf_str = f"{confidence:.1%}" if isinstance(confidence, float) else str(confidence)
            layout.addRow("置信度:", BodyLabel(conf_str))

        # 获取所有可用标签
        main_window = self.window()
        tags = []
        if hasattr(main_window, 'db_manager') and main_window.db_manager:
            try:
                tags = main_window.db_manager.get_all_tags()
            except Exception:
                pass

        # 活动类型选择器
        type_combo = ComboBox(dialog)
        tag_names = ["未分类"]
        for tag in tags:
            name = tag.name if hasattr(tag, 'name') else tag.get("name", "")
            if name:
                tag_names.append(name)
        type_combo.addItems(tag_names)

        current_type = data.get("activity_type", "未分类")
        if current_type in tag_names:
            type_combo.setCurrentText(current_type)
        layout.addRow("活动类型:", type_combo)

        # 按钮区域
        btn_layout = QHBoxLayout()

        save_btn = PushButton("保存修改")
        save_btn.setStyleSheet("background-color: #4CAF50; color: white;")

        def on_save():
            new_type = type_combo.currentText()
            activity_id = data.get("id")
            if activity_id:
                changed = False
                if new_type != current_type:
                    try:
                        main_window.db_manager.update_activity_type(activity_id, new_type)
                        data["activity_type"] = new_type
                        changed = True
                    except Exception as e:
                        log_manager.error(f"更新活动类型失败: {e}")
                new_desc = self.description_edit.toPlainText()
                old_desc = data.get("description", "")
                if new_desc != old_desc:
                    try:
                        main_window.db_manager.update_activity_description(activity_id, new_desc)
                        data["description"] = new_desc
                        changed = True
                    except Exception as e:
                        log_manager.error(f"更新活动描述失败: {e}")
                if changed:
                    if new_type != current_type:
                        color_map = {}
                        for tag in tags:
                            name = tag.name if hasattr(tag, 'name') else tag.get("name", "")
                            color = tag.color if hasattr(tag, 'color') else tag.get("color", "#3498db")
                            color_map[name] = color
                        new_color = color_map.get(new_type, "#3498db")
                        self.color_indicator.setStyleSheet(
                            f"background-color: {new_color}; border-radius: 6px;"
                        )
                        self.type_label.setText(new_type)
                    if new_desc != old_desc:
                        self.desc_label.setText(new_desc)
                        self.desc_label.setVisible(bool(new_desc))
                    InfoBar.success(
                        "修改成功",
                        f"活动信息已更新",
                        orient=Qt.Orientation.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP,
                        duration=2000,
                        parent=main_window
                    )
            dialog.accept()

        save_btn.clicked.connect(on_save)
        btn_layout.addWidget(save_btn)

        cancel_btn = PushButton("取消")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addRow(btn_layout)

        dialog.exec()


class _MergeSignals(QObject):
    """合并操作的跨线程信号桥"""
    complete = Signal(int)
    error = Signal(str)


class _SummarySignals(QObject):
    """每日总结的跨线程信号桥"""
    complete = Signal(str)
    error = Signal(str)


class TimelinePage(QWidget):
    """活动时间线页面，按天显示活动记录的时间线视图"""

    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self._current_view = "list"  # 当前视图: list 或 gantt
        self._current_date = QDate.currentDate()
        self._cached_activities = []  # 缓存活动数据
        self._init_ui()

    def _init_ui(self):
        """初始化时间线页面UI布局"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(12)

        # 顶部控制栏
        self._create_top_bar()

        # 左右分栏：左侧视图 + 右侧每日总结
        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # 左侧：视图切换容器
        self.view_stack = QStackedWidget(self)

        # 列表视图
        self.list_view = self._create_list_view()
        self.view_stack.addWidget(self.list_view)

        # 甘特图视图
        self.gantt_view = GanttViewWidget(self)
        self.gantt_view.activity_clicked.connect(self._on_gantt_activity_clicked)
        self.view_stack.addWidget(self.gantt_view)

        splitter.addWidget(self.view_stack)

        # 右侧：每日总结面板
        self._create_summary_panel(splitter)

        splitter.setSizes([500, 500])
        self.main_layout.addWidget(splitter, 1)

        # 默认显示今天的日期
        self._load_date_activities(QDate.currentDate())

    def _create_list_view(self) -> QWidget:
        """创建列表视图"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = ScrollArea(container)
        scroll_area.setWidgetResizable(True)

        self.timeline_widget = QWidget()
        self.timeline_layout = QVBoxLayout(self.timeline_widget)
        self.timeline_layout.setContentsMargins(8, 8, 16, 8)
        self.timeline_layout.setSpacing(6)
        self.timeline_layout.addStretch()

        scroll_area.setWidget(self.timeline_widget)
        layout.addWidget(scroll_area)

        return container

    def _create_top_bar(self):
        """创建顶部日期选择和操作控制栏"""
        top_bar = CardWidget(self)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 12, 16, 12)
        
        hbox1 = QHBoxLayout()
        hbox1.setSpacing(16)
        # title = TitleLabel("活动时间线", top_bar)
        # top_layout.addWidget(title)

        hbox1.addStretch()

        # 视图切换

        self.view_segment = Pivot(top_bar)
        self.view_segment.addItem("list", "列表视图")
        self.view_segment.addItem("gantt", "甘特图视图")
        self.view_segment.setCurrentItem("list")
        self.view_segment.setIndicatorLength(64)
        self.view_segment.currentItemChanged.connect(self._on_view_changed)
        hbox1.addWidget(self.view_segment)
        hbox1.addStretch()
        top_layout.addLayout(hbox1)

        hbox2 = QHBoxLayout()
        hbox2.setSpacing(16)
        hbox2.addStretch()
        # 日期选择器
        date_label = BodyLabel("日期:", top_bar)
        hbox2.addWidget(date_label)

        self.calendar_picker = FastCalendarPicker(top_bar)
        self.calendar_picker.setFixedWidth(140)
        self.calendar_picker.setDate(QDate.currentDate())
        self.calendar_picker.dateChanged.connect(self._on_date_changed)
        hbox2.addWidget(self.calendar_picker)

        # 合并连续行为按钮
        self.merge_btn = PrimaryPushButton("合并连续行为", top_bar)
        self.merge_btn.clicked.connect(self._on_merge_consecutive_activities)
        hbox2.addWidget(self.merge_btn)

        # 刷新按钮
        self.refresh_btn = PushButton(FluentIcon.SYNC, "刷新", top_bar)
        self.refresh_btn.clicked.connect(self._on_refresh)
        hbox2.addWidget(self.refresh_btn)
        top_layout.addLayout(hbox2)
        top_layout.setStretch(0, 1)
        top_layout.setStretch(1, 1)
        self.main_layout.addWidget(top_bar, 0)

    def _create_summary_panel(self, splitter):
        """创建右侧每日总结面板"""
        summary_card = CardWidget(self)
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(12, 12, 12, 12)
        summary_layout.setSpacing(8)

        title = StrongBodyLabel("每日总结", summary_card)
        summary_layout.addWidget(title)

        self.summary_date_label = BodyLabel("", summary_card)
        self.summary_date_label.setStyleSheet("color: #888888;")
        summary_layout.addWidget(self.summary_date_label)

        self.summary_browser = TextEdit(summary_card)
        # self.summary_browser.setReadOnly(True)
        self.summary_browser.setStyleSheet("""
            TextEdit {
                background-color: #1e1e1e;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
                padding: 8px;
                color: #cccccc;
            }
        """)
        summary_layout.addWidget(self.summary_browser, 1)

        self.summary_btn = PrimaryPushButton("生成总结", summary_card)
        self.summary_btn.clicked.connect(self._on_generate_summary)
        summary_layout.addWidget(self.summary_btn)

        splitter.addWidget(summary_card)

    def _on_view_changed(self, view_id: str):
        """视图切换事件"""
        self._current_view = view_id
        if view_id == "list":
            self.view_stack.setCurrentIndex(0)
        else:
            self.view_stack.setCurrentIndex(1)
        # 重新加载数据以更新当前视图
        self._load_date_activities(self._current_date)

    def _on_gantt_activity_clicked(self, activity_data: dict):
        """甘特图活动块点击事件"""
        # 弹出详情对话框
        self._show_activity_detail_dialog(activity_data)

    def _show_activity_detail_dialog(self, activity_data: dict):
        """显示活动详情对话框"""
        from qfluentwidgets import ComboBox

        dialog = QDialog(self)
        dialog.setWindowTitle("活动详情")
        dialog.setMinimumWidth(400)

        layout = QFormLayout(dialog)
        layout.setSpacing(10)

        data = activity_data
        start = data.get("start_time", "")
        end = data.get("end_time", "")

        if hasattr(start, 'strftime'):
            start_str = start.strftime("%Y-%m-%d %H:%M:%S")
        else:
            start_str = str(start)

        if hasattr(end, 'strftime'):
            end_str = end.strftime("%Y-%m-%d %H:%M:%S")
        else:
            end_str = str(end)

        layout.addRow("时间段:", BodyLabel(f"{start_str} ~ {end_str}"))
        layout.addRow("窗口标题:", BodyLabel(data.get("window_title", "无")))

        # 描述编辑框（可修改）
        self.description_edit = TextEdit(dialog)
        self.description_edit.setText(data.get("description", ""))
        self.description_edit.setPlaceholderText("输入活动描述...")
        self.description_edit.setFixedHeight(80)
        layout.addRow("描述:", self.description_edit)

        confidence = data.get("confidence", None)
        if confidence is not None:
            conf_str = f"{confidence:.1%}" if isinstance(confidence, float) else str(confidence)
            layout.addRow("置信度:", BodyLabel(conf_str))

        # 获取所有可用标签
        tags = []
        if self.main_window and self.main_window.db_manager:
            try:
                tags = self.main_window.db_manager.get_all_tags()
            except Exception:
                pass

        # 活动类型选择器
        type_combo = ComboBox(dialog)
        tag_names = ["未分类"]
        for tag in tags:
            name = tag.name if hasattr(tag, 'name') else tag.get("name", "")
            if name:
                tag_names.append(name)
        type_combo.addItems(tag_names)

        current_type = data.get("activity_type", "未分类")
        if current_type in tag_names:
            type_combo.setCurrentText(current_type)
        layout.addRow("活动类型:", type_combo)

        # 按钮区域
        btn_layout = QHBoxLayout()

        save_btn = PushButton("保存修改")
        save_btn.setStyleSheet("background-color: #4CAF50; color: white;")

        def on_save():
            new_type = type_combo.currentText()
            activity_id = data.get("id")
            if activity_id:
                changed = False
                if new_type != current_type:
                    try:
                        self.main_window.db_manager.update_activity_type(activity_id, new_type)
                        data["activity_type"] = new_type
                        changed = True
                    except Exception as e:
                        log_manager.error(f"更新活动类型失败: {e}")
                new_desc = self.description_edit.toPlainText()
                old_desc = data.get("description", "")
                if new_desc != old_desc:
                    try:
                        self.main_window.db_manager.update_activity_description(activity_id, new_desc)
                        data["description"] = new_desc
                        changed = True
                    except Exception as e:
                        log_manager.error(f"更新活动描述失败: {e}")
                if changed:
                    InfoBar.success(
                        "修改成功",
                        f"活动信息已更新",
                        orient=Qt.Orientation.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP,
                        duration=2000,
                        parent=self
                    )
                    self._load_date_activities(self._current_date)
            dialog.accept()

        save_btn.clicked.connect(on_save)
        btn_layout.addWidget(save_btn)

        cancel_btn = PushButton("取消")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addRow(btn_layout)

        dialog.exec()

    def _on_date_changed(self, date):
        """日期选择变更事件"""
        self._current_date = date
        self._load_date_activities(date)

    def _on_merge_consecutive_activities(self):
        """合并连续相同活动类型的行为描述"""
        if not self.main_window or not self.main_window.db_manager:
            InfoBar.warning("操作失败", "数据库未就绪", orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=2000, parent=self)
            return

        self.merge_btn.setEnabled(False)
        self.merge_btn.setText("合并中...")

        from ai import AIAnalyzer
        from PySide6.QtCore import QRunnable, QThreadPool

        target_date = self._current_date.toPython()
        start_time = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0)
        end_time = start_time + timedelta(days=1)

        try:
            activities = self.main_window.db_manager.get_activities_in_range(start_time, end_time)
        except Exception as e:
            log_manager.error(f"获取活动记录失败: {e}")
            InfoBar.error("获取数据失败", str(e), orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=3000, parent=self)
            self.merge_btn.setEnabled(True)
            self.merge_btn.setText("合并连续行为")
            return

        if not activities:
            InfoBar.info("无活动记录", "当前日期没有需要合并的活动记录", orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=2000, parent=self)
            self.merge_btn.setEnabled(True)
            self.merge_btn.setText("合并连续行为")
            return

        MERGE_TIME_GAP = timedelta(minutes=1)

        groups = []
        current_group = None

        for act in activities:
            act_type = act.activity_type
            act_id = act.id
            title = act.window_title or ""
            desc = act.description or ""
            if title and desc:
                combined = f"[{title}] {desc}"
            elif title:
                combined = f"[{title}]"
            else:
                combined = desc

            if current_group is None or current_group["type"] != act_type:
                current_group = {"type": act_type, "ids": [act_id], "start_id": act_id, "end_id": act_id, "descriptions": [combined], "last_end_time": act.end_time}
                groups.append(current_group)
            else:
                time_gap = act.start_time - current_group["last_end_time"]
                if time_gap > MERGE_TIME_GAP:
                    current_group = {"type": act_type, "ids": [act_id], "start_id": act_id, "end_id": act_id, "descriptions": [combined], "last_end_time": act.end_time}
                    groups.append(current_group)
                else:
                    current_group["ids"].append(act_id)
                    current_group["end_id"] = act_id
                    current_group["descriptions"].append(combined)
                    current_group["last_end_time"] = act.end_time

        mergable_groups = [g for g in groups if len(g["ids"]) > 1]
        if not mergable_groups:
            InfoBar.info("无需合并", "当前日期没有连续相同类型的活动记录", orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=2000, parent=self)
            self.merge_btn.setEnabled(True)
            self.merge_btn.setText("合并连续行为")
            return

        total_groups = len(mergable_groups)
        log_manager.info(f"找到 {total_groups} 组可合并的连续活动")

        # 在主线程创建 AIAnalyzer（QObject 不能在后台线程创建）
        ai_analyzer = AIAnalyzer(self.main_window._config, self.main_window.db_manager)

        # 创建信号桥，用于跨线程回调
        signals = _MergeSignals()
        signals.complete.connect(self._on_merge_complete)
        signals.error.connect(self._on_merge_error)

        class MergeTask(QRunnable):
            def __init__(self, groups_data, main_window, analyzer, sig):
                super().__init__()
                self.groups = groups_data
                self.main_window = main_window
                self.analyzer = analyzer
                self.signals = sig
                self.setAutoDelete(True)

            def run(self):
                try:
                    merged_count = 0

                    for group in self.groups:
                        descriptions = group["descriptions"]
                        valid_descs = [d for d in descriptions if d and d.strip()]

                        if not valid_descs:
                            first_id = group["ids"][0]
                            last_id = group["ids"][-1]
                            try:
                                with self.main_window.db_manager.get_session(expire_on_commit=False) as session:
                                    last_record = session.query(ActivityRecord).filter(ActivityRecord.id == last_id).first()
                                    if last_record:
                                        self.main_window.db_manager.update_activity_end_time(first_id, last_record.end_time)
                                        ids_to_delete = [id_ for id_ in group["ids"] if id_ != first_id]
                                        if ids_to_delete:
                                            self.main_window.db_manager.delete_activities_by_ids(ids_to_delete)
                                        merged_count += 1
                            except Exception as e:
                                log_manager.error(f"合并无描述活动组失败: {e}")
                            continue

                        try:
                            merged_desc = self.analyzer.merge_descriptions(valid_descs, group["type"])
                        except Exception:
                            merged_desc = valid_descs[0]

                        first_id = group["ids"][0]
                        with self.main_window.db_manager.get_session(expire_on_commit=False) as session:
                            last_record = session.query(ActivityRecord).filter(ActivityRecord.id == group["ids"][-1]).first()
                            if last_record:
                                self.main_window.db_manager.update_activity_end_time(first_id, last_record.end_time)

                        self.main_window.db_manager.update_activity_description(first_id, merged_desc)

                        ids_to_delete = [id_ for id_ in group["ids"] if id_ != first_id]
                        if ids_to_delete:
                            self.main_window.db_manager.delete_activities_by_ids(ids_to_delete)

                        merged_count += 1
                        log_manager.info(f"合并活动组完成: {group['type']}, {len(group['ids'])}条 -> 1条")

                    self.signals.complete.emit(merged_count)

                except Exception as e:
                    log_manager.error(f"合并活动失败: {e}")
                    self.signals.error.emit(str(e))

        task = MergeTask(mergable_groups, self.main_window, ai_analyzer, signals)
        QThreadPool.globalInstance().start(task)

    def _on_merge_complete(self, merged_count):
        """合并完成回调"""
        self.merge_btn.setEnabled(True)
        self.merge_btn.setText("合并连续行为")
        InfoBar.success("合并完成", f"已合并 {merged_count} 组连续活动", orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=3000, parent=self)
        self._load_date_activities(self._current_date)

    def _on_merge_error(self, error_msg):
        """合并失败回调"""
        self.merge_btn.setEnabled(True)
        self.merge_btn.setText("合并连续行为")
        InfoBar.error("合并失败", error_msg, orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=3000, parent=self)

    def _on_generate_summary(self):
        """生成每日总结按钮点击事件"""
        if not self.main_window or not self.main_window.db_manager:
            InfoBar.warning("操作失败", "数据库未就绪", orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=2000, parent=self)
            return

        self.summary_btn.setEnabled(False)
        self.summary_btn.setText("生成中...")

        from ai import AIAnalyzer
        from PySide6.QtCore import QRunnable, QThreadPool

        target_date = self._current_date.toPython()
        date_str = target_date.strftime("%Y-%m-%d")
        start_time = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0)
        end_time = start_time + timedelta(days=1)

        try:
            activities = self.main_window.db_manager.get_activities_in_range(start_time, end_time)
        except Exception as e:
            log_manager.error(f"获取活动记录失败: {e}")
            self.summary_btn.setEnabled(True)
            self.summary_btn.setText("生成总结")
            InfoBar.error("获取数据失败", str(e), orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=3000, parent=self)
            return

        if not activities:
            self.summary_browser.setHtml("<p style='color:#888;'>该日期暂无活动记录</p>")
            self.summary_btn.setEnabled(True)
            self.summary_btn.setText("生成总结")
            return

        # 获取标签颜色映射
        tag_color_map = self._get_tag_color_map()

        # 构建活动数据列表
        activities_data = []
        for act in activities:
            if hasattr(act, 'start_time'):
                act_type = act.activity_type
                activities_data.append({
                    "activity_type": act_type,
                    "start_time": act.start_time,
                    "end_time": act.end_time,
                    "description": act.description or "",
                    "window_title": act.window_title,
                    "color": tag_color_map.get(act_type, "#3498db"),
                })
            else:
                activities_data.append(act)

        # 在主线程创建 AIAnalyzer
        ai_analyzer = AIAnalyzer(self.main_window._config, self.main_window.db_manager)

        # 创建信号桥，用于跨线程回调
        signals = _SummarySignals()
        signals.complete.connect(self._on_summary_complete)
        signals.error.connect(self._on_summary_error)

        class SummaryTask(QRunnable):
            def __init__(self, analyzer, data, date_str, sig):
                super().__init__()
                self.analyzer = analyzer
                self.data = data
                self.date_str = date_str
                self.signals = sig
                self.setAutoDelete(True)

            def run(self):
                try:
                    result = self.analyzer.generate_daily_summary(self.data, self.date_str)
                    self.signals.complete.emit(result)
                except Exception as e:
                    log_manager.error(f"生成每日总结失败: {e}")
                    self.signals.error.emit(str(e))

        task = SummaryTask(ai_analyzer, activities_data, date_str, signals)
        QThreadPool.globalInstance().start(task)

    def _on_summary_complete(self, html_content):
        """每日总结生成完成回调"""
        self.summary_btn.setEnabled(True)
        self.summary_btn.setText("生成总结")
        self.summary_browser.setHtml(html_content)
        try:
            target_date = self._current_date.toPython()
            self.main_window.db_manager.save_daily_summary(target_date, html_content)
        except Exception as e:
            log_manager.debug(f"保存每日总结失败: {e}")
        InfoBar.success("总结完成", "每日总结已生成", orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=3000, parent=self)

    def _on_summary_error(self, error_msg):
        """每日总结生成失败回调"""
        self.summary_btn.setEnabled(True)
        self.summary_btn.setText("生成总结")
        self.summary_browser.setHtml(f"<p style='color:#e74c3c;'>生成失败: {error_msg}</p>")
        InfoBar.error("总结失败", error_msg, orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=3000, parent=self)

    def _on_refresh(self):
        """刷新按钮点击事件"""
        self._load_date_activities(self._current_date)

    def _load_date_activities(self, qdate):
        """加载指定日期的活动记录并渲染"""
        self._current_date = qdate

        # 更新右侧总结面板的日期显示
        target_date = qdate.toPython()
        self.summary_date_label.setText(f"日期: {target_date.strftime('%Y-%m-%d')}")
        # 从数据库加载已保存的总结
        if self.main_window and self.main_window.db_manager:
            try:
                saved_summary = self.main_window.db_manager.get_daily_summary(target_date)
                if saved_summary:
                    self.summary_browser.setHtml(saved_summary)
                else:
                    self.summary_browser.setHtml("<p style='color:#888;'>点击下方按钮生成当日总结</p>")
            except Exception:
                self.summary_browser.setHtml("<p style='color:#888;'>点击下方按钮生成当日总结</p>")
        else:
            self.summary_browser.setHtml("<p style='color:#888;'>点击下方按钮生成当日总结</p>")

        # 清除列表视图内容
        self._clear_list_view()

        if not self.main_window or not self.main_window.db_manager:
            return

        # 计算日期范围
        target_date = qdate.toPython()
        start_time = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0)
        end_time = start_time + timedelta(days=1)

        try:
            activities = self.main_window.db_manager.get_activities_in_range(start_time, end_time)

            # 缓存活动数据
            self._cached_activities = activities

            # 获取标签颜色映射
            tag_color_map = self._get_tag_color_map()

            # 准备活动数据列表
            activity_data_list = []
            for activity in activities:
                # 从数据库对象或字典中提取数据
                if hasattr(activity, 'start_time'):
                    act_start = activity.start_time
                    act_end = activity.end_time
                    act_type = activity.activity_type
                    act_window = activity.window_title
                    act_description = activity.description
                    act_screenshot_id = activity.screenshot_id
                    act_confidence = activity.confidence
                    act_id = activity.id
                else:
                    act_start = activity.get("start_time", "")
                    act_end = activity.get("end_time", "")
                    act_type = activity.get("activity_type", "未分类")
                    act_window = activity.get("window_title", "")
                    act_description = activity.get("description", "")
                    act_screenshot_id = activity.get("screenshot_id", None)
                    act_confidence = activity.get("confidence", None)
                    act_id = activity.get("id", None)

                color = tag_color_map.get(act_type, "#3498db")

                activity_data = {
                    "id": act_id,
                    "start_time": act_start,
                    "end_time": act_end,
                    "activity_type": act_type,
                    "window_title": act_window,
                    "description": act_description,
                    "screenshot_id": act_screenshot_id,
                    "confidence": act_confidence,
                    "color": color,
                }
                activity_data_list.append(activity_data)

            # 根据当前视图类型渲染
            if self._current_view == "list":
                self._render_list_view(activity_data_list)
            else:
                self._render_gantt_view(activity_data_list, qdate)

            count = len(activities)
            log_manager.debug(f"加载日期 {qdate.toString('yyyy-MM-dd')} 的活动记录: {count}条")

        except Exception as e:
            log_manager.error(f"加载活动记录失败: {e}")
            InfoBar.error(
                "加载失败",
                f"无法加载活动记录: {e}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

    def _render_list_view(self, activity_data_list: list):
        """渲染列表视图"""
        if not activity_data_list:
            empty_label = BodyLabel("该日期暂无活动记录", self.timeline_widget)
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet("color: #888888; padding: 40px;")
            self.timeline_layout.insertWidget(
                self.timeline_layout.count() - 1, empty_label
            )
            return

        for idx, activity_data in enumerate(activity_data_list):
            block = ActivityBlock(activity_data, idx, self.timeline_widget)
            self.timeline_layout.insertWidget(
                self.timeline_layout.count() - 1, block
            )

    def _render_gantt_view(self, activity_data_list: list, qdate):
        """渲染甘特图视图"""
        self.gantt_view.set_date(qdate)
        self.gantt_view.set_activities(activity_data_list)

    def _get_tag_color_map(self):
        """获取标签名称到颜色的映射字典"""
        color_map = {}
        try:
            if self.main_window and self.main_window.db_manager:
                tags = self.main_window.db_manager.get_all_tags()
                for tag in tags:
                    name = tag.name if hasattr(tag, 'name') else tag.get("name", "")
                    color = tag.color if hasattr(tag, 'color') else tag.get("color", "#3498db")
                    color_map[name] = color
        except Exception as e:
            log_manager.warning(f"获取标签颜色映射失败: {e}")
        return color_map

    def _clear_list_view(self):
        """清除列表视图中所有活动块"""
        # 保留最后的stretch，清除其他所有widget
        while self.timeline_layout.count() > 1:
            item = self.timeline_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
