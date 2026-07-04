"""语义去重 — 基于关键词加权 Jaccard 相似度的轻量语义去重。

不依赖 sentence-transformers（~1GB），使用改进的关键词 TF 加权方案，
对中文新闻场景效果足够（Phase 4，补充 SimHash 的不足）。
"""

import logging
from collections import Counter

from news_briefing.collector.models import NewsItem

logger = logging.getLogger(__name__)

# 语义相似度阈值（超过此值视为重复）
SEMANTIC_THRESHOLD = 0.80


def _tf_weighted_tokens(text: str) -> dict[str, float]:
    """提取 TF 加权的词袋特征。

    中文按 bigram 分词，计算词频权重。

    Args:
        text: 输入文本。

    Returns:
        {token: tf_weight} 字典。
    """
    # 提取 bigram 作为特征
    bigrams = [text[i:i + 2] for i in range(len(text) - 1)]
    if not bigrams:
        return {}

    # 计算词频
    counter = Counter(bigrams)
    total = len(bigrams)

    # TF 权重
    return {bg: count / total for bg, count in counter.items()}


def _cosine_similarity(
    vec_a: dict[str, float],
    vec_b: dict[str, float],
) -> float:
    """计算两个 TF 向量的余弦相似度。

    Args:
        vec_a: 向量 A。
        vec_b: 向量 B。

    Returns:
        余弦相似度 (0.0 ~ 1.0)。
    """
    if not vec_a or not vec_b:
        return 0.0

    # 公共 token
    common_tokens = set(vec_a) & set(vec_b)
    if not common_tokens:
        return 0.0

    # 点积
    dot_product = sum(vec_a[t] * vec_b[t] for t in common_tokens)

    # 模长
    norm_a = sum(v ** 2 for v in vec_a.values()) ** 0.5
    norm_b = sum(v ** 2 for v in vec_b.values()) ** 0.5

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def semantic_similarity(item_a: NewsItem, item_b: NewsItem) -> float:
    """计算两条新闻的语义相似度。

    综合标题和摘要的 TF-余弦相似度，标题权重 0.7，摘要权重 0.3。

    Args:
        item_a: 新闻 A。
        item_b: 新闻 B。

    Returns:
        语义相似度 (0.0 ~ 1.0)。
    """
    # 标题特征（权重 0.7）
    title_a = _tf_weighted_tokens(item_a.title)
    title_b = _tf_weighted_tokens(item_b.title)
    title_sim = _cosine_similarity(title_a, title_b)

    # 摘要特征（权重 0.3）
    snippet_a = item_a.content_snippet or ""
    snippet_b = item_b.content_snippet or ""
    snippet_a_vec = _tf_weighted_tokens(snippet_a)
    snippet_b_vec = _tf_weighted_tokens(snippet_b)
    snippet_sim = _cosine_similarity(snippet_a_vec, snippet_b_vec)

    # 如果都没有摘要，标题权重更高
    if not snippet_a or not snippet_b:
        return title_sim

    return title_sim * 0.7 + snippet_sim * 0.3


def semantic_deduplicate(
    items: list[NewsItem],
    threshold: float = SEMANTIC_THRESHOLD,
) -> tuple[list[NewsItem], int]:
    """对已通过 URL/SimHash 去重的新闻列表进行语义去重。

    这是去重的第三层补充，捕获前两层漏掉的语义重复。
    时间复杂度高（O(n²)），仅在 ≤ 200 条时运行。

    Args:
        items: 新闻列表。
        threshold: 相似度阈值。

    Returns:
        (去重后列表, 去重数量)。
    """
    if len(items) <= 1:
        return items, 0

    # 超过 200 条时跳过（性能考虑）
    if len(items) > 200:
        logger.info(f"语义去重跳过: {len(items)} 条超出阈值 (200)")
        return items, 0

    removed = 0
    result = []
    seen_indices: set[int] = set()

    for i, item_a in enumerate(items):
        if i in seen_indices:
            continue
        # 与后续条目比较
        for j in range(i + 1, len(items)):
            if j in seen_indices:
                continue
            item_b = items[j]
            sim = semantic_similarity(item_a, item_b)
            if sim >= threshold:
                seen_indices.add(j)
                removed += 1
                logger.debug(f"语义去重: '{item_a.title[:40]}...' ≈ '{item_b.title[:40]}...' (sim={sim:.3f})")
        result.append(item_a)

    if removed:
        logger.info(f"语义去重: 移除 {removed} 条")

    return result, removed
