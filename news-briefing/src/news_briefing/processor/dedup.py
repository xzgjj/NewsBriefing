"""多层去重器。

三层去重策略:
  Layer A: URL SHA256 精确去重 — 完全相同的 URL
  Layer B: 标题 Jaccard 相似度 — 标题高度相似的不同 URL
  Layer C: SimHash 64-bit — 内容指纹相似度（汉明距离）

运行模式: 同步 CPU 操作，在 run_in_executor 中执行。
"""

import logging
import re
from dataclasses import dataclass, field

from news_briefing.collector.models import NewsItem

logger = logging.getLogger(__name__)

# Jaccard 相似度阈值（超过此值视为重复）
JACCARD_THRESHOLD = 0.85
# SimHash 汉明距离阈值（低于此值视为重复）
SIMHASH_DISTANCE_THRESHOLD = 3


@dataclass
class DedupResult:
    """去重结果。"""
    items: list[NewsItem] = field(default_factory=list)
    url_dups: int = 0
    title_dups: int = 0
    simhash_dups: int = 0
    total_before: int = 0
    total_after: int = 0


def _tokenize_title(title: str) -> set[str]:
    """将标题分词为 unigram/bigram 集合。

    中文按字切分，英文按空格切分。

    Args:
        title: 新闻标题。

    Returns:
        分词集合。
    """
    # 简单的混合分词: 中文按字，英文保留单词
    tokens: set[str] = set()

    # 提取中文字符（按字切分）
    chinese_chars = re.findall(r"[一-鿿]", title)
    tokens.update(chinese_chars)

    # 提取英文单词和数字（按空格/标点切分）
    english_words = re.findall(r"[a-zA-Z0-9]+", title)
    tokens.update(w.lower() for w in english_words)

    return tokens


def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """计算两个集合的 Jaccard 相似度。

    Args:
        set_a: 集合 A。
        set_b: 集合 B。

    Returns:
        相似度 (0.0 ~ 1.0)。
    """
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def _simhash(text: str) -> int:
    """计算文本的 64-bit SimHash。

    使用 n-gram 特征向量提高短文本的区分度。
    对中文文本用 bigram 和 trigram，避免单字 Unicode 码点分布过密导致误判。

    Args:
        text: 输入文本。

    Returns:
        64-bit SimHash 值。
    """
    # 特征向量: 64 个桶的权重
    weights = [0] * 64

    # 提取 n-gram 特征
    ngrams: list[str] = []

    # unigram: 单字符
    ngrams.extend(text)

    # bigram: 连续两字符
    for i in range(len(text) - 1):
        ngrams.append(text[i:i + 2])

    # trigram: 连续三字符（对短文本可跳过）
    if len(text) >= 3:
        for i in range(len(text) - 2):
            ngrams.append(text[i:i + 3])

    # 每个 n-gram 作为特征，用 hash 分布到 64 位
    for ngram in ngrams:
        feature_hash = hash(ngram)
        for i in range(64):
            if feature_hash & (1 << i):
                weights[i] += 1
            else:
                weights[i] -= 1

    # 正权重位设为 1
    result = 0
    for i in range(64):
        if weights[i] > 0:
            result |= (1 << i)

    return result


def _hamming_distance(hash_a: int, hash_b: int) -> int:
    """计算两个整数的汉明距离。

    Args:
        hash_a: 哈希值 A。
        hash_b: 哈希值 B。

    Returns:
        不同位的数量。
    """
    xor = hash_a ^ hash_b
    return xor.bit_count()


def _select_best_item(
    existing: NewsItem, candidate: NewsItem
) -> NewsItem:
    """当两条新闻重复时，选择更优的一条保留。

    优先级: 更高 Tier > 更早发布时间 > 更丰富的摘要。

    Args:
        existing: 已保留的条目。
        candidate: 新发现的重复条目。

    Returns:
        选中的条目。
    """
    # Tier 高的优先
    if candidate.source_tier.value < existing.source_tier.value:
        return candidate

    # 同 Tier 下，补充交叉验证信息
    if candidate.source_tier == existing.source_tier:
        combined = existing.model_copy()
        if candidate.source_name not in combined.cross_validated_by:
            combined.cross_validated_by.append(candidate.source_name)
        # 如果候选的摘要更丰富，使用候选的
        if (candidate.content_snippet and
                (not existing.content_snippet or
                 len(candidate.content_snippet) > len(existing.content_snippet))):
            combined.content_snippet = candidate.content_snippet
        return combined

    return existing


def deduplicate(items: list[NewsItem]) -> DedupResult:
    """对新闻列表执行三层去重。

    Args:
        items: 待去重的新闻条目列表。

    Returns:
        DedupResult，包含去重后的条目和统计信息。
    """
    total_before = len(items)

    if not items:
        return DedupResult(total_before=0, total_after=0)

    result = DedupResult(total_before=total_before)

    # Layer A: URL 精确去重
    seen_urls: dict[str, NewsItem] = {}
    for item in items:
        url_hash = item.url_hash or item.url
        if url_hash in seen_urls:
            # 保留更好的版本
            seen_urls[url_hash] = _select_best_item(seen_urls[url_hash], item)
            result.url_dups += 1
        else:
            seen_urls[url_hash] = item
    unique_by_url = list(seen_urls.values())
    logger.debug(f"URL 去重: {total_before} → {len(unique_by_url)} (移除 {result.url_dups})")

    # Layer B: 标题 Jaccard 相似度去重
    unique_by_title: list[NewsItem] = []
    title_tokens_cache: list[set[str]] = []

    for item in unique_by_url:
        tokens = _tokenize_title(item.title)
        is_dup = False

        for i, existing_tokens in enumerate(title_tokens_cache):
            sim = _jaccard_similarity(tokens, existing_tokens)
            if sim >= JACCARD_THRESHOLD:
                # 找到重复，选择更好的保留
                unique_by_title[i] = _select_best_item(unique_by_title[i], item)
                result.title_dups += 1
                is_dup = True
                break

        if not is_dup:
            unique_by_title.append(item)
            title_tokens_cache.append(tokens)

    logger.debug(
        f"标题去重: {len(unique_by_url)} → {len(unique_by_title)} "
        f"(移除 {result.title_dups})"
    )

    # Layer C: SimHash 去重
    # 为每条新闻计算 SimHash
    for item in unique_by_title:
        if item.simhash == 0:
            text = item.title + (item.content_snippet or "")
            item.simhash = _simhash(text)

    unique_final: list[NewsItem] = []
    for item in unique_by_title:
        is_dup = False
        for existing in unique_final:
            dist = _hamming_distance(item.simhash, existing.simhash)
            if dist <= SIMHASH_DISTANCE_THRESHOLD:
                result.simhash_dups += 1
                is_dup = True
                break
        if not is_dup:
            unique_final.append(item)

    logger.debug(
        f"SimHash 去重: {len(unique_by_title)} → {len(unique_final)} "
        f"(移除 {result.simhash_dups})"
    )

    result.items = unique_final
    result.total_after = len(unique_final)

    logger.info(
        f"去重完成: {result.total_before} → {result.total_after} "
        f"(URL: {result.url_dups}, Title: {result.title_dups}, "
        f"SimHash: {result.simhash_dups})"
    )

    return result
