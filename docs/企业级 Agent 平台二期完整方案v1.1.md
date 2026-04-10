# 企业级 Agent 平台二期完整技术方案

> **版本**：v1.1 
> **上游基座**：企业级 Agent 平台一期完整方案v1.6.md  
> **技术基座**：DeerFlow 2.0 + LangGraph 1.0 + LangChain 0.3  
> **目标场景**：金融企业私有化部署 · 在一期闭环基础上扩展协作与智能检索能力  
> **核心立场**：二期是一期架构的延伸，不是重建。所有新能力必须经过 Harness 层守护，复用一期已验证的安全、审计与记忆基座。

---

## 目录

1. [二期总览与边界声明](#1-二期总览与边界声明)
   - 1.1 功能优先级与交付顺序
   - 1.2 架构收敛原则
   - 1.3 一期组件复用声明
   - 1.4 审计与分析存储适配层
2. [前置条件：一期生产就绪验收门禁](#2-前置条件一期生产就绪验收门禁)
3. [金融尽调 Plan 模式](#3-金融尽调-plan-模式)
   - 3.1 设计目标与场景
   - 3.2 模板引擎与 Plan 对象模型
   - 3.3 尽调 DAG 编排扩展
   - 3.3.1 受控多 Agent 任务入口
   - 3.4 尽调评分与 Critic 规则集
   - 3.4.1 运行时 Reflection 检查点
   - 3.5 合规存档与报告输出
   - 3.6 Skill 元数据规范
4. [协同能力（Collaboration）](#4-协同能力collaboration)
   - 4.1 设计边界与分阶段原则
   - 4.2 共享线程与可见性模型
   - 4.3 评论与标注服务
   - 4.4 通知与审批桥接
   - 4.5 冲突语义与乐观并发
5. [Web Search（受控实时检索）](#5-web-search受控实时检索)
   - 5.1 合规前置：金融场景网络访问约束
   - 5.2 独立对话入口
   - 5.3 检索工具架构
   - 5.4 沙箱隔离：Playwright 专属 Profile
   - 5.5 结果处理：可信度打分与缓存
   - 5.6 检索结果进入 L3 记忆的策略
6. [看板（Kanban）](#6-看板kanban)
   - 6.1 数据模型：Board / Column / Card
   - 6.2 DAG → Card 的事件驱动映射
   - 6.3 实时推送：WebSocket 升级方案
   - 6.4 权限与 ABAC 集成
7. [持久化调度器（Scheduler）](#7-持久化调度器scheduler)
   - 7.1 调度器选型决策
   - 7.2 调度器核心设计
   - 7.2.1 调度类具名 Skill
   - 7.3 外部触发 LangGraph 接口
   - 7.4 TokenBudget 扩展：entity 级配额
   - 7.4.1 调度任务成本聚合视图
8. [二期扩展：新增中间件与基础设施](#8-二期扩展新增中间件与基础设施)
9. [二期 Harness 层扩展](#9-二期-harness-层扩展)
10. [二期可观测性扩展](#10-二期可观测性扩展)
11. [二期 Evaluation Layer 扩展](#11-二期-evaluation-layer-扩展)
12. [部署规格增量](#12-部署规格增量)
13. [实施 Roadmap（8 个月）](#13-实施-roadmap8-个月)
14. [风险应对矩阵](#14-风险应对矩阵)

---

## 1. 二期总览与边界声明

### 1.1 功能优先级与交付顺序

| 优先级 | 功能 | 依赖的一期能力 | 对一期改动量 | 独立可交付 |
|---|---|---|---|---|
| P0 | 金融尽调 Plan 模式 | LangGraph DAG、HITL、OCR、L2/L3、Skill 中心 | 低（扩展） | 是 |
| P0 | 受控多 Agent 任务入口 | Semantic Router、尽调模板、LangGraph DAG、Harness | 低（配置 + 入口包装） | 是 |
| P1 | 协同（评论/共享/审批） | L2 事件源、HITL、ABAC、RocketMQ/ONS | 低（新增服务） | 是 |
| P1 | Web Search | Skill 中心、沙箱、Harness、L3 | 中（新沙箱 Profile） | 是 |
| P2 | 看板（Kanban） | L2 事件流、LangGraph 状态、SSE→WS | 低（前端 + 新表） | 是 |
| P2 | 持久化调度器 | LangGraph 触发接口、TokenBudget | 低（外部包装） | 是 |
| 三期 | AI 分身（Persona） | L3 长期记忆、Skill 绑定、TokenBudget 扩展 | 高（独立服务） | 三期专项 |

### 1.2 架构收敛原则（继承一期）

二期严格继承一期 §1.2.1 的架构收敛声明，平台级默认硬约束仍仅保留三类：

1. **下游系统边界硬约束**：新增功能（尽调外部数据源、Web Search、协同写入）均须通过 Harness 的工具白名单与身份强覆写，不允许旁路。
2. **状态与审计可恢复硬约束**：新增的 Board 服务状态、调度任务状态、协同操作记录，全部纳入 WAL + RocketMQ/ONS 审计链路。
3. **发布准入硬约束**：二期每个新 Skill（尽调、Web Search、调度类 Skill）上线前，必须通过 Evaluation 回放门禁。

### 1.3 一期组件复用声明

以下一期组件在二期中**零改动复用**，不作为二期工作量：

- `TokenBudgetGuard`（仅扩展 entity 级配额维度，不改核心逻辑）
- `ThinToolInterceptor`（仅扩展白名单配置，不改拦截代码）
- `HarnessScratchpad`（全量复用）
- `GlobalToolLockRegistry`（全量复用）
- `HITLApprovalStateMachine`（扩展多人审批通知，不改核心状态机）
- `PIITokenizationGateway`（全量复用）
- `TenantAwareVectorStore`（全量复用）
- `LocalWALStore` + Janitor DaemonSet（全量复用）
- `AdaptiveSemanticRouter`（全量复用）

### 1.4 审计与分析存储适配层

二期新增尽调、Web Search、协同、看板和调度器后，审计写入点会明显增多。为避免业务代码直接依赖 ClickHouse 表结构，二期统一通过审计与分析存储适配层访问热审计、事件总线和冷分析存储：

- `AuditHotStore`：承载二期在线查询、回放、HITL 审批追溯与近期报表，二期默认实现为 PG，复用一期 RLS 与分区策略。
- `AuditEventBus`：承载异步审计事件分发，二期默认实现为 RocketMQ/ONS（阿里云 ONS），保持 WAL 先写、消息后发。
- `AuditColdAnalyticsStore`：承载长期聚合、低频分析与监管留存查询，二期提供接口与空实现/PG 实现，三期再接 ClickHouse。

业务模块只能依赖上述接口，不直接依赖 `clickhouse-driver`、SQLAlchemy ClickHouse 方言或具体 ClickHouse 表名。三期接入 ClickHouse 时，仅替换 `AuditColdAnalyticsStore` 实现和迁移脚本，不修改尽调、调度器、Web Search、协同服务的业务流程。

```python
from typing import Protocol, Optional, Dict, List

class AuditEvent:
    event_id: str
    tenant_id: str
    event_type: str
    entity_type: str       # dd_plan / schedule / web_search / collab / kanban
    entity_id: str
    payload_hash: str
    payload_uri: Optional[str]
    operator_id: str
    occurred_at: float


class AuditHotStore(Protocol):
    """在线审计查询与近期回放，二期默认 PG 实现。"""
    async def append(self, event: AuditEvent) -> None: ...
    async def query_by_entity(
        self,
        tenant_id: str,
        entity_type: str,
        entity_id: str,
        limit: int = 200,
    ) -> List[AuditEvent]: ...


class AuditEventBus(Protocol):
    """审计事件总线，二期默认 RocketMQ/ONS 实现。"""
    async def publish(self, event: AuditEvent) -> None: ...


class AuditColdAnalyticsStore(Protocol):
    """长期分析与聚合查询，二期不绑定 ClickHouse。"""
    async def upsert_event(self, event: AuditEvent) -> None: ...
    async def aggregate_cost(
        self,
        tenant_id: str,
        entity_type: str,
        window: str,
    ) -> Dict: ...


class AuditStoreFacade:
    def __init__(
        self,
        wal_store,
        hot_store: AuditHotStore,
        event_bus: AuditEventBus,
        cold_store: AuditColdAnalyticsStore,
    ):
        self._wal = wal_store
        self._hot = hot_store
        self._bus = event_bus
        self._cold = cold_store

    async def append(self, event: AuditEvent) -> None:
        await self._wal.write(event.event_id, event)
        await self._hot.append(event)
        await self._bus.publish(event)
        await self._cold.upsert_event(event)
```

```yaml
# Nacos 配置：审计存储后端选择
audit_store_backend:
  phase: phase2
  hot_store: pg
  event_bus: rocketmq_ons
  cold_analytics_store: pg_compat
  clickhouse_enabled: false

# 三期切换示例：仅替换冷分析实现，不改变业务调用接口
audit_store_backend_phase3:
  hot_store: pg
  event_bus: rocketmq_ons
  cold_analytics_store: clickhouse
  clickhouse_enabled: true
```

---

## 2. 前置条件：一期生产就绪验收门禁

**二期开发不得在一期以下条件未满足时启动**，否则新功能会在不稳定的基座上积累技术债。

| 门禁项 | 验收标准 | 检查方 |
|---|---|---|
| 一期全链路压测通过 | 月末并发场景 P99 < 15s，Error Rate < 1% | 安全/运维 |
| Evaluation 基线已建立 | 标准样例集 + 脱敏真实流量双轨基线存在 | AI 算法 |
| SR 进入稳定运行区间 | 全局请求数 ≥ 1000 + 最近 200 次影子验证不一致率 ≤ 15% | AI 算法 |
| WAL Janitor 稳定运行 ≥ 30 天 | WAL 未同步条目数长期 < 10 | 安全/运维 |
| 一期红蓝对抗演练通过 | Prompt Injection + 越权测试无高危漏洞 | 安全/运维 |
| Patroni HA + Redis Sentinel 验证 | 主节点故障 30s 内自动切换，业务无感知 | 平台架构师 |

---

## 3. 金融尽调 Plan 模式

### 3.1 设计目标与场景

金融尽调（Due Diligence）是二期优先级最高的业务功能。其核心价值在于：将一期已验证的 LangGraph DAG 编排、OCR 文档解析、L2 审计轨道、L3 历史案例检索组合为一套**可版本化、可重复执行的标准化尽调流程**。

典型场景包括：

- **投前尽调**：对目标企业的财务、法务、税务、合规进行多维度核查。
- **贷款审查**：批量核验抵押资产、授信历史、风控评分。
- **监管合规检查**：定期对内部业务线进行合规自查，输出标准化报告。

设计要求继承一期 §1.2.1 原则：**Planner 生成的尽调 DAG 必须通过 Harness 环路检测；外部数据抓取必须经过 ToolLock；审批节点复用 HITL 三段式状态机；所有步骤证据链写入 WAL。**

尽调对象必须在创建 Plan 时显式区分主体类型：

- **企业尽调（`ENTERPRISE`）**：允许访问合规白名单内的 Web Search 与工商、司法、政务等公开数据源，适用于企业财务、法务、税务、合规等多维核查。
- **个人尽调（`INDIVIDUAL`）**：不允许访问 Web Search；仅允许调用人行征信、外部风控、内部私有数据等受控接口，适用于借款用户、担保人等个人主体调查。

主体类型决定模板集合、工具白名单、审计字段与合规策略，不能只依赖用户提示词由模型自行判断。

### 3.2 模板引擎与 Plan 对象模型

#### 3.2.1 Plan 对象模型

```python
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
import time, uuid

class PlanNodeType(Enum):
    """尽调 DAG 节点类型（扩展一期 LangGraph 节点语义）"""
    DOC_COLLECT      = "doc_collect"      # 文档收集（触发 OCR + Claim-Check）
    EVIDENCE_VERIFY  = "evidence_verify"  # 证据核验（对比多源数据一致性）
    EXTERNAL_FETCH   = "external_fetch"   # 外部数据抓取（工商、司法、征信）
    SUB_AGENT_TASK   = "sub_agent_task"   # 企业尽调子 Agent 并行核验任务
    RISK_SCORE       = "risk_score"       # 风险评分（调用 Critic 规则集）
    APPROVAL_GATE    = "approval_gate"    # 审批门（触发 HITL 三段式）
    REPORT_GEN       = "report_gen"       # 报告生成（长上下文主力模型）

class DueDiligenceSubjectType(Enum):
    """尽调主体类型：决定模板、工具白名单与合规策略"""
    ENTERPRISE = "enterprise"   # 企业主体：允许合规白名单内 Web Search
    INDIVIDUAL = "individual"   # 个人主体：禁止 Web Search，仅允许受控征信/风控/内部数据源

@dataclass
class PlanNode:
    """尽调 DAG 节点定义"""
    node_id:        str
    node_type:      PlanNodeType
    title:          str
    skill_id:       str                   # 复用一期 Skill 中心
    dependencies:   List[str]             # 前驱节点 ID 列表
    timeout_s:      int = 300
    max_retry:      int = 2
    required_docs:  List[str] = field(default_factory=list)  # 本节点所需文档类型
    agent_role:     Optional[str] = None                     # sub_agent_task 节点的受控角色标识
    tool_whitelist: List[str] = field(default_factory=list)  # 节点级工具白名单，运行时仍需经过 Harness 校验
    output_schema:  Dict = field(default_factory=dict)        # 输出 JSON Schema

@dataclass
class DueDiligencePlan:
    """尽调计划实体（顶层对象）"""
    plan_id:        str = field(default_factory=lambda: str(uuid.uuid4()))
    template_id:    str = ""              # 来源模板 ID
    template_ver:   str = ""              # 模板版本（防漂移）
    tenant_id:      str = ""
    target_entity:  str = ""              # 被尽调主体（企业名/项目名）
    subject_type:   DueDiligenceSubjectType = DueDiligenceSubjectType.ENTERPRISE
    created_by:     str = ""
    created_at:     float = field(default_factory=time.time)

    nodes:          List[PlanNode] = field(default_factory=list)
    status:         str = "draft"         # draft/running/pending_approval/completed/failed
    risk_summary:   Optional[Dict] = None # 最终风险汇总
    report_uri:     Optional[str] = None  # OSS 报告 URI（Claim-Check）

    # 证据包（所有收集到的文件 URI，Claim-Check 模式）
    evidence_refs:  Dict[str, str] = field(default_factory=dict)
```

#### 3.2.2 模板引擎

尽调模板以 YAML 格式管理，存储于 Nacos，支持版本化与热更新。模板定义节点拓扑，不绑定具体租户数据。

```yaml
# 模板示例: 投前尽调标准流程 v2
id: pre-investment-due-diligence
version: 2.0.0
category: due_diligence
status: published
subject_type: enterprise

metadata:
  title: 投前尽调标准流程
  description: 适用于股权投资前对目标企业的标准化多维核查
  risk_level: high
  estimated_duration_h: 8
  required_roles: [investment_analyst, compliance_officer]

tool_policy:
  allow_web_search: true
  allowed_tools:
    - corp_registry_fetch
    - judicial_risk_fetch
    - gov_credit_fetch
    - web_search
  denied_tools:
    - personal_credit_fetch

nodes:
  - id: n1_corp_register
    type: sub_agent_task
    title: 工商信息核验 Agent
    skill_id: corp-registry-fetch-v1
    agent_role: corp_registry_agent
    tool_whitelist: [corp_registry_fetch, web_search]
    dependencies: []
    timeout_s: 120
    required_docs: []
    output_schema:
      type: object
      required: [company_name, reg_no, legal_rep, reg_capital, status]

  - id: n2_financial_audit
    type: sub_agent_task
    title: 财务核验 Agent
    skill_id: financial-doc-ocr-v2      # 复用一期 OCR Skill
    agent_role: financial_audit_agent
    tool_whitelist: [invoice_ocr, financial_doc_ocr]
    dependencies: []
    timeout_s: 600
    required_docs: [annual_report_3y, audit_report, bank_statement_6m]
    output_schema:
      type: object
      required: [revenue, net_profit, total_assets, debt_ratio]

  - id: n3_legal_check
    type: sub_agent_task
    title: 司法风险核验 Agent
    skill_id: contract-review-v2        # 复用一期合同审查 Skill
    agent_role: judicial_risk_agent
    tool_whitelist: [contract_review, judicial_risk_fetch, web_search]
    dependencies: []
    timeout_s: 300
    required_docs: [articles_of_assoc, major_contracts, litigation_history]

  - id: n4_gov_credit
    type: sub_agent_task
    title: 政务信用核验 Agent
    skill_id: gov-credit-fetch-v1
    agent_role: gov_credit_agent
    tool_whitelist: [gov_credit_fetch, web_search]
    dependencies: []
    timeout_s: 180
    output_schema:
      type: object
      required: [credit_status, administrative_penalties, abnormal_records]

  - id: n5_risk_score
    type: risk_score
    title: 综合风险评分
    skill_id: dd-risk-scorer-v1
    dependencies: [n1_corp_register, n2_financial_audit, n3_legal_check, n4_gov_credit]
    timeout_s: 180

  - id: n6_approval
    type: approval_gate
    title: 投资委员会审批
    skill_id: hitl-approval-v1
    dependencies: [n5_risk_score]
    approval_config:
      risk_level: high
      approver_role: investment_committee
      timeout_h: 24

  - id: n7_report
    type: report_gen
    title: 尽调报告生成
    skill_id: dd-report-gen-v1
    dependencies: [n6_approval]
    timeout_s: 300

release_gate:
  min_evidence_completeness: 0.90    # 证据完整度下限
  max_risk_score: 0.75               # 风险分上限（超过则阻断）
  require_approval: true
```

个人尽调模板必须使用独立模板 ID 与工具策略，禁止复用企业模板后在运行时临时裁剪工具：

```yaml
# 模板示例: 个人授信尽调标准流程 v1
id: individual-credit-due-diligence
version: 1.0.0
category: due_diligence
status: published
subject_type: individual

metadata:
  title: 个人授信尽调标准流程
  description: 适用于借款用户、担保人等个人主体的受控数据核验
  risk_level: high
  estimated_duration_h: 2
  required_roles: [credit_analyst, risk_control_officer]

tool_policy:
  allow_web_search: false
  allowed_tools:
    - personal_credit_fetch
    - external_risk_score_fetch
    - internal_customer_profile_fetch
  denied_tools:
    - web_search
    - corp_registry_fetch
    - gov_credit_fetch

nodes:
  - id: n1_credit_report
    type: external_fetch
    title: 人行征信查询
    skill_id: personal-credit-fetch-v1
    dependencies: []
    timeout_s: 120
    output_schema:
      type: object
      required: [credit_score, overdue_count, loan_balance]

  - id: n2_external_risk
    type: external_fetch
    title: 外部风控核验
    skill_id: external-risk-score-fetch-v1
    dependencies: [n1_credit_report]
    timeout_s: 120

  - id: n3_internal_profile
    type: evidence_verify
    title: 内部客户资料核验
    skill_id: internal-customer-profile-fetch-v1
    dependencies: [n2_external_risk]
    timeout_s: 120

  - id: n4_risk_score
    type: risk_score
    title: 个人授信风险评分
    skill_id: dd-risk-scorer-v1
    dependencies: [n3_internal_profile]
    timeout_s: 180

  - id: n5_report
    type: report_gen
    title: 个人尽调报告生成
    skill_id: dd-report-gen-v1
    dependencies: [n4_risk_score]
    timeout_s: 300
```

主体类型与工具策略由 Nacos 配置中心管理，模板编译时读取，不在代码中硬编码。后续若需要运营后台，可在此配置之上增加管理界面；二期先使用配置化方式降低实现复杂度。

```yaml
# Nacos 配置: due_diligence_subject_policy
enterprise:
  allow_web_search: true
  required_any_skill_ids:
    - corp-registry-fetch-v1
    - judicial-risk-fetch-v1
    - gov-credit-fetch-v1
  denied_skill_ids:
    - personal-credit-fetch-v1

individual:
  allow_web_search: false
  required_any_skill_ids:
    - personal-credit-fetch-v1
    - external-risk-score-fetch-v1
    - internal-customer-profile-fetch-v1
  denied_skill_ids:
    - web_search
    - web-search-v1
    - corp-registry-fetch-v1
    - gov-credit-fetch-v1
```

### 3.3 尽调 DAG 编排扩展

一期 `AgentFastState` 扩展 `due_diligence_plan_id` 字段，将尽调 Plan 以 Claim-Check 方式挂载：

企业尽调多 Agent 并发采用 LangGraph 原生 DAG 分支实现：多个 `sub_agent_task` 节点拥有相同前驱或无前驱时可并行执行，风险评分节点等待全部上游子 Agent 输出后再聚合。子 Agent 设计可参考 CrewAI 的角色/任务分离思想，但不新增第二套编排中枢；Sub-Agent 只是受控节点执行器，必须复用一期 Harness、ToolLock、TokenBudget、WAL/ONS 审计与 Redis Checkpointer。

```python
from typing import TypedDict, Optional, Dict, List, Annotated

class AgentFastState(TypedDict):
    # ── 继承一期全部字段（此处仅列新增字段）──

    # 二期新增：尽调上下文（Claim-Check，不存大对象）
    dd_plan_id:         Optional[str]   # 关联的 DueDiligencePlan.plan_id
    dd_template_id:     Optional[str]   # 关联模板 ID，用于 Evaluation 回放
    dd_current_node:    Optional[str]   # 当前执行节点 ID
    dd_evidence_ready:  bool            # 是否所有必需文件已就绪
    dd_risk_score:      Optional[float] # 最新风险评分（0-1）
    dd_blocked_reason:  Optional[str]   # 阻断原因（供 Critic 携带）


def build_dd_workflow(plan: DueDiligencePlan):
    """
    根据 DueDiligencePlan 动态构建 LangGraph DAG。
    节点拓扑由模板决定，Harness 环路检测在编译前执行。
    """
    from langgraph.graph import StateGraph, END

    validate_dd_subject_policy(plan)

    # 复用一期 detect_cycle 防死锁机制
    dag_dict = {n.node_id: n.dependencies for n in plan.nodes}
    if detect_cycle(dag_dict):
        raise ValueError(f"尽调模板 {plan.template_id} DAG 包含环路，拒绝执行")

    graph = StateGraph(AgentFastState)

    for node in plan.nodes:
        executor = SubAgentExecutor(node) if node.node_type == PlanNodeType.SUB_AGENT_TASK else DDNodeExecutor(node)
        graph.add_node(node.node_id, executor.run)

    # 根据依赖关系连接节点
    entry_nodes = [n for n in plan.nodes if not n.dependencies]
    for entry in entry_nodes:
        graph.set_entry_point(entry.node_id)

    for node in plan.nodes:
        for dep in node.dependencies:
            graph.add_edge(dep, node.node_id)

    # 找到无后继节点作为终态
    all_ids = {n.node_id for n in plan.nodes}
    terminal_nodes = all_ids - {dep for n in plan.nodes for dep in n.dependencies}
    for term in terminal_nodes:
        graph.add_edge(term, END)

    # 复用一期 Redis Checkpointer
    return graph.compile(checkpointer=enterprise_redis_checkpointer)


def validate_dd_subject_policy(plan: DueDiligencePlan) -> None:
    """
    编译 DAG 前校验主体类型与工具策略。
    策略从 Nacos/模板配置读取，不在代码中硬编码工具集合。
    """
    skill_ids = {node.skill_id for node in plan.nodes}
    policy = dd_policy_registry.get_subject_policy(
        tenant_id=plan.tenant_id,
        subject_type=plan.subject_type,
    )

    forbidden = set(policy.denied_skill_ids)
    if skill_ids & forbidden:
        raise ValueError(f"尽调模板包含主体类型禁止使用的工具: {skill_ids & forbidden}")

    required_any = set(policy.required_any_skill_ids)
    if required_any and not (skill_ids & required_any):
        raise ValueError("尽调模板未包含该主体类型要求的至少一个必备工具")


class SubAgentExecutor:
    """
    企业尽调子 Agent 执行器。
    不替换 LangGraph 主工作流，只在单个 DAG 节点内执行受控核验任务。
    """

    def __init__(self, node: PlanNode):
        self._node = node

    async def run(self, state: AgentFastState) -> AgentFastState:
        allowed_tools = await harness.get_allowed_tools(
            tenant_id=state["tenant_id"],
            requested_tools=self._node.tool_whitelist,
        )

        result = await run_sub_agent_task(
            role=self._node.agent_role,
            skill_id=self._node.skill_id,
            allowed_tools=allowed_tools,
            state=state,
            output_schema=self._node.output_schema,
        )

        await wal.write(
            f"dd_sub_agent:{state['dd_plan_id']}:{self._node.node_id}",
            {
                "event": "dd_sub_agent_completed",
                "plan_id": state["dd_plan_id"],
                "node_id": self._node.node_id,
                "agent_role": self._node.agent_role,
                "tool_whitelist": self._node.tool_whitelist,
                "result_ref": result.claim_check_uri,
            },
        )

        return {
            **state,
            "dd_current_node": self._node.node_id,
        }
```

### 3.3.1 受控多 Agent 任务入口

二期提供受控的多 Agent 任务入口，用于从对话中触发已发布模板，而不是开放式 Agent Studio。入口只允许选择平台审核过的 `multi_agent_template_id`，由模板决定主体类型、DAG 拓扑、子 Agent 角色、工具白名单、输出 Schema 与审批策略。

```python
class MultiAgentTaskIntent(Enum):
    """Semantic Router 二期新增意图"""
    ENTERPRISE_DD = "enterprise_due_diligence"   # 企业尽调多 Agent 模板
    INDIVIDUAL_DD = "individual_due_diligence"   # 个人尽调模板


@dataclass
class MultiAgentTaskRequest:
    """受控多 Agent 任务入口请求"""
    tenant_id:      str
    operator_id:    str
    intent:         MultiAgentTaskIntent
    target_entity:  str
    template_id:    str
    subject_type:   DueDiligenceSubjectType
    input_refs:     Dict[str, str] = field(default_factory=dict)  # doc_uri / case_id / customer_id 等 Claim-Check 引用


class MultiAgentTaskGateway:
    """
    对话入口到尽调模板的受控网关。
    只负责任务创建与模板选择，不允许用户自由编辑 Agent 拓扑。
    """

    async def create_plan(self, req: MultiAgentTaskRequest) -> DueDiligencePlan:
        template = await dd_template_registry.load_published(
            tenant_id=req.tenant_id,
            template_id=req.template_id,
            subject_type=req.subject_type,
        )

        if template.intent != req.intent.value:
            raise ValueError("多 Agent 任务意图与模板类型不匹配")

        plan = DueDiligencePlan(
            template_id=template.id,
            template_ver=template.version,
            tenant_id=req.tenant_id,
            target_entity=req.target_entity,
            subject_type=req.subject_type,
            created_by=req.operator_id,
            nodes=template.nodes,
            evidence_refs=req.input_refs,
        )

        validate_dd_subject_policy(plan)
        await dd_plan_store.create(plan)
        return plan
```

受控入口的边界约束：

- 只允许触发已发布模板，不提供自由拖拽、自由新增 Agent、自由配置工具的开放式 Agent Studio。
- 模板发布仍走 Skill 上架审核、工具白名单、Evaluation 回放门禁与租户级灰度。
- 用户输入只能影响 `target_entity`、证据引用、审批人等业务参数，不能直接覆盖 `tool_whitelist`、`agent_role`、`dependencies`。
- 开放式 Agent Studio 作为三期或后续专项评估，不进入二期交付范围。

### 3.4 尽调评分与 Critic 规则集

尽调评分采用**规则引擎（Tier A，零 Token）+ LLM Critic（Tier C，仅在规则不确定时触发）**的双轨模型，与一期 Harness 的 TokenTier 分层一致。

```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class DDRiskRule:
    """单条尽调风险规则（Tier A，零 Token 消耗）"""
    rule_id:    str
    rule_name:  str
    severity:   str       # critical / high / medium / low
    field_path: str       # 检测字段 JSONPath，如 "financial.debt_ratio"
    condition:  str       # 条件描述，如 "> 0.80"
    auto_block: bool      # True = 自动阻断，不走 HITL


# 金融尽调默认规则集（从 Nacos 热加载，支持租户级覆盖）
DEFAULT_DD_RULES: List[DDRiskRule] = [
    DDRiskRule("DD-F001", "资产负债率超警戒线",   "critical", "financial.debt_ratio",      "> 0.80", auto_block=True),
    DDRiskRule("DD-F002", "连续三年净利润为负",   "high",     "financial.net_profit_trend", "all_negative_3y", auto_block=False),
    DDRiskRule("DD-L001", "存在未结诉讼金额超阈值","high",     "legal.pending_litigation",  "> 5000000", auto_block=False),
    DDRiskRule("DD-C001", "工商状态异常",         "critical", "corp.status",               "!= '存续'", auto_block=True),
    DDRiskRule("DD-C002", "实控人变更频繁",       "medium",   "corp.controller_changes",   "> 2_in_3y", auto_block=False),
]


class DDCriticEngine:
    """
    双轨尽调评分引擎
    Tier A: 规则引擎（确定性，零 Token）
    Tier C: LLM Critic（仅在规则结果有歧义或需要综合解释时触发）
    """

    def __init__(self, rules: List[DDRiskRule], token_guard, llm_client):
        self._rules = rules
        self._token_guard = token_guard
        self._llm = llm_client

    async def evaluate(self, evidence: dict, plan_id: str) -> dict:
        """
        评估证据包，返回风险报告。
        auto_block 规则触发时直接映射到 AgentFailureState.FAILED_CLOSED。
        非确定性规则触发时调用 LLM Critic（Tier C）。
        """
        rule_hits = []
        uncertain_items = []
        max_severity = "low"

        for rule in self._rules:
            result = evaluate_rule(rule, evidence)
            if result.triggered:
                rule_hits.append({
                    "rule_id": rule.rule_id,
                    "rule_name": rule.rule_name,
                    "severity": rule.severity,
                    "auto_block": rule.auto_block,
                    "evidence": result.evidence_snippet,
                })
                if rule.severity in ("critical", "high"):
                    max_severity = rule.severity
                if not rule.auto_block and rule.severity in ("critical", "high"):
                    uncertain_items.append(rule)

        # Tier C: 仅对需要综合解读的高风险项调用 LLM
        llm_analysis = None
        if uncertain_items:
            await self._token_guard.consume(
                tokens=800,
                tier=TokenTier.TIER_C,
                operation="dd_critic_analysis",
                operation_id=f"dd_critic:{plan_id}",
            )
            llm_analysis = await self._llm.analyze_risks(
                evidence=evidence,
                triggered_rules=uncertain_items,
            )

        # 综合评分（0=低风险，1=高风险）
        score = compute_risk_score(rule_hits, llm_analysis)

        return {
            "plan_id":      plan_id,
            "risk_score":   score,
            "max_severity": max_severity,
            "rule_hits":    rule_hits,
            "llm_analysis": llm_analysis,
            "auto_block":   any(r["auto_block"] for r in rule_hits),
            "requires_hitl": any(
                not r["auto_block"] and r["severity"] in ("critical", "high")
                for r in rule_hits
            ),
        }
```

### 3.4.1 运行时 Reflection 检查点

二期将 Reflection 作为 Critic 的运行时检查点显式纳入尽调流程，但不引入新的自治规划框架。Reflection 只允许基于结构化证据、工具输出摘要、规则命中结果和报告草稿给出校验结论；是否重试、阻断或进入 HITL 由固定策略决定，不由模型自由决定。

四类检查点：

- **规划反思（planning_reflection）**：在 DAG 编译后、执行前检查主体类型、依赖关系、必备节点、工具白名单和预算是否匹配模板策略。
- **工具结果反思（tool_result_reflection）**：每个 `sub_agent_task` / `external_fetch` 节点完成后，检查输出 Schema、证据完整性、来源可信度与 Claim-Check URI 是否满足要求。
- **风险反思（risk_reflection）**：`risk_score` 节点后检查规则命中、LLM Critic 结论、自动阻断与 HITL 分流是否一致。
- **最终报告反思（report_reflection）**：`report_gen` 节点后检查报告字段覆盖率、引用证据链、敏感信息脱敏和审批摘要是否完整。

```python
class ReflectionStage(Enum):
    PLANNING    = "planning_reflection"
    TOOL_RESULT = "tool_result_reflection"
    RISK        = "risk_reflection"
    REPORT      = "report_reflection"


@dataclass
class ReflectionRecord:
    plan_id:       str
    node_id:       str
    stage:         ReflectionStage
    passed:        bool
    severity:      str                 # low / medium / high / critical
    findings:      List[str]
    action:        str                 # pass / retry / hitl / failed_closed
    evidence_refs: List[str] = field(default_factory=list)


class DDReflectionGate:
    """
    尽调运行时反思门。
    复用 DDCriticEngine、Evaluation 指标和 AuditStoreFacade，不替换 LangGraph 编排。
    """

    def __init__(self, critic_engine, audit_store: AuditStoreFacade, token_guard):
        self._critic = critic_engine
        self._audit = audit_store
        self._token_guard = token_guard

    async def reflect_planning(self, plan: DueDiligencePlan) -> ReflectionRecord:
        findings = []
        try:
            validate_dd_subject_policy(plan)
            if detect_cycle({n.node_id: n.dependencies for n in plan.nodes}):
                findings.append("DAG 包含环路")
        except Exception as exc:
            findings.append(str(exc))

        return await self._record(
            plan_id=plan.plan_id,
            node_id="__plan__",
            stage=ReflectionStage.PLANNING,
            findings=findings,
            action="failed_closed" if findings else "pass",
        )

    async def reflect_tool_result(
        self,
        plan_id: str,
        node: PlanNode,
        result: dict,
    ) -> ReflectionRecord:
        findings = validate_output_schema(node.output_schema, result)
        if not result.get("claim_check_uri"):
            findings.append("缺少 Claim-Check 结果引用")

        action = "pass"
        if findings and node.max_retry > 0:
            action = "retry"
        elif findings:
            action = "hitl"

        return await self._record(plan_id, node.node_id, ReflectionStage.TOOL_RESULT, findings, action)

    async def reflect_risk(self, risk_result: dict) -> ReflectionRecord:
        findings = []
        if risk_result["auto_block"] and risk_result["requires_hitl"]:
            findings.append("自动阻断与 HITL 分流同时触发，需要人工复核")
        if risk_result["risk_score"] >= 0.75 and not risk_result["rule_hits"]:
            findings.append("高风险评分缺少规则命中证据")

        action = "hitl" if findings else "pass"
        return await self._record(
            risk_result["plan_id"],
            "risk_score",
            ReflectionStage.RISK,
            findings,
            action,
        )

    async def reflect_report(self, plan_id: str, report: dict) -> ReflectionRecord:
        findings = []
        required_fields = {"summary", "risk_score", "evidence_refs", "approval_summary"}
        missing = required_fields - set(report.keys())
        if missing:
            findings.append(f"报告缺少必填字段: {sorted(missing)}")
        if not report.get("evidence_refs"):
            findings.append("报告缺少证据链引用")

        action = "hitl" if findings else "pass"
        return await self._record(plan_id, "report_gen", ReflectionStage.REPORT, findings, action)

    async def _record(
        self,
        plan_id: str,
        node_id: str,
        stage: ReflectionStage,
        findings: List[str],
        action: str,
    ) -> ReflectionRecord:
        record = ReflectionRecord(
            plan_id=plan_id,
            node_id=node_id,
            stage=stage,
            passed=(action == "pass"),
            severity="high" if action in ("hitl", "failed_closed") else "low",
            findings=findings,
            action=action,
        )
        await self._audit.append(AuditEvent(
            event_id=f"dd_reflection:{plan_id}:{node_id}:{stage.value}",
            tenant_id=current_tenant_id(),
            event_type=stage.value,
            entity_type="dd_plan",
            entity_id=plan_id,
            payload_hash=sha256(json.dumps(asdict(record), ensure_ascii=False)),
            payload_uri=None,
            operator_id="system",
            occurred_at=time.time(),
        ))
        return record
```

Reflection 的执行边界：

- 规划反思只能阻断非法模板或回到模板配置修正，不允许模型临时新增工具、节点或依赖关系。
- 工具结果反思最多触发节点级有限重试；超过重试次数进入 HITL，不进行无限自循环。
- 风险反思只校验规则、证据与评分一致性，不替代 `DDCriticEngine` 的确定性规则。
- 报告反思只检查字段完整性、引用链和脱敏，不生成新的事实。
- 所有 Reflection 记录进入 `AuditStoreFacade`，并纳入 Evaluation 回放样例。

### 3.5 合规存档与报告输出

尽调报告涉及监管存档要求，存储策略与一期 Claim-Check 模式对齐：

```
尽调报告存储策略
  ├─ 证据原件（发票、合同、财报扫描件）
  │    └─ OSS: dd-evidence/{tenant_id}/{plan_id}/{doc_id}
  │         ├─ KMS 加密（租户密钥）
  │         └─ 保留期：7年（监管要求）
  │
  ├─ 结构化证据提取结果（OCR 输出 JSON）
  │    └─ OSS: dd-structured/{tenant_id}/{plan_id}/{node_id}.json
  │
  ├─ 风险评分报告（每次执行生成）
  │    └─ PG: dd_risk_report 表（含规则命中明细 + LLM 分析摘要）
  │         └─ 异步 → RocketMQ/ONS → AuditColdAnalyticsStore（合规轨；二期 PG，三期 ClickHouse）
  │
  ├─ 最终尽调报告（PDF/DOCX）
  │    └─ OSS: dd-reports/{tenant_id}/{plan_id}/report_v{n}.pdf
  │         └─ report_uri 写回 DueDiligencePlan.report_uri
  │
  └─ 完整审计证据链（WAL）
       └─ 每个节点的输入参数快照 + 输出结果指纹 + 操作人 + 时间戳
```

尽调审计写入统一通过 §1.4 `AuditStoreFacade` 完成，尽调业务代码只提交结构化 `AuditEvent`，不直接绑定 ClickHouse 或 PG 的物理表实现。

二期 PG 审计表（通过 `AuditHotStore` 写入）：

```sql
-- 新增尽调专项审计表
CREATE TABLE dd_plan_audit (
    id           UUID PRIMARY KEY,
    plan_id      UUID NOT NULL,
    tenant_id    TEXT NOT NULL,
    node_id      TEXT NOT NULL,
    node_type    TEXT NOT NULL CHECK (
        node_type IN ('doc_collect','evidence_verify','external_fetch',
                      'risk_score','approval_gate','report_gen')
    ),
    input_hash   TEXT NOT NULL,       -- 输入参数 SHA256（不存原文，防敏感信息泄露）
    output_uri   TEXT,                -- OSS URI（Claim-Check）
    risk_score   NUMERIC(6, 4),
    rule_hits    JSONB NOT NULL DEFAULT '[]'::jsonb,
    duration_ms  INTEGER NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('success','failed','hitl_pending','blocked')),
    operator_id  TEXT NOT NULL,
    ts           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_dd_plan_audit_tenant_plan_ts
    ON dd_plan_audit (tenant_id, plan_id, ts DESC);
```

三期接入 ClickHouse 时，`dd_plan_audit` 可迁移为 MergeTree/ReplicatedMergeTree 表，并由 `AuditColdAnalyticsStore` 消费 RocketMQ/ONS 审计事件异步写入；业务代码不感知迁移。

### 3.6 尽调 Skill 元数据规范

```yaml
# 尽调风险评分 Skill
id: dd-risk-scorer-v1
version: 1.0.0
category: due_diligence
status: published
risk_score: 0.10

spec:
  model_provider: deepseek-v3
  prompt_version: p-dd-risk-001
  harness_required: true
  scratchpad_enabled: true
  token_budget_complexity: moderate   # 20,000 tokens

runtime:
  sandbox_tier: CONTAINER
  vector_collection: skills_dd_history   # 历史尽调案例库（L3）
  max_qps: 5
  timeout: 180s
  max_retry: 2

distribution:
  allowed_tenants: [investment_div, risk_management]
  deployment_strategy: canary
  canary_weight: 20%
  auto_promote_threshold: 99.0%

observability:
  alert_on_error_rate: 3%
  alert_on_p99_latency: 60s
  auto_circuit_break: true

# 尽调评估专项指标（扩展一期 Evaluation Layer）
evaluation:
  required_metrics:
    - evidence_completeness_rate    # 证据完整度，≥ 0.90
    - rule_hit_precision            # 规则命中精确率，≥ 0.95
    - reflection_pass_rate          # 运行时反思通过率，≥ 0.95
    - report_field_coverage         # 报告字段覆盖率，≥ 0.90
    - hitl_escalation_rate          # HITL 上报率（监控趋势，无硬门禁）
```

---

## 4. 协同能力（Collaboration）

### 4.1 设计边界与分阶段原则

协同能力严格遵循**最小可用原则**，分两个阶段交付：

**阶段一（二期交付）**：只读共享 + 评论 + 多人审批通知。不支持并发写入任何 Agent 执行状态。

**阶段二（三期评估）**：协同写入（乐观锁 + 冲突解决）。在一期 L2 事件源机制充分验证后，再评估是否引入 CRDT。

> **阶段一边界声明**：任何涉及修改 `AgentFastState` 或 `DueDiligencePlan` 的操作，只允许执行人（线程发起者）进行。其他协作者只能添加评论、标注、审批意见，不能直接修改执行状态。冲突语义问题推迟到阶段二解决。

协同默认触发点来自尽调流程，而不是依赖用户手动分享。企业尽调 `REPORT_GEN` 节点完成后，系统读取 `DueDiligencePlan.approval_config` 与模板中的审批角色，将报告 URI、风险评分和规则命中摘要生成协同审批上下文，自动创建 `ThreadShareRecord` 与 HITL 审批任务，并向审批人发送 IM 通知。

```
REPORT_GEN 完成
  └─ 写入 dd_report_generated 审计事件
      └─ CollabApprovalOrchestrator 消费事件
          ├─ 创建/更新 ThreadShareRecord（read_only=true, can_approve=true）
          ├─ 创建 HITL 审批任务（approval_record）
          ├─ 推送报告 URI + 风险评分 + 关键规则命中
          └─ 审批结果回写 HITL 状态机，不直接改 AgentFastState
```

### 4.2 共享线程与可见性模型

```python
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum
import time, uuid

class ThreadVisibility(Enum):
    PRIVATE   = "private"    # 仅发起人可见（默认）
    TEAM      = "team"       # 同租户同团队可见
    TENANT    = "tenant"     # 全租户可见（需审批）
    SHARED    = "shared"     # 指定人员列表可见

@dataclass
class ThreadShareRecord:
    """
    线程共享记录。
    不修改 AgentFastState，以独立表管理可见性。
    """
    share_id:     str = field(default_factory=lambda: str(uuid.uuid4()))
    thread_id:    str = ""
    tenant_id:    str = ""
    owner_id:     str = ""                  # 线程发起人
    visibility:   ThreadVisibility = ThreadVisibility.PRIVATE
    shared_with:  List[str] = field(default_factory=list)  # user_id 列表
    shared_at:    float = field(default_factory=time.time)
    expires_at:   Optional[float] = None    # None = 永不过期
    read_only:    bool = True               # 阶段一强制 True

    # 权限细粒度（ABAC 扩展）
    can_comment:  bool = True
    can_annotate: bool = True              # 标注节点（不修改执行状态）
    can_approve:  bool = False             # 是否可参与 HITL 审批
```

PG 表设计：

```sql
CREATE TABLE thread_shares (
    share_id    UUID PRIMARY KEY,
    thread_id   TEXT NOT NULL,
    tenant_id   TEXT NOT NULL,
    owner_id    TEXT NOT NULL,
    visibility  TEXT NOT NULL DEFAULT 'private',
    shared_with TEXT[] DEFAULT '{}',
    read_only   BOOLEAN NOT NULL DEFAULT TRUE,
    can_comment BOOLEAN NOT NULL DEFAULT TRUE,
    can_approve BOOLEAN NOT NULL DEFAULT FALSE,
    shared_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ
);

-- RLS：只有 owner 或 shared_with 成员可见
ALTER TABLE thread_shares ENABLE ROW LEVEL SECURITY;
CREATE POLICY thread_shares_isolation ON thread_shares
USING (
    tenant_id = current_setting('app.current_tenant')::text
    AND (
        owner_id = current_setting('app.current_user')::text
        OR current_setting('app.current_user')::text = ANY(shared_with)
    )
);
```

### 4.3 评论与标注服务

```python
from dataclasses import dataclass, field
from typing import Optional, List
import time, uuid

class CommentTargetType(Enum):
    THREAD      = "thread"        # 整个线程
    NODE        = "node"          # DAG 中的某个节点
    DD_EVIDENCE = "dd_evidence"   # 尽调证据项
    HITL_RECORD = "hitl_record"   # 审批记录

@dataclass
class ThreadComment:
    """
    评论实体。
    评论只读（发布后不可修改内容，只能逻辑删除），保证审计完整性。
    """
    comment_id:    str = field(default_factory=lambda: str(uuid.uuid4()))
    thread_id:     str = ""
    tenant_id:     str = ""
    author_id:     str = ""
    target_type:   CommentTargetType = CommentTargetType.THREAD
    target_id:     str = ""              # 对应 node_id / evidence_id 等
    content:       str = ""
    content_type:  str = "text"          # text / markdown
    parent_id:     Optional[str] = None  # 回复关系
    created_at:    float = field(default_factory=time.time)
    is_deleted:    bool = False          # 软删除，不物理删除（审计要求）
    attachments:   List[str] = field(default_factory=list)  # OSS URI 列表（Claim-Check）


class CommentService:
    """
    评论服务。
    写入走 WAL + RocketMQ/ONS → AuditHotStore 审计轨，不走 L2 事件源（避免污染 Agent 状态流）。
    """

    def __init__(self, pg_store, wal_store, rocket_producer, abac_service):
        self._pg = pg_store
        self._wal = wal_store
        self._rocket = rocket_producer
        self._abac = abac_service

    async def add_comment(self, comment: ThreadComment) -> str:
        # 权限检查：确认作者对该线程有 can_comment 权限
        share = await self._pg.get_share_record(comment.thread_id, comment.author_id)
        if not share or not share.can_comment:
            raise PermissionError(f"用户 {comment.author_id} 对线程 {comment.thread_id} 无评论权限")

        # 写入 PG
        await self._pg.insert_comment(comment)

        # WAL 先落盘，再异步发 RocketMQ/ONS
        entry_id = f"comment:{comment.comment_id}"
        await self._wal.write(entry_id, {
            "event_type": "comment_added",
            "comment_id": comment.comment_id,
            "thread_id":  comment.thread_id,
            "tenant_id":  comment.tenant_id,
            "author_id":  comment.author_id,
            "target_type": comment.target_type.value,
            "ts": comment.created_at,
        })
        asyncio.create_task(self._rocket.send("agent_collab_events", {
            "type": "comment_added",
            "payload": asdict(comment),
        }))

        return comment.comment_id
```

### 4.4 通知与审批桥接

一期 `HITLApprovalStateMachine` 已支持飞书/钉钉单人审批卡片。二期扩展**多人审批通知**（不改核心状态机）：

```python
class CollabNotificationExtension:
    """
    协同通知扩展（一期 HITL 状态机的通知增强层）。
    不修改 HITLApprovalStateMachine 核心逻辑，以装饰器模式挂载。
    """

    def __init__(self, hitl_machine, im_client, share_service):
        self._hitl = hitl_machine
        self._im = im_client
        self._share = share_service

    async def notify_collaborators_on_hitl(
        self, thread_id: str, approval_record, event_type: str
    ) -> None:
        """
        在 HITL 状态变更时，同步通知所有协作者（只读通知，不赋予审批权限）。
        """
        shares = await self._share.get_active_shares(thread_id)
        collaborators = [
            uid for share in shares
            for uid in share.shared_with
            if uid != approval_record.approver_id  # 避免重复通知审批人
        ]

        if not collaborators:
            return

        message = self._build_notify_message(approval_record, event_type)
        for uid in collaborators:
            asyncio.create_task(
                self._im.send_notification(to=uid, message=message)
            )

    def _build_notify_message(self, record, event_type: str) -> str:
        event_map = {
            "submitted":    f"任务「{record.task_summary[:40]}」已提交审批，等待 {record.approver_id} 决策。",
            "approved":     f"任务「{record.task_summary[:40]}」已获批准。",
            "rejected":     f"任务「{record.task_summary[:40]}」被否决，请查看原因。",
            "timeout_veto": f"任务「{record.task_summary[:40]}」审批超时，已自动否决。",
        }
        return event_map.get(event_type, f"任务状态变更：{event_type}")
```

尽调报告完成后的自动协同审批由独立编排器承接，避免把协同逻辑塞回 LangGraph 节点内部：

```python
@dataclass
class DDReportGeneratedEvent:
    tenant_id:    str
    thread_id:    str
    plan_id:      str
    report_uri:   str
    risk_score:   float
    rule_hits:    List[str]
    owner_id:     str
    approver_ids: List[str]


class CollabApprovalOrchestrator:
    """
    尽调报告生成后的协同审批编排器。
    消费 dd_report_generated 事件，创建共享记录与 HITL 审批任务。
    """

    def __init__(
        self,
        share_service,
        hitl_machine,
        notification_ext: CollabNotificationExtension,
        audit_store: AuditStoreFacade,
    ):
        self._share = share_service
        self._hitl = hitl_machine
        self._notify = notification_ext
        self._audit = audit_store

    async def on_dd_report_generated(self, event: DDReportGeneratedEvent) -> None:
        if not event.approver_ids:
            return

        share = await self._share.create_or_update_share(
            thread_id=event.thread_id,
            tenant_id=event.tenant_id,
            owner_id=event.owner_id,
            shared_with=event.approver_ids,
            read_only=True,
            can_comment=True,
            can_annotate=True,
            can_approve=True,
        )

        approval_record = await self._hitl.submit(
            thread_id=event.thread_id,
            tenant_id=event.tenant_id,
            task_summary=f"尽调报告审批：plan={event.plan_id}, risk_score={event.risk_score}",
            approver_ids=event.approver_ids,
            payload_ref=event.report_uri,
            metadata={
                "plan_id": event.plan_id,
                "risk_score": event.risk_score,
                "rule_hits": event.rule_hits,
                "share_id": share.share_id,
            },
        )

        await self._audit.append(AuditEvent(
            event_id=f"collab_approval:{approval_record.approval_id}",
            tenant_id=event.tenant_id,
            event_type="collab_approval_created",
            entity_type="dd_plan",
            entity_id=event.plan_id,
            payload_hash=sha256(event.report_uri),
            payload_uri=event.report_uri,
            operator_id=event.owner_id,
            occurred_at=time.time(),
        ))

        await self._notify.notify_collaborators_on_hitl(
            thread_id=event.thread_id,
            approval_record=approval_record,
            event_type="submitted",
        )
```

### 4.5 冲突语义与乐观并发（阶段一约束）

阶段一禁止对 `AgentFastState` 并发写入，原因如下：

LangGraph 的状态更新是单写线程模型——每次节点执行都以 `checkpoint` 的方式落 Redis，多个用户同时修改执行状态会导致 `checkpoint` 版本冲突，触发不可预期的 DAG 重规划，进而产生额外 LLM 调用和 Token 超支。

**阶段一实现约束**：

```python
class ThreadWriteGuard:
    """
    阶段一写入守卫：只允许线程所有者修改执行状态。
    协作者对 AgentFastState 的修改请求直接拒绝并返回 409。
    """

    @staticmethod
    async def check_write_permission(
        thread_id: str, user_id: str, pg_store
    ) -> None:
        share = await pg_store.get_thread_owner(thread_id)
        if share.owner_id != user_id:
            raise PermissionError(
                f"阶段一协同限制：仅线程所有者 {share.owner_id} 可修改执行状态。"
                f"用户 {user_id} 可添加评论或标注，但不能修改执行状态。"
                f"并发写入支持计划在三期评估后引入。"
            )
```

---

## 5. Web Search（受控实时检索）

### 5.1 合规前置：金融场景网络访问约束

> **强制要求：Web Search 功能的合规审查必须在开发启动前完成，而不是并行推进。**

在金融私有化部署环境下，访问外部 URL 涉及以下合规维度，任一不满足则该功能不得上线：

| 合规维度 | 要求 | 检查方 |
|---|---|---|
| 数据不出境 | 检索流量经由内部网络出口，日志留存在境内 | 安全/运维 + 合规团队 |
| 访问白名单 | 仅允许访问经合规团队审核的域名白名单，默认拒绝 | 合规团队 |
| 访问留证 | 每次检索的 URL、响应摘要、时间戳、操作人写入不可篡改审计轨 | Harness + WAL |
| 版权与爬虫协议 | 不得违反目标站点的 robots.txt 协议；不存储原文，只存结构化摘要 | 合规团队 |
| 检索结果隔离 | 检索结果不得跨租户共享；不得写入共享向量库 | 平台架构师 |

合规审查通过后，以下实施方案方可启动。

### 5.2 独立对话入口

Web Search 在二期同时作为尽调内部 Tool 和独立对话能力提供。独立入口不绕过 Skill 中心，也不直接暴露 Search API；用户在对话中触发搜索意图后，由 Semantic Router 路由到 `web_search` Skill，再通过 `ThinToolInterceptor`、域名白名单、TokenBudget 与 WAL/ONS 审计执行。

```python
class WebSearchIntent(Enum):
    """Semantic Router 二期新增意图"""
    WEB_SEARCH = "web_search"


@dataclass
class WebSearchRequest:
    """独立 Web Search 对话入口请求"""
    tenant_id:     str
    operator_id:   str
    thread_id:     str
    query:         str
    max_results:   int = 5
    persist_to_l3: bool = False  # 默认不写入 L3，需走 5.6 准入策略


@dataclass
class WebSearchResponse:
    """前端可直接渲染的检索响应"""
    query_hash:    str
    results:       List[SearchResult]
    no_result:     bool = False
    blocked_reason: Optional[str] = None


class WebSearchConversationGateway:
    """
    对话入口到 WebSearchTool 的受控网关。
    只负责任务入口、审计与结果包装；检索执行仍由 WebSearchTool 完成。
    """

    async def invoke(self, req: WebSearchRequest) -> WebSearchResponse:
        allowed_tools = await harness.get_allowed_tools(
            tenant_id=req.tenant_id,
            requested_tools=["web_search"],
        )
        if "web_search" not in allowed_tools:
            return WebSearchResponse(
                query_hash=sha256(req.query),
                results=[],
                no_result=True,
                blocked_reason="web_search_not_allowed_for_tenant",
            )

        trace_id = f"web_search:{req.thread_id}:{sha256(req.query)[:12]}"
        results = await web_search_tool.search(
            query=req.query,
            tenant_id=req.tenant_id,
            operator_id=req.operator_id,
            trace_id=trace_id,
            max_results=req.max_results,
        )

        return WebSearchResponse(
            query_hash=sha256(req.query),
            results=results,
            no_result=(len(results) == 0),
        )
```

前端渲染要求：

- 每条结果展示 `title`、`source_domain`、`credibility`、`retrieved_at` 与不超过 500 字符的 `snippet`。
- 引用使用结构化结果编号，不展示完整网页正文，不缓存不可控原文。
- 无白名单内结果时展示“未命中合规白名单来源”，不回退到未受控外网搜索。
- 搜索结果默认只进入当前线程上下文；写入 L3 必须走 §5.6 的高可信度 + HITL 确认准入。

### 5.3 检索工具架构

Web Search 以标准 Skill 形式接入 Skill 中心，通过 `ThinToolInterceptor` 受 Harness 管控：

```python
from dataclasses import dataclass
from typing import List, Optional, Dict

@dataclass
class SearchResult:
    """单条检索结果（结构化，不存原文）"""
    url:           str
    title:         str
    snippet:       str               # 摘要（≤ 500 字符）
    source_domain: str
    credibility:   float             # 来源可信度评分（0-1）
    retrieved_at:  float
    cache_key:     Optional[str] = None  # 命中缓存时的 key


class WebSearchTool:
    """
    受控 Web 检索工具。
    架构：合规白名单 → 缓存层 → Brave/Bing API → 结果过滤 → 可信度评分
    不支持 headless 浏览器（二期）；headless 浏览器沙箱在后续评估。
    """

    ALLOWED_DOMAINS_KEY = "web_search:allowed_domains:{tenant_id}"
    CACHE_TTL_SECONDS   = 3600      # 检索结果缓存 1 小时
    MAX_RESULTS         = 10
    SNIPPET_MAX_CHARS   = 500

    def __init__(
        self,
        search_api_client,           # Brave Search API / Bing API
        redis_client,
        wal_store,
        credibility_scorer,
        domain_registry,             # 从 Nacos 热加载合规白名单
    ):
        self._api = search_api_client
        self._redis = redis_client
        self._wal = wal_store
        self._scorer = credibility_scorer
        self._domains = domain_registry

    async def search(
        self,
        query: str,
        tenant_id: str,
        operator_id: str,
        trace_id: str,
        max_results: int = 5,
    ) -> List[SearchResult]:
        """
        执行受控检索。
        1. 白名单过滤（Tier A，零 Token）
        2. 缓存命中检查
        3. 调用 Search API
        4. 结果过滤 + 可信度评分
        5. 审计写入（WAL + RocketMQ/ONS）
        """
        # ── 1. 审计意图写入（先于任何网络请求）──
        audit_entry = {
            "event": "web_search_initiated",
            "query_hash": hashlib.sha256(query.encode()).hexdigest(),
            "redacted_query": pii_gateway.redact(query),
            "tenant_id": tenant_id,
            "operator_id": operator_id,
            "trace_id": trace_id,
            "ts": time.time(),
        }
        await self._wal.write(f"ws:{trace_id}", audit_entry)

        # ── 2. 缓存命中 ──
        cache_key = f"ws_cache:{tenant_id}:{hashlib.sha256(query.encode()).hexdigest()[:16]}"
        cached = await self._redis.get(cache_key)
        if cached:
            results = [SearchResult(**r) for r in json.loads(cached)]
            await self._audit_result(trace_id, results, cache_hit=True)
            return results

        # ── 3. 调用 Search API ──
        raw_results = await self._api.search(query, count=self.MAX_RESULTS)

        # ── 4. 过滤：仅保留白名单域名 ──
        allowed = await self._domains.get_allowed(tenant_id)
        filtered = [
            r for r in raw_results
            if any(r.url.startswith(f"https://{d}") for d in allowed)
        ]

        if not filtered:
            # 无白名单内结果，返回空列表并告警
            asyncio.create_task(self._wal.write(
                f"ws_no_result:{trace_id}",
                {**audit_entry, "event": "web_search_no_whitelist_result"}
            ))
            return []

        # ── 5. 可信度评分 + 截断摘要 ──
        results = []
        for r in filtered[:max_results]:
            score = await self._scorer.score(r.source_domain)
            results.append(SearchResult(
                url=r.url,
                title=r.title[:200],
                snippet=r.snippet[:self.SNIPPET_MAX_CHARS],
                source_domain=r.source_domain,
                credibility=score,
                retrieved_at=time.time(),
                cache_key=cache_key,
            ))

        # ── 6. 写缓存（结构化摘要，不存原文）──
        await self._redis.setex(
            cache_key,
            self.CACHE_TTL_SECONDS,
            json.dumps([asdict(r) for r in results], ensure_ascii=False),
        )

        await self._audit_result(trace_id, results, cache_hit=False)
        return results

    async def _audit_result(
        self, trace_id: str, results: List[SearchResult], cache_hit: bool
    ) -> None:
        asyncio.create_task(self._wal.write(
            f"ws_result:{trace_id}",
            {
                "event": "web_search_completed",
                "trace_id": trace_id,
                "cache_hit": cache_hit,
                "result_count": len(results),
                "domains": [r.source_domain for r in results],
                "ts": time.time(),
            }
        ))
```

### 5.4 沙箱隔离：Playwright 专属 Profile（后续评估）

二期先使用 Search API（Brave/Bing），不启用 headless 浏览器。以下为后续 Playwright 沙箱设计预案，供架构评审：

```yaml
# 后续预案：Playwright headless 沙箱 Profile（不在二期交付）
sandbox_profile: web_search_headless
runtime_class: gvisor              # 强隔离，防逃逸
network_policy:
  egress:
    - allowed_domains: ${WEB_SEARCH_WHITELIST}   # 从 Nacos 注入
    - deny_all: true               # 默认拒绝所有出站流量
  ingress:
    - deny_all: true               # 无入站
resource_limits:
  cpu: "1"
  memory: "1Gi"
  timeout_s: 30                    # 单次页面加载超时
chromium_flags:
  - --no-sandbox                   # gVisor 已提供内核级隔离
  - --disable-gpu
  - --disable-extensions
  - --disable-dev-shm-usage
  - --js-flags=--max-old-space-size=512
pool:
  min_idle: 2
  max_size: 10
  # 注意：此预热池独立于一期 runc_pool，不共享资源配额
```

### 5.5 结果处理：可信度打分与 Reranker

```python
class SearchResultReranker:
    """
    检索结果二次排序。
    复用一期 BGE-Reranker，在语义相关性基础上叠加来源可信度权重。
    """

    CREDIBILITY_WEIGHTS = {
        "gov.cn":    0.95,
        "csrc.gov.cn": 0.95,       # 证监会
        "pbc.gov.cn":  0.95,       # 央行
        "reuters.com": 0.85,
        "bloomberg.com": 0.85,
        "xinhua.net":  0.80,
        "_default":    0.50,
    }

    def __init__(self, bge_reranker):
        self._reranker = bge_reranker

    async def rerank(
        self, query: str, results: List[SearchResult], top_k: int = 3
    ) -> List[SearchResult]:
        # BGE 语义相关性评分（复用一期组件）
        semantic_scores = await self._reranker.score(
            query=query,
            passages=[r.snippet for r in results],
        )

        # 叠加来源可信度权重
        final_scores = []
        for i, result in enumerate(results):
            domain = result.source_domain
            cred = self.CREDIBILITY_WEIGHTS.get(
                domain,
                self.CREDIBILITY_WEIGHTS["_default"]
            )
            # 语义分 70% + 可信度 30%
            combined = semantic_scores[i] * 0.70 + cred * 0.30
            final_scores.append((combined, result))

        final_scores.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in final_scores[:top_k]]
```

### 5.6 检索结果进入 L3 记忆的策略

Web Search 结果不得直接写入全局 L3 向量库，防止外部不可控内容污染金融知识库：

```python
class SearchToMemoryPolicy:
    """
    检索结果写入 L3 记忆的准入策略。
    仅高可信度、经人工确认的结果才允许进入向量库。
    """

    CREDIBILITY_THRESHOLD = 0.80   # 低于此分的结果禁止写入 L3
    REQUIRE_HUMAN_CONFIRM = True   # 强制要求人工确认后才写入（二期默认开启）

    @staticmethod
    async def can_persist(result: SearchResult, hitl_machine) -> bool:
        if result.credibility < SearchToMemoryPolicy.CREDIBILITY_THRESHOLD:
            return False
        if SearchToMemoryPolicy.REQUIRE_HUMAN_CONFIRM:
            # 触发轻量级 HITL（normal 级别，24h 超时）
            # 复用一期 HITLApprovalStateMachine
            return await hitl_machine.quick_confirm(
                summary=f"是否将「{result.title}」写入知识库？\n来源: {result.url}",
                risk_level="normal",
            )
        return True
```

---

## 6. 看板（Kanban）

### 6.1 数据模型：Board / Column / Card

```sql
-- Board: 看板（一个项目/租户一个看板）
CREATE TABLE kanban_boards (
    board_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   TEXT NOT NULL,
    title       TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Column: 列（对应 AgentFastState.stage 的映射）
CREATE TABLE kanban_columns (
    column_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    board_id    UUID REFERENCES kanban_boards(board_id),
    title       TEXT NOT NULL,
    position    INT  NOT NULL,
    stage_map   TEXT[]            -- 映射的 AgentFastState.stage 值列表
);

-- Card: 卡片（每个 thread_id 对应一张卡片）
CREATE TABLE kanban_cards (
    card_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    board_id    UUID REFERENCES kanban_boards(board_id),
    column_id   UUID REFERENCES kanban_columns(column_id),
    thread_id   TEXT NOT NULL UNIQUE,   -- 对应一期 thread_id
    tenant_id   TEXT NOT NULL,
    title       TEXT NOT NULL,
    skill_id    TEXT,
    assignee_id TEXT,
    priority    TEXT DEFAULT 'normal',  -- low/normal/high/urgent
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata    JSONB DEFAULT '{}'      -- 扩展字段（尽调 plan_id 等）
);

-- Card watchers: 关注者（接收状态变更通知）
CREATE TABLE card_watchers (
    card_id     UUID REFERENCES kanban_cards(card_id),
    user_id     TEXT NOT NULL,
    PRIMARY KEY (card_id, user_id)
);

-- RLS
ALTER TABLE kanban_boards ENABLE ROW LEVEL SECURITY;
ALTER TABLE kanban_cards  ENABLE ROW LEVEL SECURITY;
CREATE POLICY board_isolation ON kanban_boards
    USING (tenant_id = current_setting('app.current_tenant')::text);
CREATE POLICY card_isolation ON kanban_cards
    USING (tenant_id = current_setting('app.current_tenant')::text);
```

### 6.2 DAG → Card 的事件驱动映射

看板状态更新完全基于一期 L2 事件流，不轮询 LangGraph，不修改 `AgentFastState`：

```python
class KanbanEventConsumer:
    """
    RocketMQ/ONS 消费者：消费一期 agent_audit_log 事件流，更新看板卡片状态。
    消费位置：RocketMQ/ONS agent_audit_log topic（一期已有）。
    不修改任何一期组件，纯粹的读侧消费。
    """

    # AgentFastState.stage → Column 映射规则
    STAGE_TO_COLUMN = {
        "initiated":          "待处理",
        "planning":           "规划中",
        "executing":          "执行中",
        "critic_review":      "审核中",
        "human_approval":     "待审批",    # 触发 HITL 时置此列
        "approved":           "执行中",
        "rejected":           "已否决",
        "completed":          "已完成",
        "failed":             "失败",
    }

    def __init__(self, pg_store, ws_broadcaster, notification_service):
        self._pg = pg_store
        self._ws = ws_broadcaster         # WebSocket 广播器
        self._notif = notification_service

    async def process_event(self, event: dict) -> None:
        """处理一条 L2 审计事件，更新对应卡片状态"""
        thread_id  = event.get("thread_id")
        event_type = event.get("entry_type")
        stage      = event.get("diff", {}).get("stage")

        if not thread_id or not stage:
            return

        # 查找对应卡片
        card = await self._pg.get_card_by_thread(thread_id)
        if not card:
            return

        # 映射到目标列
        target_column_title = self.STAGE_TO_COLUMN.get(stage)
        if not target_column_title:
            return

        target_column = await self._pg.get_column_by_title(
            card.board_id, target_column_title
        )
        if not target_column or card.column_id == target_column.column_id:
            return

        # 更新卡片所在列
        await self._pg.move_card(card.card_id, target_column.column_id)

        # WebSocket 广播（前端实时更新）
        asyncio.create_task(
            self._ws.broadcast(
                room=f"board:{card.board_id}",
                event={
                    "type":      "card_moved",
                    "card_id":   str(card.card_id),
                    "thread_id": thread_id,
                    "from_col":  str(card.column_id),
                    "to_col":    str(target_column.column_id),
                    "stage":     stage,
                    "ts":        time.time(),
                }
            )
        )

        # HITL 进入待审批时，通知关注者
        if stage == "human_approval":
            watchers = await self._pg.get_card_watchers(card.card_id)
            for uid in watchers:
                asyncio.create_task(
                    self._notif.send(
                        to=uid,
                        message=f"任务「{card.title}」进入审批流程，请关注。"
                    )
                )
```

### 6.3 实时推送：WebSocket 升级方案

一期前端使用 SSE（单向推送）。看板需要 WebSocket（双向，支持客户端发起卡片移动、添加关注等操作）。

**升级策略**：SSE 和 WebSocket 并行存在，不废弃 SSE（一期 Agent 回复流继续使用 SSE），WebSocket 仅用于看板状态实时同步。

Kong 网关新增 WebSocket 路由：

```yaml
# Kong 配置扩展（新增，不修改一期路由）
services:
  - name: kanban-ws-service
    url: http://kanban-service:8080
    routes:
      - name: kanban-ws-route
        paths: ["/api/v1/kanban/ws"]
        protocols: ["https", "wss"]
        strip_path: false

plugins:
  - name: jwt           # 复用一期 JWT 插件
    service: kanban-ws-service
  - name: rate-limiting
    service: kanban-ws-service
    config:
      minute: 60        # WS 连接握手限流
```

WebSocket 消息协议（轻量，仅看板操作）：

```typescript
// 客户端发送
type KanbanClientMessage =
  | { type: "move_card";   card_id: string; to_column_id: string }
  | { type: "add_watcher"; card_id: string }
  | { type: "ping" }

// 服务端推送
type KanbanServerMessage =
  | { type: "card_moved";   card_id: string; from_col: string; to_col: string; stage: string; ts: number }
  | { type: "card_updated"; card_id: string; fields: Record<string, unknown>; ts: number }
  | { type: "hitl_pending"; card_id: string; approval_id: string; ts: number }
  | { type: "pong" }
```

### 6.4 权限与 ABAC 集成

看板权限复用一期 `ThinToolInterceptor` 的 ABAC 模型，以工具调用的形式统一管控：

| 操作 | 所需权限 | 说明 |
|---|---|---|
| 查看看板 | `kanban:read` | 同租户默认授予 |
| 移动卡片 | `kanban:write` | 仅限线程所有者（阶段一约束） |
| 添加关注 | `kanban:watch` | 同租户默认授予 |
| 创建看板 | `kanban:admin` | 管理员角色 |
| 删除卡片 | `kanban:admin` | 逻辑删除，不物理删除 |

---

## 7. 持久化调度器（Scheduler）

### 7.1 调度器选型决策

| 方案 | 优点 | 缺点 | 适用阶段 |
|---|---|---|---|
| **自建（Redis Streams + PG）** | 无新依赖，最快落地，完全可控 | 功能有限，高可用需自建 | **二期首选** |
| Temporal | 状态持久化极强，可视化好，工作流即代码 | 引入重型依赖，学习曲线陡 | 三期评估 |
| Argo Workflows | K8s 原生，与现有基础设施一致 | 不适合细粒度任务状态管理 | 三期备选 |

**二期选型：自建轻量调度器（Redis Streams + PG）**，满足以下需求：

- cron 表达式周期触发
- 一次性延迟任务
- 依赖前序任务完成后触发
- 持久化：任务定义存 PG，执行状态存 Redis（可降级 PG）

### 7.2 调度器核心设计

```python
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from enum import Enum
import time, uuid, croniter

class ScheduleTriggerType(Enum):
    CRON       = "cron"        # 周期执行
    ONE_SHOT   = "one_shot"    # 一次性延迟执行
    CHAIN      = "chain"       # 前序任务完成后触发

@dataclass
class ScheduleJob:
    """持久化调度任务"""
    job_id:         str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id:      str = ""
    job_name:       str = ""
    trigger_type:   ScheduleTriggerType = ScheduleTriggerType.CRON
    cron_expr:      Optional[str] = None    # 如: "0 9 * * 1-5"（工作日 9 点）
    run_at:         Optional[float] = None  # one_shot 触发时间戳
    chain_after:    Optional[str] = None    # 前序 job_id（chain 模式）

    # 触发参数（传给 LangGraph）
    skill_id:       str = ""
    task_input:     str = ""
    task_complexity: str = "moderate"

    # 并发与预算控制
    max_concurrency: int = 1            # 同一 job 最多并发执行数
    token_budget_override: Optional[int] = None  # None = 用默认预算

    # 状态
    enabled:        bool = True
    last_run_at:    Optional[float] = None
    next_run_at:    Optional[float] = None
    run_count:      int = 0
    fail_count:     int = 0
    created_at:     float = field(default_factory=time.time)


class SchedulerService:
    """
    轻量级持久化调度器。
    任务定义存 PG，执行状态存 Redis Streams（复用一期 Redis Sentinel）。
    触发逻辑：调用一期 LangGraph 外部触发接口，不修改 LangGraph 内部结构。
    """

    SCHEDULER_STREAM  = "scheduler:pending_jobs"
    SCHEDULER_GROUP   = "scheduler:workers"
    TICK_INTERVAL_S   = 30           # 每 30 秒扫描一次到期任务

    def __init__(
        self,
        pg_store,
        redis_client,
        workflow_trigger,            # 外部触发 LangGraph 的接口（见 7.3）
        token_budget_factory,
        metrics_reporter,
    ):
        self._pg = pg_store
        self._redis = redis_client
        self._trigger = workflow_trigger
        self._budget_factory = token_budget_factory
        self._metrics = metrics_reporter

    async def tick(self) -> None:
        """
        调度器心跳：扫描到期任务并推送到 Redis Stream。
        由独立的 scheduler-worker Pod 每 30 秒调用一次。
        """
        now = time.time()
        due_jobs = await self._pg.get_due_jobs(before_ts=now)

        for job in due_jobs:
            # 幂等检查：同一 job 在同一 tick 内不重复推送
            already_queued = await self._redis.setnx(
                f"scheduler:queued:{job.job_id}:{int(now // self.TICK_INTERVAL_S)}",
                "1"
            )
            if not already_queued:
                continue
            await self._redis.expire(
                f"scheduler:queued:{job.job_id}:{int(now // self.TICK_INTERVAL_S)}",
                self.TICK_INTERVAL_S * 3
            )

            await self._redis.xadd(self.SCHEDULER_STREAM, {
                "job_id":    job.job_id,
                "tenant_id": job.tenant_id,
                "skill_id":  job.skill_id,
                "task_input": job.task_input,
                "complexity": job.task_complexity,
            })

            # 更新下次执行时间
            if job.trigger_type == ScheduleTriggerType.CRON and job.cron_expr:
                next_run = croniter.croniter(job.cron_expr, now).get_next()
                await self._pg.update_job_schedule(job.job_id, next_run_at=next_run)

    async def worker_loop(self) -> None:
        """
        消费 Redis Stream，执行调度任务。
        每个 worker 以 Consumer Group 模式消费，避免重复执行。
        """
        await self._redis.xgroup_create(
            self.SCHEDULER_STREAM,
            self.SCHEDULER_GROUP,
            mkstream=True,
            id="$",
        )

        while True:
            messages = await self._redis.xreadgroup(
                groupname=self.SCHEDULER_GROUP,
                consumername=f"worker:{uuid.uuid4().hex[:8]}",
                streams={self.SCHEDULER_STREAM: ">"},
                count=5,
                block=5000,
            )

            for stream, entries in (messages or []):
                for msg_id, fields in entries:
                    await self._execute_job(fields)
                    await self._redis.xack(self.SCHEDULER_STREAM, self.SCHEDULER_GROUP, msg_id)

    async def _execute_job(self, fields: Dict) -> None:
        """触发一次 LangGraph workflow 执行"""
        job_id     = fields["job_id"]
        tenant_id  = fields["tenant_id"]
        skill_id   = fields["skill_id"]
        task_input = fields["task_input"]
        complexity = fields["complexity"]

        thread_id = f"sched:{job_id}:{uuid.uuid4().hex[:8]}"

        asyncio.create_task(self._metrics.record(
            "scheduler_job_triggered",
            job_id=job_id,
            tenant_id=tenant_id,
        ))

        try:
            # 复用一期 TokenBudget，新增 schedule_id 维度（见 7.3）
            budget = TokenBudget.allocate(
                thread_id=thread_id,
                tenant_id=tenant_id,
                task_complexity=complexity,
                entity_id=job_id,              # 二期新增
                entity_type="schedule",        # 二期新增
            )
            await self._trigger.invoke(
                thread_id=thread_id,
                tenant_id=tenant_id,
                skill_id=skill_id,
                task_input=task_input,
                token_budget=budget,
            )
            await self._pg.record_job_run(job_id, status="success")
        except Exception as exc:
            failure = map_exception_to_failure_state(exc)
            await self._pg.record_job_run(job_id, status="failed", error=str(exc))
            if failure == AgentFailureState.FAILED_CLOSED:
                await self._pg.disable_job(job_id, reason=str(exc))
```

### 7.2.1 调度类具名 Skill

二期调度器除提供通用 cron/one-shot/chain 触发能力外，需同步交付两个面向办公场景的具名 Skill，避免调度机制上线后缺少可用业务入口：

- `daily_briefing`：工作日上班前生成今日待办摘要，数据来源限定为日历/任务系统、看板卡片、尽调 Plan 待处理节点和待审批事项。
- `work_log_summary`：工作日下班后生成当日工作日志，数据来源限定为当日线程摘要、调度任务执行记录、尽调节点完成情况、看板状态变更与审批意见。

两个 Skill 均通过 `WorkflowTriggerGateway` 触发 LangGraph 工作流，仍受 Harness 工具白名单、租户权限、TokenBudget 与 WAL/ONS 审计约束；不得直接绕过 L2 事件轨读取原始会话全文，也不得自行访问未授权的日历、IM 或任务系统。

```python
@dataclass
class DailyBriefingInput:
    tenant_id: str
    operator_id: str
    work_date: str
    include_sources: List[str] = field(default_factory=lambda: [
        "calendar",
        "kanban",
        "dd_plan",
        "pending_approvals",
    ])
    output_channel: str = "im"


@dataclass
class WorkLogSummaryInput:
    tenant_id: str
    operator_id: str
    work_date: str
    include_sources: List[str] = field(default_factory=lambda: [
        "thread_summary",
        "scheduler_run_log",
        "dd_plan",
        "kanban",
        "approval_comments",
    ])
    output_channel: str = "im"
```

```yaml
# Nacos 配置：调度类 Skill 模板，仅声明可触发的具名任务，不开放任意脚本/任意 HTTP 调用
schedule_job_templates:
  daily_briefing:
    skill_id: daily_briefing
    default_cron: "0 9 * * 1-5"
    task_complexity: simple
    max_concurrency: 1
    allowed_sources: [calendar, kanban, dd_plan, pending_approvals]
    output_channel: im
  work_log_summary:
    skill_id: work_log_summary
    default_cron: "0 18 * * 1-5"
    task_complexity: simple
    max_concurrency: 1
    allowed_sources: [thread_summary, scheduler_run_log, dd_plan, kanban, approval_comments]
    output_channel: im
```

### 7.3 外部触发 LangGraph 接口

一期 LangGraph 工作流通过 HTTP API 触发，二期调度器复用此入口，**不修改 LangGraph 内部节点**：

```python
class WorkflowTriggerGateway:
    """
    LangGraph 外部触发网关。
    调度器、看板（手动触发）、协同（重新执行）均通过此统一入口触发工作流。
    不修改一期 LangGraph DAG 结构。
    """

    def __init__(self, deerflow_client, harness_interceptor):
        self._client = deerflow_client
        self._harness = harness_interceptor

    async def invoke(
        self,
        thread_id: str,
        tenant_id: str,
        skill_id: str,
        task_input: str,
        token_budget: "TokenBudget",
        trigger_source: str = "manual",   # manual / scheduler / collab
        initiator_id: str = "system",
    ) -> str:
        """
        触发 LangGraph workflow 执行。
        返回 thread_id 供调用方追踪。
        """
        # 构造符合一期 Harness 规范的环境上下文
        env_context = EnvContext(
            tenant_id=tenant_id,
            user_id=initiator_id,
            trace_id=f"{trigger_source}:{thread_id}",
            request_time=time.time(),
            allowed_tools=await self._harness.get_allowed_tools(tenant_id),
        )

        # 通过 HTTP 调用一期 DeerFlow 服务（不直接调用内部函数）
        await self._client.post(
            "/internal/workflow/trigger",
            json={
                "thread_id":      thread_id,
                "skill_id":       skill_id,
                "task_input":     task_input,
                "tenant_id":      tenant_id,
                "trigger_source": trigger_source,
                "token_budget": {
                    "total": token_budget.total_budget,
                    "entity_id": getattr(token_budget, "entity_id", None),
                },
            },
            headers={
                "X-Tenant-ID":    tenant_id,
                "X-Trace-ID":     env_context.trace_id,
                "X-Trigger-Source": trigger_source,
            },
        )

        return thread_id
```

### 7.4 TokenBudget 扩展：entity 级配额

一期 `TokenBudget` 以 `thread_id` 为维度，二期扩展 `entity_id` 维度（调度任务、尽调 Plan），**仅扩展 dataclass 字段，不改核心 `TokenBudgetGuard` 逻辑**：

```python
@dataclass
class TokenBudget:
    """
    继承一期全部字段，新增 entity 级维度（二期扩展）。
    entity_id + entity_type 用于调度任务和尽调 Plan 的成本聚合统计。
    不影响一期 TokenBudgetGuard 的熔断逻辑。
    """
    # ── 一期字段（不变）──
    thread_id:       str
    tenant_id:       str
    task_complexity: str
    total_budget:    int
    consumed:        int = 0
    degraded:        bool = False
    degraded_at:     Optional[int] = None
    created_at:      float = field(default_factory=time.time)

    # ── 二期新增字段 ──
    entity_id:       Optional[str] = None   # persona_id / job_id / plan_id
    entity_type:     Optional[str] = None   # "persona" / "schedule" / "dd_plan"

    @classmethod
    def allocate(
        cls,
        thread_id: str,
        tenant_id: str,
        task_complexity: str,
        entity_id: Optional[str] = None,
        entity_type: Optional[str] = None,
    ) -> "TokenBudget":
        budgets = {
            "simple":   5_000,
            "moderate": 20_000,
            "complex":  50_000,
        }
        return cls(
            thread_id=thread_id,
            tenant_id=tenant_id,
            task_complexity=task_complexity,
            total_budget=budgets.get(task_complexity, 10_000),
            entity_id=entity_id,
            entity_type=entity_type,
        )
```

### 7.4.1 调度任务成本聚合视图

调度任务成本聚合通过 §1.4 `AuditColdAnalyticsStore.aggregate_cost` 暴露查询能力，调度器与 Grafana Dashboard 不直接依赖 ClickHouse 物理视图。二期与三期的存储实现差异由适配层屏蔽。

```sql
-- 二期新增：PG 物化视图，按 entity 聚合 Token 消耗，支持调度任务成本核算
CREATE MATERIALIZED VIEW scheduler_cost_summary AS
SELECT
    tenant_id,
    entity_type,
    entity_id,
    sum(tokens_consumed) AS total_tokens,
    count()              AS invocation_count,
    date_trunc('day', ts) AS stat_date
FROM agent_token_events
WHERE entity_type IN ('schedule', 'dd_plan')
GROUP BY tenant_id, entity_type, entity_id, date_trunc('day', ts);

CREATE UNIQUE INDEX idx_scheduler_cost_summary_entity_day
    ON scheduler_cost_summary (tenant_id, entity_type, entity_id, stat_date);
```

三期接入 ClickHouse 后，该聚合视图可迁移为 SummingMergeTree 物化视图；Dashboard 仍通过 `AuditColdAnalyticsStore.aggregate_cost` 查询，不直接改调用方。

---

## 8. 二期扩展：新增中间件与基础设施

| 中间件 | 用途 | 部署要求 | 最低资源 | 备注 |
|---|---|---|---|---|
| **看板后端服务** | Board/Column/Card CRUD + WS 推送 | 2 副本 | 2C2G × 2 | 新增 |
| **Scheduler Worker** | Redis Stream 消费 + cron 触发 | 2 副本 | 1C1G × 2 | 新增，DaemonSet 可选 |
| **协同服务** | 共享线程管理 + 评论 + 通知 | 2 副本 | 1C2G × 2 | 新增 |
| **WebSocket Gateway** | WS 长连接管理 + 消息广播 | 3 副本 | 1C1G × 3 | 新增，Kong 插件配合 |
| **Search API Client** | Brave/Bing 检索封装 + 结果缓存 | 2 副本 | 1C1G × 2 | 新增 |
| **尽调模板服务** | DD Plan 模板管理 + 版本化 | 2 副本 | 1C1G × 2 | 新增（Nacos 配合） |

**一期中间件无需升级**，以下为 Helm 增量配置：

```yaml
# values-phase2.yaml（追加至一期 values-production.yaml）
services:
  kanban-service:    { replicas: 2, resources: { cpu: "1", memory: "2Gi" } }
  scheduler-worker:  { replicas: 2, resources: { cpu: "0.5", memory: "1Gi" } }
  collab-service:    { replicas: 2, resources: { cpu: "0.5", memory: "2Gi" } }
  ws-gateway:        { replicas: 3, resources: { cpu: "0.5", memory: "1Gi" } }
  search-tool:       { replicas: 2, resources: { cpu: "0.5", memory: "1Gi" } }
  dd-template-svc:   { replicas: 2, resources: { cpu: "0.5", memory: "1Gi" } }

# 新增数据库表（在一期 PG 实例上扩展，无需新实例）
postgresql_migrations:
  - phase2_kanban_tables.sql
  - phase2_dd_plan_tables.sql
  - dd_plan_audit.sql
  - phase2_collab_tables.sql
  - phase2_scheduler_tables.sql
  - scheduler_cost_summary.sql

# ClickHouse 三期迁移预留（二期不执行）
clickhouse_migrations_deferred:
  - dd_plan_audit_ch.sql
  - scheduler_cost_summary_ch.sql
```

**累计资源估算（在一期规格 C 基础上新增）**：约 +10C +16G，不新增存储实例。

---

## 9. 二期 Harness 层扩展

### 9.1 工具白名单扩展（Nacos 热更新，不改代码）

```yaml
# Nacos 配置：二期新增工具白名单项
tenant_tool_whitelist:
  investment_div:
    existing_tools: [invoice_ocr, contract_review, financial_query]   # 一期已有
    phase2_additions:
      - multi_agent_task_create # 受控多 Agent 任务入口（仅触发已发布模板）
      - corp_registry_fetch    # 工商信息查询（尽调）
      - web_search             # 受控 Web 检索（需合规审查通过后启用）
      - kanban_card_move       # 看板操作
      - schedule_job_trigger   # 触发调度任务
      - daily_briefing         # 今日待办摘要
      - work_log_summary       # 当日工作日志总结
  compliance_div:
    phase2_additions:
      - multi_agent_task_create # 受控多 Agent 任务入口（仅触发已发布模板）
      - dd_plan_create         # 创建尽调计划
      - dd_evidence_upload     # 上传尽调证据
      - daily_briefing         # 今日待办摘要
      - work_log_summary       # 当日工作日志总结
```

### 9.2 TokenBudget entity 级告警（Nacos 热更新）

```yaml
# entity 级预算告警配置（不改 TokenBudgetGuard 代码，通过配置扩展）
entity_budget_alerts:
  schedule:
    monthly_limit: 2_000_000   # 调度任务每月 Token 上限
    alert_at_pct:  80
  dd_plan:
    per_plan_limit: 100_000    # 每次尽调 Token 上限
    alert_at_pct:  70
```

### 9.3 失败态扩展（追加至一期 DEFAULT_FAILURE_REGISTRY）

```python
# 在一期 DEFAULT_FAILURE_REGISTRY 基础上追加（不修改原有映射）
PHASE2_FAILURE_REGISTRY = {
    # 尽调专项
    "DDEvidenceIncompleteError":   AgentFailureState.HUMAN_REVIEW,
    "DDRiskScoreBlockedError":     AgentFailureState.FAILED_CLOSED,
    "DDTemplateVersionMismatch":   AgentFailureState.HUMAN_REVIEW,
    # 调度专项
    "ScheduleJobDisabledError":    AgentFailureState.FAILED_CLOSED,
    "ScheduleConcurrencyExceeded": AgentFailureState.RETRYABLE,
    # Web Search 专项
    "SearchDomainNotWhitelisted":  AgentFailureState.FAILED_CLOSED,
    "SearchRateLimitExceeded":     AgentFailureState.RETRYABLE,
    "SearchResultEmptyError":      AgentFailureState.HUMAN_REVIEW,
    # 协同专项
    "CollabWritePermissionDenied": AgentFailureState.FAILED_CLOSED,
}

# 合并（运行时加载）
DEFAULT_FAILURE_REGISTRY.update(PHASE2_FAILURE_REGISTRY)
```

---

## 10. 二期可观测性扩展

在一期 13 个核心告警指标基础上，新增以下二期专项指标：

| 指标 | 告警阈值 | 说明 |
|---|---|---|
| 尽调证据完整度 | < 90% | 必需证据缺失，影响评分准确性 |
| 尽调规则命中精确率 | < 95% | 规则库质量下降信号 |
| 尽调自动阻断率突增 | > 2x 基线 | 规则误报或数据质量问题 |
| 尽调 Reflection 阻断率突增 | > 2x 基线 | 模板、工具输出或报告质量异常 |
| 调度任务执行成功率 | < 95% | 调度器或下游 Skill 质量问题 |
| 调度任务积压深度 | > 100 | Redis Stream 消费滞后 |
| entity 级 Token 月消耗 | 超预算 80% | 调度/尽调成本控制红线 |
| Web Search 白名单命中率 | < 60% | 检索无效或白名单配置偏窄 |
| Web Search 可信度均值 | < 0.70 | 检索结果质量下降 |
| WebSocket 连接数 | > 500/Pod | WS Gateway 容量预警 |
| 协同评论写入延迟 P99 | > 2s | 协同服务性能问题 |
| 看板事件消费延迟 P99 | > 5s | RocketMQ/ONS 消费滞后或看板服务性能问题 |

新增 OTel Span：

```python
# 二期新增标准 Span（追加至一期 AgentSpanFactory）

@staticmethod
def dd_plan_span(plan_id: str, node_type: str):
    """尽调计划执行 Span"""
    return tracer.start_as_current_span(
        f"dd_plan.{node_type}", kind=SpanKind.INTERNAL
    )

@staticmethod
def web_search_span(query_hash: str):
    """Web 检索 Span（不记录原始 query，仅记录 hash，防 PII 泄露）"""
    return tracer.start_as_current_span(
        "web_search.query", kind=SpanKind.CLIENT
    )

@staticmethod
def scheduler_span(job_id: str, trigger_type: str):
    """调度任务触发 Span"""
    return tracer.start_as_current_span(
        f"scheduler.{trigger_type}", kind=SpanKind.INTERNAL
    )
```

---

## 11. 二期 Evaluation Layer 扩展

在一期 5 类评估能力基础上，新增：

| 能力 | 输入 | 输出 | 用途 |
|---|---|---|---|
| 尽调流程回放 | 脱敏历史尽调轨迹 + 标注风险分 | 规则命中精确率、评分偏差、报告完整度 | 防止尽调 Skill 或规则库退化 |
| 调度任务稳定性评估 | 历史触发记录 + 执行结果 | 成功率、重试率、成本波动 | 调度 Skill 版本变更验收 |
| Web Search 质量评估 | 标准查询集 + 人工标注预期结果 | 白名单命中率、可信度均值、Reranker 精度 | Web Search Skill 上线准入 |

**二期发布门禁追加**（在一期 Release Gate 基础上新增）：

| 变更类型 | 新增门禁指标 | 触发动作 |
|---|---|---|
| 尽调规则库变更 | `rule_hit_precision < 0.95` | 强制阻断，回滚规则库 |
| 尽调模板 / 报告 Skill 变更 | `reflection_pass_rate < 0.95` | 强制阻断，进入人工复核 |
| Web Search Skill 版本升级 | `whitelist_hit_rate < 0.60` 或 `credibility_mean < 0.70` | 强制阻断 |
| 调度器 Worker 升级 | `scheduler_success_rate < 0.95` | 强制阻断 |

---

## 12. 部署规格增量

### 12.1 二期最终资源汇总

| 类别 | 一期规格 C | 二期增量 | 合计 |
|---|---|---|---|
| CPU（vCore） | ~60 | +10 | ~70 |
| 内存（GB） | ~120 | +16 | ~136 |
| SSD 存储 | ~2 TB | +500 GB（尽调证据归档 + 报告存储） | ~2.5 TB |
| GPU | 2 | 0（二期不引入多模态） | 2 |
| 新增 PG 表/视图 | - | 约 10 张（含 dd_plan_audit 与 scheduler_cost_summary，见 §3.5、§4.2、§6.1、§7.2、§7.4.1） | - |
| 新增 ClickHouse 表 | - | 0（二期延后，三期通过 §1.4 适配层接入） | - |

### 12.2 新增服务部署清单

```
二期新增服务（追加至一期 values-production.yaml）
  ├─ kanban-service        × 2 Pod   （看板后端）
  ├─ scheduler-worker      × 2 Pod   （调度消费者）
  ├─ collab-service        × 2 Pod   （协同/评论）
  ├─ ws-gateway            × 3 Pod   （WebSocket 网关）
  ├─ search-tool           × 2 Pod   （Web 检索封装）
  └─ dd-template-svc       × 2 Pod   （尽调模板管理）
```

---

## 13. 实施 Roadmap（8 个月）

> 二期在一期全面投产（M10）后启动，以下月份计数从二期 M1 开始。

```
P2-M1-M2  尽调 Plan 基础版
  ├─ 尽调数据模型（PG 表 + OSS 目录结构）设计与评审
  ├─ DueDiligencePlan 对象模型实现
  ├─ 受控多 Agent 任务入口（仅触发已发布尽调模板）
  ├─ 模板引擎基础版（YAML 定义 + Nacos 热加载）
  ├─ 投前尽调模板 v1（工商 + 财务 + 法务三节点）
  ├─ DDCriticEngine 双轨评分引擎（规则集 v1）
  ├─ DDReflectionGate 四类运行时检查点（规划/工具结果/风险/报告）
  ├─ 尽调 DAG 构建器（复用一期 detect_cycle）
  ├─ PG dd_plan_audit 表上线（经 AuditHotStore 写入）
  └─ Evaluation 尽调评估基线建立（标注样例集 ≥ 50 条）

P2-M3-M4  尽调深水区 + 协同基础版
  ├─ 尽调外部数据接入（工商 API + Tool 白名单更新）
  ├─ 尽调报告生成 Skill（长上下文模型，PDF/DOCX 输出）
  ├─ 尽调合规存档（OSS KMS 加密 + 7 年 TTL）
  ├─ 协同服务：共享线程数据模型 + RLS
  ├─ 评论与标注服务（CommentService + WAL 审计）
  ├─ 尽调报告完成后自动创建协同审批任务（CollabApprovalOrchestrator）
  ├─ 多人审批通知扩展（CollabNotificationExtension）
  ├─ Evaluation 尽调流程回放门禁接入 CI/CD
  └─ 尽调 Skill 红队扫描 + 上架审核

P2-M5  Web Search（合规通过后）
  ├─ [前置] 合规团队完成网络访问合规审查（M1 并行启动，M5 前必须结论）
  ├─ Search API 封装（Brave/Bing + 结果缓存）
  ├─ Web Search 独立对话入口（Semantic Router → WebSearchConversationGateway）
  ├─ 域名白名单注册表（Nacos，金融监管/权威财经站优先）
  ├─ 可信度评分器 + BGE Reranker 集成
  ├─ 检索结果审计写入 WAL + RocketMQ/ONS + AuditHotStore
  ├─ Search → L3 记忆准入策略（HITL 确认模式）
  ├─ Evaluation Web Search 质量基线 + 发布门禁
  └─ Web Search Skill 上架（canary 10% 灰度，仅 investment_div）

P2-M6  看板 + 调度器
  ├─ 看板 PG 表上线（board/column/card/watchers）
  ├─ KanbanEventConsumer（RocketMQ/ONS 消费 L2 事件）
  ├─ WebSocket Gateway 上线（Kong 配置扩展）
  ├─ 看板前端 UI（卡片视图 + 实时状态更新）
  ├─ 调度器数据模型（ScheduleJob PG 表）
  ├─ SchedulerService + Worker 部署（Redis Streams）
  ├─ 外部触发 LangGraph 接口（WorkflowTriggerGateway）
  ├─ daily_briefing Skill（工作日上班前今日待办摘要）
  ├─ work_log_summary Skill（工作日下班后工作日志总结）
  ├─ TokenBudget entity 级扩展（二期字段追加）
  └─ entity 级 Token 成本 Grafana Dashboard

P2-M7  集成测试 + 安全审计
  ├─ 尽调全链路端到端测试（真实发票 + 模拟工商数据）
  ├─ Web Search 合规审查复核（确认白名单落地生效）
  ├─ WebSocket 压测（目标：500 并发连接，P99 消息延迟 < 100ms）
  ├─ 调度任务并发压测（月末批量尽调场景）
  ├─ 蓝红对抗演练：尽调规则绕过 + Web Search 白名单逃逸测试
  ├─ 协同权限边界测试（阶段一只读约束验证）
  └─ 第三方安全审计（重点：尽调证据 OSS 访问控制 + WS 鉴权）

P2-M8  全面投产
  ├─ 尽调功能全量发布（canary → 100%）
  ├─ 协同功能全量发布
  ├─ Web Search 按租户灰度扩展（视合规审查结论）
  ├─ 看板 + 调度器全量发布
  ├─ entity 级成本告警全量开启
  ├─ 二期 Evaluation 门禁全部接入 CI/CD
  ├─ Temporal/Argo 调度器升级方案评估报告（为三期准备）
  └─ AI 分身（Persona）三期立项评审
```

---

## 14. 风险应对矩阵

| 风险项 | 概率 | 影响 | 等级 | 应对措施 |
|---|---|---|---|---|
| **Web Search 合规审查否决** | 中 | 高 | 🔴 P0 | M1 立即启动合规预审，M5 前出结论；若否决则整个 Web Search 功能取消，不影响其他功能交付 |
| **尽调外部 API 稳定性差** | 高 | 中 | 🔴 P0 | ToolLock 30s 超时 + RETRYABLE 重试；外部 API 不可用时降级为人工录入，HITL 兜底 |
| **WebSocket 长连接资源泄漏** | 中 | 中 | 🟡 P1 | WS Gateway 心跳检测（30s ping/pong）；空闲连接 5 分钟自动断开；连接数告警 > 500/Pod |
| **尽调证据 OCR 低置信导致评分偏差** | 中 | 高 | 🟡 P1 | 复用一期 PaddleOCR-VL 局部升维；置信度 < 0.7 字段标记 low_confidence，触发 HITL 人工核验 |
| **调度任务 Token 成本失控** | 中 | 中 | 🟡 P1 | entity 级预算告警（80% 触发）；月度上限硬熔断；调度任务默认 moderate 预算 |
| **协同并发写入冲突（阶段一绕过限制）** | 低 | 高 | 🟡 P1 | ThreadWriteGuard 强制拦截；前端禁用写入 UI（非所有者），双重防护 |
| **尽调规则库误报导致项目阻断** | 中 | 高 | 🟡 P1 | 规则分 auto_block 和非 auto_block 两级；非 auto_block 只触发 HITL，不直接阻断；规则变更需经 Evaluation 门禁 |
| **Scheduler Worker 重复执行** | 低 | 中 | 🟡 P1 | Redis SETNX 幂等锁 + Consumer Group ACK 机制；任务级幂等 key 防止重复触发 LangGraph |
| **Web Search 检索结果污染 L3 知识库** | 低 | 高 | 🟡 P1 | SearchToMemoryPolicy 强制高可信度（≥ 0.80）+ HITL 确认双重门槛；L3 写入前经 PIITokenizationGateway 脱敏 |
| **一期 Evaluation 基线未建立导致二期门禁失效** | 低 | 高 | 🟢 P2 | §2 一期验收门禁：Evaluation 基线是二期启动的前置条件，硬性阻断 |
| **Temporal 三期引入工期低估** | 中 | 低 | 🟢 P2 | 二期调度器保持轻量自建；Temporal 仅在 M8 出评估报告，不在二期做技术决策 |

---

## 附录：二期核心设计决策汇总

| 决策 | 选择 | 拒绝 | 理由 |
|---|---|---|---|
| 调度器技术选型 | 自建（Redis Streams + PG） | Temporal（首选） | 二期规避新重型依赖，三期评估 Temporal |
| 协同写入支持范围 | 阶段一只读共享 + 评论 | 并发写入 AgentFastState | LangGraph 单写模型约束；冲突语义需 L2 充分稳定后再设计 |
| Web Search 实现方式 | Search API（Brave/Bing） | headless 浏览器（Playwright） | 合规审查优先；Playwright 沙箱工程量与合规风险均高，作为阶段二预案 |
| 检索结果写入 L3 策略 | 高可信度 + HITL 确认双门槛 | 直接自动写入 | 防止不可控外部内容污染金融知识库 |
| WebSocket 与 SSE 关系 | 并行共存 | 替换 SSE | Agent 回复流保留 SSE；看板实时同步用 WS，避免改动一期前端 |
| AI 分身（Persona） | 推迟至三期 | 二期并行 | L3 长期记忆扩展工程量高；三层记忆需在二期充分运行后再做 Persona 级扩展 |
| 尽调证据存储加密 | OSS KMS 租户密钥 + 7 年 TTL | 普通 OSS 存储 | 金融监管合规要求；尽调证据属于高敏数据 |
| 尽调评分模型 | 规则引擎（Tier A）+ LLM Critic（Tier C，按需） | 纯 LLM 评分 | 规则确定性高、零 Token 消耗；LLM 仅处理规则无法覆盖的边界判断 |
