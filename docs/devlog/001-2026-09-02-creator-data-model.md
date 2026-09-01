# 001 · The creator data model / 从「抖音工具」变成「创作者的工具」

**Date / 日期**: 2026-09-02
**Branch / 分支**: `feature/creator-data-model`
**Phase / 阶段**: Phase 0 — see [the roadmap](../roadmap-v2.md)

---

## What changed / 改了什么

Shiome used to keep everything in one table called `videos`. That table is now three:

- **accounts** — who you are on one platform. Your account persona used to be typed into
  the source code; it is now data you can edit.
- **creatives** — the thing you made: the hook, the on-screen text, the BGM, the content
  direction. Described **once**.
- **posts** — that creative published to one platform, with the numbers that platform
  measured.

Alongside it: a duplicate finder that shows you suspected repeats instead of quietly
merging them, an MIT license, a published roadmap, and a real test suite that runs on
every push.

潮目原本把所有东西放在一张叫 `videos` 的表里。现在它是三张：

- **accounts**（账号）—— 你在某个平台上的身份。账号人设以前是写在源码里的，现在是可以改的数据。
- **creatives**（创作物）—— 你做出来的那个东西：钩子、画面文字、配乐、内容方向。**只描述一次**。
- **posts**（发布）—— 那个创作物发到某一个平台上，以及那个平台量出来的数字。

同时还有：一个「发现疑似重复但不擅自合并」的功能、MIT 许可证、公开的路线图，
以及一套每次提交都会自动跑的测试。

---

## Why / 为什么

One table worked fine while there was one platform. It stops working the moment there
are two, because it quietly merges two different things: *what you made* and *what one
platform measured*. You shoot one video and put it on Douyin, Xiaohongshu and Bilibili —
that is one creative decision and three unrelated sets of numbers.

If we had kept the flat table, two things would have followed. The small one: you would
type out the same hook and the same BGM three times. The large one: Shiome could never
answer the only question that makes a three-platform tool worth building —

> *The same hook got saved on Xiaohongshu and died on Douyin. Who did each platform
> decide to show it to?*

Without that, three analysers behind one navigation bar is just three tools sharing a
header.

Reading the old code with three platforms in mind also turned up four bugs. All four
share a property that makes them worse than crashes: **they produce confident wrong
answers instead of errors.** The baseline averaged completion rates across platforms,
which is meaningless. The trend forecast had Douyin's "24 hours decides it" written into
the shared prompt, which is simply false for search-driven platforms. Two of the five
analyses did not know what platform they were talking about at all. And posts were
identified by exact title, so a screenshot of the list page (truncated title) and one of
the detail page (full title) became two rows.

The last one had already happened three times in your live database.

一张表在只有一个平台时是够用的。但一有第二个平台就不行了，因为它把两件不同的东西混在了一起：
**你做的东西** 和 **某个平台量出来的东西**。你拍一条视频发到抖音、小红书、B站 ——
这是一个创作决定和三套毫不相干的数字。

继续用扁平表会有两个后果。小的：同一个钩子、同一段配乐你要填三遍。大的：潮目永远回答不了
那个唯一能让「三平台工具」成立的问题 —— *同一个钩子在小红书被大量收藏、在抖音却死了，
两个平台分别把它推给了谁？* 没有这个，三个分析器共用一个导航栏，就只是三个工具共用了一个页头。

带着「三个平台」的视角重读旧代码，还翻出四个 bug。它们的共同点比崩溃更糟：
**不会报错，只会给出自信的错误答案。** 基线把不同平台的完播率平均在一起，那没有意义；
流量预估把抖音的「24小时定生死」写死在共享 prompt 里，对搜索驱动的平台完全不成立；
五个分析里有两个根本不知道自己在给哪个平台提建议；作品身份用标题精确匹配，
于是列表页截图（标题被截断）和详情页截图（完整标题）变成了两行 —— 这件事在你的线上库里
已经发生了三次。

---

## What this means for you / 这对你意味着什么

**Content profiles get typed once, not once per platform.** Today that saves nothing
because there is only Douyin. From Phase 3 onward it saves two thirds of the most tedious
work in the tool.

**Three duplicate groups are waiting for you.** They show up as a banner on the dashboard,
with the reason each was flagged, and nothing merges until you click. When you do, the
merge keeps the more precise version — for the 2026-07-05 pair it keeps 10,700 plays from
the detail page rather than the list page's rounded "1.1万" = 11,000 — and keeps the
readable title over the OCR-garbled one.

