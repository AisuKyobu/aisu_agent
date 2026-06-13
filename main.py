"""Aisu — AI Agent Web 面板入口."""

import logging
import os
import signal
import sys

import config  # 加载 .env + 所有配置

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)

# ── LangSmith 可观测性 ──
if config.LANGCHAIN_TRACING_V2:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = config.LANGCHAIN_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = config.LANGCHAIN_PROJECT
    os.environ["LANGCHAIN_ENDPOINT"] = config.LANGCHAIN_ENDPOINT
    logging.getLogger("aisu").info(
        "LangSmith tracing enabled — project: %s", config.LANGCHAIN_PROJECT
    )
else:
    logging.getLogger("aisu").info("LangSmith tracing disabled")

if __name__ == "__main__":
    import uvicorn

    if sys.platform == "win32":
        signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))

    uvicorn.run("server.app:app", host=config.WEB_HOST, port=config.WEB_PORT, log_level="info")
