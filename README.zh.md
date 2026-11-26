# agent-architecture-guard

让编码 agent（Claude Code、Codex、Cursor 等）和人写的代码都守住项目架构，并让测试随代码演进、始终能追溯到业务规则。包含两个 skill，各配一个机器检查（[English](README.md)）：

- **architecture-guard** + `archguard`：代码放在哪里、哪个领域拥有哪些数据。
- **test-guard** + `testguard`：哪些规则被哪些情况测到、测试确实运行过的证据，以及让项目的测试原则、覆盖矩阵和测试随代码持续演进的循环。

架构部分分三层，可组合也可单用：

| 层 | 内容 | 适用 |
|---|---|---|
| 1. 协议 | `skill/architecture-guard/`：四步协议（读规范 → 先定位置 → 按规则编码 → 证明），项目没有规范时生成规范的提示词，规范模板 | 任意 agent：Claude Code 作为 skill 加载；其他工具经 `AGENTS.md` 读取（`templates/agents-snippet.md`） |
| 2. 守卫 | `guards/archguard/archguard.py`：表归属登记与只减不增的跨领域写入白名单，基于 SQL 与 ORM 映射 | 任何使用 SQL 迁移的语言（Java、Kotlin、TS/JS、Python、Go、C#） |
| 3. 分层规则 | `kits/`：ArchUnit（Java）、dependency-cruiser（TypeScript）、import-linter（Python）模板 | 项目自身的构建 |

`templates/` 中的 CI、pre-push 钩子与 PR 模板让检查无法绕过。

## 安装到项目

```sh
./install.sh /path/to/project          # 不覆盖已有文件；FORCE=1 只更新 skill 和 archguard
```

按输出的步骤：粘贴 AGENTS 片段，修改 `architecture/archguard.toml`，运行 `archguard init`（生成归属文件）和 `archguard init --baseline`（把现有违规登记进白名单，逐条写理由），加入分层规则模板和 CI，启用钩子。

## test-guard 与 testguard

`skill/test-guard/` 让 agent 从规则推导测试：读取（或生成后交人评审）项目的测试原则 → 列出改动涉及的规则及每条需要的情况类型 → 按情况设计数据 → 证明（`testguard check`，重新生成矩阵）→ 报告。另有演进循环，在规则变化、漏测缺陷和定时任务时运行。`references/failure-patterns.md` 列出测试套件在实践中的 16 种失败方式及对应的检查，生成的项目测试原则必须说明如何防范其中适用的每一种。

命令与失败条件见 [README.md](README.md)。

## archguard

命令与失败条件见 [README.md](README.md)。白名单每行：`写入领域 | 文件#函数 | 表 | 理由 | 移除迭代`（可写 `permanent`）。条目对应的违规消失后必须删除条目，所以白名单只减不增。

限制：运行时拼接的表名检测不到；领域由文件路径推断；注释中的 SQL 被忽略；`ON DUPLICATE KEY UPDATE` 不算写入。

测试：`python3 -m unittest discover -s guards/tests`。
