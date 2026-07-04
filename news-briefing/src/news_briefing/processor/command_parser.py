"""命令解析器 — 解析用户飞书消息中的意图。

支持:
  - 结构化命令: /briefing today, /briefing topic <主题>
  - 自然语言: "今天有什么关于XX的新闻"
  - 关键词+规则兜底保证不返回空
"""

import re
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ParsedIntent:
    """解析后的用户意图。"""
    topic: str = ""
    time_range: str = "today"       # today | yesterday | week | recent
    mode: str = "query"             # query | full_briefing | company
    company: str = ""               # 企业名（company 模式）
    raw: str = ""


# ============================================================
# 预定义命令模式
# ============================================================

COMMAND_PATTERNS: list[tuple[re.Pattern, dict]] = [
    # /briefing today → 生成今日简报
    (re.compile(r"^/briefing\s+today$", re.I),
     {"mode": "full_briefing", "time_range": "today"}),

    # /briefing topic <主题>
    (re.compile(r"^/briefing\s+topic\s+(.+)$", re.I),
     {"mode": "query"}),

    # /briefing company <企业>
    (re.compile(r"^/briefing\s+company\s+(.+)$", re.I),
     {"mode": "company"}),

    # 加关注 <企业>
    (re.compile(r"^加关注\s+(.+)$"),
     {"mode": "add_watchlist"}),

    # 取消关注 <企业>
    (re.compile(r"^取消关注\s+(.+)$"),
     {"mode": "remove_watchlist"}),

    # 我的关注
    (re.compile(r"^我的关注$"),
     {"mode": "list_watchlist"}),

    # 系统状态
    (re.compile(r"^系统状态$"),
     {"mode": "system_status"}),
]


# ============================================================
# 自然语言模式
# ============================================================

NL_PATTERNS: list[tuple[re.Pattern, dict]] = [
    # "今天有什么关于XX的新闻"
    (re.compile(r"(?:今天|今日).*(?:关于|有关)(.+?)(?:的|有什么).*(?:新闻|消息|动态)"),
     {"time_range": "today"}),

    # "XX的最新消息"
    (re.compile(r"(.+?)(?:的|有什么).*(?:最新|最近).*(?:新闻|消息|动态)"),
     {"time_range": "recent"}),

    # "有什么关于XX的新闻"
    (re.compile(r".*(?:关于|有关)(.+?)(?:的|有什么).*(?:新闻|消息)"),
     {"time_range": "today"}),

    # "XX怎么样" → 可能是公司查询
    (re.compile(r"^(.+?)(?:最近|近期|今天).*(?:怎么样|如何|有什么)"),
     {"time_range": "recent"}),

    # "帮我查XX" → 查询
    (re.compile(r"(?:帮我查|查一下|搜索)(.+)"),
     {"time_range": "today"}),
]

# 常见话题关键词映射
TOPIC_ALIASES: dict[str, str] = {
    "ai": "AI",
    "人工智能": "AI",
    "大模型": "AI",
    "半导体": "半导体",
    "芯片": "芯片",
    "金融": "金融科技",
    "政策": "政策",
    "股市": "市场",
    "股票": "市场",
    "区块链": "金融科技",
    "web3": "金融科技",
    "机器人": "科技",
    "新能源": "科技",
    "量子": "科技",
    "自动驾驶": "科技",
}


def normalize_topic(topic: str) -> str:
    """标准化话题名称。

    Args:
        topic: 原始话题词。

    Returns:
        标准化后的话题名称。
    """
    topic_lower = topic.strip().lower()
    return TOPIC_ALIASES.get(topic_lower, topic.strip())


def parse_query(text: str) -> ParsedIntent:
    """解析用户消息，提取意图。

    优先级: 结构化命令 > 自然语言模式 > 全文搜索。

    Args:
        text: 用户输入的文本。

    Returns:
        ParsedIntent 对象。
    """
    text = text.strip()
    intent = ParsedIntent(raw=text)

    # 1. 尝试匹配结构化命令
    for pattern, defaults in COMMAND_PATTERNS:
        match = pattern.match(text)
        if match:
            intent.mode = defaults.get("mode", "query")
            intent.time_range = defaults.get("time_range", "today")

            if intent.mode in ("query", "company"):
                topic_or_company = match.group(1).strip()
                if intent.mode == "company":
                    intent.company = topic_or_company
                    intent.topic = topic_or_company
                else:
                    intent.topic = normalize_topic(topic_or_company)

            logger.debug(f"匹配命令: mode={intent.mode}, topic={intent.topic}")
            return intent

    # 2. 尝试匹配自然语言模式
    for pattern, defaults in NL_PATTERNS:
        match = pattern.search(text)
        if match:
            intent.time_range = defaults.get("time_range", "today")
            topic = match.group(1).strip()
            intent.topic = normalize_topic(topic)
            intent.mode = "query"
            logger.debug(f"匹配NL: topic={intent.topic}")
            return intent

    # 3. 兜底: 将整段文本作为搜索关键词
    if len(text) > 2 and len(text) < 50:
        intent.topic = text
        intent.mode = "query"

    logger.debug(f"兜底解析: topic={intent.topic or '(无)'}")
    return intent


def is_config_command(text: str) -> bool:
    """判断是否为配置命令。

    Args:
        text: 用户输入。

    Returns:
        True 如果是配置相关命令。
    """
    config_patterns = [
        r"^(?:加关注|取消关注|我的关注|系统状态)",
        r"^(?:早间简报|午间简报|晚间简报).*(?:改到|暂停|恢复)",
        r"^我不想要\s+.+\s+的新闻",
        r"^添加.*信源",
    ]
    return any(re.search(p, text) for p in config_patterns)
