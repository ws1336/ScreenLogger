"""
设置页面 - 管理应用的各项配置参数
"""
from pathlib import Path
import threading
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QFileDialog, QFormLayout, QLabel
)
from PySide6.QtCore import Qt, QTimer, QObject, Signal
from PySide6.QtGui import QPixmap
from qfluentwidgets import (
    ScrollArea, PrimaryPushButton, PushButton,
    SpinBox, ComboBox, LineEdit, PasswordLineEdit,
    CardWidget, FluentIcon, InfoBar, InfoBarPosition,
    BodyLabel, StrongBodyLabel, TitleLabel, MessageBox
)
from shiboken6 import isValid

from config import Settings, DB_FILENAME
from logger import log_manager
import assets
from version import __version__

# AI 提供商常量定义
AI_PROVIDERS = [
    {"openai": "云端 (OpenAI Chat Completions)"},
    {"anthropic": "云端 (Anthropic Messages)"},
    {"local": "本地 (Ollama)"},
    {"off": "关闭"}
]

# AI 提供商索引常量
AI_PROVIDER_OPENAI_INDEX = 0
AI_PROVIDER_ANTHROPIC_INDEX = 1
AI_PROVIDER_LOCAL_INDEX = 2
AI_PROVIDER_OFF_INDEX = 3

# 关于页面常量定义
APP_TEAM = "四只小猫"
APP_DESCRIPTION = "桌面屏幕录制与活动分析工具"
OPEN_SOURCE_URL = "https://github.com/ws1336/ScreenLogger"
DONATE_ALI_PATH = ":/donate_ali.png"
DONATE_WX_PATH = ":/donate_wx.png"
TEAM_ICON_PATH = ":/team_icon.png"

class _AITestSignaler(QObject):
    """跨线程传递 AI 测试结果"""
    result_ready = Signal(dict)


