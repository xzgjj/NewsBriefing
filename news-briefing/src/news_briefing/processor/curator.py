"""AI 策展器 — 分类、摘要、安全约束。

使用 DeepSeek API 进行:
  1. 新闻分类（policy/fintech/ai/tech/watchlist/general）
  2. AI 摘要生成（遵守 6 条安全约束）
  3. 降级：LLM 不可用时使用关键词规则兜底
"""

import logging
import os

from openai import AsyncOpenAI

from news_briefing.collector.models import CuratedItem, NewsItem

logger = logging.getLogger(__name__)

# ============================================================
# LLM Prompt 模板
# ============================================================

CLASSIFY_PROMPT = """你是一个新闻分类助手。将新闻分类到以下类别。

类别:
- policy: 政策法规、政府公告、监管动态、国务院/部委文件
- business: 企业动态、商业合作、供应链、投资并购、人事变动
- fintech: 金融市场、银行证券、支付清算、数字货币、保险
- ai: AI大模型、人工智能、深度学习、算法突破
- watchlist: 与关注企业直接相关
- general: 其他

只回复类别名称。

标题: {title}
内容: {snippet}
类别:"""

SUMMARY_PROMPT = """你是资深新闻编辑。从下方正文中提取核心事实，写一条简报条目。

⚠️ 正文可能含导航栏、侧边栏、"Most Read"推荐等噪音。
**只关注真正的文章内容**，忽略导航和推荐链接。

格式：
第一行：**一句话标题**（说清事件+涉及方，≤25字）
第二行起：关键事实（精确数字、时间、金额、百分比。宁可不写也不编造）

禁止：
- 复制正文中的导航栏/侧边栏/推荐链接
- 使用"据悉""据报道"等废话开头
- 评价（"利好""利空""重要"）
- 预测
- 情绪化词汇

━━━
标题：{title}
来源：{source}
正文片段：{snippet}
━━━

编辑摘要："""

FALLBACK_CLASSIFY_KEYWORDS = {
    "policy": ["国务院", "央行", "证监会", "发改委", "财政部", "政策", "监管",
               "法规", "政治局", "货币政策", "财政", "通知", "意见", "办法"],
    "business": ["融资", "上市", "IPO", "收购", "并购", "投资", "供应链",
                 "代工", "订单", "合作", "人事", "裁员", "营收", "利润",
                 "阿里", "腾讯", "字节", "美团", "京东", "拼多多"],
    "fintech": ["金融科技", "支付", "区块链", "数字货币", "量化", "FinTech",
                "银行", "证券", "保险", "基金", "利率", "LPR", "MLF",
                "股市", "A股", "港股", "美股", "涨", "跌", "板块"],
    "ai": ["AI", "大模型", "GPT", "Claude", "DeepSeek", "Gemini", "Llama",
           "推理", "训练", "Agent", "多模态", "Transformer", "算力",
           "GPU", "开源模型", "benchmark", "基准测试", "机器学习"],
}


def _fallback_classify(title: str, snippet: str | None = None) -> str:
    """关键词规则兜底分类。

    Args:
        title: 新闻标题。
        snippet: 内容摘要。

    Returns:
        分类标签。
    """
    text = title
    if snippet:
        text += " " + snippet

    scores: dict[str, int] = {}
    for category, keywords in FALLBACK_CLASSIFY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in text.lower())
        if score > 0:
            scores[category] = score

    if not scores:
        return "general"

    return max(scores, key=lambda k: scores[k])


