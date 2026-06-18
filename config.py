import os

from dotenv import load_dotenv

# 加载 .env
load_dotenv()

# ===== Demo Mode（公开演示限制） =====
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
DEMO_MAX_MSG_PER_IP = int(os.getenv("DEMO_MAX_MSG_PER_IP", "5"))
DEMO_WINDOW_SECONDS = int(os.getenv("DEMO_WINDOW_SECONDS", "86400"))

# ===== DeepSeek 配置 =====
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    raise RuntimeError("DEEPSEEK_API_KEY environment variable is required but not set")

DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-chat")
TEMPERATURE = 0

# ===== Agent配置 =====
MAX_STEPS = 20
MAX_SEARCH_COUNT = 7

REASONING_MAX_STEPS = 20
REASONING_MAX_TOOL_CALLS = 15
REASONING_MAX_FILE_READS = 20
REASONING_MAX_SEARCH = 3
DATA_DIR = os.getenv("DATA_DIR", ".")
WORKSPACE_DIR = os.path.join(DATA_DIR, "workspace")
SESSION_DIR = os.path.join(DATA_DIR, "sessions")
MEMORY_DIR = os.path.join(DATA_DIR, "memory")
CONVERSATION_DB = os.path.join(DATA_DIR, "conversations.db")
CRON_FILE = os.path.join(DATA_DIR, "cron_jobs.json")

# ===== Skills =====
SKILLS_DIR = ["skills"]

# ===== 搜索配置 =====
SEARCH_PRIMARY = "searxng"
SEARCH_FALLBACK = ""
SEARCH_MAX_RESULTS = 5
SEARCH_CACHE_SIZE = 50

SEARXNG_BASE_URL = os.getenv("SEARXNG_BASE_URL", "http://localhost:8888")
SEARXNG_ENGINES = ["sogou", "baidu"]

# ===== Web Server =====
WEB_HOST = "0.0.0.0"
WEB_PORT = 7890

# ===== Browser =====
BROWSER_HEADLESS = True

# ===== 沙箱 =====
SANDBOX_MODE = os.getenv("SANDBOX_MODE", "host")  # host | docker（默认 host，Docker 中可设为 docker）
SANDBOX_IMAGE = "alpine:latest"

# ===== 工具权限 =====
TOOL_ALLOW = ["*"]  # 设为 ["*"] 表示全部放行，设列表则只允许指定工具
TOOL_DENY = []      # 拒绝列表，优先级高于 ALLOW
if DEMO_MODE:
    # Demo 模式只保留只读搜索/读取工具
    TOOL_ALLOW = ["web_search", "web_fetch", "read_file"]
    TOOL_DENY = []

CMD_ALLOW = [
    # Windows
    "dir", "type ", "echo ", "mkdir ",
    "find ", "where ", "tree ", "attrib ", "cd ",
    # Linux
    "ls", "cat ", "grep ", "head ", "tail ", "wc ", "sort ", "uniq ",
    "curl ", "wget ", "tar ", "zip ", "unzip ",
    "ps ", "top ", "df ", "du ", "free ", "ping ", "traceroute ",
    "pwd",
    "python", "python3", "node ", "npm ", "pip ", "pip3",
    # Git（非破坏性）
    "git status", "git log", "git diff", "git branch",
    "git clone", "git checkout", "git merge", "git fetch",
    # Git（需确认）
    "git add", "git commit", "git push",
]

# 永久白名单命令 — 即使匹配危险模式也自动放行
CMD_ALLOW_ALWAYS = [
    "git status", "git log", "git diff", "git branch",
    "ls", "pwd", "dir",
]

# ===== 消息压缩 =====
MAX_MESSAGES = 120
KEEP_MESSAGES = 80
SESSION_TITLE_MAX_LEN = 16
MAX_COMPRESS_CONTENT = 200000      # 单条消息压缩时截断长度
MAX_COMPRESS_TOTAL = 2000000      # 压缩 prompt 中消息文本总长上限
COMPRESSION_THRESHOLD = 0.75      # token 占比触发阈值（超过 context_window * 0.75 时触发压缩）

# ===== 重试 & 超时 =====
MAX_RETRIES = 3
RETRY_DELAY = 2
TOOL_TIMEOUT = 30

# ===== LangSmith 可观测性 =====
LANGCHAIN_TRACING_V2 = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY", "")
LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT", "aisu")
LANGCHAIN_ENDPOINT = os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")

# ===== 日志 =====
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_NODE_VERBOSE = os.getenv("LOG_NODE_VERBOSE", "0") == "1"

# ===== SMTP 邮件 =====
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SITE_URL = os.getenv("SITE_URL", "http://localhost:7890")

# ===== Redis（可选）— 不配置则自动回退到内存实现 =====
REDIS_URL = os.getenv("REDIS_URL", "")                    # 例: redis://redis:6379/0
REDIS_SEARCH_TTL = int(os.getenv("REDIS_SEARCH_TTL", "300"))  # 搜索缓存 TTL（秒）

# ===== 向量数据库（可选）— 语义记忆升级 =====
VECTOR_DB_ENABLED = os.getenv("VECTOR_DB_ENABLED", "true").lower() == "true"
VECTOR_DB_PATH = os.path.join(MEMORY_DIR, "vectors")
