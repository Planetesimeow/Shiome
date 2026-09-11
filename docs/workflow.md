# Branches, releases and version codes / 分支、发布与版本号

> **Updated by creator instruction, 2026-09-11:** every new change, however small, gets
> a new branch based on the preceding work branch, and its PR targets that branch.
> This replaces the original rule that every feature starts directly from the release branch.
>
> **2026-09-11 创作者更新：** 每个新改动无论大小，都从前一个工作分支新建分支，PR 指向前一个分支。
> 这替代原先所有 feature 都直接从 release 分支切出的规则，从本次起执行。

> Adopted 2026-09-02, starting with Phase 1. Phase 0 shipped before this existed and was
> merged straight from a feature branch into `main`. The change that introduced these
> rules also went to `main` directly — it records the version `main` already was, so it
> could not wait behind a phase. Everything from Phase 1's first feature onward follows
> what is written below.
>
> 2026-09-02 起用，从 Phase 1 开始。Phase 0 是在这套规矩之前做的，直接从 feature 分支合进了 `main`。
> 引入这套规矩的那次改动本身也是直接进 `main` 的 —— 它记录的是 `main` 当时**已经**是的版本号，
> 不能压在一个阶段后面等。从 Phase 1 的第一个功能开始，一律照下面写的走。

---

## English

### Branches

```
main                        always releasable; every commit here is a shipped version
 └── release/phase-N-name   one long-lived branch per phase from the roadmap
      └── feature/a         first change; PR targets release
           └── feature/b    next change; PR targets feature/a
                └── feature/c  next change; PR targets feature/b
```

- **A release branch per phase.** Phases come from [`roadmap-v2.md`](roadmap-v2.md) —
  `release/phase-1-hosting`, `release/phase-2-capture`, and so on. It is created from
  `main` when the phase starts and deleted after it merges back.
- **Every new change gets a new branch before editing.** This includes small features,
  independent fixes, cleanup and documentation. The first branch starts from the release
  branch; each subsequent branch starts from the preceding work branch and targets it in
  its PR. If the preceding change has already merged, use its updated integration branch.
- **One cohesive change per branch and PR.** Review corrections to that change may stay;
  unrelated work requires the next branch. Do not keep accumulating features on an old branch.
- **`main` only ever receives a release branch**, as one PR at the end of the phase.
- **Merge parents before children.** Once a parent merges, retarget its child PR to the
  integration branch and check that its diff still contains only the child's change.
  Reconcile the child's history if the merge method requires it; avoid rewriting shared
  branches or force-pushing as a routine stack-maintenance step.
- **Delete merged branches only after their children are retargeted.** Do not remove a
  branch while another open PR still targets it. Existing PR history is not retroactively
  rearranged to adopt this rule.

### Version codes

A version is stated on **every** PR, in the PR title and in `app/__init__.py`.

| | Version | Example |
|---|---|---|
| Phase | one minor version | Phase 0 → `0.2.0`, Phase 1 → `0.3.0` |
| Feature PR within a phase, including stacked PRs | pre-release counter on the phase's version | `0.3.0-dev.1`, `0.3.0-dev.2` |
| Release branch into `main` | the phase version, suffix dropped, then tagged | `0.3.0` → tag `v.0.3.0` |

Semantic versioning, with the pre-1.0 caveat that breaking changes bump the **minor**
rather than the major — which is what a phase is, so the two line up naturally.

Every PR, including a small documentation or cleanup PR, therefore does three things:

1. Bump `__version__` in [`app/__init__.py`](../app/__init__.py).
2. Add the matching heading to [`CHANGELOG.md`](../CHANGELOG.md), in both languages.
3. Put the version in the PR title: `Add mobile capture page (0.3.0-dev.2)`.

`tests/test_version.py` fails if the constant and the newest changelog heading disagree,
so the two cannot drift apart quietly.

Tags carry a dot after the `v` — `v.0.1.0`, `v.0.2.0` — matching the tag already on the
repository. Only `main` is tagged.

### Why this shape

The previous workflow put every feature branch straight onto `main`, which was fine while
a change was one self-contained commit. It stops being fine when a phase is five changes
that only make sense together: hosting is not done until auth, deployment, backups and
the budget cap all exist, and merging any one of them into `main` alone would leave the
project in a state nobody wants to run.

A release branch gives a phase somewhere to be half-finished. `main` stays a branch you
can deploy from at any commit.

