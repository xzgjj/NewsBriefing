"""Tavily 搜索采集器 — Layer 2 补充采集。

通过 Tavily Search API 搜索新闻，填补直接爬取未覆盖的缺口。
"""

import hashlib
import logging
import os

import httpx

from news_briefing.collector.models import Certainty, NewsItem, SourceTier

logger = logging.getLogger(__name__)

# Tavily API 端点
TAVILY_API_URL = "https://api.tavily.com/search"
DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_RESULTS = 10


def _compute_url_hash(url: str) -> str:
    """计算 URL SHA256 哈希前 16 位。"""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


async def fetch_tavily(
    query: str,
    source_name: str = "Tavily搜索",
    api_key: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_results: int = DEFAULT_MAX_RESULTS,
    search_depth: str = "basic",
    days: int = 1,
) -> list[NewsItem]:
    """通过 Tavily Search API 搜索新闻。

    Args:
        query: 搜索查询词。
        source_name: 信源展示名称。
        api_key: Tavily API Key。None 则从环境变量 TAVILY_API_KEY 读取。
        timeout: HTTP 超时（秒）。
        max_results: 最大返回结果数。
        search_depth: 搜索深度，"basic" 或 "advanced"。
        days: 搜索最近 N 天的内容。

    Returns:
        新闻条目列表。失败返回空列表。

    Raises:
        不抛出异常。
    """
    if api_key is None:
        api_key = os.environ.get("TAVILY_API_KEY", "")

    if not api_key:
        logger.warning("Tavily API Key 未设置，跳过搜索")
        return []

    items: list[NewsItem] = []

    try:
        payload = {
            "api_key": api_key,
            "query": query,
            "search_depth": "advanced",  # advanced=更精准的新闻搜索
            "max_results": max_results,
            "days": min(days, 3),  # 最多3天，确保时效
            "include_answer": False,
            "include_raw_content": False,
            "include_domains": [],  # 由具体查询场景决定
            "topic": "news",  # 限定新闻类内容
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(TAVILY_API_URL, json=payload)
            response.raise_for_status()

        data = response.json()
        results = data.get("results", [])

        logger.info(f"[{source_name}] 查询 '{query}' 返回 {len(results)} 条结果")

        for r in results:
            title = r.get("title", "").strip()
            url = r.get("url", "").strip()
            content = r.get("content", "").strip()
            score = r.get("score", 0.0)

            if not title or not url:
                continue

            # Tavily 搜索结果的时效由API保证（days参数），不伪造时间戳
            item = NewsItem(
                title=title,
                url=url,
                source_name=source_name,
                source_tier=SourceTier.TIER_2,
                content_snippet=content[:500] if content else None,
                published_at=None,  # Tavily不保证精确时间，由排序层按"今日"处理
                url_hash=_compute_url_hash(url),
                score=score,
                certainty=Certainty.UNCERTAIN,
            )
            items.append(item)

    except httpx.TimeoutException:
        logger.warning(f"[{source_name}] Tavily 搜索超时: '{query}'")
    except httpx.HTTPStatusError as e:
        logger.warning(
            f"[{source_name}] Tavily HTTP 错误 {e.response.status_code}: '{query}'"
        )
        if e.response.status_code == 429:
            logger.warning("[{source_name}] Tavily 额度可能已耗尽")
    except Exception as e:
        logger.error(f"[{source_name}] Tavily 搜索异常: {type(e).__name__}: {e}")

    return items
