"""
配置管理模块
使用 PySide6 的 QSettings 读写配置，采用单例模式确保全局唯一配置实例。
"""
import json
import os
from pathlib import Path
from PySide6.QtCore import QSettings


def singleton(cls):
    instances = {}
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    return get_instance


DEFAULT_ROOT_DIR_NAME = "ScreenLogger"
SUBDIR_SCREENSHOTS = "screenshots"
SUBDIR_LOGS = "logs"
DB_FILENAME = "screenlogger.db"


@singleton
class Settings:
    """应用设置管理器（单例），基于 QSettings 读写 ini 配置文件"""

    def __init__(self):
        config_dir = Path(__file__).parent.parent / "conf"
        config_dir.mkdir(exist_ok=True)
        settings_path = config_dir / "settings.ini"
        self._settings = QSettings(str(settings_path), QSettings.IniFormat)
        if not settings_path.exists():
            self._init_defaults()
            self._settings.sync()

        self._auto_migrate_old_paths()

    def _auto_migrate_old_paths(self):
        """自动迁移旧配置：若不存在 data_root_dir，从旧路径推断并设置"""
        if self._settings.value("storage_settings/data_root_dir", ""):
            return
        old_sc_path = self._settings.value("image_settings/screenshot_path", "")
        if old_sc_path and old_sc_path.endswith(SUBDIR_SCREENSHOTS):
            inferred = os.path.dirname(old_sc_path)
            self._settings.setValue("storage_settings/data_root_dir", inferred)

    def _init_defaults(self):
        default_path = Path(__file__).parent.parent / "conf" / "settings_default.ini"
        if not default_path.exists():
            return
        qs = QSettings(str(default_path), QSettings.IniFormat)
        for key in qs.allKeys():
            if not key.startswith("options/"):
                self._settings.setValue(key, qs.value(key))

    def get(self, key, default=None):
        if isinstance(default, dict):
            value = self._settings.value(key, "{}", str)
            return json.loads(value)
        value = self._settings.value(key, default)
        if isinstance(value, str):
            for conv in (int, float):
                try:
                    return conv(value)
                except (ValueError, TypeError):
                    continue
        return value

    def set(self, key, value):
        if isinstance(value, dict):
            value = json.dumps(value, ensure_ascii=False)
        self._settings.setValue(key, value)

    @staticmethod
    def get_default(key, default=None):
        default_path = Path(__file__).parent.parent / "conf" / "settings_default.ini"
        if not default_path.exists():
            return default
        qs = QSettings(str(default_path), QSettings.IniFormat)
        value = qs.value(key, default)
        if isinstance(value, str):
            for conv in (int, float):
                try:
                    return conv(value)
                except (ValueError, TypeError):
                    continue
        return value

    @staticmethod
    def get_options(key) -> list:
        default_path = Path(__file__).parent.parent / "conf" / "settings_default.ini"
        if not default_path.exists():
            return []
        qs = QSettings(str(default_path), QSettings.IniFormat)
        value = qs.value(f"options/{key}", "")
        if isinstance(value, list):
            return [str(opt).strip() for opt in value if str(opt).strip()]
        if isinstance(value, str) and value:
            return [opt.strip() for opt in value.split(",") if opt.strip()]
        return []

    def get_data_root_dir(self) -> str:
        """获取数据根目录（~/.cache/ScreenLogger），若配置中未设置则使用默认值，目录不存在时自动创建"""
        path = self._settings.value("storage_settings/data_root_dir", "")
        if not path:
            path = os.path.join(str(Path.home()), ".cache", DEFAULT_ROOT_DIR_NAME)
        path = os.path.expanduser(path)
        os.makedirs(path, exist_ok=True)
        return path

    def set_data_root_dir(self, path: str):
        """设置数据根目录到配置文件"""
        self._settings.setValue("storage_settings/data_root_dir", path)

    def get_screenshot_path(self) -> str:
        """获取截图存储目录（根目录/screenshots），自动创建"""
        root = self.get_data_root_dir()
        path = os.path.join(root, SUBDIR_SCREENSHOTS)
        os.makedirs(path, exist_ok=True)
        return path

    def get_db_path(self) -> str:
        """获取数据库文件路径（根目录/{DB_FILENAME}），自动创建目录"""
        root = self.get_data_root_dir()
        os.makedirs(root, exist_ok=True)
        return os.path.join(root, DB_FILENAME)

    def get_log_dir(self) -> str:
        """获取日志存储目录（根目录/logs），自动创建"""
        root = self.get_data_root_dir()
        path = os.path.join(root, SUBDIR_LOGS)
        os.makedirs(path, exist_ok=True)
        return path