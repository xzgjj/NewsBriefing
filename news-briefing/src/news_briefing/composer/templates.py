"""简报模板系统 — 支持"详细版"和"精简版"两种模式。"""

import logging
from datetime import datetime

from news_briefing.collector.models import Briefing

logger = logging.getLogger(__name__)


def format_compact(briefing: Briefing) -> str:
    """生成精简版简报（每条 1 行）。

    适用于午间快报或用户偏好精简模式。

    Args:
        briefing: 简报对象。

    Returns:
        精简版 Markdown 字符串。
    """
    lines = [
        f"# 📰 {briefing.title}",
        f"**{briefing.date}** | 精选 {briefing.total_selected} 条",
    ]

    if briefing.degradation_note:
        lines.append(f"⚠️ {briefing.degradation_note}")

    lines.append("")

    for section in briefing.sections:
        if not section.items:
            continue
        lines.append(f"### {section.label}")
        for curated in section.items:
            title = curated.display_title or curated.item.detoxed_title or curated.item.title
            source = curated.item.source_name
            # 精简版: 一行搞定
            lines.append(f"- {title} — *{source}*")
        lines.append("")

    lines.append(f"*{briefing.total_raw}条采集 · {briefing.total_selected}条精选*")
    return "\n".join(lines)


def format_detailed(briefing: Briefing) -> str:
    """生成详细版简报（含 AI 摘要和溯源信息）。

    Args:
        briefing: 简报对象。

    Returns:
        详细版 Markdown 字符串。
    """
    # 复用已有的 formatter
    from news_briefing.composer.formatter import format_markdown
    return format_markdown(briefing)


def is_anomaly_trigger_time() -> bool:
    """判断当前是否适合触发午间简报（仅工作日）。

    Returns:
        True 如果当前在工作日的 11:00-14:00。
    """
    now = datetime.now()
    # 工作日：周一到周五
    if now.weekday() >= 5:
        return False
    # 午间窗口
    hour = now.hour
    return 11 <= hour <= 14


def should_trigger_midday(
    anomaly_count: int = 0,
    market_move_pct: float = 0.0,
) -> tuple[bool, str]:
    """判断是否应触发午间简报。

    触发条件:
      - 至少 1 条突发事件新闻
      - 或市场出现 >3% 异动

    Args:
        anomaly_count: 检测到的异常事件数。
        market_move_pct: 市场最大涨跌幅（%）。

    Returns:
        (是否触发, 触发原因)。
    """
    reasons = []

    if anomaly_count > 0:
        reasons.append(f"检测到 {anomaly_count} 条突发事件")

    if abs(market_move_pct) > 3.0:
        direction = "上涨" if market_move_pct > 0 else "下跌"
        reasons.append(f"市场异动: {direction} {abs(market_move_pct):.1f}%")

    if reasons:
        return True, "；".join(reasons)

    return False, ""
