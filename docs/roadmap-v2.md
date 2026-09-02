# v2 Roadmap — from a Douyin tool to a creator's tool

> Written 2026-09-02, at the start of the work. This is a plan, not a report of
> finished work — sections will be wrong in hindsight, and that is fine. It is here so
> that anyone reading the repo can see *why* the next few months of commits look the way
> they do, not just what changed.
>
> 写于 2026-09-02，工作开始之前。这是计划，不是完成报告——事后来看一定有判断错的地方，
> 这没关系。放在这里是为了让读这个仓库的人能看懂接下来这些提交**为什么**长这样，
> 而不只是看到改了什么。

---

## English

### What changes, in one sentence

Shiome stops being *a tool for analysing Douyin* and becomes *a tool for a creator who
publishes to several platforms* — Douyin first, then Xiaohongshu, then Bilibili — each
read under its own mechanism rules, all from one page, running on a server instead of
one laptop.

### The modelling problem that forced this

The v1 schema has a single `videos` table. It quietly conflates two different things:

- **what you made** — the hook, the on-screen text, the BGM, the content pillar
- **what one platform measured** — plays, completion, saves, followers gained

On a single platform those are the same row, and nothing goes wrong. On three platforms
they come apart. You shoot one video and publish it to Douyin, Xiaohongshu and Bilibili;
that is *one* creative decision and *three* completely different sets of numbers.

Keeping one flat table has two costs. The small one: you would describe the same video
three times, once per platform, in a form that is already the most tedious part of using
Shiome. The large one: you could never ask the only question that justifies putting three
platforms in one tool —

> *The same hook got saved on Xiaohongshu and died on Douyin. What does that tell me
> about who each platform decided to show it to?*

That question is the whole reason to unify. Three analysers behind one navigation bar is
not a product; it is three products sharing a header. So the data model splits:

```
accounts     one creator's presence on one platform (persona lives here)
creatives    the thing you made — described once, platform-agnostic
posts        one creative published to one account (metrics live here)
post_snapshots   time-series for one post
```

`platform_data` on `posts` is a JSON column for fields that genuinely exist on only one
platform — Bilibili's coins, Xiaohongshu's impression and search-share numbers. The
columns already in use stay columns; the rule going forward is that *new* platform-specific
fields go into JSON, so the table does not drift toward sixty sparse columns.

### Four things that were quietly broken for multi-platform

Found while reading v1 with three platforms in mind. Each would have produced confident,
wrong output rather than an error — which is the dangerous kind of bug for a tool whose
entire value is honest analysis.

1. **`compute_baseline` did not filter by platform.** It averaged the most recent 20
   videos across whatever was in the table. A Douyin completion rate, a Bilibili
   completion rate, and a Xiaohongshu image-text note that has no completion rate at all
   would have been averaged into a single meaningless number, and every "vs baseline"
   delta on the dashboard would have been drawn from it.
2. **The trend-forecast prompt hard-coded Douyin's clock.** "Most videos' fate is decided
   within 24 hours" sat in the shared system prompt, outside `get_mechanism_context()`.
   That is roughly true for Douyin and false for Bilibili and Xiaohongshu, where search
   long-tail means a post keeps accumulating for weeks.
3. **`content_ideas` and `creator_profile` took no platform at all** — module-level
   constant prompts with no mechanism context. They would have given Douyin advice about
   Xiaohongshu notes without any signal that they were doing so.
4. **Post identity was too weak.** The upsert matched on exact `(title, publish_date)`, so
   a list-page screenshot with a truncated title and a detail-page screenshot with the
   full title created two rows for one video. The live database had three such duplicate
   groups. Three platforms with three different ID formats would have made this worse.

### Decisions, and why

