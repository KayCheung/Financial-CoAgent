# 企业级 Agent 平台完整技术方案

> **版本**：v1.5
> **技术基座**：DeerFlow 2.0 + LangGraph 1.0 + LangChain 0.3
> **目标场景**：金融企业私有化部署 · 安全可控 · 成本可量化
> **核心立场**：大模型是高级运算器，生杀大权由传统确定性代码掌握

---

## 目录

1. [融合架构总览](#1-融合架构总览)
2. [控制塔 Harness 层（完整实现）](#2-控制塔-harness-层完整实现)
   - 2.1 Token Budget 守护机制
   - 2.2 工具拦截器（含规则热更新）
   - 2.3 Scratchpad 分片压缩审计
   - 2.4 跨线程资源锁注册表
3. [规划层：防死锁编排引擎](#3-规划层防死锁编排引擎)
4. [三层记忆模型（完整实现）](#4-三层记忆模型完整实现)
   - 4.1 L1 即时轨分片存储
   - 4.2 L2 情节记忆（Event-Sourced Diffs）
   - 4.3 L3 语义记忆（租户隔离检索）
5. [HITL 三段式审批状态机](#5-hitl-三段式审批状态机)
6. [Semantic Router（冷启动优化）](#6-semantic-router冷启动优化)
7. [沙箱执行层（分级隔离）](#7-沙箱执行层分级隔离)
8. [Skill 中心（生命周期治理）](#8-skill-中心生命周期治理)
9. [企业安全壳与容灾](#9-企业安全壳与容灾)
10. [可观测性工具链](#10-可观测性工具链)
11. [成本控制体系](#11-成本控制体系)
12. [部署规格](#12-部署规格)
13. [实施 Roadmap](#13-实施-roadmap)
14. [风险应对矩阵](#14-风险应对矩阵)

---

## 1. 融合架构总览

### 1.1 分层架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        感知层 Perception                         │
│  [Web/Mobile/IM/API] → [边缘网关: 限流·JWT·PII边缘脱敏]          │
│                     → [Semantic Router: 向量+影子验证]            │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│           ★ 控制塔 Harness Layer（一票否决权）★                  │
│  [Token Budget 守护] → [全局策略引擎 ABAC]                       │
│  [Tool Interceptor: 身份覆写·AST校验·叶节点嗅探]                 │
│  [Scratchpad: 分片存储·风险全量落库·越权熔断]                    │
│  [熔断器: 模型降级·幂等校验·WAL双写]                             │
│  [全局工具锁注册表: 跨线程死锁防护]                              │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                      规划层 Planning                             │
│  [LangGraph DAG: 环路检测·Planner自纠错]                         │
│  [HITL 三段式状态机: 资源快照·补偿事务·超时有感知否决]           │
└──────────────────────────────┬──────────────────────────────────┘
                               │
        ┌──────────────────────┴───────────────────┐
        │                                          │
┌───────▼──────────────────────┐    ┌──────────────▼───────────────┐
│       三层记忆 Memory         │    │       执行层 Execution        │
│  L1: Redis 分片即时轨         │    │  Sub-Agent Executor(DAG并发)  │
│  L2: PG 情节库(Schema v化)    │    │  Sandbox: gVisor/runc/Process │
│  L3: Milvus 向量(租户隔离)    │    │  MCP + Legacy Adapter         │
│  Dehydrate/Hydrate 版本化     │    │  Skill 中心(版本锁定·热分发)  │
└──────────────────────────────┘    └──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                    能力基础层 Foundation                          │
│  [LLM 统一网关: Doubao/DeepSeek/Qwen·热切降级]                   │
│  [RAG: 混合召回·BGE-Reranker精排]                                │
│  [可观测: Langfuse + OTel + Grafana · 尾部采样]                  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 核心设计原则

| 原则 | 来源思想 | 落地机制 |
|---|---|---|
| 工具闭环与自主进化 | Boris Cherny (Claude Code) | 沙箱三级隔离、长任务 DAG 拆解、Critic 自纠错 |
| 标准化与生态协同 | Harrison Chase (LangChain) | LangGraph 状态机、MCP 工具链抽象、Multi-Agent 协作 |
| 认知基础设施 | Henry Li (DeerFlow) | Harness 封装、三层记忆模型、Skill 原子化 |
| 工程确定性 | Mitchell Hashimoto | 可复现 DAG、硬边界约束、WAL 审计不丢失 |

### 1.2.1 架构收敛声明

本方案遵循“少数硬约束优先，其余能力按风险增强”的建设原则，不追求以复杂控制面覆盖所有不确定性。平台级默认硬约束仅保留三类：

1. 下游系统边界硬约束  
包括租户隔离、权限控制、资金类禁写、Tool Schema 与接口级参数约束。凡可由下游业务系统或网关确定性兜底的能力，不在 Agent 控制面重复实现。

2. 状态与审计可恢复硬约束  
包括事件日志、快照检查点、WAL、统一失败态分类与回放恢复能力。平台必须保证线程状态、审计证据链和异常归宿在故障条件下仍可恢复、可解释、可追责。

3. 发布准入硬约束  
包括 Evaluation 回放、基线建立、关键指标门禁与发布阻断机制。任何模型、Prompt、Skill、Router 或工具契约变更，均应先经过离线验证，再进入灰度与生产。

除上述三类硬约束外，其余能力均视为风险增强项，包括但不限于强沙箱、影子验证、复杂路由防护、OCR 局部升维、细粒度审计增强等。这类能力应依据业务风险等级、租户敏感级别、成本预算和运行阶段按需启用，而不作为平台首期闭环的默认前提。

本方案的目标不是用更多控制逻辑“包围”大模型，而是以尽可能少、但足够硬的确定性边界，使其余组件即使局部失效，也不会演化为系统级不可控风险。

### 1.3 场景推演：财务自动化审计

```
触发: CFO 提交「Q3 财务审计」任务
  │
  ├─[感知层] SR 命中 finance_audit (置信度 0.93, 5% 抽样影子验证)
  │
  ├─[Harness] Token Budget 分配: 50,000 tokens
  │           ABAC: 验证 finance_manager 角色 + 审计权限
  │           Tool Interceptor: 强制注入 tenant_id=finance_div
  │
  ├─[规划层] Planner 生成 DAG (拓扑排序通过，无环):
  │           task_1: 发票 OCR 提取 (gVisor Tier1)
  │           task_2: 科目映射校验 (并行, 依赖 task_1)
  │           task_3: 合规红线比对 (并行, 依赖 task_1)
  │           task_4: 差异风险报告 (依赖 task_2 + task_3)
  │
  ├─[执行层] task_2 + task_3 并发执行:
  │           重结果 (MB级) → OSS (经对象存储适配层落盘，Claim-Check)
  │           状态指针 (URI) → Redis CAS 更新
  │           全局工具锁: oracle_legacy_conn 申请槽位 (max 30s)
  │
  ├─[Critic]  发现 3 张发票金额超授权阈值
  │           CriticVetoResult { rule:"FINANCE_002", severity:"high" }
  │           executor_retry_count = 1, 携带错误上下文重试
  │
  ├─[HITL]   快照已消耗资源 (Pod IDs + Object keys)
  │           推送飞书审批卡片 → 财务总监
  │           超时前 30min 催办 → 财务总监批准 [附注: 特批]
  │           补偿事务: 已释放预占沙箱资源
  │
  ├─[记忆层] 决策指纹 → L2 PG + WAL (RocksDB)
  │           异步 → Kafka → ClickHouse 永久留存
  │
 └─[输出]   结构化审计报告 (屏蔽 Scratchpad 中间推理) + OA 工单
             ★ 资金划拨操作被 Harness 硬性拦截，仅输出报告 ★
```

### 1.4 LLM 能力分层与准入机制

> 原则：**统一的是调用协议，不统一能力承诺。**  
> LLM 统一网关负责接入、鉴权、审计、限流、熔断与切流；模型是否可承担某类节点职责，必须由独立的能力准入机制判定，不能因为接入协议统一就默认模型可互换。

#### 设计目标

1. 避免“Tier B / Tier C 可线性替代”的错误假设
2. 将模型差异显式前置到设计层，而不是运行期碰撞
3. 为 Planner / Critic / 路由兜底 / 报告生成等节点定义最低能力门槛
4. 将降级从“模型切换”收敛为“能力兼容前提下的切换”

#### 能力分层

| 能力标签 | 含义 | 典型适用节点 |
|---|---|---|
| `structured_output_strict` | 严格输出 JSON / Schema，不漂移字段 | Planner、Critic、状态抽取 |
| `tool_calling_stable` | 工具调用服从性稳定，低幻觉参数 | Planner、Executor |
| `long_context_reliable` | 长上下文下保持信息完整与引用稳定 | 报告生成、合同审查 |
| `finance_chinese_reasoning` | 中文金融术语、票据、审批语境理解稳定 | 财务审计、合规审批 |
| `low_latency_router` | 低延迟分类与路由稳定性 | 路由兜底分类 |

#### 节点准入矩阵

| 节点类型 | 最低能力要求 | 可用模型池 | 不满足时策略 |
|---|---|---|---|
| Planner | `structured_output_strict` + `tool_calling_stable` | 主力模型 / 经验证轻量模型 | 缩小任务范围或失败，不假降级 |
| Critic | `structured_output_strict` + `finance_chinese_reasoning` | 主力模型优先 | 回退规则引擎 + HITL |
| 路由兜底 | `low_latency_router` | 轻量模型优先 | 路由到默认安全 Skill |
| 报告生成 | `long_context_reliable` + `finance_chinese_reasoning` | 主力模型 | 摘要化后重试或转人工 |

#### 准入与降级原则

1. 模型注册到统一网关前，必须先进入“能力注册表”
2. “能力注册表”记录模型版本、评测分、适用节点、禁止节点
3. 降级仅允许发生在“能力兼容”前提下
4. 若不存在能力兼容的替代模型，则允许：
   - 缩小任务范围
   - 转入 HITL
   - 显式失败
5. 不允许因为成本压力将关键节点降级到未通过能力准入的模型

#### 设计结论

统一网关负责“接入一致性”，能力注册表负责“能力一致性”。  
文档后续所有涉及模型热切、熔断、降级的能力，均默认受本节约束。

---

## 2. 控制塔 Harness 层

> Harness 是整套架构的"硬骨头"。所有安全、成本、权限控制收拢于此，由专职 Harness Engineer 维护。

### 2.1 Token Budget 守护机制

**设计目标**：Planner+Critic 双向重试最多触发 6 次 LLM 调用，Token 成本必须有硬上限。

```python
import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class TokenTier(Enum):
    """Token 消耗三层分级"""
    TIER_A = "rule_engine"      # 零 Token: 规则引擎、格式校验、工具白名单
    TIER_B = "lightweight_llm"  # 低成本: 边界分类、短摘要、离线评估回放
    TIER_C = "primary_llm"      # 高成本: 复杂推理、合同分析、财务报告

@dataclass
class TokenBudget:
    """Thread 级别 Token 预算对象（不可变约束）"""
    thread_id: str
    tenant_id: str
    task_complexity: str          # simple / moderate / complex
    total_budget: int             # 按任务复杂度预分配
    consumed: int = 0
    degraded: bool = False        # 是否已触发降级
    degraded_at: Optional[int] = None  # 降级时已消耗量
    created_at: float = field(default_factory=time.time)

    @classmethod
    def allocate(cls, thread_id: str, tenant_id: str, task_complexity: str) -> "TokenBudget":
        """按任务复杂度预分配 Token 预算"""
        budgets = {
            "simple":   5_000,    # 普通问答、日程查询
            "moderate": 20_000,   # 合同审查、财务报销
            "complex":  50_000,   # 季度审计、复杂编排
        }
        return cls(
            thread_id=thread_id,
            tenant_id=tenant_id,
            task_complexity=task_complexity,
            total_budget=budgets.get(task_complexity, 10_000),
        )

    @property
    def remaining(self) -> int:
        return self.total_budget - self.consumed

    @property
    def usage_ratio(self) -> float:
        return self.consumed / self.total_budget if self.total_budget > 0 else 0.0


class TokenBudgetGuard:
    """
    Token Budget 守护器
    职责: 消耗追踪、超阈值降级、超预算硬熔断、异步指标上报
    """
    DEGRADATION_THRESHOLD = 0.70   # 70% 消耗触发成本保护：仅在能力兼容前提下收缩任务
    HARD_LIMIT_THRESHOLD  = 0.95   # 95% 消耗触发硬熔断

    # Redis Lua：幂等计费（同一个 operation_id 只累计一次）
    _CONSUME_LUA = """
    local counter_key = KEYS[1]
    local op_set_key  = KEYS[2]
    local op_id       = ARGV[1]
    local tokens      = tonumber(ARGV[2])
    local ttl_secs    = tonumber(ARGV[3])

    if redis.call('SISMEMBER', op_set_key, op_id) == 1 then
        return tonumber(redis.call('GET', counter_key) or '0')
    end

    redis.call('SADD', op_set_key, op_id)
    redis.call('EXPIRE', op_set_key, ttl_secs)
    local total = redis.call('INCRBY', counter_key, tokens)
    redis.call('EXPIRE', counter_key, ttl_secs)
    return total
    """

    def __init__(self, budget: TokenBudget, metrics_reporter, audit_logger, redis_client):
        self._budget = budget
        self._metrics = metrics_reporter
        self._audit = audit_logger
        self._redis = redis_client
        self._lock = asyncio.Lock()
        self._counter_key = f"token_budget:{budget.tenant_id}:{budget.thread_id}:consumed"
        self._op_set_key = f"token_budget:{budget.tenant_id}:{budget.thread_id}:ops"
        self._ttl_secs = 86400

    async def consume(
        self,
        tokens: int,
        tier: TokenTier,
        operation: str,
        operation_id: Optional[str] = None,
    ) -> None:
        """
        消耗 Token 并检查阈值。
        Tier A（规则引擎）直接跳过，零消耗。
        """
        if tier == TokenTier.TIER_A:
            return  # 规则引擎零消耗，直接放行

        # 全局累加（多 Pod 一致）；若 Redis 不可用，降级到进程内计数并打告警
        try:
            if operation_id:
                global_total = await self._redis.eval(
                    self._CONSUME_LUA,
                    2,
                    self._counter_key,
                    self._op_set_key,
                    operation_id,
                    tokens,
                    self._ttl_secs,
                )
            else:
                # 未提供 operation_id 时走普通累计，避免生成大规模幂等索引
                global_total = await self._redis.incrby(self._counter_key, tokens)
                await self._redis.expire(self._counter_key, self._ttl_secs)
            self._budget.consumed = int(global_total)
        except Exception:
            async with self._lock:
                self._budget.consumed += tokens
            asyncio.create_task(self._audit.warn(
                f"[Budget] Redis 全局计数不可用，已降级本地计数（仅临时容错）: thread={self._budget.thread_id}"
            ))

        ratio = self._budget.usage_ratio

        # 异步上报指标（不阻塞主链路）
        asyncio.create_task(self._metrics.record(
            thread_id=self._budget.thread_id,
            tenant_id=self._budget.tenant_id,
            consumed=tokens,
            total_consumed=self._budget.consumed,
            operation=operation,
            operation_id=operation_id or "",
            tier=tier.value,
        ))

        # 70% 触发成本保护告警
        if ratio >= self.DEGRADATION_THRESHOLD and not self._budget.degraded:
            self._budget.degraded = True
            self._budget.degraded_at = self._budget.consumed
            asyncio.create_task(self._audit.warn(
                f"[Budget] Thread {self._budget.thread_id} 已消耗 {ratio:.0%}，"
                f"触发成本保护: 优先缩小任务范围 / 降低并发 / 仅在能力兼容时切换模型"
            ))

        # 95% 触发硬熔断
        if ratio >= self.HARD_LIMIT_THRESHOLD:
            asyncio.create_task(self._audit.error(
                f"[Budget] Thread {self._budget.thread_id} 超预算，强制熔断。"
                f"已消耗: {self._budget.consumed}/{self._budget.total_budget}"
            ))
            raise TokenBudgetExhaustedException(
                f"Token 预算耗尽: {self._budget.consumed}/{self._budget.total_budget}。"
                f"任务 {self._budget.thread_id} 已终止。"
            )

    def should_degrade(self) -> bool:
        """供 Planner/Executor 查询：当前是否应降级到轻量模型"""
        return self._budget.degraded

    def get_recommended_tier(self) -> TokenTier:
        """根据当前消耗情况，推荐调用哪一层模型"""
        if self._budget.usage_ratio >= self.DEGRADATION_THRESHOLD:
            return TokenTier.TIER_B  # 仅表示进入低成本通道，具体模型仍受能力准入约束
        return TokenTier.TIER_C      # 正常调用主力模型

    @property
    def snapshot(self) -> dict:
        return {
            "thread_id": self._budget.thread_id,
            "consumed": self._budget.consumed,
            "total": self._budget.total_budget,
            "ratio": f"{self._budget.usage_ratio:.1%}",
            "degraded": self._budget.degraded,
        }
```

### 2.2 工具拦截器（薄如蝉翼的旁路化设计）

在明确了不涉及资金划拨等核心交易后，所有的正则嗅探、内容匹配均剥离主链路。Harness Layer（实时拦截层）采用 **“同步极简校验 + 异步旁路拦截”** 的双轨模型。
大模型被视为“不严谨但无恶意的拼装工”。平台只负责它拼装的零件尺寸对不对（Schema验），并在包裹上贴上它的指纹标签（租户与身份强行覆写）。违禁品检查交给大门外的安检机（异步旁路引擎和业务线下游自身）。

```python
import jsonschema
import asyncio
from dataclasses import dataclass

class ThinToolInterceptor:
    """
    轻量级同步拦截器（耗时 < 5ms）
    核心原则: 只做快速的类型判断与上下文强覆盖，防呆不防贼。
    防贼的活交给异步 DLP 和下游业务网关。
    """
    @staticmethod
    async def intercept(
        tool_name: str, 
        raw_params: dict, 
        env_context, 
        async_audit_queue: asyncio.Queue
    ) -> tuple[dict, dict]:
        
        # ──【卡点 1：业务白名单鉴权（O(1) 内存查询）】──
        if tool_name not in env_context.allowed_tools:
            raise PermissionError(f"本租户 [{env_context.tenant_id}] 暂无工具 {tool_name} 的使用权")

        # ──【卡点 2：身份强制覆写 - 绝对防线】──
        # 不管大模型造了什么身份参数，全部用 Gateway 解析出来的 JWT 上下文硬质覆盖生效。
        safe_params = {
            **raw_params,
            "tenant_id": env_context.tenant_id,
            "operator_id": env_context.user_id,
        }

        # ──【卡点 3：Schema 层基础校验】──
        # 仅仅做 JSON 数据类型、Required字段校验。
        # 不对 text 叶节点执行海量正则（Regex）扫描
        tool_schema = get_schema_from_registry(tool_name)
        if tool_schema:
            try:
                jsonschema.validate(instance=safe_params, schema=tool_schema)
            except jsonschema.ValidationError as e:
                # 给大模型抛出明确的结构化异常，便于它 Critic 重试
                raise ValueError(f"参数结构错误，请遵循 Schema: {e.message}")

        # ──【旁路分支：推入异步 DLP/审计队列】──
        # 此处不 await 阻塞！直接将入参塞给异步队列风控系统。
        # 即使其中有敏感词，本次 API 调用也先行通过。风控系统若几秒后察觉异常，可以直接采取“封号/切断长连接”操作。
        asyncio.create_task(async_audit_queue.put({
            "trace_id": env_context.trace_id,
            "tenant_id": env_context.tenant_id,
            "tool": tool_name,
            "params_snapshot": safe_params,
            "timestamp": env_context.request_time
        }))

        # 构建标准的透传 Headers，交给 Executor
        downstream_headers = {
            "X-Tenant-ID": env_context.tenant_id,
            "X-Operator-ID": env_context.user_id,
            "X-Trace-ID": env_context.trace_id,
            "X-Harness-Checked": "true" 
        }

        return safe_params, downstream_headers
```

### 2.3 Scratchpad 分片压缩审计

L1 即时轨按 `step_id` 分片（每片 ≤ 64KB），超过阈值触发滚动压缩（保留最近20步全量 + 历史仅保留决策指纹），全量审计模式写入走独立异步队列。

```python
import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional

MAX_SHARD_SIZE_BYTES = 64 * 1024    # 每片上限 64KB
MAX_FULL_SHARDS      = 20           # 保留最近 20 步全量
ROLLING_COMPRESS_AT  = 30           # 超过 30 步触发滚动压缩

@dataclass
class ScratchpadShard:
    """不可变推理步骤分片"""
    shard_id: str           # f"{thread_id}:step:{step_idx}"
    step: str               # 步骤名称
    content: str            # 推理内容（原始）
    fingerprint: str        # 决策指纹（压缩后保留）
    timestamp: float
    is_high_risk: bool = False
    is_full_audit: bool = False  # 是否进入全量审计轨

class HarnessScratchpad:
    """
    双轨 Scratchpad
    即时轨 (L1, Redis 分片): 全量推理暂存，会话结束自动释放
    合规轨 (ClickHouse):     决策指纹 + 高风险全量，永久留存
    """

    def __init__(self, thread_id: str, rule_engine, audit_queue, redis_client):
        self.thread_id = thread_id
        self._rule_engine = rule_engine
        self._audit_queue = audit_queue     # 独立异步写入队列（不阻塞主链路）
        self._redis = redis_client

        self._step_count = 0
        self._force_full_audit = False      # 高风险全量审计开关
        self._shard_keys: List[str] = []    # Redis Key 索引

    async def write(self, step: str, content: str) -> None:
        # ── 1. 安全扫描（同步，必须先于写入）──
        security_report = self._rule_engine.scan(content)

        # ── 2. 状态切换：命中高风险，进入全量审计模式 ──
        if security_report.is_high_risk:
            self._force_full_audit = True

        # ── 3. 违规优先处理：先留审计证据，再熔断，不写 Redis L1 ──
        if security_report.has_violations:
            await self._audit_queue.put({
                "thread_id": self.thread_id,
                "shard_id": None,
                "step": step,
                "content": content,   # 违规场景必须留全量证据
                "is_violation": True,
                "audit_reason": "violation_blocked_before_l1",
                "violations": security_report.violations,
                "ts": time.time(),
            })
            raise HarnessSecurityException(
                f"Agent 推理越界熔断: {security_report.violations}"
            )

        # ── 4. 通过校验后再分配 step_idx，避免违规路径污染序号 ──
        self._step_count += 1
        step_idx = self._step_count
        shard_key = f"scratchpad:{self.thread_id}:step:{step_idx}"

        # ── 5. 构建分片 ──
        shard = ScratchpadShard(
            shard_id=shard_key,
            step=step,
            content=content,
            fingerprint=self._extract_fingerprint(content),
            timestamp=time.time(),
            is_high_risk=security_report.is_high_risk,
            is_full_audit=self._force_full_audit,
        )

        # ── 6. 写入 Redis L1（分片存储，TTL = 会话生命周期）──
        shard_data = json.dumps({
            "step": shard.step,
            "content": shard.content,
            "fingerprint": shard.fingerprint,
            "ts": shard.timestamp,
            "full_audit": shard.is_full_audit,
        })

        # 检查分片大小是否超限
        if len(shard_data.encode()) > MAX_SHARD_SIZE_BYTES:
            # 超限则截断内容，完整内容仅走审计队列
            truncated = {**json.loads(shard_data), "content": "[TRUNCATED→AUDIT]"}
            shard_data = json.dumps(truncated)

        await self._redis.setex(shard_key, 86400, shard_data)  # TTL 24h
        self._shard_keys.append(shard_key)

        # ── 7. 滚动压缩：超过阈值，压缩旧分片 ──
        if step_idx > ROLLING_COMPRESS_AT:
            await self._rolling_compress(step_idx)

        # ── 8. 合规轨落库（独立异步队列，不阻塞推理）──
        should_audit = (
            self._force_full_audit
            or self._is_decision_fingerprint(content)
        )
        if should_audit:
            await self._audit_queue.put({
                "thread_id": self.thread_id,
                "shard_id": shard_key,
                "step": step,
                # 全量模式写完整内容，否则只写指纹
                "content": content if self._force_full_audit else shard.fingerprint,
                "is_violation": security_report.has_violations,
                "audit_reason": "full_mode" if self._force_full_audit else "fingerprint",
                "ts": shard.timestamp,
            })

    async def _rolling_compress(self, current_step: int) -> None:
        """
        滚动压缩策略:
        - 保留最近 MAX_FULL_SHARDS (20) 步全量内容
        - 更早的分片: 清除 content，只保留 fingerprint + metadata
        - 压缩后 Redis 内存占用降低 ~85%
        """
        compress_before = current_step - MAX_FULL_SHARDS
        if compress_before <= 0:
            return

        keys_to_compress = [
            k for k in self._shard_keys
            if int(k.split(":step:")[-1]) <= compress_before
        ]

        for key in keys_to_compress:
            raw = await self._redis.get(key)
            if not raw:
                continue
            data = json.loads(raw)
            if "content" in data and data.get("content") != "[COMPRESSED]":
                # 仅保留指纹，释放 content 大字符串
                data["content"] = "[COMPRESSED]"
                data["compressed_at"] = time.time()
                await self._redis.setex(key, 86400, json.dumps(data))

    def _extract_fingerprint(self, content: str) -> str:
        """
        提取决策指纹:
        - 工具调用意图
        - 任务拆解锚点
        - 状态变更关键词
        实现: 轻量 NLP 规则匹配（零 Token 消耗）
        """
        import re
        patterns = [
            r"(调用工具|tool_call|invoke)[：:]\s*(\w+)",
            r"(任务拆解|子任务|subtask)[：:]\s*(.{0,50})",
            r"(状态变更|stage|转移)[：:]\s*(\w+)",
        ]
        fingerprints = []
        for p in patterns:
            m = re.search(p, content, re.IGNORECASE)
            if m:
                fingerprints.append(m.group(0)[:100])
        return " | ".join(fingerprints) if fingerprints else content[:200]

    def _is_decision_fingerprint(self, content: str) -> bool:
        """判定是否为关键决策锚点（需落入合规轨）"""
        keywords = ["tool_call", "调用工具", "任务拆解", "状态变更", "审批", "转账", "提交"]
        return any(kw in content for kw in keywords)

    def get_final_output(self) -> str:
        """对用户只返回最后一步结论，中间推理全部屏蔽"""
        # 从最新分片中读取最终输出
        if not self._shard_keys:
            return ""
        # 实际实现中从 Redis 异步读取最后一个分片
        return "[FINAL_OUTPUT_FROM_LAST_SHARD]"

    async def cleanup(self) -> None:
        """会话结束：批量删除 L1 即时轨，零长期成本"""
        if self._shard_keys:
            await self._redis.delete(*self._shard_keys)


# ── 独立 ClickHouse 异步写入消费者（与主链路解耦）──
async def audit_queue_consumer(audit_queue: asyncio.Queue, ch_client):
    """
    独立协程: 消费审计队列，批量写入 ClickHouse。
    批次大小: 100 条 或 5 秒触发一次写入，降低 CH 写入压力。
    """
    BATCH_SIZE = 100
    FLUSH_INTERVAL = 5.0
    buffer = []
    last_flush = time.time()

    while True:
        try:
            entry = await asyncio.wait_for(audit_queue.get(), timeout=FLUSH_INTERVAL)
            buffer.append(entry)
        except asyncio.TimeoutError:
            pass

        should_flush = (
            len(buffer) >= BATCH_SIZE
            or (time.time() - last_flush >= FLUSH_INTERVAL and buffer)
        )
        if should_flush:
            try:
                await ch_client.insert("agent_scratchpad_audit", buffer)
                last_flush = time.time()
                buffer.clear()
            except Exception as e:
                # 写入失败: 写入本地 WAL，绝不丢失
                for entry in buffer:
                    await local_wal.put(entry)
                buffer.clear()
```

### 2.4 全局工具锁注册表

本节对数据库连接、遗留系统会话、独占型工具等共享资源实施有限等待与显式失败，避免跨线程静默死锁。

```python
import asyncio
import random
import time
import uuid
from dataclasses import dataclass
from typing import Dict, Optional

@dataclass
class ToolLockEntry:
    """工具锁槽位（配置 + 本地观测镜像）"""
    tool_name: str
    max_concurrency: int    # 该工具允许的最大并发持有数
    current_holders: int = 0
    waiters: int = 0

class GlobalToolLockRegistry:
    """
    全局工具锁注册表（Redis 分布式信号量 + 本地观测镜像）
    解决: 多 Pod 部署下并发上限失真问题
    """

    # 工具并发配置（从 Nacos 热加载）
    DEFAULT_CONCURRENCY = {
        "oracle_legacy_conn":   3,    # 遗留 Oracle 连接池: 最多 3 并发
        "invoice_ocr":         10,    # OCR 服务: 最多 10 并发
        "oa_submit":            5,    # OA 提交: 最多 5 并发
        "risk_query":           8,    # 风控查询: 最多 8 并发
        "*":                   20,    # 默认工具: 最多 20 并发
    }

    def __init__(self, redis_client, metrics_reporter):
        self._registry: Dict[str, ToolLockEntry] = {}
        self._redis = redis_client
        self._metrics = metrics_reporter
        self._init_registry()

    # Redis Lua: 原子申请槽位（ZSET 记录持有者，自动剔除过期 holder）
    _ACQUIRE_LUA = """
    local holders_key = KEYS[1]
    local holder_key  = KEYS[2]
    local max_conc    = tonumber(ARGV[1])
    local lease_ms    = tonumber(ARGV[2])
    local now_ms      = tonumber(ARGV[3])
    local holder_id   = ARGV[4]

    -- 清理过期 holder，避免配额泄漏
    redis.call('ZREMRANGEBYSCORE', holders_key, '-inf', now_ms)

    if redis.call('EXISTS', holder_key) == 1 then
        redis.call('PEXPIRE', holder_key, lease_ms)
        redis.call('ZADD', holders_key, now_ms + lease_ms, holder_id)
        return 1
    end

    local current = tonumber(redis.call('ZCARD', holders_key) or '0')
    if current >= max_conc then
        return 0
    end

    redis.call('PSETEX', holder_key, lease_ms, '1')
    redis.call('ZADD', holders_key, now_ms + lease_ms, holder_id)
    return 1
    """

    # Redis Lua: 原子续租（长任务防止 lease 过期）
    _RENEW_LUA = """
    local holders_key = KEYS[1]
    local holder_key  = KEYS[2]
    local lease_ms    = tonumber(ARGV[1])
    local now_ms      = tonumber(ARGV[2])
    local holder_id   = ARGV[3]

    if redis.call('EXISTS', holder_key) == 1 then
        redis.call('PEXPIRE', holder_key, lease_ms)
        redis.call('ZADD', holders_key, now_ms + lease_ms, holder_id)
        return 1
    end
    return 0
    """

    # Redis Lua: 原子释放一个并发槽位
    _RELEASE_LUA = """
    local holders_key = KEYS[1]
    local holder_key  = KEYS[2]
    local holder_id   = ARGV[1]

    redis.call('DEL', holder_key)
    redis.call('ZREM', holders_key, holder_id)
    return 1
    """

    def _init_registry(self):
        for tool_name, max_conc in self.DEFAULT_CONCURRENCY.items():
            self._registry[tool_name] = ToolLockEntry(
                tool_name=tool_name,
                max_concurrency=max_conc,
            )

    def _get_entry(self, tool_name: str) -> ToolLockEntry:
        """获取工具锁条目，未注册的工具使用默认配置"""
        return self._registry.get(tool_name, self._registry["*"])

    def _holders_key(self, tool_name: str) -> str:
        return f"tool_lock:{tool_name}:holders"

    def _holder_key(self, tool_name: str, holder_id: str) -> str:
        return f"tool_lock:{tool_name}:holder:{holder_id}"

    async def _acquire_redis_slot(
        self,
        tool_name: str,
        holder_id: str,
        holder_key: str,
        max_concurrency: int,
        lease_ms: int,
    ) -> bool:
        now_ms = int(time.time() * 1000)
        result = await self._redis.eval(
            self._ACQUIRE_LUA,
            2,
            self._holders_key(tool_name),
            holder_key,
            max_concurrency,
            lease_ms,
            now_ms,
            holder_id,
        )
        return int(result) == 1

    async def _renew_redis_slot(self, tool_name: str, holder_id: str, holder_key: str, lease_ms: int) -> bool:
        now_ms = int(time.time() * 1000)
        result = await self._redis.eval(
            self._RENEW_LUA,
            2,
            self._holders_key(tool_name),
            holder_key,
            lease_ms,
            now_ms,
            holder_id,
        )
        return int(result) == 1

    async def _release_redis_slot(self, tool_name: str, holder_id: str, holder_key: str) -> None:
        await self._redis.eval(
            self._RELEASE_LUA,
            2,
            self._holders_key(tool_name),
            holder_key,
            holder_id,
        )

    async def reconcile_expired(self, tool_name: str) -> None:
        """
        后台 Janitor 可周期调用，主动清理过期 holder（无新请求时也能回收配额）。
        """
        now_ms = int(time.time() * 1000)
        await self._redis.zremrangebyscore(self._holders_key(tool_name), "-inf", now_ms)

    async def acquire(
        self,
        tool_name: str,
        thread_id: str,
        timeout: float = 30.0,
        lease_ms: int = 60000,
    ) -> "ToolLockContext":
        """
        申请工具执行槽位。
        - 等待超时: 30s，超时后抛出 RESOURCE_CONTENTION 错误（进入 Critic 重试）
        - 不静默挂起，保证 SLA 可测量
        - 生产建议增加后台续租任务，避免超长执行导致 holder 过期
        """
        entry = self._get_entry(tool_name)
        entry.waiters += 1
        waiter_registered = True
        holder_id = f"{thread_id}:{uuid.uuid4().hex}"
        holder_key = self._holder_key(tool_name, holder_id)
        deadline = time.time() + timeout

        # 上报等待状态
        asyncio.create_task(self._metrics.record(
            "tool_lock_wait",
            tool=tool_name,
            thread_id=thread_id,
            waiters=entry.waiters,
        ))

        try:
            backoff = 0.02       # 20ms 起步
            max_backoff = 0.50   # 最高 500ms
            while time.time() < deadline:
                acquired = await self._acquire_redis_slot(
                    tool_name=tool_name,
                    holder_id=holder_id,
                    holder_key=holder_key,
                    max_concurrency=entry.max_concurrency,
                    lease_ms=lease_ms,
                )
                if acquired:
                    entry.waiters = max(0, entry.waiters - 1)
                    waiter_registered = False
                    entry.current_holders += 1

                    asyncio.create_task(self._metrics.record(
                        "tool_lock_acquired",
                        tool=tool_name,
                        thread_id=thread_id,
                        current_holders=entry.current_holders,
                    ))
                    return ToolLockContext(
                        entry=entry,
                        tool_name=tool_name,
                        holder_id=holder_id,
                        holder_key=holder_key,
                        lease_ms=lease_ms,
                        registry=self,
                    )

                # 指数退避 + 抖动，降低高并发下 Redis 热点与惊群效应
                await asyncio.sleep(backoff * random.uniform(0.8, 1.2))
                backoff = min(backoff * 1.6, max_backoff)

            raise ResourceContentionException(
                f"工具 [{tool_name}] 等待超时 ({timeout}s)，"
                f"当前排队: {entry.waiters}，并发上限: {entry.max_concurrency}。"
                f"错误类型: RESOURCE_CONTENTION，可触发 Critic 重试。"
            )
        finally:
            if waiter_registered:
                entry.waiters = max(0, entry.waiters - 1)

    async def renew(self, tool_name: str, holder_id: str, holder_key: str, lease_ms: int) -> bool:
        return await self._renew_redis_slot(tool_name, holder_id, holder_key, lease_ms)

    async def release(self, tool_name: str, holder_id: str, holder_key: str) -> None:
        entry = self._get_entry(tool_name)
        entry.current_holders = max(0, entry.current_holders - 1)
        await self._release_redis_slot(tool_name, holder_id, holder_key)

    def update_concurrency(self, tool_name: str, new_max: int) -> None:
        """Nacos 热更新并发配置（分布式配额立即生效）"""
        if tool_name in self._registry:
            self._registry[tool_name].max_concurrency = new_max


class ToolLockContext:
    """工具锁上下文管理器，支持 async with"""

    def __init__(
        self,
        entry: ToolLockEntry,
        tool_name: str,
        holder_id: str,
        holder_key: str,
        lease_ms: int,
        registry: GlobalToolLockRegistry,
    ):
        self._entry = entry
        self._tool_name = tool_name
        self._holder_id = holder_id
        self._holder_key = holder_key
        self._lease_ms = lease_ms
        self._registry = registry
        self._stop = asyncio.Event()
        self._heartbeat_task: Optional[asyncio.Task] = None

    async def _heartbeat(self):
        """续租心跳：避免长任务 lease 过期导致并发超发。"""
        base = max(1.0, self._lease_ms / 3000)
        while not self._stop.is_set():
            await asyncio.sleep(base * random.uniform(0.9, 1.1))
            renewed = await self._registry.renew(
                self._tool_name,
                self._holder_id,
                self._holder_key,
                self._lease_ms,
            )
            if not renewed:
                await self._registry._metrics.record(
                    "tool_lock_lease_lost",
                    tool=self._tool_name,
                    holder=self._holder_id,
                )
                break

    async def __aenter__(self):
        self._heartbeat_task = asyncio.create_task(self._heartbeat())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._stop.set()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        await self._registry.release(self._tool_name, self._holder_id, self._holder_key)


# ── 使用示例（在 Executor 中）──
async def execute_with_lock(tool_name: str, thread_id: str, lock_registry: GlobalToolLockRegistry):
    async with await lock_registry.acquire(tool_name, thread_id, timeout=30.0):
        # 安全区: 工具执行逻辑
        result = await call_legacy_oracle(thread_id)
        return result
```

---

## 3. 规划层：防死锁编排引擎

### 3.1 LangGraph 状态定义与防死锁 DAG

本节以最小控制态驱动企业级编排，将大对象外置，并在运行期补充 DAG 合法性校验，保证流程可恢复、可审计、可熔断。

```python
import time
from typing import Dict, List, TypedDict, Annotated, Optional

class AgentFastState(TypedDict):
    """
    极简 Fast State（仅存流转控制字段）
    大对象不进 State，走对象存储 Claim-Check 模式
    """
    thread_id:              str
    tenant_id:              str
    task_input:             str
    task_complexity:        str                   # simple/moderate/complex
    stage:                  str
    start_time:             float

    # Planner 防死锁
    plan_retry_count:       int                   # Planner 重试次数（上限 2）
    last_planner_error:     str                   # 上一次 Planner 失败原因

    # Executor 业务重试
    executor_retry_count:   int                   # Executor 重试次数（上限 3）
    last_executor_error:    str                   # 上一次 Executor 失败原因（结构化）
    active_tasks:           List[str]             # 当前执行中的子任务 ID

    # DAG
    current_dag:            Dict[str, List[str]]  # 任务依赖图

    # 大对象指针（对象存储 URI 字典）
    payload_refs:           Annotated[Dict[str, str], "merge"]

    # Critic 结果
    is_safe:                bool
    is_accurate:            bool
    requires_approval:      bool
    critic_veto_reason:     Optional[str]         # 结构化否决原因（供重试携带）

    # HITL
    approval_id:            Optional[str]
    approved:               Optional[bool]
    approval_resource_snapshot: Optional[dict]    # HITL 前资源快照（用于补偿）

    # Token Budget
    token_consumed:         int


def detect_cycle(dag: Dict[str, List[str]]) -> bool:
    """拓扑排序环路检测（DFS）"""
    visited, rec_stack = set(), set()

    def dfs(node: str) -> bool:
        visited.add(node)
        rec_stack.add(node)
        for neighbor in dag.get(node, []):
            if neighbor not in visited:
                if dfs(neighbor):
                    return True
            elif neighbor in rec_stack:
                return True
        rec_stack.discard(node)
        return False

    return any(dfs(n) for n in dag if n not in visited)


def task_planner_node(state: AgentFastState) -> dict:
    """
    Planner 节点：生成 DAG + 运行时环路拦截 + 携带错误上下文自纠错
    """
    # 携带上一轮错误上下文，让模型有针对性地修正
    prompt = f"Task: {state['task_input']}"
    if state.get("last_planner_error"):
        prompt += f"\n[修正要求] 上次计划存在问题: {state['last_planner_error']}，请修正后重新生成。"

    raw_plan = llm_invoke(prompt)
    parsed_dag = parse_plan_to_dag(raw_plan)

    # 运行时环路检测
    if detect_cycle(parsed_dag):
        retry = state.get("plan_retry_count", 0)
        if retry < 2:
            return {
                "plan_retry_count": retry + 1,
                "last_planner_error": "您生成的计划包含环路/死锁，请重新规划。",
            }
        else:
            raise ValueError(f"Planner 连续 {retry+1} 次生成非法 DAG，触发硬性熔断。")

    return {
        "current_dag":          parsed_dag,
        "stage":                "executing",
        "last_planner_error":   "",           # 清空错误
        "plan_retry_count":     0,            # 成功后重置计数
    }


def route_after_planner(state: AgentFastState) -> str:
    """Planner 后路由：有错误则回旋，否则放行"""
    if state.get("last_planner_error"):
        return "planner"    # 回旋重规划
    return "executor"


def route_after_critic(state: AgentFastState) -> str:
    """
    Critic 后全局路由：
    1. 全局超时熔断（30min）
    2. 校验通过 → HITL 或 Memory
    3. 校验失败 → 携带结构化错误上下文重试
    4. 重试耗尽 → END
    """
    thread_id = state["thread_id"]

    # 全局超时硬熔断
    elapsed = time.time() - state.get("start_time", time.time())
    if elapsed > 1800:  # 30 分钟
        logger.error(f"Thread {thread_id} 超时熔断 ({elapsed:.0f}s)")
        return "END"

    # 校验通过
    if state.get("is_safe") and state.get("is_accurate"):
        return "human_approval" if state.get("requires_approval") else "memory"

    # 校验失败，触发重试
    retry_count = state.get("executor_retry_count", 0)
    if retry_count < 3:
        logger.warning(f"Thread {thread_id}: 校验失败，第 {retry_count+1}/3 次重试。"
                       f"原因: {state.get('critic_veto_reason')}")
        return "executor"

    # 重试耗尽
    logger.error(f"Thread {thread_id}: 连续 3 次失败，任务终止。")
    return "END"


def build_enterprise_workflow():
    """构建企业级 LangGraph 工作流"""
    from langgraph.graph import StateGraph, END

    graph = StateGraph(AgentFastState)

    graph.add_node("semantic_router",  semantic_router_node)
    graph.add_node("planner",          task_planner_node)
    graph.add_node("executor",         sub_agent_executor_node)
    graph.add_node("critic",           critic_validation_node)
    graph.add_node("human_approval",   human_approval_node)
    graph.add_node("memory",           memory_update_node)

    graph.set_entry_point("semantic_router")
    graph.add_edge("semantic_router", "planner")

    # Planner 自纠错环路
    graph.add_conditional_edges("planner", route_after_planner, {
        "planner":  "planner",
        "executor": "executor",
    })

    graph.add_edge("executor", "critic")

    # Critic 全局路由
    graph.add_conditional_edges("critic", route_after_critic, {
        "human_approval": "human_approval",
        "memory":         "memory",
        "executor":       "executor",
        "END":            END,
    })

    graph.add_edge("human_approval", "memory")
    graph.add_edge("memory",         END)

    return graph.compile(checkpointer=enterprise_redis_checkpointer)
```

### 3.2 边界条件与失败处理

> **【架构准则：全栈失败态枚举收敛】**
> 为防止 Planner、Executor、Critic 及外部挂起模块（如异步 OCR）各自发散定义报错，本平台在底层定义唯一的失败流转终止态枚举 `AgentFailureState`。任何节点抛出的异常最终必须显式映射至此三类，严禁向下游或外部系统抛出无定向的空白 `ERROR`，确保业务侧状态机和审计报表口径能够做到三端合一。

```python
from enum import Enum

class AgentFailureState(Enum):
    RETRYABLE     = "retryable"      # 系统级或可重试异常（如并发表竞争、网络抖动、LLM 偶发超时、容器分配挂起），交回 Controller/Graph 重试
    HUMAN_REVIEW  = "human_review"   # 业务阻断或不可信异常（如 HITL 前置拦截、OCR 传回格式损坏、资金越权报警），强制挂起转入审批或人工接管轨
    FAILED_CLOSED = "failed_closed"  # 硬性熔断不可恢复异常（如 Token 预算触发 95% 限额、强依赖 DB 彻底宕机、严重越权漏洞），结束当前执行线程并触底告警
```


| 场景 | 风险 | 处理策略 |
|---|---|---|
| Planner 输出空 DAG | 任务静默完成或进入错误终态 | 视为结构非法，计入 `plan_retry_count` |
| DAG 节点依赖不存在 | Executor 启动后悬空等待 | 编译前执行依赖完整性校验 |
| DAG 无环但存在孤立节点 | 部分任务永不执行 | 识别孤立节点并拒绝进入执行态 |
| Planner 输出结构合法但业务不可执行 | 运行中连续报错，成本失控 | Critic 结构化回传 `last_planner_error`，触发有限重规划 |
| Executor 部分成功后重试 | 重复调用外部系统，产生副作用 | 每个节点强制幂等键，已完成节点跳过执行 |
| Graph Checkpoint 写入失败 | 无法恢复线程状态 | 主链路标记 `CHECKPOINT_DEGRADED`，回落到 PG/WAL 保底 |

#### 规则补充

1. `Planner`、`Executor`、`Critic` 三类节点都必须具备幂等键
2. `AgentFastState` 仅存控制态，不存不可重放的大对象
3. 任一节点进入 `executing` 前，必须完成：
   - DAG 环路检测
   - 依赖完整性校验
   - 孤立节点校验
4. 连续失败达到上限后，必须产生可审计终态，不允许线程挂起在中间状态

---

## 4. 三层记忆模型

### 4.1 L1 即时轨（分片 Redis，会话级）

L1 实现已内嵌在 `HarnessScratchpad` 的分片存储中（见 §2.3）。核心参数：

| 参数 | 值 | 说明 |
|---|---|---|
| 单片上限 | 64 KB | 超限截断，完整内容走审计队列 |
| 全量保留步数 | 最近 20 步 | 旧步骤压缩为指纹 |
| 滚动压缩触发 | 30 步 | 旧分片内存释放 ~85% |
| TTL | 24h | 会话结束自动删除 |

在具体实现上，L1 对应“滚动窗口记忆”：默认保留最近 3-5 轮原始对话与最近若干执行步骤，优先保证当前任务的强相关上下文不被摘要误伤。  
当会话持续拉长时，L1 仍保留最新窗口的原样内容，较早片段则交由 L2 结构化沉淀，不让短期上下文与长期记忆混在同一层。

### 4.2 L2 情节记忆（Event-Sourced Diffs）

本节采用事件化持久化而非轻量模型“脱水总结”。在金融语境下，状态压缩最怕的不是格式不合法，而是语义静默损坏。  
L2 采用 **“事实对象快照 + 事件增量日志 + 可回放投影”**：优先保留原始结构化状态的增量变化，用存储换取上下文准确性和恢复确定性。

在实现形态上，L2 由三类对象组成：

1. 事实对象快照：任务、审批、票据、实体抽取结果等强结构化对象，直接持久化，不经过模型改写。
2. 事件增量日志：每次 `Planner / Executor / Critic / HITL` 产生的状态变化，记录为 append-only diff。
3. 可回放投影：按线程或任务维度将事件流重放成当前状态，供运行时恢复与审计复盘。

这样设计的目的，是让“长期记忆”建立在状态机和事件流之上。模型可以继续参与推理，但不作为系统状态保存的唯一解释器。

```python
import json
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List

STATE_SCHEMA_VERSION = 3

@dataclass(frozen=True)
class StateEvent:
    thread_id: str
    event_id: str
    event_type: str          # planner_updated / tool_finished / critic_veto / hitl_approved
    step_id: str
    ts: float
    payload: Dict[str, Any]  # 仅记录变更字段


def build_state_diff(previous: dict, current: dict) -> dict:
    """
    生成增量差异:
    - 只记录有变化的字段
    - 保留结构化对象，不做自然语言总结
    """
    diff = {}
    keys = set(previous.keys()) | set(current.keys())
    for key in keys:
        if previous.get(key) != current.get(key):
            diff[key] = current.get(key)
    return diff


async def append_state_event(
    thread_id: str,
    step_id: str,
    event_type: str,
    previous_state: dict,
    current_state: dict,
    redis_client,
    pg_store,
) -> None:
    diff = build_state_diff(previous_state, current_state)
    event = StateEvent(
        thread_id=thread_id,
        event_id=generate_monotonic_id(),
        event_type=event_type,
        step_id=step_id,
        ts=time.time(),
        payload={
            "schema_version": STATE_SCHEMA_VERSION,
            "diff": diff,
        },
    )

    # Redis 存最新投影，PostgreSQL 持久化原始事件流
    await redis_client.set(
        f"thread_projection:{thread_id}",
        json.dumps(current_state, ensure_ascii=False),
        ex=86400,
    )
    await pg_store.insert_event(asdict(event))


async def rebuild_thread_state(thread_id: str, redis_client, pg_store) -> dict:
    """
    上下文恢复顺序:
    1. 优先读取 Redis 最新投影（低延迟）
    2. 未命中时，从 PG 事件流回放
    """
    projection = await redis_client.get(f"thread_projection:{thread_id}")
    if projection:
        return json.loads(projection)

    events: List[dict] = await pg_store.list_events(thread_id)
    if not events:
        return {"status": "NOT_FOUND", "thread_id": thread_id}

    rebuilt = {
        "schema_version": STATE_SCHEMA_VERSION,
        "thread_id": thread_id,
        "intent": "",
        "stage": "initiated",
        "pending_actions": [],
        "key_entities": {},
        "last_error": "",
        "token_consumed": 0,
    }

    for event in events:
        rebuilt.update(event["payload"]["diff"])

    # 回填 Redis 投影，下一次读取直接命中
    await redis_client.set(
        f"thread_projection:{thread_id}",
        json.dumps(rebuilt, ensure_ascii=False),
        ex=86400,
    )
    return rebuilt
```

#### 设计约束

1. L2 的可靠性以前后可回放的事件流为前提，而不是小模型摘要成功率。
2. 任意时刻都可以从 PG 事件流重建线程状态，不依赖某次摘要是否正确。
3. Schema 版本升级只影响投影器与迁移器，不改写历史事件本体。
4. 如确需生成面向模型的短上下文，只能作为派生视图缓存，不能反向覆盖系统状态。

### 4.3 L3 语义记忆（Milvus 租户隔离检索）

本节面向跨线程可复用知识片段召回，并在检索链路中强化租户隔离、结果二次校验与防御性过滤。

在召回阶段，L3 不单独决定最终上下文，而是作为“语义补充记忆”参与多路融合。  
查询时默认同时召回 L1 滚动窗口、L2 结构化实体/摘要、L3 语义相似片段，再按权重合成为最终上下文。

```python
from pymilvus import Collection, connections, utility

class TenantAwareVectorStore:
    """
    租户感知向量存储
核心: 每个 Skill 绑定独立 Collection，检索时强制注入租户过滤条件
    """

    def __init__(self, milvus_host: str, milvus_port: int):
        connections.connect(host=milvus_host, port=milvus_port)

    def _get_collection(self, collection_name: str) -> Collection:
        if not utility.has_collection(collection_name):
            raise VectorStoreException(f"Collection [{collection_name}] 不存在")
        return Collection(collection_name)

    async def search(
        self,
        query_embedding: list,
        collection_name: str,
        tenant_id: str,
        top_k: int = 5,
    ) -> list:
        """
        向量检索。
        关键: 强制注入 tenant_id 过滤条件，不允许跨租户命中。
        """
        collection = self._get_collection(collection_name)
        collection.load()

        results = collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"nprobe": 16}},
            limit=top_k,
            # 强制过滤条件: 只返回本租户数据
            expr=f'tenant_id == "{tenant_id}"',
            output_fields=["doc_id", "chunk_text", "skill_id", "tenant_id"],
        )

        hits = []
        for hit in results[0]:
            # 二次校验（防御性编程）
            if hit.entity.get("tenant_id") != tenant_id:
                logger.critical(
                    f"[SECURITY] 跨租户数据泄露阻断! "
                    f"期望: {tenant_id}, 实际: {hit.entity.get('tenant_id')}"
                )
                continue  # 硬性过滤，绝不返回
            hits.append({
                "doc_id":     hit.entity.get("doc_id"),
                "chunk":      hit.entity.get("chunk_text"),
                "skill_id":   hit.entity.get("skill_id"),
                "score":      hit.score,
                "tenant_id":  hit.entity.get("tenant_id"),
            })

        return hits
```

查询融合策略建议如下：

| 记忆层 | 默认权重 | 作用 |
|---|---|---|
| L1 滚动窗口 | 0.50 | 保留最近强相关上下文，优先回答当前轮问题 |
| L2 实体/摘要 | 0.30 | 补足用户目标、任务进展、关键实体 |
| L3 语义召回 | 0.20 | 补足跨线程知识片段与历史经验 |

权重不是固定不变，而应随场景调整：

1. 对话问答场景：L1 权重更高
2. 长周期任务跟进场景：L2 权重更高
3. 知识型检索场景：L3 权重更高

这样处理后，当前方案中的三层记忆不只是“分层存储”，而是形成“滚动窗口 + 关键实体 + 周期摘要 + 语义召回”的协同机制。

```python
async def recall_memory(query: str, thread_id: str, tenant_id: str, scene: str) -> dict:
    """
    三层记忆融合召回:
    1. L1: 最近 3-5 轮滚动窗口
    2. L2: 关键实体 + 周期摘要
    3. L3: 语义相似片段
    """
    l1_window  = await load_recent_window(thread_id, last_n_rounds=5)
    l2_profile = await load_structured_memory(thread_id)
    l3_hits    = await vector_store.search(query_embedding(query), "skills_memory", tenant_id)

    weights = {
        "dialogue":    {"l1": 0.60, "l2": 0.25, "l3": 0.15},
        "long_task":   {"l1": 0.35, "l2": 0.45, "l3": 0.20},
        "knowledge":   {"l1": 0.20, "l2": 0.30, "l3": 0.50},
    }.get(scene, {"l1": 0.50, "l2": 0.30, "l3": 0.20})

    return {
        "recent_context": l1_window,
        "entity_memory":  l2_profile.get("key_entities", {}),
        "summary_memory": l2_profile.get("summary", ""),
        "semantic_hits":  rerank_by_weight(l3_hits, weights["l3"]),
        "weights":        weights,
    }
```

### 4.4 多租户隔离与 RLS 实现策略

> 租户隔离不能只依赖应用层 `tenant_id` 注入，必须形成“接入层 + 应用层 + 存储层 + 检索层 + 对象层”的多层硬隔离体系。

#### 4.4.1 接入层与应用层

1. JWT 中必须携带 `tenant_id`、`user_id`、`role`
2. Gateway 验签后将租户上下文写入只读环境上下文，后续链路不信任客户端原始传参
3. Harness 对所有工具调用强制覆写：
   - `tenant_id`
   - `operator_id`
   - `request_id`
4. 任一请求缺失租户上下文时，直接返回 `TENANT_CONTEXT_REQUIRED`

#### 4.4.2 PostgreSQL + RLS

设计要求：

1. 核心业务表统一包含 `tenant_id`
2. 生产环境默认开启 `ROW LEVEL SECURITY`
3. 应用连接建立后必须注入会话变量 `app.current_tenant`
4. 后台管理与审计角色不直接绕过 RLS，跨租户查询走专用审计通道并留痕

```sql
ALTER TABLE agent_memory ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_policy
ON agent_memory
USING (tenant_id = current_setting('app.current_tenant')::text);
```

应用侧约束：

```sql
SET app.current_tenant = 'finance_div';
SET app.current_user   = 'u_12345';
```

#### 4.4.3 Milvus / 向量检索

| 场景 | 默认策略 | 高敏升级策略 |
|---|---|---|
| 多中小租户 | 共享 Collection + `tenant_id` 过滤 | 分 Partition |
| 金融核心租户 | Skill 维度独立 Collection | 租户独立 Collection |
| 极高敏场景 | 不建议仅依赖元数据过滤 | 独立 Milvus 实例/逻辑集群 |

补充原则：

1. 检索时强制注入 `tenant_id` 过滤
2. 返回结果必须做二次校验
3. 对高敏租户，默认至少做到 `partition/collection` 级隔离，不以过滤条件作为唯一防线

#### 4.4.4 Redis / OSS / Claim-Check

| 组件 | 默认隔离策略 | 高敏升级策略 |
|---|---|---|
| Redis | key namespace 带 `tenant_id` 前缀 | 独立 DB / 独立实例 |
| OSS / 对象存储 | 按租户前缀或 Bucket 隔离 | 独立 Bucket + KMS 租户密钥 |
| Claim-Check URI | 返回受控引用，不暴露真实对象路径 | 引入短时令牌与一次性访问策略 |

#### 4.4.5 五层硬隔离总结

1. API 层：JWT + Gateway 注入只读租户上下文
2. Harness 层：强制覆写 + 工具白名单 + 请求级审计
3. PG 层：`tenant_id` + RLS + 会话变量
4. Vector 层：租户过滤条件 + collection / partition 隔离
5. Object / Cache 层：租户命名空间 + KMS + 受控 Claim-Check
6. 存储后端通过对象存储适配层统一接入，默认使用阿里云 OSS，并允许基于环境与成本策略切换到其他兼容对象存储实现

> 后续所有“租户隔离”字样，如无特别说明，均指上述五层共同生效，而非单一过滤条件。

---

## 5. HITL 三段式审批状态机

本节将人工审批从“流程暂停点”提升为可审计的状态机节点，统一处理超时否决、资源补偿与审批回调。
在操作分级上，删除、修改、批量写入等高风险动作除发起人确认外，还应强制同步通知第二责任人（如主管或值班负责人），避免单点误决策直接落地。

```python
import asyncio
import random
import uuid
import time
from dataclasses import dataclass, field
from typing import Optional, dict
from enum import Enum

class ApprovalStatus(Enum):
    PENDING            = "pending"
    APPROVED           = "approved"
    REJECTED           = "rejected"
    TIMEOUT_VETO       = "timeout_veto"
    COMPENSATING       = "compensating"   # 补偿事务执行中
    COMPENSATION_DONE  = "compensation_done"

@dataclass
class ApprovalRecord:
    """审批记录（幂等主键: approval_id）"""
    approval_id: str
    thread_id: str
    tenant_id: str
    initiator_id: str
    approver_id: str
    task_summary: str
    risk_level: str                    # normal / high / urgent
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: float = field(default_factory=time.time)
    decided_at: Optional[float] = None
    decision_note: Optional[str] = None

    # 资源快照（用于补偿事务）
    resource_snapshot: dict = field(default_factory=dict)

    @classmethod
    def create(cls, thread_id: str, tenant_id: str, initiator_id: str,
               approver_id: str, task_summary: str, risk_level: str,
               resource_snapshot: dict) -> "ApprovalRecord":
        return cls(
            approval_id=str(uuid.uuid4()),
            thread_id=thread_id,
            tenant_id=tenant_id,
            initiator_id=initiator_id,
            approver_id=approver_id,
            task_summary=task_summary,
            risk_level=risk_level,
            resource_snapshot=resource_snapshot,
        )

    @property
    def timeout_seconds(self) -> int:
        """按风险等级设置差异化超时"""
        return {"normal": 86400, "high": 14400, "urgent": 3600}.get(self.risk_level, 86400)


class HITLApprovalStateMachine:
    """
    HITL 三段式状态机:
    PENDING → APPROVED/TIMEOUT_VETO → COMPENSATING → COMPENSATION_DONE
    """

    def __init__(self, pg_store, im_client, audit_logger, resource_compensator):
        self._pg = pg_store
        self._im = im_client
        self._audit = audit_logger
        self._compensator = resource_compensator
        self._poll_sem = asyncio.Semaphore(200)   # 单 Pod 轮询并发上限，避免压垮 PG
        # 不使用进程内 asyncio.Event，审批等待统一基于 PG 持久态，支持跨 Pod/重启恢复

    async def recover_pending_on_startup(self) -> None:
        """
        进程启动恢复：扫描 PENDING 审批并写审计标记，确保重启后可持续追踪。
        """
        pending = await self._pg.list_approvals_by_status(ApprovalStatus.PENDING, limit=5000)
        await self._audit.log({
            "type": "HITL_RECOVER_PENDING",
            "count": len(pending),
            "ts": time.time(),
        })

    async def submit(self, record: ApprovalRecord) -> str:
        """
        提交审批（幂等: 相同 thread_id + task_summary 的重复提交直接返回原 approval_id）
        """
        # 幂等检查
        existing = await self._pg.find_pending_approval(record.thread_id)
        if existing:
            logger.info(f"Thread {record.thread_id} 已有审批 {existing.approval_id}，返回原记录")
            return existing.approval_id

        # 持久化审批记录
        await self._pg.save_approval(record)

        # 发送审批卡片（飞书/钉钉）
        await self._im.send_approval_card(
            to=record.approver_id,
            approval_id=record.approval_id,
            task_summary=record.task_summary,
            risk_level=record.risk_level,
            timeout_hint=f"{record.timeout_seconds // 3600}h",
        )
        return record.approval_id

    async def wait_for_decision(self, approval_id: str, record: ApprovalRecord) -> bool:
        """
        等待审批决策，含提前催办 + 超时有感知否决。
        """
        timeout = record.timeout_seconds
        remind_at = timeout * 0.75   # 75% 时发送催办（例: 24h 审批在 18h 时催办）

        async def _remind_task():
            await asyncio.sleep(remind_at)
            latest = await self._pg.get_approval(approval_id)
            if latest.status == ApprovalStatus.PENDING:
                await self._im.send_reminder(
                    to=record.approver_id,
                    approval_id=approval_id,
                    message=(
                        f"⚠️ 审批提醒: 任务「{record.task_summary[:50]}」"
                        f"将在 {(timeout - remind_at) // 3600:.1f}h 后超时自动否决，请及时处理。"
                    ),
                )

        async def _poll_decision() -> ApprovalStatus:
            # 轮询持久态：Pod 重启后可继续等待，不依赖内存 Event
            interval = 0.5 if record.risk_level == "urgent" else 2.0
            max_interval = 5.0 if record.risk_level == "urgent" else 15.0
            async with self._poll_sem:
                while True:
                    updated = await self._pg.get_approval(approval_id)
                    if updated.status in (
                        ApprovalStatus.APPROVED,
                        ApprovalStatus.REJECTED,
                        ApprovalStatus.TIMEOUT_VETO,
                    ):
                        return updated.status
                    await asyncio.sleep(interval * random.uniform(0.9, 1.1))
                    interval = min(interval * 1.5, max_interval)

        remind_task = asyncio.create_task(_remind_task())

        try:
            final_status = await asyncio.wait_for(_poll_decision(), timeout=float(timeout))
            remind_task.cancel()
            return final_status == ApprovalStatus.APPROVED

        except asyncio.TimeoutError:
            remind_task.cancel()
            logger.warning(f"审批 {approval_id} 超时，执行有感知否决")

            # 防止与审批回调并发覆盖：先读最新状态
            latest = await self._pg.get_approval(approval_id)
            if latest.status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED):
                return latest.status == ApprovalStatus.APPROVED

            # CAS 更新状态，避免与 on_decision 并发覆盖
            updated = await self._pg.compare_and_set_status(
                approval_id=approval_id,
                from_status=ApprovalStatus.PENDING,
                to_status=ApprovalStatus.TIMEOUT_VETO,
            )
            if not updated:
                latest = await self._pg.get_approval(approval_id)
                return latest.status == ApprovalStatus.APPROVED

            # 通知发起人（有感知，非静默）
            await self._im.notify(
                to=record.initiator_id,
                message=(
                    f"⚠️ 审批任务「{record.task_summary[:50]}」已超时，系统自动否决。\n"
                    f"如需继续，请重新发起并选择「紧急审批」通道（1h 超时）。"
                ),
            )

            # 写入审计
            await self._audit.log({
                "type": "HITL_TIMEOUT_VETO",
                "approval_id": approval_id,
                "thread_id": record.thread_id,
                "resource_snapshot": record.resource_snapshot,
            })

            # 触发资源补偿事务
            await self._trigger_compensation(approval_id, record)
            return False

    async def _trigger_compensation(self, approval_id: str, record: ApprovalRecord) -> None:
        """
        资源补偿事务:
        释放 HITL 前已预占的沙箱 Pod、对象存储对象等资源，防止泄漏。
        """
        await self._pg.update_approval_status(approval_id, ApprovalStatus.COMPENSATING)
        try:
            snapshot = record.resource_snapshot
            if "sandbox_pod_ids" in snapshot:
                for pod_id in snapshot["sandbox_pod_ids"]:
                    await self._compensator.release_sandbox(pod_id)
            if "object_store_keys" in snapshot:
                for key in snapshot["object_store_keys"]:
                    await self._compensator.release_object(key)

            await self._pg.update_approval_status(approval_id, ApprovalStatus.COMPENSATION_DONE)
            logger.info(f"审批 {approval_id} 资源补偿完成: {snapshot}")
        except Exception as e:
            logger.error(f"审批 {approval_id} 资源补偿失败: {e}，已写入告警")
            await self._audit.error(f"COMPENSATION_FAILED: {approval_id}: {e}")

    async def on_decision(self, approval_id: str, approved: bool, note: str = "") -> None:
        """审批人决策回调（由飞书 Webhook 触发）"""
        status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        updated = await self._pg.compare_and_set_status(
            approval_id=approval_id,
            from_status=ApprovalStatus.PENDING,
            to_status=status,
            decided_at=time.time(), decision_note=note,
        )
        if not updated:
            latest = await self._pg.get_approval(approval_id)
            if latest.status == ApprovalStatus.TIMEOUT_VETO:
                await self._im.notify(
                    to=latest.approver_id,
                    message=f"审批 {approval_id} 已超时否决，本次决策未生效。",
                )
        # 等待方通过轮询 PG 自动感知状态变化，无需内存 Event


# ── HITL 节点（注入 LangGraph）──
async def human_approval_node(state: AgentFastState) -> dict:
    """HITL LangGraph 节点"""
    # 在进入 HITL 前，快照当前已占用的资源
    resource_snapshot = {
        "sandbox_pod_ids":  state.get("active_sandbox_pods", []),
        "object_store_keys": list(state.get("payload_refs", {}).values()),
    }

    record = ApprovalRecord.create(
        thread_id=state["thread_id"],
        tenant_id=state["tenant_id"],
        initiator_id=state.get("initiator_id", ""),
        approver_id=state.get("approver_id", ""),
        task_summary=state["task_input"][:200],
        risk_level=state.get("risk_level", "normal"),
        resource_snapshot=resource_snapshot,
    )

    approval_id = await hitl_state_machine.submit(record)
    approved = await hitl_state_machine.wait_for_decision(approval_id, record)

    return {
        "approval_id": approval_id,
        "approved":    approved,
        "stage":       "approved" if approved else "rejected",
    }
```

---

## 6. Semantic Router

```python
import asyncio
import random
import json
import time
from opentelemetry import trace
from dataclasses import dataclass
from typing import List, Optional

tracer = trace.get_tracer(__name__)

@dataclass
class RouteCandidate:
    intent: str
    score: float       # 向量余弦相似度

@dataclass
class RouterConfig:
    """路由配置（支持 Nacos 热更新）"""
    threshold_high:        float = 0.90    # 高置信度直通阈值
    threshold_low:         float = 0.60    # 降级 LLM 兜底阈值
    shadow_sample_rate:    float = 0.05    # 高置信度区间抽样率（冷启动期提升至 0.20）
    is_cold_start:         bool  = True    # 冷启动标志（前 1000 次请求）
    cold_start_threshold_high: float = 0.75  # 冷启动期临时下调阈值
    cold_start_min_requests: int = 1000      # 冷启动退出最小请求数（全局）
    cold_start_eval_window: int = 200        # 稳定度评估窗口（最近 200 次影子验证）
    cold_start_max_mismatch_ratio: float = 0.15  # 影子验证不一致率上限
    refresh_interval_requests: int = 20      # 每 N 次请求刷新一次冷启动状态

class AdaptiveSemanticRouter:
    """
    自适应语义路由器
    冷启动优化: 阈值临时下调 + 抽样率提升 + 人工标注管道
    偏差感知: 影子验证 + Hard Negatives 检测 + 自动微调触发
    """

    def __init__(
        self,
        vector_db,
        llm_classifier,
        finetune_queue,
        router_state_store,     # Redis/PG: 记录全局请求数与影子验证稳定度
        config: RouterConfig,
    ):
        self._vdb = vector_db
        self._llm = llm_classifier
        self._finetune_q = finetune_queue
        self._state = router_state_store
        self.config = config
        self._local_request_count = 0

    async def route(self, query: str, tenant_id: str) -> str:
        with tracer.start_as_current_span("SemanticRouter.route") as span:
            self._local_request_count += 1
            global_req_count = await self._state.incr(
                key=f"router:{tenant_id}:request_count",
                delta=1,
                ttl_secs=7 * 86400,
            )

            # 冷启动状态刷新节流：避免每次请求都访问稳定度统计
            if self.config.is_cold_start and (
                self._local_request_count % self.config.refresh_interval_requests == 0
            ):
                await self._refresh_cold_start(tenant_id, int(global_req_count))

            effective_high = (
                self.config.cold_start_threshold_high
                if self.config.is_cold_start
                else self.config.threshold_high
            )

            # 向量检索（Top-5，用于透明度记录）
            candidates: List[RouteCandidate] = await self._vdb.search(
                query, top_k=5, tenant_id=tenant_id
            )
            best = candidates[0] if candidates else None
            span.set_attribute("router.best_score", best.score if best else 0)
            span.set_attribute("router.candidates_count", len(candidates))
            span.set_attribute("router.is_cold_start", self.config.is_cold_start)
            span.set_attribute("router.global_request_count", int(global_req_count))

            # 置信度低于下限: 完全降级 LLM
            if not best or best.score < self.config.threshold_low:
                span.set_attribute("router.fallback", True)
                return await self._llm_fallback(query, span)

            # 高置信度直通 or 灰度区间: 决定是否触发影子验证
            in_gray_zone = best.score < effective_high
            should_shadow = in_gray_zone or self._should_sample()

            if should_shadow:
                asyncio.create_task(
                    self._shadow_verify(query, best, tenant_id)
                )

            span.set_attribute("router.final_intent", best.intent)
            span.set_attribute("router.shadow_triggered", should_shadow)
            return best.intent

    async def _refresh_cold_start(self, tenant_id: str, global_req_count: int) -> None:
        """冷启动退出条件：全局请求数 + 影子验证稳定度（双条件同时满足）"""
        stats = await self._state.get_shadow_stats(
            tenant_id=tenant_id,
            window=self.config.cold_start_eval_window,
        )
        mismatch_ratio = float(stats.get("mismatch_ratio", 1.0))
        sample_size = int(stats.get("sample_size", 0))

        should_exit = (
            global_req_count >= self.config.cold_start_min_requests
            and sample_size >= self.config.cold_start_eval_window
            and mismatch_ratio <= self.config.cold_start_max_mismatch_ratio
        )
        if should_exit and self.config.is_cold_start:
            self.config.is_cold_start = False
            self.config.shadow_sample_rate = 0.05
            logger.info(
                "Semantic Router 冷启动期结束: "
                f"req={global_req_count}, sample={sample_size}, mismatch={mismatch_ratio:.2%}"
            )

    async def _llm_fallback(self, query: str, span) -> str:
        """LLM 兜底分类（约 800 Token，低频触发）"""
        intent = await self._llm.classify(query)
        span.set_attribute("router.llm_fallback_intent", intent)
        return intent

    async def _shadow_verify(
        self,
        query: str,
        sr_match: RouteCandidate,
        tenant_id: str,
    ) -> None:
        """
        影子验证:
        异步调用 LLM 分类器，与向量结果比对，检测漂移并推送微调样本。
        注: LLM 非绝对 Ground Truth，差异样本经人工抽检后才进入微调队列。
        """
        with tracer.start_as_current_span("SemanticRouter.shadow_verify") as span:
            try:
                llm_intent = await self._llm.classify(query)
                is_match = sr_match.intent.strip().lower() == llm_intent.strip().lower()

                span.set_attribute("shadow.sr_intent",  sr_match.intent)
                span.set_attribute("shadow.llm_intent", llm_intent)
                span.set_attribute("shadow.is_match",   is_match)
                span.set_attribute("shadow.sr_score",   sr_match.score)
                await self._state.record_shadow_result(
                    tenant_id=tenant_id,
                    is_match=is_match,
                    ttl_secs=7 * 86400,
                )

                if not is_match:
                    issue_type = (
                        "hard_negative"       if sr_match.score > 0.85
                        else "boundary_correction"
                    )
                    # 高置信度漂移: 触发告警（Domain Shift 风险信号）
                    if issue_type == "hard_negative":
                        span.add_event("HIGH_CONFIDENCE_DRIFT", {
                            "query": query[:100],
                            "sr_intent": sr_match.intent,
                            "llm_intent": llm_intent,
                        })

                    # 推送微调队列（含人工审核标志，非直接入库）
                    await self._finetune_q.put({
                        "query":      query,
                        "sr_intent":  sr_match.intent,
                        "llm_intent": llm_intent,
                        "sr_score":   sr_match.score,
                        "issue_type": issue_type,
                        "need_human_review": True,   # 人工抽检后才进微调
                        "ts": time.time(),
                    })

            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))

    def _should_sample(self) -> bool:
        """高置信度区间抽样（冷启动期 20%，稳定后 5%）"""
        rate = 0.20 if self.config.is_cold_start else self.config.shadow_sample_rate
        return random.random() < rate
```

### 6.1 边界条件与漂移处理

| 场景 | 风险 | 处理策略 |
|---|---|---|
| 向量库无结果 | 错误默认路由或直接失败 | 进入 LLM fallback，并打标 `NO_VECTOR_HIT` |
| 第一候选 / 第二候选分数接近 | 路由不稳定，跨 Skill 摆动 | 设置“最小分差阈值”，进入二次判定 |
| 向量结果与 LLM fallback 冲突 | 决策摇摆，难以解释 | 优先路由到默认安全 Skill，并推人工标注 |
| 连续高置信漂移 | 域内语义发生变化，路由持续错误 | 触发告警，暂停自动推广，进入校准窗口 |
| 冷启动达到请求数但稳定度未达标 | 过早结束冷启动，误判配置恢复 | 冷启动结束同时满足“请求数 + 稳定度”双条件 |

#### 补充决策规则

1. 当第一候选与第二候选分差低于“最小分差阈值”时，不直接直通，进入二次判定
2. 当 LLM fallback 与向量结果连续冲突超过阈值时：
   - 不自动学习
   - 不直接覆盖线上路由
   - 进入人工标注队列
3. `shadow_verify` 产生的差异样本仅作为候选，不直接写回训练集
4. 冷启动结束条件建议为：
   - 请求数达到 1000
   - 最近 200 次影子验证不一致率低于设定阈值

#### 设计结论

Semantic Router 的目标不是“永远命中最优 Skill”，而是在错误不可避免时，将错误收敛为“可观测、可恢复、可人工校正”的安全行为。

---

## 7. 沙箱执行层（按需隔离，而非默认重装）

参考 DeerFlow 的插件化架构，执行层采用 **“API 直通优先、容器隔离次之、强沙箱兜底”** 的分级执行器。
只有当工具确实需要运行不受信代码、访问临时文件系统或执行用户上传脚本时，才进入高隔离层；对于绝大多数 MCP / REST 集成，保持轻量直通即可。

### 7.1 三级级联策略

| 级别 | 执行策略 | 隔离级别 | 适用场景与优缺点 |
|---|---|---|---|
| **L1 (API_PASS)** | `DirectAPIExecutor` | 无本地执行，仅透传到受控下游 API | **适用**: 纯内部 REST/RPC/MCP 工具。<br>**优点**: <5ms 启动延迟，几乎无额外运维。<br>**缺点**: 安全边界主要依赖下游 API 的 Schema、权限和配额控制。 |
| **L2 (CONTAINER)** | `ContainerExecutor` | 容器级，Namespace/配额隔离 | **适用**: 少量受控脚本执行、文件转换、OCR 后处理。<br>**优点**: 能承载有限代码执行能力，成本明显低于 K8s 沙箱池。<br>**缺点**: 隔离强度有限，不适合多租户不受信代码。 |
| **L3 (HARDENED)** | `KubernetesPodExecutor` | 强隔离（gVisor/Kata） | **适用**: 明确允许用户生成并运行 Python/JS、或存在高风险代码执行。<br>**优点**: 强隔离、防逃逸、支持资源硬限额。<br>**缺点**: 冷延迟和运维复杂度最高，应视为高风险场景专用能力。 |

### 7.2 动态路由执行器设计

```python
from abc import ABC, abstractmethod
from typing import Any, Dict

class SandboxExecutor(ABC):
    """统一执行器基类"""
    @abstractmethod
    async def execute(self, tool_name: str, params: Dict, context: Dict) -> Any:
        pass

class DirectAPIExecutor(SandboxExecutor):
    """L1: API 直通执行（默认路径）"""
    async def execute(self, tool_name: str, params: Dict, context: Dict):
        client = get_http_client()
        return await client.post(
            f"http://internal-gateway/{tool_name}", 
            json=params, 
            headers=context.get('downstream_headers', {})
        ) 

class ContainerExecutor(SandboxExecutor):
    """L2: 受控容器执行"""
    async def execute(self, tool_name: str, params: Dict, context: Dict):
        # 挂载只读资源、限额 CPU/Mem、禁用特权模式
        pass

class K8sPodExecutor(SandboxExecutor):
    """L3: 强沙箱执行（仅高风险工具启用）"""
    async def execute(self, tool_name: str, params: Dict, context: Dict):
        # 仅对高风险代码执行工具启用；允许预热池，但不是平台默认依赖
        pass

class ExecutorFactory:
    """执行器工厂"""
    @staticmethod
    def get_executor(tool_config: dict, env_policy: str) -> SandboxExecutor:
        if tool_config.get("is_pure_api", True):
            return DirectAPIExecutor()
        if tool_config.get("requires_code_execution", False) is False:
            return ContainerExecutor()
        return K8sPodExecutor()
```

#### 执行层决策原则

1. 默认假设工具是“调用企业既有系统”，不是“运行自由代码”。
2. 隔离级别由工具声明和风险等级驱动，而不是平台一刀切上 K8s。
3. 如果某能力可通过下游 API 网关约束实现，就不在 Agent 平台重复造沙箱。
4. 预热池是 L3 的可选优化，不属于平台基础闭环的必选项。

## 8. Skill 中心（生命周期治理）

### 8.1 Skill 元数据规范

```yaml
# skill 定义示例: 合同审查 v2
id: contract-review-v2
version: 2.1.0
category: legal
status: published           # draft / testing / published / deprecated
risk_score: 0.15            # 自动红队扫描结果 (0=安全, 1=高危)

spec:
  model_provider: deepseek-v3        # 锁定底座模型（防漂移）
  prompt_version: p-772              # 锁定 System Prompt 版本
  harness_required: true             # 强制 Harness 护栏
  scratchpad_enabled: true           # 强制 Hidden CoT 审计
  token_budget_complexity: complex   # 预算分配: 50,000 tokens

runtime:
  sandbox_tier: HARDENED
  vector_collection: skills_legal    # 租户隔离向量空间
  max_qps: 20
  timeout: 60s
  max_retry: 3
  doc_parse_policy: standard         # none / standard / finance_strict
  ocr_engine_profile: paddle_hybrid  # paddle_local / paddle_hybrid / external_ocr
  callback_timeout: 600s             # 长文档异步回调等待上限
  claim_check_required: true         # 大文档必须使用 URI 引用，不直塞 Base64

distribution:
  allowed_tenants: [legal_dept, compliance_div]
  deployment_strategy: canary
  canary_weight: 10%                 # 初始灰度 10%
  auto_promote_threshold: 99.5%      # 成功率 ≥ 99.5% 自动全量

observability:
  alert_on_error_rate: 5%
  alert_on_p99_latency: 30s
  auto_circuit_break: true           # 触发告警阈值时自动熔断
```

### 8.2 Skill 上架审核流程

```
开发者提交 Skill 包（YAML + Prompt + Tools 定义）
  │
  ├─[自动扫描]
  │   ├─ Harness 兼容性: 输出格式 Schema 验证
  │   ├─ 红队测试: Prompt Injection 模拟（10 种攻击向量）
  │   ├─ 依赖检查: 工具 API 在企业合规白名单内
  │   └─ Token 消耗预估: 基于历史数据评估成本
  │
  ├─[人工审批]
  │   ├─ 业务专家: 回复质量抽检（10 个标准样例）
  │   └─ 管理层: 敏感权限二审（涉及资金/合规的 Skill）
  │
  ├─[热发布]
  │   ├─ 触发 Semantic Router 向量库热更新
  │   ├─ 按 canary_weight 灰度分流
  │   └─ 无需重启服务
  │
  └─[运行治理]
      ├─ 实时监控: Token 消耗、P99、错误率
      ├─ 自动熔断: 错误率 > 5% 或 P99 > 30s
      └─ 依赖图谱: 工具升级时反向索引影响 Skill
```

### 8.3 二级路由（防止 Skill 激增导致路由过载）

本节在 Skill 数量增长后，先用元数据过滤缩小候选范围，再在子集内做语义匹配，以降低路由开销与语义冲突。

```python
class TwoStageSkillRouter:
    """
    二级路由:
    L1: 元数据过滤 (tenant + permissions) → 候选子集
    L2: 向量相似度匹配 → 精准命中
    """

    async def route(self, query: str, env_context) -> str:
        # L1: 静态元数据过滤（零 Token 消耗）
        candidate_skill_ids = await self._metadata_filter(
            tenant_id=env_context.tenant_id,
            user_role=env_context.user_role,
            biz_scene=env_context.biz_scene,
        )

        if not candidate_skill_ids:
            raise SkillNotFoundException("无可用 Skill，请联系管理员")

        # L2: 在子集内向量检索（降低语义冲突率和计算量）
        embedding = await self._encoder.encode(query)
        results = await self._vdb.search(
            embedding,
            filter_ids=candidate_skill_ids,     # 严格限定候选范围
            tenant_id=env_context.tenant_id,
        )

        return results[0].skill_id if results else "default_skill"

    async def _metadata_filter(self, tenant_id: str, user_role: str, biz_scene: str) -> list:
        """从 Redis 缓存的 Skill 元数据中过滤（毫秒级）"""
        all_skills = await self._skill_registry.get_active_skills(tenant_id)
        return [
            s.id for s in all_skills
            if user_role in s.allowed_roles and biz_scene in s.allowed_scenes
        ]
```

### 8.4 边界条件与发布回滚

| 场景 | 风险 | 处理策略 |
|---|---|---|
| Skill 新版本上线后错误率上升 | 大面积错误路由或错误回答 | 按灰度指标自动回滚到上一个稳定版本 |
| Prompt 更新导致结果漂移 | 功能未报错但业务质量下降 | 维护标准样例回归集，按版本对比 |
| 工具 Schema 升级 | 旧 Skill 静默失效 | 通过依赖图谱触发影响分析与兼容性检查 |
| Skill 下架 | 历史线程无法重放 | 历史线程继续绑定既有版本，仅对新流量下线 |
| 灰度流量无问题但长尾异常上升 | 指标短期假健康 | 灰度观察期要求覆盖成功率、P99、人工抽检三类指标 |

#### 发布治理补充

1. Skill 运行时默认版本锁定（`version pinning`）
2. 路由层只切换“新请求”，不改写历史线程已绑定版本
3. 每个 Skill 维护：
   - 当前稳定版本指针
   - 当前灰度版本指针
   - 最近一次可回滚版本指针
4. 自动回滚阈值一旦命中，Router 与 Skill Registry 必须原子切回稳定版本

#### 设计结论

Skill 治理不仅是“上架审核”，还必须包含“灰度、回滚、重放兼容、依赖变更影响分析”四个闭环能力。

### 8.5 专项机制：多模态文档解析（OCR融合架构）

金融场景中的发票、合同、财报等属于**重负载、长耗时、大 payload** 的处理对象，传统 Agent 同步调用极易导致内存撑爆或线程断联。因此，本方案强制采用 **PaddleOCR（传统版面解析） + PaddleOCR-VL（多模态语义兜底）** 的混合栈，并确立以下四项设计规范：

#### (1) 云本兼容与动态路由热切
基于合规要求，OCR 被包装为统一入口，内部对策略实施动态热切：
- **高敏隔离策略**（涉及财务账号、PII 证件）：路由至本地集群部署的私有化 PaddleOCR（包含 PP-Structure），保证核心数据完全不离本地。
- **效率下沉策略**（通用低敏文件）：路由至性能上限更高或公有云的 OCR / VL 服务（如具备算力优势的外部大模型接口）。

#### (2) 大对象代领（Claim-Check）防内存击穿
禁止将图片 Base64 或全量识别出的几十万字文本直接塞入大模型的 Context：
- **输入阶段**：业务系统传入临时外链 `doc_uri`。
- **输出阶段**：OCR 产出的复杂 JSON（结构坐标、表格阵列）写入阿里云 OSS；Agent 仅接收带脱敏短摘要与精准取数凭证的 `result_uri`，并通过对象存储适配层完成后端切换与受控读取。

#### (3) “版面为主、大模型为辅”的混合防幻觉流水线
纯多模态大模型在密集财务表格上会出现“幻觉跨行”错误：
- **第一层确权**：依靠传统 `PP-Structure` 做绝对的版面还原与框界切分。
- **第二层升维**：当传统 OCR 遇到模糊印章、手写残片致使置信度低于阈值时，仅将该局部区域切片送给 `PaddleOCR-VL` 或大参数视觉模型进行语义补全，避免输入侧的大模型幻觉污染。

#### (4) 阻塞对抗：异步挂起与网关回调 (Suspend & Resume)
长文档解析可能耗费几分钟：
- 当识别到这是一个高耗时的 OCR Job 时，Executor 获取 `job_id` 后直接向 LangGraph 抛出挂起信号，将当前的 `AgentFastState` 保存为检查点并**释放所在的沙箱或工作线程池**。
- OCR 引擎处理完毕并 Webhook 回调边缘网关后，主动唤醒并加载该 Thread 状态图，防范全局连接池被长作业枯竭拉爆。

#### (5) OCR 运行时元数据要求
所有涉及文档解析的 Skill，运行时元数据至少需要声明以下字段：
- `doc_parse_policy`: 文档解析策略等级，用于区分通用文档与财务高敏文档。
- `ocr_engine_profile`: OCR 引擎组合策略，用于指定本地 Paddle、混合 Paddle、或外部 OCR 服务。
- `callback_timeout`: 长文档异步回调超时时间，超过阈值后进入人工处理或重试队列。
- `claim_check_required`: 是否强制使用 `doc_uri/result_uri` 的 Claim-Check 机制。

#### (6) OCR 专项评估指标
多模态文档解析不只看“能不能识别出文字”，还要看结构还原与业务字段可用性。上线前至少评估以下指标：
- 字段召回率（`field_recall`）：发票号、金额、税号、合同主体等关键字段的提取完整度。
- 表格结构还原准确率（`table_structure_f1`）：财报、对账单、清单类文档的行列对齐质量。
- 局部补全触发率（`vl_escalation_rate`）：传统 OCR 置信度不足时升级到 `PaddleOCR-VL` 的比例。
- 人工复核回退率（`human_review_fallback_rate`）：解析结果无法自动闭环、需人工接管的比例。

---

## 9. 企业安全壳与容灾

### 9.1 不可篡改审计 WAL

本节遵循“本地先落盘、网络后异步”的审计原则，确保 Kafka 或网络异常时主链路不丢日志。  
Janitor 独立 DaemonSet 部署，与主服务解耦。
审计留存以“结构化决策证据链”为主：记录决策摘要、工具调用、参数快照、结果快照、规则命中、审批记录与版本信息，支持受控回放与问题复盘，不默认暴露完整自然语言思维链。

```python
import asyncio
import json
import time
import os
from pathlib import Path

class LocalWALStore:
    """
    本地 WAL（Write-Ahead Log）存储
    使用目录 + 文件模拟 WAL（生产建议替换为 RocksDB）
    Janitor 进程独立部署，确保主进程 OOM 时不影响日志恢复
    """

    def __init__(self, wal_dir: str = "/var/agent/wal"):
        self._wal_dir = Path(wal_dir)
        self._wal_dir.mkdir(parents=True, exist_ok=True)

    async def write(self, entry_id: str, entry: dict, status: str = "PENDING") -> None:
        """先写 WAL，再异步发送 Kafka（保证不丢）"""
        wal_entry = {
            **entry,
            "_wal_id":      entry_id,
            "_wal_status":  status,
            "_wal_ts":      time.time(),
        }
        wal_path = self._wal_dir / f"{entry_id}.json"
        # 同步写入（flush + fsync 保证落盘）
        with open(wal_path, "w", encoding="utf-8") as f:
            json.dump(wal_entry, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())   # 强制 fsync，防止断电丢失

    async def mark_sent(self, entry_id: str) -> None:
        """标记已成功同步至 Kafka"""
        wal_path = self._wal_dir / f"{entry_id}.json"
        if wal_path.exists():
            wal_path.unlink()  # 删除已确认条目

    async def get_pending(self) -> list:
        """获取所有待同步条目（供 Janitor 扫描）"""
        entries = []
        for wal_file in self._wal_dir.glob("*.json"):
            try:
                with open(wal_file, "r", encoding="utf-8") as f:
                    entries.append(json.load(f))
            except Exception:
                continue
        return entries


async def secure_audit_flow(entry: dict, wal: LocalWALStore, kafka_producer) -> None:
    """
    双写审计主流程:
    1. 同步本地 WAL 落盘（优先，保障不丢）
    2. 异步发送 Kafka（解耦主链路延迟）
    """
    entry_id = entry.get("thread_id", "") + "_" + str(int(time.time() * 1000))

    # 第一步: 同步本地 WAL（必须先于任何网络 IO）
    await wal.write(entry_id, entry)

    # 第二步: 异步 Kafka 发送（不阻塞主链路）
    asyncio.create_task(_send_to_kafka(entry_id, entry, wal, kafka_producer))


async def _send_to_kafka(entry_id, entry, wal, kafka_producer) -> None:
    try:
        await kafka_producer.send("agent_audit_log", entry)
        await wal.mark_sent(entry_id)
    except Exception as e:
        logger.error(f"Kafka 发送失败，WAL 保留待 Janitor 重试: {entry_id}: {e}")


# ── Janitor 守护进程（独立 DaemonSet Pod）──
async def janitor_main(wal: LocalWALStore, kafka_producer, check_interval: int = 300) -> None:
    """
    Janitor: 每 5 分钟扫描 WAL，重试发送失败条目。
    部署: 独立 DaemonSet，绑定 PersistentVolume，与主服务 Pod 生命周期解耦。
    """
    logger.info("Janitor 守护进程启动")
    while True:
        await asyncio.sleep(check_interval)
        pending = await wal.get_pending()
        if pending:
            logger.info(f"Janitor 发现 {len(pending)} 条待重试 WAL 条目")
            for entry in pending:
                entry_id = entry["_wal_id"]
                try:
                    await kafka_producer.send("agent_audit_log", entry)
                    await wal.mark_sent(entry_id)
                    logger.info(f"Janitor 重试成功: {entry_id}")
                except Exception as e:
                    logger.error(f"Janitor 重试失败: {entry_id}: {e}")
```

### 9.2 双向脱敏网关

本节在不破坏任务可执行性的前提下，控制“模型可见数据”与“用户最终可见数据”之间的敏感信息暴露面。

```python
import json
import re
import uuid
from typing import Dict, List, Tuple

# PII 脱敏规则
PII_PATTERNS = [
    (r'\b1[3-9]\d{9}\b',                    "PHONE"),      # 手机号
    (r'\b\d{6}(19|20)\d{2}(0[1-9]|1[0-2])\d{2}\d{3}[\dXx]\b', "ID_CARD"),  # 身份证
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',   "EMAIL"),   # 邮箱
    (r'\b\d{16,19}\b',                       "BANK_CARD"), # 银行卡
]

class PIITokenizationGateway:
    """双向脱敏网关（入站 Tokenization + 出站 Detokenization）"""

    def __init__(self, redis_client, rbac_service):
        self._redis = redis_client
        self._rbac  = rbac_service

    async def tokenize(self, text: str, session_id: str) -> str:
        """
        入站脱敏（Span-based）:
        1) 全量收集命中 span
        2) 按位置拼接新字符串
        3) 严禁使用 str.replace() 逐字替换
        """
        token_map: Dict[str, dict] = {}
        spans: List[Tuple[int, int, str, str]] = []  # start, end, pii_type, original

        for pattern, pii_type in PII_PATTERNS:
            for match in re.finditer(pattern, text):
                spans.append((match.start(), match.end(), pii_type, match.group()))

        # 按起始位置升序、长度降序，优先保留更长的命中，避免子串覆盖
        spans.sort(key=lambda x: (x[0], -(x[1] - x[0])))

        merged: List[Tuple[int, int, str, str]] = []
        cursor = -1
        for start, end, pii_type, original in spans:
            if start < cursor:
                continue
            merged.append((start, end, pii_type, original))
            cursor = end

        if not merged:
            return text

        parts: List[str] = []
        cursor = 0
        for start, end, pii_type, original in merged:
            token = f"[{pii_type}_{uuid.uuid4().hex[:8].upper()}]"
            token_map[token] = {
                "value": original,
                "start": start,
                "end": end,
                "pii_type": pii_type,
            }
            parts.append(text[cursor:start])
            parts.append(token)
            cursor = end
        parts.append(text[cursor:])
        result = "".join(parts)

        if token_map:
            # 加密存储映射表（TTL 与会话同步）
            await self._redis.setex(
                f"pii_map:{session_id}",
                3600,
                json.dumps(token_map),
            )
        return result

    async def detokenize(self, text: str, session_id: str, user_id: str) -> str:
        """出站重组: 按 RBAC 权限决定展示级别"""
        raw_map = await self._redis.get(f"pii_map:{session_id}")
        if not raw_map:
            return text

        token_map = json.loads(raw_map)
        has_high_privilege = await self._rbac.has_permission(user_id, "view_pii_raw")
        result = text

        for token, payload in token_map.items():
            original = payload["value"] if isinstance(payload, dict) else payload
            if token in result:
                if has_high_privilege:
                    result = result.replace(token, original)   # 高权回填原文
                else:
                    result = result.replace(token, self._mask(original))  # 普通用户看掩码

        return result

    @staticmethod
    def _mask(value: str) -> str:
        """手机号: 138****5678，其他: 前4后4"""
        if len(value) == 11 and value.isdigit():
            return value[:3] + "****" + value[-4:]
        if len(value) > 8:
            return value[:4] + "***" + value[-4:]
        return "***"
```

### 9.3 Redis 降级保底

本节坚持“Redis 优先、PG 保底、回填可选”的降级原则，保证线程状态可恢复而不强依赖缓存完全可用。

```python
async def get_thread_state(thread_id: str, redis_client, pg_store) -> dict:
    """
    获取 Thread 状态，Redis 故障时自动降级 PG。
    """
    try:
        raw = await redis_client.get(f"thread_state:{thread_id}")
        if raw:
            return json.loads(raw)
    except RedisConnectionError:
        logger.warning(f"Redis 故障，降级查询 PG: thread_id={thread_id}")

    # 降级: PostgreSQL 兜底
    state = await pg_store.fetch_latest_state(thread_id)
    if not state:
        return {"status": "NOT_FOUND", "thread_id": thread_id}

    # 回填 Redis（可选，用于热恢复）
    try:
        await redis_client.setex(
            f"thread_state:{thread_id}",
            86400,
            json.dumps(state),
        )
    except Exception:
        pass   # 回填失败不影响业务

    return state
```

---

## 10. 可观测性工具链

### 10.1 双轨追踪架构

| 工具 | 职责 | 关键指标 |
|---|---|---|
| **Langfuse** | LLM 内部细节: Prompt/Token/Latency/评分 | Token 消耗、模型延迟、幻觉率 |
| **OpenTelemetry** | 系统级业务 Trace: 端到端链路 | P99 延迟、错误率、Harness 拦截次数 |
| **Tempo** | Trace 存储与查询 | Span 存储、异常 Trace 检索 |
| **Grafana** | 统一可视化面板 | 全部指标汇聚 |
| **OTel Collector** | 尾部采样 + 数据路由 | 正常链路 1%，异常 100% |

### 10.2 四类核心 Span

本节围绕推理、工具、校验、记忆四条主线建立最小可观测闭环，要求关键环节可追踪、可脱敏、可与业务告警关联。

```python
from opentelemetry import trace
from opentelemetry.trace import SpanKind

tracer = trace.get_tracer("agent.platform")

class AgentSpanFactory:
    """标准化 Span 工厂，确保全链路可观测"""

    @staticmethod
    def reasoning_span(span_name: str):
        """思维链 Span: 捕获 Agent 推理过程"""
        # 属性: llm.temperature, llm.top_p, prompt.version
        # 必须记录 Thought payload（即使最终丢弃）
        return tracer.start_as_current_span(
            f"reasoning.{span_name}", kind=SpanKind.INTERNAL
        )

    @staticmethod
    def tool_span(tool_name: str, tool_call_id: str):
        """工具执行 Span: 监控 Agent 与外部系统交互"""
        # 属性: tool.name, tool_call_id, execution.time.ms
        # 必须在 SDK 层自动脱敏输入/输出（API Keys、密码、PII）
        return tracer.start_as_current_span(
            f"tool.{tool_name}", kind=SpanKind.CLIENT
        )

    @staticmethod
    def critic_span(retry_count: int):
        """Critic 质量闸门 Span: 记录自我纠错过程"""
        # 属性: critic.decision(pass/veto), veto.reason.type, retry.count
        return tracer.start_as_current_span(
            "critic.validation", kind=SpanKind.INTERNAL
        )

    @staticmethod
    def memory_span(operation: str):
        """记忆操作 Span: 诊断上下文读取准确性"""
        # 属性: memory.operation(read/write), vector.similarity.score
        return tracer.start_as_current_span(
            f"memory.{operation}", kind=SpanKind.INTERNAL
        )
```

### 10.3 核心告警指标

| 指标 | 告警阈值 | 说明 |
|---|---|---|
| Semantic Router 命中率 | < 70% | 意图识别准确率与 Token 成本指示 |
| Harness 拦截突增 | > 3x 基线 | 安全攻击或规则误报信号 |
| Token 消耗趋势（租户维度） | 超预算 20% | 成本管控红线 |
| Agent 端到端 P99 延迟 | > 15s | 用户体验核心指标 |
| Scratchpad 合规覆盖率 | < 100% | 高风险 Agent 审计完整性告警 |
| Critic 重试率 | > 15% | 模型幻觉或 Prompt 质量下降信号 |
| 强沙箱容量水位 | < 80% | 仅高风险执行场景关注的资源预警 |
| Context Window 占用率 | > 85% | 防 Token 窗口溢出导致遗忘 |
| HITL 审批超时率 | > 20% | 审批流程效率问题 |
| WAL 未同步条目数 | > 100 | Kafka 网络问题或 Janitor 故障 |
| OCR 字段召回率 | < 95% | 发票/合同/财报关键字段抽取质量告警 |
| OCR 表格结构 F1 | < 90% | 表格文档还原质量告警 |
| OCR 人工复核回退率 | > 10% | OCR 自动闭环能力下降信号 |

### 10.4 Evaluation Layer（补齐 LLMOps 闭环）

可观测只能告诉我们“哪里坏了”，不能告诉我们“这次改动会不会把线上的正确率悄悄带坏”。  
因此平台需增加独立的 Evaluation Layer，将线上真实 Workflow 抽样沉淀为可回放样本，在 CI/CD 中持续验证模型、Prompt、Tool Schema、Router 配置的变更影响。

| 能力 | 输入 | 输出 | 用途 |
|---|---|---|---|
| Workflow 回放 | 线上脱敏后的真实轨迹 | 成功率、步骤偏差、耗时分布 | 回归测试与版本对比 |
| Tool Calling 评估 | 用户输入 + 工具定义 | 参数正确率、Schema 命中率 | 防止函数调用退化 |
| RAG 评估 | Query + Ground Truth Docs | 命中率、引用准确率、幻觉率 | 知识库变更验收 |
| Prompt 回归 | 标准样例集 | 版本间质量差异报告 | 防止热更新漂移 |
| OCR 文档解析评估 | 文档样本 + 标注字段/表格真值 | 字段召回率、表格 F1、人工回退率 | 验证 OCR 融合链路是否稳定 |

> **【Release Gate (发布门禁) 一票否决权声明】**
> Evaluation Layer 不能仅仅沦为“上线后的数据复盘材料”，它必须是发布准入的绝对关卡。
> 本平台将前期定义的评估指标抽取为全局强类型卡点指标常量，以确保口径唯一：`workflow_deviation_rate`（流程步骤偏离率）、`schema_error_rate`（工具调用结构抛错率）、`field_recall`（字段召回率）、`table_structure_f1`（表格还原 F1 值）。
> 
> **一票否决（红线）触发机制**：当 CI/CD 管线中的 Evaluation 回放检出 `workflow_deviation_rate > 5%`、`schema_error_rate 出现跳点劣化` 或专项校验中的 `field_recall` 与 `table_structure_f1` 低于上一版本线上防线基准时，即刻执行**核心一票否决**（Hard Release Gate）。除最高架构师应急 Hotfix 签批外，任何涉及模型版本、Prompt 模板、Skill 配置或组件升级的变更包都将被强制截停并回滚。

```python
class WorkflowEvaluator:
    """
    评估层职责:
    - 抽取线上真实 workflow
    - 在 CI/CD 中离线回放
    - 对比模型/Prompt/工具版本差异
    """

    async def replay(self, sample, runtime_bundle) -> dict:
        result = await run_agent_workflow(
            user_input=sample["input"],
            skill_id=sample["skill_id"],
            runtime_bundle=runtime_bundle,   # model version / prompt version / tool schema version
            dry_run=True,
        )
        return {
            "success": result.status == "SUCCESS",
            "tool_schema_pass": result.tool_schema_pass_rate,
            "rag_grounded": result.rag_grounded_score,
            "latency_ms": result.latency_ms,
        }
```

#### 评估准入规则

1. Prompt、模型、Router 阈值、Tool Schema 任一变更，必须触发离线回放。
2. 关键金融 Skill 至少维护一套标准样例集和一套脱敏真实流量样本集。
3. 评估结果是模型准入与灰度发布的硬门槛，而不是上线后的补充报告。

### 10.5 尾部采样配置（OTel Collector）

本节采用“异常链路全量采样、正常链路低比例采样”的策略，在控制观测成本的同时保留故障分析所需的关键信号。

```yaml
# otel-collector-config.yaml
processors:
  tail_sampling:
    decision_wait: 10s
    num_traces:    10000
    policies:
      # 异常链路 100% 采样
      - name: error-policy
        type: status_code
        status_code: { status_codes: [ERROR] }

      - name: critic-veto-policy
        type: string_attribute
        string_attribute:
          key: critic.decision
          values: [veto]

      - name: latency-policy
        type: latency
        latency: { threshold_ms: 15000 }

      - name: harness-block-policy
        type: string_attribute
        string_attribute:
          key: harness.action
          values: [BLOCK]

      # 正常链路 1% 采样
      - name: normal-sample-policy
        type: probabilistic
        probabilistic: { sampling_percentage: 1 }
```

---

## 11. 成本控制体系

### 11.1 Token 消耗三层分级

```
Tier A（零 Token）:     规则引擎、ABAC权限、格式校验、工具白名单
Tier B（低成本）:       路由兜底、短上下文派生视图、离线评估回放
Tier C（高成本）:       主力模型（DeepSeek/Doubao/Qwen）、复杂推理、报告生成
```

**降级策略**：Token 消耗达到预算 70% 进入低成本策略，优先缩小任务范围、减少并发或命中离线缓存；95% 硬熔断。

### 11.2 成本分析基准（参考）

| 任务类型 | Tier 分配 | 预算 (tokens) | 说明 |
|---|---|---|---|
| 简单问答/日程查询 | A+B | 5,000 | 本地模型处理，极低成本 |
| 发票报销审核 | A+B+C | 20,000 | OCR+规则+主力模型 |
| 合同审查 | A+B+C | 50,000 | 长文档分析，主力模型主导 |
| 季度财务审计 | A+B+C | 50,000 | 最复杂场景，含多轮重试预算 |

### 11.3 ClickHouse 冷热分离

```sql
-- 热数据表（0-90天，全量存储）
CREATE TABLE agent_audit_hot (
    thread_id    String,
    entry_type   Enum('scratchpad', 'tool_call', 'critic', 'memory'),
    content      String,
    tenant_id    String,
    ts           DateTime,
    INDEX idx_tenant (tenant_id) TYPE bloom_filter
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(ts)
ORDER BY (tenant_id, thread_id, ts)
TTL ts + INTERVAL 90 DAY TO VOLUME 'cold'; -- 90天后自动迁移冷存

-- 冷存储（OSS / 对象存储，高压缩比）
-- 通过 TTL TO VOLUME 自动归档，无需手动运维
```

---

## 12. 部署规格

### 12.1 三级部署规格

| 规格 | 适用场景 | 精简说明 | 最小团队 |
|---|---|---|---|
| **规格 A（精简版）** | 内部验证 / 部门级 POC | 去除 ClickHouse（用 PG 代替），默认 API 直通，不启用强沙箱池，单节点 Redis | 5 人 |
| **规格 B（标准版）** | 一般金融业务上线 | 完整 Harness，引入分区表与 Redis Sentinel，API 直通 + 受控容器执行 | 8-9 人 |
| **规格 C（生产完整版）** | 核心业务 / 高并发 | 本方案全量组件，按风险启用强沙箱，ClickHouse + Patroni HA + 跨 AZ 同城双活 | 12-13 人 |

### 12.2 规格 C 核心 Helm 配置

```yaml
# values-production.yaml
services:
  enterprise-gateway:   { replicas: 3,  image: "kong:3.6" }
  deerflow-backend:     { replicas: 4,  resources: { cpu: "4", memory: "8Gi" } }
  harness-monitor:      { replicas: 2 }   # Nacos 热更监听 + 防线管理
  hitl-state-machine:   { replicas: 2 }   # HITL 状态机独立服务
  janitor-daemonset:    { type: DaemonSet, resources: { cpu: "0.5", memory: "512Mi" } }
  skill-marketplace:    { replicas: 2 }
  pii-gateway:          { replicas: 3 }   # 双向脱敏网关

datastores:
  milvus:       { replicas: 3, storage: "500Gi" }
  postgresql:   { replicas: 3, storage: "100Gi", mode: patroni-ha, rpo: "< 1min", rls: true }
  redis:        { replicas: 3, mode: sentinel }
  oss:          { bucket: "agent-platform-prod", redundancy: "LRS/OSS", lifecycle: "enabled" }
  kafka:        { replicas: 3 }
  clickhouse:   { replicas: 2, storage: "1Ti" }   # 含独立加密列族

sandbox:
  runc_pool:    { min_idle: 20, max_size: 100 }
  hardened_pool_optional: { min_idle: 0, max_size: 20, runtime_class: gvisor }

storage_adapter:
  backend: oss
  policy_switch_enabled: true
  cost_aware_routing: true
  compatible_backends: [oss, s3_compatible, minio]

observability:
  langfuse:   { replicas: 2 }
  otel_collector: { replicas: 3 }
  tempo:      { replicas: 2, storage: "500Gi" }
  grafana:    { replicas: 2 }
```

## 12.3 技术栈汇总

| **层次** | 组件 | 来源 / 说明 |
| ---- | ---- | ---- |
| **编排引擎** | LangGraph 1.0 | DeerFlow，加入 DAG 环路检测防死锁 |
| **基础框架** | LangChain 0.3 | DeerFlow 抽象底层 |
| **Harness 层** | 自研 HarnessInterceptor | 自建，受 Nacos 动态热更新管理 |
| **沙箱引擎** | gVisor(runsc) + K3s | 自配，三级隔离架构 + 预热排队队列 |
| **路由模型** | BAAI/bge-small-zh-v1.5 | 自配，支持 Shadow Mode 静默调优 |
| **记忆系统** | DeerFlow Memory | 深度定制，Event-Sourced Diffs + Projection 回放 |
| **文档解析** | PaddleOCR + PaddleOCR-VL | 版面结构解析 + 局部多模态语义补全，服务于发票/合同/财报场景 |
| **API 网关** | Kong / APISIX | 自建企业安全入口 |
| **通道集成** | DeerFlow Gateway | 扩展集成飞书 / 钉钉审批卡片 |
| **数据库** | PG(Patroni) + Milvus + Redis | 自配业务、向量与状态存储 |
| **对象存储** | 阿里云 OSS + Storage Adapter | 默认承载 Claim-Check、大对象结果、冷存；适配层支持按环境/成本切换后端 |
| **容灾/审计** | RocksDB(WAL) + ClickHouse | Kafka 双写防止审计数据丢失 |
| **可观测** | Langfuse + OTel + Grafana | 追踪 LLM 推理细节与系统端到端耗时 |
| **评估系统** | Workflow Replay + Regression Suite | 支撑模型/Prompt/Tool Schema 变更准入 |
| **主力模型** | Doubao / DeepSeek V3 / Qwen | 模型降级热切机制：API 熔断时无缝切流至私有化部署 |


---

## 13. 实施 Roadmap

### 13.1 优先行动项（第一个月必须完成）

#### 13.1.1 工程可交付验收（阻塞上线）

| # | 行动项 | 负责角色 | 验收标准 |
|---|---|---|---|
| E1 | Token Budget Guard 接入所有 Agent | Harness Engineer | 单 Thread 成本可量化，超预算自动告警 |
| E2 | Planner 重试上限硬编码（≤2次）+ 错误上下文携带 | Harness Engineer | Planner 最大 LLM 调用次数 ≤ 3 |
| E3 | SR 冷启动阈值下调至 0.75 + 抽样率提升至 20% | AI 算法 | 冷启动期 LLM 调用次数 < 稳定期 2x |
| E4 | Scratchpad L1 分片存储（64KB/片）+ 滚动压缩 | Harness Engineer | 超长推理链 Redis 内存占用 < 50MB |
| E5 | 全局工具锁注册表上线（max wait 30s） | 平台架构师 | 无静默挂起，超时返回 RESOURCE_CONTENTION |

#### 13.1.2 业务价值验收（并行跟踪，不阻塞平台上线）

| # | 行动项 | 负责角色 | 验收标准 |
|---|---|---|---|
| B1 | 财务报销自动闭环率考核 | 业务/产品架构师 | 财务报销 Agent 在非受控真实发票环境中的无人工接管（全自动闭环率）达到 **85%** |
| B2 | 法务合同审查效率核算 | 业务/产品架构师 | 法务合同审查人工耗时（含 OCR 机读比对与重点风险定位）相较纯人工方式 **下降 60%** |
| B3 | 知识库客服 Agent 自主结单率 | 业务/产品架构师 | 在对客支持及机构 SOP 检索场景下，系统给出有效行动并无需转接人工核查的自动化结单率持平或超过 **90%** |
| B4 | 合规初筛（审计）虚假上报缩减率 | 财务风控委员会 | Q3/Q4 自动化财报与单据审计批次中，Agent 暴露的虚假召回（无风险却报异常）占比相比纯规则引擎模式收敛至 **5% 以内** |

> **业务价值导向说明**：Roadmap 以业务价值为最终标尺。首月工程验收用于“保证平台可安全上线”，业务指标按观察窗口并行跟踪，避免冷启动期样本偏差导致工程节奏失真。

### 13.2 完整实施时间轴（10 个月）

```
M1-M2  基座搭建
  ├─ 优先行动项 1-5 全部完成
  ├─ 企业安全网关（Kong/APISIX）上线
  ├─ DeerFlow 核心引擎部署（规格 A）
  ├─ 基础 RBAC + Semantic Router（含冷启动优化）
  ├─ 知识库 Agent（第一个生产 Skill）
  └─ WAL 双写审计基础版（本地 WAL + Kafka）

M3-M4  Harness 构建
  ├─ HarnessToolInterceptor 完整版（含 Nacos 热更新 + 灰度）
  ├─ Scratchpad 分片压缩审计 + ClickHouse 审计消费者
  ├─ 三层记忆（L1 分片 + L2 Event Diffs + L3 租户隔离）
  ├─ PaddleOCR + PaddleOCR-VL 文档解析链路 POC（Claim-Check + 局部补全）
  ├─ 受控容器执行器上线（仅保留强沙箱接口定义，不先建预热池）
  └─ HITL 三段式状态机（含资源补偿事务）

M5-M6  业务深水区
  ├─ 双向脱敏网关（PII Tokenization + RBAC 分级展示）
  ├─ WAL Janitor DaemonSet 独立部署（绑定 PV）
  ├─ MCP 智能问数（含 LegacyOracleAdapter）
  ├─ OCR 融合链路上线（PaddleOCR 主解析 + PaddleOCR-VL 局部升维）
  ├─ 财务报销 Agent
  └─ 金融审批 Agent（含 ABAC 多维权限校验）

M7-M8  平台化运营
  ├─ Skill 广场内部版（含上架审核流程 + 红队自动扫描）
  ├─ 二级路由（防 Skill 路由过载）
  ├─ Token 消耗租户维度监控 + 成本告警
  ├─ Evaluation Layer 上线（真实 Workflow 回放 + Prompt 回归）
  └─ Langfuse + OTel + Grafana 全链路可观测上线

M9-M10  生产就绪
  ├─ 生产规格扩展（ClickHouse 列族 + Patroni HA）
  ├─ 全链路压测（重点: 月末报表并发场景）
  ├─ 蓝红对抗演练（Prompt Injection + 越权测试）
  ├─ 第三方安全审计
  ├─ SR 进入稳定运行区间，切换到常态配置（全局请求数 + 稳定度双条件）
  ├─ DeerFlow 适配层（Anti-Corruption Layer）设计评审与 POC（远期，不阻塞上线）
  ├─ 强沙箱只对高风险代码执行场景灰度启用
  └─ 全面投产
```

### 13.3 团队职能配置（规格 C，13 人）

| 角色 | 人数 | 核心职责 |
|---|---|---|
| 平台架构师 | 2 | 整体架构决策、基础设施灾备联调、死锁防护 |
| **Harness Engineer** ★ | 2 | Harness 边界维护、Scratchpad 审计、Token Budget、Schema/权限护栏 |
| 业务 Agent 工程师 | 4 | 金融业务 Prompt 工程、LangGraph 工作流编排 |
| AI 算法 | 2 | SR 向量模型优化、BGE-Reranker 调优、冷启动标注管道 |
| 安全/运维 | 2 | 对抗演练、WAL 监控、Janitor 运维、K8s 安全加固 |
| 前端 | 1 | 审批卡片、SSE 实时推送、可观测面板 |

> **Harness Engineer 是最关键的角色**：把业务 Agent 当作"不受信任代码"，专职维护所有边界约束，不参与业务逻辑开发。

---

## 14. 风险应对矩阵

| 风险项 | 概率 | 影响 | 等级 | 已落地应对措施 |
|---|---|---|---|---|
| **Planner 重试成本失控** | 高 | 高 | 🔴 P0 | Token Budget Guard + 重试上限 2 次 + 有上下文纠错 |
| **Scratchpad 内存膨胀** | 高 | 高 | 🔴 P0 | 64KB 分片 + 30步滚动压缩 + ClickHouse 独立异步队列 |
| **SR 冷启动退化** | 高 | 高 | 🔴 P0 | 冷启动阈值 0.75 + 20% 抽样 + 全局请求数/稳定度双条件退出 + 人工标注管道 |
| **跨线程资源死锁** | 中 | 高 | 🔴 P0 | 全局工具锁注册表 + 30s 超时 + RESOURCE_CONTENTION 类型化错误 |
| **HITL 资源泄漏** | 中 | 中 | 🟡 P1 | 三段式状态机 + 资源快照 + 补偿事务 + 催办提醒 |
| **异步风控追溯不及时** | 中 | 高 | 🟡 P1 | 同步链路仅拦高风险写操作，旁路 DLP 秒级追溯 + 下游网关兜底 |
| **Schema 版本漂移静默失效** | 低 | 中 | 🟡 P1 | Event Schema 版本化 + Projection 迁移器 + 历史事件不可变 |
| **强沙箱建设过早拖慢交付** | 中 | 中 | 🟡 P1 | L1/L2 优先落地，L3 仅为高风险场景保留灰度启用 |
| **WAL 单点故障** | 低 | 高 | 🟡 P1 | Janitor DaemonSet 独立部署 + PV 绑定 + fsync 强制落盘 |
| **跨租户数据泄露** | 低 | 高 | 🟡 P1 | 租户过滤条件强制注入 + 二次校验 + L1-L5 五层硬隔离 |
| **DeerFlow 供应链审查** | 中 | 高 | 🟡 P1 | 版本锁定 + Harness 外挂不侵入源码 + 6-8周替代实施预案 |
| **评估缺失导致热更新回归** | 中 | 高 | 🟢 P2 | Workflow Replay + 标准样例集 + 发布前回放准入 |
| **月末并发雪崩** | 中 | 高 | 🟢 P2 | 提前压测 + Token Budget 分租户限速 + 沙箱弹性扩容 |

---

### 14.1 实施技术约束

为避免平台在落地过程中重新滑向“控制面无限堆叠”或“实现细节失控”，本方案将实施约束分为三类：生死线约束、务实实现约束、实施治理约束。前两类用于守住物理边界与合规底线，第三类用于保证系统演进过程不失真。

#### 一、生死线约束

##### 1. PII 脱敏必须采用基于 Span 的位置段替换

在金融文档、合同、财报、票据等高敏场景中，PII 脱敏不得使用基于 `str.replace()` 的逐字替换方式。平台必须基于匹配结果的 `offset/span` 进行替换与回填，以避免重复值、子串碰撞、金额误替换、编号串扰等确定性风险。

实施要求如下：

1. `tokenize()` 必须先收集全部命中片段及其位置区间，再按位置生成脱敏结果。
2. 每个匹配实例必须生成唯一 token，不因原文值相同而复用。
3. `token_map` 必须以 `token -> original_value` 为核心映射，必要时附带 `start/end offset` 供审计与精确回放。
4. `detokenize()` 只能按 token 精确回填，不得再次依赖原始正文做模糊匹配。
5. 重复手机号、重复账号、相邻匹配、嵌套子串、金额字段混排等场景必须纳入单元测试与回归测试。
6. 该能力属于平台级合规底线，不允许以“先简化实现、后续再补”的方式延期。

##### 2. Event Sourcing 必须具备快照检查点（Checkpoint）

事件流回放不得长期依赖全量事件列表。对于长线程、高频状态变更或多轮审批类任务，平台必须定期生成快照检查点，以控制恢复耗时、内存占用和数据库压力。

实施要求如下：

1. 线程状态必须按事件数阈值、时间阈值或关键阶段切换点生成快照。
2. 恢复过程优先加载最近快照，再回放其后的增量事件。
3. 单次恢复允许回放的事件数必须设置上限；超过上限时，系统应触发快照补建或告警。
4. 快照对象必须包含 `schema_version`、`event_offset`、`created_at` 等元信息。
5. 快照损坏、缺失或版本不兼容时，可退化为全量回放，但必须产生恢复告警并进入观测面。
6. 该能力属于系统物理生存线，不视为增强项，也不允许推迟到后续版本补做。

#### 二、务实实现约束

##### 3. `HarnessScratchpad` 一致性采用轻量原子方案

`HarnessScratchpad.write()` 的设计目标是避免 `step_idx`、分片内容、索引登记之间出现明显错位；但在首期实现中，不要求引入重型事务协议或两阶段提交。

实施要求如下：

1. 安全扫描通过后再生成 `step_idx`，避免明显的异常路径跳号污染。
2. 分片内容写入与索引登记应通过 Redis `Pipeline` 或 Lua 脚本打包，保证最小原子性。
3. 若写入中断导致少量孤立 key 或步号不连续，可由 TTL 与后台清理机制自然收敛，不作为首期必须彻底消灭的问题。
4. 平台只要求“不出现持续性状态错位”，不要求为极低概率异常设计重型一致性协议。
5. 若后续合规要求提升，再评估是否升级为更严格的跨存储一致性机制。
6. 命中违规时必须“先留审计证据，再实时熔断”，并禁止将违规内容写入 Redis L1。

##### 4. `GlobalToolLockRegistry` 热更新采用粗粒度切流策略

并发度配置热更新在一期实现中不要求“优雅排空”或无感平滑缩容。对于低频但高风险的限流场景，平台允许采用更直接的切流策略，以换取实现复杂度可控。

实施要求如下：

1. 并发配置变更时，允许直接创建并启用新的分布式配额窗口配置。
2. 旧配额窗口中的存量持有者允许自然执行完成，不要求回溯驱逐或平滑迁移。
3. 因配置切换造成的少量超发、超时或任务重试，可统一归类为 `RETRYABLE`。
4. 每次热更新必须记录工具名、旧并发值、新并发值、生效时间和配置版本。
5. 平台首期重点是“新配置能够尽快约束新流量”，而不是为低频运维动作投入高复杂度平滑缩容算法。
6. 分布式信号量必须具备 `lease` 续租机制；长任务在执行期间需周期性续租，避免租约过期导致并发超发。
7. 必须具备过期 holder 回收机制（请求侧惰性清理 + Janitor 主动清理至少二选一，推荐同时启用），防止配额泄漏。
8. HITL 超时状态更新必须采用 CAS（仅允许 `PENDING -> TIMEOUT_VETO`），禁止无条件覆盖。
9. 审批回调写入同样必须采用 CAS（仅允许 `PENDING -> APPROVED/REJECTED`），并对“回调晚到”做显式通知。
10. HITL 等待轮询必须配置并发上限、指数退避与随机抖动；当审批规模上升时应升级为 `LISTEN/NOTIFY` 或消息总线推送。

##### 4.1 成本与路由状态必须全局一致

Token 预算与冷启动状态均属于“跨 Pod 共享控制面状态”，不得使用仅进程内可见的计数器作为唯一依据。

实施要求如下：

1. Token 消耗必须使用 Redis `INCRBY`（或等价原子操作）作为全局累加器，本地计数仅允许作为短暂降级缓存。
2. Token 计费应支持 `operation_id` 级幂等，避免重试链路导致重复扣费。
3. Semantic Router 冷启动退出必须由全局请求计数与稳定度双条件共同判定，不得只依赖单实例请求数。
4. 冷启动状态刷新必须节流（例如每 N 次请求刷新一次），防止状态检查本身放大存储压力。

#### 三、实施治理约束

##### 5. 统一失败态必须配套异常映射表

`AgentFailureState` 的三分类 `RETRYABLE / HUMAN_REVIEW / FAILED_CLOSED` 不能只停留在抽象层，平台必须提供统一的异常映射表，避免分类逻辑散落到各节点业务代码中。

实施要求如下：

1. 平台维护一份全局异常分类注册表，作为默认判定来源。
2. `Planner / Executor / Critic / HITL / OCR / Router / Tool Adapter` 等节点抛出的异常，优先映射到统一分类表，而不是由节点自行自由判断。
3. Skill 或业务线允许在平台默认映射之上做有限扩展，但不得覆盖平台级强制分类规则。
4. 以下场景至少应有明确归类：
   - 下游接口超时、网络抖动、资源竞争、信号量抢占失败：`RETRYABLE`
   - OCR 返回损坏结构、HITL 审批超时、模型输出不可信、人工前置审核命中：`HUMAN_REVIEW`
   - Token 预算硬熔断、严重越权、关键依赖彻底不可用、合规禁区触发：`FAILED_CLOSED`
5. 映射表必须具备版本号和审计可追溯性，便于复盘“某次异常为何被归到该类别”。

##### 6. Evaluation 必须定义首版基线建立规则

`Release Gate` 不能只建立在“与上一版本对比”的假设上。首次上线、冷启动阶段或新 Skill 初次发布时，平台必须定义 bootstrap baseline 的建立方法，否则发布门禁在首版场景中将失去约束力。

实施要求如下：

1. 首版基线由两类样本共同构成：
   - 标准样例集：由架构师、业务专家、测试共同维护的人工标注样本
   - 脱敏真实流量样本：来自试运行阶段的真实任务轨迹
2. 首次上线前，应先经历有限灰度或试运行窗口，用于采集真实分布数据。
3. 在没有历史版本可比时，发布门禁应与“标准样例最低通过线”比较，而不是与“上一版基线”比较。
4. 首版上线后，试运行窗口产生的数据可沉淀为后续版本的线上基线。
5. 对高风险 Skill，不允许以“暂无基线”为由绕过评估门禁，除非走明确的应急特批流程。

##### 7. 业务验收指标必须定义统计口径与观察窗口

业务结果型指标可以用于管理层验收，但不能直接作为无边界的工程承诺。所有自动闭环率、结单率、耗时下降率、误报收敛率等指标，必须同时绑定统计边界。

实施要求如下：

1. 每个业务指标必须明确：
   - 统计样本范围
   - 时间窗口
   - 排除项
   - 人工介入判定标准
   - 成功/失败的业务定义
2. `财务报销自动闭环率` 需说明发票质量、异常票据比例、人工复核触发条件。
3. `知识库客服自主结单率` 需说明是否处于冷启动期、是否已有真实流量、何种情况算“无需转人工”。
4. `合同审查人工耗时下降率` 需说明比较基线是纯人工、规则辅助还是旧系统流程。
5. `审计虚假上报缩减率` 需说明“异常命中”与“误报”的标注口径。
6. 工程里程碑与业务结果里程碑应区分表达：前者用于平台建设验收，后者用于业务价值验收，二者不应在冷启动阶段混为同一张首月硬指标表。

---

## 附录：核心设计决策汇总

| 决策 | 选择 | 拒绝 | 理由 |
|---|---|---|---|
| Agent 边界控制 | 传统确定性代码（Harness）| LLM 自我约束 | LLM 可被诱导，代码不可 |
| 大状态存储 | OSS（经 Storage Adapter 接入）+ Redis URI 指针 | 全量写入 Redis | 防 Redis OOM + 防并发写冲突，并支持按环境/成本切换对象存储后端 |
| 记忆持久化 | Event-Sourced Diffs + Projection 回放 | 小模型脱水总结 | 避免金融语义静默损坏，恢复路径更确定 |
| 审计可靠性 | WAL 先写本地 + Kafka 异步 | 直接写 Kafka | 网络故障不丢日志 |
| 路由策略 | 向量检索为主 + LLM 影子验证 | 纯 LLM 路由 | P99 延迟可控 + 成本可控 |
| 沙箱策略 | API 直通优先，容器隔离次之，强沙箱兜底 | 一刀切 gVisor | 先保交付速度，再为高风险代码执行补强隔离 |
| HITL 超时 | 有感知否决 + 补偿事务 | 静默丢弃 | 资源泄漏 + 用户体验双重问题 |
| 资金操作 | **永远不走 Agent 链路** | Agent 自主执行 | 金融合规红线，任何优化不得触碰 |

---
