"""Execution Intent — Analyzer v2 输出模式，从单一 task_type 升级为完整执行意图"""

import json
from agent.logger import NodeLogger

_log = NodeLogger("classifier")

# ── Execution Intent Schema ──

EXECUTION_MODES = ("direct", "react", "dag", "repair-loop", "research-loop")
VERIFIER_LEVELS = ("L1", "L1+L2", "L1+L2+L3", "none")
VERIFIER_FREQUENCIES = ("every_step", "milestone", "final_only")
AUTONOMY_LEVELS = ("full_auto", "confirm_destructive", "always_ask", "read_only")
HORIZONS = ("short", "medium", "long")

EXECUTION_INTENT_SCHEMA = """
{
  "execution_mode": "direct|react|dag|repair-loop|research-loop",
  "verifier_level": "L1|L1+L2|L1+L2+L3|none",
  "verifier_frequency": "every_step|milestone|final_only",
  "autonomy_level": "full_auto|confirm_destructive|always_ask|read_only",
  "horizon": "short|medium|long",
  "planning_depth": 3,
  "retry_max_total": 3,
  "retry_per_step": 2,
  "risk_level": "low|medium|high|critical",
  "task_type": "deterministic|search|reasoning|action|planning",
  "goal": "一句话目标摘要，用于记忆检索匹配",
  "missing_params": [],
  "reasoning": "一句话解释决策逻辑"
}
"""

ANALYZER_PROMPT_V2 = f"""你是一个 Agent 执行元控制器。根据用户请求，输出完整的执行意图 JSON。

## 输入
用户消息: {{user_message}}

## goal 提取规则
从用户消息中提取一句简洁的目标描述（去噪摘要），用于记忆检索匹配历史任务。
- 去掉问候/闲聊/语气词（如"你好"、"我想问一下"、"帮忙看看"）
- 保留核心任务动词和关键名词（如"部署Flask到Docker"、"分析Nginx错误日志"）
- 不超过 30 个字
- 如果是纯闲聊无实质任务，goal 留空字符串

## execution_mode 判断规则

### direct — 直接回复
- 问候、闲聊、纯知识问答、翻译、简单计算
- 系统状态查询（dir/ls/ps 等仅查看不修改的）

### react — 单线程探索
- 搜索后总结 (search)
- 分析代码/日志 (reasoning)  
- 短操作任务 (action, < 5 步)
- 特点: 不确定具体步骤，边做边看

### dag — 结构化多步骤
- 部署项目、配置环境、数据处理管道
- 用户明确了目标，或任务天然可拆解
- 特点: 步骤间有明确依赖关系

### repair-loop — 修复/排错
- 用户说"修复"、"debug"、"排查一下为什么失败"、"帮我解决这个报错"
- 代码/配置报错需要反复尝试修复
- 特点: 目标是消除错误，允许反复尝试，最多 5 次

### research-loop — 深度调研
- 用户说"全面调研"、"深入对比"、"深度分析"、"系统研究"
- "调研一下 A 和 B 的差异"、"对比三种方案的优劣"
- 特点: 逐层深入，连续 2 轮无新信息则停止，最多 10 轮

## autonomy_level 规则
- rm -rf / git push --force / modify system config → confirm_destructive
- 纯读操作 (read_file/search/query) → read_only  
- 沙箱内安全操作 → full_auto
- 请求模糊 → always_ask

## 特殊情况
- 用户说"记住"/"记住我"/"请记住" → execution_mode: react, task_type: action
- 用户回复"允许"/"可以"/"同意"/"行"/"好" 且 上文 AI 在询问是否执行某命令
  → execution_mode: react, task_type: action, autonomy_level: full_auto
- 用户回复"拒绝"/"不行"/"不允许" → execution_mode: direct, task_type: deterministic

## 其他字段默认
- verifier_level: 一般 L1，写文件 L1+L2，关键任务 L1+L2+L3
- risk_level: 写/删/改操作 high，纯读 low
- horizon: 闲聊 short，搜索/分析 medium，部署/规划 long

## 输出
只输出 JSON，不要其他内容。
{EXECUTION_INTENT_SCHEMA}
"""


def parse_intent(raw: str) -> dict:
    """解析 Analyzer LLM 输出的 JSON → ExecutionIntent dict。"""
    try:
        intent = json.loads(raw.strip())
    except json.JSONDecodeError:
        # try to extract JSON from markdown
        import re

        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                intent = json.loads(m.group(0))
            except json.JSONDecodeError:
                intent = _default_intent()
        else:
            intent = _default_intent()

    # normalize
    intent.setdefault("execution_mode", "react")
    intent.setdefault("verifier_level", "L1")
    intent.setdefault("verifier_frequency", "every_step")
    intent.setdefault("autonomy_level", "full_auto")
    intent.setdefault("horizon", "medium")
    intent.setdefault("risk_level", "low")
    intent.setdefault("task_type", "reasoning")
    intent.setdefault("goal", "")
    intent.setdefault("missing_params", [])
    intent.setdefault("retry_max_total", 3)
    intent.setdefault("retry_per_step", 2)
    intent.setdefault("planning_depth", 3)
    intent.setdefault("reasoning", "")
    return intent


def _default_intent() -> dict:
    return {
        "execution_mode": "react",
        "verifier_level": "L1",
        "verifier_frequency": "every_step",
        "autonomy_level": "full_auto",
        "horizon": "medium",
        "risk_level": "low",
        "task_type": "reasoning",
        "goal": "",
        "missing_params": [],
    }


def resolve_intent(intent: dict) -> dict:
    """将 ExecutionIntent 展开为运行时配置（替代 router_node 的职责）。"""
    em = intent.get("execution_mode", "react")
    al = intent.get("autonomy_level", "full_auto")
    horizon = intent.get("horizon", "medium")

    # 按 horizon 映射 max_steps
    horizon_steps = {"short": 5, "medium": 15, "long": 30}
    max_steps = horizon_steps.get(horizon, 15)

    # 按 execution_mode 生成约束文本
    mode_constraints = {
        "direct": "直接回复，不调用任何工具。",
        "react": "每次只做一个决定，做完后根据结果决定下一步。",
        "dag": f"严格按 task_graph 的节点顺序执行。最大 {intent.get('planning_depth', 3)} 步。",
        "repair-loop": "当前处于修复模式。目标是消除错误，而不是完成原始任务。最多尝试 5 次修复。",
        "research-loop": "逐层深入搜索。若连续 2 轮无新信息则停止。最多 10 轮。",
    }

    return {
        "execution_mode": em,
        "verifier_level": intent.get("verifier_level", "L1"),
        "verifier_frequency": intent.get("verifier_frequency", "every_step"),
        "autonomy_level": al,
        "max_steps": max_steps,
        "retry_max_total": intent.get("retry_max_total", 3),
        "retry_per_step": intent.get("retry_per_step", 2),
        "task_type": intent.get("task_type", "reasoning"),
        "missing_params": intent.get("missing_params", []),
        "task_constraints": mode_constraints.get(em, mode_constraints["react"]),
        "risk_level": intent.get("risk_level", "low"),
    }
