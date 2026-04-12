# 一期实施方案代码现状对照表 - phase-1-stage-1

## 范围

本文件仅对照《企业级Agent一期实施方案 v1.1》中的 `T1.1 ~ T1.11`。

状态定义：

- `已实现`：已有可工作的实现，且基本覆盖任务核心目标
- `半实现`：已有壳子或局部能力，但与方案目标差距明显
- `未实现`：当前代码中没有对应能力，或仅停留在口头/README 层

---

## 总览

| 任务 | 名称 | 状态 | 结论 |
|---|---|---|---|
| T1.1 | 企业安全网关搭建 | 半实现 | 有应用层 Bearer 校验，但没有企业网关/JWT/租户注入 |
| T1.2 | DeerFlow 核心引擎部署 | 半实现 | 有 FastAPI + LangChain 流式主链，但不是 LangGraph 工作流内核 |
| T1.3 | Semantic Router 基础版 | 未实现 | 未见意图路由、向量检索、Milvus 接入 |
| T1.4 | Token Budget 守护机制 | 半实现 | 只有粗粒度 token 估算与 usage 统计，没有预算守护和熔断 |
| T1.5 | Planner 防死锁机制 | 未实现 | stage 事件是前端展示壳，不是 DAG Planner |
| T1.6 | PaddleOCR 发票解析服务 | 未实现 | 只有通用文件上传，没有 OCR 服务或发票抽取 |
| T1.7 | 知识库 Agent（第一个 Skill） | 未实现 | 未见知识入库、检索、RAG 或 Skill 路由 |
| T1.8 | WAL 双写审计基础版 | 半实现 | 有消息/流事件持久化，但不是 WAL + 审计总线 |
| T1.9 | 基础前端界面 | 已实现 | 聊天、历史、SSE、上传、stage 面板基本可用 |
| T1.10 | LLM 能力注册表 MVP | 未实现 | 未见能力标签、节点准入、兼容降级逻辑 |
| T1.11 | PostgreSQL 多租户 RLS 配置 | 未实现 | 当前默认 SQLite，无 PG RLS、多租户会话变量注入 |

---

## 逐项对照

### T1.1 企业安全网关搭建

- 状态：`半实现`
- 现有证据：
  - [server/app/api/auth.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/app/api/auth.py:1)
  - [server/app/api/deps.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/app/api/deps.py:1)
  - [server/app/core/security.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/app/core/security.py:1)
  - [server/app/main.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/app/main.py:1)
- 已有能力：
  - 统一 API 前缀 `/api/v1`
  - Bearer Token 校验
  - CORS 中间件
  - `/health` 健康检查
- 缺失能力：
  - Kong/APISIX 网关
  - JWT 验签
  - `tenant_id/user_id/role` 透传注入
  - 限流
  - 网关统一错误体与 trace_id 贯穿
- 判断：
  - 现有实现只能算开发态应用内鉴权，不是企业安全网关
- 建议接入方式：
  - `复用少量 API 结构，重构鉴权与入口层`

### T1.2 DeerFlow 核心引擎部署

- 状态：`半实现`
- 现有证据：
  - [server/app/agent/orchestrator.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/app/agent/orchestrator.py:1)
  - [server/app/services/chat_runtime.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/app/services/chat_runtime.py:1)
  - [server/app/models/schemas.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/app/models/schemas.py:1)
  - [server/requirements.txt](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/requirements.txt:1)
- 已有能力：
  - FastAPI 服务骨架
  - LangChain 流式调用
  - 基础运行态与 stage 事件
  - 中断、恢复、replay
- 缺失能力：
  - `AgentFastState`
  - `router -> planner -> executor -> END` 的 LangGraph 工作流
  - 基于节点的统一错误分类
  - 真正的 DeerFlow/LangGraph 编排核心
- 判断：
  - 当前是“聊天运行时壳”，不是方案中的工作流引擎
