# 上线与手机使用 / Deployment and mobile access

本阶段提供手机浏览器可用的网页版。新增邀请制账号和按用户隔离，升级步骤见[账号与隔离说明](multi-user.md)。2026-09-17，创作者的个人 VPS 实例已完成公网 HTTPS、
登录保护、整机重启恢复和离机备份恢复验证；创作者已在 iPhone 确认上传与真实识别正常。
新建实例仍须按本文配置和验收。持续自动异地备份尚未配置，真实使用的质量、速度和费用继续观察。

## 部署前需要确定

- 一台可运行 Docker 的 Linux 服务器及 SSH 访问；或能运行 Docker、挂载持久磁盘的 Python 托管平台。
- 域名指向服务器，开放 TCP 80/443；使用托管平台自带 HTTPS 域名时不需要自行运行 Caddy。
- 初始化口令、模型 API key、月度预算和异地备份目的地。模型密钥填服务器环境或管理员设置页，不提交 Git。

当前是单实例、一个 Uvicorn worker，每位用户独立 SQLite 文件，另有私有身份库。所有数据库必须放在持久磁盘；不能放进临时容器层、
短生命周期函数或多个实例各自独立的磁盘。备份与模型调用可能涉及私人数据，截图原件不会打入镜像。

## Linux 服务器：Docker Compose + Caddy

### 首次上线：没有域名也可以开始

个人试运行可用 [sslip.io / nip.io](https://sslip.io/) 提供的免费 DNS 名称：
把公网 IPv4 写入 `shiome.<IP 的点替换为横线>.sslip.io`，例如
`shiome.203-0-113-10.sslip.io`（这是文档示例 IP，部署时必须替换）。
确认 DNS 返回自己的服务器地址，再写入 `.env` 的 `SHIOME_DOMAIN`。
Caddy 会为这个实际名称申请独立的公网证书；不要使用 `tls internal`，也不要关闭客户端证书校验。
此入口依赖第三方 DNS 和当前服务器 IP，适合作为试运行地址；以后可换成自己的域名或 Duck DNS。

新服务器先完成这些准备：

1. 使用提供商的初始凭据接入，安装自己的 SSH 公钥，并在第二个会话验证密钥登录。
   验证成功后再关闭 SSH 密码登录；私钥留在自己的设备，不能上传 Git。
2. 安装系统安全更新，确认时钟同步；如更新要求重启，重启后重新验证连接。
3. 按 [Docker 官方 Ubuntu 安装说明](https://docs.docker.com/engine/install/ubuntu/)
   安装 Engine 与 Compose 插件；1 GB 主机保留 swap，并使用下面的内存限制配置。
4. 防火墙允许 SSH、TCP 80/443 和 UDP 443。Docker 发布端口可绕过 UFW，
   因此继续只发布 Caddy 的端口，不向公网发布应用的 8000 端口或 Docker 管理接口。
5. 部署可追溯的 Git 提交，生成独立的应用登录口令和会话密钥。记录提交、访问地址及备份位置，
   凭据保存在权限受限的本地文件和服务器环境文件中，不能进入操作日志或 PR。

**首次管理员设置需要共享 API key。** 已有环境配置可以沿用，无需再次填写；否则在初始化页面输入一次。
模型密钥仅管理员配置，受邀用户只创建用户名和密码。密钥可用性通过免费的模型查询验证；截图识别与 AI 分析的真实质量仍需实际调用验收。不要把没有调用模型的测试写成 AI 已可用。
也不要将截图目录、开发用数据库或演示数据默认复制进生产实例。

上线后用真实 HTTPS 地址检查登录保护、登录后的接口与备份下载。重启应用后核对数据库仍在，
并将备份下载到自己的另一台设备，在新的文件路径实际恢复并核对完整性及记录数量。
临时检查数据应放在单独的测试库或独立实例；首次生产库可用默认账号记录验证持久化，
无需为了测试向正式作品列表写入虚构内容。主机重启后还应确认两个容器会自动恢复。

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

多用户实例还必须备份私有身份库和每位用户的数据文件；上例只备份当前默认个人库，完整目录与恢复要求见[账号与隔离说明](multi-user.md)。
更新前记录 `git rev-parse HEAD`，备份文件名每次使用新时间。源码检出文件应可供容器用户读取（普通文件通常 644），环境凭据文件保持 600。升级失败时检出上一个已验证版本，重新构建。
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
导出当前登录用户的完整内容数据库，并存入自己的云盘或另一台设备；在重要录入后执行。导出包含这个用户的全部作品、快照、
画像与分析记录，不包含环境变量里的 API key 和登录密钥。
需要无人值守备份时，在确定自己的对象存储/第二台服务器后接入外部定时任务，将每天的完整快照加密上传；
在目的地尚未配置前，不能宣称自动异地备份已经生效。

恢复时先停止应用，将下载的备份挂载进容器，运行 `python -m scripts.restore <备份> <新路径>`，
再修改 `SHIOME_DB_PATH`、启动并核对作品/快照数量。脚本会校验完整性和 Shiome 表结构，拒绝覆盖已有文件。
至少实际恢复一次，确认备份可用。

## 手机验收

1. 用 Safari / Chrome 打开实际 HTTPS 地址，完成首次管理员设置，再用用户名和密码登录。
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

This is an invite-only, single-instance FastAPI app with separate SQLite databases per user and a private identity store. Build the root Dockerfile,
persist `/data`, configure production password/secret/API keys, and expose HTTPS. Compose
includes Caddy; managed hosting should supply its own HTTPS ingress. `PORT` is supported,
readiness is `/healthz`, and production refuses incomplete authentication configuration.

Daily snapshots are local only. Authenticated `/api/backup` downloads a fresh, verified
database for offsite storage. `python -m scripts.restore SOURCE NEW_PATH` restores without
overwriting existing databases. Configure an external destination before claiming automatic
offsite backups. Never remove production volumes when updating the application.
