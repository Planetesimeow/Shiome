# 潮目 Shiome — Design Notes / 设计备忘

> These are the original design-rationale notes (the "why it's built this way" reasoning).
> For getting started and usage, see [README.md](README.md).
>
> 这是最初的设计思路备忘（"为什么这么设计"的推理记录）。
> 上手和使用说明请看 [README.md](README.md)。

---

## English

**On the name.** *Shiome* (潮目) is the boundary line formed where two ocean currents meet; fishermen rely on it to judge where fish gather. In Japanese, *shiome ga kawaru* (潮目が変わる) is commonly used to describe the moment a trend turns. This tool does exactly that — reading, *before* the data makes it obvious, the dividing line that tells you whether a traffic pool is about to level up, or whether your content direction needs adjusting.

A small one-person tool: enter video metrics → independent analysis dimensions (enhancement / content ideas / trend forecast, plus two more) → a local web page to view results. It is deliberately built as a **runnable skeleton** rather than a finished product; the intended next step is to keep iterating on this base with Claude Code.

### Architecture

```
Creator-center CSV export ──▶ Ingestion (app/ingestion.py) ──▶ SQLite (app/database.py)
                                                        │
                                          ┌─────────────┼─────────────┐
                                          ▼             ▼             ▼
                                     Enhancement   Content ideas   Trend forecast
                                  (analysis/enhancement)(content_ideas)(trend_forecast)
                                          │             │             │
                                          └────── calls the Anthropic API ──────┘
                                                        │
                                                        ▼
                                       FastAPI (app/main.py) ──▶ local web dashboard
```

**Why three analyses run separately instead of one big prompt.** Per-video editing suggestions, account-level topic suggestions, and traffic-trend inference each need different input data and different judgment logic. Mixing them into one prompt makes them interfere with each other and the prompt grows messy. Kept separate, you can also iterate on the quality of one kind of analysis without touching the other two.

**An honest note on "trend forecast."** Douyin does not expose its recommendation-algorithm data, so a true "platform prediction" is impossible here. What `trend_forecast.py` does is a *heuristic* inference based on the account's historical push patterns, and the prompt forces it to carry a confidence level and a disclaimer. Do not treat it as a confident prediction.

### Quick start

