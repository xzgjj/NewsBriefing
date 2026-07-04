"""新闻条目与简报的核心数据结构。

所有模块使用统一的数据模型，通过 Pydantic 进行校验。
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SourceTier(int, Enum):
    """信源等级。"""
    TIER_1 = 1  # 权威媒体
    TIER_2 = 2  # 知名平台
    TIER_3 = 3  # 待核实


class Certainty(str, Enum):
    """消息确定性级别。"""
    CONFIRMED = "confirmed"          # 已确认
    UNCERTAIN = "uncertain"           # 不确定
    VENDOR_CLAIMED = "vendor_claimed"  # 厂商自称
    ARXIV = "arxiv"                   # 预印本


class Importance(str, Enum):
    """新闻重要性标签。"""
    RED = "red"        # 重大
    YELLOW = "yellow"  # 值得关注
    GREEN = "green"     # 一般


class NewsItem(BaseModel):
    """单条新闻条目 — 采集层输出，处理层输入。

    这是整个管道中流通的核心数据结构。
    """
    title: str
    url: str
    source_name: str
    source_tier: SourceTier = SourceTier.TIER_2
    content_snippet: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=datetime.now)

    # 去重字段
    url_hash: str = ""      # SHA256(url)[:16], 在去重阶段填充
    simhash: int = 0         # 64-bit SimHash

    # 评分字段（排序阶段填充）
    score: float = 0.0

    # 分类字段（AI 策展阶段填充）
    category: str = "general"  # policy|fintech|ai|tech|watchlist|general
    importance: Importance = Importance.GREEN

    # AI 策展字段
    ai_summary: str | None = None
    detoxed_title: str | None = None
    certainty: Certainty = Certainty.CONFIRMED
    cross_validated_by: list[str] = Field(default_factory=list)

    # 溯源字段
    original_title: str | None = None  # 保留原标题（去毒化前）
    editorial_actions: list[str] = Field(default_factory=list)


class CuratedItem(BaseModel):
    """策展后的新闻条目 — 处理层输出，组装层输入。"""
    item: NewsItem
    category: str = "general"
    section_label: str = ""
    ai_summary: str | None = None
    impact_analysis: str | None = None  # 深度分析（仅 red 新闻）
    display_title: str = ""                 # 用于展示的标题（可能是去毒化后的）
    uncertainty_label: str | None = None  # 不确定标注


class Section(BaseModel):
    """简报板块。"""
    label: str                              # 板块标题 e.g. "🏛️ 政策大事"
    items: list[CuratedItem] = Field(default_factory=list)
    min_items: int = 1
    max_items: int = 10
    note: str | None = None              # 板块备注 e.g. "今日该板块无重大新闻"


class Briefing(BaseModel):
    """完整简报。"""
    title: str
    date: str                               # YYYY-MM-DD
    mode: str = "scheduled"                 # scheduled | manual | event
    sections: list[Section] = Field(default_factory=list)
    total_raw: int = 0
    total_after_dedup: int = 0
    total_selected: int = 0
    degradation_level: int = 0
    degradation_note: str | None = None
    tavily_used: int = 0
    generated_at: datetime = Field(default_factory=datetime.now)
    markdown_text: str = ""
    feishu_card_json: str | None = None


class FetchResult(BaseModel):
    """单个信源的采集结果。"""
    source: str
    tier: SourceTier
    success: bool
    items: list[NewsItem] = Field(default_factory=list)
    error: str | None = None
    count: int = 0
    layer: int = 1  # 采集层（1=直接爬取, 2=Tavily, 3=Google News）
