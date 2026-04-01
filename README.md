# Financial-CoAgent

基于 LangChain / LangGraph 构建的企业金融级协作智能体，面向金融机构提供安全可控的 AI 协同服务。聚焦信贷审批、风险管控、财务核算、合规审查等核心场景，实现流程自动化、决策辅助与多角色协同执行。具备数据脱敏、操作审计、权限校验等金融级安全能力，支持结构化输出与内部系统对接。以轻量化、可扩展、可追溯为设计原则，助力企业在合规前提下提升业务效率与智能化水平。

## 一期实施顺序（与规划对齐）

| 阶段 | 内容 |
|------|------|
| **S1** | 基础平台：登录鉴权、会话、流式对话（SSE）、中断/恢复、用量统计（当前仓库已落地骨架与联调） |
| S2 | Skill 体系与市场 |
| S3 | 任务中心与定时任务 |
| S4 | 财务报销主链 |
| S5 | 助理、经营分析、知识库 |
| S6 | 安全与上线（OIDC、审计完善等） |

## 项目结构

- `server/`：FastAPI 网关（`app/` 分包：`api/`、`services/`、`core/`）
- `desktop/CoAgent/`：Electron + Vue + Vite + Pinia 桌面端

## 启动命令

### 1. 启动后端（S1）

```bash
cd server
# Windows（示例为项目内 .venv）
.\.venv\Scripts\activate
# 复制环境变量模板后按需修改
copy .env.example .env

pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

- 健康检查：<http://127.0.0.1:8000/health>
- S1 接口前缀：`/api/v1`（如 `POST /api/v1/auth/login`、`POST /api/v1/chat/stream`）

开发鉴权：先 `POST /api/v1/auth/login` 获取 `access_token`，请求头带 `Authorization: Bearer <token>`。默认令牌见 `server/.env.example` 中的 `DEV_BEARER_TOKEN`。

LLM 接入（S1）：`/api/v1/chat/stream` 通过 `LangChain` 流式调用模型。配置 `OPENAI_API_KEY` 与 `OPENAI_MODEL` 后可走真实流式；若密钥不可用或网络受限，会自动回退到占位流并返回 `llm_unavailable` 提示事件。

### 2. 启动桌面端

```bash
cd desktop/CoAgent
npm install
npm run dev
```

默认连接网关 `http://127.0.0.1:8000`，可在 `desktop/CoAgent` 下配置环境变量 `VITE_GATEWAY_URL` 覆盖。

桌面窗口内可先点「登录（开发）」再发消息；也可直接发送，会自动完成开发登录并（若尚无会话）创建会话。流式过程中可点「中断流」，再「从检查点恢复」验证 S1 流程。

## 说明

- S1 已通过 **LangChain** 接通流式会话与中断恢复；当前 `session/task/usage` 仍为内存态，后续 Sprint 接 PostgreSQL/Redis。
