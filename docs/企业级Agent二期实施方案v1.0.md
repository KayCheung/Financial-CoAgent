# 企业级 Agent 平台二期分阶段实施方案

> **基准文档**：企业级 Agent 平台二期完整技术方案 v1.1  
> **编制日期**：2026-04-11  
> **核心原则**：每阶段可独立交付成果 · 任务间低耦合/接口化依赖 · 复用一期已验证基座

---

## 总览：四阶段里程碑

| 阶段 | 周期 | 核心目标 | 可见成果 |
|------|------|----------|----------|
| **一阶段：尽调基础版** | P2-M1-M2（8周） | 金融尽调 Plan 模式 + 受控多 Agent 入口 | 企业/个人尽调可发起、评分可输出、报告可生成 |
| **二阶段：尽调深水区 + 协同** | P2-M3-M4（8周） | 外部数据接入 + 协同审批 | 外部工商数据打通、多人协同审批可用 |
| **三阶段：Web Search** | P2-M5（4周） | 受控实时检索 | 合规白名单内 Web 检索上线（以合规审查通过为前提） |
| **四阶段：看板 + 调度器 + 生产就绪** | P2-M6-M8（12周） | 看板可视化 + 持久化调度器 + 全面投产 | 任务看板实时更新、定时任务可用、压测通过 |

---

## 二期启动前提

本方案基于一期已全面投产（一期 M10 完成）。二期开发不得在以下门禁未满足时启动：

| 门禁项 | 验收标准 | 检查方 |
|--------|----------|--------|
| 一期全链路压测通过 | 月末并发场景 P99 < 15s，Error Rate < 1% | 安全/运维 |
| Evaluation 基线已建立 | 标准样例集 + 脱敏真实流量双轨基线存在 | AI 算法 |
| SR 进入稳定运行区间 | 全局请求数 ≥ 1000 + 最近 200 次影子验证不一致率 ≤ 15% | AI 算法 |
| WAL Janitor 稳定运行 ≥ 30 天 | WAL 未同步条目数长期 < 10 | 安全/运维 |
| 一期红蓝对抗演练通过 | Prompt Injection + 越权测试无高危漏洞 | 安全/运维 |
| Patroni HA + Redis Sentinel 验证 | 主节点故障 30s 内自动切换，业务无感知 | 平台架构师 |

### 架构收敛声明对齐（继承一期 §1.2.1）

二期严格继承一期三类平台级硬约束，实施范围按以下映射组织：

| 硬约束类别 | 覆盖二期任务 | 实施阶段 |
|-----------|-------------|----------|
| **下游系统边界**：Harness 工具白名单、身份强覆写、主体类型隔离 | T2.1（受控多 Agent 入口）、T2.4（协同写入守卫）、T3.1（Web Search 工具） | 一 ~ 三阶段 |
| **状态与审计可恢复**：WAL、`AuditStoreFacade`、失败态扩展 | T2.2（尽调 DAG）、T2.5（协同服务）、T4.1（调度器） | 一 ~ 四阶段 |
| **发布准入**：Evaluation 回放门禁、规则库基线 | T2.3（尽调 Skill 上架）、T3.2（Web Search Skill 上架）、T4.5（调度类 Skill 上架） | 各阶段上架前 |

其余能力（Playwright 沙箱、CRDT 协同、Temporal 调度器）作为**风险增强项**，依据业务风险等级在三期评估后按需启用。

### 一期组件复用声明

以下一期组件在二期**零改动复用**，不计入二期工作量：

`TokenBudgetGuard`（仅扩展 entity 级字段）、`ThinToolInterceptor`（仅扩展白名单配置）、`HarnessScratchpad`、`GlobalToolLockRegistry`、`HITLApprovalStateMachine`（扩展多人通知，不改核心状态机）、`PIITokenizationGateway`、`TenantAwareVectorStore`、`LocalWALStore` + Janitor DaemonSet、`AdaptiveSemanticRouter`。

---

## 第一阶段：尽调基础版（P2-M1-M2，8周）

### 阶段目标

**让业务用户看到可交互的尽调成果**：能发起企业/个人尽调 Plan、触发受控多 Agent 执行、输出风险评分报告。

### 阶段完成指标

| 指标 | 达成标准 |
|------|----------|
| 尽调 Plan 可发起 | 从对话入口选择已发布模板，10s 内创建 Plan 并启动 DAG |
| 多 Agent 执行 | 企业尽调模板下，≥ 2 个子 Agent 并发执行，结果通过 Claim-Check 传递 |
| 风险评分 | 证据完整时，规则引擎评分结果在 3s 内返回，auto_block 规则 100% 生效 |
| 报告完整度 | DDReflectionGate 报告校验通过率（financial/legal/compliance/risk_conclusion 四章均在）≥ 95% |
| Evaluation 基线 | 尽调样例集 ≥ 50 条，`rule_hit_precision` 基线建立完成 |

### 新增/升级中间件

| 中间件 | 用途 | 部署要求 | 最低资源 |
|--------|------|----------|----------|
| 尽调模板服务（新增） | DD Plan 模板管理 + 版本化 | 2 副本 | 1C1G × 2 |
| Nacos（一期已有） | 尽调模板 YAML 热加载 | 复用一期 | 0 |
| OSS（一期已有） | 证据原件 + 结构化 JSON + 报告存储 | 复用一期 + KMS 扩展 | 按用量计费 |
| PG（一期已有） | `dd_plan_audit` 表（通过 `AuditHotStore` 写入） | 复用一期 | 0 |

> **阶段一资源增量**：约 +2C +2G，复用一期全部基础设施

---

### 任务拆分

#### T2.1 受控多 Agent 任务入口

