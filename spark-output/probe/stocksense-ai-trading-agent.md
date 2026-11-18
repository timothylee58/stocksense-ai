# Probe — StockSense AI Trading Agent（⚠️ 早期信号 · 样本量 0 人 · 案头证据 4 源 · 未达饱和）

- **生成时间**：2026-11-18T14:57:01Z
- **研究方法**：验证性访谈设计 + 案头证据综合（desk research）
- **参与者**：0 人（未执行真人访谈）；独立证据源 4 个：挑战页、Participants Handbook、Qoder Deck、代码库 `382f460`
- **饱和度**：❌ 未饱和（详见文末饱和度评估）
- **研究目的**：验证哪些功能扩展最能提升 2026 Moomoo x Qoder AI Trading Agent Challenge 的四项评分
- **研究问题**：
  1. 参赛者如何在 2 周窗口内分配时间到策略、风控、agent 工程、文档？哪些环节被放弃？
  2. 评委/组织者会从提交物中找哪些证据，判断风控是真可执行而非包装？
  3. 首次连接 moomoo MCP、识别模拟账户、试单时，卡点与误操作风险在哪？
  4. 什么条件下参赛者愿意持续记录决策（含 rejected）？
  5. StockSense 现有预测/简报/回测/dashboard 能承接哪一段，缺哪一段？

> **证据说明**：本轮没有真人访谈。下列所有 quote 均来自官方文档或代码原文，并标注 `[S1]`–`[S4]`，**不是用户原话**，不用于冒充访谈结论。`frequency` 表示“出现在几个独立证据源”，不是受访者人数。

---

## 主题归纳（按 frequency × emotional_intensity 排序）

