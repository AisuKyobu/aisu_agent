# Aisu

基于 LangGraph + LangChain DeepSeek 的多功能 AI Agent Web 面板。  
支持聊天、网络搜索、文件操作、浏览器自动化、定时任务、技能系统、用户认证、持久记忆与在线反思。

适合个人开发者日常使用，也适合作为 AI Agent 项目的公开演示 / 面试展示。

## 功能一览

| 功能 | 说明 |
|------|------|
| 智能对话 | LangGraph 多节点图编排（分析→路由→记忆→Agent→工具→校验→总结） |
| 网络搜索 | SearXNG 聚合搜索（百度/搜狗），内置缓存 |
| 浏览器自动化 | Playwright Chromium 驱动，支持打开/点击/输入/截图 |
| 文件读写 | 沙箱隔离的文件读写，路径自动映射到沙箱目录 |
| 命令执行 | 白名单 + 危险命令检测 + 用户确认审批 |
| 技能系统 | 运行时加载 `SKILL.md`，Agent 按需调用，支持 ZIP 安装 |
| 定时任务 | 周期性执行 Agent 任务，支持单次/重复 |
| 会话管理 | 多会话，跨会话历史搜索，断点续聊 |
| 持久记忆 | 基于语义搜索的长期记忆（记忆、反思、情景记录） |
| 在线反思 | 每 8 步自动检查是否偏离目标，并写入反思记忆 |
| 用户认证 | 邮箱注册/登录，JWT Token，用户会话隔离 |
| 权限隔离 | 游客/普通用户/管理员分权；工作区仅管理员可编辑 |
| 多 Profile | dev（全功能）、qq（受限工具）自动切换 |
| 监控面板 | 实时查看会话状态、来源、执行模式、工具使用情况 |
| Web 面板 | FastAPI + Vue 3，含聊天/监控/技能/指令/定时/设置面板 |
| AstrBot 接入 | QQ 群聊转接，自动切 qq profile |
| 公开演示模式 | 每 IP 限制 5 条对话，仅开放搜索/读取工具，适合面试展示 |

## 快速开始（本地）

```bash
pip install -r requirements.txt
playwright install chromium

copy .env.example .env
# 填入 DEEPSEEK_API_KEY

python main.py              # Web 面板 :7890
```

## Docker 部署（生产推荐）

### 1. 准备 Chromium 浏览器

```bash
mkdir -p browsers
# 将 Playwright Chromium zip 放到 browsers/chrome-linux64.zip
# 或修改 Dockerfile 改用 CDN 自动下载
```

### 2. 配置文件

```bash
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY
# 如需邮件验证功能，填写 SMTP_* 配置
```

### 3. 构建并启动

```bash
docker compose up -d --build
```

访问 http://localhost:7890

### 4. 更新

```bash
git pull
docker compose up -d --build
```

## Docker 公开演示模式（DEMO MODE）

公开试用模式，每 IP 限制 5 条对话，仅开放只读安全工具。

```bash
# 需要 .env 包含 DEEPSEEK_API_KEY
# 确保服务器有 docker-compose.yml 所在目录的访问权限
git pull
docker compose -f docker-compose.demo.yml build --no-cache aisu
docker compose -f docker-compose.demo.yml up -d --force-recreate aisu
```

Demo 模式限制：
- 每 IP 24 小时内最多 5 条对话消息
- 可用工具：`web_search`、`web_fetch`、`read_file`（仅限沙箱内文件）
- 禁用工具：`run_command`、`write_file`、`browser_*`、`cron_add`、技能安装/加载
- 保留登录/注册功能，登录用户同样受 5 条/ IP 限制
- 文件下载需登录
- 默认 admin 密码随机生成（打印在容器日志中）

访问 http://your-server-ip:7890

## 测试

```bash
# 运行所有测试
python -m pytest tests/ -q

# 带详细输出的运行
python -m pytest tests/ -v

# 运行特定测试文件
python -m pytest tests/test_skills.py -v

# 运行测试并生成覆盖率报告
python -m pytest tests/ --cov=. --cov-report=term-missing
```