**类型**：独立任务（无前置依赖，配置 + 接口包装）  
**预估工时**：4天

**范围**：
- 实现 `MultiAgentTaskGateway`：对话触发 → 模板选择 → Plan 创建 → 主体类型校验
- 注册 Semantic Router 新意图：`enterprise_due_diligence`、`individual_due_diligence`
- 实现 `validate_dd_subject_policy`：校验模板工具集合与主体类型约束（策略读 Nacos，不硬编码）
- Harness 工具白名单新增 `multi_agent_task_create`

**细节补充**：
- 主体类型在 Plan 创建时显式声明，不依赖模型从提示词中推断
- `ENTERPRISE` 类型：允许工商/司法/Web Search 白名单工具；`INDIVIDUAL` 类型：禁止 Web Search，仅允许人行征信、外部风控、内部私有数据
- 用户输入只能影响 `target_entity`、证据引用、审批人等业务参数，不能覆写 `tool_whitelist`、`agent_role`、`dependencies`
- 子 Agent 中间结果必须走 Claim-Check（OSS URI），禁止将 MB 级 JSON 写入 `AgentFastState`
- 开放式 Agent Studio（用户自定义 Agent 拓扑）列为三期，不进入二期交付

**验收标准**：从对话入口分别发起企业尽调和个人尽调，企业尽调可命中 Web Search 工具，个人尽调触发该工具时被拒绝并返回明确错误

---

#### T2.2 尽调 DAG 编排与 DDReflectionGate

**类型**：依赖 T2.1（接口依赖——需要 `DueDiligencePlan` 对象模型完成后构建 DAG）  
**预估工时**：6天

**范围**：
- 实现 `DueDiligencePlan` + `PlanNode` 数据模型（含 `subject_type`、`agent_role`、`tool_whitelist`）
- 实现 `build_dd_workflow`：依据模板动态构建 LangGraph DAG，复用一期 `detect_cycle`
- 实现 `SubAgentExecutor`：单节点内受控执行，结果写 Claim-Check + WAL
- 实现 `DDReflectionGate`：四类运行时检查点（规划/工具结果/风险/报告），通过 `AuditStoreFacade` 落审计

**细节补充**：
- DAG 构建前必须完成：环路检测 + 依赖完整性校验 + 主体类型策略校验，三者任意失败则拒绝执行
- Reflection 执行边界：规划反思只能阻断非法模板，工具结果反思最多触发节点级有限重试，报告反思只检查完整性（financial/legal/compliance/risk_conclusion 四章 + enterprise_name/investigation_date/risk_score 三字段非空）
- `AgentFastState` 新增字段：`dd_plan_id`、`dd_template_id`、`dd_current_node`、`dd_evidence_ready`、`dd_risk_score`、`dd_blocked_reason`
- 尽调审计统一通过 §1.4 `AuditStoreFacade` 写入，不直接绑定 PG 物理表

**验收标准**：模板含环路时 DAG 构建拒绝；四类 Reflection 检查点在对应节点后执行，记录写入 `dd_plan_audit`；报告缺少必要章节时进入 HITL

---

#### T2.3 DDCriticEngine 双轨评分引擎

**类型**：依赖 T2.2（接口依赖——需要证据包结构确定后才能实现规则评估）  
**预估工时**：4天

**范围**：
- 实现 `DDRiskRule` + 默认规则集（从 Nacos 热加载，支持租户级覆盖）
- 实现 `DDCriticEngine`：Tier A 规则引擎（零 Token）+ Tier C LLM Critic（仅非确定性规则触发）
- auto_block 规则命中直接映射 `AgentFailureState.FAILED_CLOSED`；非 auto_block 高风险规则触发 HITL

**细节补充**：
- 首版规则集至少覆盖：资产负债率（critical/auto_block）、连续亏损（high）、未结诉讼金额（high）、工商状态异常（critical/auto_block）、实控人变更频繁（medium）
- LLM Critic 只在非 auto_block 且 severity=critical/high 的规则命中时触发，单次消耗 ≤ 800 Token，走 Tier C 计费
- 规则库变更必须经过 Evaluation 门禁（`rule_hit_precision ≥ 0.95`），首版基线由 AI 算法团队在上线前完成人工标注

**验收标准**：auto_block 规则触发时任务直接终止；非 auto_block 高风险规则触发时进入 HITL 审批；评分结果在证据完整时 3s 内返回

---

#### T2.4 尽调模板引擎 + Skill 上架审核

**类型**：独立任务  
**预估工时**：4天

**范围**：
- 实现 YAML 格式尽调模板（版本化，存 Nacos）：`DueDiligenceSubjectType`、节点定义、`release_gate` 字段
- 投前尽调模板 v1：工商核验 + 财务文件采集 + 法务文件核查 + 风险评分 + 审批 + 报告生成（6 节点）
- 尽调 Skill 上架审核：红队扫描（≥ 10 个攻击向量）+ Evaluation 回放门禁通过 + Harness 兼容性校验
- Skill 元数据必须声明 `reflection_pass_rate`（≥ 0.95）评估项

**细节补充**：
- 模板版本升级必须经过 Evaluation 回放对比，不允许只改 Nacos 配置绕过门禁
- 历史线程绑定既有模板版本，新流量才切换到新版本
- 每个模板维护：当前稳定版本指针 + 当前灰度版本指针 + 最近一次可回滚版本指针

**验收标准**：红队扫描不通过的模板无法发布；Evaluation 门禁不通过时阻断发布；模板版本升级有回滚能力

---

#### T2.5 合规存档与 `AuditStoreFacade` 接入

**类型**：依赖 T2.2（接口依赖——需要 `DueDiligencePlan` 数据模型确定后规划存储结构）  
**预估工时**：3天