- 建议接入方式：
  - `保留 chat runtime/SSE 交互层，重构后端编排内核`

### T1.3 Semantic Router 基础版

- 状态：`未实现`
- 现有证据：
  - 当前 `server/app/` 下无 router 模块、无 Milvus 接入、无 embedding 检索逻辑
  - [README.md](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/README.md:1) 对 S1 的描述也未体现真实 Router 落地
- 缺失能力：
  - 意图向量库
  - Milvus
  - embedding
  - 冷启动阈值
  - LLM fallback 路由
  - router 日志
- 建议接入方式：
  - `新增模块实现`

### T1.4 Token Budget 守护机制

- 状态：`半实现`
- 现有证据：
  - [server/app/services/usage_tracker.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/app/services/usage_tracker.py:1)
  - [server/app/api/usage.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/app/api/usage.py:1)
  - [server/app/services/chat_runtime.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/app/services/chat_runtime.py:1)
- 已有能力：
  - 输入/输出 token 粗略估算
  - cost 展示
  - session 维度 usage 汇总
- 缺失能力：
  - `TokenBudget`
  - `TokenBudgetGuard`
  - budget 档位
  - 70% 告警 / 95% 熔断
  - Redis 幂等计费
  - 调用前后统一扣减
- 判断：
  - 只有“统计”，没有“守护”
- 建议接入方式：
  - `局部复用 usage 展示，新增真正的 budget 守护层`

### T1.5 Planner 防死锁机制

- 状态：`未实现`
- 现有证据：
  - [server/app/services/chat_runtime.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/app/services/chat_runtime.py:1)
- 说明：
  - 当前会发出 `planner`、`responder` 这类 stage 事件
  - 但这些只是前端/运行时展示语义，不存在真实 Planner DAG
- 缺失能力：
  - DAG
  - 环路检测
  - 依赖完整性校验
  - 孤立节点检测
  - Planner 自纠错
  - Critic 后路由
- 建议接入方式：
  - `新增模块实现`

### T1.6 PaddleOCR 发票解析服务

- 状态：`未实现`
- 现有证据：
  - [server/app/api/files.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/app/api/files.py:1)
- 已有能力：
  - 文件上传
  - 用户级本地目录保存
- 缺失能力：
  - OCR 服务
  - 发票字段抽取
  - 置信度
  - OCR Tool
  - Claim-Check 规范化设计
- 判断：
  - 现在只是通用上传，不是 OCR 链路
- 建议接入方式：
  - `复用上传入口的一部分，新增 OCR 服务与工具层`

### T1.7 知识库 Agent（第一个 Skill）

- 状态：`未实现`
- 现有证据：
  - 当前后端无知识入库、检索、RAG、Skill Registry 模块
- 缺失能力：
  - 文档切片
  - embedding 入库
  - 检索召回
  - reranker
  - Skill 路由
  - 引用溯源
- 建议接入方式：
  - `新增模块实现`

### T1.8 WAL 双写审计基础版

- 状态：`半实现`
- 现有证据：
  - [server/app/services/session_store.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/app/services/session_store.py:1)
  - [server/alembic/versions/20260401_01_init_persistence.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/alembic/versions/20260401_01_init_persistence.py:1)
  - [server/alembic/versions/20260401_02_add_checkpoints.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/alembic/versions/20260401_02_add_checkpoints.py:1)
  - [server/alembic/versions/20260401_03_stream_events.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/alembic/versions/20260401_03_stream_events.py:1)
- 已有能力：
  - 会话消息持久化
  - 流事件持久化
  - checkpoint 持久化
  - stage snapshot 持久化
- 缺失能力：
  - 本地 WAL 文件
  - `fsync`
  - PG 热审计表设计
  - ONS/RocketMQ 审计总线
  - Janitor
  - 审计 schema version
- 判断：
  - 当前是“业务状态持久化”，不是“可恢复审计 WAL”
