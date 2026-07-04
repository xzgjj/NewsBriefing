"""用户反馈处理模块。

处理用户对简报内容的反馈，调整信源和类别权重。
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 权重调整系数
WEIGHT_ADJUSTMENTS = {
    "liked": {
        "category": 1.1,     # 类别 +10%
        "source": 1.05,      # 来源 +5%
    },
    "disliked": {
        "category": 0.9,     # 类别 -10%
        "source": 0.9,       # 来源 -10%
    },
    "source_unreliable": {
        "source": 0.7,       # 来源 -30%
    },
}

# 权重上下限
WEIGHT_LIMITS = {
    "category": (0.3, 2.0),
    "source": (0.1, 1.5),
}


@dataclass
class FeedbackRecord:
    """用户反馈记录。"""
    action: str                     # liked | disliked | source_unreliable
    news_id: int | None = None
    briefing_id: int | None = None
    category: str = ""
    source_name: str = ""
    comment: str = ""


@dataclass
class WeightStore:
    """权重存储（内存中，单用户无需持久化到数据库）。"""

    category_weights: dict[str, float] = field(default_factory=dict)
    source_weights: dict[str, float] = field(default_factory=dict)

    def get_category_weight(self, category: str) -> float:
        """获取类别权重。

        Args:
            category: 类别名称。

        Returns:
            权重值（0.3 ~ 2.0）。
        """
        return self.category_weights.get(category, 1.0)

    def get_source_weight(self, source_name: str) -> float:
        """获取信源权重。

        Args:
            source_name: 信源名称。

        Returns:
            权重值（0.1 ~ 1.5）。
        """
        return self.source_weights.get(source_name, 1.0)


# 全局权重存储（单用户，内存即可）
_weight_store = WeightStore()
_feedback_history: list[FeedbackRecord] = []


def apply_feedback(record: FeedbackRecord) -> str:
    """应用用户反馈，更新权重。

    Args:
        record: 反馈记录。

    Returns:
        用户可读的反馈确认消息。
    """
    global _weight_store
    _feedback_history.append(record)

    adj = WEIGHT_ADJUSTMENTS.get(record.action, {})
    limits = WEIGHT_LIMITS

    messages = {
        "liked": "👍 已记录偏好，后续将优先展示此类内容。",
        "disliked": "👎 已记录。此类内容将降权。",
        "source_unreliable": "⚠️ 已降低该来源权重。如继续标记，将建议移除该信源。",
    }

    # 更新类别权重
    if "category" in adj and record.category:
        current = _weight_store.get_category_weight(record.category)
        new = current * adj["category"]
        lo, hi = limits["category"]
        _weight_store.category_weights[record.category] = max(lo, min(hi, new))
        logger.info(
            f"类别权重更新: {record.category} {current:.2f} → "
            f"{_weight_store.category_weights[record.category]:.2f}"
        )

    # 更新来源权重
    if "source" in adj and record.source_name:
        current = _weight_store.get_source_weight(record.source_name)
        new = current * adj["source"]
        lo, hi = limits["source"]
        _weight_store.source_weights[record.source_name] = max(lo, min(hi, new))

        # 如果来源被标记3次不可靠，建议移除
        unreliable_count = sum(
            1 for r in _feedback_history
            if r.action == "source_unreliable" and r.source_name == record.source_name
        )
        if unreliable_count >= 3:
            logger.warning(
                f"信源 {record.source_name} 已被标记 {unreliable_count} 次不可靠，建议移除"
            )

        logger.info(
            f"来源权重更新: {record.source_name} {current:.2f} → "
            f"{_weight_store.source_weights[record.source_name]:.2f}"
        )

    return messages.get(record.action, "已记录反馈")


def get_weight_store() -> WeightStore:
    """获取当前权重存储。

    Returns:
        WeightStore 实例。
    """
    return _weight_store


def get_feedback_stats() -> dict:
    """获取反馈统计。

    Returns:
        包含各类反馈计数的字典。
    """
    stats = {"liked": 0, "disliked": 0, "source_unreliable": 0, "total": 0}
    for r in _feedback_history:
        if r.action in stats:
            stats[r.action] += 1
        stats["total"] += 1
    return stats