**Tenancy: build single-tenant, assume multi-tenant.** Shiome is for one creator today.
But the cost of *not* assuming a single user is small — an `owner_id` on accounts and a
discipline of never writing a query that assumes there is only one — while the cost of
retrofitting it later is a rewrite. So: SQLite stays, Postgres waits until a second person
actually logs in, and no code is written that would have to be unwritten.

**The `videos` → `posts` rename is done now, deliberately breaking things.** It touches
every query, the API surface and the frontend. It will never be cheaper than it is today,
with ten rows in the database and one person using it.

**Xiaohongshu before Bilibili.** Not because it is easier. Xiaohongshu's economics —
saves, search long-tail, high intent at low volume — match this account's actual goal of
精准触达 > 泛量增长 (precise reach over broad growth) much better than Bilibili's do. More
is learned per unit of work.

**Bilibili does not ship until its mechanism section is written.** `_PLATFORM_STUB` exists
so that a model asked about a platform we have not researched says "I don't have a
framework for this platform, confidence starts low" instead of improvising. Shipping a
platform while that stub is still in place would quietly discard the most valuable
discipline in this project.

### Phase order

```
Phase 0   accounts + creatives/posts split, persona as data, platform-scoped
          baselines, duplicate merge, pytest + CI
Phase 1   auth → deploy → offsite backup → monthly budget cap
Phase 2   mobile capture page, video → drafted content profile
Phase 3   Xiaohongshu
Phase 4   Bilibili + cross-platform comparison
Phase 5   A conversational assistant that knows your data
```

One hard constraint: **Phase 0 precedes the deploy.** Migrating a schema is dramatically
cheaper before there is live remote data to migrate.

One reordering worth explaining: hosting appears early, before the capture improvements,
even though it is not itself a feature. The most expensive part of using Shiome today is
not taking screenshots — it is moving them from a phone to a laptop. That step only
disappears when there is a server the phone can reach. Hosting is a prerequisite for the
usability fix, not a finale.

### Phase 5 — talking to it instead of reading it

Every screen in Shiome today answers a question you have to already know how to ask.
You pick a video, pick a tab, read a card. The thing a creator actually wants to say is
closer to *"why did this one die?"* or *"should I keep making these?"* — and the answer
usually needs several of those cards at once, plus context that is not on any screen,
like what you were trying to do that week.

So Phase 5 is a chat panel inside Shiome, talking to an assistant that already has your
account's data, content profiles, snapshots, cached analyses, and your own written notes.
Not a general chatbot with your data pasted in — an assistant whose default context *is*
your account.

Four sockets for it are already in place, built in Phase 0 while the schema was open:

- **`conversations` / `messages` tables.** Conversations have to persist for the assistant
  to remember anything, and adding tables is at its most expensive after deployment.
- **`app/analysis/context.py`.** One place that assembles "what do we know about this
  creator" — account, baseline, recent posts, creatives, account metrics, notes. The five
  analyses use it today; the assistant uses the same function tomorrow. It is a real
  abstraction in use, not a stub waiting for a feature.
- **`app/analysis/registry.py`.** The five analyses are declared once, with scope and
  description, instead of hard-coded into five routes. The routes read the registry now;
  the assistant will read it to expose them as callable tools.
- **`creator_notes`.** An assistant that only knows numbers cannot know that you are
  thinking about pivoting toward car-buying content, or that a week felt off. Platforms
  will never give you that. You have to write it down, so there is now somewhere to.

It sits last because it is worth more once there is multi-platform data to reason across —
but it does not depend on Bilibili, so it can move ahead of Phase 4 if it turns out to be
the thing that gets used daily.

### Deliberately not doing yet

- **A browser extension that reads the creator-center DOM.** It would give perfect data
  with no extraction cost and nothing to confirm. It is also per-platform work three times
  over, breaks whenever a page changes, and sits in murkier territory for a public project
  than for personal use. Worth doing — after the core.
- **Official platform APIs.** Worth investigating per platform rather than assuming. Not
  building the plan around them.
- **Billing, quotas, real user accounts.** No second user exists yet.

