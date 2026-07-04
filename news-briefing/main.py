#!/usr/bin/env python3
"""NewsBriefing CLI 入口。

用法:
  python main.py --mode scheduled --output console
  python main.py --mode scheduled --output feishu
  python main.py --mode manual --query "AI 新闻"
"""

import argparse
import asyncio
import sys
from pathlib import Path

# 将 src 目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from news_briefing.log_config import setup_logging
from news_briefing.config import load_config
from news_briefing.pipeline import generate_briefing


async def main_async(args: argparse.Namespace) -> None:
    """异步主函数。"""
    # 初始化日志
    setup_logging()

    # 加载配置
    config_path = args.config
    if config_path:
        config = load_config(Path(config_path))
    else:
        config = load_config()

    if args.mode == "scheduled":
        # 定时模式: 立即生成一次简报
        print("=" * 60)
        print("  NewsBriefing — 个人情报简报系统")
        print("=" * 60)

        briefing = await generate_briefing(
            config=config,
            mode="scheduled",
            output=args.output,
        )

        if briefing is None:
            print("❌ 简报生成失败，请检查日志")
            sys.exit(1)
        else:
            print(f"\n✅ 简报生成成功! 共 {briefing.total_selected} 条精选")

    elif args.mode == "manual":
        # 按需查询模式
        from news_briefing.processor.command_parser import parse_query

        query = args.query or "今天有什么重要新闻"
        print(f"🔍 查询: {query}")

        parsed = parse_query(query)
        print(f"   解析: topic={parsed.topic or '(全览)'}, time={parsed.time_range}")

        # 生成完整简报然后按话题过滤
        briefing = await generate_briefing(
            config=config,
            mode="manual",
            output=args.output,
        )

        if briefing is None:
            print("❌ 简报生成失败，请检查日志")
            sys.exit(1)
        else:
            print(f"\n✅ 查询完成! 共 {briefing.total_selected} 条精选")

    elif args.mode == "serve":
        # API 服务模式
        from news_briefing.api.routes import create_app
        import uvicorn

        print("=" * 60)
        print("  NewsBriefing API 服务")
        print("  http://localhost:18900")
        print("  API 文档: http://localhost:18900/docs")
        print("=" * 60)

        app = create_app()
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=18900,
            log_level="info",
        )


def main() -> None:
    """CLI 入口。"""
    parser = argparse.ArgumentParser(
        description="NewsBriefing — 个人情报简报系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py --mode scheduled --output console   # 终端模式
  python main.py --mode scheduled --output feishu    # 飞书推送
  python main.py --mode manual --query "AI 新闻"     # 按需查询
        """,
    )

    parser.add_argument(
        "--mode", "-m",
        choices=["scheduled", "manual", "serve"],
        default="scheduled",
        help="运行模式 (默认: scheduled)",
    )
    parser.add_argument(
        "--output", "-o",
        choices=["console", "feishu"],
        default="console",
        help="输出方式 (默认: console)",
    )
    parser.add_argument(
        "--query", "-q",
        type=str,
        help="按需查询的关键词 (仅 manual 模式)",
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        help="配置文件路径 (默认自动搜索)",
    )

    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
