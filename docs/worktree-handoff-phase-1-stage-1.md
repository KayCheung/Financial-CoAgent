# Worktree Handoff - phase-1-stage-1

## 基本信息

- Worktree 路径：`E:/Workspace/CodeRepository/opensource/phase-1-stage-1`
- Git 分支：`feature/phase-1-stage-1`
- 最近确认时间：`2026-04-11`
- 当前状态：`进行中`

## 当前目标

基于现有代码，先建立“一期实施方案（重点 T1.*）”的代码现状对照表，再收敛出一个只针对当前 worktree 的小型实施 Plan，随后再开始代码实现。

## 当前结论

当前仓库不是空白项目，而是已经有一套可运行的 MVP 壳子：

- 后端：FastAPI
- 前端：Electron + Vue
- 已具备：登录 stub、会话管理、SSE 流式聊天、消息持久化、打断/恢复、文件上传、粗粒度 token/cost 展示

当前后端主链路大致为：

`/api/v1/chat` -> `chat_runtime` -> `agent_orchestrator` -> LangChain/OpenAI -> SQLite 持久化

这说明现有代码更接近“聊天产品 MVP + 运行时交互框架”，还不是一期方案里的企业级 Agent 平台能力闭环。

`T1.1 ~ T1.11` 的代码现状对照表已整理完成，见：

- [code-status-mapping-phase-1-stage-1.md](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/docs/code-status-mapping-phase-1-stage-1.md:1)

当前 worktree 的小型实施 Plan 已整理完成，见：

- [implementation-plan-phase-1-stage-1.md](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/docs/implementation-plan-phase-1-stage-1.md:1)

当前已确认一条重要实施原则：

- 如果旧代码与目标架构偏离明显，优先删除或替换
- 不为了保留旧代码去堆适配层
- 不接受“复用导致结构持续恶化”的实现方式

`P0.1` 第一轮已完成：

- 已将后端编排从“直接调模型”收敛为可扩展的 `route -> plan -> execute` 骨架
- 已保持现有 SSE 协议和前端兼容
- 现有 smoke tests 已通过

`P0.2` 第一轮已完成：

- 已新增独立 `TokenBudget` / `TokenBudgetGuard` 模块
- 已在 chat runtime 中接入预算分配、warning、blocked、completed 事件
- 已支持超预算拦截
- 测试通过

当前还记录了两个必须后续清理的问题：

- `AgentOrchestrator.stream()` 只是迁移期兼容入口，不是长期保留接口
- 当前 `_route()` 中的关键字路由只是临时占位，不是正式 Semantic Router，实现 `T1.3` 时必须直接替换

## 已确认的代码现状

### 已实现或已有明确壳子

- FastAPI 服务入口
- 会话创建、列表、重命名、删除
- 会话消息持久化
- SSE 流式响应
- 中断、恢复、checkpoint、replay
- 前端聊天界面
- 本地文件上传
- 粗粒度 usage 统计
- stage 面板基础展示

### 仅为开发态 / MVP 实现

- 鉴权是固定 bearer token
- 用户身份是单用户 stub
- 数据库当前是 SQLite
- 文件存储是本地目录
- token 统计是估算值，不是 TokenBudgetGuard
- orchestrator 不是 LangGraph DAG 编排

### 关键缺失项

- 企业安全网关 / JWT / tenant 注入
- Semantic Router
- TokenBudgetGuard
- Planner DAG 与防死锁
- OCR 工具链
- WAL 审计
- PostgreSQL RLS
- Tool Interceptor
- 三层记忆
- HITL 审批
- ABAC
- Skill 中心

## 当前暂停点

暂停在“P0.2 第一轮完成，准备进入 P0.3 审计/WAL 基础骨架”的节点。

下一次恢复时，不要直接写代码，先完成：

1. 阅读 `implementation-plan-phase-1-stage-1.md`
2. 只聚焦一期实施方案中的 `T1.*`
3. 从 `P0.3` 开始
4. 将当前会话持久化与审计持久化分层

## 下一步

恢复后第一件事：

基于下面这份文件继续实际实现：

- [implementation-plan-phase-1-stage-1.md](E:/Workspace/CodeRepository/opensource/phase-1-stage-1/docs/implementation-plan-phase-1-stage-1.md:1)

输出目标：

- 完成 `P0.3`
- 搭出独立审计 entry 和本地 WAL 骨架
- 让审计与会话消息持久化不再混为一层概念
- 不破坏现有 SSE 协议和前端体验

## 恢复步骤

换电脑后按下面顺序恢复：

1. 打开仓库对应 worktree：
   - `E:/Workspace/CodeRepository/opensource/phase-1-stage-1`
2. 切到分支：
   - `feature/phase-1-stage-1`
3. 打开本文件：
   - `docs/worktree-handoff-phase-1-stage-1.md`
4. 先看：
   - `当前暂停点`
   - `下一步`
5. 然后从 `P0.3` 开始编码

## 工作习惯约定

后续每完成一个小节点，都更新本文件的以下内容：

- `当前结论`
- `当前暂停点`
- `下一步`

如果已经完成明确的功能改动，还应补充：

- 涉及文件
- 是否已测试
- 是否已提交 commit

## 最近一次确认

- worktree 已切换成功
- 当前分支：`feature/phase-1-stage-1`
- 当前工作区：已有本轮修改，未提交
- 当前建议：继续按小型实施 Plan，进入 `P0.3`