---

## 中文

### 一句话说清楚要改什么

潮目不再是「一个分析抖音的工具」，而变成「一个多平台创作者用的工具」——先抖音，再小红书，
再 B站——每个平台按自己的机制规则来读，但都在同一个页面里看；跑在服务器上，而不是一台笔记本上。

### 是什么建模问题逼出这次改动

v1 的 schema 只有一张 `videos` 表。它悄悄把两件不同的东西混在了一起：

- **你做出来的东西**——钩子、画面文字、配乐、内容方向
- **某一个平台量出来的东西**——播放、完播、收藏、涨粉

只有一个平台时这两者就是同一行，不会出问题。三个平台时它们会分开：你拍一条视频，同时发到
抖音、小红书、B站，这是**一个**创作决定和**三套**完全不同的数字。

继续用一张扁平表有两个代价。小的那个：同一条视频的内容画像你要填三遍，而这本来就是用潮目
最烦的一步。大的那个：你永远问不出那个唯一能证明「三个平台放在一个工具里」是值得的问题——

> *同一个钩子在小红书被大量收藏，在抖音却没起来。这说明两个平台分别把它推给了谁？*

这个问题才是统一的理由。三个分析器共用一个导航栏不是产品，只是三个产品共用了一个页头。
所以数据模型要拆开：

```
accounts     一个创作者在一个平台上的账号（人设存在这里）
creatives    你做出来的那个东西——只描述一次，与平台无关
posts        一个 creative 发到一个账号上（指标存在这里）
post_snapshots   某条 post 的时序快照
```

`posts` 上的 `platform_data` 是一个 JSON 列，装那些真正只有某一个平台才有的字段——B站的投币、
小红书的曝光量和搜索占比。已经在用的列保持是列；今后的规矩是**新增**的平台特有字段进 JSON，
这样表不会慢慢长成六十个稀疏列。

### 四个在多平台下会静默出错的地方

这些是带着「三个平台」的视角重读 v1 时发现的。它们的共同点是：不会报错，而会给出自信但错误的
结论——对一个全部价值都建立在诚实分析上的工具来说，这是最危险的一类 bug。

1. **`compute_baseline` 没有按平台过滤。** 它对表里最近 20 条视频求平均。抖音的完播率、B站的
   完播率、和一条根本没有完播率的小红书图文笔记，会被平均成一个没有意义的数字，而 dashboard 上
   每一个「对基线 Δ」都由它算出来。
2. **流量预估的 prompt 把抖音的时间尺度写死了。**「24 小时内多数已定」这句话在共享的 system
   prompt 里，不在 `get_mechanism_context()` 里面。这句话对抖音大致成立，对 B站和小红书是错的——
   搜索长尾意味着一条内容会持续累积好几周。
3. **`content_ideas` 和 `creator_profile` 根本不接收平台参数**——模块级常量 prompt，不带任何机制
   上下文。它们会用抖音的逻辑去建议小红书笔记，而且不会给出任何提示。
4. **作品的身份键太弱。** upsert 按 `(标题, 发布日期)` 精确匹配，所以列表页截图（标题被截断）
   和详情页截图（完整标题）会为同一条视频建出两行。线上库里有三组这样的重复。三个平台、三种
   ID 格式只会让这个问题更糟。

### 几个决定，以及为什么

**租户模型：按单用户建，但按多用户假设写代码。** 潮目今天只服务一个创作者。但「不假设只有一个
用户」的成本很小——accounts 上加一个 `owner_id`，加上「不写任何假设只有一个用户的查询」这条纪律
——而事后补上的成本是重写。所以：SQLite 留着，等真的有第二个人登录再谈 Postgres，现在不写将来
要推翻的代码。

**`videos` → `posts` 这个破坏性重命名现在就做。** 它会动到每一个查询、API 和前端。但今天库里只有
十行数据、只有一个人在用——以后只会更贵。

