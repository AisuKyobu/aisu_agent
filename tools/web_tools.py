import hashlib
import time

from langchain.tools import tool

from config import SEARCH_CACHE_SIZE, SEARCH_MAX_RESULTS, REDIS_SEARCH_TTL

_search_cache = {}


def _cache_key(query: str) -> str:
    return f"aisu:search:{hashlib.md5(query.encode()).hexdigest()}"


def _redis_client():
    try:
        from server.redis_client import get_redis
        return get_redis()
    except Exception:
        return None


def _cache_get(key: str) -> str | None:
    # Redis 优先
    r = _redis_client()
    if r:
        try:
            val = r.get(key)
            if val:
                return val.decode("utf-8")
        except Exception:
            pass
    # 内存回退
    entry = _search_cache.get(key)
    if entry and entry["expires"] > time.time():
        return entry["data"]
    return None


def _cache_set(key: str, data: str):
    # 同时写 Redis（主）和内存（回退）
    r = _redis_client()
    if r:
        try:
            r.setex(key, REDIS_SEARCH_TTL, data)
        except Exception:
            pass
    # 内存缓存也保留一份，作为 Redis 不可用时的回退
    if len(_search_cache) >= SEARCH_CACHE_SIZE:
        oldest = min(_search_cache.keys(), key=lambda k: _search_cache[k]["expires"])
        del _search_cache[oldest]
    _search_cache[key] = {"data": data, "expires": time.time() + 120}


def _search_searxng(query: str, max_results: int) -> dict:
    """调用 SearXNG，返回 {results, unresponsive_engines}。

    unresponsive_engines 用于让 LLM 知道是搜索引擎本身被 CAPTCHA/超时拦截，
    从而停止无意义的重复搜索。
    """
    import requests
    from config import SEARXNG_BASE_URL, SEARXNG_ENGINES
    url = f"{SEARXNG_BASE_URL}/search"
    engines = SEARXNG_ENGINES or ["baidu", "sogou"]
    resp = requests.get(url, params={"q": query, "format": "json", "engines": ",".join(engines)},
                        headers={"X-Forwarded-For": "127.0.0.1"}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])[:max_results]
    return {
        "results": [
            {"title": r.get("title", ""), "href": r.get("url", ""), "body": r.get("content", "")}
            for r in results
        ],
        "unresponsive_engines": data.get("unresponsive_engines", []),
    }


_SEARCH_ENGINES = {
    "searxng": _search_searxng,
}


def _format_results(data: dict) -> str:
    results = data.get("results", []) if isinstance(data, dict) else data
    unresponsive = data.get("unresponsive_engines", []) if isinstance(data, dict) else []
    if not results:
        lines = [f"搜索完成，未找到与 '{data.get('query', '')}' 相关的结果。"]
        if unresponsive:
            reasons = ", ".join(f"{name} ({reason})" for name, reason in unresponsive)
            lines.append(f"搜索引擎状态：{reasons}。")
        lines.append("搜索后端暂时不可用，请不要继续换词搜索，直接根据已有知识回答用户。")
        return " ".join(lines)
    lines = []
    for r in results:
        lines.append(f"- {r['title']}\n  {r['href']}\n  {r['body']}")
    return "\n\n".join(lines)


def _execute_search(query: str) -> str:
    cache_key = _cache_key(query)
    cached = _cache_get(cache_key)
    if cached:
        return cached

    engines = ["searxng"]
    last_error = ""
    for name in engines:
        engine = _SEARCH_ENGINES.get(name)
        if not engine:
            last_error = f"未知搜索引擎: {name}"
            continue
        try:
            data = engine(query, SEARCH_MAX_RESULTS)
            data["query"] = query
            text = _format_results(data)
            _cache_set(cache_key, text)
            return text
        except Exception as e:
            err = str(e).lower()
            if "connection refused" in err:
                last_error = "搜索服务未启动 (SearXNG 不可达)"
            elif "max retries exceeded" in err:
                last_error = "搜索服务连接超时，请检查网络或 SearXNG 是否运行"
            elif "timeout" in err:
                last_error = "搜索请求超时"
            else:
                last_error = f"搜索失败 ({name}): {str(e)[:100]}"
            continue

    return last_error


import ipaddress
import socket
from urllib.parse import urlparse

_BLOCKED_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private_host(hostname: str) -> bool:
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            addr = ipaddress.ip_address(socket.gethostbyname(hostname))
        except (socket.gaierror, ValueError):
            return False
    return any(addr in net for net in _BLOCKED_NETS)


from tools.tool_registry import registry

@tool
def web_search(query: str) -> str:
    """搜索互联网信息。使用 SearXNG 聚合搜索，支持缓存。query 是搜索关键词。"""
    from tools.untrusted_wrapper import wrap_untrusted_content
    return wrap_untrusted_content("web_search", _execute_search(query))


@tool
def web_fetch(url: str) -> str:
    """获取网页文本内容。url 是网页地址。"""
    try:
        import requests
        from bs4 import BeautifulSoup
        parsed = urlparse(url)
        if _is_private_host(parsed.hostname):
            return f"拒绝访问: {parsed.hostname} 是内部地址，不允许 SSRF"
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser", from_encoding="utf-8")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [l for l in text.split("\n") if len(l.strip()) > 20]
        result = "\n".join(lines[:80]) or "无法提取正文"
        from tools.untrusted_wrapper import wrap_untrusted_content
        return wrap_untrusted_content("web_fetch", result)
    except Exception as e:
        return f"获取失败: {e}"


registry.register(name="web_search", toolset="web", handler=web_search.func,
                  description="搜索互联网信息，使用 SearXNG 聚合搜索")
registry.register(name="web_fetch", toolset="web", handler=web_fetch.func,
                  description="获取网页文本内容")
