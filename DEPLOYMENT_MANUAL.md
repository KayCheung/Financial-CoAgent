# Financial-CoAgent 前后端部署手册

本文是本项目的本地部署标准路径，包含“从零重来”与“日常增量更新”两套流程，并覆盖已踩过的问题。

## 1. 前置要求

- Windows 10/11
- Python 3.11+（推荐 3.12）
- Node.js 18+（推荐 20 LTS）
- npm 9+
- 数据库：
  - 本地快速验证：SQLite（默认）
  - 长期联调：PostgreSQL（推荐）

## 2. 目录约定

- 项目根目录：`Financial-CoAgent/`
- 后端目录：`Financial-CoAgent/server`
- 前端目录：`Financial-CoAgent/desktop/CoAgent`

## 3. 后端部署（从零重来，推荐）

### 3.1 停服务并进入后端目录

```powershell
cd E:\Workspace\CodeRepository\kltb\finance-agent\Financial-CoAgent\server
```

### 3.2 重新创建干净虚拟环境

```powershell
deactivate
Remove-Item .\.venv -Recurse -Force -ErrorAction SilentlyContinue
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

验证 Python 路径必须在当前项目：

```powershell
python -c "import sys; print(sys.executable)"
```

输出应包含：

- `...\kltb\finance-agent\Financial-CoAgent\server\.venv\Scripts\python.exe`

### 3.3 安装依赖

```powershell
pip install -r requirements.txt
```

### 3.4 初始化环境变量

```powershell
copy .env.example .env
```

至少确认：

- `DEV_BEARER_TOKEN`
- `OPENAI_API_KEY`（可选）
- `OPENAI_MODEL`
- `DATABASE_URL`
- `UPLOAD_DIR`

### 3.5 重建数据库并执行迁移（SQLite 推荐）

```powershell
Remove-Item .\coagent.db -ErrorAction SilentlyContinue
alembic upgrade head
alembic current
```

正确输出应为：

- `20260401_02 (head)`

### 3.6 启动后端

```powershell
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

- `http://127.0.0.1:8000/health`

## 4. 前端部署

```powershell
cd E:\Workspace\CodeRepository\kltb\finance-agent\Financial-CoAgent\desktop\CoAgent
npm install
npm run dev
```

默认网关：`http://127.0.0.1:8000`。如需覆盖，配置：

```env
VITE_GATEWAY_URL=http://127.0.0.1:8000
```

## 5. 联调验收清单

1. 后端 `health` 返回 `ok`
2. 前端登录（开发）
3. 新建会话并发送
4. 中断后恢复（checkpoint）
5. 切会话并回放历史
6. 上传图片并检查消息 `attachments`

## 6. 常见问题（本次已验证）

### 6.1 `alembic: CommandNotFoundException`

原因：脚本不可见或 venv 混用。  
处理：

```powershell
python -c "import sys; print(sys.executable)"
pip install -r requirements.txt
alembic upgrade head
```

### 6.2 `ModuleNotFoundError: No module named 'app'`（alembic 运行时）

原因：迁移环境模块路径不正确。  
处理：已在 `server/alembic/env.py` 内固定 `sys.path`，拉取最新代码后重试。

### 6.3 `table ... already exists`（如 `sessions` / `session_checkpoints`）

原因：数据库已由旧逻辑建表，Alembic 首次迁移再建表冲突。  
处理优先级：

1) 开发环境直接重建（推荐）：

```powershell
Remove-Item .\coagent.db -ErrorAction SilentlyContinue
alembic upgrade head
```

2) 需保留数据时使用 stamp：

```powershell
alembic stamp 20260401_01
alembic stamp 20260401_02
alembic current
```

### 6.4 `RuntimeError: Directory './uploads' does not exist`

处理：已在后端启动时自动创建上传目录；若你运行旧代码，请更新或手工创建 `server/uploads`。

## 7. 日常更新流程（增量）

1. 停后端
2. `git pull`
3. 激活后端 venv
4. `pip install -r requirements.txt`（如依赖有变更）
5. `alembic upgrade head`
6. 启动后端
7. 启动/刷新前端并回归核心链路