**先小红书，后 B站。** 不是因为它更简单。小红书的机制特点——收藏、搜索长尾、低量高意向——比 B站
更贴近这个账号真正的目标：精准触达 > 泛量增长。同样的工作量能学到更多。

**B站的机制部分没写完之前不上 B站。** `_PLATFORM_STUB` 存在的意义，就是让模型在被问到一个我们
还没研究过的平台时说「我没有这个平台的参考框架，置信度从低起步」，而不是即兴发挥。在占位说明
还挂着的时候就上一个平台，等于悄悄丢掉这个项目里最值钱的纪律。

### 阶段顺序

```
Phase 0   accounts + creatives/posts 拆分、人设变成数据、基线按平台隔离、
          重复数据合并、pytest + CI
Phase 1   鉴权 → 部署 → 异地备份 → 每月预算上限
Phase 2   手机采集页、视频 → 自动生成内容画像草稿
Phase 3   小红书
Phase 4   B站 + 跨平台对比
Phase 5   懂你数据的对话式助手
```

一个硬约束：**Phase 0 必须在部署之前。** 在还没有线上数据要迁移的时候改 schema，便宜得多。

一个值得解释的调整：部署被排得很靠前，在采集体验改进之前，尽管它本身不是一个功能。今天用潮目
最费劲的一步不是截图，而是把截图从手机搬到电脑。只有当存在一个手机能直接访问的服务器时，这一步
才会消失。部署是易用性改进的**前置条件**，不是收尾。

### Phase 5 —— 跟它说话，而不是读它

今天潮目的每一个界面，回答的都是你必须已经知道该怎么问的问题：选一条视频、选一个 tab、
读一张卡片。但创作者真正想说的话更接近「这条怎么就死了？」或者「这类还要不要继续做？」——
而这种问题的答案通常要同时用到好几张卡片，还要用到界面上根本没有的上下文，
比如你那一周本来想干什么。

所以 Phase 5 是潮目里的一个对话面板，对面的助手已经拿着你账号的数据、内容画像、时序快照、
已缓存的分析，以及你自己写下的想法。不是一个把数据粘贴进去的通用聊天机器人 ——
而是一个默认上下文就是你这个账号的助手。

它的四个插槽在 Phase 0 就已经装好了，趁 schema 还开着的时候：

- **`conversations` / `messages` 表。** 助手要能记住上下文，对话就必须落库；
  而加表最贵的时机是部署之后。
- **`app/analysis/context.py`。** 一处组装「关于这个创作者，我们知道什么」——
  账号、基线、近期作品、创作物、账号级指标、创作者笔记。五个分析今天就在用它，
  助手明天用同一个函数。它是正在被使用的抽象，不是等着功能来填的空壳。
- **`app/analysis/registry.py`。** 五个分析改成一处声明（带 scope 和描述），
  而不是写死成五个路由。路由现在读它；助手将来读它，把这些分析当作可调用的工具列出来。
- **`creator_notes`。** 一个只知道数字的助手，不可能知道你正在考虑转买车避坑方向，
  也不知道你觉得这周推流不对劲。平台永远不会给你这些，只能你自己写下来 ——
  所以现在有地方写了。

它排在最后，是因为等有了多平台数据可以横向推理时它的价值更大；
但它并不依赖 B站，所以如果它成了每天真正被用的那个东西，可以提到 Phase 4 前面。

### 刻意先不做的

- **读创作者中心 DOM 的浏览器插件。** 它能给到完美的数据，没有提取成本，也不需要人工确认。
  但它是三个平台各做一遍的工作量，页面一改就坏，而且对一个公开项目来说，它所处的位置比个人
  自用更模糊。值得做——在核心做完之后。
- **平台官方 API。** 值得逐个平台去查证，而不是先假设。计划不建立在它上面。
- **计费、配额、真正的用户账号体系。** 目前还不存在第二个用户。
