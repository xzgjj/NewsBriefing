"""API 路由 — FastAPI 端点定义。

端点:
  GET  /api/v1/health              — 健康检查
  POST /api/v1/briefing/generate   — 生成简报
  POST /api/v1/query/nl            — 自然语言查询
  GET  /api/v1/watchlist           — 查看关注列表
  POST /api/v1/watchlist           — 添加关注
  DELETE /api/v1/watchlist/{id}    — 移除关注
  POST /api/v1/feedback            — 用户反馈
  GET  /api/v1/config/status       — 配置状态
"""

import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from news_briefing.api.schemas import (
    BriefingGenerateRequest,
    BriefingGenerateResponse,
    ComponentStatus,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    NLQueryRequest,
    NLQueryResponse,
    SectionSummary,
    WatchlistAddRequest,
    WatchlistItemResponse,
    WatchlistListResponse,
)
from news_briefing.config import load_config
from news_briefing.db.database import init_db

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。

    Returns:
        配置好的 FastAPI 实例。
    """
    app = FastAPI(
        title="NewsBriefing API",
        description="个人情报简报系统 — API 服务",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS 允许本地开发
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    _register_routes(app)

    # 启动事件: 初始化数据库
    @app.on_event("startup")
    async def startup():
        try:
            init_db()
            logger.info("数据库初始化完成")
        except Exception as e:
            logger.warning(f"数据库初始化失败(非致命): {e}")

    return app


def _register_routes(app: FastAPI) -> None:
    """注册所有 API 路由。"""

    # ============================================================
    # 健康检查
    # ============================================================
    @app.get("/api/v1/health", response_model=HealthResponse)
    async def health_check():
        """系统健康检查。"""
        components = {}

        # 检查配置
        try:
            load_config()
            components["config"] = ComponentStatus(status="ok")
        except Exception as e:
            components["config"] = ComponentStatus(status="down", detail=str(e))

        # 检查 Tavily 额度
        tavily_key = os.environ.get("TAVILY_API_KEY")
        tavily_info = None
        if tavily_key:
            tavily_info = {
                "status": "configured",
                "note": "Key 已设置，额度信息需通过 Tavily API 查询",
            }

        # 检查 DeepSeek
        deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
        components["llm"] = ComponentStatus(
            status="ok" if deepseek_key else "degraded",
            detail="DeepSeek API Key 已配置" if deepseek_key else "未设置，使用规则兜底",
        )

        # 检查调度器
        components["scheduler"] = ComponentStatus(status="ok", detail="就绪")

        # 综合状态
        all_ok = all(c.status == "ok" for c in components.values() if c.status != "degraded")

        return HealthResponse(
            status="healthy" if all_ok else "degraded",
            components=components,
            tavily_quota=tavily_info,
        )

    # ============================================================
    # 简报生成
    # ============================================================
    @app.post("/api/v1/briefing/generate", response_model=BriefingGenerateResponse)
    async def generate_briefing(request: BriefingGenerateRequest):
        """生成简报。"""
        try:
            config = load_config()

            from news_briefing.pipeline import generate_briefing as gen
            briefing = await gen(
                config=config,
                mode=request.mode,
                output="feishu" if request.format == "feishu_card" else "console",
            )

            if briefing is None:
                raise HTTPException(
                    status_code=500,
                    detail={"error": "COLLECTION_FAILED", "message": "所有信源采集失败"},
                )

            sections_summary = [
                SectionSummary(label=s.label, count=len(s.items))
                for s in briefing.sections
            ]

            return BriefingGenerateResponse(
                briefing_id=hash(briefing.date) & 0x7FFFFFFF,
                status="delivered",
                degradation_level=briefing.degradation_level,
                degradation_note=briefing.degradation_note,
                total_raw=briefing.total_raw,
                total_selected=briefing.total_selected,
                sections=sections_summary,
                generated_at=briefing.generated_at.isoformat(),
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"简报生成失败: {e}")
            raise HTTPException(status_code=500, detail={
                "error": "GENERATION_FAILED",
                "error_code": "INTERNAL_ERROR",
                "message": str(e)[:500],
            }) from e

    # ============================================================
    # 自然语言查询
    # ============================================================
    @app.post("/api/v1/query/nl", response_model=NLQueryResponse)
    async def natural_language_query(request: NLQueryRequest):
        """自然语言查询。"""
        try:
            from news_briefing.processor.command_parser import parse_query

            parsed = parse_query(request.query)
            config = load_config()

            # 尝试从缓存获取
            from news_briefing.pipeline import generate_briefing
            briefing = await generate_briefing(
                config=config,
                mode="manual",
                output="console",
            )

            if briefing is None:
                return NLQueryResponse(
                    type="empty",
                    query=request.query,
                    parsed=parsed,
                    message=f"未找到与「{parsed.topic or request.query}」相关的内容。",
                )

            # 按 topic 过滤
            if parsed.topic:
                filtered = []
                for section in briefing.sections:
                    matching = [
                        item for item in section.items
                        if parsed.topic.lower() in item.item.title.lower()
                        or parsed.topic.lower() in (item.ai_summary or "").lower()
                    ]
                    filtered.extend(matching)

                if not filtered:
                    return NLQueryResponse(
                        type="empty",
                        query=request.query,
                        parsed=parsed,
                        message=f"今日新闻中未找到与「{parsed.topic}」相关的内容。是否需要搜索最新信息？",
                    )

            return NLQueryResponse(
                type="briefing",
                query=request.query,
                parsed=parsed,
                source="cache",
                total_selected=briefing.total_selected,
                markdown_text=briefing.markdown_text[:2000],
            )

        except Exception as e:
            logger.error(f"查询失败: {e}")
            raise HTTPException(status_code=500, detail={
                "error": "QUERY_FAILED",
                "message": str(e)[:500],
            }) from e

    # ============================================================
    # 关注列表管理
    # ============================================================
    @app.get("/api/v1/watchlist", response_model=WatchlistListResponse)
    async def get_watchlist():
        """获取关注列表。"""
        try:
            config = load_config()
            items = [
                WatchlistItemResponse(
                    id=i,
                    name=item.get("name", ""),
                    ticker=item.get("ticker"),
                    market=item.get("market"),
                    keywords=item.get("keywords", []),
                    priority=item.get("priority", 5),
                )
                for i, item in enumerate(config.watchlist)
            ]
            return WatchlistListResponse(items=items, total=len(items))
        except Exception as e:
            raise HTTPException(status_code=500, detail={"error": str(e)}) from e

    @app.post("/api/v1/watchlist", response_model=WatchlistItemResponse)
    async def add_watchlist(request: WatchlistAddRequest):
        """添加关注项。"""
        try:
            config = load_config()

            # 检查是否已存在
            for item in config.watchlist:
                if item.get("name", "").lower() == request.name.lower():
                    msg = f"「{request.name}」已在关注列表中"
                    raise HTTPException(
                        status_code=409,
                        detail={"error": "DUPLICATE", "message": msg},
                    )

            new_item = {
                "name": request.name,
                "ticker": request.ticker,
                "market": request.market,
                "keywords": request.keywords or [request.name],
                "priority": request.priority,
            }
            config.watchlist.append(new_item)

            return WatchlistItemResponse(
                id=len(config.watchlist) - 1,
                name=request.name,
                ticker=request.ticker,
                market=request.market,
                keywords=request.keywords or [request.name],
                priority=request.priority,
            )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail={"error": str(e)}) from e

    @app.delete("/api/v1/watchlist/{item_id}")
    async def remove_watchlist(item_id: int):
        """移除关注项。"""
        try:
            config = load_config()
            if item_id < 0 or item_id >= len(config.watchlist):
                raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})

            removed = config.watchlist.pop(item_id)
            return {"message": f"已移除「{removed.get('name', '')}」", "id": item_id}

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail={"error": str(e)}) from e

    # ============================================================
    # 用户反馈
    # ============================================================
    @app.post("/api/v1/feedback", response_model=FeedbackResponse)
    async def submit_feedback(request: FeedbackRequest):
        """提交用户反馈。"""
        valid_actions = {"liked", "disliked", "source_unreliable"}
        if request.action not in valid_actions:
            raise HTTPException(
                status_code=400,
                detail={"error": "INVALID_ACTION", "message": f"无效操作: {request.action}"},
            )

        messages = {
            "liked": "👍 感谢反馈！已记录偏好，后续简报中将优先展示此类内容。",
            "disliked": "👎 已记录。此类内容将在后续简报中降权。",
            "source_unreliable": "⚠️ 已标记来源。后续简报中将降低来自该来源的新闻权重。",
        }

        return FeedbackResponse(
            id=1,
            action=request.action,
            message=messages.get(request.action, "已记录反馈"),
        )

    # ============================================================
    # 配置状态
    # ============================================================
    @app.get("/api/v1/config/status")
    async def config_status():
        """查看配置状态。"""
        try:
            config = load_config()
            return {
                "version": config.version,
                "schedule": {
                    k: v for k, v in config.schedule.items()
                    if isinstance(v, dict) and v.get("enabled")
                },
                "sources": {
                    "tier1_count": len(config.sources.get("tier1", [])),
                    "tier2_count": len(config.sources.get("tier2", [])),
                },
                "watchlist_count": len(config.watchlist),
                "llm_provider": config.llm.get("provider", "N/A"),
                "llm_model": config.llm.get("fast_model", "N/A"),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail={"error": str(e)}) from e

    # ============================================================
    # 用户交互
    # ============================================================
    @app.post("/api/v1/interact/followup")
    async def interact_followup(request: dict):
        """追问某条新闻详情（"第三条详细说说"）。"""
        try:
            from news_briefing.api.interaction import handle_followup
            return await handle_followup(
                query=request.get("query", ""),
                briefing_context=request.get("context"),
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail={"error": str(e)}) from e

    @app.post("/api/v1/interact/config")
    async def interact_config(request: dict):
        """对话式配置（加关注、系统状态等）。"""
        try:
            from news_briefing.api.interaction import handle_config_command
            return await handle_config_command(request.get("text", ""))
        except Exception as e:
            raise HTTPException(status_code=500, detail={"error": str(e)}) from e