- 建议接入方式：
  - `保留部分持久化表思路，新增独立审计/WAL 体系`

### T1.9 基础前端界面

- 状态：`已实现`
- 现有证据：
  - [desktop/CoAgent/src/renderer/src/views/ChatView.vue](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/desktop/CoAgent/src/renderer/src/views/ChatView.vue:1)
  - [desktop/CoAgent/src/renderer/src/api/gateway.js](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/desktop/CoAgent/src/renderer/src/api/gateway.js:1)
  - [desktop/CoAgent/src/renderer/src/stores/session.store.js](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/desktop/CoAgent/src/renderer/src/stores/session.store.js:1)
  - [desktop/CoAgent/src/renderer/src/stores/stage.store.js](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/desktop/CoAgent/src/renderer/src/stores/stage.store.js:1)
  - [desktop/CoAgent/src/renderer/src/stores/usage.store.js](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/desktop/CoAgent/src/renderer/src/stores/usage.store.js:1)
- 已有能力：
  - 会话列表
  - 消息历史
  - SSE 流式聊天
  - 中断 / 恢复
  - 文件上传
  - stage 面板
  - usage 展示
- 差距：
  - 当前上传展示是通用文件，不是发票 OCR 专项结果页
  - 仍偏向聊天工作台，而不是一期业务闭环 UI
- 判断：
  - 可作为 T1.9 的现有基础直接复用
- 建议接入方式：
  - `高复用`

### T1.10 LLM 能力注册表 MVP

- 状态：`未实现`
- 现有证据：
  - [server/app/agent/orchestrator.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/app/agent/orchestrator.py:1) 直接读取配置并构造单一模型
  - [server/app/core/config.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/app/core/config.py:1) 仅保留基础模型配置项
- 缺失能力：
  - ModelCapabilityRegistry
  - 能力标签
  - 节点准入检查
  - forbidden nodes
  - 兼容降级
- 建议接入方式：
  - `新增模块实现`

### T1.11 PostgreSQL 多租户 RLS 配置

- 状态：`未实现`
- 现有证据：
  - [server/app/core/config.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/app/core/config.py:1)
  - [server/app/services/session_store.py](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/app/services/session_store.py:1)
  - [server/alembic.ini](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/server/alembic.ini:1)
- 现状：
  - 默认数据库是 `sqlite:///./coagent.db`
  - 无租户字段注入
  - 无 PG RLS
  - 无 `SET app.current_tenant`
- 建议接入方式：
  - `需要从存储层重新接入 PostgreSQL 能力`

---

## 现阶段最重要判断

当前 worktree 适合的推进方式不是“在现有代码里零碎补点功能”，而是：

1. 保留现有可用的交互壳层：
   - FastAPI 路由
   - SSE 流式协议
   - 会话 UI
   - 中断/恢复体验

2. 在后端逐步替换或新增平台核心能力：
   - 鉴权与上下文
   - 编排内核
   - TokenBudget
   - 审计/WAL
   - OCR / Router / Skill

3. 优先复用前端和会话层，谨慎复用后端编排层

---

## 建议的实施收敛

如果当前 worktree 确实对应 `phase-1-stage-1`，建议下一步只围绕下面几项收敛小 Plan：

- 优先级 P0：
  - T1.2 核心引擎骨架收敛
  - T1.4 TokenBudgetGuard 基础版
  - T1.8 审计/WAL 基础骨架

- 优先级 P1：
  - T1.1 开发态鉴权向 JWT/tenant 上下文过渡
  - T1.11 PostgreSQL 迁移准备

- 优先级 P2：
  - T1.3 Router
  - T1.6 OCR
  - T1.7 知识库 Skill

原因：

- 当前代码最大复用价值在交互壳和运行时协议
- 最大风险在后端核心能力与方案设计严重不对齐
- 因此应该先补平台底座，而不是先堆业务能力
