# Changelog / 更新记录

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/).

本项目所有重要变更都记录在此。
格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## English

### [Unreleased]

**Added**
- Vision ingest: upload creator-center screenshots (phone or PC — layout-agnostic) →
  Claude vision extracts a draft → confirm/edit in the dashboard → saved through the
  same upsert path as CSV. 私密 (private) videos are flagged and refused server-side.
- Per-video detail-page fields the exports never had: 完播率, 2s跳出率, 弹幕, 封面点击率,
  涨粉/取关, 粉丝转化 — new nullable columns on `videos`/`video_snapshots`.
- New `account_metrics` table for account-level pages (主页访问, 净增粉/取关, 账号完播率,
  作品搜索, 同行百分位) + `GET /api/account-metrics`.
- Detail-page hourly trend chart is read *qualitatively* (shape description + pattern
  guess) and stored as `curve_note` on vision snapshots; 扩散诊断 uses it as corroborating
  eyewitness alongside numeric snapshots.
- Capture protocol guide: `docs/capture-guide.md` (per-video +24h/+3d; weekly list +
  account shots; no folder sorting needed).
- Delete button on each video row (removes its snapshots and analyses too, with confirm).
- Pluggable vision provider: `VISION_PROVIDER`/`VISION_MODEL` env decouple screenshot
  extraction from the analysis model — Anthropic (default now `claude-sonnet-4-6`,
  upgraded from Haiku) or Gemini (`gemini-3.5-flash` via `GEMINI_API_KEY`).
- Standalone dark-theme HTML account report (`GET /api/report`, `?download=1`), rendered
  from cached analyses only — no new API cost.
- Dashboard: hero landing with logo/stats/actions, per-video metrics vs baseline,
  diffusion-curve chart from snapshots, logo/favicon branding.
- Data-driven API smoke test (`tests/`) with JSON + CSV fixtures.
- Daily SQLite backup on first launch of the day (`app/data/backups/`, keeps 10) —
  protects hand-entered snapshots/profiles from cloud-sync corruption.
- Per-analysis cost visibility: token usage + duration stored and shown on result cards.

**Changed**
- Replaced the Douyin "traffic-pool tier" model with diffusion-curve analysis
  (pool_diagnosis → curve shape / diffusion stage / throttle-vs-decay); added the
  platform seam (`platform` column, per-platform mechanism contexts, 小红书/B站 stubs).
- CSV import now upserts (no duplicate rows on re-import) and reports per-row errors;
  parser tolerates `1.2万`, `21秒`, `0:21`, comma-grouped numbers.
- Analysis outputs are now schema-enforced via tool-forced JSON (structurally
  eliminates parse failures); API errors return a friendly retryable envelope
  instead of a 500.
- Baseline now averages the most recent 20 non-anomaly videos instead of all history.
- Upgraded `anthropic` SDK 0.39 → 0.116 (removes the httpx pin).

### [0.1.0] — 2026-07-02

### [0.1.0] — 2026-07-02

Initial public release of the runnable skeleton.

**Added**
- FastAPI backend with SQLite storage and a vanilla HTML/JS + Chart.js dashboard.
- Five independent analysis modules: enhancement direction, content ideas, trend
  forecast, pool diagnosis, and creator profile.
- CSV ingestion with fuzzy header matching (`COLUMN_ALIASES`).
- Anomaly-period handling that excludes flagged videos from baselines.
- Platform-mechanism reference framework in `prompts.py`.
- Project docs: `README.md`, design notes in `MEMO.md`, this `CHANGELOG.md`,
  `.gitignore`, and `.env.example`.

---

## 中文

### [未发布]

**新增**
- 截图采集：上传创作者中心截图（手机/PC 排版均可）→ Claude vision 提取草稿 →
  dashboard 内确认/修改 → 与 CSV 同一条 upsert 路径入库。私密视频自动标记并被
  服务端拒绝入库。
- 导出文件里从来没有的详情页字段：完播率、2s跳出率、弹幕、封面点击率、涨粉/取关、
  粉丝转化——`videos`/`video_snapshots` 新增可空列。
- 新增 `account_metrics` 表承接账号级页面（主页访问、净增粉/取关、账号完播率、
  作品搜索、同行百分位）+ `GET /api/account-metrics`。
- 详情页小时级趋势图做**定性**读取（形状描述+形态初判），作为 `curve_note` 存进
  vision 快照；扩散诊断把它当作数字快照的旁证使用。
- 采集节奏指南：`docs/capture-guide.md`（每条视频 +24h/+3天；每周列表+账号页各一张；
  无需整理文件夹）。
- 视频列表每行的删除按钮（连同快照/分析一起删，带确认）。
- 可插拔提取模型：`VISION_PROVIDER`/`VISION_MODEL` 把截图提取与分析模型解耦——
  Anthropic（默认升级为 `claude-sonnet-4-6`，不再用 Haiku）或 Gemini
  （`gemini-3.5-flash`，配 `GEMINI_API_KEY`）。
- 独立的暗色主题 HTML 账号报告（`GET /api/report`，`?download=1` 下载），只渲染已缓存分析，
  不产生新的 API 费用。
- Dashboard：带 logo/统计/操作入口的 hero 首屏、单视频指标对基线面板、快照扩散曲线图、
  logo/favicon 品牌化。
- 数据驱动的 API 冒烟测试（`tests/`），JSON + CSV 数据插槽。
- 每天首次启动自动备份数据库（`app/data/backups/`，保留 10 份）——保护手动录入的
  快照/内容画像不被云同步损坏。
- 每次分析的成本可见性：token 用量 + 耗时入库并显示在结果卡片上。

**变更**
- 用扩散曲线分析取代抖音"流量池分级"模型（pool_diagnosis → 曲线形状 / 扩散阶段 /
  限流vs衰减判别）；加入平台接缝（`platform` 列、按平台的机制上下文、小红书/B站占位）。
- CSV 导入改为 upsert（重复导入不再产生重复行）并逐行报告错误；解析器容忍
  `1.2万`、`21秒`、`0:21`、千分位逗号。
- 分析输出改为工具强制 JSON（从结构上消灭解析失败）；API 错误返回可重试的友好
  提示而不是 500。
- 基线改为最近 20 条非异常期视频的均值，不再全历史平均。
- `anthropic` SDK 0.39 → 0.116（移除 httpx 版本锁）。

### [0.1.0] — 2026-07-02

### [0.1.0] — 2026-07-02

可运行骨架的首个公开版本。

**新增**
- FastAPI 后端 + SQLite 存储 + 原生 HTML/JS + Chart.js 的 dashboard。
- 五个独立分析模块：增强方向、内容建议、流量预估、流量池定位、内容创作者画像。
- 带表头模糊匹配的 CSV 导入（`COLUMN_ALIASES`）。
- 异常期处理，计算基线时自动排除被标记的视频。
- `prompts.py` 中的平台机制参考框架。
- 项目文档：`README.md`、设计备忘 `MEMO.md`、本 `CHANGELOG.md`、
  `.gitignore` 和 `.env.example`。

---

[Unreleased]: https://github.com/Planetesimeow/Shiome/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Planetesimeow/Shiome/releases/tag/v0.1.0
