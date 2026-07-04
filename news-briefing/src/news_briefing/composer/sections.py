"""简报板块生成逻辑。

根据配置和评分结果，将策展后的条目分配到各板块:
  - 政策大事 (policy)
  - AI 前沿 (ai)
  - 金融科技 (fintech)
  - 关注动态 (watchlist)
"""

import logging

from news_briefing.collector.models import CuratedItem, Section
from news_briefing.config import AppConfig

logger = logging.getLogger(__name__)


def _select_section(
    items: list[CuratedItem],
    category: str,
    label: str,
    min_items: int,
    max_items: int,
    note_if_empty: str = "",
) -> Section:
    """从策展条目中选取指定分类的板块。

    Args:
        items: 策展后的条目列表（已排序）。
        category: 目标分类。
        label: 板块标签。
        min_items: 最少条目数。
        max_items: 最多条目数。
        note_if_empty: 空板块备注。

    Returns:
        Section 对象。
    """
    matching = [i for i in items if i.category == category]

    if not matching:
        return Section(
            label=label,
            min_items=min_items,
            max_items=max_items,
            note=note_if_empty or "今日该板块无重大新闻",
        )

    selected = matching[:max_items]

    if len(selected) < min_items:
        return Section(
            label=label,
            items=selected,
            min_items=min_items,
            max_items=max_items,
            note=f"今日该板块新闻较少 ({len(selected)} 条)",
        )

    return Section(
        label=label,
        items=selected,
        min_items=min_items,
        max_items=max_items,
    )


def select_sections(
    curated_items: list[CuratedItem],
    config: AppConfig,
) -> list[Section]:
    """生成简报的所有板块。

    板块顺序:
      1. 🏛️ 政策大事
      2. 🤖 AI 前沿
      3. 💰 金融科技
      4. 🔍 关注动态

    Args:
        curated_items: 策展后的条目列表。
        config: 应用配置。

    Returns:
        板块列表。
    """
    sections: list[Section] = []

    # 政策大事
    policy_cfg = config.topics.get("policy", {})
    if policy_cfg.get("enabled", True):
        section = _select_section(
            curated_items,
            category="policy",
            label="🏛️ 政策大事",
            min_items=policy_cfg.get("min_items", 2),
            max_items=policy_cfg.get("max_items", 5),
            note_if_empty="今日无重大政策新闻",
        )
        sections.append(section)

    # AI 前沿
    ai_cfg = config.topics.get("ai_frontier", {})
    if ai_cfg.get("enabled", True):
        section = _select_section(
            curated_items,
            category="ai",
            label="🤖 AI 前沿",
            min_items=ai_cfg.get("min_items", 3),
            max_items=ai_cfg.get("max_items", 6),
            note_if_empty="今日无重大 AI 新闻",
        )
        sections.append(section)

    # 金融科技
    fintech_cfg = config.topics.get("fintech", {})
    if fintech_cfg.get("enabled", True):
        section = _select_section(
            curated_items,
            category="fintech",
            label="💰 金融科技",
            min_items=fintech_cfg.get("min_items", 3),
            max_items=fintech_cfg.get("max_items", 8),
            note_if_empty="今日无金融科技重大新闻",
        )
        sections.append(section)

    # 关注动态 (watchlist)
    watchlist_items = [i for i in curated_items if i.category == "watchlist"]
    if watchlist_items:
        section = _select_section(
            curated_items,
            category="watchlist",
            label="🔍 关注动态",
            min_items=0,
            max_items=5,
        )
        sections.append(section)

    total_selected = sum(len(s.items) for s in sections)
    logger.info(f"板块选取完成: {len(sections)} 个板块, 共 {total_selected} 条")

    return sections
