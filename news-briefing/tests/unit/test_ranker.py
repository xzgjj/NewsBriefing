"""排序器单元测试。"""

from datetime import datetime, timedelta, timezone

import pytest

from news_briefing.collector.models import NewsItem, SourceTier
from news_briefing.config import AppConfig
from news_briefing.processor.ranker import (
    _freshness_decay,
    _keyword_bonus,
    _tier_weight,
    rank_items,
)


def make_item(
    title: str,
    tier: SourceTier = SourceTier.TIER_2,
    hours_ago: float = 0,
    snippet: str = "",
    cross_validated: list[str] | None = None,
) -> NewsItem:
    """创建测试用 NewsItem。"""
    import hashlib
    published = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return NewsItem(
        title=title,
        url=f"http://example.com/{hash(title) & 0xFFFF}",
        source_name="test_source",
        source_tier=tier,
        content_snippet=snippet,
        published_at=published,
        url_hash=hashlib.sha256(f"http://example.com/{hash(title)}".encode()).hexdigest()[:16],
        cross_validated_by=cross_validated or [],
    )


@pytest.fixture
def config() -> AppConfig:
    """测试用配置。"""
    return AppConfig(
        version="1.0",
        topics={
            "ai": {
                "enabled": True,
                "keywords": ["AI", "大模型", "GPT"],
            },
            "policy": {
                "enabled": True,
                "keywords": ["国务院", "政策"],
            },
        },
        watchlist=[
            {"name": "OpenAI", "keywords": ["OpenAI", "GPT"]},
        ],
    )


class TestTierWeight:
    """信源权重测试。"""

    def test_tier1_highest(self):
        """Tier 1 权重最高。"""
        assert _tier_weight(SourceTier.TIER_1) > _tier_weight(SourceTier.TIER_2)
        assert _tier_weight(SourceTier.TIER_2) > _tier_weight(SourceTier.TIER_3)

    def test_tier1_near_max(self):
        """Tier 1 接近满分。"""
        assert _tier_weight(SourceTier.TIER_1) > 0.9


class TestFreshnessDecay:
    """时效衰减测试。"""

    def test_recent_is_high(self):
        """最近新闻分数高。"""
        assert _freshness_decay(
            datetime.now(timezone.utc)
        ) > 0.95

    def test_old_is_low(self):
        """旧新闻分数低。"""
        old = datetime.now(timezone.utc) - timedelta(hours=48)
        assert _freshness_decay(old) < 0.5

    def test_none_returns_default(self):
        """无时间使用默认值。"""
        assert 0.7 < _freshness_decay(None) < 0.9


class TestKeywordBonus:
    """关键词加分测试。"""

    def test_title_hit(self):
        """标题命中加分高。"""
        title = "国务院发布AI产业新政"
        keywords = ["AI", "国务院"]
        bonus = _keyword_bonus(title, None, keywords)
        assert bonus > 1.0  # 应该有加分

    def test_no_hit(self):
        """无命中不加分。"""
        title = "NBA总决赛结果"
        keywords = ["AI", "大模型", "金融科技"]
        bonus = _keyword_bonus(title, None, keywords)
        assert bonus <= 1.0


class TestRankItems:
    """完整排序测试。"""

    def test_tier1_ranks_higher(self, config):
        """Tier 1 新闻排名高于 Tier 2（同等条件）。"""
        items = [
            make_item("AI大模型发布", tier=SourceTier.TIER_2, hours_ago=1),
            make_item("AI大模型发布", tier=SourceTier.TIER_1, hours_ago=1),
        ]
        ranked = rank_items(items, config)
        assert ranked[0].source_tier == SourceTier.TIER_1

    def test_empty_list(self, config):
        """空列表不崩溃。"""
        result = rank_items([], config)
        assert result == []

    def test_scores_are_positive(self, config):
        """所有分数应为正数。"""
        items = [
            make_item("测试新闻A", hours_ago=5),
            make_item("测试新闻B", hours_ago=10),
        ]
        ranked = rank_items(items, config)
        for item in ranked:
            assert item.score > 0

    def test_keyword_match_ranks_higher(self, config):
        """关键词匹配的新闻排名更高。"""
        items = [
            make_item("NBA比赛结果", hours_ago=1),
            make_item("国务院发布AI产业新政", hours_ago=2),
        ]
        ranked = rank_items(items, config)
        assert "国务院" in ranked[0].title or "AI" in ranked[0].title
