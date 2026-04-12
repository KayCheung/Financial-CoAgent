# 当前 Worktree 小型实施 Plan - phase-1-stage-1

## 当前状态

- `P0.1` 已完成
- `P0.2` 已完成
- `P0.3` 已完成
- `P1.1` 已完成
- `P1.2` 第一轮已完成
- `P2.1` 第一轮核心已完成
- `P2.2` 第二轮进行中
- `AgentOrchestrator.stream()` 旧兼容入口已删除

### P1.2 完成说明

- 已引入统一数据库入口：`server/app/core/database.py`
- 数据源解析顺序现为：
  1. 显式 `DATABASE_URL`
  2. Nacos 数据源 YAML
  3. sqlite 回退
- Nacos 客户端使用官方 Python SDK，不使用手写 HTTP 适配
- Alembic 已接入统一数据库 URL
- `audit_entries` 已纳入迁移链
- PostgreSQL 迁移链路已在本地验证通过

### 当前约束

- 如存在官方 SDK 或成熟、维护良好的开源 SDK，优先直接复用，不重复造轮子。
- 阶段相关 md 文档新增内容统一使用中文，不再新增英文标题或状态块。

### 下一步

- 继续推进 `P2.2 / T1.6 OCR`
- 保持 OCR 为真实工具执行步骤，而不是只在提示词里模拟
- OCR 稳定后，继续补强结构化抽取和工具执行边界

## 目标

基于当前 worktree 的现有 MVP 代码，收敛出一个适合“一期阶段一”的实际落地顺序。

这里不追求一次把 `T1.1 ~ T1.11` 全做完，而是优先建立后端底座的正确演进路径，尽量复用已有前端和运行时交互能力。

---

## 计划原则

1. 保留现有可复用的壳层
   - FastAPI 路由层
   - SSE 流式协议
   - Electron/Vue 聊天界面
   - 中断 / 恢复 / replay 用户体验

2. 优先替换后端核心，而不是继续堆前端功能
   - 当前最大差距在平台能力，不在 UI

3. 先做“支撑后续功能的底座”，再做业务能力
   - 先补状态模型、预算、审计、存储方向
   - 再接 Router / OCR / 知识库

4. 避免大爆炸式重构
   - 每一步都保留可运行主链路
   - 新能力优先通过适配层接入，再逐步替换旧逻辑

5. 不为复用而复用
   - 如果旧代码与目标架构偏离明显，直接删除或替换
   - 不为了兼容旧实现去增加低价值适配层
   - 不接受“能跑但持续堆积复杂度”的屎山式演进

6. 复用前先判断结构收益
   - 复用的前提是：能降低工作量，且不会扭曲目标设计
   - 如果复用成本接近重写成本，优先选择重写

---

## 总体排序

### 第一组：先打底座

- P0.1：T1.2 核心引擎骨架收敛
- P0.2：T1.4 TokenBudgetGuard 基础版
- P0.3：T1.8 审计/WAL 基础骨架

### 第二组：补企业化基础

- P1.1：T1.1 开发态鉴权向 JWT/tenant 上下文过渡
- P1.2：T1.11 PostgreSQL 迁移准备

### 第三组：补业务闭环能力

- P2.1：T1.3 Semantic Router
- P2.2：T1.6 OCR 发票解析
- P2.3：T1.7 知识库 Skill

### 延后项

- T1.5 Planner 防死锁机制
- T1.10 LLM 能力注册表

说明：

- 这两个很重要，但都建立在“核心编排骨架”已经切换到节点化设计之上
- 当前代码还没有真正的 Planner/DAG 结构，过早实现会变成重复返工

---

## 每项具体策略

### P0.1 T1.2 核心引擎骨架收敛

#### 目标

把当前“单 orchestrator 直接调用模型”的模式，收敛为可扩展的运行时骨架，为后续 Router / Planner / Executor 留标准接口。

#### 当前可复用

- `server/app/services/chat_runtime.py`
- `server/app/api/chat.py`
- `server/app/models/schemas.py`
- 前端 SSE 事件消费逻辑

#### 需要重构

- `server/app/agent/orchestrator.py`

#### 改造方向

- 将当前 orchestrator 拆成更明确的层次：
  - `runtime input`
  - `route step`
  - `plan step`
  - `execute step`
  - `response assembly`
- 即使第一版内部仍然是简化逻辑，也要先把接口形状搭出来
- 明确引入统一状态对象，例如：
  - `thread_id`
  - `trace_id`
  - `tenant_id`
  - `user_id`
  - `current_stage`
  - `router_result`
  - `plan_result`
  - `tool_calls`
  - `final_answer`

#### 交付标准

- 现有聊天流程仍可跑通
- stage 事件仍能推送到前端
- 编排代码不再只是一层直接调用 LLM

---

### P0.2 T1.4 TokenBudgetGuard 基础版

#### 目标

把当前“用量统计”升级为“运行时预算守护”的第一步。

#### 当前可复用

- `server/app/services/usage_tracker.py`
- 前端 usage 展示

#### 需要新增

- `token_budget.py` 或同类模块
- budget 对象
- guard 对象
- 与 chat runtime / LLM 调用封装的接入点

#### 第一版边界

- 先不强依赖 Redis
- 先做进程内 + 持久化日志/事件留痕版本
- 档位先实现：
  - `simple`
  - `moderate`
  - `complex`
- 先把拒绝策略和告警事件接上

#### 交付标准

- 每个 run 有预算档位
- 达阈值时有明确事件/日志
- 超预算能拒绝继续执行

