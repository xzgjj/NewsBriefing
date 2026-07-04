"""用户交互处理器 — 飞书追问、反馈、配置对话。

处理用户在飞书中对简报的后续交互：
  - "第三条详细说说" → 深度搜索
  - "不感兴趣" → 反馈记录
  - "加关注 XX" → 关注列表管理
"""

import logging

from news_briefing.processor.command_parser import parse_query

logger = logging.getLogger(__name__)


async def handle_followup(
    query: str,
    briefing_context: dict | None = None,
) -> dict:
    """处理用户追问。

    用户对简报中的某条新闻追问详情。

    Args:
        query: 用户追问文本。如"第三条详细说说"、"蚂蚁那个具体什么情况"。
        briefing_context: 最近简报的上下文信息（条目列表等）。

    Returns:
        {type: "followup", message: str, detail: dict}
    """
    # 解析追问意图
    parsed = parse_query(query)

    # 检测序号引用 ("第三条" → index=2)
    import re
    index_match = re.search(r"第\s*([一二三四五六七八九十\d]+)\s*[条个]", query)
    item_index = None
    if index_match:
        num_str = index_match.group(1)
        num_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
                   "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        item_index = num_map.get(num_str) or int(num_str) if num_str.isdigit() else None

    if item_index and briefing_context:
        items = briefing_context.get("items", [])
        if 1 <= item_index <= len(items):
            target = items[item_index - 1]
            return {
                "type": "followup",
                "action": "deep_search",
                "target": target,
                "message": f"正在深度搜索「{target.get('title', '')[:50]}」的相关信息...",
            }

    # 通用追问：按解析的话题搜索
    return {
        "type": "followup",
        "action": "search",
        "topic": parsed.topic or query,
        "message": f"正在搜索「{parsed.topic or query}」的最新信息...",
    }


async def handle_feedback(
    action: str,
    item_title: str = "",
    source_name: str = "",
    category: str = "",
) -> dict:
    """处理用户反馈。

    Args:
        action: liked | disliked | source_unreliable。
        item_title: 条目标题。
        source_name: 来源名称。
        category: 分类。

    Returns:
        {type: "feedback", message: str}
    """
    from news_briefing.processor.feedback import FeedbackRecord, apply_feedback

    record = FeedbackRecord(
        action=action,
        category=category,
        source_name=source_name,
        comment=item_title,
    )
    msg = apply_feedback(record)

    return {
        "type": "feedback",
        "action": action,
        "message": msg,
    }


async def handle_config_command(text: str) -> dict:
    """处理配置命令。

    Args:
        text: 用户输入文本。

    Returns:
        {type, action, message}
    """
    parsed = parse_query(text)

    if parsed.mode == "add_watchlist":
        return {
            "type": "config",
            "action": "add_watchlist",
            "name": parsed.topic or text.replace("加关注", "").strip(),
            "message": "✅ 已添加关注。将在下期简报中追踪相关新闻。",
        }
    if parsed.mode == "remove_watchlist":
        return {
            "type": "config",
            "action": "remove_watchlist",
            "name": parsed.topic or text.replace("取消关注", "").strip(),
            "message": "✅ 已取消关注。",
        }
    if parsed.mode == "list_watchlist":
        return {
            "type": "config",
            "action": "list_watchlist",
            "message": "📋 当前关注列表（从config.yaml读取）。",
        }
    if parsed.mode == "system_status":
        from news_briefing.monitor import get_source_monitor, get_tavily_quota
        monitor = get_source_monitor()
        quota = get_tavily_quota()
        stats = monitor.get_stats()
        return {
            "type": "config",
            "action": "status",
            "message": (
                f"📊 信源: {stats['healthy']}/{stats['total_sources']} 正常\n"
                f"   Tavily: {quota.remaining}/{quota.monthly_limit} 剩余"
            ),
        }

    return {
        "type": "config",
        "action": "unknown",
        "message": f"未识别的命令: {text}",
    }
