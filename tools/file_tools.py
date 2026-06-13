from langchain.tools import tool

from tools.sandbox import in_sandbox, sandbox_path, ensure_sandbox
from tools.tool_registry import registry


@tool
def read_file(path: str) -> str:
    """读取沙箱内的文件内容。路径自动映射到沙箱目录，总是使用 read_file 返回的实际路径。"""
    try:
        ensure_sandbox()
        safe_path = sandbox_path(path)
        if not in_sandbox(safe_path):
            return "拒绝访问: 文件不在沙箱目录内"
        with open(safe_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"文件不存在: {path}"
    except Exception as e:
        return f"读取失败: {e}"


@tool
def write_file(path: str, content: str) -> str:
    """写入内容到沙箱内的文件。路径自动映射到沙箱目录，写入后使用返回的实际路径进行后续操作。"""
    try:
        ensure_sandbox()
        safe_path = sandbox_path(path)
        if not in_sandbox(safe_path):
            return "拒绝访问: 文件不在沙箱目录内"
        with open(safe_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"已写入 {safe_path}"
    except Exception as e:
        return f"写入失败: {e}"


registry.register(name="read_file", toolset="file", handler=read_file.func,
                  description="读取沙箱内的文件内容")
registry.register(name="write_file", toolset="file", handler=write_file.func,
                  description="写入内容到沙箱内的文件")
