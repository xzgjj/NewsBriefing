"""摘要栏目处理器 — 检测并展开新闻摘要类栏目。

处理36氪"9点1氪"等每日摘要汇总栏目：
  1. 检测: 标题匹配摘要栏目模式
  2. 提取: 从正文中解析被提及的独立新闻标题
  3. 标记: 原始条目标记为 digest 类型，展开的子条目标记来源
"""

import logging
import re

from news_briefing.collector.models import NewsItem

logger = logging.getLogger(__name__)

# 摘要栏目检测模式
DIGEST_PATTERNS = [
    (re.compile(r"^9点1氪"), "36氪每日摘要"),
    (re.compile(r"^8点1氪"), "36氪每日摘要"),
    (re.compile(r"^早报"), "早报摘要"),
    (re.compile(r"^晚报"), "晚报摘要"),
    (re.compile(r"今日热点导览"), "热点摘要"),
]

# 从摘要正文中提取子标题的模式
# 36氪格式: "TOP3大新闻\n  因存在...\n  36氪从..."
# 或 "三部门：调整节能汽车..."
# 或 "- 三星传获Meta..."
SUB_ITEM_PATTERNS = [
    # "XXX：YYYY" 格式的新闻标题
    re.compile(r"(?:^|\n)\s*([^：\n]{4,40}：[^：\n]{4,100})"),
    # "- XXX" 格式的列表项
    re.compile(r"(?:^|\n)\s*[-•]\s*([^-•\n]{6,80})"),
    # "TOP3大新闻" 后的独立行
    re.compile(r"TOP\d大新闻\s*\n(.+?)(?=\n\n|\n[一二三]|\Z)", re.DOTALL),
]


def detect_digest(item: NewsItem) -> str | None:
    """检测是否为摘要栏目。

    Args:
        item: 新闻条目。

    Returns:
        摘要类型标签，不是摘要则返回 None。
    """
    title = item.title or ""
    for pattern, label in DIGEST_PATTERNS:
        if pattern.search(title):
            return label
    return None


def expand_36kr_digest(item: NewsItem) -> list[dict]:
    """展开36氪摘要栏目中的子新闻。

    从正文中提取被提及的独立话题，返回可搜索的关键词组。

    Args:
        item: "9点1氪"类型的 NewsItem。

    Returns:
        提取到的子话题列表，每个为 {title, keywords}。
    """
    content = item.content_snippet or ""
    title = item.title or ""
    text = title + "\n" + content

    found: list[dict] = []

    # 方法1: 查找 "XXX：YYY" 格式的子标题
    for match in re.finditer(r"(?:^|\n)\s*([^：\n]{4,40}：[^：\n]{4,100})", text):
        sub_title = match.group(1).strip()
        if len(sub_title) > 8:
            found.append({"title": sub_title, "keywords": sub_title.split("：")[:2]})

    # 方法2: 查找 "- XXX" 格式的列表项
    for match in re.finditer(r"(?:^|\n)\s*[-•]\s*([^-•\n]{8,80})", text):
        sub_title = match.group(1).strip()
        if sub_title and len(sub_title) > 8:
            found.append({"title": sub_title, "keywords": [sub_title]})

    # 去重
    seen = set()
    unique = []
    for f in found:
        key = f["title"][:30]
        if key not in seen:
            seen.add(key)
            unique.append(f)

    if unique:
        logger.info(f"摘要展开: '{item.title[:40]}...' → {len(unique)} 个子话题")
    return unique[:8]  # 最多展开8个


def process_digests(items: list[NewsItem]) -> list[NewsItem]:
    """处理所有摘要条目：标记原条目，展开子话题为独立查询。

    当前策略:
      - 检测并标记摘要条目（不删除，保留为信息源）
      - 从摘要中提取的子话题**不**直接创建 NewsItem
        （因为没有URL），而是记录到 editorial_actions 中
      - 由调用方根据子话题发起补充搜索

    Args:
        items: 新闻条目列表（原地修改）。

    Returns:
        修改后的同一列表。
    """
    for item in items:
        digest_type = detect_digest(item)
        if digest_type:
            item.editorial_actions.append(f"digest:{digest_type}")
            logger.debug(f"标记摘要: '{item.title[:50]}...' → {digest_type}")

    digest_count = sum(1 for i in items if detect_digest(i))
    if digest_count:
        logger.info(f"摘要处理: {digest_count} 条摘要栏目已标记")
    return items