#### 当前进展

- 已完成第一轮基础实现
- 当前已具备：
  - 独立 `TokenBudget` / `TokenBudgetGuard` 模块
  - `simple / moderate / complex` 档位定义
  - warning / blocked / completed 预算事件
  - 超预算拦截
- 当前仍未做：
  - Redis 幂等计费
  - 跨进程一致性
  - 持久化预算回填

---

### P0.3 T1.8 审计/WAL 基础骨架

#### 目标

把现在的“会话数据持久化”与“审计持久化”分开，先搭出独立审计通道的骨架。

#### 当前可复用

- `session_store.py` 中已有的持久化习惯
- `stream_events` 表的部分事件语义

#### 需要新增

- 独立的审计 entry 结构
- 本地 WAL 存储类
- 审计写入 facade
- schema version 字段

#### 第一版边界

- 先不接 MQ
- 先不做完整 Janitor
- 先完成：
  - 本地 WAL 文件写入
  - 成功后热审计表写入
  - 失败保留 WAL

#### 交付标准

- 关键执行节点有独立审计 entry
- 审计与会话消息不再混为一层概念

#### 当前进展

- 已完成第一轮基础实现
- 当前已具备：
  - 独立 `AuditEntry` / `AuditStore` 模块
  - 本地 WAL 文件落盘
  - 热审计表 `audit_entries`
  - chat runtime 对关键事件的审计写入
- 当前仍未做：
  - MQ 总线
  - Janitor 重放
  - 更细粒度审计 schema 与回放器

---

### P1.1 T1.1 鉴权向 JWT/tenant 上下文过渡

#### 目标

从“固定 dev token + 单用户”过渡到“可携带上下文的开发态身份模型”。

#### 第一版不追求

- 不强行先上 Kong/APISIX
- 不要求完整企业 SSO

#### 第一版先做

- Principal 扩充：
  - `user_id`
  - `tenant_id`
  - `role`
- 请求上下文注入
- 所有关键服务接口签名补充 tenant 维度

#### 交付标准

- 后端主链路不再默认只有单一 dev 用户语义

#### 当前进展

- 已完成第一轮基础实现
- 当前已具备：
  - 开发态可解析 token
  - `Principal` 扩展为 `user_id / name / tenant_id / role / raw_token`
  - chat 主链路已透传 tenant/role 上下文
- 当前仍未做：
  - 真正的 JWT 验签
  - 网关注入 Header
  - 多租户权限矩阵与细粒度鉴权

---

### P1.2 T1.11 PostgreSQL 迁移准备

#### 目标

先把 SQLite 风格的数据访问，整理成未来能切 PostgreSQL 的形状。

#### 第一版先做

- 统一数据库 URL 配置路径
- 清理 SQLite 假设
- 给核心表补 tenant 维度的设计预留
- 明确 Alembic 迁移方向

#### 暂不做

- 直接把 RLS 全量落地

#### 交付标准

- 存储层代码不再强绑定 SQLite 心智

#### 当前进展

- 已完成第一轮基础实现
- 当前已具备：
  - 统一数据库入口 `app/core/database.py`
  - 优先通过官方 Nacos Python SDK 读取 datasource
  - Alembic 已可直接迁移到本地 PostgreSQL
  - 审计表 `audit_entries` 已纳入迁移链
- 当前仍未做：
  - 真正的 RLS
  - tenant 维度字段补齐
  - PostgreSQL 专项索引与性能策略

---

## 第一刀建议

### 第一刀：先做 P0.1 核心引擎骨架收敛

原因：

- 它决定后面 T1.4 / T1.8 / T1.5 / T1.10 的接入位置
- 如果不先把后端编排骨架整理出来，后续预算、审计、Planner 都会接在旧结构上，返工概率高

### 第一刀的实际切入文件

- [server/app/agent/orchestrator.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/app/agent/orchestrator.py:1)
- [server/app/services/chat_runtime.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/app/services/chat_runtime.py:1)
- [server/app/models/schemas.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/app/models/schemas.py:1)

### 第一刀的目标边界

- 不改前端协议
- 不引入大规模新依赖
- 不一次做完真正 LangGraph DAG
- 先把当前后端整理成“可挂 Router / Planner / Executor / Budget / Audit”的骨架

### P0.1 已知迁移债务

- `AgentOrchestrator.stream()` 迁移期兼容入口已删除
- 主链路现已统一使用 `prepare()` + `stream_response()`

- 当前语义路由已替换旧的关键字分支，现阶段采用轻量相似度路由实现
- 它已经比早期硬编码规则更稳，但后续仍可继续演进为更完整的 Semantic Router
- 到 `T1.3 / P2.1 Semantic Router` 落地时，这段逻辑应直接替换，不允许继续在关键字规则上堆演进

---

## 建议执行顺序

1. 先重构编排骨架
2. 再接 TokenBudget 基础版
3. 再接审计/WAL 基础骨架
4. 再扩 Principal 和 tenant 上下文
5. 再准备 PostgreSQL 迁移
6. 最后进入 Router / OCR / 知识库

---

## 暂停恢复提示

如果中途中断，恢复时优先阅读：

- [worktree-handoff-phase-1-stage-1.md](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/docs/worktree-handoff-phase-1-stage-1.md:1)
- [code-status-mapping-phase-1-stage-1.md](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/docs/code-status-mapping-phase-1-stage-1.md:1)
- 本文件

然后继续按照：

`P0.1 -> P0.2 -> P0.3`

这个顺序推进。
