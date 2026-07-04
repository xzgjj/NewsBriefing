"""命令解析器单元测试。"""

from news_briefing.processor.command_parser import (
    parse_query,
    normalize_topic,
    is_config_command,
)


class TestNormalizeTopic:
    """话题标准化测试。"""

    def test_known_alias(self):
        assert normalize_topic("ai") == "AI"
        assert normalize_topic("人工智能") == "AI"
        assert normalize_topic("大模型") == "AI"

    def test_unknown_topic(self):
        assert normalize_topic("量子计算") == "量子计算"


class TestParseStructuredCommands:
    """结构化命令解析测试。"""

    def test_briefing_today(self):
        result = parse_query("/briefing today")
        assert result.mode == "full_briefing"
        assert result.time_range == "today"

    def test_briefing_topic(self):
        result = parse_query("/briefing topic 半导体")
        assert result.mode == "query"
        assert result.topic == "半导体"

    def test_briefing_company(self):
        result = parse_query("/briefing company NVIDIA")
        assert result.mode == "company"
        assert result.company == "NVIDIA"

    def test_add_watchlist(self):
        result = parse_query("加关注 OpenAI")
        assert result.mode == "add_watchlist"

    def test_remove_watchlist(self):
        result = parse_query("取消关注 OpenAI")
        assert result.mode == "remove_watchlist"

    def test_list_watchlist(self):
        result = parse_query("我的关注")
        assert result.mode == "list_watchlist"

    def test_system_status(self):
        result = parse_query("系统状态")
        assert result.mode == "system_status"


class TestParseNLQueries:
    """自然语言查询解析测试。"""

    def test_today_topic_query(self):
        result = parse_query("今天有什么关于半导体的新闻")
        assert result.mode == "query"
        assert result.topic == "半导体"

    def test_latest_news_query(self):
        result = parse_query("AI的最新消息")
        assert result.mode == "query"
        assert result.topic == "AI"

    def test_search_command(self):
        result = parse_query("帮我查OpenAI")
        assert result.mode == "query"
        assert "OpenAI" in result.topic

    def test_fallback_short_text(self):
        result = parse_query("半导体")
        assert result.mode == "query"
        assert result.topic == "半导体"

    def test_empty_no_crash(self):
        result = parse_query("")
        assert result.mode == "query"


class TestConfigCommands:
    """配置命令检测测试。"""

    def test_is_config_command(self):
        assert is_config_command("加关注 OpenAI")
        assert is_config_command("取消关注 OpenAI")
        assert is_config_command("我的关注")
        assert is_config_command("系统状态")

    def test_not_config_command(self):
        assert not is_config_command("今天有什么新闻")
        assert not is_config_command("半导体")
