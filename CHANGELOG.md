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

- _Nothing yet._

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

- _暂无。_

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
