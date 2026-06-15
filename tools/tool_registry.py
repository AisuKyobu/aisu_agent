"""Agent 工具自注册系统。

每个工具文件在模块顶层调用 ``registry.register()``，
通过 AST 扫描自动发现，无需手动维护 TOOLS 列表。

设计采用"自注册 + AST 发现"模式：模块导入时注册，启动时扫描解析。
"""

import ast
import importlib
import json
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set


def _is_register_call(node: ast.AST) -> bool:
    """判断 AST 节点是否为 ``registry.register(...)`` 调用表达式。"""
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return False
    func = node.value.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "register"
        and isinstance(func.value, ast.Name)
        and func.value.id == "registry"
    )


def _module_registers(path: Path) -> bool:
    """判断模块是否包含顶层 ``registry.register(...)`` 调用。"""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError):
        return False
    return any(_is_register_call(stmt) for stmt in tree.body)


class AgentTool:
    """注册工具的元数据。"""
    __slots__ = ("name", "toolset", "schema", "handler", "check_fn",
                 "requires_env", "is_async", "description", "max_result_size_chars")

    def __init__(self, name, toolset, schema, handler, check_fn=None,
                 requires_env=None, is_async=False, description="",
                 max_result_size_chars=None):
        self.name = name
        self.toolset = toolset
        self.schema = schema
        self.handler = handler
        self.check_fn = check_fn
        self.requires_env = requires_env or []
        self.is_async = is_async
        self.description = description or schema.get("description", "")
        self.max_result_size_chars = max_result_size_chars


_CHECK_TTL = 30.0
_check_cache: Dict[Callable, tuple] = {}
_check_cache_lock = threading.Lock()


def _check_fn_cached(fn: Callable) -> bool:
    now = time.monotonic()
    with _check_cache_lock:
        cached = _check_cache.get(fn)
        if cached is not None:
            ts, value = cached
            if now - ts < _CHECK_TTL:
                return value
    try:
        value = bool(fn())
    except Exception:
        value = False
    with _check_cache_lock:
        _check_cache[fn] = (now, value)
    return value


def _coerce_tool_args(name: str, args: dict, entry) -> dict:
    if not args or not isinstance(args, dict):
        return args or {}
    schema = entry.schema
    properties = (schema.get("parameters") or {}).get("properties")
    if not properties:
        return args
    for key, value in list(args.items()):
        prop = properties.get(key)
        if not prop:
            continue
        expected = prop.get("type")
        if expected == "integer" and isinstance(value, str):
            try:
                f = float(value)
                if f == int(f):
                    args[key] = int(f)
            except (ValueError, OverflowError):
                pass
        elif expected == "number" and isinstance(value, str):
            try:
                args[key] = float(value)
            except (ValueError, OverflowError):
                pass
        elif expected == "boolean" and isinstance(value, str):
            low = value.strip().lower()
            if low == "true":
                args[key] = True
            elif low == "false":
                args[key] = False
        elif expected == "array" and value is not None and not isinstance(value, (list, tuple)):
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        args[key] = parsed
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass
            args[key] = [value]
        elif isinstance(expected, list) and isinstance(value, str):
            for t in expected:
                if t == "integer":
                    try:
                        f = float(value)
                        if f == int(f):
                            args[key] = int(f)
                            break
                    except (ValueError, OverflowError):
                        pass
                elif t == "number":
                    try:
                        args[key] = float(value)
                        break
                    except (ValueError, OverflowError):
                        pass
                elif t == "boolean":
                    low = value.strip().lower()
                    if low in ("true", "false"):
                        args[key] = True if low == "true" else False
                        break
    return args


class ToolRegistry:
    """工具自注册中心（单例）。"""

    def __init__(self):
        self._tools: Dict[str, AgentTool] = {}
        self._lock = threading.RLock()
        self._generation = 0

    def register(self, name, toolset, handler, check_fn=None,
                 requires_env=None, is_async=False, schema=None,
                 description="", max_result_size_chars=None):
        if schema is None:
            schema = {"name": name, "description": description, "parameters": {}}
        with self._lock:
            existing = self._tools.get(name)
            if existing and existing.toolset != toolset:
                import logging
                logging.getLogger("aisu.registry").warning(
                    "Tool '%s' already registered in toolset '%s' — skipping '%s'",
                    name, existing.toolset, toolset,
                )
                return
            self._tools[name] = AgentTool(
                name=name, toolset=toolset, schema=schema,
                handler=handler, check_fn=check_fn,
                requires_env=requires_env, is_async=is_async,
                description=description or schema.get("description", ""),
                max_result_size_chars=max_result_size_chars,
            )
            self._generation += 1

    def discover(self, tools_dir=None):
        tools_path = Path(tools_dir) if tools_dir else Path(__file__).resolve().parent
        module_names = [
            f"tools.{path.stem}"
            for path in sorted(tools_path.glob("*.py"))
            if path.name not in {"__init__.py", "tool_registry.py", "registry.py"}
            and _module_registers(path)
        ]
        for mod_name in module_names:
            try:
                importlib.import_module(mod_name)
            except Exception as e:
                import logging
                logging.getLogger("aisu.registry").warning(
                    "Could not import tool module %s: %s", mod_name, e
                )

    def get_definitions(self, tool_names: Set[str]) -> List[dict]:
        """返回 OpenAI 格式的工具 schema 列表（仅包括 check_fn 通过的工具）。"""
        result = []
        with self._lock:
            entries = list(self._tools.values())
        entries_by_name = {e.name: e for e in entries}
        for name in sorted(tool_names):
            entry = entries_by_name.get(name)
            if not entry:
                continue
            if entry.check_fn and not _check_fn_cached(entry.check_fn):
                continue
            result.append(entry.schema if isinstance(entry.schema, dict)
                          else {"name": entry.name, "description": entry.description,
                                "parameters": entry.schema})
        return result

    def dispatch(self, name, args, **kwargs):
        entry = self._tools.get(name)
        if not entry:
            return f'{{"error": "Unknown tool: {name}"}}'
        from tools.toolsets import is_tool_allowed
        if not is_tool_allowed(name):
            return json.dumps({"error": f"工具 {name} 在当前 Profile 中被禁用"}, ensure_ascii=False)
        try:
            args = _coerce_tool_args(name, args, entry)
            if isinstance(args, dict):
                return entry.handler(**args, **kwargs)
            return entry.handler(args, **kwargs)
        except Exception as e:
            from tools.error_sanitizer import sanitize_tool_error
            return json.dumps({"error": sanitize_tool_error(str(e))}, ensure_ascii=False)

    def get_tool_names_for_toolset(self, toolset: str) -> List[str]:
        with self._lock:
            return sorted(e.name for e in self._tools.values() if e.toolset == toolset)

    def get_all_tool_names(self) -> List[str]:
        with self._lock:
            return sorted(self._tools.keys())

    def get_toolset_for_tool(self, name: str) -> Optional[str]:
        entry = self._tools.get(name)
        return entry.toolset if entry else None


registry = ToolRegistry()