**范围**：
- 实现 `AuditStoreFacade`（含 `AuditHotStore`/`AuditEventBus`/`AuditColdAnalyticsStore` 三个 Protocol）
- 二期 `AuditHotStore` 实现为 PG，`AuditEventBus` 实现为 RocketMQ/ONS，`AuditColdAnalyticsStore` 实现为 PG 兼容层（三期切 ClickHouse）
- `dd_plan_audit` 表上线（通过 `AuditHotStore` 写入，含 PG RLS 策略）
- OSS 目录结构：证据原件 + 结构化 JSON + 最终报告，KMS 租户密钥加密，7 年 TTL

**细节补充**：
- `AuditStoreFacade.append()` 同步路径只含 WAL + HotStore；MQ 和冷存储异步投递，失败由 WAL Janitor 补偿重放
- 业务模块只能依赖三个 Protocol 接口，禁止直接引用 `clickhouse-driver` 或具体 PG 表名
- Nacos 配置 `audit_store_backend.clickhouse_enabled: false`，三期切换仅替换 `AuditColdAnalyticsStore` 实现

**验收标准**：尽调任意节点执行后，`dd_plan_audit` 有对应记录；跨租户查询被 RLS 拦截；OSS 证据文件有 KMS 加密标记

---

### 第一阶段任务依赖关系

| 任务 | 前置依赖 | 依赖类型 | 说明 |
|------|---------|---------|------|
| T2.1 受控多 Agent 入口 | 无 | — | 独立任务 |
| T2.2 DAG 编排 + Reflection | T2.1 | 接口依赖 | 需要 Plan 对象模型 |
| T2.3 评分引擎 | T2.2 | 接口依赖 | 需要证据包结构 |
| T2.4 模板引擎 + Skill 上架 | 无 | — | 可与 T2.2 并行，集成时需 T2.2 |
| T2.5 合规存档 + Facade | T2.2 | 接口依赖 | 需要数据模型确定 |

> **并行策略**：T2.1/T2.4 完全独立可并行。T2.2/T2.3/T2.5 可与 T2.4 并行开发，集成测试时需 T2.1 完成。

### T2 任务定义补充

| 任务 | 一句话定义 | 交付物 | 边界 | 验收 |
|------|-----------|--------|------|------|
| T2.1 受控多 Agent 入口 | 对话触发尽调时只能选已发布模板，不能自定义 Agent 拓扑 | 意图注册、主体类型校验、Harness 白名单扩展 | 不做 Agent Studio，不做自由编排 | 主体类型不符时工具被拒绝 |
| T2.2 DAG 编排 + Reflection | 尽调 DAG 编译前完成全量合法性校验，运行中有四类反思门 | DAG 构建器、子 Agent 执行器、反思记录 | 不做用户自定义 DAG，不做无限自循环 | 含环 DAG 拒绝，报告残缺触发 HITL |
| T2.3 评分引擎 | 规则引擎零 Token 兜底，LLM 只补歧义场景 | 规则集、双轨评分、HITL 分流 | 不做纯 LLM 评分，不做实时外部数据校验 | auto_block 规则触发即终止 |
| T2.4 模板引擎 + Skill 上架 | 尽调模板版本化管理，上架走红队 + Evaluation 门禁 | 模板 YAML、投前尽调 v1、Skill 审核流 | 不做开放模板市场，不做用户自建节点 | 门禁不通过时阻断发布 |
| T2.5 合规存档 + Facade | 统一审计写入接口，三期切 ClickHouse 时业务代码不动 | `AuditStoreFacade`、PG 实现、`dd_plan_audit` 表 | 不直接绑定 ClickHouse，不做实时监管报表 | 跨租户查询被 RLS 拦截 |

---

## 第二阶段：尽调深水区 + 协同（P2-M3-M4，8周）

### 阶段目标

**打通外部数据与多人协同**：工商 API 接入、尽调报告支持多人审批通知、评论标注可用。

### 阶段完成指标

| 指标 | 达成标准 |
|------|----------|
| 外部数据接入 | 工商 API 调用成功率 ≥ 95%（含 ToolLock 超时重试） |
| 报告生成 | 投前尽调全链路端到端，报告 PDF/DOCX 上传 OSS 并返回 `report_uri` |
| 协同通知 | 尽调报告完成后自动创建审批任务，协作者收到只读通知 |
| 评论可用 | 协作者可对线程/节点/证据添加评论，写入有审计记录 |
| Evaluation 门禁 | 尽调流程回放门禁接入 CI/CD，不达标自动阻断 |

### 新增中间件

| 中间件 | 用途 | 部署要求 | 最低资源 |
|--------|------|----------|----------|
| 协同服务（新增） | 共享线程管理 + 评论 + 通知 | 2 副本 | 1C2G × 2 |
| RocketMQ/ONS（已有） | 协同事件分发 | 复用一期 | 0 |

> **阶段二资源增量**：约 +2C +4G

---

### 任务拆分

#### T3.1 尽调外部数据接入（工商 API）

**类型**：独立任务  
**预估工时**：5天

**范围**：
- 封装企业工商信息查询 Tool（`corp_registry_fetch`），接入 ToolLock（max_concurrency 可配）
- 实现查询结果 Claim-Check：响应 JSON 写 OSS，仅将 `result_uri` 写入 `AgentFastState.payload_refs`
- Harness 工具白名单新增 `corp_registry_fetch`，仅对 `ENTERPRISE` 类型尽调生效
- 接口异常统一映射到失败态：超时 → `RETRYABLE`，数据格式损坏 → `HUMAN_REVIEW`，配额耗尽 → `RETRYABLE`

