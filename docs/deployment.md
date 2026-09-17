# 上线与手机使用 / Deployment and mobile access

本阶段提供手机浏览器可用的单用户实例。代码已经包含部署配置；**配置文件存在不代表实例已上线**。
正式验收以公网 HTTPS 地址、真实手机登录、数据重启后仍在，以及异地备份恢复演练为准。

## 部署前需要确定

- 一台可运行 Docker 的 Linux 服务器及 SSH 访问；或能运行 Docker、挂载持久磁盘的 Python 托管平台。
- 域名指向服务器，开放 TCP 80/443；使用托管平台自带 HTTPS 域名时不需要自行运行 Caddy。
- 登录口令、模型 API key、月度预算和异地备份目的地。密钥直接填服务器环境，不提交 Git。

当前是单用户、单实例、一个 Uvicorn worker。SQLite 必须放在持久磁盘；不能放进临时容器层、
短生命周期函数或多个实例各自独立的磁盘。备份与模型调用可能涉及私人数据，截图原件不会打入镜像。

## Linux 服务器：Docker Compose + Caddy

### 低预算个人试运行

单人、少量截图的起步配置可先用 1 vCPU / 1 GB 内存 / 20 GB 磁盘。实际服务器购入后仍需检查
可用内存、磁盘和到手机的网络；CI 覆盖的是受限容器中的启动、HTTPS、数据保留、备份和 12 MP
图片预处理，不代表已验证某一台 VPS 的实际性能。

将 `deploy/low-budget.env.example` 复制为 `.env.production`，填入凭据。该模板把 AI 月度额度设为
**0.75 美元**，并固定使用当前已有价格记录的 Anthropic 模型；这不是 0.75 人民币，也不包括服务器。
模板尚未部署时不会改变任何线上额度。启动时使用：

```bash
docker compose -f compose.yaml -f deploy/compose.small.yaml up -d --build --wait
```

后续更新也使用同样两个 `-f` 参数。应用容器限制 640 MB，Caddy 限制 96 MB，给小服务器的系统留出空间。
先逐张识别、按需运行分析；预算按已记录花销检查，最后一笔或同时进行的调用可能超出余额。
若需要更严格的账单限制，在模型服务商后台同时设置可用的额度/充值限制。

