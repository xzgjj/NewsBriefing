"""简报板块生成 — 分类优先 + 配额保障。

策略:
  1. 先对所有条目分类（由Curator完成）
  2. 每个类别独立评分排序
  3. 按配额(min~max)选取
  4. 不足min时标注，不强行填充无关内容
"""

import logging

from news_briefing.collector.models import CuratedItem, Section
from news_briefing.config import AppConfig

logger = logging.getLogger(__name__)

# 板块定义: (category_key, label, config_key, default_min, default_max)
SECTION_DEFS = [
    ("policy", "🏛️ 政策大事", "policy", 2, 5),
    ("ai", "🤖 AI 前沿", "ai_frontier", 3, 6),
    ("business", "💼 企业商业与供应链", "business", 2, 4),
    ("fintech", "💰 金融与市场", "fintech", 2, 5),
    ("watchlist", "🔍 关注动态", "watchlist", 0, 5),
]


def select_sections(
    curated_items: list[CuratedItem],
    config: AppConfig,
) -> list[Section]:
    """分类优先 + 配额保障的板块选取。

    与旧版不同：不再从Top30一刀切，而是先按category分组，
    每组独立排序后按配额选取。

    Args:
        curated_items: 已分类的策展条目。
        config: 应用配置。

    Returns:
        板块列表（按定义顺序）。
    """
    # 按category分组
    by_category: dict[str, list[CuratedItem]] = {}
    for item in curated_items:
        cat = item.category or "general"
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(item)

    # 每组内按item.score降序排序
    for cat in by_category:
        by_category[cat].sort(key=lambda x: x.item.score, reverse=True)

    sections: list[Section] = []

    for cat_key, label, config_key, default_min, default_max in SECTION_DEFS:
        topic_cfg = config.topics.get(config_key, {})
        if isinstance(topic_cfg, dict) and not topic_cfg.get("enabled", True):
            continue

        if isinstance(topic_cfg, dict):
            min_items = topic_cfg.get("min_items", default_min)
            max_items = topic_cfg.get("max_items", default_max)
        else:
            min_items = default_min
            max_items = default_max

        candidates = by_category.get(cat_key, [])

        if not candidates:
            sections.append(Section(
                label=label,
                min_items=min_items,
                max_items=max_items,
                note="今日该板块无重大新闻",
            ))
            continue

        selected = candidates[:max_items]

        if len(selected) < min_items:
            sections.append(Section(
                label=label,
                items=selected,
                min_items=min_items,
                max_items=max_items,
                note=f"今日该板块新闻较少 ({len(selected)} 条)",
            ))
        else:
            sections.append(Section(
                label=label,
                items=selected,
                min_items=min_items,
                max_items=max_items,
            ))

    total_selected = sum(len(s.items) for s in sections)
    logger.info(f"板块选取完成: {len(sections)} 个板块, 共 {total_selected} 条")
    return sections
