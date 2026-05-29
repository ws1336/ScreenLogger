"""
分类管理页面 - 管理活动分类标签
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidgetItem, QColorDialog,
    QDialog, QFormLayout, QHeaderView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush
from qfluentwidgets import (
    PrimaryPushButton, PushButton, ComboBox, LineEdit,
    FluentIcon, InfoBar, InfoBarPosition, BodyLabel,
    CardWidget, TableWidget, MessageBox
)

from logger import log_manager


class TagDialog(QDialog):
    """添加/编辑分类标签的对话框"""

    def __init__(self, parent=None, tag_data=None):
        super().__init__(parent)
        self.tag_data = tag_data
        self._selected_color = tag_data.get("color", "#3498db") if tag_data else "#3498db"
        self._init_ui()
        if tag_data:
            self._load_tag_data()

    def _init_ui(self):
        """初始化对话框UI"""
        self.setWindowTitle("编辑标签" if self.tag_data else "添加标签")
        self.setMinimumWidth(400)

        layout = QFormLayout(self)
        layout.setSpacing(12)

        # 标签名称
        self.name_edit = LineEdit(self)
        self.name_edit.setPlaceholderText("输入标签名称...")
        layout.addRow("名称:", self.name_edit)

        # 颜色选择
        color_layout = QHBoxLayout()
        self.color_preview = BodyLabel(self)
        self.color_preview.setFixedSize(24, 24)
        self.color_preview.setStyleSheet(
            f"background-color: {self._selected_color}; border: 1px solid #ccc; border-radius: 4px;"
        )
        self.color_label = BodyLabel(self._selected_color, self)
        self.color_btn = PushButton(FluentIcon.PALETTE, "选择颜色", self)
        self.color_btn.clicked.connect(self._choose_color)
        color_layout.addWidget(self.color_preview)
        color_layout.addWidget(self.color_label)
        color_layout.addWidget(self.color_btn)
        color_layout.addStretch()
        layout.addRow("颜色:", color_layout)

        # 匹配模式类型
        self.pattern_type_combo = ComboBox(self)
        self.pattern_type_combo.addItems(["关键词匹配", "正则表达式"])
        layout.addRow("匹配模式类型:", self.pattern_type_combo)

        # 匹配模式
        self.pattern_edit = LineEdit(self)
        self.pattern_edit.setPlaceholderText("输入匹配模式（关键词或正则表达式）...")
        layout.addRow("匹配模式:", self.pattern_edit)

        # 描述
        self.desc_edit = LineEdit(self)
        self.desc_edit.setPlaceholderText("输入标签描述...")
        layout.addRow("描述:", self.desc_edit)

        # 按钮
        btn_layout = QHBoxLayout()
        ok_btn = PrimaryPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = PushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addRow(btn_layout)

    def _load_tag_data(self):
        """加载已有标签数据进行编辑"""
        self.name_edit.setText(self.tag_data.get("name", ""))
        self.pattern_edit.setText(self.tag_data.get("pattern", ""))
        self.desc_edit.setText(self.tag_data.get("description", ""))
        self._selected_color = self.tag_data.get("color", "#3498db")
        self.color_preview.setStyleSheet(
            f"background-color: {self._selected_color}; border: 1px solid #ccc; border-radius: 4px;"
        )
        self.color_label.setText(self._selected_color)
        # 根据pattern内容判断类型
        pattern = self.tag_data.get("pattern", "")
        if pattern and (pattern.startswith("^") or pattern.endswith("$") or ".*" in pattern):
            self.pattern_type_combo.setCurrentIndex(1)  # 正则
        else:
            self.pattern_type_combo.setCurrentIndex(0)  # 关键词

    def _choose_color(self):
        """打开颜色选择对话框"""
        color = QColorDialog.getColor(QColor(self._selected_color), self, "选择标签颜色")
        if color.isValid():
            self._selected_color = color.name()
            self.color_preview.setStyleSheet(
                f"background-color: {self._selected_color}; border: 1px solid #ccc; border-radius: 4px;"
            )
            self.color_label.setText(self._selected_color)

    def get_tag_data(self):
        """获取对话框中的标签数据"""
        return {
            "name": self.name_edit.text().strip(),
            "color": self._selected_color,
            "pattern": self.pattern_edit.text().strip(),
            "description": self.desc_edit.text().strip(),
            "is_regex": self.pattern_type_combo.currentIndex() == 1,
        }


class ClassifierPage(QWidget):
    """分类管理页面，管理标签并执行活动分类"""

    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self._init_ui()
        self._refresh_tag_list()

    def _init_ui(self):
        """初始化分类管理页面UI布局"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(12)

        # 工具栏
        self._create_toolbar()

        # 标签列表表格
        self.tag_table = TableWidget(self)
        self.tag_table.setColumnCount(6)
        self.tag_table.setHorizontalHeaderLabels([
            "名称", "颜色", "匹配模式", "是否为预设", "描述", "操作"
        ])
        self.tag_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tag_table.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        self.tag_table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
        self.tag_table.setAlternatingRowColors(True)
        self.main_layout.addWidget(self.tag_table)

    def _create_toolbar(self):
        """创建工具栏"""
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(8)

        self.add_btn = PrimaryPushButton(FluentIcon.ADD, "添加标签", self)
        self.add_btn.clicked.connect(self._on_add_tag)
        toolbar_layout.addWidget(self.add_btn)

        self.edit_btn = PushButton(FluentIcon.EDIT, "编辑标签", self)
        self.edit_btn.clicked.connect(self._on_edit_tag)
        toolbar_layout.addWidget(self.edit_btn)

        self.delete_btn = PushButton(FluentIcon.DELETE, "删除标签", self)
        self.delete_btn.clicked.connect(self._on_delete_tag)
        toolbar_layout.addWidget(self.delete_btn)

        toolbar_layout.addStretch()

        self.main_layout.addLayout(toolbar_layout)

    def _refresh_tag_list(self):
        """刷新标签列表"""
        self.tag_table.setRowCount(0)
        if not self.main_window or not self.main_window.db_manager:
            return

        try:
            tags = self.main_window.db_manager.get_all_tags()
            self.tag_table.setRowCount(len(tags))

            for row, tag in enumerate(tags):
                # 名称
                name_item = QTableWidgetItem(
                    tag.name if hasattr(tag, 'name') else tag.get("name", "")
                )
                self.tag_table.setItem(row, 0, name_item)

                # 颜色
                color_value = tag.color if hasattr(tag, 'color') else tag.get("color", "#3498db")
                color_item = QTableWidgetItem(color_value)
                color_item.setBackground(QBrush(QColor(color_value)))
                self.tag_table.setItem(row, 1, color_item)

                # 匹配模式
                pattern = tag.pattern if hasattr(tag, 'pattern') else tag.get("pattern", "")
                self.tag_table.setItem(row, 2, QTableWidgetItem(pattern))

                # 是否为预设
                is_preset = tag.is_preset if hasattr(tag, 'is_preset') else tag.get("is_preset", False)
                preset_text = "是" if is_preset else "否"
                self.tag_table.setItem(row, 3, QTableWidgetItem(preset_text))

                # 描述
                desc = tag.description if hasattr(tag, 'description') else tag.get("description", "")
                self.tag_table.setItem(row, 4, QTableWidgetItem(desc))

                # 操作按钮 - 存储在tag数据中，删除按钮单独处理
                # 存储tag原始数据用于后续操作
                for col in range(6):
                    item = self.tag_table.item(row, col)
                    if item:
                        item.setData(Qt.ItemDataRole.UserRole, row)

                # 通过表格的item存储tag id
                tag_id = tag.id if hasattr(tag, 'id') else tag.get("id", row)
                id_item = QTableWidgetItem(str(tag_id))
                id_item.setData(Qt.ItemDataRole.UserRole, tag_id)
                self.tag_table.setItem(row, 5, id_item)

        except Exception as e:
            log_manager.error(f"刷新标签列表失败: {e}")
            InfoBar.error(
                "加载失败",
                f"无法加载标签列表: {e}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

    def _get_selected_tag_id(self):
        """获取当前选中行的标签ID"""
        current_row = self.tag_table.currentRow()
        if current_row < 0:
            return None, None
        id_item = self.tag_table.item(current_row, 5)
        if id_item:
            return id_item.data(Qt.ItemDataRole.UserRole), current_row
        return None, None

    def _on_add_tag(self):
        """添加标签按钮点击事件"""
        dialog = TagDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            tag_data = dialog.get_tag_data()
            if not tag_data["name"]:
                InfoBar.warning(
                    "输入不完整",
                    "请输入标签名称",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self
                )
                return
            try:
                if self.main_window and self.main_window.db_manager:
                    self.main_window.db_manager.add_tag(
                        name=tag_data["name"],
                        color=tag_data["color"],
                        pattern=tag_data["pattern"],
                        description=tag_data["description"]
                    )
                    log_manager.info(f"添加标签: {tag_data['name']}")
                    self._refresh_tag_list()
                    InfoBar.success(
                        "添加成功",
                        f"标签 '{tag_data['name']}' 已添加",
                        orient=Qt.Orientation.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP,
                        duration=3000,
                        parent=self
                    )
            except Exception as e:
                log_manager.error(f"添加标签失败: {e}")
                InfoBar.error(
                    "添加失败",
                    str(e),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self
                )

    def _on_edit_tag(self):
        """编辑标签按钮点击事件"""
        tag_id, row = self._get_selected_tag_id()
        if tag_id is None:
            InfoBar.warning(
                "未选择",
                "请先选择要编辑的标签",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            return

        # 收集当前标签数据
        tag_data = {
            "id": tag_id,
            "name": self.tag_table.item(row, 0).text(),
            "color": self.tag_table.item(row, 1).text(),
            "pattern": self.tag_table.item(row, 2).text(),
            "is_preset": self.tag_table.item(row, 3).text() == "是",
            "description": self.tag_table.item(row, 4).text(),
        }

        dialog = TagDialog(self, tag_data)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_data = dialog.get_tag_data()
            try:
                if self.main_window and self.main_window.db_manager:
                    self.main_window.db_manager.update_tag(
                        tag_id=tag_id,
                        name=new_data["name"],
                        color=new_data["color"],
                        pattern=new_data["pattern"],
                        description=new_data["description"]
                    )
                    log_manager.info(f"更新标签: {new_data['name']}")
                    self._refresh_tag_list()
                    InfoBar.success(
                        "更新成功",
                        f"标签 '{new_data['name']}' 已更新",
                        orient=Qt.Orientation.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP,
                        duration=3000,
                        parent=self
                    )
            except Exception as e:
                log_manager.error(f"更新标签失败: {e}")
                InfoBar.error(
                    "更新失败",
                    str(e),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self
                )

    def _on_delete_tag(self):
        """删除标签按钮点击事件"""
        tag_id, row = self._get_selected_tag_id()
        if tag_id is None:
            InfoBar.warning(
                "未选择",
                "请先选择要删除的标签",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            return

        is_preset = self.tag_table.item(row, 3).text() == "是"
        if is_preset:
            InfoBar.warning(
                "无法删除",
                "预设标签不可删除",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            return

        tag_name = self.tag_table.item(row, 0).text()
        w = MessageBox(f"确定要删除标签 '{tag_name}' 吗？", "确认删除", self)
        w.yesButton.setText("确认删除")
        w.cancelButton.setText("取消")
        if w.exec():
            try:
                if self.main_window and self.main_window.db_manager:
                    self.main_window.db_manager.delete_tag(tag_id)
                    log_manager.info(f"删除标签: {tag_name}")
                    self._refresh_tag_list()
                    InfoBar.success(
                        "删除成功",
                        f"标签 '{tag_name}' 已删除",
                        orient=Qt.Orientation.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP,
                        duration=3000,
                        parent=self
                    )
            except Exception as e:
                log_manager.error(f"删除标签失败: {e}")
                InfoBar.error(
                    "删除失败",
                    str(e),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self
                )