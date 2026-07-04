"""语义去重单元测试。"""

from datetime import datetime, timezone

from news_briefing.collector.models import NewsItem
from news_briefing.processor.semantic_dedup import (
    _cosine_similarity,
    _tf_weighted_tokens,
    semantic_deduplicate,
    semantic_similarity,
)


def make_item(title: str, snippet: str = "", url: str = "") -> NewsItem:
    import hashlib
    return NewsItem(
        title=title,
        url=url or f"http://example.com/{hash(title) & 0xFFFF}",
        source_name="test",
        content_snippet=snippet,
        published_at=datetime.now(timezone.utc),
        url_hash=hashlib.sha256((url or title).encode()).hexdigest()[:16],
    )


class TestTFWeightedTokens:
    """TF加权测试。"""

    def test_empty_text(self):
        assert _tf_weighted_tokens("") == {}

    def test_single_char(self):
        result = _tf_weighted_tokens("A")
        assert result == {}

    def test_bigram_extraction(self):
        result = _tf_weighted_tokens("国务院发布政策")
        assert len(result) > 0
        assert all(v <= 1.0 for v in result.values())


class TestCosineSimilarity:
    """余弦相似度测试。"""

    def test_identical(self):
        vec = _tf_weighted_tokens("国务院发布AI政策")
        assert _cosine_similarity(vec, vec) > 0.99

    def test_different(self):
        a = _tf_weighted_tokens("国务院发布AI政策")
        b = _tf_weighted_tokens("NBA总决赛湖人获胜")
        sim = _cosine_similarity(a, b)
        assert sim < 0.5


class TestSemanticSimilarity:
    """语义相似度测试。"""

    def test_identical_news(self):
        a = make_item("国务院发布AI产业政策", "国务院发布关于促进人工智能产业发展的意见")
        b = make_item("国务院发布AI产业政策", "国务院发布关于促进人工智能产业发展的意见")
        sim = semantic_similarity(a, b)
        assert sim > 0.9

    def test_different_news(self):
        a = make_item("国务院发布AI产业政策", "关于AI产业发展的政策文件")
        b = make_item("NBA湖人队获胜", "湖人队在总决赛中击败凯尔特人")
        sim = semantic_similarity(a, b)
        assert sim < 0.5

    def test_similar_news(self):
        a = make_item("OpenAI发布GPT-5", "GPT-5在多项基准测试中表现出色")
        b = make_item("GPT-5正式发布", "OpenAI最新模型GPT-5发布")
        sim = semantic_similarity(a, b)
        assert sim > 0.3  # 应该有中等相似度


class TestSemanticDedup:
    """语义去重管道测试。"""

    def test_removes_duplicates(self):
        items = [
            make_item("国务院办公厅发布人工智能产业发展若干意见",
                      "国务院今天正式发布了关于促进人工智能产业发展的若干政策措施和指导意见"),
            make_item("国务院发布AI产业发展政策通知全文",
                      "国务院办公厅发布促进人工智能产业发展若干意见的通知文件全文内容"),
            make_item("NBA总决赛洛杉矶湖人队击败凯尔特人夺冠",
                      "湖人队在第七场比赛中击败凯尔特人获得总冠军"),
        ]
        result, removed = semantic_deduplicate(items, threshold=0.3)
        # 前两条应该被识别为相似（文章标题和正文都相似）
        assert removed >= 1
        assert len(result) <= 2

    def test_keeps_unique(self):
        items = [
            make_item("国务院发布AI政策", "关于人工智能产业发展的政策"),
            make_item("央行调整利率", "贷款市场报价利率下调"),
            make_item("NBA总决赛", "湖人获得总冠军"),
        ]
        result, removed = semantic_deduplicate(items, threshold=0.7)
        assert removed == 0
        assert len(result) == 3

    def test_empty_list(self):
        result, removed = semantic_deduplicate([])
        assert removed == 0
        assert result == []
