"""
SQLAlchemy ORM 模型定义
定义截图记录、活动记录、分类标签、每日总结和闹钟配置数据模型。
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, ForeignKey, Text, Date, create_engine
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class ScreenshotRecord(Base):
    """
    截图记录表
    存储每次截图的文件路径、时间戳及关联窗口信息。
    """
    __tablename__ = "screenshot_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filepath = Column(String(512), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.now)
    window_title = Column(String(256), nullable=False, default="")
    monitor_index = Column(Integer, nullable=False, default=0)

    def __repr__(self):
        return f"<ScreenshotRecord(id={self.id}, timestamp={self.timestamp}, filepath={self.filepath})>"


class ActivityRecord(Base):
    """
    活动记录表
    存储每个时间段的活动类型及关联窗口信息。
    """
    __tablename__ = "activity_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    activity_type = Column(String(64), nullable=False)
    window_title = Column(String(256), nullable=False, default="")
    description = Column(String(512), nullable=True, default="")
    screenshot_id = Column(Integer, ForeignKey("screenshot_records.id"), nullable=True)
    confidence = Column(Float, nullable=False, default=1.0)

    screenshot = relationship("ScreenshotRecord", backref="activities")

    def __repr__(self):
        return f"<ActivityRecord(id={self.id}, type={self.activity_type}, start={self.start_time})>"


class ClassificationTag(Base):
    """
    分类标签表
    存储用户自定义或预设的活动分类标签，支持基于窗口标题模式匹配的分类规则。
    """
    __tablename__ = "classification_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False)
    color = Column(String(9), nullable=False, default="#4CAF50")
    is_preset = Column(Boolean, nullable=False, default=False)
    pattern = Column(String(256), nullable=True)
    description = Column(String(512), nullable=True, default="")

    def __repr__(self):
        return f"<ClassificationTag(id={self.id}, name={self.name}, is_preset={self.is_preset})>"


class DailySummary(Base):
    """
    每日总结表
    每天一条，存储 AI 生成的当日活动总结内容（HTML 格式）。
    """
    __tablename__ = "daily_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, unique=True, nullable=False, index=True)
    content_html = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f"<DailySummary(date={self.date})>"


class AlarmConfig(Base):
    """
    闹钟配置表
    存储每个闹钟的完整配置数据。
    """
    __tablename__ = "alarm_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alarm_id = Column(String(64), unique=True, nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    mode = Column(String(16), nullable=False, default="single")
    message = Column(String(10), nullable=False, default="⏰ 时间到！")
    countdown_seconds = Column(Integer, nullable=False, default=10)
    hour = Column(Integer, nullable=False, default=9)
    minute = Column(Integer, nullable=False, default=0)
    days_of_week = Column(String(20), nullable=False, default="[0,1,2,3,4]")
    start_hour = Column(Integer, nullable=False, default=8)
    start_minute = Column(Integer, nullable=False, default=0)
    end_hour = Column(Integer, nullable=False, default=22)
    end_minute = Column(Integer, nullable=False, default=0)
    interval_minutes = Column(Integer, nullable=False, default=60)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f"<AlarmConfig(alarm_id={self.alarm_id}, mode={self.mode})>"