"""全文提取器 — 通过 Jina Reader API 获取网页完整内容。

Jina Reader (https://r.jina.ai) 将任意 URL 转为干净的 Markdown，
去除广告、导航栏等噪音，保留正文。免费额度充足。

这是内容质量的核心依赖：只有拿到全文，LLM 才能产出编辑级摘要。
"""

import logging

import httpx

logger = logging.getLogger(__name__)

JINA_READER_BASE = "https://r.jina.ai"
DEFAULT_TIMEOUT = 10.0
MAX_CONTENT_LENGTH = 3000  # 最多保留3000字符（足够LLM理解+控制token消耗）


async def extract_full_text(
    url: str,
    timeout: float = DEFAULT_TIMEOUT,
    max_length: int = MAX_CONTENT_LENGTH,
) -> str | None:
    """通过 Jina Reader 提取网页全文。

    Args:
        url: 目标网页 URL。
        timeout: 超时时间（秒）。
        max_length: 返回内容的最大字符数。

    Returns:
        Markdown 格式的全文内容。失败返回 None。
    """
    try:
        reader_url = f"{JINA_READER_BASE}/{url}"

        headers = {
            "Accept": "text/markdown",
            "X-Return-Format": "markdown",
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(reader_url, headers=headers)
            response.raise_for_status()

        content = response.text

        if not content or len(content) < 50:
            logger.debug(f"Jina Reader 返回内容过短: {url[:60]}")
            return None

        # 截断到合理长度
        if len(content) > max_length:
            content = content[:max_length] + "\n\n...(内容已截断)"

        logger.debug(f"全文提取成功: {url[:60]}... ({len(content)} 字符)")
        return content

    except httpx.TimeoutException:
        logger.debug(f"Jina Reader 超时: {url[:60]}")
        return None
    except httpx.HTTPStatusError as e:
        logger.debug(f"Jina Reader HTTP {e.response.status_code}: {url[:60]}")
        return None
    except Exception as e:
        logger.debug(f"Jina Reader 异常: {type(e).__name__}: {url[:60]}")
        return None


async def enrich_items(
    items: list,
    timeout: float = DEFAULT_TIMEOUT,
    max_concurrent: int = 5,
) -> int:
    """为新闻条目批量提取全文。

    并发控制：最多 max_concurrent 个同时请求，避免压垮 Jina API。

    Args:
        items: NewsItem 列表（原地修改 content_snippet 字段）。
        timeout: 单条超时。
        max_concurrent: 最大并发数。

    Returns:
        成功提取全文的条目数。
    """
    import asyncio

    semaphore = asyncio.Semaphore(max_concurrent)
    enriched = 0

    async def enrich_one(item):
        nonlocal enriched
        async with semaphore:
            full_text = await extract_full_text(item.url, timeout=timeout)
            if full_text:
                item.content_snippet = full_text
                enriched += 1
                return True
            return False

    # 只对排名靠前的条目提取全文（避免浪费资源）
    tasks = [enrich_one(item) for item in items]
    await asyncio.gather(*tasks, return_exceptions=True)

    logger.info(f"全文提取完成: {enriched}/{len(items)} 条成功")
    return enriched


# ============================================================
# 内容质量过滤
# ============================================================

LOW_QUALITY_DOMAINS = {
    "youtube.com", "youtu.be",
    "bilibili.com",
    "zhihu.com",  # 知乎问答通常不是新闻
    "weibo.com",
    "tieba.baidu.com",
}

LOW_QUALITY_TITLE_PATTERNS = [
    "直播精选", "直播回放", "subscribe", "订阅",
    "什么是", "全面解析", "一文看懂",  # 解释性文章，不是新闻
    "广告", "推广",
]


def is_low_quality(item) -> bool:
    """判断新闻条目是否为低质量内容。

    检查域名黑名单和标题模式。

    Args:
        item: NewsItem 对象。

    Returns:
        True 如果应被过滤。
    """
    from urllib.parse import urlparse

    # 域名检查
    try:
        domain = urlparse(item.url).netloc.lower()
        for bad in LOW_QUALITY_DOMAINS:
            if bad in domain:
                logger.debug(f"质量过滤(域名): {item.title[:50]}... ({domain})")
                return True
    except Exception:
        pass

    # 标题模式检查
    title_lower = item.title.lower()
    for pattern in LOW_QUALITY_TITLE_PATTERNS:
        if pattern.lower() in title_lower:
            logger.debug(f"质量过滤(标题): {item.title[:50]}...")
            return True

    return False


def filter_quality(items: list) -> tuple[list, int]:
    """过滤低质量新闻条目。

    Args:
        items: NewsItem 列表。

    Returns:
        (过滤后的列表, 过滤数量)。
    """
    filtered = []
    removed = 0
    for item in items:
        if is_low_quality(item):
            removed += 1
        else:
            filtered.append(item)

    if removed:
        logger.info(f"质量过滤: 移除 {removed} 条低质量内容")
    return filtered, removed
