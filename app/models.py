from pydantic import BaseModel
from typing import Optional


class VideoIn(BaseModel):
    douyin_video_id: Optional[str] = None
    title: str
    publish_date: str  # "YYYY-MM-DD"
    duration_sec: Optional[int] = None
    plays: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    completion_rate: Optional[float] = None
    avg_watch_time: Optional[float] = None
    profile_visits: int = 0
    new_followers: int = 0
    high_intent_comments: int = 0
    high_intent_dms: int = 0
    notes: Optional[str] = None
    content_summary: Optional[str] = None
    on_screen_text: Optional[str] = None
    music: Optional[str] = None
    hook_description: Optional[str] = None
    content_pillar: Optional[str] = None


class ContentProfileIn(BaseModel):
    """更新单条视频的内容画像字段，创作者中心导不出来，靠手动填。"""
    content_summary: Optional[str] = None
    on_screen_text: Optional[str] = None
    music: Optional[str] = None
    hook_description: Optional[str] = None
    content_pillar: Optional[str] = None


class SnapshotIn(BaseModel):
    """记录一个时间点的快照，用于流量池定位分析。checked_at 不填就用当前时间。"""
    checked_at: Optional[str] = None
    plays: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    completion_rate: Optional[float] = None
    profile_visits: int = 0
    new_followers: int = 0


class AnomalyPeriodIn(BaseModel):
    start_date: str
    end_date: str
    reason: str


class AnalysisRequest(BaseModel):
    video_id: int
