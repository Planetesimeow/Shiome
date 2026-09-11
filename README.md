# 潮目 Shiome

<img src="app/static/img/logo.png" alt="潮目 Shiome" width="320">

帮助创作者找到稳定的内容方向，提升观看和涨粉。将创作者中心截图转成可核对的数据，结合内容描述和历史表现，按需生成分析。

当前为**单用户试运行版本**，主要支持抖音。手机浏览器的登录、截图录入、作品查看与备份已实现；实际公网实例还需配置服务器、域名和凭据。版本见 [`app/__init__.py`](app/__init__.py)。

## 已有功能

- 截图上传 → AI 提取 → 编辑确认 → 入库；多张逐张处理，私密作品跳过。
- 作品级 CSV 导入、内容画像编辑、快照记录、疑似重复作品人工合并。
- 作品与创作物分离，同账号基线，异常期排除，播放与涨粉指标。
- 增强方向、内容建议、流量预估、扩散诊断、创作者画像五类按需分析，以及 HTML 报告。
- 手机总览 / 作品 / 截图导航；切换页面及重新登录时保留当前截图草稿。
- 登录、API 花销记录与月度额度、HTTPS 部署配置、每日备份及备份恢复工具。

## 本地运行

需要 Python 3.11 或 3.12。Windows PowerShell：

```powershell
git clone https://github.com/Planetesimeow/Shiome.git
cd Shiome
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

macOS / Linux 在克隆后执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 [本地应用](http://127.0.0.1:8000)。`.env` 会自动加载；浏览和手动编辑无需模型 key，截图识别和文本分析才需要相应凭据。未配登录时仅接受本机访问。手机远程使用按[部署指南](docs/deployment.md)配置 HTTPS 与登录。

## 数据和目录

| 目录 | 用途 |
|---|---|
| `app/` | API、数据、分析与静态界面 |
| `app/data/` | 默认本地数据库与备份，不提交 Git |
| `deploy/` | 生产及小服务器配置 |
| `scripts/` | 启动、口令生成、备份、恢复及创建全新演示库 |
| `tests/` | 隔离数据库测试、手机浏览器测试、容器部署验证 |
| `docs/` | 当前设计、路线图、操作指南和开发记录 |
| `userscreenshots/` | 本地真实截图，不提交 Git、不打入镜像 |

截图确认时核对标题、时间、单位和统计口径，具体见[采集指南](docs/capture-guide.md)。CSV 必须包含作品标题和发布时间，格式参考 [`sample_import.csv`](tests/fixtures/sample_import.csv)；只有日期和播放量的账号汇总表不能作为作品导入。

## 验证

安装 `requirements-dev.txt` 后，用虚拟环境里的 Python 执行：

```bash
python -m pytest -m "not costs_money"
```

浏览器测试使用独立临时库与模拟识别结果，不调用付费模型：

```bash
npm ci
npx playwright install chromium webkit
python -m tests.browser_server
# 在另一终端运行；WebKit 可设置 SHIOME_BROWSER=webkit
npm run test:mobile
```

CI 覆盖 Python 3.11 / 3.12、Chromium / WebKit 的手机流程，以及实际 Compose HTTPS、持久化和恢复。真实模型测试默认跳过。

## 文档

[当前设计](docs/design.md) · [路线图与未完成事项](docs/roadmap-v2.md) · [截图采集](docs/capture-guide.md) · [部署与备份](docs/deployment.md) · [分支发布约定](docs/workflow.md) · [开发日志](docs/devlog/README.md) · [更新记录](CHANGELOG.md)

## English

Shiome helps creators find repeatable content directions and improve viewing and follower growth. It turns creator-center screenshots into editable drafts, keeps post metrics separate from creative descriptions, and runs five analyses on demand.

This is a single-user pilot, currently focused on Douyin. Mobile navigation, login, screenshot confirmation, metrics, snapshots, CSV import, reports, API cost tracking and backup tools are implemented. A live instance still requires a server, domain and credentials; see [deployment](docs/deployment.md).

Use Python 3.11 or 3.12 and the commands above. Browsing and manual editing do not require a model key. CSV files must contain one post per row with a title and publication date. Phone access requires configured authentication and HTTPS. Data defaults to `app/data/shiome.db`; personal screenshots, databases and secrets are excluded from Git and Docker images.

The [current design](docs/design.md) and [roadmap](docs/roadmap-v2.md) distinguish working features from pending screenshot grouping, missing-value handling, goal selection and additional platforms. Analyses are hypotheses based on supplied data, not measurements of a platform's internal algorithm.

[MIT License](LICENSE)