```bash
cd douyin-analytics
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

Open http://localhost:8000

### How data comes in

Douyin's creator center has no API, so there are two routes:

1. **CSV import** (recommended): Creator center → Data → Export, then upload it in the top-left of the web page. The `COLUMN_ALIASES` dict in `app/ingestion.py` does fuzzy matching on common column headers; if an import fails saying a column can't be found, just add your actual export file's header text into that dict.
2. **Manual entry**: OCR-transcribing screenshot data is not recommended — for numbers that drive decisions, better to confirm once by hand. In the skeleton, the `POST /api/videos` endpoint already accepts a single record, but the web form isn't built yet — this is a piece Claude Code can fill in next.

### Handling anomaly periods

`POST /api/anomaly-periods` records a date range and a reason (e.g. "new account IP + geo-tag triggered throttling"). Videos falling inside the range are marked `is_anomaly_period=1`; all analysis modules automatically exclude these videos when computing baselines, so the overall judgment isn't dragged down by anomaly-period data. On the trend chart, these points are highlighted with red triangles rather than disappearing — keeping them visible so you can review them yourself.

### Platform-mechanism reference framework

`app/analysis/prompts.py` contains a `PLATFORM_MECHANISM_CONTEXT` block that writes the empirical patterns of Douyin/Xiaohongshu recommendation mechanisms (traffic-pool tiers, throttling curve vs. natural-decay curve, account-tag drift, etc.) into a reference framework; both `enhancement.py` and `trend_forecast.py` carry this block.

What was deliberately *not* done: the specific numbers inside it (e.g. "45% completion rate", "3.5% like ratio") are not used as hard criteria for comparison, because those are empirical values for the mass-entertainment market — applying them directly would conflict with this account's goal of "precise reach > broad growth". The current usage lets the model recognize which pattern a curve's *shape* resembles, rather than scoring against a pass line.

Also deliberately not added: time-series snapshots (how much at 1 hour / 24 hours / 3 days after publishing). This is the key data that would let "trend forecast" truly align with the "climb speed" logic in the platform mechanism, but the cost is you'd have to periodically check the numbers in the creator center by hand. Right now `trend_forecast.py`'s prompt honestly tells the model: "you only have terminal-state data, no time-series curve, so you can only make rough inferences" — it doesn't pretend to see the hourly curve after publishing. If you later want more accurate trend judgment, this is the first-priority data to add; when you add it, create a `video_snapshots(video_id, checked_at, plays, likes, comments, saves)` table separate from the `videos` table.

### Traffic-pool diagnosis & creator profile

Two dimensions added on top of the original three:

**Pool diagnosis** (`pool_diagnosis.py`): judges roughly which traffic-pool tier a video is currently in, which metric it's stuck on, and what editing changes it needs to clear that tier. It requires `video_snapshots` time snapshots as a precondition — judging "which tier, how fast the climb" inherently needs a curve; terminal numbers can't answer this. Snapshots rely on you checking the creator center by hand at fixed points (e.g. 1 hour, 24 hours, 3 days after publishing) and recording a snapshot on the web page. When there are fewer than 2 snapshots, the analysis honestly states low confidence rather than fabricating a definite judgment.

**Creator profile** (`creator_profile.py`): doesn't look at playback data — it looks at the content itself: what direction the recent batch of videos is actually pursuing, recurring hook patterns, text/BGM style, and whether the content-matrix structure is healthy (the ratio of trust-building content vs. conversion-triggering content). This is an account-level audit, with a division of labor different from `content_ideas.py`: content_ideas answers "what new content should I make next" (looking forward), creator_profile answers "what am I actually doing now" (looking in the mirror at the status quo).

Both need extra manual data:
- Pool diagnosis needs snapshots — the "Content profile & snapshot recording" panel on the right side of the web page has a small form; fill in plays/likes/comments/saves/completion rate and click "Record snapshot".
- Creator profile needs content-description fields (content summary, on-screen text, BGM, core hook, content-direction tag) — the same panel has a form; on save it's written into the corresponding fields of the `videos` table.

If the forms are too much trouble, you can also maintain a markdown doc yourself and batch-import via the `PATCH /api/videos/{id}/content-profile` and `POST /api/videos/{id}/snapshots` endpoints — `ingestion.py` currently only handles the creator-center CSV; this batch-import script isn't written yet and can be filled in with Claude Code.

### On the future: hosting on a server + mobile remote entry

Right now this skeleton is a local single-machine version: single-file SQLite, no auth, no multi-user isolation. If you later want to put it on a server so a phone can remotely send images/commands for the backend to record, at minimum these pieces need adding, none done yet:
- Auth (even the simplest API-token check — it can't run naked on the public internet).
- An image recognition/parsing pipeline — a phone sends a screenshot, and there must be a step that turns the screenshot into structured data stored into the `videos` or `video_snapshots` table. This might be Claude's vision capability, or you confirming manually before persisting — depends on how much human verification you want.
- An entry point that can receive the "image + command" message form. The current web form defaults to synchronous operation; the async "send it over, backend processes, check later" mode needs a task queue or at least a status field (processing / done / needs confirmation).

Hold off building this until the local setup runs smoothly and the data model is stable — otherwise changes still go through the check-data path, and hooking up the mobile side later may need another round of adjustment.

### Not done in this skeleton, but worth prioritizing

- **Comment/DM intent grading**: right now `high_intent_comments` / `high_intent_dms` are two number fields you count and fill in yourself. A better approach is to store the raw comment text too and let Claude classify and tag it by intent strength — this could become a fourth analysis module.
- **Content-risk keyword library**: `content_ideas.py` already has the model watch for risky phrasing around assets/identity/large-purchase, but that's only a prompt-level reminder, not a maintainable sensitive-word library that actively scans published content.
- **Video-entry form**: currently manual entry is API-only, no web form.
- **CSV header mapping**: the creator-center export format may change over time; `COLUMN_ALIASES` needs you to verify it against your own actual export file.
- **Auth**: currently it runs purely locally with no login. If you ever deploy it somewhere remotely accessible, this is mandatory.

### Directory structure

```
app/
  main.py              FastAPI routes
  database.py          SQLite schema
  models.py            Pydantic request/response models
  ingestion.py         CSV import + fuzzy header matching
  analysis/
    prompts.py         account-persona context, baseline calc, shared Claude-calling helper
    enhancement.py     dimension 1: per-video enhancement direction
    content_ideas.py   dimension 2: account-level content topic suggestions
    trend_forecast.py  dimension 3: heuristic traffic-trend inference
  static/              frontend (vanilla HTML/JS + Chart.js, no build step, easy to edit directly)
