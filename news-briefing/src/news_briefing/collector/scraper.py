"""HTML 爬取采集器 — Layer 1 补充。

对没有 RSS Feed 的网站进行 HTML 页面爬取，提取新闻标题和链接。
"""

import hashlib
import logging

import httpx
from bs4 import BeautifulSoup

from news_briefing.collector.models import NewsItem, SourceTier

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20.0
DEFAULT_MAX_ITEMS = 20


def _compute_url_hash(url: str) -> str:
    """计算 URL SHA256 哈希前 16 位。"""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


async def scrape_html(
    url: str,
    source_name: str,
    selector: str,
    tier: SourceTier = SourceTier.TIER_1,
    timeout: float = DEFAULT_TIMEOUT,
    max_items: int = DEFAULT_MAX_ITEMS,
    title_attr: str = "text",
    link_attr: str = "href",
    base_url: str | None = None,
) -> list[NewsItem]:
    """从 HTML 页面爬取新闻列表。

    Args:
        url: 目标页面 URL。
        source_name: 信源名称。
        selector: CSS 选择器，选择包含标题和链接的容器元素。
        tier: 信源等级。
        timeout: HTTP 超时（秒）。
        max_items: 最大返回条目数。
        title_attr: 标题的提取属性 ("text" 表示元素文本)。
        link_attr: 链接的提取属性 ("href" 表示 a 标签的 href)。
        base_url: 用于补全相对 URL 的基础 URL。

    Returns:
        新闻条目列表。失败返回空列表。
    """
    items: list[NewsItem] = []

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        elements = soup.select(selector)

        logger.info(f"[{source_name}] 选择器 '{selector}' 匹配 {len(elements)} 个元素")

        count = 0
        for elem in elements[:max_items]:
            # 提取标题
            if title_attr == "text":
                title = elem.get_text(strip=True)
            else:
                title = elem.get(title_attr, "").strip()

            # 提取链接
            link_elem = elem
            if elem.name != "a":
                link_elem = elem.find("a")

            link = ""
            if link_elem:
                link = link_elem.get(link_attr, "").strip()

            # 补全相对 URL
            if link and base_url and not link.startswith(("http://", "https://")):
                from urllib.parse import urljoin
                link = urljoin(base_url or url, link)

            if not title or not link:
                continue

            item = NewsItem(
                title=title,
                url=link,
                source_name=source_name,
                source_tier=tier,
                published_at=None,  # 爬取页面无法精确获取发布时间
                url_hash=_compute_url_hash(link),
            )
            items.append(item)
            count += 1

        logger.info(f"[{source_name}] 爬取到 {count} 条新闻")

    except httpx.TimeoutException:
        logger.warning(f"[{source_name}] 页面爬取超时 ({timeout}s): {url}")
    except httpx.HTTPStatusError as e:
        logger.warning(f"[{source_name}] 页面 HTTP 错误 {e.response.status_code}: {url}")
    except Exception as e:
        logger.error(f"[{source_name}] 页面爬取异常: {type(e).__name__}: {e}")

    return items