**细节补充**：
- 外部 API 响应时间不稳定时，ToolLock 超时 30s + 最多 2 次 `RETRYABLE` 重试，仍失败则降级为人工录入 + HITL 兜底
- 工商查询结果不得跨租户缓存；同一租户同企业可缓存（Redis，TTL 24h）
- `INDIVIDUAL` 类型尽调调用该工具时，Harness 直接拒绝并记录告警，不允许模型绕过主体类型限制

**验收标准**：企业尽调成功调用工商 API 并将结果 URI 写入状态；超时后进入 RETRYABLE 重试；个人尽调触发该工具时被 Harness 拒绝

---

#### T3.2 尽调报告生成 Skill

**类型**：依赖 T2.2 + T2.3（接口依赖——需要证据包 URI 与风险评分结果）  
**预估工时**：5天

**范围**：
- 实现 `dd-report-gen-v1` Skill：长上下文主力模型生成报告，输出 PDF/DOCX 到 OSS
- 报告必须包含 financial/legal/compliance/risk_conclusion 四章，且 enterprise_name/investigation_date/risk_score 三字段非空（`DDReflectionGate.reflect_report` 校验）
- 报告 `report_uri` 写回 `DueDiligencePlan.report_uri`，触发协同审批事件

**细节补充**：
- Skill 预算：`token_budget_complexity: complex`（50,000 tokens），Evaluation 指标：`report_field_coverage ≥ 0.90`
- 报告不得包含证据原件中的 PII 原文；敏感字段经 `PIITokenizationGateway` 掩码处理后写入报告
- 报告生成失败（字段不完整/反思门拒绝）→ `HUMAN_REVIEW`，不允许空报告通过

**验收标准**：投前尽调全链路执行完毕后，OSS 存在 PDF 报告；`DDReflectionGate` 报告反思通过；`report_uri` 可被协同服务读取

---

#### T3.3 协同服务：共享线程 + 评论标注

**类型**：独立任务  
**预估工时**：6天

**范围**：
- 实现 `ThreadShareRecord` + PG 表 `thread_shares`（含 RLS 策略）
- 实现 `CommentService`：评论写入 PG + WAL + RocketMQ/ONS 审计，评论不可修改内容（仅逻辑删除）
- 阶段一强制只读共享（`read_only: true`）：协作者可评论/标注，不能修改 `AgentFastState`
- 实现 `ThreadWriteGuard`：应用层拒绝非所有者写操作（409）；若后续执行态命令表落 PG，需同步增加 RLS 约束

**细节补充**：
- `CommentTargetType`：支持线程、DAG 节点、尽调证据项、审批记录四种目标
- 评论附件走 Claim-Check（OSS URI），不直接在 PG 存二进制
- 前端将 409 映射为只读提示（"阶段一仅所有者可修改执行状态，你可添加评论或标注"），不作为通用失败弹窗

**验收标准**：协作者可对尽调节点添加评论；非所有者修改执行状态返回 409；评论有审计记录，逻辑删除后仍可审计追溯

---

#### T3.4 协同审批编排（CollabApprovalOrchestrator）

**类型**：依赖 T3.2 + T3.3（接口依赖——需要 `report_uri` 和共享线程就绪）  
**预估工时**：4天

**范围**：
- 实现 `CollabApprovalOrchestrator`：尽调报告生成后自动创建共享线程 + 审批任务 + 通知协作者
- 复用一期 `HITLApprovalStateMachine.submit()`，不修改核心状态机签名
- 实现 `CollabNotificationExtension`：HITL 状态变更时同步通知所有协作者（只读通知，不赋予审批权限）
- 二期默认只将 `approver_ids[0]` 作为 HITL 决策人，其余人员接收只读通知

**细节补充**：
- 多人会签/或签需在后续版本显式扩展 HITL 状态机，不在二期实现
- 协同通知通过一期飞书/钉钉 IM 适配层发送，不重复实现 IM 客户端
- 所有协同审批创建记录通过 `AuditStoreFacade` 写入

**验收标准**：尽调报告 OSS 就绪后自动推送协同审批卡片；审批状态变更时协作者收到通知；通知有审计记录

---

#### T3.5 Evaluation 尽调流程回放门禁

**类型**：依赖 T2.3 + T2.5（接口依赖——需要评分结果和审计记录格式确定）  
**预估工时**：3天

**范围**：
- 建立尽调流程回放评估器：从脱敏历史轨迹重放，计算 `rule_hit_precision`、`evidence_completeness_rate`、`reflection_pass_rate`、`report_field_coverage`
- CI/CD 集成：门禁指标任意不达标时自动阻断发布（规则库变更：`rule_hit_precision < 0.95`；模板/报告 Skill 变更：`reflection_pass_rate < 0.95`）
- 扩展二期 Evaluation 能力表，纳入 §11 的 Evaluation Layer 扩展

**细节补充**：
- 首版基线建立：上线前由 AI 算法团队完成人工标注，不允许以"暂无基线"绕过门禁
- 样例集至少 50 条，覆盖企业/个人两类主体、正常/风险/边界三种场景

**验收标准**：`rule_hit_precision` 不达标时 CI 构建失败；基线对比报告可导出；门禁指标覆盖 §11 所有二期新增变更类型

---

### 第二阶段任务依赖关系

| 任务 | 前置依赖 | 依赖类型 | 说明 |
|------|---------|---------|------|
| T3.1 外部数据接入 | 无 | — | 独立任务 |
| T3.2 报告生成 Skill | T2.2, T2.3 | 接口依赖 | 需要证据包 URI + 风险评分 |
| T3.3 协同服务 | 无 | — | 独立任务 |
| T3.4 协同审批编排 | T3.2, T3.3 | 接口依赖 | 需要 `report_uri` 和共享线程 |
| T3.5 Evaluation 门禁 | T2.3, T2.5 | 接口依赖 | 需要评分结果和审计格式 |

