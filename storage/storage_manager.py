"""
存储管理模块
负责存储清理、数据迁移和存储统计。
支持按时间清理过期记录，以及数据库与媒体文件的整体迁移。
"""
import os
import shutil
from datetime import datetime, timedelta
from typing import Dict

from PySide6.QtCore import QObject, Signal

from config import Settings
from config.config_manager import DEFAULT_ROOT_DIR_NAME
from database import DatabaseManager
from logger import log_manager
from config.config_manager import DB_FILENAME



class StorageManager(QObject):
    """
    存储管理类
    提供数据清理、迁移和存储统计功能。
    """

    # 清理完成信号：删除的记录数
    cleanup_complete = Signal(int)
    # 迁移完成信号
    migration_complete = Signal()
    # 存储错误信号：错误信息
    storage_error = Signal(str)

    def __init__(self, config_manager: Settings, db_manager: DatabaseManager):
        """
        初始化存储管理器

        Args:
            config_manager: 配置管理实例
            db_manager: 数据库管理实例
        """
        super().__init__()
        self._config = config_manager
        self._db = db_manager

    def cleanup_old_records(self, days: int = None):
        """
        清理超过指定天数的记录

        依次执行：
        1. 删除过期的截图磁盘文件
        2. 删除数据库中过期的截图记录
        3. 删除数据库中过期的活动记录

        Args:
            days: 保留天数，默认使用配置中的 cleanup_days
        """
        if days is None:
            days = self._config.get("storage_settings/cleanup_days", 7)

        if days <= 0:
            log_manager.warning(f"清理天数无效: {days}，跳过清理")
            return

        cutoff = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)
        log_manager.info(f"开始清理 {days} 天前的记录，截止时间: {cutoff.isoformat()}")

        deleted_file_count = 0
        deleted_db_count = 0

        try:
            old_screenshots = self._db.get_screenshots_in_range(
                datetime(2000, 1, 1), cutoff
            )
            for s in old_screenshots:
                filepath = getattr(s, "filepath", None) or getattr(s, "file_path", None)
                if filepath and os.path.isfile(filepath):
                    try:
                        os.remove(filepath)
                        deleted_file_count += 1
                        log_manager.debug(f"已删除截图文件: {filepath}")
                    except OSError as e:
                        log_manager.warning(f"删除截图文件失败: {filepath}, 错误: {str(e)}")
                        self.storage_error.emit(f"删除截图文件失败: {filepath}")
        except Exception as e:
            log_manager.error(f"获取旧截图记录失败: {str(e)}")
            self.storage_error.emit(f"获取旧截图记录失败: {str(e)}")
            return

        try:
            deleted_db_count += self._db.delete_screenshots_older_than(days)
            deleted_db_count += self._db.delete_activities_older_than(days)
            deleted_db_count += self._db.delete_daily_summaries_older_than(days)
        except Exception as e:
            log_manager.error(f"删除数据库旧记录失败: {str(e)}")
            self.storage_error.emit(f"删除数据库旧记录失败: {str(e)}")
            return

        total = deleted_file_count + deleted_db_count
        log_manager.info(f"清理完成: 删除 {deleted_file_count} 个文件, {deleted_db_count} 条数据库记录, 共 {total} 项")
        self.cleanup_complete.emit(total)

    def migrate_data(self, new_parent_dir: str):
        """
        数据迁移：将整个数据根目录迁移到新位置（新建 {appname} 子目录）

        自动完成：
        1. 在所选路径下新建 {DEFAULT_ROOT_DIR_NAME} 子目录
        2. 复制根目录下所有内容（screenshots/、*.db、logs/ 等）到子目录
        3. 更新配置中的 data_root_dir
        4. 重新连接数据库到新位置
        5. 重新配置日志输出到新位置
        6. 迁移成功后删除旧缓存文件夹

        Args:
            new_parent_dir: 新数据根目录的父路径（将在其下创建 {DEFAULT_ROOT_DIR_NAME} 子目录）
        """
        try:
            old_root_dir = self._config.get_data_root_dir()
            expanded_parent = os.path.normpath(os.path.expanduser(new_parent_dir))
            expanded_new = os.path.join(expanded_parent, DEFAULT_ROOT_DIR_NAME)
            expanded_old = os.path.normpath(os.path.expanduser(old_root_dir))

            if not os.path.isdir(expanded_old):
                error_msg = f"旧数据根目录不存在: {expanded_old}"
                log_manager.error(error_msg)
                self.storage_error.emit(error_msg)
                return

            if expanded_new == expanded_old:
                log_manager.info("新旧目录相同，跳过迁移")
                self.migration_complete.emit()
                return

            log_manager.info(f"开始迁移数据根目录: {expanded_old} -> {expanded_new}")

            self._db.close()

            os.makedirs(expanded_new, exist_ok=True)
            self._copy_directory(expanded_old, expanded_new)

            self._config.set_data_root_dir(expanded_new)

            new_db_path = os.path.join(expanded_new, DB_FILENAME)
            self._db.reconnect(new_db_path)

            new_log_dir = os.path.join(expanded_new, "logs")
            log_manager.reconfigure(new_log_dir)

            log_manager.info(f"数据迁移完成，新根目录: {expanded_new}")
            log_manager.info(f"正在删除旧缓存文件夹: {expanded_old}")
            try:
                shutil.rmtree(expanded_old)
                log_manager.info(f"旧缓存文件夹已删除: {expanded_old}")
            except Exception as e:
                log_manager.warning(f"删除旧缓存文件夹失败（可手动删除）: {expanded_old}, 错误: {str(e)}")

            self.migration_complete.emit()

        except Exception as e:
            error_msg = f"数据迁移失败: {str(e)}"
            log_manager.error(error_msg)
            self.storage_error.emit(error_msg)

    def get_storage_stats(self) -> Dict:
        """
        获取存储统计信息

        Returns:
            dict: 包含截图总数、占用空间等统计信息
        """
        stats = {
            "screenshot_count": 0,
            "screenshot_size_bytes": 0,
            "total_size_bytes": 0,
            "total_size_mb": 0.0,
        }

        screenshot_path = self._config.get_screenshot_path()
        if os.path.isdir(screenshot_path):
            for root, dirs, files in os.walk(screenshot_path):
                for f in files:
                    filepath = os.path.join(root, f)
                    try:
                        size = os.path.getsize(filepath)
                        stats["screenshot_size_bytes"] += size
                        stats["screenshot_count"] += 1
                    except OSError:
                        pass

        stats["total_size_bytes"] = stats["screenshot_size_bytes"]
        stats["total_size_mb"] = round(stats["total_size_bytes"] / (1024 * 1024), 2)

        log_manager.debug(f"存储统计: {stats}")
        return stats

    def _copy_directory(self, src: str, dst: str):
        """
        复制整个目录到新路径（使用 shutil.copytree）

        Args:
            src: 源目录路径
            dst: 目标目录路径
        """
        if not os.path.isdir(src):
            log_manager.warning(f"源目录不存在: {src}")
            return

        shutil.copytree(src, dst, dirs_exist_ok=True)
        log_manager.debug(f"已复制目录: {src} -> {dst}")