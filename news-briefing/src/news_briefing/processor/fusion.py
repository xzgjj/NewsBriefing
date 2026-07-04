"""多源融合器 — 将同一事件的多篇报道合并为一条编辑级摘要。

策略:
  1. 按标题Jaccard相似度分组（阈值0.6）
  2. 每组选Tier最高者为代表
  3. 将组内所有报道的全文/snippet拼接
  4. 由LLM生成一条融合摘要
"""

import logging

from news_briefing.collector.models import NewsItem, SourceTier
from news_briefing.processor.dedup import _jaccard_similarity, _tokenize_title

logger = logging.getLogger(__name__)

FUSION_SIMILARITY_THRESHOLD = 0.55  # 低于去重阈值，更宽松


def group_by_topic(items: list[NewsItem]) -> list[list[NewsItem]]:
    """按话题相似度将新闻分组。

    使用标题Jaccard相似度，阈值0.55（宽松匹配）。

    Args:
        items: 新闻条目列表。

    Returns:
        分组列表，每组是相关新闻的列表。孤立的条目独自成组。
    """
    if len(items) <= 1:
        return [[i] for i in items]

    groups: list[list[NewsItem]] = []
    assigned: set[int] = set()

    for i, item_a in enumerate(items):
        if i in assigned:
            continue
        group = [item_a]
        assigned.add(i)
        tokens_a = _tokenize_title(item_a.title)

        for j in range(i + 1, len(items)):
            if j in assigned:
                continue
            item_b = items[j]
            tokens_b = _tokenize_title(item_b.title)
            sim = _jaccard_similarity(tokens_a, tokens_b)

            if sim >= FUSION_SIMILARITY_THRESHOLD:
                group.append(item_b)
                assigned.add(j)

        groups.append(group)

    # 统计
    fused_groups = [g for g in groups if len(g) >= 2]
    if fused_groups:
        total = sum(len(g) for g in fused_groups)
        logger.info(f"多源融合: {len(fused_groups)} 组可合并 ({total} 条新闻)")

    return groups


def select_representative(group: list[NewsItem]) -> NewsItem:
    """从一组相关新闻中选择代表条目。

    优先级: Tier1 > 摘要最长 > 分数最高。

    Args:
        group: 同一事件的新闻组。

    Returns:
        代表条目。
    """
    if len(group) == 1:
        return group[0]

    # 1. 选Tier最高者
    tier1 = [i for i in group if i.source_tier == SourceTier.TIER_1]
    candidates = tier1 or group

    # 2. 选摘要最长者
    return max(candidates, key=lambda x: len(x.content_snippet or ""))


def build_fusion_context(group: list[NewsItem]) -> str:
    """构建多源融合的LLM上下文。

    将组内所有报道的标题+来源+内容拼接。

    Args:
        group: 同一事件的新闻组。

    Returns:
        格式化的上下文文本。
    """
    parts = []
    for i, item in enumerate(group, 1):
        parts.append(
            f"---来源{i}: {item.source_name} (Tier{item.source_tier.value})---\n"
            f"标题: {item.title}\n"
            f"内容: {item.content_snippet or '(无)'}\n"
        )
    return "\n".join(parts)


FUSION_SUMMARY_PROMPT = """你是资深新闻编辑。以下多条报道来自不同来源，描述同一事件。
请综合所有来源的信息，写一条准确的融合摘要。

规则：
- 优先采用Tier1来源的事实
- 如果不同来源的数字有冲突，注明"来源A称X，来源B称Y"
- 保留精确数字、时间、百分比
- 不评价、不预测、不用情绪词
- 100字以内

{context}

融合摘要："""


async def fuse_group(
    group: list[NewsItem],
    curator=None,
) -> str:
    """对一组相关新闻生成融合摘要。

    Args:
        group: 同一事件的新闻组。
        curator: Curator实例（用于LLM调用）。None时降级。

    Returns:
        融合摘要文本。单条新闻返回其原始摘要。
    """
    if len(group) == 1:
        return group[0].ai_summary or group[0].content_snippet or ""

    if curator is None or not curator.available:
        # 降级: 拼接各来源摘要
        parts = []
        for item in group[:3]:
            src = item.source_name
            summary = item.ai_summary or item.content_snippet or ""
            parts.append(f"据{src}: {summary[:100]}")
        return " | ".join(parts)

    try:
        context = build_fusion_context(group)
        prompt = FUSION_SUMMARY_PROMPT.replace("{context}", context)

        response = await curator.client.chat.completions.create(
            model=curator.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.2,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.warning(f"融合摘要LLM失败: {e}")
        # 降级
        rep = select_representative(group)
        return rep.ai_summary or rep.content_snippet or ""
