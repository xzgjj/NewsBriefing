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
    NewsItem,
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

    # 跨期去重：过滤昨日已推送的新闻
    from news_briefing.monitor import filter_cross_period_duplicates, load_yesterday_titles
    yesterday_titles = load_yesterday_titles()
    if yesterday_titles:
        unique_items, cross_removed = filter_cross_period_duplicates(
            unique_items, yesterday_titles
        )
        if cross_removed:
            logger.info(f"跨期去重: 移除 {cross_removed} 条昨日已推送新闻")

    # 语义去重：补充 SimHash 的不足
    if len(unique_items) <= 200:
        from news_briefing.processor.semantic_dedup import semantic_deduplicate
        unique_items, sem_removed = semantic_deduplicate(unique_items)
        if sem_removed:
            logger.info(f"语义去重: 移除 {sem_removed} 条")

    # 摘要栏目处理：标记"9点1氪"等汇总类条目
    from news_briefing.processor.digest_handler import process_digests
    unique_items = process_digests(unique_items)

    # 内容质量过滤：移除低质量来源（YouTube/知乎/广告等）
    from news_briefing.collector.extractor import filter_quality
    unique_items, q_removed = filter_quality(unique_items)
    if q_removed:
        logger.info(f"质量过滤: 移除 {q_removed} 条低质量内容")

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
    # Step 4.5: 全文提取（核心质量提升 — Jina Reader获取完整文章）
    # ============================================================
    # 对排名前50的候选条目提取全文（降级：失败则保留原始snippet）
    enrich_pool = ranked_items[:50] if len(ranked_items) >= 50 else ranked_items
    try:
        from news_briefing.collector.extractor import enrich_items
        enriched_count = await enrich_items(enrich_pool, max_concurrent=5)
        logger.info(f"📖 全文提取: {enriched_count}/{len(enrich_pool)} 条成功")
    except Exception as e:
        logger.warning(f"全文提取失败(非致命): {e}")

    # ============================================================
    # Step 5: AI 策展 (分类优先 — 先分类全部候选，按板块选取后再摘要)
    # ============================================================
    logger.info("🧠 Step 5/7: AI 策展")

    # 分类更多条目确保每个板块都有候选 (至少80条)
    curation_pool = ranked_items[:80] if len(ranked_items) >= 80 else ranked_items

    curator = Curator(
        model=config.llm.get("fast_model", "deepseek-chat"),
    )

    try:
        # 先分类全部候选
        await curator.classify_batch(curation_pool)
        logger.info(f"分类完成: {len(curation_pool)} 条")
    except Exception as e:
        logger.warning(f"LLM 分类失败 ({e})，使用规则兜底")

    # 多源融合：将同一事件的报道合并，生成融合摘要
    try:
        from news_briefing.processor.fusion import fuse_group, group_by_topic, select_representative
        groups = group_by_topic(curation_pool)
        fused_items = []
        for group in groups:
            rep = select_representative(group)
            if len(group) >= 2:
                # 多源报道 → 生成融合摘要
                fused_summary = await fuse_group(group, curator)
                rep.ai_summary = fused_summary
                rep.cross_validated_by = list(set(
                    s.source_name for s in group if s.source_name != rep.source_name
                ))
                logger.debug(f"融合: '{rep.title[:40]}...' ({len(group)}源)")
            fused_items.append(rep)
        curation_pool = fused_items
        logger.info(f"多源融合: {len(groups)} 组 → {len(fused_items)} 条")
    except Exception as e:
        logger.warning(f"多源融合失败(非致命): {e}")

    # 构建 CuratedItem 列表
    curated_items = []
    for item in curation_pool:
        curated_items.append(CuratedItem(
            item=item,
            category=item.category,
            ai_summary=None,  # 延迟摘要
            display_title=item.detoxed_title or item.title,
        ))

    # 板块选取（先分类再选取，确保每类有配额）
    logger.info("✂️ Step 6/7: 板块选取 (分类优先)")
    sections = select_sections(curated_items, config)

    # 收集被选中的条目
    selected_items: list[NewsItem] = []
    for section in sections:
        for curated in section.items:
            selected_items.append(curated.item)

    # 只对选中的条目生成摘要
    logger.info(f"生成摘要: {len(selected_items)} 条选中条目")
    try:
        await curator.summarize_batch(selected_items)
    except Exception as e:
        logger.warning(f"LLM 摘要失败 ({e})，使用原始内容")
        degradation_level = max(degradation_level, 3)
        if not degradation_note:
            degradation_note = "⚠️ AI 摘要服务不可用，展示原始标题"

    # 更新 CuratedItem 的摘要（用于展示）
    for curated in curated_items:
        if curated.item.ai_summary:
            curated.ai_summary = curated.item.ai_summary

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