### T3 任务定义补充

| 任务 | 一句话定义 | 交付物 | 边界 | 验收 |
|------|-----------|--------|------|------|
| T3.1 外部数据接入 | 企业尽调打通工商 API，超时有 RETRYABLE 重试，个人尽调硬性拦截 | Tool 封装、ToolLock 配置、失败态映射、缓存策略 | 不做爬虫，不做数据集成平台 | 个人尽调触发工商工具被拒绝 |
| T3.2 报告生成 Skill | 尽调完成后生成结构化报告，必经 Reflection 校验才可进入审批 | `dd-report-gen-v1`、PDF/DOCX 输出、OSS 存储 | 不做报告设计平台，不做无校验直通 | 缺少必要章节时触发 HITL |
| T3.3 协同服务 | 阶段一只读共享，协作者可评论/标注但不能修改执行状态 | 共享线程、评论服务、RLS 策略、ThreadWriteGuard | 不做并发写入，不做 CRDT | 非所有者写操作返回 409 |
| T3.4 协同审批编排 | 报告完成后自动拉起协同审批，HITL 变更时广播通知 | `CollabApprovalOrchestrator`、通知扩展 | 不做多人会签，不做审批流程配置平台 | 审批卡片推送可追溯 |
| T3.5 Evaluation 门禁 | 尽调规则库、模板、报告 Skill 变更前必须过评测 | 回放评估器、门禁规则、CI/CD 接入、基线文档 | 不做离线训练，不做主观审核替代 | 不达标构建自动阻断 |

---

## 第三阶段：Web Search（P2-M5，4周）

### 阶段目标

> **强前置约束**：本阶段开发以合规团队书面通过为前提，不得并行推进。若 M4 结束时合规未给出通过结论，则 M5 整体切为"技术预研月"（仅做沙箱 Profile 评估 + 白名单设计），开发不启动，M6 Roadmap 顺延一个月。

**让用户和尽调流程能安全使用受控互联网检索**：合规白名单内站点可检索，结果可信度评分，审计可追溯。

### 阶段完成指标

| 指标 | 达成标准 |
|------|----------|
| 合规前置 | 合规团队书面确认网络访问合规（不出境、白名单、留证、版权） |
| 白名单命中率 | 检索结果白名单命中率 ≥ 60% |
| 可信度均值 | 结果可信度均值 ≥ 0.70 |
| 审计覆盖 | 每次检索的 URL hash、域名、操作人、时间戳写入 WAL + AuditHotStore |
| 个人尽调隔离 | 个人尽调流程触发 Web Search 被 Harness 100% 拦截 |

### 新增中间件

| 中间件 | 用途 | 部署要求 | 最低资源 |
|--------|------|----------|----------|
| Web Search 服务（新增） | Brave/Bing API 封装 + 结果缓存 + 可信度评分 | 2 副本 | 1C1G × 2 |

> **阶段三资源增量**：约 +2C +2G

---

### 任务拆分

#### T4.1 Web Search 工具架构

**类型**：独立任务（以合规通过为前提）  
**预估工时**：5天

**范围**：
- 实现 `WebSearchTool`：合规白名单过滤 → 缓存命中 → Search API 调用 → 可信度评分 → 审计写入
- 实现域名白名单注册表（Nacos 热加载，金融监管/权威财经站优先）
- 审计意图先于任何网络请求写入 WAL；查询只记录 `query_hash` + 脱敏摘要，不存原始 query
- 二期不启用 headless 浏览器（Playwright）；Playwright 沙箱作为三期预研预案

**细节补充**：
- 无白名单内结果时返回空列表 + 告警，不回退到未受控外网搜索
- 检索结果仅存结构化摘要（≤ 500 字符 snippet），不存网页原文
- 结果缓存 TTL 1h，按 `tenant_id + query_hash[:16]` 键，不跨租户共享

**验收标准**：非白名单域名的结果被过滤；每次检索有 WAL 审计记录；个人尽调调用 Web Search 被 Harness 拒绝

---

#### T4.2 Web Search 独立对话入口

**类型**：依赖 T4.1（接口依赖——需要 `WebSearchTool` 就绪）  
**预估工时**：3天

**范围**：
- 注册 Semantic Router 新意图：`web_search`
- 实现 `WebSearchConversationGateway`：对话入口 → TokenBudget（`simple`，5,000 tokens，不允许升档）→ Harness 鉴权 → `WebSearchTool` 调用 → 结果渲染
- 前端：展示 title/source_domain/credibility/retrieved_at/snippet，无白名单结果时展示合规提示

**细节补充**：
- 独立对话入口预算与尽调流程的 `moderate`/`complex` 配额隔离，避免通过对话入口绕开尽调预算
- 检索结果默认只进入当前线程上下文；写入 L3 必须走 §5.6 的高可信度（≥ 0.80）+ HITL 确认双门槛

**验收标准**：用户在对话中触发搜索意图，结果在 10s 内返回；超过 simple 预算时被熔断；尝试传入 `task_complexity=complex` 时报错

---

#### T4.3 Web Search Skill 上架 + Evaluation 门禁

**类型**：依赖 T4.1（接口依赖——需要 `WebSearchTool` 完成后才能评测）  
**预估工时**：3天

**范围**：
- 建立 Web Search 质量评测基线（标准查询集 + 人工标注预期结果）
- Evaluation 门禁：`whitelist_hit_rate < 0.60` 或 `credibility_mean < 0.70` 时阻断升级
- Web Search Skill 初始灰度发布（canary 10%，仅 `investment_div` 租户）

