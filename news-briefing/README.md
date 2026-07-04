# 📰 NewsBriefing — 个人情报简报系统

<p align="center">
  <b>每天早上，像一位了解你、有专业判断力的研究助理那样，<br>把最重要的事告诉你。</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/tests-97%2F97-brightgreen.svg" alt="Tests">
  <img src="https://img.shields.io/badge/ruff-clean-success.svg" alt="Ruff">
</p>

---

## 项目简介

**NewsBriefing** 是一个单用户个人情报简报系统。每天早晨 08:00，系统自动从 9 个信源采集新闻，经过去重、评分、AI 策展后，生成结构化简报，通过**飞书卡片消息**推送到你的手机。

> 不是 RSS 聚合器。RSS 聚合器把 500 条新闻堆给你。NewsBriefing 只给你 20 条，但每一条都经过了"这条你会关心吗？这条可信吗？"的过滤。

### 设计原则

```
原则 1: 不误导 — 不确定的消息必须标注，标题不改写，信息可追溯到原始出处
原则 2: 信源分等 — Tier 1 权威媒体直接采用，Tier 3 强制标注"⚠️未经核实"
原则 3: 去情绪化 — 检测并过滤"暴涨""震惊""突发"等夸大标题
原则 4: 可追溯 — 每条新闻附带来源、时间、原文链接
```

### 简报效果预览

飞书卡片消息示例：

```
┌──────────────────────────────────────────┐
│ 📰 每日情报简报 — 2026年7月5日            │
├──────────────────────────────────────────┤
│                                          │
│ 🏛️ 政策大事 (2条)                        │
│                                          │
│ 1. 国务院发布AI产业发展若干意见           │
│    提出2027年自主可控算力占比超75%...      │
│    📎 新华社 | 07:32 | ✅ 多源证实        │
│                                          │
│ 2. 央行开展1000亿元MLF操作               │
│    中标利率2.50%持平，净投放...           │
│    📎 央行官网 | 09:15                   │
│                                          │
│ 💼 企业商业与供应链 (3条)                 │
│ 1. 阿里全面禁用Claude Code               │
│    因安全风险，7月10日起内部禁用...        │
│    📎 36氪 | 昨天 15:22                  │
│                                          │
│ 🤖 AI 前沿 (4条)                         │
│ 💰 金融与市场 (3条)                      │
│                                          │
│ 📊 上证3245(+0.8%) 恒生18457(+1.2%)      │
│ ──────────────────────────────────────── │
│ 基于 173 条采集 · 97 条去重 · 20 条精选   │
└──────────────────────────────────────────┘
```

---

## 核心功能

### 🚀 自动简报
- 每日 08:00（Asia/Shanghai）自动采集、策展、推送
- 支持突发新闻/市场异动触发午间快报
- 四板块：🏛️政策大事 · 🤖AI前沿 · 💼企业商业 · 💰金融与市场

### 🔍 按需查询
- 飞书对话："今天有什么关于半导体的新闻" → 专题简报
- 命令格式：`/briefing topic <主题>` `/briefing company <企业>`
- 自然语言理解 + 关键词规则兜底

### 🛡️ 反误导机制
- **标题去毒化**：检测"暴涨/震惊/突发"等情绪词，还原客观标题
- **信源分等**：Tier 1 权威媒体 → Tier 2 知名平台 → Tier 3 待核实
- **不确定标注**：推测性消息强制标注"⚠️ 未经核实"
- **AI 摘要安全约束**：不评价、不编造、不给投资建议

### 📊 内容策展
- **全文提取**：Jina Reader API 获取网页完整内容
- **AI 策展**：DeepSeek 进行新闻分类 + 编辑级摘要生成
- **多源融合**：同一事件多来源报道 → 一条综合摘要
- **四维评分**：信源权威性 × 时效性 × 用户相关性 × 信息增量