Stacked feature branches let work continue while earlier changes are under review. Each
PR shows only its own contribution against its parent, keeping even small changes reviewable.

The version code exists so that a bug report can name what it was running. Anything
published — a deployed instance, an exported report, a screenshot in an issue — should be
traceable back to a commit, and `GET /api/version` answers that at runtime.

---

## 中文

### 分支

```
main                        永远可发布；这里的每个提交都是一个已发布版本
 └── release/phase-N-name   路线图里的一个大阶段对应一条长期分支
      └── feature/a         第一个改动，PR 指向 release
           └── feature/b    下一个改动，PR 指向 feature/a
                └── feature/c  再下一个改动，PR 指向 feature/b
```

- **一个阶段一条 release 分支。** 阶段来自 [`roadmap-v2.md`](roadmap-v2.md) ——
  `release/phase-1-hosting`、`release/phase-2-capture`，以此类推。阶段开始时从 `main` 切出来，
  合回去之后删掉。
- **每个新改动先开分支，再开始编辑。** 小功能、独立修复、清理和文档变更都一样。
  阶段内第一条 feature 从 release 切出并指向它；之后每条从前一个工作分支切出，
  PR 也指向前一个分支。前一个改动已合并时，从更新后的承接分支继续。
- **一个分支和 PR 只承载一件完整的事。** 同一件事的审查修正可以继续提交；无关的新工作
  必须再开分支，不在旧分支里不断累加功能。
- **`main` 只接收 release 分支**，一个阶段结束时一个 PR。
- **先合父分支，再合子分支。** 父分支合并后，调整子 PR 的目标分支，并确认差异只包含
  子分支自身的改动。按合并方式处理历史衔接，不把强推或重写共享历史当作日常整理手段。
- **子 PR 调整完成后，才删除已合并的父分支。** 有开放 PR 指向它时先保留。本次规则
  从新工作开始执行，不追溯重排已有 PR 的历史。

### 版本号

**每个** PR 都要有版本号，写在 PR 标题里，也写在 `app/__init__.py` 里。

| | 版本号 | 例子 |
|---|---|---|
| 一个阶段 | 一个小版本 | Phase 0 → `0.2.0`，Phase 1 → `0.3.0` |
| 阶段内的 feature PR，包含指向前一个 feature 的 PR | 该阶段版本的预发布计数 | `0.3.0-dev.1`、`0.3.0-dev.2` |
| release 分支合进 `main` | 去掉后缀的阶段版本，然后打 tag | `0.3.0` → tag `v.0.3.0` |

遵循语义化版本，但有一个 1.0 之前的约定：破坏性变更升**小版本**而不是大版本 ——
而一个阶段恰好就是这个量级，所以两者天然对齐。

于是每个 PR，包括很小的文档或清理 PR，都要做三件事：

1. 改 [`app/__init__.py`](../app/__init__.py) 里的 `__version__`。
2. 在 [`CHANGELOG.md`](../CHANGELOG.md) 里加上对应的版本标题（中英文都要）。
3. 把版本号写进 PR 标题：`Add mobile capture page (0.3.0-dev.2)`。

`tests/test_version.py` 会在常量和最新的 changelog 标题不一致时报错，
所以这两处不会悄悄跑偏。

tag 在 `v` 后面带一个点 —— `v.0.1.0`、`v.0.2.0`，跟仓库上已有的 tag 保持一致。只给 `main` 打 tag。

### 为什么改成这样

之前每条 feature 分支都直接进 `main`。一个改动是一个自洽的提交时，这没问题。
但一个阶段是五个只有凑在一起才成立的改动时就不行了：上云这件事，要等鉴权、部署、异地备份、
预算上限都有了才算完成，单独把其中一个合进 `main`，只会让项目停在一个没人想跑的状态。

release 分支给一个阶段提供了「可以做到一半」的地方，而 `main` 保持在任何一个提交上都能部署。

串联 feature 分支让前一项仍在审查时也能继续工作；每个 PR 相对父分支只展示本项差异，
小改动也能单独审查和追踪。

版本号存在的意义，是让一份 bug 报告能说清楚「我跑的是哪一版」。任何流出去的东西 ——
部署的实例、导出的报告、issue 里的一张截图 —— 都应该能追回到一个提交，
`GET /api/version` 在运行时回答这个问题。
