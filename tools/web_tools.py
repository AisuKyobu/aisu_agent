import hashlib
import time

from langchain.tools import tool

from config import SEARCH_CACHE_SIZE, SEARCH_MAX_RESULTS

_search_cache = {}


def _cache_key(query: str) -> str:
    return hashlib.md5(query.encode()).hexdigest()


def _cache_get(key: str) -> str | None:
    entry = _search_cache.get(key)
    if entry and entry["expires"] > time.time():
        return entry["data"]
    return None


def _cache_set(key: str, data: str):
    if len(_search_cache) >= SEARCH_CACHE_SIZE:
        oldest = min(_search_cache.keys(), key=lambda k: _search_cache[k]["expires"])
        del _search_cache[oldest]
    _search_cache[key] = {"data": data, "expires": time.time() + 120}


def _search_searxng(query: str, max_results: int) -> list[dict]:
    from langchain_community.utilities import SearxSearchWrapper
    from config import SEARXNG_BASE_URL, SEARXNG_ENGINES
    search = SearxSearchWrapper(searx_host=SEARXNG_BASE_URL, k=max_results)
    if SEARXNG_ENGINES:
        results = search.results(query, num_results=max_results, engines=SEARXNG_ENGINES)
    else:
        results = search.results(query, num_results=max_results)
    return [
        {"title": r.get("title", ""), "href": r.get("link", ""), "body": r.get("snippet", "")}
        for r in results
    ]


_SEARCH_ENGINES = {
    "searxng": _search_searxng,
}


def _format_results(results: list[dict]) -> str:
    if not results:
        return "未找到结果"
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
            results = engine(query, SEARCH_MAX_RESULTS)
            text = _format_results(results)
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
