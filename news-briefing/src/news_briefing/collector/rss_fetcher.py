"""RSS 采集器。

使用 feedparser 解析 RSS/Atom Feed，提取标题、链接、摘要和发布时间。
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone

import feedparser
import httpx

from news_briefing.collector.models import NewsItem, SourceTier

logger = logging.getLogger(__name__)

# 默认超时
DEFAULT_TIMEOUT = 15.0
# 时效过滤：超过 7 天的新闻直接丢弃
MAX_AGE_DAYS = 7
# 无法解析时间的新闻：标记但不丢弃（由排序层降权处理）


def _parse_published(entry) -> datetime | None:
    """从 feedparser entry 中提取发布时间。

    按优先级尝试多个字段: published_parsed, updated_parsed, published, updated。

    Args:
        entry: feedparser entry 对象。

    Returns:
        datetime，如果无法解析则返回 None。
    """
    # 尝试解析 parsed 字段（struct_time tuple）
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass

    # 回退: 尝试解析字符串字段
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                # feedparser 可能已经解析了字符串格式
                from email.utils import parsedate_to_datetime
                return parsedate_to_datetime(raw)
            except (ValueError, TypeError):
                pass

    return None


def _compute_url_hash(url: str) -> str:
    """计算 URL 的 SHA256 哈希前 16 位（用于去重）。

    Args:
        url: 新闻 URL。

    Returns:
        16 字符的十六进制哈希字符串。
    """
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _is_fresh(published_at: datetime | None) -> tuple[bool, str]:
    """检查新闻是否在时效范围内。

    Args:
        published_at: 发布时间。None 表示无法解析。

    Returns:
        (是否保留, 时效标记)。标记: "fresh" | "unknown" | "stale"
    """
    if published_at is None:
        return True, "unknown"  # 无法解析时间，保留但标记未知
    now = datetime.now(timezone.utc)
    age = now - published_at
    if age > timedelta(days=MAX_AGE_DAYS):
        return False, "stale"  # 超过7天，直接丢弃
    return True, "fresh"


async def fetch_rss(
    url: str,
    source_name: str,
    tier: SourceTier = SourceTier.TIER_2,
    timeout: float = DEFAULT_TIMEOUT,
    max_items: int = 30,
) -> list[NewsItem]:
    """从 RSS Feed URL 采集新闻。

    Args:
        url: RSS Feed URL。
        source_name: 信源名称（用于溯源）。
        tier: 信源等级。
        timeout: HTTP 超时（秒）。
        max_items: 最大返回条目数。

    Returns:
        新闻条目列表。如果采集失败则返回空列表。

    Raises:
        不抛出异常 — 所有错误都在内部处理并记录日志。
    """
    items: list[NewsItem] = []

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()

        # feedparser 解析
        feed = feedparser.parse(response.text)

        if feed.bozo:
            logger.warning(f"[{source_name}] RSS 解析警告: {feed.bozo_exception}")

        entries = feed.entries[:max_items]
        logger.info(f"[{source_name}] 获取到 {len(entries)} 条 RSS 条目")

        for entry in entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()

            if not title or not link:
                continue

            # 提取摘要
            summary = entry.get("summary", "") or entry.get("description", "")
            # 去除 HTML 标签（简单处理）
            if summary:
                import re
                summary = re.sub(r"<[^>]+>", "", summary)[:500]

            published_at = _parse_published(entry)

            # 时效过滤
            keep, age_flag = _is_fresh(published_at)
            if not keep:
                logger.debug(f"[{source_name}] 丢弃过期新闻(>{MAX_AGE_DAYS}天): {title[:50]}...")
                continue

            item = NewsItem(
                title=title,
                url=link,
                source_name=source_name,
                source_tier=tier,
                content_snippet=summary.strip() if summary else None,
                published_at=published_at,
                url_hash=_compute_url_hash(link),
            )
            items.append(item)

    except httpx.TimeoutException:
        logger.warning(f"[{source_name}] RSS 采集超时 ({timeout}s): {url}")
    except httpx.HTTPStatusError as e:
        logger.warning(f"[{source_name}] RSS HTTP 错误 {e.response.status_code}: {url}")
    except Exception as e:
        logger.error(f"[{source_name}] RSS 采集异常: {type(e).__name__}: {e}")

    return items
