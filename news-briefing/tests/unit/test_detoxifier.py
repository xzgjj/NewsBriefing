"""去毒化器单元测试。"""

from datetime import datetime, timezone

from news_briefing.collector.models import NewsItem, SourceTier, Certainty
from news_briefing.processor.detoxifier import (
    detoxify,
    detoxify_batch,
    _has_sensational,
    _has_uncertainty,
    _has_exaggeration,
    _clean_title,
)


def make_item(title: str, tier: SourceTier = SourceTier.TIER_2) -> NewsItem:
    """创建测试用 NewsItem。"""
    return NewsItem(
        title=title,
        url="http://example.com/test",
        source_name="test_source",
        source_tier=tier,
        published_at=datetime.now(timezone.utc),
    )


class TestDetection:
    """检测功能测试。"""

    def test_detect_sensational(self):
        """检测情绪化关键词。"""
        assert _has_sensational("重磅！A股暴涨5%！")
        assert _has_sensational("震惊！央行突然宣布降息")
        assert not _has_sensational("A股上证指数上涨 5.02%")

    def test_detect_uncertainty(self):
        """检测推测性表述。"""
        assert _has_uncertainty("传央行或将降息50个基点")
        assert _has_uncertainty("知情人士透露苹果将发布新品")
        assert not _has_uncertainty("央行宣布降息50个基点")

    def test_detect_exaggeration(self):
        """检测夸大表述。"""
        assert _has_exaggeration("震惊全球！中国AI取得突破")
        assert not _has_exaggeration("中国AI模型在基准测试中取得进步")


class TestDetoxify:
    """去毒化处理测试。"""

    def test_tier1_preserved(self):
        """Tier 1 标题保持不变。"""
        item = make_item("国务院发布重要政策文件", tier=SourceTier.TIER_1)
        result = detoxify(item)
        assert result.detoxed_title == "国务院发布重要政策文件"
        assert result.original_title is None  # Tier 1 不保留原标题记录

    def test_tier2_sensational_cleaned(self):
        """Tier 2 情绪化标题被清理。"""
        item = make_item("重磅！A股暴涨5%突破3400点！", tier=SourceTier.TIER_2)
        result = detoxify(item)
        # 去毒化后应去掉"重磅！"前缀
        assert not result.detoxed_title.startswith("重磅！")
        assert result.original_title is not None

    def test_uncertainty_flagged(self):
        """推测性表述被标记。"""
        item = make_item("消息人士称央行或将降息", tier=SourceTier.TIER_2)
        result = detoxify(item)
        assert result.certainty == Certainty.UNCERTAIN
        assert "detected_uncertainty" in result.editorial_actions

    def test_normal_title_unchanged(self):
        """正常标题保持不变。"""
        item = make_item("央行发布2026年第二季度货币政策报告")
        result = detoxify(item)
        assert result.detoxed_title == "央行发布2026年第二季度货币政策报告"
        assert result.editorial_actions == []


class TestDetoxifyBatch:
    """批量去毒化测试。"""

    def test_batch_processing(self):
        """批量处理。"""
        items = [
            make_item("重磅！A股暴涨", tier=SourceTier.TIER_2),
            make_item("国务院发布新政策", tier=SourceTier.TIER_1),
            make_item("消息人士称字节将上市", tier=SourceTier.TIER_2),
        ]
        result = detoxify_batch(items)
        assert len(result) == 3
        # 应有至少2条有标记
        flagged = sum(1 for i in result if i.editorial_actions)
        assert flagged >= 2


class TestCleanTitle:
    """标题清理测试。"""

    def test_remove_prefix(self):
        """移除情绪化前缀。"""
        assert _clean_title("重磅！A股大涨") == "A股大涨"

    def test_remove_exclamation(self):
        """移除多余叹号。"""
        cleaned = _clean_title("震惊！！！重大消息")
        assert cleaned.count("！") <= 1
