# Aisu

基于 LangGraph 的个人 AI 助手，支持 CLI / TUI / Web 三种交互模式。

名字由来：**Aisu**（あいす）= 用户网名 aisukyobu 的前四个字母 + Agent。

## 启动

```bash
python main.py              # Web 管理面板（:7890）
```

## 架构

```
Web (:7890)
    │
    对话 Agent
    ├── 闲聊 → 直接回复
    └── delegate_task → 执行 Agent
                          │
                          执行 Agent (LangGraph)
                          Agent → Tools → SkillLoader → (循环)
                          │
                          20+ 工具
                          消息压缩 & 重试
```

## 功能

| 功能 | 说明 |
|------|------|
| Skills 技能系统 | 运行时加载 SKILL.md，Agent 按需调用 |
| Sub-agent | 并行后台任务，异步结果回传 |
| 权限控制 | 工具级 allow/deny，命令级白名单，均从 config 配置 |
| Web 搜索 | SearXNG 聚合搜索（百度/谷歌/Bing），含缓存 |
| Browser 自动化 | Playwright 驱动，支持打开/点击/输入/截图 |
| Workspace | AGENTS.md / USER.md 自动注入 system prompt |
| 会话管理 | 跨会话历史搜索 |
| Cron 定时任务 | 周期执行 Agent 任务 |
| Docker 沙箱 | 命令可选择在容器内隔离执行 |
| Web 面板 | FastAPI 管理后台（画板/技能/指令/定时） |
| Bot 接入 | AstrBot 插件，支持 QQ |

## 快速开始

```bash
pip install -r requirements.txt
playwright install chromium

copy .env.example .env
# 填入 DEEPSEEK_API_KEY

python main.py              # Web 管理面板 :7890
```

## Docker（推荐）

```bash
# 一键启动 Aisu + SearXNG
docker-compose up -d
```

访问 http://localhost:7890

单容器方式：

```bash
docker build -t aisugent .
docker run -d --name aisu -p 7890:7890 \
  -v aisu_data:/app/data \
  -v %cd%/skills:/app/skills:ro \
  -e DEEPSEEK_API_KEY=sk-xxx \
  -e SEARXNG_BASE_URL=http://host.docker.internal:8888 \
  aisugent
```

## 项目结构

```
├── main.py             入口（CLI/TUI/Web）
├── config.py           配置
├── Dockerfile          容器镜像
├── agent/
│   ├── graph.py        执行图
│   ├── conversation_graph.py  对话图
│   ├── state.py        状态定义
│   ├── skill.py        Skill 系统
│   ├── subagent.py     子 Agent 管理
│   ├── session.py      会话管理
│   ├── cron.py         定时任务
│   └── workspace.py    Workspace 加载
├── tools/              20+ 工具
├── server/             Web 面板（FastAPI）
├── tui/                TUI（Textual）
├── skills/             技能定义（SKILL.md）
├── workspace/          用户设定（AGENTS.md）
└── tests/              测试
```