### 📱 飞书交互
- 追问："第三条详细说说" → 深度搜索
- 反馈："不感兴趣" → 偏好学习
- 配置："加关注 OpenAI" → 关注列表管理

---

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **语言** | Python 3.10+ | 异步 IO（asyncio + httpx） |
| **采集** | feedparser / BeautifulSoup4 / Tavily API / Jina Reader | RSS + HTML爬取 + 搜索 + 全文提取 |
| **AI/LLM** | DeepSeek API（兼容 OpenAI SDK） | 分类 + 编辑摘要 + 多源融合 |
| **数据库** | SQLite + SQLAlchemy ORM + Alembic | WAL 模式，单文件零配置 |
| **调度** | APScheduler | 进程内定时任务（08:00） |
| **API** | FastAPI + Uvicorn | RESTful API（localhost:18900） |
| **投递** | 飞书开放平台 API | IM 卡片消息直连 |
| **配置** | YAML + Pydantic 校验 | 类型安全的配置管理 |
| **测试** | pytest + pytest-asyncio + pytest-cov | 97 个测试用例 |
| **代码质量** | ruff | 零警告 |

---

## 快速开始

### 前置条件
- Python 3.10+
- [Tavily API Key](https://tavily.com)（搜索补充）
- [DeepSeek API Key](https://platform.deepseek.com)（AI 策展，可选）
- [飞书开放平台应用](https://open.feishu.cn)（消息推送）

### 安装

```bash
# 克隆仓库
git clone git@github.com:xzgjj/NewsBriefing.git
cd NewsBriefing/news-briefing

# 安装依赖
pip install -r requirements.txt

# 验证安装
python scripts/build_and_test.py
```

### 运行

```bash
# 终端模式（输出到控制台）—— 最常用
python main.py --mode scheduled --output console

# 飞书推送模式
python main.py --mode scheduled --output feishu

# 按需查询
python main.py --mode manual --query "今天有什么关于AI的新闻"

# 启动 API 服务（开发调试）
python server.py
# API 文档: http://localhost:18900/docs

# 启动定时任务（长期运行）
python main.py --mode serve
```

---

## 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `TAVILY_API_KEY` | 推荐 | Tavily 搜索 API Key（缺失时仅使用 RSS） |
| `DEEPSEEK_API_KEY` | 可选 | DeepSeek API Key（缺失时使用规则分类+原摘要） |
| `FEISHU_APP_ID` | 投递需要 | 飞书应用 ID |
| `FEISHU_APP_SECRET` | 投递需要 | 飞书应用 Secret |
| `FEISHU_RECEIVER_ID` | 投递需要 | 飞书用户 open_id |

> 如果安装了 OpenClaw，系统会自动从 `~/.openclaw/openclaw.json` 读取飞书凭证，无需手动设置环境变量。

---

## 项目结构

```
news-briefing/
│
├── main.py                          # CLI 入口
├── server.py                        # FastAPI 服务入口
├── config.yaml                      # 信源/话题/关注/投递配置
├── requirements.txt                 # Python 依赖
├── ruff.toml                        # 代码规范配置
│
├── src/news_briefing/               # 主包
│   │
│   ├── collector/                   # 采集层 ─── 从信源拉取新闻
│   │   ├── models.py                #   核心数据模型（Pydantic）
│   │   ├── collector.py             #   采集编排器（4层爬取优先）
│   │   ├── rss_fetcher.py           #   RSS feedparser 采集
│   │   ├── web_search.py            #   Tavily 搜索采集
│   │   ├── scraper.py               #   HTML BeautifulSoup 爬取
│   │   └── extractor.py             #   Jina Reader 全文提取
│   │
│   ├── processor/                   # 处理层 ─── 去重/排序/策展
│   │   ├── dedup.py                 #   三层去重(URL+Jaccard+SimHash)
│   │   ├── semantic_dedup.py        #   语义去重(TF-余弦相似度)
│   │   ├── ranker.py                #   四维评分系统
│   │   ├── detoxifier.py            #   标题去毒化
│   │   ├── curator.py               #   AI策展(DeepSeek分类+摘要)
│   │   ├── fusion.py                #   多源融合(跨源综合摘要)
│   │   ├── digest_handler.py        #   摘要栏目展开(9点1氪等)
│   │   ├── command_parser.py        #   飞书命令解析
│   │   └── feedback.py              #   用户反馈权重调整
│   │
│   ├── composer/                    # 组装层 ─── 简报结构与格式化
│   │   ├── sections.py              #   分类优先+配额保障板块选取
│   │   ├── formatter.py             #   Markdown + 飞书卡片生成
│   │   └── templates.py             #   简报模板(详细/精简)
│   │
│   ├── deliverer/                   # 投递层 ─── 飞书推送+归档
│   │   ├── feishu_sender.py         #   飞书开放平台直连
│   │   └── archive.py               #   本地 Markdown 归档
│   │
│   ├── api/                         # API 层 ─── RESTful 接口
│   │   ├── schemas.py               #   请求/响应模型
│   │   ├── routes.py                #   12个API端点
│   │   └── interaction.py           #   追问/反馈/配置交互
│   │
│   ├── scheduler/                   # 调度层
│   │   └── jobs.py                  #   APScheduler 08:00定时
│   │
│   ├── db/                          # 数据层
│   │   ├── database.py              #   SQLite WAL 初始化
│   │   └── models.py                #   SQLAlchemy ORM（5表）
│   │
│   ├── pipeline.py                  # 主流水线编排
│   ├── config.py                    # YAML+Pydantic 配置加载
│   ├── monitor.py                   # 信源健康+Tavily额度+跨期去重
│   └── log_config.py                # 统一日志
│
├── tests/                           # 测试（97个用例）
│   ├── unit/                        #   单元测试（92个）
│   └── integration/                 #   集成测试（5个）
│
├── scripts/
│   └── build_and_test.py            # 构建验证脚本
│
├── data/archive/                    # 简报归档（Markdown）
└── logs/                            # 运行日志
```

---

## 使用说明

### 配置信源

编辑 `config.yaml` 的 `sources` 部分：

```yaml
sources:
  tier1:                    # 权威媒体 — 标题保留原样
    - name: "中国政策(Tavily)"
      type: "web_search"
      url: "国务院 部委 政策文件 通知 法规 监管 最新"
      timeout: 15
      enabled: true
      category: "policy"

  tier2:                    # 知名平台 — 标题可去情绪化
    - name: "36氪"
      type: "rss"
      url: "https://36kr.com/feed"
      timeout: 15
      enabled: true
      category: "business"
```

### 管理关注列表

```yaml
watchlist:
  - name: "OpenAI"
    keywords: ["OpenAI", "GPT", "ChatGPT", "Sam Altman"]
    priority: 9
  - name: "NVIDIA"
    ticker: "NVDA"
    keywords: ["NVIDIA", "英伟达", "GPU", "黄仁勋"]
    priority: 8
```

### 自定义简报时间

```yaml
schedule:
  timezone: "Asia/Shanghai"
  briefings:
    morning:
      enabled: true
      time: "08:00"
    midday:
      enabled: false
      time: "12:30"
      trigger: "anomaly_only"   # 仅重大事件时发送
```

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/health` | 健康检查 |
| `POST` | `/api/v1/briefing/generate` | 生成简报 |
| `POST` | `/api/v1/query/nl` | 自然语言查询 |
| `GET` | `/api/v1/watchlist` | 查看关注列表 |
| `POST` | `/api/v1/watchlist` | 添加关注 |
| `DELETE` | `/api/v1/watchlist/{id}` | 移除关注 |
| `POST` | `/api/v1/feedback` | 用户反馈 |
| `POST` | `/api/v1/interact/followup` | 追问详情 |
| `POST` | `/api/v1/interact/config` | 对话式配置 |
| `GET` | `/api/v1/config/status` | 系统状态 |

---

## 架构设计

```
                        ┌──────────────────────────┐
                        │     飞书卡片消息          │
                        │   (用户手机/PC 飞书)       │
                        └────────────┬─────────────┘
                                     │
                        ┌────────────▼─────────────┐
                        │   飞书开放平台 API        │
                        │   im/v1/messages          │
                        └────────────┬─────────────┘
                                     │
┌───────────────────────────────────▼───────────────────────────────┐
│                     NewsBriefing Service                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────────────┐    │
│  │Scheduler │  │  API     │  │ Config (YAML + Pydantic)     │    │
│  │(APS 08:00│  │(FastAPI) │  │ 信源/话题/关注/投递           │    │
│  └────┬─────┘  └────┬─────┘  └──────────────────────────────┘    │
│       │              │                                            │
│       └──────┬───────┘                                            │
│              ▼                                                    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                  Pipeline Orchestrator                     │    │
│  │                                                            │    │
│  │  📥 Collector ──→ 🔄 Dedup ──→ 📏 Ranker                  │    │
│  │  (9信源并发)      (3层去重)     (4维评分)                   │    │
│  │       │               │              │                      │    │
│  │       ▼               ▼              ▼                      │    │
│  │  🧠 Curator ────→ ✂️ Sections ──→ 📝 Composer             │    │
│  │  (AI分类+摘要)     (配额保障)       (Markdown+卡片)         │    │
│  │       │                                              │      │    │
│  │       ▼                                              │      │    │
│  │  📨 Deliverer ──→ 📁 Archive                         │      │    │
│  │  (飞书直连)        (Markdown持久化)                    │      │    │
│  └──────────────────────────────────────────────────────────┘    │
│              │                                                    │
│  ┌───────────┼────────────────────────────┐                      │
│  │  SQLite   │  Markdown Archive          │                      │
│  │  (WAL)    │  data/archive/             │                      │
│  └───────────┴────────────────────────────┘                      │
└──────────────────────┬───────────────────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
    ┌──────────┐ ┌──────────┐ ┌──────────┐
    │ 9个RSS源 │ │  Tavily  │ │   Jina   │
    │ 36氪/钛媒│ │  Search  │ │  Reader  │
    │ 体/爱范儿│ │   API    │ │   API    │
    │ /IT之家  │ │          │ │  (全文)  │
    └──────────┘ └──────────┘ └──────────┘
```

### 采集策略：爬取优先 4 层架构

```
Layer 1 (主力)      RSS Feed + HTML 直接爬取    → 36氪/钛媒体/爱范儿/IT之家/品玩
                    无 API 额度限制，高频采集

Layer 2 (补充)      Tavily Search API           → 政策/金融/AI/商业四路搜索
                    填补 RSS 未覆盖的重要新闻

Layer 3 (备用)      Google News RSS             → Tavily 额度耗尽时启用
                    (待实现)

Layer 4 (兜底)      用户告知                     → 所有采集手段不可用时
                    "⚠️ 今日所有采集手段均失败"
```

### 数据处理流水线

```
采集 (Collect)
  ├─ 9 个信源并发请求，单源失败不阻塞
  ├─ 时效验证：>7天直接丢弃，无时间标记降权
  └─ 产 ~150-300 条原始条目
      │
      ▼
去重 (Dedup)
  ├─ Layer A: URL SHA256 精确去重
  ├─ Layer B: 标题 Jaccard 相似度（>0.85）
  ├─ Layer C: SimHash 64-bit（汉明距离<3）
  ├─ 跨期去重：对比昨日简报过滤已推送
  └─ 语义去重：TF-余弦相似度（>0.80）
      │
      ▼
质量过滤 (Quality Filter)
  ├─ 域名黑名单：YouTube/Zhihu/Bilibili/Weibo
  ├─ 标题模式：解释性文章("什么是..."/"一文看懂")
  └─ 产 ~80-200 条独立事件
      │
      ▼
评分排序 (Rank)
  score = 信源权威 × 时效衰减 × 关键词匹配 × 交叉验证 × 用户相关 × 100
      │
      ▼
全文提取 (Extract)
  └─ Jina Reader API：URL → 干净 Markdown（≤5并发，失败降级）
      │
      ▼
AI 策展 (Curate)
  ├─ 分类：DeepSeek 规则 + LLM 双重分类
  ├─ 多源融合：同事件报道合并为一条编辑摘要
  └─ 摘要：选中条目生成编辑级摘要
      │
      ▼
板块选取 (Select)
  ├─ 分类优先 + 配额保障（每类 min~max）
  └─ 产 15-25 条精选
      │
      ▼
组装投递 (Compose & Deliver)
  ├─ Markdown 格式化 + 飞书卡片 JSON
  ├─ 飞书直连 API → 手机飞书
  └─ 本地归档（兜底）
```

---

## 当前水平与局限

### 已验证的能力
- ✅ 端到端管道：173条/次采集量，5-30秒完成全流程
- ✅ 飞书投递：通过飞书开放平台 API 直接推送卡片消息
- ✅ 降级策略：LLM不可用 → 规则分类；Tavily不可用 → RSS纯采集
- ✅ 97 个测试用例全部通过，ruff 零警告
- ✅ 支持 9 个信源（5 RSS + 4 Tavily 搜索）

### 已知局限
| 局限 | 影响 | 计划 |
|------|------|------|
| Tavily 搜索精度 | 返回索引页/英文聚合页而非中文新闻 | 接入专业新闻 API（NewsAPI/Bing News） |
| AI 摘要质量 | 全文含导航栏噪音，LLM 摘要偶有偏差 | 改进正文提取 + prompt 迭代 |
| 36氪"9点1氪" | 摘要汇总栏目的子条目未独立搜索 | 子话题提取后发起补充搜索 |
| 飞书交互 | 仅支持单向推送，追问/反馈需手动处理 | WebSocket 双向消息接入 |
| 市场数据 | 未集成 A 股/美股行情 | 接入 AKShare/yfinance |

---

## 后续演进规划

### Phase B: 内容质量
- [ ] 接入 NewsAPI / Bing News Search 提升搜索精度
- [ ] 改进 Jina Reader 正文提取（过滤导航/侧栏/推荐）
- [ ] LLM 摘要质量评估 + 自动优化

### Phase C: 交互增强
- [ ] WebSocket 双向飞书消息（追问/反馈实时响应）
- [ ] 偏好学习闭环（用户反馈 → 权重调整）
- [ ] 简报个性化模板（详细版/精简版/日报/周报）

### Phase D: 智能扩展
- [ ] 市场异动检测（AKShare A股 + yfinance 美股）
- [ ] 午间快报（市场异动 + 突发新闻自动触发）
- [ ] 关注企业的零新闻异动告警
- [ ] 多用户支持

---

## 部署说明

### 本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 运行（终端模式）
python main.py --mode scheduled --output console

# 运行（飞书推送）
python main.py --mode scheduled --output feishu
```

### 长期运行

```bash
# 方式1: 直接启动 API 服务（含定时任务）
python server.py

# 方式2: 使用 nohup (Linux/Mac)
nohup python server.py > logs/server.log 2>&1 &

# 方式3: Windows 开机自启
# 将 gateway.vbs 或快捷方式放入 shell:startup
```

### Docker（计划中）

```dockerfile
# 待实现
FROM python:3.10-slim
COPY . /app
RUN pip install -r requirements.txt
CMD ["python", "server.py"]
```

---

## License

MIT License © 2026 NewsBriefing

---

<p align="center">
  <sub>不误导 · 可追溯 · 分信源等级 · 去情绪化</sub>
</p>