**细节补充**：
- 评测样例集至少覆盖：金融监管查询、企业工商查询、市场数据查询三类，每类 ≥ 10 条
- 灰度期间观察 Web Search 白名单命中率、可信度均值、L3 污染率三个指标，全部达标后扩大灰度

**验收标准**：门禁指标不达标时 CI 阻断；灰度 10% 流量可正常使用；非授权租户访问被拒绝

---

### 第三阶段任务依赖关系

```
T4.1（Web Search 工具架构）─── [合规通过才可启动]
  ├─ T4.2（独立对话入口）← T4.1 接口依赖
  └─ T4.3（Skill 上架 + Evaluation）← T4.1 接口依赖
```

### T4 任务定义补充

| 任务 | 一句话定义 | 交付物 | 边界 | 验收 |
|------|-----------|--------|------|------|
| T4.1 Web Search 工具 | 合规白名单内受控检索，审计先于网络请求，不存原文 | `WebSearchTool`、白名单注册表、可信度评分 | 不做 headless 浏览器，不做未受控外网访问 | 非白名单结果被过滤，审计可追溯 |
| T4.2 独立对话入口 | 对话触发搜索走 simple 预算，不允许升档，不跨租户 | `WebSearchConversationGateway`、SR 意图注册 | 不做 Search 管理平台，不做结果自动入库 | 超预算熔断，个人尽调场景被隔离 |
| T4.3 Skill 上架 + 门禁 | 白名单命中率和可信度不达标时阻断升级，灰度受控 | 评测基线、门禁规则、CI/CD 接入、灰度配置 | 不做全量开放，不做绕过合规的特例处理 | 门禁失败时 CI 阻断 |

---

## 第四阶段：看板 + 调度器 + 生产就绪（P2-M6-M8，12周）

### 阶段目标

**平台化能力完善与全面投产**：任务看板实时可视，定时任务可管理，全链路观测完整，安全审计通过。

### 阶段完成指标

| 指标 | 达成标准 |
|------|----------|
| 看板实时性 | DAG 状态变更 → 看板卡片更新 P99 延迟 < 5s |
| WS 并发 | 500 并发 WebSocket 连接，P99 消息延迟 < 100ms |
| 调度任务 | daily_briefing 和 work_log_summary 在工作日按 cron 准时触发，成功率 ≥ 95% |
| 压测通过 | 月末尽调并发场景 P99 < 15s，Error Rate < 1% |
| 安全审计通过 | 二期新增功能通过红蓝对抗 + 第三方安全审计 |

### 新增中间件

| 中间件 | 用途 | 部署要求 | 最低资源 |
|--------|------|----------|----------|
| 看板服务（新增） | Board/Column/Card CRUD + WS 推送 | 2 副本 | 2C2G × 2 |
| WebSocket Gateway（新增） | WS 长连接管理 + 消息广播 | 3 副本 | 1C1G × 3 |
| Scheduler Worker（新增） | Redis Stream 消费 + cron 触发 | 2 副本 | 1C1G × 2 |

> **阶段四资源增量**：约 +6C +10G，不新增存储实例

---

### 任务拆分

#### T5.1 看板数据模型 + 事件驱动映射

**类型**：独立任务  
**预估工时**：4天

**范围**：
- 实现 PG 表：`kanban_boards`/`kanban_columns`/`kanban_cards`/`card_watchers`（含 RLS）
- `stage_map` 字段：Column 与 `AgentFastState.stage` 的映射规则
- 实现 `KanbanEventConsumer`：消费 RocketMQ/ONS 的 L2 审计事件流，更新 Card 所在列
- 消费侧不轮询 LangGraph，不修改 `AgentFastState`，纯读侧消费

**细节补充**：
- 每个 `thread_id` 对应一张 Card（UNIQUE 约束），Card 与 Board 通过 `tenant_id` 隔离
- HITL 进入待审批时，通知所有 `card_watchers`
- `AgentFastState.stage` → Column 映射至少覆盖：initiated/planning/executing/critic_review/human_approval/approved/rejected/completed/failed

**验收标准**：线程状态变更后，Card 在 5s 内更新到对应列；跨租户卡片被 RLS 拦截

---

#### T5.2 WebSocket Gateway

**类型**：独立任务  
**预估工时**：3天

**范围**：
- Kong 网关新增 WS 路由 `/api/v1/kanban/ws`，复用一期 JWT 插件
- 实现 WS 消息协议：客户端 `move_card`/`add_watcher`/`ping`；服务端 `card_moved`/`card_updated`/`hitl_pending`/`pong`
- WS 心跳检测（30s ping/pong），空闲连接 5 分钟自动断开

**细节补充**：
- SSE 和 WebSocket 并行共存，不废弃一期 SSE（Agent 回复流继续使用 SSE）
- 看板写操作（`move_card`）在 WS 服务端仍走 `ThreadWriteGuard` 校验，不绕过应用层守卫
- Consumer Name 格式：`worker:{hostname}`，不使用随机 UUID，保证 Pending List 可追踪

**验收标准**：500 并发 WS 连接稳定，P99 消息延迟 < 100ms；断线重连后状态自动同步

---

#### T5.3 持久化调度器（Scheduler）

**类型**：独立任务  
**预估工时**：5天

**范围**：
- 实现 `ScheduleJob`（PG 持久化）+ `SchedulerService`（Redis Streams + Consumer Group）
- 实现三种触发模式：cron / one_shot / chain
- 幂等锁 TTL 取 `max(TICK_INTERVAL_S * 5, job.timeout_s * 1.5)` 防止执行超时后重复推送
- Worker 只在成功执行或写入 DLQ 后 XACK，`RETRYABLE` 失败不确认消息
- Consumer Name 使用 `worker:{hostname}`，不使用随机 UUID

