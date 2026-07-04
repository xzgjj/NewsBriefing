"""配置加载模块。

从 config.yaml 加载配置，使用 Pydantic 进行校验。
所有密钥从环境变量读取，禁止硬编码。
"""

import os
import logging
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


# ============================================================
# Pydantic 配置模型
# ============================================================

class ScheduleConfig(BaseModel):
    timezone: str = "Asia/Shanghai"
    enabled: bool = True
    time: str = "08:00"
    label: str = "早间简报"


class TopicConfig(BaseModel):
    enabled: bool = True
    label: str = ""
    keywords: list[str] = Field(default_factory=list)
    min_items: int = 1
    max_items: int = 10


class WatchlistItem(BaseModel):
    name: str
    ticker: Optional[str] = None
    market: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    priority: int = 5


class SourceConfig(BaseModel):
    name: str
    type: str  # rss | web_search | scrape
    url: str
    timeout: int = 15
    enabled: bool = True
    category: str = "general"
    selector: Optional[str] = None  # CSS selector for scraping


class SearchConfig(BaseModel):
    primary: str = "tavily"
    fallback_chain: list[str] = Field(default_factory=lambda: ["google_news_rss"])
    daily_limit: int = 15
    topics: dict = Field(default_factory=dict)


class LLMConfig(BaseModel):
    provider: str = "deepseek"
    fast_model: str = "deepseek-chat"
    pro_model: str = "deepseek-chat"
    timeout: int = 30
    fallback: str = "rule_based"
    safety_prompt_append: str = ""


class DeliveryConfig(BaseModel):
    primary: dict = Field(default_factory=dict)
    fallback: dict = Field(default_factory=dict)
    retry: dict = Field(default_factory=lambda: {"max_attempts": 3, "backoff_seconds": [60, 120, 240]})
    archive: dict = Field(default_factory=lambda: {"enabled": True, "path": "./data/archive/", "format": "markdown"})


class AntiMisinfoConfig(BaseModel):
    detoxify_titles: bool = True
    sensational_keywords: list[str] = Field(default_factory=list)
    uncertainty_markers: list[str] = Field(default_factory=list)
    require_cross_validation_for: list[str] = Field(default_factory=list)


class AppConfig(BaseModel):
    """应用配置总模型。"""
    version: str = "1.0"
    user_id: str = "single_user"
    schedule: dict = Field(default_factory=dict)
    topics: dict = Field(default_factory=dict)
    watchlist: list[dict] = Field(default_factory=list)
    sources: dict = Field(default_factory=dict)
    search: dict = Field(default_factory=dict)
    llm: dict = Field(default_factory=dict)
    delivery: dict = Field(default_factory=dict)
    anti_misinfo: dict = Field(default_factory=dict)


# ============================================================
# 配置加载函数
# ============================================================

def _find_config_path() -> Path:
    """查找配置文件路径。"""
    # 优先从环境变量读取
    env_path = os.environ.get("NEWS_BRIEFING_CONFIG")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    # 按优先级搜索
    search_paths = [
        Path("config.yaml"),
        Path("../config.yaml"),
        Path.home() / ".news-briefing" / "config.yaml",
    ]
    for p in search_paths:
        if p.exists():
            return p

    raise FileNotFoundError(
        "找不到 config.yaml。请将配置文件放在以下位置之一: "
        "config.yaml, ../config.yaml, ~/.news-briefing/config.yaml"
    )


def load_config(config_path: Optional[Path] = None) -> AppConfig:
    """加载并校验配置文件。

    Args:
        config_path: 配置文件路径。为 None 时自动搜索。

    Returns:
        校验后的 AppConfig 对象。

    Raises:
        FileNotFoundError: 找不到配置文件。
        ValidationError: 配置校验失败。
    """
    if config_path is None:
        config_path = _find_config_path()

    logger.info(f"加载配置: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    try:
        config = AppConfig(**raw)
        logger.info("配置校验通过")
        return config
    except ValidationError as e:
        logger.error(f"配置校验失败: {e}")
        raise

    return config


# ============================================================
# 环境变量读取
# ============================================================

def get_api_key(name: str) -> str:
    """从环境变量安全读取 API Key。

    Args:
        name: 环境变量名。

    Returns:
        API Key 字符串。

    Raises:
        ValueError: 环境变量未设置。
    """
    key = os.environ.get(name)
    if not key:
        raise ValueError(
            f"环境变量 {name} 未设置。请设置后重试。\n"
            f"示例: export {name}=your_key_here"
        )
    return key


def get_tavily_api_key() -> str:
    """获取 Tavily API Key。"""
    return get_api_key("TAVILY_API_KEY")


def get_deepseek_api_key() -> str:
    """获取 DeepSeek API Key。"""
    return get_api_key("DEEPSEEK_API_KEY")
