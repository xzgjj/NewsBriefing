"""本地归档 — 简报 Markdown 文件持久化。

所有简报都归档到 data/archive/ 目录，确保数据不丢失。
"""

import logging
from pathlib import Path

from news_briefing.collector.models import Briefing

logger = logging.getLogger(__name__)

DEFAULT_ARCHIVE_DIR = "data/archive"


def save_to_archive(
    briefing: Briefing,
    archive_dir: str = DEFAULT_ARCHIVE_DIR,
) -> str:
    """将简报保存为 Markdown 文件。

    Args:
        briefing: 简报对象。
        archive_dir: 归档目录。

    Returns:
        保存的文件路径。
    """
    archive_path = Path(archive_dir)
    archive_path.mkdir(parents=True, exist_ok=True)

    filename = f"{briefing.date}.md"
    filepath = archive_path / filename

    markdown = briefing.markdown_text
    if not markdown:
        from news_briefing.composer.formatter import format_markdown
        markdown = format_markdown(briefing)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(markdown)

    logger.info(f"简报已归档: {filepath}")
    return str(filepath)


def get_latest_archive(
    archive_dir: str = DEFAULT_ARCHIVE_DIR,
) -> str | None:
    """获取最近一次归档的简报内容。

    Args:
        archive_dir: 归档目录。

    Returns:
        Markdown 内容，如果没有归档则返回 None。
    """
    archive_path = Path(archive_dir)
    if not archive_path.exists():
        return None

    files = sorted(archive_path.glob("*.md"), reverse=True)
    if not files:
        return None

    with open(files[0], "r", encoding="utf-8") as f:
        content = f.read()

    return content


def list_archives(
    archive_dir: str = DEFAULT_ARCHIVE_DIR,
    limit: int = 30,
) -> list[str]:
    """列出最近的归档文件。

    Args:
        archive_dir: 归档目录。
        limit: 最大返回数。

    Returns:
        归档文件名列表（按日期降序）。
    """
    archive_path = Path(archive_dir)
    if not archive_path.exists():
        return []

    files = sorted(archive_path.glob("*.md"), reverse=True)
    return [f.name for f in files[:limit]]
