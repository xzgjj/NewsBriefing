#!/usr/bin/env python3
"""NewsBriefing API 服务入口。

启动 FastAPI 服务，监听 localhost:18900。
提供简报生成、自然语言查询、配置管理、健康检查等 API。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import uvicorn
from news_briefing.api.routes import create_app
from news_briefing.log_config import setup_logging


def main() -> None:
    """启动 API 服务。"""
    setup_logging()

    app = create_app()

    print("=" * 60)
    print("  NewsBriefing API 服务")
    print("  http://localhost:18900")
    print("  API 文档: http://localhost:18900/docs")
    print("=" * 60)

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=18900,
        log_level="info",
    )


if __name__ == "__main__":
    main()
