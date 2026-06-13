"""共享路径安全验证 — 防止目录穿越和符号链接逃逸。

使用 Path.resolve()（跟踪 symlink + 归一化 ..）而非 os.path.abspath()
（纯字符串拼接），确保安全。
"""

import os
from pathlib import Path
from typing import Optional


def validate_within_dir(path: str, root: str) -> Optional[str]:
    """确保 path 解析后的真实路径在 root 目录内。

    Returns:
        None 表示安全；否则返回错误消息字符串。
    """
    try:
        resolved = Path(path).resolve()
        root_resolved = Path(root).resolve()
        resolved.relative_to(root_resolved)
        return None
    except (ValueError, OSError) as exc:
        return f"Path escapes allowed directory: {exc}"


def has_traversal_component(path_str: str) -> bool:
    """快速检查是否包含 .. 目录穿越组件。"""
    return ".." in Path(path_str).parts


def safe_join(root: str, filename: str) -> str:
    """安全拼接路径，拒绝穿越组件和绝对路径"""
    if ".." in filename or filename.startswith(("/", "\\")):
        raise ValueError(f"Illegal filename (traversal detected): {filename}")
    basename = os.path.basename(filename)
    return os.path.join(root, basename)
