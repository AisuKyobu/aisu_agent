"""统一节点日志 — 结构化上下文 + ANSI 颜色 + 关键事件分层"""
import logging
import time

# ANSI 颜色码
C_STEP  = "\033[36m"      # 青色 — 节点处理
C_LLM   = "\033[32m"      # 绿色 — LLM 完成
C_ERR   = "\033[31m"      # 红色 — 错误/限制
C_TOOL  = "\033[34m"      # 蓝色 — 工具调用
C_HINT  = "\033[90m"      # 灰色 — 次要信息
C_RESET = "\033[0m"


_STEP_LABELS = {
    "analyzer": "analyze",
    "router": "route",
    "memory_retriever": "mem",
    "agent": "agent",
    "verifier": "verify",
    "summarizer": "summary",
    "skill_loader": "skill",
    "should_continue": "decide",
    "common": "common",
    "reflector": "reflect",
    "scheduler": "sched",
    "classifier": "classify",
    "verifier_rules": "vrule",
    "sub_agent": "sub",
    "skill_executor": "sk_exec",
    "cron": "cron",
    "graph": "graph",
    "server": "server",
}


class NodeLogger:
    def __init__(self, name: str):
        self._name = name
        self._log = logging.getLogger(f"aisu.{name}")
        self._tid = ""    # thread_id[:8]
        self._step = 0

    # ── 上下文绑定 ──

    def bind(self, thread_id: str = "", step: int = 0):
        self._tid = thread_id[:8] if thread_id else ""
        self._step = step

    # ── 前缀格式 ──

    def _pfx(self) -> str:
        """生成 [tid:8] [sNN] 前缀 (仅 INFO+)"""
        parts = []
        if self._tid:
            parts.append(self._tid)
        if self._step:
            parts.append(f"s{self._step:02d}")
        label = _STEP_LABELS.get(self._name, self._name[:6])
        parts.append(label)
        return " | ".join(parts) + " | " if parts else ""

    # ── 节点生命周期 ──

    def step_start(self, label: str, detail: str = ""):
        self._log.debug(f"{C_STEP}▶ {label}{C_RESET}{' | ' + detail if detail else ''}")

    def step_done(self, label: str, result: str = "", duration: float = 0, warn: bool = False):
        lvl = logging.WARNING if warn else logging.DEBUG
        if lvl == logging.DEBUG and not self._log.isEnabledFor(logging.DEBUG):
            return
        color = C_ERR if warn else C_STEP
        dur_str = f" {C_HINT}{duration:.1f}s{C_RESET}" if duration else ""
        res_str = ""
        if result:
            res_str = f" {C_ERR}→ {result}{C_RESET}" if warn else f" {color}→ {result}{C_RESET}"
        self._log.log(lvl, f"{color}{self._pfx()}{label}{C_RESET}{res_str}{dur_str}")

    # ── LLM 调用 ──

    def llm_start(self, label: str, chars: int):
        self._log.debug(f"{C_HINT}LLM ▶ {label} ({chars} chars){C_RESET}")

    def llm_done(self, label: str, tool_names: list = None, chars: int = 0, duration: float = 0):
        tools = f" (tools: {','.join(tool_names[:5])})" if tool_names else ""
        dur_str = f" {C_HINT}{duration:.1f}s{C_RESET}" if duration else ""
        self._log.info(f"{C_LLM}{self._pfx()}LLM ◀ {label}{C_RESET}{tools}{dur_str}")

    # ── 工具调用 ──

    def tool_call(self, tool_name: str, args: str = ""):
        arg_str = f" {args[:120]}" if args else ""
        self._log.info(f"{C_TOOL}{self._pfx()}⚙ {tool_name}{arg_str}{C_RESET}")

    # ── 关键事件 ──

    def event(self, label: str, detail: str = ""):
        """INFO 级关键事件（限制命中 / HITL / 总结触发等）"""
        d = f" → {detail}" if detail else ""
        self._log.info(f"{C_STEP}{self._pfx()}{label}{d}{C_RESET}")

    # ── 用户 / AI 消息 ──

    def user_msg(self, source: str, text: str):
        self._log.info(f"{C_HINT}{self._pfx()}◉ [{source}] {text[:200]}{C_RESET}")

    def ai_msg(self, text: str, tools: str = ""):
        t = f" [{tools}]" if tools else ""
        self._log.info(f"{C_LLM}{self._pfx()}◉ AI{t} {text[:300]}{C_RESET}")

    # ── 警告 / 调试 ──

    def warn(self, msg: str):
        self._log.warning(f"{C_ERR}{self._pfx()}⚠ {msg}{C_RESET}")

    def debug(self, msg: str):
        self._log.debug(f"{C_HINT}{msg}{C_RESET}")
