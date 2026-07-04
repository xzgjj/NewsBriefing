"""API 请求/响应 Pydantic 模型。"""


from pydantic import BaseModel, Field

# ============================================================
# 简报生成
# ============================================================

class BriefingGenerateRequest(BaseModel):
    """生成简报请求。"""
    mode: str = "manual"            # manual | scheduled
    time_range: str = "today"       # today | yesterday | week
    topics: list[str] = Field(default_factory=list)
    format: str = "feishu_card"     # feishu_card | markdown | json


class SectionSummary(BaseModel):
    """简报板块摘要。"""
    label: str
    count: int


class BriefingGenerateResponse(BaseModel):
    """简报生成响应。"""
    briefing_id: int = 0
    status: str = "delivered"
    degradation_level: int = 0
    degradation_note: str | None = None
    total_raw: int = 0
    total_selected: int = 0
    sections: list[SectionSummary] = Field(default_factory=list)
    tavily_remaining: int | None = None
    generated_at: str = ""


# ============================================================
# 自然语言查询
# ============================================================

class NLQueryRequest(BaseModel):
    """自然语言查询请求。"""
    query: str
    format: str = "briefing"        # briefing | list


class ParsedIntent(BaseModel):
    """解析后的意图。"""
    topic: str = ""
    time_range: str = "today"
    mode: str = "query"


class NLQueryResponse(BaseModel):
    """自然语言查询响应。"""
    type: str = "briefing"          # briefing | list | empty
    query: str
    parsed: ParsedIntent | None = None
    source: str = "cache"           # cache | search | cache+search
    briefing_id: int | None = None
    total_selected: int = 0
    markdown_text: str = ""
    message: str | None = None   # 无结果时的提示


# ============================================================
# 关注列表
# ============================================================

class WatchlistAddRequest(BaseModel):
    """添加关注请求。"""
    name: str
    ticker: str | None = None
    market: str | None = None
    keywords: list[str] = Field(default_factory=list)
    priority: int = 5


class WatchlistItemResponse(BaseModel):
    """关注列表项响应。"""
    id: int
    name: str
    ticker: str | None = None
    market: str | None = None
    keywords: list[str] = Field(default_factory=list)
    priority: int
    enabled: bool = True


class WatchlistListResponse(BaseModel):
    """关注列表响应。"""
    items: list[WatchlistItemResponse] = Field(default_factory=list)
    total: int = 0


# ============================================================
# 用户反馈
# ============================================================

class FeedbackRequest(BaseModel):
    """用户反馈请求。"""
    briefing_id: int | None = None
    news_id: int | None = None
    action: str                     # liked | disliked | source_unreliable
    comment: str | None = None


class FeedbackResponse(BaseModel):
    """用户反馈响应。"""
    id: int
    action: str
    message: str


# ============================================================
# 健康检查
# ============================================================

class ComponentStatus(BaseModel):
    """组件状态。"""
    status: str = "ok"              # ok | degraded | down
    detail: str | None = None


class HealthResponse(BaseModel):
    """健康检查响应。"""
    status: str = "healthy"         # healthy | degraded | down
    version: str = "0.1.0"
    components: dict[str, ComponentStatus] = Field(default_factory=dict)
    tavily_quota: dict | None = None


# ============================================================
# 错误响应
# ============================================================

class ErrorResponse(BaseModel):
    """错误响应。"""
    error: str
    error_code: str = "UNKNOWN"
    message: str
    details: dict | None = None