服务器费用和 AI 费用分别计费。年付服务器的“月均费用”不等于可以每月支付；下单前确认当期总价、
税费及续费金额。起步可用 [Duck DNS 免费子域名](https://www.duckdns.org/about.jsp)，将其 A 记录指向
服务器后交由 Caddy 申请 HTTPS 证书。备份先从应用下载到自己的另一台设备；自动异地备份另外配置。

### 通用配置

安装 Docker Engine 和 **Compose 2.30.0 或更新版本**。密码哈希包含 `$`，
这里用 [`env_file.format: raw`](https://docs.docker.com/reference/compose-file/services/#format)
确保原样传入。Caddy 根据域名自动签发和续期证书，证书数据也放在持久卷；
详细前提见 [Automatic HTTPS](https://caddyserver.com/docs/automatic-https)。

在准备部署的 Git 版本上执行：

```bash
cp deploy/production.env.example .env.production
chmod 600 .env.production
printf 'SHIOME_DOMAIN=shiome.example.com\n' > .env
docker compose build app
docker compose run --rm --no-deps app python -m scripts.set_password
```

将生成的 `SHIOME_PASSWORD_HASH` 和 `SHIOME_SECRET_KEY`，以及实际模型 key 写入 `.env.production`。
这个文件按 raw 格式读取：**不要给值加引号，也不要把 `$` 改成 `$$`**。`SHIOME_MONTHLY_BUDGET_USD`
示例为 20 美元，可自行降低；它只管理模型 API 调用，服务器费用另计。预算按已记录花销检查，
正在运行的请求可能使最终金额略超上限；无定价的模型调用不计入金额。

```bash
docker compose up -d --wait
curl --fail https://shiome.example.com/healthz
```

应用端口不会发布到宿主机；公网流量先到 Caddy，再到容器内部 8000 端口。转发头只在这个隔离拓扑下
信任全部来源；若改变拓扑或直接开放应用端口，必须配置具体可信代理，见
[Uvicorn proxy headers](https://www.uvicorn.org/settings/#http)。

`.env` 只放 Compose 域名配置；`.env.production` 放应用配置。生产模式在凭据缺失或格式错误时拒绝启动，
并始终要求浏览器通过 HTTPS 发送会话。不要在生产环境使用 `--reload` 或多 worker。

### 已有本地数据库

先备份，再迁移。命令使用新的目标文件名，已有文件会被拒绝覆盖。

```bash
# 在原来的本地 Python 环境执行；读取当前 SHIOME_DB_PATH 或默认库。
python -m scripts.backup shiome-transfer.db
# 用 SCP 将它传到服务器当前项目目录，然后暂停应用导入。
docker compose stop app
docker compose run --rm --no-deps --user root -v "$PWD/shiome-transfer.db:/import/shiome.db:ro" app python -m scripts.restore /import/shiome.db /data/imported.db
docker compose run --rm --no-deps --user root app chown 10001:10001 /data/imported.db
```

将 `.env.production` 的 `SHIOME_DB_PATH` 改成 `/data/imported.db` 后 `docker compose up -d --wait`。
原库与原路径继续保留，便于回退。上传到服务器的备份只由自己保管。

### 更新与回退

```bash
docker compose exec app python -m scripts.backup /data/pre-update-2026-09-11.db
git pull --ff-only
docker compose up -d --build --wait
curl --fail https://shiome.example.com/healthz
```

更新前记录 `git rev-parse HEAD`，备份文件名每次使用新时间。升级失败时检出上一个已验证版本，重新构建。
若升级涉及不可逆数据库结构迁移，先用下面的恢复流程把升级前备份恢复到新路径，再启动旧版本。
**不要使用 `docker compose down -v`：它会删除数据卷和证书卷。**

## 其他 Docker / Python 托管平台

构建仓库根目录 `Dockerfile`，将持久磁盘挂载到 `/data`（运行用户 UID 10001 须有写权限）。
设置 `SHIOME_ENV=production`、`SHIOME_DB_PATH=/data/shiome.db`、密码哈希、会话密钥、模型 key 和预算。
直接在平台的环境变量表单填原值，不加 shell 引号。健康检查路径为 `/healthz`。

启动命令为 `python -m scripts.serve`，读取平台提供的 `PORT`，默认 8000。
平台须提供 HTTPS、长请求支持及至少 12 MB 上传体积；图片识别可能持续数十秒。
`FORWARDED_ALLOW_IPS` 按该平台代理范围设置，不能对任意公网来源放开。

## 备份与恢复

启动时备份一次，之后每小时检查是否需要当天的备份，保留最近 10 天。
每日副本位于数据库旁的 `backups/`；迁移前带标记的备份单独保留。
采用 SQLite backup API 和完整性检查，写完后原子发布，失败会在服务日志中记录并于下一轮重试。

**同一块服务器磁盘上的备份不是异地备份。** 最小可用方式：手机或电脑的「工具 → 下载数据备份」
导出当时的完整数据库，并存入自己的云盘或另一台设备；在重要录入后执行。导出包含全部作品、快照、
画像与分析记录，不包含环境变量里的 API key 和登录密钥。
需要无人值守备份时，在确定自己的对象存储/第二台服务器后接入外部定时任务，将每天的完整快照加密上传；
在目的地尚未配置前，不能宣称自动异地备份已经生效。

恢复时先停止应用，将下载的备份挂载进容器，运行 `python -m scripts.restore <备份> <新路径>`，
再修改 `SHIOME_DB_PATH`、启动并核对作品/快照数量。脚本会校验完整性和 Shiome 表结构，拒绝覆盖已有文件。
至少实际恢复一次，确认备份可用。

## 手机验收

1. 用 Safari / Chrome 打开实际 HTTPS 地址，用口令登录。
2. 「截图」中选择一张真实创作者中心截图。提取会调用模型并计费，确认前不入库。
3. 核对标题、发布时间、作品时长及指标，详情页同时核对观察时间，然后确认入库。
4. 从「作品」查看结果，关闭再打开页面，确认数据仍在。
5. 「工具」下载备份并在另一台设备保存。退出后确认无法继续访问私人数据。
6. Safari 分享菜单中选择「添加到主屏幕」；Android Chrome 菜单中选择添加主屏幕入口。
   入口需要联网，不提供离线分析或后台上传。系统后台可能暂停识别请求，等待完成再切走更稳妥。

自动化浏览器检查覆盖 360 / 390 / 430 / 1280 像素、Chromium / WebKit：登录、切换视图、保留草稿、
会话过期后的重新登录、编辑保存、作品详情、下载备份及退出。测试识别使用固定数据，不调用付费模型。
自动化不能替代真实手机相册权限、真实域名证书及实际模型 key 的验收。

## English quick reference

This is a single-user, single-instance FastAPI app with SQLite. Build the root Dockerfile,
persist `/data`, configure production password/secret/API keys, and expose HTTPS. Compose
includes Caddy; managed hosting should supply its own HTTPS ingress. `PORT` is supported,
readiness is `/healthz`, and production refuses incomplete authentication configuration.

Daily snapshots are local only. Authenticated `/api/backup` downloads a fresh, verified
database for offsite storage. `python -m scripts.restore SOURCE NEW_PATH` restores without
overwriting existing databases. Configure an external destination before claiming automatic
offsite backups. Never remove production volumes when updating the application.