**细节补充**：
- `xgroup_create` 已存在时捕获 `BUSYGROUP` 异常不报错，支持多 Pod 启动幂等
- `FAILED_CLOSED` 类失败写入 `scheduler:dead_letter_jobs` Stream + 禁用 Job，等待人工处理
- TokenBudget 扩展 `entity_id`/`entity_type` 字段，调度任务的 Token 消耗按 `entity_type=schedule` 聚合
- 调度任务月度 Token 上限（`monthly_limit: 2_000_000`）在 Nacos 配置，告警阈值 80%

**验收标准**：cron Job 按时触发，成功率 ≥ 95%；FAILED_CLOSED 任务写入 DLQ 并禁用；并发执行场景无重复触发

---

#### T5.4 调度类具名 Skill（daily_briefing + work_log_summary）

**类型**：依赖 T5.3（接口依赖——需要调度器就绪后配置模板）  
**预估工时**：4天

**范围**：
- 实现 `daily_briefing` Skill：工作日 09:00 触发，聚合日历/看板/尽调 Plan 待处理节点/待审批事项，推送 IM
- 实现 `work_log_summary` Skill：工作日 18:00 触发，聚合当日线程摘要/调度运行记录/尽调/看板/审批意见，推送 IM
- 两个 Skill 均走 `WorkflowTriggerGateway` 触发，受 Harness 工具白名单 + TokenBudget（`simple`）约束

**细节补充**：
- `allowed_sources` 只是模板声明，Harness 授权必须以 `source_access_policy` 中的工具条目和访问范围为准
- 管理员查看他人数据必须显式授予 `delegated_view`/`team_admin_view` 范围，不因 `role=admin` 自动扩大可见性
- 两个 Skill 经 Skill 上架审核（红队 + Evaluation 门禁）后方可发布，初始灰度 10%

**验收标准**：工作日 09:00 收到今日待办 IM 推送；18:00 收到工作日志推送；推送有审计记录；非授权数据访问被拒绝

---

#### T5.5 二期可观测性扩展

**类型**：独立任务  
**预估工时**：4天

**范围**：
- 新增 OTel Span：`dd_plan.{node_type}`、`web_search.query`（记录 query_hash，不记录原始 query）、`scheduler.{trigger_type}`
- 新增 12 项告警指标（详见二期技术方案 §10）：尽调证据完整度、规则命中精确率、Reflection 阻断率、调度成功率、调度积压深度、entity 级 Token 月消耗、Web Search 白名单命中率/可信度均值、WS 连接数、协同评论写入延迟 P99、看板事件消费延迟 P99
- Grafana 新增二期 Dashboard：尽调漏斗视图、调度任务执行热图、entity 级 Token 成本视图

**细节补充**：
- `web_search_span` 只记录 `query_hash`，防止原始搜索词中包含 PII 或商业敏感信息
- 尽调 Reflection 阻断率突增（> 2x 基线）告警，联动模板配置检查

**验收标准**：12 项告警指标全部配置并可触发；二期 Dashboard 核心面板可正常展示；web_search Span 不含原始 query

---

#### T5.6 全链路压测 + 安全审计

**类型**：依赖 T5.1 ~ T5.5（降级依赖——建议在全部二期服务就绪后进行）  
**预估工时**：5天

**范围**：
- 月末尽调并发场景压测：模拟 20 并发企业尽调 + 10 并发个人尽调 + 50 并发看板实时更新
- 二期红蓝对抗：尽调规则绕过测试 + Web Search 白名单逃逸测试 + 协同权限边界测试（阶段一只读约束）+ 调度器重复执行攻击测试
- 第三方安全审计：重点审查尽调证据 OSS 访问控制、WebSocket 鉴权、`ThreadWriteGuard` 双层防护

**细节补充**：
- 压测指标要求：P99 < 15s，Error Rate < 1%，Token Budget 熔断不影响其他租户
- 对抗测试样本存储为可重放测试用例，纳入 CI 回归（等价于一期 T4.8 对 Web Search + 协同的扩展）

**验收标准**：压测指标全部达标；红蓝对抗无高危漏洞；第三方审计报告输出；对抗样本纳入 CI

---

### 第四阶段任务依赖关系

| 任务 | 前置依赖 | 依赖类型 | 说明 |
|------|---------|---------|------|
| T5.1 看板数据模型 | 无 | — | 独立任务 |
| T5.2 WebSocket Gateway | 无 | — | 独立任务 |
| T5.3 持久化调度器 | 无 | — | 独立任务 |
| T5.4 具名 Skill | T5.3 | 接口依赖 | 需要调度器就绪后配置模板 |
| T5.5 可观测性扩展 | 无 | — | 独立任务（集成时需各服务运行） |
| T5.6 压测 + 安全审计 | T5.1~T5.5 | 降级依赖 | 建议全部服务就绪后进行 |

### T5 任务定义补充