### 🔴 theme-1 · 风控是 30% 主战场，但缺少可执行的盘前闸门
- **频次**：4/4 独立证据源
- **情感强度**：high
- **关联 segment**：AI 工程强/交易弱、交易强/AI 工程弱、评委
- **代表性原话**：
  > [S1 评审] Strategy & risk design (30%) — robust risk controls, including position limits, drawdown responses, and kill switches.
  > [S1 FAQ] You are responsible for defining your agent's strategy-level risk controls.
  > [S3 代码库] `predictor.py` 只有 `stop_loss` 字段（[predictor.py:219](stocksense-ai/backend/app/ml/predictor.py#L219)），没有仓位上限、组合回撤或熔断逻辑。

### 🔴 theme-2 · 评委要的是可审查的证据链，不是收益曲线
- **频次**：4/4 独立证据源
- **情感强度**：high
- **关联 segment**：评委、AI 工程强/交易弱
- **代表性原话**：
  > [S2 Deck] Compete on evidence, control and clarity.
  > [S2 Deck] Keep decision logs — Include rejected and failed decisions.
  > [S1 提交] a log of trading decisions, trade fills and results, and a demo showing what worked, what failed, and why.

### 🔴 theme-3 · Cloud Agent 编排与定时任务是 30% 分项，但配置摩擦高
- **频次**：4/4 独立证据源
- **情感强度**：high
- **关联 segment**：AI 工程强/交易弱、交易强/AI 工程弱
- **代表性原话**：
  > [S4 Handbook] Make task instructions self-contained. Avoid instructions such as “do what we just discussed”.
  > [S1 FAQ] Prefer a coordinator agent that runs on a schedule and triggers the other agents when needed.
  > [S1 FAQ] Must I use both local Qoder and Cloud Agents? Yes, you must use both of them.
  > [S3 代码库] [scheduler_service.py:1](stocksense-ai/backend/app/services/scheduler_service.py#L1) 仅 12 行占位，无实际调度实现。

### 🟠 theme-5 · 回测没有建模执行摩擦，Sharpe 与模拟盘会失真
- **频次**：3/4 独立证据源
- **情感强度**：high
- **代表性原话**：
  > [S2 Deck] Model execution friction — Include costs and partial fills.
  > [S1 FAQ] Account for commissions and slippage when evaluating your strategy and recording trades in your journal.
  > [S3 代码库] [backtest_service.py:77](stocksense-ai/backend/app/services/backtest_service.py#L77) `strat_log = log_ret * position`，未扣佣金、点差或滑点。

### 🟠 theme-8 · 提交物要求 deck + 可运行包 + 可复现，复用分占 15%
- **频次**：3/4 独立证据源
- **情感强度**：medium
- **代表性原话**：
  > [S1 提交] a Qoder-generated presentation deck together with a runnable trading-agent package.
  > [S1 FAQ] Explain your agent design, trading strategy, risk controls and results clearly enough for the judges to assess them.
  > [S2 Deck] Make results reproducible — Document how to rerun the work.

### 🟠 theme-4 · 模拟账户身份与权限选择存在误操作风险
- **频次**：2/4 独立证据源（FAQ + Handbook）
- **情感强度**：high
- **代表性原话**：
  > [S1 FAQ] During authentication, select Market Data ... do not select the live trading execution or account-order permissions.
  > [S1 FAQ] Paper trading accounts have their own identifiers, which the agent can read even if they are not visible in the app.
  > [S1 FAQ] Explicitly tell Qoder to use only that account for subsequent competition trades.

### 🟠 theme-6 · 单标的 long-only 回测难以支撑组合级风险调整收益
- **频次**：2/4 独立证据源（代码库 + 评审权重）
- **情感强度**：medium
- **代表性原话**：
  > [S3 代码库] Position: long-only (hold when predicted UP, flat otherwise). No shorting.
  > [S3 代码库] walk-forward 针对单一 ticker，无组合权重、行业暴露或相关性约束。

### 🔴 theme-7 · 比赛账户不可重置，测试会直接烧掉评分资金
- **频次**：1/4 独立证据源（FAQ），但失败代价为 blocker
- **情感强度**：high
- **代表性原话**：
  > [S1 FAQ] The competition account cannot be reset. ... To practise with a separate paper trading account first.

---

## JTBD

### jtbd-1
当我在两周赛程内构建交易 agent 时（context），我想把风控做成可配置、可审计的闸门（job），让我能在提交里证明回撤可控，而不是只展示收益（outcome）。

**支持证据**：theme-1, theme-2, theme-7

### jtbd-2
当我要向评委解释一次交易决策时（context），我想看到当时所有候选决策（含被拒绝的）及其理由和特征快照（job），让我能回答“为什么没做那笔交易”（outcome）。

**支持证据**：theme-2, theme-8

### jtbd-3
当我要让 agent 无人值守运行时（context），我想用一条自包含的定时任务串起 research → risk → execute（job），让我不用每天手动触发也能持续产出日志和报告（outcome）。

**支持证据**：theme-3

### jtbd-4
当我在验证策略时（context），我想在回测里计入佣金、点差、滑点和部分成交（job），让我看到的 Sharpe 与模拟盘结果可比（outcome）。

**支持证据**：theme-5, theme-6

### jtbd-5
当我要把成果复用到下一轮或交给他人时（context），我想把研究、风控、执行封装成 Skill + 模板 + runbook（job），让我能一键复现并写进 deck（outcome）。

**支持证据**：theme-8, theme-3

---

## Personas

### 🧍 persona-1 · 「证据型独立开发者」
- **Segment**：AI 工程强 / 交易经验弱
- **Goals**：用可审计证据拿到 QCA 与文档分；把时间投入能直接加分的最小功能；让 agent 稳定无人值守运行
- **Frustrations**：定时任务与多智能体配置摩擦大；不清楚评委到底看什么；手动整理决策日志耗时
- **Quote（官方文档，非用户原话）**：`[S2] Compete on evidence, control and clarity.` / `[S1] Must I use both local Qoder and Cloud Agents? Yes, you must use both of them.`

### 🧍 persona-2 · 「策略优先的交易者」
- **Segment**：交易强 / AI 工程弱
- **Goals**：把已有交易论据自动化执行；用可信风控证明策略不是赌运气；避免误用实盘权限或错误账户
- **Frustrations**：MCP 权限与模拟账户识别不清；账户不可重置，试错成本高；回测与模拟盘结果不一致
- **Quote（官方文档，非用户原话）**：`[S1] You are responsible for defining your agent's strategy-level risk controls.` / `[S1] The competition account cannot be reset.`

### 🧍 persona-3 · 「证据审查型评委」
- **Segment**：评委 / 组织者
- **Goals**：快速分辨真实风控与包装；验证结果可复现；看到失败与被拒绝的决策
- **Frustrations**：只看到收益曲线和截图；提交物无法重跑；风控参数没有触发记录
- **Quote（官方文档，非用户原话）**：`[S2] Make the evidence inspectable.` / `[S1] a demo showing what worked, what failed, and why.`

---

## 情感曲线

| 阶段 | 情感 | 关键洞察 |
| --- | --- | --- |
| 报名与领取模拟账户 | 🟡 neutral | 账户从 11/17 起分批开放，等待期 |
| 配置 MCP / Skills / 账户权限 | 🔴 negative ← 高风险段 | 权限选择与账户识别歧义（theme-4） |
| 首次试单 | 🔴 negative | 账户不可重置，试错直接消耗比赛资金（theme-7） |
| 搭建策略与回测 | 🟡 neutral | 回测可用，但摩擦缺失导致结果偏乐观（theme-5） |
| 配置 Cloud Agent / 定时 / 多智能体 | 🔴 negative ← 流失高发 | 任务需自包含、时区/并发限制（theme-3） |
| 模拟盘运行与监控 | 🔴 negative | 缺盘前闸门与统一 ops 视图（theme-1） |
| 整理决策日志与 dashboard | 🔴 negative | rejected 决策默认不记录（theme-2） |
| 提交 deck 与可运行包 | 🟢 positive | 证据齐备时最轻松（theme-8） |
| 决赛答辩 | 🟡 neutral | 取决于能否现场复现与解释 rejected（theme-2） |

---

## Top 痛点（按 severity × frequency 排序）

### 🥇 pain-1 · 模拟账户身份与权限歧义
- **描述**：可能在错误账户上试单或消耗比赛资金
- **严重度**：blocker
- **频次**：2/4 证据源
- **证据**：theme-4, theme-7
- **推荐下一步**：`/HMW` 生成“账户守卫 + dry-run”机会点

### 🥇 pain-2 · 缺少可执行的盘前风险闸门
- **描述**：无仓位上限、行业暴露、日亏限制、回撤熔断、kill switch
- **严重度**：blocker
- **频次**：4/4 证据源
- **证据**：theme-1
- **推荐下一步**：`/Brief` 直接转成风险组件策略

### 🥈 pain-3 · 没有记录被拒绝的决策
- **描述**：评委无法审查风控是否真的拦截过交易
- **严重度**：major
- **频次**：4/4 证据源
- **证据**：theme-2
- **推荐下一步**：`/Brief`

### 🥈 pain-4 · Cloud Agent 定时/多智能体配置摩擦
- **描述**：任务失败发现滞后，容易到提交时才发现没跑起来
- **严重度**：major
- **频次**：4/4 证据源
- **证据**：theme-3
- **推荐下一步**：`/Journey` 标出失败断点

### 🥈 pain-5 · 回测未计入执行摩擦
- **描述**：佣金、点差、滑点、部分成交缺失，风险调整收益失真
- **严重度**：major
- **频次**：3/4 证据源
- **证据**：theme-5
- **推荐下一步**：`/Brief`

### 🥈 pain-6 · 单标的 long-only 无法回答组合风险
- **描述**：没有组合权重、行业暴露、相关性约束
- **严重度**：major
- **频次**：2/4 证据源
- **证据**：theme-6
- **推荐下一步**：`/Brief`

### 🥈 pain-7 · 提交物缺少可复现 runbook
- **描述**：无法一键重跑，复用分白白丢掉
- **严重度**：major
- **频次**：3/4 证据源
- **证据**：theme-8
- **推荐下一步**：`/Brief`

### 🥈 pain-8 · 缺少统一 ops 视图
- **描述**：持仓、P&L、权益曲线、决策流分散
- **严重度**：major
- **频次**：3/4 证据源
- **证据**：theme-2, theme-3
- **推荐下一步**：`/Journey`

---

## 功能扩展清单（按评审权重 × 工期排序）

> 评分映射：风险调整收益 25% / Qoder & QCA 30% / 策略与风控 30% / 复用与文档 15%。P0 直接命中 60% 权重（策略风控 + QCA），并补齐 25% 的证据基础。

### P0（11/19–11/21，必须先做）

| # | 功能 | 命中评分 | 代码落点 | 验收标准 |
|---|---|---|---|---|
| F1 | **Account Guard + moomoo Execution Adapter**：paper-only、账户 allowlist、dry-run、下单前二次确认 | 策略风控 30% + QCA 30% | 复用 [MoomooClient 单例](stocksense-ai/backend/app/data/moomoo_fetcher.py#L52)；新增 `OpenSecTradeContext` 封装与 `routes/trading.py` | 拒绝任何非 SIMULATE 账户；日志打印被选中的账户 ID；dry-run 不产生真实订单 |
| F2 | **Pre-trade Risk Gate**：单票仓位上限、行业上限、日亏限制、组合回撤 kill switch、stop/take-profit | 策略风控 30% | 新增 `services/risk_gate.py`；limits 写入 [config.py:19](stocksense-ai/backend/app/core/config.py#L19) 邻近段；复用 [predictor stop_loss](stocksense-ai/backend/app/ml/predictor.py#L219) | 每个订单返回 PASS/REJECT + reason code；触发 kill switch 后自动只平不开 |
| F3 | **Decision Ledger**：accepted + rejected、reason code、特征快照、模型版本、幂等键 | QCA 30% + 文档 15% | 新增 `services/decision_ledger.py`；在 [ch_store.py:252](stocksense-ai/backend/app/core/ch_store.py#L252) 同层新增 ClickHouse 表 | 每条记录可追溯“为什么做/为什么不做”；可按日期与 ticker 导出 |

### P1（11/22–11/24）

| # | 功能 | 命中评分 | 代码落点 |
|---|---|---|---|
| F4 | **Ops Dashboard**：持仓、P&L、权益曲线、回撤、订单、决策流、rejected 原因 | QCA 30% + 风险收益 25% | 扩展 `frontend/src/app/dashboard/`，继续用 Recharts（AGENTS.md 约束） |
| F5 | **回测执行摩擦**：佣金、点差、滑点、部分成交、容量 | 风险收益 25% + 文档 15% | 扩展 [run_backtest](stocksense-ai/backend/app/services/backtest_service.py#L36)，输出成本分解 |
| F6 | **Coordinator 定时 + Slack**：盘前扫描、风险告警、收盘复盘 | QCA 30% | 实现 [scheduler_service.py](stocksense-ai/backend/app/services/scheduler_service.py#L1) 占位；任务自包含、显式时区、并发保护 |

### P2（11/25–11/28）

| # | 功能 | 命中评分 | 代码落点 |
|---|---|---|---|
| F7 | **Researcher → Risk Auditor → Executor 多智能体**：版本 pin、共享文件契约、审计独立会话 | QCA 30% | 复用 [briefing_service.py:79](stocksense-ai/backend/app/services/briefing_service.py#L79) 作为 researcher |
| F8 | **可复用 Skill 包 + runbook + Qoder deck 模板** | 文档 15% | 新增 `skills/stocksense-agent/SKILL.md`、`docs/runbook.md` |
| F9 | **Baseline 对比 + 样本外 HTML 报告** | 风险收益 25% + 文档 15% | 新增 `services/report_service.py` |

### 不建议做（避免 Scope Creep）

- 多腿期权策略：官方建议单腿，订单额度有限，投入产出比低。
- 日内高频 / 做市：2 周窗口与模拟盘约束下不可验证。
- 实盘交易：规则明确禁止。
- 运行时重训模型：AGENTS.md 明确禁止，且会破坏可复现性。
- 更换图表库：AGENTS.md 要求保留 Recharts。

---

## 饱和度评估

| 指标 | 数值 |
| --- | --- |
| 已访谈 | 0 人 |
| 重复出现 3+ 次的主题 | 5 个（theme-1/2/3/5/8） |
| 仅出现 1 次的独特洞察 | 1 个（theme-7） |
| 最近 2 场是否产生新主题 | 不适用（无访谈） |

**判断**：❌ **未饱和**。本轮是案头证据综合，不满足访谈饱和度标准。5 个主题在 3+ 独立文档/代码源中出现，可作为较强早期信号；theme-7 虽只有 1 源，但失败代价为 blocker，必须保留。

**建议**：若能在 11/21 前完成 3 场真人访谈，重点验证 theme-3（定时任务失败率）与 theme-4（账户误选），这两项最影响 P0 优先级。

---

## 交叉验证建议

- **Signal 验证**：
  - 在 WhatsApp 群、Kickoff Q&A、Qoder 社区检索 `account identifier`、`定时任务失败`、`MCP 权限`，验证 theme-3 / theme-4 是否为大样本高频。
  - 若有工单/社区帖子，跑 `/工单分析` 验证 pain-1、pain-4。
  - 用决赛入围 deck 做样本，检查是否都展示决策日志与回撤控制。
- **Bench 启发**：
  - moomoo 模拟盘与 TradingView Paper Trading 的持仓/订单呈现。
  - Composer / Alpaca Dashboard 的回撤与 kill switch 可视化。
  - QuantConnect backtest report 的成本与容量分解。

---

## 1 周执行建议（对齐赛程）

| 日期 | 动作 |
| --- | --- |
| 11/18 | 本报告定稿；确认真人访谈是否可行；锁定 F1–F3 |
| 11/19–11/21 | 实现 F1–F3；用独立模拟账户跑 dry-run 与 1 笔测试单 |
| 11/22–11/24 | 实现 F4–F6；接入 Slack/定时任务；Dashboard 可截图 |
| 11/25–11/26 | 跑 2–3 个固定评估 prompt，diff 输出；补 F7 多智能体 |
| 11/27–11/28 | 生成 HTML 报告与 Qoder deck；写 runbook；封版 |
| 11/29 | 复现检查：按 runbook 在干净环境重跑一次 |
| 11/30 | 提交（截止 23:59 SGT） |

---

## 下一步建议

- **Brief 接力**：把 JTBD-1/2 与 persona-1/2 写入 Brief 的“用户”段，把 F1–F3 转成策略目标与验收标准。
- **Journey 接力**：用情感曲线的 9 个阶段展开完整备赛旅程，标注 pain-1/4/8 的失败断点。
- **HMW 接力**：pain-1 转 2 个 HMW（如何在不接触比赛账户的情况下安全试单？如何让 agent 自证选对了账户？）。
- **Signal 验证**：0 人访谈样本，关键痛点需在社区/FAQ 做大样本验证。
