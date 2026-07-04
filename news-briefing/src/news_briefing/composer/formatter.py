"""简报格式化 — Markdown 和飞书卡片生成。"""

import json
import logging
from datetime import datetime

from news_briefing.collector.models import Briefing, Section, Importance

logger = logging.getLogger(__name__)


def format_markdown(briefing: Briefing) -> str:
    """将简报格式化为 Markdown。

    Args:
        briefing: 简报对象。

    Returns:
        Markdown 字符串。
    """
    lines: list[str] = []

    # 标题
    lines.append(f"# 📰 {briefing.title}")
    lines.append(f"**{briefing.date}** | "
                 f"模式: {briefing.mode} | "
                 f"精选: {briefing.total_selected} 条")

    if briefing.degradation_note:
        lines.append(f"\n⚠️ **{briefing.degradation_note}**")

    lines.append("")
    lines.append("---")
    lines.append("")

    # 各板块
    for section in briefing.sections:
        lines.append(f"## {section.label}")
        lines.append("")

        if section.note and not section.items:
            lines.append(f"*{section.note}*")
            lines.append("")
            continue

        for i, curated in enumerate(section.items, 1):
            item = curated.item
            display_title = curated.display_title or item.detoxed_title or item.title

            # 重要性标记
            prefix = ""
            if item.importance == Importance.RED:
                prefix = "🔴 "
            elif item.importance == Importance.YELLOW:
                prefix = "🟡 "

            # 不确定标记
            uncertainty = ""
            if curated.uncertainty_label:
                uncertainty = f" | {curated.uncertainty_label}"

            lines.append(f"{i}. {prefix}**{display_title}**{uncertainty}")

            # AI 摘要
            if curated.ai_summary:
                lines.append(f"   {curated.ai_summary[:200]}")

            # 溯源信息
            source_info = f"📎 {item.source_name}"
            if item.published_at:
                # 格式化时间
                from datetime import timezone, timedelta
                tz = timezone(timedelta(hours=8))
                local_time = item.published_at.astimezone(tz)
                source_info += f" | {local_time.strftime('%H:%M')}"

            if item.cross_validated_by:
                source_info += f" | ✅ {', '.join(item.cross_validated_by)}"

            lines.append(f"   {source_info}")
            lines.append(f"   🔗 {item.url}")
            lines.append("")

        lines.append("---")
        lines.append("")

    # 元信息
    lines.append(f"*基于 {briefing.total_raw} 条原始采集 · "
                 f"{briefing.total_after_dedup} 条去重后 · "
                 f"{briefing.total_selected} 条精选*")
    lines.append(f"*生成时间: {briefing.generated_at.strftime('%Y-%m-%d %H:%M:%S')}*")

    md = "\n".join(lines)
    briefing.markdown_text = md
    return md


def format_feishu_card(briefing: Briefing) -> dict:
    """生成飞书卡片消息 JSON。

    Args:
        briefing: 简报对象。

    Returns:
        飞书卡片消息 JSON dict。
    """
    # 先用 Markdown 格式化内容
    markdown = briefing.markdown_text or format_markdown(briefing)

    # 飞书卡片结构
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"📰 {briefing.title}",
            },
            "template": "blue",
        },
        "elements": [
            {
                "tag": "markdown",
                "content": markdown,
            },
            {
                "tag": "hr",
            },
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": (
                            f"基于 {briefing.total_raw} 条采集 | "
                            f"{briefing.total_selected} 条精选 | "
                            f"AI 辅助生成"
                        ),
                    }
                ],
            },
        ],
    }

    briefing.feishu_card_json = json.dumps(card, ensure_ascii=False)
    return card


def compose_briefing(
    sections: list[Section],
    total_raw: int = 0,
    total_after_dedup: int = 0,
    degradation_level: int = 0,
    degradation_note: str = "",
    mode: str = "scheduled",
) -> Briefing:
    """组装完整简报。

    Args:
        sections: 板块列表。
        total_raw: 原始采集量。
        total_after_dedup: 去重后数量。
        degradation_level: 降级级别。
        degradation_note: 降级说明。
        mode: 简报模式。

    Returns:
        Briefing 对象。
    """
    total_selected = sum(len(s.items) for s in sections if s.items)

    now = datetime.now()
    briefing = Briefing(
        title=f"每日情报简报 — {now.strftime('%Y年%m月%d日')}",
        date=now.strftime("%Y-%m-%d"),
        mode=mode,
        sections=sections,
        total_raw=total_raw,
        total_after_dedup=total_after_dedup,
        total_selected=total_selected,
        degradation_level=degradation_level,
        degradation_note=degradation_note,
        generated_at=now,
    )

    # 生成 Markdown 和飞书卡片
    format_markdown(briefing)
    format_feishu_card(briefing)

    logger.info(
        f"简报组装完成: {total_selected} 条精选, "
        f"降级级别: {degradation_level}"
    )
    return briefing