class SettingsPage(QWidget):
    """设置页面，管理截图、视频、AI 和存储相关配置"""
    
    def _setup_spinbox_focus_policy(self, spinbox):
        """
        设置 SpinBox 的焦点策略为仅点击获得焦点
        并通过事件过滤器阻止鼠标悬停时的滚轮事件
        """
        spinbox.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        spinbox.installEventFilter(self)

    def eventFilter(self, obj, event):
        """
        事件过滤器：当 SpinBox 没有焦点时，忽略滚轮事件
        让事件继续传递到上层 ScrollArea 处理滚动
        """
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.Wheel and not obj.hasFocus():
            event.ignore()
            return True
        return super().eventFilter(obj, event)
    
    @staticmethod
    def get_ai_provider_labels():
        """获取 AI 提供商的显示标签列表"""
        return [list(item.values())[0] for item in AI_PROVIDERS]
    
    @staticmethod
    def get_ai_provider_index(provider: str) -> int:
        """根据提供商键名获取索引"""
        for i, item in enumerate(AI_PROVIDERS):
            if provider in item:
                return i
        return 0
    
    @staticmethod
    def get_ai_provider_key(index: int) -> str:
        """根据索引获取提供商键名"""
        if 0 <= index < len(AI_PROVIDERS):
            return list(AI_PROVIDERS[index].keys())[0]
        return "openai"
    
    @staticmethod
    def get_ai_provider_map():
        """获取索引到键名的映射字典"""
        return {i: SettingsPage.get_ai_provider_key(i) for i in range(len(AI_PROVIDERS))}
    
    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self._config = Settings()
        self._test_signaler = _AITestSignaler()
        self._test_signaler.result_ready.connect(self._on_ai_test_result)
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        """初始化设置页面UI布局"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # 滚动区域
        self.scroll_area = ScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setSpacing(16)
        self.scroll_layout.setContentsMargins(20, 20, 20, 20)

        # 页面标题
        title = TitleLabel("设置", self.scroll_widget)
        self.scroll_layout.addWidget(title)

        # ========== 截图设置 ==========
        self._create_screenshot_settings()

        # ========== 图片播放与分析设置 ==========
        self._create_image_settings()

        # ========== AI设置 ==========
        self._create_ai_settings()

        # ========== 存储设置 ==========
        self._create_storage_settings()

        # ========== 其他设置 ==========
        self._create_other_settings()

        # ========== 关于 ==========
        self._create_about_settings()

        # 底部按钮
        self._create_bottom_buttons()

        self.scroll_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_widget)
        self.main_layout.addWidget(self.scroll_area)

    def _create_screenshot_settings(self):
        """创建截图设置分组"""
        group = CardWidget(self.scroll_widget)
        group.setBorderRadius(8)
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(16, 16, 16, 16)
        group_layout.setSpacing(12)

        group_title = StrongBodyLabel("截图设置")
        group_layout.addWidget(group_title)

        layout = QFormLayout()
        layout.setSpacing(12)

        # 截图间隔
        self.screenshot_interval_spin = SpinBox()
        self.screenshot_interval_spin.setRange(1, 300)
        self.screenshot_interval_spin.setSuffix(" 秒")
        self.screenshot_interval_spin.setEnabled(False)
        self._setup_spinbox_focus_policy(self.screenshot_interval_spin)
        layout.addRow("截图间隔:", self.screenshot_interval_spin)

        # 截图质量
        self.screenshot_quality_spin = SpinBox()
        self.screenshot_quality_spin.setRange(1, 100)
        self.screenshot_quality_spin.setSuffix(" %")
        self._setup_spinbox_focus_policy(self.screenshot_quality_spin)
        layout.addRow("截图质量:", self.screenshot_quality_spin)

        group_layout.addLayout(layout)

        self.scroll_layout.addWidget(group)

    def _create_image_settings(self):
        """创建图片播放与分析设置分组"""
        group = CardWidget(self.scroll_widget)
        group.setBorderRadius(8)
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(16, 16, 16, 16)
        group_layout.setSpacing(12)

        group_title = StrongBodyLabel("图片播放与分析设置")
        group_layout.addWidget(group_title)

        layout = QFormLayout()
        layout.setSpacing(12)

        # 图片播放间隔
        self.image_play_interval_spin = SpinBox()
        self.image_play_interval_spin.setRange(1, 300)
        self.image_play_interval_spin.setSuffix(" 张")
        self.image_play_interval_spin.setToolTip("播放时每隔 N 张截图显示一张，N 越大播放速度越快")
        self._setup_spinbox_focus_policy(self.image_play_interval_spin)
        layout.addRow("图片播放间隔:", self.image_play_interval_spin)

        # 截图分析间隔
        self.analysis_interval_spin = SpinBox()
        self.analysis_interval_spin.setRange(1, 300)
        self.analysis_interval_spin.setSuffix(" 张")
        self.analysis_interval_spin.setToolTip("AI 分析时每隔 N 张截图采样分析一张")
        self._setup_spinbox_focus_policy(self.analysis_interval_spin)
        layout.addRow("截图分析间隔:", self.analysis_interval_spin)

        group_layout.addLayout(layout)

        self.scroll_layout.addWidget(group)

    def _create_ai_settings(self):
        """创建AI设置分组"""
        group = CardWidget(self.scroll_widget)
        group.setBorderRadius(8)
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(16, 16, 16, 16)
        group_layout.setSpacing(12)

        group_title = StrongBodyLabel("AI 设置")
        group_layout.addWidget(group_title)

        layout = QFormLayout()
        layout.setSpacing(12)

        # AI 提供商选择
        self.ai_provider_combo = ComboBox()
        self.ai_provider_combo.addItems(self.get_ai_provider_labels())
        self.ai_provider_combo.currentIndexChanged.connect(self._on_ai_provider_changed)
        layout.addRow("AI 提供商:", self.ai_provider_combo)

        # API密钥（用于 OpenAI 和 Anthropic）
        self.api_key_edit = PasswordLineEdit()
        self.api_key_edit.setPlaceholderText("输入 OpenAI API密钥...")
        layout.addRow("API 密钥:", self.api_key_edit)

        # API地址
        self.api_base_edit = LineEdit()
        self.api_base_edit.setPlaceholderText("https://api.openai.com/v1")
        layout.addRow("API 地址:", self.api_base_edit)

        # 模型名称
        self.model_name_edit = LineEdit()
        self.model_name_edit.setPlaceholderText("gpt-4o")
        layout.addRow("模型名称:", self.model_name_edit)

        # Ollama地址
        self.ollama_url_edit = LineEdit()
        self.ollama_url_edit.setPlaceholderText("http://localhost:11434/v1")
        layout.addRow("Ollama 地址:", self.ollama_url_edit)

        # Ollama 模型
        self.ollama_model_combo = ComboBox()
        ollama_models = self._config.get_options("ollama_models")
        if ollama_models:
            self.ollama_model_combo.addItems(ollama_models)
        else:
            log_manager.warning("配置文件中未定义 ollama_models 选项")
        default_model = self._config.get_default("ai_settings/ollama_model_name")
        if default_model:
            self.ollama_model_combo.setPlaceholderText(default_model)
        layout.addRow("Ollama 模型:", self.ollama_model_combo)

        # 频率限制
        self.rate_limit_spin = SpinBox()
        self.rate_limit_spin.setRange(1, 1000)
        self.rate_limit_spin.setSuffix(" 次/小时")
        self._setup_spinbox_focus_policy(self.rate_limit_spin)
        layout.addRow("频率限制:", self.rate_limit_spin)

        # AI分析图像最大尺寸
        self.max_image_size_spin = SpinBox()
        self.max_image_size_spin.setRange(64, 4096)
        self.max_image_size_spin.setSuffix(" px")
        self.max_image_size_spin.setToolTip("AI分析时，若图像长或宽超过该值，将自动缩放至该尺寸（锁定宽高比）")
        self._setup_spinbox_focus_policy(self.max_image_size_spin)
        layout.addRow("图像最大尺寸:", self.max_image_size_spin)

        # API连通性测试
        self.ai_test_btn = PushButton(FluentIcon.SYNC, "测试API连接")
        self.ai_test_btn.clicked.connect(self._on_test_ai_clicked)
        layout.addRow("连接测试:", self.ai_test_btn)

        group_layout.addLayout(layout)

        self.scroll_layout.addWidget(group)

    def _create_storage_settings(self):
        """创建存储设置分组"""
        group = CardWidget(self.scroll_widget)
        group.setBorderRadius(8)
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(16, 16, 16, 16)
        group_layout.setSpacing(12)

        group_title = StrongBodyLabel("存储设置")
        group_layout.addWidget(group_title)

        layout = QFormLayout()
        layout.setSpacing(12)

        # 自动清理天数
        self.cleanup_days_spin = SpinBox()
        self.cleanup_days_spin.setRange(1, 365)
        self.cleanup_days_spin.setSuffix(" 天")
        self._setup_spinbox_focus_policy(self.cleanup_days_spin)
        layout.addRow("保留时间:", self.cleanup_days_spin)

        # 数据根目录
        root_layout = QHBoxLayout()
        self.data_root_dir_edit = LineEdit()
        self.data_root_dir_edit.setPlaceholderText("选择数据根目录...")
        self.data_root_dir_btn = PushButton(FluentIcon.FOLDER, "浏览")
        self.data_root_dir_btn.clicked.connect(self._browse_data_root_dir)
        root_layout.addWidget(self.data_root_dir_edit)
        root_layout.addWidget(self.data_root_dir_btn)
        layout.addRow("数据根目录:", root_layout)

        # 派生子路径（只读显示）
        self.derived_paths_label = BodyLabel()
        self.derived_paths_label.setTextColor(Qt.gray)
        layout.addRow("", self.derived_paths_label)

        # 立即清理按钮
        self.cleanup_btn = PrimaryPushButton(FluentIcon.DELETE, "立即清理旧记录")
        self.cleanup_btn.clicked.connect(self._on_cleanup_clicked)
        layout.addRow("数据清理:", self.cleanup_btn)

        # 数据迁移按钮
        self.migrate_btn = PrimaryPushButton(FluentIcon.SAVE_AS, "数据迁移")
        self.migrate_btn.clicked.connect(self._on_migrate_clicked)
        layout.addRow("数据迁移:", self.migrate_btn)

        group_layout.addLayout(layout)

        self.scroll_layout.addWidget(group)

    def _create_other_settings(self):
        """创建其他设置分组"""
        group = CardWidget(self.scroll_widget)
        group.setBorderRadius(8)
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(16, 16, 16, 16)
        group_layout.setSpacing(12)

        group_title = StrongBodyLabel("其他设置")
        group_layout.addWidget(group_title)

        layout = QFormLayout()
        layout.setSpacing(12)

        # 时区设置
        self.time_zone_combo = ComboBox()
        time_zone_options = [f"UTC{'' if i == 0 else '+' if i > 0 else ''}{i}" for i in range(-12, 13)]
        self.time_zone_combo.addItems(time_zone_options)
        self.time_zone_combo.setCurrentIndex(20)
        layout.addRow("时区设置:", self.time_zone_combo)

        group_layout.addLayout(layout)

        self.scroll_layout.addWidget(group)

    def _create_about_settings(self):
        """创建关于卡片，展示软件版本、开发团队、打赏二维码"""
        group = CardWidget(self.scroll_widget)
        group.setBorderRadius(8)
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(16, 16, 16, 16)
        group_layout.setSpacing(16)

        group_title = StrongBodyLabel("关于")
        group_layout.addWidget(group_title)

        hbox = QHBoxLayout()
        info_layout = QVBoxLayout()
        info_layout.setSpacing(8)

        app_name_label = QLabel(APP_DESCRIPTION)
        # app_name_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        info_layout.addWidget(app_name_label)

        version_label = QLabel(f"软件版本: v{__version__}")
        # version_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        info_layout.addWidget(version_label)
        
        opensource_label = QLabel(f"开源地址：{OPEN_SOURCE_URL}")
        # opensource_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        info_layout.addWidget(opensource_label)

        team_label = QLabel(f"开发团队：{APP_TEAM}")
        # team_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        info_layout.addWidget(team_label)

        hbox.addLayout(info_layout)
        hbox.addStretch()

        team_layout = QVBoxLayout()
        team_label = QLabel("支持我们")
        team_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        team_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        team_layout.addWidget(team_label)
        team_icon_label = QLabel()
        team_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        team_icon_label.setPixmap(self._read_image_150(TEAM_ICON_PATH))
        team_layout.addWidget(team_icon_label)
        hbox.addLayout(team_layout)
        
        donate_layout1 = QVBoxLayout()
        donate_wx_label = QLabel("打赏(微信)")
        donate_wx_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        donate_wx_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        donate_layout1.addWidget(donate_wx_label)
        qrcode_wx_label = QLabel()
        qrcode_wx_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qrcode_wx_label.setPixmap(self._read_image_150(DONATE_WX_PATH))
        donate_layout1.addWidget(qrcode_wx_label)
        hbox.addLayout(donate_layout1)
        
        donate_layout2 = QVBoxLayout()
        donate_ali_label = QLabel("打赏(支付宝)")
        donate_ali_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        donate_ali_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        donate_layout2.addWidget(donate_ali_label)
        qrcode_ali_label = QLabel()
        qrcode_ali_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qrcode_ali_label.setPixmap(self._read_image_150(DONATE_ALI_PATH))
        donate_layout2.addWidget(qrcode_ali_label)
        hbox.addLayout(donate_layout2)
        
        group_layout.addLayout(hbox)
        self.scroll_layout.addWidget(group)

    def _create_bottom_buttons(self):
        """创建底部保存和恢复默认按钮"""
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 16, 0, 0)

        self.save_btn = PrimaryPushButton(FluentIcon.SAVE, "保存设置")
        self.save_btn.clicked.connect(self._on_save_clicked)

        self.reset_btn = PushButton(FluentIcon.CANCEL, "恢复默认")
        self.reset_btn.clicked.connect(self._on_reset_clicked)

        bottom_layout.addStretch()
        bottom_layout.addWidget(self.reset_btn)
        bottom_layout.addWidget(self.save_btn)
        self.scroll_layout.addWidget(bottom_widget)

    def _load_settings(self):
        """从 Settings 加载当前设置到 UI 控件"""
        self.screenshot_interval_spin.setValue(
            self._config.get("screenshot_settings/screenshot_interval", 1)
        )
        self.screenshot_quality_spin.setValue(
            self._config.get("screenshot_settings/screenshot_quality", 85)
        )

        root_dir = self._config.get_data_root_dir()
        self.data_root_dir_edit.setText(str(Path(root_dir).resolve()))
        self._update_derived_paths_display(root_dir)

        self.image_play_interval_spin.setValue(
            self._config.get("image_settings/image_play_interval")
        )
        self.analysis_interval_spin.setValue(
            self._config.get("image_settings/ai_analysis_interval")
        )

        provider = self._config.get("ai_settings/ai_provider", "openai")
        provider_index = self.get_ai_provider_index(provider)
        self.ai_provider_combo.setCurrentIndex(provider_index)

        if provider == "openai":
            self.api_key_edit.setText(
                self._config.get("ai_settings/openai_api_key", "")
            )
            self.api_base_edit.setText(
                self._config.get("ai_settings/openai_api_base", "https://api.openai.com/v1")
            )
            self.model_name_edit.setText(
                self._config.get("ai_settings/openai_model_name", "gpt-4o")
            )
        elif provider == "anthropic":
            self.api_key_edit.setText(
                self._config.get("ai_settings/anthropic_api_key", "")
            )
            self.api_base_edit.setText(
                self._config.get("ai_settings/anthropic_api_base", "https://api.anthropic.com")
            )
            self.model_name_edit.setText(
                self._config.get("ai_settings/anthropic_model_name", "claude-3-5-sonnet-20241022")
            )
        elif provider == "local":
            self.api_key_edit.clear()
            self.api_base_edit.clear()
            self.model_name_edit.clear()
        else:
            self.api_key_edit.clear()
            self.api_base_edit.clear()
            self.model_name_edit.clear()

        self.ollama_url_edit.setText(
            self._config.get("ai_settings/ollama_base_url", "")
        )
        ollama_model = self._config.get("ai_settings/ollama_model_name", "")
        index = self.ollama_model_combo.findText(ollama_model)
        if index >= 0:
            self.ollama_model_combo.setCurrentIndex(index)
        self.rate_limit_spin.setValue(
            self._config.get("ai_settings/ai_rate_limit_per_hour")
        )
        self.max_image_size_spin.setValue(
            self._config.get("ai_settings/ai_analysis_max_image_size")
        )

        self.cleanup_days_spin.setValue(
            self._config.get("storage_settings/cleanup_days")
        )

        time_zone = self._config.get("other_settings/time_zone", 8)
        time_zone_index = int(time_zone) + 12
        if 0 <= time_zone_index <= 24:
            self.time_zone_combo.setCurrentIndex(time_zone_index)

        self._on_ai_provider_changed(provider_index)

        QTimer.singleShot(2000, self._auto_test_ai_on_startup)

    def _on_save_clicked(self):
        """保存设置按钮点击事件"""
        self._config.set("screenshot_settings/screenshot_interval", self.screenshot_interval_spin.value())
        self._config.set("screenshot_settings/screenshot_quality", self.screenshot_quality_spin.value())

        root_dir = self.data_root_dir_edit.text().strip()
        if root_dir:
            self._config.set_data_root_dir(root_dir)

        self._config.set("image_settings/image_play_interval", self.image_play_interval_spin.value())
        self._config.set("image_settings/ai_analysis_interval", self.analysis_interval_spin.value())

        provider_map = self.get_ai_provider_map()
        provider_key = provider_map.get(self.ai_provider_combo.currentIndex(), "openai")
        self._config.set("ai_settings/ai_provider", provider_key)

        if provider_key == "openai":
            self._config.set("ai_settings/openai_api_key", self.api_key_edit.text())
            self._config.set("ai_settings/openai_api_base", self.api_base_edit.text())
            self._config.set("ai_settings/openai_model_name", self.model_name_edit.text())
        elif provider_key == "anthropic":
            self._config.set("ai_settings/anthropic_api_key", self.api_key_edit.text())
            self._config.set("ai_settings/anthropic_api_base", self.api_base_edit.text())
            self._config.set("ai_settings/anthropic_model_name", self.model_name_edit.text())

        self._config.set("ai_settings/ollama_base_url", self.ollama_url_edit.text())
        self._config.set("ai_settings/ollama_model_name", self.ollama_model_combo.currentText())
        self._config.set("ai_settings/ai_rate_limit_per_hour", self.rate_limit_spin.value())
        self._config.set("ai_settings/ai_analysis_max_image_size", self.max_image_size_spin.value())

        self._config.set("storage_settings/cleanup_days", self.cleanup_days_spin.value())

        time_zone = self.time_zone_combo.currentIndex() - 12
        self._config.set("other_settings/time_zone", time_zone)

        log_manager.info("设置已保存")
        InfoBar.success(
            "保存成功",
            "所有设置已成功保存到配置文件",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self
        )

    def _on_reset_clicked(self):
        """恢复默认设置按钮点击事件"""
        w = MessageBox("确定要恢复所有设置为默认值吗？当前设置将被覆盖。", "确认恢复默认", self)
        w.yesButton.setText("确认恢复")
        w.cancelButton.setText("取消")
        if w.exec():
            self.screenshot_interval_spin.setValue(
                self._config.get_default("screenshot_settings/screenshot_interval")
            )
            self.screenshot_quality_spin.setValue(
                self._config.get_default("screenshot_settings/screenshot_quality")
            )

            default_root = self._config.get_default("storage_settings/data_root_dir", "~/.cache/ScreenLogger")
            self.data_root_dir_edit.setText(default_root)
            self._update_derived_paths_display(default_root)

            self.image_play_interval_spin.setValue(
                self._config.get_default("image_settings/image_play_interval")
            )
            self.analysis_interval_spin.setValue(
                self._config.get_default("image_settings/ai_analysis_interval")
            )
            
            default_provider = self._config.get_default("ai_settings/ai_provider")
            provider_index = self.get_ai_provider_index(default_provider)
            self.ai_provider_combo.setCurrentIndex(provider_index)
            
            self.api_key_edit.setText(
                self._config.get_default("ai_settings/openai_api_key", "")
            )
            self.api_base_edit.setText(
                self._config.get_default("ai_settings/openai_api_base", "https://api.openai.com/v1")
            )
            self.model_name_edit.setText(
                self._config.get_default("ai_settings/openai_model_name", "gpt-4o")
            )
            self.ollama_url_edit.setText(
                self._config.get_default("ai_settings/ollama_base_url")
            )
            
            default_model = self._config.get_default("ai_settings/ollama_model_name")
            index = self.ollama_model_combo.findText(default_model)
            if index >= 0:
                self.ollama_model_combo.setCurrentIndex(index)
            
            self.rate_limit_spin.setValue(
                self._config.get_default("ai_settings/ai_rate_limit_per_hour")
            )
            self.max_image_size_spin.setValue(
                self._config.get_default("ai_settings/ai_analysis_max_image_size", 1024)
            )
            self.cleanup_days_spin.setValue(
                self._config.get_default("storage_settings/cleanup_days")
            )

            self.time_zone_combo.setCurrentIndex(20)

            log_manager.info("设置已恢复默认值")
            InfoBar.info(
                "已恢复默认",
                "所有设置已恢复为默认值，请点击「保存设置」使其生效",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

    def _browse_data_root_dir(self):
        """浏览选择数据根目录"""
        path = QFileDialog.getExistingDirectory(self, "选择数据根目录")
        if path:
            self.data_root_dir_edit.setText(str(Path(path).resolve()))
            self._update_derived_paths_display(path)

    def _update_derived_paths_display(self, root_dir: str):
        """更新派生子路径的只读显示"""
        expanded = Path(root_dir).expanduser()
        sc_path = str((expanded / "screenshots").resolve())
        db_path = str((expanded / DB_FILENAME).resolve())
        log_path = str((expanded / "logs").resolve())
        self.derived_paths_label.setText(
            f"截图目录: {sc_path}\n数据库文件: {db_path}\n日志目录: {log_path}"
        )

    def _on_ai_provider_changed(self, index):
        """AI 提供商切换事件，根据选择显示/隐藏和更新相关设置"""
        key = self.get_ai_provider_key(index)

        is_openai = (key == "openai")
        is_anthropic = (key == "anthropic")
        is_cloud = (is_openai or is_anthropic)
        is_local = (key == "local")
        is_off = (key == "off")

        self.api_key_edit.setEnabled(is_cloud)
        self.api_base_edit.setEnabled(is_cloud)
        self.model_name_edit.setEnabled(is_cloud)
        self.ollama_url_edit.setEnabled(is_local)
        self.ollama_model_combo.setEnabled(is_local)
        self.rate_limit_spin.setEnabled(not is_off)
        self.max_image_size_spin.setEnabled(not is_off)

        if is_openai:
            self.api_key_edit.setPlaceholderText("输入 OpenAI API密钥...")
            self.api_base_edit.setPlaceholderText("https://api.openai.com/v1")
            self.model_name_edit.setPlaceholderText("gpt-4o")
            self.api_key_edit.setText(
                self._config.get("ai_settings/openai_api_key", "")
            )
            self.api_base_edit.setText(
                self._config.get("ai_settings/openai_api_base", "https://api.openai.com/v1")
            )
            self.model_name_edit.setText(
                self._config.get("ai_settings/openai_model_name", "gpt-4o")
            )
        elif is_anthropic:
            self.api_key_edit.setPlaceholderText("输入 Anthropic API密钥...")
            self.api_base_edit.setPlaceholderText("https://api.anthropic.com")
            self.model_name_edit.setPlaceholderText("claude-3-5-sonnet-20241022")
            self.api_key_edit.setText(
                self._config.get("ai_settings/anthropic_api_key", "")
            )
            self.api_base_edit.setText(
                self._config.get("ai_settings/anthropic_api_base", "https://api.anthropic.com")
            )
            self.model_name_edit.setText(
                self._config.get("ai_settings/anthropic_model_name", "claude-3-5-sonnet-20241022")
            )
        elif is_local:
            self.api_key_edit.clear()
            self.api_base_edit.clear()
            self.model_name_edit.clear()
        else:
            self.api_key_edit.clear()
            self.api_base_edit.clear()
            self.model_name_edit.clear()

    def _on_test_ai_clicked(self):
        """测试 API 连接按钮点击事件"""
        provider = self.get_ai_provider_key(self.ai_provider_combo.currentIndex())
        if provider == "off":
            InfoBar.warning(
                "AI 已关闭",
                "请先选择 AI 提供商后再测试",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            return

        self.ai_test_btn.setEnabled(False)
        self.ai_test_btn.setText("测试中...")

        config = self._build_test_config(provider)
        self._start_ai_test(provider, config, is_auto=False)

    def _build_test_config(self, provider: str) -> dict:
        """从当前 UI 控件收集配置，构建测试用配置字典"""
        config = {
            "ai_provider": provider,
            "ollama_base_url": self.ollama_url_edit.text(),
            "ollama_model_name": self.ollama_model_combo.currentText(),
            "ai_rate_limit_per_hour": self.rate_limit_spin.value(),
        }
        if provider == "openai":
            config["openai_api_key"] = self.api_key_edit.text()
            config["openai_api_base"] = self.api_base_edit.text()
            config["openai_model_name"] = self.model_name_edit.text()
        elif provider == "anthropic":
            config["anthropic_api_key"] = self.api_key_edit.text()
            config["anthropic_api_base"] = self.api_base_edit.text()
            config["anthropic_model_name"] = self.model_name_edit.text()
        return config

    def _start_ai_test(self, provider: str, config: dict, is_auto: bool):
        """在后台线程中执行API测试，通过信号传递结果回主线程"""
        def run():
            try:
                from openai import OpenAI
                test_prompt = "请直接回复'OK'来确认API连接正常，不要回复其他内容。"

                if provider == "openai":
                    api_key = config.get("openai_api_key", "")
                    if not api_key:
                        result = {"success": False, "message": "OpenAI API密钥未配置", "provider": "openai"}
                    else:
                        api_base = config.get("openai_api_base", "https://api.openai.com/v1")
                        model_name = config.get("openai_model_name", "gpt-4o")
                        client = OpenAI(api_key=api_key, base_url=api_base)
                        response = client.chat.completions.create(
                            model=model_name, messages=[{"role": "user", "content": test_prompt}], max_tokens=256,
                        )
                        text = ""
                        if response.choices:
                            content = response.choices[0].message.content
                            reasoning = getattr(response.choices[0].message, 'reasoning_content', None)
                            if not (content and content.strip()) and reasoning:
                                log_manager.info(f"OpenAI API响应content为空，reasoning内容: {reasoning[:200]}")
                            text = content.strip() if content else ""
                        result = {"success": bool(text), "message": f"连接成功: {text[:80]}" if text else "API返回空响应", "provider": "openai"}
                elif provider == "anthropic":
                    api_key = config.get("anthropic_api_key", "")
                    if not api_key:
                        result = {"success": False, "message": "Anthropic API密钥未配置", "provider": "anthropic"}
                    else:
                        import anthropic
                        api_base = config.get("anthropic_api_base", "https://api.anthropic.com")
                        model_name = config.get("anthropic_model_name", "claude-3-5-sonnet-20241022")
                        client = anthropic.Anthropic(api_key=api_key, base_url=api_base)
                        response = client.messages.create(
                            model=model_name, messages=[{"role": "user", "content": test_prompt}], max_tokens=256,
                        )
                        text = response.content[0].text.strip() if response.content else ""
                        result = {"success": bool(text), "message": f"连接成功: {text[:80]}" if text else "API返回空响应", "provider": "anthropic"}
                elif provider == "local":
                    ollama_url = config.get("ollama_base_url", "http://localhost:11434/v1")
                    ollama_model = config.get("ollama_model_name", "llava")
                    client = OpenAI(api_key="ollama", base_url=ollama_url)
                    response = client.chat.completions.create(
                        model=ollama_model, messages=[{"role": "user", "content": test_prompt}], max_tokens=256,
                    )
                    text = ""
                    if response.choices:
                        content = response.choices[0].message.content
                        reasoning = getattr(response.choices[0].message, 'reasoning_content', None)
                        if not (content and content.strip()) and reasoning:
                            log_manager.info(f"Local Ollama API响应content为空，reasoning内容: {reasoning[:200]}")
                        text = content.strip() if content else ""
                    result = {"success": bool(text), "message": f"连接成功: {text[:80]}" if text else "API返回空响应", "provider": "local"}
                else:
                    result = {"success": False, "message": f"未知提供商: {provider}", "provider": provider}
            except Exception as e:
                result = {"success": False, "message": str(e), "provider": provider}
            result["is_auto"] = is_auto
            self._test_signaler.result_ready.emit(result)

        threading.Thread(target=run, daemon=True).start()

    def _on_ai_test_result(self, result: dict):
        """API测试完成回调（主线程执行）"""
        is_auto = result.get("is_auto", False)
        provider_label = {
            "openai": "OpenAI",
            "anthropic": "Anthropic",
            "local": "本地"
        }.get(result.get("provider", ""), result.get("provider", ""))

        if not is_auto:
            self.ai_test_btn.setEnabled(True)
            self.ai_test_btn.setText("测试API连接")

        if result.get("success"):
            InfoBar.success(
                f"{provider_label} API连接测试通过",
                result.get("message", ""),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=10000,
                parent=self.parent()
            )
            log_manager.info(f"AI连接测试通过 [{provider_label}]: {result.get('message', '')}")
        else:
            if not is_auto:
                MessageBox(
                    f"{provider_label} API连接测试失败",
                    f"错误信息: {result.get('message', '未知错误')}\n\n请检查配置是否正确，网络是否可达。",
                    self
                ).exec()
            else:
                InfoBar.warning(
                    f"{provider_label} AI连接测试失败",
                    result.get('message', ''),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=5000,
                    parent=self
                )
            log_manager.warning(f"AI连接测试失败 [{provider_label}]: {result.get('message', '')}")

    def _auto_test_ai_on_startup(self):
        """启动时自动测试 AI 连接"""
        provider_map = self.get_ai_provider_map()
        provider = provider_map.get(self.ai_provider_combo.currentIndex(), "off")
        if provider == "off":
            return
        config = self._build_test_config(provider)
        self._start_ai_test(provider, config, is_auto=True)

    def _on_cleanup_clicked(self):
        """手动清理按钮点击事件"""
        if self.main_window and self.main_window.storage_manager:
            days = self.cleanup_days_spin.value()
            self.main_window.storage_manager.cleanup_old_records(days)
            log_manager.info(f"手动触发数据清理，保留{days}天内的记录")
            InfoBar.info(
                "清理已开始",
                f"正在清理{days}天前的旧记录...",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

    def _on_migrate_clicked(self):
        """数据迁移按钮点击事件"""
        root_path = QFileDialog.getExistingDirectory(self, "选择新的数据根目录")
        if not root_path:
            return

        if not self.main_window or not self.main_window.storage_manager:
            return

        if self.main_window.screen_capture.is_recording:
            log_manager.info("迁移前停止录制")
            self.main_window.screen_capture.stop()

        self.main_window.storage_manager.migrate_data(root_path)
        log_manager.info("数据迁移已开始")
        InfoBar.info(
            "迁移已开始",
            "录制已自动停止，正在将整个数据根目录迁移到新位置...",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self
        )
    
    def _read_image_150(self, qrc_path: str) -> QPixmap:
        """读取图片文件"""
        pixmap = QPixmap(qrc_path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        else:
            pixmap = QPixmap(150, 150)
            pixmap.fill(Qt.GlobalColor.white)
            log_manager.error(f"图片加载失败: {qrc_path}")
        return pixmap