测试覆盖：
- 技能注册与发现
- 技能执行器（状态机解析、参数替换）
- 工具集解析与递归合并
- 工具注册分发
- 语言环境检测
- verify 规则（L2/L3 校验）
- 配置文件导入

## 项目结构

```
├── main.py                 入口
├── config.py               配置（含 DEMO_MODE）
├── Dockerfile              多阶段构建（node → python）
├── docker-compose.yml      完整生产部署
├── docker-compose.demo.yml 公开演示部署
├── .env.example            环境变量模板
├── agent/
│   ├── conversation_graph.py  对话图编排（10 节点 StateGraph）
│   ├── state.py               状态定义
│   ├── nodes/                 各节点逻辑（analyzer/router/agent/verifier...）
│   ├── skills/                技能注册/发现/执行
│   ├── memory/                记忆存储与检索
│   ├── cron.py                定时任务管理器
│   └── session.py             会话持久化
├── tools/
│   ├── registry.py            工具注册 + 权限过滤
│   ├── tool_registry.py       运行时工具分发
│   ├── toolsets.py            工具集分组（search/action/reasoning/planning）
│   ├── sandbox.py             沙箱隔离执行
│   ├── web_tools.py           网络搜索/抓取
│   ├── file_tools.py          文件读写
│   ├── command_tools.py       命令执行
│   ├── browser_tools.py       浏览器自动化
│   ├── cron_tools.py          定时任务
│   ├── skill_tools.py         技能加载
│   └── memory_tools.py        持久记忆
├── server/
│   ├── app.py                 FastAPI 应用（路由 + WebSocket）
│   ├── auth.py                认证（JWT/注册/登录/邮箱验证）
│   ├── db.py                  用户数据库
│   ├── state.py               会话状态/WS 广播
│   └── rate_limit.py          IP 限流（Demo 模式）
├── web/                       Vue 3 前端
│   └── src/
│       ├── App.vue            主页面（Tab 切换 + Demo Banner）
│       ├── components/        各面板组件
│       └── composables/       通用逻辑（WebSocket/Auth）
├── skills/                    技能定义（SKILL.md）
├── workspace/                 用户设定（AGENTS.md / USER.md）
└── tests/                     测试
```

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `DEEPSEEK_API_KEY` | 是 | - | DeepSeek API 密钥 |
| `DEEPSEEK_BASE_URL` | 否 | `https://api.deepseek.com/v1` | API 地址 |
| `MODEL_NAME` | 否 | `deepseek-chat` | 模型名称 |
| `SEARXNG_BASE_URL` | 否 | `http://localhost:8888` | SearXNG 地址 |
| `DATA_DIR` | 否 | `.` | 数据存储目录 |
| `SMTP_HOST` | 否 | - | 邮件服务器（用于邮箱验证） |
| `SMTP_PORT` | 否 | `587` | 邮件服务器端口 |
| `SMTP_USER` | 否 | - | 邮箱账号 |
| `SMTP_PASSWORD` | 否 | - | 邮箱密码/授权码 |
| `SITE_URL` | 否 | `http://localhost:7890` | 站点 URL（用于邮件链接） |
| `DEMO_MODE` | 否 | `false` | 开启公开演示模式 |
| `DEMO_MAX_MSG_PER_IP` | 否 | `5` | Demo 模式每 IP 最大对话数 |
| `SANDBOX_MODE` | 否 | `host` | 沙箱模式（host/docker） |
| `LANGCHAIN_API_KEY` | 否 | - | LangSmith 可观测性 |

## 最近更新

- 新增在线反思系统：普通对话无 `task_graph` 时，自动以最近用户消息为目标进行自省。
- UI  redesigned：加深背景渐变、粉青双 accent、WelcomeCard 入职引导、工具卡片、代码复制按钮。
- 工作区权限细化：登录用户可查看全部文件，仅管理员可编辑。
- 监控面板支持游客访问，并按用户身份隔离会话可见范围。
- 移除旧 Jinja2 模板与 static 前端资源，统一使用 Vue 3 构建产物。
