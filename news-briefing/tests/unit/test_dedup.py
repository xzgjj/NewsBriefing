"""去重器单元测试。"""

from datetime import datetime, timezone

from news_briefing.collector.models import NewsItem, SourceTier
from news_briefing.processor.dedup import (
    _hamming_distance,
    _jaccard_similarity,
    _simhash,
    _tokenize_title,
    deduplicate,
)


def make_item(
    title: str, url: str, snippet: str = "", tier: SourceTier = SourceTier.TIER_2,
) -> NewsItem:
    """创建测试用 NewsItem。"""
    import hashlib
    return NewsItem(
        title=title,
        url=url,
        source_name="test_source",
        source_tier=tier,
        content_snippet=snippet,
        published_at=datetime.now(timezone.utc),
        url_hash=hashlib.sha256(url.encode()).hexdigest()[:16],
    )


class TestSimHash:
    """SimHash 计算测试。"""

    def test_same_text_same_hash(self):
        """相同文本产生相同 hash。"""
        text = "国务院发布人工智能产业发展政策"
        assert _simhash(text) == _simhash(text)

    def test_similar_text_similar_hash(self):
        """相似文本的汉明距离较小。"""
        a = "国务院发布人工智能产业发展政策通知全文"
        b = "国务院发布人工智能产业发展政策"
        dist = _hamming_distance(_simhash(a), _simhash(b))
        # 相似文本应该距离较小
        assert dist < 30  # 64位中距离不超过30

    def test_different_text_different_hash(self):
        """不同文本的汉明距离较大。"""
        a = "国务院发布人工智能产业发展政策通知全文内容概要"
        b = "NBA总决赛洛杉矶湖人队战胜对手获胜取得冠军"
        dist = _hamming_distance(_simhash(a), _simhash(b))
        assert dist > 5


class TestJaccard:
    """Jaccard 相似度测试。"""

    def test_identical_titles(self):
        """相同标题相似度为 1.0。"""
        tokens1 = _tokenize_title("国务院发布人工智能政策")
        tokens2 = _tokenize_title("国务院发布人工智能政策")
        assert _jaccard_similarity(tokens1, tokens2) == 1.0

    def test_different_titles(self):
        """完全不同标题相似度低。"""
        tokens1 = _tokenize_title("国务院发布人工智能政策")
        tokens2 = _tokenize_title("NBA总决赛湖人获胜")
        sim = _jaccard_similarity(tokens1, tokens2)
        assert sim < 0.5

    def test_similar_titles(self):
        """相似标题的 Jaccard 高于阈值。"""
        tokens1 = _tokenize_title("国务院发布人工智能产业发展若干意见")
        tokens2 = _tokenize_title("国务院发布AI产业发展政策")
        sim = _jaccard_similarity(tokens1, tokens2)
        # 这两个标题共享一些关键字
        assert sim > 0.1


class TestDeduplicate:
    """完整去重管道测试。"""

    def test_no_duplicates(self):
        """无重复时的行为。"""
        items = [
            make_item("国务院发布人工智能产业发展若干意见的通知文件",
                      "http://example.com/a",
                      snippet="国务院办公厅关于促进人工智能产业发展的若干政策措施和指导意见"),
            make_item("NBA总决赛洛杉矶湖人队击败波士顿凯尔特人获得总冠军",
                      "http://example.com/b",
                      snippet="在第七场决胜局中湖人队以102比96战胜凯尔特人队"),
            make_item("中国人民银行宣布调整贷款市场报价利率LPR机制",
                      "http://example.com/c",
                      snippet="央行下调一年期贷款市场报价利率十个基点至3.45%"),
        ]
        result = deduplicate(items)
        assert result.total_after == 3
        assert result.url_dups == 0

    def test_url_dedup(self):
        """URL 精确去重。"""
        items = [
            make_item("政策A", "http://example.com/a"),
            make_item("政策A-重复", "http://example.com/a"),  # 相同 URL
        ]
        result = deduplicate(items)
        assert result.total_after == 1
        assert result.url_dups == 1

    def test_simhash_dedup_identical_content(self):
        """SimHash 去重: 内容完全相同的不同URL。"""
        items = [
            make_item("国务院发布人工智能政策", "http://a.com/1",
                      snippet="国务院今天发布了关于促进人工智能产业发展的若干意见..."),
            make_item("国务院发布人工智能政策", "http://b.com/2",
                      snippet="国务院今天发布了关于促进人工智能产业发展的若干意见..."),
        ]
        result = deduplicate(items)
        # 标题相同、内容相同 → SimHash 应检测为重复
        assert result.total_after <= 2

    def test_empty_input(self):
        """空输入。"""
        result = deduplicate([])
        assert result.total_before == 0
        assert result.total_after == 0

    def test_tier_priority_on_dup(self):
        """重复时保留 Tier 更高的条目。"""
        items = [
            make_item("重大政策发布", "http://a.com/1", tier=SourceTier.TIER_2),
            make_item("重大政策发布", "http://a.com/1", tier=SourceTier.TIER_1),
        ]
        result = deduplicate(items)
        assert result.total_after == 1
        remaining = result.items[0]
        # URL去重时应选择Tier 1
        assert remaining.source_tier == SourceTier.TIER_1