```

---

## 中文（原始设计备忘）

「潮目」指两股海流交汇形成的分界线，渔民靠它判断鱼群聚集点；日语里也常用"潮目が変わる"形容趋势转折的那一刻。这套工具做的就是这件事——在数据还没明显之前，先读出流量池要不要晋级、内容方向要不要调的那条分界线。

一个人跑的小工具：录入视频数据 → 三个独立的分析维度（增强方向 / 内容建议 / 流量预估）→ 一个本地网页看结果。设计上刻意做成"能跑起来的骨架"而不是成品，接下来建议用 Claude Code 继续在这个基础上迭代。

### 架构

```
创作者中心导出 CSV ──▶ 导入 (app/ingestion.py) ──▶ SQLite (app/database.py)
                                                        │
                                          ┌─────────────┼─────────────┐
                                          ▼             ▼             ▼
                                    增强方向分析     内容建议分析    流量预估分析
                                  (analysis/enhancement) (content_ideas) (trend_forecast)
                                          │             │             │
                                          └──────调用 Anthropic API────┘
                                                        │
                                                        ▼
                                          FastAPI (app/main.py) ──▶ 本地网页 dashboard
```

**为什么三个分析分开跑而不是一个大 prompt**：单条视频的剪辑建议、账号级的选题建议、流量趋势推断，需要的输入数据和判断逻辑都不一样，混在一起容易互相干扰、prompt 也会越写越乱。分开之后你也可以单独迭代某一类分析的效果，不用改动其他两个。

**关于"流量预估"要老实说清楚的一点**：抖音不对外开放推荐算法数据，这里做不到真正意义上的"平台预测"。`trend_forecast.py` 里做的是基于账号历史推流规律的启发式推断，prompt 强制要求带置信度和免责说明。别把它当成有把握的预测来用。

### 快速开始

```bash
cd douyin-analytics
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 填入你的 ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

打开 http://localhost:8000

### 数据怎么进来

抖音创作者中心没有 API，两条路：

1. **CSV 导入**（推荐）：创作者中心 → 数据 → 导出，然后在网页左上角上传。`app/ingestion.py` 里的 `COLUMN_ALIASES` 做了常见表头的模糊匹配，如果导入报错说找不到列，去那个字典里加上你实际导出文件的表头文字就行。
2. **手动录入**：截图数据不建议做 OCR 转录——涉及决策的数字，宁可手动确认一次。骨架里 `POST /api/videos` 这个接口已经能收单条数据，网页表单还没做，这是接下来可以让 Claude Code 补的一块。

### 异常期怎么处理

`POST /api/anomaly-periods` 记录一段日期区间和原因（比如"新号 IP+地理标签触发限流"）。落在区间内的视频会被标记 `is_anomaly_period=1`，三个分析模块计算基线时都会自动排除这些视频，不会被异常期的数据拉低整体判断。趋势图上这些点会用红色三角高亮，而不是直接从图上消失——保留可见性，方便你自己复核。

### 平台机制参考框架

`app/analysis/prompts.py` 里有一段 `PLATFORM_MECHANISM_CONTEXT`，把抖音/小红书推荐机制的经验规律（流量池分级、限流曲线 vs 自然衰减曲线的区别、账号标签漂移等）写成了参考框架，`enhancement.py` 和 `trend_forecast.py` 都会带上这段。

刻意没做的事：没把里面的具体数字（比如"45%完播率""3.5%点赞比"）当成硬性判据去对比，因为这些是泛娱乐大盘的经验值，直接套用会跟这个账号"精准触达 > 泛量增长"的目标冲突。现在的用法是让模型识别曲线"形状像哪种模式"，不是用来打分及格线。

也刻意没加时间序列快照（发布后1小时/24小时/3天分别是多少）——这是能让"流量趋势预估"真正对齐平台机制里"爬升速度"逻辑的关键数据，但代价是你得定时手动去创作者中心查数字。现在 `trend_forecast.py` 的 prompt 里已经如实告诉模型："你只有终态数据，没有时序曲线，只能做粗略推断"，不会假装自己看得到发布后每小时的曲线。如果之后想要更准的趋势判断，这个是第一优先该加的数据，加的时候要在 `videos` 表之外新建一张 `video_snapshots(video_id, checked_at, plays, likes, comments, saves)` 表。