| 任务 | 一句话定义 | 交付物 | 边界 | 验收 |
|------|-----------|--------|------|------|
| T5.1 看板数据模型 | 以事件驱动方式将 DAG 状态同步到看板卡片，不轮询 LangGraph | Board/Column/Card 表、RLS、事件消费器 | 不做看板自定义工作流，不做甘特图 | 状态变更 5s 内同步，跨租户被隔离 |
| T5.2 WebSocket Gateway | SSE 和 WS 并行共存，WS 只用于看板实时同步 | Kong 配置、WS 协议、心跳检测 | 不替换 SSE，不做通用 WS 平台 | 500 并发 P99 延迟达标 |
| T5.3 持久化调度器 | 自建 Redis Streams 轻量调度，三期评估 Temporal | `SchedulerService`、DLQ、幂等锁、entity 级预算 | 不做通用 BPM，不做 Temporal 二期引入 | 成功率达标，重复执行被幂等锁阻断 |
| T5.4 具名 Skill | 办公场景定时推送，数据来源受 Harness 工具白名单约束 | `daily_briefing`、`work_log_summary`、Nacos 配置 | 不做任意脚本/任意 HTTP 调用 | 按时推送，非授权数据被拒绝 |
| T5.5 可观测性扩展 | 尽调/调度/Web Search/协同/看板的 Span 和告警全覆盖 | 12 项告警、3 类 Span、3 个 Dashboard | 不做单纯日志堆砌，要有追踪语义 | 12 项告警全部可触发 |
| T5.6 压测 + 安全审计 | 月末并发场景压测 + 二期功能对抗测试 + 第三方安全审计 | 压测报告、对抗样本集、审计报告 | 不只看平均值，必须看 P95/P99 | 压测达标，无高危漏洞 |

---

## 风险与应对

| 风险 | 影响阶段 | 应对措施 |
|------|----------|----------|
| Web Search 合规审查否决 | 三阶段 | M1 立即启动合规预审，M4 结束前出结论；否决则 M5 整体切为技术预研月，不影响其他功能交付 |
| 尽调外部 API 稳定性差 | 一/二阶段 | ToolLock 30s 超时 + RETRYABLE 重试（最多 2 次）；仍失败降级人工录入 + HITL 兜底 |
| 尽调规则库误报导致项目阻断 | 一/二阶段 | 规则分 auto_block 和非 auto_block 两级；非 auto_block 只触发 HITL；规则变更经 Evaluation 门禁 |
| 协同并发写入冲突（阶段一约束被绕过） | 二阶段 | `ThreadWriteGuard` 应用层 + PG 存储层双重防护；前端禁用非所有者写操作 UI |
| Scheduler Worker 重复执行 | 四阶段 | 幂等锁 TTL 覆盖任务最长执行时间 1.5 倍；Consumer Group ACK 机制；RETRYABLE 失败不 ACK |
| WebSocket 长连接资源泄漏 | 四阶段 | 30s ping/pong 心跳 + 5 分钟空闲断开 + 连接数告警（> 500/Pod） |
| Web Search 检索结果污染 L3 知识库 | 三/四阶段 | SearchToMemoryPolicy 强制高可信度（≥ 0.80）+ HITL 确认双门槛 |
| 一期 Evaluation 基线未建立导致二期门禁失效 | 贯穿全期 | §2 门禁：Evaluation 基线是二期启动的硬性前置条件，未满足时不允许启动 |
| Temporal 三期引入工期低估 | 四阶段后 | 二期调度器保持轻量自建；Temporal 仅在 M8 输出评估报告，不在二期做技术决策 |
| ClickHouse 三期接入改造量超预期 | 三期 | `AuditStoreFacade` 适配层隔离业务代码；三期仅替换 `AuditColdAnalyticsStore` 实现，不涉及业务逻辑 |

---

## 附录：全局异常映射表扩展（二期追加）

在一期基础映射表之上追加以下二期异常（不修改原有映射）：

| 异常场景 | 分类 | 说明 |
|----------|------|------|
| 外部 API 超时/网络抖动 | `RETRYABLE` | 工商/司法等外部数据接口波动 |
| 调度任务并发超限 | `RETRYABLE` | Scheduler 信号量争用 |
| 尽调证据不完整 | `HUMAN_REVIEW` | 必需文件缺失，需人工补录 |
| 尽调模板版本不匹配 | `HUMAN_REVIEW` | 历史线程绑定版本已下架 |
| DDReflectionGate 报告章节缺失 | `HUMAN_REVIEW` | 报告必要章节不完整 |
| Web Search 域名不在白名单 | `FAILED_CLOSED` | 合规硬性拦截 |
| Web Search 速率限制 | `RETRYABLE` | Search API 配额暂时耗尽 |
| Web Search 无白名单结果 | `HUMAN_REVIEW` | 结果全部被过滤，建议人工查证 |
| 尽调风险分 auto_block 触发 | `FAILED_CLOSED` | critical 规则自动阻断 |
| 调度 Job 被禁用 | `FAILED_CLOSED` | FAILED_CLOSED 异常已写 DLQ 并禁用 Job |
| 协同写入权限被拒绝 | `FAILED_CLOSED` | 非所有者尝试修改执行状态 |

---

## 补充说明：二期任务接单前必须确认的事项

与一期实施方案附录保持一致，每个任务接单前应明确以下六项：

1. `目标`：这个任务最终要解决什么问题。
2. `输入`：任务依赖哪些已有能力、接口、数据、配置。
3. `输出`：要交付的代码、接口、配置、文档、测试。
4. `边界`：明确本任务不做什么。
5. `验收`：用什么样的样例、指标、日志或测试来判断完成。
6. `依赖`：依赖哪些其他任务、哪些基础设施、哪些待定决策。

以下为二期特有的待讨论事项，接单前需明确结论：

- 工商/司法外部 API 的具体供应商和接入协议（影响 T3.1 接口实现）。`[待讨论]`
- 飞书/钉钉 IM 推送是否已有企业级账号和机器人鉴权（影响 T5.4 推送实现）。`[待讨论]`
- Web Search 合规审查的具体结论时间（影响三阶段启动日期）。`[待讨论]`
- 尽调报告 PDF/DOCX 的企业模板和品牌要求（影响 T3.2 报告生成格式）。`[待讨论]`
- Temporal/Argo 三期引入的评估范围和评估人（影响 T5.3 调度器边界）。`[待讨论，M8 前出评估报告]`