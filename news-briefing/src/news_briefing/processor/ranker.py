"""四维新闻评分系统。

评分公式:
  score = tier_weight × freshness_decay × keyword_bonus
          × cross_validation × user_relevance × 100

每个维度的权重范围 0.0 ~ 2.0，最终分数为 0~200。
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from news_briefing.collector.models import NewsItem, SourceTier
from news_briefing.config import AppConfig

logger = logging.getLogger(__name__)

# 信源系数
TIER_WEIGHTS = {
    SourceTier.TIER_1: 0.95,
    SourceTier.TIER_2: 0.60,
    SourceTier.TIER_3: 0.25,
}

# 时效衰减: 24 小时半衰期
HALF_LIFE_HOURS = 24.0


def _tier_weight(tier: SourceTier) -> float:
    """获取信源等级权重。

    Args:
        tier: 信源等级。

    Returns:
        权重系数 (0.0 ~ 1.0)。
    """
    return TIER_WEIGHTS.get(tier, 0.40)


def _freshness_decay(published_at: Optional[datetime]) -> float:
    """计算时效衰减系数。

    使用指数衰减，24 小时半衰期。

    Args:
        published_at: 发布时间。None 视为当前时间。

    Returns:
        时效系数 (0.0 ~ 1.0)。越新越接近 1.0。
    """
    if published_at is None:
        return 0.8  # 未知时间给中等分数

    now = datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)

    age_hours = (now - published_at).total_seconds() / 3600.0
    if age_hours < 0:
        return 1.0  # 未来时间（时钟偏差），视为最新

    # 指数衰减: 2^(-age / half_life)
    decay = 2.0 ** (-age_hours / HALF_LIFE_HOURS)
    return decay


def _keyword_bonus(
    title: str,
    content_snippet: Optional[str],
    keywords: list[str],
) -> float:
    """计算关键词匹配加分。

    标题中出现关键词权重更高。

    Args:
        title: 新闻标题。
        content_snippet: 内容摘要。
        keywords: 关键词列表。

    Returns:
        加分系数 (0.0 ~ 2.0)。
    """
    if not keywords:
        return 1.0

    text = title.lower()
    if content_snippet:
        text += " " + content_snippet.lower()

    title_lower = title.lower()
    bonus = 0.0

    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in title_lower:
            bonus += 0.15  # 标题命中
        elif kw_lower in text:
            bonus += 0.05  # 正文命中

    return min(1.0 + bonus, 2.0)


def _cross_validation_bonus(item: NewsItem) -> float:
    """交叉验证加分。

    同一事件被多个来源报道时加分。

    Args:
        item: 新闻条目。

    Returns:
        交叉验证系数。
    """
    count = len(item.cross_validated_by)
    if count >= 3:
        return 1.3
    elif count >= 2:
        return 1.15
    elif count >= 1:
        return 1.05
    # 单一来源
    if item.source_tier == SourceTier.TIER_1:
        return 0.85  # Tier 1 但无交叉验证
    elif item.source_tier == SourceTier.TIER_2:
        return 0.65
    else:
        return 0.40


def _user_relevance(
    item: NewsItem,
    watchlist: list[dict],
    topics_keywords: dict[str, list[str]],
) -> float:
    """计算用户相关性加分。

    根据关注列表和话题关键词匹配。

    Args:
        item: 新闻条目。
        watchlist: 关注列表。
        topics_keywords: 各话题的关键词映射。

    Returns:
        用户相关性系数 (0.5 ~ 2.0)。
    """
    text = (item.title + " " + (item.content_snippet or "")).lower()
    relevance = 0.5  # 基础值

    # 检查关注列表
    for wl_item in watchlist:
        for kw in wl_item.get("keywords", []):
            if kw.lower() in text:
                relevance += 0.3
                break  # 每个关注项最多加一次

    # 检查话题关键词
    for topic_kws in topics_keywords.values():
        for kw in topic_kws:
            if kw.lower() in text:
                relevance += 0.05
                break  # 每个话题最多加一次

    return min(relevance, 2.0)


def rank_items(
    items: list[NewsItem],
    config: AppConfig,
) -> list[NewsItem]:
    """对新闻条目进行四维评分并排序。

    Args:
        items: 待评分的新闻条目列表。
        config: 应用配置（用于读取话题关键词和关注列表）。

    Returns:
        按 score 降序排列的新闻条目列表。
    """
    # 构建关键词映射
    topics_keywords: dict[str, list[str]] = {}
    for topic_name, topic_cfg in config.topics.items():
        if isinstance(topic_cfg, dict) and topic_cfg.get("enabled", True):
            topics_keywords[topic_name] = topic_cfg.get("keywords", [])

    watchlist = config.watchlist

    # 加载用户反馈权重（偏好学习）
    try:
        from news_briefing.processor.feedback import get_weight_store
        weight_store = get_weight_store()
    except ImportError:
        weight_store = None

    for item in items:
        # 四维评分
        tier_w = _tier_weight(item.source_tier)
        freshness = _freshness_decay(item.published_at)
        kw_bonus = _keyword_bonus(
            item.title, item.content_snippet,
            [kw for kws in topics_keywords.values() for kw in kws],
        )
        cross_val = _cross_validation_bonus(item)
        user_rel = _user_relevance(item, watchlist, topics_keywords)

        item.score = tier_w * freshness * kw_bonus * cross_val * user_rel * 100

        # 偏好学习调整: 应用用户反馈权重
        if weight_store is not None:
            cat_w = weight_store.get_category_weight(item.category)
            src_w = weight_store.get_source_weight(item.source_name)
            item.score *= cat_w * src_w

    # 按分数降序排序
    sorted_items = sorted(items, key=lambda x: x.score, reverse=True)

    if sorted_items:
        top_score = sorted_items[0].score
        logger.info(
            f"评分完成: {len(sorted_items)} 条, "
            f"最高分 {top_score:.1f}, 最低分 {sorted_items[-1].score:.1f}"
        )

    return sorted_items
