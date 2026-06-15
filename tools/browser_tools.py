import threading

from langchain.tools import tool

from config import BROWSER_HEADLESS
from tools.tool_registry import registry


class BrowserManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._playwright = None
        self._browser = None
        self._page = None

    def ensure(self):
        with self._lock:
            if self._page is not None:
                return self._page
            from playwright.sync_api import sync_playwright
            import os
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=BROWSER_HEADLESS,
                executable_path=os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH", ""),
                args=["--no-sandbox", "--disable-gpu"],
            )
            self._page = self._browser.new_page()
            return self._page

    def close(self):
        with self._lock:
            if self._page:
                self._page.close()
                self._page = None
            if self._browser:
                self._browser.close()
                self._browser = None
            if self._playwright:
                self._playwright.stop()
                self._playwright = None

    def current_page(self):
        return self._page


_manager = BrowserManager()


def _page_text(page) -> str:
    text = page.inner_text("body")
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return "\n".join(lines[:80]) or "(空页面)"


@tool
def browser_open(url: str) -> str:
    """在浏览器中打开指定URL，返回页面标题和正文内容。"""
    try:
        page = _manager.ensure()
        page.goto(url, timeout=30000)
        title = page.title()
        text = _page_text(page)
        from tools.untrusted_wrapper import wrap_untrusted_content
        return wrap_untrusted_content("browser_open", f"标题: {title}\n\n{text}")
    except Exception as e:
        return f"打开失败: {e}"


def _make_selector(el) -> str:
    """Generate a CSS selector for an element."""
    try:
        tag = el.evaluate("el => el.tagName.toLowerCase()")
        el_id = el.get_attribute("id")
        if el_id:
            return f"#{el_id}"
        testid = el.get_attribute("data-testid") or el.get_attribute("data-test-id")
        if testid:
            return f"[data-testid='{testid}']"
        text = el.inner_text().strip()[:30]
        classes = (el.get_attribute("class") or "").strip()
        if text and len(text) < 25:
            return f'{tag}:has-text("{text}")'
        if classes:
            cls = classes.split()[0]
            return f"{tag}.{cls}"
        return tag
    except Exception:
        return "?"


@tool
def browser_inspect() -> str:
    """获取当前页面上所有可交互元素（按钮、输入框、链接等）及其选择器。"""
    try:
        page = _manager.ensure()
        elements = page.locator("button, input, a, select, textarea, [role='button'], [role='textbox']")
        count = elements.count()
        if count == 0:
            return "页面上没有可交互元素"
        lines = ["可交互元素列表："]
        for i in range(min(count, 30)):
            el = elements.nth(i)
            tag = el.evaluate("el => el.tagName.toLowerCase()")
            text = el.inner_text().strip()[:40]
            sel = _make_selector(el)
            lines.append(f"  {i}. <{tag}> \"{text}\" → {sel}")
        return "\n".join(lines)
    except Exception as e:
        return f"获取失败: {e}"


@tool
def browser_click(selector: str) -> str:
    """点击页面上的某个元素。selector 是 CSS 选择器（如 '#btn'、'.nav a'）。"""
    try:
        page = _manager.ensure()
        page.click(selector)
        text = _page_text(page)
        return f"已点击 {selector}\n\n{text}"
    except Exception as e:
        return f"点击失败: {e}"


@tool
def browser_type(selector: str, text: str) -> str:
    """在输入框中输入文字。selector 是 CSS 选择器，text 是要输入的内容。"""
    try:
        page = _manager.ensure()
        page.fill(selector, text)
        return f"已在 {selector} 输入: {text}"
    except Exception as e:
        return f"输入失败: {e}"


@tool
def browser_screenshot() -> str:
    """对当前页面截图（保存到文件），返回截图路径。"""
    try:
        page = _manager.ensure()
        import os
        path = os.path.join("sandbox", "browser_screenshot.png")
        page.screenshot(path=path)
        return f"截图已保存: {path}"
    except Exception as e:
        err = str(e)
        if "Cannot switch to a different thread" in err:
            err = "页面处于非活动状态，请先打开新页面或重新执行上一步操作"
        return f"截图失败: {err}"


registry.register(name="browser_open", toolset="browser", handler=browser_open.func,
                  description="在浏览器中打开指定URL，返回页面内容")
registry.register(name="browser_click", toolset="browser", handler=browser_click.func,
                  description="点击页面上的元素，selector为CSS选择器")
registry.register(name="browser_type", toolset="browser", handler=browser_type.func,
                  description="在输入框中输入文字")
registry.register(name="browser_screenshot", toolset="browser", handler=browser_screenshot.func,
                  description="对当前页面截图保存到文件")
registry.register(name="browser_inspect", toolset="browser", handler=browser_inspect.func,
                  description="获取当前页面所有可交互元素及其选择器")
