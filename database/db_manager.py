"""
数据库管理器
封装 SQLAlchemy 操作，提供会话管理及完整的增删改查方法。
"""
import json
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, date as date_type
from pathlib import Path
from typing import List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from database.models import (
    Base, ScreenshotRecord, ActivityRecord, ClassificationTag,
    DailySummary, AlarmConfig,
)
from logger import log_manager


class DatabaseManager:
    """
    数据库管理器
    负责数据库引擎创建、会话管理，并提供所有实体的增删改查方法。
    """

    def __init__(self, db_path: str = None):
        """
        初始化数据库管理器
        :param db_path: 数据库文件路径，默认使用用户目录下的 .cache/{DEFAULT_ROOT_DIR_NAME}/{DB_FILENAME}
        """
        if db_path is None:
            from config import Settings
            db_path = Settings().get_db_path()
        self._db_path = db_path
        self._init_engine()

    def _init_engine(self):
        """根据当前 _db_path 创建引擎和会话工厂"""
        db_dir = os.path.dirname(self._db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._engine = create_engine(f"sqlite:///{self._db_path}", echo=False)
        self._session_factory = sessionmaker(bind=self._engine)

    def reconnect(self, db_path: str):
        """
        重新连接到新数据库文件（数据迁移后使用）

        仅销毁旧引擎并创建新引擎指向新路径，不新建数据库文件。
        新数据库文件应由迁移逻辑提前复制到目标位置。

        Args:
            db_path: 新的数据库文件路径
        """
        normalized = os.path.normpath(os.path.expanduser(db_path))
        if not os.path.isfile(normalized):
            log_manager.warning(f"目标数据库文件不存在（可能迁移未完成），将创建新文件: {normalized}")
        if self._engine:
            self._engine.dispose()
        self._db_path = normalized
        self._init_engine()
        log_manager.info(f"数据库已重新连接到: {normalized}")

    def init_db(self):
        """创建所有数据库表并执行迁移"""
        Base.metadata.create_all(self._engine)
        self._migrate_database()

    def _migrate_database(self):
        """
        数据库迁移逻辑
        处理从旧版（含video_records）到新版（仅截图）的变更
        """
        from sqlalchemy import inspect, text

        try:
            inspector = inspect(self._engine)
            columns = [col['name'] for col in inspector.get_columns('activity_records')]

            if 'description' not in columns:
                with self._engine.connect() as conn:
                    conn.execute(text("ALTER TABLE activity_records ADD COLUMN description VARCHAR(512) DEFAULT ''"))
                    conn.commit()
                log_manager.info("数据库迁移完成：为 activity_records 添加 description 列")

            if 'video_id' in columns and 'screenshot_id' not in columns:
                with self._engine.connect() as conn:
                    conn.execute(text("ALTER TABLE activity_records ADD COLUMN screenshot_id INTEGER REFERENCES screenshot_records(id)"))
                    conn.commit()
                log_manager.info("数据库迁移完成：为 activity_records 添加 screenshot_id 列")
        except Exception as e:
            log_manager.error(f"数据库迁移失败：{e}")

    @contextmanager
    def get_session(self, expire_on_commit: bool = True) -> Session:
        """
        返回一个新的 session 上下文管理器
        用法: with db_manager.get_session() as session: ...
        :param expire_on_commit: 是否在提交后过期对象，查询数据时设为False避免分离对象问题
        """
        session = self._session_factory()
        if not expire_on_commit:
            session.expire_on_commit = False
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ==================== 截图记录 CRUD ====================

    def add_screenshot(self, filepath: str, timestamp: datetime,
                       window_title: str = "", monitor_index: int = 0) -> ScreenshotRecord:
        """添加一条截图记录"""
        with self.get_session(expire_on_commit=False) as session:
            record = ScreenshotRecord(
                filepath=filepath,
                timestamp=timestamp,
                window_title=window_title,
                monitor_index=monitor_index,
            )
            session.add(record)
            session.flush()
            return record

    def get_screenshots_in_range(self, start_time: datetime, end_time: datetime) -> List[ScreenshotRecord]:
        """获取指定时间范围内的截图记录"""
        with self.get_session(expire_on_commit=False) as session:
            return session.query(ScreenshotRecord).filter(
                ScreenshotRecord.timestamp >= start_time,
                ScreenshotRecord.timestamp <= end_time,
            ).order_by(ScreenshotRecord.timestamp).all()

    def get_screenshots_by_ids(self, screenshot_ids: List[int]) -> List[ScreenshotRecord]:
        """根据ID列表获取截图记录"""
        with self.get_session(expire_on_commit=False) as session:
            return session.query(ScreenshotRecord).filter(
                ScreenshotRecord.id.in_(screenshot_ids)
            ).order_by(ScreenshotRecord.timestamp).all()

    def get_screenshot_count_in_range(self, start_time: datetime, end_time: datetime) -> int:
        """获取指定时间范围内的截图总数"""
        with self.get_session(expire_on_commit=False) as session:
            return session.query(ScreenshotRecord).filter(
                ScreenshotRecord.timestamp >= start_time,
                ScreenshotRecord.timestamp <= end_time,
            ).count()

    def delete_screenshots_older_than(self, days: int) -> int:
        """删除超过指定天数的截图记录，返回删除数量"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = today - timedelta(days=days)
        with self.get_session() as session:
            count = session.query(ScreenshotRecord).filter(
                ScreenshotRecord.timestamp < cutoff
            ).delete()
            return count

    # ==================== 活动记录 CRUD ====================

    def add_activity(self, start_time: datetime, end_time: datetime,
                     activity_type: str, window_title: str = "",
                     screenshot_id: Optional[int] = None, confidence: float = 1.0,
                     description: str = "") -> ActivityRecord:
        """添加一条活动记录"""
        with self.get_session(expire_on_commit=False) as session:
            record = ActivityRecord(
                start_time=start_time,
                end_time=end_time,
                activity_type=activity_type,
                window_title=window_title,
                screenshot_id=screenshot_id,
                confidence=confidence,
                description=description,
            )
            session.add(record)
            session.flush()
            return record

    def get_activities_in_range(self, start_time: datetime, end_time: datetime) -> List[ActivityRecord]:
        """获取指定时间范围内的活动记录"""
        with self.get_session(expire_on_commit=False) as session:
            return session.query(ActivityRecord).filter(
                ActivityRecord.start_time >= start_time,
                ActivityRecord.start_time <= end_time,
            ).order_by(ActivityRecord.start_time).all()

    def get_activities_by_screenshot_id(self, screenshot_id: int) -> List[ActivityRecord]:
        """获取指定截图ID关联的活动记录"""
        with self.get_session(expire_on_commit=False) as session:
            return session.query(ActivityRecord).filter(
                ActivityRecord.screenshot_id == screenshot_id,
            ).order_by(ActivityRecord.start_time).all()

    def update_activity_type(self, activity_id: int, new_type: str) -> None:
        """更新指定活动的类型"""
        with self.get_session() as session:
            session.query(ActivityRecord).filter(
                ActivityRecord.id == activity_id
            ).update({"activity_type": new_type})

    def update_activity_description(self, activity_id: int, description: str) -> None:
        """更新指定活动的描述"""
        with self.get_session() as session:
            session.query(ActivityRecord).filter(
                ActivityRecord.id == activity_id
            ).update({"description": description})

    def update_activity_end_time(self, activity_id: int, end_time: datetime) -> None:
        """更新指定活动的结束时间"""
        with self.get_session() as session:
            session.query(ActivityRecord).filter(
                ActivityRecord.id == activity_id
            ).update({"end_time": end_time})

    def delete_activities_by_ids(self, activity_ids: list) -> int:
        """批量删除指定ID的活动记录，返回删除数量"""
        with self.get_session() as session:
            count = session.query(ActivityRecord).filter(
                ActivityRecord.id.in_(activity_ids)
            ).delete(synchronize_session='fetch')
            return count

    def delete_activities_older_than(self, days: int) -> int:
        """删除超过指定天数的活动记录，返回删除数量"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = today - timedelta(days=days)
        with self.get_session() as session:
            count = session.query(ActivityRecord).filter(
                ActivityRecord.start_time < cutoff
            ).delete()
            return count

    # ==================== 分类标签 CRUD ====================

    def add_tag(self, name: str, color: str = "#4CAF50", is_preset: bool = False,
                pattern: str = None, description: str = "") -> ClassificationTag:
        """添加一个分类标签"""
        with self.get_session() as session:
            tag = ClassificationTag(
                name=name,
                color=color,
                is_preset=is_preset,
                pattern=pattern,
                description=description,
            )
            session.add(tag)
            session.flush()
            return tag

    def update_tag(self, tag_id: int, **kwargs) -> None:
        """更新指定标签的属性"""
        with self.get_session() as session:
            session.query(ClassificationTag).filter(
                ClassificationTag.id == tag_id
            ).update(kwargs)

    def delete_tag(self, tag_id: int) -> None:
        """删除指定标签"""
        with self.get_session() as session:
            session.query(ClassificationTag).filter(
                ClassificationTag.id == tag_id
            ).delete()

    def get_all_tags(self) -> List[ClassificationTag]:
        """获取所有分类标签"""
        with self.get_session(expire_on_commit=False) as session:
            return session.query(ClassificationTag).all()

    def get_preset_tags(self) -> List[ClassificationTag]:
        """获取所有预设标签"""
        with self.get_session(expire_on_commit=False) as session:
            return session.query(ClassificationTag).filter(
                ClassificationTag.is_preset == True
            ).all()

    # ==================== 每日总结 CRUD ====================

    def save_daily_summary(self, target_date: date_type, content_html: str) -> None:
        """保存或更新指定日期的每日总结"""
        with self.get_session() as session:
            existing = session.query(DailySummary).filter(
                DailySummary.date == target_date
            ).first()
            if existing:
                existing.content_html = content_html
                existing.updated_at = datetime.now()
            else:
                session.add(DailySummary(
                    date=target_date,
                    content_html=content_html,
                ))

    def get_daily_summary(self, target_date: date_type) -> Optional[str]:
        """获取指定日期的每日总结内容，不存在返回 None"""
        with self.get_session(expire_on_commit=False) as session:
            record = session.query(DailySummary).filter(
                DailySummary.date == target_date
            ).first()
            return record.content_html if record else None

    def delete_daily_summaries_older_than(self, days: int) -> int:
        """删除超过指定天数的每日总结记录，返回删除数量"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff_date = today.date() - timedelta(days=days)
        with self.get_session() as session:
            count = session.query(DailySummary).filter(
                DailySummary.date < cutoff_date
            ).delete()
            return count

    # ==================== 闹钟配置 CRUD ====================

    def save_alarm_config(self, alarm_data_dict: dict) -> None:
        """保存或更新一条闹钟配置"""
        with self.get_session() as session:
            existing = session.query(AlarmConfig).filter(
                AlarmConfig.alarm_id == alarm_data_dict["alarm_id"]
            ).first()
            if existing:
                for key, value in alarm_data_dict.items():
                    if key in ("created_at",):
                        continue
                    setattr(existing, key, value)
                existing.updated_at = datetime.now()
            else:
                session.add(AlarmConfig(**alarm_data_dict))

    def get_all_alarm_configs(self) -> List[AlarmConfig]:
        """获取所有闹钟配置"""
        with self.get_session(expire_on_commit=False) as session:
            return session.query(AlarmConfig).order_by(AlarmConfig.created_at).all()

    def get_alarm_config(self, alarm_id: str) -> Optional[AlarmConfig]:
        """根据 alarm_id 获取单条闹钟配置"""
        with self.get_session(expire_on_commit=False) as session:
            return session.query(AlarmConfig).filter(
                AlarmConfig.alarm_id == alarm_id
            ).first()

    def delete_alarm_config(self, alarm_id: str) -> None:
        """删除指定闹钟配置"""
        with self.get_session() as session:
            session.query(AlarmConfig).filter(
                AlarmConfig.alarm_id == alarm_id
            ).delete()

    def delete_all_alarm_configs(self) -> None:
        """删除所有闹钟配置"""
        with self.get_session() as session:
            session.query(AlarmConfig).delete()

    def close(self):
        """关闭数据库引擎"""
        self._engine.dispose()
