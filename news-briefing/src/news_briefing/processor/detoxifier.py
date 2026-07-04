"""标题去毒化器。

检测并处理情绪化标题:
  1. 情绪化关键词检测 — "暴涨""暴跌""震惊"等
  2. 推测性语言检测 — "或将""可能""据传"等
  3. 夸大表述检测 — "震惊世界""全网刷屏"等

处理策略:
  - 情绪化 → 标记但保留原标题引用
  - 推测性 → 添加 ⚠️ 标记
  - 夸大 → 标注为"原标题存在夸大"
"""

import logging
import re

from news_briefing.collector.models import Certainty, NewsItem

logger = logging.getLogger(__name__)

# 情绪化关键词
SENSATIONAL_KEYWORDS = [
    "暴涨", "暴跌", "狂飙", "雪崩", "崩盘",
    "震惊", "重磅", "疯传", "刷屏", "炸裂",
    "突发", "暴雷", "踩踏", "恐慌",
]

# 推测性表述
UNCERTAINTY_MARKERS = [
    "或将", "可能", "据传", "消息人士", "知情人士",
    "传", "据悉", "有消息称", "业内人士",
]

# 夸大表述模式
EXAGGERATION_PATTERNS = [
    r"震惊[一-鿿]*球",
    r"全网刷屏",
    r"朋友圈疯传",
    r"万亿[一-鿿]*场",
    r"史无前例",
    r"前所未有",
]


def _has_sensational(title: str) -> bool:
    """检测是否含有情绪化关键词。"""
    return any(kw in title for kw in SENSATIONAL_KEYWORDS)


def _has_uncertainty(title: str) -> bool:
    """检测是否含有推测性表述。"""
    return any(marker in title for marker in UNCERTAINTY_MARKERS)


def _has_exaggeration(title: str) -> bool:
    """检测是否含有夸大表述。"""
    return any(re.search(pattern, title) for pattern in EXAGGERATION_PATTERNS)


def _clean_title(title: str) -> str:
    """尝试清理情绪化表述，提取事实部分。

    简单策略: 移除叹号和情绪词，保留核心内容。

    Args:
        title: 原始标题。

    Returns:
        清理后的标题。
    """
    cleaned = title

    # 移除叹号修饰
    cleaned = re.sub(r"[！!]{2,}", "！", cleaned)

    # 移除情绪词（保守策略：只在标题开头的前缀模式）
    for kw in ["重磅！", "突发！", "震惊！", "炸裂！"]:
        if cleaned.startswith(kw):
            cleaned = cleaned[len(kw):]

    # 移除括号内的情绪化注释
    cleaned = re.sub(r"[（(](深度好文|必看|速看|收藏)[）)]", "", cleaned)

    return cleaned.strip()


def detoxify(item: NewsItem) -> NewsItem:
    """对单条新闻标题进行去毒化处理。

    权威媒体 (Tier 1) 标题保持不变。

    Args:
        item: 新闻条目。

    Returns:
        处理后的新闻条目（原地修改 + 返回）。
    """
    # Tier 1 权威媒体标题保留原样
    if item.source_tier.value == 1:
        item.detoxed_title = item.title
        return item

    title = item.title
    original_title = item.title
    actions: list[str] = []

    # 检测
    is_sensational = _has_sensational(title)
    is_uncertain = _has_uncertainty(title)
    is_exaggerated = _has_exaggeration(title)

    # 处理推测性
    if is_uncertain:
        item.certainty = Certainty.UNCERTAIN
        actions.append("detected_uncertainty")

    # 处理情绪化
    if is_sensational:
        cleaned = _clean_title(title)
        if cleaned != title:
            item.detoxed_title = cleaned
            actions.append("detoxified_sensational")
        else:
            item.detoxed_title = title
            actions.append("flagged_sensational")
    else:
        item.detoxed_title = title

    # 处理夸大
    if is_exaggerated:
        actions.append("flagged_exaggeration")

    if actions:
        item.original_title = original_title
        item.editorial_actions = actions
        logger.debug(
            f"[{item.source_name}] 去毒化: '{original_title[:50]}...' → "
            f"actions={actions}"
        )

    return item


def detoxify_batch(items: list[NewsItem]) -> list[NewsItem]:
    """批量去毒化处理。

    Args:
        items: 新闻条目列表。

    Returns:
        处理后的新闻条目列表。
    """
    for item in items:
        detoxify(item)

    flagged = sum(1 for i in items if i.editorial_actions)
    logger.info(f"去毒化完成: {flagged}/{len(items)} 条被标记")
    return items
