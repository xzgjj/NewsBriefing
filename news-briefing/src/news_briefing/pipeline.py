"""主流水线 — 端到端简报生成流程。

是整个系统的核心编排逻辑，将 Collector → Dedup → Ranker →
Curator → Composer → Deliverer 串联起来。
"""

import logging
from datetime import datetime

from news_briefing.collector.collector import (
    collect_all,
    determine_degradation,
    flatten_items,
)
from news_briefing.collector.models import (
    Briefing,
    CuratedItem,
)
from news_briefing.composer.formatter import compose_briefing
from news_briefing.composer.sections import select_sections
from news_briefing.config import AppConfig
from news_briefing.deliverer.archive import save_to_archive
from news_briefing.deliverer.feishu_sender import deliver
from news_briefing.processor.curator import Curator
from news_briefing.processor.dedup import deduplicate
from news_briefing.processor.detoxifier import detoxify_batch
from news_briefing.processor.ranker import rank_items

logger = logging.getLogger(__name__)


async def generate_briefing(
    config: AppConfig,
    mode: str = "scheduled",
    output: str = "console",
) -> Briefing | None:
    """执行完整的简报生成流程。

    流程:
      1. 采集 → 2. 去重 → 3. 评分 → 4. 去毒化 →
      5. AI 策展 → 6. 板块选取 → 7. 组装 → 8. 投递 → 9. 归档

    Args:
        config: 应用配置。
        mode: 简报模式 (scheduled | manual)。
        output: 输出方式 (console | feishu)。

    Returns:
        Briefing 对象，失败返回 None。
    """
    start_time = datetime.now()

    # ============================================================
    # Step 1: 采集
    # ============================================================
    logger.info("=" * 60)
    logger.info(f"📥 Step 1/7: 开始采集新闻 (模式: {mode})")
    logger.info("=" * 60)

    fetch_results = await collect_all(config)

    if not fetch_results:
        logger.error("无任何信源可用，简报生成终止")
        return None

    all_items = flatten_items(fetch_results)
    total_raw = len(all_items)

    degradation_level, degradation_note = determine_degradation(fetch_results)

    if degradation_level >= 5:
        logger.critical(f"采集完全失败: {degradation_note}")
        # 仍然尝试生成空简报记录
        return None

    # ============================================================
    # Step 2: 去重
    # ============================================================
    logger.info(f"🔄 Step 2/7: 开始去重 ({total_raw} 条原始新闻)")

    dedup_result = deduplicate(all_items)
    unique_items = dedup_result.items

    # ============================================================
    # Step 3: 评分排序
    # ============================================================
    logger.info(f"📏 Step 3/7: 评分排序 ({len(unique_items)} 条)")

    ranked_items = rank_items(unique_items, config)

    # ============================================================
    # Step 4: 标题去毒化
    # ============================================================
    logger.info("🧹 Step 4/7: 标题去毒化")

    detoxify_batch(ranked_items)

    # ============================================================
    # Step 5: AI 策展
    # ============================================================
    logger.info("🧠 Step 5/7: AI 策展")

    # 取 Top 30 进行策展
    top_items = ranked_items[:30]

    curator = Curator(
        model=config.llm.get("fast_model", "deepseek-chat"),
    )

    try:
        curated_items = await curator.curate_batch(
            top_items,
            classify_all=True,
            summarize_all=True,
        )
    except Exception as e:
        logger.warning(f"LLM 策展失败 ({e})，使用规则分类 + 原标题模式")
        # 降级: 规则分类 + 无 AI 摘要
        curated_items = []
        for item in top_items:
            curated_items.append(CuratedItem(
                item=item,
                category=item.category,
                ai_summary=item.content_snippet,
                display_title=item.detoxed_title or item.title,
            ))
        degradation_level = max(degradation_level, 3)
        if not degradation_note:
            degradation_note = "⚠️ AI 摘要服务不可用，展示原始标题"

    # ============================================================
    # Step 6: 板块选取
    # ============================================================
    logger.info("✂️ Step 6/7: 板块选取")

    sections = select_sections(curated_items, config)

    # ============================================================
    # Step 7: 组装 + 投递
    # ============================================================
    logger.info("📝 Step 7/7: 组装简报并投递")

    briefing = compose_briefing(
        sections=sections,
        total_raw=total_raw,
        total_after_dedup=dedup_result.total_after,
        degradation_level=degradation_level,
        degradation_note=degradation_note,
        mode=mode,
    )

    # 投递
    if output == "feishu":
        delivery_result = await deliver(briefing)

        if delivery_result.success:
            logger.info(f"✅ 简报已通过 {delivery_result.channel} 投递")
        else:
            logger.error(f"❌ 投递失败: {delivery_result.error}")
            # 确保本地归档
            save_to_archive(briefing)

    # 始终输出到 console
    if True:
        print(briefing.markdown_text)

    # 本地归档
    save_to_archive(briefing)

    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info(f"✅ 简报生成完成 (耗时 {elapsed:.1f}s, "
                f"采集 {total_raw} → 去重后 {dedup_result.total_after} → "
                f"精选 {briefing.total_selected})")

    return briefing
