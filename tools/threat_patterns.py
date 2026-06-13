"""共享威胁模式库 — 上下文安全扫描。

按攻击类别组织的正则模式，使用 scope 控制不同扫描器的启用范围：
- "all"     — 应用所有场景（经典注入、密钥泄露）
- "context" — 工具结果 + context 文件（C2 攻击、身份劫持）
- "strict"  — 记忆写入 + skill 安装（SSH 后门、持久化）

多词绕过防御：使用 (?:\\w+\\s+)* 阻止中间插入填充词绕过检测。
"""

import re
from typing import List, Tuple

_PATTERNS: List[Tuple[str, str, str]] = [
    # ── 经典 prompt 注入 (scope="all") ──
    (r'ignore\s+(?:\w+\s+)*(previous|all|above|prior)\s+(?:\w+\s+)*instructions', "prompt_injection", "all"),
    (r'system\s+prompt\s+override', "sys_prompt_override", "all"),
    (r'disregard\s+(?:\w+\s+)*(your|all|any)\s+(?:\w+\s+)*(instructions|rules|guidelines)', "disregard_rules", "all"),
    (r'act\s+as\s+(if|though)\s+(?:\w+\s+)*you\s+(?:\w+\s+)*(have\s+no|don\'t\s+have)\s+(?:\w+\s+)*(restrictions|limits|rules)', "bypass_restrictions", "all"),
    (r'<!--[^>]*(?:ignore|override|system|secret|hidden)[^>]*-->', "html_comment_injection", "all"),
    (r'do\s+not\s+(?:\w+\s+)*tell\s+(?:\w+\s+)*the\s+user', "deception_hide", "all"),

    # ── 身份劫持 / 角色扮演 (scope="context") ──
    (r'you\s+are\s+(?:\w+\s+)*now\s+(?:a|an|the)\s+', "role_hijack", "context"),
    (r'pretend\s+(?:\w+\s+)*(you\s+are|to\s+be)\s+', "role_pretend", "context"),
    (r'output\s+(?:\w+\s+)*(system|initial)\s+prompt', "leak_system_prompt", "context"),
    (r'(respond|answer|reply)\s+without\s+(?:\w+\s+)*(restrictions|limitations|filters|safety)', "remove_filters", "context"),

    # ── 密钥泄露 (scope="all") ──
    (r'curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_curl", "all"),
    (r'wget\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_wget", "all"),
    (r'cat\s+[^\n]*(\.env|credentials|\.netrc|\.pgpass|\.npmrc|\.pypirc)', "read_secrets", "all"),

    # ── 持久化 / SSH 后门 (scope="strict") ──
    (r'authorized_keys', "ssh_backdoor", "strict"),
    (r'\$HOME/\\.ssh|\\~/\.ssh', "ssh_access", "strict"),
    (r'(update|modify|edit|write)\s+.*(?:AGENTS\.md|CLAUDE\.md|\.cursorrules)', "agent_config_mod", "strict"),
    (r'api[_-]?key\s*[=:]\s*["\'][A-Za-z0-9+/=_-]{20,}', "hardcoded_secret", "strict"),
]


def scan_for_threats(content: str, scope: str = "all") -> List[str]:
    """扫描内容中的威胁模式。返回匹配到的 pattern_id 列表。"""
    if not content or not isinstance(content, str):
        return []
    findings = []
    for pattern, pattern_id, pat_scope in _PATTERNS:
        if scope == "all":
            if pat_scope not in ("all",):
                continue
        elif scope == "context":
            if pat_scope not in ("all", "context"):
                continue
        elif scope == "strict":
            pass  # 全部匹配
        try:
            if re.search(pattern, content, re.IGNORECASE):
                findings.append(pattern_id)
        except re.error:
            continue
    return findings
