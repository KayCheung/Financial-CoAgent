# 企业级 Agent 平台一期完整方案

> **版本**：v1.2（生产级优化版） | **技术基座**：DeerFlow 2.0 + LangGraph 1.0 + LangChain
> **许可证**：MIT（DeerFlow 原生） | **目标场景**：金融企业私有化部署

-----

**★ 核心架构思想**

_把 Agent 当作一个极其聪明但不可控的「危险生物」。Harness Engineer 的全部工作就是为它打造一个透明、坚固、带有一票否决权的「结界（Harness）」。_

**大模型只是一个高级运算器，生杀大权全部掌握在传统的、确定性的企业级代码手里。**

-----

## 目录

1.  [平台总体架构](#1-平台总体架构)
2.  [Agent Harness 层](#2-agent-harness-层)
  2.1 [隐式思考链与合规打点](#21-隐式思考链与合规打点)
  2.2 [防御性工具调用（Tool Interceptor）](#22-防御性工具调用-tool-interceptor)
  2.3 [上下文脱水与注水](#23-上下文脱水与注水)
3.  [DeerFlow 核心引擎层](#3-deerflow-核心引擎层)
  3.1 [LangGraph 工作流与 Critic 反思闭环](#31-langgraph-工作流与-critic-反思闭环)
  3.2 [Critic 节点职责拆分](#32-critic-节点职责拆分)
  3.3 [Human-in-the-Loop 超时处理](#33-human-in-the-loop-超时处理)
  3.4 [高性能沙箱（gVisor + 预热池）](#34-高性能沙箱-gvisor--预热池)
4.  [智能路由与多任务调度](#4-智能路由与多任务调度)
5.  [企业安全壳](#5-企业安全壳)
6.  [业务 Agent 模块](#6-业务-agent-模块)
7.  [智能问数对接方案](#7-智能问数对接方案)
8.  [Skill 广场体系](#8-skill-广场体系)
9.  [可观测与链路追踪](#9-可观测与链路追踪)
10. [权限与数据安全](#10-权限与数据安全)
11. [部署架构](#11-部署架构)
12. [技术栈汇总](#12-技术栈汇总)
13. [实施路线图与团队配置](#13-实施路线图与团队配置)
14. [二开可行性与风险评估](#14-二开可行性与风险评估)
-----

## 1. 平台总体架构

```
┌─────────────────────────────────────────────────────────────┐
│                     用户入口层                               │
│     Web App │ Mobile │ REST API │ 钉钉 │ 飞书 │ 微信         │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                   企业安全网关（自建）                        │
│   JWT/SAML/SSO │ RBAC/ABAC │ 数据脱敏 │ 限流 │ 审计日志       │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│             DeerFlow Message Gateway（复用+扩展）            │
│     飞书 Card │ Slack │ WebSocket │ SSE 流式输出             │
└──────────────────────────────┬──────────────────────────────┘
                               │
╔══════════════════════════════▼══════════════════════════════╗
║                       AGENT HARNESS 层                      ║
║  ┌─────────────────┐ ┌──────────────────┐ ┌─────────────┐   ║
║  │  Hidden CoT     │ │ Tool Interceptor  │ │  Context   │   ║
║  │  Scratchpad     │ │ 参数覆写+注入检测  │ │  脱水/注水  │   ║
║  └─────────────────┘ └──────────────────┘ └─────────────┘   ║
╚═════════════════════════════════════════════════════════════╝
                               │
┌──────────────────────────────▼──────────────────────────────┐
│      智能路由 & 编排引擎（DeerFlow LangGraph 内核）           │
│  [Semantic Router] → [LLM 意图分类] → [Sub-Agent 调度]       │
│         [Executor] ←→ [Critic 反思/一票否决]                 │
└──────────────────────────────┬──────────────────────────────┘
                               │
     ┌─────────────────────────┼─────────────────────────┐
     │                         │                         │
 [业务 Agent 模块]      [Skill 运行时]            [MCP 外部适配]
                               │
┌──────────────────────────────▼──────────────────────────────┐
│    能力平台层：LLM 路由 │ Milvus │ gVisor 沙箱(预热池)        │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│ 数据层：PostgreSQL(RLS) │ Redis │ MinIO │ Kafka │ ClickHouse │
└─────────────────────────────────────────────────────────────┘
```

-----

## 2. Agent Harness 层

借鉴 Claude Code 顶层设计思想，将所有围绕 Agent 的安全、上下文、工具调用控制统一收拢到 Harness 层，由专职 Harness Engineer 负责维护。Harness 层对业务层拥有一票否决权。

### 2.1 隐式思考链与合规打点（Hidden CoT Scratchpad）

借鉴 Claude Code 的 `<thinking>` 暂存区机制，为每个业务 Agent 分配独立的内部推理暂存区。Agent 进行多步推理时（如比对财报提取风险点、逐条分析合同条款），所有中间推理过程写入暂存区。

| 特性 | 说明 |
| ---- | ---- |
| 对用户不可见 | 返回给审批人员的是结构化干净结论，Scratchpad 内容全程屏蔽 |
| 100% 落入审计库 | 合规出问题时可回放 Agent 完整推理链路，明确错误判断依据 |
| 越权实时拦截 | Harness 在 Scratchpad 写入时同步扫描越权推理（如访问其他用户数据） |
| 物理隔离存储 | Scratchpad 加密后单独列存于 ClickHouse，与业务数据物理分离 |

```python
class HarnessScratchpad:
    async def write(self, step: str, content: str):
        entry = {'step': step, 'content': content, 'timestamp': utcnow()}
        self._scratchpad.append(entry)

        # Harness 核心：同步落入不可篡改审计库（无论后续是否报错）
        await self.audit_logger.log_scratchpad(self.thread_id, entry)

        # 越权推理实时拦截
        violations = boundary_rule_engine.scan(content)
        if violations:
            raise HarnessSecurityException(f'Agent 推理越界: {violations}')

    def get_final_output_only(self) -> str:
        # 对用户只返回最后一步结论，中间推理全部屏蔽
        return self._scratchpad[-1]['content'] if self._scratchpad else ''
```

### 2.2 防御性工具调用（Tool Interceptor）

在 Agent 与 MCP Tool 之间插入物理防火墙。Agent 只能说「我要查什么」，不能决定「用什么参数去查」。所有工具参数必须经过 Harness 的三步处理后方可执行。

**三步处理流程**
**步骤 1 - 强制身份覆写**：无论 Agent 生成什么参数，tenant_id 和 operator_id 只从网关透传的环境上下文中取，严禁大模型篡改。
**步骤 2 - 高危参数嗅探**：正则 + 轻量 AST 解析检测 SQL 注入（OR 1=1）、路径穿越（../）、Prompt 注入（ignore previous）等高危模式。
**步骤 3 - 工具白名单校验**：该 Agent 是否有权调用此工具，权限来源于 RBAC 配置而非 Agent 自身声明。

**配置动态热发（Hot-Reload）**：HarnessInterceptor 的注入正则库、工具白名单等规则，脱离代码硬编码，统一托管至企业动态配置中心（如 Apollo / Nacos）。Harness 服务在内存中长轮询监听配置变更，实现秒级防御策略阻断，无需重启 Pod。

```python
class HarnessToolInterceptor:
    INJECTION_PATTERNS = [
        r'OR\s+1\s*=\s*1',   # SQL 注入
        r';\s*DROP',           # DDL 注入
        r'--',                 # SQL 注释注入
        r'\.\./',             # 路径穿越
        r'ignore previous',    # Prompt 注入
    ]
    @staticmethod
    async def intercept(tool_name, raw_params, env_context):
        # 步骤 1：强制身份覆写
        safe_params = {**raw_params,
            'tenant_id':   env_context.tenant_id,
            'operator_id': env_context.user_id,
        }
        # 步骤 2：高危参数嗅探
        payload = json.dumps(safe_params)
        for pattern in HarnessToolInterceptor.INJECTION_PATTERNS:
            if re.search(pattern, payload, re.IGNORECASE):
                raise HarnessSecurityException(f'检测到高危参数注入')
        # 步骤 3：工具白名单
        if tool_name not in env_context.agent_tool_whitelist:
            raise HarnessPermissionException(f'无权调用工具 [{tool_name}]')
        return safe_params
```

### 2.3 上下文脱水与注水（Context Dehydration & Hydration）

不再让小模型写自由文本「总结小作文」（容易幻觉变形），改为强制输出状态机 JSON，由 Harness 进行 Schema 校验。

**降级保底策略**：若本地小模型（llm_mini）抽风导致连续 3 次输出的 JSON 无法通过 Schema 校验，系统绝对不丢弃上下文，而是回退保存原始长文本至持久层，在 Redis 中打上异常标记，并转交人工审核机制或触发告警。

```python
# 脱水：将冗长对话压缩为强结构 JSON（Harness 校验 Schema）
DEHYDRATE_PROMPT = '''
不要任何解释，只输出严格符合 Schema 的 JSON：
{ 'intent': '...', 'stage': '...', 'entities': {...},
  'pending_actions': [], 'constraints': {...}, 'turn_count': N }
'''

async def _memory_dehydrate(thread_id, thread_data):
    raw_json = await llm_mini.invoke(DEHYDRATE_PROMPT, response_format='json_object')
    # Harness 强制 Schema 验证
    jsonschema.validate(raw_json, DEHYDRATED_STATE_SCHEMA)  # 不合规拒绝落库
    await redis.set_state(thread_id, raw_json, ex=86400)

# 注水：将 JSON 状态还原为 Agent 系统提示前缀
async def _memory_hydrate(thread_id):
    state = await redis.get_state(thread_id)
    return f'[会话上下文恢复] 当前阶段:{state["stage"]} 待完成:{state["pending_actions"]}'
```

## 3. DeerFlow 核心引擎层（深度定制）

### 3.1 LangGraph 工作流与 Critic 反思闭环

```python
def build_enterprise_workflow():
    graph = StateGraph(AgentState)
    graph.add_node('semantic_router', semantic_router_node)   # 极速路由
    graph.add_node('llm_router',      intent_router_node)     # LLM 兜底
    graph.add_node('planner',         task_planner_node)      # DAG 拆解
    graph.add_node('executor',        sub_agent_executor)     # 工具执行（含 Harness）
    graph.add_node('fact_checker',    critic_validation_node) # 合规校验
    graph.add_node('human_approval',  human_approval_node)    # 人工确认
    graph.add_node('memory',          memory_update_node)     # 状态归档

    def check_result(state):
        if state.get('is_safe') and state.get('is_accurate'):
            return 'human_approval' if state.get('requires_approval') else 'memory'
        elif state.get('retry_count', 0) < 3:
            return 'executor'   # 带错误上下文重试
        return END              # 三次失败：阻断并告警

    graph.add_edge('executor', 'fact_checker')
    graph.add_conditional_edges('fact_checker', check_result)
    return graph.compile(checkpointer=enterprise_checkpointer)
```

### 3.2 Critic 节点职责拆分

Critic 节点分为两层：安全校验（规则引擎，确定性，必须执行）和事实准确性校验（LLM 质疑，仅在高幻觉风险场景触发）。结构化场景（问数、审批）跳过准确性校验，节省 Token 消耗。

| 检查类型 | 触发场景 | 技术实现 | Token 消耗 |
| ---- | ---- | ---- | ---- |
| 合规安全检查 | 全部场景，必须执行 | 规则引擎，确定性 | 零消耗 |
| 事实准确性校验 | 知识库问答、合同分析、财报解读 | LLM 自我质疑 | 约 500 Token / 次 |
| 结构化场景 | 智能问数、审批流、日程管理 | 直接跳过 | 零消耗 |

### 3.3 Human-in-the-Loop 超时处理

```python
async def human_approval_node(state: AgentState) -> AgentState:
    timeout_hours = state.get('approval_timeout_hours', 24)
    try:
        approval = await asyncio.wait_for(
            approval_node.wait_for_response(state['approval_id']),
            timeout=timeout_hours * 3600
        )
        state['approved'] = approval.result
    except asyncio.TimeoutError:
        state['approved'] = False
        await im.notify(state['initiator'],
            f'审批任务 {state["approval_id"]} 已超时，请重新发起')
    return state
```

### 3.4 高性能沙箱（gVisor + 预热池）

```yaml
# sandbox 配置（gVisor 防逃逸 + 预热池消除冷启动）
sandbox:
  mode: kubernetes
  provisioner:
    runtime_class: gvisor          # 替换默认 runc 为 runsc，内核级隔离
    namespace_per_tenant: true
    network_policy: strict_egress_only_api
  warm_pool:
    enabled: true
    min_idle: 10                   # 提前拉起 10 个干净 Pod
    max_pool_size: 50
    recycle_policy: destroy_after_use  # 脏容器用完即毁
```

**预热池击穿保护（Thundering Herd 拦截）：**
在 Sub-Agent 调度器前置引入基于 Redis 的令牌桶限流器与等待队列。

- **排队机制**：当活跃沙箱数达到 max_pool_size 且无空闲容器时，新任务进入最高 30 秒的排队队列，而非直接报错。
- **状态透传**：排队期间，系统通过 SSE（Server-Sent Events）向前端持续推送状态（"系统正在调度安全执行环境，排队中..."），保障极端峰值下的用户体验和集群稳定。

```python
MAX_QUEUE_DEPTH = 200  # 超出直接返回 503，不继续排队

async def acquire_sandbox(tenant_id: str, timeout: float = 30.0):
    queue_depth = await redis.llen(f"sandbox:queue:{tenant_id}")
    if queue_depth >= MAX_QUEUE_DEPTH:
        raise SandboxCapacityException("沙箱队列已满，请稍后重试")
    # 进入排队 + SSE 推送...
```

-----

## 4. 智能路由与多任务调度

### 4.1 Semantic Router（极速向量路由，0 LLM 消耗）

采用本地轻量模型（BAAI/bge-small-zh-v1.5）进行第一层意图分发，高置信度命中不消耗任何 LLM Token。Skill 上架 / 下架时触发热更新，不重启服务。

| 置信度区间 | 路由策略 | LLM 消耗 |
| ---- | ---- | ---- |
| > 0.85 | 直接路由到目标 Agent，毫秒级响应 | 零消耗 |
| 0.60 ~ 0.85 | 进入澄清对话节点，二次确认 | 约 200 Token |
| < 0.60 | 降级到 LLM 意图分类器（大模型兜底） | 约 800 Token |

**上线初期的影子模式（Shadow Mode）**：
在项目投产的前 2 个月，Semantic Router 强制开启影子模式。即：所有请求同时并行发送给“向量路由”和“LLM 兜底路由”，业务流转以 LLM 结果为准。系统静默比对两者差异并落盘。Harness Engineer 利用这些真实负样本微调意图向量阈值，待准确率达标后，再正式开启物理拦截。

### 4.2 多任务并发调度

多意图场景触发 LangGraph DAG 拆解，通过 DeerFlow SubAgentSpawner 并行调度最多 4 个子任务，结果统一聚合后返回。

-----

## 5. 企业安全壳（自建覆盖）

### 5.1 RBAC + ABAC 细粒度控制

RBAC 控制用户能访问哪些 Agent 和 Skill；ABAC 在 Tool 返回结果时注入行列级数据过滤。两者在数据访问链路上形成双重拦截。

### 5.2 双向数据脱敏网关

进入 LLM 前：将身份证、手机号、银行卡号替换为 Token，原文存入映射表。返回用户前：根据用户权限级别决定是否从映射表还原真实数据，高权限用户可见原文，普通用户见脱敏版本。

### 5.3 不可篡改审计流水

审计记录新增两个字段：scratchpad（Agent 完整推理链路）和 harness_checks（Harness 拦截记录）。通过 Kafka → ClickHouse 落表，行级不可删除，满足金融合规要求。

-----

## 6. 业务 Agent 模块

| Agent | 核心工作流 | Hidden CoT | MCP 工具 |
| ---- | ---- | ---- | ---- |
| 知识库 | 查询改写 → 混合召回 (Milvus+ES) → BGE-Reranker 精排 → 生成 | 启用 | vector_search, doc_fetch |
| 合同审查 | LayoutLM 智能切片（长文档预处理熔断） → 多模态 OCR → 结构化解析 → 模板比对 → 风险识别 → 报告 | 启用 | ocr_extract, clause_compare |
| 财务报销 | 发票 OCR → 合规检查 → 填报销单 → OA 审批流 | 关闭 | invoice_ocr, oa_submit |
| 金融编排 | 风控预审 → 材料核验 → 多级审批链 → Human-in-Loop | 关闭 | risk_query, approval_flow |
| 个人助手 | 日程 / 任务 / 邮件 / 会议纪要 | 关闭 | calendar, task_manage |
| 智能问数 | 路由到 MCP Tool → 外部问数服务 → 结果渲染 | 关闭 | data_natural_query |

*注：Hidden CoT（隐式思考链）仅在高幻觉风险 Agent（知识库、合同分析）启用，避免结构化 Agent 产生不必要的 Scratchpad 存储开销。*

-----

## 7. 智能问数对接方案

通过 DeerFlow MCP 机制完全解耦，不修改 DeerFlow 源码。HarnessToolInterceptor 在调用外部问数服务前强制覆写 tenant_id 和 user_id，确保数据权限边界。

```
调用链路：
自然语言 → Semantic Router 命中 data_query 
        → DataQuery Agent Skill 
        → HarnessToolInterceptor（强制参数覆写 + 注入检测） 
        → MCP Tool: data_natural_query 
        → HTTP POST 
        → 外部智能问数服务 
        → 返回 {sql, rows, chart_suggestion, nl_explanation} 
        → 飞书图表卡片渲染 / 表格展示
```

接口约定：外部问数服务需在请求头接受 X-Tenant-ID 和 X-User-ID，在结果集中携带数据域标识（finance/sales/hr），以便平台层进行 ABAC 行列过滤。

-----

## 8. Skill 广场体系

### 8.1 Skill 元数据

```yaml
id: contract-review-v2
version: 2.1.0
category: legal
permissions: [compliance, manager, admin]
status: published
harness_required: true     # 此 Skill 必须启用 Harness 拦截
scratchpad_enabled: true   # 启用 Hidden CoT 审计落库
```

### 8.2 生命周期管理

开发者提交 → 自动化安全扫描（含 Harness 兼容性检查）→ 人工合规审批 → 上架。Skill 上架 / 下架时触发 Semantic Router 热更新（不重启服务）。用户安装后，仅将已授权 Skill 向量化注入该用户的专属路由上下文，不全量注入 Token。

-----

## 9. 可观测与链路追踪

双路追踪架构：Langfuse 捕获 LLM 内部 Prompt/Token 细节；OpenTelemetry 覆盖系统级业务 Trace。在 OTel Span 中新增 Harness 层专属属性。

| 监控指标 | 说明 | 告警阈值 |
| ---- | ---- | ---- |
| Semantic Router 命中率 | 极速路由覆盖比例，直接反映成本节约 | < 70% 告警 |
| Harness 拦截次数 | 按拦截类型分布（注入 / 越权 / 白名单） | 突增 > 3x 告警 |
| Scratchpad 覆盖率 | 高风险 Agent 审计完整性 | < 100% 严重告警 |
| Agent 端到端延迟 P99 | 用户体验核心指标 | > 15s 告警 |
| 沙箱预热池存活率 | gVisor Pod 可用性 | < 80% 告警 |
| Token 消耗趋势 | 按租户 / Agent 维度，成本管控 | 超预算 20% 告警 |
| Critic 重试率 | Agent 输出质量代理指标 | > 15% 告警 |

-----

## 10. 权限与数据安全

### 10.1 多租户五层隔离体系

| 隔离层级 | 技术实现 |
| ---- | ---- |
| L1 网关层 | 拦截非法 Tenant Token |
| L2 Harness 层 | HarnessToolInterceptor 强制参数覆写 |
| L3 应用层 | Thread State 按 tenant 分区 |
| L4 存储层 | PostgreSQL RLS + Milvus Collection 过滤 |
| L5 沙箱层 | gVisor 内核隔离 + NetworkPolicy Egress 阻断 |

### 10.2 加密矩阵

| 数据类型 | 传输加密 | 存储加密 | 保留期 |
| ---- | ---- | ---- | ---- |
| 用户对话内容 | TLS 1.3 | AES-256 | 180 天 |
| Scratchpad 内容 | TLS 1.3 | AES-256（单独列族） | 永久 |
| 合同文本 | TLS 1.3 | AES-256 | 10 年 |
| 发票数据 | TLS 1.3 | AES-256 | 7 年 |
| 审计日志 | TLS 1.3 | AES-256 | 永久 |
| 向量索引 | 内网 | —（原文不入索引） | 随文档 |

-----

## 11. 部署架构

```yaml
services:
  enterprise-gateway:  { replicas: 3, image: 'kong:3.6' }
  deerflow-backend:    { replicas: 4, resources: {cpu: '4', memory: '8Gi'} }
  deerflow-gateway:    { replicas: 2 }   # 飞书/IM 通道
  auth-service:        { replicas: 3 }   # 自建权限服务
  skill-marketplace:   { replicas: 2 }   # Skill 广场
  harness-monitor:     { replicas: 2 }   # 新增：Harness 规则热更新服务

# 核心状态组件（PostgreSQL RLS、Milvus、Redis）均采用跨 AZ（可用区）高可用部署。灾备容忍度指标 RPO < 1 分钟，RTO < 5 分钟，保障金融合规连续性要求。
datastores:
  milvus:     { replicas: 3, storage: '500Gi' }
  postgresql: { replicas: 3, storage: '100Gi', rls: true, mode: patroni-ha, rpo_target: "< 1min", rto_target: "< 5min" }
  redis:      { replicas: 3, mode: 'sentinel' }
  minio:      { replicas: 4, storage: '2Ti' }
  kafka:      { replicas: 3 }
  clickhouse: { replicas: 2, storage: '1Ti' }  # Scratchpad 单独列族
```

-----

## 12. 技术栈汇总

| 层次 | 组件 | 来源 |
| ---- | ---- | ---- |
| 编排引擎 | LangGraph 1.0 | DeerFlow |
| 基础框架 | LangChain | DeerFlow |
| Harness 层 | 自研 HarnessInterceptor | 自建 |
| 沙箱引擎 | gVisor(runsc) + K3s | 自配 |
| 路由模型 | BAAI/bge-small-zh-v1.5 | 自配 |
| 记忆系统 | DeerFlow Memory + 脱注水 | 深度定制 |
| API 网关 | Kong / APISIX | 自建 |
| 通道集成 | DeerFlow Gateway | 扩展 |
| 数据库 | PG(RLS) + Milvus + Redis | 自配 |
| 审计系统 | Kafka + ClickHouse | 自配 |
| 可观测 | OTel + Langfuse + Grafana | 自配 |
| 主力模型 | Doubao-Pro / DeepSeek V3 / Qwen 等| API |
| 提炼模型 | Qwen 或 DeepSeek 等 | 本地 |

**模型降级热切机制**：在 API Gateway 层配置大模型熔断策略。当 Doubao/DeepSeek/Qwen 公有云 API 延迟超标或宕机时，系统支持一键无缝切流至私有化本地部署，确保核心业务不中断。

-----

## 13. 实施路线图与团队配置

### 13.1 二开核心原则

**外挂而非侵入原则**

- 不修改 DeerFlow 源码，通过继承、拦截器、MCP 扩展叠加企业能力
- 依赖版本锁定：deer-flow==2.0.x、langgraph==1.0.x、langchain==0.3.x
- Harness 层作为独立服务部署，与 DeerFlow 核心服务解耦
- 上游 DeerFlow 更新时，企业安全层只需更新依赖版本，不需要 rebase

### 13.2 实施时间轴（10 个月）

| 阶段 | 月份 | 核心交付 |
| ---- | ---- | ---- |
| 基座搭建 | M1-M2 | 企业网关、DeerFlow 核心、基础 RBAC、Semantic Router、知识库 Agent |
| Harness 构建 | M3-M4 | HarnessToolInterceptor、Scratchpad 审计、脱注水机制、gVisor 沙箱 POC |
| 业务深水区 | M5-M6 | 双向脱敏、审计流水、MCP 智能问数对接、财务报销、金融审批 Agent |
| 平台化运营 | M7-M8 | Skill 广场内部版、Memory 守护进程、Harness Monitor 服务上线 |
| 生产就绪 | M9-M10 | 全链路压测、蓝红对抗演练、第三方安全审计、Harness 规则库沉淀、全面投产 |

### 13.3 团队配置（13 人）

| 角色 | 人数 | 核心职责 |
| ---- | ---- | ---- |
| 平台架构师 | 2 | 整体架构决策，DeerFlow 与企业基础设施联调 |
| Harness Engineer | 2 | 维护 gVisor 预热池、开发 ToolInterceptor 规则、调优 Semantic Router 命中率、编写 Critic 一票否决逻辑。把业务 Agent 当作不受信任的第三方代码对待 |
| 业务 Agent 工程师 | 4 | 懂金融业务，写 Prompt、画 LangGraph 业务节点、定义审批流程 |
| AI 算法工程师 | 2 | 意图分类优化、RAG 召回调优、提炼模型微调 |
| 前端工程师 | 1 | Skill 广场 UI、对话界面 |
| 安全工程师 | 1 | RBAC 设计、渗透测试、合规审查 |
| 运维工程师 | 1 | K8s、监控告警、CI/CD |

**职能边界说明**

- 业务 Agent 工程师：关心「Agent 做什么」
- Harness Engineer：关心「Agent 能做什么、不能做什么、做了什么」
- 两者相互独立，Harness 层对业务层拥有一票否决权

-----

## 14. 二开可行性与风险评估

### 14.1 可行性综合评分

| 评估维度 | 核心考量点（基于 DeerFlow 二开） | 得分 (1-10) | 权重 | 加权分 |
| ---- | ---- | ---- | ---- | ---- |
| 开源协议与合规 | DeerFlow 采用原生 MIT 协议，对商业闭源二开无任何传染性限制，完全满足金融私有化部署合规要求。 | 9.5 | 20% | 1.90 |
| 架构扩展性 | DeerFlow 底层基于 LangGraph，DAG 状态机设计天生适合中间件插拔。方案中设计的 Harness Interceptor 极易以装饰器或节点回调形式挂载，无需侵入核心源码。 | 9.0 | 25% | 2.25 |
| 企业能力匹配度 | DeerFlow 偏向纯粹的编排内核，原生缺乏 RBAC、动态网关和审计列族。通过强力的外部“安全壳”弥补了这一点，基座只做执行器，定位匹配。 | 7.5 | 20% | 1.50 |
| 安全机制适配度 | 原生 K3s/Docker 无法满足金融防逃逸，但架构支持自定义沙箱 Provisioner，替换为 gVisor 路径清晰；原生 Memory 可通过重写子类实现“脱水/注水”。 | 8.5 | 20% | 1.70 |
| 维护可持续性 | 严格遵循依赖版本锁定与 Adapter 模式，上游代码的激进重构（如底层更换组件）导致代码冲突的风险被外部网关和 Harness 隔离，维护成本可控。 | 8.0 | 15% | 1.20 |
| 综合可行性得分 | 核心结论：高度可行，架构防御力拉满，二开切入点设计极其合理。 | — | 100% | |



### 14.2 风险分级矩阵

| 风险项 | 概率 | 影响 | 等级 | 应对策略 |
| ---- | ---- | ---- | ---- | ---- |
| 字节跳动来源合规审查 | 中 | 高 | 🔴 高 | 提前供应链评估；金融监管行业单独立项 |
| 上游激进重构维护成本 | 高 | 中 | 🔴 高 | 外挂原则，不修改源码；锁定次级版本 |
| gVisor 与 K8s 兼容性 | 中 | 中 | 🟡 中 | M3 阶段 POC 验证；备选 Kata Containers |
| Semantic Router 命中率不足 | 中 | 中 | 🟡 中 | 冷启动期降阈值至 0.75；持续采集负样本 |
| Scratchpad 审计数据膨胀 | 中 | 低 | 🟡 中 | ClickHouse 列式压缩；90 天热转冷 |
| 记忆脱水 Schema 版本漂移 | 低 | 中 | 🟡 中 | Schema 版本号管理；兼容旧格式降级读取 |
| 多租户数据泄露 | 低 | 极高 | 🟡 中 | L1-L5 五层隔离；Harness 强制参数覆写 |
| 沙箱未做第三方安全审计 | 中 | 高 | 🟡 中 | M9 阶段强制安全审计后方可全量上线 |
| MIT 许可证商业使用 | 极低 | 低 | 🟢 低 | 无需处理，可闭源商用 |
