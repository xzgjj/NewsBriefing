"""系统监控单元测试。"""

from datetime import datetime, timezone, timedelta

from news_briefing.collector.models import SourceTier
from news_briefing.monitor import (
    SourceHealthMonitor,
    TavilyQuota,
    detect_anomaly_count,
    filter_cross_period_duplicates,
)


class TestSourceHealthMonitor:
    """信源健康监控测试。"""

    def test_record_success_resets_failures(self):
        monitor = SourceHealthMonitor()
        monitor.record_failure("test_source", SourceTier.TIER_2, "timeout")
        monitor.record_failure("test_source", SourceTier.TIER_2, "timeout")
        monitor.record_success("test_source", SourceTier.TIER_2)
        health = monitor.get_or_create("test_source", SourceTier.TIER_2)
        assert health.consecutive_failures == 0

    def test_consecutive_failures_trigger_pause(self):
        monitor = SourceHealthMonitor()
        alert = ""
        for _ in range(5):
            alert = monitor.record_failure("test_source", SourceTier.TIER_2, "timeout")
        assert "已自动暂停" in alert
        health = monitor.get_or_create("test_source", SourceTier.TIER_2)
        assert health.paused is True

    def test_auto_recover_after_duration(self):
        monitor = SourceHealthMonitor()
        for _ in range(5):
            monitor.record_failure("test_source", SourceTier.TIER_2, "timeout")
        # 手动修改 last_failure 到 25 小时前
        health = monitor.get_or_create("test_source", SourceTier.TIER_2)
        health.last_failure = datetime.now(timezone.utc) - timedelta(hours=25)
        recovered = monitor.check_auto_recover("test_source")
        assert recovered is True
        assert health.paused is False

    def test_get_alerts(self):
        monitor = SourceHealthMonitor()
        for _ in range(3):
            monitor.record_failure("bad_source", SourceTier.TIER_2, "timeout")
        alerts = monitor.get_alerts()
        assert any("bad_source" in a for a in alerts)

    def test_stats(self):
        monitor = SourceHealthMonitor()
        monitor.record_success("good", SourceTier.TIER_1)
        monitor.record_failure("bad", SourceTier.TIER_2, "error")
        stats = monitor.get_stats()
        assert stats["total_sources"] == 2
        assert stats["tier1_healthy"] == 1


class TestTavilyQuota:
    """Tavily 额度管理测试。"""

    def test_consume_reduces_remaining(self):
        quota = TavilyQuota(monthly_limit=1000)
        quota.consume(5)
        assert quota.remaining == 995
        assert quota.used_this_month == 5

    def test_is_exhausted(self):
        quota = TavilyQuota(monthly_limit=1000)
        quota.used_this_month = 1000
        assert quota.is_exhausted is True

    def test_is_low_at_90_percent(self):
        quota = TavilyQuota(monthly_limit=1000)
        quota.used_this_month = 950
        assert quota.is_low is True


class TestAnomalyDetection:
    """异常新闻量检测测试。"""

    def test_too_few(self):
        msg = detect_anomaly_count(5)
        assert msg is not None
        assert "极少" in msg

    def test_too_many(self):
        msg = detect_anomaly_count(600)
        assert msg is not None
        assert "异常大" in msg

    def test_normal(self):
        msg = detect_anomaly_count(100)
        assert msg is None

    def test_boundary_min(self):
        msg = detect_anomaly_count(10)
        assert msg is None  # 等于下限是正常的

    def test_boundary_max(self):
        msg = detect_anomaly_count(500)
        assert msg is None  # 等于上限是正常的


class TestCrossPeriodDedup:
    """跨期去重测试。"""

    def test_filter_exact_match(self):
        from news_briefing.collector.models import NewsItem as NI
        items = [
            NI(title="昨日已推送的新闻", url="http://a.com/1", source_name="test",
               url_hash="abc"),
            NI(title="今日新新闻", url="http://a.com/2", source_name="test",
               url_hash="def"),
        ]
        for item in items:
            item.detoxed_title = item.title

        yesterday = {"昨日已推送的新闻", "另一条旧闻"}
        filtered, removed = filter_cross_period_duplicates(items, yesterday)
        assert removed == 1
        assert len(filtered) == 1
        assert filtered[0].title == "今日新新闻"

    def test_no_yesterday_no_removal(self):
        from news_briefing.collector.models import NewsItem as NI
        items = [
            NI(title="任意新闻", url="http://a.com/1", source_name="test",
               url_hash="abc"),
        ]
        filtered, removed = filter_cross_period_duplicates(items, set())
        assert removed == 0
        assert len(filtered) == 1
