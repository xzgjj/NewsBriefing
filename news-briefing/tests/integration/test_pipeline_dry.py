"""集成测试 — 核心管道（无外部依赖的干跑测试）。"""

import pytest
from datetime import datetime, timezone

from news_briefing.collector.models import (
    NewsItem, CuratedItem, SourceTier,
)
from news_briefing.processor.dedup import deduplicate
from news_briefing.processor.detoxifier import detoxify_batch
from news_briefing.composer.sections import select_sections
from news_briefing.composer.formatter import compose_briefing
from news_briefing.config import AppConfig


@pytest.fixture
def config() -> AppConfig:
    """测试用配置。"""
    return AppConfig(
        version="1.0",
        topics={
            "policy": {"enabled": True, "label": "政策大事", "keywords": ["政策", "国务院"], "min_items": 2, "max_items": 5},
            "ai_frontier": {"enabled": True, "label": "AI前沿", "keywords": ["AI", "大模型"], "min_items": 3, "max_items": 6},
            "fintech": {"enabled": True, "label": "金融科技", "keywords": ["金融"], "min_items": 3, "max_items": 8},
        },
        watchlist=[
            {"name": "OpenAI", "keywords": ["OpenAI", "GPT"]},
        ],
    )


def make_item(
    title: str,
    url: str = "",
    category: str = "general",
    tier: SourceTier = SourceTier.TIER_2,
    snippet: str = "",
) -> NewsItem:
    """创建测试用 NewsItem。"""
    import hashlib
    if not url:
        url = f"http://example.com/{hash(title) & 0xFFFF}"
    return NewsItem(
        title=title,
        url=url,
        source_name="test_source",
        source_tier=tier,
        content_snippet=snippet,
        published_at=datetime.now(timezone.utc),
        url_hash=hashlib.sha256(url.encode()).hexdigest()[:16],
        category=category,
    )


def make_curated(item: NewsItem) -> CuratedItem:
    """创建 CuratedItem。"""
    return CuratedItem(
        item=item,
        category=item.category,
        ai_summary=item.content_snippet,
        display_title=item.detoxed_title or item.title,
    )


class TestDedupToComposePipeline:
    """测试去重→评分→板块选取的管道。"""

    def test_full_pipeline_no_errors(self, config):
        """完整管道不抛异常。"""
        # 1. 创建测试数据
        items = [
            make_item("国务院发布AI产业发展若干意见", category="policy", tier=SourceTier.TIER_1),
            make_item("央行宣布调整货币政策工具", category="policy", tier=SourceTier.TIER_1),
            make_item("DeepSeek发布V4 Flash模型", category="ai"),
            make_item("OpenAI发布GPT-5.1", category="ai"),
            make_item("金融科技公司完成新一轮融资", category="fintech"),
            make_item("区块链支付平台上线", category="fintech"),
            make_item("某明星发布新专辑", category="general"),
        ]

        # 2. 去重
        dedup_result = deduplicate(items)
        assert dedup_result.total_after > 0

        # 3. 去毒化
        detoxify_batch(dedup_result.items)

        # 4. 转换为 CuratedItem（模拟策展）
        curated = [make_curated(item) for item in dedup_result.items]

        # 5. 板块选取
        sections = select_sections(curated, config)
        assert len(sections) >= 2  # 至少有政策 + AI 板块

        # 6. 组装简报
        briefing = compose_briefing(
            sections=sections,
            total_raw=len(items),
            total_after_dedup=dedup_result.total_after,
        )

        assert briefing.total_selected > 0
        assert briefing.markdown_text != ""
        assert "# 📰" in briefing.markdown_text


class TestMarkdownFormatting:
    """Markdown 格式化测试。"""

    def test_briefing_contains_sections(self, config):
        """简报包含所有板块标题。"""
        items = [
            make_item("政策新闻", category="policy", tier=SourceTier.TIER_1),
            make_item("AI新闻", category="ai"),
            make_item("金融新闻", category="fintech"),
        ]
        curated = [make_curated(item) for item in items]
        sections = select_sections(curated, config)
        briefing = compose_briefing(
            sections=sections,
            total_raw=3,
            total_after_dedup=3,
        )

        md = briefing.markdown_text
        assert "🏛️ 政策大事" in md
        assert "🤖 AI 前沿" in md
        assert "💰 金融科技" in md

    def test_markdown_contains_urls(self, config):
        """Markdown 包含原文链接。"""
        items = [
            make_item("测试新闻", url="http://example.com/news/123", category="ai"),
        ]
        curated = [make_curated(item) for item in items]
        sections = select_sections(curated, config)
        briefing = compose_briefing(
            sections=sections,
            total_raw=1,
            total_after_dedup=1,
        )

        assert "http://example.com/news/123" in briefing.markdown_text


class TestDegradation:
    """降级处理测试。"""

    def test_ccompose_with_degradation(self, config):
        """降级模式下简报正常生成。"""
        items = [
            make_item("测试新闻", category="ai"),
        ]
        curated = [make_curated(item) for item in items]
        sections = select_sections(curated, config)

        briefing = compose_briefing(
            sections=sections,
            total_raw=1,
            total_after_dedup=1,
            degradation_level=3,
            degradation_note="⚠️ AI摘要服务不可用",
        )

        assert briefing.degradation_level == 3
        assert "AI摘要" in briefing.degradation_note or "AI摘要" in briefing.markdown_text
