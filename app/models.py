"""
请求/响应模型。

v2 的实体拆分体现在这里：creative（你做的东西）和 post（发到某个平台的那次）
是两个不同的模型，内容画像字段只出现在 CreativeIn 上 —— 一条视频发三个平台，
这些字段填一次。
"""
from pydantic import BaseModel
from typing import Literal, Optional

# v1.0.0 只有 douyin；小红书 Phase 3、B站 Phase 4
Platform = Literal["douyin", "xiaohongshu", "bilibili"]
MediaType = Literal["video", "image_text"]


# ---------- 账号 ----------

class AccountIn(BaseModel):
    platform: Platform = "douyin"
    handle: Optional[str] = None
    display_name: Optional[str] = None
    persona: Optional[str] = None      # 账号人设，喂给所有分析 prompt
    goal_note: Optional[str] = None    # 这个账号的"成功"怎么定义


class AccountPatch(BaseModel):
    handle: Optional[str] = None
    display_name: Optional[str] = None
    persona: Optional[str] = None
    goal_note: Optional[str] = None


# ---------- 创作物（内容画像住在这里）----------

class CreativeIn(BaseModel):
    label: Optional[str] = None
    media_type: MediaType = "video"
    duration_sec: Optional[int] = None
    content_summary: Optional[str] = None
    on_screen_text: Optional[str] = None
    music: Optional[str] = None
    hook_description: Optional[str] = None
    content_pillar: Optional[str] = None


class CreativePatch(BaseModel):
    """
    部分更新。字段传了空字符串就是真的清空 —— 前端表单显示的一直是库里的当前值，
    "清空后保存"就该真的清空，不能被当成"没传"而保留旧值。
    """
    label: Optional[str] = None
    media_type: Optional[MediaType] = None
    duration_sec: Optional[int] = None
    content_summary: Optional[str] = None
    on_screen_text: Optional[str] = None
    music: Optional[str] = None
    hook_description: Optional[str] = None
    content_pillar: Optional[str] = None


# ---------- 发布 ----------

class PostIn(BaseModel):
    account_id: Optional[int] = None       # 不传就落到默认账号
    creative_id: Optional[int] = None
    platform_post_id: Optional[str] = None
    title: str
    publish_date: str                      # "YYYY-MM-DD"
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
    unfollows: Optional[int] = None
    danmaku_count: Optional[int] = None
    cover_ctr: Optional[float] = None
    bounce_2s_rate: Optional[float] = None
    fan_conversion_rate: Optional[float] = None
    high_intent_comments: int = 0
    high_intent_dms: int = 0
    notes: Optional[str] = None
    platform_data: Optional[dict] = None   # 平台特有指标


class SnapshotIn(BaseModel):
    """某个时间点的快照，扩散曲线诊断靠它。checked_at 不填就用当前时间。"""
    checked_at: Optional[str] = None
    plays: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    completion_rate: Optional[float] = None
    profile_visits: int = 0
    new_followers: int = 0
    bounce_2s_rate: Optional[float] = None


class AnomalyPeriodIn(BaseModel):
    start_date: str
    end_date: str
    reason: str
    account_id: Optional[int] = None       # 不传 = 对所有账号生效


class MergeIn(BaseModel):
    """确认把几条疑似重复的 post 合成一条。合并是破坏性的，必须由人点头。"""
    post_ids: list[int]


class CreatorNoteIn(BaseModel):
    """创作者自己写下的想法 —— 助手要懂你，光有数字不够。"""
    body: str
    account_id: Optional[int] = None
    post_id: Optional[int] = None
    creative_id: Optional[int] = None


# ---------- vision 截图确认入库 ----------

class VisionVideoIn(BaseModel):
    """从截图提取、经用户确认的一条作品数据。全部可空——布局不同可见字段就不同。"""
    status: str = "已发布"                  # 私密 会被服务端拒绝入库
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
    """确认面板提交的最终数据。status=私密 的条目服务端直接跳过。"""
    page_type: str
    account_id: Optional[int] = None       # 不传就落到默认账号
    videos: list[VisionVideoIn] = []
    account: Optional[AccountMetricsIn] = None
    curve_observation: Optional[CurveObservationIn] = None
    checked_at: Optional[str] = None       # 详情页快照的观察时间，默认当前时间
