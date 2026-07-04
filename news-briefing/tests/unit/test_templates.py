"""简报模板单元测试。"""


from news_briefing.collector.models import (
    Briefing,
    CuratedItem,
    NewsItem,
    Section,
)
from news_briefing.composer.templates import (
    format_compact,
    format_detailed,
    should_trigger_midday,
)


def make_briefing() -> Briefing:
    """创建测试简报。"""
    items = []
    for i in range(3):
        ni = NewsItem(
            title=f"测试新闻{i+1}",
            url=f"http://example.com/{i}",
            source_name="测试来源",
            category="general",
        )
        ni.detoxed_title = ni.title
        ci = CuratedItem(
            item=ni,
            category="general",
            display_title=ni.title,
            ai_summary=f"这是测试新闻{i+1}的摘要",
        )
        items.append(ci)

    section = Section(label="📋 测试板块", items=items)
    return Briefing(
        title="测试简报",
        date="2026-07-04",
        sections=[section],
        total_raw=10,
        total_after_dedup=5,
        total_selected=3,
        markdown_text="# 测试",
    )


class TestTemplates:
    """模板测试。"""

    def test_compact_format(self):
        briefing = make_briefing()
        md = format_compact(briefing)
        assert "测试简报" in md
        assert len(md.split("\n")) < 20  # 精简版应该较短

    def test_detailed_format(self):
        briefing = make_briefing()
        md = format_detailed(briefing)
        assert "测试简报" in md
        assert "📎" in md or "#" in md

    def test_compact_includes_section_label(self):
        briefing = make_briefing()
        md = format_compact(briefing)
        assert "📋" in md


class TestMiddayTrigger:
    """午间简报触发测试。"""

    def test_no_anomaly_no_trigger(self):
        trigger, reason = should_trigger_midday(anomaly_count=0, market_move_pct=1.0)
        assert trigger is False
        assert reason == ""

    def test_anomaly_triggers(self):
        trigger, reason = should_trigger_midday(anomaly_count=1, market_move_pct=0)
        assert trigger is True
        assert "突发事件" in reason

    def test_market_move_triggers(self):
        trigger, reason = should_trigger_midday(anomaly_count=0, market_move_pct=5.0)
        assert trigger is True
        assert "异动" in reason

    def test_negative_move_triggers(self):
        trigger, reason = should_trigger_midday(anomaly_count=0, market_move_pct=-4.0)
        assert trigger is True
        assert "下跌" in reason
