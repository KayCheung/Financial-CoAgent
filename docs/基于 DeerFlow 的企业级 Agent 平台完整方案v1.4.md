# 企业级 Agent 平台完整技术方案

> **版本**：v1.4
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
   - 4.2 L2 情节记忆脱注水（Schema 版本化）
   - 4.3 L3 语义记忆（租户隔离检索）
5. [HITL 三段式审批状态机](#5-hitl-三段式审批状态机)
6. [Semantic Router（冷启动优化）](#6-semantic-router冷启动优化)
7. [沙箱执行层（分级隔离）](#7-沙箱执行层分级隔离)
8. [Skill 中心（生命周期治理）](#8-skill-中心生命周期治理)
9. [企业安全壳与容灾](#9-企业安全壳与容灾)
10. [可观测性工具链](#10-可观测性工具链)
11. [成本控制体系](#11-成本控制体系)
12. [部署规格与国产化路径](#12-部署规格与国产化路径)
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
  │           重结果 (MB级) → MinIO (Claim-Check)
  │           状态指针 (URI) → Redis CAS 更新
  │           全局工具锁: oracle_legacy_conn 申请槽位 (max 30s)
  │
  ├─[Critic]  发现 3 张发票金额超授权阈值
  │           CriticVetoResult { rule:"FINANCE_002", severity:"high" }
  │           executor_retry_count = 1, 携带错误上下文重试
  │
  ├─[HITL]   快照已消耗资源 (Pod IDs + MinIO keys)
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
    TIER_B = "lightweight_llm"  # 低成本: 轻量模型脱水、意图路由边界 case
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
    DEGRADATION_THRESHOLD = 0.70   # 70% 消耗触发降级：主力模型 → 轻量模型
    HARD_LIMIT_THRESHOLD  = 0.95   # 95% 消耗触发硬熔断

    def __init__(self, budget: TokenBudget, metrics_reporter, audit_logger):
        self._budget = budget
        self._metrics = metrics_reporter
        self._audit = audit_logger
        self._lock = asyncio.Lock()

    async def consume(self, tokens: int, tier: TokenTier, operation: str) -> None:
        """
        消耗 Token 并检查阈值。
        Tier A（规则引擎）直接跳过，零消耗。
        """
        if tier == TokenTier.TIER_A:
            return  # 规则引擎零消耗，直接放行

        async with self._lock:
            self._budget.consumed += tokens
            ratio = self._budget.usage_ratio

            # 异步上报指标（不阻塞主链路）
            asyncio.create_task(self._metrics.record(
                thread_id=self._budget.thread_id,
                tenant_id=self._budget.tenant_id,
                consumed=tokens,
                total_consumed=self._budget.consumed,
                operation=operation,
                tier=tier.value,
            ))

            # 70% 触发降级告警
            if ratio >= self.DEGRADATION_THRESHOLD and not self._budget.degraded:
                self._budget.degraded = True
                self._budget.degraded_at = self._budget.consumed
                asyncio.create_task(self._audit.warn(
                    f"[Budget] Thread {self._budget.thread_id} 已消耗 {ratio:.0%}，"
                    f"触发降级: 主力模型 → 轻量模型 (Qwen2.5-7B)"
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
            return TokenTier.TIER_B  # 降级到轻量模型
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

### 2.2 工具拦截器（Nacos 热更新 + 灰度分发）

```python
import hashlib
import json
import re
import jsonschema
import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum

class HarnessRuleLevel(Enum):
    BLOCK = "block"   # 高危: 立即阻断，记录安全事件
    WARN  = "warn"    # 中危: 放行但打标告警，触发人工复核

@dataclass(frozen=True)
class SecurityRuleSnapshot:
    """不可变规则快照（Immutable），原子替换保证一致性"""
    version: str
    schemas: Dict[str, dict]          # 工具名 → OpenAPI Schema
    string_rules: List[dict]          # 叶节点正则规则集
    whitelist_patterns: List[str]     # 金融领域合法模式白名单（防误报）
    gray_ratio: int = 0               # 灰度比例 (0-100)

class HarnessRuleManager:
    """
    原子规则调度器
    解决: 配置漂移、半更新灾难、灰度窗口期规则空档
    """
    def __init__(self):
        # 初始化空规则快照（不阻断任何流量，等待 Nacos 推送）
        self._stable: SecurityRuleSnapshot = SecurityRuleSnapshot(
            version="v0.0-init", schemas={}, string_rules=[], whitelist_patterns=[]
        )
        self._gray: Optional[SecurityRuleSnapshot] = None

    def on_nacos_update(self, raw_config: dict) -> None:
        """
        Nacos/Apollo 热发回调。
        关键: 后台构建新快照，原子指针替换，零锁零停机。
        """
        new_snapshot = SecurityRuleSnapshot(
            version=raw_config["version"],
            schemas=raw_config.get("schemas", {}),
            string_rules=raw_config.get("rules", []),
            whitelist_patterns=raw_config.get("whitelist_patterns", []),
            gray_ratio=raw_config.get("gray_ratio", 0) if raw_config.get("is_gray") else 0,
        )
        if raw_config.get("is_gray"):
            self._gray = new_snapshot   # 原子替换灰度快照
        else:
            self._stable = new_snapshot # 原子替换稳定快照
            self._gray = None           # 全量发布后清理灰度

    def get_snapshot(self, tenant_id: str) -> SecurityRuleSnapshot:
        """基于租户一致性 Hash 路由灰度流量"""
        if not self._gray:
            return self._stable
        tenant_hash = int(hashlib.md5(tenant_id.encode()).hexdigest(), 16)
        if (tenant_hash % 100) < self._gray.gray_ratio:
            return self._gray
        return self._stable

# 全局单例
rule_manager = HarnessRuleManager()

class HarnessToolInterceptor:
    """
    工具调用五道闸门拦截器
    1. ABAC 白名单校验
    2. 身份强制覆写
    3. AST 结构校验
    4. 叶节点嗅探（含误报白名单）
    5. 标准化 Headers 注入
    """

    @staticmethod
    async def intercept(
        tool_name: str,
        raw_params: dict,
        env_context,        # 包含: tenant_id, user_id, user_role, biz_scene, agent_tool_whitelist
        token_budget_guard: TokenBudgetGuard,
        otel_tracer,
        audit_logger,
    ) -> tuple[dict, dict]:

        # ── 闸门 1: ABAC 工具白名单（权限来自 RBAC 配置，非 Agent 自身声明）──
        if tool_name not in env_context.agent_tool_whitelist:
            raise HarnessPermissionException(
                f"租户 [{env_context.tenant_id}] 无权调用工具 [{tool_name}]"
            )

        # ── 闸门 2: 获取当前原子规则快照（绑定版本，便于溯源）──
        rules = rule_manager.get_snapshot(env_context.tenant_id)

        # ── 闸门 3: 强制身份覆写（剥夺模型提权能力）──
        safe_params = {
            **raw_params,
            "tenant_id":   env_context.tenant_id,   # 强制覆写，不信任模型传参
            "operator_id": env_context.user_id,      # 强制覆写
        }

        # ── 闸门 4: AST 级结构化参数校验（拦截幻觉与越界）──
        tool_schema = rules.schemas.get(tool_name)
        if tool_schema:
            try:
                jsonschema.validate(instance=safe_params, schema=tool_schema)
            except jsonschema.ValidationError as e:
                raise HarnessSecurityException(
                    f"[{rules.version}] 参数结构异常/越界: {e.message}"
                )

        # ── 闸门 5: 叶节点高危嗅探（含误报白名单，解决金融数据误报痛点）──
        violations = []

        def _scan_leaves(node, path="root"):
            """仅扫描 String 叶节点，避免结构符 {} : 引发海量误报"""
            if isinstance(node, dict):
                for k, v in node.items():
                    _scan_leaves(v, f"{path}.{k}")
            elif isinstance(node, list):
                for i, item in enumerate(node):
                    _scan_leaves(item, f"{path}[{i}]")
            elif isinstance(node, str):
                # 先过白名单（合同条款、Base64、金融符号等合法模式）
                for white_pattern in rules.whitelist_patterns:
                    if re.fullmatch(white_pattern, node):
                        return  # 命中白名单，跳过扫描

                # 再扫黑规则
                for rule in rules.string_rules:
                    if re.search(rule["pattern"], node, re.IGNORECASE):
                        violations.append({
                            "path": path,
                            "level": rule["level"],
                            "rule_id": rule.get("id", "UNKNOWN"),
                            "version": rules.version,
                        })

        _scan_leaves(safe_params)

        # 处理违规
        block_violations = [v for v in violations if v["level"] == HarnessRuleLevel.BLOCK.value]
        warn_violations  = [v for v in violations if v["level"] == HarnessRuleLevel.WARN.value]

        if warn_violations:
            # WARN 级: 放行但异步打标，触发人工复核队列
            asyncio.create_task(audit_logger.warn(
                f"[Rules {rules.version}] 检测可疑参数需复核: {warn_violations}"
            ))

        if block_violations:
            # BLOCK 级: 立即阻断
            raise HarnessSecurityException(
                f"拦截高危注入，规则版本 {rules.version}，"
                f"命中: {[v['rule_id'] for v in block_violations]}"
            )

        # ── 构建标准化下游 Headers ──
        trace_id = str(otel_tracer.get_current_span().get_span_context().trace_id)
        harness_headers = {
            "X-Tenant-ID":            env_context.tenant_id,
            "X-Operator-ID":          env_context.user_id,
            "X-Trace-ID":             trace_id,
            "X-Harness-Rules-Version": rules.version,
            "X-Harness-Verified":     "true",
            "X-Budget-Remaining":     str(token_budget_guard._budget.remaining),
        }

        return safe_params, harness_headers
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
        self._step_count += 1
        step_idx = self._step_count
        shard_key = f"scratchpad:{self.thread_id}:step:{step_idx}"

        # ── 1. 安全扫描（同步，必须先于写入）──
        security_report = self._rule_engine.scan(content)

        # ── 2. 状态切换：命中高风险，进入全量审计模式 ──
        if security_report.is_high_risk:
            self._force_full_audit = True

        # ── 3. 构建分片 ──
        shard = ScratchpadShard(
            shard_id=shard_key,
            step=step,
            content=content,
            fingerprint=self._extract_fingerprint(content),
            timestamp=time.time(),
            is_high_risk=security_report.is_high_risk,
            is_full_audit=self._force_full_audit,
        )

        # ── 4. 写入 Redis L1（分片存储，TTL = 会话生命周期）──
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

        # ── 5. 滚动压缩：超过阈值，压缩旧分片 ──
        if step_idx > ROLLING_COMPRESS_AT:
            await self._rolling_compress(step_idx)

        # ── 6. 合规轨落库（独立异步队列，不阻塞推理）──
        should_audit = (
            self._force_full_audit
            or self._is_decision_fingerprint(content)
            or security_report.has_violations
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

        # ── 7. 越权实时熔断（有违规立即抛出）──
        if security_report.has_violations:
            raise HarnessSecurityException(
                f"Agent 推理越界熔断: {security_report.violations}"
            )

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
                # 写入失败: 回退到本地 WAL，绝不丢失
                for entry in buffer:
                    await local_wal.put(entry)
                buffer.clear()
```

### 2.4 全局工具锁注册表

```python
import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

@dataclass
class ToolLockEntry:
    """工具锁槽位"""
    tool_name: str
    max_concurrency: int    # 该工具允许的最大并发持有数
    current_holders: int = 0
    waiters: int = 0
    lock: asyncio.Semaphore = field(init=False)

    def __post_init__(self):
        self.lock = asyncio.Semaphore(self.max_concurrency)

class GlobalToolLockRegistry:
    """
    全局工具锁注册表（Redis 辅助 + 本地 Semaphore 双保险）
    解决: 多租户并发下的跨线程资源死锁
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

    def _init_registry(self):
        for tool_name, max_conc in self.DEFAULT_CONCURRENCY.items():
            self._registry[tool_name] = ToolLockEntry(
                tool_name=tool_name,
                max_concurrency=max_conc,
            )

    def _get_entry(self, tool_name: str) -> ToolLockEntry:
        """获取工具锁条目，未注册的工具使用默认配置"""
        return self._registry.get(tool_name, self._registry["*"])

    async def acquire(
        self,
        tool_name: str,
        thread_id: str,
        timeout: float = 30.0,
    ) -> "ToolLockContext":
        """
        申请工具执行槽位。
        - 等待超时: 30s，超时后抛出 RESOURCE_CONTENTION 错误（进入 Critic 重试）
        - 不静默挂起，保证 SLA 可测量
        """
        entry = self._get_entry(tool_name)
        entry.waiters += 1

        # 上报等待状态
        asyncio.create_task(self._metrics.record(
            "tool_lock_wait",
            tool=tool_name,
            thread_id=thread_id,
            waiters=entry.waiters,
        ))

        try:
            acquired = await asyncio.wait_for(entry.lock.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            entry.waiters -= 1
            raise ResourceContentionException(
                f"工具 [{tool_name}] 等待超时 ({timeout}s)，"
                f"当前排队: {entry.waiters}，并发上限: {entry.max_concurrency}。"
                f"错误类型: RESOURCE_CONTENTION，可触发 Critic 重试。"
            )

        entry.waiters -= 1
        entry.current_holders += 1

        asyncio.create_task(self._metrics.record(
            "tool_lock_acquired",
            tool=tool_name,
            thread_id=thread_id,
            current_holders=entry.current_holders,
        ))

        return ToolLockContext(entry=entry, tool_name=tool_name, registry=self)

    async def release(self, tool_name: str) -> None:
        entry = self._get_entry(tool_name)
        entry.current_holders = max(0, entry.current_holders - 1)
        entry.lock.release()

    def update_concurrency(self, tool_name: str, new_max: int) -> None:
        """Nacos 热更新并发配置（不重建 Semaphore，调整计数器）"""
        if tool_name in self._registry:
            self._registry[tool_name].max_concurrency = new_max


class ToolLockContext:
    """工具锁上下文管理器，支持 async with"""

    def __init__(self, entry: ToolLockEntry, tool_name: str, registry: GlobalToolLockRegistry):
        self._entry = entry
        self._tool_name = tool_name
        self._registry = registry

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._registry.release(self._tool_name)


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

```python
import time
from typing import Dict, List, TypedDict, Annotated, Optional

class AgentFastState(TypedDict):
    """
    极简 Fast State（仅存流转控制字段）
    大对象不进 State，走 MinIO Claim-Check 模式
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

    # 大对象指针（MinIO URI 字典）
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

### 4.2 L2 情节记忆（Schema 版本化脱注水）

```python
import jsonschema
import asyncio
import json
from typing import Optional

# Schema V2 定义（强结构化，替代自由文本总结）
DEHYDRATED_STATE_SCHEMA_V2 = {
    "$schema": "http://json-schema.org/draft-07/schema",
    "version": "2",
    "type": "object",
    "required": ["version", "intent", "stage", "pending_actions", "key_entities"],
    "properties": {
        "version":          {"type": "string"},
        "intent":           {"type": "string", "maxLength": 200},
        "stage":            {"enum": ["initiated", "planning", "executing", "reviewing",
                                      "awaiting_approval", "completed", "failed"]},
        "pending_actions":  {"type": "array", "items": {"type": "string"}, "maxItems": 20},
        "key_entities":     {"type": "object"},  # 关键实体 KV
        "error_context":    {"type": "string"},  # 供重试使用的错误上下文
        "token_consumed":   {"type": "integer"},
    },
    "additionalProperties": False,
}


def v1_to_v2_migration(v1_state: dict) -> dict:
    """
    向下兼容迁移: Schema V1 → V2
    字段映射 + 默认值填充，不丢弃任何已有信息
    """
    return {
        "version":          "2",
        "intent":           v1_state.get("user_intent", v1_state.get("intent", "")),
        "stage":            v1_state.get("stage", "initiated"),
        "pending_actions":  v1_state.get("pending_actions", []),
        "key_entities":     v1_state.get("entities", {}),
        "error_context":    v1_state.get("last_error", ""),
        "token_consumed":   v1_state.get("token_consumed", 0),
    }


async def memory_dehydrate(
    thread_id: str,
    thread_data: dict,
    lightweight_llm,
    redis_client,
    pg_store,
    alert_service,
) -> None:
    """
    脱水: 将冗长会话状态压缩为强结构 JSON 存入 L2
    - 使用本地轻量模型 (Qwen2.5-7B)，零主力模型 Token 消耗
    - 三次重试 + Schema 校验
    - 失败降级保底: 原文存 PG，绝不丢失上下文
    """
    DEHYDRATE_PROMPT = f"""
    将以下会话状态压缩为 JSON，严格遵循 Schema V2 格式，不输出任何额外文字:
    {json.dumps(thread_data, ensure_ascii=False)[:3000]}
    """

    for attempt in range(3):
        try:
            raw_json = await lightweight_llm.invoke(
                DEHYDRATE_PROMPT,
                response_format="json_object",
                max_tokens=500,
            )
            parsed = json.loads(raw_json)
            parsed["version"] = "2"  # 强制注入版本号

            # Schema 校验
            jsonschema.validate(instance=parsed, schema=DEHYDRATED_STATE_SCHEMA_V2)

            await redis_client.set(
                f"thread_state:{thread_id}",
                json.dumps(parsed, ensure_ascii=False),
                ex=86400,
            )
            logger.info(f"Thread {thread_id} 脱水成功 (attempt {attempt+1})")
            return

        except (json.JSONDecodeError, jsonschema.ValidationError) as e:
            logger.warning(f"Thread {thread_id} 脱水失败 attempt {attempt+1}: {e}")
            continue
        except Exception as e:
            logger.error(f"Thread {thread_id} 脱水异常 attempt {attempt+1}: {e}")
            continue

    # 三次失败: 降级保底，绝不丢失上下文
    logger.error(f"Thread {thread_id} 脱水连续失败，执行保底降级")
    await pg_store.save_raw_backup(thread_id, thread_data)
    await redis_client.set(
        f"thread_state:{thread_id}",
        json.dumps({"status": "DEHYDRATE_FAILED", "requires_human": True}),
        ex=86400,
    )
    await alert_service.trigger("脱水机制熔断", thread_id=thread_id)


async def memory_hydrate(
    thread_id: str,
    redis_client,
    pg_store,
) -> str:
    """
    注水: 从 L2 恢复上下文，支持 Schema 版本向下兼容迁移
    """
    raw = await redis_client.get(f"thread_state:{thread_id}")
    if not raw:
        # Redis 未命中，降级查询 PG
        logger.warning(f"Thread {thread_id} Redis 未命中，降级查询 PG")
        raw_backup = await pg_store.fetch_latest_state(thread_id)
        if not raw_backup:
            return "[上下文恢复失败: 未找到历史状态]"
        return f"[PG降级恢复] {raw_backup}"

    state = json.loads(raw)

    # 版本检测与迁移
    version = state.get("version", "1")
    if version == "1":
        state = v1_to_v2_migration(state)
        logger.info(f"Thread {thread_id} Schema V1→V2 迁移完成")

    if state.get("status") == "DEHYDRATE_FAILED":
        return "[上下文异常: 脱水失败，已通知人工介入]"

    return (
        f"[上下文恢复 v{version}] "
        f"意图: {state['intent']} | "
        f"阶段: {state['stage']} | "
        f"待完成: {state['pending_actions']} | "
        f"已消耗 Token: {state.get('token_consumed', 0)}"
    )
```

### 4.3 L3 语义记忆（Milvus 租户隔离检索）

```python
from pymilvus import Collection, connections, utility

class TenantAwareVectorStore:
    """
    租户感知向量存储
    核心: 每个 Skill 绑定独立 Collection，检索时强制注入 tenant_filter
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

---

## 5. HITL 三段式审批状态机

```python
import asyncio
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
        self._pending: dict[str, asyncio.Event] = {}  # approval_id → 等待 Event

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

        # 注册等待 Event
        self._pending[record.approval_id] = asyncio.Event()
        return record.approval_id

    async def wait_for_decision(self, approval_id: str, record: ApprovalRecord) -> bool:
        """
        等待审批决策，含提前催办 + 超时有感知否决。
        """
        event = self._pending.get(approval_id)
        if not event:
            raise HITLException(f"审批 {approval_id} 未找到等待 Event")

        timeout = record.timeout_seconds
        remind_at = timeout * 0.75   # 75% 时发送催办（例: 24h 审批在 18h 时催办）

        async def _remind_task():
            await asyncio.sleep(remind_at)
            if not event.is_set():
                await self._im.send_reminder(
                    to=record.approver_id,
                    approval_id=approval_id,
                    message=(
                        f"⚠️ 审批提醒: 任务「{record.task_summary[:50]}」"
                        f"将在 {(timeout - remind_at) // 3600:.1f}h 后超时自动否决，请及时处理。"
                    ),
                )

        remind_task = asyncio.create_task(_remind_task())

        try:
            await asyncio.wait_for(event.wait(), timeout=float(timeout))
            remind_task.cancel()

            # 读取决策结果
            updated = await self._pg.get_approval(approval_id)
            return updated.status == ApprovalStatus.APPROVED

        except asyncio.TimeoutError:
            remind_task.cancel()
            logger.warning(f"审批 {approval_id} 超时，执行有感知否决")

            # 更新状态
            await self._pg.update_approval_status(approval_id, ApprovalStatus.TIMEOUT_VETO)

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
        释放 HITL 前已预占的沙箱 Pod、MinIO 对象等资源，防止泄漏。
        """
        await self._pg.update_approval_status(approval_id, ApprovalStatus.COMPENSATING)
        try:
            snapshot = record.resource_snapshot
            if "sandbox_pod_ids" in snapshot:
                for pod_id in snapshot["sandbox_pod_ids"]:
                    await self._compensator.release_sandbox(pod_id)
            if "minio_object_keys" in snapshot:
                for key in snapshot["minio_object_keys"]:
                    await self._compensator.release_minio_object(key)

            await self._pg.update_approval_status(approval_id, ApprovalStatus.COMPENSATION_DONE)
            logger.info(f"审批 {approval_id} 资源补偿完成: {snapshot}")
        except Exception as e:
            logger.error(f"审批 {approval_id} 资源补偿失败: {e}，已写入告警")
            await self._audit.error(f"COMPENSATION_FAILED: {approval_id}: {e}")

    async def on_decision(self, approval_id: str, approved: bool, note: str = "") -> None:
        """审批人决策回调（由飞书 Webhook 触发）"""
        status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        await self._pg.update_approval_status(
            approval_id, status,
            decided_at=time.time(), decision_note=note,
        )
        event = self._pending.get(approval_id)
        if event:
            event.set()   # 唤醒等待协程


# ── HITL 节点（注入 LangGraph）──
async def human_approval_node(state: AgentFastState) -> dict:
    """HITL LangGraph 节点"""
    # 在进入 HITL 前，快照当前已占用的资源
    resource_snapshot = {
        "sandbox_pod_ids":  state.get("active_sandbox_pods", []),
        "minio_object_keys": list(state.get("payload_refs", {}).values()),
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
        config: RouterConfig,
    ):
        self._vdb = vector_db
        self._llm = llm_classifier
        self._finetune_q = finetune_queue
        self.config = config
        self._request_count = 0

    async def route(self, query: str, tenant_id: str) -> str:
        with tracer.start_as_current_span("SemanticRouter.route") as span:
            self._request_count += 1

            # 冷启动期: 前 1000 次请求逐步过渡
            if self._request_count == 1000:
                self.config.is_cold_start = False
                self.config.shadow_sample_rate = 0.05  # 恢复正常抽样率
                logger.info("Semantic Router 冷启动期结束，切换正常配置")

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

---

## 7. 沙箱执行层（分级隔离）

### 7.1 三级沙箱策略

| 等级 | 运行时 | 适用场景 | CPU Overhead | 启动时间 |
|---|---|---|---|---|
| Tier 1 | gVisor (runsc) | 代码执行、数据分析、OCR | ~20% | ~800ms |
| Tier 2 | runc + Namespace | 知识检索、API 调用 | ~3% | ~200ms |
| Tier 3 | Process | 文本生成、格式转换 | ~0.5% | <50ms |

### 7.2 预热池击穿保护

```python
import asyncio
from enum import Enum

MAX_QUEUE_DEPTH   = 200    # 超出返回 503
WARM_POOL_MIN     = 10     # 最小预热数
WARM_POOL_MAX     = 50     # 最大池大小

class SandboxTier(Enum):
    TIER_1_GVISOR  = "gvisor"
    TIER_2_RUNC    = "runc"
    TIER_3_PROCESS = "process"

SKILL_SANDBOX_MAP = {
    "contract-review":  SandboxTier.TIER_1_GVISOR,
    "invoice-ocr":      SandboxTier.TIER_1_GVISOR,
    "knowledge-search": SandboxTier.TIER_2_RUNC,
    "data-query":       SandboxTier.TIER_2_RUNC,
    "text-generate":    SandboxTier.TIER_3_PROCESS,
}

class SandboxPoolManager:
    """
    沙箱预热池管理器
    击穿保护: Redis 令牌桶 + SSE 实时透传排队状态
    """

    def __init__(self, redis_client, k8s_client, sse_broadcaster):
        self._redis = redis_client
        self._k8s = k8s_client
        self._sse = sse_broadcaster

    async def acquire(
        self,
        skill_id: str,
        tenant_id: str,
        timeout: float = 30.0,
    ) -> str:
        """
        申请沙箱 Pod。
        队列满时推送 SSE 告知用户，而非静默超时。
        """
        tier = SKILL_SANDBOX_MAP.get(skill_id, SandboxTier.TIER_2_RUNC)
        queue_key = f"sandbox:queue:{tenant_id}:{tier.value}"

        # 检查队列深度
        queue_depth = await self._redis.llen(queue_key)
        if queue_depth >= MAX_QUEUE_DEPTH:
            raise SandboxCapacityException(
                f"沙箱调度队列已满 ({queue_depth}/{MAX_QUEUE_DEPTH})，请稍后重试。"
            )

        # 推送排队状态（用户有感知）
        await self._sse.push(tenant_id, {
            "status": "SANDBOX_QUEUING",
            "message": f"正在为您调度「{tier.value}」安全执行环境，排队中...",
            "queue_position": queue_depth + 1,
            "estimated_wait_seconds": queue_depth * 2,
        })

        # 从预热池申请 Pod
        try:
            pod_id = await asyncio.wait_for(
                self._acquire_from_pool(tier, tenant_id),
                timeout=timeout,
            )
            await self._sse.push(tenant_id, {
                "status": "SANDBOX_READY",
                "message": "执行环境就绪",
                "pod_id": pod_id,
            })
            return pod_id
        except asyncio.TimeoutError:
            raise SandboxCapacityException(
                f"沙箱申请超时 ({timeout}s)，系统负载较高，请稍后重试。"
            )

    async def _acquire_from_pool(self, tier: SandboxTier, tenant_id: str) -> str:
        """从预热池取 Pod，不足时动态扩容"""
        pool_key = f"sandbox:pool:{tier.value}"

        # 尝试从预热池取
        pod_id = await self._redis.rpop(pool_key)
        if pod_id:
            # 异步补充预热池（保持 WARM_POOL_MIN 个就绪）
            pool_size = await self._redis.llen(pool_key)
            if pool_size < WARM_POOL_MIN:
                asyncio.create_task(self._replenish_pool(tier))
            return pod_id.decode()

        # 预热池耗尽: 动态创建新 Pod
        return await self._k8s.create_sandbox_pod(tier=tier.value, tenant_id=tenant_id)

    async def release(self, pod_id: str, tier: SandboxTier) -> None:
        """释放沙箱（销毁后补充预热池，而非复用污染环境）"""
        await self._k8s.destroy_sandbox_pod(pod_id)   # 销毁脏 Pod
        await self._replenish_pool(tier)               # 补充干净 Pod

    async def _replenish_pool(self, tier: SandboxTier) -> None:
        """后台异步补充预热池"""
        pool_key = f"sandbox:pool:{tier.value}"
        current_size = await self._redis.llen(pool_key)
        to_create = max(0, WARM_POOL_MIN - current_size)
        for _ in range(to_create):
            pod_id = await self._k8s.create_sandbox_pod(tier=tier.value, tenant_id="__warm__")
            await self._redis.lpush(pool_key, pod_id)
```

---

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
  sandbox_tier: tier_1_gvisor
  vector_collection: skills_legal    # 租户隔离向量空间
  max_qps: 20
  timeout: 60s
  max_retry: 3

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
  │   ├─ 业务专家: 回复质量抽检（10 个 Golden Cases）
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

---

## 9. 企业安全壳与容灾

### 9.1 不可篡改审计 WAL

**Janitor 独立 DaemonSet 部署，与主服务解耦。**

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
        # 同步写入（O_SYNC 保证落盘）
        with open(wal_path, "w", encoding="utf-8") as f:
            json.dump(wal_entry, f, ensure_ascii=False)
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

```python
import re
import uuid

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
        """入站脱敏: 敏感信息替换为 TOKEN"""
        token_map = {}
        result = text
        for pattern, pii_type in PII_PATTERNS:
            for match in re.finditer(pattern, result):
                original = match.group()
                token = f"[{pii_type}_{uuid.uuid4().hex[:8].upper()}]"
                token_map[token] = original
                result = result.replace(original, token, 1)

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

        for token, original in token_map.items():
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
| 沙箱预热池存活率 | < 80% | 资源水位预警 |
| Context Window 占用率 | > 85% | 防 Token 窗口溢出导致遗忘 |
| HITL 审批超时率 | > 20% | 审批流程效率问题 |
| WAL 未同步条目数 | > 100 | Kafka 网络问题或 Janitor 故障 |

### 10.4 尾部采样配置（OTel Collector）

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
Tier B（低成本）:       本地 Qwen2.5-7B、意图路由边界 case、脱水压缩
Tier C（高成本）:       主力模型（DeepSeek/Doubao）、复杂推理、报告生成
```

**降级策略**：Token 消耗达到预算 70% 自动切换 Tier B，95% 硬熔断。

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

-- 冷存储（MinIO S3，高压缩比）
-- 通过 TTL TO VOLUME 自动归档，无需手动运维
```

---

## 12. 部署规格

### 12.1 三级部署规格

| 规格 | 适用场景 | 精简说明 | 最小团队 |
|---|---|---|---|
| **规格 A（精简版）** | 内部验证 / 部门级 POC | 去除 ClickHouse（用 PG 代替），去除 gVisor（Docker 替代），单节点 Redis | 5 人 |
| **规格 B（标准版）** | 一般金融业务上线 | 完整 Harness，引入分区表与 Redis Sentinel，Tier 1-2 沙箱 | 9 人 |
| **规格 C（生产完整版）** | 核心业务 / 高并发 | 本方案全量组件，ClickHouse + Patroni HA + 跨 AZ 同城双活 | 13 人 |

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
  minio:        { replicas: 4, storage: "2Ti" }
  kafka:        { replicas: 3 }
  clickhouse:   { replicas: 2, storage: "1Ti" }   # 含独立加密列族

sandbox:
  gvisor_pool:  { min_idle: 10, max_size: 50, runtime_class: gvisor }
  runc_pool:    { min_idle: 20, max_size: 100 }

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
| **记忆系统** | DeerFlow Memory | 深度定制，JSON Schema 版本化脱注水 |
| **API 网关** | Kong / APISIX | 自建企业安全入口 |
| **通道集成** | DeerFlow Gateway | 扩展集成飞书 / 钉钉审批卡片 |
| **数据库** | PG(Patroni) + Milvus + Redis | 自配业务、向量与状态存储 |
| **容灾/审计** | RocksDB(WAL) + ClickHouse | Kafka 双写防止审计数据丢失 |
| **可观测** | Langfuse + OTel + Grafana | 追踪 LLM 推理细节与系统端到端耗时 |
| **提炼模型** | Qwen2.5-7B | 本地后置处理与 JSON 脱水任务 |
| **主力模型** | Doubao / DeepSeek V3 / Qwen | 模型降级热切机制：API 熔断时无缝切流至私有化部署 |


---

## 13. 实施 Roadmap

### 13.1 优先行动项（第一个月必须完成）

| # | 行动项 | 负责角色 | 验收标准 |
|---|---|---|---|
| 1 | Token Budget Guard 接入所有 Agent | Harness Engineer | 单 Thread 成本可量化，超预算自动告警 |
| 2 | Planner 重试上限硬编码（≤2次）+ 错误上下文携带 | Harness Engineer | Planner 最大 LLM 调用次数 ≤ 3 |
| 3 | SR 冷启动阈值下调至 0.75 + 抽样率提升至 20% | AI 算法 | 冷启动期 LLM 调用次数 < 稳定期 2x |
| 4 | Scratchpad L1 分片存储（64KB/片）+ 滚动压缩 | Harness Engineer | 超长推理链 Redis 内存占用 < 50MB |
| 5 | 全局工具锁注册表上线（max wait 30s） | 平台架构师 | 无静默挂起，超时返回 RESOURCE_CONTENTION |

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
  ├─ 三层记忆（L1 分片 + L2 Schema V2 + L3 租户隔离）
  ├─ gVisor 沙箱 POC（验证 K8s 兼容性，备选 Kata Containers）
  └─ HITL 三段式状态机（含资源补偿事务）

M5-M6  业务深水区
  ├─ 双向脱敏网关（PII Tokenization + RBAC 分级展示）
  ├─ WAL Janitor DaemonSet 独立部署（绑定 PV）
  ├─ MCP 智能问数（含 LegacyOracleAdapter）
  ├─ 财务报销 Agent
  └─ 金融审批 Agent（含 ABAC 多维权限校验）

M7-M8  平台化运营
  ├─ Skill 广场内部版（含上架审核流程 + 红队自动扫描）
  ├─ 二级路由（防 Skill 路由过载）
  ├─ Token 消耗租户维度监控 + 成本告警
  ├─ 沙箱预热池击穿保护（令牌桶 + SSE 透传）
  └─ Langfuse + OTel + Grafana 全链路可观测上线

M9-M10  生产就绪
  ├─ 规格 B → C 升级（ClickHouse 列族 + Patroni HA）
  ├─ 全链路压测（重点: 月末报表并发场景）
  ├─ 蓝红对抗演练（Prompt Injection + 越权测试）
  ├─ 第三方安全审计
  ├─ SR 冷启动结束，恢复正常配置（自动 1000 次触发）
  ├─ Harness 规则库沉淀（分级 WARN/BLOCK + 误报白名单）
  └─ 全面投产
```

### 13.3 团队职能配置（规格 C，13 人）

| 角色 | 人数 | 核心职责 |
|---|---|---|
| 平台架构师 | 2 | 整体架构决策、基础设施灾备联调、死锁防护 |
| **Harness Engineer** ★ | 2 | Nacos 规则维护、Scratchpad 审计、Token Budget、沙箱预热池 |
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
| **SR 冷启动退化** | 高 | 高 | 🔴 P0 | 冷启动阈值 0.75 + 20% 抽样 + 人工标注管道 |
| **跨线程资源死锁** | 中 | 高 | 🔴 P0 | 全局工具锁注册表 + 30s 超时 + RESOURCE_CONTENTION 类型化错误 |
| **HITL 资源泄漏** | 中 | 中 | 🟡 P1 | 三段式状态机 + 资源快照 + 补偿事务 + 催办提醒 |
| **Harness 规则误报** | 中 | 高 | 🟡 P1 | WARN 级先于 BLOCK + 叶节点白名单 + Nacos 紧急热更新 |
| **Schema 版本漂移静默失效** | 低 | 中 | 🟡 P1 | v1→v2 迁移函数 + Schema 校验三重试 + PG 原文降级保底 |
| **gVisor K8s 兼容性** | 中 | 中 | 🟡 P1 | M3 POC 验证 + Kata Containers 备选 + 三级沙箱降级 |
| **WAL 单点故障** | 低 | 高 | 🟡 P1 | Janitor DaemonSet 独立部署 + PV 绑定 + fsync 强制落盘 |
| **跨租户数据泄露** | 低 | 高 | 🟡 P1 | tenant_filter 强制注入 + 二次校验 + L1-L5 五层硬隔离 |
| **DeerFlow 供应链审查** | 中 | 高 | 🟡 P1 | 版本锁定 + Harness 外挂不侵入源码 + 6-8周迁移预案 |
| **沙箱预热池击穿** | 中 | 中 | 🟢 P2 | 令牌桶队列（深度 200）+ SSE 排队透传 + DaemonSet 补充 |
| **月末并发雪崩** | 中 | 高 | 🟢 P2 | 提前压测 + Token Budget 分租户限速 + 沙箱弹性扩容 |

---

## 附录：核心设计决策汇总

| 决策 | 选择 | 拒绝 | 理由 |
|---|---|---|---|
| Agent 边界控制 | 传统确定性代码（Harness）| LLM 自我约束 | LLM 可被诱导，代码不可 |
| 大状态存储 | MinIO（Claim-Check）+ Redis URI 指针 | 全量写入 Redis | 防 Redis OOM + 防并发写冲突 |
| 记忆压缩 | 本地 Qwen2.5-7B + Schema 校验 | 主力模型脱水 | 零主力模型 Token 消耗 |
| 审计可靠性 | WAL 先写本地 + Kafka 异步 | 直接写 Kafka | 网络故障不丢日志 |
| 路由策略 | 向量检索为主 + LLM 影子验证 | 纯 LLM 路由 | P99 延迟可控 + 成本可控 |
| 沙箱策略 | 三级按需分配（gVisor/runc/Process）| 一刀切 gVisor | 20% CPU Overhead 不可接受于全部场景 |
| HITL 超时 | 有感知否决 + 补偿事务 | 静默丢弃 | 资源泄漏 + 用户体验双重问题 |
| 资金操作 | **永远不走 Agent 链路** | Agent 自主执行 | 金融合规红线，任何优化不得触碰 |

---