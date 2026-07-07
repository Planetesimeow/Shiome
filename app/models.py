from pydantic import BaseModel
from typing import Literal, Optional

# v1.0.0 只有 douyin；小红书/B站 v2.0.0 接入时在这里加值即可
Platform = Literal["douyin", "xiaohongshu", "bilibili"]


class VideoIn(BaseModel):
    platform: Platform = "douyin"
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


# ---------- vision 截图确认入库 ----------

class VisionVideoIn(BaseModel):
    """从截图提取、经用户确认的一条视频数据。全部可空——布局不同可见字段就不同。"""
    status: str = "已发布"                 # 私密 会被服务端拒绝入库
    title: Optional[str] = None
    publish_datetime: Optional[str] = None  # "YYYY-MM-DD HH:MM" 或 "YYYY-MM-DD"
    duration_sec: Optional[int] = None
    plays: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    saves: Optional[int] = None
    danmaku_count: Optional[int] = None
    completion_rate: Optional[float] = None
    bounce_2s_rate: Optional[float] = None
    avg_watch_time: Optional[float] = None
    cover_ctr: Optional[float] = None
    new_followers: Optional[int] = None
    unfollows: Optional[int] = None
    fan_conversion_rate: Optional[float] = None


class AccountMetricsIn(BaseModel):
    period: Optional[str] = None
    plays: Optional[int] = None
    profile_visits: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    net_followers: Optional[int] = None
    unfollows: Optional[int] = None
    completion_rate: Optional[float] = None
    search_views: Optional[int] = None
    cover_ctr: Optional[float] = None
    danmaku: Optional[int] = None
    peer_percentiles: Optional[dict] = None


class CurveObservationIn(BaseModel):
    visible: bool = False
    granularity: Optional[str] = None
    shape_description: Optional[str] = None
    pattern_guess: Optional[str] = None


class VisionSaveIn(BaseModel):
    """确认面板提交的最终数据。videos 里 status=私密 的条目服务端直接跳过。"""
    page_type: str
    videos: list[VisionVideoIn] = []
    account: Optional[AccountMetricsIn] = None
    curve_observation: Optional[CurveObservationIn] = None
    checked_at: Optional[str] = None      # 详情页快照的观察时间，默认当前时间