**Nothing was deleted.** The old tables are still in the database under `_v1_videos` and
`_v1_video_snapshots`, and a tagged backup was taken before anything ran.

**Your exported reports now survive.** They used to load the chart library from a CDN,
which meant a downloaded report showed no charts offline — or in a few years, when that
URL changes. The library is embedded now. A report is an archive; it should still open in
five years.

**Bookmarked API URLs will break.** `/api/videos` is `/api/posts`. That was deliberate —
today there are ten rows and one user, and it will never be cheaper to do.

**内容画像只填一次，不是每个平台填一遍。** 今天省不下什么，因为只有抖音。
但从 Phase 3 开始，这省掉的是这个工具里最烦那件事的三分之二。

**有三组重复在等你确认。** 它们会在 dashboard 上以横幅出现，每组都写清楚为什么被标出来，
不点就不会合并。你点了之后，合并会保留更精确的那份 —— 2026-07-05 那一组保留的是详情页的
10,700 播放，而不是列表页四舍五入的「1.1万」=11,000 —— 标题也保留可读的那个，而不是 OCR 乱码。

**没有删任何数据。** 旧表还在库里，改名成了 `_v1_videos` 和 `_v1_video_snapshots`，
而且迁移前另外打了一份带标记的备份。

**导出的报告现在能存住了。** 它以前从 CDN 加载图表库，意味着下载下来断网打开就没有图 ——
几年后那个网址一变也一样。现在库是内嵌的。报告是拿来存档的东西，五年后应该还打得开。

**收藏的 API 地址会失效。** `/api/videos` 变成了 `/api/posts`。这是故意的：
今天库里只有十行、只有一个用户，以后只会更贵。

---

## Notes from the buddy / 搭档的话

Three things you should push back on if you disagree:

**I did not auto-merge your duplicates, and that was a deliberate departure from what we
agreed.** We said the migration would merge all three groups. Then I looked at the actual
rows. One pair is only detectable by noticing that two posts on the same day have
identical likes and comments — their titles are `同样1200大卡，差距居然这么明显！...` and
`仙会3啖呃2`, which share nothing. Merging on that fingerprint means deleting a row based
on a guess, in a tool whose central rule is that a human confirms any number that drives a
decision. So the machine finds them and you decide. If you would rather it just merged
them, say so and I will add a flag.

**The similarity threshold is tuned on three examples.** 0.85 works on your data —
放松/放纵 scores 93%, 大厂/大广 scores 98% — but three examples is not a sample. If real
duplicates start slipping past, or unrelated videos start getting flagged, that number is
the first thing to move.

**One number in your data looks wrong and I left it alone.** The 2026-07-05 post has a
completion rate of 33.24% while everything else sits between 1.3% and 2.6%. That is a
twenty-fold outlier, and the same row is the one whose title was OCR-garbled — so I
suspect the extraction read the wrong field off that screenshot. I did not touch it,
because guessing at your data is exactly what this tool is supposed to not do. Worth
checking against the real page when you get a chance; it is currently pulling your
baseline completion rate up on its own.

有三件事，如果你不同意就直接推翻我：

**我没有自动合并你的重复数据，而这偏离了我们说好的做法。** 我们原本说迁移时把三组都合并。
后来我看了实际的数据行：其中一组只能靠「同一天发布、点赞和评论完全相同」发现 ——
两条的标题分别是「同样1200大卡，差距居然这么明显！...」和「仙会3啖呃2」，毫无相似之处。
靠这种指纹去合并，等于凭猜测删数据，而这个工具的核心规矩恰恰是「任何影响决策的数字都要人过一遍」。
所以改成机器发现、你来决定。如果你更想让它直接合并，说一声，我加个开关。

**相似度门槛是拿三个例子调出来的。** 0.85 在你的数据上是对的（放松/放纵 93%，大厂/大广 98%），
但三个例子不算样本。如果之后有真重复漏掉、或者不相干的视频被标出来，第一个该动的就是这个数。

**你数据里有一个数看着不对，我没动它。** 2026-07-05 那条的完播率是 33.24%，
而其他几条都在 1.3% 到 2.6% 之间 —— 差二十倍。而且恰恰就是这条的标题被 OCR 读成了乱码，
所以我怀疑提取时读错了字段。我没有改它，因为「对你的数据靠猜」正是这个工具最不该做的事。
有空的时候对着真实页面核一下；它现在正一个人把你的基线完播率往上拉。

---

## Creator's note / 创作者的话

> _(left empty on purpose — Clarence fills this in)_
>
> _（刻意留空——由 Clarence 填写）_