### 流量池定位 & 内容创作者画像

在原来三个分析维度上加了两个：

**流量池定位** (`pool_diagnosis.py`)：判断这条视频现在大概在哪一级流量池、卡在哪个指标、要过这一关该做什么剪辑改动。前提是要有 `video_snapshots` 时间快照——判断"在哪一级、爬升速度怎么样"天生需要看曲线，终态数字回答不了这个问题。快照要靠你自己在固定时间点（比如发布后1小时、24小时、3天）手动查一次创作者中心，在网页里"记录一次快照"。快照数量不足2个时，分析会如实说置信度低，不会硬造一个确定的判断。

**内容创作者画像** (`creator_profile.py`)：不看播放数据，看的是内容本身——最近这批视频实际在做什么方向、反复用的钩子模式、文字/配乐风格，以及内容矩阵结构是否健康（信任建立类 vs 转化触发类内容的比例）。这是账号级的审计，跟 `content_ideas.py` 分工不同：content_ideas 回答"接下来该做什么新内容"（往前看），creator_profile 回答"现在实际在做什么"（照镜子看现状）。

这两个都需要额外的手动数据：
- 流量池定位需要快照，网页右侧"内容画像 & 快照记录"里有个小表单，填播放/点赞/评论/收藏/完播率，点一下"记录快照"就行
- 创作者画像需要内容描述字段（内容简述、画面文字、配乐、核心抓人点、内容方向标签），同一个面板里也有表单，保存后会存进 `videos` 表对应字段

如果表单太麻烦，也可以自己维护一份 md 文档手动填，再通过 `PATCH /api/videos/{id}/content-profile` 和 `POST /api/videos/{id}/snapshots` 这两个接口批量导入——`ingestion.py` 现在只处理了创作者中心的 CSV，这块批量导入脚本还没写，可以用 Claude Code 接着补。

### 关于以后要挂服务器 + 手机远程录入

现在这个骨架是本地单机版：SQLite 单文件、没有鉴权、没有多用户隔离。如果以后要把它放到服务器上，让手机远程发图片/指令过去后台记录，至少要补这几块，都还没做：
- 鉴权（哪怕最简单的一个 API token 校验也行，不能裸奔在公网上）
- 图片识别/解析这条链路——手机发截图过去，要有个环节把截图变成结构化数据存进 `videos` 或 `video_snapshots` 表，这可能是 Claude 的 vision 能力，也可能是你自己确认后再落库，看你要多少人工校验环节
- 一个能接收"图片 + 指令"这种消息形态的入口，现在的网页表单默认是同步操作，异步的"发过去、后台处理、之后来看"这种模式需要一个任务队列或者至少一个状态字段（处理中/已完成/需要确认）

这块先不建，等本地这套跑顺了、数据模型稳定了再动，不然现在改还是走查数据的路径，到时候接入手机端可能还要再调整一轮。

### 目前这个骨架没做、但值得优先补的

- **评论/私信意向分级**：现在 `high_intent_comments` / `high_intent_dms` 是两个数字字段，靠你自己数出来填。更好的做法是把评论原文也存进来，让 Claude 帮你按意向强度分类打标——这个可以做成第四个分析模块。
- **内容风控关键词库**：`content_ideas.py` 里已经让模型注意资产/身份/大额消费这类措辞风险，但只是 prompt 层面的提醒，没有一个可维护的敏感词库去主动扫描已发布内容。
- **视频录入表单**：目前手动录入只有 API，没有网页表单。
- **CSV 表头映射**：创作者中心导出格式过一段时间可能会变，`COLUMN_ALIASES` 需要你根据自己实际导出的文件核对一遍。
- **鉴权**：现在是纯本地跑，没做登录。如果以后要部署到能远程访问的地方，这个必须补上。

### 目录结构

```
app/
  main.py              FastAPI 路由
  database.py          SQLite schema
  models.py            Pydantic 请求/响应模型
  ingestion.py         CSV 导入 + 表头模糊匹配
  analysis/
    prompts.py         账号人设上下文、基线计算、调用 Claude 的公共方法
    enhancement.py      维度一：单条视频增强方向
    content_ideas.py    维度二：账号级内容选题建议
    trend_forecast.py   维度三：流量趋势启发式推断
  static/              前端（原生 HTML/JS + Chart.js，没有构建步骤，方便直接改）
```
