"""采集编排器 — 协调所有采集通道。

按爬取优先架构执行:
  Layer 1 (主力): RSS Feed + HTML 直接爬取
  Layer 2 (补充): Tavily Search API
  Layer 3 (备用): Google News RSS（待实现）
  Layer 4 (兜底): 用户告知

所有采集器并发执行，单源失败不阻塞其他源。
"""

import asyncio
import logging

from news_briefing.config import AppConfig
from news_briefing.collector.models import (
    NewsItem,
    FetchResult,
    SourceTier,
)
from news_briefing.collector.rss_fetcher import fetch_rss
from news_briefing.collector.web_search import fetch_tavily
from news_briefing.collector.scraper import scrape_html

logger = logging.getLogger(__name__)


async def _fetch_source(source: dict, tier: SourceTier, layer: int = 1) -> FetchResult:
    """采集单个信源。

    Args:
        source: 信源配置字典。
        tier: 信源等级。
        layer: 采集层编号。

    Returns:
        FetchResult，包含成功/失败状态和新闻列表。
    """
    name = source.get("name", "unknown")
    source_type = source.get("type", "rss")
    url = source.get("url", "")
    timeout = source.get("timeout", 15)

    try:
        if source_type == "rss":
            items = await fetch_rss(
                url=url,
                source_name=name,
                tier=tier,
                timeout=timeout,
            )
        elif source_type == "web_search":
            items = await fetch_tavily(
                query=url,  # web_search 类型的 url 字段存储搜索 query
                source_name=name,
                timeout=timeout,
            )
        elif source_type == "scrape":
            selector = source.get("selector", ".newslist li a")
            items = await scrape_html(
                url=url,
                source_name=name,
                selector=selector,
                tier=tier,
                timeout=timeout,
            )
        else:
            logger.warning(f"[{name}] 未知信源类型: {source_type}")
            return FetchResult(
                source=name, tier=tier, success=False,
                error=f"未知类型: {source_type}", layer=layer,
            )

        return FetchResult(
            source=name,
            tier=tier,
            success=True,
            items=items,
            count=len(items),
            layer=layer,
        )

    except Exception as e:
        logger.error(f"[{name}] 采集异常: {type(e).__name__}: {e}")
        return FetchResult(
            source=name,
            tier=tier,
            success=False,
            error=f"{type(e).__name__}: {str(e)[:200]}",
            layer=layer,
        )


async def collect_all(config: AppConfig) -> list[FetchResult]:
    """执行所有信源的并发采集。

    采集顺序（爬取优先）:
      1. Layer 1: 所有 enabled 的 RSS 和 Scrape 源
      2. Layer 2: Tavily 搜索补充
      3. 所有源并发执行，单个失败不阻塞

    Args:
        config: 应用配置。

    Returns:
        所有信源的采集结果列表。
    """
    tasks: list[asyncio.Task] = []
    task_labels: list[tuple[int, str, str]] = []  # (tier, type, name)

    # Layer 1: 直接爬取（RSS + HTML Scraping）
    tier1_sources = config.sources.get("tier1", [])
    tier2_sources = config.sources.get("tier2", [])

    for source in tier1_sources:
        if source.get("enabled", True):
            tasks.append(_fetch_source(source, SourceTier.TIER_1, layer=1))
            task_labels.append((1, source.get("type", "rss"), source.get("name", "?")))

    for source in tier2_sources:
        if source.get("enabled", True):
            tasks.append(_fetch_source(source, SourceTier.TIER_2, layer=1))
            task_labels.append((2, source.get("type", "rss"), source.get("name", "?")))

    # Layer 2: Tavily 搜索补充
    search_config = config.search
    morning_topics = search_config.get("topics", {}).get("morning", [])
    for topic in morning_topics:
        tasks.append(fetch_tavily_and_wrap(topic))
        task_labels.append((2, "tavily_search", f"Tavily-{topic[:20]}"))

    logger.info(
        f"开始并发采集: {len(tasks)} 个信源 "
        f"(Tier1: {len(tier1_sources)}, Tier2: {len(tier2_sources)}, Tavily: {len(morning_topics)})"
    )

    if not tasks:
        logger.warning("没有启用的信源")
        return []

    # 并发执行
    results: list[FetchResult] = list(await asyncio.gather(*tasks))

    # 统计
    success_count = sum(1 for r in results if r.success)
    total_items = sum(r.count for r in results if r.success)
    tier1_success = any(r.tier == SourceTier.TIER_1 and r.success for r in results)

    logger.info(
        f"采集完成: {success_count}/{len(results)} 信源成功, "
        f"共 {total_items} 条新闻"
    )

    if not tier1_success:
        logger.warning("所有 Tier 1 信源采集失败！简报将缺少权威来源")

    if total_items < 10:
        logger.warning(f"采集新闻量异常偏低: {total_items} 条")

    return results


async def fetch_tavily_and_wrap(topic: str) -> FetchResult:
    """Tavily 搜索的 FetchResult 包装。

    Args:
        topic: 搜索主题。

    Returns:
        FetchResult。
    """
    try:
        items = await fetch_tavily(query=topic, source_name=f"Tavily-{topic[:20]}")
        return FetchResult(
            source=f"Tavily-{topic[:20]}",
            tier=SourceTier.TIER_2,
            success=len(items) > 0,
            items=items,
            count=len(items),
            layer=2,
        )
    except Exception as e:
        return FetchResult(
            source=f"Tavily-{topic[:20]}",
            tier=SourceTier.TIER_2,
            success=False,
            error=str(e)[:200],
            layer=2,
        )


def flatten_items(results: list[FetchResult]) -> list[NewsItem]:
    """将所有采集结果展开为统一的新闻列表。

    Args:
        results: 采集结果列表。

    Returns:
        扁平化的新闻条目列表。
    """
    all_items: list[NewsItem] = []
    for r in results:
        if r.success:
            all_items.extend(r.items)
    return all_items


def determine_degradation(results: list[FetchResult]) -> tuple[int, str]:
    """根据采集结果确定降级级别。

    Args:
        results: 所有采集结果。

    Returns:
        (降级级别, 降级说明) 元组。
    """
    tier1_ok = any(
        r.success and r.tier == SourceTier.TIER_1 for r in results
    )
    total_ok = sum(1 for r in results if r.success)
    total_items = sum(r.count for r in results if r.success)
    total_sources = len(results)

    if total_ok == 0 or total_items == 0:
        return 5, "所有信源均采集失败，简报无法生成"
    if total_ok <= 2 and total_items < 20:
        return 4, f"仅 {total_ok} 个信源可用，采集量 {total_items} 条，系统严重降级"
    if not tier1_ok:
        return 3, "无 Tier 1 权威信源可用"
    if total_ok < total_sources * 0.5:
        return 1, f"部分信源不可用 ({total_ok}/{total_sources} 正常)"
    return 0, ""
