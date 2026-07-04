"""分类器（关键词规则）单元测试。"""


from news_briefing.processor.curator import _fallback_classify


class TestFallbackClassify:
    """规则分类测试。"""

    def test_classify_policy(self):
        """政策类分类。"""
        assert _fallback_classify("国务院发布AI产业政策") == "policy"
        assert _fallback_classify("央行宣布调整货币政策") == "policy"
        assert _fallback_classify("证监会发布新规加强监管") == "policy"

    def test_classify_ai(self):
        """AI 类分类。"""
        assert _fallback_classify("DeepSeek发布新版大模型") == "ai"
        assert _fallback_classify("GPT-5在基准测试中取得突破") == "ai"
        assert _fallback_classify("Claude Opus 4.8 发布") == "ai"
        assert _fallback_classify("开源模型Llama 4发布") == "ai"

    def test_classify_fintech(self):
        """金融科技类分类。"""
        assert _fallback_classify("数字货币支付试点扩大范围") == "fintech"
        assert _fallback_classify("区块链技术在支付领域应用") == "fintech"

    def test_classify_tech(self):
        """科技类分类。"""
        assert _fallback_classify("台积电3nm芯片量产") == "tech"
        assert _fallback_classify("新能源汽车销量增长") == "tech"

    def test_classify_general(self):
        """非匹配内容归类为 general。"""
        assert _fallback_classify("今天天气很好") == "general"
        assert _fallback_classify("某明星发布新专辑") == "general"
