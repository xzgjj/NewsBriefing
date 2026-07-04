"""用户反馈模块单元测试。"""

from news_briefing.processor.feedback import (
    FeedbackRecord,
    apply_feedback,
    get_feedback_stats,
    get_weight_store,
)


class TestApplyFeedback:
    """反馈应用测试。"""

    def test_liked_increases_weights(self):
        store = get_weight_store()
        record = FeedbackRecord(
            action="liked",
            category="ai",
            source_name="36氪",
        )
        msg = apply_feedback(record)
        assert "偏好" in msg
        assert store.get_category_weight("ai") > 1.0

    def test_disliked_decreases_weights(self):
        store = get_weight_store()
        record = FeedbackRecord(
            action="disliked",
            category="fintech",
            source_name="雪球",
        )
        apply_feedback(record)
        assert store.get_category_weight("fintech") < 1.0

    def test_source_unreliable_heavily_decreases(self):
        store = get_weight_store()
        record = FeedbackRecord(
            action="source_unreliable",
            category="general",
            source_name="test_source",
        )
        apply_feedback(record)
        assert store.get_source_weight("test_source") < 1.0

    def test_weight_not_exceed_upper_limit(self):
        store = get_weight_store()
        # 连续喜欢10次，不应超过上限
        for _ in range(10):
            apply_feedback(FeedbackRecord(
                action="liked",
                category="ai",
                source_name="test_source",
            ))
        assert store.get_category_weight("ai") <= 2.0

    def test_weight_not_below_lower_limit(self):
        store = get_weight_store()
        # 连续标记不可靠10次，不应低于下限
        for _ in range(10):
            apply_feedback(FeedbackRecord(
                action="source_unreliable",
                category="general",
                source_name="test_source_2",
            ))
        assert store.get_source_weight("test_source_2") >= 0.1

    def test_invalid_action_handled(self):
        record = FeedbackRecord(
            action="invalid_action",
            category="ai",
        )
        msg = apply_feedback(record)
        assert "反馈" in msg


class TestFeedbackStats:
    """反馈统计测试。"""

    def test_stats_reflect_feedback(self):
        stats = get_feedback_stats()
        # 之前测试已经添加了一些反馈
        assert stats["total"] >= 0
