# 潮目 Shiome

> Read the turning point before the data makes it obvious.
> 在数据显现之前，先读出趋势转折的那条分界线。

**Shiome** (潮目) is the boundary line where two ocean currents meet — where fish gather, and in Japanese, *shiome ga kawaru* (潮目が変わる) means "the tide turns." Shiome is a single-operator analytics tool for Douyin (抖音) creators: feed it your video metrics, and it runs several independent AI analyses to help you decide, earlier than raw numbers would tell you, whether a video is about to break into a higher traffic pool and whether your content direction needs to change.

It is deliberately a **runnable skeleton**, not a finished product — a base to keep iterating on with Claude Code.

---

## English

### Features

Five independent analysis dimensions, each its own prompt/module:

| Dimension | Module | What it answers |
|---|---|---|
| Enhancement direction | `analysis/enhancement.py` | Per-video editing suggestions |
| Content ideas | `analysis/content_ideas.py` | Account-level topic suggestions (looking forward) |
| Trend forecast | `analysis/trend_forecast.py` | Heuristic traffic-trend inference (**not** a platform prediction) |
| Pool diagnosis | `analysis/pool_diagnosis.py` | Which traffic-pool tier a video is in and what's blocking the next (needs snapshots) |
| Creator profile | `analysis/creator_profile.py` | An audit of what your content is actually doing (looking in the mirror) |

They run separately on purpose — each needs different input and judgment logic, and separating them lets you iterate on one without disturbing the others.

### Architecture

```
Creator-center CSV ──▶ Ingestion ──▶ SQLite ──▶ 5 analysis modules ──▶ Anthropic API
                                                        │
                                                        ▼
                                       FastAPI ──▶ local web dashboard
```

### Quick start

```bash
git clone git@github.com:Planetesimeow/Shiome.git
cd Shiome
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in your ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

Then open http://localhost:8000

**Configuration** (`.env`): `ANTHROPIC_API_KEY` is required; `ANALYSIS_MODEL` is an optional override for the model used.

### Getting data in

Douyin's creator center has no API, so:

1. **CSV import** (recommended) — Creator center → Data → Export, then upload it on the web page. `app/ingestion.py`'s `COLUMN_ALIASES` fuzzy-matches common headers; if an import can't find a column, add your file's header text to that dict.
2. **Manual entry** — the `POST /api/videos` endpoint accepts one record at a time (a web form for this is not built yet).

Two dimensions (pool diagnosis, creator profile) need extra manual data — time snapshots and content descriptions — enterable via the panel on the right of the dashboard, or the `POST /api/videos/{id}/snapshots` and `PATCH /api/videos/{id}/content-profile` endpoints.

### Project structure

```
app/
  main.py            FastAPI routes
  database.py        SQLite schema
  models.py          Pydantic request/response models
  ingestion.py       CSV import + fuzzy header matching
  analysis/          the five analysis modules + shared prompt helpers
  static/            frontend (vanilla HTML/JS + Chart.js, no build step)
```

### Status & roadmap

This is an early skeleton. Not yet built (contributions/iterations welcome): a web form for video entry, comment/DM intent grading, a maintainable content-risk keyword library, batch-import scripts, and authentication (**required before any remote deployment** — it currently runs with no login).

### Design rationale

The "why it's built this way" reasoning — separated analyses, honesty about trend forecasting, anomaly-period handling, the platform-mechanism reference framework, and future server/mobile plans — lives in **[MEMO.md](MEMO.md)**.

### Changelog

See **[CHANGELOG.md](CHANGELOG.md)** for version history.

### License

No license yet — until one is added, all rights are reserved and others have no legal right to reuse the code.

---

## 中文

### 功能

五个独立的分析维度，每个都是独立的 prompt/模块：

| 维度 | 模块 | 回答什么 |
|---|---|---|
| 增强方向 | `analysis/enhancement.py` | 单条视频的剪辑建议 |
| 内容建议 | `analysis/content_ideas.py` | 账号级选题建议（往前看） |
| 流量预估 | `analysis/trend_forecast.py` | 流量趋势启发式推断（**不是**平台预测） |
| 流量池定位 | `analysis/pool_diagnosis.py` | 视频在哪一级流量池、卡在哪、要过下一关做什么（需要快照） |
| 内容创作者画像 | `analysis/creator_profile.py` | 审计内容实际在做什么（照镜子看现状） |

它们刻意分开跑——各自需要的输入和判断逻辑不同，分开后可以单独迭代其中一个而不影响其他。

### 架构

```
创作者中心 CSV ──▶ 导入 ──▶ SQLite ──▶ 五个分析模块 ──▶ Anthropic API
                                              │
                                              ▼
                                 FastAPI ──▶ 本地网页 dashboard
```

### 快速开始

```bash
git clone git@github.com:Planetesimeow/Shiome.git
cd Shiome
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # 填入你的 ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

然后打开 http://localhost:8000

**配置**（`.env`）：`ANTHROPIC_API_KEY` 必填；`ANALYSIS_MODEL` 是可选的模型覆盖项。

### 数据怎么进来

抖音创作者中心没有 API，所以：

1. **CSV 导入**（推荐）——创作者中心 → 数据 → 导出，然后在网页上上传。`app/ingestion.py` 的 `COLUMN_ALIASES` 会对常见表头做模糊匹配；如果导入找不到某列，把你文件里的表头文字加进那个字典即可。
2. **手动录入**——`POST /api/videos` 接口一次收一条数据（对应的网页表单还没做）。

有两个维度（流量池定位、内容画像）需要额外的手动数据——时间快照和内容描述——可以在 dashboard 右侧面板录入，或用 `POST /api/videos/{id}/snapshots` 和 `PATCH /api/videos/{id}/content-profile` 接口。

### 目录结构

```
app/
  main.py            FastAPI 路由
  database.py        SQLite schema
  models.py          Pydantic 请求/响应模型
  ingestion.py       CSV 导入 + 表头模糊匹配
  analysis/          五个分析模块 + 公共 prompt 辅助
  static/            前端（原生 HTML/JS + Chart.js，无构建步骤）
```

### 现状 & 路线图

这是一个早期骨架。尚未实现（欢迎迭代/贡献）：视频录入的网页表单、评论/私信意向分级、可维护的内容风控关键词库、批量导入脚本，以及鉴权（**远程部署前必须补上**——目前无任何登录）。

### 设计思路

"为什么这么设计"的推理——分析为何分开、对流量预估的诚实说明、异常期处理、平台机制参考框架，以及未来服务器/手机端计划——都在 **[MEMO.md](MEMO.md)**。

### 更新记录

版本历史见 **[CHANGELOG.md](CHANGELOG.md)**。

### 许可

暂无许可证——在添加许可证之前，保留所有权利，他人没有合法权利复用本代码。