class Curator:
    """AI 策展器。

    封装 DeepSeek API 调用，提供分类和摘要功能。
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        timeout: float = 30.0,
    ):
        """初始化策展器。

        Args:
            api_key: DeepSeek API Key。None 从环境变量读取。
            model: 模型名称。
            base_url: API 基础 URL。
            timeout: API 超时（秒）。
        """
        if api_key is None:
            api_key = os.environ.get("DEEPSEEK_API_KEY", "")

        self.api_key = api_key
        self.model = model
        self.available = bool(api_key)

        if self.available:
            self.client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
            )
        else:
            self.client = None
            logger.warning("DeepSeek API Key 未设置，将使用规则兜底模式")

    async def classify(self, item: NewsItem) -> str:
        """对新闻进行分类。

        Args:
            item: 新闻条目。

        Returns:
            分类标签。
        """
        if not self.available or self.client is None:
            return _fallback_classify(item.title, item.content_snippet)

        try:
            # 用 replace 而非 format，避免全文中的 {} 导致 KeyError
            prompt = (CLASSIFY_PROMPT
                      .replace("{title}", item.title)
                      .replace("{snippet}", item.content_snippet or "(无内容摘要)"))

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=20,
                temperature=0.1,
            )

            category = response.choices[0].message.content.strip().lower()
            # 验证分类有效性
            valid_categories = {"policy", "business", "fintech", "ai", "watchlist", "general"}
            if category not in valid_categories:
                logger.debug(f"LLM 返回无效分类 '{category}'，回退到规则分类")
                return _fallback_classify(item.title, item.content_snippet)

            return category

        except Exception as e:
            logger.warning(f"LLM 分类失败: {e}，使用规则兜底")
            return _fallback_classify(item.title, item.content_snippet)

    async def summarize(self, item: NewsItem) -> str:
        """生成 AI 摘要。

        Args:
            item: 新闻条目。

        Returns:
            AI 生成的摘要（最多 150 字）。
        """
        if not self.available or self.client is None:
            # 降级: 使用原文片段
            return item.content_snippet or "暂无摘要"

        try:
            # 用 replace 而非 format，避免全文中的 {} 导致 KeyError
            prompt = (SUMMARY_PROMPT
                      .replace("{title}", item.title)
                      .replace("{source}", item.source_name)
                      .replace("{snippet}", item.content_snippet or "(无内容摘要)"))

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.3,
            )

            summary = response.choices[0].message.content.strip()

            # 安全约束: 检测是否有情绪化词汇
            sensational = ["暴涨", "暴跌", "震惊", "重磅", "炸裂"]
            for word in sensational:
                if word in summary:
                    logger.warning(f"LLM 摘要含情绪词 '{word}'，将重新生成")
                    # 简单清理
                    summary = summary.replace(word, "")

            return summary[:300]  # 限制长度

        except Exception as e:
            logger.warning(f"LLM 摘要失败: {e}，使用原文片段")
            return item.content_snippet or "暂无摘要"

    async def curate_batch(
        self,
        items: list[NewsItem],
        classify_all: bool = True,
        summarize_all: bool = True,
    ) -> list[CuratedItem]:
        """批量策展新闻条目。

        对每条新闻执行分类 + 摘要。

        Args:
            items: 新闻条目列表。
            classify_all: 是否对所有条目进行分类。
            summarize_all: 是否对所有条目生成摘要。

        Returns:
            策展后的条目列表。
        """
        curated: list[CuratedItem] = []

        for item in items:
            category = item.category
            ai_summary = item.ai_summary

            # 分类
            if classify_all and category == "general":
                category = await self.classify(item)
                item.category = category

            # 摘要
            if summarize_all and not ai_summary:
                ai_summary = await self.summarize(item)
                item.ai_summary = ai_summary

            curated_item = CuratedItem(
                item=item,
                category=category,
                ai_summary=ai_summary,
                display_title=item.detoxed_title or item.title,
            )
            curated.append(curated_item)

        logger.info(f"AI 策展完成: {len(curated)} 条")
        return curated

    async def classify_batch(self, items: list[NewsItem]) -> None:
        """仅批量分类（修改原对象）。

        Args:
            items: 新闻条目列表（原地修改）。
        """
        for item in items:
            if item.category == "general":
                item.category = await self.classify(item)

    async def summarize_batch(self, items: list[NewsItem]) -> None:
        """仅批量摘要（修改原对象）。

        Args:
            items: 新闻条目列表（原地修改）。
        """
        for item in items:
            if not item.ai_summary:
                item.ai_summary = await self.summarize(item)
