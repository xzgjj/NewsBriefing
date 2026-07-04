"""系统监控与健康管理。

包含:
  1. 信源健康监控 — 连续失败追踪、自动暂停/恢复
  2. Tavily 额度监控 — 使用量追踪、自动切换备用搜索
  3. 异常新闻量检测 — 太少/太多时告警
  4. 跨期去重 — 对比昨日简报避免重复推送
  5. 启动健康检查 — 检测遗漏简报
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from news_briefing.collector.models import NewsItem, SourceTier

logger = logging.getLogger(__name__)


# ============================================================
# 信源健康监控
# ============================================================

@dataclass
class SourceHealth:
    """单个信源的健康状态。"""
    name: str
    tier: SourceTier
    consecutive_failures: int = 0
    total_fetches: int = 0
    total_failures: int = 0
    last_success: datetime | None = None
    last_failure: datetime | None = None
    enabled: bool = True
    paused: bool = False
    pause_reason: str = ""

    @property
    def success_rate(self) -> float:
        if self.total_fetches == 0:
            return 1.0
        return 1.0 - (self.total_failures / self.total_fetches)

    @property
    def is_healthy(self) -> bool:
        return self.enabled and not self.paused


class SourceHealthMonitor:
    """信源健康监控器。"""

    MAX_CONSECUTIVE_FAILURES = 5
    PAUSE_DURATION_HOURS = 24  # 暂停24小时后自动恢复

    def __init__(self):
        self._sources: dict[str, SourceHealth] = {}

    def get_or_create(self, name: str, tier: SourceTier) -> SourceHealth:
        """获取或创建信源健康记录。"""
        if name not in self._sources:
            self._sources[name] = SourceHealth(name=name, tier=tier)
        return self._sources[name]

    def record_success(self, name: str, tier: SourceTier) -> None:
        """记录一次成功采集。"""
        health = self.get_or_create(name, tier)
        health.total_fetches += 1
        health.last_success = datetime.now(timezone.utc)
        health.consecutive_failures = 0

    def record_failure(self, name: str, tier: SourceTier, error: str = "") -> str:
        """记录一次采集失败。返回告警消息（如果需要的话）。

        Args:
            name: 信源名称。
            tier: 信源等级。
            error: 错误信息。

        Returns:
            告警消息字符串。如果不需要告警则返回空字符串。
        """
        health = self.get_or_create(name, tier)
        health.total_fetches += 1
        health.total_failures += 1
        health.last_failure = datetime.now(timezone.utc)
        health.consecutive_failures += 1

        alert = ""

        if health.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES and not health.paused:
            health.paused = True
            health.pause_reason = (
                f"连续 {health.consecutive_failures} 次失败，"
                f"已于 {datetime.now():%H:%M} 自动暂停"
            )
            alert = (
                f"⚠️ {name} 已连续 {health.consecutive_failures} 次采集失败，"
                f"已自动暂停。将在 24h 后自动恢复。"
            )
            logger.warning(alert)

        return alert

    def check_auto_recover(self, name: str) -> bool:
        """检查暂停的信源是否应该自动恢复。

        Args:
            name: 信源名称。

        Returns:
            True 如果已恢复。
        """
        health = self._sources.get(name)
        if not health or not health.paused:
            return False

        if health.last_failure:
            elapsed = datetime.now(timezone.utc) - health.last_failure
            if elapsed > timedelta(hours=self.PAUSE_DURATION_HOURS):
                health.paused = False
                health.consecutive_failures = 0
                health.pause_reason = ""
                logger.info(f"✅ {name} 已自动恢复 (暂停 {elapsed.total_seconds()/3600:.1f}h)")
                return True

        return False

    def get_alerts(self) -> list[str]:
        """获取所有需要通知的告警。

        Returns:
            告警消息列表。
        """
        alerts: list[str] = []
        for name, health in self._sources.items():
            if health.paused:
                alerts.append(f"⚠️ {name}: {health.pause_reason}")
            elif health.consecutive_failures >= 3:
                alerts.append(
                    f"⚠️ {name}: 最近 {health.consecutive_failures} 次采集失败 "
                    f"(成功率 {health.success_rate:.0%})"
                )
        return alerts

    def get_stats(self) -> dict:
        """获取监控统计。

        Returns:
            统计字典。
        """
        total = len(self._sources)
        healthy = sum(1 for s in self._sources.values() if s.is_healthy)
        paused = sum(1 for s in self._sources.values() if s.paused)

        return {
            "total_sources": total,
            "healthy": healthy,
            "paused": paused,
            "tier1_healthy": sum(
                1 for s in self._sources.values()
                if s.is_healthy and s.tier == SourceTier.TIER_1
            ),
        }


# 全局实例
_source_monitor = SourceHealthMonitor()


def get_source_monitor() -> SourceHealthMonitor:
    """获取全局信源健康监控器。"""
    return _source_monitor


# ============================================================
# Tavily 额度管理
# ============================================================

@dataclass
class TavilyQuota:
    """Tavily 额度追踪。"""
    monthly_limit: int = 1000
    used_this_month: int = 0
    last_reset: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def remaining(self) -> int:
        return max(0, self.monthly_limit - self.used_this_month)

    @property
    def usage_pct(self) -> float:
        return self.used_this_month / self.monthly_limit * 100

    @property
    def is_exhausted(self) -> bool:
        return self.remaining <= 0

    @property
    def is_low(self) -> bool:
        """低于 10% 时预警。"""
        return self.usage_pct > 90

    def consume(self, count: int = 1) -> None:
        """消耗额度。"""
        # 检查是否需要重置（每月）
        now = datetime.now(timezone.utc)
        if now.month != self.last_reset.month or now.year != self.last_reset.year:
            self.used_this_month = 0
            self.last_reset = now
            logger.info("Tavily 额度已重置 (新月)")

        self.used_this_month += count

        if self.is_low:
            logger.warning(
                f"Tavily 额度不足: {self.remaining}/{self.monthly_limit} "
                f"({self.usage_pct:.0f}%)"
            )
        if self.is_exhausted:
            logger.critical("Tavily 额度已耗尽! 将切换到备用搜索")


_tavily_quota = TavilyQuota()


def get_tavily_quota() -> TavilyQuota:
    """获取全局 Tavily 额度追踪。"""
    return _tavily_quota


# ============================================================
# 异常新闻量检测
# ============================================================

def detect_anomaly_count(
    total_items: int,
    min_normal: int = 10,
    max_normal: int = 500,
) -> str | None:
    """检测新闻采集量是否异常。

    Args:
        total_items: 本次采集总量。
        min_normal: 正常下限。
        max_normal: 正常上限。

    Returns:
        异常描述字符串。正常时返回 None。
    """
    if total_items < min_normal:
        return (
            f"📭 今日新闻极少 ({total_items} 条)，可能是节假日或采集系统故障。"
            f"简报内容将相应减少但不会被填充。"
        )
    if total_items > max_normal:
        return (
            f"⚠️ 今日新闻量异常大 ({total_items} 条)，"
            f"已截取最重要的 20 条。可通过 /briefing full 查看完整列表。"
        )
    return None


# ============================================================
# 跨期去重
# ============================================================

def load_yesterday_titles(archive_dir: str = "data/archive") -> set[str]:
    """加载昨天简报中的标题，用于跨期去重。

    Args:
        archive_dir: 归档目录。

    Returns:
        昨日标题集合。
    """
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    archive_path = Path(archive_dir) / f"{yesterday}.md"

    if not archive_path.exists():
        logger.debug(f"昨日归档不存在: {archive_path}")
        return set()

    try:
        content = archive_path.read_text(encoding="utf-8")
        # 提取 Markdown 中的新闻标题（以数字+点号开头的行）
        import re
        titles = set()
        for line in content.split("\n"):
            match = re.match(r"^\d+\.\s*(?:🔴\s*|🟡\s*)?\*\*(.+?)\*\*", line)
            if match:
                titles.add(match.group(1).strip())

        logger.debug(f"加载昨日标题: {len(titles)} 条")
        return titles

    except Exception as e:
        logger.warning(f"读取昨日归档失败: {e}")
        return set()


def filter_cross_period_duplicates(
    items: list[NewsItem],
    yesterday_titles: set[str],
) -> tuple[list[NewsItem], int]:
    """过滤与昨日简报重复的新闻。

    使用标题 Jaccard 相似度与昨日标题比较。

    Args:
        items: 今日新闻列表。
        yesterday_titles: 昨日标题集合。

    Returns:
        (过滤后的列表, 过滤数量)。
    """
    if not yesterday_titles:
        return items, 0

    filtered = []
    removed = 0

    for item in items:
        title = item.detoxed_title or item.title
        # 精确匹配昨日标题
        if title in yesterday_titles:
            removed += 1
            logger.debug(f"跨期去重: '{title[:50]}...'")
            continue
        filtered.append(item)

    if removed:
        logger.info(f"跨期去重: 移除 {removed} 条昨日已推送的新闻")

    return filtered, removed


# ============================================================
# 启动健康检查
# ============================================================

def check_missed_briefing(archive_dir: str = "data/archive") -> str | None:
    """检查是否有遗漏的简报（系统启动时调用）。

    Args:
        archive_dir: 归档目录。

    Returns:
        遗漏描述。无遗漏返回 None。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    archive_path = Path(archive_dir)
    if not archive_path.exists():
        return "归档目录不存在，首次运行"

    today_file = archive_path / f"{today}.md"
    yesterday_file = archive_path / f"{yesterday}.md"

    if not today_file.exists():
        if not yesterday_file.exists():
            return (
                f"⚠️ 检测到可能遗漏了简报。"
                f"最近归档: {_find_latest_archive(archive_dir) or '无'}。"
                f"是否需要立即生成？"
            )
        yesterday_mtime = datetime.fromtimestamp(
            yesterday_file.stat().st_mtime
        ).strftime("%H:%M")
        return (
            f"昨日简报已生成 ({yesterday_mtime})，"
            f"今日简报尚未生成。是否需要立即生成？"
        )

    return None


def _find_latest_archive(archive_dir: str) -> str | None:
    """寻找最近归档文件日期。"""
    archive_path = Path(archive_dir)
    if not archive_path.exists():
        return None
    files = sorted(archive_path.glob("*.md"), reverse=True)
    if files:
        return files[0].stem
    return None
